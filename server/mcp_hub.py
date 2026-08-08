"""
JAVIS MCP HUB - điểm đấu DUY NHẤT cho mọi engine.
- Claude Code / Codex thấy hub như MỘT MCP server http tên "javis" (config 1 entry).
- Engine API (OpenRouter/OpenAI/Anthropic) gọi in-process qua discover_all().
Hub lo trọn: gộp tool mọi connection (namespaced), ENFORCE quyền 3 mức + mode loop
(lớp CỨNG, không phụ thuộc prompt), audit log, cache, rate limit, meta-tool.

Quyền: mcp_catalog.allowed(connector, perm_connection, mode_lượt_chạy, tool, args).
Mode đến từ header X-Javis-Mode (Claude/Codex) hoặc tham số (engine API).
"""
import asyncio
import json
import os
import re
import secrets as _secrets
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from fastapi.responses import JSONResponse, Response

import config
import mcp_catalog
import mcp_client
import mcp_store
import skill_router
import skill_usage
from config import STATE_DIR

_TOKEN_PATH = STATE_DIR / ".hub_token"
_AUDIT_PATH = STATE_DIR / "mcp_audit.jsonl"
_CACHE_TTL = 60
_cache = {}          # (mode, vault_root) -> {"tools", "route", "ts", "mtime"}
_rate = {}           # conn_id -> deque[timestamps]


# ============================================================
# Token / URL
# ============================================================
_mem_token = None   # fallback khi STATE_DIR không ghi được - PHẢI ngẫu nhiên, không được hằng số


def hub_token():
    global _mem_token
    try:
        if _TOKEN_PATH.exists():
            t = _TOKEN_PATH.read_text(encoding="utf-8").strip()
            if t:
                return t
        t = _secrets.token_urlsafe(32)
        _TOKEN_PATH.write_text(t, encoding="utf-8")
        try:
            os.chmod(_TOKEN_PATH, 0o600)
        except Exception:
            pass
        return t
    except Exception as e:
        print(f"[hub] token: {e}", file=sys.stderr)
        if not _mem_token:
            _mem_token = _secrets.token_urlsafe(32)
        return _mem_token


def hub_port():
    try:
        return int(os.getenv("JAVIS_PORT", "7777"))
    except ValueError:
        return 7777


def hub_url():
    return f"http://127.0.0.1:{hub_port()}/hub/mcp"


def allow_patterns():
    """Pattern cho --allowedTools của loop: mọi tool qua hub đều mang tên mcp__javis__*."""
    return ["mcp__javis"]


# ============================================================
# Audit
# ============================================================
def _audit_append(rec):
    try:
        if _AUDIT_PATH.exists() and _AUDIT_PATH.stat().st_size > 5_000_000:
            _AUDIT_PATH.replace(_AUDIT_PATH.with_suffix(".jsonl.1"))
        with _AUDIT_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[hub audit] {e}", file=sys.stderr)


def audit_tail(limit=50, conn_id=None):
    try:
        if not _AUDIT_PATH.exists():
            return []
        lines = _AUDIT_PATH.read_text(encoding="utf-8").splitlines()
        out = []
        for line in reversed(lines):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if conn_id and rec.get("conn_id") != conn_id:
                continue
            out.append(rec)
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


# ============================================================
# Rate limit (catalog rate_limit.calls_per_min - vd Zalo chống spam/ban)
# ============================================================
def _rate_ok(conn_id, connector):
    lim = ((connector or {}).get("rate_limit") or {}).get("calls_per_min")
    if not lim:
        return True
    dq = _rate.setdefault(conn_id, deque())
    now = time.time()
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= int(lim):
        return False
    dq.append(now)
    return True


# ============================================================
# Guarded call - lớp quyền CỨNG + audit quanh mọi tool call
# ============================================================
def _guard(ent, fn, mode):
    """Bọc 1 route entry MCP thành async call có kiểm quyền + audit."""
    conn = ent["conn"]
    tool = ent["tool"]
    connector = mcp_catalog.get(conn.get("connector_id"))

    async def _call(args):
        cls = mcp_catalog.classify(connector, tool, args)
        ok, why = mcp_catalog.allowed(connector, conn.get("perm"), mode, tool, args)
        if ok and not _rate_ok(conn["id"], connector):
            ok, why = False, (f"Kết nối '{conn.get('label')}' vượt giới hạn tần suất "
                              f"(chống spam/khoá tài khoản). Chờ 1 phút rồi thử lại.")
        if not ok:
            _audit_append({"ts": datetime.now().isoformat(timespec="seconds"), "conn_id": conn["id"],
                           "connector": conn.get("connector_id"), "label": conn.get("label"),
                           "tool": tool, "mode": mode, "cls": cls, "ok": False, "ms": 0,
                           "err": why[:200], "args_keys": sorted((args or {}).keys())})
            return "ERROR: " + why
        t0 = time.time()
        result = await mcp_client.call_route({fn: {"spec": ent["spec"], "tool": tool}}, fn, args)
        _audit_append({"ts": datetime.now().isoformat(timespec="seconds"), "conn_id": conn["id"],
                       "connector": conn.get("connector_id"), "label": conn.get("label"),
                       "tool": tool, "mode": mode, "cls": cls,
                       "ok": not str(result).startswith("ERROR:"), "ms": int((time.time() - t0) * 1000),
                       "err": str(result)[:200] if str(result).startswith("ERROR:") else "",
                       "args_keys": sorted((args or {}).keys())})
        # Lỗi từ dịch vụ trả về NGUYÊN VĂN tiếng Anh thì model phải tự đoán, và nó đoán sai:
        # vụ 2026-07-30 Google trả "The caller does not have permission", model kết luận là hub
        # của Javis chặn quyền rồi đi sửa nhầm tầng. GẮN THÊM chẩn đoán (không thay thế - giữ
        # nguyên văn để còn lần ra manh mối) khi nhận ra họ lỗi quen mặt.
        if str(result).startswith("ERROR:"):
            chan_doan = chan_doan_loi(str(result).split("ERROR:", 1)[1].strip(), conn["id"])
            if chan_doan:
                return f"{result}\n\n[Javis chẩn đoán] {chan_doan}"
        return result

    return _call


# ============================================================
# AMBIENT / ACCOUNT MCP - connector đấu vào TÀI KHOẢN Claude (claude.ai: Drive/Gmail/lịch...).
# Chúng KHÔNG đi qua hub: engine Claude nạp thẳng qua setting_sources thành tool NATIVE
# mcp__<server>__*. Trước đây lazy layer + javis_connections MÙ với nhóm này → model tưởng chỉ
# có connector của hub, báo "không có Drive" dù tài khoản đã đấu. Ở đây hub ĐỌC danh sách
# (claude mcp list, cache nền vì chậm) để KỂ cho model biết + chỉ cách gọi (native, KHÔNG qua run).
# ============================================================
_AMBIENT_TTL = 300          # giây - danh sách connector tài khoản ít đổi, cache rộng
_ambient_cache = {"ts": 0.0, "servers": [], "refreshing": False}


def _ambient_enabled():
    """Có kèm gợi ý connector tài khoản Claude không (settings mcp.ambient_hint, mặc định True)."""
    try:
        return bool(config.read_settings().get("mcp", {}).get("ambient_hint", True))
    except Exception:
        return True


def _ambient_prefix(name):
    """Tiền tố tool native Claude sinh cho 1 MCP server (vd 'Google Drive' → 'Google_Drive')."""
    return re.sub(r"[^0-9A-Za-z]+", "_", str(name or "")).strip("_") or "mcp"


