"""
Graph builder - quét các file markdown, parse [[wikilink]], dựng đồ thị kết nối.
Đây là lớp "Graphify" - visualize mạng lưới note như Obsidian graph view.
"""
import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Match [[Note]] và [[folder/Note|alias]]
WIKILINK_RE = re.compile(r"\[\[([^\]\|#]+)(?:[#\|][^\]]*)?\]\]")

# Khối mã phải được BỎ RA trước khi dò wikilink. Bash dùng `[[ ... ]]` làm phép thử, nên một
# skill có dòng `[[ ! "$f" =~ \.md$ ]]` sẽ đẻ ra một "wikilink" tên là ! "$f" =~ \.md$ - và
# đồ thị phía trình duyệt ném "node not found" mỗi khung hình cho tới khi chết hẳn. Vấp thật
# 15/09 ngay sau khi cài bộ skill lập trình vào brain.
#
# `build_graph` tình cờ thoát vì nó chỉ nối khi tên khớp một note CÓ THẬT; đường cập nhật
# trực tiếp (routes/graph.py::_node_payload) thì gửi thẳng nên nổ. Sửa ở đây, một chỗ, cho cả
# hai đường dùng chung.
_KHOI_MA_RE = re.compile(r"```[\s\S]*?```|~~~[\s\S]*?~~~")
_MA_DONG_RE = re.compile(r"`[^`\n]*`")


def bo_khoi_ma(text: str) -> str:
    """Thay khối mã và mã trong dòng bằng khoảng trắng, giữ nguyên độ dài dòng ở mức đủ dùng."""
    s = _KHOI_MA_RE.sub(" ", text or "")
    return _MA_DONG_RE.sub(" ", s)


def doc_wikilink(text: str):
    """Tên các note được trỏ tới trong một file markdown (đã chuẩn hoá thường, bỏ khối mã)."""
    for m in WIKILINK_RE.finditer(bo_khoi_ma(text)):
        ten = m.group(1).strip().split("/")[-1].strip().lower()
        if ten:
            yield ten

# Palette tinh vân tím (như V.A.U.L.T) - tím chủ đạo + vài tông phụ, lõi trắng nóng
FOLDER_COLORS = {
    "00": "#c77dff", "01": "#a96bff", "02": "#7c5cff", "03": "#d98cff",
    "04": "#8a9bff", "05": "#e07ad1", "06": "#b07aff", "07": "#9b8cff",
    "08": "#c9a3ff", "brain": "#c77dff", "wiki": "#7c5cff",
}

def _color_for(rel_path: str) -> str:
    top = rel_path.split("/")[0].lower()
    for key, color in FOLDER_COLORS.items():
        if top.startswith(key):
            return color
    return "#9d7aff"  # tím mặc định

def _top_folder(rel_path: str) -> str:
    parts = rel_path.split("/")
    return parts[0] if len(parts) > 1 else "root"


# ---- Bộ nhớ đệm (0.225.0) ----
# Chủ dự án 19/10: "khi tải bộ não mới hoặc sang 1 bộ não khác phần tải note đang rất chậm". Đo trên bộ não 2000 note:
# mỗi lần đổi brain là đọc lại TRỌN 2000 file (20 MB) để dò wikilink, dù không file nào đổi, rồi gửi gần 1 MB JSON
# không nén. Giờ mỗi file chỉ đọc lại khi mtime hoặc kích thước của nó đổi; phần dò được lưu xuống
# `<JAVIS_STATE_DIR>/cache/graph/` nên khởi động lại server cũng không phải đọc lại; và cả kết quả được nhớ theo
# chữ ký của vault (ETag), không đổi gì thì trình duyệt nhận 304 trống.
_CACHE_VER = 1
_locks_lock = threading.Lock()
_root_locks: Dict[str, threading.Lock] = {}
_file_cache: Dict[str, Dict[str, list]] = {}     # root -> {rel: [mtime_ns, size, born, [targets]]}
_result_cache: Dict[tuple, Tuple[str, dict]] = {}  # (roots, orphans, max_files) -> (etag, kết quả)
_RESULT_MAX = 16


def _cache_dir() -> Path:
    return Path(os.getenv("JAVIS_STATE_DIR", str(Path(__file__).parent))) / "cache" / "graph"


