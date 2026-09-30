"""Plugin bundled: tag ĐÚNG người trong nhóm Zalo, ghi chú nhóm, nhắc hẹn và poll.

Vì sao có plugin này. Chủ dự án (2026-09-30): trong nhóm Zalo Javis không tag được đúng tên người đang nói chuyện ("@minhquy"), và
muốn Javis tạo được ghi chú, nhắc hẹn, poll. MCP chuẩn của `zalo-agent-cli` chỉ có bảy tool và `zalo_send_message` chỉ nhận chữ,
nhưng chính CLI đó (bản 1.6.2, bản mới nhất trên npm) đã có `msg send --mention`, `group note-create`, `reminder create`,
`poll create`. Nên làm như plugin `zalo-image`: gọi lại đúng CLI đó bằng phiên đã đăng nhập (xem `server/zalo_cli.py`).

Điều khó nhất là TAG ĐÚNG NGƯỜI. Zalo tag bằng `uid` chứ không bằng tên, mà người dùng chỉ nói tên ("tag anh Quý"). Nên:
  1. tìm tên trong những người ĐÃ NHẮN trong nhóm này (Hộp thư của Javis có sẵn, tức thì, không tốn mạng);
  2. không thấy thì hỏi Zalo danh sách thành viên của nhóm;
  3. chuẩn hoá bỏ dấu, hoa thường, khoảng trắng và dấu @ khi so ("minhquy" khớp "Minh Quý");
  4. TRÙNG TÊN HOẶC KHÔNG THẤY THÌ HỎI LẠI kèm danh sách ứng viên, không đoán: tag nhầm người thì không rút lại được;
  5. vị trí chữ Zalo cần là chỉ số theo đơn vị UTF-16 (JavaScript), không phải số ký tự Python: emoji chiếm 2 đơn vị. Tính sai
     là vệt tô xanh lệch sang chữ bên cạnh.

Cả năm tool đều là hành động THẬT, hiện ra cho cả nhóm và không thu hồi được, nên `min_mode: full` (cùng hạng `zalo_send_message`),
trừ `zalo_group_members` chỉ đọc.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from typing import Any, List, Optional, Tuple

import zalo_cli

MAX_MENTIONS = 20
MAX_TEXT = 2000               # bằng trần một tin nhắn của Hộp thư
MAX_TITLE = 500
MAX_QUESTION = 200
MAX_OPTION = 100
POLL_OPTIONS = (2, 10)
REPEATS = ("none", "daily", "weekly", "monthly")
MEMBER_INFO_CHUNK = 40        # số id hỏi tên mỗi lượt gọi CLI
MEMBER_INFO_MAX_CHUNKS = 3    # mỗi lượt gọi tốn vài giây, nên có trần: nhóm rất lớn thì dựa vào người đã nhắn
ALL_UID = "-1"                # Zalo dùng uid -1 cho @All

_UID_RE = re.compile(r"^\d{4,25}$")


# ============================================================
# Chuẩn hoá tên
# ============================================================
def norm(s: Any) -> str:
    """Bỏ dấu, hoa thường, chỉ giữ chữ và số: "@Minh Quý" -> "minhquy"."""
    t = unicodedata.normalize("NFD", str(s or ""))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").replace("đ", "d").replace("Đ", "d")
    return re.sub(r"[^0-9a-z]+", "", t.lower())


def clean_uid(x: Any) -> str:
    """Zalo trả id khi thì "123", khi thì "123_0" (kèm số phiên bản). Lấy phần id."""
    s = str(x or "").strip()
    return s.split("_", 1)[0] if re.match(r"^\d+_\d+$", s) else s


def utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


# ============================================================
# Danh sách thành viên
# ============================================================
def local_members(conn: dict, thread_id: str) -> List[dict]:
    """Người đã nhắn trong nhóm này, từ Hộp thư của Javis (không tốn mạng)."""
    try:
        import conversations
        rows = conversations.group_speakers(f"zalo_personal:{conn['id']}", thread_id)
    except Exception:      # noqa: BLE001 - kho hỏng thì rơi về danh sách của Zalo
        return []
    return [{"uid": clean_uid(r["uid"]), "name": r["name"], "source": "hop_thu"} for r in rows]


def _group_entry(data: Any, thread_id: str) -> dict:
    grid = (data or {}).get("gridInfoMap") if isinstance(data, dict) else None
    if not isinstance(grid, dict) or not grid:
        return {}
    return grid.get(thread_id) or next(iter(grid.values())) or {}


async def remote_members(conn: dict, thread_id: str) -> Tuple[List[dict], str]:
    """Thành viên nhóm theo Zalo: `group info` (có `currentMems` kèm tên), rồi `group members-info` cho id còn thiếu tên."""
    ok, data, err = await zalo_cli.run_cli(conn, ["group", "info"], [thread_id])
    if not ok:
        return [], err
    info = _group_entry(data, thread_id)
    out, have = [], set()
    for m in (info.get("currentMems") or []):
        if isinstance(m, dict) and m.get("id"):
            uid = clean_uid(m["id"])
            name = str(m.get("dName") or m.get("zaloName") or "").strip()
            if uid and uid not in have:
                have.add(uid)
                out.append({"uid": uid, "name": name, "source": "zalo"})
    ids = [clean_uid(x) for x in (info.get("memberIds") or info.get("memVerList") or [])]
    missing = [u for u in dict.fromkeys(ids) if u and u not in have]
    nameless = [m for m in out if not m["name"]]
    need = [m["uid"] for m in nameless] + missing
    for i in range(0, min(len(need), MEMBER_INFO_CHUNK * MEMBER_INFO_MAX_CHUNKS), MEMBER_INFO_CHUNK):
        ok2, d2, _err2 = await zalo_cli.run_cli(conn, ["group", "members-info"], need[i:i + MEMBER_INFO_CHUNK])
        profiles = (d2 or {}).get("profiles") if isinstance(d2, dict) else None
        if not ok2 or not isinstance(profiles, dict):
            break
        for uid, p in profiles.items():
            uid = clean_uid(uid)
            name = str((p or {}).get("displayName") or (p or {}).get("zaloName") or "").strip()
            hit = next((m for m in out if m["uid"] == uid), None)
            if hit:
                hit["name"] = hit["name"] or name
            else:
                out.append({"uid": uid, "name": name, "source": "zalo"})
    for uid in missing:
        if not any(m["uid"] == uid for m in out):
            out.append({"uid": uid, "name": "", "source": "zalo"})
    return out, ""


def merge_members(local: List[dict], remote: List[dict]) -> List[dict]:
    """Gộp theo uid. Tên ở Hộp thư ưu tiên (đó là tên người ta đang dùng khi nhắn), Zalo bù chỗ thiếu."""
    by = {}
    for m in remote:
        by[m["uid"]] = dict(m)
    for m in local:
        cur = by.get(m["uid"])
        if cur:
            cur["name"] = m["name"] or cur["name"]
            cur["source"] = "hop_thu+zalo"
        else:
            by[m["uid"]] = dict(m)
    return list(by.values())


# ============================================================
# Tìm người để tag
# ============================================================
def find_members(query: str, members: List[dict]) -> List[dict]:
    """Thành viên khớp `query`: khớp CHÍNH XÁC (sau chuẩn hoá) thì chỉ trả những người đó; không có thì trả người có tên CHỨA
    chuỗi. Rỗng = không thấy."""
    q = norm(query)
    if not q:
        return []
    named = [m for m in members if m.get("name")]
    exact = [m for m in named if norm(m["name"]) == q]
    if exact:
        return exact
    return [m for m in named if q in norm(m["name"])]


def _candidates(members: List[dict], limit: int = 8) -> str:
    named = [m for m in members if m.get("name")][:limit]
    return "; ".join(f"{m['name']} (uid {m['uid']})" for m in named) or "(chưa biết tên ai trong nhóm)"


def _request_items(mentions: Any) -> List[dict]:
    """`mentions` từ model có thể là danh sách chuỗi ("Minh Quý", "@minhquy", "123456") hoặc danh sách {name, uid}."""
    out = []
    for m in (mentions if isinstance(mentions, list) else []):
        if isinstance(m, dict):
            name = str(m.get("name") or m.get("display") or "").strip().lstrip("@")
            uid = clean_uid(m.get("uid") or m.get("id") or "")
        else:
            name, uid = str(m or "").strip().lstrip("@"), ""
            if _UID_RE.match(name):
                name, uid = "", name
        if uid and not _UID_RE.match(uid):
            uid = ""
        if name or uid:
            out.append({"name": name, "uid": uid})
    return out


async def resolve_targets(conn: dict, thread_id: str, items: List[dict]) -> Tuple[List[dict], str]:
    """Đổi mỗi yêu cầu tag thành `{uid, display, typed}` hoặc trả lý do (câu hỏi lại) nếu không chắc chắn."""
    members = local_members(conn, thread_id)
    remote_loaded = False
    targets: List[dict] = []
    seen_uid = set()
    for it in items:
        uid, typed = it["uid"], it["name"]
        display = ""
        if uid:
            hit = next((m for m in members if m["uid"] == uid), None)
            display = (hit or {}).get("name") or typed
        else:
            hits = find_members(typed, members)
            if not hits and not remote_loaded:
                remote, err = await remote_members(conn, thread_id)
                remote_loaded = True
                members = merge_members(members, remote)
                if err and not remote:
                    return [], (f"không tìm thấy '{typed}' trong những người đã nhắn ở nhóm này và cũng không lấy được danh "
                                f"sách thành viên từ Zalo ({err}). Đưa uid của người đó vào mentions, hoặc thử lại.")
                hits = find_members(typed, members)
            if not hits:
                return [], (f"không thấy ai tên '{typed}' trong nhóm. Một số thành viên: {_candidates(members)}. "
                            "Gọi zalo_group_members để xem đủ, rồi nêu lại tên đúng hoặc uid.")
            if len(hits) > 1:
                return [], (f"'{typed}' khớp {len(hits)} người: {_candidates(hits)}. Hỏi lại người dùng là ai, rồi nêu tên đầy đủ "
                            "hoặc uid. KHÔNG đoán, tag nhầm người thì không rút lại được.")
            uid, display = hits[0]["uid"], hits[0]["name"]
        if uid in seen_uid:
            continue
        seen_uid.add(uid)
        typed_forms = [t for t in dict.fromkeys([typed, display]) if t]
        targets.append({"uid": uid, "display": display or typed or uid, "typed": typed_forms})
    return targets, ""


# ============================================================
# Dựng tin có tag
# ============================================================
def build_mention_message(text: str, targets: List[dict]) -> Tuple[str, List[dict]]:
    """Dựng `(nội dung cuối, [{uid, pos, len, display}])`.

    Mỗi người được tag ứng với một đoạn "@Tên" trong `text` (tìm không phân biệt hoa thường theo cả tên người dùng gõ lẫn tên thật);
    đoạn đó được thay bằng "@<tên thật>". Người nào không có đoạn "@..." nào thì được chèn "@<tên thật> " ở ĐẦU tin. `pos` và `len`
    tính theo đơn vị UTF-16 trên chuỗi CUỐI CÙNG, đúng thứ Zalo đọc."""
    spans: List[Tuple[int, int, dict]] = []
    missing: List[dict] = []
    for t in targets:
        found = None
        for form in t["typed"]:
            # `(?!\w)`: "@Quý" không được ăn vào "@Quýnh" (tag nhầm chữ đầu của một tên dài hơn).
            for m in re.finditer(re.escape("@" + form) + r"(?!\w)", text, flags=re.IGNORECASE):
                s, e = m.span()
                if not any(s < e2 and e > s2 for s2, e2, _ in spans):
                    found = (s, e)
                    break
            if found:
                break
        if found:
            spans.append((found[0], found[1], t))
        else:
            missing.append(t)
    spans.sort(key=lambda x: x[0])

    out = ""
    mentions: List[dict] = []
    for t in missing:
        token = "@" + t["display"]
        mentions.append({"uid": t["uid"], "pos": utf16_len(out), "len": utf16_len(token), "display": t["display"]})
        out += token + " "
    cursor = 0
    for s, e, t in spans:
        out += text[cursor:s]
        token = "@" + t["display"]
        mentions.append({"uid": t["uid"], "pos": utf16_len(out), "len": utf16_len(token), "display": t["display"]})
        out += token
        cursor = e
    out += text[cursor:]
    return out, mentions


# ============================================================
# Tiện ích chung cho các tool
# ============================================================
def _ready(args: dict) -> Tuple[Optional[dict], str]:
    """Kiểm điều kiện dùng được và chọn kết nối. Trả `(kết nối, "")` hoặc `(None, "ERROR: ...")`."""
    why = zalo_cli.check()
    if why:
        return None, "ERROR: " + why
    conn, why = zalo_cli.pick_connection(zalo_cli.connections(), str(args.get("connection_id") or ""))
    if not conn:
        return None, "ERROR: " + why
    return conn, ""


def _need(args: dict, key: str) -> str:
    return str(args.get(key) or "").strip()


def _bool(v: Any) -> bool:
    return v is True or str(v).strip().lower() in ("1", "true", "yes", "co", "có")


def _first_id(data: Any, *keys: str) -> str:
    """Lấy id vừa tạo từ kết quả CLI (mỗi lệnh đặt tên khác nhau: poll_id, reminderId, topicId...)."""
    if isinstance(data, dict):
        for k in keys:
            if data.get(k) not in (None, ""):
                return str(data[k])
        for v in data.values():
            if isinstance(v, dict):
                got = _first_id(v, *keys)
                if got:
                    return got
    return ""


def _short(data: Any, limit: int = 600) -> Any:
    try:
        s = json.dumps(data, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(data)[:limit]
    return data if len(s) <= limit else s[:limit] + "..."


def _done(**kw) -> str:
    return json.dumps({"ok": True, **kw}, ensure_ascii=False)


def _fail(what: str, err: str, hint: str = "") -> str:
    """Câu lỗi của một lệnh GHI. Hết giờ là kết cục KHÔNG RÕ (CLI có thể đã tạo xong rồi mới bị giết), nên dặn xem lại nhóm trước
    khi thử tiếp: gửi lại mù thì ra hai poll, hai ghi chú hoặc hai tin dưới tên chủ."""
    if zalo_cli.is_timeout(err):
        return (f"ERROR: {what} quá giờ và KHÔNG rõ đã thành công chưa ({err}). Mở nhóm Zalo xem đã có chưa "
                "rồi mới thử lại, kẻo bị tạo hai lần.")
    return f"ERROR: {what} không được. {err}" + (f" {hint}" if hint else "")


# ============================================================
# Tool 1: danh sách thành viên
# ============================================================
async def _members(args, ctx):
    args = args or {}
    conn, why = _ready(args)
    if not conn:
        return why
    thread_id = _need(args, "thread_id")
    if not thread_id:
        return "ERROR: thiếu thread_id. Tìm bằng zalo_search_threads hoặc zalo_list_threads."
    local = local_members(conn, thread_id)
    remote, err = await remote_members(conn, thread_id)
    members = merge_members(local, remote)
    query = str(args.get("query") or "").strip()
    if query:
        members = find_members(query, members)
    if not members and err and not local:
        return f"ERROR: không lấy được danh sách thành viên ({err})"
    members.sort(key=lambda m: (not m.get("name"), norm(m.get("name"))))
    return _done(thread_id=thread_id, account=conn["label"], count=len(members), query=query,
                 members=[{"uid": m["uid"], "name": m["name"]} for m in members[:200]],
                 note=("Danh sách của Zalo chưa lấy được, đây chỉ là những người đã nhắn ở nhóm này: " + err) if err else "")


# ============================================================
# Tool 2: gửi tin có tag
# ============================================================
async def _send_mention(args, ctx):
    args = args or {}
    conn, why = _ready(args)
    if not conn:
        return why
    thread_id = _need(args, "thread_id")
    if not thread_id:
        return "ERROR: thiếu thread_id (id nhóm Zalo, từ zalo_search_threads). Tag chỉ dùng được trong NHÓM."
    text = str(args.get("text") or "").strip()
    if not text:
        return "ERROR: thiếu text (nội dung tin). Viết @Tên ở chỗ muốn tag, ví dụ \"@Minh Quý họp lúc 9h nhé\"."
    if len(text) > MAX_TEXT:
        return f"ERROR: tin dài quá {MAX_TEXT} ký tự."
    items = _request_items(args.get("mentions"))
    tag_all = _bool(args.get("mention_all"))
    if not items and not tag_all:
        return "ERROR: thiếu mentions (danh sách người cần tag: tên hoặc uid) hoặc mention_all=true để tag cả nhóm."
    if len(items) > MAX_MENTIONS:
        return f"ERROR: tag tối đa {MAX_MENTIONS} người một tin."

    targets, why = await resolve_targets(conn, thread_id, items)
    if why:
        return "ERROR: " + why
    if tag_all:
        targets.append({"uid": ALL_UID, "display": "All", "typed": ["All"]})
    final_text, mentions = build_mention_message(text, targets)
    if len(final_text) > MAX_TEXT + 200:
        return f"ERROR: tin sau khi chèn tên dài quá {MAX_TEXT} ký tự."
    specs = [f"{m['pos']}:{m['uid']}:{m['len']}" for m in mentions]
    ok, data, err = await zalo_cli.run_cli(conn, ["msg", "send"], [thread_id, final_text],
                                           ["-t", "1", "--mention", *specs])
    if not ok:
        return _fail("gửi tin", err)
    return _done(thread_id=thread_id, account=conn["label"], text=final_text,
                 mentions=[{"uid": m["uid"], "name": m["display"], "pos": m["pos"], "len": m["len"]} for m in mentions],
                 message_id=_first_id(data, "msgId", "message_id"))


# ============================================================
# Tool 3: ghi chú nhóm
# ============================================================
async def _create_note(args, ctx):
    args = args or {}
    conn, why = _ready(args)
    if not conn:
        return why
    group_id = _need(args, "group_id")
    title = str(args.get("title") or "").strip()
    if not group_id:
        return "ERROR: thiếu group_id (id nhóm Zalo, từ zalo_search_threads). Ghi chú chỉ có ở NHÓM."
    if not title:
        return "ERROR: thiếu title (nội dung ghi chú)."
    if len(title) > MAX_TITLE:
        return f"ERROR: ghi chú dài quá {MAX_TITLE} ký tự."
    ok, data, err = await zalo_cli.run_cli(conn, ["group", "note-create"], [group_id, title],
                                           ["--pin"] if _bool(args.get("pin")) else [])
    if not ok:
        return _fail("tạo ghi chú", err, "(nhóm có thể đã khoá quyền tạo ghi chú của thành viên).")
    return _done(group_id=group_id, account=conn["label"], title=title, pinned=_bool(args.get("pin")),
                 note_id=_first_id(data, "topicId", "noteId", "id"), result=_short(data))


# ============================================================
# Tool 4: nhắc hẹn
# ============================================================
def machine_local_time(value: str) -> Tuple[Optional[str], str]:
    """Đổi giờ người dùng nói ("YYYY-MM-DD HH:mm", theo múi giờ CỦA JAVIS) sang chuỗi giờ theo đồng hồ của MÁY chạy CLI.

    CLI đọc `--time` bằng `new Date(y, m, d, h, mi)` tức là theo múi giờ hệ thống của máy. VPS thường ở UTC còn người dùng ở
    Việt Nam, nên "9 giờ sáng mai" gửi nguyên chữ sẽ thành 16 giờ. Trả `(chuỗi, "")` hoặc `(None, lý do)`."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})$", str(value or "").strip())
    if not m:
        return None, 'time phải có dạng "YYYY-MM-DD HH:mm" (ví dụ "2026-10-02 09:00"), theo giờ của người dùng.'
    try:
        naive = datetime(*[int(x) for x in m.groups()])
    except ValueError:
        return None, f"time '{value}' không phải ngày giờ có thật."
    try:
        import localefmt
        tz = localefmt.now().tzinfo
    except Exception:      # noqa: BLE001 - không biết múi giờ Javis thì coi như trùng đồng hồ máy
        tz = None
    aware = naive.replace(tzinfo=tz) if tz else naive.astimezone()
    now = datetime.now(aware.tzinfo)
    if aware <= now:
        return None, f"time {value} đã qua (bây giờ là {now.strftime('%Y-%m-%d %H:%M')}). Nhắc hẹn phải ở tương lai."
    return aware.astimezone().strftime("%Y-%m-%d %H:%M"), ""


