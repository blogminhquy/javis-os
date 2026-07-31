"""
Registry KẾT NỐI MCP của Javis - model v2: connector (mẫu, xem mcp_catalog) ↔ connection (tài khoản).
- File: STATE_DIR/mcp_servers.json (v2). Bản v1 (danh sách server phẳng) tự MIGRATE khi đọc lần đầu,
  bản gốc backup sang mcp_servers.v1.bak.json - không phá dữ liệu cũ.
- Secret (headers/env/fields) mã hoá at rest qua secrets_store.
- GIỮ nguyên bộ hàm legacy (list_servers/add_server/update_server/.../servers_for_client/
  rebuild_config/disallowed_tools) để endpoint /mcp/* cũ và chế độ fallback (không hub) chạy như cũ.
"""
import json
import os
import re
import sys
import threading
import unicodedata
import uuid
from pathlib import Path

import mcp_catalog
import secrets_store
import config as cfgmod
from config import STATE_DIR

# Registry bị ghi từ cả event-loop (endpoint) lẫn thread thường (zalo_login) →
# khoá quanh mọi chu trình load-modify-save để không lost-update.
_LOCK = threading.RLock()

STORE = STATE_DIR / "mcp_servers.json"
_LEGACY_STORE = Path(__file__).parent / "mcp_servers.json"   # vị trí cũ (trước khi theo STATE_DIR)
CONFIG = Path(__file__).parent / ".mcp_config.json"

WRITE_HINTS = mcp_catalog.WRITE_HINTS   # giữ tương thích import cũ


def _slugify(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("đ", "d").replace("Đ", "D")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.strip().lower()).strip("-")
    # Cắt 32 ký tự: slug đi vào tên tool (namespace__tool <= 64) - label shop dài không được
    # nuốt mất phần tên tool (xem _mk_fn bên mcp_client).
    return s[:32].strip("-") or "acc"


# ============================================================
# Load / save / migrate
# ============================================================
def _locked(fn):
    """Bọc chu trình load-modify-save trong _LOCK (RLock nên gọi lồng nhau vô hại)."""
    def wrap(*a, **k):
        with _LOCK:
            return fn(*a, **k)
    wrap.__name__ = fn.__name__
    wrap.__doc__ = fn.__doc__
    return wrap


@_locked
def _load():
    raw = None
    path = STORE if STORE.exists() else (_LEGACY_STORE if _LEGACY_STORE.exists() else None)
    if path:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[mcp_store] lỗi đọc {path.name}: {e}", file=sys.stderr)
            raw = None
    if not raw:
        return {"version": 2, "connections": []}
    if raw.get("version") == 2 and "connections" in raw:
        return raw
    return _migrate_v1(raw, path)


def _migrate_v1(raw, src_path):
    """v1 {"servers":[...]} → v2 connections. Backup bản gốc, chạy đúng 1 lần."""
    conns, taken = [], set()
    for s in raw.get("servers", []) or []:
        cid = mcp_catalog.match_url(s.get("url")) or "custom"
        base = _slugify(s.get("name") or cid)
        slug, i = base, 2
        while (cid, slug) in taken:
            slug = f"{base}-{i}"
            i += 1
        taken.add((cid, slug))
        conns.append({
            "id": s.get("id") or uuid.uuid4().hex[:12],
            "connector_id": cid,
            "label": s.get("name") or cid,
            "slug": slug,
            "transport": s.get("transport") or "http",
            "url": (s.get("url") or "").strip(),
            "command": (s.get("command") or "").strip(),
            "args": s.get("args") or [],
            "headers": secrets_store.encrypt_map(s.get("headers") or {}),
            "env": secrets_store.encrypt_map(s.get("env") or {}),
            "secrets": {},
            "config": {},
            "auth": s.get("auth") or "header",
            "enabled": bool(s.get("enabled")),
            "perm": s.get("perm") if s.get("perm") in mcp_catalog.PERM_RANK else "full",
            "deny_tools": s.get("deny_tools") or [],
            "is_default": False,
        })
    seen = set()
    for c in conns:   # tài khoản đầu tiên của mỗi connector = mặc định
        if c["connector_id"] not in seen:
            c["is_default"] = True
            seen.add(c["connector_id"])
    d = {"version": 2, "connections": conns}
    try:
        if src_path and src_path.exists():
            src_path.replace(src_path.with_name("mcp_servers.v1.bak.json"))
    except Exception as e:
        print(f"[mcp_store] không backup được v1: {e}", file=sys.stderr)
    _save(d)
    print(f"[mcp_store] đã migrate {len(conns)} server v1 → connection v2", file=sys.stderr)
    return d


