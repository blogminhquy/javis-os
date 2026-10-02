"""Lệnh "/" hệ thống của Javis: phần LÕI dùng chung cho khung chat web và Telegram.

Vì sao có file này: web chat từng chỉ có ba lệnh (/new /reset /stop), còn Telegram có hẳn một
bộ riêng nằm trong `main.py::_tg_command`. Hai kênh nói hai thứ khác nhau về cùng một khái
niệm, và mọi lệnh kiểu Claude Code (nén ngữ cảnh, chế độ kế hoạch, xem mức dùng...) đều phải
viết lại hai lần. File này giữ những gì KHÔNG phụ thuộc kênh: khối chỉ dẫn của `/plan`, việc
nén hội thoại của `/compact`, và cách định dạng số liệu cho kênh chỉ có chữ.

Nguyên tắc: lệnh do JAVIS tự xử lý chứ không mượn lệnh có sẵn của Claude Code. Engine API,
Codex, Grok, Antigravity đều không có `/compact` hay `/plan` của Claude Code, nên nếu dựa vào
đó thì năng lực đổi theo bộ não - trái với nguyên tắc "năng lực của Javis không đổi theo model".

Hai khối chỉ dẫn (`/plan`, `/goal`) đi cùng dạng "khối ngoặc vuông đứng TRƯỚC câu người dùng,
kết thúc bằng ]\\n\\n" như `[SKILL: ...]`, để bong bóng chat, tên hội thoại và nút "gửi lại" đều
thấy đúng câu người dùng gõ (xem dashboard/app.js::chuNguoiGo và sessions.py::title_from_message).
"""
from __future__ import annotations

import re
import sys

import compaction
import localefmt

# Dấu hiệu nhận diện. PHẢI khớp từng chữ với dashboard/chat-lenh.js (có test khoá hai bên).
PLAN_MARK = "[CHẾ ĐỘ KẾ HOẠCH:"
GOAL_MARK = "[MỤC TIÊU:"
GOAL_TAG = "JAVIS_GOAL"

# Neo đầu DÒNG chứ không phải đầu tin: trước khối này dashboard còn chèn khối "file đang ghim" và
# "ngữ cảnh giao diện", nên nó hiếm khi đứng ở byte 0. Neo đầu dòng để một đoạn văn dán vào
# mà tình cờ nhắc chữ này giữa câu không bị coi là lệnh.
_PLAN_RE = re.compile(r"(?m)^\[CHẾ ĐỘ KẾ HOẠCH:")

# Phải có ít nhất chừng này tin (user + Javis) mới đáng nén: dưới đó là chưa có gì để gấp.
MIN_TIN_NEN = 4
# Số tin GẦN NHẤT giữ nguyên vẹn khi nén bằng tóm tắt (2 lượt hỏi-đáp).
GIU_NGUYEN = 4
# Nhà API mà bộ nén nền của Javis đã chạy được (cùng danh sách với móc nén nền sau mỗi lượt
# trong main.py). Nhà khác (Ollama, OpenAI-compat) chưa được kiểm chứng đường tóm tắt nên
# không đoán mò: báo thẳng là chưa hỗ trợ thay vì nén hỏng.
NHA_API_NEN_DUOC = ("openrouter", "openai", "anthropic-api", "gemini", "groq")


def khoi_ke_hoach() -> str:
    """Khối chỉ dẫn `/plan`: một lượt CHỈ ĐỌC và ĐỀ XUẤT, chưa làm gì ra ngoài.

    Đây là chỉ dẫn cho model, không phải câu người dùng gõ. Ở ba engine CLI có cổng công cụ
    (Claude Code, Grok, Antigravity) server còn hạ mức quyền của lượt xuống `suggest`
    (`la_luot_ke_hoach`), nên cổng chặn thật chứ không chỉ dựa vào lời dặn.
    """
    return (
        f"{PLAN_MARK} chỉ đọc và đề xuất.\n"
        "Lượt này CHƯA được làm gì ra bên ngoài: không ghi hay xoá file, không gửi tin, không "
        "đăng bài, không tạo đơn, không chạy hay sửa quảng cáo, không xếp việc nền, không đặt "
        "lịch nhắc. Được đọc dữ liệu và dùng công cụ chỉ đọc để hiểu tình hình.\n"
        "Trả lời bằng một kế hoạch ngắn: mục tiêu, các bước, việc nào cần người dùng duyệt, "
        "rủi ro chính. Kết thúc bằng một câu hỏi xem người dùng có muốn làm theo kế hoạch "
        "không. Chỉ khi họ đồng ý ở tin sau mới bắt đầu làm thật.]\n\n"
    )


