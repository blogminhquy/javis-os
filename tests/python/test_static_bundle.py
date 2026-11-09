"""Startup scripts as one bundle, minified output kept on disk, gzip made once (2026-11-09).

    python tests/run.py static_bundle      (no network)

The owner measured a slow first open of the Partners page: ~110 separate script requests at page load, and after every
restart the pure Python minifier re-ran over all files while holding the GIL. These pin: which tags are bundled, that
the bundle keeps order and isolates a broken file (the inline fallback), the line table used by error reports, the
javis-fresh swap, and the disk cache that makes a restart skip the minifier."""
from _paths import ROOT, SERVER  # noqa: E402,F401
import ast
import gzip
import json
import subprocess
import shutil
from pathlib import Path

import static_bundle
import tinh_gon


def _page(*tags: str) -> str:
    return "<html><head></head><body>\n" + "\n".join(tags) + "\n</body></html>"


def _tag(rel: str, crc: str) -> str:
    return f'<script src="/static/{rel}?v={crc}"></script>'


def _dash(tmp_path: Path, files: dict) -> Path:
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path


def _crc(d: Path, rel: str) -> str:
    return tinh_gon.ban_phuc_vu(d / rel, rel)[1]


def test_runs_break_only_on_scripts_that_execute_in_place():
    html = _page(
        _tag("a.js", "1"), _tag("b.js", "2"),
        '<script>window.x = 1;</script>',                    # inline code: breaks
        _tag("c.js", "3"),
        '<script id="javis-lazy" type="application/json">{"g": []}</script>',   # data block: does not break
        '<!-- <script>commented out</script> -->',          # comment: ignored
        '<script src="/static/m.js?v=4" defer></script>',   # defer: does not run in place
        _tag("d.js", "5"),
        '<script src="/static/freshness.js"></script>',     # no ?v=: kept apart, breaks
        _tag("e.js", "6"))
    runs = [[r[2] for r in run] for run in static_bundle.find_runs(html)]
    assert runs == [["a.js", "b.js"], ["c.js", "d.js"]]    # a lone e.js is not worth a bundle


def test_apply_replaces_a_run_with_one_tag_at_its_last_place(tmp_path, monkeypatch):
    monkeypatch.setenv("JAVIS_BUNDLE", "1")
    d = _dash(tmp_path, {"a.js": "var A = 1;\n", "b.js": "// note\nvar B = A + 1;\n", "c.js": "var C = 3;"})
    html = _page(_tag("a.js", _crc(d, "a.js")), "<div id=x></div>", _tag("b.js", _crc(d, "b.js")),
                 '<script>inline()</script>', _tag("c.js", _crc(d, "c.js")))
    out, fresh = static_bundle.apply(html, d)
    assert "a.js?v=" not in out.split("<script>(function(i,L)")[0]     # only the fallback list still names it
    assert out.index("<div id=x></div>") < out.index("/static/_bundle/")    # placed where b.js stood
    assert out.index("/static/_bundle/") < out.index("<script>inline()</script>")
    assert _tag("c.js", _crc(d, "c.js")) in out                           # single file after the inline script
    names = [k for k, v in fresh.items() if v]
    assert len(names) == 1 and names[0].startswith("_bundle/")
    assert fresh["a.js"] is None and fresh["b.js"] is None and "c.js" not in fresh
    data, gz, crc = static_bundle.get(names[0])
    assert fresh[names[0]] == crc and gzip.decompress(gz) == data
    assert f"/static/{names[0]}?v={crc}" in out


def test_a_file_changed_since_its_fingerprint_keeps_its_run_unbundled(tmp_path, monkeypatch):
    monkeypatch.setenv("JAVIS_BUNDLE", "1")
    d = _dash(tmp_path, {"a.js": "var A = 1;\n", "b.js": "var B = 2;\n"})
    html = _page(_tag("a.js", "00000000"), _tag("b.js", _crc(d, "b.js")))
    out, fresh = static_bundle.apply(html, d)
    assert out == html and fresh == {}


def test_switch_off(tmp_path, monkeypatch):
    monkeypatch.setenv("JAVIS_BUNDLE", "0")
    d = _dash(tmp_path, {"a.js": "var A=1;", "b.js": "var B=2;"})
    html = _page(_tag("a.js", _crc(d, "a.js")), _tag("b.js", _crc(d, "b.js")))
    assert static_bundle.apply(html, d) == (html, {})


def test_bundle_counts_files_and_maps_lines_back():
    files = [("a.js", b"var a = 1;\nvar a2 = 2;\n"), ("b.js", b"// no trailing newline\nvar b = 3;"),
             ("c.js", b"'use strict';\nvar c = 4;\n")]
    data, crc, ident, table = static_bundle.build(files)
    lines = data.decode().split("\n")
    # The counter comes first, so no file's "use strict" can become the bundle's directive prologue.
    assert lines[0].startswith("window.__javisBundle=")
    for start, rel in table:
        src = dict(files)[rel].decode().splitlines()
        assert lines[start - 1:start - 1 + len(src)] == src, rel
    assert data.decode().rstrip().endswith(f'window.__javisBundle["{ident}"]=3;')


