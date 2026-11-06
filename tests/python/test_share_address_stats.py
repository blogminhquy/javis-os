"""Share links: custom address (slug) and the view counter.

    python tests/run.py share_address_stats

Owner, 2026-11-06: besides renaming a link, change the address after /s/, and count the views of every link. Checks:
the slug opens the link while the random token keeps working, a taken or too short slug changes nothing, revoking
kills both, and a view counts once per visit, never for a link-preview bot, a prefetch, an asset or the owner.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import tempfile

_STATE = tempfile.mkdtemp(prefix="javis-share-addr-")
_BRAINS = tempfile.mkdtemp(prefix="javis-share-addr-brains-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["BRAINS_DIR"] = _BRAINS

BRAIN = os.path.join(_BRAINS, "brain")
os.makedirs(os.path.join(BRAIN, "apps", "demo"), exist_ok=True)
os.makedirs(os.path.join(BRAIN, "notes"), exist_ok=True)
with open(os.path.join(BRAIN, "apps", "demo", "index.html"), "w", encoding="utf-8") as f:
    f.write("<!doctype html><title>Demo app</title><script>fetch('data.json')</script>")
with open(os.path.join(BRAIN, "apps", "demo", "data.json"), "w", encoding="utf-8") as f:
    f.write('{"a": 1}')
with open(os.path.join(BRAIN, "notes", "ke-hoach.md"), "w", encoding="utf-8") as f:
    f.write("# Kế hoạch\n\nchữ")

import share_stats  # noqa: E402
import share_store  # noqa: E402
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

cl = TestClient(main.app, base_url="http://127.0.0.1")
_fails = []

BROWSER = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"}
BROWSER2 = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/140.0 Safari/537.36"}


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


# ---- 1. slugify ----
check("slugify strips Vietnamese marks and punctuation",
      share_store.slugify("  Đường dẫn: Vibecode Javis!! ") == "duong-dan-vibecode-javis")
check("slugify caps the length", len(share_store.slugify("a" * 200)) == share_store.SLUG_MAX)

# ---- 2. custom address through the dashboard route ----
app_link = cl.post("/share/create", json={"brain": BRAIN, "path": "apps/demo/index.html"}).json()
note_link = cl.post("/share/create", json={"brain": BRAIN, "path": "notes/ke-hoach.md"}).json()
tok = app_link["token"]
r = cl.post("/share/rename", json={"token": tok, "nhan": "Demo", "slug": "Vibecode Javis"}).json()
check("rename sets name and address together", r.get("ok") and r.get("slug") == "vibecode-javis"
      and r.get("url") == "/s/vibecode-javis" and r.get("ten") == "Demo", r)

g = cl.get("/s/vibecode-javis", follow_redirects=False)
check(".html via the slug redirects to the slug with a trailing slash, not to the token",
      g.status_code == 307 and g.headers.get("location") == "/s/vibecode-javis/", (g.status_code, g.headers.get("location")))
check("the slug serves the page", cl.get("/s/vibecode-javis/").status_code == 200)
check("the slug is case-insensitive", cl.get("/s/Vibecode-Javis/").status_code == 200)
check("files next to the page load through the slug", cl.get("/s/vibecode-javis/data.json").json() == {"a": 1})
check("the random token keeps working (links already sent do not break)", cl.get("/s/" + tok + "/").status_code == 200)
of = cl.get("/share/of", params={"brain": BRAIN, "path": "apps/demo/index.html"}).json()
check("the editor's Share button hands out the slug address", of["share"]["path"] == "/s/vibecode-javis", of)
again = cl.post("/share/create", json={"brain": BRAIN, "path": "apps/demo/index.html"}).json()
check("sharing the same file again returns the slug address", again["path"] == "/s/vibecode-javis", again)

taken = cl.post("/share/rename", json={"token": note_link["token"], "nhan": "Khác", "slug": "vibecode-javis"}).json()
check("a taken address is refused", taken.get("ok") is False and taken.get("field") == "slug", taken)
check("and the refused call changed nothing (name untouched)",
      share_store.get(note_link["token"]).get("nhan") != "Khác" and not share_store.get(note_link["token"]).get("slug"))
_d = share_store._read_raw()
_d["plain-token-abc"] = {"brain": BRAIN, "path": "notes/khac.md", "nhan": "", "tao_luc": 1}
share_store._write_raw(_d)
taken2 = cl.post("/share/rename", json={"token": note_link["token"], "slug": "Plain-Token-ABC"}).json()
share_store.remove("plain-token-abc")
check("an address equal to another link's random token is refused", taken2.get("ok") is False, taken2)
short = cl.post("/share/rename", json={"token": note_link["token"], "slug": "a!"}).json()
check("an address under 3 letters is refused", short.get("ok") is False and short.get("field") == "slug", short)
only_slug = cl.post("/share/rename", json={"token": note_link["token"], "slug": "ke-hoach-q4"}).json()
check("changing only the address keeps the name", only_slug.get("ok") and only_slug.get("slug") == "ke-hoach-q4"
      and share_store.get(note_link["token"]).get("nhan") == only_slug.get("nhan"), only_slug)

cl.post("/share/rename", json={"token": tok, "slug": "demo-moi"})
check("changing the address frees the old one", cl.get("/s/vibecode-javis/").status_code == 404
      and cl.get("/s/demo-moi/").status_code == 200)
cl.post("/share/rename", json={"token": tok, "slug": ""})
check("clearing the address leaves only the token", cl.get("/s/demo-moi/").status_code == 404
      and cl.get("/s/" + tok + "/").status_code == 200 and not share_store.get(tok).get("slug"))
lst = {x["token"]: x for x in cl.get("/share/list").json()["items"]}
check("the list carries slug, address and token address", lst[note_link["token"]]["url"] == "/s/ke-hoach-q4"
      and lst[note_link["token"]]["slug"] == "ke-hoach-q4" and lst[note_link["token"]]["token_url"] == "/s/" + note_link["token"])

# ---- 3. view counter ----
ntok = note_link["token"]
share_stats.forget(tok)                # section 2 opened it with the test client's own agent
share_stats.forget(ntok)


def views(t):
    return share_stats.summary(t)["views"]


check("a new link starts at zero", views(ntok) == 0)
cl.get("/s/ke-hoach-q4", headers=BROWSER)
check("opening the link counts one view", views(ntok) == 1, views(ntok))
cl.get("/s/ke-hoach-q4", headers=BROWSER)
cl.get("/s/" + ntok, headers=BROWSER)
check("reloading within the same visit does not count again", views(ntok) == 1, views(ntok))
cl.get("/s/ke-hoach-q4", headers=BROWSER2)
s = share_stats.summary(ntok)
check("another reader counts a view and a visitor", s["views"] == 2 and s["visitors"] == 2, s)
for ua in ("TelegramBot (like TwitterBot)", "facebookexternalhit/1.1", "Mozilla/5.0 (compatible; Discordbot/2.0)",
           "WhatsApp/2.23", "Slackbot-LinkExpanding 1.0", "curl/8.4", ""):
    cl.get("/s/ke-hoach-q4", headers={"User-Agent": ua})
check("link-preview bots, scripts and empty agents do not count", views(ntok) == 2, views(ntok))
cl.get("/s/ke-hoach-q4", headers=dict(BROWSER, **{"User-Agent": "Mozilla/5.0 Firefox/150", "Sec-Purpose": "prefetch"}))
check("a browser prefetch does not count", views(ntok) == 2, views(ntok))

atok = tok
cl.get("/s/" + atok, headers=BROWSER, follow_redirects=False)  # 307 to the trailing slash: not a view yet
check("the redirect hop is not a view", views(atok) == 0, views(atok))
cl.get("/s/" + atok + "/", headers=BROWSER)
cl.get("/s/" + atok + "/data.json", headers=BROWSER2)
cl.get("/s/" + atok + "/raw", headers=BROWSER2)
check("the page counts, its data file and /raw do not", views(atok) == 1, views(atok))

# owner: a valid dashboard session is not a reader
real_gate, real_valid = main.cfgmod.gate_active, main.cfgmod.valid_session
main.cfgmod.gate_active = lambda: True
main.cfgmod.valid_session = lambda tok_: tok_ == "owner-session"
try:
    cl.cookies.set("javis_session", "owner-session")
    cl.get("/s/" + atok + "/", headers={"User-Agent": "Mozilla/5.0 Owner/1"})
    check("the owner opening their own link does not count", views(atok) == 1, views(atok))
    cl.cookies.clear()
finally:
    main.cfgmod.gate_active, main.cfgmod.valid_session = real_gate, real_valid

# visit window and the 14-day chart
t0 = 1_800_000_000.0
check("same visitor 10 minutes later: same visit", share_stats.record_view("x", "v1", t0)
      and not share_stats.record_view("x", "v1", t0 + 600))
check("same visitor 2 hours later: a new view, not a new visitor", share_stats.record_view("x", "v1", t0 + 7200)
      and share_stats.summary("x", t0 + 7200)["visitors"] == 1 and share_stats.summary("x", t0 + 7200)["views"] == 2)
share_stats.record_view("x", "v2", t0 - 3 * 86400)
sm = share_stats.summary("x", t0 + 7200)
check("chart is 14 days, oldest first, today last", len(sm["days"]) == 14 and sm["days"][-1] == 2, sm["days"])
check("the last 7 days sum the chart's tail", sm["week"] == 3, sm)
share_stats.record_view("x", "v3", t0 + 90 * 86400)
check("days older than the keep window are dropped",
      all(k >= share_stats._day(t0 + 30 * 86400) for k in share_stats._data["links"]["x"]["days"]))

lst = {x["token"]: x for x in cl.get("/share/list").json()["items"]}
check("the list reports each link's views", lst[ntok]["stats"]["views"] == 2 and lst[atok]["stats"]["views"] == 1, lst[ntok]["stats"])

# persisted without raw addresses or browsers
share_stats._flush()
raw = open(share_stats.STORE, encoding="utf-8").read()
check("counts are written to disk", json.loads(raw)["links"][ntok]["views"] == 2)
check("no raw address or browser string is stored", "testclient" not in raw and "iPhone" not in raw and "Chrome" not in raw)

# ---- 4. QR code (owner, 2026-11-06: "thêm mã QR cho từng link") ----
import segno  # noqa: E402
q = cl.get("/share/qr", params={"token": ntok, "origin": "https://share.example"})
check("QR comes back as an SVG image", q.status_code == 200 and q.headers["content-type"].startswith("image/svg+xml")
      and q.text.lstrip().startswith(("<?xml", "<svg")), q.status_code)
want = segno.make("https://share.example/s/ke-hoach-q4", error="m")
check("it encodes origin + the link's current address (the slug)", want.version > 0 and q.content == (lambda b: (
    want.save(b, kind="svg", scale=8, border=4, dark="#111", light="#fff"), b.getvalue())[1])(__import__("io").BytesIO()))
p = cl.get("/share/qr", params={"token": ntok, "origin": "https://share.example/", "fmt": "png", "dl": 1})
check("PNG download with a readable file name", p.status_code == 200 and p.content[:8] == b"\x89PNG\r\n\x1a\n"
      and 'filename="qr-' in p.headers.get("content-disposition", ""), p.headers.get("content-disposition"))
check("a forged origin is refused", cl.get("/share/qr", params={"token": ntok, "origin": "javascript:alert(1)"}).status_code == 400
      and cl.get("/share/qr", params={"token": ntok, "origin": "https://a.example/x?y"}).status_code == 400)
check("an unknown token is 404", cl.get("/share/qr", params={"token": "nope", "origin": "https://a.example"}).status_code == 404)
check("only the random token, not the slug, addresses the QR route",
      cl.get("/share/qr", params={"token": "ke-hoach-q4", "origin": "https://a.example"}).status_code == 404)
check("drawing a QR is not a view", views(ntok) == 2, views(ntok))

cl.post("/share/revoke", json={"token": ntok})
check("revoking kills the address too", cl.get("/s/ke-hoach-q4").status_code == 404 and cl.get("/s/" + ntok).status_code == 404)
check("and drops its counts", share_stats.summary(ntok)["views"] == 0)

print("\nFAIL: " + ", ".join(_fails) if _fails else "\nTat ca OK")
raise SystemExit(1 if _fails else 0)
