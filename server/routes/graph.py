"""Đồ thị note: ảnh chụp `GET /graph` và luồng realtime `WS /ws/graph`.

Bóc nguyên văn khỏi main.py ở 0.9.243. Chỉ đổi đúng một thứ: `_resolve_graph_roots` lấy
đường dẫn brain/vault qua `deps` thay vì đọc biến toàn cục của main. Mọi dòng còn lại giữ
y hệt, kể cả các chi tiết dễ tưởng là thừa:

- `ws_graph` TỰ kiểm đăng nhập ở đầu hàm. Middleware `_auth_guard` của main chỉ thấy request
  HTTP, không thấy scope websocket, nên bỏ dòng đó là mở toang socket này.
- `from watchfiles import ...` cố tình nằm TRONG hàm: thiếu thư viện thì rơi về quét thưa
  chứ không làm chết cả app lúc khởi động.
- `__import__('sys').stderr` giữ nguyên vì đây là bản chép đúng từ main.py, nơi không có
  `import sys` ở đầu file.
"""
import asyncio
import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

import config as cfgmod
from graph_builder import graph_with_etag, _color_for, _top_folder, doc_wikilink


@dataclass
class GraphDeps:
    """Thứ duy nhất module này cần từ main: gốc brain mặc định và đường dẫn vault."""
    default_brain_dir: Callable[[], Path]
    vault_path: Callable[[], str]


_DEPS: GraphDeps = None


def _resolve_graph_roots(source: str, path: str = None):
    """Chuyển lựa chọn nguồn (all|brain|vault|path) → danh sách thư mục root để quét."""
    if path:
        return [path]
    if source == "brain":
        return [str(_DEPS.default_brain_dir())]
    if source == "vault":
        return [_DEPS.vault_path()]
    return [str(_DEPS.default_brain_dir()), _DEPS.vault_path()]


# ============================================================
# Realtime graph - theo dõi file .md mới/đổi → đẩy node mọc lên live
# ============================================================
def _scan_md_mtimes(roots):
    """Quét .md trong các root → dict {fullpath: mtime}. Bỏ qua thư mục ẩn (.git, .obsidian...).
    Dùng os.walk + cắt tỉa thư mục ẩn NGAY khi duyệt (glob cũ vẫn chui vào .git/.obsidian
    rồi mới lọc - tốn phần lớn thời gian quét trên vault lớn) và lấy mtime từ os.scandir
    (DirEntry.stat đã có sẵn trên Windows, khỏi getmtime từng file)."""
    out = {}
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, dirnames, _files in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            try:
                with os.scandir(dirpath) as it:
                    for entry in it:
                        if entry.name.endswith(".md") and entry.is_file():
                            try:
                                out[entry.path] = entry.stat().st_mtime
                            except OSError:
                                pass
            except OSError:
                pass
    return out


def _root_of(fpath, roots):
    for root in roots:
        try:
            Path(fpath).relative_to(root)
            return root
        except ValueError:
            continue
    return roots[0] if roots else os.path.dirname(fpath)


def _node_payload(fpath, roots):
    """Tạo node dict (giống build_graph) cho 1 file + danh sách wikilink target (stem lowercase)."""
    root = _root_of(fpath, roots)
    root_name = Path(root).name
    try:
        rel = Path(fpath).relative_to(root).as_posix()
    except ValueError:
        rel = Path(fpath).name
    stem = Path(fpath).stem
    try:
        _st = os.stat(fpath)
        _born = min(getattr(_st, "st_birthtime", _st.st_ctime), _st.st_mtime)
    except OSError:
        _born = 0
    node = {
        "id": stem.lower(),
        "label": stem,
        "folder": _top_folder(rel),
        "color": _color_for(rel),
        "path": f"{root_name}/{rel}",
        "links": 0,
        "t": _born,   # mốc ra đời - node live cũng xếp đúng chỗ trong timelapse
    }
    targets = []
    try:
        content = Path(fpath).read_text(encoding="utf-8", errors="replace")
        for t in doc_wikilink(content):
            if t != node["id"]:
                targets.append(t)
    except Exception:
        pass
    # dedup giữ thứ tự
    targets = list(dict.fromkeys(targets))
    return node, targets


