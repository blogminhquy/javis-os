"""Remote control page for the machine running Javis (phone over Tailscale).

Loaded by plugin.py and served at /ext/desktop-apps/. Every route needs the owner's browser session
(the plugin host default) and every mutating route is POST, so the core CSRF guard covers them.

System calls are module-level functions (`ps`, `spawn`, `capture_screen`...) so tests swap them
for fakes and nothing real runs. Screen and clipboard go through Win32 directly; the only PowerShell
left (volume, folders, sleep) runs fixed scripts and reads values from environment variables.

New controls (lock, volume, screen, clipboard, files, power) are Windows only for now; apps reuse
the plugin's own open/close so outcome words stay the same as the model tools.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import platform
import re
import subprocess
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

try:
    import localefmt
    _chu = localefmt.chu

    def ui_lang() -> str:
        return localefmt.ngon_ngu_giao_dien()
except Exception:  # pragma: no cover - outside the server
    def _chu(vi, en, **kw):
        return vi.format(**kw) if kw else vi

    def ui_lang() -> str:
        return "vi"

try:
    from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response
except Exception:  # pragma: no cover
    FileResponse = HTMLResponse = JSONResponse = Response = None

IS_WIN = os.name == "nt"
HERE = Path(__file__).resolve().parent

VOLUME_STEP = 0.06
SHOT_MAX_W = 1600
CLIP_MAX = 20000
FILES_MAX = 60
_ROOTS_TTL = 300.0
FAV_MAX = 12


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0


# ============================================================
# System layer (swapped in tests)
# ============================================================
_PS_PRELUDE = ("$ProgressPreference = 'SilentlyContinue'\n$ErrorActionPreference = 'Stop'\n"
               "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n")


def ps(script: str, env: Optional[Dict[str, str]] = None, timeout: float = 15.0) -> str:
    """Run a FIXED PowerShell script. Values from the user go in `env`, read as $env:NAME."""
    enc = base64.b64encode((_PS_PRELUDE + script)
                           .encode("utf-16-le")).decode("ascii")
    full_env = dict(os.environ)
    full_env.update(env or {})
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc],
                           capture_output=True, text=True, timeout=timeout, env=full_env,
                           encoding="utf-8", errors="ignore", creationflags=_no_window())
    except Exception as e:
        raise RuntimeError(f"{type(e).__name__}: {e}")
    if r.returncode != 0:
        raise RuntimeError(_ps_error(r.stderr or r.stdout or "") or f"exit {r.returncode}")
    return r.stdout or ""


def _ps_error(raw: str) -> str:
    """First real error line out of PowerShell's CLIXML stderr (or the plain text)."""
    parts = re.findall(r'<S S="Error">(.*?)</S>', raw or "", flags=re.S)
    text = "".join(parts).replace("_x000D__x000A_", "\n") if parts else (raw or "")
    lines = [ln.strip() for ln in text.splitlines()
             if ln.strip() and not ln.strip().startswith(("At line:", "+", "#< CLIXML"))]
    return " ".join(lines)[:300]


def spawn(argv: List[str]) -> None:
    """Start a process and do not wait (lock, power: the HTTP answer must leave first)."""
    flags = _no_window()
    if IS_WIN:
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(argv, creationflags=flags, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)


_AUDIO_CS = r'''
using System;
using System.Runtime.InteropServices;
[Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioEndpointVolume {
  int f(); int g(); int h(); int i();
  int SetMasterVolumeLevelScalar(float fLevel, Guid ctx);
  int j();
  int GetMasterVolumeLevelScalar(out float pfLevel);
  int k(); int l(); int m(); int n();
  int SetMute([MarshalAs(UnmanagedType.Bool)] bool bMute, Guid ctx);
  int GetMute(out bool pbMute);
}
[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDevice { int Activate(ref Guid id, int clsCtx, int p, out IAudioEndpointVolume aev); }
[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumerator { int f(); int GetDefaultAudioEndpoint(int flow, int role, out IMMDevice dev); }
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumeratorCom { }
public class JavisAudio {
  static IAudioEndpointVolume Vol() {
    var en = new MMDeviceEnumeratorCom() as IMMDeviceEnumerator;
    IMMDevice dev = null;
    Marshal.ThrowExceptionForHR(en.GetDefaultAudioEndpoint(0, 1, out dev));
    IAudioEndpointVolume v = null;
    var id = typeof(IAudioEndpointVolume).GUID;
    Marshal.ThrowExceptionForHR(dev.Activate(ref id, 23, 0, out v));
    return v;
  }
  public static float Level {
    get { float x = -1; Marshal.ThrowExceptionForHR(Vol().GetMasterVolumeLevelScalar(out x)); return x; }
    set { Marshal.ThrowExceptionForHR(Vol().SetMasterVolumeLevelScalar(value, Guid.Empty)); }
  }
  public static bool Mute {
    get { bool x; Marshal.ThrowExceptionForHR(Vol().GetMute(out x)); return x; }
    set { Marshal.ThrowExceptionForHR(Vol().SetMute(value, Guid.Empty)); }
  }
}
'''

