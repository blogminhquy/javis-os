"""Plugin bundled: mở / đóng / liệt kê app trên chính máy đang chạy Javis.

Vì sao là plugin chứ không phải Desktop Agent riêng (roadmap Phase 5): trên máy chủ dự án Javis
ĐANG chạy ngay trên máy Windows của họ, nên hai file Python làm được phần lớn giá trị. Khi Javis
chạy trong Docker trên VPS, `check_fn` chặn và nói rõ lý do; điều khiển máy KHÁC máy chạy Javis
là việc của Desktop Agent sau này. Xem docs/dev/2026-09-voice-v1-spec.md mục 7.

Ba tool, ba mức quyền:
  - javis_app_list   readonly  app đã cài + app đang chạy
  - javis_app_open   safe      mở app theo tên (khớp mờ), URL http(s), hoặc đường dẫn tuyệt đối
  - javis_app_close  full      đóng app đang chạy; mặc định đóng LỊCH SỰ (app tự hỏi lưu),
                               `force=true` mới ép tắt

Chủ dự án chốt 2026-09-14: mở và đóng đều LÀM NGAY, không hỏi lại. Hai chốt an toàn còn giữ vì
chúng không phải "hỏi lại": đường dẫn mở phải nằm trong thư mục người dùng hoặc trong brain, và
đóng lịch sự trước để app có tài liệu chưa lưu còn kịp hỏi.

Mọi lệnh hệ thống đi qua bốn hàm module-level (`_launch`, `_list_running`, `_kill`, `_scan_installed`)
để test thay được bằng hàm giả, không mở gì thật trên máy chạy test.
"""
from __future__ import annotations

import difflib
import json
import os
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

try:
    import deploy_info
except Exception:  # pragma: no cover - chạy ngoài server (không xảy ra trong app)
    deploy_info = None

IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"

# Bí danh người dùng hay nói -> chuỗi tìm trong tên app / ảnh tiến trình. Không dấu, thường.
ALIASES: Dict[str, Tuple[str, ...]] = {
    "chrome": ("google chrome", "chrome"),
    "trinh duyet": ("google chrome", "chrome", "microsoft edge", "msedge", "firefox"),
    "browser": ("google chrome", "chrome", "microsoft edge", "msedge", "firefox"),
    "edge": ("microsoft edge", "msedge"),
    "firefox": ("firefox",),
    "word": ("word", "winword"),
    "excel": ("excel",),
    "powerpoint": ("powerpoint", "powerpnt"),
    "outlook": ("outlook",),
    "notepad": ("notepad",),
    "ghi chu": ("notepad", "notes"),
    "may tinh": ("calculator", "calc"),
    "calculator": ("calculator", "calc"),
    "explorer": ("file explorer", "explorer"),
    "file explorer": ("file explorer", "explorer"),
    "terminal": ("terminal", "windows terminal", "wt", "cmd"),
    "cmd": ("cmd",),
    "vscode": ("visual studio code", "code"),
    "vs code": ("visual studio code", "code"),
    "code": ("visual studio code", "code"),
    "zalo": ("zalo",),
    "telegram": ("telegram",),
    "spotify": ("spotify",),
    "obsidian": ("obsidian",),
    "antigravity": ("antigravity",),
    "cursor": ("cursor",),
    "paint": ("paint", "mspaint"),
    "capcut": ("capcut",),
}

# Tên lệnh Windows mở thẳng được bằng os.startfile dù không có shortcut (App Paths / PATH).
_WIN_COMMANDS = {"notepad", "calc", "mspaint", "explorer", "cmd", "wt", "code", "winword",
                 "excel", "powerpnt", "outlook", "msedge", "chrome", "firefox"}

# Tiến trình KHÔNG bao giờ đóng qua tool này, dù tên khớp mờ có trùng.
_PROTECTED = {"explorer.exe", "csrss.exe", "winlogon.exe", "wininit.exe", "services.exe",
              "lsass.exe", "svchost.exe", "dwm.exe", "system", "python.exe", "pythonw.exe",
              "javis.exe", "uvicorn.exe", "finder", "launchd", "systemd", "init"}

