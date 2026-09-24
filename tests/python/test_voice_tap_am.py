"""Legacy noise-marker compatibility, conservative prompt and focus-setting wiring."""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-tapam-"))

import voice_brain as vb  # noqa: E402
import sessions  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. parse_bo_qua ----
check("bỏ lượt: lấy được lý do",
      vb.parse_bo_qua("JAVIS_BO_QUA: tiếng TV trong phòng") == "tiếng TV trong phòng")
check("không có marker -> None",
      vb.parse_bo_qua("JAVIS_NGHE: xin chào\nChào anh, em nghe đây.") is None)
# Lý do rỗng vẫn là BỎ: dòng lệnh có mặt đã là quyết định. Trả "" chứ không None, nên chỗ gọi
# phải hỏi `is not None` - hỏi truthy là lượt tạp âm lọt thẳng vào khung chat.
check("lý do rỗng vẫn là bỏ (chuỗi rỗng, không phải None)",
      vb.parse_bo_qua("JAVIS_BO_QUA:") == "")
check("marker không ở dòng đầu vẫn bắt được",
      vb.parse_bo_qua("JAVIS_NGHE: abc\nJAVIS_BO_QUA: hai người nói chuyện") == "hai người nói chuyện")
check("marker giữa câu KHÔNG tính (phải đứng đầu dòng)",
      vb.parse_bo_qua("anh bảo JAVIS_BO_QUA: gì cơ") is None)
check("BO_QUA_MARKER nằm trong MARKERS", vb.BO_QUA_MARKER in vb.MARKERS)

# ---- 2. Không bao giờ ra loa ----
check("final: dòng bỏ lượt không ra loa",
      vb.split_speakable("JAVIS_BO_QUA: tiếng TV", 0, True)[0] == [])
check("đang stream: chưa biết là marker thì giữ lại, không đọc",
      vb.split_speakable("JAVIS_BO", 0, False)[0] == [])
check("bỏ lượt sau một dòng khác: chỉ dòng kia ra loa",
      vb.split_speakable("Ừ.\nJAVIS_BO_QUA: tiếng TV\n", 0, True)[0] == ["Ừ.\n"])

# Text alone cannot identify the speaker. Legacy markers are still parsed/suppressed,
# but the model no longer has permission to delete accepted user speech.
check("prompt forbids guessing noise", "Không đoán tiếng TV" in vb.SYSTEM_PROMPT)
check("per-turn guard protects running brains with old prompts",
      vb.BO_QUA_MARKER in vb.GHI_CHU_TAT_LOC and "không cắt bỏ" in vb.GHI_CHU_TAT_LOC)
for value in (None, False, True):
    check(f"legacy setting {value} cannot enable model noise deletion",
          vb.config_from_settings({"voice": {"loc_tap_am": value}})["loc_tap_am"] is False)

# ---- 5. Xoá tin cuối khỏi kho phiên ----
_db = os.path.join(tempfile.mkdtemp(prefix="javis-tapam-db-"), "sessions.db")
store = sessions.SessionStore(_db)
sid = store.get_or_create(None, brain="brain", engine="cli", model="")
store.append_message(sid, "user", "câu thật")
store.append_message(sid, "assistant", "trả lời")
store.append_message(sid, "user", "tiếng TV lải nhải")
check("xoá đúng tin cuối đúng vai", store.pop_last_message(sid, "user") is True)
_msgs = [(m["role"], m["content"]) for m in store.get_messages(sid)]
check("chỉ mất đúng tin tạp âm",
      _msgs == [("user", "câu thật"), ("assistant", "trả lời")])
# Phải trừ cả msg_count, không thì danh sách Lịch sử khoe số tin nhiều hơn số tin thật - một
# cuộc chỉ có đúng một lượt tạp âm sẽ hiện "1 tin" dù bên trong rỗng không.
check("msg_count trừ theo", store.get_session(sid)["msg_count"] == 2)
# Trợ lý đã kịp trả lời thì tin cuối là của nó: xoá là mất câu trả lời thật.
check("sai vai thì không xoá gì", store.pop_last_message(sid, "user") is False)
check("kho phiên nguyên vẹn sau lần gọi hụt",
      len(store.get_messages(sid)) == 2)
check("phiên rỗng thì không nổ", store.pop_last_message("khong-co-phien-nay", "user") is False)

# ---- 6. Dây trong main.py ----
MAIN = (SERVER / "main.py").read_text(encoding="utf-8")
# Bẫy đã cắn hai lần (locale, Voice V2): POST /settings dùng allowlist TỪNG KEY, thêm ô mới
# mà quên nhánh này thì nút báo "Đã lưu" nhưng F5 là mất sạch.
check("POST /settings nhận ô loc_tap_am", '"loc_tap_am" in patch' in MAIN)
check("settings accepts focus_mode", '\"focus_mode\" in patch' in MAIN)
check("focus defaults on independently of retired text filtering", 'focus_mode=v.get("focus_mode") is not False' in MAIN)
# Deletion prohibition is exercised against production handler/SQLite in test_voice_turn_integrity.
check("guard sent on every turn", "voice_brain.GHI_CHU_TAT_LOC" in MAIN)

# ---- 7. Trần một lượt nói và dây phía trình duyệt ----
VOICE_JS = (ROOT / "dashboard" / "voice.js").read_text(encoding="utf-8")
check("voice.js có trần cho một lượt", "TRAN_LUOT_MS" in VOICE_JS)
check("quá trần thì chốt ngay, không hẹn tiếp",
      "if (Date.now() - this._batDauLuot >= JavisVoice.TRAN_LUOT_MS) { this.stopListening(); return; }" in VOICE_JS)
APP_JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
# Bubble removal and stale raw-text guards are exercised by test_voice_app_session.js.
check("app.js để lại dòng ghi chú thoáng qua", 'ghiChuThoang(window.t("app.tap_am_bo_qua"))' in APP_JS)
CONSOLE_JS = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("trang Cài đặt có ô gạt", 'id="v2LocTapAm"' in CONSOLE_JS)
check("ô gạt được gửi lên khi bấm Lưu", 'focus_mode: $("v2LocTapAm").checked' in CONSOLE_JS)

print()
if _fails:
    print(f"{len(_fails)} phép thử đỏ: " + ", ".join(_fails))
    raise SystemExit(1)
print("Tất cả xanh.")
