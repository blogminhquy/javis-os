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
import hashlib
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
from urllib.parse import quote, unquote

from fastapi.responses import JSONResponse, Response

import chatbot_doc_tools
import coding_files
import config
import doc_text
import hub_trace
import localefmt
import mcp_catalog
import mcp_client
import mcp_store
import once_ledger
import skill_router
import skill_usage
import team_gate
import turn_context
from config import STATE_DIR

_TOKEN_PATH = STATE_DIR / ".hub_token"
_AUDIT_PATH = STATE_DIR / "mcp_audit.jsonl"
_CACHE_TTL = 60
# Vòng dò có nguồn bị BỎ QUA (quá hạn/lỗi) thì danh sách tool là bản THIẾU. Cache nó đủ 60
# giây là đóng băng cái thiếu đó: mọi lượt chat mở trong cửa sổ ấy nhận một hộp công cụ vắng
# nguồn, mà CLI engine chỉ đọc danh sách MỘT LẦN lúc mở phiên nên cả phiên chat đó coi như
# mất nguồn. Bản thiếu vẫn phải cache (không thì một nguồn chết là mỗi lượt lại đi dò lại từ
# đầu), chỉ là cache NGẮN để lượt sau còn cơ hội thấy nguồn đã hồi.
_CACHE_TTL_THIEU = 10
# 0.382.0: a COMPLETE list past its 60 s is still served (up to this age) while a refresh runs in the background, so a
# chat turn that opens an engine after a pause does not wait for every source to be dialled again. A partial list
# keeps the short synchronous rule above; any change to the connection store (mtime) or invalidate_cache() still
# drops the entry at once.
_CACHE_STALE_MAX = 900
_refreshing: set = set()
_cache = {}          # (mode, vault_root) -> {"tools", "route", "ts", "mtime"}
_cache_epoch = 0
_rate = {}           # conn_id -> deque[timestamps]
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic"}


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


# Tools that only the OWNER's own sessions may see (0.77.0). A dedicated bot at the "can write" / "full" level gets
# hub tools, and there the person steering the model is a stranger. These two read every customer chat the reply
# judge logged and retune the bot itself, so a customer must never reach them, not even through the lazy
# `javis_run_tool`. `discover_all(for_bot=True)` drops them before the lazy tier; bot paths pass that flag (API
# engines directly, Claude Code through the X-Javis-Bot header written by `claude_config_path(bot=True)`).
# `javis_team` (0.173.0) creates, edits and deletes team chats and writes assistant files: owner-only for the same reason.
# `javis_watch` (0.239.0) makes the server fetch an address on a schedule and message the owner: not a customer's call.
# `javis_login` (0.251.0) opens pages signed in as the owner (login vault): a customer must never browse as them.
OWNER_ONLY_TOOLS = frozenset({"javis_reply_policy", "javis_reply_policy_tune", "javis_team", "javis_memory",
                              "javis_watch", "javis_login",
                              # 0.403.0: changes which notices reach the owner. A customer must never mute the owner.
                              "javis_notify",
                              # 2026-10-25: writes code that runs in the server (installed OFF, still owner's call).
                              "javis_plugin",
                              # 0.259.0: tìm và đọc web. Bot nói chuyện với khách lạ không được biến
                              # máy chủ của chủ thành máy đi đọc web hộ bất kỳ ai nhắn tới.
                              "javis_web_search", "javis_web_fetch"})


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


def forget_rate(conn_id) -> None:
    """Quên bộ đếm tần suất của một connection đã bị xoá.

    Nhỏ nhưng có thật: `_rate` là dict theo conn_id và không ai pop nó bao giờ, nên id của
    mọi kết nối từng dùng tool sẽ nằm lại trong RAM tới lúc khởi động lại."""
    _rate.pop(conn_id, None)


def audit_scrub(conn_id, drop=False) -> int:
    """Dọn nhật ký cho một connection đã xoá. Trả về số dòng đã chạm.

    MẶC ĐỊNH CHỈ XOÁ NHÃN, không xoá dòng. Nhãn là thứ duy nhất trong bản ghi mang tên người
    hoặc tên cửa hàng; bỏ nó đi là hết dữ liệu cá nhân, mà vẫn còn lại dấu vết "kết nối này
    từng gọi tool kia lúc đó". Một nhật ký mà thao tác xoá tự quét sạch được thì không còn là
    nhật ký - nên `drop=True` phải do người dùng tự tick.

    Ghi lại bằng tmp + replace vì `_audit_append` mở file ở chế độ append KHÔNG khoá: sửa tại
    chỗ mà gặp đúng lúc một tool call đang ghi là mất dòng đó.
    """
    if not conn_id or not _AUDIT_PATH.exists():
        return 0
    try:
        lines = _AUDIT_PATH.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        print(f"[hub audit] doc de don: {e}", file=sys.stderr)
        return 0
    out, touched = [], 0
    for line in lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            out.append(line)      # dòng hỏng: giữ nguyên, không phải việc của hàm này
            continue
        if rec.get("conn_id") != conn_id:
            out.append(line)
            continue
        touched += 1
        if drop:
            continue
        rec["label"] = ""
        out.append(json.dumps(rec, ensure_ascii=False))
    if not touched:
        return 0
    try:
        tmp = _AUDIT_PATH.with_suffix(".jsonl.tmp")
        tmp.write_text((("\n".join(out)) + "\n") if out else "", encoding="utf-8")
        tmp.replace(_AUDIT_PATH)
    except OSError as e:
        print(f"[hub audit] ghi lai: {e}", file=sys.stderr)
        return 0
    return touched


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
        gated_ask = False
        if mode == team_gate.HUB_MODE and cls != "read":
            # 0.207.0: a gated Team step. Anything that is not a read is an outside action (review: a custom
            # connector's `send_email` is classed `write`, which `auto` would allow). The connection itself must allow
            # it at full; then only the owner's approval of this exact call for this step lets it through
            # (team_gate.py). No live gate means refused.
            full_ok, full_why = mcp_catalog.allowed(connector, conn.get("perm"), "full", tool, args)
            ok, why, gated_ask = (False, full_why, False) if not full_ok else (False, "", True)
        if (ok or gated_ask) and not _rate_ok(conn["id"], connector):
            ok, gated_ask = False, False
            why = (f"Kết nối '{conn.get('label')}' vượt giới hạn tần suất "
                   f"(chống spam/khoá tài khoản). Chờ 1 phút rồi thử lại.")
        if gated_ask:
            # Checked after the rate limit, so a refused call never burns the owner's approval.
            ok, why = await asyncio.to_thread(team_gate.hub_check, fn, args,
                                              f"{conn.get('label') or conn.get('connector_id') or ''}: {tool}")
            why = why[len("ERROR: "):] if why.startswith("ERROR: ") else why
        if not ok:
            _audit_append({"ts": datetime.now().isoformat(timespec="seconds"), "conn_id": conn["id"],
                           "connector": conn.get("connector_id"), "label": conn.get("label"),
                           "tool": tool, "mode": mode, "cls": cls, "ok": False, "ms": 0,
                           "err": why[:200], "args_keys": sorted((args or {}).keys()), **team_gate.audit_fields()})
            return "ERROR: " + why
        t0 = time.time()
        if cls == "read":
            result = await mcp_client.call_route({fn: {"spec": ent["spec"], "tool": tool}}, fn, args)
        else:
            # 0.238.0: a Kanban job that runs again must not send, post or order twice (once_ledger.py).
            # Outside a background job this calls straight through.
            result = await once_ledger.run(
                fn, args, lambda a: mcp_client.call_route({fn: {"spec": ent["spec"], "tool": tool}}, fn, a))
        _audit_append({"ts": datetime.now().isoformat(timespec="seconds"), "conn_id": conn["id"],
                       "connector": conn.get("connector_id"), "label": conn.get("label"),
                       "tool": tool, "mode": mode, "cls": cls,
                       "ok": not str(result).startswith("ERROR:"), "ms": int((time.time() - t0) * 1000),
                       "err": str(result)[:200] if str(result).startswith("ERROR:") else "",
                       "args_keys": sorted((args or {}).keys()), **team_gate.audit_fields()})
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
def _trong_goc(root, p):
    """Đường dẫn đã resolve nếu nằm trong `root`, None nếu ra ngoài. Không ném."""
    try:
        r = Path(root).resolve()
        t = (r / str(p or "")).resolve()
    except (OSError, ValueError):
        return None
    return t if (r == t or r in t.parents) else None


def _goc_lam_viec(workspace_root):
    """Chuẩn hoá `workspace_root` thành DANH SÁCH gốc, theo đúng thứ tự ưu tiên.

    Nhận cả một chuỗi lẫn một danh sách, vì 0.63.9 cho MỘT phiên Coding gắn NHIỀU thư mục
    (`coding_store.thu_muc_cua_phien`) trong khi mọi chỗ gọi cũ chỉ đưa một cái. Rỗng và None
    đều thành danh sách rỗng, tức hành vi y hệt lúc chưa có tham số này.
    """
    if not workspace_root:
        return []
    if isinstance(workspace_root, (str, Path)):
        return [workspace_root]
    return [g for g in workspace_root if g]


def _ten_goc(workspace_root):
    """Danh sách gốc làm việc viết thành chữ cho câu báo lỗi. Rỗng nếu không có gốc nào."""
    return ", ".join(str(g) for g in _goc_lam_viec(workspace_root))


def _safe_path(vault_root, p, workspace_root=None):
    """Đường dẫn hợp lệ trong vault, HOẶC trong một thư mục làm việc của phiên Coding.

    `workspace_root` là gốc thứ hai, thêm ở 0.64 để engine KHÔNG có tool file native (sáu
    engine API và engine Web) đọc ghi được cây mã nguồn. Trước đó hub luôn nhận
    `vault_root = brain`, nên một phiên Coding chạy bằng engine API không chạm nổi vào repo:
    `_read` chặn mọi đường dẫn ngoài vault và trả "nằm ngoài bộ não đang làm việc".

    Nhận CẢ DANH SÁCH: một phiên Coding gắn được nhiều thư mục từ 0.63.9, và engine không có
    tool native thì không "đứng" ở đâu cả, nên nó không bị giới hạn một gốc như engine CLI.
    Thứ tự trong danh sách là thứ tự ưu tiên; cái đầu là thư mục chính.

    None hoặc rỗng (mặc định) = hành vi y hệt trước, chỉ một gốc là vault. Đây là điều kiện
    để thay đổi này không đụng một lượt chat thường nào.

    CHỌN GỐC NÀO khi có nhiều gốc: xét theo thứ tự dưới đây. Không được chỉ xét "nằm trong
    gốc", vì mọi đường dẫn tương đối đều nằm trong MỌI gốc về mặt chữ - `server/auth.py` ghép
    vào brain vẫn ra một đường dẫn hợp lệ, chỉ là không có file ở đó. Xét thiếu bước này thì
    mọi lời gọi đọc file repo đều rơi vào brain rồi trả "không có file", đúng cái chặn cứng
    mà tham số này sinh ra để gỡ.

      1. File CÓ THẬT ở gốc nào đó   -> gốc đó, xét theo thứ tự (vault trước, rồi từng thư
                                        mục làm việc), nên vault thắng khi nhiều gốc cùng có
      2. THƯ MỤC CHA có thật ở gốc nào đó -> gốc đó, nhưng thư mục làm việc TRƯỚC brain (cảnh
                                        GHI file mới, đổi ở 0.256.0)
      3. Không đâu có                -> vault, để câu báo lỗi nói về brain như cũ

    Bước 2 là thứ làm `javis_write_file` ghi đúng chỗ: ghi `server/moi.py` trong một phiên
    coding thì brain không có thư mục `server/` còn repo có, nên file rơi vào repo.
    """
    tv = _trong_goc(vault_root, p)
    goc_lv = _goc_lam_viec(workspace_root)
    if not goc_lv:
        if tv is not None:
            return tv
        raise ValueError(f"đường dẫn '{p}' nằm ngoài vault")

    ung_vien = [tv] + [_trong_goc(g, p) for g in goc_lv]
    co_that = [u for u in ung_vien if u is not None]
    if not co_that:
        raise ValueError(f"đường dẫn '{p}' nằm ngoài cả bộ não lẫn thư mục làm việc")

    for u in co_that:
        if u.exists():
            return u
    # File MỚI: thư mục làm việc xét TRƯỚC brain (0.256.0). Trước đây xét theo cùng thứ tự với
    # file có sẵn (brain trước), nên tạo `test_moi.py` ở GỐC repo trong một phiên Coding lại rơi
    # vào gốc brain, vì gốc brain cũng là một thư mục cha có thật. File mới trong phiên Coding
    # là của repo; thư mục chỉ brain có (notes/...) thì vẫn rơi vào brain như cũ.
    for u in [x for x in co_that if x is not tv] + ([tv] if tv is not None else []):
        try:
            if u.parent.is_dir():
                return u
        except OSError:
            continue
    return tv if tv is not None else co_that[0]