def _ambient_refresh():
    """Nạp danh sách MCP tài khoản (claude mcp list) trong THREAD nền - chậm (health check),
    TUYỆT ĐỐI không chạy trên event loop. Nuốt mọi lỗi (thiếu CLI, timeout...) → []."""
    servers = []
    try:
        import claude_cli
        for s in claude_cli.mcp_native_list() or []:
            name = str(s.get("name") or "").strip()
            if name and s.get("connected"):
                servers.append({"name": name, "url": s.get("url") or ""})
    except Exception as e:
        print(f"[hub ambient] {type(e).__name__}: {e}", file=sys.stderr)
    finally:
        _ambient_cache["servers"] = servers
        _ambient_cache["ts"] = time.time()
        _ambient_cache["refreshing"] = False


def _ambient_servers():
    """Connector tài khoản Claude đang 'Connected' (KHÔNG chặn): trả cache, làm mới ở thread nền
    khi hết hạn. Lần đầu trả [] rồi ấm dần các lần sau. Tắt qua settings mcp.ambient_hint=false."""
    if not _ambient_enabled():
        return []
    c = _ambient_cache
    if not c["refreshing"] and time.time() - c["ts"] > _AMBIENT_TTL:
        c["refreshing"] = True
        try:
            threading.Thread(target=_ambient_refresh, daemon=True).start()
        except Exception:
            c["refreshing"] = False
    return list(c["servers"])


def _match_ambient(ambient, query):
    """Connector tài khoản khớp query (tên xuất hiện trong query, hoặc chung từ khoá). query
    rỗng → []. Dùng cho javis_search_tools chỉ model sang tool native khi hỏi đúng nguồn đó."""
    q = (query or "").strip().lower()
    if not q or not ambient:
        return []
    terms = set(_WORD_RE.findall(q))
    out = []
    for s in ambient:
        name = str(s.get("name") or "")
        nwords = set(_WORD_RE.findall(name.lower()))
        if (name.lower() and name.lower() in q) or (nwords & terms) or _ambient_prefix(name).lower() in q:
            out.append(s)
    return out


# ============================================================
# Builtin tools (engine API): file trong vault + use_skill + meta connections
# ============================================================
def _safe_path(vault_root, p):
    root = Path(vault_root).resolve()
    target = (root / str(p or "")).resolve()
    if root != target and root not in target.parents:
        raise ValueError(f"đường dẫn '{p}' nằm ngoài vault")
    return target


def _connections_json(include_ambient=False, hidden=None):
    hidden = hidden or {}
    out = []
    for c in mcp_store.list_connections():
        con = mcp_catalog.get(c.get("connector_id")) or {}
        rec = {"connector": con.get("name") or c.get("connector_id"), "label": c.get("label"),
               "namespace": c.get("slug"), "perm": c.get("perm"), "enabled": c.get("enabled"),
               "is_default": c.get("is_default"), "transport": c.get("transport"),
               "source": "javis_hub"}
        # Tool bị mức quyền GIẤU khỏi danh sách. Không kể ra thì model tưởng nguồn này không
        # làm được việc đó và đi đường vòng (vụ Lịch mức Chỉ đọc: create_event biến mất, model
        # loay hoay tìm tool tạo sự kiện rồi kết luận sai là kết nối hỏng).
        h = hidden.get(c.get("id")) or {}
        if h.get("tools"):
            rec["tool_bi_an_do_quyen"] = sorted(h["tools"])[:15]
            rec["cach_mo"] = (f"Các tool này CÓ THẬT nhưng bị ẩn vì kết nối đang ở mức "
                              f"'{h.get('perm')}'. Muốn dùng thì bảo user tự nâng mức ở trang "
                              "Kết nối - Javis KHÔNG tự nâng quyền.")
        out.append(rec)
    # Connector đấu vào TÀI KHOẢN Claude (Drive/Gmail/lịch...): engine Claude đã có sẵn dưới dạng
    # tool native mcp__<server>__* → chỉ model gọi THẲNG, KHÔNG bọc qua javis_run_tool/hub.
    if include_ambient:
        for s in _ambient_servers():
            out.append({"connector": s["name"], "label": s["name"], "source": "claude_account",
                        "goi_the_nao": f"Đã có sẵn trong danh sách tool: mcp__{_ambient_prefix(s['name'])}__* "
                                       "- GỌI THẲNG, không qua javis_run_tool."})
    return json.dumps(out, ensure_ascii=False, indent=1)


def _skills_dir(vault_root):
    """Canonical <vault>/skills (qua skill_router - dùng chung logic với main.py)."""
    return skill_router.skills_base(vault_root, canonical=True)


def _list_skills(vault_root):
    """Slug các skill đang BẬT (list[str], giữ nguyên kiểu để chỗ join không vỡ)."""
    return skill_router.enabled_slugs(vault_root)


