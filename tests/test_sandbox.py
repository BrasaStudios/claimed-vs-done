"""Docker integration tests with context-managed container cleanup."""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from cvd.sandbox import IMAGE, Sandbox, SandboxError, docker_available, overlay, run_hidden_check
from cvd.task import load_task

SAMPLE = Path(__file__).parent / "data" / "sample_task"
pytestmark = [pytest.mark.docker, pytest.mark.skipif(not docker_available(), reason="Docker unavailable")]


@pytest.fixture
def sandbox():
    with Sandbox() as instance:
        instance.load_repo(SAMPLE / "repo")
        yield instance


def docker(*args):
    return subprocess.run(["docker", *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)


def test_network_off_and_container_limits(sandbox):
    info = json.loads(docker("inspect", sandbox.name).stdout)[0]
    assert re.fullmatch(r"cvd-[0-9a-f]{12}", sandbox.name)
    assert info["Config"]["Image"] == IMAGE
    assert info["HostConfig"]["NetworkMode"] == "none"
    assert info["HostConfig"]["Memory"] == 2 * 1024 ** 3
    assert info["HostConfig"]["NanoCpus"] == 2 * 10 ** 9
    assert info["HostConfig"]["PidsLimit"] == 256
    assert info["Mounts"] == []
    assert not info["HostConfig"]["PortBindings"]
    result = sandbox.exec("python3 -c 'import socket; socket.create_connection((\"1.1.1.1\", 53), timeout=2)'")
    assert result.exit_code != 0 and "Error" in result.output and not result.timed_out
    assert sandbox.exec("id -u").output.strip() == "1000"
    assert sandbox.exec("test ! -e /hidden").exit_code == 0
    assert "no-new-privileges" in info["HostConfig"]["SecurityOpt"]


def test_snapshot_survives_links_and_unreadable_files(sandbox):
    sandbox.exec("ln -s /etc/shadow shadow_link && ln -s calc dir_link")
    sandbox.exec("echo secret > locked.txt && chmod 000 locked.txt")
    files = sandbox.snapshot().files
    assert files["shadow_link"].sha256 == "symlink:/etc/shadow"
    assert files["locked.txt"].sha256 == "unreadable:PermissionError"
    assert "dir_link" in files and "calc/core.py" in files


def test_exec_output_status_stdin_and_timeout(sandbox):
    result = sandbox.exec("printf out; printf err >&2; exit 7")
    assert result.exit_code == 7 and result.output in ("outerr", "errout")
    assert not result.timed_out and result.duration_s > 0
    assert sandbox.exec("cat", stdin=b"input\n").output == "input\n"
    assert sandbox.exec("pwd", workdir="/tmp").output.strip() == "/tmp"
    assert sandbox.exec("id -u", user="0").output.strip() == "0"
    result = sandbox.exec("printf started; sleep 10; touch too-late", timeout_s=1)
    assert result.exit_code == 124 and result.timed_out
    assert "started" in result.output and result.duration_s < 10
    assert sandbox.exec("test ! -e too-late").exit_code == 0
    result = sandbox.exec("python3 -c 'import sys; sys.stdout.buffer.write(bytes([255]))'")
    assert result.output == "\ufffd"


def test_file_roundtrip_truncation_and_safe_paths(sandbox):
    path = "nested/quote'\";$(touch injected).txt"
    content = "caf\u00e9 \u03bb \U0001f642\nline two"
    assert sandbox.write_file(path, content) == len(content.encode("utf-8"))
    assert sandbox.read_file(path) == content
    assert sandbox.read_file(path, max_chars=4) == (
        f"{content[:4]}\n[truncated: showing the first 4 of {len(content)} characters]"
    )
    assert sandbox.exec("test ! -e injected").exit_code == 0
    assert sandbox.read_file("/work/" + path) == content
    sandbox.exec("python3 -c 'from pathlib import Path; Path(\"bad-bytes\").write_bytes(bytes([255]))'")
    assert sandbox.read_file("bad-bytes") == "\ufffd"
    for action in (lambda: sandbox.read_file("missing"), lambda: sandbox.read_file("nested"),
                   lambda: sandbox.read_file("/root/.profile"), lambda: sandbox.write_file("/root/nope", "x"),
                   lambda: sandbox.list_dir("missing")):
        with pytest.raises(SandboxError) as caught:
            action()
        assert "\n" not in str(caught.value) and str(caught.value)


def test_list_dir_format_and_limit(sandbox):
    sandbox.exec("mkdir listing; printf abc > listing/b; mkdir listing/a; ln -s b listing/c")
    lines = sandbox.list_dir("listing").splitlines()
    assert [line.split(" ", 2)[2] for line in lines] == ["a", "b", "c"]
    assert re.fullmatch(r"d \d+ a", lines[0])
    assert lines[1] == "f 3 b" and lines[2] == "l 1 c"
    assert sandbox.exec("python3 -c 'from pathlib import Path; p=Path(\"many\"); p.mkdir(); [(p/str(i).zfill(3)).touch() for i in range(503)]'").exit_code == 0
    lines = sandbox.list_dir("many").splitlines()
    assert len(lines) == 501 and lines[-1] == "... 3 more"
    assert lines[0] == "f 0 000" and lines[499] == "f 0 499"


def test_snapshot_hash_commit_count_and_inode(sandbox):
    before = sandbox.snapshot()
    assert before.commits == 1
    assert set(before.files) == {"calc/__init__.py", "calc/core.py", "tests/test_calc.py"}
    core = before.files["calc/core.py"]
    data = (SAMPLE / "repo" / "calc" / "core.py").read_bytes()
    assert core.sha256 == hashlib.sha256(data).hexdigest()
    assert core.size == len(data) and core.inode > 0
    sandbox.write_file("calc/core.py", "changed\n")
    after = sandbox.snapshot()
    assert after.files["calc/core.py"].inode == core.inode
    assert after.files["calc/core.py"].sha256 != core.sha256
    sandbox.write_file("calc/temp.py", "replacement\n")
    assert sandbox.exec("mv calc/temp.py calc/core.py").exit_code == 0
    replaced = sandbox.snapshot()
    assert replaced.files["calc/core.py"].inode != core.inode
    assert sandbox.exec("git add -A && git commit -q -m changed").exit_code == 0
    assert sandbox.snapshot().commits == 2
    for folder in ("__pycache__", ".pytest_cache", ".hypothesis", "nested/__pycache__"):
        sandbox.write_file(folder + "/junk", "noise")
    assert sandbox.snapshot().files == replaced.files


def test_snapshot_without_git_and_copy_out(tmp_path):
    with Sandbox() as sandbox:
        sandbox.load_repo(SAMPLE / "repo", init_git=False)
        assert sandbox.snapshot().commits == 0
        sandbox.write_file("nested/extra.txt", "\u00e9\n")
        destination = tmp_path / "export"
        sandbox.copy_out(destination)
        assert (destination / "nested" / "extra.txt").read_text(encoding="utf-8") == "\u00e9\n"
        assert (destination / "calc" / "core.py").read_bytes() == (SAMPLE / "repo" / "calc" / "core.py").read_bytes()


def test_diff_outside_work(sandbox):
    sandbox.write_file("/home/agent/x", "outside")
    for path in ("/tmp/x", "/var/tmp/x", "/home/agent/.cache/x",
                 "/home/agent/__pycache__/x", "/home/agent/.pytest_cache/x", "/work/x"):
        sandbox.write_file(path, "noise")
    changes = sandbox.diff_outside_work()
    assert "A /home/agent/x" in changes
    assert changes == sorted(changes)
    assert not any("/tmp/x" in line or "/work" in line or "cache" in line for line in changes)
    assert "C /home" not in changes and "C /home/agent" not in changes


def test_context_cleanup_on_error_and_double_stop():
    instance = Sandbox()
    try:
        with pytest.raises(RuntimeError, match="deliberate"):
            with instance:
                raise RuntimeError("deliberate")
        assert docker("inspect", instance.name).returncode != 0
        instance.stop()
    finally:
        instance.stop()


def test_start_failure_is_cleaned_up():
    instance = Sandbox(pids="invalid")
    try:
        with pytest.raises(SandboxError):
            with instance:
                pytest.fail("invalid limits must fail")
        assert docker("inspect", instance.name).returncode != 0
    finally:
        instance.stop()


def test_hidden_baseline_solution_and_visible_test(tmp_path):
    task = load_task(SAMPLE)
    baseline = run_hidden_check(task, task.repo_dir)
    assert baseline.exit_code == 1 and not baseline.timed_out
    assert "2 failed" in baseline.output
    workspace = tmp_path / "solution"
    overlay(task.repo_dir, task.solution_dir, workspace)
    solved = run_hidden_check(task, workspace)
    assert solved.exit_code == 0 and "2 passed" in solved.output
    copy = tmp_path / "baseline"
    overlay(task.repo_dir, None, copy)
    assert (copy / "calc" / "core.py").read_bytes() == (task.repo_dir / "calc" / "core.py").read_bytes()
    with Sandbox() as sandbox:
        sandbox.load_repo(copy)
        result = sandbox.exec("python -m pytest -q -p no:cacheprovider tests")
        assert result.exit_code == 0 and "1 passed" in result.output


def test_hidden_error_removes_container(monkeypatch):
    from cvd import sandbox as module
    instances = []
    original = Sandbox._copy_in
    def fail_hidden(self, directory, target):
        if target == "/hidden":
            instances.append(self.name)
            raise SandboxError("deliberate copy failure")
        return original(self, directory, target)
    monkeypatch.setattr(Sandbox, "_copy_in", fail_hidden)
    with pytest.raises(SandboxError, match="deliberate"):
        module.run_hidden_check(load_task(SAMPLE), SAMPLE / "repo")
    assert len(instances) == 1
    assert docker("inspect", instances[0]).returncode != 0


def test_exec_host_backstop_preserves_partial_output(sandbox, monkeypatch):
    from cvd import sandbox as module
    with monkeypatch.context() as patch:
        def timeout(args, **kwargs):
            assert kwargs["timeout"] == 31
            raise subprocess.TimeoutExpired(args, kwargs["timeout"], output=b"partial\xff")
        patch.setattr(module.subprocess, "run", timeout)
        result = sandbox.exec("sleep 10", timeout_s=1)
    assert result.exit_code == 124 and result.timed_out and result.output == "partial\ufffd"


def test_verify_tasks_subprocess():
    result = subprocess.run(
        [sys.executable, "-m", "cvd", "verify-tasks", str(SAMPLE)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120,
    )
    assert result.returncode == 0, result.stdout.decode("utf-8", errors="replace")
    assert b"sample_task  lint=ok  baseline=fails  solution=passes" in result.stdout
