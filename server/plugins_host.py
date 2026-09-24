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
_HTTP_PATH_RE = re.compile(r"^[A-Za-z0-9._~-]+(/[A-Za-z0-9._~-]+)*$")
_WELL_KNOWN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
# Nguồn được mở đường HTTP. Thiếu 'vault' là CHỦ Ý: model ghi được vào brain.
_HTTP_NGUON = frozenset({"bundled", "pack", "user"})

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


def _pack_plugin_dirs() -> List[tuple]:
    """[(slug, dir, pack_id)] cho plugin nằm trong GÓI đang bật. Rỗng nếu module packs lỗi."""
    try:
        import packs
        return [(d.name, d, pid) for pid, d in packs.plugin_dirs()]
    except Exception as e:
        print(f"[plugins] không đọc được plugin của gói: {e}", file=sys.stderr)
        return []


def _iter_plugin_dirs(vault_root: Optional[str]):
    """Yield (source, plugin_dir). source ∈ {'bundled','pack','user','vault'} (dedupe theo slug,
    nguồn SAU đè nguồn TRƯỚC): bundled (ship theo app) → pack (gói cài từ .zip) → user
    (GLOBAL_DIR, chung mọi brain) → vault (riêng 1 brain).
    'user' và 'pack' KHÔNG phụ thuộc vault_root nên nạp được ở MỌI brain và MỌI engine.

    Vì sao 'pack' đứng SAU bundled mà TRƯỚC user: đặt sau bundled thì hành vi cũ
    (user/vault đè bundled) giữ nguyên bit-for-bit, không phá một shadow nào đang chạy. Còn
    việc gói KHÔNG được đè bundled thì chặn ở chỗ khác và chặn sớm hơn - trình cài từ chối
    ngay một gói mang plugin trùng slug bundled, xem `_slug_bundled`."""
    seen: Dict[str, tuple] = {}
    for source, base in (("bundled", BUNDLED_DIR),):
        if not base or not Path(base).is_dir():
            continue
        for d in sorted(Path(base).iterdir()):
            if d.is_dir() and any((d / e).is_file() for e in _ENTRY_FILES):
                seen[d.name] = (source, d)
    for slug, d, _pid in _pack_plugin_dirs():
        seen[slug] = ("pack", d)
    for source, base in (("user", GLOBAL_DIR), ("vault", vault_plugins_dir(vault_root))):
        if not base or not Path(base).is_dir():
            continue
        for d in sorted(Path(base).iterdir()):
            if d.is_dir() and any((d / e).is_file() for e in _ENTRY_FILES):
                seen[d.name] = (source, d)   # trùng slug: nguồn sau ghi đè
    for _slug, (source, d) in seen.items():
        yield source, d


def _slug_bundled() -> set:
    """Slug của plugin ĐI KÈM APP. Trình cài từ chối gói mang plugin trùng một trong số này.

    Vì sao chặn ở lúc CÀI chứ không lúc nạp: một gói lặng lẽ thay `javis_task` hay
    `javis_schedule` dưới một màn hình xác nhận chỉ nói "gói này chạy mã" là đúng kiểu bất ngờ
    không nên có. Chặn sớm thì người dùng thấy lý do trước khi có gì rơi xuống đĩa."""
    try:
        return {d.name for d in BUNDLED_DIR.iterdir()
                if d.is_dir() and any((d / e).is_file() for e in _ENTRY_FILES)}
    except OSError:
        return set()


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


def da_go(slug: str) -> bool:
    """Plugin ĐI KÈM APP mà người dùng đã GỠ.

    "Gỡ" không phải xoá file: cây code read-only trên Docker nên xoá là EACCES, còn trên bản
    native thì lượt `git pull` sau đó mọc lại - một thứ "đã xoá" mà tự quay về thì tệ hơn một
    thứ đang tắt. Nên gỡ nghĩa là biến khỏi danh sách chính, khỏi mọi engine, khỏi prompt; file
    vẫn nằm trong bản cài và cài lại là một cú bấm.

    Khác `disabled` ở Ý ĐỊNH: tắt là "tạm không dùng, vẫn để đó nhìn", gỡ là "tôi không cần
    thứ này". Giao diện đối xử hai trạng thái đó khác nhau nên sổ ghi cũng tách."""
    return slug in (_read_state().get("removed") or [])


