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
        "try:\n    _sd = sys.stdin.read()\nexcept Exception:\n    _sd = ''\n"
        f"open({str(d / 'stdin.txt')!r}, 'w').write(_sd or '')\n"
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
# CANARY của một lỗi ĐÃ XẢY RA và im lặng suốt: hai đường dẫn `.antigravity/*` là bản ĐOÁN của
# 0.30.0, và cả hai đều sai. Chỗ đúng ở tầng workspace là `.agents/mcp_config.json` (ba driver
# `agy` thật của bên thứ ba dùng đường này, cộng CHANGELOG 1.0.5 của Google nhắc đích danh tên
# file). Sai đường dẫn thì `agy` chạy bình thường nhưng KHÔNG có tool nào của Javis - không
# Kanban, không MCP, không skill - mà chẳng có câu lỗi nào để lần ra.
_p_moi = _brain / ".agents" / "mcp_config.json"
check("CANARY: ghi cả đường dẫn ĐÚNG `.agents/mcp_config.json`", _p_moi.is_file(), _p_moi)
check("và entry hub ở đó cũng đúng",
      (json.loads(_p_moi.read_text(encoding="utf-8")).get("mcpServers") or {}).get("javis") == _hub)
check("CANARY: có neo `.antigravitycli/` để agy nhận đúng brain làm gốc project",
      (_brain / ".antigravitycli").is_dir())

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
# 8. Prompt dài hơn trần dòng lệnh: phải ĐI VÒNG, không phải bỏ cuộc
# ============================================================
# Ca này đã hiểu sai một lần, và cái giá là bộ não Antigravity chết hẳn trên Windows suốt
# 0.31.x-0.32.x mà không ai biết.
#
# Người dùng báo 2026-08-13 kèm ảnh: mọi lượt chat qua Antigravity trên Windows đều trả về "Hội
# thoại này đã quá dài", KỂ CẢ tin nhắn "hi em" trong một hội thoại mới tinh. Đo lại thì rõ vì
# sao: system prompt của Javis trên brain TRỐNG đã 36.045 ký tự (CLAUDE.md 27.172 + lớp agentic +
# chỉ mục năng lực + khối kênh 5.838), trong khi CreateProcess của Windows chặn tổng dòng lệnh ở
# 32767. Phần vượt trần là phần CỐ ĐỊNH chứ không phải phần hội thoại - nên lời khuyên "mở hội
# thoại mới" của bản cũ không bao giờ cứu được ai, và mỗi lần người dùng làm theo lại càng tin
# là mình làm sai chứ không phải Javis hỏng.
#
# Nay có ba đường, và phải ĐO chứ không đoán: argv (khi vừa), stdin (khi CLI chịu), file ngữ
# cảnh (khi không còn cách nào). Test tách làm hai nửa vì một lý do rất cụ thể: giả `os.name =
# "nt"` trên Linux làm `pathlib.Path()` dựng WindowsPath rồi ném NotImplementedError, nên nửa
# QUYẾT ĐỊNH (chọn đường nào) giả Windows nhưng chặn mọi thao tác pathlib, còn nửa CƠ CHẾ (file
# ngữ cảnh chạy ra sao) ép đường bằng biến môi trường và chạy thật trên Linux.
_no_window_that = antigravity_cli._no_window
antigravity_cli._no_window = lambda: 0     # os.name giả sẽ làm _no_window() nổ trên Linux


# ---- Nửa 1: trên Windows, prompt dài phải đi STDIN, và prompt phải TỚI NƠI nguyên vẹn ----
# Đường đúng là stdin, và đây là bằng chứng chính chủ chứ không phải phỏng đoán. CHANGELOG của
# `agy`, hai dòng:
#   1.1.1 "Fixed `agy -p` hanging when run inside a shell script or subprocess by no longer
#          reading stdin when a prompt is provided via a flag."
#   1.1.2 "... when stdin is consumed by a piped prompt."
# Tức nó ĐỌC stdin, với đúng một điều kiện: prompt không cấp qua cờ. `--print ""` (giá trị rỗng)
# rồi bơm stdin là công thức đúng, và `_build_args()` đã làm sẵn như vậy từ đầu.
#
# Vì sao bản trước không bao giờ đi vào đường này: `nhan_prompt_qua_stdin()` quyết định bằng
# cách tìm chữ "stdin" trong `agy --help`, mà KHÔNG bản help nào có chữ đó. Hàm trả False vĩnh
# viễn, mọi lượt rơi xuống argv rồi đâm vào trần 32767 của Windows.
_cli_win, _d_win = _gia([json.dumps({"role": "assistant", "content": "Chào anh."})],
                        help_text=_HELP_CU)   # _HELP_CU không nhắc stdin: đúng như bản thật
