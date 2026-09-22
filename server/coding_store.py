"""Sổ repo và ràng buộc phiên cho trang Coding (0.63.0).

Vì sao có file này
------------------
Trước 0.63.0, sai Javis sửa một repo phải nói trong khung chat chung, và engine chạy với
`cwd = <brain>`. Hậu quả: model đọc nhầm cây thư mục, không chỗ nào ghi "đang làm ở repo nào
nhánh nào", và mở hai việc song song trên cùng repo là giẫm chân nhau.

Kho này giữ đúng ba thứ mà khung chat sẵn có KHÔNG biết:

  1. **Sổ repo** của từng brain: repo nào đã khai báo, nằm ở đâu.
  2. **Ràng buộc của một phiên**: phiên này làm ở repo nào, nhánh nào, worktree nào, mức quyền
     nào. Khoá theo `session_id` của kho phiên (`sessions.py`), nên một phiên coding vẫn là
     một phiên chat bình thường, chỉ khác cái kênh `coding:<repo id>`.
  3. **Điểm hồi**: tag git tạo TRƯỚC mỗi lượt ở mức toàn quyền, để `git reset --hard` kéo về
     được khi model sửa hỏng.

Ba ranh giới có chủ ý
---------------------
- **Xoá repo khỏi sổ KHÔNG đụng đĩa.** Người dùng bấm xoá là muốn Javis quên nó đi, không phải
  muốn mất mã nguồn. Nhầm hai thứ này một lần là mất việc thật.
- **Worktree luôn mở NHÁNH MỚI** `javis/<phiên>` tách từ nhánh gốc, chứ không checkout thẳng
  nhánh gốc. Git từ chối checkout cùng một nhánh ở hai worktree, mà nhánh gốc thì gần như
  luôn đang được checkout ở cây chính, nên cách kia hỏng ngay lần đầu dùng.
- **Không tự tạo commit.** Điểm hồi là TAG trên HEAD hiện tại. Tự commit hộ là ghi vào lịch sử
  của người khác; tag thì thêm được, gỡ được, và không đổi thứ gì đang có.

Stdlib-only, không import main, không import FastAPI: test được bằng một repo git tạm.
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

# Nơi đặt worktree của các phiên. Ngoài cây repo, cố ý: worktree nằm TRONG repo thì mọi lệnh
# quét file của chính repo đó (test, lint, build) lại thấy một bản sao của chính mình.
WORKTREE_DIR = STATE_DIR / "worktrees"

MUC_QUYEN = ("suggest", "auto", "full")
# Mặc định `auto` chứ không `full`: phiên mới mở đọc được, sửa file được, chạy test được,
# nhưng chưa tự đẩy ra ngoài. Ai cần toàn quyền thì bật một cú bấm ở chip, và lúc đó việc bật
# là một hành động có chủ ý chứ không phải thứ họ được thừa kế mà không biết.
MUC_QUYEN_MAC_DINH = "auto"

TEN_MAX = 60
GIT_TIMEOUT = 30


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
def _load() -> dict:
    try:
        d = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": 1, "repos": [], "phien": {}}
    except Exception:
        # File hỏng (đĩa đầy giữa lúc ghi, sửa tay sai cú pháp): đổi tên rồi bắt đầu lại. Ném
        # lỗi ở đây là cả trang Coding không mở được, mà thứ mất đi chỉ là một sổ khai báo
        # dựng lại trong ba mươi giây.
        try:
            STORE_PATH.rename(STORE_PATH.with_suffix(".json.hong"))
        except Exception:
            pass
        return {"version": 1, "repos": [], "phien": {}}
    if not isinstance(d, dict):
        return {"version": 1, "repos": [], "phien": {}}
    d.setdefault("version", 1)
    # Di trú: sổ của bản cũ có thể thiếu hẳn một khoá. Đọc mà thiếu thì vá tại chỗ, không bắt
    # người vận hành chạy script.
    if not isinstance(d.get("repos"), list):
        d["repos"] = []
    if not isinstance(d.get("phien"), dict):
        d["phien"] = {}
    return d


def _save(d: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STORE_PATH)


# ============================================================
# Git
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


def la_repo_git(duong_dan: str) -> bool:
    """Thư mục này có phải gốc một repo git không.

    Kiểm `.git` TỒN TẠI chứ không kiểm nó là thư mục: trong một worktree hay một submodule,
    `.git` là một FILE trỏ sang chỗ khác. Đòi thư mục là từ chối nhầm đúng những repo mà trang
    này sinh ra.
    """
    try:
        return (Path(duong_dan).expanduser().resolve() / ".git").exists()
    except Exception:
        return False


def nhanh_hien_tai(duong_dan: str) -> str:
    """Tên nhánh đang checkout, hoặc "" khi đang ở HEAD rời hoặc đọc không được."""
    try:
        ten = _git(["rev-parse", "--abbrev-ref", "HEAD"], duong_dan)
        return "" if ten == "HEAD" else ten
    except Exception:
        return ""


def danh_sach_nhanh(duong_dan: str) -> List[str]:
    try:
        ra = _git(["for-each-ref", "--format=%(refname:short)", "refs/heads"], duong_dan)
    except Exception:
        return []
    return [x.strip() for x in ra.splitlines() if x.strip()]


def cay_sach(duong_dan: str) -> bool:
    """Working tree không có sửa đổi chưa commit. Đọc hỏng thì trả False (coi như bẩn).

    Nghiêng về "bẩn" là cố ý: nhầm theo hướng này chỉ làm người dùng thấy thêm một lời nhắc,
    nhầm theo hướng kia làm họ tưởng không có gì để mất rồi bấm rollback.
    """
    try:
        return _git(["status", "--porcelain"], duong_dan) == ""
    except Exception:
        return False


# ============================================================
# Sổ repo
# ============================================================
def list_repos(brain: str = "") -> List[Dict[str, Any]]:
    d = _load()
    ds = [r for r in d["repos"] if not brain or (r.get("brain") or "") == brain]
    return [dict(r) for r in ds]


def get_repo(rid: str) -> Optional[Dict[str, Any]]:
    for r in _load()["repos"]:
        if r.get("id") == rid:
            return dict(r)
    return None


def add_repo(duong_dan: str, brain: str = "", ten: str = "") -> Dict[str, Any]:
    raw = str(duong_dan or "").strip()
    if not raw:
        raise LoiCoding("Chưa nhập đường dẫn repo.")
    p = Path(raw).expanduser()
    try:
        p = p.resolve()
    except Exception:
        raise LoiCoding(f"Đường dẫn không đọc được: {raw}")
    if not p.is_dir():
        raise LoiCoding(f"Không có thư mục {p}")
    if not la_repo_git(str(p)):
        # Nói rõ nó KHÔNG phải repo git thay vì im lặng nhận: nhận vào thì mọi thứ còn lại của
        # trang (nhánh, worktree, điểm hồi) đều hỏng sau, xa chỗ gây lỗi.
        raise LoiCoding(f"{p} không phải một repo git (không thấy .git). "
                        f"Chạy `git init` ở đó trước, hoặc chọn đúng thư mục gốc của repo.")
    with _lock:
        d = _load()
        for r in d["repos"]:
            if r.get("duong_dan") == str(p) and (r.get("brain") or "") == (brain or ""):
                return dict(r)
        rec = {
            "id": uuid.uuid4().hex[:12],
            "ten": (str(ten).strip() or p.name)[:TEN_MAX],
            "duong_dan": str(p),
            "brain": brain or "",
            "nhanh_goc": nhanh_hien_tai(str(p)),
            "them_luc": _now(),
        }
        d["repos"].append(rec)
        _save(d)
        return dict(rec)


def remove_repo(rid: str) -> bool:
    """Xoá khỏi SỔ. Không đụng một byte nào trên đĩa - xem docstring đầu file."""
    with _lock:
        d = _load()
        truoc = len(d["repos"])
        d["repos"] = [r for r in d["repos"] if r.get("id") != rid]
        if len(d["repos"]) == truoc:
            return False
        _save(d)
        return True


# ============================================================
# Ràng buộc của một phiên
# ============================================================
def rang_buoc(sid: str) -> Dict[str, Any]:
    return dict(_load()["phien"].get(str(sid or ""), {}))


def dat_rang_buoc(sid: str, *, repo: Optional[str] = None, nhanh: Optional[str] = None,
                  muc_quyen: Optional[str] = None, worktree: Optional[str] = None) -> Dict[str, Any]:
    """Ghi đè từng trường một. Trường nào truyền None thì giữ nguyên giá trị cũ."""
    sid = str(sid or "").strip()
    if not sid:
        raise LoiCoding("Thiếu session id.")
    if muc_quyen is not None and muc_quyen not in MUC_QUYEN:
        raise LoiCoding(f"Mức quyền phải là một trong {', '.join(MUC_QUYEN)}.")
    if repo is not None and repo and not get_repo(repo):
        raise LoiCoding("Repo không có trong sổ.")
    with _lock:
        d = _load()
        cu = dict(d["phien"].get(sid, {}))
        if repo is not None:
            cu["repo"] = repo
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
    """Thư mục engine phải chạy trong đó, hoặc "" khi phiên này không phải phiên coding.

    Đây là hàm DUY NHẤT main.py cần gọi ở đường chat. Trả "" thì nơi gọi giữ nguyên hành vi cũ
    (cwd = brain), nên một phiên chat thường không đổi gì.

    Worktree đã bị xoá tay ngoài giao diện thì suy biến về chính repo thay vì ném lỗi: mất một
    thư mục tạm không đáng để cả phiên không nhắn được.
    """
    rb = rang_buoc(sid)
    wt = (rb.get("worktree") or "").strip()
    if wt and Path(wt).is_dir():
        return wt
    r = get_repo(rb.get("repo") or "")
    if r and Path(r["duong_dan"]).is_dir():
        return r["duong_dan"]
    return ""


# ============================================================
# Worktree
# ============================================================
def tao_worktree(sid: str) -> Dict[str, Any]:
    """Mở một worktree riêng cho phiên, trên nhánh mới `javis/<phiên>` tách từ nhánh đã chọn.

    Nhánh MỚI chứ không phải nhánh gốc: git từ chối checkout một nhánh ở hai worktree cùng
    lúc, mà nhánh gốc thì gần như luôn đang được checkout ở cây chính.
    """
    rb = rang_buoc(sid)
    r = get_repo(rb.get("repo") or "")
    if not r:
        raise LoiCoding("Phiên này chưa gắn repo nào.")
    cu = (rb.get("worktree") or "").strip()
    if cu and Path(cu).is_dir():
        return {"worktree": cu, "nhanh": rb.get("nhanh") or "", "da_co": True}
    goc = (rb.get("nhanh") or r.get("nhanh_goc") or nhanh_hien_tai(r["duong_dan"]) or "HEAD")
    ten_nhanh = f"javis/{_sid_ngan(sid)}"
    dich = WORKTREE_DIR / f"{r['id']}-{_sid_ngan(sid)}"
    WORKTREE_DIR.mkdir(parents=True, exist_ok=True)
    _git(["worktree", "add", "-b", ten_nhanh, str(dich), goc], r["duong_dan"])
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
    r = get_repo(rb.get("repo") or "")
    if not r:
        raise LoiCoding("Phiên này chưa gắn repo nào.")
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
    vì đây là cảnh có thật ở một repo vừa `git init`.
    """
    cwd = cwd_cua_phien(sid)
    if not cwd:
        raise LoiCoding("Phiên này chưa gắn repo nào.")
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

    Giới hạn đó không phải hình thức: nhận tag bất kỳ thì một cú bấm nhầm kéo cả repo về một
    mốc của phiên khác, và `--hard` thì không hỏi lại.
    """
    tag = str(tag or "").strip()
    cwd = cwd_cua_phien(sid)
    if not cwd:
        raise LoiCoding("Phiên này chưa gắn repo nào.")
    if tag not in {x.get("tag") for x in danh_sach_diem_hoi(sid)}:
        raise LoiCoding("Điểm hồi đó không phải của phiên này.")
    _git(["reset", "--hard", tag], cwd)
    return {"ok": True, "tag": tag, "cwd": cwd}
