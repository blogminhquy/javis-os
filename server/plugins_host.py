"""
plugins_host.py - Hệ PLUGIN của Javis (port ý tưởng "plugin" của nousresearch/hermes-agent).

Plugin = THƯ MỤC Python thả vào, tự thêm TOOL (ra MỌI engine qua mcp_hub) + HOOK lifecycle,
KHÔNG phải sửa lõi. Mỗi plugin gồm:
    <dir>/plugin.yaml   - manifest (name, slug, description, version, author, enabled, min_mode)
    <dir>/plugin.py     - có def register(ctx): ctx.register_tool(...) / ctx.register_hook(...)

NGUỒN plugin (giống bundled/user của Hermes):
    - BUNDLED  <project>/system/plugins/<slug>/    ship theo app, TIN CẬY
    - VAULT    <vault>/plugins/<slug>/  (hoặc  <vault>/Javis/plugins/<slug>/)   do user tạo

TOOL plugin đi qua mcp_hub.discover_all → Claude Code / Codex (HTTP /hub/mcp) + engine API
(in-process). TÔN TRỌNG 3 mức quyền của Javis qua `min_mode` (readonly/safe/full), enforce y hệt
tool ghi file builtin. HOOK 'pre_tool_call'/'post_tool_call' được mcp_hub bắn quanh MỌI tool call
khi có plugin đăng ký (0 overhead khi không plugin nào dùng hook).

AN TOÀN (lớp CỨNG - plugin chạy code Python THẬT trong tiến trình server):
    - Bundled: tự nạp khi effective-enabled (mặc định theo manifest `enabled:`).
    - Vault:  CHỈ nạp khi env  JAVIS_ENABLE_VAULT_PLUGINS=true  (giống Hermes
      HERMES_ENABLE_PROJECT_PLUGINS - chống RCE khi ai đó ghi được vào vault) VÀ enabled:true.
    - Enable-state: bundled ở STATE_DIR/plugins.json (override, KHÔNG mutate file app);
      vault ở frontmatter plugin.yaml.
    - 1 plugin lỗi KHÔNG làm sập hub: mọi load/tool/hook đều bọc try/except.
"""
from __future__ import annotations

import asyncio
import copy
import importlib.util
import inspect
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml
import fastyaml

import mcp_catalog
from config import STATE_DIR

PROJECT_ROOT = Path(__file__).parent.parent
BUNDLED_DIR = PROJECT_ROOT / "system" / "plugins"
GLOBAL_DIR = STATE_DIR / "plugins"                # plugin TOÀN CỤC do user cài - CHUNG mọi brain
_STATE_PATH = STATE_DIR / "plugins.json"          # override bật/tắt cho bundled
_PLUGIN_DATA_DIR = STATE_DIR / "plugin-data"      # state riêng mỗi plugin (không đụng vault)

VALID_MIN_MODE = ("readonly", "safe", "full")
_ENTRY_FILES = ("plugin.py", "__init__.py")

# slug + tool name: chống traversal / chèn tên tool lạ
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_TOOL_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

# Tên tool builtin/lõi - plugin KHÔNG được trùng (mcp_hub cũng skip lúc merge, đây là lớp 2).
_RESERVED_TOOLS = {"javis_connections", "javis_read_file", "javis_list_dir",
                   "javis_write_file", "javis_use_skill"}

_lock = threading.Lock()
# cache theo vault_root: {sig, plugins:[LoadedPlugin], hooks:{event:[cb]}, errors:{slug:msg}}
_cache: Dict[str, dict] = {}


def valid_slug(s: Any) -> bool:
    return bool(_SLUG_RE.match(str(s or "")))


def _env_user_enabled() -> bool:
    """Cho phép chạy plugin do NGƯỜI DÙNG cài (global STATE_DIR/plugins + vault/plugins). Chúng chạy
    code Python THẬT trong tiến trình server nên mặc định TẮT - bật bằng JAVIS_ENABLE_USER_PLUGINS=true
    (hoặc alias cũ JAVIS_ENABLE_VAULT_PLUGINS=true) rồi khởi động lại. Plugin BUNDLED không chịu gate này."""
    for k in ("JAVIS_ENABLE_USER_PLUGINS", "JAVIS_ENABLE_VAULT_PLUGINS"):
        if str(os.getenv(k, "")).strip().lower() in ("1", "true", "yes", "on"):
            return True
    return False


# Alias tương thích: main.py + code cũ còn gọi _env_vault_enabled().
_env_vault_enabled = _env_user_enabled


