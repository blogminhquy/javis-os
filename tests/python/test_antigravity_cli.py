"""Bộ não thứ 10: Antigravity CLI (`agy`) - bản Google chỉ định thay cho Gemini CLI.

    python tests/run.py antigravity_cli      (KHÔNG mạng, KHÔNG cần cài agy)

File engine này viết trong hoàn cảnh KHÁC hẳn `gemini_cli.py`: máy dựng bản đó có binary trong
tay để đọc `--help` thật, còn ở đây thì không (máy build bị chặn mạng). Nên thiết kế của nó là
"đo lúc chạy chứ không đoán" - và ĐÚNG CÁI ĐÓ là thứ test này phải canh, vì nó là chỗ duy nhất
có thể sai lặng lẽ:

1. **Không truyền cờ mà binary chưa có.** Bản `agy` cũ không có `--output-format`; truyền vào
   là nó thoát ngay "unknown flag" và hỏng cả lượt chat. Cờ nào cũng phải hỏi `--help` trước.
2. **Danh sách model hỏi CLI, không chép tay.** Chép tay là sai lặng lẽ ngay lần Google đổi
   tên model - mà họ đổi liên tục. Phải bóc được nhiều hình dạng JSON vì chưa đo được khoá thật.
3. **Không bao giờ im lặng.** Bản 1.0.0 có lỗi nuốt stdout khi chạy qua ống dẫn (issue #76).
   Trả bong bóng rỗng là đúng triệu chứng đã hành chủ repo cả buổi tối bên Gemini CLI.
4. **Mức quyền fail-closed.** Giá trị lạ phải về nấc chặt nhất, không phải nấc mở nhất.

Test dựng một `agy` GIẢ bằng script Python nên chạy được ở CI không có gì cả.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-agytest-")

import antigravity_cli   # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name
          + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def chay(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _gia(dong_ra, ma=0, stderr="", help_text="", models_out=""):
    """Dựng một `agy` giả: trả `--help` / `models` / lượt chat theo ý mình."""
    d = Path(tempfile.mkdtemp(prefix="javis-fakeagy-"))
    p = d / "agy"
    p.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "a = sys.argv[1:]\n"
        f"if '--help' in a:\n    sys.stdout.write({help_text!r}); sys.exit(0)\n"
        f"if a and a[0] == 'models':\n    sys.stdout.write({models_out!r}); sys.exit(0)\n"
        "sys.stdout.write(open('/dev/null').read()) if False else None\n"
        "try:\n    sys.stdin.read()\nexcept Exception:\n    pass\n"
        f"open({str(d / 'argv.txt')!r}, 'w').write('\\x00'.join(a))\n"
        f"for l in {json.dumps(dong_ra)}:\n    print(l, flush=True)\n"
        f"sys.stderr.write({stderr!r})\n"
        f"sys.exit({ma})\n",
        encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(p), d


def _reset_cache():
    antigravity_cli._HELP_CACHE.update(path=None, text="", ts=0.0)
    antigravity_cli._AUTH_CACHE.update(ts=0.0, val=None)


def _chay_gia(dong_ra, ma=0, stderr="", help_text="", prompt="xin chào", mode="full"):
    cli, d = _gia(dong_ra, ma, stderr, help_text)
    _reset_cache()
    antigravity_cli.find_antigravity_cli = lambda: cli
    g = antigravity_cli.AntigravityCLI(cwd="/tmp")
    g.cli_path = cli
    g.mode = mode

    async def _go():
        return [ev async for ev in g.query(prompt)]
    evs = chay(_go())
    argv = ""
    try:
        argv = (d / "argv.txt").read_text(encoding="utf-8")
    except Exception:
        pass
    return evs, g, argv.split("\x00")


_that_find = antigravity_cli.find_antigravity_cli

# HELP đầy đủ của một bản mới (>= 1.1.8: print mode có --output-format).
_HELP_MOI = ("Usage: agy [options]\n"
             "  -p, --print, --prompt   Run once and exit. Appended to input on stdin\n"
             "  --output-format <fmt>   text | json | stream-json\n"
             "  --model <slug>          Model to use\n"
             "  --conversation <uuid>   Resume a conversation\n"
             "  --dangerously-skip-permissions  Auto-approve tool calls\n"
             "  --sandbox               Restrict terminal access\n"
             "  --add-dir <path>        Add directory to context\n")
# HELP của một bản CŨ: KHÔNG có --output-format, KHÔNG có --sandbox.
_HELP_CU = ("Usage: agy [options]\n"
            "  -p, --print   Run once and exit\n"
            "  --model <slug>   Model to use\n")


# ============================================================
# 1. Chỉ truyền cờ mà binary THẬT SỰ có
# ============================================================
_DONG = [
    json.dumps({"type": "init", "conversation_id": "abc-123"}),
    json.dumps({"type": "tool_use", "tool_name": "read_file", "tool_id": "t1",
                "parameters": {"path": "a.md"}}),
    json.dumps({"type": "tool_result", "tool_id": "t1", "status": "success", "output": "nội dung"}),
    json.dumps({"role": "assistant", "content": "Chào "}),
    json.dumps({"role": "assistant", "content": "anh."}),
    json.dumps({"type": "result", "status": "success",
                "stats": {"input_tokens": 250, "output_tokens": 50, "total_tokens": 300}}),
]

_evs, _g, _argv = _chay_gia(_DONG, help_text=_HELP_MOI)
check("bản mới: truyền --output-format stream-json", "--output-format" in _argv
      and _argv[_argv.index("--output-format") + 1] == "stream-json", _argv)
check("gom được câu trả lời từ các mảnh chữ",
      any(e["type"] == "final" and e["content"] == "Chào anh." for e in _evs), _evs)
check("dịch được tool_call", any(e["type"] == "tool_call" and e["name"] == "read_file"
                                 for e in _evs))
check("dịch được tool_result", any(e["type"] == "tool_result" for e in _evs))
check("đọc được token vào/ra", any(e["type"] == "usage" and e["input_tokens"] == 250
                                   for e in _evs))
check("nhặt được id hội thoại để lượt sau nối lại", _g.session_id == "abc-123")

_evs2, _g2, _argv2 = _chay_gia(_DONG, help_text=_HELP_CU)
check("CANARY: bản CŨ không có --output-format thì TUYỆT ĐỐI không truyền "
      "(truyền là CLI thoát 'unknown flag', hỏng cả lượt)", "--output-format" not in _argv2, _argv2)
check("và vẫn lấy được câu trả lời",
      any(e["type"] == "final" and e["content"] == "Chào anh." for e in _evs2), _evs2)
check("bản cũ không có --sandbox thì cũng không truyền", "--sandbox" not in _argv2)

_evs3, _g3, _argv3 = _chay_gia(_DONG, help_text=_HELP_MOI, mode="suggest")
check("mức suggest: bật --sandbox", "--sandbox" in _argv3, _argv3)
check("CANARY: mức suggest KHÔNG tự duyệt mọi tool",
      "--dangerously-skip-permissions" not in _argv3, _argv3)

_evs4, _g4, _argv4 = _chay_gia(_DONG, help_text=_HELP_MOI, mode="full")
check("mức full: tự duyệt tool để headless không treo",
      "--dangerously-skip-permissions" in _argv4, _argv4)


# ============================================================
# 2. Mức quyền: giá trị lạ về nấc CHẶT nhất
# ============================================================
_cli_moi, _ = _gia([], help_text=_HELP_MOI)
_reset_cache()
antigravity_cli.find_antigravity_cli = lambda: _cli_moi
check("mode rỗng -> siết như suggest",
      antigravity_cli.co_quyen_cho_mode("") == ["--sandbox"])
check("CANARY: mode gõ sai KHÔNG được thành toàn quyền",
      "--dangerously-skip-permissions" not in antigravity_cli.co_quyen_cho_mode("FULLL"))
check("mode auto: có sandbox VÀ tự duyệt (headless dừng hỏi là treo)",
      set(antigravity_cli.co_quyen_cho_mode("auto"))
      == {"--sandbox", "--dangerously-skip-permissions"})


# ============================================================
# 3. Danh sách model: hỏi CLI, không chép tay
# ============================================================
for ten, ra, mong in [
    ("list JSON phẳng", '["Gemini 3.6 Flash (High)", "Claude Opus 4.6 (Thinking)"]',
     ["Gemini 3.6 Flash (High)", "Claude Opus 4.6 (Thinking)"]),
    ("bọc trong khoá models", '{"models": [{"slug": "gemini-3.6-flash", "name": "bỏ qua"}]}',
     ["gemini-3.6-flash"]),
    ("list dict dùng khoá id", '[{"id": "claude-opus-4.6"}]', ["claude-opus-4.6"]),
]:
    _c, _ = _gia([], help_text=_HELP_MOI, models_out=ra)
    _reset_cache()
    antigravity_cli.find_antigravity_cli = lambda c=_c: c
    check(f"bóc được model từ {ten}", antigravity_cli.list_models() == mong,
          antigravity_cli.list_models())

_c_chu, _ = _gia([], help_text=_HELP_CU, models_out="gemini-3-pro  Gemini 3 Pro\nclaude-opus-4-6  Claude Opus 4.6\n")
_reset_cache()
antigravity_cli.find_antigravity_cli = lambda: _c_chu
check("bản cũ in chữ thuần cũng bóc được",
      antigravity_cli.list_models() == ["gemini-3-pro", "claude-opus-4-6"],
      antigravity_cli.list_models())

# ---- Định dạng THẬT của `agy models` 1.1.12 (người dùng gửi kèm `cat -A`) ----
# Đây là ca đã làm provider Antigravity KHÔNG DÙNG ĐƯỢC Ở ĐÂU CẢ: cột phân tách bằng TAB, mà
# `\s{2,}` không khớp một tab đơn, nên cả dòng "gemini-3.6-flash-high\tGemini 3.6 Flash (High)"
# bị lấy làm mã model rồi truyền vào `--model` -> `agy` thoát mã 1 ở MỌI lượt chat.
_THAT = ("Fetching available models...\n"
         "gemini-3.6-flash-high\tGemini 3.6 Flash (High)\n"
         "gemini-3.5-flash-high\tGemini 3.5 Flash (High)\n"
         "claude-sonnet-4-6\tClaude Sonnet 4.6 (Thinking)\n")
_c_tab, _ = _gia([], help_text=_HELP_CU, models_out=_THAT)
_reset_cache()
antigravity_cli.find_antigravity_cli = lambda: _c_tab
_ds_tab = antigravity_cli.list_models()
check("CANARY: cột phân tách bằng TAB -> lấy ĐÚNG mã model, không dính tên hiển thị",
      _ds_tab == ["gemini-3.6-flash-high", "gemini-3.5-flash-high", "claude-sonnet-4-6"], _ds_tab)
check("CANARY: dòng thông báo 'Fetching available models...' KHÔNG lọt vào trình chọn",
      not any("Fetching" in m for m in (_ds_tab or [])), _ds_tab)
check("và không mã nào dính khoảng trắng (mã model là slug, câu thông báo thì luôn có)",
      all(" " not in m for m in (_ds_tab or [])), _ds_tab)

# Soi phần CODE thôi, bỏ chú thích ra: điều cần cấm là một BẢNG model chép tay dùng làm dữ
# liệu, chứ không phải việc trích tên model vào chú thích. Bản đầu soi cả file nên chỉ cần dán
# một dòng `agy models` thật vào comment để giải thích là test đỏ - đo sai thứ.
_src_agy = (ROOT / "server" / "antigravity_cli.py").read_text(encoding="utf-8")
_code_agy = "\n".join(l for l in _src_agy.splitlines() if not l.strip().startswith("#"))
_code_agy = _code_agy.split('"""', 2)[-1]      # bỏ luôn docstring đầu module
check("CANARY: KHÔNG có bảng model chép tay trong module (Google đổi tên là sai lặng lẽ)",
      "gemini-3" not in _code_agy)

