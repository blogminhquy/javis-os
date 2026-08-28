"""Gỡ một provider thì cấu hình CŨ của người dùng phải được nắn lại, không được hỏng câm.

    python tests/run.py provider_da_go       (KHÔNG mạng)

Vì sao có file này. Bản 0.50.0 gỡ hẳn engine Gemini CLI. Ai đang ĐẶT NÓ làm model chính thì
sau khi cập nhật, `settings.json` của họ vẫn ghi `model.main.provider = "gemini-cli"` - một
provider không còn tồn tại. Đo trên máy trước khi vá, chuỗi hỏng đúng như sau:

  1. `_provider_def("gemini-cli")` trả None.
  2. Trang Models KHÔNG thẻ nào mang nhãn MAIN - người dùng mở ra không hiểu mình đang dùng gì.
  3. `_chat_provider` rơi về `kind="cli"` mặc định, tức lượt chat chạy bằng CLAUDE CODE, nhưng
     mang theo `model="gemini-2.5-pro"` - tên model của nhà khác.

Không có câu lỗi nào ở cả ba bước. Đây đúng là hạng hỏng câm mà repo này canh khắp nơi, chỉ
khác là nó nằm ở đường DI TRÚ chứ không ở đường chạy - nên không test nào cũ bắt được.

Hai lớp đỡ, và test này canh cả hai vì chúng đỡ hai ca khác nhau:

  - `config._nan_provider_da_go` nắn lúc ĐỌC settings. Phủ được `aux_engine`, thứ đọc thẳng
    settings chứ không đi qua `main`.
  - `main._effective_main` tự kiểm provider còn trong `PROVIDER_DEFS` không. Phủ được cfg do
    nơi khác DỰNG TAY (bot chuyên trách, test, người sửa file), không đi qua `read_settings`.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-dago-test-")

import config as cfgmod   # noqa: E402
import main               # noqa: E402
import aux_engine         # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name
          + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


_GO = "gemini-cli"      # provider đã gỡ ở 0.50.0

check("bảng provider đã gỡ có khai nó", _GO in cfgmod._PROVIDER_DA_GO)
check("CANARY: và nó THẬT SỰ không còn trong PROVIDER_DEFS "
      "(bảng kia mà kể tên một provider vẫn sống là nắn nhầm)",
      main._provider_def(_GO) is None)


# ============================================================
# 1. Lớp một: nắn lúc đọc settings
# ============================================================
_cfg = cfgmod.read_settings()
_cfg["model"]["main"] = {"provider": _GO, "model": "gemini-2.5-pro"}
_cfg["model"]["engine"] = _GO
_cfg["model"]["auxiliary"] = {"provider": _GO, "model": "gemini-2.5-flash"}
cfgmod.write_settings(_cfg)

_lai = cfgmod.read_settings()
check("model chính trỏ vào provider đã gỡ -> nắn về rỗng",
      (_lai["model"]["main"] or {}).get("provider") in ("", None), _lai["model"]["main"])
check("CANARY: trường legacy `engine` cũng phải nắn - bỏ sót nó là `_effective_main` "
      "suy ngược ra đúng provider vừa gỡ",
      _lai["model"].get("engine") != _GO, _lai["model"].get("engine"))
check("model việc nền cũng nắn",
      (_lai["model"]["auxiliary"] or {}).get("provider") in ("", None),
      _lai["model"]["auxiliary"])

_em = main._effective_main(_lai)
check("model chính hiệu lực về mặc định của app, không phải provider đã gỡ",
      _em["provider"] == "anthropic-cli", _em)
_prov, _kind, _key, _model = main._chat_provider(_lai["model"])
check("lượt chat chạy bằng đúng engine mặc định", _prov == "anthropic-cli", _prov)
check("CANARY: và KHÔNG mang theo model của nhà đã gỡ "
      "(đưa 'gemini-2.5-pro' cho Claude Code là hỏng câm)",
      _model != "gemini-2.5-pro", _model)

_view = main._providers_view(_lai)
_main_ids = [p["id"] for p in _view if p["is_main"]]
check("CANARY: trang Models có ĐÚNG MỘT thẻ mang nhãn MAIN "
      "(trước khi vá là KHÔNG thẻ nào, người dùng mở ra không biết đang dùng gì)",
      len(_main_ids) == 1, _main_ids)

check("model việc nền cũng về mặc định, không giữ provider đã gỡ",
      aux_engine.read_spec(_lai).get("provider") != _GO, aux_engine.read_spec(_lai))


# ============================================================
# 2. Lớp hai: cfg dựng TAY, không đi qua read_settings
# ============================================================
_tay = {"model": {"main": {"provider": _GO, "model": "gemini-2.5-pro"}, "engine": "cli"}}
check("cfg dựng tay vẫn được `_effective_main` đỡ",
      main._effective_main(_tay)["provider"] == "anthropic-cli", main._effective_main(_tay))
check("và `_chat_provider` theo đó",
      main._chat_provider(_tay["model"])[0] == "anthropic-cli")


# ============================================================
# 3. KHÔNG được đụng vào cấu hình hợp lệ
# ============================================================
# Hàng rào nào cũng phải chứng minh nó không bắt oan. Nắn nhầm một provider đang sống là đá
# người dùng ra khỏi bộ não họ đã chọn, im lặng - còn tệ hơn cái nó định chữa.
for _ok in ("anthropic-cli", "grok-cli", "openrouter", "groq"):
    _c = {"model": {"main": {"provider": _ok, "model": "m"}}}
    check(f"provider còn sống '{_ok}' KHÔNG bị nắn",
          main._effective_main(_c)["provider"] == _ok, main._effective_main(_c))

_c2 = cfgmod.read_settings()
_c2["model"]["main"] = {"provider": "grok-cli", "model": "grok-4.6"}
_c2["model"]["auxiliary"] = {"provider": "groq", "model": "llama-3.3-70b-versatile"}
cfgmod.write_settings(_c2)
_lai2 = cfgmod.read_settings()
check("đọc lại: cấu hình hợp lệ còn nguyên vẹn",
      (_lai2["model"]["main"] or {}).get("provider") == "grok-cli"
      and (_lai2["model"]["auxiliary"] or {}).get("provider") == "groq",
      (_lai2["model"]["main"], _lai2["model"]["auxiliary"]))


# ============================================================
# 4. Cảnh báo chỉ in MỘT lần mỗi tiến trình
# ============================================================
# `read_settings` được gọi liên tục (mỗi lượt chat, mỗi request). In mỗi lần là ngập nhật ký
# máy chủ tới mức che mất lỗi thật.
check("có cơ chế chống in lặp", isinstance(cfgmod._DA_BAO_GO, set) and len(cfgmod._DA_BAO_GO) > 0)


print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + "; ".join(_fails))
else:
    print("XANH: tất cả đều đạt")
sys.exit(1 if _fails else 0)
