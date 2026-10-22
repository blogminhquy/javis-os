"""Plugin bundled: tool `javis_watch` - theo dõi trang web không tốn token, từ MỌI engine (0.239.0).

Gọi THẲNG tính năng `web_watch` trong tiến trình (`web_watch.current()`), cùng lý do như `javis_task`:
không mở thêm cửa HTTP miễn đăng nhập nào.

Luật "chỉ lên lịch khi đủ điều kiện" (CLAUDE.md): mục theo dõi là một việc chạy nền, nên trước khi tạo
phải chắc kết quả có chỗ về. Khung chat web và hòm thư luôn nhận được, nên không chặn; nhưng khi chưa
có kênh ngoài (Telegram, Zalo...) thì kết quả tạo NÓI RA điều đó, để model báo lại cho người dùng là
lúc không mở dashboard thì sẽ không có tin trên điện thoại.
"""
from __future__ import annotations

import web_watch

try:
    import luot_dang_chay
except Exception:          # chạy lẻ ngoài máy chủ
    luot_dang_chay = None

_TEN_DK = {"change": "trang thay đổi", "contains": "xuất hiện cụm chữ", "price_below": "có giá dưới ngưỡng"}


def _feature():
    f = web_watch.current()
    if f is None:
        return None, "ERROR: tính năng theo dõi trang chưa sẵn sàng (máy chủ đang khởi động?). Thử lại sau vài giây."
    return f, ""


def _dong(w: dict) -> str:
    dk = _TEN_DK.get(w.get("cond"), w.get("cond"))
    if w.get("value"):
        dk += f" \"{w['value']}\""
    tt = {"active": "đang canh", "paused": "tạm dừng", "stopped": "đã dừng"}.get(w.get("status"), w.get("status"))
    loi = f" · lỗi gần nhất: {w['last_error'][:120]}" if w.get("last_error") else ""
    dn = " · có đăng nhập" if w.get("login_id") else ""
    return (f"{w['id']} · {w['title']} · {w['url']} · {dk} · {w['interval_min']} phút/lần · {tt}"
            f" · đã canh {w.get('checks') or 0} lần{dn}{loi}")


def _tao(args, ctx) -> str:
    if not ctx.vault_root:
        return "ERROR: chưa biết đang làm việc trên brain nào nên không tạo được mục theo dõi."
    f, loi = _feature()
    if loi:
        return loi
    a = args or {}
    chat_id = str(a.get("chat_id") or "").strip()
    tu_gan = False
    if not chat_id and luot_dang_chay is not None:
        try:
            chat_id = luot_dang_chay.doan_chat_id(ctx.vault_root)
            tu_gan = bool(chat_id)
        except Exception:
            chat_id = ""
    w, err = f.create(ctx.vault_root, a.get("url", ""), a.get("condition") or "change", a.get("value", ""),
                      a.get("title", ""), a.get("interval_minutes") or web_watch.DEFAULT_INTERVAL, chat_id,
                      bool(a.get("summarize")), str(a.get("login") or "").strip())
    if err:
        return f"ERROR: {err}"
    ra = ["Đã tạo mục theo dõi: " + _dong(w),
          "Lượt canh đầu chạy trong vòng 30 giây. Mỗi lượt chỉ tải trang và so chữ, không tốn token"
          + ("; khi có thay đổi sẽ gọi AI một lần để tóm tắt." if w.get("summarize") else ".")]
    if w["cond"] == "change":
        ra.append("Lượt đầu chỉ ghi lại trang làm mốc, từ lượt sau mới báo thay đổi.")
    if tu_gan:
        ra.append(f"Người nhận báo: tự gắn khung chat đang hỏi ({chat_id}).")
    elif not chat_id:
        ra.append("Chưa gắn người nhận (chat_id): báo sẽ về khung chat Javis Core của brain này và hòm thư.")
    co, thieu = f.deps.channels() if f.deps.channels else (True, "")
    if not co:
        ra.append(f"LƯU Ý: chưa có kênh ngoài ({thieu}), nên báo chỉ nằm trong khung chat web và hòm thư, không tới "
                  "điện thoại. Nói rõ điều này với người dùng.")
    ra.append("Quản lý (tạm dừng, canh ngay, xoá) ở tab Theo dõi trang của trang Việc định kỳ.")
    return "\n".join(ra)