def global_plugins_dir() -> Path:
    """Thư mục plugin TOÀN CỤC (chung mọi brain) - JAVIS_STATE_DIR/plugins."""
    return GLOBAL_DIR


# ============================================================
# State (bundled override) - STATE_DIR/plugins.json
# ============================================================
# Cache đọc file theo (mtime_ns, size) - cùng khuôn với config.read_settings (config.py:136).
# Vì sao cần: describe() chạy trên đường nóng system prompt (mỗi lượt chat, mỗi task Kanban,
# mỗi lần nhắc hẹn nổ, mỗi tick loop). Mỗi lần nó đọc + parse plugin.yaml của MỌI plugin, và
# _effective_enabled còn đọc lại plugins.json cho TỪNG plugin bundled - 8 plugin là 8 lần đọc
# cùng một file. File đổi thì mtime/size đổi nên tự nạp lại; bật/tắt plugin ghi thẳng vào
# manifest hoặc plugins.json nên cũng tự hết hạn.
# Luôn trả BẢN SAO SÂU: cả hai dict đều bị nơi gọi sửa tại chỗ rồi ghi ngược ra file
# (xem toggle ở cuối file), trả thẳng object trong cache là bẩn cache.
_STATE_CACHE = {"sig": None, "data": None}
_MANIFEST_CACHE: dict = {}


_MISSING = "<khong-ton-tai>"


def _stat_sig(p: Path):
    """(mtime_ns, size), hoặc _MISSING khi file chưa có, hoặc None khi lỗi lạ (không cache).

    Phân biệt 'chưa có file' với 'lỗi lạ' là cần thiết: plugins.json chỉ sinh ra khi user
    bật/tắt plugin bundled lần đầu, nên trên phần lớn bản cài nó KHÔNG tồn tại. Gộp nó vào
    None thì _read_state không cache được và mỗi describe() lại ném FileNotFoundError một
    lần cho MỖI plugin bundled - đúng cái đang muốn bỏ.
    """
    try:
        st = p.stat()
        return (st.st_mtime_ns, st.st_size)
    except FileNotFoundError:
        return _MISSING
    except OSError:
        return None


def _read_state() -> dict:
    sig = _stat_sig(_STATE_PATH)
    if sig is not None and sig == _STATE_CACHE["sig"] and _STATE_CACHE["data"] is not None:
        return copy.deepcopy(_STATE_CACHE["data"])
    try:
        d = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        out = d if isinstance(d, dict) else {}
    except Exception:
        out = {}
    if sig is not None:
        _STATE_CACHE["sig"] = sig
        _STATE_CACHE["data"] = copy.deepcopy(out)
    return out


def _write_state(state: dict) -> None:
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STATE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(_STATE_PATH)
    except Exception as e:
        print(f"[plugins] ghi state lỗi: {e}", file=sys.stderr)


# ============================================================
# Discovery (chỉ ĐỌC manifest - KHÔNG chạy code plugin)
# ============================================================
def vault_plugins_dir(vault_root: Optional[str]) -> Optional[Path]:
    """Thư mục plugin của vault: ưu tiên <root>/plugins (cấu trúc phẳng mới),
    fallback <root>/Javis/plugins (cấu trúc cũ). Trả path mặc định (có thể chưa tồn tại)."""
    if not vault_root:
        return None
    root = Path(vault_root)
    flat = root / "plugins"
    if flat.is_dir():
        return flat
    nested = root / "Javis" / "plugins"
    if nested.is_dir():
        return nested
    return flat


def _iter_plugin_dirs(vault_root: Optional[str]):
    """Yield (source, plugin_dir). source ∈ {'bundled','user','vault'} (dedupe theo slug, nguồn SAU đè
    nguồn TRƯỚC): bundled (ship theo app) → user (GLOBAL_DIR, chung mọi brain) → vault (riêng 1 brain).
    'user' KHÔNG phụ thuộc vault_root nên nạp được ở MỌI brain và MỌI engine (kể cả Claude/Codex qua hub)."""
    seen: Dict[str, tuple] = {}
    for source, base in (("bundled", BUNDLED_DIR), ("user", GLOBAL_DIR), ("vault", vault_plugins_dir(vault_root))):
        if not base or not Path(base).is_dir():
            continue
        for d in sorted(Path(base).iterdir()):
            if d.is_dir() and any((d / e).is_file() for e in _ENTRY_FILES):
                seen[d.name] = (source, d)   # trùng slug: nguồn sau ghi đè
    for _slug, (source, d) in seen.items():
        yield source, d


