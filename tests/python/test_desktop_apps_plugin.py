"""Plugin desktop-apps: mở / đóng / liệt kê app trên máy chạy Javis.

    python tests/run.py desktop_apps

Không mở gì thật: bốn hàm hệ thống (_scan_installed, _list_running, _launch, _kill) bị thay
bằng hàm giả và ghi lại lời gọi. Test khoá:
  1. Khớp mờ: bí danh tiếng Việt / tiếng Anh, không dấu, exact thắng contains, dưới ngưỡng thì
     không mở bừa.
  2. Chạy trong Docker -> check_fn trả câu lý do (tool bị chặn với câu đó, không phải im).
  3. Mở: URL đi thẳng; đường dẫn tuyệt đối ngoài home và ngoài brain bị chặn; app khớp -> gọi
     _launch đúng target.
  4. Đóng: khớp ảnh tiến trình rồi tiêu đề cửa sổ; tiến trình hệ thống không bao giờ đóng; đóng
     lịch sự còn sống thì báo và gợi ý force; force=true gọi _kill với force.
  5. Manifest: enabled, ba tool, min_mode đúng mức (list readonly, open safe, close full).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-dapps-")

import plugins_host  # noqa: E402
import deploy_info  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


spec = importlib.util.spec_from_file_location(
    "desktop_apps_plugin", ROOT / "system" / "plugins" / "desktop-apps" / "plugin.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# ---- Hàm giả ----
INSTALLED = [
    {"name": "Google Chrome", "path": "C:/sm/Google Chrome.lnk"},
    {"name": "Microsoft Edge", "path": "C:/sm/Microsoft Edge.lnk"},
    {"name": "Excel", "path": "C:/sm/Excel.lnk"},
    {"name": "Word", "path": "C:/sm/Word.lnk"},
    {"name": "WordPad", "path": "C:/sm/WordPad.lnk"},
    {"name": "Visual Studio Code", "path": "C:/sm/Visual Studio Code.lnk"},
    {"name": "Zalo", "path": "C:/sm/Zalo.lnk"},
    {"name": "Antigravity", "path": "C:/sm/Antigravity.lnk"},
]
RUNNING = [
    {"image": "chrome.exe", "pid": "1", "title": "YouTube - Google Chrome"},
    {"image": "chrome.exe", "pid": "2", "title": ""},
    {"image": "EXCEL.EXE", "pid": "3", "title": "Doanh thu T9.xlsx - Excel"},
    {"image": "explorer.exe", "pid": "4", "title": "Tải xuống"},
    {"image": "sublime_text.exe", "pid": "5", "title": "bài viết.md - Sublime Text"},
    {"image": "python.exe", "pid": "6", "title": ""},
]
calls = {"launch": [], "kill": []}
state = {"running": list(RUNNING)}

m._scan_installed = lambda: list(INSTALLED)
m._CACHE["t"] = 0.0
m._list_running = lambda: list(state["running"])
m._launch = lambda target, kind: (calls["launch"].append((target, kind)) or "")


def _fake_kill(image, force):
    calls["kill"].append((image, force))
    if force or image == "sublime_text.exe":
        state["running"] = [r for r in state["running"] if r["image"].lower() != image.lower()]
    return ""


m._kill = _fake_kill
m.time.sleep = lambda s: None   # đóng lịch sự có chờ 1,5 giây - bỏ chờ trong test


class Ctx:
    vault_root = str(Path(tempfile.mkdtemp(prefix="javis-brain-")))


ctx = Ctx()

# ---- 1. Khớp mờ ----
ten = [a["name"] for a in INSTALLED]
check("khớp: 'chrome' -> Google Chrome", m.best_match("chrome", ten)[0] == "Google Chrome")
check("khớp: 'trình duyệt' -> một trình duyệt", m.best_match("trình duyệt", ten)[0] in ("Google Chrome", "Microsoft Edge"))
check("khớp: 'word' -> Word chứ không phải WordPad", m.best_match("word", ten)[0] == "Word")
check("khớp: 'vscode' -> Visual Studio Code", m.best_match("vscode", ten)[0] == "Visual Studio Code")
check("khớp: 'Antigraviti' (gõ sai) vẫn ra Antigravity", m.best_match("Antigraviti", ten)[0] == "Antigravity")
check("khớp: 'photoshop' không có -> rỗng", m.best_match("photoshop", ten)[0] == "")
check("khong_dau: bỏ dấu, đ->d, gộp khoảng trắng", m.khong_dau("  Máy  Tính Đặc biệt ") == "may tinh dac biet")

# ---- 2. Docker chặn ----
_goc = deploy_info.deploy_mode
deploy_info.deploy_mode = lambda: "docker"
why = m.check_ready()
check("docker: check_fn trả lý do nhắc máy chủ", isinstance(why, str) and "máy chủ" in why)
deploy_info.deploy_mode = lambda: "windows"
# CI chạy trên Linux không màn hình: giả DISPLAY để nhánh "Linux không có DISPLAY" không bắt nhầm.
_disp = os.environ.get("DISPLAY")
os.environ["DISPLAY"] = ":0"
check("windows/có màn hình: check_fn trả None", m.check_ready() is None)
if _disp is None:
    del os.environ["DISPLAY"]
else:
    os.environ["DISPLAY"] = _disp
deploy_info.deploy_mode = _goc

# ---- 3. Mở ----
out = m._open({"name": "https://youtube.com"}, ctx)
check("mở URL: gọi _launch kind=url, không nói là đã hiện lên",
      calls["launch"][-1] == ("https://youtube.com", "url") and out.startswith("[unverified]"))
# Opening an app that is not running: watched until a new process answers to it.
state["running"] = [r for r in RUNNING if r["image"] != "chrome.exe"]
_launch_goc = m._launch


def _launch_then_appears(target, kind):
    calls["launch"].append((target, kind))
    state["running"] = state["running"] + [{"image": "chrome.exe", "pid": "99", "title": "New Tab - Google Chrome"}]
    return ""


m._launch = _launch_then_appears
out = m._open({"name": "chrome"}, ctx)
check("mở app: _launch đúng đường dẫn shortcut", calls["launch"][-1][0] == "C:/sm/Google Chrome.lnk")
check("mở app: thấy tiến trình mới -> [done] nêu tên app", out.startswith("[done]") and "Google Chrome" in out)
m._launch = _launch_goc
state["running"] = [r for r in RUNNING if r["image"] != "chrome.exe"]
out = m._open({"name": "zalo"}, ctx)
check("mở app: không thấy tiến trình nào -> [unverified], dặn đừng nói là đã mở",
      out.startswith("[unverified]") and "Đừng nói là đã mở" in out)
# Already running with a window: raised, not launched a second time.
state["running"] = list(RUNNING)
raised = []
m._raise_window = lambda entry, running: (raised.append(entry["image"]) or (True, True))
n_truoc = len(calls["launch"])
out = m._open({"name": "chrome"}, ctx)
check("app đang chạy: đưa cửa sổ lên trước, không mở bản thứ hai",
      raised == ["chrome.exe"] and len(calls["launch"]) == n_truoc and out.startswith("[done]"))
m._raise_window = lambda entry, running: (True, False)
out = m._open({"name": "chrome"}, ctx)
check("đưa lên trước mà không đọc lại được -> [unverified]", out.startswith("[unverified]") and len(calls["launch"]) == n_truoc)
m._raise_window = lambda entry, running: (False, False)
out = m._open({"name": "chrome"}, ctx)
check("không đưa lên được (app nằm khay) -> rơi về mở như cũ", len(calls["launch"]) == n_truoc + 1)
state["running"] = list(RUNNING)
out = m._open({"name": "photoshop"}, ctx)
check("mở app không có: ERROR [failed] + gợi ý gọi list", out.startswith("ERROR: [failed]") and "javis_app_list" in out)
out = m._open({"name": "zallo app"}, ctx)
check("tên gần giống mà không chắc: [ask], không mở bừa", out.startswith("[ask]") and "Zalo" in out)
n_truoc = len(calls["launch"])
ngoai = Path(tempfile.gettempdir()).resolve()
# Tìm một đường dẫn tuyệt đối TỒN TẠI nằm ngoài home lẫn brain (thư mục gốc ổ đĩa hoặc /etc).
ngoai_home = None
for cand in (Path(os.environ.get("SystemRoot", "C:/Windows")), Path("/etc"), Path("/usr")):
    if cand.exists():
        try:
            cand.resolve().relative_to(Path.home().resolve())
        except ValueError:
            ngoai_home = cand
            break
if ngoai_home is not None:
    out = m._open({"name": str(ngoai_home)}, ctx)
    check("mở đường dẫn ngoài home/brain: chặn, không _launch",
          out.startswith("ERROR") and len(calls["launch"]) == n_truoc)
trong_brain = Path(ctx.vault_root) / "bao-cao.md"
trong_brain.write_text("x", encoding="utf-8")
out = m._open({"name": str(trong_brain)}, ctx)
check("mở file trong brain: được, kind=path", calls["launch"][-1][1] == "path" and out.startswith("[unverified]"))
n_truoc = len(calls["launch"])
for duoi in (".bat", ".cmd", ".ps1", ".exe", ".vbs", ".lnk", ".sh", ".command"):
    f = Path(ctx.vault_root) / f"chay{duoi}"
    f.write_text("echo x", encoding="utf-8")
    out = m._open({"name": str(f)}, ctx)
    check(f"CANARY: file chạy được {duoi} trong brain KHÔNG được mở (lượt auto có thể vừa ghi nó)",
          out.startswith("ERROR") and len(calls["launch"]) == n_truoc)
out = m._open({"name": ""}, ctx)
check("mở thiếu name: ERROR", out.startswith("ERROR"))

# ---- 4. Đóng ----
img, why = m.resolve_close("chrome", RUNNING)
check("đóng: 'chrome' -> chrome.exe", img == "chrome.exe")
img, why = m.resolve_close("excel", RUNNING)
check("đóng: 'excel' -> EXCEL.EXE (không phân biệt hoa thường)", img == "EXCEL.EXE")
img, why = m.resolve_close("sublime", RUNNING)
check("đóng: khớp theo tiêu đề/ảnh 'sublime'", img == "sublime_text.exe")
img, why = m.resolve_close("bài viết", RUNNING)
check("đóng: khớp theo tiêu đề cửa sổ tiếng Việt", img == "sublime_text.exe")
img, why = m.resolve_close("explorer", RUNNING)
check("đóng: explorer là hệ thống -> chặn", img == "" and "hệ thống" in why)
img, why = m.resolve_close("python", RUNNING)
check("đóng: python (chính Javis) -> chặn", img == "")
img, why = m.resolve_close("photoshop", RUNNING)
check("đóng: không chạy -> lý do nêu javis_app_list", img == "" and "javis_app_list" in why)

out = m._close({"name": "chrome"}, ctx)
check("đóng lịch sự: gọi _kill force=False", calls["kill"][-1] == ("chrome.exe", False))
check("đóng lịch sự còn sống: [unverified], gợi ý force", out.startswith("[unverified]") and "force=true" in out and "vẫn đang chạy" in out)
out = m._close({"name": "chrome", "force": True}, ctx)
check("ép tắt: gọi _kill force=True", calls["kill"][-1] == ("chrome.exe", True))
check("ép tắt: đọc lại thấy đã tắt -> [done]", out.startswith("[done] Đã đóng") and "ép tắt" in out)
out = m._close({"name": "sublime"}, ctx)
check("đóng lịch sự mà app tắt thật: [done]", out.startswith("[done] Đã đóng sublime_text.exe"))
state["running"] = list(RUNNING)
m._kill = lambda image, force: ""   # the OS refuses: the process survives even a forced kill
out = m._close({"name": "excel", "force": True}, ctx)
check("ép tắt mà vẫn chạy -> ERROR [failed], không báo đã đóng", out.startswith("ERROR: [failed]") and "vẫn đang chạy" in out)
m._kill = _fake_kill
out = m._close({"name": "explorer"}, ctx)
check("đóng explorer qua handler: ERROR, không gọi _kill", out.startswith("ERROR") and calls["kill"][-1][0] != "explorer.exe")

# ---- 4b. Short names match exactly (0.221.0) ----
check("'wp' không khớp mờ sang wps.exe", m.best_match("wp", ["WPS Office", "WhatsApp"])[0] == "")
check("'cmd' (bí danh ngắn) vẫn khớp đúng tên cmd", m.best_match("cmd", ["cmd", "cmdkey"])[0] == "cmd")
img, why = m.resolve_close("wp", RUNNING + [{"image": "wps.exe", "pid": "7", "title": "WPS Office"}])
check("đóng 'wp' không đóng nhầm wps.exe", img == "")
check("image_matches: Visual Studio Code -> Code.exe", m.image_matches("Visual Studio Code", "Code.exe"))
check("image_matches: Microsoft Edge -> msedge.exe", m.image_matches("Microsoft Edge", "msedge.exe"))
check("image_matches: Google Chrome -> chrome.exe", m.image_matches("Google Chrome", "chrome.exe"))
check("image_matches: Zalo không khớp chrome.exe", not m.image_matches("Zalo", "chrome.exe"))
check("mô tả tool dặn [unverified] không được nói là xong", "[unverified]" in m.OUTCOME_RULE and "KHÔNG BAO GIỜ" in m.OUTCOME_RULE)

# ---- 5. Liệt kê ----
import json
state["running"] = list(RUNNING)   # các test đóng ở trên đã "tắt" chrome trong danh sách giả
d = json.loads(m._list({"filter": "chrome"}, ctx))
check("list lọc: installed chỉ còn Chrome", d["installed"] == ["Google Chrome"])
check("list: running gom theo ảnh, có tiêu đề", any(r["image"] == "chrome.exe" and r["windows"] == 2 for r in json.loads(m._list({}, ctx))["running"]))

# ---- 6. Manifest qua plugins_host ----
desc = {x["slug"]: x for x in plugins_host.describe(None)}
check("manifest: có slug desktop-apps, enabled", desc.get("desktop-apps", {}).get("enabled") is True)
check("manifest: nạp không lỗi", desc.get("desktop-apps", {}).get("loaded") is True and not desc["desktop-apps"]["error"])
tools, route = plugins_host.plugin_tools("full", None)
mm = {t["fn"]: route[t["fn"]]["required_mode"] for t in tools if t["fn"].startswith("javis_app_")}
check("mức quyền: list readonly, open safe, close full",
      mm == {"javis_app_list": "readonly", "javis_app_open": "safe", "javis_app_close": "full"})
tools_s, route_s = plugins_host.plugin_tools("suggest", None)
res = asyncio.run(route_s["javis_app_open"]["call"]({"name": "chrome"}))
check("chế độ suggest: mở app bị chặn bằng code", res.startswith("ERROR") and "mức quyền" in res)

if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - desktop-apps")
