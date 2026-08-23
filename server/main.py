"""
Javis OS - Backend
Kiến trúc: Voice (browser) ⇄ FastAPI WebSocket ⇄ Claude Code CLI subprocess

Javis KHÔNG gọi Anthropic API trực tiếp. Mọi reasoning + tool calling đi qua
`claude` CLI đã cài trên máy → tự kế thừa MCP, skills, auth.
"""
import localefmt   # múi giờ theo cấu hình, thay UTC+7 nhúng cứng
import os
import json
import math
import asyncio
import glob
import hashlib
# `sys` phải nằm ở ĐẦU file: rải rác trong file có chỗ `import sys` cục bộ, nhưng cũng có chỗ
# dùng sys.stderr mà quên import - và vì chúng nằm trong nhánh `except` (đường ghi log lỗi),
# chúng chỉ nổ đúng lúc đã có sự cố khác, biến một lỗi lẽ ra chỉ cần ghi log thành NameError
# phá cả luồng. Import một lần ở đây thì mọi chỗ dùng đều an toàn.
import sys
import uuid
from pathlib import Path
import re
import secrets
import shutil
import time
import types as _types   # object tạm cho _apply_antigravity_hub ở endpoint kiểm tra
import yaml
import fastyaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, UploadFile, File, Form, Request, Body, Header
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse, Response
# edge_tts CỐ TÌNH không import ở đây mà nạp lười trong _tts_edge và /tts/voices.
# Nó chiếm 944ms trong 2.263ms nạp main (41%), và kéo theo cả chuỗi aiohttp 212ms vào
# đường khởi động, trong khi TTS là tính năng TUỲ CHỌN mà đa số phiên không đụng tới.
# Khởi động chậm không chỉ khó chịu: trên VPS nó ăn vào cửa sổ healthcheck lúc deploy.
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from claude_cli import CodexCLI, claude_engine, find_claude_cli, find_codex_cli, cancel_all, _empty_mcp_file, auth_status as claude_auth_status, auth_login as claude_auth_login, auth_logout as claude_auth_logout, auth_login_ui_start, auth_login_ui_code, mcp_native_add, mcp_native_remove, mcp_native_status, mcp_open_auth_terminal, mcp_native_list, codex_mcp_native_list, codex_mcp_native_add, codex_mcp_native_remove, codex_mcp_native_status, codex_mcp_open_login_terminal
import config as cfgmod
import update_state
_ver_tuple = update_state.ver_tuple
_ver_newer = update_state.ver_newer
_read_update_state = update_state.read_state
_write_update_state = update_state.write_state
_record_boot_version = update_state.record_boot_version
_update_outcome = update_state.update_outcome
import git_brain
import engine
import openai_oauth
import claude_models   # model Claude LIVE cho provider anthropic-cli (hỏi bằng API key, nếu có)
import gemini_cli      # bộ não thứ 9: Gemini CLI (Google đã ngắt hạng cá nhân 18/06/2026)
import winproc         # chạy lệnh con câm lặng trên Windows (không nháy console đen)
import md_repair       # chữa file .md bị vòng lưu WYSIWYG của bản <= 0.33.3 làm hỏng
import terminal        # tab Code: pseudo-terminal thật trong dashboard (pty trên POSIX, ống trên Windows)
import antigravity_cli   # bộ não thứ 10: Antigravity CLI (`agy`) - bản Google chỉ định thay Gemini CLI
import gemini_oauth    # đăng nhập Google ngay trên dashboard rồi bắc cầu token sang Gemini CLI
import totp            # xác thực 2 lớp (TOTP) cho cổng đăng nhập - thuần toán, không đụng cấu hình
import claude_auth     # gói Claude Code xác thực bằng gì: phiên subscription hay API key
import aux_engine   # engine việc nền: Claude / Codex / API rẻ
import mcp_store
import mcp_client
import mcp_catalog
import mcp_hub
import connect_health   # sức khoẻ kết nối: vòng check nền + phân loại lỗi tiếng người
import cred_exchange   # đổi credential hộ user (vd App Password -> Google master token) khi đấu
import plugins_host   # hệ PLUGIN: thư mục Python thả vào, tự thêm tool/hook cho mọi engine qua hub
import web_security   # chống CSRF-to-localhost + DNS-rebinding cho web API cục bộ
import image_gen      # tạo ảnh bằng gói ChatGPT (OAuth) - Codex Responses + tool image_generation
import media_gc       # dọn vùng cache media (attachments/ + inbox/) theo hạn tuổi + trần dung lượng
import stt            # nghe tin thoại (Whisper qua Groq) -> chữ, cho kênh Telegram/Zalo
import zalo_login
import oauth_mcp
import system_sync   # tầng năng lực HỆ THỐNG (skill/loop mặc định) - update theo phiên bản app
import skill_router   # nguồn chân lý khám phá skill (canonical <brain>/skills) dùng chung mọi engine
import skill_usage     # telemetry: đếm skill nào THẬT SỰ được dùng qua javis_use_skill (tín hiệu DƯƠNG một chiều)
import share_bundle   # xuất/nhập gói agent/skill/workflow (.zip) để chia sẻ giữa brain/người dùng
import usage_store   # đếm token/chi phí Javis tự đo (đa nhà cung cấp)
import usage_index   # dashboard token: index log thô Claude+Codex + query summary/insights
import usage_parsers as up_parsers   # bảng giá + khớp model, dùng chung với indexer
import usage_saving   # tiết kiệm đối chứng ngược, mốc sự kiện, dự báo, ngân sách
import context_runtime   # Phase 0-8: trace + Registry/Resolver/Compiler + canary paths
import capability_registry   # Phase 2: registry dẫn xuất, không phải nguồn sự thật
import capability_resolver   # Phase 3: resolver deterministic chỉ chạy shadow
import context_compiler      # Phase 4: capsule + quota preflight + quality gate shadow
import fast_path_runtime     # Phase 5: dashboard API canary, hard quota + single model call
import evidence_store        # Phase 6: encrypted provenance/artifact store
import capability_executor   # Phase 6: one-use read lease + schema validation
import readonly_path_runtime # Phase 6: exact-schema, two-round read-only canary
import readonly_orchestrator # Phase 7: checkpointed multi-round read-only DAG
import adaptive_context_runtime # Phase 8: state + sourced memory + lazy skill canaries
import agent_runtime           # Phase 11: agent = workflow có quyền replan trong quyền đã cấp
import limit_learner          # học hạn mức từ chính lỗi nhà cung cấp trả về
import quota_scheduler        # sổ cái TPM dùng chung (Việc 6)
import model_limits           # hạn mức GỢI Ý theo provider, để khai quota profile cho canary
import model_router           # Phase 12: chọn model theo từng bước, lọc năng lực trước
import workflow_graph          # Phase 10: workflow -> capability graph (thuần dữ liệu)
import workflow_runtime        # Phase 10: chạy graph có checkpoint/resume
import write_path_runtime    # Phase 9: write có xác nhận, idempotency và reconcile
from telegram_bot import TelegramBot, parse_chat_ids as tg_parse_ids
import zalo_bot   # kênh Zalo Bot của chủ (API chính thức) - cùng khế ước với TelegramBot
import channel_context   # metadata kênh + gom file trả về kênh chat (port gateway hermes-agent)
import lang as lang_mod   # chốt ngôn ngữ trả lời cho một lượt
import lang_registry      # sổ đăng ký: mọi thứ về một ngôn ngữ nằm đúng một chỗ
import background_status  # việc nền còn sống của một khung chat + bắt lời hứa "xong em báo"
import chatbot_log       # nhật ký hội thoại khách + thống kê câu bot trả lời không nổi
import chatbot_runtime   # bộ giám sát Bot chuyên trách (mỗi bot một poller Telegram)
import chatbot_store     # kho bản ghi bot + token qua secrets_store
from sessions import get_store   # kho phiên hội thoại (sqlite + fts5): list/resume/search
import compaction   # nén hội thoại dài cho engine API (tóm tắt phần cũ thay vì cắt bỏ)
from chat_runtime import ChatRuntime

app = FastAPI(title="Javis OS")
_CHAT_RUNTIME = ChatRuntime()
_CONTEXT_RUNTIME = context_runtime.get_runtime()
_CAPABILITY_REGISTRY = capability_registry.get_registry()
_CAPABILITY_RESOLVER = capability_resolver.get_resolver()
_CONTEXT_COMPILER = context_compiler.get_compiler()
_QUALITY_GATE = context_compiler.get_quality_gate()
_FAST_PATH = fast_path_runtime.FastPathCanary(
    _CAPABILITY_REGISTRY, _CAPABILITY_RESOLVER, _CONTEXT_COMPILER,
    _CONTEXT_RUNTIME, cfgmod.read_settings,
)
_EVIDENCE_STORE = evidence_store.EvidenceStore(_CONTEXT_RUNTIME)
_CAPABILITY_EXECUTOR = capability_executor.CapabilityExecutor(
    _CAPABILITY_REGISTRY, _CONTEXT_RUNTIME, _EVIDENCE_STORE,
)
_READONLY_PATH = None
_READONLY_ORCHESTRATOR = None
_ADAPTIVE_CONTEXT = None
_WRITE_PATH = None
# Tham số write ĐÃ ĐƯỢC DUYỆT, giữ trong RAM theo invocation_id. Cố ý KHÔNG persist:
# raw arguments không được vào runtime store (bất biến privacy từ Phase 0). Hệ quả có
# chủ đích: khởi động lại tiến trình là mất phần duyệt, và lượt xác nhận fail-closed
# thay vì chạy một hành động ghi mà Javis không còn đọc lại được tham số.
_WRITE_PENDING_ARGS: dict[str, dict] = {}
_WRITE_PENDING_ARGS_MAX = 64
_REGISTRY_SHADOW_TASKS = set()
# CORS KHÔNG dùng '*' nữa: dashboard cùng-origin (không cần CORS). Chỉ mở cross-origin cho localhost
# (tiện dev). Chống trang web độc ĐỌC API qua trình duyệt; phần chống GHI/CSRF ở _csrf_guard bên dưới.
app.add_middleware(CORSMiddleware,
                   allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$",
                   allow_methods=["*"], allow_headers=["*"])

# Đường dẫn KHÔNG cần đăng nhập. CHỈ các auth endpoint công khai (status/login/setup) -
# KHÔNG để cả prefix /auth public vì /auth/disable, /auth/logout phải yêu cầu đăng nhập.
_AUTH_PUBLIC_PREFIX = ("/static", "/health")
# /brand-logo: hiện trên màn đăng nhập (trước session). /tls-check: Caddy gọi (không đăng nhập được).
_AUTH_PUBLIC_EXACT = ("/", "/favicon.ico", "/auth/status", "/auth/login", "/auth/setup",
                      "/brand-logo", "/tls-check",
                      # /hub/mcp: Claude CLI/Codex gọi bằng Bearer hub_token riêng (không có cookie).
                      # /connect/oauth/callback: browser redirect từ provider OAuth về.
                      "/hub/mcp", "/connect/oauth/callback")
# Endpoint CHỈ-LOCALHOST: agent (Claude CLI chạy cùng máy/container) curl được mà không cần
# cookie đăng nhập; request từ ngoài (qua Traefik/Caddy/LAN) đến từ IP khác loopback → vẫn bị chặn.
# /reminders/cancel đi cùng nhóm với /reminders (TẠO nhắc): huỷ là thao tác YẾU HƠN tạo, nên
# miễn cùng mức là nhất quán chứ không nới rào - thiếu nó thì javis_schedule (plugin in-process,
# gọi localhost không cookie) huỷ nhắc hẹn LUÔN lỗi 401 khi đã bật mật khẩu (gate_active()=True).
# /reminders/update cùng nhóm: SỬA lịch cũng là thao tác yếu hơn TẠO, và javis_schedule
# (op=update) gọi từ chính máy này khi user nói "đổi giờ việc đó sang 8h" - thiếu nó thì sửa lịch
# bằng chat trả 401 câm. /reminders/delete CỐ Ý không có ở đây: xoá hẳn thì để dashboard (có
# session) làm, chat chỉ cần huỷ.
_AUTH_LOCAL_EXACT = ("/telegram/send-file", "/reminders", "/reminders/cancel", "/reminders/update")


@app.middleware("http")
async def _csrf_guard(request: Request, call_next):
    """Chống CSRF-to-localhost + DNS-rebinding (xem web_security.py). Chạy TRƯỚC auth guard.
    Không đụng client không-trình-duyệt (Claude CLI/Codex/curl không gửi Origin) và cùng-origin."""
    d = web_security.csrf_decision(request.method, request.headers.get("host", ""),
                                   request.headers.get("origin"), cfgmod.gate_active())
    if d:
        return JSONResponse({"error": d[1], "blocked": "web_security"}, status_code=d[0])
    # GET có tác dụng phụ (chạy workflow, duyệt node ghi): Origin không đủ, xem SIDE_EFFECT_GET.
    n = web_security.navigation_decision(request.url.path, request.headers.get("sec-fetch-site"))
    if n:
        return JSONResponse({"error": n[1], "blocked": "web_security"}, status_code=n[0])
    return await call_next(request)


@app.middleware("http")
async def _auth_guard(request: Request, call_next):
    """Chặn endpoint khi CẦN đăng nhập (đã đặt mật khẩu HOẶC chạy public) mà chưa có session.
    Khi chạy public (0.0.0.0) lần đầu chưa có mật khẩu → vẫn chặn để ÉP tạo tài khoản trước
    (setup_required), tránh hở dashboard điều khiển Claude full quyền ra Internet."""
    if cfgmod.gate_active():
        path = request.url.path
        client_host = request.client.host if request.client else ""
        public = (path in _AUTH_PUBLIC_EXACT
                  or any(path.startswith(p) for p in _AUTH_PUBLIC_PREFIX)
                  or (path in _AUTH_LOCAL_EXACT and client_host in ("127.0.0.1", "::1")))
        if not public and not cfgmod.valid_session(request.cookies.get("javis_session", "")):
            # Client ngoài trình duyệt (CLI, script, cron) không có cookie. Nhánh token là
            # đường DUY NHẤT của chúng - xem docs/dev/2026-08-cli-spec.md. Đặt SAU nhánh
            # cookie để dashboard không phải đọc file token mỗi request.
            if not _token_ok(request, path):
                return JSONResponse({"error": "unauthorized", "auth_required": True,
                                     "setup_required": not cfgmod.auth_enabled()},
                                    status_code=401)
    return await call_next(request)


def _bearer(request) -> str:
    raw = str(request.headers.get("authorization") or "")
    return raw[7:].strip() if raw[:7].lower() == "bearer " else ""


def _token_ok(request, path: str) -> bool:
    """Request này mang token API hợp lệ cho `path` không.

    Chặn dò trước khi kiểm: IP đã sai quá nhiều thì từ chối thẳng, không cho nó dò tiếp và
    cũng không tốn công băm. Không có header thì im lặng trả False - đó là ca thường của
    trình duyệt chưa đăng nhập, không phải chuyện đáng ghi nhật ký.
    """
    raw = _bearer(request)
    if not raw:
        return False
    ip = request.client.host if request.client else ""
    if cfgmod.token_ip_banned(ip):
        return False
    if cfgmod.verify_api_token(raw, path):
        return True
    cfgmod.note_token_failure(ip, raw[:12])
    return False

DASHBOARD_PATH = Path(__file__).parent.parent / "dashboard"
# Windows/mimetypes không biết .webp -> StaticFiles trả text/plain; khai rõ để logo webp đúng kiểu ảnh.
import mimetypes
mimetypes.add_type("image/webp", ".webp")
app.mount("/static", StaticFiles(directory=str(DASHBOARD_PATH)), name="static")


@app.middleware("http")
async def _static_cache_headers(request: Request, call_next):
    """Asset tĩnh có ?v= (cache-bust theo VERSION, index.html tự gắn) → cho cache 1 năm immutable.
    Không có ?v= thì giữ nguyên (ETag/Last-Modified của StaticFiles vẫn lo revalidate).
    Thiếu header này trình duyệt phải hỏi lại ~27 file JS/CSS mỗi lần mở trang."""
    resp = await call_next(request)
    if request.url.path.startswith("/static/") and request.query_params.get("v"):
        resp.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
    return resp

CLAUDE_MD_PATH = Path(__file__).parent.parent / "CLAUDE.md"
SYSTEM_PROMPT = CLAUDE_MD_PATH.read_text(encoding="utf-8") if CLAUDE_MD_PATH.exists() else None

# Bộ nhớ dài hạn - lưu TRONG vault đang chọn để đi theo vault
MEMORY_SEED = (
    "# Bộ nhớ Javis - Index\n\n"
    "> Chỉ mục bộ nhớ dài hạn của Javis. Mỗi dòng = 1 ký ức, trỏ tới file trong `facts/`.\n"
    "> Nội dung file này được nạp vào đầu mỗi câu hỏi để Javis nhớ ngữ cảnh.\n\n"
    "_(Chưa có ký ức nào. Javis sẽ học dần sau mỗi hội thoại.)_\n"
)

def _atomic_write_text(path, content: str, encoding: str = "utf-8"):
    """Ghi file nguyên tử: viết ra .tmp cùng thư mục → fsync → os.replace.

    Mặc định write_text() ghi trực tiếp; nếu Javis crash hoặc mất điện
    giữa chừng, file (loop_config.json, automations.json, memory .md...)
    sẽ bị cắt cụt → JSON corrupt / frontmatter hỏng. Pattern port từ
    hermes-agent/utils.py:atomic_replace - bảo đảm reader luôn thấy bản
    cũ hoặc bản mới hoàn chỉnh, không bao giờ thấy bản dở dang.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding=encoding, newline="") as fh:
            fh.write(content)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        os.replace(tmp, p)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        raise


def _brain_memory_dir(brain: str) -> Path:
    """Folder bộ nhớ TRONG brain đang chọn. Cấu trúc mới: <root>/memory; fallback cũ <root>/Memory."""
    base = Path(__file__).parent.parent
    if not brain or brain == "brain":
        root = _default_brain_dir()
    else:
        root = Path(brain) if os.path.isdir(brain) else _default_brain_dir()
    mem = root / "memory"
    if not mem.is_dir() and (root / "Memory").is_dir():
        mem = root / "Memory"   # vault cũ chưa migrate
    try:
        (mem / "facts").mkdir(parents=True, exist_ok=True)
        (mem / "conversations").mkdir(parents=True, exist_ok=True)
        idx = mem / "MEMORY.md"
        if not idx.exists():
            idx.write_text(MEMORY_SEED, encoding="utf-8")
    except Exception as e:
        print(f"[memory dir error] {e}", file=__import__('sys').stderr)
    return mem

# Trần cho chỉ mục bộ nhớ nạp vào MỌI lượt chat. Đo trên brain thật: 87 ký ức = 18.363 ký tự
# (~5,7k token) và tăng tuyến tính theo số ký ức - đúng cái bệnh curator vừa mắc, không có gì
# chặn. Trần này chưa cắt gì hôm nay (18.363 < 20.000), nó biến đường dốc thành đường phẳng.
MEMORY_INDEX_MAX = int(os.getenv("JAVIS_MEMORY_INDEX_MAX", "20000"))
_MEM_ITEM_RE = re.compile(r'^(\s*-\s*\[[^\]]*\]\([^)]*\))\s*[-–—]?\s*(.*)$')


def _fit_memory_index(mem: str, cap: int = None) -> str:
    """Ép chỉ mục bộ nhớ xuống dưới trần mà KHÔNG làm mất ký ức nào cho tới phút chót.

    Hạ dần theo bậc: giữ nguyên -> rút mô tả còn 100 ký tự -> còn 60 -> chỉ còn tiêu đề+link
    -> (cùng lắm) cắt bớt dòng kèm lời chỉ đường. Rút mô tả KHÔNG mất năng lực nhớ: tiêu đề và
    đường dẫn file vẫn còn nguyên, chi tiết đầy đủ vẫn nằm trong Memory/facts/*.md và đọc được
    bất cứ lúc nào. Mất hẳn dòng mới là mất trí nhớ, nên đó là bậc CUỐI.
    """
    cap = cap or MEMORY_INDEX_MAX
    if len(mem) <= cap:
        return mem
    lines = mem.split("\n")

    def rebuild(desc_cap):
        out = []
        for l in lines:
            m = _MEM_ITEM_RE.match(l)
            if not m:
                out.append(l)
                continue
            head, desc = m.group(1), m.group(2).strip()
            if not desc:
                out.append(head)
            elif desc_cap is None:
                out.append(head)
            elif len(desc) <= desc_cap:
                out.append(f"{head} - {desc}")
            else:
                out.append(f"{head} - {desc[:desc_cap].rstrip()}…")
        return "\n".join(out)

    for desc_cap in (100, 60, None):
        got = rebuild(desc_cap)
        if len(got) <= cap:
            note = ("\n\n> (Mô tả trong chỉ mục đã rút gọn cho vừa ngữ cảnh. Chi tiết đầy đủ của "
                    "từng ký ức nằm trong file tương ứng ở Memory/facts/ - cứ đọc khi cần.)")
            return got + note

    # Bậc cuối: buộc phải bỏ bớt dòng. Giữ các dòng ĐẦU (ký ức nền tảng ghi sớm nhất) và nói rõ
    # còn bao nhiêu, kèm đường đọc tiếp - đừng để mất im lặng.
    kept, total = [], 0
    items = 0
    for l in rebuild(None).split("\n"):
        if total + len(l) + 1 > cap - 300:
            break
        kept.append(l)
        total += len(l) + 1
        if _MEM_ITEM_RE.match(l):
            items += 1
    con_lai = sum(1 for l in lines if _MEM_ITEM_RE.match(l)) - items
    return "\n".join(kept) + (
        f"\n\n> (Chỉ mục quá dài nên còn {con_lai} ký ức chưa liệt kê ở đây. "
        "Đọc Memory/MEMORY.md để xem đủ danh sách, và Memory/facts/ để xem chi tiết.)")


def build_system_prompt(brain: str = "brain", include_memory: bool = True,
                        include_skills: bool = True,
                        lang: "lang_mod.LangDecision | str | None" = None) -> str:
    """CLAUDE.md + nạp MEMORY.md của vault đang chọn → Javis luôn nhớ ngữ cảnh."""
    base = CLAUDE_MD_PATH.read_text(encoding="utf-8") if CLAUDE_MD_PATH.exists() else ""
    # Chốt ngôn ngữ NGAY đầu hàm: khối NGÔN NGỮ ở cuối cần nó, mà danh sách skill ở giữa cũng
    # cần (mô tả skill là bề mặt ĐỐI CHIẾU với câu người dùng vừa gõ, nên nó phải cùng thứ
    # tiếng với câu đó thì định tuyến mới sắc).
    _lq = lang if isinstance(lang, lang_mod.LangDecision) else None
    _lma = (_lq.lang if _lq else lang_registry.chuan_hoa(lang or "")) or lang_registry.MAC_DINH
    idx = _brain_memory_dir(brain) / "MEMORY.md"
    mem = ""
    try:
        if idx.exists():
            mem = idx.read_text(encoding="utf-8")
    except Exception:
        mem = ""
    if include_memory and mem.strip():
        base += "\n\n# === BỘ NHỚ DÀI HẠN (nạp sẵn) ===\n" + _fit_memory_index(mem)
    # Đường dẫn lớp Agentic của vault đang làm việc (để Javis tạo agent/workflow/loop qua chat)
    root = _brain_root(brain)
    system_sync.ensure_synced(root)   # brain nào cũng có đủ năng lực hệ thống (1 lần/process, rẻ)
    try:
        # Mirror skills/ → .claude/skills để fork Claude cwd=brain (workflow/loop/learn/lint) nạp
        # native được skill viết giữa phiên (rẻ: cổng chữ ký stat-only bỏ qua nếu cây nguồn
        # không đổi, xem system_sync._mirror_signature - KHÔNG còn so hash nội dung nữa).
        #
        # KHÔNG gắn với include_skills. Cờ đó chỉ nói "có chèn khối ROUTER SKILL vào prompt hay
        # không" - một chuyện về CHỮ. Còn mirror là một tác dụng phụ lên ĐĨA mà Claude Code và
        # Codex dựa vào để tự tìm skill. Gộp hai chuyện làm một thì bật tiết kiệm token cho
        # Claude Code là vô hiệu hoá luôn skill native của nó, mà lỗi đó im lặng hoàn toàn.
        system_sync.mirror_skills(root)
    except Exception:
        pass
    ag, wf = _agents_dir(brain), _workflows_dir(brain)
    lp = Path(root) / "Javis" / "loops"
    sk = _skills_dir(brain)
    base += (
        "\n\n# === LỚP AGENTIC (vault đang làm việc) ===\n"
        f"Vault root: {root}\n"
        f"- AGENT: tạo/sửa tại `{ag}/<slug>.md`\n"
        f"- WORKFLOW: tạo/sửa tại `{wf}/<slug>.md`\n"
        f"- LOOP (nhiệm vụ lặp vô hạn): tạo/sửa tại `{lp}/<slug>.md`\n"
        f"- SKILL: tạo/sửa tại `{sk}/<slug>/SKILL.md` (tự mirror sang .claude/skills cho Claude native)\n"
        "Khi user yêu cầu tạo/sửa agent, workflow hoặc loop qua chat, ghi file .md đúng định dạng "
        "(xem mục 'Tạo/sửa Agent & Workflow qua chat' và 'Điều phối' trong system prompt) bằng "
        "ĐƯỜNG DẪN TUYỆT ĐỐI ở trên. Trang Agents/Workflows/Việc định kỳ sẽ tự nhận file mới."
    )
    # Quét cây skill MỘT lần cho cả hai khối dưới. Trước đây _javis_capability_summary
    # gọi list_skills còn _skill_router_block gọi list_enabled_meta (vốn chỉ là list_skills
    # lọc lại), nên cả cây skill bị đi và parse YAML HAI lần mỗi lượt chat - đo được 18ms
    # mỗi lần trên brain 30 skill. Lỗi thì để None và mỗi khối tự quét như cũ.
    # Quét LUÔN, kể cả khi bỏ khối router. Khối "NĂNG LỰC JAVIS HIỆN CÓ" chỉ ĐẾM skill và
    # liệt kê tên nhóm (vài chục ký tự), nên nó không phải chỗ tốn token; nhưng đưa cho nó một
    # danh sách rỗng thì Javis sẽ tự khai là mình không có skill nào - một câu SAI, và sai theo
    # hướng khiến nó đi tạo lại thứ đã có.
    try:
        _skills = skill_router.list_skills(root, _lma)
    except Exception:
        _skills = None
    try:
        base += _javis_capability_summary(brain, _skills)   # chỉ mục năng lực LIVE (mọi engine biết Javis có gì)
    except Exception:
        pass
    try:
        if include_skills:
            base += _skill_router_block(brain, root, _skills)   # ROUTER SKILL đa-engine: list skill + cách gọi
    except Exception:
        pass
    # Đồng hồ. Cùng một dòng với capsule của đường tiết kiệm (context_compiler.dong_ho), để
    # bật hay tắt tiết kiệm thì Javis vẫn biết bây giờ mấy giờ y như nhau. Model không có
    # đồng hồ, và tool `javis_now` thì không phải đường nào cũng phát tool.
    # Khối NGÔN NGỮ + đồng hồ đi CÙNG NHAU và đi CUỐI, sát chỗ model bắt đầu trả lời.
    # Ngôn ngữ đặt ở cuối vì luật càng gần chỗ sinh chữ thì model càng ít trôi; đồng hồ
    # đi kèm vì tên thứ trong tuần cũng phải theo ngôn ngữ đó.
    base += "\n\n# === BÂY GIỜ ===\n" + context_compiler.dong_ho(lang=_lma)
    base += lang_mod.khoi_ngon_ngu(_lq or lang_mod.LangDecision(_lma, "default", 1.0, True))
    try:
        # 1 dòng MỨC DÙNG để Javis TRẢ LỜI được khi user hỏi "token tiêu bao nhiêu" (chi tiết ở panel).
        _t = usage_store.summary().get("today", {}).get("total", {})
        if _t.get("in") or _t.get("out"):
            _c = f", ~${_t.get('cost', 0):.4f}" if _t.get("cost") else ""
            base += (f"\n\n# === MỨC DÙNG HÔM NAY (Javis tự đo) ===\n"
                     f"{_t.get('in', 0):,} token vào + {_t.get('out', 0):,} token ra qua "
                     f"{_t.get('turns', 0)} lượt{_c}. Đây là token Javis TỰ ĐO, KHÔNG phải hạn mức gói "
                     f"thuê bao (đa số nhà cung cấp không cho lấy hạn mức tài khoản qua API). Chi tiết "
                     f"từng nhà cung cấp ở panel 'Mức dùng' trên dashboard.")
    except Exception:
        pass
    return base


def build_adaptive_source_prompt(brain: str = "brain", include_memory: bool = False,
                                 include_skills: bool = False) -> str:
    """Small Phase 8 base. Context Compiler already owns identity/safety/output contracts.

    Only a source that has not entered its canary is restored here. This intentionally
    does not wrap CLAUDE.md, otherwise lazy memory/skills would save little at first load.
    """
    root = _brain_root(brain)
    ag, wf = _agents_dir(brain), _workflows_dir(brain)
    loops = Path(root) / "Javis" / "loops"
    skills = _skills_dir(brain)
    parts = [
        "# Javis adaptive source contract",
        f"Brain root: {root}",
        "MCP Hub và tool gateway là nguồn capability live. Chỉ gọi tool được cung cấp; "
        "không bịa tool, dữ liệu live hay kết quả hành động.",
        f"Agent files: {ag}/<slug>.md; workflow files: {wf}/<slug>.md; "
        f"loop files: {loops}/<slug>.md; skill files: {skills}/<slug>/SKILL.md.",
    ]
    if include_memory:
        try:
            idx = _brain_memory_dir(brain) / "MEMORY.md"
            memory = idx.read_text(encoding="utf-8") if idx.exists() else ""
        except OSError:
            memory = ""
        if memory.strip():
            parts.append("# Bộ nhớ fallback\n" + _fit_memory_index(memory))
    if include_skills:
        try:
            system_sync.ensure_synced(root)
            system_sync.mirror_skills(root)
            skill_meta = skill_router.list_skills(root)
            parts.append(_skill_router_block(brain, root, skill_meta))
        except Exception:
            # The caller records source fallback through Phase 8 status; empty router
            # remains safer than aborting the existing chat request here.
            pass
    return "\n\n".join(x for x in parts if str(x).strip())

# Redaction patterns - port subset từ hermes-agent/agent/redact.py.
# Bảo vệ log_conversation() khỏi việc ghi vĩnh viễn API key / Telegram bot token /
# JWT vào brain/Memory/conversations/*.md khi user vô tình paste vào chat
# (file này thường bị commit lên git → leak vĩnh viễn).
_SECRET_PREFIX_RE = re.compile(
    r"(?<![A-Za-z0-9_-])("
    r"sk-[A-Za-z0-9_-]{10,}"             # OpenAI / Anthropic (sk-ant) / OpenRouter (sk-or)
    r"|xai-[A-Za-z0-9]{20,}"             # xAI Grok
    r"|gsk_[A-Za-z0-9]{10,}"             # Groq
    r"|ghp_[A-Za-z0-9]{10,}"             # GitHub PAT classic
    r"|gho_[A-Za-z0-9]{10,}"             # GitHub OAuth
    r"|github_pat_[A-Za-z0-9_]{10,}"     # GitHub PAT fine-grained
    r"|AIza[A-Za-z0-9_-]{30,}"           # Google API key
    r"|hf_[A-Za-z0-9]{10,}"              # HuggingFace
    r"|tvly-[A-Za-z0-9]{10,}"            # Tavily
    r")(?![A-Za-z0-9_-])"
)
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_=-]{4,}){0,2}")
_TELEGRAM_BOT_RE = re.compile(r"(bot)?(\d{8,}):([-A-Za-z0-9_]{30,})")
_AUTH_HEADER_RE = re.compile(r"(authorization\s*:\s*)([A-Za-z][\w.+-]*\s+)?(\S+)", re.IGNORECASE)
_DB_CONN_RE = re.compile(
    r"((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^:\s]+:)([^@\s]+)(@)",
    re.IGNORECASE,
)

def _mask_secret(token: str) -> str:
    """head6...tail4 nếu đủ dài, ngược lại '***' để không leak token ngắn."""
    if not token or len(token) < 18:
        return "***"
    return f"{token[:6]}...{token[-4:]}"

def _redact_secrets(text: str) -> str:
    """Mask API key / Telegram token / JWT / DB password trước khi ghi log.

    Cheap substring pre-check trước mỗi regex để không phí cycle trên dòng
    text bình thường (pattern Hermes - ~3x faster trên log thông thường).
    """
    if not text or not isinstance(text, str):
        return text
    if "eyJ" in text:
        text = _JWT_RE.sub(lambda m: _mask_secret(m.group(0)), text)
    if any(s in text for s in ("sk-", "xai-", "gsk_", "ghp_", "gho_", "github_pat_", "AIza", "hf_", "tvly-")):
        text = _SECRET_PREFIX_RE.sub(lambda m: _mask_secret(m.group(1)), text)
    if ":" in text:
        def _redact_tg(m):
            prefix = m.group(1) or ""
            digits = m.group(2)
            return f"{prefix}{digits}:***"
        text = _TELEGRAM_BOT_RE.sub(_redact_tg, text)
    if "uthorization" in text:
        text = _AUTH_HEADER_RE.sub(
            lambda m: m.group(1) + (m.group(2) or "") + _mask_secret(m.group(3)),
            text,
        )
    if "://" in text:
        text = _DB_CONN_RE.sub(lambda m: f"{m.group(1)}***{m.group(3)}", text)
    return text

# Cap kích thước mỗi message khi ghi conversation log - port head/tail truncation
# từ hermes-agent/agent/prompt_builder.py::_truncate_content. conversations/*.md là
# "nguyên liệu để học" (rewire đọc lại) VÀ bị git commit; user paste 1 source dài
# hoặc Javis trả báo cáo dài → log phình, rewire tốn token, repo nặng. Giữ đầu +
# đuôi (đủ ngữ cảnh để học), bỏ giữa, ghi rõ đã cắt bao nhiêu ký tự.
_LOG_MSG_MAX_CHARS = 4000
_LOG_HEAD_CHARS = 2800
_LOG_TAIL_CHARS = 1000

def _clip_for_log(text: str, max_chars: int = _LOG_MSG_MAX_CHARS) -> str:
    if not text or len(text) <= max_chars:
        return text
    head, tail = text[:_LOG_HEAD_CHARS], text[-_LOG_TAIL_CHARS:]
    omitted = len(text) - _LOG_HEAD_CHARS - _LOG_TAIL_CHARS
    marker = (f"\n\n[… cắt {omitted} ký tự giữa - giữ {_LOG_HEAD_CHARS} đầu + "
              f"{_LOG_TAIL_CHARS} cuối / tổng {len(text)} …]\n\n")
    return head + marker + tail

def log_conversation(brain: str, user_msg: str, javis_msg: str):
    """Ghi log hội thoại vào Memory của vault đang chọn (nguyên liệu để học)."""
    try:
        from datetime import datetime, timezone, timedelta
        now = localefmt.now()
        conv = _brain_memory_dir(brain) / "conversations"
        f = conv / f"{now.strftime('%Y-%m-%d')}.md"
        u = _clip_for_log(_redact_secrets(user_msg))
        j = _clip_for_log(_redact_secrets(javis_msg))
        entry = f"\n## {now.strftime('%H:%M')}\n**Bạn:** {u}\n\n**Javis:** {j}\n"
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(entry)
    except Exception as e:
        print(f"[memory log error] {e}", file=__import__('sys').stderr)

# Working directory cho Claude CLI - mặc định là root project Javis OS
# để Claude đọc được CLAUDE.md và truy cập MCPs cài globally
CLAUDE_CWD = os.getenv("CLAUDE_CWD", str(Path(__file__).parent.parent))

# Second Brain - gộp folder brain/ trong project + vault chính
PROJECT_ROOT = Path(__file__).parent.parent
BRAIN_PATH = os.getenv("BRAIN_PATH", str(PROJECT_ROOT / "brain"))   # LEGACY (brain đơn cũ) - chỉ dùng để migrate
# Thư mục CHA chứa MỌI brain - mỗi folder con = 1 second brain. Docker = /brains (mount riêng,
# git-backup được, KHÔNG nằm trong /data state). Local = <project>/brains. Brain mặc định =
# <BRAINS_DIR>/Brain Default. KHÔNG hardcode: cấu hình qua env, chọn brain bất kỳ qua path:.
BRAINS_DIR = os.getenv("BRAINS_DIR", str(PROJECT_ROOT / "brains"))
# Default PORTABLE: vault/ trong repo (tạo lần đầu chạy). Trên VPS/máy khác đặt
# OBSIDIAN_VAULT_PATH trong .env trỏ tới vault thật; để trống = dùng vault/.
OBSIDIAN_VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", str(PROJECT_ROOT / "vault"))
# Nơi lưu file đính kèm từ chat (source cho Second Brain)
SOURCES_PATH = os.getenv("SOURCES_PATH", str(PROJECT_ROOT / "brain" / "01 - Sources"))

# Tạo sẵn thư mục brains/vault để máy mới (VPS sạch) không crash vì thiếu folder.
for _p in (BRAINS_DIR, OBSIDIAN_VAULT_PATH):
    try:
        Path(_p).mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


@app.get("/")
async def root():
    html = (DASHBOARD_PATH / "index.html").read_text(encoding="utf-8")
    # Ép khoá cache của MỌI file .js/.css theo phiên bản app. Trước đây mỗi file có ?v=NN
    # gõ tay, và suốt hàng chục bản không ai nhớ tăng console.js?v=72 nên trình duyệt cứ
    # dùng console.js CŨ trong cache - máy chủ cập nhật thật mà giao diện đóng băng, mọi
    # sửa đổi frontend trở nên vô hình. Gắn phiên bản vào đây thì mỗi lần bump là tự bể cache.
    ver = _app_version() or "0"
    html = re.sub(r'(/static/[\w./-]+\.(?:js|css))\?v=[\w.]+', r'\1?v=' + ver, html)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.post("/stop")
async def stop(payload: dict = Body(None)):
    """Nút Stop: ngắt lệnh CHAT đang chạy, không đụng tới metrics/loop nền.
    Ưu tiên body {"session_id": "..."} để ngắt đúng job, kể cả job thuộc kết nối web cũ.
    Body {"tag": "chat:..."} vẫn được giữ để tương thích; không có cả hai thì ngắt họ 'chat'."""
    data = payload or {}
    session_id = str(data.get("session_id") or "").strip()
    tag = str(data.get("tag") or "").strip()
    if session_id:
        job_tag = _CHAT_RUNTIME.cancel_session(session_id)
        n = cancel_all(job_tag) if job_tag else 0
        return {"ok": True, "cancelled": max(1, n) if job_tag else 0}
    # chỉ chấp nhận tag họ chat - chặn lạm dụng endpoint này để giết loop/workflow nền
    prefix = tag if tag.startswith("chat:") else "chat"
    job_tags = _CHAT_RUNTIME.cancel_matching(prefix)
    n = cancel_all(prefix)
    if job_tags:
        n = max(n, len(job_tags))
    return {"ok": True, "cancelled": n}


# ============================================================
# Auth - 1 tài khoản admin (đặt lần đầu để chặn người lạ khi lên VPS)
# ============================================================
def _session_cookie(resp, token, request=None):
    # KHÔNG tự suy Secure từ X-Forwarded-Proto: nhiều proxy (vd Hostinger port-path http://host/PORT/)
    # phục vụ HTTP → cookie Secure sẽ KHÔNG được trình duyệt gửi lại → KẸT vòng đăng nhập (đăng nhập/
    # tạo tài khoản xong vẫn bị hỏi lại từ đầu). Mặc định TẮT Secure để chạy được cả HTTP lẫn HTTPS.
    # Chỉ bật khi bạn CHẮC CHẮN HTTPS đầu-cuối: đặt env JAVIS_SECURE_COOKIE=1.
    secure = os.getenv("JAVIS_SECURE_COOKIE", "").strip().lower() in ("1", "true", "yes", "on")
    # HTTPS thật qua TÊN MIỀN RIÊNG (Caddy On-Demand TLS): Host khớp custom domain → chắc chắn đi
    # qua Caddy = HTTPS đầu-cuối → bật Secure. An toàn: KHÔNG suy từ X-Forwarded-Proto, và không
    # ảnh hưởng bản localhost/Hostinger (Host khác custom domain → giữ nguyên như cũ).
    if not secure and request is not None:
        try:
            host = (request.headers.get("host", "") or "").split(":")[0].strip().lower()
            custom = (cfgmod.read_settings().get("domain", {}) or {}).get("custom", "").strip().lower()
            if custom and host == custom:
                secure = True
        except Exception:
            pass
    resp.set_cookie("javis_session", token, httponly=True, samesite="lax",
                    secure=secure, max_age=30 * 86400, path="/")
    return resp


def _env_bat(ten: str) -> bool:
    """Biến môi trường có đang bật không (1/true/yes/on). Dùng cho cờ gợi ý, không phải rào."""
    return (os.getenv(ten, "") or "").strip().lower() in ("1", "true", "yes", "on")


@app.get("/auth/status")
async def auth_status(request: Request):
    cfg = cfgmod.read_settings()
    enabled = cfgmod.auth_enabled(cfg)
    require = cfgmod.require_login()
    has_session = cfgmod.valid_session(request.cookies.get("javis_session", ""))
    # authed: có session thật; HOẶC bản local không bắt buộc login + chưa đặt mật khẩu (giữ UX cũ).
    authed = has_session or (not enabled and not require)
    return {"needs_setup": not enabled, "auth_required": enabled or require,
            "require_login": require, "authed": authed,
            # 2FA lộ ra ở đây là CỐ Ý và không phải rò rỉ: màn đăng nhập cần biết có hỏi ô mã
            # hay không, mà việc "tài khoản này có 2FA" thì kẻ tấn công cũng biết ngay sau lần
            # nhập mật khẩu đầu tiên. Số mã khôi phục còn lại thì chỉ trả khi ĐÃ đăng nhập.
            "totp_enabled": cfgmod.totp_enabled(cfg),
            # 2FA bật trong file mà secret không giải mã được (mất/đổi .secret_key). Lộ ra
            # cùng lý lẽ với totp_enabled: sau lần nhập mật khẩu đầu thì kẻ tấn công cũng
            # tự biết, còn CHỦ thì cần biết NGAY để khỏi tưởng 2FA "tự tắt".
            "totp_broken": cfgmod.totp_hong(cfg),
            "totp_recovery_left": (cfgmod.totp_recovery_left(cfg) if authed else None),
            # install.sh có thể ghi JAVIS_SETUP_2FA=1 vào .env khi người cài chọn bật 2FA.
            # Đây chỉ là LỜI NHẮC cho giao diện mở sẵn màn bật, không phải một cơ chế bảo mật.
            "totp_suggested": (_env_bat("JAVIS_SETUP_2FA") and not cfgmod.totp_enabled(cfg)),
            "username": (cfg.get("auth", {}).get("username", "") if authed else "")}


@app.post("/auth/setup")
async def auth_setup(request: Request, username: str = Form(...), password: str = Form(...),
                     setup_token: str = Form("")):
    cfg = cfgmod.read_settings()
    if cfgmod.auth_enabled(cfg):
        return JSONResponse({"ok": False, "error": "Đã có tài khoản - hãy đăng nhập."}, status_code=400)
    # PUBLIC: chống kẻ chỉ-có-URL chiếm admin lần đầu → bắt buộc MÃ THIẾT LẬP (in trong log server).
    if cfgmod.setup_token_required() and not cfgmod.check_setup_token(setup_token):
        return JSONResponse({"ok": False, "error": "Sai hoặc thiếu MÃ THIẾT LẬP - xem mã trong log/terminal của server."}, status_code=403)
    if len(password) < 8:
        return JSONResponse({"ok": False, "error": "Mật khẩu tối thiểu 8 ký tự"}, status_code=400)
    h, salt = cfgmod.hash_password(password)
    cfg["auth"] = {"username": username.strip() or "admin", "password_hash": h, "salt": salt}
    cfgmod.write_settings(cfg)
    cfgmod.clear_setup_token()
    return _session_cookie(JSONResponse({"ok": True}), cfgmod.new_session(), request)


# Rate-limit đăng nhập (chống brute-force) - đếm theo IP, khoá tạm sau N lần sai.
_LOGIN_FAILS = {}        # ip -> [fail_count, locked_until_ts]
_LOGIN_MAX_FAILS = 8
_LOGIN_LOCK_SEC = 300


def _login_locked(ip):
    rec = _LOGIN_FAILS.get(ip)
    return bool(rec) and rec[1] > time.time()


def _login_fail(ip):
    rec = _LOGIN_FAILS.get(ip) or [0, 0.0]
    rec[0] += 1
    if rec[0] >= _LOGIN_MAX_FAILS:
        rec[1] = time.time() + _LOGIN_LOCK_SEC
        rec[0] = 0
    _LOGIN_FAILS[ip] = rec


@app.post("/auth/login")
async def auth_login(request: Request, username: str = Form(...), password: str = Form(...),
                     code: str = Form("")):
    """Đăng nhập. `code` chỉ cần khi đã bật 2FA - nhận CẢ mã 6 số lẫn mã khôi phục.

    Thứ tự kiểm CÓ CHỦ Ý: mật khẩu trước, mã sau. Đảo lại là biến ô mã thành một máy dò xem
    tài khoản nào đã bật 2FA, cho người còn chưa biết mật khẩu.
    """
    ip = request.client.host if request.client else "?"
    if _login_locked(ip):
        return JSONResponse({"ok": False, "error": "Quá nhiều lần sai - thử lại sau ít phút."}, status_code=429)
    cfg = cfgmod.read_settings()
    if not cfgmod.auth_enabled(cfg):
        return {"ok": True, "note": "auth chưa bật"}
    if username.strip() != cfg["auth"].get("username") or not cfgmod.verify_password(password, cfg):
        _login_fail(ip)
        await asyncio.sleep(0.5)   # làm chậm brute-force online
        return JSONResponse({"ok": False, "error": "Sai tài khoản hoặc mật khẩu"}, status_code=401)
    # totp_hong: 2FA bật trong file nhưng secret không giải mã được (mất .secret_key).
    # Vẫn PHẢI hỏi mã (fail-closed) - chỉ mã khôi phục qua được vì nó băm, không mã hoá.
    # Trước 0.35.6 nhánh này fail-open: totp_enabled trả False nên cổng thôi hỏi mã luôn,
    # tức 2FA âm thầm biến mất đúng lúc chủ tin là nó đang bật.
    _tfa_hong = cfgmod.totp_hong(cfg)
    if cfgmod.totp_enabled(cfg) or _tfa_hong:
        ma = (code or "").strip()
        if not ma:
            # 401 kèm needs_2fa để giao diện hiện ô mã. KHÔNG tính là một lần sai: người dùng
            # chưa gõ gì cả, tính vào hạn mức là tự khoá chính chủ sau vài lần mở màn đăng nhập.
            return JSONResponse({"ok": False, "needs_2fa": True,
                                 "error": ("Máy chủ không giải mã được khoá 2FA - nhập MÃ KHÔI PHỤC "
                                           "để vào." if _tfa_hong else "Nhập mã xác thực 2 lớp.")},
                                status_code=401)
        buoc = totp.kiem(cfgmod.totp_secret(cfg), ma,
                         buoc_da_dung=cfgmod.totp_last_step(cfg))
        if buoc is not None:
            cfgmod.totp_ghi_buoc(buoc)
        elif cfgmod.totp_dung_ma_khoi_phuc(ma):
            con = cfgmod.totp_recovery_left()
            print(f"[auth] đăng nhập bằng MÃ KHÔI PHỤC, còn {con} mã", file=__import__('sys').stderr)
        else:
            _login_fail(ip)
            await asyncio.sleep(0.5)
            return JSONResponse({"ok": False, "needs_2fa": True,
                                 "error": ("Khoá 2FA trên máy chủ không giải mã được (file "
                                           ".secret_key đổi/mất?) nên mã 6 số KHÔNG dùng được - "
                                           "chỉ MÃ KHÔI PHỤC vào được. Mất cả mã khôi phục thì "
                                           "SSH vào server xoá khối auth.totp trong "
                                           "settings.json." if _tfa_hong
                                           else "Mã xác thực không đúng hoặc đã dùng rồi.")},
                                status_code=401)
    _LOGIN_FAILS.pop(ip, None)
    return _session_cookie(JSONResponse({"ok": True}), cfgmod.new_session(), request)


# ---- Xác thực 2 lớp: bật / xác nhận / tắt ----
# MỌI endpoint dưới đây đòi SESSION trình duyệt, không nhận token API. Cùng lý do với
# /auth/tokens: cho token đổi được cách đăng nhập thì một token rò ra là kẻ cầm nó tự gắn 2FA
# của mình vào rồi khoá chính chủ ra ngoài.
def _doi_phien_that(request: Request):
    if cfgmod.gate_active() and not cfgmod.valid_session(request.cookies.get("javis_session", "")):
        return JSONResponse({"ok": False, "error": "Thao tác này phải đăng nhập bằng trình duyệt."},
                            status_code=403)
    return None


def _ten_hien_thi(cfg=None) -> str:
    """Tên NGƯỜI để hiện trong app Authenticator, sau tên workspace: "Javis OS: Minh Quý".

    Thứ tự ưu tiên có lý do: `USER_NAME` là tên người dùng tự đặt cho chính mình, còn
    `auth.username` là tên ĐĂNG NHẬP - thường là "admin", đúng về kỹ thuật nhưng vô nghĩa khi
    nằm trong danh sách chục tài khoản 2FA trên điện thoại.

    Bỏ qua giá trị mặc định "Bạn" của env: nó là chỗ giữ chỗ, không phải tên ai cả.
    """
    cfg = cfg if cfg is not None else cfgmod.read_settings()
    ten = (os.getenv("USER_NAME", "") or "").strip()
    if ten and ten.lower() not in ("bạn", "ban", "you", "user"):
        return ten
    return (cfg.get("auth", {}) or {}).get("username") or "admin"


# Secret ĐANG CHỜ xác nhận, giữ trong RAM chứ không ghi settings. Ghi xuống đĩa trước khi
# người dùng chứng minh app của họ sinh đúng mã là để lại một secret nửa vời trong file cấu
# hình; restart giữa chừng thì nó nằm đó mãi mà chẳng ai dùng.
_TOTP_CHO = {}          # {"secret": str, "ts": float}
_TOTP_CHO_TTL = 15 * 60


@app.post("/auth/2fa/start")
async def auth_2fa_start(request: Request):
    """Sinh secret MỚI (chưa bật) + QR để quét. Gọi lại là sinh cái khác, cái cũ bỏ đi."""
    if (loi := _doi_phien_that(request)) is not None:
        return loi
    cfg = cfgmod.read_settings()
    if cfgmod.totp_enabled(cfg):
        return JSONResponse({"ok": False, "error": "2FA đang bật rồi - tắt trước nếu muốn đổi."},
                            status_code=400)
    secret = totp.sinh_secret()
    _TOTP_CHO.clear()
    _TOTP_CHO.update(secret=secret, ts=time.time())
    uri = totp.otpauth_uri(secret, _ten_hien_thi(cfg),
                           cfg.get("workspace_name") or "Javis OS")
    return {"ok": True, "secret": secret, "uri": uri, "qr_svg": totp.qr_svg(uri)}


@app.post("/auth/2fa/enable")
async def auth_2fa_enable(request: Request, code: str = Form(...)):
    """Xác nhận bằng một mã đúng rồi mới BẬT. Trả mã khôi phục đúng MỘT lần."""
    if (loi := _doi_phien_that(request)) is not None:
        return loi
    cho = dict(_TOTP_CHO)
    if not cho.get("secret") or time.time() - float(cho.get("ts") or 0) > _TOTP_CHO_TTL:
        return JSONResponse({"ok": False, "error": "Phiên bật 2FA đã hết hạn - bấm Bật lại."},
                            status_code=400)
    buoc = totp.kiem(cho["secret"], code)
    if buoc is None:
        return JSONResponse({"ok": False, "error": "Mã không đúng. Kiểm tra giờ trên điện thoại "
                                                   "rồi nhập mã đang hiện."}, status_code=400)
    ma_khoi_phuc = totp.sinh_ma_khoi_phuc()
    cfgmod.totp_set(secret=cho["secret"], enabled=True, recovery=ma_khoi_phuc, last_step=buoc)
    _TOTP_CHO.clear()
    return {"ok": True, "recovery": ma_khoi_phuc}


@app.post("/auth/2fa/disable")
async def auth_2fa_disable(request: Request, password: str = Form(...), code: str = Form("")):
    """Tắt 2FA. Đòi mật khẩu VÀ một mã đúng (hoặc mã khôi phục).

    Đòi cả hai vì đây là thao tác HẠ bảo mật: ai đó mượn được máy đang mở sẵn dashboard mà tắt
    được 2FA chỉ bằng một cú bấm thì lớp thứ hai coi như không có.
    """
    if (loi := _doi_phien_that(request)) is not None:
        return loi
    cfg = cfgmod.read_settings()
    if not cfgmod.totp_enabled(cfg):
        return {"ok": True, "note": "2FA vốn đã tắt"}
    if not cfgmod.verify_password(password, cfg):
        return JSONResponse({"ok": False, "error": "Sai mật khẩu."}, status_code=401)
    ma = (code or "").strip()
    if totp.kiem(cfgmod.totp_secret(cfg), ma, buoc_da_dung=cfgmod.totp_last_step(cfg)) is None \
            and not cfgmod.totp_dung_ma_khoi_phuc(ma):
        return JSONResponse({"ok": False, "error": "Mã xác thực không đúng."}, status_code=401)
    cfgmod.totp_tat()
    return {"ok": True}


@app.post("/auth/2fa/recovery")
async def auth_2fa_recovery(request: Request, password: str = Form(...)):
    """Sinh LẠI bộ mã khôi phục (bộ cũ hết hiệu lực ngay). Dùng khi lỡ mất tờ giấy cũ."""
    if (loi := _doi_phien_that(request)) is not None:
        return loi
    cfg = cfgmod.read_settings()
    if not cfgmod.totp_enabled(cfg):
        return JSONResponse({"ok": False, "error": "2FA chưa bật."}, status_code=400)
    if not cfgmod.verify_password(password, cfg):
        return JSONResponse({"ok": False, "error": "Sai mật khẩu."}, status_code=401)
    ma_khoi_phuc = totp.sinh_ma_khoi_phuc()
    cfgmod.totp_set(secret=None, recovery=ma_khoi_phuc)
    return {"ok": True, "recovery": ma_khoi_phuc}


@app.post("/auth/password")
async def auth_password(request: Request, current_password: str = Form(""),
                        password: str = Form(""), username: str = Form("")):
    """ĐỔI mật khẩu / tên đăng nhập của tài khoản ĐANG CÓ.

    Vì sao không dùng lại /auth/setup: đó là đường CÔNG KHAI cho lần đầu tạo admin, nên nó
    buộc phải từ chối khi đã có tài khoản - không thì ai gõ trúng URL cũng chiếm được quyền
    trước chủ máy. Dashboard trước đây gọi nhầm sang đó để đổi mật khẩu và nhận đúng cái từ
    chối ấy, nên bấm Lưu là không có gì xảy ra.

    Đòi MẬT KHẨU HIỆN TẠI dù đã đăng nhập, cùng lý do với /auth/2fa/disable: một phiên bị mượn
    (máy mở sẵn dashboard) không được phép biến thành "đổi mật khẩu rồi khoá chính chủ ra ngoài".

    Để trống `password` = chỉ đổi tên đăng nhập; vẫn phải nhập mật khẩu hiện tại vì đổi tên
    đăng nhập cũng là đổi credential vào máy.
    """
    if (loi := _doi_phien_that(request)) is not None:
        return loi
    cfg = cfgmod.read_settings()
    if not cfgmod.auth_enabled(cfg):
        return JSONResponse({"ok": False, "error": "Chưa có tài khoản nào - đặt mật khẩu lần đầu đã."},
                            status_code=400)
    if not cfgmod.verify_password(current_password, cfg):
        await asyncio.sleep(0.5)   # cùng nhịp làm chậm với /auth/login
        return JSONResponse({"ok": False, "error": "Sai mật khẩu hiện tại."}, status_code=401)
    ten = (username or "").strip()
    if password and len(password) < 8:
        return JSONResponse({"ok": False, "error": "Mật khẩu tối thiểu 8 ký tự"}, status_code=400)
    if not password and not ten:
        return JSONResponse({"ok": False, "error": "Không có gì để đổi."}, status_code=400)
    # GHI ĐÈ TỪNG KHOÁ, không thay cả object `auth`: 2FA cũng nằm trong đó, gán đè nguyên cục
    # là lặng lẽ tắt xác thực 2 lớp của người ta ngay lúc họ vừa đổi mật khẩu.
    a = dict(cfg.get("auth") or {})
    if ten:
        a["username"] = ten
    if password:
        a["password_hash"], a["salt"] = cfgmod.hash_password(password)
    cfg["auth"] = a
    cfgmod.write_settings(cfg)
    if not password:
        return {"ok": True, "username": a.get("username", "")}
    # Đổi mật khẩu = hạ MỌI phiên cũ (máy khác, trình duyệt khác) rồi cấp lại phiên cho chính
    # máy này. Thiếu bước này thì cái phiên mà người ta đổi mật khẩu để đuổi đi vẫn sống thêm
    # 30 ngày, và việc đổi coi như không có tác dụng.
    cfgmod.clear_sessions()
    return _session_cookie(JSONResponse({"ok": True, "username": a.get("username", "")}),
                           cfgmod.new_session(), request)


@app.get("/auth/tokens")
async def auth_tokens_list():
    """Token API đang có. KHÔNG kèm bản băm và không có đường nào đọc lại token thô."""
    return {"tokens": cfgmod.list_api_tokens()}


@app.post("/auth/tokens")
async def auth_tokens_create(request: Request, name: str = Form(""), scope: str = Form("full")):
    """Tạo token mới. Trả bản THÔ đúng MỘT lần.

    Bắt buộc phải đang đăng nhập bằng SESSION mới tạo được: không cho dùng token đẻ token.
    Thiếu rào này thì một token rò ra là kẻ cầm nó tự cấp thêm token vĩnh viễn cho mình, và
    thu hồi cái đã rò cũng vô nghĩa.
    """
    if cfgmod.gate_active() and not cfgmod.valid_session(request.cookies.get("javis_session", "")):
        return JSONResponse({"ok": False, "error": "Tạo token phải đăng nhập bằng trình duyệt "
                                                  "(không dùng token để tạo token)."},
                            status_code=403)
    return {"ok": True, **cfgmod.create_api_token(name, scope)}


@app.post("/auth/tokens/revoke")
async def auth_tokens_revoke(request: Request, id: str = Form(...)):
    """Thu hồi. Cho phép dùng chính token đang cầm để tự thu hồi mình: mất máy thì phải hạ
    được credential ngay, kể cả khi không mở nổi trình duyệt."""
    return {"ok": cfgmod.revoke_api_token(id)}


@app.post("/auth/logout")
async def auth_logout(request: Request):
    cfgmod.drop_session(request.cookies.get("javis_session", ""))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("javis_session", path="/")
    return resp


@app.post("/auth/disable")
async def auth_disable():
    """Tắt yêu cầu đăng nhập (xóa mật khẩu) - chỉ gọi được khi ĐANG đăng nhập (middleware chặn)."""
    cfg = cfgmod.read_settings()
    cfg["auth"] = {"username": "", "password_hash": "", "salt": ""}
    cfgmod.write_settings(cfg)
    cfgmod.clear_sessions()
    return {"ok": True}


# ============================================================
# Providers - nhà cung cấp model. MỌI kind đều được cấp MCP Javis + tool file brain + skill;
# khác nhau ở ĐƯỜNG đi và ở việc chạy được lệnh máy hay không:
#   kind=cli   (Claude Code, Gemini CLI) - MCP native + Bash, chạy lệnh máy
#   kind=oauth (ChatGPT qua Codex) - MCP native + kho MCP gốc Codex, chạy lệnh máy
#   kind=api   (OpenRouter/OpenAI/Anthropic/Gemini) - MCP qua hub trong vòng gọi tool
#              (_api_stream_mcp), đọc/ghi brain bằng tool vault, KHÔNG chạy lệnh máy
#
# `gemini-cli` để kind="cli" là CỐ Ý, không phải tiện tay: `kind` phân loại NĂNG LỰC chứ không
# phải nhà cung cấp. Mọi chỗ hỏi "đây có phải bộ não gói thuê bao có tool thật không" đều viết
# `kind in ("cli","oauth")` - đường tắt fast-path, ngân sách ngữ cảnh, nhãn thuê bao. Đặt nó
# một kind riêng là phải sửa đúng 17 chỗ đó và chắc chắn sót. Chỗ nào cần biết ĐÚNG engine nào
# thì so bằng `prov`, như nhánh chat vẫn làm với openai-oauth.
# ============================================================
PROVIDER_DEFS = [   # thứ tự = thứ tự hiển thị card ở trang Models
    {"id": "anthropic-cli", "label": "Anthropic OAuth (Claude Code)", "kind": "cli", "key_field": None,          "catalog_key": "claude",
     "default_models": ["opus", "sonnet", "haiku", "fable"]},
    {"id": "openai-oauth",  "label": "OpenAI OAuth (ChatGPT)",  "kind": "oauth", "key_field": None,             "catalog_key": "openai-oauth",
     "default_models": []},  # model/list của Codex app-server là nguồn chân lý; không ghim version ở đây
    # Gemini CLI: đăng nhập bằng TÀI KHOẢN GOOGLE, không cần mua API key - cùng backend Code
    # Assist mà Antigravity dùng, nhưng qua CLI chính chủ Google có hỗ trợ bên thứ ba.
    # Khác hẳn provider `gemini` bên dưới (kind=api, trả tiền theo lượt gọi bằng API key).
    # Antigravity CLI (binary `agy`) - bản Google chỉ định thay cho Gemini CLI sau khi họ ngắt
    # hạng cá nhân 18/06/2026. Đặt TRƯỚC thẻ Gemini CLI vì đây mới là đường còn sống cho người
    # dùng cá nhân, và cho chọn đúng dàn model của Antigravity IDE (có cả Claude).
    # default_models để RỖNG là cố ý: danh sách hỏi thẳng `agy models` chứ không chép tay - tên
    # model của Google đổi liên tục, mà bảng chép tay thì sai lặng lẽ.
    {"id": "antigravity-cli", "label": "Google Antigravity CLI", "kind": "cli", "key_field": None,
     "catalog_key": "antigravity-cli", "default_models": []},
    {"id": "gemini-cli",    "label": "Google Gemini CLI (cá nhân đã bị Google ngắt)", "kind": "cli", "key_field": None,
     "catalog_key": "gemini-cli", "default_models": list(gemini_cli.MODELS_MAC_DINH)},
    {"id": "openrouter",    "label": "OpenRouter",              "kind": "api", "key_field": "openrouter_key",    "catalog_key": "openrouter",
     "default_models": ["openai/gpt-4o-mini"]},
    {"id": "anthropic-api", "label": "Anthropic (API)",         "kind": "api", "key_field": "anthropic_api_key", "catalog_key": "anthropic-api",
     "default_models": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]},
    {"id": "openai",        "label": "OpenAI (ChatGPT API)",    "kind": "api", "key_field": "openai_api_key",    "catalog_key": "openai",
     "default_models": ["gpt-4o", "gpt-4o-mini", "o3-mini"]},
    {"id": "gemini",        "label": "Google Gemini (API)",     "kind": "api", "key_field": "gemini_api_key",    "catalog_key": "gemini",
     "default_models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]},
    {"id": "groq",          "label": "Groq (API)",              "kind": "api", "key_field": "groq_api_key",      "catalog_key": "groq",
     "default_models": ["llama-3.3-70b-versatile", "qwen3-32b", "openai/gpt-oss-120b"]},
    # Ollama Cloud. CỐ Ý không đấu bản chạy trên máy nhà: bản đó đòi một ô địa chỉ riêng, tức
    # một ca đặc biệt duy nhất xuyên suốt lớp này, trong khi phần đông người dùng Javis chạy
    # nó trên VPS - nơi "localhost" là chính cái container chứ không phải máy họ.
    # default_models RỖNG: danh sách model của Ollama đổi luôn, /provider/models nạp bản LIVE.
    {"id": "ollama",        "label": "Ollama Cloud",            "kind": "api", "key_field": "ollama_key",
     "catalog_key": "ollama", "default_models": []},
]

def _provider_def(pid):
    return next((p for p in PROVIDER_DEFS if p["id"] == pid), None)

def _effective_main(cfg):
    """Model chính HIỆU LỰC: lấy model.main nếu đã set; nếu rỗng → suy từ legacy engine
    (để config cũ chưa có 'main' vẫn route đúng provider)."""
    m = cfg.get("model", {})
    main = m.get("main") or {}
    if main.get("provider"):
        return {"provider": main["provider"], "model": main.get("model") or ""}
    eng = m.get("engine")
    if eng == "openrouter":
        return {"provider": "openrouter", "model": m.get("openrouter_model") or ""}
    if eng == "anthropic-api":
        return {"provider": "anthropic-api", "model": m.get("claude_model") or ""}
    return {"provider": "anthropic-cli", "model": m.get("claude_model") or "opus"}

def _providers_view(cfg):
    m = cfg.get("model", {})
    cat = m.get("catalog", {}) or {}
    main = _effective_main(cfg)
    oauth = m.get("openai_oauth") or {}
    oauth_on = bool(oauth.get("access_token") or oauth.get("refresh_token"))
    out = []
    for p in PROVIDER_DEFS:
        # Gemini CLI: ẨN thẻ khi máy không có binary `gemini` (0.29.1).
        #
        # Google ngừng phục vụ nó cho MỌI tài khoản cá nhân từ 18/06/2026, nên với gần như mọi
        # người đây là một lựa chọn chết - bày ra chỉ để họ đăng nhập xong rồi đâm vào tường.
        # Nhưng KHÔNG xoá engine: hai diện Google giữ nguyên là giấy phép Code Assist doanh
        # nghiệp và chạy bằng API key, mà máy của họ thì luôn có sẵn binary. Nên "có binary hay
        # không" vừa đúng là ranh giới giữa hai nhóm, vừa không cần thêm nút bật/tắt nào.
        #
        # Ngoại lệ `is_main`: ai đang ĐẶT nó làm Main Model thì phải thấy thẻ, không thì họ mất
        # đường đổi sang engine khác ngay trên trang này.
        if (p["id"] == "gemini-cli" and not gemini_cli.find_gemini_cli()
                and main.get("provider") != p["id"]):
            continue
        models = cat.get(p["catalog_key"]) or p.get("default_models", [])
        if p["kind"] == "oauth":
            configured = oauth_on
        elif p["id"] == "gemini-cli":
            # Không dùng lối "key_field rỗng nên coi như xong" của anthropic-cli: Gemini CLI có
            # thể chưa cài, hoặc cài rồi mà chưa đăng nhập Google. Cả hai đều đọc từ file, rẻ.
            configured = bool(gemini_cli.auth_status().get("connected"))
        elif p["id"] == "antigravity-cli":
            # `agy` giữ phiên trong keyring của hệ điều hành nên không có file nào để soi -
            # auth_status() phải hỏi chính CLI, và nó tự nhớ kết quả một phút để mở trang Models
            # không đẻ tiến trình mỗi lần.
            configured = bool(antigravity_cli.auth_status().get("connected"))
        elif p["key_field"] is None:
            configured = True
        else:
            configured = bool(m.get(p["key_field"]))
        item = {
            "id": p["id"], "label": p["label"], "kind": p["kind"],
            "needs_key": p["key_field"] is not None,
            "configured": configured,
            "models": models,
            "is_main": main.get("provider") == p["id"],
        }
        if p["kind"] == "oauth":
            item["account"] = oauth.get("account_id", "")
            item["plan"] = oauth.get("plan", "")
            # Đăng nhập ChatGPT do CHÍNH JAVIS lo (OAuth device code, token ghi vào ~/.codex)
            # nên "Đã kết nối" không chứng minh máy có binary `codex`. Máy thiếu nó là thẻ
            # xanh mà chat vỡ - báo cáo 16/08: người mới cài kết nối được nhưng không dùng
            # được. Lộ cli_found để thẻ nói thẳng ngay tại trang Models.
            item["cli_found"] = bool(find_codex_cli())
            item["cai_lenh"] = "npm install -g @openai/codex"
        if p["id"] == "gemini-cli":
            _g = gemini_cli.auth_status()
            item["cli_found"] = bool(gemini_cli.find_gemini_cli())
            item["auth_method"] = _g.get("method", "")
            item["account"] = _g.get("email", "")
            item["auth_error"] = _g.get("error", "")
            # Đăng nhập qua dashboard thì Javis giữ token nên NGẮT được; đăng nhập bằng
            # terminal thì token là của CLI, Javis không có quyền gỡ hộ.
            item["auth_by_javis"] = gemini_oauth.connected()
        if p["id"] == "antigravity-cli":
            _a = antigravity_cli.auth_status()
            item["cli_found"] = bool(antigravity_cli.find_antigravity_cli())
            item["auth_method"] = _a.get("method", "")
            item["auth_error"] = _a.get("error", "")
            item["cai_lenh"] = antigravity_cli.lenh_cai()
            # Không có nút Ngắt: token nằm trong keyring của hệ điều hành, Javis không giữ nên
            # cũng không gỡ hộ được. Dựng nút rồi bên dưới không làm gì mới là dối.
            item["auth_by_javis"] = False
            # Đăng nhập làm trong TERMINAL, không phải trên dashboard - xem
            # `antigravity_cli.login_huong_dan()` để biết vì sao. Thẻ Models chỉ đưa lại đúng
            # lệnh cần gõ.
            item["dang_nhap"] = antigravity_cli.login_huong_dan()
        if p["id"] == "anthropic-cli":
            # Gói Claude Code chạy bằng gì, và có đang gánh việc nền không. Trang Models vẽ ô
            # chọn + cảnh báo từ ba field này. Cảnh báo đi kèm DỮ LIỆU chứ không hardcode ở
            # dashboard: chỉ server mới biết model việc nền đang trỏ vào đâu.
            item["auth_mode"] = claude_auth.che_do(cfg)
            item["auth_api_key_set"] = bool(claude_auth.api_key(cfg))
            item["auth_warning"] = claude_auth.canh_bao_neu_can(cfg)
            # Cùng lý do với cli_found của Codex: key_field=None làm configured luôn True,
            # nhưng bản cài tay thiếu binary `claude` thì chat chết ngay lượt đầu.
            item["cli_found"] = bool(find_claude_cli())
            item["cai_lenh"] = "npm install -g @anthropic-ai/claude-code"
        out.append(item)
    return out

def _set_main_model(cfg, provider, model):
    """Đặt model chính + ĐỒNG BỘ field legacy (engine/claude_model/openrouter_model) để chat/Telegram cũ chạy."""
    m = cfg["model"]
    # Đóng mốc vào nhật ký trước khi ghi đè. Đổi bộ não là thứ làm đường token gãy khúc rõ
    # nhất trên biểu đồ, và không có mốc thì tháng sau nhìn lại chỉ thấy một cái bậc thang
    # không ai giải thích được. Đây là choke point DUY NHẤT của việc đổi model chính.
    _cu = m.get("main") or {}
    if (_cu.get("provider"), _cu.get("model")) != (provider, model):
        usage_saving.ghi_moc("model", f"{provider}/{model}",
                             f"{_cu.get('provider') or ''}/{_cu.get('model') or ''}",
                             f"Đổi bộ não sang {model or provider}")
    m["main"] = {"provider": provider, "model": model}
    if provider == "openrouter":
        m["engine"] = "openrouter"; m["openrouter_model"] = model
    elif provider == "anthropic-api":
        m["engine"] = "anthropic-api"; m["claude_model"] = model
    elif provider == "openai":
        m["engine"] = "openai"
    elif provider == "openai-oauth":
        m["engine"] = "openai-oauth"
    elif provider == "gemini":
        m["engine"] = "gemini"
    elif provider == "gemini-cli":
        m["engine"] = "gemini-cli"
    elif provider == "antigravity-cli":
        m["engine"] = "antigravity-cli"
    elif provider == "groq":
        m["engine"] = "groq"
    elif provider == "ollama":
        m["engine"] = "ollama"
    else:  # anthropic-cli
        m["engine"] = "cli"; m["claude_model"] = model

def _aux_model():
    """Model việc nền khi provider là Claude. '' = không đổi (mặc định CLI).

    Provider khác Claude thì model KHÔNG phải alias Claude, trả '' để nhánh cũ đừng gán
    nhầm vào engine Claude - việc chọn engine đúng do _aux_swap lo."""
    spec = aux_engine.read_spec()
    return spec["model"] if aux_engine.is_claude(spec) else ""


def _aux_swap(cli, mode=None, tag=None):
    """Engine Claude vừa dựng cho việc nền -> engine theo model phụ người dùng chọn.
    Mặc định/hỏng cấu hình thì trả lại chính engine Claude đó (việc nền không được chết)."""
    return aux_engine.swap(cli, mode=mode, tag=tag, codex_profile=_write_codex_profile)

def _codex_safe_model(model: str) -> str:
    """Model hợp lệ cho Codex/ChatGPT-account. Model API thường (gpt-5-mini, gpt-4o, o3...)
    KHÔNG chạy được qua Codex → coerce về model Codex mặc định vừa lấy live.
    Hợp lệ = nằm trong catalog 'openai-oauth' HOẶC kết thúc '-codex'."""
    m = (model or "").strip()
    cat = (cfgmod.read_settings().get("model", {}).get("catalog", {}).get("openai-oauth")) or []
    if m and (m in cat or m.endswith("-codex")):
        return m
    # Catalog rỗng (cài mới/offline): không truyền -m để Codex tự chọn default
    # hiện hành của chính nó, thay vì Javis đoán một model id rồi sớm lỗi thời.
    return cat[0] if cat else ""

def _is_codex_model(model: str) -> bool:
    """Model này thuộc Codex/ChatGPT (chạy qua Codex CLI) hay Claude? gpt* / *-codex / trong
    catalog openai-oauth = Codex. Còn lại (sonnet/opus/haiku/fable/claude-*) = Claude."""
    m = (model or "").strip().lower()
    if not m:
        return False
    cat = [c.lower() for c in (cfgmod.read_settings().get("model", {}).get("catalog", {}).get("openai-oauth") or [])]
    return m.startswith("gpt") or m.endswith("-codex") or m in cat

def _chat_provider(mcfg):
    """Provider dùng cho chat (id, kind, key, model) - từ model chính hiệu lực."""
    em = _effective_main({"model": mcfg})
    prov, model = em["provider"], em["model"]
    d = _provider_def(prov) or {}
    kind = d.get("kind", "cli")
    key = mcfg.get(d["key_field"], "") if d.get("key_field") else ""
    if prov == "openrouter":
        model = model or mcfg.get("openrouter_model")
    return prov, kind, key, model


def _chat_provider_for_session(mcfg, row):
    """Provider cho MỘT phiên chat: phiên đã GHIM model riêng (user đổi model ngay trong
    phiên) thì theo ghim; chưa ghim thì rơi về _chat_provider (mặc định chung).

    Vì sao có hàm này (16/08): đổi model ở tab/phiên khác kéo model của MỌI phiên đổi
    theo, vì tất cả đọc chung settings.json. Chủ muốn phiên nhớ model cuối user đã chọn
    TRONG phiên đó. Ghim hỏng (provider không còn cấu hình) thì rơi về mặc định chung
    thay vì chết lượt chat."""
    pprov = ((row or {}).get("pinned_provider") or "").strip()
    if not pprov:
        return _chat_provider(mcfg)
    d = _provider_def(pprov)
    if not d:
        return _chat_provider(mcfg)
    kind = d.get("kind", "cli")
    key = mcfg.get(d["key_field"], "") if d.get("key_field") else ""
    if kind == "api" and not key:
        return _chat_provider(mcfg)   # key đã bị gỡ sau khi ghim → đừng chạy vào tường
    model = ((row or {}).get("pinned_model") or "").strip()
    if pprov == "openrouter":
        model = model or mcfg.get("openrouter_model")
    return pprov, kind, key, model


def _claude_api_model(model: str) -> str:
    """Alias của Claude Code -> model id THẬT mà API nhận.

    Claude Code hiểu "opus"/"sonnet"/"haiku" và tự chọn bản mới nhất, nhưng /v1/messages thì
    không: gửi "haiku" là ăn 404 model_not_found. Đường gọi thẳng của gói thuê bao đi qua API
    nên phải dịch. Catalog `claude` đã được /provider/models ghi đè bằng danh sách LIVE (alias
    đứng trước, id đầy đủ đứng sau), nên chỉ cần lấy id đầy đủ ĐẦU TIÊN cùng dòng - đó chính
    là bản mới nhất, đúng thứ alias vẫn trỏ tới.

    Không tra được thì trả nguyên: thà để nhà cung cấp nói không còn hơn tự đoán một tên khác.
    """
    m = str(model or "").strip()
    if not m or "-" in m:
        return m                      # đã là id đầy đủ (claude-opus-4-8...), hoặc rỗng
    try:
        cat = (cfgmod.read_settings().get("model", {}).get("catalog", {}).get("claude")) or []
    except Exception:  # noqa: BLE001 - tra cứu hỏng không được phá lượt chat
        return m
    for x in cat:
        x = str(x or "")
        if "-" in x and x.split("-")[1:2] == [m]:
            return x
    return m


def _api_stream(prov, key, model, messages, reasoning="off"):
    """Stream của một provider, KÈM chạy lại khi nhà cung cấp gãy tạm thời.

    Chạy lại nằm ở đây chứ không nằm trong từng hàm engine vì đây là chỗ DUY NHẤT mọi đường
    chat không-tool đi qua: dashboard, Telegram, bot chuyên trách, việc nền, đường tắt. Một
    chỗ sửa là tám bộ não cùng được.

    Lỗi tạm thời là 429 và 5xx - nhà cung cấp đang quá tải hoặc mình vừa gọi hơi dày. Trước
    bản này chỉ OpenRouter tự thử lại, nên một cú 429 chớp nhoáng của Anthropic giết trọn
    lượt trả lời: người nhắn cho bot nhận câu xin lỗi kỹ thuật, người trực bị gọi dậy, còn
    thứ cần làm chỉ là chờ một giây rồi hỏi lại.
    """
    return engine.thu_lai_khi_tam_thoi(
        lambda: _api_stream_goc(prov, key, model, messages, reasoning),
        nhan=f"{prov}/{model or 'mặc định'}")


# Allowlist rỗng-thật cho engine Claude Code: bật cổng `can_use_tool` mà không tool nào khớp,
# nên MỌI tool bị từ chối per-call. Danh sách rỗng [] KHÔNG dùng được - nó falsy nên engine rơi
# vào nhánh bypassPermissions, tức mở toang đúng cái ta đang muốn đóng.
CLAUDE_SUB_KHONG_TOOL = ["__javis_claude_sub_khong_tool__"]


def _claude_sub_tach(messages):
    """messages kiểu API -> (system, prompt) cho engine Claude Code.

    Engine Claude Code nhận MỘT prompt chứ không nhận mảng messages, nên lịch sử được gói lại
    bằng chính `compaction.bootstrap_prompt` mà nhánh Codex và nhánh xoay-mạch vẫn dùng.
    """
    sys_txt = "\n\n".join((m.get("content") or "") for m in messages
                          if m.get("role") == "system").strip()
    conv = [{"role": m["role"], "content": m.get("content") or ""}
            for m in messages
            if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()]
    if not conv:
        return sys_txt, "(tiếp tục)"
    if conv[-1]["role"] == "user":
        return sys_txt, compaction.bootstrap_prompt(conv[:-1], conv[-1]["content"])
    return sys_txt, compaction.bootstrap_prompt(conv, "(tiếp tục)")


async def _claude_sub_doc(cli, prompt, model):
    """Đọc một lượt engine Claude Code -> đúng hợp đồng sự kiện của `_api_stream`.

    `final` mang TOÀN VĂN câu trả lời, còn `text` là từng mảnh của chính văn bản đó - phát cả
    hai là người dùng đọc câu trả lời hai lần. Nên `final` chỉ được phát chữ khi chưa mảnh nào
    đi qua (lượt không stream), và luôn là chỗ chốt usage.
    """
    yield {"type": "meta", "model": model}
    da_co_chu = False
    async for ev in cli.query(prompt):
        et = ev.get("type")
        if et == "text":
            txt = ev.get("content") or ""
            if txt:
                da_co_chu = True
                yield {"type": "text", "content": txt}
        elif et == "tool_call":
            yield {"type": "tool_call", "tool": ev.get("name") or "",
                   "content": f"⚙ {ev.get('name') or 'tool'}"}
        elif et == "final":
            txt = ev.get("content") or ""
            if txt and not da_co_chu:
                yield {"type": "text", "content": txt}
            ti = int(ev.get("tokens_in") or 0)
            to = int(ev.get("tokens_out") or 0)
            if ti or to:
                yield {"type": "usage", "input": ti, "output": to}
        elif et == "error":
            yield {"type": "error", "content": str(ev.get("content") or "lỗi không rõ")}


def _claude_sub_stream(model, messages, reasoning="off", *, brain=None, tag="chat",
                       tiet_kiem=False):
    """Gói Claude Code, KHÔNG tool - thay cho đường gọi thẳng /v1/messages bằng token OAuth.

    Đường cũ tự đọc `~/.claude/.credentials.json` rồi gửi `Authorization: Bearer <token>` tới
    api.anthropic.com. Anthropic cấm đúng việc đó (xem claude_auth.py), và cách họ bắt là soi
    dấu vân tay request - thứ mà request Javis tự dựng chắc chắn không có. Nay lượt này chạy
    qua chính binary `claude`, nên ai đăng nhập và ai trả tiền là chuyện của Claude Code.

    `tiet_kiem=True` cho đường Siêu tiết kiệm: gửi system prompt TRẦN thay vì preset
    claude_code, giữ nguyên phần tiết kiệm token vốn là toàn bộ lý do tồn tại của nó.
    """
    sys_txt, prompt = _claude_sub_tach(messages)
    cli = claude_engine(system_prompt=sys_txt, cwd=_brain_root(brain) if brain else None,
                        tag=tag, allowed_tools=CLAUDE_SUB_KHONG_TOOL,
                        model=_claude_api_model(model) or None)
    cli.system_prompt_raw = bool(tiet_kiem)
    return _claude_sub_doc(cli, _cli_think(reasoning, prompt), model)


def _gemini_sub_stream(model, messages, reasoning="off", *, brain=None, tag="chat",
                       mode="suggest"):
    """Gói Google (Gemini CLI) cho đường CHAT-THUẦN của `_api_stream`.

    Vì sao phải có: `_api_stream` là đường DÙNG CHUNG của bot chuyên trách, tóm tắt, đặt tiêu
    đề - những chỗ chỉ cần một lượt chữ. Provider nào không có nhánh ở đó thì rơi xuống dòng
    cuối `engine.anthropic_stream(key, ...)` với key rỗng, tức là hỏng câm. Đúng khuôn
    `_claude_sub_stream` đã dựng cho gói Claude Code.

    `mode="suggest"` mặc định là CỐ Ý: đường này không phải chỗ để một bot đang nói chuyện với
    người lạ ghi file. Nơi cần quyền cao hơn thì truyền vào tường minh.

    KHÔNG phải `async def`, y như `_claude_sub_stream`: nơi gọi làm `async for ev in
    _api_stream(...)`, nên hàm phải TRẢ VỀ async generator chứ không phải là coroutine sinh ra
    nó. Viết `async def` ở đây thì `async for` nhận một coroutine và ném TypeError giữa lượt.
    """
    sys_txt, prompt = _claude_sub_tach(messages)
    g = gemini_cli.GeminiCLI(cwd=_brain_root(brain) if brain else None, tag=tag,
                             model=model or gemini_cli.MODEL_MAC_DINH, instructions=sys_txt)
    g.approval_mode = gemini_cli.approval_cho_mode(mode)
    if brain:
        _apply_gemini_hub(g, _brain_root(brain), mode=mode)
    return _gemini_sub_doc(g, _cli_think(reasoning, prompt), model)


def _antigravity_sub_stream(model, messages, reasoning="off", *, brain=None, tag="chat",
                            mode="suggest"):
    """Gói Google qua Antigravity CLI cho đường CHAT-THUẦN của `_api_stream`.

    Cùng lý do tồn tại với `_gemini_sub_stream`: provider nào không có nhánh ở `_api_stream` sẽ
    rơi xuống `engine.anthropic_stream(key="")` và hỏng câm. KHÔNG phải `async def` - xem chú
    thích dài ở `_gemini_sub_stream`.
    """
    sys_txt, prompt = _claude_sub_tach(messages)
    g = antigravity_cli.AntigravityCLI(cwd=_brain_root(brain) if brain else None, tag=tag,
                                       model=model or None, instructions=sys_txt)
    g.mode = mode or "suggest"
    if brain:
        _apply_antigravity_hub(g, _brain_root(brain), mode=mode)
    # Dùng chung bộ dịch sự kiện với Gemini CLI: hai engine đã phát cùng một hợp đồng
    # {tool_call, final, usage, error}, viết lại là hai bản dễ lệch nhau.
    return _gemini_sub_doc(g, _cli_think(reasoning, prompt), model)


async def _gemini_sub_doc(g, prompt, model):
    """Một lượt engine CLI (Gemini hoặc Antigravity) -> hợp đồng sự kiện của `_api_stream`."""
    yield {"type": "meta", "model": model}
    async for ev in g.query(prompt):
        et = ev.get("type")
        if et == "final":
            txt = ev.get("content") or ""
            if txt:
                yield {"type": "text", "content": txt}
        elif et == "tool_call":
            yield {"type": "tool_call", "tool": ev.get("name") or "",
                   "content": f"⚙ {ev.get('name') or 'tool'}"}
        elif et == "usage":
            yield {"type": "usage", "input": int(ev.get("input_tokens") or 0),
                   "output": int(ev.get("output_tokens") or 0)}
        elif et == "error":
            yield {"type": "error", "content": str(ev.get("content") or "lỗi không rõ")}


# Tool NATIVE của Claude Code mà bot chuyên trách TUYỆT ĐỐI không được chạm, ở mọi mức quyền.
# Bot phục vụ người lạ nhắn tới, nên "chạy được lệnh máy" là một hạng rủi ro khác hẳn phần còn
# lại của Javis. Allowlist bên dưới đã đủ chặn (mọi tool ngoài list bị `can_use_tool` từ chối
# per-call); danh sách này là lớp thứ hai, để một hôm nào đó allowlist bị nới thì đây vẫn giữ.
BOT_CAM_NATIVE = ["Bash", "BashOutput", "KillShell", "WebFetch", "WebSearch", "Task",
                  "Write", "Edit", "NotebookEdit", "Read", "Glob", "Grep"]


def _claude_sub_stream_tools(model, messages, reasoning="off", *, brain=None, tag="bot",
                            mode="full"):
    """Gói Claude Code CÓ tool, cho bot chuyên trách - thay `anthropic_chat_with_mcp(oauth_token=)`.

    Đường cũ an toàn nhờ MỘT sự thật kiến trúc: không engine nào của bot mở CLI, nên không con
    nào có tool native, nên không con nào trèo ra khỏi brain của bot được. Mở engine Claude
    Code là MẤT sự thật đó. Nó được dựng lại ở đây bằng bốn lớp tường minh, và cả bốn đều cần:

    1. `allowed_tools` chỉ có `mcp__javis` → cổng `can_use_tool` TỪ CHỐI mọi tool khác từng lần
       gọi, kể cả Bash/Read/Write builtin của Claude Code.
    2. `BOT_CAM_NATIVE` chặn thẳng nhóm native, phòng khi lớp 1 bị nới sau này.
    3. Config hub mang X-Javis-Vault = brain CỦA BOT → tool file đi qua `_safe_path` của đúng
       brain đó. Thiếu nó thì hub không cấp nhóm tool file (mặc định của đường Claude), và bot
       mức Được ghi mất khả năng ghi - vì lớp 1 đã chặn Write native rồi.
    4. `mcp_strict` → không nạp MCP ambient của máy chủ, tức bot không thấy connector của chủ.

    Cố ý KHÔNG dùng `_apply_mcp`: hàm đó gắn config hub DÙNG CHUNG không mang brain, đúng cho
    chat của chủ (Claude có tool file native nên hub bỏ nhóm file đi cho khỏi trùng) nhưng sai
    cho ca này. Đây là chỗ duy nhất cần cấu hình riêng, nên nó viết thẳng ra chứ không nới hàm
    dùng chung của mọi đường Claude.
    """
    sys_txt, prompt = _claude_sub_tach(messages)
    vault = _brain_root(brain) if brain else None
    cli = claude_engine(system_prompt=sys_txt, cwd=vault, tag=tag,
                        allowed_tools=list(mcp_hub.allow_patterns()),
                        model=_claude_api_model(model) or None)
    cli.javis_mode = mode
    cli.javis_vault = vault
    cli.mcp_config = mcp_hub.claude_config_path(mode, vault_root=vault)
    cli.mcp_strict = cli.mcp_config is not None
    cli.disallowed_tools = list(BOT_CAM_NATIVE)
    return _claude_sub_doc(cli, _cli_think(reasoning, prompt), model)


def _api_stream_goc(prov, key, model, messages, reasoning="off"):
    """Chọn generator stream theo provider api-kind. reasoning=off|low|medium|high."""
    if prov == "openrouter":
        return engine.openrouter_stream(key, model, messages, reasoning)
    if prov == "openai":
        return engine.openai_stream(key, model, messages, reasoning)
    if prov == "gemini":
        return engine.gemini_stream(key, model, messages, reasoning)
    if prov == "groq":
        return engine.groq_stream(key, model, messages, reasoning)
    if prov == "ollama":
        return engine.ollama_stream(key, model, messages, reasoning)
    if prov == "openai-oauth":
        creds = openai_oauth.valid_creds() or {}
        return engine.openai_responses_stream(creds.get("access_token", ""), creds.get("account_id", ""),
                                              _codex_safe_model(model), messages, reasoning)
    if prov == "gemini-cli":
        # Gói Google đi qua chính binary `gemini`, cùng lý do với anthropic-cli ngay dưới:
        # Javis không cầm token của ai, CLI tự lo đăng nhập.
        return _gemini_sub_stream(model, messages, reasoning)
    if prov == "antigravity-cli":
        return _antigravity_sub_stream(model, messages, reasoning)
    if prov == "anthropic-cli":
        # Gói Claude Code đi qua chính binary `claude`, KHÔNG tự dựng request tới
        # api.anthropic.com bằng token của người dùng nữa (xem claude_auth.py). Vẫn không có
        # tool nào ở đường này, đúng hợp đồng cũ. `tiet_kiem` giữ được mức Siêu tiết kiệm.
        return _claude_sub_stream(model, messages, reasoning, tiet_kiem=True)
    return engine.anthropic_stream(key, model, messages, reasoning)


# Cửa sổ lịch sử chat cho engine API (openrouter/openai/anthropic-api). Mỗi lượt
# resend TOÀN BỘ history → phiên dài phình vô hạn. Cửa sổ + logic nén nằm ở compaction.py:
# phần cũ rơi khỏi cửa sổ được TÓM TẮT (chạy nền) thay vì cắt bỏ mất trí nhớ như trước.
_trim_history = compaction.trim_history


def _hub_enabled():
    """Hub MCP bật (mặc định) → mọi engine đấu 1 điểm; tắt qua settings mcp.hub=false (fallback cũ)."""
    return bool(cfgmod.read_settings().get("mcp", {}).get("hub", True))


async def _api_stream_mcp(prov, key, model, messages, reasoning="off", brain=None,
                          force_lazy=False, mode="full"):
    """Model API/OAuth dùng MCP của Javis qua HUB: đa tài khoản + quyền + audit + builtin tools
    (file vault, use_skill) → engine API cũng là agent thực thụ. anthropic-api giờ CÓ tool loop.
    ChatGPT OAuth ở các kênh tương tác đi qua Codex CLI native MCP, không dùng fallback này."""
    tools, route = [], {}
    inventory_tools, inventory_route = [], {}
    if prov in ("openrouter", "openai", "anthropic-api", "gemini", "groq", "ollama"):
        try:
            if _hub_enabled():
                vault_root = _brain_root(brain) if brain else None
                # staging=True: đây là đường chat của CHỦ (dashboard + Telegram của chủ), tức
                # đúng nơi người dùng đính kèm/dán file. Cho javis_read_file với tới vùng nhận
                # file của khung chat, nếu không thì khối "[File đính kèm để ĐỌC…]" mà chính
                # dashboard chèn vào câu hỏi là một lời hứa engine API không giữ nổi. Bot
                # chuyên trách dựng tool ở chỗ khác và KHÔNG truyền cờ này - khách lạ vẫn chỉ
                # thấy brain của bot.
                tools, route = await mcp_hub.discover_all(
                    mode, vault_root=vault_root, force_lazy=force_lazy, staging=True
                )
                inventory_tools, inventory_route = mcp_hub.registry_inventory(
                    mode, vault_root=vault_root, force_lazy=force_lazy, staging=True)
            else:
                servers = mcp_store.servers_for_client()
                if servers:
                    tools, route = await mcp_client.discover(servers)
                    inventory_tools, inventory_route = tools, route
        except Exception as e:
            print(f"[mcp discover] {e}", file=__import__('sys').stderr)
    # Phase 0-1: chỉ đo metadata payload sau khi đã biết tool schema thật. Không lưu content,
    # không chặn quota và không thay danh sách tool. ContextVar giữ trace riêng từng asyncio task.
    _trace = context_runtime.current_trace()
    if _trace:
        _CONTEXT_RUNTIME.set_route(_trace, prov, model or "?")
        _CONTEXT_RUNTIME.observe_payload(
            _trace, messages, tools, provider=prov, model=model or "?")
        _schedule_registry_shadow(
            _trace, brain, inventory_tools or tools, inventory_route or route,
            _last_user_text(messages), prov, model or "?", kind="api",
        )
    if tools:
        # Vòng tool cũng được chạy lại khi gãy tạm thời, nhưng chỉ tới khi nó chạy tool ĐẦU
        # TIÊN: từ đó trở đi lượt này đã để lại dấu vết ngoài đời (ghi file, gửi tin, đặt
        # lịch) và chạy lại là làm hai lần. Điều kiện đó do `thu_lai_khi_tam_thoi` giữ.
        def _vong_tool():
            if prov == "openrouter":
                return engine.openrouter_chat_with_mcp(key, model, messages, reasoning, tools, route)
            if prov == "openai":
                return engine.openai_chat_with_mcp(key, model, messages, reasoning, tools, route)
            if prov == "anthropic-api":
                return engine.anthropic_chat_with_mcp(key, model, messages, reasoning, tools, route)
            if prov == "gemini":
                return engine.gemini_chat_with_mcp(key, model, messages, reasoning, tools, route)
            if prov == "groq":
                return engine.groq_chat_with_mcp(key, model, messages, reasoning, tools, route)
            return engine.ollama_chat_with_mcp(key, model, messages, reasoning, tools, route)

        if prov in ("openrouter", "openai", "anthropic-api", "gemini", "groq", "ollama"):
            return engine.thu_lai_khi_tam_thoi(_vong_tool, nhan=f"{prov}/{model or 'mặc định'}+tool")
    return _api_stream(prov, key, model, messages, reasoning)


def _last_user_text(messages) -> str:
    for message in reversed(messages or []):
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content")
            return content if isinstance(content, str) else ""
    return ""


def _get_readonly_path():
    """Khởi tạo lười để production mặc định 0% không trả chi phí discovery hay Evidence Store."""
    global _READONLY_PATH
    if _READONLY_PATH is None:
        async def _discover(mode, brain_root):
            actual_mode = "full" if mode == "refresh_full" else mode
            await mcp_hub.discover_all(
                actual_mode, vault_root=brain_root,
                force_refresh=(mode == "refresh_full"),
            )
            return mcp_hub.registry_inventory(actual_mode, vault_root=brain_root)

        _READONLY_PATH = readonly_path_runtime.ReadonlyPathCanary(
            _CAPABILITY_REGISTRY, _CAPABILITY_RESOLVER, _CONTEXT_COMPILER,
            _CONTEXT_RUNTIME, _CAPABILITY_EXECUTOR, cfgmod.read_settings, _discover,
        )
    return _READONLY_PATH


def _get_readonly_orchestrator():
    """Phase 7 khởi tạo lười; mặc định 0% không tạo planner/checkpoint trên hot path."""
    global _READONLY_ORCHESTRATOR
    if _READONLY_ORCHESTRATOR is None:
        async def _discover(mode, brain_root):
            actual_mode = "full" if mode == "refresh_full" else mode
            await mcp_hub.discover_all(
                actual_mode, vault_root=brain_root,
                force_refresh=(mode == "refresh_full"),
            )
            return mcp_hub.registry_inventory(actual_mode, vault_root=brain_root)

        _READONLY_ORCHESTRATOR = readonly_orchestrator.ReadonlyOrchestrator(
            _CAPABILITY_REGISTRY, _CAPABILITY_RESOLVER, _CONTEXT_COMPILER,
            _CONTEXT_RUNTIME, _CAPABILITY_EXECUTOR, cfgmod.read_settings, _discover,
            _QUALITY_GATE,
        )
    return _READONLY_ORCHESTRATOR


def _get_adaptive_context():
    """Lazy init để import/startup không mở thêm DB khi Phase 8 vẫn allocation=0."""
    global _ADAPTIVE_CONTEXT
    if _ADAPTIVE_CONTEXT is None:
        _ADAPTIVE_CONTEXT = adaptive_context_runtime.AdaptiveContextCanary(
            cfgmod.STATE_DIR, _CAPABILITY_REGISTRY, _CONTEXT_COMPILER,
            _CONTEXT_RUNTIME, cfgmod.read_settings,
        )
    return _ADAPTIVE_CONTEXT


def _get_write_path():
    """Phase 9 khởi tạo lười; mặc định allocation=0 nên không tốn gì trên hot path."""
    global _WRITE_PATH
    if _WRITE_PATH is None:
        async def _discover(mode, brain_root):
            actual_mode = "full" if mode == "refresh_full" else mode
            await mcp_hub.discover_all(
                actual_mode, vault_root=brain_root,
                force_refresh=(mode == "refresh_full"),
            )
            return mcp_hub.registry_inventory(actual_mode, vault_root=brain_root)

        _WRITE_PATH = write_path_runtime.WritePathCanary(
            _CAPABILITY_REGISTRY, _CAPABILITY_RESOLVER, _CONTEXT_COMPILER,
            _CONTEXT_RUNTIME, _CAPABILITY_EXECUTOR, cfgmod.read_settings, _discover,
        )
    return _WRITE_PATH


async def _execute_write_proposal(plan, provider: str, api_key: str, model: str,
                                  reasoning: str, ws, session_id: str, runtime_trace):
    """Vòng 1 của Phase 9: model chỉ LẬP tham số, gateway ghi ý định rồi HỎI người dùng.

    Không có nhánh nào trong hàm này gọi tool. Write chỉ chạy ở lượt sau, khi
    người dùng gõ lại đúng mã xác nhận.
    """
    actual_model = model or "?"
    lease = plan.lease
    _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "write_path.proposal_started", {
        "provider": provider, "model": actual_model, "model_rounds": 1,
        "capability_id": lease.capability_id, "capability_revision": lease.revision,
        "schema_hash": lease.schema_hash, "policy_version": plan.policy_version,
        "profile_id": (plan.profile or {}).get("id", ""),
    })
    planned = await engine.single_tool_plan(
        provider, api_key, model, list(plan.messages), reasoning, plan.tool_spec
    )
    tokens_in = int(planned.get("input") or 0)
    tokens_out = int(planned.get("output") or 0)
    if planned.get("model"):
        actual_model = planned["model"]
        _CONTEXT_RUNTIME.set_route(runtime_trace, provider, actual_model)
    _CONTEXT_RUNTIME.consume_quota(runtime_trace, plan.reservation_id, tokens_in, tokens_out)
    if tokens_in or tokens_out:
        usage_store.record(provider, actual_model, tokens_in, tokens_out)
    if planned.get("status") != "ok":
        _CONTEXT_RUNTIME.revoke_capability_lease(
            runtime_trace, lease.lease_id, planned.get("error_code") or "planner_failed")
        text = ("Model không lập được tham số đúng hợp đồng cho hành động ghi này. "
                "Javis đã dừng an toàn, chưa gọi tool và chưa thay đổi gì.")
        _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "write_path.failed", {
            "stage": "argument_planner", "error_code": planned.get("error_code") or "unknown",
            "model_rounds": 1, "tool_calls": 0,
        })
        await ws.send_text(json.dumps({
            "type": "response", "content": text, "engine": "javis-gateway",
            "model": actual_model, "session_id": session_id,
            **_ctx_frame(runtime_trace, tokens_in),
        }))
        return text, actual_model

    args = planned.get("arguments") or {}
    valid, error_code = _CAPABILITY_EXECUTOR._validate(lease, args)
    if not valid:
        _CONTEXT_RUNTIME.revoke_capability_lease(runtime_trace, lease.lease_id, error_code)
        text = ("Tham số model đề xuất không đạt JSON Schema của capability. "
                "Javis chưa gọi tool và chưa thay đổi gì.")
        _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "write_path.failed", {
            "stage": "argument_validation", "error_code": error_code,
            "model_rounds": 1, "tool_calls": 0,
        })
        await ws.send_text(json.dumps({
            "type": "response", "content": text, "engine": "javis-gateway",
            "model": actual_model, "session_id": session_id,
            **_ctx_frame(runtime_trace, tokens_in),
        }))
        return text, actual_model

    registered = _get_write_path().register_proposal(
        runtime_trace, plan, args, session_id)
    status = registered.get("status")
    if status == "duplicate":
        text = ("Hành động này đã được ghi nhận trước đó nên Javis KHÔNG chạy lại. "
                f"Trạng thái hiện tại: {registered.get('invocation_status')}.")
    elif status == "locked":
        text = ("Đang có một hành động ghi khác trên cùng tài nguyên chưa kết thúc. "
                "Javis dừng để tránh ghi chồng; bạn xử lý xong việc kia rồi nhắn lại.")
    elif status != "prepared":
        text = ("Không ghi được ý định vào sổ nên Javis dừng trước khi gọi tool. "
                "Chưa có gì thay đổi.")
    elif not str(registered.get("confirmation_code") or "").strip():
        # Không có mã thì KHÔNG có cách nào duyệt: nút bấm sẽ chết và câu gõ tay cũng
        # vô nghĩa. Nói thẳng là hỏng còn hơn bày ra một lời đề xuất không duyệt được.
        status = "no_confirmation_code"
        text = ("Javis không tạo được mã duyệt cho hành động ghi này nên đã dừng. "
                "Chưa có gì thay đổi.")
    else:
        code = str(registered.get("confirmation_code")).strip()
        summary = ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}"
                            for k, v in sorted(args.items()))[:600]
        # Nút bấm, nhưng nhãn PHẢI mang mã của đúng ý định này. Chip gửi đi chính
        # nhãn đó như một tin nhắn người dùng, nên mã là thứ giữ lại tính chất cũ:
        # cú xác nhận gắn với MỘT việc cụ thể, không phải một chữ "xác nhận" trôi
        # nổi mà gõ nhầm cũng ra. Vẫn nói rõ câu gõ tay cho kênh không có nút.
        ask = json.dumps({
            "question": f"Chạy hành động ghi này chứ? ({lease.capability_name})",
            "header": "Duyệt ghi",
            "options": [
                {"label": f"Xác nhận {code}", "desc": "Chạy thật, không hoàn tác được"},
                {"label": "Huỷ", "desc": "Không chạy, bỏ ý định này"},
            ],
        }, ensure_ascii=False)
        text = (
            f"Javis chuẩn bị chạy hành động ghi: {lease.capability_name}.\n"
            f"Tham số: {summary}\n\n"
            f"Việc này thay đổi dữ liệu thật và không tự hoàn tác được, nên Javis "
            f"CHƯA chạy. Bạn bấm nút duyệt bên dưới, hoặc nhắn lại đúng câu: "
            f"XAC NHAN {code}\n"
            f"Không muốn nữa thì nhắn: huỷ\n"
            f"<!-- JAVIS_ASK: {ask} -->"
        )
    if status != "prepared":
        _CONTEXT_RUNTIME.revoke_capability_lease(
            runtime_trace, lease.lease_id, str(status or "register_failed"))
    if status == "prepared":
        invocation_id = str(registered.get("invocation_id") or "")
        if len(_WRITE_PENDING_ARGS) >= _WRITE_PENDING_ARGS_MAX:
            _WRITE_PENDING_ARGS.pop(next(iter(_WRITE_PENDING_ARGS)), None)
        _WRITE_PENDING_ARGS[invocation_id] = dict(args)
    _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "write_path.proposed", {
        "register_status": status, "model_rounds": 1, "tool_calls": 0,
        "capability_id": lease.capability_id,
        "invocation_id": registered.get("invocation_id", ""),
    })
    await ws.send_text(json.dumps({
        "type": "response", "content": text, "engine": provider,
        "model": actual_model, "session_id": session_id,
        **_ctx_frame(runtime_trace, tokens_in),
    }))
    return text, actual_model


async def _execute_write_confirmation(plan, ws, session_id: str, runtime_trace,
                                      brain, provider: str, model: str):
    """Vòng 2 của Phase 9: người dùng đã gõ đúng mã, giờ mới chạy write ĐÚNG MỘT lần.

    Không có model call nào ở vòng này. Tham số đã được duyệt ở vòng trước và được
    khoá bằng args_hash, nên model không còn cơ hội đổi ý giữa duyệt và chạy.
    """
    invocation = plan.invocation or {}
    canary = _get_write_path()
    policy = canary.policy()
    capability_id = str(invocation.get("capability_id") or "")
    records = _CAPABILITY_REGISTRY.get_capabilities([capability_id], _brain_root(brain))
    profile = policy.profile_for(records[0]) if len(records) == 1 else None
    if (len(records) != 1 or profile is None or
            records[0].get("capability_revision") != invocation.get("capability_revision")):
        _CONTEXT_RUNTIME.finish_write_invocation(
            runtime_trace, str(invocation.get("id") or ""),
            str(invocation.get("lease_id") or ""), "FAILED_VALIDATION",
            error_code="capability_changed_since_proposal")
        text = ("Capability đã thay đổi kể từ lúc Javis đề xuất, nên hành động ghi bị "
                "huỷ để không chạy nhầm phiên bản cũ. Chưa có gì thay đổi.")
        await ws.send_text(json.dumps({
            "type": "response", "content": text, "engine": "javis-gateway",
            "model": model, "session_id": session_id,
            **_ctx_frame(runtime_trace, 0),
        }))
        return text

    # Đọc lại arguments đã duyệt từ chính lease + args_hash: raw arguments KHÔNG được
    # lưu ở trace, nên vòng này lấy lại qua evidence store của đề xuất.
    args = _WRITE_PENDING_ARGS.pop(str(invocation.get("id") or ""), None)
    if args is None:
        _CONTEXT_RUNTIME.finish_write_invocation(
            runtime_trace, str(invocation.get("id") or ""),
            str(invocation.get("lease_id") or ""), "FAILED_FINAL",
            error_code="approved_arguments_unavailable")
        text = ("Javis không còn giữ tham số đã được duyệt (tiến trình đã khởi động lại), "
                "nên không chạy hành động ghi này. Bạn nhắn lại yêu cầu để Javis đề xuất mới.")
        await ws.send_text(json.dumps({
            "type": "response", "content": text, "engine": "javis-gateway",
            "model": model, "session_id": session_id,
            **_ctx_frame(runtime_trace, 0),
        }))
        return text

    try:
        _tools, route = await mcp_hub.discover_all("write", vault_root=_brain_root(brain))
        route_entry = route.get(records[0]["name"])
    except Exception as exc:
        route_entry = None
        _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "write.discovery_failed", {
            "mode": "confirm", "error_type": type(exc).__name__})
    if not route_entry or not callable(route_entry.get("call")) or \
            str(route_entry.get("effect") or "") != "write":
        _CONTEXT_RUNTIME.finish_write_invocation(
            runtime_trace, str(invocation.get("id") or ""),
            str(invocation.get("lease_id") or ""), "FAILED_FINAL",
            error_code="write_route_unavailable")
        text = "Không còn đường gọi tool ghi này, Javis dừng an toàn. Chưa có gì thay đổi."
        await ws.send_text(json.dumps({
            "type": "response", "content": text, "engine": "javis-gateway",
            "model": model, "session_id": session_id,
            **_ctx_frame(runtime_trace, 0),
        }))
        return text

    await ws.send_text(json.dumps({
        "type": "tool_call", "tool": records[0]["name"],
        "content": f"⚙ MCP write (đã xác nhận): {records[0]['name']}",
    }))
    outcome = await canary.execute_confirmed(
        runtime_trace, invocation, route_entry["call"], args,
        float(profile.get("timeout_seconds") or 30),
        str(invocation.get("actor_hash") or ""),
    )
    status = outcome.get("status")
    if status == "UNKNOWN":
        reconciled = await canary.reconcile_unknown(
            runtime_trace, invocation, _brain_root(brain), profile)
        if reconciled.get("status") == "SUCCEEDED":
            text = ("Kết nối bị gián đoạn giữa chừng nên Javis đã kiểm chứng lại bằng một "
                    "lệnh đọc: hành động ĐÃ được thực hiện. Javis không chạy lại.")
        elif reconciled.get("status") == "FAILED_FINAL":
            text = ("Kết nối bị gián đoạn, Javis kiểm chứng lại bằng lệnh đọc và thấy hành "
                    "động CHƯA được thực hiện. Bạn nhắn lại nếu muốn Javis làm lại.")
        else:
            text = ("Kết nối bị gián đoạn và Javis KHÔNG kiểm chứng được là hành động đã "
                    "chạy hay chưa. Javis tuyệt đối không chạy lại để tránh làm hai lần. "
                    "Bạn kiểm tra trực tiếp bên hệ thống đích rồi báo lại giúp mình.")
    elif status == "SUCCEEDED":
        evidence = outcome.get("evidence")
        text = "Đã thực hiện xong hành động ghi."
        if evidence is not None:
            text += f"\n\nNguồn: {evidence.ref}"
    elif status == "FAILED_FINAL":
        text = ("Tool báo lỗi rõ ràng nên hành động KHÔNG được thực hiện. "
                f"Mã lỗi: {outcome.get('error_code')}.")
    else:
        text = ("Javis dừng trước khi gọi tool vì ý định ghi không còn hợp lệ. "
                f"Mã: {outcome.get('error_code')}.")
    _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "write_path.completed", {
        "status": status, "model_rounds": 0, "tool_calls": 1 if status != "REJECTED" else 0,
        "capability_id": capability_id,
        "invocation_id": outcome.get("invocation_id", ""),
    })
    await ws.send_text(json.dumps({
        "type": "response", "content": text, "engine": "javis-gateway",
        "model": model, "session_id": session_id,
        **_ctx_frame(runtime_trace, 0),
    }))
    return text


def _track_shadow_task(coro) -> None:
    """Chạy derived refresh/resolve ngoài hot path; lỗi không được ảnh hưởng chat."""
    try:
        task = asyncio.create_task(coro)
        _REGISTRY_SHADOW_TASKS.add(task)
        task.add_done_callback(_REGISTRY_SHADOW_TASKS.discard)
    except Exception:
        try:
            coro.close()
        except Exception:
            pass


def _schedule_registry_shadow(trace, brain, tools, route, query, provider, model,
                              kind="unknown", actor_mode="full") -> None:
    """`actor_mode` phải là mức quyền THẬT của lượt đang chạy.

    Trước đây nó bị đóng cứng "full". Đường chat dashboard đúng là full nên số đo
    không sai, nhưng khi nối shadow vào loop hay task nền (mức suggest/auto) thì
    hằng số đó sẽ im lặng đo bằng quyền cao hơn thực tế, và miss do phân quyền -
    đúng cái filter mà Phase 9 dựa vào - không bao giờ quan sát được.
    """
    if not trace:
        return

    async def _job():
        try:
            await asyncio.to_thread(
                _CAPABILITY_REGISTRY.refresh_tools, _brain_root(brain), tools or [], route or {})
            await asyncio.to_thread(
                _CAPABILITY_REGISTRY.refresh_model_profile,
                provider or "unknown", model or "unknown", kind, True,
                {"observed": True},
            )
            report = await asyncio.to_thread(
                _CAPABILITY_RESOLVER.resolve, query or "", _brain_root(brain),
                capability_resolver.ActorPolicy(
                    mode=str(actor_mode or "full"), channel=trace.channel),
            )
            report = dict(report)
            report["actor_mode"] = str(actor_mode or "full")
            _CONTEXT_RUNTIME.record_shadow_resolution(trace, report)
            compiled = await asyncio.to_thread(
                _CONTEXT_COMPILER.compile_shadow,
                context_compiler.CompileRequest(
                    task_id=trace.task_id, step_id=trace.step_id,
                    objective=query or "", brain=_brain_root(brain), channel=trace.channel,
                    provider=provider or "unknown", model=model or "unknown", model_kind=kind,
                ),
                report,
            )
            compiler_report = dict(compiled.trace_report)
            calibration = _CONTEXT_RUNTIME.token_estimate_stats(provider, model)
            compiler_report["calibration_samples"] = calibration.get("samples", 0)
            compiler_report["median_abs_pct_error"] = calibration.get("median_abs_pct_error", 0)
            _CONTEXT_RUNTIME.record_compiler_shadow(trace, compiler_report)
        except Exception as exc:
            # Không lưu message lỗi vì có thể chứa path/source; chỉ lưu loại lỗi.
            _CONTEXT_RUNTIME.record_shadow_resolution(trace, {
                "policy_version": capability_resolver.RESOLVER_POLICY_VERSION,
                "registry_revision": trace.registry_revision,
                "miss_class": f"shadow_error:{type(exc).__name__}",
            })

    _track_shadow_task(_job())


def _schedule_registry_discovery_shadow(trace, brain, query, provider, model,
                                        kind="cli", actor_mode="full") -> None:
    """CLI có tool native nên refresh inventory Hub ở task nền, không chặn lượt chat."""
    if not trace:
        return

    async def _discover_then_shadow():
        try:
            root = _brain_root(brain)
            await mcp_hub.discover_all("full", vault_root=root, include_ambient=True)
            tools, route = mcp_hub.registry_inventory(
                "full", vault_root=root, include_ambient=True)
            _schedule_registry_shadow(trace, brain, tools, route, query, provider, model,
                                      kind, actor_mode)
        except Exception as exc:
            _CONTEXT_RUNTIME.record_shadow_resolution(trace, {
                "policy_version": capability_resolver.RESOLVER_POLICY_VERSION,
                "registry_revision": trace.registry_revision,
                "miss_class": f"discovery_error:{type(exc).__name__}",
            })

    _track_shadow_task(_discover_then_shadow())


def _record_quality_shadow(trace, objective: str, response: str, channel: str) -> None:
    # Shadow-only: chạy SAU khi câu trả lời đã có. Mọi exception ở đây phải nuốt tại chỗ,
    # nếu để lọt ra ngoài thì run_turn/_tg sẽ biến một lượt THÀNH CÔNG thành báo lỗi cho user.
    if not trace:
        return
    try:
        report = _CONTEXT_COMPILER.report_for_task(trace.task_id)
        decision = _QUALITY_GATE.evaluate(
            objective, response, channel,
            had_error=bool(trace.had_error), compiler_report=report,
        )
        _CONTEXT_RUNTIME.record_quality_shadow(trace, decision.trace_report())
    except Exception as exc:
        print(f"[quality shadow] {type(exc).__name__}", file=__import__('sys').stderr)


async def _fast_path_core(plan, provider: str, api_key: str, model: str, reasoning: str,
                          runtime_trace, objective: str = "", im_lang_khi_loi: bool = False,
                          channel: str = "dashboard", gui_stream=None, gui_loi=None):
    """Lõi đường tắt, KHÔNG dính kênh nào. Trả (text, model, tokens_in).

    Tách ra khỏi `_execute_fast_path` để Telegram dùng lại được. Trước đó toàn bộ hệ Tiết
    kiệm chỉ nối vào đúng handler WebSocket của dashboard, nên người dùng bấm mức Siêu tiết
    kiệm rồi nhắn qua Telegram vẫn gửi nguyên CLAUDE.md + MEMORY.md mỗi lượt - trang Cài đặt
    báo đã bật, mà kênh họ dùng nhiều nhất thì không đi qua dòng code nào của nó.

    `gui_stream(text)` / `gui_loi(text)` là hai móc gửi tin của kênh; bỏ trống thì lượt chạy
    im lặng và chỗ gọi tự gửi bản đầy đủ (đúng cách Telegram làm - nó gửi MỘT tin cuối chứ
    không stream từng mẩu).
    """
    actual_model = model or "?"
    final_text = ""
    tokens_in = 0
    tokens_out = 0
    _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "fast_path.started", {
        "provider": provider, "model": actual_model, "model_rounds": 1,
        "capsule_hash": plan.capsule_hash,
        "estimated_input_tokens": plan.estimated_input_tokens,
        "reserved_input_tokens": plan.reserved_input_tokens,
        "reserved_output_tokens": plan.reserved_output_tokens,
        "policy_version": plan.policy_version,
    })
    gen = _api_stream(provider, api_key, model, list(plan.messages), reasoning)
    async for ev in gen:
        if ev["type"] == "meta":
            actual_model = ev.get("model") or actual_model
            _CONTEXT_RUNTIME.set_route(runtime_trace, provider, actual_model)
        elif ev["type"] == "usage":
            tokens_in += int(ev.get("input") or 0)
            tokens_out += int(ev.get("output") or 0)
        elif ev["type"] == "text":
            final_text += ev["content"]
            if gui_stream:
                await gui_stream(ev["content"])
        elif ev["type"] == "error":
            if im_lang_khi_loi:
                # Nuốt tại chỗ: chỗ gọi sẽ lui về engine đầy đủ và người dùng vẫn có câu trả
                # lời. Vẫn ghi vào trace để trang chẩn đoán nói được đường tắt đã hỏng vì gì.
                _CONTEXT_RUNTIME.record_runtime_event(
                    runtime_trace, "fast_path.stream_error",
                    {"provider": provider, "model": actual_model})
            elif gui_loi:
                await gui_loi(ev["content"])
    if im_lang_khi_loi and not final_text.strip():
        # Về tay không. KHÔNG gửi gói `response`: gửi là khung chat chốt một bong bóng rỗng
        # rồi lượt lui về engine sẽ chèn thêm bong bóng thứ hai.
        _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "fast_path.empty", {
            "provider": provider, "model": actual_model})
        return "", actual_model, 0
    if tokens_in or tokens_out:
        usage_store.record(provider, actual_model, tokens_in, tokens_out)
        _CONTEXT_RUNTIME.consume_quota(
            runtime_trace, plan.reservation_id, tokens_in, tokens_out
        )
    decision = _QUALITY_GATE.evaluate(
        objective, final_text, channel,
        had_error=bool(runtime_trace and runtime_trace.had_error),
        compiler_report=_CONTEXT_COMPILER.report_for_task(
            runtime_trace.task_id if runtime_trace else ""
        ),
    )
    _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "quality.canary", {
        **decision.trace_report(), "model_rounds": 1,
    })
    _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "fast_path.completed", {
        "provider": provider, "model": actual_model, "model_rounds": 1,
        "response_chars": len(final_text), "quality_status": decision.status,
        "channel": channel,
    })
    return final_text, actual_model, tokens_in


async def _execute_fast_path(plan, provider: str, api_key: str, model: str,
                             reasoning: str, ws, session_id: str, runtime_trace,
                             objective: str = "", im_lang_khi_loi: bool = False):
    """Vỏ WebSocket của đường tắt: stream từng mẩu về khung chat rồi chốt gói `response`."""
    async def _stream(txt):
        await ws.send_text(json.dumps({"type": "stream", "content": txt, "tts": False}))

    async def _loi(txt):
        await ws.send_text(json.dumps({"type": "error", "content": txt}))

    final_text, actual_model, tokens_in = await _fast_path_core(
        plan, provider, api_key, model, reasoning, runtime_trace, objective,
        im_lang_khi_loi, channel="dashboard", gui_stream=_stream, gui_loi=_loi)
    if im_lang_khi_loi and not final_text.strip():
        return "", actual_model
    # Dòng "đi đường nào, tốn bao nhiêu" phải có ở ĐÂY nữa. Bản 0.13.0 gắn nó vào ba nhánh
    # engine mà quên nhánh này, nên đúng những lượt TIẾT KIỆM NHẤT lại là những lượt duy nhất
    # không khoe được gì: khung chat để trống dòng đó, và người dùng không có cách nào biết
    # câu vừa rồi đã đi đường tắt.
    await ws.send_text(json.dumps({
        "type": "response", "content": final_text, "engine": provider,
        "model": actual_model, "session_id": session_id,
        **_ctx_frame(runtime_trace, tokens_in),
    }))
    return final_text, actual_model


async def _execute_readonly_orchestrator(plan, provider: str, api_key: str, model: str,
                                         reasoning: str, ws, session_id: str,
                                         runtime_trace):
    """Adapter WebSocket mỏng; state machine, budget và checkpoint nằm trong Phase 7 runtime."""
    async def emit(event_type: str, payload: dict):
        if event_type == "started":
            await ws.send_text(json.dumps({
                "type": "system",
                "content": (
                    f"Orchestrator read-only: tối đa {payload.get('candidate_count', 0)} "
                    "capability ứng viên, có checkpoint/resume."
                ),
                "task_id": payload.get("task_id") or runtime_trace.task_id,
            }))
        elif event_type == "plan":
            await ws.send_text(json.dumps({
                "type": "system",
                "content": (
                    f"Đã lập {payload.get('step_count', 0)} read step cho vòng "
                    f"{payload.get('cycle', 0)}."
                ),
                "task_id": runtime_trace.task_id,
            }))
        elif event_type == "tool_call":
            await ws.send_text(json.dumps({
                "type": "tool_call", "tool": payload.get("tool") or "read-only",
                "content": f"⚙ MCP read-only: {payload.get('tool') or 'capability'}",
                "task_id": runtime_trace.task_id,
            }))
        elif event_type == "tool_result":
            await ws.send_text(json.dumps({
                "type": "tool_result",
                "content": f"Evidence đã lưu: {payload.get('evidence_ref') or ''}",
                "task_id": runtime_trace.task_id,
            }))

    result = await _get_readonly_orchestrator().run(
        plan, api_key, reasoning, emit, _api_stream
    )
    if result.tokens_in or result.tokens_out:
        usage_store.record(
            provider, result.model or model or "?", result.tokens_in,
            result.tokens_out, result.cost_usd,
        )
    if result.status not in ("COMPLETED",):
        _CONTEXT_RUNTIME.note_error(runtime_trace, result.stop_reason or result.status)
    _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "orchestrator.completed", {
        "status": result.status, "stop_reason": result.stop_reason,
        "model_rounds": result.model_rounds, "evidence_count": len(result.evidence_refs),
        "input_tokens": result.tokens_in, "output_tokens": result.tokens_out,
        "cost_usd": result.cost_usd,
    })
    # Buffer final để Quality Gate trong orchestrator chặn false write claim trước khi client thấy.
    await ws.send_text(json.dumps({
        "type": "stream", "content": result.text, "tts": False,
        "task_id": result.task_id,
    }))
    await ws.send_text(json.dumps({
        "type": "response", "content": result.text, "engine": provider,
        "model": result.model or model or "?", "session_id": session_id,
        "task_id": result.task_id, "stop_reason": result.stop_reason,
        "evidence_refs": list(result.evidence_refs),
        **_ctx_frame(runtime_trace, 0),
    }))
    return result.text, result.model or model or "?"


async def _execute_readonly_path(plan, provider: str, api_key: str, model: str,
                                 reasoning: str, ws, session_id: str, runtime_trace,
                                 objective: str, actor_id: str):
    """Hai model round cố định: exact arguments, gateway read, evidence-only synthesis."""
    actual_model = model or "?"
    tokens_in = 0
    tokens_out = 0
    lease = plan.lease
    _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "readonly_path.started", {
        "provider": provider, "model": actual_model, "model_rounds": 2,
        "capability_id": lease.capability_id if lease else "",
        "capability_revision": lease.revision if lease else "",
        "schema_hash": lease.schema_hash if lease else "",
        "estimated_input_tokens": plan.estimated_input_tokens,
        "reserved_input_tokens": plan.reserved_input_tokens,
        "reserved_output_tokens": plan.reserved_output_tokens,
        "policy_version": plan.policy_version,
    })
    planned = await engine.single_tool_plan(
        provider, api_key, model, list(plan.messages), reasoning, plan.tool_spec
    )
    tokens_in += int(planned.get("input") or 0)
    tokens_out += int(planned.get("output") or 0)
    if planned.get("model"):
        actual_model = planned["model"]
        _CONTEXT_RUNTIME.set_route(runtime_trace, provider, actual_model)
    if planned.get("status") != "ok":
        if lease:
            _CONTEXT_RUNTIME.revoke_capability_lease(
                runtime_trace, lease.lease_id, planned.get("error_code") or "planner_failed"
            )
        uncertain = str(planned.get("error_code") or "").startswith("provider_exception:")
        _CONTEXT_RUNTIME.consume_quota(
            runtime_trace, plan.reservation_id,
            max(tokens_in, plan.estimated_input_tokens if uncertain else 0),
            max(tokens_out, plan.reserved_output_tokens // 2 if uncertain else 0),
        )
        final_text = (
            "Model không tạo được arguments đúng contract cho capability read-only. "
            "Javis đã dừng an toàn, chưa gọi tool và không tự chuyển sang vòng agent cũ."
        )
        _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "readonly_path.failed", {
            "stage": "argument_planner", "error_code": planned.get("error_code") or "unknown",
            "model_rounds": 1, "tool_calls": 0,
        })
        await ws.send_text(json.dumps({
            "type": "response", "content": final_text, "engine": "javis-gateway",
            "model": actual_model, "session_id": session_id,
            **_ctx_frame(runtime_trace, tokens_in),
        }))
        return final_text, actual_model

    await ws.send_text(json.dumps({
        "type": "tool_call", "tool": lease.capability_name,
        "content": f"⚙ MCP read-only: {lease.capability_name}",
    }))
    invocation = await _CAPABILITY_EXECUTOR.invoke(
        runtime_trace, actor_id, lease, planned.get("arguments"), plan.route_call
    )
    if invocation.status != "SUCCEEDED" or invocation.evidence is None:
        _CONTEXT_RUNTIME.consume_quota(
            runtime_trace, plan.reservation_id, tokens_in, tokens_out
        )
        final_text = (
            "Capability read-only đã dừng an toàn trước vòng tổng hợp. "
            f"Mã trạng thái: {invocation.error_code or invocation.status}."
            + (f" Evidence đã lưu: {invocation.evidence.ref}" if invocation.evidence else "")
        )
        _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "readonly_path.failed", {
            "stage": "capability_execute", "error_code": invocation.error_code,
            "model_rounds": 1, "tool_calls": 1,
        })
        await ws.send_text(json.dumps({
            "type": "response", "content": final_text, "engine": "javis-gateway",
            "model": actual_model, "session_id": session_id,
            **_ctx_frame(runtime_trace, tokens_in),
        }))
        return final_text, actual_model

    evidence = invocation.evidence
    await ws.send_text(json.dumps({
        "type": "tool_result", "content": f"Evidence đã lưu: {evidence.ref}",
    }))
    try:
        evidence_payload = json.loads(invocation.model_payload)
    except (TypeError, json.JSONDecodeError):
        evidence_payload = {
            "evidence_ref": evidence.ref, "source_type": evidence.source_type,
            "capability_id": lease.capability_id,
            "capability_name": lease.capability_name,
            "capability_revision": lease.revision,
            "content_hash": evidence.content_hash, "excerpt": evidence.inline_excerpt,
        }
    compiled = _CONTEXT_COMPILER.compile_evidence_final(
        plan.compile_request, evidence_payload
    )
    if compiled.status != "compiled" or compiled.capsule is None:
        _CONTEXT_RUNTIME.consume_quota(
            runtime_trace, plan.reservation_id, tokens_in, tokens_out
        )
        final_text = (
            "Đã đọc dữ liệu và lưu evidence nhưng capsule tổng hợp vượt policy hiện tại. "
            f"Bạn có thể dùng lại nguồn này: {evidence.ref}"
        )
        _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "readonly_path.failed", {
            "stage": "final_compile", "error_code": compiled.status,
            "model_rounds": 1, "tool_calls": 1, "evidence_id": evidence.id,
        })
        await ws.send_text(json.dumps({
            "type": "response", "content": final_text, "engine": "javis-gateway",
            "model": actual_model, "session_id": session_id,
            **_ctx_frame(runtime_trace, tokens_in),
        }))
        return final_text, actual_model

    final_text = ""
    engine_failed = False
    gen = _api_stream(
        provider, api_key, model,
        list(compiled.capsule.rendered_request.get("messages") or []), reasoning,
    )
    async for ev in gen:
        if ev["type"] == "meta":
            actual_model = ev.get("model") or actual_model
            _CONTEXT_RUNTIME.set_route(runtime_trace, provider, actual_model)
        elif ev["type"] == "usage":
            tokens_in += int(ev.get("input") or 0)
            tokens_out += int(ev.get("output") or 0)
        elif ev["type"] == "text":
            final_text += ev["content"]
        elif ev["type"] == "error":
            engine_failed = True
            _CONTEXT_RUNTIME.note_error(runtime_trace, "readonly_final_engine_error")

    if not final_text:
        final_text = (
            "Vòng tổng hợp không trả nội dung, nhưng dữ liệu đọc được đã lưu an toàn tại "
            + evidence.ref
        )

    if tokens_in or tokens_out:
        usage_store.record(provider, actual_model, tokens_in, tokens_out)
    _CONTEXT_RUNTIME.consume_quota(
        runtime_trace, plan.reservation_id,
        max(tokens_in, plan.reserved_input_tokens if engine_failed else 0),
        max(tokens_out, plan.reserved_output_tokens if engine_failed else 0),
    )
    # Gate chấm trên text THÔ của model - footer "Nguồn:" chỉ được nối SAU khi chấm,
    # nếu nối trước thì evidence_ref_missing không bao giờ bắn được (check chết).
    decision = _QUALITY_GATE.evaluate(
        objective, final_text, "dashboard", had_error=engine_failed,
        compiler_report=compiled.trace_report,
        expected_evidence_ref=evidence.ref, read_only=True,
    )
    if evidence.ref not in final_text:
        final_text += "\n\nNguồn: " + evidence.ref
    response_blocked = "false_action_claim" in decision.reasons
    if response_blocked:
        final_text = (
            "Bản tổng hợp của model đã bị Quality Gate chặn vì có tuyên bố hành động không phù hợp "
            "với lease read-only. Dữ liệu gốc vẫn được giữ an toàn tại " + evidence.ref
        )
    # Phase 6 buffer vòng cuối để Quality Gate có thể chặn false action trước khi client thấy text.
    await ws.send_text(json.dumps({
        "type": "stream", "content": final_text, "tts": False,
    }))
    _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "quality.canary", {
        **decision.trace_report(), "model_rounds": 2,
        "evidence_id": evidence.id, "response_blocked": response_blocked,
    })
    _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "readonly_path.completed", {
        "provider": provider, "model": actual_model, "model_rounds": 2,
        "tool_calls": 1, "response_chars": len(final_text),
        "quality_status": decision.status, "evidence_id": evidence.id,
    })
    await ws.send_text(json.dumps({
        "type": "response", "content": final_text, "engine": provider,
        "model": actual_model, "session_id": session_id,
        **_ctx_frame(runtime_trace, tokens_in),
    }))
    return final_text, actual_model


async def _schedule_cancel_action(message: str, brain):
    """Provider-independent delete bridge for cron/reminders.

    The gateway resolves and executes only an unambiguous target. This keeps
    ChatGPT/Codex and OpenRouter models without function calling equally capable
    of deleting schedules, while preserving the no-guess safety rule.
    """
    messages = [{"role": "user", "content": message or ""}]
    if not engine._schedule_cancel_request(messages):
        return None
    try:
        vault_root = _brain_root(brain)
        tools, route = await mcp_hub.discover_all("full", vault_root=vault_root)
        return await engine.schedule_cancel_gateway(messages, tools, route)
    except Exception as exc:
        return {
            "handled": False,
            "error": f"Không truy cập được kho lịch: {type(exc).__name__}: {exc}",
            "calls": [],
        }


def _schedule_cancel_reply(action: dict) -> str:
    if action.get("handled"):
        return str(action.get("result") or "Đã huỷ lịch.")
    if action.get("not_found"):
        return str(action.get("list_result") or "Không có lịch đang chạy để xoá.")
    if action.get("needs_choice"):
        return (
            "Mình đã đọc danh sách lịch thật nhưng có nhiều mục gần giống nhau nên chưa xoá để tránh nhầm. "
            "Bạn nói đúng tên hoặc ID cần xoá:\n\n" + str(action.get("list_result") or "")
        )
    return "⚠ " + str(action.get("error") or "Không thể thao tác lịch.")


def _api_label(prov):
    return {"openrouter": "OpenRouter", "openai": "OpenAI", "anthropic-api": "Anthropic API",
            "openai-oauth": "ChatGPT (OAuth)", "gemini": "Google Gemini",
            "groq": "Groq", "ollama": "Ollama"}.get(prov, prov)

def _reasoning_level(mcfg):
    r = (mcfg or {}).get("reasoning", "off")
    return r if r in engine.REASONING_LEVELS else "off"

# Từ khoá kích hoạt extended thinking của Claude Code (engine cli không có flag chuẩn).
# Claude Code leo thang theo đúng bộ từ khoá này, nên hai mức trên cùng KHÁC nhau thật ở đây
# chứ không phải bịa cho đủ nấc.
_CLI_THINK_KW = {"low": "think", "medium": "think hard", "high": "think harder",
                 "xhigh": "ultrathink", "ultra": "ultrathink"}

def _cli_think(reasoning, message):
    """Chèn gợi ý suy nghĩ vào prompt cho engine Claude Code CLI (off = giữ nguyên)."""
    kw = _CLI_THINK_KW.get(reasoning)
    if not kw:
        return message
    return f"{message}\n\n(Suy nghĩ kỹ trước khi trả lời - {kw})"


def _toml_str(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _write_codex_profile():
    """Ghi ~/.codex/<profile>.config.toml → `codex exec -p <profile>` thấy MCP của Javis.
    Hub bật (mặc định): 1 entry hub - Codex dùng được MỌI transport (cả stdio/internal) + đa tài
    khoản + quyền. Hub tắt: per-server http như cũ. Trả tên profile nếu có server, None nếu rỗng.

    Tên profile lấy từ `mcp_hub.codex_profile_name()` (gắn cổng khi cổng khác mặc định) để nhiều
    bản Javis chạy chung một $HOME không ghi đè profile của nhau - xem chú thích ở hàm đó."""
    if _hub_enabled():
        return mcp_hub.codex_profile("full")
    path = mcp_hub.codex_profile_path()
    lines, seen = [], set()
    for s in mcp_store.servers_for_client():
        name = re.sub(r"[^A-Za-z0-9_]", "_", (s.get("name") or "").strip())
        url = s.get("url")
        headers = s.get("headers") or {}
        if not name or not url or name in seen:
            continue
        seen.add(name)
        lines.append(f"[mcp_servers.{name}]")
        lines.append(f"url = {_toml_str(url)}")
        lines.append("startup_timeout_sec = 20")
        if headers:
            lines.append(f"[mcp_servers.{name}.http_headers]")
            for hk, hv in headers.items():
                lines.append(f"{_toml_str(hk)} = {_toml_str(hv)}")
        lines.append("")
    try:
        if seen:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(lines), encoding="utf-8")
            return mcp_hub.codex_profile_name()
        if path.exists():
            path.unlink()
    except Exception as e:
        print(f"[codex profile] {e}", file=__import__('sys').stderr)
    return None


def _apply_gemini_hub(cli, vault_root=None, mode="full"):
    """Gắn MCP hub của Javis vào tiến trình Gemini CLI, khoá theo đúng brain đang mở.

    Gemini CLI đọc `mcpServers` từ `.gemini/settings.json` của THƯ MỤC LÀM VIỆC, và Javis luôn
    chạy nó với cwd = gốc brain - nên ghi file ngay trong brain vừa đúng chỗ vừa cô lập sẵn
    từng brain. Không đụng `~/.gemini/settings.json` của người dùng: đó là cấu hình cá nhân họ
    dùng cho mọi thứ chạy bằng `gemini`, và nhiều brain thì brain nọ sẽ đọc header brain kia.

    Header giống hệt đường Claude/Codex (`Bearer hub_token` + X-Javis-Mode + X-Javis-Vault) nên
    hub áp đúng một bộ luật quyền cho cả ba engine.
    """
    root = vault_root or getattr(cli, "cwd", None)
    if not root:
        return cli
    hub = None
    if _hub_enabled():
        headers = {"Authorization": f"Bearer {mcp_hub.hub_token()}", "X-Javis-Mode": mode}
        try:
            headers["X-Javis-Vault"] = str(Path(root).expanduser().resolve())
        except Exception:
            headers["X-Javis-Vault"] = str(root)
        hub = {"httpUrl": mcp_hub.hub_url(), "headers": headers,
               "trust": True, "timeout": 20000}
    gemini_cli.ghi_mcp_settings(root, hub)
    return cli


def _apply_antigravity_hub(cli, vault_root=None, mode="full"):
    """Gắn MCP hub của Javis vào tiến trình `agy`.

    Header y hệt ba engine kia (`Bearer hub_token` + X-Javis-Mode + X-Javis-Vault) nên hub áp
    đúng một bộ luật quyền cho cả bốn. Hai chỗ KHÁC hẳn `_apply_gemini_hub`, và cả hai là lý do
    bộ não này chạy suốt mấy bản mà không có lấy một tool nào của Javis:

    - **Hình dạng entry** dựng bằng `antigravity_cli.hub_entry()` chứ không viết tay ở đây.
      `agy` đọc khoá `serverUrl`; `httpUrl` (khoá của Gemini CLI) bị nó bỏ qua không một tiếng
      động. Để hình dạng entry trong module engine là để nó không trôi theo file Gemini lần nữa.
    - **Chỗ đặt file** là cấu hình HOME của `agy`, không phải trong brain - xem khối chú thích ở
      `antigravity_cli.ghi_mcp_settings`. Đổi lại là file dùng chung, nên khi bản CLI có cờ nhận
      file cấu hình riêng thì gắn thêm một file per-brain để hai brain chạy cùng lúc không giẫm
      lên header của nhau (đối xứng `mcp_hub.codex_vault_override` bên Codex).
    """
    root = vault_root or getattr(cli, "cwd", None)
    if not root:
        return cli
    hub = None
    if _hub_enabled():
        headers = {"Authorization": f"Bearer {mcp_hub.hub_token()}", "X-Javis-Mode": mode}
        try:
            headers["X-Javis-Vault"] = str(Path(root).expanduser().resolve())
        except Exception:
            headers["X-Javis-Vault"] = str(root)
        hub = antigravity_cli.hub_entry(mcp_hub.hub_url(), headers)
    antigravity_cli.ghi_mcp_settings(root, hub)
    try:
        cli.mcp_config = mcp_hub.antigravity_config_path(mode, root) if hub else None
    except Exception as e:
        print(f"[antigravity hub] config riêng: {e}", file=__import__('sys').stderr)
    return cli


def _apply_codex_hub(cli, vault_root=None):
    """Gắn profile MCP và brain hiện tại vào riêng tiến trình Codex."""
    cli.profile = _write_codex_profile()
    if _hub_enabled():
        override = mcp_hub.codex_vault_override(vault_root)
        if override and override not in cli.extra_config:
            cli.extra_config.append(override)
    return cli


def _apply_mcp(cli, mode="full", brain=None):
    """Gắn MCP do Javis quản lý vào 1 engine Claude (registry rỗng → không đổi gì, dùng MCP sẵn của máy).
    Hub bật: config 1 entry trỏ hub kèm X-Javis-Mode - deny/perm/audit chặn TẠI hub (lớp cứng),
    không cần --disallowedTools. Hub tắt: per-server + --disallowedTools như cũ."""
    try:
        cli.javis_mode = mode   # engine SDK dùng để enforce min_mode plugin in-process
        # Brain đang làm việc → engine truyền xuống ctx của plugin. KHÔNG suy từ cwd: chat chạy
        # với cwd=CLAUDE_CWD (gốc project, main.py:318) chứ không phải thư mục brain, nên suy từ
        # cwd là luôn trượt đúng ở đường chat - nơi bug thật sự xảy ra.
        cli.javis_vault = _brain_root(brain) if brain else None
        if _hub_enabled():
            cli.mcp_config = mcp_hub.claude_config_path(mode)
            # `strict` = chỉ dùng MCP của Javis, bỏ qua config MCP sẵn có của máy. Ở mức FULL
            # thì cờ này bị bỏ qua, cố ý: connector ambient của tài khoản Claude (Gmail, Google
            # Drive, Lịch) nằm ngoài registry của Javis và chỉ gọi được bằng tool native, nên
            # strict ở mức full là mở allowlist ra rồi lại khoá cửa sau. Người bật strict muốn
            # siết mấy mức DƯỚI; ai đã chủ động chọn Toàn quyền cho một việc thì việc đó phải
            # thật sự toàn quyền, không thì "Toàn quyền" là một cái nhãn nói dối.
            cli.mcp_strict = (mode != "full"
                              and bool(cfgmod.read_settings().get("mcp", {}).get("strict"))
                              and cli.mcp_config is not None)
        else:
            cli.mcp_config = mcp_store.config_path()
            cli.mcp_strict = bool(cfgmod.read_settings().get("mcp", {}).get("strict")) and cli.mcp_config is not None
            dis = mcp_store.disallowed_tools()
            cli.disallowed_tools = dis or None
    except Exception as e:
        print(f"[mcp apply] {e}", file=__import__('sys').stderr)
    return cli


# ============================================================
# Settings - đọc/ghi cấu hình (secret bị che khi đọc)
# ============================================================
@app.get("/providers")
async def providers_get():
    return {"providers": _providers_view(cfgmod.read_settings())}


# ---- ChatGPT OAuth (device-code) - đăng nhập gói ChatGPT thay API key ----
@app.post("/oauth/openai/start")
def oauth_openai_start():
    try:
        return openai_oauth.start_device()
    except Exception as e:
        return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=400)


@app.post("/oauth/openai/poll")
def oauth_openai_poll():
    return openai_oauth.poll()


# Browser OAuth (Authorization Code + PKCE) - cho Workspace chặn device-code.
@app.post("/oauth/openai/browser/start")
def oauth_openai_browser_start():
    try:
        return openai_oauth.start_browser()
    except Exception as e:
        return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=400)


@app.post("/oauth/openai/browser/finish")
async def oauth_openai_browser_finish(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    callback = (body or {}).get("callback") or (body or {}).get("url") or ""
    return openai_oauth.finish_browser(callback)


@app.post("/oauth/openai/disconnect")
def oauth_openai_disconnect():
    cfg = cfgmod.read_settings()
    if _effective_main(cfg).get("provider") == "openai-oauth":   # đang là MAIN → về Claude Code CLI
        _set_main_model(cfg, "anthropic-cli", cfg["model"].get("claude_model") or "opus")
        cfgmod.write_settings(cfg)
    openai_oauth.disconnect()
    return {"ok": True}


@app.get("/oauth/openai/status")
def oauth_openai_status():
    return openai_oauth.status()


# ---- Claude Code auth (provider anthropic-cli) - connect/disconnect như OAuth ----
@app.get("/claude/status")
def claude_status(refresh: bool = False):
    """Trạng thái đăng nhập Claude Code. `refresh=1` = bỏ qua bản nhớ, hỏi lại CLI.

    Nút "Kiểm tra lại" trên thẻ truyền refresh=1; còn lúc vẽ trang thì đọc bản nhớ, khỏi đẻ một
    tiến trình Node mỗi lần mở trang Models.
    """
    return claude_auth_status(bo_qua_cache=bool(refresh))


@app.get("/gemini-cli/status")
def gemini_cli_status():
    """Trạng thái bộ não Gemini CLI: đã cài chưa, đã đăng nhập Google chưa, đăng nhập kiểu gì."""
    d = gemini_cli.auth_status()
    d["cli_path"] = gemini_cli.find_gemini_cli() or ""
    d["huong_dan"] = gemini_cli.login_huong_dan()
    return d


@app.post("/gemini-cli/login-start")
def gemini_cli_login_start():
    """Bước 1: trả link đồng ý của Google để người dùng mở.

    Đòi session trình duyệt: đây là thao tác GẮN một tài khoản Google vào máy này, ngang hàng
    với /auth/tokens - không cho token API tự làm."""
    return gemini_oauth.start_login()


@app.post("/gemini-cli/login-code")
async def gemini_cli_login_code(code: str = Form("")):
    """Bước 2: nhận mã Google hiện ra, đổi lấy token, bắc cầu sang Gemini CLI."""
    return await asyncio.to_thread(gemini_oauth.finish_login, code)


@app.post("/gemini-cli/logout")
def gemini_cli_logout():
    """Ngắt tài khoản Google khỏi Javis (không đụng tới đăng nhập bằng `gemini` trong terminal)."""
    gemini_oauth.disconnect()
    return {"ok": True}


@app.post("/gemini-cli/check")
async def gemini_cli_check():
    """Chạy thử MỘT lượt thật để biết chắc gói đang dùng được.

    File credential còn nằm đó không có nghĩa là còn dùng được (token hết hạn mà refresh hỏng
    thì file vẫn nguyên). Trang Models cần câu trả lời dứt khoát, và đây là cách duy nhất có nó.
    """
    return await asyncio.to_thread(gemini_cli.kiem_tra_nhanh)


@app.get("/antigravity/status")
def antigravity_status():
    """Trạng thái Antigravity CLI cho trang Models."""
    d = antigravity_cli.auth_status()
    d["cli_path"] = antigravity_cli.find_antigravity_cli() or ""
    d["cai_lenh"] = antigravity_cli.lenh_cai()
    d["huong_dan"] = antigravity_cli.login_huong_dan()
    return d


@app.post("/antigravity/check")
async def antigravity_check(brain: str = "brain"):
    """Chạy thử MỘT lượt thật, VÀ soát lại xem hub MCP đã vào cấu hình của `agy` chưa.

    Không dùng lại kết quả `agy models` đã nhớ trong RAM: nó chỉ nói tài khoản còn sống, chưa
    nói luồng chat có chạy không - mà đúng chỗ đó là chỗ Gemini CLI gãy hồi Google ngắt hạng
    cá nhân. Nút này phải trả lời được câu "chat được chưa", nên chạy thật một lượt.

    Phần `mcp` thêm vào (0.43.0) canh đúng hạng lỗi đã ba lần lọt lưới: cấu hình ghi thành công
    nhưng SAI CHỖ hoặc SAI KHOÁ, `agy` chạy trơn tru mà không có lấy một tool nào của Javis, và
    không ở đâu có một câu lỗi để lần ra. Ghi lại cấu hình rồi ĐỌC LẠI chính file đó.
    """
    root = _brain_root(brain)
    try:
        _apply_antigravity_hub(_types.SimpleNamespace(cwd=root), root)
    except Exception as e:
        print(f"[antigravity check] ghi cấu hình MCP: {e}", file=__import__('sys').stderr)
    d = await asyncio.to_thread(antigravity_cli.kiem_tra_nhanh)
    try:
        mcp = antigravity_cli.trang_thai_mcp(root)
        mcp["hub_bat"] = _hub_enabled()
        d["mcp"] = mcp
    except Exception as e:
        d["mcp"] = {"ok": False, "files": [], "thieu": [], "loi": f"{type(e).__name__}: {e}"}
    return d


# Không có endpoint đăng nhập cho `agy`, và đó là quyết định có lý do (0.32.2). Bản trước lái
# luồng đăng nhập của CLI qua một pseudo-terminal: chạy được trên Linux nhưng đẻ ra một ô
# terminal nhỏ trên trang mà bấm vào không ăn, còn Windows thì không có PTY nên luôn tắc. Người
# dùng `agy` đều là dân code sẵn terminal trong tay, nên gõ một lệnh gọn hơn hẳn một luồng UI
# nửa vời. Thẻ Models chỉ đưa lệnh và nút Kiểm tra lại.


@app.post("/claude/login")
def claude_login():
    return claude_auth_login()


@app.post("/claude/login-start")
def claude_login_start():
    """Đăng nhập Claude NGAY TRÊN UI: trả link để user mở (chạy được trên VPS headless)."""
    return auth_login_ui_start()


@app.post("/claude/login-code")
def claude_login_code(code: str = Form("")):
    """Nhận code user dán sau khi mở link đăng nhập."""
    return auth_login_ui_code(code)


@app.post("/claude/logout")
def claude_logout():
    return claude_auth_logout()


# ---- MCP do Javis quản lý (engine Claude Code) ----
@app.get("/mcp/list")
async def mcp_list():
    return {"servers": mcp_store.list_servers(),
            "strict": bool(cfgmod.read_settings().get("mcp", {}).get("strict"))}


@app.post("/mcp/add")
async def mcp_add(request: Request):
    data = await request.json()
    if not (data.get("name") or "").strip():
        return JSONResponse({"ok": False, "error": "Thiếu tên server"}, status_code=400)
    codex_ok = False
    if (data.get("auth") or "header") == "oauth":
        # Đăng ký native để Claude Code tự lo OAuth (cần xác thực 1 lần trong terminal: claude → /mcp)
        res = mcp_native_add(data["name"].strip(), (data.get("url") or "").strip(),
                             data.get("transport", "http"), None, data.get("client_id") or None)
        if not res.get("ok"):
            return JSONResponse({"ok": False, "error": res.get("error") or res.get("out") or "native add lỗi"}, status_code=400)
        # Đối xứng cho engine ChatGPT: server OAuth không đi qua hub được (CLI tự lo OAuth) nên
        # đăng ký thêm vào kho MCP gốc của Codex (best-effort - chưa cài codex thì bỏ qua).
        # User xác thực 1 lần bằng `codex mcp login <tên>`.
        if find_codex_cli():
            codex_ok = bool(codex_mcp_native_add(data["name"].strip(),
                                                 url=(data.get("url") or "").strip()).get("ok"))
    sid = mcp_store.add_server(data)
    mcp_hub.invalidate_cache()
    _write_codex_profile()
    return {"ok": True, "id": sid, "oauth": (data.get("auth") or "header") == "oauth",
            "codex": codex_ok}


@app.post("/mcp/update")
async def mcp_update(request: Request):
    data = await request.json()
    ok = mcp_store.update_server(data.get("id"), data)
    mcp_hub.invalidate_cache()
    return {"ok": ok}


@app.post("/mcp/delete")
async def mcp_delete(request: Request):
    data = await request.json()
    s = next((x for x in mcp_store.list_servers() if x["id"] == data.get("id")), None)
    if s and s.get("auth") == "oauth" and s.get("name"):
        mcp_native_remove(s["name"])
        if find_codex_cli():
            codex_mcp_native_remove(s["name"])   # gỡ cả bản đã đăng ký vào kho gốc Codex
    ok = mcp_store.delete_server(data.get("id"))
    mcp_hub.invalidate_cache()
    _write_codex_profile()
    return {"ok": ok}


@app.post("/mcp/toggle")
async def mcp_toggle(request: Request):
    data = await request.json()
    en = mcp_store.toggle_server(data.get("id"))
    mcp_hub.invalidate_cache()
    _write_codex_profile()
    return {"ok": en is not None, "enabled": en}


@app.post("/mcp/strict")
async def mcp_strict(request: Request):
    data = await request.json()
    cfg = cfgmod.read_settings()
    cfg.setdefault("mcp", {})["strict"] = bool(data.get("strict"))
    cfgmod.write_settings(cfg)
    return {"ok": True}


@app.get("/mcp/ambient")
def mcp_ambient():
    """MCP sẵn của từng CLI - chỉ hiển thị. servers = Claude Code (đồng bộ claude.ai);
    codex_servers = kho MCP gốc của Codex (~/.codex/config.toml, user tự `codex mcp add`).
    Engine ChatGPT nạp kho gốc đó vì profile javis chỉ phủ THÊM lên config gốc."""
    return {"servers": mcp_native_list(), "codex_servers": codex_mcp_native_list()}


@app.get("/mcp/native-status")
def mcp_native_status_ep(name: str = Query(...), engine: str = Query("claude")):
    return codex_mcp_native_status(name) if engine == "codex" else mcp_native_status(name)


@app.post("/mcp/oauth-auth")
async def mcp_oauth_auth(request: Request):
    """Mở terminal xác thực OAuth MCP (chỉ máy local). Mặc định: chạy claude rồi user gõ /mcp.
    Body {"engine":"codex","name":...}: chạy `codex mcp login <tên>` cho kho gốc Codex."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    if (data or {}).get("engine") == "codex":
        return codex_mcp_open_login_terminal((data or {}).get("name") or "")
    return mcp_open_auth_terminal()


# ============================================================
# KHO KẾT NỐI (connector catalog + đa tài khoản) + MCP HUB
# ============================================================
@app.post("/hub/mcp")
async def hub_mcp(request: Request):
    """Endpoint MCP hub - Claude Code/Codex đấu vào đây (auth bằng Bearer hub_token riêng)."""
    return await mcp_hub.handle_http(request)


@app.get("/connect/catalog")
async def connect_catalog():
    return {"catalog": mcp_catalog.public_catalog(), "connections": mcp_store.list_connections(),
            "strict": bool(cfgmod.read_settings().get("mcp", {}).get("strict")), "hub": _hub_enabled()}


@app.post("/connect/add")
async def connect_add(request: Request):
    """Thêm tài khoản cho 1 connector trong kho: lưu tạm → VALIDATE ngay (gọi tool xác minh,
    tự lấy tên shop làm label) → key sai thì xoá, không lưu rác."""
    data = await request.json()
    con_id = (data.get("connector_id") or "").strip()
    # Connector cần trình duyệt TRÊN MÁY CHẠY JAVIS (workspace-mcp: OAuth callback cứng
    # localhost:8000) mà user đang mở dashboard qua domain public → luồng đăng nhập Google
    # chắc chắn đứt ở ERR_CONNECTION_REFUSED (issue #112). Chặn kèm lời giải thích + đường
    # thay thế; can_force để ca đặc biệt (đấu sẵn từ xa, sang máy bấm đồng ý sau) vẫn đi được.
    if (mcp_catalog.get(con_id) or {}).get("needs_local_browser") and not data.get("force"):
        host_thay = web_security.external_base(
            request.url.scheme, request.url.netloc,
            request.headers.get("x-forwarded-proto", ""),
            request.headers.get("x-forwarded-host", ""))
        if not web_security.host_kieu_local(host_thay):
            return {"ok": False, "can_force": True, "error":
                    "Kết nối này chạy OAuth trên CHÍNH MÁY cài Javis (Google sẽ chuyển về "
                    "localhost:8000), mà bạn đang mở Javis qua domain public - đăng nhập Google "
                    "sẽ đứt giữa chừng với lỗi không kết nối được. Trên VPS hãy dùng thẻ Lịch "
                    "và Gmail riêng (hai thẻ đó đăng nhập ngay trong dashboard). Nếu máy chạy "
                    "Javis có màn hình và bạn sẽ bấm đồng ý trên đó, bấm Kết nối lần nữa."}
    # Dùng lại key OAuth client của connection khác (vd Gmail dùng lại key đã tạo cho
    # Calendar) - copy server-side, secrets không bao giờ về browser.
    fields_in = mcp_store.reuse_client_fields(
        mcp_catalog.get(con_id), data.get("fields") or {}, (data.get("reuse_from") or "").strip())
    # Bước ĐỔI CREDENTIAL (nếu connector khai auth.exchange): vd Google Keep đổi App Password
    # thành master token ngay tại đây, để người dùng khỏi phải mở terminal. Hàm này LUÔN xoá các
    # field khai trong `drop` (như app_password) nên thứ đó không bao giờ xuống tới mcp_store.
    fields, ex_err = cred_exchange.run(mcp_catalog.get(con_id), fields_in)
    if ex_err:
        return {"ok": False, "error": ex_err}
    cid, err = mcp_store.add_connection(con_id, {
        "label": (data.get("label") or "").strip(), "fields": fields})
    if err:
        return {"ok": False, "error": err}
    val = await mcp_hub.validate_connection(cid)
    if not val.get("ok"):
        mcp_store.delete_connection(cid)
        return {"ok": False, "error": val.get("error") or "Không kết nối được"}
    if val.get("label") and not (data.get("label") or "").strip():
        mcp_store.update_connection(cid, {"label": val["label"]})
    mcp_hub.invalidate_cache()
    _write_codex_profile()
    c = mcp_store.get_connection(cid) or {}
    return {"ok": True, "id": cid, "label": c.get("label"), "tools": val.get("tools", 0)}


@app.post("/connect/test")
async def connect_test(request: Request):
    data = await request.json()
    return await mcp_hub.validate_connection(data.get("id"))


@app.get("/connect/health")
async def connect_health_all():
    """Sức khoẻ mọi connection (vòng nền connect_health cập nhật) + đèn báo não (engines).
    Connection chưa check thì vắng mặt - UI hiểu là 'chưa rõ' (chấm vàng)."""
    return {"health": connect_health.snapshot(), "engines": connect_health.engines_snapshot()}


@app.post("/connect/health/check")
async def connect_health_check(request: Request):
    """Ép check ngay một connection (nút test/refresh trên chip tài khoản)."""
    data = await request.json()
    rec = await connect_health.check_by_id((data.get("id") or "").strip())
    return {"ok": rec.get("ok", False), **rec}


@app.get("/connect/substack/resolve-uid")
async def connect_substack_resolve_uid(q: str = Query("")):
    """Tra User ID (+ gợi ý Publication URL) của một tài khoản Substack từ handle hoặc URL trang
    Hồ sơ. Substack đã đổi URL Hồ sơ sang dạng substack.com/@handle (không còn dãy số), nên trợ lý
    lấy nhanh ở trang Docs gọi endpoint này - server hỏi API CÔNG KHAI của Substack (không cần đăng
    nhập Substack, không đụng secret) rồi trả về id. Endpoint vẫn sau auth guard (cần session Javis)."""
    import re
    raw = (q or "").strip()
    m = re.search(r"/profile/(\d{3,})", raw)   # URL /profile/<id>-name kiểu cũ: số chính là user_id
    if m:
        return {"ok": True, "user_id": int(m.group(1)), "name": "", "publications": []}
    m = re.search(r"@([A-Za-z0-9_-]+)", raw) or re.search(r"substack\.com/([A-Za-z0-9_-]+)", raw)
    handle = (m.group(1) if m else raw).lstrip("@").strip().strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", handle):
        return {"ok": False, "error": "Handle không hợp lệ. Dán link trang Hồ sơ (vd substack.com/@ten) hoặc chính handle."}
    # Substack đứng sau Cloudflare - chặn httpx theo TLS fingerprint (403), nhưng để curl qua.
    # Dùng curl (có sẵn cả trên Windows lẫn Docker image); handle đã validate + truyền dạng argv
    # riêng (không qua shell) nên không có nguy cơ chèn lệnh/SSRF.
    import shutil
    curl = shutil.which("curl") or "curl"
    url = f"https://substack.com/api/v1/user/{handle}/public_profile"
    try:
        proc = await asyncio.create_subprocess_exec(
            curl, "-s", "--max-time", "12", "-A", "Mozilla/5.0", "-H", "accept: application/json", url,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            **winproc.kwargs_no_window())
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
    except Exception as e:
        return {"ok": False, "error": f"Không gọi được Substack ({type(e).__name__}). Dùng Cách B (Console) nếu vẫn lỗi."}
    try:
        d = json.loads(out.decode("utf-8", "replace"))
    except Exception:
        return {"ok": False, "error": f"Không đọc được hồ sơ '{handle}'. Kiểm tra lại handle, hoặc dùng Cách B (Console)."}
    if isinstance(d, dict) and d.get("error"):
        return {"ok": False, "error": f"Substack: {d.get('error')} - kiểm tra lại handle '{handle}'."}
    uid = d.get("id")
    if not uid:
        return {"ok": False, "error": "Hồ sơ Substack không trả về id."}
    pubs, seen = [], set()
    for pu in (d.get("publicationUsers") or []):
        p = pu.get("publication") or {}
        cd, sub = p.get("custom_domain"), p.get("subdomain")
        url = f"https://{cd}" if cd else (f"https://{sub}.substack.com" if sub else "")
        if url and url not in seen:
            seen.add(url)
            pubs.append({"name": p.get("name") or sub or "", "url": url})
    return {"ok": True, "user_id": uid, "name": d.get("name") or "", "handle": handle, "publications": pubs}


@app.post("/connect/update")
async def connect_update(request: Request):
    data = await request.json()
    ok = mcp_store.update_connection(data.get("id"), data)
    mcp_hub.invalidate_cache()
    return {"ok": ok}


@app.post("/connect/toggle")
async def connect_toggle(request: Request):
    data = await request.json()
    en = mcp_store.toggle_connection(data.get("id"))
    mcp_hub.invalidate_cache()
    _write_codex_profile()
    return {"ok": en is not None, "enabled": en}


@app.post("/connect/delete")
async def connect_delete(request: Request):
    data = await request.json()
    cid = data.get("id")
    oauth_mcp.forget(cid)
    connect_health.forget(cid)   # khỏi hiện trạng thái ma của connection đã xoá
    ok = mcp_store.delete_connection(cid)
    mcp_hub.invalidate_cache()
    _write_codex_profile()
    return {"ok": ok}


@app.post("/connect/relogin")
async def connect_relogin(request: Request):
    """Vứt token mà connector tự cache ngoài Javis (workspace-mcp) mà GIỮ nguyên kết nối.

    Vì sao cần một nút riêng: với connector loại này, nút Kết nối lại chỉ lưu lại Client ID/Secret
    chứ không đụng được token - server con đã có credential trên đĩa nên không bao giờ mở lại màn
    đăng nhập Google. Token cấp thiếu quyền thì thiếu mãi. Dọn kho token xong, lần gọi tool kế
    tiếp server tự mở trình duyệt xin lại quyền theo đúng bộ hiện hành."""
    data = await request.json()
    cid = (data.get("id") or "").strip()
    if not cid:
        return JSONResponse({"ok": False, "error": "Thiếu id kết nối"}, status_code=400)
    done = mcp_store.forget_cred_dir_by_id(cid)
    mcp_client.pool.invalidate(cid)   # giết tiến trình con đang giữ token cũ trong RAM
    mcp_hub.invalidate_cache()
    connect_health.forget(cid)
    return {"ok": True, "cleared": done,
            "message": ("Đã xoá đăng nhập Google cũ. Nhờ Javis làm một việc bất kỳ với nguồn này, "
                        "trình duyệt trên máy chạy Javis sẽ mở để bạn cấp lại quyền."
                        if done else
                        "Kết nối này không tự giữ token riêng, hoặc chưa từng đăng nhập.")}


@app.post("/connect/default")
async def connect_default(request: Request):
    data = await request.json()
    return {"ok": mcp_store.set_default(data.get("id"))}


@app.get("/connect/audit")
async def connect_audit(limit: int = Query(80), id: str = Query("")):
    return {"entries": mcp_hub.audit_tail(limit=min(int(limit or 80), 500), conn_id=(id or None))}


# ---- Zalo: đăng nhập QR ngay trong UI ----
@app.post("/connect/zalo/start")
async def connect_zalo_start(request: Request):
    data = await request.json()
    return zalo_login.start(label=(data.get("label") or "").strip() or None)


@app.get("/connect/zalo/status")
async def connect_zalo_status(sid: str = Query(...)):
    st = zalo_login.status(sid)
    if st.get("state") == "done":
        mcp_hub.invalidate_cache()
        _write_codex_profile()
    return st


@app.post("/connect/zalo/cancel")
async def connect_zalo_cancel(request: Request):
    data = await request.json()
    return zalo_login.cancel(data.get("sid"))


# ---- OAuth chuẩn MCP: Javis tự giữ token, không cần terminal ----
@app.post("/connect/oauth/start")
async def connect_oauth_start(request: Request):
    data = await request.json()
    conn_id = data.get("id")
    # fields: client_id/secret user tự khai (BYO) cho provider không DCR (vd Google). Rỗng với Meta.
    fields = {k: v for k, v in (data.get("fields") or {}).items() if v}
    # Dùng lại key client từ connection Google khác (copy server-side, xem reuse_client_fields)
    fields = mcp_store.reuse_client_fields(
        mcp_catalog.get((data.get("connector_id") or "").strip()), fields,
        (data.get("reuse_from") or "").strip())
    if not conn_id and data.get("connector_id"):
        # Tái dùng connection oauth dở dang (chưa có token) của connector này -
        # tránh mỗi lần bấm nút lại đẻ 1 connection mồ côi.
        pend = next((c for c in mcp_store.list_connections()
                     if c.get("connector_id") == data["connector_id"] and c.get("auth") == "oauth"
                     and not oauth_mcp.status(c["id"]).get("connected")), None)
        if pend:
            conn_id = pend["id"]
            if fields:   # cập nhật lại client_id/secret nếu user nhập mới ở lần bấm này
                mcp_store.update_connection(conn_id, {"fields": fields})
        else:
            conn_id, err = mcp_store.add_connection(data["connector_id"],
                {"label": (data.get("label") or "").strip(), "auth": "oauth", "fields": fields})
            if err:
                return {"ok": False, "error": err}
    elif conn_id and fields:
        mcp_store.update_connection(conn_id, {"fields": fields})
    # Địa chỉ quay về NHƯ NGƯỜI DÙNG THẤY: sau reverse proxy (VPS https) phải theo
    # X-Forwarded-Proto/Host, không thì dựng ra http://... và Meta/Google từ chối.
    redirect = web_security.external_base(
        request.url.scheme, request.url.netloc,
        request.headers.get("x-forwarded-proto", ""),
        request.headers.get("x-forwarded-host", "")) + "/connect/oauth/callback"
    res = await oauth_mcp.start_auth(conn_id, redirect)
    # start_auth FAIL (vd Meta MCP beta allowlist từ chối DCR) mà connection chưa từng có
    # token → XOÁ ngay, đừng để "xác chưa đăng nhập" nằm lại trên trang Kết nối như tài
    # khoản thật (vụ Meta Ads xoá rồi cứ mọc lại mỗi lần bấm thử nút Kết nối).
    if not res.get("ok") and conn_id and not oauth_mcp.status(conn_id).get("connected"):
        oauth_mcp.forget(conn_id)
        connect_health.forget(conn_id)
        mcp_store.delete_connection(conn_id)
        mcp_hub.invalidate_cache()
        return {"ok": False, "error": res.get("error") or "Không mở được trang đăng nhập."}
    res["id"] = conn_id
    return res


@app.get("/connect/oauth/callback")
async def connect_oauth_callback(state: str = Query(""), code: str = Query("")):
    res = await oauth_mcp.handle_callback(state, code)
    mcp_hub.invalidate_cache()
    if res.get("ok"):
        _write_codex_profile()
        # Tự đặt tên tài khoản như flow dán key (vd lấy tên tài khoản ads từ Meta) -
        # chỉ ở lần đăng nhập ĐẦU và khi label còn là tên mặc định (đăng nhập lại giữ tên user
        # đã đặt, kể cả khi trùng tên connector); lỗi thì bỏ qua, không phá trang báo thành công.
        try:
            cid = res.get("conn_id")
            c = mcp_store.get_connection(cid) or {}
            con = mcp_catalog.get(c.get("connector_id")) or {}
            if (cid and res.get("first_auth", True)
                    and c.get("label") in ("", None, con.get("name"), c.get("connector_id"))):
                label = res.get("email") or ""   # email từ id_token (Google) chắc chắn hơn validate
                if not label:
                    val = await mcp_hub.validate_connection(cid)
                    label = val.get("label") or ""
                if label:
                    mcp_store.update_connection(cid, {"label": label})
        except Exception as e:
            print(f"[oauth label] {e}")
        html = ("<html><body style='font-family:sans-serif;background:#111;color:#eee;text-align:center;padding-top:80px'>"
                "<h2>✓ Đã kết nối thành công</h2><p>Đóng tab này và quay lại Javis, bấm Làm mới ở trang Kết nối.</p></body></html>")
    else:
        html = (f"<html><body style='font-family:sans-serif;background:#111;color:#eee;text-align:center;padding-top:80px'>"
                f"<h2>⚠ Kết nối thất bại</h2><p>{res.get('error', '')}</p></body></html>")
    return HTMLResponse(html)


@app.get("/settings")
async def settings_get():
    cfg = cfgmod.read_settings()
    safe = json.loads(json.dumps(cfg))
    safe["auth"] = {"username": cfg["auth"].get("username", ""), "has_password": bool(cfg["auth"].get("password_hash"))}
    # Danh sách ngôn ngữ đi kèm cài đặt luôn, thay vì bắt dashboard gọi thêm một endpoint.
    # Nguồn duy nhất là sổ đăng ký phía server: dashboard KHÔNG khai lại danh sách, nếu không
    # thì thêm ngôn ngữ mới phải nhớ sửa hai chỗ và chỗ bị quên hỏng trong im lặng.
    safe["lang_list"] = lang_registry.cho_giao_dien()
    # Gói locale (múi giờ, tiền tệ, locale định dạng số). Dashboard KHÔNG tự suy nó từ ngôn
    # ngữ: hai thứ đó tách rời, người dùng đọc tiếng Anh mà vẫn ngồi ở UTC+7 là bình thường.
    safe["locale_fmt"] = localefmt.cho_giao_dien()
    for kf in ("openrouter_key", "anthropic_api_key", "openai_api_key", "gemini_api_key", "groq_api_key"):
        k = cfg["model"].get(kf, "")
        safe["model"][kf] = ("••••" + k[-4:]) if k else ""
        safe["model"][kf + "_set"] = bool(k)
    o = cfg["model"].get("openai_oauth") or {}
    safe["model"]["openai_oauth"] = {   # che token, chỉ lộ trạng thái
        "connected": bool(o.get("access_token") or o.get("refresh_token")),
        "account_id": o.get("account_id", ""), "plan": o.get("plan", ""),
    }
    tok = cfg["telegram"].get("token", "")
    safe["telegram"]["token"] = ("••••" + tok[-4:]) if tok else ""
    safe["telegram"]["token_set"] = bool(tok)
    vk = (cfg.get("voice", {}) or {}).get("elevenlabs_key", "")
    safe.setdefault("voice", {})
    safe["voice"]["elevenlabs_key"] = ("••••" + vk[-4:]) if vk else ""
    safe["voice"]["elevenlabs_key_set"] = bool(vk)
    bt = (cfg.get("backup", {}) or {}).get("token", "")
    safe.setdefault("backup", {})
    safe["backup"]["token"] = ("••••" + bt[-4:]) if bt else ""
    safe["backup"]["token_set"] = bool(bt)
    safe["model"]["providers"] = _providers_view(cfg)   # danh sách provider + trạng thái + model
    safe["model"]["main"] = _effective_main(cfg)         # model chính hiệu lực (suy từ legacy nếu cần)
    return safe


@app.post("/settings")
async def settings_set(section: str = Form(...), data: str = Form("{}")):
    cfg = cfgmod.read_settings()
    try:
        patch = json.loads(data)
    except json.JSONDecodeError:
        return JSONResponse({"ok": False, "error": "data không phải JSON"}, status_code=400)

    if section == "locale":
        # Nhánh RIÊNG chứ không nhét vào "general": endpoint này dùng allowlist TỪNG KEY chứ
        # không merge, nên key nào không có tên trong một nhánh sẽ bị bỏ trong khi vẫn trả
        # {"ok": true} và nút vẫn hiện "Đã lưu". Một cụm cài đặt mới mà quên nhánh của nó thì
        # người dùng bấm lưu, thấy báo thành công, F5 xong mất sạch - không lỗi, không log.
        lc = cfg.setdefault("locale", {})
        if "reply_lang" in patch:
            v = str(patch["reply_lang"] or "").strip().lower()
            # "auto" là giá trị HỢP LỆ, không phải chuỗi rỗng: nó nghĩa là "bám theo người
            # dùng", khác hẳn với "chưa chọn".
            lc["reply_lang"] = "auto" if v in ("", "auto") else (lang_registry.chuan_hoa(v) or "auto")
        if "ui_lang" in patch:
            lc["ui_lang"] = lang_registry.chuan_hoa(patch["ui_lang"]) or lang_registry.MAC_DINH
        if "tz" in patch:
            lc["tz"] = str(patch["tz"] or "").strip() or "Asia/Ho_Chi_Minh"
        if "currency" in patch:
            lc["currency"] = str(patch["currency"] or "").strip().upper() or "VND"
    elif section == "general":
        if "workspace_name" in patch:
            cfg["workspace_name"] = patch["workspace_name"] or "Javis OS"
        if "setup_done" in patch:
            cfg["setup_done"] = bool(patch["setup_done"])
    elif section == "model":
        m = cfg["model"]
        # Đặt model chính theo provider (UI mới)
        if patch.get("main"):
            prov = patch["main"].get("provider"); mod = patch["main"].get("model")
            if _provider_def(prov) and mod:
                _set_main_model(cfg, prov, mod)
        # Nhập credential provider (chỉ ghi khi có giá trị mới - tránh xoá bằng giá trị che ••••)
        for kf in ("openrouter_key", "anthropic_api_key", "openai_api_key", "gemini_api_key", "groq_api_key"):
            if patch.get(kf):
                m[kf] = patch[kf]
        # Ngắt kết nối 1 provider (xoá key). Nếu nó đang là MAIN → quay về Claude Code CLI để chat không gãy.
        if patch.get("clear_key"):
            d = _provider_def(patch["clear_key"])
            if d and d.get("key_field"):
                m[d["key_field"]] = ""
                if _effective_main(cfg).get("provider") == patch["clear_key"]:
                    _set_main_model(cfg, "anthropic-cli", m.get("claude_model") or "opus")
        # Gói Claude Code xác thực bằng gì: phiên subscription sẵn có, hay API key riêng.
        # Giá trị lạ về "subscription" thay vì báo lỗi - đây là ô hai lựa chọn, gõ sai thì lui
        # về cái không tốn tiền của người dùng chứ không làm chết đường chat.
        if "claude_auth" in patch:
            m["claude_auth"] = (claude_auth.API_KEY
                                if str(patch["claude_auth"] or "").strip().lower() == claude_auth.API_KEY
                                else claude_auth.SUBSCRIPTION)
        if "auxiliary" in patch:   # model phụ cho việc nền (provider + model)
            aux_patch = patch["auxiliary"] or {}
            aux = m.setdefault("auxiliary", {})
            aux["model"] = aux_patch.get("model", "")
            # Thiếu provider (client cũ) = Claude, đúng hành vi trước khi mở nhiều provider.
            prov = aux_patch.get("provider") or aux_engine.CLAUDE
            aux["provider"] = prov if _provider_def(prov) else aux_engine.CLAUDE
        # Độ sâu suy nghĩ. Danh sách nấc lấy từ engine.REASONING_LEVELS - đường LƯU này và
        # đường ĐỌC (_reasoning_level) phải soi CÙNG một nguồn, nếu không thêm nấc mới là
        # giao diện cho chọn mà server lặng lẽ hạ về "off".
        if "reasoning" in patch:
            r = patch["reasoning"]
            m["reasoning"] = r if r in engine.REASONING_LEVELS else "off"
        # Legacy trực tiếp (tương thích ngược)
        for k in ("engine", "claude_model", "openrouter_model"):
            if k in patch:
                m[k] = patch[k]
    elif section == "telegram":
        t = cfg["telegram"]
        if "enabled" in patch:
            t["enabled"] = bool(patch["enabled"])
        if "chat_id" in patch:
            # Nhận MỘT hoặc NHIỀU ID ("id1, id2" / list) → chuẩn hoá lưu "id1,id2".
            t["chat_id"] = ",".join(tg_parse_ids(patch["chat_id"]))
        if patch.get("token"):
            t["token"] = patch["token"]
    elif section == "zalo_bot":
        # Cùng khuôn với telegram. Id Zalo là chuỗi HEX chứ không phải số, nhưng `tg_parse_ids`
        # chỉ tách và bỏ trùng chứ không ép kiểu nên dùng chung được.
        z = cfg.setdefault("zalo_bot", {"enabled": False, "token": "", "chat_id": ""})
        if "enabled" in patch:
            z["enabled"] = bool(patch["enabled"])
        if "chat_id" in patch:
            z["chat_id"] = ",".join(tg_parse_ids(patch["chat_id"]))
        if patch.get("token"):
            z["token"] = patch["token"]
    elif section == "dashboard":
        cfg.setdefault("dashboard", {})
        if "graph_enabled" in patch:
            cfg["dashboard"]["graph_enabled"] = bool(patch["graph_enabled"])
    elif section == "image":
        cfg.setdefault("image", {})
        if "strip_c2pa" in patch:
            cfg["image"]["strip_c2pa"] = bool(patch["strip_c2pa"])
    elif section == "voice":
        v = cfg.setdefault("voice", {})
        if patch.get("tts_provider") in ("edge", "openai", "elevenlabs"):
            v["tts_provider"] = patch["tts_provider"]
        for k in ("openai_tts_voice", "openai_tts_model", "elevenlabs_voice", "elevenlabs_model"):
            if patch.get(k):
                v[k] = str(patch[k]).strip()
        # Chỉ ghi khi có key mới THẬT: client lỡ gửi lại giá trị che "••••abcd" (lấy từ GET
        # /settings rồi POST nguyên object về) mà lưu thì đè mất key thật.
        if patch.get("elevenlabs_key") and not patch["elevenlabs_key"].strip().startswith("••••"):
            v["elevenlabs_key"] = patch["elevenlabs_key"].strip()
    elif section == "password":
        # Đổi mật khẩu KHÔNG đi qua đây nữa - xem /auth/password. Đường này không đòi mật khẩu
        # hiện tại VÀ nhận cả token API scope `full`, nghĩa là một token rò ra là đổi được mật
        # khẩu chủ máy rồi khoá chính chủ ra ngoài. Nó cũng nhận mật khẩu 4 ký tự trong khi mọi
        # đường khác đòi 8.
        return JSONResponse({"ok": False, "error": "Đổi mật khẩu chuyển sang trang Tài khoản "
                                                   "(phải nhập mật khẩu hiện tại). Tải lại trang "
                                                   "nếu vẫn thấy form cũ."}, status_code=400)
    else:
        return JSONResponse({"ok": False, "error": "section không hợp lệ"}, status_code=400)

    cfgmod.write_settings(cfg)
    if section == "telegram":
        try:
            restart_telegram()   # áp cấu hình bot ngay
        except Exception as e:
            print(f"[telegram restart] {e}", file=__import__('sys').stderr)
    if section == "zalo_bot":
        try:
            restart_zalo_bot()   # áp cấu hình bot ngay
        except Exception as e:
            print(f"[zalo restart] {e}", file=__import__('sys').stderr)
    if section == "voice":
        cfgmod.apply_tool_env(cfg)   # key ElevenLabs -> env cho tool ngoài (video-use) ngay, không cần restart
    return {"ok": True}


# ============================================================
# ĐỒNG BỘ brain với GitHub - 2 CHIỀU (kéo về + hoà nhập + đẩy lên).
# Dùng được nhiều máy (local + VPS) chung 1 repo: các máy tự khớp nhau qua repo.
# UI + hướng dẫn ở trang Tự học (console.js renderLearn). Token lưu settings.json (gitignored).
# ============================================================
def _do_backup(brain: str = "") -> dict:
    """Đồng bộ 2 CHIỀU toàn bộ thư mục brains với repo GitHub. Tham số brain giữ cho
    tương thích chữ ký cũ nhưng KHÔNG dùng - luôn đồng bộ cả BRAINS_DIR.
    Cập nhật last_backup/last_status/last_report."""
    cfg = cfgmod.read_settings()
    b = cfg.get("backup", {}) or {}
    if not (b.get("repo_url") and b.get("token")):
        return {"ok": False, "error": "Chưa cấu hình repo URL + token"}
    mirror = str(cfgmod.STATE_DIR / "brains-backup")   # repo mirror riêng (tránh nested git từng brain)
    res = git_brain.sync_brains(BRAINS_DIR, mirror, b["repo_url"], b["token"], b.get("branch") or "main",
                                trash_dir=str(cfgmod.STATE_DIR / "brain-trash"),
                                protected_names={_default_brain_dir().name})
    # Ghi lại trạng thái (đọc lại cfg mới nhất để không đè thay đổi song song)
    cfg = cfgmod.read_settings()
    cfg.setdefault("backup", {})
    cfg["backup"]["last_backup"] = time.time()
    if res.get("ok"):
        bits = []
        if res.get("applied"):
            bits.append(f"nhận {res['applied']} file")
        if res.get("deleted"):
            bits.append(f"xoá {res['deleted']}")
        if res.get("conflicts"):
            bits.append(f"{len(res['conflicts'])} xung đột (giữ cả 2 bản)")
        if res.get("restored"):
            bits.append("khôi phục từ backup")
        detail = (" · " + ", ".join(bits)) if bits else ""
        cfg["backup"]["last_status"] = "✓ Đồng bộ 2 chiều " + time.strftime("%H:%M %d/%m") + detail
    else:
        cfg["backup"]["last_status"] = "✗ " + (res.get("error") or "lỗi")[:150]
    cfg["backup"]["last_report"] = {
        "ts": time.time(), "ok": bool(res.get("ok")), "pushed": bool(res.get("pushed")),
        "applied": res.get("applied", 0), "deleted": res.get("deleted", 0),
        "conflicts": (res.get("conflicts") or [])[:20], "restored": bool(res.get("restored")),
        "error": (res.get("error") or "")[:200],
    }
    cfgmod.write_settings(cfg)
    return res


@app.get("/backup/status")
async def backup_status(brain: str = Query("brain")):
    cfg = cfgmod.read_settings()
    b = cfg.get("backup", {}) or {}
    # Đếm số brain trong BRAINS_DIR (để UI báo "backup N brain")
    try:
        n_brains = len([d for d in Path(BRAINS_DIR).iterdir() if d.is_dir() and not d.name.startswith(".")])
    except Exception:
        n_brains = 0
    return {
        "enabled": bool(b.get("enabled")),
        "repo_url": b.get("repo_url", ""),
        "branch": b.get("branch", "main"),
        "interval_hours": b.get("interval_hours", 6),
        "token_set": bool(b.get("token")),
        "last_backup": b.get("last_backup", 0.0),
        "last_status": b.get("last_status", ""),
        "last_report": b.get("last_report") or {},
        "has_git": git_brain.has_git(),
        "brains_dir": BRAINS_DIR,
        "brains_count": n_brains,
    }


@app.post("/backup/config")
async def backup_config(
    repo_url: str = Form(None), token: str = Form(None), branch: str = Form(None),
    enabled: str = Form(None), interval_hours: str = Form(None),
):
    cfg = cfgmod.read_settings()
    b = cfg.setdefault("backup", {})
    if repo_url is not None:
        b["repo_url"] = repo_url.strip()
    if token:                     # chỉ ghi khi có token MỚI (tránh xoá bằng chuỗi che ••••)
        b["token"] = token.strip()
    if branch:
        b["branch"] = branch.strip() or "main"
    if enabled is not None:
        b["enabled"] = enabled in ("1", "true", "True", "on")
    if interval_hours is not None:
        try:
            b["interval_hours"] = max(1, int(interval_hours))
        except ValueError:
            pass
    cfgmod.write_settings(cfg)
    return {"ok": True}


@app.post("/backup/test")
async def backup_test():
    """Kiểm tra token + repo hợp lệ (git ls-remote) trước khi bật auto."""
    cfg = cfgmod.read_settings()
    b = cfg.get("backup", {}) or {}
    return await asyncio.to_thread(git_brain.remote_reachable, b.get("repo_url", ""), b.get("token", ""))


@app.post("/backup/now")
async def backup_now(brain: str = Form("brain")):
    return await asyncio.to_thread(_do_backup, brain)


_OR_MODELS_CACHE = {"data": None, "ts": 0.0}


async def openrouter_models_index():
    """Lõi thuần của GET /openrouter/models. Dùng chung với _fetch_provider_models."""
    """Lấy danh sách model OpenRouter (API công khai, không cần key). Cache 1 giờ."""
    now = time.time()
    if _OR_MODELS_CACHE["data"] and (now - _OR_MODELS_CACHE["ts"]) < 3600:
        return {"models": _OR_MODELS_CACHE["data"], "cached": True}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("https://openrouter.ai/api/v1/models")
            r.raise_for_status()
            raw = r.json().get("data", [])
        models = [{"id": m.get("id"), "name": m.get("name") or m.get("id")} for m in raw if m.get("id")]
        models.sort(key=lambda x: x["name"].lower())
        _OR_MODELS_CACHE["data"] = models
        _OR_MODELS_CACHE["ts"] = now
        return {"models": models}
    except Exception as e:
        return {"models": [], "error": f"{type(e).__name__}: {e}"}


@app.get("/openrouter/models")
async def openrouter_models():
    return await openrouter_models_index()


# Model load ĐỘNG theo provider (không hardcode - provider đổi model không cần sửa code).
_PROV_MODELS_CACHE = {}   # provider -> {"ids":[...], "ts": float}


async def _fetch_provider_models(provider, m):
    """Danh sách model id LIVE từ API của provider, hoặc None (caller fallback catalog)."""
    import httpx
    if provider == "openrouter":
        d = await openrouter_models_index()
        return [x["id"] for x in d.get("models", []) if x.get("id")] or None
    if provider == "openai":
        key = m.get("openai_api_key")
        if not key:
            return None
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"})
            r.raise_for_status()
            data = r.json().get("data", [])
        ids = sorted(x.get("id") for x in data if x.get("id"))
        # lọc model chat (bỏ embedding/whisper/tts/dall-e/moderation...)
        ids = [i for i in ids if i.startswith(("gpt", "o1", "o3", "o4", "chatgpt"))]
        return ids or None
    if provider == "anthropic-api":
        key = m.get("anthropic_api_key")
        if not key:
            return None
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get("https://api.anthropic.com/v1/models",
                            headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
            r.raise_for_status()
            data = r.json().get("data", [])
        return [x.get("id") for x in data if x.get("id")] or None
    if provider == "gemini":
        key = m.get("gemini_api_key")
        if not key:
            return None
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get("https://generativelanguage.googleapis.com/v1beta/models", params={"key": key})
            r.raise_for_status()
            data = r.json().get("models", [])
        # name dạng 'models/gemini-2.5-flash' → lấy đuôi; chỉ giữ model sinh nội dung (bỏ embedding/aqa)
        ids = [(x.get("name") or "").split("/")[-1] for x in data
               if "generateContent" in (x.get("supportedGenerationMethods") or [])]
        return sorted(i for i in ids if i.startswith("gemini")) or None
    if provider == "groq":
        key = m.get("groq_api_key")
        if not key:
            return None
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get("https://api.groq.com/openai/v1/models",
                            headers={"Authorization": f"Bearer {key}"})
            r.raise_for_status()
            data = r.json().get("data", [])
        # Groq phục vụ cả model whisper (chuyển giọng thành chữ) và guard trên cùng endpoint -
        # lọc ra kẻo picker chat hiện model không chat được.
        ids = [x.get("id") for x in data if x.get("id")
               and not any(s in x["id"].lower() for s in ("whisper", "tts", "guard", "embed"))]
        return sorted(ids) or None
    if provider == "ollama":
        key = m.get("ollama_key")
        if not key:
            return None
        # Hỏi HAI đường vì Ollama phục vụ cả hai và tài liệu của họ không nói rõ đường nào là
        # chính cho bản Cloud: /v1/models là chuẩn OpenAI, /api/tags là đường gốc của Ollama.
        # Thử chuẩn trước, hụt mới sang gốc. Lỗi của đường sau mới ném ra, vì đó là lỗi người
        # dùng cần đọc. Thà thừa một request còn hơn báo "chưa thấy model" với một key đúng.
        headers = {"Authorization": f"Bearer {key}"}
        async with httpx.AsyncClient(timeout=20) as c:
            try:
                r = await c.get(engine.OLLAMA_BASE + "/v1/models", headers=headers)
                r.raise_for_status()
                ids = sorted(x.get("id") for x in (r.json().get("data") or []) if x.get("id"))
                if ids:
                    return ids
            except Exception:  # noqa: BLE001 - còn một đường nữa, chưa phải lúc bỏ cuộc
                pass
            r = await c.get(engine.OLLAMA_BASE + "/api/tags", headers=headers)
            r.raise_for_status()
            data = r.json().get("models", [])
        # `name` là tên đầy đủ kèm tag (gpt-oss:120b-cloud) - đúng thứ phải gửi lại khi chat.
        return sorted(x.get("name") for x in data if x.get("name")) or None
    if provider == "openai-oauth":
        # app-server là subprocess đồng bộ; chạy ở worker để request FastAPI
        # khác không đứng hình trong lúc Codex nạp catalog.
        return await asyncio.to_thread(openai_oauth.list_models, openai_oauth.valid_creds())
    if provider == "gemini-cli":
        return gemini_cli.list_models()
    if provider == "antigravity-cli":
        # `agy models` là NGUỒN CHÂN LÝ, không có bảng chép tay nào để rơi về - chạy ở worker
        # vì nó đẻ tiến trình con và có thể mất vài giây.
        return await asyncio.to_thread(antigravity_cli.list_models)
    if provider == "anthropic-cli":
        # Provider này chạy bằng đăng nhập OAuth của Claude Code → mượn chính token đó hỏi
        # /v1/models, nên Anthropic ra bản mới là picker thấy ngay (trước kẹt ở 4 alias tĩnh).
        return await claude_models.fetch_models(m.get("anthropic_api_key") or "")
    return None


def _remember_catalog(cfg, d, ids):
    """Ghi danh sách live vừa lấy vào catalog settings.

    Để lần sau mất mạng / token OAuth hết hạn thì fallback vẫn là danh sách MỚI NHẤT
    từng thấy, chứ không rơi về mấy alias cũ hardcode trong config.py.
    """
    key = d.get("catalog_key")
    if not key:
        return
    keep = list(ids[:50])                     # chặn phình settings.json (OpenRouter vài trăm model)
    cat = cfg.setdefault("model", {}).setdefault("catalog", {})
    if cat.get(key) == keep:
        return
    cat[key] = keep
    try:
        cfgmod.write_settings(cfg)
    except Exception as e:
        import sys
        print(f"[models] không ghi được catalog {key}: {e}", file=sys.stderr)


def _vi_sao_khong_co_model(provider: str, m: dict) -> str:
    """Vì sao provider này không trả về model nào - viết cho NGƯỜI ĐỌC, không phải log.

    Hầu hết đường lấy model hỏng theo kiểu IM LẶNG: hàm trả None chứ không ném lỗi, nên phía
    trên chỉ còn một danh sách rỗng và giao diện đành nói "không có model" - đúng nhưng vô
    dụng. ChatGPT là ca nặng nhất vì nó KHÔNG có catalog dự phòng (danh sách model do Codex
    quyết, Javis cố ý không ghim version), nên hỏng là thẻ hiện đúng "0 model" ngay sau khi
    người dùng vừa đăng nhập xong - trông y như đăng nhập hỏng.
    """
    d = _provider_def(provider) or {}
    if provider == "openai-oauth":
        if not (openai_oauth.valid_creds() or {}).get("access_token"):
            return ("Chưa kết nối ChatGPT (hoặc phiên đăng nhập đã hết hạn) - "
                    "đăng nhập lại ở thẻ ChatGPT.")
        if not find_codex_cli():
            return ("Không thấy Codex CLI trên máy - danh sách model của gói ChatGPT do chính "
                    "Codex cấp. Cài bằng `npm i -g @openai/codex` (macOS có thể dùng "
                    "`brew install codex`) rồi bấm lại. Cài ở chỗ lạ thì trỏ thẳng bằng biến "
                    "môi trường JAVIS_CODEX_BIN.")
        return ("Có Codex CLI nhưng nó chưa trả được danh sách model. Thường là bản Codex quá "
                "cũ (`npm i -g @openai/codex@latest`), hoặc máy chưa chạy `codex login` lần nào.")
    if provider == "gemini-cli":
        return (gemini_cli.auth_status().get("error")
                or "Không đọc được danh sách model của Gemini CLI.")
    if provider == "ollama":
        return "Không gọi được Ollama. Kiểm tra máy chủ Ollama còn chạy và key còn hạn."
    if d.get("key_field") and not m.get(d["key_field"]):
        return "Chưa có API key cho nhà cung cấp này."
    return ""


async def provider_models_index(provider: str, refresh: bool = False) -> dict:
    """Lõi thuần của GET /provider/models. Dùng chung với Telegram (menu chọn model)."""
    cfg = cfgmod.read_settings()
    m = cfg.get("model", {})
    d = _provider_def(provider) or {}
    cat = m.get("catalog", {}) or {}
    fallback = cat.get(d.get("catalog_key", "")) or d.get("default_models", [])
    now = time.time()
    c = _PROV_MODELS_CACHE.get(provider)
    if not refresh and c and (now - c["ts"]) < 600 and c.get("ids"):
        return {"models": c["ids"], "live": True, "cached": True}
    try:
        ids = await _fetch_provider_models(provider, m)
    except Exception as e:
        ids = None
        last_err = f"{type(e).__name__}: {e}"
    else:
        last_err = None
    if ids:
        _PROV_MODELS_CACHE[provider] = {"ids": ids, "ts": now}
        _remember_catalog(cfg, d, ids)
        return {"models": ids, "live": True}
    return {"models": fallback, "live": False,
            "error": last_err or _vi_sao_khong_co_model(provider, m)}


@app.get("/provider/models")
async def provider_models(provider: str = Query(...), refresh: bool = Query(False)):
    """Model động cho 1 provider. ``refresh=1`` bỏ cache để picker hỏi Codex ngay."""
    return await provider_models_index(provider, refresh=refresh)


@app.get("/memory/stats")
async def memory_stats(brain: str = Query("brain")):
    """Đếm số ký ức đã học trong vault đang chọn."""
    try:
        facts_dir = _brain_memory_dir(brain) / "facts"
        facts = len(list(facts_dir.glob("*.md")))
    except Exception:
        facts = 0
    return {"facts": facts}


@app.post("/reflect")
async def reflect(brain: str = Form("brain")):
    """Nút 'Học từ hội thoại' (THỦ CÔNG): rút Memory + đúc Wiki từ hội thoại gần đây.

    Phase 0 (an toàn): KHÔNG còn spawn Claude full-quyền như trước. Đi qua engine learn.py:
    fork READ-ONLY cô lập (0 MCP, không Bash/Web) → manifest → Python tin cậy ghi; fail-closed
    qua git (git-init khi bấm) + secret-scan trước commit. force_write=True vì đây là chủ đích
    của user (ghi bất kể mode dry-run), caps = memory+wiki (skill giữ off, dựng ở Phase 3)."""
    if not find_claude_cli():
        return {"ok": False, "error": "Claude CLI chưa cài"}
    g = git_brain.ensure_git_repo(_brain_root(brain))   # consent thủ công → git-init để undo được
    res = await learn_feature.run_once(
        brain, reason="reflect", force_write=True,
        caps_override={"memory": True, "wiki": True, "skill": False})
    facts = 0
    try:
        facts = len(list((_brain_memory_dir(brain) / "facts").glob("*.md")))
    except Exception:
        pass
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error", "reflect lỗi"), "git": g}
    rep = res.get("report", {})
    return {"ok": True, "summary": res.get("summary", ""), "facts": facts,
            "status": res.get("status", ""), "report": rep, "git": g}


@app.get("/health")
async def health():
    cli = find_claude_cli()
    return {
        "status": "ok",
        "claude_cli": cli or "NOT FOUND",
        "claude_cli_available": cli is not None,
        "cwd": CLAUDE_CWD,
    }


# Đồ thị note (GET /graph + WS /ws/graph) đã bóc sang routes/graph.py ở 0.9.243.
# Lời gọi register PHẢI nằm đúng chỗ này - Starlette khớp route theo thứ tự đăng ký và
# tests/python/route_table.json khoá cả thứ tự, nên dời lên/xuống là test bảng route đỏ.
# _default_brain_dir truyền dưới dạng lambda vì nó được định nghĩa BÊN DƯỚI dòng này.
import routes.graph as graph_routes   # noqa: E402
graph_routes.register(app, graph_routes.GraphDeps(
    default_brain_dir=lambda: _default_brain_dir(),
    vault_path=lambda: OBSIDIAN_VAULT_PATH,
))


def _sanitize_filename(name: str) -> str:
    name = os.path.basename(name or "").strip()
    name = re.sub(r"[^\w\-. ()À-ỹ]", "_", name, flags=re.UNICODE)
    return name or "file"

def _unique_path(folder: str, name: str) -> str:
    base, ext = os.path.splitext(name)
    candidate = os.path.join(folder, name)
    i = 1
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{base}_{i}{ext}")
        i += 1
    return candidate

IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
# Thư mục stage tạm cho file upload. PHẢI nằm trong STATE_DIR (ghi được ở mọi môi trường):
# Docker/VPS = /data/state (volume ghi được), local = server/. KHÔNG dùng PROJECT_ROOT/.staging
# vì trong container code tree /app là read-only + chạy user non-root → makedirs ném
# PermissionError → HTTP 500 khi upload. (config.py cùng nguyên tắc cho settings/branding.)
STAGING = cfgmod.STATE_DIR / ".staging"

def _default_brain_dir() -> Path:
    """Brain mặc định = <BRAINS_DIR>/Brain Default. BRAINS_DIR = thư mục CHA chứa mọi brain
    (mỗi folder con = 1 brain). Docker = /brains (mount riêng, ghi được, git-backup được).
    Local = <project>/brains. Đây là 'bộ não khởi đầu' - user vẫn chọn brain khác trong danh
    sách hoặc folder ngoài bất kỳ qua 'path:<thư mục>'. KHÔNG hardcode vault cá nhân nào."""
    p = Path(BRAINS_DIR) / "Brain Default"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p

def _brain_root(brain: str) -> str:
    if not brain or brain == "brain":
        return str(_default_brain_dir())
    return brain if os.path.isdir(brain) else str(_default_brain_dir())


def _brain_key(brain) -> str:
    """Giá trị CHUẨN của một brain để GHI vào kho phiên: đường dẫn tuyệt đối đã resolve.

    Cột `sessions.brain` trước đây lưu nguyên văn thứ chỗ tạo phiên truyền vào, mà mỗi kênh
    viết một kiểu cho CÙNG một brain: dashboard gửi tên gọi tắt "brain" (app.js::
    currentBrainPath), Telegram `/brain` và loop lưu đường dẫn tuyệt đối. Ghi chuẩn hoá thì
    phiên mới của mọi kênh nằm chung một khoá; phiên CŨ đã lệch thì `_brain_keys` lo lúc đọc.
    """
    root = _brain_root(str(brain or ""))
    try:
        return str(Path(root).resolve())
    except OSError:
        return str(root)


def _brain_keys(brain) -> list:
    """Mọi cách viết cùng trỏ về brain này, để LỌC kho phiên. [] = không lọc.

    Có cả bản chuẩn (`_brain_key`) lẫn các bản cũ còn nằm trong DB: chuỗi người gọi đưa vào,
    đường dẫn chưa resolve, và tên gọi tắt "brain" khi đây đúng là brain mặc định. Nhờ vậy
    hội thoại lưu từ trước bản vá vẫn hiện lên mà không phải chạy migration nào.
    """
    raw = str(brain or "").strip()
    if not raw:
        return []
    root = _brain_root(raw)
    try:
        chuan = str(Path(root).resolve())
    except OSError:
        chuan = str(root)
    keys = [raw]
    for v in (str(root), chuan):
        if v and v not in keys:
            keys.append(v)
    try:
        if chuan == str(_default_brain_dir().resolve()) and "brain" not in keys:
            keys.append("brain")
    except OSError:
        pass
    return keys


def _brain_sub(root, new_name: str, old_rel: str) -> Path:
    """Subfolder trong brain theo cấu trúc CHUẨN MỚI (phẳng <root>/<new_name>).
    Fallback cấu trúc CŨ (<root>/<old_rel>, vd Javis/agents, Memory) nếu mới chưa có →
    không vỡ vault chưa migrate. Chưa có cả hai → tạo mới."""
    root = Path(root)
    new = root / new_name
    if new.is_dir():
        return new
    old = root / old_rel
    if old.is_dir():
        return old
    new.mkdir(parents=True, exist_ok=True)
    return new

def _resolve_subfolder(root: str, name_regex: str, default_name: str) -> str:
    """Tìm (hoặc tạo) subfolder khớp regex trong root (vd Sources / Attachments)."""
    if not os.path.isdir(root):
        root = str(_default_brain_dir())
    try:
        for name in os.listdir(root):
            full = os.path.join(root, name)
            if os.path.isdir(full) and re.match(name_regex, name.strip(), re.IGNORECASE):
                return full
    except Exception:
        pass
    dest = os.path.join(root, default_name)
    os.makedirs(dest, exist_ok=True)
    return dest

async def _save_upload_stream(upload: UploadFile, dest: str, chunk: int = 1024 * 1024):
    """Ghi file upload xuống đĩa theo từng chunk 1MB - KHÔNG nạp cả file vào RAM và nhường
    event-loop giữa các chunk. Tránh worker treo khi file lớn → reverse proxy (Caddy/Hostinger)
    reset kết nối, khiến client thấy 'lỗi mạng'."""
    with open(dest, "wb") as f:
        while True:
            part = await upload.read(chunk)
            if not part:
                break
            f.write(part)


@app.post("/upload")
async def upload(file: UploadFile = File(...), brain: str = Form("")):
    """Nhận file → stage tạm (chưa vào Sources). Bước /ingest-upload sẽ chuyển thành .md.

    Bọc TOÀN BỘ trong try/except: mọi lỗi (không tạo được thư mục staging, đĩa đầy,
    brain không ghi được...) trả JSON {ok:false, error} + in traceback ra log, KHÔNG để
    rơi thành HTTP 500 khó chẩn đoán. Frontend hiển thị "lỗi: <lý do>" thay vì "lỗi máy chủ (500)".
    """
    try:
        os.makedirs(STAGING, exist_ok=True)
        raw = file.filename or ""
        if not raw or raw in ("blob", "image.png"):
            ext = os.path.splitext(raw)[1] or ".png"
            raw = f"paste-{int(time.time())}{ext}"
        name = _sanitize_filename(raw)
        staged = _unique_path(str(STAGING), name)
        await _save_upload_stream(file, staged)
        ext = os.path.splitext(staged)[1].lower()
        kind = "image" if ext in IMG_EXTS else "file"
        root = _brain_root(brain)
        sources = _resolve_subfolder(root, r"^(\d+\s*[-_.]\s*)?sources$", "Sources")
        attachments = _resolve_subfolder(root, r"^(\d+\s*[-_.]\s*)?attachments$", "Attachments")
        return {"ok": True, "staged": staged, "name": os.path.basename(staged),
                "kind": kind, "size": os.path.getsize(staged),
                "sources": sources, "attachments": attachments}
    except Exception as e:
        import sys, traceback
        traceback.print_exc(file=sys.stderr)
        return {"ok": False, "error": f"Không lưu được file tạm: {e}"}

@app.post("/ingest-upload")
async def ingest_upload(
    staged: str = Form(...), sources: str = Form(...),
    attachments: str = Form(""), kind: str = Form("file"), name: str = Form(""),
):
    """Dùng Claude CLI biến file staged thành .md nguồn: text→trích, ảnh→mô tả."""
    cli = claude_engine(system_prompt=SYSTEM_PROMPT, cwd=CLAUDE_CWD)
    cli = _aux_swap(cli, mode="auto", tag="ingest")   # việc nền: theo model phụ đã chọn
    if not cli.is_available():
        return {"ok": False, "error": "Engine việc nền chưa sẵn sàng (kiểm tra trang Model)"}
    slug = _sanitize_filename(os.path.splitext(name)[0]) or "source"

    if kind == "image":
        prompt = (
            f"File ẢNH vừa tải lên nằm ở: {staged}\n"
            f"Hãy:\n"
            f"1) Đọc và HIỂU KỸ ảnh (chữ trong ảnh, số liệu, biểu đồ, sơ đồ, ý chính).\n"
            f"2) Tạo file Markdown tại folder \"{sources}\" tên \"{slug}.md\" gồm:\n"
            f"   - frontmatter: type: source, source_kind: screenshot, status: unprocessed, created (hôm nay), original: {name}\n"
            f"   - phần MÔ TẢ CHI TIẾT nội dung ảnh bằng tiếng Việt.\n"
            f"3) Di chuyển file ảnh gốc vào folder \"{attachments}\" rồi nhúng vào .md bằng ![[tên-ảnh]].\n"
            f"CHỈ in ra đường dẫn đầy đủ của file .md đã tạo, không giải thích thêm."
        )
    else:
        prompt = (
            f"File VĂN BẢN vừa tải lên nằm ở: {staged}\n"
            f"Hãy:\n"
            f"1) Đọc toàn bộ nội dung.\n"
            f"2) Tạo file Markdown SẠCH tại folder \"{sources}\" tên \"{slug}.md\" gồm:\n"
            f"   - frontmatter: type: source, source_kind phù hợp, status: unprocessed, created (hôm nay), original: {name}\n"
            f"   - nội dung đã định dạng gọn gàng, giữ nguyên thông tin, bỏ rác.\n"
            f"3) Xóa file gốc tại {staged}.\n"
            f"CHỈ in ra đường dẫn đầy đủ của file .md đã tạo, không giải thích thêm."
        )

    final = ""
    async for ev in cli.query(prompt):
        if ev["type"] == "final":
            final = ev.get("content", "")
        elif ev["type"] == "error":
            return {"ok": False, "error": ev["content"][:200]}

    m = re.search(r"[A-Za-z]:\\[^\n\"]+\.md|/[^\n\"]+\.md", final)
    md_path = m.group(0).strip() if m else os.path.join(sources, f"{slug}.md")
    if os.path.exists(md_path):
        return {"ok": True, "md_path": md_path, "md_name": os.path.basename(md_path),
                "folder": os.path.basename(sources)}
    return {"ok": False, "error": "Không tạo được .md", "raw": final[:200]}

# Cấu trúc chuẩn Javis - kiểm tra khi mở vault
# detect: regex khớp tên folder top-level (linh hoạt "06 - Sources" / "Sources")
STANDARD_STRUCTURE = [
    # Nội dung người dùng đưa vào - nguồn lưu trữ (source of truth)
    {"key": "sources", "label": "sources", "kind": "dir", "detect": r"^(\d+\s*[-_.]\s*)?sources$", "create": "sources", "essential": True},
    # Lớp vận hành Javis (alt = vị trí cũ chưa migrate → không báo thiếu nhầm)
    {"key": "agents", "label": "agents", "kind": "dir", "detect": r"^agents$", "alt": "Javis/agents", "create": "agents", "essential": True},
    {"key": "workflows", "label": "workflows", "kind": "dir", "detect": r"^workflows$", "alt": "Javis/workflows", "create": "workflows", "essential": True},
    {"key": "memory", "label": "memory", "kind": "dir", "detect": r"^memory$", "alt": "Memory", "create": "memory", "essential": True},
    # Skill: canonical phẳng skills/<slug>/SKILL.md (mirror sang .claude/skills cho Claude native),
    # chia nhóm bằng field `group` trong frontmatter. alt = .claude/skills (vị trí cũ chưa migrate).
    {"key": "skills", "label": "skills", "kind": "dir", "detect": r"^skills$", "alt": ".claude/skills", "create": "skills", "essential": False},
    # Tuỳ chọn - Javis chưng cất source → wiki (nuôi graph); đính kèm ảnh/file
    {"key": "wiki", "label": "wiki", "kind": "dir", "detect": r"^(\d+\s*[-_.]\s*)?wiki$", "create": "wiki", "essential": False},
    {"key": "attachments", "label": "attachments", "kind": "dir", "detect": r"^(\d+\s*[-_.]\s*)?attachments$", "create": "attachments", "essential": False},
    # Bộ sổ bullet journal - nơi ghi chép + task hằng ngày, dataview kéo từ đây.
    # detect linh hoạt: "01 - Daily Log" / "Daily Log" / "Daily" đều tính là có.
    {"key": "dashboard", "label": "dashboard", "kind": "dir", "detect": r"^(\d+\s*[-_.]\s*)?dashboard$", "create": "00 - Dashboard", "essential": False},
    {"key": "daily", "label": "daily log", "kind": "dir", "detect": r"^(\d+\s*[-_.]\s*)?daily(\s*log)?$", "create": "01 - Daily Log", "essential": False},
    {"key": "weekly", "label": "weekly log", "kind": "dir", "detect": r"^(\d+\s*[-_.]\s*)?weekly(\s*log)?$", "create": "02 - Weekly Log", "essential": False},
    {"key": "monthly", "label": "monthly log", "kind": "dir", "detect": r"^(\d+\s*[-_.]\s*)?monthly(\s*log)?$", "create": "03 - Monthly Log", "essential": False},
    {"key": "future", "label": "future log", "kind": "dir", "detect": r"^(\d+\s*[-_.]\s*)?future(\s*log)?$", "create": "04 - Future Log", "essential": False},
]

def _check_structure(root: Path):
    items = []
    try:
        top_dirs = [d for d in os.listdir(root) if os.path.isdir(root / d)]
    except Exception:
        top_dirs = []
    for it in STANDARD_STRUCTURE:
        present, where = False, None
        if it["kind"] == "dir":
            for d in top_dirs:
                if re.match(it["detect"], d.strip(), re.IGNORECASE):
                    present, where = True, d
                    break
            if not present and it.get("alt") and (root / it["alt"]).exists():
                present, where = True, it["alt"]   # vị trí cũ chưa migrate vẫn tính là có
        elif it["kind"] == "exact":
            p = root / it["path"]
            present = p.exists()
            where = it["path"] if present else None
        elif it["kind"] == "file_any":
            for f in it["files"]:
                if (root / f).exists():
                    present, where = True, f
                    break
        items.append({"key": it["key"], "label": it["label"], "present": present,
                      "where": where, "essential": it["essential"]})
    return items

JAVIS_README = (
    "# Javis\n\nLớp điều phối của Javis OS trong vault này.\n\n"
    "- `agents/` - các Agent (vai trò + skills + bộ nhớ riêng)\n"
    "- `workflows/` - quy trình nhiều agent (status active/off)\n"
    "- Skills dùng chung ở `skills/` (tự mirror sang `.claude/skills` cho Claude Code native)\n"
)
DASHBOARD_SEED = (
    "# Dashboard\n\n"
    "## 🔴 Nhiệm vụ quá hạn\n\n"
    "```tasks\nnot done\ndue before today\nsort by due\nlimit 20\n```\n\n"
    "## 🟡 Nhiệm vụ hôm nay\n\n"
    "```tasks\nnot done\ndue today\n```\n\n"
    "## 🟢 Sắp tới\n\n"
    "```tasks\nnot done\ndue after today\nsort by due\nlimit 20\n```\n\n"
    "## 📥 Chưa có hạn\n\n"
    "```tasks\nnot done\nno due date\nlimit 20\n```\n"
)
TASKINBOX_SEED = (
    "# Task Inbox\n\n"
    "Việc thêm nhanh từ dashboard - kéo về đúng sổ khi rảnh.\n"
)
SCHEMA_SEED = (
    "# AGENTS.md - Vault Schema (Javis)\n\n"
    "> Vault này hoạt động với Javis OS. Cấu trúc:\n\n"
    "- `01 - Daily Log/` → `04 - Future Log/` - bộ sổ bullet journal (nhật ký ngày/tuần/tháng/tương lai, chứa task `- [ ]`; khối dataview kéo việc từ đây)\n"
    "- `06 - Sources/` - ghi chú thô (source of truth)\n"
    "- `07 - Wiki/` - tri thức đã chưng cất, có `[[wikilink]]`\n"
    "- `Memory/` - bộ nhớ dài hạn của Javis (facts + conversations)\n"
    "- `Javis/` - agents + workflows\n\n"
    "Nguyên lý: Sources → (ingest) → Wiki. Tri thức tích luỹ, không tái phát hiện.\n"
)

def _ensure_brain_scaffold(root):
    """Tạo cấu trúc chuẩn cho MỘT brain (idempotent): sources/agents/workflows/memory/wiki/
    attachments + Javis/README + memory seed. Dùng cho brain mặc định lẫn brain mới tạo."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    present = {i["key"] for i in _check_structure(root) if i["present"]}
    for it in STANDARD_STRUCTURE:
        if it["key"] in present:
            continue
        try:
            if it["kind"] in ("dir", "exact"):
                (root / it["create"]).mkdir(parents=True, exist_ok=True)
            elif it["kind"] == "file_any":
                (root / it["create"]).write_text(SCHEMA_SEED, encoding="utf-8")
        except Exception as e:
            print(f"[brain scaffold] {it['key']}: {e}", file=__import__('sys').stderr)
    jr = root / "Javis" / "README.md"
    if not jr.exists():
        jr.parent.mkdir(parents=True, exist_ok=True)
        jr.write_text(JAVIS_README, encoding="utf-8")
    try:
        # Seed trang Dashboard + Task Inbox trong thư mục dashboard (create-if-missing,
        # user sửa gì giữ nấy). Khối ```tasks trong seed chạy thật trên dashboard Javis.
        dash = Path(_resolve_subfolder(str(root), r"^(\d+\s*[-_.]\s*)?dashboard$", "00 - Dashboard"))
        if not (dash / "Dashboard.md").exists():
            (dash / "Dashboard.md").write_text(DASHBOARD_SEED, encoding="utf-8")
        if not (dash / "Task Inbox.md").exists():
            (dash / "Task Inbox.md").write_text(TASKINBOX_SEED, encoding="utf-8")
    except Exception as e:
        print(f"[brain scaffold] dashboard seed: {e}", file=__import__('sys').stderr)
    try:
        _brain_memory_dir(str(root))   # memory/ + MEMORY.md seed
    except Exception:
        pass
    try:
        # Năng lực HỆ THỐNG (skill javis-builder/ingest/query/lint + loop tự-cải-tiến): nguồn chuẩn
        # nằm ở tầng app (.claude/skills + system/loops, đi theo phiên bản), mirror vào brain qua
        # manifest - cài nếu thiếu, UPDATE khi app lên bản mới, giữ nguyên nếu user đã sửa.
        system_sync.sync_brain(str(root))
    except Exception as e:
        print(f"[system sync] {e}", file=__import__('sys').stderr)
    try:
        import meta_tools
        # Bộ khung "compounding wiki" phổ quát: schema doc + điều hướng wiki + HANDOFF - seed 1 LẦN
        # (create-if-missing) vì user + AI cùng tiến hoá các file này, update app KHÔNG ghi đè.
        # Resolve đúng thư mục wiki hiện có (vd '07 - Wiki') để không tạo 'wiki' trùng.
        _wd = _resolve_subfolder(str(root), r"^(\d+\s*[-_.]\s*)?wiki$", "wiki")
        meta_tools.ensure_brain_pattern(str(root), _wd)
    except Exception as e:
        print(f"[meta tools seed] {e}", file=__import__('sys').stderr)
    try:
        rebuild_javis_index(str(root))   # chỉ mục tầng vận hành (Javis/index.md)
    except Exception as e:
        print(f"[javis index] {e}", file=__import__('sys').stderr)


def _ensure_default_brain():
    """Seed brain mặc định (<BRAINS_DIR>/Brain Default) lúc khởi động → deploy mới có ngay 'bộ não
    Javis khởi đầu', không hiện banner 'cấu trúc chưa chuẩn'."""
    try:
        _ensure_brain_scaffold(_default_brain_dir())
    except Exception as e:
        print(f"[brain scaffold] {e}", file=__import__('sys').stderr)


def _sync_system_all_brains():
    """Đồng bộ năng lực HỆ THỐNG vào MỌI brain trong BRAINS_DIR lúc khởi động - đổi brain nào
    cũng có đủ chức năng mặc định, và app lên bản mới thì brain cũ nhận bản skill/loop mới
    (trừ file user đã sửa). Brain ngoài (path:) được sync ở lượt dùng đầu (build_system_prompt).
    KHÔNG scaffold cấu trúc thư mục ở đây - chỉ đụng file hệ thống, dữ liệu user để yên."""
    try:
        base = Path(BRAINS_DIR)
        if not base.is_dir():
            return
        for p in sorted(base.iterdir()):
            if p.is_dir() and not p.name.startswith("."):
                system_sync.ensure_synced(p)
    except Exception as e:
        print(f"[system sync all] {e}", file=__import__('sys').stderr)


def _migrate_legacy_brain():
    """Chuyển dữ liệu brain CŨ sang <BRAINS_DIR>/Brain Default (mô hình mới: mọi brain trong BRAINS_DIR).
    CHỈ chạy khi brain mặc định MỚI còn rỗng → KHÔNG ghi đè. Nguồn cũ thử lần lượt: /data/brain
    (BRAIN_PATH), <project>/Brain Default, <project>/brain. An toàn, chạy lại nhiều lần vô hại."""
    try:
        new = _default_brain_dir()
        if new.is_dir() and any(new.iterdir()):
            return   # brain mặc định đã có dữ liệu → khỏi migrate
        for cand in (Path(BRAIN_PATH), PROJECT_ROOT / "Brain Default", PROJECT_ROOT / "brain"):
            try:
                # Nếu nguồn cũ CHỨA sẵn 'Brain Default' con (vd brain/Brain Default do user gom tay)
                # → lấy đúng folder con đó để KHÔNG bị lồng brains/Brain Default/Brain Default.
                inner = cand / "Brain Default"
                old = inner if (inner.is_dir() and any(inner.iterdir())) else cand
                if old.resolve() == new.resolve():
                    continue
                if old.is_dir() and any(old.iterdir()):
                    new.mkdir(parents=True, exist_ok=True)
                    for item in old.iterdir():
                        dst = new / item.name
                        if not dst.exists():
                            shutil.move(str(item), str(dst))   # gộp, KHÔNG ghi đè cái đã có
                    print(f"[brain migrate] {old} -> {new}", file=__import__('sys').stderr)
                    return
            except Exception as e:
                print(f"[brain migrate] {cand}: {e}", file=__import__('sys').stderr)
    except Exception as e:
        print(f"[brain migrate] {e}", file=__import__('sys').stderr)

@app.get("/vault/check")
async def vault_check(brain: str = Query("brain")):
    """Kiểm tra cấu trúc chuẩn của vault đang chọn."""
    root = Path(_brain_root(brain))
    items = _check_structure(root)
    missing = [i for i in items if not i["present"]]
    missing_essential = [i for i in missing if i["essential"]]
    return {"root": str(root), "items": items,
            "ok": len(missing_essential) == 0, "missing": len(missing),
            "missing_essential": len(missing_essential)}

@app.post("/vault/init")
async def vault_init(brain: str = Form("brain")):
    """Tạo các mục cấu trúc còn thiếu để vault chạy với Javis. Dùng CHUNG scaffold với brain
    mới tạo (đủ bộ: cấu trúc + memory seed + schema/wiki nav + năng lực HỆ THỐNG + index) →
    vault ngoài chọn qua path: cũng có đầy đủ chức năng mặc định, không còn bản seed thiếu."""
    root = Path(_brain_root(brain))
    missing = [i["label"] for i in _check_structure(root) if not i["present"]]
    try:
        _ensure_brain_scaffold(root)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    return {"ok": True, "created": missing}


@app.post("/brain/migrate")
async def brain_migrate(brain: str = Form("brain")):
    """Chuẩn hóa cấu trúc brain sang dạng phẳng đồng nhất: agents/ workflows/ memory/ skills/.
    AN TOÀN: chỉ MOVE khi nguồn tồn tại VÀ đích chưa có (không ghi đè, chạy lại nhiều lần vô hại)."""
    import shutil
    root = Path(_brain_root(brain))
    moved, skipped = [], []
    for old_rel, new_rel in [("Javis/agents", "agents"), ("Javis/workflows", "workflows"), ("Memory", "memory")]:
        src, dst = root / old_rel, root / new_rel
        if dst.exists():
            skipped.append(f"{new_rel} (đã tồn tại - bỏ qua)")
            continue
        if src.is_dir():
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                moved.append(f"{old_rel} → {new_rel}")
            except Exception as e:
                skipped.append(f"{old_rel}: {e}")
    return {"ok": True, "root": str(root), "moved": moved, "skipped": skipped}


def _safe_brain_name(name: str) -> str:
    name = (name or "").strip().strip(".")
    name = re.sub(r'[\\/:*?"<>|]+', "", name)
    return name[:60].strip()


_BRAINS_MD_CAP = 5000       # trần đếm .md mỗi brain cho dropdown chọn brain


def _list_brains_sync() -> dict:
    """Phần quét đĩa của GET /brains. Tách ra để chạy trong to_thread.

    Đếm bằng _count_md (scandir, trần THẬT, không theo symlink) thay cho rglob("*.md").
    rglob đi HẾT cây rồi mới trả, không có trần: đo được 136ms cho 4 brain / 837 file .md,
    và tăng tuyến tính theo kích thước vault. Đúng lỗi này đã được chẩn và ghi comment cho
    /viec/all (xem chỗ liệt kê brain RẺ ở dưới), nhưng /brains thì để nguyên - trong khi
    dashboard gọi nó lúc BOOT, tức chặn event loop ngay lúc app vừa dậy.
    Chạm trần thì trả đúng số trần và gắn cờ notes_capped để UI không nói dối là con số chính xác.
    """
    base = Path(BRAINS_DIR)
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    default = _default_brain_dir()
    try:
        default_resolved = default.resolve()
    except OSError:
        default_resolved = default
    out = []
    try:
        for p in sorted(base.iterdir(), key=lambda x: x.name.lower()):
            if not p.is_dir() or p.name.startswith("."):
                continue
            try:
                notes = _count_md(str(p), _BRAINS_MD_CAP)
            except Exception:
                notes = 0
            try:
                is_default = p.resolve() == default_resolved
            except OSError:
                is_default = False
            out.append({"name": p.name, "path": str(p), "notes": notes,
                        "notes_capped": notes >= _BRAINS_MD_CAP,
                        "is_default": is_default})
    except Exception as e:
        return {"dir": str(base), "brains": [], "error": str(e)}
    return {"dir": str(base), "brains": out}


@app.get("/brains")
async def list_brains():
    """Liệt kê mọi brain trong BRAINS_DIR (mỗi folder con = 1 brain) + số note .md.
    Dropdown chọn brain đổ từ đây (server-side) thay vì localStorage."""
    return await asyncio.to_thread(_list_brains_sync)


@app.post("/brains/new")
async def new_brain(name: str = Form(...)):
    """Tạo brain mới = folder con trong BRAINS_DIR + seed cấu trúc chuẩn."""
    safe = _safe_brain_name(name)
    if not safe:
        return JSONResponse({"ok": False, "error": "Tên brain không hợp lệ"}, status_code=400)
    root = Path(BRAINS_DIR) / safe
    if root.exists():
        return JSONResponse({"ok": False, "error": "Brain đã tồn tại"}, status_code=400)
    try:
        _ensure_brain_scaffold(root)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    git_brain.clear_tombstone(BRAINS_DIR, safe)   # dựng lại não cùng tên -> gỡ giấy báo tử để không bị xoá oan
    return {"ok": True, "name": safe, "path": str(root)}


_DELETE_SYNC_TASKS = set()   # giữ ref mạnh cho eager-sync sau khi xóa não (tránh GC nuốt task)


@app.post("/brains/delete")
async def delete_brain(name: str = Form(...), confirm: str = Form("")):
    """Xoá 1 brain: CHUYỂN vào thùng rác cục bộ (giữ 30 ngày) + ghi giấy báo tử để lan việc xoá
    sang mọi máy đồng bộ. Yêu cầu confirm == name. Chặn xoá não mặc định + chỉ trong BRAINS_DIR."""
    safe = _safe_brain_name(name)
    if not safe:
        return JSONResponse({"ok": False, "error": "Tên brain không hợp lệ"}, status_code=400)
    if (confirm or "").strip() != safe:
        return JSONResponse({"ok": False, "error": "Xác nhận không khớp tên brain"}, status_code=400)
    root = (Path(BRAINS_DIR) / safe).resolve()
    base = Path(BRAINS_DIR).resolve()
    if root == base or base not in root.parents:
        return JSONResponse({"ok": False, "error": "Brain ngoài phạm vi quản lý"}, status_code=400)
    if root == _default_brain_dir().resolve():
        return JSONResponse({"ok": False, "error": "Không thể xoá Brain mặc định"}, status_code=400)
    if not root.is_dir():
        return JSONResponse({"ok": False, "error": "Brain không tồn tại"}, status_code=404)
    trash_dir = str(cfgmod.STATE_DIR / "brain-trash")

    def _trash_and_mark():
        dest = git_brain.move_to_trash(str(root), trash_dir, safe)   # có retry cho Windows
        try:
            git_brain.write_tombstone(BRAINS_DIR, safe)              # giấy báo tử -> lan việc xoá
        except Exception:
            # Nguyên tử: ghi giấy báo tử lỗi thì ĐƯA brain trở lại - tránh trạng thái "mất mà không
            # có tombstone" (lần sync sau _restore_missing_brains sẽ hồi sinh nó).
            if dest:
                shutil.move(dest, str(root))
            raise
        return dest

    try:
        dest = await asyncio.to_thread(_trash_and_mark)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"Không xoá được (brain đang bận?): {e}"},
                            status_code=500)

    # Eager sync (nền, best-effort): đẩy lệnh xoá + tombstone lên remote NGAY thay vì chờ chu kỳ 6h.
    try:
        _b = cfgmod.read_settings().get("backup", {}) or {}
        if _b.get("enabled") and _b.get("repo_url") and _b.get("token") and git_brain.has_git():
            _t = asyncio.create_task(asyncio.to_thread(_do_backup))
            _DELETE_SYNC_TASKS.add(_t)
            _t.add_done_callback(_DELETE_SYNC_TASKS.discard)
    except Exception:
        pass

    return {"ok": True, "name": safe, "trashed": bool(dest)}

# ============================================================
# STUDIO - Agents / Skills / Workflows
# ============================================================
def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_]+", "-", s)
    return s[:60] or "item"

def _ascii_slug(s: str) -> str:
    """Slug KHÔNG DẤU (a-z0-9-) - dùng cho tên thư mục skill (Claude Code nạp bền hơn ASCII)."""
    import unicodedata
    s = (s or "").replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return _slugify(s)

def _read_md(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except Exception:
        return {}, ""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                meta = fastyaml.safe_load(parts[1]) or {}
            except Exception:
                meta = {}
            return (meta if isinstance(meta, dict) else {}), parts[2].strip()
    return {}, text

def _write_md(path, meta, body):
    fm = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    _atomic_write_text(path, f"---\n{fm}\n---\n\n{body}\n")

def _today():
    from datetime import date
    return date.today().strftime("%Y-%m-%d")

def _agents_dir(brain):
    return _brain_sub(_brain_root(brain), "agents", "Javis/agents")
def _workflows_dir(brain):
    return _brain_sub(_brain_root(brain), "workflows", "Javis/workflows")

def _agent_memory(brain, slug):
    f = _brain_memory_dir(brain) / "agents" / slug / "MEMORY.md"
    try:
        return f.read_text(encoding="utf-8") if f.exists() else ""
    except Exception:
        return ""

# ---- Agent tự bồi đắp: "model ĐỀ XUẤT, code GHI" (đúng nguyên tắc docs/22-tu-hoc) ----
# Bản đầu (0.35.3) cho agent tự Edit MEMORY.md, rào bằng lời "chỉ thêm dòng". Rào bằng
# lời thì model yếu có ngày Write đè cả file, và luật cấm-xoá làm bài học sai nằm vĩnh
# viễn, bộ nhớ chỉ phình không bao giờ gọn. Nay: agent phát dòng `JAVIS_LESSON: ...`
# cuối output, code bóc lấy và ghi vào ĐÚNG mục "## Bài học (tự học)" - trần cứng +
# chống trùng ép bằng code, phần chủ viết tay ngoài mục đó không bao giờ bị chạm.
_BAI_HOC_HEADER = "## Bài học (tự học)"
_BAI_HOC_TRAN = 15          # giữ N dòng MỚI NHẤT - bộ nhớ đặc dần thay vì dài dần
_BAI_HOC_RE = re.compile(r"^[ \t]*JAVIS_LESSON:[ \t]*(.+?)[ \t]*$", re.MULTILINE)

def _boc_bai_hoc(out):
    """Tách các dòng JAVIS_LESSON khỏi output agent. Trả (bài học, output đã sạch) -
    phải bóc khỏi output vì `out` chảy tiếp vào {{prev}} của bước sau và lên UI."""
    if not out or "JAVIS_LESSON" not in out:
        return [], out
    lessons = [m.group(1).strip()[:300] for m in _BAI_HOC_RE.finditer(out)][:3]
    sach = re.sub(r"\n{3,}", "\n\n", _BAI_HOC_RE.sub("", out)).strip()
    return [l for l in lessons if l], sach

def _ghi_bai_hoc(brain, slug, lessons):
    """Ghi bài học vào mục tự học của MEMORY.md. Vùng NGOÀI mục là của chủ - giữ nguyên
    từng ký tự. Trong mục: loại trùng (chuẩn hoá bỏ dấu câu/hoa thường) rồi cắt về
    _BAI_HOC_TRAN dòng mới nhất."""
    if not lessons:
        return
    try:
        f = _brain_memory_dir(brain) / "agents" / slug / "MEMORY.md"
        f.parent.mkdir(parents=True, exist_ok=True)
        text = f.read_text(encoding="utf-8") if f.exists() else ""
        lines = text.splitlines()
        i0 = next((i for i, l in enumerate(lines) if l.strip() == _BAI_HOC_HEADER), None)
        if i0 is None:
            truoc, bullets, sau = lines, [], []
        else:
            i1 = next((i for i in range(i0 + 1, len(lines)) if lines[i].startswith("## ")),
                      len(lines))
            truoc = lines[:i0]
            bullets = [l.rstrip() for l in lines[i0 + 1:i1] if l.strip().startswith("- ")]
            sau = lines[i1:]
        def _chuan(s):
            return re.sub(r"\W+", "", s).casefold()
        seen = {_chuan(b) for b in bullets}
        for l in lessons:
            b = "- " + l
            if _chuan(b) in seen:
                continue
            bullets.append(b)
            seen.add(_chuan(b))
        bullets = bullets[-_BAI_HOC_TRAN:]
        while truoc and not truoc[-1].strip():
            truoc.pop()
        moi = truoc + ([""] if truoc else []) + [_BAI_HOC_HEADER] + bullets
        if sau:
            moi += [""] + sau
        _atomic_write_text(f, "\n".join(moi).rstrip() + "\n")
    except Exception as e:
        print(f"[agent-memory] ghi bài học lỗi ({slug}): {e}", file=sys.stderr)

def _log_agent_run(brain, slug, task, out):
    try:
        d = _brain_memory_dir(brain) / "agents" / slug / "runs"
        d.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone, timedelta
        now = localefmt.now()
        with open(d / f"{now.strftime('%Y-%m-%d')}.md", "a", encoding="utf-8") as fh:
            # Cắt CẢ task: prompt bước workflow sau vòng retry có thể ôm cả kết quả cũ
            # (out[:8000] nối vào), không cắt là một lượt chạy phình cả chục KB nhật ký.
            fh.write(f"\n## {now.strftime('%H:%M')}\n**Task:** {task[:2000]}\n\n**Kết quả:** {out[:1500]}\n")
    except Exception:
        pass

# ---- Agents ----
# ---- Lõi dùng chung cho route VÀ cho Telegram (0.9.243) ----
# Trước đây khối Telegram gọi THẲNG các route handler như hàm Python thường
# (await list_agents(brain), await provider_models(provider=pid)...). Chạy được, nhưng
# là một quả bom hẹn giờ: tham số mặc định của handler là đối tượng fastapi Query, nên
# ngày nào có người gọi thiếu đối số thì `brain` trở thành một Query object, `_brain_root`
# nhận vào rồi `os.path.isdir(Query)` ném TypeError. Nay handler chỉ còn là lớp vỏ HTTP
# mỏng bọc quanh hàm thuần bên dưới, và Telegram gọi thẳng hàm thuần đó.

def agents_index(brain: str) -> list:
    """Danh sách agent của một brain. Lõi thuần, dùng chung cho GET /agents và Telegram."""
    out = []
    for f in sorted(_agents_dir(brain).glob("*.md")):
        meta, body = _read_md(f)
        out.append({"slug": f.stem, "name": meta.get("name", f.stem),
                    "role": meta.get("role", ""), "skills": meta.get("skills", []) or [],
                    "model": meta.get("model", ""), "prompt": body})
    return out

@app.get("/agents")
async def list_agents(brain: str = Query("brain")):
    return {"agents": agents_index(brain)}

@app.post("/agents")
async def save_agent(name: str = Form(...), role: str = Form(""), skills: str = Form(""),
                     model: str = Form(""), slug: str = Form(""), prompt: str = Form(""),
                     brain: str = Form("brain")):
    slug = slug or _slugify(name)
    skills_list = [s.strip() for s in re.split(r"[,\n]", skills) if s.strip()]
    meta = {"type": "agent", "name": name, "slug": slug, "role": role,
            "skills": skills_list, "model": model, "updated": _today()}  # "" = mặc định theo CLI
    _write_md(_agents_dir(brain) / f"{slug}.md", meta, (prompt.strip() or role))
    return {"ok": True, "slug": slug}

@app.post("/agents/delete")
async def delete_agent(slug: str = Form(...), brain: str = Form("brain")):
    f = _agents_dir(brain) / f"{slug}.md"
    if f.exists():
        f.unlink()
    return {"ok": True}

# ---- Skills ----

def skills_index(brain: str) -> list:
    """Chỉ mục skill của một brain (kèm cờ hệ thống + telemetry dùng).
    Lõi thuần, dùng chung cho GET /skills và Telegram."""
    # NGUỒN SKILL: canonical <brain>/skills/<slug>/SKILL.md, fallback đọc .claude/skills (legacy +
    # bản mirror) và .agents (rất cũ). Dùng skill_router (CHUNG với engine) → hiển thị == thực thi.
    # NHÓM = field `group` trong frontmatter (mặc định "Chung"). Skill TẮT = <base>/.disabled/<slug>.
    root = _brain_root(brain)
    sys_slugs = system_sync.system_skill_slugs()   # skill HỆ THỐNG (đi theo phiên bản app)
    usage = skill_usage.read_usage(root)           # telemetry (tín hiệu DƯƠNG một chiều)
    now = time.time()

    def _mtime(p):
        try:
            return Path(p).stat().st_mtime
        except OSError:
            return None

    # Danh sách trên trang Kỹ năng đi theo NGÔN NGỮ GIAO DIỆN, không theo ngôn ngữ trả lời:
    # đây là chữ trên màn hình. Skill nào chưa có bản dịch thì hiện nguyên bản gốc.
    _ui = localefmt.ngon_ngu_giao_dien()
    out = []
    for s in skill_router.list_skills(root, _ui):
        rec = usage.get(s["slug"])
        if not isinstance(rec, dict):   # sidecar tay-sửa hỏng dạng: {"slug": "khong-phai-dict"}
            rec = {}
        try:
            use_count = int(rec.get("use_count", 0) or 0)
        except (TypeError, ValueError):  # vd use_count: "abc" - coi như chưa đếm được, không sập trang
            use_count = 0
        out.append({**s,
                    "system": s["slug"] in sys_slugs,
                    "use_count": use_count,
                    "last_used_at": rec.get("last_used_at"),
                    "pinned": bool(rec.get("pinned", False)),
                    # stale = "chưa thấy dùng + đủ già". CHỈ để hiển thị tham khảo: skill nạp
                    # native qua .claude/skills không đi qua bộ đếm nên use=0 KHÔNG có nghĩa
                    # là vô dụng. Không có gì tự tắt dựa trên cờ này.
                    "stale": skill_usage.is_stale(rec, _mtime(s["path"]), now)})
    return out

@app.get("/skills")
async def list_skills(brain: str = Query("brain")):
    return {"skills": skills_index(brain)}


def _skills_dir(brain):
    """Thư mục skill CANONICAL của brain: <brain>/skills (phẳng, cùng hướng agents/workflows).
    Bản mirror sang <brain>/.claude/skills (cho Claude Code native) do system_sync.mirror_skills lo."""
    return skill_router.skills_base(_brain_root(brain), canonical=True)


@app.post("/skills/toggle")
async def skill_toggle(slug: str = Form(...), enabled: str = Form(...), brain: str = Form("brain")):
    """Bật/tắt skill = di chuyển folder giữa <brain>/skills/<slug> và <brain>/skills/.disabled/<slug>.
    Đồng bộ bản mirror .claude/skills (bật→copy, tắt→gỡ) để Claude native cwd=brain khớp trạng thái.
    CẢ HAI nhánh đều gọi lại mirror_skills (không chỉ nhánh bật) - xem lý do ở comment trong nhánh
    tắt bên dưới, đây là chỗ vá CRITICAL 1 của bản 0.9.64 (tắt rồi bật lại làm mất mirror vĩnh viễn)."""
    want = enabled in ("1", "true", "True", "on")
    if not skill_router.valid_slug(slug):   # chống traversal: slug 1 đoạn, dùng cho rmtree/rename bên dưới
        return JSONResponse({"error": "slug không hợp lệ"}, status_code=400)
    root = _brain_root(brain)
    try:
        system_sync.migrate_brain(root)   # brain cũ: kéo skill legacy .claude/skills → skills/ trước
    except Exception:
        pass
    sk = _skills_dir(brain)
    dis = sk / ".disabled"
    src = (dis / slug) if want else (sk / slug)
    dst = (sk / slug) if want else (dis / slug)
    if not src.is_dir():
        return {"ok": True} if dst.is_dir() else JSONResponse({"error": "Không tìm thấy skill"}, status_code=404)
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            shutil.rmtree(dst)
        src.rename(dst)
        mirror_slug = Path(root) / ".claude" / "skills" / slug
        if want:
            system_sync.mirror_skills(root)      # bật → tạo/cập nhật bản mirror cho Claude native
        else:
            if mirror_slug.is_dir():
                shutil.rmtree(mirror_slug)       # tắt → gỡ mirror để native không còn nạp
            # Gọi lại mirror_skills NGAY ở đây, không chỉ chờ lượt gọi tự nhiên kế tiếp (CRITICAL 1
            # đã vá): rename ở trên vừa đổi cây <root>/skills nên chữ ký của nó đã đổi, và lệnh này
            # ép cache ghi nhận đúng chữ ký-đã-tắt NGAY LẬP TỨC. Thiếu dòng này: `rename` giữ nguyên
            # st_mtime_ns/st_size, nên BẬT lại sau đó (rename ngược) làm chữ ký quay về Y HỆT giá
            # trị cache còn nhớ từ TRƯỚC KHI TẮT (vì tắt chưa từng gọi mirror_skills để cache thấy
            # trạng thái tắt ở giữa) → tầng 1 tưởng "cây không đổi gì" → bỏ qua → bản mirror vừa
            # rmtree ở trên KHÔNG BAO GIỜ được tạo lại, cho tới khi khởi động lại tiến trình. Xem
            # test_system_sync.py (chuỗi tắt->bật) và CHANGELOG 0.9.64.
            system_sync.mirror_skills(root)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return {"ok": True}


@app.get("/skills/get")
async def skill_get(slug: str = Query(...), brain: str = Query("brain")):
    if not skill_router.valid_slug(slug):
        return JSONResponse({"error": "slug không hợp lệ"}, status_code=400)
    root = _brain_root(brain)
    smd = skill_router.resolve_skill_file(root, slug)   # canonical → .claude → .agents (bản BẬT)
    if not smd:
        for base in ("skills", ".claude/skills"):        # cho phép xem/sửa cả skill đang TẮT
            cand = Path(root) / base / ".disabled" / slug / "SKILL.md"
            if cand.is_file():
                smd = cand
                break
    if not smd or not smd.is_file():
        return JSONResponse({"error": "Không tìm thấy skill"}, status_code=404)
    meta, body = _read_md(smd)
    return {"slug": slug, "name": meta.get("name", slug), "description": meta.get("description", ""),
            "group": meta.get("group") or "Chung", "body": body}


@app.post("/skills")
async def save_skill(name: str = Form(...), description: str = Form(""), group: str = Form("Chung"),
                     body: str = Form(""), slug: str = Form(""), brain: str = Form("brain")):
    """Tạo/cập nhật skill → CANONICAL <brain>/skills/<slug>/SKILL.md. group vào frontmatter để gom
    nhóm. Sau khi ghi, mirror sang .claude/skills để Claude native (cwd=brain) thấy ngay."""
    slug = (slug or _ascii_slug(name)).strip()
    if not skill_router.valid_slug(slug):
        return JSONResponse({"error": "Tên skill không hợp lệ"}, status_code=400)
    # Ép trần description NGAY, trước khi tạo bất cứ thư mục nào -> request bị từ chối không
    # để lại folder skill rỗng trên đĩa. Router cắt ở SKILL_DESC_MAX nên vượt trần = mất chữ
    # im lặng; chặn ở đây tốt hơn là ghi bừa rồi để runtime cắt.
    desc_err = skill_router.validate_description(description)
    if desc_err:
        return JSONResponse({"error": desc_err}, status_code=400)
    root = _brain_root(brain)
    try:
        system_sync.migrate_brain(root)   # brain cũ: chuẩn hoá về skills/ trước khi ghi
    except Exception:
        pass
    sk = _skills_dir(brain)
    # SỬA skill đang TẮT thì GIỮ nguyên trạng thái tắt (ghi lại vào .disabled), không tự bật lên
    # + không để lại bản mồ côi. Skill MỚI (chưa có ở đâu) → ghi vào vị trí BẬT (mặc định bật).
    disabled_dir = sk / ".disabled" / slug
    d = disabled_dir if disabled_dir.is_dir() else (sk / slug)
    d.mkdir(parents=True, exist_ok=True)
    meta = {"name": name, "description": description, "group": (group or "Chung").strip()}
    # GIỮ LẠI các bản dịch (`description_en`, `name_en`...) của skill đang có. Form chỉ gửi lên
    # bản gốc, nên ghi đè trắng meta là mỗi lần user bấm Lưu lại xoá sạch bản dịch mà không ai
    # thấy - skill hệ thống sẽ tụt về mô tả tiếng Việt cho người dùng tiếng Anh.
    cu, _ = _read_md(d / "SKILL.md")
    for k, v in (cu or {}).items():
        if skill_router.la_khoa_ngon_ngu(k) and k not in meta:
            meta[k] = v
    _write_md(d / "SKILL.md", meta, body or f"# {name}\n\n{description}")
    try:
        system_sync.mirror_skills(root)   # bật → cập nhật mirror; tắt (.disabled) → mirror bỏ qua
    except Exception:
        pass
    return {"ok": True, "slug": slug}


@app.post("/skills/delete")
async def delete_skill(slug: str = Form(...), brain: str = Form("brain")):
    if system_sync.is_system_skill(slug):
        return JSONResponse({"error": "Skill hệ thống của Javis OS - không xoá được (đi theo "
                             "phiên bản app, xoá cũng tự cài lại khi cập nhật). Muốn ngừng dùng "
                             "thì TẮT skill (bỏ tích)."}, status_code=400)
    if not skill_router.valid_slug(slug):
        return JSONResponse({"error": "slug không hợp lệ"}, status_code=400)
    root = Path(_brain_root(brain))
    # Xoá ở MỌI nơi: canonical (bật+tắt) + bản mirror .claude (bật+tắt) + legacy .agents.
    targets = [root / "skills" / slug, root / "skills" / ".disabled" / slug,
               root / ".claude" / "skills" / slug, root / ".claude" / "skills" / ".disabled" / slug,
               root / ".agents" / slug]
    found = False
    for d in targets:
        if d.is_dir():
            try:
                shutil.rmtree(d)
                found = True
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=500)
    return {"ok": True} if found else JSONResponse({"error": "Không tìm thấy skill"}, status_code=404)


@app.post("/skills/group")
async def skill_set_group(slug: str = Form(...), group: str = Form(...), brain: str = Form("brain")):
    """Đổi nhóm 1 skill (chỉ cập nhật field group, giữ nguyên body)."""
    if not skill_router.valid_slug(slug):
        return JSONResponse({"error": "slug không hợp lệ"}, status_code=400)
    smd = skill_router.resolve_skill_file(_brain_root(brain), slug)
    if not smd or not smd.is_file():
        return JSONResponse({"error": "Không tìm thấy"}, status_code=404)
    meta, body = _read_md(smd)
    meta["group"] = (group or "Chung").strip()
    _write_md(smd, meta, body)
    try:
        system_sync.mirror_skills(_brain_root(brain))
    except Exception:
        pass
    return {"ok": True}


# ============================================================
# Quản lý File (File Manager) - duyệt / đọc / sửa / tải / xoá file.
# TRẦN duyệt (_files_ceiling): mặc định localhost = ổ đĩa chứa brain (out được ra root để
# đọc/sửa data ngoài vault); public bind (VPS/login) = khoá trong brain. Chỉnh bằng
# JAVIS_FILES_ROOT. Điểm vào mặc định LUÔN là brain. _safe_path chặn vượt trần (chống ../).
# ============================================================
_TEXT_EXTS = {".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".js", ".ts", ".py",
              ".html", ".css", ".toml", ".ini", ".log", ".sh", ".bat", ".xml", ".svg", ".env"}


def _files_ceiling(brain: str) -> Path:
    """Ranh giới trên của File Manager (không cho 'Lên' quá đây). Brain LUÔN nằm trong trần.
    JAVIS_FILES_ROOT: `brain`/`vault` = khoá trong brain | `drive`/`root` = ổ đĩa chứa brain |
    <đường dẫn tuyệt đối> = trần tuỳ ý (phải chứa brain). KHÔNG đặt: localhost → ổ đĩa (chủ máy
    tin cậy), bind public → khoá brain (fail-closed, tránh hở cả ổ đĩa qua web)."""
    broot = Path(_brain_root(brain)).resolve()
    env = os.getenv("JAVIS_FILES_ROOT", "").strip()
    ceil = None
    if env:
        low = env.lower()
        if low in ("brain", "vault"):
            ceil = broot
        elif low in ("drive", "root"):
            ceil = Path(broot.anchor or broot)
        else:
            cand = Path(env).expanduser()
            if cand.is_dir():
                ceil = cand.resolve()
    elif not cfgmod.require_login():
        ceil = Path(broot.anchor or broot)      # localhost = chủ máy → tới ổ đĩa
    if ceil is None:
        ceil = broot                            # public / cấu hình lạ → khoá brain
    try:
        broot.relative_to(ceil)                 # brain phải trong trần, else fallback brain
    except ValueError:
        ceil = broot
    return ceil


def _files_root(brain: str) -> Path:
    """Trần duyệt hiện hành (mọi path tương đối tính từ đây). Alias giữ tên cũ cho call site."""
    return _files_ceiling(brain)


def _safe_path(brain: str, rel: str) -> Path:
    """Resolve rel TRONG trần duyệt; ném ValueError nếu vượt ra ngoài (chống ../)."""
    root = _files_root(brain)
    rel = (rel or "").strip().replace("\\", "/").lstrip("/")
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        raise ValueError("Đường dẫn ngoài phạm vi cho phép")
    return target


def _safe_serve_path(brain: str, rel: str) -> Path:
    """Resolve rel để PHỤC VỤ/ĐỌC file, chấp nhận CẢ HAI quy ước đường dẫn:
    - tương đối TRẦN duyệt (File Manager, path lấy từ /files/list) → thử trước;
    - tương đối GỐC BRAIN/vault (link & ảnh trong chat, do AI ghi theo CLAUDE.md) → dự phòng.
    Lý do: khi trần duyệt nằm CAO hơn gốc brain (vd localhost = tới ổ đĩa), đường dẫn vault kiểu
    'videos/x.mp4' nếu chỉ tính theo trần sẽ thành 'D:/videos/x.mp4' → 404. Cả hai nhánh đều bị
    KHOÁ trong trần (chống ../). CHỈ dùng cho endpoint CHỈ-ĐỌC (raw/read/download) - KHÔNG dùng cho
    ghi/xoá/đổi tên để tránh mơ hồ khi tạo file mới."""
    root = _files_root(brain)
    rel = (rel or "").strip().replace("\\", "/").lstrip("/")
    ceil_target = (root / rel).resolve()
    ceil_in = ceil_target == root or root in ceil_target.parents
    if ceil_in and ceil_target.exists():
        return ceil_target
    broot = Path(_brain_root(brain)).resolve()
    if broot != root:                                   # chỉ khi trần KHÁC gốc brain
        brain_target = (broot / rel).resolve()
        if (brain_target == broot or broot in brain_target.parents) and brain_target.exists():
            return brain_target                         # đường dẫn vault, vẫn nằm trong gốc brain
    if not ceil_in:
        raise ValueError("Đường dẫn ngoài phạm vi cho phép")
    return ceil_target                                  # không thấy: trả theo trần để 404 nhất quán


def _files_rel(root: Path, p: Path) -> str:
    """Đường dẫn POSIX của p tương đối so với trần root ('' nếu p == root)."""
    return "" if p == root else str(p.relative_to(root)).replace("\\", "/")


@app.get("/files/list")
async def files_list(brain: str = Query("brain"), path: str = Query(None)):
    root = _files_root(brain)
    broot = Path(_brain_root(brain)).resolve()
    try:
        # path VẮNG (None) = điểm vào mặc định = BRAIN; path="" = trần (ổ đĩa); còn lại = tương đối trần.
        # Dùng _safe_serve_path (chỉ-đọc) nên chấp CẢ quy ước tương đối GỐC BRAIN - link trong chat
        # do AI ghi theo lối đó, trước đây rơi hết vào nhánh lỗi bên dưới.
        d = broot if path is None else _safe_serve_path(brain, path)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    # Trỏ trúng một FILE, hoặc trúng chỗ KHÔNG CÓ GÌ, thì đừng trả về một câu lỗi trên nền rỗng.
    # Người dùng vừa bấm một link trong chat: đích của họ ở đây chứ không phải chữ "Không phải thư
    # mục" giữa màn hình trắng (chủ repo báo 2026-08-13). Mở thư mục CHA - hoặc tổ tiên gần nhất
    # còn tồn tại - rồi nói rõ đích là gì:
    #   focus   = tên file mà đường dẫn trỏ trúng (client soi sáng + mở thẳng ra sửa)
    #   missing = đường dẫn đã hỏi nhưng không có (client tự đi tìm theo tên, không dấu cũng khớp)
    focus, missing = "", ""
    if not d.is_dir():
        if d.is_file():
            focus, d = d.name, d.parent
        else:
            missing = (path or "").replace("\\", "/").strip("/")
            leo = d.parent
            while not leo.is_dir() and root in leo.parents:
                leo = leo.parent
            # Leo hết đường mà chỉ tới TRẦN (trên localhost trần là cả ổ đĩa) thì về nhà brain:
            # đổ nguyên ổ đĩa ra vì một link gõ sai là câu trả lời tệ hơn cả câu lỗi cũ.
            if not leo.is_dir() or (leo == root and root != broot):
                leo = broot if broot.is_dir() else root
            d = leo
    items = []
    for p in sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        try:
            st = p.stat()
            items.append({"name": p.name, "type": "dir" if p.is_dir() else "file",
                          "size": st.st_size if p.is_file() else 0, "mtime": st.st_mtime,
                          "ext": p.suffix.lower()})
        except (PermissionError, OSError):
            continue
    return {"root": root.name or str(root), "path": _files_rel(root, d),
            "home": _files_rel(root, broot),                       # brain = 'nhà' (nút ⌂)
            "parent": None if d == root else _files_rel(root, d.parent),   # None = đã ở trần → ẩn Lên
            "focus": focus, "missing": missing,
            "items": items}


def _fold_accents(s: str) -> str:
    """Bỏ dấu tiếng Việt + thường hoá để so khớp tên file không phân biệt dấu (đ -> d)."""
    import unicodedata
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.replace("đ", "d").replace("Đ", "D").lower()


@app.get("/files/search")
async def files_search(brain: str = Query("brain"), q: str = Query(""), limit: int = Query(50),
                       mode: str = Query("all")):
    """Tìm note trong GỐC BRAIN (KHÔNG phải trần duyệt - tránh quét cả ổ đĩa trên localhost).
    `mode=name` khớp TÊN file (mọi loại, không phân biệt dấu tiếng Việt), `mode=content` tìm
    trong NỘI DUNG file text, còn `mode=all` giữ hành vi cũ là tìm cả hai; bỏ file >1MB
    và thư mục ẩn/nặng. Path trả về tính theo TRẦN (giống /files/list) để mở bằng cùng quy ước.
    Walk chạy trong threadpool để không chặn event loop FastAPI."""
    from starlette.concurrency import run_in_threadpool
    q = (q or "").strip()
    if not q:
        return {"items": [], "q": q}
    mode = (mode or "all").strip().lower()
    if mode not in ("name", "content", "all"):
        mode = "all"
    root = _files_root(brain)                        # trần (để tính path trả về, khớp /files/list)
    broot = Path(_brain_root(brain)).resolve()       # phạm vi quét = gốc brain
    ql = q.lower()
    qf = _fold_accents(q)                            # bản không dấu (khớp tên kể cả gõ thiếu dấu)
    try:
        limit = max(1, min(int(limit), 200))
    except (TypeError, ValueError):
        limit = 50
    SKIP_DIRS = {".git", "node_modules", "__pycache__", ".obsidian", ".trash", ".venv", ".pytest_cache"}

    def _walk():
        out = []
        for dirpath, dirnames, filenames in os.walk(broot):
            dirnames[:] = [dn for dn in dirnames if not dn.startswith(".") and dn not in SKIP_DIRS]
            for fn in sorted(filenames):
                if len(out) >= limit:
                    return out
                p = Path(dirpath) / fn
                ext = p.suffix.lower()
                name_hit = mode in ("name", "all") and (ql in fn.lower() or qf in _fold_accents(fn))
                content_hit = False
                snippet, line_no = "", 0
                if mode in ("content", "all") and ext in _TEXT_EXTS:
                    try:
                        if p.stat().st_size <= 1_000_000:
                            txt = p.read_text(encoding="utf-8", errors="ignore")
                            idx = txt.lower().find(ql)
                            if idx >= 0:
                                content_hit = True
                                line_no = txt.count("\n", 0, idx) + 1
                                a = max(0, idx - 40)
                                snippet = txt[a:idx + 80].replace("\n", " ").replace("\r", " ").strip()
                    except (OSError, ValueError):
                        pass
                if name_hit or content_hit:
                    try:
                        rel = _files_rel(root, p)
                    except ValueError:
                        continue
                    out.append({"path": rel, "name": fn, "ext": ext, "snippet": snippet,
                                "line": line_no,
                                "match": "content" if (mode == "content" or (mode == "all" and content_hit)) else "name"})
        return out

    items = await run_in_threadpool(_walk)
    return {"items": items, "q": q, "mode": mode}


# --- Chữa file .md bị bản cũ làm hỏng ------------------------------------------------------
# Bản <= 0.33.3 lưu note .md qua trình sửa trực quan là phá frontmatter (`---` thành `* * *`)
# và dồn dấu gạch chéo (`1.` -> `1\.` -> `1\\.`). 0.33.4 bịt đường đó, nhưng file đã hỏng thì
# phải chữa. Luật nhận dạng nằm trong md_repair.py - chỉ sửa thứ mà CHỈ lỗi đó tạo ra được.
_MD_HONG_MAX_FILE = 1_000_000        # cùng ngưỡng với tìm theo nội dung
_MD_HONG_MAX_HIT = 500               # đủ để một brain rất to vẫn liệt được, không phình vô hạn


def _quet_md_hong(brain: str, chi_path: set = None):
    """Đi khắp GỐC BRAIN tìm file .md hỏng. Trả về [{path, name, van_de, mo_ta}] (path theo TRẦN,
    giống /files/list). chi_path (tương đối trần) = chỉ soi đúng mấy file đó."""
    root = _files_root(brain)
    broot = Path(_brain_root(brain)).resolve()
    SKIP_DIRS = {".git", "node_modules", "__pycache__", ".obsidian", ".trash", ".venv", ".pytest_cache"}
    out = []
    for dirpath, dirnames, filenames in os.walk(broot):
        dirnames[:] = [dn for dn in dirnames if not dn.startswith(".") and dn not in SKIP_DIRS]
        for fn in sorted(filenames):
            if not fn.lower().endswith(".md") or len(out) >= _MD_HONG_MAX_HIT:
                continue
            p = Path(dirpath) / fn
            try:
                rel = _files_rel(root, p)
            except ValueError:
                continue
            if chi_path is not None and rel not in chi_path:
                continue
            try:
                if p.stat().st_size > _MD_HONG_MAX_FILE:
                    continue
                txt = p.read_text(encoding="utf-8")
            except (OSError, ValueError, UnicodeDecodeError):
                continue
            van_de = md_repair.tim_van_de(txt)
            if van_de:
                out.append({"path": rel, "name": fn, "van_de": van_de,
                            "mo_ta": md_repair.mo_ta_van_de(van_de)})
    return out


@app.get("/files/md-hong")
async def files_md_hong(brain: str = Query("brain")):
    """CHỈ SOI, không ghi gì: liệt kê file .md còn dấu vết hỏng của bản cũ."""
    from starlette.concurrency import run_in_threadpool
    items = await run_in_threadpool(_quet_md_hong, brain)
    return {"items": items, "cham_nguong": len(items) >= _MD_HONG_MAX_HIT}


@app.post("/files/md-hong/sua")
async def files_md_hong_sua(brain: str = Form("brain"), paths: str = Form("")):
    """Chữa thật. `paths` = JSON list đường dẫn (theo trần); bỏ trống = chữa mọi file soi thấy.

    Ghi bằng _atomic_write_text nên không có cảnh file bị cắt nửa chừng. Brain có bật sao lưu
    git thì mọi thay đổi vẫn lần lại được như mọi lần sửa khác."""
    from starlette.concurrency import run_in_threadpool
    chi = None
    if (paths or "").strip():
        try:
            chi = {str(x).replace("\\", "/").strip("/") for x in json.loads(paths)}
        except (ValueError, TypeError):
            return JSONResponse({"error": "Danh sách đường dẫn không đọc được"}, status_code=400)

    def _lam():
        da_sua, loi = [], []
        for it in _quet_md_hong(brain, chi):
            try:
                f = _safe_path(brain, it["path"])
                moi, van_de = md_repair.sua(f.read_text(encoding="utf-8"))
                _atomic_write_text(f, moi)
                da_sua.append({"path": it["path"], "name": it["name"], "van_de": van_de})
            except (OSError, ValueError, UnicodeDecodeError) as e:
                loi.append({"path": it["path"], "name": it["name"], "loi": str(e)})
        return da_sua, loi

    da_sua, loi = await run_in_threadpool(_lam)
    return {"ok": True, "da_sua": da_sua, "loi": loi}


@app.get("/files/read")
async def files_read(brain: str = Query("brain"), path: str = Query(...)):
    try:
        f = _safe_serve_path(brain, path)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if not f.is_file():
        return JSONResponse({"error": "Không tìm thấy file"}, status_code=404)
    if f.stat().st_size > 2_000_000:
        return JSONResponse({"error": "File quá lớn để xem (>2MB) - hãy tải về"}, status_code=413)
    try:
        text = f.read_text(encoding="utf-8")
    except Exception:
        return JSONResponse({"error": "File nhị phân - không xem được dạng văn bản"}, status_code=415)
    # `abs` để trình sửa ghim được file đang mở vào khung chat: engine cần ĐƯỜNG DẪN THẬT
    # mới mở được file, mà đường dẫn tương đối ở đây tính theo TRẦN DUYỆT chứ không theo gốc
    # brain (hai cái khác nhau khi trần cao hơn brain) nên client tự ghép là ghép sai.
    return {"path": path, "name": f.name, "content": text, "abs": str(f),
            "editable": f.suffix.lower() in _TEXT_EXTS, "ext": f.suffix.lower()}


@app.post("/files/write")
async def files_write(brain: str = Form("brain"), path: str = Form(...), content: str = Form("")):
    try:
        f = _safe_path(brain, path)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    f.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(f, content)
    return {"ok": True}


@app.post("/files/mkdir")
async def files_mkdir(brain: str = Form("brain"), path: str = Form(""), name: str = Form(...)):
    try:
        d = _safe_path(brain, (path.rstrip("/") + "/" + _sanitize_filename(name)).lstrip("/"))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    d.mkdir(parents=True, exist_ok=True)
    return {"ok": True}


@app.post("/files/delete")
async def files_delete(brain: str = Form("brain"), path: str = Form(...)):
    try:
        p = _safe_path(brain, path)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if p == _files_root(brain) or p == Path(_brain_root(brain)).resolve():
        return JSONResponse({"error": "Không thể xoá thư mục gốc / brain"}, status_code=400)
    try:
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return {"ok": True}


@app.post("/files/rename")
async def files_rename(brain: str = Form("brain"), path: str = Form(...), newname: str = Form(...)):
    try:
        p = _safe_path(brain, path)
        parent_rel = str(Path(path).parent).replace("\\", "/")
        dst = _safe_path(brain, (("" if parent_rel == "." else parent_rel) + "/" + _sanitize_filename(newname)).lstrip("/"))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if not p.exists():
        return JSONResponse({"error": "Không tìm thấy"}, status_code=404)
    p.rename(dst)
    return {"ok": True}


@app.post("/files/upload")
async def files_upload(file: UploadFile = File(...), brain: str = Form("brain"), path: str = Form("")):
    try:
        d = _safe_path(brain, path)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    d.mkdir(parents=True, exist_ok=True)
    dest = _unique_path(str(d), _sanitize_filename(file.filename))
    try:
        await _save_upload_stream(file, dest)
    except Exception as e:
        return JSONResponse({"error": f"Ghi file thất bại: {e}"}, status_code=500)
    return {"ok": True, "name": os.path.basename(dest)}


@app.get("/files/download")
async def files_download(brain: str = Query("brain"), path: str = Query(...)):
    try:
        f = _safe_serve_path(brain, path)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if f.is_dir():
        return await zip_dir_response(brain, path)   # trỏ vào thư mục → tự nén .zip
    if not f.is_file():
        return JSONResponse({"error": "Không tìm thấy file"}, status_code=404)
    return FileResponse(str(f), filename=f.name)


# Trần an toàn khi nén thư mục: trên localhost trần duyệt có thể là CẢ Ổ ĐĨA, một cú bấm nhầm
# ở thư mục gốc sẽ nén hàng trăm nghìn file. Dừng SỚM ngay khi vượt, không nén nửa vời.
_ZIP_MAX_BYTES = 2 * 1024 * 1024 * 1024      # 2GB dữ liệu thô
_ZIP_MAX_FILES = 20000                       # 20 nghìn file


class _ZipTooBig(Exception):
    """Thư mục vượt trần _ZIP_MAX_* - dừng nén, báo người dùng chọn thư mục con."""


def _zip_scan(src: Path, zf=None):
    """Duyệt src, đếm (số file, tổng byte); nếu zf khác None thì ghi luôn vào zip đó.
    Bỏ qua symlink để không đi vòng ra ngoài trần duyệt. Ném _ZipTooBig khi vượt trần.
    Chạy trong threadpool (I/O nặng) - KHÔNG gọi thẳng trên event loop."""
    files = total = 0
    for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
        if zf is not None:
            rel_dir = Path(dirpath).relative_to(src)
            arc_dir = src.name if str(rel_dir) == "." else (Path(src.name) / rel_dir).as_posix()
            zf.writestr(arc_dir + "/", b"")          # giữ cả thư mục rỗng
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.is_symlink():
                continue
            try:
                size = p.stat().st_size
            except OSError:
                continue                              # file bị khoá/biến mất giữa chừng: bỏ qua
            files += 1
            total += size
            if files > _ZIP_MAX_FILES or total > _ZIP_MAX_BYTES:
                raise _ZipTooBig()
            if zf is not None:
                try:
                    zf.write(p, (Path(src.name) / p.relative_to(src)).as_posix())
                except (OSError, ValueError):
                    continue
    return files, total


def _zip_dir_sync(src: Path, dst: str):
    """Nén CẢ thư mục src vào file zip dst. Trả (số file, tổng byte thô)."""
    import zipfile
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        return _zip_scan(src, zf)


def _rm_quiet(p):
    try:
        os.unlink(p)
    except OSError:
        pass


def _zip_too_big_msg():
    return (f"Thư mục quá lớn để nén (trần {_ZIP_MAX_FILES:,} file hoặc "
            f"{_ZIP_MAX_BYTES // (1024 ** 3)}GB). Hãy tải từng thư mục con.")


async def zip_dir_response(brain: str, path: str, probe: bool = False):
    """Lõi thuần của /files/zip (route handler KHÔNG được gọi nhau như hàm thường, xem
    test_handler_khong_goi_truc_tiep). Trả JSON đo khi probe=True, còn lại trả file .zip.

    Zip dựng ra file TẠM trong threadpool (không chặn event loop) rồi gửi; file tạm xoá
    sau khi gửi xong qua BackgroundTask."""
    import tempfile
    from starlette.background import BackgroundTask
    from starlette.concurrency import run_in_threadpool
    try:
        d = _safe_serve_path(brain, path)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if not d.is_dir():
        return JSONResponse({"error": "Không phải thư mục"}, status_code=404)
    name = (d.name or "brain") + ".zip"
    if probe:
        try:
            files, total = await run_in_threadpool(_zip_scan, d, None)
        except _ZipTooBig:
            return JSONResponse({"error": _zip_too_big_msg()}, status_code=413)
        except Exception as e:
            return JSONResponse({"error": f"Không đọc được thư mục: {e}"}, status_code=500)
        return {"ok": True, "files": files, "bytes": total, "name": name}
    fd, tmp = tempfile.mkstemp(prefix="javis-zip-", suffix=".zip")
    os.close(fd)
    try:
        await run_in_threadpool(_zip_dir_sync, d, tmp)
    except _ZipTooBig:
        _rm_quiet(tmp)
        return JSONResponse({"error": _zip_too_big_msg()}, status_code=413)
    except Exception as e:
        _rm_quiet(tmp)
        return JSONResponse({"error": f"Nén thất bại: {e}"}, status_code=500)
    return FileResponse(tmp, media_type="application/zip", filename=name,
                        background=BackgroundTask(_rm_quiet, tmp))


@app.get("/files/zip")
async def files_zip(brain: str = Query("brain"), path: str = Query(""), probe: int = Query(0)):
    """Tải CẢ một thư mục về máy dưới dạng .zip (File Manager + cây file: nút ⤓).

    probe=1 chỉ ĐO trước (số file, dung lượng) và trả JSON - dashboard hỏi trước để báo
    lỗi tử tế / xin xác nhận khi thư mục nặng, thay vì để trình duyệt tải về một trang lỗi."""
    return await zip_dir_response(brain, path, probe=bool(probe))


def raw_file_response(brain: str, path: str, dl: bool = False):
    """Lõi thuần của /files/raw (route handler KHÔNG được gọi nhau như hàm thường, xem
    test_handler_khong_goi_truc_tiep). Trả file inline, hoặc ép tải khi dl=True."""
    try:
        f = _safe_serve_path(brain, path)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if not f.is_file():
        return JSONResponse({"error": "Không tìm thấy file"}, status_code=404)
    if dl:
        return FileResponse(str(f), filename=f.name)   # ép tải (giữ tên, kể cả tên tiếng Việt)
    mt, _ = mimetypes.guess_type(f.name)
    resp = FileResponse(str(f), media_type=mt or "application/octet-stream")
    resp.headers["Content-Disposition"] = "inline"      # hiển thị trong trình duyệt, không ép tải
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@app.get("/files/raw")
async def files_raw(brain: str = Query("brain"), path: str = Query(...), dl: int = Query(0)):
    """Phục vụ file THÔ để XEM INLINE trong trình duyệt: ảnh hiện trong <img>, pdf mở thẳng trên
    tab, mọi file khác có URL tĩnh để mở/tải. Khác /files/download (luôn ép tải về): mặc định
    inline; truyền dl=1 để ép tải. Cùng rào chống traversal (_safe_serve_path)."""
    return raw_file_response(brain, path, dl=bool(dl))


@app.get("/brains/{brain_name}/{path:path}")
async def brain_file_compat(brain_name: str, path: str, dl: int = Query(0)):
    """Tương thích link file cũ do chat/AI đã xuất dạng ``/brains/<tên>/<path>``.

    Route chuẩn vẫn là /files/raw. Link cũ đã nằm trong lịch sử chat hoặc đã được copy ra ngoài
    không thể sửa lại, nên server ánh xạ tên brain trực tiếp sang đúng thư mục con của BRAINS_DIR.
    Chỉ nhận đúng một thư mục con thật (không symlink/không traversal), rồi dùng lại toàn bộ rào
    _safe_serve_path của /files/raw.
    """
    safe_name = _safe_brain_name(brain_name)
    if not safe_name or safe_name != str(brain_name or "").strip():
        return JSONResponse({"error": "Tên brain không hợp lệ"}, status_code=400)
    base = Path(BRAINS_DIR).resolve()
    root = (base / safe_name).resolve()
    if root.parent != base or not root.is_dir():
        return JSONResponse({"error": "Không tìm thấy brain"}, status_code=404)
    return raw_file_response(str(root), path, dl=bool(dl))


# ============================================================
# Dataview lite + tick task (cảm hứng obsidian-dataview / obsidian-tasks).
# /files/mdindex quét note .md trong GỐC BRAIN thành chỉ mục (frontmatter, tag, task
# kèm ký hiệu ngày/độ ưu tiên kiểu obsidian-tasks) - dashboard tự chạy truy vấn client.
# /files/taskcheck lật một dòng "- [ ]" <-> "- [x]" ghi thẳng vào file (tick là lưu).
# ============================================================
_MD_TASK_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+\[( |x|X)\]\s+(.*)$")
_MD_TAG_RE = re.compile(r"(?<![\w#])#([A-Za-zÀ-ỹ][\w\-/À-ỹ]*)")
_TASK_DATE_KEYS = {"📅": "due", "⏳": "scheduled", "🛫": "start", "✅": "done", "➕": "created"}
_TASK_PRIO = {"🔺": 0, "⏫": 1, "🔼": 2, "🔽": 4, "⏬": 5}
_TASK_FIELD_RE = re.compile(r"(📅|⏳|🛫|✅|➕)\s*(\d{4}-\d{2}-\d{2})")


def _md_task_fields(text):
    """Bóc ký hiệu obsidian-tasks khỏi text task: ngày (📅 hạn, ⏳ dự kiến, 🛫 bắt đầu,
    ✅ xong, ➕ tạo) + độ ưu tiên (🔺⏫🔼🔽⏬; không có = 3). Trả (text sạch, dict field)."""
    fields = {"priority": 3}

    def _take(m):
        fields[_TASK_DATE_KEYS[m.group(1)]] = m.group(2)
        return ""

    clean = _TASK_FIELD_RE.sub(_take, text)
    for emo, p in _TASK_PRIO.items():
        if emo in clean:
            fields["priority"] = p
            clean = clean.replace(emo, "")
    return " ".join(clean.split()), fields


def _json_safe_fm(v):
    """Đưa giá trị YAML frontmatter về dạng JSON-serializable (date -> chuỗi ISO)."""
    import datetime as _dt
    if isinstance(v, dict):
        return {str(k): _json_safe_fm(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe_fm(x) for x in v]
    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.isoformat()
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)


def _scan_note_md(text):
    """Bóc (frontmatter, tags, tasks) từ nội dung MỘT file .md. Bỏ qua nội dung nằm
    trong code fence ``` để không nhặt nhầm task/tag trong ví dụ code. Số dòng của task
    tính theo FILE GỐC (1-based) để /files/taskcheck lật đúng dòng."""
    fm, body = {}, text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                meta = fastyaml.safe_load(parts[1])
                if isinstance(meta, dict):
                    fm = _json_safe_fm(meta)
            except Exception:
                fm = {}
            body = parts[2]
    fm_lines = text[: len(text) - len(body)].count("\n") if body is not text else 0
    tags = set()
    fmt = fm.get("tags") or fm.get("tag")
    if isinstance(fmt, str):
        fmt = [t for t in re.split(r"[,\s]+", fmt) if t]
    if isinstance(fmt, list):
        for t in fmt:
            tags.add("#" + str(t).lstrip("#"))
    tasks = []
    in_fence = False
    for i, line in enumerate(body.split("\n")):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for tg in _MD_TAG_RE.finditer(line):
            tags.add("#" + tg.group(1))
        tm = _MD_TASK_RE.match(line)
        if tm:
            raw_text = tm.group(4).rstrip("\r").strip()
            clean, fields = _md_task_fields(raw_text)
            task = {"line": fm_lines + i + 1, "raw": line.rstrip("\r"), "text": clean,
                    "checked": tm.group(3).lower() == "x",
                    "tags": ["#" + t.group(1) for t in _MD_TAG_RE.finditer(raw_text)]}
            task.update(fields)
            tasks.append(task)
    return fm, sorted(tags), tasks


# Cache chỉ mục TĂNG DẦN theo mtime: giữa 2 lần gọi thường chỉ 1-2 note đổi, nên chỉ
# parse lại file có (mtime, size) khác lần trước; còn lại dùng bản đã parse trong RAM.
# Vault vài nghìn note: lần đầu tốn như cũ, từ lần hai chỉ còn chi phí walk + stat.
_MDINDEX_CACHE = {}   # str(broot) -> { rel: {"mtime","size","entry"} }
_MDINDEX_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".obsidian", ".trash",
                      ".venv", ".pytest_cache", ".claude", ".agents"}
_MDINDEX_CAP = 20000


from typing import List as _List, Optional as _Optional


def _mdindex_collect(broot: Path, prefixes):
    """Quét (tăng dần) chỉ mục note .md của MỘT brain. Trả (files, etag). Dùng chung cho
    endpoint /files/mdindex lẫn prewarm lúc khởi động (để lượt mở dashboard đầu tiên
    không phải trả giá parse cả vault)."""
    cache = _MDINDEX_CACHE.setdefault(str(broot), {})
    bases = []
    if prefixes:
        for pre in prefixes:
            cand = (broot / pre).resolve()
            if (cand == broot or broot in cand.parents) and cand.is_dir():
                bases.append(cand)
        if not bases:
            return [], "empty"
    else:
        bases = [broot]
    seen = {}                       # rel -> (mtime, size), cũng là dedupe khi base lồng nhau
    for base in bases:
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [dn for dn in dirnames
                           if not dn.startswith(".") and dn not in _MDINDEX_SKIP_DIRS]
            for fn in filenames:
                if not fn.lower().endswith(".md") or len(seen) >= _MDINDEX_CAP:
                    continue
                p = Path(dirpath) / fn
                try:
                    st = p.stat()
                except OSError:
                    continue
                if st.st_size > 1_000_000:
                    continue
                rel = str(p.relative_to(broot)).replace("\\", "/")
                seen[rel] = (st.st_mtime, st.st_size)
    etag = '"' + hashlib.md5(
        ("|".join(sorted(prefixes)) + "\n" +
         "\n".join(sorted(r + "\x00" + repr(ms) for r, ms in seen.items()))
         ).encode("utf-8", "ignore")).hexdigest() + '"'
    out = []
    for rel in sorted(seen):
        mtime, size = seen[rel]
        c = cache.get(rel)
        if c is None or c["mtime"] != mtime or c["size"] != size:
            try:
                txt = (broot / rel).read_text(encoding="utf-8", errors="ignore")
            except (OSError, ValueError):
                continue
            fm, tags, tasks = _scan_note_md(txt)
            c = {"mtime": mtime, "size": size,
                 "entry": {"path": rel, "name": rel.rsplit("/", 1)[-1],
                           "folder": rel.rsplit("/", 1)[0] if "/" in rel else "",
                           "mtime": mtime, "fm": fm, "tags": tags, "tasks": tasks}}
            cache[rel] = c
        out.append(c["entry"])
    if not prefixes:                # walk toàn brain mới biết chắc file nào đã xoá
        for rel in [r for r in cache if r not in seen]:
            cache.pop(rel, None)
    return out, etag


@app.get("/files/mdindex")
async def files_mdindex(brain: str = Query("brain"),
                        path: _Optional[_List[str]] = Query(None),
                        if_none_match: _Optional[str] = Header(None)):
    """Chỉ mục note .md trong GỐC BRAIN cho khối ```dataview trên dashboard. `path` =
    tiền tố thư mục (tương đối gốc brain) để thu hẹp phạm vi quét, truyền được NHIỀU
    lần (?path=A&path=B) - dataview.js tự suy từ mệnh đề FROM. Trả kèm `etag` (đặt cả
    header ETag); client gửi lại qua If-None-Match, không có gì đổi thì nhận 304 rỗng
    thay vì cả cục JSON. Client tự lọc/sắp xếp trên chỉ mục."""
    from starlette.concurrency import run_in_threadpool
    broot = Path(_brain_root(brain)).resolve()
    root = _files_root(brain)
    if path is None:
        prefixes = []
    elif isinstance(path, str):
        prefixes = [path]
    else:
        prefixes = list(path)
    prefixes = [p.strip().replace("\\", "/").strip("/") for p in prefixes if p and p.strip("/ ")]

    files, etag = await run_in_threadpool(_mdindex_collect, broot, prefixes)
    if if_none_match and if_none_match == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return JSONResponse({"home": _files_rel(root, broot), "files": files, "etag": etag,
                         "capped": len(files) >= _MDINDEX_CAP},
                        headers={"ETag": etag})


@app.on_event("startup")
async def _prewarm_mdindex():
    """Hâm nóng chỉ mục dataview cho MỌI brain ngay sau khi boot (thread nền, không chặn
    startup): lượt mở dashboard/note đầu tiên khỏi phải ngồi chờ parse cả vault."""
    import threading

    def _warm():
        try:
            base = Path(BRAINS_DIR)
            if not base.is_dir():
                return
            for p in sorted(base.iterdir()):
                if p.is_dir() and not p.name.startswith("."):
                    try:
                        _mdindex_collect(p.resolve(), [])
                    except Exception as e:
                        print(f"[mdindex prewarm] {p.name}: {e}", file=__import__('sys').stderr)
        except Exception as e:
            print(f"[mdindex prewarm] {e}", file=__import__('sys').stderr)

    threading.Thread(target=_warm, daemon=True, name="mdindex-prewarm").start()


@app.post("/files/taskadd")
async def files_taskadd(brain: str = Form("brain"), text: str = Form(...),
                        due: str = Form(""), path: str = Form("")):
    """Thêm MỘT dòng task "- [ ] ..." vào cuối file (nút "+ Việc" trên khối dataview/tasks).
    `path` bỏ trống thì rơi về hộp thư việc mặc định: "<thư mục Dashboard>/Task Inbox.md"
    (tự tạo nếu chưa có). `due` dạng YYYY-MM-DD thì gắn "📅 due" kiểu obsidian-tasks."""
    text = " ".join((text or "").split())
    if not text:
        return JSONResponse({"error": "Nội dung việc trống"}, status_code=400)
    broot = Path(_brain_root(brain)).resolve()
    rel = (path or "").strip().replace("\\", "/").strip("/")
    if rel:
        target = (broot / rel).resolve()
        if target != broot and broot not in target.parents:
            return JSONResponse({"error": "Đường dẫn ngoài phạm vi cho phép"}, status_code=400)
        if target.suffix.lower() not in (".md", ".txt"):
            return JSONResponse({"error": "Chỉ thêm task vào file .md/.txt"}, status_code=400)
    else:
        dash = _resolve_subfolder(str(broot), r"^(\d+\s*[-_.]\s*)?dashboard$", "00 - Dashboard")
        target = Path(dash) / "Task Inbox.md"
    line = "- [ ] " + text
    if re.match(r"^\d{4}-\d{2}-\d{2}$", (due or "").strip()) and "📅" not in text:
        line += " 📅 " + due.strip()
    try:
        if target.exists():
            old = target.read_text(encoding="utf-8")
            body = old.rstrip("\n") + ("\n" if old.strip() else "") + line + "\n"
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            body = "# Task Inbox\n\nViệc thêm nhanh từ dashboard - kéo về đúng sổ khi rảnh.\n\n" + line + "\n"
        _atomic_write_text(target, body)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    rel_out = str(target.relative_to(broot)).replace("\\", "/")
    return {"ok": True, "path": rel_out, "line": len(body.split("\n")) - 1, "raw": line}


@app.post("/files/taskcheck")
async def files_taskcheck(brain: str = Form("brain"), path: str = Form(...),
                          line: int = Form(...), checked: int = Form(...),
                          expect: str = Form("")):
    """Tick/untick MỘT dòng task trong file: lật "[ ]" <-> "[x]" rồi lưu ngay. Rào an
    toàn: dòng đích phải đúng là dòng task và khớp `expect`; file đã đổi thì tìm lại
    dòng theo nội dung, không thấy DUY NHẤT thì trả 409 để client tải lại. Task kiểu
    obsidian-tasks (có 📅/⏳/🛫/🔁) khi tick xong tự gắn "✅ YYYY-MM-DD", untick thì gỡ
    - giống plugin Tasks; checklist thường thì giữ nguyên chữ."""
    try:
        f = _safe_serve_path(brain, path)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if not f.is_file() or f.suffix.lower() not in (".md", ".txt"):
        return JSONResponse({"error": "Không tìm thấy file task"}, status_code=404)
    try:
        text = f.read_text(encoding="utf-8")
    except Exception:
        return JSONResponse({"error": "Không đọc được file"}, status_code=415)
    lines = text.split("\n")
    exp = (expect or "").strip()
    idx = None
    if 1 <= line <= len(lines) and _MD_TASK_RE.match(lines[line - 1]) and \
            (not exp or lines[line - 1].strip() == exp):
        idx = line - 1
    elif exp:
        hits = [i for i, ln in enumerate(lines) if _MD_TASK_RE.match(ln) and ln.strip() == exp]
        if len(hits) == 1:
            idx = hits[0]
    if idx is None:
        return JSONResponse({"error": "File đã thay đổi - tải lại rồi tick lại giúp nhé"},
                            status_code=409)
    m = _MD_TASK_RE.match(lines[idx])
    want = bool(int(checked))
    cr = "\r" if lines[idx].endswith("\r") else ""
    body = m.group(4).rstrip("\r")
    if want:
        if re.search(r"[📅⏳🛫🔁]", body) and "✅" not in body:
            body = body.rstrip() + " ✅ " + _today()
    else:
        body = re.sub(r"\s*✅\s*\d{4}-\d{2}-\d{2}", "", body).rstrip()
    lines[idx] = m.group(1) + m.group(2) + " [" + ("x" if want else " ") + "] " + body + cr
    _atomic_write_text(f, "\n".join(lines))
    return {"ok": True, "line": idx + 1, "raw": lines[idx].rstrip("\r"), "checked": want}


# ---- Workflows ----
def workflows_index(brain: str) -> list:
    """Danh sách workflow của một brain. Lõi thuần, dùng chung cho GET /workflows và Telegram."""
    out = []
    for f in sorted(_workflows_dir(brain).glob("*.md")):
        meta, _ = _read_md(f)
        out.append({"slug": f.stem, "name": meta.get("name", f.stem),
                    "status": meta.get("status", "off"),
                    "description": meta.get("description", ""),
                    "steps": meta.get("steps", []) or []})
    return out

def _get_workflow_canary(brain):
    """Dựng mới theo TỪNG brain.

    KHÔNG được cache toàn cục: graph_loader đóng gói `brain`, nên một instance dùng
    chung sẽ nạp workflow con của brain khác - đúng kiểu rò rỉ xuyên brain mà spec
    bắt phải chặn. Object này thuần tham chiếu, không I/O, nên dựng mới là miễn phí.
    """
    return workflow_runtime.WorkflowCanary(
        _CONTEXT_RUNTIME, cfgmod.read_settings,
        graph_loader=lambda slug: load_workflow_graph(brain, slug),
    )


def workflow_manifests(brain: str) -> list[dict]:
    """WorkflowSource của Phase 10: manifest + hợp đồng, KHÔNG kèm thân prompt của node.

    Workflow hỏng định nghĩa thì bỏ qua đúng workflow đó, không làm hỏng cả nguồn.
    """
    out = []
    root = _workflows_dir(brain)
    for f in sorted(root.glob("*.md")):
        try:
            meta, _ = _read_md(f)
            graph = workflow_graph.compile_workflow(meta, f.stem)
        except (workflow_graph.WorkflowContractError, Exception):
            continue
        out.append(workflow_graph.manifest_of(graph, relative_path=f.name))
    return out


def load_workflow_graph(brain: str, slug: str):
    """Đọc một workflow thành đồ thị đã kiểm tra hợp lệ; None nếu thiếu hoặc sai."""
    path = _workflows_dir(brain) / f"{slug}.md"
    if not path.exists():
        return None
    try:
        meta, _ = _read_md(path)
        return workflow_graph.compile_workflow(meta, slug)
    except Exception:
        return None


@app.get("/workflows")
async def list_workflows(brain: str = Query("brain")):
    return {"workflows": workflows_index(brain)}

@app.post("/workflows")
async def save_workflow(name: str = Form(...), description: str = Form(""), steps: str = Form("[]"),
                        status: str = Form("active"), slug: str = Form(""), brain: str = Form("brain")):
    slug = slug or _slugify(name)
    try:
        steps_list = json.loads(steps)
    except Exception:
        steps_list = []
    meta = {"type": "workflow", "name": name, "slug": slug, "status": status,
            "description": description, "steps": steps_list, "updated": _today()}
    _write_md(_workflows_dir(brain) / f"{slug}.md", meta, description)
    return {"ok": True, "slug": slug}

@app.post("/workflows/toggle")
async def toggle_workflow(slug: str = Form(...), brain: str = Form("brain")):
    f = _workflows_dir(brain) / f"{slug}.md"
    if not f.exists():
        return {"ok": False, "error": "not found"}
    meta, body = _read_md(f)
    meta["status"] = "off" if meta.get("status") == "active" else "active"
    _write_md(f, meta, body)
    return {"ok": True, "status": meta["status"]}

@app.post("/workflows/delete")
async def delete_workflow(slug: str = Form(...), brain: str = Form("brain")):
    f = _workflows_dir(brain) / f"{slug}.md"
    if f.exists():
        f.unlink()
    return {"ok": True}

# ---- Xuất / Nhập năng lực (chia sẻ agent/skill/workflow qua file .zip) ----
def _app_version() -> str:
    try:
        return (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return ""


@app.get("/export")
async def export_capability(kind: str = Query(...), slug: str = Query(...),
                            brain: str = Query("brain"), deps: int = Query(1)):
    """Xuất agent/skill/workflow (kèm phụ thuộc nếu deps=1) thành gói .zip để tải về, chia sẻ.

    `slug` nhận MỘT slug hoặc NHIỀU slug cách nhau bằng dấu phẩy (chọn nhiều / chọn tất
    cả trên trang Studio, 16/08) - nhiều cái vẫn ra một gói duy nhất, nhập lại một phát."""
    if kind not in ("agent", "skill", "workflow"):
        return JSONResponse({"error": "kind phải là agent/skill/workflow"}, status_code=400)
    slugs = [s.strip() for s in str(slug or "").split(",") if s.strip()]
    if not slugs or len(slugs) > 200:
        return JSONResponse({"error": "slug rỗng hoặc quá nhiều (tối đa 200)"}, status_code=400)
    xau = [s for s in slugs if not skill_router.valid_slug(s)]
    if xau:
        return JSONResponse({"error": f"slug không hợp lệ: {', '.join(xau[:5])}"}, status_code=400)
    data, fname = share_bundle.build_bundle(
        kind, slugs if len(slugs) > 1 else slugs[0],
        agents_dir=_agents_dir(brain), workflows_dir=_workflows_dir(brain),
        skills_root=_skills_dir(brain), include_deps=bool(deps),
        system_slugs=system_sync.system_skill_slugs(), app_version=_app_version())
    if not data:
        return JSONResponse({"error": f"Không tìm thấy {kind} '{slug}' để xuất"}, status_code=404)
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.post("/import")
async def import_capability(file: UploadFile = File(...), brain: str = Form("brain"),
                            overwrite: str = Form("0")):
    """Nhập gói .zip (hoặc file .md lẻ cho agent/workflow) vào brain. Trùng slug thì bỏ qua trừ khi
    tick ghi đè. Có rào chống zip-slip + giới hạn dung lượng ở share_bundle."""
    data = await file.read()
    if not data:
        return JSONResponse({"error": "File rỗng"}, status_code=400)
    if len(data) > 25 * 1024 * 1024:
        return JSONResponse({"error": "File quá lớn (>25MB)"}, status_code=413)
    root = _brain_root(brain)
    res = share_bundle.import_bundle(
        data, file.filename,
        agents_dir=_agents_dir(brain), workflows_dir=_workflows_dir(brain),
        skills_root=_skills_dir(brain),
        overwrite=(overwrite in ("1", "true", "True", "on")))
    if any(str(k).startswith("skill:") for k in res.get("imported", [])):
        try:
            system_sync.mirror_skills(root)   # skill mới → mirror sang .claude cho Claude native
        except Exception:
            pass
    try:
        rebuild_javis_index(root)
    except Exception:
        pass
    return {"ok": not res.get("errors"), **res}


@app.get("/usage")
async def usage_stats():
    """Token/chi phí Javis TỰ ĐO theo nhà cung cấp (hôm nay + tổng). Kèm số dư THẬT của OpenRouter
    nếu có key (provider duy nhất lộ số dư qua API); các provider còn lại API không cho lấy hạn mức."""
    out = usage_store.summary()
    out["daily"] = usage_store.daily(14)   # chuỗi 14 ngày cho đồ thị trang Mức dùng
    try:
        out["openrouter"] = await _openrouter_credits(cfgmod.read_settings().get("model", {}) or {})
    except Exception:
        out["openrouter"] = None
    return out


async def _openrouter_credits(mcfg: dict):
    """Số dư THẬT của OpenRouter, hoặc None. Provider duy nhất lộ số dư qua API.

    Tách ra làm hàm riêng vì cả `/usage` lẫn `/usage/tong-quan` đều cần: đây là con số tiền
    mặt duy nhất trên cả trang không phải ước lượng từ bảng giá.
    """
    key = (mcfg or {}).get("openrouter_key")
    if not key:
        return None
    import httpx
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get("https://openrouter.ai/api/v1/credits",
                             headers={"Authorization": f"Bearer {key}"})
    if r.status_code != 200:
        return None
    d = (r.json() or {}).get("data") or {}
    tc, tu = d.get("total_credits"), d.get("total_usage")
    if tc is None or tu is None:
        return None
    return {"total": round(float(tc), 4), "used": round(float(tu), 4),
            "remaining": round(float(tc) - float(tu), 4)}


# ---- Dashboard Token (index log thô Claude + Codex + nhánh API) -----------------------
# Một khoá cho MỌI lượt quét. refresh() xoá sạch dòng cũ của từng file rồi chèn lại, nên hai
# lượt quét chạy chồng nhau là chèn trùng - và trang báo gấp đôi số token. Mở hai tab, hay
# một tab gọi cả /usage/summary lẫn /usage/tong-quan song song, là đủ để dính.
_USAGE_REFRESH_LOCK = asyncio.Lock()


async def _usage_refresh_once() -> dict:
    """Quét tăng dần, tuần tự hoá. Lỗi thì nuốt: số liệu cũ vẫn hơn một trang lỗi."""
    try:
        async with _USAGE_REFRESH_LOCK:
            return await asyncio.to_thread(usage_index.refresh)
    except Exception:  # noqa: BLE001
        return {}


@app.get("/usage/summary")
async def usage_summary(period: str = "this_month", provider: str = "", project: str = "", refresh: int = 1):
    """Báo cáo token theo kỳ: KPI + breakdown + timeseries, kèm so kỳ trước. refresh=1 (mặc
    định) quét tăng dần trước khi trả (rẻ khi index đã ấm)."""
    if refresh:
        await _usage_refresh_once()
    try:
        # to_thread như refresh ngay trên: summary() truy vấn sqlite, đo được 46,7ms. Chạy
        # thẳng trên event loop là chặn MỌI request khác, kể cả healthcheck 4 giây của Docker.
        return await asyncio.to_thread(
            usage_index.summary, period=period, provider=provider or None, project=project or None)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/usage/insights")
async def usage_insights(period: str = "this_month", refresh: int = 0):
    """Danh sách đề xuất hành động cho kỳ. Mặc định KHÔNG refresh (UI đã refresh ở /usage/summary)."""
    if refresh:
        await _usage_refresh_once()
    try:
        return {"items": await asyncio.to_thread(usage_index.insights, period=period)}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/usage/refresh")
async def usage_refresh():
    """Quét tăng dần 3 nguồn, trả số file/event xử lý lần này."""
    return await _usage_refresh_once()


# ---- Trang Mức dùng: khối trả lời "tôi tốn bao nhiêu, và có đáng không" ---------------
# Chi phí cố định mỗi lượt của từng mức tiết kiệm. Đo bằng prompt THẬT nên tốn ~20ms cộng một
# vòng quét kho tool - rẻ với một lần mở trang, nhưng vòng lặp nền hỏi mỗi 10 phút thì không.
# Nhớ đệm theo brain, hết hạn sau 10 phút để brain to dần lên thì con số cũng đi theo.
_PHI_MUC_CACHE: dict = {}
_PHI_MUC_TTL = 600.0


async def _phi_moi_muc(brain: str = "brain") -> dict:
    """{muc_id: token_co_dinh_moi_luot}. Rỗng nếu chưa đo được (đừng bịa)."""
    khoa = str(brain or "brain")
    o = _PHI_MUC_CACHE.get(khoa)
    if o and time.time() - o[0] < _PHI_MUC_TTL:
        return o[1]
    try:
        uoc = await _uoc_tinh_tiet_kiem(khoa)
    except Exception:  # noqa: BLE001 - phần thông tin, không được làm sập trang
        return (o[1] if o else {})
    phi = {k: int((v or {}).get("token_moi_request") or 0)
           for k, v in ((uoc or {}).get("muc") or {}).items()}
    _PHI_MUC_CACHE[khoa] = (time.time(), phi)
    return phi


def _tien_cache(by_model: list, prices: dict) -> float:
    """Nhờ cache, đã KHÔNG phải trả bao nhiêu USD.

    Token đọc lại từ cache vẫn bị tính tiền, nhưng rẻ hơn token vào bình thường nhiều lần.
    Phần chênh đó là tiền thật không phải trả. Tính theo ĐÚNG bảng giá của từng model rồi
    cộng lại, chứ không lấy một giá bình quân - opus và haiku chênh nhau gần 20 lần.

    Đây là cách nói lại "cache hit 80%" bằng đơn vị người ta quan tâm. Phần trăm là ngôn ngữ
    của người viết code; tiền là ngôn ngữ của người trả tiền.
    """
    tong = 0.0
    for x in by_model or []:
        cr = int(x.get("cache_read") or 0)
        if cr <= 0:
            continue
        khoa = up_parsers._khoa_gia(str(x.get("key") or ""), prices)
        if not khoa:
            continue
        p = prices[khoa]
        chenh = max(0.0, float(p.get("in") or 0) - float(p.get("cache_read") or 0))
        tong += cr * chenh / 1_000_000.0
    return round(tong, 4)


def _cau_mo_dau(d: dict) -> str:
    """Một câu tiếng người tóm tắt cả trang. Không bảng, không phần trăm trần trụi.

    Vì sao câu này đáng có: sáu ô số ngang hàng nhau bắt người đọc tự ghép nghĩa, và con số
    to nhất trên trang ("chi phí quy đổi") lại là con số KHÔNG phải tiền thật - đọc lướt thì
    y như một hoá đơn. Một câu nói thẳng ai trả gì cho cái gì thì không đọc nhầm được.
    """
    t = d.get("tien") or {}
    goi = t.get("goi") or {}
    that = float((t.get("that") or {}).get("usd") or 0)
    quy = float((t.get("quy_doi") or {}).get("usd") or 0)
    ky = d.get("ten_ky") or "Kỳ này"
    ve = []
    if goi.get("so_duoc"):
        lan = goi.get("roi_lan") or 0
        # Nói đủ cả ba ca. Chỉ khoe khi thật sự lời, và dám nói khi gói đang đắt hơn API -
        # một trang chỉ biết khen thì lần sau không ai tin nó nữa.
        if lan >= 1.2:
            ket = f", tức gói đang lời {lan:g} lần."
        elif lan >= 0.8:
            ket = ", tức gói đang hoà vốn so với giá API."
        elif lan > 0:
            ket = ", tức với nhịp dùng này thì gói đang đắt hơn trả theo API."
        else:
            ket = "."
        ve.append(f"{ky} bạn trả ${goi['gia_thang_usd']:g} tiền gói, "
                  f"lượng việc đã chạy nếu tính theo giá API đáng ${quy:,.0f}" + ket)
    elif quy > 0:
        ve.append(f"{ky} lượng việc đã chạy quy theo giá API là khoảng ${quy:,.2f}.")
    if that > 0:
        ve.append(f"Tiền mặt thật đã tiêu: ${that:,.2f}.")
    else:
        ve.append("Chưa có nhánh nào tính tiền theo token, nên tiền mặt thật là $0.")
    tk = d.get("tiet_kiem") or {}
    if tk.get("token"):
        ve.append(f"Chế độ tiết kiệm đã tránh được {_fmt_tok_vn(tk['token'])} token.")
    return " ".join(ve)


def _fmt_tok_vn(n) -> str:
    n = int(n or 0)
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f} tỉ"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} triệu"
    if n >= 1_000:
        return f"{n / 1_000:.0f} nghìn"
    return str(n)


_TEN_KY = {"today": "Hôm nay", "yesterday": "Hôm qua", "this_week": "Tuần này",
           "last_week": "Tuần trước", "this_month": "Tháng này", "last_month": "Tháng trước",
           "last_3_months": "3 tháng qua", "this_year": "Năm nay"}


@app.get("/usage/tong-quan")
async def usage_tong_quan(period: str = "this_month", brain: str = "brain", refresh: int = 0):
    """Khối ĐẦU trang Mức dùng: tiền thật vs tiền quy đổi, trần gói, tiết kiệm, dự báo.

    Tách khỏi `/usage/summary` có chủ ý. Endpoint kia là số liệu thô theo chiều (model, dự
    án, provider) - đúng thứ cần khi đã biết mình muốn soi gì. Còn đây trả lời ba câu hỏi
    người ta mở trang ra để hỏi: tháng này tốn bao nhiêu tiền THẬT, gói có đáng tiền không,
    và sắp chạm trần chưa. Trộn hai thứ vào một endpoint thì mỗi lần đổi chip kỳ lại kéo theo
    một vòng đo prompt và hai truy vấn cửa sổ trượt.
    """
    if refresh:
        await _usage_refresh_once()
    try:
        s = await asyncio.to_thread(usage_index.summary, period=period)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    k = s.get("kpi") or {}
    mcfg = cfgmod.read_settings().get("model", {}) or {}
    prices = up_parsers.load_prices()

    # --- Tiền: TÁCH BẠCH tiền mặt và tiền quy đổi. Đây là chỗ dễ nói dối nhất của cả trang.
    # Nhánh API key thì mỗi token là tiền mặt ra khỏi ví. Gói thuê bao thì đã trả trọn gói,
    # token không sinh thêm hoá đơn nào - con số quy đổi chỉ để biết gói có đáng tiền không.
    theo_prov = {x["key"]: x for x in (s.get("by_provider") or [])}
    tien_that = round(float((theo_prov.get("api") or {}).get("cost") or 0), 4)
    tien_quy_doi = round(sum(float(v.get("cost") or 0)
                             for kk, v in theo_prov.items() if kk != "api"), 2)
    # Gia goi la tien MOT THANG, nen chi so sanh duoc voi so lieu CUA MOT THANG. Bam chip
    # "Hom nay" roi lay chi phi mot ngay chia cho tien goi ca thang thi ra "goi dang lo 10
    # lan" - va do la dong chu to nhat tren trang, doc dau tien. Ky khong phai thang thi
    # khong so, chu khong so bua.
    gia_goi = float(mcfg.get("gia_goi_thang_usd") or 0)
    ky_thang = period in ("this_month", "last_month")
    goi = {"gia_thang_usd": gia_goi, "so_duoc": bool(gia_goi > 0 and ky_thang),
           "roi_lan": round(tien_quy_doi / gia_goi, 1) if (gia_goi > 0 and ky_thang) else 0}

    orb = None
    try:
        orb = await _openrouter_credits(mcfg)
    except Exception:  # noqa: BLE001
        orb = None

    # --- Cửa sổ trượt 5 giờ. Nhà cung cấp gói tính hạn mức theo cửa sổ vài giờ chứ không
    # theo ngày, nên "hôm nay dùng bao nhiêu" không trả lời được câu "tôi sắp bị chặn chưa".
    try:
        cs5 = await asyncio.to_thread(usage_index.cua_so, 5.0)
        dinh5 = await asyncio.to_thread(usage_index.dinh_cua_so, 5.0)
    except Exception:  # noqa: BLE001
        cs5, dinh5 = {}, {}
    tran_5h = int(mcfg.get("tran_5h") or 0)
    # Chưa khai trần thì so với ĐỈNH của chính người dùng: mức cao nhất từng chạm mà chưa bị
    # chặn là một cận dưới THẬT của hạn mức, và nó riêng cho từng tài khoản. Kém chính xác
    # hơn một con số chính thức, nhưng có thật - hơn hẳn việc bịa một hạn mức mặc định.
    moc_so = tran_5h or int(dinh5.get("tokens") or 0)
    cua_so = {**cs5, "dinh": int(dinh5.get("tokens") or 0), "dinh_luc": dinh5.get("hour") or "",
              "tran_khai": tran_5h,
              "moc_so_sanh": moc_so,
              "ty_le": round(int(cs5.get("tokens") or 0) / moc_so, 4) if moc_so > 0 else 0}

    # --- Tiết kiệm: đối chứng ngược, chạy được cho MỌI kỳ (xem usage_saving).
    phi = await _phi_moi_muc(brain)
    muc_nay = current_preset(cfgmod.read_settings().get("context_runtime") or {})
    gia_1m, nguon_gia = _gia_input_1m(_ten_model_chinh(mcfg), mcfg)
    luot_javis = await asyncio.to_thread(usage_index.luot_theo_ngay, period)
    tk = usage_saving.tiet_kiem(luot_javis, phi, muc_nay, gia_1m_usd=gia_1m)
    tk["nguon_gia"] = nguon_gia
    tk["nhan_muc"] = (RUNTIME_PRESETS.get(muc_nay) or {}).get("nhan") or muc_nay

    # --- Ngân sách + dự báo
    # Tran tien la tran THANG. Doi chieu no voi chi phi cua ky dang chon la so mot ngay voi
    # tran mot thang: bam chip "Hom nay" thi o ngan sach bao "con nguyen 30$" du thang nay da
    # tieu het. Nen o nay LUON doc so cua thang, khong theo chip.
    tien_that_thang = await _tien_that_thang()
    db = usage_saving.du_bao(k.get("tokens") or 0, tien_that,
                             (s.get("range") or ["", ""])[0], (s.get("range") or ["", ""])[1],
                             period)
    du_bao_thang = float(db.get("cost") or 0) if (period == "this_month" and db.get("co")) else 0.0
    ns = usage_saving.ngan_sach(tien_that_thang, float(mcfg.get("ngan_sach_thang_usd") or 0),
                                du_bao_thang)
    ns["tu_phanh"] = bool(mcfg.get("tu_phanh"))
    ns["dang_phanh"] = usage_saving.dang_phanh()

    usd_cache = _tien_cache(s.get("by_model") or [], prices)
    d = {
        "period": period, "ten_ky": _TEN_KY.get(period, "Kỳ này"), "range": s.get("range"),
        "engine": _engine_runtime_view(cfgmod.read_settings().get("context_runtime") or {}),
        "tien": {
            "that": {"usd": tien_that, "usd_thang": tien_that_thang, "openrouter": orb},
            "quy_doi": {"usd": tien_quy_doi},
            "goi": goi,
        },
        "ngan_sach": ns,
        "tiet_kiem": tk,
        "cua_so": cua_so,
        "cache": {"ty_le": k.get("cache_hit") or 0, "token": k.get("cache_read") or 0,
                  "usd": usd_cache},
        "du_bao": db,
        "luot": {"so_luot": k.get("turns") or 0, "moi_luot": k.get("avg_per_turn") or 0},
        "nhip_engine": await asyncio.to_thread(usage_index.nhip_engine, period),
        "bao_cao_tuan": mcfg.get("bao_cao_tuan") or "",
        "moc": usage_saving.doc_moc((s.get("range") or ["", ""])[0],
                                    (s.get("range") or ["", ""])[1]),
    }
    d["cau"] = _cau_mo_dau(d)
    return d


@app.post("/usage/ngan-sach")
async def usage_ngan_sach(gia_goi_thang_usd: str = Form(""), ngan_sach_thang_usd: str = Form(""),
                          tran_5h: str = Form(""), tu_phanh: str = Form(""),
                          bao_cao_tuan: str = Form("")):
    """Bốn con số Javis KHÔNG tự biết được: giá gói, trần tiền tháng, trần cửa sổ 5h, tự phanh.

    Trường bỏ trống = giữ nguyên. Gửi "0" mới là xoá. Phân biệt hai cái đó quan trọng: giao
    diện chỉ gửi ô người dùng vừa sửa, gửi thiếu mà bị hiểu là 0 thì bấm lưu một ô là mất ba
    ô kia.
    """
    cfg = cfgmod.read_settings()
    m = cfg.setdefault("model", {})
    truoc = float(m.get("ngan_sach_thang_usd") or 0)

    def _chu(x) -> str:
        # Gọi thẳng hàm endpoint (test, hoặc code khác trong server) thì tham số mặc định vẫn
        # là object Form(...) chứ không phải chuỗi. Không chặn ở đây là ghi nguyên cái repr
        # của nó vào settings.json.
        return x.strip() if isinstance(x, str) else ""

    def _so(raw, cu, kieu=float):
        raw = _chu(raw).replace(",", "")
        if not raw:
            return cu
        try:
            return max(kieu(0), kieu(float(raw)))
        except (TypeError, ValueError):
            return cu

    m["gia_goi_thang_usd"] = _so(gia_goi_thang_usd, float(m.get("gia_goi_thang_usd") or 0))
    m["ngan_sach_thang_usd"] = _so(ngan_sach_thang_usd, float(m.get("ngan_sach_thang_usd") or 0))
    m["tran_5h"] = _so(tran_5h, int(m.get("tran_5h") or 0), int)
    if _chu(tu_phanh):
        m["tu_phanh"] = _chu(tu_phanh).lower() in ("1", "true", "on", "yes", "co", "có")
    if _chu(bao_cao_tuan):
        v = _chu(bao_cao_tuan)
        m["bao_cao_tuan"] = "" if v.lower() in ("0", "off", "tat", "tắt", "khong", "không") else v
    cfgmod.write_settings(cfg)
    if m["ngan_sach_thang_usd"] != truoc:
        usage_saving.ghi_moc("ngan_sach", f"${m['ngan_sach_thang_usd']:g}", f"${truoc:g}",
                             "Đổi trần tiền tháng")

    # ĐỦ ĐIỀU KIỆN MỚI HẸN LỊCH. Hai thứ vừa bật đều hẹn giờ báo về cho người dùng: cảnh báo
    # ngân sách và báo cáo tuần. Chưa đấu kênh nào thì tới giờ chúng chạy xong rồi rơi vào hư
    # không, và người dùng tưởng Javis quên. Không chặn (họ có thể sắp đấu), nhưng phải NÓI.
    canh_bao = []
    san_sang, ly_do = _notify_ready()
    if not san_sang and (m.get("bao_cao_tuan") or m["ngan_sach_thang_usd"] > 0):
        canh_bao.append(ly_do or "Chưa đấu kênh báo nào (Telegram hoặc Zalo) nên báo cáo và "
                                 "cảnh báo ngân sách sẽ không tới được ai.")
    if m["ngan_sach_thang_usd"] > 0 and not m.get("tu_phanh"):
        canh_bao.append("Tự phanh đang tắt, nên chạm trần Javis chỉ nhắc chứ không dừng tiêu tiền.")

    await _kiem_ngan_sach(nhac=False)     # đặt lại phanh ngay, đừng đợi vòng lặp nền
    return {"ok": True, "gia_goi_thang_usd": m["gia_goi_thang_usd"],
            "ngan_sach_thang_usd": m["ngan_sach_thang_usd"], "tran_5h": m["tran_5h"],
            "tu_phanh": bool(m.get("tu_phanh")), "bao_cao_tuan": m.get("bao_cao_tuan") or "",
            "canh_bao": canh_bao, "dang_phanh": usage_saving.dang_phanh()}


@app.get("/usage/bao-cao")
async def usage_bao_cao(period: str = "this_week"):
    """Báo cáo token dạng CHỮ, đọc được trên Telegram/Zalo. Dùng cho bản đẩy hàng tuần."""
    return {"text": await _bao_cao_token(period)}


async def _tien_that_thang() -> float:
    """USD tiền MẶT đã tiêu tháng này (chỉ nhánh dùng API key). Lỗi -> 0, không chặn."""
    try:
        s = await asyncio.to_thread(usage_index.summary, period="this_month")
    except Exception:  # noqa: BLE001
        return 0.0
    for x in s.get("by_provider") or []:
        if x.get("key") == "api":
            return round(float(x.get("cost") or 0), 4)
    return 0.0


async def _kiem_ngan_sach(nhac: bool = True) -> dict:
    """Đối chiếu tiền mặt tháng này với trần người dùng đặt: bật/tắt phanh, và nhắc một lần.

    Gọi từ hai chỗ: vòng lặp nền (mỗi 10 phút) và ngay sau khi người dùng đổi trần. `nhac`
    tắt ở lần thứ hai vì đổi trần xong mà bị nhắn ngay một tin cảnh báo thì như bị mắng.

    Nhắc ĐÚNG MỘT LẦN mỗi mốc mỗi tháng (dấu lưu trong nhật ký mốc). Nhắc lại mỗi 10 phút
    suốt nửa tháng cuối là cách nhanh nhất để người ta tắt thông báo, và tắt rồi thì lần
    sau thật sự vượt trần cũng không ai biết.
    """
    mcfg = cfgmod.read_settings().get("model", {}) or {}
    tran = float(mcfg.get("ngan_sach_thang_usd") or 0)
    if tran <= 0:
        usage_saving.dat_phanh(False, "")
        return {"co": False}
    da = await _tien_that_thang()
    ns = usage_saving.ngan_sach(da, tran)
    bat_phanh = bool(mcfg.get("tu_phanh")) and ns.get("muc_do") == "het"
    usage_saving.dat_phanh(bat_phanh,
                           f"đã tiêu ${da:.2f} trên trần ${tran:.2f} tháng này" if bat_phanh else "")
    if nhac and ns.get("muc_do") in ("sap_het", "het"):
        khoa = f"{ns['muc_do']}"
        if not usage_saving.da_nhac_chua(khoa):
            usage_saving.ghi_moc("ngan_sach", khoa, "", f"Nhắc ngân sách: {khoa}")
            if ns["muc_do"] == "het":
                tin = (f"Ngân sách API tháng này đã hết: tiêu ${da:.2f} trên trần ${tran:.2f}.\n"
                       + ("Javis đã tự chuyển việc nền sang đường không tốn tiền."
                          if bat_phanh else
                          "Tự phanh đang tắt nên việc nền vẫn tiêu tiền như thường."))
            else:
                tin = (f"Ngân sách API tháng này đã dùng {ns['ty_le'] * 100:.0f}%: "
                       f"${da:.2f} trên trần ${tran:.2f}. Còn ${ns['con']:.2f}.")
            try:
                await _notify_owner("", tin)
            except Exception:  # noqa: BLE001 - không gửi được thì thôi, đừng làm hỏng vòng lặp
                pass
    return ns


_NGAN_SACH_LAST = [0.0]        # mốc lần kiểm ngân sách gần nhất (nhịp riêng 10 phút)


async def _bao_cao_tuan_neu_toi_gio() -> bool:
    """Sáng thứ Hai thì đẩy báo cáo token tuần trước về đúng người. Tắt mặc định.

    Vì sao đẩy chứ không đợi người ta mở trang: trang Mức dùng chỉ hữu ích khi có người nhớ
    mở nó ra, mà thứ người ta cần biết ("tuần rồi tiêu gấp đôi vì một cái loop") lại đúng là
    thứ không ai nghĩ tới việc đi kiểm. Javis đã có sẵn đường nhắn chủ động, dùng nó.

    Dấu đã-gửi lưu trong nhật ký mốc theo tuần ISO, nên máy khởi động lại giữa sáng thứ Hai
    cũng không gửi hai lần.
    """
    from datetime import datetime, timedelta, timezone
    mcfg = cfgmod.read_settings().get("model", {}) or {}
    dich = str(mcfg.get("bao_cao_tuan") or "").strip()
    if not dich:
        return False
    gio = localefmt.now()
    if gio.weekday() != 0 or gio.hour < 8:
        return False
    tuan = f"tuan-{gio.isocalendar()[0]}-{gio.isocalendar()[1]}"
    if usage_saving.da_nhac_chua(tuan, gio):
        return False
    usage_saving.ghi_moc("ngan_sach", tuan, "", "Đã gửi báo cáo token tuần")
    try:
        await _notify_owner("" if dich == "auto" else dich, await _bao_cao_token("last_week"))
    except Exception as e:  # noqa: BLE001 - gửi hỏng thì thôi, đừng giết vòng lặp nền
        print(f"[bao cao tuan] {type(e).__name__}: {e}", file=sys.stderr)
    return True


async def _bao_cao_token(period: str = "this_week") -> str:
    """Báo cáo token bằng VĂN NÓI, cho kênh chữ thuần (Telegram/Zalo).

    Không bảng, không markdown nặng: kênh nhận là chỗ chữ chạy một cột. Nội dung chọn theo
    đúng thứ hành động được - tiêu bao nhiêu tiền thật, cái gì ngốn nhất, có gì bất thường -
    chứ không đổ hết mọi chiều số liệu ra.
    """
    try:
        s = await asyncio.to_thread(usage_index.summary, period=period)
    except Exception as e:  # noqa: BLE001
        return f"Chưa dựng được báo cáo token: {type(e).__name__}."
    k = s.get("kpi") or {}
    ten = _TEN_KY.get(period, "Kỳ này")
    mcfg = cfgmod.read_settings().get("model", {}) or {}
    theo_prov = {x["key"]: x for x in (s.get("by_provider") or [])}
    that = float((theo_prov.get("api") or {}).get("cost") or 0)
    quy = sum(float(v.get("cost") or 0) for kk, v in theo_prov.items() if kk != "api")

    d = [f"BÁO CÁO TOKEN - {ten.lower()}",
         f"Tổng {_fmt_tok_vn(k.get('tokens'))} token qua {k.get('turns') or 0} lượt."]
    if k.get("delta_pct") is not None:
        chieu = "tăng" if k["delta_pct"] >= 0 else "giảm"
        d.append(f"So kỳ trước {chieu} {abs(k['delta_pct']):.0f}%.")
    d.append(f"Tiền mặt thật: ${that:,.2f}."
             + (f" Quy theo giá API thì phần gói thuê bao đáng ${quy:,.0f}." if quy > 0 else ""))

    tran = float(mcfg.get("ngan_sach_thang_usd") or 0)
    if tran > 0:
        da = await _tien_that_thang()
        d.append(f"Ngân sách tháng: đã dùng ${da:,.2f} trên ${tran:,.2f}.")

    phi = await _phi_moi_muc("brain")
    muc_nay = current_preset(cfgmod.read_settings().get("context_runtime") or {})
    tk = usage_saving.tiet_kiem(await asyncio.to_thread(usage_index.luot_theo_ngay, period),
                                phi, muc_nay)
    if tk.get("token"):
        d.append(f"Chế độ tiết kiệm tránh được {_fmt_tok_vn(tk['token'])} token "
                 f"({tk.get('phan_tram') or 0}% mỗi lượt).")

    top_m = (s.get("by_model") or [])[:1]
    top_p = (s.get("by_project") or [])[:1]
    if top_m:
        d.append(f"Model ngốn nhất: {top_m[0]['key']} ({_fmt_tok_vn(top_m[0]['tokens'])}).")
    if top_p:
        d.append(f"Nơi ngốn nhất: {top_p[0]['key']} ({_fmt_tok_vn(top_p[0]['tokens'])}).")
    nen = next((x["tokens"] for x in (s.get("by_activity") or []) if x["key"] == "background"), 0)
    if nen and k.get("tokens"):
        d.append(f"Việc chạy nền chiếm {nen / k['tokens'] * 100:.0f}% token.")

    try:
        cho = await asyncio.to_thread(usage_index.insights, period=period)
    except Exception:  # noqa: BLE001
        cho = []
    for i in (cho or [])[:2]:
        d.append(f"- {i.get('title')}: {i.get('detail')}")
    return "\n".join(d)


# Engine của workflow chỉ chạy được CLI (Claude hoặc Codex). Router có thể khai model
# của provider API, nhưng ở đây không với tới được, nên chỉ nhận đúng hai họ này.
# Dự trù output cho một bước workflow. Bảo thủ: thà loại một model sát trần còn hơn
# route vào rồi tràn cửa sổ giữa chừng.
_ROUTER_STEP_OUTPUT_RESERVE = 4000

_WORKFLOW_ROUTABLE_PROVIDERS = {
    "cli": "claude", "claude": "claude", "anthropic-cli": "claude",
    "codex": "codex", "openai-oauth": "codex",
}


def _route_step_model(router, prompt, agent_model, session_id):
    """Chọn model cho MỘT bước. Không route được thì giữ nguyên model của agent.

    Guard quan trọng: router có thể trỏ sang provider mà engine workflow không gọi
    được. Im lặng dùng model đó là chạy sai model so với thứ đã quyết.

    Phải truyền KÍCH THƯỚC prompt thật, nếu không bộ lọc cửa sổ context vô hiệu và
    một prompt dài vẫn lọt vào model cửa sổ nhỏ.
    """
    if router is None:
        return agent_model, ""
    # Cùng heuristic ký tự/token với phần còn lại của runtime; ước lượng bảo thủ.
    estimated = max(1, int(len(str(prompt or "")) / 3) + 1)
    try:
        decision = router.route(
            model_router.RoutingRequest(
                step_kind="model_step",
                requires=model_router.requirements_for(
                    "model_step", needs_tools=True),
                risk="none",
                estimated_input_tokens=estimated,
                reserved_output_tokens=_ROUTER_STEP_OUTPUT_RESERVE,
            ),
            session_id or "workflow",
            current_model=agent_model or "",
        )
    except Exception:
        return agent_model, ""
    if decision.action != "route":
        return agent_model, decision.reason
    family = _WORKFLOW_ROUTABLE_PROVIDERS.get(decision.provider)
    if family is None:
        return agent_model, "provider_not_reachable_from_workflow_engine"
    if family == "codex" and not _is_codex_model(decision.model):
        return agent_model, "routed_model_not_valid_for_codex"
    return decision.model, decision.reason


async def _run_workflow_step(node, prompt, mk, agent_sysprompt, sink, router=None,
                             session_id="", log_run=None, learn=None):
    """Chạy ĐÚNG một bước theo đúng ngữ nghĩa runner cũ: agent, kiểm chứng, retry.

    Dùng chung cho cả hai đường. `sink` nhận event để đường graph đẩy ra SSE y như cũ.
    `log_run(slug, task, out)`: ghi nhật ký lượt chạy vào memory/agents/<slug>/runs/.
    Trước 0.35.3 chỉ runner cũ ghi - bật canary graph là nhật ký lặng lẽ biến mất.
    """
    agent_name, sysprompt, agent_model = agent_sysprompt(node.agent)
    # Studio định vị chỗ đổ chữ bằng CHỈ SỐ bước, không phải id node. Thiếu `i` thì
    # event vẫn phát ra nhưng giao diện lặng lẽ vứt đi - người xem thấy bước chạy và
    # bước xong mà không thấy chữ nào.
    index = int((node.metadata or {}).get("legacy_index",
                (node.metadata or {}).get("declared_index", 0)) or 0)
    routed_model, route_reason = _route_step_model(router, prompt, agent_model, session_id)
    if routed_model != agent_model:
        await sink({"type": "step_model", "i": index, "node": node.id,
                    "model": routed_model, "reason": route_reason})
        agent_model = routed_model
    cur_prompt = prompt
    out = ""
    verified = None
    attempt = 0
    while True:
        gcli = mk(sysprompt, agent_model)
        out = ""
        async for ev in gcli.query(cur_prompt):
            if ev["type"] == "text":
                await sink({"type": "step_text", "i": index, "node": node.id,
                            "content": ev["content"]})
            elif ev["type"] == "tool_call":
                await sink({"type": "step_tool", "i": index, "node": node.id,
                            "tool": ev["name"]})
            elif ev["type"] == "final":
                out = ev.get("content") or out
            elif ev["type"] == "error":
                await sink({"type": "step_error", "i": index, "node": node.id,
                            "content": ev["content"]})
        if not node.verify_agent:
            break
        v_name, v_body, v_model = agent_sysprompt(node.verify_agent)
        await sink({"type": "step_verify", "i": index, "node": node.id,
                    "agent": v_name, "attempt": attempt})
        v_sys = (
            v_body + "\n\nVAI TRÒ KIỂM CHỨNG: Bạn là người ĐÁNH GIÁ độc lập. "
            "Mặc định GIẢ ĐỊNH kết quả dưới đây ĐANG SAI và phải tự chứng minh. "
            "Kiểm tra thực tế (đọc file/chạy thử nếu cần), KHÔNG chỉ đọc lướt. "
            'CHỈ trả JSON 1 dòng: {"pass":true|false,"reason":"ngắn gọn vì sao","fixes":"cần sửa gì nếu fail"}.'
        )
        v_prompt = (
            f"NHIỆM VỤ GỐC:\n{prompt}\n\n"
            f"KẾT QUẢ CẦN KIỂM CHỨNG:\n{out}\n\n"
            "Đánh giá kết quả có ĐẠT nhiệm vụ không. Trả JSON như hướng dẫn."
        )
        vcli = mk(v_sys, v_model)
        v_out = ""
        async for ev in vcli.query(v_prompt):
            if ev["type"] == "final":
                v_out = ev.get("content") or v_out
            elif ev["type"] == "error":
                v_out = '{"pass":true,"reason":"verify lỗi, tạm chấp nhận"}'
        vm = re.search(r"\{.*\}", v_out, re.DOTALL)
        verdict = {}
        if vm:
            try:
                verdict = json.loads(vm.group(0))
            except json.JSONDecodeError:
                verdict = {}
        passed = bool(verdict.get("pass", True))
        reason = verdict.get("reason", "")
        fixes = verdict.get("fixes", "")
        await sink({"type": "step_verify_result", "i": index, "node": node.id, "passed": passed,
                    "reason": reason, "attempt": attempt})
        if log_run:
            # Agent kiểm chứng cũng là agent đang LÀM VIỆC - nó nhìn thấy cả nhiệm vụ
            # lẫn kết quả bị chê, là agent học được nhiều nhất mà trước giờ mất dấu.
            log_run(node.verify_agent, f"[kiểm chứng bước của {agent_name}] {prompt}", v_out)
        verified = passed
        if passed or attempt >= node.max_retries:
            break
        attempt += 1
        await sink({"type": "step_retry", "i": index, "node": node.id, "attempt": attempt})
        cur_prompt = (
            f"{prompt}\n\n# KẾT QUẢ LẦN TRƯỚC (bị kiểm chứng đánh giá CHƯA ĐẠT):\n{out[:8000]}\n\n"
            f"# PHẢN HỒI KIỂM CHỨNG:\n- Vấn đề: {reason}\n- Cần sửa: {fixes}\n"
            "CẢI THIỆN kết quả lần trước theo phản hồi: giữ phần đã tốt, sửa đúng chỗ bị chê. Làm cho ĐẠT."
        )
    if learn:
        out = learn(node.agent, out)   # bóc JAVIS_LESSON + ghi bộ nhớ TRƯỚC khi out chảy tiếp
    if log_run:
        log_run(node.agent, prompt, out)
    return {"output": out, "verified": verified, "attempts": attempt + 1,
            "agent_name": agent_name}


def _workflow_agent_helpers(brain, tools):
    """Trả (_mk, _agent_sysprompt) dùng CHUNG cho runner cũ và đường graph Phase 10.

    Tương đương giữa hai đường phải đến từ việc dùng chung code, không phải từ việc
    chép cho giống. Mọi thay đổi ở đây tự động áp cho cả hai.
    """
    vault_root = str(_brain_root(brain))

    def _mk(sysprompt, model=None):
        if model and _is_codex_model(model) and tools is None and find_codex_cli():
            openai_oauth.write_codex_auth()
            cc = CodexCLI(cwd=vault_root, tag="workflow", model=_codex_safe_model(model),
                          instructions=sysprompt)
            _apply_codex_hub(cc, vault_root)
            return cc
        c = claude_engine(system_prompt=sysprompt, cwd=vault_root, tag="workflow",
                          allowed_tools=tools)
        c.model = ((model if not _is_codex_model(model) else "") or _aux_model() or None)
        if tools is not None:
            _mcpf = _empty_mcp_file()
            if _mcpf:
                c.mcp_config = _mcpf
                c.mcp_strict = True
            c.disallowed_tools = ["Bash", "WebFetch", "WebSearch", "Task"]
            # Trần chung cho fork nền (mặc định 1 giờ, env JAVIS_BG_MAX_WALL_S): một bước
            # workflow quét dữ liệu thật cũng có thể chạy quá 300s như việc lịch/Kanban.
            c.max_wall_s = aux_engine.bg_max_wall_s()
        else:
            c.javis_vault = vault_root
        return c

    def _agent_sysprompt(aslug):
        ameta, abody = _read_md(_agents_dir(brain) / f"{aslug}.md")
        amem = _agent_memory(brain, aslug)
        # Khối bộ nhớ + luật tự bồi đắp chèn VÔ ĐIỀU KIỆN (kể cả khi amem rỗng): điều
        # kiện `if amem` cũ là bẫy con-gà-quả-trứng - agent chưa có ký ức thì không bao
        # giờ được bảo là mình CÓ bộ nhớ, nên không bao giờ tạo được ký ức đầu tiên.
        # Đây là cơ chế "tự thông minh lên LÚC DÙNG" chủ repo chốt 16/08: agent tự đúc
        # bài học ngay trong lượt chạy, KHÔNG có job nền nào quét hàng loạt.
        mem_path = _brain_memory_dir(brain) / "agents" / aslug / "MEMORY.md"
        sysprompt = (
            f"Bạn là agent **{ameta.get('name', aslug)}**.\nVai trò: {ameta.get('role','')}\n{abody}\n\n"
            f"Skills khả dụng: {', '.join(ameta.get('skills', []) or []) or '(không)'}. Dùng skill khi cần.\n"
            + f"\n# Bộ nhớ của bạn (file: {mem_path}):\n{amem or '(chưa có ký ức nào)'}\n"
            + "\n# Tự bồi đắp lúc dùng: nếu cuối nhiệm vụ rút ra được bài học TÁI DÙNG cho vai này "
              "(cách làm tốt hơn, lỗi cần tránh, ngữ cảnh riêng đã học được), KẾT THÚC câu trả lời "
              "bằng tối đa 2 dòng riêng, mỗi dòng đúng dạng `JAVIS_LESSON: <bài học một câu>`. "
              "Javis tự ghi vào mục `## Bài học (tự học)` của file bộ nhớ trên (tự loại trùng, giữ "
              f"{_BAI_HOC_TRAN} dòng mới nhất). KHÔNG tự sửa file bộ nhớ trực tiếp - phần ngoài mục "
              "đó là của chủ. Lượt chạy không có gì đáng nhớ thì ĐỪNG phát JAVIS_LESSON, và đừng "
              "lặp lại bài học đã có trong bộ nhớ.\n"
            + "\nLàm việc trong vault. Tập trung hoàn thành nhiệm vụ, trả kết quả rõ ràng, ngắn gọn."
        )
        return ameta.get("name", aslug), sysprompt, (ameta.get("model") or "").strip() or None

    def _log_run(aslug, task, out):
        _log_agent_run(brain, aslug, task, out)

    def _learn(aslug, out):
        """Bóc JAVIS_LESSON khỏi output, ghi vào bộ nhớ agent, trả output ĐÃ SẠCH
        (marker không được chảy vào {{prev}} của bước sau hay lên UI)."""
        lessons, sach = _boc_bai_hoc(out or "")
        if not lessons:
            return out
        _ghi_bai_hoc(brain, aslug, lessons)
        return sach

    return _mk, _agent_sysprompt, _log_run, _learn


async def execute_workflow_graph(brain, slug, input="", tools=None, session_id=""):
    """Đường Phase 10: cùng engine, cùng prompt, khác ở chỗ CÓ trạng thái.

    Yield đúng bộ event mà dashboard đang nghe, cộng thêm `node` để trace theo đồ thị.
    Không admitted thì trả None để caller dùng runner cũ.
    """
    graph = load_workflow_graph(brain, slug)
    if graph is None:
        return
    trace = _CONTEXT_RUNTIME.start_turn(session_id or f"wf:{slug}", _brain_root(brain), "workflow")
    canary = _get_workflow_canary(brain)
    admission = canary.prepare(trace, graph, session_id or f"wf:{slug}")
    if admission.action != "execute":
        _CONTEXT_RUNTIME.finish(trace, "COMPLETED", admission.reason)
        return
    mk, agent_sysprompt, log_run, learn = _workflow_agent_helpers(brain, tools)
    agent_policy = agent_runtime.AgentPolicy.from_settings(cfgmod.read_settings() or {})
    agent_admitted = graph.allows_replan and agent_policy.admits(
        graph.slug, session_id or f"wf:{slug}")[0]
    queue: asyncio.Queue = asyncio.Queue()

    async def sink(event):
        await queue.put(event)

    async def node_executor(node, prompt):
        if node.kind != "model_step":
            # Phase 10 chỉ tự chạy model step. Node capability/workflow con do tầng
            # runtime quyết định; node ghi đã dừng hỏi trước khi tới đây.
            return {"output": "", "error": f"node_kind_not_executable:{node.kind}"}
        return await _run_workflow_step(
            node, prompt, mk, agent_sysprompt, sink,
            router=model_router.ModelRouter(cfgmod.read_settings),
            session_id=session_id or f"wf:{slug}", log_run=log_run, learn=learn)

    async def capability_runner(node, approved):
        """Node capability của workflow.

        Tham số là TĨNH, do người viết workflow khai trong file - không phải do model
        sinh - nên đường này an toàn hơn Phase 9 một bậc. Nhưng node ghi vẫn phải đi
        qua đúng sổ ghi của Phase 9 để giữ chống chạy trùng và trạng thái UNKNOWN.
        """
        try:
            tools, route = await mcp_hub.discover_all(
                "full", vault_root=_brain_root(brain))
        except Exception as exc:
            return {"output": "", "error": f"discover_failed:{type(exc).__name__}"}
        entry = (route or {}).get(node.capability_name or node.capability_id)
        blocked = workflow_capability_guard(node, entry, approved)
        if blocked:
            return {"output": "", "error": blocked}
        try:
            result = await entry["call"](dict(node.arguments or {}))
        except Exception as exc:
            return {"output": "", "error": f"capability_error:{type(exc).__name__}"}
        text = str(result)
        if text.startswith("ERROR:"):
            return {"output": "", "error": "capability_returned_error"}
        return {"output": text[:20000]}

    async def planner(objective, summary, granted):
        """Hỏi model xem nên làm thêm bước nào, TRONG đúng quyền đã cấp.

        Model chỉ được chọn từ danh sách agent/capability đã cấp - danh sách đó đi
        vào chính prompt. Nhưng prompt KHÔNG phải hàng rào: mọi đề xuất vẫn bị
        CapabilityGrant kiểm lại trong code, và một node vượt quyền chặn cả lô.
        Ở đây prompt chỉ để model đỡ đoán mò, không để thay phép kiểm.
        """
        agents = list(granted.get("agents") or [])
        caps = list(granted.get("capabilities") or [])
        if not agents and not caps:
            return []
        failed = {k: v for k, v in (summary.get("nodes") or {}).items()
                  if (v or {}).get("status") != "COMPLETED"}
        spec = {"type": "function", "function": {
            "name": "submit_extra_steps",
            "description": "Đề xuất thêm bước để đạt mục tiêu. Chỉ dùng agent/capability đã cấp.",
            "parameters": {
                "type": "object",
                "properties": {"steps": {
                    "type": "array", "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "kind": {"type": "string", "enum": ["model_step", "capability"]},
                            "agent": {"type": "string", "enum": agents or ["-"]},
                            "capability": {"type": "string", "enum": caps or ["-"]},
                            "task": {"type": "string", "maxLength": 2000},
                            "depends_on": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["kind"], "additionalProperties": False,
                    }}},
                "required": ["steps"], "additionalProperties": False,
            }}}
        messages = [
            {"role": "system", "content":
             "Bạn lập thêm bước cho một agent đang chạy dở. CHỈ dùng agent và capability "
             "trong danh sách đã cấp. Không đủ căn cứ để làm thêm thì trả mảng rỗng - "
             "đó là câu trả lời hợp lệ và tốt hơn việc bịa ra việc."},
            {"role": "user", "content": json.dumps({
                "objective": objective,
                "granted_agents": agents, "granted_capabilities": caps,
                "allows_write": bool(granted.get("allows_write")),
                "nodes_not_completed": failed,
            }, ensure_ascii=False)[:8000]},
        ]
        mcfg = cfgmod.read_settings().get("model", {})
        prov, kind, api_key, api_model = _chat_provider(mcfg)
        if kind != "api" or not api_key:
            # Planner cần tool-call có kiểm soát; engine CLI không đi đường này.
            return []
        try:
            planned = await engine.single_tool_plan(
                prov, api_key, api_model, messages, "off", spec)
        except Exception:
            return []
        if planned.get("status") != "ok":
            return []
        steps = (planned.get("arguments") or {}).get("steps")
        return [x for x in (steps or []) if isinstance(x, dict)][:3]

    async def drive():
        try:
            if agent_admitted:
                runner = agent_runtime.AgentRunner(
                    canary, cfgmod.read_settings, _QUALITY_GATE)
                agent_result = await runner.run(
                    trace, graph, input or "", session_id or f"wf:{slug}",
                    node_executor, planner, sink,
                    capability_runner=capability_runner)
                # Giữ nguyên trạng thái thật. Gộp "đang chờ người duyệt" hay "đã
                # chuyển lại cho người" thành FAILED là ghi sai vào trace: chúng là
                # kết cục BÌNH THƯỜNG, không phải hỏng.
                return workflow_runtime.WorkflowRunResult(
                    agent_result.status, agent_result.output,
                    agent_result.stop_reason, agent_result.task_id,
                    pending_node_id=agent_result.output_node_id)
            return await canary.run(trace, graph, input or "", session_id or f"wf:{slug}",
                                    node_executor, sink,
                                    capability_runner=capability_runner)
        finally:
            await queue.put(None)

    task = asyncio.create_task(drive())
    while True:
        event = await queue.get()
        if event is None:
            break
        yield event
    result = await task
    # ESCALATED và STOPPED là dừng có chủ đích, không phải lỗi runtime.
    _CONTEXT_RUNTIME.finish(
        trace,
        {"COMPLETED": "COMPLETED", "WAITING_USER": "WAITING_USER",
         "ESCALATED": "COMPLETED_WITH_ERROR", "STOPPED": "COMPLETED_WITH_ERROR"}.get(
            result.status, "FAILED"),
        result.stop_reason)
    if result.status == "WAITING_USER":
        yield {"type": "wait_user", "node": result.pending_node_id,
               "task_id": result.task_id, "reason": result.stop_reason}


async def execute_workflow(brain, slug, input="", tools=None, session_id=""):
    """Chạy workflow nhiều agent tuần tự, YIELD event dict (KHÔNG bọc SSE). Dùng CHUNG cho:
      - /workflows/run  : user bấm ở Studio (full quyền, stream SSE).
      - dispatcher Kanban: chạy nền không người xem → truyền tools=SAFE_FILE_TOOLS để agent
        CHỈ thao tác file (không đụng MCP tiền/đơn) + cô lập MCP (strict rỗng). Task cần hành
        động ra ngoài → dừng ở review cho người duyệt, KHÔNG tự làm.
    tools=None → full (như cũ). list → giới hạn tool + cô lập MCP (an toàn nền)."""
    wf_file = _workflows_dir(brain) / f"{slug}.md"
    if not wf_file.exists():
        yield {"type": "error", "content": "workflow not found"}
        return
    # Phase 10 canary: mặc định allocation 0 nên vòng lặp cũ vẫn là đường duy nhất.
    # Lỗi ở đường mới không được cướp lượt chạy - rơi về runner cũ.
    emitted = False
    try:
        async for event in execute_workflow_graph(brain, slug, input, tools, session_id):
            emitted = True
            yield event
        if emitted:
            return
    except Exception as _wf_exc:
        print(f"[workflow graph] {type(_wf_exc).__name__}", file=__import__('sys').stderr)
        if emitted:
            # Đã phát event ra client rồi thì chạy lại bằng runner cũ là CHẠY HAI LẦN.
            # Báo lỗi và dừng, để người dùng quyết định chạy lại.
            yield {"type": "error",
                   "content": "Workflow dừng giữa chừng ở đường mới. Không tự chạy lại "
                              "để tránh làm hai lần; bạn chạy lại nếu cần."}
            return
    meta, _ = _read_md(wf_file)
    steps = meta.get("steps", []) or []
    vault_root = str(_brain_root(brain))
    try:
        # Agent workflow chạy cwd=brain, agent nền có MCP rỗng → chỉ nạp skill NATIVE từ
        # .claude/skills. Đảm bảo đã migrate + mirror trước khi spawn (idempotent, rẻ).
        system_sync.ensure_synced(vault_root)
        system_sync.mirror_skills(vault_root)
    except Exception:
        pass

    _mk, _agent_sysprompt, _log, _learn = _workflow_agent_helpers(brain, tools)

    yield {"type": "start", "workflow": meta.get("name", slug), "steps": len(steps)}
    prev = ""
    for i, step in enumerate(steps):
        agent_slug = step.get("agent", "")
        task = step.get("task", "")
        verify_slug = (step.get("verify_agent") or "").strip()
        max_retries = int(step.get("max_retries", 1) or 0)
        agent_name, sysprompt, agent_model = _agent_sysprompt(agent_slug)
        task_f = task.replace("{{input}}", input or "").replace("{{prev}}", prev or "")
        yield {"type": "step_start", "i": i, "agent": agent_name, "task": task_f}

        cur_prompt = task_f
        out = ""
        verified = None
        attempt = 0
        while True:
            gcli = _mk(sysprompt, agent_model)   # áp model agent đã chọn
            out = ""
            async for ev in gcli.query(cur_prompt):
                if ev["type"] == "text":
                    yield {"type": "step_text", "i": i, "content": ev["content"]}
                elif ev["type"] == "tool_call":
                    yield {"type": "step_tool", "i": i, "tool": ev["name"]}
                elif ev["type"] == "final":
                    out = ev.get("content") or out
                elif ev["type"] == "error":
                    yield {"type": "step_error", "i": i, "content": ev["content"]}

            if not verify_slug:
                break

            # --- KIỂM CHỨNG bằng agent KHÁC (giả định kết quả SAI) ---
            v_name, v_body, v_model = _agent_sysprompt(verify_slug)
            yield {"type": "step_verify", "i": i, "agent": v_name, "attempt": attempt}
            v_sys = (
                v_body + "\n\nVAI TRÒ KIỂM CHỨNG: Bạn là người ĐÁNH GIÁ độc lập. "
                "Mặc định GIẢ ĐỊNH kết quả dưới đây ĐANG SAI và phải tự chứng minh. "
                "Kiểm tra thực tế (đọc file/chạy thử nếu cần), KHÔNG chỉ đọc lướt. "
                'CHỈ trả JSON 1 dòng: {"pass":true|false,"reason":"ngắn gọn vì sao","fixes":"cần sửa gì nếu fail"}.'
            )
            v_prompt = (
                f"NHIỆM VỤ GỐC:\n{task_f}\n\n"
                f"KẾT QUẢ CẦN KIỂM CHỨNG:\n{out}\n\n"
                "Đánh giá kết quả có ĐẠT nhiệm vụ không. Trả JSON như hướng dẫn."
            )
            vcli = _mk(v_sys, v_model)   # agent kiểm chứng cũng dùng model của nó
            v_out = ""
            async for ev in vcli.query(v_prompt):
                if ev["type"] == "final":
                    v_out = ev.get("content") or v_out
                elif ev["type"] == "error":
                    v_out = '{"pass":true,"reason":"verify lỗi, tạm chấp nhận"}'
            vm = re.search(r"\{.*\}", v_out, re.DOTALL)
            verdict = {}
            if vm:
                try:
                    verdict = json.loads(vm.group(0))
                except json.JSONDecodeError:
                    verdict = {}
            passed = bool(verdict.get("pass", True))
            reason = verdict.get("reason", "")
            fixes = verdict.get("fixes", "")
            yield {"type": "step_verify_result", "i": i, "passed": passed, "reason": reason, "attempt": attempt}
            _log(verify_slug, f"[kiểm chứng bước của {agent_name}] {task_f}", v_out)
            verified = passed
            if passed or attempt >= max_retries:
                break
            attempt += 1
            yield {"type": "step_retry", "i": i, "attempt": attempt}
            # Evaluator-optimizer (cookbook Anthropic): lượt sau THẤY kết quả cũ + phản hồi
            # để CẢI THIỆN tiếp, không làm lại từ đầu (làm lại mù dễ lặp đúng lỗi cũ).
            cur_prompt = (
                f"{task_f}\n\n# KẾT QUẢ LẦN TRƯỚC (bị kiểm chứng đánh giá CHƯA ĐẠT):\n{out[:8000]}\n\n"
                f"# PHẢN HỒI KIỂM CHỨNG:\n- Vấn đề: {reason}\n- Cần sửa: {fixes}\n"
                "CẢI THIỆN kết quả lần trước theo phản hồi: giữ phần đã tốt, sửa đúng chỗ bị chê. Làm cho ĐẠT."
            )

        out = _learn(agent_slug, out)   # bóc JAVIS_LESSON + ghi bộ nhớ trước khi out thành {{prev}}
        prev = out
        yield {"type": "step_done", "i": i, "agent": agent_name, "output": out, "verified": verified}
        _log(agent_slug, task_f, out)
    yield {"type": "done", "result": prev}


def workflow_capability_guard(node, route_entry, approved: bool) -> str:
    """Hàng rào cuối trước khi chạy một node capability. Rỗng = cho chạy.

    Tách ra thành hàm gọi được là có chủ đích: tầng workflow_runtime đã dừng ở node
    ghi trước khi tới đây, nên đây là LỚP THỨ HAI và không bao giờ được chạm tới ở
    luồng bình thường. Một hàng rào không kiểm được là hàng rào không tin được.
    """
    if not route_entry or not callable(route_entry.get("call")):
        return "capability_route_missing"
    effect = str(route_entry.get("effect") or "read")
    if effect not in ("none", "read", "write"):
        return f"effect_not_allowed:{effect}"
    if effect == "write" and not approved:
        return "write_without_approval"
    return ""


async def execute_workflow_resume(brain, slug, task_id, node_id, code, tools=None,
                                  session_id=""):
    """Duyệt xong thì chạy tiếp workflow đang dừng. Yield event như /workflows/run."""
    graph = load_workflow_graph(brain, slug)
    if graph is None:
        yield {"type": "error", "content": "workflow not found"}
        return
    trace = _CONTEXT_RUNTIME.resume_trace(task_id)
    if trace is None:
        yield {"type": "error", "content": "Không tìm thấy hoặc không resume được task này."}
        return
    canary = _get_workflow_canary(brain)
    mk, agent_sysprompt, log_run, learn = _workflow_agent_helpers(brain, tools)
    queue: asyncio.Queue = asyncio.Queue()

    async def sink(event):
        await queue.put(event)

    async def node_executor(node, prompt):
        if node.kind != "model_step":
            return {"output": "", "error": f"node_kind_not_executable:{node.kind}"}
        return await _run_workflow_step(
            node, prompt, mk, agent_sysprompt, sink,
            router=model_router.ModelRouter(cfgmod.read_settings),
            session_id=session_id or f"wf:{slug}", log_run=log_run, learn=learn)

    async def capability_runner(node, approved):
        try:
            _tools, route = await mcp_hub.discover_all("full", vault_root=_brain_root(brain))
        except Exception as exc:
            return {"output": "", "error": f"discover_failed:{type(exc).__name__}"}
        entry = (route or {}).get(node.capability_name or node.capability_id)
        blocked = workflow_capability_guard(node, entry, approved)
        if blocked:
            return {"output": "", "error": blocked}
        try:
            result = await entry["call"](dict(node.arguments or {}))
        except Exception as exc:
            return {"output": "", "error": f"capability_error:{type(exc).__name__}"}
        text = str(result)
        return ({"output": "", "error": "capability_returned_error"}
                if text.startswith("ERROR:") else {"output": text[:20000]})

    async def drive():
        try:
            return await canary.resume(
                trace, task_id, graph, node_executor, sink,
                confirmed_node_id=str(node_id or ""),
                confirmation_code=str(code or ""),
                capability_runner=capability_runner)
        finally:
            await queue.put(None)

    task = asyncio.create_task(drive())
    while True:
        event = await queue.get()
        if event is None:
            break
        yield event
    result = await task
    _CONTEXT_RUNTIME.finish(
        trace, "COMPLETED" if result.status == "COMPLETED" else "COMPLETED_WITH_ERROR",
        result.stop_reason)
    if result.status == "WAITING_USER":
        yield {"type": "wait_user", "node": result.pending_node_id,
               "task_id": task_id, "reason": result.stop_reason}


@app.get("/workflows/resume")
async def resume_workflow(task_id: str = Query(...), node: str = Query(...),
                          code: str = Query(...), slug: str = Query(...),
                          brain: str = Query("brain")):
    """Duyệt một node đang chờ rồi chạy tiếp. Mã sai thì workflow đứng yên."""
    def sse(obj):
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    async def gen():
        async for ev in execute_workflow_resume(brain, slug, task_id, node, code):
            yield sse(ev)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/workflows/run")
async def run_workflow(slug: str = Query(...), brain: str = Query("brain"), input: str = Query("")):
    """Chạy workflow (user bấm ở Studio) - stream tiến độ qua SSE, full quyền."""
    if not (_workflows_dir(brain) / f"{slug}.md").exists():
        return JSONResponse({"error": "workflow not found"}, status_code=404)

    def sse(obj):
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    async def gen():
        async for ev in execute_workflow(brain, slug, input):
            yield sse(ev)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.post("/studio/seed")
async def studio_seed(brain: str = Form("brain")):
    """Tạo bộ Agent + Workflow mẫu để bắt đầu."""
    a = _agents_dir(brain)
    examples = [
        {"name": "Researcher", "role": "Chuyên nghiên cứu, tìm tư liệu và tổng hợp nguồn đáng tin cậy.",
         "skills": ["deep-research"], "prompt": "Bạn tìm 5-7 nguồn chất lượng, trích dẫn rõ ràng, tổng hợp insight chính."},
        {"name": "Writer", "role": "Chuyên viết bài chuẩn SEO và hấp dẫn từ tư liệu nghiên cứu.",
         "skills": ["salepage-16-buoc"], "prompt": "Bạn viết bài có cấu trúc, hook mạnh, dùng tư liệu được cung cấp."},
        {"name": "Kiểm chứng viên", "role": "Đánh giá độc lập - luôn giả định kết quả SAI và phải chứng minh.",
         "skills": [], "prompt": "Bạn KHÔNG tạo nội dung, chỉ ĐÁNH GIÁ. Mặc định kết quả đang sai/thiếu. "
                                 "Kiểm tra thực tế: có bám nhiệm vụ không, có bịa/thiếu dẫn chứng không, có lỗi rõ ràng không. "
                                 "Khắt khe nhưng công bằng."},
    ]
    for ex in examples:
        slug = _slugify(ex["name"])
        meta = {"type": "agent", "name": ex["name"], "slug": slug, "role": ex["role"],
                "skills": ex["skills"], "model": "sonnet", "updated": _today()}
        _write_md(a / f"{slug}.md", meta, ex["prompt"])
    wf_meta = {"type": "workflow", "name": "Research → Write (có kiểm chứng)", "slug": "research-and-write",
               "status": "active", "description": "Nghiên cứu → viết bài → kiểm chứng độc lập, tự sửa nếu chưa đạt.",
               "steps": [
                   {"agent": "researcher", "task": "Nghiên cứu kỹ chủ đề: {{input}}. Tìm nguồn, tổng hợp insight chính."},
                   {"agent": "writer", "task": "Viết một bài hoàn chỉnh về '{{input}}' dựa trên nghiên cứu sau:\n{{prev}}",
                    "verify_agent": "kiem-chung-vien", "max_retries": 2},
               ], "updated": _today()}
    _write_md(_workflows_dir(brain) / "research-and-write.md", wf_meta, wf_meta["description"])
    return {"ok": True}


# ============================================================
# LOOP TỰ CẢI THIỆN (Beta) - Discovery + Scheduling, an toàn (chỉ thao tác file vault)
# ============================================================
# An toàn: loop CHỈ được dùng các tool file dưới đây → không thể gọi MCP tạo đơn/đốt tiền.
SAFE_FILE_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "LS"]
READONLY_TOOLS = ["Read", "Glob", "Grep", "LS"]

# Vòng tự cải thiện đã TÁCH sang module self_improve.py - giờ là MULTI-LOOP: N loop định
# nghĩa bằng file <vault>/Javis/loops/<slug>.md, state ở <vault>/Javis/loop-state.json,
# thực thi TUẦN TỰ (1 lock). main.py chỉ tiêm helper + giữ shim mỏng cho code cũ.
# Endpoints /loops/* (mới) + /loop/* (shim legacy) nằm trong router của self_improve.
import self_improve


async def _loop_notify(text: str) -> None:
    """Báo Telegram khi loop tự tạm dừng (nice-to-have, im lặng nếu chưa cấu hình bot).
    Gửi tới TẤT CẢ chat ID trong whitelist (hỗ trợ nhiều người dùng chung bot)."""
    try:
        tg = cfgmod.read_settings().get("telegram", {})
        ids = tg_parse_ids(tg.get("chat_id"))
        if not (tg.get("enabled") and tg.get("token") and ids):
            return
        import httpx
        async with httpx.AsyncClient(timeout=10) as c:
            for cid in ids:
                await c.post(f"https://api.telegram.org/bot{tg['token']}/sendMessage",
                             json={"chat_id": cid, "text": text})
    except Exception as e:
        print(f"[loop notify] {e}", file=__import__('sys').stderr)


async def _tg_send_to(chat_id, text) -> tuple:
    """Gửi 1 tin tới ĐÚNG chat_id (dùng cho nhắc hẹn). chat_id rỗng hoặc không nằm trong
    whitelist → gửi cho CHỦ bot (mọi ID whitelist). Trả (ok, error).

    Nhắc hẹn đặt TỪ Zalo mang chat_id có tiền tố `zalo:` - rẽ sang bot Zalo ngay tại đây. Tên
    hàm giữ nguyên vì nó là cửa duy nhất `reminders.py` biết; đổi tên chỉ để đúng chính tả là
    phải sửa cả một tầng không liên quan.
    """
    cid_raw = str(chat_id or "").strip()
    if cid_raw.startswith(ZALO_CHAT_PREFIX):
        return await _zalo_send_to(cid_raw[len(ZALO_CHAT_PREFIX):], text)
    tg = cfgmod.read_settings().get("telegram", {})
    token = tg.get("token")
    ids = tg_parse_ids(tg.get("chat_id"))
    if not (tg.get("enabled") and token):
        return False, "Bot Telegram chưa bật"
    cid = str(chat_id or "").strip()
    targets = [cid] if (cid and (not ids or cid in ids)) else (ids or ([cid] if cid else []))
    if not targets:
        return False, "Chưa có chat_id đích"
    import httpx
    ok_any, errs = False, []
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            for t in targets:
                try:
                    r = await c.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                     json={"chat_id": t, "text": text})
                    d = r.json() if r.content else {}
                    if d.get("ok"):
                        ok_any = True
                    else:
                        errs.append(str(d.get("description") or f"HTTP {r.status_code}")[:80])
                except Exception as e:
                    errs.append(type(e).__name__)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    return ok_any, "; ".join(e for e in errs if e)[:200]


async def push_to_chat(session_id, text) -> bool:
    """Đẩy MỘT tin của Javis vào đúng phiên chat web, ngoài luồng hỏi-đáp thường.

    Vì sao cần: việc Kanban / loop / nhắc hẹn chạy nền xong thì lượt chat đã kết thúc từ lâu,
    không còn chỗ nào để trả lời. Trước 0.9.289 kết quả CHỈ đi Telegram, nên người dùng ngồi
    trên web giao việc xong là im lặng tuyệt đối - không trạng thái, không hồi âm (đúng lỗi
    chủ repo báo). Ghi vào kho phiên TRƯỚC rồi mới bắn WebSocket: ghi trước thì đóng tab hay
    F5 xong mở lại vẫn thấy, bắn sau chỉ để ai đang mở thấy NGAY.
    """
    sid = str(session_id or "").strip()
    clean = channel_context.strip_control_blocks(text or "").strip()
    if not sid or not clean:
        return False
    try:
        get_store().append_message(sid, "assistant", clean)
    except Exception as e:
        print(f"[push_to_chat] lưu phiên lỗi: {type(e).__name__}: {e}", file=sys.stderr)
    try:
        await _CHAT_RUNTIME.publish({"type": "push", "content": clean, "session_id": sid})
    except Exception as e:
        print(f"[push_to_chat] bắn WebSocket lỗi: {type(e).__name__}: {e}", file=sys.stderr)
    return True


WEB_CHAT_PREFIX = "web:"   # owner_chat của việc giao từ dashboard: "web:<mã phiên chat>"


async def _zalo_send_to(chat_id, text) -> tuple:
    """Gửi 1 tin Zalo tới ĐÚNG chat_id. Trả (ok, error). Đối xứng với `_tg_send_to`."""
    z = cfgmod.read_settings().get("zalo_bot", {})
    token = z.get("token")
    ids = tg_parse_ids(z.get("chat_id"))
    if not (z.get("enabled") and token):
        return False, "Bot Zalo chưa bật"
    cid = str(chat_id or "").strip()
    targets = [cid] if (cid and (not ids or cid in ids)) else (ids or ([cid] if cid else []))
    if not targets:
        return False, "Chưa có chat_id đích"
    import httpx
    ok_any, errs = False, []
    url = f"https://bot-api.zaloplatforms.com/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            for t in targets:
                try:
                    r = await c.post(url, json={"chat_id": t, "text": text[:1900]})
                    d = r.json() if r.content else {}
                    if d.get("ok"):
                        ok_any = True
                    else:
                        errs.append(str(d.get("description") or f"HTTP {r.status_code}")[:120])
                except Exception as e:
                    errs.append(f"{type(e).__name__}: {e}")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    return ok_any, "; ".join(errs)[:200]


async def _notify_owner(owner_chat, text) -> tuple:
    """Báo cáo cho NGƯỜI YÊU CẦU loop/task (mặc định của Javis). Quy tắc:
      - owner_chat dạng "web:<sid>" → đẩy thẳng vào ĐÚNG khung chat web đã giao việc.
      - owner_chat dạng "zalo:<id>" → gửi qua bot Zalo cho ĐÚNG người đó.
      - owner_chat là chat_id Telegram trong whitelist → gửi ĐÚNG người đó.
      - owner_chat rỗng (không rõ ai giao) → gửi ID ĐẦU TIÊN trong whitelist (chủ bot).

    Vì sao có nhánh web: người ngồi dashboard giao việc xong thì lượt chat đã đóng, mà kênh
    báo duy nhất trước 0.9.289 là Telegram - máy không đấu Telegram thì im lặng tuyệt đối,
    đúng lỗi "chạy agent không có trạng thái, không có phản hồi". Mượn luôn field chat_id
    (đã xuyên suốt enqueue → DB → _report) thay vì thêm cột: một việc chỉ sinh ra từ MỘT
    kênh nên không bao giờ cần mang cả hai.

    Im lặng (trả (False, lý do)) nếu bot chưa bật / chưa có chat_id. Trả (ok, error)."""
    cid = str(owner_chat or "").strip()
    if cid.startswith(WEB_CHAT_PREFIX):
        sid = cid[len(WEB_CHAT_PREFIX):]
        if await push_to_chat(sid, text):
            return True, ""
        return False, "Không tìm thấy phiên chat web để báo"
    # Việc giao TỪ Zalo phải báo VỀ Zalo. Không có nhánh này thì kết quả rơi sang Telegram của
    # chủ, tức là người giao việc không bao giờ thấy nó, còn chủ thì nhận một báo cáo không
    # rõ của ai - và máy chưa đấu Telegram thì mất hút hoàn toàn.
    if cid.startswith(ZALO_CHAT_PREFIX):
        return await _zalo_send_to(cid[len(ZALO_CHAT_PREFIX):], text)
    tg = cfgmod.read_settings().get("telegram", {})
    token = tg.get("token")
    ids = tg_parse_ids(tg.get("chat_id"))
    if not (tg.get("enabled") and token and ids):
        return False, "Bot Telegram chưa bật hoặc chưa có chat_id"
    target = cid if (cid and cid in ids) else ids[0]
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"https://api.telegram.org/bot{token}/sendMessage",
                             json={"chat_id": target, "text": text})
            d = r.json() if r.content else {}
            if d.get("ok"):
                return True, ""
            return False, str(d.get("description") or f"HTTP {r.status_code}")[:200]
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _loop_mcp_allow():
    """Pattern MCP cho allowlist của loop. Hub bật: mọi tool nằm dưới server 'javis' → 1 pattern;
    quyền đọc/ghi thật sự do hub chặn theo X-Javis-Mode. Hub tắt: 'mcp__<namespace>' như cũ."""
    try:
        conns = [c for c in mcp_store.list_connections() if c.get("enabled")]
        if not conns:
            return []
        if _hub_enabled():
            return mcp_hub.allow_patterns()
        return [f"mcp__{r['namespace']}" for r in mcp_store.resolved()
                if r.get("auth") != "oauth" and r.get("namespace")]
    except Exception:
        return []


loop_feature = self_improve.register(app, self_improve.LoopDeps(
    build_system_prompt=build_system_prompt,
    brain_root=_brain_root,
    aux_model=_aux_model,
    aux_swap=_aux_swap,
    atomic_write_text=_atomic_write_text,
    project_root=PROJECT_ROOT,
    state_dir=cfgmod.STATE_DIR,
    safe_tools=SAFE_FILE_TOOLS,
    readonly_tools=READONLY_TOOLS,
    notify=_loop_notify,
    report=_notify_owner,               # báo Telegram cho NGƯỜI YÊU CẦU loop mỗi vòng (web → ID đầu)
    apply_mcp=_apply_mcp,               # loop ĐỌC được dữ liệu thật qua MCP Javis-quản-lý
    mcp_allow_patterns=_loop_mcp_allow,
))

_LOOP_LOCK = loop_feature.lock   # shim: giữ tên cũ cho code phía dưới (scheduler)


def _read_loop_config():
    return loop_feature.read_config()


def _write_loop_config(cfg):
    loop_feature.write_config(cfg)


async def run_loop_cycle(reason="manual"):
    # Shim: giờ = "chạy loop đến hạn nhất" (multi-loop chọn loop quá hạn lâu nhất)
    return await loop_feature.run_due(reason)


# ============================================================
# ENGINE TỰ HỌC (learn.py) - rewire sau lượt + auto-Wiki + skill + curator.
# READ-ONLY fork trả manifest JSON; Python tin cậy ghi; fail-closed qua git.
# Mặc định enabled=False, mode=dry-run → bật an toàn.
# ============================================================
import learn as learn_mod

learn_feature = learn_mod.register(app, learn_mod.LearnDeps(
    build_system_prompt=build_system_prompt,
    brain_root=_brain_root,
    brain_memory_dir=_brain_memory_dir,
    resolve_subfolder=_resolve_subfolder,
    aux_model=_aux_model,
    aux_swap=_aux_swap,
    atomic_write_text=_atomic_write_text,
    sessions_store=get_store(),
    state_dir=cfgmod.STATE_DIR,
    readonly_tools=READONLY_TOOLS,
))


# ============================================================
# AUTONOMOUS TASK QUEUE + DISPATCHER - tasks.py
# SQLite giữ lifecycle, dispatcher riêng quét mọi brain, worker chạy độc lập với scheduler
# nhắc hẹn. Model nền Claude/Codex/API dùng chung aux_engine và cùng policy quyền.
# Mặc định orchestration=off; người dùng bật auto theo từng brain.
# ============================================================
import tasks as tasks_mod


def _kanban_brains():
    """Mọi brain cần dispatcher quét, gồm cả folder ngoài đã đăng ký với scheduler."""
    values = []
    try:
        values.extend(
            str(p) for p in Path(BRAINS_DIR).iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )
    except Exception:
        pass
    try:
        values.extend(loop_feature.scheduler_brains() or [])
    except Exception:
        pass
    return list(dict.fromkeys(values))


tasks_feature = tasks_mod.register(app, tasks_mod.TasksDeps(
    brain_root=_brain_root,
    atomic_write_text=_atomic_write_text,
    execute_workflow=execute_workflow,
    workflows_dir=_workflows_dir,
    build_system_prompt=build_system_prompt,
    aux_model=_aux_model,
    aux_swap=_aux_swap,
    safe_tools=SAFE_FILE_TOOLS,
    state_dir=cfgmod.STATE_DIR,
    scheduler_brains=_kanban_brains,
    apply_mcp=_apply_mcp,
    mcp_allow_patterns=_loop_mcp_allow,
    report=_notify_owner,               # báo Telegram cho NGƯỜI YÊU CẦU task khi chạy xong (web → ID đầu)
))

# Nối learn → Kanban: engine học đề xuất việc nền → enqueue vào backlog.
# Gate ở learn.py (cap "task" mặc định off + chỉ enqueue khi allow_write); dedup ở tasks.enqueue.
learn_feature.deps.enqueue_task = tasks_feature.enqueue


# ============================================================
# NHẮC HẸN TỪ CHAT (reminders.py) - "30 phút nữa nhắc anh...", "8h30 sáng mai...".
# Javis tự đặt qua POST /reminders (localhost), scheduler nền đánh thức đúng giờ → bắn Telegram.
# mode notify = nhắn lại · mode task = chạy engine (đọc MCP, ghi nháp) rồi báo. KHÔNG tiền/đơn.
# ============================================================
import reminders as reminders_mod


def _notify_ready() -> tuple:
    """(sẵn_sàng, lý_do): Javis có đường BÁO kết quả cho người dùng hay chưa. Nhắc hẹn và việc
    nền chỉ có giá trị khi tới giờ nó nói được với ai đó - chưa đấu kênh nào thì việc chạy xong
    rồi kết quả rơi vào hư không, người dùng tưởng Javis quên. Dùng để chặn ngay lúc TẠO.

    ĐỦ MỘT kênh là đủ. Từ 0.26.8 Zalo cũng tính: người dùng chỉ đấu Zalo mà bị chặn tạo nhắc
    hẹn với lý do "bot Telegram chưa bật" là một câu vừa sai vừa không sửa được, và nó đẩy họ
    đi cài một app họ không cần.
    """
    try:
        cfg = cfgmod.read_settings()
    except Exception:
        return True, ""      # không đọc được cấu hình thì đừng dựng rào, cứ để tạo
    thieu = []
    for khoa, ten in (("telegram", "Telegram"), ("zalo_bot", "Zalo")):
        c = cfg.get(khoa, {}) or {}
        if not c.get("enabled"):
            thieu.append(f"bot {ten} chưa bật")
        elif not c.get("token"):
            thieu.append(f"bot {ten} chưa có token")
        elif not tg_parse_ids(c.get("chat_id")):
            thieu.append(f"bot {ten} chưa có Chat ID được phép")
        else:
            return True, ""
    return False, " và ".join(thieu)


def _notify_live_warn() -> str:
    """Cấu hình đủ nhưng bot Telegram ĐANG lỗi thật (token bị thu hồi, 409 poll trùng...) thì
    việc tới giờ vẫn chạy mà tin không đi được. KHÔNG dùng để chặn tạo việc (lỗi có thể thoáng
    qua và tự khỏi), chỉ để nói ra ở trang Việc. Rỗng = không có gì đáng báo."""
    try:
        loi = []
        if _TG_BOT and _TG_BOT.status in ("error", "conflict"):
            loi.append(f"bot Telegram đang lỗi ({_TG_BOT.status}): {(_TG_BOT.last_error or '')[:160]}")
        if _ZALO_BOT and _ZALO_BOT.status == "error":
            loi.append(f"bot Zalo đang lỗi: {(_ZALO_BOT.last_error or '')[:160]}")
        return "; ".join(loi)
    except Exception:
        return ""


reminders_feature = reminders_mod.register(app, reminders_mod.RemindersDeps(
    brain_root=_brain_root,
    atomic_write_text=_atomic_write_text,
    send_telegram=_tg_send_to,
    notify_ready=_notify_ready,
    build_system_prompt=build_system_prompt,
    aux_model=_aux_model,
    aux_swap=_aux_swap,
    safe_tools=SAFE_FILE_TOOLS,
    readonly_tools=READONLY_TOOLS,
    scheduler_brains=loop_feature.scheduler_brains,
    apply_mcp=_apply_mcp,                 # nhắc mode 'task' ĐỌC được dữ liệu thật qua MCP
    mcp_allow_patterns=_loop_mcp_allow,
))


@app.get("/viec/all")
async def viec_all():
    """Gộp MỌI brain cho trang Việc: mỗi brain kèm loop + nhắc hẹn đang chờ, mỗi item gắn
    brain_name/brain_path để nút thao tác (bật/tắt/xoá/chuyển/huỷ) nhắm ĐÚNG brain của chính
    item, không phải brain đang chọn ở sidebar. Quét list_brains() (KHÔNG chỉ brain đã đăng ký)
    để thấy cả việc nằm ở brain chưa từng mở trên dashboard - đây là gốc của cái rối 'tạo qua
    Telegram vào brain mặc định, tìm ở brain khác không thấy'."""
    loop_feature.ensure_migrated()

    def _brain_viec(name: str, path: str, is_default: bool) -> dict:
        try:
            st_all = loop_feature.read_state(path)
            loops = []
            for lp in loop_feature.list_loops(path):
                v = loop_feature.loop_view(path, lp, st_all)
                v["brain_name"], v["brain_path"] = name, path
                loops.append(v)
        except Exception:
            loops = []
        try:
            rems = []
            for v in reminders_feature.pending_views(path):
                v["brain_name"], v["brain_path"] = name, path
                rems.append(v)
        except Exception:
            rems = []
        if loops or rems:
            loop_feature.register_brain(path)   # brain có việc → scheduler nền quét
        return {"name": name, "path": path, "is_default": is_default,
                "loops": loops, "reminders": rems}

    # Liệt kê thư mục brain RẺ - KHÔNG dùng list_brains() vì nó đếm note bằng rglob("*.md") quét
    # CẢ cây mỗi brain (vault lớn = vài giây). Trang Việc không cần số note; đếm làm /viec/all chậm
    # tới mức reverse proxy trên VPS cắt giữa chừng (504) → dashboard báo "không tải được". Đây là
    # gốc lỗi VPS khách không hiện mà VPS nhẹ hơn vẫn hiện.
    base = Path(BRAINS_DIR)
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    try:
        default_resolved = _default_brain_dir().resolve()
    except Exception:
        default_resolved = None
    out = []
    seen = set()
    try:
        brain_dirs = sorted((p for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")),
                            key=lambda x: x.name.lower())
    except Exception:
        brain_dirs = []
    for p in brain_dirs:
        path = str(p)
        try:
            rp = p.resolve()
            seen.add(str(rp))
            is_def = default_resolved is not None and rp == default_resolved
        except Exception:
            is_def = False
        out.append(_brain_viec(p.name, path, is_def))

    # Gộp thêm brain đã ĐĂNG KÝ với scheduler nhưng KHÔNG nằm trong BRAINS_DIR (folder ngoài, hoặc
    # brain legacy trong loop_config). Trước đây chỉ quét list_brains() nên loop tạo qua chat vào
    # brain ngoài VẪN CHẠY (scheduler quét) mà KHÔNG hiện ở tab Việc → đúng triệu chứng khách báo.
    try:
        extra = loop_feature.scheduler_brains()
    except Exception:
        extra = []
    for bident in extra:
        try:
            ep = _brain_root(bident)
            rp = str(Path(ep).resolve())
        except Exception:
            continue
        if rp in seen or not os.path.isdir(ep):
            continue
        seen.add(rp)
        v = _brain_viec(Path(ep).name, ep, False)
        if v["loops"] or v["reminders"]:   # brain ngoài chỉ hiện khi thực sự có việc (tránh rác)
            out.append(v)

    ready, why = reminders_feature.notify_status()
    return {"brains": out, "running": loop_feature.lock.locked(),
            "running_slug": loop_feature._running[1] if loop_feature._running else "",
            # Trang Việc cảnh báo ngay đầu trang khi chưa có kênh báo: việc vẫn chạy nhưng không
            # ai nhận được kết quả, mà đó là thứ người dùng KHÔNG tự đoán ra được. "warn" là
            # trường hợp KHÁC: cấu hình đủ nhưng bot đang lỗi thật (token bị thu hồi, 409...) -
            # không chặn tạo việc (lỗi có thể chỉ thoáng qua) nhưng phải nói ra.
            "notify": {"ok": ready, "error": why, "warn": _notify_live_warn()}}


# ============================================================
# VIỆC NỀN CỦA MỘT KHUNG CHAT - dải trạng thái sống trong khung chat
#
# Lỗi thật chủ repo báo (2026-08-06): "có agent chạy ngầm thì anh cũng không biết là nó đang
# chạy thật hay không, không giống Claude nếu đang chạy ngầm thì vẫn có báo ở đầu hội thoại".
# Đúng: trước bản này khung chat KHÔNG hiện một chữ nào về việc nền. Muốn biết phải tự mở
# trang Việc, mà người dùng thì không có lý do nào để nghĩ là phải mở.
#
# Ba kho khác nhau nên phải gom ở đây, không nằm sẵn chỗ nào: việc Kanban (sqlite), loop
# (file .md trong brain), nhắc hẹn (reminders.json). Cả ba đều tự báo kết quả về khung chat
# qua `_notify_owner`, nên cả ba đều đáng hiện.
# ============================================================
def _viec_nen_view(brain: str, chat_id: str = "") -> dict:
    """Khung nhìn việc nền còn sống của một brain, đánh dấu việc thuộc đúng khung chat này."""
    root = _brain_root(brain)
    try:
        tasks = tasks_feature.store.list_tasks(root)
    except Exception:
        tasks = []
    try:
        orchestration = tasks_feature.store.board_mode(root)
    except Exception:
        orchestration = "off"
    try:
        st_all = loop_feature.read_state(root)
        loops = [loop_feature.loop_view(root, lp, st_all)
                 for lp in loop_feature.list_loops(root)]
    except Exception:
        loops = []
    try:
        rems = reminders_feature.pending_views(root)
    except Exception:
        rems = []
    running_slug = ""
    try:
        running_slug = loop_feature._running[1] if loop_feature._running else ""
    except Exception:
        pass
    return background_status.active_view(
        tasks, loops, rems, chat_id=chat_id,
        orchestration=orchestration, running_loop=running_slug,
    )


@app.get("/background")
async def background_active(brain: str = Query("brain"), chat_id: str = Query("")):
    """Việc nền đang sống, cho dải trạng thái trong khung chat.

    `chat_id`: "web:<mã phiên>" khi gọi từ dashboard. Việc khớp chat_id được đánh dấu `mine`
    để dải trạng thái nói được "việc CỦA hội thoại này" thay vì gộp chung với việc của người
    khác - gộp chung thì lại đúng chỗ mù mà endpoint này sinh ra để lấp.
    """
    try:
        return {"ok": True, **_viec_nen_view(brain, chat_id)}
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)


async def _canh_bao_hua_suong(brain: str, chat_id: str, final_text: str,
                              runtime_trace=None) -> str:
    """Dòng sự thật khi Javis hứa "xong em báo" mà lượt đó KHÔNG có việc nền nào.

    Trả về chuỗi cảnh báo (rỗng = không cần cảnh báo). Người gọi quyết định dán vào đâu:
    dashboard đẩy thành một bong bóng riêng (câu trả lời đã stream xong từ lâu), Telegram nối
    thẳng vào cuối tin nhắn.

    KHÔNG chặn và KHÔNG sửa câu trả lời của model - chỉ nói thêm sự thật ở dưới.
    """
    mau = background_status.detect_promise(final_text or "")
    if not mau:
        return ""
    try:
        view = _viec_nen_view(brain, chat_id)
    except Exception:
        return ""    # không đọc được kho việc thì im, thà thiếu cảnh báo còn hơn cảnh báo sai
    if background_status.has_pending_work(view):
        return ""
    try:
        _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "promise.unbacked", {
            "pattern": mau, "orchestration": view.get("orchestration") or "",
            "background_count": view.get("count", 0),
        })
    except Exception:
        pass
    return background_status.promise_note(view.get("orchestration") or "")


@app.get("/lint")
async def lint(brain: str = Query("brain")):
    """LINT - health-check Wiki (chỉ đọc, không sửa). Trả danh sách 8 loại vấn đề."""
    cli = claude_engine(system_prompt=SYSTEM_PROMPT, cwd=_brain_root(brain), tag="lint",
                    allowed_tools=READONLY_TOOLS)
    _mcpf = _empty_mcp_file()
    if _mcpf:
        cli.mcp_config = _mcpf; cli.mcp_strict = True
    cli.disallowed_tools = ["Bash", "WebFetch", "WebSearch", "Task"]
    if not cli.is_available():
        return {"ok": False, "error": "Claude CLI chưa cài"}
    prompt = (
        "LINT - quét folder Wiki của vault, tìm 8 loại vấn đề: mâu thuẫn, stale claim, orphan page, "
        "missing page, broken wikilink, trùng lặp, gap (vùng kiến thức mỏng), open-question chưa lấp.\n"
        "CHỈ liệt kê DANH SÁCH CHECK ngắn gọn theo nhóm (không tự sửa). Mỗi mục 1 dòng. Tiếng Việt. "
        "Nếu Wiki sạch thì nói rõ."
    )
    final = ""
    async for ev in cli.query(prompt):
        if ev["type"] == "final":
            final = ev.get("content", "")
        elif ev["type"] == "error":
            return {"ok": False, "error": ev["content"][:200]}
    return {"ok": True, "report": final}


# ============================================================
# Trang Việc = loop (việc bền, chạy engine theo chu kỳ) + nhắc hẹn (việc phù du, 1 lần).
# KHÔNG có registry tay và KHÔNG có endpoint gộp: dashboard đọc thẳng hai nguồn thật là
# GET /loops và GET /reminders. Tab Lịch cũ (5 route /automations*) đã xoá vì nó chưa từng
# có executor - _scheduler_loop không đọc nó. Xem spec 2026-07-17-hop-nhat-viec-dinh-ky.
# ============================================================


# ============================================================
# JAVIS INDEX - chỉ mục tầng vận hành (agents/skills/workflows/loops/plugins).
# Song song wiki/index.md: để MỌI engine (Claude/Codex/OpenRouter) đọc 1 chỗ là hiểu Javis
# có năng lực gì. SINH TỪ FILE (không sửa tay) → không bao giờ lệch. Ghi Javis/index.md CHỈ KHI
# nội dung đổi (change-gated → không churn git). Bản LIVE gọn được chèn vào system prompt.
# ============================================================
def _gather_capabilities(brain: str, skills=None) -> dict:
    """skills: kết quả skill_router.list_skills(root) đã quét sẵn, để nơi gọi chia sẻ được
    một lần quét thay vì mỗi hàm tự đi lại cả cây. None = tự quét (đường cũ, vẫn đúng)."""
    root = Path(_brain_root(brain))
    caps = {"agents": [], "skills": [], "workflows": [], "loops": [], "plugins": []}
    ad = _agents_dir(brain)
    if ad.is_dir():
        for f in sorted(ad.glob("*.md")):
            m, _ = _read_md(f)
            caps["agents"].append({"slug": f.stem, "name": m.get("name", f.stem), "role": m.get("role", ""),
                                   "model": m.get("model", ""), "skills": m.get("skills", []) or []})
    wd = _workflows_dir(brain)
    if wd.is_dir():
        for f in sorted(wd.glob("*.md")):
            m, _ = _read_md(f)
            steps = m.get("steps", []) or []
            caps["workflows"].append({"slug": f.stem, "name": m.get("name", f.stem),
                                      "status": m.get("status", "active"), "description": m.get("description", ""),
                                      "agents": [s.get("agent") for s in steps if isinstance(s, dict)],
                                      "n_steps": len(steps)})
    # Skill: canonical <root>/skills + fallback .claude/skills + .agents (qua skill_router, de-dup).
    caps["skills"] = [{"slug": s["slug"], "name": s["name"], "description": s["description"],
                       "group": s["group"], "enabled": s["enabled"]}
                      for s in (skills if skills is not None else skill_router.list_skills(root))]
    try:
        st = loop_feature.read_state(brain)
        for lp in loop_feature.list_loops(brain):
            caps["loops"].append({"slug": lp["slug"], "name": lp["name"], "enabled": lp["enabled"],
                "mode": lp["mode"], "interval_min": lp["interval_min"], "goal": lp["goal"],
                "paused": bool(st.get(lp["slug"], {}).get("auto_paused_reason"))})
    except Exception:
        pass
    try:
        for p in plugins_host.describe(str(root)):
            caps["plugins"].append({"slug": p["slug"], "name": p["name"], "source": p["source"],
                "description": p["description"], "enabled": p["enabled"], "loaded": p["loaded"],
                "gated": p["gated"], "min_mode": p["min_mode"], "tools": p["tools"],
                "hooks": p["hooks"], "error": p["error"]})
    except Exception:
        pass
    return caps


def _render_javis_index(caps: dict) -> str:
    n_on_loops = sum(1 for l in caps["loops"] if l["enabled"])
    n_on_wf = sum(1 for w in caps["workflows"] if w["status"] == "active")
    plugins = caps.get("plugins", [])
    n_on_plugins = sum(1 for p in plugins if p.get("loaded"))
    L = ["# Javis Index (tầng vận hành)", "",
         "> Tự sinh từ file - ĐỪNG sửa tay. Chỉ mục mọi năng lực của Javis trong brain này để bất kỳ "
         "AI/engine đọc 1 chỗ là hiểu Javis làm được gì. Song song `wiki/index.md` (tri thức).", "",
         f"**Tổng quan:** {len(caps['agents'])} agents · {len(caps['skills'])} skills · "
         f"{len(caps['workflows'])} workflows ({n_on_wf} bật) · {len(caps['loops'])} loops ({n_on_loops} bật) · "
         f"{len(plugins)} plugins ({n_on_plugins} chạy)", ""]
    L.append("## Agents")
    if caps["agents"]:
        for a in caps["agents"]:
            mdl = f" · model {a['model']}" if a["model"] else ""
            sk = f" · skills: {', '.join(a['skills'])}" if a["skills"] else ""
            L.append(f"- **{a['name']}** (`{a['slug']}`) - {a['role']}{mdl}{sk}")
    else:
        L.append("_(chưa có)_")
    L.append("\n## Skills")
    if caps["skills"]:
        by_group = {}
        for s in caps["skills"]:
            by_group.setdefault(s["group"], []).append(s)
        for g in sorted(by_group):
            L.append(f"### {g}")
            for s in by_group[g]:
                off = "" if s["enabled"] else " · [TẮT]"
                L.append(f"- **{s['name']}** (`{s['slug']}`){off} - {s['description']}")
    else:
        L.append("_(chưa có)_")
    L.append("\n## Workflows")
    if caps["workflows"]:
        for w in caps["workflows"]:
            L.append(f"- **{w['name']}** (`{w['slug']}`) - {w['status']} · {w['n_steps']} bước "
                     f"[{' -> '.join(x for x in w['agents'] if x)}]" + (f" · {w['description']}" if w["description"] else ""))
    else:
        L.append("_(chưa có)_")
    L.append("\n## Loops")
    if caps["loops"]:
        for l in caps["loops"]:
            stt = "⚠ tự tạm dừng" if l["paused"] else ("bật" if l["enabled"] else "tắt")
            L.append(f"- **{l['name']}** (`{l['slug']}`) - {stt} · {l['goal']}/{l['mode']} · mỗi {l['interval_min']} phút")
    else:
        L.append("_(chưa có)_")
    if plugins:
        L.append("\n## Plugins (tool/hook native cho mọi engine)")
        for p in plugins:
            if p.get("loaded"):
                stt = "chạy"
            elif p.get("gated"):
                stt = "⚠ chờ env JAVIS_ENABLE_USER_PLUGINS"
            elif p.get("error"):
                stt = "⚠ lỗi"
            else:
                stt = "tắt"
            extra = []
            if p.get("tools"):
                extra.append("tools: " + ", ".join(p["tools"]))
            if p.get("hooks"):
                extra.append("hooks: " + ", ".join(p["hooks"]))
            tail = (" · " + " · ".join(extra)) if extra else ""
            L.append(f"- **{p['name']}** (`{p['slug']}`) - {p['source']}/{stt}{tail}"
                     + (f" · {p['description']}" if p.get("description") else ""))
    # Cờ sức khoẻ (mini-LINT tầng vận hành)
    agent_slugs = {a["slug"] for a in caps["agents"]}
    used = {ag for w in caps["workflows"] for ag in w["agents"] if ag}
    missing = sorted({ag for w in caps["workflows"] for ag in w["agents"] if ag and ag not in agent_slugs})
    orphan = sorted(s for s in agent_slugs if s not in used)
    flags = []
    if missing:
        flags.append(f"- Workflow trỏ agent KHÔNG tồn tại: {', '.join(missing)}")
    if orphan:
        flags.append(f"- Agent chưa workflow nào dùng: {', '.join(orphan)}")
    dis_sk = [s["slug"] for s in caps["skills"] if not s["enabled"]]
    if dis_sk:
        flags.append(f"- Skill đang tắt: {', '.join(dis_sk)}")
    paused = [l["slug"] for l in caps["loops"] if l["paused"]]
    if paused:
        flags.append(f"- Loop tự tạm dừng (cần xem): {', '.join(paused)}")
    p_gated = [p["slug"] for p in plugins if p.get("gated")]
    if p_gated:
        flags.append(f"- Plugin bật nhưng bị chặn (đặt env JAVIS_ENABLE_USER_PLUGINS=true): {', '.join(p_gated)}")
    p_err = [p["slug"] for p in plugins if p.get("error")]
    if p_err:
        flags.append(f"- Plugin lỗi nạp: {', '.join(p_err)}")
    if flags:
        L.append("\n## Cờ sức khoẻ")
        L.extend(flags)
    return "\n".join(L) + "\n"


def rebuild_javis_index(brain: str) -> dict:
    """Dựng lại Javis/index.md từ file. Chỉ ghi KHI nội dung đổi (chống churn git)."""
    try:
        content = _render_javis_index(_gather_capabilities(brain))
        idx = Path(_brain_root(brain)) / "Javis" / "index.md"
        old = idx.read_text(encoding="utf-8") if idx.exists() else ""
        if old != content:
            idx.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_text(idx, content)
            return {"ok": True, "written": True}
        return {"ok": True, "written": False}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _javis_capability_summary(brain: str, skills=None) -> str:
    """Bản LIVE gọn (capped) chèn vào system prompt: để engine nào cũng biết Javis có gì.
    Skill nhiều -> chỉ đếm + nhóm (chi tiết ở Javis/index.md), tránh phình context.
    skills: cây skill đã quét sẵn, xem _gather_capabilities."""
    try:
        c = _gather_capabilities(brain, skills)
    except Exception:
        return ""
    if not any(c.values()):
        return ""
    parts = ["\n\n# === NĂNG LỰC JAVIS HIỆN CÓ (đọc `Javis/index.md` để biết chi tiết + trigger) ==="]
    if c["agents"]:
        parts.append("Agents: " + ", ".join(a["name"] for a in c["agents"][:30]))
    if c["skills"]:
        groups = sorted({s["group"] for s in c["skills"] if s["enabled"]})
        parts.append(f"Skills: {sum(1 for s in c['skills'] if s['enabled'])} kỹ năng (nhóm: {', '.join(groups[:12])})")
    if c["workflows"]:
        parts.append("Workflows: " + ", ".join(w["name"] for w in c["workflows"][:20] if w["status"] == "active"))
    if c["loops"]:
        parts.append("Loops: " + ", ".join(f"{l['name']}({'bật' if l['enabled'] else 'tắt'})" for l in c["loops"][:20]))
    live_plugins = [p for p in c.get("plugins", []) if p.get("loaded")]
    if live_plugins:
        tool_names = [t for p in live_plugins for t in p.get("tools", [])]
        parts.append("Plugins đang chạy: " + ", ".join(p["name"] for p in live_plugins[:12])
                     + (f" (tool: {', '.join(tool_names[:12])})" if tool_names else ""))
    parts.append("Trước khi tạo năng lực mới, kiểm chỉ mục này để khỏi trùng.")
    return "\n".join(parts)


def _skill_router_block(brain: str, root: str, skills=None) -> str:
    """ROUTER SKILL đa-engine (chèn vào system prompt của MỌI engine). Liệt kê skill đang BẬT kèm
    mô tả (trigger) + chỉ rõ 2 cách nạp: tool javis_use_skill (engine API có tool) HOẶC mở thẳng
    file SKILL.md bằng công cụ đọc file (Claude/Codex - dùng ĐƯỜNG DẪN TUYỆT ĐỐI vì cwd có thể là
    /app). Đây là thứ giúp skill chạy trên cả ChatGPT/Codex, không phụ thuộc cơ chế native của Claude.
    Cap skill_router.SKILL_LIST_MAX để không phình context (nhiều hơn → trỏ Javis/index.md).
    skills: cây skill đã quét sẵn (list_skills), lọc tại chỗ thay vì quét lại - xem
    _gather_capabilities. None = tự quét (đường cũ)."""
    metas = ([s for s in skills if s.get("enabled")] if skills is not None
             else skill_router.list_enabled_meta(root))
    if not metas:
        return ""
    sk_dir = skill_router.skills_base(root, canonical=True)
    lines = ["\n\n# === SKILL KHẢ DỤNG (router - dùng được trên MỌI engine) ==="]
    cap = skill_router.SKILL_LIST_MAX
    for s in metas[:cap]:
        desc = (s.get("description") or "").replace("\n", " ")[:skill_router.SKILL_DESC_MAX]
        lines.append(f"- {s['slug']} ({s['name']}): {desc}")
    if len(metas) > cap:
        lines.append(f"…(+{len(metas) - cap} skill nữa - xem `Javis/index.md`)")
    lines.append(
        "CÁCH DÙNG: khi yêu cầu của user KHỚP mô tả 1 skill ở trên, hãy NẠP skill đó rồi LÀM THEO - "
        "gọi tool `javis_use_skill(name=<slug>)` nếu engine có tool này; nếu không, mở file "
        f"`{sk_dir}/<slug>/SKILL.md` bằng công cụ đọc file rồi tuân theo hướng dẫn trong đó. "
        "Chỉ nạp khi thực sự khớp, không nạp tràn lan."
    )
    return "\n".join(lines)


@app.get("/javis/index")
async def javis_index(brain: str = Query("brain")):
    """Dựng lại + trả nội dung Javis/index.md (chỉ mục tầng vận hành)."""
    rebuild_javis_index(brain)
    idx = Path(_brain_root(brain)) / "Javis" / "index.md"
    return {"ok": True, "content": idx.read_text(encoding="utf-8") if idx.exists() else "",
            "counts": {k: len(v) for k, v in _gather_capabilities(brain).items()}}


# ============================================================
# PLUGINS - tool/hook native cho MỌI engine (port ý tưởng plugin của Hermes).
# Plugin = thư mục Python (plugin.yaml + plugin.py với register(ctx)) thả vào 1 trong 3 nơi:
#   - bundled  <project>/system/plugins/<slug>/     (ship theo app, tin cậy)
#   - user     <JAVIS_STATE_DIR>/plugins/<slug>/    (TOÀN CỤC - chung MỌI brain; nơi cài mặc định)
#   - vault    <brain>/plugins/<slug>/              (riêng 1 brain)
# user + vault chạy code thật → CHỈ nạp khi env JAVIS_ENABLE_USER_PLUGINS=true (alias cũ *_VAULT_*).
# ============================================================
@app.post("/image/generate")
async def image_generate(prompt: str = Form(...), aspect_ratio: str = Form("square"),
                         quality: str = Form("medium"), brain: str = Form("brain")):
    """Tạo ảnh bằng gói ChatGPT (OAuth) → lưu vào attachments/ của vault. Cho UI/gọi trực tiếp;
    engine LLM dùng tool javis_generate_image (plugin image-chatgpt). Trả rel_path để nhúng ![](...)."""
    res = await image_gen.generate_chatgpt(prompt, aspect_ratio, quality, vault_root=_brain_root(brain))
    return JSONResponse(res, status_code=200 if res.get("ok") else 400)


@app.get("/plugins")
async def plugins_list(brain: str = Query("brain")):
    """Liệt kê MỌI plugin (bundled + vault) kèm trạng thái bật/nạp/gated/lỗi. KHÔNG chạy code plugin."""
    root = _brain_root(brain)
    items = plugins_host.describe(root)
    return {"ok": True, "user_gate": plugins_host._env_user_enabled(),
            "global_dir": str(plugins_host.global_plugins_dir()),
            "vault_dir": str(plugins_host.vault_plugins_dir(root) or ""), "plugins": items}


@app.post("/plugins/toggle")
async def plugins_toggle(slug: str = Form(...), enabled: str = Form(...), brain: str = Form("brain")):
    """Bật/tắt 1 plugin. Bundled → ghi STATE_DIR/plugins.json (không đụng file app); vault → ghi
    frontmatter plugin.yaml. Làm mới cache hub để tool xuất hiện/biến mất ngay."""
    if not plugins_host.valid_slug(slug):
        return JSONResponse({"error": "slug không hợp lệ"}, status_code=400)
    want = enabled in ("1", "true", "True", "on")
    res = plugins_host.set_enabled(slug, want, _brain_root(brain))
    if not res.get("ok"):
        return JSONResponse({"error": res.get("error", "lỗi")}, status_code=400)
    mcp_hub.invalidate_cache()   # tool builtin/plugin nằm trong route cache của hub → phải làm mới
    try:
        rebuild_javis_index(brain)
    except Exception:
        pass
    return res


# Mốc lần dọn media gần nhất. Dùng list 1 phần tử để hàm lồng bên trong _scheduler_loop
# gán được mà không cần `global`. Khởi tạo 0.0 -> chạy ngay ở tick đầu sau khi server lên.
_MEDIA_GC_LAST = [0.0]


@app.on_event("startup")
async def _start_scheduler():
    # Bootstrap bảo mật cho deploy public: (1) tạo admin từ env nếu có; (2) nếu vẫn chưa có admin
    # mà đang public → in MÃ THIẾT LẬP ra log để chính chủ tạo tài khoản (chống kẻ chỉ-có-URL chiếm admin).
    import sys as _sys
    _migrate_legacy_brain()   # dữ liệu brain cũ → <BRAINS_DIR>/Brain Default (không mất data)
    _ensure_default_brain()   # brain mặc định có sẵn cấu trúc chuẩn (ghi được trên mount /brains)
    _sync_system_all_brains() # năng lực hệ thống → mọi brain (update theo phiên bản app)
    # 0.9.251: gỡ hẳn listener Zalo cũ. Nó từng tự tắt connector MCP để giữ riêng socket,
    # nên khi nâng cấp phải bật trả connector về rồi xoá cấu hình listener; nếu không user
    # nối tài khoản rồi mà model vẫn không thấy các tool zalo_* để gửi trực tiếp.
    try:
        _legacy_cfg = cfgmod.read_settings()
        _legacy_zalo = _legacy_cfg.pop("zalo_listener", None)
        if isinstance(_legacy_zalo, dict):
            _legacy_conn = str(_legacy_zalo.get("conn_id") or "")
            if _legacy_conn and _legacy_zalo.get("conn_was_enabled"):
                mcp_store.update_connection(_legacy_conn, {"enabled": True})
            cfgmod.write_settings(_legacy_cfg)
            mcp_hub.invalidate_cache()
    except Exception as e:
        print(f"[zalo mcp migrate] {e}", file=_sys.stderr)
    try:
        _record_boot_version(_read_version())   # duy trì last_good/previous cho tính năng lùi bản
    except Exception:
        pass
    cfgmod.apply_tool_env()   # secret Cài đặt (key ElevenLabs...) → env cho tool ngoài (video-use)
    try:
        loop_feature.ensure_migrated()   # loop_config.json cũ → Javis/loops/vong-lap-goc.md (1 lần)
    except Exception as e:
        print(f"[loops migrate] {e}", file=_sys.stderr)
    try:
        # Dispatcher có vòng lặp riêng, không chặn cron/nhắc hẹn khi một worker chạy lâu.
        tasks_feature.start()
    except Exception as e:
        print(f"[kanban start] {e}", file=_sys.stderr)
    try:
        connect_health.on_engine_down = _loop_notify   # đèn báo não → Telegram, chỉ 1 lần mỗi đợt chết
        connect_health.start()   # vòng check sức khoẻ kết nối + probe đèn báo não
    except Exception as e:
        print(f"[connect health start] {e}", file=_sys.stderr)
    try:
        if cfgmod.provision_admin_from_env():
            print("[auth] Đã tạo tài khoản admin từ JAVIS_ADMIN_PASSWORD (env).", file=_sys.stderr)
        if cfgmod.setup_token_required():
            _tok = cfgmod.get_or_create_setup_token()
            print("\n" + "=" * 66 +
                  "\n  [BẢO MẬT] Javis chạy PUBLIC, CHƯA có tài khoản admin."
                  "\n  Mở app → màn tạo tài khoản sẽ hỏi MÃ THIẾT LẬP dưới đây:"
                  f"\n      SETUP TOKEN:  {_tok}"
                  "\n  (Chỉ người xem được log/terminal này tạo được admin. Hoặc đặt"
                  "\n   JAVIS_ADMIN_PASSWORD env để tạo sẵn admin, khỏi cần mã.)\n" +
                  "=" * 66 + "\n", file=_sys.stderr)
    except Exception as e:
        print(f"[auth bootstrap] {e}", file=_sys.stderr)
    async def _scheduler_loop():
        while True:
            try:
                await asyncio.sleep(30)
                # 1) Multi-loop tự cải thiện: mỗi tick chọn TỐI ĐA 1 loop đến hạn
                #    (quá hạn lâu nhất), chạy tuần tự qua lock toàn cục.
                try:
                    await loop_feature.tick()
                except Exception as lpe:
                    print(f"[loop tick] {type(lpe).__name__}: {lpe}", file=__import__('sys').stderr)
                # 2) Engine tự học: debounce tick (rewire sau lượt) + curator định kỳ
                try:
                    await learn_feature.tick()
                    await learn_feature.curator_tick()
                except Exception as le:
                    print(f"[learn tick] {type(le).__name__}: {le}", file=__import__('sys').stderr)
                # 3) Kanban: chỉ đánh thức dispatcher riêng. Không await model run tại đây.
                try:
                    await tasks_feature.tick()
                except Exception as te:
                    print(f"[kanban tick] {type(te).__name__}: {te}", file=__import__('sys').stderr)
                # 3b) Nhắc hẹn từ chat: tới giờ → bắn Telegram (mode task: chạy engine rồi báo)
                try:
                    await reminders_feature.tick()
                except Exception as rte:
                    print(f"[reminders tick] {type(rte).__name__}: {rte}", file=__import__('sys').stderr)
                # 3c) Ngân sách token + báo cáo tuần. Nhịp RIÊNG 10 phút chứ không theo 30s:
                #     mỗi lượt kiểm là một truy vấn sqlite cả tháng, chạy 30 giây một lần thì
                #     chính cái đồng hồ đo tiền lại thành thứ tốn tài nguyên nhất.
                try:
                    if time.time() - _NGAN_SACH_LAST[0] >= 600:
                        _NGAN_SACH_LAST[0] = time.time()
                        await _kiem_ngan_sach(nhac=True)
                        await _bao_cao_tuan_neu_toi_gio()
                except Exception as nse:
                    print(f"[ngan sach tick] {type(nse).__name__}: {nse}", file=__import__('sys').stderr)
                # 4) Đồng bộ GitHub tự động (2 CHIỀU): đủ interval → kéo về + hoà nhập + đẩy lên
                try:
                    bcfg = cfgmod.read_settings().get("backup", {}) or {}
                    if bcfg.get("enabled") and bcfg.get("repo_url") and bcfg.get("token") and git_brain.has_git():
                        interval = max(1, int(bcfg.get("interval_hours", 6))) * 3600
                        if time.time() - float(bcfg.get("last_backup", 0)) >= interval:
                            await asyncio.to_thread(_do_backup)   # 1 lần: toàn bộ thư mục brains, 2 chiều
                except Exception as be:
                    print(f"[backup tick] {type(be).__name__}: {be}", file=__import__('sys').stderr)
                # 5) Javis index: dựng lại chỉ mục tầng vận hành (chỉ ghi khi đổi → không churn)
                try:
                    for _ib in loop_feature.scheduler_brains():
                        await asyncio.to_thread(rebuild_javis_index, _ib)
                except Exception as ie:
                    print(f"[javis index tick] {type(ie).__name__}: {ie}", file=__import__('sys').stderr)
                # 6) Dọn media quá hạn: attachments/ + inbox/ là VÙNG CACHE chứ không phải
                #    tri thức. Nhịp riêng 6 TIẾNG (không theo nhịp 30s của vòng lặp) vì đây là
                #    quét đĩa, và to_thread vì quét đồng bộ trong event loop từng làm container
                #    unhealthy tới mức Traefik gỡ route. Đặt mốc TRƯỚC khi chạy: lỡ có hỏng thì
                #    đợi lượt sau chứ không quay vòng nóng.
                try:
                    if time.time() - _MEDIA_GC_LAST[0] >= 6 * 3600:
                        _MEDIA_GC_LAST[0] = time.time()
                        mcfg = cfgmod.read_settings().get("media", {}) or {}
                        if mcfg.get("enabled", True):
                            tuoi = int(mcfg.get("max_age_days", 30))
                            tran = int(mcfg.get("max_mb", 300))
                            for _mb in loop_feature.scheduler_brains():
                                kq = await asyncio.to_thread(media_gc.sweep, _mb, tuoi, tran)
                                if kq.get("files"):
                                    print(f"[media gc] {_mb}: dọn {kq['files']} tệp, "
                                          f"{kq['bytes'] // (1024 * 1024)}MB")
                            # Staging KHÔNG theo brain: nó là một thư mục dùng chung trong
                            # STATE_DIR, nên quét đúng một lần ngoài vòng lặp brain.
                            kqs = await asyncio.to_thread(media_gc.sweep_staging, str(STAGING),
                                                          int(mcfg.get("staging_days", 3)))
                            if kqs.get("files"):
                                print(f"[media gc] staging: dọn {kqs['files']} tệp, "
                                      f"{kqs['bytes'] // (1024 * 1024)}MB")
                except Exception as me:
                    print(f"[media gc] {type(me).__name__}: {me}", file=__import__('sys').stderr)
            except Exception as e:
                print(f"[scheduler] {type(e).__name__}: {e}", file=__import__('sys').stderr)
    asyncio.create_task(_scheduler_loop())
    try:
        restart_telegram()   # bật bot Telegram nếu đã cấu hình
    except Exception as e:
        print(f"[telegram start] {e}", file=__import__('sys').stderr)
    try:
        restart_zalo_bot()   # bật bot Zalo nếu đã cấu hình
    except Exception as e:
        print(f"[zalo start] {e}", file=__import__('sys').stderr)
    try:
        # Bot chuyên trách: nối bộ giám sát rồi bật những con đang để BẬT. Nối ở đây chứ không
        # để module tự import main - vòng import là thứ byte-compile không thấy, chỉ chết lúc
        # khởi động (xem bước "Import thật main" trong CI).
        chatbot_runtime.wire(answer=_tg_answer, brain_root=_brain_root,
                             read_agent=lambda b, slug: _read_md(_agents_dir(b) / f"{slug}.md"))
        kq = chatbot_runtime.sync_all()
        if kq.get("errors"):
            print(f"[chatbot] bật lỗi: {kq['errors']}", file=__import__('sys').stderr)
    except Exception as e:
        print(f"[chatbot start] {type(e).__name__}: {e}", file=__import__('sys').stderr)


_BROWSE_MD_CAP = 500        # trần đếm .md cho mỗi thư mục con
_BROWSE_HERE_CAP = 1000     # trần đếm .md ngay tại thư mục đang đứng
_BROWSE_DEPTH = 8           # tầng sâu tối đa khi đếm


def _count_md(root: str, cap: int) -> int:
    """Đếm file .md dưới root, có TRẦN THẬT: chạm cap là dừng ngay, không đi nốt cây.

    Bản cũ dùng `glob.glob(..., recursive=True)[:500]` - lát cắt chỉ áp lên KẾT QUẢ nên
    glob vẫn quét hết cây trước rồi mới cắt. Trên VPS (/home ôm cả brains lẫn dự án khác)
    một lần duyệt thư mục quét tới mức khoá cứng event loop, healthcheck bị bỏ đói, Docker
    gắn unhealthy và Traefik gỡ route: cả trang thành 404 dù app vẫn sống.

    Không đi theo symlink (symlink trỏ ngược lên cha làm glob recursive lặp vô tận), có
    trần độ sâu, và lỗi quyền ở một nhánh không giết cả lần đếm."""
    n = 0
    stack = [(root, 0)]
    while stack:
        cur, depth = stack.pop()
        try:
            with os.scandir(cur) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if depth < _BROWSE_DEPTH and not entry.name.startswith((".", "$")):
                                stack.append((entry.path, depth + 1))
                        elif entry.name.endswith(".md"):
                            n += 1
                            if n >= cap:
                                return n
                    except OSError:
                        continue        # entry hỏng (symlink gãy, mất quyền) → bỏ qua
        except OSError:
            continue                    # thư mục không đọc được → bỏ qua, đừng bỏ cả cây
    return n


def _browse_sync(path: str) -> dict:
    """Phần chạm đĩa của /browse. Tách hẳn ra để chạy trong thread, KHÔNG trên event loop."""
    import string

    if not path:
        if os.name == "nt":
            drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
            return {"path": "", "parent": None,
                    "dirs": [{"name": d, "path": d, "md": None} for d in drives]}
        path = os.path.expanduser("~")

    if not os.path.isdir(path):
        return {"error": "Không phải thư mục", "path": path, "parent": None, "dirs": []}

    try:
        dirs = []
        for name in sorted(os.listdir(path), key=str.lower):
            if name.startswith(".") or name.startswith("$"):
                continue
            full = os.path.join(path, name)
            if os.path.isdir(full):
                try:
                    md = _count_md(full, _BROWSE_MD_CAP)
                except Exception:
                    md = 0
                dirs.append({"name": name, "path": full, "md": md})
                if len(dirs) >= 300:
                    break               # đủ hiển thị rồi, đừng đếm tiếp cho phần bị cắt
        parent = os.path.dirname(path.rstrip("\\/")) or None
        if os.name == "nt" and parent and len(parent) <= 2:
            parent = ""  # về danh sách ổ đĩa
        here_md = _count_md(path, _BROWSE_HERE_CAP)
        return {"path": path, "parent": parent, "here_md": here_md, "dirs": dirs}
    except PermissionError:
        return {"error": "Không có quyền truy cập", "path": path, "parent": None, "dirs": []}
    except Exception as e:
        return {"error": str(e), "path": path, "parent": None, "dirs": []}


@app.get("/browse")
async def browse(path: str = Query("", description="Thư mục cần liệt kê; rỗng = ổ đĩa/gốc")):
    """Duyệt thư mục để chọn brain folder. Đếm số file .md trong mỗi folder con.

    Quét đĩa đẩy sang thread: dù thư mục có to tới đâu, event loop vẫn phục vụ được
    healthcheck và các request khác. Xem _count_md để biết vì sao (sự cố 404 trên VPS)."""
    return await asyncio.to_thread(_browse_sync, path)


@app.get("/path/exists")
async def path_exists(path: str = Query("", description="Đường dẫn tuyệt đối cần kiểm tra")):
    """Kiểm tra RẺ (chỉ os.path) 1 đường dẫn có còn là thư mục không. Dùng cho dropdown chọn
    brain dọn folder ngoài (📁) đã bị xoá khỏi ổ đĩa khỏi localStorage. Read-only, không liệt kê
    nội dung (khác /browse) nên nhẹ, gọi được cho nhiều entry lúc nạp trang."""
    p = (path or "").strip()
    if not p:
        return {"path": p, "exists": False, "is_dir": False}
    try:
        return {"path": p, "exists": os.path.exists(p), "is_dir": os.path.isdir(p)}
    except Exception:
        # Lỗi truy cập (path lạ/ổ đĩa rút) → coi như KHÔNG xác định được, báo exists=None để
        # frontend GIỮ entry (không tự xoá khi chưa chắc chắn là đã mất).
        return {"path": p, "exists": None, "is_dir": None}


@app.get("/config")
async def config():
    s = cfgmod.read_settings()
    return {
        "workspace_name": s.get("workspace_name") or os.getenv("WORKSPACE_NAME", "Javis OS"),
        "user_name": os.getenv("USER_NAME", "Bạn"),
        "tts_voice": os.getenv("TTS_VOICE", "vi-VN-HoaiMyNeural"),
        "tts_rate": os.getenv("TTS_RATE", "+5%"),
    }


# ============================================
# Phiên bản + cập nhật trong UI
# ============================================
GITHUB_REPO = "blogminhquy/javis-os"
_UPDATE_TASKS = set()   # giữ ref mạnh cho asyncio.create_task (tránh GC nuốt mất task)


def _read_version() -> str:
    try:
        p = PROJECT_ROOT / "VERSION"
        if p.exists():
            return (p.read_text(encoding="utf-8").strip() or "0.0.0")
    except Exception:
        pass
    return "0.0.0"


def _deploy_mode() -> str:
    """docker | windows | native - quyết định cách cập nhật."""
    if os.path.exists("/.dockerenv") or os.getenv("JAVIS_STATE_DIR", "").startswith("/data"):
        return "docker"
    if os.name == "nt":
        return "windows"
    return "native"


def _host_platform() -> str:
    """windows | mac | linux - nền tảng thật của máy (để UI ghi đúng nhãn, vd Mac
    cũng là mode 'native' nhưng không có systemd)."""
    import sys as _s
    if os.name == "nt":
        return "windows"
    return "mac" if _s.platform == "darwin" else "linux"


def _is_git_checkout(root: str) -> bool:
    try:
        import subprocess
        r = subprocess.run(["git", "-C", root, "rev-parse", "--is-inside-work-tree"],
                           capture_output=True, text=True, timeout=10,
                           creationflags=winproc.no_window())
        return r.returncode == 0 and "true" in (r.stdout or "").lower()
    except Exception:
        return False


async def _watchtower_reachable() -> bool:
    """True nếu container Watchtower (profile 'update') đang CHẠY và mở cổng API.
    Chỉ có ý nghĩa ở mode docker (host 'watchtower' trên mạng nội bộ compose). Biến env
    WATCHTOWER_TOKEN luôn được set sẵn trong compose nên KHÔNG đủ để kết luận - phải dò thật.
    Dò bằng cách MỞ KẾT NỐI TCP tới cổng, TUYỆT ĐỐI không gửi HTTP: endpoint /v1/update của
    Watchtower bị kích hoạt update kể cả với GET, nên một request 'thăm dò' sẽ trigger nhầm."""
    return await _watchtower_ly_do() == ""


async def _watchtower_ly_do() -> str:
    """"" = Watchtower đang chạy, tự cập nhật được. Khác rỗng = MÃ LÝ DO vì sao không.

    Vì sao cần mã lý do chứ không chỉ True/False: chủ repo báo (2026-08-12) rằng "một số máy
    VPS không có nút update, không hiểu vì sao". Cả hai lý do dưới đây đều là HÀNH VI ĐÚNG
    theo thiết kế, nhưng app trước nay gộp chúng vào một câu chung chung nên nhìn hệt như máy
    hỏng - và không có cách nào tự biết máy mình thiếu gì.

    - no_token: WATCHTOWER_TOKEN không được set. Đây là stack Hostinger, nơi CỐ TÌNH không
      kèm Watchtower (nó không đụng được Docker socket, bị Restarting liên tục). Đường cập
      nhật ở đây là Redeploy, không có gì để bật thêm.
    - watchtower_off: token có (docker-compose.yml luôn đặt sẵn) nhưng không nối được tới
      container. Gần như luôn là vì Watchtower nằm trong `profiles: ["update"]`, tức là
      `docker compose up -d` KHÔNG bật nó. Đây mới là trường hợp bật được, và bật bằng đúng
      một lệnh - nên phải nói ra lệnh đó.
    """
    if not os.getenv("WATCHTOWER_TOKEN", ""):
        return "no_token"
    import asyncio
    writer = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("watchtower", 8080), timeout=4)
        return ""     # bắt tay TCP xong = container Watchtower đang lắng nghe
    except Exception:
        return "watchtower_off"   # không phân giải host / connection refused = không chạy
    finally:
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass


@app.get("/version")
async def version_info():
    cur = _read_version()
    latest, err = None, None
    try:
        import httpx
        url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/VERSION"
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(url)
            if r.status_code == 200:
                latest = (r.text or "").strip() or None
            else:
                err = f"VERSION chưa có trên nhánh main (HTTP {r.status_code})"
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    mode = _deploy_mode()
    avail = _ver_newer(latest, cur)
    # docker: chỉ tự cập nhật tại chỗ được nếu Watchtower ĐANG chạy (ping thật). Không có →
    # frontend chuyển sang hướng dẫn REDEPLOY. native/windows: git pull tự lo.
    ly_do = await _watchtower_ly_do() if mode == "docker" else ""
    can = mode in ("native", "windows") or (mode == "docker" and ly_do == "")
    st = _read_update_state()
    # self_update_off: mã lý do để UI nói ĐÚNG máy này thiếu gì thay vì một câu chung chung.
    # Rỗng khi tự cập nhật được - frontend chỉ đọc nó ở nhánh không có nút.
    return {"current": cur, "latest": latest, "update_available": avail,
            "mode": mode, "platform": _host_platform(), "can_self_update": can, "error": err,
            "self_update_off": ly_do, "previous_version": st.get("previous_version")}


@app.get("/update/status")
async def update_status():
    """Trạng thái cập nhật (UI poll để vẽ tiến trình). Đọc update_state.json + ~50 dòng cuối
    update.log. File sống qua restart nên sau khi server lên lại vẫn báo được kết quả."""
    st = _read_update_state()
    tail = ""
    try:
        logf = cfgmod.STATE_DIR / "update.log"
        if logf.exists():
            lines = logf.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = "\n".join(lines[-50:])
    except Exception:
        tail = ""
    return {"state": st, "log_tail": tail}


_UPDATE_ACTIVE = {"preparing", "pulling", "installing", "restarting", "health_check", "rolling_back"}


def _update_recent(started_at, window_s=900) -> bool:
    """True nếu lần cập nhật đang dở BẮT ĐẦU gần đây (trong window ~15 phút). Guard chỉ chặn khi
    THỰC SỰ đang chạy; phase 'đang dở' còn sót từ lần cũ (docker để 'restarting' vĩnh viễn, updater
    chết giữa chừng, máy reboot) thì coi là cũ và CHO chạy lại. Khớp spec: 'phase đang dở VÀ started_at gần đây'.
    started_at thiếu/hỏng -> coi là cũ (fail-open, tránh brick nút update)."""
    if not started_at:
        return False
    try:
        import datetime as _dt
        return (_dt.datetime.now() - _dt.datetime.fromisoformat(started_at)).total_seconds() < window_s
    except Exception:
        return False


def _git_head(root: str) -> str:
    try:
        import subprocess
        r = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=10,
                           creationflags=winproc.no_window())
        return (r.stdout or "").strip() if r.returncode == 0 else ""
    except Exception:
        return ""


@app.post("/update")
async def do_update():
    """Cập nhật lên bản mới nhất. Git checkout (windows/native) → spawn updater.py TÁCH RỜI
    (stop/pull/pip/start/health/rollback). Docker → Watchtower nếu có, không thì hướng dẫn Redeploy."""
    import sys as _sys
    import subprocess
    import datetime as _dt
    now = lambda: _dt.datetime.now().isoformat(timespec="seconds")

    st = _read_update_state()
    if st.get("phase") in _UPDATE_ACTIVE and _update_recent(st.get("started_at")):
        return JSONResponse({"ok": False, "error": "Đang cập nhật rồi, chờ chút.",
                             "phase": st.get("phase")}, status_code=409)

    # Claim NGAY sau guard (KHÔNG có await ở giữa → nguyên tử với event loop) để chặn double-click:
    # request thứ 2 đọc phase="preparing" (thuộc _UPDATE_ACTIVE) sẽ bị 409.
    _write_update_state({"phase": "preparing", "result": None, "error": None,
                         "old_version": None, "old_sha": None, "target_version": None,
                         "started_at": now(), "finished_at": None})

    mode = _deploy_mode()
    cur = _read_version()
    latest = None
    try:
        import httpx
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/VERSION")
            if r.status_code == 200:
                latest = (r.text or "").strip() or None
    except Exception:
        latest = None

    if mode == "docker":
        if not await _watchtower_reachable():
            _write_update_state({"phase": "idle"})   # nhả claim, không kẹt "preparing"
            return JSONResponse({"ok": False,
                "error": "Bản Docker cập nhật bằng REDEPLOY để kéo image mới: trên Hostinger bấm Redeploy trong Docker Manager; trên VPS chạy lệnh dưới. Nếu bản mới lỗi, pin tag phiên bản cũ rồi Redeploy để lùi.",
                "manual": "docker compose up -d --pull always",
                "current": cur, "latest": latest,
                "previous_version": st.get("previous_version")}, status_code=400)
        token = os.getenv("WATCHTOWER_TOKEN", "")
        _write_update_state({"phase": "restarting", "old_version": cur, "target_version": latest,
                             "old_sha": None, "result": None, "error": None, "stashed": False,
                             "started_at": now(), "finished_at": None})
        import asyncio
        import httpx

        async def _trigger():
            try:
                async with httpx.AsyncClient(timeout=180) as client:
                    await client.post("http://watchtower:8080/v1/update",
                                      headers={"Authorization": f"Bearer {token}"})
            except Exception as e:
                print(f"[update] watchtower trigger: {e}", file=_sys.stderr)
        t = asyncio.create_task(_trigger())
        _UPDATE_TASKS.add(t)
        t.add_done_callback(_UPDATE_TASKS.discard)
        return {"ok": True, "mode": "docker", "message": "Đang kéo image mới + khởi động lại (~20-40s)."}

    # git checkout (windows / native)
    root = str(PROJECT_ROOT)
    if not _is_git_checkout(root):
        _write_update_state({"phase": "idle"})   # nhả claim, không kẹt "preparing"
        return JSONResponse({"ok": False,
            "error": "Thư mục cài đặt không phải git checkout → không tự cập nhật được. Cài lại bằng 'git clone' hoặc cập nhật thủ công.",
            "manual": "./update.sh"}, status_code=400)
    old_sha = _git_head(root)
    _write_update_state({"phase": "preparing", "old_version": cur, "old_sha": old_sha,
                         "target_version": latest, "result": None, "error": None, "stashed": False,
                         "started_at": now(), "finished_at": None})
    try:
        py = _sys.executable
        updater = str(PROJECT_ROOT / "server" / "updater.py")
        port = os.getenv("JAVIS_PORT", "7777")
        args = [py, updater, "--old-sha", old_sha, "--old-version", cur,
                "--target", latest or "", "--port", str(port),
                "--server-pid", str(os.getpid())]
        if mode == "windows":
            subprocess.Popen(args, cwd=root, creationflags=0x00000008 | 0x00000200)  # DETACHED|NEW_GROUP
        else:
            subprocess.Popen(args, cwd=root, start_new_session=True)
        return {"ok": True, "mode": mode,
                "message": "Đang cập nhật + khởi động lại (theo dõi ở thanh tiến trình)."}
    except Exception as e:
        _write_update_state({"phase": "error", "result": "error", "error": str(e), "finished_at": now()})
        return JSONResponse({"ok": False, "error": str(e), "manual": "./update.sh"}, status_code=500)


# ============================================================
# Tự khởi động cùng máy (autostart) - Windows: ghi HKCU Run key trỏ wscript chạy
# start-javis.vbs (đã tự tắt bản cũ + chạy NỀN ẩn). Per-user, KHÔNG cần quyền admin.
# Registry là nguồn sự thật duy nhất - không lưu trùng vào settings.json.
# ============================================================
_AUTOSTART_NAME = "JavisOS"
_AUTOSTART_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
# Task Manager tab "Startup" KHÔNG xoá mục trong Run key khi người dùng bấm Disable. Nó ghi
# một cờ 12 byte vào khoá riêng dưới đây, rồi Explorer bỏ qua mục đó lúc đăng nhập.
#
# Đây là kiểu hỏng tệ nhất của cả tính năng: Run key còn nguyên nên `/autostart` báo "Bật",
# người dùng nhìn dashboard thấy đúng, mà mở máy lên thì không có gì chạy và không có một
# dòng lỗi nào ở đâu cả. Mấy phần mềm "dọn máy, tăng tốc khởi động" cũng tắt bằng đúng cờ này.
_AUTOSTART_APPROVED_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run")
# Byte đầu: 2 hoặc 6 = đang bật, 3 = đã tắt. Xét theo BIT 0 chứ không so bằng, vì các byte còn
# lại là dấu thời gian và Windows có dùng vài giá trị khác nhau cho trạng thái bật.
_AUTOSTART_APPROVED_ON = bytes([2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])


def _autostart_command() -> str:
    """Lệnh chạy khi đăng nhập Windows: wscript chạy start-javis.vbs ẩn (kill cũ + chạy nền)."""
    vbs = str(PROJECT_ROOT / "start-javis.vbs")
    return f'wscript.exe //nologo "{vbs}"'


def _autostart_bi_chan(raw) -> bool:
    """Cờ StartupApproved nói mục này đã bị tắt trong Task Manager?"""
    try:
        return bool(raw) and bool(raw[0] & 1)
    except (TypeError, IndexError):
        return False


def _autostart_thieu_gi(root=None) -> list:
    """Mảnh nào của dây chuyền khởi động không còn trên đĩa.

    Thiếu một trong hai là lúc đăng nhập chắc chắn không có gì chạy, mà cũng chẳng có lỗi nào
    hiện ra: `wscript` im lặng khi không thấy file .vbs, còn `cmd` thì ghi lỗi vào javis.log,
    một file không ai mở ra xem bao giờ. Kiểm ngay lúc đọc trạng thái thì rẻ hơn nhiều.
    """
    goc = Path(root) if root else PROJECT_ROOT
    thieu = []
    if not (goc / "start-javis.vbs").is_file():
        thieu.append("start-javis.vbs")
    if not (goc / ".venv" / "Scripts" / "python.exe").is_file():
        thieu.append(r".venv\Scripts\python.exe")
    return thieu


def _autostart_ly_do(st: dict) -> str:
    """Một câu nói thẳng vì sao autostart sẽ KHÔNG chạy, hoặc '' nếu mọi thứ ổn.

    Tính ở server chứ không ở dashboard: cùng một trạng thái đang hiện ở hai trang (Tổng quan
    và Cài đặt), và luật kiểu này viết hai bản thì sớm muộn hai bản nói khác nhau.
    """
    if not st.get("enabled"):
        return ""
    if st.get("blocked"):
        return ("Windows đang chặn mục khởi động này (ai đó tắt nó trong Task Manager, thẻ "
                "Startup, hoặc một phần mềm dọn máy đã tắt hộ). Bấm bật lại để gỡ chặn.")
    if st.get("stale"):
        return ("Thư mục cài đặt đã đổi chỗ nên lệnh khởi động đang trỏ vào đường dẫn cũ. "
                "Bấm bật lại để cập nhật.")
    if st.get("missing"):
        return ("Thiếu " + ", ".join(st["missing"]) + " trong thư mục cài đặt nên lúc đăng nhập "
                "sẽ không có gì chạy. Chạy lại setup.bat để dựng lại phần thiếu.")
    return ""


def _autostart_status() -> dict:
    """Trạng thái ĐẦY ĐỦ của autostart, đủ để nói vì sao nó không chạy.

    `enabled` một mình không trả lời được câu hỏi thật của người dùng ("sao mở máy lên không
    thấy Javis"): Run key còn nguyên vẫn có ba đường chết lặng khác nhau, và cả ba đều được
    kiểm ở đây - Windows chặn, đường dẫn cũ, hoặc file đã mất.
    """
    if os.name != "nt":
        return {"supported": False, "enabled": False}
    expected = _autostart_command()
    st = {"supported": True, "enabled": False, "expected": expected,
          "log": str(PROJECT_ROOT / "server" / "javis.log")}
    try:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_RUN_KEY) as k:
                val, _ = winreg.QueryValueEx(k, _AUTOSTART_NAME)
            st["enabled"] = bool(val)
            st["command"] = val
            st["stale"] = bool(val) and val.strip() != expected
        except FileNotFoundError:
            pass
        if st["enabled"]:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_APPROVED_KEY) as k:
                    raw, _ = winreg.QueryValueEx(k, _AUTOSTART_NAME)
                st["blocked"] = _autostart_bi_chan(raw)
            except FileNotFoundError:
                st["blocked"] = False     # không có cờ nghĩa là chưa ai tắt
            st["missing"] = _autostart_thieu_gi()
    except Exception as e:
        st["error"] = str(e)
    st["ly_do"] = _autostart_ly_do(st)
    st["healthy"] = bool(st["enabled"]) and not st["ly_do"]
    return st


def _autostart_set(enabled: bool) -> dict:
    if os.name != "nt":
        return {"ok": False, "error": "Chỉ hỗ trợ trên Windows"}
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_RUN_KEY) as k:
            if enabled:
                winreg.SetValueEx(k, _AUTOSTART_NAME, 0, winreg.REG_SZ, _autostart_command())
            else:
                try:
                    winreg.DeleteValue(k, _AUTOSTART_NAME)
                except FileNotFoundError:
                    pass
        if enabled:
            # Ghi lại Run key KHÔNG gỡ được cờ chặn của Task Manager, nên bật xong vẫn không
            # chạy và nút bấm thành ra vô nghĩa. Chỉ lật cờ đã có sẵn của CHÍNH mục này, không
            # tự tạo mới: không có cờ đã là đang bật rồi.
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_APPROVED_KEY,
                                    0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
                    try:
                        raw, _ = winreg.QueryValueEx(k, _AUTOSTART_NAME)
                    except FileNotFoundError:
                        raw = None
                    if _autostart_bi_chan(raw):
                        winreg.SetValueEx(k, _AUTOSTART_NAME, 0, winreg.REG_BINARY,
                                          _AUTOSTART_APPROVED_ON)
            except FileNotFoundError:
                pass
        return {"ok": True, "enabled": enabled, **_autostart_status()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/autostart")
async def autostart_get():
    return _autostart_status()


@app.post("/autostart")
async def autostart_post(enabled: str = Form(...)):
    on = str(enabled).strip().lower() in ("1", "true", "on", "yes")
    return _autostart_set(on)


# ---- Nhật ký cập nhật (changelog) -------------------------------------------
_CL_VER_RE = re.compile(r"^##\s+\[?(\d+\.\d+\.\d+)\]?\s*[-:]?\s*(.*)$")
_CL_SEC_RE = re.compile(r"^###\s+(.+?)\s*$")
_CL_ITEM_RE = re.compile(r"^[-*]\s+(.+?)\s*$")


def _parse_changelog(md: str):
    """Parse CHANGELOG.md → [{version, date, sections:[{title, items:[...]}]}].
    Nhận khối '## [x.y.z] - ngày', mục '### Nhóm', dòng '- việc'."""
    releases, cur, sec = [], None, None
    for line in (md or "").splitlines():
        mv = _CL_VER_RE.match(line)
        if mv:
            cur = {"version": mv.group(1), "date": (mv.group(2) or "").strip(), "sections": []}
            releases.append(cur); sec = None; continue
        if cur is None:
            continue
        ms = _CL_SEC_RE.match(line)
        if ms:
            sec = {"title": ms.group(1).strip(), "items": []}
            cur["sections"].append(sec); continue
        mi = _CL_ITEM_RE.match(line)
        if mi and sec is not None:
            sec["items"].append(mi.group(1).strip())
    return releases


def _parse_announcements(raw: str):
    """Đọc ANNOUNCEMENTS.json an toàn.

    Nội dung từ GitHub là dữ liệu không tin cậy: chỉ giữ text thuần, URL http(s) và
    một tập kind/action nhỏ. Frontend tiếp tục escape trước khi render.
    """
    try:
        payload = json.loads(raw or "{}")
    except Exception:
        return []
    rows = payload.get("announcements", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []

    def text(value, limit):
        return str(value or "").strip()[:limit]

    today = time.strftime("%Y-%m-%d")
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item_id = text(row.get("id"), 120)
        title = text(row.get("title"), 180)
        if not item_id or not title or not re.fullmatch(r"[\w.:-]+", item_id, flags=re.UNICODE):
            continue
        expires = text(row.get("expires_at"), 32)
        if expires and expires[:10] < today:
            continue
        kind = text(row.get("kind"), 24).lower()
        if kind not in ("community", "marketing"):
            kind = "community"
        priority = text(row.get("priority"), 16).lower()
        if priority not in ("high", "normal", "low"):
            priority = "normal"
        cta_in = row.get("cta") if isinstance(row.get("cta"), dict) else {}
        cta = {}
        label = text(cta_in.get("label"), 80)
        action = text(cta_in.get("action"), 32).lower()
        url = text(cta_in.get("url"), 500)
        if label:
            cta["label"] = label
        if action == "changelog":
            cta["action"] = action
        if re.match(r"^https?://", url, flags=re.I):
            cta["url"] = url
        out.append({
            "id": item_id,
            "kind": kind,
            "title": title,
            "summary": text(row.get("summary"), 500),
            "body": text(row.get("body"), 3000),
            "published_at": text(row.get("published_at"), 32),
            "expires_at": expires,
            "priority": priority,
            "cta": cta,
        })
    return out


def _release_plain(value: str) -> str:
    """Thu gọn một bullet Markdown thành text cho thẻ thông báo."""
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", str(value or ""))
    return re.sub(r"[*_`#]", "", s).strip()


async def _load_community_announcements():
    """Local làm fallback; bản trên GitHub main ghi đè cùng id để phát tin không cần release."""
    by_id, err = {}, None
    local_path = PROJECT_ROOT / "ANNOUNCEMENTS.json"
    try:
        if local_path.exists():
            for item in _parse_announcements(local_path.read_text(encoding="utf-8")):
                by_id[item["id"]] = item
    except Exception:
        pass
    try:
        import httpx
        url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/ANNOUNCEMENTS.json"
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(url)
            if response.status_code == 200:
                for item in _parse_announcements(response.text):
                    by_id[item["id"]] = item
            else:
                err = f"HTTP {response.status_code}"
    except Exception as e:
        err = type(e).__name__
    return list(by_id.values()), err


async def changelog_index():
    """Lõi thuần của GET /changelog. Dùng chung với /notifications (gọi nội bộ)."""
    """Nhật ký cập nhật: đọc CHANGELOG.md trong bản đang cài + đối chiếu bản trên GitHub để
    nêu cả phiên bản mới chưa cài. Mất mạng vẫn trả được phần local (bản đã cài)."""
    cur = _read_version()
    p = PROJECT_ROOT / "CHANGELOG.md"
    local_md = ""
    try:
        if p.exists():
            local_md = p.read_text(encoding="utf-8")
    except Exception:
        local_md = ""
    by_ver = {rel["version"]: rel for rel in _parse_changelog(local_md)}
    err = None
    try:
        import httpx
        url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/CHANGELOG.md"
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(url)
            if r.status_code == 200:
                for rel in _parse_changelog(r.text):
                    by_ver.setdefault(rel["version"], rel)   # bản GitHub chưa có local = bản mới
    except Exception as e:
        err = type(e).__name__
    merged = sorted(by_ver.values(), key=lambda r: _ver_tuple(r["version"]) or (0, 0, 0), reverse=True)
    ct = _ver_tuple(cur) or (0, 0, 0)
    for rel in merged:
        vt = _ver_tuple(rel["version"]) or (0, 0, 0)
        rel["installed"] = vt <= ct
        rel["is_current"] = (vt == ct)
    latest = merged[0]["version"] if merged else None
    return {"current": cur, "latest": latest,
            "update_available": bool(_ver_newer(latest, cur)),
            "releases": merged, "error": err}


@app.get("/changelog")
async def changelog_info():
    return await changelog_index()


_NOTIFICATION_CACHE = {"at": 0.0, "data": None}


@app.get("/notifications")
async def notifications_info():
    """Hộp thư thống nhất: release tự động + tin cộng đồng/marketing từ GitHub main."""
    now = time.monotonic()
    cached = _NOTIFICATION_CACHE.get("data")
    if cached is not None and now - float(_NOTIFICATION_CACHE.get("at") or 0) < 120:
        return cached

    changelog_task = asyncio.create_task(changelog_index())
    announcements_task = asyncio.create_task(_load_community_announcements())
    changelog, (announcements, announcement_error) = await asyncio.gather(
        changelog_task, announcements_task
    )

    releases = []
    for rel in (changelog.get("releases") or [])[:30]:
        bullets = [
            _release_plain(item)
            for section in (rel.get("sections") or [])
            for item in (section.get("items") or [])
            if _release_plain(item)
        ]
        is_new = not bool(rel.get("installed"))
        is_current = bool(rel.get("is_current"))
        is_latest = str(rel.get("version") or "") == str(changelog.get("latest") or "")
        releases.append({
            "id": f"release:{rel.get('version')}",
            "kind": "update",
            "title": f"Javis OS v{rel.get('version')}",
            "summary": bullets[0] if bullets else "Bản cập nhật Javis OS mới.",
            "body": "\n".join(f"• {item}" for item in bullets[1:5]),
            "published_at": rel.get("date") or "",
            "priority": "high" if (is_current or (is_new and is_latest)) else "normal",
            "installed": bool(rel.get("installed")),
            "is_current": is_current,
            "update_available": is_new,
            "action": "changelog",
            "cta": {"label": "Xem chi tiết bản cập nhật →", "action": "changelog"},
        })

    priority_rank = {"high": 2, "normal": 1, "low": 0}
    items = announcements + releases
    items.sort(
        key=lambda item: (
            str(item.get("published_at") or ""),
            priority_rank.get(item.get("priority"), 1),
            str(item.get("id") or ""),
        ),
        reverse=True,
    )
    data = {
        "current": changelog.get("current"),
        "latest": changelog.get("latest"),
        "unified": True,
        "items": items[:60],
        "errors": {
            "changelog": changelog.get("error"),
            "announcements": announcement_error,
        },
    }
    _NOTIFICATION_CACHE.update({"at": now, "data": data})
    return data


# ============================================
# Branding - logo/avatar đổi được qua UI (lưu ở STATE_DIR/branding, giữ qua update).
# Trong Docker code tree read-only → KHÔNG ghi đè dashboard/logo.png; lưu ở volume state.
# ============================================
_LOGO_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_DEFAULT_LOGO = DASHBOARD_PATH / "logo.png"
_MAX_LOGO_BYTES = 5 * 1024 * 1024   # 5MB


def _current_logo_file():
    """File logo tùy chỉnh nếu có (theo branding.logo_ext), else None → dùng ảnh mặc định."""
    ext = (cfgmod.read_settings().get("branding", {}) or {}).get("logo_ext", "")
    if ext:
        p = cfgmod.BRANDING_DIR / f"logo{ext}"
        if p.exists():
            return p
    return None


@app.get("/brand-logo")
async def brand_logo():
    p = _current_logo_file() or _DEFAULT_LOGO
    if not p.exists():
        return JSONResponse({"error": "no logo"}, status_code=404)
    # cache ngắn: đổi ảnh xong thấy ngay trong ~1 phút; JS còn bust bằng ?v= khi vừa upload.
    return FileResponse(str(p), headers={"Cache-Control": "public, max-age=60"})


@app.get("/favicon.ico")
async def favicon_ico():
    """Favicon = logo hiện tại. Trình duyệt LUÔN tự gọi /favicon.ico và cache rất lì;
    trước đây route này trả 404 nên tab giữ icon cũ. Trả thẳng ảnh logo cho khớp app."""
    p = _current_logo_file() or _DEFAULT_LOGO
    if not p.exists():
        return JSONResponse({"error": "no favicon"}, status_code=404)
    media = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
             ".webp": "image/webp", ".gif": "image/gif"}.get(p.suffix.lower(), "image/png")
    return FileResponse(str(p), media_type=media, headers={"Cache-Control": "public, max-age=300"})


@app.post("/branding/logo")
async def branding_logo_set(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext == ".jpe":
        ext = ".jpg"
    if ext not in _LOGO_EXTS:
        return JSONResponse({"ok": False, "error": "Chỉ nhận ảnh PNG / JPG / WEBP / GIF"}, status_code=400)
    data = await file.read()
    if not data:
        return JSONResponse({"ok": False, "error": "File rỗng"}, status_code=400)
    if len(data) > _MAX_LOGO_BYTES:
        return JSONResponse({"ok": False, "error": "Ảnh quá lớn (tối đa 5MB)"}, status_code=400)
    try:
        cfgmod.BRANDING_DIR.mkdir(parents=True, exist_ok=True)
        for old in cfgmod.BRANDING_DIR.glob("logo.*"):   # xoá ảnh cũ mọi đuôi, tránh file thừa
            try:
                old.unlink()
            except Exception:
                pass
        (cfgmod.BRANDING_DIR / f"logo{ext}").write_bytes(data)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"Lưu ảnh thất bại: {e}"}, status_code=500)
    cfg = cfgmod.read_settings()
    cfg.setdefault("branding", {})
    cfg["branding"]["logo_ext"] = ext
    cfg["branding"]["logo_v"] = int(cfg["branding"].get("logo_v", 0) or 0) + 1
    cfgmod.write_settings(cfg)
    return {"ok": True, "logo_v": cfg["branding"]["logo_v"]}


@app.post("/branding/logo/reset")
async def branding_logo_reset():
    try:
        if cfgmod.BRANDING_DIR.exists():
            for old in cfgmod.BRANDING_DIR.glob("logo.*"):
                try:
                    old.unlink()
                except Exception:
                    pass
    except Exception:
        pass
    cfg = cfgmod.read_settings()
    cfg.setdefault("branding", {})
    cfg["branding"]["logo_ext"] = ""
    cfg["branding"]["logo_v"] = int(cfg["branding"].get("logo_v", 0) or 0) + 1
    cfgmod.write_settings(cfg)
    return {"ok": True}


# Tên miền riêng + HTTPS (Caddy On-Demand TLS) đã bóc sang routes/domain.py ở 0.9.243.
# Vị trí lời gọi register quyết định thứ tự route - xem routes/__init__.py.
import routes.domain as domain_routes   # noqa: E402
domain_routes.register(app, domain_routes.DomainDeps(deploy_mode=lambda: _deploy_mode()))


# ============================================
# TTS - Edge TTS (giọng Vietnamese chuẩn, miễn phí)
# ============================================
def _rate_to_speed(rate: str) -> float:
    """'+10%' / '-20%' → tốc độ 1.1 / 0.8 cho OpenAI (kẹp 0.25..4.0)."""
    try:
        pct = float((rate or "").strip().replace("%", ""))
        return max(0.25, min(4.0, 1.0 + pct / 100.0))
    except Exception:
        return 1.0


async def _tts_edge(text: str, voice: str, rate: str) -> bytes:
    import edge_tts   # lazy - xem ghi chú ở đầu file
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    buf = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.extend(chunk["data"])
    return bytes(buf)


async def _tts_openai(text: str, rate: str, cfg: dict) -> bytes:
    import httpx
    key = (cfg.get("model", {}) or {}).get("openai_api_key", "")
    if not key:
        raise RuntimeError("Chưa có OpenAI API key (đặt ở Models / Cài đặt).")
    v = cfg.get("voice", {}) or {}
    payload = {
        "model": v.get("openai_tts_model") or "gpt-4o-mini-tts",
        "voice": v.get("openai_tts_voice") or "alloy",
        "input": text, "response_format": "mp3", "speed": _rate_to_speed(rate),
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post("https://api.openai.com/v1/audio/speech",
                              headers={"Authorization": f"Bearer {key}"}, json=payload)
        r.raise_for_status()
        return r.content


async def _tts_elevenlabs(text: str, cfg: dict) -> bytes:
    import httpx
    v = cfg.get("voice", {}) or {}
    key = v.get("elevenlabs_key", "")
    if not key:
        raise RuntimeError("Chưa có ElevenLabs API key.")
    voice_id = v.get("elevenlabs_voice") or "21m00Tcm4TlvDq8ikWAM"
    payload = {"text": text, "model_id": v.get("elevenlabs_model") or "eleven_multilingual_v2"}
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, headers={"xi-api-key": key, "accept": "audio/mpeg"},
                              json=payload, params={"output_format": "mp3_44100_128"})
        r.raise_for_status()
        return r.content


@app.get("/tts")
async def tts(
    text: str = Query(...),
    voice: str = Query("vi-VN-HoaiMyNeural"),
    rate: str = Query("+5%"),
):
    """Sinh audio TTS theo nhà cung cấp đã chọn (edge/openai/elevenlabs). Provider trả phí lỗi
    → tự fallback về Edge TTS để giọng không bao giờ tắt hẳn."""
    import sys
    from fastapi import HTTPException, Response
    cfg = cfgmod.read_settings()
    provider = ((cfg.get("voice", {}) or {}).get("tts_provider") or "edge").lower()
    audio = b""
    try:
        if provider == "openai":
            audio = await _tts_openai(text, rate, cfg)
        elif provider == "elevenlabs":
            audio = await _tts_elevenlabs(text, cfg)
        else:
            audio = await _tts_edge(text, voice, rate)
    except Exception as e:
        print(f"[TTS {provider}] {type(e).__name__}: {e} - thử fallback Edge", file=sys.stderr)
        if provider != "edge":
            try:
                audio = await _tts_edge(text, voice, rate)
            except Exception as e2:
                raise HTTPException(502, f"TTS failed: {type(e2).__name__}: {e2}")
        else:
            raise HTTPException(502, f"TTS failed: {type(e).__name__}: {e}")
    if not audio:
        raise HTTPException(502, "TTS không trả audio.")
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-cache"})


@app.get("/tts/voices")
async def tts_voices(lang: str = Query("")):
    """Giọng Edge cho MỘT ngôn ngữ. Không truyền `lang` = ngôn ngữ trả lời đang cấu hình.

    Trước đây hàm này lọc cứng `Locale.startswith("vi")`, nên dù Javis có trả lời tiếng Anh
    thì ô chọn giọng vẫn chỉ hiện giọng Việt - và một câu tiếng Anh đọc bằng giọng Việt thì
    nghe như máy hỏng. Danh sách ngôn ngữ lấy từ sổ đăng ký chứ không khai lại ở đây.
    """
    import edge_tts   # lazy - xem ghi chú ở đầu file
    ma = lang_registry.chuan_hoa(lang) or localefmt.ngon_ngu_tra_loi()
    # Tiền tố locale suy từ giọng mặc định của ngôn ngữ đó ("vi-VN-HoaiMyNeural" -> "vi-VN"),
    # để thêm ngôn ngữ vẫn chỉ là thêm một dòng trong sổ đăng ký.
    giong_mac_dinh = lang_registry.giong_tts(ma, "edge")
    tien_to = "-".join(giong_mac_dinh.split("-")[:2]) if giong_mac_dinh else ma
    voices = await edge_tts.list_voices()
    return {
        "lang": ma,
        "voices": [
            {"name": v["ShortName"], "gender": v["Gender"], "display": v["FriendlyName"]}
            for v in voices if v["Locale"].startswith(tien_to)
        ]
    }


# ============================================
# Lưu MỘT lượt hội thoại - đường DUY NHẤT, dùng chung cho mọi kênh (dashboard, Telegram)
# ============================================
async def _persist_turn(store, conv_sid, brain, user_message, final_text):
    """Lưu lượt vừa xong: kho phiên + tiêu đề + nhật ký Memory + hàng đợi tự học.

    Bóc khối điều khiển (`<!-- JAVIS_ASK ... -->`) TRƯỚC khi lưu. Dashboard vẽ nút từ sự kiện
    WebSocket SỐNG, còn bản lưu chỉ để đọc lại và để TỰ HỌC - giữ khối thô ở đây là đẩy rác
    vào đúng corpus dùng để học. (`openStoredSession` bên dashboard vốn không dựng lại nút từ
    lịch sử, nên bóc khối không mất gì cả.)

    Vì sao là hàm chung: trước 0.9.244 chỉ nhánh dashboard lưu, nên hội thoại Telegram vắng
    mặt ở `/sessions`, ở `brain/Memory/conversations`, và ở vòng tự học.

    Trả về text đã bóc khối (rỗng/None thì KHÔNG lưu gì - lượt lỗi hoặc bị huỷ).
    """
    clean = channel_context.strip_control_blocks(final_text or "")
    if not clean:
        return None
    store.append_message(conv_sid, "assistant", clean)
    store.auto_title(conv_sid, user_message)
    log_conversation(brain, user_message, clean)
    # Rewire: đưa lượt vào hàng đợi học. `enqueue` chỉ đọc config + cộng bộ đếm dưới khoá
    # (mẻ học thật chạy ở `learn_feature.tick`), nên await thẳng - rẻ hơn một lần ghi file
    # log ngay trên. Trước đây dùng create_task: task mồ côi, không ai chờ, nuốt lỗi im.
    try:
        await learn_feature.enqueue(brain, conv_sid, user_message, clean)
    except Exception as _e:
        print(f"[learn enqueue hook] {_e}", file=__import__('sys').stderr)
    return clean


# ============================================
# WebSocket - Voice chat với Claude Code
# ============================================
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    if cfgmod.gate_active() and not cfgmod.valid_session(ws.cookies.get("javis_session", "")):
        await ws.close(code=1008)
        return
    await ws.accept()
    # WebSocket chỉ là subscriber. Job chat sống trong _CHAT_RUNTIME nên đóng/F5 tab
    # không huỷ job; kết nối mới nhận snapshot để xem hoặc Stop tiếp.
    conn_tag = f"chat:{uuid.uuid4().hex[:8]}"
    client_id = uuid.uuid4().hex
    _real_ws = ws                       # ws THẬT; mỗi lượt dùng proxy (bơm session_id + khoá ghi)
    store = get_store()

    # ĐA HỘI THOẠI SONG SONG: mỗi lượt chat chạy như 1 task nền (không chặn vòng nhận tin), engine
    # riêng từng lượt nên 2 hội thoại generate cùng lúc được. Mọi gói gửi kèm session_id để client
    # định tuyến về đúng phiên; mở "hội thoại mới" KHÔNG giết lượt cũ (nó chạy nốt + tự lưu).
    send_lock = asyncio.Lock()          # nhiều lượt ghi chung 1 ws → khoá cho khỏi xen kẽ hỏng gói

    async def send_client(obj):
        async with send_lock:
            try:
                await _real_ws.send_text(json.dumps(obj))
            except Exception:
                pass

    _CHAT_RUNTIME.add_client(client_id, send_client)
    await send_client({
        "type": "hello",
        "stop_tag": conn_tag,
        "running": _CHAT_RUNTIME.snapshot(),
    })

    async def send_raw(obj):
        await _CHAT_RUNTIME.publish(obj)

    class _SendProxy:
        """Đội lốt ws bên trong 1 lượt: mọi send_text tự gắn session_id của lượt + qua khoá ghi.
        Nhờ vậy toàn bộ code các nhánh engine bên dưới KHÔNG cần sửa mà vẫn định tuyến đúng phiên."""
        def __init__(self, sid, runtime_trace=None):
            self._sid = sid
            self._runtime_trace = runtime_trace

        async def send_text(self, txt):
            try:
                o = json.loads(txt)
                o["session_id"] = self._sid
                o.update(context_runtime.event_fields(self._runtime_trace))
                if o.get("type") == "error":
                    _CONTEXT_RUNTIME.note_error(self._runtime_trace, "engine_error_event")
            except Exception:
                return
            await _CHAT_RUNTIME.publish(o)

    try:
        async def _do_turn(conv_sid, user_message, brain, turn_tag, runtime_trace=None,
                           has_attachments=False):
            ws = _SendProxy(conv_sid, runtime_trace)  # các nhánh engine bên dưới dùng ws proxy này
            _cfg_all = cfgmod.read_settings()
            mcfg = _cfg_all.get("model", {})
            # NGÔN NGỮ chốt MỘT LẦN cho cả lượt, ngay đây. Chốt sớm và chốt một chỗ là để câu
            # trả lời, giọng đọc và các cổng chặn không bao giờ hiểu khác nhau trong cùng một
            # lượt. Không ai ghim gì thì `resolve` trả `theo_nguoi_dung=True` và chính MODEL
            # bám theo thứ tiếng người dùng vừa viết - xem đầu file lang.py.
            _lc = _cfg_all.get("locale") or {}
            _lang_qd = lang_mod.resolve(
                turn_text=user_message,
                reply_pref=_lc.get("reply_lang") or "auto",
                ui_lang=_lc.get("ui_lang") or "",
            )
            try:
                _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "lang.resolved",
                                                      _lang_qd.as_trace())
            except Exception:
                pass
            # Đọc row phiên TRƯỚC khi chọn provider: phiên có thể đã ghim model riêng.
            _row0 = store.get_session(conv_sid) or {}
            prov, kind, api_key, api_model = _chat_provider_for_session(mcfg, _row0)
            reasoning = _reasoning_level(mcfg)
            _CONTEXT_RUNTIME.set_route(
                runtime_trace,
                "codex" if prov == "openai-oauth" else prov,
                api_model or mcfg.get("claude_model") or "mặc định",
            )
            if kind in ("cli", "oauth"):
                _schedule_registry_discovery_shadow(
                    runtime_trace, brain, user_message,
                    "codex" if prov == "openai-oauth" else "cli",
                    api_model or mcfg.get("claude_model") or "mặc định", kind,
                )
            _ctx_in = 0        # token VÀO của lượt này, để khung chat nói được nó tốn bao nhiêu
            cli = claude_engine(system_prompt=SYSTEM_PROMPT, cwd=CLAUDE_CWD, tag=turn_tag)
            cli.session_id = _row0.get("cli_session_id") or None    # --resume đúng mạch phiên này
            final_text = ""
            used_fast_path = False

            await ws.send_text(json.dumps({
                "type": "status",
                "content": "Javis đang suy nghĩ..."
            }))

            # Dựng prompt cũ theo nhu cầu. Fast Path không đọc/nạp memory hoặc lịch sử cũ.
            sysprompt = None

            def _legacy_system_prompt():
                nonlocal sysprompt
                if sysprompt is None:
                    sysprompt = build_system_prompt(brain, lang=_lang_qd) + channel_context.build_channel_block(
                        "dashboard", {"session_id": conv_sid}, telegram_running=bool(_TG_BOT),
                        port=_javis_port(), brain_root=_brain_root(brain),
                    )
                return sysprompt

            async def _subscription_system_prompt(route_provider, route_model, route_kind):
                """System prompt cho engine chạy bằng GÓI THUÊ BAO (Claude Code, Codex).

                Cùng bộ máy Phase 8 với engine API, nhưng khác một điểm CỐ Ý: nền vẫn là
                `build_system_prompt` (giữ nguyên CLAUDE.md) chứ không phải
                `build_adaptive_source_prompt` (bỏ CLAUDE.md).

                Vì sao khác: bỏ CLAUDE.md đổi lấy token là món hời khi bị siết TPM và mỗi
                token đều tính tiền. Với gói thuê bao thì không tính tiền theo token, mà
                CLAUDE.md lại chính là 21.500 ký tự luật hành xử của Javis - vứt nó đi để
                tiết kiệm thứ mình không bị tính là đổi hành vi lấy một khoản không cần.
                Nên ở đây chỉ chọn lọc hai nguồn ĐỌC THÊM: bộ nhớ và skill.

                Trả về (prompt, plan). plan=None nghĩa là Phase 8 không chạy được lượt này.
                """
                def _base(include_memory: bool, include_skills: bool) -> str:
                    return build_system_prompt(
                        brain, include_memory=include_memory, include_skills=include_skills,
                        lang=_lang_qd,
                    ) + channel_context.build_channel_block(
                        "dashboard", {"session_id": conv_sid}, telegram_running=bool(_TG_BOT),
                        port=_javis_port(), brain_root=_brain_root(brain),
                    )

                try:
                    plan = await asyncio.to_thread(
                        _get_adaptive_context().prepare,
                        runtime_trace, user_message, _brain_root(brain), conv_sid,
                        store.get_messages(conv_sid), "dashboard", route_provider,
                        route_model, route_kind, _base,
                    )
                except Exception as _exc:   # noqa: BLE001 - không được phá lượt chat
                    _CONTEXT_RUNTIME.record_runtime_event(
                        runtime_trace, "context_sources.subscription_error",
                        {"error_type": type(_exc).__name__, "provider_kind": route_kind})
                    return _legacy_system_prompt(), None
                # "reject" không tới được đây: với engine thuê bao, prepare() đã đổi nhánh
                # vượt ngân sách thành legacy (subscription_soft_over_budget) vì con số đó là
                # trần ta tự khai, không phải hạn mức nhà cung cấp nói ra.
                if plan.action == "use" and plan.system_prompt:
                    return plan.system_prompt, plan
                return _legacy_system_prompt(), plan

            final_text = ""
            _schedule_action = await _schedule_cancel_action(user_message, brain)
            # Đường tắt cho bộ não GÓI THUÊ BAO phải xét TRƯỚC chuỗi nhánh engine, vì nó thay
            # hẳn nhánh engine chứ không chạy bên trong. Tính ở đây để chuỗi bên dưới chỉ còn
            # là một điều kiện, khỏi phải thụt lề lại cả hai nhánh. None = không đi đường tắt.
            _codex_fast_plan = None
            if kind in ("oauth", "cli") and not _schedule_action:
                try:
                    _plan = await asyncio.to_thread(
                        _FAST_PATH.prepare, runtime_trace, user_message, _brain_root(brain),
                        "dashboard", prov,
                        _codex_safe_model(api_model) if kind == "oauth"
                        else (api_model or mcfg.get("claude_model") or "mặc định"),
                        kind, bool(has_attachments), _lang_qd.lang_cau_hoi, _lang_qd.lang,
                    )
                    # Chỉ nhận "execute". "reject" của đường tắt là lời từ chối dựa trên
                    # TRẦN TỰ KHAI của gói thuê bao, không phải hạn mức nhà cung cấp nói ra -
                    # lấy nó chặn lượt chat là vượt quyền, cùng lý do với nhánh soft ở Phase 8.
                    _codex_fast_plan = _plan if _plan and _plan.action == "execute" else None
                except Exception as _exc:
                    _codex_fast_plan = None
                    _CONTEXT_RUNTIME.record_runtime_event(
                        runtime_trace, "fast_path.prepare_error",
                        {"error_type": type(_exc).__name__, "engine": "codex"})
            if _schedule_action:
                for _call in _schedule_action.get("calls") or []:
                    await ws.send_text(json.dumps({
                        "type": "tool_call", "tool": "javis_schedule",
                        "content": f"⚙ Lịch: {_call.split(':')[-1]}",
                    }))
                final_text = _schedule_cancel_reply(_schedule_action)
                await ws.send_text(json.dumps({
                    "type": "response", "content": final_text,
                    "engine": "javis_schedule", "model": "gateway",
                    "session_id": conv_sid,
                    **_ctx_frame(runtime_trace, _ctx_in),
                }))
            elif _codex_fast_plan is not None and kind in ("oauth", "cli"):
                # ===== GÓI THUÊ BAO, ĐƯỜNG TẮT: gọi thẳng model một vòng =====
                # Câu hỏi không cần tra cứu gì thì không có lý do đi qua CLI, nơi mỗi lượt là
                # cả một vòng lặp đọc file và gọi tool. Đây là chỗ token thật sự nằm: đo trên
                # máy chủ repo, một lượt Codex vào 100k tới 412k trong khi model chỉ viết ra
                # vài trăm token. Đường tắt đi đúng một vòng.
                # _execute_fast_path tự gửi gói `response` kèm dòng đường chạy, y như nhánh
                # engine API vẫn dùng nó. Gửi thêm một gói nữa ở đây là hiện hai câu trả lời.
                final_text, _fast_model = await _execute_fast_path(
                    _codex_fast_plan, prov, "",
                    _codex_safe_model(api_model) if kind == "oauth"
                    else (api_model or mcfg.get("claude_model") or "mặc định"),
                    reasoning, ws, conv_sid, runtime_trace, user_message,
                    im_lang_khi_loi=True,
                )
                if final_text:
                    used_fast_path = True
                    # Lượt này KHÔNG đi qua CLI, nên mạch native của engine không hề biết nó
                    # đã xảy ra. Cứ nối tiếp mạch cũ ở lượt sau là engine trả lời với một bản
                    # ghi THIẾU: không thấy câu vừa hỏi lẫn câu vừa đáp, rồi nói lại hoặc nói
                    # mâu thuẫn. Bỏ liên kết mạch để lượt sau dựng lại từ SQLite - nơi lượt
                    # này ĐÃ được lưu. Bản mồi lại có trần ký tự nên còn rẻ hơn mạch cũ.
                    # Trước đây chỗ này gọi set_cli_session_id với chuỗi RỖNG để xoá mạch
                    # Claude Code, và nó KHÔNG xoá gì: hàm đó return ngay khi giá trị rỗng.
                    # Tức mạch Claude vẫn trỏ mạch cũ, đúng cái mà đoạn trên vừa giải thích
                    # là phải bỏ. Nay dọn cả ba mạch bằng một lệnh có kiểm chứng bằng test.
                    store.clear_native_threads(conv_sid)
                else:
                    # Đường tắt về tay không. Với gói Claude Code đây là ca THẬT SỰ có thể
                    # xảy ra: nó gọi Messages API bằng access token của CLI, mà token đó có
                    # thể hết hạn hoặc bị Anthropic từ chối cho đường này. Không có lưới ở
                    # đây thì một câu hỏi đơn giản trả về bong bóng rỗng. Lui về engine đầy
                    # đủ ngay trong lượt: chậm hơn, nhưng người dùng có câu trả lời.
                    _CONTEXT_RUNTIME.record_runtime_event(
                        runtime_trace, "fast_path.fallback_engine",
                        {"engine": "codex" if kind == "oauth" else "claude-code"})
                    # Trả lại chỗ ghim. Đường tắt đã ghim "fast" lúc nhận lượt; giữ nguyên là
                    # lượt CHẠY BẰNG engine đầy đủ vẫn đeo nhãn "Tức thì", và con số tiết kiệm
                    # bị thổi lên bằng đúng những lượt không hề tiết kiệm.
                    _CONTEXT_RUNTIME.nha_ghim_duong(runtime_trace, "fast")

            # Một cờ DUY NHẤT cho "lượt này đã có câu trả lời rồi". Hai nhánh trên đều có thể
            # kết thúc lượt, mà đường tắt còn có thể về tay không rồi nhường lại cho engine
            # đầy đủ - viết thành hai chuỗi if/elif lồng nhau thì đúng nhưng không ai đọc nổi.
            _da_tra_loi = bool(_schedule_action) or used_fast_path
            if _da_tra_loi:
                pass
            elif prov == "gemini-cli":
                # ===== Gói Google (đăng nhập tài khoản) qua GEMINI CLI - tool native + MCP hub =====
                actual_model = api_model or gemini_cli.MODEL_MAC_DINH
                sysprompt, _sub_plan = await _subscription_system_prompt(
                    "gemini-cli", actual_model, kind)
                gcli = gemini_cli.GeminiCLI(cwd=_brain_root(brain), model=actual_model,
                                            tag=turn_tag, instructions=sysprompt)
                _apply_gemini_hub(gcli, _brain_root(brain))
                if not gcli.is_available():
                    final_text = ("⚠ Chưa cài Gemini CLI trên máy này. Cài bằng "
                                  "`npm i -g @google/gemini-cli` rồi chạy `gemini` một lần để "
                                  "đăng nhập Google.")
                    await ws.send_text(json.dumps({
                        "type": "response", "content": final_text, "engine": "gemini-cli",
                        "model": actual_model, "session_id": conv_sid,
                        **_ctx_frame(runtime_trace, _ctx_in)}))
                else:
                    # Mạch cũ: nối lại nếu có và chưa phình quá ngưỡng. Cùng luật với Codex và
                    # Claude Code - Javis không nhìn được vào mạch của CLI, chỉ có token vào của
                    # lượt trước làm dấu hiệu.
                    _g_mach = (_row0.get("gemini_session_id") or "").strip()
                    if _g_mach and compaction.nen_mach_thue_bao(
                            _row0.get("last_input_tokens"), msg_count=_row0.get("msg_count"),
                            rotated_at=_row0.get("thread_rotated_msg")):
                        _g_mach = ""
                        store.clear_gemini_session_id(conv_sid)
                        store.mark_thread_rotated(conv_sid)
                        _CONTEXT_RUNTIME.record_runtime_event(
                            runtime_trace, "thread.rotated",
                            {"engine": "gemini-cli",
                             "last_input_tokens": int(_row0.get("last_input_tokens") or 0),
                             "threshold": compaction.SUBSCRIPTION_THREAD_MAX_TOKENS})
                        await ws.send_text(json.dumps({
                            "type": "tool_call", "tool": "javis_nen_mach",
                            "content": "⚙ Mạch hội thoại đã dài, Javis mở mạch mới."}))
                    gcli.session_id = _g_mach or None
                    # Mạch mới thì mồi lại bằng transcript đã lưu, y như Codex: không có bước
                    # này là mở mạch mới = mất sạch ngữ cảnh cuộc đang nói dở.
                    _g_cur = _cli_think(reasoning, user_message)
                    _g_raw = [{"role": _m["role"], "content": _m["content"]}
                              for _m in store.get_messages(conv_sid)[:-1]
                              if _m["role"] in ("user", "assistant") and _m.get("content")]
                    _g_prompt = (_g_cur if _g_mach else compaction.bootstrap_prompt(
                        _g_raw, _g_cur, summary=_row0.get("compact_summary") or ""))

                    async def _nuot_gemini(prompt):
                        nonlocal final_text
                        _CONTEXT_RUNTIME.observe_payload(
                            runtime_trace,
                            [{"role": "system", "content": sysprompt},
                             {"role": "user", "content": prompt}],
                            provider="gemini-cli", model=actual_model)
                        async for ev in gcli.query(prompt):
                            et = ev.get("type")
                            if et == "tool_call":
                                await ws.send_text(json.dumps({
                                    "type": "tool_call", "tool": ev.get("name", ""),
                                    "content": f"⚙ Đang gọi: {ev.get('name', '')}"}))
                            elif et == "final":
                                final_text = ev.get("content") or ""
                            elif et == "usage":
                                # Token VÀO của lượt là dấu hiệu DUY NHẤT để biết mạch đã phình
                                # tới đâu (CLI tự quản mạch, Javis không nhìn vào được).
                                store.set_last_input_tokens(
                                    conv_sid, int(ev.get("input_tokens") or 0))
                            elif et == "error":
                                _noi = _subscription_limit_message(ev.get("content") or "",
                                                                   "gemini-cli")
                                if _noi:
                                    _CONTEXT_RUNTIME.record_runtime_event(
                                        runtime_trace, "subscription.limit_reached",
                                        {"engine": "gemini-cli", "model": actual_model})
                                    final_text = final_text or _noi
                                await ws.send_text(json.dumps({
                                    "type": "error", "content": _noi or ev.get("content", "")}))

                    await _nuot_gemini(_g_prompt)
                    # CLI cấp UUID mạch ở sự kiện `init`; lưu lại để lượt sau --resume.
                    if gcli.session_id:
                        store.set_gemini_session_id(conv_sid, gcli.session_id)
                    await ws.send_text(json.dumps({
                        "type": "response", "content": final_text, "engine": "gemini-cli",
                        "model": actual_model, "session_id": conv_sid,
                        **_ctx_frame(runtime_trace, _ctx_in)}))
            elif prov == "antigravity-cli":
                # ===== Gói Google qua ANTIGRAVITY CLI (`agy`) - tool native + MCP hub =====
                #
                # CỐ Ý chưa nối lại mạch hội thoại của CLI như nhánh Gemini/Codex ngay trên.
                # `agy` có `--conversation <uuid>`, nhưng chưa ai đo được nó trên máy thật, mà
                # lưu một id sai vào SQLite thì lượt sau nối vào mạch không tồn tại và hỏng câm.
                # Nên mỗi lượt mở mạch mới và mồi lại bằng transcript đã lưu - tốn token hơn
                # nhưng KHÔNG mất ngữ cảnh. Đo được cờ đó rồi thì nâng lên đúng khuôn Gemini.
                actual_model = api_model or None
                sysprompt, _sub_plan = await _subscription_system_prompt(
                    "antigravity-cli", actual_model or "", kind)
                acli = antigravity_cli.AntigravityCLI(cwd=_brain_root(brain), model=actual_model,
                                                      tag=turn_tag, instructions=sysprompt)
                acli.mode = "full"
                _apply_antigravity_hub(acli, _brain_root(brain))
                if not acli.is_available():
                    final_text = ("⚠ Chưa cài Antigravity CLI trên máy này. Cài một lần:\n\n"
                                  f"`{antigravity_cli.lenh_cai()}`\n\n"
                                  "Rồi gõ `agy` một lần để đăng nhập Google (qua SSH thì nó in "
                                  "ra một link để mở trên máy bạn).")
                    await ws.send_text(json.dumps({
                        "type": "response", "content": final_text, "engine": "antigravity-cli",
                        "model": actual_model or "", "session_id": conv_sid,
                        **_ctx_frame(runtime_trace, _ctx_in)}))
                else:
                    _a_cur = _cli_think(reasoning, user_message)
                    _a_raw = [{"role": _m["role"], "content": _m["content"]}
                              for _m in store.get_messages(conv_sid)[:-1]
                              if _m["role"] in ("user", "assistant") and _m.get("content")]
                    _a_prompt = compaction.bootstrap_prompt(
                        _a_raw, _a_cur, summary=_row0.get("compact_summary") or "")
                    _CONTEXT_RUNTIME.observe_payload(
                        runtime_trace,
                        [{"role": "system", "content": sysprompt},
                         {"role": "user", "content": _a_prompt}],
                        provider="antigravity-cli", model=actual_model or "")
                    async for ev in acli.query(_a_prompt):
                        et = ev.get("type")
                        if et == "tool_call":
                            await ws.send_text(json.dumps({
                                "type": "tool_call", "tool": ev.get("name", ""),
                                "content": f"⚙ Đang gọi: {ev.get('name', '')}"}))
                        elif et == "final":
                            final_text = ev.get("content") or ""
                        elif et == "usage":
                            store.set_last_input_tokens(
                                conv_sid, int(ev.get("input_tokens") or 0))
                        elif et == "error":
                            _noi = _subscription_limit_message(ev.get("content") or "",
                                                               "antigravity-cli")
                            if _noi:
                                final_text = final_text or _noi
                            await ws.send_text(json.dumps({
                                "type": "error", "content": _noi or ev.get("content", "")}))
                    await ws.send_text(json.dumps({
                        "type": "response", "content": final_text, "engine": "antigravity-cli",
                        "model": actual_model or "", "session_id": conv_sid,
                        **_ctx_frame(runtime_trace, _ctx_in)}))
            elif prov == "openai-oauth":
                # ===== ChatGPT subscription qua CODEX CLI - MCP/tool NATIVE (như Hermes, dùng codex của máy) =====
                actual_model = _codex_safe_model(api_model)   # gpt-5-mini/gpt-4o... → coerce về model Codex hợp lệ
                sysprompt, _sub_plan = await _subscription_system_prompt("codex", actual_model, kind)
                if api_model and actual_model != api_model:
                    # Tự chữa: model đã lưu không hợp lệ cho Codex → ghi lại model đúng (converge sau 1 lượt)
                    try:
                        _fix = cfgmod.read_settings(); _set_main_model(_fix, "openai-oauth", actual_model); cfgmod.write_settings(_fix)
                        await ws.send_text(json.dumps({"type": "system", "content": f"⚠ Model '{api_model}' không chạy được qua Codex (tài khoản ChatGPT) - đã tự đổi sang '{actual_model}'. Đổi model khác ở trang Models nếu muốn."}))
                    except Exception as _e:
                        print(f"[codex model self-heal] {_e}", file=__import__('sys').stderr)
                openai_oauth.write_codex_auth()   # bắc cầu token đã nối ở Models → ~/.codex/auth.json (codex dùng được)
                # cwd=brain (để Codex đọc được Javis/skills + .claude/skills mirror bằng tool file
                # native, như nhánh workflow) + instructions=sysprompt (kèm ROUTER SKILL) → Codex
                # dùng được skill. Mỗi hội thoại dashboard giữ riêng codex_thread_id để resume.
                ccli = CodexCLI(cwd=_brain_root(brain), model=actual_model, tag=turn_tag, instructions=sysprompt)
                _apply_codex_hub(ccli, _brain_root(brain))   # MCP + đúng brain cho cron/nhắc hẹn
                stored_codex_thread = (_row0.get("codex_thread_id") or "").strip()
                # Mạch Codex đã phình quá ngưỡng thì THÔI resume: mở mạch mới rồi mồi lại
                # bằng transcript trong SQLite. Không làm bước này thì mỗi lượt tiếp theo
                # đều đắt hơn lượt trước mà không thêm giá trị gì, và đó là phần TO NHẤT của
                # hoá đơn token - to hơn hẳn thứ Phase 8 gọt được. Xem compaction.
                if stored_codex_thread and compaction.nen_mach_thue_bao(
                        _row0.get("last_input_tokens"), msg_count=_row0.get("msg_count"),
                        rotated_at=_row0.get("thread_rotated_msg")):
                    stored_codex_thread = ""
                    store.clear_codex_thread_id(conv_sid)
                    store.mark_thread_rotated(conv_sid)
                    _CONTEXT_RUNTIME.record_runtime_event(
                        runtime_trace, "thread.rotated",
                        {"engine": "codex",
                         "last_input_tokens": int(_row0.get("last_input_tokens") or 0),
                         "threshold": compaction.SUBSCRIPTION_THREAD_MAX_TOKENS})
                    await ws.send_text(json.dumps({
                        "type": "tool_call", "tool": "javis_nen_mach",
                        "content": ("⚙ Mạch hội thoại đã dài "
                                    f"({int(_row0.get('last_input_tokens') or 0):,} token mỗi lượt), "
                                    "Javis mở mạch mới và mang theo tóm tắt."),
                    }))
                ccli.session_id = stored_codex_thread or None
                if not ccli.is_available():
                    await ws.send_text(json.dumps({"type": "error", "content": "Chưa cài Codex CLI trong container. ChatGPT subscription là THỬ NGHIỆM - dùng Claude Code hoặc OpenRouter cho ổn định (đổi ở Models)."}))
                else:
                    _codex_current = _cli_think(reasoning, user_message)
                    _codex_raw = [{"role": _m["role"], "content": _m["content"]}
                                  for _m in store.get_messages(conv_sid)[:-1]
                                  if _m["role"] in ("user", "assistant") and _m.get("content")]
                    # Phiên tạo trước bản vá chưa có thread_id: seed transcript đúng 1 lượt để
                    # không mất mạch, rồi thread.started sẽ được lưu và resume native từ lượt sau.
                    _codex_prompt = (_codex_current if stored_codex_thread else
                                     compaction.bootstrap_prompt(
                                         _codex_raw, _codex_current,
                                         summary=_row0.get("compact_summary") or ""))
                    async def _consume_codex(prompt, suppress_resume_error=False):
                        # _ctx_in PHẢI khai nonlocal: nó bị `+=` ngay dưới, mà thiếu dòng này
                        # thì Python coi nó là biến CỤC BỘ của hàm con - đọc trước khi gán là
                        # UnboundLocalError, ném đúng lúc Codex trả lời xong. Hậu quả không chỉ
                        # là mất dòng đếm token: cả lượt chat vỡ, câu trả lời đã stream ra không
                        # được lưu, người dùng chỉ thấy "Lỗi xử lý". Đây là hàm con DUY NHẤT
                        # đụng vào _ctx_in; hai nhánh engine kia cộng thẳng trong _do_turn nên
                        # không dính.
                        nonlocal final_text, _ctx_in
                        resume_failed = False
                        # Đo theo từng invocation thật: nhánh khôi phục thread có thể gọi lần hai.
                        _CONTEXT_RUNTIME.observe_payload(
                            runtime_trace,
                            [{"role": "system", "content": sysprompt},
                             {"role": "user", "content": prompt}],
                            provider="codex", model=actual_model,
                        )
                        async for ev in ccli.query(prompt):
                            et = ev["type"]
                            if et == "session":
                                if ev.get("session_id"):
                                    store.set_codex_thread_id(conv_sid, ev["session_id"])
                            elif et == "tool_call":
                                await ws.send_text(json.dumps({"type": "tool_call", "tool": ev.get("name", ""), "content": f"⚙ {ev.get('name', '')}"}))
                            elif et == "text":
                                final_text += ev["content"]
                                await ws.send_text(json.dumps({"type": "stream", "content": ev["content"], "tts": False}))
                            elif et == "final":
                                final_text = ev.get("content") or final_text
                                if ev.get("session_id"):
                                    store.set_codex_thread_id(conv_sid, ev["session_id"])
                                _ctx_in += int(ev.get("tokens_in", 0) or 0)
                                usage_store.record("codex", actual_model, ev.get("tokens_in", 0), ev.get("tokens_out", 0))
                                _CONTEXT_RUNTIME.record_usage(
                                    runtime_trace, ev.get("tokens_in", 0), ev.get("tokens_out", 0))
                            elif et == "error":
                                if ev.get("resume_failed"):
                                    resume_failed = True
                                    if suppress_resume_error:
                                        continue
                                _noi = _subscription_limit_message(ev.get("content") or "", "codex")
                                if _noi:
                                    _CONTEXT_RUNTIME.record_runtime_event(
                                        runtime_trace, "subscription.limit_reached",
                                        {"engine": "codex", "model": actual_model})
                                    final_text = final_text or _noi
                                await ws.send_text(json.dumps({
                                    "type": "error", "content": _noi or ev["content"]}))
                        return resume_failed

                    _resume_failed = await _consume_codex(
                        _codex_prompt, suppress_resume_error=bool(stored_codex_thread))
                    if stored_codex_thread and _resume_failed and not final_text:
                        # Rollout local có thể bị dọn/mất sau nâng cấp máy. Không bỏ luôn context:
                        # tạo thread mới từ transcript SQLite, lưu ID mới, rồi các lượt sau resume nó.
                        await ws.send_text(json.dumps({
                            "type": "system",
                            "content": "Phiên Codex cũ không còn trên máy - Javis đang khôi phục ngữ cảnh từ lịch sử đã lưu."
                        }))
                        ccli.session_id = None
                        _fallback = compaction.bootstrap_prompt(
                            _codex_raw, _codex_current,
                            summary=_row0.get("compact_summary") or "")
                        await _consume_codex(_fallback)
                    await ws.send_text(json.dumps({
                        "type": "response", "content": final_text, "engine": "codex",
                        "model": actual_model, "session_id": conv_sid,
                        **_ctx_frame(runtime_trace, _ctx_in)}))
            elif (kind == "api" and api_key) or kind == "oauth":
                orchestrator_plan = None
                readonly_plan = None
                fast_plan = None
                write_plan = None
                confirm_plan = None
                if kind == "api" and api_key:
                    # Phase 9 xét TRƯỚC: lượt này có thể là câu xác nhận cho một hành
                    # động ghi đã đề xuất ở lượt trước, không phải một yêu cầu mới.
                    try:
                        confirm_plan = _get_write_path().pending_for(conv_sid, user_message)
                    except Exception as _exc:
                        confirm_plan = None
                        _CONTEXT_RUNTIME.record_runtime_event(
                            runtime_trace, "write.confirm_lookup_error",
                            {"error_type": type(_exc).__name__})
                    if confirm_plan is None or confirm_plan.action != "execute":
                        try:
                            write_plan = await _get_write_path().prepare(
                                runtime_trace, user_message, _brain_root(brain),
                                "dashboard", prov, api_model or "?", kind,
                                actor_id=conv_sid, has_attachments=bool(has_attachments),
                            )
                        except Exception as _exc:
                            write_plan = None
                            _CONTEXT_RUNTIME.record_runtime_event(
                                runtime_trace, "write.prepare_error",
                                {"error_type": type(_exc).__name__})
                write_handled = False
                if confirm_plan is not None and confirm_plan.action == "execute":
                    used_fast_path = True
                    write_handled = True
                    final_text = await _execute_write_confirmation(
                        confirm_plan, ws, conv_sid, runtime_trace, brain, prov,
                        api_model or "?",
                    )
                elif write_plan is not None and write_plan.action == "propose":
                    used_fast_path = True
                    write_handled = True
                    final_text, _actual_model = await _execute_write_proposal(
                        write_plan, prov, api_key, api_model, reasoning, ws, conv_sid,
                        runtime_trace,
                    )
                elif write_plan is not None and write_plan.action == "reject":
                    used_fast_path = True
                    write_handled = True
                    final_text = write_plan.rejection_message
                    _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "write_path.rejected", {
                        "reason": write_plan.reason, "model_rounds": 0,
                        "estimated_input_tokens": write_plan.estimated_input_tokens,
                    })
                    await ws.send_text(json.dumps({
                        "type": "response", "content": final_text,
                        "engine": "javis-gateway", "model": api_model or "?",
                        "session_id": conv_sid,
                        **_ctx_frame(runtime_trace, _ctx_in),
                    }))
                elif kind == "api" and api_key:
                    # Mọi exception trong prepare của canary phải rơi tiếp xuống nhánh
                    # sau (cuối cùng là legacy), không được phá lượt chat (spec mục 23).
                    try:
                        orchestrator_plan = await _get_readonly_orchestrator().prepare(
                            runtime_trace, user_message, _brain_root(brain), "dashboard",
                            prov, api_model or "?", kind, actor_id=conv_sid,
                            has_attachments=bool(has_attachments),
                        )
                    except Exception as _exc:
                        orchestrator_plan = None
                        _CONTEXT_RUNTIME.record_runtime_event(
                            runtime_trace, "orchestrator.prepare_error",
                            {"error_type": type(_exc).__name__})
                    if orchestrator_plan is None or orchestrator_plan.action == "not_applicable":
                        try:
                            readonly_plan = await _get_readonly_path().prepare(
                                runtime_trace, user_message, _brain_root(brain),
                                "dashboard", prov, api_model or "?", kind,
                                actor_id=conv_sid, has_attachments=bool(has_attachments),
                            )
                        except Exception as _exc:
                            readonly_plan = None
                            _CONTEXT_RUNTIME.record_runtime_event(
                                runtime_trace, "readonly.prepare_error",
                                {"error_type": type(_exc).__name__})
                        if readonly_plan is None or readonly_plan.action == "not_applicable":
                            try:
                                fast_plan = await asyncio.to_thread(
                                    _FAST_PATH.prepare, runtime_trace, user_message,
                                    _brain_root(brain), "dashboard", prov,
                                    api_model or "?", kind, bool(has_attachments),
                                    _lang_qd.lang_cau_hoi, _lang_qd.lang,
                                )
                            except Exception as _exc:
                                fast_plan = None
                                _CONTEXT_RUNTIME.record_runtime_event(
                                    runtime_trace, "fast_path.prepare_error",
                                    {"error_type": type(_exc).__name__})
                if write_handled:
                    pass
                elif orchestrator_plan and orchestrator_plan.action == "execute":
                    used_fast_path = True
                    final_text, _actual_model = await _execute_readonly_orchestrator(
                        orchestrator_plan, prov, api_key, api_model, reasoning, ws,
                        conv_sid, runtime_trace,
                    )
                elif orchestrator_plan and orchestrator_plan.action == "reject":
                    used_fast_path = True
                    final_text = orchestrator_plan.rejection_message
                    _CONTEXT_RUNTIME.record_runtime_event(
                        runtime_trace, "orchestrator.rejected", {
                            "reason": orchestrator_plan.reason, "model_rounds": 0,
                            "estimated_input_tokens": orchestrator_plan.estimated_input_tokens,
                            "reserved_output_tokens": orchestrator_plan.reserved_output_tokens,
                            "estimated_cost_usd": orchestrator_plan.estimated_cost_usd,
                        },
                    )
                    await ws.send_text(json.dumps({
                        "type": "response", "content": final_text,
                        "engine": "javis-gateway", "model": api_model or "?",
                        "session_id": conv_sid, "task_id": runtime_trace.task_id,
                        **_ctx_frame(runtime_trace, _ctx_in),
                    }))
                elif readonly_plan and readonly_plan.action == "execute":
                    used_fast_path = True
                    final_text, _actual_model = await _execute_readonly_path(
                        readonly_plan, prov, api_key, api_model, reasoning, ws, conv_sid,
                        runtime_trace, user_message, conv_sid,
                    )
                elif readonly_plan and readonly_plan.action == "reject":
                    used_fast_path = True
                    final_text = readonly_plan.rejection_message
                    _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "readonly_path.rejected", {
                        "reason": readonly_plan.reason, "model_rounds": 0,
                        "estimated_input_tokens": readonly_plan.estimated_input_tokens,
                        "reserved_input_tokens": readonly_plan.reserved_input_tokens,
                    })
                    await ws.send_text(json.dumps({
                        "type": "response", "content": final_text,
                        "engine": "javis-gateway", "model": api_model or "?",
                        "session_id": conv_sid,
                        **_ctx_frame(runtime_trace, _ctx_in),
                    }))
                elif fast_plan and fast_plan.action == "execute":
                    used_fast_path = True
                    final_text, _actual_model = await _execute_fast_path(
                        fast_plan, prov, api_key, api_model, reasoning, ws, conv_sid,
                        runtime_trace, user_message,
                    )
                elif fast_plan and fast_plan.action == "reject":
                    used_fast_path = True
                    final_text = fast_plan.rejection_message
                    _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "fast_path.rejected", {
                        "reason": fast_plan.reason, "model_rounds": 0,
                        "estimated_input_tokens": fast_plan.estimated_input_tokens,
                        "reserved_input_tokens": fast_plan.reserved_input_tokens,
                    })
                    await ws.send_text(json.dumps({
                        "type": "response", "content": final_text,
                        "engine": "javis-gateway", "model": api_model or "?",
                        "session_id": conv_sid,
                        **_ctx_frame(runtime_trace, _ctx_in),
                    }))
                else:
                    # ===== API/OAuth: Phase 8 sources canary, fallback độc lập về legacy =====
                    def _phase8_base(include_memory: bool, include_skills: bool) -> str:
                        return build_adaptive_source_prompt(
                            brain, include_memory=include_memory, include_skills=include_skills
                        ) + channel_context.build_channel_block(
                            "dashboard", {"session_id": conv_sid},
                            telegram_running=bool(_TG_BOT), port=_javis_port(),
                            brain_root=_brain_root(brain),
                        )

                    try:
                        _phase8_plan = await asyncio.to_thread(
                            _get_adaptive_context().prepare,
                            runtime_trace, user_message, _brain_root(brain), conv_sid,
                            store.get_messages(conv_sid), "dashboard", prov,
                            api_model or "?", kind, _phase8_base,
                        )
                    except Exception as _exc:
                        _phase8_plan = adaptive_context_runtime.AdaptiveContextPlan(
                            "legacy", f"prepare_error:{type(_exc).__name__}")
                    if _phase8_plan.action == "reject":
                        # Rơi về legacy ở đây là SAI CHIỀU. Phase 8 tồn tại để thay
                        # CLAUDE.md bằng capsule nhỏ; legacy gửi nguyên CLAUDE.md cộng
                        # MEMORY.md, tức là còn TO HƠN cái vừa bị từ chối vì quá to.
                        # Provider sẽ trả lỗi hạn mức và user chỉ thấy thông báo khó hiểu.
                        used_fast_path = True
                        final_text = _phase8_plan.rejection_message
                        _CONTEXT_RUNTIME.record_runtime_event(
                            runtime_trace, "quota.rejected",
                            {"reason": _phase8_plan.reason, "path": "context_sources"})
                        await ws.send_text(json.dumps({
                            "type": "response", "content": final_text,
                            "engine": "javis-gateway", "model": api_model or "?",
                            "session_id": conv_sid,
                            **_ctx_frame(runtime_trace, _ctx_in),
                        }))
                    else:
                        sysprompt = (_phase8_plan.system_prompt
                                     if _phase8_plan.action == "use" else _legacy_system_prompt())
                        label = _api_label(prov)
                        actual_model = api_model or "?"
                        _ident = (
                            f"\n\n[Sự thật hệ thống - TUÂN THỦ tuyệt đối: Bạn đang chạy qua {label}, "
                            f"model thực tế là '{actual_model}'. Khi được hỏi bạn là AI/model nào, "
                            f"trả lời ĐÚNG tên model này. KHÔNG được tự nhận là model khác.]"
                        )
                        _head = [{"role": "system", "content": sysprompt + _ident}]
                        if _phase8_plan.action == "use" and _phase8_plan.state_applied:
                            # State + recent transcript were already budgeted by Context Compiler.
                            or_messages = list(_head)
                        else:
                            _raw = [{"role": _m["role"], "content": _m["content"]}
                                    for _m in store.get_messages(conv_sid)[:-1]
                                    if _m["role"] in ("user", "assistant") and _m.get("content")]
                            or_messages = await compaction.prepare_history(
                                _head, store, conv_sid, _raw, prov, api_key, api_model, _api_stream)
                        or_messages.append({"role": "user", "content": user_message})
                        # Vòng gửi có TỰ CHỮA: nếu nhà cung cấp nói request quá hạn mức,
                        # học lấy con số thật rồi co ngữ cảnh lại và chạy tiếp, thay vì ném
                        # lỗi thô ra cho người dùng. Chỉ thử lại MỘT lần: lần hai mà vẫn
                        # vượt thì vấn đề không nằm ở kích thước ngữ cảnh nữa.
                        _limit_hit = None
                        for _attempt in (1, 2):
                            final_text = ""
                            _limit_hit = None
                            gen = await _api_stream_mcp(
                                prov, api_key, api_model, or_messages, reasoning, brain=brain,
                                force_lazy=(_phase8_plan.action == "use" or _attempt > 1),
                            )
                            async for ev in gen:
                                if ev["type"] == "meta":
                                    actual_model = ev.get("model") or actual_model
                                    _CONTEXT_RUNTIME.set_route(runtime_trace, prov, actual_model)
                                elif ev["type"] == "usage":
                                    _ctx_in += int(ev.get("input", 0) or 0)
                                    usage_store.record(
                                        prov, actual_model, ev.get("input", 0), ev.get("output", 0)
                                    )
                                    _CONTEXT_RUNTIME.record_usage(
                                        runtime_trace, ev.get("input", 0), ev.get("output", 0)
                                    )
                                elif ev["type"] == "limit_exceeded":
                                    _limit_hit = ev
                                elif ev["type"] == "tool_call":
                                    await ws.send_text(json.dumps({
                                        "type": "tool_call", "tool": ev.get("name", ""),
                                        "content": f"⚙ MCP: {ev.get('name', '')}",
                                    }))
                                elif ev["type"] == "text":
                                    final_text += ev["content"]
                                    await ws.send_text(json.dumps({
                                        "type": "stream", "content": ev["content"], "tts": False,
                                    }))
                                elif ev["type"] == "error":
                                    if not _limit_hit:
                                        await ws.send_text(json.dumps({
                                            "type": "error", "content": ev["content"],
                                        }))
                            if not _limit_hit or _attempt == 2:
                                break
                            # Thử lại chỉ có nghĩa khi việc cần làm là CO NHỎ. Hết hạn mức
                            # theo NGÀY, hay bị chặn nhịp mà không rõ chiều nào, thì gửi lại
                            # chỉ tốn thêm một lượt để ăn đúng cái lỗi đó lần nữa - và tệ hơn,
                            # nó dựng lên vẻ "Javis đang xử lý" trong khi không xử lý được gì.
                            if str(_limit_hit.get("remedy") or "") not in ("shrink", "wait"):
                                break
                            # Không đọc được hạn mức từ lỗi lần này thì lấy con số đã HỌC được
                            # từ lần nhà cung cấp từ chối trước đó. Đây chính là chỗ trước đây
                            # bỏ trống: target = 0 làm _shrink_messages chỉ bỏ lịch sử rồi trả
                            # về, không đụng system prompt - mà system prompt mới là chỗ phình.
                            _target = int(_limit_hit.get("shrink_to") or 0)
                            if _target <= 0:
                                _hoc = limit_learner.learned_token_limit(prov, actual_model)
                                _target = limit_learner.shrink_target(_hoc) if _hoc else 0
                            if _target <= 0:
                                break
                            _CONTEXT_RUNTIME.record_runtime_event(
                                runtime_trace, "limit.autoshrink", {
                                    "provider": prov, "limit": _limit_hit.get("limit", 0),
                                    "requested": _limit_hit.get("requested", 0),
                                    "kind": _limit_hit.get("kind", ""),
                                    "remedy": _limit_hit.get("remedy", ""),
                                    "shrink_to": _target,
                                })
                            await ws.send_text(json.dumps({
                                "type": "tool_call", "tool": "javis_autoshrink",
                                "content": (f"⚙ Vượt hạn mức {_limit_hit.get('limit', 0):,} "
                                            f"{_LIMIT_KIND_LABEL.get(_limit_hit.get('kind') or '', 'token')}, "
                                            f"đang rút gọn ngữ cảnh xuống {_target:,} token rồi thử lại..."),
                            }))
                            or_messages = _shrink_messages(or_messages, _target)
                        if _limit_hit:
                            final_text = final_text or _limit_autoshrink_message(
                                prov, actual_model, _limit_hit)
                            await ws.send_text(json.dumps({
                                "type": "error", "content": final_text,
                            }))
                        await ws.send_text(json.dumps({
                            "type": "response", "content": final_text, "engine": prov,
                            "model": actual_model, "session_id": conv_sid,
                            **_ctx_frame(runtime_trace, _ctx_in),
                        }))
            else:
                # ===== PROVIDER anthropic-cli - qua Claude Code, đầy đủ MCP / skill / session =====
                cli.model = api_model or mcfg.get("claude_model") or None   # alias opus/sonnet/haiku/fable
                # Cùng luật với Codex: mạch phình quá ngưỡng thì thôi --resume, mở mạch mới.
                # Claude Code cũng tự quản transcript nên Javis chỉ có đúng con số token vào
                # của lượt trước làm dấu hiệu.
                _cli_xoay_mach = bool(cli.session_id) and compaction.nen_mach_thue_bao(
                    _row0.get("last_input_tokens"), msg_count=_row0.get("msg_count"),
                    rotated_at=_row0.get("thread_rotated_msg"))
                if _cli_xoay_mach:
                    cli.session_id = None
                    store.mark_thread_rotated(conv_sid)
                    _CONTEXT_RUNTIME.record_runtime_event(
                        runtime_trace, "thread.rotated",
                        {"engine": "claude-code",
                         "last_input_tokens": int(_row0.get("last_input_tokens") or 0),
                         "threshold": compaction.SUBSCRIPTION_THREAD_MAX_TOKENS})
                    await ws.send_text(json.dumps({
                        "type": "tool_call", "tool": "javis_nen_mach",
                        "content": ("⚙ Mạch hội thoại đã dài "
                                    f"({int(_row0.get('last_input_tokens') or 0):,} token mỗi lượt), "
                                    "Javis mở mạch mới."),
                    }))
                sysprompt, _sub_plan = await _subscription_system_prompt(
                    "cli", cli.model or mcfg.get("claude_model") or "mặc định", kind)
                cli.system_prompt = sysprompt
                _apply_mcp(cli, brain=brain)   # gắn MCP do Javis quản lý (nhiều shop POSCake...)
                _streamed = ""      # phần đã stream - phương án dự phòng khi luồng đứt trước 'final'
                _cli_sid = None
                _cost = None
                _cli_prompt = _cli_think(reasoning, user_message)
                if not cli.session_id:
                    # Bỏ --resume là Claude Code mất sạch mạch cũ. Mở mạch mới mà không mang
                    # theo gì thì đó không phải tiết kiệm, đó là làm hỏng hội thoại: người
                    # dùng hỏi tiếp "cái đó" và Javis không còn biết "cái đó" là gì. Mồi lại
                    # từ transcript SQLite, đúng cách nhánh Codex/Gemini vẫn làm.
                    #
                    # Điều kiện là KHÔNG CÓ MẠCH chứ không phải "vừa xoay mạch" như bản cũ.
                    # Mạch trống còn xảy ra ở ba ca khác ngoài xoay chủ động: đường tắt
                    # (fast path) vừa dọn liên kết mạch và TIN rằng lượt sau mồi lại từ
                    # SQLite (xem `clear_native_threads` ở nhánh đường tắt); lượt trước
                    # đứt trước sự kiện `final` nên chưa kịp lưu id; và update/restart làm
                    # rollout cũ biến mất. Bản cũ chỉ mồi khi xoay nên cả ba ca kia đều mở
                    # mạch tay không - Javis quên sạch cuộc đang nói dở (người dùng báo
                    # 18/08: hỏi tiếp "ok tra và so sánh giúp anh" và Javis hỏi lại "so
                    # sánh gì?"). Phiên MỚI thật sự thì get_messages rỗng và
                    # bootstrap_prompt tự trả về nguyên prompt, không tốn gì.
                    _cli_raw = [{"role": _m["role"], "content": _m["content"]}
                                for _m in store.get_messages(conv_sid)[:-1]
                                if _m["role"] in ("user", "assistant") and _m.get("content")]
                    _cli_prompt = compaction.bootstrap_prompt(
                        _cli_raw, _cli_prompt,
                        summary=_row0.get("compact_summary") or "")
                _CONTEXT_RUNTIME.observe_payload(
                    runtime_trace,
                    [{"role": "system", "content": sysprompt},
                     {"role": "user", "content": _cli_prompt}],
                    provider="cli", model=cli.model or mcfg.get("claude_model") or "mặc định",
                )
                async for event in cli.query(_cli_prompt):
                    etype = event["type"]
                    if etype == "tool_call":
                        await ws.send_text(json.dumps({"type": "tool_call", "tool": event["name"], "content": f"⚙ Đang gọi: {event['name']}"}))
                    elif etype == "tool_result":
                        await ws.send_text(json.dumps({"type": "tool_result", "content": event["content"][:200]}))
                    elif etype == "text":
                        _streamed += event["content"]
                        await ws.send_text(json.dumps({"type": "stream", "content": event["content"]}))
                    elif etype == "final":
                        final_text = event.get("content") or final_text
                        _cli_sid = event.get("session_id")
                        _cost = event.get("cost_usd")
                        if _cli_sid:
                            store.set_cli_session_id(conv_sid, _cli_sid)
                        _ctx_in += int(event.get("tokens_in", 0) or 0)
                        usage_store.record("cli", cli.model or mcfg.get("claude_model") or "mặc định",
                                           event.get("tokens_in", 0), event.get("tokens_out", 0), event.get("cost_usd") or 0)
                        _CONTEXT_RUNTIME.record_usage(
                            runtime_trace, event.get("tokens_in", 0), event.get("tokens_out", 0))
                    elif etype == "error":
                        # Hết lượt gói Claude thì Claude Code in nguyên văn câu tiếng Anh (có khi
                        # là dạng máy "…reached|<epoch>"). Dịch sang câu nói được TRƯỚC khi đẩy
                        # ra khung chat, và giữ lại làm final_text để lượt này còn lưu được.
                        _noi = _subscription_limit_message(event.get("content") or "", "claude-code")
                        if _noi:
                            _CONTEXT_RUNTIME.record_runtime_event(
                                runtime_trace, "subscription.limit_reached",
                                {"engine": "claude-code",
                                 "model": cli.model or mcfg.get("claude_model") or "mặc định"})
                            final_text = final_text or _noi
                        await ws.send_text(json.dumps({
                            "type": "error", "content": _noi or event["content"]}))
                # Khung `response` PHẢI nằm NGOÀI vòng lặp. Trước đây nó nằm trong nhánh
                # `final`, nên luồng đứt trước khi có `final` (engine chết, mạng rớt) là client
                # không nhận `response` nào cả và bong bóng chat treo mãi - trong khi phần chữ
                # đã stream ra thì vẫn còn đó. Ba nhánh engine kia vốn đã gửi ngoài vòng lặp.
                final_text = final_text or _streamed
                await ws.send_text(json.dumps({
                    "type": "response", "content": final_text, "session_id": conv_sid,
                    "cli_session_id": _cli_sid, "cost_usd": _cost, "engine": "cli",
                    "model": (mcfg.get("claude_model") or "mặc định"),
                    **_ctx_frame(runtime_trace, _ctx_in)}))

            # Token VÀO của lượt vừa xong. Với engine gói thuê bao đây là DẤU HIỆU DUY NHẤT
            # cho biết mạch hội thoại của chúng đã phình tới đâu: Claude Code và Codex tự quản
            # transcript ở phía chúng, Javis không đếm được bằng cách nào khác. Lượt sau đọc
            # con số này để quyết định có mở mạch mới hay không (xem compaction).
            # Chỉ ghi khi ĐO ĐƯỢC: lượt lỗi trả 0 mà ghi đè thì tưởng mạch vừa được dọn.
            if _ctx_in > 0:
                try:
                    store.set_last_input_tokens(conv_sid, _ctx_in)
                except Exception as _e:
                    print(f"[last_input_tokens] {type(_e).__name__}: {_e}", file=sys.stderr)

            # Lưu lượt assistant: kho phiên + title + log Memory + hàng đợi tự học.
            # Đường lưu DÙNG CHUNG với Telegram (_persist_turn) - nó tự bóc khối điều khiển.
            if final_text:
                await _persist_turn(store, conv_sid, brain, user_message, final_text)
                # Hứa "xong em báo" mà không có việc nền nào → nói thẳng ra ngay dưới câu trả
                # lời. Đẩy thành bong bóng RIÊNG (không sửa câu của model, và câu đó cũng đã
                # stream xong từ lâu). push_to_chat ghi kho phiên trước rồi mới bắn WebSocket
                # nên F5 vẫn còn - người dùng cần thấy dòng này đúng lúc họ quay lại đợi.
                try:
                    _canh_bao = await _canh_bao_hua_suong(
                        brain, WEB_CHAT_PREFIX + conv_sid, final_text, runtime_trace)
                    if _canh_bao:
                        await push_to_chat(conv_sid, _canh_bao)
                except Exception as _e:
                    print(f"[hua suong] {type(_e).__name__}: {_e}", file=sys.stderr)
                # Nén NỀN phần lịch sử cũ sắp rơi khỏi cửa sổ (chỉ engine API - CLI tự quản
                # context). Lỗi nén không ảnh hưởng lượt chat; lượt sau vẫn còn fallback trim.
                if (not used_fast_path and kind == "api" and api_key and
                        prov in ("openrouter", "openai", "anthropic-api", "gemini", "groq")):
                    try:
                        asyncio.create_task(compaction.maybe_compact(
                            store, conv_sid, prov, api_key, api_model, _api_stream))
                    except Exception as _e:
                        print(f"[compact hook] {_e}", file=__import__('sys').stderr)
            return final_text

        async def run_turn(conv_sid, user_message, brain, turn_tag, runtime_trace=None,
                           has_attachments=False):
            _trace_token = context_runtime.bind_trace(runtime_trace)
            try:
                final_text = await _do_turn(
                    conv_sid, user_message, brain, turn_tag, runtime_trace, has_attachments
                )
                _record_quality_shadow(
                    runtime_trace, user_message, final_text or "", "dashboard")
                _CONTEXT_RUNTIME.finish(
                    runtime_trace,
                    "COMPLETED_WITH_ERROR" if runtime_trace and runtime_trace.had_error else "COMPLETED",
                )
            except asyncio.CancelledError:
                _CONTEXT_RUNTIME.finish(runtime_trace, "CANCELLED", "cancelled")
                await send_raw({"type": "system", "content": "Đã dừng lượt này.", "session_id": conv_sid,
                                **context_runtime.event_fields(runtime_trace)})
            except Exception as e:
                _CONTEXT_RUNTIME.note_error(runtime_trace, type(e).__name__)
                _CONTEXT_RUNTIME.finish(runtime_trace, "FAILED", type(e).__name__)
                await send_raw({"type": "error", "content": f"Lỗi xử lý: {type(e).__name__}: {e}",
                                "session_id": conv_sid, **context_runtime.event_fields(runtime_trace)})
            finally:
                context_runtime.reset_trace(_trace_token)
                await send_raw({"type": "turn_done", "session_id": conv_sid,
                                **context_runtime.event_fields(runtime_trace)})
                _CHAT_RUNTIME.finish_job(conv_sid, asyncio.current_task())

        while True:
            raw = await _real_ws.receive_text()
            payload = json.loads(raw)
            action = payload.get("action")
            if action == "reset":
                continue                        # client tự quản phiên; reset KHÔNG còn giết lượt nào
            if action == "stop":
                _sid = payload.get("session_id") or ""
                _tag = _CHAT_RUNTIME.cancel_session(_sid)
                if _tag:
                    cancel_all(_tag)     # giết subprocess engine của đúng lượt đó
                continue
            user_message = payload.get("message", "").strip()
            if not user_message:
                continue
            brain = payload.get("brain", "brain")
            mcfg = cfgmod.read_settings().get("model", {})
            # Phiên đã ghim model riêng thì engine_label phải suy từ provider HIỆU LỰC
            # của phiên, không phải từ mặc định chung - nhãn sai là clear_codex_thread_id
            # dọn nhầm/không dọn mạch native khi đổi engine.
            _prow = store.get_session(payload.get("session_id") or "") or {}
            prov, kind, api_key, api_model = _chat_provider_for_session(mcfg, _prow)
            engine_label = ("codex" if prov == "openai-oauth"
                            else "gemini-cli" if prov == "gemini-cli"
                            else "antigravity-cli" if prov == "antigravity-cli"
                            else prov if ((kind == "api" and api_key) or kind == "oauth")
                            else "cli")
            conv_sid = store.get_or_create(
                payload.get("session_id"), brain=_brain_key(brain), engine=engine_label,
                model=(api_model or mcfg.get("claude_model")))
            # ĐÓNG DẤU model từ tin đầu (chủ chốt 16/08): mỗi lượt bảo đảm ghim của
            # phiên == model ĐANG CHẠY THẬT của lượt này. Phủ một lúc ba ca:
            #   - phiên mới / phiên cũ chưa ghim → đóng dấu model hiệu lực, từ đây đổi
            #     mặc định chung không bao giờ đổi ngược cuộc đang dở;
            #   - ghim hỏng (provider mất key, đã rơi về mặc định chung) → thay bằng
            #     model đang chạy thật, thanh model thôi khoe ghim chết;
            #   - ghim lành → resolved == ghim, không có gì để ghi (no-op).
            if ((_prow.get("pinned_provider") or "").strip() != prov
                    or (_prow.get("pinned_model") or "") != (api_model or "")):
                try:
                    store.set_pinned_model(conv_sid, prov, api_model or "")
                except Exception:
                    pass
            # Đổi bộ não giữa chừng: mạch native của MỌI engine khác engine đang chạy lượt
            # này lập tức thành stale, vì nó không chứa lượt sắp diễn ra. Quay lại engine đó
            # mà cứ nối tiếp mạch cũ là nó mù đúng đoạn ở giữa, rồi trả lời lạc đề - đúng
            # điều người dùng báo 22/08.
            #
            # Bản trước chỉ dọn Codex, bỏ sót Claude Code và Gemini CLI. Nay hỏi thẳng kho
            # phiên để luật nằm ở MỘT chỗ: thêm engine giữ phiên mới thì sửa bảng trong
            # sessions.py, không phải nhớ thêm một lệnh clear ở đây.
            _da_don_mach = store.clear_native_threads(conv_sid, keep=engine_label)
            if _da_don_mach:
                print(f"[chat] đổi engine sang {engine_label!r}, dọn mạch stale: "
                      f"{', '.join(_da_don_mach)}", file=sys.stderr)
            if _CHAT_RUNTIME.get_job(conv_sid):
                await send_raw({"type": "error", "content": "Phiên này đang trả lời - đợi lượt hiện tại xong đã.", "session_id": conv_sid})
                continue
            store.append_message(conv_sid, "user", user_message)
            turn_tag = f"chat:{conv_sid[:12]}:{uuid.uuid4().hex[:8]}"
            runtime_trace = _CONTEXT_RUNTIME.start_turn(conv_sid, brain, "dashboard")
            has_attachments = bool(payload.get("attachments") or payload.get("files"))
            task = asyncio.create_task(run_turn(
                conv_sid, user_message, brain, turn_tag, runtime_trace, has_attachments))
            _CHAT_RUNTIME.register_job(
                conv_sid, task, turn_tag,
                runtime_task_id=runtime_trace.task_id if runtime_trace else "",
                runtime_step_id=runtime_trace.step_id if runtime_trace else "",
            )
    except WebSocketDisconnect:
        pass
    finally:
        # Chỉ bỏ subscriber; job server tiếp tục chạy và tự lưu kết quả.
        _CHAT_RUNTIME.remove_client(client_id)


# ============================================================
# Tab Code - Terminal
#
# Cửa duy nhất vào terminal là WebSocket dưới đây, và nó đòi ĐÚNG cookie phiên đăng nhập như
# /ws. Cố ý KHÔNG mở cho token API: token `full` sinh ra để script gọi REST, còn đây là chạy
# lệnh tuỳ ý trên máy chủ - mở rộng cửa đó thì mỗi token dán nhầm chỗ thành một shell.
# Toàn bộ phần khó (pty, tiến trình, bộ đệm màn hình) nằm trong server/terminal.py.
# ============================================================
def _terminal_cwd(brain: str) -> str:
    """Thư mục shell mở ra. Từ 0.35.8: mặc định là HOME của user đang chạy Javis - "cmd gốc
    của máy" như mọi terminal bình thường (chủ chốt 16/08).

    Trước đây mở ở gốc brain và điều đó gây hại thật cho việc chính của tab này (cài + đăng
    nhập CLI): `agy` coi thư mục đang đứng là project của nó nên đăng nhập trong brain vừa
    khó vừa vấy file cấu hình vào vault. Cần thao tác brain thì shell đã có sẵn biến
    $JAVIS_BRAIN - `cd "$JAVIS_BRAIN"` là về. Máy nào muốn khác thì đặt JAVIS_TERMINAL_CWD."""
    rieng = str(os.getenv("JAVIS_TERMINAL_CWD", "")).strip()
    if rieng and os.path.isdir(rieng):
        return rieng
    try:
        home = str(Path.home())
        if os.path.isdir(home):
            return home
    except Exception:
        pass
    try:
        goc = _brain_root(brain)
        if os.path.isdir(goc):
            return goc
    except Exception:
        pass
    return CLAUDE_CWD


@app.get("/terminal/status")
async def terminal_status(brain: str = Query("brain")):
    return terminal.trang_thai(_terminal_cwd(brain))


@app.post("/terminal/close")
async def terminal_close(session: str = Form(...)):
    """Đóng hẳn một phiên (nút 'Phiên mới' trên giao diện). Khác với đóng tab: đóng tab chỉ là
    thôi xem, shell vẫn chạy tiếp."""
    return {"ok": terminal.KHO.dong(session)}


@app.websocket("/ws/terminal")
async def terminal_ws(ws: WebSocket, session: str = Query(""), brain: str = Query("brain"),
                      cols: int = Query(80), rows: int = Query(24)):
    if cfgmod.gate_active() and not cfgmod.valid_session(ws.cookies.get("javis_session", "")):
        await ws.close(code=1008)
        return
    await ws.accept()

    async def bao_loi(msg: str):
        try:
            await ws.send_text(json.dumps({"type": "error", "error": msg}))
        except Exception:
            pass
        await ws.close()

    if not terminal.bat():
        await bao_loi("Terminal đang tắt trên máy này (biến môi trường JAVIS_TERMINAL=0).")
        return
    try:
        phien = terminal.KHO.mo(session, _terminal_cwd(brain), cols, rows, asyncio.get_running_loop(),
                                extra_env={"JAVIS_BRAIN": str(_brain_root(brain))})
    except RuntimeError as e:
        await bao_loi(str(e))
        return
    except Exception as e:
        await bao_loi(f"Không mở được terminal: {type(e).__name__}: {e}")
        return

    q = phien.gan()
    await ws.send_text(json.dumps({
        "type": "hello", "session": phien.id, "che_do": phien.che_do,
        "shell": Path(phien.argv[0]).name if phien.argv else "", "cwd": phien.cwd,
        "song": phien.song(),
    }))

    async def bom_ra():
        """Một chiều: hàng đợi của phiên -> trình duyệt.

        GOM gói trước khi gửi. Lệnh in nhanh (`cat` file to, `npm install`) đẩy ra hàng nghìn
        mẩu nhỏ; gửi mỗi mẩu một khung WebSocket thì trình duyệt nhận đúng chỗ nghẽn. Gom lại
        thành một khung là cùng bấy nhiêu chữ nhưng ít hơn hẳn số vòng.
        """
        while True:
            goi = await q.get()
            if goi.get("type") == "out":
                gom = [goi["data"]]
                do_dai = len(goi["data"])
                while do_dai < 256_000:
                    try:
                        tiep = q.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    if tiep.get("type") != "out":
                        q.put_nowait(tiep)      # gói khác loại (exit): trả lại, gửi ở vòng sau
                        break
                    gom.append(tiep["data"])
                    do_dai += len(tiep["data"])
                goi = {"type": "out", "data": "".join(gom)}
            await ws.send_text(json.dumps(goi))

    async def bom_ra_an_toan():
        # Trình duyệt đóng giữa chừng thì send_text ném; nuốt ở đây để asyncio khỏi kêu
        # "Task exception was never retrieved" - vòng nhận tin bên dưới sẽ tự thấy và thoát.
        try:
            await bom_ra()
        except Exception:
            pass

    bom = asyncio.create_task(bom_ra_an_toan())
    try:
        while True:
            raw = await ws.receive_text()
            try:
                m = json.loads(raw)
            except Exception:
                continue
            t = m.get("type")
            if t == "in":
                phien.go(str(m.get("data") or ""))
            elif t == "resize":
                phien.doi_co(m.get("cols"), m.get("rows"))
            elif t == "sig" and m.get("name") == "int":
                phien.ngat()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        bom.cancel()
        # CHỈ gỡ người xem: shell chạy tiếp để đổi trang/F5 không giết mất việc đang chạy.
        # Không ai quay lại trong terminal.REAP_GIAY thì vòng dọn sẽ đóng nó.
        phien.go_ra(q)


# ============================================================
# Phiên hội thoại - list / view / search / rename / delete (sqlite + fts5)
# /sessions/search KHAI BÁO TRƯỚC /sessions/{id} để không bị nuốt làm path param.
# ============================================================
@app.get("/sessions")
async def sessions_list(brain: str = Query(None), limit: int = Query(50),
                        project: str = Query("")):
    """project: bỏ trống = mọi hội thoại; "none" = cuộc chưa xếp nhóm; còn lại = id project."""
    return {"sessions": get_store().list_sessions(limit=limit, brain=_brain_keys(brain),
                                                  project=project or None)}


@app.get("/sessions/search")
async def sessions_search(q: str = Query(...), brain: str = Query(None), limit: int = Query(30)):
    return {"results": get_store().search(q, limit=limit, brain=_brain_keys(brain))}


@app.get("/sessions/{session_id}")
async def sessions_get(session_id: str):
    store = get_store()
    sess = store.get_session(session_id)
    if not sess:
        return JSONResponse({"error": "not found"}, status_code=404)
    sess["messages"] = store.get_messages(session_id)
    return sess


@app.post("/sessions/{session_id}/rename")
async def sessions_rename(session_id: str, title: str = Form(...)):
    get_store().rename(session_id, title)
    return {"ok": True}


@app.post("/sessions/{session_id}/delete")
async def sessions_delete(session_id: str):
    get_store().delete(session_id)
    # Phase 8 state is a disposable projection; purge it with the source transcript.
    if _ADAPTIVE_CONTEXT is not None:
        try:
            _ADAPTIVE_CONTEXT.state.delete(session_id)
        except Exception:
            pass
    return {"ok": True}


@app.post("/sessions/{session_id}/pin")
async def sessions_pin(session_id: str, pinned: str = Form("1")):
    """Ghim hội thoại lên đầu danh sách (hoặc bỏ ghim khi pinned=0)."""
    get_store().set_pinned(session_id, str(pinned).strip() not in ("0", "false", ""))
    return {"ok": True}


@app.get("/sessions/{session_id}/meta")
async def sessions_meta(session_id: str):
    """Row phiên KHÔNG kèm messages - cho model bar hỏi 'phiên này ghim model gì' mà
    không phải kéo cả hội thoại về (GET /sessions/{id} trả nguyên cả messages).

    Kèm `pin_ok`: ghim còn dùng được không (provider còn tồn tại + còn key). Server
    rơi về mặc định chung khi ghim hỏng, nên UI mà cứ vẽ 'ghim' theo DB là hai tầng
    nói hai chuyện khác nhau - cờ này để thanh model nói đúng sự thật."""
    sess = get_store().get_session(session_id)
    if not sess:
        return JSONResponse({"error": "not found"}, status_code=404)
    pp = (sess.get("pinned_provider") or "").strip()
    if pp:
        d = _provider_def(pp)
        mcfg = cfgmod.read_settings().get("model", {})
        key = mcfg.get(d["key_field"], "") if d and d.get("key_field") else ""
        sess["pin_ok"] = bool(d) and (d.get("kind") != "api" or bool(key))
    return sess


@app.post("/sessions/{session_id}/model")
async def sessions_set_model(session_id: str, provider: str = Form(""),
                             model: str = Form(""), brain: str = Form("")):
    """Ghim model riêng cho phiên (provider rỗng = gỡ ghim, quay về mặc định chung).

    Có `brain` thì tạo hàng nếu phiên chưa tồn tại - dashboard mint id phía client nên
    user có thể đổi model trước cả tin nhắn đầu tiên (cùng khuôn /sessions/{id}/project).
    CHỦ Ý không đi qua _set_main_model: hàm đó ghi mốc nhật ký usage cho việc đổi bộ não
    TOÀN CỤC, ghim theo phiên mà đi qua đó là rác hoá biểu đồ token."""
    prov = (provider or "").strip()
    if prov and not _provider_def(prov):
        return JSONResponse({"error": f"provider không tồn tại: {prov}"}, status_code=400)
    ok = get_store().set_pinned_model(session_id, prov, model, brain=(brain or "").strip() or None)
    if not ok:
        return JSONResponse({"error": "phiên không tồn tại"}, status_code=404)
    return {"ok": True, "pinned_provider": prov or None, "pinned_model": (model or "").strip() or None}


@app.post("/sessions/{session_id}/project")
async def sessions_set_project(session_id: str, project_id: str = Form(""),
                               brain: str = Form("")):
    """Xếp hội thoại vào project (project_id rỗng = gỡ khỏi nhóm).

    Có `brain` thì tạo hàng nếu hội thoại chưa kịp tồn tại: dashboard mint id ở phía client
    ngay lúc bấm gửi, nên đây là cách duy nhất để chat mới tạo trong lúc đang mở một project
    rơi đúng vào project đó ngay từ tin nhắn đầu. Xem sessions.set_project.
    """
    pid = (project_id or "").strip()
    store = get_store()
    if pid and not store.get_project(pid):
        return JSONResponse({"error": "project không tồn tại"}, status_code=404)
    if not store.set_project(session_id, pid, brain=(brain or "").strip() or None):
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"ok": True}


# ============================================================
# Project = nhóm hội thoại người dùng tự gom. Xoá project chỉ GỠ NHÃN, không xoá hội thoại.
# ============================================================
@app.get("/projects")
async def projects_list(brain: str = Query(None)):
    return {"projects": get_store().list_projects(brain=brain)}


@app.post("/projects")
async def projects_create(name: str = Form(...), icon: str = Form(""),
                          brain: str = Form("brain")):
    if not (name or "").strip():
        return JSONResponse({"error": "thiếu tên project"}, status_code=400)
    pid = get_store().create_project(name, icon=icon, brain=brain or "brain")
    return {"ok": True, "id": pid}


@app.post("/projects/{project_id}/update")
async def projects_update(project_id: str, name: str = Form(None), icon: str = Form(None)):
    store = get_store()
    if not store.get_project(project_id):
        return JSONResponse({"error": "not found"}, status_code=404)
    store.update_project(project_id, name=name, icon=icon)
    return {"ok": True}


@app.post("/projects/{project_id}/delete")
async def projects_delete(project_id: str):
    store = get_store()
    if not store.get_project(project_id):
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"ok": True, "detached": store.delete_project(project_id)}


@app.get("/runtime/diagnostics")
async def runtime_diagnostics(hours: float = Query(24.0), limit: int = Query(200),
                              brain: str = Query("brain")):
    """Spec mục 27: trang chẩn đoán cho admin.

    Chỉ trả metadata đã có sẵn trong runtime.db. Không objective (đang mã hoá),
    không actor hash, không excerpt evidence, không arguments. Trang này để trả lời
    "token đi đâu", không phải để đọc lại hội thoại.
    """
    snapshot = _CONTEXT_RUNTIME.diagnostics_snapshot(limit=limit, hours=hours)
    settings = cfgmod.read_settings().get("context_runtime") or {}
    canaries = {}
    for key, value in settings.items():
        if isinstance(value, dict) and "allocation_basis_points" in value:
            canaries[key] = {
                "allocation_basis_points": value.get("allocation_basis_points", 0),
                "policy_version": value.get("policy_version", ""),
                # Đếm thôi, không trả nội dung rule: chúng chứa hạn mức tài khoản thật.
                "quota_rules": len(value.get("quota_profiles") or value.get("models") or []),
                "allowlist": len(value.get("capability_profiles")
                                 or value.get("allowed_slugs") or []),
            }
    registry = {}
    try:
        registry = _CAPABILITY_REGISTRY.integrity_check()
    except Exception as exc:
        registry = {"error": type(exc).__name__}
    return {**snapshot, "canaries": canaries, "registry": registry,
            # Provider đã tra được hạn mức gợi ý - để trang Chẩn đoán dựng ô chọn thay vì
            # bắt người vận hành nhớ tên provider nào có preset.
            "quota_presets": model_limits.known_providers(),
            # Token đã đốt trong 60 giây qua, gộp MỌI nguồn. Đây là thứ trả lời được câu
            # "sao canary bị chặn trong khi tôi có chat gì đâu": loop nền vừa ăn hết hạn mức.
            "tpm_window": quota_scheduler.snapshot(60),
            # Hạn mức Javis TỰ HỌC từ lỗi nhà cung cấp trả về. Khác quota_presets ở chỗ
            # đây là số thật của tài khoản này, do chính nhà cung cấp nói ra.
            "learned_limits": limit_learner.snapshot(),
            # Mức tiết kiệm token đang chọn + danh sách mức, để giao diện vẽ ba nút thay
            # vì bắt người dùng tự hiểu 10 đường canary và đơn vị basis point.
            "preset": current_preset(settings),
            "presets": [{"id": k, **{x: v[x] for x in ("nhan", "mo_ta")}}
                        for k, v in RUNTIME_PRESETS.items()],
            # Mức đang chạy là do NGƯỜI DÙNG chọn, hay chỉ là mặc định của bản đã cài? Hai
            # thứ đó trông y hệt nhau trên màn hình mà ý nghĩa ngược nhau: cái sau sẽ đi lên
            # theo bản cập nhật, cái trước thì không. Nói ra để người dùng biết mình đang ở
            # đâu, và biết rằng bấm một mức là ghim lại.
            "preset_nguon": str((settings.get("preset_choice") or {}).get("source") or ""),
            "preset_mac_dinh": cfgmod.PRESET_MAC_DINH,
            # Bộ não đang chạy có ăn được phần tiết kiệm này không. Câu hỏi đầu tiên của
            # người dùng khi mở trang, mà trước đây trang không trả lời được: bảng canary
            # chỉ hiện allocation, còn việc engine của họ có nằm trong provider_kinds hay
            # không thì phải SSH đọc settings.json mới biết.
            "engine_hien_tai": _engine_runtime_view(settings),
            # Mỗi mức tiết kiệm được bao nhiêu phần trăm. Không có con số này thì ba nút chỉ
            # là ba cái tên, người dùng bấm mà không biết đổi được gì.
            "uoc_tinh": await _uoc_tinh_tiet_kiem(brain),
            # Và con số ĐO ĐƯỢC từ chính các lượt đã chạy, đáng tin hơn hẳn ước lượng.
            "do_duoc": _do_duoc_tiet_kiem(snapshot.get("tasks") or [],
                                          snapshot.get("window_hours") or 24,
                                          cfgmod.read_settings().get("model", {}) or {}),
            # Lý do LẶP LẠI nhiều nhất khiến lượt không đi được đường tắt. Đây là câu trả lời
            # cho "sao chưa lần nào thấy chữ Tức thì" - thứ trước đây chỉ đoán được.
            "vi_sao": _vi_sao_chua_di_tat(snapshot.get("tasks") or [])}


def _ctx_frame(trace, tokens_in) -> dict:
    """Cho khung chat biết lượt vừa rồi đi đường nào và tốn bao nhiêu token vào.

    Vì sao cần: trước đây không có cách nào biết một lượt đã đi đường tiết kiệm hay lặng lẽ
    tụt về đường cũ - phải đợi tới lúc nhà cung cấp báo vượt hạn mức mới lộ ra, mà lúc đó thì
    đã muộn. Một dòng nhỏ dưới câu trả lời biến thứ vô hình thành thứ nhìn thấy được.

    Không có trace thì coi như đường cũ: nói "chưa rõ" ở đây chỉ làm người đọc phân vân, mà
    đường cũ đúng là thứ chạy khi runtime chưa gắn vào."""
    try:
        path = str(getattr(trace, "execution_path", "") or "")
    except Exception:  # noqa: BLE001 - phần hiển thị, không được phá lượt chat
        path = ""
    return {"ctx_path": path if path and path != "unassigned" else "legacy",
            "ctx_in": max(0, int(tokens_in or 0))}


async def _uoc_tinh_tiet_kiem(brain: str = "brain") -> dict:
    """Mỗi mức tiết kiệm được bao nhiêu PHẦN TRĂM token mỗi request.

    Đo trên prompt THẬT của brain đang chọn, không phải con số quảng cáo. Người dùng bấm một
    mức mà không biết nó đổi được gì thì bấm cũng như không - đó là lý do trang này bị chê
    "không hiểu dùng như nào".

    Ba con số:
      - Tắt: gửi nguyên CLAUDE.md + chỉ mục bộ nhớ + khối skill + mô tả tool.
      - Tối ưu: capsule nhỏ thay chỗ CLAUDE.md, vẫn kèm mô tả tool.
      - Siêu tiết kiệm: như trên, và câu hỏi đơn giản đi thẳng không kèm mô tả tool.

    Dùng CHÍNH hệ số ký tự-trên-token mà runtime đang dùng để ước lượng, để con số ở đây và
    con số ở chỗ khác không đá nhau. Đây là ƯỚC LƯỢNG: bộ đếm token thật của từng nhà cung
    cấp khác nhau, và tiếng Việt có dấu tốn hơn tiếng Anh. Giao diện phải nói rõ là ước lượng.
    """
    # Gọi thẳng hàm endpoint trong test thì tham số mặc định vẫn là object Query(...) chứ
    # không phải chuỗi. Không chặn ở đây là cả bảng ước tính im lặng trả rỗng, và test đi qua
    # endpoint chỉ đo được cái vỏ.
    if not isinstance(brain, str) or not brain.strip():
        brain = "brain"
    try:
        cfg = cfgmod.read_settings().get("context_runtime") or {}
        ratio = max(1.0, float(cfg.get("estimate_chars_per_token") or 3.0))
    except Exception:  # noqa: BLE001 - phần thông tin, không được làm sập trang
        ratio = 3.0

    def tok(text: str) -> int:
        return int(math.ceil(len(str(text or "")) / ratio))

    def _dung_prompt_cu() -> str:
        return build_system_prompt(brain) + channel_context.build_channel_block(
            "dashboard", {"session_id": "uoc-tinh"}, telegram_running=bool(_TG_BOT),
            port=_javis_port(), brain_root=_brain_root(brain))

    try:
        # build_system_prompt quét cây skill và đọc file, khoảng 18ms - đẩy sang thread để
        # trang chẩn đoán không chặn vòng lặp sự kiện.
        cu = tok(await asyncio.to_thread(_dung_prompt_cu))
    except Exception:  # noqa: BLE001
        return {}
    try:
        cc = context_compiler
        vien = tok(cc.CORE_CONTRACT
                   + "Runtime identity: provider=x; model=y. "
                   + cc.ContextCompiler._channel_contract("dashboard")
                   + cc.dong_ho()
                   + cc.ContextCompiler._output_contract_text("dashboard"))
    except Exception:  # noqa: BLE001
        return {}
    try:
        # discover_all trả danh sách ĐÃ qua tầng lazy - tức đúng thứ được gửi đi thật, không
        # phải kho tool đầy đủ. Lấy nhầm bản đầy đủ là thổi phồng con số tiết kiệm.
        spec, _route = await mcp_hub.discover_all(mode="full", vault_root=_brain_root(brain))
        cong_cu = tok(json.dumps(spec, ensure_ascii=False))
    except Exception:  # noqa: BLE001 - thiếu tool thì tính phần còn lại, đừng bỏ cả bảng
        cong_cu = 0

    goc = max(1, cu + cong_cu)

    def muc(token_moi_request: int) -> int:
        return max(0, min(99, round((1 - token_moi_request / goc) * 100)))

    # Đường tắt của mức "Siêu tiết kiệm" (fast path) CHỈ chạy trên engine dùng API key: nó
    # nằm trong nhánh `kind == "api"` của _do_turn, và provider_kinds mặc định của nó cũng
    # chỉ có "api". Với gói thuê bao (Claude Code, ChatGPT) thì mức đó y hệt mức Tối ưu.
    # Vẫn khoe "giảm 96%" cho họ là hứa một con số không bao giờ tới - đúng kiểu knob xoay
    # mà đèn không sáng. Nên đo xong thì kiểm luôn xem bộ não đang chạy có ăn được không.
    # ĐỌC cấu hình thật, KHÔNG gõ cứng. Bản trước viết `fast_hop = _kind == "api"` vì lúc đó
    # đường tắt mới chỉ chạy trên engine API key. Tới 0.14.0 nó mở cho cả gói ChatGPT, mà dòng
    # gõ cứng này không ai nhớ sửa - nên trang vẫn dán nhãn "không áp cho bộ não đang dùng"
    # lên đúng mức vừa được mở, và chủ repo bấm vào rồi tưởng mình bấm nhầm. Đọc thẳng
    # provider_kinds của đường tắt thì lần sau mở thêm bộ não nào, trang tự đúng theo.
    try:
        _st = cfgmod.read_settings()
        _prov, _kind, _k, _m = _chat_provider(_st.get("model", {}) or {})
        _kinds_tat = [str(x) for x in (((_st.get("context_runtime") or {}).get("canary") or {})
                                       .get("provider_kinds") or ["api"])]
    except Exception:  # noqa: BLE001 - phần thông tin, không được làm sập trang
        _kind, _kinds_tat = "api", ["api"]
    fast_hop = _kind in _kinds_tat
    max_token = vien if fast_hop else (vien + cong_cu)
    return {
        "chu_ky_ky_tu_tren_token": ratio,
        "la_uoc_luong": True,
        "kind_bo_nao": _kind,
        "chi_tiet": {"claude_md_va_bo_nho": cu, "capsule": vien, "mo_ta_cong_cu": cong_cu},
        "muc": {
            "off": {"token_moi_request": goc, "phan_tram": 0, "ap_dung": True,
                    "ghi_chu": "Gửi nguyên bộ luật, bộ nhớ và danh sách skill mỗi lượt."},
            "saving": {"token_moi_request": vien + cong_cu, "phan_tram": muc(vien + cong_cu),
                       "ap_dung": True,
                       "ghi_chu": "Thay bộ luật dài bằng bản rút gọn; nhớ và skill chỉ nạp phần liên quan."},
            "max": {"token_moi_request": max_token, "phan_tram": muc(max_token),
                    "ap_dung": fast_hop,
                    "ghi_chu": ("Như trên, và câu hỏi đơn giản đi thẳng không kèm mô tả công cụ. "
                                "Câu cần tra cứu vẫn đi đường đầy đủ, nên không phải lượt nào "
                                "cũng thấy khác."
                                if fast_hop else
                                "Đường tắt cho câu hỏi đơn giản chưa mở cho loại bộ não đang "
                                "chạy, nên bấm mức này cũng chỉ bằng mức Tối ưu."),
                    },
        },
    }


# Giá THAM KHẢO của 1 TRIỆU token ĐẦU VÀO, đơn vị USD. Chỉ để quy đổi phần token tiết kiệm
# được ra một con số tiền cho dễ hình dung - "giảm 38%" không nói lên điều gì với người đang
# trả tiền, còn "khoảng 40 nghìn một tháng" thì có.
#
# Đây là con số THAM KHẢO và sẽ cũ đi: giá của các nhà cung cấp đổi vài tháng một lần. Nên
# giao diện phải nói rõ là ước lượng, và người dùng đặt được số của chính mình qua
# settings.model.gia_input_1m (USD cho 1 triệu token vào) để đè lên bảng này.
#
# Khớp theo CHUỖI CON của tên model, dài trước ngắn sau, nên "claude-opus-5" ăn mục "opus"
# chứ không rơi về mặc định.
_GIA_INPUT_1M = {
    "opus": 15.0, "sonnet": 3.0, "haiku": 1.0,
    "gpt-5-mini": 0.25, "gpt-5": 1.25, "gpt-4o-mini": 0.15, "gpt-4o": 2.5, "o3": 2.0,
    "gemini-2.5-pro": 1.25, "gemini-2.5-flash": 0.30, "gemini": 0.30,
    "deepseek": 0.30, "llama": 0.10, "qwen": 0.20, "mistral": 0.20, "grok": 2.0,
}
_GIA_INPUT_MAC_DINH = 3.0     # không đoán được model thì lấy mức phổ biến tầm trung
# Mọi con số tiền trên trang Mức dùng đều để nguyên USD. Trước đây có thêm một lớp quy đổi ra
# đồng bằng tỉ giá gõ cứng, và lớp đó chỉ tạo ra một con số thứ ba để sai: giá của mọi nhà
# cung cấp đều niêm yết bằng USD, còn tỉ giá thì trôi và không ai đi cập nhật hằng số đó.


def _ten_model_chinh(mcfg: dict) -> str:
    """Tên model chính đang chạy, lấy từ ĐÚNG chỗ nó nằm.

    `settings["model"]` KHÔNG có khoá `"model"` - tên model nằm ở `main.model`, và với cấu
    hình cũ thì ở `claude_model` / `openrouter_model`. Đọc `mcfg.get("model")` luôn ra rỗng,
    nên mọi phép quy đổi tiền rơi về đơn giá mặc định 3$ bất kể người dùng đang chạy Opus
    (15$) hay Haiku (1$). Sai im lặng: con số vẫn hiện ra, chỉ là sai vài lần.
    """
    m = mcfg or {}
    # Thứ tự có chủ ý:
    #   1. `main.model` - chỗ trang Models ghi vào, đúng nhất khi có.
    #   2. khoá `model` phẳng - KHÔNG tồn tại trong settings thật, nhưng vài chỗ trong server
    #      gọi hàm này với một dict tự dựng kiểu {"model": "..."} để hỏi giá của một model cụ
    #      thể. Bỏ qua nó là lặng lẽ trả lời về một model khác với model được hỏi.
    #   3. `_chat_provider` - bộ giải mà chính đường chat dùng, hiểu cả cấu hình cũ (`engine`).
    #   4. các khoá cũ, chỉ khi ba bước trên đều câm.
    # Bước 4 phải nằm SAU bước 3: `openrouter_model` có sẵn giá trị "openai/gpt-4o-mini" ngay
    # trong cấu hình xuất xưởng, kể cả khi engine đang là anthropic-cli chạy Opus. Dò tay
    # trước là lấy $0,15 thay cho $15 - lệch 100 lần, theo hướng khai thấp phần tiết kiệm.
    ten = ((m.get("main") or {}).get("model") or "").strip()
    if ten:
        return ten
    ten = str(m.get("model") or "").strip()
    if ten:
        return ten
    try:
        _prov, _kind, _key, model = _chat_provider(m)
        if str(model or "").strip():
            return str(model).strip()
    except Exception:  # noqa: BLE001 - phần thông tin, rơi về cách dò tay bên dưới
        pass
    for khoa in ("claude_model", "openrouter_model"):
        v = str(m.get(khoa) or "").strip()
        if v:
            return v
    return ""


def _gia_input_1m(model: str, settings_model: dict = None) -> tuple:
    """(giá USD cho 1 triệu token vào, nguồn của con số đó)."""
    try:
        tay = float((settings_model or {}).get("gia_input_1m") or 0)
        if tay > 0:
            return tay, "tay"
    except (TypeError, ValueError):
        pass
    m = str(model or "").lower()
    for khoa in sorted(_GIA_INPUT_1M, key=len, reverse=True):
        if khoa in m:
            return _GIA_INPUT_1M[khoa], "bang"
    return _GIA_INPUT_MAC_DINH, "mac_dinh"


def _do_duoc_tiet_kiem(tasks: list, window_hours: float = 24.0,
                       settings_model: dict = None) -> dict:
    """Tiết kiệm ĐO ĐƯỢC từ chính các lượt đã chạy, không phải ước lượng.

    Con số này đáng tin hơn hẳn phần ước lượng vì nó là token nhà cung cấp thật sự tính. Đổi
    lại, nó chỉ có khi đã chạy cả hai đường trong cùng cửa sổ thời gian - nên giao diện phải
    chịu được ca "chưa đủ dữ liệu" thay vì hiện 0% một cách vô nghĩa.

    Ngoài phần trăm, trả thêm SỐ TOKEN thật đã tiết kiệm và quy đổi ra tiền. Phần trăm một
    mình không trả lời được câu người dùng thật sự muốn hỏi: "cái công tắc này đáng bao
    nhiêu?". Cách tính token tiết kiệm: mỗi lượt đi đường mới đáng lẽ tốn bằng trung bình của
    đường cũ, nên phần chênh nhân số lượt là phần không phải trả.
    """
    cu, moi = [], []
    for t in tasks or []:
        n = int(t.get("actual_input_tokens") or t.get("estimated_input_tokens") or 0)
        if n <= 0:
            continue
        duong = str(t.get("execution_path") or "")
        if duong in ("legacy", "unassigned"):
            cu.append(n)
        elif duong in ("sources", "fast"):
            moi.append(n)
    out = {"so_luot_cu": len(cu), "so_luot_moi": len(moi),
           "tb_cu": round(sum(cu) / len(cu)) if cu else 0,
           "tb_moi": round(sum(moi) / len(moi)) if moi else 0,
           "phan_tram": 0, "du_du_lieu": bool(cu and moi),
           "token_tiet_kiem": 0, "gio_do": round(float(window_hours or 24), 1),
           "token_thang": 0, "tien": {}}
    if not (out["du_du_lieu"] and out["tb_cu"] > 0):
        return out
    out["phan_tram"] = max(0, min(99, round((1 - out["tb_moi"] / out["tb_cu"]) * 100)))
    chenh = max(0, out["tb_cu"] - out["tb_moi"])
    out["token_tiet_kiem"] = chenh * out["so_luot_moi"]
    # Chiếu ra một tháng theo đúng nhịp của cửa sổ vừa đo. Là PHÉP CHIẾU chứ không phải số đã
    # xảy ra, nên giao diện phải gọi nó là "theo nhịp này" chứ đừng ghi như một hoá đơn.
    gio = max(1.0, float(out["gio_do"]))
    out["token_thang"] = round(out["token_tiet_kiem"] * (24 * 30 / gio))
    gia, nguon = _gia_input_1m(_ten_model_chinh(settings_model or {}), settings_model)
    out["tien"] = {
        "gia_1m_usd": gia, "nguon_gia": nguon,
        "usd": round(out["token_tiet_kiem"] / 1_000_000 * gia, 4),
        "usd_thang": round(out["token_thang"] / 1_000_000 * gia, 2),
    }
    return out


def _vi_sao_chua_di_tat(tasks: list) -> dict:
    """Gộp lý do của những lượt KHÔNG đi đường tắt, xếp theo số lần.

    Vì sao cần con số gộp trong khi bảng "Lượt gần nhất" đã ghi lý do từng lượt: một lý do
    lặp lại 18 trên 20 lượt là một CÁI HỎNG, còn cùng lý do đó xuất hiện 2 lần là chuyện
    bình thường. Bảng từng dòng không phân biệt nổi hai ca đó, và chủ repo đã phải nói bằng
    lời "chưa lần nào thấy chữ Tức thì" thay vì chỉ vào một con số. Đó là lúc trang chẩn đoán
    thua: người dùng biết có gì đó sai mà trang không nói được sai ở đâu.
    """
    dem: dict[str, int] = {}
    tong = 0
    for t in tasks or []:
        if str(t.get("execution_path") or "") == "fast":
            continue
        ly = str(t.get("ly_do") or "").strip()
        if not ly:
            continue
        tong += 1
        dem[ly] = dem.get(ly, 0) + 1
    top = sorted(dem.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    return {"tong": tong, "top": [{"ma": k, "so_lan": v} for k, v in top]}


def _engine_runtime_view(settings: dict) -> dict:
    """Bộ não đang dùng ăn được những đường tiết kiệm nào. Cho trang Tiết kiệm token.

    Mọi lỗi nuốt về một khối "chưa biết": đây là phần THÔNG TIN của trang chẩn đoán, không
    được phép làm chính trang chẩn đoán sập."""
    try:
        prov, kind, _key, model = _chat_provider(cfgmod.read_settings().get("model", {}) or {})
        label = (_provider_def(prov) or {}).get("label") or prov
        thue_bao = kind in ("cli", "oauth")
        hop, khong = [], []
        for name, value in (settings or {}).items():
            if not (isinstance(value, dict) and "allocation_basis_points" in value):
                continue
            if int(value.get("allocation_basis_points") or 0) <= 0:
                continue
            kinds = [str(x) for x in (value.get("provider_kinds") or ["api"])]
            (hop if kind in kinds else khong).append(name)
        if not (hop or khong):
            giai_thich = "Chưa bật mảng nào, nên mọi lượt vẫn đi đường cũ. Chọn một mức ở trên."
        elif hop:
            giai_thich = (f"{label} đang ăn được {len(hop)} mảng tiết kiệm."
                          + (f" {len(khong)} mảng khác không áp cho loại bộ não này."
                             if khong else ""))
        else:
            giai_thich = (f"Đã bật {len(khong)} mảng nhưng không mảng nào áp cho {label}, "
                          "nên thực tế chưa tiết kiệm được gì.")
        return {"provider": prov, "nhan": label, "kind": kind, "model": model or "",
                "loai": "Gói thuê bao" if thue_bao else "API key",
                "duong_hop": sorted(hop), "duong_khong_hop": sorted(khong),
                "giai_thich": giai_thich}
    except Exception:   # noqa: BLE001 - xem docstring
        return {"provider": "", "nhan": "", "kind": "", "model": "", "loai": "",
                "duong_hop": [], "duong_khong_hop": [],
                "giai_thich": "Chưa đọc được cấu hình bộ não."}


def _shrink_messages(messages: list, target_tokens: int) -> list:
    """Co danh sách message xuống dưới `target_tokens`, giữ thứ cần nhất.

    Thứ tự hy sinh, từ bỏ được nhất tới không bỏ được:
      1. Lịch sử hội thoại cũ (bỏ từ cũ nhất).
      2. Phần đuôi của system prompt.
    KHÔNG bao giờ bỏ câu hỏi hiện tại của người dùng - bỏ nó thì có trả lời cũng vô nghĩa.

    target_tokens <= 0 nghĩa là không biết hạn mức: vẫn co bằng cách bỏ lịch sử, vì đó là
    thứ duy nhất chắc chắn giúp được mà không làm hỏng câu trả lời.
    """
    if not messages:
        return messages
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    last_user = rest[-1:] if rest else []
    kept = system + last_user           # bỏ sạch lịch sử, giữ prompt lõi + câu hỏi
    if target_tokens <= 0:
        return kept
    # Vẫn quá thì cắt bớt đuôi system prompt. Ước lượng thô là đủ: đây đã là đường cứu hộ.
    budget_chars = max(1000, int(target_tokens) * 3)
    total = sum(len(str(m.get("content") or "")) for m in kept)
    if total <= budget_chars or not system:
        return kept
    over = total - budget_chars
    trimmed = []
    for m in kept:
        if m.get("role") == "system" and over > 0:
            body = str(m.get("content") or "")
            cut = min(over, max(0, len(body) - 500))
            if cut > 0:
                over -= cut
                body = body[:len(body) - cut] + "\n[... đã rút gọn để vừa hạn mức ...]"
            trimmed.append({**m, "content": body})
        else:
            trimmed.append(m)
    return trimmed


_LIMIT_KIND_LABEL = {
    "tpm": "token mỗi phút", "tpd": "token mỗi ngày",
    "rpm": "số lượt mỗi phút", "rpd": "số lượt mỗi ngày",
    "context": "cửa sổ ngữ cảnh", "rate": "nhịp gọi",
}


def _limit_autoshrink_message(provider: str, model: str, hit: dict) -> str:
    """Câu nói khi nhà cung cấp chặn vì hạn mức. Lời khuyên phải khớp ĐÚNG loại hạn mức.

    Bản trước gộp mọi thứ thành "request quá lớn, rút gọn yêu cầu đi". Với gói Groq - siết
    bốn chiều cùng lúc và cả bốn đều mở đầu bằng "Rate limit reached" - lời khuyên đó sai với
    ba trong bốn trường hợp, và người dùng thấy đúng câu này:

        "groq báo request quá lớn ... Lượt này cần khoảng 0 token, trong khi groq giới hạn
         12,000 token mỗi phút."

    Con số 0 là vì không đọc được gì từ lỗi; con 12.000 thì lấy từ BẢNG TRA SẴN trong code
    chứ không phải từ Groq. Ghép hai thứ đó lại thành một câu nghe như đã hiểu chuyện là kiểu
    hỏng tệ nhất: nó vừa sai, vừa che mất bằng chứng để lần ra cái sai.

    Nguyên tắc bây giờ: biết tới đâu nói tới đó, không biết thì đưa nguyên văn lời nhà cung
    cấp ra chứ không bịa một câu cho tròn.
    """
    limit = int(hit.get("limit") or 0)
    requested = int(hit.get("requested") or 0)
    used = int(hit.get("used") or 0)
    remedy = str(hit.get("remedy") or "")
    nhan = _LIMIT_KIND_LABEL.get(str(hit.get("kind") or ""), "hạn mức")
    raw = str(hit.get("raw") or "").strip()
    cho = float(hit.get("retry_after") or 0)

    if not limit:
        # Không đọc được con số nào. Đây là lúc TUYỆT ĐỐI không được nói như thể đã hiểu.
        loi = f'\n\n{provider} nói nguyên văn: "{raw}"' if raw else ""
        if remedy == "wait" and cho:
            return (f"{provider} đang chặn nhịp gọi, bảo chờ {cho:.0f} giây. "
                    f"Bạn hỏi lại sau chừng đó là được.{loi}")
        return (f"{provider} từ chối lượt này vì hạn mức, nhưng không nói rõ hạn mức nào nên "
                f"Javis chưa biết phải làm gì để qua.{loi}")

    dau = f"{provider} báo vượt {nhan}: hạn mức {limit:,}"
    if used:
        dau += f", đã dùng {used:,}"
    if requested:
        dau += f", lượt này xin thêm {requested:,}"
    dau += ". "

    if remedy == "wait_long":
        # Cửa sổ NGÀY. Rút gọn hoàn toàn vô ích ở đây - nói thẳng ra thay vì để người dùng
        # ngồi cắt câu hỏi cho ngắn rồi vẫn lỗi.
        return (dau + "Đây là hạn mức theo NGÀY nên rút gọn câu hỏi không giúp gì cả. "
                "Phải chờ sang ngày mới, hoặc đổi tạm sang bộ não khác ở trang Models, "
                "hoặc nâng gói với nhà cung cấp.")
    if remedy == "wait":
        khi_nao = f" khoảng {cho:.0f} giây nữa" if cho else " một lát"
        return (dau + f"Cửa sổ hiện tại đã đầy vì các lượt trước, hỏi lại{khi_nao} là được. "
                "Rút gọn câu hỏi không giúp vì hạn mức này đếm theo thời gian.")
    return (dau + "Javis đã tự rút gọn ngữ cảnh và thử lại một lần nhưng vẫn không vừa. "
            + model_limits.blocked_hint(provider, model, requested or limit,
                                        _configured_api_providers()))


def _configured_api_providers() -> tuple:
    """Provider API mà người dùng ĐÃ cắm khoá - để gợi ý đường lui CÓ THẬT.

    Chỉ đọc SỰ TỒN TẠI của khoá, không đọc giá trị. Đây là phần phụ của một câu báo lỗi nên
    mọi trục trặc đều nuốt về rỗng: gợi ý sai còn đỡ hơn làm hỏng chính câu báo lỗi."""
    try:
        mcfg = (cfgmod.read_settings() or {}).get("model") or {}
    except Exception:   # noqa: BLE001 - xem docstring
        return ()
    out = []
    for pdef in PROVIDER_DEFS:
        field = pdef.get("key_field")
        if field and str(mcfg.get(field) or "").strip():
            out.append(pdef["label"])
    return tuple(out)


def _subscription_limit_message(raw: str, engine_hint: str) -> str:
    """Đổi lỗi thô "gói thuê bao hết lượt" thành câu người dùng hiểu. "" nếu không phải.

    Vì sao cần: Claude Code và Codex in ra nguyên văn câu tiếng Anh của nhà cung cấp, có khi
    còn là dạng máy đọc ("Claude AI usage limit reached|1730000000"). Đẩy thẳng chuỗi đó ra
    khung chat là người dùng thấy một lỗi lạ mà không biết phải làm gì - đúng cái kiểu hỏng
    mà dải đỏ "mở terminal gõ /login" từng mắc.

    Ranh giới: KHÔNG tự đổi engine hộ. Chuyển sang một bộ não khác là tiêu hạn mức của một
    tài khoản khác, có khi mất tiền thật - đó là quyết định của người dùng. Việc của câu này
    là nói rõ hết lượt tới bao giờ và bộ não nào đang sẵn sàng.
    """
    try:
        hit = limit_learner.parse_subscription_limit(raw, engine_hint=engine_hint)
        if not hit:
            return ""
        return model_limits.subscription_blocked_hint(hit, _configured_api_providers())
    except Exception:   # noqa: BLE001 - không được để câu báo lỗi tự nó nổ
        return ""


def _canary_keys() -> set:
    """Tên các đường canary hợp lệ, lấy từ CHÍNH _DEFAULT chứ không chép tay.

    Chép tay thì thêm phase mới là danh sách lệch, và endpoint sẽ từ chối một đường có
    thật với lý do 'không tồn tại'. Nguồn sự thật duy nhất là cấu hình mặc định."""
    rt = (cfgmod._DEFAULT.get("context_runtime") or {})
    return {k for k, v in rt.items()
            if isinstance(v, dict) and "allocation_basis_points" in v}


def _canary_inert_reason(entry: dict) -> str:
    """Vì sao đặt allocation > 0 cho đường này sẽ KHÔNG có tác dụng gì. "" nếu ổn.

    Thiết kế fail-closed: thiếu quota profile hoặc allowlist rỗng thì mọi task đều rơi về
    legacy. Cộng với việc canary không báo lỗi khi rơi về legacy (đúng theo thiết kế), kết
    quả là người vận hành bật knob lên rồi ngồi đợi một thứ không bao giờ xảy ra. Chặn ở
    đây để cái im lặng đó thành một câu nói ra được.

    Chỉ soát trường mà đường đó THẬT SỰ CÓ. Hai ca đã cắn:
      - fast path không gọi tool nên không có `capability_profiles`;
      - ba canary Phase 8 (memory, lazy_skill, conversation_state) không có
        `quota_profiles` riêng vì chúng đọc ké từ `context_sources`/`canary`.
    Đòi trường mà đường đó không có nghĩa là từ chối oan một cấu hình hợp lệ, và người vận
    hành nhận một lý do SAI - còn khó hiểu hơn là không chặn."""
    has_quota_field = "quota_profiles" in entry or "models" in entry
    if has_quota_field and not (entry.get("quota_profiles") or entry.get("models")):
        return ("chưa khai quota profile (rolling_tpm, context_window, giá) nên fail-closed "
                "sẽ cho mọi task rơi về legacy")
    has_allowlist_field = "capability_profiles" in entry or "allowed_slugs" in entry
    if has_allowlist_field and not (entry.get("capability_profiles")
                                    or entry.get("allowed_slugs")):
        return "allowlist rỗng nên fail-closed sẽ cho mọi task rơi về legacy"
    return ""


def canary_set_decision(path: str, allocation_basis_points, entry: dict, allow_inert: bool,
                        mode: str = "canary"):
    """Quyết định cho POST /runtime/canary. Hàm THUẦN, trả (status_code, payload).

    Tách khỏi endpoint vì hai lý do. Một, đây là hàng rào duy nhất chặn việc bật một đường
    chắc chắn vô tác dụng, mà hàng rào không kiểm được là hàng rào không tin được. Hai, gọi
    thẳng một hàm FastAPI trong test thì tham số mặc định vẫn là object `Form(...)` (truthy),
    nên test đi qua endpoint chỉ đo được cái vỏ chứ không đo được quyết định.
    status_code 0 nghĩa là cho phép ghi."""
    keys = _canary_keys()
    if path not in keys:
        return 400, {"ok": False, "error": f"đường canary '{path}' không tồn tại",
                     "hop_le": sorted(keys)}
    try:
        bp = int(allocation_basis_points)
    except (TypeError, ValueError):
        return 400, {"ok": False, "error": "allocation_basis_points phải là số"}
    if not 0 <= bp <= 10000:
        return 400, {"ok": False,
                     "error": "allocation_basis_points phải trong khoảng 0..10000 "
                              "(10000 = 100 phần trăm)"}
    # Tắt về 0 LUÔN được phép: đường lui phải rẻ hơn đường tiến, nếu không thì người vận
    # hành sẽ ngại thử.
    if bp > 0 and not allow_inert:
        # `mode` là điều kiện TRÙM: mọi canary đều đòi mode canary/on, nên còn ở shadow thì
        # đặt allocation bao nhiêu cũng vô nghĩa. Bản đầu của rào này soát quota mà QUÊN
        # mode, nên nó để lọt đúng cái kiểu hỏng nó sinh ra để chặn: người vận hành bật lên,
        # endpoint trả ok, và không có gì chạy.
        if str(mode or "").strip().casefold() not in ("canary", "on"):
            return 409, {"ok": False, "can_force": True,
                         "error": f"context_runtime.mode đang là '{mode}', mọi canary chỉ "
                                  "chạy khi mode là 'canary' hoặc 'on'",
                         "goi_y": "đổi mode sang canary trước (POST /runtime/mode), "
                                  "hoặc gửi lại với allow_inert=true nếu cố ý"}
        reason = _canary_inert_reason(entry)
        if reason:
            # Cùng quy ước với POST /reminders: trả can_force kèm lý do thay vì âm thầm làm.
            return 409, {"ok": False, "can_force": True, "error": reason,
                         "goi_y": "khai quota profile trước, hoặc gửi lại với "
                                  "allow_inert=true nếu cố ý bật để quan sát"}
    return 0, {"ok": True, "allocation_basis_points": bp}


_RUNTIME_MODES = cfgmod.RUNTIME_MODES

# Đường canary nào ĐỌC hạn mức ở chỗ nào. Mặc định là đọc của chính mình; ba đường Phase 8 thì
# không có `quota_profiles` riêng mà đọc ké `context_sources` (xem AdaptiveContextCanary._quota).
#
# Vì sao phải viết ra thành bảng: vòng khai hạn mức của /runtime/preset duyệt theo TÊN ĐƯỜNG và
# bỏ qua đường nào không có sẵn khoá `quota_profiles` - tức là bỏ qua đúng ba đường Phase 8. Kết
# quả: bấm mức "Tiết kiệm" thì allocation lên 10000, mode sang canary, mà _quota() vẫn trả None
# nên MỌI lượt rơi về legacy. Knob xoay, đèn không sáng - đúng lỗi người dùng đã báo.
QUOTA_OWNER_OF = {
    "conversation_state_canary": "context_sources",
    "memory_canary": "context_sources",
    "lazy_skill_canary": "context_sources",
}

# Ba MỨC tiết kiệm token, thay cho việc bắt người dùng tự hiểu 10 đường canary và đơn vị
# basis point. Người dùng chỉ cần biết "tiết kiệm ít hay nhiều", còn bên dưới bật đường nào
# là việc của Javis.
#
# Chỉ đưa vào đây những đường CHẠY ĐƯỢC với cấu hình mặc định. readonly_canary,
# orchestrator_canary, write_canary... đều đòi allowlist capability mà mặc định rỗng, nên
# bật chúng chỉ tạo cảm giác đã bật trong khi mọi lượt vẫn rơi về đường cũ.
#
# `mode` và `duong` KHÔNG gõ ở đây mà lấy từ `cfgmod.PRESET_DUONG`. Vì sao: `_ap_muc_mac_dinh`
# bên config phải biết mức xuất xưởng bật những đường nào, mà config không import được main.
# Chép bảng ra hai chỗ thì tới lúc thêm một đường vào mức nào đó, chỗ nâng mặc định vẫn nâng
# theo bảng cũ - lệch âm thầm, đúng kiểu lỗi không ai phát hiện cho tới khi hoá đơn token nói.
def _muc(key: str, nhan: str, mo_ta: str) -> dict:
    p = cfgmod.PRESET_DUONG[key]
    return {"nhan": nhan, "mo_ta": mo_ta, "mode": p["mode"], "duong": dict(p["duong"])}


RUNTIME_PRESETS = {
    # Nhắc tên "Đầy đủ" ngay trong mô tả để nối với nhãn chế độ hiện dưới mỗi câu trả lời và
    # trong bảng đo. Nút thì tên "Tắt" (tắt phần tiết kiệm), còn thứ đang chạy khi tắt thì tên
    # "Đầy đủ" - không buộc hai tên đó lại là người dùng thấy hai thứ khác nhau.
    "off": _muc("off", "Tắt",
                "Chế độ Đầy đủ: gửi mọi thứ cho model mỗi lượt. "
                "An toàn nhất, tốn token nhất."),
    "saving": _muc("saving", "Tối ưu",
                   "Chỉ gửi phần liên quan tới câu hỏi: nhớ có chọn lọc, skill nạp khi cần. "
                   "Giảm mạnh token mỗi lượt, hợp với model bị siết hạn mức."),
    "max": _muc("max", "Siêu tiết kiệm",
                "Như mức Tiết kiệm, cộng thêm đường tắt cho câu hỏi đơn giản không cần "
                "tra cứu gì. Nhanh và rẻ nhất, nhưng mới nhất nên ít được thử nhất."),
}


def _ky_ten_muc(runtime_cfg: dict, level: str) -> dict:
    """Đóng dấu "chính người dùng đã chọn mức này" vào config.

    Đây là thứ duy nhất phân biệt được "cố ý chọn Tắt" với "chưa ai chọn gì, mặc định cũ
    đóng băng lại trong settings.json". Thiếu nó thì mọi lần nâng mặc định về sau đều phải
    chọn giữa hai cái sai: giẫm lên quyết định của người dùng, hoặc để mặc định mới không bao
    giờ tới được máy đã cài. Xem `config._ap_muc_mac_dinh`.

    Gọi từ MỌI endpoint đổi mức tiết kiệm, kể cả đổi tay từng đường: người vào tận phần Nâng
    cao chỉnh allocation rõ ràng là người có ý kiến riêng, đừng nâng của họ lên sau lưng.
    """
    from datetime import datetime, timezone
    dau = {"level": str(level or ""), "source": "user",
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    runtime_cfg["preset_choice"] = dau
    return dau


def current_preset(runtime_cfg: dict) -> str:
    """Cấu hình hiện tại khớp mức nào. "custom" nếu người dùng tự chỉnh tay khác cả ba."""
    cfg = runtime_cfg or {}
    mode = str(cfg.get("mode") or "").casefold()
    on = {k: int((v or {}).get("allocation_basis_points") or 0)
          for k, v in cfg.items()
          if isinstance(v, dict) and "allocation_basis_points" in v}
    bat = {k for k, v in on.items() if v > 0}
    for name, preset in RUNTIME_PRESETS.items():
        want = set(preset["duong"])
        if bat != want:
            continue
        # Mức off không quan tâm mode là gì, vì không đường nào bật thì mode vô nghĩa.
        if name == "off" or mode in ("canary", "on"):
            return name
    return "custom"


@app.get("/runtime/muc")
async def runtime_muc(brain: str = Query("brain")):
    """Đúng những gì trang Mức dùng cần để vẽ khối chọn mức tiết kiệm. Không hơn.

    Tách khỏi `/runtime/diagnostics` có chủ ý. Endpoint kia sinh ra cho người vận hành soi
    máy: nó gánh theo bảng canary tính bằng phần vạn, cửa sổ token 60 giây, hạn mức tự học,
    danh sách task kèm execution_path, kết quả integrity_check của registry. Không thứ nào
    trong đó trả lời được câu hỏi của người dùng cuối - *"tôi nên bấm mức nào"* - mà mỗi thứ
    đều tốn một lượt đọc runtime.db hoặc một vòng quét registry.

    Người dùng cần đúng bốn thứ: có những mức nào, đang ở mức nào, mỗi mức tiết kiệm bao
    nhiêu, và thực tế 24 giờ qua đo được bao nhiêu. Trang Mức dùng gọi endpoint này sau mỗi
    lần đổi mức, nên nó phải rẻ.
    """
    settings = cfgmod.read_settings().get("context_runtime") or {}
    tasks = []
    try:
        tasks = (_CONTEXT_RUNTIME.diagnostics_snapshot(limit=200, hours=24.0) or {}).get("tasks") or []
    except Exception as exc:  # noqa: BLE001 - không đọc được trace thì vẫn phải vẽ được nút
        print(f"[runtime/muc] đọc trace hỏng: {type(exc).__name__}: {exc}", file=sys.stderr)
    return {
        "muc": current_preset(settings),
        "danh_sach": [{"id": k, "nhan": v["nhan"], "mo_ta": v["mo_ta"]}
                      for k, v in RUNTIME_PRESETS.items()],
        # Người dùng đã tự chọn mức, hay đây chỉ là mặc định của bản đã cài? Hai thứ trông y
        # hệt nhau trên màn hình mà ý nghĩa ngược nhau: cái sau còn đi lên theo bản cập nhật.
        "tu_chon": str((settings.get("preset_choice") or {}).get("source") or "") == "user",
        "uoc_tinh": await _uoc_tinh_tiet_kiem(brain),
        "do_duoc": _do_duoc_tiet_kiem(tasks, 24.0, cfgmod.read_settings().get("model", {}) or {}),
        # Cần để nói ĐÚNG về phần quy đổi tiền: người dùng gói thuê bao không trả theo token,
        # nên con số tiền với họ là mức quy đổi chứ không phải tiền mặt tiết kiệm được.
        "engine": _engine_runtime_view(settings),
    }


@app.post("/runtime/preset")
async def runtime_preset_set(level: str = Form(...)):
    """Đặt mức tiết kiệm token. Một thao tác thay cho việc chỉnh mode + 10 allocation.

    Trả về ĐÚNG những gì đã đổi, để giao diện nói được "đã bật cái gì" thay vì im lặng.
    """
    key = str(level or "").strip().casefold()
    preset = RUNTIME_PRESETS.get(key)
    if not preset:
        return JSONResponse({"ok": False, "error": f"mức '{level}' không có",
                             "hop_le": list(RUNTIME_PRESETS)}, status_code=400)
    cfg = cfgmod.read_settings()
    runtime_cfg = cfg.setdefault("context_runtime", {})
    # Đóng mốc TRƯỚC khi đổi, để còn biết mức cũ là gì. Nhật ký mốc là thứ duy nhất cho phép
    # tính đúng tiết kiệm của một kỳ có đổi mức giữa chừng: không có nó thì phải lấy mức hôm
    # nay áp ngược cho cả tháng, và người vừa bật tiết kiệm hôm qua sẽ được khoe một con số
    # tiết kiệm của cả tháng mà họ chưa từng nhận.
    _muc_cu = current_preset(runtime_cfg)
    if _muc_cu != key:
        usage_saving.ghi_moc("muc", key, _muc_cu,
                             f"Đổi chế độ tiết kiệm sang {preset['nhan']}")
    runtime_cfg["mode"] = preset["mode"]
    # Ký tên TRƯỚC khi ghi: từ đây trở đi mức này là quyết định của người dùng, không bản
    # cập nhật nào được nâng nó lên sau lưng.
    _ky_ten_muc(runtime_cfg, key)

    # Đường nào cần hạn mức mà chưa khai thì TỰ KHAI cho provider đang dùng. Không làm bước
    # này thì bấm một mức sẽ bật một đường fail-closed: knob xoay được, đèn không sáng - đúng
    # cái người dùng đã phàn nàn là "ấn vào đặt thì không có gì diễn ra".
    canh_bao = []
    prov, kind_hien_tai, _key, model = _chat_provider(cfg.get("model", {}) or {})
    goi_y = [model_limits.as_quota_profile(x)
             for x in model_limits.suggest_profiles(prov, model or "")]
    for name in sorted({QUOTA_OWNER_OF.get(n, n) for n in preset["duong"]}):
        entry = dict(runtime_cfg.get(name) or {})
        if "quota_profiles" not in entry:
            continue
        # BỔ SUNG chứ không phải "trống thì mới ghi". Bản trước bỏ qua khi danh sách đã có
        # gì đó, nên người đổi bộ não (đúng thứ Javis mời chào: đổi được bộ não) bị kẹt với
        # hạn mức của bộ não CŨ: `_quota` lọc theo provider nên không khớp cái nào, và mức
        # tiết kiệm lặng lẽ ngừng chạy trong khi trang vẫn ghi đang bật.
        co_san = [x for x in (entry.get("quota_profiles") or []) if isinstance(x, dict)]
        da_co = {str(x.get("id") or "") for x in co_san}
        them = [x for x in goi_y if str(x.get("id") or "") not in da_co]
        if them:
            entry["quota_profiles"] = co_san + them
            runtime_cfg[name] = entry
            continue
        if co_san or goi_y:
            continue        # đã có hạn mức dùng được cho bộ não này
        if kind_hien_tai in ("cli", "oauth"):
            # Gói thuê bao không có hạn mức token để khai, và cũng không cần: Phase 8 dùng
            # trần ngữ cảnh ở context_runtime.subscription_context. Cảnh báo ở đây là cảnh
            # báo oan, sẽ dạy người dùng bỏ qua mọi cảnh báo khác.
            continue
        canh_bao.append(
            f"Chưa có bảng hạn mức sẵn cho '{prov}', nên Javis biên soạn ngữ cảnh theo trần "
            "mặc định (context_runtime.api_context). Vẫn tiết kiệm được ngay; sau lần đầu "
            "nhà cung cấp báo vượt hạn mức, Javis dùng đúng con số thật của họ.")

    da_bat, da_tat = [], []
    for name in _canary_keys():
        entry = dict(runtime_cfg.get(name) or {})
        muon = int(preset["duong"].get(name, 0))
        truoc = int(entry.get("allocation_basis_points") or 0)
        entry["allocation_basis_points"] = muon
        runtime_cfg[name] = entry
        if muon > 0 and truoc == 0:
            da_bat.append(name)
        elif muon == 0 and truoc > 0:
            da_tat.append(name)
    cfgmod.write_settings(cfg)
    return {"ok": True, "level": key, "nhan": preset["nhan"],
            "mode": preset["mode"], "da_bat": da_bat, "da_tat": da_tat,
            "dang_bat": sorted(preset["duong"]), "canh_bao": canh_bao,
            "co_hieu_luc_ngay": True}


@app.post("/runtime/mode")
async def runtime_mode_set(mode: str = Form(...)):
    """Đổi `context_runtime.mode`. Đây là công tắc TRÙM của mọi đường canary.

    Vì sao phải có endpoint riêng: mọi canary đều đòi mode là `canary` hoặc `on`, nên còn ở
    `shadow` thì đặt allocation bao nhiêu cũng không có gì chạy. Trước khi có nút này, cách
    duy nhất để đổi là SSH sửa tay settings.json.
    """
    value = str(mode or "").strip().casefold()
    if value not in _RUNTIME_MODES:
        return JSONResponse({"ok": False, "error": f"mode '{mode}' không hợp lệ",
                             "hop_le": list(_RUNTIME_MODES)}, status_code=400)
    cfg = cfgmod.read_settings()
    runtime_cfg = cfg.setdefault("context_runtime", {})
    runtime_cfg["mode"] = value
    # Đổi công tắc trùm cũng là một quyết định về mức tiết kiệm: hạ xuống shadow là cố ý tắt
    # hết. Không ký ở đây thì lần nâng mặc định sau sẽ kéo mode trở lại canary sau lưng.
    _ky_ten_muc(runtime_cfg, current_preset(runtime_cfg))
    cfgmod.write_settings(cfg)
    active = [k for k, v in (cfgmod.read_settings().get("context_runtime") or {}).items()
              if isinstance(v, dict) and int(v.get("allocation_basis_points") or 0) > 0]
    return {"ok": True, "mode": value, "duong_dang_bat": active,
            "luu_y": ("Mode đã sang canary nhưng chưa đường nào có allocation > 0, "
                      "nên vẫn chưa có gì đổi.") if value in ("canary", "on") and not active
                     else ""}


@app.post("/runtime/quota")
async def runtime_quota_apply(provider: str = Form(...), model: str = Form(""),
                              paths: str = Form("")):
    """Khai quota profile cho các đường canary từ bộ hạn mức gợi ý (model_limits).

    Vì sao cần: fail-closed nghĩa là thiếu quota profile thì mọi task rơi về legacy, nên
    trước bước này mọi thao tác bật canary đều vô nghĩa. Trước đây cách duy nhất để khai là
    gõ tay JSON lồng ba tầng vào settings.json.

    `paths` bỏ trống = áp cho MỌI đường canary có trường quota_profiles. Con số là GỢI Ý dựa
    trên tài liệu công khai, người vận hành phải đối chiếu với gói cước thật của mình.
    """
    suggestions = model_limits.suggest_profiles(provider, model)
    if not suggestions:
        return JSONResponse({
            "ok": False,
            "error": f"chưa có hạn mức gợi ý cho provider '{provider}'"
                     + (f" model '{model}'" if model else ""),
            "provider_da_biet": model_limits.known_providers(),
            "goi_y": "khai tay quota_profiles cho đường canary, hoặc bổ sung mục vào "
                     "server/model_limits.py nếu đã tra được hạn mức chính thức",
        }, status_code=404)

    profiles = [model_limits.as_quota_profile(s) for s in suggestions]
    wanted = {p.strip() for p in (paths or "").split(",") if p.strip()}
    keys = _canary_keys()
    if wanted - keys:
        return JSONResponse({"ok": False, "error": "có đường canary không tồn tại",
                             "sai": sorted(wanted - keys), "hop_le": sorted(keys)},
                            status_code=400)

    cfg = cfgmod.read_settings()
    runtime_cfg = cfg.setdefault("context_runtime", {})
    applied = []
    for key in sorted(keys):
        if wanted and key not in wanted:
            continue
        entry = dict(runtime_cfg.get(key) or {})
        # Đường nào dùng 'models' (model router) có hình dạng rule khác hẳn - không áp bừa.
        if "quota_profiles" not in entry:
            continue
        entry["quota_profiles"] = profiles
        runtime_cfg[key] = entry
        applied.append(key)
    cfgmod.write_settings(cfg)
    return {"ok": True, "provider": provider, "model": model or "(mọi model)",
            "so_rule": len(profiles), "da_ap_cho": applied,
            "can_doi_chieu": [s.get("source") for s in suggestions if s.get("verify")],
            "luu_y": "Đây là hạn mức GỢI Ý theo tài liệu công khai. Đối chiếu với gói cước "
                     "thật của tài khoản trước khi tin vào nó."}


@app.post("/runtime/canary")
async def runtime_canary_set(
    path: str = Form(...),
    allocation_basis_points: int = Form(...),
    allow_inert: bool = Form(False),
):
    """Đặt allocation cho MỘT đường canary, an toàn hơn sửa tay settings.json.

    Vì sao cần endpoint riêng thay vì bảo người vận hành tự sửa file: knob nằm sâu hai tầng
    (`context_runtime.<path>.allocation_basis_points`). Endpoint này đọc-sửa-ghi trọn cấu
    hình nên không bao giờ làm mất field anh em, và nó CHẶN trước khi bật một đường chắc
    chắn vô tác dụng (xem `_canary_inert_reason`).
    """
    cfg = cfgmod.read_settings()
    runtime_cfg = cfg.get("context_runtime") or {}
    entry = dict(runtime_cfg.get(path) or {})
    status, payload = canary_set_decision(path, allocation_basis_points, entry,
                                          bool(allow_inert),
                                          str(runtime_cfg.get("mode") or "off"))
    if status:
        return JSONResponse(payload, status_code=status)
    entry["allocation_basis_points"] = payload["allocation_basis_points"]
    rt = cfg.setdefault("context_runtime", {})
    rt[path] = entry
    # Người vào tận phần Nâng cao chỉnh từng đường là người có ý kiến riêng. Ký tên để bản
    # cập nhật sau không nâng cấu hình tay của họ lên theo mặc định mới.
    _ky_ten_muc(rt, current_preset(rt))
    cfgmod.write_settings(cfg)
    # Không cần restart: read_settings cache theo mtime nên lượt kế tiếp đã ăn giá trị mới.
    after = (cfgmod.read_settings().get("context_runtime") or {}).get(path) or {}
    return {"ok": True, "path": path,
            "allocation_basis_points": after.get("allocation_basis_points"),
            "quota_rules": len(after.get("quota_profiles") or after.get("models") or []),
            "allowlist": len(after.get("capability_profiles")
                             or after.get("allowed_slugs") or []),
            "co_hieu_luc_ngay": True}


@app.get("/runtime/tasks/{task_id}")
async def runtime_task_status(task_id: str):
    """Phase 7 status tối thiểu; không trả objective, checkpoint ciphertext hay actor hash."""
    task = _CONTEXT_RUNTIME.get_task(task_id)
    if not task:
        return JSONResponse({"error": "task_not_found"}, status_code=404)
    return {
        "task_id": task["id"], "session_id": task["session_id"],
        "status": task["status"],
        "orchestration_status": task.get("orchestration_status") or "",
        "execution_path": task.get("execution_path") or "",
        "runtime_version": task.get("runtime_version") or "",
        "registry_revision": task.get("registry_revision") or "",
        "policy_version": task.get("canary_policy_version") or "",
        "updated_at": task.get("updated_at"),
    }


@app.post("/runtime/tasks/{task_id}/resume")
async def runtime_task_resume(task_id: str):
    """Resume explicit sau restart; OCC claim ngăn hai request chạy cùng task."""
    task = _CONTEXT_RUNTIME.get_task(task_id)
    if not task:
        return JSONResponse({"error": "task_not_found"}, status_code=404)
    if task.get("execution_path") != "orchestrator" or task.get("status") != "RUNNING":
        return JSONResponse({"error": "task_not_resumable"}, status_code=409)
    if _CHAT_RUNTIME.get_job(str(task.get("session_id") or "")):
        return JSONResponse({"error": "session_is_running"}, status_code=409)
    mcfg = cfgmod.read_settings().get("model", {})
    provider, kind, api_key, model = _chat_provider(mcfg)
    if kind != "api" or not api_key:
        return JSONResponse({"error": "api_provider_required"}, status_code=409)
    try:
        result = await _get_readonly_orchestrator().resume(
            task_id, str(task["session_id"]), provider, model or "?", api_key,
            str(mcfg.get("reasoning") or "off"), None, _api_stream,
        )
    except (ValueError, PermissionError, RuntimeError) as exc:
        return JSONResponse({"error": str(exc)[:160]}, status_code=409)
    if result.tokens_in or result.tokens_out:
        usage_store.record(
            provider, result.model or model or "?", result.tokens_in,
            result.tokens_out, result.cost_usd,
        )
    if result.text:
        get_store().append_message(str(task["session_id"]), "assistant", result.text)
    _CONTEXT_RUNTIME.finish(
        _CONTEXT_RUNTIME.resume_trace(task_id),
        "COMPLETED" if result.status == "COMPLETED" else "COMPLETED_WITH_ERROR",
        result.stop_reason if result.status != "COMPLETED" else "",
    )
    return {
        "ok": result.status == "COMPLETED", "task_id": result.task_id,
        "status": result.status, "stop_reason": result.stop_reason,
        "content": result.text, "model": result.model,
        "model_rounds": result.model_rounds,
        "tokens_in": result.tokens_in, "tokens_out": result.tokens_out,
        "cost_usd": result.cost_usd, "evidence_refs": list(result.evidence_refs),
    }


# ============================================================
# Telegram bot - nhắn Telegram ↔ Javis (dùng engine theo Settings; CLI thì có cả MCP)
# ============================================================
_TG_BOT = None
# ĐA PHIÊN theo tài khoản: mỗi chat_id giữ NGỮ CẢNH RIÊNG để không lẫn hội thoại giữa
# các người dùng chung 1 bot. Map chat_id(str) -> phiên:
#   {"cli": engine Claude|None,   # session Claude riêng (giữ session_id để resume)
#    "or":  list|None,        # lịch sử hội thoại engine OpenRouter/API
#    "last": str|None,        # câu hỏi gần nhất của chat này (cho /retry)
#    "sent": set,             # path đã gửi qua /telegram/send-file trong lượt (chống gửi trùng)
#    "brain": str|None}       # brain RIÊNG của phiên (path); None = brain mặc định (theo Settings)
_TG_SESS = {}

# Map BỀN chat_id -> TÊN brain, sống sót qua restart (khác _TG_SESS bị .clear() mỗi lần bot bật
# lại). Lưu theo TÊN (không phải path tuyệt đối) để bền qua Docker/local + brain đổi chỗ; đọc mới
# resolve tên -> path. Ghi STATE_DIR/tg_brain.json (server state, gitignored, xuyên brain).
_TG_BRAIN_PATH = cfgmod.STATE_DIR / "tg_brain.json"


def _tg_load_brain_map() -> dict:
    try:
        if _TG_BRAIN_PATH.exists():
            d = json.loads(_TG_BRAIN_PATH.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return {str(k): str(v) for k, v in d.items()}
    except Exception:
        pass
    return {}


_TG_BRAIN_MAP = _tg_load_brain_map()


def _tg_save_brain_map() -> None:
    try:
        _atomic_write_text(_TG_BRAIN_PATH, json.dumps(_TG_BRAIN_MAP, ensure_ascii=False, indent=2))
    except Exception as e:
        import sys
        print(f"[tg brain map write] {type(e).__name__}: {e}", file=sys.stderr)


def _tg_session(chat_id):
    """Lấy (tạo nếu chưa có) phiên riêng của 1 chat_id. chat_id rỗng → gộp vào 'default'."""
    key = str(chat_id or "default")
    s = _TG_SESS.get(key)
    if s is None:
        s = {
            "cli": None, "codex": None, "or": None,
            "last": None, "sent": set(), "brain": None,
        }
        _TG_SESS[key] = s
    return s


def _tg_brain(chat_id):
    """Brain của phiên Telegram này. Ưu tiên: phiên sống (RAM) -> map BỀN (chat đã /brain, kể cả
    trước restart) -> brain mặc định (Settings/loop). Map bền lưu TÊN brain nên brain đã xoá/đổi
    tên thì tự dọn entry cũ và rơi về mặc định, không kẹt vào brain không còn."""
    key = str(chat_id or "default")
    sess = _TG_SESS.get(key) or {}
    b = sess.get("brain")
    if b and os.path.isdir(b):
        return b
    name = _TG_BRAIN_MAP.get(key)
    if name:
        p = str(Path(BRAINS_DIR) / name)
        if os.path.isdir(p):
            return p
        _TG_BRAIN_MAP.pop(key, None)   # brain đã biến mất → dọn, khỏi kẹt
        _tg_save_brain_map()
    return _read_loop_config().get("brain", "brain")


def _tg_set_brain(chat_id, brain_path):
    """Đổi brain cho 1 phiên Telegram + reset ngữ cảnh (brain khác = bộ nhớ/skill khác,
    giữ mạch cũ sẽ trộn tri thức 2 vault). Ghi cả phiên sống lẫn map BỀN để sống qua restart."""
    sess = _tg_session(chat_id)
    sess["brain"] = str(brain_path)
    try:
        _TG_BRAIN_MAP[str(chat_id or "default")] = Path(str(brain_path)).name
        _tg_save_brain_map()
    except Exception:
        pass
    if sess.get("cli"):
        sess["cli"].reset_session()
    sess["codex"] = None
    sess["or"] = None
    sess["last"] = None
    sess["sid"] = None     # brain khác = hội thoại khác → mở phiên mới trong kho, đừng trộn


def _tg_chat_busy(chat) -> bool:
    """Chat này đang có lượt trả lời chạy dở không (đa phiên: _current là dict theo chat)."""
    cur = getattr(_TG_BOT, "_current", None)
    if not isinstance(cur, dict):
        return False
    t = cur.get(str(chat)) if chat else None
    return bool(t and not t.done())


def _javis_port() -> int:
    try:
        return int(os.getenv("JAVIS_PORT", "7777"))
    except ValueError:
        return 7777


def _tg_compact_bg(sess, prov, api_key, api_model):
    """Đẩy vòng nén lịch sử in-memory của phiên Telegram sang chạy NỀN.

    Trước đây `compact_mem` được await thẳng trong đường request: phiên đủ dài là user phải
    ngồi chờ xong một vòng tóm tắt (một request LLM nữa) rồi mới thấy câu trả lời của mình.
    Dashboard vốn đã nén nền qua `compaction.maybe_compact`; đây là bản tương ứng.

    Chỉ ÁP kết quả khi lịch sử chưa đổi kể từ lúc bắt đầu nén. Có lượt chen vào giữa thì bản
    nén đã lỗi thời - đè vào là nuốt mất lượt vừa nói; bỏ đi, lượt sau nén lại.
    """
    msgs = sess.get("or")
    if not msgs or sess.get("dang_nen"):
        return
    n = len(msgs)
    sess["dang_nen"] = True

    async def _chay():
        try:
            moi = await compaction.compact_mem(list(msgs), prov, api_key, api_model, _api_stream)
            if sess.get("or") is msgs and len(msgs) == n:
                sess["or"] = moi
        except Exception as _e:
            print(f"[compact_mem nền] {_e}", file=__import__('sys').stderr)
        finally:
            sess["dang_nen"] = False

    try:
        asyncio.create_task(_chay())
    except Exception as _e:
        sess["dang_nen"] = False
        print(f"[compact_mem nền] {_e}", file=__import__('sys').stderr)


# ---- XOAY phiên Telegram: nghỉ lâu hoặc đủ dài thì sang phiên mới ----
# Trên dashboard người dùng tự bấm "+ Hội thoại mới" nên phiên không bao giờ dài mãi. Trên
# Telegram thì gần như KHÔNG AI gõ /reset, nên một Chat ID gắn với một phiên là phiên đó dài
# vô tận chừng nào server chưa restart. Mở nó ra đọc là kéo về cả nghìn tin: openStoredSession
# (dashboard/app.js) vẽ TOÀN BỘ sess.messages, không phân trang - nút "Xem thêm" ở thanh bên
# chỉ phân trang DANH SÁCH hội thoại chứ không phân trang tin trong một cuộc.
#
# Xoay phiên biến một phiên vô hạn thành nhiều phiên hữu hạn, nên phần đọc không phải sửa gì:
# cái tăng lên là SỐ hội thoại, đúng thứ nút "Xem thêm" đã lo sẵn.
#
# QUAN TRỌNG: xoay chỉ xoay BẢN GHI. Ngữ cảnh engine (sess['cli'] của Claude CLI, thread Codex,
# sess['or'] của nhánh API vốn đã có compact_mem lo cửa sổ) KHÔNG bị đụng tới, nên người dùng
# Telegram không hề thấy Javis quên gì - chỉ dashboard là thấy hội thoại chia thành khúc đọc được.
_TG_CONV_IDLE_S = 12 * 3600      # nghỉ quá ngần này → lượt kế mở phiên mới
_TG_CONV_MAX_MSGS = 200          # ~100 lượt hỏi-đáp/phiên → mở phiên mới dù đang chat liên tục
_TG_CONV_ARCHIVE_DAYS = 30       # phiên Telegram nguội quá ngần này → tự cất vào kho lưu


def _tg_conv_sid(store, sess, brain, engine_label, model):
    """Phiên kho cho lượt Telegram này, tự xoay theo hai ngưỡng trên.

    sess['sid'] sống theo RAM giống sess['cli']/['or']/['codex'] - restart server là mạch ngữ
    cảnh đã mất rồi, nên mở phiên mới mới đúng, chứ không nối tiếp phiên cụt. Đổi brain và
    /reset đã tự đặt sess['sid'] = None ở chỗ khác nên ở đây không phải xét lại.
    """
    sid = sess.get("sid")
    if sid:
        row = store.get_session(sid)
        if not row:
            sid = None      # user đã xoá hội thoại đó trên dashboard → đừng hồi sinh id cũ
        else:
            # Chỉ xoay khi có BẰNG CHỨNG phiên đã cũ/đã dài. Thiếu số liệu thì giữ nguyên,
            # kẻo một cột rỗng bất ngờ làm mỗi lượt đẻ một phiên.
            nghi = time.time() - float(row.get("updated_at") or time.time())
            if nghi >= _TG_CONV_IDLE_S or int(row.get("msg_count") or 0) >= _TG_CONV_MAX_MSGS:
                sid = None      # nghỉ lâu / đã dài → sang khúc mới
    if sid:
        # Còn dùng tiếp: đồng bộ engine/model vì người dùng có thể vừa đổi bằng /model.
        sess["sid"] = store.get_or_create(sid, brain=_brain_key(brain), engine=engine_label,
                                          model=model)
        return sess["sid"]
    # `_brain_key`: Telegram cầm ĐƯỜNG DẪN brain, dashboard gửi tên gọi tắt "brain" - ghi
    # nguyên văn thì hai bên lệch khoá và thanh bên không thấy hội thoại Telegram đâu.
    sess["sid"] = store.create_session(brain=_brain_key(brain), engine=engine_label, model=model,
                                       channel="telegram")
    # Dọn theo nhịp XOAY (hiếm, cỡ vài ngày một lần) chứ không mỗi lượt - đủ để thanh bên
    # không ngập dần vì các khúc cũ.
    try:
        n = store.archive_stale("telegram", time.time() - _TG_CONV_ARCHIVE_DAYS * 86400)
        if n:
            print(f"[telegram] cất {n} phiên nguội quá {_TG_CONV_ARCHIVE_DAYS} ngày vào kho lưu",
                  file=__import__('sys').stderr)
    except Exception as e:
        print(f"[telegram archive] {type(e).__name__}: {e}", file=__import__('sys').stderr)
    return sess["sid"]


async def _tg_answer(text, meta=None, progress=None, channel="telegram", bot=None):
    """Vỏ ngoài một lượt KHÔNG-WEBSOCKET: khớp phiên trong kho -> chạy engine -> LƯU lượt.

    `channel` mở hàm này cho kênh thứ ba là CLI (xem docs/dev/2026-08-cli-spec.md). Cố ý
    THÊM THAM SỐ chứ không viết một vỏ riêng: vỏ này là chỗ duy nhất biết cách khớp phiên,
    ghi bộ nhớ hội thoại, gắn trace runtime và chấm chất lượng. Viết bản thứ hai là lượt CLI
    sẽ vắng mặt ở /sessions và ở vòng tự học - đúng lỗ hổng mà nhánh Telegram từng dính
    trước 0.9.244, chỉ khác là lần này biết trước mà vẫn làm.

    Vì sao tách vỏ khỏi lõi: trước 0.9.244 nhánh Telegram không lưu gì cả, nên hội thoại
    Telegram vắng mặt ở `/sessions`, ở `brain/Memory/conversations`, và ở vòng tự học -
    lỗ hổng chức năng lớn nhất trong danh sách trôi lệch giữa hai bản dispatch.

    Quy ước trả về của lõi: **dict = câu trả lời thật** (đáng lưu), **chuỗi = thông báo lỗi**
    (không lưu). Đó là lý do nhánh gateway lịch cũng trả dict chứ không trả chuỗi như trước.
    """
    # ĐA PHIÊN: định tuyến theo chat_id → ngữ cảnh của mỗi tài khoản tách biệt.
    chat_id = str((meta or {}).get("chat_id") or "default")
    if bot:
        # Bot chuyên trách: brain RIÊNG của bot, không phải brain của chủ. Khoá phiên gắn id bot
        # nên hai bot cùng nói chuyện với một khách vẫn là hai mạch tách bạch, và không cái nào
        # đụng vào phiên của chủ. Nhãn kênh "bot:<slug>" để hội thoại khách nằm riêng ở /sessions.
        sess = _tg_session(f"bot:{bot['id']}:{chat_id}")
        brain = bot["brain"]
        channel = f"bot:{bot.get('slug') or bot['id']}"
    else:
        sess = _tg_session(chat_id)
        brain = _tg_brain(chat_id)   # brain riêng của phiên (đổi bằng /brain), mặc định theo Settings
    mcfg = cfgmod.read_settings().get("model", {})
    prov, kind, api_key, api_model = _chat_provider(mcfg)
    # Nhãn engine phải do VỎ quyết định rồi truyền xuống lõi: hai bên tự suy ra độc lập là
    # có ngày phiên bị dán nhãn 'cli' trong khi lượt thật chạy qua OpenRouter.
    engine_label = ("codex" if prov == "openai-oauth"
                    else "gemini-cli" if prov == "gemini-cli"
                    else "antigravity-cli" if prov == "antigravity-cli"
                    else prov if ((kind == "api" and api_key) or kind == "oauth")
                    else "cli")

    # Bản tương ứng của `store.clear_native_threads` bên dashboard, cho ba engine giữ phiên.
    # Cùng một bất biến: engine khác vừa chen một lượt thì mạch của MỌI engine còn lại không
    # chứa lượt đó, nối tiếp là mù đúng đoạn ở giữa. Xoá liên kết thôi, giữ nguyên đối tượng
    # (cwd/instructions vẫn dùng lại được); lượt sau của engine đó bootstrap từ kho phiên.
    #
    # Claude Code (`sess["cli"]`) trước đây BỊ BỎ SÓT ở đây, dù nó là engine hay dùng nhất.
    for _nhan, _khoa in (("gemini-cli", "gemini"), ("codex", "codex"), ("cli", "cli")):
        if engine_label == _nhan or sess.get(_khoa) is None:
            continue
        try:
            _obj = sess[_khoa]
            # Dùng API công khai khi engine có (Claude Code), rơi về gán thẳng cho engine
            # chưa có - khỏi phải rẽ nhánh theo tên engine ở đây.
            if hasattr(_obj, "reset_session"):
                _obj.reset_session()
            else:
                _obj.session_id = None
        except Exception:
            sess[_khoa] = None

    store = get_store()
    conv_sid = ""
    try:
        conv_sid = _tg_conv_sid(store, sess, brain, engine_label,
                                api_model or mcfg.get("claude_model"))
        store.append_message(conv_sid, "user", text)
    except Exception as e:
        print(f"[telegram session] {e}", file=__import__('sys').stderr)

    runtime_trace = _CONTEXT_RUNTIME.start_turn(
        conv_sid or f"{channel}:{chat_id}", brain, channel)
    _CONTEXT_RUNTIME.set_route(runtime_trace, engine_label,
                               api_model or mcfg.get("claude_model") or "mặc định")
    _trace_token = context_runtime.bind_trace(runtime_trace)
    try:
        out = await _tg_answer_engine(
            text, meta, progress, chat_id=chat_id, sess=sess, brain=brain, mcfg=mcfg,
            prov=prov, kind=kind, api_key=api_key, api_model=api_model,
            store=store, conv_sid=conv_sid, channel=channel, bot=bot)

        # Cùng luật với dashboard: hứa "xong em báo" mà không có việc nền nào thì nói thẳng.
        # Ở kênh này tin nhắn CHƯA gửi đi nên nối luôn vào cuối, khỏi phải bắn thêm một tin.
        # Bot chuyên trách đứng ngoài: nó nói chuyện với người lạ và không có quyền giao việc
        # nền, nên dán một dòng nội bộ về điều phối Kanban vào đó là lạc chỗ.
        if not bot and isinstance(out, dict):
            try:
                _canh_bao = await _canh_bao_hua_suong(
                    brain, str(chat_id or ""), out.get("text") or "", runtime_trace)
                if _canh_bao:
                    out["text"] = (out.get("text") or "") + "\n\n" + _canh_bao
            except Exception as e:
                print(f"[hua suong telegram] {type(e).__name__}: {e}", file=__import__('sys').stderr)
        if conv_sid and isinstance(out, dict):
            try:
                await _persist_turn(store, conv_sid, brain, text, out.get("text") or "")
            except Exception as e:
                print(f"[telegram persist] {e}", file=__import__('sys').stderr)
        if isinstance(out, str):
            _CONTEXT_RUNTIME.note_error(runtime_trace, f"{channel}_error_response")
        _record_quality_shadow(
            runtime_trace, text,
            (out.get("text") or "") if isinstance(out, dict) else str(out or ""),
            channel,
        )
        _CONTEXT_RUNTIME.finish(
            runtime_trace,
            "COMPLETED_WITH_ERROR" if runtime_trace and runtime_trace.had_error else "COMPLETED",
        )
        return out
    except asyncio.CancelledError:
        _CONTEXT_RUNTIME.finish(runtime_trace, "CANCELLED", "cancelled")
        raise
    except Exception as e:
        _CONTEXT_RUNTIME.note_error(runtime_trace, type(e).__name__)
        _CONTEXT_RUNTIME.finish(runtime_trace, "FAILED", type(e).__name__)
        raise
    finally:
        context_runtime.reset_trace(_trace_token)


def _tg_ket(clean_out, files, canh_bao="", loi=()):
    """Gói câu trả lời Telegram: cảnh báo hệ thống lên đầu, lỗi giữa lượt xuống cuối.

    Lỗi giữa lượt KHÔNG huỷ câu trả lời (dashboard vốn coi lỗi là không chí mạng), nhưng cũng
    không được giấu: giấu đi thì user tưởng lượt chạy sạch trong khi có tool đã hỏng."""
    txt = (canh_bao or "") + (clean_out or "")
    if loi:
        txt += "\n\n⚠ Có lỗi giữa lượt: " + str(loi[0])
    return {"text": txt, "files": files or []}


# Số lượt hội thoại (user+assistant) giữ lại cho một người nói chuyện với bot. Cắt cứng thay
# vì nén như đường chat của chủ: nén là thêm một lượt gọi model nữa, mà bot trả lời người lạ
# thì cần nhanh và rẻ hơn là cần nhớ dai.
BOT_LICH_SU_MAX = 20

# Danh sách tool cho phép của bot khi phải chạy qua CLI: một chuỗi KHÔNG khớp tool nào.
#
# Không dùng list rỗng được: `claude_sdk_engine` kiểm `if self.allowed_tools:` nên [] là falsy,
# và engine hiểu thành "không có allowlist" rồi chạy thẳng permission_mode="bypassPermissions"
# - tức mở TOÀN QUYỀN đúng lúc mình định khoá chặt nhất. Một chuỗi vô nghĩa thì truthy, cổng
# can_use_tool bật lên, và mọi tool đều rớt khỏi allowlist nên bị từ chối từng lượt gọi.
BOT_KHONG_TOOL = ["__javis_bot_khong_tool__"]


# ------------------------------------------------------------
# Mảnh dùng chung của MỘT lượt bot
# ------------------------------------------------------------
# Hai mức quyền của bot khác nhau đúng MỘT chỗ: có tool hay không. Mọi thứ còn lại (lịch sử,
# ghim đường đo, đọc stream, tính usage, cắt lịch sử) phải giống hệt nhau, nên chúng nằm ở đây
# chứ không chép hai bản. Chép hai bản là cách chắc chắn để một hôm nào đó `usage_store.record`
# có ở đường này mà thiếu ở đường kia - hoá đơn thiếu, và không ai nhìn ra được từ bên ngoài.
def _bot_lich_su(sess):
    if sess.get("bot") is None:
        sess["bot"] = []
    return sess["bot"]


def _bot_cat_lich_su(lich_su):
    if len(lich_su) > BOT_LICH_SU_MAX:
        del lich_su[:len(lich_su) - BOT_LICH_SU_MAX]


def _bot_ghim_duong(runtime_trace, prov, api_model, messages, tools=()):
    """Ghim lượt này vào đường 'bot' trên trang Tiết kiệm token.

    Không ghim thì `pin_execution_path` xếp nó vào 'Đầy đủ' - đường ĐẮT NHẤT - trong khi lượt
    bot là đường rẻ nhất hệ thống (không CLAUDE.md, không MEMORY.md). Trang đo nói ngược sự thật.
    """
    if not runtime_trace:
        return
    _CONTEXT_RUNTIME.set_route(runtime_trace, prov, api_model or "?")
    _CONTEXT_RUNTIME.pin_execution_path(
        runtime_trace, "bot", None, context_runtime.RUNTIME_VERSION, "bot_chuyen_trach")
    _CONTEXT_RUNTIME.observe_payload(runtime_trace, messages, list(tools or []),
                                     provider=prov, model=api_model or "?")


async def _bot_doc_stream(stream, *, progress, runtime_trace, prov, api_model):
    """Đọc MỘT stream của bot: trả (text, [lỗi]). Tính usage, báo tiến độ, không đụng lịch sử.

    Lỗi giữa lượt KHÔNG dừng vòng lặp: một tool hỏng không có nghĩa là cả lượt hỏng, và luồng
    thường vẫn chạy tiếp ra câu trả lời. Đúng cách đường chat của chủ vẫn xử lý.
    """
    out, loi, actual_model = "", [], api_model or "?"
    _pinged = False
    try:
        async for ev in stream:
            t = ev.get("type")
            if t == "text":
                if not _pinged:
                    _pinged = True
                    await progress("✍ Đang soạn câu trả lời…")
                out += ev.get("content") or ""
            elif t == "meta":
                actual_model = ev.get("model") or actual_model
            elif t == "tool_call":
                await progress(f"⚙ Đang dùng công cụ: {ev.get('name', '')}")
            elif t == "usage":
                usage_store.record(prov, actual_model, ev.get("input", 0), ev.get("output", 0))
                _CONTEXT_RUNTIME.record_usage(runtime_trace, ev.get("input", 0), ev.get("output", 0))
            elif t == "error":
                loi.append(str(ev.get("content") or "lỗi không rõ"))
    except Exception as e:
        print(f"[bot {prov}] {type(e).__name__}: {e}", file=__import__('sys').stderr)
        loi.append(str(e))
    return out, loi


def _bot_ket(out, lich_su):
    """Đóng gói câu trả lời của một lượt bot đã chạy được."""
    lich_su.append({"role": "assistant", "content": out})
    _bot_cat_lich_su(lich_su)   # cắt SAU khi thêm, không thì trần bị vượt đúng một lượt mỗi vòng
    return {"text": channel_context.strip_control_blocks(out), "files": []}


# `_bot_cli_du_phong` đã gỡ ở 0.26.17. Nó là đường LUI cho ca "đọc không ra token OAuth nên
# /v1/messages trả 401". Nay không còn token nào để đọc: gói Claude Code chạy thẳng qua binary
# `claude` ngay từ `_api_stream`, nên một đường lui cũng dẫn tới đúng engine ấy là vô nghĩa.


async def _bot_tra_loi(text, *, sess, sysprompt, prov, api_key, api_model, reasoning,
                       progress, runtime_trace, brain=None, chat_id=""):
    """Một lượt của Bot chuyên trách. MỘT đường duy nhất cho CẢ TÁM bộ não.

    Vì sao không đi theo bốn nhánh engine như đường chat của chủ:

    1. **Để đổi bộ não không đổi trải nghiệm.** Đó là lời hứa gốc của Javis. Đi bốn nhánh thì
       Claude Code có Bash, Codex có kho MCP riêng, engine API bị trần 8 vòng gọi tool - ba
       kiểu hành xử khác nhau cho cùng một con bot, và chủ đổi model là khách thấy khác ngay.
       Ở đây mọi engine nhận CÙNG system prompt, CÙNG tài liệu, CÙNG lịch sử, và đều không có
       tool. Khác biệt còn lại đúng bằng khác biệt giữa các model, không phải giữa các đường ống.

    2. **Để cách ly brain là thật, không phải là rào.** Bot không được cấp tool nào cả, nên nó
       KHÔNG CÓ cách nào chạm vào đĩa - khỏi cần cổng duyệt, khỏi cần sandbox, khỏi phải hy
       vọng cwd giữ chân được nó. Trước đó bản 0.21.0 phải khoá allowed_tools cho Claude Code
       và TỪ CHỐI chạy trên Codex vì Codex không khoá được phạm vi đọc. Cả hai chỗ chắp vá đó
       biến mất: không có tool thì không có gì để khoá.

    Tài liệu đã được `chatbot_grounding` tra sẵn bằng Python TRƯỚC khi model chạy và nằm trong
    `sysprompt`, nên bỏ tool không làm bot mất khả năng đọc brain - chỉ bỏ khả năng đi lang
    thang trong đó.

    `_api_stream` phục vụ sáu provider API cộng gói ChatGPT (đi `openai_responses_stream`).
    Gói Claude Code là ngoại lệ DUY NHẤT: nó rẽ sang `_bot_cli_du_phong` ngay dưới đây, tức
    chạy qua binary `claude`. Đắt hơn một nhịp khởi động tiến trình, đổi lại không phải mượn
    token đăng nhập của ai - thứ Anthropic cấm và có khoá tài khoản thật (xem claude_auth.py).

    Đây là đường của mức **Chỉ đọc** - mức mặc định. Bot đặt ở mức Được ghi / Toàn quyền đi
    `_bot_tra_loi_co_tool`. Hai đường tách hẳn nhau CÓ CHỦ Ý: đường này phải soi được bằng mắt
    là không có tool nào, và một test canh đúng thân hàm này (test_chatbot_cach_ly.py mục B2).
    """
    lich_su = _bot_lich_su(sess)
    lich_su.append({"role": "user", "content": text})
    _bot_cat_lich_su(lich_su)

    # System dựng LẠI mỗi lượt: tài liệu tra được đổi theo từng câu hỏi. Giữ system cũ là bot
    # trả lời câu này bằng tài liệu của câu trước.
    messages = [{"role": "system", "content": sysprompt}] + lich_su
    _bot_ghim_duong(runtime_trace, prov, api_model, messages)

    out, loi = await _bot_doc_stream(
        _api_stream(prov, api_key, api_model, messages, reasoning),
        progress=progress, runtime_trace=runtime_trace, prov=prov, api_model=api_model)

    if not out:
        lich_su.pop()   # lượt hỏng thì đừng để câu hỏi treo lơ lửng không có câu trả lời
        if prov == "openai-oauth" and not (openai_oauth.valid_creds() or {}).get("access_token"):
            # Codex không chạy không-tool được nên không có đường dự phòng. Nói đúng việc cần
            # làm thay vì để chủ đọc một mã lỗi HTTP.
            return ("⚠ Chưa đăng nhập được ChatGPT nên bot không gọi được model. "
                    "Vào trang Models kết nối lại tài khoản ChatGPT rồi nhắn lại.")
        return "⚠ " + (loi[0] if loi else "Không nhận được nội dung nào.")
    # Không gửi kèm file: bot ở mức này không tạo được file (không có tool), và quét thư mục
    # brain để tìm file "mới" thì lại là một đường rò tài liệu ra ngoài.
    return _bot_ket(out, lich_su)


# ============================================================
# Bot ở mức Được ghi / Toàn quyền - CÓ tool
# ============================================================
def _bot_stream_co_tool(prov, key, model, messages, reasoning, tools, route,
                        *, brain=None, tag_bot="bot", muc_quyen="full"):
    """Vòng gọi tool cho một lượt bot, đủ CẢ TÁM bộ não.

    Vẫn giữ nguyên lời hứa gốc: đổi bộ não thì trải nghiệm không đổi. Nên hai gói thuê bao
    không bị bỏ lại - ChatGPT đi `responses_with_mcp`, Claude Code đi engine Claude Code thật
    (`_claude_sub_stream_tools`) thay cho đường mượn token OAuth đã gỡ ở 0.26.17.

    Điều đó có một hệ quả PHẢI biết: nhánh Claude Code nay CÓ tool native (Bash, Read,
    WebFetch), khác hẳn sáu nhánh kia. Rào an toàn vì thế không còn tựa vào "không engine nào
    mở CLI" được nữa, mà tựa vào allowlist per-call của `can_use_tool` - xem `_bot_allowlist`.

    `tools` rỗng (hub tắt, hoặc chưa đấu nguồn nào) → rơi về stream không tool. Bot vẫn trả lời
    được thay vì im; chỗ gọi báo cho chủ biết là lượt đó không có công cụ nào.
    """
    if not tools:
        return _api_stream(prov, key, model, messages, reasoning)

    def _vong():
        if prov == "openrouter":
            return engine.openrouter_chat_with_mcp(key, model, messages, reasoning, tools, route)
        if prov == "openai":
            return engine.openai_chat_with_mcp(key, model, messages, reasoning, tools, route)
        if prov == "gemini":
            return engine.gemini_chat_with_mcp(key, model, messages, reasoning, tools, route)
        if prov == "groq":
            return engine.groq_chat_with_mcp(key, model, messages, reasoning, tools, route)
        if prov == "ollama":
            return engine.ollama_chat_with_mcp(key, model, messages, reasoning, tools, route)
        if prov == "openai-oauth":
            creds = openai_oauth.valid_creds() or {}
            return engine.responses_with_mcp(creds.get("access_token", ""), creds.get("account_id", ""),
                                             _codex_safe_model(model), messages, reasoning, tools, route)
        if prov == "anthropic-cli":
            # Gói Claude Code: qua binary `claude` + hub, không mượn token đăng nhập của ai.
            # `tools` chỉ dùng để BIẾT lượt này có công cụ hay không - engine tự đấu hub bằng
            # config riêng mang brain của bot, nên không phải chuyển danh sách schema sang.
            # Bốn lớp rào giữ đúng hợp đồng cách ly: xem `_claude_sub_stream_tools`.
            return _claude_sub_stream_tools(model, messages, reasoning, brain=brain,
                                            tag=tag_bot, mode=muc_quyen)
        return engine.anthropic_chat_with_mcp(key, model, messages, reasoning, tools, route)

    # Nhà cung cấp gãy tạm thời thì thử lại - nhưng dừng ngay khi tool đầu tiên đã chạy, vì từ
    # đó lượt này đã chạm vào thế giới thật.
    return engine.thu_lai_khi_tam_thoi(_vong, nhan=f"bot {prov}/{model or 'mặc định'}")


async def _bot_tra_loi_co_tool(text, *, sess, sysprompt, prov, api_key, api_model, reasoning,
                               progress, runtime_trace, brain, chat_id, muc_quyen):
    """Một lượt của bot ở mức **Được ghi** (auto) hoặc **Toàn quyền** (full).

    Khác `_bot_tra_loi` đúng một thứ: có tool. Mọi thứ còn lại - prompt của Agent, tài liệu tra
    sẵn, lịch sử, cách đọc stream - dùng chung mã, nên hai mức không trôi xa nhau.

    **Tool ở đây CHỈ đến từ hub MCP, không có tool native nào.** Đó là điều kiện để nới quyền
    mà không phá rào đã có:

    1. **Cách ly brain vẫn nguyên.** Tool file của hub đi qua `mcp_hub._safe_path(vault_root,…)`
       với `vault_root` là brain CỦA CHÍNH BOT, nên trèo sang brain khác thì nổ ValueError chứ
       không trả rỗng. Nếu mở tool native của Claude Code thì `Read` đọc được đường dẫn tuyệt
       đối bất kỳ - đúng lỗ mà 0.21.0 đã phải vá.
    2. **Không lệnh máy, không lang thang web.** Không Bash, không WebFetch, không WebSearch,
       không Task - vì chúng vốn không nằm trong hub.
    3. **Mức quyền là lớp CỨNG, không phải lời dặn.** `muc_quyen` đi thẳng vào `discover_all`
       rồi thành header `X-Javis-Mode`: mức `auto` thì hub tự chặn nhóm nguy hiểm (tiền, đơn,
       gửi tin, đăng bài) ngay tại chỗ gọi, bất kể prompt nói gì và khách dụ khéo cỡ nào.

    Cái KHÔNG còn nữa, và chủ phải biết trước khi bật: ở mức này người điều khiển tool là KHÁCH
    LẠ. Rào còn lại chỉ là quy định trong file Agent, mà chữ thì lách được. Vì thế nâng mức đòi
    một cú xác nhận có ý thức (`chatbot_store.can_xac_nhan`), và trang Chatbot nói thẳng cái
    mất được trước khi chủ bấm.

    Vẫn KHÔNG tự đính kèm file như đường chat của chủ, dù ở mức này bot tạo được file thật.
    `collect_turn_files` quét thư mục brain tìm file "mới", và với người lạ thì đó là một đường
    rò tài liệu: hỏi một câu vu vơ đúng lúc có file khác vừa sinh ra là nhận được nó. Bot muốn
    đưa file cho khách thì nói đường dẫn trong câu trả lời.
    """
    lich_su = _bot_lich_su(sess)
    lich_su.append({"role": "user", "content": text})
    _bot_cat_lich_su(lich_su)
    messages = [{"role": "system", "content": sysprompt}] + lich_su

    # vault_root = brain CỦA BOT. Đây là một tham số, không phải một quy ước - truyền nhầm brain
    # của chủ vào đây là mở toang đúng thứ cả tính năng này đang giữ.
    tools, route = [], {}
    try:
        tools, route = await mcp_hub.discover_all(muc_quyen, vault_root=_brain_root(brain))
    except Exception as e:
        print(f"[bot {prov} chat {chat_id}] nạp tool hỏng: {type(e).__name__}: {e}",
              file=__import__('sys').stderr)
    _bot_ghim_duong(runtime_trace, prov, api_model, messages, tools)

    out, loi = await _bot_doc_stream(
        _bot_stream_co_tool(prov, api_key, api_model, messages, reasoning, tools, route,
                            brain=brain, tag_bot=f"bot:{chat_id}", muc_quyen=muc_quyen),
        progress=progress, runtime_trace=runtime_trace, prov=prov, api_model=api_model)

    # Engine KHÔNG chạy nổi vòng tool: trả lời lại lượt này mà bỏ tool đi.
    #
    # Không phải phòng xa. Bản 0.24.0 nối mức Được ghi của gói ChatGPT vào
    # `engine.responses_with_mcp`, một hàm tới lúc đó CHƯA TỪNG được gọi từ đâu và tự ghi
    # EXPERIMENTAL trong docstring. Chạy thật thì nó trả rỗng, và hậu quả không dừng ở "tính
    # năng mới chưa chạy": MỌI câu người ta nhắn cho bot đều nhận một lời xin lỗi kỹ thuật, tức
    # nâng mức quyền làm HỎNG con bot vốn đang chạy tốt. Nâng quyền không được phép lấy đi năng
    # lực đã có.
    #
    # Nên đường lui: vẫn trả lời, chỉ là không có công cụ. Và tuyệt đối KHÔNG im lặng về việc
    # đó - chủ đặt mức Được ghi mà bot lặng lẽ chạy như mức Chỉ đọc là đúng kiểu hỏng tệ nhất.
    # Cảnh báo đi kèm câu trả lời, lên thẻ bot, và nói luôn việc cần làm.
    canh_bao = ""
    if not out and tools:
        print(f"[bot {prov} chat {chat_id}] vòng tool rỗng ({loi[0] if loi else '?'}), "
              f"trả lời lại KHÔNG tool", file=__import__('sys').stderr)
        out, loi2 = await _bot_doc_stream(
            _api_stream(prov, api_key, api_model, messages, reasoning),
            progress=progress, runtime_trace=runtime_trace, prov=prov, api_model=api_model)
        if out:
            canh_bao = (f"Engine đang chạy ({_api_label(prov)}) không gọi được công cụ cho bot, "
                        f"nên lượt vừa rồi trả lời ở mức Chỉ đọc chứ không phải mức "
                        f"{chatbot_store.MUC_NHAN.get(muc_quyen, muc_quyen)} bạn đã đặt. "
                        f"Cần bot làm việc thật thì đổi engine ở trang Models, hoặc hạ mức bot "
                        f"xuống Chỉ đọc cho khỏi hiểu nhầm.")
            loi = []
        else:
            # Gãy CẢ đường không-tool thì lỗi đáng báo là lỗi của đường đó, không phải lỗi vòng
            # tool. Đường không-tool là lời gọi đơn giản nhất còn lại, nên nó nói đúng bệnh hơn:
            # hết quota, sai token, mạng chết. Báo lỗi vòng tool trước là đẩy chủ đi tìm xem
            # engine có hỗ trợ tool không, trong khi thứ hỏng là cái khác hẳn.
            loi = loi2 + loi

    if not out:
        lich_su.pop()   # lượt hỏng thì đừng để câu hỏi treo lơ lửng không có câu trả lời
        if prov == "openai-oauth" and not (openai_oauth.valid_creds() or {}).get("access_token"):
            return ("⚠ Chưa đăng nhập được ChatGPT nên bot không gọi được model. "
                    "Vào trang Models kết nối lại tài khoản ChatGPT rồi nhắn lại.")
        return "⚠ " + (loi[0] if loi else "Không nhận được nội dung nào.")
    if not tools:
        # Bot được đặt ở mức có quyền mà lại chẳng có công cụ nào - im lặng ở đây thì chủ tưởng
        # bot đang làm việc, còn thực tế nó chỉ đang nói chuyện.
        canh_bao = (f"Bot đang ở mức {chatbot_store.MUC_NHAN.get(muc_quyen, muc_quyen)} nhưng "
                    f"chưa có nguồn dữ liệu nào đấu vào, nên không có công cụ nào để dùng. "
                    f"Đấu thêm ở trang Kết nối, hoặc hạ mức bot xuống Chỉ đọc.")
        print(f"[bot {prov} chat {chat_id}] mức '{muc_quyen}' nhưng hub không trả tool nào - "
              f"lượt này chỉ chat", file=__import__('sys').stderr)
    ket = _bot_ket(out, lich_su)
    if canh_bao:
        ket["canh_bao"] = canh_bao
    return ket


async def _tg_answer_engine(text, meta, progress, *, chat_id, sess, brain, mcfg,
                            prov, kind, api_key, api_model, store=None, conv_sid="",
                            channel="telegram", bot=None):
    """Lõi 4 nhánh engine của một lượt Telegram. Trả dict khi có câu trả lời thật,
    trả CHUỖI khi là thông báo lỗi (vỏ `_tg_answer` dựa vào đó để biết lượt nào đáng lưu)."""
    sess["last"] = text
    sess["sent"] = set()    # lượt mới → reset dedupe (endpoint /telegram/send-file add vào đây)
    reasoning = _reasoning_level(mcfg)
    runtime_trace = context_runtime.current_trace()

    # NGÔN NGỮ cho lượt này. Dính theo TỪNG CUỘC CHAT (chat_id), không theo tiến trình: một
    # bot Telegram phục vụ nhiều người, và ngôn ngữ của người này không được tràn sang người
    # kia.
    #
    # Với bot chuyên trách thì ngôn ngữ do BẢN GHI BOT quyết, và cố ý KHÔNG truyền
    # `reply_pref` của chủ xuống: bot ghim "auto" nghĩa là "bám theo khách", còn tràn cài đặt
    # của chủ vào đó là phá đúng lý do trường `ngon_ngu` tồn tại - chủ người Việt bán cho
    # khách Nhật thì ngôn ngữ của chủ là thông tin SAI để suy ra ngôn ngữ của bot.
    _lc_kenh = cfgmod.read_settings().get("locale") or {}
    _lang_qd = lang_mod.resolve(
        turn_text=text,
        chatbot_pin=(bot or {}).get("ngon_ngu") or "",
        reply_pref=("" if bot else (_lc_kenh.get("reply_lang") or "auto")),
        channel_default=("vi" if channel == "zalo" and not bot else ""),
        ui_lang=("" if bot else (_lc_kenh.get("ui_lang") or "")),
    )
    try:
        _CONTEXT_RUNTIME.record_runtime_event(runtime_trace, "lang.resolved", _lang_qd.as_trace())
    except Exception:
        pass

    async def _p(s):
        # Báo trạng thái trung gian về kênh (Telegram) cho user đỡ lo khi chờ. Bỏ qua nếu lỗi.
        if progress:
            try:
                await progress(s)
            except Exception:
                pass
    # Block kênh (port gateway hermes-agent): engine biết đang trả lời qua đâu, ai đang nhắn,
    # và cách gửi file trả về (auto-attach + endpoint send-file).
    # telegram_running phải theo kênh THẬT: bật cờ đó cho lượt CLI là dạy Javis một công thức
    # gửi file qua Telegram trong khi người hỏi đang ngồi ở terminal.
    # Bot chuyên trách KHÔNG dùng system prompt của Javis: prompt đó dạy cách điều phối, ghi
    # vault, giao việc - toàn thứ bot trả lời người ngoài không được làm. Nó dùng prompt của
    # chính Agent nó trỏ tới. Xem chatbot_runtime.build_bot_prompt.
    if bot:
        import chatbot_runtime
        # Prompt của bot KHÔNG kèm block kênh: block đó dạy cách tự gửi file qua Telegram và
        # nêu đường dẫn thư mục thật của brain - kiến thức vận hành, không phải thứ đưa cho
        # một con bot đang nói chuyện với người lạ.
        _sys_bot = chatbot_runtime.build_bot_prompt(bot)
        # Mức quyền đọc từ BẢN GHI, và giá trị lạ (file sửa tay, bản ghi cũ) rơi về Chỉ đọc.
        # Fail-closed là bắt buộc ở đây: đoán sai theo hướng kia là cấp tool cho một con bot
        # đang nói chuyện với người lạ.
        _muc = str((bot or {}).get("muc_quyen") or "").strip().lower()
        if _muc in chatbot_store.MUC_NANG:
            return await _bot_tra_loi_co_tool(
                text, sess=sess, sysprompt=_sys_bot, prov=prov, api_key=api_key,
                api_model=api_model, reasoning=reasoning, progress=_p,
                runtime_trace=runtime_trace, brain=brain, chat_id=chat_id, muc_quyen=_muc)
        return await _bot_tra_loi(text, sess=sess, sysprompt=_sys_bot,
                                  prov=prov, api_key=api_key, api_model=api_model,
                                  reasoning=reasoning, progress=_p, runtime_trace=runtime_trace,
                                  brain=brain, chat_id=chat_id)
    # ===== Hệ Tiết kiệm cho kênh NGOÀI dashboard =====
    #
    # Tới 0.23.1, cả Tối ưu lẫn Siêu tiết kiệm chỉ được nối vào đúng handler WebSocket của
    # dashboard: mọi lệnh gọi prepare() ở đó truyền cứng chữ "dashboard", và khối này không
    # có một dòng nào chạm tới chúng. Hệ quả là người dùng bấm mức tiết kiệm ở trang Cài đặt,
    # trang báo xanh "đã bật", rồi mỗi lượt Telegram vẫn gửi nguyên CLAUDE.md + MEMORY.md.
    # Không lỗi, không cảnh báo - chỉ có hoá đơn token không giảm ở đúng kênh dùng nhiều nhất.
    #
    # Hai tầng nối ở đây, theo thứ tự rẻ dần:
    #   1. Đường tắt (Phase 5): câu không cần tra cứu thì gọi model MỘT vòng với capsule nhỏ.
    #   2. Nguồn chọn lọc (Phase 8): thay CLAUDE.md + MEMORY.md bằng prompt gọn hơn.
    #
    # Bot chuyên trách KHÔNG đi qua đây - nó thoát khỏi hàm này từ trên, và prompt của nó
    # (~20 token) vốn đã nhỏ hơn capsule của mức Siêu tiết kiệm (~460 token) hơn hai chục lần.
    # Phase 8 (mức Tối ưu): thay CLAUDE.md + MEMORY.md bằng nguồn chọn lọc. Gọi qua
    # `_get_adaptive_context()` chứ không kiểm biến global - biến đó dựng LƯỜI, còn None cho
    # tới lần gọi đầu tiên, nên kiểm nó là khối này không bao giờ chạy.
    #
    # Truyền [] làm lịch sử: `conversation_state_canary` cố ý KHÔNG mở cho kênh này, vì phiên
    # Telegram đã giữ mạch hội thoại riêng (sess["or"] cho engine API, session/thread cho hai
    # gói thuê bao). Đưa thêm transcript vào system prompt là gửi lịch sử HAI LẦN.
    sysprompt = ""

    def _nen_goc(include_memory: bool, include_skills: bool) -> str:
        return build_adaptive_source_prompt(
            brain, include_memory=include_memory, include_skills=include_skills)

    try:
        _p8 = await asyncio.to_thread(
            _get_adaptive_context().prepare, runtime_trace, text, _brain_root(brain),
            str(conv_sid or chat_id), [], channel, prov,
            api_model or mcfg.get("claude_model") or "mặc định", kind, _nen_goc)
        if _p8.action == "use":
            sysprompt = _p8.system_prompt
    except Exception as _e:
        _CONTEXT_RUNTIME.record_runtime_event(
            runtime_trace, "adaptive_context.prepare_error",
            {"error_type": type(_e).__name__, "channel": channel})
    # "reject" của Phase 8 KHÔNG được chặn lượt ở đây. Rơi về prompt đầy đủ là sai chiều trên
    # dashboard (bản đầy đủ còn TO HƠN cái vừa bị từ chối vì quá to), nhưng ở kênh này ta chưa
    # có đường nào khác để đi, nên cứ chạy tiếp và để nhà cung cấp nói nếu thật sự quá hạn mức.
    if not sysprompt:
        sysprompt = build_system_prompt(brain, lang=_lang_qd)
    sysprompt += channel_context.build_channel_block(
        channel, meta, telegram_running=(channel == "telegram"), port=_javis_port(),
        brain_root=_brain_root(brain))
    if kind in ("cli", "oauth"):
        _schedule_registry_discovery_shadow(
            runtime_trace, brain, text,
            "codex" if prov == "openai-oauth" else "cli",
            api_model or mcfg.get("claude_model") or "mặc định", kind,
        )
    schedule_action = await _schedule_cancel_action(text, brain)
    if schedule_action:
        for call in schedule_action.get("calls") or []:
            await _p(f"⚙ Lịch: {call.split(':')[-1]}")
        # dict (không phải chuỗi): đây là câu trả lời THẬT nên vỏ phải lưu nó lại.
        return {"text": channel_context.strip_control_blocks(_schedule_cancel_reply(schedule_action)),
                "files": []}

    if _FAST_PATH is not None:
        try:
            _fp = await asyncio.to_thread(
                _FAST_PATH.prepare, runtime_trace, text, _brain_root(brain), channel, prov,
                api_model or mcfg.get("claude_model") or "mặc định", kind, False,
                _lang_qd.lang_cau_hoi, _lang_qd.lang)
        except Exception as _e:
            _fp = None
            _CONTEXT_RUNTIME.record_runtime_event(
                runtime_trace, "fast_path.prepare_error",
                {"error_type": type(_e).__name__, "channel": channel})
        # CHỈ nhận "execute". "reject" của đường tắt dựa trên trần TỰ KHAI, không phải hạn mức
        # nhà cung cấp nói ra - lấy nó chặn lượt chat là vượt quyền (cùng lý do với dashboard).
        if _fp is not None and _fp.action == "execute":
            await _p("⚡ Đường tắt…")
            _txt, _mdl, _ = await _fast_path_core(
                _fp, prov, api_key, api_model or mcfg.get("claude_model") or "mặc định",
                reasoning, runtime_trace, text, im_lang_khi_loi=True, channel=channel)
            # Rỗng = đường tắt hụt (token gói thuê bao hết hạn, model không trả gì). Rơi
            # xuống engine đầy đủ bên dưới, người dùng vẫn có câu trả lời.
            if _txt.strip():
                return {"text": channel_context.strip_control_blocks(_txt), "files": []}

    if prov == "gemini-cli":
        # Cùng engine với dashboard: Gemini CLI + tool native + MCP hub, chỉ khác chỗ giữ mạch.
        # Phiên Telegram giữ luôn object engine trong `sess` (như Codex), nên mạch hội thoại
        # nối tiếp qua các tin nhắn mà không phải đụng SQLite.
        actual_model = api_model or gemini_cli.MODEL_MAC_DINH
        gcli = sess.get("gemini")
        if gcli is None:
            gcli = gemini_cli.GeminiCLI(cwd=_brain_root(brain), model=actual_model,
                                        tag=f"telegram:{chat_id}", instructions=sysprompt)
            sess["gemini"] = gcli
        else:
            gcli.cwd = _brain_root(brain)
            gcli.model = actual_model
            gcli.instructions = sysprompt
        _apply_gemini_hub(gcli, _brain_root(brain))
        if not gcli.is_available():
            return ("⚠ Chưa cài Gemini CLI trên máy chạy Javis. Cài bằng "
                    "`npm i -g @google/gemini-cli` rồi chạy `gemini` một lần để đăng nhập Google.")
        out, loi = "", []
        async for ev in gcli.query(text):
            et = ev.get("type")
            if et == "tool_call":
                await _p(f"⚙ Đang gọi: {ev.get('name', '')}")
            elif et == "final":
                out = ev.get("content") or ""
            elif et == "error":
                loi.append(str(ev.get("content") or ""))
        if not out and loi:
            _noi = _subscription_limit_message(loi[0], "gemini-cli")
            return _noi or ("⚠ Gemini CLI lỗi: " + loi[0][:400])
        return out or "(không có nội dung)"

    if prov == "antigravity-cli":
        # Cùng khuôn nhánh Gemini CLI ngay trên: giữ object engine trong `sess` để mạch hội
        # thoại nối tiếp qua các tin nhắn mà không phải đụng SQLite.
        actual_model = api_model or None
        acli = sess.get("antigravity")
        if acli is None:
            acli = antigravity_cli.AntigravityCLI(cwd=_brain_root(brain), model=actual_model,
                                                  tag=f"telegram:{chat_id}",
                                                  instructions=sysprompt)
            sess["antigravity"] = acli
        else:
            acli.cwd = _brain_root(brain)
            acli.model = actual_model
            acli.instructions = sysprompt
        acli.mode = "full"
        _apply_antigravity_hub(acli, _brain_root(brain))
        if not acli.is_available():
            return ("⚠ Chưa cài Antigravity CLI trên máy chạy Javis. Cài một lần:\n"
                    f"`{antigravity_cli.lenh_cai()}`\n"
                    "Rồi gõ `agy` một lần để đăng nhập Google.")
        out, loi = "", []
        async for ev in acli.query(text):
            et = ev.get("type")
            if et == "tool_call":
                await _p(f"⚙ Đang gọi: {ev.get('name', '')}")
            elif et == "final":
                out = ev.get("content") or ""
            elif et == "error":
                loi.append(str(ev.get("content") or ""))
        if not out and loi:
            _noi = _subscription_limit_message(loi[0], "antigravity-cli")
            return _noi or ("⚠ Antigravity CLI lỗi: " + loi[0][:400])
        return out or "(không có nội dung)"

    if prov == "openai-oauth":
        # Telegram dùng cùng Codex CLI + MCP native như dashboard. Trước đây nhánh OAuth
        # rơi vào Responses chat-thuần nên model nói đúng là phiên không có tool.
        actual_model = _codex_safe_model(api_model)
        canh_bao = ""
        if api_model and actual_model != api_model:
            # Tự chữa như dashboard: ghi lại model đúng để lượt sau khỏi ép lại nữa, VÀ nói cho
            # user biết. Trước đây Telegram lặng lẽ đổi, user cứ tưởng đang chạy model mình chọn.
            try:
                _fix = cfgmod.read_settings()
                _set_main_model(_fix, "openai-oauth", actual_model)
                cfgmod.write_settings(_fix)
            except Exception as _e:
                print(f"[codex model self-heal] {_e}", file=__import__('sys').stderr)
            canh_bao = (f"⚠ Model '{api_model}' không chạy được qua Codex (tài khoản ChatGPT) - "
                        f"đã tự đổi sang '{actual_model}'. Đổi model khác ở trang Models nếu muốn.\n\n")
        openai_oauth.write_codex_auth()
        ccli = sess.get("codex")
        if ccli is None:
            ccli = CodexCLI(
                cwd=_brain_root(brain),
                model=actual_model,
                tag=f"telegram:{chat_id}",
                instructions=sysprompt,
            )
            sess["codex"] = ccli
        else:
            ccli.cwd = _brain_root(brain)
            ccli.model = actual_model
            ccli.instructions = sysprompt
        _apply_codex_hub(ccli, _brain_root(brain))
        if not ccli.is_available():
            return "⚠ Chưa cài Codex CLI trong container nên ChatGPT chưa dùng được tool."
        t0 = time.time()
        out = ""
        loi = []
        written = []   # đường dẫn moi từ payload tool call (xem candidate_paths_from_tool)

        async def _nuot_codex(prompt, bo_qua_loi_resume=False):
            """Tiêu thụ một lượt Codex. Trả về: lượt này có chết vì resume hỏng không."""
            nonlocal out
            resume_hong = False
            _CONTEXT_RUNTIME.observe_payload(
                runtime_trace,
                [{"role": "system", "content": sysprompt},
                 {"role": "user", "content": prompt}],
                provider="codex", model=actual_model,
            )
            async for ev in ccli.query(prompt):
                et = ev.get("type")
                if et in ("tool_call", "item"):
                    if et == "tool_call":
                        await _p(f"⚙ Đang gọi: {ev.get('name', '')}")
                    # Codex KHÔNG phát file_path có cấu trúc như Claude nên phải moi từ payload,
                    # nếu không thì file nó ghi ra chỉ được gửi kèm khi tình cờ được nhắc tên.
                    # 'item' = item lạ (vd bản vá file) - không in ra nhưng vẫn moi đường dẫn.
                    try:
                        written.extend(channel_context.candidate_paths_from_tool(ev.get("item")))
                    except Exception:
                        pass
                elif et == "text":
                    out += ev.get("content") or ""
                    await _p("✍ Đang soạn câu trả lời…")
                elif et == "final":
                    out = ev.get("content") or out
                    usage_store.record(
                        "codex", actual_model,
                        ev.get("tokens_in", 0), ev.get("tokens_out", 0),
                    )
                    _CONTEXT_RUNTIME.record_usage(
                        runtime_trace, ev.get("tokens_in", 0), ev.get("tokens_out", 0))
                elif et == "error":
                    if ev.get("resume_failed"):
                        resume_hong = True
                        if bo_qua_loi_resume:
                            continue    # còn cửa dựng lại, chưa phải lúc kêu lỗi với user
                    loi.append(str(ev.get("content") or "Codex lỗi"))
                    _CONTEXT_RUNTIME.note_error(runtime_trace, "codex_error_event")
            return resume_hong

        # Lịch sử để dựng lại thread khi cần. Bỏ lượt cuối vì đó chính là câu đang hỏi.
        _raw = []
        if store is not None and conv_sid:
            try:
                _raw = [{"role": m["role"], "content": m["content"]}
                        for m in store.get_messages(conv_sid)[:-1]
                        if m.get("role") in ("user", "assistant") and m.get("content")]
            except Exception:
                _raw = []
        _hien_tai = _cli_think(reasoning, text)
        thread_cu = (getattr(ccli, "session_id", None) or "")
        # Chưa có thread (phiên mới, hoặc vừa bị xoá liên kết vì provider khác chen vào) thì
        # seed transcript đúng một lượt; có thread rồi thì resume native, khỏi gửi lại lịch sử.
        _resume_hong = await _nuot_codex(
            _hien_tai if thread_cu else compaction.codex_bootstrap_prompt(_raw, _hien_tai),
            bo_qua_loi_resume=bool(thread_cu))
        if thread_cu and _resume_hong and not out:
            # Rollout local có thể bị dọn/mất sau nâng cấp máy. Trước đây Telegram bỏ luôn lượt
            # và mất sạch ngữ cảnh; dashboard thì dựng lại. Giờ Telegram cũng có kho phiên nên
            # dựng lại được y hệt: thread mới từ transcript đã lưu, các lượt sau resume nó.
            await _p("Phiên Codex cũ không còn trên máy - đang khôi phục ngữ cảnh từ lịch sử đã lưu.")
            ccli.session_id = None
            loi.clear()
            await _nuot_codex(compaction.codex_bootstrap_prompt(_raw, _hien_tai))
        if not out:
            return "⚠ " + (loi[0] if loi else "Codex không trả về nội dung nào.")
        files = channel_context.collect_turn_files(
            out, written, t0, cwd=_brain_root(brain), exclude=sess["sent"],
            vault_root=_brain_root(brain),
        )
        clean_out = channel_context.strip_attached_media(
            channel_context.strip_control_blocks(out), files, _brain_root(brain)
        )
        return _tg_ket(clean_out, files, canh_bao, loi)
    if (kind == "api" and api_key) or kind == "oauth":
        label = _api_label(prov)
        if sess["or"] is None:
            ident = (f"\n\n[Sự thật hệ thống: bạn chạy qua {label}, model '{api_model}'. "
                     f"Hỏi model nào thì khai đúng tên này, KHÔNG nhận là model khác.]")
            sess["or"] = [{"role": "system", "content": sysprompt + ident}]
        sess["or"].append({"role": "user", "content": text})
        t0 = time.time()
        out = ""
        actual_model = api_model or "?"
        loi = []
        _pinged = False
        async for ev in (await _api_stream_mcp(prov, api_key, api_model, sess["or"], reasoning,
                                               brain=brain)):
            if ev["type"] == "text":
                if not _pinged:
                    _pinged = True; await _p("✍ Đang soạn câu trả lời…")
                out += ev["content"]
            elif ev["type"] == "meta":
                actual_model = ev.get("model") or actual_model   # model THẬT (OpenRouter tính tiền theo cái này)
                _CONTEXT_RUNTIME.set_route(runtime_trace, prov, actual_model)
            elif ev["type"] == "usage":
                # Thiếu dòng này tới 0.9.244: mọi lượt Telegram không đi qua Codex đều không
                # được tính vào bảng Mức dùng.
                usage_store.record(prov, actual_model, ev.get("input", 0), ev.get("output", 0))
                _CONTEXT_RUNTIME.record_usage(
                    runtime_trace, ev.get("input", 0), ev.get("output", 0))
            elif ev["type"] == "tool_call":
                await _p(f"⚙ Đang gọi công cụ: {ev.get('name', '')}")
            elif ev["type"] == "error":
                # KHÔNG return ngay: một tool hỏng giữa chừng không có nghĩa là cả lượt hỏng,
                # luồng thường chạy tiếp và vẫn ra câu trả lời. Dashboard vốn xử lý như vậy.
                loi.append(str(ev.get("content") or "lỗi không rõ"))
                _CONTEXT_RUNTIME.note_error(runtime_trace, "api_error_event")
        if not out:
            return "⚠ " + (loi[0] if loi else "Không nhận được nội dung nào.")
        sess["or"].append({"role": "assistant", "content": out})
        # Nén (KHÔNG cắt câm) phần cũ rơi khỏi cửa sổ, chạy NỀN. Phiên Telegram giữ lịch sử
        # in-memory nên dùng compact_mem - bản in-memory của cơ chế nén dashboard: phần cũ vào
        # tóm tắt thay vì bị trim cứng bỏ mất. Chạy nền vì đây là một request LLM nữa; await
        # thẳng ở đây là bắt user ngồi chờ tóm tắt xong mới thấy câu trả lời của chính mình.
        _tg_compact_bg(sess, prov, api_key, api_model)
        # MCP đa-model có thể tạo ảnh/file dù engine không có tool Write native. Thu đường dẫn
        # Markdown giống nhánh Codex/Claude để OpenRouter cũng gửi media thật qua Telegram.
        files = channel_context.collect_turn_files(
            out, [], t0, cwd=_brain_root(brain), exclude=sess["sent"],
            vault_root=_brain_root(brain),
        )
        clean_out = channel_context.strip_attached_media(
            channel_context.strip_control_blocks(out), files, _brain_root(brain)
        )
        return _tg_ket(clean_out, files, "", loi)
    else:
        if sess["cli"] is None:
            # tag riêng theo chat → /stop chỉ giết đúng subprocess của chat này, không đụng người khác
            sess["cli"] = claude_engine(system_prompt=sysprompt, cwd=CLAUDE_CWD, tag=f"telegram:{chat_id}")
        cli = sess["cli"]
        cli.system_prompt = sysprompt
        cli.model = api_model or mcfg.get("claude_model") or None
        _apply_mcp(cli, brain=brain)
        t0 = time.time()
        written = []   # file agent ghi bằng tool Write trong lượt này (ứng viên auto-gửi)
        out = ""
        _streamed = ""   # phần đã stream - phương án dự phòng khi luồng đứt trước 'final'
        loi = []
        _pinged = False
        _cli_prompt = _cli_think(reasoning, text)
        _CONTEXT_RUNTIME.observe_payload(
            runtime_trace,
            [{"role": "system", "content": sysprompt},
             {"role": "user", "content": _cli_prompt}],
            provider="cli", model=cli.model or mcfg.get("claude_model") or "mặc định",
        )
        async for ev in cli.query(_cli_prompt):
            et = ev["type"]
            if et == "final":
                out = ev.get("content") or out
                # Thiếu dòng này tới 0.9.244 (xem nhánh API ngay trên): lượt Telegram qua
                # Claude Code không được tính vào bảng Mức dùng.
                usage_store.record("cli", cli.model or mcfg.get("claude_model") or "mặc định",
                                   ev.get("tokens_in", 0), ev.get("tokens_out", 0),
                                   ev.get("cost_usd") or 0)
                _CONTEXT_RUNTIME.record_usage(
                    runtime_trace, ev.get("tokens_in", 0), ev.get("tokens_out", 0))
            elif et == "tool_call":
                nm = ev.get("name", "")
                if nm in ("Write", "NotebookEdit"):
                    fp = (ev.get("input") or {}).get("file_path") or (ev.get("input") or {}).get("notebook_path")
                    if fp:
                        written.append(str(fp))
                await _p(f"⚙ Đang gọi: {nm}")
            elif et == "tool_result":
                await _p("✓ Nhận kết quả - đang phân tích…")
            elif et == "text":
                _streamed += ev.get("content") or ""
                if not _pinged:
                    _pinged = True; await _p("✍ Đang soạn câu trả lời…")
            elif et == "error":
                # Xem nhánh API: lỗi giữa lượt không chí mạng, cứ chạy tiếp rồi báo ở cuối.
                loi.append(str(ev.get("content") or "lỗi không rõ"))
                _CONTEXT_RUNTIME.note_error(runtime_trace, "cli_error_event")
        out = out or _streamed
        if not out:
            return "⚠ " + (loi[0] if loi else "Engine không trả về nội dung nào.")
        # File sinh ra trong lượt → bot gửi đính kèm SAU câu trả lời (xem telegram_bot._handle_turn).
        # vault_root = brain phiên này: ảnh Javis tạo nhúng dạng ![](attachments/x.png) (path tương
        # đối) được resolve về gốc vault để tự đính kèm về ĐÚNG người đang chat, khỏi phải curl.
        files = channel_context.collect_turn_files(out, written, t0,
                                                   cwd=CLAUDE_CWD, exclude=sess["sent"],
                                                   vault_root=_brain_root(brain))
        # Lọc SAU collect_turn_files: hàm đó dò đường dẫn file trong text gốc, lọc trước là mất dấu.
        clean_out = channel_context.strip_attached_media(
            channel_context.strip_control_blocks(out), files, _brain_root(brain)
        )
        return _tg_ket(clean_out, files, "", loi)


async def _tg_help_text(brain):
    return (
        "🤖 Javis Telegram\n\n"
        "Lệnh:\n"
        "/status - engine, model, vault, trạng thái\n"
        "/skills - liệt kê skill\n"
        "/agents - liệt kê agent + việc đang chạy\n"
        "/workflows - liệt kê workflow\n"
        "/model - xem/đổi model: gõ /model để chọn bằng nút (mọi nhà cung cấp đã kết nối), hoặc /model <tên model>\n"
        "/brain - xem/đổi brain (vault) cho riêng phiên của bạn (vd /brain hoặc /brain <tên>)\n"
        "/cli - engine Claude (có MCP/skill)\n"
        "/or - engine OpenRouter (chat + MCP đa-model)\n"
        "/retry - gửi lại câu gần nhất\n"
        "/reset - hội thoại mới · /stop - dừng\n\n"
        "Gửi tin thường để hỏi Javis. ChatGPT/Codex và OpenRouter đều dùng được MCP của Javis.\n"
        "Gõ /tên-skill để gọi skill (cần engine Claude CLI).\n"
        "Gửi file/ảnh vào đây để Javis đọc. File Javis tạo ra sẽ tự gửi lại cho bạn ở đây."
    )


async def _tg_skills_text(brain):
    try:
        d = {"skills": skills_index(brain)}
        sk = d.get("skills", []) or []
    except Exception:
        sk = []
    if not sk:
        return "Vault chưa có skill nào trong skills/."
    lines = [f"/{s['slug']} - {(s.get('description') or '')[:60]}" for s in sk[:30]]
    return "🧩 Skill có sẵn (gõ /slug để gọi, cần engine Claude CLI):\n" + "\n".join(lines)


# ---- Menu chọn model (inline keyboard Telegram) - kiểu Hermes: chọn provider
#      (đánh dấu ✓ + số model) → lưới model 2 cột PHÂN TRANG ◀ 1/N ▶.
#      Danh sách model lấy LIVE qua provider_models() (OpenRouter đầy đủ, ChatGPT,
#      Claude API...), fallback catalog trong settings khi provider không list được. ----
# Nhãn NGẮN cho nút Telegram. Nhãn trong PROVIDER_DEFS viết cho dashboard nên dài ("Google
# Antigravity CLI", "Google Gemini CLI (cá nhân đã bị Google ngắt)"), mà nút Telegram còn phải
# chứa cả dấu ✓ lẫn số model. Id nào không có ở đây thì cắt ngắn nhãn gốc.
_TG_NHAN_NGAN = {
    "anthropic-cli": "Claude Code",
    "openai-oauth": "ChatGPT",
    "antigravity-cli": "Antigravity",
    "gemini-cli": "Gemini CLI",
    "openrouter": "OpenRouter",
    "anthropic-api": "Claude API",
    "openai": "OpenAI API",
    "gemini": "Gemini API",
    "groq": "Groq",
    "ollama": "Ollama",
}
_TG_MODEL_LISTS = {}   # provider -> list model id ĐÃ render (index nút ổn định khi bấm)
_TG_PAGE = 8           # model mỗi trang (lưới 2 cột x 4 hàng)


def _tg_providers():
    """Provider cho menu Telegram, lấy từ ĐÚNG danh sách của app.

    Trước 0.33.7 đây là một bảng chép tay 5 dòng, và nó lệch dần khỏi thực tế đúng như mọi bảng
    chép tay: dashboard lên 10 provider thì Telegram vẫn 5, nên bộ não Antigravity (đường Google
    còn sống cho tài khoản cá nhân) không đổi model được từ điện thoại, mà cũng chẳng có câu nào
    nói vì sao. Đọc thẳng PROVIDER_DEFS thì thêm provider mới vào app là Telegram tự có.
    """
    return [(p["id"], _tg_prov_label(p["id"])) for p in PROVIDER_DEFS]


def _tg_prov_label(pid):
    if pid in _TG_NHAN_NGAN:
        return _TG_NHAN_NGAN[pid]
    nhan = (_provider_def(pid) or {}).get("label") or pid
    return nhan.split("(")[0].strip()[:20] or pid


def _tg_prov_ready(pid, m):
    """Provider dùng được ngay chưa? CLI luôn sẵn; OAuth cần đã kết nối; API cần key
    (cùng logic 'configured' của _providers_view)."""
    d = _provider_def(pid) or {}
    if d.get("kind") == "oauth":
        o = m.get("openai_oauth") or {}
        return bool(o.get("access_token") or o.get("refresh_token"))
    kf = d.get("key_field")
    return True if kf is None else bool(m.get(kf))


async def _tg_provider_cho_model(mid, m):
    """Model id này thuộc nhà cung cấp nào. Trả (provider chốt được, danh sách ứng viên).

    Ưu tiên provider ĐANG DÙNG khi nó cũng có id đó: `/model sonnet` lúc đang ở Claude Code thì
    ý người dùng là đổi model trong cùng nhà cung cấp, không phải nhảy sang Claude API. Nhiều
    nhà cùng có mà không nhà nào đang dùng thì KHÔNG đoán - trả danh sách để hỏi lại, vì đoán
    trượt ở đây là âm thầm đổi cả đường tiền (gói thuê bao so với API tính theo lượt gọi).
    """
    cur_prov, _ = _model_current()
    ung_vien = []
    for pid, _lb in _tg_providers():
        if not _tg_prov_ready(pid, m):
            continue
        ids = _TG_MODEL_LISTS.get(pid)
        if ids is None:
            ids = await _tg_models_for(pid)
        if mid in ids:
            ung_vien.append(pid)
    if cur_prov in ung_vien:
        return cur_prov, ung_vien
    if len(ung_vien) == 1:
        return ung_vien[0], ung_vien
    return None, ung_vien


async def _tg_models_for(pid):
    """Model của 1 provider (live, cache 10' trong provider_models) + nhớ lại danh sách
    đã render để index nút bấm không lệch giữa lúc hiện menu và lúc user bấm."""
    try:
        d = await provider_models_index(pid)
        ids = [str(x) for x in (d.get("models") or [])]
    except Exception:
        ids = []
    _TG_MODEL_LISTS[pid] = ids
    return ids


def _model_current():
    em = _effective_main(cfgmod.read_settings())
    return em["provider"], em["model"] or "mặc định"


async def _model_provider_kb():
    m = cfgmod.read_settings().get("model", {})
    cur_prov, _ = _model_current()
    ready = [(pid, lb) for pid, lb in _tg_providers() if _tg_prov_ready(pid, m)]
    lists = await asyncio.gather(*(_tg_models_for(pid) for pid, _ in ready))
    rows, row = [], []
    for (pid, lb), ids in zip(ready, lists):
        # Provider không liệt kê nổi model nào thì bấm vào cũng chỉ ra một trang trống. Hay gặp
        # nhất là CLI đã cài nhưng chưa đăng nhập (`agy models` phải có tài khoản mới trả danh
        # sách). Giấu đi cho gọn, TRỪ provider đang dùng - luôn phải thấy mình đang đứng ở đâu.
        if not ids and pid != cur_prov:
            continue
        mark = "✓ " if pid == cur_prov else ""
        row.append({"text": f"{mark}{lb} ({len(ids)})", "callback_data": f"mp:{pid}"})
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([{"text": "✕ Đóng", "callback_data": "mx"}])
    return {"inline_keyboard": rows}


def _model_list_kb(pid, page=0):
    ids = _TG_MODEL_LISTS.get(pid) or []
    _, cur = _model_current()
    pages = max(1, (len(ids) + _TG_PAGE - 1) // _TG_PAGE)
    page = max(0, min(page, pages - 1))
    rows, row = [], []
    for i in range(page * _TG_PAGE, min((page + 1) * _TG_PAGE, len(ids))):
        mid = ids[i]
        # OpenRouter id dạng vendor/tên → nút chỉ hiện tên cho gọn (chọn vẫn theo id đầy đủ)
        disp = mid.split("/", 1)[-1] if pid == "openrouter" else mid
        mark = "✓ " if mid == cur else ""
        row.append({"text": f"{mark}{disp}"[:60], "callback_data": f"ms:{pid}:{i}"})
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)
    if pages > 1:
        nav = []
        if page > 0:
            nav.append({"text": "◀", "callback_data": f"ml:{pid}:{page - 1}"})
        nav.append({"text": f"{page + 1}/{pages}", "callback_data": "noop"})
        if page < pages - 1:
            nav.append({"text": "▶", "callback_data": f"ml:{pid}:{page + 1}"})
        rows.append(nav)
    rows.append([{"text": "‹ Provider", "callback_data": "mp:back"},
                 {"text": "✕ Đóng", "callback_data": "mx"}])
    return {"inline_keyboard": rows}


def _tg_model_list_text(pid):
    n = len(_TG_MODEL_LISTS.get(pid) or [])
    tip = "\nMẹo: gõ /model <id> để chọn nhanh không cần lật trang." if n > _TG_PAGE else ""
    return f"⚙️ {_tg_prov_label(pid)} - chọn model ({n}):{tip}"


def _model_header():
    prov, cur = _model_current()
    return ("⚙️ Cấu hình model\n"
            f"Hiện tại: {cur}\n"
            f"Provider: {_tg_prov_label(prov)}\n\n"
            "Chọn provider (chỉ hiện provider đã kết nối):")


# ---- Menu chọn brain cho PHIÊN Telegram (inline keyboard, giống menu model) ----
def _tg_brain_header(chat_key):
    cur = Path(_brain_root(_tg_brain(chat_key))).name
    return ("🧠 Brain của phiên này: " + cur + "\n"
            "Chọn brain khác (chỉ đổi cho phiên CỦA BẠN, người khác và dashboard không đổi):")


def _tg_brain_kb(brains, chat_key):
    try:
        cur = str(Path(_brain_root(_tg_brain(chat_key))).resolve())
    except Exception:
        cur = ""
    rows = []
    for i, b in enumerate(brains[:20]):   # Telegram giới hạn nút; >20 brain thì gõ /brain <tên>
        try:
            mark = "✓ " if str(Path(b["path"]).resolve()) == cur else ""
        except Exception:
            mark = ""
        rows.append([{"text": f"{mark}{b['name']} · {b.get('notes', 0)} note",
                      "callback_data": f"bs:{i}"}])
    rows.append([{"text": "✕ Đóng", "callback_data": "bx"}])
    return {"inline_keyboard": rows}


async def _tg_callback(data, chat=None):
    """Xử lý khi user bấm nút inline. Trả {'text','reply_markup','alert'} hoặc None.
    chat = chat_id người bấm → nút brain chỉ đổi cho PHIÊN của họ (model vẫn đổi toàn cục)."""
    data = data or ""
    chat_key = str(chat or "default")
    if data == "mx":
        return {"text": "Đã đóng bảng chọn model.", "alert": "Đã đóng"}
    # ---- nút chọn brain (bs:<idx> | bx) - tác động PHIÊN của người bấm ----
    if data == "bx":
        return {"text": "Đã đóng bảng chọn brain.", "alert": "Đã đóng"}
    if data.startswith("bs:"):
        try:
            i = int(data.split(":", 1)[1])
        except ValueError:
            return {"alert": "Dữ liệu nút lỗi"}
        d = await asyncio.to_thread(_list_brains_sync); brains = d.get("brains") or []
        if i < 0 or i >= len(brains):
            return {"alert": "Danh sách brain đã đổi - gõ /brain lại"}
        hit = brains[i]
        _tg_set_brain(chat_key, hit["path"])
        return {"text": f"🧠 Đã chuyển phiên này sang brain: {hit['name']}\n"
                        "(hội thoại reset để nạp đúng bộ nhớ/skill của brain mới)",
                "alert": "Đã đổi brain"}
    if data == "noop":
        return None   # nút chỉ-hiển-thị (số trang) - answer callback cho tắt spinner, không sửa tin
    if data in ("mp:back", "model"):
        return {"text": _model_header(), "reply_markup": await _model_provider_kb()}
    if data.startswith("mp:"):
        pid = data.split(":", 1)[1]
        if pid not in dict(_tg_providers()):
            return {"alert": "Provider không hợp lệ - gõ /model lại"}
        if not _tg_prov_ready(pid, cfgmod.read_settings().get("model", {})):
            return {"alert": f"{_tg_prov_label(pid)} chưa kết nối - vào dashboard trang Models"}
        await _tg_models_for(pid)   # nạp danh sách mới nhất trước khi vẽ trang 1
        return {"text": _tg_model_list_text(pid), "reply_markup": _model_list_kb(pid, 0)}
    if data.startswith("ml:"):
        # lật trang danh sách model
        try:
            _, pid, pg = data.split(":")
            page = int(pg)
        except ValueError:
            return {"alert": "Dữ liệu nút lỗi"}
        if pid not in _TG_MODEL_LISTS:
            await _tg_models_for(pid)   # server vừa restart → nạp lại rồi vẽ tiếp
        return {"text": _tg_model_list_text(pid), "reply_markup": _model_list_kb(pid, page)}
    if data.startswith("ms:"):
        try:
            _, pid, idx = data.split(":")
            i = int(idx)
        except ValueError:
            return {"alert": "Dữ liệu nút lỗi"}
        ids = _TG_MODEL_LISTS.get(pid) or []
        if i < 0 or i >= len(ids):
            return {"alert": "Danh sách đã đổi - gõ /model lại"}
        mdl = ids[i]
        s = cfgmod.read_settings(); m = s["model"]
        if not _tg_prov_ready(pid, m):
            return {"alert": f"{_tg_prov_label(pid)} chưa kết nối - vào dashboard trang Models"}
        if pid == "anthropic-cli":
            mdl = mdl.lower()   # alias opus/sonnet/haiku/fable
        _set_main_model(s, pid, mdl); cfgmod.write_settings(s)
        note = {"anthropic-cli": "Claude Code - đầy đủ MCP/skill",
                "openai-oauth": "ChatGPT qua Codex CLI - có MCP",
                "openrouter": "OpenRouter - chat + MCP đa-model",
                "anthropic-api": "Claude API - chat + MCP đa-model",
                "openai": "OpenAI API - chat + MCP đa-model"}.get(pid, pid)
        return {"text": f"✅ {note}\nModel: {mdl}", "alert": "Đã đổi model"}
    return None


async def _tg_command(cmd, arg, chat=None, meta=None):
    """Xử lý lệnh Telegram cho 1 chat. Trả {'reply':...} hoặc {'ask':...} hoặc None.
    chat = chat_id của người gõ lệnh → reset/stop/retry/brain chỉ tác động PHIÊN của họ."""
    chat_key = str(chat or "default")
    brain = _tg_brain(chat_key)   # brain riêng của phiên (đổi bằng /brain)
    if cmd == "stop":
        # Chỉ giết subprocess Claude của CHÍNH chat này (tag telegram:<chat>), không đụng người khác.
        cancel_all(f"telegram:{chat_key}")
        return {"reply": "⏹ Đã dừng lệnh đang chạy."}
    if cmd in ("reset", "new", "clear"):
        sess = _TG_SESS.get(chat_key)
        if sess:
            if sess.get("cli"):
                sess["cli"].reset_session()
            sess["codex"] = None
            sess["or"] = None
            sess["last"] = None
            sess["sid"] = None     # hội thoại mới → phiên mới trong kho, khỏi nối vào mạch cũ
        return {"reply": "🔄 Đã reset hội thoại (chỉ phiên của bạn)."}
    if cmd in ("cli", "claude"):
        s = cfgmod.read_settings()
        _set_main_model(s, "anthropic-cli", (s["model"].get("main") or {}).get("model") or s["model"].get("claude_model") or "opus")
        cfgmod.write_settings(s)
        return {"reply": "✅ Provider: Anthropic (Claude Code) - đầy đủ MCP, hỏi POS/Ads/vault được."}
    if cmd in ("or", "openrouter"):
        s = cfgmod.read_settings()
        if not s["model"].get("openrouter_key"):
            return {"reply": "⚠ Chưa có OpenRouter key - đặt trong Models trên dashboard trước."}
        _set_main_model(s, "openrouter", s["model"].get("openrouter_model")); cfgmod.write_settings(s)
        return {"reply": f"✅ Provider: OpenRouter ({s['model'].get('openrouter_model')}) - chat + MCP đa-model."}
    if cmd in ("help", "menu", "start"):
        return {"reply": await _tg_help_text(brain)}
    if cmd == "skills":
        return {"reply": await _tg_skills_text(brain)}
    if cmd == "status":
        prov, model = _model_current()
        busy = _tg_chat_busy(chat_key)
        bname = Path(_brain_root(brain)).name
        return {"reply": ("📊 Trạng thái Javis\n"
                          f"Provider: {prov}\n"
                          f"Model: {model}\n"
                          f"Brain: {bname} (đổi bằng /brain)\n"
                          f"Phiên: {chat_key} (ngữ cảnh riêng)\n"
                          f"Đang xử lý: {'có (gửi /stop để dừng)' if busy else 'rảnh'}")}
    if cmd == "model":
        s = cfgmod.read_settings(); m = s["model"]
        a = arg.strip()
        if a:
            # HỎI DANH SÁCH THẬT TRƯỚC, đoán sau. Mấy luật đoán bên dưới ra đời khi Telegram chỉ
            # biết 3 provider, và giờ chúng gán nhầm một cách im lặng: gõ tên model của
            # Antigravity (vd `gemini-3-flash-high`) thì rơi vào nhánh cuối rồi bị đặt làm model
            # CLAUDE, lượt chat sau mới báo lỗi mà chẳng ai hiểu vì sao.
            _pid, _ung_vien = await _tg_provider_cho_model(a, m)
            if _pid:
                _set_main_model(s, _pid, a); cfgmod.write_settings(s)
                return {"reply": f"✅ {_tg_prov_label(_pid)}: {a}."}
            if len(_ung_vien) > 1:
                _ten = ", ".join(_tg_prov_label(p) for p in _ung_vien)
                return {"reply": f"⚠ '{a}' có ở nhiều nhà cung cấp ({_ten}) nên không đoán "
                                 f"được ý bạn. Gõ /model rồi chọn bằng nút cho chắc."}
            # Không provider nào khai model này (danh sách hỏng, hoặc tên mới tinh) → về mấy
            # luật đoán cũ: id chứa "/" = OpenRouter; gpt*/*-codex = ChatGPT; còn lại = Claude.
            if "/" in a:
                _set_main_model(s, "openrouter", a); cfgmod.write_settings(s)
                return {"reply": f"✅ OpenRouter model: {a}."}
            if _is_codex_model(a):
                if not _tg_prov_ready("openai-oauth", m):
                    return {"reply": "⚠ Chưa kết nối ChatGPT (OpenAI OAuth) - nối ở dashboard trang Models trước."}
                _set_main_model(s, "openai-oauth", a); cfgmod.write_settings(s)
                return {"reply": f"✅ ChatGPT (Codex) model: {a}."}
            _set_main_model(s, "anthropic-cli", a.lower()); cfgmod.write_settings(s)
            return {"reply": f"✅ Model Claude: {a.lower()}. Nếu CLI chưa hỗ trợ tên này, query sẽ báo lỗi."}
        # Không tham số → mở menu nút bấm (chọn provider → chọn model, phân trang)
        return {"reply": _model_header(), "reply_markup": await _model_provider_kb()}
    if cmd == "agents":
        ags = agents_index(brain)
        busy = _tg_chat_busy(chat_key)
        if not ags:
            return {"reply": "Chưa có agent nào (tạo trong Studio trên dashboard)."}
        lines = [f"• {a.get('name')} - {(a.get('role') or '')[:50]}" for a in ags[:20]]
        return {"reply": f"🤖 Agents ({len(ags)}):\n" + "\n".join(lines) + f"\n\nĐang chạy lượt: {'có' if busy else 'không'}"}
    if cmd == "workflows":
        wfs = workflows_index(brain)
        if not wfs:
            return {"reply": "Chưa có workflow (tạo trong Studio trên dashboard)."}
        lines = [f"• {w.get('name')} ({w.get('status')})" for w in wfs[:20]]
        return {"reply": "⚡ Workflows:\n" + "\n".join(lines) + "\n\n(Hiện chạy trên dashboard; chạy qua Telegram sẽ thêm sau.)"}
    if cmd == "retry":
        last = (_TG_SESS.get(chat_key) or {}).get("last")
        if not last:
            return {"reply": "Chưa có câu nào để gửi lại."}
        return {"ask": last}
    if cmd in ("brain", "vault"):
        d = await asyncio.to_thread(_list_brains_sync); brains = d.get("brains") or []
        if not brains:
            return {"reply": "Chưa có brain nào (tạo trong dashboard, nút + cạnh dropdown brain)."}
        a = arg.strip()
        if a:
            # match theo tên: khớp đúng trước, khớp một phần sau (không phân biệt hoa thường)
            hit = (next((b for b in brains if b["name"].lower() == a.lower()), None)
                   or next((b for b in brains if a.lower() in b["name"].lower()), None))
            if not hit:
                names = ", ".join(b["name"] for b in brains[:15])
                return {"reply": f"⚠ Không thấy brain '{a}'. Có: {names}"}
            _tg_set_brain(chat_key, hit["path"])
            return {"reply": f"🧠 Đã chuyển phiên này sang brain: {hit['name']}\n"
                             "(hội thoại reset để nạp đúng bộ nhớ/skill của brain mới)"}
        # Không tham số → menu nút bấm chọn brain
        return {"reply": _tg_brain_header(chat_key), "reply_markup": _tg_brain_kb(brains, chat_key)}
    # /<slug> khác → coi là gọi skill (cần CLI)
    if cfgmod.read_settings().get("model", {}).get("engine") == "openrouter":
        return {"reply": f"⚠ Skill cần engine Claude CLI. Gửi /cli để đổi, rồi /{cmd} lại."}
    ask = (f"Hãy dùng skill `{cmd}`" + (f" với yêu cầu: {arg}" if arg else "")
           + ". Nếu không có skill tên này thì cứ xử lý yêu cầu của tôi bình thường.")
    return {"ask": ask}


def _tg_inbox_dir(chat=None):
    """Nơi lưu file user gửi lên Telegram - đặt trong brain CỦA PHIÊN người gửi
    (đổi bằng /brain; chưa đổi thì brain mặc định) để agent đọc được ngay."""
    root = _brain_root(_tg_brain(chat))
    return str(Path(root) / "inbox" / "telegram")


async def _stt_nghe(data, ten=""):
    """Nghe tin thoại của kênh chat -> chữ. Đọc key Groq TẠI THỜI ĐIỂM GỌI, cố ý.

    Dán key ở trang Models xong là tin thoại tiếp theo nghe được ngay, không phải tắt bật lại
    bot. Đọc lúc dựng bot thì key mới dán nằm im tới lần khởi động sau, mà chẳng có gì trên
    màn hình nói cho người ta biết điều đó.
    """
    _cfg = cfgmod.read_settings()
    key = (_cfg.get("model") or {}).get("groq_api_key") or ""
    # Gợi ý ngôn ngữ theo cấu hình. reply_lang="auto" -> truyền "" để Whisper TỰ DÒ, thay vì
    # ép "vi" như trước: người nói tiếng Anh vào một Javis đang để "auto" thì cái ép đó biến
    # câu của họ thành một câu tiếng Việt sai nghĩa.
    _lc2 = _cfg.get("locale") or {}
    # Thứ tự: ngôn ngữ trả lời đã GHIM -> ngôn ngữ giao diện -> để Whisper tự dò.
    #
    # `ui_lang` ở giữa là để CHỮA MỘT HỒI QUY chứ không phải cho đẹp: `reply_lang` mặc định
    # là "auto", nên nếu chỉ đọc mỗi nó thì mọi máy đang chạy đột nhiên mất gợi ý "vi" mà chủ
    # máy không đổi cài đặt gì. Whisper không có gợi ý thì câu tiếng Việt NGẮN hay bị đoán
    # nhầm sang tiếng khác rồi dịch luôn, ra một câu không ai gõ bao giờ - đúng lý do gợi ý
    # này tồn tại từ đầu.
    _ma = (lang_registry.chuan_hoa(_lc2.get("reply_lang") or "")
           or lang_registry.chuan_hoa(_lc2.get("ui_lang") or ""))
    return await stt.groq_nghe(data, ten, key,
                               ngon_ngu=(lang_registry.get(_ma).stt if _ma else ""))


# ============================================================
# Kênh Zalo Bot của CHỦ (API chính thức). Xem docs/dev/2026-08-zalo-bot-spec.md
# ============================================================
_ZALO_BOT = None
# Hàng chờ ghép nối: người lạ nhắn cho bot -> vào đây kèm MÃ, chủ bấm một nút là vào whitelist.
#
# Vì sao không chép cách của Telegram: bên đó bắt chủ đi tìm Chat ID bằng @userinfobot rồi tự
# dán vào ô. Zalo KHÔNG có công cụ tương đương, và id là chuỗi hex như "6ede9afa66b88fe6d6a9" -
# không ai đọc ra được nó là ai. Nên đảo chiều: bot thấy người lạ thì đưa họ lên đây kèm tên
# hiển thị THẬT và một mã ngắn để chủ đối chiếu đúng người khi hai người trùng tên.
_ZALO_CHO = {}                 # chat_id -> {chat_id, ten, ma, ts, lan}
_ZALO_CHO_MAX = 20             # trần: hộp thư mở cho người lạ, không được phình theo
_ZALO_CHO_TTL = 30 * 60        # mục cũ hơn 30 phút thì rụng
_ZALO_CHO_NHAC = 10 * 60       # mỗi chat_id lạ chỉ nhận MỘT câu từ chối trong 10 phút
ZALO_CHAT_PREFIX = "zalo:"     # owner_chat của việc giao từ Zalo: "zalo:<chat_id>"


def _zalo_don_cho():
    het = [k for k, v in _ZALO_CHO.items() if time.time() - v.get("ts", 0) > _ZALO_CHO_TTL]
    for k in het:
        _ZALO_CHO.pop(k, None)


def _zalo_ghi_cho(meta) -> str:
    """Đưa một chat lạ lên hàng chờ, trả câu bot nên đáp ("" = im, vừa đáp gần đây rồi)."""
    _zalo_don_cho()
    cid = str((meta or {}).get("chat_id") or "").strip()
    if not cid:
        return ""
    cu = _ZALO_CHO.get(cid)
    if cu:
        cu["lan"] = cu.get("lan", 0) + 1
        cu["ten"] = str((meta or {}).get("user_name") or cu.get("ten") or "")[:80]
        nhac_lai = time.time() - cu.get("nhac", 0) > _ZALO_CHO_NHAC
        cu["ts"] = time.time()
        if not nhac_lai:
            return ""      # im: không để người lạ bơm tin làm ngập cả hàng chờ lẫn chat của họ
        cu["nhac"] = time.time()
        return _zalo_cau_tu_choi(cu["ma"])
    if len(_ZALO_CHO) >= _ZALO_CHO_MAX:
        _ZALO_CHO.pop(min(_ZALO_CHO, key=lambda k: _ZALO_CHO[k].get("ts", 0)), None)
    ma = f"{secrets.randbelow(9000) + 1000}"
    _ZALO_CHO[cid] = {"chat_id": cid, "ten": str((meta or {}).get("user_name") or "")[:80],
                      "ma": ma, "ts": time.time(), "nhac": time.time(), "lan": 1}
    return _zalo_cau_tu_choi(ma)


def _zalo_cau_tu_choi(ma: str) -> str:
    return ("Bạn chưa được cấp quyền dùng Javis này.\n"
            f"Mã ghép nối của bạn: {ma}\n"
            "Đưa mã này cho chủ máy để họ cho phép ở trang Kênh.")


def _zalo_inbox_dir(chat=None):
    """Nơi lưu ảnh user gửi lên Zalo - trong brain CỦA PHIÊN người gửi, y như Telegram."""
    root = _brain_root(_tg_brain(ZALO_CHAT_PREFIX + str(chat or "")))
    return str(Path(root) / "inbox" / "zalo")


async def _zalo_answer(text, meta=None, progress=None, channel="zalo", bot=None):
    """Vỏ cho kênh Zalo: gắn TIỀN TỐ vào chat_id rồi mới vào lõi chung.

    Vì sao phải gắn: `_tg_answer` dùng `meta["chat_id"]` làm khoá phiên, khoá brain, và làm
    `owner_chat` cho việc nền. Id Zalo là chuỗi hex còn id Telegram là số, nên trùng nhau thì
    khó, nhưng "khó" không phải là một bảo đảm - và cái giá của một lần trùng là hai người
    khác nhau dùng chung một mạch hội thoại. Tiền tố cũng chính là thứ `_notify_owner` đọc để
    biết đường nào gửi kết quả về.

    KHÔNG gắn tiền tố vào `meta` mà lớp vận chuyển đang cầm: nó dùng chat_id THẬT để gửi tin.
    """
    m = dict(meta or {})
    goc = str(m.get("chat_id") or "").strip()
    m["chat_id"] = (ZALO_CHAT_PREFIX + goc) if goc else "default"
    return await _tg_answer(text, m, progress, channel="zalo", bot=bot)


def _zalo_precheck(text, meta):
    """Chốt chặn TRƯỚC khi tốn một lượt: người lạ thì đưa vào hàng chờ ghép nối.

    Whitelist của lớp vận chuyển cũng chặn được, nhưng nó chỉ trả một câu cụt. Chặn ở đây thì
    người lạ nhận được MÃ, và chủ có một nút để bấm - thay vì phải đi tra một chuỗi hex.
    """
    z = cfgmod.read_settings().get("zalo_bot", {})
    ids = tg_parse_ids(z.get("chat_id"))
    cid = str((meta or {}).get("chat_id") or "").strip()
    if cid and cid in ids:
        return None
    # DANH SÁCH RỖNG = CHƯA AI ĐƯỢC PHÉP, không phải "ai cũng được".
    #
    # Đây là chỗ CỐ Ý khác Telegram, đừng "sửa" cho giống. Bên Telegram ô trống nghĩa là mở
    # cho tất cả, và tài liệu phải đi kèm một câu dặn đừng để trống - vì bên đó user tự tra
    # được id của mình bằng @userinfobot rồi điền vào trước khi bật.
    #
    # Zalo không có công cụ đó, nên luồng đúng là bật bot với ô TRỐNG rồi tự nhắn cho nó một
    # câu để hiện lên hàng chờ. Nếu ô trống lại mở cho tất cả thì đúng cái luồng mà giao diện
    # đang hướng dẫn sẽ tạo ra một con bot ai nhắn cũng chạm được vào brain của chủ, trong
    # khoảng thời gian giữa lúc bật và lúc bấm Cho phép. Fail-closed.
    return {"reply": _zalo_ghi_cho(meta)}


def restart_zalo_bot():
    """Bật lại bot Zalo theo cấu hình settings.zalo_bot (tắt bot cũ nếu có)."""
    global _ZALO_BOT
    z = cfgmod.read_settings().get("zalo_bot", {})
    if _ZALO_BOT:
        _ZALO_BOT.stop()
        _ZALO_BOT = None
    if z.get("enabled") and z.get("token"):
        # KHÔNG truyền whitelist xuống lớp vận chuyển: `_zalo_precheck` lo phần đó và còn trả
        # về mã ghép nối. Truyền cả hai là người lạ ăn hai câu từ chối cho một tin.
        _ZALO_BOT = zalo_bot.ZaloBot(z["token"], "", _zalo_answer, _tg_command,
                                     download_dir=_zalo_inbox_dir,
                                     precheck_fn=_zalo_precheck, stt_fn=_stt_nghe)
        _ZALO_BOT.start()
        return True
    return False


@app.get("/zalo-bot/status")
async def zalo_bot_status():
    z = cfgmod.read_settings().get("zalo_bot", {})
    running = bool(_ZALO_BOT and _ZALO_BOT._task and not _ZALO_BOT._task.done())
    _zalo_don_cho()
    cho = sorted(_ZALO_CHO.values(), key=lambda x: x.get("ts", 0), reverse=True)
    return {"enabled": bool(z.get("enabled")), "token_set": bool(z.get("token")),
            "chat_id": z.get("chat_id", ""), "chat_ids": tg_parse_ids(z.get("chat_id")),
            "running": running,
            "status": (_ZALO_BOT.status if _ZALO_BOT else "off"),
            "last_error": (_ZALO_BOT.last_error if _ZALO_BOT else ""),
            "bot_name": (_ZALO_BOT.bot_username if _ZALO_BOT else ""),
            "loi_danh_tinh": (_ZALO_BOT.loi_danh_tinh if _ZALO_BOT else ""),
            "cho": cho}


@app.post("/zalo-bot/restart")
async def zalo_bot_restart():
    return {"ok": True, "running": restart_zalo_bot()}


@app.post("/zalo-bot/allow")
async def zalo_bot_allow(chat_id: str = Form(...), on: str = Form("1")):
    """Cho phép (hoặc bỏ qua) một chat đang chờ, bằng ĐÚNG một cú bấm."""
    cid = str(chat_id or "").strip()
    if not cid:
        return JSONResponse({"ok": False, "error": "Thiếu chat_id"}, status_code=400)
    if str(on).strip() not in ("", "0", "false"):
        z = cfgmod.read_settings().get("zalo_bot", {})
        ids = tg_parse_ids(z.get("chat_id"))
        if cid not in ids:
            ids.append(cid)
        cfgmod.write_settings({"zalo_bot": {"chat_id": ", ".join(ids)}})
    # Ra khỏi hàng chờ dù chủ chọn gì: cho phép rồi thì hết chờ, mà bấm bỏ qua cũng là đã quyết.
    _ZALO_CHO.pop(cid, None)
    z = cfgmod.read_settings().get("zalo_bot", {})
    return {"ok": True, "chat_ids": tg_parse_ids(z.get("chat_id"))}


@app.post("/zalo-bot/test")
async def zalo_bot_test():
    """Gửi tin test tới TẤT CẢ chat ID trong whitelist - báo rõ ID nào lỗi."""
    z = cfgmod.read_settings().get("zalo_bot", {})
    ids = tg_parse_ids(z.get("chat_id"))
    if not z.get("token") or not ids:
        return {"ok": False, "error": "Thiếu token hoặc chat ID (lưu trước đã)"}
    import httpx
    sent, errs = 0, []
    url = f"https://bot-api.zaloplatforms.com/bot{z['token']}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            for cid in ids:
                try:
                    r = await c.post(url, json={"chat_id": cid,
                                                "text": "Javis Zalo đã kết nối. Nhắn câu hỏi bất kỳ nhé."})
                    d = r.json() if r.content else {}
                    if d.get("ok"):
                        sent += 1
                    else:
                        errs.append(f"{cid}: {str(d.get('description') or 'lỗi')[:80]}")
                except Exception as e:
                    errs.append(f"{cid}: {type(e).__name__}")
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": sent > 0, "sent": sent, "total": len(ids), "error": "; ".join(errs)[:300]}


def restart_telegram():
    """Bật lại bot theo cấu hình settings.telegram (tắt bot cũ nếu có)."""
    global _TG_BOT
    t = cfgmod.read_settings().get("telegram", {})
    if _TG_BOT:
        _TG_BOT.stop()
        _TG_BOT = None
    _TG_SESS.clear()   # xoá mọi phiên hội thoại cũ khi khởi động lại bot
    if t.get("enabled") and t.get("token"):
        _TG_BOT = TelegramBot(t["token"], t.get("chat_id", ""), _tg_answer, _tg_command, _tg_callback,
                              download_dir=_tg_inbox_dir, stt_fn=_stt_nghe)
        _TG_BOT.start()
        return True
    return False


@app.get("/telegram/status")
async def telegram_status():
    t = cfgmod.read_settings().get("telegram", {})
    running = bool(_TG_BOT and _TG_BOT._task and not _TG_BOT._task.done())
    return {"enabled": bool(t.get("enabled")), "token_set": bool(t.get("token")),
            "chat_id": t.get("chat_id", ""), "chat_ids": tg_parse_ids(t.get("chat_id")),
            "running": running,
            "status": (_TG_BOT.status if _TG_BOT else "off"),
            "last_error": (_TG_BOT.last_error if _TG_BOT else ""),
            # Menu lệnh "/" đặt hụt: bot vẫn chạy, chỉ là gõ "/" không sổ ra danh sách. Tách
            # khỏi last_error vì vòng poll xoá last_error sau mỗi lượt thành công.
            "loi_menu_lenh": (getattr(_TG_BOT, "loi_menu_lenh", "") if _TG_BOT else "")}


@app.post("/telegram/restart")
async def telegram_restart():
    return {"ok": True, "running": restart_telegram()}


# ============================================================
# Bot chuyên trách - chatbot chuyên một lĩnh vực, trả lời KHÁCH
# Xem docs/dev/2026-08-bot-chuyen-trach-spec.md
# ============================================================
@app.get("/chatbots")
async def chatbots_list(brain: str = ""):
    """Danh sách bot kèm trạng thái SỐNG (không phải trạng thái mong muốn).

    Gộp cấu hình với trạng thái thật ngay tại đây: tách hai lời gọi thì giao diện có lúc vẽ
    'đang chạy' cho một con vừa chết, và 'bot chết âm thầm' đúng là thứ tính năng này phải
    chống.

    `brain` lọc theo brain - trang Chatbot chỉ hiện bot của brain đang mở, đúng như trang
    Agents và trang Skills. Bỏ trống thì trả TẤT CẢ (bộ giám sát và các lời gọi nội bộ cần
    thấy hết, chúng không đứng ở brain nào cả).
    """
    loc = str(brain or "").strip()
    out = []
    for b in chatbot_store.list_bots():
        if loc and str(b.get("brain") or "") != loc:
            continue
        b = dict(b)
        b["status"] = chatbot_runtime.status(b["id"])
        a = b.get("agent") or {}
        meta, _ = _read_md(_agents_dir(a.get("brain") or "brain") / f"{a.get('slug')}.md")
        b["agent_name"] = meta.get("name") or ""
        b["agent_missing"] = not bool(meta)   # Agent bị xoá/đổi slug -> thẻ phải báo, đừng im
        # Poller sống KHÔNG có nghĩa là bot trả lời được: model gọi hỏng thì thẻ vẫn chấm xanh
        # trong khi khách nhận toàn câu xin lỗi. Lấy lỗi của lượt gần nhất lên thẻ luôn.
        b["loi_luot"] = chatbot_log.loi_gan_nhat(b["id"])
        # Lượt gần nhất chạy được nhưng KHÔNG đúng mức đã đặt. Không gộp vào `loi_luot`: hai
        # chuyện sửa khác nhau, gộp lại là thẻ báo sai loại việc.
        b["canh_bao_luot"] = chatbot_log.canh_bao_gan_nhat(b["id"])
        # Nhóm có người gọi bot mà chủ chưa cho phép. Không đưa lên đây thì hành vi đúng ("bot
        # không tự nhận việc trong nhóm lạ") trông hệt hành vi hỏng: gọi tên bot trong nhóm và
        # không có gì xảy ra, không chỗ nào nói vì sao.
        b["nhom_cho"] = chatbot_runtime.nhom_cho(b["id"])
        out.append(b)
    # Nhãn + cảnh báo rủi ro của từng mức quyền đi kèm luôn: giao diện KHÔNG được giữ bản chép
    # riêng. Chép riêng thì một hôm server siết thêm một rào mà ô cảnh báo vẫn hứa như cũ, và
    # chủ bấm đồng ý dựa trên một câu đã sai.
    return {"bots": out, "lang_list": lang_registry.cho_giao_dien(), "muc_quyen": [
        {"id": m, "nhan": chatbot_store.MUC_NHAN.get(m, m),
         "canh_bao": chatbot_store.canh_bao_muc(m),
         "can_xac_nhan": m in chatbot_store.MUC_NANG}
        for m in chatbot_store.MUC_QUYEN
    ], "kenh": [
        # Cùng lý do với mức quyền: giao diện KHÔNG giữ bản chép riêng. Chỗ lấy token và những
        # thứ kênh đó KHÔNG làm được là kiến thức của server, và nó sẽ đổi khi Zalo mở thêm API.
        {"id": k, "nhan": chatbot_store.KENH_NHAN.get(k, k),
         "lay_token": chatbot_store.KENH_NGUON_TOKEN.get(k, ""),
         "co_nhom": k == "telegram",
         "gui_tai_lieu": k == "telegram"}
        for k in chatbot_store.KENH
    ]}


@app.post("/chatbots/verify-token")
async def chatbots_verify_token(token: str = Form(...), bot_id: str = Form(""),
                                channel: str = Form("")):
    """Hỏi nền tảng xem token này là con bot nào (getMe), và chặn trùng.

    Chặn theo tên tài khoản chứ không so chuỗi token: cùng một token dán hai lần với khoảng
    trắng khác nhau vẫn là hai chuỗi khác nhau. Một token chỉ được MỘT tiến trình long-polling;
    hai poller cùng token thì máy chủ trả 409 và CẢ HAI cùng chết.

    Hỏi ĐÚNG nền tảng theo `channel`. Dán token Zalo vào đường Telegram (hoặc ngược lại) chỉ
    ra 401, và câu "token không hợp lệ" khi token hoàn toàn hợp lệ là chỗ người dùng mắc kẹt
    lâu nhất - họ đi kiểm tra lại token thay vì kiểm tra lại kênh.
    """
    tok = (token or "").strip()
    if not tok:
        return JSONResponse({"ok": False, "error": "Thiếu token"}, status_code=400)
    kenh = str(channel or "").strip().lower()
    kenh = kenh if kenh in chatbot_store.KENH else chatbot_store.KENH_DEFAULT
    nhan = chatbot_store.KENH_NHAN.get(kenh, kenh)
    import httpx   # main.py không import httpx ở mức module (xem telegram_test làm y hệt)
    url = (f"https://api.telegram.org/bot{tok}/getMe" if kenh == "telegram"
           else f"https://bot-api.zaloplatforms.com/bot{tok}/getMe")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = (await client.get(url)) if kenh == "telegram" else (await client.post(url, json={}))
        d = r.json()
    except Exception as e:
        return {"ok": False, "error": f"Không nối được {nhan}: {e}"}
    if not d.get("ok"):
        return {"ok": False, "error": f"Token không hợp lệ ({nhan} từ chối). Kiểm lại xem token "
                                      f"này có đúng là token {nhan} không."}
    info = d.get("result") or {}
    # Telegram gọi là `username`, Zalo gọi là `account_name`. Bản ghi bot chỉ có một trường nên
    # quy về một tên ngay tại cửa vào.
    username = info.get("username") or info.get("account_name") or ""
    if kenh == "telegram":
        chu = cfgmod.read_settings().get("telegram", {})
        if chu.get("token", "").strip() == tok:
            return {"ok": False, "error": "Đây là token bot chính của bạn. Bot chuyên trách phải "
                                          "dùng một bot Telegram RIÊNG (tạo thêm ở BotFather)."}
    trung = chatbot_store.token_owner(username, exclude_id=bot_id, channel=kenh)
    if trung:
        return {"ok": False, "error": f"Bot {nhan} \"{username}\" đã được bot \"{trung['name']}\" "
                                      f"dùng rồi. Mỗi bot phải một token riêng."}
    ra = {"ok": True, "username": username,
          "bot_name": info.get("first_name") or info.get("account_name") or ""}
    # Gói BASIC của Zalo không cho bot vào nhóm. Nói NGAY lúc kiểm token, để người dùng không
    # ngồi khai id nhóm trong form rồi chờ mãi một con bot không bao giờ vào được nhóm nào.
    if kenh == "zalo":
        ra["vao_duoc_nhom"] = bool(info.get("can_join_groups"))
        ra["account_type"] = info.get("account_type") or ""
    return ra


def _chan_nang_quyen(muc, xac_nhan):
    """Chặn nâng mức quyền khi chủ chưa xác nhận đã đọc rủi ro. None = cho qua.

    Cùng khuôn với `POST /reminders` lúc chưa đấu kênh báo: trả `can_force` kèm LÝ DO cụ thể
    để giao diện hỏi lại, chứ không im lặng hạ mức. Hạ mức im lặng thì chủ tưởng bot đang làm
    việc, còn nó thì từ chối mọi công cụ mà không ai biết.
    """
    if not chatbot_store.can_xac_nhan(muc, xac_nhan):
        return None
    m = str(muc).strip().lower()
    return JSONResponse({"ok": False, "error": chatbot_store.LOI_CHUA_XAC_NHAN,
                         "can_force": True, "muc_quyen": m,
                         "nhan": chatbot_store.MUC_NHAN.get(m, m),
                         "canh_bao": chatbot_store.canh_bao_muc(m)}, status_code=400)


@app.post("/chatbots")
async def chatbots_create(name: str = Form(...), agent_slug: str = Form(...),
                          brain: str = Form(""), agent_brain: str = Form(""),
                          icon: str = Form(""), token: str = Form(""),
                          bot_username: str = Form(""), handoff_to: str = Form(""),
                          nguon_tra_loi: str = Form(""), muc_quyen: str = Form(""),
                          groups: str = Form(""), reply_when: str = Form(""),
                          channel: str = Form(""), xac_nhan_rui_ro: str = Form(""),
                          ngon_ngu: str = Form("")):
    # Bot sống TRONG một brain: Agent nó dùng và tài liệu nó đọc là cùng một chỗ. Nhận cả hai
    # tên tham số và tự bù cho nhau, nên người gọi chỉ cần gửi một cái.
    br = (brain or agent_brain or "").strip()
    ack = str(xac_nhan_rui_ro).strip() not in ("", "0", "false")
    chan = _chan_nang_quyen(muc_quyen, ack)
    if chan is not None:
        return chan
    bid, err = chatbot_store.create_bot({
        "name": name, "agent_slug": agent_slug, "agent_brain": br, "brain": br,
        "icon": icon, "token": token, "bot_username": bot_username, "handoff_to": handoff_to,
        "nguon_tra_loi": nguon_tra_loi, "muc_quyen": muc_quyen, "xac_nhan_rui_ro": ack,
        "channel": channel,
        # Nhóm khai được NGAY LÚC TẠO. Bản trước chỉ cho khai ở form Sửa, nên đường đi tự nhiên
        # nhất ("tạo bot, thả vào nhóm, gọi tên") luôn kết thúc bằng một con bot im lặng.
        "groups": groups, "reply_when": reply_when,
        # Ngôn ngữ bot trả lời KHÁCH. "auto" = bám theo khách; ghim một mã khi khách của chủ
        # nói cùng một thứ tiếng. Cố ý KHÔNG thừa hưởng ngôn ngữ của chủ, xem chatbot_store.
        "ngon_ngu": ngon_ngu,
    })
    if err:
        return JSONResponse({"ok": False, "error": err}, status_code=400)
    return {"ok": True, "id": bid}


@app.post("/chatbots/{bot_id}/update")
async def chatbots_update(bot_id: str, request: Request):
    form = dict(await request.form())
    # Giữ hai trường brain luôn bằng nhau: Agent và tài liệu của bot ở cùng một chỗ. Sửa lệch
    # được thì bot trỏ vào Agent nằm ngoài brain nó đọc, và không có gì báo.
    br = (form.get("brain") or form.get("agent_brain") or "").strip()
    if br:
        form["brain"] = form["agent_brain"] = br
    form["xac_nhan_rui_ro"] = str(form.get("xac_nhan_rui_ro") or "").strip() not in ("", "0", "false")
    if "muc_quyen" in form:
        chan = _chan_nang_quyen(form.get("muc_quyen"), form["xac_nhan_rui_ro"])
        if chan is not None:
            return chan
    ok, err = chatbot_store.update_bot(bot_id, form)
    if not ok:
        # 404 CHỈ khi thật sự không có bot nào id đó; mọi lý do còn lại (xác nhận rủi ro, slug
        # Agent hỏng) là 400 - bot có thật, chỉ yêu cầu sai. Bản trước liệt kê ngược lại: mặc
        # định 404 rồi trừ ra một trường hợp, nên mỗi lý do từ chối mới thêm vào kho lại đi ra
        # ngoài dưới dạng "không tìm thấy bot", đọc xong không lần được ra lỗi thật.
        return JSONResponse({"ok": False, "error": err},
                            status_code=404 if err == chatbot_store.LOI_KHONG_CO_BOT else 400)
    # Đang chạy mà đổi token/agent/brain thì phải khởi động lại mới ăn. Khởi động lại luôn cho
    # chắc thay vì đoán trường nào cần: sai ở đây là bot chạy bằng cấu hình cũ mà không ai biết.
    if bot_id in chatbot_runtime._RUNNING:
        chatbot_runtime.start_bot(bot_id)
    return {"ok": True}


@app.post("/chatbots/{bot_id}/enable")
async def chatbots_enable(bot_id: str, on: str = Form("1")):
    bat = str(on).strip() not in ("0", "false", "")
    ok, err = chatbot_store.set_enabled(bot_id, bat)
    if not ok:
        return JSONResponse({"ok": False, "error": err}, status_code=400)
    if bat:
        thanh, loi = chatbot_runtime.start_bot(bot_id)
        if not thanh:
            chatbot_store.set_enabled(bot_id, False)   # bật hụt thì đừng để cấu hình nói dối
            return JSONResponse({"ok": False, "error": loi}, status_code=400)
    else:
        chatbot_runtime.stop_bot(bot_id)
    return {"ok": True, "status": chatbot_runtime.status(bot_id)}


@app.post("/chatbots/{bot_id}/groups")
async def chatbots_groups(bot_id: str, chat_id: str = Form(...), on: str = Form("1")):
    """Cho phép (hoặc gỡ) MỘT nhóm cho bot, bằng đúng một cú bấm trên thẻ.

    Đường này tồn tại vì đường cũ dài tới mức không ai đi hết: thả bot vào nhóm, gõ /id, chép
    id, mở dashboard, bấm Sửa, kéo xuống cuối form, dán vào ô textarea, Lưu. Bỏ sót một bước
    là bot im, và không có gì nói cho biết đã sót ở đâu.

    Không khởi động lại poller: `_answer` đọc lại bản ghi bot MỖI LƯỢT, nên nhóm vừa cho phép
    ăn ngay từ câu tiếp theo.
    """
    bot = chatbot_store.get_bot(bot_id)
    if not bot:
        return JSONResponse({"ok": False, "error": "Không có bot nào id đó"}, status_code=404)
    cid = str(chat_id or "").strip()
    if not cid:
        return JSONResponse({"ok": False, "error": "Thiếu id nhóm"}, status_code=400)
    bat = str(on).strip() not in ("0", "false", "")
    ds = [str(x) for x in (bot.get("groups") or [])]
    if bat:
        if cid not in ds:
            ds.append(cid)
    else:
        ds = [x for x in ds if x != cid]
    ok, err = chatbot_store.update_bot(bot_id, {"groups": ds})
    if not ok:
        return JSONResponse({"ok": False, "error": err}, status_code=400)
    # Ra khỏi hàng đợi dù chủ chọn gì: cho phép rồi thì hết chờ, mà bấm bỏ qua cũng là đã
    # quyết. Nhóm nào bị gỡ mà sau này lại có người gọi bot thì nó tự quay lại hàng đợi.
    chatbot_runtime.bo_nhom_cho(bot_id, cid)
    return {"ok": True, "groups": (chatbot_store.get_bot(bot_id) or {}).get("groups") or []}


@app.get("/chatbots/{bot_id}/log")
async def chatbots_log(bot_id: str, limit: int = 50):
    """Nhật ký hội thoại khách + danh sách CÂU BOT TRẢ LỜI KHÔNG NỔI.

    Trả cả hai trong một lời gọi: chúng luôn được xem cùng nhau, và mỗi cái đọc lại chính file
    đó nên tách ra chỉ tốn hai lượt đọc đĩa cho cùng một dữ liệu.
    """
    if not chatbot_store.get_bot(bot_id):
        return JSONResponse({"ok": False, "error": "Không có bot nào id đó"}, status_code=404)
    return {"ok": True, "turns": chatbot_log.doc(bot_id, limit),
            "gaps": chatbot_log.lo_hong(bot_id), "tom_tat": chatbot_log.tom_tat(bot_id)}


@app.post("/chatbots/{bot_id}/delete")
async def chatbots_delete(bot_id: str):
    """Xoá bản ghi bot. KHÔNG đụng brain và Agent của nó - xem chatbot_store.delete_bot."""
    chatbot_runtime.quen_bot(bot_id)   # tắt + dọn hết vết trong RAM (hàng đợi nhóm, bộ đếm)
    ok, err = chatbot_store.delete_bot(bot_id)
    if not ok:
        return JSONResponse({"ok": False, "error": err}, status_code=404)
    chatbot_log.xoa(bot_id)   # nhật ký của một bot không còn tồn tại thì không ai đọc được nữa
    return {"ok": True}


@app.post("/telegram/test")
async def telegram_test():
    """Gửi tin test tới TẤT CẢ chat ID trong whitelist - báo rõ ID nào lỗi (vd chưa bấm Start bot)."""
    t = cfgmod.read_settings().get("telegram", {})
    ids = tg_parse_ids(t.get("chat_id"))
    if not t.get("token") or not ids:
        return {"ok": False, "error": "Thiếu token hoặc chat ID (lưu trước đã)"}
    import httpx
    sent, errs = 0, []
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            for cid in ids:
                try:
                    r = await c.post(f"https://api.telegram.org/bot{t['token']}/sendMessage",
                                     json={"chat_id": cid, "text": "✅ Javis Telegram đã kết nối. Nhắn câu hỏi bất kỳ nhé."})
                    d = r.json()
                    if d.get("ok"):
                        sent += 1
                    else:
                        errs.append(f"{cid}: {d.get('description', 'lỗi')}")
                except Exception as e:
                    errs.append(f"{cid}: {type(e).__name__}")
        return {"ok": sent > 0, "sent": sent, "total": len(ids),
                "error": "; ".join(errs)[:300]}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ============================================================
# KÊNH CLI - chat qua HTTP (xem docs/dev/2026-08-cli-spec.md)
#
# Trước bản này, muốn nói chuyện với Javis chỉ có hai đường: WebSocket /ws (dashboard, cần
# cookie) và long-polling Telegram. Không có cách nào `curl` một câu hỏi vào, nên cũng không
# có cách nào cắm Javis vào cron, đường ống Unix hay một CLI.
#
# Hai endpoint dưới đây KHÔNG có lõi riêng: chúng gọi thẳng `_tg_answer(..., channel="cli")`,
# tức đúng cái vỏ mà Telegram chạy hằng ngày. Vỏ đó là chỗ duy nhất biết khớp phiên trong kho,
# ghi bộ nhớ hội thoại, gắn trace runtime và chấm chất lượng. Viết bản thứ hai thì lượt CLI sẽ
# vắng mặt ở /sessions và ở vòng tự học.
# ============================================================

def _cli_sess_key(session: str) -> str:
    """Khoá phiên trong RAM cho một terminal. Tiền tố `cli:` để không đụng khoá của Telegram
    (cùng một map `_TG_SESS`), và để nhìn log là biết lượt đó tới từ đâu."""
    # Bỏ dấu chấm khỏi tập cho phép: id phiên không cần nó, mà cho phép thì chuỗi ".." đi
    # thẳng vào khoá và vào nhật ký. Chặn ở đây rẻ hơn tin rằng mọi chỗ dùng khoá đều an toàn.
    raw = "".join(ch for ch in str(session or "").strip() if ch.isalnum() or ch in "-_")[:64]
    return "cli:" + (raw or "default")


async def _cli_turn(message: str, brain: str, session: str, host: str, progress=None):
    """Một lượt chat của kênh CLI. Trả (out, key) với out là dict (trả lời thật) hoặc str (lỗi)."""
    key = _cli_sess_key(session)
    sess = _tg_session(key)
    if brain:
        # Brain do client chọn, ghi vào phiên RAM y như lệnh /brain của Telegram. Không ghi thì
        # mọi lượt CLI rơi vào brain mặc định, và người dùng nhiều brain sẽ hỏi nhầm kho.
        try:
            root = _brain_root(brain)
            if os.path.isdir(root):
                sess["brain"] = root
        except Exception:  # noqa: BLE001 - brain sai tên thì dùng mặc định, không phá lượt
            pass
    meta = {"chat_id": key, "host": (host or "")[:64]}
    out = await _tg_answer(message, meta=meta, progress=progress, channel="cli")
    return out, key


def _cli_payload(out, key: str) -> dict:
    """Đóng gói câu trả lời cho client. Lỗi (chuỗi) vẫn trả 200 kèm ok=false: lượt chat lỗi là
    chuyện thường của một agent, không phải lỗi giao thức HTTP."""
    if isinstance(out, dict):
        return {"ok": True, "text": out.get("text") or "", "session": key,
                "files": list(out.get("files") or []),
                "ctx_path": out.get("ctx_path") or "legacy"}
    return {"ok": False, "text": str(out or ""), "session": key, "files": [], "ctx_path": ""}


@app.post("/chat")
async def chat_once(message: str = Form(...), brain: str = Form(""),
                    session: str = Form(""), host: str = Form("")):
    """Một lượt chat, đồng bộ. Trả câu trả lời cuối cùng.

    KHÔNG đặt trần thời gian riêng: một lượt agentic có thể chạy vài phút và cắt ngang giữa
    chừng là mất luôn công đã bỏ ra. Client tự chọn thời gian chờ; muốn thấy tiến độ thì dùng
    /chat/stream.
    """
    if not str(message or "").strip():
        return JSONResponse({"ok": False, "error": "message rỗng"}, status_code=400)
    out, key = await _cli_turn(message, brain, session, host)
    return _cli_payload(out, key)


@app.post("/chat/stream")
async def chat_stream(message: str = Form(...), brain: str = Form(""),
                      session: str = Form(""), host: str = Form("")):
    """Cùng một lượt, nhưng đẩy tiến độ về ngay khi có (SSE).

    Gói đi theo ĐÚNG quy ước của WebSocket dashboard (`{"type": ...}`) để client không phải
    học giao thức thứ hai. Hiện phát `status` (tiến độ, tên tool đang gọi) rồi `response`
    (câu trả lời cuối). Nói rõ giới hạn thay vì hứa suông: đây KHÔNG phải stream từng chữ -
    stream từng chữ nằm ở đường WebSocket, và kéo nó ra khỏi vòng đời WebSocket là một việc
    lớn hơn hẳn, để dành cho bản sau.

    Client PHẢI bỏ qua im lặng mọi `type` nó chưa biết: server thêm loại gói mới là chuyện
    thường, và một CLI cũ không được vỡ vì điều đó.
    """
    if not str(message or "").strip():
        return JSONResponse({"ok": False, "error": "message rỗng"}, status_code=400)

    hang = asyncio.Queue()

    async def _progress(s):
        await hang.put({"type": "status", "content": str(s or "")})

    async def _chay():
        try:
            out, key = await _cli_turn(message, brain, session, host, progress=_progress)
            await hang.put({"type": "response", **_cli_payload(out, key)})
        except Exception as exc:  # noqa: BLE001 - lỗi phải tới được client, không nuốt
            await hang.put({"type": "error", "content": f"{type(exc).__name__}: {exc}"})
        finally:
            await hang.put(None)

    async def _phat():
        viec = asyncio.create_task(_chay())
        try:
            while True:
                goi = await hang.get()
                if goi is None:
                    break
                yield "data: " + json.dumps(goi, ensure_ascii=False) + "\n\n"
        finally:
            if not viec.done():
                viec.cancel()

    return StreamingResponse(_phat(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/telegram/send-file")
async def telegram_send_file(payload: dict = Body(...)):
    """Gửi 1 file qua Telegram tới chat whitelist. Agent gọi bằng curl từ localhost
    (miễn đăng nhập qua _AUTH_LOCAL_EXACT - request từ ngoài vẫn bị chặn).
    Body: {"path": "<đường dẫn tuyệt đối>", "caption": "<mô tả ngắn>", "chat_id": "<id người hỏi>"}.
    ĐA PHIÊN: có chat_id (và trong whitelist) → gửi ĐÚNG người đang hỏi + dedupe theo phiên họ;
    thiếu chat_id → gửi chủ bot (ID đầu whitelist) như cũ. Ảnh/tệp Javis tạo trong lượt nay tự đính
    kèm về đúng người qua auto-attach (collect_turn_files), nên đường curl này ít khi cần cho chat."""
    path = str((payload or {}).get("path", "")).strip().strip('"')
    caption = str((payload or {}).get("caption", "")).strip()
    chat_id = str((payload or {}).get("chat_id", "")).strip()
    if not (_TG_BOT and _TG_BOT._task and not _TG_BOT._task.done()):
        return {"ok": False, "error": "Bot Telegram chưa chạy (bật ở Settings → Telegram)."}
    if not path:
        return {"ok": False, "error": "Thiếu path"}
    # chỉ nhận chat_id nằm trong whitelist (chống gửi tới ID lạ); ngoài whitelist → về chủ bot
    target = chat_id if (chat_id and chat_id in (_TG_BOT.chat_ids or [])) else None
    ok, err = await _TG_BOT.send_file(path, caption, chat=target)
    if ok:
        # ghi nhận vào ĐÚNG phiên để auto-attach cuối lượt không gửi lại file này lần nữa
        try:
            sess = _TG_SESS.get(chat_id) if chat_id else None
            if sess is not None:
                sess["sent"].add(os.path.normcase(os.path.normpath(os.path.abspath(path))))
        except Exception:
            pass
    return {"ok": ok, "error": err}


@app.on_event("startup")
async def _ve_si_claude_creds():
    """Vòng vệ sĩ ~/.claude/.credentials.json mỗi 5 phút: bản lành thì sao lưu, file hỏng/mất
    thì phục hồi + hô to. Chống vụ "thi thoảng Claude Code tự đăng xuất" (16/08) - tiến trình
    claude bị watchdog giết đúng lúc đang ghi file token là file cụt, CLI coi như chưa đăng
    nhập. Codex không bị vì token ChatGPT do chính Javis giữ."""
    async def _vong():
        while True:
            try:
                import claude_cli as _ccli
                await asyncio.to_thread(_ccli.giu_credentials)
            except Exception:
                pass
            await asyncio.sleep(300)
    asyncio.create_task(_vong())


@app.on_event("startup")
async def _soat_secret_hong():
    """Soi các secret mã hoá không giải mã được (mất/đổi .secret_key) và HÔ TO ngay lúc
    boot. Trước đây lỗi này chỉ hiện một dòng stderr chung chung của secrets_store rồi
    chìm giữa log; hậu quả thật (16/08): 2FA âm thầm thành fail-open, chủ tưởng nó
    "tự tắt" sau cập nhật."""
    try:
        hong = cfgmod.secret_paths_hong()
        if hong:
            print("=" * 68 + f"\n[secrets] {len(hong)} secret MÃ HOÁ KHÔNG GIẢI MÃ ĐƯỢC "
                  f"(file .secret_key trong {cfgmod.STATE_DIR} bị mất/đổi?):\n"
                  + "\n".join(f"  - {p}" for p in hong)
                  + "\nCác giá trị này cần nhập lại (2FA: đăng nhập bằng mã khôi phục rồi "
                    "bật lại).\n" + "=" * 68,
                  file=__import__('sys').stderr)
    except Exception:
        pass


@app.on_event("startup")
async def _warm_mcp_hub():
    """Làm nóng hub sau khi boot: mở sẵn session MCP (stdio npx lần đầu phải tải package)
    để tin nhắn/tool call đầu tiên không phải chờ."""
    async def _w():
        try:
            await asyncio.to_thread(_EVIDENCE_STORE.cleanup)
            # Phase 9 restart reconciliation: write còn RUNNING sau khi tiến trình chết
            # KHÔNG được chạy lại; chuyển UNKNOWN và giữ resource lock cho tới khi có
            # kết luận. Chạy trước khi nhận lượt chat đầu tiên.
            stale = await asyncio.to_thread(_CONTEXT_RUNTIME.sweep_stale_writes)
            if stale:
                print(f"[write ledger] {len(stale)} write chuyển UNKNOWN sau restart",
                      file=__import__('sys').stderr)
            await asyncio.sleep(3)
            if _hub_enabled():
                await mcp_hub.discover_all("full")
        except Exception as e:
            print(f"[hub warmup] {e}", file=__import__('sys').stderr)
    asyncio.create_task(_w())


@app.on_event("shutdown")
async def _shutdown_mcp_pool():
    """Đóng các session MCP sống lâu (stdio subprocess, httpx client) khi server tắt."""
    try:
        await tasks_feature.shutdown()
    except Exception as e:
        print(f"[kanban shutdown] {e}", file=__import__('sys').stderr)
    try:
        await mcp_client.pool.close_all()
    except Exception:
        pass
    # Shell của tab Code chạy trong process group RIÊNG (setsid), nên nó KHÔNG chết theo server
    # - tắt Javis mà bỏ quên là để lại một đàn shell mồ côi giữ cổng và file.
    try:
        terminal.KHO.dong_het()
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn
    # 127.0.0.1: chỉ máy này truy cập được (an toàn - tránh người khác trong mạng LAN
    # chạy Claude full quyền trên máy + vault của bạn). Đổi qua JAVIS_HOST nếu cần.
    host = os.getenv("JAVIS_HOST", "127.0.0.1")
    port = int(os.getenv("JAVIS_PORT", "7777"))
    uvicorn.run("main:app", host=host, port=port, reload=False)
