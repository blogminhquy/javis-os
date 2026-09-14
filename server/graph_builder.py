"""
Graph builder - quét các file markdown, parse [[wikilink]], dựng đồ thị kết nối.
Đây là lớp "Graphify" - visualize mạng lưới note như Obsidian graph view.
"""
import os
import re
import glob
from pathlib import Path
from typing import List, Dict

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


def build_graph(roots: List[str], max_files: int = 2000, include_orphans: bool = False) -> Dict:
    """
    Quét nhiều thư mục root, dựng graph.
    roots: list các đường dẫn thư mục chứa .md
    Trả về: {nodes: [...], edges: [...], stats: {...}}
    """
    nodes = {}          # stem (lowercase) -> node dict
    stem_to_id = {}     # stem lowercase -> node id
    edges = []
    file_count = 0

    # Pass 1: thu thập tất cả file -> tạo node
    all_files = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        root_name = Path(root).name
        for fpath in glob.glob(f"{root}/**/*.md", recursive=True):
            if file_count >= max_files:
                break
            try:
                rel = Path(fpath).relative_to(root).as_posix()
            except ValueError:
                rel = Path(fpath).name
            stem = Path(fpath).stem
            key = stem.lower()
            node_id = key
            if node_id in stem_to_id:
                continue  # trùng tên -> bỏ qua bản sau
            stem_to_id[key] = node_id
            # Mốc "note ra đời" cho timelapse: birthtime (macOS) > ctime (Windows = creation) >
            # mtime; lấy min với mtime vì file copy/sync có thể mang mtime gốc cũ hơn ctime.
            try:
                st = os.stat(fpath)
                born = min(getattr(st, "st_birthtime", st.st_ctime), st.st_mtime)
            except OSError:
                born = 0
            nodes[node_id] = {
                "id": node_id,
                "label": stem,
                "folder": _top_folder(rel),
                "color": _color_for(rel),
                "path": f"{root_name}/{rel}",
                "fullpath": fpath,
                "links": 0,
                "t": born,
            }
            all_files.append((node_id, fpath))
            file_count += 1

    # Pass 2: parse wikilink -> tạo edge
    for node_id, fpath in all_files:
        try:
            content = Path(fpath).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for target_stem in doc_wikilink(content):
            if target_stem in stem_to_id and target_stem != node_id:
                edges.append({"source": node_id, "target": stem_to_id[target_stem]})
                nodes[node_id]["links"] += 1
                nodes[stem_to_id[target_stem]]["links"] += 1

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
