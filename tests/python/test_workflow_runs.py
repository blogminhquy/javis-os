"""Kho lịch sử chạy quy trình (server/workflow_runs.py).

    python tests/run.py workflow_runs

Vì sao có kho này: trước đây bấm Chạy ở trang Quy trình thì kết quả stream vào một ngăn kéo
tạm, đóng là mất. Hỏi Javis "quy trình chạy gần nhất ra sao" là không có gì để tra.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-wfruns-")

import workflow_runs  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


st = workflow_runs.get_store()

# 1. Bắt đầu một lần chạy -> có id, trạng thái running
rid = st.bat_dau(brain="/b1", slug="viet-bai", name="Viết bài", input="chủ đề A",
                 source="web", session_id="s1")
r = st.lay(rid)
check("bat_dau tra id va running", bool(rid) and r["status"] == "running")
check("bat_dau giu input/source/session", r["input"] == "chủ đề A" and r["source"] == "web"
      and r["session_id"] == "s1" and r["name"] == "Viết bài")

# 2. Ghi bước: tạo mới rồi cập nhật cùng chỉ số
st.ghi_buoc(rid, 0, agent="Nhà nghiên cứu", task="tìm hiểu")
st.ghi_buoc(rid, 0, output="kết quả bước 0", verified=True)
st.ghi_buoc(rid, 1, agent="Người viết", task="viết", error="hết hạn")
steps = st.lay(rid)["steps"]
check("ghi_buoc gop cung chi so", len(steps) == 2 and steps[0]["agent"] == "Nhà nghiên cứu"
      and steps[0]["output"] == "kết quả bước 0" and steps[0]["verified"] is True)
check("ghi_buoc giu loi buoc", steps[1]["error"] == "hết hạn")

# 3. Kết thúc: done + output, finished_at có
st.ket_thuc(rid, "done", output="bài hoàn chỉnh")
r = st.lay(rid)
check("ket_thuc done", r["status"] == "done" and r["output"] == "bài hoàn chỉnh" and r["finished_at"] > 0)

# 4. Cắt độ dài: input 4000, task 2000, output bước 4000, output cuối 20000
rid2 = st.bat_dau(brain="/b1", slug="viet-bai", name="Viết bài", input="x" * 9000, source="kanban")
st.ghi_buoc(rid2, 0, task="t" * 5000, output="o" * 9000)
st.ket_thuc(rid2, "error", output="k" * 30000, error="lỗi thật")
r2 = st.lay(rid2)
check("cat input 4000", len(r2["input"]) == 4000)
check("cat task 2000 va output buoc 4000", len(r2["steps"][0]["task"]) == 2000
      and len(r2["steps"][0]["output"]) == 4000)
check("cat output cuoi 20000", len(r2["output"]) == 20000 and r2["error"] == "lỗi thật")

# 5. gan_nhat: mới nhất trước, lọc slug/session/status, limit
rid3 = st.bat_dau(brain="/b1", slug="ban-tin", name="Bản tin", input="", source="web", session_id="s2")
ds = st.gan_nhat("/b1")
check("gan_nhat moi nhat truoc", [x["id"] for x in ds] == [rid3, rid2, rid])
check("gan_nhat loc slug", [x["id"] for x in st.gan_nhat("/b1", slug="ban-tin")] == [rid3])
check("gan_nhat loc session+status", [x["id"] for x in st.gan_nhat("/b1", session_id="s1", status="done")] == [rid])
check("gan_nhat limit", len(st.gan_nhat("/b1", limit=2)) == 2)
check("gan_nhat khac brain rong", st.gan_nhat("/khac") == [])
check("gan_nhat khong mang output day du", "output_tom_tat" in ds[1] and "output" not in ds[1]
      and len(ds[1]["output_tom_tat"]) == 200)

# 6. dem_theo_phien, tim_theo_task, moc_moi_nhat_theo_slug
check("dem_theo_phien", st.dem_theo_phien("s1") == 1 and st.dem_theo_phien("s9") == 0)
st.ket_thuc(rid3, "waiting", task_id="task-77")
check("tim_theo_task", (st.tim_theo_task("task-77") or {}).get("id") == rid3
      and st.tim_theo_task("khong-co") is None)
moc = st.moc_moi_nhat_theo_slug("/b1")
check("moc_moi_nhat_theo_slug", set(moc) == {"viet-bai", "ban-tin"} and moc["ban-tin"] >= moc["viet-bai"])

# 7. Nhãn trạng thái tiếng Việt có đủ
check("nhan trang thai", set(workflow_runs.NHAN_TRANG_THAI) == set(workflow_runs.TRANG_THAI))

print("\nFAIL:" if fails else "\nOK - workflow_runs", fails or "")
sys.exit(1 if fails else 0)
