"""Bundled plugin: tool `javis_mytask` - the owner's own tasks, appointments and habits from chat, on every engine.

The Tasks page has a tab "Mine" (server/my_tasks.py). Spec docs/dev/2026-10-nhiem-vu-spec.md 7, 8.4 and 11. Every
change the owner can make on the page can be asked for in chat (owner, 2026-11-05: "everything I ask Javis to edit in
the calendar must be editable"), in-process like javis-task (no HTTP route opened for it):

    add      a task, a repeat, a habit or an appointment (kind=appt: date, time, end or duration, place, reminder)
    list     today (default), the next days (scope=upcoming) or everything (scope=all), optionally filtered by name
    update   any field of one item: title, date, time, end, kind (task <-> appt), repeat, place, reminder, notes,
             tags, habit on/off, star, done/open
    delete   one item (the whole repeat when it repeats)
    skip     skip one time of a repeat (it counts as handled, never as done)
    check / uncheck   tick or untick, for a one-off or one day of a repeat / habit

Ticking is the risky part: a wrong tick makes the owner stop trusting the streak. So every op that acts on one item
only acts when the name matches ONE item; several matches return the list so the model asks back, and every tick by
this tool is stored with by="javis" so the page marks it and the owner can undo it there.

Texts returned here go to the model, not to a screen, so they stay in Vietnamese like the other tool results.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta

import my_tasks as my_tasks_mod

WD = {"cn": 0, "chu nhat": 0, "t2": 1, "thu 2": 1, "thu hai": 1, "t3": 2, "thu 3": 2, "thu ba": 2, "t4": 3, "thu 4": 3,
      "thu tu": 3, "t5": 4, "thu 5": 4, "thu nam": 4, "t6": 5, "thu 6": 5, "thu sau": 5, "t7": 6, "thu 7": 6, "thu bay": 6,
      "sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
WD_NAME = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"]
NONE_WORDS = ("", "none", "khong", "null", "bo", "xoa")
TAG_COLOR = "#3b82f6"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or "").lower().replace("đ", "d"))
    return re.sub(r"\s+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip()


def _store():
    f = my_tasks_mod.current()
    if f is None:
        return None, "ERROR: kho việc của tôi chưa sẵn sàng (máy chủ đang khởi động?). Thử lại sau vài giây."
    return f, ""


def _today(f) -> str:
    tz = f.deps.tz() if f.deps.tz else None
    return datetime.now(tz).date().isoformat()


def _has(args, key) -> bool:
    return key in args and args.get(key) is not None


def _repeat(args) -> dict | None:
    unit = _norm(args.get("repeat"))
    if unit in NONE_WORDS:
        return None
    if unit not in ("day", "week", "month", "year"):
        return None
    try:
        n = max(1, int(args.get("every") or 1))
    except (TypeError, ValueError):
        n = 1
    rep = {"unit": unit, "n": n}
    if unit == "week":
        days = []
        for part in re.split(r"[,;/]+", str(args.get("days") or "")):
            k = _norm(part)
            if k in WD:
                days.append(WD[k])
        rep["days"] = sorted(set(days))
    return rep


def _rep_text(rep: dict | None) -> str:
    if not rep:
        return "không lặp"
    n, unit = rep.get("n") or 1, rep.get("unit")
    word = {"day": "ngày", "week": "tuần", "month": "tháng", "year": "năm"}.get(unit, unit)
    s = f"mỗi {word}" if n == 1 else f"mỗi {n} {word}"
    if unit == "week" and rep.get("days"):
        s += " (" + ", ".join(WD_NAME[d] for d in rep["days"]) + ")"
    return s


def _minutes(hm: str) -> int:
    return int(hm[:2]) * 60 + int(hm[3:5])


def _hm(m: int) -> str:
    m = max(0, min(23 * 60 + 59, m))
    return f"{m // 60:02d}:{m % 60:02d}"


def _date_arg(v):
    """A date argument: YYYY-MM-DD, or a word that clears it (None). Anything else is an error (raises)."""
    s = str(v or "").strip()
    if _norm(s) in NONE_WORDS:
        return None
    if not my_tasks_mod._clean_date(s):
        raise ValueError(f"ngày '{s}' không đúng dạng YYYY-MM-DD")
    return s


def _time_arg(v) -> str:
    s = str(v or "").strip()
    if _norm(s) in NONE_WORDS:
        return ""
    if len(s) == 4 and s[1] == ":":
        s = "0" + s
    if not my_tasks_mod._clean_time(s):
        raise ValueError(f"giờ '{s}' không đúng dạng HH:MM")
    return s


def _tag_ids(f, brain: str, names) -> list:
    """Tag names -> tag ids of this brain; a name with no tag yet creates the tag."""
    data = f.load(brain)
    have = {_norm(p.get("name")): p["id"] for p in data.get("projects", []) if p.get("id")}
    out = []
    for raw in re.split(r"[,;]+", names) if isinstance(names, str) else (names or []):
        nm = str(raw or "").strip()
        if not nm:
            continue
        tid = have.get(_norm(nm))
        if not tid:
            r = f.project(brain, {"name": nm, "color": TAG_COLOR})
            if not r.get("ok"):
                continue
            tid = r["project"]["id"]
            have[_norm(nm)] = tid
        if tid not in out:
            out.append(tid)
    return out


def _tag_names(data: dict, t: dict) -> list:
    names = {p.get("id"): p.get("name") for p in data.get("projects", [])}
    return [names[x] for x in my_tasks_mod.task_tags(t) if names.get(x)]


def _kind(t: dict) -> str:
    if t.get("kind") == "appt":
        return "lịch hẹn"
    if t.get("habit") and not (t["habit"] or {}).get("off"):
        return "thói quen"
    return "việc lặp" if t.get("repeat") else "việc"


def _describe(t: dict, data: dict) -> str:
    parts = [_kind(t)]
    when = t.get("date") or "chưa hẹn ngày"
    if t.get("time"):
        when += " " + t["time"] + ("-" + t["end"] if t.get("end") else "")
    parts.append(when)
    if t.get("repeat"):
        parts.append(_rep_text(t["repeat"]))
    if t.get("location"):
        parts.append("tại " + t["location"])
    if t.get("kind") == "appt" and str(t.get("remind") or "0") not in ("", "0"):
        parts.append(f"nhắc trước {t['remind']} phút")
    tags = _tag_names(data, t)
    if tags:
        parts.append("tag " + ", ".join(tags))
    if t.get("star"):
        parts.append("ưu tiên")
    if not t.get("repeat") and t.get("status") == "done":
        parts.append("ĐÃ XONG")
    return f"\"{t.get('title')}\" ({'; '.join(parts)}) id={t.get('id')}"


def _pick(args, tasks):
    """One item by id or by name. Returns (task, None) or (None, text for the model)."""
    tid = str(args.get("id") or "").strip()
    if tid:
        hits = [t for t in tasks if t.get("id") == tid]
    else:
        q = _norm(args.get("name") or "")
        if len(q) < 2:
            return None, "ERROR: cần id hoặc name (tên việc / lịch hẹn)."
        exact = [t for t in tasks if _norm(t.get("title")) == q]
        hits = exact or [t for t in tasks if q in _norm(t.get("title")) or _norm(t.get("title")) in q]
        open_hits = [t for t in hits if t.get("repeat") or t.get("kind") == "appt" or t.get("status") != "done"]
        hits = open_hits or hits
    if not hits:
        return None, "Không thấy việc nào khớp. Hỏi lại người dùng tên chính xác, hoặc gọi op=list scope=all để xem."
    if len(hits) > 1:
        return None, ("Có nhiều mục khớp, HỎI LẠI người dùng là mục nào (hoặc dùng id), đừng đoán:\n"
                      + "\n".join(f"- {t['title']} ({_kind(t)}, {t.get('date') or 'chưa hẹn ngày'}) id={t['id']}" for t in hits[:10]))
    return hits[0], None


def _them(args, ctx) -> str:
    if not ctx.vault_root:
        return "ERROR: chưa xác định brain hiện tại, không thêm được việc."
    f, err = _store()
    if err:
        return err
    title = str(args.get("title") or "").strip()
    if not title:
        return "ERROR: thiếu title (tên việc)."
    rep = _repeat(args)
    habit = bool(args.get("habit"))
    appt = str(args.get("kind") or "") == "appt"
    today = _today(f)
    try:
        d = _date_arg(args.get("date")) if _has(args, "date") else None
        tm = _time_arg(args.get("time")) if _has(args, "time") else ""
        end = _time_arg(args.get("end")) if _has(args, "end") else ""
    except ValueError as e:
        return f"ERROR: {e}."
    payload = {"title": title, "date": d or (today if habit or (rep and not d) else None), "time": tm,
               "repeat": rep, "notes": args.get("notes") or "", "from_javis": False}
    if appt:
        if not payload["date"] or not tm:
            return "ERROR: lịch hẹn cần date (YYYY-MM-DD) và time (HH:MM). Hỏi lại người dùng giờ hẹn."
        dur = int(args.get("duration") or 60)
        payload.update({"kind": "appt", "end": end if end and end > tm else _hm(_minutes(tm) + max(5, dur)),
                        "location": str(args.get("location") or ""), "remind": str(args.get("remind") if _has(args, "remind") else "15")})
    if habit and rep is None:
        payload["repeat"] = {"unit": "day", "n": 1}
    if habit and not appt:
        payload["habit"] = {"start": today, "remind": "auto"}
    if _has(args, "tags"):
        payload["tags"] = _tag_ids(f, ctx.vault_root, args.get("tags"))
    if args.get("star") and not payload["repeat"] and not appt:
        payload["star"] = True
    r = f.create(ctx.vault_root, payload)
    if not r.get("ok"):
        return "ERROR: " + str(r.get("error") or "không thêm được")
    return "OK: đã thêm " + _describe(r["task"], f.load(ctx.vault_root)) + " vào tab Việc của tôi, trang Nhiệm vụ."


def _occurs_between(t: dict, a: str, b: str) -> list:
    """The dates in [a, b] a repeat falls on (skipped times left out)."""
    anchor = t.get("date") or (t.get("habit") or {}).get("start") or a
    sk = t.get("skip_dates") or {}
    out, d, end = [], date.fromisoformat(a), date.fromisoformat(b)
    while d <= end and len(out) < 40:
        iso = d.isoformat()
        if my_tasks_mod.occurs_on(t["repeat"], anchor, iso) and iso not in sk:
            out.append(iso)
        d += timedelta(days=1)
    return out


def _liet_ke(args, ctx) -> str:
    if not ctx.vault_root:
        return "ERROR: chưa xác định brain hiện tại."
    f, err = _store()
    if err:
        return err
    today = _today(f)
    data = f.load(ctx.vault_root)
    scope = _norm(args.get("scope") or "today")
    q = _norm(args.get("name") or args.get("query") or "")
    tasks = [t for t in data.get("tasks", []) if not q or q in _norm(t.get("title"))]
    if scope == "all":
        lines = [("- " + _describe(t, data)) for t in tasks if t.get("repeat") or t.get("kind") == "appt" or t.get("status") != "done"]
        return f"Tất cả việc, lịch hẹn và thói quen đang mở ({len(lines)}):\n" + ("\n".join(lines) if lines else "(không có)")
    try:
        days = max(1, min(60, int(args.get("days") or 7)))
    except (TypeError, ValueError):
        days = 7
    end = today if scope != "upcoming" else (date.fromisoformat(today) + timedelta(days=days)).isoformat()
    lines = []
    for t in tasks:
        if t.get("repeat"):
            hits = _occurs_between(t, today, end)
            if not hits:
                continue
            done = today in (t.get("done_dates") or {})
            extra = ""
            if t.get("habit") and not (t["habit"] or {}).get("off"):
                st = my_tasks_mod.habit_state(t, today)
                extra = f", thói quen chuỗi {st['cur']} ngày" + (", ĐANG ĐÓNG BĂNG" if st["frozen"] else "")
            when = ", ".join(hits[:7]) if scope == "upcoming" else (t.get("time") or "")
            lines.append(f"- [{'x' if done and hits[0] == today else ' '}] {t['title']} ({_kind(t)} {_rep_text(t['repeat'])}"
                         f"{', ' + when if when else ''}{extra}) id={t['id']}")
        elif t.get("kind") == "appt":
            if t.get("date") and today <= t["date"] <= end:
                lines.append(f"- {t['title']} (lịch hẹn {t['date']} {t.get('time', '')}-{t.get('end', '')}"
                             f"{', ' + t['location'] if t.get('location') else ''}) id={t['id']}")
        elif t.get("status") != "done" and ((t.get("date") or "") <= end if scope == "upcoming" else (t.get("date") or "") <= today):
            late = " QUÁ HẠN" if t.get("date") and t["date"] < today else ""
            lines.append(f"- [ ] {t['title']} ({t.get('date') or 'chưa hẹn ngày'}{' ' + t['time'] if t.get('time') else ''}{late}"
                         f"{', ưu tiên' if t.get('star') else ''}) id={t['id']}")
    head = "Việc của người dùng hôm nay " + today if scope != "upcoming" else f"Việc và lịch hẹn từ {today} đến {end}"
    return head + ":\n" + ("\n".join(lines) if lines else "(không có)")


def _sua(args, ctx) -> str:
    """Change any field of one item. Only the keys given are changed."""
    if not ctx.vault_root:
        return "ERROR: chưa xác định brain hiện tại."
    f, err = _store()
    if err:
        return err
    data = f.load(ctx.vault_root)
    t, msg = _pick(args, data.get("tasks", []))
    if not t:
        return msg
    today = _today(f)
    p, changed = {"id": t["id"]}, []
    try:
        if _has(args, "title") and str(args["title"]).strip():
            p["title"] = str(args["title"]).strip()
            changed.append("tên")
        if _has(args, "date"):
            p["date"] = _date_arg(args["date"])
            changed.append("ngày")
        if _has(args, "time"):
            p["time"] = _time_arg(args["time"])
            changed.append("giờ")
        if _has(args, "end"):
            p["end"] = _time_arg(args["end"])
            changed.append("giờ kết thúc")
    except ValueError as e:
        return f"ERROR: {e}."
    if _has(args, "repeat"):
        p["repeat"] = _repeat(args)
        changed.append("lặp")
        if p["repeat"] and not (p.get("date") or t.get("date")):
            p["date"] = today
        if not p["repeat"] and t.get("habit"):
            p["habit"] = None
    elif _has(args, "every") or _has(args, "days"):
        rep = dict(t.get("repeat") or {})
        if not rep:
            return "ERROR: mục này không lặp; truyền repeat (day|week|month|year) để bật lặp."
        p["repeat"] = _repeat({"repeat": rep["unit"], "every": args.get("every") or rep.get("n"),
                               "days": args.get("days") if _has(args, "days") else ",".join(WD_NAME[d] for d in rep.get("days") or [])})
        changed.append("lặp")
    for key, label in (("location", "địa điểm"), ("notes", "ghi chú")):
        if _has(args, key):
            p[key] = str(args[key] or "")
            changed.append(label)
    if _has(args, "remind"):
        p["remind"] = str(args["remind"] or "0")
        changed.append("nhắc trước")
    if _has(args, "tags"):
        p["tags"] = _tag_ids(f, ctx.vault_root, args["tags"])
        changed.append("tag")
    kind = str(args.get("kind") or "")
    if kind in ("task", "appt") and kind != (t.get("kind") or "task"):
        p["kind"] = kind
        changed.append("loại (" + ("lịch hẹn" if kind == "appt" else "việc") + ")")
    final_kind = p.get("kind") or t.get("kind") or "task"
    if final_kind == "appt":
        d = p.get("date", t.get("date"))
        tm = p.get("time", t.get("time"))
        if not d or not tm:
            return "ERROR: lịch hẹn cần ngày và giờ bắt đầu. Hỏi lại người dùng giờ hẹn rồi gọi lại với date và time."
        end = p.get("end", t.get("end")) or ""
        dur = int(args.get("duration") or 0)
        if dur:
            p["end"] = _hm(_minutes(tm) + max(5, dur))
        elif not end or end <= tm:
            old = (_minutes(t["end"]) - _minutes(t["time"])) if t.get("end") and t.get("time") and t["end"] > t["time"] else 60
            p["end"] = _hm(_minutes(tm) + max(5, old))
        if kind == "appt" and not str(t.get("remind") or "").isdigit() and "remind" not in p:
            p["remind"] = "15"
        if t.get("habit"):
            p["habit"] = None          # an appointment is not a habit
        if t.get("star"):
            p["star"] = False          # priorities are one-off tasks
    if _has(args, "habit"):
        if args.get("habit"):
            if final_kind == "appt":
                return "ERROR: lịch hẹn không bật thói quen được; đổi kind=task trước."
            if not (p.get("repeat", t.get("repeat"))):
                p["repeat"] = {"unit": "day", "n": 1}
                p.setdefault("date", t.get("date") or today)
            hb = dict(t.get("habit") or {})
            hb.pop("off", None)
            p["habit"] = hb or {"start": today, "remind": "auto"}
        elif t.get("habit"):
            p["habit"] = dict(t["habit"], off=True)
        changed.append("thói quen")
    if _has(args, "star"):
        if args.get("star") and (p.get("repeat", t.get("repeat")) or final_kind == "appt"):
            return "ERROR: chỉ việc một lần mới gắn sao ưu tiên được (việc lặp, thói quen và lịch hẹn thì không)."
        p["star"] = bool(args.get("star"))
        changed.append("ưu tiên")
    status = str(args.get("status") or "")
    if len(p) == 1 and status not in ("done", "open"):
        return "ERROR: không có gì để sửa. Truyền trường cần đổi (title, date, time, end, kind, repeat, location, remind, notes, tags, habit, star, status)."
    r = f.update(ctx.vault_root, p) if len(p) > 1 else {"ok": True, "task": t}
    if not r.get("ok"):
        return "ERROR: " + str(r.get("error") or "không sửa được")
    if status in ("done", "open"):
        if t.get("repeat"):
            return "ERROR: việc lặp thì dùng op=check / uncheck với date, hoặc op=skip để bỏ qua một lần."
        r = f.check(ctx.vault_root, t["id"], "", "javis", status == "done")
        changed.append("đã xong" if status == "done" else "mở lại")
    return "OK: đã sửa " + ", ".join(changed) + ". Bây giờ: " + _describe(r["task"], f.load(ctx.vault_root))


def _xoa(args, ctx) -> str:
    if not ctx.vault_root:
        return "ERROR: chưa xác định brain hiện tại."
    f, err = _store()
    if err:
        return err
    data = f.load(ctx.vault_root)
    t, msg = _pick(args, data.get("tasks", []))
    if not t:
        return msg
    desc = _describe(t, data)
    r = f.delete(ctx.vault_root, t["id"])
    if not r.get("ok"):
        return "ERROR: " + str(r.get("error") or "không xoá được")
    whole = " (cả chuỗi lặp; muốn bỏ một lần thôi thì dùng op=skip)" if t.get("repeat") else ""
    return f"OK: đã xoá {desc}{whole}."


def _bo_qua(args, ctx) -> str:
    """Skip one time of a repeat: the given date, or its next time from today."""
    if not ctx.vault_root:
        return "ERROR: chưa xác định brain hiện tại."
    f, err = _store()
    if err:
        return err
    data = f.load(ctx.vault_root)
    t, msg = _pick(args, data.get("tasks", []))
    if not t:
        return msg
    if not t.get("repeat"):
        return "ERROR: chỉ việc lặp hoặc lịch hẹn lặp mới bỏ qua một lần được. Việc một lần thì dời ngày (op=update date) hoặc xoá."
    today = _today(f)
    try:
        day = _date_arg(args.get("date")) if _has(args, "date") else None
    except ValueError as e:
        return f"ERROR: {e}."
    if not day:
        nxt = [d for d in _occurs_between(t, today, (date.fromisoformat(today) + timedelta(days=400)).isoformat())
               if d not in (t.get("done_dates") or {})]
        day = nxt[0] if nxt else None
    anchor = t.get("date") or (t.get("habit") or {}).get("start") or today
    if not day or not my_tasks_mod.occurs_on(t["repeat"], anchor, day):
        return f"ERROR: \"{t['title']}\" không có lần nào vào ngày {day or '(không tìm thấy lần tới)'}."
    sk = dict(t.get("skip_dates") or {})
    sk[day] = 1
    r = f.update(ctx.vault_root, {"id": t["id"], "skip_dates": sk})
    if not r.get("ok"):
        return "ERROR: " + str(r.get("error") or "không bỏ qua được")
    return f"OK: đã bỏ qua \"{t['title']}\" ngày {day} (tính là đã xử lý, không tính lửa). Lịch lặp giữ nguyên."


def _tich(args, ctx, done: bool = True) -> str:
    if not ctx.vault_root:
        return "ERROR: chưa xác định brain hiện tại."
    f, err = _store()
    if err:
        return err
    today = _today(f)
    data = f.load(ctx.vault_root)
    t, msg = _pick(args, data.get("tasks", []))
    if not t:
        return msg
    if t.get("kind") == "appt":
        return "ERROR: lịch hẹn không cần tích, nó tự qua khi hết giờ."
    day = str(args.get("date") or "") or today
    r = f.check(ctx.vault_root, t["id"], day if t.get("repeat") else "", "javis", done)
    if not r.get("ok"):
        return "ERROR: " + str(r.get("error") or "không tích được")
    if not done:
        return f"OK: đã bỏ tích \"{t['title']}\"" + (f" ngày {day}." if t.get("repeat") else ".")
    if t.get("habit") and t.get("repeat"):
        st = my_tasks_mod.habit_state(r["task"], today)
        return (f"OK: đã tích \"{t['title']}\" ngày {day} (Javis tích theo lời người dùng, họ bỏ tích được trên trang Nhiệm vụ). "
                f"Chuỗi giữ lửa: {st['cur']} ngày.")
    return f"OK: đã đánh dấu xong \"{t['title']}\"."


def register(ctx):
    ctx.register_tool(
        "javis_mytask",
        "Việc, lịch hẹn và thói quen của CHÍNH người dùng (tab Việc của tôi trên trang Nhiệm vụ). Mọi thứ người dùng "
        "sửa được trên trang thì sửa được bằng tool này. "
        "op=add: thêm (title; date YYYY-MM-DD, time HH:MM; repeat day|week|month|year, every, days 'T3,T5' khi lặp theo tuần; "
        "habit=true để giữ lửa thói quen; kind=appt cho lịch hẹn với end HH:MM hoặc duration phút, location, remind phút; "
        "tags 'Bán hàng, Ebook'; star=true cho việc một lần ưu tiên hôm nay). "
        "op=list: scope=today (mặc định) | upcoming (days ngày tới) | all, name để lọc. "
        "op=update: sửa MỘT mục theo id hoặc name, chỉ truyền trường cần đổi: title, date (none để bỏ ngày), time, end, "
        "duration, kind task|appt (đổi việc lặp thành lịch hẹn và ngược lại), repeat (none để thôi lặp), every, days, "
        "location, remind, notes, tags, habit true|false, star, status done|open. "
        "op=delete: xoá một mục (việc lặp thì xoá cả chuỗi). op=skip: bỏ qua một lần của việc lặp (date, mặc định lần tới). "
        "op=check / uncheck: CHỈ khi người dùng NÓI RÕ đã làm xong (vd 'đọc sách xong rồi'); câu mơ hồ thì KHÔNG tích. "
        "Nhiều mục khớp thì tool trả danh sách: hỏi lại người dùng, đừng đoán. "
        "Việc Javis làm thì dùng javis_task hoặc javis_schedule, KHÔNG dùng tool này.",
        _chay,
        schema={
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": ["add", "list", "update", "delete", "skip", "check", "uncheck"]},
                "id": {"type": "string"}, "name": {"type": "string"},
                "title": {"type": "string"}, "date": {"type": "string"}, "time": {"type": "string"},
                "end": {"type": "string"}, "duration": {"type": "integer"},
                "kind": {"type": "string", "enum": ["task", "appt"]},
                "repeat": {"type": "string", "enum": ["none", "day", "week", "month", "year"]},
                "every": {"type": "integer"}, "days": {"type": "string"}, "habit": {"type": "boolean"},
                "location": {"type": "string"}, "remind": {"type": "string"}, "notes": {"type": "string"},
                "tags": {"type": "string"}, "star": {"type": "boolean"},
                "status": {"type": "string", "enum": ["done", "open"]},
                "scope": {"type": "string", "enum": ["today", "upcoming", "all"]},
            },
            "required": ["op"],
        },
        min_mode="safe",
        emoji="✅",
    )


async def _chay(args, ctx) -> str:
    args = args or {}
    op = str(args.get("op") or "").strip().lower()
    if op == "add":
        return _them(args, ctx)
    if op == "list":
        return _liet_ke(args, ctx)
    if op == "update":
        return _sua(args, ctx)
    if op == "delete":
        return _xoa(args, ctx)
    if op == "skip":
        return _bo_qua(args, ctx)
    if op == "check":
        return _tich(args, ctx, True)
    if op == "uncheck":
        return _tich(args, ctx, False)
    return "ERROR: op phải là add, list, update, delete, skip, check hoặc uncheck."
