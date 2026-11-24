"""Memory recall flags a conflict only when two records state different things about one specific subject (#1743).

    python tests/run.py memory_conflict_labels

Reported on 0.620.0: retrieve() paired any two recalled records of different files that shared a `subject`, and the
subject was the text before the first ":" of a paragraph, else the heading. #934 listed generic labels ("Vì sao:"),
but any other shared label still collided. One brain prefixes memories with a brand tag ("GROUP: ...", "SOHO: ..."):
57 files got subject `group` and the chat showed a false conflict almost every turn (1844 file pairs). Shared headings
did the same: "## Bài học (tự học)", which the core itself writes into every memory/agents/<slug>/MEMORY.md, and
"Liên quan", "Luật chủ đạo", "Quyết định đã chốt".

The rule now (server/memory_index.py, _label_subject): a subject comes only from a leading label of two or more words
that is not generic. A one-word label is a tag; a real label right behind it still counts, scoped by the tag. A heading
never makes a subject. Checked here with a real index on a temporary brain:
- the false positives from the report give no conflict, also at the scale of the report;
- "Giá gói Pro: 500k" against "Giá gói Pro: 700k" in two files is still a conflict, with or without a tag in front.
No model call, no network.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-conflict-labels-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

import memory_index  # noqa: E402
from memory_index import MemoryIndex, _label_subject  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:400] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


def recall(files: dict, query: str, limit: int = 12):
    """Write `files` into a fresh brain and recall `query` from a fresh index."""
    root = Path(tempfile.mkdtemp(prefix="javis-conflict-labels-"))
    brain = root / "b"
    for relative, text in files.items():
        path = brain / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return MemoryIndex(root / "state").retrieve(brain, query, limit=limit)


def files_of(got) -> set:
    return {record["content_ref"] for record in got.records}


def conflict_files(got) -> list:
    by_id = {record["record_id"]: record["content_ref"] for record in got.records}
    return [tuple(sorted((by_id.get(a), by_id.get(b)))) for a, b in got.conflicts]


FACT = "---\ntype: business\n---\n"

# ═════ 1. The subject rule on its own ═════
check("a specific label is the subject", _label_subject("- Giá gói Pro: 500k một tháng.") == "gia goi pro")
check("a one-word tag is not a subject", _label_subject("GROUP: khách sỉ được giảm 10 phần trăm.") == "")
check("a bold one-word tag is not a subject", _label_subject("**SOHO:** giao hàng trong ngày.") == "")
check("a real label behind a tag counts, scoped by the tag",
      _label_subject("GROUP: Giá gói Pro: 500k.") == "group gia goi pro", _label_subject("GROUP: Giá gói Pro: 500k."))
check("a generic label behind a tag is still nothing", _label_subject("GROUP: Lưu ý: gọi trước khi giao.") == "")
check("two tags in a row are nothing (one level only)", _label_subject("GROUP: SOHO: giá 500k.") == "")
check("a generic label is not a subject (#934)", _label_subject("**Vì sao:** chủ dặn.") == "")
check("a section name written as a label is not a subject",
      _label_subject("**Quyết định đã chốt:** dùng giao hàng nhanh.") == "")
check("no label, no subject", _label_subject("Khách sỉ được giảm 10 phần trăm.") == "")

# ═════ 2. False positives from the report ═════
got = recall({
    "memory/facts/group-si.md": FACT + "GROUP: khách sỉ mua trên 10 hộp được giảm 10 phần trăm.\n",
    "memory/facts/group-giao.md": FACT + "GROUP: giao hàng nội thành trong ngày, ngoại thành hai ngày.\n",
}, "GROUP khách sỉ giảm giá và giao hàng")
check("brand tag: both facts are recalled", len(got.records) == 2, files_of(got))
check("brand tag: two unrelated GROUP facts are no conflict", not got.conflicts, conflict_files(got))
check("brand tag: no context item names a conflict",
      not any(item.conflicts_with for item in got.context_items()))

got = recall({
    f"memory/facts/group-{n}.md": FACT + f"**GROUP:** chương trình khuyến mãi số {n} cho khách sỉ, áp dụng tới cuối tháng.\n"
    for n in range(12)
}, "GROUP chương trình khuyến mãi khách sỉ")
check("brand tag at scale: many GROUP files recalled", len(got.records) >= 6, len(got.records))
check("brand tag at scale: no conflict", not got.conflicts, conflict_files(got))

lessons = "# {name}\n\nViết ngắn gọn.\n\n## Bài học (tự học)\n- {lesson}\n"
got = recall({
    "memory/agents/sales/MEMORY.md": lessons.format(name="Sales", lesson="Báo giá luôn kèm phí ship cho khách."),
    "memory/agents/writer/MEMORY.md": lessons.format(name="Writer", lesson="Bài Facebook giữ dưới 150 chữ cho khách."),
    "memory/agents/support/MEMORY.md": lessons.format(name="Support", lesson="Trả lời khách trong 5 phút đầu."),
}, "bài học tự học cho khách")
check("core lessons heading: all three agent memories recalled",
      {"memory/agents/sales/MEMORY.md", "memory/agents/writer/MEMORY.md", "memory/agents/support/MEMORY.md"}
      <= files_of(got), files_of(got))
check("core lessons heading: '## Bài học (tự học)' in several agents is no conflict", not got.conflicts,
      conflict_files(got))

sections = FACT + "# {title}\n\n{body}\n\n## Liên quan\n- {link}\n\n## Luật chủ đạo\n{rule}\n\n## Quyết định đã chốt\n{decision}\n"
got = recall({
    "memory/facts/hop-qua.md": sections.format(
        title="Hộp quà Tết", body="Hộp quà Tết giá 120 nghìn.", link="[[Tết]] và [[Hộp quà]]",
        rule="Luôn gói giấy đỏ cho hộp quà.", decision="Chốt nhập 500 hộp quà trước rằm tháng chạp."),
    "memory/facts/giao-hang.md": sections.format(
        title="Giao hàng", body="Giao nội thành 20 nghìn.", link="[[Ship]] và [[Grab]]",
        rule="Luôn gọi khách trước khi giao.", decision="Chốt dùng Grab cho đơn gấp."),
}, "liên quan luật chủ đạo quyết định đã chốt hộp quà giao hàng")
check("shared headings: both files recalled", files_of(got) == {"memory/facts/hop-qua.md", "memory/facts/giao-hang.md"},
      files_of(got))
check("shared headings: 'Liên quan', 'Luật chủ đạo', 'Quyết định đã chốt' are no conflict", not got.conflicts,
      conflict_files(got))

got = recall({
    "memory/facts/chot-a.md": FACT + "**Quyết định đã chốt:** dùng Grab cho mọi đơn gấp trong nội thành.\n",
    "memory/facts/chot-b.md": FACT + "**Quyết định đã chốt:** nhập thêm 500 hộp quà trước Tết.\n",
}, "quyết định đã chốt grab hộp quà")
check("section name as a label: both recalled", len(got.records) == 2, files_of(got))
check("section name as a label: no conflict", not got.conflicts, conflict_files(got))

# ═════ 3. Real conflicts are still flagged ═════
pro_pair = ("memory/facts/gia-pro-a.md", "memory/facts/gia-pro-b.md")
got = recall({
    pro_pair[0]: FACT + "- Giá gói Pro: 500k một tháng.\n",
    pro_pair[1]: FACT + "- Giá gói Pro: 700k một tháng.\n",
}, "giá gói pro bao nhiêu")
check("CANARY: the same specific subject with two values in two files is a conflict",
      conflict_files(got) == [pro_pair], conflict_files(got))
ids = {item.id: item.conflicts_with for item in got.context_items()}
check("CANARY: each side of the conflict names the other",
      len(ids) == 2 and all(len(other) == 1 and other[0] in ids for other in ids.values()), ids)

got = recall({
    pro_pair[0]: FACT + "GROUP: Giá gói Pro: 500k một tháng.\n",
    pro_pair[1]: FACT + "GROUP: Giá gói Pro: 700k một tháng.\n",
    "memory/facts/soho-pro.md": FACT + "SOHO: Giá gói Pro: 900k một tháng.\n",
}, "giá gói pro bao nhiêu")
check("CANARY: behind a brand tag the same subject is still a conflict",
      conflict_files(got) == [pro_pair], conflict_files(got))

check("the schema version moved, so old indexes rebuild with the new subjects",
      memory_index.INDEX_SCHEMA_VERSION not in ("memory-index-v3", "memory-index-v4"), memory_index.INDEX_SCHEMA_VERSION)

print()
if fails:
    print(f"FAIL - {len(fails)} check(s): " + "; ".join(fails))
    raise SystemExit(1)
print("OK - test_memory_conflict_labels: all pass")
