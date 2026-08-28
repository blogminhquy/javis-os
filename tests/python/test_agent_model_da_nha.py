"""Agent chọn được model của MỌI nhà cung cấp, và chạy ĐÚNG nhà đã chọn.

Chủ repo yêu cầu 27/08/2026: ô chọn model của agent (Studio) chỉ có Claude và ChatGPT,
muốn đầy đủ như trình chọn model chính.

Cái bẫy khiến việc này không phải là "thêm option vào <select>": tới 0.47.8, engine agent
(`_workflow_agent_helpers._mk`) chỉ biết hai nhánh - model kiểu gpt* thì chạy Codex, CÒN
LẠI thì nhét thẳng vào `c.model` của engine Claude Code. Nếu chỉ sửa giao diện, người dùng
chọn Gemini/OpenRouter xong agent vẫn lặng lẽ chạy Claude với một tên model nó không hiểu -
không lỗi, không cảnh báo, và hoá đơn về nhầm nhà. File này khoá cả hai đầu:

  * đầu SAU  : _mk phải đưa model của nhà khác sang aux_engine.swap, và KHÔNG được gán
               model đó vào engine Claude.
  * đầu TRƯỚC: danh sách bày ra cho người dùng chỉ được chứa nhà mà aux_engine dựng nổi
               engine - bày antigravity-cli/ollama là hứa suông vì server sẽ hạ về Claude.

Chạy:
    python tests/python/test_agent_model_da_nha.py
"""
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-agentmodel-"))

from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path

import aux_engine  # noqa: E402
import main  # noqa: E402

fails = []


def check(name: str, condition: bool, extra=None) -> None:
    print(("PASS: " if condition else "FAIL: ") + name
          + ("" if condition or extra is None else f"  [{extra}]"))
    if not condition:
        fails.append(name)


# ─────────── 1. Danh sách bày ra == danh sách chạy thật được ───────────
# Đây là luật chống hứa suông. Thêm nhà vào AGENT_PROVIDERS mà aux_engine chưa dựng nổi
# engine cho nó thì test này đỏ NGAY, thay vì để người dùng phát hiện bằng một agent chạy
# sai nhà trong im lặng.
dung_duoc = {aux_engine.CLAUDE, aux_engine.CODEX, aux_engine.GROK_CLI,
             aux_engine.ANTIGRAVITY} | set(aux_engine.API_PROVIDERS)
check("mọi nhà trong AGENT_PROVIDERS đều có bộ dựng engine ở aux_engine",
      set(main.AGENT_PROVIDERS) <= dung_duoc,
      sorted(set(main.AGENT_PROVIDERS) - dung_duoc))
check("có đủ cả CLI lẫn API (không còn chỉ Claude + ChatGPT)",
      len(main.AGENT_PROVIDERS) >= 7, len(main.AGENT_PROVIDERS))
for p in ("anthropic-cli", "openai-oauth", "grok-cli", "antigravity-cli", "openrouter",
          "anthropic-api", "openai", "gemini", "groq", "ollama"):
    check(f"có nhà {p}", p in main.AGENT_PROVIDERS)
check("đủ mọi nhà ở trang Models",
      len(main.AGENT_PROVIDERS) == len(main.PROVIDER_DEFS), len(main.AGENT_PROVIDERS))

# Giao diện Studio lọc theo cờ này, nên nó phải nói đúng AGENT_PROVIDERS.
view = {p["id"]: p for p in main._providers_view(main.cfgmod.read_settings())}
check("mọi provider đều có cờ agent_ok", all("agent_ok" in p for p in view.values()))
check("agent_ok khớp đúng AGENT_PROVIDERS",
      all(p["agent_ok"] == (pid in main.AGENT_PROVIDERS) for pid, p in view.items()),
      [pid for pid, p in view.items() if p["agent_ok"] != (pid in main.AGENT_PROVIDERS)])

# ─────────── 2. Suy ra nhà: có lưu thì theo, agent cũ thì suy như trước ───────────
check("nhà lưu sẵn thắng phép suy",
      main._agent_model_provider("gpt-5-codex", "openrouter") == "openrouter")
check("cùng tên model, khác nhà -> theo đúng nhà đã lưu",
      main._agent_model_provider("gemini-2.5-pro", "gemini") == "gemini"
      and main._agent_model_provider("gemini-2.5-pro", "openrouter") == "openrouter")
check("agent CŨ (chưa lưu nhà): gpt* vẫn ra Codex như trước",
      main._agent_model_provider("gpt-5-codex", "") == "openai-oauth")
check("agent CŨ: model Claude vẫn ra Claude Code như trước",
      main._agent_model_provider("opus", "") == "anthropic-cli")
