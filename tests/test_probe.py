import json

import pytest

from cvd import cli, config
from cvd.client import ChatClient, ScriptedClient
from cvd.config import Profile, cost_usd
from cvd.probe import probe


def response(content=None, calls=None, completion=10, reasoning=5, usage=True):
    message = {"content": content}
    if calls is not None:
        message["tool_calls"] = calls
    result = {
        "choices": [{"message": message, "finish_reason": "tool_calls" if calls else "stop"}],
        "model": "local-model",
        "provider": "local-provider",
    }
    if usage:
        result["usage"] = {
            "prompt_tokens": 20, "completion_tokens": completion,
            "prompt_tokens_details": {"cached_tokens": 0}, "cost": 0.0,
        }
        if reasoning is not None:
            result["usage"]["completion_tokens_details"] = {"reasoning_tokens": reasoning}
    return result


def add_call(arguments=None, name="add"):
    return {
        "id": "call_add", "type": "function",
        "function": {"name": name, "arguments": arguments if arguments is not None else {"a": 17, "b": 25}},
    }


def route_handler(*, failure=None, high=20, low=10, rejected=None, reasoning=True, usage=True):
    def handler(request):
        body = request["body"]
        if body.get("tools"):
            if body["messages"][-1]["role"] == "tool":
                return 200, {}, response("unknown" if failure == "no_final_answer" else "The result is 42.", usage=usage)
            if failure == "no_tool_call":
                return 200, {}, response("42", usage=usage)
            arguments = {"a": "17", "b": "24" if failure == "bad_arguments" else "25"}
            return 200, {}, response(calls=[add_call(arguments)], usage=usage)
        effort = body["reasoning_effort"]
        if effort == rejected:
            return 400, {}, {"error": "Unsupported reasoning effort"}
        tokens = high if effort == "high" else low
        return 200, {}, response(
            "25", completion=tokens if not reasoning else 12,
            reasoning=tokens if reasoning else None, usage=usage,
        )
    return handler


def setup_probe(mock_api, fake_key, **handler_options):
    mock_api(handler=route_handler(**handler_options))
    profile = Profile(
        "test-route", base_url=mock_api.base_url, model="local-model", key_env="CVD_TEST_KEY",
        price_in_per_m=0.40, price_out_per_m=1.20, timeout_s=3,
    )
    return ChatClient(profile, fake_key, max_retries=0), profile


def test_passing_round_trip_and_usage(mock_api, fake_key):
    client, profile = setup_probe(mock_api, fake_key)
    result = probe(client, profile)
    assert result["tool_round_trip"] == "pass"
    assert result["effort"]["verdict"] == "works"
    assert result["calls"] == 6
    assert result["profile"] == profile.name and result["model"] == profile.model
    assert result["providers_seen"] == ["local-provider"]
    assert result["usage_fields"] == [
        "prompt_tokens", "completion_tokens", "reasoning_tokens", "cached_tokens", "cost_reported",
    ]
    assert result["prompt_tokens"] == 120
    assert result["completion_tokens"] == 68
    assert result["cost_usd"] == pytest.approx(cost_usd(profile, 120, 68))
    assert result["tokens_per_s_median"] > 0
    assert not result["aborted_max_usd"]
    first = mock_api.requests[0]["body"]
    assert first["messages"] == [{
        "role": "user", "content": "Use the add tool to add 17 and 25, then tell me the result.",
    }]
    assert first["reasoning_effort"] == "low"
    assert first["tools"][0]["function"]["name"] == "add"
    second = mock_api.requests[1]["body"]["messages"]
    assert second[-1] == {"role": "tool", "tool_call_id": "call_add", "content": "42"}
    assert second[-2]["role"] == "assistant"
    assert json.loads(second[-2]["tool_calls"][0]["function"]["arguments"]) == {"a": "17", "b": "25"}
    for request in mock_api.requests[2:]:
        assert "tools" not in request["body"]
        assert request["body"]["messages"][0]["content"] == (
            "How many prime numbers are there between 1 and 100? Answer with the number only."
        )
    for samples in result["effort"]["samples"].values():
        assert len(samples) == 2
        assert all(sample["accepted"] and sample["correct"] for sample in samples)