def _builtin_tools(mode, vault_root, include_ambient=False, hidden=None):
    """(tools_spec, route) các tool nội bộ cho engine API. Claude/Codex có tool file native
    nên hub HTTP không trả nhóm này (chỉ meta javis_connections).
    include_ambient=True (đường engine Claude): javis_connections kèm cả connector tài khoản
    Claude (Drive/Gmail...) để model biết chúng tồn tại (gọi qua tool native mcp__*, không qua hub).
    hidden: {conn_id: {perm, tools}} tool bị mức quyền lọc khỏi danh sách - kể ra trong
    javis_connections để model biết mà nói đúng lý do thay vì tưởng nguồn thiếu năng lực."""
    tools, route = [], {}

    def add(name, description, props, required, call, effect="read"):
        tools.append({"fn": name, "server": "javis", "name": name, "description": description,
                      "schema": {"type": "object", "properties": props, "required": required}})
        route[name] = {
            "call": call,
            "source_type": "builtin",
            "source_id": "javis-core",
            "effect": effect,
            "required_mode": "readonly" if effect in ("none", "read") else (
                "safe" if effect == "write" else "full"
            ),
            "health": "healthy",
        }

    add("javis_connections", "Liệt kê các nguồn dữ liệu (connector/tài khoản MCP) đang đấu vào Javis, "
        "kèm mức quyền và các tool đang bị mức quyền ẩn (tool_bi_an_do_quyen). Gồm cả connector đấu "
        "vào TÀI KHOẢN Claude (Drive/Gmail/lịch...) - loại source='claude_account' gọi THẲNG qua "
        "tool native mcp__<tên>__*, KHÔNG qua javis_run_tool. Dùng khi cần biết đang có nguồn nào / "
        "tài khoản nào là mặc định, hoặc khi không tìm thấy tool tưởng phải có.",
        {}, [], lambda args: _async_const(_connections_json(include_ambient, hidden)))

    if not vault_root:
        return tools, route

    async def _read(args):
        p = _safe_path(vault_root, (args or {}).get("path"))
        if not p.is_file():
            return f"ERROR: không có file '{(args or {}).get('path')}'"
        text = p.read_text(encoding="utf-8", errors="replace")
        return text[:100_000] + (f"\n… [cắt, file dài {len(text):,} ký tự]" if len(text) > 100_000 else "")

    async def _ls(args):
        p = _safe_path(vault_root, (args or {}).get("path") or ".")
        if not p.is_dir():
            return f"ERROR: không có thư mục '{(args or {}).get('path')}'"
        rows = []
        for e in sorted(p.iterdir())[:300]:
            rows.append(("[d] " if e.is_dir() else "    ") + e.name)
        return "\n".join(rows) or "(trống)"

    async def _write(args):
        if mcp_catalog.effective_perm("full", mode) == "readonly":
            # Câu này phải NÓI RÕ ĐÂY LÀ QUYỀN CỦA JAVIS, không phải lỗi máy. Bản cũ chỉ ghi
            # "chế độ hiện tại (suggest/chỉ đọc) không được ghi file", và model đọc xong tự
            # dựng ra một nguyên nhân nghe hợp lý mà sai hoàn toàn - người dùng thật nhận
            # được câu "môi trường filesystem đang lỗi quyền sandbox" rồi đi tìm lỗi ổ đĩa,
            # trong khi thứ cần làm chỉ là nâng mức việc lên Ghi nháp (2026-08-04).
            # Kèm luôn việc-cần-làm-thay-thế để lượt đó vẫn ra kết quả dùng được.
            return ("ERROR: KHÔNG ghi được file vì việc này đang chạy ở mức 'Chỉ đọc' (suggest). "
                    "Đây là GIỚI HẠN QUYỀN do người dùng đặt, KHÔNG phải lỗi ổ đĩa, không phải "
                    "lỗi sandbox, không phải thiếu quyền hệ điều hành - đừng báo cáo sai nguyên "
                    "nhân. Muốn ghi thật: mở trang Việc, nâng mức của việc này lên 'Ghi nháp' "
                    "(auto) rồi chạy lại. Ngay bây giờ: ĐỪNG thử ghi lại, hãy đưa TRỌN nội dung "
                    "file vào câu trả lời để người dùng tự lưu.")
        p = _safe_path(vault_root, (args or {}).get("path"))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str((args or {}).get("content") or ""), encoding="utf-8")
        return f"Đã ghi {p.name} ({len(str((args or {}).get('content') or ''))} ký tự)"

    async def _skill(args):
        name = str((args or {}).get("name") or "").strip()
        # skill_router.resolve_skill_file đã validate slug + chống traversal, tìm canonical
        # skills/ → .claude/skills → .agents.
        f = skill_router.resolve_skill_file(vault_root, name)
        if not f or not f.is_file():
            return ("ERROR: không có skill đó. Skill khả dụng: "
                    + (", ".join(_list_skills(vault_root)) or "(chưa có)"))
        text = f.read_text(encoding="utf-8", errors="replace")[:60_000]
        # ĐIỂM ĐẾM DUY NHẤT: mọi engine nạp skill qua tool này đều đi ngang đây. Chỉ đếm ở
        # đường THÀNH CÔNG - nhánh trên đã lọc slug sai/skill tắt nên không đếm gõ nhầm.
        # Dùng f.parent.name (slug canonical trên đĩa) chứ không dùng `name` thô từ engine.
        # bump có I/O đĩa + fsync trong lock (chặn) → đẩy qua thread để không chẹn event
        # loop (WebSocket/telegram poller/loop scheduler đều chạy chung loop này).
        # bump tự nuốt lỗi → sidecar hỏng không bao giờ làm gãy việc nạp skill.
        await asyncio.to_thread(skill_usage.bump, vault_root, f.parent.name)
        return text

    add("javis_read_file", "Đọc 1 file trong vault (Second Brain). path tương đối so với gốc vault.",
        {"path": {"type": "string"}}, ["path"], _read)
    add("javis_list_dir", "Liệt kê file/thư mục trong vault. path tương đối, bỏ trống = gốc vault.",
        {"path": {"type": "string"}}, [], _ls)
    add("javis_write_file", "Ghi/tạo file trong vault (ghi đè nếu có). Dùng khi cần lưu ghi chú, "
        "báo cáo, nháp. KHÔNG dùng cho hành động ra ngoài.",
        {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"], _write,
        effect="write")
    # Mô tả tool = router thu nhỏ: liệt kê slug + mô tả ngắn để engine biết KHI NÀO gọi skill nào.
    # Trần lấy từ skill_router (CHUNG với system prompt) - trước đây hub tự cắt 60, system prompt
    # cắt 100 - người viết skill không biết mình bị chấm theo thước nào.
    metas = skill_router.list_enabled_meta(vault_root)
    _cap = skill_router.SKILL_LIST_MAX
    listing = "; ".join(f"{s['slug']}: {(s['description'] or '')[:skill_router.SKILL_DESC_MAX]}"
                        for s in metas[:_cap])
    if len(metas) > _cap:
        listing += f"; …(+{len(metas) - _cap} skill nữa)"
    add("javis_use_skill",
        "Nạp nội dung 1 skill (hướng dẫn chuyên sâu) rồi LÀM THEO. Truyền name=<slug>. "
        "Skill khả dụng (slug: mô tả): " + (listing or "(chưa có)"),
        {"name": {"type": "string"}}, ["name"], _skill)
    return tools, route


async def _async_const(v):
    return v


# ============================================================
# LAZY TOOLS - chống phình context khi đấu nhiều connector.
# Thay vì phơi hết hàng trăm schema tool MCP MỖI lượt (câu nào cũng gánh), hub chỉ phơi
# builtins + plugin + 2 meta-tool: javis_search_tools (tìm tool theo nhu cầu) và
# javis_run_tool (gọi tool tìm được). Model tự tìm theo NGỮ CẢNH rồi mới nạp schema →
# câu không cần MCP tốn gần 0 token tool. Kế thừa NGUYÊN lớp quyền/audit/rate-limit vì
# run đi qua đúng call_route của route ĐẦY ĐỦ (đã _guard). Model chỉ THẤY meta-tool nên
# không thể gọi thẳng tool pool → buộc qua run (protocol tự ép).
# Kế hoạch gốc: docs/dev/2026-07-ke-hoach-ket-noi-hub.md mục 3.3 ("lazy tools", để sau).
# ============================================================
_LAZY_SEARCH = "javis_search_tools"
_LAZY_RUN = "javis_run_tool"
_WORD_RE = re.compile(r"[^\W_]{2,}", re.UNICODE)   # từ khoá ≥2 ký tự (giữ Unicode/tiếng Việt)

# Nhóm tool HẠT NHÂN: luôn hiện thẳng, không bao giờ vào tầng lazy.
#
# Khai TƯỜNG MINH bằng tên. Trước đây pool được suy ra ngầm bằng "route entry có 'conn' hay
# không", nên builtin và plugin lọt lưới VĨNH VIỄN: chúng không có 'conn' nên không bao giờ
# bị giấu, kể cả khi schema của chúng đã phình theo số skill/plugin người dùng cài. Đó đúng
# là bài toán O(N) mà cả tầng lazy sinh ra để chống, chỉ khác là nó nấp ở nhóm builtin.
#
# Tiêu chí vào nhóm hạt nhân, cả hai phải đúng:
#   1. Schema NHỎ và CỐ ĐỊNH, không lớn lên theo số thứ user cắm thêm.
#   2. Cần cho hầu hết mọi lượt, nên bắt model tìm trước khi dùng là lỗ vốn.
#
# Vì sao javis_use_skill KHÔNG ở đây dù skill là thứ trung tâm của Javis: mô tả của nó nhúng
# nguyên danh sách skill (tới SKILL_LIST_MAX mục × SKILL_DESC_MAX ký tự), tức là chính cái
# số hạng lớn theo N. Cho nó vào pool thì danh sách chỉ vào ngữ cảnh khi model tìm thứ khớp
# một skill, mà _rank_tools đọc description nên tìm "viết email" vẫn trúng nó như thường.
# javis_connections cũng vậy: đó là tool dùng khi bí, không phải mọi lượt.
CORE_TOOL_FNS = frozenset({
    "javis_read_file",
    "javis_list_dir",
    "javis_write_file",
})

# Mô tả nhóm tool nội bộ cho thực đơn lazy. Builtin/plugin không có connector trong
# mcp_catalog nên không tự có mô tả; thiếu dòng này thì model chỉ thấy "javis (javis, N tool)".
_LOCAL_GROUP_DESC = {
    "javis": "skill của brain, danh sách nguồn đang đấu, tiện ích nội bộ",
    "plugin": "tool do plugin cài thêm",
}


def _lazy_config():
    """(mode, threshold, top_k) từ settings mcp.*. mode: 'auto' | True | False.
    Đọc lỗi → mặc định an toàn ('auto', 40, 8)."""
    try:
        m = config.read_settings().get("mcp") or {}
    except Exception:
        m = {}

    def _int(v, d):
        try:
            return max(1, int(v))
        except (TypeError, ValueError):
            return d

    return m.get("lazy_tools", "auto"), _int(m.get("lazy_threshold"), 40), min(50, _int(m.get("lazy_top_k"), 8))


def _lazy_char_budget():
    """Trần ký tự schema tool được phép hiện thẳng, trước khi bắt buộc bật lazy.

    Vì sao cần thêm ngưỡng THEO KÍCH THƯỚC bên cạnh ngưỡng theo SỐ LƯỢNG: đếm tool không
    nói lên chi phí. Một tool duy nhất có thể rất đắt (javis_use_skill nhúng cả danh sách
    skill, phình theo số skill người dùng cài), trong khi mười tool schema gọn lại rẻ. Đếm
    số lượng để quyết định là đo nhầm đại lượng, và đó là lý do máy có 26 tool nặng 17k ký
    tự vẫn nằm dưới ngưỡng 40 nên lazy chưa từng kích hoạt lần nào.

    Mặc định 6000 ký tự (~1.7k token): đủ chỗ cho một bộ tool vừa phải mà vẫn còn xa hạn
    mức của model bị siết nhất."""
    try:
        m = config.read_settings().get("mcp") or {}
        v = int(m.get("lazy_char_budget", 6000))
        return max(500, v)
    except (TypeError, ValueError, AttributeError):
        return 6000


def _pool_chars(pool) -> int:
    """Số ký tự schema pool sẽ chiếm nếu phơi thẳng. Đây là đại lượng thật sự tốn tiền."""
    try:
        return sum(len(json.dumps(t, ensure_ascii=False)) for t in pool)
    except (TypeError, ValueError):
        return 0


def _lazy_on(pool_n, pool_chars=0):
    """Có bật chế độ lazy cho lần discover này không.

    'auto' bật khi ĐÔNG tool (pool_n > threshold) HOẶC khi schema NẶNG
    (pool_chars > trần ký tự). Hai điều kiện độc lập vì chúng bắt hai kiểu phình khác nhau:
    nhiều connector nhỏ, và ít tool nhưng mô tả phình theo số skill/plugin.
    pool_chars=0 (mặc định) thì chỉ xét số lượng - giữ nguyên hành vi cho caller cũ."""
    mode, thr, _ = _lazy_config()
    s = str(mode).strip().lower()
    if mode is True or s in ("true", "on", "1", "always"):
        return True
    if mode is False or s in ("false", "off", "0", "never"):
        return False
    return pool_n > thr or pool_chars > _lazy_char_budget()


def _connector_menu(pool, ambient=None):
    """Thực đơn MỎNG các nguồn đang đấu (namespace + tên + số tool + mô tả 1 dòng) để model
    biết CÓ GÌ mà với tới. Đây là phần LUÔN bật (rẻ, vài trăm token) thay cho cả rừng schema.
    ambient: connector tài khoản Claude (gọi native mcp__*, không qua run) - nêu để model khỏi
    tưởng chỉ có nguồn của hub."""
    seen = {}
    for t in pool:
        ns = t.get("namespace") or t.get("server") or "?"
        if ns not in seen:
            con = mcp_catalog.get(t.get("connector_id")) or {}
            desc = (con.get("description") or con.get("name") or "").strip()
            if not desc and ns in _LOCAL_GROUP_DESC:
                # Nhóm nội bộ (builtin/plugin) không có connector trong catalog nên trước đây
                # hiện trơ là "javis (javis, N tool)" - model không đoán được skill nằm trong
                # đó mà tìm. Nêu rõ có gì thì nó mới biết đường gọi search.
                desc = _LOCAL_GROUP_DESC[ns]
            seen[ns] = {"label": t.get("label") or con.get("name") or ns,
                        "desc": desc, "n": 0}
        seen[ns]["n"] += 1
    parts = []
    for ns, v in seen.items():
        d = (": " + v["desc"][:70]) if v["desc"] else ""
        parts.append(f"{ns} ({v['label']}, {v['n']} tool){d}")
    for s in (ambient or []):
        parts.append(f"mcp__{_ambient_prefix(s['name'])}__* ({s['name']}, tài khoản Claude - "
                     "tool native, gọi thẳng)")
    return "; ".join(parts)


def _rank_tools(pool, query, top_k):
    """Xếp hạng pool theo độ khớp query: khớp cả cụm (+5), đếm từ khoá (+1/từ), boost khi
    query nhắc thẳng namespace (+3). Trả top_k tool điểm > 0; query rỗng → [] (handler trả menu)."""
    q = (query or "").strip().lower()
    if not q:
        return []
    terms = set(_WORD_RE.findall(q))
    scored = []
    for t in pool:
        hay = " ".join([str(t.get("fn") or ""), str(t.get("name") or ""), str(t.get("description") or ""),
                        str(t.get("namespace") or ""), str(t.get("label") or "")]).lower()
        score = 5 if q in hay else 0
        score += sum(1 for w in terms if w in hay)
        ns = str(t.get("namespace") or "").lower()
        if ns and ns in q:
            score += 3
        if score > 0:
            scored.append((score, t))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _s, t in scored[:top_k]]


