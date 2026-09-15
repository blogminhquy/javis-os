"""Plugin javis-workflow: Javis tra được lịch sử chạy quy trình từ mọi engine.

    python tests/run.py javis_workflow_plugin
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-wfplug-")

import workflow_runs  # noqa: E402
import plugins_host  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


spec = importlib.util.spec_from_file_location(
    "javis_workflow_plugin", ROOT / "system" / "plugins" / "javis-workflow" / "plugin.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

VAULT = tempfile.mkdtemp(prefix="javis-vault-")
B = str(Path(VAULT).resolve())
ctx = plugins_host.PluginContext("javis-workflow", "bundled", ROOT / "system/plugins/javis-workflow", VAULT)
m.register(ctx)
tool = ctx._tools[0]
check("dang ky tool javis_workflow readonly", tool["name"] == "javis_workflow" and tool["min_mode"] == "readonly")

st = workflow_runs.get_store()
r1 = st.bat_dau(brain=B, slug="viet-bai", name="Viết bài", input="A", source="web", session_id="s")
st.ghi_buoc(r1, 0, agent="Người viết", task="viết", output="xong A")
st.ket_thuc(r1, "done", output="BÀI A")
r2 = st.bat_dau(brain=B, slug="ban-tin", name="Bản tin", input="", source="kanban")
st.ket_thuc(r2, "error", error="engine chết")

h = tool["handler"]
out = asyncio.run(h({"op": "runs"}, ctx))
check("runs liet ke moi nhat truoc, co ten/trang thai/id", out.index("Bản tin") < out.index("Viết bài")
      and "lỗi" in out and "xong" in out and r1 in out and r2 in out)
out = asyncio.run(h({"op": "runs", "slug": "viet-bai"}, ctx))
check("runs loc slug", "Viết bài" in out and "Bản tin" not in out)
out = asyncio.run(h({"op": "show", "id": r1}, ctx))
check("show co dau vao, buoc, ket qua", "A" in out and "Người viết" in out and "BÀI A" in out)
check("show id la -> loi ro", "ERROR" in asyncio.run(h({"op": "show", "id": "xxx"}, ctx)))
check("op la -> loi ro", "ERROR" in asyncio.run(h({"op": "bay"}, ctx)))
ctx2 = plugins_host.PluginContext("javis-workflow", "bundled", ROOT / "system/plugins/javis-workflow", None)
check("khong co vault_root -> loi ro", "ERROR" in asyncio.run(h({"op": "runs"}, ctx2)))

# Dòng trong system prompt
import main  # noqa: E402
d = main._dong_lan_chay_gan_nhat(B)
check("dong lan chay gan nhat", d.startswith("Lần chạy quy trình gần nhất: Bản tin") and "lỗi" in d and "javis_workflow" in d)
check("brain chua chay -> rong", main._dong_lan_chay_gan_nhat("/khong-co") == "")
src = (SERVER / "main.py").read_text(encoding="utf-8")
than = src[src.index("def _javis_capability_summary("):src.index("def _skill_router_block(")]
check("capability summary goi dong lan chay", "_dong_lan_chay_gan_nhat(" in than)

print("\nFAIL:" if fails else "\nOK - javis_workflow_plugin", fails or "")
sys.exit(1 if fails else 0)
