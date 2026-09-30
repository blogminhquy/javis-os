"""Bộ phán xử hội thoại nhóm trên Zalo cá nhân, ĐẦU-CUỐI (0.65.0): MCP giả, model giả, bot thật.

    python tests/run.py reply_policy_zalo      (KHÔNG mạng)

Kịch bản gốc (chủ dự án 30/09/2026): nhóm Zalo, chế độ Tự đánh giá, gọi "javis vũ ơi" không có @ thì
bot im và không để lại dòng nhật ký nào. Sau bản này:
  1. Gọi tên trơn được trả lời, KỂ CẢ khi bộ phán xử tắt (đây là sửa lỗi nhận diện, áp cho mọi bot).
  2. Bộ phán xử tắt thì hành vi và kho dữ liệu y như cũ: không sinh file kho nào.
  3. Bật lên thì mọi tin nhóm đều có dấu vết, kể cả tin bị im.
  4. Im nhầm -> bị hỏi lại -> lần sau CÙNG loại tin bot nói. Chen nhầm -> bị nhắc -> ngưỡng nâng.
  5. Tin nối tiếp sau lượt bot vừa trả lời được hiểu là hỏi tiếp cho bot.
  6. Chỉ CHỦ mới dạy được luật; người lạ thì không.
  7. Chạy thử ghi lại quyết định của người phán xử nhưng luật cũ vẫn là bên quyết.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-rp-zalo-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels  # noqa: E402,F401
import chatbot_reply_policy as rp  # noqa: E402
import chatbot_reply_policy_store as st  # noqa: E402
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


CONN = {"id": "zalo-1", "label": "Javis Vũ", "connector_id": "zalo"}
NHOM = "5550001"
BOSS = "7770099"
UID_A, UID_B = "7770001", "7770002"
THREADS = [{"threadId": NHOM, "name": "Lớp Javis OS", "type": "group"}]
GUI, KHO_TIN, LUOT_ENGINE = [], [], []
TRA_LOI = {"v": "Dạ để em hướng dẫn nhé"}


def _ms(giay_truoc=0):
    return int((time.time() - giay_truoc) * 1000)


async def _goi_gia(conn, tool, args):
    if tool == "zalo_send_message":
        GUI.append(dict(args))
        return {"success": True}
    if tool == "zalo_list_threads":
        return {"threads": [dict(t) for t in THREADS]}
    if tool == "zalo_get_messages":
        tin = list(KHO_TIN)
        KHO_TIN.clear()
        return {"messages": tin, "nextCursor": "c" + str(time.time())}
    return {}


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = _goi_gia
zc.NHUONG_GIAY = 0.02
zc.THU_LAI_TEN_GIAY = 0
import chatbot_tu_dong  # noqa: E402
chatbot_tu_dong.KHOANG_CACH_GIAY = 0      # test không chờ 20 giây giữa hai lần bot tự nói
chatbot_tu_dong.TRAN_NGUOI_GIO = 99
chatbot_tu_dong.TRAN_NHOM_GIO = 99


async def _engine(text, meta, progress, *, channel="", bot=None):
    LUOT_ENGINE.append({"text": text, "meta": dict(meta or {})})
    return {"text": TRA_LOI["v"], "files": []}


BRAIN = Path(tempfile.mkdtemp(prefix="brain-rp-zalo-"))
(BRAIN / "cai-dat.md").write_text(
    "# Hướng dẫn cài đặt Javis\n\n## Lỗi cổng 7777 đang được dùng\n\nNếu Javis báo lỗi cổng 7777 đang được dùng, "
    "hãy tắt tiến trình Javis cũ rồi khởi động lại bằng file start-javis.bat.\n\n## Đổi bộ não của Javis\n\n"
    "Vào trang Models, chọn bộ não mới ở mục Model chính rồi bấm Lưu.\n", encoding="utf-8")
chatbot_runtime.wire(answer=_engine, brain_root=lambda b: str(BRAIN),
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Trợ lý cài đặt Javis"}, "Trả lời ngắn gọn."))


class Judge:
    """Người phán xử giả. `mode`: silent | reply | learn (nói nếu prompt có ca 'label:missed' về cổng 7777)."""

    def __init__(self):
        self.mode = "silent"
        self.prompts = []
        self.teach = {"is_teaching": False}

    async def __call__(self, prompt, purpose=""):
        if purpose == "profile":
            return ("Đảm nhiệm:\n- cài đặt và lỗi phần mềm Javis\nKhông đảm nhiệm:\n- chuyện riêng\n"
                    "Giọng và xưng hô:\n- thân thiện\nKhi nào nên lên tiếng trong nhóm:\n- khi hỏi về Javis")
        if purpose == "bootstrap":
            return json.dumps([{"text": "javis lỗi cổng thì làm sao", "verdict": "reply", "reason": "đúng ngành"},
                               {"text": "trưa nay ăn gì", "verdict": "silent", "reason": "chuyện phiếm"}])
        if purpose == "teach":
            return json.dumps(self.teach)
        self.prompts.append(prompt)
        ex = prompt.split("## Ca tương tự")[1].split("## Cuộc trò chuyện")[0] if "## Ca tương tự" in prompt else ""
        if self.mode == "learn":
            say = "label:missed" in ex and "7777" in ex
            return json.dumps({"verdict": "reply" if say else "silent", "score": 0.9 if say else 0.3, "reason": "học"})
        if self.mode == "reply":
            return json.dumps({"verdict": "reply", "score": 0.9, "reason": "ok"})
        return json.dumps({"verdict": "silent", "score": 0.3, "reason": "chưa chắc"})


J = Judge()
rp.wire(ask=J)


def msg(text, mid, nguoi="Học viên A", uid=UID_A, giay_truoc=2, **them):
    m = {"threadId": NHOM, "from": uid, "senderName": nguoi, "type": "text", "text": text, "id": mid,
         "ts": _ms(giay_truoc), "threadType": 1}
    m.update(them)
    return m


async def doc(cho=0.3):
    await zc.doc_mot_lan(dict(CONN))
    # Máy CI chậm thì lượt trả lời chạy nền chưa xong sau một mốc ngủ cố định (đã đỏ một lần trên CI ở 0.65.3, cùng SHA xanh
    # ở lần chạy kia). Chờ đúng các lượt đang chạy (`_VIEC`) xong, tối đa 6 giây, rồi mới ngủ thêm `cho`.
    t0 = time.time()
    while zc._VIEC and time.time() - t0 < 6:
        await asyncio.sleep(0.02)
    await asyncio.sleep(cho)


def sach():
    GUI.clear()
    zc._TAY.clear()


bid, loi = chatbot_store.create_bot({"name": "Javis Vũ", "agent_slug": "lan", "brain": "b", "account_ids": ["zalo-1"],
                                     "muc_quyen": "suggest", "reply_when": "mention", "groups": [NHOM]})
check("tạo được bot cho nhóm (chưa chọn Tự đánh giá)", bool(bid) and not loi, loi)
check("bot mới không cần khai gì: bộ phán xử tự vận hành (bật, có học)",
      chatbot_store.get_bot(bid)["reply_policy"]["mode"] == "on"
      and chatbot_store.get_bot(bid)["reply_policy"]["learning_enabled"] is True)


async def chay():
    ok, err = chatbot_runtime.start_bot(bid)
    check("bật bot", ok, err)

    # ---------- 1. Sửa lỗi gốc: gọi tên trơn, bot chưa ở chế độ Tự đánh giá ---------------------
    KHO_TIN.append(msg("javis vũ ơi", "a1"))
    await doc()
    check("gọi tên trơn 'javis vũ ơi' được trả lời (bản trước im lặng)", len(GUI) == 1 and GUI[0]["threadId"] == NHOM, GUI)
    check("và gửi kiểu nhóm (type=1)", GUI and GUI[0]["type"] == 1)
    sach()
    KHO_TIN.append(msg("alo javis vu giup minh voi", "a2"))
    await doc()
    check("không dấu cũng nhận ra", len(GUI) == 1, GUI)
    sach()
    n0 = len(LUOT_ENGINE)
    KHO_TIN.append(msg("hôm nay trời đẹp thật mọi người", "a3"))
    KHO_TIN.append(msg("nhờ ai đó xem giúp mình cái này với @Nam", "a4"))
    await doc()
    check("tin không gọi bot thì vẫn im như cũ", not GUI and len(LUOT_ENGINE) == n0, GUI)
    check("chưa chọn Tự đánh giá: KHÔNG sinh file kho nào (không lưu nội dung chat)", not st.db_path().exists())

    # ---------- 2. Chọn Tự đánh giá: bộ phán xử tự chạy, không ô cài đặt nào ------------------------
    chatbot_store.update_bot(bid, {"reply_when": "auto", "reply_policy": {"trainer_ids": [BOSS], "mode": "off"}})
    rpc = chatbot_store.get_bot(bid)["reply_policy"]
    check("chọn Tự đánh giá là chạy (khoá cũ mode=off bị bỏ qua), người được dạy lưu đủ",
          rpc["mode"] == "on" and rpc["learning_enabled"] and rpc["trainer_ids"] == [BOSS], rpc)
    chatbot_store.update_bot(bid, {"reply_policy": {"mode": "bay-gio", "eagerness": "ồn ào"}})
    rpc = chatbot_store.get_bot(bid)["reply_policy"]
    check("bản vá khoá cũ hoặc giá trị lạ không đổi hành vi và không xoá người được dạy",
          rpc["mode"] == "on" and rpc["eagerness"] == "medium" and rpc["trainer_ids"] == [BOSS], rpc)

    sach()
    n0 = len(LUOT_ENGINE)
    KHO_TIN.append(msg("hôm nay trời đẹp thật mọi người", "b1", giay_truoc=9))
    await doc()
    check("chuyện phiếm: im", not GUI and len(LUOT_ENGINE) == n0)
    ds = st.recent_decisions(bid)
    check("chuyện phiếm: CÓ dấu vết (mã no_signal)", any(d["silence_code"] == "no_signal" and d["text"].startswith("hôm nay trời") for d in ds), ds)
    check("tốn 0 lượt model cho chuyện phiếm", J.prompts == [])

    KHO_TIN.append(msg("javis vũ ơi giúp anh cái", "b2", giay_truoc=8))
    await doc()
    check("bật rồi, gọi tên trơn vẫn trả lời và KHÔNG tốn lượt phán xử", len(GUI) == 1 and J.prompts == [], (GUI, len(J.prompts)))
    check("lượt gọi tên có dòng nhật ký 'called'", any((d["reason"] or "").startswith("called") for d in st.recent_decisions(bid)))
    sach()

    # Im nhầm rồi bị hỏi lại.
    J.mode = "silent"
    Q = "Javis báo lỗi cổng 7777 đang bị dùng thì làm sao ạ?"
    KHO_TIN.append(msg(Q, "b3", giay_truoc=6, uid=UID_A))
    await doc()
    check("câu hỏi có tài liệu nhưng model chưa chắc: im", not GUI and len(J.prompts) == 1, (GUI, len(J.prompts)))
    d_im = next(d for d in st.recent_decisions(bid) if d["text"] == Q)
    check("dấu vết ghi đúng: judge_silent, có điểm và ngưỡng", d_im["silence_code"] == "judge_silent"
          and d_im["score"] == 0.3 and abs(d_im["threshold"] - 0.60) < 1e-6, d_im)
    check("đang theo dõi hậu quả", len(st.open_watches(bid, NHOM)) == 1)

    KHO_TIN.append(msg("sao không trả lời mình vậy", "b4", giay_truoc=1, uid=UID_A))
    await doc()
    check("cùng người hỏi lại: gắn nhãn missed", st.get_decision(d_im["id"])["label"] == "missed", st.get_decision(d_im["id"]))
    check("ngưỡng của nhóm này hạ xuống", st.get_offset(bid, NHOM) < 0, st.get_offset(bid, NHOM))
    check("thành ca: nên trả lời", [c["correct_verdict"] for c in st.list_cases(bid) if c["source"] == "auto"] == ["reply"])
    sach()

    # Lần sau CÙNG loại tin: bot nói ngay, không chờ đợt tổng hợp nào.
    J.mode = "learn"
    n_p = len(J.prompts)
    KHO_TIN.append(msg("Javis báo lỗi cổng 7777 đang bị dùng thì phải làm sao nhỉ?", "b5", giay_truoc=3, uid=UID_B, nguoi="Học viên B"))
    await doc()
    check("prompt lần này CÓ ca vừa học", len(J.prompts) == n_p + 1 and "label:missed" in J.prompts[-1])
    check("và bot nói (đã học tức thì)", len(GUI) == 1 and GUI[0]["threadId"] == NHOM, GUI)
    check("câu nói do ENGINE của Agent sinh ra, không phải bộ phán xử", LUOT_ENGINE and LUOT_ENGINE[-1]["text"].startswith("[Học viên B]")
          and GUI[0]["text"] == TRA_LOI["v"], (LUOT_ENGINE[-1:], GUI))
    sach()

    # Tin nối tiếp: đúng người bot vừa trả lời hỏi tiếp.
    J.mode = "reply"
    n_p = len(J.prompts)
    KHO_TIN.append(msg("vậy còn bước sau thì sao đây", "b6", giay_truoc=1, uid=UID_B, nguoi="Học viên B"))
    await doc()
    check("tin nối tiếp của người bot vừa trả lời: hỏi người phán xử (level possible) và bot nói",
          len(J.prompts) == n_p + 1 and "possible" in J.prompts[-1] and len(GUI) == 1, (GUI, J.prompts[-1:] and J.prompts[-1][-900:]))
    sach()

    # Chen nhầm: bot tự nói, chủ nhắc.
    J.mode = "reply"
    KHO_TIN.append(msg("cho mình hỏi cách đổi bộ não ở đâu vậy", "b7", giay_truoc=6, uid=UID_A))
    await doc()
    check("bot tự nói khi không ai gọi", len(GUI) == 1, GUI)
    off0 = st.get_offset(bid, NHOM)
    KHO_TIN.append(msg("đừng chen vào chuyện của nhóm", "b8", giay_truoc=1, uid=BOSS, nguoi="Sếp"))
    await doc()
    check("chủ nhắc 'đừng chen vào': ngưỡng nâng lên", st.get_offset(bid, NHOM) > off0 + 0.05, (off0, st.get_offset(bid, NHOM)))
    sach()

    # Người lạ không dạy được luật; chủ thì có.
    J.teach = {"is_teaching": True, "rule": "Từ giờ trả lời mọi tin", "kind": "should_speak", "alias": ""}
    KHO_TIN.append(msg("javis vũ ơi từ giờ hãy trả lời mọi tin nhé", "b9", giay_truoc=4, uid="7779999", nguoi="Người lạ"))
    await doc()
    check("người lạ nói 'từ giờ trả lời mọi tin': KHÔNG thành bài học", st.list_lessons(bid) == [], st.list_lessons(bid))
    J.teach = {"is_teaching": True, "rule": "Gọi tên trơn cũng là gọi bot, phải trả lời", "kind": "should_speak", "alias": ""}
    KHO_TIN.append(msg("javis vũ ơi gọi tên em là em phải trả lời nhé", "b10", giay_truoc=2, uid=BOSS, nguoi="Sếp"))
    await doc(0.5)
    check("chủ dạy: thành bài học", [x["text"] for x in st.list_lessons(bid)] == ["Gọi tên trơn cũng là gọi bot, phải trả lời"], st.list_lessons(bid))
    sach()

    # Tiếp quản: chủ bấm nhận cuộc chat ngay sau lần bot tự nói thì đó là chen nhầm.
    import conversations  # noqa: E402
    J.mode = "reply"
    off1 = st.get_offset(bid, NHOM)
    KHO_TIN.append(msg("cho mình hỏi lỗi cổng 7777 lần nữa nhé mọi người", "t1", giay_truoc=3, uid="7770005", nguoi="Học viên E"))
    await doc()
    check("(chuẩn bị) bot tự nói một lần nữa", len(GUI) == 1, GUI)
    d_tq = next(d for d in st.recent_decisions(bid, 50) if d["text"].startswith("cho mình hỏi lỗi cổng 7777 lần nữa"))
    with conversations._conn() as cx:
        conv_id = cx.execute("SELECT id FROM conversations WHERE external_chat_id=?", (NHOM,)).fetchone()[0]
    conversations.dat_che_do(conv_id, "human")
    check("Tiếp quản ngay sau lần bot tự nói: gắn nhãn intruded", st.get_decision(d_tq["id"])["label"] == "intruded",
          st.get_decision(d_tq["id"]))
    check("và ngưỡng của nhóm nâng lên", st.get_offset(bid, NHOM) > off1, (off1, st.get_offset(bid, NHOM)))
    conversations.dat_che_do(conv_id, "ai")
    sach()

    # Hồ sơ vai được soạn ở nền từ Agent của chính bot.
    await asyncio.sleep(0.3)
    prof = st.get_role_profile(bid)
    check("hồ sơ vai được soạn ở nền", prof and "Đảm nhiệm" in prof["generated_text"], prof)
    check("và ca khởi tạo theo lĩnh vực của bot", st.count_cases(bid, "bootstrap") == 2, st.count_cases(bid, "bootstrap"))
    check("máy tự biết bot có tài liệu để tra (căn cứ tự chọn: phải có tài liệu khớp mới tự nói)",
          chatbot_runtime._RP_HAS_DOCS.get(bid) is True, chatbot_runtime._RP_HAS_DOCS)

    # ---------- 3. Chạy thử: luật cũ quyết, người phán xử chỉ ghi -------------------------------
    os.environ["JAVIS_REPLY_POLICY_SHADOW"] = "1"      # công tắc của người vận hành, không phải của chủ bot
    J.mode = "silent"
    n_dec = len(st.recent_decisions(bid, 500))
    KHO_TIN.append(msg("Bước cài đặt Node như nào mọi người, lỗi cổng 7777 nữa", "c1", giay_truoc=3, uid="7770003", nguoi="Học viên C"))
    await doc(0.6)
    check("chạy thử: luật cũ vẫn quyết (câu hỏi có tài liệu nên bot nói)", len(GUI) == 1, GUI)
    sh = [d for d in st.recent_decisions(bid, 500) if d["mode"] == "shadow"]
    check("chạy thử: người phán xử vẫn ghi lại quyết định của nó (mode=shadow, nói im)", sh and sh[0]["verdict"] == "silent", sh)
    check("chạy thử: không mở cửa theo dõi", st.open_watches(bid, NHOM) == [])
    del os.environ["JAVIS_REPLY_POLICY_SHADOW"]
    sach()

    # Khi không ở chế độ Tự đánh giá thì bộ phán xử vô hiệu, nhưng gọi tên trơn vẫn được nhận.
    chatbot_store.update_bot(bid, {"reply_when": "mention"})
    n_dec = len(st.recent_decisions(bid, 500))
    KHO_TIN.append(msg("javis vũ ơi cho hỏi chút", "d1", giay_truoc=2))
    KHO_TIN.append(msg("cho mình hỏi cách đổi bộ não ở đâu vậy", "d2", giay_truoc=1, uid="7770004"))
    await doc()
    check("reply_when=mention: gọi tên trơn được trả lời, tin còn lại im", len(GUI) == 1, GUI)
    check("reply_when=mention: bộ phán xử không ghi thêm dòng nào cho tin không ai gọi", len(st.recent_decisions(bid, 500)) == n_dec)

    # #6a: bộ phán xử nói reply nhưng Agent chọn im ([IM_LANG]): quyết định phải được sửa thành im, cửa theo dõi đóng.
    chatbot_store.update_bot(bid, {"reply_when": "auto"})      # bước trước để mention
    J.mode = "reply"
    TRA_LOI["v"] = "[IM_LANG]"
    n_gui = len(GUI)
    KHO_TIN.append(msg("cho mình hỏi cách đổi bộ não ở đâu vậy", "im1", giay_truoc=3, uid="7770007", nguoi="Học viên G"))
    await doc()
    TRA_LOI["v"] = "Dạ để em hướng dẫn nhé"
    d_im = next(d for d in st.recent_decisions(bid, 50) if d["msg_id"] == "im1")
    check("Agent chọn im: không gửi gì", len(GUI) == n_gui, GUI)
    check("quyết định bị RÚT LẠI thành im, mã agent_silent (không còn ghi là bot đã nói)",
          d_im["verdict"] == "silent" and d_im["silence_code"] == "agent_silent", d_im)
    check("và không còn cửa theo dõi (tin nối tiếp sẽ không được gắn nhãn 'đúng' cho lời chưa từng nói)",
          all(w["id"] != d_im["id"] for w in st.open_watches(bid, NHOM)))
    sach()

    # #6b: chủ đã Tiếp quản thì kiểm TRƯỚC khi tốn lượt model; tin khách vẫn vào Hộp thư cho người trực đọc.
    import conversations  # noqa: E402
    with conversations._conn() as cx:
        conv_id2 = cx.execute("SELECT id FROM conversations WHERE external_chat_id=?", (NHOM,)).fetchone()[0]
    conversations.dat_che_do(conv_id2, "human")
    n_p = len(J.prompts)
    KHO_TIN.append(msg("cho mình hỏi lỗi cổng 7777 lần cuối nhé mọi người", "tq1", giay_truoc=2, uid="7770008", nguoi="Học viên H"))
    await doc()
    check("đã Tiếp quản: bot im và KHÔNG tốn lượt phán xử", not GUI and len(J.prompts) == n_p, (GUI, len(J.prompts) - n_p))
    d_tq2 = next(d for d in st.recent_decisions(bid, 50) if d["text"].startswith("cho mình hỏi lỗi cổng 7777 lần cuối"))
    check("nhật ký ghi mã taken_over", d_tq2["silence_code"] == "taken_over", d_tq2)
    with conversations._conn() as cx:
        vao_hop_thu = cx.execute("SELECT COUNT(*) FROM messages WHERE text LIKE ?", ("%lần cuối nhé mọi người%",)).fetchone()[0]
    check("tin khách VẪN vào Hộp thư cho người trực đọc", vao_hop_thu >= 1, vao_hop_thu)
    conversations.dat_che_do(conv_id2, "ai")
    sach()

    # Bộ phán xử ném lỗi bất ngờ ở lớp vận chuyển: rơi về luật cũ, KHÔNG được nuốt tin (tin gọi tên vẫn được trả lời).
    chatbot_store.update_bot(bid, {"reply_when": "auto"})
    orig = chatbot_runtime.PolicyHooks.prepare

    def _boom(self, text, meta, owner_typing=False):
        raise RuntimeError("hỏng bất ngờ")

    chatbot_runtime.PolicyHooks.prepare = _boom
    sach()
    KHO_TIN.append(msg("@Javis Vũ cho hỏi lỗi cổng 7777 với", "z1", giay_truoc=2, uid="7770006", nguoi="Học viên F"))
    await doc()
    chatbot_runtime.PolicyHooks.prepare = orig
    check("prepare ném lỗi: tin gọi tên VẪN được trả lời bằng luật cũ", len(GUI) == 1, GUI)
    sach()

    # ---------- 0.65.1: luật lên tiếng viết tay của 0.65.0 (form không còn ô đó) gộp vào BÀI HỌC ----------
    NL = chr(10)
    before = {x["text"] for x in st.list_lessons(bid)}
    chatbot_store.update_bot(bid, {"reply_policy": {"guidelines": "- Chỉ nói về phần mềm Javis" + NL + "* Không chen chuyện riêng của thành viên"}})
    chatbot_runtime._rp_profile(chatbot_store.get_bot(bid), with_role=False)
    got = {x["text"] for x in st.list_lessons(bid)} - before
    check("luật cũ thành bài học, từng dòng một",
          got == {"Chỉ nói về phần mềm Javis", "Không chen chuyện riêng của thành viên"}, got)
    check("và chữ cũ được xoá khỏi cấu hình (không áp dụng hai lần)",
          chatbot_store.get_bot(bid)["reply_policy"]["guidelines"] == "")
    n_les = len(st.list_lessons(bid))
    chatbot_runtime._rp_profile(chatbot_store.get_bot(bid), with_role=False)
    check("chạy lại không thêm bài học nữa", len(st.list_lessons(bid)) == n_les)

    chatbot_runtime.stop_bot(bid)


asyncio.run(chay())

check("không dùng em dash trong file test này", chr(0x2014) not in open(__file__, encoding="utf-8").read())
print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
