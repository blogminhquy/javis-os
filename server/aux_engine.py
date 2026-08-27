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
- gemini-cli: Gemini CLI chạy bằng đăng nhập Google. Cũng agent thật (tool file + MCP hub qua
  .gemini/settings.json trong brain). Mức quyền ánh xạ thẳng vào --approval-mode của nó:
  suggest -> plan (chỉ đọc), auto -> auto_edit, full -> yolo.
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

CLAUDE = "anthropic-cli"
CODEX = "openai-oauth"
GEMINI_CLI = "gemini-cli"
ANTIGRAVITY = "antigravity-cli"
API_PROVIDERS = ("openrouter", "openai", "gemini", "groq", "anthropic-api", "ollama")

# provider -> tên trường chứa API key trong settings["model"]
_KEY_FIELD = {
    "openrouter": "openrouter_key",
    "openai": "openai_api_key",
    "gemini": "gemini_api_key",
    "groq": "groq_api_key",
    "anthropic-api": "anthropic_api_key",
    # Ollama ở đây là bản CLOUD (ollama.com) - có API key như mọi nhà API khác. Bản chạy
    # máy nhà cố ý không đấu (xem chú thích `ollama` trong config.py): nó đòi thêm một ô
    # địa chỉ, mà phần đông người dùng Javis chạy trên VPS nơi "localhost" là container.
    "ollama": "ollama_key",
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
    return (s.get("model", {}) or {}).get(field) or ""


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
    if prov == GEMINI_CLI:
        try:
            import gemini_cli as _g
            st = _g.auth_status()
            if not st.get("connected"):
                return False, st.get("error") or "Gemini CLI chưa sẵn sàng."
        except Exception:
            return False, "Không kiểm tra được Gemini CLI."
        return True, ""
    if prov == ANTIGRAVITY:
        try:
            import antigravity_cli as _a
            if not _a.find_antigravity_cli():
                return False, "Chưa cài Antigravity CLI (`agy`) trên máy chạy Javis."
            st = _a.auth_status()
            if not st.get("connected"):
                return False, st.get("error") or "Antigravity CLI chưa đăng nhập Google."
        except Exception:
            return False, "Không kiểm tra được Antigravity CLI."
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
                 mode="full", tag="aux", reasoning="off"):
        self.provider = provider
        self.model = model
        self.system_prompt = system_prompt
        self.vault_root = vault_root
        self.javis_mode = mode
        self.tag = tag
        self.reasoning = reasoning
        self.session_id = None      # engine API không có phiên nối tiếp - giữ cho đủ hợp đồng

    def is_available(self) -> bool:
        return bool(api_key_for(self.provider))

    def reset_session(self):
        self.session_id = None

    async def query(self, prompt: str):
        import engine as eng
        import mcp_hub

        key = api_key_for(self.provider)
        if not key:
            yield {"type": "error", "content": f"Chưa có API key cho {self.provider}."}
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
                yield {"type": "error", "content": "Không chọn được model free OpenRouter."}
                return

        tools, route = [], {}
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
                  "anthropic-api": eng.anthropic_chat_with_mcp,
                  "ollama": eng.ollama_chat_with_mcp}[self.provider]
            stream = fn(key, self.model, messages, self.reasoning, tools, route)
        else:
            fn = {"openrouter": eng.openrouter_stream, "openai": eng.openai_stream,
                  "gemini": eng.gemini_stream, "groq": eng.groq_stream,
                  "anthropic-api": eng.anthropic_stream,
                  "ollama": eng.ollama_stream}[self.provider]
            stream = fn(key, self.model, messages, self.reasoning)

        # Đường API sinh "text" theo mảnh; việc nền chỉ đọc "final" nên gom lại rồi phát MỘT lần.
        buf = []
        async for ev in stream:
            t = ev.get("type")
            if t == "text":
                buf.append(ev.get("content") or "")
            elif t in ("tool_call", "error", "usage"):
                if t == "usage":
                    self._ghi_muc_dung(ev)
                yield ev
                if t == "error":
                    return
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
                               ev.get("input", 0), ev.get("output", 0), ev.get("cost", 0) or 0)
        except Exception as e:  # noqa: BLE001
            print(f"[aux usage] {type(e).__name__}: {e}", file=sys.stderr)


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

    async def query(self, prompt: str):
        fail = "chuỗi engine việc nền rỗng"
        for e in self._all():
            try:
                if not e.is_available():
                    fail = f"{self._name(e)} không sẵn sàng"
                    continue
                got_final, got_error = False, None
                async for ev in e.query(prompt):
                    t = (ev or {}).get("type")
                    if t == "error":
                        got_error = ev.get("content") or f"{self._name(e)} trả error"
                        break
                    # Engine CLI chưa đăng nhập trả một FINAL ngắn kiểu "Not logged in ·
                    # Please run /login" chứ không phải error - nuốt nó lại và coi là mắt
                    # chết, kẻo chuỗi dự phòng tưởng thành công rồi dừng (xem chú thích
                    # ở _AUTH_FINAL_PATTERNS).
                    if t == "final" and final_loi_dang_nhap(ev.get("content")):
                        got_error = (f"{self._name(e)} mất đăng nhập: "
                                     + (ev.get("content") or "").strip()[:200])
                        break
                    yield ev
                    if t == "final":
                        got_final = True
                if got_final:
                    return                                       # mắt này chạy ngon → xong
                fail = got_error or f"{self._name(e)} kết thúc mà không có final"
            except Exception as exc:
                fail = f"{self._name(e)}: {type(exc).__name__}: {exc}"
            print(f"[aux router] {self._name(e)} lỗi → thử mắt xích kế tiếp. Lý do: {str(fail)[:300]}",
                  file=sys.stderr)
        yield {"type": "error", "content": str(fail)}            # hết chuỗi → trả lỗi thật


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
    if codex_profile:
        try:
            cc.profile = codex_profile()   # profile javis = thấy MCP của Javis (POS, connector...)
        except Exception as e:
            print(f"[aux codex profile] {e}", file=sys.stderr)
    try:
        import mcp_hub
        override = mcp_hub.codex_vault_override(getattr(claude_cli_obj, "javis_vault", None))
        if override:
            cc.extra_config.append(override)
    except Exception as e:
        print(f"[aux codex vault] {e}", file=sys.stderr)
    return cc


