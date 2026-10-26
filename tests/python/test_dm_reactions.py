"""T2 (0.154.0): reaction ở chat riêng qua đường host thật (main.app, TestClient). Hợp đồng docs/dev/team-chat-t2-contract.md
mục 4; thiết kế 2026-10-15 mục 4.1, 4.3.

    python tests/run.py dm_reactions -v

Không model nào được gọi: chốt chặn làm test DỪNG NGAY nếu có đường nào dựng engine thật (engine nhóm, engine chat
Claude/Codex, engine Cộng hưởng). Các ca: sáu giá trị, đổi/bỏ, nonce gửi lại, nonce của tin khác 409, tin không phải câu
trả lời 409, content_sha/seen_sha (stale), lịch sử mang reaction, gói WS chat_reaction và turn_saved, giữ qua mở lại kho,
khối phản hồi vào lượt `agent:<slug>` kế tiếp của ĐÚNG trợ lý, mốc bật lại Cộng hưởng ở route chủ và lệnh trưởng nhóm.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import inspect
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-dm-react-")
os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)
BR = Path(tempfile.mkdtemp(prefix="javis-dm-react-brain-"))
(BR / "agents").mkdir()
for slug, name in (("lan", "Lan"), ("minh", "Minh")):
    (BR / "agents" / f"{slug}.md").write_text(f"---\nname: {name}\nrole: Trợ lý\n---\nBạn là {name}.\n",
                                              encoding="utf-8", newline="\n")

import main  # noqa: E402
import agent_ledger as AL  # noqa: E402
import resonance_store as RS  # noqa: E402
import sessions  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


class RealEngineUsed(AssertionError):
    pass


def _no_real_engine(*a, **k):
    raise RealEngineUsed("test tried to build a REAL engine; reactions must never call a model")


# Chốt: không đường nào tới model thật.
main.team_engine.build = _no_real_engine
main.claude_engine = _no_real_engine
main.CodexCLI = _no_real_engine
main._resonance_engine = _no_real_engine

sent = []


async def fake_publish(ev):
    sent.append(ev)


main._CHAT_RUNTIME.publish = fake_publish
c = TestClient(main.app, base_url="http://127.0.0.1:8080")
store = main.get_store()
Q = f"?brain={BR}"
rs = main._resonance_store()
OWNER = RS.Principal("owner", "owner", main._brain_key(str(BR)))

S_LAN = store.create_session(brain=str(BR), channel="agent:lan")
S_MINH = store.create_session(brain=str(BR), channel="agent:minh")
S_MAIN = store.create_session(brain=str(BR))
u1 = store.append_message(S_LAN, "user", "Viết giúp bài giới thiệu")
a1 = store.append_message(S_LAN, "assistant", "Đây là bài giới thiệu của Lan")
a2 = store.append_message(S_LAN, "assistant", "Bản thứ hai của Lan")
am = store.append_message(S_MINH, "assistant", "Câu trả lời của Minh")
ax = store.append_message(S_MAIN, "assistant", "Câu của Javis")


def post(sid, mid, body):
    return c.post(f"/sessions/{sid}/messages/{mid}/reaction{Q}", json=body)


SIX = ("like", "love", "haha", "wow", "sad", "angry")
for i, v in enumerate(SIX):
    r = post(S_LAN, a1, {"value": v, "nonce": f"six-{i}"})
    check(f"chọn {v}: 200, lưu nguyên giá trị", r.status_code == 200 and r.json()["reaction"]["value"] == v, r.text)
R = r.json()["reaction"]
check("khuôn R đúng hợp đồng (đủ trường, không thừa)", set(R) == {"value", "reasons", "axis", "comment", "stale",
                                                                  "status", "status_reason", "source_kind", "revision",
                                                                  "updated_at"} and R["source_kind"] == "owner"
      and R["revision"] == 6, R)
check("trợ lý tắt Cộng hưởng: 'Đã nhận, chỉ lưu' kèm lý do Cộng hưởng đang tắt", R["status"] == "stored_only"
      and ("đang tắt" in R["status_reason"] or "is off" in R["status_reason"]), R)
r = post(S_LAN, a1, {"value": "none", "reasons": ["too_long"], "axis": "should_silent", "comment": "Gọn hơn",
                     "nonce": "change"})
R = r.json()["reaction"]
check("đổi: bỏ emoji, giữ lý do, trục nói/im, góp ý", R["value"] is None and R["reasons"] == ["too_long"]
      and R["axis"] == "should_silent" and R["comment"] == "Gọn hơn", R)
n_log = len(store.dm_reaction_log(S_LAN, a1))
n_sent = len(sent)
r = post(S_LAN, a1, {"value": "love", "nonce": "change"})
check("gửi lại cùng nonce: 200, trả trạng thái hiện tại, không ghi thêm dòng, không đẩy WS",
      r.status_code == 200 and r.json()["reaction"]["comment"] == "Gọn hơn"
      and len(store.dm_reaction_log(S_LAN, a1)) == n_log and len(sent) == n_sent, r.text)
r = post(S_LAN, a2, {"value": "love", "nonce": "change"})
check("nonce đã dùng cho tin khác: 409", r.status_code == 409 and r.json()["ok"] is False, r.text)
r = post(S_LAN, a1, {"value": None, "reasons": [], "axis": "", "comment": "", "nonce": "clear"})
check("bỏ hết: reaction null", r.status_code == 200 and r.json()["reaction"] is None, r.text)
log = store.dm_reaction_log(S_LAN, a1)
check("nhật ký trước/sau của lần bỏ", log[-1]["next"] is None and log[-1]["prev"]["comment"] == "Gọn hơn")
for label, sid, mid, body, code in (
        ("tin của người dùng", S_LAN, u1, {"value": "like", "nonce": "u"}, 409),
        ("tin không có", S_LAN, 999999, {"value": "like", "nonce": "x"}, 404),
        ("tin của phiên khác", S_LAN, am, {"value": "like", "nonce": "y"}, 404),
        ("phiên không có", "khong-co", a1, {"value": "like", "nonce": "z"}, 404),
        ("giá trị lạ", S_LAN, a1, {"value": "thumbs", "nonce": "b1"}, 400),
        ("lý do lạ", S_LAN, a1, {"value": "like", "reasons": ["hay"], "nonce": "b2"}, 400),
        ("trục lạ", S_LAN, a1, {"value": "like", "axis": "loud", "nonce": "b3"}, 400),
        ("góp ý quá 500", S_LAN, a1, {"value": "like", "comment": "x" * 501, "nonce": "b4"}, 400),
        ("nonce rỗng", S_LAN, a1, {"value": "like", "nonce": ""}, 400),
        ("nonce quá 100", S_LAN, a1, {"value": "like", "nonce": "n" * 101}, 400)):
    r = post(sid, mid, body)
    check(f"{label}: {code}", r.status_code == code and r.json().get("ok") is False, (r.status_code, r.text))

# content_sha, seen_sha, lịch sử
page = c.get(f"/sessions/{S_LAN}/messages").json()["messages"]
sha_a2 = hashlib.sha256("Bản thứ hai của Lan".encode("utf-8")).hexdigest()
m2 = next(m for m in page if m["id"] == a2)
check("GET messages: mỗi tin có content_sha của nội dung đã lưu", m2["content_sha"] == sha_a2
      and all(m.get("content_sha") for m in page))
check("GET messages: tin assistant có reaction (null khi chưa có), tin user không có khoá reaction",
      "reaction" in m2 and m2["reaction"] is None
      and "reaction" not in next(m for m in page if m["id"] == u1))
r = post(S_LAN, a2, {"value": "wow", "nonce": "seen-ok", "seen_sha": sha_a2})
check("seen_sha khớp: stale false", r.json()["reaction"]["stale"] is False)
r = post(S_LAN, a2, {"value": "sad", "reasons": ["wrong_facts"], "comment": "Sai số liệu", "nonce": "seen-old",
                     "seen_sha": "hash-cu"})
check("seen_sha lệch: stale true, vẫn nhận", r.status_code == 200 and r.json()["reaction"]["stale"] is True)
page = c.get(f"/sessions/{S_LAN}/messages").json()["messages"]
check("lịch sử mang reaction (F5)", next(m for m in page if m["id"] == a2)["reaction"]["value"] == "sad")
full = c.get(f"/sessions/{S_LAN}?limit=10").json()["messages"]
check("GET /sessions/{id}?limit= (mở phiên từ lịch sử) cũng mang reaction và content_sha mọi tin",
      next(m for m in full if m["id"] == a2)["reaction"]["value"] == "sad"
      and all(m.get("content_sha") for m in full)
      and next(m for m in full if m["id"] == a2)["content_sha"] == sha_a2
      and "reaction" not in next(m for m in full if m["id"] == u1)
      and next(m for m in full if m["id"] == a1)["reaction"] is None, full[:2])
whole = c.get(f"/sessions/{S_LAN}").json()["messages"]
check("GET /sessions/{id} (không limit) cũng vậy", next(m for m in whole if m["id"] == a2)["reaction"]["value"] == "sad"
      and all(m.get("content_sha") for m in whole))
ev = [e for e in sent if e.get("type") == "chat_reaction" and e.get("message_id") == a2]
check("gói WS chat_reaction sau mỗi lần ghi, mang R", len(ev) == 2 and ev[-1]["session_id"] == S_LAN
      and ev[-1]["reaction"]["value"] == "sad", ev)
store2 = sessions.SessionStore(db_path=store.db_path)
check("giữ qua mở lại kho (restart)", store2.dm_reaction_of(S_LAN, a2)["value"] == "sad")

# tác giả và trang chính
pin = rs.session_pin(S_LAN)
lan = rs.agent(main._brain_key(str(BR)), "lan")
check("tác giả do host tra: phiên agent:lan ghim vào mã của Lan (Cộng hưởng vẫn tắt)",
      pin and lan and pin["agent_key"] == lan["agent_key"] and lan["enabled"] is False
      and store.dm_reaction_of(S_LAN, a2)["agent_key"] == lan["agent_key"])
r = post(S_MAIN, ax, {"value": "like", "nonce": "main-1"})
check("trang Trò chuyện chính: lưu, agent rỗng, trạng thái 'Đã nhận'", r.json()["reaction"]["status"] == "received"
      and store.dm_reaction_of(S_MAIN, ax)["agent_key"] == "")

# turn_saved sau khi lưu lượt
sent.clear()
mid_saved = asyncio.run(main._persist_turn(store, S_LAN, str(BR), "hỏi tiếp", "Trả lời mới.\n<!-- JAVIS_ASK: {} -->"))
ts_ev = [e for e in sent if e.get("type") == "turn_saved"]
saved = store.message_row(S_LAN, mid_saved) if isinstance(mid_saved, int) else None
check("_persist_turn trả mã tin câu trả lời", isinstance(mid_saved, int) and saved and saved["role"] == "assistant")
check("gói turn_saved {session_id, message_id, content_sha của nội dung đã lưu}", len(ts_ev) == 1
      and ts_ev[0]["session_id"] == S_LAN and ts_ev[0]["message_id"] == mid_saved
      and ts_ev[0]["content_sha"] == sessions.content_sha(saved["content"]), ts_ev)
_pt = inspect.getsource(main._persist_turn)
check("turn_saved được CHỜ gửi xong trong _persist_turn (không create_task), nên luôn đi trước turn_done",
      'await _CHAT_RUNTIME.publish({"type": "turn_saved"' in _pt)
_body = inspect.getsource(main)
_rt = _body.index("async def run_turn(")
_end = min(x for x in (_body.find("\nasync def ", _rt + 10), _body.find("\ndef ", _rt + 10)) if x != -1)
_seg = _body[_body.index("async def _do_turn("):_end]   # _do_turn lưu lượt, run_turn gửi turn_done sau khi nó trả về
_persists = [i for i in range(len(_seg)) if _seg.startswith("await _persist_turn(", i)]
check("mọi chỗ lưu lượt trong _do_turn có gói turn_done ĐI SAU (turn_saved trước turn_done)",
      _persists and all(_seg.find('"turn_done"', i) != -1 for i in _persists), len(_persists))
check("_persist_turn rỗng: không lưu, trả None", asyncio.run(main._persist_turn(store, S_LAN, str(BR), "u", "")) is None)

# khối phản hồi ở lượt agent:<slug> kế tiếp, chỉ đúng trợ lý
post(S_MINH, am, {"value": "angry", "comment": "MINH_ONLY_FEEDBACK", "nonce": "minh-1"})
p_lan = main._agent_turn_system_prompt(str(BR), "lan", S_LAN)
p_minh = main._agent_turn_system_prompt(str(BR), "minh", S_MINH)
check("lượt agent:lan kế tiếp có khối phản hồi của chủ (emoji, lý do, góp ý, đoạn trích, câu dặn)",
      "Phản hồi gần đây của chủ" in p_lan and "😢 (sad)" in p_lan and "Sai dữ kiện" in p_lan and "Sai số liệu" in p_lan
      and "Bản thứ hai của Lan" in p_lan and "đừng coi là chấm điểm" in p_lan, p_lan[-900:])
check("khối phản hồi của trợ lý khác không lọt vào lượt của Lan", "MINH_ONLY_FEEDBACK" not in p_lan)
check("lượt agent:minh chỉ thấy phản hồi của Minh", "MINH_ONLY_FEEDBACK" in p_minh and "Sai số liệu" not in p_minh)
S_LAN2 = store.create_session(brain=str(BR), channel="agent:lan")
check("phiên chat riêng khác của cùng trợ lý dùng chung ngữ cảnh dm:<agent_key>",
      "Sai số liệu" in main._agent_turn_system_prompt(str(BR), "lan", S_LAN2))
src = inspect.getsource(main)
check("lượt chat trợ lý ghép khối phản hồi giống hệt _agent_turn_system_prompt",
      "_agent_chat_prompt(brain, _persona[1], conv_sid=conv_sid, skill_served=skill_served)\n" in src
      and "+ _session_block(conv_sid)\n" in src
      and "+ _dm_feedback_prompt(brain, _persona[1], conv_sid)\n" in src
      # T3 phần L: cả hai chỗ còn ghép bài học phạm vi chat riêng + chung.
      and "+ _dm_lessons_prompt(brain, _persona[1], conv_sid))" in src
      and "return (_agent_chat_prompt(brain, slug, channel, conv_sid) + _session_block(conv_sid)"
      "\n            + _dm_feedback_prompt(brain, slug, conv_sid)"
      "\n            + _dm_lessons_prompt(brain, slug, conv_sid))" in src)

# Cộng hưởng bật: route của chủ ghi resumed_at; phản hồi mới tạo một lý do
r = c.post(f"/resonance/agents/toggle{Q}", json={"slug": "lan", "enabled": True})
check("route bật Cộng hưởng của chủ: 200", r.status_code == 200, r.text)
check("route của chủ ghi resumed_at", (rs.resumed_at(lan["agent_key"]) or 0) > 0)
W = AL.WakeReasons(rs)
r = post(S_LAN, a1, {"value": "love", "nonce": "on-1"})
r2 = post(S_LAN, a2, {"value": "like", "nonce": "on-2"})
rr = W.reasons(agent_key=lan["agent_key"])
check("Cộng hưởng bật: 'Chờ xem xét', hai lần bấm gom một lý do ở dm:<agent_key>",
      r.json()["reaction"]["status"] == "pending_review" and len(rr) == 1
      and rr[0]["context_ref"] == f"dm:{lan['agent_key']}" and len(W.sources(rr[0]["id"])) == 2, rr)
new_logs = {f"rx:dm:{store.dm_reaction_of(S_LAN, a1)['log_id']}", f"rx:dm:{store.dm_reaction_of(S_LAN, a2)['log_id']}"}
check("phản hồi cũ (trước khi bật) không được phát lại: nguồn chỉ là hai lần bấm mới",
      {x["source_ref"] for x in W.sources(rr[0]["id"])} == new_logs)
minh = rs.agent(main._brain_key(str(BR)), "minh")
res = main._TeamAdmin().set_resonance(str(BR), "minh", True, "leader:test")
check("lệnh set_resonance của trưởng nhóm ghi resumed_at", res.get("enabled") is True
      and (rs.resumed_at(minh["agent_key"]) or 0) > 0, res)

# ═════ review T2 P3: tra tác giả SAU khi kiểm thân và nonce; kho resonance lỗi không làm mất reaction ═════
(BR / "agents" / "hoa.md").write_text("---\nname: Hoa\nrole: Trợ lý\n---\nBạn là Hoa.\n", encoding="utf-8", newline="\n")
S_HOA = store.create_session(brain=str(BR), channel="agent:hoa")
ah = store.append_message(S_HOA, "assistant", "Câu trả lời của Hoa")
BK = main._brain_key(str(BR))
r = post(S_HOA, ah, {"value": "thumbs", "nonce": "hoa-bad"})
check("review T2 P3: request 400 không cấp mã trợ lý, không ghim phiên", r.status_code == 400
      and rs.agent(BK, "hoa") is None and not rs.session_pin(S_HOA), (r.status_code, rs.agent(BK, "hoa")))
check("review T2 P3: lỗi 400 theo ngôn ngữ giao diện, không lẫn câu tiếng Việt khi đang tiếng Anh",
      "reaction" in r.json()["error"].lower())
_orig_author = main._dm_reaction_author


def _author_down(sess):
    raise RuntimeError("resonance store is locked")


main._dm_reaction_author = _author_down
r = post(S_HOA, ah, {"value": "love", "nonce": "hoa-down"})
main._dm_reaction_author = _orig_author
R = r.json().get("reaction") or {}
log_row = store.dm_reaction_log(S_HOA, ah)[-1]
check("review T2 P3: kho resonance lỗi lúc tra tác giả: reaction VẪN lưu (200), trạng thái Đã nhận kèm lý do",
      r.status_code == 200 and R.get("value") == "love" and R.get("status") == "received" and R.get("status_reason"), r.text)
check("review T2 P3: dòng nhật ký chờ tra tác giả, chưa chiếu", log_row.get("effect_state") == "pending_author", log_row)
n_fix = main._dm_resolve_pending_authors()
main._feedback_projector().project_pending()
after = store.dm_reaction_of(S_HOA, ah)
check("review T2 P3: nhịp sau tra lại được tác giả, chiếu xong (Hoa tắt Cộng hưởng: chỉ lưu)",
      n_fix == 1 and after["agent_key"] and after["status"] == "stored_only"
      and store.dm_reaction_log(S_HOA, ah)[-1]["effect_state"] == "done", (n_fix, after))
r = post(S_HOA, ah, {"value": "love", "nonce": "hoa-down"})
check("review T2 P3: gửi lại cùng nonce sau đó vẫn 200, không ghi thêm dòng", r.status_code == 200
      and len(store.dm_reaction_log(S_HOA, ah)) == 1, r.text)

# Review T2 vòng 2: một dòng chờ tác giả lỗi mãi không chặn các dòng sau.
(BR / "agents" / "tu.md").write_text("---\nname: Tu\nrole: Trợ lý\n---\nBạn là Tu.\n", encoding="utf-8", newline="\n")
S_TU = store.create_session(brain=str(BR), channel="agent:tu")
at_ = store.append_message(S_TU, "assistant", "Câu trả lời của Tu")
S_BAD = store.create_session(brain=str(BR), channel="agent:hoa")
ab_ = store.append_message(S_BAD, "assistant", "Câu của phiên lỗi mãi")
main._dm_reaction_author = _author_down
post(S_BAD, ab_, {"value": "like", "nonce": "bad-1"})
post(S_TU, at_, {"value": "like", "nonce": "tu-1"})


def _author_bad_only(sess):
    if sess.get("id") == S_BAD:
        raise RuntimeError("phiên này lỗi mãi")
    return _orig_author(sess)


main._dm_reaction_author = _author_bad_only
n_fix2 = main._dm_resolve_pending_authors()
main._dm_reaction_author = _orig_author
check("review T2 vòng 2: dòng lỗi mãi bị bỏ qua, dòng sau vẫn được tra tác giả", n_fix2 == 1
      and store.dm_reaction_log(S_TU, at_)[-1]["effect_state"] == "pending"
      and store.dm_reaction_log(S_BAD, ab_)[-1]["effect_state"] == "pending_author", n_fix2)

# Quyết định của chủ (0.168.0): tin đẩy về (tin báo goal, kết quả việc nền) mang mã tin để có ngay hàng sáu cảm xúc.
n_before = len(sent)
ok_push = asyncio.run(main.push_to_chat(S_LAN, "Báo cáo mục tiêu: đã xong bản nháp"))
push_ev = [e for e in sent[n_before:] if e.get("type") == "push"]
stored = store.get_messages(S_LAN)[-1]
check("tin đẩy về mang message_id và content_sha khớp tin đã lưu (có nút cảm xúc không cần F5)",
      ok_push and push_ev and push_ev[-1].get("message_id") == stored["id"]
      and push_ev[-1].get("content_sha") == sessions.content_sha(stored["content"]), (push_ev[-1:], stored.get("id")))
r = post(S_LAN, stored["id"], {"value": "love", "nonce": "push-1"})
check("thả cảm xúc lên tin đẩy về: 200", r.status_code == 200 and r.json()["reaction"]["value"] == "love", r.text)

print(f"\n{'FAIL' if fails else 'PASS'} - test_dm_reactions: {len(fails)} lỗi")
raise SystemExit(1 if fails else 0)
