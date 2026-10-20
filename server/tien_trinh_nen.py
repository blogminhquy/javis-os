"""Tiến trình nền do engine bỏ lại: Javis nhận theo dõi, xong thì tự báo và tự làm tiếp (0.64.66).

Vì sao có file này
==================
Chủ repo báo 2026-09-27, kèm nguyên đoạn chat: nhờ Javis làm video, Javis trả lời "Đang render
nền, xong mình ghép tiếng và gửi video" rồi im. Video render xong lúc 14:57 mà phải tới 16:14,
khi chủ hỏi "xong video chưa", Javis mới biết.

Gốc rễ: engine có shell (Codex, Grok Build, Antigravity) tự bật lệnh dài chạy ngầm (`cmd &`,
`nohup cmd &`) rồi kết thúc lượt. Javis chỉ biết tự báo về cho việc Kanban, loop và nhắc hẹn.
Một tiến trình do engine tự bật thì Javis không hề biết nó tồn tại, nên không có gì đánh thức
khung chat khi nó xong. Còn lời hứa "xong mình gửi" là lời của model, không có cơ chế nào đứng
sau.

Cách làm
========
Engine CLI được chạy với `start_new_session=True`, nên mọi tiến trình con của nó, kể cả con
chạy ngầm bằng `&` hay `nohup`, nằm chung NHÓM tiến trình có mã bằng pid của engine. Engine
thoát rồi mà nhóm đó còn sống nghĩa là engine đã bỏ lại việc chạy ngầm. Không cần đoán qua lời
model, không cần model nhớ gọi tool nào: đây là sự thật đọc từ hệ điều hành.

  1. Engine ghi pid của mình theo tag lượt (`ghi_nhom`).
  2. Hết lượt, `nhan_nuoi_theo_tag` xem nhóm nào còn sống và nhận theo dõi.
  3. Một vòng lặp nền (`_vong_theo_doi`) hỏi hệ điều hành mỗi vài giây; nhóm chết hết là việc
     xong. Gọi `_KHI_XONG` do main đặt: báo về đúng khung chat + hòm thư + thông báo đẩy, và nếu
     cần thì mở một lượt nối tiếp trong cùng phiên để làm nốt (ghép tiếng, kiểm tra, gửi file).

Lượt nối tiếp chạy khi: model đã dặn rõ bằng tool `javis_job` op=then, HOẶC câu trả lời của
lượt vừa rồi có hứa "xong em làm tiếp/gửi" (bộ bắt lời hứa của background_status). Nhờ vậy lời
hứa của model thành sự thật, thay vì chỉ bị dán nhãn là hứa suông.

Giới hạn có chủ ý
=================
- Chỉ POSIX. Windows không có nhóm tiến trình kiểu này; ở đó mọi hàm là no-op an toàn.
- Tiến trình tự `setsid` thoát khỏi nhóm thì không theo dõi được. Hiếm với lệnh render/build.
- Không biết mã thoát của tiến trình nhận nuôi (nó không phải con của máy chủ). Thay vào đó
  liệt kê file mới sinh trong thư mục làm việc, là thứ người dùng thật sự cần thấy.
- Theo dõi tối đa `TRAN_THEO_DOI` giây. Quá đó thì báo "vẫn chạy, ngừng theo dõi" chứ không
  treo mãi (một dev server bị bỏ lại sẽ không bao giờ tự thoát).
- Lượt nối tiếp có trần độ sâu `TRAN_NOI_TIEP`: lượt nối tiếp lại bỏ việc nền mới là bình thường
  (render xong thì ghép tiếng), nhưng không được thành vòng lặp vô tận.

Module KHÔNG import main hay FastAPI: chỉ os/asyncio, để test được bằng tiến trình thật.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

try:
    import config as _cfg
    _STATE_DIR = Path(_cfg.STATE_DIR)
except Exception:          # chạy lẻ trong test
    _STATE_DIR = Path(os.getenv("JAVIS_STATE_DIR", str(Path(__file__).parent)))

POSIX = os.name != "nt"

# Nhịp hỏi hệ điều hành. Vài giây là đủ: người dùng chờ phút, không chờ mili giây.
NHIP_GIAY = 3.0
# Theo dõi tối đa bao lâu cho một việc (render dài nhất thường vài chục phút).
TRAN_THEO_DOI = 6 * 3600
# Độ sâu tối đa của chuỗi lượt nối tiếp.
TRAN_NOI_TIEP = 3
# Lời dặn "khi xong thì làm gì" đặt trong lượt mà hết lượt không có việc nào để gắn thì bỏ.
TUOI_LOI_DAN = 3600
# Số file mới liệt kê trong báo cáo.
TRAN_FILE_MOI = 6

_FILE = _STATE_DIR / "tien_trinh_nen.json"
_KHOA = threading.Lock()

_NHOM_THEO_TAG: Dict[str, List[int]] = {}      # tag lượt -> pid engine (= mã nhóm)
_VIEC: Dict[str, dict] = {}                     # mã việc -> bản ghi
_LOI_DAN: Dict[str, dict] = {}                  # chat_id -> {"text", "ts"} (javis_job op=then)
_KHI_XONG: Optional[Callable[[dict], Any]] = None
_VONG: Optional[asyncio.Task] = None


# ---------------------------------------------------------------------------------------
# Hệ điều hành
# ---------------------------------------------------------------------------------------
def nhom_con_song(pgid: int) -> bool:
    """Còn ÍT NHẤT MỘT tiến trình ĐANG CHẠY trong nhóm không. Tín hiệu 0 không gửi gì, chỉ hỏi.

    Tiến trình đã chết mà chưa ai dọn (zombie, trạng thái Z) vẫn làm killpg(0) thành công. Máy
    thật có tiến trình số 1 dọn chúng (tini trong Docker, systemd, launchd), nhưng một container
    chạy thẳng uvicorn làm PID 1 thì không: khi đó việc đã xong mà Javis tưởng còn chạy mãi. Nên
    có /proc thì hỏi thêm trạng thái từng thành viên, chỉ tính người còn sống thật.
    """
    if not POSIX or not pgid:
        return False
    try:
        os.killpg(int(pgid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass                 # có tiến trình, chỉ là không phải của mình để gửi tín hiệu
    except Exception:
        return False
    if not Path("/proc").is_dir():
        return True
    tv = _thanh_vien(pgid)
    return (not tv) or any(m.get("state") != "Z" for m in tv)


def _thanh_vien(pgid: int) -> List[dict]:
    """Các tiến trình còn sống của nhóm: pid, lệnh, thư mục làm việc. Best-effort.

    Đọc /proc khi có (Linux, kể cả container slim không có `ps`), không có thì hỏi `ps`
    (macOS). Hỏng cả hai thì trả rỗng: mô tả là để đọc cho dễ, không phải điều kiện theo dõi.
    """
    out: List[dict] = []
    proc = Path("/proc")
    if proc.is_dir():
        for d in proc.iterdir():
            if not d.name.isdigit():
                continue
            try:
                stat = (d / "stat").read_text()
                # "pid (comm) state ppid pgrp ..." - comm có thể chứa dấu cách và ngoặc.
                sau = stat[stat.rindex(")") + 2:].split()
                if int(sau[2]) != int(pgid):
                    continue
                cmd = (d / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace").strip()
                # Tiến trình vừa fork chưa kịp exec thì cmdline rỗng: lấy tên trong ngoặc của stat.
                if not cmd:
                    cmd = stat[stat.index("(") + 1:stat.rindex(")")]
                try:
                    cwd = os.readlink(str(d / "cwd"))
                except Exception:
                    cwd = ""
                out.append({"pid": int(d.name), "cmd": cmd, "cwd": cwd, "state": sau[0],
                            "ppid": int(sau[1])})
            except Exception:
                continue
        return out
    try:
        r = subprocess.run(["ps", "-A", "-o", "pid=,pgid=,command="], capture_output=True,
                           text=True, timeout=5,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for dong in r.stdout.splitlines():
            parts = dong.split(None, 2)
            if len(parts) >= 2 and parts[1].isdigit() and int(parts[1]) == int(pgid):
                out.append({"pid": int(parts[0]), "cmd": parts[2] if len(parts) > 2 else "", "cwd": ""})
    except Exception:
        pass
    return out


_VO_VI = re.compile(r"^(/\S*/)?(sh|bash|zsh|dash|nohup|env|timeout|sleep)$")


def mo_ta_lenh(members: List[dict]) -> str:
    """Một dòng người đọc hiểu được: lệnh "thật" nhất của nhóm, bỏ qua lớp vỏ sh/nohup."""
    tot = ""
    for m in members:
        cmd = str(m.get("cmd") or "").strip()
        if not cmd:
            continue
        dau = cmd.split()[0]
        if not tot or (_VO_VI.match(tot.split()[0]) and not _VO_VI.match(dau)):
            tot = cmd
    tot = re.sub(r"\s+", " ", tot)
    return (tot[:157] + "...") if len(tot) > 160 else tot


def file_moi(thu_muc: str, tu_luc: float, tran: int = TRAN_FILE_MOI) -> List[str]:
    """File được ghi SAU `tu_luc` trong thư mục làm việc (sâu 2 tầng), mới nhất trước.

    Bỏ file ẩn, thư mục ẩn và file tạm hay gặp của trình render. Đây là thứ người dùng cần:
    "video ra ở đâu", không phải mã thoát.
    """
    goc = Path(str(thu_muc or ""))
    if not thu_muc or not goc.is_dir():
        return []
    ds = []
    try:
        for p in list(goc.iterdir()) + [q for d in goc.iterdir() if d.is_dir() and not d.name.startswith(".")
                                        for q in d.iterdir()]:
            if p.name.startswith(".") or not p.is_file():
                continue
            if re.search(r"\.(tmp|part|lock|log)$", p.name, re.I):
                continue
            try:
                mt = p.stat().st_mtime
            except Exception:
                continue
            if mt >= tu_luc - 1:
                ds.append((mt, str(p)))
    except Exception:
        return []
    ds.sort(reverse=True)
    return [x[1] for x in ds[:tran]]


# ---------------------------------------------------------------------------------------
# Sổ
# ---------------------------------------------------------------------------------------
def _luu() -> None:
    try:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        tam = _FILE.with_suffix(".tmp")
        tam.write_text(json.dumps(list(_VIEC.values()), ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tam, _FILE)
    except Exception:
        pass


def _nap() -> None:
    try:
        ds = json.loads(_FILE.read_text(encoding="utf-8"))
    except Exception:
        return
    for v in ds if isinstance(ds, list) else []:
        if isinstance(v, dict) and v.get("id"):
            _VIEC[str(v["id"])] = v


def ghi_nhom(tag: str, pid: int) -> None:
    """Engine CLI vừa chạy: nhớ pid (cũng là mã nhóm) theo tag của lượt."""
    if not POSIX or not tag or not pid:
        return
    with _KHOA:
        ds = _NHOM_THEO_TAG.setdefault(str(tag), [])
        if int(pid) not in ds:
            ds.append(int(pid))
        # Tag của việc Kanban, quy trình... không bao giờ đi qua bước nhận nuôi của khung chat.
        # Không có trần thì sổ phình mãi theo thời gian chạy máy chủ.
        while len(_NHOM_THEO_TAG) > 200:
            _NHOM_THEO_TAG.pop(next(iter(_NHOM_THEO_TAG)))


def dat_loi_dan(chat_id: str, text: str) -> None:
    """Model dặn "khi việc nền của lượt này xong thì làm tiếp X" (tool javis_job op=then)."""
    cid = str(chat_id or "").strip()
    t = str(text or "").strip()
    if not cid or not t:
        return
    with _KHOA:
        _LOI_DAN[cid] = {"text": t[:2000], "ts": time.time()}


def _lay_loi_dan(chat_id: str) -> str:
    with _KHOA:
        d = _LOI_DAN.pop(str(chat_id or ""), None)
    if not d or time.time() - float(d.get("ts") or 0) > TUOI_LOI_DAN:
        return ""
    return str(d.get("text") or "")


def gan_loi_dan_cho_viec_dang_chay(chat_id: str, text: str) -> Optional[dict]:
    """Model dặn "khi xong thì..." cho việc ĐÃ đang theo dõi (lượt sau mới nhớ ra). Gắn vào việc
    mới nhất còn chạy của khung chat này; không có thì trả None để người gọi giữ làm lời dặn."""
    cid = str(chat_id or "")
    with _KHOA:
        ds = [v for v in _VIEC.values() if v.get("chat_id") == cid and v.get("trang_thai") == "run"]
        if not ds:
            return None
        v = max(ds, key=lambda x: float(x.get("bat_dau") or 0))
        v["sau_khi_xong"] = str(text or "")[:2000]
        v["noi_tiep"] = True
    _luu()
    return dict(v)


def nhan_nuoi_theo_tag(tag: str, brain_root: str, chat_id: str, *, hua: bool = False,
                       do_sau: int = 0) -> List[dict]:
    """Hết lượt: nhóm tiến trình nào của engine còn sống thì nhận theo dõi.

    `hua` = câu trả lời của lượt có hứa "xong em làm tiếp/gửi". Khi đó xong việc nền là mở
    lượt nối tiếp dù model không dặn gì, để lời hứa thành thật.
    Trả về các bản ghi vừa nhận (rỗng = không có gì chạy ngầm). Lời dặn đang chờ của khung chat
    luôn được lấy ra khỏi hàng: không có việc thì nó không còn nghĩa gì.
    """
    with _KHOA:
        pids = _NHOM_THEO_TAG.pop(str(tag or ""), [])
    loi_dan = _lay_loi_dan(chat_id)
    moi: List[dict] = []
    if not POSIX:
        return moi
    for pgid in pids:
        if not nhom_con_song(pgid):
            continue
        tv = _thanh_vien(pgid)
        if la_phu_engine(tv):
            continue
        if not mo_ta_lenh(tv) or all(_VO_VI.match(str(m.get("cmd") or "x").split()[0]) for m in tv):
            time.sleep(0.15)          # vừa fork chưa kịp exec: đợi một nhịp ngắn rồi đọc lại
            tv = _thanh_vien(pgid) or tv
        cwd = next((m["cwd"] for m in tv if m.get("cwd")), "") or str(brain_root or "")
        v = {
            "id": "j" + uuid.uuid4().hex[:8],
            "pgid": int(pgid),
            "mo_ta": mo_ta_lenh(tv) or "tiến trình nền",
            "cwd": cwd,
            "brain_root": str(brain_root or ""),
            "chat_id": str(chat_id or ""),
            "bat_dau": time.time(),
            "trang_thai": "run",
            "sau_khi_xong": loi_dan,
            "noi_tiep": bool(loi_dan) or bool(hua),
            "do_sau": int(do_sau or 0),
        }
        moi.append(v)
    if moi:
        with _KHOA:
            for v in moi:
                _VIEC[v["id"]] = v
        _luu()
        _dam_bao_vong()
    return [dict(v) for v in moi]


def theo_doi_nhom(pgid: int, mo_ta: str, cwd: str, brain_root: str, chat_id: str) -> str:
    """Nhận theo dõi NGAY một nhóm tiến trình Javis tự bật (terminal của engine API, 0.256.0).

    Khác `nhan_nuoi_theo_tag`: không cần đợi hết lượt rồi dò nhóm còn sống, vì chính Javis bật
    tiến trình và biết chắc mã nhóm. Trả mã việc (rỗng nếu không theo dõi được).
    """
    if not POSIX or not pgid or not chat_id:
        return ""
    v = {
        "id": "j" + uuid.uuid4().hex[:8],
        "pgid": int(pgid),
        "mo_ta": str(mo_ta or "tiến trình nền")[:200],
        "cwd": str(cwd or ""),
        "brain_root": str(brain_root or ""),
        "chat_id": str(chat_id or ""),
        "bat_dau": time.time(),
        "trang_thai": "run",
        "sau_khi_xong": _lay_loi_dan(chat_id),
        "noi_tiep": False,
        "do_sau": 0,
    }
    v["noi_tiep"] = bool(v["sau_khi_xong"])
    with _KHOA:
        _VIEC[v["id"]] = v
    _luu()
    _dam_bao_vong()
    return v["id"]


def ngung_theo_doi(job_id: str) -> None:
    """Bỏ một việc khỏi sổ, KHÔNG báo gì. Dùng khi chính model vừa dừng tiến trình đó: báo lại
    "đã dừng việc chạy nền" cho thứ model vừa tự tay dừng là tin nhắn thừa."""
    with _KHOA:
        _VIEC.pop(str(job_id or ""), None)
    _luu()


# Tiến trình phụ của chính engine (máy chủ MCP chạy stdio) có khi nán lại một nhịp sau khi
# engine thoát. Đó không phải "việc chạy nền" của người dùng: nhận nuôi là báo nhầm một cái
# "việc đã xong sau 3 giây: node mcp-server...". Nhóm chỉ gồm những tiến trình kiểu này thì bỏ.
_PHU_ENGINE = re.compile(r"(\bmcp\b|mcp-server|modelcontextprotocol|mcp_hub|codex mcp)", re.I)


def la_phu_engine(tv: List[dict]) -> bool:
    """Nhóm là tiến trình phụ của engine: mọi tiến trình GỐC (cha không nằm trong nhóm, tức là
    đứa bị bỏ lại khi engine thoát) đều là máy chủ MCP. Con cháu của chúng thì tên gì cũng được."""
    song = [m for m in tv if m.get("state") != "Z"]
    if not song:
        return False
    pids = {m.get("pid") for m in song}
    goc = [m for m in song if m.get("ppid") not in pids]
    return bool(goc) and all(_PHU_ENGINE.search(str(m.get("cmd") or "")) for m in goc)


def co_nhom_song(tag: str) -> bool:
    """Tag này còn nhóm tiến trình nào sống không (KHÔNG lấy ra khỏi sổ). Để người gọi quyết
    định có cần đợi một nhịp ân hạn trước khi nhận nuôi hay không."""
    with _KHOA:
        pids = list(_NHOM_THEO_TAG.get(str(tag or ""), []))
    return any(nhom_con_song(p) for p in pids)


def bo_tag(tag: str) -> None:
    """Lượt không đi tới bước nhận nuôi (lỗi, bị dừng): bỏ ghi nhớ để sổ không phình."""
    with _KHOA:
        _NHOM_THEO_TAG.pop(str(tag or ""), None)


def dang_chay(chat_id: str = "", brain_root: str = "") -> List[dict]:
    with _KHOA:
        ds = [dict(v) for v in _VIEC.values() if v.get("trang_thai") == "run"]
    if chat_id:
        ds = [v for v in ds if v.get("chat_id") == chat_id]
    if brain_root:
        ds = [v for v in ds if v.get("brain_root") == brain_root]
    return sorted(ds, key=lambda v: float(v.get("bat_dau") or 0))


def gan_day(chat_id: str = "", tran: int = 10) -> List[dict]:
    with _KHOA:
        ds = [dict(v) for v in _VIEC.values()]
    if chat_id:
        ds = [v for v in ds if v.get("chat_id") == chat_id]
    return sorted(ds, key=lambda v: -float(v.get("bat_dau") or 0))[:tran]


def huy(job_id: str) -> Optional[dict]:
    """Dừng một việc: TERM cả nhóm. Vòng theo dõi sẽ thấy nhóm chết và báo như thường."""
    with _KHOA:
        v = _VIEC.get(str(job_id or ""))
        if not v or v.get("trang_thai") != "run":
            return None
        v["huy"] = True
    try:
        os.killpg(int(v["pgid"]), signal.SIGTERM)
    except Exception:
        pass
    _luu()
    return dict(v)


def thoi_luong(giay: float) -> str:
    g = max(0, int(giay))
    if g < 60:
        return f"{g} giây"
    if g < 3600:
        return f"{g // 60} phút" + (f" {g % 60} giây" if g % 60 and g < 600 else "")
    return f"{g // 3600} giờ {(g % 3600) // 60} phút"


# ---------------------------------------------------------------------------------------
# Vòng theo dõi
# ---------------------------------------------------------------------------------------
def dat_khi_xong(cb: Callable[[dict], Any]) -> None:
    global _KHI_XONG
    _KHI_XONG = cb


def kiem_mot_luot(now: float = 0.0) -> List[dict]:
    """Một nhịp của vòng theo dõi, tách ra để test gọi thẳng. Trả các việc vừa KẾT THÚC."""
    moc = float(now) or time.time()
    xong: List[dict] = []
    with _KHOA:
        chay = [v for v in _VIEC.values() if v.get("trang_thai") == "run"]
    for v in chay:
        if nhom_con_song(v.get("pgid") or 0):
            # Lúc nhận nuôi, lệnh ngầm có khi mới fork xong (chỉ thấy vỏ "sh"). Nhịp sau đã exec
            # thành lệnh thật: cập nhật mô tả và thư mục làm việc cho báo cáo cuối dễ đọc.
            if v.get("mo_ta") in ("", "tiến trình nền") or _VO_VI.match(str(v.get("mo_ta") or "").split(" ")[0]):
                tv = _thanh_vien(v.get("pgid") or 0)
                moi = mo_ta_lenh(tv)
                if moi and moi != v.get("mo_ta"):
                    v["mo_ta"] = moi
                    cwd = next((m["cwd"] for m in tv if m.get("cwd")), "")
                    if cwd:
                        v["cwd"] = cwd
            if moc - float(v.get("bat_dau") or moc) > TRAN_THEO_DOI:
                v["trang_thai"] = "bo_theo_doi"
                v["ket_thuc"] = moc
                xong.append(v)
            continue
        v["trang_thai"] = "huy" if v.get("huy") else "xong"
        v["ket_thuc"] = moc
        v["file_moi"] = file_moi(v.get("cwd") or v.get("brain_root") or "", float(v.get("bat_dau") or moc))
        xong.append(v)
    if xong:
        _luu()
    return [dict(v) for v in xong]


async def _goi_khi_xong(v: dict) -> None:
    cb = _KHI_XONG
    if cb is None:
        return
    try:
        r = cb(v)
        if asyncio.iscoroutine(r):
            await r
    except Exception as e:
        print(f"[tien trinh nen] báo xong lỗi: {type(e).__name__}: {e}")


async def _vong_theo_doi() -> None:
    while True:
        try:
            for v in kiem_mot_luot():
                await _goi_khi_xong(v)
        except Exception as e:
            print(f"[tien trinh nen] vòng theo dõi lỗi: {type(e).__name__}: {e}")
        if not dang_chay():
            return          # hết việc thì nghỉ; việc mới sẽ đánh thức lại
        await asyncio.sleep(NHIP_GIAY)


def _dam_bao_vong() -> None:
    global _VONG
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _VONG is None or _VONG.done():
        _VONG = loop.create_task(_vong_theo_doi())


def khoi_dong() -> None:
    """Máy chủ vừa bật: nạp sổ cũ. Việc còn "run" mà nhóm vẫn sống thì theo dõi tiếp (engine
    chạy với session riêng nên việc nền sống sót qua lần khởi động lại máy chủ). Nhóm đã chết
    thì vòng theo dõi sẽ báo "xong" ở nhịp đầu tiên, kèm file mới như thường."""
    _nap()
    if dang_chay():
        _dam_bao_vong()
