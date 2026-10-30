"""Engine cho VIỆC NỀN (loop, việc Kanban, nhắc hẹn, tự học, tiêu hoá nguồn).

Trước đây việc nền luôn chạy bằng Claude Code, ô chọn ở trang Model bị khoá cứng vào
danh sách model của provider 'anthropic-cli' - muốn đẩy việc nền sang gói ChatGPT hay
một API rẻ để đỡ hạn mức Claude thì không có đường. Module này mở đường đó.

Cách nối vào (cố ý ít xâm lấn): các nơi chạy nền VẪN dựng engine Claude y như cũ, kèm
đủ allowlist/mode/MCP mà chúng vốn tính toán; xong xuôi mới gọi `swap()`. Nếu người dùng
để mặc định Claude thì `swap()` trả lại đúng engine đó, không đổi gì. Chọn provider khác
thì `swap()` đọc chính các thuộc tính engine Claude đã tính (system_prompt, cwd, vault,
mode, allowlist) và dựng engine tương ứng - nên mọi quyết định an toàn ở đầu kia được
thừa hưởng nguyên vẹn, không phải chép lại.

Ba loại engine, khác nhau ở CÔNG CỤ có được - đây là chỗ phải cẩn thận:
- anthropic-cli: Claude Code. Tool file native + Bash + MCP, chặn theo allowlist per-call.
- openai-oauth: Codex CLI, cũng là agent thật (đọc/ghi file + MCP qua profile javis).
  Sandbox của Codex ánh xạ theo mode: suggest -> read-only, auto -> workspace-write,
  full -> toàn quyền. KHÔNG có allowlist per-call như Claude nên chỉ chặn ở tầng sandbox.
- grok-cli: Grok Build CLI chạy bằng gói SuperGrok / X Premium+. Cũng agent thật (tool file +
  MCP hub qua .grok/config.toml trong brain). Mức quyền xuống thẳng cờ chặn của CLI:
  suggest -> chặn Write/Edit/Bash, auto -> chặn Bash, full -> không chặn ở tầng CLI.
- api (openrouter/openai/gemini/anthropic-api): KHÔNG có tool native. Bù lại hub cấp
  javis_read_file / javis_list_dir / javis_write_file / javis_use_skill + tool MCP, và
  javis_write_file tự chặn khi mode là suggest (mcp_hub._builtin_tools). Không có Bash,
  không có WebFetch - hẹp hơn Claude, nhưng đủ cho việc nền đọc/ghi ghi chú trong vault.

Hợp đồng sự kiện giữ y như ClaudeSDK để nơi gọi không phải sửa: query() sinh dict
{"type": "tool_call"|"final"|"error"|"usage", ...}. Đường API sinh "text" nhiều mảnh nên
ở đây gom lại thành đúng MỘT "final" ở cuối - việc nền đều chỉ đọc sự kiện final.
"""
from __future__ import annotations

import os
import re
import sys
import time
from typing import Optional

import config as cfgmod
import model_routing

CLAUDE = "anthropic-cli"
CODEX = "openai-oauth"
GROK_CLI = "grok-cli"
ANTIGRAVITY = "antigravity-cli"
API_PROVIDERS = ("openrouter", "openai", "gemini", "groq", "deepseek", "anthropic-api", "ollama",
                 "ollama-local", "openai-compat", "anthropic-compat")

# provider -> tên trường chứa API key trong settings["model"]
_KEY_FIELD = {
    "openrouter": "openrouter_key",
    "openai": "openai_api_key",
    "gemini": "gemini_api_key",
    "groq": "groq_api_key",
    "deepseek": "deepseek_api_key",
    "anthropic-api": "anthropic_api_key",
    "ollama": "ollama_key",
    # Bản chạy MÁY NHÀ. Trường này thường RỖNG - Ollama trần không có xác thực - và điều đó
    # là bình thường chứ không phải "chưa cấu hình": thứ xác định nó dùng được hay không là
    # ĐỊA CHỈ (`ollama_local_endpoint`), còn khoá chỉ cần khi ai đó đặt Ollama sau reverse
    # proxy. Xem `_key_of` bên dưới, chỗ ollama-local được miễn kiểm khoá rỗng.
    "ollama-local": "ollama_local_key",
    # Endpoint OpenAI-compatible tự khai. Như ollama-local: thứ quyết định dùng được là ĐỊA CHỈ
    # (`openai_compat_base`), khoá có thể rỗng khi endpoint không đòi xác thực.
    "openai-compat": "openai_compat_key",
    # Anthropic-compatible gateway (0.254.0): usable once its base URL is set, like openai-compat.
    "anthropic-compat": "anthropic_compat_key",
}

# mode của Javis -> sandbox của Codex CLI. Bản đồ thật nằm ở `claude_cli.codex_sandbox_cho_mode`
# (nó còn đọc cờ JAVIS_CODEX_SANDBOX); giữ dict này để mã cũ đọc tên mức vẫn chạy.
_CODEX_SANDBOX = {"suggest": "read-only", "auto": "workspace-write", "full": None}

# ── Final "mất đăng nhập" phải bị coi là engine CHẾT, không phải kết quả ──────────────────
# Claude Code chưa đăng nhập KHÔNG trả event error: ResultMessage lỗi vẫn có chữ nên
# claude_sdk_engine map thành một FINAL ngắn "Not logged in · Please run /login".
# _FallbackChain mà tin final đó là thành công thì mắt sau không bao giờ được thử.
# Ca thật 26/08: máy chỉ đăng nhập Gemini, việc nền mặc định Claude → vòng tự học nào
# cũng chết với đúng câu này, nhật ký chỉ ghi "không parse được manifest" khó hiểu.
# Danh sách mẫu đồng bộ TAY với connect_health._ENGINE_AUTH_PATTERNS (không import -
# module này phải test đứng một mình được, xem tests/python/test_aux_fallback.py).
_AUTH_FINAL_PATTERNS = ("please run /login", "not logged in", "invalid api key",
                        "api key not found", "failed to authenticate",
                        "oauth session expired", "oauth token has expired",
                        "could not be refreshed", "refresh token was already used",
                        "log out and sign in again")
_AUTH_FINAL_MAX = 400   # câu lỗi đăng nhập luôn ngắn; final dài là nội dung thật, đừng nghi oan


def final_loi_dang_nhap(text: str) -> bool:
    """Final này có phải câu báo mất đăng nhập của engine CLI không."""
    t = (text or "").strip()
    if not t or len(t) > _AUTH_FINAL_MAX:
        return False
    low = t.lower()
    return any(p in low for p in _AUTH_FINAL_PATTERNS)

# ── Trần wall-clock cho fork NỀN (nhắc hẹn/cron, việc Kanban, bước workflow) ──────────────
# Mặc định 3600s (1 giờ). Trước đây mỗi nơi ghim một số cứng (nhắc hẹn 300, workflow 300,
# Kanban 600) và 300s giết chết việc nền THẬT của người dùng: quét 11 phân mục Meta Ads +
# ghi Google Sheet + gửi Telegram bị chặt ngang lúc đang ghi dở, result rỗng (báo 18/08).
# Trần này là LƯỚI ĐỠ chống fork treo vô hạn, không phải công cụ quản chi phí - fork đơ
# thật thì watchdog idle-timeout của engine bắt sớm hơn nhiều, nên đặt trần theo việc nền
# DÀI NHẤT hợp lệ chứ không theo việc trung bình. Chỉnh qua env JAVIS_BG_MAX_WALL_S
# (giây; giá trị rác hoặc <= 0 thì về mặc định).
BG_MAX_WALL_S_DEFAULT = 3600


