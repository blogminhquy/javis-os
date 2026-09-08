"""Test Dataview lite + tick task (mdindex / taskcheck). Chạy tay / CI:

    python tests/run.py dataview_tasks

KHÔNG mạng. Phủ: _md_task_fields bóc ngày + độ ưu tiên kiểu obsidian-tasks,
_scan_note_md (frontmatter, tag, task, bỏ qua code fence, số dòng theo file gốc),
/files/mdindex trả chỉ mục, /files/taskcheck lật checkbox đúng dòng + rào expect
(409 khi file đổi) + tự gắn/gỡ "✅ ngày" cho task kiểu obsidian-tasks.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-dvtest-"))

import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


_TMP = Path(tempfile.mkdtemp(prefix="javis-dvbrain-")).resolve()
BRAIN = _TMP / "brains" / "vault"
(BRAIN / "05 - Việc").mkdir(parents=True)
main._brain_root = lambda brain: str(BRAIN)
os.environ["JAVIS_HOST"] = "127.0.0.1"
os.environ.pop("JAVIS_REQUIRE_LOGIN", None)

NOTE = """---
type: project
tags: [duan, "quan-trong"]
status: doing
---

# Kế hoạch #q3

- [ ] Gọi khách A 📅 2026-07-30 ⏫
- [x] Chốt báo giá ✅ 2026-07-20
- [ ] Việc thường không ngày

```bash
- [ ] task giả trong code fence, không được nhặt
# than-phien-gia
```

