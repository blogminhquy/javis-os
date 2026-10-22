"""Nhóm chat team T1, nhiệm vụ 2: kho `team.sqlite3` (spec 2026-10-13-team-chat-design mục 5.2).

    python tests/run.py team_store

Không gọi model. Nhóm, thành viên ở nhiều nhóm, trưởng nhóm, bước nội bộ (CAS), sổ lượt, khoá bận theo agent.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-store-")

import team_store as TS  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


st = TS.TeamStore(Path(os.environ["JAVIS_STATE_DIR"]) / "team.sqlite3")
B = "D:/brain-a"

# ───────────── nhóm và thành viên ─────────────
t1 = st.create_team(B, "Ra mắt", "Kế hoạch ra mắt", "team:s1")
t2 = st.create_team(B, "Nội dung", "", "team:s2")
t3 = st.create_team("D:/brain-b", "Khác brain", "", "team:s3")
check("tạo nhóm: mã tm_, trạng thái active, chưa có trưởng nhóm, trần mặc định",
      t1["team_id"].startswith("tm_") and t1["status"] == "active" and t1["leader_key"] is None
      and t1["caps"]["task_turns"] == 12 and t1["caps"]["mentions"] == 3)
check("danh sách chỉ của đúng brain", {t["team_id"] for t in st.list_teams(B)} == {t1["team_id"], t2["team_id"]})
st.add_member(t1["team_id"], "ag_lan", "lan")
st.add_member(t1["team_id"], "ag_minh", "minh")
st.add_member(t2["team_id"], "ag_lan", "lan")
check("cùng agent ở hai nhóm", {m["agent_key"] for m in st.members(t2["team_id"])} == {"ag_lan"}
      and len(st.members(t1["team_id"])) == 2)
check("thêm lại thành viên đang có: không trùng", len(st.add_member(t1["team_id"], "ag_lan", "lan") and
                                                       st.members(t1["team_id"])) == 2)
try:
    st.set_leader(t1["team_id"], "ag_nguoi_ngoai")
    check("trưởng nhóm phải là thành viên đang hoạt động", False)
except TS.TeamError:
    check("trưởng nhóm phải là thành viên đang hoạt động", True)
t1 = st.set_leader(t1["team_id"], "ag_lan")
check("chọn trưởng nhóm", t1["leader_key"] == "ag_lan"
      and [m["role"] for m in st.members(t1["team_id"]) if m["agent_key"] == "ag_lan"] == ["leader"])
st.set_leader(t2["team_id"], "ag_lan")
check("một agent làm trưởng nhóm ở nhóm này, thành viên ở nhóm khác được", st.get(t2["team_id"])["leader_key"] == "ag_lan")
st.remove_member(t1["team_id"], "ag_lan")
t1 = st.get(t1["team_id"])
check("bỏ trưởng nhóm khỏi nhóm: nhóm không còn trưởng nhóm, ghi sự kiện, nhóm khác không đổi",
      t1["leader_key"] is None and st.get(t2["team_id"])["leader_key"] == "ag_lan"
      and any(e["kind"] == "leader_removed" for e in st.events(t1["team_id"])))
check("thành viên đã bỏ không còn trong danh sách đang hoạt động, vẫn ở lịch sử",
      "ag_lan" not in {m["agent_key"] for m in st.members(t1["team_id"])}
      and "ag_lan" in {m["agent_key"] for m in st.members(t1["team_id"], include_removed=True)})
st.add_member(t1["team_id"], "ag_lan", "lan")
check("thêm lại người đã bỏ: hoạt động lại, là thành viên thường",
      [m["role"] for m in st.members(t1["team_id"]) if m["agent_key"] == "ag_lan"] == ["member"])
gone = st.mark_agent_gone(B, "ag_lan")
check("agent bị xoá khỏi Javis: mọi nhóm đánh dấu agent_gone, nhóm 2 mất trưởng nhóm",
      set(gone) == {t1["team_id"], t2["team_id"]} and st.get(t2["team_id"])["leader_key"] is None
      and "ag_lan" not in {m["agent_key"] for m in st.members(t2["team_id"])})
t2 = st.update(t2["team_id"], name="Nội dung tuần", status="paused")
check("đổi tên, tạm dừng", t2["name"] == "Nội dung tuần" and t2["status"] == "paused")
try:
    st.update(t2["team_id"], status="xoa_het")
    check("trạng thái lạ bị từ chối", False)
except TS.TeamError:
    check("trạng thái lạ bị từ chối", True)

# ───────────── bước nội bộ ─────────────
s1 = st.add_step("task_1", t1["team_id"], "plan", "ag_minh", 1, "Lập kế hoạch", [])
s2 = st.add_step("task_1", t1["team_id"], "work", "ag_minh", 1, "Viết", ["msg:1"], parent_step=None)
check("bước đánh số tăng dần trong một việc", (s1["seq"], s2["seq"]) == (1, 2) and s2["input_refs"] == ["msg:1"])
check("lấy bước chờ kế tiếp theo thứ tự", st.next_queued_step("task_1")["step_id"] == s1["step_id"])
check("nhận bước: CAS queued sang running đúng một lần", st.claim_step(s1["step_id"]) is True
      and st.claim_step(s1["step_id"]) is False)
st.finish_step(s1["step_id"], "done", result_msg_id=7, applied=True)
check("kết thúc bước ghi kết quả và cờ áp dụng", [(x["status"], x["result_msg_id"], x["applied"])
      for x in st.steps("task_1") if x["step_id"] == s1["step_id"]] == [("done", 7, True)])

# ───────────── sổ lượt ─────────────
u1 = st.reserve_turn(t1["team_id"], "task_1", s1["step_id"], "ag_minh", "plan")
u2 = st.reserve_turn(t1["team_id"], "task_1", s2["step_id"], "ag_minh", "work")
u3 = st.reserve_turn(t1["team_id"], None, None, "ag_minh", "member_reply")
st.mark_engine(u1, "anthropic-cli", "sonnet")
st.settle_turn(u1, "ok", tokens_in=10, tokens_out=5)
st.refund_turn(u2)
st.mark_engine(u3, "fake", "fake")
st.settle_turn(u3, "error")
check("lượt hoàn không tính; lỗi sau mốc engine vẫn tính", st.count_task_turns("task_1") == 1
      and st.count_team_turns(t1["team_id"], since=0) == 2)
try:
    st.refund_turn(u1)
    check("lượt đã gọi engine không hoàn được", False)
except TS.TeamError:
    check("lượt đã gọi engine không hoàn được", True)

# ───────────── khoá bận theo agent ─────────────
check("giữ khoá bận", st.acquire_busy("ag_minh", t1["team_id"], "turn_a", lease_s=60, now=1000) is True)
check("lượt khác (nhóm khác) không lấy được khi còn hạn", st.acquire_busy("ag_minh", t2["team_id"], "turn_b",
                                                                           lease_s=60, now=1030) is False)
check("hết hạn thì lấy được", st.acquire_busy("ag_minh", t2["team_id"], "turn_b", lease_s=60, now=1061) is True)
st.release_busy("ag_minh", "turn_a")
check("nhả bằng lượt cũ không gỡ khoá của lượt mới", st.busy_of("ag_minh", now=1062)["turn_id"] == "turn_b")
st.release_busy("ag_minh", "turn_b")
check("nhả đúng lượt thì trống", st.busy_of("ag_minh", now=1063) is None)
# 0.257.0: lượt nhóm giữ dòng theo mạch (agent + nhóm). Hai nhóm không chặn nhau; dòng giữ trọn agent chặn tất cả.
check("mạch nhóm 1 giữ được", st.acquire_busy("ag_minh", t1["team_id"], "turn_c", lease_s=60, now=2000, per_team=True))
check("mạch nhóm 2 giữ được CÙNG LÚC", st.acquire_busy("ag_minh", t2["team_id"], "turn_d", lease_s=60, now=2000,
                                                     per_team=True))
check("cùng nhóm, lượt khác: phải chờ", not st.acquire_busy("ag_minh", t1["team_id"], "turn_e", lease_s=60, now=2001,
                                                          per_team=True))
check("giữ trọn agent khi đang có lượt nhóm: không được", not st.acquire_busy("ag_minh", "pulse", "tok", lease_s=60,
                                                                            now=2001))
check("busy_of thấy agent bận, mã agent trần", st.busy_of("ag_minh", now=2001)["agent_key"] == "ag_minh")
check("busy_keys trả mã agent trần", st.busy_keys(now=2001) == {"ag_minh"})
check("lượt nhóm không chặn nhóm khác", st.busy_blocking("ag_minh", "tm_khac", now=2001) is None)
check("busy_turn theo nhóm", st.busy_turn("ag_minh", t2["team_id"]) == "turn_d" and st.busy_turn("ag_minh") is None)
check("gia hạn đúng lượt trên dòng mạch", st.renew_busy("ag_minh", "turn_c", 60, now=2002))
st.release_busy("ag_minh", "turn_c")
st.release_busy("ag_minh", "turn_d")
check("nhả hết thì trống", st.busy_of("ag_minh", now=2003) is None)
check("giữ trọn agent", st.acquire_busy("ag_minh", "pulse", "tok", lease_s=60, now=2003))
check("dòng giữ trọn chặn lượt nhóm", not st.acquire_busy("ag_minh", t1["team_id"], "turn_f", lease_s=60, now=2004,
                                                         per_team=True)
      and st.busy_blocking("ag_minh", t1["team_id"], now=2004)["team_id"] == "pulse")
st.release_busy("ag_minh", "tok")
raise SystemExit(1 if fails else 0)
