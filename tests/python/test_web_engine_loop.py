"""Vòng lặp tool của engine Web, chạy bằng TRANSPORT GIẢ - không trình duyệt, không mạng.

    python tests/run.py web_engine_loop

Vì sao test bằng transport giả: phần dễ sai của engine Web không nằm ở Chromium (lớp 4 đã
chứng minh đoạn tee chạy thật) mà nằm ở CHỖ NỐI - khi nào dừng, khi nào sửa khuôn, khi nào
cắt vì kẹt, và sự kiện nào bay ra cho dashboard. Nhét trình duyệt vào đây là biến một phép
thử một giây thành một phép thử ba mươi giây mà không soi thêm được gì.

Ba bất biến phải giữ, vì hỏng cái nào cũng là hỏng thầm lặng:
  1. Lượt KHÔNG BAO GIỜ chạy vô hạn: hết vòng, hết giờ, hay kẹt vòng lặp đều phải ra `final`.
  2. Một tool hỏng KHÔNG giết cả lượt - model phải đọc được câu lỗi và đi tiếp.
  3. KHÔNG có sự kiện `usage`: web không trả số token, bịa một con số còn tệ hơn không có.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-webeng-")
os.environ["JAVIS_ENABLE_WEB_CHAT"] = "true"

import web_engine as we  # noqa: E402
import web_state  # noqa: E402
import web_tool_protocol as wtp  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ============================================================
# Đồ giả
# ============================================================

class KetQuaGia:
    def __init__(self, ok=True, text="", error="", kind="", thread_id="t1"):
        self.ok, self.text, self.error, self.kind = ok, text, error, kind
        self.thread_id, self.elapsed, self.chunks = thread_id, 0.1, []


class TransportGia:
    """Trả lần lượt các câu đã dựng sẵn. Ghi lại mọi tin nhắn đã nhận để soi prompt."""

    def __init__(self, tra_loi):
        self.tra_loi = list(tra_loi)
        self.da_gui = []
        self.thread_da_hoi = []
        self.da_dung = False
        self.luong_moi_lan = 0

    def gui(self, prompt, timeout_s=180.0, on_chunk=None, thread_id=""):
        self.da_gui.append(prompt)
        self.thread_da_hoi.append(thread_id)
        if not self.tra_loi:
            return KetQuaGia(ok=False, error="hết câu dựng sẵn", kind=web_state.TEMPORARY_ERROR)
        kq = self.tra_loi.pop(0)
        return kq() if callable(kq) else kq

    def dung(self):
        self.da_dung = True

    def luong_moi(self):
        self.luong_moi_lan += 1


def khoi(*calls):
    """Dựng một câu trả lời có khối gọi tool."""
    return "```javis_tool\n" + json.dumps({"calls": list(calls)}) + "\n```"


def lam_engine(tra_loi, route=None, tools=None, **kw):
    tr = TransportGia(tra_loi)
    e = we.WebEngine(transport=tr, tools=tools or [{"fn": "doc"}], route=route or {}, **kw)
    # Bỏ qua kiểm tra playwright: phép thử này soi vòng lặp, không soi môi trường.
    e.is_available = lambda: True
    return e, tr


def chay(engine, prompt="xin chào"):
    async def _go():
        return [ev async for ev in engine.query(prompt)]
    return asyncio.run(_go())


def loai(evs):
    return [e["type"] for e in evs]


def cuoi(evs):
    return next((e for e in reversed(evs) if e["type"] == "final"), None)


def route_gia(bang):
    """bang: {tên tool: hàm(args) -> chuỗi hoặc raise}."""
    def boc(f):
        async def _c(args):
            r = f(args)
            return r
        return {"call": _c, "source_type": "builtin", "effect": "read"}
    return {k: boc(v) for k, v in bang.items()}


def sach_so():
    web_state.dat_lai()


# ============================================================
# 1) Đường thẳng: trả lời luôn, không tool
# ============================================================

sach_so()
e, tr = lam_engine([KetQuaGia(text="Chào anh, em đây.")])
evs = chay(e)
check("trả lời thẳng: có text rồi final", loai(evs)[-2:] == ["text", "final"])
check("trả lời thẳng: đúng nguyên văn", cuoi(evs)["content"] == "Chào anh, em đây.")
check("mở luồng mới thì báo session", any(x["type"] == "session" for x in evs))
check("KHÔNG có sự kiện usage (web không trả số token)",
      not any(x["type"] == "usage" for x in evs))
check("có dòng trạng thái để màn hình không đứng im suốt vài chục giây",
      any(x["type"] == "progress" for x in evs))
check("dòng trạng thái nói rõ đang ở vòng nào",
      any("vòng 1" in (x.get("content") or "") for x in evs if x["type"] == "progress"))
check("chỉ tốn ĐÚNG một tin nhắn web", len(tr.da_gui) == 1)

check("tin đầu có nhét lời dẫn khuôn tool", wtp.TOOL_PROTOCOL_VERSION in tr.da_gui[0])
check("tin đầu có câu hỏi của người dùng", "xin chào" in tr.da_gui[0])

e2, tr2 = lam_engine([KetQuaGia(text="ừ")], instructions="BẠN LÀ JAVIS.")
chay(e2)
check("tin đầu có instructions (web không có system role nên phải nhét vào đây)",
      "BẠN LÀ JAVIS." in tr2.da_gui[0])
check("thứ tự: vai trò trước, câu hỏi sau",
      tr2.da_gui[0].index("BẠN LÀ JAVIS.") < tr2.da_gui[0].index("xin chào"))


# ============================================================
# 2) Một tool rồi trả lời
# ============================================================

sach_so()
goi = []
rt = route_gia({"doc": lambda a: goi.append(a) or "nội dung file: abc"})
e, tr = lam_engine([KetQuaGia(text=khoi({"name": "doc", "arguments": {"path": "a.py"}})),
                    KetQuaGia(text="File đó chứa abc.")], route=rt)
evs = chay(e)
check("một tool: có sự kiện tool_call", any(x["type"] == "tool_call" for x in evs))
check("một tool: tên tool đúng",
      [x["name"] for x in evs if x["type"] == "tool_call"] == ["doc"])
check("một tool: tham số tới được tool", goi == [{"path": "a.py"}])
check("một tool: câu trả lời cuối là lượt SAU khi có kết quả",
      cuoi(evs)["content"] == "File đó chứa abc.")
check("kết quả tool được gửi lại vào tin nhắn thứ hai", "nội dung file: abc" in tr.da_gui[1])
check("vòng đầu chưa có luồng -> transport được bảo mở cuộc MỚI",
      tr.thread_da_hoi[0] == "")
check("vòng sau gõ vào ĐÚNG cuộc vừa mở (không để hai hội thoại trộn mạch)",
      tr.thread_da_hoi[1] == "t1")


# ============================================================
# 3) Gộp nhiều tool trong MỘT vòng
# ============================================================

sach_so()
rt = route_gia({"a": lambda x: "A", "b": lambda x: "B", "c": lambda x: "C"})
e, tr = lam_engine([KetQuaGia(text=khoi({"name": "a", "arguments": {}},
                                        {"name": "b", "arguments": {}},
                                        {"name": "c", "arguments": {}})),
                    KetQuaGia(text="xong")], route=rt)
evs = chay(e)
check("gộp 3 tool: ba sự kiện tool_call",
      [x["name"] for x in evs if x["type"] == "tool_call"] == ["a", "b", "c"])
check("gộp 3 tool: CHỈ tốn thêm MỘT tin nhắn web (đây là lý do gộp)", len(tr.da_gui) == 2)
check("gộp 3 tool: cả ba kết quả trong cùng một tin",
      all(k in tr.da_gui[1] for k in ("A", "B", "C")))


# ============================================================
# 4) Tool hỏng: không giết lượt
# ============================================================

sach_so()
def _no(a):
    raise RuntimeError("ổ cứng bốc khói")

rt = route_gia({"xau": _no})
e, tr = lam_engine([KetQuaGia(text=khoi({"name": "xau", "arguments": {}})),
                    KetQuaGia(text="Thôi em đi đường khác.")], route=rt)
evs = chay(e)
check("tool nổ: lượt VẪN chạy tiếp, không thành error", cuoi(evs) is not None)
check("tool nổ: model đọc được câu lỗi",
      "ERROR" in tr.da_gui[1] and "ổ cứng bốc khói" in tr.da_gui[1])
check("tool nổ: trả lời cuối vẫn về được", cuoi(evs)["content"] == "Thôi em đi đường khác.")

sach_so()
e, tr = lam_engine([KetQuaGia(text=khoi({"name": "khong_co", "arguments": {}})),
                    KetQuaGia(text="ok")], route=route_gia({"co_that": lambda a: "x"}))
evs = chay(e)
check("tool không tồn tại: báo lỗi nói được chứ không nổ",
      "không có tool 'khong_co'" in tr.da_gui[1])
check("tool không tồn tại: có kể tên tool đang có", "co_that" in tr.da_gui[1])


# ============================================================
# 5) Khuôn hỏng: ĐÚNG một lượt sửa
# ============================================================

sach_so()
rt = route_gia({"doc": lambda a: "ND"})
e, tr = lam_engine([KetQuaGia(text="```javis_tool\n{khong-phai-json\n```"),
                    KetQuaGia(text=khoi({"name": "doc", "arguments": {}})),
                    KetQuaGia(text="đã sửa được")], route=rt)
evs = chay(e)
check("khuôn hỏng rồi sửa được: lượt đi tiếp bình thường",
      cuoi(evs) and cuoi(evs)["content"] == "đã sửa được")
check("lượt sửa là một tin nhắn nhắc khuôn", "[JAVIS]" in tr.da_gui[1])

sach_so()
e, tr = lam_engine([KetQuaGia(text="```javis_tool\n{hong\n```"),
                    KetQuaGia(text="```javis_tool\n{van hong\n```"),
                    KetQuaGia(text="lẽ ra không tới đây")], route=rt)
evs = chay(e)
check("sửa một lượt vẫn hỏng: DỪNG, không sửa mãi", loai(evs)[-1] == "error")
check("chỉ nhắc sửa ĐÚNG một lần (2 tin, không phải 3)", len(tr.da_gui) == 2)
check("câu lỗi có gợi ý đổi model", "model" in evs[-1]["content"].lower())


# ============================================================
# 6) Kẹt vòng lặp: _LapGuard cắt
# ============================================================

sach_so()
check("có nạp được _LapGuard của engine API (không tự viết phanh thứ hai)",
      we._nap_lap_guard() is not None)

lap = KetQuaGia(text=khoi({"name": "doc", "arguments": {"path": "a"}}))
e, tr = lam_engine([lambda: KetQuaGia(text=khoi({"name": "doc", "arguments": {"path": "a"}}))
                    for _ in range(20)], route=rt)
evs = chay(e)
f = cuoi(evs)
check("gọi y hệt mãi: bị CẮT chứ không chạy hết 30 vòng", f is not None)
check("cắt vì kẹt: nói rõ lý do", f and "kẹt vòng lặp" in f["content"])
check("cắt sớm hơn nhiều so với trần vòng", len(tr.da_gui) <= 7)

sach_so()
e, tr = lam_engine([KetQuaGia(text=khoi({"name": "doc", "arguments": {"path": "a"}})),
                    KetQuaGia(text=khoi({"name": "doc", "arguments": {"path": "b"}})),
                    KetQuaGia(text=khoi({"name": "doc", "arguments": {"path": "a"}})),
                    KetQuaGia(text="xong")], route=rt)
evs = chay(e)
check("đọc a, đọc b, đọc lại a: KHÔNG bị bắt oan là kẹt",
      cuoi(evs) and cuoi(evs)["content"] == "xong")


# ============================================================
# 7) Trần vòng và ngân sách thời gian
# ============================================================

sach_so()
os.environ["JAVIS_WEB_MAX_TOOL_ROUNDS"] = "3"
try:
    check("trần vòng đọc từ biến môi trường", we._tran_vong() == 3)
    # Tham số đổi mỗi vòng nên _LapGuard không cắt; chỉ trần vòng cắt được.
    e, tr = lam_engine([KetQuaGia(text=khoi({"name": "doc", "arguments": {"path": str(i)}}))
                        for i in range(10)], route=rt)
    evs = chay(e)
    f = cuoi(evs)
    check("hết trần vòng: ra final chứ không treo", f is not None)
    check("hết trần vòng: nói rõ câu trả lời có thể còn dở",
          f and "hết 3 vòng" in f["content"])
    check("hết trần vòng: đúng 3 tin nhắn web", len(tr.da_gui) == 3)
finally:
    os.environ.pop("JAVIS_WEB_MAX_TOOL_ROUNDS", None)

os.environ["JAVIS_WEB_MAX_TOOL_ROUNDS"] = "khong-phai-so"
check("trần vòng rác -> về mặc định, không nổ", we._tran_vong() == we.MAX_VONG_MAC_DINH)
os.environ["JAVIS_WEB_MAX_TOOL_ROUNDS"] = "99999"
check("trần vòng vô lý bị kẹp lại", we._tran_vong() <= 120)
os.environ.pop("JAVIS_WEB_MAX_TOOL_ROUNDS", None)

os.environ["JAVIS_WEB_TURN_BUDGET_S"] = "1"
check("ngân sách quá bé bị nâng lên sàn (1 giây là vô nghĩa)", we._ngan_sach() >= 30)
os.environ["JAVIS_WEB_TURN_BUDGET_S"] = "rác"
check("ngân sách rác -> mặc định", we._ngan_sach() == float(we.TURN_BUDGET_MAC_DINH))
os.environ.pop("JAVIS_WEB_TURN_BUDGET_S", None)

sach_so()
import time as _t
goc = we.time.time
_dong_ho = {"t": goc()}
we.time = type("T", (), {"time": staticmethod(lambda: _dong_ho["t"])})()
try:
    def nhay():
        _dong_ho["t"] += 400.0
        return KetQuaGia(text=khoi({"name": "doc", "arguments": {"path": str(_dong_ho["t"])}}))

    e, tr = lam_engine([nhay for _ in range(10)], route=rt)
    evs = chay(e)
    f = cuoi(evs)
    check("hết ngân sách thời gian: ra final chứ không chạy tiếp", f is not None)
    check("hết giờ: nói rõ đã quá bao nhiêu giây", f and "giây" in f["content"])
    check("hết giờ cắt TRƯỚC khi chạm trần vòng", len(tr.da_gui) < 10)
finally:
    we.time = _t


# ============================================================
# 8) Transport hỏng: ghi sổ trạng thái, không nuốt lỗi
# ============================================================

sach_so()
e, tr = lam_engine([KetQuaGia(ok=False, error="Bạn đã đạt giới hạn tin nhắn",
                              kind=web_state.USAGE_LIMITED)])
evs = chay(e)
check("transport hỏng: ra error", loai(evs)[-1] == "error")
check("transport hỏng: đưa nguyên câu của trang cho người dùng",
      "giới hạn" in evs[-1]["content"])
check("transport hỏng: có GHI SỔ để lượt sau còn biết mà nghỉ",
      web_state.doc().last_error_kind == web_state.USAGE_LIMITED)

e2, tr2 = lam_engine([KetQuaGia(text="lẽ ra không chạy")])
evs2 = chay(e2)
check("đang nghỉ: CHẶN TRƯỚC, không mở trình duyệt", len(tr2.da_gui) == 0)
check("đang nghỉ: nói rõ còn nghỉ bao lâu", "phút" in evs2[-1]["content"])

sach_so()
e, tr = lam_engine([KetQuaGia(text="ổn")])
chay(e)
check("chạy xong thì ghi nhận thành công", web_state.doc().state == web_state.READY)
check("có đếm số lượt trong ngày", web_state.doc().so_luot_trong_ngay >= 1)


# ============================================================
# 9) Cắt kết quả tool quá dài
# ============================================================

sach_so()
rt_dai = route_gia({"quet": lambda a: "X" * 200_000})
e, tr = lam_engine([KetQuaGia(text=khoi({"name": "quet", "arguments": {}})),
                    KetQuaGia(text="ok")], route=rt_dai)
chay(e)
check("kết quả khổng lồ bị cắt trước khi nhét vào tin nhắn web",
      len(tr.da_gui[1]) <= we.KET_QUA_CA_LO + 2000)
check("cắt thì NÓI RÕ là đã cắt (không để model tưởng đó là tất cả)",
      "cắt bớt" in tr.da_gui[1])
check("_cat_giua giữ cả đầu lẫn đuôi",
      we._cat_giua("A" * 100 + "Z" * 100, 60).startswith("A")
      and we._cat_giua("A" * 100 + "Z" * 100, 60).endswith("Z"))
check("_cat_giua không đụng chuỗi ngắn", we._cat_giua("ngắn", 1000) == "ngắn")


# ============================================================
# 10) Huỷ, và bề mặt engine
# ============================================================

sach_so()
e, tr = lam_engine([KetQuaGia(text="ok")])
e.cancel()
evs = chay(e)
check("huỷ: transport được bảo dừng", tr.da_dung)

sach_so()
e, tr = lam_engine([KetQuaGia(text="ok")], session_id="cu")
e.reset_session()
check("reset_session: quên luồng cũ", e.session_id == "")
check("reset_session: bảo transport mở luồng mới", tr.luong_moi_lan == 1)

check("model/provider khai đúng tên", we.WebEngine().model == "chatgpt-web")
check("không có transport -> không khả dụng", we.WebEngine().is_available() is False)


# ============================================================
# 11) Ranh giới kiến trúc
# ============================================================

_src = (SERVER / "web_engine.py").read_text(encoding="utf-8")
check("engine Web KHÔNG chạy qua codex (đó là tiêu đúng quota định tránh)",
      "codex exec" not in _src.replace("`codex exec`", "").replace("codex exec (", ""))
for cam in ("import main", "from main import"):
    check(f"engine không '{cam}' (tránh vòng import)", cam not in _src)
check("engine gọi tool qua call_route, không tự đọc một khuôn entry",
      "call_route" in _src and 'ent["call"]' not in _src)
check("gửi web chạy trong thread, không chặn event loop", "asyncio.to_thread" in _src)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_web_engine_loop: tất cả pass")
