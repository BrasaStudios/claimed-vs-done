"""Small route capability and usage probe."""

import statistics
import time
from decimal import Decimal, InvalidOperation

from .client import ApiError
from .config import cost_usd

_ADD_TOOL = {
    "type": "function",
    "function": {
        "name": "add",
        "description": "Add two integers.",
        "parameters": {
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
            "additionalProperties": False,
        },
    },
}
_TOOL_PROMPT = "Use the add tool to add 17 and 25, then tell me the result."
_PRIME_PROMPT = "How many prime numbers are there between 1 and 100? Answer with the number only."


class _BudgetStop(Exception):
    pass


def _correct_arguments(call):
    if call.name != "add" or call.arguments is None:
        return False
    try:
        return (
            Decimal(str(call.arguments.get("a"))) == 17
            and Decimal(str(call.arguments.get("b"))) == 25
        )
    except (InvalidOperation, ValueError, TypeError):
        return False


def _effort_verdict(samples, efforts):
    for effort in efforts:
        if any(not sample["accepted"] for sample in samples[effort]):
            return "rejected:" + effort
    first = samples[efforts[0]]
    last = samples[efforts[-1]]
    if not first or not last:
        return "unclear"
    all_samples = [sample for effort in efforts for sample in samples[effort]]
    # A route that reports reasoning_tokens as 0 everywhere is not exposing
    # them; its reasoning is inside completion_tokens.
    field = (
        "reasoning_tokens"
        if all(sample["reasoning_tokens"] is not None for sample in all_samples)
        and any(sample["reasoning_tokens"] for sample in all_samples)
        else "completion_tokens"
    )
    low = statistics.median(sample[field] for sample in first)
    high = statistics.median(sample[field] for sample in last)
    if low == 0:
        return "works" if high > 0 else "no_effect"
    if high >= 1.5 * low:
        return "works"
    if 0.8 <= high / low <= 1.25:
        return "no_effect"
    return "unclear"


def probe(client, profile, efforts=("low", "high"), samples=2, max_usd=0.05) -> dict:
    efforts = tuple(efforts)
    if not efforts or any(not effort for effort in efforts):
        raise ValueError("At least one nonempty effort is required")
    if samples < 1:
        raise ValueError("samples must be positive")
    if max_usd < 0:
        raise ValueError("max_usd must be nonnegative")
    result = {
        "profile": profile.name,
        "model": profile.model,
        "providers_seen": [],
        "tool_round_trip": "aborted_max_usd",
        "effort": {"verdict": "unclear", "samples": {effort: [] for effort in efforts}},
        "usage_fields": [],
        "calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cost_usd": 0.0,
        "tokens_per_s_median": None,
        "aborted_max_usd": False,
    }
    providers = set()
    fields = set()
    speeds = []

    def complete(messages, tools=None, *, effort):
        if result["cost_usd"] >= max_usd:
            raise _BudgetStop
        result["calls"] += 1
        reply = client.complete(messages, tools, reasoning_effort=effort)
        result["prompt_tokens"] += reply.prompt_tokens
        result["completion_tokens"] += reply.completion_tokens
        result["cost_usd"] = cost_usd(
            profile, result["prompt_tokens"], result["completion_tokens"]
        )
        if reply.provider is not None:
            providers.add(reply.provider)
        usage = reply.usage_raw
        for field in ("prompt_tokens", "completion_tokens"):
            if usage.get(field) is not None:
                fields.add(field)
        for field in ("reasoning_tokens", "cached_tokens", "cost_reported"):
            if getattr(reply, field) is not None:
                fields.add(field)
        if reply.latency_s > 0:
            speeds.append(reply.completion_tokens / reply.latency_s)
        return reply

    try:
        messages = [{"role": "user", "content": _TOOL_PROMPT}]
        first = complete(messages, [_ADD_TOOL], effort=efforts[0])
        add_calls = [call for call in first.tool_calls if call.name == "add"]
        if not add_calls:
            result["tool_round_trip"] = "no_tool_call"
        elif not any(_correct_arguments(call) for call in add_calls):
            result["tool_round_trip"] = "bad_arguments"
        else:
            messages.append({
                "role": "assistant",
                "content": first.content or "",
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": call.arguments_raw},
                    }
                    for call in first.tool_calls
                ],
            })
            for call in first.tool_calls:
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": "42" if _correct_arguments(call) else "Error: unexpected tool call",
                })
            final = complete(messages, [_ADD_TOOL], effort=efforts[0])
            result["tool_round_trip"] = (
                "pass" if "42" in (final.content or "") else "no_final_answer"
            )
        for effort in efforts:
            for _ in range(samples):
                started = time.perf_counter()
                try:
                    reply = complete(
                        [{"role": "user", "content": _PRIME_PROMPT}], effort=effort
                    )
                except ApiError as error:
                    if error.status != 400:
                        raise
                    result["effort"]["samples"][effort].append({
                        "accepted": False,
                        "completion_tokens": None,
                        "reasoning_tokens": None,
                        "correct": False,
                        "latency_s": time.perf_counter() - started,
                    })
                else:
                    result["effort"]["samples"][effort].append({
                        "accepted": True,
                        "completion_tokens": reply.completion_tokens,
                        "reasoning_tokens": reply.reasoning_tokens,
                        "correct": "25" in (reply.content or ""),
                        "latency_s": reply.latency_s,
                    })
        result["effort"]["verdict"] = _effort_verdict(result["effort"]["samples"], efforts)
    except _BudgetStop:
        result["aborted_max_usd"] = True
        result["effort"]["verdict"] = "aborted_max_usd"
    result["providers_seen"] = sorted(providers)
    result["usage_fields"] = [
        name for name in (
            "prompt_tokens", "completion_tokens", "reasoning_tokens",
            "cached_tokens", "cost_reported",
        ) if name in fields
    ]
    if speeds:
        result["tokens_per_s_median"] = statistics.median(speeds)
    return result
