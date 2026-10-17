"""0.200.0: a whole team travels as one file, with no secrets, model choices or Auto switches.

Run:
    python tests/run.py team_bundle
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import io
import json
import tempfile
import zipfile
from pathlib import Path

import share_bundle  # noqa: E402
import team_bundle as tb  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


src = Path(tempfile.mkdtemp(prefix="javis-teamsrc-"))
(src / "agents").mkdir()
(src / "skills" / "viet-email").mkdir(parents=True)
(src / "workflows").mkdir()
(src / "agents" / "lan.md").write_text(
    "---\nname: Lan\nrole: Marketing\nmodel: claude-opus\nmodel_provider: anthropic-cli\nauto: true\n"
    "skills:\n- viet-email\ntags:\n- Marketing\n---\nDùng key sk-ant-api03-ABCDEFGHIJKLMNOP để gọi. password: hunter2hunter2\n",
    encoding="utf-8")
(src / "agents" / "minh.md").write_text("---\nname: Minh\n---\nBot token 123456789:AAEhBP0av28zVhzTFr7XZ_abcdefghijklmn\n",
                                        encoding="utf-8")
(src / "skills" / "viet-email" / "SKILL.md").write_text("---\nname: viet-email\n---\nghp_abcdefghijklmnop1234\n",
                                                       encoding="utf-8")

zip_bytes, _ = share_bundle.build_bundle("agent", ["lan", "minh"], agents_dir=src / "agents",
                                         workflows_dir=src / "workflows", skills_root=src / "skills")
team = {"name": "Team Marketing", "description": "Chạy quảng cáo, token=abcdefghijklmnop", "tags": ["Marketing"]}
manifest = tb.team_manifest(team, ["lan", "minh"], "lan",
                            ["Luôn trả lời ngắn", "Key của shop là AIzaSyA1234567890abcdefghijklmnopqrstuv"])
data = tb.add_team_entry(zip_bytes, manifest)
z = zipfile.ZipFile(io.BytesIO(data))
lan = z.read("agents/lan.md").decode("utf-8")
check("team entry present", tb.TEAM_ENTRY in z.namelist())
check("model fields dropped", "model:" not in lan and "model_provider" not in lan)
check("Auto switch dropped", "auto:" not in lan)
check("role, skills and tags kept", "role: Marketing" in lan and "viet-email" in lan and "Marketing" in lan)
check("API key scrubbed", "sk-ant-api03" not in lan and "[REDACTED_KEY]" in lan)
check("password scrubbed", "hunter2" not in lan)
check("bot token scrubbed", "AAEhBP0av28" not in z.read("agents/minh.md").decode("utf-8"))
check("skill secret scrubbed", "ghp_abcdefghijklmnop" not in z.read("skills/viet-email/SKILL.md").decode("utf-8"))
m = tb.read_team_entry(data)
check("manifest read back", m and m["name"] == "Team Marketing" and m["members"] == ["lan", "minh"] and m["leader"] == "lan")
check("instruction secret scrubbed", "AIzaSy" not in json.dumps(m))
check("description query secret scrubbed", "abcdefghijklmnop" not in m["description"])
pv = tb.preview(data)
check("preview lists members and skills", pv["ok"] and pv["members"] == ["lan", "minh"] and pv["skills"] == ["viet-email"])
check("plain bundle is not a team", tb.read_team_entry(zip_bytes) is None and not tb.preview(zip_bytes)["ok"])
check("garbage is not a team", tb.read_team_entry(b"not a zip") is None)

# An old Javis imports the same file as a plain bundle: the extra entry is ignored.
dst = Path(tempfile.mkdtemp(prefix="javis-teamdst-"))
(dst / "agents").mkdir()
(dst / "agents" / "minh.md").write_text("---\nname: Minh (mine)\n---\n", encoding="utf-8")
res = share_bundle.import_bundle(data, "team.javis.zip", agents_dir=dst / "agents", workflows_dir=dst / "workflows",
                                 skills_root=dst / "skills")
check("partners imported, existing one kept", "agent:lan" in res["imported"] and "agent:minh" in res["skipped"]
      and "Minh (mine)" in (dst / "agents" / "minh.md").read_text(encoding="utf-8"))
check("no stray file from the team entry", not (dst / tb.TEAM_ENTRY).exists() and not res["errors"])
members, missing = tb.resolve_members(m, res["imported"], res["skipped"], {"minh"})
check("members resolved to what is present", members == ["lan", "minh"] and missing == [])
members, missing = tb.resolve_members(m, [], [], set())
check("missing members reported", members == [] and missing == ["lan", "minh"])

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