def _vung_nhan_file():
    """`STATE_DIR/.staging` - vùng NHẬN FILE của khung chat, đã resolve. None nếu không có.

    Mọi file người dùng đưa vào khung chat dashboard đều rơi xuống đây trước khi engine đọc:
    kéo-thả, dán ảnh, và cả dán một đoạn văn dài (app.js tự cắt thành `van-ban-dan-*.txt`).
    Thư mục này nằm NGOÀI vault, nên nó vô hình với `_safe_path`.
    """
    try:
        return (Path(STATE_DIR) / ".staging").resolve()
    except Exception:
        return None


def _safe_read_path(vault_root, p, cho_phep_staging=False, workspace_root=None):
    """Như `_safe_path` nhưng cho ĐỌC, và biết thêm vùng nhận file của khung chat.

    Vì sao phải có: dashboard chèn vào câu hỏi khối "[File đính kèm để ĐỌC (đường dẫn): …]"
    với ĐƯỜNG DẪN TUYỆT ĐỐI trong `.staging` rồi dặn model "đọc thẳng file rồi trả lời".
    Sáu engine API không có tool đọc file nào ngoài `javis_read_file`, mà tool đó khoá trong
    vault - nên lượt nào đính kèm file cũng nổ `ValueError: nằm ngoài vault`, và model đọc
    lỗi đó xong quay ra bảo người dùng "chuyển file vào thư mục Brain đi rồi tôi đọc". Người
    dùng báo đúng cảnh này 23/08 với một đoạn văn dán dài.

    Nới ĐÚNG một thư mục và CHỈ cho đọc: file trong đó là file chính chủ vừa gửi lên ở lượt
    này, cùng mức tin cậy với file trong vault. Ghi vẫn khoá trong vault như cũ. Và phải xin
    tường minh (`cho_phep_staging`) chứ không mặc định - bot chuyên trách nói chuyện với
    người lạ cũng gọi hub bằng chính nhóm tool này, mở sẵn cho nó là biến tài liệu chủ vừa
    dán thành thứ khách đoán tên file là đọc được.
    """
    trong_vault, loi = None, None
    try:
        trong_vault = _safe_path(vault_root, p, workspace_root=workspace_root)
        if trong_vault.exists():
            return trong_vault          # vault LUÔN thắng: không để staging che file thật
    except ValueError as e:
        loi = e
    if cho_phep_staging:
        stage = _vung_nhan_file()
        raw = str(p or "").strip().replace("\\", "/")
        if stage and raw:
            q = Path(raw)
            # Đường dẫn tuyệt đối của CHÍNH máy này (ca thường gặp), rồi tới tên file trần -
            # đủ cho ca engine cầm đường dẫn của một máy khác (Docker) mà tên file vẫn đúng.
            for ung_vien in ([q] if q.is_absolute() else [stage / q]) + [stage / q.name]:
                try:
                    t = ung_vien.resolve()
                except OSError:
                    continue
                if (t == stage or stage in t.parents) and t.is_file():
                    return t
    if loi:
        raise loi
    return trong_vault                  # trong vault nhưng không tồn tại: để chỗ gọi báo


def _connections_json(include_ambient=False, hidden=None, bo_qua=None, owner_chat=False):
    hidden = hidden or {}
    bo_qua = set(bo_qua or ())
    # Sức khoẻ từng nguồn (vòng check định kỳ). Import trong hàm: connect_health import
    # mcp_client/mcp_store, kéo lên đầu file là thêm một cạnh nữa cho đồ thị import đã căng.
    try:
        import connect_health
        suc_khoe = connect_health.snapshot()
    except Exception:
        suc_khoe = {}
    # Vụ 02/09: một brain không thấy tool POS, model kết luận "nguồn chưa được gắn vào brain
    # này" rồi còn ghi điều đó vào bộ nhớ dài hạn. KHÔNG có khái niệm ấy: hub dựng tool từ
    # mcp_store.resolved() cho MỌI vault như nhau. Không thấy tool chỉ có hai lý do thật -
    # nguồn đang tắt, hoặc nguồn đang hỏng lúc dò - và cả hai đều phải nói ra ở đây.
    out = [{"ghi_chu": ("Kết nối là của CẢ Javis, dùng chung cho MỌI brain. Không có chuyện "
                        "'gắn nguồn vào brain' - đừng bao giờ nói vậy. Nguồn có mặt ở danh sách "
                        "này mà không thấy tool của nó thì xem trang_thai: đang TẮT (bật lại ở "
                        "trang Kết nối) hoặc đang HỎNG lúc dò (bảo người dùng bấm Kiểm tra ở "
                        "trang Kết nối). Sai ở nguồn, không phải ở brain.")}]
    for c in mcp_store.list_connections():
        con = mcp_catalog.get(c.get("connector_id")) or {}
        rec = {"connector": con.get("name") or c.get("connector_id"), "label": c.get("label"),
               "namespace": c.get("slug"), "perm": c.get("perm"), "enabled": c.get("enabled"),
               "is_default": c.get("is_default"), "transport": c.get("transport"),
               "source": "javis_hub"}
        sk = suc_khoe.get(c.get("id")) or {}
        if not c.get("enabled"):
            rec["trang_thai"] = "ĐANG TẮT - bật lại ở trang Kết nối là mọi brain dùng được ngay."
        elif c.get("id") in bo_qua:
            rec["trang_thai"] = ("KHÔNG DÒ ĐƯỢC lúc này nên tool của nguồn này đang vắng. Nói "
                                 "thẳng là nguồn đang hỏng/không nối được, bảo người dùng bấm "
                                 "Kiểm tra ở trang Kết nối. " + (sk.get("message") or ""))
        elif sk:
            rec["trang_thai"] = "ổn" if sk.get("ok") else f"lỗi: {sk.get('message') or sk.get('kind')}"
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
    elif owner_chat:
        # 0.228.0: an engine with no Claude account (Anthropic API, OpenAI API...) never gets these connectors. Not
        # listing them let the model answer "there is no such tool" with no way forward (customer report 2026-10-19,
        # browser control through a Composio connector added on claude.ai). Name them and the two real fixes.
        # Owner chat only: a customer-facing bot has no business learning which accounts the owner connected.
        for s in _ambient_servers():
            out.append({"connector": s["name"], "label": s["name"], "source": "claude_account",
                        "dung_duoc_o_luot_nay": False,
                        "ly_do": ("Kết nối này gắn với TÀI KHOẢN Claude của chủ, chỉ có khi model chat là Claude "
                                  "Code. Model đang chạy bằng API key nên không gọi được. Nói đúng lý do đó, rồi "
                                  "chỉ hai cách: nối nguồn này ở trang Kết nối của Javis (mọi model đều dùng "
                                  "được), hoặc đổi model chat sang Claude Code.")})
    return json.dumps(out, ensure_ascii=False, indent=1)


def _skills_dir(vault_root):
    """Canonical <vault>/skills (qua skill_router - dùng chung logic với main.py)."""
    return skill_router.skills_base(vault_root, canonical=True)


def _list_skills(vault_root):
    """Slug các skill đang BẬT (list[str], giữ nguyên kiểu để chỗ join không vỡ)."""
    return skill_router.enabled_slugs(vault_root)