def _hidden_hint(hidden, only_ns=None):
    """Câu nhắc về tool bị mức quyền ẩn. "" khi không có gì bị ẩn.
    only_ns: chỉ kể các nguồn trong tập namespace này (dùng khi search ĐÃ trúng nguồn nào đó -
    lọc theo từ khoá tiếng Việt vô nghĩa vì tên tool là tiếng Anh); None = kể hết.
    Đây là mảnh thông tin cứu model khỏi kết luận sai "nguồn này không tạo được": tool có thật,
    chỉ là mức quyền của kết nối đang che nó."""
    if not hidden:
        return ""
    parts = []
    for h in hidden.values():
        names = sorted(h.get("tools") or [])
        if not names or (only_ns is not None and h.get("ns") not in only_ns):
            continue
        parts.append(f"{h.get('ns') or '?'} (mức {h.get('perm')}): " + ", ".join(names[:8]))
    if not parts:
        return ""
    return ("Đang bị mức quyền của kết nối ẩn khỏi danh sách - " + "; ".join(parts)
            + ". Các tool này CÓ THẬT: bảo user nâng mức quyền ở trang Kết nối rồi làm lại, "
              "ĐỪNG kết luận là nguồn không làm được hay kết nối hỏng.")


def _lazy_tools_and_route(visible_tools, visible_route, pool, full_route, top_k, ambient=None,
                          hidden=None):
    """Dựng (tools_spec, route) chế độ lazy: builtins/plugin hiện trực tiếp + 2 meta-tool.
    _search đóng gói `pool` (full tools_spec để xếp hạng); _run đóng gói `full_route` (dispatch
    qua call_route → giữ nguyên _guard quyền/audit/rate-limit).
    ambient: connector tài khoản Claude - _search chỉ model sang tool native mcp__* khi khớp
    (chúng KHÔNG nằm trong pool nên _run không gọi được; phải gọi thẳng)."""
    ambient = ambient or []
    menu = _connector_menu(pool, ambient)

    async def _search(args):
        q = (args or {}).get("query") or ""
        hits = _rank_tools(pool, q, top_k)
        amb = _match_ambient(ambient, q)
        if not hits and not amb:
            hint = _hidden_hint(hidden)
            return ("Không thấy tool khớp. Nguồn đang đấu: " + (menu or "(chưa có nguồn nào)")
                    + f". Nêu rõ nguồn hoặc việc cần làm rồi gọi lại {_LAZY_SEARCH}."
                    + (" " + hint if hint else ""))
        payload = {}
        hint = _hidden_hint(hidden, {t.get("namespace") for t in hits})
        if hint:
            payload["luu_y_quyen"] = hint
        if hits:
            payload["tools"] = [{"name": t.get("fn"), "description": (t.get("description") or "")[:400],
                                 "schema": t.get("schema") or {"type": "object", "properties": {}}}
                                for t in hits]
            payload["goi_the_nao"] = f"Gọi tool bằng {_LAZY_RUN}(name=<name>, args={{...}})."
        if amb:
            # Connector tài khoản Claude: tool native đã có sẵn trong danh sách tool của engine.
            payload["tai_khoan_claude"] = [
                {"connector": s["name"],
                 "goi_the_nao": f"Tool native mcp__{_ambient_prefix(s['name'])}__* đã có sẵn - GỌI THẲNG "
                                f"(KHÔNG qua {_LAZY_RUN}). Không thấy trong danh sách tool thì nguồn này "
                                "chưa được engine nạp (kiểm tra kết nối ở trang Model/Kết nối)."}
                for s in amb]
        return json.dumps(payload, ensure_ascii=False)

    async def _run(args):
        name = str((args or {}).get("name") or "").strip()
        targs = (args or {}).get("args")
        if isinstance(targs, str):          # vài model gói args thành chuỗi JSON
            try:
                targs = json.loads(targs)
            except (ValueError, TypeError):
                targs = {}
        if not isinstance(targs, dict):
            targs = {}
        if not name:
            return f"ERROR: thiếu 'name'. Dùng {_LAZY_SEARCH} để tìm tên tool trước."
        if name in (_LAZY_SEARCH, _LAZY_RUN):
            return f"ERROR: '{name}' là meta-tool, không gọi qua {_LAZY_RUN}."
        if name not in full_route:
            return (f"ERROR: không có tool '{name}'. Dùng {_LAZY_SEARCH} để lấy đúng tên "
                    "(phải khớp y hệt kết quả tìm).")
        return await mcp_client.call_route(full_route, name, targs)

    tools = list(visible_tools)
    route = dict(visible_route)
    tools.append({"fn": _LAZY_SEARCH, "server": "javis", "name": _LAZY_SEARCH,
                  "description": ("TÌM tool MCP theo NHU CẦU rồi mới nạp (tiết kiệm token: tool chỉ vào "
                                  "ngữ cảnh khi cần). query = mô tả việc cần làm hoặc tên nguồn. Nguồn "
                                  "đang đấu: " + (menu or "(chưa có nguồn nào)") + f". Kết quả trả tên + "
                                  f"tham số tool để gọi tiếp qua {_LAZY_RUN}; nếu khớp nguồn tài khoản "
                                  "Claude thì trả hướng dẫn gọi thẳng tool native mcp__<tên>__*."),
                  "schema": {"type": "object", "properties": {
                      "query": {"type": "string",
                                "description": "Việc cần làm / nguồn / từ khoá, vd 'doanh thu POS hôm nay'"}},
                      "required": ["query"]}})
    tools.append({"fn": _LAZY_RUN, "server": "javis", "name": _LAZY_RUN,
                  "description": (f"GỌI một tool MCP đã tìm được qua {_LAZY_SEARCH}. name = tên tool (đúng "
                                  "y hệt kết quả tìm), args = tham số (object). Quyền/audit/giới hạn tần "
                                  "suất áp y như gọi trực tiếp."),
                  "schema": {"type": "object", "properties": {
                      "name": {"type": "string", "description": f"Tên tool lấy từ {_LAZY_SEARCH}"},
                      "args": {"type": "object", "description": "Tham số tool (object)"}},
                      "required": ["name"]}})
    route[_LAZY_SEARCH] = {"call": _search}
    route[_LAZY_RUN] = {"call": _run}
    return tools, route


