"""Tài liệu & link gắn vào MỘT trợ lý (agent).

Song sinh với bộ tài liệu của project và của cuộc trò chuyện (server/sessions.py), nhưng
KHÔNG nằm trong SQLite: một trợ lý là một file `.md` trong brain, nên tài liệu của nó phải
đi theo đúng file đó. Xuất trợ lý ra gửi cho người khác, copy brain sang máy mới, hay mở
file lên sửa tay đều giữ nguyên danh sách; để trong DB thì trợ lý qua tay người khác là
thành cái vỏ rỗng, im lặng.

Chỗ lưu: khoá `assets` trong frontmatter.

    assets:
      files:
        - id: 8f3a...
          path: sources/bang-gia.md
          name: bang-gia.md
          pinned: true
          added_at: 1758412800.0
      links:
        - id: 1c90...
          url: https://vi.wikipedia.org/...
          label: Bảng thuế 2026
          pinned: false
          added_at: 1758412800.0

Mọi hàm ở đây là hàm THUẦN trên dict meta: nhận meta, trả meta MỚI (không sửa tại chỗ).
Phần đọc/ghi file do main.py lo (_read_md/_write_md), nên test được mà không cần dựng brain
thật, và không kéo theo FastAPI.

Đường dẫn file KHÔNG được kiểm ở đây: module này không biết trợ lý thuộc brain nào và không
được phép đoán. Caller phải cho qua rào path của brain (main._safe_path) TRƯỚC khi gọi, đúng
như bộ hàm project bên sessions.py.
"""
import time
import uuid

# Trần mỗi loại. Danh sách này đi vào system prompt của trợ lý ở MỌI lượt, và nằm trong
# frontmatter của một file người ta còn mở ra đọc bằng mắt - hai lý do để đừng cho nó phình.
TRAN_MOI_LOAI = 50
_TEN_MAX = 160
_URL_MAX = 2000
DESCRIPTION_MAX = 200    # same cap as the description of a project document (sessions.PROJECT_ASSET_NOTE_MAX)


def _sach_hang(h, khoa_chinh):
    """Một hàng đã lưu → dict đúng hình dạng. Bỏ hàng rác (sửa tay hỏng, thiếu khoá chính)."""
    if not isinstance(h, dict):
        return None
    chinh = str(h.get(khoa_chinh) or "").strip()
    if not chinh:
        return None
    try:
        moc = float(h.get("added_at") or 0)
    except (TypeError, ValueError):
        moc = 0.0
    # Dựng đúng THỨ TỰ khoá muốn thấy trong frontmatter: yaml.safe_dump giữ nguyên thứ tự
    # của dict (sort_keys=False), nên nhét `name` vào sau cùng là file mở ra đọc lộn xộn.
    ra = {"id": str(h.get("id") or "").strip() or uuid.uuid4().hex, khoa_chinh: chinh}
    if khoa_chinh == "path":
        ra["name"] = str(h.get("name") or "").strip() or chinh.replace("\\", "/").split("/")[-1]
    else:
        ra["label"] = str(h.get("label") or "").strip()
    ra["pinned"] = bool(h.get("pinned"))
    ra["added_at"] = moc
    # 2026-11-13: one line saying what the document holds (Javis writes it, the owner can fix it). Kept only when set,
    # so an agent file without descriptions reads exactly as before.
    desc = " ".join(str(h.get("description") or "").split())[:DESCRIPTION_MAX]
    if desc:
        ra["description"] = desc
    return ra


def _ds(meta, loai, khoa_chinh):
    kho = (meta or {}).get("assets")
    tho = (kho or {}).get(loai) if isinstance(kho, dict) else None
    ra = []
    for h in (tho or []):
        s = _sach_hang(h, khoa_chinh)
        if s:
            ra.append(s)
    return ra


def _xep(ds):
    """Ghim lên đầu, rồi mới nhất trước. Cùng thứ tự với bộ project (ORDER BY pinned, added_at)
    để hai danh sách trên cùng một ngăn kéo không xếp khác nhau."""
    return sorted(ds, key=lambda h: (0 if h.get("pinned") else 1, -float(h.get("added_at") or 0)))


