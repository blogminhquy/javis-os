"""Model MỚI của nhà cung cấp phải tới được người dùng, kể cả khi máy đã chạy lâu năm.

    python tests/run.py model_moi

Lỗi thật chủ repo báo 05/09/2026: "Javis đang không có bản claude 5.1 fable, ngày trước tôi
nhớ tôi làm live tự động có các phiên bản mới nhất khi nhà cung cấp cập nhật mà giờ khi lên
phiên bản lại không được."

Ba lưới cùng thủng, và cả ba đều hỏng KIỂU IM LẶNG - trình chọn model vẫn hiện ra một danh
sách trông bình thường, chỉ là thiếu mất dòng model mới:

1. **Không còn nguồn live nào cho gói Claude Code.** Bản 0.26.17 gỡ đường mượn access token
   OAuth của Claude Code để hỏi `/v1/models` (Anthropic cấm dùng token gói Pro/Max ngoài
   Claude Code - xem `server/claude_auth.py`). Từ đó tới nay, máy không có `anthropic_api_key`
   thì danh sách kẹt ở mấy alias ghi cứng. Nay có nguồn mới KHÔNG chạm credential của ai:
   binary `claude` nhúng sẵn danh mục model của chính nó, đọc ra là biết bản CLI đang cài hiểu
   những model nào, và cập nhật Claude Code là danh sách tự mới theo.

2. **Danh sách đã nhớ ĐÈ danh sách mặc định.** `_remember_catalog` ghi bản live vào
   `settings.json`, mà `config._deep_merge` thì THAY danh sách chứ không nối. Nên kể từ lần
   ghi đầu tiên, bản mặc định mới trong `config.py` không bao giờ tới được người dùng nữa:
   nâng cấp Javis bao nhiêu lần cũng vô ích, trừ khi sửa tay `settings.json`. Nay hai danh
   sách HỢP với nhau.

3. **Dịch alias sang id thật lấy "cái đầu tiên gặp".** Alias có nghĩa là "bản mới nhất của
   dòng này", nên dịch `fable` thành một bản cũ là lặng lẽ ghim người dùng vào model cũ.

Kèm hai chỗ hỏng theo cùng một dàn model mới:
- `engine._ADAPTIVE_THINKING` sót `opus-5` và `sonnet-5`, nên bật độ sâu suy nghĩ trên hai
  model đó là gửi `budget_tokens` - tham số dòng 5 trả 400.
- Bảng giá gộp cả dòng Opus vào một mức 15$, trong khi Opus từ 4.5 đã còn 5$ và Fable thì
  10$. Sai theo cả hai chiều, và sai thẳng vào con số tiền trên trang Mức dùng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-model-moi-")

import claude_cli  # noqa: E402
import config as cfg  # noqa: E402
import engine  # noqa: E402
import main  # noqa: E402
import usage_parsers as up  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ============================================================
# 1. Đọc danh mục model từ chính binary `claude`
# ============================================================
# Không phụ thuộc máy chạy test có cài Claude Code hay không: dựng một file GIẢ mang đúng hình
# dạng dữ liệu thật (id nằm trong dấu nháy kép, lẫn giữa rác nhị phân) rồi trỏ hàm vào đó.
_gia = os.path.join(os.environ["JAVIS_STATE_DIR"], "claude-gia.bin")
with open(_gia, "wb") as _fh:
    _fh.write(b'\x00rac"claude-opus-4-1-20250805"rac"claude-fable-5"\xff'
              b'"claude-opus-5"..."claude-fable-5-1"..."claude-sonnet-5"'
              b'"claude-haiku-4-5"..."claude-haiku-4-5-20251001""claude-opus-4-8"'
              # Hai chuỗi TRÙNG KHUÔN mà không phải model - phải bị loại.
              b'"claude-code-20250219""claude-desktop-3p"\x00')

_cu = claude_cli._file_co_danh_muc
try:
    claude_cli._file_co_danh_muc = lambda: __import__("pathlib").Path(_gia)
    claude_cli._MODELS_CACHE.update(sig=None, ids=None)
    _ids = claude_cli.list_models()
finally:
    claude_cli._file_co_danh_muc = _cu

check("đọc được danh sách model từ danh mục nhúng trong CLI", bool(_ids), _ids)
check("CANARY: có Fable 5.1 - đúng model chủ repo báo thiếu", "claude-fable-5-1" in (_ids or []))
check("alias của từng dòng đứng trước id đầy đủ",
      _ids[:1] == ["fable"] and set(_ids[:4]) == {"fable", "opus", "sonnet", "haiku"}, _ids[:6])
check("CANARY: chuỗi trùng khuôn mà không phải model thì bị loại",
      "claude-code-20250219" not in _ids and "claude-desktop-3p" not in _ids)
check("CANARY: alias không đẻ từ mấy chuỗi rác đó",
      "code" not in _ids[:6] and "desktop" not in _ids[:6], _ids[:6])

_i = {m: n for n, m in enumerate(_ids)}
check("CANARY: bản mới nhất của dòng đứng trên bản cũ (5.1 trước 5)",
      _i["claude-fable-5-1"] < _i["claude-fable-5"])
check("CANARY: 4.8 đứng trên 4.1, không bị so như 4.1 > 4.8",
      _i["claude-opus-4-8"] < _i["claude-opus-4-1-20250805"])
check("bản không gắn ngày đứng trên bản gắn ngày",
      _i["claude-haiku-4-5"] < _i["claude-haiku-4-5-20251001"])

# Nhớ theo mtime: hỏi lại không quét đĩa, nhưng cập nhật Claude Code thì tự quét lại.
claude_cli._file_co_danh_muc = lambda: __import__("pathlib").Path(_gia)
try:
    check("hỏi lại trả cùng kết quả (có nhớ đệm)", claude_cli.list_models() == _ids)
finally:
    claude_cli._file_co_danh_muc = _cu

# Không cài Claude Code thì im lặng trả None để caller giữ nguyên catalog, không nổ.
claude_cli._file_co_danh_muc = lambda: None
try:
    check("không đọc được thì trả None chứ không nổ", claude_cli.list_models() is None)
finally:
    claude_cli._file_co_danh_muc = _cu
    claude_cli._MODELS_CACHE.update(sig=None, ids=None)


# ============================================================
# 2. Catalog đã nhớ KHÔNG được đè danh sách mặc định của app
# ============================================================
# Dựng lại đúng hiện trường: một máy chạy từ lâu, `settings.json` còn giữ danh sách live của
# ngày hôm đó (chưa có Fable). Trước bản này, danh sách ấy là TẤT CẢ những gì người dùng thấy.
_c = cfg.read_settings()
_c.setdefault("model", {}).setdefault("catalog", {})["claude"] = [
    "opus", "sonnet", "haiku", "claude-opus-4-1-20250805"]
_c["model"]["anthropic_api_key"] = ""
cfg.write_settings(_c)

_cu2 = main._fetch_provider_models


async def _khong_co_nguon(provider, m):
    return None                     # không API key, không đọc được CLI - lưới cuối cùng


try:
    main._fetch_provider_models = _khong_co_nguon
    main._PROV_MODELS_CACHE.clear()
    _r = asyncio.run(main.provider_models_index("anthropic-cli", refresh=True))
finally:
    main._fetch_provider_models = _cu2
    main._PROV_MODELS_CACHE.clear()

check("CANARY: danh sách nhớ từ đời nào vẫn KHÔNG che được model mới của app",
      "fable" in _r["models"] and "claude-fable-5-1" in _r["models"], _r["models"])
check("và model cũ trong danh sách nhớ thì vẫn còn, không xoá của ai cái gì",
      "claude-opus-4-1-20250805" in _r["models"])
check("không có mục nào lặp lại", len(_r["models"]) == len(set(_r["models"])))
check("gói Claude Code không bao giờ ra 0 model", len(_r["models"]) > 0)


# ============================================================
# 3. Alias phải dịch sang bản MỚI NHẤT cùng dòng
# ============================================================
_c = cfg.read_settings()
# Thứ tự cố tình xáo trộn, bản cũ đứng trước - đúng thứ một settings.json chạy lâu năm hay có.
_c["model"]["catalog"]["claude"] = [
    "fable", "opus", "claude-fable-5", "claude-opus-4-1-20250805",
    "claude-fable-5-1", "claude-opus-5"]
cfg.write_settings(_c)
check("CANARY: 'fable' ra Fable 5.1 chứ không phải bản 5 đứng trước nó trong danh sách",
      main._claude_api_model("fable") == "claude-fable-5-1",
      main._claude_api_model("fable"))
check("'opus' cũng lấy bản mới nhất", main._claude_api_model("opus") == "claude-opus-5")
check("id đầy đủ thì giữ nguyên", main._claude_api_model("claude-opus-4-8") == "claude-opus-4-8")
check("dòng không có trong catalog thì trả nguyên, không đoán tên khác",
      main._claude_api_model("haiku") == "haiku" and main._claude_api_model("") == "")


# ============================================================
# 4. Độ sâu suy nghĩ: dòng 5 dùng adaptive, không dùng budget_tokens
# ============================================================
# Gửi `budget_tokens` cho Opus 5 / Sonnet 5 là ăn 400 - hỏng cả lượt chat, mà người dùng chỉ
# thấy một lỗi chung chung. Khớp theo chuỗi con nên "claude-opus-5" không dính "opus-4-8".
for _m in ("claude-fable-5-1", "claude-opus-5", "claude-sonnet-5", "claude-opus-4-8"):
    _p = engine._anthropic_reasoning(_m, "high")
    check(f"{_m}: adaptive thinking, không có budget_tokens",
          _p.get("thinking", {}).get("type") == "adaptive" and "budget_tokens" not in str(_p),
          _p)
_p = engine._anthropic_reasoning("claude-haiku-4-5", "high")
check("CANARY: model cũ vẫn đi đường budget_tokens như trước",
      _p.get("thinking", {}).get("type") == "enabled")


# ============================================================
# 5. Bảng giá theo TỪNG BẢN, không gộp cả dòng vào một mức
# ============================================================
# Gộp là khai vống chi phí của người chạy Opus 5 lên gấp ba (15$ thay vì 5$) và khai hụt của
# người chạy Fable đi ba lần. Con số vẫn hiện ra bình thường, chỉ là sai.
_gia = up.load_prices()
check("Fable có giá riêng và ĐẮT hơn Opus 5",
      _gia["claude-fable"]["in"] > _gia["claude-opus-5"]["in"])
check("Opus 5 rẻ hơn mức 15$ của dòng Opus đời cũ",
      _gia["claude-opus-5"]["in"] < _gia["claude-opus"]["in"])
check("khớp tiền tố DÀI NHẤT nên Fable 5.1 ăn đúng mục của nó",
      up._khoa_gia("claude-fable-5-1", _gia) == "claude-fable-5-1")
check("bảng quy đổi nhanh cũng tách theo bản",
      main._gia_input_1m("claude-fable-5-1", {})[0] > main._gia_input_1m("claude-opus-5", {})[0]
      > main._gia_input_1m("claude-sonnet-5", {})[0])


# ============================================================
# 6. Ô model ở Cài đặt nạp động, không còn ba lựa chọn ghi cứng
# ============================================================
# Gán `select.value` một giá trị không có option thì trình duyệt lặng lẽ nhả về "" - tức mở
# Cài đặt rồi bấm Lưu là model đang chạy bị đổi về Mặc định mà không ai nói gì.
_app = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
_html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
check("ô model Claude ở Cài đặt hỏi server danh sách",
      "loadClaudeModels" in _app and "provider=anthropic-cli" in _app)
check("CANARY: không còn danh sách ba model ghi cứng trong HTML",
      '<option value="sonnet">' not in _html and '<option value="opus">' not in _html)
check("model đang chạy luôn có mặt trong ô, dù server không trả nó",
      "ids.indexOf(cur) < 0" in _app)


print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test model_moi đã qua.")
