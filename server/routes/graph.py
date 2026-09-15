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
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

import config as cfgmod
from graph_builder import build_graph, _color_for, _top_folder, doc_wikilink


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


def _make_router() -> APIRouter:
    router = APIRouter()

    @router.get("/graph")
    async def graph(
        source: str = Query("all", description="all | brain | vault"),
        path: str = Query(None, description="Đường dẫn folder tùy ý (ưu tiên nếu có)"),
        orphans: int = Query(0, description="1 = hiện cả note cô đơn (0 kết nối), như graph view Obsidian"),
    ):
        """Lớp Graphify - dựng đồ thị kết nối note từ wikilink.
        build_graph là CPU-bound (đọc + regex toàn vault, nguồn 'all' đo được ~10s) - phải đẩy
        sang thread, chạy sync trên event loop là đứng cả server (mọi request khác xếp hàng)."""
        return await asyncio.to_thread(build_graph, _resolve_graph_roots(source, path),
                                       include_orphans=bool(orphans))

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
        stop = asyncio.Event()
        queue: asyncio.Queue = asyncio.Queue()

        async def _fs_watcher():
            live = [r for r in roots if r and os.path.isdir(r)]
            if not live:
                return
            try:
                from watchfiles import awatch, Change
            except ImportError:   # môi trường thiếu watchfiles → còn mỗi quét thưa, vẫn chạy được
                print("[ws_graph] thiếu watchfiles - node mọc theo nhịp quét thưa", file=__import__('sys').stderr)
                return
            try:
                async for changes in awatch(*live, stop_event=stop,
                                            watch_filter=lambda _c, p: p.endswith(".md")):
                    paths = {p for c, p in changes if c in (Change.added, Change.modified)}
                    if paths:
                        await queue.put(paths)
            except Exception as e:
                print(f"[ws_graph watcher] {type(e).__name__}: {e}", file=__import__('sys').stderr)

        async def _sparse_rescan():
            while True:
                await asyncio.sleep(_GRAPH_SPARSE_RESCAN)
                await queue.put(None)   # None = hiệu lệnh quét lại toàn bộ

        watcher = asyncio.create_task(_fs_watcher())
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
                    except Exception:
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
        except Exception as e:
            print(f"[ws_graph] {type(e).__name__}: {e}", file=__import__('sys').stderr)
        finally:
            # Tắt watcher và CHỜ mọi task thoát hẳn. Chỉ gọi ``cancel()`` rồi rời handler sẽ
            # để luồng FSEvents/watchfiles còn giữ Unix socket trên macOS; mỗi lần F5 tạo thêm
            # một socket mồ côi, tới giới hạn ``maxfiles=256`` thì toàn bộ API bắt đầu nổ
            # ``OSError: [Errno 24] Too many open files`` và giao diện tưởng brain biến mất.
            stop.set()
            # awatch cần nhìn thấy stop_event để tự đóng backend FSEvents. Hủy watcher ngay
            # có thể ngắt coroutine trước khi backend kịp thu socket; ngược lại chờ vô hạn sẽ
            # treo disconnect trên một số bản watchfiles. Vì vậy dọn ba task thuần asyncio
            # trước, cho watcher tối đa 2 giây thoát êm rồi mới cưỡng chế hủy.
            auxiliaries = (sparse, recv, item)
            for t in auxiliaries:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*auxiliaries, return_exceptions=True)
            try:
                await asyncio.wait_for(watcher, timeout=2.0)
            except asyncio.TimeoutError:
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)

    return router


def register(app, deps: GraphDeps):
    """Gắn router vào app. Gọi ĐÚNG vị trí dòng cũ trong main.py - xem routes/__init__.py."""
    global _DEPS
    _DEPS = deps
    router = _make_router()
    app.include_router(router)
    return router