def _hub_on():
    try:
        return bool(cfgmod.read_settings().get("mcp", {}).get("hub", True))
    except Exception:
        return True


def _save(d):
    with _LOCK:
        STORE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    # Hub bật (mặc định): KHÔNG sinh file fallback .mcp_config.json - file đó chứa header/env
    # ĐÃ GIẢI MÃ (plaintext), để nằm lại là vô hiệu hoá mã hoá at-rest. Xoá bản cũ nếu có.
    if _hub_on():
        try:
            CONFIG.unlink()
        except Exception:
            pass
    else:
        rebuild_config()


def _find(d, cid):
    return next((c for c in d["connections"] if c.get("id") == cid), None)


def _public(c):
    """Bản che secret trả ra frontend (giữ tên key, ẩn giá trị)."""
    h = c.get("headers") or {}
    e = c.get("env") or {}
    s = c.get("secrets") or {}
    return {
        "id": c.get("id"), "connector_id": c.get("connector_id", "custom"),
        "name": c.get("label"), "label": c.get("label"), "slug": c.get("slug", ""),
        "transport": c.get("transport"), "url": c.get("url"), "auth": c.get("auth"),
        "enabled": bool(c.get("enabled")), "perm": c.get("perm") or "full",
        "deny_tools": c.get("deny_tools") or [], "is_default": bool(c.get("is_default")),
        "command": c.get("command", ""), "args": c.get("args") or [],
        "header_keys": list(h.keys()), "env_keys": list(e.keys()), "secret_keys": list(s.keys()),
    }


# ============================================================
# API v2 - connections
# ============================================================
def list_connections():
    return [_public(c) for c in _load()["connections"]]


def get_connection(cid):
    c = _find(_load(), cid)
    return _public(c) if c else None


def connection_secrets(cid):
    """Trả map secrets (fields) ĐÃ GIẢI MÃ của 1 connection - chỉ cho code nội bộ
    (vd oauth_mcp lấy client_id/client_secret BYO). TUYỆT ĐỐI không trả ra frontend."""
    c = _find(_load(), cid)
    return secrets_store.decrypt_map((c or {}).get("secrets") or {})


def reuse_client_fields(target_con, fields, from_cid, keys=("client_id", "client_secret")):
    """Dùng lại key OAuth client từ connection KHÁC, copy hoàn toàn SERVER-SIDE.

    Các connector Google dùng chung được một OAuth client, nên user đã tạo key cho
    Calendar thì Gmail chỉ cần "dùng lại key của Calendar" thay vì làm lại 10 phút.
    Secrets không bao giờ đi qua browser: UI chỉ gửi `reuse_from=<conn_id>`, server
    tự đọc và điền. Chỉ copy key nằm trong danh sách fields của connector ĐÍCH, và
    KHÔNG đè giá trị user đã tự nhập."""
    out = dict(fields or {})
    if not from_cid:
        return out
    allowed = {f.get("key") for f in ((target_con or {}).get("auth") or {}).get("fields", [])}
    src = connection_secrets(from_cid)
    for k in keys:
        if k in allowed and not out.get(k) and src.get(k):
            out[k] = src[k]
    return out