async def _create_reminder(args, ctx):
    args = args or {}
    conn, why = _ready(args)
    if not conn:
        return why
    thread_id = _need(args, "thread_id")
    title = str(args.get("title") or "").strip()
    if not thread_id:
        return "ERROR: thiếu thread_id (id nhóm hoặc người, từ zalo_search_threads)."
    if not title:
        return "ERROR: thiếu title (nội dung nhắc)."
    if len(title) > MAX_TITLE:
        return f"ERROR: nội dung nhắc dài quá {MAX_TITLE} ký tự."
    when, why = machine_local_time(str(args.get("time") or ""))
    if not when:
        return "ERROR: " + why
    repeat = str(args.get("repeat") or "none").strip().lower()
    if repeat not in REPEATS:
        return f"ERROR: repeat phải là một trong {', '.join(REPEATS)}."
    try:
        ttype = int(args.get("thread_type", 1))
    except (TypeError, ValueError):
        ttype = 1
    if ttype not in (0, 1):
        ttype = 1
    options = ["-t", str(ttype), "--time", when, "--repeat", repeat]
    emoji = str(args.get("emoji") or "").strip()
    if emoji:
        options += ["--emoji", emoji[:8]]
    ok, data, err = await zalo_cli.run_cli(conn, ["reminder", "create"], [thread_id, title], options)
    if not ok:
        return _fail("tạo nhắc hẹn", err)
    return _done(thread_id=thread_id, thread_type=ttype, account=conn["label"], title=title,
                 time=str(args.get("time")).strip(), repeat=repeat,
                 reminder_id=_first_id(data, "reminderId", "id"), result=_short(data))