antigravity_cli.find_antigravity_cli = lambda: None
_reset_cache()
check("chưa cài CLI -> list_models trả None để phía trên biết mà nói lý do",
      antigravity_cli.list_models() is None)
check("và auth_status nói cách cài",
      "install.sh" in antigravity_cli.auth_status()["error"]
      or "install.ps1" in antigravity_cli.auth_status()["error"])


# ============================================================
# 3b. Hình dạng sự kiện THẬT của agy 1.1.12 (người dùng đo và gửi kèm)
# ============================================================
# `agy` gói payload LỒNG dưới đúng tên sự kiện, và chữ trả lời nằm ở khoá `text_delta`. Bản đầu
# chỉ đọc tầng ngoài cùng nên `agy` chạy thành công mà bong bóng trả lời RỖNG.
_LONG = [
    json.dumps({"event": "init", "conversation_id": "hoi-thoai-1",
                "init": {"model": "gemini-3.6-flash-high", "cwd": "/app"}}),
    json.dumps({"event": "step_update",
                "step_update": {"step_type": "agent_response", "text_delta": "Xin ",
                                "usage": {"input_tokens": 10, "output_tokens": 2}}}),
    json.dumps({"event": "step_update",
                "step_update": {"step_type": "agent_response", "text_delta": "chào!"}}),
    json.dumps({"event": "result",
                "result": {"status": "SUCCESS", "response": "Xin chào!",
                           "usage": {"input_tokens": 120, "output_tokens": 8}}}),
]
_evsl, _gl, _ = _chay_gia(_LONG, help_text=_HELP_MOI)
_final = [e for e in _evsl if e["type"] == "final"]
check("CANARY: sự kiện LỒNG + khoá text_delta -> vẫn ra câu trả lời (bản đầu trả bong bóng rỗng)",
      len(_final) == 1 and _final[0]["content"] == "Xin chào!", _evsl)