def la_luot_ke_hoach(user_message) -> bool:
    """Lượt này có phải lượt `/plan` không (để hạ mức quyền xuống chỉ đọc)."""
    return bool(_PLAN_RE.search(str(user_message or "")))


def _don_dieu_kien(dieu_kien: str, toi_da: int = 400) -> str:
    """Điều kiện `/goal` -> MỘT dòng an toàn để đặt trong khối ngoặc vuông.

    Dấu ngoặc vuông bị đổi thành ngoặc tròn vì dashboard cắt khối ở chỗ `]` đầu tiên theo sau
    là hai dấu xuống dòng; một điều kiện chứa `]` sẽ làm bong bóng lộ ra nửa khối chỉ dẫn.
    """
    s = re.sub(r"\s+", " ", str(dieu_kien or "")).strip()
    s = s.replace("[", "(").replace("]", ")")
    return s[:toi_da]


def khoi_muc_tieu(dieu_kien: str, vong: int = 1, toi_da: int = 8) -> str:
    """Khối chỉ dẫn `/goal`: làm tiếp cho tới khi điều kiện đúng, tự báo trạng thái ở cuối.

    Trình duyệt đọc dòng ẩn `<!-- JAVIS_GOAL: {...} -->` để quyết định có tự gửi vòng tiếp
    không. Cách này giống JAVIS_ASK/JAVIS_LESSON: MODEL đề xuất, CODE quyết định (trần vòng,
    dừng khi không tiến triển, dừng khi người dùng chen vào).
    """
    dk = _don_dieu_kien(dieu_kien)
    return (
        f"{GOAL_MARK} {dk}\n"
        f"Chế độ làm tới khi đạt, vòng {int(vong)}/{int(toi_da)}. Làm tiếp phần còn thiếu bằng "
        "công cụ sẵn có, rồi tự kiểm tra bằng dữ liệu thật xem điều kiện trên đã đúng chưa.\n"
        "Cuối câu trả lời LUÔN thêm đúng MỘT dòng ẩn: "
        f'<!-- {GOAL_TAG}: {{"done":true}} --> nếu điều kiện đã đúng và đã kiểm chứng, hoặc '
        f'<!-- {GOAL_TAG}: {{"done":false,"left":"tình trạng và phần còn lại, một câu ngắn"}} --> nếu chưa. '
        "Không báo đã đạt khi chưa kiểm chứng. Cần người dùng quyết định điều gì thì hỏi rõ rồi "
        "dừng.]\n\n"
    )


_GOAL_RE = re.compile(r"<!--\s*" + GOAL_TAG + r":\s*([\s\S]*?)\s*-->")


def doc_muc_tieu(text: str):
    """Đọc dòng ẩn JAVIS_GOAL CUỐI CÙNG trong câu trả lời -> {'done': bool, 'left': str} hoặc None.

    None = model không báo (hoặc báo hỏng). Bên gọi coi đó là "không rõ" và DỪNG, không đoán
    là chưa xong: đoán sai chiều đó là tự chạy vòng lặp đốt token.
    """
    import json
    hit = None
    for m in _GOAL_RE.finditer(str(text or "")):
        hit = m
    if not hit:
        return None
    try:
        d = json.loads(hit.group(1))
    except (ValueError, TypeError):
        return None
    if not isinstance(d, dict) or not isinstance(d.get("done"), bool):
        return None
    return {"done": d["done"], "left": str(d.get("left") or "").strip()[:300]}


