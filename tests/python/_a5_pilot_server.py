"""Server cho pilot A5: ĐÚNG `main.app` của checkout, chỉ bọc hàm dựng engine việc nền `main._resonance_engine` bằng sổ
lượt theo vai của pilot (`_a5_pilot_ledger.py`). Không đổi mã sản phẩm, không đổi luồng nào khác.

    python tests/python/_a5_pilot_server.py        # bộ chạy test_resonance_a5_pilot.py dựng tiến trình này

Biến môi trường (bộ chạy đặt; không có mặc định nào cho phép gọi model):
- JAVIS_A5_PILOT_MODE: `dry` hay `real`. Thiếu hay lạ thì từ chối khởi động.
- JAVIS_A5_PILOT_LEDGER: sổ lượt theo vai (JSON). BẮT BUỘC có sẵn (bộ chạy tạo một lần đầu đợt).
- JAVIS_A5_PILOT_CAPS: JSON {"maker": n, "reviewer": n}: trần của GIAI ĐOẠN này (đếm cộng dồn trong sổ); vai khác
  (bộ lập mục tiêu, mọi lời dặn hệ thống khác) luôn là 0.
- JAVIS_A5_PILOT_SCRIPT (chỉ dry): file JSON {"work": [...], "review": [...]} cho engine giả.

Kết cục mỗi lượt theo đúng luật lỗi của host (xem `_a5_pilot_ledger.Counted`); thêm lớp bọc `GoalDeps._ask` để kết luận
cuối của host (lỗi sau khi đã gọi engine) cũng hạ dòng sổ.

Lượt bị chặn (sổ đóng, hết trần): hàm dựng trả (None, lý do) mà không chạm engine thật; host coi là engine chưa dựng được
và hoàn lượt theo đường not-run của A5.

dry: hàm dựng "thật" là BẪY (chạm tới là ghi sự kiện `tripwire` và trả None); engine giả chỉ đọc kịch bản; settings dry
dùng provider không tồn tại. Không có đường nào tới engine thật.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
MODE = os.environ.get("JAVIS_A5_PILOT_MODE", "")
LEDGER = os.environ.get("JAVIS_A5_PILOT_LEDGER", "")
if MODE not in ("dry", "real") or not LEDGER or not Path(LEDGER).is_file():
    print("[a5-pilot] từ chối khởi động: thiếu JAVIS_A5_PILOT_MODE hay sổ lượt", file=sys.stderr)
    sys.exit(3)
CAPS = json.loads(os.environ.get("JAVIS_A5_PILOT_CAPS") or "{}")

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "server"))
os.chdir(str(ROOT / "server"))
import _a5_pilot_ledger as PL  # noqa: E402
import main  # noqa: E402
import resonance as R  # noqa: E402

LED = PL.RoleLedger(LEDGER, CAPS)


def role_of(system_prompt: str) -> str:
    if system_prompt == R.REVIEW_SYSTEM:
        return "reviewer"
    if system_prompt == R.SYSTEM_PROMPT:
        return "maker"
    return "other"


if MODE == "dry":
    SCRIPT = Path(os.environ.get("JAVIS_A5_PILOT_SCRIPT", ""))

    def _tripwire(system_prompt, tag="resonance"):
        LED.tripwire(role_of(system_prompt))
        return None, {"blocked": "dry_tripwire"}

    class _Fake:
        def __init__(self, role):
            self.role, self.max_wall_s = role, None

        def is_available(self):
            return True

        async def query(self, prompt):
            try:
                sc = json.loads(SCRIPT.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                sc = {}
            key = "review" if self.role == "reviewer" else "work"
            lst = sc.get(key) or []
            item = lst[0] if lst else {"error": "kịch bản dry trống"}
            if len(lst) > 1:
                sc[key] = lst[1:]
                SCRIPT.write_text(json.dumps(sc, ensure_ascii=False), encoding="utf-8")
            if isinstance(item, dict) and item.get("sleep"):
                # Ca dry hết giờ: engine treo lâu hơn trần thời gian của giai đoạn việc nền.
                await asyncio.sleep(float(item["sleep"]))
                return
            if isinstance(item, dict) and item.get("events"):
                for ev in item["events"]:
                    yield ev
                return
            if isinstance(item, dict) and item.get("error"):
                yield {"type": "error", "content": item["error"]}
                return
            yield {"type": "final", "content": item, "tokens_in": 1, "tokens_out": 1}

    def _fake_factory(system_prompt, tag="resonance"):
        if os.environ.get("JAVIS_A5_PILOT_DRY_FORCE_REAL") == "1":
            # Ca dry `tripwire`: đi đúng đường của real tới hàm dựng "thật"; ở dry hàm đó là bẫy.
            return _tripwire(system_prompt, tag)
        return _Fake(role_of(system_prompt)), {"provider": "pilot-dry", "model": "fake", "text_only": True}

    main._resonance_engine = PL.wrap_factory(_fake_factory, LED, role_of)
else:
    main._resonance_engine = PL.wrap_factory(main._resonance_engine, LED, role_of)
# Lớp thứ hai: kết luận cuối của host (`GoalDeps._ask`) cho đúng lượt vừa dựng; host báo lỗi thì dòng sổ không còn `ok`.
R.GoalDeps._ask = PL.wrap_ask(R.GoalDeps._ask, LED)

print(f"[a5-pilot] mode={MODE} caps={CAPS} sổ đã gắn", file=sys.stderr)

import uvicorn  # noqa: E402
uvicorn.run(main.app, host="127.0.0.1", port=int(os.environ.get("JAVIS_PORT", "7793")), reload=False)
