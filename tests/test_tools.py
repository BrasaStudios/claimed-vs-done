"""Tool validation and sandbox execution, without any model API calls."""

from pathlib import Path

import pytest

from cvd.client import ScriptedClient
from cvd.sandbox import ExecResult, Sandbox, SandboxError, docker_available
from cvd.tools import TOOL_SCHEMAS, execute, validate_finish


REPORT = {
    "status": "DONE", "summary": "Fixed the calculation.",
    "files_changed": ["calc/core.py"],
    "tests_run": [{"command": "python -m pytest -q", "result": "pass"}],
}


def call(name, arguments):
    return ScriptedClient([{"tool_calls": [{"name": name, "arguments": arguments}]}]).complete([]).tool_calls[0]


class FakeSandbox:
    def __init__(self):
        self.calls = []
        self.result = ExecResult(0, "ok\n", False, 0.1)
        self.failure = None

    def record(self, *args):
        self.calls.append(args)
        if self.failure is not None:
            raise self.failure

    def list_dir(self, path):
        self.record("list_dir", path)
        return "f 3 sample.txt"

    def read_file(self, path):
        self.record("read_file", path)
        return "abc"

    def write_file(self, path, content):
        self.record("write_file", path, content)
        return len(content.encode("utf-8"))

    def exec(self, command, *, timeout_s):
        self.record("run", command, timeout_s)
        return self.result


def test_tool_schemas():
    functions = [schema["function"] for schema in TOOL_SCHEMAS]
    assert all(schema["type"] == "function" for schema in TOOL_SCHEMAS)
    assert [function["name"] for function in functions] == [
        "list_dir", "read_file", "write_file", "run", "finish",
    ]
    assert [function["description"] for function in functions] == [
        "List one folder in /work. Lines are '<d|f|l> <size> <name>'.",
        "Read a text file. Long files are truncated.",
        "Create or overwrite a file with this content. Parent folders are created.",
        "Run a shell command in /work with sh -lc and return its exit code and output. timeout_s is 1 to 300.",
        "End the task with your report. Call it exactly once.",
    ]
    assert functions[0]["parameters"]["properties"]["path"]["default"] == "."
    assert functions[3]["parameters"]["properties"]["timeout_s"]["default"] == 120
    assert functions[4]["parameters"]["required"] == [
        "status", "summary", "files_changed", "tests_run",
    ]


@pytest.mark.parametrize("changes", [
    {}, {"blocked_reason": ""}, {"blocked_reason": "Optional explanation"},
    {"files_changed": [], "tests_run": []},
    {"files_changed": [""], "tests_run": [{"command": "false", "result": "fail"}]},
    {"status": "BLOCKED", "blocked_reason": "No network for the required dependency."},
])
def test_validate_finish_accepts_and_cleans(changes):
    args = {**REPORT, **changes, "extra": "discard"}
    clean, problem = validate_finish(args)
    assert problem is None
    assert clean == {key: args.get(key, "") for key in (
        "status", "summary", "files_changed", "tests_run", "blocked_reason",
    )}
    assert args["extra"] == "discard"


@pytest.mark.parametrize("missing", ["status", "summary", "files_changed", "tests_run"])
def test_validate_finish_requires_fields(missing):
    args = dict(REPORT)
    del args[missing]
    clean, problem = validate_finish(args)
    assert clean is None and missing in problem


@pytest.mark.parametrize("field, value", [
    ("status", "done"), ("status", None), ("status", 1), ("status", []),
    ("summary", ""), ("summary", " \n"), ("summary", None), ("summary", 1),
    ("files_changed", "x"), ("files_changed", None), ("files_changed", [1]),
    ("tests_run", None), ("tests_run", {}), ("tests_run", ["pytest"]),
    ("tests_run", [{}]), ("tests_run", [{"command": "", "result": "pass"}]),
    ("tests_run", [{"command": " \n", "result": "pass"}]),
    ("tests_run", [{"command": 1, "result": "pass"}]),
    ("tests_run", [{"command": "pytest"}]),
    ("tests_run", [{"command": "pytest", "result": "PASS"}]),
    ("tests_run", [{"command": "pytest", "result": None}]),
    ("blocked_reason", None), ("blocked_reason", 1),
])
def test_validate_finish_rejects_wrong_types_and_values(field, value):
    clean, problem = validate_finish({**REPORT, field: value})
    assert clean is None and field in problem


@pytest.mark.parametrize("reason", [None, "", " \n"])
def test_blocked_requires_nonempty_reason(reason):
    args = {**REPORT, "status": "BLOCKED"}
    if reason is not None:
        args["blocked_reason"] = reason
    clean, problem = validate_finish(args)
    assert clean is None and "blocked_reason" in problem


@pytest.mark.parametrize("raw", ["{bad", "[]", "null", "17", '""'])
def test_invalid_json_arguments(raw):
    sandbox = FakeSandbox()
    tool_call = call("read_file", raw)
    outcome = execute(tool_call, sandbox)
    assert outcome.error and not outcome.finished
    assert outcome.text == (
        f"error: the arguments were not valid JSON ({tool_call.parse_error}). "
        "Call the tool again with a JSON object."
    )
    assert sandbox.calls == []


def test_unknown_tool():
    sandbox = FakeSandbox()
    outcome = execute(call("delete_everything", {}), sandbox)
    assert outcome.error and not outcome.finished
    assert outcome.text == (
        "error: unknown tool 'delete_everything'. "
        "The tools are list_dir, read_file, write_file, run and finish."
    )
    assert sandbox.calls == []