def _effective_enabled(source: str, slug: str, manifest: dict) -> bool:
    """Bật/tắt HIỆU LỰC (chưa tính env gate của vault)."""
    if da_go(slug):
        return False
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
        # Nguồn 'pack' KHÔNG chịu cổng env: nó đã đi qua trình cài, tức có người xem rồi bấm
        # đồng ý, và chữ ký mã được đối chiếu lại ở mỗi lần nạp. Thiếu vế này thì thẻ báo
        # "bật (chưa nạp)" trong khi tool của nó đã ra tới mọi engine - nói sai với người dùng.
        loaded = want and (env_ok or source in ("bundled", "pack"))
        mm = manifest.get("min_mode", "readonly")
        out.append({
            "slug": slug, "name": name, "source": source,
            "description": manifest.get("description", ""),
            "version": str(manifest.get("version", "")), "author": manifest.get("author", ""),
            "enabled": bool(want), "loaded": bool(loaded), "gated": gated,
            "min_mode": mm if mm in VALID_MIN_MODE else "readonly",
            "tools": list(manifest.get("tools") or []),
            "hooks": list(manifest.get("hooks") or []),
            "valid_slug": valid_slug(slug), "removed": da_go(slug),
            # Trang riêng của plugin: chỉ đưa ra khi plugin có quyền mở đường HTTP và đang nạp
            # được, không thì nút "Mở trang" trỏ vào một đường 404.
            "page": (f"/ext/{slug}/" + (_trang_cua(manifest) or "")
                     if (_trang_cua(manifest) is not None and loaded
                         and source in _HTTP_NGUON) else ""),
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
        self._on_unload: List[Callable] = []
        self._http: List[dict] = []
        self._well_known: Dict[str, Callable] = {}

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

    def on_unload(self, fn: Callable) -> None:
        """Đăng ký việc phải làm khi plugin bị TẮT hoặc GỠ. Chạy ngược thứ tự đăng ký.

        Tool và hook thì Javis tự thu hồi được: chúng chỉ nằm trong danh sách của
        `LoadedPlugin` trong cache, và hub dựng lại bảng route mỗi lần cache hết hạn. Cái Javis
        KHÔNG tự thu hồi được là thứ `register()` mở ra với thế giới bên ngoài - một thread,
        một socket, một watcher hệ tệp, một tiến trình con. Nếu plugin mở thứ như vậy thì phải
        tự đóng ở đây, nếu không nó sống tiếp sau khi người dùng đã bấm Tắt.

        Lỗi trong callback bị nuốt và in ra stderr: một plugin dọn dẹp hỏng không được phép
        chặn việc tắt nó."""
        if callable(fn):
            self._on_unload.append(fn)

    def register_hook(self, event: str, callback: Callable) -> None:
        """Đăng ký callback lifecycle. v1 hỗ trợ: 'pre_tool_call', 'post_tool_call'
        (bắn quanh MỌI tool call). callback(**kwargs) - nhận tool_name, args, result, mode,
        vault_root. Luôn khai `**kwargs` trong callback: các khoá mới được thêm theo thời gian
        (vd `denied` ở post_tool_call), và một callback khai cứng tham số sẽ gãy khi đó.

        **`pre_tool_call` CHẶN ĐƯỢC** (từ 0.63.1 - trước đó nó chỉ quan sát được dù docstring
        này nói "bắn quanh mọi tool call" nên ai cũng tưởng là chốt chặn). Giá trị trả về:

            return {"deny": "lý do"}    -> tool KHÔNG chạy, model nhận đúng câu lý do đó
            return {"args": {...}}      -> thay tham số rồi mới chạy
            return None                 -> không ảnh hưởng (mặc định, plugin cũ giữ nguyên)

        Hook ném lỗi thì tool VẪN CHẠY (fail-open có chủ ý, xem `_fire_pre`). `post_tool_call`
        không chặn được: lúc đó tool đã chạy rồi.
        """
        self._hooks.setdefault(str(event), []).append(callback)


    # ---- đường HTTP (0.64.22) ----
    #
    # Sinh ra để "Javis trong ChatGPT" rời lõi thành một gói trong kho: gói đó phải mở cửa OAuth
    # và một địa chỉ MCP cho máy chủ OpenAI gọi vào, mà plugin trước đây chỉ đăng ký được tool
    # và hook. Cố ý làm CHUNG chứ không may đo cho một gói: webhook của dịch vụ ngoài là cùng
    # một nhu cầu.
    #
    # Ranh giới (lõi ép, plugin không nới được):
    #   - Mọi đường nằm dưới `/ext/<slug>/`, không chiếm được đường nào của lõi.
    #   - MẶC ĐỊNH đòi phiên đăng nhập dashboard thật (token API không qua).
    #   - `public=True`: không đòi đăng nhập - plugin TỰ xác thực (token OAuth, chữ ký webhook).
    #   - `no_cookie=True` (chỉ đi kèm public): miễn hàng rào CSRF, và lõi GỠ HẲN cookie khỏi
    #     request trước khi giao cho plugin. Miễn CSRF mà vẫn mang cookie là mở đường cho trang
    #     lạ mượn phiên của chủ; gỡ cookie thì đường đó không còn gì để mượn.
    #   - Chỉ plugin đi kèm app, plugin của GÓI đã đồng ý cài, và plugin global (đã qua cổng
    #     env) mới có đường. Plugin trong brain KHÔNG: model ghi được vào brain.

    def register_http(self, path: str, handler: Callable, methods=("GET",),
                      public: bool = False, no_cookie: bool = False) -> None:
        """Mở `/ext/<slug>/<path>`. handler(request, ctx) (sync|async) trả về một Response của
        Starlette, một dict/list (thành JSON) hoặc một chuỗi (thành HTML)."""
        duong = str(path or "").strip("/")
        if duong and (not _HTTP_PATH_RE.match(duong)
                      or any(p in (".", "..") for p in duong.split("/"))):
            raise ValueError(f"đường HTTP không hợp lệ: {path!r}")
        if no_cookie and not public:
            raise ValueError("no_cookie chỉ đi kèm public=True")
        mt = tuple(sorted({str(m).upper() for m in (methods or ("GET",))}))
        if not mt or any(m not in _HTTP_METHODS for m in mt):
            raise ValueError(f"method không hợp lệ: {methods!r}")
        self._http.append({"path": duong, "handler": handler, "methods": mt,
                           "public": bool(public), "no_cookie": bool(no_cookie)})

    def register_well_known(self, name: str, handler: Callable) -> None:
        """Phục vụ `GET /.well-known/<name>` và `/.well-known/<name>/<phần sau>` (ví dụ metadata
        OAuth, vốn BẮT BUỘC nằm ở gốc tên miền). Công khai và không cookie. Hai plugin cùng xin
        một tên thì plugin nạp trước giữ tên đó."""
        ten = str(name or "").strip("/")
        if not _WELL_KNOWN_RE.match(ten):
            raise ValueError(f"tên well-known không hợp lệ: {name!r}")
        self._well_known[ten] = handler


class LoadedPlugin:
    __slots__ = ("slug", "source", "name", "description", "min_mode", "tools", "hooks", "ctx",
                 "http", "well_known", "page")

    def __init__(self, ctx: PluginContext, manifest: dict):
        self.slug = ctx.slug
        self.source = ctx.source
        self.name = manifest.get("name") or ctx.slug
        # Giữ lại mô tả của manifest để hub có cái mà GIỚI THIỆU plugin này trong thực đơn
        # tool lười. Xem `plugin_tools` bên dưới về lý do nó quan trọng.
        self.description = str(manifest.get("description") or "").strip()
        self.tools = ctx._tools
        self.hooks = ctx._hooks
        self.ctx = ctx
        self.http = ctx._http
        self.well_known = ctx._well_known
        self.page = _trang_cua(manifest)


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
    try:
        import packs
        sig.append(packs.signature())      # gói bật/tắt, cài/gỡ -> nạp lại
    except Exception:
        sig.append(None)
    for source, pdir in _iter_plugin_dirs(vault_root if scope_vault else None):
        for fn in ("plugin.yaml", "plugin.yml", "plugin.py", "__init__.py"):
            p = pdir / fn
            try:
                st = p.stat()
                # Thêm SIZE bên cạnh mtime: ghi đè một tệp mà giữ nguyên mtime là chuyện làm
                # được, và chỉ so mtime thì bản mới cưỡi lên cache. Không phải chốt tuyệt đối
                # (đổi nội dung giữ nguyên cả hai vẫn lọt) - chốt thật là chữ ký mã đối chiếu
                # lúc NẠP, xem `_digest_thu_muc`.
                sig.append((source, pdir.name, fn, st.st_mtime, st.st_size))
            except OSError:
                pass
    return tuple(sig)


def _import_entry(slug: str, source: str, entry: Path):
    """Nạp entry file thành module riêng. Chèn tạm dir vào sys.path để import phụ (nếu có)."""
    mod_name = f"javis_plugin_{source}_{re.sub(r'[^a-z0-9_]', '_', slug.lower())}"
    spec = importlib.util.spec_from_file_location(mod_name, str(entry))
    if not spec or not spec.loader:
        raise ImportError(f"không tạo được spec cho {entry}")
    # Cho module tự tìm được anh em của nó mà KHÔNG chọc sys.path. Cách cũ chèn thư mục
    # plugin vào đầu sys.path suốt lúc chạy thân module, nên một plugin chứa `config.py` hay
    # `mcp_hub.py` sẽ CHE module thật của server cho mọi import nó thực hiện - và cache
    # sys.modules giữ lại thứ nó đã import nhầm. `submodule_search_locations` cho đúng khả
    # năng import anh em mà không đụng đường tìm kiếm toàn cục.
    spec.submodule_search_locations = [str(entry.parent)]
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(mod_name, None)   # nạp hỏng thì đừng để lại xác trong sys.modules
        raise
    return module


def _digest_thu_muc(thu_muc: Path) -> str:
    """SHA256 của mọi tệp .py trong thư mục, theo thứ tự đường dẫn. Rỗng nếu không có tệp nào.

    Phải khớp từng bit với `pack_install._digest_ma`, vì hai hàm này đối chiếu với nhau: một
    cái ghi lúc CÀI, một cái tính lại lúc NẠP."""
    import hashlib
    h = hashlib.sha256()
    co = False
    for f in sorted(thu_muc.rglob("*.py")):
        try:
            h.update(str(f.relative_to(thu_muc)).replace("\\", "/").encode("utf-8"))
            h.update(f.read_bytes())
            co = True
        except OSError:
            continue
    return h.hexdigest() if co else ""


def _pack_cua(pdir: Path) -> str:
    """Gói nào sở hữu thư mục plugin này. Rỗng nếu không phải plugin của gói."""
    for slug, d, pid in _pack_plugin_dirs():
        if d == pdir:
            return pid
    return ""


def _pack_duoc_nap(pdir: Path) -> Tuple[bool, str]:
    """Plugin của GÓI có được chạy mã không. Trả (được, lý do nếu không).

    Hai điều kiện, và cả hai đều nói về CÙNG một thứ: có người đã xem rồi bấm đồng ý.

    1. Gói phải có hàng trong sổ cài đặt, tức đã đi qua trình cài. Gói thả tay vào thư mục
       không có hàng nào, nên mã của nó không tự chạy.
    2. Chữ ký mã tính lại từ đĩa phải khớp cái ghi lúc cài. Kiểm ở đây chứ không chỉ ở trình
       cài, vì ai ghi được `plugin.py` thì cũng ghi được `packs.json` - một chốt chỉ nằm ở
       trình cài thì chỉ gác được trình cài, không gác được lần nạp sau.

    Cổng `JAVIS_ENABLE_USER_PLUGINS` KHÔNG áp ở đây, có chủ ý. Cổng đó bịt lỗ "thư mục ghi
    được nên mã chạy mà không ai bấm gì" - đúng với `<brain>/plugins/` vì model ghi được vào
    vault. Trình cài phá bỏ đúng điều kiện đó: có người bấm, có màn hình liệt kê từng tệp .py,
    và có chữ ký ghi lại để đối chiếu. Cùng loại bảo đảm, chỉ theo TỪNG gói thay vì bật tắt
    tất cả. Xem docs/dev/2026-09-tang-goi-mo-rong-spec.md."""
    pid = _pack_cua(pdir)
    if not pid:
        return False, "không xác định được gói sở hữu"
    try:
        import packs
    except Exception as e:
        return False, f"không đọc được sổ gói: {e}"
    thuc = _digest_thu_muc(pdir.parent.parent)   # digest tính trên CẢ gói, như lúc cài
    if not thuc:
        return True, ""                          # gói không có mã thì không có gì để gác
    if not packs.da_dong_y_ma(pid):
        return False, ("gói này chưa đi qua trình cài nên mã của nó không tự chạy - "
                       "cài lại ở Kho cài đặt để xác nhận")
    ghi = packs.digest_ma(pid)
    if ghi and ghi != thuc:
        return False, ("mã trong gói đã đổi so với lúc bạn đồng ý cài - "
                       "cài lại ở Kho cài đặt để xem và xác nhận lại")
    return True, ""


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
            if source == "pack":
                if not valid_slug(slug):
                    errors[slug] = "slug không hợp lệ"
                    continue
                duoc, vi_sao = _pack_duoc_nap(pdir)
                if not duoc:
                    errors[slug] = vi_sao
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


# ============================================================
# Đường HTTP của plugin (0.64.22) - lõi tra ở đây, main.py chỉ chuyển request
# ============================================================
def _trang_cua(manifest: dict) -> Optional[str]:
    """Đường tương đối của trang riêng plugin khai trong `plugin.yaml` (`page: ""` là gốc), hoặc
    None nếu không khai. Thẻ trên trang Plugin dùng nó để hiện nút "Mở trang"."""
    if "page" not in (manifest or {}):
        return None
    v = str(manifest.get("page") or "").strip("/")
    if v and (not _HTTP_PATH_RE.match(v) or any(p in (".", "..") for p in v.split("/"))):
        return None
    return v


def _plugin_http() -> List["LoadedPlugin"]:
    """Plugin đang nạp được mở đường HTTP. MỘT bản nạp cố định, không theo brain: cùng một
    đường mà mỗi brain một bản plugin thì trạng thái trong RAM của plugin (yêu cầu đang chờ,
    mã một lần) sẽ nằm ở bản này còn request tới bản kia."""
    ent = _load_all(None, scope_vault=False)
    return [lp for lp in ent["plugins"] if lp.source in _HTTP_NGUON]


def tim_http(slug: str, duong: str, method: str = ""):
    """(plugin, route) phục vụ `/ext/<slug>/<duong>`, hoặc None.
    `method` rỗng = khớp theo đường thôi (hàng rào cần biết đường có tồn tại, chưa cần method)."""
    duong = str(duong or "").strip("/")
    for lp in _plugin_http():
        if lp.slug != slug:
            continue
        for r in lp.http:
            if r["path"] == duong and (not method or method.upper() in r["methods"]):
                return lp, r
    return None


def tim_well_known(ten: str):
    """(plugin, handler) phục vụ `/.well-known/<ten>`, hoặc None. Plugin nạp trước giữ tên."""
    for lp in _plugin_http():
        h = lp.well_known.get(ten)
        if h:
            return lp, h
    return None


def _tach_ext(path: str):
    """'/ext/<slug>/<phần sau>' -> (slug, phần sau), hoặc None."""
    if not path.startswith("/ext/"):
        return None
    con = path[len("/ext/"):]
    slug, _, sau = con.partition("/")
    return (slug, sau) if valid_slug(slug) else None


def _ten_well_known(path: str) -> str:
    if not path.startswith("/.well-known/"):
        return ""
    return path[len("/.well-known/"):].split("/", 1)[0]


def http_cong_khai(path: str, method: str) -> bool:
    """Hàng rào đăng nhập hỏi: đường này của plugin có được vào KHÔNG cần đăng nhập không.
    Xét theo CẶP (đường, method): một plugin có thể để GET công khai mà POST cùng đường thì không."""
    try:
        ten = _ten_well_known(path)
        if ten:
            return method.upper() == "GET" and tim_well_known(ten) is not None
        t = _tach_ext(path)
        if not t:
            return False
        tr = tim_http(t[0], t[1], method or "?")
        return bool(tr and tr[1]["public"])
    except Exception:
        return False


def http_khong_cookie(path: str, method: str) -> bool:
    """Hàng rào CSRF hỏi: đường này có được miễn không. Chỉ đường KHÔNG dùng cookie (lõi gỡ
    cookie trước khi giao cho plugin), nên miễn CSRF không cho ai mượn được phiên của chủ."""
    try:
        ten = _ten_well_known(path)
        if ten:
            return method.upper() == "GET" and tim_well_known(ten) is not None
        t = _tach_ext(path)
        if not t:
            return False
        tr = tim_http(t[0], t[1], method or "?")
        return bool(tr and tr[1]["no_cookie"])
    except Exception:
        return False


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


def unload(slug: str) -> dict:
    """Dừng một plugin cho THẬT: chạy on_unload, bỏ khỏi cache, và pop khỏi sys.modules.

    Vì sao phải pop sys.modules: `_import_entry` đặt module vào đó và trước bản này không ai
    bỏ ra. Nạp lại sẽ ghi đè khoá cũ nên không sai kết quả, nhưng module cũ vẫn sống trong bộ
    nhớ cùng mọi thứ nó giữ tham chiếu - và với plugin của gói thì "gói đã gỡ mà mã của nó còn
    trong tiến trình" là một câu khó nói cho xuôi.

    Trả về số callback đã chạy và số module đã bỏ. Không ném lỗi ra ngoài bao giờ: đây là
    đường DỌN, mà một đường dọn tự ném lỗi thì để lại đúng cái tình trạng nửa vời nó sinh ra để
    chấm dứt."""
    slug = str(slug or "").strip()
    ra = {"ok": True, "callbacks": 0, "modules": 0}
    if not slug:
        return ra
    with _lock:
        for k, ent in list(_cache.items()):
            for lp in list(ent.get("plugins") or []):
                if lp.ctx.slug != slug:
                    continue
                # Ngược thứ tự đăng ký: thứ mở sau đóng trước, đúng như một khối try/finally
                # lồng nhau sẽ làm.
                for fn in reversed(getattr(lp.ctx, "_on_unload", []) or []):
                    try:
                        fn()
                        ra["callbacks"] += 1
                    except Exception as e:
                        print(f"[plugins] on_unload '{slug}': {type(e).__name__}: {e}",
                              file=sys.stderr)
                ent["plugins"] = [x for x in ent["plugins"] if x.ctx.slug != slug]
                ent["sig"] = None      # buộc dựng lại ở lần gọi sau
        an = f"_{re.sub(r'[^a-z0-9_]', '_', slug.lower())}"
        for mod in [m for m in list(sys.modules)
                    if m.startswith("javis_plugin_") and m.endswith(an)]:
            sys.modules.pop(mod, None)
            ra["modules"] += 1
    return ra


def set_removed(slug: str, removed: bool) -> dict:
    """Gỡ hoặc cài lại một plugin. Ghi vào `STATE_DIR/plugins.json`, không đụng cây code.

    Áp cho MỌI nguồn, kể cả bundled - đó chính là điểm: người dùng dọn được bộ mặc định mà bản
    cập nhật sau không làm nó mọc lại."""
    slug = str(slug or "").strip()
    if not slug:
        return {"ok": False, "error": "thiếu slug"}
    st = _read_state()
    ds = set(st.get("removed") or [])
    ds.add(slug) if removed else ds.discard(slug)
    st["removed"] = sorted(ds)
    _write_state(st)
    if removed:
        unload(slug)      # gỡ thì dừng THẬT, không chỉ biến khỏi danh sách
    invalidate()
    return {"ok": True, "removed": bool(removed)}


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
            # `namespace` + `label` + `group_desc`: để hub xếp tool của MỖI plugin thành một
            # nhóm RIÊNG trong thực đơn tool lười, thay vì gộp chung vào "javis".
            #
            # Vì sao đây không phải chuyện thẩm mỹ: khi lazy bật, thực đơn là thứ DUY NHẤT
            # model đọc được về những gì nó với tới. Thiếu ba trường này thì 20 tool của gói
            # TTS Dropship nằm lẫn trong dòng "javis (javis, 45 tool): skill của brain, danh
            # sách nguồn đang đấu, tiện ích nội bộ" - không một chữ nào nhắc tới sàn, đơn hàng
            # hay dropship. Model không có lý do gì để đoán là nên tìm, nên nó kết luận thẳng
            # rằng gói chưa kết nối, dù tool vẫn gọi được qua javis_run_tool. Đúng vụ ngày
            # 05/09/2026: người dùng báo "không lên đơn được" trong khi hub vẫn phục vụ đủ.
            tools.append({"fn": fn, "server": "javis", "name": fn,
                          "description": desc, "schema": t["schema"],
                          "namespace": lp.slug, "label": lp.name,
                          "group_desc": lp.description})
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
    """Bắn hook và BỎ QUA thứ nó trả về. Dùng cho hook chỉ để quan sát (post_tool_call).

    Muốn hook CHẶN được thì dùng `_fire_pre` - xem chú thích dài ở đó.
    """
    ent = _load_all(vault_root)
    for cb in ent["hooks"].get(event, []):
        try:
            await _maybe_await(cb(**payload))
        except Exception as e:
            print(f"[plugins] hook {event} lỗi: {type(e).__name__}: {e}", file=sys.stderr)


async def _fire_pre(vault_root: Optional[str], payload: dict) -> dict:
    """Bắn `pre_tool_call` và ĐỌC thứ hook trả về. Trả {"deny": str} hoặc {"args": dict} hoặc {}.

    **Vì sao hàm này tồn tại.** Tới 0.63.0, `wrap_with_hooks` gọi `await _fire("pre_tool_call")`
    rồi vứt giá trị trả về, và `_fire` còn nuốt cả exception. Nghĩa là hook CHỈ QUAN SÁT được:
    nó không chặn nổi một lời gọi tool nào, dù docstring của `register_hook` hứa "bắn quanh
    MỌI tool call" nên ai đọc cũng tưởng đó là chốt chặn. Một lớp bảo vệ mà không bảo vệ được
    gì thì nguy hiểm hơn là không có, vì người ta tin vào nó.

    **Hợp đồng với plugin** (giữ nguyên chữ ký cũ, plugin cũ không phải sửa gì):
      - trả `{"deny": "lý do"}`  -> tool KHÔNG chạy, model nhận đúng câu lý do đó
      - trả `{"args": {...}}`    -> thay tham số rồi mới chạy (vd nắn đường dẫn về đúng thư mục)
      - trả None / bất cứ gì khác -> không ảnh hưởng, y như trước

    **FAIL-OPEN là cố ý.** Hook ném lỗi thì tool VẪN CHẠY, chỉ ghi một dòng stderr. Hook là
    thứ người dùng tự cài; để một plugin hỏng khoá được mọi tool của Javis là đổi một lỗi nhỏ
    lấy một hệ thống chết. Ai cần fail-closed thì tự bắt lỗi trong hook rồi trả `deny`.

    Nhiều hook cùng đăng ký thì hook ĐẦU TIÊN nói `deny` thắng và dừng luôn vòng lặp: đã có
    một lý do từ chối rõ ràng thì chạy tiếp mấy hook sau chỉ tổ sinh tác dụng phụ.
    """
    ent = _load_all(vault_root)
    ra: dict = {}
    for cb in ent["hooks"].get("pre_tool_call", []):
        try:
            out = await _maybe_await(cb(**payload))
        except Exception as e:
            print(f"[plugins] hook pre_tool_call lỗi: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        if not isinstance(out, dict):
            continue
        ly_do = str(out.get("deny") or "").strip()
        if ly_do:
            return {"deny": ly_do[:2000]}
        moi = out.get("args")
        if isinstance(moi, dict):
            payload = {**payload, "args": moi}
            ra["args"] = moi
    return ra


# Câu báo khi hook chặn. Đi thẳng vào chỗ model đọc kết quả tool, nên phải nói ĐƯỢC GÌ TIẾP
# THEO chứ không chỉ nói "bị chặn" - model nhận một câu cụt thì nó thử lại y hệt.
def _cau_bi_chan(fn: str, ly_do: str) -> str:
    return (f"ERROR: lời gọi `{fn}` bị chặn bởi một hook đang bật trên máy này.\n"
            f"Lý do: {ly_do}\n"
            f"Đọc kỹ lý do rồi làm lại theo đúng cách nó chỉ. Đừng gọi lại y nguyên.")


def wrap_with_hooks(fn: str, base_call: Callable, mode: str, vault_root: Optional[str]) -> Callable:
    """Bọc 1 route call để bắn pre/post_tool_call. base_call(args) -> result (async).

    `pre_tool_call` CHẶN được và SỬA được tham số (xem `_fire_pre`). `post_tool_call` thì
    không: lúc đó tool đã chạy rồi, thứ nó trả về không còn đổi được gì.
    """
    async def _wrapped(args):
        quyet = await _fire_pre(vault_root,
                                {"tool_name": fn, "args": args, "mode": mode,
                                 "vault_root": vault_root})
        if quyet.get("deny"):
            ket = _cau_bi_chan(fn, quyet["deny"])
            # Vẫn bắn post_tool_call: hook kiểm toán cần thấy CẢ lời gọi bị chặn, không thì
            # nhật ký chỉ có phần trôi lọt và đó là loại nhật ký tệ nhất.
            await _fire("post_tool_call", vault_root,
                        {"tool_name": fn, "args": args, "result": ket, "mode": mode,
                         "vault_root": vault_root, "denied": True})
            return ket
        if isinstance(quyet.get("args"), dict):
            args = quyet["args"]
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
    if not enabled:
        # "Tắt" phải là DỪNG, không phải "biến khỏi danh sách". Thiếu bước này thì thread hay
        # socket mà plugin mở ra vẫn sống sau khi người dùng bấm Tắt.
        unload(slug)
    if source == "pack":
        # Plugin của gói KHÔNG bật/tắt riêng lẻ: nó đi theo gói, và Kho cài đặt mới là chỗ bật
        # tắt. Ghi `enabled` vào manifest trong thư mục gói sẽ làm chữ ký mã lệch ngay lần nạp
        # sau, tức tự tay biến gói thành "đã đổi so với lúc đồng ý".
        return {"ok": False, "source": source,
                "error": "Plugin này đến từ một gói. Bật hoặc tắt cả gói ở Kho cài đặt."}
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