def _cache_file(root: str) -> Path:
    return _cache_dir() / (hashlib.sha1(root.encode("utf-8", "surrogatepass")).hexdigest()[:20] + ".json")


def _root_lock(root: str) -> threading.Lock:
    with _locks_lock:
        lk = _root_locks.get(root)
        if lk is None:
            lk = _root_locks[root] = threading.Lock()
        return lk


def _load_cache(root: str) -> Dict[str, list]:
    if root in _file_cache:
        return _file_cache[root]
    files: Dict[str, list] = {}
    try:
        d = json.loads(_cache_file(root).read_text(encoding="utf-8"))
        if d.get("v") == _CACHE_VER and d.get("root") == root and isinstance(d.get("files"), dict):
            files = d["files"]
    except (OSError, ValueError, AttributeError):
        pass
    _file_cache[root] = files
    return files


def _save_cache(root: str, files: Dict[str, list]) -> None:
    """Ghi đè nguyên tử. Hỏng (đĩa đầy, không có quyền) thì thôi: bộ đệm chỉ để nhanh, không phải để đúng."""
    try:
        f = _cache_file(root)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f.name + ".tmp")
        tmp.write_text(json.dumps({"v": _CACHE_VER, "root": root, "files": files}, ensure_ascii=False,
                                  separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, f)
    except OSError:
        pass


def _scan_root(root: str):
    """Mọi file .md dưới `root`: (rel, fullpath, stat), thứ tự cố định. Như `glob("**/*.md")` cũ: bỏ thư mục và file
    ẩn (.git, .obsidian, .trash), đi theo liên kết thư mục. Cắt tỉa thư mục ẩn ngay khi duyệt, và stat lấy từ scandir."""
    out = []
    seen = set()
    stack = [""]
    while stack:
        rel_dir = stack.pop()
        d = os.path.join(root, rel_dir) if rel_dir else root
        try:
            real = os.path.realpath(d)
            if real in seen:
                continue           # liên kết vòng
            seen.add(real)
            with os.scandir(d) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            continue
        subdirs = []
        for e in entries:
            if e.name.startswith("."):
                continue
            rel = (rel_dir + "/" + e.name) if rel_dir else e.name
            try:
                if e.is_dir():
                    subdirs.append(rel)
                elif e.name.endswith(".md") and e.is_file():
                    out.append((rel, e.path, e.stat()))
            except OSError:
                continue
        stack.extend(reversed(subdirs))
    return out


def _parse_file(fpath: str, st) -> list:
    born = min(getattr(st, "st_birthtime", st.st_ctime), st.st_mtime)
    try:
        with open(fpath, encoding="utf-8", errors="replace") as fh:
            targets = list(dict.fromkeys(doc_wikilink(fh.read())))
    except OSError:
        targets = []
    return [st.st_mtime_ns, st.st_size, int(born), targets]


def _collect(root: str, budget: int):
    """[(rel, fullpath, mtime_ns, size, born, targets)] của một root, tối đa `budget` file. Chỉ đọc file mới hoặc đã đổi."""
    with _root_lock(root):
        old = _load_cache(root)
        scanned = _scan_root(root)
        fresh: Dict[str, list] = {}
        changed = False
        out = []
        for rel, fpath, st in scanned:
            if len(out) >= budget:
                break
            ent = old.get(rel)
            if not (isinstance(ent, list) and len(ent) == 4 and ent[0] == st.st_mtime_ns and ent[1] == st.st_size):
                ent = _parse_file(fpath, st)
                changed = True
            fresh[rel] = ent
            out.append((rel, fpath, ent[0], ent[1], ent[2], ent[3]))
        if len(fresh) != len(old):
            changed = True       # có file bị xoá (hoặc vượt trần)
        _file_cache[root] = fresh
        if changed:
            _save_cache(root, fresh)
        return out


def graph_with_etag(roots: List[str], max_files: int = 2000, include_orphans: bool = False) -> Tuple[str, Dict]:
    """Như `build_graph`, kèm ETag theo chữ ký nội dung vault: mọi file .md giữ nguyên mtime và kích thước thì ETag
    giữ nguyên, và kết quả được trả lại từ bộ nhớ mà không dựng lại."""
    per_root = []
    left = max_files
    for root in roots:
        if not root or not os.path.isdir(root) or left <= 0:
            continue
        files = _collect(root, left)
        left -= len(files)
        per_root.append((root, files))
    h = hashlib.sha1(f"{_CACHE_VER}|{max_files}|{int(include_orphans)}".encode())
    for root, files in per_root:
        h.update(b"\0R" + root.encode("utf-8", "surrogatepass"))
        for rel, _fp, mt, size, _b, _t in files:
            h.update(f"\0{rel}\1{mt}\1{size}".encode("utf-8", "surrogatepass"))
    etag = h.hexdigest()[:24]
    key = (tuple(roots), bool(include_orphans), max_files)
    hit = _result_cache.get(key)
    if hit and hit[0] == etag:
        return hit
    data = _build_from(per_root, include_orphans)
    if len(_result_cache) >= _RESULT_MAX:
        _result_cache.pop(next(iter(_result_cache)))
    _result_cache[key] = (etag, data)
    return etag, data


def build_graph(roots: List[str], max_files: int = 2000, include_orphans: bool = False) -> Dict:
    """
    Quét nhiều thư mục root, dựng graph.
    roots: list các đường dẫn thư mục chứa .md
    Trả về: {nodes: [...], edges: [...], stats: {...}}
    """
    return graph_with_etag(roots, max_files=max_files, include_orphans=include_orphans)[1]


def _build_from(per_root, include_orphans: bool) -> Dict:
    nodes = {}          # stem (lowercase) -> node dict
    edges = []

    # Pass 1: mỗi file một node. Trùng tên (không phân biệt hoa thường) thì giữ bản gặp trước.
    # KHÔNG gửi đường dẫn tuyệt đối của máy chủ (trước 0.225.0 có trường `fullpath`): trình duyệt không dùng nó, mà
    # nó chiếm gần một phần năm gói dữ liệu và để lộ cấu trúc thư mục của máy.
    all_files = []
    for root, files in per_root:
        root_name = Path(root).name
        for rel, _fp, _mt, _size, born, targets in files:
            stem = rel.rsplit("/", 1)[-1][:-3]
            node_id = stem.lower()
            if node_id in nodes:
                continue
            # Mốc "note ra đời" cho timelapse: birthtime (macOS) > ctime (Windows = creation) > mtime.
            nodes[node_id] = {
                "id": node_id,
                "label": stem,
                "folder": _top_folder(rel),
                "color": _color_for(rel),
                "path": f"{root_name}/{rel}",
                "links": 0,
                "t": born,
            }
            all_files.append((node_id, targets))

    # Pass 2: wikilink -> edge (chỉ nối tới note CÓ THẬT)
    for node_id, targets in all_files:
        for target_stem in targets:
            if target_stem in nodes and target_stem != node_id:
                edges.append({"source": node_id, "target": target_stem})
                nodes[node_id]["links"] += 1
                nodes[target_stem]["links"] += 1

    # Loại edge trùng
    seen = set()
    unique_edges = []
    for e in edges:
        k = tuple(sorted([e["source"], e["target"]]))
        if k not in seen:
            seen.add(k)
            unique_edges.append(e)

    orphan_count = len([n for n in nodes.values() if n["links"] == 0])

    # Giữ node: mặc định bỏ note cô đơn (0 kết nối); include_orphans=True thì giữ HẾT (như Obsidian).
    if include_orphans:
        keep = set(nodes.keys())
    else:
        keep = {nid for nid, n in nodes.items() if n["links"] > 0}
        if not keep:
            keep = set(nodes.keys())
    node_list = [n for nid, n in nodes.items() if nid in keep]
    edge_list = [e for e in unique_edges if e["source"] in keep and e["target"] in keep]

    # Đếm concept theo nhóm (folder cha trực tiếp của file) - cho nhãn HUD
    from collections import Counter
    cat_counter = Counter()
    for n in node_list:
        segs = n["path"].split("/")
        cat = segs[-2] if len(segs) >= 2 else "root"
        cat = re.sub(r"^\d+\s*[-_.]\s*", "", cat).strip()  # bỏ tiền tố "07 - "
        if cat:
            cat_counter[cat] += 1
    categories = [{"name": c, "count": cnt} for c, cnt in cat_counter.most_common(8)]

    return {
        "nodes": node_list,
        "edges": edge_list,
        "categories": categories,
        "stats": {
            "total_notes": len(node_list),
            "total_links": len(edge_list),
            "orphans": orphan_count,
            "hidden": len(nodes) - len(node_list),
        }
    }
