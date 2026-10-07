"""Per-session OAuth routing. Never infer account access from prices or model names."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
from pathlib import Path

RULE_VERSION = "chat-auto-v1"
TIERS = ("low", "medium", "high")
MODELS = {"low": "gpt-6-luna", "medium": "gpt-6.1-sol", "high": "gpt-6-astra"}
ACCESS_TTL = 86400


class RoutingUnavailable(ValueError):
    pass


def account_fingerprint(mcfg):
    account = (mcfg.get("openai_oauth") or {}).get("account_id")
    return hashlib.sha256(str(account).encode()).hexdigest() if account else ""


def access_path():
    return Path(os.getenv("JAVIS_STATE_DIR", str(Path(__file__).parent))) / "chat-auto-access.json"


def verified_candidates(mcfg, catalog, *, evidence=None, now=None):
    now = time.time() if now is None else now
    if evidence is None:
        try:
            evidence = json.loads(access_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            evidence = {}
    fp = account_fingerprint(mcfg)
    if not fp or evidence.get("account_fingerprint") != fp:
        return {}
    items = {x["id"]: x for x in (catalog or {}).get("items", [])}
    out = {}
    for tier, model in MODELS.items():
        proof = evidence.get("models", {}).get(model, {})
        stamp = proof.get("verified_at", 0)
        if (model in items and proof.get("executed_model") == model
                and proof.get("ok") is True and 0 <= now - stamp < ACCESS_TTL):
            out[tier] = items[model]
    return out


def normalized(text):
    return "".join(c for c in unicodedata.normalize("NFD", str(text).lower())
                   if unicodedata.category(c) != "Mn").replace("đ", "d")


def classify(text, previous=None, has_attachments=False):
    # Classify the user task, without making a model call.
    raw = str(text or "").strip()
    has_attachments = has_attachments or raw.startswith("[File đính kèm")
    # Only known dashboard wrappers; never strip arbitrary user bracketed content.
    wrapper = r"^\s*\[(?:FILE ĐANG MỞ|File đính kèm|NGỮ CẢNH GIAO DIỆN:)[^\]]*\]\s*"
    for _ in range(4):
        rest = re.sub(wrapper, "", raw, count=1)
        if rest == raw:
            break
        raw = rest
    t = normalized(raw).strip()
    continuation = re.fullmatch(r"(?:tiep tuc(?: di)?|lam tiep(?: di)?|continue|go on|ok(?: lam di)?|duyet(?: di)?)[.!?\s]*", t)
    if continuation and previous and previous.get("tier") in TIERS:
        return previous["tier"], "continuation_of_previous_task"
    if re.search(r"thiet ke|kien truc|debug|doi soat|mau thuan|trien khai|migration|architecture|security|conflict|deploy|race condition|phat hanh|ngan sach|budget|quang cao|campaign", t):
        return "high", "complex_or_high_impact_task"
    if len(t) > 2400 or t.count("\n") > 18:
        return "high", "multiple_constraints"
    if has_attachments or re.search(r"phan tich|ke hoach|viet|so sanh|analyse|analyze|plan|compare|write|tom tat|summar", t) or len(t) > 160:
        return "medium", "reasoning_or_content_task"
    if re.search(r"chao|hello|hi\b|cam on|thanks|dinh dang|format|doi ngay|hom nay|tinh|calculate|bao nhieu", t):
        return "low", "simple_explicit_task"
    return "medium", "conservative_default"


def resolve(text, candidates, previous=None, has_attachments=False, profile="balanced"):
    tier, reason = classify(text, previous, has_attachments)
    if profile == "quality" and tier == "low":
        tier, reason = "medium", "quality_profile"
    for level in TIERS[TIERS.index(tier):]:
        item = candidates.get(level)
        if not item:
            continue
        desired = {"low": "low", "medium": "medium", "high": "high"}[level]
        supported = item.get("supported_reasoning_efforts", [])
        effort = desired if desired in supported else None
        return {"mode": "auto", "profile": profile, "provider": "openai-oauth",
                "requested_model": None, "selected_model": item["id"],
                "executed_model": None, "execution_evidence": None,
                "tier": level, "required_tier": tier, "reason": reason,
                "effort": effort, "rule_version": RULE_VERSION,
                "escalations": 0, "usage": None, "attempts": []}
    raise RoutingUnavailable("No verified OAuth candidate meets the required tier")


def safe_fallback(decision, candidates, error, activity=False):
    # Transport/auth/timeouts and any observed or unknown activity must stop.
    if activity or decision["escalations"] >= 2:
        return None
    if not re.search(r"model.*(?:unavailable|not available|not found|not supported|does not exist)|model_not_found", error, re.I):
        return None
    for tier in TIERS[TIERS.index(decision["tier"]) + 1:]:
        if tier in candidates:
            next_route = resolve("", {tier: candidates[tier]}, {"tier": tier})
            next_route.update(required_tier=decision["required_tier"], reason="model_unavailable_before_activity",
                              escalations=decision["escalations"] + 1, profile=decision["profile"])
            return next_route
    return None


def executed_model(thread_id, started_after=0, home=None):
    """Read only this invocation's native turn context. Unknown remains unknown."""
    if not re.fullmatch(r"[a-zA-Z0-9-]{16,80}", thread_id or ""):
        return None
    root = Path(home or os.getenv("CODEX_HOME", str(Path.home() / ".codex"))) / "sessions"
    try:
        files = sorted(root.glob(f"*/*/*/*{thread_id}*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        for file in files[:1]:
            model = None
            for line in file.open(encoding="utf-8"):
                try:
                    event = json.loads(line)
                    if event.get("type") != "turn_context":
                        continue
                    from datetime import datetime
                    ts = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).timestamp()
                    if ts >= started_after:
                        model = event.get("payload", {}).get("model")
                except (ValueError, KeyError):
                    continue
            return model
    except OSError:
        pass
    return None


def invocation_usage(thread_id, started_after, home=None):
    """Codex turn.completed can be thread-cumulative. Subtract the native baseline."""
    if not re.fullmatch(r"[a-zA-Z0-9-]{16,80}", thread_id or ""):
        return None
    from datetime import datetime
    root = Path(home or os.getenv("CODEX_HOME", str(Path.home() / ".codex"))) / "sessions"
    mapping = {"input_tokens": "input_tokens", "output_tokens": "output_tokens",
               "cached_input_tokens": "cached_input_tokens",
               "cache_write_input_tokens": "cache_write_input_tokens",
               "reasoning_tokens": "reasoning_output_tokens"}
    before, after = None, None
    try:
        files = sorted(root.glob(f"*/*/*/*{thread_id}*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        for file in files[:1]:
            with file.open(encoding="utf-8") as stream:
                for line in stream:
                    try:
                        event = json.loads(line)
                        payload = event.get("payload") or {}
                        if event.get("type") != "event_msg" or payload.get("type") != "token_count":
                            continue
                        usage = (payload.get("info") or {}).get("total_token_usage")
                        if not isinstance(usage, dict):
                            continue
                        stamp = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).timestamp()
                        if stamp < started_after:
                            before = usage
                        else:
                            after = usage
                    except (ValueError, KeyError):
                        continue
    except OSError:
        return None
    if after is None:
        return None
    out = {}
    for key, native in mapping.items():
        value = after.get(native)
        baseline = before.get(native) if before else 0
        out[key] = value - baseline if (isinstance(value, int) and isinstance(baseline, int)
                                        and value >= baseline) else None
    return out


class InvocationUsage:
    """Replace cumulative snapshots within an invocation; sum only distinct calls."""
    def __init__(self):
        self.calls = {}

    def observe(self, invocation, event):
        usage = event.get("usage")
        if not isinstance(usage, dict):
            return
        self.calls[invocation] = {k: usage.get(k) for k in
            ("input_tokens", "output_tokens", "cached_input_tokens", "cache_write_input_tokens", "reasoning_tokens")}

    def total(self):
        if not self.calls:
            return None
        return {key: sum(c[key] for c in self.calls.values())
                if all(isinstance(c.get(key), int) for c in self.calls.values()) else None
                for key in next(iter(self.calls.values()))}


async def verify_access(mcfg, catalog, creds, *, client_factory=None):
    """Explicit Auto selection probes OAuth without tools or task replay."""
    import httpx
    import uuid
    evidence = {"account_fingerprint": account_fingerprint(mcfg), "models": {}}
    items = {x["id"]: x for x in (catalog or {}).get("items", [])}
    if (not creds.get("access_token") or not evidence["account_fingerprint"]
            or account_fingerprint({"openai_oauth": creds}) != evidence["account_fingerprint"]):
        return evidence
    headers = {"Authorization": "Bearer " + creds["access_token"],
               "chatgpt-account-id": creds.get("account_id") or "",
               "OpenAI-Beta": "responses=experimental", "originator": "codex_cli_rs",
               "session_id": str(uuid.uuid4()), "Accept": "text/event-stream"}
    factory = client_factory or httpx.AsyncClient
    async with factory(timeout=httpx.Timeout(30, connect=10)) as client:
        for model in MODELS.values():
            if model not in items:
                continue
            proof = {"ok": False, "verified_at": time.time(), "executed_model": None}
            payload = {"model": model, "instructions": "Reply exactly OAUTH_AUTO_OK.",
                       "input": [{"role": "user", "content": "OAUTH_AUTO_OK"}],
                       "stream": True, "store": False}
            if "low" in items[model].get("supported_reasoning_efforts", []):
                payload["reasoning"] = {"effort": "low"}
            try:
                async with client.stream("POST", "https://chatgpt.com/backend-api/codex/responses",
                                         headers=headers, json=payload) as response:
                    proof["http_status"] = response.status_code
                    if response.status_code == 200:
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            try:
                                event = json.loads(line[5:])
                            except ValueError:
                                continue
                            if event.get("type") == "response.completed":
                                result = event.get("response") or {}
                                proof.update(executed_model=result.get("model"),
                                             usage=result.get("usage"), evidence="oauth_response_completed")
                                proof["ok"] = result.get("model") == model
                            elif event.get("type") in ("error", "response.failed"):
                                proof["ok"] = False
                                break
            except (httpx.HTTPError, OSError):
                proof["error"] = "oauth_probe_failed"
            evidence["models"][model] = proof
    # Atomic, account-scoped proof, containing no credentials or user prompt.
    dest = access_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_suffix(".tmp")
    temp.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, dest)
    return evidence