# ============================================================
# Tool 5: poll
# ============================================================
async def _create_poll(args, ctx):
    args = args or {}
    conn, why = _ready(args)
    if not conn:
        return why
    group_id = _need(args, "group_id")
    question = str(args.get("question") or "").strip()
    if not group_id:
        return "ERROR: thiếu group_id (id nhóm Zalo, từ zalo_search_threads). Poll chỉ có ở NHÓM."
    if not question:
        return "ERROR: thiếu question (câu hỏi của poll)."
    if len(question) > MAX_QUESTION:
        return f"ERROR: câu hỏi dài quá {MAX_QUESTION} ký tự."
    raw = args.get("options")
    options = [str(o or "").strip() for o in (raw if isinstance(raw, list) else [])]
    options = list(dict.fromkeys(o for o in options if o))
    lo, hi = POLL_OPTIONS
    if not lo <= len(options) <= hi:
        return f"ERROR: poll cần từ {lo} đến {hi} lựa chọn khác nhau, đang có {len(options)}."
    if any(len(o) > MAX_OPTION for o in options):
        return f"ERROR: mỗi lựa chọn dài tối đa {MAX_OPTION} ký tự."
    flags: List[str] = []
    if _bool(args.get("multi")):
        flags.append("--multi")
    if _bool(args.get("allow_add_options")):
        flags.append("--add-options")
    if _bool(args.get("anonymous")):
        flags.append("--anonymous")
    if _bool(args.get("hide_results_until_voted")):
        flags.append("--hide-preview")
    expire = args.get("expire_minutes")
    if expire not in (None, "", 0):
        try:
            mins = int(expire)
        except (TypeError, ValueError):
            return "ERROR: expire_minutes phải là số phút."
        if not 1 <= mins <= 60 * 24 * 30:
            return "ERROR: expire_minutes từ 1 đến 43200 (30 ngày)."
        flags += ["--expire", str(mins)]
    ok, data, err = await zalo_cli.run_cli(conn, ["poll", "create"], [group_id, question, *options], flags)
    if not ok:
        return _fail("tạo poll", err, "(nhóm có thể đã khoá quyền tạo poll của thành viên).")
    return _done(group_id=group_id, account=conn["label"], question=question, options=options,
                 poll_id=_first_id(data, "poll_id", "pollId", "id"), result=_short(data))


