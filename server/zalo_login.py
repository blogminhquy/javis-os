"""
Đăng nhập Zalo bằng QR ngay trong UI Javis (connector "zalo" - CLI javis-zalo).
Flow: POST /connect/zalo/start → spawn `npx -y --prefer-offline <gói> login --json` với HOME
cô lập riêng cho tài khoản → bắt event {"event":"qr", dataUrl} đưa lên modal →
user quét bằng app Zalo → thành công thì TỰ TẠO connection (config.home_dir trỏ
home cô lập đó, mcp_store.resolved tự set env HOME/USERPROFILE khi chạy MCP).

Đã verify (zalo-agent-cli 1.6.2, giữ nguyên ở javis-zalo 1.0.0): account active là TOÀN CỤC theo home dir
(thư mục phiên vẫn tên ~/.zalo-agent-cli để tài khoản đã đăng nhập không bị đăng xuất)
→ mỗi connection 1 home riêng để nhiều tài khoản Zalo chạy song song.
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid

import mcp_store
import localefmt
import winproc
from config import STATE_DIR

_TIMEOUT = 180        # QR Zalo sống ngắn - quá 3 phút coi như hết hạn
_SESS_TTL = 900
_sessions = {}        # sid -> {state, qr, label, conn_id, error, proc, home, ts}

_SUCCESS_EVENTS = {"login", "login_success", "success", "ready", "logged_in", "authenticated"}
_ERROR_EVENTS = {"error", "failed", "login_error"}   # CLI in {"event":"login_error","message":...} khi QR hỏng
_CLI_PACKAGE = "https://codeload.github.com/blogminhquy/javis-zalo/tar.gz/refs/tags/v1.13.0"  # trùng zalo_cli.CLI_PACKAGE và catalog


def _sweep():
    now = time.time()
    for sid in [k for k, v in _sessions.items() if now - v["ts"] > _SESS_TTL]:
        cancel(sid)
        _sessions.pop(sid, None)


def _npx_argv():
    npx = shutil.which("npx")
    if not npx:
        return None
    argv = [npx, "-y", "--prefer-offline", _CLI_PACKAGE, "login", "--json"]
    if npx.lower().endswith((".cmd", ".bat")):
        argv = ["cmd.exe", "/c"] + argv
    return argv


def _qr_from_event(obj, home):
    """Lấy dataUrl QR từ event: ưu tiên dataUrl > image > đọc file png."""
    for k in ("dataUrl", "data_url", "image"):
        v = obj.get(k)
        if isinstance(v, str) and v.startswith("data:image"):
            return v
    f = obj.get("file")
    if isinstance(f, str) and os.path.isfile(f):
        try:
            return "data:image/png;base64," + base64.b64encode(open(f, "rb").read()).decode("ascii")
        except OSError:
            pass
    # fallback: file mặc định của CLI trong home cô lập
    p = os.path.join(home, ".zalo-agent-cli", "qr.png")
    if os.path.isfile(p):
        try:
            return "data:image/png;base64," + base64.b64encode(open(p, "rb").read()).decode("ascii")
        except OSError:
            pass
    return ""


def account_ids(home) -> set:
    """Zalo account ids (ownId) signed in under one session folder: the CLI's `accounts.json` registry plus its
    `credentials/cred_<ownId>.json` files. Empty when the folder holds neither."""
    base = os.path.join(str(home or ""), ".zalo-agent-cli")
    ids = set()
    try:
        with open(os.path.join(base, "accounts.json"), encoding="utf-8") as f:
            data = json.load(f)
        rows = data.get("accounts") if isinstance(data, dict) else data
        for a in rows if isinstance(rows, list) else []:
            if isinstance(a, dict) and str(a.get("ownId") or "").strip():
                ids.add(str(a["ownId"]).strip())
    except (OSError, ValueError):
        pass
    try:
        for name in os.listdir(os.path.join(base, "credentials")):
            if name.startswith("cred_") and name.endswith(".json") and len(name) > 10:
                ids.add(name[5:-5])
    except OSError:
        pass
    return ids


def _same_account(own_ids: set, home: str):
    """The saved Zalo connection already signed in as one of `own_ids`, in another folder than `home`, or None.

    Field reports 19-20/11/2026: a second Zalo connection is only safe when it is another account. Zalo keeps one live
    socket per account, so two connections of the same nick evict each other and both bots miss most messages. The
    phone that scans the QR decides the account, and nothing on the page showed it was the nick already connected."""
    if not own_ids:
        return None
    try:
        conns = mcp_store.resolved(enabled_only=False)
    except Exception:       # noqa: BLE001 - unsure means do not block a sign-in
        return None
    for c in conns:
        if c.get("connector_id") != "zalo":
            continue
        h = str(((c.get("env") or {}).get("HOME")) or ((c.get("config") or {}).get("home_dir")) or "")
        if not h or os.path.realpath(h) == os.path.realpath(home):
            continue
        if own_ids & account_ids(h):
            return c
    return None


def _finish_ok(sess, obj):
    own = {str(obj.get(k)).strip() for k in ("ownId", "own_id") if str(obj.get(k) or "").strip()}
    dup = _same_account(own | account_ids(sess["home"]), sess["home"])
    if dup:
        ten = str(dup.get("label") or "Zalo")
        sess.update(state="error", duplicate=True, error=localefmt.chu(
            f"Nick Zalo vừa quét đã kết nối sẵn ở \"{ten}\". Hai kết nối cùng một nick sẽ giành nhau và bot lỡ tin, nên "
            "Javis không thêm kết nối này. Muốn nối nick khác: mở app Zalo bằng nick đó rồi quét lại.",
            f"The Zalo account you scanned is already connected as \"{ten}\". Two connections of one account take the "
            "connection from each other and the bots miss messages, so Javis did not add this one. To connect another "
            "account, open the Zalo app signed in as that account and scan again."))
        return
    label = (obj.get("displayName") or obj.get("display_name") or obj.get("name")
             or obj.get("ownId") or obj.get("own_id") or sess["label"] or "Zalo")
    cid, err = mcp_store.add_connection("zalo", {
        "label": str(label)[:60],
        "config": {"home_dir": sess["home"]},
    })
    if err:
        sess.update(state="error", error=localefmt.chu(f"Đăng nhập được nhưng không lưu kết nối: {err}",
                                                       f"Signed in, but the connection could not be saved: {err}"))
        return
    sess.update(state="done", label=str(label)[:60], conn_id=cid)
    try:
        import mcp_hub
        mcp_hub.invalidate_cache()
    except Exception:
        pass


def _reader(sid):
    sess = _sessions.get(sid)
    if not sess:
        return
    proc = sess["proc"]
    got_qr = False
    try:
        for raw in iter(proc.stdout.readline, ""):
            if sess.get("state") in ("done", "error"):
                break
            raw = (raw or "").strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue   # noise npx/log thường → bỏ qua
            if not isinstance(obj, dict):
                continue
            ev = str(obj.get("event") or "").lower()
            if ev == "qr":
                qr = _qr_from_event(obj, sess["home"])
                if qr:
                    got_qr = True
                    sess.update(state="qr", qr=qr)
                continue
            if ev in _SUCCESS_EVENTS or (not ev and (obj.get("ownId") or obj.get("own_id"))):
                _finish_ok(sess, obj)
                break
            if ev in _ERROR_EVENTS:
                sess.update(state="error", error=str(obj.get("message") or obj.get("error")
                                                     or localefmt.chu("Đăng nhập thất bại", "Sign-in failed")))
                break
    except Exception as e:
        if sess.get("state") not in ("done", "error"):
            sess.update(state="error", error=f"{type(e).__name__}: {e}")
    finally:
        try:
            rc = proc.wait(timeout=5)
        except Exception:
            rc = None
        if sess.get("duplicate"):
            # The same account signed in a second time: end the sign-in process and drop its fresh session folder,
            # which holds a working login of that account nobody would ever close.
            cancel(sid, keep=True)
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
            shutil.rmtree(sess["home"], ignore_errors=True)
        # CLI thoát êm sau khi đã hiện QR mà chưa bắt được event success → coi là thành công
        if sess.get("state") not in ("done", "error"):
            if rc == 0 and got_qr:
                _finish_ok(sess, {})
            else:
                err_tail = ""
                try:
                    err_tail = (proc.stderr.read() or "")[-300:]
                except Exception:
                    pass
                sess.update(state="error",
                            error=localefmt.chu("Đăng nhập chưa hoàn tất", "Sign-in did not complete")
                            + (f" (exit {rc}): {err_tail}" if rc else ""))


def _watchdog(sid):
    time.sleep(_TIMEOUT)
    sess = _sessions.get(sid)
    if sess and sess.get("state") in ("starting", "qr"):
        sess.update(state="error", error=localefmt.chu("Mã QR hết hạn, bấm thử lại", "The QR code expired, press try again"))
        cancel(sid, keep=True)


def start(label=None):
    """Bắt đầu 1 phiên đăng nhập QR. Trả {ok, sid} hoặc {ok:False, error}."""
    _sweep()
    argv = _npx_argv()
    if not argv:
        return {"ok": False, "error": localefmt.chu("Cần cài Node.js 20+ (lệnh npx) trên máy chạy Javis - tải tại nodejs.org",
                                                    "Node.js 20+ (the npx command) must be installed on the machine running Javis - download it at nodejs.org")}
    sid = uuid.uuid4().hex[:10]
    slug = mcp_store._slugify(label or "zalo")
    # Kèm sid: 2 tài khoản đặt CÙNG tên gợi nhớ vẫn phải 2 home riêng (account active của
    # zalo-agent-cli là toàn cục theo home - trùng home = tài khoản sau đè tài khoản trước).
    home = str(STATE_DIR / "connector-home" / f"zalo-{slug}-{sid[:6]}")
    os.makedirs(home, exist_ok=True)
    env = dict(os.environ)
    env["HOME"] = home
    env["USERPROFILE"] = home
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                                errors="replace", env=env, **kwargs)
    except OSError as e:
        return {"ok": False, "error": localefmt.chu(f"Không chạy được npx: {e}", f"Could not run npx: {e}")}
    _sessions[sid] = {"state": "starting", "qr": "", "label": (label or "").strip(),
                      "conn_id": "", "error": "", "proc": proc, "home": home, "ts": time.time()}
    threading.Thread(target=_reader, args=(sid,), daemon=True).start()
    threading.Thread(target=_watchdog, args=(sid,), daemon=True).start()
    return {"ok": True, "sid": sid}


def status(sid):
    sess = _sessions.get(sid)
    if not sess:
        return {"state": "error", "error": localefmt.chu("Phiên đăng nhập không tồn tại (hết hạn?)",
                                                       "The sign-in session does not exist (expired?)")}
    return {"state": sess["state"], "qr": sess.get("qr", ""), "label": sess.get("label", ""),
            "conn_id": sess.get("conn_id", ""), "error": sess.get("error", "")}


def cancel(sid, keep=False):
    sess = _sessions.get(sid)
    if not sess:
        return {"ok": True}
    try:
        if sess["proc"].poll() is None:
            # Giết CẢ CÂY, không riêng launcher. Trên Windows npx chạy qua `cmd.exe /c`, nên
            # kill() chỉ hạ cái vỏ còn tiến trình node cháu vẫn sống và vẫn giữ khoá trên thư
            # mục home cô lập - lần xoá kết nối sau đó sẽ trượt mà không báo gì.
            if not winproc.kill_tree(sess["proc"].pid):
                sess["proc"].kill()
    except Exception:
        pass
    if not keep:
        if sess.get("state") not in ("done",):
            sess["state"] = "error"
            sess.setdefault("error", localefmt.chu("Đã huỷ", "Cancelled"))
    return {"ok": True}