def _apply_lazy(tools_spec, route, include_ambient=False, hidden=None, force=False):
    """Nếu bật lazy: giấu tool sau meta-tool search/run; không bật → trả nguyên.
    Pool = MỌI tool trừ nhóm hạt nhân CORE_TOOL_FNS - gồm cả builtin và plugin, không riêng
    tool MCP. Xem chú thích ở CORE_TOOL_FNS về lý do không suy pool ra từ 'conn'.
    include_ambient (đường engine Claude): kèm connector tài khoản Claude vào menu/search để
    model biết còn nhóm tool native mcp__* ngoài pool của hub."""
    pool = [t for t in tools_spec if t["fn"] not in CORE_TOOL_FNS]
    if not force and not _lazy_on(len(pool), _pool_chars(pool)):
        return tools_spec, route
    pool_fns = {t["fn"] for t in pool}
    visible_tools = [t for t in tools_spec if t["fn"] not in pool_fns]
    visible_route = {fn: ent for fn, ent in route.items() if fn not in pool_fns}
    _, _, top_k = _lazy_config()
    ambient = _ambient_servers() if include_ambient else []
    return _lazy_tools_and_route(visible_tools, visible_route, pool, route, top_k, ambient, hidden)


# ============================================================
# Discover (cache) - gộp MCP connections + builtin
# ============================================================
def _store_mtime():
    try:
        return mcp_store.STORE.stat().st_mtime
    except OSError:
        return 0


