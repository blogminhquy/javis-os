"""Files and links of a conversation are read once, then only what is new (2026-11-12).

    python tests/run.py session_assets_scan

A customer: "load trong Team rất chậm", worse after hours of work in one team. Since 0.518.0 a team opens with its Info
tab, and that tab asks GET /sessions/{id}/assets, which read EVERY message of the team on every open (1.5 s for 3,000
messages, and it slowed every other request meanwhile). session_assets_scan.py keeps what the messages mention.

Two things are guarded here: the answer is the same as reading everything again (checked against the old way of
computing it, after appends, an edit, a delete and a rewind), and an open with nothing new reads no message at all.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import random
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-assets-scan-"))

from fastapi.testclient import TestClient  # noqa: E402
import channel_context  # noqa: E402
import main  # noqa: E402
import session_assets_scan as scan  # noqa: E402
from sessions import get_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:600] + "]") if not cond and extra != "" else ""))
    if not cond:
        fails.append(name)


BRAIN = tempfile.mkdtemp(prefix="javis-brain-assets-scan-")
broot = Path(BRAIN).resolve()
(broot / "docs").mkdir()
for n in ("plan.md", "price.md", "moved.md", "late.md"):
    (broot / "docs" / n).write_text(n, encoding="utf-8")
(broot / "docs" / "moved.md").unlink()                 # linked in the chat, gone from disk

st = get_store()
c = TestClient(main.app, base_url="http://127.0.0.1")


def old_way(sid):
    """The answer as 0.545.2 computed it: every message, in order, on every call."""
    files, links = {}, {}
    for m in st.get_messages(sid):
        text = m.get("content") or ""
        if not text:
            continue
        ts = m.get("ts") or 0
        for tg in channel_context.markdown_targets(text):
            raw = tg["raw"]
            if "://" in raw or raw.startswith(("#", "mailto:", "data:", "tel:")):
                continue
            cand = channel_context._vault_markdown_candidate(raw, str(broot))
            rp = main._ts_trong_brain(broot, cand) if cand else None
            if not rp:
                continue
            files.setdefault(os.path.normcase(str(rp)), {"p": rp, "label": tg["nhan"], "image": tg["hinh"], "ts": ts})["ts"] = ts
        for raw in channel_context.extract_paths(text):
            rp = main._ts_trong_brain(broot, Path(raw))
            if not rp or not rp.is_file():
                continue
            files.setdefault(os.path.normcase(str(rp)), {"p": rp, "label": "", "image": False, "ts": ts})["ts"] = ts
        for u in channel_context.extract_urls(text):
            links.setdefault(u, {"url": u, "ts": ts, "vai": m.get("role") or ""})
    out_files = sorted(({"name": v["p"].name, "label": v["label"], "image": v["image"], "exists": v["p"].is_file(),
                         "ts": v["ts"]} for v in files.values()), key=lambda x: x["ts"], reverse=True)
    out_links = sorted(links.values(), key=lambda x: x["ts"], reverse=True)
    return out_files, out_links


def new_way(sid):
    d = c.get(f"/sessions/{sid}/assets").json()
    return ([{k: f[k] for k in ("name", "label", "image", "exists", "ts")} for f in d["files"]],
            [{k: l[k] for k in ("url", "ts", "vai")} for l in d["links"]])


def same(sid, name):
    a, b = old_way(sid), new_way(sid)
    check(name, a == b, {"old": a, "new": b})


random.seed(7)
PIECES = [
    "Xong rồi anh: [Kế hoạch](docs/plan.md) và ![banner](docs/price.md)",
    "File ở `" + str(broot / "docs" / "price.md") + "` nhé, xem thêm https://example.com/a.",
    "Bản cũ [đã dời](docs/moved.md), ngoài brain /etc/passwd, giả định `" + str(broot / "docs" / "nope.md") + "`",
    "Tham khảo https://example.com/b và https://example.com/a",
    "Anh xem `" + str(broot / "docs" / "plan.md") + "` rồi [bảng giá](docs/price.md)",
    "Không có gì để nhắc ở tin này.",
    "Sẽ tạo sau: `" + str(broot / "docs" / "soon.md") + "` và [file muộn](docs/late.md)",
]


def say(sid, k):
    st.append_message(sid, "user" if k % 3 == 0 else "assistant", random.choice(PIECES) + f" (tin {k})")


SID = "team-long"
st.get_or_create(SID, brain=BRAIN, engine="cli", model="x")
for k in range(40):
    say(SID, k)

scan.forget()
before = scan.stats()
same(SID, "the first read gives the same files and links as reading everything")
check("and it was one full read", scan.stats()["full"] == before["full"] + 1, scan.stats())

# ---- nothing new: no message is read again -----------------------------------------------------------------------
calls = []
real_after = st.messages_after
st.messages_after = lambda *a, **k: (calls.append(a), real_after(*a, **k))[1]
try:
    hits = scan.stats()["hits"]
    new_way(SID)
    new_way(SID)
    check("an open with nothing new reads no message", calls == [], calls)
    check("and counts as a hit", scan.stats()["hits"] == hits + 2, scan.stats())

    # ---- new messages: only they are read ---------------------------------------------------------------------------
    last_id = st.messages_fingerprint(SID)[1]
    for k in range(40, 46):
        say(SID, k)
    same(SID, "after new messages the answer is still the same as reading everything")
    check("only the new messages were read", len(calls) == 1 and calls[0][1] == last_id, calls)
finally:
    st.messages_after = real_after

# ---- whether a file exists is the truth of now, not of the scan ---------------------------------------------------
(broot / "docs" / "soon.md").write_text("made after its message", encoding="utf-8")
same(SID, "a bare path whose file is made later shows up without a new message")
check("the file made later is listed", any(f["name"] == "soon.md" for f in new_way(SID)[0]))
(broot / "docs" / "late.md").unlink()
(broot / "docs" / "soon.md").unlink()
same(SID, "a deleted file: the linked one stays as missing, the bare one leaves")
got = {f["name"]: f for f in new_way(SID)[0]}
check("linked and deleted stays, marked missing", got.get("late.md", {}).get("exists") is False, got)
check("bare and deleted leaves the list", "soon.md" not in got, got)

# ---- an edit, a delete, a rewind: read again from the start -------------------------------------------------------
full = scan.stats()["full"]
st.append_message(SID, "assistant", "Tin cuối: [một file](docs/plan.md) https://example.com/last")
same(SID, "before the edit")
check("the last message is edited in place", st.replace_last_message(SID, "assistant", "Đã sửa: https://example.com/edited"))
same(SID, "an edited message: its old link is gone, its new one is there")
check("the edit caused a full read", scan.stats()["full"] == full + 1, scan.stats())
urls = [l["url"] for l in new_way(SID)[1]]
check("old link gone, new link there", "https://example.com/last" not in urls and "https://example.com/edited" in urls, urls)

ids = [m["id"] for m in st.get_messages(SID)]
st.rewind_from(SID, ids[len(ids) // 2])
same(SID, "after a rewind the answer matches what is left")

# ---- a second conversation does not mix with the first, and the store is bounded ---------------------------------
st.get_or_create("other", brain=BRAIN, engine="cli", model="x")
st.append_message("other", "assistant", "Chỉ có https://example.com/other")
same("other", "another conversation has its own list")
same(SID, "and the first one is unchanged")
for i in range(scan.MAX_SESSIONS + 5):
    sid = f"many-{i}"
    st.get_or_create(sid, brain=BRAIN, engine="cli", model="x")
    st.append_message(sid, "assistant", f"https://example.com/{i}")
    new_way(sid)
check("kept conversations are bounded", scan.stats()["sessions"] <= scan.MAX_SESSIONS, scan.stats())

print("")
if fails:
    print(f"RED: {len(fails)}")
    sys.exit(1)
print("All green.")
