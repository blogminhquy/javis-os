"""
Javis OS - Backend
Kiến trúc: Voice (browser) ⇄ FastAPI WebSocket ⇄ Claude Code CLI subprocess

Javis KHÔNG gọi Anthropic API trực tiếp. Mọi reasoning + tool calling đi qua
`claude` CLI đã cài trên máy → tự kế thừa MCP, skills, auth.
"""
import os
import json
import asyncio
import glob
import hashlib
import uuid
from pathlib import Path
import re
import shutil
import time
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
import claude_models   # model Claude LIVE cho provider anthropic-cli (mượn token OAuth của Claude Code)
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
import zalo_login
import oauth_mcp
import system_sync   # tầng năng lực HỆ THỐNG (skill/loop mặc định) - update theo phiên bản app
import skill_router   # nguồn chân lý khám phá skill (canonical <brain>/skills) dùng chung mọi engine
import skill_usage     # telemetry: đếm skill nào THẬT SỰ được dùng qua javis_use_skill (tín hiệu DƯƠNG một chiều)
import share_bundle   # xuất/nhập gói agent/skill/workflow (.zip) để chia sẻ giữa brain/người dùng
import usage_store   # đếm token/chi phí Javis tự đo (đa nhà cung cấp)
import usage_index   # dashboard token: index log thô Claude+Codex + query summary/insights
from telegram_bot import TelegramBot, parse_chat_ids as tg_parse_ids
import channel_context   # metadata kênh + gom file trả về kênh chat (port gateway hermes-agent)
from sessions import get_store   # kho phiên hội thoại (sqlite + fts5): list/resume/search
import compaction   # nén hội thoại dài cho engine API (tóm tắt phần cũ thay vì cắt bỏ)
from chat_runtime import ChatRuntime

app = FastAPI(title="Javis OS")
_CHAT_RUNTIME = ChatRuntime()
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
            return JSONResponse({"error": "unauthorized", "auth_required": True,
                                 "setup_required": not cfgmod.auth_enabled()}, status_code=401)
    return await call_next(request)

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


# Trần KÝ TỰ cho toàn bộ system prompt, theo từng nhà cung cấp. 0 = không giới hạn.
#
# Vì sao cần: có provider giới hạn token/PHÚT rất chặt. Groq gói on_demand miễn phí chỉ cho
# 12.000 TPM, trong khi system prompt của Javis (CLAUDE.md ~21.500 ký tự + chỉ mục bộ nhớ tới
# 20.000 + năng lực + router skill) đã ~41.000 ký tự, cộng lịch sử chat là một lượt hơn 21.000
# token - bị chặn ngay từ đầu, chưa kịp trả lời. Càng dùng lâu bộ nhớ càng dày thì càng chắc
# chết. Cắt theo ngân sách ở gateway là chỗ xử lý đúng: bộ nhớ cứ việc lớn lên, phần GỬI ĐI
# vẫn nhỏ.
#
# Tiếng Việt ~3 ký tự/token nên 24.000 ký tự ~ 8.000 token, còn chỗ cho lịch sử + câu trả lời
# trong hạn mức 12.000.
PROMPT_BUDGET_CHARS = {
    "groq": int(os.getenv("JAVIS_PROMPT_BUDGET_GROQ", "24000")),
}


def prompt_budget(provider: str) -> int:
    """Trần ký tự system prompt cho provider này (0 = thả cửa)."""
    return int(PROMPT_BUDGET_CHARS.get(provider, 0) or 0)


def _fit_prompt(core: str, blocks: list, budget: int) -> tuple:
    """Ghép `core` + các khối phụ sao cho tổng <= `budget` ký tự.

    blocks: [(tên, nội dung, shrink)] xếp theo ĐỘ QUAN TRỌNG GIẢM DẦN. `shrink` là hàm
    (text, cap) -> text, hoặc None nếu khối chỉ bỏ được chứ không rút được.
    Cắt từ CUỐI danh sách lên - khối kém quan trọng nhất đi trước. Rút trước, bỏ sau: rút
    chỉ mất chi tiết (đường dẫn file vẫn còn để đọc lại), bỏ mới là mất hẳn.
    Trả (prompt, [mô tả những gì đã rút/bỏ])."""
    if budget <= 0:
        return core + "".join(t for _, t, _ in blocks), []
    keep, trimmed = list(blocks), []
    total = lambda ks: len(core) + sum(len(t) for _, t, _ in ks)   # noqa: E731
    for i in range(len(keep) - 1, -1, -1):
        if total(keep) <= budget:
            break
        name, text, shrink = keep[i]
        if not shrink:
            continue
        room = budget - (total(keep) - len(text))
        if room > 400:
            new = shrink(text, room)
            if len(new) < len(text):
                keep[i] = (name, new, shrink)
                trimmed.append(f"{name} (rút gọn)")
    while keep and total(keep) > budget:
        trimmed.append(f"{keep.pop()[0]} (bỏ)")
    out = core + "".join(t for _, t, _ in keep)
    if len(out) > budget:
        # Chỉ riêng CLAUDE.md đã vượt trần. Cắt đuôi và nói thẳng, hơn là gửi đi rồi ăn lỗi.
        out = out[:budget] + "\n\n[... phần cuối system prompt bị cắt cho vừa hạn mức nhà cung cấp ...]"
        trimmed.append("system prompt gốc (cắt đuôi)")
    return out, trimmed


