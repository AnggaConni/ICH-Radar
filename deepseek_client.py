"""Minimal DeepSeek API client for ICH Radar.

This module is intentionally standalone for the first migration step. Existing
Gemini calls are not changed yet; integration happens in later steps.
"""

import json
import logging
import os
import random
import re
import time

import requests

log = logging.getLogger("ICH_Radar")

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class DeepSeekAPIError(RuntimeError):
    """Raised when DeepSeek API calls fail after retries."""


def _extract_json(text):
    """Parse JSON directly, or recover the first complete object/array."""
    text = (text or "").strip()
    if not text:
        raise ValueError("DeepSeek returned an empty response.")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[index:])
            return parsed
        except json.JSONDecodeError:
            continue

    raise ValueError("No valid JSON object or array found in DeepSeek response.")


def call_deepseek(
    api_key,
    prompt,
    model=DEFAULT_MODEL,
    system_prompt=None,
    json_mode=True,
    max_tokens=8192,
    timeout=180,
    max_attempts=4,
):
    """Call DeepSeek Chat Completions and return parsed JSON or text.

    JSON mode is enabled by default for compatibility with the existing ICH
    pipeline, which expects dictionaries/lists from its AI calls.
    """
    api_key = (api_key or "").strip()
    if not api_key:
        raise DeepSeekAPIError("DEEPSEEK_API_KEY is missing.")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if json_mode:
        prompt = (
            prompt.rstrip()
            + "\n\nReturn ONLY valid JSON. Do not wrap it in Markdown fences."
        )
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
        "thinking": {"type": "disabled"},
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
    }

    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(
                DEEPSEEK_API_URL,
                json=payload,
                headers=headers,
                timeout=timeout,
            )

            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                usage = data.get("usage", {})
                log.info(
                    "DeepSeek request successful | model=%s | prompt_tokens=%s | completion_tokens=%s",
                    model,
                    usage.get("prompt_tokens", "unknown"),
                    usage.get("completion_tokens", "unknown"),
                )
                if json_mode:
                    try:
                        return _extract_json(content)
                    except (ValueError, json.JSONDecodeError) as exc:
                        log.error("DeepSeek JSON parsing failed: %s | preview=%s", exc, content[:500])
                        return None
                return content.strip()

            if response.status_code in TRANSIENT_STATUS_CODES:
                if attempt < max_attempts:
                    delay = min(30, (2 ** (attempt - 1)) + random.uniform(0.25, 1.25))
                    log.warning(
                        "DeepSeek transient HTTP %s on attempt %s/%s; retrying in %.1fs",
                        response.status_code, attempt, max_attempts, delay,
                    )
                    time.sleep(delay)
                    continue

            try:
                error_detail = response.json().get("error", {}).get("message", response.text)
            except (ValueError, AttributeError):
                error_detail = response.text
            raise DeepSeekAPIError(
                "DeepSeek API HTTP %s: %s" % (response.status_code, str(error_detail)[:1500])
            )

        except requests.RequestException as exc:
            if attempt < max_attempts:
                delay = min(30, (2 ** (attempt - 1)) + random.uniform(0.25, 1.25))
                log.warning("DeepSeek network error on attempt %s/%s: %s; retrying in %.1fs",
                            attempt, max_attempts, exc, delay)
                time.sleep(delay)
                continue
            raise DeepSeekAPIError("DeepSeek network failure after retries: %s" % exc) from exc

    return None
