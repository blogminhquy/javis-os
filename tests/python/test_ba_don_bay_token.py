"""Ba đòn bẩy token còn lại sau khi chế độ tiết kiệm đã chạy được.

    python tests/run.py ba_don_bay_token

Bối cảnh, đo trên máy thật của chủ repo. Sau khi chế độ tiết kiệm chạy đúng (0.13.2 tới
0.13.4), số liệu cho thấy phần Javis gọt được NHỎ hơn tưởng tượng rất nhiều:

  - Bộ luật + bộ nhớ 9.749 token, mô tả công cụ 896 token. Tổng phần Javis gói vào khoảng
    10.600 token.
  - Nhưng token VÀO thật của mỗi lượt chạy từ 35.720 tới 412.730, và bảng đo 24 giờ ghi
    Đầy đủ 103.997 so với Tối ưu 90.743, tức chỉ giảm 13%.
  - Cột "Ra" chỉ 266 tới 1.496 token. Vào gấp Ra từ 88 tới 340 lần.
  - Cột "Lệch" âm 86% tới 96%.

Ba con số đó cùng chỉ về một chỗ: phần lớn token KHÔNG nằm ở thứ Javis gói, mà ở vòng lặp
agentic của engine gói thuê bao. Codex nhận prompt rồi tự gọi model nhiều vòng, mỗi vòng gửi
lại toàn bộ ngữ cảnh đã tích. Javis không nhìn thấy các vòng đó, chỉ nhận tổng ở cuối. Nên ba
đòn bẩy còn lại, theo đúng thứ tự tác động:

  1. ĐƯỜNG TẮT cho câu hỏi không cần tra cứu: đi thẳng một vòng thay vì cả vòng lặp. Trước
     bản này đường tắt chỉ chạy trên engine API key, nên mức "Siêu tiết kiệm" chỉ là cái tên
     với người dùng gói ChatGPT.
  2. XOAY MẠCH khi mạch hội thoại phình: engine thuê bao tự quản transcript, Javis chỉ có
     đúng con số token vào của lượt trước làm dấu hiệu.
  3. HIỆU CHỈNH BỘ ĐOÁN: đoán thấp hơn thật bảy lần thì hàng rào chặn-trước-khi-vượt gần như
     không tồn tại.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-3db-")

from fastapi import WebSocketDisconnect  # noqa: E402

import compaction  # noqa: E402
import config as cfg  # noqa: E402
import context_runtime  # noqa: E402
import main  # noqa: E402
from chat_runtime import ChatRuntime  # noqa: E402
from sessions import SessionStore  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


BRAIN = Path(tempfile.mkdtemp(prefix="javis-3db-brain-"))
(BRAIN / "Memory" / "facts").mkdir(parents=True, exist_ok=True)
(BRAIN / "Memory" / "MEMORY.md").write_text("- [user] chu ho nuoc mam\n", encoding="utf-8")
(BRAIN / "Memory" / "facts" / "a.md").write_text(
    "---\ntype: user\n---\nChu ho kinh doanh nuoc mam.\n", encoding="utf-8")
(BRAIN / "skills").mkdir(exist_ok=True)

_s = cfg.read_settings()
_s.setdefault("model", {})["main"] = {"provider": "openai-oauth", "model": "gpt-5.6-luna"}
cfg.write_settings(_s)
asyncio.run(main.runtime_preset_set(level="max"))
# Trên máy thật, registry được hâm nóng bởi tác vụ nền của chính lượt chat
# (_schedule_registry_discovery_shadow). Ở đây làm thẳng cho khỏi phụ thuộc MCP.
main._CAPABILITY_REGISTRY.refresh_tools(str(BRAIN), [], {})


class _WS:
    """Gửi một tin rồi ở lại nghe tới khi lượt chốt, giữ mọi gói máy chủ bắn ra."""
    cookies = {}

    def __init__(self, payload):
        self._p = json.dumps(payload)
        self.sent = []

    async def accept(self):
        pass

    async def close(self, code=None):
        pass

    async def send_text(self, v):
        self.sent.append(json.loads(v))

    async def receive_text(self):
        if self._p is not None:
            v, self._p = self._p, None
            return v
        for _ in range(400):
            if any(g.get("type") == "turn_done" for g in self.sent):
                break
            await asyncio.sleep(0.02)
        raise WebSocketDisconnect()


DEM = {"codex": 0, "thang": 0}


# Số token Codex giả báo về. Suy từ chính hằng số ngưỡng chứ KHÔNG gõ tay: chủ repo đã
# nâng ngưỡng từ 120k lên 1 triệu sau khi dùng thật, và một con số gõ cứng ở đây sẽ lặng
# lẽ ngừng kiểm đúng thứ nó sinh ra để kiểm ngay lần chỉnh ngưỡng kế tiếp.
TOKEN_VUOT_NGUONG = compaction.SUBSCRIPTION_THREAD_MAX_TOKENS + 30_000
TOKEN_DUOI_NGUONG = compaction.SUBSCRIPTION_THREAD_MAX_TOKENS // 2


class _Codex:
    """Codex giả, báo về con số token vào vượt ngưỡng xoay mạch."""
    last_resume = "chua chay"
    last_prompt = ""

    def __init__(self, **kw):
        self.session_id = None
        self.profile = None
        self.extra_config = []

    def is_available(self):
        return True

    async def query(self, prompt):
        DEM["codex"] += 1
        _Codex.last_resume = self.session_id
        _Codex.last_prompt = prompt
        yield {"type": "final", "content": "codex tra loi", "session_id": "thread-1",
               "tokens_in": TOKEN_VUOT_NGUONG, "tokens_out": 400}


def chay(cau_hoi, sid, store):
    rt = ChatRuntime()
    ws = _WS({"message": cau_hoi, "brain": "brain", "session_id": sid})
    cu = {}

    def patch(o, n, v):
        cu[(id(o), n)] = (o, n, getattr(o, n))
        setattr(o, n, v)

    patch(main, "_CHAT_RUNTIME", rt)
    patch(main, "get_store", lambda: store)
    patch(main.cfgmod, "gate_active", lambda: False)
    patch(main, "_chat_provider", lambda _c: ("openai-oauth", "oauth", "", "gpt-5.6-luna"))
    patch(main, "_brain_root", lambda b: BRAIN)
    patch(main, "_reasoning_level", lambda _c: "off")
    patch(main, "_codex_safe_model", lambda m: m or "gpt-5.6-luna")
    patch(main, "build_system_prompt", lambda *a, **k: "LUAT " * 400)
    patch(main.channel_context, "build_channel_block", lambda *a, **k: "")
    patch(main, "claude_engine", lambda **k: type("C", (), {"session_id": None})())
    patch(main, "CodexCLI", _Codex)
    patch(main, "_apply_codex_hub", lambda *a, **k: None)
    patch(main.openai_oauth, "write_codex_auth", lambda *a, **k: None)
    patch(main, "_schedule_registry_discovery_shadow", lambda *a, **k: None)
    patch(main, "log_conversation", lambda *a, **k: None)
    patch(main.usage_store, "record", lambda *a, **k: None)

    async def khong(*a, **k):
        return None

    def gia_lap_goi_thang(prov, key, model, messages, reasoning="off"):
        DEM["thang"] += 1

        async def ev():
            yield {"type": "usage", "input": 900, "output": 60}
            yield {"type": "text", "content": "duong tat tra loi"}
        return ev()

    patch(main, "_schedule_cancel_action", khong)
    patch(main.learn_feature, "enqueue", khong)
    patch(main, "_api_stream", gia_lap_goi_thang)
    patch(main.compaction, "maybe_compact", khong)

    async def go():
        await main.websocket_endpoint(ws)
        for _ in range(120):
            if rt.get_job(sid) is None:
                break
            await asyncio.sleep(0.02)

    try:
        asyncio.run(go())
    finally:
        for o, n, old in cu.values():
            setattr(o, n, old)
    resp = [g for g in ws.sent if g.get("type") == "response"]
    return {
        "resp": resp,
        "loi": [g for g in ws.sent if g.get("type") == "error"],
        "tool": [g.get("content", "") for g in ws.sent if g.get("type") == "tool_call"],
    }


STORE = SessionStore(Path(os.environ["JAVIS_STATE_DIR"]) / "c.db")

# ============================================================
# 1. Đường tắt: câu không cần tra cứu thì KHÔNG đi qua vòng lặp Codex
# ============================================================
DEM["codex"] = DEM["thang"] = 0
_r = chay("entropy la gi", "s-tat", STORE)
check("câu hỏi đơn giản không gọi Codex lần nào", DEM["codex"] == 0)
check("mà gọi thẳng model đúng MỘT vòng", DEM["thang"] == 1)
check("không có gói lỗi nào", not _r["loi"])
check("CANARY: chỉ MỘT gói trả lời, không gửi trùng", len(_r["resp"]) == 1)
if _r["resp"]:
    check("CANARY: lượt đường tắt vẫn khai được nó đi đường nào",
          _r["resp"][0].get("ctx_path") == "fast")
    check("và khai được số token vào", int(_r["resp"][0].get("ctx_in") or 0) > 0)
# Lượt đường tắt KHÔNG đi qua Codex nên mạch native của Codex không biết nó đã xảy ra. Giữ
# liên kết mạch là lượt sau Codex trả lời với một bản ghi THIẾU: nó không thấy câu vừa hỏi
# lẫn câu vừa đáp, rồi nói lại hoặc nói mâu thuẫn.
#
# Phải dựng phiên ĐÃ CÓ mạch thật rồi mới kiểm, không thì phiên nào cũng rỗng sẵn và phép
# kiểm này luôn xanh kể cả khi bản vá bị gỡ (đã kiểm ngược, đột biến này từng lọt).
chay("doanh thu hom nay bao nhieu", "s-mach", STORE)      # lượt Codex, tạo mạch
check("dựng được phiên có mạch Codex thật",
      (STORE.get_session("s-mach") or {}).get("codex_thread_id") == "thread-1")
chay("entropy la gi", "s-mach", STORE)                    # lượt đường tắt trên CÙNG phiên
check("CANARY: sau đường tắt thì bỏ liên kết mạch Codex",
      not ((STORE.get_session("s-mach") or {}).get("codex_thread_id") or ""))

# ============================================================
# 2. Câu cần dữ liệu thật thì TUYỆT ĐỐI không được đi đường tắt
# ============================================================
# Đây là chiều nguy hiểm: đi tắt một câu cần tra cứu là trả lời bịa.
DEM["codex"] = DEM["thang"] = 0
_r2 = chay("doanh thu hom nay bao nhieu", "s-that", STORE)
check("CANARY: câu cần dữ liệu thật vẫn đi qua Codex", DEM["codex"] == 1)
check("và KHÔNG đi đường tắt", DEM["thang"] == 0)

# Rào cứng cho Claude Code: đường tắt chạy bằng _api_stream, mà provider anthropic-cli rơi
# vào nhánh cần API key - thứ gói Claude Code không có. Nới cấu hình bằng tay tới đây là mọi
# câu hỏi đơn giản ăn 401.
_tr = main._CONTEXT_RUNTIME.start_turn("s-cli", "brain", "dashboard")
_ke = main._FAST_PATH.prepare(_tr, "entropy la gi", str(BRAIN), "dashboard",
                              "anthropic-cli", "opus", "cli", False)
check("CANARY: Claude Code KHÔNG bao giờ đi đường tắt", _ke.action == "legacy")
_src_fp = (SERVER / "fast_path_runtime.py").read_text(encoding="utf-8")
check("CANARY: và bị chặn CỨNG trong mã, không chỉ dựa vào cấu hình",
      'provider_kind or "") == "cli"' in _src_fp)

# ============================================================
# 3. Xoay mạch khi mạch phình
# ============================================================
_row = STORE.get_session("s-that") or {}
check("token vào của lượt trước được ghi lại",
      int(_row.get("last_input_tokens") or 0) == TOKEN_VUOT_NGUONG)
check("mạch Codex đang được lưu", bool(_row.get("codex_thread_id")))
DEM["codex"] = DEM["thang"] = 0
_r3 = chay("doanh thu tuan nay bao nhieu", "s-that", STORE)
check("CANARY: mạch quá ngưỡng thì thôi resume mạch cũ", _Codex.last_resume is None)
check("và mạch mới MANG THEO lịch sử, không bỏ trắng trí nhớ",
      "KHÔI PHỤC NGỮ CẢNH" in _Codex.last_prompt)
check("có nói cho người dùng biết", any("mở mạch mới" in x for x in _r3["tool"]))
check("có ghi mốc để lần sau không xoay liên tục",
      int((STORE.get_session("s-that") or {}).get("thread_rotated_msg") or 0) > 0)

# Luật xoay: hai điều kiện, và mọi giá trị rác đều phải quy về "chưa đáng xoay".
check("dưới ngưỡng thì không xoay",
      compaction.nen_mach_thue_bao(TOKEN_DUOI_NGUONG) is False)
# Số đo thật của chủ repo: ba lượt liên tiếp 83k, 552k, 36k. Lượt 552k nặng vì công việc
# của chính nó (đi tra thời tiết), không vì mạch dài - và mạch tự co ngay lượt sau. Ngưỡng
# phải đủ cao để không xoay trong ca đó.
check("CANARY: lượt 552k như thực tế đo được KHÔNG được xoay mạch",
      compaction.nen_mach_thue_bao(552_000) is False)
check("trên ngưỡng, chưa từng xoay thì xoay", compaction.nen_mach_thue_bao(TOKEN_VUOT_NGUONG) is True)
check("CANARY: vừa xoay xong thì KHÔNG xoay tiếp ngay",
      compaction.nen_mach_thue_bao(TOKEN_VUOT_NGUONG, msg_count=10, rotated_at=10) is False)
check("phải có đủ message mới mới xoay lần nữa",
      compaction.nen_mach_thue_bao(TOKEN_VUOT_NGUONG, msg_count=12, rotated_at=10) is False
      and compaction.nen_mach_thue_bao(TOKEN_VUOT_NGUONG, msg_count=14, rotated_at=10) is True)
for _rac in (None, "abc", -5, 0):
    check(f"giá trị rác {_rac!r} coi như chưa đáng xoay",
          compaction.nen_mach_thue_bao(_rac) is False)

# ============================================================
# 4. Hiệu chỉnh bộ đoán
# ============================================================
_rt2 = context_runtime.ObserveRuntime(
    Path(tempfile.mkdtemp(prefix="javis-3db-rt-")), cfg.read_settings)
_db = _rt2._conn()


def _mau(prov, uoc, that, i):
    tr = _rt2.start_turn(f"s-{prov}-{i}", "brain", "dashboard")
    _db.execute("UPDATE runtime_steps SET provider=?,estimated_input_tokens=?,"
                "actual_input_tokens=? WHERE id=?", (prov, uoc, that, tr.step_id))
    _db.commit()


check("chưa có mẫu thì không hiệu chỉnh gì", _rt2._he_so_hieu_chinh(_db, "codex") == 1.0)
for _i, _that in enumerate([100_000, 90_000, 110_000, 70_000, 130_000, 95_000]):
    _mau("codex", 15_000, _that, _i)
_hs = _rt2._he_so_hieu_chinh(_db, "codex")
check("CANARY: học được rằng thật gấp nhiều lần đoán", 5.0 < _hs < 9.0)
for _i, _that in enumerate([9_000, 9_500, 10_000, 9_800, 9_200]):
    _mau("groq", 10_000, _that, _i)
# Đoán CAO hơn thật thì cùng lắm là thận trọng thừa; đoán THẤP hơn thật là để lọt đúng thứ
# hàng rào sinh ra để chặn. Nên chỉ nới lên, không bao giờ thu nhỏ.
check("CANARY: engine đoán sát thì giữ nguyên, không thu nhỏ",
      _rt2._he_so_hieu_chinh(_db, "groq") == 1.0)
for _i in range(5):
    _mau("loan", 10, 100_000_000, _i)
check("CANARY: tỉ lệ điên rồ bị kẹp trần, không nhân vô hạn",
      _rt2._he_so_hieu_chinh(_db, "loan") == context_runtime.ObserveRuntime._HIEU_CHINH_TRAN)
for _i in range(4):
    _mau("it", 100, 500, _i)
check("dưới số mẫu tối thiểu thì chưa dám hiệu chỉnh",
      _rt2._he_so_hieu_chinh(_db, "it") == 1.0)
check("provider rỗng không làm hỏng gì", _rt2._he_so_hieu_chinh(_db, "") == 1.0)

# Và hệ số phải THẬT SỰ được áp vào con số ghi xuống, không chỉ tính rồi bỏ đó.
_tr3 = _rt2.start_turn("s-ap", "brain", "dashboard")
_meta = _rt2.observe_payload(_tr3, [{"role": "system", "content": "x" * 3000},
                                    {"role": "user", "content": "y" * 300}],
                             provider="codex", model="gpt-5.6-luna")
check("CANARY: con số ghi xuống ĐÃ được hiệu chỉnh",
      _meta["estimated_input_tokens"] > _meta["estimated_input_tokens_raw"])
check("và vẫn giữ lại con số thô để lần ngược được",
      _meta["estimated_input_tokens_raw"] > 0 and _meta["calibration_factor"] > 1)


# ============================================================
# 5. Rác trích dẫn nội bộ của nhà cung cấp không được lọt ra màn hình
# ============================================================
# Chủ repo chụp lại: câu trả lời thời tiết hiện ra "Độ ẩm 70-99%. \ue200cite\ue202turn4view0
# \ue201" - ba ký tự vùng Private Use, trình duyệt vẽ thành ô vuông trống. Tệ hơn phần nhìn:
# nó đi thẳng vào lịch sử hội thoại, nên lượt sau chính Javis đọc lại rồi tưởng "turn4view0"
# là nguồn có thật. Được hỏi lấy tin ở đâu, nó trả lời "mình chỉ còn mã tham chiếu
# turn4view0, không có URL nguồn gốc".
import engine  # noqa: E402

_ban = "Do am cao 70-99%. \ue200cite\ue202turn4view0\ue201\n\nAnh nen mang ao mua."
_sach = engine.strip_provider_markers(_ban)
check("CANARY: bóc sạch dấu trích dẫn nội bộ", "\ue200" not in _sach and "\ue201" not in _sach)
check("và không nuốt mất chữ thật của câu trả lời",
      "Do am cao 70-99%." in _sach and "Anh nen mang ao mua." in _sach)
check("mảnh vụn khi stream cắt giữa dấu cũng bị quét",
      "\ue200" not in engine.strip_provider_markers("abc\ue200cite\ue202turn4"))
check("văn bản thường không bị đụng vào",
      engine.strip_provider_markers("Doanh thu 5 trieu.") == "Doanh thu 5 trieu.")
for _rong in ("", None):
    check(f"đầu vào {_rong!r} không làm hỏng gì",
          engine.strip_provider_markers(_rong) == _rong)
# Phải nối vào CẢ HAI đường text đi ra, không thì bóc ở một chỗ rồi chỗ kia vẫn rò.
_src_cli = (SERVER / "claude_cli.py").read_text(encoding="utf-8")
check("CANARY: nhánh Codex CLI có bóc", "engine.strip_provider_markers(" in _src_cli)
_src_eng = (SERVER / "engine.py").read_text(encoding="utf-8")
check("CANARY: đường gọi thẳng của gói ChatGPT cũng bóc",
      "strip_provider_markers(obj.get(\"delta\")" in _src_eng)


# ============================================================
# 6. Bản mồi lại mạch mới phải ĐỦ DÀY
# ============================================================
# Đây mới là chỗ ngữ cảnh THẬT SỰ mất khi xoay mạch, và nó đi ngược cái ngưỡng theo cách phản
# trực giác: ngưỡng càng cao thì xoay càng hiếm, nhưng mỗi lần xoay lại rơi càng sâu. Ở ngưỡng
# 120k, rơi xuống 60.000 ký tự là mất sáu lần; ở ngưỡng 1 triệu, cùng cái trần đó thành mất
# năm mươi lần. Chủ repo lo mất ngữ cảnh khi giao việc nặng chạy lâu, và chỗ đau đúng là đây.
_msgs = [{"role": "user" if _i % 2 == 0 else "assistant",
          "content": f"noi dung luot {_i} " * 200} for _i in range(120)]
_moi = compaction.bootstrap_prompt(_msgs, "cau hoi moi")
_giu = _moi.count("<User>") + _moi.count("<Javis>")
_giu_cu = (lambda p: p.count("<User>") + p.count("<Javis>"))(
    compaction.bootstrap_prompt(_msgs, "cau hoi moi", max_chars=60_000))
check("CANARY: trần mồi lại đủ dày cho phiên làm việc dài",
      compaction.CODEX_BOOTSTRAP_MAX_CHARS >= 300_000)
check(f"giữ được nhiều lượt hơn hẳn trần cũ ({_giu} so với {_giu_cu})", _giu > _giu_cu * 3)
check("câu hỏi hiện tại luôn còn nguyên, không bị cắt", _moi.endswith("cau hoi moi"))

# Tóm tắt đã nén đại diện cho hàng chục lượt đã rơi khỏi ngân sách. Bỏ nó để nhét thêm hai
# lượt thô là đổi sai chiều, nên nó đứng TRƯỚC transcript và không bị cắt.
_co_tt = compaction.bootstrap_prompt(_msgs, "cau hoi moi",
                                     summary="Hai ben da chot kien truc Javis Gateway.")
check("CANARY: bản tóm tắt đã nén được mang theo khi mồi lại",
      "Javis Gateway" in _co_tt)
check("và đứng TRƯỚC phần transcript thô",
      _co_tt.find("Javis Gateway") < _co_tt.find("<User>"))
check("phiên chưa có tóm tắt vẫn chạy y như cũ",
      compaction.bootstrap_prompt(_msgs, "x", summary="") == compaction.bootstrap_prompt(_msgs, "x"))
check("tóm tắt rác không làm hỏng gì",
      compaction.bootstrap_prompt(_msgs, "x", summary="   ")
      == compaction.bootstrap_prompt(_msgs, "x"))
# Và phải NỐI vào đường xoay mạch thật, không chỉ nhận tham số rồi không ai truyền.
_src_main = (SERVER / "main.py").read_text(encoding="utf-8")
check("CANARY: đường mồi lại THẬT SỰ truyền tóm tắt vào",
      _src_main.count('summary=_row0.get("compact_summary")') >= 3)

print(("\nFAILED: " + ", ".join(_fails)) if _fails else "\nAll passed")
sys.exit(1 if _fails else 0)
