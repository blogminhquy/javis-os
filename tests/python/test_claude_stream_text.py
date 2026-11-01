"""Claude Code hiện chữ lần lượt như ChatGPT (0.438.4).

    python tests/run.py claude_stream_text

Chủ repo hỏi 01/11/2026: ChatGPT đã hiện chữ ra lần lượt, Claude thì chưa. Claude Code vốn đã gửi từng mẩu
(StreamEvent text_delta) nhưng map_message bỏ qua, chỉ đẩy chữ khi xong cả AssistantMessage. Test giữ ba điều:
mẩu chữ ra ngay, khối chữ đầy đủ theo sau KHÔNG lặp lại, và không mất chữ nào khi luồng mẩu thiếu.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os

from claude_agent_sdk.types import (AssistantMessage, ResultMessage, StreamEvent, TextBlock,  # noqa: E402
                                    ToolUseBlock)
import claude_sdk_engine as eng  # noqa: E402
import claude_stream_text as cst  # noqa: E402

fails = []


def check(ten, ok, them=None):
    print(("PASS: " if ok else "FAIL: ") + ten + ("" if ok or them is None else f"  [{them}]"))
    if not ok:
        fails.append(ten)


check("cài móc được, gọi lại không chồng thêm lớp", cst.cai_vao_claude_sdk() and cst.cai_vao_claude_sdk()
      and getattr(eng.map_message, "_stream_text", False)
      and not getattr(eng.map_message.__wrapped__, "_stream_text", False))

SID = "s-1"
n = [0]


def se(event, parent=None, sid=SID):
    n[0] += 1
    return StreamEvent(uuid=f"u{n[0]}", session_id=sid, event=event, parent_tool_use_id=parent)


def am(blocks, mid="m1", parent=None, sid=SID):
    return AssistantMessage(content=blocks, model="claude", parent_tool_use_id=parent, message_id=mid,
                            session_id=sid)


def texts(evs):
    return [e["content"] for e in evs if e.get("type") == "text"]


def run(msgs):
    out = []
    for m in msgs:
        out.extend(eng.map_message(m)[0])
    return out


# 1. Một câu trả lời thường: mẩu ra ngay, khối đầy đủ không lặp.
evs = run([
    se({"type": "message_start", "message": {"id": "m1"}}),
    se({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
    se({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Xin "}}),
    se({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "chào anh."}}),
    se({"type": "content_block_stop", "index": 0}),
    am([TextBlock(text="Xin chào anh.")]),
])
check("mẩu chữ ra lần lượt, khối đầy đủ không lặp lại", texts(evs) == ["Xin ", "chào anh."], texts(evs))
check("ghép lại đúng nguyên câu", "".join(texts(evs)) == "Xin chào anh.")

# 2. Chữ rồi gọi tool trong cùng message: tool_call vẫn ra, chữ không lặp.
evs = run([
    se({"type": "message_start", "message": {"id": "m2"}}),
    se({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Để em xem."}}),
    am([TextBlock(text="Để em xem."), ToolUseBlock(id="t1", name="Read", input={"p": "a"})], mid="m2"),
])
check("chữ trước tool không lặp, tool_call vẫn còn", texts(evs) == ["Để em xem."]
      and [e["type"] for e in evs] == ["text", "tool_call"], evs)

# 3. Claude Code gửi mỗi khối một AssistantMessage cùng id: khối thứ hai vẫn khớp đúng.
evs = run([
    se({"type": "message_start", "message": {"id": "m3"}}),
    se({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Một."}}),
    se({"type": "content_block_delta", "index": 2, "delta": {"type": "text_delta", "text": "Hai."}}),
    am([TextBlock(text="Một.")], mid="m3"),
    am([TextBlock(text="Hai.")], mid="m3"),
])
check("mỗi khối một AssistantMessage cùng id cũng không lặp", texts(evs) == ["Một.", "Hai."], texts(evs))

# 4. Luồng mẩu thiếu đuôi: phần chưa ra được bù, không mất chữ.
evs = run([
    se({"type": "message_start", "message": {"id": "m4"}}),
    se({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Doanh thu "}}),
    am([TextBlock(text="Doanh thu tăng 12%.")], mid="m4"),
])
check("mẩu thiếu đuôi thì bù đúng phần còn thiếu", "".join(texts(evs)) == "Doanh thu tăng 12%.", texts(evs))

# 5. Không có StreamEvent (CLI cũ, binary đóng gói): y như trước.
evs = run([am([TextBlock(text="Không stream.")], mid="m5", sid="s-khac")])
check("không có mẩu nào thì khối đầy đủ ra như cũ", texts(evs) == ["Không stream."], texts(evs))

# 6. Khối khác message id với cái đang stream: không đụng tới.
evs = run([
    se({"type": "message_start", "message": {"id": "m6"}}),
    se({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "A"}}),
    am([TextBlock(text="A")], mid="m-khac"),
])
check("message id khác thì không bỏ chữ", texts(evs) == ["A", "A"], texts(evs))
cst._STATE.clear()

# 7. Sub-agent: mẩu của nó không ra, chữ của nó đi như trước.
evs = run([
    se({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "sub"}}, parent="t9"),
    am([TextBlock(text="sub done")], mid="m7", parent="t9"),
])
check("sub-agent giữ nguyên cách cũ", texts(evs) == ["sub done"], texts(evs))

# 8. ResultMessage dọn trạng thái của phiên, final vẫn mang nguyên câu cuối.
run([se({"type": "message_start", "message": {"id": "m8"}}),
     se({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "x"}})])
evs = run([ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                         session_id=SID, result="x", usage={})])
check("ResultMessage dọn trạng thái, final giữ nguyên", SID not in cst._STATE
      and [e for e in evs if e["type"] == "final"][0]["content"] == "x")

# 9. Tắt bằng biến môi trường thì quay lại như cũ.
os.environ["JAVIS_CLAUDE_STREAM_TEXT"] = "0"
evs = run([se({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "z"}})])
check("JAVIS_CLAUDE_STREAM_TEXT=0 thì không phát mẩu", texts(evs) == [])
os.environ.pop("JAVIS_CLAUDE_STREAM_TEXT")

# 10. Móc nằm DƯỚI hai móc còn lại, cài từ factory, không đụng file engine bị khoá.
cli = (ROOT / "server" / "claude_cli.py").read_text(encoding="utf-8")
fac = cli[cli.find("def claude_engine("):cli.find("return eng", cli.find("def claude_engine("))]
check("factory cài móc chữ chạy TRƯỚC móc đếm cache và móc hạn mức",
      0 < fac.find("claude_stream_text.cai_vao_claude_sdk()") < fac.find("_cai_dem_cache()")
      < fac.find("plan_limits.cai_vao_claude_sdk()"))
check("không sửa claude_sdk_engine.py", "claude_stream_text" not in
      (ROOT / "server" / "claude_sdk_engine.py").read_text(encoding="utf-8"))

if fails:
    raise SystemExit(f"{len(fails)} FAIL")
print("OK")