def bg_max_wall_s() -> int:
    try:
        v = int(os.getenv("JAVIS_BG_MAX_WALL_S", "") or 0)
        if v > 0:
            return v
    except (TypeError, ValueError):
        pass
    return BG_MAX_WALL_S_DEFAULT

# ── Chọn model FREE mạnh nhất trên OpenRouter (mắt xích cuối của router việc nền) ──
# Xếp hạng theo HỌ model (đầu danh sách = mạnh nhất) rồi tới cỡ tham số trong id, rồi context.
# Danh sách model free của OpenRouter đổi liên tục nên chấm điểm động thay vì ghim cứng 1 tên.
_FREE_FAMILY_RANK = ("deepseek-r1", "deepseek", "qwen3", "qwen", "llama-4", "llama-3.3",
                     "llama", "glm", "gemini", "mistral", "kimi")
_OR_FREE_CACHE = {"ts": 0.0, "model": ""}   # cache 6h - khỏi gọi API models mỗi lần fallback
_OR_FREE_TTL = 6 * 3600


def _score_free_model(mid: str, ctx: int = 0) -> tuple:
    low = (mid or "").lower()
    fam = 0
    for i, f in enumerate(_FREE_FAMILY_RANK):
        if f in low:
            fam = len(_FREE_FAMILY_RANK) - i
            break
    sizes = [int(x) for x in re.findall(r"(\d{1,4})b\b", low)]
    return (fam, max(sizes, default=0), ctx)


async def pick_openrouter_free(key: str = "") -> str:
    """Model free mạnh nhất đang có trên OpenRouter. Lỗi mạng → đoán tĩnh một id phổ biến."""
    now = time.time()
    if _OR_FREE_CACHE["model"] and now - _OR_FREE_CACHE["ts"] < _OR_FREE_TTL:
        return _OR_FREE_CACHE["model"]
    data = []
    try:
        import httpx
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        async with httpx.AsyncClient(timeout=20) as cx:
            r = await cx.get("https://openrouter.ai/api/v1/models", headers=headers)
            r.raise_for_status()
            data = (r.json() or {}).get("data") or []
    except Exception as e:
        print(f"[aux router] không tải được danh sách model OpenRouter: {e}", file=sys.stderr)
    best, best_score = "", (-1, -1, -1)
    for m in data:
        mid = m.get("id") or ""
        if not mid.endswith(":free"):
            continue
        score = _score_free_model(mid, int(m.get("context_length") or 0))
        if score > best_score:
            best, best_score = mid, score
    if not best:
        best = "deepseek/deepseek-chat:free"
    _OR_FREE_CACHE.update(ts=now, model=best)
    return best


def read_spec(settings: dict = None) -> dict:
    """{'provider','model'} của model việc nền. Cấu hình cũ chỉ có 'model' (luôn là alias
    Claude) nên thiếu provider = anthropic-cli - giữ nguyên hành vi bản cũ.

    PHANH NGÂN SÁCH: nếu tháng này đã tiêu quá trần tiền người dùng đặt VÀ họ đã bật tự
    phanh, việc nền không được tiêu thêm tiền mặt nữa. Nó không dừng lại - nó chuyển sang
    đường KHÔNG tính tiền theo token: gói thuê bao đang đăng nhập, hoặc model free của
    OpenRouter. Chat của người dùng KHÔNG bị đụng tới; chỉ việc chạy nền bị hạ, vì đó là
    phần tiêu tiền lúc người ta không ngồi nhìn.
    """
    s = settings if settings is not None else cfgmod.read_settings()
    aux = (s.get("model", {}) or {}).get("auxiliary") or {}
    spec = {"provider": (aux.get("provider") or CLAUDE), "model": (aux.get("model") or "")}
    if spec["provider"] not in API_PROVIDERS:
        return spec                      # gói thuê bao: không tính tiền theo token, kệ phanh
    try:
        import usage_saving
        if not usage_saving.dang_phanh().get("bat"):
            return spec
    except Exception:                    # noqa: BLE001 - thiếu module thì cứ chạy như cũ
        return spec
    return _spec_ne_tien(s, spec)


def _spec_ne_tien(s: dict, spec: dict) -> dict:
    """Đường thay thế khi phanh: ưu tiên gói thuê bao đã đăng nhập, cuối cùng là OpenRouter free.

    `availability` trả True VÔ ĐIỀU KIỆN cho anthropic-cli (nó không kiểm binary `claude` có
    trên máy hay không, khác hẳn nhánh Codex/Gemini). Nên nếu chỉ hỏi availability thì vòng
    này luôn dừng ở mắt đầu, và trên máy KHÔNG cài Claude Code việc nền bị đẩy sang một engine
    không chạy được - phanh biến thành cái làm chết việc nền. Phải hỏi thẳng binary.
    """
    for prov in (CLAUDE, CODEX):
        ok, _ly_do = availability({"provider": prov}, s)
        if ok and _co_binary(prov):
            return {"provider": prov, "model": ""}
    if api_key_for("openrouter", s):
        # model "" trên OpenRouter = tự chọn model FREE mạnh nhất lúc chạy (_ApiAuxEngine.query).
        return {"provider": "openrouter", "model": ""}
    return spec                          # không có đường nào rẻ hơn -> giữ nguyên, đừng làm chết việc nền


def _co_binary(prov: str) -> bool:
    """Engine CLI đó có thật trên máy không. Lỗi/thiếu module -> False (đừng đoán là có)."""
    try:
        import claude_cli
        if prov == CLAUDE:
            return bool(claude_cli.find_claude_cli())
        if prov == CODEX:
            return bool(claude_cli.find_codex_cli())
    except Exception:   # noqa: BLE001 - không dò được thì coi như không có, rồi thử mắt sau
        return False
    return False


def main_spec(settings: dict = None) -> dict:
    """{'provider','model'} của MAIN MODEL (bộ não người dùng chọn ở trang Models).

    Bản rút của main._effective_main - chép lại thay vì import main (module này không được
    import main, tránh vòng). Dùng làm MẮT DỰ PHÒNG cho việc nền: người để trống model phụ
    thì aux mặc định Claude, nhưng máy chỉ đăng nhập Gemini/OpenAI... thì Claude chết và
    việc nền chết theo dù bộ não CHÍNH vẫn chạy ngon - chuỗi fallback phải biết tới nó.
    """
    s = settings if settings is not None else cfgmod.read_settings()
    m = s.get("model", {}) or {}
    main = m.get("main") or {}
    if main.get("provider"):
        return {"provider": main["provider"], "model": main.get("model") or ""}
    eng = m.get("engine")
    if eng == "openrouter":
        return {"provider": "openrouter", "model": m.get("openrouter_model") or ""}
    if eng == "anthropic-api":
        return {"provider": "anthropic-api", "model": m.get("claude_model") or ""}
    return {"provider": CLAUDE, "model": m.get("claude_model") or ""}