check("CANARY: câu trả lời KHÔNG bị gom hai lần (một lần từ text_delta, một lần từ result.response)",
      len(_final) == 1 and _final[0]["content"].count("Xin chào") == 1, _final)
check("id hội thoại lấy ở TẦNG NGOÀI, không bị payload lồng đè mất",
      _gl.session_id == "hoi-thoai-1", _gl.session_id)
check("đọc được token từ usage lồng bên trong result",
      any(e["type"] == "usage" and e["input_tokens"] == 120 for e in _evsl), _evsl)

# Ca NGƯỢC LẠI, và đây là chỗ patch của người dùng còn hở: lượt trả lời NGẮN có bản chỉ phát
# mỗi `result`, không có text_delta nào. `return ra` vô điều kiện ở nhánh result là câu trả lời
# biến mất sạch. Nên chỉ bỏ qua khi ĐÃ gom được chữ.
_CHI_RESULT = [
    json.dumps({"event": "init", "conversation_id": "x"}),
    json.dumps({"event": "result", "result": {"status": "SUCCESS", "response": "Chỉ mỗi result."}}),
]
_evsr, _, _ = _chay_gia(_CHI_RESULT, help_text=_HELP_MOI)
check("CANARY: chỉ có `result`, không có text_delta -> VẪN lấy được câu trả lời",
      any(e["type"] == "final" and e["content"] == "Chỉ mỗi result." for e in _evsr), _evsr)


