"""Bộ não thứ 11: Grok Build CLI (gói SuperGrok / X Premium+).

    python tests/run.py grok_cli        (KHÔNG mạng, KHÔNG cần cài grok)

Bốn chỗ dễ hỏng của mọi driver CLI, cộng hai chỗ riêng của engine này:

1. **Dịch sự kiện.** `--output-format streaming-json` phát NDJSON riêng (thought/tool_call/
   tool_call_update/text/usage/end). Dịch sai một loại là mất câu trả lời, mất mạch hội thoại,
   hoặc lượt nào cũng đỏ vì một dòng log vặt.
2. **Mức quyền.** Ba mức của Javis phải xuống đúng cờ chặn. Mức `suggest` mà không chặn được
   ghi file thì "chỉ đọc" chỉ còn là một lời hứa trong prompt.
3. **Không đăng nhập.** Phải thành một câu người dùng làm theo được, không phải nguyên văn
   tiếng Anh của xAI.
4. **Cô lập theo brain.** MCP hub ghi vào `<brain>/.grok/config.toml`, không đụng `~/.grok`
   của người dùng, và KHÔNG xoá mất phần cấu hình họ đã có trong đó.
5. **Dò cờ trước khi truyền** (`co_co`) - bản CLI này còn mới và đổi cờ liên tục; truyền một cờ
   chưa có là CLI thoát ngay với "unknown flag", hỏng cả lượt chat vì một tuỳ chọn phụ.
6. **Ghi TOML không được phá file.** `tomllib` chỉ đọc, phần ghi là serializer tự viết - nên
   phải chứng minh nó round-trip đúng, VÀ không ghi đè lên một file nó không đọc nổi.

Test dựng một `grok` GIẢ bằng script Python nên chạy được ở CI không có binary thật.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-groktest-")

import grok_cli          # noqa: E402
import main              # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name
          + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def chay(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


_HELP = """Usage: grok [OPTIONS] [COMMAND]
  -p, --single <PROMPT>          Direct prompt
      --prompt-file <PATH>       Read prompt from file
  -m, --model <MODEL>            Model
  -r, --resume <ID>              Resume session
      --output-format <FORMAT>   plain | json | streaming-json
      --permission-mode <MODE>   bypassPermissions | defaultMode
      --allow <RULE>
      --deny <RULE>
      --max-turns <N>
      --no-auto-update
      --device-auth
