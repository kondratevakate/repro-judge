"""Minimal client for the Hugging Face router (OpenAI-compatible chat completions)."""
import json
import re
import time

import httpx

ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"
RETRY_STATUS = {429, 500, 502, 503, 504}


class RouterError(RuntimeError):
    pass


def extract_json(content: str) -> dict | None:
    """Parse the outermost JSON object in a reply, tolerating code fences and prose."""
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _post(client: httpx.Client, token: str, body: dict, http_retries: int) -> httpx.Response:
    for attempt in range(http_retries + 1):
        r = client.post(ROUTER_URL, headers={"Authorization": f"Bearer {token}"}, json=body, timeout=900)
        if r.status_code not in RETRY_STATUS or attempt == http_retries:
            return r
        time.sleep(min(60, 5 * 2 ** attempt))
    return r


def judge_call(
    messages: list[dict],
    *,
    token: str,
    model: str,
    provider: str | None,
    temperature: float = 0.1,
    max_tokens: int = 8000,
    attempts: int = 2,
    http_retries: int = 3,
    client: httpx.Client | None = None,
) -> dict:
    """Return parsed JSON plus call metadata. Raise RouterError when no JSON comes back."""
    model_id = f"{model}:{provider}" if provider else model
    own = client is None
    client = client or httpx.Client()
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    try:
        last = ""
        for attempt in range(1, attempts + 1):
            body = {"model": model_id, "messages": messages, "temperature": temperature,
                    "max_tokens": max_tokens * attempt}
            r = _post(client, token, body, http_retries)
            if r.status_code != 200:
                raise RouterError(f"router HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            for k in usage:
                usage[k] += int((data.get("usage") or {}).get(k) or 0)
            choice = data["choices"][0]
            content = (choice.get("message") or {}).get("content") or ""
            parsed = extract_json(content)
            if parsed is not None:
                return {"parsed": parsed, "content": content, "usage": usage, "attempts": attempt,
                        "finish_reason": choice.get("finish_reason"), "model_id": model_id,
                        "served_by": r.headers.get("x-inference-provider")}
            last = f"no JSON (finish_reason={choice.get('finish_reason')})"
        raise RouterError(last)
    finally:
        if own:
            client.close()