def is_claude(spec: dict) -> bool:
    return (spec or {}).get("provider", CLAUDE) == CLAUDE


def api_key_for(provider: str, settings: dict = None) -> str:
    field = _KEY_FIELD.get(provider)
    if not field:
        return ""
    s = settings if settings is not None else cfgmod.read_settings()
    m = s.get("model", {}) or {}
    if provider == "openai-compat":
        # Có Base URL là chạy được; khoá rỗng thì gửi "none" (endpoint không đòi xác thực).
        return (m.get(field) or "none") if (m.get("openai_compat_base") or "").strip() else ""
    if provider == "anthropic-compat":
        return (m.get(field) or "none") if (m.get("anthropic_compat_base") or "").strip() else ""
    return m.get(field) or ""


def availability(spec: dict, settings: dict = None) -> tuple:
    """(dùng được?, lý do nếu không). Để trang Model cảnh báo TRƯỚC khi người dùng chọn
    nhầm một provider chưa đăng nhập / chưa có key rồi việc nền chết lặng lẽ."""
    prov = (spec or {}).get("provider", CLAUDE)
    if prov == CLAUDE:
        return True, ""
    if prov == CODEX:
        try:
            from claude_cli import find_codex_cli
            if not find_codex_cli():
                return False, "Chưa cài Codex CLI (cần đăng nhập gói ChatGPT)."
        except Exception:
            return False, "Không kiểm tra được Codex CLI."
        return True, ""
    if prov == GROK_CLI:
        try:
            import grok_cli as _g
            st = _g.auth_status()
            if not st.get("connected"):
                return False, st.get("error") or "Grok Build CLI chưa sẵn sàng."
        except Exception:
            return False, "Không kiểm tra được Grok Build CLI."
        return True, ""
    if prov == ANTIGRAVITY:
        try:
            import antigravity_cli as _a
            if not _a.find_antigravity_cli():
                return False, "Chưa cài Antigravity CLI (`agy`) trên máy chạy Javis."
            # Bản NỀN (đọc cache, làm mới bằng thread), KHÔNG phải auth_status(): hàm này chạy
            # ngay trong code async (học sau lượt chat, việc Kanban, nhắc hẹn, loop), mà
            # auth_status() hỏi thẳng `agy models` tới 80 giây. Cả app đứng theo: chủ repo đổi
            # trợ lý giữa lúc Gemini đang chạy thì màn hình không đổi (23/09).
            # "dang_kiem" = mới khởi động, chưa có kết quả: cứ cho chạy, lượt thật tự báo lỗi.
            st = _a.auth_status_nen()
            if not st.get("connected") and not st.get("dang_kiem"):
                return False, st.get("error") or "Antigravity CLI chưa đăng nhập Google."
        except Exception:
            return False, "Không kiểm tra được Antigravity CLI."
        return True, ""
    # Ollama máy nhà xét theo ĐỊA CHỈ, không theo khoá: Ollama trần không có xác thực nên
    # khoá rỗng là trạng thái BÌNH THƯỜNG. Để nó rơi vào nhánh kiểm khoá bên dưới thì mọi
    # agent dùng model local đều bị báo "chưa có API key" dù đang chạy ngon.
    if prov == "ollama-local":
        s = settings if settings is not None else cfgmod.read_settings()
        if not (s.get("model", {}) or {}).get("ollama_local_endpoint"):
            return False, "Chưa đặt địa chỉ Ollama - vào trang Models, tab Local Model."
        return True, ""
    if prov == "openai-compat":
        s = settings if settings is not None else cfgmod.read_settings()
        if not (s.get("model", {}) or {}).get("openai_compat_base"):
            return False, "Chưa đặt Base URL cho OpenAI Compatible - vào trang Models."
        return True, ""
    if prov == "anthropic-compat":
        s = settings if settings is not None else cfgmod.read_settings()
        if not (s.get("model", {}) or {}).get("anthropic_compat_base"):
            return False, "Chưa đặt Base URL cho Anthropic Compatible - vào trang Models."
        return True, ""
    if prov in API_PROVIDERS:
        if not api_key_for(prov, settings):
            return False, f"Chưa có API key cho {prov} - vào trang Model dán key trước."
        return True, ""
    return False, f"Provider lạ: {prov}"


