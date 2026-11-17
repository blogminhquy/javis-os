"""Engine của một lượt nhóm chat (0.142.0): hợp đồng CHAT TƯƠNG TÁC và GIAO VIỆC, tách khỏi hợp đồng Cộng hưởng.

Vì sao có module này. Trước 0.142.0 lượt nhóm dựng engine bằng `main._resonance_engine`, tức hợp đồng của Cộng hưởng:
model VIỆC NỀN, và chỉ nhận đúng hai cơ chế chỉ chữ đã kiểm (Claude có cổng `can_use_tool`, engine API có `no_tools`).
Máy để model việc nền là Codex (gói ChatGPT) thì `resonance.pick_text_only_link` chặn trước khi gọi model, bộ chạy coi
là lỗi dựng engine, còn tầng gọi bỏ kết quả lỗi đi: nhóm im lặng, không một dòng báo nào.

Hợp đồng ở đây:
- **Model:** model riêng của trợ lý (trường `model` + `model_provider` trong file agent). Chỉ khi chưa chọn model/provider
  mới theo **model chính** ở trang Models. KHÔNG dùng model
  việc nền, KHÔNG tự đổi sang provider thứ ba, KHÔNG có chuỗi dự phòng: provider đã chọn không chạy được chỉ chữ thì lượt
  báo lỗi rõ lý do trong khung chat, chủ đổi model của trợ lý hay bấm Thử lại.
- **Quyền:** giữ nguyên giới hạn đã có của lượt nhóm (phán quyết R3): chỉ chữ, thư mục trống, không MCP, không hub.
  Sự kiện công cụ nào lọt ra vẫn làm hỏng lượt (`team_runner.TextOnlyOutcome`). Không nâng quyền, không bật Auto.
  Ngoại lệ từ 0.194.0: lượt Làm và Hỗ trợ của một việc nhóm (`team_runner.TOOL_ROLES`) chạy CÓ công cụ như chat riêng
  (`build_tools`). Lượt trò chuyện, lập kế hoạch, tổng hợp, quét và học vẫn chỉ chữ.

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
import engine_capability

CLAUDE = aux_engine.CLAUDE
CODEX = aux_engine.CODEX

# Công cụ native của Codex tắt được bằng `-c features.<tên>=false`. Tên lạ với một bản Codex bị bỏ qua (đã thử), nên
# danh sách được phép dài hơn những gì một bản cụ thể có.
CODEX_OFF_FEATURES = ("shell_tool", "unified_exec", "view_image", "goals", "apps", "multi_agent", "image_generation",
                      "browser_use", "browser_use_external", "computer_use", "plugins", "tool_suggest", "skill_search",
                      "sleep_tool", "code_mode_host", "in_app_browser", "shell_snapshot", "js_repl", "memories")


class TeamEngineUnavailable(RuntimeError):
    """Không dựng được engine chỉ chữ cho provider đã chọn. `reason` là câu cho chủ đọc."""

    def __init__(self, reason: str, provider: str = "", *, code: str = engine_capability.AUTH_MISSING,
                 stage: str = "preflight", fix_hint: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.provider = provider
        self.code = engine_capability.normalize_code(code)
        self.stage = stage
        self.fix_hint = fix_hint or engine_capability.reason(self.code, provider)["fix_hint"]
        self.retryable = bool(engine_capability.RETRYABLE.get(self.code, False))


def choose_spec(agent_model: str, agent_provider: str, main: dict, resolve: Callable[[str, str], str],
                available: Callable[[dict], tuple], tools: bool = False) -> dict:
    """Select identity, never a replacement for an unavailable explicit selection (engine_capability.select).

    Only an unset agent selection inherits MAIN (source=main). Legacy model-only data uses the caller's resolver
    (source=legacy); explicit provider IDs are never inferred from a model name. Readiness/capability belongs to
    build, so an unsupported text-only choice cannot prevent an otherwise supported tool turn.
    The `available`/`tools` arguments remain for existing callers; availability is not a routing decision.
    """
    return engine_capability.select(agent_model, agent_provider, main,
                                    (lambda m: resolve(m, "")) if resolve is not None else None)


def validate_spec(spec: dict) -> None:
    """Fail closed for an unregistered adapter, before consulting credentials or probing a CLI."""
    provider = str(spec.get("provider") or CLAUDE)
    if provider not in engine_capability.KNOWN_PROVIDERS:
        r = engine_capability.reason(engine_capability.PROVIDER_UNKNOWN, provider)
        raise TeamEngineUnavailable(r["message"], provider, code=r["reason_code"], stage="resolve",
                                    fix_hint=r["fix_hint"])


def text_only_supported(provider: str) -> bool:
    """Provider có cơ chế chỉ chữ đã kiểm cho lượt nhóm: Claude (cổng chặn), Codex (cờ + sandbox read-only), engine API.
    Nguồn duy nhất: engine_capability (mode team_text)."""
    return engine_capability.adapter_static(str(provider or ""), engine_capability.TEAM_TEXT)


def tools_supported(provider: str) -> bool:
    """Provider dựng được engine CÓ công cụ cho lượt Làm/Hỗ trợ (0.194.0): mọi provider có builder việc nền.
    Nguồn duy nhất: engine_capability (mode team_tool_full)."""
    return engine_capability.adapter_static(str(provider or ""), engine_capability.TEAM_TOOL_FULL)


def _not_ready(prov: str, model: str, why: str) -> TeamEngineUnavailable:
    """Availability probe said no: auth_missing with the probe's own sentence (no secrets: aux_engine reasons only)."""
    r = engine_capability.reason(engine_capability.AUTH_MISSING, prov)
    return TeamEngineUnavailable(str(why or r["message"]), prov, code=r["reason_code"], stage="preflight",
                                 fix_hint=r["fix_hint"])


