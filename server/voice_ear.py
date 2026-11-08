"""Tai nghe lại (ear): một model đa ngôn ngữ nghe lại ÂM THANH rồi mới chốt chữ vào bong bóng.

Vì sao có (0.65.15, docs/dev/2026-10-voice-call-spec.md mục 2 và phụ lục A4): Chrome Web Speech chỉ nghe được một
ngôn ngữ (vi-VN), nên câu Việt pha tiếng Anh hỏng nặng. Đo trên 20 câu pha (tools/stt_bench),
Chrome sai 41% số từ, "Mở dashboard Facebook ads" thành "Mở double Facebook add". Sửa chữ sau
khi Chrome nghe không cứu được câu đã mất hẳn thông tin ("John Smith về deadline" thành "Dung
biết về nick liên quân"), nên phải để một model nghe chính âm thanh.

Module này lo hai việc:
  - CHỌN tai cho lượt nói (`select_ear`, `order`), từ khoá `voice.ear` = auto | chatgpt | groq | openai | off.
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
CHOICES = ("auto", "chatgpt", "groq", "openai", "off")
DEFAULT = "auto"

# Các tai Javis biết chạy. `kind`:
#   upload - trình duyệt ghi âm cả câu, hết câu mới gửi lên /stt.
# `key_field`: the API key on the Models page this ear needs. `plan`: the signed-in plan it runs on instead.
EARS = {
    # 2026-11-08: the ChatGPT plan's own dictation ear (stt.chatgpt_nghe), on the login Javis already holds. No key.
    "chatgpt": {"label": "ChatGPT plan", "kind": "upload", "plan": "openai-oauth"},
    "groq": {"label": "Groq Whisper", "kind": "upload", "key_field": "groq_api_key"},
    # 0.231.0: a machine with an OpenAI key but no Groq key used to have no ear at all, so a Vietnamese sentence with
    # English words in it stayed as Chrome heard it ("Claude Code" -> "lót code"). gpt-4o-transcribe keeps both.
    # The model is OpenAI's newest transcribe model (stt_models), so the label names no version.
    "openai": {"label": "OpenAI transcribe", "kind": "upload", "key_field": "openai_api_key"},
}

# Thứ tự khi `auto` mà bộ não chính không có tai cùng hãng. Xếp theo bộ đo tools/stt_bench:
# có số mới thì sửa ở đây.
# Groq stays first: it is the ear tools/stt_bench measured. The ChatGPT plan comes next (2026-11-08): it costs the
# owner nothing beyond the plan they pay for, so it goes before the OpenAI key, which bills every minute.
RANKING = ("groq", "chatgpt", "openai")

# Provider của bộ não chính (main._effective_main) -> tai cùng hãng. Owner, 2026-11-08: "no setting, the ear follows
# the main model in use: on ChatGPT use the ChatGPT plan's ear, and the same for the others". Claude, Antigravity and
# Grok have no ear Javis can reach on their plans (Claude's voice needs the login token Javis never reads, `agy` keeps
# its session in the OS keyring, xAI bills speech-to-text as an API apart from SuperGrok), so those brains get the
# best ear the machine has and stay the brain.
BRAIN_EAR = {
    "openai-oauth": "chatgpt",
    "groq": "groq",
    "openai": "openai",
}

# Mã lý do, trang Cài đặt dịch qua khoá i18n `settings.ear_reason_<mã>`.
REASON_OFF = "off"
REASON_CHOSEN = "chosen"
REASON_CHOSEN_UNAVAILABLE = "chosen_unavailable"
REASON_SAME_VENDOR = "same_vendor"
REASON_BEST = "best"
REASON_NONE = "none"


def setting(cfg: dict) -> str:
    """Lựa chọn hiệu lực của người dùng: auto | chatgpt | groq | openai | off.

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
        if ear.get("plan") == "openai-oauth":
            o = m.get("openai_oauth") or {}
            out[name] = bool(o.get("access_token") or o.get("refresh_token"))
        else:
            out[name] = bool(m.get(key_field)) if key_field else True
    return out


def order(cfg: dict, brain_provider: str = "", choice: str = "") -> list:
    """Every ear that can run now, best first: what one sentence tries, one after another, until an ear hears it.

    auto: the main brain's own vendor first (BRAIN_EAR), then RANKING. A chosen ear goes first and the others stay
    behind it, so a vendor that is down still does not cost the sentence. off: none. `choice` overrides the setting
    (voice messages pass "auto": `voice.ear` = off silences the dashboard mic's re-listen, not Telegram or Zalo)."""
    choice = choice if choice in CHOICES else setting(cfg)
    if choice == "off":
        return []
    avail = availability(cfg)
    first = [choice] if choice != "auto" else [BRAIN_EAR.get(brain_provider or "", "")]
    out = []
    for name in first + list(RANKING):
        if name and avail.get(name) and name not in out:
            out.append(name)
    return out


