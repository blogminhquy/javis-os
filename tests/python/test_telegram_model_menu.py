"""Menu /model trên Telegram phải phủ ĐỦ nhà cung cấp mà app có, không phải một bảng chép tay.

    python tests/run.py telegram_model_menu      (KHÔNG mạng)

Chủ repo báo 2026-08-13: "ở telegram anh cũng muốn chuyển được các model của antigravity".

Gốc: `_TG_PROVIDERS` là một danh sách chép tay 5 dòng, viết hồi app mới có 5 nhà cung cấp. App
lên 10 nhà thì Telegram vẫn 5, nên bộ não Antigravity - đường Google còn sống cho tài khoản cá
nhân, và là thứ chủ repo đang dùng - không đổi model được từ điện thoại, mà cũng chẳng có câu
nào nói vì sao. Đúng kiểu hỏng của mọi bảng chép tay: nó không sai lúc viết, nó sai dần.

Hai thứ test này canh:
1. Danh sách nhà cung cấp của Telegram lấy từ `PROVIDER_DEFS` (một nguồn sự thật), nên thêm
   nhà mới vào app là Telegram tự có. Kèm canary riêng cho `antigravity-cli`.
2. `/model <tên>` chốt nhà cung cấp bằng DANH SÁCH THẬT chứ không đoán theo hình dạng tên. Luật
   đoán cũ ("có dấu / là OpenRouter, còn lại là Claude") gán tên model Antigravity thành model
   Claude một cách im lặng, và lượt chat sau mới báo lỗi.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-tgmodel-"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name
          + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def chay(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ============================================================
# 1. Danh sách nhà cung cấp: một nguồn sự thật
# ============================================================
_ids_tg = [pid for pid, _ in main._tg_providers()]
_ids_app = [p["id"] for p in main.PROVIDER_DEFS]
check("CANARY: Telegram thấy ĐỦ nhà cung cấp app có (không phải bảng chép tay)",
      _ids_tg == _ids_app, f"tg={_ids_tg} app={_ids_app}")
check("CANARY: có Antigravity CLI trong menu Telegram", "antigravity-cli" in _ids_tg)
check("và mọi nhà đều có nhãn NGẮN, không lòi id thô ra nút bấm",
      all(main._tg_prov_label(p) != p and len(main._tg_prov_label(p)) <= 20 for p in _ids_tg),
      {p: main._tg_prov_label(p) for p in _ids_tg})
check("nhãn dài của dashboard bị cắt gọn cho vừa nút",
      main._tg_prov_label("antigravity-cli") == "Antigravity"
      and "(" not in main._tg_prov_label("gemini-cli"),
      main._tg_prov_label("gemini-cli"))


# ============================================================
# 2. Bàn phím chọn nhà cung cấp
# ============================================================
_GIA = {
    "anthropic-cli": ["opus", "sonnet"],
    "antigravity-cli": ["gemini-3-flash-high", "claude-sonnet-4-6"],
    "gemini-cli": [],          # cài rồi nhưng chưa đăng nhập -> không liệt kê nổi model nào
}


async def _models_gia(pid):
    ids = _GIA.get(pid, [])
    main._TG_MODEL_LISTS[pid] = ids
    return ids


_that_models_for = main._tg_models_for
_that_read = main.cfgmod.read_settings
main._tg_models_for = _models_gia
main.cfgmod.read_settings = lambda: {"model": {"main": {"provider": "antigravity-cli",
                                                        "model": "gemini-3-flash-high"}}}
try:
    _kb = chay(main._model_provider_kb())
finally:
    main._tg_models_for = _that_models_for
    main.cfgmod.read_settings = _that_read

_nut = [b["callback_data"] for hang in _kb["inline_keyboard"] for b in hang]
check("CANARY: Antigravity có nút riêng trong bàn phím /model", "mp:antigravity-cli" in _nut, _nut)
check("nhà đang dùng được đánh dấu ✓",
      any("✓" in b["text"] and b["callback_data"] == "mp:antigravity-cli"
          for hang in _kb["inline_keyboard"] for b in hang),
      [b["text"] for hang in _kb["inline_keyboard"] for b in hang])
check("CANARY: nhà không liệt kê nổi model nào thì ẩn (bấm vào chỉ ra trang trống)",
      "mp:gemini-cli" not in _nut, _nut)
check("nhưng vẫn còn nút Đóng", "mx" in _nut)


# ============================================================
# 3. `/model <tên>`: chốt theo DANH SÁCH THẬT, không đoán theo hình dạng tên
# ============================================================
main._TG_MODEL_LISTS.clear()
main._TG_MODEL_LISTS.update({
    "anthropic-cli": ["opus", "sonnet", "claude-sonnet-4-6"],
    "antigravity-cli": ["gemini-3-flash-high", "claude-sonnet-4-6"],
})
_m_cfg = {}   # chưa có API key nào -> chỉ hai nhà CLI ở trên là dùng được


def _voi_nha_dang_dung(pid, model=""):
    main.cfgmod.read_settings = lambda: {"model": {"main": {"provider": pid, "model": model}}}


try:
    _voi_nha_dang_dung("anthropic-cli", "opus")
    _pid, _uv = chay(main._tg_provider_cho_model("gemini-3-flash-high", _m_cfg))
    check("CANARY: tên model của Antigravity KHÔNG còn bị gán nhầm sang Claude",
          _pid == "antigravity-cli", (_pid, _uv))

    _voi_nha_dang_dung("openrouter", "x/y")   # nhà đang dùng KHÔNG nằm trong ứng viên
    _pid2, _uv2 = chay(main._tg_provider_cho_model("claude-sonnet-4-6", _m_cfg))
    check("CANARY: tên có ở nhiều nhà mà không nhà nào đang dùng -> KHÔNG đoán, hỏi lại",
          _pid2 is None and set(_uv2) == {"anthropic-cli", "antigravity-cli"}, (_pid2, _uv2))

    _voi_nha_dang_dung("antigravity-cli", "gemini-3-flash-high")
    _pid3, _uv3 = chay(main._tg_provider_cho_model("claude-sonnet-4-6", _m_cfg))
    check("nhà ĐANG DÙNG thắng khi nó cũng có tên đó (đổi model trong cùng một nhà)",
          _pid3 == "antigravity-cli", (_pid3, _uv3))

    _pid4, _uv4 = chay(main._tg_provider_cho_model("ten-la-hoac-moi-tinh", _m_cfg))
    check("tên không nhà nào khai -> trả None để nhánh đoán cũ còn cơ hội",
          _pid4 is None and _uv4 == [], (_pid4, _uv4))
finally:
    main.cfgmod.read_settings = _that_read

_src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("CANARY: nhánh /model hỏi danh sách thật TRƯỚC mấy luật đoán",
      _src.index("_tg_provider_cho_model(a, m)") < _src.index('if "/" in a:'), "")

print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test telegram_model_menu đã qua.")
