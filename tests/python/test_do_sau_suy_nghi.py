"""Thang độ sâu suy nghĩ (effort) - nhiều nấc nhưng KHÔNG gửi giá trị lạ lên API.

    python tests/python/test_do_sau_suy_nghi.py

Không cần pytest, không chạm mạng.

Chủ repo (2026-07-31): "phần Effort đang thiếu nhiều cấp độ". Javis vốn chỉ có off/low/medium/
high, trong khi Claude Code cho tới Ultra. Đã thêm hai nấc xhigh + ultra.

Chỗ NGUY HIỂM khi thêm nấc: giá trị này được nhét thẳng vào payload của nhà cung cấp. API chỉ
nhận low|medium|high; gửi "ultra" là ăn 400 và hỏng CẢ LƯỢT CHAT. Nên phải có một cửa ải dịch
mức Javis sang giá trị API an toàn, và mọi chỗ gửi đều phải đi qua nó.

Chỗ dễ quên thứ hai: đường LƯU và đường ĐỌC có hai whitelist RIÊNG. Sửa một bên thì giao diện
cho chọn nấc mới mà server lặng lẽ hạ về "off" (đúng lỗi đã đo được trong trình duyệt).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import re
import sys

import engine

loi = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten + (("  [" + str(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        loi.append(ten)


# ---- 1. Thang nấc ----
check("có 6 nấc, đúng thứ tự nhẹ -> nặng",
      engine.REASONING_LEVELS == ("off", "low", "medium", "high", "xhigh", "ultra"),
      engine.REASONING_LEVELS)

# ---- 2. Không bao giờ gửi giá trị lạ lên API ----
HOP_LE = {"low", "medium", "high"}
for r in engine.REASONING_LEVELS:
    check("nấc " + r + " -> effort API hợp lệ", engine.api_effort(r) in HOP_LE, engine.api_effort(r))
check("CANARY: nấc 'ultra' quy về 'high' khi gửi API", engine.api_effort("ultra") == "high")
check("CANARY: nấc 'xhigh' quy về 'high' khi gửi API", engine.api_effort("xhigh") == "high")
check("giá trị rác cũng ra effort hợp lệ", engine.api_effort("bay-ba") in HOP_LE)
check("None cũng ra effort hợp lệ", engine.api_effort(None) in HOP_LE)
check("ba nấc dưới giữ nguyên nghĩa",
      (engine.api_effort("low"), engine.api_effort("medium"), engine.api_effort("high"))
      == ("low", "medium", "high"))

# ---- 3. MỌI chỗ nhét effort vào payload phải đi qua api_effort ----
# Đây là canary quan trọng nhất: thêm một chỗ gửi thẳng `reasoning` là lại 400 trên nấc mới.
SRC = (ROOT / "server" / "engine.py").read_text(encoding="utf-8")
tho = re.findall(r'\["reasoning(?:_effort)?"\]\s*=\s*reasoning\b', SRC)
check("CANARY: không còn chỗ nào gửi thẳng biến reasoning lên API", not tho, tho)
tho2 = re.findall(r'\{"effort":\s*reasoning\}', SRC)
check("CANARY: không còn {\"effort\": reasoning} thô", not tho2, tho2)
check("có ít nhất 6 chỗ đã đi qua api_effort",
      len(re.findall(r"api_effort\(reasoning\)", SRC)) >= 6,
      len(re.findall(r"api_effort\(reasoning\)", SRC)))

# ---- 4. Anthropic: nấc trên phải khác nhau THẬT ở model cũ (budget token) ----
budget = {}
for r in engine.REASONING_LEVELS[1:]:
    budget[r] = engine._anthropic_reasoning("claude-haiku-4-5", r)["thinking"]["budget_tokens"]
check("budget token tăng dần theo nấc",
      list(budget.values()) == sorted(budget.values()) and len(set(budget.values())) == 5, budget)
check("CANARY: xhigh và ultra KHÔNG cùng budget (nếu bằng nhau thì nấc mới chỉ là nhãn suông)",
      budget["xhigh"] != budget["ultra"], budget)
# Anthropic có thang RIÊNG và rộng hơn: Messages API nhận đủ low|medium|high|xhigh|max. Dùng
# chung `api_effort` (bảng cho các nhà kiểu OpenAI) là bóp ba nấc trên cùng của Javis thành
# "high" - người dùng bấm "Tối đa" mà không có gì đổi, không lỗi, không dấu hiệu nào.
HOP_LE_ANT = {"low", "medium", "high", "xhigh", "max"}
_eff = lambda m, r: engine._anthropic_reasoning(m, r)["output_config"]["effort"]  # noqa: E731
for _m in ("claude-opus-4-8", "claude-opus-5", "claude-sonnet-5", "claude-fable-5-1",
           "claude-sonnet-4-6", "claude-opus-4-5"):
    for _r in engine.REASONING_LEVELS[1:]:
        check(f"{_m} nấc {_r} -> effort Anthropic hợp lệ", _eff(_m, _r) in HOP_LE_ANT,
              _eff(_m, _r))
check("CANARY: không bao giờ gửi tên nấc RIÊNG của Javis ('ultra') lên Anthropic",
      all(_eff(m, "ultra") != "ultra" for m in ("claude-opus-5", "claude-sonnet-4-6")))
check("CANARY: model đời mới thì xhigh và ultra khác 'high' THẬT, không phải nhãn suông",
      (_eff("claude-opus-5", "xhigh"), _eff("claude-opus-5", "ultra")) == ("xhigh", "max"))
check("model 4.6 chưa có 'xhigh' thì hạ về 'high', nhưng 'max' thì vẫn có",
      (_eff("claude-sonnet-4-6", "xhigh"), _eff("claude-sonnet-4-6", "ultra")) == ("high", "max"))
check("Opus 4.5 chỉ có ba nấc nên hai nấc trên cùng đều về 'high'",
      (_eff("claude-opus-4-5", "xhigh"), _eff("claude-opus-4-5", "ultra")) == ("high", "high"))
check("nấc off -> không gửi thinking gì cả",
      engine._anthropic_reasoning("claude-opus-4-8", "off") == {})

# ---- 5. Đường LƯU và đường ĐỌC phải soi CÙNG nguồn ----
MAIN = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("CANARY: đường lưu dùng engine.REASONING_LEVELS",
      re.search(r'm\["reasoning"\]\s*=\s*r if r in engine\.REASONING_LEVELS', MAIN) is not None)
check("CANARY: đường đọc dùng engine.REASONING_LEVELS",
      re.search(r'return r if r in engine\.REASONING_LEVELS', MAIN) is not None)
check("không còn whitelist chép tay ('off','low','medium','high')",
      '("off", "low", "medium", "high")' not in MAIN)

# ---- 6. Claude Code CLI: mỗi nấc có từ khoá, leo thang đúng ----
import main as srv

kw = {r: srv._CLI_THINK_KW.get(r) for r in engine.REASONING_LEVELS[1:]}
check("mọi nấc bật đều có từ khoá cho Claude Code", all(kw.values()), kw)
check("từ khoá leo thang think -> ultrathink",
      kw["low"] == "think" and kw["high"] == "think harder" and kw["ultra"] == "ultrathink", kw)
check("nấc off giữ nguyên câu hỏi, không chèn gì", srv._cli_think("off", "xin chào") == "xin chào")
check("nấc bật thì có chèn gợi ý", "ultrathink" in srv._cli_think("ultra", "xin chào"))

# ---- 6b. Claude Code CLI: đi bằng CỜ `--effort`, từ khoá chỉ là đường dự phòng ----
# Bảng từ khoá ở trên cho "xhigh" và "ultra" CÙNG một chữ `ultrathink`, tức "Rất cao" và
# "Tối đa" y hệt nhau - hai nấc mà một nghĩa. Cờ `--effort` của Claude Code thì trùng khít
# thang của Javis (low|medium|high|xhigh|max) nên chọn nấc nào ra nấc đó.
check("CANARY: bảng từ khoá cũ ĐÚNG LÀ có hai nấc trùng nhau (lý do phải đổi sang cờ)",
      srv._CLI_THINK_KW["xhigh"] == srv._CLI_THINK_KW["ultra"])
check("bảng cờ effort phủ đủ mọi nấc bật",
      all(srv._CLI_EFFORT.get(r) for r in engine.REASONING_LEVELS[1:]), srv._CLI_EFFORT)
check("CANARY: sang cờ thì hai nấc trên cùng KHÁC nhau thật",
      srv._CLI_EFFORT["xhigh"] != srv._CLI_EFFORT["ultra"])
check("nấc trên cùng của Javis ('ultra') dịch sang tên của Claude Code ('max')",
      srv._CLI_EFFORT["ultra"] == "max")
check("CANARY: không gửi tên nấc riêng của Javis cho CLI",
      "ultra" not in set(srv._CLI_EFFORT.values()))

_HOP_LE_CLI = {"low", "medium", "high", "xhigh", "max"}
check("mọi giá trị gửi cho `claude --effort` đều nằm trong thang CLI nhận",
      set(srv._CLI_EFFORT.values()) <= _HOP_LE_CLI, srv._CLI_EFFORT)


class _EngineGia:
    def __init__(self):
        self.effort = None


_cu_co_co = srv.claude_cli.co_co
try:
    # CLI đời mới: đặt cờ, và prompt phải giữ NGUYÊN VĂN. Cộng dồn cả hai đường là vừa tốn
    # token vừa đẩy model lên một mức khác mức người dùng chọn.
    srv.claude_cli.co_co = lambda co: True
    _e = _EngineGia()
    _msg = srv._cli_do_sau(_e, "ultra", "xin chào")
    check("CLI có --effort: đặt đúng mức", _e.effort == "max", _e.effort)
    check("CLI có --effort: KHÔNG chèn từ khoá vào prompt nữa", _msg == "xin chào", _msg)
    _e2 = _EngineGia()
    check("nấc off thì không đặt effort gì cả",
          srv._cli_do_sau(_e2, "off", "xin chào") == "xin chào" and _e2.effort is None)

    # CLI đời cũ: không được truyền cờ lạ (CLI thoát ngay với "unknown option", hỏng cả lượt),
    # nên rơi về từ khoá như trước - mất độ chính xác chứ không mất tính năng.
    srv.claude_cli.co_co = lambda co: False
    _e3 = _EngineGia()
    _msg3 = srv._cli_do_sau(_e3, "ultra", "xin chào")
    check("CANARY: CLI cũ thì KHÔNG đặt cờ", _e3.effort is None)
    check("CLI cũ vẫn còn đường dự phòng bằng từ khoá", "ultrathink" in _msg3)
finally:
    srv.claude_cli.co_co = _cu_co_co

# ---- 6c. Codex / Grok Build / Antigravity: cần gạt thật, và KHÔNG dùng từ khoá của Claude ----
# Ba engine này trước đây nhận độ sâu suy nghĩ bằng đúng bảng từ khoá của Claude Code, tức là
# Javis dán chữ "ultrathink" vào cuối câu hỏi của người dùng rồi gửi cho Grok hay Gemini - một
# chữ chúng không hiểu. Không lỗi, không dấu hiệu, chỉ là không có tác dụng gì.
import antigravity_cli  # noqa: E402
import codex_models  # noqa: E402
import grok_cli  # noqa: E402


class _EngineGia2:
    def __init__(self, model=""):
        self.effort = None
        self.extra_config = []
        self.model = model


# --- Codex: mức lấy từ thang chính Codex khai cho model đó ---
codex_models._EFFORTS["gpt-5.5-gia"] = ["minimal", "low", "medium", "high", "xhigh"]
codex_models._EFFORTS["hep-gia"] = ["low", "high"]
_c1 = _EngineGia2("gpt-5.5-gia")
check("Codex: đặt -c model_reasoning_effort theo mức đã chọn",
      srv._codex_do_sau(_c1, "medium", "hỏi") == "hỏi"
      and _c1.extra_config == ["model_reasoning_effort=medium"], _c1.extra_config)
_c2 = _EngineGia2("gpt-5.5-gia")
srv._codex_do_sau(_c2, "ultra", "hỏi")
check("CANARY: nấc trên cùng ra nấc CAO NHẤT model có, không phải 'ultra'",
      _c2.extra_config == ["model_reasoning_effort=xhigh"], _c2.extra_config)
_c3 = _EngineGia2("hep-gia")
srv._codex_do_sau(_c3, "medium", "hỏi")
check("model thang hẹp thì LÙI xuống nấc thấp hơn, không tự tiến lên",
      _c3.extra_config == ["model_reasoning_effort=low"], _c3.extra_config)
check("CANARY: mọi mức gửi cho Codex đều nằm trong thang model tự khai",
      all(codex_models.muc_cho("hep-gia", r) in ("", "low", "high")
          for r in engine.REASONING_LEVELS))
_c4 = _EngineGia2("chua-hoi-bao-gio")
_m4 = srv._codex_do_sau(_c4, "ultra", "hỏi")
check("chưa biết thang của model thì KHÔNG truyền gì, rơi về câu nhắc",
      _c4.extra_config == [] and _m4 != "hỏi", _c4.extra_config)
_c5 = _EngineGia2("gpt-5.5-gia")
check("nấc off thì không đặt gì cả",
      srv._codex_do_sau(_c5, "off", "hỏi") == "hỏi" and _c5.extra_config == [])

# --- Grok Build / Antigravity: chỉ truyền cờ khi CHÍNH --help khai cả cờ lẫn giá trị ---
_HELP_CO = "Usage: x\n  --effort <level>   low, medium, high, xhigh\n  --model <m>\n"
_HELP_KHONG = "Usage: x\n  --model <m>\n"
grok_cli.find_grok_cli = lambda: "gia"
antigravity_cli.find_antigravity_cli = lambda: "gia"
import time as _t  # noqa: E402

for _mod, _ten in ((grok_cli, "Grok"), (antigravity_cli, "Antigravity")):
    _mod._HELP_CACHE.update(path="gia", text=_HELP_CO, ts=_t.time())
    _e = _EngineGia2()
    check(f"{_ten}: CLI khai cờ thì đặt cờ, prompt giữ nguyên văn",
          srv._cli_do_sau_khac(_e, _mod, "xhigh", "hỏi") == "hỏi" and _e.effort == "xhigh",
          _e.effort)
    _e2 = _EngineGia2()
    srv._cli_do_sau_khac(_e2, _mod, "ultra", "hỏi")
    check(f"CANARY: {_ten} nấc trên cùng LÙI xuống nấc CLI có, không rơi thẳng về prompt",
          _e2.effort == "xhigh", _e2.effort)
    _e3 = _EngineGia2()
    check(f"{_ten}: nấc off không đặt gì",
          srv._cli_do_sau_khac(_e3, _mod, "off", "hỏi") == "hỏi" and _e3.effort is None)
    # CLI không khai cờ: KHÔNG được đoán bừa một giá trị rồi làm hỏng cả lượt chat.
    _mod._HELP_CACHE.update(path="gia", text=_HELP_KHONG, ts=_t.time())
    _e4 = _EngineGia2()
    _m4b = srv._cli_do_sau_khac(_e4, _mod, "ultra", "hỏi")
    check(f"CANARY: {_ten} CLI không khai cờ thì KHÔNG truyền gì", _e4.effort is None)
    check(f"{_ten}: rơi về câu nhắc, và câu đó KHÔNG chứa từ khoá của Claude Code",
          _m4b != "hỏi" and "ultrathink" not in _m4b and "think hard" not in _m4b, _m4b)
    check(f"{_ten}: cờ lạ giá trị không khai cũng không truyền", _mod.co_effort("max") == [])

check("mọi nấc bật đều có câu nhắc trung tính",
      all(srv._GOI_SUY_NGHI.get(r) for r in engine.REASONING_LEVELS[1:]), srv._GOI_SUY_NGHI)
check("CANARY: câu nhắc trung tính không mượn từ khoá của Claude Code",
      not any(k in " ".join(srv._GOI_SUY_NGHI.values())
              for k in srv._CLI_THINK_KW.values()), srv._GOI_SUY_NGHI)
check("nấc off không có câu nhắc", srv._nhac_suy_nghi("off", "hỏi") == "hỏi")

# Bảng từ khoá của Claude Code chỉ được gọi TỪ TRONG `_cli_do_sau` (đường lui của chính
# Claude Code). Gọi nó ở bất cứ đâu khác nghĩa là lại có engine ăn nhầm từ khoá của nhà khác.
_SRC_MAIN = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
_than = _SRC_MAIN.split("def _cli_do_sau(", 1)[1].split("\ndef ", 1)[0]
_goi_tat_ca = len(re.findall(r"(?<!def )_cli_think\(", _SRC_MAIN))
check("CANARY: chỉ đường lui của Claude Code còn gọi bảng từ khoá đó",
      _goi_tat_ca > 0 and _goi_tat_ca == _than.count("_cli_think("),
      (_goi_tat_ca, _than.count("_cli_think(")))


# ---- 7. Lọc giá trị ----
check("giá trị lạ bị hạ về off", srv._reasoning_level({"reasoning": "bay-ba"}) == "off")
check("nấc mới KHÔNG bị hạ về off", srv._reasoning_level({"reasoning": "ultra"}) == "ultra")
check("thiếu config -> off", srv._reasoning_level({}) == "off")
check("config None -> off", srv._reasoning_level(None) == "off")

# ---- 8. Giao diện phải khớp server ----
for f, ten in ((ROOT / "dashboard" / "model-picker.js", "thanh chat"),
               (ROOT / "dashboard" / "console.js", "trang Models")):
    txt = f.read_text(encoding="utf-8")
    thieu = [r for r in engine.REASONING_LEVELS if '"%s"' % r not in txt]
    check("%s có đủ mọi nấc của server" % ten, not thieu, thieu)

if loi:
    print("\nFAIL - test_do_sau_suy_nghi: %d lỗi: %s" % (len(loi), ", ".join(loi)))
    sys.exit(1)
print("\nOK - test_do_sau_suy_nghi: tất cả pass")
