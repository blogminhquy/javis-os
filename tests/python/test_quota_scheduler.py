"""Sổ cái TPM dùng chung cho mọi nguồn gọi model.

    python tests/run.py quota_scheduler

Vấn đề được sửa: hạn mức token mỗi phút là của TÀI KHOẢN, không phải của từng đường code.
Nhưng `admit_quota` chỉ nhìn thấy đặt chỗ của bốn đường canary, trong khi `usage_store.record`
được gọi từ mười chỗ (chat legacy, loop nền, task Kanban, nhắc hẹn, Telegram, CLI, Codex).
Mọi lượt không phải canary đốt hạn mức thật một cách vô hình, nên canary tưởng còn nhiều
token hơn thực tế rồi cho qua đúng request làm vỡ hạn mức.

Phần dễ sai nhất là ĐẾM HAI LẦN: một lượt canary vừa đặt chỗ vừa báo mức dùng thật. Ranh
giới là đặt chỗ chỉ đếm phần ĐANG BAY, còn phần đã tiêu do sổ cái nắm.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-qsched-")

import quota_scheduler as qs  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. Sổ cái thuần ----
qs.reset()
check("chưa ghi gì → dùng 0", qs.used("groq", "llama", 60, now=1000.0) == 0)

qs.observe("groq", "llama", 5000, now=1000.0)
qs.observe("groq", "llama", 3000, now=1010.0)
check("cộng dồn trong cửa sổ", qs.used("groq", "llama", 60, now=1020.0) == 8000)
# now=1065, cửa sổ 60 → mốc cắt 1005: sự kiện t=1000 rơi ra, t=1010 còn lại.
check("ra khỏi cửa sổ thì rơi ra", qs.used("groq", "llama", 60, now=1065.0) == 3000)
check("qua hết cửa sổ thì về 0", qs.used("groq", "llama", 60, now=1200.0) == 0)

check("tách theo model", qs.used("groq", "model-khac", 60, now=1020.0) == 0)
check("tách theo provider", qs.used("openai", "llama", 60, now=1020.0) == 0)
check("provider không phân biệt hoa thường",
      qs.used("GROQ", "llama", 60, now=1020.0) == 8000)


# Kế toán là việc phụ, không được ném lỗi làm hỏng lượt chat.
qs.observe("groq", "llama", None, now=1020.0)
qs.observe("groq", "llama", "abc", now=1020.0)
qs.observe("groq", "llama", -5, now=1020.0)
check("giá trị rác không làm đổi sổ và không nổ",
      qs.used("groq", "llama", 60, now=1020.0) == 8000)

check("snapshot nêu đúng mức dùng",
      qs.snapshot(60, now=1020.0).get("groq|llama") == 8000)

# ---- 2. Móc PHỔ QUÁT: mọi lượt đi qua usage_store.record đều vào sổ ----
qs.reset()
import usage_store  # noqa: E402

usage_store.record("groq", "llama-3.3-70b-versatile", 4000, 500)
check("usage_store.record tự nạp vào sổ cái dùng chung",
      qs.used("groq", "llama-3.3-70b-versatile", 60) == 4500)

# Đây là điểm mấu chốt: loop nền / task / Telegram đều gọi record(), nên chúng KHÔNG còn
# đốt hạn mức vô hình nữa.
usage_store.record("groq", "llama-3.3-70b-versatile", 2000, 0)
check("nguồn thứ hai (loop nền) cộng dồn vào cùng sổ",
      qs.used("groq", "llama-3.3-70b-versatile", 60) == 6500)

# ---- 3. admit_quota phải TRỪ phần các nguồn khác đã đốt ----
from pathlib import Path  # noqa: E402

from context_runtime import ObserveRuntime  # noqa: E402

_settings = {"context_runtime": {"mode": "canary", "retention_days": 14}}
_tmp = Path(tempfile.mkdtemp(prefix="javis-qsched-rt-"))
_rt = ObserveRuntime(_tmp / "runtime", settings_reader=lambda: _settings)
_trace = _rt.start_turn("sid-quota", str(_tmp / "brain"), "dashboard")

qs.reset()
_adm = _rt.admit_quota(_trace, "groq", "llama-x", 5000, 500, 12000, 60)
check("sổ trống: xin 5.500/12.000 → cho qua", _adm.allowed is True)

# Giờ giả lập loop nền vừa đốt 10.000 token của CÙNG tài khoản.
qs.observe("groq", "llama-x", 10000)
_trace2 = _rt.start_turn("sid-quota-2", str(_tmp / "brain"), "dashboard")
_adm2 = _rt.admit_quota(_trace2, "groq", "llama-x", 5000, 500, 12000, 60)
check("loop nền đã đốt 10.000 → xin thêm 5.500 phải bị TỪ CHỐI",
      _adm2.allowed is False)
check("từ chối đúng lý do rolling_tpm", _adm2.reason == "rolling_tpm")
check("số used đã bao gồm phần nguồn khác đốt", _adm2.used_tokens >= 10000)

# Và chiều ngược lại: hết cửa sổ thì lại cho qua.
qs.reset()
_trace3 = _rt.start_turn("sid-quota-3", str(_tmp / "brain"), "dashboard")
_adm3 = _rt.admit_quota(_trace3, "groq", "llama-x", 5000, 500, 12000, 60)
check("sổ sạch trở lại → cho qua", _adm3.allowed is True)

# ---- 4. KHÔNG đếm hai lần ----
# Một lượt canary đặt chỗ rồi báo số thật. Nếu admit_quota vẫn cộng cả phần đã tiêu trong
# bảng đặt chỗ LẪN sổ cái thì nó tự bóp nghẹt throughput của chính mình.
qs.reset()
_trace4 = _rt.start_turn("sid-double", str(_tmp / "brain"), "dashboard")
_a = _rt.admit_quota(_trace4, "groq", "llama-dbl", 1000, 200, 12000, 60)
check("lượt đầu được nhận", _a.allowed is True)
_rt.consume_quota(_trace4, _a.reservation_id, 1000, 200)   # báo số thật, chốt đặt chỗ
qs.observe("groq", "llama-dbl", 1200)                       # usage_store cũng ghi sổ

_trace5 = _rt.start_turn("sid-double-2", str(_tmp / "brain"), "dashboard")
_b = _rt.admit_quota(_trace5, "groq", "llama-dbl", 1000, 200, 12000, 60)
check("lượt sau vẫn được nhận (không bị đếm hai lần)", _b.allowed is True)
check("used chỉ tính 1.200 chứ không phải 2.400",
      _b.used_tokens == 1200)

# ---- 5. Bất biến CẶP ĐÔI: ghi mức dùng vào runtime thì phải ghi cả vào sổ cái ----
# Đây là rào chống việc tái tạo đúng lỗi vừa sửa. Sổ cái là nguồn sự thật duy nhất cho
# "đã tiêu bao nhiêu", còn bảng đặt chỗ chỉ giữ phần đang bay. Một chỗ gọi tương lai ghi
# vào runtime mà quên usage_store sẽ tạo ra mức dùng VÔ HÌNH y như cũ, và không có gì
# báo động vì cả hai lời gọi đều "chạy đúng".
import re  # noqa: E402

_main_src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
_lines = _main_src.split("\n")
_unpaired = []
for _i, _ln in enumerate(_lines):
    if "_CONTEXT_RUNTIME.record_usage(" not in _ln:
        continue
    # usage_store.record phải xuất hiện trong vài dòng ngay trước đó (cùng nhánh xử lý)
    _window = "\n".join(_lines[max(0, _i - 8):_i])
    if "usage_store.record(" not in _window:
        _unpaired.append(_i + 1)

check("mọi chỗ ghi mức dùng vào runtime đều ghi kèm vào sổ cái dùng chung",
      not _unpaired)
if _unpaired:
    print("     dòng thiếu cặp:", _unpaired)
check("bất biến này có ý nghĩa (tìm thấy ít nhất vài cặp thật)",
      _main_src.count("_CONTEXT_RUNTIME.record_usage(") >= 4)

# ---- 6. Số liệu chẩn đoán phải ĐẾN ĐƯỢC MẮT NGƯỜI ----
# Họ lỗi lặp lại nhiều nhất trong nhánh này: code đúng, test xanh, nhưng không nối được với
# thứ nó phục vụ. Chính tpm_window đã dính: API trả về mà trang Chẩn đoán không vẽ, nên cái
# số sinh ra để trả lời "sao tôi bị chặn" lại vô hình đúng lúc cần.
_console = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
for _field in ("tpm_window", "quota_presets", "canaries", "registry", "engine_hien_tai"):
    check(f"trang Chẩn đoán có dùng trường '{_field}' mà API trả về",
          _field in _console)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_quota_scheduler: tất cả pass")
