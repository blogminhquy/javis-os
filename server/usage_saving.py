"""
usage_saving.py - Tiet kiem token DO DUOC theo doi chung nguoc, moc su kien, du bao, ngan sach.

VI SAO MODULE NAY TON TAI
=========================
Cach do cu (`main._do_duoc_tiet_kiem`) so trung binh token cua nhung luot di duong CU voi
nhung luot di duong MOI trong cung 24 gio. Cach do dung, nhung no chi co so khi ca hai duong
cung chay - tuc la chi trong vai gio chuyen giao ngay sau khi nguoi dung doi muc. Bat che do
tiet kiem roi de yen mot ngay la moi luot deu di duong moi, khong con luot nao lam doi chung,
va ca khoi "da tiet kiem bao nhieu" BIEN MAT khoi trang. Che do cang chay tot thi con so cang
khong bao gio hien - dung cai nguoc lai voi thu nguoi dung can.

Cach o day khong can luot doi chung nao. Phan tiet kiem cua che do nay nam o CHI PHI CO DINH
moi luot: bo luat, bo nho, danh sach skill, mo ta cong cu. Phan con lai cua mot luot (cau hoi,
lich su hoi thoai, noi dung file) giong het nhau du bat muc nao. Nen:

    tiet kiem = (chi phi co dinh o muc Tat - chi phi co dinh o muc dang chay) x so luot

Ca hai chi phi co dinh deu do duoc bang cach dung THAT prompt cua brain dang dung (xem
`main._uoc_tinh_tiet_kiem`), va so luot thi dem duoc tu log. Cong thuc chay cho MOI ky - hom
nay, thang truoc, ca nam - va cong don duoc.

Doi lai, phai goi dung ten no: day la mot PHEP DOI CHUNG ("neu luc do chay muc Tat thi da ton
them chung nay"), khong phai mot hoa don. Giao dien noi dung nhu vay.

MOC SU KIEN
===========
Muc tiet kiem doi giua ky thi khong the lay muc HIEN TAI ap cho ca ky. `usage-marks.jsonl`
ghi lai moi lan doi muc / doi model, nen tinh duoc tung ngay chay muc nao. Cung file do ve
thanh gach moc tren bieu do theo ngay - nhin phat thay cot tut xuong dung hom bat tiet kiem.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime, timedelta, timezone

from config import STATE_DIR

_TZ = timezone(timedelta(hours=7))
MOC_PATH = STATE_DIR / "usage-marks.jsonl"
_LOCK = threading.Lock()

# Giu bao nhieu moc. Moc chi la mot dong ~120 byte, nhung file khong prune thi sau vai nam
# doc lai ca file de ve mot bieu do 30 ngay la lang phi. 2000 moc du cho nhieu nam doi muc.
_GIU_MOC = 2000

LOAI_MOC = ("muc", "model", "ngan_sach")


def ghi_moc(loai: str, den: str, tu: str = "", nhan: str = "", now: datetime = None) -> dict:
    """Ghi mot moc su kien. Best-effort: hong thi nuot, KHONG duoc lam vo thao tac gay ra no.

    `loai`: 'muc' (doi che do tiet kiem) | 'model' (doi bo nao) | 'ngan_sach' (doi tran tien).
    `tu`/`den`: gia tri truoc va sau. `nhan`: chu de hien tren bieu do.
    """
    now = now or datetime.now(_TZ)
    moc = {"ts": int(now.timestamp()), "day": now.astimezone(_TZ).strftime("%Y-%m-%d"),
           "loai": str(loai or "")[:20], "tu": str(tu or "")[:80],
           "den": str(den or "")[:80], "nhan": str(nhan or "")[:120]}
    try:
        with _LOCK:
            with open(MOC_PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(moc, ensure_ascii=False) + "\n")
    except Exception:   # noqa: BLE001 - nhat ky phu, khong duoc chan viec chinh
        pass
    return moc


def doc_moc(tu_ngay: str = "", den_ngay: str = "", loai: str = "") -> list:
    """Moc trong khoang ngay (ISO 'YYYY-MM-DD', rong = khong chan). Cu -> moi."""
    out = []
    try:
        if not MOC_PATH.exists():
            return []
        with open(MOC_PATH, "r", encoding="utf-8", errors="replace") as fh:
            dong = fh.readlines()
    except OSError:
        return []
    for ln in dong[-_GIU_MOC:]:
        ln = ln.strip()
        if not ln:
            continue
        try:
            m = json.loads(ln)
        except Exception:   # noqa: BLE001 - dong rac giua file khong duoc giet ca nhat ky
            continue
        d = str(m.get("day") or "")
        if not d:
            continue
        if tu_ngay and d < tu_ngay:
            continue
        if den_ngay and d > den_ngay:
            continue
        if loai and m.get("loai") != loai:
            continue
        out.append(m)
    out.sort(key=lambda x: x.get("ts") or 0)
    return out


def muc_theo_ngay(ngay: list, muc_hien_tai: str) -> dict:
    """{ngay: muc_chay_hom_do} suy nguoc tu nhat ky moc.

    Cach suy: di TU HIEN TAI VE QUA KHU. Muc bay gio ap cho moi ngay tu moc doi muc gan nhat
    tro di; truoc moc do la gia tri `tu` cua chinh moc do; cu the lui dan.

    Chua co moc nao (may vua nang cap, nhat ky con rong) -> ap muc hien tai cho ca day. Do la
    gia dinh, va ham `tiet_kiem` bao ra ngoai bang co `suy_doan` de giao dien noi that.
    """
    ngay = sorted(set(str(d) for d in (ngay or []) if d))
    if not ngay:
        return {}
    moc = [m for m in doc_moc(loai="muc") if m.get("day")]
    out = {}
    hien = str(muc_hien_tai or "off")
    # Duyet ngay tu MOI ve CU; gap moc nao co day > ngay dang xet thi truoc do la `tu` cua no.
    for d in reversed(ngay):
        while moc and str(moc[-1]["day"]) > d:
            m = moc.pop()
            hien = str(m.get("tu") or hien)
        out[d] = hien
    return out


def out_rong(goc: int = 0, so_luot: int = 0) -> dict:
    """Khoi tiet kiem RONG, dung khi khong do duoc. Giu du khoa de giao dien khong phai dem null."""
    return {"token": 0, "so_luot": so_luot, "moi_luot": 0, "phi_goc": goc, "phi_dang_chay": goc,
            "muc_chinh": "", "phan_tram": 0, "theo_ngay": [], "suy_doan": False,
            "du_du_lieu": False, "khong_do_duoc": False,
            "tien": {"usd": 0.0, "gia_1m_usd": 0.0}}


def tiet_kiem(theo_ngay: list, phi_moi_muc: dict, muc_hien_tai: str,
              gia_1m_usd: float = 3.0) -> dict:
    """Token tiet kiem duoc trong ky, bang doi chung voi che do Tat.

    `theo_ngay`: [{day, turns}] - lay thang tu `usage_index.summary()["timeseries"]`.
    `phi_moi_muc`: {muc_id: token_co_dinh_moi_luot} - tu `main._uoc_tinh_tiet_kiem`.

    Tra ve mot khoi noi duoc thanh cau: bao nhieu luot, moi luot re di bao nhieu, tong cong
    tranh duoc bao nhieu token, va quy ra tien khoang bao nhieu.
    """
    phi = {k: int(v or 0) for k, v in (phi_moi_muc or {}).items() if int(v or 0) > 0}
    goc = phi.get("off") or 0
    ngay = [str((r or {}).get("day") or "") for r in (theo_ngay or [])]
    ban_do = muc_theo_ngay(ngay, muc_hien_tai)
    co_moc = bool(doc_moc(loai="muc"))

    tong_token, tong_luot, chi_tiet = 0, 0, []
    dem_muc = {}
    for r in theo_ngay or []:
        d = str((r or {}).get("day") or "")
        luot = int((r or {}).get("turns") or 0)
        if not d or luot <= 0:
            continue
        m = ban_do.get(d, muc_hien_tai)
        chenh = max(0, goc - (phi.get(m, goc)))
        tok = chenh * luot
        tong_token += tok
        tong_luot += luot
        dem_muc[m] = dem_muc.get(m, 0) + luot
        chi_tiet.append({"day": d, "muc": m, "turns": luot, "token": tok})

    # `muc_chinh` = muc chiem nhieu luot nhat trong ky (de ke lai ky da qua), con `moi_luot`
    # va `phan_tram` bam vao muc DANG CHAY. Hai thu khac nhau va deu can: mot nguoi vua bat
    # tiet kiem hom qua co ky chu yeu la muc Tat, nhung cau ho hoi la "tu gio moi luot re di
    # bao nhieu" - lay muc chiem da so ma tra loi thi ra 0% ngay sau khi vua bat.
    muc_chinh = max(dem_muc, key=lambda k: dem_muc[k]) if dem_muc else str(muc_hien_tai or "off")
    nay = str(muc_hien_tai or "off")
    # `current_preset` tra ve "custom" khi nguoi dung tu chinh tay tung duong (endpoint
    # /runtime/canary). Luc do ta KHONG biet chi phi co dinh moi luot cua cau hinh do, nen moi
    # ngay ra chenh 0 va tong ra 0 token. Bao "du_du_lieu: True" kem so 0 la noi "che do tiet
    # kiem cua anh khong dang gi" - sai, va sai theo huong lam nguoi ta tat no di.
    if nay not in phi:
        return {**out_rong(goc, tong_luot), "muc_chinh": muc_chinh, "khong_do_duoc": True}
    usd = tong_token / 1_000_000.0 * float(gia_1m_usd or 0)
    return {
        "token": tong_token,
        "so_luot": tong_luot,
        "moi_luot": max(0, goc - phi.get(nay, goc)),
        "phi_goc": goc,
        "phi_dang_chay": phi.get(nay, goc),
        "muc_chinh": muc_chinh,
        "phan_tram": round((1 - phi.get(nay, goc) / goc) * 100) if goc else 0,
        "theo_ngay": chi_tiet,
        # Chua co moc nao thi ta dang GIA DINH ca ky chay cung mot muc. Noi ra, dung im.
        "suy_doan": not co_moc,
        "du_du_lieu": bool(goc and tong_luot),
        "khong_do_duoc": False,
        # Chi USD. Gia model deu niem yet bang USD, nen quy doi tiep sang mot don vi khac
        # bang mot ti gia go cung chi them mot cho de sai ma khong them thong tin nao.
        "tien": {"usd": round(usd, 4), "gia_1m_usd": float(gia_1m_usd or 0)},
    }


# ============================================================
# Du bao cuoi ky
# ============================================================
def du_bao(tokens: int, cost_est: float, tu_ngay: str, den_ngay: str,
           period: str = "this_month", today: date = None) -> dict:
    """Chieu muc dung hien tai toi HET ky (thang/tuan/nam), theo dung nhip da chay.

    Chi co nghia khi ky VAN DANG CHAY. Ky da dong (thang truoc, tuan truoc) thi khong du bao
    gi ca - so da chot roi, ve them mot con so "du bao" chi lam nguoi doc tuong no chua xong.
    """
    dang_chay = period in ("today", "this_week", "this_month", "this_year", "last_3_months")
    if not dang_chay:
        return {"co": False}
    try:
        cs = date.fromisoformat(tu_ngay)
        ce = date.fromisoformat(den_ngay)
    except (TypeError, ValueError):
        return {"co": False}
    d = today or datetime.now(_TZ).date()
    da_qua = (ce - cs).days + 1
    if period == "this_month":
        nxt = (ce.replace(day=28) + timedelta(days=4)).replace(day=1)
        het = nxt - timedelta(days=1)
    elif period == "this_week":
        het = cs + timedelta(days=6)
    elif period == "this_year":
        het = date(cs.year, 12, 31)
    else:
        return {"co": False}
    ca_ky = (het - cs).days + 1
    if da_qua <= 0 or ca_ky <= da_qua:
        return {"co": False}
    he_so = ca_ky / da_qua
    return {"co": True, "tokens": round(int(tokens or 0) * he_so),
            "cost": round(float(cost_est or 0) * he_so, 2),
            "het_ngay": het.isoformat(), "con_ngay": max(0, (het - d).days),
            "da_qua_ngay": da_qua, "ca_ky_ngay": ca_ky}


# ============================================================
# Ngan sach tien that
# ============================================================
NGUONG_CANH_BAO = 0.8      # cham 80% tran thi bat den vang


def ngan_sach(da_tieu_usd: float, tran_usd: float, du_bao_usd: float = 0.0) -> dict:
    """Trang thai ngan sach thang: {co, tran, da_tieu, con, ty_le, muc_do, du_bao_vuot}.

    `muc_do`: 'ok' | 'sap_het' (>=80%) | 'het' (>=100%). Giao dien to mau theo day, va
    `main` dung dung nguong nay de quyet dinh co nhac hay khong - mot nguong, mot cho.
    """
    tran = max(0.0, float(tran_usd or 0))
    da = max(0.0, float(da_tieu_usd or 0))
    if tran <= 0:
        return {"co": False, "da_tieu": round(da, 2)}
    ty_le = da / tran
    muc_do = "het" if ty_le >= 1.0 else ("sap_het" if ty_le >= NGUONG_CANH_BAO else "ok")
    return {"co": True, "tran": round(tran, 2), "da_tieu": round(da, 2),
            "con": round(max(0.0, tran - da), 2), "ty_le": round(ty_le, 4),
            "muc_do": muc_do,
            "du_bao_vuot": bool(du_bao_usd and float(du_bao_usd) > tran),
            "du_bao": round(float(du_bao_usd or 0), 2)}


# Trang thai PHANH, dat trong tien trinh. Vong lap nen tinh lai moi 10 phut roi ghi vao day;
# `aux_engine.read_spec()` chi doc mot bien nen khong ton them truy van nao tren duong nong.
#
# Vi sao la trang thai trong RAM chu khong phai co trong settings.json: phanh la HE QUA cua so
# lieu, khong phai lua chon cua nguoi dung. Ghi vao file thi may khoi dong lai giua thang se
# giu nguyen phanh cu cho toi luot tinh dau tien - hoac te hon, mot lan tinh sai bi dong bang
# vinh vien vao cau hinh. De trong RAM thi mac dinh la KHONG phanh, va lan tick dau tien
# (30 giay sau khi chay) tu dat lai cho dung.
_PHANH = {"bat": False, "ly_do": "", "ts": 0}


def dat_phanh(bat: bool, ly_do: str = "") -> None:
    _PHANH["bat"] = bool(bat)
    _PHANH["ly_do"] = str(ly_do or "")
    _PHANH["ts"] = int(datetime.now(_TZ).timestamp())


def dang_phanh() -> dict:
    """{'bat': bool, 'ly_do': str}. Viec nen doc cai nay de biet co phai ne tien khong."""
    return {"bat": bool(_PHANH["bat"]), "ly_do": _PHANH["ly_do"], "ts": _PHANH["ts"]}


def da_nhac_chua(khoa: str, now: datetime = None) -> bool:
    """Chong nhac lai cung mot canh bao ngan sach nhieu lan trong THANG.

    Dau nhac luu ngay trong chinh nhat ky moc (loai 'ngan_sach') de khong de them mot file
    trang thai nua. Tra True neu THANG NAY da nhac khoa do roi.
    """
    now = now or datetime.now(_TZ)
    thang = now.strftime("%Y-%m")
    for m in doc_moc(loai="ngan_sach"):
        if str(m.get("den") or "") == khoa and str(m.get("day") or "").startswith(thang):
            return True
    return False