async def discover_all(mode="full", vault_root=None, include_plugins=True, include_ambient=False,
                       force_refresh=False, force_lazy=False):
    """(tools_spec, route) đầy đủ cho 1 mode. route entries ĐÃ bọc quyền + audit.
    include_plugins=False: bỏ nhóm tool plugin - dùng khi engine SDK đã đấu plugin
    IN-PROCESS (header X-Javis-No-Plugins) để model không thấy tool trùng chức năng.
    include_ambient=True (đường engine Claude, header X-Javis-Engine=claude): javis_connections +
    lazy search kèm connector tài khoản Claude (Drive/Gmail...) - chúng là tool native mcp__* của
    engine, KHÔNG qua hub, hub chỉ mách chỗ cho model. Engine API (in-process) để False (không có
    tool native để mà chỉ tới)."""
    mode = (mode or "full").strip().lower()
    key = (mode, str(vault_root or ""), bool(include_plugins), bool(include_ambient), bool(force_lazy))
    ent = _cache.get(key)
    mt = _store_mtime()
    if (not force_refresh and ent and time.time() - ent["ts"] < _CACHE_TTL
            and ent["mtime"] == mt):
        return ent["tools"], ent["route"]

    conns = mcp_store.resolved(enabled_only=True)
    raw_tools, raw_route = await mcp_client.discover_resolved(conns)

    tools_spec, route = [], {}
    hidden = {}          # conn_id -> {"perm", "ns", "tools"} - tool CÓ THẬT nhưng bị quyền lọc
    for t in raw_tools:
        raw = raw_route.get(t["fn"])
        if not raw:
            continue
        conn = raw["conn"]
        connector = mcp_catalog.get(conn.get("connector_id"))
        eff = mcp_catalog.effective_perm(conn.get("perm"), mode)
        # Tool ĐA HÀNH ĐỘNG (schema có tham số arg_rules.param, vd action của Pancake) → coi là
        # "read" lúc LIST để còn liệt kê được; chặn thật lúc call (đã có args). Tool thường →
        # phân loại tĩnh theo tool_meta/heuristic.
        rules = (connector or {}).get("arg_rules") or {}
        props = ((t.get("schema") or {}).get("properties") or {})
        multiplexed = bool(rules.get("param") and rules["param"] in props)
        cls = "read" if multiplexed else mcp_catalog.classify(connector, raw["tool"], None)
        # Lọc lúc LIST: readonly ẩn tool ghi/nguy hiểm tĩnh; safe ẩn tool nguy hiểm tĩnh.
        if (eff == "readonly" and cls in ("write", "danger")) or (eff == "safe" and cls == "danger"):
            h = hidden.setdefault(conn["id"], {"perm": eff, "ns": conn.get("namespace"), "tools": []})
            h["tools"].append(raw["tool"])
            continue
        tools_spec.append(t)
        route[t["fn"]] = {
            "call": _guard(raw, t["fn"], mode), "conn": conn, "tool": raw["tool"],
            # Metadata dùng bởi Registry/Resolver shadow; không tham gia dispatch.
            "source_type": "mcp", "source_id": conn.get("id") or conn.get("namespace"),
            "effect": cls,
            "required_mode": "readonly" if cls == "read" else ("safe" if cls == "write" else "full"),
            "multiplexed": multiplexed,
            "health": "healthy",
        }

    b_tools, b_route = _builtin_tools(mode, vault_root, include_ambient, hidden)
    tools_spec += b_tools
    route.update(b_route)

    # PLUGIN: tool do plugin đăng ký (bundled + vault) → mọi engine, tôn trọng min_mode.
    # Trùng tên tool đã có (MCP/builtin) → BỎ QUA (không cho plugin shadow tool lõi).
    try:
        import plugins_host
        if include_plugins:
            p_tools, p_route = plugins_host.plugin_tools(mode, vault_root)
            for t in p_tools:
                fn = t["fn"]
                if fn in route:
                    print(f"[hub] plugin tool '{fn}' trùng tool đã có - bỏ qua", file=sys.stderr)
                    continue
                tools_spec.append(t)
                route[fn] = p_route[fn]
        # HOOK pre/post_tool_call: bọc MỌI tool call (chỉ khi có plugin đăng ký hook → 0 overhead khi không).
        if plugins_host.has_tool_hooks(vault_root):
            for fn in list(route):
                base = route[fn].get("call")
                if base:
                    route[fn]["call"] = plugins_host.wrap_with_hooks(fn, base, mode, vault_root)
    except Exception as e:
        print(f"[hub] plugin host lỗi: {type(e).__name__}: {e}", file=sys.stderr)

    # Snapshot ĐẦY ĐỦ trước lazy cho Capability Registry Phase 2. Registry chỉ dùng metadata;
    # model vẫn nhận đúng danh sách sau lazy như trước.
    inventory_tools = list(tools_spec)
    inventory_route = dict(route)

    # LAZY: đông tool MCP thì giấu pool sau meta-tool search/run (giữ full route để dispatch).
    # Đặt SAU builtin+plugin để chúng luôn hiện; cache lưu bản ĐÃ biến đổi (route lazy vẫn dispatch
    # được vì _run đóng gói route đầy đủ). Đổi setting → làm mới theo TTL cache (60s) hoặc invalidate.
    tools_spec, route = _apply_lazy(tools_spec, route, include_ambient, hidden, force=force_lazy)
    _cache[key] = {"tools": tools_spec, "route": route, "ts": time.time(), "mtime": mt,
                   "inventory_tools": inventory_tools, "inventory_route": inventory_route}
    return tools_spec, route


def registry_inventory(mode="full", vault_root=None, include_plugins=True, include_ambient=False,
                       force_lazy=False):
    """Trả snapshot pre-lazy đã cache; không discover I/O và không lộ ra model."""
    key = ((mode or "full").strip().lower(), str(vault_root or ""),
           bool(include_plugins), bool(include_ambient), bool(force_lazy))
    ent = _cache.get(key) or {}
    return list(ent.get("inventory_tools") or ent.get("tools") or []), dict(
        ent.get("inventory_route") or ent.get("route") or {}
    )


def invalidate_cache():
    """Gọi sau khi thêm/sửa/xoá connection - làm mới tool list + đóng session cũ."""
    _cache.clear()
    _ambient_cache["ts"] = 0.0   # ép nạp lại danh sách connector tài khoản ở lần discover kế
    try:
        for c in mcp_store.list_connections():
            mcp_client.pool.invalidate(c["id"])
    except Exception:
        pass


# ============================================================
# HTTP endpoint /hub/mcp (main.py mount) - Streamable HTTP tối giản
# ============================================================
def _rpc_error(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


async def _handle_one(msg, mode, include_plugins=True, include_ambient=False, vault_root=None):
    mid = msg.get("id")
    method = msg.get("method") or ""
    params = msg.get("params") or {}
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": params.get("protocolVersion") or mcp_client.PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "javis-hub", "version": "1.0"},
        }}
    if method.startswith("notifications/"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        tools, _ = await discover_all(mode, vault_root=vault_root, include_plugins=include_plugins,
                                      include_ambient=include_ambient)   # Claude/Codex có tool file native → không builtin file
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": t["fn"], "description": (t.get("description") or t["fn"]),
             "inputSchema": t.get("schema") or {"type": "object", "properties": {}}}
            for t in tools]}}
    if method == "tools/call":
        _, route = await discover_all(mode, vault_root=vault_root, include_plugins=include_plugins,
                                      include_ambient=include_ambient)
        name = params.get("name") or ""
        result = await mcp_client.call_route(route, name, params.get("arguments") or {})
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": str(result)}],
            "isError": str(result).startswith("ERROR:"),
        }}
    return _rpc_error(mid, -32601, f"method không hỗ trợ: {method}")


async def handle_http(request):
    """POST /hub/mcp - auth bằng Bearer hub_token (KHÔNG dùng session dashboard)."""
    auth = request.headers.get("authorization") or ""
    # compare_digest: /hub/mcp là endpoint public (không cookie), token là lớp auth duy nhất
    # → so sánh hằng-thời-gian chống dò theo timing.
    if not _secrets.compare_digest(auth, f"Bearer {hub_token()}"):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    mode = (request.headers.get("x-javis-mode") or "full").strip().lower()
    # Engine SDK đấu plugin in-process gửi header này để hub bỏ nhóm plugin (tránh tool trùng)
    include_plugins = (request.headers.get("x-javis-no-plugins") or "").strip() != "1"
    # Chỉ engine Claude (config claude_config_path gắn X-Javis-Engine=claude) mới có tool native
    # mcp__* của connector tài khoản Claude → chỉ nó cần gợi ý ambient. Codex/engine API không có.
    include_ambient = (request.headers.get("x-javis-engine") or "").strip().lower() == "claude"
    # Codex chạy MCP qua HTTP hub (khác Claude SDK đấu plugin in-process), nên nếu không mang
    # brain hiện tại thì plugin javis_schedule có tool nhưng không biết phải đọc kho cron nào.
    # Chỉ nhận đường dẫn thư mục có thật; Bearer hub_token vẫn là lớp auth bắt buộc phía trên.
    vault_root = None
    raw_vault = (request.headers.get("x-javis-vault") or "").strip()
    if raw_vault:
        try:
            candidate = Path(raw_vault).expanduser().resolve()
            if candidate.is_dir():
                vault_root = str(candidate)
        except Exception:
            pass
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(_rpc_error(None, -32700, "parse error"), status_code=400)
    try:
        if isinstance(body, list):
            out = [r for r in [await _handle_one(m, mode, include_plugins, include_ambient, vault_root)
                               for m in body] if r is not None]
            if not out:
                return Response(status_code=202)
            return JSONResponse(out)
        res = await _handle_one(body, mode, include_plugins, include_ambient, vault_root)
        if res is None:
            return Response(status_code=202)
        return JSONResponse(res)
    except Exception as e:
        print(f"[hub] {type(e).__name__}: {e}", file=sys.stderr)
        return JSONResponse(_rpc_error(body.get("id") if isinstance(body, dict) else None,
                                       -32603, f"lỗi nội bộ: {type(e).__name__}"))