_GRAPH_SPARSE_RESCAN = 300   # giây - lưới an toàn: ổ mạng NFS/SMB không bắn sự kiện file


def _hidden_in_roots(fpath, roots):
    """True nếu file nằm trong thư mục ẩn (.git, .obsidian, .trash...) tính theo root chứa nó."""
    for root in roots:
        try:
            rel = os.path.relpath(fpath, root)
        except ValueError:
            continue
        if not rel.startswith(".."):
            return any(part.startswith(".") for part in rel.split(os.sep))
    return False


# ---- One OS file watcher per folder, shared by every graph socket (2026-11-09) ----
# watchfiles builds its RustNotify (one inotify watch per folder) while HOLDING the GIL, so moving it to its own thread
# (0.521.1) did not free the event loop: in a test, a 60 000-folder tree froze the loop 0.54 s of the 0.60 s build, and
# the owner's /health/loop after that release still showed graph.py _fs_watcher 4 times, up to 2.74 s, the latest one
# right after a phone reconnected. Every graph tab and every reconnect built its own watcher. Now the first socket
# builds the watcher of each folder, later sockets join it, and it lingers after the last one leaves, so a reload, a
# second tab or a phone waking up costs nothing.
_WATCH_LINGER_S = 900   # seconds a watcher outlives its last graph socket


class _SharedWatch:
    def __init__(self, root: str):
        self.root = root
        self.subscribers = set()          # (loop, asyncio.Queue) of each graph socket listening
        self.stop = threading.Event()
        self.idle_since = None            # monotonic time the last socket left, None while one listens


_shared_watches: dict = {}                # root -> _SharedWatch, only watchers whose thread is starting or running
_shared_lock = threading.Lock()


def _watch_roots(roots) -> list:
    """Existing roots, normalised, without a root that sits inside another one (it would be watched twice)."""
    live = sorted({os.path.normpath(os.path.abspath(r)) for r in roots if r and os.path.isdir(r)})
    out = []
    for r in live:
        if not any(r == o or r.startswith(o.rstrip(os.sep) + os.sep) for o in out):
            out.append(r)
    return out


def _watch_run(w: _SharedWatch) -> None:
    """Thread body: watch one folder and hand each batch of changed notes to every socket listening."""
    try:
        from watchfiles import watch, Change
        for changes in watch(w.root, stop_event=w.stop, raise_interrupt=False,
                             watch_filter=lambda _c, p: p.endswith(".md")):
            paths = frozenset(p for c, p in changes if c in (Change.added, Change.modified))
            if not paths:
                continue
            with _shared_lock:
                listeners = list(w.subscribers)
            for loop, queue in listeners:
                try:
                    loop.call_soon_threadsafe(queue.put_nowait, paths)
                except RuntimeError:   # that loop is closing: nobody is listening there any more
                    pass
    except Exception as e:
        print(f"[ws_graph watcher] {type(e).__name__}: {e}", file=__import__('sys').stderr)
    finally:
        with _shared_lock:
            if _shared_watches.get(w.root) is w:
                del _shared_watches[w.root]


def _watch_join(roots, loop, queue) -> list:
    """Join the shared watcher of each root, starting the ones that do not run yet. Returns the watchers joined."""
    try:
        import watchfiles  # noqa: F401
    except ImportError:   # môi trường thiếu watchfiles → còn mỗi quét thưa, vẫn chạy được
        print("[ws_graph] thiếu watchfiles - node mọc theo nhịp quét thưa", file=__import__('sys').stderr)
        return []
    joined = []
    for root in _watch_roots(roots):
        with _shared_lock:
            w = _shared_watches.get(root)
            new = w is None
            if new:
                w = _shared_watches[root] = _SharedWatch(root)
            w.subscribers.add((loop, queue))
            w.idle_since = None
        if new:
            threading.Thread(target=_watch_run, args=(w,), name="ws-graph-watch", daemon=True).start()
        joined.append(w)
    return joined


