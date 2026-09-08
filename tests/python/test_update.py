"""Test tầng cập nhật: update_state (thuần) + endpoint /update/status + updater dry-run.
Chạy:  python tests/run.py update    (KHÔNG mạng)."""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import os, sys, tempfile, json
os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-update-test-")

_fails = []
def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)

import update_state as us  # noqa: E402

# --- version compare ---
check("ver_newer 0.9.79 > 0.9.78", us.ver_newer("0.9.79", "0.9.78") is True)
check("ver_newer bằng nhau - False", us.ver_newer("1.0.0", "1.0.0") is False)
check("ver_newer local ahead - False", us.ver_newer("0.9.78", "0.9.79") is False)
check("ver_tuple rác - coi như (0,0,0), không crash", us.ver_tuple("abc") == (0, 0, 0))

# --- state round-trip ---
us.write_state({"phase": "installing", "old_version": "0.9.78"})
st = us.read_state()
check("write/read state giữ phase", st.get("phase") == "installing")
check("write/read state giữ old_version", st.get("old_version") == "0.9.78")
us.write_state({"phase": "done"})
check("write_state merge (không mất field cũ)", us.read_state().get("old_version") == "0.9.78")

# --- record_boot_version ---
us.STATE_FILE.unlink(missing_ok=True)
us.record_boot_version("0.9.78")
check("boot lần đầu: last_good = current", us.read_state().get("last_good_version") == "0.9.78")
check("boot lần đầu: chưa có previous", us.read_state().get("previous_version") is None)
us.record_boot_version("0.9.79")
check("boot lên bản mới: last_good cập nhật", us.read_state().get("last_good_version") == "0.9.79")
check("boot lên bản mới: previous = bản cũ", us.read_state().get("previous_version") == "0.9.78")

# --- update_outcome ---
check("health đỏ - need_rollback", us.update_outcome(False, "0.9.79", "0.9.78", "0.9.79") == "need_rollback")
check("health xanh + đúng target - success", us.update_outcome(True, "0.9.79", "0.9.78", "0.9.79") == "success")
check("health xanh + version tiến (target rỗng) - success", us.update_outcome(True, "0.9.79", "0.9.78", None) == "success")
check("health xanh nhưng version chưa đổi - version_mismatch", us.update_outcome(True, "0.9.78", "0.9.78", "0.9.79") == "version_mismatch")

# --- update_state: phủ thêm hợp đồng hàm ---
check("ver_tuple số hợp lệ -> tuple 3 phần", us.ver_tuple("1.2.3") == (1, 2, 3))
check("ver_tuple bỏ tiền tố v", us.ver_tuple("v2.0.0") == (2, 0, 0))
# health xanh + version tiến qua old nhưng CHƯA tới target (main nhích trong lúc pull):
# vẫn coi là success - KHÔNG rollback một bản đang chạy khoẻ chỉ vì chưa phải bản mới nhất.
check("outcome: khoẻ + tiến qua old dù chưa tới target -> success",
      us.update_outcome(True, "0.9.79", "0.9.78", "0.9.80") == "success")
us.STATE_FILE.unlink(missing_ok=True)
us.record_boot_version("1.0.0")
us.record_boot_version("1.0.0")
check("boot lại cùng phiên bản -> không đặt previous", us.read_state().get("previous_version") is None)
us.STATE_FILE.write_text("{khong-phai-json", encoding="utf-8")
check("read_state gặp JSON hỏng -> trả {}", us.read_state() == {})
us.STATE_FILE.unlink(missing_ok=True)

# --- main.py dùng update_state + /version có previous_version ---
import asyncio  # noqa: E402
import main  # noqa: E402

# Stub httpx để suite KHÔNG chạm mạng: fetch VERSION/CHANGELOG từ GitHub là best-effort,
# ta ép nó "không có" (404) nên version_info -> latest=None, do_update -> latest=None.
import httpx as _httpx  # noqa: E402
class _FakeResp:
    def __init__(self, status_code=404, text=""):
        self.status_code = status_code
        self.text = text