_LIST_MAX = 60
_CACHE: dict = {"t": 0.0, "apps": []}
_CACHE_TTL = 60.0


# ============================================================
# Chuẩn hoá và khớp mờ
# ============================================================
def khong_dau(s: str) -> str:
    s = str(s or "").strip().lower().replace("đ", "d")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.replace("_", " ").replace("-", " ").split())


def _stem_khong_ext(name: str) -> str:
    n = khong_dau(name)
    for ext in (".exe", ".lnk", ".app", ".desktop", ".url"):
        if n.endswith(ext):
            n = n[: -len(ext)]
    return n.strip()


def _cum_tim(name: str) -> List[str]:
    """Từ tên người dùng nói ra các cụm sẽ đem đi khớp: chính nó + bí danh."""
    q = khong_dau(name)
    for tien_to in ("app ", "ung dung ", "phan mem ", "chuong trinh ", "application "):
        if q.startswith(tien_to):
            q = q[len(tien_to):]
    out = [q]
    out.extend(ALIASES.get(q, ()))
    return [x for x in out if x]


def score(query: str, candidate: str) -> float:
    """0..1. exact 1.0, startswith 0.95, contains 0.9, còn lại difflib."""
    q, c = khong_dau(query), _stem_khong_ext(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    if c.startswith(q):
        return 0.95
    if q in c.split() or f" {q} " in f" {c} ":
        return 0.92
    if q in c:
        return 0.9
    return difflib.SequenceMatcher(None, q, c).ratio()


def best_match(name: str, candidates: List[str], nguong: float = 0.75) -> Tuple[str, float]:
    best, best_s = "", 0.0
    for cum in _cum_tim(name):
        for c in candidates:
            s = score(cum, c)
            if s > best_s:
                best, best_s = c, s
    return (best, best_s) if best_s >= nguong else ("", best_s)


# ============================================================
# Lớp hệ thống (thay được trong test)
# ============================================================
def _start_menu_dirs() -> List[Path]:
    out = []
    for env, sub in (("ProgramData", "Microsoft/Windows/Start Menu/Programs"),
                     ("APPDATA", "Microsoft/Windows/Start Menu/Programs")):
        base = os.environ.get(env)
        if base:
            p = Path(base) / sub
            if p.is_dir():
                out.append(p)
    return out


def _scan_installed() -> List[dict]:
    """[{name, path}] app đã cài. Windows: .lnk trong Start Menu; mac: /Applications; Linux: .desktop."""
    apps: List[dict] = []
    seen = set()
    if IS_WIN:
        for d in _start_menu_dirs():
            for p in d.rglob("*.lnk"):
                n = p.stem
                k = khong_dau(n)
                if not k or k in seen or k.startswith("uninstall"):
                    continue
                seen.add(k)
                apps.append({"name": n, "path": str(p)})
    elif IS_MAC:
        for d in (Path("/Applications"), Path.home() / "Applications", Path("/System/Applications")):
            if d.is_dir():
                for p in d.glob("*.app"):
                    k = khong_dau(p.stem)
                    if k and k not in seen:
                        seen.add(k)
                        apps.append({"name": p.stem, "path": str(p)})
    else:
        for d in (Path("/usr/share/applications"), Path.home() / ".local/share/applications"):
            if d.is_dir():
                for p in d.glob("*.desktop"):
                    ten = p.stem
                    try:
                        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                            if line.startswith("Name="):
                                ten = line[5:].strip()
                                break
                    except Exception:
                        pass
                    k = khong_dau(ten)
                    if k and k not in seen:
                        seen.add(k)
                        apps.append({"name": ten, "path": str(p)})
    return apps


def _installed() -> List[dict]:
    now = time.time()
    if now - _CACHE["t"] > _CACHE_TTL or not _CACHE["apps"]:
        try:
            _CACHE["apps"] = _scan_installed()
        except Exception:
            _CACHE["apps"] = []
        _CACHE["t"] = now
    return _CACHE["apps"]


def _run(cmd: List[str], timeout: float = 8.0) -> str:
    kw = {}
    if IS_WIN:
        try:
            import winproc
            kw = winproc.kwargs_no_window()
        except Exception:
            kw = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="ignore", **kw)
        return r.stdout or ""
    except Exception as e:
        return f"__ERR__ {type(e).__name__}: {e}"


