"""Đăng nhập agy sống qua update image + thẻ Models nói thật khi máy thiếu binary CLI.

    python tests/run.py docker_giu_home_va_cli     (KHÔNG mạng)

Hai báo cáo 16/08:
1. "Mỗi lần cập nhật là mất đăng nhập Antigravity" - agy do user tự cài vào ~/.local/bin,
   đăng nhập nằm trong ~/.antigravity / ~/.config, mà HOME của container KHÔNG nằm trên
   volume nào (chỉ /data, /brains, ~/.claude, ~/.codex). Update = container mới = HOME
   mới tinh → bay cả binary lẫn đăng nhập, lần nào cũng vậy. Fix: entrypoint link các
   thư mục đó vào /data/home (volume sẵn có, KHÔNG cần user sửa compose).
2. "Người mới cài không có codex... kết nối được nhưng không sử dụng được" - hai lỗ:
   image từng phát hành với codex cài best-effort (lỗi bị nuốt bằng `|| echo`), và thẻ
   Codex báo "Đã kết nối" thuần theo OAuth token (Javis tự lo, không cần binary) nên
   thiếu binary vẫn xanh, vào chat mới vỡ. Fix: build thiếu codex phải ĐỎ, và thẻ
   Models lộ cli_found để cảnh báo ngay tại chỗ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


EP = ROOT / "docker" / "entrypoint.sh"
check("có docker/entrypoint.sh", EP.is_file())
check("entrypoint có quyền thực thi (git giữ bit +x)", os.access(EP, os.X_OK))


def chay_ep(home, persist, cmd=("sh", "-c", "echo DA_CHAY")):
    env = dict(os.environ, HOME=str(home), JAVIS_HOME_PERSIST=str(persist))
    return subprocess.run(["sh", str(EP), *cmd], env=env, capture_output=True,
                          text=True, timeout=30)


if os.name == "nt":
    print("ok   (bỏ qua phần chạy entrypoint - script POSIX, image là Linux)")
else:
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        persist = Path(td) / "data" / "home"
        # Hiện trường: user ĐÃ cài agy trong container hiện tại (trước khi có bản này).
        (home / ".local" / "bin").mkdir(parents=True)
        (home / ".local" / "bin" / "agy").write_text("#!/bin/sh\necho agy\n")
        (home / ".antigravity").mkdir()
        (home / ".antigravity" / "auth.db").write_text("token-cu")
        # ...và đã đăng nhập Grok Build (báo cáo 29/08, xem khối dưới).
        (home / ".local" / "bin" / "grok").write_text("#!/bin/sh\necho grok\n")
        (home / ".grok").mkdir()
        (home / ".grok" / "auth.json").write_text('{"oauth": {"accessToken": "xai-cu"}}')

        r = chay_ep(home, persist)
        check("entrypoint exec lệnh chính (server vẫn lên)", r.returncode == 0
              and "DA_CHAY" in r.stdout)
        # `.gemini` vào danh sách từ 0.43.0: `agy` để cấu hình MCP ở
        # ~/.gemini/config/mcp_config.json (chỗ Javis đấu hub vào) và token OAuth của MCP
        # ở đó. Thiếu nó thì cập nhật xong là mất sạch kết nối MCP người dùng tự thêm.
        # `.grok` vào danh sách từ 0.50.4. Người dùng báo 29/08: "mỗi lần nâng cấp bản mới
        # là grok lại bị logout". Đúng hạng lỗi của `agy` hồi 16/08, chỉ khó thấy hơn một
        # bậc - binary `grok` nằm ở ~/.local/bin nên VẪN CÒN sau update, thẻ Models vẫn báo
        # "Đã cài CLI", nên trông như một lỗi đăng nhập chứ không phải lỗi ổ đĩa.
        for d in (".local", ".antigravity", ".config", ".gemini", ".grok"):
            check(f"CANARY: ~/{d} thành symlink vào volume",
                  (home / d).is_symlink()
                  and str((home / d).resolve()).startswith(str(persist.resolve())))
        check("agy đã cài trước đó được DỌN SANG volume, không mất",
              (persist / ".local" / "bin" / "agy").is_file()
              and (home / ".local" / "bin" / "agy").is_file())
        check("đăng nhập cũ đi theo", (persist / ".antigravity" / "auth.db").read_text()
              == "token-cu")
        check("đăng nhập Grok cũng được dọn sang volume",
              (persist / ".grok" / "auth.json").read_text() == '{"oauth": {"accessToken": "xai-cu"}}')

        # Update kế tiếp: container MỚI, HOME mới tinh, volume còn nguyên.
        home2 = Path(td) / "home2"
        home2.mkdir()
        r2 = chay_ep(home2, persist)
        check("CANARY: sau 'update' (HOME mới) agy + đăng nhập VẪN CÒN",
              r2.returncode == 0 and (home2 / ".local" / "bin" / "agy").is_file()
              and (home2 / ".antigravity" / "auth.db").read_text() == "token-cu")
        check("CANARY: và Grok KHÔNG bị logout sau update - đúng lỗi người dùng báo 29/08",
              (home2 / ".grok" / "auth.json").read_text()
              == '{"oauth": {"accessToken": "xai-cu"}}')
        check("binary grok cũng còn (nó vốn đã còn - đó là lý do lỗi này khó thấy)",
              (home2 / ".local" / "bin" / "grok").is_file())

        # Bản trên volume là bản SỐNG QUA UPDATE - nội dung mới tinh trong HOME không đè nó.
        home3 = Path(td) / "home3"
        (home3 / ".antigravity").mkdir(parents=True)
        (home3 / ".antigravity" / "auth.db").write_text("rong-moi-tinh")
        chay_ep(home3, persist)
        check("nội dung volume THẮNG nội dung home mới (không mất đăng nhập)",
              (persist / ".antigravity" / "auth.db").read_text() == "token-cu")

        # /data hỏng (mkdir fail) → bỏ link nhưng server VẪN LÊN, không chết app.
        hong = Path(td) / "chan.txt"
        hong.write_text("file thường, không mkdir con được")
        home4 = Path(td) / "home4"
        home4.mkdir()
        r4 = chay_ep(home4, hong / "sub")
        check("volume hỏng thì server vẫn lên (nhịn lỗi, không crash)",
              r4.returncode == 0 and "DA_CHAY" in r4.stdout)

# ---- Dockerfile: codex hết best-effort + entrypoint được nối dây ----
df = (ROOT / "Dockerfile").read_text(encoding="utf-8")
dong_codex = next((l for l in df.splitlines() if "npm install -g @openai/codex" in l), "")
check("CANARY: cài codex KHÔNG còn nuốt lỗi (thiếu codex là build đỏ, hết ship image què)",
      dong_codex != "" and "||" not in dong_codex)
check("codex --version vẫn là cổng kiểm sau cài", "codex --version" in df)
check("ENTRYPOINT chạy qua entrypoint.sh", "/app/docker/entrypoint.sh" in df)

# Danh sách thư mục nằm trong MỘT dòng `for` của entrypoint. Canh thẳng vào đó: thêm một
# engine CLI mới mà quên dòng này là người dùng bị đăng xuất mỗi lần cập nhật, im lặng, và
# triệu chứng trông giống hệt lỗi đăng nhập nên đi lần nhầm hướng (đã xảy ra hai lần).
_ep = EP.read_text(encoding="utf-8")
_dong_for = next((l for l in _ep.splitlines() if l.startswith("for d in ")), "")
for _d in (".local", ".antigravity", ".config", ".gemini", ".grok"):
    check(f"CANARY: entrypoint còn giữ {_d} trong danh sách", _d in _dong_for)

# ---- Trang Models nói thật khi thiếu binary ----
src = (SERVER / "main.py").read_text(encoding="utf-8")
check("CANARY: thẻ Codex lộ cli_found (OAuth xanh không còn che được máy thiếu binary)",
      'item["cli_found"] = bool(find_codex_cli())' in src)
check("thẻ Claude Code cũng kiểm binary", 'item["cli_found"] = bool(find_claude_cli())' in src)

cjs = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("UI có cảnh báo thiếu CLI ngay trên thẻ provider",
      "cliWarn" in cjs and 'cliWarn("codex")' in cjs and 'cliWarn("claude")' in cjs)
check("cảnh báo chỉ nổ khi cli_found === false (thẻ không thuộc diện thì im)",
      "p.cli_found === false" in cjs)

if _fails:
    print(f"\nFAIL {len(_fails)} muc: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_docker_giu_home_va_cli: tat ca pass")