class _ApiAuxEngine:
    """Engine việc nền chạy bằng provider API, mang hợp đồng của ClaudeSDK.

    Công cụ lấy từ hub (builtin file vault + MCP). Hub tự chặn ghi khi mode=suggest, nên
    loop chế độ chỉ-đọc vẫn chỉ-đọc dù chạy trên engine này.
    """

    def __init__(self, provider, model, system_prompt=None, vault_root=None,
                 mode="full", tag="aux", reasoning="off", api_key="", account_id=""):
        self.provider = provider
        self.model = model
        # 0.350.0: one link per account of the card, so the chain moves to key 2 when key 1 is out of quota.
        self.api_key = api_key or ""
        self.account_id = account_id or ""
        self.system_prompt = system_prompt
        self.vault_root = vault_root
        self.javis_mode = mode
        self.tag = tag
        self.reasoning = reasoning
        self.session_id = None      # engine API không có phiên nối tiếp - giữ cho đủ hợp đồng

    def is_available(self) -> bool:
        return bool(self.api_key or api_key_for(self.provider))

    def reset_session(self):
        self.session_id = None

    async def query(self, prompt: str):
        import engine as eng
        import mcp_hub

        key = self.api_key or api_key_for(self.provider)
        if not key:
            import localefmt
            yield {"type": "error", "content": localefmt.chu(f"Chưa có API key cho {self.provider}.",
                                                             f"No API key for {self.provider}.")}
            return

        # OpenRouter model trống = "tự chọn free mạnh nhất". User ghi đè bằng
        # settings model.fallback_openrouter_model; lần chọn tự động đầu tiên cũng lưu vào
        # đúng field đó để user thấy đang dùng gì và đổi sau nếu muốn.
        if self.provider == "openrouter" and not self.model:
            try:
                s = cfgmod.read_settings()
                override = ((s.get("model", {}) or {}).get("fallback_openrouter_model") or "").strip()
                self.model = override or await pick_openrouter_free(key)
                if not override and self.model:
                    s.setdefault("model", {})["fallback_openrouter_model"] = self.model
                    cfgmod.write_settings(s)
            except Exception as e:
                print(f"[aux router] chọn model free lỗi: {e}", file=sys.stderr)
            if not self.model:
                import localefmt
                yield {"type": "error", "content": localefmt.chu("Không chọn được model free OpenRouter.",
                                                                 "Could not pick a free OpenRouter model.")}
                return

        tools, route = [], {}
        # `no_tools` (strip_tools): text-only turn on untrusted input, so the hub is never asked for anything.
        if not getattr(self, "no_tools", False):
            try:
                tools, route = await mcp_hub.discover_all(self.javis_mode or "full",
                                                          vault_root=self.vault_root)
            except Exception as e:
                print(f"[aux discover] {e}", file=sys.stderr)

        messages = []
        sysprompt = self.system_prompt or ""
        # Khai THẬT năng lực của engine này. Không có dòng này, model chỉ thấy "gọi tool X
        # không được" rồi tự dựng một lý do nghe hợp lý mà sai - hay gặp nhất là đổ cho quyền
        # ("phiên này bị chặn quyền"), khiến chủ đi sửa mức quyền trong khi mức quyền không hề
        # sai. Nói rõ THIẾU GÌ và VÌ SAO thì câu báo về mới dẫn đúng tới việc cần làm.
        sysprompt += (
            "\n\n[Sự thật hệ thống - năng lực của phiên này] Bạn đang chạy bằng engine API "
            f"'{self.provider}', KHÔNG phải Claude Code. Bạn có: các tool qua MCP Hub của Javis "
            "(gồm tool đọc/ghi file trong vault và mọi MCP người dùng đã đấu vào Javis). "
            "Bạn KHÔNG có: lệnh máy (Bash), tự mở URL (WebFetch/WebSearch), và KHÔNG có các "
            "connector gắn thẳng vào TÀI KHOẢN Claude - Gmail, Google Drive, Google Calendar "
            "gọi bằng tool native `mcp__<tên>__*` chỉ tồn tại trên engine Claude Code. "
            "Nếu việc được giao cần một trong những thứ đó, hãy nói THẲNG là engine hiện tại "
            "không có công cụ ấy và chủ cần đổi model việc nền sang Claude Code. TUYỆT ĐỐI "
            "không mô tả chuyện này là bị chặn quyền hay thiếu quyền: mức quyền không liên "
            "quan, đây là chuyện engine nào có tool nào."
        )
        if sysprompt.strip():
            messages.append({"role": "system", "content": sysprompt})
        messages.append({"role": "user", "content": prompt})

        if tools:
            fn = {"openrouter": eng.openrouter_chat_with_mcp,
                  "openai": eng.openai_chat_with_mcp,
                  "gemini": eng.gemini_chat_with_mcp, "groq": eng.groq_chat_with_mcp,
                  "deepseek": eng.deepseek_chat_with_mcp,
                  "anthropic-api": eng.anthropic_chat_with_mcp,
                  "ollama": eng.ollama_chat_with_mcp,
                  "ollama-local": eng.ollama_local_chat_with_mcp,
                  "openai-compat": eng.openai_compat_chat_with_mcp,
                  "anthropic-compat": eng.anthropic_compat_chat_with_mcp}[self.provider]
            stream = fn(key, self.model, messages, self.reasoning, tools, route)
        else:
            fn = {"openrouter": eng.openrouter_stream, "openai": eng.openai_stream,
                  "gemini": eng.gemini_stream, "groq": eng.groq_stream,
                  "deepseek": eng.deepseek_stream,
                  "anthropic-api": eng.anthropic_stream,
                  "ollama": eng.ollama_stream,
                  "ollama-local": eng.ollama_local_stream,
                  "openai-compat": eng.openai_compat_stream,
                  "anthropic-compat": eng.anthropic_compat_stream}[self.provider]
            stream = fn(key, self.model, messages, self.reasoning)

        # Đường API sinh "text" theo mảnh; việc nền chỉ đọc "final" nên gom lại rồi phát MỘT lần.
        buf = []
        import turn_context
        observed_requests = [False]
        request_ids = set()
        self.usage_request_count = 0

        def observe_request(event):
            observed_requests[0] = True
            request_ids.add(event.get("event_id"))
            self.usage_request_count = len(request_ids)
            self._ghi_muc_dung(event)

        observer = observe_request if (turn_context.current() or {}).get("execution") else None
        observer_token = eng.TEAM_REQUEST_OBSERVER.set(observer)
        try:
            async for ev in stream:
                t = ev.get("type")
                if t == "text":
                    buf.append(ev.get("content") or "")
                elif t in ("tool_call", "error", "usage"):
                    if t == "usage" and not observed_requests[0]:
                        self.usage_request_count += 1
                        self._ghi_muc_dung(ev)
                    yield ev
                    if t == "error":
                        return
        finally:
            eng.TEAM_REQUEST_OBSERVER.reset(observer_token)
        yield {"type": "final", "content": "".join(buf)}

    def _ghi_muc_dung(self, ev: dict) -> None:
        """Cộng lượt việc nền này vào sổ mức dùng.

        Đây là chỗ DUY NHẤT việc nền chạy bằng API key đi qua. Trước đây không có nó: cả 12
        chỗ gọi `usage_store.record` trong repo đều nằm trên đường CHAT, còn loop / việc
        Kanban / nhắc hẹn / tự học đều chạy qua đây và không ghi gì. Hệ quả là trang Mức dùng
        không thấy phần token nền của nhánh API, và tệ hơn: trần tiền tháng cùng cái phanh
        ngân sách không nhìn thấy ĐÚNG khoản chi mà chúng sinh ra để chặn - việc nền tiêu tiền
        lúc không ai ngồi nhìn.

        Best-effort: hỏng thì nuốt, một cái sổ đếm không được phép làm chết việc nền.
        """
        try:
            import usage_store
            usage_store.record(self.provider, self.model,
                               ev.get("input"), ev.get("output"), ev.get("cost"),
                               request_id=ev.get("request_id"), event_id=ev.get("event_id"),
                               cache_read=ev.get("cache_read"), cache_create=ev.get("cache_create"))
        except Exception as e:  # noqa: BLE001
            try:
                usage_store.note_telemetry_error()
            except Exception:
                pass
            print(f"[aux usage] {type(e).__name__}: {e}", file=sys.stderr)


# ---- Cooldown of broken links (0.222.0) ----
# A link that just failed is put to rest for a while, so the next background job does not pay for
# the same dead model again (a 504 can take 15 seconds to arrive). Process memory only: a restart
# forgets, which is the right default after an update or a new key. Resting links are not skipped,
# they move to the END of the chain: if every other link fails too, the one closest to waking is
# still tried, because a background job must run rather than die.
COOLDOWN_QUOTA_S = 5 * 60          # 429 / quota: quotas refill
COOLDOWN_DOWN_S = 30 * 60          # 502/503/504/529/timeout: an outage outlasts a retry
COOLDOWN_ACCESS_S = 6 * 3600       # 401/403/404 / no access to the model: will not change in a minute
COOLDOWN_MAX_S = 6 * 3600
_COOLDOWN: dict = {}               # key -> monotonic time it may be tried first again
_COOL_CLASSES = ("ClaudeSDK", "CodexCLI", "GrokCLI", "AntigravityCLI")

_RE_RETRY_AFTER = re.compile(r"retry[- ]?after\D{0,5}(\d+(?:\.\d+)?)\s*(ms|s|sec|seconds?|m|min|minutes?)?", re.I)
_RE_TRY_AGAIN = re.compile(r"try again in\s*(\d+(?:\.\d+)?)\s*(ms|s|sec|seconds?|m|min|minutes?|h|hours?)", re.I)