# ============================================================
# 4. Không bao giờ im lặng
# ============================================================
_evs5, _, _ = _chay_gia([], help_text=_HELP_MOI)
check("CANARY: chạy xong mà không in gì -> BÁO LỖI, không trả bong bóng rỗng",
      any(e["type"] == "error" for e in _evs5) and not any(e["type"] == "final" for e in _evs5),
      _evs5)
check("và mách nước nâng cấp (bản cũ có lỗi nuốt stdout khi chạy nền)",
      any("nâng cấp" in e.get("content", "") or "install" in e.get("content", "")
          for e in _evs5))

_evs6, _, _ = _chay_gia(["một dòng chữ không phải JSON"], help_text=_HELP_MOI)
check("dòng không phải JSON vẫn được nhận làm câu trả lời",
      any(e["type"] == "final" and "không phải JSON" in e["content"] for e in _evs6), _evs6)

_evs7, _, _ = _chay_gia([], ma=1, stderr="Error: not signed in", help_text=_HELP_MOI)
check("chưa đăng nhập -> câu làm theo được, không phải nguyên văn tiếng Anh",
      any(e["type"] == "error" and "agy" in e.get("content", "") for e in _evs7), _evs7)

_evs8, _, _ = _chay_gia([], ma=3, stderr="một lỗi lạ nào đó", help_text=_HELP_MOI)
check("lỗi lạ thì giữ nguyên văn để còn tra được",
      any("một lỗi lạ nào đó" in e.get("content", "") for e in _evs8))

async def _gom(g):
    return [ev async for ev in g.query("hỏi gì đó")]


