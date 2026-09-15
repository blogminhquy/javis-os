"""Ghi lịch sử chạy ngay trong execute_workflow + route đọc lịch sử.

    python tests/run.py workflow_runs_api

Không chạy engine thật: bọc một generator giả phát đúng dãy sự kiện của execute_workflow.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-wfapi-")
# TestClient gửi Host: testserver, không nằm trong allowlist mặc định của web_security.py
# (localhost/127.0.0.1/::1) - chưa đặt mật khẩu thì middleware DNS-rebinding chặn 403 "host
# không được phép" trước khi vào tới route. Thêm host giả này vào allowlist CHỈ trong tiến
# trình test, không đụng gì tới hành vi thật.
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"

import main  # noqa: E402
import workflow_runs  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


async def gia_done():
    yield {"type": "start", "workflow": "Viết bài", "steps": 2}
    yield {"type": "step_start", "i": 0, "agent": "Nhà nghiên cứu", "task": "tìm"}
    yield {"type": "step_text", "i": 0, "content": "..."}
    yield {"type": "step_done", "i": 0, "agent": "Nhà nghiên cứu", "output": "dữ liệu", "verified": None}
    yield {"type": "step_start", "i": 1, "agent": "Người viết", "task": "viết"}
    yield {"type": "step_done", "i": 1, "agent": "Người viết", "output": "bài xong", "verified": True}
    yield {"type": "done", "result": "bài xong"}


async def gia_error():
    yield {"type": "start", "workflow": "Viết bài", "steps": 1}
    yield {"type": "step_start", "i": 0, "agent": "A", "task": "t"}
    yield {"type": "step_error", "i": 0, "content": "engine chết"}
    yield {"type": "error", "content": "dừng vì lỗi"}


async def gia_wait():
    yield {"type": "start", "workflow": "Đăng bài", "steps": 2}
    yield {"type": "wait_user", "node": "dang", "prompt": "duyệt đăng?", "task_id": "tk1", "code": "AB12"}


async def gom(gen):
    return [e async for e in gen]


st = workflow_runs.get_store()

# Route khoá brain bằng _brain_key(brain) trước khi chạm kho; generator boc _ghi_lich_su
# nhan brain DA khoa san (main.py truyen _brain_key(brain) vao no). Vi vay test phai tu
# khoa truoc khi goi _ghi_lich_su truc tiep, con khi goi qua route thi truyen brain="/b"
# tho de route tu khoa - hai duong phai ra CUNG mot chuoi thi test moi doi chieu dung.
B = main._brain_key("/b")

evs = asyncio.run(gom(main._ghi_lich_su(gia_done(), brain=B, slug="viet-bai", name="Viết bài",
                                        input="chủ đề", source="web", session_id="s1")))
check("start co run_id, cac su kien giu nguyen", evs[0]["type"] == "start" and evs[0].get("run_id")
      and [e["type"] for e in evs[1:]] == ["step_start", "step_text", "step_done", "step_start", "step_done", "done"])
r = st.lay(evs[0]["run_id"])
check("ban ghi done du buoc", r["status"] == "done" and r["output"] == "bài xong"
      and [s["agent"] for s in r["steps"]] == ["Nhà nghiên cứu", "Người viết"] and r["steps"][1]["verified"] is True)

evs = asyncio.run(gom(main._ghi_lich_su(gia_error(), brain=B, slug="viet-bai", name="Viết bài",
                                        input="", source="kanban", session_id="")))
r = st.lay(evs[0]["run_id"])
check("ban ghi error", r["status"] == "error" and r["error"] == "dừng vì lỗi" and r["steps"][0]["error"] == "engine chết"
      and r["source"] == "kanban")

evs = asyncio.run(gom(main._ghi_lich_su(gia_wait(), brain=B, slug="dang-bai", name="Đăng bài",
                                        input="", source="web", session_id="s2")))
r = st.lay(evs[0]["run_id"])
check("ban ghi waiting + task_id", r["status"] == "waiting" and r["task_id"] == "tk1")

# Resume: truyền run_id cũ thì cập nhật đúng bản ghi đó thay vì tạo mới
truoc = len(st.gan_nhat(B))
evs = asyncio.run(gom(main._ghi_lich_su(gia_done(), brain=B, slug="dang-bai", name="Đăng bài",
                                        input="", source="web", session_id="s2", run_id=r["id"])))
check("resume cap nhat ban ghi cu", len(st.gan_nhat(B)) == truoc and st.lay(r["id"])["status"] == "done")


# Dừng giữa chừng (client đóng): bản ghi không kẹt ở running
async def dung_som():
    gen = main._ghi_lich_su(gia_done(), brain=B, slug="viet-bai", name="Viết bài",
                            input="", source="web", session_id="s3")
    first = await gen.__anext__()
    await gen.aclose()
    return first["run_id"]

rid = asyncio.run(dung_som())
check("dong som -> error 'dung giua chung'", st.lay(rid)["status"] == "error")

# Route đọc
c = TestClient(main.app)
# 4 ban ghi tich luy tu dau file: viet-bai(done), viet-bai(error), dang-bai(waiting -> resume
# thanh done, VAN LA 1 ban ghi), viet-bai(dung_som/error). limit=5 chi de kiem no khong bi
# cat khi con it hon limit, khong phai dung 5.
ds = c.get("/workflows/runs", params={"brain": "/b", "limit": 5}).json()["runs"]
check("GET /workflows/runs tra danh sach gon", len(ds) == 4 and "output_tom_tat" in ds[0] and "output" not in ds[0])
ds2 = c.get("/workflows/runs", params={"brain": "/b", "slug": "dang-bai"}).json()["runs"]
check("GET /workflows/runs loc slug", all(x["slug"] == "dang-bai" for x in ds2) and ds2)
one = c.get(f"/workflows/runs/{ds[0]['id']}").json()
check("GET /workflows/runs/{id} day du", one["id"] == ds[0]["id"] and "output" in one and "steps" in one)
check("GET /workflows/runs/{id} 404", c.get("/workflows/runs/khong-co").status_code == 404)

print("\nFAIL:" if fails else "\nOK - workflow_runs_api", fails or "")
sys.exit(1 if fails else 0)