def _build_gemini(spec, claude_cli_obj, mode, tag):
    """Engine việc nền chạy bằng Gemini CLI.

    Mức quyền của Javis đi thẳng vào `--approval-mode` của CLI chứ không phải một lời hứa
    trong prompt: `plan` là chế độ CHỈ ĐỌC do chính CLI cưỡng chế. Cùng vai với sandbox của
    Codex - lớp chặn thật sự duy nhất, vì Gemini CLI cũng không có allowlist per-call.
    """
    import gemini_cli as _g
    muc = mode or getattr(claude_cli_obj, "javis_mode", None) or "full"
    gc = _g.GeminiCLI(cwd=getattr(claude_cli_obj, "cwd", None),
                      tag=tag or getattr(claude_cli_obj, "tag", "aux"),
                      model=spec.get("model") or None,
                      instructions=getattr(claude_cli_obj, "system_prompt", None))
    gc.approval_mode = _g.approval_cho_mode(muc)
    vault = getattr(claude_cli_obj, "javis_vault", None) or getattr(claude_cli_obj, "cwd", None)
    if vault:
        try:
            import mcp_hub
            hub = None
            if bool(cfgmod.read_settings().get("mcp", {}).get("hub", True)):
                hub = {"httpUrl": mcp_hub.hub_url(),
                       "headers": {"Authorization": f"Bearer {mcp_hub.hub_token()}",
                                   "X-Javis-Mode": muc, "X-Javis-Vault": str(vault)},
                       "trust": True, "timeout": 20000}
            _g.ghi_mcp_settings(vault, hub)
        except Exception as e:
            print(f"[aux gemini mcp] {e}", file=sys.stderr)
    return gc


