"""One source of truth for "which provider/model runs this agent, in this kind of turn, and can it" (2026-11-17).

Before this module the rules lived in five places (POST /agents, the team admin tool, team_engine, the team gate,
the dashboard) and drifted apart: a team could be created with a leader whose provider cannot run a text-only team
turn, and the owner only learned it from "Không rõ lý do" in the chat. Every caller now asks here.

Pure: no file, settings or network I/O. Machine facts (is the CLI signed in, which catalogs list the model, can the
team gate stop this provider's tools on THIS machine) come in through `Probes`, which main.py builds once.

Contract (board #8 + amendments #9):
- Modes actually used: solo_chat, team_text (reply/plan/synthesize/volunteer + text-only helpers), team_tool_full and
  team_tool_gated (work/help steps of a job; gated unless the team is in full mode). Retry and restart resume run the
  same mode as the step they repeat.
- Identity: an agent's explicit provider is used exactly (unknown -> provider_unknown, never reinterpreted); model-only
  legacy data is resolved by the caller's legacy resolver (source=legacy); only an empty selection inherits MAIN
  (source=main). Never another provider, never "the first provider", never a swap because something is unavailable.
- Evidence kept in four separate fields: adapter (code supports the mode), configured (signed in / key / CLI),
  model (catalog sources for THIS provider only), last_call (last real outcome since process start).
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

import aux_engine

CLAUDE = aux_engine.CLAUDE
CODEX = aux_engine.CODEX
GROK_CLI = aux_engine.GROK_CLI
ANTIGRAVITY = aux_engine.ANTIGRAVITY
API_PROVIDERS = tuple(aux_engine.API_PROVIDERS)
COMPAT_GATEWAYS = ("openai-compat", "anthropic-compat")
# Every provider an agent can be pinned to and that has a builder (must equal main.AGENT_PROVIDERS as a set).
KNOWN_PROVIDERS = (CLAUDE, CODEX, GROK_CLI, ANTIGRAVITY) + API_PROVIDERS

SOLO_CHAT = "solo_chat"
TEAM_TEXT = "team_text"
TEAM_TOOL_FULL = "team_tool_full"
TEAM_TOOL_GATED = "team_tool_gated"
MODES = (SOLO_CHAT, TEAM_TEXT, TEAM_TOOL_FULL, TEAM_TOOL_GATED)

# team_runner roles (LEADER_ROLES, REPLY_ROLES, TOOL_ROLES, member_volunteer).
TEXT_ROLES = ("leader_reply", "member_reply", "member_volunteer", "plan", "synthesize")
TOOL_ROLES = ("work", "help")
FULL = "full"   # team_gate.FULL; anything else (incl. missing) is gated, as in team_runner

# (a) adapter support per mode, static upper bound. team_tool_gated is narrowed further by the machine gate probe.
# Grok Build and Antigravity have no verified text-only mechanism (native tools cannot be switched off for a turn),
# so they are NOT text-only: the guard stays until a probe proves tool side effects impossible.
_ADAPTER = {
    SOLO_CHAT: frozenset(KNOWN_PROVIDERS),
    TEAM_TEXT: frozenset((CLAUDE, CODEX) + API_PROVIDERS),
    TEAM_TOOL_FULL: frozenset(KNOWN_PROVIDERS),
    TEAM_TOOL_GATED: frozenset((CLAUDE, CODEX) + API_PROVIDERS),
}

MODE_LABEL_VI = {
    SOLO_CHAT: "chat riêng",
    TEAM_TEXT: "trò chuyện, lập kế hoạch, tổng hợp trong nhóm (chỉ chữ)",
    TEAM_TOOL_FULL: "bước làm việc có công cụ (toàn quyền)",
    TEAM_TOOL_GATED: "bước làm việc có công cụ cần duyệt",
}
MODE_LABEL_EN = {
    SOLO_CHAT: "private chat",
    TEAM_TEXT: "team chat, planning and synthesis (text only)",
    TEAM_TOOL_FULL: "tool step (full access)",
    TEAM_TOOL_GATED: "tool step with approvals",
}

# ---- reason codes -------------------------------------------------------------------------------------------------

CAPABILITY_UNSUPPORTED = "capability_unsupported"
AUTH_MISSING = "auth_missing"
MODEL_INVALID = "model_invalid"
PROVIDER_UNKNOWN = "provider_unknown"
QUOTA_OR_RATE_LIMIT = "quota_or_rate_limit"
NETWORK = "network"
BUILD_FAILED = "build_failed"
MODEL_UNVERIFIED = "model_unverified"   # informational, never blocks

CONFIG_CODES = frozenset((CAPABILITY_UNSUPPORTED, AUTH_MISSING, MODEL_INVALID, PROVIDER_UNKNOWN, BUILD_FAILED))
# Codes that make team create / add member / leader change refuse (auth_missing is flagged, not refused).
REFUSE_CODES = frozenset((CAPABILITY_UNSUPPORTED, PROVIDER_UNKNOWN, MODEL_INVALID))
RETRYABLE = {CAPABILITY_UNSUPPORTED: False, AUTH_MISSING: False, MODEL_INVALID: False, PROVIDER_UNKNOWN: False,
             QUOTA_OR_RATE_LIMIT: True, NETWORK: True, BUILD_FAILED: False, MODEL_UNVERIFIED: False}
ALIASES = {"invalid_provider": PROVIDER_UNKNOWN, "provider_required": PROVIDER_UNKNOWN,
           "provider_not_ready": AUTH_MISSING, "engine_unavailable": BUILD_FAILED,
           "engine_build_failed": BUILD_FAILED, "auth": AUTH_MISSING, "quota": QUOTA_OR_RATE_LIMIT,
           "rate_limit": QUOTA_OR_RATE_LIMIT}

_TEXT = {
    CAPABILITY_UNSUPPORTED: (
        "{provider} chưa chạy được kiểu lượt này ({mode_vi}).",
        "{provider} cannot run this kind of turn ({mode_en}).",
        "Ở trang Cộng sự, đổi model của trợ lý sang provider chạy được kiểu lượt này (Claude, ChatGPT/Codex hoặc "
        "một model API). Javis không tự đổi provider.",
        "On the Partners page, switch the assistant to a provider that runs this kind of turn (Claude, "
        "ChatGPT/Codex or an API model). Javis never switches providers by itself."),
    AUTH_MISSING: (
        "{provider} chưa đăng nhập hoặc chưa có khoá.",
        "{provider} is not signed in or has no key.",
        "Đăng nhập lại hoặc thêm khoá cho {provider} ở trang Models, rồi bấm Thử lại.",
        "Sign in again or add a key for {provider} on the Models page, then press Try again."),
    MODEL_INVALID: (
        "Model không hợp lệ cho {provider}.",
        "The model is not valid for {provider}.",
        "Chọn lại model của {provider} ở trang Cộng sự.",
        "Select the {provider} model again on the Partners page."),
    PROVIDER_UNKNOWN: (
        "Provider không có trong danh sách Javis chạy được.",
        "This provider is not one Javis can run.",
        "Chọn lại cả provider và model ở trang Cộng sự; cấu hình cũ chưa bị thay đổi.",
        "Select both provider and model again on the Partners page; the saved configuration is unchanged."),
    QUOTA_OR_RATE_LIMIT: (
        "{provider} hết lượt hoặc đang bị giới hạn tốc độ.",
        "{provider} is out of quota or rate limited.",
        "Chờ hết giới hạn hoặc đổi tài khoản ở trang Models, rồi bấm Thử lại.",
        "Wait for the limit to reset or switch account on the Models page, then press Try again."),
    NETWORK: (
        "Không kết nối được tới {provider}.",
        "Could not reach {provider}.",
        "Kiểm tra mạng và địa chỉ máy chủ của {provider}, rồi bấm Thử lại.",
        "Check the network and the {provider} endpoint, then press Try again."),
    BUILD_FAILED: (
        "Không dựng được engine {provider}.",
        "Could not build the {provider} engine.",
        "Kiểm tra {provider} đã cài và đăng nhập ở trang Models; chi tiết nằm trong nhật ký máy chủ.",
        "Check that {provider} is installed and signed in on the Models page; details are in the server log."),
    MODEL_UNVERIFIED: (
        "Chưa có bằng chứng model này có ở {provider}.",
        "No evidence yet that {provider} offers this model.",
        "Làm mới danh sách model của {provider} ở trang Models, hoặc kiểm tra lại tên model.",
        "Refresh the {provider} model list on the Models page, or check the model name."),
}


def normalize_code(code: str) -> str:
    c = str(code or "").strip()
    return ALIASES.get(c, c)


def _chu(vi: str, en: str, **kw) -> str:
    try:
        from localefmt import chu
        return chu(vi, en, **kw)
    except Exception:  # noqa: BLE001 - localefmt unavailable in a stripped test env
        try:
            return vi.format(**kw)
        except (KeyError, IndexError, ValueError):
            return vi


def reason(code: str, provider: str = "", mode: str = "") -> dict:
    """{reason_code, retryable, message, fix_hint} for a stable code. Unknown codes keep their name, not retryable."""
    c = normalize_code(code)
    if not c:
        return {"reason_code": "", "retryable": False, "message": "", "fix_hint": ""}
    vi, en, hint_vi, hint_en = _TEXT.get(c, ("{provider}: " + c, "{provider}: " + c, "", ""))
    kw = {"provider": provider or "provider", "mode_vi": MODE_LABEL_VI.get(mode, mode or ""),
          "mode_en": MODE_LABEL_EN.get(mode, mode or "")}
    return {"reason_code": c, "retryable": bool(RETRYABLE.get(c, False)), "message": _chu(vi, en, **kw),
            "fix_hint": _chu(hint_vi, hint_en, **kw) if hint_vi else ""}


# ---- probes -------------------------------------------------------------------------------------------------------

@dataclass
class Probes:
    """Machine facts, supplied by the caller (main._capability_probes). Every field is optional; a missing probe
    makes the matching evidence `None` (unknown) - except the gate, which fails closed."""
    availability: Optional[Callable[[dict], tuple]] = None      # spec -> (ok, why)    (b) configured
    gate_support: Optional[Callable[[str], dict]] = None        # provider -> {ok, reason}  gated adapter, this machine
    catalog: Optional[Callable[[str], dict]] = None             # provider -> {source: [model ids]}  (c)
    legacy_provider: Optional[Callable[[str], str]] = None      # model -> provider, for model-only legacy agents
    known_providers: tuple = KNOWN_PROVIDERS


CATALOG_SOURCES = ("remote", "remembered", "manual", "default")

# ---- (d) last real call outcome -----------------------------------------------------------------------------------

_OUTCOMES: dict = {}
_OUTCOMES_LOCK = threading.Lock()


def record_outcome(provider: str, model: str, ok: bool, code: str = "") -> None:
    """Remember the last real engine outcome for (provider, model). In memory: evidence since process start only."""
    with _OUTCOMES_LOCK:
        _OUTCOMES[(str(provider or ""), str(model or ""))] = {"ok": bool(ok), "code": normalize_code(code) if not ok
                                                              else "", "at": int(time.time())}


def last_outcome(provider: str, model: str) -> Optional[dict]:
    with _OUTCOMES_LOCK:
        got = _OUTCOMES.get((str(provider or ""), str(model or "")))
        return dict(got) if got else None


def _reset_outcomes_for_tests() -> None:
    with _OUTCOMES_LOCK:
        _OUTCOMES.clear()


# ---- modes --------------------------------------------------------------------------------------------------------

def tool_mode(work_mode: Any) -> str:
    return TEAM_TOOL_FULL if str(work_mode or "") == FULL else TEAM_TOOL_GATED


def mode_for(role: str, work_mode: Any = None, has_task: bool = True) -> str:
    """The mode of one team turn, exactly as team_runner._prepare decides tool_turn."""
    if str(role or "") in TOOL_ROLES and has_task:
        return tool_mode(work_mode)
    return TEAM_TEXT


def required_modes(is_leader: bool, work_mode: Any = None) -> tuple:
    """Modes a team member must be able to run. Leader: replies, plan, synthesize (+ work steps it may be given);
    member: replies (+ work/help steps)."""
    return (TEAM_TEXT, tool_mode(work_mode))


def adapter_static(provider: str, mode: str) -> bool:
    """(a) without machine flags: does any builder exist for this provider in this mode."""
    return str(provider or "") in _ADAPTER.get(mode, frozenset())


def adapter_supports(provider: str, mode: str, probes: Optional[Probes] = None) -> tuple:
    """(a) with this machine's flags: (ok, why). Gated mode asks the gate probe; no probe -> conservative default
    (team_gate.provider_support with no Codex sandbox), i.e. fail closed."""
    p = str(provider or "")
    if not adapter_static(p, mode):
        return False, ""
    if mode == TEAM_TOOL_GATED:
        try:
            if probes is not None and probes.gate_support is not None:
                sup = probes.gate_support(p) or {}
            else:
                import team_gate
                sup = team_gate.provider_support(p, codex_sandbox=None, api_providers=API_PROVIDERS)
        except Exception as e:  # noqa: BLE001 - a broken probe never opens the gate
            return False, type(e).__name__
        return bool(sup.get("ok")), str(sup.get("reason") or "")
    return True, ""


# ---- identity -----------------------------------------------------------------------------------------------------

def select(agent_model: str, agent_provider: str, main: Optional[dict],
           legacy_provider: Optional[Callable[[str], str]] = None) -> dict:
    """Identity only: {provider, model, source, note}. Availability and capability never change it."""
    model = str(agent_model or "").strip()
    provider = str(agent_provider or "").strip()
    if provider:
        return {"provider": provider, "model": model, "source": "agent", "note": ""}
    if model:
        p = ""
        if legacy_provider is not None:
            try:
                p = str(legacy_provider(model) or "")
            except Exception:  # noqa: BLE001
                p = ""
        return {"provider": p, "model": model, "source": "legacy", "note": "legacy_model_only"}
    m = dict(main or {})
    return {"provider": str(m.get("provider") or CLAUDE), "model": str(m.get("model") or ""), "source": "main",
            "note": ""}


_MODEL_BAD = re.compile(r"[\s\x00-\x1f\x7f]")


def _model_shape_ok(model: str) -> bool:
    return bool(model) and len(model) <= 200 and not _MODEL_BAD.search(model)


def validate_agent_selection(provider: str, model: str, probes: Optional[Probes] = None) -> dict:
    """The ONE save-time validator (POST /agents, _TeamAdmin.create_agent / set_model).
    Returns {ok, provider, model, reason_code, message, fix_hint, retryable}; provider/model normalized
    (empty model = inherit MAIN, provider cleared). Refuses only structural errors; auth/catalog are warnings
    that the caller reports via resolve()."""
    known = tuple((probes.known_providers if probes else None) or KNOWN_PROVIDERS)
    p = str(provider or "").strip()
    m = str(model or "").strip()
    if p and p not in known:
        return {"ok": False, "provider": p, "model": m, **reason(PROVIDER_UNKNOWN, p)}
    if m and not p:
        r = reason(PROVIDER_UNKNOWN)
        r["message"] = _chu("Model chưa có provider.", "The model has no provider.")
        return {"ok": False, "provider": "", "model": m, **r}
    if not m:
        return {"ok": True, "provider": "", "model": "", **reason("")}
    if not _model_shape_ok(m):
        return {"ok": False, "provider": p, "model": m, **reason(MODEL_INVALID, p)}
    return {"ok": True, "provider": p, "model": m, **reason("")}


# ---- evidence -----------------------------------------------------------------------------------------------------

def model_evidence(provider: str, model: str, probes: Optional[Probes] = None) -> dict:
    """(c) Which catalogs of THIS provider list THIS model. known: True/False, or None when nothing to compare
    (empty model = the provider's own default, or no catalog probe / empty catalogs). Another provider's catalog is
    never consulted: the same name under two providers is two different models."""
    if not model:
        return {"known": None, "sources": []}
    if probes is None or probes.catalog is None:
        return {"known": None, "sources": []}
    try:
        cats = probes.catalog(provider) or {}
    except Exception:  # noqa: BLE001
        return {"known": None, "sources": []}
    any_list = False
    sources = []
    for src in CATALOG_SOURCES:
        ids = [str(x) for x in (cats.get(src) or [])]
        if ids:
            any_list = True
            if model in ids:
                sources.append(src)
    if not any_list:
        return {"known": None, "sources": []}
    return {"known": bool(sources), "sources": sources}


def configured(provider: str, model: str, probes: Optional[Probes] = None) -> dict:
    """(b) provider configured / signed in. None when no probe."""
    if probes is None or probes.availability is None:
        return {"ok": None, "detail": ""}
    try:
        ok, why = probes.availability({"provider": provider, "model": model})
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": type(e).__name__}
    return {"ok": bool(ok), "detail": "" if ok else str(why or "")}


def manual_only_gateway(provider: str, ev: dict) -> bool:
    return provider in COMPAT_GATEWAYS and list(ev.get("sources") or []) == ["manual"]


# ---- resolve ------------------------------------------------------------------------------------------------------

def _blocking_code(provider: str, model: str, source: str, mode: str, probes: Optional[Probes],
                   adapter_ok: bool, conf: dict) -> str:
    known = tuple((probes.known_providers if probes else None) or KNOWN_PROVIDERS)
    if not provider or provider not in known:
        return PROVIDER_UNKNOWN
    if provider in API_PROVIDERS and not model:
        return MODEL_INVALID
    if model and not _model_shape_ok(model):
        return MODEL_INVALID
    if not adapter_ok:
        return CAPABILITY_UNSUPPORTED
    if conf.get("ok") is False:
        return AUTH_MISSING
    return ""


def resolve(agent: Optional[dict], main: Optional[dict], mode: str, probes: Optional[Probes] = None, *,
            all_modes: bool = False) -> dict:
    """The effective provider/model of `agent` ({model, model_provider}) for `mode`, and whether it can run.

    status: blocked (reason_code is a config error), unverified (runnable; no catalog evidence for the model, or a
    compat gateway known only from owner-typed names), ready."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    a = dict(agent or {})
    sel = select(a.get("model") or "", a.get("model_provider") or "", main,
                 probes.legacy_provider if probes else None)
    prov, model = sel["provider"], sel["model"]
    ad_ok, ad_why = adapter_supports(prov, mode, probes)
    conf = configured(prov, model, probes)
    ev = model_evidence(prov, model, probes)
    code = _blocking_code(prov, model, sel["source"], mode, probes, ad_ok, conf)
    if code:
        status = "blocked"
    elif ev["known"] is False or manual_only_gateway(prov, ev):
        status, code = "unverified", MODEL_UNVERIFIED
    else:
        status = "ready"
    out = {"provider": prov, "model": model, "source": sel["source"], "note": sel["note"], "mode": mode,
           "status": status, **reason(code, prov, mode),
           "evidence": {"adapter": {"ok": ad_ok, "why": ad_why}, "configured": conf, "model": ev,
                        "last_call": last_outcome(prov, model)}}
    if code == CAPABILITY_UNSUPPORTED and ad_why:
        out["detail"] = ad_why
    if all_modes:
        modes = {}
        for m in MODES:
            ok_m, _why = adapter_supports(prov, m, probes)
            c = _blocking_code(prov, model, sel["source"], m, probes, ok_m, conf)
            modes[m] = {"ok": not c, "reason_code": c}
        out["modes"] = modes
    return out


def preflight(agent: Optional[dict], main: Optional[dict], mode: str, probes: Optional[Probes] = None) -> dict:
    """Runtime check before building an engine. Same as resolve; the caller raises on status == blocked."""
    return resolve(agent, main, mode, probes)


# ---- teams --------------------------------------------------------------------------------------------------------

def member_status(member: dict, is_leader: bool, work_mode: Any, main: Optional[dict],
                  probes: Optional[Probes] = None) -> dict:
    modes = required_modes(is_leader, work_mode)
    issues = []
    first = None
    text_ok = None
    for m in modes:
        r = resolve(member, main, m, probes)
        first = first or r
        if m == TEAM_TEXT:
            text_ok = r["status"] != "blocked"
        if r["status"] == "blocked" and m != TEAM_TEXT and text_ok and r["reason_code"] == CAPABILITY_UNSUPPORTED:
            # #16/#18: the member can chat/plan; only its tool steps cannot run (e.g. gated Codex on a machine without
            # its sandbox). A warning, not a refusal; the runtime still refuses that step with the coded error.
            # The machine cause is reported as an owner setting; never suggests turning a sandbox or approvals off.
            why = str(r.get("detail") or "")
            msg = _chu("{provider} chưa chạy được {mode_vi} trên máy này.",
                       "{provider} cannot run {mode_en} on this machine.", provider=r["provider"],
                       mode_vi=MODE_LABEL_VI.get(m, m), mode_en=MODE_LABEL_EN.get(m, m))
            if why:
                msg += " " + _chu("Lý do: {why}.", "Why: {why}.", why=why.rstrip("."))
            hint = _chu("Đây là thiết lập của chủ máy, Javis không tự đổi. Bước làm việc có thể giao cho thành viên "
                        "dùng Claude hoặc một model API; trò chuyện và lập kế hoạch vẫn chạy bình thường.",
                        "This is a machine owner setting; Javis does not change it. Tool steps can go to a member on "
                        "Claude or an API model; chat and planning still run normally.")
            issues.append({"mode": m, "reason_code": r["reason_code"], "message": msg, "fix_hint": hint,
                           "retryable": False, "severity": "warning", "machine_reason": why})
        elif r["status"] == "blocked":
            issues.append({"mode": m, "reason_code": r["reason_code"], "message": r["message"],
                           "fix_hint": r["fix_hint"], "retryable": r["retryable"], "severity": "blocked"})
        elif r["status"] == "unverified" and manual_only_gateway(r["provider"], r["evidence"]["model"]):
            # A4: catalog noise is not a team warning, except a compat gateway known only from typed names.
            issues.append({"mode": m, "reason_code": r["reason_code"], "message": r["message"],
                           "fix_hint": r["fix_hint"], "retryable": False, "severity": "warning"})
    # identical issue codes across modes (provider_unknown, auth_missing) are reported once
    seen, uniq = set(), []
    for i in issues:
        k = i["reason_code"] if i["reason_code"] in (PROVIDER_UNKNOWN, AUTH_MISSING, MODEL_INVALID) else (
            i["reason_code"], i["mode"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(i)
    return {"agent_key": str(member.get("agent_key") or member.get("key") or ""),
            "name": str(member.get("name") or ""), "role": "leader" if is_leader else "member",
            "provider": first["provider"], "model": first["model"], "source": first["source"],
            "required_modes": list(modes), "issues": uniq}


def team_status(members: Iterable[dict], leader_key: str, work_mode: Any, main: Optional[dict],
                probes: Optional[Probes] = None) -> dict:
    """config_status of a team: {status: ready|warning|blocked, refuse, members:[...]}. `refuse` is what create /
    add member / leader change act on (capability_unsupported, provider_unknown, model_invalid)."""
    rows = []
    for mb in members or ():
        key = str(mb.get("agent_key") or mb.get("key") or "")
        rows.append(member_status(mb, key == str(leader_key or ""), work_mode, main, probes))
    sev = [i["severity"] for r in rows for i in r["issues"]]
    status = "blocked" if "blocked" in sev else ("warning" if sev else "ready")
    # #18: refuse only when a member cannot run team_text, or its provider/model is invalid in any mode;
    # auth_missing is flagged, tool-mode-only capability gaps are warnings.
    refuse = any(i["severity"] == "blocked" and i["reason_code"] in REFUSE_CODES for r in rows for i in r["issues"])
    return {"status": status, "refuse": refuse, "work_mode": str(work_mode or "gated"), "members": rows}


# ---- MAIN change impact -------------------------------------------------------------------------------------------

def main_change_impact(agents: Iterable[dict], teams: Iterable[dict], old_main: Optional[dict],
                       new_main: Optional[dict], probes: Optional[Probes] = None) -> dict:
    """What changes if MAIN goes from old_main to new_main. `agents`: [{key, name, model, model_provider}];
    `teams`: [{team_id, name, leader_key, work_mode, members:[agent dicts with agent_key]}].
    Only agents that inherit MAIN can change. `blocking` counts things that go from runnable to blocked."""
    out_agents = []
    blocking = 0
    for a in agents or ():
        if select(a.get("model") or "", a.get("model_provider") or "", old_main)["source"] != "main":
            continue
        b = resolve(a, old_main, SOLO_CHAT, probes)
        n = resolve(a, new_main, SOLO_CHAT, probes)
        nt = resolve(a, new_main, TEAM_TEXT, probes)
        row = {"key": str(a.get("key") or a.get("agent_key") or ""), "name": str(a.get("name") or ""),
               "before": {"provider": b["provider"], "model": b["model"]},
               "after": {"provider": n["provider"], "model": n["model"]},
               "before_status": b["status"], "after_status": n["status"], "reason_code": n["reason_code"],
               "team_text_after": {"ok": nt["status"] != "blocked", "reason_code": nt["reason_code"]}}
        if b["status"] != "blocked" and n["status"] == "blocked":
            blocking += 1
        out_agents.append(row)
    out_teams = []
    for t in teams or ():
        before = team_status(t.get("members") or (), t.get("leader_key") or "", t.get("work_mode"), old_main, probes)
        after = team_status(t.get("members") or (), t.get("leader_key") or "", t.get("work_mode"), new_main, probes)
        if before == after:
            continue
        if before["status"] != "blocked" and after["status"] == "blocked":
            blocking += 1
        out_teams.append({"team_id": str(t.get("team_id") or ""), "name": str(t.get("name") or ""),
                          "before": before["status"], "after": after["status"],
                          "issues": [dict(i, agent_key=r["agent_key"], name=r["name"])
                                     for r in after["members"] for i in r["issues"]]})
    return {"ok": True, "before": dict(old_main or {}), "after": dict(new_main or {}), "agents": out_agents,
            "teams": out_teams, "blocking": blocking}


# ---- runtime errors -----------------------------------------------------------------------------------------------

_RUNTIME_PATTERNS = (
    (QUOTA_OR_RATE_LIMIT, re.compile(r"\b429\b|rate.?limit|quota|usage limit|too many requests|hết lượt|"
                                     r"resource.?exhausted|overloaded", re.I)),
    (AUTH_MISSING, re.compile(r"\b401\b|\b403\b|unauthori[sz]ed|forbidden|not logged in|log ?in again|sign ?in|"
                              r"invalid.{0,12}(api )?key|no api key|mất đăng nhập|chưa đăng nhập|chưa có khoá|"
                              r"authentication", re.I)),
    (MODEL_INVALID, re.compile(r"model.{0,40}(not found|does not exist|not supported|unknown|invalid)|"
                               r"(unknown|invalid|unsupported) model|model_not_found", re.I)),
    (NETWORK, re.compile(r"connection (refused|reset|error|aborted)|connecterror|getaddrinfo|name or service|"
                         r"network is unreachable|econn|enotfound|dns|ssl|timed? ?out|timeout|\b50[234]\b|\b52[0-9]\b",
                         re.I)),
)


def classify_runtime_error(text: Any, *, kind: str = "", stage: str = "") -> str:
    """Stable code for an engine error. `kind`: team_runner outcome kind when known. Pre-engine stages
    (resolve/preflight/build/capability) default to build_failed; an unrecognised error after the engine started
    returns "" so the caller keeps its own outcome kind instead of a made-up code."""
    k = normalize_code(kind)
    if k in RETRYABLE:
        return k
    s = str(text or "")
    for code, pat in _RUNTIME_PATTERNS:
        if pat.search(s):
            return code
    if str(stage or "") in ("resolve", "preflight", "build", "capability"):
        return BUILD_FAILED
    return ""
