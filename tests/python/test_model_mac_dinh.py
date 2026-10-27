"""Model "mặc định" phải ghi rõ là model nào (0.355.0, chủ repo 27/10: "cứ ghi mặc định sao biết được").

    python tests/run.py model_mac_dinh

Trang Models và chip model ở khung chat ghi "mặc định (tên model)" khi server biết thẻ đó chạy model gì lúc
chưa chọn riêng. Tên lấy từ ĐÚNG chỗ engine dùng khi model để trống, nên test này giữ hai thứ khớp nhau:
bảng `engine.DEFAULT_MODELS` và các giá trị dự phòng viết trong hàm engine.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-macdinh-"))

import engine  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{them}]" if not cond and them else ""))
    if not cond:
        _fails.append(name)


SRC = (SERVER / "engine.py").read_text(encoding="utf-8")

# ---- 1. bảng mặc định khớp với giá trị dự phòng của engine ----
for prov, name in engine.DEFAULT_MODELS.items():
    lit = {"groq": "GROQ_DEFAULT_MODEL", "deepseek": "DEEPSEEK_DEFAULT_MODEL"}.get(prov)
    pat = f"model or {lit}" if lit else f'model or "{name}"'
    check(f"{prov}: engine chạy đúng '{name}' khi model để trống", pat in SRC, pat)
fallbacks = set(re.findall(r'model or "([^"]+)"', SRC))
known = set(engine.DEFAULT_MODELS.values()) | {"gpt-5.5", "gpt-5-codex"}   # Codex HTTP paths, not a Models card
check("engine không có giá trị dự phòng nào nằm ngoài bảng", fallbacks <= known, str(sorted(fallbacks - known)))

# ---- 2. tên mặc định từng thẻ ----
home = Path(tempfile.mkdtemp(prefix="javis-macdinh-home-"))
os.environ["HOME"] = str(home)
for v in ("CODEX_HOME", "GROK_HOME", "CLAUDE_CONFIG_DIR"):
    os.environ.pop(v, None)
_old_read = main.cfgmod.read_settings
main.cfgmod.read_settings = lambda: {"model": {"catalog": {"openai-oauth": ["gpt-5.6-luna", "gpt-5.6"]}}}
try:
    check("Groq: tên model mặc định", main._default_model_name({}, "groq") == engine.GROQ_DEFAULT_MODEL)
    check("OpenRouter theo model đã đặt ở cài đặt cũ",
          main._default_model_name({"openrouter_model": "x/y"}, "openrouter") == "x/y")
    check("ChatGPT: model Javis truyền cho Codex khi để trống",
          main._default_model_name({}, "openai-oauth") == "gpt-5.6-luna")
    check("Claude Code: model Claude đã đặt", main._default_model_name({"claude_model": "opus"}, "anthropic-cli") == "opus")
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text(json.dumps({"model": "sonnet"}), encoding="utf-8")
    check("Claude Code: chưa đặt thì đọc settings.json của Claude", main._default_model_name({}, "anthropic-cli") == "sonnet")
    (home / ".grok").mkdir()
    (home / ".grok" / "config.toml").write_text('[models]\ndefault = "grok-5"\n', encoding="utf-8")
    check("Grok: đọc models.default trong config.toml", main._default_model_name({}, "grok-cli") == "grok-5")
    check("nhà không biết được model mặc định thì để trống (trang ghi 'mặc định' trơn)",
          main._default_model_name({}, "antigravity-cli") == "")
    view = main._routing_view({}, [{"id": "groq", "configured": True}, {"id": "antigravity-cli", "configured": True}])
    check("trang Models nhận bảng tên mặc định", view.get("defaults", {}).get("groq") == engine.GROQ_DEFAULT_MODEL
          and "antigravity-cli" not in view.get("defaults", {}))
finally:
    main.cfgmod.read_settings = _old_read

# ---- 3. giao diện ----
D = lambda f: (ROOT / "dashboard" / f).read_text(encoding="utf-8")  # noqa: E731
JS, MP = D("console.js"), D("model-picker.js")
VI, EN = json.loads(D("i18n/vi.json")), json.loads(D("i18n/en.json"))
check("trang Models ghi tên model mặc định ở chip, danh sách và thẻ việc nền",
      "MODEL_DEFAULTS = R.defaults || {};" in JS and JS.count("defName(") >= 7 and 't("models.mp_default"))' not in JS.replace(
          'MODEL_DEFAULTS[pid] }) : t("models.mp_default")', ""))
check("chip khung chat gọi tên model mặc định khi biết", "state.defaults[eff.provider]" in MP and "defText(eff.provider)" in MP)
check("thẻ gói chưa đặt model nói rõ CLI tự chọn theo gói", "PLAN_CLI.indexOf(pid) >= 0 ? t(\"models.mp_default_cli\")" in JS
      and bool(VI.get("models.mp_default_cli")) and bool(EN.get("models.mp_default_cli")))
check("có chữ 'mặc định ({m})' cả hai thứ tiếng", VI.get("models.mp_default_is") == "mặc định ({m})"
      and EN.get("models.mp_default_is") == "default ({m})")
check("gợi ý tên tài khoản là tên gói, không phải 'Gói của vợ'",
      "Gói Pro 2" in VI.get("models.pacct_label_ph", "") and "vợ" not in VI.get("models.pacct_label_ph", ""))

print()
if _fails:
    print("FAILED: " + ", ".join(_fails))
    sys.exit(1)
print("All passed")