def _build_antigravity(spec, claude_cli_obj, mode, tag):
    """Engine việc nền/agent chạy bằng Antigravity CLI (`agy`).

    Khác `_build_gemini` ở hai chỗ, và cả hai đều là lý do phải viết riêng thay vì dùng chung:

    - **Mức quyền yếu hơn thật.** `agy` KHÔNG có nấc chỉ-đọc do CLI cưỡng chế (Gemini có
      `--approval-mode plan`); `suggest` ở đây chỉ được siết bằng `--sandbox` cộng lời dặn
      trong prompt. Xem `antigravity_cli.co_quyen_cho_mode` - nó nói thẳng chuyện này, và
      rào tiền/đơn/đăng bài vẫn nằm ở MCP Hub chứ không ở CLI.
    - **Hình dạng entry MCP khác hẳn.** `agy` đọc khoá `serverUrl`; `httpUrl` (khoá của Gemini
      CLI) bị nó bỏ qua không một tiếng động - đúng thứ đã làm bộ não này chạy mấy bản liền mà
      không có lấy một tool nào của Javis. Nên dựng entry bằng `antigravity_cli.hub_entry()`
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


def _main_fallback_engine(cli, mode, tag, settings, exclude, codex_profile=None):
    """Mắt dự phòng dựng từ BỘ NÃO CHÍNH của người dùng, hoặc None nếu không dựng được.

    exclude = tập provider đã có mặt trong chuỗi (aux + Claude) - trùng thì khỏi thêm.
    Provider không có builder nền (ollama, antigravity-cli) trả None, chuỗi còn lại lo.
    """
    sp = main_spec(settings)
    prov = sp.get("provider") or ""
    if not prov or prov == CLAUDE or prov in (exclude or set()):
        return None
    ok, _why = availability(sp, settings)
    if not ok:
        return None
    t = (tag or getattr(cli, "tag", "aux")) + "-main"
    try:
        if prov == CODEX:
            return _build_codex(sp, cli, mode, t, codex_profile)
        if prov == GEMINI_CLI:
            return _build_gemini(sp, cli, mode, t)
        if prov in API_PROVIDERS:
            return _build_api(sp, cli, mode, t)
    except Exception as e:
        print(f"[aux router] không dựng được mắt não-chính ({prov}): {e}", file=sys.stderr)
    return None


def _co_mat_orfree(chain) -> bool:
    """Chuỗi đã chứa một mắt OpenRouter model trống (= tự chọn free) chưa - có rồi thì
    mắt or_free cuối trùng hệt, khỏi thêm."""
    return any(getattr(e, "provider", "") == "openrouter"
               and not (getattr(e, "model", "") or "").strip() for e in chain)


def _openrouter_free_engine(cli, mode, tag, settings):
    """Mắt xích CUỐI của router: OpenRouter model free (model '' = tự chọn free mạnh nhất
    lúc chạy, xem _ApiAuxEngine.query). Chưa có key OpenRouter thì không có mắt này."""
    if not api_key_for("openrouter", settings):
        return None
    return _ApiAuxEngine(
        provider="openrouter",
        model="",
        system_prompt=getattr(cli, "system_prompt", None),
        vault_root=getattr(cli, "javis_vault", None),
        mode=mode or getattr(cli, "javis_mode", None) or "full",
        tag=(tag or getattr(cli, "tag", "aux")) + "-orfree",
    )


def swap(cli, mode: str = None, tag: str = None, spec: dict = None,
         codex_profile=None, settings: dict = None):
    """Engine Claude đã dựng -> ROUTER việc nền theo model phụ người dùng chọn.

    Chuỗi fallback (mắt trước chết lúc chạy thì mắt sau tiếp quản, xem _FallbackChain):
      engine phụ user chọn → Claude → BỘ NÃO CHÍNH đang chat (nếu khác hai mắt trước)
      → OpenRouter model free mạnh nhất (nếu có key).
    Mắt não-chính là để máy KHÔNG đăng nhập Claude (chỉ chạy Gemini/OpenAI/Groq...) vẫn
    tự học và chạy việc nền được bằng đúng bộ não người dùng đang dùng, thay vì chết lặng
    với "Not logged in". Mặc định Claude + không dựng được mắt nào khác thì trả NGUYÊN
    engine Claude như xưa; hỏng cấu hình kiểu gì việc nền cũng phải chạy được chứ không chết.
    """
    try:
        sp = spec if spec is not None else read_spec(settings)
        prov = sp.get("provider", CLAUDE)
        # MỨC FULL KHÔNG CÓ CHUỖI DỰ PHÒNG. Đây là quyết định có chủ ý, không phải bỏ sót.
        #
        # Việc ở mức full thường là hành động RA NGOÀI: đăng bài, gửi tin, tạo đơn, đặt lịch.
        # Ba lý do khiến rơi engine ở đây tệ hơn là chết hẳn:
        #   1. Engine dự phòng (API) không có tool NATIVE, nên không gọi được connector ambient
        #      của tài khoản Claude. Việc cần Google Drive/Gmail sẽ dừng giữa chừng.
        #   2. Model không biết mình vừa bị đổi engine, nên nó suy ra một lý do nghe hợp lý mà
        #      sai - ca thật: nhắc hẹn đăng Fanpage báo "phiên này bị chặn quyền" trong khi
        #      user đã bật Toàn quyền, làm người ta đi tìm nhầm chỗ.
        #   3. Mắt trước có thể đã làm xong MỘT PHẦN việc (đăng được 1 trong 3 bài) rồi mới
        #      gãy. Chạy lại nguyên prompt bằng engine khác là đăng lại từ đầu.
        # Thà dừng và nói đúng "Claude gãy vì X" để chủ xử lý, hơn là làm nửa vời trong im lặng.
        if str(mode or "").strip().lower() == "full":
            if prov == CLAUDE:
                cli.model = sp.get("model") or None
                return cli
            ok, why = availability(sp, settings)
            if not ok:
                print(f"[aux] {why} → việc full tạm dùng lại Claude.", file=sys.stderr)
                return cli
            if prov == CODEX:
                return _build_codex(sp, cli, mode, tag, codex_profile)
            if prov == GEMINI_CLI:
                return _build_gemini(sp, cli, mode, tag)
            if prov == ANTIGRAVITY:
                return _build_antigravity(sp, cli, mode, tag)
            if prov in API_PROVIDERS:
                return _build_api(sp, cli, mode, tag)
            return cli
        if prov == CLAUDE:
            cli.model = sp.get("model") or None
            # Máy có thể CHƯA đăng nhập Claude (người dùng chỉ chạy Gemini/OpenAI...):
            # thêm bộ não CHÍNH làm mắt kế để việc nền đi theo đúng bộ não đang sống.
            chain = [cli]
            mn = _main_fallback_engine(cli, mode, tag, settings, {CLAUDE}, codex_profile)
            if mn:
                chain.append(mn)
            or_free = _openrouter_free_engine(cli, mode, tag, settings)
            if or_free and not _co_mat_orfree(chain):
                chain.append(or_free)
            return _FallbackChain(chain) if len(chain) > 1 else cli
        ok, why = availability(sp, settings)
        if not ok:
            print(f"[aux] {why} → việc nền tạm dùng lại Claude.", file=sys.stderr)
            return cli
        if prov == CODEX:
            primary = _build_codex(sp, cli, mode, tag, codex_profile)
        elif prov == GEMINI_CLI:
            primary = _build_gemini(sp, cli, mode, tag)
        elif prov == ANTIGRAVITY:
            primary = _build_antigravity(sp, cli, mode, tag)
        elif prov in API_PROVIDERS:
            primary = _build_api(sp, cli, mode, tag)
        else:
            return cli
        chain = [primary, cli]
        mn = _main_fallback_engine(cli, mode, tag, settings, {CLAUDE, prov}, codex_profile)
        if mn:
            chain.append(mn)
        or_free = _openrouter_free_engine(cli, mode, tag, settings)
        # Chuỗi đã có mắt openrouter model trống (tự chọn free) thì or_free trùng hệt → khỏi thêm.
        if or_free and not _co_mat_orfree(chain):
            chain.append(or_free)
        return _FallbackChain(chain)
    except Exception as e:
        print(f"[aux swap] {e} → giữ engine Claude.", file=sys.stderr)
    return cli
