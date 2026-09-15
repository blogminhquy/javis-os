"""Plugin javis-workflow: Javis tra được lịch sử chạy quy trình từ mọi engine.

    python tests/run.py javis_workflow_plugin
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import os
import sys
import tempfile
from datetime import datetime
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
import localefmt  # noqa: E402  - da nap san server/ vao sys.path qua _paths

d = main._dong_lan_chay_gan_nhat(B)
check("dong lan chay gan nhat", d.startswith("Lần chạy quy trình gần nhất: Bản tin") and "lỗi" in d and "javis_workflow" in d)
check("brain chua chay -> rong", main._dong_lan_chay_gan_nhat("/khong-co") == "")
src = (SERVER / "main.py").read_text(encoding="utf-8")
than = src[src.index("def _javis_capability_summary("):src.index("def _skill_router_block(")]
check("capability summary goi dong lan chay", "_dong_lan_chay_gan_nhat(" in than)

# Fix round 1 (c): gio phai theo mui gio localefmt (Docker chay UTC), khong phai gio he thong tran.
r1_day_du = st.lay(r1)
gio_ky_vong_r1 = datetime.fromtimestamp(
    float(r1_day_du["started_at"]), tz=localefmt.now().tzinfo).strftime("%H:%M %d/%m")
check("_gio dung mui gio localefmt", m._gio(r1_day_du["started_at"]) == gio_ky_vong_r1)

r2_day_du = st.lay(r2)
gio_ky_vong_r2 = datetime.fromtimestamp(
    float(r2_day_du["started_at"]), tz=localefmt.now().tzinfo).strftime("%H:%M %d/%m")
check("dong lan chay gan nhat dung mui gio localefmt", gio_ky_vong_r2 in d)

# Fix round 1 (a): op=show voi qua nhieu buoc, moi buoc mang loi dai - phai cat va bao con bao nhieu.
r3 = st.bat_dau(brain=B, slug="dai-buoc", name="Dài bước", input="X", source="web")
for i in range(15):
    st.ghi_buoc(r3, i, agent=f"Tác nhân {i}", task=f"làm bước {i}", error="E" * 3000)
st.ket_thuc(r3, "error", error="tổng lỗi")
out = asyncio.run(h({"op": "show", "id": r3}, ctx))
check("show nhieu buoc loi dai bi cat, co danh dau con bao nhieu",
      len(out) <= 7600 and "bước nữa" in out)

# Fix round 1 (b): op=runs voi nhieu lan chay loi dai cung khong duoc phinh vo han.
for i in range(10):
    rid_loi = st.bat_dau(brain=B, slug=f"loi-{i}", name=f"Lỗi {i}", input="", source="kanban")
    st.ket_thuc(rid_loi, "error", error="L" * 3000)
out = asyncio.run(h({"op": "runs", "limit": 20}, ctx))
check("runs nhieu lan chay loi dai bi cat trong tran chung", len(out) <= 7600)

print("\nFAIL:" if fails else "\nOK - javis_workflow_plugin", fails or "")
sys.exit(1 if fails else 0)