def _seconds(num: str, unit: str) -> float:
    n = float(num)
    unit = (unit or "s").lower()
    if unit == "ms":
        return n / 1000
    if unit.startswith("h"):
        return n * 3600
    if unit.startswith("m"):
        return n * 60
    return n


def cooldown_for(error) -> float:
    """Seconds to rest a link after `error`, 0 when the error says nothing about the link itself
    (a bad prompt, a tool failing). Retry-After / "try again in" wins when the provider states it."""
    text = str(error or "")
    low = text.lower()
    for rx in (_RE_RETRY_AFTER, _RE_TRY_AGAIN):
        m = rx.search(text)
        if m:
            return min(COOLDOWN_MAX_S, max(1.0, _seconds(m.group(1), m.group(2) or "s")))
    if re.search(r"\b(401|403|404)\b", low) or any(k in low for k in (
            "not found", "does not exist", "no access", "permission", "unauthorized", "forbidden",
            "invalid api key", "invalid_api_key", "model_not_found", "mất đăng nhập", "not logged in")):
        return COOLDOWN_ACCESS_S
    if re.search(r"\b429\b", low) or any(k in low for k in (
            "quota", "rate limit", "rate_limit", "usage limit", "too many requests", "hết lượt", "hết hạn mức",
            "resource_exhausted")):
        return COOLDOWN_QUOTA_S
    if re.search(r"\b(502|503|504|529)\b", low) or any(k in low for k in (
            "timeout", "timed out", "deadline", "overloaded", "unavailable", "bad gateway", "không phản hồi")):
        return COOLDOWN_DOWN_S
    return 0.0


def _cool_key(e) -> str:
    """provider:model(:account) for API links, class:model for CLI links; "" for anything else (never rests)."""
    prov = getattr(e, "provider", None)
    if not (isinstance(prov, str) and prov):
        prov = getattr(e, "account_provider", None)   # a plan engine pointed at one account (plan_accounts, 0.353.0)
    kind = prov if isinstance(prov, str) and prov else (type(e).__name__ if type(e).__name__ in _COOL_CLASSES else "")
    acc = getattr(e, "account_id", "") if isinstance(getattr(e, "account_id", ""), str) else ""
    return (f"{kind}:{getattr(e, 'model', '') or ''}" + (f":{acc}" if acc else "")) if kind else ""


def _resting(e, now: float) -> float:
    """Monotonic time a resting link wakes, 0 when it is not resting."""
    key = _cool_key(e)
    until = _COOLDOWN.get(key, 0.0) if key else 0.0
    return until if until > now else 0.0


class _FallbackChain:
    """Router việc nền: CHUỖI engine thử lần lượt, mắt trước chết LÚC CHẠY (hết quota, CLI
    lỗi, stream câm không final, không sẵn sàng) thì chạy lại nguyên prompt bằng mắt sau.
    Chuỗi điển hình: engine phụ user chọn → Claude → OpenRouter model free mạnh nhất.
    Triết lý của swap() vốn là "việc nền phải chạy chứ không chết" nhưng trước đây chỉ đỡ
    được lỗi lúc DỰNG (thiếu key/CLI); lỗi lúc chạy thì chết thật - ca thật: Codex "You've
    hit your usage limit" làm nhắc hẹn chỉ báo ⚠ về Telegram rồi thôi.
    Trong suốt với nơi gọi: đọc attr → mắt đầu; GÁN attr (max_wall_s...) → đặt cho MỌI mắt
    để engine dự phòng cũng nhận giới hạn/cấu hình mà caller đặt sau swap()."""

    def __init__(self, engines):
        object.__setattr__(self, "_engines", [e for e in (engines or []) if e is not None])

    def _all(self):
        return object.__getattribute__(self, "_engines")

    def __getattr__(self, name):
        return getattr(self._all()[0], name)

    def __setattr__(self, name, value):
        for e in self._all():
            try:
                setattr(e, name, value)
            except Exception:
                pass

    def is_available(self) -> bool:
        for e in self._all():
            try:
                if e.is_available():
                    return True
            except Exception:
                pass
        return False

    def reset_session(self):
        for e in self._all():
            try:
                e.reset_session()
            except Exception:
                pass

    @staticmethod
    def _name(e) -> str:
        return getattr(e, "provider", None) or type(e).__name__

    def _order(self):
        """Links in chain order, resting links moved to the end (soonest to wake first)."""
        now = time.monotonic()
        engines = self._all()
        awake = [e for e in engines if not _resting(e, now)]
        resting = sorted((e for e in engines if _resting(e, now)), key=lambda e: _resting(e, now))
        for e in resting:
            print(f"[aux router] {self._name(e)} đang nghỉ thêm {int(_resting(e, now) - now)} giây sau lỗi "
                  "lần trước: thử sau cùng.", file=sys.stderr)
        return awake + resting

    @staticmethod
    def _rest(e, error) -> None:
        key, secs = _cool_key(e), cooldown_for(error)
        if key and secs:
            _COOLDOWN[key] = time.monotonic() + secs
            # A quota error on one API key rests that ACCOUNT for chat too (model_routing), so the next chat turn and
            # the next job start on key 2 instead of paying for the same dead key again.
            acc = getattr(e, "account_id", "")
            plan = getattr(e, "account_provider", None)
            if isinstance(plan, str) and plan and secs != COOLDOWN_QUOTA_S:
                # A plan account rests for chat on quota only: a model this job asked for that the plan lacks, or the
                # service being down, says nothing about the account (0.355.0).
                return
            if isinstance(acc, str) and acc:
                # Plan engines (Codex, Grok, Claude) carry `account_provider`; API engines carry `provider` (0.353.0).
                model_routing.mark_rest(getattr(e, "account_provider", None) or getattr(e, "provider", ""), acc,
                                        seconds=secs)

    async def query(self, prompt: str):
        fail = "chuỗi engine việc nền rỗng"
        dau = ""      # lỗi của mắt xích ĐẦU TIÊN thật sự chạy - thường là lỗi có nghĩa nhất
        for e in self._order():
            try:
                if not e.is_available():
                    fail = f"{self._name(e)} không sẵn sàng"
                    continue
                got_final, got_error, acted = False, None, False
                async for ev in e.query(prompt):
                    t = (ev or {}).get("type")
                    if t == "tool_call":
                        acted = True
                    if t == "error":
                        got_error = ev.get("content") or f"{self._name(e)} trả error"
                        # Hub bắt buộc không lên: mọi mắt sau lấy tool qua đúng hub đó, chạy tiếp
                        # là chạy mù rồi báo xong giả. Dừng cả chuỗi, trả nguyên lỗi
                        # (claude_cli.codex_error_text đã đặt lý do lên đầu).
                        if _hub_bat_buoc_hong(got_error):
                            print(f"[aux router] {self._name(e)}: hub bắt buộc không lên - dừng chuỗi, "
                                  "không thử mắt kế tiếp.", file=sys.stderr)
                            # Giữ cả lỗi của mắt TRƯỚC (vd Claude hết lượt gói): tasks._het_luot
                            # đọc nó để hoãn tới giờ gói mở lại. Lý do hub đứng đầu vì ô lỗi bị cắt.
                            yield {"type": "error",
                                   "content": got_error + (f" | {dau}" if dau else "")}
                            return
                        break
                    # Engine CLI chưa đăng nhập trả một FINAL ngắn kiểu "Not logged in ·
                    # Please run /login" chứ không phải error - nuốt nó lại và coi là mắt
                    # chết, kẻo chuỗi dự phòng tưởng thành công rồi dừng (xem chú thích
                    # ở _AUTH_FINAL_PATTERNS).
                    # Cuộc đua làm mới token Claude: phiên KHÔNG mất, nhưng lượt này hỏng và
                    # việc nền không tự gửi lại được -> vẫn phải nhảy sang mắt kế tiếp. Đọc CỜ
                    # chứ không khớp chữ: câu người đọc đã được viết lại cho dễ hiểu.
                    if t == "final" and ev.get("dua_token"):
                        got_error = (f"{self._name(e)} trùng lúc làm mới phiên đăng nhập "
                                     "(hai lượt cùng dùng một tài khoản)")
                        break
                    if t == "final" and final_loi_dang_nhap(ev.get("content")):
                        got_error = (f"{self._name(e)} mất đăng nhập: "
                                     + (ev.get("content") or "").strip()[:200])
                        break
                    # Claude Code ends a failed turn (out of plan usage, API 429) with a final flagged
                    # `is_error` whose text is the provider's message. Passing it on as a success kept
                    # the next link from ever running, and the job was reported done with that message
                    # as its result. Codex says the same thing as an `error` event; treat both alike.
                    if t == "final" and ev.get("is_error"):
                        got_error = ((ev.get("content") or "").strip()[:300]
                                     or f"{self._name(e)} kết thúc lỗi ({ev.get('subtype') or 'final'})")
                        break
                    yield ev
                    if t == "final":
                        got_final = True
                if got_final:
                    _COOLDOWN.pop(_cool_key(e), None)            # it works again: no more rest
                    return                                       # mắt này chạy ngon → xong
                fail = got_error or f"{self._name(e)} kết thúc mà không có final"
                self._rest(e, fail)
                if acted:
                    # 0.350.0 (spec 2.7): this link already called a tool before it broke. Running the prompt again on
                    # another engine could send the message or post the article twice, so the chain stops here and
                    # says why. This is what lets `full` jobs have a fallback chain at all.
                    print(f"[aux router] {self._name(e)} hỏng SAU khi đã gọi công cụ - dừng, không chạy lại "
                          "bằng engine khác.", file=sys.stderr)
                    yield {"type": "error", "content": str(fail) + (f" | {dau}" if dau and dau != str(fail) else "")}
                    return
            except Exception as exc:
                fail = f"{self._name(e)}: {type(exc).__name__}: {exc}"
                self._rest(e, fail)
            print(f"[aux router] {self._name(e)} lỗi → thử mắt xích kế tiếp. Lý do: {str(fail)[:300]}",
                  file=sys.stderr)
            dau = dau or str(fail)
        # Hết chuỗi: trả CẢ lỗi đầu lẫn lỗi cuối. Chỉ trả lỗi cuối ("openrouter không sẵn sàng")
        # là câu "hết lượt gói Claude" của mắt đầu bị nuốt, và hàng đợi việc không nhận ra để hoãn
        # tới giờ gói mở lại (tasks._het_luot đọc câu này).
        noi = str(fail) if (not dau or dau == str(fail)) else f"{dau} | {fail}"
        yield {"type": "error", "content": noi}


