"""Start-up screen, one "Loading..." look everywhere, graph counts only on the graph (2026-11-09).

    python tests/run.py boot_splash_loading      (no network; node for the pure helpers)

Owner: a start-up screen until the whole interface is ready (most slow spots after an update sit in the first minute),
the Partners page's loading effect on every screen that waits, and the "N notes, M links" counts only on the neural
graph screen."""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import re
import shutil
import subprocess

DASH = ROOT / "dashboard"


def _read(name):
    return (DASH / name).read_text(encoding="utf-8")


def test_splash_is_in_the_page_from_the_first_paint_and_hides_after_the_first_page():
    html = _read("index.html")
    body = html.split("<body>", 1)[1]
    assert body.index('id="bootSplash"') < body.index('<div class="hud">')     # before anything else on screen
    assert 'data-i18n="boot.starting"' in body and 'id="bootSub" data-i18n="boot.just_started" hidden' in body
    assert html.index("/static/i18n/index.js") < html.index("/static/boot-splash.js")
    con = _read("console.js")
    assert re.search(r"khoiPhucTrang\(\);\s*\n\s*//[^\n]*\n\s*try \{ if \(window\.JavisBoot\) window\.JavisBoot\.pageStarted\(\); \}", con)
    root = (SERVER / "main.py").read_text(encoding="utf-8").split("async def root()", 1)[1].split("\n@app.", 1)[0]
    assert '"up": int(time.time() - _PROCESS_STARTED)' in root


def test_splash_helpers():
    node = shutil.which("node")
    if not node:
        return
    js = ("const b=require(%s);console.log(JSON.stringify([b.justStarted({up:30}),b.justStarted({up:500}),"
          "b.justStarted({}),b.loaderVisible([{getClientRects:()=>[1],closest:()=>null}]),"
          "b.loaderVisible([{getClientRects:()=>[],closest:()=>null}]),"
          "b.loaderVisible([{getClientRects:()=>[1],closest:()=>({})}]),b.MAX_MS<=15000]))") % json.dumps(str(DASH / "boot-splash.js"))
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    # just restarted, long up, no info, a visible loader, a hidden one, one inside the splash itself, a cap.
    assert json.loads(out.stdout) == [True, False, False, True, False, False, True]


def test_waiting_screens_share_the_loading_look():
    con = _read("console.js")
    assert 'ic("loader", { cls: "ic-xl ic-spin" })}</div><div>${esc(t("common.loading"))}' not in con
    assert con.count('<div class="pg-loading pg-page">') >= 9
    lazy = con.split("const nhomCan = NHOM_TRANG[id];", 1)[1].split("await window.JavisNapCham.cho(nhomCan);", 1)[0]
    assert "placeholder(" not in lazy and "pg-loading pg-page" in lazy          # not "<page> - in development"
    # A container that keeps living after its data arrives holds the loading line INSIDE it, so no spinner stays.
    for k in ("lnChat", "lnReview", "lnLog"):
        assert '<div id="%s"><div class="pg-loading">' % k in con
    assert '<div id="fmList" class="fm-list"><div class="pg-loading">' in con
    assert '<div class="sk3-md" id="skMd"><div class="pg-loading">' in _read("studio.js")
    assert '<div class="cb-log-body"><div class="pg-loading">' in _read("chatbots.js")
    assert '<div class="cb-rp-body"><div class="pg-loading">' in _read("chatbots-reply-policy.js")
    css = _read("console.css")
    assert ".pg-loading::before" in css and ".pg-loading.pg-page {" in css and ".boot-splash {" in css


def test_graph_counts_show_only_on_the_graph_screen():
    assert "body.in-console .graph-stats { display: none; }" in _read("style.css")
    assert 'document.body.classList.toggle("in-console", id !== "home");' in _read("console.js")


