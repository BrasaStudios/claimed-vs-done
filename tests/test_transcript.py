

from cvd import transcript
from cvd.transcript import Transcript, read_transcript, redact


def test_transcript_sequence_clock_flush_and_read(tmp_path, monkeypatch, fake_key):
    ticks = iter([10.0, 10.123456, 11.987654])
    monkeypatch.setattr(transcript.time, "perf_counter", lambda: next(ticks))
    path = tmp_path / "trace.jsonl"
    record = {"type": "header", "secret": fake_key, "seq": 99, "t": 99}
    with Transcript(path, secrets=[fake_key]) as log:
        log.write(record)
        assert len(read_transcript(path)) == 1
        log.write({"type": "end", "text": "\u2603", "nested": [fake_key]})
    assert record["seq"] == 99
    lines = read_transcript(path)
    assert [line["seq"] for line in lines] == [0, 1]
    assert [line["t"] for line in lines] == [0.123, 1.988]
    assert lines[0]["secret"] == "[REDACTED]"
    assert lines[1]["nested"] == ["[REDACTED]"]
    assert lines[1]["text"] == "\u2603"
    data = path.read_bytes()
    assert fake_key.encode() not in data
    assert b"\r" not in data
    assert b"\\u2603" not in data
    assert len(data.splitlines()) == 2


def test_redact_threshold_and_overlapping_values():
    assert redact("short 12345678 abc12345678", ["short", "12345678", "abc12345678"]) == (
        "short [REDACTED] [REDACTED]"
    )


def test_escaped_secrets_stay_valid_json(tmp_path):
    secret = 'secret"with\\escapes\n'
    path = tmp_path / "trace.jsonl"
    with Transcript(path, secrets=[secret, "short"]) as log:
        log.write({"value": secret, "short": "short"})
    assert read_transcript(path)[0]["value"] == "[REDACTED]"
    assert read_transcript(path)[0]["short"] == "short"


def test_close_and_append(tmp_path):
    path = tmp_path / "trace.jsonl"
    first = Transcript(path)
    first.write({"type": "header"})
    first.close()
    first.close()
    with Transcript(path) as second:
        second.write({"type": "end"})
    assert [entry["type"] for entry in read_transcript(path)] == ["header", "end"]
