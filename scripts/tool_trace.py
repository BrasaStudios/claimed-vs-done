"""Print a run's tool calls in order (turn, tool, exit code, start of the arguments).

Usage: python scripts/tool_trace.py runs/<batch>/<run> [--last N]
"""
import json
import sys
from pathlib import Path


def main(run_dir: str, last: int | None) -> None:
    rows = []
    for line in (Path(run_dir) / "transcript.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("type") == "tool_call":
            arguments = (record.get("arguments_raw") or "").replace("\n", " ")[:80]
            rows.append(f"turn {record['turn']:>2} {record['name']:<10} exit={record.get('exit_code')} {arguments}")
        elif record.get("type") == "nudge":
            rows.append(f"turn {record['turn']:>2} (nudge: no tool call)")
    for row in rows[-last:] if last else rows:
        print(row)


if __name__ == "__main__":
    count = int(sys.argv[sys.argv.index("--last") + 1]) if "--last" in sys.argv else None
    main(sys.argv[1], count)