antigravity_cli.find_antigravity_cli = lambda: None
_g9 = antigravity_cli.AntigravityCLI()
_g9.cli_path = None
_evs9 = chay(_gom(_g9))
check("chưa cài CLI -> báo cách cài, không nổ",
      len(_evs9) == 1 and _evs9[0]["type"] == "error"
      and ("install.sh" in _evs9[0]["content"] or "install.ps1" in _evs9[0]["content"]), _evs9)
check("is_available() nói đúng sự thật", _g9.is_available() is False)


# ============================================================
# 5. MCP hub cô lập theo brain, không đụng file người dùng
# ============================================================
_brain = Path(tempfile.mkdtemp(prefix="javis-agybrain-"))
_hub = {"httpUrl": "http://127.0.0.1:7777/mcp", "headers": {"Authorization": "Bearer x"}}
antigravity_cli.ghi_mcp_settings(_brain, _hub)
_files = list((_brain / ".antigravity").glob("*.json"))
check("ghi cấu hình MCP vào TRONG brain, không vào HOME", len(_files) >= 1, _files)
_doc = json.loads(_files[0].read_text(encoding="utf-8"))
check("entry hub tên 'javis'", (_doc.get("mcpServers") or {}).get("javis") == _hub, _doc)

# Giữ nguyên phần người dùng đã tự thêm.
_p0 = _brain / ".antigravity" / "mcp.json"
_doc0 = json.loads(_p0.read_text(encoding="utf-8"))
_doc0["mcpServers"]["cua-toi"] = {"httpUrl": "http://x"}
_doc0["theme"] = "dark"
_p0.write_text(json.dumps(_doc0), encoding="utf-8")
antigravity_cli.ghi_mcp_settings(_brain, _hub)
_doc1 = json.loads(_p0.read_text(encoding="utf-8"))
check("CANARY: không xoá MCP người dùng tự thêm",
      "cua-toi" in (_doc1.get("mcpServers") or {}), _doc1)
check("và không xoá cấu hình khác của họ", _doc1.get("theme") == "dark")

antigravity_cli.ghi_mcp_settings(_brain, None)
_doc2 = json.loads(_p0.read_text(encoding="utf-8"))
check("tắt hub -> gỡ đúng entry javis, giữ phần còn lại",
      "javis" not in (_doc2.get("mcpServers") or {})
      and "cua-toi" in (_doc2.get("mcpServers") or {}), _doc2)

if os.name != "nt":
    check("file chứa hub token bị siết quyền",
          (_p0.stat().st_mode & 0o077) == 0, oct(_p0.stat().st_mode))


# ============================================================
# 6. Đã đấu vào Javis chưa (không chỉ là một module nằm không)
# ============================================================
antigravity_cli.find_antigravity_cli = _that_find
_main_src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("có trong danh sách provider của trang Models",
      '"id": "antigravity-cli"' in _main_src)
check("CANARY: xếp TRƯỚC thẻ Gemini CLI (đường Gemini cá nhân đã chết)",
      _main_src.index('"id": "antigravity-cli"') < _main_src.index('"id": "gemini-cli"'))
check("có nhánh chat riêng", 'elif prov == "antigravity-cli":' in _main_src)
check("Telegram cũng có nhánh đó", 'if prov == "antigravity-cli":' in _main_src)
check("đường chat-thuần (_api_stream) có nhánh, không rơi xuống anthropic key rỗng",
      "_antigravity_sub_stream" in _main_src)
check("có gắn MCP hub", "_apply_antigravity_hub" in _main_src)
check("trang Models hỏi được danh sách model", "antigravity_cli.list_models" in _main_src)
check("có endpoint kiểm tra", "/antigravity/check" in _main_src)

_console = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("thẻ Models có card riêng", 'p.id === "antigravity-cli"' in _console)
check("card chỉ đúng lệnh cài", "data-agycheck" in _console)

