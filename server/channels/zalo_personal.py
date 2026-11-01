"""Kênh Zalo CÁ NHÂN: tài khoản đã quét QR ở trang Kết nối (MCP `javis-zalo`). Đọc tin bằng
vòng cursor ở `zalo_personal_channel`, gửi tin bằng tool `zalo_send_message` của chính MCP đó.

Gửi từ kênh này là gửi DƯỚI DANH TÍNH CHỦ (không phải bot), nên Hộp thư nói rõ điều đó ở ô
soạn tin; ngoài ra nó là một kênh như mọi kênh khác, không có mục riêng nào trên giao diện.

Từ 0.64.80 kênh này gắn được Bot chuyên trách (lớp `Transport` cuối file). Bot tự trả lời và tự
quyết có nên trả lời không; các rào nằm ở `Transport.xu_ly`. Từ 0.64.82 bot còn đứng được trong
NHÓM đã cho phép: trả lời khi được tag/reply, hoặc (chế độ Tự đánh giá) khi tin là một câu hỏi
mà tài liệu của bot trả lời được, xem `chatbot_tu_dong`. Từ 0.65.7 trong nhóm bot tự tag người nó đang trả lời (`gui(..., mention=)`).
"""
from __future__ import annotations

import asyncio
import re
import sys
import time
from typing import Optional

from channels import KenhSpec
import localefmt
import zalo_markup

SPEC = KenhSpec(
    id="zalo_personal", nhan="Zalo cá nhân", kind="account", logo="zalo", mau="#0068FF",
    tom_tat="Tài khoản Zalo của chính bạn. Bot trực thì tự trả lời chat riêng và nhóm đã cho phép, dưới tên bạn.",
    nang_luc={"nhom": True, "gui_chu": True, "gui_file": True},
)


def cau_vao_nhom(ev: dict) -> str:
    """What the Agent reads when someone joins a group (0.84.2). Written for the model, so Vietnamese like the
    rest of the bot prompts. It says plainly this is an event and not a message, gives the join time Zalo
    reported, and tells the Agent to stay silent unless its own instructions cover newcomers: Javis has no
    greeting of its own, so a bot whose owner never asked for one must not start greeting people."""
    from datetime import datetime
    md = (ev.get("metadata") or {}).get("member_join") or {}
    ten = str(ev.get("sender_name") or "").strip() or str(ev.get("sender_id") or "").strip() or "Một người"
    try:
        luc = datetime.fromtimestamp(float(md.get("time") or ev.get("created_at") or time.time()), localefmt.tz())
        gio = luc.strftime("%H:%M ngày %d/%m/%Y")
    except (TypeError, ValueError, OverflowError, OSError):
        gio = ""
    if md.get("added_by_me"):
        cach = ", do chính tài khoản này thêm vào"
    elif md.get("added_by"):
        cach = ", do một thành viên khác thêm vào"
    else:
        cach = ""
    return (f"[Sự kiện nhóm, KHÔNG phải tin nhắn: {ten} vừa vào nhóm"
            + (f" lúc {gio}" if gio else "") + cach + ". "
            "Làm đúng theo chỉ dẫn của bạn về người mới vào nhóm; câu bạn gửi sẽ tự tag người này. "
            "Chỉ dẫn của bạn không nói gì về người mới vào nhóm thì trả đúng [IM_LANG].]")


def tai_khoan():
    import zalo_personal_channel
    return zalo_personal_channel.tai_khoan()


def bat(account_id: str, on: bool) -> dict:
    import zalo_personal_channel
    return zalo_personal_channel.bat(account_id, on)


async def nhap_lich_su(account_id: str) -> dict:
    """Nhập tin cũ (khoảng 2 tuần javis-zalo giữ được) vào Hộp thư, xem `zalo_personal_channel.nhap_lich_su`."""
    import zalo_personal_channel
    return await zalo_personal_channel.nhap_lich_su(account_id)


def trang_thai() -> dict:
    import zalo_personal_channel
    return zalo_personal_channel.trang_thai()


# ---- tag người được trả lời (0.65.6) -----------------------------------------------------------
# Tool gửi tin của MCP chỉ nhận chữ nên không tag được ai. Trong nhóm, bot trả lời ai thì tag đúng người đó
# bằng chính CLI `zalo-agent-cli` (`msg send --mention`), xem `zalo_cli`. Không có công tắc nào: tag hỏng
# thì tin vẫn đi như cũ, chỉ mất cái tag.
TAG_TIMEOUT = 40            # giây: gửi một dòng chữ mà quá thế là bất thường; gồm cả lần đầu npx nạp package
TAG_FAIL_LIMIT = 3          # từng đó lần tag hỏng LIÊN TIẾP thì nghỉ, khỏi lần nào cũng trả thêm vài giây cho một thứ đang hỏng
TAG_PAUSE = 600             # giây nghỉ tag sau khi hỏng liên tiếp; tin vẫn đi bằng MCP như cũ
# Trần một tin (0.171.2). Zalo từ chối cả tin quá dài (quanh 2000 ký tự) và khách không nhận được gì: chủ repo
# 16/10/2026 gặp lần thứ ba, hai lần trước ở khách Khang Duy Dao. 1500 chừa chỗ cho "@Tên" khi tag trong nhóm.
TIN_TOI_DA = 1500
NGHI_GIUA_DOAN = 1.2        # giây nghỉ giữa hai đoạn của một câu trả lời dài, cho giống người gõ và giữ thứ tự
# Chỗ cắt tốt theo thứ tự ưu tiên: hết đoạn văn, hết dòng, hết câu, rồi mới tới khoảng trắng.
_CHO_CAT = (re.compile(r"\n\s*\n"), re.compile(r"\n"), re.compile(r"[.!?…:;](?=\s)"), re.compile(r"\s"))
_TAG_STATE: dict = {}       # conn_id -> {"fails": số lần hỏng liên tiếp, "until": giờ hết nghỉ}
# "Đang soạn tin" while the bot writes a private reply (0.413.0, owner 30/10/2026: customers should not be able to tell
# the bot from a person). Needs the MCP tool `zalo_send_typing` (javis-zalo >= 1.9.0); an older MCP answers "tool not
# found" and the indicator is simply skipped for TYPING_OFF seconds, the reply itself never waits on it.
TYPING_TOOL = "zalo_send_typing"
TYPING_DELAY = 1.5          # seconds: a turn that ends quickly (silence, takeover) never shows the indicator
TYPING_EVERY = 4.0          # Zalo drops the indicator after a few seconds without a new event
TYPING_OFF = 3600           # seconds without trying again once the MCP lacks the tool or refuses it
_TYPING_OFF_UNTIL: dict = {}  # conn_id -> time the indicator may be tried again
_UID_RE = re.compile(r"\d{3,25}")


def _utf16_len(s: str) -> int:
    """Zalo (như JavaScript) đo vị trí chữ theo đơn vị UTF-16: emoji chiếm 2, khác ký tự Python."""
    return len(s.encode("utf-16-le")) // 2


def tagged_text(text: str, name: str) -> tuple:
    """`(chữ gửi đi, vị trí, độ dài)` của đoạn tag người tên `name`.

    Model đã tự viết "@Tên" thì tag đúng chỗ đó (khỏi tag hai lần), chưa thì đặt "@Tên " ở ĐẦU tin. Tên phải kết thúc ở ranh giới
    chữ: "@Quý" không được ăn vào đầu "@Quýnh".
    """
    tok = "@" + name
    m = re.search(re.escape(tok) + r"(?!\w)", text, re.IGNORECASE)
    if m:
        return text, _utf16_len(text[:m.start()]), _utf16_len(text[m.start():m.end()])
    return tok + " " + text, 0, _utf16_len(tok)


def _bo_dau(s: str) -> str:
    """Lowercase without Vietnamese diacritics, SAME length as the input (one char in, one out), so a
    match found on this form maps back to the same positions in the real text."""
    import unicodedata
    out = []
    for ch in s:
        if ch in "đĐ":
            out.append("d")
            continue
        base = unicodedata.normalize("NFD", ch)[0]
        out.append(base.lower() if len(base) == 1 else ch.lower())
    return "".join(out)


