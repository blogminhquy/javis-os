"""Tai nghe lại (ear): một model đa ngôn ngữ nghe lại ÂM THANH rồi mới chốt chữ vào bong bóng.

Vì sao có (0.65.15, docs/dev/2026-10-voice-ear-spec.md): Chrome Web Speech chỉ nghe được một
ngôn ngữ (vi-VN), nên câu Việt pha tiếng Anh hỏng nặng. Đo trên 20 câu pha (tools/stt_bench),
Chrome sai 41% số từ, "Mở dashboard Facebook ads" thành "Mở double Facebook add". Sửa chữ sau
khi Chrome nghe không cứu được câu đã mất hẳn thông tin ("John Smith về deadline" thành "Dung
biết về nick liên quân"), nên phải để một model nghe chính âm thanh.

Module này lo hai việc:
  - CHỌN tai cho lượt nói (`select_ear`), từ khoá `voice.ear` = auto | groq | off.
  - Chạy tai dạng TẢI LÊN (`transcribe_upload`): trình duyệt ghi âm, hết câu gửi file lên /stt.

Ba lớp rào cho chữ của tai, giống nhau với mọi tai:
  - `stt.loc_ao_giac`: Whisper bịa câu outro YouTube khi gặp im lặng hay tiếng ồn.
  - `stt.khop_ban_nhap`: chữ tai lệch hẳn bản nháp của trình duyệt thì giữ bản nháp. Rào này
    bắt kiểu lỗi model nghe âm thanh trả về nguyên một câu không liên quan.
  - `nghe_sua.sua`: sửa tên trợ lý nghe nhầm ("David" thành "Javis").
"""
from __future__ import annotations

import sys

import nghe_sua
import stt

# Giá trị hợp lệ của `voice.ear`. "auto" là mặc định: chủ dự án chốt 01/10/2026 "tự chọn, bật
# sẵn", vì máy suy ra được tai nào dùng được thì không bắt người dùng phải chọn.
CHOICES = ("auto", "groq", "off")
DEFAULT = "auto"

# Các tai Javis biết chạy. `kind`:
#   upload - trình duyệt ghi âm cả câu, hết câu mới gửi lên /stt.
EARS = {
    "groq": {"label": "Groq Whisper", "kind": "upload", "key_field": "groq_api_key"},
}

# Thứ tự khi `auto` mà bộ não chính không có tai cùng hãng. Xếp theo bộ đo tools/stt_bench:
# có số mới thì sửa ở đây.
RANKING = ("groq",)

# Provider của bộ não chính (main._effective_main) -> tai cùng hãng. Bộ não Claude không có
# tai: model Claude không nhận âm thanh, còn giọng nói của Claude Code cần token đăng nhập mà
# Javis cố ý không đọc. Khi đó dùng tai tốt nhất đang có, bộ não vẫn là Claude.
BRAIN_EAR = {
    "groq": "groq",
}

# Mã lý do, trang Cài đặt dịch qua khoá i18n `settings.ear_reason_<mã>`.
REASON_OFF = "off"
REASON_CHOSEN = "chosen"
REASON_CHOSEN_UNAVAILABLE = "chosen_unavailable"
REASON_SAME_VENDOR = "same_vendor"
REASON_BEST = "best"
REASON_NONE = "none"


def setting(cfg: dict) -> str:
    """Lựa chọn hiệu lực của người dùng: auto | groq | off.

    Khoá cũ `voice.stt_provider` (trước 0.65.15): "groq" là người dùng đã CHỌN thật nên vẫn tôn
    trọng; "browser" bị bỏ qua vì nút Lưu của trang Cài đặt luôn gửi kèm mặc định đó, nó không
    phải một lựa chọn.
    """
    v = (cfg or {}).get("voice") or {}
    ear = v.get("ear")
    if ear in CHOICES:
        return ear
    if v.get("stt_provider") == "groq":
        return "groq"
    return DEFAULT


def availability(cfg: dict) -> dict:
    """{tên tai: True/False}: tai nào chạy được NGAY bây giờ với cấu hình này."""
    m = (cfg or {}).get("model") or {}
    out = {}
    for name, ear in EARS.items():
        key_field = ear.get("key_field")
        out[name] = bool(m.get(key_field)) if key_field else True
    return out


