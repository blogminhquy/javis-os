"""Việc dài chạy bằng API key không bị cắt ở vòng 30 (05/11/2026).

    python tests/run.py viec_dai_api_key

Người dùng báo: việc nền điền Google Sheet bằng API key "chạy 30 vòng xong lỗi", dựng video cũng
vậy. Chủ repo chốt: cắm token vào là phải làm được việc, không bị giới hạn. Các phép thử:

  1. Việc nền có tool (aux_engine) chạy với trần của CHỦ (500), thật sự vượt quá vòng 30.
  2. Bot nói chuyện với khách vẫn giữ trần 30.
  3. Phanh chống kẹt: thăm dò có tiến triển không bị bắt oan, vòng xoay A-B-A-B bị cắt.
  4. Kết quả tool cũ được rút gọn khi lượt dài vượt ngân sách ngữ cảnh, kết quả mới giữ nguyên.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="javis-viecdai-")
os.environ["JAVIS_STATE_DIR"] = _TMP
for _bien in ("JAVIS_MAX_TOOL_ROUNDS", "JAVIS_MAX_TOOL_ROUNDS_CODING", "JAVIS_TOOL_LOOP_BUDGET_CHARS"):
    os.environ.pop(_bien, None)

import engine  # noqa: E402
import aux_engine  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("  ok  " if cond else "  FAIL ") + name + (f"  ({extra})" if extra and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- 1. Trần theo ai giao việc ----
check("bot / lượt không rõ chủ: vẫn 30 vòng", engine._max_tool_rounds() == 30)


async def _trong_viec_chu():
    async def _gen():
        yield engine._max_tool_rounds()
        yield engine._het_vong_msg()
    return [v async for v in engine.chay_trong_phien_coding(_gen)]


tran, cau = asyncio.run(_trong_viec_chu())
check("việc của chủ: 500 vòng", tran == 500, tran)
check("câu chạm trần của chủ chỉ đúng biến và cách đi tiếp",
      "JAVIS_MAX_TOOL_ROUNDS_CODING" in cau and "làm tiếp" in cau and "không giới hạn" in cau)
check("sau khi bọc xong, cờ không rò sang lượt sau", engine._max_tool_rounds() == 30)


# ---- 1b. Việc nền bằng API key chạy được quá vòng 30 (đúng ca người dùng báo) ----
async def _gia_vong_tool(key, model, messages, reasoning, tools, route):
    """Giả một vòng tool: gọi tool tới hết trần rồi báo số vòng đã chạy."""
    n = engine._max_tool_rounds()
    for i in range(min(n, 60)):
        yield {"type": "tool_call", "name": "sheet_append", "input": {"row": i}}
    yield {"type": "text", "content": f"xong {min(n, 60)} vòng, trần {n}"}


async def _gia_discover(*a, **k):
    return [{"fn": "sheet_append", "schema": {}}], {"sheet_append": "x"}


async def _chay_viec_nen():
    import mcp_hub
    goc_discover = mcp_hub.discover_all
    goc_fn = engine.openai_chat_with_mcp
    mcp_hub.discover_all = _gia_discover
    engine.openai_chat_with_mcp = _gia_vong_tool
    try:
        eng = aux_engine._ApiAuxEngine("openai", "gpt-x", api_key="sk-test")
        out = [ev async for ev in eng.query("điền 60 dòng vào sheet")]
    finally:
        mcp_hub.discover_all = goc_discover
        engine.openai_chat_with_mcp = goc_fn
    return out


if hasattr(aux_engine, "_ApiAuxEngine"):
    ra = asyncio.run(_chay_viec_nen())
    so_tool = sum(1 for e in ra if e.get("type") == "tool_call")
    final = next((e.get("content") for e in ra if e.get("type") == "final"), "")
    check("việc nền bằng API key chạy quá 30 vòng tool", so_tool == 60, so_tool)
    check("việc nền thấy trần của chủ (500)", "trần 500" in final, final)
else:
    src = (ROOT / "server" / "aux_engine.py").read_text(encoding="utf-8")
    check("aux_engine bọc vòng tool trong trần của chủ", "chay_trong_phien_coding" in src)

# ---- 2. Bot giữ trần thấp: chỗ dựng vòng tool cho bot KHÔNG bọc cờ của chủ ----
msrc = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
_bot = msrc[msrc.find("def _bot_stream_co_tool("):]
_bot = _bot[:_bot.find("\ndef ", 10)]
check("vòng tool của bot không chạy với trần của chủ", "chay_trong_phien_coding" not in _bot)

# ---- 3. Phanh chống kẹt ----
g = engine._LapGuard()
for i in range(25):
    g.ghi([("javis_process", '{"action":"poll"}')], [f"đang dựng video {i * 4}%"])
check("thăm dò có tiến triển (kết quả đổi) không bị cắt ở vòng 5", not g.ket() and g.lap == 1)
for i in range(25, 31):
    g.ghi([("javis_process", '{"action":"poll"}')], [f"đang dựng video {i * 3}%"])
check("thăm dò không được chờ vô hạn", g.ket())

g = engine._LapGuard()
for _ in range(5):
    g.ghi([("doc_file", '{"path":"a.md"}')], ["cùng nội dung"])
check("gọi y nguyên, kết quả y nguyên: vẫn cắt ở vòng 5", g.ket())

g = engine._LapGuard()
for _ in range(4):
    g.ghi([("doc", '{"p":"a"}')], ["A"])
    g.ghi([("doc", '{"p":"b"}')], ["B"])
check("vòng xoay A-B-A-B không tiến triển bị cắt", g.ket())

g = engine._LapGuard()
for i in range(4):
    g.ghi([("sleep", '{"s":30}')], [""])
    g.ghi([("poll", "{}")], [f"{i * 25}%"])
check("chờ rồi xem tiến độ (kết quả đổi) không bị coi là vòng xoay", not g.ket())

g = engine._LapGuard()
for i in range(60):
    g.ghi([("sheet_append", json.dumps({"row": i}))], ["ok"])
check("60 vòng làm việc thật (tham số mỗi vòng khác) không bị phanh", not g.ket())

# ---- 4. Gọn kết quả tool cũ ----
cc = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
for i in range(20):
    cc.append({"role": "assistant", "content": "", "tool_calls": []})
    cc.append({"role": "tool", "tool_call_id": str(i), "content": f"kq{i}:" + "x" * 20_000})
n = engine._gon_ket_qua_cu(cc, 100_000)
tong = sum(len(m["content"]) for m in cc if m["role"] == "tool")
check("vượt ngân sách thì rút gọn kết quả cũ", n > 0 and tong <= 100_000, tong)
check("các kết quả mới nhất (vừa nửa ngân sách) giữ nguyên văn",
      all(len(m["content"]) > 20_000 for m in cc[-4:] if m["role"] == "tool"))
nho = [{"role": "tool", "content": "k" * 12_000} for _ in range(20)]
engine._gon_ket_qua_cu(nho, 200_000)
check("kết quả nhỏ thì giữ nguyên văn đủ 8 cái mới nhất",
      all(engine._GON_DAU_HIEU not in m["content"] for m in nho[-8:])
      and engine._GON_DAU_HIEU in nho[0]["content"])
check("kết quả bị rút gọn vẫn giữ phần đầu và báo cho model biết",
      cc[3]["content"].startswith("kq0:") and engine._GON_DAU_HIEU in cc[3]["content"])
check("chạy lại không rút gọn thêm lần nữa", engine._gon_ket_qua_cu(cc, 100_000) == 0)
check("dưới ngân sách thì không đụng tới gì",
      engine._gon_ket_qua_cu([{"role": "tool", "content": "x" * 50}], 100_000) == 0)

an = [{"role": "user", "content": "u"}]
for i in range(12):
    an.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": str(i),
                                            "content": "y" * 30_000}]})
engine._gon_ket_qua_cu(an, 100_000)
check("định dạng Anthropic (tool_result) cũng được rút gọn",
      engine._GON_DAU_HIEU in an[1]["content"][0]["content"])

rs = [{"type": "function_call_output", "call_id": str(i), "output": "z" * 30_000} for i in range(12)]
engine._gon_ket_qua_cu(rs, 100_000)
check("định dạng Responses (function_call_output) cũng được rút gọn", engine._GON_DAU_HIEU in rs[0]["output"])

os.environ["JAVIS_TOOL_LOOP_BUDGET_CHARS"] = "0"
check("JAVIS_TOOL_LOOP_BUDGET_CHARS=0 tắt việc rút gọn",
      engine._gon_ket_qua_cu([{"role": "tool", "content": "x" * 900_000}] * 10) == 0)
os.environ.pop("JAVIS_TOOL_LOOP_BUDGET_CHARS", None)

esrc = (ROOT / "server" / "engine.py").read_text(encoding="utf-8")
check("cả ba vòng tool đều rút gọn trước mỗi vòng", esrc.count("_gon_ket_qua_cu(") == 4,
      esrc.count("_gon_ket_qua_cu("))
check("cả ba vòng tool đều đưa kết quả vào phanh", esrc.count("guard.ghi(") == 3
      and esrc.count("for m in msgs[-len(tcs):]") == 1 and "items[-len(fcalls):]" in esrc
      and "[r.get(\"content\") for r in results]" in esrc)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_viec_dai_api_key: tất cả pass")