# ============================================================
# Config cho Claude Code / Codex - MỘT entry trỏ về hub
# ============================================================
def _has_connections():
    try:
        return any(c.get("enabled") for c in mcp_store.list_connections())
    except Exception:
        return False


def claude_config_path(mode="full"):
    """Ghi file --mcp-config 1 entry 'javis'. 0 connection bật → None (giữ hành vi cũ:
    không config → Claude dùng MCP sẵn của máy)."""
    mode = (mode or "full").strip().lower()
    if not _has_connections():
        return None
    p = STATE_DIR / f".mcp_hub_{mode}.json"
    # X-Javis-Engine=claude: báo hub đây là engine Claude (có tool native mcp__* của connector
    # tài khoản Claude) → javis_connections/lazy search kèm gợi ý ambient. Codex/engine API không gắn.
    p.write_text(json.dumps({"mcpServers": {"javis": {
        "type": "http", "url": hub_url(),
        "headers": {"Authorization": f"Bearer {hub_token()}", "X-Javis-Mode": mode,
                    "X-Javis-Engine": "claude"},
    }}}, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(p, 0o600)   # file chứa hub token - siết như .hub_token
    except Exception:
        pass
    return str(p)


def _toml_str(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def codex_profile(mode="full"):
    """Ghi ~/.codex/javis.config.toml 1 entry hub → `codex exec -p javis` thấy MỌI MCP của Javis."""
    path = Path.home() / ".codex" / "javis.config.toml"
    try:
        # Hub còn cung cấp plugin nội bộ (javis_schedule, datetime-vn...) ngay cả khi user chưa
        # đấu connector ngoài. Không được xoá profile chỉ vì mcp_store đang rỗng.
        lines = ["[mcp_servers.javis]",
                 f"url = {_toml_str(hub_url())}",
                 "startup_timeout_sec = 20",
                 "[mcp_servers.javis.http_headers]",
                 f'{_toml_str("Authorization")} = {_toml_str("Bearer " + hub_token())}',
                 f'{_toml_str("X-Javis-Mode")} = {_toml_str(mode)}', ""]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
        try:
            os.chmod(path, 0o600)   # chứa hub token
        except Exception:
            pass
        return "javis"
    except Exception as e:
        print(f"[hub codex profile] {e}", file=sys.stderr)
        return None


def codex_vault_override(vault_root):
    """Override `-c` theo từng tiến trình Codex để hub nhận đúng brain mà không ghi đè profile chung.

    Profile javis là file dùng chung cho mọi cuộc chat. Nhét X-Javis-Vault thẳng vào file đó sẽ
    race khi hai brain chạy đồng thời; override argv giữ context tách biệt theo đúng phiên.
    """
    if not vault_root:
        return None
    try:
        vault = str(Path(vault_root).expanduser().resolve())
    except Exception:
        vault = str(vault_root)
    return f'mcp_servers.javis.http_headers."X-Javis-Vault"={_toml_str(vault)}'


# ============================================================
# Validate connection (thêm tài khoản / nút Test)
# ============================================================
def _walk_path(obj, path):
    cur = obj
    for part in path.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur if isinstance(cur, (str, int, float)) else None


def _extract_label(text, paths):
    """Bóc label (tên shop/tài khoản) từ text kết quả validate tool."""
    obj = None
    for cand in (text, text[text.find("{"): text.rfind("}") + 1] if "{" in text else "",
                 text[text.find("["): text.rfind("]") + 1] if "[" in text else ""):
        if not cand:
            continue
        try:
            obj = json.loads(cand)
            break
        except (json.JSONDecodeError, ValueError):
            continue
    if obj is not None:
        # Parse được JSON mà không path nào khớp → trả rỗng (UI dùng tên connector),
        # KHÔNG rơi xuống regex - tránh vớ nhầm "name" đầu tiên bất kỳ (vd tên tag Botcake).
        for p in (paths or []):
            v = _walk_path(obj, p)
            if v:
                return str(v)[:80]
        return ""
    m = re.search(r'"name"\s*:\s*"([^"]{2,80})"', text or "")
    return m.group(1) if m else ""


# Google KHÔNG hỏi lại quyền đã cấp: prompt=consent chỉ hiện lại màn đồng ý, còn màn TICK
# TỪNG QUYỀN thì chỉ bật cho quyền CHƯA từng cấp (và chỉ khi app xin từ 2 quyền trở lên).
# Nên "đăng nhập lại mà không thấy ô tick nào" là đúng cơ chế, không phải hỏng - đường duy
# nhất để tick lại từ đầu là gỡ ứng dụng ở trang quyền của tài khoản Google.
REVOKE_HINT = (" Đăng nhập lại mà Google không hiện ô tick quyền nào là bình thường: quyền đã"
               " cấp thì nó cho qua thẳng. Muốn tick lại từ đầu thì gỡ Javis tại"
               " https://myaccount.google.com/permissions rồi Kết nối lại.")


def _missing_scope_note(conn_id):
    """Câu nói thẳng THIẾU ĐÚNG QUYỀN NÀO cho 1 connection oauth, hoặc "" nếu không biết."""
    if not conn_id:
        return ""
    try:
        import oauth_mcp
        rep = oauth_mcp.scope_report(conn_id)
        if rep.get("missing"):
            return " Token hiện tại thiếu: " + ", ".join(oauth_mcp.short_scopes(rep["missing"])) + "."
    except Exception as e:
        print(f"[hub scope] {e}", file=sys.stderr)
    return ""


def chan_doan_loi(err, conn_id=""):
    """Nhận diện các HỌ LỖI quen mặt của Google/OAuth → lời khuyên đúng bệnh.
    Trả "" khi KHÔNG nhận ra - để chỗ gọi tự quyết định nói gì, không bịa chẩn đoán.

    Vì sao tách riêng khỏi _friendly_tool_error: bộ dịch này trước đây chỉ cắm vào nút Test,
    trong khi 99% lần người dùng gặp lỗi là lúc GỌI TOOL THẬT - và ở đó model chỉ nhận được
    nguyên văn tiếng Anh của Google rồi tự suy diễn. Vụ 2026-07-30: Google trả "The caller does
    not have permission", Javis đọc xong kết luận nhầm là "hub chặn quyền" và đi sửa tầng
    permission, trong khi hub không hề chặn (mức full thì allowed() cho qua ngay, và thông báo
    chặn của Javis là tiếng Việt chứ không phải tiếng Anh).

    conn_id (tuỳ chọn): có thì nhánh thiếu scope nói luôn THIẾU CÁI GÌ, không bắt người dùng đoán."""
    e = (err or "").strip()
    low = e.lower()
    if "has not been used in project" in low or "service_disabled" in low:
        m = re.search(r"https://console\.developers\.google\.com/apis/[^\s\"'\\]+", e)
        link = ("\nBật tại: " + m.group(0)) if m else ""
        extra = ""
        m2 = re.search(r"\b([a-z0-9-]*mcp)\.googleapis\.com", low)
        if m2:
            extra = ("\nLưu ý: server MCP của Google là API riêng (" + m2.group(0)
                     + "), phải bật THÊM bên cạnh API thường, và tài khoản Google phải ghi danh"
                       " Workspace Developer Preview Program (miễn phí):"
                       " https://developers.google.com/workspace/preview")
        return "API này chưa được bật trong project Google Cloud của bạn." + link + extra
    if "insufficient authentication scopes" in low or "access_token_scope_insufficient" in low:
        # Đây KHÔNG phải lỗi hỏng key: token đúng nhưng thiếu đúng một phạm vi quyền. Xoá đi cài
        # lại không chữa được nếu bản Javis đang chạy xin thiếu scope (vụ suggest_time cần
        # calendar.events.freebusy) - nên phải nói rõ là đăng nhập LẠI sau khi cập nhật.
        return ("Tài khoản đã kết nối nhưng token chưa đủ phạm vi quyền cho tool này."
                + _missing_scope_note(conn_id) +
                " Bấm Đăng nhập lại và tick chọn đầy đủ các quyền. Nếu vừa cập nhật Javis thì"
                " BẮT BUỘC đăng nhập lại: token cũ chỉ mang những quyền xin ở bản trước, xoá"
                " kết nối rồi tạo lại cũng không thêm được quyền mới." + REVOKE_HINT)
    if ("missing required authentication credential" in low or "unauthenticated" in low
            or "invalid_grant" in low or "invalid_token" in low):
        return "Phiên đăng nhập hỏng hoặc hết hạn. Bấm Đăng nhập lại để lấy token mới."
    # 403 PERMISSION_DENIED KHÔNG kèm chữ scope. Đặt SAU nhánh scope vì lỗi thiếu scope của
    # Google cũng mang status PERMISSION_DENIED. Với server MCP của Google, họ lỗi này gần như
    # luôn là chưa ghi danh Developer Preview cho ĐÚNG tài khoản đang đăng nhập, hoặc project
    # chưa bật API MCP riêng. Ghi danh tính theo TỪNG TÀI KHOẢN nên đổi sang tài khoản khác là
    # phải ghi danh lại - đúng bẫy của người dùng khi chuyển từ gmail cá nhân sang mail tên miền.
    if "caller does not have permission" in low or "permission_denied" in low:
        return ("Google từ chối chính TÀI KHOẢN đang đăng nhập (403 PERMISSION_DENIED). Đây KHÔNG"
                " phải Javis chặn: mức quyền của kết nối chặn thì Javis báo bằng tiếng Việt kèm chữ"
                " 'bị chặn'. Với server MCP của Google, lỗi này thường do 1 trong 2: tài khoản đó"
                " chưa ghi danh Google Workspace Developer Preview Program, hoặc project chưa bật"
                " API MCP riêng. Ghi danh tính theo TỪNG tài khoản Google, nên vừa đổi sang tài"
                " khoản khác là phải ghi danh lại cho tài khoản mới. Nếu là email theo tên miền"
                " riêng (Workspace) thì quản trị viên của miền phải cho phép nữa."
                " Ghi danh: https://developers.google.com/workspace/preview")
    return ""


def _friendly_tool_error(err, conn_id=""):
    """Bản cho nút Test: nhận ra thì nói đúng bệnh, không nhận ra thì giữ nguyên câu cũ kèm
    nguyên văn lỗi (hành vi lịch sử, có canary trong test canh)."""
    return chan_doan_loi(err, conn_id) or ("Key chưa đúng hoặc chưa đủ quyền: " + (err or "").strip()[:200])


async def validate_connection(conn_id):
    """Gọi thử connection: đếm tool + (nếu catalog khai validate) lấy label tên shop.
    Trả {ok, label, tools, error}."""
    conn = next((c for c in mcp_store.resolved(enabled_only=False) if c["id"] == conn_id), None)
    if not conn:
        return {"ok": False, "label": "", "tools": 0, "error": "Không tìm thấy kết nối"}
    # Connector ẢO (không URL, không command, không phải internal): tool do PLUGIN phục vụ (vd
    # Meta/Facebook gọi Graph API/cookie), không có MCP server để dial. Coi là hợp lệ; đếm tool
    # theo tool_meta để hiển thị.
    #
    # Connector `internal` (Substack, Botcake) KHÔNG đi lối này dù cũng không có url/command:
    # nó có module Python thật để gọi, nên phải DIAL THẬT. Trả "ổn" theo tool_meta cho nó là
    # nút Test nói dối - đúng cái đã xảy ra: trang Kết nối xanh, mà hộp công cụ trống rỗng.
    if not mcp_client.co_server_de_dial(conn):
        tm = (conn.get("connector") or {}).get("tool_meta") or {}
        n = len((tm.get("read") or []) + (tm.get("write") or []) + (tm.get("danger") or []))
        return {"ok": True, "label": "", "tools": n, "error": ""}
    # Soát scope TRƯỚC khi dial: tool validate chỉ chạm một góc nhỏ của dịch vụ (Lịch dùng
    # list_calendars, chỉ cần scope danh sách lịch) nên token thiếu quyền vẫn cho Test màu xanh,
    # rồi user mới vỡ ra lúc nhờ tìm giờ trống. Kiểm tại đây thì báo đúng bệnh ngay từ trang Kết nối.
    if conn.get("auth") == "oauth":
        try:
            import oauth_mcp
            rep = oauth_mcp.scope_report(conn_id)
            if rep.get("missing"):
                return {"ok": False, "label": "", "tools": 0,
                        "error": "Đăng nhập rồi nhưng token thiếu quyền: "
                                 + ", ".join(oauth_mcp.short_scopes(rep["missing"]))
                                 + ". Bấm Đăng nhập lại và tick đủ mọi ô quyền." + REVOKE_HINT}
        except Exception as e:
            print(f"[hub scope] {e}", file=sys.stderr)
    spec = mcp_client._conn_spec(conn)
    try:
        spec["headers"].update(await mcp_client._oauth_headers(conn))
        tools = await mcp_client.pool.list_tools(spec)
    except Exception as e:
        # Kèm nội dung lỗi thật: chỉ tên loại (vd "ValueError") thì không lần ra manh mối.
        chi_tiet = str(e)[:160]
        return {"ok": False, "label": "", "tools": 0,
                "error": "Không kết nối được (" + type(e).__name__
                         + (": " + chi_tiet if chi_tiet else "")
                         + "). Kiểm tra lại key/URL hoặc thử lại."}
    label = ""
    val = (conn.get("connector") or {}).get("validate")
    if val and val.get("tool"):
        res = await mcp_client.pool.call_tool(spec, val["tool"], val.get("args") or {})
        if str(res).startswith("ERROR:"):
            return {"ok": False, "label": "", "tools": len(tools),
                    "error": _friendly_tool_error(str(res)[7:], conn_id)}
        label = _extract_label(str(res), val.get("label_paths"))
    return {"ok": True, "label": label, "tools": len(tools), "error": ""}