def build_system_prompt(brain: str = "brain", budget: int = 0) -> str:
    """CLAUDE.md + nạp MEMORY.md của vault đang chọn → Javis luôn nhớ ngữ cảnh.

    budget > 0: ép toàn bộ prompt xuống dưới trần ký tự đó (xem PROMPT_BUDGET_CHARS)."""
    base = CLAUDE_MD_PATH.read_text(encoding="utf-8") if CLAUDE_MD_PATH.exists() else ""
    idx = _brain_memory_dir(brain) / "MEMORY.md"
    mem = ""
    try:
        if idx.exists():
            mem = idx.read_text(encoding="utf-8")
    except Exception:
        mem = ""
    # Từ 0.9.294 các khối phụ gom vào `blocks` thay vì cộng thẳng vào base, để _fit_prompt
    # cắt được theo ngân sách của provider. Thứ tự trong blocks = ĐỘ QUAN TRỌNG giảm dần.
    blocks = []
    if mem.strip():
        blocks.append(("bộ nhớ dài hạn",
                       "\n\n# === BỘ NHỚ DÀI HẠN (nạp sẵn) ===\n" + _fit_memory_index(mem),
                       lambda t, cap: t[:120] + _fit_memory_index(t[120:], max(400, cap - 120))))
    # Đường dẫn lớp Agentic của vault đang làm việc (để Javis tạo agent/workflow/loop qua chat)
    root = _brain_root(brain)
    system_sync.ensure_synced(root)   # brain nào cũng có đủ năng lực hệ thống (1 lần/process, rẻ)
    try:
        # Mirror skills/ → .claude/skills để fork Claude cwd=brain (workflow/loop/learn/lint) nạp
        # native được skill viết giữa phiên (rẻ: cổng chữ ký stat-only bỏ qua nếu cây nguồn
        # không đổi, xem system_sync._mirror_signature - KHÔNG còn so hash nội dung nữa).
        system_sync.mirror_skills(root)
    except Exception:
        pass
    ag, wf = _agents_dir(brain), _workflows_dir(brain)
    lp = Path(root) / "Javis" / "loops"
    sk = _skills_dir(brain)
    agentic = (
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
    blocks.insert(0, ("lớp agentic", agentic, None))   # quan trọng nhất: thiếu là không ghi được file
    # Quét cây skill MỘT lần cho cả hai khối dưới. Trước đây _javis_capability_summary
    # gọi list_skills còn _skill_router_block gọi list_enabled_meta (vốn chỉ là list_skills
    # lọc lại), nên cả cây skill bị đi và parse YAML HAI lần mỗi lượt chat - đo được 18ms
    # mỗi lần trên brain 30 skill. Lỗi thì để None và mỗi khối tự quét như cũ.
    try:
        _skills = skill_router.list_skills(root)
    except Exception:
        _skills = None
    try:
        blocks.append(("chỉ mục năng lực", _javis_capability_summary(brain, _skills), None))
    except Exception:
        pass
    try:
        # Router skill rút được: cắt bớt dòng cuối, giữ nguyên cách gọi ở đầu khối.
        blocks.append(("router skill", _skill_router_block(brain, root, _skills),
                       lambda t, cap: t[:cap].rsplit("\n", 1)[0]
                       + "\n… (danh sách skill bị cắt cho vừa hạn mức - hỏi `javis_use_skill` hoặc đọc thư mục skills/)"))
    except Exception:
        pass
    try:
        # 1 dòng MỨC DÙNG để Javis TRẢ LỜI được khi user hỏi "token tiêu bao nhiêu" (chi tiết ở panel).
        _t = usage_store.summary().get("today", {}).get("total", {})
        if _t.get("in") or _t.get("out"):
            _c = f", ~${_t.get('cost', 0):.4f}" if _t.get("cost") else ""
            blocks.append(("mức dùng hôm nay",
                           f"\n\n# === MỨC DÙNG HÔM NAY (Javis tự đo) ===\n"
                           f"{_t.get('in', 0):,} token vào + {_t.get('out', 0):,} token ra qua "
                           f"{_t.get('turns', 0)} lượt{_c}. Đây là token Javis TỰ ĐO, KHÔNG phải hạn mức gói "
                           f"thuê bao (đa số nhà cung cấp không cho lấy hạn mức tài khoản qua API). Chi tiết "
                           f"từng nhà cung cấp ở panel 'Mức dùng' trên dashboard.", None))
    except Exception:
        pass
    out, trimmed = _fit_prompt(base, blocks, budget)
    if trimmed:
        # Nói cho model biết nó đang thiếu gì và lấy lại ở đâu, thay vì im lặng đưa bản cụt
        # rồi để nó tưởng brain trống trơn.
        out += ("\n\n# === ĐÃ RÚT NGỮ CẢNH CHO VỪA HẠN MỨC NHÀ CUNG CẤP ===\n"
                "Đã rút/bỏ: " + ", ".join(trimmed) + ".\n"
                "Nội dung đầy đủ VẪN CÒN trên đĩa: chỉ mục bộ nhớ ở `Memory/MEMORY.md`, chi tiết ở "
                "`Memory/facts/*.md`, danh sách skill ở thư mục `skills/`. Cần chi tiết nào thì ĐỌC FILE "
                "đó rồi trả lời, đừng nói là không có.")
    return out

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
        now = datetime.now(timezone(timedelta(hours=7)))
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
async def auth_login(request: Request, username: str = Form(...), password: str = Form(...)):
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
    _LOGIN_FAILS.pop(ip, None)
    return _session_cookie(JSONResponse({"ok": True}), cfgmod.new_session(), request)


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
#   kind=cli   (Claude Code)      - MCP native + Bash, chạy lệnh máy
#   kind=oauth (ChatGPT qua Codex) - MCP native + kho MCP gốc Codex, chạy lệnh máy
#   kind=api   (OpenRouter/OpenAI/Anthropic/Gemini) - MCP qua hub trong vòng gọi tool
#              (_api_stream_mcp), đọc/ghi brain bằng tool vault, KHÔNG chạy lệnh máy
# ============================================================
PROVIDER_DEFS = [   # thứ tự = thứ tự hiển thị card ở trang Models
    {"id": "anthropic-cli", "label": "Anthropic OAuth (Claude Code)", "kind": "cli", "key_field": None,          "catalog_key": "claude",
     "default_models": ["opus", "sonnet", "haiku", "fable"]},
    {"id": "openai-oauth",  "label": "OpenAI OAuth (ChatGPT)",  "kind": "oauth", "key_field": None,             "catalog_key": "openai-oauth",
     "default_models": []},  # model/list của Codex app-server là nguồn chân lý; không ghim version ở đây
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
        if p["kind"] == "oauth":
            configured = oauth_on
        elif p["key_field"] is None:
            configured = True
        else:
            configured = bool(m.get(p["key_field"]))
        item = {
            "id": p["id"], "label": p["label"], "kind": p["kind"],
            "needs_key": p["key_field"] is not None,
            "configured": configured,
            "models": cat.get(p["catalog_key"]) or p.get("default_models", []),
            "is_main": main.get("provider") == p["id"],
        }
        if p["kind"] == "oauth":
            item["account"] = oauth.get("account_id", "")
            item["plan"] = oauth.get("plan", "")
        out.append(item)
    return out

def _set_main_model(cfg, provider, model):
    """Đặt model chính + ĐỒNG BỘ field legacy (engine/claude_model/openrouter_model) để chat/Telegram cũ chạy."""
    m = cfg["model"]
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
    elif provider == "groq":
        m["engine"] = "groq"
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

def _api_stream(prov, key, model, messages, reasoning="off"):
    """Chọn generator stream theo provider api-kind. reasoning=off|low|medium|high."""
    if prov == "openrouter":
        return engine.openrouter_stream(key, model, messages, reasoning)
    if prov == "openai":
        return engine.openai_stream(key, model, messages, reasoning)
    if prov == "gemini":
        return engine.gemini_stream(key, model, messages, reasoning)
    if prov == "groq":
        return engine.groq_stream(key, model, messages, reasoning)
    if prov == "openai-oauth":
        creds = openai_oauth.valid_creds() or {}
        return engine.openai_responses_stream(creds.get("access_token", ""), creds.get("account_id", ""),
                                              _codex_safe_model(model), messages, reasoning)
    return engine.anthropic_stream(key, model, messages, reasoning)


# Cửa sổ lịch sử chat cho engine API (openrouter/openai/anthropic-api). Mỗi lượt
# resend TOÀN BỘ history → phiên dài phình vô hạn. Cửa sổ + logic nén nằm ở compaction.py:
# phần cũ rơi khỏi cửa sổ được TÓM TẮT (chạy nền) thay vì cắt bỏ mất trí nhớ như trước.
_trim_history = compaction.trim_history


def _hub_enabled():
    """Hub MCP bật (mặc định) → mọi engine đấu 1 điểm; tắt qua settings mcp.hub=false (fallback cũ)."""
    return bool(cfgmod.read_settings().get("mcp", {}).get("hub", True))


async def _api_stream_mcp(prov, key, model, messages, reasoning="off", brain=None):
    """Model API/OAuth dùng MCP của Javis qua HUB: đa tài khoản + quyền + audit + builtin tools
    (file vault, use_skill) → engine API cũng là agent thực thụ. anthropic-api giờ CÓ tool loop.
    ChatGPT OAuth ở các kênh tương tác đi qua Codex CLI native MCP, không dùng fallback này."""
    tools, route = [], {}
    if prov in ("openrouter", "openai", "anthropic-api", "gemini", "groq"):
        try:
            if _hub_enabled():
                vault_root = _brain_root(brain) if brain else None
                tools, route = await mcp_hub.discover_all("full", vault_root=vault_root)
            else:
                servers = mcp_store.servers_for_client()
                if servers:
                    tools, route = await mcp_client.discover(servers)
        except Exception as e:
            print(f"[mcp discover] {e}", file=__import__('sys').stderr)
    if tools:
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
    return _api_stream(prov, key, model, messages, reasoning)


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
            "Em đã đọc danh sách lịch thật nhưng có nhiều mục gần giống nhau nên chưa xoá để tránh nhầm. "
            "Anh nói đúng tên hoặc ID cần xoá:\n\n" + str(action.get("list_result") or "")
        )
    return "⚠ " + str(action.get("error") or "Không thể thao tác lịch.")


def _api_label(prov):
    return {"openrouter": "OpenRouter", "openai": "OpenAI", "anthropic-api": "Anthropic API",
            "openai-oauth": "ChatGPT (OAuth)", "gemini": "Google Gemini",
            "groq": "Groq"}.get(prov, prov)

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
    """Ghi ~/.codex/javis.config.toml → `codex exec -p javis` thấy MCP của Javis.
    Hub bật (mặc định): 1 entry hub - Codex dùng được MỌI transport (cả stdio/internal) + đa tài
    khoản + quyền. Hub tắt: per-server http như cũ. Trả 'javis' nếu có server, None nếu rỗng."""
    if _hub_enabled():
        return mcp_hub.codex_profile("full")
    path = Path.home() / ".codex" / "javis.config.toml"
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
            return "javis"
        if path.exists():
            path.unlink()
    except Exception as e:
        print(f"[codex profile] {e}", file=__import__('sys').stderr)
    return None


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
            cli.mcp_strict = bool(cfgmod.read_settings().get("mcp", {}).get("strict")) and cli.mcp_config is not None
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
def claude_status():
    return claude_auth_status()


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
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
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

    if section == "general":
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
        if patch.get("new_password"):
            if len(patch["new_password"]) < 4:
                return JSONResponse({"ok": False, "error": "Mật khẩu quá ngắn"}, status_code=400)
            h, salt = cfgmod.hash_password(patch["new_password"])
            cfg["auth"]["password_hash"] = h
            cfg["auth"]["salt"] = salt
        if patch.get("username"):
            cfg["auth"]["username"] = patch["username"].strip()
    else:
        return JSONResponse({"ok": False, "error": "section không hợp lệ"}, status_code=400)

    cfgmod.write_settings(cfg)
    if section == "telegram":
        try:
            restart_telegram()   # áp cấu hình bot ngay
        except Exception as e:
            print(f"[telegram restart] {e}", file=__import__('sys').stderr)
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
    if provider == "openai-oauth":
        # app-server là subprocess đồng bộ; chạy ở worker để request FastAPI
        # khác không đứng hình trong lúc Codex nạp catalog.
        return await asyncio.to_thread(openai_oauth.list_models, openai_oauth.valid_creds())
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
    return {"models": fallback, "live": False, "error": last_err}


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

def _log_agent_run(brain, slug, task, out):
    try:
        d = _brain_memory_dir(brain) / "agents" / slug / "runs"
        d.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone(timedelta(hours=7)))
        with open(d / f"{now.strftime('%Y-%m-%d')}.md", "a", encoding="utf-8") as fh:
            fh.write(f"\n## {now.strftime('%H:%M')}\n**Task:** {task}\n\n**Kết quả:** {out[:1500]}\n")
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

    out = []
    for s in skill_router.list_skills(root):
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
        # path VẮNG (None) = điểm vào mặc định = BRAIN; path="" = trần (ổ đĩa); còn lại = tương đối trần
        d = broot if path is None else _safe_path(brain, path)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if not d.is_dir():
        return JSONResponse({"error": "Không phải thư mục"}, status_code=400)
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
    """Xuất 1 agent/skill/workflow (kèm phụ thuộc nếu deps=1) thành gói .zip để tải về, chia sẻ."""
    if kind not in ("agent", "skill", "workflow"):
        return JSONResponse({"error": "kind phải là agent/skill/workflow"}, status_code=400)
    if not skill_router.valid_slug(slug):
        return JSONResponse({"error": "slug không hợp lệ"}, status_code=400)
    data, fname = share_bundle.build_bundle(
        kind, slug,
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
    orb = None
    try:
        key = (cfgmod.read_settings().get("model", {}) or {}).get("openrouter_key")
        if key:
            import httpx
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get("https://openrouter.ai/api/v1/credits",
                                     headers={"Authorization": f"Bearer {key}"})
            if r.status_code == 200:
                d = (r.json() or {}).get("data") or {}
                tc, tu = d.get("total_credits"), d.get("total_usage")
                if tc is not None and tu is not None:
                    orb = {"total": round(float(tc), 4), "used": round(float(tu), 4),
                           "remaining": round(float(tc) - float(tu), 4)}
    except Exception:
        orb = None
    out["openrouter"] = orb
    return out


# ---- Dashboard Token (index log thô Claude + Codex + nhánh API) -----------------------
@app.get("/usage/summary")
async def usage_summary(period: str = "this_month", provider: str = "", project: str = "", refresh: int = 1):
    """Báo cáo token theo kỳ: KPI + breakdown + timeseries, kèm so kỳ trước. refresh=1 (mặc
    định) quét tăng dần trước khi trả (rẻ khi index đã ấm)."""
    if refresh:
        try:
            await asyncio.to_thread(usage_index.refresh)
        except Exception:
            pass
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
        try:
            await asyncio.to_thread(usage_index.refresh)
        except Exception:
            pass
    try:
        return {"items": await asyncio.to_thread(usage_index.insights, period=period)}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/usage/refresh")
async def usage_refresh():
    """Quét tăng dần 3 nguồn, trả số file/event xử lý lần này."""
    try:
        return await asyncio.to_thread(usage_index.refresh)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def execute_workflow(brain, slug, input="", tools=None):
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

    def _mk(sysprompt, model=None):
        # Agent model = Codex/ChatGPT → chạy qua Codex CLI (có tool file + MCP native của codex).
        # CHỈ ở chế độ foreground (tools is None): codex không giới hạn tool được như Claude
        # (--allowedTools), nên chạy nền an-toàn-file-only (tools != None) vẫn ép dùng Claude.
        if model and _is_codex_model(model) and tools is None and find_codex_cli():
            openai_oauth.write_codex_auth()   # bắc cầu token ChatGPT → ~/.codex/auth.json
            cc = CodexCLI(cwd=vault_root, tag="workflow", model=_codex_safe_model(model), instructions=sysprompt)
            _apply_codex_hub(cc, vault_root)   # MCP + đúng brain cho cron/nhắc hẹn
            return cc
        c = claude_engine(system_prompt=sysprompt, cwd=vault_root, tag="workflow", allowed_tools=tools)
        # Model Claude của AGENT (sonnet/opus/haiku/fable) được ÁP THẬT vào CLI.
        # Rỗng → dùng model phụ (việc nền) nếu có, cuối cùng None = mặc định CLI.
        c.model = ((model if not _is_codex_model(model) else "") or _aux_model() or None)
        if tools is not None:   # chạy nền hạn chế → cô lập MCP + chặn Bash/Web
            _mcpf = _empty_mcp_file()
            if _mcpf:
                c.mcp_config = _mcpf; c.mcp_strict = True
            c.disallowed_tools = ["Bash", "WebFetch", "WebSearch", "Task"]
            c.max_wall_s = 300
        else:
            # Ungated (allowed_tools=None, "chạy full quyền" - Studio bấm nút): plugin in-process
            # CÓ nạp (claude_sdk_engine._mcp_servers gọi _plugins_server() khi allowed_tools rỗng)
            # nên PHẢI gắn brain để ctx plugin (vd javis_generate_image) suy đúng vault - thiếu
            # dòng này thì rơi về Brain Default y hệt bug 0.9.70 đã vá ở đường chat (Nợ 1,
            # final-fix-gd2). KHÔNG gọi _apply_mcp() ở đây: nhánh này cố ý dựa vào setting_sources
            # (claude_sdk_engine.py _options(): permission_mode=bypassPermissions +
            # setting_sources=[user,project,local]) để kế thừa MCP/skill/auth có sẵn của máy như
            # 1 phiên `claude` tương tác thật - đúng ý đầu file main.py "claude CLI đã cài trên
            # máy → tự kế thừa MCP". Gọi apply_mcp sẽ ép gắn thêm cấu hình MCP hub, đổi hành vi
            # ngoài phạm vi lỗi vault_root đang vá.
            c.javis_vault = vault_root
        return c

    def _agent_sysprompt(aslug):
        ameta, abody = _read_md(_agents_dir(brain) / f"{aslug}.md")
        amem = _agent_memory(brain, aslug)
        sysprompt = (
            f"Bạn là agent **{ameta.get('name', aslug)}**.\nVai trò: {ameta.get('role','')}\n{abody}\n\n"
            f"Skills khả dụng: {', '.join(ameta.get('skills', []) or []) or '(không)'}. Dùng skill khi cần.\n"
            + (f"\n# Bộ nhớ của bạn:\n{amem}\n" if amem else "")
            + "\nLàm việc trong vault. Tập trung hoàn thành nhiệm vụ, trả kết quả rõ ràng, ngắn gọn."
        )
        return ameta.get("name", aslug), sysprompt, (ameta.get("model") or "").strip() or None

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

        prev = out
        yield {"type": "step_done", "i": i, "agent": agent_name, "output": out, "verified": verified}
        _log_agent_run(brain, agent_slug, task_f, out)
    yield {"type": "done", "result": prev}


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
    """Gửi 1 tin Telegram tới ĐÚNG chat_id (dùng cho nhắc hẹn). chat_id rỗng hoặc không nằm
    trong whitelist → gửi cho CHỦ bot (mọi ID whitelist). Trả (ok, error)."""
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


async def _notify_owner(owner_chat, text) -> tuple:
    """Báo cáo cho NGƯỜI YÊU CẦU loop/task (mặc định của Javis). Quy tắc:
      - owner_chat dạng "web:<sid>" → đẩy thẳng vào ĐÚNG khung chat web đã giao việc.
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
    nền chỉ có giá trị khi tới giờ nó nói được với ai đó - chưa đấu Telegram thì việc chạy xong
    rồi kết quả rơi vào hư không, người dùng tưởng Javis quên. Dùng để chặn ngay lúc TẠO."""
    try:
        tg = cfgmod.read_settings().get("telegram", {}) or {}
    except Exception:
        return True, ""      # không đọc được cấu hình thì đừng dựng rào, cứ để tạo
    if not tg.get("enabled"):
        return False, "bot Telegram chưa bật"
    if not tg.get("token"):
        return False, "chưa có bot token"
    if not tg_parse_ids(tg.get("chat_id")):
        return False, "chưa có Chat ID được phép"
    return True, ""


def _notify_live_warn() -> str:
    """Cấu hình đủ nhưng bot Telegram ĐANG lỗi thật (token bị thu hồi, 409 poll trùng...) thì
    việc tới giờ vẫn chạy mà tin không đi được. KHÔNG dùng để chặn tạo việc (lỗi có thể thoáng
    qua và tự khỏi), chỉ để nói ra ở trang Việc. Rỗng = không có gì đáng báo."""
    try:
        if not _TG_BOT or _TG_BOT.status not in ("error", "conflict"):
            return ""
        return f"bot Telegram đang lỗi ({_TG_BOT.status}): {(_TG_BOT.last_error or '')[:160]}"
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
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0 and "true" in (r.stdout or "").lower()
    except Exception:
        return False


async def _watchtower_reachable() -> bool:
    """True nếu container Watchtower (profile 'update') đang CHẠY và mở cổng API.
    Chỉ có ý nghĩa ở mode docker (host 'watchtower' trên mạng nội bộ compose). Biến env
    WATCHTOWER_TOKEN luôn được set sẵn trong compose nên KHÔNG đủ để kết luận - phải dò thật.
    Dò bằng cách MỞ KẾT NỐI TCP tới cổng, TUYỆT ĐỐI không gửi HTTP: endpoint /v1/update của
    Watchtower bị kích hoạt update kể cả với GET, nên một request 'thăm dò' sẽ trigger nhầm."""
    if not os.getenv("WATCHTOWER_TOKEN", ""):
        return False
    import asyncio
    writer = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("watchtower", 8080), timeout=4)
        return True   # bắt tay TCP xong = container Watchtower đang lắng nghe
    except Exception:
        return False  # không phân giải host / connection refused = Watchtower không chạy
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
    can = mode in ("native", "windows") or (mode == "docker" and await _watchtower_reachable())
    st = _read_update_state()
    return {"current": cur, "latest": latest, "update_available": avail,
            "mode": mode, "platform": _host_platform(), "can_self_update": can, "error": err,
            "previous_version": st.get("previous_version")}


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
                           capture_output=True, text=True, timeout=10)
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


