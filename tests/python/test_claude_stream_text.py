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


def turn():
    """Each scenario is its own turn: nothing of this session has been shown yet."""
    cst._STATE.clear()


turn()
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

turn()
# 2. Chữ rồi gọi tool trong cùng message: tool_call vẫn ra, chữ không lặp.
evs = run([
    se({"type": "message_start", "message": {"id": "m2"}}),
    se({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Để em xem."}}),
    am([TextBlock(text="Để em xem."), ToolUseBlock(id="t1", name="Read", input={"p": "a"})], mid="m2"),
])
check("chữ trước tool không lặp, tool_call vẫn còn", texts(evs) == ["Để em xem."]
      and [e["type"] for e in evs] == ["text", "tool_call"], evs)

turn()
# 3. Claude Code gửi mỗi khối một AssistantMessage cùng id: khối thứ hai vẫn khớp đúng.
evs = run([
    se({"type": "message_start", "message": {"id": "m3"}}),
    se({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Một."}}),
    se({"type": "content_block_delta", "index": 2, "delta": {"type": "text_delta", "text": "Hai."}}),
    am([TextBlock(text="Một.")], mid="m3"),
    am([TextBlock(text="Hai.")], mid="m3"),
])
# Index 1 between them is the tool call, so the second block starts a new paragraph (2026-11-16).
check("mỗi khối một AssistantMessage cùng id cũng không lặp", texts(evs) == ["Một.", "\n\nHai."], texts(evs))

turn()
# 4. Luồng mẩu thiếu đuôi: phần chưa ra được bù, không mất chữ.
evs = run([
    se({"type": "message_start", "message": {"id": "m4"}}),
    se({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Doanh thu "}}),
    am([TextBlock(text="Doanh thu tăng 12%.")], mid="m4"),
])
check("mẩu thiếu đuôi thì bù đúng phần còn thiếu", "".join(texts(evs)) == "Doanh thu tăng 12%.", texts(evs))

turn()
# 5. Không có StreamEvent (CLI cũ, binary đóng gói): y như trước.
evs = run([am([TextBlock(text="Không stream.")], mid="m5", sid="s-khac")])
check("không có mẩu nào thì khối đầy đủ ra như cũ", texts(evs) == ["Không stream."], texts(evs))

turn()
# 6. Khối khác message id với cái đang stream: không đụng tới.
evs = run([
    se({"type": "message_start", "message": {"id": "m6"}}),
    se({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "A"}}),
    am([TextBlock(text="A")], mid="m-khac"),
])
check("message id khác thì không bỏ chữ", texts(evs) == ["A", "\n\nA"], texts(evs))
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

# 11. 2026-11-16: text before a tool call and text after it no longer reach the chat glued together
#     (owner's screenshot: "... cần đăng nhập.Xong mục 3", "... Hồng Ngọc.Now the CEO ...").
from claude_agent_sdk.types import SystemMessage  # noqa: E402

turn()
evs = run([
    SystemMessage(subtype="init", data={"session_id": SID}),
    se({"type": "message_start", "message": {"id": "a1"}}),
    se({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
    se({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Em lưu bằng hàm của app "}}),
    se({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "thay cho API cần đăng nhập."}}),
    am([TextBlock(text="Em lưu bằng hàm của app thay cho API cần đăng nhập."),
        ToolUseBlock(id="t2", name="Bash", input={"command": "ls"})], mid="a1"),
    se({"type": "message_start", "message": {"id": "a2"}}),
    se({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
    se({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Xong mục 3."}}),
    am([TextBlock(text="Xong mục 3.")], mid="a2"),
])
joined = "".join(texts(evs))
check("text after a tool call starts a new paragraph", "cần đăng nhập.\n\nXong mục 3." in joined, joined)
check("the first text of a turn has no break in front", joined.startswith("Em lưu"), joined)
check("a block that streams in pieces is not broken up", "của app thay cho API" in joined, joined)
check("nothing is repeated", joined.count("Xong mục 3.") == 1 and joined.count("Em lưu") == 1, joined)

turn()
evs = run([am([TextBlock(text="Bước một.")], mid="b1"),
           am([ToolUseBlock(id="t3", name="Read", input={})], mid="b2"),
           am([TextBlock(text="Bước hai.")], mid="b3")])
check("no streaming (old CLI): complete blocks get the same break", texts(evs) == ["Bước một.", "\n\nBước hai."],
      texts(evs))

turn()
evs = run([am([TextBlock(text="Đã có dòng trống.\n\n")], mid="c1"), am([TextBlock(text="Tiếp.")], mid="c2")])
check("a blank line the model already wrote is not doubled", "".join(texts(evs)) == "Đã có dòng trống.\n\nTiếp.",
      texts(evs))

turn()
run([am([TextBlock(text="Lượt cũ.")], mid="d1")])
evs = run([SystemMessage(subtype="init", data={"session_id": SID}), am([TextBlock(text="Lượt mới.")], mid="d2")])
check("a new turn starts clean even when the last one never reached its result", texts(evs) == ["Lượt mới."], texts(evs))

turn()
os.environ["JAVIS_CLAUDE_STREAM_TEXT"] = "0"
evs = run([am([TextBlock(text="Một.")], mid="e1"), am([TextBlock(text="Hai.")], mid="e2")])
os.environ.pop("JAVIS_CLAUDE_STREAM_TEXT")
check("with streaming switched off the breaks still apply", texts(evs) == ["Một.", "\n\nHai."], texts(evs))
cst._STATE.clear()

if fails:
    raise SystemExit(f"{len(fails)} FAIL")
print("OK")