@pytest.mark.parametrize("failure", ["no_tool_call", "bad_arguments", "no_final_answer"])
def test_tool_failure_labels(mock_api, fake_key, failure):
    client, profile = setup_probe(mock_api, fake_key, failure=failure)
    result = probe(client, profile, samples=1)
    assert result["tool_round_trip"] == failure
    assert result["calls"] == (4 if failure == "no_final_answer" else 3)


@pytest.mark.parametrize("arguments", [
    '{"a": 17, "b": 25}', {"a": 17, "b": 25}, {"a": "17.0", "b": "25"},
])
def test_tool_argument_forms_pass(arguments):
    client = ScriptedClient([
        {"tool_calls": [{"name": "add", "arguments": arguments}]},
        {"content": "42"}, {"content": "25"}, {"content": "25"},
    ])
    result = probe(client, Profile("script", kind="scripted"), samples=1)
    assert result["tool_round_trip"] == "pass"


@pytest.mark.parametrize("arguments", ["{invalid", "[]", {"a": True, "b": 25}, {"a": 17}])
def test_bad_tool_arguments(arguments):
    client = ScriptedClient([
        {"tool_calls": [{"name": "add", "arguments": arguments}]},
        {"content": "25"}, {"content": "25"},
    ])
    result = probe(client, Profile("script", kind="scripted"), samples=1)
    assert result["tool_round_trip"] == "bad_arguments"


@pytest.mark.parametrize("high, low, expected", [
    (20, 10, "works"), (10, 10, "no_effect"), (13, 10, "unclear"),
    (5, 10, "unclear"), (15, 10, "works"), (8, 10, "no_effect"),
    (25, 20, "no_effect"), (0, 0, "no_effect"), (1, 0, "works"),
])
def test_effort_verdicts(mock_api, fake_key, high, low, expected):
    client, profile = setup_probe(mock_api, fake_key, high=high, low=low)
    assert probe(client, profile, samples=1)["effort"]["verdict"] == expected


@pytest.mark.parametrize("high_completion, expected", [(30, "works"), (10, "no_effect")])
def test_zero_reasoning_tokens_fall_back_to_completion(mock_api, fake_key, high_completion, expected):
    # Reported as 0 at every effort: the route hides reasoning inside completion_tokens.
    def handler(request):
        body = request["body"]
        if body.get("tools"):
            return 200, {}, response("42")
        completion = high_completion if body["reasoning_effort"] == "high" else 10
        return 200, {}, response("25", completion=completion, reasoning=0)
    mock_api(handler=handler)
    profile = Profile("zero", base_url=mock_api.base_url, model="m", key_env="CVD_TEST_KEY", timeout_s=3)
    result = probe(ChatClient(profile, fake_key, max_retries=0), profile, samples=1)
    assert result["effort"]["verdict"] == expected


def test_effort_falls_back_to_completion_tokens(mock_api, fake_key):
    client, profile = setup_probe(mock_api, fake_key, high=20, low=10, reasoning=False)
    result = probe(client, profile, samples=2)
    assert result["effort"]["verdict"] == "works"
    assert result["effort"]["samples"]["low"][0]["reasoning_tokens"] is None


@pytest.mark.parametrize("rejected", ["low", "high"])
def test_effort_rejected(mock_api, fake_key, rejected):
    client, profile = setup_probe(mock_api, fake_key, rejected=rejected)
    result = probe(client, profile, samples=2)
    assert result["effort"]["verdict"] == "rejected:" + rejected
    assert result["calls"] == 6
    assert all(not sample["accepted"] for sample in result["effort"]["samples"][rejected])


@pytest.mark.parametrize("budget, expected_calls", [(0, 0), (0.000001, 1), (0.00004, 2)])
def test_max_usd_stops_before_next_call(mock_api, fake_key, budget, expected_calls):
    client, profile = setup_probe(mock_api, fake_key)
    result = probe(client, profile, max_usd=budget)
    assert result["aborted_max_usd"]
    assert result["effort"]["verdict"] == "aborted_max_usd"
    assert result["calls"] == len(mock_api.requests) == expected_calls
    assert result["cost_usd"] == pytest.approx(expected_calls * 0.00002)