def _watch_leave(joined, loop, queue) -> None:
    """Leave the watchers joined; one left with no socket stops after _WATCH_LINGER_S unless a socket joins again."""
    for w in joined:
        with _shared_lock:
            w.subscribers.discard((loop, queue))
            if w.subscribers or _shared_watches.get(w.root) is not w:
                continue
            w.idle_since = time.monotonic()
        loop.call_later(_WATCH_LINGER_S, _watch_reap, w)


def _watch_reap(w: _SharedWatch) -> None:
    with _shared_lock:
        if w.subscribers or w.idle_since is None or _shared_watches.get(w.root) is not w:
            return
        if time.monotonic() - w.idle_since < _WATCH_LINGER_S - 0.5:
            return   # a later leave restarted the clock and set its own reap
        del _shared_watches[w.root]
    w.stop.set()


def _make_router() -> APIRouter:
    router = APIRouter()

    @router.get("/graph")
    async def graph(
        request: Request,
        source: str = Query("all", description="all | brain | vault"),
        path: str = Query(None, description="Đường dẫn folder tùy ý (ưu tiên nếu có)"),
        orphans: int = Query(0, description="1 = hiện cả note cô đơn (0 kết nối), như graph view Obsidian"),
    ):
        """Lớp Graphify - dựng đồ thị kết nối note từ wikilink.
        Dựng đồ thị đụng tới đĩa (quét + đọc file đã đổi) - phải đẩy sang thread, chạy sync trên event loop là đứng cả
        server (mọi request khác xếp hàng).

        0.225.0: kèm ETag theo chữ ký vault. Trình duyệt hỏi lại với If-None-Match (`Cache-Control: no-cache`) và nhận 304
        trống khi không note nào đổi: quay lại một bộ não vừa xem không phải tải lại cả đồ thị. JSON viết gọn, và gzip ở
        middleware `nen_phan_hoi`."""
        etag, data = await asyncio.to_thread(graph_with_etag, _resolve_graph_roots(source, path),
                                             include_orphans=bool(orphans))
        tag = f'"g-{etag}"'
        hdr = {"ETag": tag, "Cache-Control": "no-cache"}
        if tag in (request.headers.get("if-none-match") or ""):
            return Response(status_code=304, headers=hdr)
        # 2026-11-09: on a worker thread too: the graph of a 2000-note brain is ~1 MB of JSON.
        body = await asyncio.to_thread(json.dumps, data, ensure_ascii=False, separators=(",", ":"))
        return Response(body, media_type="application/json", headers=hdr)

    @router.get("/graph/counts")
    async def graph_counts(
        source: str = Query("brain", description="all | brain | vault"),
        path: str = Query(None, description="A brain folder (the picker's path:<folder> value)"),
    ):
        """Note and link counts of one brain, as its graph shows them (2026-11-09, the brain picker). Asked only when the
        picker opens, never at page load, and counted from the per-file link cache on a worker thread."""
        from graph_builder import graph_counts as _counts
        return await asyncio.to_thread(_counts, _resolve_graph_roots(source, path))

    @router.websocket("/ws/graph")
    async def ws_graph(ws: WebSocket):
        """Đẩy realtime khi note .md sinh ra / đổi. Nghe SỰ KIỆN file từ HĐH qua watchfiles
        (inotify Linux / FSEvents macOS / ReadDirectoryChangesW Windows - lib đã có sẵn theo
        uvicorn[standard]) thay cho poll 4s/lần: vault không đổi thì nằm im tuyệt đối, node
        mọc lên NGAY khi file được ghi thay vì đợi nhịp quét. Poll cũ mỗi tab là một vòng
        quét toàn vault vô hạn, 99% số lần trả lời "không có gì mới".
        Lưới an toàn: quét thưa _GRAPH_SPARSE_RESCAN giây/lần trong to_thread - bắt các thay
        đổi mà sự kiện không phủ (vault trên ổ mạng, sự kiện rơi khi burst quá lớn)."""
        if cfgmod.gate_active() and not cfgmod.valid_session(ws.cookies.get("javis_session", "")):
            await ws.close(code=1008)
            return
        await ws.accept()
        qp = ws.query_params
        roots = _resolve_graph_roots(qp.get("source", "all"), qp.get("path") or None)
        known = await asyncio.to_thread(_scan_md_mtimes, roots)   # baseline lúc kết nối → chỉ báo cái sinh ra sau đó
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        # The OS watch of each folder is shared with every other graph socket (see _SharedWatch): only the first
        # socket after a quiet spell pays for building it.
        joined = _watch_join(roots, loop, queue)

        async def _sparse_rescan():
            while True:
                await asyncio.sleep(_GRAPH_SPARSE_RESCAN)
                await queue.put(None)   # None = hiệu lệnh quét lại toàn bộ

        sparse = asyncio.create_task(_sparse_rescan())
        # Client không bao giờ gửi gì lên socket này - task receive sống CHỈ để báo disconnect
        # (mô hình poll cũ phát hiện disconnect nhờ send định kỳ lỗi; giờ im lặng dài nên phải nghe).
        recv = asyncio.create_task(ws.receive())
        item = asyncio.create_task(queue.get())
        try:
            while True:
                done, _pending = await asyncio.wait({recv, item}, return_when=asyncio.FIRST_COMPLETED)
                if recv in done:
                    try:
                        recv.result()   # tiêu thụ exception (nếu có) cho gọn warning
                    except (Exception, asyncio.CancelledError):
                        pass
                    break   # disconnect / socket lỗi → dọn
                batch = item.result()
                item = asyncio.create_task(queue.get())
                changed = []
                if batch is None:   # quét thưa: diff toàn bộ như mô hình poll cũ
                    current = await asyncio.to_thread(_scan_md_mtimes, roots)
                    for fp, mt in current.items():
                        old = known.get(fp)
                        if old is None:
                            changed.append((fp, True))            # note MỚI sinh
                        elif mt > old + 0.001:
                            changed.append((fp, False))           # note đổi
                    known = current
                else:               # sự kiện HĐH: chỉ đụng đúng các file được báo
                    for fp in batch:
                        if _hidden_in_roots(fp, roots):
                            continue
                        try:
                            mt = os.path.getmtime(fp)
                        except OSError:
                            continue   # vừa bị xoá/đổi tên giữa chừng
                        old = known.get(fp)
                        if old is None:
                            changed.append((fp, True))
                        elif mt > old + 0.001:
                            changed.append((fp, False))
                        known[fp] = mt
                for fp, is_new in changed[:80]:               # chặn burst
                    node, targets = await asyncio.to_thread(_node_payload, fp, roots)
                    await ws.send_text(json.dumps({
                        "type": "graph_add", "node": node,
                        "linkTargets": targets, "isNew": is_new,
                    }, ensure_ascii=False))
        except WebSocketDisconnect:
            pass
        except asyncio.CancelledError:
            # TestClient (và một số proxy) hủy task ngay sau khi gửi disconnect.
            # CancelledError không thuộc Exception; để lọt ra sẽ làm lần đóng socket
            # ném lỗi dù mọi graph_add trước đó đã gửi thành công.
            pass
        except Exception as e:
            print(f"[ws_graph] {type(e).__name__}: {e}", file=__import__('sys').stderr)
        finally:
            # Leave the shared watchers first: nothing may be handed to this socket's queue any more. The watcher
            # itself keeps running for the next graph socket and stops through its stop_event after
            # _WATCH_LINGER_S, so a reload (F5) no longer builds a new one. On macOS each new watcher used to leave an
            # FSEvents Unix socket behind when it was only cancelled, until ``maxfiles=256`` turned every API call into
            # ``OSError: [Errno 24] Too many open files``; one long-lived watcher per folder, stopped by its event,
            # cannot pile up like that.
            _watch_leave(joined, loop, queue)
            auxiliaries = (sparse, recv, item)
            for t in auxiliaries:
                if not t.done():
                    t.cancel()
            try:
                await asyncio.gather(*auxiliaries, return_exceptions=True)
            except asyncio.CancelledError:
                # Proxy/TestClient có thể hủy task ngay sau khi gửi disconnect. Không để
                # CancelledError biến một lần đóng socket bình thường thành lỗi.
                pass

    return router


def register(app, deps: GraphDeps):
    """Gắn router vào app. Gọi ĐÚNG vị trí dòng cũ trong main.py - xem routes/__init__.py."""
    global _DEPS
    _DEPS = deps
    router = _make_router()
    app.include_router(router)
    return router
