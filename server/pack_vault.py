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
import localefmt
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

# The folder the app READS each kind from (0.4xx, owner report 2026-11-04). The app falls back to the old
# `Javis/agents` / `Javis/workflows` while the flat folder does not exist (`main._brain_sub`). Writing into
# `<brain>/agents` on such a brain would create that folder, the app would switch to it, and every agent in
# `Javis/agents` would vanish from the Partners page.
_LEGACY = {"agents": "Javis/agents", "workflows": "Javis/workflows"}

# How many `-2`, `-3`... names to try before giving up on a clash.
_MAX_ALT = 50


def _dir_for(root: Path, loai: str) -> Path:
    new = root / LOAI[loai]["thu_muc"]
    old = _LEGACY.get(loai)
    if not new.is_dir() and old and (root / old).is_dir():
        return root / old
    return new


def _target(root: Path, loai: str, slug: str) -> Path:
    return _dir_for(root, loai) / (slug + LOAI[loai]["duoi"])


def _skill_disabled(p: Path) -> Path:
    """`skills/<slug>` -> `skills/.disabled/<slug>`, where the app moves a skill the user turned off."""
    return p.parent / ".disabled" / p.name


def _where(m: dict) -> Path | None:
    """Where an item the pack placed lives NOW, or None when the user deleted it.

    A skill the user turned off sits in `skills/.disabled/<slug>`: still there, still the pack's. Missing that
    case made a disabled skill look deleted (the Store said "not installed") and left it behind on uninstall."""
    p = Path(m.get("duong") or "")
    if not str(p) or str(p) == ".":
        return None
    if p.exists():
        return p
    if m.get("loai") == "skills":
        d = _skill_disabled(p)
        if d.exists():
            return d
    return None


def _taken(p: Path, loai: str) -> bool:
    return p.exists() or (loai == "skills" and _skill_disabled(p).exists())


def _free_slug(root: Path, loai: str, slug: str) -> str:
    """First `<slug>-N` that is free in this brain, or "" when none is."""
    for n in range(2, _MAX_ALT + 2):
        cand = f"{slug}-{n}"
        if not _taken(_target(root, loai, cand), loai):
            return cand
    return ""


