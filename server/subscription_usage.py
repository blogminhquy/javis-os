"""Separate Codex request observations from turn totals and context size."""
from __future__ import annotations


def _tokens(value: dict, camel: bool = True) -> dict:
    keys = ("inputTokens", "cachedInputTokens", "outputTokens") if camel else (
        "input_tokens", "cached_input_tokens", "output_tokens")
    values = [max(0, int(value.get(key) or 0)) for key in keys]
    return dict(zip(("input", "cache", "output"), values))


class CodexUsage:
    """Use cumulative counters to reject duplicate/limit-only notifications.

    A request is verified only when its last usage equals the cumulative delta.
    An unanchored resumed thread cannot prove that its first sample is complete.
    """

    def __init__(self, baseline=None):
        self.previous = baseline
        self.events = 0
        self.requests = []
        self.input = self.cache = self.output = 0
        self.last_input = None
        self.complete = baseline is not None

    def observe(self, usage: dict) -> None:
        self.events += 1
        last = _tokens(usage.get("last") or {})
        total = _tokens(usage["total"]) if usage.get("total") else None
        if total is not None and total == self.previous:
            return
        delta = ({key: total[key] - self.previous[key] for key in total}
                 if total is not None and self.previous is not None else last)
        verified = total is not None and self.previous is not None and delta == last
        if any(value < 0 for value in delta.values()):
            delta, verified = last, False
        self.complete = self.complete and verified
        self.previous = total
        if not any(delta.values()):
            return
        self.input += delta["input"]
        self.cache += delta["cache"]
        self.output += delta["output"]
        if last["input"] > 0:
            self.last_input = last["input"]
        self.requests.append({**delta, "uncached": max(0, delta["input"] - delta["cache"]),
                              "verified_request": verified, "last_request_input": last["input"]})

    def summary(self) -> dict:
        return {"scope": "turn", "source": "codex_app_server", "estimated": False,
                "input": self.input, "cache": self.cache,
                "uncached": max(0, self.input - self.cache), "output": self.output,
                "usage_event_count": self.events, "request_count": len(self.requests) if self.complete else None,
                "verified_request_count": sum(row["verified_request"] for row in self.requests),
                "complete": self.complete, "last_request_input": self.last_input}
