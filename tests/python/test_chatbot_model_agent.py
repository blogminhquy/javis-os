"""Chatbot chạy ĐÚNG model mà Agent của nó đã chọn.

    python tests/run.py chatbot_model_agent      (KHÔNG mạng)

Chủ repo hỏi 21/09: "anh muốn khi lựa chọn model thì ở bên chatbot sẽ mặc định model đó để chat
ra bên ngoài". Tới 0.62.2 thì không: bot chuyên trách mượn PROMPT của Agent (build_bot_prompt)
nhưng model thì luôn lấy model CHÍNH, nên chọn model cho trợ lý xong bật bot lên là nó chạy một
model khác hẳn, không có dấu hiệu nào cho thấy điều đó.

Dáng đã chốt, cùng luật rơi-về với ghim phiên web và ghim kênh Telegram:
  - Agent có chọn model  -> bot chạy đúng model đó.
  - Agent để "Mặc định"  -> bot theo model chính (không đổi gì cho người đang dùng).
  - Agent cũ chỉ lưu tên model (chưa có model_provider) -> suy nhà từ chính tên model.
  - Nhà đã gỡ / key đã xoá -> lui về model chính, KHÔNG để bot chết câm trước mặt khách.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-botmodel-"))
# Brain RIÊNG cho test: mặc định BRAINS_DIR trỏ vào `brains/` thật của repo, nên không đặt
# là test rải file agent vào brain người dùng đang xài.
os.environ.setdefault("BRAINS_DIR", tempfile.mkdtemp(prefix="javis-botbrain-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config as cfgmod  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def _mcfg(main_prov="anthropic-cli", main_model="sonnet", **keys):
    s = cfgmod.read_settings()
    s["model"]["main"] = {"provider": main_prov, "model": main_model}
    for k, v in keys.items():
        s["model"][k] = v
    cfgmod.write_settings(s)
    return cfgmod.read_settings()["model"]


# Brain thật trong STATE_DIR để _agents_dir trỏ vào một thư mục có ghi được.
BRAIN = "brain"
AG = main._agents_dir(BRAIN)
AG.mkdir(parents=True, exist_ok=True)


def _viet_agent(slug, model=None, provider=None):
    fm = ["---", "name: " + slug, "role: bán hàng"]
    if model is not None:
        fm.append("model: " + model)
    if provider is not None:
        fm.append("model_provider: " + provider)
    fm += ["---", "", "Thân prompt."]
    (AG / f"{slug}.md").write_text("\n".join(fm), encoding="utf-8")


def _bot(slug, brain=BRAIN):
    return {"id": "b1", "slug": "shop", "brain": brain, "agent": {"brain": brain, "slug": slug}}


# ---- 1. Agent chọn model -> bot chạy đúng model đó -------------------------------
_viet_agent("ag-codex", model="gpt-5.6-codex", provider="openai-oauth")
m = _mcfg("anthropic-cli", "sonnet")
prov, kind, _key, model = main._chat_provider_bot(m, _bot("ag-codex"))
check("agent chọn Codex -> bot chạy Codex, không phải model chính",
      prov == "openai-oauth" and model == "gpt-5.6-codex", (prov, model))
check("model chính KHÔNG bị đụng tới", main._chat_provider(m)[0] == "anthropic-cli")

# ---- 2. Agent để Mặc định -> theo model chính ------------------------------------
_viet_agent("ag-mac-dinh")
prov, _k, _key, model = main._chat_provider_bot(m, _bot("ag-mac-dinh"))
check("agent để Mặc định -> bot theo model chính",
      (prov, model) == main._chat_provider(m)[0::3], (prov, model))

# ---- 3. Agent CŨ chỉ lưu tên model ----------------------------------------------
_viet_agent("ag-cu", model="gpt-5.6-codex")
prov, _k, _key, model = main._chat_provider_bot(m, _bot("ag-cu"))
check("agent cũ (không có model_provider) vẫn suy ra đúng nhà",
      prov == "openai-oauth" and model == "gpt-5.6-codex", (prov, model))

# ---- 4. Nhà API chưa có key -> lui về model chính, không chết lượt ---------------
_viet_agent("ag-or", model="meta-llama/llama-3-70b", provider="openrouter")
m = _mcfg("anthropic-cli", "sonnet", openrouter_key="")
prov, _k, _key, model = main._chat_provider_bot(m, _bot("ag-or"))
check("agent trỏ nhà API chưa cắm key -> lui về model chính",
      prov == "anthropic-cli" and model == "sonnet", (prov, model))
m = _mcfg("anthropic-cli", "sonnet", openrouter_key="sk-test")
prov, _k, key, model = main._chat_provider_bot(m, _bot("ag-or"))
check("cắm key vào thì bot chạy đúng nhà đó",
      prov == "openrouter" and model == "meta-llama/llama-3-70b" and key == "sk-test",
      (prov, model, key))

# ---- 5. Agent bị xoá / bot chưa trỏ agent nào -> model chính ---------------------
prov, _k, _key, model = main._chat_provider_bot(m, _bot("khong-ton-tai"))
check("agent đã bị xoá -> bot vẫn trả lời bằng model chính",
      prov == "anthropic-cli" and model == "sonnet", (prov, model))
prov, _k, _key, model = main._chat_provider_bot(m, {"id": "b2", "brain": BRAIN})
check("bot chưa trỏ agent nào -> model chính",
      prov == "anthropic-cli" and model == "sonnet", (prov, model))

# ---- 6. CANARY: lượt của bot phải đi qua _chat_provider_bot ----------------------
SRC = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("CANARY: _tg_answer dùng _chat_provider_bot cho bot chuyên trách",
      "_chat_provider_bot(mcfg, bot) if bot" in SRC)
check("CANARY: không còn nhánh cũ lấy thẳng model chính cho bot",
      "(_chat_provider(mcfg) if bot" not in SRC)

# ---- 7. Thẻ trang Chatbot phải biết bot đang chạy model nào -----------------------
# Đổi hành vi mà không hiện ra thì chọn model cho trợ lý xong không cách nào biết bot đã theo
# hay chưa - đúng loại "hỏng lặng lẽ" mà repo này canh.
check("CANARY: /chatbots trả thêm agent_model cho thẻ", 'b["agent_model"] = _model_cua_agent(' in SRC)

print()
if _fails:
    print("THAT BAI " + str(len(_fails)) + ": " + ", ".join(_fails))
    sys.exit(1)
print("OK - test_chatbot_model_agent: tat ca pass")