def select_ear(cfg: dict, brain_provider: str = "") -> dict:
    """Chọn tai cho lượt nói. Trả:

        {"provider": "chatgpt" | "groq" | "openai" | "", "kind": "upload" | "", "label": "...",
         "setting": "auto|...|off", "reason": "<mã lý do>", "fallbacks": [tai dự phòng]}

    provider rỗng nghĩa là không có tai: dùng chữ của trình duyệt như trước.
    """
    choice = setting(cfg)
    ears = order(cfg, brain_provider)

    def none(reason):
        return {"provider": "", "kind": "", "label": "", "setting": choice, "reason": reason, "fallbacks": []}

    if choice == "off":
        return none(REASON_OFF)
    if choice != "auto" and (not ears or ears[0] != choice):
        return none(REASON_CHOSEN_UNAVAILABLE)
    if not ears:
        return none(REASON_NONE)
    name = ears[0]
    if choice != "auto":
        reason = REASON_CHOSEN
    elif name == BRAIN_EAR.get(brain_provider or ""):
        reason = REASON_SAME_VENDOR
    else:
        reason = REASON_BEST
    ear = EARS.get(name) or {}
    return {"provider": name, "kind": ear.get("kind", ""), "label": ear.get("label", ""),
            "setting": choice, "reason": reason, "fallbacks": ears[1:]}


async def chatgpt_creds() -> dict:
    """{"access_token", "account_id"} of the ChatGPT plan, refreshed when it has expired; {} when not connected.

    `openai_oauth.valid_creds` may refresh over the network with a blocking call, so it runs in a thread."""
    import asyncio
    try:
        import openai_oauth
        return (await asyncio.to_thread(openai_oauth.valid_creds)) or {}
    except Exception:   # noqa: BLE001 - a broken login is one ear less, never a lost sentence
        return {}


def _mcp_labels() -> list:
    """Tên các kết nối MCP đang có ("Pancake POS", "Gmail"...): người dùng hay gọi tên chúng."""
    try:
        import mcp_store
        return [str(c.get("label") or "").strip() for c in mcp_store.list_connections()
                if str(c.get("label") or "").strip()]
    except Exception:
        return []


def vocab(cfg: dict) -> list:
    """Bộ từ mồi cho tai: tên trợ lý + từ người dùng khai (`nghe_sua.vocabulary`) + tên các kết nối
    MCP. Chỉ dùng làm MỒI cho model nghe, KHÔNG đưa vào lớp sửa mờ `nghe_sua.sua` (sửa mờ với
    nhiều tên dễ đổi nhầm một từ tiếng Việt)."""
    # The assistant's name and the owner's words go LAST: Whisper keeps only the end of its prompt, and a machine with
    # thirty connections used to push "Javis" out of it (2026-11-06).
    own = list(nghe_sua.vocabulary(cfg))
    seen = {t.lower() for t in own}
    labels = []
    for label in _mcp_labels():
        if label.lower() not in seen:
            seen.add(label.lower())
            labels.append(label)
    room = max(0, nghe_sua.MAX_VOCABULARY - len(own))
    return labels[:room] + own[:nghe_sua.MAX_VOCABULARY]


def whisper_lang(lang: str):
    """Mã ngôn ngữ của trình duyệt -> gợi ý cho Whisper (xem ba giá trị trong stt.groq_nghe).

    "auto" (ô Ngôn ngữ nghe = Đa ngôn ngữ) -> "" để Whisper tự dò; "vi-VN" -> "vi"; rỗng -> None.
    """
    lang = (lang or "").strip()
    if lang.lower() == "auto":
        return ""
    return lang.split("-")[0].strip() or None


async def transcribe_upload(cfg: dict, data: bytes, filename: str = "voice.webm", lang: str = "",
                            draft: str = "", provider: str = "groq", fallbacks=()) -> dict:
    """Chạy tai dạng tải lên cho một câu đã ghi âm. Trả cùng khuôn với route /stt:

        {"ok": True, "text": "...", "model": "..."}
        {"ok": False, "text": "", "ly_do": "...", "model": "..."}

    ok=False thì trình duyệt giữ chữ của Web Speech, không mất lượt.

    `fallbacks` (select_ear): the ears tried next, in order, when `provider` fails in a way another ear may fix (no
    login, the vendor down, a refused file). Silence stays silence, so "khong_nghe_ro" ends the chain.
    """
    tv = nghe_sua.fix_vocabulary(cfg)
    hotwords = nghe_sua.goi_y_whisper(vocab(cfg))
    res = {}
    for name in [provider] + [f for f in (fallbacks or ()) if f != provider]:
        res = await _hear(cfg, name, data, filename or "voice.webm", whisper_lang(lang), hotwords)
        if res.get("ok") or res.get("ly_do") not in stt._TRY_NEXT:
            break
        print(f"[stt] tai {name} hỏng ({res.get('ly_do')}), thử tai kế tiếp", file=sys.stderr)
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


async def _hear(cfg: dict, name: str, data: bytes, filename: str, lang, hotwords: str) -> dict:
    """One ear, one try. Same contract as `stt.groq_nghe`."""
    m = (cfg or {}).get("model") or {}
    v = (cfg or {}).get("voice") or {}
    if name == "chatgpt":
        creds = await chatgpt_creds()
        return await stt.chatgpt_nghe(data, filename, creds.get("access_token") or "", creds.get("account_id") or "",
                                      lang, hotwords=hotwords)
    if name == "openai":
        return await stt.openai_nghe(data, filename, m.get("openai_api_key", ""), "", lang, hotwords=hotwords)
    return await stt.groq_nghe(data, filename, m.get("groq_api_key", ""), v.get("stt_model") or "", lang,
                               hotwords=hotwords)