_reset_cache()
antigravity_cli.find_antigravity_cli = lambda: _cli_win
_g_win = antigravity_cli.AntigravityCLI(cwd=str(_d_win))
_g_win.cli_path = _cli_win
_g_win.instructions = "x" * 40000
_ten_that = os.name
try:
    os.name = "nt"
    _evs_win = chay(_gom(_g_win))
finally:
    os.name = _ten_that


def _doc(d, ten):
    try:
        return (d / ten).read_text(encoding="utf-8")
    except Exception:
        return ""


_argv_win, _stdin_win = _doc(_d_win, "argv.txt"), _doc(_d_win, "stdin.txt")

check("CANARY: Windows + prompt dài hơn trần -> VẪN CHẠY, không bỏ cuộc",
      any(e["type"] == "final" for e in _evs_win)
      and not any("quá dài" in str(e.get("content") or "") for e in _evs_win), _evs_win)
check("CANARY: dòng lệnh gửi đi nằm dưới trần 32767 của Windows",
      bool(_argv_win) and len(_argv_win) < 32767, len(_argv_win))
check("CANARY: prompt tới nơi NGUYÊN VẸN qua stdin (không cắt, không tóm tắt)",
      "x" * 40000 in _stdin_win and "hỏi gì đó" in _stdin_win, len(_stdin_win))
check("và `-p` truyền giá trị RỖNG - đúng công thức agy mới chịu đọc stdin",
      _argv_win.split("\x00")[-2:] == ["-p", ""], _argv_win.split("\x00")[-3:])
check("CANARY: không dựng file ngữ cảnh khi stdin đã đủ (đường trung thực hơn thì ưu tiên)",
      not (_d_win / ".javis-agy").exists())

# `-p` PHẢI là cờ CUỐI CÙNG. `agy` bỏ qua mọi cờ đứng sau nó, nên chèn thêm gì ở dưới là
# `--output-format stream-json` rơi mất, CLI in chữ thuần, bộ đọc stream không hiểu, và người
# dùng nhận một bong bóng rỗng. Hỏng lặng lẽ, không có câu lỗi nào để lần ra - đúng loại bug
# đắt nhất, nên khoá lại bằng canary.
_dsach = _argv_win.split("\x00")
check("CANARY: `-p` nằm CUỐI dòng lệnh (cờ đứng sau nó bị agy bỏ qua)",
      len(_dsach) >= 2 and _dsach[-2] == "-p", _dsach[-4:])

check("CANARY: Linux vẫn đi argv như cũ (trần 128KB cho một tham số, chưa chạm)",
      antigravity_cli._tran_argv() == 120000)
try:
    os.name = "nt"
    check("và Windows lấy đúng trần chặt hơn", antigravity_cli._tran_argv() == 30000)
finally:
    os.name = _ten_that


# ---- Nửa 1b: bản CLI nào KHÔNG chịu đọc stdin thì tự chuyển sang file ngay trong lượt đó ----
# Một bản `agy` đủ cũ (trước 1.1.1) hoặc một ngày Google đổi luật thì stdin thành ngõ cụt. Dấu
# hiệu là: chạy xong, không lỗi, mà cũng không có lấy một chữ. Bắt người dùng nhìn bong bóng
# rỗng rồi tự đoán là đúng cái sai mà file engine này viết ra để tránh.
_HELP_MOI_KHONG_STDIN = _HELP_MOI.replace(". Appended to input on stdin", "")
_d_bo = Path(tempfile.mkdtemp(prefix="javis-fakeagy-boqua-"))
_cli_bo = _d_bo / "agy"
_cli_bo.write_text(
    "#!/usr/bin/env python3\nimport sys, json\n"
    "a = sys.argv[1:]\n"
    f"if '--help' in a:\n    sys.stdout.write({_HELP_MOI_KHONG_STDIN!r}); sys.exit(0)\n"
    "try:\n    sys.stdin.read()\nexcept Exception:\n    pass\n"
    "v = a[a.index('-p') + 1] if '-p' in a and a.index('-p') + 1 < len(a) else ''\n"
    "# Bỏ QUA stdin: prompt rỗng thì im lặng, y như bản agy cũ.\n"
    "if not v:\n    sys.exit(0)\n"
    "print(json.dumps({'role': 'assistant', 'content': 'Chào anh.'}), flush=True)\n",
    encoding="utf-8")
