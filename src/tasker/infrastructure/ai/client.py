"""Minimal OpenAI-compatible chat-completions client (BYOK)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from tasker.domain.exceptions import AIClientError


def chat_completion_content(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_message: str,
    user_message: str,
    timeout_seconds: float = 120.0,
) -> str:
    """
    POST to `{base_url}/chat/completions` and return the first message content string.

    Works with OpenAI and many OpenAI-compatible servers without the official SDK.
    """
    root = base_url.rstrip("/")
    url = f"{root}/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        response = httpx.post(
            url,
            headers=headers,
            json=payload,
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        msg = f"AI request failed: {exc}"
        raise AIClientError(msg) from exc

    if response.status_code >= 400:
        body = response.text[:500]
        msg = f"AI API error {response.status_code}: {body}"
        raise AIClientError(msg)

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        msg = "AI API returned non-JSON body."
        raise AIClientError(msg) from exc

    try:
        choices = data["choices"]
        message = choices[0]["message"]
        content = message["content"]
    except (KeyError, IndexError, TypeError) as exc:
        msg = "AI API response missing choices[0].message.content."
        raise AIClientError(msg) from exc

    if not isinstance(content, str) or not content.strip():
        msg = "AI returned empty message content."
        raise AIClientError(msg)

    return content.strip()
