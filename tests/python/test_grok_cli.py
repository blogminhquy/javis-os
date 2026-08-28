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
    json.dumps({"access_token": "t", "email": "ai@x.ai", "plan": "SuperGrok"}), encoding="utf-8")
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
