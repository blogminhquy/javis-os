"""Bật tiết kiệm token KHÔNG được biến câu trả lời thành khối JSON.

    python tests/run.py capsule_khong_ra_json

Chủ repo chụp lại khung chat trên điện thoại, chỗ đáng lẽ là lời chào thì hiện nguyên:

    {
    "channel": "dashboard",
    "language": "match_user",
    "must_report_missing_evidence": true,
    "no_false_action_claim": true,
    "type": "text",
    "content": "Chào anh Minh Quy!"
    }

Nguyên nhân: capsule nhét thẳng object đó vào prompt dưới nhãn `Output contract: {...}`. Đặt
một object JSON ngay trước chỗ model phải trả lời thì model yếu hiểu là "hãy phát ra object
này" - và nó phát thật, kèm luôn câu trả lời nhét vào trường "content".

Đây là lỗi NẶNG nhất trong ba lỗi từ tấm ảnh đó: hai lỗi kia làm giao diện xấu, lỗi này làm
chính tính năng tiết kiệm token sinh ra rác. Bật lên là hỏng, nên thà đừng bật.

Object vẫn giữ nguyên trong CompileResult.output_contract cho trace đọc; chỉ phần ĐƯA CHO
MODEL đổi sang lời. Máy đọc dữ liệu, model đọc chữ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-capsule-"))

import context_compiler as cc  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


_SRC = (ROOT / "server" / "context_compiler.py").read_text(encoding="utf-8")

# ============================================================
# 1. Không còn chỗ nào nhét JSON hợp đồng vào prompt
# ============================================================
# Ba chỗ dựng system prompt đều từng làm việc này. Sót một chỗ là còn một đường sinh ra rác.
check("CANARY: không còn nhãn 'Output contract: ' kèm JSON trong prompt",
      'Output contract: "' not in _SRC)
check("và không còn json.dumps(output_contract) ở chỗ dựng prompt",
      "json.dumps(output_contract" not in _SRC)
check("có hàm viết hợp đồng thành LỜI", "_output_contract_text" in _SRC)
check("cả ba chỗ dựng prompt đều dùng hàm đó",
      _SRC.count("self._output_contract_text(request.channel)") >= 3)

# ============================================================
# 2. Lời dặn phải CẤM ĐÍCH DANH việc bọc JSON
# ============================================================
# Không đủ nếu chỉ "hãy trả lời bằng văn xuôi": model vừa nhìn thấy một object thì mặc định
# của nó là bắt chước. Phải nói thẳng là không được bọc.
_loi = cc.ContextCompiler._output_contract_text("dashboard")
check("cấm đích danh việc bọc trong JSON", "không bọc câu trả lời" in _loi.casefold()
      or "không bọc" in _loi.casefold())
check("có nhắc JSON để lời cấm không mơ hồ", "JSON" in _loi)
check("cấm in lại chính lời dặn này", "không in lại" in _loi.casefold())
check("vẫn giữ luật ngôn ngữ theo người dùng", "ngôn ngữ người dùng" in _loi)
check("vẫn giữ luật thiếu dữ liệu phải nói", "thiếu" in _loi.casefold())
check("vẫn giữ luật không nhận bừa là đã làm xong", "bằng chứng" in _loi.casefold())
check("nêu đúng kênh", "Dashboard" in _loi)
check("kênh Telegram ra lời riêng",
      "Telegram" in cc.ContextCompiler._output_contract_text("telegram"))
check("kênh lạ không làm nổ", isinstance(cc.ContextCompiler._output_contract_text(""), str))

# Và bản thân lời dặn TUYỆT ĐỐI không được trông giống JSON, nếu không lại đúng cái bẫy cũ.
for _dau in ("{", "}", '":'):
    check(f"CANARY: lời dặn không chứa ký tự {_dau!r} của JSON", _dau not in _loi)
check("KHÔNG dùng em dash", "—" not in _loi)

# ============================================================
# 3. Object vẫn còn nguyên cho MÁY đọc
# ============================================================
# Bỏ luôn object là mất dữ liệu trace và làm hỏng các chỗ kiểm hợp đồng.
_oc = cc.ContextCompiler._output_contract("dashboard")
check("object hợp đồng vẫn còn", isinstance(_oc, dict))
for _k in ("type", "language", "channel", "must_report_missing_evidence", "no_false_action_claim"):
    check(f"giữ nguyên trường '{_k}'", _k in _oc)
check("capsule vẫn mang object ra ngoài", "output_contract: dict" in _SRC)

# ============================================================
# 4. Core Contract không được trỏ tới một cái tên không còn nữa
# ============================================================
# Câu "Trả lời đúng output contract" nay trỏ vào hư không vì không còn khối nào tên vậy -
# model đi tìm một thứ không có là mở đường cho nó tự bịa ra.
check("CANARY: Core Contract không còn trỏ tới 'output contract'",
      "output contract" not in cc.CORE_CONTRACT.casefold())
check("mà trỏ đúng vào phần Cách trả lời", "Cách trả lời" in cc.CORE_CONTRACT)
check("và phần đó có thật trong lời dặn", "Cách trả lời" in _loi)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_capsule_khong_ra_json: tất cả pass")