def _list_running() -> List[dict]:
    """[{image, pid, title}] tiến trình đang chạy (Windows kèm tiêu đề cửa sổ)."""
    out: List[dict] = []
    if IS_WIN:
        # KHÔNG dùng `tasklist /V`: nó phải hỏi tiêu đề từng cửa sổ và trên máy nhiều tiến
        # trình mất quá 8 giây (đo 2026-09-14). Get-Process trả cùng thông tin trong dưới 1 giây.
        # Ép UTF-8 ở đầu ra, không thì tiêu đề tiếng Việt về thành dấu hỏi.
        raw = _run(["powershell", "-NoProfile", "-Command",
                    "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
                    "Get-Process | Select-Object ProcessName,Id,MainWindowTitle | "
                    "ConvertTo-Csv -NoTypeInformation"], timeout=15.0)
        import csv
        import io
        for row in csv.reader(io.StringIO(raw)):
            if len(row) < 3 or row[0] == "ProcessName":
                continue
            name, pid, title = row[0], row[1], row[2]
            if not name or name.startswith("__ERR__"):
                continue
            out.append({"image": name + ".exe", "pid": pid, "title": title or ""})
    else:
        raw = _run(["ps", "-eo", "pid=,comm="])
        for line in raw.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                out.append({"image": Path(parts[1]).name, "pid": parts[0], "title": ""})
    return out


