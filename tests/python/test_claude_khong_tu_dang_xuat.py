"""Claude Code hết "thi thoảng tự đăng xuất": vệ sĩ credentials + kill có ân hạn.

    python tests/run.py claude_khong_tu_dang_xuat     (KHÔNG mạng, KHÔNG cần cài claude)

Chủ báo 16/08: thi thoảng Claude Code bị đăng xuất phải đăng nhập lại, còn ChatGPT thì
không bao giờ. Bất đối xứng đó chính là manh mối: token ChatGPT do CHÍNH JAVIS giữ và
ghi nguyên tử; còn Claude CLI TỰ quản ~/.claude/.credentials.json và tự ghi lại mỗi lần
refresh OAuth - trong khi Javis chạy nhiều tiến trình claude song song VÀ có watchdog
SIGKILL tiến trình treo. Kill rơi đúng lúc CLI đang ghi file token là file cụt nửa
chừng, lượt sau CLI đọc không ra và coi như chưa đăng nhập. Repo còn ghi sẵn bài học
cùng họ ở connect_health.py: "tự refresh làm user bị đăng xuất".

Vá 2 tầng, test ghim cả hai:
1. _kill_tree: TERM cả nhóm trước, chờ ân hạn cho tiến trình kịp đóng file, lì mới KILL.
2. giu_credentials: bản lành → sao lưu; file hỏng/mất → phục hồi từ sao lưu + hô to;
   đăng xuất CHỦ ĐỘNG → xoá sao lưu, không "hồi sinh" phiên người dùng vừa ngắt.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import subprocess
import sys
import tempfile
import time
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


import claude_cli  # noqa: E402

CRED_LANH = json.dumps({"claudeAiOauth": {
    "accessToken": "sk-ant-test", "refreshToken": "rt-test", "expiresAt": 9999999999}})

_td = tempfile.TemporaryDirectory()
_home = Path(_td.name)
(_home / ".claude").mkdir()
_that_home = claude_cli._home_dir
claude_cli._home_dir = lambda: _home
try:
    p = _home / ".claude" / ".credentials.json"
    b = _home / ".claude" / ".credentials.json.javis-bak"

    # ---- 0. Máy chưa từng đăng nhập (macOS Keychain cũng rơi vào đây) → im lặng ----
    check("chưa có file + chưa có sao lưu → không làm gì", claude_cli.giu_credentials() == "")
    check("không tự đẻ file", not p.exists() and not b.exists())

    # ---- 1. Bản lành → sao lưu ----
    p.write_text(CRED_LANH, encoding="utf-8")
    check("bản lành → sao lưu", claude_cli.giu_credentials() == "backup")
    check("bản sao lưu đúng nội dung", b.read_text(encoding="utf-8") == CRED_LANH)
    check("không đổi thì không ghi lại", claude_cli.giu_credentials() == "")

    # ---- 2. File CỤT NỬA CHỪNG (kill giữa lúc ghi) → phục hồi ----
    p.write_text(CRED_LANH[: len(CRED_LANH) // 2], encoding="utf-8")   # JSON đứt đôi
    check("CANARY: file hỏng → PHỤC HỒI từ sao lưu", claude_cli.giu_credentials() == "restore")
    check("nội dung về lại nguyên bản lành", p.read_text(encoding="utf-8") == CRED_LANH)

    # ---- 3. File BIẾN MẤT → phục hồi ----
    p.unlink()
    check("CANARY: file mất → phục hồi", claude_cli.giu_credentials() == "restore")
    check("file sống lại", _cred := p.read_text(encoding="utf-8") == CRED_LANH)

    # ---- 4. Đăng xuất TỬ TẾ (JSON lành, không còn token) → tôn trọng, xoá sao lưu ----
    p.write_text(json.dumps({"claudeAiOauth": {}}), encoding="utf-8")
    check("CANARY: đăng xuất chủ động → xoá sao lưu, KHÔNG hồi sinh",
          claude_cli.giu_credentials() == "logout" and not b.exists())
    check("vòng sau cũng không phục hồi gì", claude_cli.giu_credentials() in ("logout", ""))
finally:
    claude_cli._home_dir = _that_home
    _td.cleanup()

# ---- 5. _kill_tree: TERM trước, KILL sau ----
if os.name == "nt":
    print("ok   (bỏ qua phần kill - Windows dùng taskkill /T)")
else:
    # Tiến trình NGOAN: bắt TERM rồi thoát sạch → không bao giờ ăn SIGKILL.
    ngoan = subprocess.Popen(["bash", "-c", "trap 'exit 7' TERM; sleep 300 & wait"],
                             start_new_session=True)
    time.sleep(0.3)
    # Buộc vào ÂN HẠN thật thay vì một con số chép tay. Bản cũ chốt 2.5s, mà ân hạn chỉ
    # 2.0s - tức là ngưỡng ấy nằm NGOÀI ân hạn nên nó xanh kể cả khi tiến trình ăn trọn ân
    # hạn rồi mới bị KILL, đúng thứ nó sinh ra để bắt. Thoát tử tế thì vòng chờ nhả ngay ở
    # nhịp 0.1s đầu tiên, nên "dưới trọn ân hạn" vừa đúng ý vừa dư biên gấp nhiều lần.
    AN_HAN_S = 2.0
    t0 = time.time()
    claude_cli._kill_tree(ngoan, grace_s=AN_HAN_S)
    mat = time.time() - t0
    check("CANARY: tiến trình bắt TERM được thoát TỬ TẾ (kịp đóng file token)",
          ngoan.poll() is not None and ngoan.returncode == 7)
    check(f"và thoát nhanh, KHÔNG cần hết ân hạn {AN_HAN_S}s (thật: {mat:.2f}s)",
          mat < AN_HAN_S)

    # Tiến trình LÌ (phớt lờ TERM): hết ân hạn phải bị KILL - không được sống mãi.
    li = subprocess.Popen(["bash", "-c", "trap '' TERM; sleep 300"], start_new_session=True)
    time.sleep(0.3)
    claude_cli._kill_tree(li, grace_s=0.6)
    time.sleep(0.3)
    check("tiến trình lì vẫn bị KILL sau ân hạn", li.poll() is not None)

# ---- 6. Dây nối ----
src = (SERVER / "main.py").read_text(encoding="utf-8")
check("server có vòng vệ sĩ định kỳ", "giu_credentials" in src)
src_c = (SERVER / "claude_cli.py").read_text(encoding="utf-8")
check("Ngắt trên UI xoá luôn bản sao lưu (tôn trọng ý người dùng)",
      "_cred_bak_path().unlink" in src_c)
check("mất đăng nhập thật thì log CÓ GIỜ để truy vết", "ĐÃ ĐĂNG XUẤT" in src_c)

if _fails:
    print(f"\nFAIL {len(_fails)} muc: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_claude_khong_tu_dang_xuat: tat ca pass")