def _set_slug(md: Path, old: str, new: str) -> None:
    """Point the `slug:` line of a copied agent/workflow file at its new file name.

    Only inside the frontmatter, and only the exact old value: the body is the author's text."""
    try:
        text = md.read_text(encoding="utf-8")
    except OSError:
        return
    if not text.startswith("---"):
        return
    end = text.find("\n---", 3)
    if end < 0:
        return
    head, rest = text[:end], text[end:]
    lines = head.split("\n")
    for i, line in enumerate(lines):
        if line.strip() in (f"slug: {old}", f"slug: '{old}'", f'slug: "{old}"'):
            lines[i] = f"slug: {new}"
            break
    else:
        return
    md.write_text("\n".join(lines) + rest, encoding="utf-8")


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

    `xung_dot` là những mục brain ĐÃ CÓ mà không phải do gói này đặt vào. Chúng KHÔNG bị ghi đè:
    tệp của người dùng thắng, và bản trong gói được cài dưới một tên mới (`<slug>-2`), xem `cai`."""
    root = Path(brain_root)
    ra = {"them": [], "cap_nhat": [], "xung_dot": [], "giu_nguyen": []}
    so = doc_so_brain(thu_muc_goi.name, root)
    for loai in LOAI:
        for slug, nguon in _nguon(thu_muc_goi, loai):
            khoa = f"{loai}/{slug}"
            cu = so.get(khoa)
            hien = _where(cu) if cu else None
            dich = hien or _target(root, loai, slug)
            muc = {"loai": loai, "slug": slug, "duong": str(dich)}
            if cu and not hien:
                ra["them"].append(muc)
            elif cu:
                (ra["cap_nhat"] if _hash(hien) == cu.get("hash") else ra["giu_nguyen"]).append(muc)
            elif not _taken(dich, loai):
                ra["them"].append(muc)
            else:
                ra["xung_dot"].append(muc)
    return ra


def doc_so_brain(pack_id: str, root: Path) -> dict:
    """Items of this pack's ledger, but only when it was written for THIS brain.

    The ledger holds one brain. Installing into another brain is a fresh install there: using the old brain's
    entries would compare against (and write to) files of a brain the user did not open."""
    so = doc_so(pack_id)
    try:
        cung = bool(so.get("brain")) and Path(so["brain"]).resolve() == Path(root).resolve()
    except OSError:
        cung = so.get("brain") == str(root)
    return (so.get("items") or {}) if cung else {}


def _copy(nguon: Path, dich: Path, loai: str) -> None:
    dich.parent.mkdir(parents=True, exist_ok=True)
    if LOAI[loai]["la_thu_muc"]:
        if dich.exists():
            shutil.rmtree(dich, ignore_errors=True)
        shutil.copytree(nguon, dich)
    else:
        shutil.copy2(nguon, dich)


def cai(pack_id: str, thu_muc_goi: Path, brain_root: str) -> dict:
    """Ghi năng lực của gói vào brain. Trả báo cáo từng mục.

    KHÔNG BAO GIỜ ghi đè một tệp mà gói không phải người đặt vào đó. Với bản cập nhật của chính
    gói này thì ghi đè chỉ khi tệp còn y nguyên - người dùng đã sửa thì giữ bản của họ, y như
    `system_sync` làm với skill hệ thống.

    Trùng tên với một mục gói KHÔNG đặt vào (owner report 2026-11-04): the user renamed or edited the
    pack's agent, uninstalled (their edited copy is kept, by design), then installed again. Before, the
    install skipped the item without a word, so the agent never came back and the Store still said
    "installed". Now: an identical copy is adopted as the pack's again, and a different one stays the
    user's while the pack's copy goes in under a free name (`javis-vu-2`), reported in `doi_ten`."""
    root = Path(brain_root)
    muc_cu = doc_so_brain(pack_id, root)
    moi = {}
    bao = {"them": [], "cap_nhat": [], "bo_qua": [], "doi_ten": [], "loi": []}

    for loai in LOAI:
        for slug, nguon in _nguon(thu_muc_goi, loai):
            khoa = f"{loai}/{slug}"
            cu = muc_cu.get(khoa)
            try:
                if cu:
                    hien = _where(cu)
                    if hien is not None:
                        if _hash(hien) != cu.get("hash"):
                            bao["bo_qua"].append({"khoa": khoa, "vi_sao": localefmt.chu(
                                "bạn đã sửa, giữ bản của bạn", "you edited it, your version is kept")})
                            moi[khoa] = cu      # vẫn ghi nhận là của gói, để lúc gỡ còn biết
                            continue
                        # Unchanged: update in place, where it is (a turned-off skill stays off).
                        dich, ke, ten = hien, "cap_nhat", cu.get("slug") or slug
                    else:
                        # The user deleted it. Put it back under the name it had.
                        ten = cu.get("slug") or slug
                        dich, ke = _target(root, loai, ten), "them"
                        if _taken(dich, loai):
                            ten = ""
                else:
                    ten, ke = slug, "them"
                    dich = _target(root, loai, slug)
                    if _taken(dich, loai):
                        hien = dich if dich.exists() else _skill_disabled(dich)
                        if _hash(hien) == _hash(nguon):
                            # Same content as the pack ships: it is the pack's copy, take it back.
                            moi[khoa] = {"duong": str(dich), "hash": _hash(hien), "loai": loai, "slug": slug}
                            bao["cap_nhat"].append({"khoa": khoa, "duong": str(hien)})
                            continue
                        ten = ""
                if not ten:
                    ten = _free_slug(root, loai, slug)
                    if not ten:
                        bao["bo_qua"].append({"khoa": khoa, "vi_sao": localefmt.chu(
                            "brain đã có mục cùng tên", "the brain already has an item with that name")})
                        continue
                    dich = _target(root, loai, ten)
                    ke = "doi_ten"
                _copy(nguon, dich, loai)
                if ten != slug and not LOAI[loai]["la_thu_muc"]:
                    _set_slug(dich, slug, ten)
                moi[khoa] = {"duong": str(dich), "hash": _hash(dich), "loai": loai, "slug": ten}
                hang = {"khoa": khoa, "duong": str(dich)}
                if ke == "doi_ten":
                    hang.update({"slug": ten, "goc": slug, "loai": loai})
                bao[ke].append(hang)
            except OSError as e:
                bao["loi"].append(f"{khoa}: {e}")

    if moi:
        _ghi_so(pack_id, {"brain": str(root), "items": moi})
    else:
        _xoa_so(pack_id)
    return bao


def con_lai(pack_id: str) -> dict:
    """How many brain items this pack placed, and how many are still there.

    The Store uses it: a pack that only brings agents/workflows/skills, whose items the user deleted from the
    app, is not "installed" any more, and must offer Install again instead of Uninstall."""
    items = doc_so(pack_id).get("items") or {}
    return {"placed": len(items), "present": sum(1 for m in items.values() if _where(m) is not None)}


def ke_hoach_go(pack_id: str) -> dict:
    """Gỡ gói này thì mất năng lực nào, và giữ lại cái nào vì người dùng đã sửa."""
    so = doc_so(pack_id)
    xoa, giu = [], []
    for khoa, m in (so.get("items") or {}).items():
        p = _where(m)
        if p is None:
            continue
        (xoa if _hash(p) == m.get("hash") else giu).append(
            {"khoa": khoa, "slug": m.get("slug"), "loai": m.get("loai"), "duong": str(p)})
    return {"brain": so.get("brain", ""), "xoa": xoa, "giu": giu}


def _valid_skill_slug(slug: str) -> bool:
    try:
        import skill_router
        return skill_router.valid_slug(slug)
    except Exception:
        return False


def _drop_mirror(brain: str, slug: str) -> None:
    """Remove the `.claude/skills/<slug>` copy Claude Code loads natively.

    `system_sync.mirror_skills` only ever adds; removing is the job of whoever removes the skill (the
    /skills/delete route does it). Without this an uninstalled pack skill kept loading in every Claude Code
    turn run inside the brain."""
    if not brain or not _valid_skill_slug(slug):
        return
    base = Path(brain) / ".claude" / "skills"
    for d in (base / slug, base / ".disabled" / slug):
        try:
            if d.is_dir() and base.resolve() in d.resolve().parents:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


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
            if m.get("loai") == "skills":
                _drop_mirror(ke.get("brain", ""), p.name)
            bao["da_xoa"].append(m["khoa"])
        except OSError as e:
            bao["loi"].append(f"{m['khoa']}: {e}")
    _xoa_so(pack_id)
    return bao
