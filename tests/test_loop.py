"""Scripted agent runs in real, context-managed Docker sandboxes."""

import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pytest

from cvd import __version__
from cvd.client import ApiError, AuthError, QuotaError, ScriptedClient
from cvd.config import Profile, cost_usd
from cvd.loop import Budget, build_system_prompt, run_agent
from cvd.sandbox import IMAGE, Sandbox, docker_available
from cvd.task import load_task
from cvd.tools import TOOL_SCHEMAS
from cvd.transcript import Transcript, read_transcript


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "tests" / "data" / "sample_task"
TEST_COMMAND = "python -m pytest -q -p no:cacheprovider tests"
REPORT = {
    "status": "DONE", "summary": "Fixed mean and ran the visible tests.",
    "files_changed": ["calc/core.py"],
    "tests_run": [{"command": TEST_COMMAND, "result": "pass"}],
}
NUDGE = (
    "No tool was called. Continue the task using the tools, "
    "and call finish when you are done or blocked."
)


def step(name, arguments, **fields):
    return {"tool_calls": [{"name": name, "arguments": arguments}], **fields}


@pytest.fixture
def sandbox():
    if not docker_available():
        pytest.skip("Docker unavailable")
    with Sandbox() as instance:
        instance.load_repo(SAMPLE / "repo")
        yield instance


@pytest.fixture
def drive(sandbox, tmp_path):
    def run(steps=(), *, budget=None, profile=None, client=None, secrets=()):
        budget = budget if budget is not None else Budget()
        profile = profile if profile is not None else Profile(
            "scripted-test", kind="scripted", model="test-model",
            price_in_per_m=0.4, price_out_per_m=1.2,
        )
        client = client if client is not None else ScriptedClient(list(steps), profile)
        task = load_task(SAMPLE)
        prompt = build_system_prompt((ROOT / "prompts" / "system.md").read_text(encoding="ascii"), budget)
        path = tmp_path / "transcript.jsonl"
        with Transcript(path, secrets=secrets) as transcript:
            result = run_agent(
                task, client, sandbox, profile=profile, budget=budget, effort="high",
                transcript=transcript, system_prompt=prompt, run_id="sample-r1",
            )
        return result, client, read_transcript(path)
    return run


@pytest.mark.parametrize("wall_s, minutes", [(0, 0), (1, 1), (60, 1), (61, 2), (601, 11)])
def test_build_system_prompt(wall_s, minutes):
    template = (ROOT / "prompts" / "system.md").read_text(encoding="ascii")
    prompt = build_system_prompt(template, Budget(max_turns=17, wall_s=wall_s))
    assert "{max_turns}" not in prompt and "{wall_minutes}" not in prompt
    assert f"17 model turns and about {minutes} minutes" in prompt
    assert build_system_prompt('{"literal": 1} {max_turns} {wall_minutes}', Budget()) == (
        '{"literal": 1} 40 10'
    )


