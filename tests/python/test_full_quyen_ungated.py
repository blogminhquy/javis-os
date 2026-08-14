"""Mức TOÀN QUYỀN phải thật sự toàn quyền, ở CẢ BỐN đường chạy nền.

    python tests/run.py full_quyen      (KHÔNG mạng, KHÔNG cần Claude CLI)

Lỗi thật, ảnh chụp từ nhóm người dùng: một nhắc hẹn định kỳ "tới giờ đọc Google Sheet rồi đăng
bài lên Fanpage" chạy tới nơi rồi dừng, báo về Telegram:

    "Sheet Google cần đọc qua Google Drive, nhưng phiên chạy nhắc hẹn này bị chặn quyền, chỉ
     dùng được tool file nội bộ và mcp__javis, không gọi được Google Drive."

Chủ vào bảo "đăng lại đi" trong chat thường thì nó đăng ngay. Tức là việc làm ĐƯỢC, chỉ phiên
nền là không.

Gốc rễ: Gmail / Google Drive / Google Calendar đấu vào TÀI KHOẢN Claude, không nằm trong
registry MCP của Javis. Chúng chỉ gọi được bằng tool NATIVE `mcp__<tên>__*`, mà tool native chỉ
xuất hiện khi phiên Claude chạy KHÔNG có allowlist (`allowed_tools=None` → SDK nạp
`setting_sources`). Bất kỳ thứ gì âm thầm dựng lại rào ở mức full đều giết cả nhóm công cụ đó,
và model - vốn chỉ thấy "gọi tool không được" - sẽ đổ cho quyền, làm chủ đi sửa nhầm chỗ.

Bốn đường nền không chia chung một hàm dựng engine (cố ý: rào của chúng khác nhau thật), nên
luật "full ⇒ ungated" phải được canh ở từng đường một. Đó là việc của file này.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import sys

import aux_engine   # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ============================================================
# 1. Việc Kanban - đường DUY NHẤT từng bỏ quên `execution_mode`
# ============================================================
from tasks import TasksFeature   # noqa: E402


class _Deps:
    safe_tools = ["Read", "Write", "Glob"]
    readonly_tools = ["Read", "Glob"]
    mcp_allow_patterns = staticmethod(lambda: ["mcp__javis"])


_fake = object.__new__(TasksFeature)
_fake.deps = _Deps()


def _lane(mode, capability="files"):
    return TasksFeature._lane_tools(_fake, {"execution_mode": mode, "capability": capability})


_tools, _mode, _dis = _lane("full")
check("việc Kanban mức full -> KHÔNG allowlist", _tools is None)
check("việc Kanban mức full -> KHÔNG chặn tool nào", _dis == [])
check("và mode vẫn đi tiếp xuống hub đúng chữ", _mode == "full")

# Mức full phải ungated ở MỌI capability: "external-write" (đăng bài, gửi tin) chính là nhóm
# cần connector ambient nhất, và cũng là nhóm server chỉ cho chạy khi mode=full.
for _cap in ("files", "code", "research", "mcp-read", "external-write"):
    check(f"full + capability '{_cap}' -> vẫn ungated", _lane("full", _cap)[0] is None)

# Ba mức dưới GIỮ NGUYÊN rào. Nới chúng ra là mất chỗ dựa của chính chúng.
for _m in ("auto", "suggest", "", None, "FULL_", "toanquyen"):
    _t, _, _d = _lane(_m)
    check(f"mức {_m!r} (không phải full) -> VẪN có allowlist", isinstance(_t, list) and _t)
    check(f"mức {_m!r} -> vẫn chặn Task", "Task" in _d)
_t_mcp, _, _ = _lane("mcp-read" and "auto", "mcp-read")
check("mức auto vẫn được gọi MCP qua hub", "mcp__javis" in _t_mcp)


# ============================================================
# 2. Chuỗi engine dự phòng KHÔNG được bật ở mức full
# ============================================================
# Rơi engine ở mức full tệ hơn chết hẳn: engine API không có tool native nên việc dừng giữa
# chừng, model không biết mình vừa bị đổi engine nên báo sai lý do, và mắt trước có thể đã làm
# xong một phần việc (đăng được 1 trong 3 bài) rồi mới gãy.
class _FakeCli:
    def __init__(self):
        self.model = None
        self.system_prompt = "sys"
        self.javis_vault = "/tmp/brain"
        self.javis_mode = None
        self.tag = "reminder"
        self.cwd = "/tmp/brain"


_S_OR = {"model": {"openrouter_key": "sk-or", "auxiliary": {"provider": "anthropic-cli", "model": ""}}}

_out_full = aux_engine.swap(_FakeCli(), mode="full", tag="reminder", settings=_S_OR)
check("CANARY: mức full KHÔNG dựng chuỗi dự phòng, dù có sẵn key OpenRouter",
      not isinstance(_out_full, aux_engine._FallbackChain))

# Ở mức auto/suggest thì chuỗi dự phòng vẫn là thứ tốt: việc chỉ đọc/ghi vault chạy được trên
# engine nào cũng xong, và "việc nền phải chạy chứ không chết" vẫn đúng ở đó.
_out_auto = aux_engine.swap(_FakeCli(), mode="auto", tag="loop", settings=_S_OR)
check("mức auto VẪN có chuỗi dự phòng (việc nhẹ thì chạy được là hơn)",
      isinstance(_out_auto, aux_engine._FallbackChain))

# User chọn hẳn một provider API cho việc nền thì tôn trọng, nhưng vẫn KHÔNG nối thêm mắt sau.
_S_API = {"model": {"openrouter_key": "sk-or", "groq_api_key": "sk-groq",
                    "auxiliary": {"provider": "groq", "model": "llama"}}}
_out_api = aux_engine.swap(_FakeCli(), mode="full", tag="reminder", settings=_S_API)
check("full + user chọn provider API -> dùng đúng provider đó",
      getattr(_out_api, "provider", None) == "groq")
check("full + provider API -> vẫn KHÔNG có chuỗi dự phòng",
      not isinstance(_out_api, aux_engine._FallbackChain))

# Provider chưa có key thì lui về Claude chứ không chết - hành vi cũ, giữ nguyên ở mức full.
_S_THIEU = {"model": {"auxiliary": {"provider": "groq", "model": "llama"}}}
_cli_thieu = _FakeCli()
check("full + provider chưa có key -> lui về Claude, không chết",
      aux_engine.swap(_cli_thieu, mode="full", settings=_S_THIEU) is _cli_thieu)


# ============================================================
# 3. Engine API phải KHAI THẬT là nó thiếu tool native
# ============================================================
# Không có lời khai này thì model chỉ thấy "gọi tool không được" rồi tự dựng lý do nghe hợp lý
# mà sai. Đúng cái đã xảy ra: nó đổ cho quyền, chủ đi sửa mức quyền, mà mức quyền không hề sai.
_src_aux = (SERVER / "aux_engine.py").read_text(encoding="utf-8")
for _phai_co in ("Google Drive", "mcp__<tên>__*", "Bash", "không có công cụ"):
    check(f"engine API khai rõ {_phai_co!r}", _phai_co in _src_aux)
check("và cấm thẳng chuyện đổ cho quyền",
      "không mô tả chuyện này là bị chặn quyền" in _src_aux)


# ============================================================
# 4. Ba đường nền còn lại - canary nguồn
# ============================================================
# Nhắc hẹn và loop vốn ĐÃ đúng; canary ở đây để không ai vô tình bịt lại như tasks.py từng bị.
_src_rem = (SERVER / "reminders.py").read_text(encoding="utf-8")
check("nhắc hẹn mức full -> allowed_tools=None",
      'tag="reminder", allowed_tools=None' in _src_rem)
_src_loop = (SERVER / "self_improve.py").read_text(encoding="utf-8")
check("loop mức full -> allowed_tools=None",
      'tag="loop", allowed_tools=None' in _src_loop)

# `strict` = chỉ dùng MCP của Javis. Ở mức full nó phải bị bỏ qua, nếu không thì mở allowlist
# rồi lại khoá cửa sau: connector ambient nằm NGOÀI registry của Javis.
_src_main = (SERVER / "main.py").read_text(encoding="utf-8")
_ham = _src_main[_src_main.index("def _apply_mcp("):_src_main.index("def _apply_mcp(") + 2200]
check("CANARY: mức full KHÔNG bao giờ bật strict-mcp-config",
      'cli.mcp_strict = (mode != "full"' in _ham)

# Tự học cố ý CHỈ ĐỌC - đây không phải thiếu sót, nên canary giữ nó ở nguyên trạng.
_src_learn = (SERVER / "learn.py").read_text(encoding="utf-8")
check("tự học vẫn chỉ đọc (cố ý, không nới)",
      "allowed_tools=self.deps.readonly_tools" in _src_learn)

print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test full_quyen_ungated đã qua.")
