"""Chỉ số token phải ĐỌC TIẾP transcript, không parse lại từ đầu mỗi lần.

Bối cảnh (đo 2026-09-21 trên máy chủ dự án, chủ repo báo trang Mức dùng "mỗi lần vào cũng rất
lag"): `~/.claude/projects` có 651 file và 602 MB, file to nhất 25 MB. Bản cũ của `_scan_claude`
thấy size/mtime đổi là `_clear_file` rồi parse LẠI CẢ FILE từ dòng đầu, trong khi transcript
phiên chỉ được GHI THÊM vào cuối. Một phiên Claude Code đang chạy, mỗi lần ghi thêm một dòng, là
cả file bị parse lại. Đo được: quét đầy đủ mất 27 giây, và trang thì CHỜ quét xong mới vẽ.

File này khoá lại phần khó nhất của cách đọc tiếp - đếm cho ĐÚNG:
  - đọc tiếp phải ra đúng bằng quét lại trọn file, không thiếu và không đếm trùng;
  - dòng cuối chưa ghi xong (chưa có \\n) không được tính, và khi nó ghi xong thì tính ĐÚNG MỘT LẦN;
  - file teo lại (log bị dọn/xoay vòng) thì quét lại trọn, không cộng nhầm lên số cũ.

Chạy:
    python tests/run.py chi_so_token_doc_tiep
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="javis-token-index-"))
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
(_TMP / "state").mkdir(parents=True, exist_ok=True)

import usage_index as ui  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# ── Một thư mục transcript giả, để không đụng log thật của máy ───────────────
LOG_DIR = _TMP / "projects"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG = LOG_DIR / "phien-thu.jsonl"
ui.DB_PATH = _TMP / "usage_index.db"
ui._claude_dir = lambda: str(LOG_DIR)


def dong(inp, out, ts="2026-09-21T08:00:00.000Z"):
    return json.dumps({
        "type": "assistant", "sessionId": "s1", "cwd": "/x/brain-thu",
        "timestamp": ts, "entrypoint": "sdk-cli",
        "message": {"model": "claude-opus-5", "usage": {"input_tokens": inp, "output_tokens": out}},
    }, ensure_ascii=False)


def ghi(lines, mode="a"):
    with open(LOG, mode, encoding="utf-8", newline="\n") as fh:
        for ln in lines:
            fh.write(ln + "\n")
    # mtime của hệ tệp Windows thô hơn một lượt ghi, mà `_scan_claude` so cả size nên vẫn thấy
    # file đổi; đẩy mtime lên cho chắc, không thì test thành ra phụ thuộc đồng hồ.
    st = os.stat(LOG)
    os.utime(LOG, (st.st_atime, st.st_mtime + 10))


def ghi_tho(text):
    """Ghi thẳng, KHÔNG thêm xuống dòng - dựng cảnh dòng cuối đang ghi dở."""
    with open(LOG, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    st = os.stat(LOG)
    os.utime(LOG, (st.st_atime, st.st_mtime + 10))


def quet():
    conn = ui._connect()
    try:
        n = ui._scan_claude(conn, set(), {})
        conn.commit()
        return n
    finally:
        conn.close()


def tong():
    conn = ui._connect()
    try:
        r = conn.execute("SELECT COALESCE(SUM(input),0), COALESCE(SUM(output),0), "
                         "COALESCE(SUM(turns),0) FROM file_daily").fetchone()
        return tuple(r)
    finally:
        conn.close()


def offset_da_ghi():
    conn = ui._connect()
    try:
        r = conn.execute("SELECT offset FROM files_seen WHERE path=?", (str(LOG),)).fetchone()
        return (r[0] or 0) if r else 0
    finally:
        conn.close()


# ── 1. Quét lần đầu ──────────────────────────────────────────────────────────
ghi([dong(100, 10), dong(200, 20)], mode="w")
check("quét lần đầu có đọc file", quet() == 1)
check("cộng đúng token lần đầu", tong() == (300, 30, 2))
check("có ghi lại offset để lần sau đọc tiếp", offset_da_ghi() == os.path.getsize(LOG))

# ── 2. Không đổi gì thì không đọc lại ────────────────────────────────────────
check("file không đổi -> bỏ qua, không đọc lại", quet() == 0)
check("và số liệu giữ nguyên", tong() == (300, 30, 2))

# ── 3. Ghi thêm -> chỉ cộng phần mới, không đếm trùng phần cũ ────────────────
ghi([dong(1, 2)])
check("ghi thêm thì có quét", quet() == 1)
check("đọc tiếp cộng đúng phần mới, không đếm trùng phần cũ", tong() == (301, 32, 3))

# ── 4. Dòng cuối không có \n: tính ngay, và KHÔNG được tính lần hai ──────────
# Đây là chỗ dễ sai nhất. Bỏ qua dòng cụt thì một phiên kết thúc mà không có xuống dòng bị mất
# lượt cuối vĩnh viễn; tính nó rồi vẫn đọc tiếp thì khi nó được ghi nốt, nó bị đếm hai lần.
ghi_tho(dong(50, 5))           # thiếu \n ở cuối
check("file dài ra thì có quét", quet() == 1)
check("dòng cuối không có xuống dòng vẫn được tính", tong() == (351, 37, 4))
check("nhưng offset dừng TRƯỚC dòng đó", offset_da_ghi() < os.path.getsize(LOG))
ghi_tho("\n")                  # dòng đó vừa ghi xong
quet()
check("ghi nốt xuống dòng KHÔNG làm nó bị đếm lần hai", tong() == (351, 37, 4))
ghi([dong(2, 1)])              # rồi ghi thêm một dòng trọn vẹn nữa
quet()
check("và dòng trọn vẹn tiếp theo vẫn cộng đúng", tong() == (353, 38, 5))

# ── 5. Đối chứng: đọc tiếp phải ra đúng bằng quét lại trọn file ──────────────
mong_doi = tong()
conn = ui._connect()
conn.execute("DELETE FROM files_seen")
conn.execute("DELETE FROM file_daily")
conn.execute("DELETE FROM file_hourly")
conn.commit()
conn.close()
quet()
check(f"quét lại trọn file ra đúng bằng đường đọc tiếp ({mong_doi})", tong() == mong_doi)

# ── 6. File teo lại (log bị dọn/xoay vòng) -> quét lại trọn, không cộng dồn ──
ghi([dong(7, 3)], mode="w")    # ghi đè, file ngắn hẳn lại
check("file teo lại thì có quét", quet() == 1)
check("và đếm lại từ đầu chứ không cộng lên số cũ", tong() == (7, 3, 1))

print("")
print(("ĐỎ: " + ", ".join(fails)) if fails else "OK - test_chi_so_token_doc_tiep: tất cả pass")
sys.exit(1 if fails else 0)