@_locked
def add_connection(connector_id, data):
    """Thêm 1 tài khoản. data: {label?, fields{}, headers{}, env{}, url?, command?, args?,
    transport?, perm?, config{}, auth?, deny_tools?}. Trả (id, None) hoặc (None, "lỗi")."""
    connector_id = (connector_id or "custom").strip() or "custom"
    con = mcp_catalog.get(connector_id)
    if connector_id != "custom" and not con:
        return None, f"Không có connector '{connector_id}' trong kho"
    if con and con.get("status") == "soon":
        return None, "Connector này chưa mở (đang chờ xác minh endpoint)"
    d = _load()
    label = (data.get("label") or "").strip() or (con or {}).get("name") or connector_id
    base = _slugify(label)
    taken = {c["slug"] for c in d["connections"] if c.get("connector_id") == connector_id}
    slug, i = base, 2
    while slug in taken:
        slug = f"{base}-{i}"
        i += 1
    auth = data.get("auth") or ((con or {}).get("auth") or {}).get("type") or "header"
    conn = {
        "id": uuid.uuid4().hex[:12],
        "connector_id": connector_id,
        "label": label,
        "slug": slug,
        "transport": data.get("transport") or (con or {}).get("transport") or "http",
        # url_template ưu tiên hơn url tĩnh: connector self-host lấy địa chỉ từ ô user gõ.
        "url": (data.get("url")
                or mcp_catalog.build_url(con, data.get("fields") or {})
                or (con or {}).get("url") or "").strip(),
        "command": (data.get("command") or (con or {}).get("command") or "").strip(),
        "args": data.get("args") if data.get("args") is not None else list((con or {}).get("args") or []),
        "headers": secrets_store.encrypt_map(data.get("headers") or {}),
        "env": secrets_store.encrypt_map(data.get("env") or {}),
        "secrets": secrets_store.encrypt_map(data.get("fields") or {}),
        "config": data.get("config") or {},
        "auth": auth,
        "enabled": True,
        "perm": data.get("perm") if data.get("perm") in mcp_catalog.PERM_RANK
                else ((con or {}).get("default_perm") or "full"),
        "deny_tools": data.get("deny_tools") or [],
        "is_default": not any(c.get("connector_id") == connector_id for c in d["connections"]),
    }
    d["connections"].append(conn)
    _save(d)
    return conn["id"], None


@_locked
def update_connection(cid, patch):
    """Sửa connection. Secret (fields/headers/env): chỉ ghi đè key CÓ giá trị mới -
    'để trống = giữ key cũ' như UI cũ. label đổi thì slug GIỮ NGUYÊN (tên tool ổn định)."""
    d = _load()
    c = _find(d, cid)
    if not c:
        return False
    for k in ("label", "transport", "url", "command", "auth"):
        if patch.get(k) is not None:
            c[k] = patch[k].strip() if isinstance(patch[k], str) else patch[k]
    if patch.get("name") is not None:   # alias legacy
        c["label"] = str(patch["name"]).strip() or c["label"]
    if patch.get("perm") in mcp_catalog.PERM_RANK:
        c["perm"] = patch["perm"]
    for k in ("args", "deny_tools"):
        if patch.get(k) is not None:
            c[k] = patch[k]
    if patch.get("config") is not None:
        c["config"] = patch["config"]
    if "enabled" in patch and patch["enabled"] is not None:
        c["enabled"] = bool(patch["enabled"])
    doi_dang_nhap = False
    for k, src in (("secrets", "fields"), ("headers", "headers"), ("env", "env")):
        newvals = patch.get(src)
        if newvals:
            merged = dict(c.get(k) or {})
            for kk, vv in newvals.items():
                if vv:   # giá trị rỗng = giữ cũ
                    if k == "secrets" and secrets_store.decrypt(merged.get(kk, "")) != vv:
                        doi_dang_nhap = True
                    merged[kk] = secrets_store.encrypt(vv)
            c[k] = merged
    # Đổi ô đăng nhập (email Google, Client ID/Secret) trên connector TỰ giữ token thì token
    # đang cache thuộc về tài khoản/app CŨ - giữ lại là mọi tool vẫn chạy bằng tài khoản cũ.
    # Vụ thật: user xoá đi đăng nhập lại bằng hi@minhquy.vn mà tool vẫn trả về
    # blogminhquy@gmail.com, vì credential cũ nằm nguyên trên đĩa và không ai dọn.
    if doi_dang_nhap:
        forget_cred_dir(c)
    _save(d)
    return True


def _cred_dir(conn, con=None):
    """{env, path} thư mục token RIÊNG của 1 connection, hoặc None nếu connector không khai.

    Vì sao tồn tại: có connector tự chạy luồng OAuth của nó và cache token ra đĩa NGOÀI tầm với
    của Javis (workspace-mcp). Không tách thư mục thì (1) nhiều tài khoản giẫm lên nhau và
    (2) Javis không có cách nào bắt nó đăng nhập lại."""
    con = con or mcp_catalog.get(conn.get("connector_id"))
    cd = (con or {}).get("cred_dir") or {}
    if not cd.get("env"):
        return None
    slug = conn.get("slug") or conn.get("id") or ""
    return {"env": cd["env"],
            "path": STATE_DIR / "connector-cred" / f"{conn.get('connector_id')}-{slug}"}


