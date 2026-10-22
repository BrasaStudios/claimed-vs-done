import json
import urllib.error
import urllib.request
from dataclasses import replace

import pytest

from cvd import __version__
from cvd.client import (
    ApiError,
    AuthError,
    ChatClient,
    QuotaError,
    RetryExhausted,
    ScriptedClient,
    ScriptExhausted,
)
from cvd.config import Profile


def payload(content="ok", calls=None, usage=None, **message_fields):
    message = {"content": content, **message_fields}
    if calls is not None:
        message["tool_calls"] = calls
    result = {
        "choices": [{"message": message, "finish_reason": "tool_calls" if calls else "stop"}],
        "provider": "local-provider",
        "model": "response-model",
    }
    if usage is not None:
        result["usage"] = usage
    return result


def client_for(mock_api, fake_key, **kwargs):
    profile = Profile(
        "test", base_url=mock_api.base_url + "/", model="request-model", key_env="CVD_TEST_KEY",
        reasoning_effort="low", max_tokens=50, temperature=0.2, timeout_s=3,
    )
    return ChatClient(profile, fake_key, **kwargs)


def test_request_path_headers_and_overrides(mock_api, fake_key):
    mock_api.enqueue(body=payload())
    client = client_for(mock_api, fake_key)
    tools = [{"type": "function", "function": {"name": "add"}}]
    messages = [{"role": "user", "content": "hello"}]
    reply = client.complete(messages, tools, tool_choice="required", reasoning_effort="high", max_tokens=7)
    request = mock_api.requests[0]
    headers = {name.lower(): value for name, value in request["headers"].items()}
    assert request["path"] == "/v1/chat/completions"
    assert headers["authorization"] == "Bearer " + fake_key
    assert headers["content-type"] == "application/json"
    assert headers["user-agent"] == "claimed-vs-done/" + __version__
    assert request["body"] == {
        "model": "request-model", "messages": messages, "tools": tools,
        "tool_choice": "required", "reasoning_effort": "high", "max_tokens": 7, "temperature": 0.2,
    }
    assert reply.provider == "local-provider"
    assert reply.model == "response-model"
    assert reply.finish_reason == "stop"
    assert reply.retries == 0
    assert reply.latency_s >= 0


def test_profile_defaults_and_no_tools(mock_api, fake_key):
    mock_api.enqueue(body=payload())
    client_for(mock_api, fake_key).complete([])
    body = mock_api.requests[0]["body"]
    assert body["reasoning_effort"] == "low"
    assert body["max_tokens"] == 50
    assert "tools" not in body and "tool_choice" not in body


def test_absent_optional_fields(mock_api, fake_key):
    mock_api.enqueue(body=payload())
    profile = Profile("minimal", base_url=mock_api.base_url, model="model")
    ChatClient(profile, fake_key).complete([])
    assert mock_api.requests[0]["body"] == {"model": "model", "messages": []}


def test_extra_body_merged_last(mock_api, fake_key):
    mock_api.enqueue(body=payload())
    client = client_for(mock_api, fake_key)
    client.profile = replace(client.profile, extra_body={
        "model": "last-model", "reasoning_effort": "last-effort", "max_tokens": 99,
        "temperature": 0, "tool_choice": "none", "custom": {"enabled": True},
    })
    client.complete([], [], reasoning_effort="high", max_tokens=2)
    body = mock_api.requests[0]["body"]
    assert body["model"] == "last-model"
    assert body["reasoning_effort"] == "last-effort"
    assert body["max_tokens"] == 99
    assert body["temperature"] == 0
    assert body["tool_choice"] == "none"
    assert body["custom"] == {"enabled": True}
    assert body["tools"] == []


def test_non_http_base_url_is_refused(fake_key):
    with pytest.raises(ValueError, match="https"):
        ChatClient(Profile("bad", base_url="file:///etc", model="m", key_env="K"), fake_key)


def test_missing_tool_call_ids_get_unique_fallbacks(mock_api, fake_key):
    call = {"type": "function", "function": {"name": "add", "arguments": "{}"}}
    mock_api.enqueue(body=payload(content=None, calls=[dict(call), dict(call, id="")]))
    ids = [c.id for c in client_for(mock_api, fake_key).complete([]).tool_calls]
    assert all(i.startswith("call_") for i in ids) and len(set(ids)) == 2


@pytest.mark.parametrize("arguments, expected", [
    ('{"a": 17, "b": 25}', {"a": 17, "b": 25}),
    ({"a": "17", "b": "25"}, {"a": "17", "b": "25"}),
    ("{invalid", None), ("[]", None), ("null", None), ("17", None),
])
def test_tool_argument_parsing(mock_api, fake_key, arguments, expected):
    mock_api.enqueue(body=payload(content=None, calls=[{
        "id": "call_test", "type": "function", "function": {"name": "add", "arguments": arguments},
    }]))
    reply = client_for(mock_api, fake_key).complete([])
    call = reply.tool_calls[0]
    assert call.id == "call_test" and call.name == "add"
    assert call.arguments == expected
    assert bool(call.parse_error) == (expected is None)
    if isinstance(arguments, str):
        assert call.arguments_raw == arguments
    else:
        assert json.loads(call.arguments_raw) == arguments