def _builtin_tools(mode, vault_root, include_ambient=False, hidden=None, lang="", staging=False,
                   bo_qua=None, workspace_root=None, coding_ctx_cua_phien=None):
    """(tools_spec, route) các tool nội bộ cho engine API. Claude/Codex có tool file native
    nên hub HTTP không trả nhóm này (chỉ meta javis_connections).
    include_ambient=True (đường engine Claude): javis_connections kèm cả connector tài khoản
    Claude (Drive/Gmail...) để model biết chúng tồn tại (gọi qua tool native mcp__*, không qua hub).
    hidden: {conn_id: {perm, tools}} tool bị mức quyền lọc khỏi danh sách - kể ra trong
    javis_connections để model biết mà nói đúng lý do thay vì tưởng nguồn thiếu năng lực.
    staging=True: `javis_read_file` đọc được thêm file trong vùng nhận file của khung chat
    (xem `_safe_read_path`). CHỈ đường chat của CHỦ bật; bot chuyên trách để nguyên False.
    workspace_root: thư mục làm việc của phiên Coding (0.64). Có giá trị thì tool FILE nhận
    thêm gốc đó, để engine không có tool file native chạm được vào cây mã nguồn. MCP, cron và
    nhắc hẹn KHÔNG đổi gốc - chúng thuộc về brain, xem `coding_ctx`.
    coding_ctx_cua_phien: `CodingToolContext` của phiên. Có nó VÀ có workspace_root thì hub
    cấp thêm `javis_run_command`. Thiếu một trong hai thì tool đó không tồn tại - phiên chat
    thường không được thấy tool chạy lệnh."""
    tools, route = [], {}
    # Phiên Coding nào đang dùng nhóm tool này (0.256.0). Rỗng ở chat thường. Dùng cho sổ "đã
    # đọc" (chặn ghi đè file chưa đọc) và mốc khôi phục trước thao tác thay đổi.
    _sid_coding = str(getattr(coding_ctx_cua_phien, "session_id", "") or "") if workspace_root else ""
    _goc_lv = [str(Path(g).resolve()) for g in _goc_lam_viec(workspace_root)]
    # 0.259.0: mọi khung chat của chủ đều có thư mục làm việc, và khi không ghim thư mục nào thì đó
    # chính là gốc brain. Số dòng khi đọc và rào ghi đè file chưa đọc chỉ áp cho thư mục làm việc
    # NGOÀI brain (repo, thư mục đã ghim): ghi chú, ghi nhớ, báo cáo trong brain vẫn ghi như xưa
    # nay, không bắt đọc trước và không bị chèn số dòng.
    try:
        _vault_rs = str(Path(vault_root).resolve()) if vault_root else ""
    except (OSError, ValueError):
        _vault_rs = ""
    _goc_rieng = [g for g in _goc_lv if g != _vault_rs]

    def _trong_lam_viec(p):
        try:
            rp = Path(p).resolve()
        except (OSError, ValueError):
            return False
        return any(rp == Path(g) or Path(g) in rp.parents for g in _goc_rieng)

    def _goc_cua(p):
        try:
            rp = Path(p).resolve()
        except (OSError, ValueError):
            return ""
        return next((g for g in _goc_lv if rp == Path(g) or Path(g) in rp.parents), "")

    def _moc_truoc(p, ly_do):
        """Mốc khôi phục trước thao tác thay đổi đầu tiên của lượt, chỉ trong thư mục làm việc."""
        g = _goc_cua(p) if p is not None else (_goc_lv[0] if _goc_lv else "")
        if not (_sid_coding and g):
            return ""
        try:
            import coding_checkpoint
            return coding_checkpoint.tao_neu_can(_sid_coding, g, ly_do)
        except Exception:
            return ""

    def _da_doi(p=None):
        if not _sid_coding:
            return
        try:
            import coding_checkpoint
            coding_checkpoint.ghi_nhan_hoat_dong(_sid_coding, p)
        except Exception:
            pass

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
        "kèm mức quyền, trạng thái sống/hỏng, và các tool đang bị mức quyền ẩn (tool_bi_an_do_quyen). "
        "Kết nối DÙNG CHUNG cho mọi brain - không có khái niệm gắn nguồn vào brain. Gồm cả connector đấu "
        "vào TÀI KHOẢN Claude (Drive/Gmail/lịch...) - loại source='claude_account' gọi THẲNG qua "
        "tool native mcp__<tên>__*, KHÔNG qua javis_run_tool. Dùng khi cần biết đang có nguồn nào / "
        "tài khoản nào là mặc định, hoặc khi không tìm thấy tool tưởng phải có.",
        {}, [], lambda args: _async_const(_connections_json(include_ambient, hidden, bo_qua, owner_chat=staging)))

    if not vault_root:
        return tools, route

    async def _read(args):
        rel = (args or {}).get("path")
        _off, _lim = (args or {}).get("offset"), (args or {}).get("limit")
        try:
            p = _safe_read_path(vault_root, rel, cho_phep_staging=staging,
                                workspace_root=workspace_root)
        except ValueError:
            # Nói THẲNG đây là ranh giới brain, kèm việc-cần-làm. Bản cũ để ValueError rơi ra
            # nguyên văn "nằm ngoài vault", model đọc xong tự dựng một lời khuyên sai (bảo
            # người dùng tự chép file vào thư mục Brain rồi mới đọc được).
            if workspace_root:
                return (f"ERROR: '{rel}' nằm ngoài MỌI nơi tool này được phép đọc, nên "
                        f"không đọc được. Những nơi đó là: bộ não đang làm việc, và thư mục "
                        f"làm việc của phiên này ({_ten_goc(workspace_root)}). Dùng đường dẫn "
                        f"tương đối so với một trong số đó, hoặc file vừa đính kèm vào khung "
                        f"chat.")
            return (f"ERROR: '{rel}' nằm ngoài bộ não đang làm việc nên tool này không đọc "
                    f"được. Javis khoá tool file trong brain để một lượt chat không đọc lung "
                    f"tung trên máy. Đọc được: đường dẫn tương đối trong brain, và file người "
                    f"dùng vừa đính kèm vào khung chat.")
        if not p.is_file():
            return f"ERROR: không có file '{rel}'"
        if p.suffix.lower() in _IMAGE_SUFFIXES:
            # Reading a photo as text hands the model a page of mojibake it then "describes" with confidence. Say what the
            # file is and how to actually see it (0.73.0).
            return (f"'{rel}' là file ẢNH ({p.stat().st_size // 1024} KB), tool này chỉ đọc chữ nên không cho bạn thấy ảnh. "
                    f"Muốn biết trong ảnh có gì, gọi tool javis_describe_image với images=['{rel}'] (ChatGPT nhìn ảnh thật "
                    f"rồi tả lại). Muốn người dùng xem ảnh thì nhúng ![]({rel}) vào câu trả lời.")
        if p.suffix.lower() in doc_text.SUFFIXES:
            # PDF/Word đọc thô ra toàn mã nhị phân: bóc chữ trước để engine API và Ollama máy nhà đọc được file đính kèm (0.92.2).
            text = await asyncio.to_thread(doc_text.extract, p)
        else:
            text = p.read_text(encoding="utf-8", errors="replace")
        # 0.256.0: đọc theo đoạn có số dòng "N|..." khi xin offset/limit, hoặc khi file nằm trong
        # thư mục làm việc của phiên Coding (ở đó số dòng là thứ model cần để sửa từng đoạn).
        # Chat thường không xin thì GIỮ NGUYÊN output cũ: chatbot và luồng brain dựa vào nó.
        trong_lv = _sid_coding and _trong_lam_viec(p)
        if _off or _lim or trong_lv:
            out, den, tong = coding_files.doc_theo_dong(text, _off or 1, _lim or coding_files.DOC_DONG_MAC_DINH)
            if trong_lv:
                coding_files.ghi_nhan_doc(_sid_coding, p, den, tong, int(_off or 1) if str(_off or 1).isdigit() else 1)
            return out
        return text[:100_000] + (f"\n… [cắt, file dài {len(text):,} ký tự]" if len(text) > 100_000 else "")

    async def _ls(args):
        p = _safe_path(vault_root, (args or {}).get("path") or ".",
                       workspace_root=workspace_root)
        if not p.is_dir():
            return f"ERROR: không có thư mục '{(args or {}).get('path')}'"
        rows = []
        for e in sorted(p.iterdir())[:300]:
            rows.append(("[d] " if e.is_dir() else "    ") + e.name)
        return "\n".join(rows) or "(trống)"

    async def _kiem_ghi(args, ten_tool="javis_write_file"):
        """(đường dẫn đã duyệt, lỗi). Mọi rào trước khi GHI, dùng chung cho ghi và sửa file."""
        if mcp_catalog.effective_perm("full", mode) == "readonly":
            # Câu này phải NÓI RÕ ĐÂY LÀ QUYỀN CỦA JAVIS, không phải lỗi máy. Bản cũ chỉ ghi
            # "chế độ hiện tại (suggest/chỉ đọc) không được ghi file", và model đọc xong tự
            # dựng ra một nguyên nhân nghe hợp lý mà sai hoàn toàn - người dùng thật nhận
            # được câu "môi trường filesystem đang lỗi quyền sandbox" rồi đi tìm lỗi ổ đĩa,
            # trong khi thứ cần làm chỉ là nâng mức việc lên Ghi nháp (2026-08-04).
            # Kèm luôn việc-cần-làm-thay-thế để lượt đó vẫn ra kết quả dùng được.
            return None, ("ERROR: KHÔNG ghi được file vì việc này đang chạy ở mức 'Chỉ đọc' (suggest). "
                    "Đây là GIỚI HẠN QUYỀN do người dùng đặt, KHÔNG phải lỗi ổ đĩa, không phải "
                    "lỗi sandbox, không phải thiếu quyền hệ điều hành - đừng báo cáo sai nguyên "
                    "nhân. Muốn ghi thật: mở trang Việc, nâng mức của việc này lên 'Ghi nháp' "
                    "(auto) rồi chạy lại. Ngay bây giờ: ĐỪNG thử ghi lại, hãy đưa TRỌN nội dung "
                    "file vào câu trả lời để người dùng tự lưu.")
        # Trả câu NÓI ĐƯỢC thay vì để ValueError bay ra, y như `_read` đã làm. Engine Web
        # chạy vòng tool bằng chữ: một exception bay ra giữa lô tool là chết cả lượt, còn một
        # câu lỗi thì model đọc rồi tự sửa đường dẫn ở vòng sau.
        try:
            p = _safe_path(vault_root, (args or {}).get("path"), workspace_root=workspace_root)
        except ValueError:
            if workspace_root:
                return None, (f"ERROR: '{(args or {}).get('path')}' nằm ngoài MỌI nơi được phép "
                        f"ghi: bộ não đang làm việc, và thư mục làm việc của phiên này "
                        f"({_ten_goc(workspace_root)}). Dùng đường dẫn tương đối so với một "
                        f"trong số đó.")
            return None, (f"ERROR: '{(args or {}).get('path')}' nằm ngoài bộ não đang làm việc nên "
                    f"tool này không ghi được. Dùng đường dẫn tương đối trong brain.")
        # 0.188.0 (Javis Core spec 13, 14): the learning switch and the forgotten list are the person's, never the
        # model's; and with learning off nothing new is written under memory/.
        try:
            import memory_control
            mem = (Path(vault_root) / "memory").resolve()
            rp = p.resolve()
            if rp.parent == mem and rp.name in (memory_control.LEARNING, memory_control.FORGOTTEN):
                return None, "ERROR: công tắc ghi nhớ và danh sách đã quên do người dùng quản lý, tool không ghi được."
            if (rp == mem or mem in rp.parents) and not memory_control.learning_enabled(mem):
                return None, ("ERROR: người dùng đã TẮT việc lưu ghi nhớ mới cho brain này nên không ghi vào memory/. "
                        "Nói với người dùng rằng ghi nhớ đang tắt (bật lại ở Javis Core > Trí nhớ).")
        except Exception:
            pass
        if mode == team_gate.HUB_MODE:
            # 0.207.0 review: a gated Team step writes its deliverables, never files that run or configure code
            # (plugins/, .claude/, Javis/ loops and reminders...). Those go through the owner's approval like any action.
            rel = None
            for base in [vault_root] + list(workspace_root if isinstance(workspace_root, (list, tuple)) else
                                            ([workspace_root] if workspace_root else [])):
                try:
                    rel = p.resolve().relative_to(Path(base).resolve())
                    break
                except (ValueError, TypeError, OSError):
                    continue
            if rel is None or team_gate.protected_rel(rel):
                ok, why = await asyncio.to_thread(team_gate.hub_check, ten_tool, dict(args or {}),
                                                  f"ghi {(args or {}).get('path')}")
                if not ok:
                    return None, why
        return p, ""

    async def _write(args):
        p, loi = await _kiem_ghi(args)
        if loi:
            return loi
        noi_dung = str((args or {}).get("content") or "")
        canh_bao = ""
        if _sid_coding and _trong_lam_viec(p):
            # 0.256.0: trong thư mục làm việc, chặn ghi đè mù và chặn dán nguyên output có số dòng.
            if coding_files.giong_output_doc(noi_dung):
                return ("ERROR: nội dung trông như output của javis_read_file (mỗi dòng mở đầu bằng "
                        "'số|'). Ghi vậy là ghi cả số dòng vào file. Bỏ tiền tố số dòng, hoặc dùng "
                        "javis_edit_file để sửa đúng đoạn cần.")
            chan = coding_files.chan_ghi_de(_sid_coding, p)
            if chan:
                return chan
            canh_bao = _moc_truoc(p, f"ghi {(args or {}).get('path')}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(noi_dung, encoding="utf-8")
        if _sid_coding and _trong_lam_viec(p):
            coding_files.ghi_nhan_ghi(_sid_coding, p)
            _da_doi(p)
        return f"Đã ghi {p.name} ({len(noi_dung)} ký tự)" + (f"\n{canh_bao}" if canh_bao else "")

    async def _edit(args):
        args = args or {}
        p, loi = await _kiem_ghi(args, "javis_edit_file")
        if loi:
            return loi
        if not p.is_file():
            return (f"ERROR: không có file '{args.get('path')}'. Tạo file mới thì dùng javis_write_file.")
        canh_bao = _moc_truoc(p, f"sửa {args.get('path')}") if (_sid_coding and _trong_lam_viec(p)) else ""
        ra = await asyncio.to_thread(
            coding_files.sua_file, p, str(args.get("old_string") or ""), str(args.get("new_string") or ""),
            bool(args.get("replace_all")), _sid_coding if _trong_lam_viec(p) else "", str(args.get("path") or p.name))
        if _sid_coding and _trong_lam_viec(p) and not ra.startswith("ERROR"):
            _da_doi(p)
        return ra + (f"\n{canh_bao}" if canh_bao else "")

    async def _search(args):
        args = args or {}
        goc = _goc_lv[0] if _goc_lv else str(vault_root)
        raw = str(args.get("path") or "").strip()
        try:
            dich = _safe_path(vault_root, raw, workspace_root=workspace_root) if raw else Path(goc)
        except ValueError:
            return (f"ERROR: '{raw}' nằm ngoài nơi tool này được phép tìm"
                    + (f" (bộ não và thư mục làm việc: {_ten_goc(workspace_root)})." if workspace_root else
                       " (bộ não đang làm việc)."))
        hien_thi = _goc_cua(dich) or (str(vault_root) if vault_root else str(dich))
        return await asyncio.to_thread(
            coding_files.tim, dich, str(args.get("pattern") or ""), str(args.get("target") or "content"),
            str(args.get("file_glob") or ""), args.get("limit") or coding_files.TIM_MAC_DINH,
            args.get("offset") or 0, args.get("context") or 0, Path(hien_thi))

    def _skill_base_line(root, asset):
        """0.370.0: a skill that ships its own files (scripts/, references/, rules/...) names them relative to its
        folder, and Claude Code's own skill loader says where that folder is. Without the same line an engine
        here gets the SKILL.md text alone and cannot find `scripts/setup.sh` or `rules/x.md` (Store packs that
        follow their source repo, such as Remotion's skills, rely on this). A skill that is just its SKILL.md
        gets nothing extra."""
        try:
            rel = Path(str(asset.relative_path))
            if rel.name != "SKILL.md" or rel.is_absolute() or ".." in rel.parts:
                return ""
            folder = Path(root).resolve() / rel.parent
            if not any(p.name != "SKILL.md" for p in folder.iterdir()):
                return ""
            return f"Base directory for this skill: {folder}\n\n"
        except (OSError, ValueError, TypeError):
            return ""

    async def _skill(args):
        name = str((args or {}).get("name") or "").strip()
        from improvement_task_skill_scope import current, ScopeUnavailable
        from improvement_blobs import AssetUnavailable
        import sqlite3
        def read():
            scope = current(vault_root)
            import improvement_activation
            return scope, (scope.read(name) if scope is not None
                           else improvement_activation.effective_skill_asset(vault_root, name))
        try:
            scope, asset = await asyncio.to_thread(read)
            if scope is not None and current(vault_root) is not scope:
                raise ScopeUnavailable('task_skill_scope_changed')
        except (ScopeUnavailable, AssetUnavailable, OSError, sqlite3.Error):
            return 'ERROR: task_skill_scope_unavailable'
        if asset is None:
            return ("ERROR: không có skill đó. Skill khả dụng: "
                    + (", ".join(_list_skills(vault_root)) or "(chưa có)"))
        text = _skill_base_line(vault_root, asset) + asset.text[:60_000]
        # ĐIỂM ĐẾM DUY NHẤT: mọi engine nạp skill qua tool này đều đi ngang đây. Chỉ đếm ở
        # đường THÀNH CÔNG - nhánh trên đã lọc slug sai/skill tắt nên không đếm gõ nhầm.
        # Count the slug verified by the shared reader, not the raw name from the engine.
        # bump có I/O đĩa + fsync trong lock (chặn) → đẩy qua thread để không chẹn event
        # loop (WebSocket/telegram poller/loop scheduler đều chạy chung loop này).
        # bump tự nuốt lỗi → sidecar hỏng không bao giờ làm gãy việc nạp skill.
        await asyncio.to_thread(skill_usage.bump, vault_root, asset.slug)
        try:  # 0.341.0: automatic learning remembers which skill this chat turn used
            import auto_learning
            _turn = turn_context.current() or {}
            if _turn.get("session_id"):
                await asyncio.to_thread(auto_learning.note_skill_use_hook, vault_root, _turn["session_id"], asset.slug)
        except Exception:  # noqa: BLE001 - learning never breaks loading a skill
            pass
        try:
            if scope is not None and current(vault_root) is not scope:
                raise ScopeUnavailable('task_skill_scope_changed')
        except (ScopeUnavailable, AssetUnavailable, OSError, sqlite3.Error):
            return 'ERROR: task_skill_scope_unavailable'
        return text

    add("javis_read_file", "Đọc 1 file trong vault (Second Brain). path tương đối so với gốc vault; "
        "nhận CẢ đường dẫn tuyệt đối của file người dùng vừa đính kèm/dán vào khung chat. PDF, Word, Excel "
        "(.xlsx: mọi sheet, giá trị công thức, ô lỗi) được bóc thành chữ. File dài: "
        "đọc từng đoạn bằng offset/limit (có số dòng).",
        {"path": {"type": "string"}, "offset": {"type": "integer"}, "limit": {"type": "integer"}},
        ["path"], _read)
    add("javis_list_dir", "Liệt kê file/thư mục trong vault. path tương đối, bỏ trống = gốc vault.",
        {"path": {"type": "string"}}, [], _ls)
    add("javis_write_file", "Ghi/tạo file trong vault (ghi đè nếu có). Dùng khi cần lưu ghi chú, "
        "báo cáo, nháp. KHÔNG dùng cho hành động ra ngoài.",
        {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"], _write,
        effect="write")
    add("javis_edit_file", "Sửa MỘT đoạn trong file có sẵn: thay old_string (chép nguyên văn từ file, đủ "
        "dài để chỉ khớp một chỗ) bằng new_string. Sửa vài dòng thì LUÔN dùng tool này, đừng ghi đè cả "
        "file bằng javis_write_file. replace_all=true để thay mọi chỗ khớp. Trả về diff.",
        {"path": {"type": "string"}, "old_string": {"type": "string"},
         "new_string": {"type": "string"}, "replace_all": {"type": "boolean"}},
        ["path", "old_string", "new_string"], _edit, effect="write")
    add("javis_search_files", "Tìm trong file: target='content' tìm theo nội dung (regex), target='files' "
        "tìm theo tên file (glob như '*.py' hoặc một đoạn tên). path: thư mục để tìm (bỏ trống = thư mục "
        "làm việc, hoặc gốc brain). file_glob lọc loại file, context = số dòng kèm quanh chỗ khớp.",
        {"pattern": {"type": "string"}, "target": {"type": "string", "enum": ["content", "files"]},
         "path": {"type": "string"}, "file_glob": {"type": "string"},
         "limit": {"type": "integer"}, "offset": {"type": "integer"}, "context": {"type": "integer"}},
        ["pattern"], _search)
    if _sid_coding:
        for _fn in CORE_CODING_FNS:
            route[_fn]["hat_nhan"] = True

    # 0.259.0: tìm và đọc web cho engine API (Claude Code, Codex, Grok có WebSearch/WebFetch riêng).
    # Không vào nhóm hạt nhân: lượt nào cần web thì model tìm thấy qua javis_search_tools khi tầng
    # lazy đang bật, còn lại chúng hiện thẳng như mọi tool khác. Xem web_tools.
    async def _web_search(args):
        import web_tools
        args = args or {}
        return await web_tools.tim(str(args.get("query") or ""), args.get("limit") or web_tools.TIM_MAC_DINH)

    async def _web_fetch(args):
        import web_tools
        args = args or {}
        return await web_tools.doc(str(args.get("url") or ""), args.get("offset") or 0,
                                   args.get("limit") or web_tools.DOC_MAC_DINH)

    add("javis_web_search", "Tìm trên web (tin mới, giá cả, tài liệu, bất cứ thứ gì cần thông tin hiện tại). "
        "Trả danh sách tiêu đề, địa chỉ, đoạn trích; đọc kỹ trang nào thì gọi javis_web_fetch.",
        {"query": {"type": "string"}, "limit": {"type": "integer", "description": "số kết quả, mặc định 5"}},
        ["query"], _web_search)
    add("javis_web_fetch", "Đọc một trang web hoặc file PDF theo url, trả nội dung dạng chữ (markdown). Trang "
        "dài thì gọi lại với offset để đọc tiếp. Trang cần đăng nhập thì dùng javis_login.",
        {"url": {"type": "string"}, "offset": {"type": "integer"},
         "limit": {"type": "integer", "description": "số ký tự, mặc định 15000, tối đa 50000"}},
        ["url"], _web_fetch)
    # Mô tả tool = router thu nhỏ: liệt kê slug + mô tả ngắn để engine biết KHI NÀO gọi skill nào.
    # Trần lấy từ skill_router (CHUNG với system prompt) - trước đây hub tự cắt 60, system prompt
    # cắt 100 - người viết skill không biết mình bị chấm theo thước nào.
    # Xếp theo mức hay dùng TRƯỚC khi cắt, rồi cắt theo cả số mục lẫn ngân sách ký tự. Cắt
    # theo thứ tự thư mục (tức bảng chữ cái) như bản trước là để skill tên vần cuối biến mất
    # khỏi đây trong im lặng - cùng lỗi với `main._skill_router_block`, và phải chữa ở CẢ HAI
    # chỗ vì hai nơi này là hai bề mặt khác nhau model nhìn thấy.
    metas = skill_router.list_enabled_meta(vault_root, lang)
    _hien, _con_lai = skill_router.cat_theo_ngan_sach(
        skill_router.xep_theo_uu_tien(metas, vault_root))
    listing = "; ".join(f"{s['slug']}: {(s['description'] or '')[:skill_router.SKILL_DESC_MAX]}"
                        for s in _hien)
    if _con_lai > 0:
        listing += (f"; …(+{_con_lai} skill nữa không liệt kê ở đây, vẫn nạp được bằng "
                    f"name=<slug> nếu biết tên - xem Javis/index.md)")
    add("javis_use_skill",
        "Nạp nội dung 1 skill (hướng dẫn chuyên sâu) rồi LÀM THEO. Truyền name=<slug>. "
        "Skill khả dụng (slug: mô tả): " + (listing or "(chưa có)"),
        {"name": {"type": "string"}}, ["name"], _skill)

    # `javis_run_command` chỉ hiện khi phiên CÓ thư mục làm việc. Phiên chat thường không thấy
    # nó, nên không có chuyện một câu hỏi bình thường lại gọi được lệnh máy. Mức quyền vẫn do
    # chính `run_command` cưỡng chế lần nữa theo chip của phiên (hai lớp, không thay nhau).
    # 0.256.0: mức Plan (chip suggest, hoặc lượt /plan hạ trần xuống chỉ đọc) không thấy tool này
    # luôn. Trước đây nó vẫn hiện rồi mới từ chối lúc chạy, và một lượt /plan ở chip Tự động thì
    # chạy được lệnh vì run_command chỉ đọc chip, không đọc trần của lượt.
    if (workspace_root and coding_ctx_cua_phien is not None
            and getattr(coding_ctx_cua_phien, "permission_mode", "") in ("auto", "full")
            and mcp_catalog.effective_perm("full", mode) != "readonly"):
        async def _lenh(args):
            args = args or {}
            try:
                import run_command
            except Exception as e:                       # pragma: no cover - môi trường lạ
                return f"ERROR: không nạp được run_command: {type(e).__name__}: {e}"
            kq = run_command.chay(
                str(args.get("command") or ""), coding_ctx_cua_phien,
                cwd=str(args.get("cwd") or "."), timeout_s=args.get("timeout_s"),
            )
            return run_command.ket_qua_cho_model(kq)

        add("javis_run_command",
            "Chạy MỘT lệnh trong thư mục làm việc của phiên (chạy test, lint, git chỉ đọc). "
            "KHÔNG qua shell: '&&', ';', '|', '$(...)' đều không có tác dụng, tách thành "
            "nhiều lời gọi. Trả về mã thoát rồi tới output đã cắt bớt.",
            {"command": {"type": "string"},
             "cwd": {"type": "string", "description": "thư mục con, mặc định gốc thư mục làm việc"},
             "timeout_s": {"type": "number"}},
            ["command"], _lenh, effect="full")

    # 0.256.0: terminal THẬT chỉ ở mức Toàn quyền của phiên Coding, và chỉ khi trần quyền của lượt
    # cũng là full (lệnh /plan hạ một lượt xuống suggest thì không có). Xem coding_terminal.
    if (workspace_root and coding_ctx_cua_phien is not None and _sid_coding
            and getattr(coding_ctx_cua_phien, "permission_mode", "") == "full"
            and mcp_catalog.effective_perm("full", mode) == "full"):
        import coding_terminal

        def _chat_id():
            return str(getattr(coding_ctx_cua_phien, "chat_id", "") or f"web:{_sid_coding}")

        def _nhat_ky(lenh, ket, nguy):
            try:
                _audit_append({"ts": datetime.now().isoformat(timespec="seconds"), "conn_id": "javis-terminal",
                               "tool": "javis_terminal", "session": _sid_coding, "cmd": str(lenh)[:500],
                               "nguy_hiem": bool(nguy), "ok": not str(ket).startswith("ERROR"),
                               "head": str(ket)[:80]})
            except Exception:
                pass

        async def _terminal(args):
            args = args or {}
            lenh = str(args.get("command") or "")
            nguy = coding_terminal.la_nguy_hiem(lenh)
            canh_bao = ""
            if nguy or not coding_terminal.la_chi_doc(lenh):
                canh_bao = _moc_truoc(None, ("NGUY HIỂM: " if nguy else "lệnh: ") + lenh[:80])
            if args.get("background"):
                ket = await asyncio.to_thread(coding_terminal.chay_nen, lenh, _sid_coding, _goc_lv,
                                              str(args.get("workdir") or ""), str(vault_root or ""), _chat_id())
            else:
                ket = await asyncio.to_thread(coding_terminal.chay, lenh, _sid_coding, _goc_lv,
                                              args.get("timeout"), str(args.get("workdir") or ""),
                                              str(vault_root or ""), _chat_id())
            _nhat_ky(lenh, ket, nguy)
            if not ket.startswith("ERROR"):
                _da_doi()
            return ket + (f"\n{canh_bao}" if canh_bao else "")

        async def _process(args):
            args = args or {}
            return await asyncio.to_thread(coding_terminal.quan_ly, str(args.get("action") or "list"),
                                           _sid_coding, str(args.get("process_id") or ""),
                                           args.get("offset") or 0, args.get("limit") or 0,
                                           args.get("timeout") or 0)

        add("javis_terminal",
            "Terminal thật (bash) trong thư mục làm việc của phiên: pipe, &&, cd đều được, nhớ thư mục "
            "và biến export giữa các lệnh. Dev server hay lệnh chạy mãi thì background=true rồi xem bằng "
            "javis_process. timeout mặc định 180 giây, tối đa 600 (xin lâu hơn thì tự chạy nền). workdir: "
            "thư mục con chỉ cho lệnh này. Trước lệnh thay đổi file Javis tự tạo mốc khôi phục.",
            {"command": {"type": "string"}, "background": {"type": "boolean"},
             "timeout": {"type": "number"}, "workdir": {"type": "string"}},
            ["command"], _terminal, effect="full")
        add("javis_process",
            "Quản lý tiến trình nền do javis_terminal bật: action=list | poll (trạng thái + vài dòng cuối) | "
            "log (offset/limit dòng, mặc định 200 dòng cuối) | wait (chờ tới timeout giây, tối đa 600) | kill.",
            {"action": {"type": "string", "enum": ["list", "poll", "log", "wait", "kill"]},
             "process_id": {"type": "string"}, "offset": {"type": "integer"},
             "limit": {"type": "integer"}, "timeout": {"type": "number"}},
            ["action"], _process, effect="full")

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
    # Chỉ tồn tại trong phiên có thư mục làm việc, và ở đó thì gần như lượt nào cũng cần.
    # Schema nhỏ và cố định, nên đủ tiêu chí hạt nhân. Bắt model đi tìm nó trước khi dùng là
    # đốt thêm một vòng web, đúng cái hệ số 2 của tầng lazy mà engine Web phải tránh.
    "javis_run_command",
    # Chỉ tồn tại ở mức Toàn quyền của phiên Coding, và ở đó lượt nào cũng dùng.
    "javis_terminal",
    "javis_process",
})