async def nen_phien(store, sid, *, kind, prov, api_key, model, api_stream, giu=GIU_NGUYEN):
    """`/compact`: nén hội thoại `sid` NGAY, không đợi ngưỡng tự động.

    Hai đường, tuỳ bộ não của phiên (vì hai họ engine giữ ngữ cảnh khác nhau):

    - **Engine API** (OpenRouter, OpenAI, Claude API, Gemini, Groq): gấp phần cũ vào bản tóm tắt
      `compact_summary` (cùng bộ máy nén nền), chỉ giữ nguyên `giu` tin gần nhất. Lượt sau gửi
      tóm tắt + đuôi thay vì cả lịch sử.
    - **Engine gói thuê bao** (Claude Code, Codex, Grok, Antigravity): các engine này tự giữ mạch
      native, và phần phình to nằm trong mạch đó (kết quả công cụ, vòng lặp agentic) chứ không
      trong transcript của Javis. Nén = vứt mạch native đi; lượt sau Javis mở mạch mới và mồi
      lại bằng transcript đã lưu (`compaction.bootstrap_prompt`). Không có bước tóm tắt vì gói
      thuê bao không có API key để gọi một request tóm tắt riêng.

    Trả dict có `ok` và `cach`/`ly_do` để giao diện nói đúng sự thật, không khoe nén khi chưa nén.
    """
    try:
        msgs = [m for m in store.get_messages(sid)
                if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()]
    except Exception as e:  # noqa: BLE001 - kho phiên hỏng: báo lỗi chứ không ném lên
        print(f"[nen_phien] đọc tin lỗi: {type(e).__name__}: {e}", file=sys.stderr)
        return {"ok": False, "ly_do": "loi_doc", "so_tin": 0}
    n = len(msgs)
    if n < MIN_TIN_NEN:
        return {"ok": False, "ly_do": "ngan", "so_tin": n}

    if kind == "api":
        if not api_key or prov not in NHA_API_NEN_DUOC:
            return {"ok": False, "ly_do": "khong_ho_tro", "so_tin": n}
        sess = store.get_session(sid) or {}
        da_nen = int(sess.get("compact_count") or 0)
        if (n - giu) - da_nen < 1:
            # Không còn gì cũ hơn cửa sổ giữ nguyên để gấp thêm: đã gọn rồi, không phải lỗi.
            return {"ok": True, "cach": "da_gon", "so_tin": n, "da_nen": da_nen}
        ok = await compaction.maybe_compact(store, sid, prov, api_key, model, api_stream,
                                            keep=giu, min_chunk=1)
        if not ok:
            return {"ok": False, "ly_do": "loi_tom_tat", "so_tin": n}
        sess = store.get_session(sid) or {}
        return {"ok": True, "cach": "tom_tat", "so_tin": n,
                "da_nen": int(sess.get("compact_count") or 0)}

    da_don = store.clear_native_threads(sid)
    if not da_don:
        # Không có mạch native nào đang giữ ngữ cảnh (phiên mới, hoặc engine dựng lại từ
        # transcript ở mọi lượt như Antigravity): không có gì để vứt, nói thật.
        return {"ok": True, "cach": "khong_co_mach", "so_tin": n}
    store.mark_thread_rotated(sid)
    try:
        store.set_last_input_tokens(sid, 0)   # thước đo ngữ cảnh về 0 cho đến lượt sau
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "cach": "xoay_mach", "so_tin": n, "mach": list(da_don)}


# ---------------------------------------------------------------------------
# Định dạng cho kênh chỉ có chữ (Telegram). Web nhận JSON thô và tự dịch bằng i18n.
# ---------------------------------------------------------------------------

def gon_so(n) -> str:
    """84300 -> '84,3k', 1250000 -> '1,25M'. Số nhỏ giữ nguyên."""
    try:
        v = float(n or 0)
    except (TypeError, ValueError):
        return "0"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.2f}".rstrip("0").rstrip(".").replace(".", ",") + "M"
    if v >= 1000:
        return f"{v / 1000:.1f}".rstrip("0").rstrip(".").replace(".", ",") + "k"
    return str(int(v))


def _dong_muc_dung(nhan: str, tot: dict) -> str:
    luot = int((tot or {}).get("turns") or 0)
    if not luot:
        return localefmt.chu(f"{nhan}: chưa có lượt nào.", f"{nhan}: no turns yet.")
    s = localefmt.chu(f"{nhan}: {luot} lượt, {gon_so(tot.get('in'))} token vào, "
                      f"{gon_so(tot.get('out'))} token ra",
                      f"{nhan}: {luot} turns, {gon_so(tot.get('in'))} tokens in, "
                      f"{gon_so(tot.get('out'))} tokens out")
    chi = float((tot or {}).get("cost") or 0)
    if chi > 0:
        s += f", ~${chi:.2f}"
    return s + "."