def _read_manifest(pdir: Path) -> Tuple[dict, str]:
    f = pdir / "plugin.yaml"
    if not f.is_file():
        f = pdir / "plugin.yml"
    if not f.is_file():
        return {}, ""
    sig, key = _stat_sig(f), str(f)
    hit = _MANIFEST_CACHE.get(key)
    if sig is not None and hit is not None and hit["sig"] == sig:
        return copy.deepcopy(hit["manifest"]), hit["err"]
    try:
        m = fastyaml.safe_load(f.read_text(encoding="utf-8")) or {}
        out, err = (m if isinstance(m, dict) else {}), ""
    except Exception as e:
        out, err = {}, f"manifest lỗi: {type(e).__name__}: {e}"
    if sig is not None:
        _MANIFEST_CACHE[key] = {"sig": sig, "manifest": copy.deepcopy(out), "err": err}
    return out, err


def _entry_file(pdir: Path) -> Optional[Path]:
    for e in _ENTRY_FILES:
        p = pdir / e
        if p.is_file():
            return p
    return None


def _effective_enabled(source: str, slug: str, manifest: dict) -> bool:
    """Bật/tắt HIỆU LỰC (chưa tính env gate của vault)."""
    if source == "bundled":
        st = _read_state()
        if slug in (st.get("disabled") or []):
            return False
        if slug in (st.get("enabled") or []):
            return True
        return bool(manifest.get("enabled", False))
    # user (global) + vault: theo 'enabled' trong manifest (toggle ghi thẳng manifest)
    return bool(manifest.get("enabled", False))


def describe(vault_root: Optional[str] = None) -> List[dict]:
    """Metadata MỌI plugin (KHÔNG chạy code plugin) - cho UI/index/endpoint.
    Kèm trạng thái load lỗi nếu cache đã từng nạp."""
    errors = (_cache.get(_key(vault_root)) or {}).get("errors") or {}
    env_ok = _env_user_enabled()
    out: List[dict] = []
    for source, pdir in _iter_plugin_dirs(vault_root):
        slug = pdir.name
        manifest, merr = _read_manifest(pdir)
        name = manifest.get("name") or slug
        want = _effective_enabled(source, slug, manifest)
        user_src = source in ("user", "vault")
        gated = bool(user_src and want and not env_ok)   # muốn bật nhưng env chặn
        loaded = want and (env_ok or source == "bundled")
        mm = manifest.get("min_mode", "readonly")
        out.append({
            "slug": slug, "name": name, "source": source,
            "description": manifest.get("description", ""),
            "version": str(manifest.get("version", "")), "author": manifest.get("author", ""),
            "enabled": bool(want), "loaded": bool(loaded), "gated": gated,
            "min_mode": mm if mm in VALID_MIN_MODE else "readonly",
            "tools": list(manifest.get("tools") or []),
            "hooks": list(manifest.get("hooks") or []),
            "valid_slug": valid_slug(slug),
            "error": merr or errors.get(slug, ""),
            "dir": str(pdir),
        })
    return out


# ============================================================
# PluginContext - API cho register(ctx)
# ============================================================
class PluginContext:
    """Thứ plugin nhận trong register(ctx). Đăng ký tool + hook, kèm tiện ích state/log."""

    def __init__(self, slug: str, source: str, plugin_dir: Path, vault_root: Optional[str]):
        self.slug = slug
        self.source = source
        self.dir = Path(plugin_dir)
        self.vault_root = vault_root
        self.state_dir = STATE_DIR
        self._tools: List[dict] = []
        self._hooks: Dict[str, List[Callable]] = {}

    @property
    def data_dir(self) -> Path:
        """Thư mục state RIÊNG của plugin (tự tạo). KHÔNG nằm trong vault."""
        d = _PLUGIN_DATA_DIR / self.slug
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return d

    def register_tool(self, name: str, description: str, handler: Callable,
                      schema: Optional[dict] = None, parameters: Optional[dict] = None,
                      min_mode: str = "readonly", check_fn: Optional[Callable] = None,
                      emoji: str = "") -> None:
        """Thêm 1 tool cho MỌI engine. handler(args: dict, ctx: PluginContext) -> str (sync|async).
        min_mode: readonly(mặc định, luôn chạy) | safe(chặn ở chế độ suggest) | full(chỉ chế độ full).
        check_fn(): None nếu sẵn sàng, hoặc str lý do để chặn (vd chưa đăng nhập)."""
        if not _TOOL_RE.match(str(name or "")):
            raise ValueError(f"tên tool không hợp lệ (a-z0-9_): {name!r}")
        if min_mode not in VALID_MIN_MODE:
            min_mode = "readonly"
        self._tools.append({
            "name": name, "description": description or name, "handler": handler,
            "schema": schema or parameters or {"type": "object", "properties": {}},
            "min_mode": min_mode, "check_fn": check_fn, "emoji": emoji,
        })

    def register_hook(self, event: str, callback: Callable) -> None:
        """Đăng ký callback lifecycle. v1 hỗ trợ: 'pre_tool_call', 'post_tool_call'
        (bắn quanh MỌI tool call). callback(**kwargs) - nhận tool_name, args, result, mode, vault_root."""
        self._hooks.setdefault(str(event), []).append(callback)


