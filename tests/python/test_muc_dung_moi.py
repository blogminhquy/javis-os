"""Trang Mức dùng phải trả lời được ba câu người ta mở nó ra để hỏi, và phải nói THẬT.

    python tests/run.py muc_dung_moi

Ba câu đó: tháng này tốn bao nhiêu TIỀN MẶT, gói thuê bao có đáng tiền không, và sắp chạm
trần chưa. Bản trước không trả lời được câu nào: nó bày sáu ô số ngang hàng nhau, trong đó ô
to nhất ("chi phí quy đổi") lại KHÔNG phải tiền thật mà đứng ngay cạnh số dư OpenRouter là
tiền thật.

Lỗi nặng nhất được sửa ở đây, và là lý do file test này tồn tại: khối "đã tiết kiệm bao nhiêu
token" BIẾN MẤT đúng lúc chế độ tiết kiệm chạy tốt nhất. Phép đo cũ so trung bình token giữa
lượt đi đường đầy đủ và lượt đi đường tiết kiệm trong cùng 24 giờ, nên nó chỉ có số trong vài
giờ chuyển giao ngay sau khi đổi mức. Bật tiết kiệm rồi để yên một ngày là mọi lượt đều đi
đường mới, không còn lượt đối chứng, `du_du_lieu` thành False, và cả khối tắt ngóm. Chủ repo
báo đúng chuyện đó: "ở phần mức dùng không hiển thị token tiết kiệm thật".
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix="javis-mdm-")
os.environ["JAVIS_STATE_DIR"] = _TMP
os.environ["JAVIS_CLAUDE_PROJECTS_DIR"] = os.path.join(_TMP, "claude-projects")
os.environ["JAVIS_CODEX_SESSIONS_DIR"] = os.path.join(_TMP, "codex-sessions")
os.makedirs(os.environ["JAVIS_CLAUDE_PROJECTS_DIR"], exist_ok=True)
os.makedirs(os.environ["JAVIS_CODEX_SESSIONS_DIR"], exist_ok=True)

import aux_engine  # noqa: E402
import usage_index as ui  # noqa: E402
import usage_parsers as up  # noqa: E402
import usage_saving as us  # noqa: E402

_fails = []
_TZ = timezone(timedelta(hours=7))


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


_USAGE = (ROOT / "dashboard" / "usage.js").read_text(encoding="utf-8")
_MAIN = (ROOT / "server" / "main.py").read_text(encoding="utf-8")

# ============================================================
# 1. Đếm được SỐ LƯỢT - mẫu số của mọi phép tính tiết kiệm
# ============================================================
# Không có số lượt thì không có cách nào nhân "mỗi lượt rẻ đi bao nhiêu" thành một con số
# tổng. Trang cũ chỉ có `sessions` = số FILE phân biệt, không phải số lượt gọi model.
_ev = up.parse_claude_line(
    {"type": "assistant", "timestamp": "2026-08-10T03:00:00Z", "sessionId": "s1",
     "message": {"model": "claude-opus-5", "usage": {"input_tokens": 100, "output_tokens": 20}}},
    set(), {})
check("mỗi dòng assistant của Claude là MỘT lượt", (_ev or {}).get("turns") == 1)
check("và mang theo mốc thời gian để dựng cửa sổ trượt", (_ev or {}).get("ts", 0) > 0)

_rollout = os.path.join(os.environ["JAVIS_CODEX_SESSIONS_DIR"], "rollout-test.jsonl")
with open(_rollout, "w", encoding="utf-8") as fh:
    fh.write(json.dumps({"type": "session_meta", "payload": {"cwd": "/x/duan"}}) + "\n")
    for i, tot in enumerate((100, 400, 900)):
        fh.write(json.dumps({
            "timestamp": "2026-08-10T0%d:00:00Z" % (i + 1), "model": "gpt-5",
            "payload": {"type": "token_count", "info": {"total_token_usage": {
                "total_tokens": tot, "input_tokens": tot - 10, "output_tokens": 10,
                "cached_input_tokens": 0}}}}) + "\n")
_cx = up.parse_codex_file(_rollout)
# Trước bản này một phiên Codex 200 lượt và một phiên 2 lượt đều được đếm là MỘT, nên
# "token mỗi lượt" của Codex sai cả trăm lần - và nó là mẫu số của cả phép so engine.
check("CANARY: phiên Codex đếm đúng số lần gọi model, không gộp thành 1",
      (_cx or {}).get("turns") == 3)
check("và vẫn lấy đúng tổng token của trạng thái cuối", (_cx or {}).get("input") == 890)

# ============================================================
# 2. Kho số liệu giữ được số lượt và giữ được GIỜ
# ============================================================
_conn = ui._connect()
try:
    _cols = {r[1] for r in _conn.execute("PRAGMA table_info(file_daily)")}
    _bang = {r[0] for r in _conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
finally:
    _conn.close()
check("bảng theo ngày có cột số lượt", "turns" in _cols)
check("có bảng grain GIỜ cho cửa sổ trượt", "file_hourly" in _bang)
# file_daily gom theo ngày TRƯỚC khi ghi, nên giờ bị mất ngay tại chỗ. Hỏi "tôi còn bao nhiêu
# trong cửa sổ 5 tiếng" mà trả lời theo ngày thì 8 giờ sáng mùng 1 sẽ báo gần bằng 0 dù 5 giờ
# trước vừa đốt sạch hạn mức.
check("CANARY: bảng giờ tách riêng, không nhét thêm chiều vào bảng ngày",
      "hour" not in _cols)

_now = datetime.now(_TZ)


def _seed(hour_dt, tokens, turns, provider="claude", path="p1", day=None, activity="chat",
          model="claude-opus-5", inp=None, source="javis"):
    c = ui._connect()
    try:
        c.execute("INSERT INTO file_hourly(path,hour,provider,tokens,turns) VALUES(?,?,?,?,?)",
                  (path, hour_dt.strftime("%Y-%m-%dT%H"), provider, tokens, turns))
        c.execute("INSERT INTO file_daily(path,day,provider,source,activity,model,project,"
                  "input,output,cache_read,cache_create,turns) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                  (path, day or hour_dt.strftime("%Y-%m-%d"), provider, source, activity,
                   model, "brainX", inp if inp is not None else tokens, 0, 0, 0, turns))
        c.commit()
    finally:
        c.close()


_seed(_now - timedelta(hours=1), 30_000, 3)
_seed(_now - timedelta(hours=4), 20_000, 2)
_seed(_now - timedelta(hours=30), 500_000, 40)     # ngoài cửa sổ 5 giờ
_cs = ui.cua_so(5.0, now=_now)
check("cửa sổ 5 giờ chỉ cộng phần trong cửa sổ", _cs["tokens"] == 50_000)
check("và đếm cả số lượt trong đó", _cs["turns"] == 5)
check("CANARY: token cũ hơn cửa sổ không bị kéo vào", _cs["tokens"] < 500_000)

# Đỉnh dùng để trả lời "tôi đang ở đâu so với chính mình" khi nhà cung cấp không công bố hạn
# mức bằng số. Nó phải trượt trên chuỗi giờ LIÊN TỤC: DB không có dòng cho giờ rảnh, nên nếu
# không lấp lỗ hổng thì "5 giờ" thành 5 giờ-có-hoạt-động rải rác cả tuần và đỉnh bị thổi lên.
_dinh = ui.dinh_cua_so(5.0, 60, now=_now)
check("đo được đỉnh cửa sổ 5 giờ trong lịch sử", _dinh["tokens"] >= 500_000)
check("CANARY: đỉnh không cộng dồn những giờ cách xa nhau",
      _dinh["tokens"] < 550_000)

# Một lượt Claude Code được ghi HAI LẦN: một lần trong log thô (~/.claude/projects), một lần
# trong usage-events.jsonl do usage_store.record() ghi làm dự phòng. `_dedup_events_vs_raw` khử
# trùng chuyện đó, và nó phải khử ở CẢ HAI bảng. Bản đầu chỉ khử ở bảng ngày, nên bảng ngày
# đúng còn cửa sổ 5 giờ báo GẤP ĐÔI - sai đúng về hướng nguy hiểm nhất, vì đó là con số dùng
# để đoán xem sắp chạm trần gói chưa.
_D2 = tempfile.mkdtemp(prefix="javis-dup-")
_CP2 = os.path.join(_D2, "cp")
os.makedirs(_CP2, exist_ok=True)
_now2 = datetime.now(_TZ)
with open(os.path.join(_CP2, "a.jsonl"), "w", encoding="utf-8") as _fh:
    _fh.write(json.dumps({
        "type": "assistant", "timestamp": _now2.astimezone(timezone.utc).isoformat(),
        "sessionId": "s-dup", "cwd": "/x",
        "message": {"model": "claude-opus-5",
                    "usage": {"input_tokens": 1000, "output_tokens": 0}}}) + "\n")
with open(os.path.join(_D2, "usage-events.jsonl"), "w", encoding="utf-8") as _fh:
    _fh.write(json.dumps({"ts": int(_now2.timestamp()), "day": _now2.strftime("%Y-%m-%d"),
                          "provider": "cli", "model": "claude-opus-5",
                          "in": 1000, "out": 0, "cost": 0}) + "\n")


def _quet_rieng(state_dir, claude_dir):
    """Chạy indexer trên một kho tạm khác, rồi trả (tokens_ngay, tokens_cua_so)."""
    import importlib
    import config as _cfg
    cu = (os.environ.get("JAVIS_STATE_DIR"), os.environ.get("JAVIS_CLAUDE_PROJECTS_DIR"))
    os.environ["JAVIS_STATE_DIR"] = state_dir
    os.environ["JAVIS_CLAUDE_PROJECTS_DIR"] = claude_dir
    try:
        importlib.reload(_cfg)
        importlib.reload(ui)
        ui.refresh()
        return ui.summary("today")["kpi"]["tokens"], ui.cua_so(5.0)["tokens"]
    finally:
        os.environ["JAVIS_STATE_DIR"], os.environ["JAVIS_CLAUDE_PROJECTS_DIR"] = cu
        importlib.reload(_cfg)
        importlib.reload(ui)


_ngay, _cua = _quet_rieng(_D2, _CP2)
check("CANARY: một lượt ghi hai nguồn thì cửa sổ trượt KHÔNG đếm đôi", _cua == 1000)
check("và bảng theo ngày vẫn đúng như trước", _ngay == 1000)

_D3 = tempfile.mkdtemp(prefix="javis-dp-")
_CP3 = os.path.join(_D3, "cp")
os.makedirs(_CP3, exist_ok=True)
with open(os.path.join(_D3, "usage-events.jsonl"), "w", encoding="utf-8") as _fh:
    _fh.write(json.dumps({"ts": int(_now2.timestamp()), "day": _now2.strftime("%Y-%m-%d"),
                          "provider": "cli", "model": "claude-opus-5",
                          "in": 1000, "out": 0, "cost": 0}) + "\n")
_ngay3, _cua3 = _quet_rieng(_D3, _CP3)
# Khử trùng mà khử luôn cả ca không có bản trùng thì bản Docker/VPS (không đọc được log thô)
# sẽ báo 0 token, đúng cái mà nhánh dự phòng sinh ra để tránh.
check("CANARY: không có log thô thì nhánh dự phòng vẫn được giữ", _cua3 == 1000 and _ngay3 == 1000)


# ============================================================
# 3. Tiết kiệm tính bằng ĐỐI CHỨNG NGƯỢC - có số ở mọi kỳ
# ============================================================
_PHI = {"off": 13779, "saving": 1508, "max": 574}
_tk = us.tiet_kiem([{"day": "2026-08-12", "turns": 10}], _PHI, "max")
check("CANARY: không cần lượt đối chứng nào vẫn ra số",
      _tk["token"] == (13779 - 574) * 10)
check("nói rõ mỗi lượt rẻ đi bao nhiêu", _tk["moi_luot"] == 13779 - 574)
check("và bao nhiêu phần trăm", _tk["phan_tram"] == 96)
check("đủ dữ liệu thì khai là đủ", _tk["du_du_lieu"] is True)
check("chưa có lượt nào thì KHÔNG bịa ra số",
      us.tiet_kiem([], _PHI, "max")["token"] == 0
      and us.tiet_kiem([], _PHI, "max")["du_du_lieu"] is False)
check("mức Tắt thì không tiết kiệm gì, và nói đúng vậy",
      us.tiet_kiem([{"day": "2026-08-12", "turns": 10}], _PHI, "off")["token"] == 0)
check("có quy ra tiền", us.tiet_kiem([{"day": "2026-08-12", "turns": 100}], _PHI, "max",
                                     gia_1m_usd=3.0)["tien"]["vnd"] > 0)
# Chưa có nhật ký mốc thì ta đang GIẢ ĐỊNH cả kỳ chạy cùng một mức. Đó là một giả định, và
# giao diện phải nói ra thay vì trình bày nó như số đo.
check("CANARY: chưa có mốc thì tự khai là suy đoán", _tk["suy_doan"] is True)

# ============================================================
# 4. Nhật ký mốc: kỳ có ĐỔI MỨC giữa chừng phải tính đúng
# ============================================================
us.ghi_moc("muc", "max", "off", "Đổi chế độ tiết kiệm sang Siêu tiết kiệm",
           now=datetime(2026, 8, 13, 9, 0, tzinfo=_TZ))
_ban_do = us.muc_theo_ngay(["2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14"], "max")
check("ngày sau mốc chạy mức mới", _ban_do["2026-08-13"] == "max" and _ban_do["2026-08-14"] == "max")
check("CANARY: ngày TRƯỚC mốc chạy mức cũ, không bị áp ngược mức hôm nay",
      _ban_do["2026-08-11"] == "off" and _ban_do["2026-08-12"] == "off")
_tk2 = us.tiet_kiem([{"day": "2026-08-12", "turns": 10}, {"day": "2026-08-13", "turns": 5}],
                    _PHI, "max")
# Không có nhật ký thì người vừa bật tiết kiệm hôm qua sẽ được khoe con số tiết kiệm của cả
# tháng mà họ chưa từng nhận - tức là trang nói dối theo hướng có lợi cho chính nó.
check("CANARY: chỉ tính tiết kiệm cho những ngày THẬT SỰ đã bật",
      _tk2["token"] == (13779 - 574) * 5)
check("có mốc rồi thì thôi khai suy đoán", _tk2["suy_doan"] is False)
check("phần trăm bám mức ĐANG CHẠY, không bám mức chiếm đa số lượt",
      _tk2["phan_tram"] == 96 and _tk2["muc_chinh"] == "off")
check("đọc lại được mốc theo khoảng ngày",
      len(us.doc_moc("2026-08-13", "2026-08-13", "muc")) == 1
      and len(us.doc_moc("2026-08-01", "2026-08-12", "muc")) == 0)

# ============================================================
# 5. Ngân sách + dự báo + phanh
# ============================================================
check("chưa đặt trần thì không vẽ thanh tiến độ", us.ngan_sach(5, 0)["co"] is False)
check("dưới 80% là bình thường", us.ngan_sach(5, 30)["muc_do"] == "ok")
check("từ 80% là sắp hết", us.ngan_sach(24, 30)["muc_do"] == "sap_het")
check("chạm trần là hết", us.ngan_sach(30, 30)["muc_do"] == "het")
check("báo trước nếu theo nhịp này sẽ vượt", us.ngan_sach(10, 30, 45)["du_bao_vuot"] is True)

_db = us.du_bao(100, 10.0, "2026-08-01", "2026-08-10", "this_month",
                today=date(2026, 8, 10))
check("kỳ đang chạy thì chiếu ra cuối kỳ", _db["co"] is True and _db["tokens"] > 100)
# Kỳ đã chốt mà vẽ thêm một con số "dự báo" thì người đọc tưởng nó chưa xong.
check("CANARY: kỳ đã đóng thì KHÔNG dự báo gì",
      us.du_bao(100, 10.0, "2026-07-01", "2026-07-31", "last_month")["co"] is False)

us.dat_phanh(False)
check("mặc định không phanh", us.dang_phanh()["bat"] is False)
_spec_goc = {"provider": "openrouter", "model": "openai/gpt-5"}
_st = {"model": {"auxiliary": dict(_spec_goc), "openrouter_key": "k"}}
check("chưa phanh thì việc nền chạy đúng model người dùng chọn",
      aux_engine.read_spec(_st)["model"] == "openai/gpt-5")
us.dat_phanh(True, "vượt trần")
_sp = aux_engine.read_spec(_st)
check("CANARY: phanh rồi thì việc nền hết tiêu tiền theo token",
      _sp["provider"] != "openrouter" or _sp["model"] == "")
_st_goi = {"model": {"auxiliary": {"provider": aux_engine.CLAUDE, "model": "opus"}}}
# Phanh sinh ra để chặn TIỀN MẶT. Gói thuê bao đã trả trọn gói nên hạ nó xuống không tiết
# kiệm được đồng nào, chỉ làm việc nền tệ đi.
check("CANARY: gói thuê bao KHÔNG bị phanh đụng vào",
      aux_engine.read_spec(_st_goi)["provider"] == aux_engine.CLAUDE)
us.dat_phanh(False)

# ============================================================
# 6. Bảng giá: model OpenRouter hết ra chi phí 0
# ============================================================
# Đây đúng là nhánh DUY NHẤT người dùng trả tiền mặt, mà lại là nhánh bị tính thành 0 - nên
# ô "tiền mặt tháng này" luôn hiện $0.00 dù ví có vơi đi thật.
_p = up.load_prices()
check("CANARY: model OpenRouter khớp được bảng giá",
      up._khoa_gia("anthropic/claude-opus-4", _p) == "claude-opus")
check("và khớp bản CỤ THỂ chứ không rơi về tên hãng",
      up._khoa_gia("deepseek/deepseek-r1", _p) == "deepseek-r1")
check("tên nguyên văn vẫn khớp như cũ", up._khoa_gia("claude-opus-5", _p) == "claude-opus")
check("model lạ vẫn trả 0, không đoán bừa", up._khoa_gia("mo-hinh-la-hoac", _p) == "")

# ============================================================
# 7. So nhịp giữa các engine
# ============================================================
_seed(_now - timedelta(hours=2), 90_000, 3, provider="api", path="p2",
      activity="background", model="openai/gpt-5")
_nhip = ui.nhip_engine("today")
check("có bảng so nhịp engine", isinstance(_nhip, list) and len(_nhip) >= 1)
check("so bằng TOKEN MỖI LƯỢT chứ không phải tổng",
      all("moi_luot" in x for x in _nhip))
# Engine chạy nhiều việc hơn thì đương nhiên tốn nhiều token hơn; so tổng là so khối lượng
# việc, không phải so giá.
check("CANARY: engine không có lượt nào thì bị loại, không chia cho 0",
      all(x["turns"] > 0 for x in _nhip))

# ============================================================
# 8. Endpoint: nói THẬT về tiền
# ============================================================
import main  # noqa: E402

_tq = asyncio.run(main.usage_tong_quan(period="this_month", brain="brain"))
check("endpoint tổng quan trả về dict", isinstance(_tq, dict))
for _f in ("tien", "ngan_sach", "tiet_kiem", "cua_so", "cache", "du_bao", "cau", "moc",
           "nhip_engine", "luot"):
    check(f"có khối '{_f}'", _f in _tq)
# Nhập nhèm hai loại tiền là cả trang mất tin cậy: người dùng gói thuê bao nhìn "$1.700" rồi
# tưởng mình vừa bị trừ tiền.
check("CANARY: tiền MẶT và tiền QUY ĐỔI là hai khối tách hẳn nhau",
      "that" in _tq["tien"] and "quy_doi" in _tq["tien"])
check("có câu mở đầu bằng tiếng người", len(_tq["cau"]) > 20)
check("câu đó nói rõ đâu là tiền mặt",
      "tiền mặt" in _tq["cau"].lower() or "tiền gói" in _tq["cau"].lower())
check("chưa khai giá gói thì không bịa ra tỉ lệ lời lãi",
      _tq["tien"]["goi"]["roi_lan"] == 0)

_luu = asyncio.run(main.usage_ngan_sach(ngan_sach_thang_usd="30", gia_goi_thang_usd="200",
                                        tran_5h="5000000", tu_phanh="1"))
check("lưu được ngân sách", _luu["ok"] is True and _luu["ngan_sach_thang_usd"] == 30.0)
check("lưu được giá gói", _luu["gia_goi_thang_usd"] == 200.0)
check("lưu được trần cửa sổ 5 giờ", _luu["tran_5h"] == 5_000_000)
check("lưu được cờ tự phanh", _luu["tu_phanh"] is True)
# Giao diện chỉ gửi ô người dùng vừa sửa. Hiểu ô trống là 0 thì bấm lưu một ô là mất ba ô kia.
_luu2 = asyncio.run(main.usage_ngan_sach(gia_goi_thang_usd="300"))
check("CANARY: trường bỏ trống thì GIỮ NGUYÊN, không xoá về 0",
      _luu2["ngan_sach_thang_usd"] == 30.0 and _luu2["tran_5h"] == 5_000_000)
check("và trường có gửi thì đổi", _luu2["gia_goi_thang_usd"] == 300.0)
# Gọi thẳng hàm endpoint thì tham số mặc định là object Form(...), không phải chuỗi.
check("CANARY: giá trị mặc định của Form không lọt vào settings.json",
      isinstance(_luu2["bao_cao_tuan"], str) and "annotation=" not in _luu2["bao_cao_tuan"])

_tq2 = asyncio.run(main.usage_tong_quan(period="this_month", brain="brain"))
check("khai giá gói rồi thì tính được gói lời hay lỗ",
      _tq2["tien"]["goi"]["gia_thang_usd"] == 300.0)
check("khai trần 5 giờ thì lấy trần đó làm mốc, không lấy đỉnh đo được",
      _tq2["cua_so"]["moc_so_sanh"] == 5_000_000)

_bc = asyncio.run(main.usage_bao_cao(period="this_month"))
check("dựng được báo cáo dạng chữ", isinstance(_bc.get("text"), str) and len(_bc["text"]) > 40)
check("báo cáo là văn nói, không phải bảng markdown", "|---" not in _bc["text"])
check("báo cáo nói cả tiền mặt", "Tiền mặt thật" in _bc["text"])

# ============================================================
# 9. Giao diện phải VẼ những thứ đó ra
# ============================================================
check("gọi endpoint tổng quan", '"/usage/tong-quan?period="' in _USAGE)
check("vẽ câu mở đầu", "function heroHtml(" in _USAGE and "t.cau" in _USAGE)
check("có ba ô hành động", all(f"function {f}(" in _USAGE for f in ("oTien", "oTran", "oTietKiem")))
check("ô tiền đọc đúng khối tiền mặt", "t.ngan_sach" in _USAGE and ".openrouter" in _USAGE)
check("ô trần đọc cửa sổ trượt", "t.cua_so" in _USAGE)
check("ô tiết kiệm đọc khối tiết kiệm", "t.tiet_kiem" in _USAGE)
check("đặt được ngân sách ngay trên trang",
      "function nganSachHtml(" in _USAGE and '"/usage/ngan-sach"' in _USAGE)
# "Cache hit 80%" là ngôn ngữ của người viết code. Người trả tiền hỏi nó đáng bao nhiêu.
check("CANARY: cache được dịch ra TIỀN chứ không chỉ phần trăm",
      "Cache đỡ cho" in _USAGE and "cache.vnd" in _USAGE)
check("biểu đồ có hàng mốc sự kiện", "tk-mrow" in _USAGE and "mocTheoNgay" in _USAGE)
check("có CSS cho hàng mốc", ".tk-mrow{" in _USAGE and ".tk-m{" in _USAGE)
check("bảng ngốn nhất có nút hành động", "data-goto=" in _USAGE and "tk-go" in _USAGE)
check("liệt kê loop nền kèm nút tắt",
      "function loopHtml(" in _USAGE and '"/loops/toggle"' in _USAGE and "data-loop=" in _USAGE)
check("có bảng so nhịp engine", "function engineHtml(" in _USAGE and "nhip_engine" in _USAGE)
check("dải chế độ tiết kiệm thu gọn một dòng, bấm mới bung",
      "tk-muc-strip" in _USAGE and "state.moMuc" in _USAGE)
# Chủ repo đã chốt khối chọn mức nằm ĐẦU trang. Thu gọn nó là để đỡ chiếm màn hình, không
# phải để đẩy nó xuống dưới hoá đơn.
check("CANARY: và nó vẫn nằm TRƯỚC mọi con số", "mucHtml(state.muc) + bar1" in _USAGE)
check("nói rõ dự báo là ước chừng, không phải hoá đơn", "ước chừng" in _USAGE)
check("nói rõ phanh chỉ đụng việc nền", "việc chạy nền" in _USAGE)

# ============================================================
# 10. Vòng lặp nền có thật sự gọi tới
# ============================================================
# Viết hàm mà quên nối vào vòng lặp là lỗi im lặng: không có gì báo, ngân sách chỉ đơn giản
# không bao giờ được kiểm.
check("vòng lặp nền có kiểm ngân sách", "_kiem_ngan_sach(nhac=True)" in _MAIN)
check("và có đẩy báo cáo tuần", "_bao_cao_tuan_neu_toi_gio()" in _MAIN)
check("nhịp riêng chứ không chạy mỗi 30 giây", "_NGAN_SACH_LAST" in _MAIN and ">= 600" in _MAIN)
check("đổi mức tiết kiệm thì đóng mốc", 'usage_saving.ghi_moc("muc"' in _MAIN)
check("đổi bộ não cũng đóng mốc", 'usage_saving.ghi_moc("model"' in _MAIN)
# refresh() xoá sạch dòng cũ của từng file rồi chèn lại. Hai lượt quét chồng nhau là chèn
# trùng, và trang báo gấp đôi số token.
check("CANARY: quét index được tuần tự hoá",
      "_USAGE_REFRESH_LOCK" in _MAIN and "async with _USAGE_REFRESH_LOCK" in _MAIN)

# ============================================================
# 11. Những chỗ "sai im lặng" - số vẫn hiện ra, chỉ là sai
# ============================================================
# Không cái nào trong mục này làm app đổ. Chúng chỉ trả ra một con số trông bình thường mà
# sai, và đó là loại lỗi sống lâu nhất trên một trang báo cáo.

# settings["model"] KHÔNG có khoá "model" - tên model nằm ở main.model / claude_model.
# Đọc nhầm thì mọi phép quy đổi tiền rơi về đơn giá mặc định 3$ bất kể đang chạy Opus (15$)
# hay Haiku (1$), tức sai 5 lần theo cả hai chiều.
check("CANARY: lấy đúng tên model chính từ main.model",
      main._ten_model_chinh({"main": {"provider": "anthropic-cli", "model": "claude-opus-5"}})
      == "claude-opus-5")
check("cấu hình cũ (claude_model) vẫn đọc được",
      main._ten_model_chinh({"claude_model": "haiku"}) == "haiku")
check("CANARY: và giá đi theo đúng model đó, không rơi về mặc định",
      main._gia_input_1m(main._ten_model_chinh(
          {"main": {"model": "claude-opus-5"}}), {}) == (15.0, "bang"))

# Model free của OpenRouter có hậu tố ':free' và giá bằng 0. Tính tiền cho nó là bịa ra một
# hoá đơn không tồn tại, và hoá đơn đó chảy thẳng vào phanh ngân sách.
check("CANARY: model ':free' không bị tính tiền",
      up._khoa_gia("deepseek/deepseek-r1:free", _p) == ""
      and up.estimate_cost({"model": "deepseek/deepseek-r1:free", "input": 10_000_000,
                            "output": 0, "cache_read": 0, "cache_create": 0}, _p) == 0.0)
check("bản trả phí cùng họ thì vẫn tính tiền",
      up.estimate_cost({"model": "deepseek/deepseek-r1", "input": 10_000_000,
                        "output": 0, "cache_read": 0, "cache_create": 0}, _p) > 0)

# Cửa sổ hiện tại và đỉnh đối chiếu phải đếm CÙNG số mốc giờ. Lệch một mốc là tỉ lệ phồng
# ~20% trên một nhịp dùng đều, và ô đó hiện "100%" trong khi thực tế mới dùng 80%.
_D4 = tempfile.mkdtemp(prefix="javis-cs-")
_dem = {"cua_so": 0, "dinh": 0}


def _do_moc():
    import importlib
    import config as _cfg
    cu = os.environ.get("JAVIS_STATE_DIR")
    os.environ["JAVIS_STATE_DIR"] = _D4
    try:
        importlib.reload(_cfg)
        importlib.reload(ui)
        moc = datetime(2026, 8, 13, 14, 30, tzinfo=_TZ)
        c = ui._connect()
        try:
            for i in range(48):
                g = (moc - timedelta(hours=i)).strftime("%Y-%m-%dT%H")
                c.execute("INSERT INTO file_hourly(path,hour,provider,tokens,turns) "
                          "VALUES('p','%s','claude',1000,1)" % g)
            c.commit()
        finally:
            c.close()
        return ui.cua_so(5.0, now=moc)["tokens"], ui.dinh_cua_so(5.0, 60, now=moc)["tokens"]
    finally:
        os.environ["JAVIS_STATE_DIR"] = cu
        importlib.reload(_cfg)
        importlib.reload(ui)


_cs4, _dinh4 = _do_moc()
check("CANARY: cửa sổ hiện tại và đỉnh đếm cùng số mốc giờ", _cs4 == _dinh4 == 5000)

# Provider API nào thiếu trong danh sách là mọi dòng của nó bị vứt im lặng (chuỗi if/elif
# không có else), và ô tiền mặt báo 0 trong khi ví vẫn vơi đi.
for _pv in ("groq", "gemini", "openrouter", "openai", "anthropic-api", "ollama"):
    check(f"nhánh API '{_pv}' được indexer nhận", _pv in ui._API_PROVIDERS)

# Mẫu số của tiết kiệm phải là lượt CỦA JAVIS. Lượt người dùng tự gõ `claude` trong terminal
# không đi qua prompt của Javis nên chế độ tiết kiệm không làm chúng rẻ đi.
_seed(_now, 5000, 100, provider="claude", path="p-manual", activity="manual", source="manual")
_luot = ui.luot_theo_ngay("today")
_tong_moi = sum(x["turns"] for x in _luot)
_tong_tat = sum(x["turns"] for x in ui.summary("today")["timeseries"])
check("CANARY: lượt người dùng tự gõ KHÔNG được tính vào tiết kiệm", _tong_moi < _tong_tat)
check("và lượt của Javis thì vẫn được tính", _tong_moi > 0)

# Người tự chỉnh tay từng đường (preset 'custom'): Javis không biết cấu hình đó tốn bao nhiêu
# mỗi lượt. Báo "tiết kiệm 0" kèm du_du_lieu=True là nói "chế độ của anh chẳng đáng gì".
_tk_custom = us.tiet_kiem([{"day": "2026-08-12", "turns": 10}], _PHI, "custom")
check("CANARY: cấu hình tự chỉnh thì nói KHÔNG ĐO ĐƯỢC, không nói tiết kiệm 0",
      _tk_custom["du_du_lieu"] is False and _tk_custom["khong_do_duoc"] is True)

# Giá gói là tiền MỘT THÁNG. Chia nó cho chi phí của một ngày thì ra "gói đang lỗ 10 lần",
# mà đó là dòng chữ to nhất trên trang.
asyncio.run(main.usage_ngan_sach(gia_goi_thang_usd="200"))
_tq_ngay = asyncio.run(main.usage_tong_quan(period="today", brain="brain"))
_tq_thang = asyncio.run(main.usage_tong_quan(period="this_month", brain="brain"))
check("CANARY: kỳ không phải tháng thì KHÔNG so với giá gói",
      _tq_ngay["tien"]["goi"]["so_duoc"] is False and _tq_ngay["tien"]["goi"]["roi_lan"] == 0)
check("kỳ tháng thì so được", _tq_thang["tien"]["goi"]["so_duoc"] is True)
check("và câu mở đầu của kỳ ngày không nhắc tiền gói",
      "tiền gói" not in _tq_ngay["cau"])

# Trần tiền là trần THÁNG. Bấm chip "Hôm nay" mà ô ngân sách đọc chi phí một ngày thì nó báo
# "còn nguyên" dù tháng này đã tiêu hết.
asyncio.run(main.usage_ngan_sach(ngan_sach_thang_usd="30"))
_a = asyncio.run(main.usage_tong_quan(period="today", brain="brain"))["ngan_sach"]
_b = asyncio.run(main.usage_tong_quan(period="this_year", brain="brain"))["ngan_sach"]
check("CANARY: ô ngân sách luôn đọc số của THÁNG, không đổi theo chip kỳ",
      _a["da_tieu"] == _b["da_tieu"])

# Giao diện
check("giao diện soi r.ok chứ không chỉ đọc thân JSON",
      "function jsonOk(" in _USAGE and "if (!r.ok)" in _USAGE)
check("phiên hết hạn thì nói ra, không vẽ trang 0 đồng", "hết hạn" in _USAGE)
check("nút lưu ngân sách báo lỗi khi server từ chối", "Chưa lưu được" in _USAGE)
check("CANARY: thông báo tan sau khi hiện, không dính lại mãi",
      'state.toast = "";' in _USAGE and 'state.nsToast = "";' in _USAGE)
check("số đang gõ dở trong form không bị xoá khi trang vẽ lại",
      "function nhoForm(" in _USAGE and "state.nsForm" in _USAGE)
check("nói rõ chỉ đếm lượt của Javis", "lượt của Javis" in _USAGE)

# Việc nền chạy bằng API key phải ghi mức dùng, không thì trần tiền không thấy chính khoản
# chi mà nó sinh ra để chặn.
_AUX = (ROOT / "server" / "aux_engine.py").read_text(encoding="utf-8")
check("CANARY: việc nền đường API có ghi vào sổ mức dùng",
      "usage_store.record(" in _AUX and "_ghi_muc_dung" in _AUX)
check("phanh có kiểm binary CLI thật sự tồn tại", "_co_binary(" in _AUX)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_muc_dung_moi: tất cả pass")
