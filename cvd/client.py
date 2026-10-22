"""OpenAI-compatible HTTP and deterministic scripted chat clients."""

import http.client
import json
import math
import time
import urllib.error
import urllib.request
import uuid
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .config import Profile


@dataclass
class ToolCall:
    id: str
    name: str
    arguments_raw: str
    arguments: dict | None
    parse_error: str | None


@dataclass
class ChatResponse:
    content: str | None
    reasoning: str | None
    tool_calls: list[ToolCall]
    finish_reason: str | None
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int | None
    cached_tokens: int | None
    cost_reported: float | None
    usage_raw: dict
    provider: str | None
    model: str | None
    latency_s: float
    retries: int


def assistant_message(reply: ChatResponse, reasoning_echo: str | None = None) -> dict:
    message = {"role": "assistant", "content": reply.content or ""}
    if reply.tool_calls:
        message["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments_raw},
            }
            for call in reply.tool_calls
        ]
    if reasoning_echo and reply.reasoning is not None:
        message[reasoning_echo] = reply.reasoning
    return message


class ApiError(Exception):
    def __init__(self, status: int | None, body: str):
        self.status = status
        self.body = body[:2000]
        label = "API error" if status is None else "HTTP " + str(status)
        super().__init__(label + ": " + self.body)


class AuthError(ApiError):
    pass


class QuotaError(ApiError):
    pass


class RetryExhausted(ApiError):
    pass


class ScriptExhausted(Exception):
    pass


def _tool_call(call_id, name, arguments) -> ToolCall:
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False)
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError) as error:
        return ToolCall(call_id, name, raw, None, str(error))
    if not isinstance(parsed, dict):
        return ToolCall(call_id, name, raw, None, "Tool arguments must decode to an object")
    return ToolCall(call_id, name, raw, parsed, None)


def _response(payload, latency_s, retries) -> ChatResponse:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("Response has no choices")
    choice = choices[0]
    message = choice["message"]
    usage = payload.get("usage") or {}
    completion_details = usage.get("completion_tokens_details") or {}
    prompt_details = usage.get("prompt_tokens_details") or {}
    calls = []
    for call in message.get("tool_calls") or []:
        function = call["function"]
        # Some providers omit ids; an empty tool_call_id breaks the next request.
        call_id = call.get("id") or "call_" + uuid.uuid4().hex[:12]
        calls.append(_tool_call(call_id, function["name"], function.get("arguments")))
    reasoning = message.get("reasoning_content")
    if reasoning is None:
        reasoning = message.get("reasoning")
    return ChatResponse(
        content=message.get("content"),
        reasoning=reasoning,
        tool_calls=calls,
        finish_reason=choice.get("finish_reason"),
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        reasoning_tokens=completion_details.get("reasoning_tokens"),
        cached_tokens=prompt_details.get("cached_tokens"),
        cost_reported=usage.get("cost"),
        usage_raw=deepcopy(usage),
        provider=payload.get("provider"),
        model=payload.get("model"),
        latency_s=latency_s,
        retries=retries,
    )


