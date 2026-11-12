"""Team chat opens an assistant's .html file inside the chat frame (2026-11-09), not in a new browser tab."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / "dashboard" / "teams.js").read_text(encoding="utf-8")
CSS = (ROOT / "dashboard" / "console.css").read_text(encoding="utf-8")


def test_file_chip_and_info_list_mark_html_links():
    assert JS.count("htmlAttr(") >= 3  # definition + chip + info list
    assert "a[data-tm-html]" in JS and "openHtmlSheet(" in JS


def test_sheet_renders_through_html_preview_and_lives_in_page():
    assert "JavisHtmlPreview" in JS and "HP.render(body, code, path, rawUrl)" in JS
    assert 'S.el.querySelector(".tm-page")' in JS
    assert ".tm-htmlsheet" in CSS


def test_modified_click_keeps_new_tab_and_i18n_keys_exist():
    assert "e.ctrlKey || e.metaKey" in JS
    for lang in ("vi", "en"):
        d = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        for k in ("teams.html_newtab", "teams.html_close", "teams.html_fail"):
            assert d.get(k), (lang, k)