def _build_api(spec, claude_cli_obj, mode, tag):
    return _ApiAuxEngine(
        provider=spec["provider"],
        model=spec.get("model") or "",
        system_prompt=getattr(claude_cli_obj, "system_prompt", None),
        vault_root=getattr(claude_cli_obj, "javis_vault", None),
        mode=mode or getattr(claude_cli_obj, "javis_mode", None) or "full",
        tag=tag or getattr(claude_cli_obj, "tag", "aux"),
    )


def _build_codex(spec, claude_cli_obj, mode, tag, codex_profile=None):
    from claude_cli import CodexCLI, codex_sandbox_cho_mode
    cc = CodexCLI(cwd=getattr(claude_cli_obj, "cwd", None),
                  tag=tag or getattr(claude_cli_obj, "tag", "aux"),
                  model=spec.get("model") or None,
                  instructions=getattr(claude_cli_obj, "system_prompt", None))
    # Codex không có allowlist per-call như Claude → chặn ở tầng sandbox của chính nó.
    # `codex_sandbox_cho_mode` còn đọc cờ JAVIS_CODEX_SANDBOX: trong Docker, bubblewrap không
    # chạy nổi nên rào đó không phải "chặt hơn" mà là "chết hẳn", và cờ là đường thoát.
    cc.sandbox = codex_sandbox_cho_mode(mode or getattr(claude_cli_obj, "javis_mode", None) or "full")
    cc.vault_root = getattr(claude_cli_obj, "javis_vault", None)   # ảnh Codex vẽ về đúng brain
    if codex_profile:
        try:
            cc.profile = codex_profile()   # profile javis = thấy MCP của Javis (POS, connector...)
        except Exception as e:
            print(f"[aux codex profile] {e}", file=sys.stderr)
    try:
        import mcp_hub
        mcp_hub.dat_codex_vault(cc.extra_config, getattr(claude_cli_obj, "javis_vault", None))
        # The job's own level, not the profile's `full` (see mcp_hub.dat_codex_mode).
        mcp_hub.dat_codex_mode(cc.extra_config,
                               mode or getattr(claude_cli_obj, "javis_mode", None) or "full")
    except Exception as e:
        print(f"[aux codex vault] {e}", file=sys.stderr)
    # Việc nền theo lịch: hub bắt buộc, không app ChatGPT - xem mcp_hub.CODEX_REQUIRED_KEY. Chat
    # không đi qua hàm này, còn workflow Codex dựng engine riêng (main._workflow_agent_helpers),
    # nên chỉ các làn trong la_viec_nen_theo_lich đổi hành vi.
    try:
        if (cc.profile and la_viec_nen_theo_lich(cc.tag)
                and bool(cfgmod.read_settings().get("mcp", {}).get("hub", True))):
            import mcp_hub
            mcp_hub.dat_codex_hub_bat_buoc(cc.extra_config)
            mcp_hub.dat_codex_tat_app(cc.extra_config)
    except Exception as e:
        print(f"[aux codex hub] {e}", file=sys.stderr)
    # Fast mode (0.164.0): background runs never get the bolt. Force the normal tier, or a
    # config.toml with service_tier = "priority" would make every scheduled run fast.
    cc.extra_config[:] = [x for x in cc.extra_config if not str(x).startswith("service_tier=")]
    cc.extra_config.append('service_tier="default"')
    return cc


# Nhãn lượt của việc nền THEO LỊCH: nhắc hẹn, loop, Kanban ("dispatch:<id>:<hậu tố>"). The "-main" suffix came from
# the pre-0.350.0 main-brain link; it is still accepted so old tags read the same.
_TAG_VIEC_NEN_THEO_LICH = ("reminder", "loop")


def la_viec_nen_theo_lich(tag) -> bool:
    t = str(tag or "").strip()
    if t.endswith("-main"):
        t = t[:-len("-main")]
    return t in _TAG_VIEC_NEN_THEO_LICH or t.startswith("dispatch:")


