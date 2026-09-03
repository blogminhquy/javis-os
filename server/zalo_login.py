"""
Đăng nhập Zalo bằng QR ngay trong UI Javis (connector "zalo" - zalo-agent-cli).
Flow: POST /connect/zalo/start → spawn `npx -y zalo-agent-cli login --json` với HOME
cô lập riêng cho tài khoản → bắt event {"event":"qr", dataUrl} đưa lên modal →
user quét bằng app Zalo → thành công thì TỰ TẠO connection (config.home_dir trỏ
home cô lập đó, mcp_store.resolved tự set env HOME/USERPROFILE khi chạy MCP).

Đã verify (v1.6.2): bin "zalo-agent"; account active là TOÀN CỤC theo home dir
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
import winproc
from config import STATE_DIR

_TIMEOUT = 180        # QR Zalo sống ngắn - quá 3 phút coi như hết hạn
_SESS_TTL = 900
_sessions = {}        # sid -> {state, qr, label, conn_id, error, proc, home, ts}

_SUCCESS_EVENTS = {"login", "login_success", "success", "ready", "logged_in", "authenticated"}
_CLI_PACKAGE = "zalo-agent-cli@1.6.2"


def _sweep():
    now = time.time()
    for sid in [k for k, v in _sessions.items() if now - v["ts"] > _SESS_TTL]:
        cancel(sid)
        _sessions.pop(sid, None)


def _npx_argv():
    npx = shutil.which("npx")
    if not npx:
        return None
    argv = [npx, "-y", _CLI_PACKAGE, "login", "--json"]
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


def _finish_ok(sess, obj):
    label = (obj.get("displayName") or obj.get("display_name") or obj.get("name")
             or obj.get("ownId") or obj.get("own_id") or sess["label"] or "Zalo")
    cid, err = mcp_store.add_connection("zalo", {
        "label": str(label)[:60],
        "config": {"home_dir": sess["home"]},
    })
    if err:
        sess.update(state="error", error=f"Đăng nhập được nhưng không lưu kết nối: {err}")
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
            if ev in ("error", "failed"):
                sess.update(state="error", error=str(obj.get("message") or obj.get("error") or "Đăng nhập thất bại"))
                break
    except Exception as e:
        if sess.get("state") not in ("done", "error"):
            sess.update(state="error", error=f"{type(e).__name__}: {e}")
    finally:
        try:
            rc = proc.wait(timeout=5)
        except Exception:
            rc = None
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
                            error="Đăng nhập chưa hoàn tất" + (f" (exit {rc}): {err_tail}" if rc else ""))


def _watchdog(sid):
    time.sleep(_TIMEOUT)
    sess = _sessions.get(sid)
    if sess and sess.get("state") in ("starting", "qr"):
        sess.update(state="error", error="Mã QR hết hạn, bấm thử lại")
        cancel(sid, keep=True)


def start(label=None):
    """Bắt đầu 1 phiên đăng nhập QR. Trả {ok, sid} hoặc {ok:False, error}."""
    _sweep()
    argv = _npx_argv()
    if not argv:
        return {"ok": False, "error": "Cần cài Node.js 20+ (lệnh npx) trên máy chạy Javis - tải tại nodejs.org"}
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
        return {"ok": False, "error": f"Không chạy được npx: {e}"}
    _sessions[sid] = {"state": "starting", "qr": "", "label": (label or "").strip(),
                      "conn_id": "", "error": "", "proc": proc, "home": home, "ts": time.time()}
    threading.Thread(target=_reader, args=(sid,), daemon=True).start()
    threading.Thread(target=_watchdog, args=(sid,), daemon=True).start()
    return {"ok": True, "sid": sid}


def status(sid):
    sess = _sessions.get(sid)
    if not sess:
        return {"state": "error", "error": "Phiên đăng nhập không tồn tại (hết hạn?)"}
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
            sess.setdefault("error", "Đã huỷ")
    return {"ok": True}
