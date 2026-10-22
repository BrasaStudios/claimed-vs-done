"""Run batches against Docker and the loopback-only mock API."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cvd import cli
from cvd.sandbox import Sandbox, docker_available
from cvd.transcript import read_transcript

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "tests/data/sample_task"
SCRIPT = ROOT / "tests/data/sample_script.json"
pytestmark = [pytest.mark.docker, pytest.mark.skipif(not docker_available(), reason="Docker unavailable")]


def containers():
    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=cvd-", "--format", "{{.Names}}"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=True,
    )
    return set(result.stdout.decode("ascii").splitlines())


@pytest.fixture(autouse=True)
def cleanup_containers():
    before = containers()
    try:
        yield
    finally:
        leaked = containers() - before
        if leaked:
            subprocess.run(
                ["docker", "rm", "-f", *sorted(leaked)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=True,
            )
        assert not leaked, f"Run command leaked containers: {sorted(leaked)}"


def arguments(out, *extra):
    return [
        "run", "--profile", "scripted-sample", "--tasks", str(SAMPLE),
        "--models", str(ROOT / "models.toml"), "--runs", "1", "--out", str(out),
        *extra,
    ]


def run_cli(out, *extra):
    return subprocess.run(
        [sys.executable, "-m", "cvd", *arguments(out, *extra)],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="replace", timeout=120,
    )


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True) + "\n", encoding="ascii", newline="\n")


def scripted_models(tmp_path, steps=None, **fields):
    script = tmp_path / "script.json"
    write_json(script, read_json(SCRIPT) if steps is None else steps)
    models = tmp_path / "models.toml"
    lines = [
        "[profiles.scripted-sample]", 'kind = "scripted"', 'script = "script.json"',
        *(f"{name} = {json.dumps(value)}" for name, value in fields.items()),
    ]
    models.write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")
    return models


def test_run_artifacts_and_resume(tmp_path):
    out = tmp_path / "batch"
    result = run_cli(out)
    assert result.returncode == 0, result.stdout
    assert "sample_task-r1 finish DONE hidden PASS" in result.stdout
    directory = out / "sample_task-r1"
    expected = {"transcript.jsonl", "result.json", "final.tar", "hidden.json"}
    assert {path.name for path in directory.iterdir()} == expected
    saved = read_json(directory / "result.json")
    assert saved["stop_reason"] == "finish"
    assert saved["finish"]["status"] == "DONE"
    assert saved["hidden_passed"] is True
    assert saved["finish"]["tests_run"] == [
        {"command": "python -m pytest -q tests", "result": "pass"},
    ]
    assert saved["before"]["files"]["calc/core.py"]["sha256"] != saved["after"]["files"]["calc/core.py"]["sha256"]
    assert saved["before"]["commits"] == saved["after"]["commits"] == 1
    hidden = read_json(directory / "hidden.json")
    assert set(hidden) == {"exit_code", "passed", "timed_out", "duration_s", "output"}
    assert hidden["passed"] is True and hidden["exit_code"] == 0
    assert hidden["timed_out"] is False
    assert "2 passed" in hidden["output"]
    records = read_transcript(directory / "transcript.jsonl")
    assert records[0]["type"] == "header" and records[-1]["type"] == "end"
    assert [record["name"] for record in records if record["type"] == "tool_call"] == [
        "read_file", "write_file", "run", "finish",
    ]
    visible = next(record for record in records if record.get("name") == "run")
    assert visible["exit_code"] == 0 and "1 passed" in visible["result"]
    assert records[0]["budget"] == {
        "max_turns": 40, "max_tokens": 2000000, "wall_s": 600,
        "max_nudges": 3, "max_bad_finish": 2,
    }
    before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in directory.iterdir()}
    resumed = run_cli(out)
    assert resumed.returncode == 0, resumed.stdout
    assert "sample_task-r1 skipped" in resumed.stdout
    assert before == {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in directory.iterdir()}


def test_interrupted_transcript_is_kept(tmp_path):
    out = tmp_path / "batch"
    stale = out / "sample_task-r1" / "transcript.jsonl"
    stale.parent.mkdir(parents=True)
    stale.write_text('{"type": "header", "seq": 0}\n', encoding="ascii", newline="\n")
    result = run_cli(out)
    assert result.returncode == 0, result.stdout
    kept = list(stale.parent.glob("transcript.interrupted-*.jsonl"))
    assert len(kept) == 1 and '"header"' in kept[0].read_text(encoding="ascii")
    assert read_transcript(stale)[-1]["type"] == "end"


def test_script_restarts_for_each_run(tmp_path):
    result = run_cli(tmp_path, "--runs", "2")
    assert result.returncode == 0, result.stdout
    for number in (1, 2):
        saved = read_json(tmp_path / f"sample_task-r{number}/result.json")
        assert saved["stop_reason"] == "finish" and saved["hidden_passed"] is True


def test_zero_usd_stops_before_start(tmp_path, monkeypatch):
    def unexpected_start(self):
        pytest.fail("A zero-dollar budget must not start a container")
    monkeypatch.setattr(Sandbox, "start", unexpected_start)
    assert cli.main(arguments(tmp_path, "--max-usd", "0")) == 6
    assert not list(tmp_path.glob("sample_task-r*"))


def test_resume_cost_includes_completed_runs(tmp_path, monkeypatch):
    write_json(tmp_path / "sample_task-r1/result.json", {"cost_usd": 1.25})
    write_json(tmp_path / "another-task-r1/result.json", {"cost_usd": 0.75})
    def unexpected_start(self):
        pytest.fail("The completed runs already exhausted the dollar budget")
    monkeypatch.setattr(Sandbox, "start", unexpected_start)
    assert cli.main(arguments(tmp_path, "--runs", "2", "--max-usd", "2")) == 6
    assert not (tmp_path / "sample_task-r2").exists()


def test_new_run_cost_stops_batch(tmp_path):
    models = scripted_models(tmp_path, price_in_per_m=1000000, price_out_per_m=1000000)
    out = tmp_path / "batch"
    result = run_cli(out, "--models", str(models), "--runs", "2", "--max-usd", "560")
    assert result.returncode == 6, result.stdout
    assert read_json(out / "sample_task-r1/result.json")["cost_usd"] == 560
    assert not (out / "sample_task-r2").exists()


@pytest.mark.parametrize("flags, stop, expected", [
    (["--max-turns", "1", "--max-tokens", "999", "--wall-s", "17"],
     "max_turns", {"max_turns": 1, "max_tokens": 999, "wall_s": 17}),
    (["--max-tokens", "1"], "max_tokens", {"max_turns": 40, "max_tokens": 1, "wall_s": 600}),
])
def test_cli_budgets_reach_loop(tmp_path, flags, stop, expected):
    result = run_cli(tmp_path, *flags)
    assert result.returncode == 0, result.stdout
    directory = tmp_path / "sample_task-r1"
    saved = read_json(directory / "result.json")
    assert saved["stop_reason"] == stop and saved["turns"] == 1
    header = read_transcript(directory / "transcript.jsonl")[0]
    assert {name: header["budget"][name] for name in expected} == expected
    assert saved["hidden_passed"] is False


def test_wall_budget_stops_script(tmp_path):
    steps = [
        {"tool_calls": [{"name": "run", "arguments": {"command": "sleep 2"}}]},
        read_json(SCRIPT)[-1],
    ]
    models = scripted_models(tmp_path, steps)
    out = tmp_path / "batch"
    result = run_cli(out, "--models", str(models), "--wall-s", "1")
    assert result.returncode == 0, result.stdout
    saved = read_json(out / "sample_task-r1/result.json")
    assert saved["stop_reason"] == "wall_clock"
    assert saved["turns"] <= 1


@pytest.mark.parametrize("override", [False, True])
def test_task_budget_and_effort_precedence(tmp_path, override):
    task = tmp_path / "sample_task"
    shutil.copytree(SAMPLE, task)
    with (task / "task.toml").open("a", encoding="ascii", newline="\n") as stream:
        stream.write("\n[budget]\nmax_turns = 1\nwall_s = 20\n")
    models = scripted_models(tmp_path, reasoning_effort="low")
    out = tmp_path / "batch"
    extra = ["--max-turns", "2", "--wall-s", "30", "--effort", "high"] if override else []
    result = run_cli(out, "--tasks", str(task), "--models", str(models), *extra)
    assert result.returncode == 0, result.stdout
    header = read_transcript(out / "sample_task-r1/transcript.jsonl")[0]
    assert header["budget"]["max_turns"] == (2 if override else 1)
    assert header["budget"]["wall_s"] == (30 if override else 20)
    assert header["effort"] == ("high" if override else "low")
    assert str(header["budget"]["max_turns"]) in header["system_prompt"]


@pytest.mark.parametrize("status, code", [(401, 3), (403, 3), (402, 4)])
def test_fatal_api_writes_artifacts_and_stops(tmp_path, mock_api, fake_key, monkeypatch, status, code):
    monkeypatch.setenv("CVD_RUN_TEST_KEY", fake_key)
    mock_api.enqueue(status, body={"error": "Rejected " + fake_key})
    models = tmp_path / "models.toml"
    models.write_text(
        '[profiles.mock]\nbase_url = "' + mock_api.base_url + '"\n'
        'model = "local-mock"\nkey_env = "CVD_RUN_TEST_KEY"\n',
        encoding="ascii", newline="\n",
    )
    out = tmp_path / "batch"
    result = run_cli(out, "--profile", "mock", "--models", str(models), "--runs", "2")
    assert result.returncode == code, result.stdout
    directory = out / "sample_task-r1"
    saved = read_json(directory / "result.json")
    assert saved["stop_reason"] == "api_error" and saved["fatal"] is True
    assert saved["finish"] is None and saved["hidden_passed"] is False
    assert "[REDACTED]" in saved["api_error"]
    for name in ("result.json", "transcript.jsonl", "hidden.json"):
        assert fake_key not in (directory / name).read_text(encoding="utf-8")
    assert (directory / "final.tar").is_file()
    assert read_json(directory / "hidden.json")["passed"] is False
    assert not (out / "sample_task-r2").exists()
    assert len(mock_api.requests) == 1
    assert mock_api.requests[0]["headers"]["Authorization"] == "Bearer " + fake_key
    assert fake_key not in result.stdout


def test_retry_incomplete_run_replaces_transcript(tmp_path):
    directory = tmp_path / "sample_task-r1"
    directory.mkdir()
    (directory / "transcript.jsonl").write_text("interrupted\n", encoding="ascii", newline="\n")
    result = run_cli(tmp_path)
    assert result.returncode == 0, result.stdout
    records = read_transcript(directory / "transcript.jsonl")
    assert sum(record["type"] == "header" for record in records) == 1
    assert records[0]["seq"] == 0


def test_default_batch_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = arguments(tmp_path, "--max-turns", "1", "--effort", "high")
    at = args.index("--out")
    del args[at:at + 2]
    assert cli.main(args) == 0
    batches = list((tmp_path / "runs").iterdir())
    assert len(batches) == 1 and batches[0].name.endswith("-scripted-sample-high")
    assert (batches[0] / "sample_task-r1/result.json").is_file()
