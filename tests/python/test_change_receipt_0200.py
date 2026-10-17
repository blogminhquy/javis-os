"""0.200.0: a chat turn that creates or edits a schedule, loop, partner, workflow or skill gets a receipt line.

Run:
    python tests/run.py change_receipt
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import tempfile
import time
from pathlib import Path

import change_receipt as cr  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


root = Path(tempfile.mkdtemp(prefix="javis-receipt-"))
(root / "Javis" / "loops").mkdir(parents=True)
(root / "agents").mkdir()
(root / "skills" / "old").mkdir(parents=True)
(root / "skills" / "old" / "SKILL.md").write_text("---\nname: Old skill\n---\nx", encoding="utf-8")
(root / "agents" / "lan.md").write_text("---\nname: Lan\n---\nbody", encoding="utf-8")
(root / "Javis" / "reminders.json").write_text(json.dumps({"reminders": [
    {"id": "r_old", "status": "pending", "label": "Old"}]}), encoding="utf-8")

check("no snapshot, no receipt", cr.diff(None, root) == [])
snap = cr.snapshot(root)
check("unchanged brain gives nothing", cr.diff(snap, root) == [])

time.sleep(0.01)
(root / "Javis" / "reminders.json").write_text(json.dumps({"reminders": [
    {"id": "r_old", "status": "cancelled", "label": "Old"},
    {"id": "r_new", "status": "pending", "label": "Báo doanh thu 7h"}]}), encoding="utf-8")
(root / "Javis" / "loops" / "quet-don.md").write_text("---\nname: Quét đơn\n---\n", encoding="utf-8")
(root / "agents" / "lan.md").write_text("---\nname: Lan (sửa)\n---\nbody 2", encoding="utf-8")
(root / "skills" / "viet-email").mkdir()
(root / "skills" / "viet-email" / "SKILL.md").write_text("---\nname: \"Viết email\"\n---\n", encoding="utf-8")
items = cr.diff(snap, root)
by = {(i["kind"], i["id"]): i for i in items}
check("new reminder", by.get(("reminder", "r_new"), {}).get("act") == "new"
      and by[("reminder", "r_new")]["title"] == "Báo doanh thu 7h")
check("cancelled reminder shows as removed", by.get(("reminder", "r_old"), {}).get("act") == "removed")
check("new loop with its name", by.get(("loop", "quet-don"), {}).get("title") == "Quét đơn")
check("edited agent", by.get(("agent", "lan"), {}).get("act") == "updated")
check("new skill name unquoted", by.get(("skill", "viet-email"), {}).get("title") == "Viết email")
check("old skill untouched not listed", ("skill", "old") not in by)

block = cr.receipt_block(items, "/brains/shop")
check("block shape", block.startswith("<!-- JAVIS_DOI: ") and block.endswith(" -->"))
data = json.loads(block[len("<!-- JAVIS_DOI: "):-4])
check("block carries brain and items", data["brain"] == "/brains/shop" and len(data["items"]) == len(items))
check("block cannot be closed early by a title", "-->" not in cr.receipt_block(
    [{"kind": "loop", "id": "x", "title": "evil --> <script>", "act": "new"}], "b")[:-4])
check("plain text line names each change", "Quét đơn" in cr.receipt_text(items))
check("items capped", len(cr.diff({"loop": {}, "agent": {}, "workflow": {}, "skill": {}, "reminder": {}}, root))
      <= cr.MAX_ITEMS)

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
