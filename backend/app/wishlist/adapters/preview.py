"""Product URL preview adapters (manual fallback + HTTP scrape)."""

from __future__ import annotations

import html
import ipaddress
import json
import os
import re
import socket
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx

from app.wishlist.domain.errors import ValidationError

_MAX_BYTES = 512_000  # hard cap — product meta is almost always in the first chunk / <head>
_DEFAULT_TIMEOUT = 10.0
_MAX_REDIRECTS = 8
_HEAD_END = re.compile(rb"</head\s*>", re.IGNORECASE)
# Keep a little body after </head> for stores that put JSON-LD just below it.
_POST_HEAD_SLACK = 64_000
_BOT_WALL_HINTS = (
    "continue shopping",
    "robot check",
    "enter the characters you see",
    "api-services-support@amazon",
    "not a robot",
    "automated access",
)
_AMAZON_HOST_SUFFIXES = (
    "amazon.com",
    "amazon.in",
    "amazon.co.uk",
    "amazon.de",
    "amazon.ca",
    "amazon.com.au",
    "amzn.in",
    "amzn.to",
    "a.co",
)

_META_PROP = re.compile(
    r'<meta[^>]+(?:property|name)\s*=\s*["\']([^"\']+)["\'][^>]+content\s*=\s*["\']([^"\']*)["\']',
    re.IGNORECASE,
)
_META_PROP_REV = re.compile(
    r'<meta[^>]+content\s*=\s*["\']([^"\']*)["\'][^>]+(?:property|name)\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_JSON_LD = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


class NullPreview:
    async def from_url(self, url: str) -> Dict[str, Any]:
        raise ValidationError("URL preview unavailable; enter option details manually")


def _preview_enabled() -> bool:
    return os.getenv("WISHLIST_PREVIEW_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _timeout_s() -> float:
    raw = os.getenv("WISHLIST_PREVIEW_TIMEOUT_S", str(_DEFAULT_TIMEOUT)).strip()
    try:
        return max(1.0, min(float(raw), 20.0))
    except ValueError:
        return _DEFAULT_TIMEOUT


def _user_agent() -> str:
    return os.getenv(
        "WISHLIST_PREVIEW_USER_AGENT",
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
    ).strip()


def _draft_has_signal(draft: Dict[str, Any]) -> bool:
    return bool(
        draft.get("title") or draft.get("image_url") or draft.get("price") is not None
    )


def _is_amazon_host(hostname: Optional[str]) -> bool:
    host = (hostname or "").lower().rstrip(".")
    return any(host == s or host.endswith("." + s) for s in _AMAZON_HOST_SUFFIXES)


def _looks_like_bot_wall(html_text: str) -> bool:
    lowered = (html_text or "")[:8000].lower()
    return any(hint in lowered for hint in _BOT_WALL_HINTS)


def _fetch_blocked_message(url: str, status: Optional[int] = None) -> str:
    host = urlparse(url).hostname
    if _is_amazon_host(host):
        return (
            "Amazon blocks automated previews for short/share links. "
            "Open the product in a browser, copy the full amazon.in/dp/… URL, "
            "or enter title, image, and price manually."
        )
    if status is not None:
        return f"could not fetch url (HTTP {status})"
    return "could not fetch url; enter details manually"


def _read_enough_html(buf: bytearray) -> bool:
    """
    Stop streaming once </head> is seen (+ small slack), or hard cap is hit.
    Large storefronts (Shopify etc.) often exceed 1MB; OG/JSON-LD live in <head>.
    """
    if len(buf) >= _MAX_BYTES:
        return True
    m = _HEAD_END.search(buf)
    if not m:
        return False
    return len(buf) >= m.end() + _POST_HEAD_SLACK


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
        return True
    if ip.is_reserved or ip.is_unspecified:
        return True
    # Explicit cloud metadata / CGNAT ranges
    blocked_nets = [
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("100.64.0.0/10"),
        ipaddress.ip_network("0.0.0.0/8"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("fe80::/10"),
    ]
    return any(ip in net for net in blocked_nets)


def assert_safe_public_url(url: str) -> str:
    """
    Validate URL scheme/host and resolve DNS to public IPs only (SSRF guard).
    Returns normalized URL string.
    """
    raw = (url or "").strip()
    if not raw or len(raw) > 2000:
        raise ValidationError("url is required and must be under 2000 characters")

    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError("only http and https URLs are allowed")
    host = parsed.hostname
    if not host:
        raise ValidationError("url host is required")
    if host.lower() in {"localhost", "metadata.google.internal"}:
        raise ValidationError("url host is not allowed")

    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as e:
        raise ValidationError("could not resolve url host") from e

    if not infos:
        raise ValidationError("could not resolve url host")

    for info in infos:
        sockaddr = info[4]
        ip = ipaddress.ip_address(sockaddr[0])
        if _is_blocked_ip(ip):
            raise ValidationError("url resolves to a private or blocked address")

    # Rebuild without credentials / fragments
    netloc = host
    if parsed.port:
        netloc = f"{host}:{parsed.port}"
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme}://{netloc}{path}{query}"


def _decode_entities(value: str) -> str:
    return html.unescape(value or "").strip()


def _collect_meta(html_text: str) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    for prop, content in _META_PROP.findall(html_text):
        meta[prop.lower()] = _decode_entities(content)
    for content, prop in _META_PROP_REV.findall(html_text):
        meta.setdefault(prop.lower(), _decode_entities(content))
    return meta


def _parse_price(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    # Keep first number-like token (handles "$1,299.00", "INR 899", "12.50 USD")
    cleaned = text.replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)", cleaned)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _walk_jsonld(node: Any, out: List[Dict[str, Any]]) -> None:
    if isinstance(node, list):
        for item in node:
            _walk_jsonld(item, out)
        return
    if not isinstance(node, dict):
        return
    types = node.get("@type")
    type_list = types if isinstance(types, list) else [types] if types else []
    type_names = {str(t).lower() for t in type_list}
    if "product" in type_names or "productgroup" in type_names:
        out.append(node)
    if "@graph" in node:
        _walk_jsonld(node["@graph"], out)
    for v in node.values():
        if isinstance(v, (dict, list)):
            _walk_jsonld(v, out)


def _from_jsonld(html_text: str) -> Dict[str, Any]:
    products: List[Dict[str, Any]] = []
    for block in _JSON_LD.findall(html_text):
        raw = block.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        _walk_jsonld(data, products)

    if not products:
        return {}

    product = products[0]
    title = product.get("name")
    image = product.get("image")
    if isinstance(image, list) and image:
        image = image[0]
    if isinstance(image, dict):
        image = image.get("url") or image.get("contentUrl")

    price = None
    currency = None
    offers = product.get("offers")
    offer_list = offers if isinstance(offers, list) else [offers] if offers else []
    for offer in offer_list:
        if not isinstance(offer, dict):
            continue
        price = _parse_price(offer.get("price") or offer.get("lowPrice"))
        currency = offer.get("priceCurrency")
        if price is not None:
            break

    return {
        "title": _decode_entities(str(title)) if title else None,
        "image_url": str(image).strip() if image else None,
        "price": price,
        "currency": str(currency).strip()[:8] if currency else None,
    }


def parse_product_html(html_text: str, base_url: str) -> Dict[str, Any]:
    """Extract title / image / price from HTML. Pure function for unit tests."""
    meta = _collect_meta(html_text)
    jsonld = _from_jsonld(html_text)

    title = (
        meta.get("og:title")
        or meta.get("twitter:title")
        or jsonld.get("title")
    )
    if not title:
        m = _TITLE_TAG.search(html_text)
        if m:
            title = _decode_entities(re.sub(r"\s+", " ", m.group(1)))

    image = (
        meta.get("og:image")
        or meta.get("og:image:url")
        or meta.get("twitter:image")
        or meta.get("twitter:image:src")
        or jsonld.get("image_url")
    )
    if image:
        image = urljoin(base_url, image)

    price = _parse_price(
        meta.get("product:price:amount")
        or meta.get("og:price:amount")
        or meta.get("twitter:data1")
        or jsonld.get("price")
    )
    currency = (
        meta.get("product:price:currency")
        or meta.get("og:price:currency")
        or jsonld.get("currency")
    )
    if currency:
        currency = currency.strip()[:8]

    return {
        "title": (title[:150] if title else None),
        "url": base_url,
        "price": price,
        "currency": currency,
        "image_url": (image[:2000] if image else None),
        "notes": None,
    }


class HttpScrapePreview:
    """Fetch a public product page and extract draft option fields."""

    async def from_url(self, url: str) -> Dict[str, Any]:
        current = assert_safe_public_url(url)
        timeout = httpx.Timeout(_timeout_s(), connect=min(5.0, _timeout_s()))
        headers = {
            "User-Agent": _user_agent(),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
            # Allow gzip — some CDNs (Amazon) 4xx/5xx when forced to identity.
            "Accept-Encoding": "gzip, deflate",
            "Cache-Control": "no-cache",
            "Upgrade-Insecure-Requests": "1",
        }

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            headers=headers,
            max_redirects=0,
        ) as client:
            for _ in range(_MAX_REDIRECTS + 1):
                body = b""
                try:
                    async with client.stream("GET", current) as resp:
                        # Manual redirect handling with SSRF re-check
                        if resp.status_code in {301, 302, 303, 307, 308}:
                            loc = resp.headers.get("location")
                            if not loc:
                                raise ValidationError("redirect without location")
                            nxt = urljoin(current, loc)
                            current = assert_safe_public_url(nxt)
                            continue

                        if resp.status_code >= 400:
                            raise ValidationError(
                                _fetch_blocked_message(current, resp.status_code)
                            )

                        ctype = (resp.headers.get("content-type") or "").lower()
                        if "html" not in ctype and "xml" not in ctype and ctype:
                            if not ctype.startswith("text/"):
                                raise ValidationError("url did not return HTML")

                        buf = bytearray()
                        async for chunk in resp.aiter_bytes():
                            if not chunk:
                                continue
                            buf.extend(chunk)
                            if _read_enough_html(buf):
                                # Drop the connection early — do not download the full page.
                                break
                        body = bytes(buf)
                except ValidationError:
                    raise
                except httpx.TimeoutException as e:
                    raise ValidationError("preview timed out; enter details manually") from e
                except httpx.HTTPError as e:
                    raise ValidationError(_fetch_blocked_message(current)) from e

                if not body:
                    raise ValidationError("empty response; enter details manually")

                text = body.decode("utf-8", errors="replace")
                if _looks_like_bot_wall(text):
                    raise ValidationError(_fetch_blocked_message(current))

                draft = parse_product_html(text, current)
                if not _draft_has_signal(draft):
                    if _is_amazon_host(urlparse(current).hostname):
                        raise ValidationError(_fetch_blocked_message(current))
                    raise ValidationError(
                        "could not extract product details; enter title, image, and price manually"
                    )
                draft["source"] = "http_scrape"
                return draft

        raise ValidationError("too many redirects")


class ChainedPreview:
    """Try primary scrape, then optional AI fallbacks."""

    def __init__(self, primary: Any, *fallbacks: Any) -> None:
        self.primary = primary
        self.fallbacks = [f for f in fallbacks if f is not None]

    async def from_url(self, url: str) -> Dict[str, Any]:
        try:
            return await self.primary.from_url(url)
        except ValidationError as first_err:
            last = first_err
            for fb in self.fallbacks:
                try:
                    return await fb.from_url(url)
                except ValidationError as e:
                    last = e
            raise last


def build_preview_adapter() -> Any:
    if not _preview_enabled():
        return NullPreview()
    primary = HttpScrapePreview()
    fallbacks: List[Any] = []
    # Lazy import avoids hard dependency cycle / unused path when no key.
    try:
        from app.wishlist.adapters.gemini_preview import GeminiPreview, _gemini_enabled

        if _gemini_enabled():
            fallbacks.append(GeminiPreview())
    except Exception:
        pass
    if not fallbacks:
        return primary
    return ChainedPreview(primary, *fallbacks)