# ============================================================
# Đăng ký
# ============================================================
_CONN = {"connection_id": {"type": "string", "description": "id kết nối Zalo, chỉ cần khi đã đấu nhiều tài khoản"}}


def register(ctx):
    ctx.register_tool(
        name="zalo_group_members",
        description=(
            "Liệt kê thành viên một NHÓM Zalo (uid kèm tên) để biết tag ai, hoặc tra một người theo tên (query). Gộp hai nguồn: "
            "người đã nhắn trong nhóm (Hộp thư của Javis) và danh sách thành viên của Zalo. Chỉ đọc. Tham số: thread_id (id nhóm, "
            "từ zalo_search_threads), query (tuỳ chọn, tên cần tìm; không phân biệt hoa thường hay dấu)."
        ),
        handler=_members, min_mode="readonly", check_fn=zalo_cli.check,
        schema={"type": "object", "properties": {
            "thread_id": {"type": "string", "description": "id nhóm Zalo (từ zalo_search_threads/zalo_list_threads)"},
            "query": {"type": "string", "description": "tên cần tìm (tuỳ chọn)"}, **_CONN}, "required": ["thread_id"]},
    )
    ctx.register_tool(
        name="zalo_send_mention",
        description=(
            "Gửi tin vào NHÓM Zalo và TAG ĐÚNG NGƯỜI (người được tag nhận thông báo, tên tô xanh). Dùng thay zalo_send_message mỗi khi "
            "cần @ ai đó. Chỉ cần nói TÊN, tool tự tìm uid thật; trùng tên hoặc không thấy thì báo lỗi kèm ứng viên để bạn HỎI LẠI "
            "người dùng, đừng đoán. Tham số: thread_id (id nhóm), text (nội dung; viết @Tên ở chỗ muốn tag, không viết thì tên được "
            "chèn ở đầu tin), mentions (danh sách tên hoặc uid, hoặc {name, uid}), mention_all=true để @All (chỉ khi người dùng "
            "yêu cầu rõ)."
        ),
        handler=_send_mention, min_mode="full", check_fn=zalo_cli.check,
        schema={"type": "object", "properties": {
            "thread_id": {"type": "string", "description": "id nhóm Zalo"},
            "text": {"type": "string", "description": "nội dung tin, có thể chứa @Tên"},
            "mentions": {"type": "array", "items": {"anyOf": [
                {"type": "string"},
                {"type": "object", "properties": {"name": {"type": "string"}, "uid": {"type": "string"}}}]},
                "description": "người cần tag: tên (\"Minh Quý\", \"@minhquy\"), uid, hoặc {name, uid}"},
            "mention_all": {"type": "boolean", "description": "tag cả nhóm (@All). Chỉ khi được yêu cầu rõ."}, **_CONN},
            "required": ["thread_id", "text"]},
    )
    ctx.register_tool(
        name="zalo_create_note",
        description=(
            "Tạo GHI CHÚ trong một nhóm Zalo (hiện cho cả nhóm, ghim được). Tham số: group_id (id nhóm), title (nội dung ghi chú), "
            "pin (ghim lên đầu)."
        ),
        handler=_create_note, min_mode="full", check_fn=zalo_cli.check,
        schema={"type": "object", "properties": {
            "group_id": {"type": "string", "description": "id nhóm Zalo"},
            "title": {"type": "string", "description": "nội dung ghi chú"},
            "pin": {"type": "boolean", "description": "ghim ghi chú"}, **_CONN}, "required": ["group_id", "title"]},
    )
    ctx.register_tool(
        name="zalo_create_reminder",
        description=(
            "Tạo NHẮC HẸN ngay TRONG Zalo, hiện cho cả nhóm (hoặc người kia trong chat riêng) và họ bấm nhận/từ chối được. KHÁC nhắc "
            "hẹn riêng của Javis (javis_schedule chỉ nhắc chủ qua Telegram). Tham số: thread_id, title, time (\"YYYY-MM-DD HH:mm\" theo "
            "giờ của người dùng, phải ở tương lai), repeat (none, daily, weekly, monthly), emoji, thread_type (1=nhóm mặc định, "
            "0=chat riêng)."
        ),
        handler=_create_reminder, min_mode="full", check_fn=zalo_cli.check,
        schema={"type": "object", "properties": {
            "thread_id": {"type": "string", "description": "id nhóm hoặc người"},
            "title": {"type": "string", "description": "nội dung nhắc"},
            "time": {"type": "string", "description": "YYYY-MM-DD HH:mm theo giờ của người dùng"},
            "repeat": {"type": "string", "enum": list(REPEATS)},
            "emoji": {"type": "string", "description": "biểu tượng (mặc định ⏰)"},
            "thread_type": {"type": "integer", "enum": [0, 1], "description": "1 = nhóm (mặc định), 0 = chat riêng"}, **_CONN},
            "required": ["thread_id", "title", "time"]},
    )
    ctx.register_tool(
        name="zalo_create_poll",
        description=(
            "Tạo POLL (bình chọn) trong một nhóm Zalo. Tham số: group_id, question, options (2 đến 10 lựa chọn khác nhau), multi (cho "
            "chọn nhiều), allow_add_options (thành viên thêm được lựa chọn), anonymous (ẩn người bình chọn), hide_results_until_voted, "
            "expire_minutes (tự đóng sau N phút)."
        ),
        handler=_create_poll, min_mode="full", check_fn=zalo_cli.check,
        schema={"type": "object", "properties": {
            "group_id": {"type": "string", "description": "id nhóm Zalo"},
            "question": {"type": "string", "description": "câu hỏi"},
            "options": {"type": "array", "items": {"type": "string"}, "description": "2 đến 10 lựa chọn"},
            "multi": {"type": "boolean"}, "allow_add_options": {"type": "boolean"}, "anonymous": {"type": "boolean"},
            "hide_results_until_voted": {"type": "boolean"},
            "expire_minutes": {"type": "integer", "description": "tự đóng sau N phút"}, **_CONN},
            "required": ["group_id", "question", "options"]},
    )
