"""Search real product image candidates (Google CSE or Serper)."""

from __future__ import annotations

import os
from typing import List, Optional
from urllib.parse import urlparse

import httpx

from app.wishlist.adapters.preview import assert_safe_public_url
from app.wishlist.domain.errors import ValidationError

_MAX_CANDIDATES = 10


def _cse_configured() -> bool:
    return bool(
        (os.getenv("GOOGLE_CSE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
        and (os.getenv("GOOGLE_CSE_CX") or "").strip()
    )


def _serper_configured() -> bool:
    return bool((os.getenv("SERPER_API_KEY") or "").strip())


def image_search_enabled() -> bool:
    return _cse_configured() or _serper_configured()


def _safe_image_url(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    try:
        url = assert_safe_public_url(str(raw).strip()[:2000])
    except ValidationError:
        return None
    host = (urlparse(url).hostname or "").lower()
    # Skip obvious non-product assets
    if any(x in host for x in ("facebook.com", "twitter.com", "x.com", "instagram.com")):
        return None
    path = urlparse(url).path.lower()
    if path.endswith((".svg", ".gif")) and "product" not in path:
        # allow but prefer raster; still OK for picker
        pass
    return url


async def search_product_images(query: str, *, limit: int = _MAX_CANDIDATES) -> List[str]:
    """
    Return up to `limit` public https image URLs for a product query.
    Prefers Google Programmable Search (CSE); falls back to Serper.
    """
    q = (query or "").strip()[:200]
    if not q:
        return []
    limit = max(1, min(int(limit), _MAX_CANDIDATES))

    if _cse_configured():
        try:
            return await _search_google_cse(q, limit)
        except Exception:
            pass
    if _serper_configured():
        try:
            return await _search_serper(q, limit)
        except Exception:
            pass
    return []


async def _search_google_cse(query: str, limit: int) -> List[str]:
    api_key = (
        (os.getenv("GOOGLE_CSE_API_KEY") or "").strip()
        or (os.getenv("GEMINI_API_KEY") or "").strip()
    )
    cx = (os.getenv("GOOGLE_CSE_CX") or "").strip()
    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "searchType": "image",
        "num": limit,
        "safe": "active",
    }
    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.get("https://www.googleapis.com/customsearch/v1", params=params)
    if resp.status_code >= 400:
        raise ValidationError(f"image search failed (HTTP {resp.status_code})")
    data = resp.json()
    out: List[str] = []
    seen = set()
    for item in data.get("items") or []:
        link = _safe_image_url(item.get("link"))
        if not link or link in seen:
            continue
        seen.add(link)
        out.append(link)
        if len(out) >= limit:
            break
    return out


async def _search_serper(query: str, limit: int) -> List[str]:
    api_key = (os.getenv("SERPER_API_KEY") or "").strip()
    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.post(
            "https://google.serper.dev/images",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": limit},
        )
    if resp.status_code >= 400:
        raise ValidationError(f"image search failed (HTTP {resp.status_code})")
    data = resp.json()
    out: List[str] = []
    seen = set()
    for item in data.get("images") or []:
        link = _safe_image_url(item.get("imageUrl") or item.get("thumbnailUrl"))
        if not link or link in seen:
            continue
        seen.add(link)
        out.append(link)
        if len(out) >= limit:
            break
    return out