class ChatClient:
    def __init__(self, profile, key, *, sleep=time.sleep, max_retries=5):
        if max_retries < 0:
            raise ValueError("max_retries must be nonnegative")
        if not profile.base_url.startswith(("https://", "http://")):
            raise ValueError("base_url must start with https:// or http://")
        self.profile = profile
        self._key = key
        self._sleep = sleep
        self._max_retries = max_retries

    def _redact(self, text):
        if self._key:
            text = text.replace(self._key, "[REDACTED]")
            escaped = json.dumps(self._key, ensure_ascii=False)[1:-1]
            text = text.replace(escaped, "[REDACTED]")
        return text

    @staticmethod
    def _delay(retry_after, attempt):
        if retry_after is not None:
            try:
                seconds = float(retry_after)
                if math.isfinite(seconds):
                    return min(60.0, max(0.0, seconds))
            except (TypeError, ValueError):
                pass
        return min(2 ** (attempt + 1), 32)

    def complete(self, messages, tools=None, *, tool_choice="auto",
                 reasoning_effort=None, max_tokens=None) -> ChatResponse:
        body = {"model": self.profile.model, "messages": messages}
        if tools is not None:
            body.update(tools=tools, tool_choice=tool_choice)
        effort = reasoning_effort if reasoning_effort is not None else self.profile.reasoning_effort
        if effort is not None:
            body["reasoning_effort"] = effort
        limit = max_tokens if max_tokens is not None else self.profile.max_tokens
        if limit is not None:
            body["max_tokens"] = limit
        if self.profile.temperature is not None:
            body["temperature"] = self.profile.temperature
        body.update(self.profile.extra_body)
        request = urllib.request.Request(
            self.profile.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self._key,
                "Content-Type": "application/json",
                "User-Agent": "claimed-vs-done/" + __version__,
            },
            method="POST",
        )
        for attempt in range(self._max_retries + 1):
            # Per attempt, so retry back-off never inflates a call's latency.
            started = time.perf_counter()
            retry_after = None
            status = None
            try:
                # nosec B310: __init__ allows only http and https base URLs.
                with urllib.request.urlopen(request, timeout=self.profile.timeout_s) as response:  # nosec B310
                    status = response.status
                    raw = response.read().decode("utf-8", errors="replace")
                try:
                    payload = json.loads(raw)
                    return _response(payload, time.perf_counter() - started, attempt)
                except (ValueError, TypeError, KeyError, IndexError, AttributeError):
                    error_body = "Invalid chat response: " + raw
            except urllib.error.HTTPError as error:
                status = error.code
                error_body = error.read().decode("utf-8", errors="replace")
                retry_after = error.headers.get("Retry-After")
                error.close()
                if status not in (429, 500, 502, 503, 504, 529):
                    error_type = AuthError if status in (401, 403) else QuotaError if status == 402 else ApiError
                    raise error_type(status, self._redact(error_body)) from None
            except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
                error_body = str(error)
            if attempt == self._max_retries:
                raise RetryExhausted(status, self._redact(error_body)) from None
            self._sleep(self._delay(retry_after, attempt))


class ScriptedClient:
    def __init__(self, steps: list[dict], profile: Profile | None = None):
        self.profile = profile
        self._steps = deepcopy(steps)
        self._index = 0
        self._call_number = 0
        self.received: list[list[dict]] = []

    @classmethod
    def from_file(cls, path, profile=None) -> "ScriptedClient":
        with Path(path).open(encoding="utf-8") as stream:
            steps = json.load(stream)
        if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
            raise ValueError("A script must be a list of step objects")
        return cls(steps, profile)

    def complete(self, messages, tools=None, *, tool_choice="auto",
                 reasoning_effort=None, max_tokens=None) -> ChatResponse:
        self.received.append(deepcopy(messages))
        if self._index >= len(self._steps):
            raise ScriptExhausted("No scripted responses remain")
        step = self._steps[self._index]
        self._index += 1
        calls = []
        for call in step.get("tool_calls") or []:
            self._call_number += 1
            calls.append({
                "id": "call_" + str(self._call_number),
                "type": "function",
                "function": {"name": call["name"], "arguments": call.get("arguments")},
            })
        message = {
            "content": step.get("content"),
            "tool_calls": calls,
            "reasoning_content": step.get("reasoning_content"),
            "reasoning": step.get("reasoning"),
        }
        payload = {
            "choices": [{
                "message": message,
                "finish_reason": step.get("finish_reason", "tool_calls" if calls else "stop"),
            }],
            "usage": step.get("usage", {}),
            "provider": step.get("provider"),
            "model": step.get("model", self.profile.model if self.profile else None),
        }
        return _response(payload, 0.0, 0)
