"""Mốc khôi phục TỰ ĐỘNG cho phiên Coding, và Hoàn tác an toàn (0.256.0).

Vì sao có file này
------------------
Từ 0.256.0 engine API có terminal thật và sửa file từng đoạn trong phiên Coding. Model sửa hỏng
là chuyện thường, và "điểm hồi" có sẵn (`coding_store.tao_diem_hoi`) không đỡ được: nó là một
tag git do NGƯỜI bấm tay, chỉ có ở thư mục là repo đã có commit, và kéo về bằng
`git reset --hard`, tức là xoá luôn những gì người dùng tự sửa sau mốc.

File này tạo mốc TỰ ĐỘNG, ngay trước thao tác thay đổi đầu tiên của mỗi lượt chat, và khôi phục
có chọn lọc. Thiết kế học từ `tools/checkpoint_manager.py` của Hermes Agent
(github.com/NousResearch/hermes-agent, MIT):

- Một kho git "bóng" riêng ở `STATE_DIR/checkpoints/store`, đọc ghi bằng GIT_DIR, GIT_WORK_TREE
  và GIT_INDEX_FILE riêng. KHÔNG chạm vào `.git`, index, stash hay nhánh của repo người dùng,
  và chạy được cả ở thư mục không phải repo.
- Mỗi mốc là một commit mồ côi giữ bằng một ref riêng, nên xoá mốc cũ chỉ là xoá ref.
- Hoàn tác "an toàn": chỉ trả lại file mà model đã đụng. File người dùng tự sửa SAU lần cuối
  model làm việc thì giữ nguyên và liệt kê ra. Cách phân biệt: sổ băm nội dung những file model
  ghi qua tool, cộng mốc thời gian lần cuối model hoạt động trong phiên (file đổi sau mốc đó là
  của người).

Lỗi ở đây không bao giờ được làm hỏng lượt chat: mọi hàm công khai nuốt lỗi và trả câu nói được.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import winproc
from config import STATE_DIR

GOC = STATE_DIR / "checkpoints"
KHO = GOC / "store"
SO = GOC / "so.json"

GIU_MOC = 20                       # mỗi thư mục làm việc
KHO_TOI_DA_MB = 500
FILE_TOI_DA_MB = 10
FILE_TOI_DA_SO = 50_000
GIT_TIMEOUT = 30

_BO_QUA = ("node_modules/", ".venv/", "venv/", "__pycache__/", "*.pyc", ".mypy_cache/",
           ".pytest_cache/", ".ruff_cache/", ".tox/", ".next/", ".nuxt/", ".cache/", "dist/",
           "build/", "target/", ".worktrees/", ".DS_Store")

_KHOA = threading.RLock()
# Lượt hiện tại của mỗi phiên, và lượt nào đã có mốc cho thư mục nào.
_LUOT: Dict[str, int] = {}
_DA_TAO: Dict[Tuple[str, str], int] = {}
# Sổ băm nội dung file do model ghi: {sid: {đường dẫn: sha256}}.
_SO_GHI: Dict[str, Dict[str, str]] = {}
# Lần cuối model làm gì đó thay đổi được file trong phiên (ghi, sửa, chạy lệnh).
_HOAT_DONG: Dict[str, float] = {}


class LoiMoc(Exception):
    pass


def _git_env(ws: str, index: Path) -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({
        "GIT_DIR": str(KHO), "GIT_WORK_TREE": str(ws), "GIT_INDEX_FILE": str(index),
        "GIT_AUTHOR_NAME": "Javis", "GIT_AUTHOR_EMAIL": "javis@localhost",
        "GIT_COMMITTER_NAME": "Javis", "GIT_COMMITTER_EMAIL": "javis@localhost",
        "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "LC_ALL": "C",
    })
    return env


def _git(args: List[str], ws: str, index: Path, inp: Optional[bytes] = None, bytes_out: bool = False):
    git = shutil.which("git")
    if not git:
        raise LoiMoc("máy không có git")
    r = subprocess.run([git, "-c", "core.autocrlf=false", "-c", "core.quotepath=false"] + args,
                       cwd=str(ws), env=_git_env(ws, index), input=inp, capture_output=True,
                       timeout=GIT_TIMEOUT, creationflags=winproc.no_window())
    if r.returncode != 0:
        raise LoiMoc((r.stderr or b"").decode("utf-8", "replace").strip()[:300] or f"git {args[0]} lỗi")
    return r.stdout if bytes_out else r.stdout.decode("utf-8", "replace")


def _ma_ws(ws: str) -> str:
    return hashlib.sha256(str(Path(ws).resolve()).encode("utf-8")).hexdigest()[:16]


def _index(ws: str, tam: bool = False) -> Path:
    d = GOC / "index"
    d.mkdir(parents=True, exist_ok=True)
    return d / (f"{_ma_ws(ws)}-{uuid.uuid4().hex[:6]}.tmp" if tam else _ma_ws(ws))


def _dam_bao_kho() -> None:
    if (KHO / "HEAD").is_file():
        return
    KHO.mkdir(parents=True, exist_ok=True)
    git = shutil.which("git")
    if not git:
        raise LoiMoc("máy không có git")
    subprocess.run([git, "init", "--bare", "-q", str(KHO)], capture_output=True, timeout=GIT_TIMEOUT,
                   creationflags=winproc.no_window())
    (KHO / "info").mkdir(exist_ok=True)
    (KHO / "info" / "exclude").write_text("\n".join(_BO_QUA) + "\n", encoding="utf-8")


def _nap_so() -> dict:
    try:
        return json.loads(SO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _luu_so(d: dict) -> None:
    GOC.mkdir(parents=True, exist_ok=True)
    tmp = SO.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, SO)


def _kho_mb() -> float:
    tong = 0
    for thu_muc, _con, files in os.walk(KHO):
        for f in files:
            try:
                tong += os.path.getsize(os.path.join(thu_muc, f))
            except OSError:
                pass
    return tong / 1_048_576


def _quet(ws: str) -> Tuple[bool, List[str], str]:
    """(được chụp không, file quá lớn cần bỏ, lý do nếu không được)."""
    p = Path(ws).resolve()
    if str(p) in ("/", str(Path.home().resolve())) or len(p.parts) <= 1:
        return False, [], "thư mục làm việc là gốc ổ đĩa hoặc thư mục home"
    lon, dem = [], 0
    bo = {x.rstrip("/") for x in _BO_QUA if x.endswith("/")} | {".git"}
    for thu_muc, con, files in os.walk(p):
        con[:] = [c for c in con if c not in bo]
        for f in files:
            dem += 1
            if dem > FILE_TOI_DA_SO:
                return False, [], f"thư mục có hơn {FILE_TOI_DA_SO:,} file"
            fp = os.path.join(thu_muc, f)
            try:
                if os.path.getsize(fp) > FILE_TOI_DA_MB * 1_048_576:
                    lon.append(os.path.relpath(fp, p).replace("\\", "/"))
            except OSError:
                pass
    return True, lon, ""


def _chup(ws: str, index: Path) -> str:
    """Ghi trạng thái hiện tại của `ws` thành một tree trong kho bóng. Trả mã tree."""
    ok, lon, ly_do = _quet(ws)
    if not ok:
        raise LoiMoc(ly_do)
    _git(["add", "-A", "--ignore-errors", "--", "."], ws, index)
    if lon:
        try:
            _git(["rm", "-q", "--cached", "--ignore-unmatch", "--"] + lon, ws, index)
        except LoiMoc:
            pass
    return _git(["write-tree"], ws, index).strip()


# ---------------------------------------------------------------------------------------
# Lượt và sổ hoạt động
# ---------------------------------------------------------------------------------------
def luot_moi(sid: str) -> None:
    """Một lượt chat mới bắt đầu trong phiên: lượt sau được tạo mốc mới."""
    if not sid:
        return
    with _KHOA:
        _LUOT[sid] = _LUOT.get(sid, 0) + 1


def ghi_nhan_hoat_dong(sid: str, path: Optional[Path] = None) -> None:
    """Model vừa thay đổi được file: ghi mốc thời gian, và băm file nếu biết file nào."""
    if not sid:
        return
    with _KHOA:
        _HOAT_DONG[sid] = time.time()
        if path is not None:
            try:
                h = hashlib.sha256(Path(path).read_bytes()).hexdigest()
                _SO_GHI.setdefault(sid, {})[str(Path(path).resolve())] = h
            except OSError:
                pass


def tao_neu_can(sid: str, ws: str, ly_do: str = "") -> str:
    """Tạo mốc cho `ws` nếu lượt này chưa có. Trả câu cảnh báo khi không tạo được, "" khi ổn.

    KHÔNG ném: lỗi tạo mốc chỉ là một cảnh báo, không chặn việc model đang làm.
    """
    if not sid or not ws:
        return ""
    with _KHOA:
        luot = _LUOT.get(sid, 0)
        key = (sid, str(Path(ws).resolve()))
        if _DA_TAO.get(key) == luot:
            return ""
        _DA_TAO[key] = luot
    try:
        tao(sid, ws, ly_do=ly_do, luot=luot)
        return ""
    except Exception as e:
        return f"(Không tạo được mốc khôi phục trước thao tác này: {e}. Hoàn tác sẽ không có mốc của lượt này.)"


def tao(sid: str, ws: str, ly_do: str = "", luot: int = 0) -> dict:
    """Chụp `ws` thành một mốc của phiên `sid`. Ném LoiMoc nếu không được."""
    ws = str(Path(ws).resolve())
    with _KHOA:
        _dam_bao_kho()
        if _kho_mb() > KHO_TOI_DA_MB:
            _don_bot(giu=5)
            if _kho_mb() > KHO_TOI_DA_MB:
                raise LoiMoc(f"kho mốc đã quá {KHO_TOI_DA_MB} MB")
        idx = _index(ws)
        tree = _chup(ws, idx)
        commit = _git(["commit-tree", tree, "-m", f"javis {sid} {ly_do}"[:200]], ws, idx).strip()
        mid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        ref = f"refs/javis/{_ma_ws(ws)}/{mid}"
        _git(["update-ref", ref, commit], ws, idx)
        rec = {"id": mid, "ws": ws, "ref": ref, "commit": commit, "luc": time.time(),
               "luot": luot, "ly_do": str(ly_do or "")[:120]}
        so = _nap_so()
        ds = list(so.get(sid) or [])
        ds.append(rec)
        # Giữ GIU_MOC mốc gần nhất cho mỗi thư mục của phiên; ref của mốc bị bỏ cũng xoá.
        cua_ws = [x for x in ds if x.get("ws") == ws]
        thua = cua_ws[:-GIU_MOC] if len(cua_ws) > GIU_MOC else []
        for x in thua:
            try:
                _git(["update-ref", "-d", x["ref"]], ws, idx)
            except LoiMoc:
                pass
        ds = [x for x in ds if x not in thua]
        so[sid] = ds
        _luu_so(so)
        return rec


def _don_bot(giu: int = 5) -> None:
    so = _nap_so()
    for sid, ds in list(so.items()):
        theo_ws: Dict[str, list] = {}
        for x in ds:
            theo_ws.setdefault(x.get("ws", ""), []).append(x)
        con = []
        for ws, xs in theo_ws.items():
            for x in xs[:-giu]:
                try:
                    _git(["update-ref", "-d", x["ref"]], ws, _index(ws))
                except Exception:
                    pass
            con += xs[-giu:]
        so[sid] = sorted(con, key=lambda x: x.get("luc", 0))
    _luu_so(so)
    git = shutil.which("git")
    if git:
        subprocess.run([git, "--git-dir", str(KHO), "gc", "--prune=now", "-q"], capture_output=True,
                       timeout=120, creationflags=winproc.no_window())


def danh_sach(sid: str) -> List[dict]:
    return list(reversed(_nap_so().get(str(sid)) or []))


def _tim(sid: str, mid: str) -> dict:
    for x in _nap_so().get(str(sid)) or []:
        if x.get("id") == mid:
            return x
    raise LoiMoc("không có mốc đó trong phiên này")


# ---------------------------------------------------------------------------------------
# Xem thay đổi và khôi phục
# ---------------------------------------------------------------------------------------
def thay_doi(sid: str, mid: str) -> dict:
    """Những file khác nhau giữa mốc và hiện tại: [{"trang_thai": A|M|D, "file": ...}]."""
    rec = _tim(sid, mid)
    ws = rec["ws"]
    if not Path(ws).is_dir():
        raise LoiMoc("thư mục làm việc của mốc này không còn trên đĩa")
    with _KHOA:
        tam = _index(ws, tam=True)
        try:
            tree_nay = _chup(ws, tam)
            out = _git(["diff-tree", "-r", "--no-renames", "--name-status", rec["commit"], tree_nay], ws, tam)
        finally:
            try:
                tam.unlink()
            except OSError:
                pass
    ds = []
    for dong in out.splitlines():
        if "\t" not in dong:
            continue
        st, f = dong.split("\t", 1)
        # Từ mốc tới hiện tại: A = file mới sinh sau mốc, D = file bị xoá sau mốc.
        ds.append({"trang_thai": st.strip()[:1], "file": f})
    return {"moc": rec, "file": ds, "tree_nay": tree_nay}


def diff_file(sid: str, mid: str, rel: str, tran: int = 60_000) -> str:
    rec = _tim(sid, mid)
    ws = rec["ws"]
    p = (Path(ws) / rel).resolve()
    if Path(ws).resolve() not in p.parents:
        raise LoiMoc("đường dẫn nằm ngoài thư mục làm việc")
    try:
        cu = _git(["show", f"{rec['commit']}:{rel}"], ws, _index(ws), bytes_out=True).decode("utf-8", "replace")
    except LoiMoc:
        cu = ""
    try:
        moi = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
    except OSError:
        moi = ""
    import difflib
    d = "".join(difflib.unified_diff(cu.splitlines(True), moi.splitlines(True),
                                     fromfile=f"mốc/{rel}", tofile=f"hiện tại/{rel}", n=3))
    return d[:tran] + (f"\n… [diff dài {len(d):,} ký tự, đã cắt]" if len(d) > tran else "")


def _cua_model(sid: str, p: Path) -> bool:
    """File này có phải do model đụng tới lần cuối không (để Hoàn tác an toàn trả lại)."""
    with _KHOA:
        h = (_SO_GHI.get(sid) or {}).get(str(p.resolve()))
        cuoi = _HOAT_DONG.get(sid, 0.0)
    if h is not None and p.is_file():
        try:
            if hashlib.sha256(p.read_bytes()).hexdigest() == h:
                return True
        except OSError:
            return False
    if not p.exists():
        return True
    try:
        # Đổi lần cuối KHÔNG sau lần cuối model hoạt động (+2 giây cho độ phân giải mtime).
        return p.stat().st_mtime <= cuoi + 2.0
    except OSError:
        return False


def khoi_phuc(sid: str, mid: str, an_toan: bool = True, chi_file: str = "") -> dict:
    """Trả thư mục làm việc về mốc `mid`.

    an_toan=True: chỉ trả lại file model đã đụng; file người dùng sửa tay sau đó giữ nguyên.
    chi_file: chỉ khôi phục đúng một file (luôn làm, coi như người dùng đã chọn có chủ ý).
    Trước khi khôi phục, chụp một mốc của trạng thái hiện tại để hoàn tác được cả lần hoàn tác.
    """
    rec = _tim(sid, mid)
    ws = rec["ws"]
    td = thay_doi(sid, mid)
    try:
        truoc = tao(sid, ws, ly_do="trước khi hoàn tác")
    except LoiMoc:
        truoc = None
    tra, giu = [], []
    goc = Path(ws).resolve()
    for x in td["file"]:
        rel = x["file"]
        if chi_file and rel != chi_file:
            continue
        p = (goc / rel).resolve()
        if goc not in p.parents:
            continue
        if an_toan and not chi_file and not _cua_model(sid, p):
            giu.append(rel)
            continue
        try:
            if x["trang_thai"] == "A":
                if p.is_file():
                    p.unlink()
            else:
                data = _git(["show", f"{rec['commit']}:{rel}"], ws, _index(ws), bytes_out=True)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            tra.append(rel)
        except (LoiMoc, OSError) as e:
            giu.append(f"{rel} (lỗi: {e})")
    with _KHOA:
        so_ghi = _SO_GHI.get(sid) or {}
        for rel in tra:
            so_ghi.pop(str((goc / rel).resolve()), None)
    return {"ok": True, "da_tra": tra, "giu_nguyen": giu, "moc_truoc_khi_hoan_tac": (truoc or {}).get("id", "")}


def don_phien(sid: str) -> None:
    """Phiên bị xoá: bỏ mọi mốc của nó."""
    with _KHOA:
        so = _nap_so()
        for x in so.pop(str(sid), []) or []:
            try:
                _git(["update-ref", "-d", x["ref"]], x.get("ws") or str(GOC), _index(x.get("ws") or str(GOC)))
            except Exception:
                pass
        _luu_so(so)
        _SO_GHI.pop(sid, None)
        _HOAT_DONG.pop(sid, None)
        _LUOT.pop(sid, None)
