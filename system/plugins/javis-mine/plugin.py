"""Bundled plugin: tool `javis_mytask` - the owner's own tasks and habits from chat, on every engine (0.425.0).

The Tasks page has a tab "Mine" (server/my_tasks.py). Spec docs/dev/2026-10-nhiem-vu-spec.md 7 and 8.4 promise two
things from chat: "add this to my list" and "I read for 30 minutes" ticking the habit. Both go through this tool,
in-process like javis-task (no HTTP route opened for it).

Ticking is the risky part: a wrong tick makes the owner stop trusting the streak. So op=check only acts when the
name matches ONE task; several matches return the list so the model asks back, and every tick by this tool is
stored with by="javis" so the page marks it and the owner can undo it there.
"""
from __future__ import annotations

import re
import time
import unicodedata

import my_tasks as my_tasks_mod

WD = {"cn": 0, "chu nhat": 0, "t2": 1, "thu 2": 1, "thu hai": 1, "t3": 2, "thu 3": 2, "thu ba": 2, "t4": 3, "thu 4": 3,
      "thu tu": 3, "t5": 4, "thu 5": 4, "thu nam": 4, "t6": 5, "thu 6": 5, "thu sau": 5, "t7": 6, "thu 7": 6, "thu bay": 6,
      "sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}


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
    from datetime import datetime
    return datetime.now(tz).date().isoformat()


def _repeat(args) -> dict | None:
    unit = str(args.get("repeat") or "").strip().lower()
    if unit in ("", "none", "khong"):
        return None
    if unit not in ("day", "week", "month", "year"):
        return None
    rep = {"unit": unit, "n": max(1, int(args.get("every") or 1))}
    if unit == "week":
        days = []
        for part in re.split(r"[,;/]+", str(args.get("days") or "")):
            k = _norm(part)
            if k in WD:
                days.append(WD[k])
        rep["days"] = sorted(set(days))
    return rep


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
    today = _today(f)
    payload = {"title": title, "date": args.get("date") or (today if habit else None), "time": args.get("time") or "",
               "repeat": rep, "notes": args.get("notes") or "", "from_javis": False}
    if habit:
        payload["habit"] = {"start": today, "remind": "auto"}
    r = f.create(ctx.vault_root, payload)
    if not r.get("ok"):
        return "ERROR: " + str(r.get("error") or "không thêm được")
    t = r["task"]
    kind = "thói quen (giữ lửa)" if t.get("habit") else ("việc lặp" if t.get("repeat") else "việc")
    when = (t.get("date") or "chưa hẹn ngày") + (" " + t["time"] if t.get("time") else "")
    return f"OK: đã thêm {kind} \"{t['title']}\" ({when}) vào tab Việc của tôi, trang Nhiệm vụ. id={t['id']}"


def _liet_ke(args, ctx) -> str:
    if not ctx.vault_root:
        return "ERROR: chưa xác định brain hiện tại."
    f, err = _store()
    if err:
        return err
    today = _today(f)
    data = f.load(ctx.vault_root)
    lines = []
    for t in data.get("tasks", []):
        if t.get("repeat"):
            anchor = t.get("date") or (t.get("habit") or {}).get("start") or today
            if not my_tasks_mod.occurs_on(t["repeat"], anchor, today):
                continue
            done = today in (t.get("done_dates") or {})
            extra = ""
            if t.get("habit") and not (t["habit"] or {}).get("off"):
                st = my_tasks_mod.habit_state(t, today)
                extra = f", thói quen chuỗi {st['cur']} ngày" + (", ĐANG ĐÓNG BĂNG" if st["frozen"] else "")
            lines.append(f"- [{'x' if done else ' '}] {t['title']} (lặp{extra}) id={t['id']}")
        elif t.get("status") != "done" and (t.get("date") or "") <= today:
            late = " QUÁ HẠN" if t.get("date") and t["date"] < today else ""
            lines.append(f"- [ ] {t['title']} ({t.get('date') or 'chưa hẹn ngày'}{late}) id={t['id']}")
    return "Việc của người dùng hôm nay " + today + ":\n" + ("\n".join(lines) if lines else "(không có)")


def _tich(args, ctx) -> str:
    if not ctx.vault_root:
        return "ERROR: chưa xác định brain hiện tại."
    f, err = _store()
    if err:
        return err
    today = _today(f)
    data = f.load(ctx.vault_root)
    tasks = data.get("tasks", [])
    tid = str(args.get("id") or "").strip()
    if tid:
        hits = [t for t in tasks if t.get("id") == tid]
    else:
        q = _norm(args.get("name") or "")
        if len(q) < 2:
            return "ERROR: cần id hoặc name (tên việc/thói quen người dùng vừa báo xong)."
        hits = [t for t in tasks if q in _norm(t.get("title")) or _norm(t.get("title")) in q]
        open_hits = [t for t in hits if t.get("repeat") or t.get("status") != "done"]
        hits = open_hits or hits
    if not hits:
        return "Không thấy việc nào khớp. Hỏi lại người dùng tên chính xác, hoặc gọi op=list để xem danh sách."
    if len(hits) > 1:
        return ("Có nhiều việc khớp, HỎI LẠI người dùng là việc nào, đừng đoán:\n"
                + "\n".join(f"- {t['title']} id={t['id']}" for t in hits[:10]))
    t = hits[0]
    date = str(args.get("date") or "") or today
    r = f.check(ctx.vault_root, t["id"], date if t.get("repeat") else "", "javis", True)
    if not r.get("ok"):
        return "ERROR: " + str(r.get("error") or "không tích được")
    if t.get("habit") and t.get("repeat"):
        st = my_tasks_mod.habit_state(r["task"], today)
        return (f"OK: đã tích \"{t['title']}\" ngày {date} (Javis tích theo lời người dùng, họ bỏ tích được trên trang Nhiệm vụ). "
                f"Chuỗi giữ lửa: {st['cur']} ngày.")
    return f"OK: đã đánh dấu xong \"{t['title']}\"."


def register(ctx):
    ctx.register_tool(
        "javis_mytask",
        "Việc của CHÍNH người dùng (tab Việc của tôi trên trang Nhiệm vụ) và thói quen của họ. "
        "op=add: người dùng nhờ ghi một việc họ tự làm (title; date YYYY-MM-DD, time HH:MM nếu có; "
        "repeat day|week|month|year, every, days 'T3,T5,T7' khi lặp theo tuần; habit=true nếu họ muốn giữ lửa thói quen). "
        "Việc Javis làm thì dùng javis_task hoặc javis_schedule, KHÔNG dùng tool này. "
        "op=list: xem việc và thói quen hôm nay. "
        "op=check: CHỈ khi người dùng NÓI RÕ là đã làm xong (vd 'đọc sách xong rồi', 'hôm nay tập rồi'): "
        "truyền name (hoặc id), tool tích xong và ghi là Javis tích. Câu mơ hồ ('chắc tối đọc', 'định tập') thì KHÔNG tích. "
        "Nhiều việc khớp thì tool trả danh sách: hỏi lại người dùng, đừng đoán.",
        _chay,
        schema={
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": ["add", "list", "check"]},
                "title": {"type": "string"}, "date": {"type": "string"}, "time": {"type": "string"},
                "repeat": {"type": "string", "enum": ["none", "day", "week", "month", "year"]},
                "every": {"type": "integer"}, "days": {"type": "string"}, "habit": {"type": "boolean"},
                "notes": {"type": "string"}, "name": {"type": "string"}, "id": {"type": "string"},
            },
            "required": ["op"],
        },
        min_mode="safe",
        emoji="✅",
    )


async def _chay(args, ctx) -> str:
    op = str((args or {}).get("op") or "").strip().lower()
    if op == "add":
        return _them(args or {}, ctx)
    if op == "list":
        return _liet_ke(args or {}, ctx)
    if op == "check":
        return _tich(args or {}, ctx)
    return "ERROR: op phải là add, list hoặc check."
