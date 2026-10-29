"""One OpenAI-compatible client for Ollama, LM Studio and similar servers."""

from __future__ import annotations

import json
import re
import time
from typing import Iterator

import httpx

REQUEST_TIMEOUT = 60.0  # whole request
FIRST_TOKEN_TIMEOUT = 20.0  # a cold model can be slow to load
DEFAULT_TEMPERATURE = 0.4


class LLMError(Exception):
    """Raised with a message that is safe to show to the user.

    kind: "unreachable" | "model_missing" | "timeout" | "http" | "bad_response"
    """

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def _headers(api_key: str | None) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + path


def _unreachable(base_url: str) -> LLMError:
    return LLMError("unreachable", f"Can't reach the model server at {base_url}. Is it running?")


def _extract_model_ids(payload: object) -> list[str]:
    """Extract model IDs from OpenAI (`/v1/models`) or Ollama (`/api/tags`) payloads."""
    items: list = []
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            items = payload["data"]
        elif isinstance(payload.get("models"), list):
            items = payload["models"]
    elif isinstance(payload, list):
        items = payload

    ids: list[str] = []
    for item in items:
        if isinstance(item, dict):
            mid = item.get("id") or item.get("name") or item.get("model")
            if isinstance(mid, str) and mid.strip():
                ids.append(mid.strip())
        elif isinstance(item, str) and item.strip():
            ids.append(item.strip())
    return sorted({i for i in ids if "embed" not in i.lower()})


def list_models(base_url: str, api_key: str | None = None, timeout: float = 5.0) -> list[str]:
    """Installed model ids, with embedding models hidden.

    Queries `/models` first (OpenAI-compatible) and falls back to Ollama's native `/api/tags`
    if `/models` is empty or the user configured the root server URL without `/v1`.
    """
    headers = _headers(api_key)
    root_url = re.sub(r"/v1/?$", "", base_url.strip().rstrip("/"))
    candidates = [_url(base_url, "/models")]
    if root_url:
        v1_models = f"{root_url}/v1/models"
        if v1_models not in candidates:
            candidates.append(v1_models)
        api_tags = f"{root_url}/api/tags"
        if api_tags not in candidates:
            candidates.append(api_tags)

    last_error: LLMError | None = None
    responded = False

    for idx, url in enumerate(candidates):
        try:
            resp = httpx.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()
            responded = True
        except (httpx.ConnectError, httpx.ConnectTimeout):
            if idx == 0:
                raise _unreachable(base_url) from None
            continue
        except httpx.TimeoutException:
            if idx == 0:
                raise LLMError("timeout", f"The server at {base_url} did not answer in time.") from None
            continue
        except httpx.HTTPStatusError as exc:
            last_error = LLMError("http", f"The server returned HTTP {exc.response.status_code}.")
            continue
        except (ValueError, AttributeError):
            last_error = LLMError("bad_response", "The server answered, but not with a valid model list.")
            continue

        models = _extract_model_ids(payload)
        if models:
            return models

    if responded:
        return []
    if last_error is not None:
        raise last_error
    raise _unreachable(base_url)


def _raise_for_status(resp: httpx.Response, model: str) -> None:
    if resp.status_code < 400:
        return
    detail = resp.read().decode("utf-8", "replace")[:300]
    if resp.status_code == 404 or "not found" in detail.lower():
        raise LLMError("model_missing", f"Model '{model}' was not found on the server. Pick another one in Settings.")
    raise LLMError("http", f"The server returned HTTP {resp.status_code}: {detail}")


def stream_chat(
    base_url: str,
    model: str,
    messages: list[dict],
    api_key: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    request_timeout: float = REQUEST_TIMEOUT,
    first_token_timeout: float = FIRST_TOKEN_TIMEOUT,
    no_think: bool = True,
) -> Iterator[str]:
    """Yield text chunks as they arrive.

    no_think asks reasoning models (qwen3 etc.) to skip thinking, which would otherwise
    delay the first token past the timeout. Servers that reject the field get one retry without it.
    """
    body = {"model": model, "messages": messages, "temperature": temperature, "stream": True}
    if no_think:
        body["reasoning_effort"] = "none"
    started = time.monotonic()
    got_token = False
    # The read timeout applies between chunks; it is also the longest we wait for the first token.
    timeout = httpx.Timeout(10.0, read=first_token_timeout)
    url = _url(base_url, "/chat/completions")
    try:
        for attempt in (1, 2):
            with httpx.stream("POST", url, headers=_headers(api_key), json=body, timeout=timeout) as resp:
                if attempt == 1 and "reasoning_effort" in body and resp.status_code in (400, 422):
                    del body["reasoning_effort"]
                    continue
                _raise_for_status(resp, model)
                for line in resp.iter_lines():
                    if time.monotonic() - started > request_timeout:
                        raise LLMError("timeout", f"The model took longer than {int(request_timeout)}s.")
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        return
                    try:
                        delta = json.loads(payload)["choices"][0].get("delta", {})
                    except (ValueError, KeyError, IndexError):
                        continue
                    text = delta.get("content")
                    if text:
                        got_token = True
                        yield text
                return
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise _unreachable(base_url) from None
    except httpx.ReadTimeout:
        what = "to start answering" if not got_token else "to continue"
        raise LLMError("timeout", f"The model took too long {what}. It may still be loading; try again.") from None
    except httpx.HTTPError as exc:
        raise LLMError("http", f"Connection problem: {exc}") from None


def chat(base_url: str, model: str, messages: list[dict], **kwargs) -> str:
    return "".join(stream_chat(base_url, model, messages, **kwargs))


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_think(text: str) -> str:
    """Remove <think>…</think> blocks (and an unclosed trailing one)."""
    text = _THINK.sub("", text)
    text = re.sub(r"<think>.*\Z", "", text, flags=re.DOTALL | re.IGNORECASE)
    return text.replace("</think>", "").strip()


def test_connection(base_url: str, model: str, api_key: str | None = None) -> tuple[str, float]:
    """Send a short rewrite. Returns (result text, seconds). Raises LLMError."""
    started = time.monotonic()
    messages = [
        {"role": "system", "content": "Rewrite the user's text as one polite sentence. Output only the sentence."},
        {"role": "user", "content": "send me the file asap"},
    ]
    text = strip_think(chat(base_url, model, messages, api_key=api_key))
    return text, time.monotonic() - started