"""Sổ THƯ MỤC và ràng buộc phiên cho trang Coding (0.63.1).

Vì sao có file này
------------------
Trước 0.63.0, sai Javis sửa một dự án phải nói trong khung chat chung, và engine chạy với
`cwd = <brain>`. Hậu quả: model đọc nhầm cây thư mục, không chỗ nào ghi "đang làm ở đâu", và
mở hai việc song song trên cùng một dự án là giẫm chân nhau.

Kho này giữ đúng ba thứ mà khung chat sẵn có KHÔNG biết:

  1. **Sổ thư mục** của từng brain: thư mục nào đã khai, nằm ở đâu.
  2. **Ràng buộc của một phiên**: phiên này làm ở thư mục nào, nhánh nào, worktree nào, mức
     quyền nào. Khoá theo `session_id` của kho phiên (`sessions.py`).
  3. **Điểm hồi**: tag git để `git reset --hard` kéo về được khi model sửa hỏng.

THƯ MỤC chứ không phải REPO (đổi ở 0.63.1)
------------------------------------------
Bản 0.63.0 bắt thư mục phải là repo git, không có `.git` thì TỪ CHỐI kèm câu "chạy git init
trước đi". Chủ dự án chỉ ra đó là bắt người dùng làm việc vặt cho vừa mô hình dữ liệu của
Javis: một thư mục script, một thư mục tài liệu, một dự án mới tinh chưa init đều là chỗ làm
việc hợp lệ.

Nay git là một THUỘC TÍNH ĐỌC ĐƯỢC của thư mục, không phải điều kiện để vào cửa. Không có
git thì ba thứ phụ thuộc git (nhánh, worktree, điểm hồi) tự vắng mặt trên giao diện, phần còn
lại chạy bình thường. Muốn có chúng thì bảo Javis `git init` ngay trong lượt chat, vì nó đang
đứng sẵn trong thư mục đó.

Ba ranh giới có chủ ý
---------------------
- **Xoá thư mục khỏi sổ KHÔNG đụng đĩa.** Người dùng bấm xoá là muốn Javis quên nó đi, không
  phải muốn mất mã nguồn. Nhầm hai thứ này một lần là mất việc thật.
- **Worktree luôn mở NHÁNH MỚI** `javis/<phiên>` tách từ nhánh gốc, chứ không checkout thẳng
  nhánh gốc. Git từ chối checkout cùng một nhánh ở hai worktree, mà nhánh gốc thì gần như
  luôn đang được checkout ở cây chính, nên cách kia hỏng ngay lần đầu dùng.
- **Không tự tạo commit.** Điểm hồi là TAG trên HEAD hiện tại. Tự commit hộ là ghi vào lịch sử
  của người khác; tag thì thêm được, gỡ được, và không đổi thứ gì đang có.

Stdlib-only, không import main, không import FastAPI: test được bằng một thư mục tạm.
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import winproc            # lệnh con chạy câm trên Windows (không nháy cửa sổ console đen)
from config import STATE_DIR

STORE_PATH = STATE_DIR / "coding.json"
_lock = threading.RLock()

# Kênh của MỌI phiên trang Coding. Một hằng, KHÔNG nhét id thư mục vào.
#
# Bản 0.63.0 dùng `coding:<id thư mục>` và điều đó sai về bản chất: thư mục là thứ phiên đang
# LÀM VIỆC TRONG, có thể đổi giữa chừng, không phải danh tính của phiên. Nhét vào kênh thì đổi
# thư mục là phiên vẫn nằm dưới thư mục cũ trong danh sách, và một phiên CHƯA chọn thư mục thì
# không có kênh nào để mở. Nay thư mục chỉ là một ràng buộc đọc từ kho này.
KENH = "coding:phien"

# Nơi đặt worktree của các phiên. Ngoài cây thư mục gốc, cố ý: worktree nằm TRONG nó thì mọi
# lệnh quét file của chính dự án đó (test, lint, build) lại thấy một bản sao của chính mình.
WORKTREE_DIR = STATE_DIR / "worktrees"

MUC_QUYEN = ("suggest", "auto", "full")
# Mặc định `auto` chứ không `full`: phiên mới mở đọc được, sửa file được, chạy test được,
# nhưng chưa tự đẩy ra ngoài. Ai cần toàn quyền thì bật một cú bấm ở chip, và lúc đó việc bật
# là một hành động có chủ ý chứ không phải thứ họ được thừa kế mà không biết.
MUC_QUYEN_MAC_DINH = "auto"

TEN_MAX = 60
GIT_TIMEOUT = 30

LOI_CAN_GIT = ("Thư mục này chưa phải repo git nên chưa có {viec}. "
               "Nhắn Javis `git init` giúp một câu là xong, rồi thử lại.")


class LoiCoding(Exception):
    """Lỗi NÓI ĐƯỢC cho người dùng. Route bắt cái này và trả 400 kèm nguyên văn."""


def _now() -> float:
    return time.time()


def _sid_ngan(sid: str) -> str:
    """Tám ký tự đầu của session id, dùng đặt tên nhánh/worktree/tag.

    Đủ để không trùng trong một brain, và ngắn để tên nhánh còn đọc được bằng mắt trên màn
    hình điện thoại. Lọc ký tự lạ vì chuỗi này đi thẳng vào tên nhánh git.
    """
    s = re.sub(r"[^0-9a-zA-Z]", "", str(sid or ""))[:8]
    return s or "phien"


# ============================================================
# Kho JSON
# ============================================================
def _rong() -> dict:
    return {"version": 2, "thu_muc": [], "phien": {}}


def _di_tru(d: dict) -> dict:
    """Sổ 0.63.0 dùng khoá `repos` và ràng buộc `repo`. Đổi tên tại chỗ lúc đọc.

    Làm ở đây chứ không bằng script: sổ này nhỏ, và bắt người vận hành chạy một lệnh sau khi
    cập nhật là cách chắc chắn nhất để có người không chạy rồi mất sổ.
    """
    if isinstance(d.get("repos"), list) and not d.get("thu_muc"):
        d["thu_muc"] = d.pop("repos")
    d.pop("repos", None)
    for rec in (d.get("phien") or {}).values():
        if isinstance(rec, dict) and "repo" in rec and "thu_muc" not in rec:
            rec["thu_muc"] = rec.pop("repo")
        if isinstance(rec, dict):
            rec.pop("repo", None)
    d["version"] = 2
    return d


def _load() -> dict:
    try:
        d = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _rong()
    except Exception:
        # File hỏng (đĩa đầy giữa lúc ghi, sửa tay sai cú pháp): đổi tên rồi bắt đầu lại. Ném
        # lỗi ở đây là cả trang Coding không mở được, mà thứ mất đi chỉ là một sổ khai báo
        # dựng lại trong ba mươi giây.
        try:
            STORE_PATH.rename(STORE_PATH.with_suffix(".json.hong"))
        except Exception:
            pass
        return _rong()
    if not isinstance(d, dict):
        return _rong()
    if not isinstance(d.get("thu_muc"), list):
        d["thu_muc"] = []
    if not isinstance(d.get("phien"), dict):
        d["phien"] = {}
    return _di_tru(d)


def _save(d: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STORE_PATH)


# ============================================================
# Git - thuộc tính của thư mục, KHÔNG phải điều kiện vào cửa
# ============================================================
def _git(args: List[str], cwd: str) -> str:
    """Chạy một lệnh git, trả stdout đã strip. Lỗi thì ném LoiCoding kèm stderr của git.

    Nguyên văn stderr của git đi thẳng ra giao diện là CỐ Ý: "fatal: 'x' is already checked
    out at '/y'" nói đúng vấn đề hơn mọi câu tóm tắt mà file này nghĩ ra được.
    """
    try:
        p = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT,
                           creationflags=winproc.no_window())
    except FileNotFoundError:
        raise LoiCoding("Máy này chưa cài git.")
    except subprocess.TimeoutExpired:
        raise LoiCoding(f"Lệnh git chạy quá {GIT_TIMEOUT} giây, đã dừng: git {' '.join(args)}")
    if p.returncode != 0:
        loi = (p.stderr or p.stdout or "").strip().splitlines()
        raise LoiCoding(f"git {args[0]} hỏng: {loi[-1] if loi else 'không rõ lý do'}")
    return (p.stdout or "").strip()


def la_git(duong_dan: str) -> bool:
    """Thư mục này có phải gốc một repo git không. Chỉ để BIẾT, không để chặn.

    Kiểm `.git` TỒN TẠI chứ không kiểm nó là thư mục: trong một worktree hay một submodule,
    `.git` là một FILE trỏ sang chỗ khác. Đòi thư mục là từ chối nhầm đúng những cây mà chính
    trang này sinh ra.
    """
    try:
        return (Path(duong_dan).expanduser().resolve() / ".git").exists()
    except Exception:
        return False


def nhanh_hien_tai(duong_dan: str) -> str:
    """Tên nhánh đang checkout, hoặc "" khi không phải repo git / HEAD rời / đọc không được."""
    if not la_git(duong_dan):
        return ""
    try:
        ten = _git(["rev-parse", "--abbrev-ref", "HEAD"], duong_dan)
        return "" if ten == "HEAD" else ten
    except Exception:
        return ""


def danh_sach_nhanh(duong_dan: str) -> List[str]:
    if not la_git(duong_dan):
        return []
    try:
        ra = _git(["for-each-ref", "--format=%(refname:short)", "refs/heads"], duong_dan)
    except Exception:
        return []
    return [x.strip() for x in ra.splitlines() if x.strip()]


def cay_sach(duong_dan: str) -> bool:
    """Working tree không có sửa đổi chưa commit. Không phải git hoặc đọc hỏng thì trả False.

    Nghiêng về "bẩn" là cố ý: nhầm theo hướng này chỉ làm người dùng thấy thêm một lời nhắc,
    nhầm theo hướng kia làm họ tưởng không có gì để mất rồi bấm rollback.
    """
    if not la_git(duong_dan):
        return False
    try:
        return _git(["status", "--porcelain"], duong_dan) == ""
    except Exception:
        return False


# ============================================================
# Sổ thư mục
# ============================================================
def danh_sach_thu_muc(brain: str = "") -> List[Dict[str, Any]]:
    d = _load()
    ds = [r for r in d["thu_muc"] if not brain or (r.get("brain") or "") == brain]
    return [dict(r) for r in ds]


def thu_muc(tid: str) -> Optional[Dict[str, Any]]:
    for r in _load()["thu_muc"]:
        if r.get("id") == tid:
            return dict(r)
    return None


def them_thu_muc(duong_dan: str, brain: str = "", ten: str = "") -> Dict[str, Any]:
    """Khai một thư mục làm chỗ làm việc. KHÔNG đòi nó là repo git.

    Chỉ từ chối ba thứ không thể làm việc được: chuỗi rỗng, đường dẫn đọc không ra, và thứ
    không phải thư mục. Còn lại nhận hết - có git hay không là chuyện đọc ra sau.
    """
    raw = str(duong_dan or "").strip()
    if not raw:
        raise LoiCoding("Chưa nhập đường dẫn thư mục.")
    p = Path(raw).expanduser()
    try:
        p = p.resolve()
    except Exception:
        raise LoiCoding(f"Đường dẫn không đọc được: {raw}")
    if not p.is_dir():
        raise LoiCoding(f"Không có thư mục {p}")
    with _lock:
        d = _load()
        for r in d["thu_muc"]:
            if r.get("duong_dan") == str(p) and (r.get("brain") or "") == (brain or ""):
                return dict(r)
        rec = {
            "id": uuid.uuid4().hex[:12],
            "ten": (str(ten).strip() or p.name)[:TEN_MAX],
            "duong_dan": str(p),
            "brain": brain or "",
            "them_luc": _now(),
        }
        d["thu_muc"].append(rec)
        _save(d)
        return dict(rec)


def bo_thu_muc(tid: str) -> bool:
    """Bỏ khỏi SỔ. Không đụng một byte nào trên đĩa - xem docstring đầu file."""
    with _lock:
        d = _load()
        truoc = len(d["thu_muc"])
        d["thu_muc"] = [r for r in d["thu_muc"] if r.get("id") != tid]
        if len(d["thu_muc"]) == truoc:
            return False
        _save(d)
        return True


# ============================================================
# Ràng buộc của một phiên
# ============================================================
def rang_buoc(sid: str) -> Dict[str, Any]:
    return dict(_load()["phien"].get(str(sid or ""), {}))


def dat_rang_buoc(sid: str, *, thu_muc_id: Optional[str] = None, nhanh: Optional[str] = None,
                  muc_quyen: Optional[str] = None, worktree: Optional[str] = None) -> Dict[str, Any]:
    """Ghi đè từng trường một. Trường nào truyền None thì giữ nguyên giá trị cũ.

    `thu_muc_id=""` là hợp lệ và có nghĩa: GỠ thư mục khỏi phiên, quay về chat trong brain.
    """
    sid = str(sid or "").strip()
    if not sid:
        raise LoiCoding("Thiếu session id.")
    if muc_quyen is not None and muc_quyen not in MUC_QUYEN:
        raise LoiCoding(f"Mức quyền phải là một trong {', '.join(MUC_QUYEN)}.")
    if thu_muc_id is not None and thu_muc_id and not thu_muc(thu_muc_id):
        raise LoiCoding("Thư mục không có trong sổ.")
    with _lock:
        d = _load()
        cu = dict(d["phien"].get(sid, {}))
        if thu_muc_id is not None:
            cu["thu_muc"] = thu_muc_id
            # Đổi thư mục thì worktree và nhánh của thư mục CŨ không còn nghĩa gì. Giữ lại là
            # để một đường dẫn chết nằm trong ràng buộc rồi lượt sau chạy nhầm chỗ.
            cu["worktree"] = ""
            cu["nhanh"] = ""
        if nhanh is not None:
            cu["nhanh"] = nhanh
        if muc_quyen is not None:
            cu["muc_quyen"] = muc_quyen
        if worktree is not None:
            cu["worktree"] = worktree
        cu.setdefault("muc_quyen", MUC_QUYEN_MAC_DINH)
        cu["sua_luc"] = _now()
        d["phien"][sid] = cu
        _save(d)
        return dict(cu)


def xoa_rang_buoc(sid: str) -> None:
    with _lock:
        d = _load()
        if d["phien"].pop(str(sid or ""), None) is not None:
            _save(d)


def muc_quyen_cua_phien(sid: str) -> str:
    return rang_buoc(sid).get("muc_quyen") or MUC_QUYEN_MAC_DINH


def cwd_cua_phien(sid: str) -> str:
    """Thư mục engine phải chạy trong đó, hoặc "" khi phiên chưa gắn thư mục nào.

    Đây là hàm DUY NHẤT main.py cần gọi ở đường chat. Trả "" thì nơi gọi giữ nguyên hành vi cũ
    (cwd = brain), nên một phiên chat thường không đổi gì - và một phiên Coding CHƯA chọn thư
    mục cũng chat được ngay, chỉ là đang đứng trong bộ não.

    Worktree đã bị xoá tay ngoài giao diện thì suy biến về chính thư mục gốc thay vì ném lỗi:
    mất một thư mục tạm không đáng để cả phiên không nhắn được.
    """
    rb = rang_buoc(sid)
    wt = (rb.get("worktree") or "").strip()
    if wt and Path(wt).is_dir():
        return wt
    r = thu_muc(rb.get("thu_muc") or "")
    if r and Path(r["duong_dan"]).is_dir():
        return r["duong_dan"]
    return ""


def _can_git(sid: str, viec: str) -> str:
    """cwd của phiên, sau khi chắc chắn nó là repo git. Không phải thì nói rõ cách có được."""
    cwd = cwd_cua_phien(sid)
    if not cwd:
        raise LoiCoding("Phiên này chưa gắn thư mục nào.")
    if not la_git(cwd):
        raise LoiCoding(LOI_CAN_GIT.format(viec=viec))
    return cwd


# ============================================================
# Worktree
# ============================================================
def tao_worktree(sid: str) -> Dict[str, Any]:
    """Mở một worktree riêng cho phiên, trên nhánh mới `javis/<phiên>` tách từ nhánh đã chọn.

    Nhánh MỚI chứ không phải nhánh gốc: git từ chối checkout một nhánh ở hai worktree cùng
    lúc, mà nhánh gốc thì gần như luôn đang được checkout ở cây chính.
    """
    rb = rang_buoc(sid)
    r = thu_muc(rb.get("thu_muc") or "")
    if not r:
        raise LoiCoding("Phiên này chưa gắn thư mục nào.")
    cu = (rb.get("worktree") or "").strip()
    if cu and Path(cu).is_dir():
        return {"worktree": cu, "nhanh": rb.get("nhanh") or "", "da_co": True}
    if not la_git(r["duong_dan"]):
        raise LoiCoding(LOI_CAN_GIT.format(viec="worktree"))
    goc = (rb.get("nhanh") or nhanh_hien_tai(r["duong_dan"]) or "HEAD")
    ten_nhanh = f"javis/{_sid_ngan(sid)}"
    dich = WORKTREE_DIR / f"{r['id']}-{_sid_ngan(sid)}"
    WORKTREE_DIR.mkdir(parents=True, exist_ok=True)
    # Nhánh của phiên có thể ĐÃ TỒN TẠI: gỡ worktree không xoá nhánh, nên bật lại lần hai là
    # `-b` nổ "a branch named ... already exists" và người dùng thấy một lỗi git thô cho một
    # việc họ vừa làm được cách đó một phút. Có rồi thì checkout lại chính nó, và đó cũng là
    # hành vi đúng: công việc dở dang của phiên nằm trên nhánh ấy.
    da_co_nhanh = ten_nhanh in danh_sach_nhanh(r["duong_dan"])
    them = ["worktree", "add"] + ([str(dich), ten_nhanh] if da_co_nhanh
                                  else ["-b", ten_nhanh, str(dich), goc])
    _git(them, r["duong_dan"])
    dat_rang_buoc(sid, worktree=str(dich), nhanh=ten_nhanh)
    return {"worktree": str(dich), "nhanh": ten_nhanh, "da_co": False}


def go_worktree(sid: str, ep: bool = False) -> Dict[str, Any]:
    """Gỡ worktree của phiên.

    Còn sửa đổi chưa commit mà không `ep` thì TỪ CHỐI và nói rõ đang giữ ở đâu. Gỡ im lặng một
    thư mục có việc dở là kiểu mất mát người dùng không bao giờ ngờ tới.
    """
    rb = rang_buoc(sid)
    wt = (rb.get("worktree") or "").strip()
    if not wt:
        return {"da_go": False, "ly_do": "Phiên này không có worktree."}
    r = thu_muc(rb.get("thu_muc") or "")
    if not r:
        raise LoiCoding("Phiên này chưa gắn thư mục nào.")
    if Path(wt).is_dir() and not ep and not cay_sach(wt):
        return {"da_go": False, "giu_tai": wt,
                "ly_do": f"Worktree còn sửa đổi chưa commit, đang giữ tại {wt}"}
    _git(["worktree", "remove", "--force", wt], r["duong_dan"])
    dat_rang_buoc(sid, worktree="")
    return {"da_go": True}


# ============================================================
# Điểm hồi
# ============================================================
def _tag_moi(sid: str, cwd: str) -> str:
    tien_to = f"javis/{_sid_ngan(sid)}/"
    try:
        da_co = _git(["tag", "--list", tien_to + "*"], cwd).splitlines()
    except Exception:
        da_co = []
    so = 0
    for t in da_co:
        duoi = t.strip().rsplit("/", 1)[-1]
        if duoi.isdigit():
            so = max(so, int(duoi))
    return f"{tien_to}{so + 1}"


def tao_diem_hoi(sid: str) -> Dict[str, Any]:
    """Đặt một tag lên HEAD hiện tại để rollback được. KHÔNG commit hộ.

    Repo chưa có commit nào thì không có HEAD để gắn tag: nói thẳng chứ không ném lỗi git thô,
    vì đây là cảnh có thật ở một thư mục vừa `git init`.
    """
    cwd = _can_git(sid, "điểm hồi")
    try:
        head = _git(["rev-parse", "HEAD"], cwd)
    except LoiCoding:
        raise LoiCoding("Repo chưa có commit nào nên chưa đặt được điểm hồi. "
                        "Commit lần đầu rồi thử lại.")
    tag = _tag_moi(sid, cwd)
    _git(["tag", tag, head], cwd)
    with _lock:
        d = _load()
        rec = dict(d["phien"].get(str(sid), {}))
        ds = list(rec.get("diem_hoi") or [])
        ds.append({"tag": tag, "commit": head, "luc": _now()})
        rec["diem_hoi"] = ds[-20:]     # giữ 20 mốc gần nhất, đủ để lùi lại mà sổ không phình
        rec.setdefault("muc_quyen", MUC_QUYEN_MAC_DINH)
        d["phien"][str(sid)] = rec
        _save(d)
    return {"tag": tag, "commit": head, "cwd": cwd}


def danh_sach_diem_hoi(sid: str) -> List[Dict[str, Any]]:
    return list(rang_buoc(sid).get("diem_hoi") or [])


def rollback(sid: str, tag: str) -> Dict[str, Any]:
    """`git reset --hard <tag>`. Chỉ nhận tag CỦA CHÍNH phiên này.

    Giới hạn đó không phải hình thức: nhận tag bất kỳ thì một cú bấm nhầm kéo cả cây về một
    mốc của phiên khác, và `--hard` thì không hỏi lại.
    """
    tag = str(tag or "").strip()
    cwd = _can_git(sid, "điểm hồi")
    if tag not in {x.get("tag") for x in danh_sach_diem_hoi(sid)}:
        raise LoiCoding("Điểm hồi đó không phải của phiên này.")
    _git(["reset", "--hard", tag], cwd)
    return {"ok": True, "tag": tag, "cwd": cwd}