class LoadedPlugin:
    __slots__ = ("slug", "source", "name", "min_mode", "tools", "hooks", "ctx")

    def __init__(self, ctx: PluginContext, manifest: dict):
        self.slug = ctx.slug
        self.source = ctx.source
        self.name = manifest.get("name") or ctx.slug
        self.tools = ctx._tools
        self.hooks = ctx._hooks
        self.ctx = ctx


# ============================================================
# Load (CHẠY code plugin) - có cache theo signature
# ============================================================
def _key(vault_root: Optional[str], scope_vault: bool = True) -> str:
    return f"{vault_root or ''}|{scope_vault}"


def _signature(vault_root: Optional[str], scope_vault: bool = True) -> tuple:
    """Chữ ký để biết khi nào phải nạp lại: mtime state + mtime entry/manifest mọi plugin + env flag."""
    sig: List[Any] = [_env_user_enabled()]
    try:
        sig.append(_STATE_PATH.stat().st_mtime)
    except OSError:
        sig.append(0)
    for source, pdir in _iter_plugin_dirs(vault_root if scope_vault else None):
        for fn in ("plugin.yaml", "plugin.yml", "plugin.py", "__init__.py"):
            p = pdir / fn
            try:
                sig.append((source, pdir.name, fn, p.stat().st_mtime))
            except OSError:
                pass
    return tuple(sig)


def _import_entry(slug: str, source: str, entry: Path):
    """Nạp entry file thành module riêng. Chèn tạm dir vào sys.path để import phụ (nếu có)."""
    mod_name = f"javis_plugin_{source}_{re.sub(r'[^a-z0-9_]', '_', slug.lower())}"
    spec = importlib.util.spec_from_file_location(mod_name, str(entry))
    if not spec or not spec.loader:
        raise ImportError(f"không tạo được spec cho {entry}")
    module = importlib.util.module_from_spec(spec)
    pdir = str(entry.parent)
    added = pdir not in sys.path
    if added:
        sys.path.insert(0, pdir)
    try:
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
    finally:
        if added:
            try:
                sys.path.remove(pdir)
            except ValueError:
                pass
    return module


def _load_all(vault_root: Optional[str], scope_vault: bool = True) -> dict:
    """Nạp (hoặc lấy cache) mọi plugin effective-enabled cho vault_root này.

    scope_vault=False: KHÔNG duyệt thư mục plugin riêng-của-vault (chỉ bundled + user/global),
    nhưng PluginContext của mọi plugin nạp được vẫn nhận đúng vault_root thật - đây là chỗ
    tách hai nghĩa của tham số vault_root cũ (xem plugin_tools)."""
    k = _key(vault_root, scope_vault)
    sig = _signature(vault_root, scope_vault)
    with _lock:
        ent = _cache.get(k)
        if ent and ent.get("sig") == sig:
            return ent
        plugins: List[LoadedPlugin] = []
        hooks: Dict[str, List[Callable]] = {}
        errors: Dict[str, str] = {}
        env_ok = _env_user_enabled()
        dirs_vault_root = vault_root if scope_vault else None
        for source, pdir in _iter_plugin_dirs(dirs_vault_root):
            slug = pdir.name
            manifest, merr = _read_manifest(pdir)
            if merr:
                errors[slug] = merr
                continue
            if not _effective_enabled(source, slug, manifest):
                continue
            if source in ("user", "vault"):
                if not env_ok:
                    continue   # gate CỨNG: plugin user (global+vault) cần JAVIS_ENABLE_USER_PLUGINS=true
                if not valid_slug(slug):
                    errors[slug] = "slug không hợp lệ"
                    continue
            entry = _entry_file(pdir)
            if not entry:
                errors[slug] = "thiếu plugin.py"
                continue
            try:
                ctx = PluginContext(slug, source, pdir, vault_root)
                module = _import_entry(slug, source, entry)
                reg = getattr(module, "register", None)
                if not callable(reg):
                    raise AttributeError("thiếu hàm register(ctx)")
                reg(ctx)
                lp = LoadedPlugin(ctx, manifest)
                plugins.append(lp)
                for evt, cbs in ctx._hooks.items():
                    hooks.setdefault(evt, []).extend(cbs)
            except Exception as e:
                errors[slug] = f"{type(e).__name__}: {e}"
                print(f"[plugins] nạp '{slug}' lỗi: {e}", file=sys.stderr)
        ent = {"sig": sig, "plugins": plugins, "hooks": hooks, "errors": errors}
        _cache[k] = ent
        return ent


