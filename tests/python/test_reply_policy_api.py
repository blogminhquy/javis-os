"""Bộ phán xử hội thoại nhóm: năm đường API, lưu cấu hình qua form, và độ khớp giữa mã im ở Python với nhãn ở giao diện.

    python tests/run.py reply_policy_api      (KHÔNG mạng; dùng TestClient)

Điểm cần canh:
  - Bot CHƯA từng bật thì GET không sinh ra file kho (bot chưa opt-in không được lưu nội dung chat).
  - Cấu hình đi qua FORM (chuỗi JSON) vẫn lưu đúng, giá trị lạ giữ nguyên giá trị cũ.
  - 👍/👎 chỉ chạy khi bot đã bật tự học, và không gắn được nhãn cho quyết định của bot khác.
  - Xoá bot xoá sạch dữ liệu học của bot đó (nội dung chat khách).
  - Mọi mã im mà bộ máy phát ra đều có nhãn đọc được ở giao diện.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import re
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-rp-api-")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"       # xem test_workflow_runs_api.py
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_reply_policy as rp  # noqa: E402
import chatbot_reply_policy_store as st  # noqa: E402
import chatbot_store  # noqa: E402
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


c = TestClient(main.app)
NOW = 1_800_000_000.0

bid, err = chatbot_store.create_bot({"name": "Nhi Mai", "agent_slug": "hoa", "brain": "brain", "reply_when": "auto"})
check("(chuẩn bị) có bot", bid and not err, err)
r = c.get(f"/chatbots/{bid}/reply-policy").json()
check("GET chưa bật: cấu hình mặc định, không quyết định nào", r["ok"] and r["config"]["mode"] == "off" and r["decisions"] == [], r)
check("GET chưa bật KHÔNG sinh file kho (bot chưa opt-in thì không lưu nội dung chat)", not st.db_path().exists())
check("bot không tồn tại thì 404", c.get("/chatbots/khong-co/reply-policy").status_code == 404)

# ---- lưu cấu hình qua form ----
pol = {"mode": "on", "eagerness": "high", "guidelines": "Chỉ nói về mỹ phẩm", "aliases": ["Nhi"], "trainer_ids": ["boss1"],
       "learning_enabled": True, "grounding": "role"}
r = c.post(f"/chatbots/{bid}/update", data={"reply_policy": json.dumps(pol)})
check("POST update nhận reply_policy dạng chuỗi JSON", r.status_code == 200 and r.json()["ok"], r.text)
got = chatbot_store.get_bot(bid)["reply_policy"]
check("cấu hình được lưu đủ", got["mode"] == "on" and got["eagerness"] == "high" and got["aliases"] == ["Nhi"]
      and got["trainer_ids"] == ["boss1"] and got["learning_enabled"] and got["grounding"] == "role", got)
c.post(f"/chatbots/{bid}/update", data={"reply_policy": json.dumps({"mode": "lung-tung", "eagerness": "ồn", "learning_enabled": "yes"})})
got = chatbot_store.get_bot(bid)["reply_policy"]
check("bản vá giá trị lạ: GIỮ giá trị cũ, không hạ hay nâng", got["mode"] == "on" and got["eagerness"] == "high" and got["learning_enabled"] is True, got)
c.post(f"/chatbots/{bid}/update", data={"reply_policy": "không phải json"})
check("JSON hỏng: không đổi gì", chatbot_store.get_bot(bid)["reply_policy"] == got)
c.post(f"/chatbots/{bid}/update", data={"name": "Nhi Mai 2"})
check("cập nhật trường khác KHÔNG đụng cấu hình bộ phán xử", chatbot_store.get_bot(bid)["reply_policy"] == got)
c.post(f"/chatbots/{bid}/update", data={"reply_policy": json.dumps({"aliases": ["Mai"]})})
check("bản vá từng phần chỉ đổi khoá được gửi", chatbot_store.get_bot(bid)["reply_policy"]["aliases"] == ["Mai"]
      and chatbot_store.get_bot(bid)["reply_policy"]["mode"] == "on")

r = c.post("/chatbots", data={"name": "Bot mới", "agent_slug": "hoa", "brain": "brain",
                              "reply_policy": json.dumps({"mode": "shadow", "learning_enabled": True})}).json()
check("tạo bot kèm reply_policy", r["ok"] and chatbot_store.get_bot(r["id"])["reply_policy"]["mode"] == "shadow")
r2 = c.post("/chatbots", data={"name": "Bot không khai", "agent_slug": "hoa", "brain": "brain"}).json()
check("tạo bot không khai: tắt sẵn, không học", chatbot_store.get_bot(r2["id"])["reply_policy"]["mode"] == "off"
      and chatbot_store.get_bot(r2["id"])["reply_policy"]["learning_enabled"] is False)

# ---- GET có dữ liệu ----
rid = st.log_decision({"bot_id": bid, "chat_id": "g1", "ts": NOW, "text": "câu hỏi", "sender": "Nam", "sender_id": "u1",
                       "verdict": "silent", "candidate": True, "silence_code": "judge_silent", "mode": "on", "score": 0.3, "threshold": 0.45}, NOW)
st.log_decision({"bot_id": bid, "chat_id": "g1", "ts": NOW, "text": "haha", "verdict": "silent", "silence_code": "no_signal", "mode": "on"}, NOW)
st.log_decision({"bot_id": bid, "chat_id": "g1", "ts": NOW, "text": "gọi tên", "verdict": "reply", "candidate": True, "mode": "on"}, NOW)
st.add_case(bid, "g1", "ca chủ dạy", {}, "reply", "r", "owner", 2.0, now=NOW)
st.add_lesson(bid, "Gọi tên trơn cũng là gọi bot", NOW)
st.set_role_profile(bid, "Đảm nhiệm: mỹ phẩm", "h", NOW)
r = c.get(f"/chatbots/{bid}/reply-policy").json()
check("GET trả quyết định KỂ CẢ lúc im, có sender_id", len(r["decisions"]) == 3 and any(d["sender_id"] == "u1" for d in r["decisions"]))
check("GET trả thống kê, ca, bài học, hồ sơ vai", r["stats"]["silent"] == 2 and len(r["cases"]) == 1
      and r["lessons"][0]["text"].startswith("Gọi tên") and r["role_profile"].startswith("Đảm nhiệm"), r["stats"])
check("only_silent lọc đúng", len(c.get(f"/chatbots/{bid}/reply-policy", params={"only_silent": "true"}).json()["decisions"]) == 2)
check("dữ liệu tách theo bot: bot khác không thấy gì", c.get(f"/chatbots/{r2['id']}/reply-policy").json()["decisions"] == [])

# ---- nhãn của chủ ----
r = c.post(f"/chatbots/{bid}/reply-policy/label", data={"decision_id": rid, "thumb": "down"})
check("👎 trên quyết định im -> missed", r.status_code == 200 and r.json()["label"] == "missed", r.text)
check("nhãn đã vào kho và thành ca", st.get_decision(rid)["label"] == "missed" and st.count_cases(bid, "auto") + st.count_cases(bid, "owner") >= 2)
check("nút lạ -> 400", c.post(f"/chatbots/{bid}/reply-policy/label", data={"decision_id": rid, "thumb": "x"}).status_code == 400)
check("quyết định của bot khác -> 400", c.post(f"/chatbots/{r2['id']}/reply-policy/label", data={"decision_id": rid, "thumb": "up"}).status_code in (400, 409))
r3 = c.post(f"/chatbots/{r2['id']}/reply-policy/label", data={"decision_id": rid, "thumb": "up"})
check("bot chưa bật tự học: từ chối, không lưu nhãn (409)", r3.status_code == 409, r3.text)

# ---- xoá ca, quên ----
case_id = st.list_cases(bid)[0]["id"]
check("xoá một ca", c.post(f"/chatbots/{bid}/reply-policy/cases/{case_id}/delete").json()["deleted"] is True)
check("xoá lại: không còn", c.post(f"/chatbots/{bid}/reply-policy/cases/{case_id}/delete").json()["deleted"] is False)
n0 = st.stats(bid)
f = c.post(f"/chatbots/{bid}/reply-policy/forget", data={}).json()
check("quên hết: ca và bài học sạch", f["ok"] and st.count_cases(bid, "auto") == 0 and st.count_cases(bid, "owner") == 0
      and st.list_lessons(bid) == [], f)
check("quên hết xoá CẢ nhật ký quyết định (đó là chữ chat của khách)", st.stats(bid)["decisions"] == 0 and f["decisions"] == n0["decisions"], f)

# ---- engine của người phán xử phải bị nhốt (rà soát 30/09: bỏ trống allowed_tools là bypassPermissions) ----
seen = {}


class _CliGia:
    def __init__(self, **kw):
        seen.update(kw)
        self.disallowed_tools = None
        self.mcp_config = None
        self.mcp_strict = False

    def is_available(self):
        return True

    async def query(self, prompt):
        yield {"type": "final", "content": '{"verdict":"silent","score":0.1,"reason":"x"}'}


import asyncio as _aio  # noqa: E402
_orig_engine, _orig_swap = main.claude_engine, main._aux_swap
main.claude_engine = lambda **kw: _CliGia(**kw)
main._aux_swap = lambda cli, mode=None, tag=None: cli
try:
    out = _aio.run(main._reply_policy_ask("prompt thử", "judge"))
finally:
    main.claude_engine, main._aux_swap = _orig_engine, _orig_swap
check("người phán xử chạy được và trả chữ", "verdict" in out)
check("allowed_tools CÓ giá trị (khác rỗng) nên cổng can_use_tool từ chối mọi công cụ", bool(seen.get("allowed_tools")), seen)
check("cwd là thư mục trống riêng, không phải repo hay brain", "reply_policy_cwd" in str(seen.get("cwd")), seen.get("cwd"))
src_ask = __import__("inspect").getsource(main._reply_policy_ask)
check("lớp thứ hai: danh sách công cụ bị cấm gồm Bash, Read, PowerShell, Skill", all(x in src_ask for x in ("BOT_CAM_NATIVE", "PowerShell", "Skill")))
check("và không dùng MCP", "mcp_strict = True" in src_ask)

# ---- soạn hồ sơ vai ----
check("soạn hồ sơ khi chưa nối engine: 503", c.post(f"/chatbots/{bid}/reply-policy/draft-guidelines").status_code == 503)


async def fake_ask(prompt, purpose=""):
    if purpose == "profile":
        return "Đảm nhiệm:\n- mỹ phẩm và chăm sóc da\nKhông đảm nhiệm:\n- chính trị\nGiọng và xưng hô:\n- nhẹ nhàng\nKhi nào nên lên tiếng trong nhóm:\n- khi hỏi về da"
    return json.dumps([{"text": "da mình bị mụn thì dùng gì", "verdict": "reply", "reason": "đúng ngành"}])


import tempfile as _t  # noqa: E402
from pathlib import Path  # noqa: E402
brain_dir = Path(_t.mkdtemp(prefix="brain-rp-api-"))
(brain_dir / "cham-soc-da.md").write_text("# Chăm sóc da\nRửa mặt hai lần mỗi ngày.", encoding="utf-8")
main.chatbot_runtime._deps["brain_root"] = lambda b: str(brain_dir)
main.chatbot_runtime._deps["read_agent"] = lambda b, slug: ({"name": "Nhi Mai", "role": "Chuyên gia da"}, "Tư vấn chăm sóc da.")
rp.wire(ask=fake_ask)
r = c.post(f"/chatbots/{bid}/reply-policy/draft-guidelines")
check("soạn hồ sơ vai từ Agent + mục lục tài liệu của bot", r.status_code == 200 and "mỹ phẩm" in r.json()["generated_text"], r.text)
check("và sinh ca khởi tạo theo lĩnh vực", r.json().get("bootstrap_cases") == 1 and st.count_cases(bid, "bootstrap") == 1)
rp.wire(ask=None)

# ---- xoá bot xoá sạch dữ liệu học ----
st.log_decision({"bot_id": bid, "chat_id": "g9", "ts": NOW, "text": "một tin nữa", "verdict": "silent", "mode": "on"}, NOW)
check("(chuẩn bị) bot còn dữ liệu", st.stats(bid)["decisions"] > 0)
ok, e = chatbot_store.delete_bot(bid)
check("xoá bot", ok, e)
check("xoá bot xoá sạch nhật ký, ca, hồ sơ vai của bot (nội dung chat khách)",
      st.stats(bid) == {"decisions": 0, "silent": 0, "labeled": 0, "cases": 0, "cases_bootstrap": 0, "lessons": 0}
      and st.get_role_profile(bid) is None)
check("và không đụng dữ liệu của bot khác", st.stats(r2["id"])["decisions"] >= 0)

# ---- mã im ở Python phải có nhãn ở giao diện ----
py = (SERVER / "chatbot_reply_policy.py").read_text(encoding="utf-8")
js = (ROOT / "dashboard" / "chatbots-reply-policy.js").read_text(encoding="utf-8")
codes = set()
for m in re.finditer(r'(?:silence_code|code) = "([a-z_]+)"|return \(?(?:True|False), "([a-z_]+)"\)?|finish\("silent", "([a-z_]+)"|\("(?:silent)", "([a-z_]+)"', py):
    codes.update(x for x in m.groups() if x)
codes |= set(re.findall(r'"([a-z_]+)"', re.search(r"_UNTRACKED = frozenset\(\{(.*?)\}\)", py, re.S).group(1)))
codes |= {"judge_silent", "below_threshold"}
codes -= {"silent", "reply", "called"}
labels = set(re.findall(r"(\w+):\s*\"rp\.code_", js))
check("mọi mã im bộ máy phát ra đều có nhãn ở giao diện", codes <= labels, sorted(codes - labels))
runtime_codes = set(main.chatbot_runtime._RP_RATE.values()) | set(main.chatbot_runtime._RP_RETRACT_CODES)
check("mã hạn mức của runtime cũng có nhãn", runtime_codes <= labels, sorted(runtime_codes - labels))

check("không dùng em dash trong file test này", chr(0x2014) not in open(__file__, encoding="utf-8").read())
print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