def doc(meta) -> dict:
    """{"files": [...], "links": [...]} của một trợ lý, đã dọn và xếp thứ tự."""
    return {"files": _xep(_ds(meta, "files", "path")),
            "links": _xep(_ds(meta, "links", "url"))}


def _ghi(meta, files, links, repo_rows=None) -> dict:
    """meta MỚI mang danh sách vừa đổi. Rỗng cả hai thì GỠ hẳn khoá `assets` chứ không để lại
    một khoá rỗng: frontmatter là thứ người ta mở ra đọc, đừng rải xác trong đó.

    `repo_rows` None keeps the assistant's GitHub repos as they are (every file and link edit goes through here)."""
    moi = dict(meta or {})
    repo_rows = repos(meta) if repo_rows is None else repo_rows
    if files or links or repo_rows:
        kho = {"files": files, "links": links}
        if repo_rows:
            kho["repos"] = repo_rows
        moi["assets"] = kho
    else:
        moi.pop("assets", None)
    return moi


# ---- GitHub repos of an assistant (2026-11-15) ----
# Owner: "cả trong tài liệu của agent ... cũng có khả năng thêm repo". Stored next to its files and links, so the list
# travels with the assistant's file; every private chat with it gets the repos on its next turn
# (github_repos.seed_session), each chat on its own branch.
#
#     assets:
#       repos:
#         - full_name: owner/name
#           added_at: 1758412800.0
#
# The name is checked (and the repo cloned) by the caller, through github_repos, before it is written here.
REPOS_MAX = 10


def repos(meta) -> list:
    """[{"full_name", "added_at"}] of an assistant, oldest first, cleaned (rows broken by a hand edit are dropped)."""
    kho = (meta or {}).get("assets")
    raw = kho.get("repos") if isinstance(kho, dict) else None
    out, seen = [], set()
    for h in (raw or []):
        name = str((h.get("full_name") if isinstance(h, dict) else h) or "").strip().strip("/")
        if not name or "/" not in name or name.lower() in seen:
            continue
        seen.add(name.lower())
        try:
            at = float(h.get("added_at") or 0) if isinstance(h, dict) else 0.0
        except (TypeError, ValueError):
            at = 0.0
        out.append({"full_name": name[:_TEN_MAX], "added_at": at})
    return out[:REPOS_MAX]


def repo_names(meta) -> list:
    return [r["full_name"] for r in repos(meta)]


def set_repos(meta, names) -> tuple:
    """Make the assistant's repo list exactly `names` (case-insensitive). A repo kept keeps its `added_at`.
    Returns (new meta, {"added": [...], "removed": [...]}). Raises ValueError past REPOS_MAX."""
    wanted = []
    for n in names or []:
        n = str(n or "").strip()
        if n and n.lower() not in {w.lower() for w in wanted}:
            wanted.append(n)
    if len(wanted) > REPOS_MAX:
        import localefmt
        raise ValueError(localefmt.chu(f"Mỗi trợ lý chỉ gắn được tối đa {REPOS_MAX} repository",
                                       f"Each assistant can have at most {REPOS_MAX} repositories"))
    have = repos(meta)
    by_low = {r["full_name"].lower(): r for r in have}
    now = time.time()
    rows = [by_low.get(n.lower()) or {"full_name": n, "added_at": now + i * 1e-6} for i, n in enumerate(wanted)]
    rows.sort(key=lambda r: r["added_at"])
    added = [n for n in wanted if n.lower() not in by_low]
    removed = [r["full_name"] for r in have if r["full_name"].lower() not in {w.lower() for w in wanted}]
    kho = doc(meta)
    return _ghi(meta, kho["files"], kho["links"], rows), {"added": added, "removed": removed}


