"""Antigravity báo gọi công cụ qua `step_update`, không phải qua sự kiện `tool_call` tầng ngoài.

    python tests/run.py agy_buoc_tool

Vì sao có file này: bản 0.63.8 thêm khối tiến trình từng bước vào khung chat, chủ dự án thử
bằng bộ não Antigravity và báo "không thấy tiến trình nào cả, nó vẫn là một phát rồi trả lời
thôi".

Đo thật trên `agy` 1.2.8 (chạy `agy --output-format stream-json -p "Doc file a.txt..."` rồi
đọc NDJSON thô) thì `agy` gói MỌI bước dưới đúng một tên sự kiện:

    {"event":"step_update","step_update":{"step_type":"agent_response","text_delta":"..."}}
    {"event":"step_update","step_update":{"step_type":"tool","tool_name":"run_command",
                                          "state":"ACTIVE","step_index":2,"tool_info":{...}}}
    {"event":"step_update","step_update":{"step_type":"tool","tool_name":"run_command",
                                          "state":"DONE","step_index":2,"duration_seconds":...}}

`_doi_su_kien` lấy loại sự kiện từ `type`/`event` nên luôn thấy "step_update", và KHÔNG hề đọc
`step_type`. Nhánh `tool_use/tool_call/tool` ngay trong file đó chỉ khớp khi `agy` đặt loại ở
TẦNG NGOÀI - hình dạng mà bản CLI thật không dùng. Hậu quả: mọi lần `agy` gọi công cụ đều rơi
vào hư không, khung chat không có tiến trình nào để vẽ, và cờ `co_tool` cũng không bật lên nên
Javis tưởng lượt đó chưa đụng gì bên ngoài và được phép chạy lại.

Các mẫu dưới đây chép từ luồng đo được ở trên, giữ đúng bộ khoá.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import sys

from antigravity_cli import AntigravityCLI  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if (not cond and them) else ""))
    if not cond:
        _fails.append(name)


def buoc_tool(idx, state, ten="run_command"):
    """Đúng bộ khoá đo được: ACTIVE không có duration_seconds, DONE thì có."""
    sub = {"conversation_id": "c1", "step_index": idx, "state": state, "step_type": "tool",
           "tool_name": ten, "tool_info": {"name": ten, "parameters": {"CommandLine": "ls"}}}
    if state == "DONE":
        sub["duration_seconds"] = 0.42
    return {"event": "step_update", "step_update": sub}


def buoc_chu(idx, delta):
    return {"event": "step_update",
            "step_update": {"conversation_id": "c1", "step_index": idx, "state": "DONE",
                            "step_type": "agent_response", "text_delta": delta}}


def _chay(cac_ev):
    """Chạy đúng đường `_doi_su_kien` của engine, trả về (sự kiện, các mảnh chữ)."""
    cli = AntigravityCLI(tag="test")
    manh, chan, ra = [], {}, []
    for ev in cac_ev:
        ra.extend(cli._doi_su_kien(dict(ev), manh, chan))
    return ra, manh


# ---- 1. Bước tool ACTIVE phải thành một sự kiện tool_call ---------------------------------
ra, _ = _chay([buoc_tool(2, "ACTIVE")])
goi = [e for e in ra if e.get("type") == "tool_call"]
check("step_update/tool ACTIVE -> sinh tool_call", len(goi) == 1, ra)
check("tool_call mang đúng tên công cụ", bool(goi) and goi[0].get("name") == "run_command",
      goi[0].get("name") if goi else "")

# ---- 2. Cùng một bước báo ACTIVE rồi DONE: chỉ MỘT lần gọi, cộng một lần xong -------------
ra, _ = _chay([buoc_tool(2, "ACTIVE"), buoc_tool(2, "DONE")])
check("một bước ACTIVE rồi DONE chỉ đếm là MỘT lần gọi",
      len([e for e in ra if e.get("type") == "tool_call"]) == 1,
      [e.get("type") for e in ra])
check("bước xong thì báo tool_result",
      len([e for e in ra if e.get("type") == "tool_result"]) == 1,
      [e.get("type") for e in ra])

# ---- 3. Bước chỉ có DONE (lượt cắt ngang giữa chừng) vẫn phải hiện ra ---------------------
ra, _ = _chay([buoc_tool(7, "DONE")])
check("bước chỉ thấy DONE vẫn sinh tool_call (không nuốt mất bước)",
      len([e for e in ra if e.get("type") == "tool_call"]) == 1,
      [e.get("type") for e in ra])

# ---- 4. Hai bước khác step_index = hai lần gọi -------------------------------------------
ra, _ = _chay([buoc_tool(2, "ACTIVE"), buoc_tool(2, "DONE"),
               buoc_tool(4, "ACTIVE"), buoc_tool(4, "DONE")])
check("hai bước khác nhau đếm thành hai lần gọi",
      len([e for e in ra if e.get("type") == "tool_call"]) == 2,
      [e.get("type") for e in ra])

# ---- 5. KHÔNG được đụng vào đường chữ: agent_response vẫn gom vào câu trả lời -------------
ra, manh = _chay([buoc_chu(1, "Xin "), buoc_chu(3, "chào!")])
check("agent_response vẫn chỉ là chữ, không thành bước", not ra, ra)
check("chữ vẫn gom đủ vào câu trả lời", "".join(manh) == "Xin chào!", manh)

# ---- 6. Hình dạng CŨ (loại nằm ở tầng ngoài) vẫn nhận, không phá bản CLI khác -------------
ra, _ = _chay([{"event": "tool_call", "tool_name": "read_file"}])
check("hình dạng tool_call tầng ngoài vẫn nhận như trước",
      [e.get("name") for e in ra if e.get("type") == "tool_call"] == ["read_file"], ra)

# ---- 7. Nguyên luồng đo được: 3 lần gọi công cụ, chữ không lẫn tên công cụ ----------------
LUONG_THAT = [
    buoc_chu(1, None),
    buoc_tool(2, "ACTIVE"), buoc_tool(2, "DONE"),
    buoc_chu(3, None),
    buoc_tool(4, "ACTIVE"), buoc_tool(4, "DONE"),
    buoc_chu(5, "Tôi đang tìm kiếm file `a.txt`..."),
    buoc_chu(7, None),
    buoc_tool(8, "ACTIVE"),
    buoc_chu(9, "Đang kiểm tra các thư mục phổ biến...\n"),
]
ra, manh = _chay(LUONG_THAT)
check("luồng thật: đếm đúng 3 lần gọi công cụ",
      len([e for e in ra if e.get("type") == "tool_call"]) == 3,
      [e.get("type") for e in ra])
check("luồng thật: câu trả lời không lẫn tên công cụ",
      "run_command" not in "".join(m for m in manh if m), manh)
check("luồng thật: câu trả lời vẫn đủ chữ",
      "Tôi đang tìm kiếm" in "".join(m for m in manh if m), manh)


def test_agy_bao_buoc_tool():
    assert not _fails, _fails


if __name__ == "__main__":
    print(("\nFAILED: " + ", ".join(_fails)) if _fails else "\nAll passed")
    sys.exit(1 if _fails else 0)
