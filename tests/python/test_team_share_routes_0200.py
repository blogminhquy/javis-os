"""0.200.0: GET /teams/{id}/export and POST /teams/import through the real host (no model).

Run:
    python tests/run.py team_share_routes
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-share-")
BR = Path(tempfile.mkdtemp(prefix="javis-team-share-src-"))
BR2 = Path(tempfile.mkdtemp(prefix="javis-team-share-dst-"))
(BR / "agents").mkdir()
(BR / "skills" / "viet-email").mkdir(parents=True)
(BR / "skills" / "viet-email" / "SKILL.md").write_text("---\nname: viet-email\ngroup: Marketing\n---\nViết email.\n",
                                                       encoding="utf-8")
(BR / "agents" / "lan.md").write_text("---\nname: Lan\nrole: Marketing\nmodel: claude-opus\nskills:\n- viet-email\n---\n"
                                      "Key sk-ant-api03-SECRETSECRETSECRET.\n", encoding="utf-8")
(BR / "agents" / "minh.md").write_text("---\nname: Minh\nrole: Sales\n---\nBạn là Minh.\n", encoding="utf-8")
(BR2 / "agents").mkdir()
(BR2 / "agents" / "minh.md").write_text("---\nname: Minh của tôi\n---\nGiữ nguyên.\n", encoding="utf-8")

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


main._TEAM_API.deps.spawn = lambda job: None
c = TestClient(main.app, base_url="http://127.0.0.1:8080")
r = c.post(f"/teams?brain={BR}", json={"name": "Team Marketing", "description": "Chạy quảng cáo",
                                        "members": ["lan", "minh"], "leader_slug": "lan"})
check("team created", r.status_code == 200, r.text[:200])
tid = r.json()["team"]["team_id"]

r = c.get(f"/teams/{tid}/export?brain={BR}")
check("export answers a zip", r.status_code == 200 and r.headers["content-type"] == "application/zip", r.text[:200])
z = zipfile.ZipFile(io.BytesIO(r.content))
m = json.loads(z.read("javis-team.json"))
check("manifest names members and leader", sorted(m["members"]) == ["lan", "minh"] and m["leader"] == "lan" and m["name"] == "Team Marketing")
lan = z.read("agents/lan.md").decode()
check("partner file cleaned", "model:" not in lan and "SECRETSECRET" not in lan)
check("member skill included", "skills/viet-email/SKILL.md" in z.namelist())
check("unknown team refused", c.get(f"/teams/nope/export?brain={BR}").status_code == 404)

files = {"file": ("team.javis.zip", r.content, "application/zip")}
pv = c.post("/teams/import", data={"brain": str(BR2), "preview": "1"}, files=files)
check("preview lists the team", pv.status_code == 200 and sorted(pv.json().get("members") or []) == ["lan", "minh"], pv.text[:200])
check("preview writes nothing", not (BR2 / "agents" / "lan.md").exists())
got = c.post("/teams/import", data={"brain": str(BR2)}, files=files)
j = got.json()
check("import builds the team", got.status_code == 200 and j.get("ok") and j["team"]["name"] == "Team Marketing", got.text[:300])
check("new partner imported, existing kept", "agent:lan" in j["imported"] and "agent:minh" in j["kept"]
      and "Minh của tôi" in (BR2 / "agents" / "minh.md").read_text(encoding="utf-8"))
check("skill imported", (BR2 / "skills" / "viet-email" / "SKILL.md").is_file())
r2 = c.get(f"/teams?brain={BR2}")
check("team listed in the new brain", any(t["name"] == "Team Marketing" for t in r2.json().get("teams", [])))
bad = c.post("/teams/import", data={"brain": str(BR2)}, files={"file": ("x.zip", b"not a zip", "application/zip")})
check("a non-team file is refused", bad.status_code == 400)

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