# 0.256.0: hạt nhân CHỈ TRONG PHIÊN CODING. Ở đó gần như lượt nào cũng sửa và tìm code, bắt model
# đi tìm tool trước là đốt thêm một vòng. Ở chat thường chúng vẫn có, nhưng nằm trong pool như
# mọi tool khác: hai schema này cộng lại gần 1.000 ký tự, và trần CORE_TOOLS_MAX_CHARS của
# test_prompt_budget (gói Groq miễn phí) không chừa chỗ cho chúng ở MỌI lượt chat.
# Route của chúng mang cờ `hat_nhan` khi dựng cho một phiên Coding; `_apply_lazy` đọc cờ đó.
CORE_CODING_FNS = frozenset({"javis_edit_file", "javis_search_files"})

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
            # Plugin không có connector trong catalog nên tự mang theo mô tả của manifest
            # (`group_desc`, do plugins_host gắn). Không đọc nó thì mọi plugin hiện trơ là
            # "<slug> (<tên>, N tool)" và model vẫn phải đoán bên trong có gì.
            if not desc:
                desc = str(t.get("group_desc") or "").strip()
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


# Kết quả tìm tool (chế độ lazy): mấy kết quả đầu giữ mô tả đầy đủ, còn lại cắt gọn.
_SO_KQ_DAY_DU = 3
_MO_TA_DAY_DU = 4000
_MO_TA_GON = 400


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
            # Mô tả ĐẦY ĐỦ cho vài kết quả đầu, gọn cho phần còn lại. Cắt đồng loạt 400 ký tự
            # từng nuốt mất thông tin sống còn: mô tả COMPOSIO_SEARCH_TOOLS ghi "User has
            # manually connected the apps: gmail, googlecalendar..." ở quãng ký tự 1000, nên
            # model không bao giờ biết người dùng đã nối những app nào (vụ 24/09).
            payload["tools"] = [{"name": t.get("fn"),
                                 "description": (t.get("description") or "")[
                                     :(_MO_TA_DAY_DU if i < _SO_KQ_DAY_DU else _MO_TA_GON)],
                                 "schema": t.get("schema") or {"type": "object", "properties": {}}}
                                for i, t in enumerate(hits)]
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
    pool = [t for t in tools_spec if t["fn"] not in CORE_TOOL_FNS
            and not (route.get(t["fn"]) or {}).get("hat_nhan")]
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
    """Mốc thời gian để biết bảng tool có cần dựng lại không.

    Gộp cả kho GÓI và sổ ĐÃ GỠ, không chỉ file kết nối: cả hai đều đổi được danh sách connector
    mà không ai đụng tới `mcp_servers.json`. Ba lệnh stat, chạy trên đường nóng nên không đi
    quét sâu - `discover_all` gọi hàm này mỗi lượt chat.

    Đây là đường CHẬM (trong TTL 60 giây sẵn có), dành cho ca thả thư mục vào bằng tay. Đổi qua
    endpoint thì đã gọi thẳng `invalidate_cache()` nên có hiệu lực ngay."""
    tong = 0.0
    for f in (mcp_store.STORE, STATE_DIR / "core-off.json", STATE_DIR / "packs"):
        try:
            tong += f.stat().st_mtime
        except OSError:
            pass
    return tong