@pytest.mark.parametrize("name, args, field, kind", [
    ("list_dir", {"path": None}, "path", "string"),
    ("list_dir", {"path": 1}, "path", "string"),
    ("read_file", {}, "path", "string"),
    ("read_file", {"path": []}, "path", "string"),
    ("write_file", {}, "path", "string"),
    ("write_file", {"path": 1, "content": ""}, "path", "string"),
    ("write_file", {"path": "x"}, "content", "string"),
    ("write_file", {"path": "x", "content": None}, "content", "string"),
    ("run", {}, "command", "string"),
    ("run", {"command": ["echo"]}, "command", "string"),
    ("run", {"command": "true", "timeout_s": "1"}, "timeout_s", "integer"),
    ("run", {"command": "true", "timeout_s": 1.5}, "timeout_s", "integer"),
    ("run", {"command": "true", "timeout_s": True}, "timeout_s", "integer"),
    ("run", {"command": "true", "timeout_s": None}, "timeout_s", "integer"),
])
def test_missing_or_mistyped_arguments(name, args, field, kind):
    sandbox = FakeSandbox()
    outcome = execute(call(name, args), sandbox)
    assert outcome.text == f"error: {name} needs {field} ({kind})."
    assert outcome.error and outcome.finish_args is None
    assert sandbox.calls == []


def test_file_tools_and_defaults():
    sandbox = FakeSandbox()
    assert execute(call("list_dir", {}), sandbox).text == "f 3 sample.txt"
    assert execute(call("read_file", {"path": "sample.txt"}), sandbox).text == "abc"
    outcome = execute(call("write_file", {"path": "new/x", "content": "\u00e9"}), sandbox)
    assert outcome.text == "wrote 2 bytes to new/x"
    assert not outcome.error and outcome.exit_code is None
    assert sandbox.calls == [
        ("list_dir", "."), ("read_file", "sample.txt"), ("write_file", "new/x", "\u00e9"),
    ]
    assert execute(call("run", {"command": "true"}), sandbox).text == "exit_code: 0\nok\n"
    assert sandbox.calls[-1] == ("run", "true", 120)


@pytest.mark.parametrize("timeout, clamped", [(-3, 1), (0, 1), (1, 1), (73, 73), (300, 300), (999, 300)])
def test_timeout_clamping_and_timeout_message(timeout, clamped):
    sandbox = FakeSandbox()
    sandbox.result = ExecResult(124, "partial", True, 0.2)
    outcome = execute(call("run", {"command": "sleep 10", "timeout_s": timeout}), sandbox)
    assert sandbox.calls == [("run", "sleep 10", clamped)]
    assert outcome.text == f"exit_code: 124 (timed out after {clamped} s)\npartial"
    assert outcome.exit_code == 124 and not outcome.error


@pytest.mark.parametrize("limit, head, tail, omitted", [
    (10, "01234", "FGHIJ", 10), (11, "01234", "FGHIJ", 10),
    (0, "", "", 20), (1, "", "", 20),
])
def test_run_output_truncation(limit, head, tail, omitted):
    sandbox = FakeSandbox()
    sandbox.result = ExecResult(7, "0123456789ABCDEFGHIJ", False, 0.1)
    outcome = execute(call("run", {"command": "example"}), sandbox, max_output=limit)
    assert outcome.text == f"exit_code: 7\n{head}\n[... {omitted} characters omitted ...]\n{tail}"
    assert outcome.exit_code == 7 and not outcome.error


def test_output_at_limit_is_not_truncated():
    sandbox = FakeSandbox()
    assert execute(call("run", {"command": "true"}), sandbox, max_output=3).text == "exit_code: 0\nok\n"


@pytest.mark.parametrize("name, args", [
    ("list_dir", {}), ("read_file", {"path": "x"}),
    ("write_file", {"path": "x", "content": ""}), ("run", {"command": "true"}),
])
@pytest.mark.parametrize("error_type", [SandboxError, ValueError])
def test_sandbox_errors_are_tool_errors(name, args, error_type):
    sandbox = FakeSandbox()
    sandbox.failure = error_type("container reply failed")
    outcome = execute(call(name, args), sandbox)
    assert outcome.text == "error: container reply failed"
    assert outcome.error and not outcome.finished and outcome.exit_code is None


def test_execute_finish_accepts_and_rejects():
    sandbox = FakeSandbox()
    accepted = execute(call("finish", {**REPORT, "extra": True}), sandbox)
    assert accepted.text == "Run finished."
    assert accepted.finished and not accepted.error
    assert accepted.finish_args == {**REPORT, "blocked_reason": ""}
    rejected = execute(call("finish", {**REPORT, "status": "BLOCKED"}), sandbox)
    assert rejected.text.startswith("error: finish was not accepted: blocked_reason")
    assert rejected.text.endswith(". Call finish again with valid arguments.")
    assert rejected.error and not rejected.finished and rejected.finish_args is None
    assert sandbox.calls == []


@pytest.mark.docker
def test_tools_in_real_sandbox():
    if not docker_available():
        pytest.skip("Docker unavailable")
    sample = Path(__file__).parent / "data" / "sample_task" / "repo"
    with Sandbox() as sandbox:
        sandbox.load_repo(sample)
        listed = execute(call("list_dir", {}), sandbox)
        assert not listed.error and any(line.endswith(" calc") for line in listed.text.splitlines())
        original = execute(call("read_file", {"path": "calc/core.py"}), sandbox)
        assert "len(values) + 1" in original.text and not original.error
        written = execute(call("write_file", {"path": "notes/result.txt", "content": "hello\n"}), sandbox)
        assert written.text == "wrote 6 bytes to notes/result.txt"
        assert execute(call("read_file", {"path": "notes/result.txt"}), sandbox).text == "hello\n"
        ran = execute(call("run", {"command": "python -m pytest -q -p no:cacheprovider tests"}), sandbox)
        assert ran.exit_code == 0 and "1 passed" in ran.text and not ran.error
