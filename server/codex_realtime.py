"""Một `codex app-server` sống lâu cho ChatGPT Live (docs/dev/2026-10-voice-call-spec.md mục 3.2).

ChatGPT Live chạy trên GÓI ChatGPT của người dùng qua giao diện realtime của Codex CLI: Javis nói
JSON-RPC qua stdin/stdout với `codex app-server`, còn âm thanh đi THẲNG trình duyệt tới OpenAI qua
WebRTC. Javis chỉ chuyển gói bắt tay SDP và đọc thông báo chữ, nên không bao giờ cầm token: chính
app-server lo đăng nhập.

Vì sao một tiến trình cho cả máy chủ: khởi động app-server mất cỡ 1 giây và nạp cả cấu hình MCP
của Codex, còn mở thread mới chỉ mất 0,1 giây. Mỗi cuộc gọi (và mỗi lần nối lại sau khi ngắt vì
im lặng) mở một thread RIÊNG: dùng lại thread cho lần `realtime/start` thứ hai thì ICE hỏng.

Luôn chạy với `-c features.realtime_conversation=true`: Codex trước 0.159 (Docker đang ghim
0.153.4) để cờ này "under development" và tắt sẵn, báo "thread does not support realtime
conversation". Từ 0.159 cờ đã ổn định, truyền vào vẫn vô hại.

Luồng đọc stdout là thread daemon (khuôn của codex_models và antigravity_cli), đẩy sang asyncio
bằng `loop.call_soon_threadsafe`. Yêu cầu server gửi về (duyệt lệnh, duyệt file...) bị TỪ CHỐI
ngay: phiên realtime của Javis không bao giờ được để Codex tự làm việc trên máy.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import threading
from typing import Dict, Optional, Tuple

REALTIME_FLAG = ["-c", "features.realtime_conversation=true"]
INIT_TIMEOUT = 20.0


class AppServerError(RuntimeError):
    """Lỗi từ app-server hay tiến trình đã chết. Câu lỗi đọc được, route chuyển thẳng cho người dùng."""


def _no_window() -> int:
    try:
        import codex_models
        return codex_models._no_window()
    except Exception:
        return 0


class AppServer:
    def __init__(self, cli: str, popen_factory=subprocess.Popen):
        self.cli = cli
        self._popen = popen_factory
        self.proc = None
        self._lock = threading.Lock()
        self._next_id = 0
        self._pending: Dict[int, tuple] = {}
        self._subs: Dict[str, tuple] = {}
        self._dead = False
        self._started = False
        self._start_lock: Optional[asyncio.Lock] = None

    # ---- vòng đời ----
    @property
    def alive(self) -> bool:
        if self.proc is None or self._dead:
            return False
        try:
            return self.proc.poll() is None
        except Exception:
            return False

    async def ensure_started(self):
        if self._start_lock is None:
            self._start_lock = asyncio.Lock()
        async with self._start_lock:
            if self._started and self.alive:
                return
            self._spawn()
            await self.request("initialize", {
                "clientInfo": {"name": "javis_os", "title": "Javis OS", "version": "1.0"},
                "capabilities": {"experimentalApi": True},
            }, timeout=INIT_TIMEOUT)
            self._write({"method": "initialized", "params": {}})
            self._started = True

    def _spawn(self):
        self._dead = False
        self.proc = self._popen(
            [self.cli, *REALTIME_FLAG, "app-server"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=_no_window(),
        )
        threading.Thread(target=self._reader, name="javis-codex-realtime", daemon=True).start()

    def close(self):
        proc, self.proc = self.proc, None
        self._dead = True
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass

    # ---- gửi / nhận ----
    def _write(self, msg: dict):
        line = json.dumps(msg, ensure_ascii=False) + "\n"
        with self._lock:
            if self.proc is None or self._dead:
                raise AppServerError("Codex app-server không chạy.")
            try:
                self.proc.stdin.write(line)
                self.proc.stdin.flush()
            except Exception as e:
                self._dead = True
                raise AppServerError(f"Không gửi được cho Codex app-server: {e}")

    async def request(self, method: str, params: Optional[dict] = None, timeout: float = 30.0) -> dict:
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        with self._lock:
            self._next_id += 1
            rid = self._next_id
            self._pending[rid] = (loop, fut)
        try:
            self._write({"method": method, "id": rid, "params": params or {}})
            msg = await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            raise AppServerError(f"Codex app-server không trả lời {method} sau {int(timeout)} giây.")
        finally:
            with self._lock:
                self._pending.pop(rid, None)
        if msg.get("error"):
            err = msg["error"]
            raise AppServerError(str(err.get("message") if isinstance(err, dict) else err))
        return msg.get("result") or {}

    def subscribe(self, thread_id: str) -> asyncio.Queue:
        """Hàng đợi nhận mọi thông báo có `params.threadId == thread_id` (và `_exit` khi chết)."""
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subs[str(thread_id)] = (asyncio.get_running_loop(), q)
        return q

    def unsubscribe(self, thread_id: str):
        with self._lock:
            self._subs.pop(str(thread_id), None)

    @staticmethod
    def _deliver(loop, fn, *args):
        try:
            loop.call_soon_threadsafe(fn, *args)
        except RuntimeError:
            pass   # vòng lặp đã đóng (phiên đã kết thúc)

    def _reader(self):
        proc = self.proc
        try:
            for line in iter(proc.stdout.readline, ""):
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                if not isinstance(msg, dict):
                    continue
                if "id" in msg and "method" not in msg:
                    with self._lock:
                        item = self._pending.get(msg["id"])
                    if item:
                        loop, fut = item
                        self._deliver(loop, lambda f=fut, m=msg: f.done() or f.set_result(m))
                    continue
                if "id" in msg and "method" in msg:
                    # Yêu cầu từ server (duyệt lệnh, duyệt file, gọi tool động): luôn từ chối.
                    try:
                        self._write({"id": msg["id"], "error": {"code": -32000,
                                     "message": "Javis không cho phiên realtime tự làm việc trên máy."}})
                    except AppServerError:
                        pass
                    continue
                tid = str(((msg.get("params") or {}).get("threadId")) or "")
                with self._lock:
                    sub = self._subs.get(tid)
                if sub:
                    loop, q = sub
                    self._deliver(loop, q.put_nowait, msg)
        except Exception as e:  # pragma: no cover - ống đọc vỡ bất thường
            print(f"[codex realtime] đọc stdout lỗi: {e}", file=sys.stderr)
        finally:
            if proc is self.proc:
                self._dead = True
            with self._lock:
                pending = list(self._pending.values())
                subs = list(self._subs.values())
            for loop, fut in pending:
                self._deliver(loop, lambda f=fut: f.done() or f.set_exception(
                    AppServerError("Codex app-server đã thoát.")))
            for loop, q in subs:
                self._deliver(loop, q.put_nowait, {"method": "_exit", "params": {}})


# ---- một tiến trình cho cả máy chủ ----
_SERVER: Optional[AppServer] = None
_popen_factory = subprocess.Popen


def _find_cli() -> Optional[str]:
    try:
        import claude_cli
        return claude_cli.find_codex_cli()
    except Exception:
        return None


async def get_app_server() -> AppServer:
    """App-server đang sống, hoặc dựng mới khi chưa có / đã chết."""
    global _SERVER
    if _SERVER is not None and _SERVER.alive and _SERVER._started:
        return _SERVER
    cli = _find_cli()
    if not cli:
        raise AppServerError("Chưa cài Codex CLI nên chưa dùng được ChatGPT Live. Cài Codex rồi nối ChatGPT ở trang Models.")
    if _SERVER is not None:
        _SERVER.close()
    srv = AppServer(cli, popen_factory=_popen_factory)
    await srv.ensure_started()
    _SERVER = srv
    return srv


def _codex_logged_in() -> bool:
    try:
        import openai_oauth
        p = openai_oauth._codex_auth_path()
        return p.exists() and p.stat().st_size > 20
    except Exception:
        return False


def realtime_available(cfg: dict) -> Tuple[bool, str]:
    """ChatGPT Live dùng được chưa: (True, "") hoặc (False, "no_cli" | "no_login").

    Không hỏi mạng: chỉ xem có Codex CLI và có đăng nhập ChatGPT (token Javis đã nối ở trang Models,
    hoặc phiên `codex login` sẵn trên máy). Codex quá cũ hay gói không cho realtime thì lỗi hiện ra
    lúc mở cuộc gọi, và cuộc gọi rơi xuống đường kế tiếp.
    """
    if not _find_cli():
        return False, "no_cli"
    o = ((cfg or {}).get("model") or {}).get("openai_oauth") or {}
    if o.get("access_token") or o.get("refresh_token") or _codex_logged_in():
        return True, ""
    return False, "no_login"