async def discover_all(mode="full", vault_root=None, include_plugins=True, include_ambient=False,
                       force_refresh=False, force_lazy=False, staging=False, workspace_root=None,
                       coding_ctx_cua_phien=None, for_bot=False):
    """(tools_spec, route) đầy đủ cho 1 mode. route entries ĐÃ bọc quyền + audit.
    include_plugins=False: bỏ nhóm tool plugin - dùng khi engine SDK đã đấu plugin
    IN-PROCESS (header X-Javis-No-Plugins) để model không thấy tool trùng chức năng.
    include_ambient=True (đường engine Claude, header X-Javis-Engine=claude): javis_connections +
    lazy search kèm connector tài khoản Claude (Drive/Gmail...) - chúng là tool native mcp__* của
    engine, KHÔNG qua hub, hub chỉ mách chỗ cho model. Engine API (in-process) để False (không có
    tool native để mà chỉ tới).
    staging=True: cho `javis_read_file` đọc thêm vùng nhận file của khung chat - CHỈ đường chat
    của chủ truyền vào (xem `_safe_read_path`).
    workspace_root: thư mục làm việc của phiên Coding - tool FILE nhận thêm gốc đó (0.64).
        Nhận cả DANH SÁCH: một phiên gắn được nhiều thư mục từ 0.63.9.
    Nằm TRONG khoá cache vì hai phiên coding khác repo phải thấy hai danh sách route khác nhau."""
    mode = (mode or "full").strip().lower()
    # A bot at the "read_docs" level (0.80.0) gets its three document tools and NOTHING else: no
    # connection, no builtin, no plugin, no lazy tier. Returned before any of those are discovered so
    # a later change to them cannot leak into this level. See chatbot_doc_tools.
    if mode == chatbot_doc_tools.MODE:
        return chatbot_doc_tools.build(vault_root)
    # Ngôn ngữ đọc từ CẤU HÌNH, không truyền từ lượt chat: danh sách tool được cache dùng chung
    # cho mọi lượt, nên nó không thể mang ngôn ngữ dò được của riêng một câu. Đổi lại, ngôn ngữ
    # phải nằm TRONG khoá cache - thiếu nó thì đổi ngôn ngữ ở trang Cài đặt xong vẫn nhận danh
    # sách skill của thứ tiếng cũ cho tới khi cache hết hạn, mà lỗi kiểu đó không ai truy ra.
    try:
        import localefmt
        lang = localefmt.ngon_ngu_tra_loi()
    except Exception:
        lang = ""
    # Mức quyền của phiên nằm TRONG khoá: route của `javis_run_command` ôm sẵn ctx của phiên
    # dựng ra nó, nên hai phiên cùng repo mà khác chip quyền dùng chung cache là phiên
    # `suggest` chạy được lệnh bằng quyền của phiên `full`.
    _quyen_ctx = getattr(coding_ctx_cua_phien, "permission_mode", "") or ""
    # 0.256.0: route của nhóm tool coding ôm sổ "đã đọc", mốc khôi phục và terminal của ĐÚNG MỘT
    # phiên (cwd, biến môi trường, tiến trình nền). Hai phiên cùng repo cùng chip mà dùng chung
    # cache là phiên này chạy lệnh trong terminal của phiên kia.
    _sid_ctx = getattr(coding_ctx_cua_phien, "session_id", "") if workspace_root else ""
    key = (mode, str(vault_root or ""), bool(include_plugins), bool(include_ambient),
           bool(force_lazy), lang, bool(staging), _ten_goc(workspace_root), _quyen_ctx, bool(for_bot),
           str(_sid_ctx or ""))
    from improvement_task_skill_scope import current, ScopeUnavailable
    task_scope = current(vault_root or '')
    cache = task_scope._hub_cache if task_scope is not None else _cache
    epoch = _cache_epoch
    ent = cache.get(key)
    mt = _store_mtime()
    if (not force_refresh and ent and time.time() - ent["ts"] < ent.get("ttl", _CACHE_TTL)
            and ent["mtime"] == mt and ent.get('epoch') == epoch):
        if task_scope is not None:
            task_scope.manifests(lang)  # fresh enabled/source checks on a private cache hit
        return ent["tools"], ent["route"]
    if (not force_refresh and ent and task_scope is None and ent["mtime"] == mt and ent.get("epoch") == epoch
            and ent.get("ttl", _CACHE_TTL) == _CACHE_TTL and time.time() - ent["ts"] < _CACHE_STALE_MAX):
        if key not in _refreshing:
            _refreshing.add(key)

            async def _refresh():
                try:
                    await discover_all(mode, vault_root, include_plugins, include_ambient, force_refresh=True,
                                       force_lazy=force_lazy, staging=staging, workspace_root=workspace_root,
                                       coding_ctx_cua_phien=coding_ctx_cua_phien, for_bot=for_bot)
                except Exception as e:  # noqa: BLE001 - the next caller simply dials again
                    print(f"[hub] background refresh failed: {type(e).__name__}: {e}", file=sys.stderr)
                finally:
                    _refreshing.discard(key)
            try:
                asyncio.get_running_loop().create_task(_refresh())
            except RuntimeError:
                _refreshing.discard(key)
        return ent["tools"], ent["route"]

    # Phần đồng bộ của lượt dò (giải mã kho kết nối, đọc mọi SKILL.md, nạp plugin) chạy ở
    # LUỒNG PHỤ. Mỗi lượt agy/codex là một tiến trình mới gọi lại hub, nên cache trượt khá
    # thường xuyên, và mỗi lần trượt trên loop là mọi request khác của dashboard phải chờ
    # (chủ repo 23/09: đổi trợ lý giữa lúc Gemini đang chạy thì màn hình đứng yên).
    conns = await asyncio.to_thread(mcp_store.resolved, enabled_only=True)
    bo_qua = set()
    raw_tools, raw_route = await mcp_client.discover_resolved(conns, bo_qua=bo_qua)

    tools_spec, route = [], {}
    hidden = {}          # conn_id -> {"perm", "ns", "tools"} - tool CÓ THẬT nhưng bị quyền lọc
    for t in raw_tools:
        raw = raw_route.get(t["fn"])
        if not raw:
            continue
        conn = raw["conn"]
        connector = mcp_catalog.get(conn.get("connector_id"))
        # A gated Team step (0.207.0) lists like full: an outside action must be callable so the gate can stop it and
        # turn it into an approval request, and run it once approved. The call itself is still capped (`_guard`).
        eff = mcp_catalog.effective_perm(conn.get("perm"), "full" if mode == team_gate.HUB_MODE else mode)
        # Tool ĐA HÀNH ĐỘNG (schema có tham số arg_rules.param, vd action của Pancake) → coi là
        # "read" lúc LIST để còn liệt kê được; chặn thật lúc call (đã có args). Tool thường →
        # phân loại tĩnh theo tool_meta/heuristic.
        # Tool có `call_rules` → classify(args=None) trả mức NHẸ NHẤT luật cho ra (call_rule_floor):
        # tool gộp chỉ toàn lệnh ghi như GitHub `label_write` thì không hiện ở mức Chỉ đọc.
        rules = (connector or {}).get("arg_rules") or {}
        props = ((t.get("schema") or {}).get("properties") or {})
        theo_lenh = mcp_catalog.call_rule(connector, raw["tool"]) is not None
        multiplexed = bool(rules.get("param") and rules["param"] in props) or theo_lenh
        cls = ("read" if multiplexed and not theo_lenh
               else mcp_catalog.classify(connector, raw["tool"], None))
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

    b_tools, b_route = await asyncio.to_thread(
        _builtin_tools, mode, vault_root, include_ambient, hidden, lang, staging,
        bo_qua, workspace_root=workspace_root, coding_ctx_cua_phien=coding_ctx_cua_phien)
    tools_spec += b_tools
    route.update(b_route)

    # PLUGIN: tool do plugin đăng ký (bundled + vault) → mọi engine, tôn trọng min_mode.
    # Trùng tên tool đã có (MCP/builtin) → BỎ QUA (không cho plugin shadow tool lõi).
    try:
        import plugins_host
        if include_plugins:
            p_tools, p_route = await asyncio.to_thread(plugins_host.plugin_tools, mode, vault_root)
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

    # Owner-only tools leave a bot's list BEFORE the lazy tier, or `javis_run_tool` would still dispatch them.
    if for_bot:
        tools_spec = [t for t in tools_spec if t.get("fn") not in OWNER_ONLY_TOOLS]
        for fn in OWNER_ONLY_TOOLS:
            route.pop(fn, None)

    # Snapshot ĐẦY ĐỦ trước lazy cho Capability Registry Phase 2. Registry chỉ dùng metadata;
    # model vẫn nhận đúng danh sách sau lazy như trước.
    inventory_tools = list(tools_spec)
    inventory_route = dict(route)

    # LAZY: đông tool MCP thì giấu pool sau meta-tool search/run (giữ full route để dispatch).
    # Đặt SAU builtin+plugin để chúng luôn hiện; cache lưu bản ĐÃ biến đổi (route lazy vẫn dispatch
    # được vì _run đóng gói route đầy đủ). Đổi setting → làm mới theo TTL cache (60s) hoặc invalidate.
    tools_spec, route = _apply_lazy(tools_spec, route, include_ambient, hidden, force=force_lazy)
    if task_scope is not None:
        if current(vault_root) is not task_scope or _cache_epoch != epoch:
            raise ScopeUnavailable('task_skill_discovery_changed')
        task_scope.manifests(lang)
    elif _cache_epoch != epoch:
        # invalidate_cache() ran while this dial was out (0.382.0: a background refresh makes that likelier): the
        # list may predate the change, so hand it to this caller only and do not store it.
        return tools_spec, route
    cache[key] = {"tools": tools_spec, "route": route, "ts": time.time(), "mtime": mt, 'epoch': epoch,
                   "ttl": _CACHE_TTL_THIEU if bo_qua else _CACHE_TTL,
                   "inventory_tools": inventory_tools, "inventory_route": inventory_route}
    return tools_spec, route