def forget_cred_dir(conn):
    """Xoá kho token riêng của 1 connection → lần gọi tool sau connector phải đăng nhập lại.
    Nhận dict connection (hoặc None). Nuốt lỗi: dọn không được cũng không được chặn việc xoá."""
    if not conn:
        return False
    cred = _cred_dir(conn)
    if not cred:
        return False
    try:
        import shutil
        if cred["path"].is_dir():
            shutil.rmtree(cred["path"])
            return True
    except OSError as e:
        print(f"[mcp_store] dọn cred dir: {e}", file=sys.stderr)
    return False


@_locked
def forget_cred_dir_by_id(cid):
    """Bản gọi theo id cho endpoint 'đăng nhập lại' - giữ nguyên connection, chỉ vứt token."""
    return forget_cred_dir(_find(_load(), cid))


@_locked
def delete_connection(cid):
    try:
        for fp in (STATE_DIR / "connector-files").glob(f"{cid}-*"):
            fp.unlink()   # dọn file secret đã materialize (service account JSON...)
    except Exception:
        pass
    d = _load()
    before = len(d["connections"])
    victim = _find(d, cid)
    forget_cred_dir(victim)   # token OAuth connector tự giữ ngoài Javis - xoá kết nối là xoá theo
    d["connections"] = [c for c in d["connections"] if c.get("id") != cid]
    if victim and victim.get("is_default"):   # chuyển default cho tài khoản còn lại cùng connector
        for c in d["connections"]:
            if c.get("connector_id") == victim.get("connector_id"):
                c["is_default"] = True
                break
    _save(d)
    return len(d["connections"]) < before


@_locked
def toggle_connection(cid):
    d = _load()
    c = _find(d, cid)
    if not c:
        return None
    c["enabled"] = not c.get("enabled")
    _save(d)
    return c["enabled"]


@_locked
def set_default(cid):
    d = _load()
    c = _find(d, cid)
    if not c:
        return False
    for x in d["connections"]:
        if x.get("connector_id") == c.get("connector_id"):
            x["is_default"] = (x.get("id") == cid)
    _save(d)
    return True