def tag_ten_trong_cau(text: str, danh_ba, bo_qua=(), chiem=()) -> list:
    """`[(pos, uid, len)]` (UTF-16 units) for every "@Name" in `text` that names someone in `danh_ba`.

    Field report 2026-10-14: a bot told to tag "@Minh Quý" and "@Phạm Đại" wrote both names, but only
    the person it was answering got a real Zalo tag; the others were plain text and Zalo notified no
    one. `danh_ba` is `[{uid, name}]` (conversations.group_speakers: everyone who has written in the
    group). Longest names are tried first ("@Minh Quý Phạm" beats "@Minh Quý"), case and diacritics
    are ignored ("@minh quy" still tags), a name must end on a word boundary, and `bo_qua` holds uids
    already tagged (the person being answered) or never to tag (the account itself).

    `chiem` holds `(pos, len)` stretches that already carry a tag (the person being answered). An "@" inside one is
    skipped: "@Tuan Fernel" must not also become "@Tuan" for another member (0.331.0, see `_khong_chong`)."""
    import re as _re
    ten = []
    for d in danh_ba or []:
        uid = str((d or {}).get("uid") or "").strip()
        name = " ".join(str((d or {}).get("name") or "").split())
        if _UID_RE.fullmatch(uid) and len(name) >= 2 and uid not in bo_qua:
            ten.append((_bo_dau(name), uid, len(name)))
    if not ten or "@" not in text:
        return []
    ten.sort(key=lambda x: -x[2])
    chuan = _bo_dau(text)
    ra, da_tag = [], set(bo_qua)
    for m in _re.finditer("@", text):
        i = m.start() + 1
        at = _utf16_len(text[:m.start()])
        if any(p <= at < p + n_ for p, n_ in chiem):
            continue
        for key, uid, n in ten:
            if uid in da_tag or chuan[i:i + n] != key:
                continue
            nxt = text[i + n:i + n + 1]
            if nxt and (nxt.isalnum() or nxt == "_"):
                continue
            ra.append((_utf16_len(text[:m.start()]), uid, _utf16_len(text[m.start():i + n])))
            da_tag.add(uid)
            break
    return ra


def _khong_chong(specs) -> list:
    """`[(pos, uid, len)]` with no two tags over the same text, sorted by position. The first claim wins.

    Field report 2026-10-26: the reply tag covered "@Tuan Fernel" and the name finder also tagged "@Tuan" at the same
    spot for another member. Zalo on a computer drew one tag; Zalo on a phone laid the second tag over the markup
    of the first and showed `@Tuannntion href="zm://Profile/..._mention">@Tuan Fernel</a_mention>` as text."""
    giu = []
    for pos, uid, ln in specs:
        if all(pos + ln <= p or p + n <= pos for p, _u, n in giu):
            giu.append((pos, uid, ln))
    return sorted(giu)


def _danh_ba_nhom(conn_id: str, chat_id: str) -> list:
    """Everyone who has written in this group, from the inbox store (instant, no network call)."""
    try:
        import conversations
        return conversations.group_speakers(f"zalo_personal:{conn_id}", str(chat_id))
    except Exception as e:      # noqa: BLE001 - no directory = only the answered person gets tagged
        print(f"[zalo-personal] danh bạ nhóm lỗi: {type(e).__name__}: {e}", file=sys.stderr)
        return []


def _clean_mention(mention) -> tuple:
    """`(uid, tên)` dùng được, hoặc `("", "")`. uid phải là số (nó đi vào tham số lệnh); tên chưa biết thì không có gì để tô."""
    if not isinstance(mention, dict):
        return "", ""
    uid = str(mention.get("uid") or "").strip()
    name = " ".join(str(mention.get("name") or "").split())[:80]
    if not _UID_RE.fullmatch(uid) or not name:
        return "", ""
    return uid, name


def _tag_paused(conn_id: str) -> bool:
    return time.time() < float((_TAG_STATE.get(conn_id) or {}).get("until") or 0)


def _tag_result(conn_id: str, ok: bool) -> None:
    st = _TAG_STATE.setdefault(conn_id, {"fails": 0, "until": 0})
    if ok:
        st["fails"], st["until"] = 0, 0
        return
    st["fails"] += 1
    if st["fails"] >= TAG_FAIL_LIMIT:
        st["fails"], st["until"] = 0, time.time() + TAG_PAUSE
        print(f"[zalo-personal] gửi qua CLI (tag người, định dạng) hỏng {TAG_FAIL_LIMIT} lần liên tiếp, nghỉ "
              f"{TAG_PAUSE // 60} phút (tin vẫn gửi như thường)", file=sys.stderr)


def _style_args(styles) -> list:
    """`--style` arguments of `javis-zalo msg send` for `zalo_markup.to_zalo` styles (positions in UTF-16 units)."""
    specs = [f"{int(a)}:{int(n)}:{name}" for a, n, name in styles or () if int(n) > 0 and name in zalo_markup.STYLE_NAMES]
    return ["--style"] + specs if specs else []


async def _send_styled(conn: dict, chat_id: str, text: str, loai: int, styles) -> Optional[tuple]:
    """Send one message WITH text styles (bold, colours...) through `javis-zalo msg send --style` (0.413.0): the MCP
    send tool took plain text only before javis-zalo 1.9.0. Returns `(ok, error)` once there is an outcome, or None when
    nothing was sent and the caller should send the plain text through the MCP. A timeout is an outcome (the CLI may
    have sent it already), like `_send_tagged`."""
    import zalo_cli
    home = zalo_cli.home_of(conn)
    cid = str(conn.get("id") or "")
    args = _style_args(styles)
    if not home or not args or _tag_paused(cid):
        return None
    ok, _data, err = await zalo_cli.run_cli(
        {"home": home}, ["msg", "send"], [chat_id, text], ["-t", str(int(loai))] + args, timeout=TAG_TIMEOUT)
    if ok:
        _tag_result(cid, True)
        return True, ""
    _tag_result(cid, False)
    if zalo_cli.is_timeout(err):
        return False, f"không rõ tin có định dạng đã đi chưa ({err})"
    print(f"[zalo-personal] gửi có định dạng lỗi, gửi lại chữ thường: {err[:200]}", file=sys.stderr)
    return None


async def _send_tagged(conn: dict, chat_id: str, text: str, mention, styles=()) -> Optional[tuple]:
    """Gửi một tin nhóm CÓ TAG. Trả `(ok, lỗi)` khi đã có kết cục, hoặc None khi chưa gửi gì và người gọi nên gửi thường.

    Hết giờ là kết cục KHÔNG RÕ: CLI có thể đã gửi xong mới bị giết. Gửi lại bằng đường khác thì có thể thành hai tin dưới tên chủ trong
    nhóm, còn không gửi lại thì cùng lắm thiếu một câu (và Hộp thư/nhật ký bot ghi lỗi), nên hết giờ trả lỗi chứ không rơi về gửi thường.
    """
    import zalo_cli
    import zalo_personal_channel as zc
    uid, name = _clean_mention(mention)
    home = zalo_cli.home_of(conn)
    cid = str(conn.get("id") or "")
    if not home or _tag_paused(cid):
        return None
    final, specs = text, []
    if uid:
        final, pos, ln = tagged_text(text, name)
        specs.append((pos, uid, ln))
    # Every other "@Name" the message carries (0.123.0), never the account itself, never inside the reply tag.
    minh = str((zc._ID_MINH.get(cid) or {}).get("uid") or "")
    specs += tag_ten_trong_cau(final, _danh_ba_nhom(cid, chat_id), bo_qua={u for u in (uid, minh) if u},
                               chiem=[(p, n) for p, _u, n in specs])
    if not specs:
        return None
    specs = _khong_chong(specs)
    # "@Name " put in front of the text moves every style by its length.
    lech = _utf16_len(final) - _utf16_len(text)
    styles = [(a + lech, n, name) for a, n, name in styles or ()]
    # Tiếng vọng của tin có tag mang cả "@Tên": nhớ luôn bản này, không thì vòng đọc tưởng chủ vừa tự tay nhắn và bot im 10 phút.
    zc.ghi_da_gui(cid, chat_id, final)
    ok, _data, err = await zalo_cli.run_cli(
        {"home": home}, ["msg", "send"], [chat_id, final],
        ["-t", "1", "--mention"] + [f"{p}:{u}:{n}" for p, u, n in specs] + _style_args(styles), timeout=TAG_TIMEOUT)
    if ok:
        _tag_result(cid, True)
        return True, ""
    _tag_result(cid, False)
    if zalo_cli.is_timeout(err):
        return False, f"không rõ tin có tag đã đi chưa ({err})"
    print(f"[zalo-personal] gửi có tag lỗi, gửi lại không tag: {err[:200]}", file=sys.stderr)
    return None


