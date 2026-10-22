"""Regression (customer report 0.270, Code 4): the Kanban "needs approval" box is a review AFTER.

`needs_approval` was designed as "review the result": the form checkbox read "Yêu cầu duyệt kết
quả" and docs/21-viec-kanban.md says a ticked job runs, then stops in `review` instead of closing.
The labels "Cần duyệt ngoại lệ" / "Approve exception" made a customer expect approval BEFORE the
run. Behaviour is unchanged; this test pins it and pins labels that say plainly it is the result
being reviewed, in both languages, with the explanation in an (i) block.

    python tests/python/test_kanban_review_after_label.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import tempfile
from pathlib import Path

import task_store

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


vi = json.loads((ROOT / "dashboard" / "i18n" / "vi.json").read_text(encoding="utf-8"))
en = json.loads((ROOT / "dashboard" / "i18n" / "en.json").read_text(encoding="utf-8"))

for key in ("kanban.need_approve", "kanban.act_approve", "kanban.st_review", "lenh.tk_review"):
    check(f"vi {key} says it is the result being reviewed", "kết quả" in vi.get(key, ""))
    check(f"en {key} says it is the result being reviewed", "result" in en.get(key, "").lower())
    check(f"vi {key} no longer says 'ngoại lệ'", "ngoại lệ" not in vi.get(key, ""))
    check(f"en {key} no longer says 'exception'", "exception" not in en.get(key, "").lower())

check("vi info text says it does not wait for approval before running",
      "không bắt duyệt trước khi chạy" in vi.get("kanban.need_approve_info", ""))
check("en info text says it does not wait for approval before running",
      "does not ask for approval before" in en.get("kanban.need_approve_info", ""))

console = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
form = console[console.index('id="knApprove"') - 400: console.index('id="knApprove"')]
check("form shows the explanation in an (i) block next to the checkbox",
      "infoBtn()" in form and 'infoBody(esc(t("kanban.need_approve_info")))' in form)

# Behaviour pinned: a needs_approval task is claimable right away and lands in `review` after.
store = task_store.TaskStore(Path(tempfile.mkdtemp(prefix="javis-review-after-")) / "tasks.sqlite3")
root = tempfile.mkdtemp(prefix="javis-review-after-brain-")
tid = store.enqueue(root, "Đọc báo cáo", "Đọc báo cáo", needs_approval=True, status="ready")
claimed = store.claim(tid, "w1")
check("needs_approval task is claimed without a prior approval", bool(claimed))
done = store.complete(tid, "w1", "Kết quả", needs_approval=True)
check("needs_approval task ends in review with its result",
      bool(done) and done.get("status") == "review" and done.get("result") == "Kết quả")

if _fails:
    raise SystemExit(f"{len(_fails)} check(s) failed")
print("all ok")