@pytest.mark.docker
class TestAgentLoop:
    def test_fix_visible_tests_and_finish(self, drive, sandbox):
        fixed = (SAMPLE / "solution" / "calc" / "core.py").read_text(encoding="ascii")
        steps = [
            step("read_file", {"path": "calc/core.py"}, usage={"prompt_tokens": 10, "completion_tokens": 3}),
            step("write_file", {"path": "calc/core.py", "content": fixed}),
            step("run", {"command": TEST_COMMAND}),
            step("finish", REPORT),
        ]
        result, client, records = drive(steps)
        assert result.stop_reason == "finish" and result.finish == {**REPORT, "blocked_reason": ""}
        assert result.turns == 4 and len(client.received) == 4
        assert result.prompt_tokens == 10 and result.completion_tokens == 3
        assert result.reasoning_tokens == 0 and result.cost_reported is None
        assert result.cost_usd == pytest.approx(cost_usd(client.profile, 10, 3))
        assert result.nudges == result.tool_errors == 0 and not result.fatal and result.api_error is None
        assert result.before.files["calc/core.py"].sha256 == hashlib.sha256(
            (SAMPLE / "repo" / "calc" / "core.py").read_bytes()
        ).hexdigest()
        assert result.after.files["calc/core.py"].sha256 == hashlib.sha256(fixed.encode("ascii")).hexdigest()
        assert result.before.files["calc/core.py"] != result.after.files["calc/core.py"]
        assert result.before.commits == result.after.commits == 1
        assert result.outside_writes == [] and result.wall_s > 0
        assert sandbox.read_file("calc/core.py") == fixed
        assert client.received[0][0]["role"] == "system"
        assert client.received[0][1] == {"role": "user", "content": load_task(SAMPLE).spec}
        run_record = next(record for record in records if record.get("name") == "run")
        assert run_record["exit_code"] == 0 and "1 passed" in run_record["result"]
        assert client.received[3][-1]["content"] == run_record["result"]
        assert records[-1]["finish"] == result.finish

    def test_max_turns(self, drive):
        result, client, records = drive(
            [step("list_dir", {}), step("finish", REPORT)], budget=Budget(max_turns=1),
        )
        assert result.stop_reason == "max_turns" and result.turns == len(client.received) == 1
        assert result.finish is None and records[-1]["stop_reason"] == "max_turns"

    def test_three_no_tool_calls(self, drive):
        result, client, records = drive([{"content": "working"}] * 3)
        assert result.stop_reason == "no_tool_calls" and result.turns == result.nudges == 3
        assert [record["text"] for record in records if record["type"] == "nudge"] == [NUDGE] * 3
        assert client.received[1][-1] == {"role": "user", "content": NUDGE}

    def test_nudge_count_resets_after_tools(self, drive):
        result, _, _ = drive([
            {"content": "thinking"}, {"content": "thinking"},
            step("list_dir", {}), {"content": "thinking"}, {"content": "thinking"},
            step("finish", REPORT),
        ])
        assert result.stop_reason == "finish" and result.nudges == 4 and result.turns == 6

    def test_invalid_json_returns_error_and_continues(self, drive):
        result, client, records = drive([
            step("read_file", "{invalid"), step("list_dir", {}), step("finish", REPORT),
        ])
        assert result.stop_reason == "finish" and result.tool_errors == 1 and result.turns == 3
        message = client.received[1][-1]
        assert message["role"] == "tool" and message["tool_call_id"] == "call_1"
        assert message["content"].startswith("error: the arguments were not valid JSON (")
        tool_record = next(record for record in records if record["type"] == "tool_call")
        assert tool_record["arguments_raw"] == "{invalid"
        assert tool_record["result"] == message["content"]

    def test_three_rejected_finishes(self, drive):
        result, client, records = drive([
            step("finish", {**REPORT, "status": "BLOCKED"}),
            step("finish", {**REPORT, "summary": ""}),
            step("finish", {**REPORT, "tests_run": "not a list"}),
            step("finish", REPORT),
        ])
        assert result.stop_reason == "bad_finish" and result.finish is None
        assert result.turns == len(client.received) == result.tool_errors == 3
        assert len([record for record in records if record["type"] == "tool_call"]) == 3

    def test_rejected_finish_can_be_corrected(self, drive):
        result, _, _ = drive([
            step("finish", {}), step("finish", {}), step("finish", REPORT),
        ])
        assert result.stop_reason == "finish" and result.tool_errors == 2

    @pytest.mark.parametrize("budget, expected", [
        (Budget(wall_s=0), "wall_clock"),
        (Budget(max_tokens=0), "max_tokens"),
        (Budget(max_turns=0), "max_turns"),
    ])
    def test_zero_budgets_stop_before_call(self, drive, budget, expected):
        result, client, records = drive([step("finish", REPORT)], budget=budget)
        assert result.stop_reason == expected and result.turns == 0
        assert client.received == [] and result.before == result.after
        assert [record["type"] for record in records] == ["header", "end"]

    def test_token_budget_includes_prompt_and_completion(self, drive):
        result, client, _ = drive([
            step("list_dir", {}, usage={"prompt_tokens": 7, "completion_tokens": 3}),
            step("finish", REPORT),
        ], budget=Budget(max_tokens=10))
        assert result.stop_reason == "max_tokens" and result.turns == len(client.received) == 1
        assert result.prompt_tokens == 7 and result.completion_tokens == 3

    @pytest.mark.parametrize("error_type, status, fatal", [
        (AuthError, 401, True), (QuotaError, 402, True), (ApiError, 400, False),
    ])
    def test_client_errors(self, drive, fake_key, tmp_path, error_type, status, fatal):
        class FailingClient:
            def complete(self, messages, tools=None, **kwargs):
                raise error_type(status, "rejected " + fake_key)

        result, _, records = drive(client=FailingClient(), secrets=(fake_key,))
        assert result.stop_reason == "api_error" and result.fatal is fatal and result.turns == 1
        assert fake_key not in result.api_error and "[REDACTED]" in result.api_error
        assert result.before == result.after and result.finish is None
        assert fake_key not in (tmp_path / "transcript.jsonl").read_text(encoding="utf-8")
        assert records[-1]["totals"]["api_error"] == result.api_error

    def test_script_exhausted_is_nonfatal(self, drive):
        result, client, records = drive()
        assert result.stop_reason == "api_error" and not result.fatal
        assert result.turns == len(client.received) == 1
        assert "No scripted responses remain" in result.api_error
        assert records[-1]["stop_reason"] == "api_error"

    @pytest.mark.parametrize("echo", ["reasoning_content", None])
    def test_reasoning_echo_in_next_request(self, drive, echo):
        profile = Profile("script", kind="scripted", reasoning_echo=echo)
        result, client, records = drive([
            step("list_dir", {}, reasoning_content="First inspect the project."),
            step("finish", REPORT),
        ], profile=profile)
        assert result.stop_reason == "finish"
        assistant = client.received[1][2]
        assert assistant["role"] == "assistant" and assistant["content"] == ""
        if echo:
            assert assistant[echo] == "First inspect the project."
        else:
            assert "reasoning_content" not in assistant and "reasoning" not in assistant
        assert records[1]["reasoning"] == "First inspect the project."

    def test_transcript_records_usage_and_redaction(self, drive, fake_key, tmp_path):
        steps = [
            {"content": fake_key, "reasoning": "Think " + fake_key, "usage": {
                "prompt_tokens": 11, "completion_tokens": 5,
                "completion_tokens_details": {"reasoning_tokens": 4},
                "prompt_tokens_details": {"cached_tokens": 2}, "cost": 0.01,
            }, "provider": "local", "finish_reason": "stop"},
            step("run", {"command": "printf '%s' " + fake_key}, usage={
                "prompt_tokens": 13, "completion_tokens": 7,
                "completion_tokens_details": {"reasoning_tokens": 6}, "cost": 0.02,
            }),
            step("finish", {**REPORT, "summary": fake_key}, usage={"cost": 0.0}),
        ]
        result, client, records = drive(steps, secrets=(fake_key,))
        assert result.stop_reason == "finish" and result.nudges == 1
        assert (result.prompt_tokens, result.completion_tokens, result.reasoning_tokens) == (24, 12, 10)
        assert result.cost_reported == pytest.approx(0.03)
        assert result.cost_usd == pytest.approx(cost_usd(client.profile, 24, 12))
        assert [record["type"] for record in records] == [
            "header", "model_call", "nudge", "model_call", "tool_call",
            "model_call", "tool_call", "end",
        ]
        header = records[0]
        assert header["run_id"] == result.run_id == "sample-r1"
        assert header["task_id"] == result.task_id == "sample_task"
        assert header["profile"] == result.profile == "scripted-test"
        assert header["model"] == "test-model" and header["effort"] == result.effort == "high"
        assert header["budget"] == asdict(Budget())
        assert header["harness_version"] == __version__ and header["image"] == IMAGE
        assert header["task_prompt"] == load_task(SAMPLE).spec
        assert header["system_prompt"] == client.received[0][0]["content"]
        assert datetime.fromisoformat(header["started_at"]).tzinfo is not None
        model = records[1]
        assert model["turn"] == 1 and model["cached_tokens"] == 2 and model["provider"] == "local"
        assert model["finish_reason"] == "stop" and model["latency_s"] == model["retries"] == 0
        assert model["reasoning"] == "Think [REDACTED]"
        tool_record = records[4]
        assert tool_record["turn"] == 2 and tool_record["call_id"] == "call_1"
        assert tool_record["name"] == "run" and tool_record["exit_code"] == 0
        assert tool_record["duration_s"] >= 0
        assert json.loads(tool_record["arguments_raw"])["command"].endswith("[REDACTED]")
        assert tool_record["result"] == "exit_code: 0\n[REDACTED]"
        assert [record["seq"] for record in records] == list(range(len(records)))
        raw = (tmp_path / "transcript.jsonl").read_text(encoding="utf-8")
        assert fake_key not in raw and "[REDACTED]" in raw
        for key in ("turns", "prompt_tokens", "completion_tokens", "reasoning_tokens",
                    "cost_usd", "cost_reported", "wall_s", "nudges", "tool_errors", "fatal"):
            assert records[-1]["totals"][key] == getattr(result, key)

    def test_tools_execute_in_order_and_finish_stops_immediately(self, drive, sandbox):
        result, _, records = drive([{"tool_calls": [
            {"name": "write_file", "arguments": {"path": "order.txt", "content": "first"}},
            {"name": "read_file", "arguments": {"path": "order.txt"}},
            {"name": "finish", "arguments": REPORT},
            {"name": "write_file", "arguments": {"path": "order.txt", "content": "too late"}},
        ]}])
        assert result.stop_reason == "finish" and result.turns == 1
        calls = [record for record in records if record["type"] == "tool_call"]
        assert [record["name"] for record in calls] == ["write_file", "read_file", "finish"]
        assert calls[1]["result"] == sandbox.read_file("order.txt") == "first"

    def test_outside_writes_are_recorded(self, drive):
        result, _, _ = drive([
            step("write_file", {"path": "/home/agent/loop-note", "content": "outside"}),
            step("finish", {**REPORT, "status": "BLOCKED", "blocked_reason": "Task is impossible."}),
        ])
        assert result.stop_reason == "finish" and result.finish["status"] == "BLOCKED"
        assert "A /home/agent/loop-note" in result.outside_writes

    def test_complete_receives_tools_and_effort(self, drive):
        class CheckingClient(ScriptedClient):
            def complete(self, messages, tools=None, *, tool_choice="auto",
                         reasoning_effort=None, max_tokens=None):
                assert tools == TOOL_SCHEMAS and tool_choice == "auto"
                assert reasoning_effort == "high" and max_tokens is None
                return super().complete(messages, tools, reasoning_effort=reasoning_effort)

        result, _, _ = drive(client=CheckingClient([step("finish", REPORT)]))
        assert result.stop_reason == "finish"
