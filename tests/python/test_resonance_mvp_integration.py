"""Resonance M1: một lượt engine qua đường thật của Javis, trả receipt do host quan sát được.

Hai phần, báo cáo TÁCH RIÊNG:
  1. Engine giả (luôn chạy, CI chạy): kiểm luồng run_once và bộ chọn engine chỉ chữ.
  2. Pilot thật (chỉ khi bật JAVIS_RESONANCE_PILOT=1): gọi engine việc nền đang chọn qua
     main._resonance_engine, trên dữ liệu mô phỏng, trong JAVIS_STATE_DIR tạm.

    python tests/run.py resonance_mvp_integration -v

Pilot thật cần thêm JAVIS_RESONANCE_PILOT_SETTINGS = đường dẫn settings.json thật. Test CHỈ
đọc khối model.auxiliary / model.main / model.engine / model.claude_model từ file đó (không
đọc khoá), chép vào settings.json của thư mục tạm. Không ghi gì vào state thật.
JAVIS_RESONANCE_PILOT_CALLS (mặc định 1, trần 5) giới hạn số lượt gọi model.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import types
from pathlib import Path

PILOT = os.environ.get("JAVIS_RESONANCE_PILOT") == "1"
_STATE = tempfile.mkdtemp(prefix="javis-resonance-m1-")
os.environ["JAVIS_STATE_DIR"] = _STATE

if PILOT:
    src = os.environ.get("JAVIS_RESONANCE_PILOT_SETTINGS", "")
    if not src or not Path(src).is_file():
        print("FAIL pilot: thiếu JAVIS_RESONANCE_PILOT_SETTINGS trỏ tới settings.json thật")
        sys.exit(1)
    live = json.loads(Path(src).read_text(encoding="utf-8"))
    m = live.get("model") or {}
    # Chỉ các ô CHỌN engine. Không chép khoá: engine Claude/Codex dùng đăng nhập của CLI.
    keep = {k: m[k] for k in ("auxiliary", "main", "engine", "claude_model") if k in m}
    Path(_STATE, "settings.json").write_text(json.dumps({"model": keep}, ensure_ascii=False),
                                              encoding="utf-8", newline="\n")

import aux_engine  # noqa: E402
import resonance as R  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ───────────────────────────── engine giả ─────────────────────────────

class FakeEngine:
    def __init__(self, events, available=True, delay=0.0):
        self.events = events
        self.available = available
        self.delay = delay
        self.queries = 0
        self.max_wall_s = None

    def is_available(self):
        return self.available

    async def query(self, prompt):
        self.queries += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        for ev in self.events:
            yield ev


def make_deps(engine, calls=5, info=None, **kw):
    built = {"n": 0}

    def factory(system_prompt, tag):
        built["n"] += 1
        return engine, dict(info or {"provider": "fake", "model": "fake-1"})
    deps = R.GoalDeps(engine_factory=factory, budget=R.CallBudget(calls), **kw)
    return deps, built


def goal_in(tmp):
    return R.GoalRecord(id="g_test", brain_id="b1", owner="javis", revision=3, output_root=str(tmp))


def run(deps, goal, aid, prompt="Viết ba gạch đầu dòng."):
    return asyncio.run(deps.run_once(goal, prompt, aid))


# 1. Thành công: host ghi, host tự băm, usage lấy từ final của Claude SDK
tmp = Path(tempfile.mkdtemp(prefix="res-out-"))
eng = FakeEngine([{"type": "final", "content": "- một\n- hai\n- ba", "tokens_in": 120, "tokens_out": 30,
                   "cost_usd": 0.0, "duration_ms": 900}])
deps, built = make_deps(eng)
r = run(deps, goal_in(tmp), "act_001")
f = tmp / "act_001.md"
import hashlib  # noqa: E402
check("thành công: status succeeded", r.status == "succeeded")
check("thành công: host đã ghi file đầu ra", f.is_file() and f.read_text(encoding="utf-8").startswith("- một"))
check("thành công: sha256 khớp đúng byte trên đĩa", r.output_sha256 == hashlib.sha256(f.read_bytes()).hexdigest())
check("thành công: file LF, không CRLF", b"\r" not in f.read_bytes())
check("thành công: usage lấy từ final", r.usage and r.usage["tokens_in"] == 120 and r.usage["tokens_out"] == 30)
check("thành công: ghim goal và revision", r.goal_id == "g_test" and r.revision == 3)
check("thành công: ghi engine thật sự chạy", r.engine.get("provider") == "fake")
check("thành công: đã giữ chỗ đúng 1 lượt", deps.budget.used == 1)
check("thành công: đặt trần wall-clock lên engine", eng.max_wall_s == deps.max_wall_s)
check("thành công: receipt ra dict được", json.dumps(r.to_dict(), ensure_ascii=False))

# 2. Chạy lại cùng action_id: không gọi model lần hai, không ghi đè
r2 = run(deps, goal_in(tmp), "act_001")
check("lặp action_id: cancelled action_exists", r2.status == "cancelled" and r2.error_code == "action_exists")
check("lặp action_id: model chỉ được gọi một lần", eng.queries == 1)
check("lặp action_id: không tốn thêm lượt", deps.budget.used == 1)

# 3. Usage không đo được thì là None, không phải 0
tmp3 = Path(tempfile.mkdtemp(prefix="res-out-"))
deps3, _ = make_deps(FakeEngine([{"type": "final", "content": "xong"}]))
r3 = run(deps3, goal_in(tmp3), "act_003")
check("usage không có: None chứ không phải 0", r3.status == "succeeded" and r3.usage is None)

# 4. Usage từ sự kiện của engine API
deps4, _ = make_deps(FakeEngine([{"type": "usage", "input": 50, "output": 7, "cost": 0.0001},
                                 {"type": "final", "content": "xong"}]))
r4 = run(deps4, goal_in(Path(tempfile.mkdtemp())), "act_004")
check("usage engine API: cộng đúng", r4.usage and r4.usage["tokens_in"] == 50 and r4.usage["cost_usd"] == 0.0001)

# 5. Hết hạn mức: không dựng engine, không gọi model
eng5 = FakeEngine([{"type": "final", "content": "x"}])
deps5, built5 = make_deps(eng5, calls=0)
r5 = run(deps5, goal_in(Path(tempfile.mkdtemp())), "act_005")
check("hết lượt: cancelled budget_exhausted", r5.status == "cancelled" and r5.error_code == "budget_exhausted")
check("hết lượt: không dựng engine, không gọi model", built5["n"] == 0 and eng5.queries == 0)


def fail_case(name, events, code, called=True, **kw):
    t = Path(tempfile.mkdtemp(prefix="res-out-"))
    d, _ = make_deps(FakeEngine(events, **kw))
    rr = run(d, goal_in(t), "act_fail")
    check(f"{name}: failed {code}", rr.status == "failed" and rr.error_code == code)
    check(f"{name}: không có file đầu ra", not any(t.iterdir()))
    # Giữ chỗ trước, đối soát sau: model đã được gọi thì tính một lượt, chưa gọi thì trả chỗ lại.
    check(f"{name}: hạn mức {'tính 1 lượt' if called else 'được trả lại'}", d.budget.used == (1 if called else 0))
    return rr


fail_case("engine báo lỗi", [{"type": "error", "content": "hết lượt gói"}], "engine_error")
fail_case("engine mất đăng nhập trả final", [{"type": "final", "content": "Not logged in · Please run /login"}],
          "engine_auth")
fail_case("đua làm mới token", [{"type": "final", "content": "x", "dua_token": True}], "engine_session_race")
rr = fail_case("gọi công cụ trong lượt chỉ chữ",
               [{"type": "tool_call", "name": "Write", "input": {}}, {"type": "final", "content": "đã ghi"}],
               "tool_call_in_text_only")
check("gọi công cụ: đếm được số lần", rr.tool_calls_observed == 1)
fail_case("trả rỗng", [{"type": "final", "content": "   "}], "empty_output")
fail_case("không có final", [{"type": "usage", "input": 1, "output": 0}], "empty_output")
fail_case("engine chưa sẵn sàng", [{"type": "final", "content": "x"}], "engine_unavailable", called=False,
          available=False)

# 6. Factory báo blocked thì không chạy gì, và không mất lượt
tb = Path(tempfile.mkdtemp())
db = R.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "antigravity không tắt được công cụ"}),
                budget=R.CallBudget(2))
rb = run(db, goal_in(tb), "act_blk")
check("factory blocked: failed engine_blocked kèm lý do",
      rb.status == "failed" and rb.error_code == "engine_blocked" and "antigravity" in rb.error_detail)
check("factory blocked: trả lại chỗ đã giữ", db.budget.used == 0)


def boom(s, t):
    raise RuntimeError("không dựng được")


de = R.GoalDeps(engine_factory=boom, budget=R.CallBudget(2))
re_ = run(de, goal_in(Path(tempfile.mkdtemp())), "act_boom")
check("factory ném lỗi: failed engine_build, trả lại chỗ", re_.error_code == "engine_build" and de.budget.used == 0)

# 7. Quá trần thời gian
tt = Path(tempfile.mkdtemp())
dt, _ = make_deps(FakeEngine([{"type": "final", "content": "muộn"}], delay=0.5), max_wall_s=0, wall_grace_s=0.05)
rt = run(dt, goal_in(tt), "act_slow")
check("quá giờ: failed timeout, không ghi", rt.status == "failed" and rt.error_code == "timeout" and not any(tt.iterdir()))

# 8. Vùng ghi và action_id
dsc, bsc = make_deps(FakeEngine([{"type": "final", "content": "x"}]))
rs = run(dsc, R.GoalRecord("g", "b", "javis", 1, str(Path(_STATE) / "khong-ton-tai")), "act_scope")
check("vùng ghi chưa cấp: cancelled output_scope", rs.status == "cancelled" and rs.error_code == "output_scope")
ri = run(dsc, goal_in(Path(tempfile.mkdtemp())), "../../thoat")
check("action_id lạ: cancelled invalid_action_id", ri.status == "cancelled" and ri.error_code == "invalid_action_id")
check("vùng ghi / id sai: không dựng engine", bsc["n"] == 0)


# ─────────────── bộ chọn engine chỉ chữ, chạy trên aux_engine thật ───────────────

def fake_cli(allowed_tools=("javis_reply_policy_khong_cong_cu",)):
    # Giống engine Claude của _reply_policy_sandbox_engine: allowed_tools có giá trị thì cổng can_use_tool
    # từ chối mọi công cụ. Đó là cơ chế chỉ chữ duy nhất bộ chọn tin cho mắt Claude.
    return types.SimpleNamespace(system_prompt="s", javis_vault=None, javis_mode="suggest", tag="resonance",
                                 model=None, cwd=None, allowed_tools=list(allowed_tools) if allowed_tools else None)


CLAUDE = {"provider": "anthropic-cli", "model": "sonnet"}

# Claude được chọn, máy có key OpenRouter: swap dựng chuỗi [Claude, OpenRouter free]. Phải giữ đúng Claude.
base = fake_cli()
s_or = {"model": {"auxiliary": CLAUDE, "main": {"provider": "anthropic-cli", "model": "opus"},
                  "openrouter_key": "sk-or-gia"}}
sw = aux_engine.strip_tools(aux_engine.swap(base, mode="suggest", tag="resonance", spec=CLAUDE, settings=s_or), base)
check("swap thật dựng chuỗi dự phòng khi có key OpenRouter", isinstance(sw, aux_engine._FallbackChain))
e1, i1 = R.pick_text_only_link(sw, base, CLAUDE, aux_engine._FallbackChain)
check("chọn: giữ đúng Claude, bỏ mắt dự phòng", e1 is base and i1["provider"] == "anthropic-cli"
      and i1["fallback_links_dropped"] >= 1)
check("chọn: ghi model đã chọn", i1["model"] == "sonnet")

# Không có mắt dự phòng: swap trả nguyên engine
base2 = fake_cli()
sw2 = aux_engine.strip_tools(aux_engine.swap(base2, mode="suggest", tag="resonance", spec=CLAUDE,
                                             settings={"model": {"auxiliary": CLAUDE}}), base2)
e2, i2 = R.pick_text_only_link(sw2, base2, CLAUDE, aux_engine._FallbackChain)
check("chọn: không chuỗi thì giữ nguyên Claude", e2 is base2 and i2["fallback_links_dropped"] == 0)

# Chọn Antigravity: strip_tools không tắt được công cụ của agy nên lùi về Claude. Phải chặn, không chạy thay.
base3 = fake_cli()
AGY = {"provider": "antigravity-cli", "model": ""}
sw3 = aux_engine.strip_tools(aux_engine.swap(base3, mode="suggest", tag="resonance", spec=AGY,
                                             settings={"model": {"auxiliary": AGY}}), base3)
e3, i3 = R.pick_text_only_link(sw3, base3, AGY, aux_engine._FallbackChain)
check("chọn: Antigravity bị lùi về Claude thì chặn", e3 is None and "không tự đổi provider" in i3.get("blocked", ""))

# Chọn OpenRouter có key: mắt đầu là engine API đã tắt công cụ
base4 = fake_cli()
ORS = {"provider": "openrouter", "model": "x/y"}
sw4 = aux_engine.strip_tools(aux_engine.swap(base4, mode="suggest", tag="resonance", spec=ORS,
                                             settings={"model": {"auxiliary": ORS, "openrouter_key": "sk-or-gia"}}),
                             base4)
e4, i4 = R.pick_text_only_link(sw4, base4, ORS, aux_engine._FallbackChain)
check("chọn: OpenRouter giữ mắt API, không lùi về Claude", e4 is not None and e4 is not base4
      and i4["provider"] == "openrouter" and getattr(e4, "no_tools", False) is True)


# Mắt Claude mà KHÔNG có allowed_tools thì không có gì chặn công cụ: không được khai là chỉ chữ.
base_open = fake_cli(allowed_tools=None)
e7, i7 = R.pick_text_only_link(base_open, base_open, CLAUDE)
check("chọn: Claude không có cổng chặn công cụ thì chặn", e7 is None and "chỉ chữ" in i7.get("blocked", ""))

# Review PR #566 P1-2: Codex / Grok còn công cụ NATIVE (strip_tools chỉ gỡ MCP). Dựng bằng builder THẬT qua
# aux_engine.swap; chỉ giả availability để không cần CLI trên máy, KHÔNG chạy CLI.
_avail_that = aux_engine.availability
aux_engine.availability = lambda spec, settings=None: (True, "")
try:
    import claude_cli  # noqa: E402
    import grok_cli  # noqa: E402
    CODEX = {"provider": "openai-oauth", "model": "gpt-5"}
    for sandbox_env in ("auto", "off"):
        os.environ["JAVIS_CODEX_SANDBOX"] = sandbox_env
        bc = fake_cli()
        swc = aux_engine.strip_tools(aux_engine.swap(bc, mode="suggest", tag="resonance", spec=CODEX,
                                                     settings={"model": {"auxiliary": CODEX}}), bc)
        first_c = swc._all()[0] if isinstance(swc, aux_engine._FallbackChain) else swc
        check(f"Codex thật (sandbox={sandbox_env}): builder dựng đúng CodexCLI", isinstance(first_c, claude_cli.CodexCLI))
        if sandbox_env == "off":
            check("Codex thật (sandbox=off): sandbox thật sự là None", first_c.sandbox is None)
        ec, ic = R.pick_text_only_link(swc, bc, CODEX, aux_engine._FallbackChain)
        check(f"chọn: Codex (sandbox={sandbox_env}) bị chặn trước khi gọi vì còn công cụ native",
              ec is None and "công cụ native" in ic.get("blocked", "") and ic.get("text_only") is False)
    os.environ.pop("JAVIS_CODEX_SANDBOX", None)
    GROK = {"provider": "grok-cli", "model": ""}
    bg = fake_cli()
    swg = aux_engine.strip_tools(aux_engine.swap(bg, mode="suggest", tag="resonance", spec=GROK,
                                                 settings={"model": {"auxiliary": GROK}}), bg)
    first_g = swg._all()[0] if isinstance(swg, aux_engine._FallbackChain) else swg
    check("Grok thật: builder dựng đúng GrokCLI", isinstance(first_g, grok_cli.GrokCLI))
    eg, ig = R.pick_text_only_link(swg, bg, GROK, aux_engine._FallbackChain)
    check("chọn: Grok bị chặn trước khi gọi vì còn công cụ native",
          eg is None and "công cụ native" in ig.get("blocked", ""))
    # Engine bị chặn thì run_once không gọi gì và trả lại chỗ đã giữ
    dcx = R.GoalDeps(engine_factory=lambda s, t: R.pick_text_only_link(swg, bg, GROK, aux_engine._FallbackChain),
                     budget=R.CallBudget(1))
    rcx = run(dcx, goal_in(Path(tempfile.mkdtemp())), "act_grok")
    check("run_once với Grok: failed engine_blocked, không tốn lượt",
          rcx.error_code == "engine_blocked" and dcx.budget.used == 0)
finally:
    aux_engine.availability = _avail_that
    os.environ.pop("JAVIS_CODEX_SANDBOX", None)


# ─────────── Review PR #566 P1-1: Claude kết thúc LỖI nhưng vẫn có chữ (đi qua mapper SDK thật) ───────────
import claude_sdk_engine  # noqa: E402
from claude_agent_sdk import ResultMessage  # noqa: E402


def sdk_result(is_error, subtype, result, usage=None, cost=0.01):
    evs, _sid = claude_sdk_engine.map_message(ResultMessage(
        subtype=subtype, duration_ms=1200, duration_api_ms=900, is_error=is_error, num_turns=1,
        session_id="s_m1", total_cost_usd=cost, usage=usage or {"input_tokens": 100, "output_tokens": 5},
        result=result))
    return evs


t_err = Path(tempfile.mkdtemp(prefix="res-out-"))
d_err, _ = make_deps(FakeEngine(sdk_result(True, "error_during_execution",
                                           "You've hit your limit; try again after the reset.")))
r_err = run(d_err, goal_in(t_err), "act_sdkerr")
check("SDK lỗi có chữ: failed engine_result_error", r_err.status == "failed" and r_err.error_code == "engine_result_error")
check("SDK lỗi có chữ: không ghi file đầu ra", not any(t_err.iterdir()))
check("SDK lỗi có chữ: vẫn giữ usage của lượt lỗi", r_err.usage and r_err.usage.get("tokens_in") == 100)
check("SDK lỗi có chữ: model đã gọi nên tính 1 lượt", d_err.budget.used == 1)
t_ok = Path(tempfile.mkdtemp(prefix="res-out-"))
d_ok, _ = make_deps(FakeEngine(sdk_result(False, "success", "# Việc đang dở\n- một")))
r_ok = run(d_ok, goal_in(t_ok), "act_sdkok")
check("SDK thành công qua mapper thật: succeeded", r_ok.status == "succeeded" and (t_ok / "act_sdkok.md").is_file())
check("SDK thành công: usage đúng từ mapper thật", r_ok.usage and r_ok.usage["tokens_in"] == 100
      and r_ok.usage["tokens_out"] == 5)


# ─────────── Review PR #566 P2-1: chuẩn hoá usage, thiếu là thiếu ───────────
u_g = R._usage_from(grok_cli.GrokCLI._usage({"input_tokens": 9028, "output_tokens": 54}), None)
check("usage Grok thật (input_tokens/output_tokens): đọc đúng", u_g and u_g["tokens_in"] == 9028 and u_g["tokens_out"] == 54)
u_c = R._usage_from({"type": "final", "content": "x", "cost_usd": 0.02}, None)
check("final chỉ có cost: không bịa token bằng 0", u_c == {"cost_usd": 0.02})
u_n = R._usage_from({"type": "final", "content": "x"}, None)
check("final không có số liệu: usage vẫn None", u_n is None)


# ─────────── Review PR #566 P2-2: đầu ra quá dài không bị cắt âm thầm ───────────
t_big = Path(tempfile.mkdtemp(prefix="res-out-"))
d_big, _ = make_deps(FakeEngine([{"type": "final", "content": "x" * R.OUTPUT_MAX_CHARS + "IMPORTANT_TAIL",
                                  "tokens_in": 10, "tokens_out": 9}]))
r_big = run(d_big, goal_in(t_big), "act_big")
check("đầu ra quá dài: failed output_too_large", r_big.status == "failed" and r_big.error_code == "output_too_large")
check("đầu ra quá dài: không công bố file bị cắt", not any(t_big.iterdir()))
check("đầu ra quá dài: vẫn giữ usage", r_big.usage and r_big.usage["tokens_out"] == 9)


# ───────────────────────────── pilot thật ─────────────────────────────

if PILOT:
    import main  # noqa: E402  - nạp SAU khi JAVIS_STATE_DIR tạm đã đặt
    calls = max(1, min(int(os.environ.get("JAVIS_RESONANCE_PILOT_CALLS", "1") or 1), 5))
    out_root = Path(tempfile.mkdtemp(prefix="res-pilot-"))
    goal = R.GoalRecord(id="g_pilot", brain_id="pilot", owner="javis", revision=1, output_root=str(out_root))
    deps = R.GoalDeps(engine_factory=main._resonance_engine, budget=R.CallBudget(calls), max_wall_s=300)
    prompt = ("Dữ liệu mô phỏng, không phải việc thật. Danh sách việc đang dở: (1) viết ghi chú họp thứ Hai, "
              "(2) gom hoá đơn tháng 9, (3) trả lời email của nhà cung cấp A. Hãy viết một ghi chú Markdown "
              "có tiêu đề '# Việc đang dở' và đúng ba gạch đầu dòng, mỗi gạch một việc, kèm một bước kế tiếp ngắn.")
    receipt = asyncio.run(deps.run_once(goal, prompt, "pilot_m1_001"))
    replay = asyncio.run(deps.run_once(goal, prompt, "pilot_m1_001"))
    out_file = Path(receipt.output_ref) if receipt.output_ref else None
    out_bytes = out_file.read_bytes() if out_file and out_file.is_file() else b""
    out_text = out_bytes.decode("utf-8") if out_bytes else ""
    disk_sha = hashlib.sha256(out_bytes).hexdigest() if out_bytes else None
    lines = [ln for ln in out_text.splitlines() if ln.strip()]
    import subprocess  # noqa: E402
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True,
                              timeout=10).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "server"], cwd=str(ROOT),
                                    capture_output=True, text=True, timeout=10).stdout.strip())
    except Exception:  # noqa: BLE001
        head, dirty = "", None

    def _no_path(d):
        # Bỏ đường dẫn cá nhân: chỉ giữ tên file đầu ra.
        d = dict(d)
        if d.get("output_ref"):
            d["output_ref"] = Path(d["output_ref"]).name
        return d
    rep = {"commit": head, "server_dirty": dirty, "prompt": prompt,
           "receipt": _no_path(receipt.to_dict()), "replay_same_action": _no_path(replay.to_dict()),
           "budget": {"max_calls": deps.budget.max_calls, "used": deps.budget.used},
           "disk_sha256": disk_sha, "output": out_text}
    print("PILOT_REPORT " + json.dumps(rep, ensure_ascii=False))
    outp = os.environ.get("JAVIS_RESONANCE_PILOT_OUT")
    if outp:
        Path(outp).write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    check("pilot: receipt succeeded", receipt.status == "succeeded")
    check("pilot: chạy đúng provider đã chọn",
          receipt.engine.get("provider") == receipt.engine.get("requested_provider"))
    check("pilot: SHA-256 tính lại từ byte trên đĩa khớp receipt", bool(disk_sha) and disk_sha == receipt.output_sha256)
    check("pilot: đầu ra đúng cấu trúc yêu cầu (tiêu đề + đúng 3 gạch đầu dòng)",
          bool(lines) and lines[0].strip() == "# Việc đang dở"
          and sum(1 for ln in lines if ln.lstrip().startswith("- ")) == 3)
    check("pilot: không gọi công cụ", receipt.tool_calls_observed == 0)
    check("pilot: chạy lại cùng action_id không gọi model", replay.error_code == "action_exists"
          and deps.budget.used == 1)
else:
    print("pilot thật: bỏ qua (đặt JAVIS_RESONANCE_PILOT=1 để chạy)")

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