# Canary này đảo chiều hai lần, nên ghi lại cả hai để đừng đảo lần thứ ba mà không có dữ liệu
# mới. Trước 0.30.0: "không hứa nút đăng nhập trên dashboard" (đúng hiện trạng, nhưng chốt sai
# khả năng - không ghi credential hộ được KHÔNG có nghĩa là không đăng nhập trên trang được).
# 0.30.0 đi đường LÁI luồng đăng nhập của chính CLI qua một pseudo-terminal, và nó chạy thật
# trên Linux. 0.32.2 gỡ hẳn, lần này vì TRẢI NGHIỆM chứ không phải vì bất khả: luồng đó hiện ra
# một ô terminal trên trang mà bấm vào không ăn nên người dùng vẫn phải mở terminal, còn Windows
# không có PTY nên chưa bao giờ dùng được. Người dùng `agy` đều là dân code sẵn terminal - một
# lệnh `agy` gọn hơn hẳn một luồng UI nửa vời. Muốn dựng lại thì phải là terminal tương tác
# thật, không phải bản chỉ-đọc.
check("thẻ Models KHÔNG dựng nút đăng nhập trên trang (0.32.2)", "data-agylogin" not in _console)
check("và không còn gọi endpoint đăng nhập đã gỡ",
      "/antigravity/login-start" not in _console and "/antigravity/login-start" not in _main_src)
check("thay vào đó đưa đúng lệnh cần gõ trong terminal", "p.dang_nhap" in _console)
check("server cấp hướng dẫn đó cho trang Models",
      "antigravity_cli.login_huong_dan()" in _main_src)

# ============================================================
# 8. Windows: dòng lệnh quá dài phải báo tử tế, không nổ WinError 206
# ============================================================
# Người dùng báo 2026-08-13 (Windows 10, agy 1.1.12): hội thoại dài ~648k token ngữ cảnh thì
# mọi lượt chat qua Antigravity chết vì CreateProcess chặn tổng dòng lệnh ở 32767 ký tự.
# Họ đã ĐO: bản này không nhận prompt qua stdin, không đọc AGENTS.md, không đọc GEMINI.md, và
# --help không có cờ nào nhận prompt từ file. Nên không có đường vòng - việc duy nhất làm đúng
# được là nói thẳng thay vì để nổ một câu không ai đoán ra.
_cli_win, _ = _gia([], help_text=_HELP_CU)     # _HELP_CU không nhắc stdin -> buộc đi argv
_reset_cache()
antigravity_cli.find_antigravity_cli = lambda: _cli_win
_g_win = antigravity_cli.AntigravityCLI(cwd="/tmp")
_g_win.cli_path = _cli_win
_g_win.instructions = "x" * 40000
_ten_that = os.name
try:
    os.name = "nt"
    _evs_win = chay(_gom(_g_win))
finally:
    os.name = _ten_that
check("CANARY: Windows + prompt quá dài -> báo tử tế, KHÔNG để nổ WinError 206",
      len(_evs_win) == 1 and _evs_win[0]["type"] == "error"
      and "quá dài" in _evs_win[0]["content"], _evs_win)
check("và nói đúng hai việc làm được ngay",
      "hội thoại mới" in _evs_win[0]["content"] and "Models" in _evs_win[0]["content"])
check("CANARY: Linux KHÔNG bị chặn nhầm (không có trần 32767)",
      any(e["type"] in ("final", "error") for e in chay(_gom(_g_win)))
      and "quá dài" not in str(chay(_gom(_g_win))))


# ============================================================
# 9. Kernel cũ: SDK phải chạy binary `claude` của máy, không phải bản Bun đóng gói
# ============================================================
# Người dùng chạy NAS Synology DS916+ (kernel 3.10.108) báo kèm log: `_bundled/claude` build
# bằng Bun, Bun đòi syscall getrandom (kernel >= 3.17), thiếu thì panic `errno 38` rồi abort ->
# SDK ném "Command failed with exit code -6" - trong khi `claude` bản Node cùng container chạy
# hoàn hảo. Dính mọi kernel < 3.17.
_sdk = (ROOT / "server" / "claude_sdk_engine.py").read_text(encoding="utf-8")
check("CANARY: đặt cli_path cho SDK (không thì SDK tự chọn bản Bun đóng gói)",
      '"cli_path" in fields' in _sdk and 'kw["cli_path"]' in _sdk)
check("dùng tim_binary chứ không shutil.which (tiến trình nền trên macOS có PATH tối giản)",
      "tim_binary" in _sdk.split('"cli_path" in fields')[1][:800])
check("CANARY: chặn PATH trỏ nhầm về chính binary đóng gói",
      '"_bundled" not in' in _sdk)
check("có cửa thoát JAVIS_CLAUDE_CLI cho máy cài chỗ lạ", "JAVIS_CLAUDE_CLI" in _sdk)


print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test antigravity_cli đã qua.")