_VOLUME_PS = ("Add-Type -TypeDefinition @'\n" + _AUDIO_CS + "\n'@\n" + r'''
$op = $env:JAVIS_RC_OP
$step = [float]$env:JAVIS_RC_STEP
if ($op -eq 'up') { [JavisAudio]::Mute = $false; [JavisAudio]::Level = [Math]::Min(1.0, [JavisAudio]::Level + $step) }
elseif ($op -eq 'down') { [JavisAudio]::Level = [Math]::Max(0.0, [JavisAudio]::Level - $step) }
elseif ($op -eq 'mute') { [JavisAudio]::Mute = -not [JavisAudio]::Mute }
'{0}|{1}' -f [int][Math]::Round([JavisAudio]::Level * 100), [int][JavisAudio]::Mute
''')


def volume(op: str = "") -> dict:
    """Apply `op` (up | down | mute | "" to read) and return the level read back from Windows."""
    out = ps(_VOLUME_PS, {"JAVIS_RC_OP": op, "JAVIS_RC_STEP": str(VOLUME_STEP)})
    last = [ln for ln in out.strip().splitlines() if "|" in ln][-1]
    lvl, mute = last.strip().split("|", 1)
    return {"level": int(lvl), "muted": mute.strip() == "1"}


def _win32():
    import ctypes
    from ctypes import wintypes as w
    u, g, k = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.kernel32
    H = ctypes.c_void_p
    for f, res, args in (
        (u.GetDC, H, [H]), (u.ReleaseDC, ctypes.c_int, [H, H]), (u.GetSystemMetrics, ctypes.c_int, [ctypes.c_int]),
        (g.CreateCompatibleDC, H, [H]), (g.CreateCompatibleBitmap, H, [H, ctypes.c_int, ctypes.c_int]),
        (g.SelectObject, H, [H, H]), (g.DeleteObject, w.BOOL, [H]), (g.DeleteDC, w.BOOL, [H]),
        (g.SetStretchBltMode, ctypes.c_int, [H, ctypes.c_int]),
        (g.StretchBlt, w.BOOL, [H] + [ctypes.c_int] * 4 + [H] + [ctypes.c_int] * 4 + [w.DWORD]),
        (g.GetDIBits, ctypes.c_int, [H, H, w.UINT, w.UINT, ctypes.c_void_p, ctypes.c_void_p, w.UINT]),
        (u.OpenClipboard, w.BOOL, [H]), (u.CloseClipboard, w.BOOL, []), (u.EmptyClipboard, w.BOOL, []),
        (u.GetClipboardData, H, [w.UINT]), (u.SetClipboardData, H, [w.UINT, H]),
        (k.GlobalAlloc, H, [w.UINT, ctypes.c_size_t]), (k.GlobalLock, H, [H]), (k.GlobalUnlock, w.BOOL, [H]),
        (k.GlobalFree, H, [H]),
    ):
        f.restype, f.argtypes = res, args
    return ctypes, u, g, k


