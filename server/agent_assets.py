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


def _ghi(meta, files, links) -> dict:
    """meta MỚI mang danh sách vừa đổi. Rỗng cả hai thì GỠ hẳn khoá `assets` chứ không để lại
    một khoá rỗng: frontmatter là thứ người ta mở ra đọc, đừng rải xác trong đó."""
    moi = dict(meta or {})
    if files or links:
        moi["assets"] = {"files": files, "links": links}
    else:
        moi.pop("assets", None)
    return moi


def them_file(meta, path, name="") -> tuple:
    """Gắn một file có sẵn trong brain. Trùng đường dẫn thì trả id CŨ, không thêm lần hai.

    Trả (meta_moi, id). Ném ValueError nếu thiếu đường dẫn hoặc đã chạm trần.
    """
    duong = str(path or "").strip()
    if not duong:
        raise ValueError("thiếu đường dẫn")
    kho = doc(meta)
    for f in kho["files"]:
        if f["path"] == duong:
            return _ghi(meta, kho["files"], kho["links"]), f["id"]
    if len(kho["files"]) >= TRAN_MOI_LOAI:
        raise ValueError(f"Mỗi trợ lý chỉ gắn được tối đa {TRAN_MOI_LOAI} file")
    fid = uuid.uuid4().hex
    ten = str(name or "").strip() or duong.replace("\\", "/").split("/")[-1]
    kho["files"].append({"id": fid, "path": duong, "name": ten[:_TEN_MAX],
                         "pinned": False, "added_at": time.time()})
    return _ghi(meta, _xep(kho["files"]), kho["links"]), fid


def them_link(meta, url, label="") -> tuple:
    """Như them_file nhưng cho link. Caller phải chặn scheme lạ trước (chỉ http/https)."""
    u = str(url or "").strip()
    if not u:
        raise ValueError("thiếu URL")
    kho = doc(meta)
    for l in kho["links"]:
        if l["url"] == u:
            return _ghi(meta, kho["files"], kho["links"]), l["id"]
    if len(kho["links"]) >= TRAN_MOI_LOAI:
        raise ValueError(f"Mỗi trợ lý chỉ gắn được tối đa {TRAN_MOI_LOAI} link")
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
