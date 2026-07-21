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
        return result

    return _call


# ============================================================
# Builtin tools (engine API): file trong vault + use_skill + meta connections
# ============================================================
def _safe_path(vault_root, p):
    root = Path(vault_root).resolve()
    target = (root / str(p or "")).resolve()
    if root != target and root not in target.parents:
        raise ValueError(f"đường dẫn '{p}' nằm ngoài vault")
    return target


def _connections_json():
    out = []
    for c in mcp_store.list_connections():
        con = mcp_catalog.get(c.get("connector_id")) or {}
        out.append({"connector": con.get("name") or c.get("connector_id"), "label": c.get("label"),
                    "namespace": c.get("slug"), "perm": c.get("perm"), "enabled": c.get("enabled"),
                    "is_default": c.get("is_default"), "transport": c.get("transport")})
    return json.dumps(out, ensure_ascii=False, indent=1)


def _skills_dir(vault_root):
    """Canonical <vault>/skills (qua skill_router - dùng chung logic với main.py)."""
    return skill_router.skills_base(vault_root, canonical=True)


def _list_skills(vault_root):
    """Slug các skill đang BẬT (list[str], giữ nguyên kiểu để chỗ join không vỡ)."""
    return skill_router.enabled_slugs(vault_root)


def _builtin_tools(mode, vault_root):
    """(tools_spec, route) các tool nội bộ cho engine API. Claude/Codex có tool file native
    nên hub HTTP không trả nhóm này (chỉ meta javis_connections)."""
    tools, route = [], {}

    def add(name, description, props, required, call):
        tools.append({"fn": name, "server": "javis", "name": name, "description": description,
                      "schema": {"type": "object", "properties": props, "required": required}})
        route[name] = {"call": call}

    add("javis_connections", "Liệt kê các nguồn dữ liệu (connector/tài khoản MCP) đang đấu vào Javis, "
        "kèm mức quyền. Dùng khi cần biết đang có nguồn nào / tài khoản nào là mặc định.",
        {}, [], lambda args: _async_const(_connections_json()))

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
            return "ERROR: chế độ hiện tại (suggest/chỉ đọc) không được ghi file. Chỉ đề xuất thôi."
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
        {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"], _write)
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


def _lazy_on(pool_n):
    """Có bật chế độ lazy cho lần discover này không (theo config + số tool pool MCP)."""
    mode, thr, _ = _lazy_config()
    s = str(mode).strip().lower()
    if mode is True or s in ("true", "on", "1", "always"):
        return True
    if mode is False or s in ("false", "off", "0", "never"):
        return False
    return pool_n > thr   # 'auto': chỉ bật khi thật sự đông tool


def _connector_menu(pool):
    """Thực đơn MỎNG các nguồn đang đấu (namespace + tên + số tool + mô tả 1 dòng) để model
    biết CÓ GÌ mà với tới. Đây là phần LUÔN bật (rẻ, vài trăm token) thay cho cả rừng schema."""
    seen = {}
    for t in pool:
        ns = t.get("namespace") or t.get("server") or "?"
        if ns not in seen:
            con = mcp_catalog.get(t.get("connector_id")) or {}
            seen[ns] = {"label": t.get("label") or con.get("name") or ns,
                        "desc": (con.get("description") or con.get("name") or "").strip(), "n": 0}
        seen[ns]["n"] += 1
    parts = []
    for ns, v in seen.items():
        d = (": " + v["desc"][:70]) if v["desc"] else ""
        parts.append(f"{ns} ({v['label']}, {v['n']} tool){d}")
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


def _lazy_tools_and_route(visible_tools, visible_route, pool, full_route, top_k):
    """Dựng (tools_spec, route) chế độ lazy: builtins/plugin hiện trực tiếp + 2 meta-tool.
    _search đóng gói `pool` (full tools_spec để xếp hạng); _run đóng gói `full_route` (dispatch
    qua call_route → giữ nguyên _guard quyền/audit/rate-limit)."""
    menu = _connector_menu(pool)

    async def _search(args):
        hits = _rank_tools(pool, (args or {}).get("query") or "", top_k)
        if not hits:
            return ("Không thấy tool khớp. Nguồn đang đấu: " + (menu or "(chưa có nguồn nào)")
                    + f". Nêu rõ nguồn hoặc việc cần làm rồi gọi lại {_LAZY_SEARCH}.")
        out = [{"name": t.get("fn"), "description": (t.get("description") or "")[:400],
                "schema": t.get("schema") or {"type": "object", "properties": {}}} for t in hits]
        return json.dumps({"tools": out,
                           "goi_the_nao": f"Gọi tool bằng {_LAZY_RUN}(name=<name>, args={{...}})."},
                          ensure_ascii=False)

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
                                  f"tham số tool để gọi tiếp qua {_LAZY_RUN}."),
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


def _apply_lazy(tools_spec, route):
    """Nếu bật lazy: giấu tool MCP (pool) sau meta-tool search/run; không bật → trả nguyên.
    Pool = tool có route entry mang 'conn' (đến từ connection MCP). Builtins + plugin (entry
    'call' không 'conn') LUÔN hiện trực tiếp - chúng ít và luôn hữu dụng."""
    pool = [t for t in tools_spec if (route.get(t["fn"]) or {}).get("conn")]
    if not _lazy_on(len(pool)):
        return tools_spec, route
    pool_fns = {t["fn"] for t in pool}
    visible_tools = [t for t in tools_spec if t["fn"] not in pool_fns]
    visible_route = {fn: ent for fn, ent in route.items() if fn not in pool_fns}
    _, _, top_k = _lazy_config()
    return _lazy_tools_and_route(visible_tools, visible_route, pool, route, top_k)