check("nhà lạ (client cũ / gõ tay) rơi về phép suy chứ không tin bừa",
      main._agent_model_provider("opus", "nha-khong-co-that") == "anthropic-cli")

# ─────────── 3. _mk chạy ĐÚNG nhà đã chọn ───────────
_swap_that = aux_engine.swap
nhan = {}


def _swap_gia(cli, **kw):
    nhan.clear()
    nhan.update(kw.get("spec") or {})
    nhan["tag"] = kw.get("tag")
    return cli


aux_engine.swap = _swap_gia
try:
    mk, _sysprompt, _log, _learn = main._workflow_agent_helpers("brain", None)

    nhan.clear()
    cli = mk("prompt hệ thống", "openai/gpt-4o-mini", "openrouter")
    check("model nhà khác được chuyển sang aux_engine đúng nhà + đúng tên",
          nhan.get("provider") == "openrouter" and nhan.get("model") == "openai/gpt-4o-mini", nhan)
    check("KHÔNG nhét model nhà khác vào engine Claude (gốc của lỗi chạy nhầm nhà)",
          getattr(cli, "model", None) != "openai/gpt-4o-mini", getattr(cli, "model", None))

    nhan.clear()
    mk("x", "grok-4.6", "grok-cli")
    check("Grok Build CLI cũng đi qua aux_engine", nhan.get("provider") == "grok-cli", nhan)

    nhan.clear()
    mk("x", "claude-sonnet-4-5", "antigravity-cli")
    check("Antigravity CLI cũng đi qua aux_engine", nhan.get("provider") == "antigravity-cli", nhan)

    nhan.clear()
    mk("x", "qwen3-coder", "ollama")
    check("Ollama Cloud cũng đi qua aux_engine", nhan.get("provider") == "ollama", nhan)

    nhan.clear()
    cli2 = mk("x", "opus", "anthropic-cli")
    check("Claude Code giữ nguyên đường cũ (không qua aux_engine)", not nhan, nhan)
    check("model Claude vẫn được gán vào engine Claude", getattr(cli2, "model", None) == "opus")

    nhan.clear()
    cli3 = mk("x", "", "")
    check("để Mặc định thì không ép nhà nào", not nhan, nhan)

    # Rào an toàn đã hứa ở docs/07: workflow chạy NỀN ở chế độ giới hạn công cụ thì agent
    # luôn là Claude Code, kể cả khi chọn nhà khác - giới hạn nằm ở allowed_tools/
    # disallowed_tools của chính CLI đó, engine nhà khác lấy tool từ hub nên không mang
    # theo được rào ấy. Nhánh Codex cũ đã theo luật này; nhánh mới phải theo y hệt.
    mk_han, _s2, _l2, _h2 = main._workflow_agent_helpers("brain", ["Read"])
    nhan.clear()
    mk_han("x", "openai/gpt-4o-mini", "openrouter")
    check("chế độ giới hạn công cụ vẫn ở lại Claude Code (không nới quyền lén)", not nhan, nhan)
finally:
    aux_engine.swap = _swap_that

# ─────────── 4. File agent lưu + đọc lại được nhà ───────────
src = (SERVER / "main.py").read_text(encoding="utf-8")
check("save_agent nhận model_provider", "model_provider: str = Form(\"\")" in src)
check("chỉ ghi nhà hợp lệ vào file agent", 'mp if mp in AGENT_PROVIDERS else ""' in src)
check("agents_index trả model_provider cho giao diện",
      '"model_provider": meta.get("model_provider", "")' in src)
check("_agent_sysprompt trả kèm nhà", 'ameta.get("model_provider")' in src)
# Bốn chỗ bóc tuple và bốn chỗ dựng engine phải đi cùng nhau - lệch một chỗ là agent đó
# âm thầm mất nhà đã chọn.
check("đủ 4 chỗ bóc tuple 4 phần", src.count("= _agent_sysprompt(") + src.count("= agent_sysprompt(") == 4)
check("mọi chỗ bóc tuple đều lấy cả provider",
      src.count("agent_model, agent_prov = ") + src.count("v_model, v_prov = ") == 4)
check("mọi chỗ dựng engine đều truyền provider xuống",
      src.count("mk(sysprompt, agent_model, agent_prov)") + src.count("mk(v_sys, v_model, v_prov)") == 4)
check("router đổi model thì bỏ nhà cũ (không ép model Claude qua nhà khác)",
      'agent_prov = ""' in src)

print()
if fails:
    print(f"FAIL - test_agent_model_da_nha: {len(fails)} lỗi: " + ", ".join(fails))
    raise SystemExit(1)
print("OK - test_agent_model_da_nha: tất cả pass")