"""


def _nap_help(txt=_HELP, path="/fake/grok"):
    """Giả lập một máy CÓ `grok` và nhét sẵn `--help` vào cache.

    Phải stub cả `find_grok_cli`: `_help_text()` thoát ngay khi không tìm thấy binary, TRƯỚC
    khi nhìn tới cache - nên chỉ nhét cache thôi thì `co_co()` vẫn trả False.
    """
    grok_cli.find_grok_cli = lambda: path
    grok_cli._HELP_CACHE.update(path=path, text=txt, ts=float("inf"))


# ============================================================
# 1. Dò cờ: fail-closed khi không đọc được --help
# ============================================================
grok_cli._HELP_CACHE.update(path=None, text="", ts=0.0)
_that_find = grok_cli.find_grok_cli
grok_cli.find_grok_cli = lambda: None
check("CANARY: không đọc được --help -> co_co() trả False (thà thiếu cờ còn hơn 'unknown flag')",
      grok_cli.co_co("--output-format") is False)
_nap_help()
check("đọc được --help thì nhận đúng cờ có thật", grok_cli.co_co("--output-format") is True)
check("và KHÔNG nhận cờ bịa", grok_cli.co_co("--khong-he-co") is False)


# ============================================================
# 2. Mức quyền: ba mức của Javis -> cờ chặn của CLI
# ============================================================
def _deny(mode):
    a = grok_cli.permission_cho_mode(mode)
    return {a[i + 1] for i, x in enumerate(a) if x == "--deny"}


check("suggest CHẶN ghi file (chỉ đọc do CLI cưỡng chế, không phải lời hứa trong prompt)",
      {"Write(*)", "Edit(*)"} <= _deny("suggest"))
check("suggest CHẶN lệnh máy", "Bash(*)" in _deny("suggest"))
check("auto cho ghi file nhưng vẫn CHẶN lệnh máy",
      _deny("auto") == {"Bash(*)"})
check("full không chặn gì ở tầng CLI", _deny("full") == set())
for xau in ("", None, "FULL_QUYEN", "bậy bạ", "yolo"):
    check(f"CANARY: mode lạ ({xau!r}) rơi về nấc CHẶT NHẤT, không phải toàn quyền",
          {"Write(*)", "Edit(*)", "Bash(*)"} <= _deny(xau))
check("viết hoa vẫn nhận", _deny("Full") == set())
check("luôn đặt --permission-mode tường minh (headless mà dừng hỏi duyệt là treo tới hết giờ)",
      "--permission-mode" in grok_cli.permission_cho_mode("full"))


# ============================================================
# 3. argv dựng ra phải đúng hợp đồng của CLI
# ============================================================
_g = grok_cli.GrokCLI(cwd="/tmp", model="grok-4.6")
_g.cli_path = "/fake/grok"
_argv = _g._build_args(prompt_file="/tmp/p.txt", prompt_argv="dài" * 20000)
check("có --output-format streaming-json (không có thì không đọc được sự kiện nào)",
      "--output-format" in _argv and _argv[_argv.index("--output-format") + 1] == "streaming-json")
check("model đi qua --model",
      "--model" in _argv and _argv[_argv.index("--model") + 1] == "grok-4.6")
check("CANARY: prompt đi qua FILE, KHÔNG nằm trong argv "
      "(Windows chặn dòng lệnh ở 32767 ký tự)",
      "--prompt-file" in _argv and not any(len(x) > 30000 for x in _argv))
check("lượt đầu KHÔNG tự cấp id mạch (Grok sinh UUIDv7, Javis chỉ có uuid4)",
      "--session-id" not in _argv and "--resume" not in _argv)

# Tắt bộ tự cập nhật: Javis chạy `grok` headless trên VPS/container, để nó tự tải bản mới giữa
# lượt là in thêm chữ vào stdout (hỏng dòng NDJSON đang đọc) hoặc ghi vào chỗ chỉ đọc.
check("có --no-auto-update (bộ tự cập nhật xen vào giữa lượt là hỏng dòng NDJSON)",
      "--no-auto-update" in _argv)
_env = grok_cli._moi_truong()
check("và ĐỒNG THỜI đặt biến GROK_DISABLE_AUTOUPDATER - hai lớp phủ cho nhau",
      _env.get("GROK_DISABLE_AUTOUPDATER") == "1")
check("CANARY: môi trường vẫn KẾ THỪA của server (mất PATH là không tìm nổi binary nào)",
      bool(_env.get("PATH")))
_cu_env = os.environ.get("GROK_DISABLE_AUTOUPDATER")
os.environ["GROK_DISABLE_AUTOUPDATER"] = "0"
check("người dùng tự đặt khác thì TÔN TRỌNG, không đè (setdefault chứ không phải gán)",
      grok_cli._moi_truong().get("GROK_DISABLE_AUTOUPDATER") == "0")
if _cu_env is None:
    os.environ.pop("GROK_DISABLE_AUTOUPDATER", None)
else:
    os.environ["GROK_DISABLE_AUTOUPDATER"] = _cu_env

_g.session_id = "0195abcd-1111-7222-8333-444455556666"
_argv2 = _g._build_args(prompt_file="/tmp/p.txt")
check("có mạch cũ thì --resume đúng id",
      "--resume" in _argv2 and _argv2[_argv2.index("--resume") + 1] == _g.session_id)

# Bản CLI cũ không khai --prompt-file thì phải lùi về argv chứ không gãy
_nap_help("Usage: grok\n  -p, --single <PROMPT>\n")
_argv3 = _g._build_args(prompt_file="/tmp/p.txt", prompt_argv="chào")
check("bản CLI thiếu --prompt-file thì lùi về -p, không truyền cờ nó không có",
      "--prompt-file" not in _argv3 and _argv3[-2:] == ["-p", "chào"])
check("và cũng không truyền --output-format mà bản đó không khai",
      "--output-format" not in _argv3)
check("CANARY: bản CLI cũ cũng KHÔNG bị truyền --no-auto-update "
      "(biến môi trường vẫn phủ được ca này, cờ thì không)",
      "--no-auto-update" not in _argv3)
_nap_help()


# ============================================================
# 4. Dịch sự kiện streaming-json -> hợp đồng của Javis
# ============================================================
def _gia(dong_ra, ma=0, stderr=""):
    """Dựng một `grok` giả in ra đúng những dòng mình muốn."""
    d = Path(tempfile.mkdtemp(prefix="javis-fakegrok-"))
    p = d / "grok"
    body = json.dumps(dong_ra)
    p.write_text(
        "#!/usr/bin/env python3\n"
        "import sys, json\n"
        f"for l in {body}:\n"
        "    print(l, flush=True)\n"
        f"sys.stderr.write({stderr!r})\n"
        f"sys.exit({ma})\n",
        encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(p)


def _chay_gia(dong_ra, ma=0, stderr="", prompt="xin chào"):
    g = grok_cli.GrokCLI(cwd="/tmp")
    g.cli_path = _gia(dong_ra, ma, stderr)

    async def _go():
        return [ev async for ev in g.query(prompt)]
    return chay(_go()), g


_DONG = [
    json.dumps({"type": "thought", "text": "để tôi nghĩ đã"}),
    json.dumps({"type": "tool_call", "id": "t1", "name": "javis_read_file",
                "input": {"path": "MEMORY.md"}}),
    json.dumps({"type": "tool_call_update", "id": "t1", "status": "running"}),
    json.dumps({"type": "tool_call_update", "id": "t1", "status": "completed",
                "output": "nội dung file"}),
    json.dumps({"type": "text", "text": "Chào "}),
    json.dumps({"type": "text", "text": "bạn."}),
    json.dumps({"type": "usage", "input": 1200, "output": 45, "cache_read": 900}),
    json.dumps({"type": "end", "stopReason": "end_turn",
                "metadata": {"sessionId": "sess-42"}}),
]
_evs, _g3 = _chay_gia(_DONG)
_loai = [e["type"] for e in _evs]
_final = next((e for e in _evs if e["type"] == "final"), None)
check("mảnh chữ được GHÉP lại thành một câu trả lời",
      _final is not None and _final["content"] == "Chào bạn.", _final)
check("CANARY: `thought` KHÔNG lọt vào câu trả lời (lập luận nội bộ, không phải câu trả lời)",
      _final is not None and "nghĩ" not in _final["content"], _final)
check("tool_call -> tool_call kèm tên công cụ",
      any(e["type"] == "tool_call" and e.get("name") == "javis_read_file" for e in _evs))
check("CANARY: tool_call_update đang chạy dở KHÔNG thành tool_result "
      "(không thì mỗi tool báo kết quả hai lần)",
      len([e for e in _evs if e["type"] == "tool_result"]) == 1, _loai)
check("tool_call_update xong -> tool_result",
      any(e["type"] == "tool_result" and "nội dung file" in e.get("content", "") for e in _evs))
check("usage -> token vào/ra",
      any(e["type"] == "usage" and e.get("input_tokens") == 1200 for e in _evs))
check("id mạch từ `end` được giữ để lượt sau resume", _g3.session_id == "sess-42")

# stderr có chữ nhưng thoát 0: là LOG, không phải lỗi
_evs2, _ = _chay_gia(_DONG, ma=0, stderr="INFO thinking...\nDEBUG ok\n")
check("CANARY: thoát 0 mà stderr có log thì KHÔNG thành lỗi "
      "(ai đặt RUST_LOG là lượt nào cũng đỏ)",
      not any(e["type"] == "error" for e in _evs2), [e["type"] for e in _evs2])
check("và câu trả lời vẫn về đủ",
      any(e["type"] == "final" and e["content"] == "Chào bạn." for e in _evs2))

# Chưa đăng nhập: exit != 0, không dòng JSON nào
_evs3, _ = _chay_gia([], ma=1, stderr="Error: not authenticated")
_e3 = next((e for e in _evs3 if e["type"] == "error"), None)
check("chưa đăng nhập -> câu tiếng Việt làm theo được, không phải nguyên văn tiếng Anh",
      _e3 is not None and "đăng nhập" in _e3["content"] and "grok login" in _e3["content"], _e3)
check("và KHÔNG bịa thêm một câu trả lời rỗng",
      not any(e["type"] == "final" for e in _evs3))

# Không ra gì cả: phải nói là không ra gì, không im lặng
_evs4, _ = _chay_gia([], ma=0)
check("chạy xong mà không có nội dung -> nói thẳng, không im lặng",
      any(e["type"] == "error" for e in _evs4))

# Dòng không phải JSON thì GIỮ làm chữ, không vứt im lặng
_evs5, _ = _chay_gia(["đây không phải json"], ma=0)
check("CANARY: dòng không phải JSON được giữ làm chữ, không nuốt im lặng",
      any(e["type"] == "final" and "không phải json" in e["content"] for e in _evs5))

# end kèm stopReason=error
_evs6, _ = _chay_gia([json.dumps({"type": "end", "stopReason": "error",
                                  "message": "model bận"})])
check("end status=error -> sự kiện error",
      any(e["type"] == "error" and "model bận" in e.get("content", "") for e in _evs6))


# CLI treo im (headless mà dừng lại hỏi duyệt) -> watchdog phải cắt, không treo tới vô tận.
# Đây KHÔNG phải phòng xa: `permission_cho_mode()` fail-closed, nên trên một bản CLI không khai
# `--permission-mode` nó không truyền cờ nào, và lúc đó không có gì ngoài watchdog gỡ được.
_treo = Path(tempfile.mkdtemp(prefix="javis-grokhang-")) / "grok"
_treo.write_text("#!/usr/bin/env python3\nimport sys, time\n"
                 "if '--help' in sys.argv:\n    print('  -p, --single')\n"
                 "else:\n    time.sleep(60)\n", encoding="utf-8")
_treo.chmod(_treo.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
_gh = grok_cli.GrokCLI(cwd="/tmp")
_gh.cli_path = str(_treo)
_gh.timeout = 2
async def _go_treo():
    return [e async for e in _gh.query("hi")]


_t0 = __import__("time").time()
_evsh = chay(_go_treo())
_giay = __import__("time").time() - _t0
check("CANARY: CLI treo im bị watchdog cắt (không có nó là lượt chat treo tới vô tận)",
      _giay < 20, f"{_giay:.1f}s")
check("và nói rõ là bị cắt vì quá giờ, không im lặng",
      any("quá 2s" in str(e.get("content", "")) for e in _evsh), _evsh)

# File prompt tạm phải được dọn, kể cả ở lượt bị cắt giữa chừng
import glob  # noqa: E402
check("CANARY: file prompt tạm được dọn, không tích rác trong thư mục tạm",
      glob.glob(os.path.join(tempfile.gettempdir(), "javis-grok-*.txt")) == [])


# ============================================================
# 4b. Trạng thái đăng nhập đọc từ file, không đẻ tiến trình
# ============================================================
os.environ["GROK_HOME"] = tempfile.mkdtemp(prefix="javis-grokhome-")
os.environ.pop("XAI_API_KEY", None)
_a = grok_cli.auth_status()
check("chưa đăng nhập -> nói rõ phải làm gì",
      _a["connected"] is False and "Đăng nhập" in _a["error"], _a)
os.environ["XAI_API_KEY"] = "xai-abc"
check("có XAI_API_KEY thì coi như đã cấu hình (đường lùi cho CI)",
      grok_cli.auth_status()["method"] == "xai-api-key")
os.environ.pop("XAI_API_KEY", None)
Path(os.environ["GROK_HOME"], "auth.json").write_text(
    json.dumps({"access_token": "xai-oat-" + "t" * 32, "email": "ai@x.ai",
                "plan": "SuperGrok"}), encoding="utf-8")
_a2 = grok_cli.auth_status()
check("có auth.json thì đọc ra cả tài khoản và gói",
      _a2["connected"] and _a2["account"] == "ai@x.ai" and _a2["plan"] == "SuperGrok", _a2)


# ============================================================
# 5. MCP: cô lập theo brain, và KHÔNG phá cấu hình sẵn có
# ============================================================
_brain = Path(tempfile.mkdtemp(prefix="javis-grokbrain-"))
_hub = grok_cli.hub_entry("http://127.0.0.1:8790/mcp",
                          {"Authorization": "Bearer tok", "X-Javis-Mode": "full",
                           "X-Javis-Vault": str(_brain)})
check("CANARY: entry MCP dùng khoá `url` - KHÔNG phải `httpUrl` (Gemini) hay `serverUrl` (agy)",
      "url" in _hub and "httpUrl" not in _hub and "serverUrl" not in _hub, _hub)
_p = grok_cli.ghi_mcp_settings(_brain, _hub)
check("ghi vào TRONG brain, không đụng ~/.grok của người dùng",
      _p is not None and str(_brain) in _p and _p.endswith(".grok/config.toml"), _p)
_st = grok_cli.trang_thai_mcp(_brain)
check("đọc LẠI chính file vừa ghi thì thấy entry javis",
      _st["co_javis"] and _st["url"] == "http://127.0.0.1:8790/mcp" and _st["so_header"] == 3, _st)
try:
    check("file chứa hub token nên phải chmod 600",
          (os.stat(_p).st_mode & 0o077) == 0 or os.name == "nt")
except Exception:
    pass

# Người dùng đã có cấu hình riêng trong file đó -> giữ nguyên
Path(_p).write_text(Path(_p).read_text(encoding="utf-8")
                    + '\n[models]\ndefault = "grok-4.6"\n\n[tools]\nbash_timeout = 60\n'
                      'flag = true\ndomains = ["a.com", "b.com"]\n', encoding="utf-8")
grok_cli.ghi_mcp_settings(_brain, _hub)
import tomllib  # noqa: E402
_lai = tomllib.load(open(_p, "rb"))
check("CANARY: ghi lại hub KHÔNG xoá mất cấu hình sẵn có của người dùng",
      _lai.get("models", {}).get("default") == "grok-4.6"
      and _lai.get("tools", {}).get("bash_timeout") == 60
      and _lai.get("tools", {}).get("flag") is True
      and _lai.get("tools", {}).get("domains") == ["a.com", "b.com"], _lai)
check("và entry javis vẫn còn", "javis" in _lai.get("mcp_servers", {}))

# hub=None -> gỡ entry javis, giữ phần còn lại
grok_cli.ghi_mcp_settings(_brain, None)
_lai2 = tomllib.load(open(_p, "rb"))
check("tắt hub thì GỠ entry javis nhưng giữ nguyên phần còn lại",
      "javis" not in _lai2.get("mcp_servers", {})
      and _lai2.get("models", {}).get("default") == "grok-4.6", _lai2)

# File HỎNG -> tuyệt đối không ghi đè
_hong = '[mcp_servers.javis]\nurl = "quên đóng nháy\n'
Path(_p).write_text(_hong, encoding="utf-8")
_r = grok_cli.ghi_mcp_settings(_brain, _hub)
check("CANARY: file config.toml HỎNG thì KHÔNG ghi đè (thà thiếu tool còn hơn xoá cấu hình)",
      _r is None and Path(_p).read_text(encoding="utf-8") == _hong)
check("và trạng thái nói thẳng là chưa đấu được, không báo xanh giả",
      grok_cli.trang_thai_mcp(_brain)["co_javis"] is False)


# ============================================================
# 6. Đăng nhập device code: bóc link + mã từ dòng CLI in ra
# ============================================================
grok_cli._LOGIN.update(url="", code="")
grok_cli._bat_url_code("Open https://x.ai/device and enter code ABCD-EFGH")
check("bóc được link đăng nhập", grok_cli._LOGIN["url"] == "https://x.ai/device")
check("bóc được mã device code", grok_cli._LOGIN["code"] == "ABCD-EFGH")
grok_cli._LOGIN.update(url="", code="")
grok_cli._bat_url_code("Visit https://accounts.x.ai/activate")
grok_cli._bat_url_code("Your code: WXYZ-1234")
check("link và mã in ra hai dòng khác nhau vẫn bóc đủ",
      grok_cli._LOGIN["url"] == "https://accounts.x.ai/activate"
      and grok_cli._LOGIN["code"] == "WXYZ-1234")


# ============================================================
# 7. Đăng ký provider: thêm một bộ não phải chạm đủ chỗ, sót một chỗ là lỗi câm
# ============================================================
_MAIN = Path(SERVER, "main.py").read_text(encoding="utf-8")
check("có mặt trong PROVIDER_DEFS",
      any(d["id"] == "grok-cli" for d in main.PROVIDER_DEFS))
_d = next(d for d in main.PROVIDER_DEFS if d["id"] == "grok-cli")
check("kind=cli (đủ tư cách bộ não gói thuê bao có tool thật)", _d["kind"] == "cli")
check("CANARY: default_models RỖNG - tên model xAI đổi liên tục, bảng chép tay sai lặng lẽ",
      _d["default_models"] == [])
check("có nhánh ở _api_stream (thiếu là bot/tóm tắt/đặt tiêu đề rơi xuống anthropic key rỗng)",
      'prov == "grok-cli"' in _MAIN and "_grok_sub_stream(" in _MAIN)
check("có nhánh chat dashboard", 'elif prov == "grok-cli":' in _MAIN)
check("có hàm gắn MCP hub riêng", "def _apply_grok_hub(" in _MAIN)
check("có nhánh _set_main_model", 'm["engine"] = "grok-cli"' in _MAIN)
check("có nhánh _provider_models_live", "grok_cli.list_models" in _MAIN)

import config as _cfgmod          # noqa: E402
check("có ô catalog trong config mặc định",
      "grok-cli" in (_cfgmod._DEFAULT["model"]["catalog"]))

import sessions as _sess          # noqa: E402
check("CANARY: có cột mạch RIÊNG (dùng chung cột là đưa id engine này cho engine kia resume)",
      _sess.SessionStore._MACH_NATIVE.get("grok-cli") == "grok_session_id")
check("và có hàm ghi/xoá cột đó",
      hasattr(_sess.SessionStore, "set_grok_session_id")
      and hasattr(_sess.SessionStore, "clear_grok_session_id"))

import connect_health as _ch      # noqa: E402
check("đèn 'mất đăng nhập' nhận ra engine mới", "grok-cli" in _ch._PROVIDER_ENGINE)

import usage_index as _ui         # noqa: E402
check("báo cáo token có cột riêng", "grok-cli" in _ui._EVENT_GROK_CLI)

_CONSOLE = Path(ROOT, "dashboard", "console.js").read_text(encoding="utf-8")
check("trang Models có thẻ riêng", 'p.id === "grok-cli"' in _CONSOLE)
check("CANARY: thẻ CÓ nút Đăng nhập - đây là engine CLI duy nhất đăng nhập được trên VPS",
      "data-groklogin" in _CONSOLE and "/grok/login-start" in _CONSOLE)
check("thẻ có nút Kiểm tra lại và nút Ngắt",
      "data-grokcheck" in _CONSOLE and "data-grokdisc" in _CONSOLE)

# ============================================================
# 7. ĐỌC TRẠNG THÁI ĐĂNG NHẬP - chỗ đã hỏng thật ở 0.50.0
# ============================================================
# Người dùng báo 28/08/2026: bấm Đăng nhập trên thẻ, mở link, accounts.x.ai hiện "Device
# Authorized" - mà thẻ vẫn quay "đang chờ bạn xác nhận" mãi không đổi.
#
# Nguyên nhân hạng gốc: `auth_status` của 0.50.0 ĐOÁN sơ đồ `auth.json` (đòi `access_token`
# hoặc `refresh_token` nằm ngay tầng cao nhất) trong khi xAI KHÔNG tài liệu hoá trường nào
# cả - Giai đoạn 0 của kế hoạch có ghi rõ phải đo trước, và bước đó đã bị bỏ qua vì máy chưa
# cài `grok`. Đoán sai một tầng là Javis báo "chưa đăng nhập" vĩnh viễn dù đăng nhập đã xong.
#
# Nên nhóm test này canh HÌNH DẠNG, không canh một sơ đồ: token lồng ở đâu cũng phải nhận ra.
_HOME_CU = os.environ.get("GROK_HOME")
_TIM_CU = grok_cli.find_grok_cli
grok_cli.find_grok_cli = lambda: "/gia/grok"      # bỏ qua bước "đã cài chưa"


def _dat_auth(noi_dung, ten="auth.json"):
    d = tempfile.mkdtemp(prefix="javis-grokhome-")
    if noi_dung is not None:
        Path(d, ten).write_text(json.dumps(noi_dung, ensure_ascii=False), encoding="utf-8")
    os.environ["GROK_HOME"] = d
    return d


# Bốn hình dạng: phẳng (bản cũ đã đỡ được), lồng một tầng, tên khoá kiểu camelCase, và tên
# file khác. Ba cái sau là ba cách bản 0.50.0 hỏng câm.
for _ten, _shape in (
    ("phẳng như bản cũ vẫn đỡ được", {"access_token": "a" * 40, "email": "q@x.ai"}),
    ("token LỒNG một tầng", {"oauth": {"accessToken": "b" * 40}, "user": {"email": "q@x.ai"}}),
    ("chỉ có refresh token, viết camelCase", {"refreshToken": "c" * 40}),
    ("khoá tên trống trơn là `token`", {"session": {"token": "d" * 40}}),
):
    _dat_auth(_shape)
    check(f"nhận ra đã đăng nhập: {_ten}", grok_cli.auth_status().get("connected") is True,
          grok_cli.auth_status())

_dat_auth({"accessToken": "e" * 40}, ten="credentials.json")
check("CLI đổi tên file phiên thì vẫn nhận ra",
      grok_cli.auth_status().get("connected") is True, grok_cli.auth_status())

check("lấy được email để hiện lên thẻ",
      (_dat_auth({"oauth": {"access_token": "f" * 40}, "user": {"email": "q@x.ai"}}) and
       grok_cli.auth_status().get("account")) == "q@x.ai")

# Chiều ngược lại quan trọng ngang: đừng gật bừa.
_dat_auth({"token_type": "Bearer", "expires_in": 3600})
_d = grok_cli.auth_status()
check("CANARY: `token_type: Bearer` KHÔNG được tính là đã đăng nhập "
      "(gật bừa thì thẻ xanh mà chat lượt nào cũng đỏ)", _d.get("connected") is False, _d)
check("CANARY: và câu lỗi phải NÓI RA là có file mà không đọc được token - gộp chung với "
      "'chưa đăng nhập bao giờ' đúng là cái đã bắt người dùng bấm Đăng nhập lại vô ích",
      "không nhận ra token" in (_d.get("error") or ""), _d.get("error"))

_dat_auth({"token": "x"})
check("CANARY: chuỗi rác quá ngắn không phải token",
      grok_cli.auth_status().get("connected") is False)
# Ngưỡng độ dài phải ĐỦ THẤP để không chặn nhầm một token thật. Chặn nhầm ở đây là người dùng
# đăng nhập xong vẫn không vào được - đúng lỗi bản này đang chữa, nên đừng siết nó lên.
check("CANARY: ngưỡng độ dài token để THẤP, chỉ lọc rác chứ không đoán token dài bao nhiêu",
      grok_cli._TOKEN_DAI_TOI_THIEU <= 8, grok_cli._TOKEN_DAI_TOI_THIEU)

_dat_auth(None)
_moi = grok_cli.auth_status()
check("thư mục trống: báo chưa đăng nhập và chỉ đúng nút phải bấm",
      _moi.get("connected") is False and "Đăng nhập" in (_moi.get("error") or ""), _moi)

# Chẩn đoán: phải đủ để lần ra lỗi, và TUYỆT ĐỐI không lộ token.
_bi_mat = "g" * 40
_dat_auth({"oauth": {"access_token": _bi_mat}, "email": "q@x.ai"})
_cd = grok_cli.chan_doan()
check("chẩn đoán kể được thư mục và tên file",
      _cd["home_ton_tai"] and any(x["ten"] == "auth.json" for x in _cd["files"]), _cd)
check("chẩn đoán nói rõ có nhận ra token không", _cd["co_token"] is True, _cd)
check("CANARY: chẩn đoán KHÔNG chứa giá trị token - phần này hiện lên màn hình và đi vào "
      "ảnh chụp người dùng gửi đi",
      _bi_mat not in json.dumps(_cd, ensure_ascii=False), "LỘ TOKEN")

if _HOME_CU is None:
    os.environ.pop("GROK_HOME", None)
else:
    os.environ["GROK_HOME"] = _HOME_CU
grok_cli.find_grok_cli = _TIM_CU


# ============================================================
# 8. Bóc link/mã và giữ lại nhật ký của `grok login`
# ============================================================
grok_cli._LOGIN.update(url="", code="", log=None)
grok_cli._bat_url_code("Open https://accounts.x.ai/oauth2/device?user_code=N3FJ-B2J7 to continue")
check("bóc đúng link đăng nhập",
      grok_cli._LOGIN["url"] == "https://accounts.x.ai/oauth2/device?user_code=N3FJ-B2J7",
      grok_cli._LOGIN["url"])
check("CANARY: bóc được mã NẰM TRONG link - bản cũ cố ý bỏ qua ca này nên thẻ chỉ hiện link "
      "trần, đúng thứ ảnh chụp của người dùng cho thấy",
      grok_cli._LOGIN["code"] == "N3FJ-B2J7", grok_cli._LOGIN["code"])

check("link giữ nguyên trong nhật ký (người dùng còn phải bấm vào)",
      "accounts.x.ai" in grok_cli._che_bi_mat("Open https://accounts.x.ai/oauth2/device?a=1"))
check("CANARY: chuỗi dài trông như token thì CHE trước khi hiện ra màn hình",
      "h" * 45 not in grok_cli._che_bi_mat("saved token " + "h" * 45))
check("mã device code ngắn không bị che nhầm",
      "N3FJ-B2J7" in grok_cli._che_bi_mat("code: N3FJ-B2J7"))

from collections import deque as _dq      # noqa: E402
grok_cli._LOGIN["log"] = _dq(maxlen=grok_cli.NHAT_KY_TOI_DA)
for _i in range(grok_cli.NHAT_KY_TOI_DA + 25):
    grok_cli._ghi_nhat_ky(f"dòng {_i}")
check("nhật ký có TRẦN, không phình vô hạn trong RAM",
      len(grok_cli.nhat_ky_dang_nhap()) == grok_cli.NHAT_KY_TOI_DA,
      len(grok_cli.nhat_ky_dang_nhap()))

_CONSOLE_LOG = Path(ROOT, "dashboard", "console.js").read_text(encoding="utf-8")
check("CANARY: màn hình có hiện lại lời CLI khi chờ - bản cũ chỉ có một dòng 'đang chờ' quay "
      "mãi, nên không ai biết `grok login` kẹt ở đâu",
      "nhat_ky" in _CONSOLE_LOG and "grokLog" in _CONSOLE_LOG)
check("và vòng quay kiểm `connected` TRƯỚC khi kêu hết giờ",
      0 < _CONSOLE_LOG.find("d.connected") < _CONSOLE_LOG.find('t("models.timeout_login")'))


# ============================================================
# 9. CHẠY THẬT một vòng đăng nhập, đúng kịch bản người dùng gặp
# ============================================================
# Mấy mục trên kiểm từng mảnh. Mục này ghép lại: dựng một `grok login` GIẢ hành xử y như bản
# thật theo ảnh chụp của người dùng - in link kèm mã bằng `\r` (spinner, KHÔNG xuống dòng),
# đứng chờ, rồi mới ghi file phiên với token LỒNG trong `oauth`. Bản 0.50.0 hỏng ở cả hai chỗ
# đó, và không mục nào ở trên một mình chứng minh được cả chuỗi chạy thông.
_login_home = tempfile.mkdtemp(prefix="javis-grokhome-live-")
_d = Path(tempfile.mkdtemp(prefix="javis-fakelogin-"))
_p = _d / "grok"
_p.write_text(
    "#!/usr/bin/env python3\n"
    "import sys, json, time, os, pathlib\n"
    # spinner dùng \r: `readline` của bản cũ đứng chờ \n nên dòng này kẹt trong bộ đệm
    "sys.stdout.write('Waiting for browser...\\r')\n"
    "sys.stdout.write('Open https://accounts.x.ai/oauth2/device?user_code=N3FJ-B2J7\\r')\n"
    "sys.stdout.flush()\n"
    "time.sleep(1.2)\n"
    "h = pathlib.Path(os.environ['GROK_HOME']); h.mkdir(parents=True, exist_ok=True)\n"
    "(h/'auth.json').write_text(json.dumps({'oauth': {'accessToken': 'x'*40}},\n"
    "                                      ensure_ascii=False))\n"
    "print('Logged in as ai@x.ai')\n",
    encoding="utf-8")
_p.chmod(_p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

_HOME_CU2 = os.environ.get("GROK_HOME")
os.environ["GROK_HOME"] = _login_home
# Trỏ thẳng vào binary giả, và nhét sẵn `--help` vào cache thay vì để `co_co()` tự chạy nó:
# script giả này bỏ qua mọi tham số, nên gọi nó với `--help` là nó ghi luôn file phiên và
# lượt đo sau đó không còn nghĩa gì.
_nap_help(path=str(_p))

_r = grok_cli.login_start(cho_giay=8.0)
check("mở được vòng đăng nhập", _r.get("ok") is True, _r)
check("CANARY: bắt được link dù CLI in bằng `\\r` không xuống dòng - `readline` của bản cũ "
      "đứng chờ `\\n` nên dòng này kẹt lại tới lúc hết giờ",
      "accounts.x.ai" in (_r.get("url") or ""), _r)
check("và hiện luôn mã cho người dùng", _r.get("code") == "N3FJ-B2J7", _r.get("code"))

_t0b = __import__("time").time()
_tt = {}
while __import__("time").time() - _t0b < 15:
    _tt = grok_cli.login_trang_thai()
    if _tt.get("connected"):
        break
    __import__("time").sleep(0.3)
check("CANARY: người dùng xác nhận xong -> thẻ TỰ chuyển sang đã đăng nhập. "
      "Đây đúng là thứ đã không xảy ra, dù accounts.x.ai đã báo Device Authorized",
      _tt.get("connected") is True, _tt)
check("và vòng quay có mang theo lời CLI để màn hình nói được điều gì đó",
      any("Logged in" in x or "accounts.x.ai" in x for x in _tt.get("nhat_ky") or []),
      _tt.get("nhat_ky"))

grok_cli.logout_huy_tien_trinh()
if _HOME_CU2 is None:
    os.environ.pop("GROK_HOME", None)
else:
    os.environ["GROK_HOME"] = _HOME_CU2
grok_cli._HELP_CACHE.update(path=None, text="", ts=0.0)


# ============================================================
# 10. LƯỢT CHAT KHÔNG RA CHỮ - chỗ hỏng thứ hai người dùng gặp
# ============================================================
# Đăng nhập xong, gõ "chào grok", và nhận lại đúng một câu:
#
#     "Grok CLI chạy xong nhưng không trả về nội dung nào."
#
# Câu đó không nói được gì và không dẫn tới đâu. Nấp sau nó là HAI ca khác hẳn nhau, mà bản
# 0.50.2 gộp làm một:
#
#   a) CLI in ra JSON nhưng toàn loại sự kiện Javis chưa biết. Sơ đồ `streaming-json` là ĐOÁN
#      từ tài liệu, chưa từng đo trên máy thật - cùng hạng lỗi với `auth.json` ở 0.50.2.
#   b) CLI in ra ĐÚNG KHÔNG GÌ CẢ rồi thoát 0. Nhiều CLI coi `-p` là cờ BẬT chế độ headless,
#      còn `--prompt-file` chỉ là chỗ lấy nội dung.
#
# Hai ca cần hai cách chữa, nên test này canh riêng từng ca.
def _gia_kich_ban(than: str):
    """Dựng `grok` giả với thân hàm tự viết, và trỏ cả `co_co` vào nó."""
    d = Path(tempfile.mkdtemp(prefix="javis-grokq-"))
    q = d / "grok"
    q.write_text("#!/usr/bin/env python3\nimport sys, json\n" + than, encoding="utf-8")
    q.chmod(q.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(q)


def _chay(cli_path, prompt="chào grok"):
    g = grok_cli.GrokCLI(cwd="/tmp")
    g.cli_path = cli_path

    async def _go():
        return [e async for e in g.query(prompt)]
    return asyncio.run(_go()), g


# --- ca (a): JSON toàn loại lạ ---
_la = _gia_kich_ban(
    "print(json.dumps({'type': 'assistant_message', 'message': {'content': 'Chào bạn!'}}))\n"
    "print(json.dumps({'type': 'result_v2', 'sessionId': 'abc-123'}))\n")
_nap_help(path=_la)
_evs, _g = _chay(_la)
_fin = [e for e in _evs if e["type"] == "final"]
check("CANARY: sự kiện toàn loại LẠ nhưng có chữ -> vẫn vớt ra được câu trả lời, "
      "không trả về ô trống", _fin and "Chào bạn!" in _fin[0]["content"], _evs)

# --- ca (a2): loại lạ mà KHÔNG có chữ nào -> phải kể tên loại đã thấy ---
_la2 = _gia_kich_ban("print(json.dumps({'type': 'ping'}))\n"
                     "print(json.dumps({'type': 'heartbeat'}))\n")
_nap_help(path=_la2)
_evs2, _ = _chay(_la2)
_er = [e for e in _evs2 if e["type"] == "error"]
check("không vớt được chữ thì báo lỗi", bool(_er), _evs2)
check("CANARY: câu lỗi KỂ TÊN loại sự kiện đã thấy - đó là thứ duy nhất chỉ ra sơ đồ đã "
      "đổi ở đâu",
      _er and "ping" in _er[0]["content"] and "heartbeat" in _er[0]["content"],
      _er and _er[0]["content"])
check("và nói luôn nó in ra mấy dòng, kèm dòng đầu",
      _er and "2 dòng" in _er[0]["content"], _er and _er[0]["content"])

# --- ca (b): im hoàn toàn, thoát 0. Đúng thứ ảnh chụp người dùng cho thấy ---
# `--prompt-file` thì im, `-p` thì trả lời - mô phỏng CLI coi `-p` là cờ bật headless.
_im = _gia_kich_ban(
    "a = sys.argv[1:]\n"
    "if '-p' in a:\n"
    "    print(json.dumps({'type': 'text', 'text': 'chào anh'}))\n"
    "sys.exit(0)\n")
_nap_help(path=_im)
_evs3, _ = _chay(_im)
_fin3 = [e for e in _evs3 if e["type"] == "final"]
check("CANARY: `--prompt-file` ra rỗng thì THỬ LẠI bằng `-p` trên dòng lệnh, và lượt chat "
      "vẫn có câu trả lời thay vì một ô trống",
      _fin3 and "chào anh" in _fin3[0]["content"], _evs3)

# --- ca (b2): im hoàn toàn ở CẢ HAI đường -> câu lỗi phải dùng được ---
_im2 = _gia_kich_ban("sys.exit(0)\n")
_nap_help(path=_im2)
_evs4, _ = _chay(_im2)
_er4 = [e for e in _evs4 if e["type"] == "error"]
check("im ở cả hai đường thì báo lỗi", bool(_er4), _evs4)
_t4 = _er4[0]["content"] if _er4 else ""
check("CANARY: câu lỗi nói rõ CLI không in ra gì và mã thoát là bao nhiêu",
      "KHÔNG in ra gì" in _t4 and "mã thoát 0" in _t4, _t4)
check("và đưa lệnh chạy tay để người dùng tự soi", "grok -p" in _t4, _t4)
check("kể cả cờ đã truyền", "--output-format" in _t4, _t4)

# Prompt TUYỆT ĐỐI không được lọt vào câu lỗi: nó là system prompt + ngữ cảnh brain.
_evs5, _ = _chay(_im2, prompt="BÍ MẬT CỦA NGƯỜI DÙNG cần giữ kín")
_t5 = "".join(e.get("content") or "" for e in _evs5)
check("CANARY: câu lỗi KHÔNG chứa nội dung prompt (system prompt + ngữ cảnh brain nằm trong "
      "đó, và câu lỗi thì hiện lên màn hình rồi vào ảnh chụp)",
      "BÍ MẬT CỦA NGƯỜI DÙNG" not in _t5, _t5[:200])

# Đường bình thường KHÔNG được đi qua phần vớt: vớt hai lần là chữ nhân đôi.
_thuong = _gia_kich_ban(
    "print(json.dumps({'type': 'text', 'text': 'một hai '}))\n"
    "print(json.dumps({'type': 'text', 'text': 'ba'}))\n"
    "print(json.dumps({'type': 'end', 'stopReason': 'stop'}))\n")
_nap_help(path=_thuong)
_evs6, _ = _chay(_thuong)
_fin6 = [e for e in _evs6 if e["type"] == "final"]
check("CANARY: lượt bình thường trả về ĐÚNG một lần chữ, không nhân đôi vì phần vớt",
      _fin6 and _fin6[0]["content"] == "một hai ba", _fin6)

# ============================================================
# 11. LUỒNG THẬT của Grok, đo từ máy người dùng ngày 29/08
# ============================================================
# Phần chẩn đoán thêm ở 0.50.3 đã làm đúng việc của nó và trả về nguyên văn:
#
#   "Grok CLI in ra 40 dòng nhưng Javis không nhận ra loại sự kiện nào là câu trả lời
#    (thấy: available_commands, thought). Dòng đầu CLI in ra:
#    {"type":"available_commands","tools":["run_terminal_command","read_file",...]}"
#
# Hai điều rút ra, và cả hai đều là lỗi của chính phần chẩn đoán:
#
#   1. Sơ đồ sự kiện thật KHÔNG giống bảng Javis đoán. `available_commands` và `thought` không
#      hề có trong tài liệu Javis dựa vào.
#   2. Trần 40 dòng chỉ giữ phần ĐẦU, mà câu trả lời của model luôn nằm ở CUỐI - sau bảng khai
#      báo tool và một tràng `thought`. Nên nó chẩn được phần mở đầu và mù đúng phần cần nhìn.
#      Trần 30 sự kiện cho danh sách LOẠI cũng vậy: 40 dòng `thought` ăn hết chỗ.
_DAU = json.dumps({"type": "available_commands",
                   "tools": ["run_terminal_command", "read_file", "grep", "todo_write"]})
_NGHI = json.dumps({"type": "thought", "text": "đang nghĩ"})


def _luong_that(cuoi_json, so_nghi=40):
    """`grok` giả phát đúng khuôn luồng thật: khai báo tool -> một tràng thought -> kết."""
    return _gia_kich_ban(
        f"print({_DAU!r})\n"
        f"for _ in range({so_nghi}):\n"
        f"    print({_NGHI!r})\n"
        f"print({cuoi_json!r})\n")


# --- Câu trả lời nằm ở CUỐI, dưới một loại Javis chưa biết ---
_cuoi = json.dumps({"type": "assistant_turn_complete",
                    "message": {"content": "Chào anh, em nghe đây."}})
_cli = _luong_that(_cuoi)
_nap_help(path=_cli)
_evs, _ = _chay(_cli, "hello em")
_fin = [e for e in _evs if e["type"] == "final"]
check("CANARY: câu trả lời ở CUỐI luồng vẫn ra được - trần cũ giữ 40 dòng ĐẦU nên đúng chỗ "
      "này bị cắt mất (ảnh chụp người dùng 29/08)",
      _fin and "Chào anh, em nghe đây." in _fin[0]["content"], _evs[-3:])
check("CANARY: bảng khai báo tool KHÔNG bị vớt nhầm thành câu trả lời",
      _fin and "run_terminal_command" not in _fin[0]["content"], _fin)
check("CANARY: và `thought` cũng không - đó là lập luận nội bộ, không phải câu trả lời",
      _fin and "đang nghĩ" not in _fin[0]["content"], _fin)

# --- Không có câu trả lời: câu lỗi phải kể được DÒNG CUỐI và ĐỦ loại ---
_cli2 = _luong_that(json.dumps({"type": "stream_closed", "reason": "done"}))
_nap_help(path=_cli2)
_evs2, _ = _chay(_cli2, "hello em")
_er = [e for e in _evs2 if e["type"] == "error"]
_t = _er[0]["content"] if _er else ""
check("không có câu trả lời thì vẫn báo lỗi", bool(_er), _evs2)
check("CANARY: câu lỗi kể được DÒNG CUỐI (bản cũ chỉ in dòng đầu, mà dòng đầu luôn là "
      "bảng khai báo tool nên dẫn sai hướng)", "stream_closed" in _t, _t)
check("CANARY: danh sách loại không bị `thought` chiếm hết chỗ - loại là TẬP, không phải "
      "30 sự kiện đầu tiên",
      "available_commands" in _t and "stream_closed" in _t and "thought" in _t, _t)
check("có nói bao nhiêu dòng, và số đó là số THẬT chứ không phải trần",
      f"{2 + 40} dòng" in _t, _t)

# --- Lượt hai: streaming-json hụt thì đổi sang `--output-format json` ---
# Bản 0.50.3 chỉ thử lại khi stdout RỖNG, nên ca thật ở trên (40 dòng, không chữ) không hề
# chạm tới đường này. Điều kiện đúng là "chưa ra chữ", không phải "chưa in gì".
_hai_duong = _gia_kich_ban(
    "a = sys.argv[1:]\n"
    "if 'json' in a:\n"
    "    print(json.dumps({'text': 'Chào anh (đường json).'}))\n"
    "else:\n"
    f"    print({_DAU!r})\n"
    f"    print({_NGHI!r})\n"
    "sys.exit(0)\n")
_nap_help(path=_hai_duong)
_evs3, _ = _chay(_hai_duong, "hello em")
_fin3 = [e for e in _evs3 if e["type"] == "final"]
check("CANARY: streaming-json in ra dòng mà không ra chữ -> thử lại bằng `--output-format "
      "json`, và lượt chat có câu trả lời",
      _fin3 and "đường json" in _fin3[0]["content"], _evs3)

# --- Trần bộ đệm vẫn phải có, kẻo một câu trả lời dài nằm hết trong RAM ---
check("bộ đệm chẩn đoán có trần cả hai đầu",
      grok_cli._CHAN_DAU_TOI_DA > 0 and grok_cli._CHAN_DUOI_TOI_DA > 0)
_chan = grok_cli._chan_moi()
_chan["so_dong"] = 500
for _i in range(grok_cli._CHAN_DAU_TOI_DA):
    _chan["raw"].append(f"đầu {_i}")
for _i in range(300):
    _chan["duoi"].append(f"đuôi {_i}")
_d = grok_cli._chan_dong(_chan)
check("giữ cả đầu lẫn đuôi, có dấu cắt ở giữa",
      _d[0] == "đầu 0" and _d[-1] == "đuôi 299" and any("lược" in x for x in _d), _d[:3])
check("và KHÔNG phình vô hạn",
      len(_d) <= grok_cli._CHAN_DAU_TOI_DA + grok_cli._CHAN_DUOI_TOI_DA + 1, len(_d))

# ============================================================
# 12. MẪU VÀNG: luồng streaming-json THẬT, dán nguyên từ máy người dùng
# ============================================================
# Đây là thứ đáng lẽ phải có từ Giai đoạn 0 của kế hoạch, và việc thiếu nó đã đẻ ra bốn bản
# vá đi vòng quanh. Người dùng chạy trên VPS ngày 29/08:
#
#     $ grok -p "chào" --output-format streaming-json | tail -5
#     {"type":"text","data":" nay"}
#     {"type":"text","data":"?"}
#     {"type":"available_commands","tools":[...],"commands":[...]}
#     {"type":"usage","usage":{"input_tokens":9028,...},"signature":"..."}
#     {"type":"end","stopReason":"end_turn","sessionId":"01a04b69-...","usage":{...}}
#
# Ba chỗ lệch so với bảng Javis ĐOÁN, và cái đầu tiên là gốc rễ của cả chuỗi lỗi:
#
#   1. Chữ nằm ở khoá `data`, KHÔNG phải `text`. Javis dò `text`/`content`/`delta` nên mọi sự
#      kiện text trả về chuỗi rỗng - lượt chạy đúng, model trả lời đúng, người dùng thấy ô
#      trống. Bản 0.50.5 vẫn hỏng y nguyên vì `text` là loại ĐÃ BIẾT nên không đi qua đường vớt.
#   2. Sự kiện `usage` BỌC số liệu trong khoá `usage`; đọc tầng ngoài là mọi lượt vào bảng Mức
#      dùng với 0 token.
#   3. Tên khoá token là `input_tokens` / `cache_read_input_tokens`.
_MAU_VANG = [
    "{\"type\":\"text\",\"data\":\"Chào\"}",
    "{\"type\":\"text\",\"data\":\" anh,\"}",
    "{\"type\":\"text\",\"data\":\" khỏe không\"}",
    "{\"type\":\"text\",\"data\":\" nay\"}",
    "{\"type\":\"text\",\"data\":\"?\"}",
    "{\"type\":\"available_commands\",\"tools\":[\"run_terminal_command\",\"read_file\",\"search_replace\",\"list_dir\",\"grep\",\"web_search\",\"image_gen\",\"write\"],\"commands\":[\"compact\",\"context\",\"review\"]}",
    "{\"type\":\"usage\",\"usage\":{\"input_tokens\":9028,\"output_tokens\":54,\"cache_read_input_tokens\":4352,\"cache_creation_input_tokens\":0,\"reasoning_tokens\":32},\"signature\":\"3+dBOy9tPOFi4\"}",
    "{\"type\":\"end\",\"stopReason\":\"end_turn\",\"sessionId\":\"01a04b69-8bcc-71c3-8cab-4c2320bd28c2\",\"requestId\":\"8ffd587e\",\"usage\":{\"input_tokens\":9028,\"cache_read_input_tokens\":4352,\"cache_creation_input_tokens\":0,\"output_tokens\":54,\"reasoning_tokens\":32,\"total_tokens\":13434},\"num_turns\":1,\"total_cost_usd\":0.020556}"
]

_vang = _gia_kich_ban(
    "for l in " + repr(_MAU_VANG) + ":\n"
    "    print(l)\n")
_nap_help(path=_vang)
_evs_v, _g_v = _chay(_vang, "chào")
_fin_v = [e for e in _evs_v if e["type"] == "final"]
check("CANARY: luồng THẬT ra đúng câu trả lời - khoá chữ là `data`, và bốn bản trước dò "
      "`text`/`content`/`delta` nên lượt nào cũng ra ô trống",
      _fin_v and _fin_v[0]["content"] == "Chào anh, khỏe không nay?", _fin_v)
check("CANARY: bảng `available_commands` ở CUỐI luồng không lọt vào câu trả lời",
      _fin_v and "run_terminal_command" not in _fin_v[0]["content"], _fin_v)

_us = [e for e in _evs_v if e["type"] == "usage"]
check("có sự kiện Mức dùng", bool(_us), _evs_v)
check("CANARY: đọc đúng token dù số liệu BỌC trong khoá `usage` (đọc tầng ngoài là mọi lượt "
      "Grok vào bảng Mức dùng với 0 token)",
      _us and _us[0]["input_tokens"] == 9028 and _us[0]["output_tokens"] == 54,
      _us[:1])
check("đọc đúng token đọc-từ-cache (`cache_read_input_tokens`)",
      _us and any(e.get("cached") == 4352 for e in _us), _us)
check("tổng token lấy từ `total_tokens` của sự kiện end",
      any(e.get("total_tokens") == 13434 for e in _us), _us)

check("CANARY: nhặt được sessionId từ `end` để lượt sau `--resume` nối đúng mạch",
      _g_v.session_id == "01a04b69-8bcc-71c3-8cab-4c2320bd28c2", _g_v.session_id)

# Và KHÔNG được thử lại lần hai: lượt này ra chữ rồi, chạy thêm là tốn một lượt model.
check("CANARY: lượt ra chữ thì KHÔNG chạy lại lần hai", len(_fin_v) == 1, _evs_v)

grok_cli._HELP_CACHE.update(path=None, text="", ts=0.0)
grok_cli.find_grok_cli = _that_find


_CLAUDEMD = Path(ROOT, "CLAUDE.md").read_text(encoding="utf-8")
check("CANARY: CLAUDE.md đã kể tên bộ não mới "
      "(câu này vào system prompt MỖI LƯỢT CHAT, sai là Javis nói sai với mọi người dùng)",
      "Grok Build" in _CLAUDEMD and "Ten brains" in _CLAUDEMD)
check("và đã đếm lại số engine CLI", "three CLI engines" in _CLAUDEMD)
check("CANARY: Gemini CLI đã gỡ khỏi system prompt (đường đó đã chết)",
      "Gemini CLI was removed" in _CLAUDEMD)


print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + "; ".join(_fails))
else:
    print("XANH: tất cả đều đạt")
sys.exit(1 if _fails else 0)