def test_bundle_and_fallback_behave_like_separate_files(tmp_path):
    """Run the bundle and its inline fallback in node: a file that throws costs only itself, a bundle that never ran
    (syntax error, missing) loads every file, a clean run loads none."""
    node = shutil.which("node")
    if not node:
        return
    files = [("a.js", b"log.push('a');\n"), ("b.js", b"log.push('b'); throw new Error('boom');\n"),
             ("c.js", b"log.push('c');\n")]
    data, _crc, ident, _t = static_bundle.build(files)
    fb = static_bundle._fallback(ident, ["/a.js", "/b.js", "/c.js"])
    inline = fb[len("<script>"):-len("</script>")]
    script = f"""
const vm = require('vm');
function run(bundle) {{
  const written = [], log = [];
  const ctx = {{ log, document: {{ write: s => written.push(/src="([^"]+)"/.exec(s)[1]) }} }};
  ctx.window = ctx;
  vm.createContext(ctx);
  if (bundle !== null) {{ try {{ vm.runInContext(bundle, ctx); }} catch (e) {{}} }}
  vm.runInContext({json.dumps(inline)}, ctx);
  return {{ log, written }};
}}
const bundle = {json.dumps(data.decode())};
console.log(JSON.stringify([run(bundle), run(null), run(bundle.replace("throw new Error('boom');", ""))]));
"""
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    thrown, missing, clean = json.loads(out.stdout)
    assert thrown == {"log": ["a", "b"], "written": ["/c.js"]}
    assert missing == {"log": [], "written": ["/a.js", "/b.js", "/c.js"]}
    assert clean == {"log": ["a", "b", "c"], "written": []}


def test_minified_output_survives_a_restart_and_unused_entries_are_pruned(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    d = _dash(tmp_path / "dash", {"x.js": "// comment\nvar x = 1;\n", "y.css": "/* c */ a { color: red; }"})
    monkeypatch.setattr(tinh_gon, "_DISK_USED", set())
    tinh_gon.set_cache_dir(cache)
    try:
        first = tinh_gon.ban_phuc_vu(d / "x.js", "x.js")
        tinh_gon.ban_phuc_vu(d / "y.css", "y.css")
        assert len(list(cache.iterdir())) == 2
        (cache / "stale.js").write_bytes(b"old")
        # A restart: memory caches empty, the minifier must not run again.
        tinh_gon._NHO.clear()
        monkeypatch.setattr(tinh_gon, "_DISK_USED", set())

        def boom(*_a):
            raise AssertionError("minified again")
        monkeypatch.setattr(tinh_gon, "nen_js", boom)
        monkeypatch.setattr(tinh_gon, "nen_css", boom)
        assert tinh_gon.ban_phuc_vu(d / "x.js", "x.js") == first
        tinh_gon.ban_phuc_vu(d / "y.css", "y.css")
        assert tinh_gon.prune_disk_cache() == 1 and not (cache / "stale.js").exists()
        data, gz, crc = tinh_gon.gzip_of(d / "x.js", "x.js")
        assert (data, crc) == first and gzip.decompress(gz) == data
    finally:
        tinh_gon._DISK_DIR = None
        tinh_gon._NHO.clear()


def test_main_wires_the_bundle_the_warm_up_and_the_precompressed_files():
    src = (SERVER / "main.py").read_text(encoding="utf-8")
    root = src.split("async def root()", 1)[1].split("\n@app.", 1)[0]
    assert "to_thread(static_bundle.apply, html, DASHBOARD_PATH)" in root
    assert root.index("static_bundle.apply") < root.index('id="javis-fresh"')
    assert "tinh_gon.set_cache_dir(" in src and "static_bundle.warm" in src
    assert "static_bundle.get(rel)" in src and "tinh_gon.gzip_of" in src


def _handler(path: Path, name: str):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(name)


def test_partners_page_reads_leave_the_event_loop():
    """Reads the Partners page fires at open that touch files or SQLite: plain `def`, so FastAPI runs them on a worker
    thread instead of the event loop that every other request (static files included) waits on."""
    assert isinstance(_handler(SERVER / "resonance_api.py", "resonance_agents"), ast.FunctionDef)
    for name in ("background_active", "inbox_list", "vault_check", "list_workflows", "voice_call_route",
                 "voice_ear_route", "pet_menu_get", "ui_order_get", "notifications_read_get"):
        assert isinstance(_handler(SERVER / "main.py", name), ast.FunctionDef), name
    nen = (SERVER / "nen_phan_hoi.py").read_text(encoding="utf-8")
    assert "await asyncio.to_thread(gzip.compress" in nen
    graph = (SERVER / "routes" / "graph.py").read_text(encoding="utf-8")
    assert "await asyncio.to_thread(json.dumps" in graph


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
