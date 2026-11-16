"""Lệnh "/" hệ thống (server/lenh_he_thong.py + các endpoint /slash/* và /sessions/{id}/compact).

    python tests/python/test_lenh_he_thong.py        (hoặc: python tests/run.py lenh_he_thong)

Không cần API key, không chạm mạng: nhà cung cấp là hàm giả, kho phiên là SQLite tạm.

Phủ: khối chỉ dẫn của /plan và /goal (đúng hình dạng để dashboard và tên hội thoại gỡ được),
hạ mức quyền của lượt /plan xuống `suggest`, /compact ở cả hai họ engine (API: tóm tắt; gói
thuê bao: xoay mạch native), định dạng cho Telegram, và các endpoint mới.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import os
import re
import tempfile
from pathlib import Path

state = tempfile.mkdtemp(prefix="javis-lenh-test-")
os.environ["JAVIS_STATE_DIR"] = state
os.environ["BRAINS_DIR"] = str(Path(state) / "brains")
os.environ["JAVIS_SESSIONS_DB"] = str(Path(state) / "sessions.db")

import lenh_he_thong as L            # noqa: E402
from sessions import SessionStore, title_from_message  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + ((f"  [{them!r}]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- 1. Khối /plan: đúng HÌNH DẠNG mà dashboard và tên hội thoại biết gỡ ----
kp = L.khoi_ke_hoach()
check("plan: mở bằng dấu nhận diện", kp.startswith(L.PLAN_MARK))
check("plan: kết thúc bằng ]\\n\\n (dashboard cắt ở chỗ này)", kp.endswith("]\n\n"))
check("plan: KHÔNG có ] nào giữa khối (cắt sớm là lộ nửa khối ra bong bóng)", kp[:-3].count("]") == 0)
check("plan: nói rõ chỉ đọc, chưa làm gì ra ngoài", "chỉ đọc" in kp and "CHƯA" in kp)
check("plan: nhận ra lượt /plan", L.la_luot_ke_hoach(kp + "dọn kho"))
check("plan: nhận ra dù đứng sau khối ghim/ngữ cảnh khác", L.la_luot_ke_hoach("[FILE ĐANG MỞ trong trình sửa của Javis: /a.md\nx]\n\n" + kp + "dọn kho"))
check("plan: tin thường không bị coi là /plan", not L.la_luot_ke_hoach("dọn kho giúp tôi"))
check("plan: nhắc dấu nhận diện GIỮA câu không phải lệnh", not L.la_luot_ke_hoach("tôi thấy dòng [CHẾ ĐỘ KẾ HOẠCH: trong file"))
check("plan: rỗng/None an toàn", not L.la_luot_ke_hoach("") and not L.la_luot_ke_hoach(None))

# ---- 2. Khối /goal ----
kg = L.khoi_muc_tieu("mọi đơn hôm nay đã đối soát", 2, 5, "còn 8 đơn")
check("goal: mở bằng dấu nhận diện + điều kiện", kg.startswith(L.GOAL_MARK + " mọi đơn hôm nay đã đối soát"))
check("goal: kết thúc bằng ]\\n\\n", kg.endswith("]\n\n"))
check("goal: có vòng hiện tại/tối đa", "vòng 2/5" in kg)
# 0.173.1: trần mặc định 5, vòng tự động mang tình trạng vòng trước và dòng ẩn JAVIS_GOAL_ROUND, dặn báo blocked
check("goal: trần mặc định là 5", L.GOAL_MAX_ROUNDS == 5 and "vòng 1/5" in L.khoi_muc_tieu("x"))
check("goal: vòng 2+ có tình trạng vòng trước và dòng ẩn JAVIS_GOAL_ROUND",
      "Vòng trước còn: còn 8 đơn" in kg and '<!-- JAVIS_GOAL_ROUND: {"v": 2, "n": 5, "left": "còn 8 đơn"} -->' in kg)
check("goal: vòng 1 không có dòng JAVIS_GOAL_ROUND", "JAVIS_GOAL_ROUND" not in L.khoi_muc_tieu("x", 1, 5, "y"))
check("goal: dặn model báo blocked khi thiếu quyền/công cụ/dữ liệu", '"blocked"' in kg and "thiếu quyền" in kg)
check("goal: tình trạng có --> hay ] không phá khối", (lambda k: "-->" not in k.split("JAVIS_GOAL_ROUND")[1].split("-->")[0]
      and k[:-3].count("]") == 0)(L.khoi_muc_tieu("a", 2, 5, "x --> ] y")))
check("goal: dặn model tự báo qua dòng ẩn JAVIS_GOAL", "JAVIS_GOAL" in kg and '"done":true' in kg and '"done":false' in kg)
check("goal: điều kiện chứa ] thì bị đổi (không cắt sớm khối)", (lambda k: k[:-3].count("]") == 0 and "(x)" in k)(L.khoi_muc_tieu("đạt [x]", 1, 8)))
check("goal: điều kiện nhiều dòng gộp về một dòng", "\n" not in L.khoi_muc_tieu("a\n\n  b\tc", 1, 8).split("\n")[0].replace(L.GOAL_MARK, ""))
check("goal: điều kiện dài bị cắt", len(L.khoi_muc_tieu("x" * 5000, 1, 8)) < 1500)

# ---- 3. Đọc dòng ẩn JAVIS_GOAL (bản Python, khớp bản JS) ----
D = L.doc_muc_tieu
check("doc: done true", D('ok <!-- JAVIS_GOAL: {"done":true} -->') == {"done": True, "left": ""})
check("doc: done false + left", D('<!-- JAVIS_GOAL: {"done":false,"left":"thiếu báo cáo"} -->') == {"done": False, "left": "thiếu báo cáo"})
check("doc: blocked kèm lý do", D('<!-- JAVIS_GOAL: {"done":false,"blocked":"thiếu quyền POS"} -->') == {"done": False, "left": "", "blocked": "thiếu quyền POS"})
check("doc: done true bỏ qua blocked", D('<!-- JAVIS_GOAL: {"done":true,"blocked":"x"} -->') == {"done": True, "left": ""})
check("doc: không có -> None", D("không có gì") is None)
check("doc: JSON hỏng -> None", D("<!-- JAVIS_GOAL: {done -->") is None)
check("doc: done không phải bool -> None", D('<!-- JAVIS_GOAL: {"done":1} -->') is None)
check("doc: dòng cuối thắng", D('<!-- JAVIS_GOAL: {"done":false} --> <!-- JAVIS_GOAL: {"done":true} -->')["done"] is True)

# ---- 4. Tên hội thoại: bóc khối /plan, /goal ----
check("tên: /plan dọn kho -> 'dọn kho'", title_from_message(kp + "dọn kho") == "dọn kho", title_from_message(kp + "dọn kho"))
check("tên: /goal -> điều kiện", title_from_message(L.khoi_muc_tieu("đối soát đơn", 1, 8) + "đối soát đơn") == "đối soát đơn")
check("tên: khối ghim đứng trước khối /plan vẫn bóc được", title_from_message("[FILE ĐANG MỞ trong trình sửa của Javis: /a.md\nx]\n\n" + kp + "lập kế hoạch tháng") == "lập kế hoạch tháng")
check("tên: câu mở bằng ngoặc vuông của người dùng KHÔNG bị bóc", title_from_message("[gấp] xem giúp đơn hàng") .startswith("[gấp]"))

# ---- 5. main: hạ mức quyền lượt /plan ----
import main  # noqa: E402

check("quyền: chat thường vẫn full", main._muc_quyen_luot_chat({}, "chào") == "full")
check("quyền: chưa truyền tin vẫn full (chỗ gọi cũ không vỡ)", main._muc_quyen_luot_chat({}) == "full")
check("quyền: lượt /plan hạ xuống suggest", main._muc_quyen_luot_chat({}, kp + "dọn kho") == "suggest")
check("quyền: /plan trong khung chat Coding cũng suggest (siết, không nới)", main._muc_quyen_luot_chat({"id": "x", "channel": "coding:abc"}, kp + "sửa lỗi") == "suggest")
check("quyền: lượt /goal KHÔNG bị siết (goal là làm thật)", main._muc_quyen_luot_chat({}, kg + "làm") == "full")

# ---- 6. /compact ----
tmp = Path(tempfile.mkdtemp(prefix="javis-lenh-nen-"))


def fake_stream(text, goi=None):
    async def _f(prov, key, model, messages, reasoning):
        if goi is not None:
            goi.append(messages[0]["content"])
        yield {"type": "meta", "model": model}
        yield {"type": "text", "content": text}
    return _f


async def chay_nen():
    st = SessionStore(db_path=tmp / "nen.db")

    # (a) ngắn
    s0 = st.create_session(brain="brain")
    for i in range(3):
        st.append_message(s0, "user" if i % 2 == 0 else "assistant", f"m{i}")
    r = await L.nen_phien(st, s0, kind="api", prov="openrouter", api_key="k", model="m", api_stream=fake_stream("T"))
    check("nén: hội thoại ngắn -> ly_do ngan, không tốn request", r["ok"] is False and r["ly_do"] == "ngan" and r["so_tin"] == 3)

    # (b) engine API: gấp phần cũ vào tóm tắt, giữ nguyên 4 tin cuối
    s1 = st.create_session(brain="brain")
    for i in range(12):
        st.append_message(s1, "user" if i % 2 == 0 else "assistant", f"nội dung {i}")
    goi = []
    r = await L.nen_phien(st, s1, kind="api", prov="openrouter", api_key="k", model="m", api_stream=fake_stream("TÓM TẮT 1", goi))
    sess = st.get_session(s1)
    check("nén API: có tóm tắt", r["ok"] and r["cach"] == "tom_tat", r)
    check("nén API: gấp 8 tin đầu, giữ 4 tin cuối", sess["compact_count"] == 8 and sess["compact_summary"] == "TÓM TẮT 1")
    check("nén API: prompt tóm tắt có tin cũ, không có 4 tin giữ nguyên", "nội dung 0" in goi[-1] and "nội dung 7" in goi[-1] and "nội dung 11" not in goi[-1])
    r2 = await L.nen_phien(st, s1, kind="api", prov="openrouter", api_key="k", model="m", api_stream=fake_stream("KHÔNG GỌI", goi))
    check("nén API: gọi lại ngay -> da_gon, KHÔNG tốn thêm request", r2["ok"] and r2["cach"] == "da_gon" and len(goi) == 1, r2)

    # (c) nhà cung cấp lỗi
    s2 = st.create_session(brain="brain")
    for i in range(12):
        st.append_message(s2, "user" if i % 2 == 0 else "assistant", f"n{i}")

    async def loi(prov, key, model, messages, reasoning):
        yield {"type": "error", "content": "provider chết"}
    r = await L.nen_phien(st, s2, kind="api", prov="openrouter", api_key="k", model="m", api_stream=loi)
    check("nén API: provider lỗi -> ok False (loi_tom_tat), không ghi tóm tắt rác", r["ok"] is False and r["ly_do"] == "loi_tom_tat" and not (st.get_session(s2).get("compact_summary") or ""), r)

    # (d) nhà API chưa kiểm chứng đường tóm tắt / thiếu key
    r = await L.nen_phien(st, s2, kind="api", prov="ollama-local", api_key="k", model="m", api_stream=fake_stream("T"))
    check("nén API: nhà chưa hỗ trợ -> khong_ho_tro (không nén bừa)", r["ok"] is False and r["ly_do"] == "khong_ho_tro")
    r = await L.nen_phien(st, s2, kind="api", prov="openrouter", api_key="", model="m", api_stream=fake_stream("T"))
    check("nén API: thiếu key -> khong_ho_tro", r["ok"] is False and r["ly_do"] == "khong_ho_tro")

    # (e) engine gói thuê bao: vứt mạch native, lượt sau mồi lại từ transcript
    s3 = st.create_session(brain="brain")
    for i in range(6):
        st.append_message(s3, "user" if i % 2 == 0 else "assistant", f"c{i}")
    st.set_cli_session_id(s3, "claude-thread-1")
    st.set_codex_thread_id(s3, "codex-thread-1")
    st.set_last_input_tokens(s3, 800_000)
    r = await L.nen_phien(st, s3, kind="cli", prov="anthropic-cli", api_key="", model="opus", api_stream=fake_stream("KHÔNG GỌI", goi))
    sess = st.get_session(s3)
    check("nén thuê bao: xoay mạch", r["ok"] and r["cach"] == "xoay_mach", r)
    check("nén thuê bao: mạch Claude và Codex đều bị vứt", not sess.get("cli_session_id") and not sess.get("codex_thread_id"))
    check("nén thuê bao: thước ngữ cảnh về 0", int(sess.get("last_input_tokens") or 0) == 0)
    check("nén thuê bao: có ghi mốc xoay (chống xoay dồn dập)", int(sess.get("thread_rotated_msg") or 0) == int(sess.get("msg_count") or 0) > 0)
    check("nén thuê bao: KHÔNG tốn request tóm tắt (không có API key)", len(goi) == 1)
    check("nén thuê bao: transcript còn nguyên để mồi lại mạch mới", len(st.get_messages(s3)) == 6)

    # (f) engine không giữ mạch riêng
    r = await L.nen_phien(st, s3, kind="cli", prov="antigravity-cli", api_key="", model="m", api_stream=fake_stream("T"))
    check("nén thuê bao: không còn mạch nào -> khong_co_mach (nói thật, không khoe đã nén)", r["ok"] and r["cach"] == "khong_co_mach", r)


asyncio.run(chay_nen())

# ---- 7. Định dạng cho Telegram ----
check("gon_so", L.gon_so(950) == "950" and L.gon_so(84300) == "84,3k" and L.gon_so(1_250_000) == "1,25M" and L.gon_so(None) == "0")
mu = L.dinh_dang_muc_dung(
    {"today": {"total": {"turns": 3, "in": 12000, "out": 900, "cost": 0},
               "items": [{"provider": "anthropic-cli", "model": "opus", "turns": 3, "in": 12000, "out": 900}]},
     "all_time": {"total": {"turns": 40, "in": 1_000_000, "out": 50_000, "cost": 1.5}}},
    {"remaining": 4.2})
check("Telegram usage: có hôm nay, tổng và số dư", "Hôm nay: 3 lượt" in mu and "Từ trước tới nay: 40 lượt" in mu and "$4.20" in mu, mu)
check("Telegram usage: không in $0.00 khi gói thuê bao (không có chi phí)", "$0.00" not in mu)
check("Telegram usage: rỗng vẫn nói được", "chưa có lượt nào" in L.dinh_dang_muc_dung({}))
vt = L.dinh_dang_viec({"orchestration": "off", "columns": {"running": [{"title": "Đối soát"}], "todo": [{"title": "Gửi báo cáo"}, {"title": "Dọn kho"}]}, "completed_24h": 3, "counts": {}})
check("Telegram tasks: nhóm + cảnh báo tự vận hành tắt", "Đang chạy (1)" in vt and "Chờ làm (2)" in vt and "TẮT" in vt and "Đối soát" in vt, vt)
check("Telegram tasks: trống", "Không có việc nào" in L.dinh_dang_viec({"orchestration": "auto", "columns": {}}))
check("Telegram tasks: cắt bớt khi quá nhiều", "và 2 việc nữa" in L.dinh_dang_viec({"columns": {"running": [{"title": f"v{i}"} for i in range(7)]}}, moi_cot=5))
check("Telegram memory: cắt cho vừa một tin", len(L.dinh_dang_bo_nho("x" * 9000, 3000)) < 3200)
check("Telegram memory: trống thì hướng dẫn", "memory/MEMORY.md" in L.dinh_dang_bo_nho(""))

# ---- 8. Endpoint mới ----
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

app = FastAPI()
app.post("/sessions/{session_id}/compact")(main.sessions_compact)
app.get("/slash/status")(main.slash_status)
app.get("/slash/memory")(main.slash_memory)
app.post("/slash/block")(main.slash_block)
client = TestClient(app)

r = client.post("/slash/block", data={"kind": "plan"})
check("POST /slash/block plan trả đúng khối của server", r.status_code == 200 and r.json()["block"] == L.khoi_ke_hoach())
r = client.post("/slash/block", data={"kind": "goal", "dk": "đối soát xong", "vong": "3", "toi_da": "8"})
check("POST /slash/block goal có vòng 3/8", r.status_code == 200 and "vòng 3/8" in r.json()["block"] and "đối soát xong" in r.json()["block"])
check("POST /slash/block goal thiếu điều kiện -> 400", client.post("/slash/block", data={"kind": "goal", "dk": "  "}).status_code == 400)
check("POST /slash/block kind lạ -> 400", client.post("/slash/block", data={"kind": "xyz"}).status_code == 400)
r = client.post("/slash/block", data={"kind": "goal", "dk": "a", "vong": "999", "toi_da": "999"})
check("POST /slash/block kẹp trần vòng (không cho model chạy vô hạn)", "vòng 20/20" in r.json()["block"], r.json())
# 2026-11-16: what the owner typed while the goal ran rides in every later round's block.
r = client.post("/slash/block", data={"kind": "goal", "dk": "báo cáo tuần", "vong": "2", "toi_da": "6",
                                      "left": "còn email", "them": '["tính cả Shopee", "gửi trước 9 giờ ]"]'})
_b = r.json()["block"]
check("POST /slash/block goal mang lời bổ sung của chủ", "đã bổ sung trong lúc mục tiêu chạy" in _b
      and "- tính cả Shopee" in _b and "- gửi trước 9 giờ )" in _b and _b.index("tính cả Shopee") < _b.index("JAVIS_GOAL_ROUND"), _b)
r = client.post("/slash/block", data={"kind": "goal", "dk": "a", "them": "không phải json"})
check("POST /slash/block them hỏng thì bỏ qua", r.status_code == 200 and "bổ sung" not in r.json()["block"])
_b = L.khoi_muc_tieu("a", 2, 5, "", [str(i) for i in range(9)])
check("khối giữ tối đa 5 lời bổ sung, mới nhất", "- 8\n" in _b and "- 3\n" not in _b and "- 4\n" in _b)
check("khối không có lời bổ sung thì như cũ", L.khoi_muc_tieu("a", 2, 5, "x") == L.khoi_muc_tieu("a", 2, 5, "x", []))

st = main.get_store()
sid = st.create_session(brain="brain")
r = client.get("/slash/status", params={"session_id": sid})
d = r.json()
check("GET /slash/status: có engine, model, brain, phiên bản", r.status_code == 200 and d["provider"] and "brain" in d and d["version"] == main._app_version() and d["running"] is False, d)
check("GET /slash/status: phiên chưa ghim model -> pinned False", d["pinned"] is False)
st.set_pinned_model(sid, "openrouter", "x/y")
check("GET /slash/status: phiên ghim model -> pinned True", client.get("/slash/status", params={"session_id": sid}).json()["pinned"] is True)
check("GET /slash/status: không truyền phiên vẫn trả được (chat trống)", client.get("/slash/status").status_code == 200)

check("POST compact: phiên không tồn tại -> 404", client.post("/sessions/khong-co/compact").status_code == 404)
r = client.post(f"/sessions/{sid}/compact")
check("POST compact: phiên còn ngắn -> ok False ly_do ngan (200, không phải lỗi)", r.status_code == 200 and r.json()["ok"] is False and r.json()["ly_do"] == "ngan", r.json())

# phiên đang chạy -> 409
class _Job:
    class task:
        @staticmethod
        def done():
            return False
main._CHAT_RUNTIME._jobs[sid] = type("J", (), {"task": _Job.task, "tag": "t", "text": ""})()
check("POST compact: phiên đang trả lời -> 409 (không đổi lịch sử dưới chân lượt đang chạy)", client.post(f"/sessions/{sid}/compact").status_code == 409)
main._CHAT_RUNTIME._jobs.pop(sid, None)

# /slash/memory
brain_dir = Path(main._brain_root("brain"))
(brain_dir / "memory" / "facts").mkdir(parents=True, exist_ok=True)
(brain_dir / "memory" / "MEMORY.md").write_text("# Bộ nhớ\n- [Khách A](facts/a.md) - hay mua sỉ\n", encoding="utf-8")
(brain_dir / "memory" / "facts" / "a.md").write_text("x", encoding="utf-8")
r = client.get("/slash/memory")
check("GET /slash/memory: trả mục lục + số file chi tiết", r.status_code == 200 and "Khách A" in r.json()["text"] and r.json()["facts"] == 1 and r.json()["cat_bot"] is False, r.json())
(brain_dir / "memory" / "MEMORY.md").write_text("x" * 30000, encoding="utf-8")
r = client.get("/slash/memory").json()
check("GET /slash/memory: file quá dài bị cắt và báo cat_bot", len(r["text"]) == 20000 and r["cat_bot"] is True)
(brain_dir / "memory" / "MEMORY.md").unlink()
check("GET /slash/memory: chưa có file -> text rỗng, không lỗi", client.get("/slash/memory").json()["text"] == "")

# ---- 9. Telegram: menu lệnh và trợ giúp nói cùng một bộ ----
import telegram_bot  # noqa: E402

menu_tg = {c["command"] for c in telegram_bot.BOT_COMMANDS}
check("Telegram: menu có usage/tasks/memory/plan", {"usage", "tasks", "memory", "plan"} <= menu_tg)
check("Telegram: tên lệnh hợp lệ (a-z0-9_, <= 32 ký tự)", all(re.fullmatch(r"[a-z0-9_]{1,32}", c) for c in menu_tg))
check("Telegram: mô tả lệnh <= 256 ký tự", all(1 <= len(c["description"]) <= 256 for c in telegram_bot.BOT_COMMANDS))
tro_giup = asyncio.run(main._tg_help_text("brain"))
check("Telegram: /help nhắc bốn lệnh mới", all(f"/{c}" in tro_giup for c in ("usage", "tasks", "memory", "plan")))


async def tg(cmd, arg=""):
    return await main._tg_command(cmd, arg, chat="test-chat")


r = asyncio.run(tg("plan", "dọn kho"))
check("Telegram /plan <việc>: chạy một lượt thật kèm khối chỉ đọc", "ask" in r and r["ask"].startswith(L.PLAN_MARK) and r["ask"].endswith("dọn kho"), r)
r = asyncio.run(tg("plan"))
check("Telegram /plan trống: hướng dẫn, KHÔNG chạy lượt nào", "reply" in r and "ask" not in r)
r = asyncio.run(tg("memory"))
check("Telegram /memory: trả lời được khi brain chưa có bộ nhớ", "reply" in r and "memory/MEMORY.md" in r["reply"], r)
r = asyncio.run(tg("usage"))
check("Telegram /usage: trả lời được", "reply" in r and "Mức dùng" in r["reply"], r)
r = asyncio.run(tg("tasks"))
check("Telegram /tasks: trả lời được", "reply" in r and "Việc nền" in r["reply"], r)

# ---- 10. Không em dash trong file mới (luật toàn dự án) ----
for f in (SERVER / "lenh_he_thong.py", Path(__file__)):
    check(f"không em dash: {f.name}", chr(0x2014) not in f.read_text(encoding="utf-8"))

if _fails:
    print(f"\nFAIL - test_lenh_he_thong: {len(_fails)} lỗi")
    raise SystemExit(1)
print("\nOK - test_lenh_he_thong: tất cả pass")