def _autostart_command() -> str:
    """Lệnh chạy khi đăng nhập Windows: wscript chạy start-javis.vbs ẩn (kill cũ + chạy nền)."""
    vbs = str(PROJECT_ROOT / "start-javis.vbs")
    return f'wscript.exe //nologo "{vbs}"'


def _autostart_status() -> dict:
    """{supported, enabled, command, stale}. stale = đang bật nhưng trỏ đường dẫn cũ (đã move folder)."""
    if os.name != "nt":
        return {"supported": False, "enabled": False}
    expected = _autostart_command()
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_RUN_KEY) as k:
            try:
                val, _ = winreg.QueryValueEx(k, _AUTOSTART_NAME)
                return {"supported": True, "enabled": bool(val),
                        "command": val, "expected": expected,
                        "stale": bool(val) and val.strip() != expected}
            except FileNotFoundError:
                return {"supported": True, "enabled": False, "expected": expected}
    except FileNotFoundError:
        return {"supported": True, "enabled": False, "expected": expected}
    except Exception as e:
        return {"supported": True, "enabled": False, "expected": expected, "error": str(e)}


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
        return {"ok": True, "enabled": enabled}
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
async def tts_voices():
    import edge_tts   # lazy - xem ghi chú ở đầu file
    voices = await edge_tts.list_voices()
    return {
        "voices": [
            {"name": v["ShortName"], "gender": v["Gender"], "display": v["FriendlyName"]}
            for v in voices if v["Locale"].startswith("vi")
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
        def __init__(self, sid):
            self._sid = sid

        async def send_text(self, txt):
            try:
                o = json.loads(txt)
                o["session_id"] = self._sid
            except Exception:
                return
            await _CHAT_RUNTIME.publish(o)

    try:
        async def _do_turn(conv_sid, user_message, brain, turn_tag):
            ws = _SendProxy(conv_sid)               # các nhánh engine bên dưới dùng ws proxy này
            mcfg = cfgmod.read_settings().get("model", {})
            prov, kind, api_key, api_model = _chat_provider(mcfg)
            reasoning = _reasoning_level(mcfg)
            _row0 = store.get_session(conv_sid) or {}
            cli = claude_engine(system_prompt=SYSTEM_PROMPT, cwd=CLAUDE_CWD, tag=turn_tag)
            cli.session_id = _row0.get("cli_session_id") or None    # --resume đúng mạch phiên này
            final_text = ""

            await ws.send_text(json.dumps({
                "type": "status",
                "content": "Javis đang suy nghĩ..."
            }))

            # Nạp bộ nhớ của vault đang chọn vào system prompt (Javis luôn nhớ)
            # + block kênh (port gateway hermes): engine biết đang trả lời qua dashboard web
            # Ngân sách theo provider: Groq gói miễn phí chặn ở 12.000 token/phút, mà system
            # prompt đầy đủ đã hơn thế. Cắt TRƯỚC khi gọi, đừng gửi đi rồi ăn 429.
            sysprompt = build_system_prompt(brain, budget=prompt_budget(prov)) + channel_context.build_channel_block(
                "dashboard", {"session_id": conv_sid}, telegram_running=bool(_TG_BOT),
                port=_javis_port(), brain_root=_brain_root(brain))

            final_text = ""
            _schedule_action = await _schedule_cancel_action(user_message, brain)
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
                }))
            elif prov == "openai-oauth":
                # ===== ChatGPT subscription qua CODEX CLI - MCP/tool NATIVE (như Hermes, dùng codex của máy) =====
                actual_model = _codex_safe_model(api_model)   # gpt-5-mini/gpt-4o... → coerce về model Codex hợp lệ
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
                                     compaction.codex_bootstrap_prompt(_codex_raw, _codex_current))

                    async def _consume_codex(prompt, suppress_resume_error=False):
                        nonlocal final_text
                        resume_failed = False
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
                                usage_store.record("codex", actual_model, ev.get("tokens_in", 0), ev.get("tokens_out", 0))
                            elif et == "error":
                                if ev.get("resume_failed"):
                                    resume_failed = True
                                    if suppress_resume_error:
                                        continue
                                await ws.send_text(json.dumps({"type": "error", "content": ev["content"]}))
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
                        _fallback = compaction.codex_bootstrap_prompt(_codex_raw, _codex_current)
                        await _consume_codex(_fallback)
                    await ws.send_text(json.dumps({"type": "response", "content": final_text, "engine": "codex", "model": actual_model, "session_id": conv_sid}))
            elif (kind == "api" and api_key) or kind == "oauth":
                # ===== PROVIDER API/OAuth (openrouter | openai | anthropic-api | gemini) =====
                # Đi qua _api_stream_mcp: vòng gọi tool với MCP Javis + tool file brain + skill.
                # Chỉ rơi về chat trần khi hub không trả tool nào. KHÔNG phải "chat thuần".
                label = _api_label(prov)
                actual_model = api_model or "?"
                _ident = (
                    f"\n\n[Sự thật hệ thống - TUÂN THỦ tuyệt đối: Bạn đang chạy qua {label}, "
                    f"model thực tế là '{actual_model}'. Khi được hỏi bạn là AI/model nào, "
                    f"trả lời ĐÚNG tên model này. KHÔNG được tự nhận là model khác.]"
                )
                _head = [{"role": "system", "content": sysprompt + _ident}]
                # Resume: nạp lại lượt user/assistant cũ từ SQLite để engine API thấy lại mạch
                # hội thoại (trừ lượt user vừa lưu ở trên). prepare_history đảm bảo phần cũ CHỈ
                # rời payload khi đã vào tóm tắt nén - KHÔNG cắt câm như trim cũ (đó là lỗi mất
                # ngữ cảnh khi phiên dài / vừa đổi từ engine Claude sang API).
                _raw = [{"role": _m["role"], "content": _m["content"]}
                        for _m in store.get_messages(conv_sid)[:-1]
                        if _m["role"] in ("user", "assistant") and _m.get("content")]
                or_messages = await compaction.prepare_history(
                    _head, store, conv_sid, _raw, prov, api_key, api_model, _api_stream)
                or_messages.append({"role": "user", "content": user_message})
                gen = await _api_stream_mcp(prov, api_key, api_model, or_messages, reasoning, brain=brain)   # MCP đa-model qua hub
                async for ev in gen:
                    if ev["type"] == "meta":
                        actual_model = ev.get("model") or actual_model
                    elif ev["type"] == "usage":
                        usage_store.record(prov, actual_model, ev.get("input", 0), ev.get("output", 0))
                    elif ev["type"] == "tool_call":
                        await ws.send_text(json.dumps({"type": "tool_call", "tool": ev.get("name", ""), "content": f"⚙ MCP: {ev.get('name', '')}"}))
                    elif ev["type"] == "text":
                        final_text += ev["content"]
                        # tts:False → frontend chỉ hiển thị token, đọc TTS 1 lần ở cuối
                        await ws.send_text(json.dumps({"type": "stream", "content": ev["content"], "tts": False}))
                    elif ev["type"] == "error":
                        await ws.send_text(json.dumps({"type": "error", "content": ev["content"]}))
                # (or_messages là biến cục bộ của lượt - mỗi lượt dựng lại từ SQLite qua
                # prepare_history, nên không cần append/trim để giữ mạch; lịch sử ở store.)
                await ws.send_text(json.dumps({"type": "response", "content": final_text, "engine": prov, "model": actual_model, "session_id": conv_sid}))
            else:
                # ===== PROVIDER anthropic-cli - qua Claude Code, đầy đủ MCP / skill / session =====
                cli.system_prompt = sysprompt
                cli.model = api_model or mcfg.get("claude_model") or None   # alias opus/sonnet/haiku/fable
                _apply_mcp(cli, brain=brain)   # gắn MCP do Javis quản lý (nhiều shop POSCake...)
                _streamed = ""      # phần đã stream - phương án dự phòng khi luồng đứt trước 'final'
                _cli_sid = None
                _cost = None
                async for event in cli.query(_cli_think(reasoning, user_message)):
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
                        usage_store.record("cli", cli.model or mcfg.get("claude_model") or "mặc định",
                                           event.get("tokens_in", 0), event.get("tokens_out", 0), event.get("cost_usd") or 0)
                    elif etype == "error":
                        await ws.send_text(json.dumps({"type": "error", "content": event["content"]}))
                # Khung `response` PHẢI nằm NGOÀI vòng lặp. Trước đây nó nằm trong nhánh
                # `final`, nên luồng đứt trước khi có `final` (engine chết, mạng rớt) là client
                # không nhận `response` nào cả và bong bóng chat treo mãi - trong khi phần chữ
                # đã stream ra thì vẫn còn đó. Ba nhánh engine kia vốn đã gửi ngoài vòng lặp.
                final_text = final_text or _streamed
                await ws.send_text(json.dumps({"type": "response", "content": final_text, "session_id": conv_sid, "cli_session_id": _cli_sid, "cost_usd": _cost, "engine": "cli", "model": (mcfg.get("claude_model") or "mặc định")}))

            # Lưu lượt assistant: kho phiên + title + log Memory + hàng đợi tự học.
            # Đường lưu DÙNG CHUNG với Telegram (_persist_turn) - nó tự bóc khối điều khiển.
            if final_text:
                await _persist_turn(store, conv_sid, brain, user_message, final_text)
                # Nén NỀN phần lịch sử cũ sắp rơi khỏi cửa sổ (chỉ engine API - CLI tự quản
                # context). Lỗi nén không ảnh hưởng lượt chat; lượt sau vẫn còn fallback trim.
                if kind == "api" and api_key and prov in ("openrouter", "openai", "anthropic-api", "gemini", "groq"):
                    try:
                        asyncio.create_task(compaction.maybe_compact(
                            store, conv_sid, prov, api_key, api_model, _api_stream))
                    except Exception as _e:
                        print(f"[compact hook] {_e}", file=__import__('sys').stderr)

        async def run_turn(conv_sid, user_message, brain, turn_tag):
            try:
                await _do_turn(conv_sid, user_message, brain, turn_tag)
            except asyncio.CancelledError:
                await send_raw({"type": "system", "content": "Đã dừng lượt này.", "session_id": conv_sid})
            except Exception as e:
                await send_raw({"type": "error", "content": f"Lỗi xử lý: {type(e).__name__}: {e}", "session_id": conv_sid})
            finally:
                await send_raw({"type": "turn_done", "session_id": conv_sid})
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
            prov, kind, api_key, api_model = _chat_provider(mcfg)
            engine_label = ("codex" if prov == "openai-oauth"
                            else prov if ((kind == "api" and api_key) or kind == "oauth")
                            else "cli")
            conv_sid = store.get_or_create(
                payload.get("session_id"), brain=brain, engine=engine_label,
                model=(api_model or mcfg.get("claude_model")))
            if engine_label != "codex":
                # Provider khác vừa chen một lượt: thread Codex cũ không chứa lượt này nữa.
                # Xoá liên kết để lần quay lại Codex bootstrap từ SQLite thay vì resume mạch stale.
                store.clear_codex_thread_id(conv_sid)
            if _CHAT_RUNTIME.get_job(conv_sid):
                await send_raw({"type": "error", "content": "Phiên này đang trả lời - đợi lượt hiện tại xong đã.", "session_id": conv_sid})
                continue
            store.append_message(conv_sid, "user", user_message)
            turn_tag = f"chat:{conv_sid[:12]}:{uuid.uuid4().hex[:8]}"
            task = asyncio.create_task(run_turn(conv_sid, user_message, brain, turn_tag))
            _CHAT_RUNTIME.register_job(conv_sid, task, turn_tag)
    except WebSocketDisconnect:
        pass
    finally:
        # Chỉ bỏ subscriber; job server tiếp tục chạy và tự lưu kết quả.
        _CHAT_RUNTIME.remove_client(client_id)