@pytest.mark.parametrize("fields, expected", [
    ({"reasoning_content": "preferred", "reasoning": "fallback"}, "preferred"),
    ({"reasoning": "fallback"}, "fallback"),
    ({"reasoning_content": None, "reasoning": "fallback"}, "fallback"),
    ({}, None),
])
def test_reasoning(mock_api, fake_key, fields, expected):
    mock_api.enqueue(body=payload(**fields))
    assert client_for(mock_api, fake_key).complete([]).reasoning == expected


def test_usage_details_and_cost(mock_api, fake_key):
    usage = {
        "prompt_tokens": 100, "completion_tokens": 40,
        "completion_tokens_details": {"reasoning_tokens": 30},
        "prompt_tokens_details": {"cached_tokens": 0}, "cost": 0.001,
        "other_provider_field": 7,
    }
    mock_api.enqueue(body=payload(usage=usage))
    reply = client_for(mock_api, fake_key).complete([])
    assert (reply.prompt_tokens, reply.completion_tokens) == (100, 40)
    assert reply.reasoning_tokens == 30
    assert reply.cached_tokens == 0
    assert reply.cost_reported == 0.001
    assert reply.usage_raw == usage


def test_missing_usage_defaults(mock_api, fake_key):
    mock_api.enqueue(body=payload())
    reply = client_for(mock_api, fake_key).complete([])
    assert (reply.prompt_tokens, reply.completion_tokens) == (0, 0)
    assert reply.reasoning_tokens is reply.cached_tokens is reply.cost_reported is None
    assert reply.usage_raw == {}


@pytest.mark.parametrize("retry_after, expected", [("7", 7), ("120", 60), ("0", 0), ("invalid", 2)])
def test_429_retry_after(mock_api, fake_key, retry_after, expected):
    mock_api.enqueue(429, {"Retry-After": retry_after}, {"error": "slow down"})
    mock_api.enqueue(body=payload())
    waits = []
    reply = client_for(mock_api, fake_key, sleep=waits.append).complete([])
    assert waits == [expected]
    assert reply.retries == 1
    assert len(mock_api.requests) == 2


@pytest.mark.parametrize("status", [500, 502, 503, 504, 529])
def test_transient_status_retries(mock_api, fake_key, status):
    mock_api.enqueue(status, body={"error": "temporary"})
    mock_api.enqueue(body=payload())
    waits = []
    reply = client_for(mock_api, fake_key, sleep=waits.append).complete([])
    assert waits == [2] and reply.retries == 1


def test_repeated_500_exhausts_with_exponential_waits(mock_api, fake_key):
    for _ in range(6):
        mock_api.enqueue(500, body={"error": fake_key})
    waits = []
    with pytest.raises(RetryExhausted) as caught:
        client_for(mock_api, fake_key, sleep=waits.append).complete([])
    assert caught.value.status == 500
    assert waits == [2, 4, 8, 16, 32]
    assert len(mock_api.requests) == 6
    assert fake_key not in str(caught.value) and fake_key not in caught.value.body
    assert "[REDACTED]" in caught.value.body


@pytest.mark.parametrize("body", [b"not JSON", {}, {"choices": []}])
def test_invalid_200_retried(mock_api, fake_key, body):
    mock_api.enqueue(body=body)
    mock_api.enqueue(body=payload())
    waits = []
    assert client_for(mock_api, fake_key, sleep=waits.append).complete([]).retries == 1
    assert waits == [2]


@pytest.mark.parametrize("status, error_type", [
    (401, AuthError), (403, AuthError), (402, QuotaError), (400, ApiError), (404, ApiError),
])
def test_permanent_errors_do_not_retry_and_redact(mock_api, fake_key, status, error_type):
    mock_api.enqueue(status, body={"error": fake_key + "x" * 3000})
    waits = []
    with pytest.raises(error_type) as caught:
        client_for(mock_api, fake_key, sleep=waits.append).complete([])
    assert type(caught.value) is error_type
    assert caught.value.status == status
    assert len(caught.value.body) <= 2000
    assert fake_key not in str(caught.value) and fake_key not in caught.value.body
    assert "[REDACTED]" in caught.value.body
    assert waits == [] and len(mock_api.requests) == 1