class _FakeClient:
    def __init__(self, *a, **k):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False
    async def get(self, *a, **k):
        return _FakeResp(404, "")
_httpx.AsyncClient = _FakeClient

check("main alias _ver_newer chạy", main._ver_newer("0.9.79", "0.9.78") is True)
us.STATE_FILE.unlink(missing_ok=True)
us.write_state({"previous_version": "0.9.77"})
_v = asyncio.run(main.version_info())
check("/version có khoá previous_version", "previous_version" in _v)
check("/version previous_version đúng giá trị", _v.get("previous_version") == "0.9.77")

# --- hook boot dùng ĐÚNG cặp hàm (bắt lỗi đổi tên/chữ ký làm hook fail âm thầm) ---
us.STATE_FILE.unlink(missing_ok=True)
_bs = main._record_boot_version(main._read_version())
check("hook boot: _record_boot_version(_read_version()) chạy + đặt last_good = bản hiện tại",
      _bs.get("last_good_version") == main._read_version())

# --- /update/status ---
us.write_state({"phase": "health_check", "result": None})
(us.STATE_DIR / "update.log").write_text("dong 1\ndong 2\ndong 3\n", encoding="utf-8")
_s = asyncio.run(main.update_status())
check("/update/status trả state.phase", _s["state"].get("phase") == "health_check")
check("/update/status trả log_tail", "dong 3" in _s["log_tail"])

# --- POST /update chống chạy trùng ---
from fastapi.responses import JSONResponse  # noqa: E402
import datetime as _dtmod  # noqa: E402
_recent_iso = _dtmod.datetime.now().isoformat(timespec="seconds")
us.write_state({"phase": "pulling", "started_at": _recent_iso})
_r = asyncio.run(main.do_update())
check("update đang chạy (started_at gần đây) → 409", isinstance(_r, JSONResponse) and _r.status_code == 409)
us.write_state({"phase": "idle"})  # dọn để không kẹt
check("có hàm _git_head", callable(getattr(main, "_git_head", None)))
check("có hàm _update_recent", callable(getattr(main, "_update_recent", None)))
check("_update_recent: started_at rất cũ → False", main._update_recent("2000-01-01T00:00:00") is False)
check("_update_recent: started_at bây giờ → True", main._update_recent(_dtmod.datetime.now().isoformat(timespec="seconds")) is True)
check("_update_recent: rỗng → False", main._update_recent("") is False)
# phase 'đang dở' NHƯNG started_at rất cũ (docker để restarting mãi / updater chết) -> KHÔNG được kẹt 409:
# dùng mock docker+no-watchtower để chứng minh nó ĐI QUA guard và trả 400 (không 409), không spawn updater.
_om = main._deploy_mode
_ow = main._watchtower_reachable
async def _wt_no():
    return False
main._deploy_mode = lambda: "docker"
main._watchtower_reachable = _wt_no
us.write_state({"phase": "restarting", "started_at": "2000-01-01T00:00:00"})
_rs = asyncio.run(main.do_update())
check("phase cũ kẹt (started_at rất cũ) → KHÔNG 409, cho chạy lại (docker→400)",
      isinstance(_rs, JSONResponse) and _rs.status_code == 400)
main._deploy_mode = _om
main._watchtower_reachable = _ow
us.write_state({"phase": "idle"})

# --- claim rồi nhả: docker không watchtower → 400 + phase reset idle (chống kẹt "preparing") ---
_orig_mode = main._deploy_mode
_orig_wt = main._watchtower_reachable
async def _wt_false():
    return False
main._deploy_mode = lambda: "docker"
main._watchtower_reachable = _wt_false
us.write_state({"phase": "idle"})
_rd = asyncio.run(main.do_update())
check("docker no-watchtower → 400", isinstance(_rd, JSONResponse) and _rd.status_code == 400)
check("early-return nhả claim → phase idle (không kẹt preparing)", us.read_state().get("phase") == "idle")
main._deploy_mode = _orig_mode
main._watchtower_reachable = _orig_wt

