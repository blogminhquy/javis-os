"""The archive of a team (Info tab, "See all") reads files and links one page at a time.

    python tests/run.py session_assets_pages

Owner, 19/11/2026: "phần file với link trong nhóm cần phân trang ... zalo nó làm xem tất cả này xong ấn vào thì nó vào
kho lưu trữ". The plain call of GET /sessions/{id}/assets stops at the newest 200 files and 200 links, so a team with
more had files the panel never showed. The archive asks one kind at a time (`kind`), with a search (`q`) and a page
(`offset`, `limit`), and reaches every row. The plain call also says the true totals (`counts`), so the headings of the
Info tab count every file, not only the ones it received.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-assetpages-"))

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
from sessions import get_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if not cond and extra else ""))
    if not cond:
        fails.append(name)


BRAIN = tempfile.mkdtemp(prefix="javis-brain-assetpages-")
broot = Path(BRAIN)
os.environ["JAVIS_FILES_ROOT"] = BRAIN       # the browse ceiling is the brain itself (see test_tai_san_gan_tay)
docs = broot / "docs"
docs.mkdir(parents=True, exist_ok=True)
N_DOCS, N_IMGS, N_LINKS = 230, 7, 215
for i in range(N_DOCS):
    (docs / f"bao-cao-{i:03d}.md").write_text("x", encoding="utf-8")
for i in range(N_IMGS):
    (docs / f"anh-{i}.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)
(docs / "Kế hoạch Việt.md").write_text("x", encoding="utf-8")

st = get_store()
SID = "cuoc-kho-luu-tru"
st.get_or_create(SID, brain=BRAIN, engine="cli", model="x")
# One message per file and link, so each has its own time: the older the index, the older the message.
for i in range(N_DOCS):
    st.append_message(SID, "assistant", f"Xong: [Báo cáo {i}](docs/bao-cao-{i:03d}.md)")
for i in range(N_IMGS):
    st.append_message(SID, "assistant", f"![ảnh {i}](docs/anh-{i}.png)")
for i in range(N_LINKS):
    st.append_message(SID, "assistant", f"Nguồn https://vd.vn/trang-{i:03d}")
st.append_message(SID, "assistant", "[Kế hoạch](docs/Kế hoạch Việt.md)")

c = TestClient(main.app, base_url="http://127.0.0.1")
API = f"/sessions/{SID}/assets"

# ---- the plain call: lists cut at 200 as before, counts are the true totals ----
d = c.get(API, params={"brain": BRAIN}).json()
check("the plain call still cuts each list at 200", len(d["files"]) == 200 and len(d["links"]) == 200,
      (len(d["files"]), len(d["links"])))
check("counts are the true totals, images apart from files",
      d.get("counts") == {"images": N_IMGS, "files": N_DOCS + 1, "links": N_LINKS}, d.get("counts"))

# ---- one kind a page at a time ----
p1 = c.get(API, params={"brain": BRAIN, "kind": "file", "limit": 20}).json()
check("a page of files: 20 rows, the total of every file", p1["total"] == N_DOCS + 1 and len(p1["items"]) == 20,
      (p1.get("total"), len(p1.get("items", []))))
check("files only, no picture in the files kind", all(not f["image"] for f in p1["items"]))
check("newest first", [f["ts"] for f in p1["items"]] == sorted([f["ts"] for f in p1["items"]], reverse=True))
check("the newest file is on the first page", p1["items"][0]["name"] == "Kế hoạch Việt.md", p1["items"][0]["name"])
last = c.get(API, params={"brain": BRAIN, "kind": "file", "offset": 220, "limit": 20}).json()
check("the last page reaches files the plain call never sent (beyond 200)",
      len(last["items"]) == N_DOCS + 1 - 220 and last["items"][-1]["name"] == "bao-cao-000.md",
      [f["name"] for f in last["items"]][-3:])
every = []
for off in range(0, N_DOCS + 1, 20):
    every += [f["name"] for f in c.get(API, params={"brain": BRAIN, "kind": "file", "offset": off, "limit": 20}).json()["items"]]
check("paging through gives every file once", len(every) == N_DOCS + 1 and len(set(every)) == N_DOCS + 1, len(every))

imgs = c.get(API, params={"brain": BRAIN, "kind": "image", "limit": 24}).json()
check("the image kind holds only pictures", imgs["total"] == N_IMGS and all(f["image"] for f in imgs["items"]), imgs.get("total"))
lk = c.get(API, params={"brain": BRAIN, "kind": "link", "offset": 200, "limit": 20}).json()
check("links page past 200 too", lk["total"] == N_LINKS and len(lk["items"]) == N_LINKS - 200
      and lk["items"][-1]["url"] == "https://vd.vn/trang-000", lk.get("items", [])[-1:])

# ---- search ----
s1 = c.get(API, params={"brain": BRAIN, "kind": "file", "q": "ke hoach viet"}).json()
check("search ignores accents and case, every word must match",
      s1["total"] == 1 and s1["items"][0]["name"] == "Kế hoạch Việt.md", s1)
s2 = c.get(API, params={"brain": BRAIN, "kind": "file", "q": "bao-cao-01"}).json()
check("search finds part of a name", s2["total"] == 10, s2.get("total"))
s3 = c.get(API, params={"brain": BRAIN, "kind": "link", "q": "trang-21"}).json()
check("links are searched by url", s3["total"] == 5, s3.get("total"))
check("nothing found is an empty page, not an error",
      c.get(API, params={"brain": BRAIN, "kind": "file", "q": "khong co gi"}).json()["total"] == 0)

# ---- bounds ----
big = c.get(API, params={"brain": BRAIN, "kind": "file", "limit": 5000}).json()
check("a page is at most 100 rows", len(big["items"]) == 100 and big["limit"] == 100, big.get("limit"))
neg = c.get(API, params={"brain": BRAIN, "kind": "file", "offset": -5, "limit": 0}).json()
check("a negative offset reads from the start, a zero limit reads one row", neg["offset"] == 0 and len(neg["items"]) == 1)
check("an unknown kind is refused", c.get(API, params={"brain": BRAIN, "kind": "video"}).status_code == 400)
check("no such conversation is 404", c.get("/sessions/khong-co/assets", params={"kind": "file"}).status_code == 404)

print("")
if fails:
    print(f"FAIL {len(fails)}")
    sys.exit(1)
print("OK test_session_assets_pages")