_cli_bo.chmod(_cli_bo.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
_reset_cache()
antigravity_cli.find_antigravity_cli = lambda: str(_cli_bo)
_g_bo = antigravity_cli.AntigravityCLI(cwd=str(_d_bo))
_g_bo.cli_path = str(_cli_bo)
_g_bo.instructions = "x" * 40000
os.environ["JAVIS_AGY_PROMPT_DAI"] = "stdin"
try:
    _evs_bo = chay(_gom(_g_bo))
finally:
    os.environ.pop("JAVIS_AGY_PROMPT_DAI", None)
check("CANARY: CLI bỏ qua stdin -> tự thử lại bằng file ngữ cảnh, người dùng vẫn có câu trả lời",
      any(e["type"] == "final" and "Chào anh." in str(e.get("content") or "")
          for e in _evs_bo), _evs_bo)
check("và chỉ trả về MỘT câu trả lời, không phải hai (lượt hỏng không được phát final)",
      len([e for e in _evs_bo if e["type"] == "final"]) == 1, _evs_bo)
check("CANARY: và lượt đi đường file đó nói rõ là model chưa đọc file ngữ cảnh",
      any("file ngữ cảnh" in str(e.get("content") or "")
          for e in _evs_bo if e.get("type") == "final"), _evs_bo)


# Bộ nhớ "đường nào chạy được" phải BẤT ĐỐI XỨNG. "stdin chạy được" là bằng chứng chắc chắn nên
# nhớ vĩnh viễn; "stdin trả rỗng" có thể chỉ là một lượt model im lặng hay một lúc mạng lỗi, nhớ
# vĩnh viễn theo chiều đó là đóng đinh cả máy vào đường kém trung thực hơn vì đúng một lượt xui,
# mà chữ ký binary chỉ đổi khi nâng cấp `agy` nên không có gì gỡ ra được.
_cli_nho, _d_nho = _gia([], help_text=_HELP_CU)
_reset_cache()
antigravity_cli.find_antigravity_cli = lambda: _cli_nho
antigravity_cli.nho_duong(_cli_nho, "file", "stdin trả về rỗng")
check("nhớ được là bản này phải đi đường file",
      antigravity_cli.duong_prompt_dai(_cli_nho) == "file")
_nho = antigravity_cli._doc_nho_duong()
_nho["ts"] = _nho["ts"] - antigravity_cli._HAN_NHO_AM - 10
antigravity_cli._ghi_nho_duong(_nho)
check("CANARY: kết quả ÂM TÍNH hết hạn sau 24h -> thử lại stdin, không đóng đinh vĩnh viễn",
      antigravity_cli.duong_prompt_dai(_cli_nho) == "stdin")
antigravity_cli.nho_duong(_cli_nho, "stdin", "đã chạy được")
_nho2 = antigravity_cli._doc_nho_duong()
_nho2["ts"] = 0.0
antigravity_cli._ghi_nho_duong(_nho2)
check("còn kết quả DƯƠNG TÍNH thì nhớ mãi (bằng chứng chắc chắn, không cần đo lại)",
      antigravity_cli.duong_prompt_dai(_cli_nho) == "stdin")


# ---- Nửa 2: cơ chế file ngữ cảnh, chạy thật (ép đường bằng biến môi trường) ----
_STATE = Path(os.environ["JAVIS_STATE_DIR"])


def _tep_ngu_canh():
    d = _STATE / ".javis-agy"
    return sorted(d.glob("ngu-canh-*.md")) if d.is_dir() else []


def _chay_ep_file(dong_ra, giu=False, help_text=_HELP_MOI):
    cli, d = _gia(dong_ra, help_text=help_text)
    _reset_cache()
    antigravity_cli.find_antigravity_cli = lambda: cli
    g = antigravity_cli.AntigravityCLI(cwd=str(d))
    g.cli_path = cli
    g.instructions = "x" * 40000
    os.environ["JAVIS_AGY_PROMPT_DAI"] = "file"
    if giu:
        os.environ["JAVIS_AGY_GIU_NGU_CANH"] = "1"
    try:
        evs = chay(_gom(g))
    finally:
        os.environ.pop("JAVIS_AGY_PROMPT_DAI", None)
        os.environ.pop("JAVIS_AGY_GIU_NGU_CANH", None)
    argv = ""
    try:
        argv = (d / "argv.txt").read_text(encoding="utf-8")
    except Exception:
        pass
    return evs, d, argv.split("\x00")


for _f in _tep_ngu_canh():
    _f.unlink()
_evs_f, _d_f, _argv_f = _chay_ep_file([json.dumps({"role": "assistant", "content": "ok"})],
                                      giu=True)
_tep_nc = _tep_ngu_canh()
# CANARY của một lỗ hổng suýt ship: file ngữ cảnh là BẢN SAO của system prompt + MEMORY.md +
# toàn bộ lịch sử hội thoại. Bản đầu ghi nó vào trong brain, mà đường sao lưu git của brain
# (`git_brain._backup_skip`) chỉ chặn theo danh sách cố định rồi cho qua mọi file .md - tức một
# lượt đồng bộ chạy trúng lúc `agy` đang chạy là nguyên gói đó được commit và push lên remote
# của người dùng, và git giữ blob vĩnh viễn. Ngay cạnh đó, `Memory/conversations/` bị chặn khỏi
# backup CÓ CHỦ ĐÍCH vì "có thể chứa secret".
check("CANARY: file ngữ cảnh nằm NGOÀI brain (không lọt vào git backup của người dùng)",
      len(_tep_nc) == 1 and not str(_tep_nc[0]).startswith(str(_d_f)), _tep_nc)
check("và chứa nguyên vẹn system prompt",
      bool(_tep_nc) and "x" * 40000 in _tep_nc[0].read_text(encoding="utf-8"))
check("CANARY: mở quyền đọc thư mục đó bằng --add-dir (file không còn nằm trong cwd)",
      "--add-dir" in _argv_f
      and str(_tep_nc[0].parent) in _argv_f, _argv_f[:8])
# Hai lớp nữa cho cùng một rủi ro, phòng khi có ai đó đổi chỗ ghi file về lại trong brain.
_gb = (ROOT / "server" / "git_brain.py").read_text(encoding="utf-8")
check("CANARY: git backup chặn thư mục .javis-agy", "/.javis-agy/" in _gb)
check("và .gitignore của brain cũng chặn", '".javis-agy/"' in _gb)

for _f in _tep_ngu_canh():
    _f.unlink()
_evs_f2, _d_f2, _ = _chay_ep_file([json.dumps({"role": "assistant", "content": "ok"})])
check("CANARY: dọn sạch file ngữ cảnh sau khi chạy (không để lại bản sao ký ức)",
      not _tep_ngu_canh(), _tep_ngu_canh())

# Dọn cả file MỒ CÔI: kill -9 hay mất điện giữa lượt thì không `finally` nào chạy, mà thứ nằm
# lại là bản sao ký ức của người dùng chứ không phải file tạm vô hại.
_mo_coi = _STATE / ".javis-agy" / "ngu-canh-mocoi000000.md"
_mo_coi.parent.mkdir(parents=True, exist_ok=True)
_mo_coi.write_text("rác cũ", encoding="utf-8")
os.utime(_mo_coi, (0, 0))
antigravity_cli._don_ngu_canh_cu(_mo_coi.parent)
check("CANARY: file ngữ cảnh mồ côi quá hạn bị dọn", not _mo_coi.exists())


def _chay_file_voi_su_kien(dong_ra_fn, help_text=_HELP_MOI):
    """Chạy đường file với CLI giả biết nhắc ĐÚNG tên file ngữ cảnh mà lượt đó sinh ra."""
    cli, d = _gia([], help_text=help_text)
    _reset_cache()
    antigravity_cli.find_antigravity_cli = lambda: cli
    g = antigravity_cli.AntigravityCLI(cwd=str(d))
    g.cli_path = cli
    g.instructions = "x" * 40000
    that = antigravity_cli._viet_file_ngu_canh

    def _viet_roi_dung_cli(cwd, nd):
        p, duong = that(cwd, nd)
        Path(cli).write_text(
            "#!/usr/bin/env python3\nimport sys, json\n"
            "a = sys.argv[1:]\n"
            "if '--help' in a:\n    sys.stdout.write(%r); sys.exit(0)\n"
            "try:\n    sys.stdin.read()\nexcept Exception:\n    pass\n"
            "%s\n"
            % (help_text, "\n".join(
                "print(%r, flush=True)" % l for l in dong_ra_fn(duong))),
            encoding="utf-8")
        return p, duong

    antigravity_cli._viet_file_ngu_canh = _viet_roi_dung_cli
    os.environ["JAVIS_AGY_PROMPT_DAI"] = "file"
    try:
        return chay(_gom(g))
    finally:
        antigravity_cli._viet_file_ngu_canh = that
        os.environ.pop("JAVIS_AGY_PROMPT_DAI", None)


def _co_canh_bao(evs):
    return any("file ngữ cảnh" in str(e.get("content") or "")
               for e in evs if e.get("type") == "final")


# Đọc ĐƯỢC: có kết quả tool không lỗi nhắc đúng tên file -> tuyệt đối không cảnh báo.
_evs_doc = _chay_file_voi_su_kien(lambda duong: [
    json.dumps({"type": "tool_use", "tool_name": "read_file", "tool_id": "t1",
                "parameters": {"path": duong}}),
    json.dumps({"type": "tool_result", "tool_id": "t1", "status": "success",
                "output": f"nội dung của {duong}"}),
    json.dumps({"role": "assistant", "content": "Chào anh."}),
])
check("CANARY: model ĐỌC ĐƯỢC file thì KHÔNG dán cảnh báo oan",
      any(e["type"] == "final" for e in _evs_doc) and not _co_canh_bao(_evs_doc), _evs_doc)

# Đọc HỎNG: có gọi tool nhưng kết quả báo lỗi (sandbox/quyền chặn). Bản đầu tính ca này là "đã
# đọc" vì chỉ dò tên file trong bất kỳ sự kiện nào - tức lưới an toàn mù đúng lúc cần nhất.
_evs_hong = _chay_file_voi_su_kien(lambda duong: [
    json.dumps({"type": "tool_use", "tool_name": "read_file", "tool_id": "t1",
                "parameters": {"path": duong}}),
    json.dumps({"type": "tool_result", "tool_id": "t1", "status": "error",
                "output": "permission denied"}),
    json.dumps({"role": "assistant", "content": "Chào anh."}),
])
check("CANARY: gọi tool nhưng đọc HỎNG (sandbox/quyền) -> phải nói ra, không tính là đã đọc",
      _co_canh_bao(_evs_hong), _evs_hong)

# Không đụng tới file: cảnh báo, và là câu khác (chưa thử vs thử mà hỏng).
_evs_lo = _chay_file_voi_su_kien(lambda duong: [
    json.dumps({"role": "assistant", "content": "Chào anh."}),
])
check("CANARY: model lờ file ngữ cảnh -> cũng phải nói ra", _co_canh_bao(_evs_lo), _evs_lo)

# Bản CLI cũ không có --output-format: stdout là chữ thuần, KHÔNG có sự kiện cấu trúc nào để đo.
# Không biết mà vẫn dán cảnh báo thì mọi lượt đều bị dán oan - cũng là một kiểu nói sai.
_evs_mu = _chay_file_voi_su_kien(lambda duong: ["Chào anh."], help_text=_HELP_CU)
check("CANARY: bản CLI không có stream-json -> KHÔNG đo được thì KHÔNG dán cảnh báo oan",
      any(e["type"] == "final" for e in _evs_mu) and not _co_canh_bao(_evs_mu), _evs_mu)

# Bản CLI nhận stdin thì phải đi stdin và KHÔNG đụng tới file: stdin giữ prompt nguyên vẹn, còn
# file thì phụ thuộc model chịu mở ra đọc.
_cli_sd, _d_sd = _gia([json.dumps({"role": "assistant", "content": "ok"})], help_text=_HELP_MOI)
_reset_cache()
antigravity_cli.find_antigravity_cli = lambda: _cli_sd
_g_sd = antigravity_cli.AntigravityCLI(cwd=str(_d_sd))
_g_sd.cli_path = _cli_sd
_g_sd.instructions = "y" * 40000
try:
    os.name = "nt"
    _evs_sd = chay(_gom(_g_sd))
finally:
    os.name = _ten_that
check("CANARY: bản CLI nhận stdin thì đi stdin, không dựng file ngữ cảnh",
      not (_d_sd / ".javis-agy").exists() and any(e["type"] == "final" for e in _evs_sd),
      _evs_sd)

antigravity_cli._no_window = _no_window_that


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