def _png(width: int, height: int, rgb: bytes) -> bytes:
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    stride = width * 3
    raw = b"".join(b"\x00" + rgb[y * stride:(y + 1) * stride] for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def capture_screen() -> bytes:
    """PNG of the whole desktop, scaled to at most SHOT_MAX_W wide, through plain GDI (no PowerShell:
    antivirus flags screen-capture scripts, and Pillow is not a Javis dependency). Kept in memory
    only: a file in the brain would sync the owner's screen to every device."""
    ctypes, u, g, _k = _win32()
    # Physical pixels on a scaled laptop, for this thread only: the rest of Javis keeps its setting.
    old = None
    try:
        u.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        u.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        old = u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    except AttributeError:
        pass
    try:
        x, y = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
        w, h = u.GetSystemMetrics(78), u.GetSystemMetrics(79)
        if w <= 0 or h <= 0:
            raise RuntimeError("screen unavailable")
        dw = min(w, SHOT_MAX_W)
        dh = max(1, round(h * dw / w))
        sdc = u.GetDC(None)
        mdc = g.CreateCompatibleDC(sdc)
        bmp = g.CreateCompatibleBitmap(sdc, dw, dh)
        prev = g.SelectObject(mdc, bmp)
        try:
            g.SetStretchBltMode(mdc, 4)   # HALFTONE: smooth downscale
            if not g.StretchBlt(mdc, 0, 0, dw, dh, sdc, x, y, w, h, 0x00CC0020):
                raise RuntimeError("screen unavailable")
            hdr = (ctypes.c_uint32 * 10)()
            ctypes.memset(hdr, 0, ctypes.sizeof(hdr))
            ctypes.c_uint32.from_buffer(hdr, 0).value = 40
            ctypes.c_int32.from_buffer(hdr, 4).value = dw
            ctypes.c_int32.from_buffer(hdr, 8).value = -dh          # top-down rows
            ctypes.c_uint16.from_buffer(hdr, 12).value = 1
            ctypes.c_uint16.from_buffer(hdr, 14).value = 32
            buf = (ctypes.c_ubyte * (dw * dh * 4))()
            if g.GetDIBits(mdc, bmp, 0, dh, buf, hdr, 0) != dh:
                raise RuntimeError("screen unavailable")
        finally:
            g.SelectObject(mdc, prev)
            g.DeleteObject(bmp)
            g.DeleteDC(mdc)
            u.ReleaseDC(None, sdc)
    finally:
        if old:
            u.SetThreadDpiAwarenessContext(old)
    bgra = bytes(buf)
    rgb = bytearray(dw * dh * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = bgra[2::4], bgra[1::4], bgra[0::4]
    return _png(dw, dh, bytes(rgb))


def _open_clipboard(u) -> None:
    for _ in range(10):
        if u.OpenClipboard(None):
            return
        time.sleep(0.05)
    raise RuntimeError("clipboard busy")


def clipboard_get() -> str:
    ctypes, u, _g, k = _win32()
    _open_clipboard(u)
    try:
        h = u.GetClipboardData(13)    # CF_UNICODETEXT
        if not h:
            return ""
        p = k.GlobalLock(h)
        try:
            return ctypes.wstring_at(p)[:CLIP_MAX] if p else ""
        finally:
            k.GlobalUnlock(h)
    finally:
        u.CloseClipboard()


def clipboard_set(text: str) -> None:
    ctypes, u, _g, k = _win32()
    data = (str(text) + "\0").encode("utf-16-le")
    h = k.GlobalAlloc(0x0002, len(data))    # GMEM_MOVEABLE
    if not h:
        raise RuntimeError("out of memory")
    p = k.GlobalLock(h)
    ctypes.memmove(p, data, len(data))
    k.GlobalUnlock(h)
    _open_clipboard(u)
    try:
        u.EmptyClipboard()
        if not u.SetClipboardData(13, h):
            k.GlobalFree(h)
            raise RuntimeError("clipboard refused the text")
    finally:
        u.CloseClipboard()


def lock_screen() -> None:
    spawn(["rundll32.exe", "user32.dll,LockWorkStation"])


_SLEEP_PS = ("Start-Sleep -Seconds 3; Add-Type -AssemblyName System.Windows.Forms; "
             "[void][System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)")


def power(op: str) -> None:
    """Schedule the power action a few seconds out, so the page gets its answer first."""
    if op == "sleep":
        enc = base64.b64encode(_SLEEP_PS.encode("utf-16-le")).decode("ascii")
        spawn(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc])
    elif op == "restart":
        spawn(["shutdown", "/r", "/t", "5"])
    elif op == "shutdown":
        spawn(["shutdown", "/s", "/t", "5"])
    else:
        raise ValueError(op)


_FOLDERS_PS = r'''
[Environment]::GetFolderPath('Desktop')
(New-Object -ComObject Shell.Application).Namespace('shell:Downloads').Self.Path
[Environment]::GetFolderPath('MyDocuments')
'''
_roots_cache: Dict[str, object] = {"t": 0.0, "v": {}}


def folder_roots() -> Dict[str, str]:
    """Real Desktop / Downloads / Documents, including OneDrive redirection."""
    now = time.time()
    if _roots_cache["v"] and now - float(_roots_cache["t"]) < _ROOTS_TTL:
        return dict(_roots_cache["v"])  # type: ignore[arg-type]
    lines = [ln.strip() for ln in ps(_FOLDERS_PS).splitlines() if ln.strip()]
    v = {k: p for k, p in zip(("desktop", "downloads", "documents"), lines) if p and Path(p).is_dir()}
    _roots_cache.update(t=now, v=v)
    return dict(v)


# ============================================================
# Pure helpers
# ============================================================
def list_files(root: str) -> List[dict]:
    """Files (not folders) directly inside `root`, newest first."""
    out = []
    try:
        for e in os.scandir(root):
            if e.name.startswith(".") or e.name.lower() == "desktop.ini":
                continue
            try:
                if not e.is_file():
                    continue
                st = e.stat()
            except OSError:
                continue
            out.append({"name": e.name, "size": st.st_size, "mtime": int(st.st_mtime)})
    except OSError:
        return []
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out[:FILES_MAX]


def safe_file(roots: Dict[str, str], root_key: str, name: str) -> Optional[Path]:
    """The file `name` directly inside the chosen root, or None. No separators, no climbing out,
    no links pointing elsewhere."""
    base = roots.get(str(root_key or ""))
    name = str(name or "")
    if not base or not name or name in (".", "..") or "/" in name or "\\" in name or ":" in name:
        return None
    try:
        b = Path(base).resolve()
        p = (b / name).resolve()
        p.relative_to(b)
    except (OSError, ValueError):
        return None
    if p.parent != b or not p.is_file():
        return None
    return p


def load_favorites(data_dir: Path) -> List[str]:
    try:
        v = json.loads((Path(data_dir) / "favorites.json").read_text(encoding="utf-8"))
        return [str(x) for x in v if str(x).strip()][:FAV_MAX] if isinstance(v, list) else []
    except Exception:
        return []


def save_favorites(data_dir: Path, favs: List[str]) -> None:
    d = Path(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "favorites.json.tmp"
    tmp.write_text(json.dumps(favs[:FAV_MAX], ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, d / "favorites.json")


def outcome(text: str) -> dict:
    """Map the plugin's outcome words to what the page shows. [unverified] is NOT shown as done."""
    s = str(text or "")
    for word, state in (("[done]", "done"), ("[unverified]", "unverified"), ("[ask]", "ask"),
                        ("[started]", "unverified"), ("ERROR: [failed]", "failed")):
        if s.startswith(word):
            return {"ok": state in ("done", "unverified"), "state": state, "detail": s[len(word):].strip()}
    return {"ok": False, "state": "failed", "detail": s}


# ============================================================
# Page strings
# ============================================================
STRINGS = {
    "title": ("Điều khiển máy", "Remote control"),
    "online": ("Đang bật, cập nhật {t}", "Online, updated {t}"),
    "offline": ("Không kết nối được tới máy", "Can't reach the computer"),
    "screen": ("Màn hình", "Screen"),
    "shot_empty": ("Bấm Chụp để xem màn hình máy", "Tap Capture to see the screen"),
    "shot_at": ("Chụp lúc {t}", "Captured at {t}"),
    "shot_alt": ("Ảnh màn hình máy", "Screenshot of the computer"),
    "capture": ("Chụp", "Capture"),
    "download_shot": ("Tải ảnh về điện thoại", "Save image to phone"),
    "apps": ("Ứng dụng", "Apps"),
    "add_app": ("Thêm app hay dùng", "Add a favorite app"),
    "running": ("Đang mở", "Open"),
    "stopped": ("Đang tắt, bấm để mở", "Closed, tap to open"),
    "open_x": ("{n}, bấm để mở hoặc đưa lên trước", "{n}, tap to open or bring to front"),
    "close_x": ("Đóng {n}", "Close {n}"),
    "unfav_x": ("Bỏ {n} khỏi danh sách", "Remove {n} from the list"),
    "apps_empty": ("Chưa có app nào đang mở. Bấm + để ghim app hay dùng.",
                   "No apps open. Tap + to pin apps you use often."),
    "add_title": ("Thêm app hay dùng", "Add a favorite app"),
    "add_label": ("Tên app", "App name"),
    "add_ph": ("Ví dụ: Chrome, Excel, Zalo", "For example: Chrome, Excel, Zalo"),
    "add": ("Thêm", "Add"),
    "cancel": ("Huỷ", "Cancel"),
    "clipboard": ("Clipboard", "Clipboard"),
    "clip_label": ("Chữ gửi sang máy tính", "Text to send to the computer"),
    "clip_ph": ("Gõ hoặc dán vào đây", "Type or paste here"),
    "send": ("Gửi", "Send"),
    "fetch": ("Lấy về", "Get"),
    "files": ("Lấy file từ máy", "Get a file"),
    "files_sub": ("Desktop, Downloads, Documents", "Desktop, Downloads, Documents"),
    "pick": ("Chọn file", "Pick a file"),
    "files_empty": ("Thư mục này chưa có file", "No files in this folder"),
    "f_desktop": ("Desktop", "Desktop"),
    "f_downloads": ("Downloads", "Downloads"),
    "f_documents": ("Documents", "Documents"),
    "close": ("Đóng", "Close"),
    "power": ("Nguồn", "Power"),
    "sleep_row": ("Cho máy ngủ", "Sleep"),
    "sleep": ("Ngủ", "Sleep"),
    "restart": ("Khởi động lại", "Restart"),
    "shutdown": ("Tắt máy", "Shut down"),
    "sleep_q": ("Cho máy ngủ?", "Put the computer to sleep?"),
    "sleep_p": ("Máy ngủ thì Javis và điện thoại mất kết nối tới khi máy thức lại.",
                "While it sleeps, Javis and your phone lose the connection until it wakes up."),
    "restart_q": ("Khởi động lại?", "Restart?"),
    "restart_p": ("Javis tạm mất kết nối khoảng 1 đến 2 phút rồi tự vào lại.",
                  "Javis drops for about 1 to 2 minutes, then comes back on its own."),
    "shutdown_q": ("Tắt máy?", "Shut down?"),
    "shutdown_p": ("Javis sẽ ngắt kết nối cho tới khi bật máy lại. Từ xa không bật lại được.",
                   "Javis stays offline until the computer is turned on again. It can't be turned on remotely."),
    "dock": ("Điều khiển nhanh", "Quick controls"),
    "lock": ("Khoá", "Lock"),
    "volume": ("Âm lượng", "Volume"),
    "vol_down": ("Nhỏ hơn", "Quieter"),
    "vol_up": ("To hơn", "Louder"),
    "mute": ("Tắt tiếng", "Mute"),
    "unmute": ("Bật tiếng", "Unmute"),
    "muted": ("Tắt", "Off"),
    "done": ("Xong", "Done"),
    "unverified": ("Đã gửi lệnh, chưa xác nhận được", "Command sent, not confirmed"),
    "net_err": ("Mất kết nối tới máy. Kiểm tra Tailscale rồi thử lại.",
                "Lost the connection. Check Tailscale and try again."),
}


def strings_for(lang: str) -> Dict[str, str]:
    i = 0 if str(lang or "").lower().startswith("vi") else 1
    return {k: v[i] for k, v in STRINGS.items()}


def render_page(lang: str) -> str:
    html = (HERE / "page.html").read_text(encoding="utf-8")
    t = strings_for(lang)
    blob = json.dumps(t, ensure_ascii=False).replace("<", "\\u003c")
    html = html.replace("__LANG__", "vi" if lang.lower().startswith("vi") else "en")
    html = html.replace("__TITLE__", t["title"])
    return html.replace("__STRINGS__", blob)


# ============================================================
# HTTP routes
# ============================================================
class Core:
    """What the routes need from plugin.py. Late-bound so tests can swap plugin functions."""

    def __init__(self, check_ready: Callable, open_app: Callable, close_app: Callable,
                 list_running: Callable, installed: Callable, protected: set):
        self.check_ready = check_ready
        self.open_app = open_app
        self.close_app = close_app
        self.list_running = list_running
        self.installed = installed
        self.protected = protected


def _err(msg: str, code: int = 200) -> "JSONResponse":
    return JSONResponse({"ok": False, "error": msg}, status_code=code)


def _blocked(core: Core) -> Optional[str]:
    why = core.check_ready()
    if why:
        return why
    if not IS_WIN:
        return _chu("Trang điều khiển máy hiện chỉ chạy trên Windows.",
                    "The remote control page only works on Windows for now.")
    return None


def _sys_err(e: Exception) -> str:
    if "clipboard busy" in str(e):
        return _chu("Không mở được clipboard. Máy đang khoá thì mở khoá rồi thử lại.",
                    "Couldn't open the clipboard. If the computer is locked, unlock it and try again.")
    return _chu("Máy không làm được lệnh này ({e}).", "The computer could not do that ({e}).", e=str(e)[:160])


async def _body(request) -> dict:
    try:
        v = await request.json()
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def register_routes(ctx, core: Core) -> None:
    async def page(request, c):
        return HTMLResponse(render_page(ui_lang()), headers={"Cache-Control": "no-store"})

    async def status(request, c):
        why = _blocked(core)
        return {"ok": not why, "error": why or "", "host": platform.node(), "time": time.strftime("%H:%M")}

    async def apps(request, c):
        why = _blocked(core)
        if why:
            return _err(why)
        running = await asyncio.to_thread(core.list_running)
        seen: Dict[str, dict] = {}
        for r in running:
            img = str(r.get("image") or "")
            if not r.get("title") or not img or img.lower() in core.protected:
                continue
            seen.setdefault(img.lower(), {"image": img, "title": str(r["title"])[:80]})
        favs = load_favorites(c.data_dir)
        installed = []
        try:
            installed = sorted({a["name"] for a in await asyncio.to_thread(core.installed)})[:400]
        except Exception:
            pass
        return {"ok": True, "running": list(seen.values()), "favorites": favs, "installed": installed}

    async def app_action(request, c):
        why = _blocked(core)
        if why:
            return _err(why)
        b = await _body(request)
        op, name = str(b.get("op") or ""), str(b.get("name") or "").strip()[:120]
        if not name:
            return _err(_chu("Thiếu tên app.", "Missing app name."), 400)
        if op == "open":
            res = await asyncio.to_thread(core.open_app, {"name": name}, c)
        elif op == "close":
            res = await asyncio.to_thread(core.close_app, {"name": name}, c)
        else:
            return _err(_chu("Lệnh không hợp lệ.", "Unknown command."), 400)
        return outcome(res)

    async def favorites(request, c):
        b = await _body(request)
        op, name = str(b.get("op") or ""), str(b.get("name") or "").strip()[:80]
        favs = load_favorites(c.data_dir)
        if op == "add" and name:
            if name.lower() not in (f.lower() for f in favs):
                if len(favs) >= FAV_MAX:
                    return _err(_chu("Đã đủ {n} app, bỏ bớt một app trước.",
                                     "Already {n} apps, remove one first.", n=FAV_MAX))
                favs.append(name)
        elif op == "remove":
            favs = [f for f in favs if f.lower() != name.lower()]
        else:
            return _err(_chu("Lệnh không hợp lệ.", "Unknown command."), 400)
        save_favorites(c.data_dir, favs)
        return {"ok": True, "favorites": favs}

    async def lock(request, c):
        why = _blocked(core)
        if why:
            return _err(why)
        try:
            await asyncio.to_thread(lock_screen)
        except Exception as e:
            return _err(_sys_err(e))
        return {"ok": True, "state": "unverified", "msg": _chu("Đã gửi lệnh khoá máy.", "Lock command sent.")}

    async def vol(request, c):
        why = _blocked(core)
        if why:
            return _err(why)
        op = ""
        if request.method == "POST":
            op = str((await _body(request)).get("op") or "")
            if op not in ("up", "down", "mute"):
                return _err(_chu("Lệnh không hợp lệ.", "Unknown command."), 400)
        try:
            v = await asyncio.to_thread(volume, op)
        except Exception as e:
            return _err(_sys_err(e))
        return {"ok": True, **v}

    async def shot(request, c):
        why = _blocked(core)
        if why:
            return _err(why, 409)
        try:
            data = await asyncio.to_thread(capture_screen)
        except Exception as e:
            if "screen unavailable" in str(e):
                return _err(_chu("Máy đang khoá hoặc tắt màn hình nên không chụp được.",
                                 "The computer is locked or its screen is off, so it can't capture."), 409)
            return _err(_sys_err(e), 500)
        return Response(data, media_type="image/png", headers={"Cache-Control": "no-store"})

    async def clip(request, c):
        why = _blocked(core)
        if why:
            return _err(why)
        try:
            if request.method == "POST":
                text = str((await _body(request)).get("text") or "")
                if not text:
                    return _err(_chu("Chưa có chữ để gửi.", "Nothing to send."), 400)
                if len(text) > CLIP_MAX:
                    return _err(_chu("Chữ quá dài (tối đa {n} ký tự).", "Text too long (max {n} characters).",
                                     n=CLIP_MAX), 400)
                await asyncio.to_thread(clipboard_set, text)
                return {"ok": True, "msg": _chu("Đã gửi, trên máy bấm Ctrl+V để dán.",
                                                 "Sent. Press Ctrl+V on the computer to paste.")}
            return {"ok": True, "text": await asyncio.to_thread(clipboard_get)}
        except Exception as e:
            return _err(_sys_err(e))

    async def files(request, c):
        why = _blocked(core)
        if why:
            return _err(why)
        try:
            roots = await asyncio.to_thread(folder_roots)
        except Exception as e:
            return _err(_sys_err(e))
        key = str(request.query_params.get("root") or "")
        if key not in roots:
            return _err(_chu("Không tìm thấy thư mục này trên máy.", "This folder was not found."), 404)
        return {"ok": True, "roots": list(roots), "files": await asyncio.to_thread(list_files, roots[key])}

    async def file_get(request, c):
        why = _blocked(core)
        if why:
            return _err(why, 409)
        try:
            roots = await asyncio.to_thread(folder_roots)
        except Exception as e:
            return _err(_sys_err(e), 500)
        p = safe_file(roots, request.query_params.get("root", ""), request.query_params.get("name", ""))
        if not p:
            return _err(_chu("Không tìm thấy file.", "File not found."), 404)
        return FileResponse(str(p), filename=p.name)

    async def pwr(request, c):
        why = _blocked(core)
        if why:
            return _err(why)
        b = await _body(request)
        op = str(b.get("op") or "")
        if op not in ("sleep", "restart", "shutdown"):
            return _err(_chu("Lệnh không hợp lệ.", "Unknown command."), 400)
        if b.get("confirm") is not True:
            return _err(_chu("Cần xác nhận trước khi làm.", "Needs confirmation first."), 400)
        try:
            await asyncio.to_thread(power, op)
        except Exception as e:
            return _err(_sys_err(e))
        msg = {"sleep": _chu("Máy sẽ ngủ sau 3 giây.", "The computer sleeps in 3 seconds."),
               "restart": _chu("Máy sẽ khởi động lại sau 5 giây.", "The computer restarts in 5 seconds."),
               "shutdown": _chu("Máy sẽ tắt sau 5 giây.", "The computer shuts down in 5 seconds.")}[op]
        return {"ok": True, "state": "unverified", "msg": msg}

    ctx.register_http("", page)
    ctx.register_http("api/status", status)
    ctx.register_http("api/apps", apps)
    ctx.register_http("api/app", app_action, methods=("POST",))
    ctx.register_http("api/favorites", favorites, methods=("POST",))
    ctx.register_http("api/lock", lock, methods=("POST",))
    ctx.register_http("api/volume", vol, methods=("GET", "POST"))
    ctx.register_http("api/screen", shot)
    ctx.register_http("api/clipboard", clip, methods=("GET", "POST"))
    ctx.register_http("api/files", files)
    ctx.register_http("api/file", file_get)
    ctx.register_http("api/power", pwr, methods=("POST",))