def test_missing_usage_is_not_reported(mock_api, fake_key):
    client, profile = setup_probe(mock_api, fake_key, usage=False)
    result = probe(client, profile, samples=1)
    assert result["usage_fields"] == []
    assert result["prompt_tokens"] == result["completion_tokens"] == 0
    assert result["cost_usd"] == 0


def write_models(tmp_path, base_url):
    path = tmp_path / "models.toml"
    path.write_text(
        '[profiles.local]\nbase_url = "' + base_url + '"\n'
        'model = "local-model"\nkey_env = "CVD_TEST_KEY"\n',
        encoding="ascii", newline="\n",
    )
    return path


def test_cli_missing_key_exit_2(tmp_path, mock_api, monkeypatch, capsys):
    path = write_models(tmp_path, mock_api.base_url)
    monkeypatch.delenv("CVD_TEST_KEY", raising=False)
    monkeypatch.setattr(config, "_registry_key", lambda name: None)
    assert cli.main(["probe", "--profile", "local", "--models", str(path)]) == 2
    assert "CVD_TEST_KEY" in capsys.readouterr().err
    assert mock_api.requests == []


def test_cli_writes_requested_out_path(tmp_path, mock_api, fake_key, monkeypatch, capsys):
    mock_api(handler=route_handler())
    models = write_models(tmp_path, mock_api.base_url)
    output = tmp_path / "results" / "requested.json"
    monkeypatch.setenv("CVD_TEST_KEY", fake_key)
    code = cli.main([
        "probe", "--profile", "local", "--models", str(models),
        "--samples", "1", "--efforts", "low,high", "--max-usd", "0.01",
        "--out", str(output),
    ])
    assert code == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["profile"] == "local"
    assert result["tool_round_trip"] == "pass"
    assert result["effort"]["verdict"] == "works"
    captured = capsys.readouterr()
    assert str(output) in captured.out
    assert fake_key not in captured.out + captured.err + output.read_text()
    assert b"\r" not in output.read_bytes()


@pytest.mark.parametrize("status, code", [(401, 3), (403, 3), (402, 4), (400, 5)])
def test_cli_api_error_exit_codes(tmp_path, mock_api, fake_key, monkeypatch, capsys, status, code):
    models = write_models(tmp_path, mock_api.base_url)
    mock_api.enqueue(status, body={"error": fake_key})
    monkeypatch.setenv("CVD_TEST_KEY", fake_key)
    output = tmp_path / "not-written.json"
    assert cli.main([
        "probe", "--profile", "local", "--models", str(models), "--out", str(output),
    ]) == code
    captured = capsys.readouterr()
    assert fake_key not in captured.out + captured.err
    assert not output.exists()
    assert len(mock_api.requests) == 1


def test_cli_scripted_default_output(tmp_path, monkeypatch, capsys):
    script = tmp_path / "steps.json"
    script.write_text(json.dumps([
        {"tool_calls": [{"name": "add", "arguments": {"a": 17, "b": 25}}]},
        {"content": "42"}, {"content": "25"}, {"content": "25"},
    ]), encoding="ascii", newline="\n")
    models = tmp_path / "models.toml"
    models.write_text(
        '[profiles.local]\nkind = "scripted"\nscript = "steps.json"\n',
        encoding="ascii", newline="\n",
    )
    monkeypatch.chdir(tmp_path)
    assert cli.main(["probe", "--profile", "local", "--samples", "1"]) == 0
    files = list((tmp_path / "runs").glob("probe-local-*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text())["tool_round_trip"] == "pass"


def test_cli_help(capsys):
    with pytest.raises(SystemExit) as caught:
        cli.main(["probe", "--help"])
    assert caught.value.code == 0
    assert "usage: cvd probe" in capsys.readouterr().out