def registry_inventory(mode="full", vault_root=None, include_plugins=True, include_ambient=False,
                       force_lazy=False, staging=False, workspace_root=None, coding_ctx_cua_phien=None):
    """Trả snapshot pre-lazy đã cache; không discover I/O và không lộ ra model."""
    key = ((mode or "full").strip().lower(), str(vault_root or ""),
           bool(include_plugins), bool(include_ambient), bool(force_lazy), bool(staging))
    from improvement_task_skill_scope import current
    task_scope = current(vault_root or '')
    if task_scope is not None:
        try:
            import localefmt
            lang = localefmt.ngon_ngu_tra_loi()
        except Exception:
            lang = ''
        task_scope.manifests(lang)
        key = ((mode or 'full').strip().lower(), str(vault_root or ''), bool(include_plugins),
            bool(include_ambient), bool(force_lazy), lang, bool(staging), _ten_goc(workspace_root),
            getattr(coding_ctx_cua_phien, 'permission_mode', '') or '', False,
            str((getattr(coding_ctx_cua_phien, 'session_id', '') if workspace_root else '') or ''))
        ent = task_scope._hub_cache.get(key) or {}
        if ent.get('epoch') != _cache_epoch:
            ent = {}
    else:
        ent = _cache.get(key) or {}
    return list(ent.get("inventory_tools") or ent.get("tools") or []), dict(
        ent.get("inventory_route") or ent.get("route") or {}
    )


def invalidate_cache():
    """Gọi sau khi thêm/sửa/xoá connection - làm mới tool list + đóng session cũ."""
    global _cache_epoch
    _cache_epoch += 1
    _cache.clear()
    _ambient_cache["ts"] = 0.0   # ép nạp lại danh sách connector tài khoản ở lần discover kế
    try:
        for c in mcp_store.list_connections():
            # A session still in its first package download is closed as soon as its handshake
            # is over, not now: killing it mid-install leaves a half-installed npx folder that npx
            # reuses forever. The new credentials or the disabled state apply right after.
            mcp_client.pool.invalidate(c["id"], defer_if_starting=True)
    except Exception:
        pass


# ============================================================
# HTTP endpoint /hub/mcp (main.py mount) - Streamable HTTP tối giản
# ============================================================
def _rpc_error(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


# ============================================================
# Brain (vault) của một lượt gọi hub
# ============================================================
# Sự cố 2026-09-21: hub chỉ biết brain qua header `X-Javis-Vault`, mà chỗ DUY NHẤT ghi header
# đó là khi CHÍNH Javis khởi động tiến trình engine (`codex_vault_override` nhét vào argv `-c`,
# Claude/Antigravity/Grok ghi file cấu hình riêng từng lượt). Profile dùng chung
# `~/.codex/<tên>.config.toml` thì CỐ Ý không mang header, vì nhét vào file dùng chung sẽ race
# khi hai brain chạy đồng thời. Hệ quả không ai lường: mọi phiên Codex NGƯỜI DÙNG tự mở đều tới
# hub với vault rỗng, và `javis_task`/`javis_schedule`/`javis_workflow` fail-closed với câu
# "chưa biết đang làm việc trên brain nào" - đúng, nhưng vô phương chẩn đoán từ phía client.
#
# Luật fail-closed sinh ra để chặn một chuyện CỤ THỂ: chạy nhầm sang brain của người khác. Nó
# không đòi phải câm. Nên chỗ này suy ra brain đang mở, và đổi lại thì NÓI RA: mọi kết quả tool
# đi theo đường suy-ra đều kèm một dòng ghi rõ đang chạy brain nào. Chạy nhầm brain mà người
# dùng nhìn thấy ngay ở câu trả lời thì không còn là chạy nhầm im lặng nữa.
_BRAIN_CACHE = {"ts": 0.0, "root": "", "nguon": ""}
_BRAIN_TTL = 10.0     # đủ ngắn để đổi brain ở dashboard có hiệu lực gần như tức thì


def _brains_dir() -> Path:
    """Thư mục CHA chứa mọi brain (mỗi folder con = 1 brain).

    Suy y hệt `main.BRAINS_DIR` nhưng KHÔNG import main: main import mcp_hub, nên chiều ngược
    lại là vòng tròn. Đọc env ở MỖI lần gọi (không cache vào hằng số module) để test đổi
    BRAINS_DIR giữa chừng vẫn đúng.
    """
    return Path(os.getenv("BRAINS_DIR", str(Path(__file__).parent.parent / "brains")))


def _brain_duy_nhat() -> str:
    """Đường dẫn brain DUY NHẤT trên máy, hoặc "" nếu có 0 hay nhiều hơn 1.

    Đây là ca không thể nhầm: không có brain nào khác để mà nhầm sang. Dùng cho máy vừa cài,
    chưa chat lượt nào nên chưa suy được brain đang mở."""
    try:
        ds = [d for d in sorted(_brains_dir().iterdir())
              if d.is_dir() and not d.name.startswith(".")]
    except OSError:
        return ""
    if len(ds) != 1:
        return ""
    try:
        return str(ds[0].resolve())
    except OSError:
        return str(ds[0])


def _brain_tu_phien(ung) -> str:
    """Đường dẫn tuyệt đối của brain ghi trong cột `sessions.brain`, hoặc "" nếu không dám tin.

    Cột đó KHÔNG luôn là đường dẫn: phiên tạo trước 0.43.1, hay phiên mà dashboard tạo sớm qua
    /sessions/{id}/model|project, giữ nguyên tên gọi tắt "brain" của brain mặc định (app.js::
    currentBrainPath). Kiểm nó như đường dẫn thô thì "brain" không resolve được (#610), còn một
    giá trị TƯƠNG ĐỐI như "." resolve theo cwd của tiến trình thành /app hay gốc repo - một thư
    mục có thật nhưng không phải brain nào cả, tức đúng kiểu chạy nhầm brain mà luật fail-closed
    sinh ra để chặn. Nên: "brain" -> Brain Default (cùng quy ước `main._brain_root`), đường dẫn
    TUYỆT ĐỐI có thật -> chính nó, mọi thứ khác -> "" để rơi về các nấc suy luận sau.
    """
    raw = str(ung or "").strip()
    if not raw:
        return ""
    if raw == "brain":
        p = _brains_dir() / "Brain Default"
    else:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            return ""
    try:
        return str(p.resolve()) if p.is_dir() else ""
    except OSError:
        return ""


def quen_brain_dang_mo() -> None:
    """Xoá cache brain đang mở. Gọi sau khi đổi brain nếu cần hiệu lực ngay (test dùng)."""
    _BRAIN_CACHE.update({"ts": 0.0, "root": "", "nguon": ""})


def _brain_dang_mo() -> tuple:
    """(đường_dẫn, nguồn) brain suy ra được. ("", "") nghĩa là không suy được."""
    now = time.time()
    if now - _BRAIN_CACHE["ts"] < _BRAIN_TTL:
        return _BRAIN_CACHE["root"], _BRAIN_CACHE["nguon"]
    root, nguon = "", ""
    try:
        import sessions
        ung = _brain_tu_phien(sessions.get_store().brain_gan_nhat())
        if ung:
            root, nguon = ung, "phien"
    except Exception as e:
        print(f"[hub brain] {type(e).__name__}: {e}", file=sys.stderr)
    if not root:
        mot = _brain_duy_nhat()
        if mot:
            root, nguon = mot, "duy-nhat"
    _BRAIN_CACHE.update({"ts": now, "root": root, "nguon": nguon})
    return root, nguon


def resolve_vault(raw_vault):
    """(vault_root, nguồn, header_hỏng) cho một lượt gọi hub.

    nguồn: "header" (client gửi đúng) | "phien" (brain đang mở) | "duy-nhat" (máy chỉ có một
    brain) | "" (chịu, không suy được). `header_hỏng` khác rỗng nghĩa là client CÓ gửi header
    nhưng nó không trỏ tới thư mục có thật - phải nói ra, vì im lặng bỏ qua một header sai
    chính là kiểu hỏng khó truy nhất (client tin là mình đã gửi rồi).
    """
    raw = (raw_vault or "").strip()
    header_hong = ""
    if raw:
        # Ba cách đọc, nguyên văn trước: đường dẫn ASCII như cũ; dạng mã hoá phần trăm (Codex
        # gửi brain tên có dấu như vậy, xem `ma_hoa_vault`); và UTF-8 thô mà Starlette đã giải
        # thành latin-1, trường hợp một client khác gửi thẳng byte UTF-8 trong header.
        ung = [raw, unquote(raw)]
        try:
            ung.append(raw.encode("latin-1").decode("utf-8"))
        except Exception:
            pass
        for thu in dict.fromkeys(ung):
            try:
                p = Path(thu).expanduser().resolve()
                if p.is_dir():
                    return str(p), "header", ""
            except Exception:
                pass
        header_hong = raw
    root, nguon = _brain_dang_mo()
    return (root or None), (nguon if root else ""), header_hong


_NGUON_CHU = {"phien": "brain đang mở (cuộc trò chuyện gần nhất)",
              "duy-nhat": "brain duy nhất trên máy này"}


def _ten_hien_brain(vault_root) -> str:
    """Tên hiển thị của brain (0.219.0, brain_label), rơi về tên thư mục nếu không đọc được."""
    try:
        import brain_label
        return brain_label.display(vault_root)
    except Exception:
        return Path(vault_root).name


def _ghi_chu_brain(nguon, vault_root, header_hong):
    """Dòng gắn vào kết quả tool để người dùng luôn biết lượt đó chạy trên brain nào."""
    if nguon not in _NGUON_CHU:
        return ""
    ra = (f"(Javis đang làm việc trên brain \"{_ten_hien_brain(vault_root)}\" - {vault_root}. "
          f"Lượt gọi này tới hub không kèm header X-Javis-Vault nên hub lấy "
          f"{_NGUON_CHU[nguon]}. Muốn brain khác thì đổi brain trên dashboard, hoặc thêm "
          f"header X-Javis-Vault vào cấu hình MCP của client.)")
    if header_hong:
        ra = (f"(Header X-Javis-Vault có gửi nhưng trỏ vào \"{header_hong}\" - đường dẫn này "
              f"không có thật trên máy chủ nên hub không dùng được.) ") + ra
    return ra


def _chan_doan_thieu_brain(header_hong):
    """Phần đuôi gắn vào lỗi khi hub không suy ra nổi brain nào. Phải nêu ĐÍCH DANH thứ còn
    thiếu và ai gây ra nó, vì đứng từ phía client thì lỗi gốc nói y như một lỗi cấu hình máy."""
    dau = ""
    if header_hong:
        dau = (f"Header X-Javis-Vault có gửi nhưng trỏ vào \"{header_hong}\", đường dẫn này "
               f"không có thật trên máy chủ. ")
    return ("\n\n(CHẨN ĐOÁN: " + dau + "lượt gọi này tới hub không mang brain nào, và Javis "
            "cũng chưa suy ra được brain đang mở (chưa có cuộc trò chuyện nào, mà thư mục "
            f"{_brains_dir()} đang có nhiều hơn một brain nên hub không đoán bừa). Thiếu header "
            "là chuyện của cấu hình MCP phía client: Javis chỉ tự gắn X-Javis-Vault khi CHÍNH "
            "nó khởi động engine, còn phiên Codex do người dùng tự mở thì dùng profile chung "
            "vốn không mang header. Cách chữa: chat một lượt ở dashboard để Javis biết brain "
            "đang mở, hoặc thêm \"X-Javis-Vault\" = \"<đường dẫn brain>\" vào http_headers của "
            "server javis trong cấu hình MCP.)")


async def _handle_one(msg, mode, include_plugins=True, include_ambient=False, vault_root=None,
                      vault_nguon="", vault_header_hong="", for_bot=False):
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
    # Hub chỉ khai năng lực `tools`, nên theo đúng spec thì client KHÔNG được hỏi resources/
    # prompts. Nhiều client vẫn hỏi, và trả -32601 cho chúng là cách nhanh nhất để bị coi là
    # "server không tuân thủ" rồi bị đóng kết nối - đúng hạng lỗi issue #71 của antigravity-cli
    # mô tả (tool thấy đủ nhưng gọi thì báo "not enabled for server"). Trả danh sách RỖNG vừa
    # đúng sự thật vừa không cho ai cái cớ đóng kết nối.
    if method in ("resources/list", "resources/templates/list", "prompts/list"):
        khoa = {"resources/list": "resources", "resources/templates/list": "resourceTemplates",
                "prompts/list": "prompts"}[method]
        return {"jsonrpc": "2.0", "id": mid, "result": {khoa: []}}
    if method == "tools/list":
        tools, _ = await discover_all(mode, vault_root=vault_root, include_plugins=include_plugins,
                                      include_ambient=include_ambient,
                                      for_bot=for_bot)   # Claude/Codex có tool file native → không builtin file
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": t["fn"], "description": (t.get("description") or t["fn"]),
             "inputSchema": t.get("schema") or {"type": "object", "properties": {}}}
            for t in tools]}}
    if method == "tools/call":
        _, route = await discover_all(mode, vault_root=vault_root, include_plugins=include_plugins,
                                      include_ambient=include_ambient, for_bot=for_bot)
        name = params.get("name") or ""
        result = str(await mcp_client.call_route(route, name, params.get("arguments") or {}))
        ghi_chu = _ghi_chu_brain(vault_nguon, vault_root, vault_header_hong)
        if ghi_chu:
            result += "\n\n" + ghi_chu
        elif not vault_root and result.startswith("ERROR:"):
            # Không suy ra nổi brain: chỉ gắn chẩn đoán vào LỖI, để tool không cần brain
            # (POS, Gmail...) không phải gánh một đoạn văn không liên quan.
            result += _chan_doan_thieu_brain(vault_header_hong)
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": result}],
            "isError": result.startswith("ERROR:"),
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
    # Header chỉ nhận đường dẫn thư mục có thật; thiếu header thì `resolve_vault` suy ra brain
    # đang mở rồi NÓI RA ở kết quả tool (xem khối chú thích ở `_brain_dang_mo`). Bearer
    # hub_token vẫn là lớp auth bắt buộc phía trên.
    # A dedicated bot's Claude Code config carries X-Javis-Bot: 1 (see `claude_config_path(bot=True)`), so the hub
    # hides OWNER_ONLY_TOOLS from it. The header can only take tools AWAY; leaving it out grants nothing new.
    for_bot = (request.headers.get("x-javis-bot") or "").strip() == "1"
    # Who is talking (`turn` for tool hooks). The CLI engine of a chat turn sends the opaque key
    # that turn issued; the header names nobody by itself, so a forged or stale key is just None.
    # ALWAYS bind, even to None: this request must never inherit a turn from whatever context
    # the server happens to run it in.
    tok = turn_context.bind(turn_context.resolve_key(request.headers.get(turn_context.HEADER.lower())))
    # CLI engines also load skills natively from `.claude/skills`; an improvement overlay served only
    # through this tool would split one turn across two versions, so these requests see canonical skills.
    import improvement_activation
    try:
        with improvement_activation.cli_transport():
            return await tra_loi_jsonrpc(request, mode, include_plugins=include_plugins,
                                         include_ambient=include_ambient,
                                         raw_vault=request.headers.get("x-javis-vault"), for_bot=for_bot)
    finally:
        turn_context.reset(tok)