def them_file(meta, path, name="") -> tuple:
    """Gắn một file có sẵn trong brain. Trùng đường dẫn thì trả id CŨ, không thêm lần hai.

    Trả (meta_moi, id). Ném ValueError nếu thiếu đường dẫn hoặc đã chạm trần.
    """
    duong = str(path or "").strip()
    if not duong:
        import localefmt
        raise ValueError(localefmt.chu("thiếu đường dẫn", "missing path"))
    kho = doc(meta)
    for f in kho["files"]:
        if f["path"] == duong:
            return _ghi(meta, kho["files"], kho["links"]), f["id"]
    if len(kho["files"]) >= TRAN_MOI_LOAI:
        import localefmt
        raise ValueError(localefmt.chu(f"Mỗi trợ lý chỉ gắn được tối đa {TRAN_MOI_LOAI} file",
                                       f"Each assistant can have at most {TRAN_MOI_LOAI} files"))
    fid = uuid.uuid4().hex
    ten = str(name or "").strip() or duong.replace("\\", "/").split("/")[-1]
    kho["files"].append({"id": fid, "path": duong, "name": ten[:_TEN_MAX],
                         "pinned": False, "added_at": time.time()})
    return _ghi(meta, _xep(kho["files"]), kho["links"]), fid


def them_link(meta, url, label="") -> tuple:
    """Như them_file nhưng cho link. Caller phải chặn scheme lạ trước (chỉ http/https)."""
    u = str(url or "").strip()
    if not u:
        import localefmt
        raise ValueError(localefmt.chu("thiếu URL", "missing URL"))
    kho = doc(meta)
    for l in kho["links"]:
        if l["url"] == u:
            return _ghi(meta, kho["files"], kho["links"]), l["id"]
    if len(kho["links"]) >= TRAN_MOI_LOAI:
        import localefmt
        raise ValueError(localefmt.chu(f"Mỗi trợ lý chỉ gắn được tối đa {TRAN_MOI_LOAI} link",
                                       f"Each assistant can have at most {TRAN_MOI_LOAI} links"))
    lid = uuid.uuid4().hex
    kho["links"].append({"id": lid, "url": u[:_URL_MAX], "label": str(label or "").strip()[:_TEN_MAX],
                         "pinned": False, "added_at": time.time()})
    return _ghi(meta, kho["files"], _xep(kho["links"])), lid


def _bo(meta, loai, hid) -> tuple:
    kho = doc(meta)
    con = [h for h in kho[loai] if h["id"] != hid]
    if len(con) == len(kho[loai]):
        return meta, False
    kho[loai] = con
    return _ghi(meta, kho["files"], kho["links"]), True


def go_file(meta, fid) -> tuple:
    """GỠ KHỎI TRỢ LÝ, KHÔNG xoá file trên đĩa. File nằm trong brain và có đời sống riêng."""
    return _bo(meta, "files", str(fid or ""))


def go_link(meta, lid) -> tuple:
    return _bo(meta, "links", str(lid or ""))


def _ghim(meta, loai, hid, on) -> tuple:
    kho = doc(meta)
    thay = False
    for h in kho[loai]:
        if h["id"] == hid:
            h["pinned"] = bool(on)
            thay = True
    if not thay:
        return meta, False
    return _ghi(meta, _xep(kho["files"]), _xep(kho["links"])), True


def ghim_file(meta, fid, on) -> tuple:
    """Ghim = NẠP SẴN nội dung file vào prompt của trợ lý, không chỉ đổi thứ tự danh sách
    (xem main._liet_ke_tai_lieu). Cùng nghĩa với nút ghim bên project."""
    return _ghim(meta, "files", str(fid or ""), on)


def ghim_link(meta, lid, on) -> tuple:
    return _ghim(meta, "links", str(lid or ""), on)


def describe(meta, kind, ref, text) -> tuple:
    """Write the one-line description of an attached file (`kind="file"`, `ref` its stored path or id) or link
    (`kind="link"`, `ref` its URL or id). Empty text removes it. Returns (new meta, True) or (meta, False) when the
    assistant has no such document."""
    if kind not in ("file", "link"):
        return meta, False
    loai, key = ("files", "path") if kind == "file" else ("links", "url")
    ref = str(ref or "").strip()
    kho = doc(meta)
    hit = [h for h in kho[loai] if h["id"] == ref or h[key] == ref]
    if not ref or len(hit) != 1:
        return meta, False
    line = " ".join(str(text or "").split())[:DESCRIPTION_MAX]
    if line:
        hit[0]["description"] = line
    else:
        hit[0].pop("description", None)
    return _ghi(meta, kho["files"], kho["links"]), True
