"""Javis phải biết BÂY GIỜ MẤY GIỜ trên mọi đường, kể cả đường tắt không phát tool.

    python tests/run.py dong_ho

Lỗi thật chủ repo chụp lại: hỏi "giờ Việt Nam là mấy giờ" thì Javis trả lời "MCP server của
Javis hiện đang mất kết nối... khi nào kết nối lại em sẽ gọi tool javis_now". Không có server
nào mất kết nối cả. Sự thật là lượt đó đi ĐƯỜNG TẮT của mức Siêu tiết kiệm, mà đường tắt gửi
capsule KHÔNG KÈM TOOL NÀO - đó chính là chỗ nó tiết kiệm. Model không có đồng hồ, không có
tool, nên nó làm cái tệ nhất: bịa ra một lý do nghe hợp lý.

Bộ lọc câu hỏi CÓ chặn "bây giờ", "hôm nay"... nhưng chặn theo từ khoá là trò đuổi bắt, và
"giờ Việt Nam là mấy giờ" lọt qua đúng như vậy. Nên chữa ở gốc: mọi prompt Javis gửi đi đều
mang theo một dòng giờ thật. Khoảng 30 token, đổi lấy việc không còn cửa nào để bịa.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-dongho-")

import context_compiler as cc  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. Dòng giờ nói đúng thứ nó phải nói ----
_moc = datetime(2026, 8, 3, 21, 34, tzinfo=timezone(timedelta(hours=7)))   # thứ Hai
_d = cc.dong_ho(_moc)
check("có giờ và phút", "21:34" in _d)
check("có thứ trong tuần bằng tiếng Việt", "Thứ Hai" in _d)
check("có ngày tháng năm kiểu Việt Nam", "03/08/2026" in _d)
check("nói rõ múi giờ", "UTC+7" in _d)
check("và nêu tên múi giờ đang cấu hình", "Asia/Ho_Chi_Minh" in _d)
check("không dùng em dash", "—" not in _d)
# Nói thẳng là không cần gọi tool, nếu không model vẫn đi tìm tool rồi báo không có.
check("nói rõ khỏi cần gọi tool", "không cần gọi tool" in _d)

# Múi giờ là UTC+7 CỐ ĐỊNH, không đọc múi giờ của máy chủ - VPS thường chạy UTC.
_utc = datetime(2026, 8, 3, 14, 34, tzinfo=timezone.utc).astimezone(
    timezone(timedelta(hours=7)))
check("14:34 UTC là 21:34 giờ Việt Nam", "21:34" in cc.dong_ho(_utc))

# Không ghim thì phải là giờ THẬT lúc chạy, không phải một hằng số ai đó quên thay.
_that = cc.dong_ho()
_hom_nay = datetime.now(timezone(timedelta(hours=7)))
check("không ghim thì lấy đúng ngày đang chạy",
      _hom_nay.strftime("%d/%m/%Y") in _that)
check("và đúng giờ đang chạy", _hom_nay.strftime("%H:%M") in _that
      or (_hom_nay + timedelta(minutes=1)).strftime("%H:%M") in _that)

# ---- 2. Capsule của ĐƯỜNG TẮT phải mang theo giờ. Đây là chỗ lỗi thật nằm ----
from capability_registry import CapabilityRegistry  # noqa: E402

_reg_dir = tempfile.mkdtemp(prefix="javis-dongho-reg-")
_reg = CapabilityRegistry(_reg_dir)
_reg.refresh_tools("brain-a", [], {})
_reg.refresh_model_profile("groq", "model-a", "api", True, {"observed": True})
_req = cc.CompileRequest(task_id="t1", step_id="s1", objective="giờ Việt Nam là mấy giờ",
                         brain="brain-a", channel="dashboard", provider="groq",
                         model="model-a", model_kind="api")
_kq = cc.ContextCompiler(_reg).compile_shadow(_req, {"selected": []})
check("biên soạn được capsule", _kq.status == "compiled")
check("capsule đi đường tắt", _kq.capsule.path == "fast")
_sys = _kq.capsule.rendered_request["messages"][0]["content"]
# Nhãn múi giờ nay đọc từ cấu hình (vd "Asia/Ho_Chi_Minh (UTC+7)") thay vì ghim "Việt Nam":
# người dùng đổi múi giờ mà Javis vẫn khai giờ Việt Nam là sai một cách rất khó ngờ, vì
# con số giờ thì đã đúng. Test bám vào ĐỘ LỆCH, thứ luôn có mặt.
check("CANARY: capsule đường tắt CÓ mang theo giờ", "UTC+7" in _sys)
check("giờ là món BẮT BUỘC, có tên riêng trong sổ nguồn",
      "time" in (_kq.capsule.source_map or {}))
# Đường tắt không phát tool - đúng thiết kế. Chính vì vậy giờ mới phải nằm sẵn trong capsule.
check("và đúng là không có tool nào để mà gọi", _kq.capsule.capabilities == ())

# ---- 3. Đường ĐẦY ĐỦ cũng phải có, nếu không thì bật/tắt tiết kiệm lại ra hai hành vi ----
_full = main.build_system_prompt("brain")
check("prompt đầy đủ cũng mang theo giờ", "UTC+7" in _full)
check("có tiêu đề dễ thấy cho khối đó", "BÂY GIỜ" in _full)

# ---- 4. Bảng ước tính phải ĐẾM cả dòng giờ ----
# Không đếm thì trang khoe một con số tiết kiệm cao hơn thực tế. Nhỏ thôi, nhưng đây đúng là
# kiểu sai số âm thầm mà cả trang này sinh ra để chống.
_goc_dong_ho = cc.dong_ho
try:
    _truoc = asyncio.run(main._uoc_tinh_tiet_kiem("brain"))
    # `lang` thêm vào khi đồng hồ nói được nhiều thứ tiếng; stub phải nhận nó,
    # không thì lời gọi thật ném TypeError và test đo nhầm sang nhánh lỗi.
    cc.dong_ho = lambda now=None, lang="": "X" * 30000
    _sau = asyncio.run(main._uoc_tinh_tiet_kiem("brain"))
finally:
    cc.dong_ho = _goc_dong_ho
_t = ((_truoc.get("muc") or {}).get("max") or {}).get("token_moi_request")
_s = ((_sau.get("muc") or {}).get("max") or {}).get("token_moi_request")
check("ước tính có đo được viên capsule", isinstance(_t, int) and _t > 0)
check("CANARY: dòng giờ được tính vào capsule khi ước tính",
      isinstance(_s, int) and _s > _t + 9000)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_dong_ho: tất cả pass")
