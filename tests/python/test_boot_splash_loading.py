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


def test_new_texts_in_both_languages():
    for lang in ("vi", "en"):
        d = json.loads((DASH / "i18n" / ("%s.json" % lang)).read_text(encoding="utf-8"))
        assert d.get("boot.starting") and d.get("boot.just_started"), lang


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
