"""Vì sao mức Siêu tiết kiệm chưa chạy lần nào trên máy đấu nhiều MCP.

    python tests/run.py duong_tat_bi_chan

Chủ repo báo: "chưa lần nào chat anh nhìn thấy chữ Tức thì, có chỗ thì không hiện gì". Hai
triệu chứng, hai lỗi khác nhau, và cả hai đều KHÔNG lộ ra trên máy dev.

1. ĐƯỜNG TẮT BỊ CHẶN Ở MỌI LƯỢT. Cửa nhận lượt xét `candidate_count > 0` - số ứng viên dò
   được bằng CHỮ, đếm TRƯỚC khi chấm điểm và TRƯỚC khi lọc quyền. Máy đấu vài trăm tool MCP
   (Gmail, Drive, Lịch, quảng cáo...) thì gần như câu tiếng Việt nào cũng dò trúng vài tool
   qua một từ chung, nên điều kiện đó ĐÚNG với mọi lượt và đường tắt không bao giờ chạy. Càng
   đấu nhiều nguồn càng không tiết kiệm được - ngược hẳn thứ nó hứa. Máy dev có kho tool gần
   như rỗng nên mọi test đều xanh trong khi máy thật đứng hình.

2. NHIỀU NHÁNH TRẢ LỜI KHÔNG GẮN NHÃN. Dòng "chế độ + token" dưới câu trả lời do gói tin
   `response` mang theo, mà chỉ vài nhánh gắn nó. Nhánh gateway (nhắc hẹn), nhánh tra cứu,
   nhánh từ chối vì vượt hạn mức... đều gửi câu trả lời trần - và người dùng thấy đúng cái
   họ mô tả: có lượt hiện, có lượt không hiện gì.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import ast
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-duongtat-")

import config as cfg  # noqa: E402
import fast_path_runtime as fp  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ============================================================
# 1. Cửa nhận lượt xét ĐIỂM, không xét số lần dò trúng chữ
# ============================================================
_pol = fp.CanaryPolicy.from_settings(cfg.read_settings())
check("có ngưỡng điểm khớp", 0.0 < _pol.min_resolver_score <= 1.0)
# Phải nằm trong settings.json để người vận hành chỉnh được. Mã có giá trị dự phòng, nên
# thiếu khoá này thì hành vi vẫn đúng - chỉ có điều không ai tìm thấy nút mà vặn.
check("ngưỡng có mặt trong cấu hình mặc định để chỉnh được",
      "min_resolver_score" in ((cfg._DEFAULT["context_runtime"] or {}).get("canary") or {}))
check("ngưỡng đọc được từ cấu hình",
      fp.CanaryPolicy.from_settings(
          {"context_runtime": {"canary": {"min_resolver_score": 0.9}}}).min_resolver_score == 0.9)


class _Runtime:
    def __init__(self):
        self.events = []

    def pin_execution_path(self, trace, path, bucket, ver, reason):
        return path

    def record_runtime_event(self, trace, ten, data):
        self.events.append((ten, data))

    def admit_quota(self, *a, **k):
        class _Ok:
            allowed = True
            reason = ""
            reservation_id = "r1"
        return _Ok()


class _Registry:
    def inventory_status(self, brain):
        return {"ready": True, "age_seconds": 1.0, "revision": "reg_x"}


class _Resolver:
    """Giả lập máy THẬT: kho vài trăm tool nên câu nào cũng dò trúng, nhưng không cái nào
    thật sự khớp. `ranked` là danh sách đã chấm điểm."""

    def __init__(self, diem, so_ung_vien=180):
        self.diem, self.so = diem, so_ung_vien

    def resolve(self, objective, brain, actor):
        return {"policy_version": "p", "registry_revision": "reg_x",
                "candidate_count": self.so, "selected_count": 0,
                "ranked": [{"capability_id": "c1", "name": "x", "score": self.diem}],
                "filtered": {"required_mode": 12}, "miss_class": "coverage"}


class _Capsule:
    capsule_hash = "h"
    rendered_request = {"messages": [{"role": "system", "content": "x"}]}
    path = "fast"


class _Compiled:
    status = "compiled"
    capsule = _Capsule()
    trace_report = {"status": "compiled", "path": "fast", "estimated_input_tokens": 100,
                    "max_input_tokens": 10000, "reserved_output_tokens": 1000,
                    "preflight_decision": "would_allow"}


class _Compiler:
    def compile_canary(self, request, resolution):
        return _Compiled()


class _Trace:
    session_id = "s1"
    task_id = "t1"
    step_id = "st1"
    channel = "dashboard"
    registry_revision = "reg_x"


def _lam(diem, so_ung_vien=180):
    rt = _Runtime()
    admission = fp.FastPathCanary(
        runtime=rt, registry=_Registry(), resolver=_Resolver(diem, so_ung_vien),
        compiler=_Compiler(),
        settings_reader=lambda: {"context_runtime": {
            "mode": "canary",
            "subscription_context": {"context_window": 180000, "reserved_output_tokens": 8000},
            "canary": {"allocation_basis_points": 10000, "channels": ["dashboard"],
                       "provider_kinds": ["api", "oauth", "cli"]},
        }},
    )
    return admission.prepare(_Trace(), "giờ Việt Nam là mấy giờ", "brain-a", "dashboard",
                             "anthropic", "claude", "cli"), rt


# Đây là ca THẬT trên máy chủ repo: 180 tool dò trúng, không cái nào khớp thật.
_plan, _rt = _lam(diem=0.05)
check("CANARY: dò trúng nhiều nhưng điểm thấp thì VẪN đi đường tắt",
      _plan.action == "execute")
check("và lý do không còn là 'mơ hồ'", _plan.reason != "capability_ambiguous")

# Có cái SUÝT khớp thì vẫn phải nhường đường thường - bộ lọc không được nới thành vô dụng.
_plan, _ = _lam(diem=0.9)
check("có capability suýt khớp thì nhường đường thường",
      _plan.action == "legacy" and _plan.reason == "capability_ambiguous")

# Ngay ở ngưỡng thì phải chặn (>=), không được lọt.
_plan, _ = _lam(diem=_pol.min_resolver_score)
check("đúng ngay ngưỡng thì chặn", _plan.reason == "capability_ambiguous")

# Không có ứng viên nào thì đương nhiên đi tắt.
_plan, _ = _lam(diem=0.0, so_ung_vien=0)
check("kho tool rỗng thì đi tắt như cũ", _plan.action == "execute")

# Điểm phải được ghi lại, nếu không thì lần sau lại đoán mò như lần này.
_plan, _rt = _lam(diem=0.05)
_ev = dict(_rt.events).get("resolver.canary") or {}
check("có ghi lại điểm cao nhất để chẩn đoán", "top_score" in _ev)
check("và ghi cả ngưỡng đang dùng", "min_resolver_score" in _ev)


# ============================================================
# 2. Mọi nhánh trả lời trong lượt chat phải gắn nhãn chế độ
# ============================================================
_src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
_lines = _src.split("\n")
_thieu = []
for i, l in enumerate(_lines):
    if '"type": "response"' not in l:
        continue
    j = i
    while j < len(_lines) and not _lines[j].strip().startswith("}))"):
        j += 1
    if j >= len(_lines) or j - i > 10:
        continue
    if "_ctx_frame" not in "\n".join(_lines[i:j + 1]):
        _thieu.append(i + 1)
check(f"CANARY: mọi gói trả lời đều mang nhãn chế độ (thiếu ở dòng {_thieu})", not _thieu)

# Và nhãn đó phải nói được đường tắt, nếu không thì gắn cũng bằng thừa.
_ast = ast.parse(_src)
check("hàm dựng nhãn có thật",
      any(isinstance(n, ast.FunctionDef) and n.name == "_ctx_frame" for n in ast.walk(_ast)))


# ============================================================
# 3. Trang phải nói được lý do LẶP LẠI, không bắt người dùng tự đếm
# ============================================================
import main  # noqa: E402

# Lý do nhiều nhất CỐ Ý đứng sau theo bảng chữ cái: xếp nhầm theo tên thay vì theo số lần
# thì dữ liệu này lộ ra ngay, còn dữ liệu thuận chiều thì hai cách xếp cho cùng kết quả và
# test đó không canh được gì.
_vs = main._vi_sao_chua_di_tat([
    {"execution_path": "sources", "ly_do": "registry_stale"},
    {"execution_path": "sources", "ly_do": "registry_stale"},
    {"execution_path": "legacy", "ly_do": "capability_ambiguous"},
    {"execution_path": "fast", "ly_do": "admitted"},
    {"execution_path": "sources", "ly_do": ""},
])
check("đếm đúng số lượt không đi tắt", _vs["tong"] == 3)
check("xếp lý do nhiều nhất lên đầu",
      _vs["top"] and _vs["top"][0]["ma"] == "registry_stale"
      and _vs["top"][0]["so_lan"] == 2)
check("lượt đã đi tắt không bị tính là lý do",
      all(x["ma"] != "admitted" for x in _vs["top"]))

# Khối "vì sao chưa đi tắt" đi cùng trang Tiết kiệm khi trang đó gộp vào Mức dùng (0.24.7).
# Bảng xếp hạng lý do vẫn được tính và vẫn trả qua `/runtime/diagnostics` cho người vận hành;
# chỉ là không còn màn hình nào bắt buộc phải vẽ nó cho người dùng cuối.
_main_src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("máy chủ vẫn xếp hạng lý do và trả ra", "_vi_sao_chua_di_tat(" in _main_src
      and '"vi_sao"' in _main_src)
check("máy chủ có trả khối đó", '"vi_sao"' in _src)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_duong_tat_bi_chan: tất cả pass")