# ============================================================
# Discover (cache) - gộp MCP connections + builtin
# ============================================================
def _store_mtime():
    try:
        return mcp_store.STORE.stat().st_mtime
    except OSError:
        return 0


async def discover_all(mode="full", vault_root=None, include_plugins=True):
    """(tools_spec, route) đầy đủ cho 1 mode. route entries ĐÃ bọc quyền + audit.
    include_plugins=False: bỏ nhóm tool plugin - dùng khi engine SDK đã đấu plugin
    IN-PROCESS (header X-Javis-No-Plugins) để model không thấy tool trùng chức năng."""
    mode = (mode or "full").strip().lower()
    key = (mode, str(vault_root or ""), bool(include_plugins))
    ent = _cache.get(key)
    mt = _store_mtime()
    if ent and time.time() - ent["ts"] < _CACHE_TTL and ent["mtime"] == mt:
        return ent["tools"], ent["route"]

    conns = mcp_store.resolved(enabled_only=True)
    raw_tools, raw_route = await mcp_client.discover_resolved(conns)

    tools_spec, route = [], {}
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
        if eff == "readonly" and cls in ("write", "danger"):
            continue
        if eff == "safe" and cls == "danger":
            continue
        tools_spec.append(t)
        route[t["fn"]] = {"call": _guard(raw, t["fn"], mode), "conn": conn, "tool": raw["tool"]}

    b_tools, b_route = _builtin_tools(mode, vault_root)
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

    # LAZY: đông tool MCP thì giấu pool sau meta-tool search/run (giữ full route để dispatch).
    # Đặt SAU builtin+plugin để chúng luôn hiện; cache lưu bản ĐÃ biến đổi (route lazy vẫn dispatch
    # được vì _run đóng gói route đầy đủ). Đổi setting → làm mới theo TTL cache (60s) hoặc invalidate.
    tools_spec, route = _apply_lazy(tools_spec, route)
    _cache[key] = {"tools": tools_spec, "route": route, "ts": time.time(), "mtime": mt}
    return tools_spec, route


def invalidate_cache():
    """Gọi sau khi thêm/sửa/xoá connection - làm mới tool list + đóng session cũ."""
    _cache.clear()
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


async def _handle_one(msg, mode, include_plugins=True):
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
        tools, _ = await discover_all(mode, include_plugins=include_plugins)   # Claude/Codex có tool file native → không builtin file
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": t["fn"], "description": (t.get("description") or t["fn"]),
             "inputSchema": t.get("schema") or {"type": "object", "properties": {}}}
            for t in tools]}}
    if method == "tools/call":
        _, route = await discover_all(mode, include_plugins=include_plugins)
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
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(_rpc_error(None, -32700, "parse error"), status_code=400)
    try:
        if isinstance(body, list):
            out = [r for r in [await _handle_one(m, mode, include_plugins) for m in body] if r is not None]
            if not out:
                return Response(status_code=202)
            return JSONResponse(out)
        res = await _handle_one(body, mode, include_plugins)
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
    p.write_text(json.dumps({"mcpServers": {"javis": {
        "type": "http", "url": hub_url(),
        "headers": {"Authorization": f"Bearer {hub_token()}", "X-Javis-Mode": mode},
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
        if not _has_connections():
            if path.exists():
                path.unlink()
            return None
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


async def validate_connection(conn_id):
    """Gọi thử connection: đếm tool + (nếu catalog khai validate) lấy label tên shop.
    Trả {ok, label, tools, error}."""
    conn = next((c for c in mcp_store.resolved(enabled_only=False) if c["id"] == conn_id), None)
    if not conn:
        return {"ok": False, "label": "", "tools": 0, "error": "Không tìm thấy kết nối"}
    # Connector ẢO (không URL, không command): tool do PLUGIN phục vụ (vd Meta/Facebook gọi
    # Graph API/cookie), không có MCP server để dial. Coi là hợp lệ; đếm tool theo tool_meta để hiển thị.
    if not (conn.get("url") or "").strip() and not (conn.get("command") or "").strip():
        tm = (conn.get("connector") or {}).get("tool_meta") or {}
        n = len((tm.get("read") or []) + (tm.get("write") or []) + (tm.get("danger") or []))
        return {"ok": True, "label": "", "tools": n, "error": ""}
    spec = mcp_client._conn_spec(conn)
    try:
        spec["headers"].update(await mcp_client._oauth_headers(conn))
        tools = await mcp_client.pool.list_tools(spec)
    except Exception as e:
        return {"ok": False, "label": "", "tools": 0,
                "error": f"Không kết nối được ({type(e).__name__}). Kiểm tra lại key/URL hoặc thử lại."}
    label = ""
    val = (conn.get("connector") or {}).get("validate")
    if val and val.get("tool"):
        res = await mcp_client.pool.call_tool(spec, val["tool"], val.get("args") or {})
        if str(res).startswith("ERROR:"):
            return {"ok": False, "label": "", "tools": len(tools),
                    "error": "Key chưa đúng hoặc chưa đủ quyền: " + str(res)[7:200]}
        label = _extract_label(str(res), val.get("label_paths"))
    return {"ok": True, "label": label, "tools": len(tools), "error": ""}