def invalidate() -> None:
    """Xoá cache load - gọi sau khi bật/tắt/sửa plugin.

    Dọn luôn cache đọc file. Về lý thuyết thừa (ghi file làm mtime đổi nên cache tự hết hạn),
    nhưng mtime trên vài hệ tệp chỉ chính xác tới giây, mà bật rồi tắt liền nhau trong cùng
    một giây lại đúng là thao tác user hay làm nhất trên trang Plugin.
    """
    with _lock:
        _cache.clear()
    _STATE_CACHE["sig"] = None
    _STATE_CACHE["data"] = None
    _MANIFEST_CACHE.clear()


# ============================================================
# Tool specs cho mcp_hub (build tươi mỗi discover_all theo mode)
# ============================================================
def _min_mode_ok(min_mode: str, mode: str) -> bool:
    eff = mcp_catalog.effective_perm("full", mode)   # readonly | safe | full (đã cap theo mode)
    rank = mcp_catalog.PERM_RANK
    return rank.get(eff, 2) >= rank.get(min_mode, 0)


async def _maybe_await(v):
    if inspect.isawaitable(v):
        return await v
    return v


def _make_call(tool: dict, ctx: PluginContext, mode: str):
    """Bọc 1 handler plugin thành async call(args) có gate min_mode + check_fn + chống crash."""
    handler = tool["handler"]
    min_mode = tool["min_mode"]
    check_fn = tool.get("check_fn")
    name = tool["name"]

    async def _call(args):
        if not _min_mode_ok(min_mode, mode):
            loai = "ghi/hành động" if min_mode == "safe" else "nguy hiểm (chỉ chế độ full)"
            return (f"ERROR: tool '{name}' cần mức quyền cao hơn ({min_mode}) - thao tác {loai} "
                    f"bị chặn ở chế độ hiện tại. Nâng chế độ chạy nếu thật sự cần.")
        if check_fn:
            try:
                why = check_fn()
                why = await _maybe_await(why)
            except Exception as e:
                return f"ERROR: kiểm tra điều kiện tool '{name}' lỗi: {type(e).__name__}: {e}"
            if why:
                return f"ERROR: {why}"
        try:
            res = handler(args or {}, ctx)
            res = await _maybe_await(res)
            return res if isinstance(res, str) else json.dumps(res, ensure_ascii=False, default=str)
        except Exception as e:
            return f"ERROR: tool plugin '{name}' lỗi: {type(e).__name__}: {e}"

    return _call


def plugin_tools(mode: str = "full", vault_root: Optional[str] = None, *,
                 scope_vault: bool = True) -> Tuple[List[dict], Dict[str, dict]]:
    """(tools_spec, route) từ MỌI plugin đã nạp. mcp_hub merge vào discover_all.
    tools_spec: [{fn, server:'javis', name, description, schema}]. route: {fn: {'call': async fn}}.

    mode: mức quyền lượt chạy. vault_root: brain để ctx của plugin biết đang ở đâu.
    scope_vault=False: KHÔNG nạp plugin riêng-của-vault (chỉ bundled + global) nhưng ctx VẪN
    thấy vault_root. Tách hai nghĩa vì trước đây một chữ None gánh cả hai, làm ctx mù brain."""
    ent = _load_all(vault_root, scope_vault)
    tools: List[dict] = []
    route: Dict[str, dict] = {}
    seen = set()
    for lp in ent["plugins"]:
        for t in lp.tools:
            fn = t["name"]
            if fn in _RESERVED_TOOLS or fn in seen:
                print(f"[plugins] tool '{fn}' ({lp.slug}) trùng tên - bỏ qua", file=sys.stderr)
                continue
            seen.add(fn)
            desc = t["description"]
            if lp.source == "vault":
                desc = f"[plugin {lp.slug}] {desc}"
            tools.append({"fn": fn, "server": "javis", "name": fn,
                          "description": desc, "schema": t["schema"]})
            effect = "read" if t["min_mode"] == "readonly" else (
                "write" if t["min_mode"] == "safe" else "danger"
            )
            route[fn] = {
                "call": _make_call(t, lp.ctx, mode),
                # Metadata dẫn xuất cho Capability Registry Phase 2; dispatcher chỉ đọc `call`.
                "source_type": "plugin",
                "source_id": f"{lp.source}:{lp.slug}",
                "effect": effect,
                "required_mode": t["min_mode"],
                "health": "healthy",
            }
    return tools, route


