"""Gemini AI fallback for product URL preview when HTTP scrape is blocked."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from app.wishlist.adapters.image_search import image_search_enabled, search_product_images
from app.wishlist.adapters.preview import assert_safe_public_url
from app.wishlist.domain.errors import ValidationError

_ASIN_RE = re.compile(r"(?:/dp/|/gp/product/|/product/)([A-Z0-9]{10})", re.I)
_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)


def _gemini_enabled() -> bool:
    if not (os.getenv("GEMINI_API_KEY") or "").strip():
        return False
    return os.getenv("WISHLIST_PREVIEW_AI_FALLBACK", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _gemini_model() -> str:
    return (
        os.getenv("WISHLIST_PREVIEW_GEMINI_MODEL", "gemini-2.0-flash").strip()
        or "gemini-2.0-flash"
    )


def _gemini_timeout_s() -> float:
    raw = os.getenv("WISHLIST_PREVIEW_GEMINI_TIMEOUT_S", "20").strip()
    try:
        return max(5.0, min(float(raw), 45.0))
    except ValueError:
        return 20.0


def _extract_asin(url: str) -> Optional[str]:
    m = _ASIN_RE.search(url or "")
    return m.group(1).upper() if m else None


async def _gemini_title_and_query(page_url: str) -> Dict[str, Optional[str]]:
    """
    Ask Gemini only for a product title + image search query.
    Never trust model-invented prices or single image URLs.
    """
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    asin = _extract_asin(page_url)
    host = (urlparse(page_url).hostname or "").lower()

    prompt = {
        "task": (
            "Identify the product at this shopping URL. "
            "Return ONLY JSON with keys: title, search_query. "
            "title = concise product name (max 120 chars) or null if unknown. "
            "search_query = short Google image search query (brand + product + color/size) "
            "to find photos of THIS product, or null. "
            "Do NOT invent a price. Do NOT invent image URLs."
        ),
        "url": page_url,
        "host": host,
        "asin": asin,
    }

    model = _gemini_model()
    endpoint = _GEMINI_URL.format(model=model)
    payload: Dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": json.dumps(prompt, ensure_ascii=False)}],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
        "tools": [{"google_search": {}}],
    }

    async with httpx.AsyncClient(timeout=_gemini_timeout_s()) as client:
        resp = await client.post(
            endpoint,
            params={"key": api_key},
            headers={"Content-Type": "application/json"},
            json=payload,
        )
        if resp.status_code in {400, 404} and "tools" in payload:
            payload.pop("tools", None)
            resp = await client.post(
                endpoint,
                params={"key": api_key},
                headers={"Content-Type": "application/json"},
                json=payload,
            )

    if resp.status_code >= 400:
        raise ValidationError(
            f"AI preview failed (HTTP {resp.status_code}); enter details manually"
        )

    data = resp.json()
    parts = data["candidates"][0]["content"]["parts"]
    text_bits = [p.get("text", "") for p in parts if isinstance(p, dict)]
    content = "\n".join(t for t in text_bits if t).strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("not an object")

    title = parsed.get("title")
    title = str(title).strip()[:150] if title else None
    search_query = parsed.get("search_query")
    search_query = str(search_query).strip()[:200] if search_query else None
    return {"title": title or None, "search_query": search_query or None}


class GeminiPreview:
    """
    AI-assisted preview after scrape fails:
    - title from Gemini (+ Google Search grounding)
    - NEVER auto-fill price (models invent prices)
    - NEVER auto-pick a single image_url
    - up to 10 real image candidates from Google image search (CSE/Serper)
    """

    async def from_url(self, url: str) -> Dict[str, Any]:
        if not (os.getenv("GEMINI_API_KEY") or "").strip():
            raise ValidationError("AI preview is not configured")

        page_url = assert_safe_public_url(url)
        try:
            meta = await _gemini_title_and_query(page_url)
        except ValidationError:
            raise
        except httpx.TimeoutException as e:
            raise ValidationError("AI preview timed out; enter details manually") from e
        except Exception as e:
            raise ValidationError(
                "AI preview returned unusable data; enter details manually"
            ) from e

        title = meta.get("title")
        query = meta.get("search_query") or title
        if not query:
            host = urlparse(page_url).hostname or ""
            query = f"product {host}".strip()

        candidates: List[str] = []
        if image_search_enabled() and query:
            candidates = await search_product_images(query, limit=10)

        draft: Dict[str, Any] = {
            "title": title,
            "url": page_url,
            # Price is scrape-only — AI invents bad numbers.
            "price": None,
            "currency": None,
            "image_url": None,
            "image_candidates": candidates,
            "notes": (
                "Price not auto-filled (AI). Pick an image below or enter details manually."
                if candidates
                else "Could not find image candidates; enter title/price/photo manually."
            ),
            "source": "gemini+images" if candidates else "gemini",
        }
        if not title and not candidates:
            raise ValidationError(
                "AI preview found no title or images; enter details manually"
            )
        return draft
