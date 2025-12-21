from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx


class OpenRouterError(RuntimeError):
    pass


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_s: float = 40.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    async def chat_json(
        self,
        model: str,
        system_prompt: str,
        user_json: Dict[str, Any],
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        import json

        def _json_default(o: Any) -> Any:
            # Make common non-JSON types serializable without leaking internal details.
            if hasattr(o, "isoformat"):
                try:
                    return o.isoformat()
                except Exception:
                    pass
            return str(o)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # Optional OpenRouter headers (safe defaults)
            "X-Title": "TripSync",
        }
        payload = {
            "model": model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                # OpenAI-style chat expects string content; send structured input as JSON text.
                {"role": "user", "content": json.dumps(user_json, ensure_ascii=False, default=_json_default)},
            ],
            # Ask for JSON back; model still might fail, so we validate downstream.
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
        if resp.status_code >= 400:
            raise OpenRouterError(f"OpenRouter error {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except Exception as e:
            raise OpenRouterError("Invalid OpenRouter response shape") from e

        # content is expected to be JSON object (because response_format json_object), but still parse it.
        if isinstance(content, dict):
            return content
        if isinstance(content, str):
            import json

            try:
                return json.loads(content)
            except Exception as e:
                raise OpenRouterError("Model did not return valid JSON") from e
        raise OpenRouterError("Unexpected model content type")


def get_openrouter_client() -> OpenRouterClient:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise OpenRouterError("OPENROUTER_API_KEY is not configured")
    return OpenRouterClient(api_key=api_key)


def get_openrouter_model() -> str:
    return os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()


def get_openrouter_fallback_model() -> Optional[str]:
    m = os.getenv("OPENROUTER_FALLBACK_MODEL", "").strip()
    return m or None