# --- updater.py --dry-run (không thực thi git/pip) ---
import subprocess as _sp  # noqa: E402
_upd = os.path.join(str(SERVER), "updater.py")
_p = _sp.run([sys.executable, _upd, "--dry-run", "--port", "7777", "--server-pid", "123"],
             capture_output=True, text=True, env={**os.environ})
check("updater --dry-run (kèm --server-pid) thoát 0", _p.returncode == 0)
check("updater --dry-run in PLAN", "PLAN:" in (_p.stdout or ""))

# --- updater: 4 chế độ restart (bug thật: Mac không có systemd bị chặn cứng không update được;
# rồi 14/08/2026 Mac CÓ launchd mà updater kill PID + nohup → launchd respawn giành cổng 7777) ---
import updater as _updmod  # noqa: E402
check("service_mode: Windows -> windows", _updmod.service_mode("nt") == "windows")
check("service_mode: Linux có systemd -> systemd",
      _updmod.service_mode("posix", systemd=True, launchd=False) == "systemd")
check("service_mode: Mac/không launchd, không systemd -> nohup (KHÔNG bail lỗi)",
      _updmod.service_mode("posix", systemd=False, launchd=False) == "nohup")
check("service_mode: Mac có launchd job -> launchd (ưu tiên trước cả systemd)",
      _updmod.service_mode("posix", systemd=True, launchd=True) == "launchd")
_upd_src = open(_upd, encoding="utf-8").read()
check("updater không còn nhánh chặn 'Không có systemd service'",
      "Không có systemd service" not in _upd_src)
check("chế độ launchd đổi ca bằng kickstart -k, KHÔNG kill PID + nohup (hết đua bind cổng)",
      "kickstart" in _upd_src and 'mode == "launchd"' in _upd_src)
check("has_launchd_job không bao giờ bật ngoài Mac (Linux CI không được gọi launchctl)",
      sys.platform == "darwin" or _updmod.has_launchd_job() is False)

# --- /version báo platform để UI ghi đúng nhãn (Mac từng bị dán 'Linux (systemd)') ---
_v2 = asyncio.run(main.version_info())
check("/version có khoá platform", _v2.get("platform") in ("windows", "mac", "linux"))
_console_src = (main.DASHBOARD_PATH / "console.js").read_text(encoding="utf-8")
check("console.js hết hardcode nhãn 'Linux (systemd)'", "Linux (systemd)" not in _console_src)
check("console.js có nhãn macOS theo platform", "macOS" in _console_src)
check("main.py truyền --server-pid cho updater",
      "--server-pid" in open(os.path.join(str(SERVER), "main.py"), encoding="utf-8").read())

# Khoá cache tĩnh phải do SERVER tính, không phải số gõ tay. Bug thật: console.js?v=72 đứng
# yên suốt hàng chục bản nên trình duyệt dùng bản CŨ trong cache, mọi sửa frontend vô hình.
#
# 06/09 đổi khoá từ <phiên bản app> sang <vân tay crc32 từng file>. Lý do: khoá theo phiên bản
# làm cả 42 file đổi URL mỗi lần bump VERSION, cache immutable trượt sạch, trình duyệt kéo lại
# trọn 1,6 MB - đúng câu người dùng báo "update xong app vào chậm". Bất biến cần giữ vẫn thế
# (không file nào mang khoá chết), chỉ mạnh thêm: khoá bám NỘI DUNG chứ không bám số phiên bản.
import asyncio as _aio  # noqa: E402
_html = _aio.run(main.root()).body.decode("utf-8")
_ver = main._app_version()
import re as _re2  # noqa: E402
_khoa = dict(_re2.findall(r'/static/(\S+?\.(?:js|css))\?v=([\w.]+)', _html))
check("mọi file .js/.css đều được gắn khoá cache, không sót cái nào",
      len(_khoa) > 30 and all(v for v in _khoa.values()))
check("KHÔNG còn khoá cache gõ tay ?v=72 (đã thay bằng khoá server tính)",
      "?v=72" not in _html)