def resolved(enabled_only=True):
    """Danh sách connection ĐẦY ĐỦ (secret THẬT đã giải mã) cho hub/client nội bộ.
    TUYỆT ĐỐI không trả kết quả hàm này ra frontend.
    Mỗi phần tử: {id, connector_id, label, slug, namespace, transport, url, command, args,
    headers, env, perm, deny_tools, is_default, connector(dict catalog hoặc None)}."""
    d = _load()
    conns = [c for c in d["connections"] if c.get("enabled") or not enabled_only]
    counts = {}
    for c in conns:
        counts[c["connector_id"]] = counts.get(c["connector_id"], 0) + 1
    out = []
    taken_ns = set()
    for c in conns:
        con = mcp_catalog.get(c["connector_id"])
        secrets = secrets_store.decrypt_map(c.get("secrets") or {})
        headers = {}
        if con:
            headers.update(mcp_catalog.build_headers(con, secrets))
        headers.update(secrets_store.decrypt_map(c.get("headers") or {}))
        headers = {k: v for k, v in headers.items() if v}
        if c["connector_id"] == "custom":
            ns = c.get("slug") or _slugify(c.get("label"))
        elif counts[c["connector_id"]] > 1:
            ns = f"{c['connector_id']}-{c.get('slug')}"
        else:
            ns = c["connector_id"]
        if ns in taken_ns:   # vd custom tự đặt tên trùng connector catalog → không cho ghi đè nhau
            base_ns, i2 = ns, 2
            while ns in taken_ns:
                ns = f"{base_ns}-{i2}"
                i2 += 1
        taken_ns.add(ns)
        args = list(c.get("args") or [])
        env = secrets_store.decrypt_map(c.get("env") or {})
        if con:
            for k, v in mcp_catalog.build_env(con, secrets).items():
                env.setdefault(k, v)
        # Connector tự giữ token OAuth RIÊNG bên ngoài Javis (vd workspace-mcp cache ở
        # ~/.google_workspace_mcp/credentials). Để mặc định thì mọi tài khoản dùng chung một
        # kho, và Javis KHÔNG có đường nào dọn - xoá kết nối rồi thêm lại vẫn xài đúng token cũ,
        # nên token thiếu quyền là thiếu mãi mãi (đúng vụ Lịch báo thiếu quyền của người dùng
        # thật: cài lại chục lần vô ích vì lần nào cũng đọc lại credential cũ trên đĩa).
        # Trỏ mỗi connection vào một thư mục riêng thì xoá kết nối là token đi theo, lần gọi
        # tool kế tiếp server tự mở lại màn đăng nhập Google với đúng bộ quyền hiện hành.
        cred = _cred_dir(c, con)
        if cred:
            try:
                cred["path"].mkdir(parents=True, exist_ok=True)
            except OSError as e:
                print(f"[mcp_store] cred dir {cred['path']}: {e}", file=sys.stderr)
            env.setdefault(cred["env"], str(cred["path"]))
        if (con or {}).get("isolate_home"):
            # Connector kiểu zalo-agent-cli: account active là TOÀN CỤC theo home dir
            # → mỗi connection 1 home riêng để nhiều tài khoản chạy song song không giẫm nhau.
            home = (c.get("config") or {}).get("home_dir") or str(
                STATE_DIR / "connector-home" / f"{c['connector_id']}-{c.get('slug')}")
            env.setdefault("HOME", home)
            env.setdefault("USERPROFILE", home)
        # Field dạng FILE (vd service account JSON của Google): nội dung dán khi kết nối
        # (mã hoá trong store) → ghi ra file 0600 riêng, cấp cho tiến trình con qua env đường dẫn.
        for f in (((con or {}).get("auth") or {}).get("fields") or []):
            if not (f.get("file") and f.get("env") and f.get("key")):
                continue
            val = secrets.get(f["key"], "")
            if not val:
                continue
            try:
                fdir = STATE_DIR / "connector-files"
                fdir.mkdir(parents=True, exist_ok=True)
                fp = fdir / f"{c['id']}-{f['key']}{f.get('file_ext', '.json')}"
                try:
                    cur = fp.read_text(encoding="utf-8")
                except OSError:
                    cur = None
                if cur != val:
                    fp.write_text(val, encoding="utf-8")
                    try:
                        os.chmod(fp, 0o600)
                    except Exception:
                        pass
                env[f["env"]] = str(fp)
            except Exception as e:
                print(f"[mcp_store] field file {f['key']}: {e}", file=sys.stderr)
        # Connector STDIO đăng nhập bằng OAuth (vd google-ads): token nằm ở oauth_mcp, nhưng tiến
        # trình con chỉ nhận credential qua FILE + env. Dựng file theo format catalog khai rồi trỏ
        # env vào. KHÔNG ghi đè nếu user đã tự dán file ở vòng trên (đường lui thủ công thắng).
        of = (con or {}).get("oauth_file") or {}
        if of.get("env") and of.get("format") and not env.get(of["env"]):
            try:
                import oauth_mcp   # import TRỄ: oauth_mcp import mcp_store ở cấp module
                blob = oauth_mcp.credentials_file(c["id"], of["format"])
                if blob:
                    fdir = STATE_DIR / "connector-files"
                    fdir.mkdir(parents=True, exist_ok=True)
                    fp = fdir / f"{c['id']}-oauth{of.get('ext', '.json')}"
                    try:
                        cur = fp.read_text(encoding="utf-8")
                    except OSError:
                        cur = None
                    if cur != blob:
                        fp.write_text(blob, encoding="utf-8")
                        try:
                            os.chmod(fp, 0o600)
                        except Exception:
                            pass
                    env[of["env"]] = str(fp)
            except Exception as e:
                print(f"[mcp_store] oauth file {c['id']}: {e}", file=sys.stderr)
        out.append({
            "id": c["id"], "connector_id": c["connector_id"], "label": c.get("label"),
            "slug": c.get("slug"), "namespace": ns,
            "transport": c.get("transport") or "http",
            # Connector khai url_template (server nằm trên tên miền của CHÍNH user, vd n8n tự
            # dựng): dựng lại URL từ secret ở ĐÂY chứ không chỉ lúc thêm, để user sửa ô địa chỉ
            # là kết nối đi theo ngay - y như headers vốn đã dựng lại mỗi lần resolve.
            "url": (mcp_catalog.build_url(con, secrets) if (con or {}).get("url_template")
                    else "") or c.get("url", ""),
            "command": c.get("command", ""), "args": args,
            "headers": headers, "env": env,
            "internal": (con or {}).get("internal") or "",
            "secrets": secrets if (con or {}).get("internal") else {},
            "config": c.get("config") or {},
            "perm": c.get("perm") or "full", "deny_tools": c.get("deny_tools") or [],
            "is_default": bool(c.get("is_default")), "auth": c.get("auth"), "connector": con,
        })
    return out