def _hub_bat_buoc_hong(text) -> bool:
    try:
        from claude_cli import codex_loi_hub_bat_buoc
        return codex_loi_hub_bat_buoc(text)
    except Exception:
        return False


def _build_grok(spec, claude_cli_obj, mode, tag):
    """Engine việc nền/agent chạy bằng Grok Build CLI (`grok`).

    Mức quyền xuống thẳng cờ `--deny` của CLI chứ không phải một lời hứa trong prompt, và
    `grok_cli.permission_cho_mode` fail-closed (mode lạ về nấc chặt nhất). Cùng vai với sandbox
    của Codex - lớp chặn tool NATIVE, còn rào tiền/đơn/đăng bài vẫn nằm ở MCP Hub.

    Entry MCP dựng bằng `grok_cli.hub_entry()` chứ KHÔNG viết tay: Grok đọc khoá `url`, còn
    `agy` đọc `serverUrl`. Chép nhầm khoá giữa hai engine là không có lấy một tool nào của
    Javis mà không một câu lỗi nào - đúng thứ đã xảy ra với `agy` mấy bản liền.
    """
    import grok_cli as _g
    muc = mode or getattr(claude_cli_obj, "javis_mode", None) or "full"
    gc = _g.GrokCLI(cwd=getattr(claude_cli_obj, "cwd", None),
                    tag=tag or getattr(claude_cli_obj, "tag", "aux"),
                    model=spec.get("model") or None,
                    instructions=getattr(claude_cli_obj, "system_prompt", None))
    gc.mode = muc
    vault = getattr(claude_cli_obj, "javis_vault", None) or getattr(claude_cli_obj, "cwd", None)
    if vault:
        try:
            import mcp_hub
            hub = None
            if bool(cfgmod.read_settings().get("mcp", {}).get("hub", True)):
                hub = _g.hub_entry(mcp_hub.hub_url(),
                                   {"Authorization": f"Bearer {mcp_hub.hub_token()}",
                                    "X-Javis-Mode": muc, "X-Javis-Vault": str(vault)})
            _g.ghi_mcp_settings(vault, hub)
        except Exception as e:
            print(f"[aux grok mcp] {e}", file=sys.stderr)
    return gc


def _build_antigravity(spec, claude_cli_obj, mode, tag):
    """Engine việc nền/agent chạy bằng Antigravity CLI (`agy`).

    Khác `_build_grok` ở hai chỗ, và cả hai đều là lý do phải viết riêng thay vì dùng chung:

    - **Mức quyền yếu hơn thật.** `agy` KHÔNG có cờ chặn per-tool như `--deny` của Grok;
      `suggest` ở đây chỉ được siết bằng `--sandbox` cộng lời dặn trong prompt. Xem
      `antigravity_cli.co_quyen_cho_mode` - nó nói thẳng chuyện này, và rào tiền/đơn/đăng bài
      vẫn nằm ở MCP Hub chứ không ở CLI.
    - **Hình dạng entry MCP khác hẳn.** `agy` đọc khoá `serverUrl`, Grok đọc `url`. Chép nhầm
      khoá là engine chạy trơn tru mà không có lấy một tool nào của Javis, không một tiếng
      động - đúng thứ đã xảy ra mấy bản liền. Nên dựng entry bằng `antigravity_cli.hub_entry()`
      chứ không viết tay.
    """
    import antigravity_cli as _a
    muc = mode or getattr(claude_cli_obj, "javis_mode", None) or "full"
    ac = _a.AntigravityCLI(cwd=getattr(claude_cli_obj, "cwd", None),
                           tag=tag or getattr(claude_cli_obj, "tag", "aux"),
                           model=spec.get("model") or None,
                           instructions=getattr(claude_cli_obj, "system_prompt", None))
    ac.mode = muc
    vault = getattr(claude_cli_obj, "javis_vault", None) or getattr(claude_cli_obj, "cwd", None)
    if vault:
        try:
            import mcp_hub
            hub = None
            if bool(cfgmod.read_settings().get("mcp", {}).get("hub", True)):
                hub = _a.hub_entry(mcp_hub.hub_url(),
                                   {"Authorization": f"Bearer {mcp_hub.hub_token()}",
                                    "X-Javis-Mode": muc, "X-Javis-Vault": str(vault)})
            _a.ghi_mcp_settings(vault, hub)
        except Exception as e:
            print(f"[aux antigravity mcp] {e}", file=sys.stderr)
    return ac


def apply(deps, cli, mode: str = None, tag: str = None):
    """Dùng ở các nơi chạy nền sau khi đã dựng xong engine Claude.

    deps.aux_swap được main tiêm; thiếu nó (unit test dựng deps tối giản) thì rơi về cách
    cũ - chỉ đặt model - nên test cũ không phải sửa và hành vi không đổi.
    """
    fn = getattr(deps, "aux_swap", None)
    if fn:
        return fn(cli, mode=mode, tag=tag)
    getter = getattr(deps, "aux_model", None)
    if getter:
        cli.model = getter() or None
    return cli


def strip_tools(engine, base):
    """Make a swapped engine (or fallback chain) TEXT-ONLY: no hub, no MCP of any kind (0.77.0).

    For turns whose prompt carries untrusted text (the group reply judge, its self-review): a stranger can write
    instructions into a group message, and the prompt fences them as data, but the only real wall is that the
    model has nothing to call. `base` is the sandboxed Claude engine the caller built before `swap` (allowed_tools
    set, empty MCP file, empty cwd), so it is safe as is. Every other link is stripped or DROPPED:

    - API engines: `no_tools` skips `discover_all`.
    - Codex: no `-p` profile (that is where the hub entry lives) and `mcp_servers={}` wipes any MCP the user's
      own config.toml declares.
    - Grok: its MCP file lives in the working directory (the empty sandbox folder), so the hub entry is removed.
    - Antigravity (`agy`) and anything unknown: dropped. `agy` reads MCP servers from the shared HOME file, which
      also serves the owner's own chats, so there is no way to take the hub away for one turn.

    Nothing left: fall back to `base` (a dead Claude login then fails the turn, which the judge treats as silence).
    """
    try:
        links = list(engine._all()) if isinstance(engine, _FallbackChain) else [engine]
    except Exception:       # noqa: BLE001
        return base
    keep = []
    for e in links:
        if e is base:
            keep.append(e)
            continue
        try:
            if isinstance(e, _ApiAuxEngine):
                e.no_tools = True
                keep.append(e)
                continue
            from claude_cli import CodexCLI
            if isinstance(e, CodexCLI):
                e.profile = None
                e.extra_config = [c for c in (e.extra_config or []) if not str(c).startswith("mcp_servers")]
                e.extra_config.append("mcp_servers={}")
                keep.append(e)
                continue
            import grok_cli
            if isinstance(e, grok_cli.GrokCLI):
                grok_cli.ghi_mcp_settings(e.cwd, None)
                keep.append(e)
                continue
        except Exception as ex:      # noqa: BLE001 - cannot prove it is tool-free: drop it
            print(f"[aux strip_tools] bỏ {type(e).__name__}: {type(ex).__name__}: {ex}", file=sys.stderr)
            continue
        print(f"[aux strip_tools] bỏ {type(e).__name__}: không tắt được công cụ cho riêng lượt này", file=sys.stderr)
    if not keep:
        return base
    return keep[0] if len(keep) == 1 else _FallbackChain(keep)


