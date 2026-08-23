"""Gemini AI fallback for product URL preview when HTTP scrape is blocked."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

from app.wishlist.adapters.preview import (
    _draft_has_signal,
    _parse_price,
    assert_safe_public_url,
)
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


def _sanitize_draft(raw: Dict[str, Any], page_url: str) -> Dict[str, Any]:
    title = raw.get("title")
    if title is not None:
        title = str(title).strip()[:150] or None

    image_url = raw.get("image_url") or raw.get("image")
    if image_url:
        image_url = str(image_url).strip()[:2000]
        try:
            image_url = assert_safe_public_url(image_url)
        except ValidationError:
            image_url = None
    else:
        image_url = None

    price = _parse_price(raw.get("price"))
    currency = raw.get("currency")
    if currency:
        currency = str(currency).strip().upper()[:8] or None

    notes = raw.get("notes")
    if notes is not None:
        notes = str(notes).strip()[:500] or None

    draft = {
        "title": title,
        "url": page_url,
        "price": price,
        "currency": currency,
        "image_url": image_url,
        "notes": notes,
        "source": "gemini",
    }
    if not _draft_has_signal(draft):
        raise ValidationError(
            "AI preview returned no usable product fields; enter details manually"
        )
    return draft


class GeminiPreview:
    """
    Use Gemini (+ Google Search / URL context when available) to recover product
    metadata after HTTP scrape fails (common for Amazon share links).
    Requires GEMINI_API_KEY. Key stays server-side only.
    """

    async def from_url(self, url: str) -> Dict[str, Any]:
        api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
        if not api_key:
            raise ValidationError("AI preview is not configured")

        page_url = assert_safe_public_url(url)
        asin = _extract_asin(page_url)
        host = (urlparse(page_url).hostname or "").lower()

        prompt = {
            "task": (
                "Extract product listing fields for a wishlist draft from this URL. "
                "Use web/search knowledge if the page blocks scrapers. "
                "Return ONLY JSON with keys: title, price, currency, image_url, notes. "
                "price must be a number or null. currency like INR/USD or null. "
                "image_url must be a direct https image URL or null. "
                "If unsure, use nulls — do not invent a price."
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
            # Let Gemini resolve product pages / short links that block our scraper.
            "tools": [{"google_search": {}}],
        }

        try:
            async with httpx.AsyncClient(timeout=_gemini_timeout_s()) as client:
                resp = await client.post(
                    endpoint,
                    params={"key": api_key},
                    headers={"Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.TimeoutException as e:
            raise ValidationError("AI preview timed out; enter details manually") from e
        except httpx.HTTPError as e:
            raise ValidationError("AI preview failed; enter details manually") from e

        if resp.status_code >= 400:
            # Retry once without tools if the model rejects google_search.
            if resp.status_code in {400, 404} and "tools" in payload:
                payload.pop("tools", None)
                try:
                    async with httpx.AsyncClient(timeout=_gemini_timeout_s()) as client:
                        resp = await client.post(
                            endpoint,
                            params={"key": api_key},
                            headers={"Content-Type": "application/json"},
                            json=payload,
                        )
                except httpx.HTTPError as e:
                    raise ValidationError("AI preview failed; enter details manually") from e
            if resp.status_code >= 400:
                raise ValidationError(
                    f"AI preview failed (HTTP {resp.status_code}); enter details manually"
                )

        try:
            data = resp.json()
            parts = data["candidates"][0]["content"]["parts"]
            text_bits = [p.get("text", "") for p in parts if isinstance(p, dict)]
            content = "\n".join(t for t in text_bits if t).strip()
            if not content:
                raise KeyError("empty")
            # Models sometimes wrap JSON in fences.
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("not an object")
        except Exception as e:
            raise ValidationError(
                "AI preview returned unusable data; enter details manually"
            ) from e

        return _sanitize_draft(parsed, page_url)