def test_graph_counts_sit_inside_the_graph_not_the_top_bar():
    """2026-11-09, owner: the Node / Link counter leaves the top bar and shows inside the graph."""
    html = _read("index.html")
    assert html.count('id="graphStats"') == 1
    top_bar = html.split('<header class="hud-top">', 1)[1].split("</header>", 1)[0]
    assert 'id="graphStats"' not in top_bar
    center = html.split('<div class="hud-center">', 1)[1].split('<div class="note-editor"', 1)[0]
    assert '<span class="graph-stats" id="graphStats">' in center
    css = _read("style.css")
    rule = css.split("\n.graph-stats {", 1)[1].split("}", 1)[0]
    assert "position: absolute;" in rule and "top: 14px; left: 14px;" in rule and "pointer-events: none;" in rule
    assert ".hud-center.brain-overlays-hidden .graph-stats {" in css     # the eye button hides it with the labels
    assert ".navbar-brain .graph-stats" not in _read("console.css")


def test_brain_picker_counts_stay_on_one_line():
    """2026-11-09, owner: "1920 Node · 2480 Link" on one line in each picker row, never split in two."""
    css = _read("style.css")
    rule = css.split("\n.bp-sub {", 1)[1].split("}", 1)[0]
    assert "white-space: nowrap;" in rule and "text-overflow: ellipsis;" in rule
    assert "flex-wrap: wrap" not in rule and ".bp-sub-part" not in css
    js = _read("brain-picker.js")
    assert "subHtml(" not in js and "bp-sub-part" not in js


def test_new_texts_in_both_languages():
    for lang in ("vi", "en"):
        d = json.loads((DASH / "i18n" / ("%s.json" % lang)).read_text(encoding="utf-8"))
        assert d.get("boot.starting") and d.get("boot.just_started"), lang


def test_brain_picker_counts_nodes_and_links_only_when_opened(tmp_path, monkeypatch):
    """The picker shows each brain's node and link counts as its graph shows them, asked when the picker opens."""
    import graph_builder as G
    monkeypatch.setenv("JAVIS_STATE_DIR", str(tmp_path / "state"))
    b = tmp_path / "brain"
    (b / "notes").mkdir(parents=True)
    (b / "notes" / "A.md").write_text("[[B]] [[C]] [[missing]]", encoding="utf-8")
    (b / "notes" / "B.md").write_text("[[A]]", encoding="utf-8")
    (b / "C.md").write_text("alone", encoding="utf-8")
    (b / ".hidden").mkdir()
    (b / ".hidden" / "D.md").write_text("[[A]]", encoding="utf-8")
    G._COUNTS.clear()
    got = G.graph_counts([str(b)])
    stats = G.graph_with_etag([str(b)], include_orphans=True)[1]["stats"]
    assert got == {"nodes": stats["total_notes"], "links": stats["total_links"], "capped": False} == \
        {"nodes": 3, "links": 2, "capped": False}
    assert G.graph_counts([str(b)], max_files=2)["capped"] is True
    js = _read("brain-picker.js")
    show = js.split("function show() {", 1)[1].split("\n  function close()", 1)[0]
    assert "askCounts(sel.value);" in show                     # asked when the picker opens...
    init = js.split("function show() {", 1)[0]
    assert "askCounts(" not in init.split("function askCounts(", 1)[0]   # ...and nowhere at page load
    assert '"/graph/counts?"' in js
    route = (SERVER / "routes" / "graph.py").read_text(encoding="utf-8")
    assert '@router.get("/graph/counts")' in route and "await asyncio.to_thread(_counts" in route
    # 2026-11-09, owner: "Node" and "Link", capitalised, instead of "node" and "liên kết".
    for lang, node, link in (("vi", "Node", "Link"), ("en", "Nodes", "Links")):
        d = json.loads((DASH / "i18n" / ("%s.json" % lang)).read_text(encoding="utf-8"))
        assert node in d["bpick.notes"] and node in d["bpick.graph"] and node in d["app.graph_stats"]
        assert link in d["bpick.graph"] and link in d["app.graph_stats"]
        assert "liên kết" not in d["bpick.graph"] + d["app.graph_stats"]


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