def _liet_ke(ctx) -> str:
    if not ctx.vault_root:
        return "ERROR: chưa biết đang làm việc trên brain nào."
    f, loi = _feature()
    if loi:
        return loi
    ds = f.store.list(f.deps.brain_root(ctx.vault_root))
    if not ds:
        return "Chưa có trang nào được theo dõi trong brain này."
    return "\n".join(_dong(w) for w in ds[:40])


async def _dieu_khien(args, ctx, action) -> str:
    f, loi = _feature()
    if loi:
        return loi
    wid = str((args or {}).get("id") or "").strip()
    w = f.store.get(wid)
    if not w or (ctx.vault_root and w.get("brain") != f.deps.brain_root(ctx.vault_root)):
        return f"ERROR: không thấy mục theo dõi {wid} trong brain này. Gọi op=list để xem mã."
    kq, err = f.control(wid, action)
    if err:
        return f"ERROR: {err}"
    if action == "delete":
        return f"Đã xoá mục theo dõi {wid}."
    if action == "check_now":
        bao = await f.check(wid)
        w = f.store.get(wid) or w
        if w.get("last_error") and not bao:
            return f"Đã canh ngay {wid} nhưng không tải được trang: {w['last_error']}"
        return f"Đã canh ngay {wid}. " + ("Có chuyện mới, đã gửi báo." if bao else "Chưa có gì mới so với lần trước.")
    return f"Đã {'tạm dừng' if action == 'pause' else 'mở lại'}: " + _dong(kq)


def register(ctx):
    ctx.register_tool(
        "javis_watch",
        "Theo dõi một trang web theo lịch, KHÔNG tốn token mỗi lượt: chỉ tải trang và so chữ, có chuyện mới mới báo "
        "về khung chat. Dùng thay cho loop khi việc cần làm chỉ là canh một trang (giá đối thủ, offer mới, trang chính "
        "sách, hàng về). op=create: url, condition = change (trang đổi) | contains (xuất hiện cụm chữ, cần value) | "
        "price_below (có giá dưới ngưỡng, value như 1.500.000đ, 1,5 triệu, 250k, $20); interval_minutes (5 tới 10080, "
        "mặc định 60); title; chat_id lấy từ khối KÊNH HỘI THOẠI HIỆN TẠI; summarize=true để AI tóm tắt mỗi lần có "
        "thay đổi (tốn token, mặc định tắt); login = tên một đăng nhập trong trang Cookies khi trang cần đăng nhập. "
        "op=list: liệt kê. op=pause | resume | check_now | delete: cần id.",
        _chay,
        schema={
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": ["create", "list", "pause", "resume", "check_now", "delete"]},
                "url": {"type": "string"},
                "condition": {"type": "string", "enum": ["change", "contains", "price_below"]},
                "value": {"type": "string", "description": "Cụm chữ (contains) hoặc ngưỡng giá (price_below)"},
                "interval_minutes": {"type": "integer"},
                "title": {"type": "string"},
                "chat_id": {"type": "string", "description": "Người nhận báo, vd web:<mã phiên>"},
                "summarize": {"type": "boolean"},
                "login": {"type": "string", "description": "Tên đăng nhập trong trang Cookies, khi trang cần đăng nhập"},
                "id": {"type": "string", "description": "Mã mục theo dõi (op pause/resume/check_now/delete)"},
            },
            "required": ["op"],
        },
        min_mode="safe",
        emoji="👁",
    )


async def _chay(args, ctx) -> str:
    op = str((args or {}).get("op") or "").strip().lower()
    if op == "create":
        return _tao(args, ctx)
    if op == "list":
        return _liet_ke(ctx)
    if op in ("pause", "resume", "check_now", "delete"):
        return await _dieu_khien(args, ctx, op)
    return "ERROR: op phải là create, list, pause, resume, check_now hoặc delete."