def codex_text_only(cc: Any) -> Any:
    """Đặt một CodexCLI về chế độ chỉ chữ (xem docstring module)."""
    cc.profile = None
    cc.hub_turn = False
    cc.sandbox = "read-only"
    cfg = [c for c in (cc.extra_config or []) if not str(c).startswith(("mcp_servers", "features.", "web_search"))]
    cfg.append("mcp_servers={}")
    cfg.append('web_search="disabled"')
    cfg += [f"features.{f}=false" for f in CODEX_OFF_FEATURES]
    # Fast mode (0.164.0): team turns run at the normal tier whatever config.toml says.
    cfg = [c for c in cfg if not str(c).startswith("service_tier=")] + ['service_tier="default"']
    cc.extra_config = cfg
    cc.text_only = True
    return cc


def build(spec: dict, base: Any, tag: str, settings: Optional[dict] = None) -> Any:
    """Engine chỉ chữ cho `spec`. `base` là engine Claude hộp cát (thư mục trống, MCP rỗng, cổng từ chối mọi công cụ)
    mà caller đã dựng với lời nhắc hệ thống của trợ lý. Ném TeamEngineUnavailable khi không dựng được."""
    validate_spec(spec)
    prov = str(spec.get("provider") or CLAUDE)
    model = str(spec.get("model") or "")
    if prov == CLAUDE:
        if not getattr(base, "allowed_tools", None):
            raise TeamEngineUnavailable("engine Claude không có cổng chặn công cụ", prov,
                                        code=engine_capability.CAPABILITY_UNSUPPORTED, stage="capability")
        base.model = model or None
        return base
    if not text_only_supported(prov):
        from localefmt import chu
        raise TeamEngineUnavailable(chu(
            "{provider} chưa chạy được lượt nhóm chỉ chữ. Kiểm tra lựa chọn ở trang Cộng sự; Javis không tự đổi provider.",
            "{provider} cannot run text-only team turns. Check the Partners selection; Javis will not switch providers.",
            provider=prov), prov,
            code=engine_capability.CAPABILITY_UNSUPPORTED, stage="capability")
    ok, why = aux_engine.availability({"provider": prov, "model": model}, settings)
    if not ok:
        raise _not_ready(prov, model, why)
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
        "Đổi model của trợ lý ở trang Cộng sự sang Claude, ChatGPT (Codex) hay một model API", prov,
        code=engine_capability.CAPABILITY_UNSUPPORTED, stage="capability")


def build_tools(spec: dict, base: Any, tag: str, settings: Optional[dict] = None, mode: str = "full",
                codex_profile: Optional[Callable[[], Any]] = None) -> Any:
    """Engine CÓ công cụ cho lượt Làm/Hỗ trợ của việc nhóm (0.194.0, chủ 17/10/2026: "team phải đầy đủ các quyền thì mới
    làm việc được"). `base` là engine Claude caller đã dựng như chat riêng: cwd là thư mục làm việc của nhóm (hay bộ não),
    hub MCP gắn ở mức `mode`, `javis_vault` là bộ não. Provider khác Claude dựng bằng đúng các builder của việc nền
    (`aux_engine._build_*`), nên quyền đi theo cùng một chỗ: hub chặn theo mức, sandbox Codex và cờ deny của Grok theo mức.
    Không có chuỗi dự phòng (như việc nền mức full): provider đã chọn không chạy được thì báo lỗi rõ."""
    validate_spec(spec)
    prov = str(spec.get("provider") or CLAUDE)
    model = str(spec.get("model") or "")
    if prov == CLAUDE:
        base.model = model or None
        return base
    if not tools_supported(prov):
        r = engine_capability.reason(engine_capability.CAPABILITY_UNSUPPORTED, prov, engine_capability.TEAM_TOOL_FULL)
        raise TeamEngineUnavailable(r["message"], prov, code=r["reason_code"], stage="capability")
    ok, why = aux_engine.availability({"provider": prov, "model": model}, settings)
    if not ok:
        raise _not_ready(prov, model, why)
    sp = {"provider": prov, "model": model}
    if prov == CODEX:
        return aux_engine._build_codex(sp, base, mode, tag, codex_profile)
    if prov == aux_engine.GROK_CLI:
        return aux_engine._build_grok(sp, base, mode, tag)
    if prov == aux_engine.ANTIGRAVITY:
        return aux_engine._build_antigravity(sp, base, mode, tag)
    if prov in aux_engine.API_PROVIDERS:
        return aux_engine._build_api(sp, base, mode, tag)
    raise TeamEngineUnavailable(f"{prov} chưa dựng được lượt làm việc có công cụ", prov,
                                code=engine_capability.BUILD_FAILED, stage="build")
