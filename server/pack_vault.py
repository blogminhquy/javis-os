"""Gói mang theo agent, workflow và skill: ghi vào brain người dùng, và biết đường lùi.

Vì sao ba thứ này KHÁC connector và plugin
------------------------------------------
Connector và plugin của gói nằm TRONG thư mục gói. Gỡ là `rmtree`, hết chuyện, không ai mất gì.

Agent, workflow và skill thì sống trong BRAIN của người dùng, và brain là nơi họ **sửa**. Cài
một skill xong người ta chỉnh lại cho hợp việc của mình, rồi bản mới ra, rồi họ gỡ gói. Mỗi
bước đều có một câu hỏi không có đáp án hiển nhiên, và trả lời sai là **xoá mất công của người
dùng** - loại lỗi tệ nhất mà một trình cài có thể gây ra.

Luật ở đây, đúng ba câu:

1. Cài thì KHÔNG BAO GIỜ ghi đè một tệp đã có mà gói không phải người đặt vào đó.
2. Cập nhật chỉ ghi đè khi tệp còn Y NGUYÊN như lúc gói đặt vào (đối chiếu hash).
3. Gỡ chỉ xoá tệp còn y nguyên. Người dùng đã sửa thì GIỮ LẠI và nói ra, chứ không xoá.

Không nghĩ ra cơ chế mới
------------------------
`system_sync` đã giải đúng bài này cho skill hệ thống: một manifest ghi hash bản đã cài, hash
CHUẨN HOÁ (bỏ khác biệt xuống dòng, ngày tháng, khoảng trắng cuối dòng) để "cùng nội dung" không
bị hiểu thành "đã sửa". File này dùng lại `system_sync._norm_text` và `skill_hash` chứ không
viết bản thứ hai - hai hàm hash cho cùng một mục đích là hai thứ sẽ trôi lệch nhau.

Chỗ ghi sổ thì khác: `system_sync` có manifest của riêng nó cho tầng hệ thống, còn gói ghi vào
`STATE_DIR/packs-state/<pack_id>.json`. Tách ra vì hai vòng đời khác nhau - tầng hệ thống đi
theo bản app, gói thì người dùng cài và gỡ.

Cài vào brain NÀO
-----------------
Brain đang mở lúc bấm Cài, và ghi tên brain đó vào sổ. Vì agent/workflow/skill vốn thuộc về một
brain cụ thể (khác hẳn connector và plugin vốn dùng chung mọi brain), nên "cài vào tất cả" là
áp đặt: người dùng có brain việc và brain cá nhân, và họ không muốn mọi thứ ở cả hai nơi.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import system_sync
from config import STATE_DIR

HIEU_UNG_DIR = STATE_DIR / "packs-state"

# Loại năng lực gói ghi được vào brain, kèm nơi đến và hình dạng.
#   thu_muc : đường dẫn tương đối từ gốc brain
#   la_thu_muc : skill là một THƯ MỤC (SKILL.md + tệp phụ), agent/workflow là một tệp .md
LOAI = {
    "agents":    {"thu_muc": "agents",    "la_thu_muc": False, "duoi": ".md"},
    "workflows": {"thu_muc": "workflows", "la_thu_muc": False, "duoi": ".md"},
    "skills":    {"thu_muc": "skills",    "la_thu_muc": True,  "duoi": ""},
}


def _hash(duong: Path) -> str:
    """Hash chuẩn hoá của một tệp, hoặc của cả cây tệp nếu là thư mục.

    Dùng `system_sync._norm_text` để "cùng nội dung nhưng khác xuống dòng" không bị hiểu thành
    "người dùng đã sửa". Đây chính là ca đã cắn ở chỗ khác: trình soạn thảo Windows lưu lại một
    tệp là đủ đổi mọi byte xuống dòng."""
    if duong.is_file():
        try:
            return system_sync.skill_hash(duong.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            return ""
    if duong.is_dir():
        import hashlib
        h = hashlib.sha256()
        for f in sorted(duong.rglob("*")):
            if not f.is_file():
                continue
            h.update(str(f.relative_to(duong)).replace("\\", "/").encode("utf-8"))
            try:
                h.update(system_sync._norm_text(
                    f.read_text(encoding="utf-8", errors="replace")).encode("utf-8"))
            except OSError:
                continue
        return h.hexdigest()
    return ""


def _so_path(pack_id: str) -> Path:
    return HIEU_UNG_DIR / f"{pack_id}.json"


def doc_so(pack_id: str) -> dict:
    """Sổ hiệu ứng: những gì gói này đã ghi RA NGOÀI thư mục của nó."""
    try:
        d = json.loads(_so_path(pack_id).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _ghi_so(pack_id: str, d: dict) -> None:
    try:
        HIEU_UNG_DIR.mkdir(parents=True, exist_ok=True)
        p = _so_path(pack_id)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)
    except OSError as e:
        print(f"[pack_vault] ghi sổ {pack_id}: {e}", file=sys.stderr)


def _xoa_so(pack_id: str) -> None:
    try:
        _so_path(pack_id).unlink()
    except OSError:
        pass


def _nguon(thu_muc_goi: Path, loai: str) -> list:
    """Các mục loại này mà gói mang theo, dạng [(slug, đường_dẫn_nguồn)]."""
    goc = thu_muc_goi / LOAI[loai]["thu_muc"]
    if not goc.is_dir():
        return []
    ra = []
    try:
        for p in sorted(goc.iterdir()):
            if LOAI[loai]["la_thu_muc"]:
                if p.is_dir() and (p / "SKILL.md").is_file():
                    ra.append((p.name, p))
            elif p.is_file() and p.suffix.lower() == ".md":
                ra.append((p.stem, p))
    except OSError:
        pass
    return ra


def liet_ke(thu_muc_goi: Path) -> dict:
    """Gói này mang theo năng lực gì. Dùng cho màn hình xác nhận trước khi cài."""
    return {loai: [slug for slug, _ in _nguon(thu_muc_goi, loai)] for loai in LOAI}


def ke_hoach_cai(thu_muc_goi: Path, brain_root: str) -> dict:
    """Cài gói này vào brain thì đụng gì. KHÔNG ghi gì cả.

    `xung_dot` là những mục brain ĐÃ CÓ mà không phải do gói này đặt vào. Chúng sẽ bị BỎ QUA
    khi cài chứ không ghi đè - người dùng tự đặt tên trùng thì tệp của họ thắng."""
    root = Path(brain_root)
    ra = {"them": [], "cap_nhat": [], "xung_dot": [], "giu_nguyen": []}
    so = {}
    for loai in LOAI:
        for slug, nguon in _nguon(thu_muc_goi, loai):
            dich = root / LOAI[loai]["thu_muc"] / (slug + LOAI[loai]["duoi"])
            muc = {"loai": loai, "slug": slug, "duong": str(dich)}
            if not dich.exists():
                ra["them"].append(muc)
            elif _hash(dich) == so.get(f"{loai}/{slug}"):
                ra["cap_nhat"].append(muc)
            else:
                ra["xung_dot"].append(muc)
    return ra


def cai(pack_id: str, thu_muc_goi: Path, brain_root: str) -> dict:
    """Ghi năng lực của gói vào brain. Trả báo cáo từng mục.

    KHÔNG BAO GIỜ ghi đè một tệp mà gói không phải người đặt vào đó. Với bản cập nhật của chính
    gói này thì ghi đè chỉ khi tệp còn y nguyên - người dùng đã sửa thì giữ bản của họ, y như
    `system_sync` làm với skill hệ thống."""
    root = Path(brain_root)
    so_cu = doc_so(pack_id)
    muc_cu = so_cu.get("items") or {}
    moi = {}
    bao = {"them": [], "cap_nhat": [], "bo_qua": [], "loi": []}

    for loai in LOAI:
        for slug, nguon in _nguon(thu_muc_goi, loai):
            khoa = f"{loai}/{slug}"
            dich = root / LOAI[loai]["thu_muc"] / (slug + LOAI[loai]["duoi"])
            try:
                if dich.exists():
                    h = _hash(dich)
                    if khoa not in muc_cu:
                        # Của người dùng, hoặc của một gói khác. Không đụng.
                        bao["bo_qua"].append({"khoa": khoa, "vi_sao": "brain đã có mục cùng tên"})
                        continue
                    if h != muc_cu[khoa].get("hash"):
                        bao["bo_qua"].append({"khoa": khoa, "vi_sao": "bạn đã sửa, giữ bản của bạn"})
                        moi[khoa] = muc_cu[khoa]      # vẫn ghi nhận là của gói, để lúc gỡ còn biết
                        continue
                    ke = "cap_nhat"
                else:
                    ke = "them"
                dich.parent.mkdir(parents=True, exist_ok=True)
                if LOAI[loai]["la_thu_muc"]:
                    if dich.exists():
                        shutil.rmtree(dich, ignore_errors=True)
                    shutil.copytree(nguon, dich)
                else:
                    shutil.copy2(nguon, dich)
                moi[khoa] = {"duong": str(dich), "hash": _hash(dich), "loai": loai, "slug": slug}
                bao[ke].append({"khoa": khoa, "duong": str(dich)})
            except OSError as e:
                bao["loi"].append(f"{khoa}: {e}")

    if moi:
        _ghi_so(pack_id, {"brain": str(root), "items": moi})
    else:
        _xoa_so(pack_id)
    return bao


def ke_hoach_go(pack_id: str) -> dict:
    """Gỡ gói này thì mất năng lực nào, và giữ lại cái nào vì người dùng đã sửa."""
    so = doc_so(pack_id)
    xoa, giu = [], []
    for khoa, m in (so.get("items") or {}).items():
        p = Path(m.get("duong") or "")
        if not p.exists():
            continue
        (xoa if _hash(p) == m.get("hash") else giu).append(
            {"khoa": khoa, "slug": m.get("slug"), "loai": m.get("loai"), "duong": str(p)})
    return {"brain": so.get("brain", ""), "xoa": xoa, "giu": giu}


def go(pack_id: str) -> dict:
    """Xoá năng lực gói đã đặt vào brain. CHỈ xoá thứ còn y nguyên.

    Người dùng đã sửa thì giữ lại và trả về trong `giu` để giao diện nói ra. Xoá công sửa của
    người dùng vì họ gỡ một gói là đánh đổi tệ nhất có thể: gói cài lại được trong ba giây,
    còn thứ họ viết thì không."""
    ke = ke_hoach_go(pack_id)
    bao = {"da_xoa": [], "giu_lai": [x["khoa"] for x in ke["giu"]], "loi": []}
    for m in ke["xoa"]:
        p = Path(m["duong"])
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.is_file():
                p.unlink()
            bao["da_xoa"].append(m["khoa"])
        except OSError as e:
            bao["loi"].append(f"{m['khoa']}: {e}")
    _xoa_so(pack_id)
    return bao
