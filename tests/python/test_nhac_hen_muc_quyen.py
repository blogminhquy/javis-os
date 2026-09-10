"""Nhắc hẹn phải LÀM ĐƯỢC việc user đã hẹn.

    python tests/run.py nhac_hen_muc_quyen      (KHÔNG mạng, không spawn engine)

Chủ repo báo 2026-08-07 sau khi soát lại một loạt nhắc hẹn: ngày giờ đặt đúng hết, nhưng tới
giờ không có cái nào làm được việc, vì mức quyền bị ghim cứng ở chỉ-đọc. Nhóm tool hành động
ra ngoài (gửi tin, đăng bài, đặt lịch) bị hub xếp loại nguy hiểm nên ở mức đó agent không
những gọi không được mà còn KHÔNG NHÌN THẤY chúng, và prompt còn dặn thêm "tuyệt đối không gửi
tin ra ngoài". Kết cục: đúng giờ nó vẫn thức dậy, chạy, rồi báo về là không làm được - còn
việc thì vẫn chưa ai làm.

Chốt hướng (chủ repo, 2026-08-07): "Bỏ các quyền giúp anh, có cảnh báo là được." Rồi tới
2026-09-10 chủ repo bỏ luôn luật an toàn "không giao tự động tiền/đơn/đăng bài/nhắn khách" trên
toàn Javis: câu cảnh báo lúc tạo (`canh_bao`) và hộp cảnh báo đỏ trên form được gỡ, loop cũng
mặc định toàn quyền như nhắc hẹn.

Test này khoá ba thứ: mặc định toàn quyền, ba mức dựng engine khác nhau thật, và phần cảnh báo
cũ đã gỡ hết (không còn nửa bản nào sót lại trong server, plugin, CLAUDE.md hay giao diện).
"""
import asyncio
import os
import sys
import tempfile

_STATE = tempfile.mkdtemp(prefix="javis-nhachen-")
os.environ.setdefault("JAVIS_STATE_DIR", _STATE)

from _paths import ROOT, SERVER  # noqa: E402,F401

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import reminders as R  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. Mặc định và chuẩn hoá ----
check("mặc định là toàn quyền", R.MUC_QUYEN_MAC_DINH == "full")
check("ba mức, cùng bộ từ với loop",
      R.VALID_MUC_QUYEN == {"suggest", "auto", "full"})
check("bản ghi CŨ (chưa có trường này) chạy theo mặc định, không rơi vào chỉ-đọc",
      R.muc_quyen_cua({"id": "r_cu"}) == "full")
check("mức lạ trong file cũng quy về mặc định chứ không nổ",
      R.muc_quyen_cua({"muc_quyen": "linh tinh"}) == "full")
check("mức hợp lệ thì giữ nguyên",
      R.muc_quyen_cua({"muc_quyen": "suggest"}) == "suggest"
      and R.muc_quyen_cua({"muc_quyen": "auto"}) == "auto")


# ---- 2. Ba mức dựng engine KHÁC NHAU thật ----
# Đây là phần đáng canh nhất: nhãn trên thẻ đúng mà engine vẫn dựng như cũ thì lỗi y nguyên,
# chỉ khác là giờ nó im lặng.
class _CLI:
    def __init__(self, **kw):
        self.kw = kw
        self.max_wall_s = None
        self.mcp_config = None
        self.mcp_strict = False
        self.disallowed_tools = None

    def is_available(self):
        return True

    async def query(self, prompt):
        _GHI["prompt"] = prompt
        yield {"type": "final", "content": "xong"}


_GHI = {}


class _Deps:
    safe_tools = ["Read", "Write", "Edit"]
    readonly_tools = ["Read", "Glob", "Grep"]
    mcp_allow_patterns = staticmethod(lambda: ["mcp__javis__*"])
    aux_swap = None
    aux_model = staticmethod(lambda: None)

    @staticmethod
    def brain_root(brain):
        return _STATE

    @staticmethod
    def build_system_prompt(brain):
        return "sysprompt"

    @staticmethod
    def apply_mcp(cli, mode="full", brain=None):
        _GHI["hub_mode"] = mode
        _GHI["hub_brain"] = brain


def _chay(muc_quyen):
    _GHI.clear()

    def _fake_engine(**kw):
        cli = _CLI(**kw)
        _GHI["allowed_tools"] = kw.get("allowed_tools")
        return cli

    that = R.claude_engine
    R.claude_engine = _fake_engine
    try:
        feat = R.RemindersFeature.__new__(R.RemindersFeature)
        feat.deps = _Deps()
        asyncio.run(feat._run_task("brain", "gửi link vào nhóm", muc_quyen))
    finally:
        R.claude_engine = that
    return dict(_GHI)


g = _chay("full")
check("toàn quyền: KHÔNG khoá allowlist (thấy được cả nhóm tool hành động ra ngoài)",
      g["allowed_tools"] is None)
