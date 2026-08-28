"""Telegram không được QUÊN SẠCH sau mỗi lần restart server.

    python tests/run.py tg_ngu_canh_restart      (KHÔNG mạng, không cần Telegram)

Vì sao có file này. Người dùng báo ngày 28/08/2026, nguyên văn:

  "mỗi lần update bản mới bấm nút update thì bên telegram nó mất hết ký ức, quên sạch mọi
   thứ, từ cách xưng hô tới quy trình đặt tên file. Còn ở localhost:7777 thì bình thường.
   Trí nhớ với lưu trữ thì vẫn còn, nhưng đoạn chat liên tục thì như là không nhớ gì."

Đo lại trên máy trước khi vá thì đúng y như vậy, và lý do nằm ở chỗ dữ liệu SỐNG Ở ĐÂU:

  - Dashboard: trình duyệt giữ `session_id` và gửi kèm MỖI request, nên restart không mất gì.
  - Telegram: KHÔNG có ai giữ hộ. `sess["sid"]` (chat -> hội thoại) và `sess["or"]` (lịch sử
    engine API) đều nằm trong `_TG_SESS`, tức RAM của tiến trình. Restart là bay sạch, lượt
    kế mở một phiên TRỐNG trong khi bản ghi cũ vẫn nằm nguyên trong SQLite, chỉ là không còn
    ai nối vào.

Hai nửa đó phải vá cả hai mới hết bệnh, nên test này canh cả hai:

  1. Nối lại ĐÚNG phiên cũ sau restart (`_TG_SID_MAP` ghi xuống đĩa).
  2. Dựng lại ĐÚNG nội dung đã nói (`_tg_lich_su_kho` đọc transcript SQLite).

Vá được nửa một mà quên nửa hai thì thanh bên dashboard trông liền mạch nhưng Javis vẫn hỏi
lại "bạn là ai" ở tin nhắn kế - đúng thứ người dùng đang than.

Và canh cả CHIỀU NGƯỢC LẠI: /reset, đổi brain, phiên đã nguội quá 12 tiếng hay đã dài quá 200
tin thì vẫn phải sang phiên mới. Khôi phục mà bỏ qua mấy luật đó là chữa một lỗi bằng một lỗi
to hơn (dính vĩnh viễn vào một hội thoại không cách nào thoát ra).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-tgsid-test-")

import main                     # noqa: E402
from sessions import get_store  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name
          + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


BRAIN = tempfile.mkdtemp(prefix="javis-tgsid-brain-")
BRAIN2 = tempfile.mkdtemp(prefix="javis-tgsid-brain2-")
CHAT = "999000111"
store = get_store()


def restart():
    """Giả lập restart server: tiến trình mới thì `_TG_SESS` rỗng và map bền đọc lại từ đĩa.

    Cố ý KHÔNG gọi thẳng hàm nội bộ nào ngoài hai dòng này - đây đúng là những gì xảy ra khi
    module được import lại: `_TG_SESS = {}` và `_TG_SID_MAP = _tg_load_sid_map()`.
    """
    main._TG_SESS.clear()
    main._TG_SID_MAP.clear()
    main._TG_SID_MAP.update(main._tg_load_sid_map())


def mot_luot(chat, brain, hoi, dap, engine="cli"):
    """Một lượt Telegram, đúng thứ tự `_tg_answer` làm: khớp phiên -> ghi hỏi -> ghi đáp."""
    sess = main._tg_session(chat)
    sid = main._tg_conv_sid(store, sess, brain, engine, "m")
    store.append_message(sid, "user", hoi)
    store.append_message(sid, "assistant", dap)
    return sid


# ============================================================
# 1. Trong CÙNG một tiến trình: một chat = một phiên
# ============================================================
sid1 = mot_luot(CHAT, BRAIN, "gọi tôi là anh nhé", "Vâng, em nhớ rồi.")
sid2 = mot_luot(CHAT, BRAIN, "file dự án đặt tên kiểu YYYY-MM-DD", "Đã ghi nhận.")
check("hai lượt liên tiếp nằm chung một phiên", sid1 == sid2, (sid1, sid2))
check("transcript có đủ 4 tin", len(store.get_messages(sid1)) == 4,
      len(store.get_messages(sid1)))


# ============================================================
# 2. RESTART: phải nối lại đúng phiên cũ  (nửa một)
# ============================================================
restart()
check("CANARY: restart xong `_TG_SESS` thật sự rỗng (không thì cả test này vô nghĩa)",
      main._TG_SESS.get(CHAT) is None)
check("map bền có ghi xuống đĩa", main._TG_SID_PATH.exists(), main._TG_SID_PATH)

sess3 = main._tg_session(CHAT)
check("CANARY: phiên RAM dựng lại KHÔNG tự có sid (nó phải đến từ map bền)",
      sess3.get("sid") in (None, ""))
sid3 = main._tg_conv_sid(store, sess3, BRAIN, "cli", "m")
check("sau restart vẫn là ĐÚNG phiên cũ - đây là lỗi người dùng báo",
      sid3 == sid1, (sid1, sid3))


# ============================================================
# 3. RESTART: phải dựng lại đúng NỘI DUNG  (nửa hai)
# ============================================================
cau_moi = "tạo giúp file dự án mới"
store.append_message(sid3, "user", cau_moi)      # `_tg_answer` ghi câu hỏi TRƯỚC khi gọi engine
cu, tom = main._tg_lich_su_kho(store, sid3, cau_moi)
noi_dung = " | ".join(m["content"] for m in cu)
check("lịch sử dựng lại có lời dặn xưng hô", "gọi tôi là anh" in noi_dung, noi_dung[:200])
check("lịch sử dựng lại có quy ước đặt tên file", "YYYY-MM-DD" in noi_dung, noi_dung[:200])
check("CANARY: KHÔNG kèm câu đang hỏi (kèm là engine bị hỏi hai lần)",
      cau_moi not in noi_dung, noi_dung[-120:])
check("thứ tự giữ nguyên, tin đầu là của user",
      cu and cu[0]["role"] == "user", cu[:1])

# Ghi câu hỏi hụt (lệnh append nằm trong try/except) thì KHÔNG được cắt nhầm tin thật.
cu2, _ = main._tg_lich_su_kho(store, sid3, "một câu chưa hề được ghi vào kho")
check("CANARY: không có tin nào khớp câu đang hỏi thì không cắt bừa tin cuối",
      len(cu2) == len(cu) + 1, (len(cu), len(cu2)))

# Cửa sổ mồi lại phải CÓ TRẦN, kẻo phiên nghìn tin thổi phồng lượt đầu sau restart.
check("có trần số tin mồi lại", isinstance(main._TG_MOI_LAI_MAX, int)
      and 0 < main._TG_MOI_LAI_MAX <= 100, main._TG_MOI_LAI_MAX)
check("phiên rỗng/không có kho thì trả rỗng, không nổ",
      main._tg_lich_su_kho(None, "", "x") == ([], "")
      and main._tg_lich_su_kho(store, "khong-co-that", "x") == ([], ""))


# ============================================================
# 4. /reset và đổi brain vẫn phải CẮT được, kể cả xuyên restart
# ============================================================
main._tg_quen_sid(main._tg_session(CHAT))       # đúng thứ /reset gọi
restart()
sid_reset = main._tg_conv_sid(store, main._tg_session(CHAT), BRAIN, "cli", "m")
check("/reset xong, restart xong vẫn là phiên MỚI (không hồi sinh hội thoại cũ)",
      sid_reset != sid1, (sid1, sid_reset))
check("CANARY: bản ghi cũ KHÔNG bị xoá, chỉ là thôi nối vào",
      len(store.get_messages(sid1)) >= 4, len(store.get_messages(sid1)))

sid_b2 = main._tg_conv_sid(store, main._tg_session(CHAT), BRAIN2, "cli", "m")
check("brain đổi (kể cả lúc server đang tắt) thì sang phiên khác, không trộn hai bộ não",
      sid_b2 != sid_reset, (sid_reset, sid_b2))

# ...nhưng phép so brain phải DỄ TÍNH, kẻo chữa một lỗi bằng một lỗi to hơn. Cột `sessions.brain`
# từng được mỗi kênh ghi một kiểu cho CÙNG một brain (xem `_brain_keys`), và phiên do nơi khác
# dựng có thể để trống. So bằng dấu bằng thì mọi bản ghi như vậy bị coi là "khác brain" và bị
# bỏ - MỖI LƯỢT đẻ một phiên mới, tệ hơn hẳn cái đang chữa.
CHAT_TRONG = "999000555"
sid_trong = mot_luot(CHAT_TRONG, BRAIN, "chào", "chào bạn")
store._write(lambda c: c.execute("UPDATE sessions SET brain='' WHERE id=?", (sid_trong,)))
restart()
_l1 = main._tg_conv_sid(store, main._tg_session(CHAT_TRONG), BRAIN, "cli", "m")
check("CANARY: cột brain rỗng thì THA, không coi là khác brain", _l1 == sid_trong,
      (sid_trong, _l1))
restart()
check("CANARY: và ổn định qua nhiều lượt (không mỗi lượt một phiên)",
      main._tg_conv_sid(store, main._tg_session(CHAT_TRONG), BRAIN, "cli", "m") == sid_trong)


# ============================================================
# 5. Luật XOAY phiên không được vì khôi phục mà mất hiệu lực
# ============================================================
CHAT_CU = "999000222"
sid_cu = mot_luot(CHAT_CU, BRAIN, "chào", "chào bạn")
store._write(lambda c: c.execute(          # ép phiên nguội hơn ngưỡng 12 tiếng
    "UPDATE sessions SET updated_at=? WHERE id=?",
    (time.time() - main._TG_CONV_IDLE_S - 60, sid_cu)))
restart()
sid_moi = main._tg_conv_sid(store, main._tg_session(CHAT_CU), BRAIN, "cli", "m")
check("phiên nguội quá 12 tiếng: khôi phục xong vẫn xoay sang khúc mới",
      sid_moi != sid_cu, (sid_cu, sid_moi))

CHAT_DAI = "999000333"
sid_dai = mot_luot(CHAT_DAI, BRAIN, "chào", "chào bạn")
store._write(lambda c: c.execute(          # ép phiên dài hơn ngưỡng 200 tin
    "UPDATE sessions SET msg_count=? WHERE id=?", (main._TG_CONV_MAX_MSGS + 1, sid_dai)))
restart()
check("phiên đã dài quá 200 tin: khôi phục xong vẫn xoay sang khúc mới",
      main._tg_conv_sid(store, main._tg_session(CHAT_DAI), BRAIN, "cli", "m") != sid_dai)

# Hội thoại bị xoá trên dashboard thì đừng hồi sinh id cũ.
CHAT_XOA = "999000444"
sid_xoa = mot_luot(CHAT_XOA, BRAIN, "chào", "chào bạn")
store._write(lambda c: c.execute("DELETE FROM sessions WHERE id=?", (sid_xoa,)))
restart()
check("hội thoại đã bị xoá: mở phiên mới chứ không hồi sinh id chết",
      main._tg_conv_sid(store, main._tg_session(CHAT_XOA), BRAIN, "cli", "m") != sid_xoa)


# ============================================================
# 6. Hai chat khác nhau không được dính vào nhau
# ============================================================
restart()
a = main._tg_conv_sid(store, main._tg_session("111"), BRAIN, "cli", "m")
b = main._tg_conv_sid(store, main._tg_session("222"), BRAIN, "cli", "m")
check("hai chat_id khác nhau = hai phiên khác nhau", a != b, (a, b))
restart()
check("và sau restart mỗi người vẫn về đúng phiên của mình",
      main._tg_conv_sid(store, main._tg_session("111"), BRAIN, "cli", "m") == a
      and main._tg_conv_sid(store, main._tg_session("222"), BRAIN, "cli", "m") == b)


# ============================================================
# 7. Cắt mạch native: phải đủ BỐN engine
# ============================================================
# Mồi lại từ transcript chỉ chạy khi engine CHƯA có mạch native. Nên chỗ cắt mạch mà sót một
# engine thì engine đó vừa không được cắt, vừa không được mồi - hỏng câm đúng kiểu repo này canh.
class _GiaEngine:
    def __init__(self):
        self.session_id = "mach-cu"


class _GiaEngineCoReset(_GiaEngine):
    def reset_session(self):
        self.session_id = None


check("bảng engine giữ mạch kể đủ bốn cái",
      {k for _, k in main._TG_ENGINE_MACH} == {"cli", "codex", "grok", "antigravity"},
      main._TG_ENGINE_MACH)

_s = main._tg_session("777")
_s["cli"] = _GiaEngineCoReset()
for _k in ("codex", "grok", "antigravity"):
    _s[_k] = _GiaEngine()
main._tg_ngat_mach(_s)
check("cắt sạch: mọi engine đều mất mạch native",
      all(_s[k].session_id is None for k in ("cli", "codex", "grok", "antigravity")),
      {k: _s[k].session_id for k in ("cli", "codex", "grok", "antigravity")})

_s2 = main._tg_session("888")
for _k in ("cli", "codex", "grok", "antigravity"):
    _s2[_k] = _GiaEngine()
main._tg_ngat_mach(_s2, tru="grok-cli")
check("CANARY: engine ĐANG chạy được tha, không thì mỗi lượt nó tự cắt mạch của chính mình",
      _s2["grok"].session_id == "mach-cu", _s2["grok"].session_id)
check("các engine còn lại vẫn bị cắt",
      all(_s2[k].session_id is None for k in ("cli", "codex", "antigravity")))


print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + "; ".join(_fails))
else:
    print("XANH: tất cả đều đạt")
sys.exit(1 if _fails else 0)
