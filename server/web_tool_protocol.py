"""Giao thức tool qua CHỮ cho engine Web (spec: docs/dev/2026-09-chatgpt-web-model-spec.md).

Vì sao có file này
------------------
Sáu engine API của Javis được nhà cung cấp bảo đảm khuôn tool call: gửi `tools=[...]` dạng
schema, nhận lại `tool_calls` đã parse sẵn. ChatGPT Web **không có function calling**. Nó chỉ
nhận chữ và trả chữ.

Nên muốn engine Web dùng được tool của Javis thì phải quy ước một khuôn bằng chữ, rồi bóc
khuôn đó ra khỏi câu trả lời. Module này là chỗ duy nhất biết khuôn ấy.

Ba ranh giới có chủ ý
---------------------
1. **THUẦN.** Không import `main`, không FastAPI, không Playwright, không đụng đĩa. Chỉ
   stdlib. Vì đây là phần dễ sai nhất và phải test được trong một giây, không cần trình duyệt.
2. **KHÔNG ĐOÁN.** JSON hỏng, thiếu `name`, `arguments` không phải object: trả lỗi NÓI ĐƯỢC
   để vòng ngoài gửi lại một lượt sửa. Đoán ý model là cách chắc chắn để một ngày nào đó ghi
   nhầm file hoặc chạy nhầm lệnh. Spec mục 19: "Never silently infer a destructive command
   from broken output."
3. **KHÔNG CƯỠNG CHẾ QUYỀN Ở ĐÂY.** Module này chỉ nói "model muốn gọi cái này". Ai được gọi,
   mức quyền nào, là việc của `mcp_hub`. Tách ra để không có hai chỗ cùng xét quyền rồi lệch
   nhau.

Khuôn
-----
Model trả về MỘT khối rào bằng ```javis_tool chứa JSON:

    ```javis_tool
    {"calls": [{"name": "javis_read_file", "arguments": {"path": "a.py"}}]}
    ```

Hoặc không có khối nào, nghĩa là đây là câu trả lời cuối cùng.

V1 KHÔNG cho vừa gọi tool vừa trả lời trong một lượt (spec mục 17). Lý do: câu trả lời "cuối"
kèm tool call là câu trả lời viết TRƯỚC khi biết kết quả tool, tức là bịa. Thà mất một vòng
còn hơn giao cho người dùng một đoạn văn tự tin mà sai.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

# Phiên bản khuôn. Đổi khuôn thì tăng số này và sửa cả lời dặn trong prompt, để lần sau đọc
# nhật ký còn biết một lượt hỏng là do khuôn cũ hay do model.
TOOL_PROTOCOL_VERSION = "javis-web-tool-v1"

FENCE = "javis_tool"

# Số tool tối đa trong MỘT khối. Gộp nhiều tool một vòng là đòn giảm thời gian chính của
# engine Web (spec mục 18), nhưng gộp vô hạn thì một khối hỏng kéo theo cả chục lời gọi, và
# kết quả trả về cũng phình quá một lượt chat.
MAX_CALLS = 8

# Trần ký tự của phần JSON. Khối dài hơn gần như chắc chắn là model dán nhầm cả file vào
# `arguments` chứ không phải một lời gọi thật.
MAX_BLOCK_CHARS = 20_000

# Bóc khối rào. Chấp nhận cả ```javis_tool lẫn ``` javis_tool, và cả khi model quên xuống
# dòng sau tên rào. re.S để '.' nuốt được xuống dòng.
_BLOCK_RE = re.compile(
    r"```[ \t]*" + FENCE + r"[ \t]*\r?\n?(?P<body>.*?)```",
    re.S | re.I,
)

# Rào KHÔNG có tên: model thỉnh thoảng trả ```json hoặc ``` trần. Chỉ dùng làm nguồn CHẨN
# ĐOÁN cho câu nhắc sửa, KHÔNG bao giờ dùng làm lời gọi thật - đó chính là chỗ "đừng đoán".
_ANY_FENCE_RE = re.compile(r"```[ \t]*(?P<lang>[a-zA-Z_-]*)[ \t]*\r?\n?(?P<body>.*?)```", re.S)


@dataclass(frozen=True)
class ToolCall:
    """Một lời gọi tool model yêu cầu. `index` để nối kết quả về đúng chỗ."""
    name: str
    arguments: dict
    index: int = 0


@dataclass
class ParseResult:
    """Kết quả bóc một câu trả lời của Web.

    Đúng một trong ba trạng thái:
      - `calls` không rỗng  -> model muốn gọi tool
      - `final_text` có chữ -> đây là câu trả lời cuối
      - `error` có chữ      -> khuôn hỏng, vòng ngoài gửi một lượt sửa
    """
    calls: list[ToolCall] = field(default_factory=list)
    final_text: str = ""
    error: str = ""
    # Nguyên văn khối đã bóc (đã cắt), để ghi nhật ký khi cần lần lại.
    raw_block: str = ""

    @property
    def is_tool(self) -> bool:
        return bool(self.calls)

    @property
    def is_final(self) -> bool:
        return not self.calls and not self.error

    @property
    def is_error(self) -> bool:
        return bool(self.error)


def _cat(s: str, n: int = 400) -> str:
    s = str(s or "")
    return s if len(s) <= n else s[:n] + f"… [cắt, còn {len(s) - n} ký tự]"


def _bo_khoi(text: str) -> str:
    """Bỏ mọi khối javis_tool khỏi chữ, để lấy phần văn xuôi còn lại."""
    return _BLOCK_RE.sub("", text or "")


def _goi_y_khi_khong_co_khoi(text: str) -> str:
    """Model có vẻ ĐỊNH gọi tool mà rào sai tên? Trả câu nhắc; rỗng nếu không có dấu hiệu.

    Chỉ nhận diện khi rào chứa một object JSON có khoá `calls` hoặc `name`. Bắt rộng hơn thế
    là bắt oan mọi đoạn code mẫu model viết ra để giải thích.
    """
    for m in _ANY_FENCE_RE.finditer(text or ""):
        lang = (m.group("lang") or "").strip().lower()
        if lang == FENCE.lower():
            continue
        body = (m.group("body") or "").strip()
        if not body.startswith("{"):
            continue
        try:
            obj = json.loads(body)
        except (TypeError, ValueError):
            continue
        if isinstance(obj, dict) and ("calls" in obj or "name" in obj):
            return (f"Khối gọi tool phải rào bằng ```{FENCE}, không phải ```{lang or '(trống)'}. "
                    f"Gửi lại đúng khuôn.")
    return ""


def _doc_mot_call(raw: Any, i: int) -> tuple[Optional[ToolCall], str]:
    """Đọc một phần tử của `calls`. Trả (ToolCall, "") hoặc (None, lý do nói được)."""
    if not isinstance(raw, dict):
        return None, f"calls[{i}] phải là object, đang là {type(raw).__name__}."
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        return None, f"calls[{i}] thiếu 'name' (tên tool) hoặc name không phải chuỗi."
    args = raw.get("arguments", {})
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return None, (f"calls[{i}].arguments phải là object, đang là {type(args).__name__}. "
                      f"Tool không nhận tham số thì để {{}} hoặc bỏ hẳn.")
    return ToolCall(name=name.strip(), arguments=args, index=i), ""


def parse(text: str) -> ParseResult:
    """Bóc câu trả lời của Web thành lời gọi tool, hoặc câu trả lời cuối, hoặc lỗi khuôn."""
    text = text or ""
    khoi = _BLOCK_RE.findall(text)

    if not khoi:
        nhac = _goi_y_khi_khong_co_khoi(text)
        if nhac:
            return ParseResult(error=nhac)
        return ParseResult(final_text=text.strip())

    if len(khoi) > 1:
        # Nhiều khối = model phân vân. Gộp nhiều tool thì đã có mảng `calls`, nên nhiều khối
        # là sai khuôn chứ không phải nhu cầu thật.
        return ParseResult(error=(
            f"Tìm thấy {len(khoi)} khối ```{FENCE} trong một lượt. Chỉ được MỘT khối. "
            f"Gọi nhiều tool thì cho nhiều phần tử vào mảng 'calls' của cùng một khối."))

    body = (khoi[0] or "").strip()
    if len(body) > MAX_BLOCK_CHARS:
        return ParseResult(error=(
            f"Khối ```{FENCE} dài {len(body)} ký tự, quá trần {MAX_BLOCK_CHARS}. "
            f"Đừng dán nội dung file vào arguments; truyền đường dẫn rồi gọi tool đọc."),
            raw_block=_cat(body))

    # V1: có khối tool thì KHÔNG nhận phần văn xuôi kèm theo (spec mục 17).
    van_xuoi = _bo_khoi(text).strip()

    try:
        obj = json.loads(body)
    except (TypeError, ValueError) as e:
        return ParseResult(error=(
            f"Khối ```{FENCE} không phải JSON hợp lệ ({e}). Gửi lại đúng khuôn: "
            f'{{"calls": [{{"name": "<tên tool>", "arguments": {{...}}}}]}}'),
            raw_block=_cat(body))

    if not isinstance(obj, dict):
        return ParseResult(error=(
            f"Khối ```{FENCE} phải là một object JSON, đang là {type(obj).__name__}."),
            raw_block=_cat(body))

    raw_calls = obj.get("calls")
    if raw_calls is None:
        # Khoan dung đúng MỘT chỗ: model trả thẳng {"name": ..., "arguments": ...} không bọc
        # trong `calls`. Đây không phải đoán ý - cấu trúc vẫn tường minh, chỉ thiếu lớp bọc.
        if "name" in obj:
            raw_calls = [obj]
        else:
            return ParseResult(error=(
                f"Khối ```{FENCE} thiếu khoá 'calls'. Khuôn đúng: "
                f'{{"calls": [{{"name": "<tên tool>", "arguments": {{...}}}}]}}'),
                raw_block=_cat(body))

    if not isinstance(raw_calls, list):
        return ParseResult(error=(
            f"'calls' phải là mảng, đang là {type(raw_calls).__name__}."), raw_block=_cat(body))
    if not raw_calls:
        return ParseResult(error=(
            "'calls' rỗng. Muốn trả lời thì đừng gửi khối tool nào cả."), raw_block=_cat(body))
    if len(raw_calls) > MAX_CALLS:
        return ParseResult(error=(
            f"Gọi {len(raw_calls)} tool trong một lượt, quá trần {MAX_CALLS}. "
            f"Chia thành nhiều lượt."), raw_block=_cat(body))

    calls: list[ToolCall] = []
    for i, raw in enumerate(raw_calls):
        call, loi = _doc_mot_call(raw, i)
        if loi:
            return ParseResult(error=loi, raw_block=_cat(body))
        calls.append(call)

    return ParseResult(calls=calls, final_text=van_xuoi, raw_block=_cat(body))


# ============================================================
# Lượt sửa khuôn
# ============================================================

def loi_nhac_sua(error: str) -> str:
    """Tin nhắn gửi lại cho Web khi khuôn hỏng. Đúng MỘT lần cho mỗi lượt (spec mục 19)."""
    return (
        f"[JAVIS] Lượt vừa rồi không đọc được: {error}\n\n"
        f"Gửi lại NGAY, chỉ một trong hai:\n"
        f"  (a) đúng một khối gọi tool:\n"
        f"```{FENCE}\n"
        f'{{"calls": [{{"name": "<tên tool>", "arguments": {{}}}}]}}\n'
        f"```\n"
        f"  (b) hoặc câu trả lời cuối bằng chữ thường, KHÔNG kèm khối nào.\n"
        f"Không giải thích thêm gì ngoài hai thứ đó."
    )


def khoi_ket_qua(call: ToolCall, ket_qua: str) -> str:
    """Một mục kết quả tool, định dạng ổn định để model đọc lại được."""
    return f"[{call.index}] {call.name}\n{ket_qua}"


def tin_ket_qua(cap: list[tuple[ToolCall, str]]) -> str:
    """Gộp kết quả của cả lô tool thành MỘT tin nhắn gửi lại Web.

    Gửi một tin cho cả lô chứ không phải mỗi tool một tin: cả lô vốn được gọi trong một vòng,
    tách ra là đốt thêm lượt web đúng cái mà việc gộp tool sinh ra để tiết kiệm.
    """
    than = "\n\n".join(khoi_ket_qua(c, r) for c, r in cap)
    return (f"[JAVIS] Kết quả {len(cap)} tool vừa chạy:\n\n{than}\n\n"
            f"Dùng kết quả trên để trả lời, hoặc gọi tiếp tool nếu còn thiếu dữ liệu.")


# ============================================================
# Lời dặn khuôn, nhúng vào prompt
# ============================================================

def loi_dan(ten_tool: list[str]) -> str:
    """Đoạn dặn khuôn tool, nhúng vào tin nhắn đầu của một luồng Web.

    Ngắn là có chủ ý: web KHÔNG có system role (spec mục 3.2), nên mọi chữ ở đây nằm trong
    chính tin nhắn đầu và cạnh tranh chỗ với system prompt của Javis.
    """
    ds = ", ".join(ten_tool) if ten_tool else "(chưa có tool nào)"
    return (
        f"[TOOL PROTOCOL {TOOL_PROTOCOL_VERSION}]\n"
        f"Cần dữ liệu hoặc cần làm gì đó thì gọi tool, bằng đúng MỘT khối:\n"
        f"```{FENCE}\n"
        f'{{"calls": [{{"name": "<tên tool>", "arguments": {{...}}}}]}}\n'
        f"```\n"
        f"Luật:\n"
        f"- Gọi nhiều tool cùng lúc thì cho nhiều phần tử vào 'calls' (tối đa {MAX_CALLS}). "
        f"Mỗi vòng tốn vài chục giây nên gộp được thì gộp.\n"
        f"- Lượt có khối tool thì KHÔNG viết câu trả lời kèm theo; Javis sẽ gửi kết quả rồi "
        f"bạn trả lời ở lượt sau.\n"
        f"- Trả lời cuối thì viết chữ thường, không kèm khối nào.\n"
        f"- Không bịa tên tool. Tool đang có: {ds}."
    )