def select_ear(cfg: dict, brain_provider: str = "") -> dict:
    """Chọn tai cho lượt nói. Trả:

        {"provider": "groq" | "", "kind": "upload" | "", "label": "...",
         "setting": "auto|groq|off", "reason": "<mã lý do>"}

    provider rỗng nghĩa là không có tai: dùng chữ của trình duyệt như trước.
    """
    choice = setting(cfg)
    avail = availability(cfg)

    def pick(name, reason):
        ear = EARS.get(name) or {}
        return {"provider": name, "kind": ear.get("kind", ""), "label": ear.get("label", ""),
                "setting": choice, "reason": reason}

    def none(reason):
        return {"provider": "", "kind": "", "label": "", "setting": choice, "reason": reason}

    if choice == "off":
        return none(REASON_OFF)
    if choice != "auto":
        return pick(choice, REASON_CHOSEN) if avail.get(choice) else none(REASON_CHOSEN_UNAVAILABLE)
    same = BRAIN_EAR.get(brain_provider or "")
    if same and avail.get(same):
        return pick(same, REASON_SAME_VENDOR)
    for name in RANKING:
        if avail.get(name):
            return pick(name, REASON_BEST)
    return none(REASON_NONE)


def _mcp_labels() -> list:
    """Tên các kết nối MCP đang có ("Pancake POS", "Gmail"...): người dùng hay gọi tên chúng."""
    try:
        import mcp_store
        return [str(c.get("label") or "").strip() for c in mcp_store.list_connections()
                if str(c.get("label") or "").strip()]
    except Exception:
        return []


def vocab(cfg: dict) -> list:
    """Bộ từ mồi cho tai: tên trợ lý + từ người dùng khai (`nghe_sua.tu_vung`) + tên các kết nối
    MCP. Chỉ dùng làm MỒI cho model nghe, KHÔNG đưa vào lớp sửa mờ `nghe_sua.sua` (sửa mờ với
    nhiều tên dễ đổi nhầm một từ tiếng Việt)."""
    out = list(nghe_sua.tu_vung(cfg))
    seen = {t.lower() for t in out}
    for label in _mcp_labels():
        if label.lower() not in seen:
            seen.add(label.lower())
            out.append(label)
    return out[:nghe_sua.MAX_TU_VUNG]


def whisper_lang(lang: str):
    """Mã ngôn ngữ của trình duyệt -> gợi ý cho Whisper (xem ba giá trị trong stt.groq_nghe).

    "auto" (ô Ngôn ngữ nghe = Đa ngôn ngữ) -> "" để Whisper tự dò; "vi-VN" -> "vi"; rỗng -> None.
    """
    lang = (lang or "").strip()
    if lang.lower() == "auto":
        return ""
    return lang.split("-")[0].strip() or None


async def transcribe_upload(cfg: dict, data: bytes, filename: str = "voice.webm", lang: str = "",
                            draft: str = "") -> dict:
    """Chạy tai dạng tải lên cho một câu đã ghi âm. Trả cùng khuôn với route /stt:

        {"ok": True, "text": "...", "model": "..."}
        {"ok": False, "text": "", "ly_do": "...", "model": "..."}

    ok=False thì trình duyệt giữ chữ của Web Speech, không mất lượt.
    """
    m = (cfg or {}).get("model") or {}
    v = (cfg or {}).get("voice") or {}
    tv = nghe_sua.tu_vung(cfg)
    res = await stt.groq_nghe(data, filename or "voice.webm", m.get("groq_api_key", ""),
                              v.get("stt_model") or "", whisper_lang(lang),
                              hotwords=nghe_sua.goi_y_whisper(vocab(cfg)))
    text = nghe_sua.sua(res.get("text", ""), tv) if res.get("ok") else res.get("text", "")
    # Log chỉ ghi SỐ ĐO (độ dài, độ giống), không ghi lời người dùng.
    if res.get("ok") and str(draft or "").strip():
        ok, word_sim, sound_sim = stt.khop_ban_nhap(draft, text)
        print(f"[stt] audio={len(data) // 1024}KB nhap={len(draft.split())}tu tai={len(text.split())}tu "
              f"giong_tu={word_sim} giong_am={sound_sim} -> {'tai' if ok else 'GIU NHAP'}", file=sys.stderr)
        if not ok:
            return {"ok": False, "text": "", "ly_do": "lech_ban_nhap", "model": res.get("model", "")}
    return {"ok": bool(res.get("ok")), "text": text, "ly_do": res.get("ly_do", ""),
            "model": res.get("model", "")}
