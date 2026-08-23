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

_MAX_BYTES = 1_048_576  # 1 MiB
_DEFAULT_TIMEOUT = 8.0
_MAX_REDIRECTS = 3

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
        "WishlistPreviewBot/1.0 (+https://wishlist.local; product-preview)",
    ).strip()


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
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8",
        }

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            headers=headers,
            max_redirects=0,
        ) as client:
            for _ in range(_MAX_REDIRECTS + 1):
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
                                f"could not fetch url (HTTP {resp.status_code})"
                            )

                        ctype = (resp.headers.get("content-type") or "").lower()
                        if "html" not in ctype and "xml" not in ctype and ctype:
                            # Some stores return text/html without charset; allow empty
                            if not ctype.startswith("text/"):
                                raise ValidationError("url did not return HTML")

                        chunks: List[bytes] = []
                        total = 0
                        async for chunk in resp.aiter_bytes():
                            total += len(chunk)
                            if total > _MAX_BYTES:
                                raise ValidationError("page is too large to preview")
                            chunks.append(chunk)
                        body = b"".join(chunks)
                except httpx.TimeoutException as e:
                    raise ValidationError("preview timed out; enter details manually") from e
                except httpx.HTTPError as e:
                    raise ValidationError("could not fetch url; enter details manually") from e

                # Successful body fetch
                text = body.decode("utf-8", errors="replace")
                draft = parse_product_html(text, current)
                if not any(
                    [draft.get("title"), draft.get("image_url"), draft.get("price") is not None]
                ):
                    raise ValidationError(
                        "could not extract product details; enter title, image, and price manually"
                    )
                draft["source"] = "http_scrape"
                return draft

        raise ValidationError("too many redirects")


def build_preview_adapter() -> NullPreview | HttpScrapePreview:
    if _preview_enabled():
        return HttpScrapePreview()
    return NullPreview()
