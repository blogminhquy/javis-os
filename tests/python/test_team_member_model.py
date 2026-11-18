"""The Team tab shows the model each member runs on (owner, 18/11/2026).

    python tests/run.py team_member_model -v

Owner: "trong team nhìn được model của các thành viên, như vậy sẽ dễ kiểm soát hơn". The team meta carries the model a
team turn picks first (the assistant's own, else the main model), and member_views passes it on only while the
assistant's file is confirmed as that member. Real TeamStore on temporary SQLite, fake registry, no model is called.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import tempfile
from pathlib import Path

import team_api  # noqa: E402
import team_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


class Registry:
    def __init__(self, rows):
        self.rows = rows

    def agents_by_keys(self, root, keys):
        return {k: self.rows.get(k) for k in keys}


d = Path(tempfile.mkdtemp(prefix="javis-team-model-"))
root = str(d)
META = [
    {"slug": "an", "name": "An", "provider": "anthropic-cli", "avatar": None, "title": "",
     "model": "claude-opus-5-5", "model_label": "Claude Code", "model_main": False},
    {"slug": "duy", "name": "Duy", "provider": "openai-oauth", "avatar": None, "title": "",
     "model": "gpt-5.5", "model_label": "ChatGPT", "model_main": True},
    {"slug": "mai", "name": "Mai", "provider": "anthropic-cli", "avatar": None, "title": "",
     "model": "claude-sonnet-5-5", "model_label": "Claude Code", "model_main": False},
]
reg = Registry({"k_an": {"slug": "an", "status": "active"}, "k_duy": {"slug": "duy", "status": "active"},
                "k_mai": {"slug": "mai", "status": "missing"}})
api = team_api.TeamApi(team_api.TeamApiDeps(
    brain_key=lambda b: root, session_store=lambda: None, task_store=lambda: None, resonance_store=lambda: reg,
    agents_meta=lambda r: META, agent_info=lambda r, k: None, engine_for=lambda *a: None))
api._teams = team_store.TeamStore(d / "team.sqlite3")
tid = team_store.new_team_id()
api._teams.create_team(root, "Blog", "", "sess-1", team_id=tid)
for k, slug in (("k_an", "an"), ("k_duy", "duy"), ("k_mai", "mai")):
    api._teams.add_member(tid, k, slug)

views = {m["agent_key"]: m for m in api.member_views(api._teams.get(tid))}
check("an assistant with its own model: engine, model, not the main one",
      views["k_an"]["model"] == {"model": "claude-opus-5-5", "label": "Claude Code", "main": False}, views["k_an"])
check("an assistant without a model of its own follows the main model, and says so",
      views["k_duy"]["model"] == {"model": "gpt-5.5", "label": "ChatGPT", "main": True}, views["k_duy"])
check("a member whose file is not confirmed as it shows no model (it could be another assistant's)",
      views["k_mai"]["model"] is None, views["k_mai"])

src = (SERVER / "main.py").read_text(encoding="utf-8")
meta = src.split("def _resonance_agents_meta(root):", 1)[1].split("\ndef ", 1)[0]
check("the team meta gives the model a team turn picks first: the assistant's own, else the main model",
      '"model": own or main_model' in meta and '"model_main": not own' in meta
      and 'main_model = str(_effective_main({"model": mcfg}).get("model") or "")' in meta
      and '"model_label": str((_provider_def(prov) or {}).get("label") or prov)' in meta, meta[:600])

if fails:
    raise SystemExit(f"\nFAILED {len(fails)}")
print("\nALL OK")
