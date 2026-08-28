"""Bộ não thứ 9: Gemini CLI (đăng nhập Google, không cần API key).

    python tests/run.py gemini_cli      (KHÔNG mạng, KHÔNG cần cài gemini)

Chỗ dễ hỏng của một driver CLI không nằm ở "gọi được hay không" - nó nằm ở bốn thứ chỉ lộ ra
khi đã chạy thật một thời gian, nên test này canh đúng bốn thứ đó:

1. **Dịch sự kiện.** `gemini -o stream-json` phát JSONL riêng của nó (init/message/tool_use/
   tool_result/error/result). Dịch sai một loại là mất câu trả lời, hoặc mất mạch hội thoại,
   hoặc lượt nào cũng đỏ vì một cảnh báo vặt.
2. **Mức quyền.** Ba mức của Javis phải xuống đúng `--approval-mode`. Mức `suggest` mà không
   ra `plan` thì "chỉ đọc" chỉ còn là một lời hứa trong prompt, và loop nền ghi đè file thật.
3. **Không đăng nhập.** Ca thường gặp nhất. CLI báo bằng một câu dài về biến môi trường, phát
   ra STDERR, exit 41, KHÔNG có dòng JSON nào - phải thành một câu người dùng làm theo được
   chứ không phải bong bóng rỗng.
4. **Cô lập theo brain.** MCP hub ghi vào `.gemini/settings.json` của brain, không đụng file
   HOME của người dùng, và không xoá mất phần cấu hình họ đã có trong đó.

Test dựng một `gemini` GIẢ bằng script Python, nên chạy được ở CI không có Node.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-gemtest-")

import aux_engine        # noqa: E402
import gemini_cli        # noqa: E402
import limit_learner     # noqa: E402
import model_limits      # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def chay(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ============================================================
# 1. Mức quyền: ba mức của Javis -> nấc duyệt của CLI
# ============================================================
check("suggest -> plan (CHỈ ĐỌC do CLI cưỡng chế, không phải lời hứa trong prompt)",
      gemini_cli.approval_cho_mode("suggest") == "plan")
check("auto -> auto_edit", gemini_cli.approval_cho_mode("auto") == "auto_edit")
check("full -> yolo", gemini_cli.approval_cho_mode("full") == "yolo")
for xau in ("", None, "FULL_QUYEN", "yolo", "bậy bạ"):
    if xau == "yolo":
        continue
    check(f"CANARY: mode lạ ({xau!r}) rơi về nấc CHẶT NHẤT, không phải toàn quyền",
          gemini_cli.approval_cho_mode(xau) == "plan")
check("viết hoa vẫn nhận", gemini_cli.approval_cho_mode("Full") == "yolo")


# ============================================================
# 2. argv dựng ra phải đúng hợp đồng của CLI thật
# ============================================================
_g = gemini_cli.GeminiCLI(cwd="/tmp", model="gemini-2.5-pro")
_g.cli_path = "/fake/gemini"
_g.approval_mode = "plan"
_argv = _g._build_args()
check("có -o stream-json (không có thì không đọc được sự kiện nào)",
      "-o" in _argv and _argv[_argv.index("-o") + 1] == "stream-json")
check("có --approval-mode đúng nấc",
      "--approval-mode" in _argv and _argv[_argv.index("--approval-mode") + 1] == "plan")
check("CANARY: có --skip-trust - thiếu nó là CLI hỏi 'tin thư mục này không' rồi treo im",
      "--skip-trust" in _argv)
check("lượt đầu MỞ mạch bằng --session-id (CLI từ chối id đã tồn tại)",
      "--session-id" in _argv and "--resume" not in _argv)
check("id mở mạch đúng dạng UUID", len(_argv[_argv.index("--session-id") + 1]) == 36)
check("model đi qua -m", "-m" in _argv and _argv[_argv.index("-m") + 1] == "gemini-2.5-pro")
check("CANARY: prompt KHÔNG nằm trong argv (Windows chặn dòng lệnh ở 32767 ký tự)",
      _argv[-2:] == ["-p", ""])

_g.session_id = "11111111-2222-3333-4444-555555555555"
_argv2 = _g._build_args()
check("có mạch cũ thì --resume, không --session-id nữa",
      "--resume" in _argv2 and "--session-id" not in _argv2)
check("resume đúng id", _argv2[_argv2.index("--resume") + 1] == _g.session_id)


# ============================================================
# 3. Dịch sự kiện stream-json -> hợp đồng của Javis
# ============================================================
def _gia(dong_ra, ma=0, stderr=""):
    """Dựng một `gemini` giả in ra đúng những dòng mình muốn."""
    d = Path(tempfile.mkdtemp(prefix="javis-fakegem-"))
    p = d / "gemini"
    body = json.dumps(dong_ra)
    p.write_text(
        "#!/usr/bin/env python3\n"
        "import sys, json\n"
        "sys.stdin.read()\n"          # phải nuốt stdin, không thì driver kẹt lúc ghi
        f"for l in {body}:\n"
        "    print(l, flush=True)\n"
        f"sys.stderr.write({stderr!r})\n"
        f"sys.exit({ma})\n",
        encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(p)


def _chay_gia(dong_ra, ma=0, stderr="", prompt="xin chào"):
    g = gemini_cli.GeminiCLI(cwd="/tmp")
    g.cli_path = _gia(dong_ra, ma, stderr)

    async def _go():
        return [ev async for ev in g.query(prompt)]
    return chay(_go()), g


_DONG = [
    json.dumps({"type": "init", "timestamp": "t", "session_id": "abc-123", "model": "gemini-2.5-pro"}),
    json.dumps({"type": "message", "role": "user", "content": "xin chào"}),
    json.dumps({"type": "tool_use", "tool_name": "read_file", "tool_id": "t1",
                "parameters": {"path": "a.md"}}),
    json.dumps({"type": "tool_result", "tool_id": "t1", "status": "success", "output": "nội dung"}),
    json.dumps({"type": "message", "role": "assistant", "content": "Chào ", "delta": True}),
    json.dumps({"type": "message", "role": "assistant", "content": "anh.", "delta": True}),
    json.dumps({"type": "error", "severity": "warning", "message": "extension abc thiếu"}),
    json.dumps({"type": "result", "status": "success",
                "stats": {"total_tokens": 300, "input_tokens": 250, "output_tokens": 50,
                          "cached": 10, "duration_ms": 900, "tool_calls": 1}}),
]
_evs, _g3 = _chay_gia(_DONG)
_loai = [e["type"] for e in _evs]
_final = next((e for e in _evs if e["type"] == "final"), None)
check("mảnh chữ của assistant được GHÉP lại thành một câu trả lời",
      _final is not None and _final["content"] == "Chào anh.", _final)
check("CANARY: tin của role=user KHÔNG lọt vào câu trả lời (CLI dội lại prompt của mình)",
      _final is not None and "xin chào" not in _final["content"])
check("tool_use -> tool_call kèm tên công cụ",
      any(e["type"] == "tool_call" and e.get("name") == "read_file" for e in _evs))
check("tool_result đi qua được", any(e["type"] == "tool_result" for e in _evs))
check("stats -> usage với token vào/ra",
      any(e["type"] == "usage" and e.get("input_tokens") == 250 for e in _evs))
check("CANARY: severity=warning KHÔNG thành lỗi (không thì lượt nào cũng đỏ)",
      "error" not in _loai, _loai)
check("session_id từ `init` được giữ để lượt sau resume", _g3.session_id == "abc-123")

# result kèm status=error
_evs2, _ = _chay_gia([
    json.dumps({"type": "init", "session_id": "x"}),
    json.dumps({"type": "result", "status": "error",
                "error": {"type": "ApiError", "message": "model bận"},
                "stats": {"input_tokens": 5, "output_tokens": 0, "total_tokens": 5}}),
])
check("result status=error -> sự kiện error",
      any(e["type"] == "error" and "model bận" in e.get("content", "") for e in _evs2))
check("và KHÔNG bịa thêm một câu trả lời rỗng",
      not any(e["type"] == "final" for e in _evs2))

# severity=error thật
_evs3, _ = _chay_gia([json.dumps({"type": "error", "severity": "error", "message": "hỏng thật"})])
check("severity=error -> lỗi thật",
      any(e["type"] == "error" and "hỏng thật" in e.get("content", "") for e in _evs3))


# ============================================================
# 4. Chưa đăng nhập: stderr + exit 41, KHÔNG có JSON nào
# ============================================================
_LOI_THAT = ("Please set an Auth method in your /root/.gemini/settings.json or specify one of "
             "the following environment variables before running: GEMINI_API_KEY, "
             "GOOGLE_GENAI_USE_VERTEXAI, GOOGLE_GENAI_USE_GCA")
_evs4, _ = _chay_gia([], ma=41, stderr=_LOI_THAT)
_loi4 = next((e for e in _evs4 if e["type"] == "error"), None)
check("CANARY: không đăng nhập -> câu LÀM THEO ĐƯỢC, không phải nguyên văn tiếng Anh",
      _loi4 is not None and "Login with Google" in _loi4["content"], _loi4)
check("và không dán nguyên câu về biến môi trường vào mặt người dùng",
      _loi4 is not None and "GOOGLE_GENAI_USE_VERTEXAI" not in _loi4["content"])
check("KHÔNG kèm thêm một 'final' rỗng", not any(e["type"] == "final" for e in _evs4))

_evs5, _ = _chay_gia([], ma=3, stderr="một lỗi lạ nào đó")
check("lỗi lạ thì giữ nguyên văn để còn tra được",
      any("một lỗi lạ nào đó" in e.get("content", "") for e in _evs5))

# --- Google ngắt hạng cá nhân (18/06/2026) -----------------------------------
# Chủ repo gặp thật 2026-08-13: chat ra "(không có nội dung trả về)" trong khi log đầy
# IneligibleTierError. Ba đường lỗi khác nhau đều phải về CÙNG một câu tiếng Việt, vì cả ba
# đều gặp trong thực tế tuỳ bản CLI: stderr + exit khác 0, sự kiện `error`, và `result` với
# status=error.
_LOI_TIER = ("Error authenticating: IneligibleTierError: This client is no longer supported "
             "for Gemini Code Assist for individuals. To continue using Gemini, please migrate "
             "to the Antigravity suite of products: https://antigravity.google")

_evs_t1, _ = _chay_gia([], ma=1, stderr=_LOI_TIER)
_l1 = next((e for e in _evs_t1 if e["type"] == "error"), None)
check("CANARY: IneligibleTierError qua stderr -> nói thẳng Google đã ngắt, không dán stack trace",
      _l1 is not None and "18/06/2026" in _l1["content"] and "IneligibleTierError" not in _l1["content"],
      _l1)
check("và chỉ sang đường còn dùng được",
      _l1 is not None and "OpenRouter" in _l1["content"] and "Antigravity CLI" in _l1["content"])

_evs_t2, _ = _chay_gia([json.dumps({"type": "error", "severity": "warning",
                                    "message": _LOI_TIER})])
check("CANARY: cùng lỗi đó gắn severity=warning vẫn PHẢI hiện - lọc warning trước là nuốt mất",
      any(e["type"] == "error" and "18/06/2026" in e.get("content", "") for e in _evs_t2), _evs_t2)

_evs_t3, _ = _chay_gia([json.dumps({"type": "result", "status": "error",
                                    "error": {"message": _LOI_TIER}, "stats": {}})])
check("và qua result.status=error cũng ra đúng câu đó",
      any(e["type"] == "error" and "18/06/2026" in e.get("content", "") for e in _evs_t3))

check("nhận diện được cả mã lý do UNSUPPORTED_CLIENT",
      gemini_cli._la_loi_het_cua("reasonCode: 'UNSUPPORTED_CLIENT'") is True)
check("CANARY: lỗi thường KHÔNG bị nhận nhầm thành 'Google đã ngắt'",
      gemini_cli._la_loi_het_cua("ECONNRESET khi gọi API") is False)

# Chạy xong sạch sẽ nhưng câm - phải nói ra chứ không trả bong bóng rỗng.
_evs6, _ = _chay_gia([json.dumps({"type": "result", "status": "success", "stats": {}})])
check("chạy xong mà không có nội dung -> báo lỗi, không im lặng",
      any(e["type"] == "error" for e in _evs6) and not any(e["type"] == "final" for e in _evs6))

# Bản CLI cũ chưa có stream-json thì in chữ thuần - đừng vứt đi.
_evs7, _ = _chay_gia(["câu trả lời chữ thuần"])
check("dòng không phải JSON vẫn được nhận làm câu trả lời",
      any(e["type"] == "final" and "chữ thuần" in e["content"] for e in _evs7))

# Không có CLI trên máy.
async def _gom(g):
    return [ev async for ev in g.query("hỏi gì đó")]


_g8 = gemini_cli.GeminiCLI()
_g8.cli_path = None
_evs8 = chay(_gom(_g8))
check("chưa cài CLI -> báo cách cài, không nổ",
      len(_evs8) == 1 and _evs8[0]["type"] == "error"
      and "npm i -g @google/gemini-cli" in _evs8[0]["content"], _evs8)
check("is_available() nói đúng sự thật", _g8.is_available() is False)


# ============================================================
# 5. Đọc trạng thái đăng nhập từ file (không đẻ tiến trình mỗi lần mở trang)
# ============================================================
_home = Path(tempfile.mkdtemp(prefix="javis-gemhome-"))
(_home / ".gemini").mkdir()
_moi_truong_cu = {k: os.environ.get(k) for k in
                  ("HOME", "USERPROFILE", "GEMINI_API_KEY", "GOOGLE_GENAI_USE_GCA")}
try:
    os.environ["HOME"] = str(_home)
    os.environ["USERPROFILE"] = str(_home)
    for k in ("GEMINI_API_KEY", "GOOGLE_GENAI_USE_GCA"):
        os.environ.pop(k, None)
    _that = gemini_cli.find_gemini_cli
    gemini_cli.find_gemini_cli = lambda: "/fake/gemini"
    try:
        st = gemini_cli.auth_status()
        check("có CLI mà chưa đăng nhập -> chỉ thẳng nút trên trang, không bắt mở terminal",
              st["connected"] is False and "Đăng nhập Google" in st["error"], st)
        (_home / ".gemini" / "oauth_creds.json").write_text(
            json.dumps({"refresh_token": "r", "access_token": "a"}), encoding="utf-8")
        (_home / ".gemini" / "settings.json").write_text(
            json.dumps({"security": {"auth": {"selectedType": "oauth-personal"}}}), encoding="utf-8")
        (_home / ".gemini" / "google_accounts.json").write_text(
            json.dumps({"active": "quy@example.com"}), encoding="utf-8")
        st2 = gemini_cli.auth_status()
        check("có oauth_creds.json -> đã đăng nhập, đọc đúng cách đăng nhập",
              st2["connected"] is True and st2["method"] == "oauth-personal", st2)
        check("lấy được cả email để hiện trên thẻ", st2["email"] == "quy@example.com")

        (_home / ".gemini" / "oauth_creds.json").unlink()
        os.environ["GEMINI_API_KEY"] = "k"
        check("API key trong env cũng tính là đã cấu hình",
              gemini_cli.auth_status()["connected"] is True)
        os.environ.pop("GEMINI_API_KEY")
        os.environ["GOOGLE_GENAI_USE_GCA"] = "1"
        check("GOOGLE_GENAI_USE_GCA=1 (Code Assist) cũng tính",
              gemini_cli.auth_status()["connected"] is True)
    finally:
        gemini_cli.find_gemini_cli = _that

    gemini_cli.find_gemini_cli = lambda: None
    try:
        check("chưa cài CLI -> nói cách cài",
              "npm i -g @google/gemini-cli" in gemini_cli.auth_status()["error"])
        check("và list_models trả None để phía trên biết mà nói lý do",
              gemini_cli.list_models() is None)
    finally:
        gemini_cli.find_gemini_cli = _that
finally:
    for k, v in _moi_truong_cu.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ============================================================
# 6. MCP hub ghi vào BRAIN, không đụng file HOME của người dùng
# ============================================================
_vault = Path(tempfile.mkdtemp(prefix="javis-gembrain-"))
(_vault / ".gemini").mkdir()
(_vault / ".gemini" / "settings.json").write_text(
    json.dumps({"theme": "Dracula", "mcpServers": {"cua_toi": {"command": "x"}}}),
    encoding="utf-8")
_hub = {"httpUrl": "http://127.0.0.1:7777/hub/mcp",
        "headers": {"Authorization": "Bearer T", "X-Javis-Mode": "suggest"},
        "trust": True, "timeout": 20000}
_p = gemini_cli.ghi_mcp_settings(_vault, _hub)
_doc = json.loads(Path(_p).read_text(encoding="utf-8"))
check("ghi vào .gemini/settings.json của BRAIN", Path(_p).parent.parent == _vault)
check("entry javis trỏ đúng hub", _doc["mcpServers"]["javis"]["httpUrl"].endswith("/hub/mcp"))
check("CANARY: GIỮ nguyên cấu hình sẵn có của người dùng trong file đó",
      _doc.get("theme") == "Dracula" and "cua_toi" in _doc["mcpServers"])
check("token nằm trong file thì file phải bị siết quyền",
      (os.stat(_p).st_mode & 0o077) == 0 or os.name == "nt")
gemini_cli.ghi_mcp_settings(_vault, None)
_doc2 = json.loads(Path(_p).read_text(encoding="utf-8"))
check("tắt hub -> gỡ entry javis nhưng KHÔNG đụng phần còn lại",
      "javis" not in _doc2.get("mcpServers", {}) and "cua_toi" in _doc2["mcpServers"])


# ============================================================
# 7. Nối vào Javis: provider, việc nền, hạn mức
# ============================================================
import main   # noqa: E402  - import sau khi STATE_DIR đã trỏ vào thư mục tạm

_defs = {p["id"]: p for p in main.PROVIDER_DEFS}
check("có provider gemini-cli trong danh sách", "gemini-cli" in _defs)
_d = _defs.get("gemini-cli", {})
check("CANARY: kind='cli' - mọi chỗ hỏi 'có phải bộ não gói thuê bao không' đều dựa vào nó",
      _d.get("kind") == "cli")
check("không đòi API key", _d.get("key_field") is None)
check("có sẵn catalog dự phòng nên không bao giờ ra 0 model như ChatGPT từng bị",
      len(_d.get("default_models") or []) >= 3)
check("KHÁC provider `gemini` (API key) - hai thẻ, hai đường tính tiền",
      _defs["gemini"]["kind"] == "api" and _defs["gemini"]["key_field"] == "gemini_api_key")

check("model chính đặt được sang gemini-cli", True)
_cfg = {"model": {}}
main._set_main_model(_cfg, "gemini-cli", "gemini-2.5-pro")
check("và đồng bộ trường engine legacy", _cfg["model"]["engine"] == "gemini-cli")

_prov, _kind, _key, _model = main._chat_provider(
    {"main": {"provider": "gemini-cli", "model": "gemini-2.5-pro"}})
check("_chat_provider trả đúng bộ (prov, kind, key, model)",
      (_prov, _kind, _key, _model) == ("gemini-cli", "cli", "", "gemini-2.5-pro"))

# Việc nền
check("aux_engine biết provider này", aux_engine.GEMINI_CLI == "gemini-cli")
_ok, _vi_sao = aux_engine.availability({"provider": "gemini-cli"})
check("chưa đăng nhập -> việc nền báo TRƯỚC chứ không chết lặng lẽ",
      (_ok is True) or bool(_vi_sao), _vi_sao)


class _CliGia:
    cwd = str(_vault)
    tag = "aux"
    system_prompt = "vai trò"
    javis_vault = str(_vault)
    javis_mode = "suggest"
    model = None


_engine_nen = aux_engine._build_gemini({"provider": "gemini-cli", "model": "gemini-2.5-flash"},
                                       _CliGia(), "suggest", "loop")
check("việc nền mức suggest -> --approval-mode plan (CLI tự chặn ghi)",
      _engine_nen.approval_mode == "plan")
check("việc nền mức full -> yolo",
      aux_engine._build_gemini({"provider": "gemini-cli"}, _CliGia(), "full", "x").approval_mode
      == "yolo")
check("engine nền chạy đúng trong brain", _engine_nen.cwd == str(_vault))

# Hạn mức gói: câu của Google phải dịch được thành câu người đọc
_hit = limit_learner.parse_subscription_limit("You have exhausted your daily quota on this model.",
                                              engine_hint="gemini-cli")
check("nhận ra 'hết lượt hôm nay' của gói Google", _hit is not None and _hit.engine == "gemini-cli")
check("và nói đúng tên gói chứ không phải 'gói thuê bao đang dùng'",
      "Gemini CLI" in model_limits.subscription_blocked_hint(_hit))
check("lỗi backend RESOURCE_EXHAUSTED cũng nhận ra",
      limit_learner.parse_subscription_limit("429 RESOURCE_EXHAUSTED", engine_hint="gemini-cli")
      is not None)
check("CANARY: câu thường KHÔNG bị nhận nhầm là hết hạn mức",
      limit_learner.parse_subscription_limit("hôm nay trời đẹp", engine_hint="gemini-cli") is None)

# Mạch hội thoại: cột riêng, không dùng chung với Codex
import sessions as _sessions   # noqa: E402
_db = Path(tempfile.mkdtemp(prefix="javis-gemsess-")) / "c.db"
_store = _sessions.Store(str(_db)) if hasattr(_sessions, "Store") else None
if _store is not None:
    _sid = _store.get_or_create(None, brain="brain", engine="gemini-cli", model="gemini-2.5-pro")
    _store.set_gemini_session_id(_sid, "uuid-gemini")
    _store.set_codex_thread_id(_sid, "thread-codex")
    _row = _store.get_session(_sid)
    check("CANARY: mạch Gemini và mạch Codex nằm HAI cột khác nhau",
          _row.get("gemini_session_id") == "uuid-gemini"
          and _row.get("codex_thread_id") == "thread-codex")
    _store.clear_gemini_session_id(_sid)
    check("xoá mạch Gemini không đụng mạch Codex",
          not (_store.get_session(_sid).get("gemini_session_id") or "")
          and _store.get_session(_sid).get("codex_thread_id") == "thread-codex")

# Giao diện
_console = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("trang Models có thẻ riêng cho Gemini CLI", 'p.id === "gemini-cli"' in _console)
check("CANARY: thẻ Gemini nằm TRƯỚC nhánh kind==='cli' (nhánh đó là của Claude Code)",
      _console.index('p.id === "gemini-cli"') < _console.index('if (p.kind === "cli")'))
check("CANARY: không hỏi /claude/status hộ Gemini (trạng thái Claude không nói gì về Gemini)",
      'p.id === "anthropic-cli" ? claudeOn' in _console)
check("có nút kiểm tra lại gọi đúng endpoint", '/gemini-cli/check' in _console)
check("thẻ vẫn chỉ cách cài CLI khi máy chưa có",
      "npm install -g @google/gemini-cli" in _console)

_src_main = (SERVER / "main.py").read_text(encoding="utf-8")
check("chat dashboard có nhánh riêng cho gemini-cli", 'elif prov == "gemini-cli":' in _src_main)
check("Telegram cũng có nhánh đó", 'if prov == "gemini-cli":' in _src_main)
check("CANARY: nhãn engine không đội lốt 'cli' của Claude Code",
      _src_main.count('else "gemini-cli" if prov == "gemini-cli"') == 2)

# ============================================================
# 8. Đăng nhập Google NGAY TRÊN DASHBOARD (gemini_oauth)
# ============================================================
import gemini_oauth as _go   # noqa: E402
from urllib.parse import urlparse, parse_qs   # noqa: E402

# CI không cài Node nên KHÔNG có binary `gemini` để moi client OAuth ra. Dùng chính cửa thoát
# bằng biến môi trường - vừa chạy được ở CI, vừa là phép thử cho cái cửa thoát đó.
_GIA_ID = "test-1234.apps.googleusercontent.com"
_GIA_SECRET = "GIA-SECRET"
os.environ["JAVIS_GEMINI_OAUTH_CLIENT_ID"] = _GIA_ID
os.environ["JAVIS_GEMINI_OAUTH_CLIENT_SECRET"] = _GIA_SECRET
check("biến môi trường ghi đè được client (cửa thoát cho bản đóng gói lạ)",
      _go.doc_client() == (_GIA_ID, _GIA_SECRET))

_r = _go.start_login()
_q = parse_qs(urlparse(_r["authorize_url"]).query)
check("link đăng nhập trỏ đúng Google", urlparse(_r["authorize_url"]).netloc == "accounts.google.com")
check("và dùng đúng client đang cấu hình", _q["client_id"][0] == _GIA_ID)

# Máy nào CÓ Gemini CLI thật thì phải moi được client từ bundle của nó. CI bỏ qua nhánh này.
_go._CLIENT_CACHE.clear()
for _k in ("JAVIS_GEMINI_OAUTH_CLIENT_ID", "JAVIS_GEMINI_OAUTH_CLIENT_SECRET"):
    os.environ.pop(_k, None)
if gemini_cli.find_gemini_cli():
    _cid, _csec = _go.doc_client()
    check("đọc được client OAuth TỪ CHÍNH bản Gemini CLI đã cài",
          _cid.endswith("apps.googleusercontent.com") and bool(_csec), _cid)
    # GitHub push protection chặn đúng lần đầu thử chép cứng vào repo, và nó chặn đúng.
    check("CANARY: client đọc được KHÔNG nằm nguyên văn trong mã nguồn",
          bool(_cid) and _cid not in (SERVER / "gemini_oauth.py").read_text(encoding="utf-8"))
else:
    print("bỏ qua  đọc client từ bundle (máy này chưa cài gemini CLI)")
_src_oauth = (SERVER / "gemini_oauth.py").read_text(encoding="utf-8")
check("CANARY: KHÔNG chép cứng client secret của Google vào repo",
      "GOCSPX" not in _src_oauth and "apps.googleusercontent.com\"" not in _src_oauth)
check("có cửa thoát bằng biến môi trường cho bản đóng gói lạ",
      "JAVIS_GEMINI_OAUTH_CLIENT_ID" in _src_oauth)
os.environ["JAVIS_GEMINI_OAUTH_CLIENT_ID"] = _GIA_ID
os.environ["JAVIS_GEMINI_OAUTH_CLIENT_SECRET"] = _GIA_SECRET
_go._CLIENT_CACHE.clear()
# Đây là điểm KHÁC biệt quyết định so với luồng gốc của CLI: nó dựng máy chủ loopback ở cổng
# ngẫu nhiên TRÊN MÁY CHẠY CLI, vô dụng khi Javis ở VPS còn trình duyệt ở máy người dùng.
check("CANARY: redirect về trang HIỆN MÃ của Google, không phải localhost",
      _q["redirect_uri"][0] == "https://codeassist.google.com/authcode"
      and "localhost" not in _r["authorize_url"] and "127.0.0.1" not in _r["authorize_url"])
check("có PKCE S256", _q["code_challenge_method"][0] == "S256" and len(_q["code_challenge"][0]) > 20)
check("CANARY: access_type=offline + prompt=consent - thiếu là không có refresh token, "
      "chạy được 1 tiếng rồi im",
      _q["access_type"][0] == "offline" and _q["prompt"][0] == "consent")
check("xin đủ scope Code Assist + email",
      "cloud-platform" in _q["scope"][0] and "userinfo.email" in _q["scope"][0])
check("mỗi lần bấm là một verifier khác",
      parse_qs(urlparse(_go.start_login()["authorize_url"]).query)["code_challenge"][0]
      != _q["code_challenge"][0])

_that_cli = gemini_cli.find_gemini_cli
try:
    for _k in ("JAVIS_GEMINI_OAUTH_CLIENT_ID", "JAVIS_GEMINI_OAUTH_CLIENT_SECRET"):
        os.environ.pop(_k, None)
    _go._CLIENT_CACHE.clear()
    gemini_cli.find_gemini_cli = lambda: None
    check("chưa cài CLI -> nói cách cài thay vì dựng một link hỏng",
          _go.start_login()["ok"] is False and "npm i -g" in _go.start_login()["error"])
finally:
    gemini_cli.find_gemini_cli = _that_cli
    os.environ["JAVIS_GEMINI_OAUTH_CLIENT_ID"] = _GIA_ID
    os.environ["JAVIS_GEMINI_OAUTH_CLIENT_SECRET"] = _GIA_SECRET
    _go._CLIENT_CACHE.clear()
_go.start_login()

check("dán mã rỗng -> báo rõ, không gọi Google", _go.finish_login("")["ok"] is False)
_go._pending.clear()
check("chưa bấm đăng nhập mà dán mã -> nói phải bấm trước",
      "Đăng nhập" in _go.finish_login("abc")["error"])
_go.start_login()
_go._pending["ts"] = 0.0
check("phiên quá hạn -> bắt bấm lại chứ không gửi mã cũ đi",
      "hết hạn" in _go.finish_login("abc")["error"])

# Token phải MÃ HOÁ trên đĩa như mọi secret khác.
_go._ghi({"access_token": "AT-abc", "refresh_token": "RT-xyz", "email": "quy@example.com",
          "expires_at": int(__import__("time").time()) + 3600})
_raw = (Path(os.environ["JAVIS_STATE_DIR"]) / "settings.json").read_text(encoding="utf-8")
check("CANARY: refresh token KHÔNG nằm nguyên văn trong settings.json",
      "RT-xyz" not in _raw and "AT-abc" not in _raw)
check("đọc lại vẫn ra đúng", _go.connected() is True and _go.email() == "quy@example.com")

# Refresh bị Google từ chối = mất quyền thật -> phải XOÁ, không được giữ trạng thái nói dối.
class _Rep:
    def __init__(self, code, payload=None):
        self.status_code = code
        self._p = payload or {}

    def json(self):
        return self._p


_post_that = _go.httpx.post
try:
    _go._ghi({"access_token": "cu", "refresh_token": "RT", "email": "a@b.com", "expires_at": 0})
    _go.httpx.post = lambda *a, **k: _Rep(400, {"error": "invalid_grant"})
    check("CANARY: refresh token bị thu hồi -> Javis nhận là MẤT đăng nhập",
          _go.valid_creds() == {} and _go.connected() is False)
    _go._ghi({"access_token": "cu", "refresh_token": "RT", "email": "a@b.com", "expires_at": 0})
    _go.httpx.post = lambda *a, **k: _Rep(200, {"access_token": "MOI", "expires_in": 3600})
    _d = _go.valid_creds()
    check("token sắp hết hạn thì tự làm mới", _d["access_token"] == "MOI")
    check("và giữ nguyên refresh token cũ khi Google không cấp cái mới", _d["refresh_token"] == "RT")
finally:
    _go.httpx.post = _post_that

# Bắc cầu sang kho của CLI.
_gh = Path(tempfile.mkdtemp(prefix="javis-gembridge-"))
_moi_cu = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE")}
try:
    os.environ["HOME"] = str(_gh)
    os.environ["USERPROFILE"] = str(_gh)
    _go._ghi({"access_token": "AT", "refresh_token": "RT", "email": "quy@example.com",
              "expires_at": int(__import__("time").time()) + 3600})
    check("bắc cầu được", _go.ghi_creds_cho_cli() is True)
    _cred = json.loads((_gh / ".gemini" / "oauth_creds.json").read_text(encoding="utf-8"))
    check("ghi đúng file mà CLI đọc", _cred["access_token"] == "AT" and _cred["refresh_token"] == "RT")
    check("CANARY: expiry_date tính bằng MILI giây (CLI dùng ms, sai đơn vị là nó tưởng hết hạn)",
          _cred["expiry_date"] > 1e12)
    check("file chứa token bị siết quyền",
          (os.stat(_gh / ".gemini" / "oauth_creds.json").st_mode & 0o077) == 0 or os.name == "nt")
    _st = json.loads((_gh / ".gemini" / "settings.json").read_text(encoding="utf-8"))
    check("CANARY: đặt luôn selectedType=oauth-personal - thiếu nó CLI dừng ở 'set an Auth method'",
          _st["security"]["auth"]["selectedType"] == "oauth-personal")
    check("ghi email để CLI + trang Models cùng hiện đúng tài khoản",
          json.loads((_gh / ".gemini" / "google_accounts.json").read_text(encoding="utf-8"))["active"]
          == "quy@example.com")

    # Người dùng đã tự chọn cách đăng nhập khác thì KHÔNG giẫm lên.
    (_gh / ".gemini" / "settings.json").write_text(
        json.dumps({"security": {"auth": {"selectedType": "vertex-ai"}}}), encoding="utf-8")
    _go.ghi_creds_cho_cli()
    check("CANARY: không đè cách đăng nhập người dùng đã tự chọn",
          json.loads((_gh / ".gemini" / "settings.json").read_text(encoding="utf-8"))
          ["security"]["auth"]["selectedType"] == "vertex-ai")

    # CLI bản mới NUỐT file rồi xoá đi -> mỗi lượt chạy phải dựng lại.
    (_gh / ".gemini" / "oauth_creds.json").unlink()
    _gq = gemini_cli.GeminiCLI(cwd=str(_gh))
    _gq.cli_path = None
    _gq._bac_cau_token()
    check("CANARY: mỗi lượt chạy tự dựng lại file (CLI nuốt xong là xoá)",
          (_gh / ".gemini" / "oauth_creds.json").exists())

    _that2 = gemini_cli.find_gemini_cli
    gemini_cli.find_gemini_cli = lambda: "/fake/gemini"
    try:
        _st2 = gemini_cli.auth_status()
        check("trang Models đọc trạng thái từ Javis, không phụ thuộc file CLI vừa bị nuốt",
              _st2["connected"] is True and _st2["email"] == "quy@example.com")
    finally:
        gemini_cli.find_gemini_cli = _that2

    _go.disconnect()
    check("ngắt thì xoá cả bản đã bắc cầu",
          _go.connected() is False and not (_gh / ".gemini" / "oauth_creds.json").exists())
finally:
    for k, v in _moi_cu.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

_duong = {getattr(r, "path", "") for r in main.app.routes}
for _e in ("/gemini-cli/login-start", "/gemini-cli/login-code", "/gemini-cli/logout",
           "/gemini-cli/check", "/gemini-cli/status"):
    check(f"có endpoint {_e}", _e in _duong)
check("CANARY: endpoint đăng nhập KHÔNG nằm trong danh sách miễn đăng nhập Javis",
      "gemini" not in _src_main[_src_main.index("_AUTH_PUBLIC_EXACT = "):
                                _src_main.index("_AUTH_PUBLIC_EXACT = ") + 400])
check("thẻ Models có nút đăng nhập ngay trên trang",
      "startGeminiLogin" in _console and "/gemini-cli/login-start" in _console)
check("và ô dán mã", "gcliCode" in _console and "/gemini-cli/login-code" in _console)
check("CANARY: giao diện không còn bắt người dùng mở terminal để đăng nhập",
      "Chạy <code>gemini</code> trong terminal" not in _console)

# Ô dán mã từng KHÔNG GÕ ĐƯỢC (chủ repo báo 2026-08-12 kèm ảnh): khối #gcliLogin nằm ngoài
# .prov-action nên không hưởng luật `width:auto` của nút ở đó, mà luật gốc .gcard-btn cuối
# console.css là `width:100%` - nút "Xong" giãn ra nuốt cả hàng flex, ô nhập còn vài chục
# pixel. Hai check này giữ đúng cặp class + luật CSS đã chữa, vì tách rời nhau là tái phát.
_console_css = (ROOT / "dashboard" / "console.css").read_text(encoding="utf-8")
check("ô dán mã dùng class riêng thay cho style inline",
      'class="gcli-code-row"' in _console)
check("CANARY: có luật CSS gò nút 'Xong' lại - thiếu nó nút nuốt hết chỗ của ô nhập",
      ".gcli-code-row .gcard-btn" in _console_css and "width: auto" in _console_css[
          _console_css.index(".gcli-code-row .gcard-btn"):
          _console_css.index(".gcli-code-row .gcard-btn") + 120])
# --- Thẻ Models ẨN khi máy không có binary (0.29.1) -------------------------
# Google ngắt hạng cá nhân nên với gần như mọi người đây là lựa chọn chết; bày ra chỉ để họ
# đăng nhập xong rồi đâm vào tường. Nhưng engine KHÔNG bị xoá (doanh nghiệp + API key vẫn
# chạy), nên ranh giới là "máy có binary hay không".
import config as _cfgmod   # noqa: E402
_cfg_the = _cfgmod.read_settings()
_that_find2 = gemini_cli.find_gemini_cli
try:
    gemini_cli.find_gemini_cli = lambda: None
    _ids = [p["id"] for p in main._providers_view(_cfg_the)]
    check("CANARY: máy KHÔNG có binary `gemini` -> thẻ Gemini CLI biến mất khỏi trang Models",
          "gemini-cli" not in _ids, _ids)
    check("và các thẻ khác không bị ảnh hưởng",
          "antigravity-cli" in _ids and "anthropic-cli" in _ids
          and len(_ids) == len(main.PROVIDER_DEFS) - 1, _ids)

    gemini_cli.find_gemini_cli = lambda: "/usr/bin/gemini"
    check("máy CÓ binary (doanh nghiệp / chạy bằng API key) -> thẻ hiện lại",
          "gemini-cli" in [p["id"] for p in main._providers_view(_cfg_the)])

    # Ai đang ĐẶT nó làm Main Model mà mất thẻ thì mất luôn đường đổi sang engine khác.
    gemini_cli.find_gemini_cli = lambda: None
    _cfg_main = dict(_cfg_the)
    _cfg_main["model"] = dict(_cfg_the["model"])
    _cfg_main["model"]["main"] = {"provider": "gemini-cli", "model": "gemini-2.5-pro"}
    check("CANARY: đang là Main Model thì VẪN hiện dù không có binary "
          "(không thì người dùng kẹt, không đổi engine được)",
          "gemini-cli" in [p["id"] for p in main._providers_view(_cfg_main)])
finally:
    gemini_cli.find_gemini_cli = _that_find2

for _f, _ten in ((ROOT / "Dockerfile", "Dockerfile"), (ROOT / "install.sh", "install.sh"),
                 (ROOT / "setup.bat", "setup.bat")):
    _txt = _f.read_text(encoding="utf-8")
    _dong_cai = [d for d in _txt.splitlines()
                 if "@google/gemini-cli" in d and not d.strip().startswith(("#", "REM"))]
    check(f"CANARY: {_ten} KHÔNG còn tự cài @google/gemini-cli (Google đã ngắt hạng cá nhân)",
          _dong_cai == [], _dong_cai)

check("CANARY: ô nhập được phép co (min-width:0) nên không tràn ra ngoài card",
      ".gcli-code-row .js-input" in _console_css and "min-width: 0" in _console_css[
          _console_css.index(".gcli-code-row .js-input"):
          _console_css.index(".gcli-code-row .js-input") + 120])

print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test gemini_cli đã qua.")