def _cli_effort(level: str):
    """Background effort for a Claude Code link. xhigh/ultra go to "high": an older `claude` rejects the top two values,
    and a background job is never worth a failed run. "off" sends nothing (spec 2.3.4)."""
    return {"low": "low", "medium": "medium", "high": "high", "xhigh": "high", "ultra": "high"}.get(level or "")


def _plan_accounts_for(prov: str, settings) -> list:
    """Usable accounts of a plan card that holds more than one (plan_accounts, 0.353.0); [] = run as before."""
    try:
        import plan_accounts
        s = settings if settings is not None else cfgmod.read_settings()
        m = s.get("model", {}) or {}
        if prov == CLAUDE:
            import claude_auth
            if claude_auth.che_do(s) == claude_auth.API_KEY:
                return []                   # Claude on an API key: no plan account to rotate
        if not plan_accounts.has_extra(m, prov):
            return []
        # None usable: the first switched-on account still runs (and reports its quota), never one switched off.
        fb = plan_accounts.fallback(m, prov)
        return plan_accounts.usable(m, prov) or ([fb] if fb else [])
    except Exception as e:  # noqa: BLE001 - account rotation must never cost the step
        print(f"[aux] tài khoản {prov}: {type(e).__name__}: {e}", file=sys.stderr)
        return []


def _per_account(prov: str, first, settings, more) -> list:
    """One link per usable account: `first` takes account 1 of the list, `more()` builds each further link."""
    accs = _plan_accounts_for(prov, settings)
    if not accs:
        return [first]
    import plan_accounts
    out = [plan_accounts.use(first, prov, accs[0]["id"])]
    for a in accs[1:]:
        out.append(plan_accounts.use(more(), prov, a["id"]))
    return out


def _links_for_step(step: dict, cli, mode, tag, codex_profile, settings, claude_used: list) -> list:
    """Engines for one step of the background order. An API card gives one link per usable account (key 1, key 2...);
    a plan card gives one link; a step that cannot run on this machine gives none."""
    prov = step.get("provider") or CLAUDE
    sp = {"provider": prov, "model": step.get("model") or ""}
    level = step.get("reasoning") or "off"
    if prov == CLAUDE:
        # The caller's engine carries the allowlist, MCP and sandbox decisions, so the first Claude link IS that engine
        # (resonance and strip_tools recognise it by identity). A second Claude step is a shallow copy with its own model.
        import copy
        e = cli if not claude_used else copy.copy(cli)
        claude_used.append(e)
        e.model = sp["model"] or None
        eff = _cli_effort(level)
        if eff and hasattr(e, "effort"):
            e.effort = eff

        def _more():
            c = copy.copy(e)
            claude_used.append(c)
            return c
        return _per_account(CLAUDE, e, settings, _more)
    ok, why = availability(sp, settings)
    if not ok:
        print(f"[aux] {why} → bỏ bước {prov}.", file=sys.stderr)
        return []
    try:
        if prov == CODEX:
            return _per_account(CODEX, _build_codex(sp, cli, mode, tag, codex_profile), settings,
                                lambda: _build_codex(sp, cli, mode, tag, codex_profile))
        if prov == GROK_CLI:
            return _per_account(GROK_CLI, _build_grok(sp, cli, mode, tag), settings,
                                lambda: _build_grok(sp, cli, mode, tag))
        if prov == ANTIGRAVITY:
            return [_build_antigravity(sp, cli, mode, tag)]
        if prov in API_PROVIDERS:
            s = settings if settings is not None else cfgmod.read_settings()
            m = s.get("model", {}) or {}
            field = _KEY_FIELD.get(prov, "")
            accs = ([] if prov in ("openai-compat", "anthropic-compat", "ollama-local")
                    else model_routing.usable_accounts(m, prov, field))
            mk = lambda key="", acc="": _ApiAuxEngine(   # noqa: E731
                provider=prov, model=sp["model"], system_prompt=getattr(cli, "system_prompt", None),
                vault_root=getattr(cli, "javis_vault", None),
                mode=mode or getattr(cli, "javis_mode", None) or "full",
                tag=tag or getattr(cli, "tag", "aux"), reasoning=level if level in model_routing.LEVELS else "off",
                api_key=key, account_id=acc)
            if len(accs) > 1:
                return [mk(a["key"], a["id"]) for a in accs]
            if accs:
                return [mk(accs[0]["key"], accs[0]["id"])]
            return [mk()]
    except Exception as e:  # noqa: BLE001 - one broken step must not cost the others
        print(f"[aux router] không dựng được bước {prov}: {type(e).__name__}: {e}", file=sys.stderr)
    return []


def swap(cli, mode: str = None, tag: str = None, spec: dict = None,
         codex_profile=None, settings: dict = None):
    """Engine Claude đã dựng -> ROUTER việc nền (0.350.0, docs/dev/2026-10-model-routing-spec.md part 2.4).

    Order: the background model (or `spec`, e.g. an assistant's own model) -> fallback 1, 2, ... of the Models page
    usage order, each on its provider's starting config -> MAIN last, on its starting config. An API card contributes
    one link per usable key. The chain is the same at every permission level: a link that already called a tool and
    then broke stops the chain (_FallbackChain), so nothing is sent twice. Before 0.350.0 the chain was fixed
    (Claude, the main brain, OpenRouter free) and `full` jobs had none.

    Broken config still keeps background work alive: no buildable link at all returns the caller's Claude engine.
    """
    try:
        s = settings if settings is not None else cfgmod.read_settings()
        m = s.get("model", {}) or {}
        sp = spec if spec is not None else read_spec(s)
        first = {"provider": sp.get("provider") or CLAUDE, "model": sp.get("model") or "",
                 "reasoning": (sp.get("reasoning") if sp.get("reasoning") in model_routing.LEVELS
                               else model_routing.background_spec(m)["reasoning"] if spec is None else "off")}
        # Settings not yet moved to 0.350.0 have no stored order: MAIN plus every API card holding a key, which is
        # exactly what the migration will store.
        conn = None
        if not model_routing.stored_order(m):
            conn = [model_routing.main_provider(m)] + [p for p in API_PROVIDERS if api_key_for(p, s)]
        chain, claude_used = [], []
        # A plan's quota belongs to the account, not the model: a second Claude step after Claude ran dry would only
        # cost another failed call, so each plan provider appears once.
        for st in model_routing.background_chain(m, conn, first=first, once=(CLAUDE, CODEX, GROK_CLI, ANTIGRAVITY)):
            chain.extend(_links_for_step(st, cli, mode, tag, codex_profile, s, claude_used))
        if not chain:
            return cli
        return chain[0] if len(chain) == 1 else _FallbackChain(chain)
    except Exception as e:
        print(f"[aux swap] {e} → giữ engine Claude.", file=sys.stderr)
    return cli