_fps = main._asset_fps(_html)
check("khoá là VÂN TAY nội dung của chính file đó",
      _khoa.get("console.js") == _fps.get("console.js") != None)
# Đây mới là điều bản vá đánh đổi để lấy: sửa MỘT file thì chỉ file đó bể cache.
_truoc = dict(_khoa)
_cjs = main.DASHBOARD_PATH / "console.js"
_goc = _cjs.read_bytes()
try:
    _cjs.write_bytes(_goc + b"\n// canary\n")
    _sau = dict(_re2.findall(r'/static/(\S+?\.(?:js|css))\?v=([\w.]+)',
                             _aio.run(main.root()).body.decode("utf-8")))
    check("sửa console.js thì RIÊNG nó đổi khoá",
          _sau.get("console.js") != _truoc.get("console.js"))
    _lay = [k for k in _truoc if k != "console.js" and _sau.get(k) != _truoc[k]]
    check("và mọi file khác GIỮ NGUYÊN khoá (cache vẫn ăn qua bản cập nhật)", not _lay)
finally:
    _cjs.write_bytes(_goc)

# --- Hộp thư thông báo: dữ liệu cộng đồng + release hợp nhất ---
_ann_raw = json.dumps({
    "announcements": [
        {
            "id": "tin-hop-le",
            "kind": "marketing",
            "title": "Tin hợp lệ",
            "summary": "Nội dung",
            "published_at": "2099-01-01",
            "priority": "high",
            "cta": {"label": "Xem", "url": "https://javisos.com"},
        },
        {
            "id": "tin-het-han",
            "kind": "community",
            "title": "Tin hết hạn",
            "expires_at": "2000-01-01",
        },
        {
            "id": "tin-url-xau",
            "kind": "marketing",
            "title": "Không chạy javascript URL",
            "cta": {"label": "Xấu", "url": "javascript:alert(1)"},
        },
    ]
}, ensure_ascii=False)
_anns = main._parse_announcements(_ann_raw)
check("announcement hợp lệ được parse", any(x["id"] == "tin-hop-le" for x in _anns))
check("announcement hết hạn bị lọc", not any(x["id"] == "tin-het-han" for x in _anns))
_bad_url = next((x for x in _anns if x["id"] == "tin-url-xau"), {})
check("announcement chặn javascript URL", not (_bad_url.get("cta") or {}).get("url"))

main._NOTIFICATION_CACHE.update({"at": 0.0, "data": None})
_notifications = _aio.run(main.notifications_info())
check("/notifications hợp nhất dữ liệu", _notifications.get("unified") is True)
check("/notifications có tin cộng đồng local", any(
    x.get("id") == "community-notification-inbox-launch"
    for x in _notifications.get("items", [])
))
check("/notifications có release tự động", any(
    x.get("kind") == "update" and x.get("id", "").startswith("release:")
    for x in _notifications.get("items", [])
))
_index_text = (main.DASHBOARD_PATH / "index.html").read_text(encoding="utf-8")
_noti_js = (main.DASHBOARD_PATH / "notifications.js").read_text(encoding="utf-8")
_mobile_js = (main.DASHBOARD_PATH / "mobile-chat.js").read_text(encoding="utf-8")
check("navbar có nút chuông và panel thông báo",
      'id="notificationTrigger"' in _index_text and 'id="notificationPanel"' in _index_text)
check("frontend ghi nhớ đã đọc", "javis.notifications.read" in _noti_js)
check("hộp thư giới hạn 5 tin và có tải thêm",
      "PAGE_SIZE = 5" in _noti_js and "notificationLoadMore" in _noti_js)
check("release không render toàn bộ body trong card",
      'kind !== "update" && item.body' in _noti_js)
check("nút chuông được dời lên header mobile", "origNotificationParent" in _mobile_js)

print()
if _fails:
    print(f"{len(_fails)} FAIL: {_fails}"); sys.exit(1)
print("TẤT CẢ PASS")