def dinh_dang_muc_dung(summary: dict, openrouter=None) -> str:
    """Kết quả `usage_store.summary()` (+ số dư OpenRouter nếu có) -> chữ cho Telegram."""
    summary = summary or {}
    hom_nay = summary.get("today") or {}
    tat_ca = summary.get("all_time") or {}
    dong = [localefmt.chu("📈 Mức dùng Javis (số Javis tự đo)", "📈 Javis usage (as measured by Javis)"),
            _dong_muc_dung(localefmt.chu("Hôm nay", "Today"), hom_nay.get("total") or {})]
    for it in (hom_nay.get("items") or [])[:5]:
        dong.append(f"  - {it.get('provider', '?')} {it.get('model', '')}: "
                    + localefmt.chu(f"{int(it.get('turns') or 0)} lượt, ",
                                    f"{int(it.get('turns') or 0)} turns, ")
                    + f"{gon_so((it.get('in') or 0) + (it.get('out') or 0))} token")
    dong.append(_dong_muc_dung(localefmt.chu("Từ trước tới nay", "All time"), tat_ca.get("total") or {}))
    if openrouter and openrouter.get("remaining") is not None:
        dong.append(localefmt.chu(f"Số dư OpenRouter: ${float(openrouter['remaining']):.2f}",
                                  f"OpenRouter balance: ${float(openrouter['remaining']):.2f}"))
    return "\n".join(dong)


_NHAN_COT = (("running", "Đang chạy"), ("review", "Chờ duyệt"), ("blocked", "Bị kẹt"),
             ("ready", "Sẵn sàng"), ("todo", "Chờ làm"), ("triage", "Mới nhận"))
_NHAN_COT_EN = {"running": "Running", "review": "Awaiting review", "blocked": "Blocked",
                "ready": "Ready", "todo": "To do", "triage": "New"}


def dinh_dang_viec(view: dict, moi_cot: int = 5) -> str:
    """Kết quả `board_view` của Kanban -> chữ cho Telegram: việc nào đang chạy, xếp hàng, kẹt."""
    view = view or {}
    cot = view.get("columns") or {}
    dem = view.get("counts") or {}
    che_do = str(view.get("orchestration") or "")
    dong = [localefmt.chu("📋 Việc nền của Javis", "📋 Javis background work")]
    if che_do.lower() == "off":
        dong.append(localefmt.chu("⚠ Tự vận hành đang TẮT: việc chỉ nằm trong hàng đợi, chưa chạy. "
                                  "Bật ở trang Việc trên dashboard.",
                                  "⚠ AI self-driving is OFF: work only sits in the queue and does not run. "
                                  "Turn it on from the Tasks page on the dashboard."))
    elif che_do.lower() == "manual":
        dong.append(localefmt.chu("Tự vận hành ở chế độ thủ công: việc chỉ chạy khi bấm Chạy ở trang Việc.",
                                  "AI self-driving is manual: work only runs when you click Run on the Tasks page."))
    co_gi = False
    for khoa, nhan in _NHAN_COT:
        ds = cot.get(khoa) or []
        if not ds:
            continue
        co_gi = True
        dong.append(f"{localefmt.chu(nhan, _NHAN_COT_EN.get(khoa, nhan))} ({len(ds)}):")
        for t in ds[:moi_cot]:
            dong.append(f"  - {str(t.get('title') or t.get('id') or '?')[:70]}")
        if len(ds) > moi_cot:
            dong.append(localefmt.chu(f"  ... và {len(ds) - moi_cot} việc nữa",
                                      f"  ... and {len(ds) - moi_cot} more"))
    if not co_gi:
        dong.append(localefmt.chu("Không có việc nào đang chạy hay chờ.", "Nothing is running or waiting."))
    xong = int(view.get("completed_24h") or 0)
    if xong or dem.get("done"):
        dong.append(localefmt.chu(f"Xong trong 24 giờ qua: {xong}.", f"Done in the last 24 hours: {xong}."))
    return "\n".join(dong)


def dinh_dang_bo_nho(noi_dung: str, toi_da: int = 3000) -> str:
    """Mục lục bộ nhớ (memory/MEMORY.md) -> chữ cho Telegram, cắt cho vừa một tin nhắn."""
    s = str(noi_dung or "").strip()
    if not s:
        return localefmt.chu("Brain này chưa có bộ nhớ dài hạn nào (memory/MEMORY.md trống). "
                             "Nói \"nhớ giúp ... \" là Javis tự ghi.",
                             "This brain has no long-term memory yet (memory/MEMORY.md is empty). "
                             "Say \"remember ...\" and Javis writes it down.")
    if len(s) > toi_da:
        s = s[:toi_da].rstrip() + localefmt.chu("\n... (còn nữa, mở memory/MEMORY.md để xem đủ)",
                                                "\n... (more, open memory/MEMORY.md for the rest)")
    return localefmt.chu("🧠 Bộ nhớ dài hạn của brain này\n\n", "🧠 Long-term memory of this brain\n\n") + s
