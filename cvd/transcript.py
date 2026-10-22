"""Flushed JSONL transcripts with secret redaction."""

import json
import time
from pathlib import Path


def redact(text: str, secrets) -> str:
    for secret in sorted(
        {secret for secret in secrets if isinstance(secret, str) and len(secret) >= 8},
        key=len,
        reverse=True,
    ):
        text = text.replace(secret, "[REDACTED]")
    return text


class Transcript:
    def __init__(self, path, secrets=()):
        self._started = time.perf_counter()
        self._seq = 0
        self._secrets = tuple(
            secret for secret in secrets if isinstance(secret, str) and len(secret) >= 8
        )
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = path.open("a", encoding="utf-8", newline="\n")

    def write(self, record: dict) -> None:
        entry = dict(record)
        entry["seq"] = self._seq
        entry["t"] = round(time.perf_counter() - self._started, 3)
        line = json.dumps(entry, ensure_ascii=False)
        # Match the JSON representation, including escaped quotes and backslashes.
        encoded_secrets = (
            json.dumps(secret, ensure_ascii=False)[1:-1] for secret in self._secrets
        )
        self._stream.write(redact(line, encoded_secrets) + "\n")
        self._stream.flush()
        self._seq += 1

    def close(self) -> None:
        self._stream.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


def read_transcript(path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]
