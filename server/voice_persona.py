"""Voice call with a partner (an assistant of the Partners page): who the call model is.

A call started from a partner's chat (session channel `agent:<slug>`) used to speak with the plain
Javis voice prompt, which says nothing about that partner: no name, no role, no instructions from
the partner file. Asked "who are you", the ChatGPT Live model then answered that it was ChatGPT
(owner report 2026-11-05). This module turns any of the voice prompts (voice_live, voice_brain)
into the partner's prompt, and builds the identity block from the partner file.

Pure functions, no I/O: main.py reads the files and passes the text in.
"""
from __future__ import annotations
import os

# Every voice prompt opens with this clause (voice_live.SYSTEM_PROMPT, GPT_LIVE_PROMPT,
# CHATGPT_LIVE_PROMPT, voice_brain.SYSTEM_PROMPT); test_voice_persona.py keeps them in step.
OPENING = "Bạn là Javis, trợ lý cá nhân,"

# Voice budgets are *Javis* defaults, not provider model context limits.
# Keep a bounded override for long-lived agent profiles (including future telephone gateways).
def _env_budget(name: str, default: int, ceiling: int) -> int:
    try:
        configured = int(os.environ.get(name, ""))
    except (ValueError, TypeError):
        return default
    return max(1000, min(configured, ceiling))


BODY_CHARS = _env_budget("JAVIS_VOICE_AGENT_BODY_CHARS", 12000, 24000)
MEMORY_CHARS = _env_budget("JAVIS_VOICE_AGENT_MEMORY_CHARS", 6000, 12000)
# Optional markers in an agent's Markdown body. Move the enclosed high-priority
# instructions before ordinary agent prose *before* applying BODY_CHARS.
VOICE_RULES_START = "<!-- JAVIS_VOICE_RULES_START -->"
VOICE_RULES_END = "<!-- JAVIS_VOICE_RULES_END -->"

# These operational integrity rules are never subject to body or memory truncation.
ALWAYS_ON = (
    "Quy tắc bắt buộc trong Voice: không đoán giá, định lượng, tồn kho, phí giao, lịch "
    "hoặc trạng thái công việc từ trí nhớ hay lời khách. Cần dữ liệu thật thì dùng công cụ "
    "có thẩm quyền; thiếu kết quả phải nói rõ chưa xác minh. "
    "Không nói đã tạo đơn, đặt giao hàng, gửi tin, chuyển nhân viên hay nhận thanh toán "
    "nếu chưa có kết quả thực thi thành công. Phân biệt yêu cầu đã ghi nhận, bản nháp "
    "và hành động đã hoàn tất."
)


def _priority_body(text: str) -> str:
    """Move one opt-in pinned section before the rest; do not duplicate it."""
    text = str(text or "").strip()
    start = text.find(VOICE_RULES_START)
    if start < 0:
        return text
    content_start = start + len(VOICE_RULES_START)
    end = text.find(VOICE_RULES_END, content_start)
    if end < 0:
        return text  # An unmatched marker must not eat the agent instructions.
    pinned = text[content_start:end].strip()
    if not pinned:
        return text
    remainder = (text[:start] + "\n" + text[end + len(VOICE_RULES_END):]).strip()
    return pinned + ("\n\n" + remainder if remainder else "")


def _cut(text: str, cap: int) -> str:
    text = str(text or "").strip()
    return text if len(text) <= cap else text[:cap].rstrip() + " ..."


def identity_block(name: str, role: str = "", body: str = "", memory: str = "") -> str:
    """Who the partner is, for a call model: the Javis context, the partner's role and its own instructions."""
    name = str(name or "").strip() or "cộng sự"
    role = str(role or "").strip()
    parts = [
        "# Bạn là ai trong cuộc gọi này",
        f"Bạn là **{name}**, một cộng sự (trợ lý chuyên trách) trong Javis OS, hệ trợ lý AI cá nhân của chủ."
        + (f" Vai trò: {role}." if role else ""),
        "Javis là hệ thống bạn đang chạy bên trong, không phải tên của bạn. Chủ đang gọi thoại riêng với bạn "
        "từ khung chat của bạn trên dashboard. Mọi chỗ ở trên nói 'Javis' là nói về chính bạn trong vai này.",
        f"Khi được hỏi bạn là ai, trả lời bạn là {name}, cộng sự trong Javis của chủ, và nói ngắn vai của mình. "
        "KHÔNG tự nhận là ChatGPT, Claude, Gemini, Grok hay một trợ lý AI chung chung. Chỉ khi chủ hỏi rõ đang "
        "chạy model hay engine nào mới nói tên đó.",
        "Việc cần dữ liệu thật, công cụ hay hành động thì vẫn giao như hướng dẫn ở trên: phần đó do chính bạn "
        f"({name}) làm tiếp với đủ công cụ của Javis, nên kết quả trả về là của bạn, thuật lại như lời mình.",
        ALWAYS_ON,
    ]
    if str(body or "").strip():
        parts += ["", "# Hướng dẫn riêng của bạn (file cộng sự)", _cut(_priority_body(body), BODY_CHARS)]
    if str(memory or "").strip():
        parts += ["", "# Bộ nhớ của bạn (luật chủ dặn, bài học)", _cut(memory, MEMORY_CHARS)]
    return "\n".join(parts)


def apply(base: str, name: str, block: str) -> str:
    """`base` voice prompt spoken as the partner `name`: the opening clause names the partner, the block follows.

    A prompt without the usual opening (a custom one) keeps its text and gets the block in front, so the identity
    still comes first."""
    base = str(base or "")
    name = str(name or "").strip() or "cộng sự"
    block = str(block or "").strip()
    head = f"Bạn là {name}, một cộng sự của chủ trong Javis,"
    if OPENING in base:
        out = base.replace(OPENING, head, 1)
        return out + ("\n\n" + block if block else "")
    return (block + "\n\n" + base) if block else base