# ============================================================
# Hooks - mcp_hub bắn quanh mọi tool call (khi có hook)
# ============================================================
def has_tool_hooks(vault_root: Optional[str] = None) -> bool:
    ent = _load_all(vault_root)
    h = ent["hooks"]
    return bool(h.get("pre_tool_call") or h.get("post_tool_call"))


async def _fire(event: str, vault_root: Optional[str], payload: dict) -> None:
    ent = _load_all(vault_root)
    for cb in ent["hooks"].get(event, []):
        try:
            await _maybe_await(cb(**payload))
        except Exception as e:
            print(f"[plugins] hook {event} lỗi: {type(e).__name__}: {e}", file=sys.stderr)


def wrap_with_hooks(fn: str, base_call: Callable, mode: str, vault_root: Optional[str]) -> Callable:
    """Bọc 1 route call để bắn pre/post_tool_call. base_call(args) -> result (async)."""
    async def _wrapped(args):
        await _fire("pre_tool_call", vault_root,
                    {"tool_name": fn, "args": args, "mode": mode, "vault_root": vault_root})
        result = await base_call(args)
        await _fire("post_tool_call", vault_root,
                    {"tool_name": fn, "args": args, "result": result, "mode": mode, "vault_root": vault_root})
        return result
    return _wrapped


def fire_hook(event: str, vault_root: Optional[str] = None, **payload) -> None:
    """Bắn 1 hook đồng bộ từ code không-async (tasks/loops sau này). Best-effort."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        loop.create_task(_fire(event, vault_root, payload))
    else:
        try:
            asyncio.run(_fire(event, vault_root, payload))
        except Exception:
            pass


# ============================================================
# Bật/tắt plugin
# ============================================================
def set_enabled(slug: str, enabled: bool, vault_root: Optional[str] = None) -> dict:
    """Bật/tắt 1 plugin. Bundled → ghi STATE_DIR/plugins.json (không đụng file app);
    vault → ghi enabled vào frontmatter plugin.yaml. Trả {ok, source, gated, note}."""
    if not valid_slug(slug):
        return {"ok": False, "error": "slug không hợp lệ"}
    # xác định plugin thuộc nguồn nào
    found = None
    for source, pdir in _iter_plugin_dirs(vault_root):
        if pdir.name == slug:
            found = (source, pdir)
            break
    if not found:
        return {"ok": False, "error": "không tìm thấy plugin"}
    source, pdir = found
    if source == "bundled":
        st = _read_state()
        en = set(st.get("enabled") or [])
        dis = set(st.get("disabled") or [])
        if enabled:
            en.add(slug); dis.discard(slug)
        else:
            dis.add(slug); en.discard(slug)
        st["enabled"] = sorted(en); st["disabled"] = sorted(dis)
        _write_state(st)
        invalidate()
        return {"ok": True, "source": source, "gated": False, "note": ""}
    # user (global) + vault: ghi 'enabled' thẳng vào manifest của plugin
    f = pdir / "plugin.yaml"
    if not f.is_file():
        f = pdir / "plugin.yml"
    manifest, merr = _read_manifest(pdir)
    if merr:
        return {"ok": False, "error": merr}
    manifest["enabled"] = bool(enabled)
    try:
        f.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": f"ghi manifest lỗi: {e}"}
    invalidate()
    gated = bool(enabled and not _env_user_enabled())
    note = ("Đã bật trong manifest NHƯNG plugin do người dùng cài chỉ chạy khi đặt biến môi trường "
            "JAVIS_ENABLE_USER_PLUGINS=true rồi khởi động lại (bảo vệ chống chạy code lạ).") if gated else ""
    return {"ok": True, "source": source, "gated": gated, "note": note}