async def _handle_one_traced(msg, *args, **kwargs):
    """`_handle_one` plus a trace of the startup requests (initialize, tools/list).

    A Claude Code startup timeout reads this trace to tell "Claude never reached the hub" from
    "the hub answered late". See hub_trace."""
    ev = hub_trace.begin(msg.get("method") if isinstance(msg, dict) else None)
    try:
        return await _handle_one(msg, *args, **kwargs)
    finally:
        hub_trace.end(ev)


async def tra_loi_jsonrpc(request, mode, include_plugins=True, include_ambient=False,
                          raw_vault=None, for_bot=False):
    """Đọc thân JSON-RPC của `request`, chạy qua hub, trả Response. KHÔNG xác thực gì cả.

    Tách khỏi `handle_http` để một cửa khác (ví dụ plugin tự lo OAuth qua `register_http`) đi
    ĐÚNG đường này - cùng danh sách tool, cùng mức quyền ép ở lớp cứng, cùng chú thích brain -
    và chỉ khác lớp xác thực phía trước. Hai bản chép của cùng một vòng xử lý là hai chỗ để
    lệch nhau.
    """
    vault_root, vault_nguon, vault_header_hong = resolve_vault(raw_vault)
    # "read_docs" opens documents of ONE brain, the bot's, named by the X-Javis-Vault header Javis
    # writes into the bot's config. Without a valid header `resolve_vault` would fall back to the
    # brain the owner has open, i.e. hand a stranger the owner's documents. No header, no tools.
    if (mode or "").strip().lower() == chatbot_doc_tools.MODE and vault_nguon != "header":
        vault_root = None
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(_rpc_error(None, -32700, "parse error"), status_code=400)
    try:
        if isinstance(body, list):
            out = [r for r in [await _handle_one_traced(m, mode, include_plugins, include_ambient,
                                                        vault_root, vault_nguon, vault_header_hong,
                                                        for_bot=for_bot)
                               for m in body] if r is not None]
            if not out:
                return Response(status_code=202)
            return JSONResponse(out)
        res = await _handle_one_traced(body, mode, include_plugins, include_ambient, vault_root,
                                       vault_nguon, vault_header_hong, for_bot=for_bot)
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