# ============================================================
# Phiên hội thoại - list / view / search / rename / delete (sqlite + fts5)
# /sessions/search KHAI BÁO TRƯỚC /sessions/{id} để không bị nuốt làm path param.
# ============================================================
@app.get("/sessions")
async def sessions_list(brain: str = Query(None), limit: int = Query(50)):
    return {"sessions": get_store().list_sessions(limit=limit, brain=brain)}


@app.get("/sessions/search")
async def sessions_search(q: str = Query(...), brain: str = Query(None), limit: int = Query(30)):
    return {"results": get_store().search(q, limit=limit, brain=brain)}


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
    return {"ok": True}


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
        sess["sid"] = store.get_or_create(sid, brain=brain, engine=engine_label, model=model)
        return sess["sid"]
    sess["sid"] = store.create_session(brain=brain, engine=engine_label, model=model,
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


async def _tg_answer(text, meta=None, progress=None):
    """Vỏ ngoài một lượt Telegram: khớp phiên trong kho -> chạy engine -> LƯU lượt.

    Vì sao tách vỏ khỏi lõi: trước 0.9.244 nhánh Telegram không lưu gì cả, nên hội thoại
    Telegram vắng mặt ở `/sessions`, ở `brain/Memory/conversations`, và ở vòng tự học -
    lỗ hổng chức năng lớn nhất trong danh sách trôi lệch giữa hai bản dispatch.

    Quy ước trả về của lõi: **dict = câu trả lời thật** (đáng lưu), **chuỗi = thông báo lỗi**
    (không lưu). Đó là lý do nhánh gateway lịch cũng trả dict chứ không trả chuỗi như trước.
    """
    # ĐA PHIÊN: định tuyến theo chat_id → ngữ cảnh của mỗi tài khoản tách biệt.
    chat_id = str((meta or {}).get("chat_id") or "default")
    sess = _tg_session(chat_id)
    brain = _tg_brain(chat_id)   # brain riêng của phiên (đổi bằng /brain), mặc định theo Settings
    mcfg = cfgmod.read_settings().get("model", {})
    prov, kind, api_key, api_model = _chat_provider(mcfg)
    # Nhãn engine phải do VỎ quyết định rồi truyền xuống lõi: hai bên tự suy ra độc lập là
    # có ngày phiên bị dán nhãn 'cli' trong khi lượt thật chạy qua OpenRouter.
    engine_label = ("codex" if prov == "openai-oauth"
                    else prov if ((kind == "api" and api_key) or kind == "oauth")
                    else "cli")

    if engine_label != "codex" and sess.get("codex") is not None:
        # Bản tương ứng của `store.clear_codex_thread_id` bên dashboard: provider khác vừa chen
        # một lượt, thread Codex cũ KHÔNG chứa lượt đó. Quay lại Codex mà cứ resume thread cũ là
        # nó mù các lượt ở giữa. Xoá liên kết thôi, giữ nguyên đối tượng (cwd/instructions vẫn
        # dùng lại được); lượt Codex kế tiếp sẽ bootstrap từ kho phiên.
        try:
            sess["codex"].session_id = None
        except Exception:
            sess["codex"] = None

    store = get_store()
    conv_sid = ""
    try:
        conv_sid = _tg_conv_sid(store, sess, brain, engine_label,
                                api_model or mcfg.get("claude_model"))
        store.append_message(conv_sid, "user", text)
    except Exception as e:
        print(f"[telegram session] {e}", file=__import__('sys').stderr)

    out = await _tg_answer_engine(
        text, meta, progress, chat_id=chat_id, sess=sess, brain=brain, mcfg=mcfg,
        prov=prov, kind=kind, api_key=api_key, api_model=api_model,
        store=store, conv_sid=conv_sid)

    if conv_sid and isinstance(out, dict):
        try:
            await _persist_turn(store, conv_sid, brain, text, out.get("text") or "")
        except Exception as e:
            print(f"[telegram persist] {e}", file=__import__('sys').stderr)
    return out


def _tg_ket(clean_out, files, canh_bao="", loi=()):
    """Gói câu trả lời Telegram: cảnh báo hệ thống lên đầu, lỗi giữa lượt xuống cuối.

    Lỗi giữa lượt KHÔNG huỷ câu trả lời (dashboard vốn coi lỗi là không chí mạng), nhưng cũng
    không được giấu: giấu đi thì user tưởng lượt chạy sạch trong khi có tool đã hỏng."""
    txt = (canh_bao or "") + (clean_out or "")
    if loi:
        txt += "\n\n⚠ Có lỗi giữa lượt: " + str(loi[0])
    return {"text": txt, "files": files or []}


async def _tg_answer_engine(text, meta, progress, *, chat_id, sess, brain, mcfg,
                            prov, kind, api_key, api_model, store=None, conv_sid=""):
    """Lõi 4 nhánh engine của một lượt Telegram. Trả dict khi có câu trả lời thật,
    trả CHUỖI khi là thông báo lỗi (vỏ `_tg_answer` dựa vào đó để biết lượt nào đáng lưu)."""
    sess["last"] = text
    sess["sent"] = set()    # lượt mới → reset dedupe (endpoint /telegram/send-file add vào đây)
    reasoning = _reasoning_level(mcfg)

    async def _p(s):
        # Báo trạng thái trung gian về kênh (Telegram) cho user đỡ lo khi chờ. Bỏ qua nếu lỗi.
        if progress:
            try:
                await progress(s)
            except Exception:
                pass
    # Block kênh (port gateway hermes-agent): engine biết đang trả lời qua Telegram,
    # ai đang nhắn, và cách gửi file trả về (auto-attach + endpoint send-file).
    _tg_prov = _chat_provider(cfgmod.read_settings().get("model", {}))[0]
    sysprompt = build_system_prompt(brain, budget=prompt_budget(_tg_prov)) + channel_context.build_channel_block(
        "telegram", meta, telegram_running=True, port=_javis_port(), brain_root=_brain_root(brain))
    schedule_action = await _schedule_cancel_action(text, brain)
    if schedule_action:
        for call in schedule_action.get("calls") or []:
            await _p(f"⚙ Lịch: {call.split(':')[-1]}")
        # dict (không phải chuỗi): đây là câu trả lời THẬT nên vỏ phải lưu nó lại.
        return {"text": channel_context.strip_control_blocks(_schedule_cancel_reply(schedule_action)),
                "files": []}
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
                elif et == "error":
                    if ev.get("resume_failed"):
                        resume_hong = True
                        if bo_qua_loi_resume:
                            continue    # còn cửa dựng lại, chưa phải lúc kêu lỗi với user
                    loi.append(str(ev.get("content") or "Codex lỗi"))
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
        async for ev in (await _api_stream_mcp(prov, api_key, api_model, sess["or"], reasoning, brain=brain)):
            if ev["type"] == "text":
                if not _pinged:
                    _pinged = True; await _p("✍ Đang soạn câu trả lời…")
                out += ev["content"]
            elif ev["type"] == "meta":
                actual_model = ev.get("model") or actual_model   # model THẬT (OpenRouter tính tiền theo cái này)
            elif ev["type"] == "usage":
                # Thiếu dòng này tới 0.9.244: mọi lượt Telegram không đi qua Codex đều không
                # được tính vào bảng Mức dùng.
                usage_store.record(prov, actual_model, ev.get("input", 0), ev.get("output", 0))
            elif ev["type"] == "tool_call":
                await _p(f"⚙ Đang gọi công cụ: {ev.get('name', '')}")
            elif ev["type"] == "error":
                # KHÔNG return ngay: một tool hỏng giữa chừng không có nghĩa là cả lượt hỏng,
                # luồng thường chạy tiếp và vẫn ra câu trả lời. Dashboard vốn xử lý như vậy.
                loi.append(str(ev.get("content") or "lỗi không rõ"))
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
        async for ev in cli.query(_cli_think(reasoning, text)):
            et = ev["type"]
            if et == "final":
                out = ev.get("content") or out
                # Thiếu dòng này tới 0.9.244 (xem nhánh API ngay trên): lượt Telegram qua
                # Claude Code không được tính vào bảng Mức dùng.
                usage_store.record("cli", cli.model or mcfg.get("claude_model") or "mặc định",
                                   ev.get("tokens_in", 0), ev.get("tokens_out", 0),
                                   ev.get("cost_usd") or 0)
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
        "/model - xem/đổi model (opus|sonnet|haiku|fable|<claude-id> hoặc <provider/id> cho OpenRouter)\n"
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
_TG_PROVIDERS = [   # (id provider, nhãn nút ngắn)
    ("anthropic-cli", "Claude Code"),
    ("openai-oauth", "ChatGPT"),
    ("openrouter", "OpenRouter"),
    ("anthropic-api", "Claude API"),
    ("openai", "OpenAI API"),
]
_TG_MODEL_LISTS = {}   # provider -> list model id ĐÃ render (index nút ổn định khi bấm)
_TG_PAGE = 8           # model mỗi trang (lưới 2 cột x 4 hàng)


def _tg_prov_label(pid):
    return dict(_TG_PROVIDERS).get(pid, pid)


def _tg_prov_ready(pid, m):
    """Provider dùng được ngay chưa? CLI luôn sẵn; OAuth cần đã kết nối; API cần key
    (cùng logic 'configured' của _providers_view)."""
    d = _provider_def(pid) or {}
    if d.get("kind") == "oauth":
        o = m.get("openai_oauth") or {}
        return bool(o.get("access_token") or o.get("refresh_token"))
    kf = d.get("key_field")
    return True if kf is None else bool(m.get(kf))


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
    ready = [(pid, lb) for pid, lb in _TG_PROVIDERS if _tg_prov_ready(pid, m)]
    lists = await asyncio.gather(*(_tg_models_for(pid) for pid, _ in ready))
    rows, row = [], []
    for (pid, lb), ids in zip(ready, lists):
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
        if pid not in dict(_TG_PROVIDERS):
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


async def _tg_command(cmd, arg, chat=None):
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
            # Không whitelist cứng → model mới dùng ngay. id chứa "/" = OpenRouter;
            # gpt*/*-codex = ChatGPT (Codex, cần đã kết nối); còn lại = alias/id Claude.
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
                              download_dir=_tg_inbox_dir)
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
            "last_error": (_TG_BOT.last_error if _TG_BOT else "")}


@app.post("/telegram/restart")
async def telegram_restart():
    return {"ok": True, "running": restart_telegram()}


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
async def _warm_mcp_hub():
    """Làm nóng hub sau khi boot: mở sẵn session MCP (stdio npx lần đầu phải tải package)
    để tin nhắn/tool call đầu tiên không phải chờ."""
    async def _w():
        try:
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


if __name__ == "__main__":
    import uvicorn
    # 127.0.0.1: chỉ máy này truy cập được (an toàn - tránh người khác trong mạng LAN
    # chạy Claude full quyền trên máy + vault của bạn). Đổi qua JAVIS_HOST nếu cần.
    host = os.getenv("JAVIS_HOST", "127.0.0.1")
    port = int(os.getenv("JAVIS_PORT", "7777"))
    uvicorn.run("main:app", host=host, port=port, reload=False)