def cat_tin(text: str, toi_da: int = TIN_TOI_DA) -> list:
    """Cắt một câu trả lời dài thành các đoạn không quá `toi_da` ký tự (0.171.2).

    Cắt ở chỗ hết đoạn văn trước, rồi hết dòng, hết câu, cuối cùng là khoảng trắng: không cắt giữa chữ,
    và không cắt giữa một link (link không có khoảng trắng). Chỉ khi cả cửa sổ không có khoảng trắng nào
    (một chuỗi dài liền) mới cắt cứng. Chỗ cắt nằm ở nửa sau cửa sổ, kẻo đoạn đầu cụt lủn."""
    con = str(text or "").strip()
    if len(con) <= toi_da:
        return [con] if con else []
    ra = []
    while len(con) > toi_da:
        cua_so = con[:toi_da + 1]
        cat = 0
        for mau in _CHO_CAT:
            vt = [m.end() for m in mau.finditer(cua_so) if toi_da // 2 <= m.end() <= toi_da]
            if vt:
                cat = vt[-1]
                break
        if not cat:
            cat = toi_da
        doan = con[:cat].strip()
        if doan:
            ra.append(doan)
        con = con[cat:].strip()
    if con:
        ra.append(con)
    return ra


async def gui(tk: dict, chat_id: str, text: str, chat_type: str = "private", mention=None):
    """Gửi qua MCP: `threadId`, `text` và kiểu cuộc chat (0 = chat riêng, 1 = nhóm).

    `mention={"uid", "name"}` (chỉ có nghĩa trong nhóm): tag người đó, xem `_send_tagged`.

    Khoá kiểu cuộc chat mà MCP javis-zalo (và zalo-agent-cli 1.6.2 trước nó) THẬT SỰ đọc là `threadType` (mcp-tools.js), không
    phải `type` như tài liệu mcp-guide ghi. MCP bỏ qua khoá lạ mà không báo lỗi, nên gửi `type` một
    mình thì tin nhóm đi như chat riêng và Zalo không giao được (chủ thấy bot trả lời trong Hộp thư
    mà nhóm im, 29/09/2026). Gửi cả hai: `threadType` cho bản đang ghim, `type` cho bản khác
    đọc theo tài liệu; khoá thừa bị MCP bỏ qua.
    """
    import zalo_personal_channel
    conn = zalo_personal_channel.ket_noi_theo_id(str(tk.get("id") or tk.get("external_id") or ""))
    if not conn:
        return False, localefmt.chu("tài khoản Zalo này không còn ở trang Kết nối (hoặc đang tắt)",
                                     "this Zalo account is no longer on the Connections page (or is turned off)")
    # Zalo shows its own tag markup as plain code (2026-10-19): keep only the "@Name", which `_send_tagged` turns into a real tag.
    sach = zalo_personal_channel.strip_mention_markup(text)
    if sach != str(text or ""):
        # The caller remembered the raw text as our echo; remember the cleaned one too, or the read loop takes it for the owner.
        try:
            zalo_personal_channel.ghi_da_gui(str(conn.get("id") or ""), str(chat_id), sach)
        except Exception:      # noqa: BLE001 - worst case one duplicate line in the inbox
            pass
    text = sach
    # Several short messages the bot chose to send (0.281.0, bot_split): each part is its own message, and a part
    # still longer than `TIN_TOI_DA` is cut as before. Without the marker this is exactly the old single split.
    import bot_split
    doan = [d for p in (bot_split.parts(text) or [str(text or "")]) for d in (cat_tin(p) or [])] or [str(text or "")]
    if len(doan) == 1:
        return await _gui_mot(conn, chat_id, doan[0], chat_type, mention)
    # Tin dài: gửi lần lượt từng đoạn. Mỗi đoạn về vòng đọc như một tin riêng, nên phải nhớ TỪNG đoạn là
    # tiếng vọng (người gọi chỉ nhớ cả câu). Thiếu bước này thì đoạn hai trở đi bị coi là chủ nhắn tay: Hộp thư
    # hiện đôi và bot im TAY_IM giây.
    cid = str(conn.get("id") or "")
    for i, phan in enumerate(doan):
        if i:
            await asyncio.sleep(NGHI_GIUA_DOAN)
        try:
            zalo_personal_channel.ghi_da_gui(cid, str(chat_id), phan)
        except Exception:      # noqa: BLE001 - không nhớ được tiếng vọng thì vẫn gửi, tệ nhất là một dòng trùng
            pass
        # Trong nhóm chỉ tag người được trả lời ở đoạn ĐẦU, kẻo một người bị tag mấy lần cho một câu trả lời.
        ok, loi = await _gui_mot(conn, chat_id, phan, chat_type, mention if i == 0 else None)
        if not ok:
            return False, localefmt.chu(f"đoạn {i + 1}/{len(doan)}: {loi}", f"part {i + 1}/{len(doan)}: {loi}")[:300]
    return True, ""


async def _gui_mot(conn: dict, chat_id: str, text: str, chat_type: str, mention=None):
    """Gửi MỘT tin (đã vừa trần `TIN_TOI_DA`). `(ok, lỗi)`.

    Markdown in the reply becomes Zalo text styles (0.413.0, `zalo_markup.to_zalo`): the customer sees bold or coloured
    words, never the stars. When the styled send cannot run, the plain text still goes out through the MCP."""
    import zalo_personal_channel
    loai = 1 if str(chat_type or "") == "group" else 0
    text, styles = zalo_markup.to_zalo(str(text or ""))
    if loai == 1 and (mention or "@" in text):
        r = await _send_tagged(conn, str(chat_id), text, mention, styles)
        if r is not None:
            return r
    if styles:
        r = await _send_styled(conn, str(chat_id), text, loai, styles)
        if r is not None:
            return r
    try:
        d = await zalo_personal_channel._goi(conn, "zalo_send_message", {
            "threadId": str(chat_id), "text": str(text or ""),
            "threadType": loai, "type": loai,
        })
    except Exception as e:
        return False, str(e)[:300]
    if isinstance(d, dict) and d.get("success") is False:
        return False, str(d.get("error") or d.get("message") or localefmt.chu("Zalo từ chối", "Zalo refused"))[:300]
    # javis-zalo returns the id Zalo gave the message. "success" without one means Zalo never confirmed it (0.283.0,
    # 22/10/2026: replies in the bot history that never reached the customer): report a failure, so the inbox marks the
    # reply as not sent instead of showing it as delivered.
    if isinstance(d, dict) and d.get("success") is True and "messageId" in d and not d.get("messageId"):
        return False, localefmt.chu("Zalo không xác nhận đã nhận tin (không có mã tin)",
                                    "Zalo did not confirm the message (no message id)")
    return True, ""


async def send_typing(conn_id: str, chat_id: str, chat_type: str = "private") -> bool:
    """Show "đang soạn tin" in one chat (0.413.0, `zalo_send_typing` of javis-zalo >= 1.9.0). True when Zalo took it.
    Never raises: the indicator is a nicety, and a connection whose MCP lacks the tool is not asked again for
    TYPING_OFF seconds."""
    import zalo_personal_channel
    cid = str(conn_id or "")
    if time.time() < float(_TYPING_OFF_UNTIL.get(cid) or 0):
        return False
    conn = zalo_personal_channel.ket_noi_theo_id(cid)
    if not conn:
        return False
    try:
        d = await zalo_personal_channel._goi(conn, TYPING_TOOL, {
            "threadId": str(chat_id), "threadType": 1 if str(chat_type or "") == "group" else 0})
    except Exception as e:      # noqa: BLE001 - older javis-zalo: "Tool zalo_send_typing not found"
        _TYPING_OFF_UNTIL[cid] = time.time() + TYPING_OFF
        print(f"[zalo-personal] không bật được \"đang soạn tin\" ({str(e)[:120]}), thử lại sau "
              f"{TYPING_OFF // 60} phút", file=sys.stderr)
        return False
    if isinstance(d, dict) and d.get("success") is False:
        _TYPING_OFF_UNTIL[cid] = time.time() + TYPING_OFF
        return False
    return True


async def keep_typing(conn_id: str, chat_id: str, chat_type: str = "private") -> None:
    """Run while a reply is being written; the caller cancels it. Starts after TYPING_DELAY, repeats every
    TYPING_EVERY seconds, stops for good as soon as one attempt fails."""
    await asyncio.sleep(TYPING_DELAY)
    while await send_typing(conn_id, chat_id, chat_type):
        await asyncio.sleep(TYPING_EVERY)


async def send_reaction(tk: dict, chat_id: str, msg_id: str, name: str, chat_type: str = "private",
                      cli_msg_id: str = ""):
    """Put an emoji reaction on one message (0.334.0, javis-zalo >= 1.7.0 `zalo_add_reaction`). `(ok, error)`.

    `cli_msg_id` is optional: the MCP looks it up from its buffer or history when it is missing."""
    import zalo_personal_channel
    conn = zalo_personal_channel.ket_noi_theo_id(str(tk.get("id") or tk.get("external_id") or ""))
    if not conn:
        return False, localefmt.chu("tài khoản Zalo này không còn ở trang Kết nối (hoặc đang tắt)",
                                     "this Zalo account is no longer on the Connections page (or is turned off)")
    args = {"threadId": str(chat_id), "threadType": 1 if str(chat_type or "") == "group" else 0, "msgId": str(msg_id),
            "reaction": str(name)}
    if cli_msg_id:
        args["cliMsgId"] = str(cli_msg_id)
    try:
        d = await zalo_personal_channel._goi(conn, "zalo_add_reaction", args)
    except Exception as e:
        return False, str(e)[:300]
    if isinstance(d, dict) and d.get("success") is False:
        return False, str(d.get("error") or d.get("message") or localefmt.chu("Zalo từ chối", "Zalo refused"))[:300]
    return True, ""


async def gui_anh(tk: dict, chat_id: str, paths, chat_type: str = "private"):
    """Send images the bot asked for (0.84.3), after its text. `(ok, error)`.

    The MCP send tool takes text only, so this goes through the CLI (`msg send-image`) in the session of the signed-in
    account, like tagging does (`zalo_cli`). `paths` are absolute and already checked by `bot_images.pick`."""
    import zalo_cli
    import zalo_personal_channel
    conn = zalo_personal_channel.ket_noi_theo_id(str(tk.get("id") or tk.get("external_id") or ""))
    if not conn:
        return False, localefmt.chu("tài khoản Zalo này không còn ở trang Kết nối (hoặc đang tắt)",
                                     "this Zalo account is no longer on the Connections page (or is turned off)")
    home = zalo_cli.home_of(conn)
    ds = [str(x) for x in (paths or []) if str(x or "").strip()]
    if not home or not ds:
        return False, localefmt.chu("không có ảnh hoặc thư mục phiên để gửi", "no image or session folder to send with")
    loai = "1" if str(chat_type or "") == "group" else "0"
    ok, _data, err = await zalo_cli.run_cli({"home": home}, ["msg", "send-image"], [str(chat_id)] + ds, ["-t", loai])
    return (True, "") if ok else (False, str(err or "")[:300])


class Transport:
    """Lớp vận chuyển cho bot trên Zalo cá nhân, đúng khế ước của `chatbot_runtime.start_bot`.

    KHÔNG tự đọc tin: vòng đọc của `zalo_personal_channel` là nguồn duy nhất (một cursor, hai
    người đọc là mất tin của nhau). Lớp này đăng ký ở đó, được đưa từng tin khách mới, và gửi
    câu trả lời bằng `gui`. `token` ở đây là id kết nối Zalo (xem `channel_accounts.get_token`).
    """

    def __init__(self, token, whitelist, answer_fn, command_fn=None, download_dir=None,
                 commands=None, precheck_fn=None, event_fn=None, giau_trang_thai=True,
                 cfg_fn=None, policy=None, **_):
        self.download_dir = download_dir
        self.conn_id = str(token or "")
        self.answer_fn = answer_fn
        self.precheck_fn = precheck_fn
        self.event_fn = event_fn        # tin dịch vụ của nhóm: ở đây chỉ dùng "thay_nhom"
        self.cfg_fn = cfg_fn            # đọc cấu hình bot SỐNG (chế độ trả lời trong nhóm)
        self.policy = policy            # móc bộ phán xử hội thoại nhóm (0.65.0), xem chatbot_runtime.PolicyHooks
        self.account_id = self.conn_id
        self.status = "off"
        self.last_error = ""
        self._task = None
        self._khoa = {}         # thread -> Lock: một cuộc chat một lượt, khỏi trả lời chồng nhau

    def _nhuong_phut(self):
        """The bot's saved `nhuong_tay_phut` as an int, or None when the owner never set it (old records, blank)."""
        v = ((self.cfg_fn() if self.cfg_fn else {}) or {}).get("nhuong_tay_phut")
        if v is None or str(v).strip() == "":
            return None
        return max(0, int(v))

    def tay_im(self) -> int:
        """Giây bot nhường sau khi chủ nhắn tay (0.172.0): cài đặt `nhuong_tay_phut` của bot, 0 = không nhường. Không
        khai thì mặc định của kênh (`zalo_personal_channel.TAY_IM`, 10 phút)."""
        import zalo_personal_channel as zc
        n = self._nhuong_phut()
        return zc.TAY_IM if n is None else n * 60

    def yield_explicit(self) -> bool:
        """True when the owner saved a yield time on this bot. Only then do groups get the 0.172.0 logic (tags answered
        during the window, held messages released afterwards); otherwise groups stay silent as before."""
        return self._nhuong_phut() is not None

    def nhan_ket_ban(self) -> bool:
        """Bot này tự nhận lời mời kết bạn và đọc lời giới thiệu kèm theo (0.172.0, `zalo_friend_intake`)."""
        v = ((self.cfg_fn() if self.cfg_fn else {}) or {}).get("nhan_ket_ban")
        return v is True or str(v).strip().lower() in ("1", "true", "yes", "on")

    # ---- vòng đời ------------------------------------------------------------------
    def start(self):
        import zalo_personal_channel as zc
        zc.dang_ky_bot(self.conn_id, self)
        self.status = "starting"
        self._task = asyncio.get_running_loop().create_task(self._giam_sat())

    def stop(self):
        import zalo_personal_channel as zc
        zc.huy_dang_ky_bot(self.conn_id, self)
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        self.status = "off"

    async def _giam_sat(self):
        """Đo sức khoẻ để thẻ bot nói thật: chấm xanh chỉ khi vòng đọc đang đọc được."""
        import zalo_personal_channel as zc
        while True:
            try:
                tt = zc._TT.get(self.conn_id) or {}
                if not zc.ket_noi_theo_id(self.conn_id):
                    self.status = "error"
                    self.last_error = localefmt.chu(
                        "Kết nối Zalo này không còn (hoặc đang tắt) ở trang Kết nối, "
                        "bot không nhận được tin.",
                        "This Zalo connection is gone (or turned off) on the Connections page, "
                        "so the bot receives no messages.")
                elif tt.get("loi"):
                    self.status = "error"
                    self.last_error = str(tt["loi"])
                elif zc.evicted_recently(self.conn_id):
                    # 0.283.0: reading answers, but another session of the account holds the live socket, so the bot
                    # hears only seconds after each reconnect. Green here hid three hours of missed tags (22/10/2026).
                    self.status = "error"
                    self.last_error = localefmt.chu(
                        "Một phiên khác của cùng nick đang giành kết nối Zalo, bot lỡ phần lớn tin. Đóng Zalo Web của "
                        "nick này và các Javis hay Claude khác dùng cùng nick.",
                        "Another session of this account keeps taking the Zalo connection, so the bot misses most "
                        "messages. Close Zalo Web for this account and any other Javis or Claude client using it.")
                elif tt.get("lan_cuoi"):
                    self.status = "polling"
                    self.last_error = ""
                else:
                    self.status = "starting"
            except Exception:
                pass
            await asyncio.sleep(10)

    # ---- một tin khách ---------------------------------------------------------------
    def _che_do_nhom(self) -> str:
        try:
            return str((self.cfg_fn() if self.cfg_fn else {}).get("reply_when") or "")
        except Exception:
            return ""

    async def _bao_nhom(self, thread: str, ev: dict):
        """Báo cho bộ giám sát THẤY một nhóm (có tin bất kỳ về từ đó) để nhóm chưa cho phép hiện
        lên hàng chờ của thẻ bot, kèm nút Cho phép. Không thì chủ phải tự đi tìm id nhóm Zalo."""
        if not self.event_fn:
            return
        try:
            r = self.event_fn("thay_nhom", {"chat_id": thread,
                                            "chat_title": str(ev.get("chat_title") or "")})
            if asyncio.iscoroutine(r):
                await r
        except Exception as e:
            print(f"[zalo-personal bot {self.conn_id}] báo nhóm lỗi: {e}", file=sys.stderr)

    def _nho_anh_tron(self, ev: dict, thread: str):
        import zalo_personal_channel as zc
        minh = (zc._ID_MINH.get(self.conn_id) or {}).get("uid")
        nguoi = str(ev.get("sender_id") or "")
        url = str((ev.get("metadata") or {}).get("image_url") or "")
        if not nguoi or not url or (minh and nguoi == minh):
            return
        if time.time() - float(ev.get("created_at") or 0) > zc.TUOI_TOI_DA:
            return
        try:
            self.policy.nho_anh({"chat_id": thread, "chat_type": "group", "user_id": nguoi, "co_anh": True,
                                 "image_url": url, "message_id": str(ev.get("external_message_id") or ""),
                                 "account_id": self.conn_id})
        except Exception as e:      # noqa: BLE001 - nhớ ảnh hỏng không được làm sập vòng đọc tin
            print(f"[zalo-personal bot {self.conn_id}] nhớ ảnh trơn lỗi: {type(e).__name__}: {e}", file=sys.stderr)

    async def _tai_file(self, files: list, text: str, meta: dict, thread: str, chi_file: bool) -> tuple:
        """Tải các file khách gửi về `inbox/khach` của brain bot, rồi gắn dấu file vào lượt.

        Trả `(text, các file đã tải, đi tiếp không)`. Gọi khi đã cầm khoá cuộc chat, nên rào lại những
        gì có thể đổi trong lúc chờ khoá (bot tắt, chủ tự nhắn, Tiếp quản). Lưu file là GHI vào brain,
        nên cần mức quyền Được ghi trở lên: bot Chỉ đọc không tải. Lượt chỉ có file mà không được tải
        thì dừng cả lượt; lượt có chữ thì báo cho Agent biết khách có gửi file. Lượt bị huỷ sau khi đã
        tải thì xoá file vừa tải, không để rác trong brain."""
        import conversations
        import zalo_attachments
        import zalo_personal_channel as zc
        from pathlib import Path
        import chatbot_store
        # Per-chat exception (0.172.0): a chat raised to "Can write" may send files even when the bot is read only.
        cfg = chatbot_store.ap_ngoai_le((self.cfg_fn() if self.cfg_fn else {}) or {}, meta)
        if cfg.get("muc_quyen") not in ("auto", "full"):
            if chi_file:
                return text, [], False
            return text + "\n[Khách có gửi kèm file; bot này không có quyền lưu file nên không mở được.]", [], True
        # A group message that tags the account or replies to it is answered during the owner's yield when the
        # bot's yield time was set explicitly (0.172.0, see `xu_ly`), so its file must be downloaded too.
        goi_trong_nhuong = (meta.get("chat_type") == "group" and (meta.get("mentioned") or meta.get("reply_to_bot"))
                            and zc.yield_explicit(self.conn_id))
        if (zc._BOTS.get(self.conn_id) is not self or not zc.ket_noi_theo_id(self.conn_id)
                or (zc.chu_vua_nhan_tay(self.conn_id, thread) and not goi_trong_nhuong)
                or conversations.che_do("zalo_personal", self.conn_id, thread) == "human"):
            return text, [], False
        r = self.precheck_fn(text, meta)
        if asyncio.iscoroutine(r):
            r = await r
        if r is not None:
            return text, [], False
        ddir = self.download_dir(thread) if callable(self.download_dir) else self.download_dir
        inbox = Path(ddir) if ddir else None
        if inbox is None or inbox.parts[-2:] != ("inbox", "khach"):
            raise ValueError("thiếu thư mục inbox/khach của brain bot")
        da_tai = []
        for att in files:
            saved, why = await zalo_attachments.fetch_file(att, inbox)
            if saved:
                da_tai.append(saved)
                # Off the event loop: a long PDF takes a moment to turn into text (0.336.0).
                text += "\n" + await asyncio.to_thread(zalo_attachments.turn_text, saved)
            else:
                text += "\n[Không tải được file Zalo: " + why + ". Không suy đoán nội dung.]"
        if zc._BOTS.get(self.conn_id) is not self:
            for f in da_tai:
                f.unlink(missing_ok=True)
            return text, [], False
        return text, da_tai, True

    async def xu_ly(self, ev: dict):
        """Quyết định có trả lời một tin khách không, và trả lời nếu có.

        Các rào, theo thứ tự rẻ tới đắt (cái nào chặn thì KHÔNG tốn một lượt model):
          - tin dạng CHỮ, FILE, hoặc tin ẢNH có CHÚ THÍCH (0.65.13: chú thích coi như nội dung tin, nên "@bot ..." viết trong chú thích ảnh là một cái tag thật),
            ở chat riêng hoặc nhóm (tiếng bỏ qua; file tải sau precheck; ảnh trơn trong nhóm không trả lời nhưng được NHỚ cho lần người đó gọi bot ngay sau);
          - tin cũ quá `TUOI_TOI_DA` bỏ qua (bộ đệm MCP lúc mới bật);
          - chủ vừa TỰ TAY nhắn cuộc chat này thì nhường;
          - nhóm: phải được chủ cho phép (chưa thì im TUYỆT ĐỐI và hiện lên hàng chờ duyệt);
          - chế độ Tự đánh giá, tin không ai gọi tên: giống câu hỏi không, rồi chờ `NHUONG_GIAY`
            để nhường nếu có người nhắn tay trong lúc đó;
          - rồi tới các luật chung của bot (Tiếp quản, hạn mức, tra tài liệu) trong `answer_fn`;
          - cuối cùng chính bot tự quyết: Agent viết `[IM_LANG]` nghĩa là không gửi gì.

        Trong NHÓM bot KHÔNG bao giờ nói một câu cố định nào (như "em chưa được bật cho nhóm
        này" của Telegram): nick này là người thật, câu đó khai với cả nhóm rằng đây là máy.
        """
        import chatbot_tu_dong
        import conversations      # nhập trễ: conversations nạp sổ kênh lúc import, nhập ở đầu file là vòng import
        import zalo_personal_channel as zc
        loai = ev.get("chat_type")
        kieu = ev.get("message_type")
        md0 = ev.get("metadata") or {}
        vao_nhom = md0.get("member_join")
        if vao_nhom and loai != "group":
            return
        if loai not in ("private", "group") or (kieu not in ("text", "image", "file", "reaction", "video", "audio")
                                                and not vao_nhom):
            return
        nhom = loai == "group"
        # A customer's emoji reaction (0.334.0) reaches the bot as its describing line. Nothing here decides whether it
        # deserves an answer: the judge does in a group ("Tự đánh giá"), the Agent everywhere else.
        is_reaction = kieu == "reaction"
        # File khách gửi (một tin file, hoặc các file đi theo lượt gộp chat riêng của `zc.gop_tin`).
        # Rào chặt: sai tài khoản, không phải khách, thiếu người gửi, chat riêng mà người gửi không phải
        # chủ cuộc chat, hoặc không có precheck thì KHÔNG tải. Lượt chỉ có file thì bỏ cả lượt; lượt có
        # chữ thì vẫn trả lời chữ, chỉ bỏ file.
        if md0.get("gop"):
            files = md0.get("attachments") or []
        else:
            files = [md0.get("attachment")] if kieu == "file" else []
        files = [a for a in files if isinstance(a, dict)]
        if files and (str(ev.get("account_id") or "") != self.conn_id
                      or ev.get("sender_type") != "customer" or not ev.get("sender_id")
                      or not self.precheck_fn or not zc.ket_noi_theo_id(self.conn_id)
                      or (not nhom and str(ev.get("sender_id")) != str(ev.get("external_chat_id")))):
            files = []
        chi_file = kieu == "file"
        if chi_file and not files:
            return
        # Tin ảnh có CHÚ THÍCH (0.65.13) xử lý như tin chữ với chú thích làm nội dung: "@Javis Vũ ..." viết trong phần chú thích của ảnh
        # là một cái tag thật. Trước đây mọi tin không phải chữ bị bỏ, nên tag kèm ảnh không bao giờ tới bot. Ảnh trơn: xem `_nho_anh_tron`.
        co_anh = kieu == "image"
        # 0.433.0: a video the customer sent in this private turn; the bot looks at its frames (`chatbot_runtime`).
        video_url = str(md0.get("video_url") or "") if loai == "private" and not vao_nhom else ""
        # 0.435.0: voice messages of this private turn (a merged turn carries a list, a single message its own link).
        audio_urls = ([] if loai != "private" or vao_nhom
                      else list(md0.get("audio_urls") or []) if md0.get("gop")
                      else [md0["audio_url"]] if kieu == "audio" and md0.get("audio_url") else [])
        if vao_nhom:
            # 0.84.2: someone joined the group. The newcomer is the "sender", so a reply tags them (`_gui`).
            # Javis writes no greeting of its own: the bot's Agent decides, and stays silent when its
            # instructions say nothing about newcomers.
            text = cau_vao_nhom(ev)
        else:
            # Lượt gộp (0.128.0, `zalo_personal_channel.gop_tin`) đã bóc chú thích ảnh từng tin rồi nối lại: lấy nguyên.
            gop = bool(md0.get("gop"))
            text = (conversations.chu_thich_anh(ev.get("text")) if co_anh and not gop
                    else "" if kieu in ("video", "audio") and not gop      # its text is only its link
                    else str(ev.get("text") or "").strip())
        if chi_file and not text:
            text = "(người dùng gửi file)"
        thread = str(ev.get("external_chat_id") or "")
        if not thread:
            return
        if not text:
            # Ảnh TRƠN trong nhóm (không chú thích) không gọi bot, nhưng phải được NHỚ: cách gửi hay gặp nhất là
            # gửi ảnh rồi nhắn "@bot xem giúp". Trước 0.88.3 ảnh trơn bị bỏ ngay ở đây, trước cả bước nhớ ảnh
            # (nằm trong precheck), nên bot báo "chưa thấy ảnh"; ảnh có vài chữ chú thích thì lại thấy - đúng
            # cảnh "lúc thấy lúc không" chủ repo báo 09/10. Chạy TRƯỚC mọi await: ảnh và câu tag về cùng một
            # nhịp đọc thì ảnh đã được nhớ trước khi lượt của câu tag cần tới nó.
            if co_anh and loai == "group" and self.policy is not None:
                self._nho_anh_tron(ev, thread)
                return
            # Chat riêng: ảnh không kèm chữ vẫn là người ta đang nhờ xem ảnh (gửi đề, gửi bài làm). Trước đây bị bỏ hẳn
            # ở đây, nên bot không bao giờ thấy ảnh gửi trơn (15/10/2026). Đưa cho bot kèm ảnh, Agent tự quyết hỏi gì.
            if audio_urls and not co_anh and not video_url:
                import chatbot_runtime
                text = chatbot_runtime.AUDIO_TRON
            elif video_url and not co_anh:
                import chatbot_runtime
                text = chatbot_runtime.VIDEO_TRON
            elif not (co_anh and loai == "private" and (ev.get("metadata") or {}).get("image_url")):
                return
            else:
                text = "[Khách gửi một ảnh, không kèm lời nhắn]"
        # Không biết cuộc chat là nhóm hay chat riêng (đã hỏi lại bảng mà vẫn không thấy): KHÔNG trả
        # lời. Đoán là chat riêng nghĩa là trả lời từng tin của một nhóm, dưới tên người thật.
        if (ev.get("metadata") or {}).get("chua_ro_loai"):
            return
        # Tin do CHÍNH nick này gửi (id đã học từ tin của nó) không bao giờ là khách, kể cả khi MCP
        # không gắn cờ "của mình": không thì bot tự trả lời chính nó.
        minh = (zc._ID_MINH.get(self.conn_id) or {}).get("uid")
        if minh and str(ev.get("sender_id") or "") == minh:
            return
        if nhom:
            await self._bao_nhom(thread, ev)
        # Lượt "chủ chưa trả lời" (0.136.0, `zc.xa_cho_chu`) cũ là có chủ ý. Since 0.172.0 it is released once the
        # bot's yield time (`zc.tay_im_cua`, default `CHO_CHU_TRA_LOI`) has passed since the owner's LAST hand-typed
        # message; in groups this happens only when the bot's yield time was saved explicitly (`zc.yield_explicit`).
        sau_chu_im = bool((ev.get("metadata") or {}).get("sau_chu_im"))
        if time.time() - float(ev.get("created_at") or 0) > zc.TUOI_TOI_DA and not sau_chu_im:
            return
        # With a 0-minute yield the bot does not go quiet, but a private message the owner has already answered by
        # hand is not answered again under the owner's name (held turns are filtered the same way in `xa_cho_chu`).
        if not nhom and zc.owner_typed_after(self.conn_id, thread, float(ev.get("created_at") or 0)):
            return
        # Chủ vừa nhắn tay thì bot nhường (`nhuong_tay_phut` của bot). Riêng NHÓM của bot ĐÃ ĐẶT số phút nhường, tin
        # TAG thẳng nick hoặc trả lời tin của nick vẫn được trả lời ngay (0.172.0, chủ nick MTM chốt 14/10/2026):
        # người ta gọi đích danh thì im 3 phút là bỏ rơi họ. Xét sau khi biết tin có gọi hay không, ở nhánh nhóm bên
        # dưới. A bot without the setting keeps the old group rule: silent for the whole window.
        chu_nhuong = zc.chu_vua_nhan_tay(self.conn_id, thread)
        if chu_nhuong and (not nhom or not zc.yield_explicit(self.conn_id)):
            return
        meta = {
            "chat_id": thread, "chat_type": "group" if nhom else "private",
            "chat_title": str(ev.get("chat_title") or "") if nhom else "",
            # Trong nhóm id NGƯỜI gửi khác id nhóm: hạn mức và Hộp thư khoá theo người.
            "user_id": str(ev.get("sender_id") or ("" if nhom else thread)),
            "user_name": str(ev.get("sender_name") or ""), "username": "",
            "message_id": str(ev.get("external_message_id") or ""),
            "account_id": self.conn_id,
            # The message a reaction from the bot would go on (0.334.0): this one, or the last real message of a merged
            # private turn. Never a reaction.
            "react_to": (str(md0.get("react_to") or "") if md0.get("gop")
                         else "" if is_reaction else str(ev.get("external_message_id") or "")),
            "react_to_cli": str((md0.get("react_to_cli") if md0.get("gop") else md0.get("cliMsgId")) or ""),
        }
        if is_reaction:
            meta["reaction"] = True
        # Labels the owner put on this chat in the Zalo app (0.281.0, javis-zalo 1.6.0): the bot can skip chats tagged
        # e.g. "Gia đình" (`chatbot_runtime._ly_do_im`) and sees the tags in its prompt. Cached per connection, so this
        # await costs nothing on most messages; any failure leaves the list empty and the turn runs as before.
        try:
            meta["zalo_labels"] = await zc.labels_of_chat(self.conn_id, thread)
        except Exception as e:      # noqa: BLE001
            meta["zalo_labels"] = []
            print(f"[zalo-personal bot {self.conn_id}] tag Zalo lỗi: {type(e).__name__}", file=sys.stderr)
        if co_anh:
            meta["co_anh"] = True
            # 0.74.1: the photo's link, so the bot can actually look at it (see `chatbot_runtime.anh_cho_bot`).
            meta["image_url"] = str((ev.get("metadata") or {}).get("image_url") or "")
            if not nhom:
                zc.nho_anh_rieng(self.conn_id, thread, meta["image_url"])
        elif not vao_nhom and not is_reaction:
            # 0.141.0: a message that QUOTES a photo ("@bot xem ảnh này" as a reply to it) shows the bot that photo.
            # Checked BEFORE the remembered private photo (0.172.0): a quoted photo is the one the person means, the
            # latest photo is only a guess.
            url_quote = zc.anh_duoc_quote(self.conn_id, thread, md0)
            if url_quote:
                meta.update(co_anh=True, image_url=url_quote, anh_quote=True)
            elif not nhom and zc.anh_rieng_gan_day(self.conn_id, thread):
                # Lượt chữ ngay sau một ảnh ở chat riêng ("check xem đúng chưa", trả lời câu hỏi danh tính rồi nhờ
                # tiếp): kèm lại ảnh đó để bot vẫn thấy, kèm một dòng nói rõ ảnh từ tin trước. Giờ theo múi giờ trong
                # Cài đặt, không theo giờ máy: VPS thường chạy UTC.
                from datetime import datetime
                gio, url = zc.anh_rieng_gan_day(self.conn_id, thread)
                meta.update(co_anh=True, image_url=url, anh_truoc=True)
                text = (text + "\n[Kèm ảnh khách gửi lúc " + datetime.fromtimestamp(gio, localefmt.tz()).strftime("%H:%M")
                        + " trong cuộc chat này, có thể liên quan tới tin trên]")
        if audio_urls:
            meta["audio_urls"] = audio_urls
        if video_url:
            meta["video_url"] = video_url
            meta["video_msg"] = str(md0.get("video_msg") or ev.get("external_message_id") or "")
            zc.remember_private_video(self.conn_id, thread, video_url, meta["video_msg"])
        elif not nhom and not vao_nhom and not is_reaction and zc.recent_private_video(self.conn_id, thread):
            # A text right after a video ("anh xem hỗ trợ em với"): show that video again, saying it came earlier.
            from datetime import datetime
            gio, url, mid = zc.recent_private_video(self.conn_id, thread)
            meta.update(video_url=url, video_msg=mid,
                        video_truoc=datetime.fromtimestamp(gio, localefmt.tz()).strftime("%H:%M"))
        duoc_goi = False
        pol = None
        if vao_nhom:
            # An event, not chat: it reaches the Agent in every enabled group whatever "reply when" says
            # (see `chatbot_runtime._ly_do_im`), and skips the reply-policy judge, which scores chat.
            meta["member_join"] = True
            duoc_goi = True
            if chu_nhuong:
                return
        elif nhom:
            conn = zc.ket_noi_theo_id(self.conn_id) or {}
            tag, rep = zc.nhan_dien_goi(self.conn_id, ev, (conn.get("label") or "",))
            meta["mentioned"], meta["reply_to_bot"] = tag, rep
            duoc_goi = tag or rep
            if chu_nhuong and not duoc_goi:
                return      # chủ đang nói chuyện trong nhóm và tin này không gọi ai: nhường như cũ
            if self.policy is not None:
                # Tên gọi tự suy của nick (nhãn kết nối, tên hiển thị học được) để nhận ra gọi tên trơn
                # ("nhi mai ơi"); tin nào gọi chắc chắn thì `prepare` đặt `meta["mentioned"]`.
                meta["aliases_auto"] = [conn.get("label") or "", (zc._ID_MINH.get(self.conn_id) or {}).get("ten") or ""]
                meta["ts"] = float(ev.get("created_at") or time.time())
                try:
                    pol = self.policy.prepare(text, meta)
                except Exception as e:      # noqa: BLE001 - bộ phán xử hỏng thì giữ luật cũ, không được nuốt tin
                    pol = None
                    print(f"[zalo-personal bot {self.conn_id}] bộ phán xử lỗi: {type(e).__name__}: {e}", file=sys.stderr)
                duoc_goi = duoc_goi or bool(meta.get("mentioned"))
        if nhom and not vao_nhom and not is_reaction:
            # Files in a group (0.336.0, see `zc.remember_bare_file`): a file nobody addressed to the bot waits for its
            # sender's next call; a call that quotes a file, or comes right after the sender's bare file, gets it.
            nguoi = str(ev.get("sender_id") or "")
            if chi_file and files and not duoc_goi and self._che_do_nhom() != "always":
                zc.remember_bare_file(self.conn_id, thread, nguoi, files[0], float(ev.get("created_at") or 0))
            elif (duoc_goi and not files and nguoi and ev.get("sender_type") == "customer" and self.precheck_fn
                  and str(ev.get("account_id") or "") == self.conn_id):
                files = zc.quoted_file(self.conn_id, thread, md0) or zc.take_bare_files(self.conn_id, thread, nguoi)
        try:
            if self.precheck_fn:
                r = self.precheck_fn(text, meta)
                if asyncio.iscoroutine(r):
                    r = await r
                if r is not None:           # {} = im, {"reply": ...} = một câu cố định
                    cau = str((r or {}).get("reply") or "").strip()
                    if cau and not nhom:
                        await self._gui(thread, cau, "private")
                    return
            if chi_file and nhom and not duoc_goi and self._che_do_nhom() != "always":
                return  # file thả vào nhóm mà không ai gọi bot: không tải, không đưa qua bộ phán xử
            if nhom and not duoc_goi and self._che_do_nhom() == "auto":
                if pol and pol.get("mode") == "on":
                    # Bộ phán xử thay cửa từ khoá: tin hiển nhiên không đáng đã được ghi vết và bỏ ở `prepare`.
                    if pol.get("action") == "drop":
                        return
                elif is_reaction or not chatbot_tu_dong.nhin_nhu_cau_hoi(text)[0]:
                    # Without the judge, "auto" only answers what looks like a question; a reaction never is one.
                    return
                # Chờ TRƯỚC khi cầm khoá cuộc chat: khoá là của các lượt được tag, đừng bắt chúng
                # xếp hàng sau một lượt đang ngủ.
                await asyncio.sleep(zc.NHUONG_GIAY)
                if zc.chu_vua_nhan_tay(self.conn_id, thread):
                    return
                if zc._BOTS.get(self.conn_id) is not self:
                    return      # bot bị tắt lúc đang chờ: nút Tắt phải có tác dụng ngay
            khoa = self._khoa.setdefault(thread, asyncio.Lock())
            async with khoa:
                da_tai = []
                chu_khach = text        # chữ của khách trong lượt này, trước khi gắn kết quả đọc file
                if files:
                    text, da_tai, dung = await self._tai_file(files, text, meta, thread, chi_file)
                    if not dung:
                        return
                # Câu trả lời đã cũ (0.172.0, `zc.bo_do_gui`): lượt chat riêng này tới sau một lượt bị bỏ vì khách nhắn thêm.
                cu = {}
                if not nhom and md0.get("seq_cuoi") is not None:
                    meta["seq_cuoi"] = int(md0["seq_cuoi"])
                    cu = zc.lay_bo_do(self.conn_id, thread)
                    meta["bo_do_n"] = int(cu.get("n") or 0)
                    if cu:
                        meta["ghi_chu_dau"] = ("[Ghi chú của Javis, không phải lời khách: câu trả lời trước của bạn CHƯA được gửi "
                                               "vì khách nhắn thêm trong lúc bạn soạn. Các tin khách chưa được đáp, theo thứ tự: "
                                               + " / ".join(cu["texts"]) + ". Hãy trả lời MỘT lần cho các tin này cùng tin mới "
                                               "bên dưới, đừng hỏi lại điều khách đã nói. Việc lượt trước đã làm bằng công cụ (ghi file, gửi tin, "
                                               "đặt lịch) là ĐÃ xong, đừng làm lại.]")
                # "Đang soạn tin" while the reply is written (0.413.0), private chats only: in a group most turns end
                # in silence by design, and an indicator followed by nothing reads as a person who changed their mind.
                go = None if nhom else asyncio.create_task(keep_typing(self.conn_id, thread, loai))
                try:
                    out = await self.answer_fn(text, meta, None)
                except BaseException:
                    for f in da_tai:
                        f.unlink(missing_ok=True)
                    if cu:
                        zc.bo_do_gui(self.conn_id, thread, cu["texts"], int(cu.get("n") or 0))
                    raise
                finally:
                    if go is not None:
                        go.cancel()
                anh = []
                if isinstance(out, dict):
                    if out.get("khach_nhan_them"):
                        # Soạn xong mà khách đã nhắn thêm: không gửi câu cũ, giữ chữ khách cho lượt kế tiếp (đang chờ khoá).
                        for f in da_tai:
                            f.unlink(missing_ok=True)
                        zc.bo_do_gui(self.conn_id, thread, list(cu.get("texts") or []) + [chu_khach], int(cu.get("n") or 0) + 1)
                        return
                    if out.get("reaction") and zc._BOTS.get(self.conn_id) is self:
                        await self._react(thread, loai, meta, str(out["reaction"]))
                    if out.get("im_lang"):
                        return
                    cau = str(out.get("text") or "").strip()
                    # 0.84.3: images the Agent asked to send, already checked by `bot_images.pick`.
                    anh = [str((f.get("path") if isinstance(f, dict) else f) or "") for f in (out.get("files") or [])]
                    anh = [x for x in anh if x]
                else:
                    cau = str(out or "").strip()
                if (cau or anh) and zc._BOTS.get(self.conn_id) is self:
                    if cau:
                        await self._gui(thread, cau, loai, meta)
                    if anh:
                        await self._gui_anh(thread, anh, loai)
                    if cau and nhom and self.policy is not None:
                        self.policy.replied(meta, cau)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"[:300]
            print(f"[zalo-personal bot {self.conn_id}] lượt hỏng: {self.last_error}",
                  file=sys.stderr)

    async def _react(self, thread: str, chat_type: str, meta: dict, name: str) -> None:
        """Put the reaction the judge or the Agent chose on the customer's message (0.334.0). No target (a turn made
        only of reactions) or an unknown name: nothing. A failure only shows on the bot card, the turn goes on."""
        import bot_reaction
        import zalo_personal_channel as zc
        target = str((meta or {}).get("react_to") or "")
        if not target or name not in bot_reaction.NAMES:
            return
        bot_name = str(((self.cfg_fn() if self.cfg_fn else {}) or {}).get("name") or "")
        # Remembered BEFORE sending: the echo may reach the read loop in the very next round.
        zc.remember_bot_reaction(self.conn_id, thread, target, name, bot_name)
        ok, err = await send_reaction({"id": self.conn_id}, thread, target, name, chat_type,
                                      str((meta or {}).get("react_to_cli") or ""))
        if not ok:
            self.last_error = localefmt.chu(f"Thả cảm xúc Zalo lỗi: {err}", f"Zalo reaction failed: {err}")[:300]
            print(f"[zalo-personal bot {self.conn_id}] {self.last_error}", file=sys.stderr)

    async def _gui(self, thread: str, cau: str, chat_type: str = "private", meta: Optional[dict] = None):
        import zalo_personal_channel as zc
        # Nhớ TRƯỚC khi gửi: tiếng vọng có thể về vòng đọc ngay trong nhịp kế tiếp.
        zc.ghi_da_gui(self.conn_id, thread, cau)
        # Trong nhóm, bot trả lời ai thì tag đúng người đó (0.65.6). Chat riêng không cần tag.
        tag = {"uid": (meta or {}).get("user_id"), "name": (meta or {}).get("user_name")} if chat_type == "group" else None
        ok, loi = await gui({"id": self.conn_id}, thread, cau, chat_type, tag)
        if not ok:
            self.last_error = localefmt.chu(f"Gửi Zalo lỗi: {loi}", f"Zalo send failed: {loi}")[:300]
            print(f"[zalo-personal bot {self.conn_id}] {self.last_error}", file=sys.stderr)
            self._ghi_loi_gui(thread, cau, loi, chat_type)

    async def _gui_anh(self, thread: str, anh: list, chat_type: str = "private"):
        import zalo_personal_channel as zc
        # Remember BEFORE sending, like _gui: each image comes back in the read loop as the account's own message.
        zc.ghi_da_gui_anh(self.conn_id, thread, len(anh))
        ok, loi = await gui_anh({"id": self.conn_id}, thread, anh, chat_type)
        if not ok:
            self.last_error = localefmt.chu(f"Gửi ảnh Zalo lỗi: {loi}", f"Zalo image send failed: {loi}")[:300]
            print(f"[zalo-personal bot {self.conn_id}] {self.last_error}", file=sys.stderr)
            self._ghi_loi_gui(thread, localefmt.chu(f"({len(anh)} ảnh)", f"({len(anh)} image(s))"), loi, chat_type)

    def _ghi_loi_gui(self, thread: str, cau: str, loi: str, chat_type: str):
        """Để lại dấu ở nhật ký bot khi gửi lỗi.

        Câu trả lời đã vào Hộp thư TRƯỚC khi gửi (xem `chatbot_runtime._answer`), còn `last_error`
        bị vòng giám sát xoá sau vài giây. Không có dòng này thì "bot đã trả lời" trong Hộp thư và
        "khách không nhận được gì" nhìn giống hệt nhau, và không chỗ nào cho biết vì sao.
        """
        try:
            import chatbot_log
            cfg = self.cfg_fn() if self.cfg_fn else {}
            bid = str((cfg or {}).get("id") or "")
            if not bid:
                return
            chatbot_log.ghi(bid, {
                "chat_id": thread, "chat_type": chat_type, "user_name": "",
                "hoi": "(bot gửi tin vào " + ("nhóm" if chat_type == "group" else "chat riêng") + ")",
                "dap": cau,
                "loi": f"Gửi Zalo lỗi: {loi}. Câu định gửi: {cau[:200]}",
                "muc_quyen": (cfg or {}).get("muc_quyen") or "suggest",
            })
        except Exception as e:
            print(f"[zalo-personal bot {self.conn_id}] ghi nhật ký lỗi gửi: {e}", file=sys.stderr)