# ============================================================
# API legacy (endpoint /mcp/* cũ + fallback không hub) - shape như v1
# ============================================================
def list_servers():
    return list_connections()


def add_server(data):
    cid, err = add_connection("custom", {
        "label": (data.get("name") or "").strip(),
        "transport": data.get("transport") or "http",
        "url": data.get("url"), "command": data.get("command"), "args": data.get("args"),
        "headers": data.get("headers"), "env": data.get("env"),
        "auth": data.get("auth") or "header",
        "perm": data.get("perm") if data.get("perm") in mcp_catalog.PERM_RANK else "full",
        "deny_tools": data.get("deny_tools"),
    })
    if err:
        print(f"[mcp_store] add_server: {err}", file=sys.stderr)
    return cid


def update_server(sid, data):
    patch = dict(data or {})
    if patch.get("perm") == "readonly":   # giá trị legacy hợp lệ, giữ nguyên
        pass
    return update_connection(sid, patch)


def delete_server(sid):
    return delete_connection(sid)


def toggle_server(sid):
    return toggle_connection(sid)


def rebuild_config():
    """FALLBACK không-hub: ghi .mcp_config.json 1 entry / connection (bỏ oauth).
    Khi hub bật, main.py dùng mcp_hub.claude_config_path() thay hàm này."""
    servers = {}
    for r in resolved(enabled_only=True):
        if r.get("auth") == "oauth" or not r.get("namespace"):
            continue
        t = r.get("transport") or "http"
        if t in ("http", "sse"):
            if not r.get("url"):
                continue
            entry = {"type": t, "url": r["url"]}
            if r.get("headers"):
                entry["headers"] = r["headers"]
        else:
            if not r.get("command"):
                continue
            entry = {"type": "stdio", "command": r["command"], "args": r.get("args") or []}
            if r.get("env"):
                entry["env"] = r["env"]
        servers[r["namespace"]] = entry
    try:
        if servers:
            CONFIG.write_text(json.dumps({"mcpServers": servers}, ensure_ascii=False), encoding="utf-8")
            try:
                os.chmod(CONFIG, 0o600)   # file chứa key THẬT (đã giải mã) - siết quyền đọc
            except Exception:
                pass
            return str(CONFIG)
        CONFIG.unlink()
    except Exception:
        # server/ read-only (Docker) → fallback legacy không ghi được; hub (STATE_DIR) vẫn chạy
        pass
    return None


def config_path():
    return rebuild_config()


def servers_for_client():
    """Legacy cho MCP client HTTP: connection http/sse đang bật + headers THẬT."""
    out = []
    for r in resolved(enabled_only=True):
        if r.get("auth") == "oauth":
            continue
        if (r.get("transport") or "http") not in ("http", "sse") or not r.get("url"):
            continue
        out.append({"name": r["namespace"], "url": r["url"], "headers": r.get("headers") or {},
                    "transport": r.get("transport") or "http", "deny_tools": r.get("deny_tools") or []})
    return out


def disallowed_tools():
    """Pattern --disallowedTools cho fallback không-hub (hub tự chặn nên không cần)."""
    out = []
    for r in resolved(enabled_only=True):
        for t in (r.get("deny_tools") or []):
            t = (t or "").strip()
            if t:
                out.append(f"mcp__{r['namespace']}__{t}")
    return out