def claude_config_path(mode="full", vault_root=None, bot=False):
    """Ghi file --mcp-config 1 entry 'javis'. 0 connection bật → None (giữ hành vi cũ:
    không config → Claude dùng MCP sẵn của máy).

    `vault_root` gắn thêm header X-Javis-Vault, tức hub cấp CẢ nhóm tool file
    (javis_read_file/javis_write_file/javis_use_skill) và khoá chúng vào đúng brain đó qua
    `_safe_path`. Mặc định KHÔNG gắn, và đó là chủ ý: engine Claude bình thường đã có Read/
    Write native nên thêm nhóm này chỉ tạo hai bộ tool trùng chức năng.

    Chỗ cần nó là đường Claude bị CHẶN tool native - bot chuyên trách ở mức Được ghi/Toàn
    quyền. Bot không được chạm Read/Write của Claude Code (nó nhận đường dẫn tuyệt đối, trèo
    ra khỏi brain được), nên tool file phải đi qua hub để `_safe_path` chặn.

    `bot=True` (0.77.0) adds X-Javis-Bot: 1 so the hub hides OWNER_ONLY_TOOLS, and writes a separate file (suffix
    `_bot`) so the owner's own config for the same brain never carries the header.

    File tách riêng theo brain (hậu tố băm) vì đây là file DÙNG CHUNG cho mọi phiên: hai bot
    hai brain chạy cùng lúc mà ghi chung một file là brain nọ đọc header của brain kia.
    """
    mode = (mode or "full").strip().lower()
    # The "read_docs" bot level needs no connection at all: its tools come from the bot's own brain.
    if not _has_connections() and mode != chatbot_doc_tools.MODE:
        return None
    headers = {"Authorization": f"Bearer {hub_token()}", "X-Javis-Mode": mode,
               "X-Javis-Engine": "claude"}
    hau_to = ""
    if vault_root:
        try:
            vault = str(Path(vault_root).expanduser().resolve())
        except Exception:
            vault = str(vault_root)
        headers["X-Javis-Vault"] = vault
        hau_to = "_" + hashlib.sha1(vault.encode("utf-8")).hexdigest()[:10]
    if bot:
        headers["X-Javis-Bot"] = "1"
        hau_to += "_bot"
    p = STATE_DIR / f".mcp_hub_{mode}{hau_to}.json"
    # X-Javis-Engine=claude: báo hub đây là engine Claude (có tool native mcp__* của connector
    # tài khoản Claude) → javis_connections/lazy search kèm gợi ý ambient. Codex/engine API không gắn.
    p.write_text(json.dumps({"mcpServers": {"javis": {
        "type": "http", "url": hub_url(), "headers": headers,
    }}}, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(p, 0o600)   # file chứa hub token - siết như .hub_token
    except Exception:
        pass
    return str(p)


def antigravity_config_path(mode="full", vault_root=None):
    """File mcp_config RIÊNG cho một lượt `agy`, tách theo brain (hậu tố băm như Claude).

    Chỉ có tác dụng nếu bản `agy` trên máy khai một cờ nhận file cấu hình - `AntigravityCLI.
    _build_args` hỏi `co_co()` rồi mới truyền. Vì sao vẫn ghi dù chưa chắc dùng được: cấu hình
    HOME mà `agy` thật sự nạp là file DÙNG CHUNG, nên hai brain chạy đồng thời sẽ ghi đè header
    X-Javis-Vault của nhau. Bên Codex chỗ này chữa bằng override argv; ở đây file per-brain là
    thứ tương đương, và nó nằm sẵn đó cho ngày cờ kia có thật.

    Hình dạng entry lấy từ `antigravity_cli.hub_entry` - KHÔNG viết tay `httpUrl` như bên Gemini.
    """
    mode = (mode or "full").strip().lower()
    headers = {"Authorization": f"Bearer {hub_token()}", "X-Javis-Mode": mode}
    hau_to = ""
    if vault_root:
        try:
            vault = str(Path(vault_root).expanduser().resolve())
        except Exception:
            vault = str(vault_root)
        headers["X-Javis-Vault"] = vault
        hau_to = "_" + hashlib.sha1(vault.encode("utf-8")).hexdigest()[:10]
    try:
        import antigravity_cli
        entry = antigravity_cli.hub_entry(hub_url(), headers)
    except Exception:
        entry = {"serverUrl": hub_url(), "url": hub_url(), "headers": headers, "disabled": False}
    p = STATE_DIR / f".mcp_agy_{mode}{hau_to}.json"
    p.write_text(json.dumps({"mcpServers": {"javis": entry}}, ensure_ascii=False),
                 encoding="utf-8")
    try:
        os.chmod(p, 0o600)   # chứa hub token
    except Exception:
        pass
    return str(p)


def _toml_str(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def codex_profile_name():
    """Tên profile Codex của BẢN NÀY (file `~/.codex/<tên>.config.toml`).

    Vì sao không phải hằng số "javis": nhiều bản Javis cài native trên cùng một VPS chạy chung
    một user, tức chung `$HOME`. Tên cố định là bản khởi động sau ghi đè profile của bản trước,
    mà profile đó chứa URL + token của hub, nên Codex của bản A quay sang gọi hub của bản B - sai
    im lặng, không lỗi nào hiện ra. Gắn cổng vào tên là hết đụng (Docker thì mỗi container một
    HOME nên vốn đã không dính).

    Cổng mặc định giữ nguyên tên "javis" để máy đang chạy không phải sinh file mới.
    """
    p = hub_port()
    return "javis" if p == 7777 else f"javis-{p}"


def codex_profile_path():
    return Path.home() / ".codex" / f"{codex_profile_name()}.config.toml"


def codex_profile(mode="full"):
    """Ghi ~/.codex/<profile>.config.toml 1 entry hub → `codex exec -p <profile>` thấy MỌI MCP của Javis."""
    path = codex_profile_path()
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
        return codex_profile_name()
    except Exception as e:
        print(f"[hub codex profile] {e}", file=sys.stderr)
        return None


# Tiền tố của override brain. KHÔNG được bọc tên header trong dấu nháy: Codex tách khoá của
# `-c` bằng `path.split('.')` (codex-rs/config/src/overrides.rs, apply_toml_override) và giữ
# NGUYÊN dấu nháy, nên `http_headers."X-Javis-Vault"` thành header tên `"X-Javis-Vault"` - có
# cả hai dấu nháy. Đó không phải tên header HTTP hợp lệ, và rmcp-client của Codex bỏ qua nó
# với đúng một dòng warn (rmcp-client/src/utils.rs, build_default_headers). Hub không bao giờ
# nhận được brain, rơi về "phiên cập nhật gần nhất" của CẢ MÁY - sự cố 27/09/2026: dashboard
# đang ở My Bullet Journal mà lệnh tạo đơn TTS chạy trên brain Ngọc Thu Phạm.
CODEX_VAULT_KEY = "mcp_servers.javis.http_headers.X-Javis-Vault"


def ma_hoa_vault(vault: str) -> str:
    """Giá trị header CHỈ được là ASCII: rmcp-client dựng header bằng `HeaderValue::from_str`,
    hàm này từ chối ký tự ngoài ASCII, và brain tên tiếng Việt ("Ngọc Thu Phạm") thì đường
    dẫn có dấu. Mã hoá phần trăm; hub thử nguyên văn trước rồi mới giải mã (`resolve_vault`)."""
    return vault if vault.isascii() else quote(vault, safe="/:\\ ")


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
    return f"{CODEX_VAULT_KEY}={_toml_str(ma_hoa_vault(vault))}"


CODEX_MODE_KEY = "mcp_servers.javis.http_headers.X-Javis-Mode"
_CODEX_MODES = ("suggest", "auto", "full", "gated")


def dat_codex_mode(extra_config, mode):
    """Pin the hub permission level of ONE Codex process with a `-c` override, replacing any earlier one.

    The shared Codex profile is written with `X-Javis-Mode: full` (the chat path). Before 0.117.0 a
    background job at suggest or auto (reminder, loop, Kanban) reached hub tools at FULL through that
    profile, while Grok and Antigravity already got the job's own level. An unknown level falls back to
    the strictest one, as every other mode mapping here does."""
    m = str(mode or "full").strip().lower()
    if m not in _CODEX_MODES:
        m = "suggest"
    extra_config[:] = [x for x in extra_config if not str(x).startswith(CODEX_MODE_KEY + "=")]
    extra_config.append(f"{CODEX_MODE_KEY}={_toml_str(m)}")
    return extra_config


def dat_codex_vault(extra_config, vault_root):
    """Gắn override brain vào danh sách `-c` của MỘT CodexCLI, THAY override brain cũ nếu có.

    Engine Telegram giữ nguyên một CodexCLI qua nhiều lượt. Chỉ nối thêm khi chuỗi chưa có thì
    đổi brain A -> B -> A để lại cả [A, B] trong argv, và Codex lấy giá trị đứng sau: lượt đang
    ở A vẫn chạy trên B. Bỏ cả dạng cũ có dấu nháy để bản vá này không để lại rác."""
    cu = (CODEX_VAULT_KEY + "=", 'mcp_servers.javis.http_headers."X-Javis-Vault"=')
    extra_config[:] = [x for x in extra_config if not str(x).startswith(cu)]
    override = codex_vault_override(vault_root)
    if override:
        extra_config.append(override)
    return extra_config


# Việc nền theo lịch chạy trên Codex: hub là server BẮT BUỘC.
#
# Codex 0.161.0 chụp danh sách tool của lượt và chỉ chờ một server MCP không `required` tới
# `mcp_optional_startup_grace_ms`, mặc định 1 giây; quá hạn là cả server bị bỏ khỏi lượt đó
# (codex-mcp/src/connection_manager/tool_catalog.rs). Hub trả `tools/list` qua `discover_all`,
# cache 60 giây hết hạn là dò lại mọi connector, mất khoảng 2 giây. Hai con số đua nhau nên việc
# nền lúc có tool hub lúc không (canary 08-09/10/2026: 4 trên 12 lượt nhắc hẹn không thấy
# `mcp__javis__*`), model đi vòng qua app ChatGPT hoặc báo không làm được mà nhắc hẹn vẫn ghi xong.
# `required = true` bắt Codex chờ hub tới `startup_timeout_sec` của profile; hub không lên thì
# phiên không mở và `codex exec` thoát lỗi TRƯỚC khi gọi model (core/src/session/session.rs); câu
# lỗi đó do claude_cli.codex_error_text đọc. Chỉ gắn khi profile hub có mặt: override vào
# `mcp_servers.javis` mà thiếu entry đó thì Codex từ chối khởi động ("invalid transport").
CODEX_REQUIRED_KEY = "mcp_servers.javis.required"
# `features.apps = false` gỡ hẳn server `codex_apps` (app ChatGPT gắn với tài khoản,
# codex-mcp/src/mcp/mod.rs). Tool của nó không đi qua hub nên không chịu mức quyền của việc, và
# là đường vòng model từng chọn cả khi hub có mặt (canary 08/10/2026).
CODEX_APPS_KEY = "features.apps"


def dat_codex_hub_bat_buoc(extra_config):
    """Gắn `required = true` cho entry hub vào `-c` của MỘT CodexCLI, THAY bản cũ nếu có."""
    extra_config[:] = [x for x in extra_config if not str(x).startswith(CODEX_REQUIRED_KEY + "=")]
    extra_config.append(f"{CODEX_REQUIRED_KEY}=true")
    return extra_config


def dat_codex_team_gated(extra_config):
    """0.207.0: one Codex process of a GATED Team step (team_gate.py): hub level `gated` (the gate decides outside
    actions), no ChatGPT apps (they bypass the hub) and no shell network in its workspace sandbox, whatever the user's
    own Codex config says. Chat and workflow Codex processes never get this."""
    dat_codex_mode(extra_config, "gated")
    dat_codex_tat_app(extra_config)
    extra_config[:] = [x for x in extra_config if not str(x).startswith("sandbox_workspace_write.network_access=")]
    extra_config.append("sandbox_workspace_write.network_access=false")
    return extra_config


def dat_codex_tat_app(extra_config):
    """Tắt app ChatGPT (`codex_apps`) cho MỘT CodexCLI, THAY bản cũ nếu có."""
    extra_config[:] = [x for x in extra_config if not str(x).startswith(CODEX_APPS_KEY + "=")]
    extra_config.append(f"{CODEX_APPS_KEY}=false")
    return extra_config


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
    return chan_doan_loi(err, conn_id) or (
        localefmt.chu("Key chưa đúng hoặc chưa đủ quyền: ", "The key is wrong or lacks permission: ")
        + (err or "").strip()[:200])


async def validate_connection(conn_id):
    """Gọi thử connection: đếm tool + (nếu catalog khai validate) lấy label tên shop.
    Trả {ok, label, tools, error}."""
    conn = next((c for c in mcp_store.resolved(enabled_only=False) if c["id"] == conn_id), None)
    if not conn:
        return {"ok": False, "label": "", "tools": 0,
                "error": localefmt.chu("Không tìm thấy kết nối", "Connection not found")}
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
                        "error": localefmt.chu(
                            "Đăng nhập rồi nhưng token thiếu quyền: "
                            + ", ".join(oauth_mcp.short_scopes(rep["missing"]))
                            + ". Bấm Đăng nhập lại và tick đủ mọi ô quyền." + REVOKE_HINT,
                            "Signed in, but the token is missing permissions: "
                            + ", ".join(oauth_mcp.short_scopes(rep["missing"]))
                            + ". Press Sign in again and tick every permission box."
                            " If Google shows no permission boxes when you sign in again, that is"
                            " normal: permissions already granted are passed straight through. To"
                            " tick them again from scratch, remove Javis at"
                            " https://myaccount.google.com/permissions and then Connect again.")}
        except Exception as e:
            print(f"[hub scope] {e}", file=sys.stderr)
    spec = mcp_client._conn_spec(conn)
    try:
        spec["headers"].update(await mcp_client._oauth_headers(conn))
        tools = await mcp_client.pool.list_tools(spec)
    except Exception as e:
        if conn.get("connector_id") == "composio":
            import connect_health
            kind, msg = connect_health.classify_error(f"{type(e).__name__}: {e}", conn)
            if kind == "auth":
                return {"ok": False, "label": "", "tools": 0, "error": msg}
        # Kèm nội dung lỗi thật: chỉ tên loại (vd "ValueError") thì không lần ra manh mối.
        # Giữ ĐUÔI chứ không giữ đầu: traceback Python để nguyên nhân ở dòng CUỐI, mà một
        # dòng "File .../.cache/uv/..." đã ~135 ký tự nên cắt [:160] từ đầu là NUỐT đúng
        # dòng "ModuleNotFoundError: ..." với mọi lỗi import của gói chạy qua uvx.
        chi_tiet = str(e)
        if len(chi_tiet) > 400:
            chi_tiet = "..." + chi_tiet[-400:]
        # Crash vì phụ thuộc của gói MCP thì bảo đi kiểm key là dẫn user đi sai hướng
        # có hệ thống (họ sẽ tạo lại key/service account mãi mà không bao giờ ra).
        la_loi_goi = any(k in chi_tiet for k in (
            "ModuleNotFoundError", "ImportError", "Traceback", "No module named"))
        goi_y = (localefmt.chu(
                    "Gói MCP này hỏng phụ thuộc - lỗi nằm ở gói, KHÔNG phải key của bạn. "
                    "Cần ghim phiên bản thư viện trong lệnh chạy (vd uvx --with 'mcp<2' ...).",
                    "This MCP package has a broken dependency - the fault is in the package, NOT your key. "
                    "Pin the library version in the run command (e.g. uvx --with 'mcp<2' ...).")
                 if la_loi_goi else localefmt.chu("Kiểm tra lại key/URL hoặc thử lại.",
                                                  "Check the key/URL again or try again."))
        return {"ok": False, "label": "", "tools": 0,
                "error": localefmt.chu("Không kết nối được (", "Could not connect (") + type(e).__name__
                         + (": " + chi_tiet if chi_tiet else "")
                         + "). " + goi_y}
    label = ""
    val = (conn.get("connector") or {}).get("validate")
    if val and val.get("tool"):
        res = await mcp_client.pool.call_tool(spec, val["tool"], val.get("args") or {})
        if str(res).startswith("ERROR:"):
            return {"ok": False, "label": "", "tools": len(tools),
                    "error": _friendly_tool_error(str(res)[7:], conn_id)}
        label = _extract_label(str(res), val.get("label_paths"))
    return {"ok": True, "label": label, "tools": len(tools), "error": ""}
