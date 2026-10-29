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


def list_models(base_url: str, api_key: str | None = None, timeout: float = 5.0) -> list[str]:
    """Installed model ids, with embedding models hidden."""
    try:
        resp = httpx.get(_url(base_url, "/models"), headers=_headers(api_key), timeout=timeout)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise _unreachable(base_url) from None
    except httpx.TimeoutException:
        raise LLMError("timeout", f"The server at {base_url} did not answer in time.") from None
    except httpx.HTTPStatusError as exc:
        raise LLMError("http", f"The server returned HTTP {exc.response.status_code}.") from None
    except (ValueError, AttributeError):
        raise LLMError("bad_response", "The server answered, but not with an OpenAI-style model list.") from None
    ids = [m["id"] for m in data if isinstance(m, dict) and "id" in m]
    return sorted(i for i in ids if "embed" not in i.lower())


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
                if attempt == 1 and "reasoning_effort" in body and resp.status_code == 400:
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