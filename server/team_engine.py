"""Engine của một lượt nhóm chat (0.142.0): hợp đồng CHAT TƯƠNG TÁC và GIAO VIỆC, tách khỏi hợp đồng Cộng hưởng.

Vì sao có module này. Trước 0.142.0 lượt nhóm dựng engine bằng `main._resonance_engine`, tức hợp đồng của Cộng hưởng:
model VIỆC NỀN, và chỉ nhận đúng hai cơ chế chỉ chữ đã kiểm (Claude có cổng `can_use_tool`, engine API có `no_tools`).
Máy để model việc nền là Codex (gói ChatGPT) thì `resonance.pick_text_only_link` chặn trước khi gọi model, bộ chạy coi
là lỗi dựng engine, còn tầng gọi bỏ kết quả lỗi đi: nhóm im lặng, không một dòng báo nào.

Hợp đồng ở đây:
- **Model:** model riêng của trợ lý (trường `model` + `model_provider` trong file agent). Trợ lý không đặt model, hay
  provider của nó chưa cấu hình được (thiếu khoá, chưa cài CLI) thì theo **model chính** ở trang Models. KHÔNG dùng model
  việc nền, KHÔNG tự đổi sang provider thứ ba, KHÔNG có chuỗi dự phòng: provider đã chọn không chạy được chỉ chữ thì lượt
  báo lỗi rõ lý do trong khung chat, chủ đổi model của trợ lý hay bấm Thử lại.
- **Quyền:** giữ nguyên giới hạn đã có của lượt nhóm (phán quyết R3): chỉ chữ, thư mục trống, không MCP, không hub.
  Sự kiện công cụ nào lọt ra vẫn làm hỏng lượt (`team_runner.TextOnlyOutcome`). Không nâng quyền, không bật Auto.

Cơ chế chỉ chữ theo provider:
- `anthropic-cli`: engine Claude hộp cát của caller (`allowed_tools` không khớp công cụ nào, MCP rỗng).
- `openai-oauth` (Codex): không profile `-p` (nơi có hub), `mcp_servers={}`, tắt các công cụ native bằng cờ `features.*`,
  và LUÔN `--sandbox read-only` kể cả khi máy đặt `JAVIS_CODEX_SANDBOX=off`: lượt chỉ chữ không chạy lệnh nào nên rào hỏng
  trong Docker không làm hỏng câu trả lời, còn công cụ còn sót (`apply_patch`) bị Codex từ chối ở tầng chính sách
  ("writing is blocked by read-only sandbox"). Đã thử với Codex 0.153.4 qua một máy chủ Responses giả: danh sách công cụ
  gửi cho model chỉ còn `request_user_input` và `apply_patch`, và một `apply_patch` ghi file ngoài thư mục bị từ chối.
- Engine API: `no_tools` (không hỏi hub, model không được đưa công cụ nào).
- Grok Build, Antigravity: chưa có cơ chế chỉ chữ được kiểm (Grok còn công cụ đọc native; `agy` đọc MCP từ file chung
  của máy). Báo lỗi rõ, không chạy thay bằng provider khác.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import aux_engine

CLAUDE = aux_engine.CLAUDE
CODEX = aux_engine.CODEX

# Công cụ native của Codex tắt được bằng `-c features.<tên>=false`. Tên lạ với một bản Codex bị bỏ qua (đã thử), nên
# danh sách được phép dài hơn những gì một bản cụ thể có.
CODEX_OFF_FEATURES = ("shell_tool", "unified_exec", "view_image", "goals", "apps", "multi_agent", "image_generation",
                      "browser_use", "browser_use_external", "computer_use", "plugins", "tool_suggest", "skill_search",
                      "sleep_tool", "code_mode_host", "in_app_browser", "shell_snapshot", "js_repl", "memories")


class TeamEngineUnavailable(RuntimeError):
    """Không dựng được engine chỉ chữ cho provider đã chọn. `reason` là câu cho chủ đọc."""

    def __init__(self, reason: str, provider: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.provider = provider


def choose_spec(agent_model: str, agent_provider: str, main: dict, resolve: Callable[[str, str], str],
                available: Callable[[dict], tuple]) -> dict:
    """Spec {provider, model, source, note} cho lượt nhóm của một trợ lý.

    `resolve(model, provider)` là luật chọn provider của agent (main._agent_model_provider). `available(spec)` trả
    (ok, lý do). Model riêng không chạy được thì theo model chính, kèm `note` nói vì sao (hiện trên tin)."""
    model = str(agent_model or "").strip()
    if model:
        prov = resolve(model, str(agent_provider or ""))
        spec = {"provider": prov, "model": model, "source": "agent", "note": ""}
        if not text_only_supported(prov):
            # Grok Build, Antigravity: chưa có cơ chế chỉ chữ được kiểm. Chạy bằng model chính và NÓI RÕ trên tin (không
            # âm thầm đổi provider), thay vì để trợ lý im hay báo lỗi mỗi tin.
            ok, why = False, "chưa chạy được lượt nhóm chỉ chữ (còn công cụ native không tắt riêng được)"
        else:
            ok, why = available(spec)
        if ok:
            return spec
        note = f"Model riêng của trợ lý ({prov}) chưa dùng được: {str(why or '').strip().rstrip('.')}. Lượt này chạy bằng model chính."
    else:
        note = ""
    m = dict(main or {})
    return {"provider": str(m.get("provider") or CLAUDE), "model": str(m.get("model") or ""), "source": "main",
            "note": note}


def text_only_supported(provider: str) -> bool:
    """Provider có cơ chế chỉ chữ đã kiểm cho lượt nhóm: Claude (cổng chặn), Codex (cờ + sandbox read-only), engine API."""
    p = str(provider or "")
    return p in (CLAUDE, CODEX) or p in aux_engine.API_PROVIDERS


def codex_text_only(cc: Any) -> Any:
    """Đặt một CodexCLI về chế độ chỉ chữ (xem docstring module)."""
    cc.profile = None
    cc.hub_turn = False
    cc.sandbox = "read-only"
    cfg = [c for c in (cc.extra_config or []) if not str(c).startswith(("mcp_servers", "features.", "web_search"))]
    cfg.append("mcp_servers={}")
    cfg.append('web_search="disabled"')
    cfg += [f"features.{f}=false" for f in CODEX_OFF_FEATURES]
    cc.extra_config = cfg
    cc.text_only = True
    return cc


def build(spec: dict, base: Any, tag: str, settings: Optional[dict] = None) -> Any:
    """Engine chỉ chữ cho `spec`. `base` là engine Claude hộp cát (thư mục trống, MCP rỗng, cổng từ chối mọi công cụ)
    mà caller đã dựng với lời nhắc hệ thống của trợ lý. Ném TeamEngineUnavailable khi không dựng được."""
    prov = str(spec.get("provider") or CLAUDE)
    model = str(spec.get("model") or "")
    if prov == CLAUDE:
        if not getattr(base, "allowed_tools", None):
            raise TeamEngineUnavailable("engine Claude không có cổng chặn công cụ", prov)
        base.model = model or None
        return base
    ok, why = aux_engine.availability({"provider": prov, "model": model}, settings)
    if not ok:
        raise TeamEngineUnavailable(str(why or "provider chưa sẵn sàng"), prov)
    if prov == CODEX:
        from claude_cli import CodexCLI
        cc = CodexCLI(cwd=getattr(base, "cwd", None), tag=tag, model=model or None,
                      instructions=getattr(base, "system_prompt", None))
        return codex_text_only(cc)
    if prov in aux_engine.API_PROVIDERS:
        eng = aux_engine._ApiAuxEngine(provider=prov, model=model, system_prompt=getattr(base, "system_prompt", None),
                                       vault_root=None, mode="suggest", tag=tag)
        eng.no_tools = True
        return eng
    raise TeamEngineUnavailable(
        f"{prov} chưa chạy được lượt nhóm chỉ chữ (còn công cụ native không tắt riêng cho lượt này được). "
        "Đổi model của trợ lý ở trang Cộng sự sang Claude, ChatGPT (Codex) hay một model API", prov)