Ghi chú #ban-hang cuối trang.
"""
(BRAIN / "05 - Việc" / "du-an.md").write_text(NOTE, encoding="utf-8")
(BRAIN / "note-khac.md").write_text("- [ ] việc lẻ ngoài thư mục", encoding="utf-8")

try:
    # ---- 1. _md_task_fields ----
    txt, f = main._md_task_fields("Gọi khách A 📅 2026-07-30 ⏫")
    check("fields: bóc due", f.get("due") == "2026-07-30")
    check("fields: priority cao", f.get("priority") == 1)
    check("fields: text sạch emoji", txt == "Gọi khách A")
    txt2, f2 = main._md_task_fields("Việc thường")
    check("fields: mặc định priority 3, không due", f2.get("priority") == 3 and "due" not in f2)

    # ---- 2. _scan_note_md ----
    fm, tags, tasks = main._scan_note_md(NOTE)
    check("scan: frontmatter", fm.get("type") == "project" and fm.get("status") == "doing")
    check("scan: tag gộp frontmatter + inline",
          "#duan" in tags and "#q3" in tags and "#ban-hang" in tags)
    check("scan: không nhặt tag trong fence", "#than-phien-gia" not in tags)
    check("scan: đủ 3 task (bỏ task trong fence)", len(tasks) == 3)
    check("scan: task done có ngày done", tasks[1]["checked"] and tasks[1].get("done") == "2026-07-20")
    lines = NOTE.split("\n")
    check("scan: line đúng file gốc",
          all(main._MD_TASK_RE.match(lines[t["line"] - 1]) for t in tasks))

    # ---- 3. /files/mdindex: chỉ mục + cache mtime tăng dần + ETag + đa thư mục ----
    import json as _json
    import time as _time

    def _jbody(r):
        return _json.loads(r.body)

    calls = {"n": 0}
    _orig_scan = main._scan_note_md

    def _counting_scan(text):
        calls["n"] += 1
        return _orig_scan(text)

    main._scan_note_md = _counting_scan
    try:
        r = asyncio.run(main.files_mdindex(brain="brain", path=None, if_none_match=None))
        d = _jbody(r)
        paths = [x["path"] for x in d["files"]]
        check("mdindex: thấy cả 2 note", "05 - Việc/du-an.md" in paths and "note-khac.md" in paths)
        check("mdindex: lần đầu parse đủ 2 file", calls["n"] == 2)
        etag = d.get("etag")
        check("mdindex: có etag (body + header)", bool(etag) and r.headers.get("ETag") == etag)

        calls["n"] = 0
        r2 = asyncio.run(main.files_mdindex(brain="brain", path=None, if_none_match=None))
        check("mdindex: lần 2 KHÔNG parse lại (cache mtime)",
              calls["n"] == 0 and _jbody(r2)["etag"] == etag)

        r3 = asyncio.run(main.files_mdindex(brain="brain", path=None, if_none_match=etag))
        check("mdindex: If-None-Match trúng -> 304 rỗng", r3.status_code == 304)

        calls["n"] = 0
        p2 = BRAIN / "note-khac.md"
        p2.write_text("- [ ] việc lẻ ngoài thư mục\n- [ ] việc mới thêm", encoding="utf-8")
        os.utime(p2, (_time.time() + 5, _time.time() + 5))   # ép mtime đổi dù fs làm tròn giây
        r4 = asyncio.run(main.files_mdindex(brain="brain", path=None, if_none_match=etag))
        d4 = _jbody(r4)
        check("mdindex: file đổi -> 200 + etag mới", r4.status_code == 200 and d4["etag"] != etag)
        check("mdindex: chỉ parse lại đúng file đổi", calls["n"] == 1)

        d5 = _jbody(asyncio.run(main.files_mdindex(brain="brain", path=["05 - Việc"], if_none_match=None)))
        check("mdindex: lọc theo list thư mục", [x["path"] for x in d5["files"]] == ["05 - Việc/du-an.md"])
        d6 = _jbody(asyncio.run(main.files_mdindex(brain="brain", path="05 - Việc", if_none_match=None)))
        check("mdindex: path chuỗi (tương thích cũ) vẫn chạy",
              [x["path"] for x in d6["files"]] == ["05 - Việc/du-an.md"])
        check("mdindex: path ngoài brain bị chặn",
              _jbody(asyncio.run(main.files_mdindex(brain="brain", path=["../.."], if_none_match=None)))["files"] == [])

        extra = BRAIN / "tam.md"
        extra.write_text("- [ ] tạm", encoding="utf-8")
        d7 = _jbody(asyncio.run(main.files_mdindex(brain="brain", path=None, if_none_match=None)))
        check("mdindex: thấy file mới tạo", any(x["path"] == "tam.md" for x in d7["files"]))
        extra.unlink()
        d8 = _jbody(asyncio.run(main.files_mdindex(brain="brain", path=None, if_none_match=None)))
        check("mdindex: file xoá biến khỏi chỉ mục", not any(x["path"] == "tam.md" for x in d8["files"]))
    finally:
        main._scan_note_md = _orig_scan

    # ---- 4. /files/taskcheck ----
    t0 = tasks[0]
    r = asyncio.run(main.files_taskcheck(brain="brain", path="05 - Việc/du-an.md",
                                         line=t0["line"], checked=1, expect=t0["raw"].strip()))
    check("taskcheck: tick ok", isinstance(r, dict) and r.get("ok"))
    body = (BRAIN / "05 - Việc" / "du-an.md").read_text(encoding="utf-8")
    line_now = body.split("\n")[t0["line"] - 1]
    check("taskcheck: dòng thành [x]", "- [x] Gọi khách A" in line_now)
    check("taskcheck: task obsidian tick xong gắn ✅ ngày", "✅ " + main._today() in line_now)

    r = asyncio.run(main.files_taskcheck(brain="brain", path="05 - Việc/du-an.md",
                                         line=t0["line"], checked=0, expect=line_now.strip()))
    body = (BRAIN / "05 - Việc" / "du-an.md").read_text(encoding="utf-8")
    line_now = body.split("\n")[t0["line"] - 1]
    check("taskcheck: untick gỡ ✅ ngày", "- [ ] Gọi khách A" in line_now and "✅" not in line_now)

    # file đổi (expect lệch) -> 409, KHÔNG ghi
    r = asyncio.run(main.files_taskcheck(brain="brain", path="05 - Việc/du-an.md",
                                         line=t0["line"], checked=1, expect="- [ ] dòng không tồn tại"))
    check("taskcheck: expect lệch -> 409", getattr(r, "status_code", 0) == 409)

    # expect đúng nhưng line lệch (file bị chèn dòng) -> vẫn tìm ra theo nội dung
    r = asyncio.run(main.files_taskcheck(brain="brain", path="05 - Việc/du-an.md",
                                         line=2, checked=1, expect="- [ ] Việc thường không ngày"))
    body = (BRAIN / "05 - Việc" / "du-an.md").read_text(encoding="utf-8")
    check("taskcheck: line lệch vẫn khớp theo expect",
          isinstance(r, dict) and r.get("ok") and "- [x] Việc thường không ngày" in body)
    check("taskcheck: checklist thường KHÔNG bị gắn ✅",
          "Việc thường không ngày ✅" not in body)

    # đường dẫn leo thang -> 400
    r = asyncio.run(main.files_taskcheck(brain="brain", path="../../ngoai.md",
                                         line=1, checked=1, expect=""))
    check("taskcheck: chặn ../", getattr(r, "status_code", 0) in (400, 404))

    # ---- 5. /files/taskadd (nút "+ Việc") ----
    r = asyncio.run(main.files_taskadd(brain="brain", text="Việc thêm nhanh", due="2026-08-01", path=""))
    check("taskadd: mặc định rơi vào Task Inbox trong thư mục Dashboard",
          isinstance(r, dict) and r.get("ok") and r["path"].endswith("Task Inbox.md")
          and "Dashboard" in r["path"])
    inbox = BRAIN / r["path"]
    body = inbox.read_text(encoding="utf-8")
    # Từ 03/09 brain mới KHÔNG còn được rải sẵn Task Inbox, nên đường này là chỗ DUY NHẤT
    # sinh ra nó. File tự tạo phải có đủ phần mở đầu, không phải một file trơ chỉ có task.
    check("CANARY: taskadd tự tạo được file kèm phần mở đầu (không còn ai seed sẵn nữa)",
          body.startswith("# Task Inbox"))
    check("taskadd: dòng task đúng + gắn 📅", "- [ ] Việc thêm nhanh 📅 2026-08-01" in body)
    r2 = asyncio.run(main.files_taskadd(brain="brain", text="Việc 2", due="", path=r["path"]))
    body = inbox.read_text(encoding="utf-8")
    check("taskadd: append vào file chỉ định, không có hạn thì không 📅",
          isinstance(r2, dict) and r2.get("ok") and body.rstrip().endswith("- [ ] Việc 2"))
    check("taskadd: line trả về trỏ đúng dòng (tick được ngay)",
          body.split("\n")[r2["line"] - 1].strip() == "- [ ] Việc 2")
    r3 = asyncio.run(main.files_taskadd(brain="brain", text="x", due="", path="../../ngoai.md"))
    check("taskadd: chặn ../", getattr(r3, "status_code", 0) == 400)
    r4 = asyncio.run(main.files_taskadd(brain="brain", text="   ", due="", path=""))
    check("taskadd: nội dung trống -> 400", getattr(r4, "status_code", 0) == 400)
finally:
    pass

print()
if _fails:
    print(f"{len(_fails)} test FAIL: {_fails}")
    sys.exit(1)
print("Tất cả test dataview/tasks OK")
