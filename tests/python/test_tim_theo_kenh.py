"""Ô tìm ở cột lịch sử của một cộng sự chỉ được thấy hội thoại CỦA CỘNG SỰ ĐÓ.

    python tests/run.py tim_theo_kenh

Cột lịch sử trang Cộng sự dùng chính module của trang Trò chuyện (dashboard/sessions-ui.js) ở
chế độ lọc kênh. Danh sách thì `/sessions?channel=` lo từ trước, nhưng ô TÌM đi đường
`/sessions/search` vốn quét cả brain - gõ một chữ vào đó mà nhảy ra hội thoại của người dùng
với bộ não chính thì bấm vào là văng khỏi trợ lý đang mở.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-timkenh-")
os.environ["JAVIS_STATE_DIR"] = _TMP
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_TMP) / "conv.db")

import sessions  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


store = sessions.SessionStore(str(Path(_TMP) / "kho.db"))
web = store.create_session(brain="b", channel="web")
ag = store.create_session(brain="b", channel="agent:nguoi-viet")
ag2 = store.create_session(brain="b", channel="agent:ke-toan")
wf = store.create_session(brain="b", channel="workflow:ban-tin")
for sid in (web, ag, ag2, wf):
    store.append_message(sid, "user", "ngân sách quảng cáo tháng này")

moi = {r["session_id"] for r in store.search("ngân sách", brain="b")}
check("khong truyen kenh thi tim ca brain nhu cu", moi == {web, ag, ag2, wf})

mot = {r["session_id"] for r in store.search("ngân sách", brain="b", channel="agent:nguoi-viet")}
check("truyen kenh thi CHI thay hoi thoai cua cong su do", mot == {ag})
check("khong lot hoi thoai cua tro ly khac", ag2 not in mot and wf not in mot)

check("kenh cua quy trinh cung loc dung",
      {r["session_id"] for r in store.search("ngân sách", brain="b", channel="workflow:ban-tin")} == {wf})
check("kenh khong co that thi tra ve rong",
      store.search("ngân sách", brain="b", channel="agent:khong-co-ai") == [])
# Chuỗi rỗng phải hiểu là "không lọc", không phải "lọc theo kênh rỗng" (endpoint truyền
# Query("") xuống, và một câu `s.channel = ''` thì không hàng nào khớp).
check("chuoi rong = khong loc", len(store.search("ngân sách", brain="b", channel="")) == 4)
check("khoang trang cung tinh la khong loc", len(store.search("ngân sách", brain="b", channel="  ")) == 4)

store.close()
if fails:
    print("\nFAIL:", len(fails), fails)
    raise SystemExit(1)
print("\nOK - tim theo kenh")