def test_transport_timeouts_and_connection_errors_retry(mock_api, fake_key, monkeypatch):
    original = urllib.request.urlopen
    failures = iter([TimeoutError(fake_key), urllib.error.URLError("connection lost"), None])
    mock_api.enqueue(body=payload())

    def sometimes_fails(request, timeout):
        error = next(failures)
        if error is not None:
            raise error
        return original(request, timeout=timeout)

    monkeypatch.setattr(urllib.request, "urlopen", sometimes_fails)
    waits = []
    assert client_for(mock_api, fake_key, sleep=waits.append).complete([]).retries == 2
    assert waits == [2, 4]


def test_transport_error_redaction(mock_api, fake_key, monkeypatch):
    def fail(*args, **kwargs):
        raise ConnectionError(fake_key)

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    with pytest.raises(RetryExhausted) as caught:
        client_for(mock_api, fake_key, max_retries=0).complete([])
    assert caught.value.status is None
    assert fake_key not in str(caught.value) and fake_key not in caught.value.body


def test_script_replay_ids_messages_and_exhaustion(tmp_path):
    steps = [
        {"content": None, "tool_calls": [
            {"name": "add", "arguments": {"a": 17, "b": 25}},
            {"name": "add", "arguments": '{"a": 1, "b": 2}'},
        ], "usage": {"prompt_tokens": 5, "completion_tokens": 3}},
        {"content": "42", "tool_calls": [{"name": "add", "arguments": "invalid"}]},
    ]
    path = tmp_path / "script.json"
    path.write_text(json.dumps(steps), encoding="ascii", newline="\n")
    profile = Profile("scripted", kind="scripted", model="script-model")
    client = ScriptedClient.from_file(path, profile)
    messages = [{"role": "user", "content": "test", "nested": [1]}]
    first = client.complete(messages, [], tool_choice="none", reasoning_effort="high", max_tokens=2)
    messages[0]["nested"].append(2)
    assert client.received[0][0]["nested"] == [1]
    assert [call.id for call in first.tool_calls] == ["call_1", "call_2"]
    assert first.tool_calls[1].arguments == {"a": 1, "b": 2}
    assert (first.prompt_tokens, first.completion_tokens) == (5, 3)
    assert first.model == "script-model"
    second = client.complete([{"role": "tool", "content": "42"}])
    assert second.content == "42"
    assert second.tool_calls[0].id == "call_3"
    assert second.tool_calls[0].arguments is None
    assert second.tool_calls[0].parse_error
    assert second.usage_raw == {}
    with pytest.raises(ScriptExhausted):
        client.complete([])
    assert len(client.received) == 3


def test_script_steps_are_copied():
    steps = [{"content": "original"}]
    client = ScriptedClient(steps)
    steps[0]["content"] = "changed"
    assert client.complete([]).content == "original"


def test_invalid_200_exhaustion_redacts_secret(mock_api, fake_key):
    mock_api.enqueue(body={"error": fake_key})
    with pytest.raises(RetryExhausted) as caught:
        client_for(mock_api, fake_key, max_retries=0).complete([])
    assert caught.value.status == 200
    assert fake_key not in str(caught.value) and fake_key not in caught.value.body
    assert "[REDACTED]" in caught.value.body


@pytest.mark.parametrize("content", [None, "", "answer"])
def test_assistant_message_content_and_no_calls(content):
    from cvd.client import assistant_message

    reply = ScriptedClient([{"content": content}]).complete([])
    assert assistant_message(reply) == {"role": "assistant", "content": content or ""}


def test_assistant_message_preserves_raw_tool_arguments():
    from cvd.client import assistant_message

    raw = ' { "path" : "calc/core.py" } '
    reply = ScriptedClient([{"tool_calls": [
        {"name": "read_file", "arguments": raw},
        {"name": "write_file", "arguments": "{broken"},
    ]}]).complete([])
    message = assistant_message(reply)
    assert message == {
        "role": "assistant", "content": "", "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": raw}},
            {"id": "call_2", "type": "function", "function": {"name": "write_file", "arguments": "{broken"}},
        ],
    }


@pytest.mark.parametrize("echo", [None, "", "reasoning_content", "reasoning"])
@pytest.mark.parametrize("reasoning", [None, "", "Inspect first."])
def test_assistant_message_reasoning_only_when_configured(echo, reasoning):
    from cvd.client import assistant_message

    reply = ScriptedClient([{"reasoning_content": reasoning}]).complete([])
    expected = {"role": "assistant", "content": ""}
    if echo and reasoning is not None:
        expected[echo] = reasoning
    assert assistant_message(reply, echo) == expected


def test_profiles_load_reasoning_echo_for_beam():
    from pathlib import Path
    from cvd.config import load_profiles

    profiles = load_profiles(Path(__file__).resolve().parents[1] / "models.toml")
    assert profiles["beam-hf"].reasoning_echo == "reasoning_content"
    assert profiles["beam-openrouter"].reasoning_echo is None
    assert Profile("default").reasoning_echo is None