check("toàn quyền: hub chạy ở mức full", g["hub_mode"] == "full")
check("toàn quyền: có truyền brain (plugin in-process cần biết vault nào)",
      g["hub_brain"] == "brain")
check("toàn quyền: prompt KHÔNG còn câu cấm gửi tin ra ngoài",
      "KHÔNG tạo đơn" not in g["prompt"] and "gửi tin ra ngoài" not in g["prompt"])
check("toàn quyền: prompt dặn đừng hỏi lại rồi ngồi đợi (không ai ngồi cạnh)",
      "không ai ngồi cạnh" in g["prompt"].lower() or "Không có ai ngồi cạnh" in g["prompt"])

g = _chay("auto")
check("ghi file: allowlist là bộ tool ghi được", "Write" in (g["allowed_tools"] or []))
check("ghi file: vẫn kèm pattern MCP để gọi được tool đọc",
      "mcp__javis__*" in (g["allowed_tools"] or []))
check("ghi file: hub chạy ở mức auto", g["hub_mode"] == "auto")
check("ghi file: prompt vẫn cấm hành động ra ngoài",
      "KHÔNG tạo đơn" in g["prompt"] and "gửi tin ra ngoài" in g["prompt"])

g = _chay("suggest")
check("chỉ đọc: allowlist KHÔNG có tool ghi", "Write" not in (g["allowed_tools"] or []))
check("chỉ đọc: hub chạy ở mức suggest", g["hub_mode"] == "suggest")
check("chỉ đọc: prompt nói rõ không ghi file", "KHÔNG ghi file" in g["prompt"])

g = _chay("")     # mức rỗng -> mặc định
check("không nói mức thì chạy theo mặc định (toàn quyền)",
      g["allowed_tools"] is None and g["hub_mode"] == "full")


# ---- 3. Cảnh báo cũ đã gỡ hết, không sót nửa bản nào ----
# Một luật an toàn có hai bản thì bản bị quên là bản sai; luật đã bỏ mà còn sót một bản thì
# người dùng vẫn đọc thấy một cảnh báo mà app không còn làm theo.
check("reminders.py không còn hằng cảnh báo toàn quyền", not hasattr(R, "CANH_BAO_TOAN_QUYEN"))
SRC = (SERVER / "reminders.py").read_text(encoding="utf-8")
check("endpoint tạo không còn trả canh_bao", '"canh_bao"' not in SRC)

PLUGIN = (ROOT / "system" / "plugins" / "javis-schedule" / "plugin.py").read_text(encoding="utf-8")
check("tool javis_schedule không còn đọc lại cảnh báo", 'data.get("canh_bao")' not in PLUGIN)
check("tool javis_schedule nói mức quyền của nhắc hẹn vừa tạo", 'data.get("muc_quyen")' in PLUGIN)
check("tool nhận tham số muc_quyen", '"muc_quyen"' in PLUGIN)

CLAUDEMD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
check("CLAUDE.md không còn bắt đọc lại nguyên văn cảnh báo", "read it back VERBATIM" not in CLAUDEMD)
check("CLAUDE.md vẫn dạy tham số muc_quyen", "muc_quyen" in CLAUDEMD)
check("CLAUDE.md: loop tạo từ chat mặc định full", "defaults to `mode: full`" in CLAUDEMD)
check("CLAUDE.md không còn cấm tự đặt full", "NEVER set `mode: full`" not in CLAUDEMD)


# ---- 4. Giao diện: mức quyền phải hiện ra, hộp cảnh báo đỏ và confirm() đã gỡ ----
JS = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("thẻ nhắc hẹn hiện mức quyền", "MQ_LBL" in JS and "rm-mq" in JS)
check("form có ô chọn mức quyền", "lpRemMq" in JS)
check("form không còn hộp cảnh báo đỏ khi chọn toàn quyền", "lpRemMqWarn" not in JS)
check("form loop không còn hộp cảnh báo đỏ", "lpFullWarn" not in JS)
check("không còn confirm() khi lưu hay bật loop toàn quyền",
      "si_full_confirm" not in JS and "si_toggle_confirm" not in JS)
check("loop mới mặc định toàn quyền trên form", 'fcur = { mode: "full" }' in JS)
check("ô mức quyền chỉ hiện với kiểu tự-làm", 'frmode === "task" ? "" : "none"' in JS)
check("form gửi muc_quyen lên server", JS.count("muc_quyen: frmq") + JS.count('"muc_quyen", frmq') >= 2)
CSS = (ROOT / "dashboard" / "style.css").read_text(encoding="utf-8")
check("mức toàn quyền nổi bật trên thẻ, không chìm như dòng phụ chú", ".rm-mq.on" in CSS)


if _fails:
    raise SystemExit(f"\nFAIL - test_nhac_hen_muc_quyen: {len(_fails)} lỗi: {_fails}")
print("\nOK - test_nhac_hen_muc_quyen: tất cả pass")