def _launch(target: str, kind: str) -> str:
    """Mở thật. kind: lnk | path | url | command | app(mac/linux name). Trả "" nếu ổn, lỗi nếu không."""
    try:
        if IS_WIN:
            os.startfile(target)  # type: ignore[attr-defined]
            return ""
        if IS_MAC:
            cmd = ["open", "-a", target] if kind == "app" else ["open", target]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return "" if r.returncode == 0 else (r.stderr or "open lỗi").strip()
        if kind == "url" or kind == "path":
            subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return ""
        if target.endswith(".desktop"):
            r = subprocess.run(["gtk-launch", Path(target).name], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                return ""
        subprocess.Popen([target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return ""
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def _kill(image: str, force: bool) -> str:
    """Đóng tiến trình theo ảnh (chrome.exe). Trả output/lỗi dạng chuỗi."""
    if IS_WIN:
        cmd = ["taskkill", "/IM", image] + (["/F", "/T"] if force else [])
        return _run(cmd)
    if IS_MAC:
        ten = _stem_khong_ext(image)
        if not force:
            return _run(["osascript", "-e", f'tell application "{ten}" to quit'])
        return _run(["pkill", "-x", image])
    return _run(["pkill", "-f" if force else "-x", image])


# ============================================================
# Điều kiện chạy
# ============================================================
def check_ready() -> Optional[str]:
    mode = deploy_info.deploy_mode() if deploy_info else ("windows" if IS_WIN else "native")
    if mode == "docker":
        return ("Javis đang chạy trong Docker trên máy chủ, không phải trên máy của bạn, nên không "
                "mở hay đóng app trên máy bạn được. Muốn dùng tính năng này hãy chạy Javis ngay "
                "trên máy tính đang ngồi.")
    if not IS_WIN and not IS_MAC and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return ("Máy chạy Javis là Linux không có màn hình (không có DISPLAY), nên không mở app "
                "đồ hoạ được.")
    return None


def _duong_dan_cho_phep(p: Path, vault_root: Optional[str]) -> bool:
    try:
        rp = p.resolve()
    except Exception:
        return False
    goc = [Path.home().resolve()]
    if vault_root:
        try:
            goc.append(Path(vault_root).resolve())
        except Exception:
            pass
    for g in goc:
        try:
            rp.relative_to(g)
            return True
        except ValueError:
            continue
    return False


# ============================================================
# Handler
# ============================================================
def _list(args, ctx) -> str:
    loc = khong_dau((args or {}).get("filter") or "")
    installed = [a["name"] for a in _installed()]
    running = _list_running()
    # Gom tiến trình theo ảnh, giữ tiêu đề cửa sổ có nghĩa nhất.
    by_image: Dict[str, dict] = {}
    for r in running:
        img = r["image"]
        ent = by_image.setdefault(img, {"image": img, "count": 0, "title": ""})
        ent["count"] += 1
        if r.get("title") and not ent["title"]:
            ent["title"] = r["title"]
    dang_chay = [{"app": _stem_khong_ext(v["image"]), "image": v["image"], "windows": v["count"],
                  "title": v["title"][:80]} for v in by_image.values() if v["title"]]
    if loc:
        installed = [n for n in installed if loc in khong_dau(n)]
        dang_chay = [d for d in dang_chay if loc in khong_dau(d["image"]) or loc in khong_dau(d["title"])]
    return json.dumps({
        "installed": sorted(installed, key=khong_dau)[:_LIST_MAX],
        "installed_total": len(installed),
        "running": dang_chay[:_LIST_MAX],
        "hint": "Gọi javis_app_open với name là tên trong installed (hoặc bí danh như chrome, "
                "word, máy tính); javis_app_close với name khớp app/title trong running.",
    }, ensure_ascii=False)


def resolve_open(name: str, vault_root: Optional[str]) -> Tuple[str, str, str]:
    """(target, kind, mô tả) hoặc ("", "", lý do không tìm thấy)."""
    n = str(name or "").strip()
    if not n:
        return "", "", "thiếu name: tên app, URL hoặc đường dẫn."
    low = n.lower()
    if low.startswith(("http://", "https://")):
        return n, "url", n
    # Đường dẫn tuyệt đối: chỉ trong home hoặc brain.
    p = Path(n)
    if p.is_absolute():
        if not p.exists():
            return "", "", f"không thấy đường dẫn {n}."
        if not _duong_dan_cho_phep(p, vault_root):
            return "", "", ("đường dẫn nằm ngoài thư mục người dùng và ngoài brain, tool không mở "
                            "để tránh chạy nhầm file hệ thống.")
        return str(p), "path", str(p)
    installed = _installed()
    ten = [a["name"] for a in installed]
    hit, s = best_match(n, ten)
    if hit:
        app = next(a for a in installed if a["name"] == hit)
        return app["path"], ("lnk" if IS_WIN else "app"), hit
    if IS_WIN:
        for cum in _cum_tim(n):
            lenh = cum.replace(" ", "")
            if lenh in _WIN_COMMANDS:
                return lenh, "command", lenh
    elif IS_MAC:
        return n, "app", n     # `open -a` tự tìm theo tên
    goi_y = [c for c, sc in ((c, best_match(n, [c])[1]) for c in ten) if sc >= 0.5][:5]
    return "", "", (f"không thấy app nào tên giống '{n}' trong máy."
                    + (f" Gần giống: {', '.join(goi_y)}." if goi_y else "")
                    + " Gọi javis_app_list để xem danh sách.")


def _open(args, ctx) -> str:
    name = str((args or {}).get("name") or "")
    target, kind, mo_ta = resolve_open(name, getattr(ctx, "vault_root", None))
    if not target:
        return "ERROR: " + mo_ta
    err = _launch(target, kind)
    if err:
        return f"ERROR: không mở được {mo_ta} ({err})."
    loai = {"url": "địa chỉ", "path": "file", "lnk": "app", "app": "app", "command": "app"}[kind]
    return f"Đã mở {loai} {mo_ta}."


def resolve_close(name: str, running: List[dict]) -> Tuple[str, str]:
    """(image, lý do rỗng) hoặc ("", lý do)."""
    n = str(name or "").strip()
    if not n:
        return "", "thiếu name: tên app đang chạy."
    images = sorted({r["image"] for r in running})
    # Khớp theo ảnh tiến trình trước, rồi theo tiêu đề cửa sổ.
    hit, s = best_match(n, images, nguong=0.8)
    if not hit:
        best, best_s = "", 0.0
        for r in running:
            if not r.get("title"):
                continue
            for cum in _cum_tim(n):
                if cum and cum in khong_dau(r["title"]):
                    sc = 0.85 + min(0.1, len(cum) / 100)
                    if sc > best_s:
                        best, best_s = r["image"], sc
        hit = best
    if not hit:
        return "", f"không thấy app nào đang chạy khớp '{n}'. Gọi javis_app_list để xem app đang chạy."
    if hit.lower() in _PROTECTED:
        return "", f"'{hit}' là tiến trình hệ thống hoặc chính Javis, tool không đóng."
    return hit, ""


def _close(args, ctx) -> str:
    name = str((args or {}).get("name") or "")
    force = bool((args or {}).get("force"))
    running = _list_running()
    image, why = resolve_close(name, running)
    if not image:
        return "ERROR: " + why
    out = _kill(image, force)
    if out.startswith("__ERR__"):
        return f"ERROR: không đóng được {image} ({out[8:]})."
    # Đóng lịch sự thì đợi một nhịp rồi kiểm lại: app đang hỏi lưu sẽ còn sống.
    if not force:
        time.sleep(1.5)
        con = [r for r in _list_running() if r["image"].lower() == image.lower()]
        if con:
            return (f"Đã gửi lệnh đóng tới {image} nhưng nó vẫn đang chạy ({len(con)} cửa sổ), có thể "
                    f"đang hỏi lưu tài liệu. Người dùng muốn ép tắt thì gọi lại với force=true.")
    return f"Đã đóng {image}." + (" (ép tắt)" if force else "")


def register(ctx):
    ctx.register_tool(
        name="javis_app_list",
        description=("Liệt kê app đã cài và app đang chạy trên máy đang chạy Javis. Dùng khi người "
                     "dùng hỏi 'đang mở app nào', 'máy có app gì', hoặc trước khi mở/đóng mà chưa chắc tên. "
                     "filter: lọc theo chuỗi (tuỳ chọn)."),
        handler=_list, min_mode="readonly", check_fn=check_ready,
        schema={"type": "object", "properties": {"filter": {"type": "string"}}},
    )
    ctx.register_tool(
        name="javis_app_open",
        description=("MỞ một app / địa chỉ web / file trên máy đang chạy Javis, làm ngay không hỏi lại. "
                     "name: tên app (khớp mờ, có bí danh: chrome, edge, word, excel, máy tính, notepad, "
                     "vscode, zalo...), hoặc URL http(s), hoặc đường dẫn tuyệt đối trong thư mục người "
                     "dùng / trong brain. Dùng khi người dùng nói 'mở Chrome', 'bật Excel lên', "
                     "'mở trang youtube.com'."),
        handler=_open, min_mode="safe", check_fn=check_ready,
        schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    )
    ctx.register_tool(
        name="javis_app_close",
        description=("ĐÓNG một app đang chạy trên máy đang chạy Javis, làm ngay không hỏi lại. name: tên "
                     "app hoặc tiêu đề cửa sổ. Mặc định đóng lịch sự (app có tài liệu chưa lưu sẽ tự hỏi "
                     "lưu); force=true chỉ khi người dùng nói 'ép tắt' / 'tắt hẳn'. Dùng khi người dùng nói "
                     "'tắt Chrome', 'đóng Excel'."),
        handler=_close, min_mode="full", check_fn=check_ready,
        schema={"type": "object", "properties": {"name": {"type": "string"},
                                                 "force": {"type": "boolean"}},
                "required": ["name"]},
    )
