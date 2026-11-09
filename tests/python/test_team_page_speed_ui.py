"""Teams page: one registry query for the whole team list, "Loading" notes, Info tab by default (2026-11-09).

    python tests/run.py team_page_speed_ui      (no network)

The owner found the Partners and Teams pages slow to open and blank while loading. Measured with 15 teams: the team
list opened one SQLite connection per member of every team (225) to read the registry, 80% of its time; one batched
query took GET /teams from ~85 ms to ~33 ms. Measured too: opening a team takes the same time with 1,500 or 15,000
messages (paged, indexed reads)."""
from _paths import ROOT, SERVER  # noqa: E402,F401
import tempfile
from pathlib import Path


def test_agents_by_keys_reads_many_rows_in_one_connection(monkeypatch):
    import resonance_store as RS
    store = RS.GoalStore(Path(tempfile.mkdtemp()) / "r.sqlite3")
    owner = RS.Principal("owner", "owner", "/brain")
    keys = [store.agent_register(owner, slug)["agent_key"] for slug in ("lan", "minh", "hoa")]
    opened = []
    real = store._conn

    def counting():
        opened.append(1)
        return real()
    monkeypatch.setattr(store, "_conn", counting)
    rows = store.agents_by_keys("/brain", keys + ["ag_missing", ""])
    assert set(rows) == set(keys) and len(opened) == 1
    assert rows[keys[0]]["slug"] == "lan"
    assert store.agents_by_keys("/other-brain", keys) == {}          # another brain's keys stay out
    assert store.agents_by_keys("/brain", []) == {} and len(opened) == 2   # no key: no connection at all


def test_team_list_reads_the_registry_once_for_every_team():
    src = (SERVER / "team_api.py").read_text(encoding="utf-8")
    lst = src.split('@app.get("/teams")', 1)[1].split("@app.", 1)[0]
    assert lst.count("_regs_of(") == 1 and "api.faces(t, meta, mems[t[\"team_id\"]], regs)" in lst
    mv = src.split("def member_views(", 1)[1].split("\n    def ", 1)[0]
    assert "rs.agent_by_key(" not in mv and "_regs_of(rs, root, members)" in mv
    au = src.split("def authors(", 1)[1].split("\n    def ", 1)[0]
    assert "rs.agent_by_key(" not in au


def test_pages_say_loading_and_teams_open_on_the_info_tab():
    ws = (ROOT / "dashboard" / "workspace.js").read_text(encoding="utf-8")
    assert 'id="wsList">\' + dangTaiHtml("ws.loading_list")' in ws
    assert 'if (!daTai && !ds.length) { host.innerHTML = dangTaiHtml("ws.loading_list"); return; }' in ws
    tm = (ROOT / "dashboard" / "teams.js").read_text(encoding="utf-8")
    assert 'loadingHtml("teams.loading_list")' in tm and 'loadingHtml("teams.loading_chat")' in tm
    assert "S.msgsFor !== S.activeId" in tm
    open_team = tm.split("function openTeam(", 1)[1].split("\n  function ", 1)[0]
    assert "S.side = sideByDefault();" in open_team and 'if (S.side) S.tab = "info";' in open_team
    assert "rememberSide(false)" in tm.split("function closeSide(", 1)[1].split("\n  }", 1)[0]
    css = (ROOT / "dashboard" / "console.css").read_text(encoding="utf-8")
    assert ".pg-loading {" in css and ".ws-btn.tm-icon { width: 36px; height: 36px;" in css
    import json
    for lang in ("vi", "en"):
        d = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        for k in ("ws.loading_list", "ws.loading_chat", "teams.loading_list", "teams.loading_chat"):
            assert d.get(k), (lang, k)


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
