#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request
from typing import Any


DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5"
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}


def api_key_from_env() -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return api_key


def base_url_from_env() -> str:
    return os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def model_from_env(default: str = DEFAULT_MODEL) -> str:
    return os.environ.get("OPENAI_MODEL", default).strip() or default


def max_retries_from_env(default: int = 4) -> int:
    raw = os.environ.get("OPENAI_MAX_RETRIES", str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(0, value)


def retry_backoff_seconds_from_env(default: float = 1.5) -> float:
    raw = os.environ.get("OPENAI_RETRY_BACKOFF_SECONDS", str(default)).strip()
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(0.1, value)


def _retry_after_seconds(exc: urllib.error.HTTPError) -> float | None:
    retry_after = exc.headers.get("Retry-After")
    if retry_after is None:
        return None
    try:
        return max(0.0, float(retry_after))
    except ValueError:
        return None


def _sleep_for_retry(*, base_backoff: float, attempt: int, retry_after: float | None = None) -> None:
    if retry_after is not None:
        sleep_seconds = retry_after
    else:
        sleep_seconds = (base_backoff * (2 ** attempt)) + random.uniform(0.0, 0.35)
    time.sleep(sleep_seconds)


def create_response(
    *,
    model: str,
    instructions: str,
    input_text: str,
    text_format: dict[str, Any] | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    max_output_tokens: int | None = None,
    store: bool = False,
    max_retries: int | None = None,
    retry_backoff_seconds: float | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "input": input_text,
        "store": store,
    }
    if text_format is not None:
        payload["text"] = {"format": text_format}
    if max_output_tokens is not None:
        payload["max_output_tokens"] = max_output_tokens

    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url=f"{base_url or base_url_from_env()}/responses",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key or api_key_from_env()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    retries = max_retries if max_retries is not None else max_retries_from_env()
    backoff = (
        retry_backoff_seconds
        if retry_backoff_seconds is not None
        else retry_backoff_seconds_from_env()
    )
    raw = ""
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request) as response:
                raw = response.read().decode("utf-8")
            break
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            should_retry = exc.code in RETRYABLE_HTTP_CODES and attempt < retries
            if not should_retry:
                raise RuntimeError(
                    f"OpenAI API request failed with HTTP {exc.code}: {error_body}"
                ) from exc
            _sleep_for_retry(
                base_backoff=backoff,
                attempt=attempt,
                retry_after=_retry_after_seconds(exc),
            )
        except urllib.error.URLError as exc:
            if attempt >= retries:
                raise RuntimeError(f"OpenAI API request failed: {exc}") from exc
            _sleep_for_retry(base_backoff=backoff, attempt=attempt)

    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError("OpenAI API returned a non-object JSON response")
    error = parsed.get("error")
    if isinstance(error, dict):
        raise RuntimeError(f"OpenAI API returned an error: {json.dumps(error)}")
    return parsed


def extract_output_text(response: dict[str, Any]) -> str:
    output = response.get("output")
    if not isinstance(output, list):
        raise RuntimeError("OpenAI response missing output array")
    texts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            if content_item.get("type") != "output_text":
                continue
            text = content_item.get("text")
            if isinstance(text, str):
                texts.append(text)
    if not texts:
        raise RuntimeError("OpenAI response did not contain any output_text content")
    return "".join(texts)


def incomplete_details(response: dict[str, Any]) -> dict[str, Any] | None:
    details = response.get("incomplete_details")
    if isinstance(details, dict):
        return details
    return None


def incomplete_reason(response: dict[str, Any]) -> str:
    details = incomplete_details(response)
    if not details:
        return ""
    reason = details.get("reason")
    if isinstance(reason, str):
        return reason
    return ""
