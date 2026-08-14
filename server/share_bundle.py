"""
share_bundle.py - Xuất/Nhập năng lực Javis (agent / skill / workflow) dưới dạng gói .zip để
CHIA SẺ giữa các brain / người dùng.

Gói "javis-bundle" = 1 file .zip:
  javis-bundle.json          - manifest (kind, primary, items, app_version)
  agents/<slug>.md           - agent (1 file)
  workflows/<slug>.md        - workflow (1 file)
  skills/<slug>/...          - skill (cả thư mục: SKILL.md + asset)

Gói KÈM PHỤ THUỘC để bên nhận chạy được ngay:
  workflow -> các agent nó tham chiếu (step.agent + verify_agent) -> skill của các agent đó
  agent    -> skill của agent
Skill HỆ THỐNG (javis-builder/ingest/query/lint...) KHÔNG gói (bên nhận đã có sẵn theo app).

Nhập: đọc gói .zip (hoặc 1 file .md lẻ cho agent/workflow), ghi vào đúng thư mục brain. Rào an toàn:
  - chống zip-slip / path traversal (chỉ nhận agents/ workflows/ skills/, chặn '..', path tuyệt đối).
  - giới hạn số file + tổng dung lượng giải nén + kích thước mỗi file (chống zip bomb).
  - trùng slug -> BỎ QUA trừ khi overwrite=True (giữ nguyên slug để tham chiếu workflow->agent không gãy).

Module CHỈ thao tác file trong các thư mục được truyền vào; không import main/mcp (tránh vòng import).
"""
from __future__ import annotations

import localefmt   # múi giờ theo cấu hình, thay UTC+7 nhúng cứng
import io
import json
import re
import unicodedata
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import fastyaml

_MAX_FILES = 300
_MAX_TOTAL = 20 * 1024 * 1024      # tổng giải nén 20MB
_MAX_ONE = 5 * 1024 * 1024         # mỗi file 5MB
_ALLOWED_TOP = ("agents/", "workflows/", "skills/")


def _parse(text: str):
    """(meta dict, body) từ file .md có frontmatter YAML."""
    if (text or "").startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                meta = fastyaml.safe_load(parts[1]) or {}
            except Exception:
                meta = {}
            return (meta if isinstance(meta, dict) else {}), parts[2]
    return {}, (text or "")


def slugify(name: str) -> str:
    """ascii-slug không dấu (khớp cách main.py sinh slug)."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s


def _safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(s or "bundle")).strip("-") or "bundle"


def _valid_slug(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", s or "")) and ".." not in (s or "")


# ────────────────────────── XUẤT ──────────────────────────

def build_bundle(kind, slug, *, agents_dir, workflows_dir, skills_root,
                 include_deps=True, system_slugs=frozenset(), app_version=""):
    """Trả (zip_bytes, filename) cho 1 năng lực + phụ thuộc; (None, None) nếu không tìm thấy."""
    agents_dir, workflows_dir, skills_root = Path(agents_dir), Path(workflows_dir), Path(skills_root)
    files: dict[str, bytes] = {}
    items: list[dict] = []
    seen = {"agent": set(), "skill": set(), "workflow": set()}

    def add_skill(sslug):
        sslug = str(sslug or "")
        if not _valid_slug(sslug) or sslug in seen["skill"] or sslug in system_slugs:
            return
        smd = skills_root / sslug / "SKILL.md"
        if not smd.is_file():
            return
        seen["skill"].add(sslug)
        d = skills_root / sslug
        for f in sorted(d.rglob("*")):
            if f.is_file():
                rel = f.relative_to(skills_root).as_posix()   # <slug>/...
                files[f"skills/{rel}"] = f.read_bytes()
        meta, _ = _parse(smd.read_text(encoding="utf-8", errors="replace"))
        items.append({"type": "skill", "slug": sslug, "name": meta.get("name", sslug)})

    def add_agent(aslug):
        aslug = str(aslug or "")
        if not _valid_slug(aslug) or aslug in seen["agent"]:
            return
        p = agents_dir / f"{aslug}.md"
        if not p.is_file():
            return
        seen["agent"].add(aslug)
        text = p.read_text(encoding="utf-8", errors="replace")
        files[f"agents/{aslug}.md"] = text.encode("utf-8")
        meta, _ = _parse(text)
        items.append({"type": "agent", "slug": aslug, "name": meta.get("name", aslug)})
        if include_deps:
            for sk in (meta.get("skills") or []):
                add_skill(sk)

    def add_workflow(wslug):
        wslug = str(wslug or "")
        if not _valid_slug(wslug) or wslug in seen["workflow"]:
            return
        p = workflows_dir / f"{wslug}.md"
        if not p.is_file():
            return
        seen["workflow"].add(wslug)
        text = p.read_text(encoding="utf-8", errors="replace")
        files[f"workflows/{wslug}.md"] = text.encode("utf-8")
        meta, _ = _parse(text)
        items.append({"type": "workflow", "slug": wslug, "name": meta.get("name", wslug)})
        if include_deps:
            for st in (meta.get("steps") or []):
                if isinstance(st, dict):
                    add_agent(st.get("agent"))
                    add_agent(st.get("verify_agent"))

    {"agent": add_agent, "skill": add_skill, "workflow": add_workflow}.get(kind, lambda _s: None)(slug)
    if not files:
        return None, None

    prim = next((i for i in items if i["type"] == kind and i["slug"] == slug), None)
    manifest = {
        "format": "javis-bundle", "version": 1, "kind": kind,
        "primary": {"type": kind, "slug": slug, "name": (prim or {}).get("name", slug)},
        "items": items, "app_version": app_version,
        "created": localefmt.now().isoformat(timespec="seconds"),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("javis-bundle.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        for arc, data in files.items():
            z.writestr(arc, data)
    return buf.getvalue(), f"{_safe_name((prim or {}).get('name') or slug)}.javis.zip"


# ────────────────────────── NHẬP ──────────────────────────

def _dst_for(arc, agents_dir, workflows_dir, skills_root):
    """(target_path, type, slug) cho 1 arcname hợp lệ; None nếu bỏ qua/không hợp lệ."""
    top = next((t for t in _ALLOWED_TOP if arc.startswith(t)), None)
    if not top:
        return None
    rel = arc[len(top):]
    if not rel or rel.endswith("/"):
        return None
    if top == "agents/":
        if "/" in rel or not rel.endswith(".md"):
            return None
        return Path(agents_dir) / rel, "agent", rel[:-3]
    if top == "workflows/":
        if "/" in rel or not rel.endswith(".md"):
            return None
        return Path(workflows_dir) / rel, "workflow", rel[:-3]
    # skills/<slug>/...
    slug = rel.split("/")[0]
    if not _valid_slug(slug):
        return None
    return Path(skills_root) / rel, "skill", slug


def import_bundle(data: bytes, filename, *, agents_dir, workflows_dir, skills_root, overwrite=False):
    """Nhập 1 gói .zip (hoặc .md lẻ). Trả {imported, skipped, errors} (mỗi cái list 'type:slug')."""
    res = {"imported": [], "skipped": [], "errors": []}
    imp, skp = set(), set()
    name = (filename or "").lower()
    is_zip = data[:2] == b"PK" or name.endswith(".zip")

    def write_one(target: Path, blob: bytes, typ, slug, arc=None):
        key = f"{typ}:{slug}"
        try:
            if target.exists() and not overwrite:
                skp.add(key); return
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_bytes(blob)
            tmp.replace(target)
            imp.add(key)
        except Exception as e:
            res["errors"].append(f"{arc or key}: {type(e).__name__}: {e}")

    if not is_zip:
        # 1 file .md lẻ → agent hoặc workflow
        try:
            text = data.decode("utf-8")
        except Exception:
            res["errors"].append("File không đọc được (cần .zip hoặc .md UTF-8).")
            return res
        meta, _ = _parse(text)
        typ = str(meta.get("type") or "").lower()
        if typ in ("agent", "workflow"):
            slug = slugify(meta.get("slug") or meta.get("name") or Path(name).stem)
            if not _valid_slug(slug):
                res["errors"].append("Không xác định được slug hợp lệ từ file.")
                return res
            target = (Path(agents_dir) if typ == "agent" else Path(workflows_dir)) / f"{slug}.md"
            write_one(target, data, typ, slug)
        elif meta.get("name") and (name.endswith("skill.md") or "group" in meta or "description" in meta):
            # SKILL.md lẻ (skill Claude chưa nén) → tạo skills/<slug>/SKILL.md
            slug = slugify(meta.get("name"))
            if not _valid_slug(slug):
                res["errors"].append("Không xác định được tên skill hợp lệ từ file SKILL.md.")
                return res
            write_one(Path(skills_root) / slug / "SKILL.md", data, "skill", slug)
        else:
            res["errors"].append("File .md không rõ là agent/skill/workflow. Skill nên nhập bằng gói .zip / .skill.")
            return res
    else:
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
        except Exception as e:
            res["errors"].append(f"Không mở được file .zip: {e}")
            return res
        infos = [i for i in z.infolist() if not i.is_dir()]
        if len(infos) > _MAX_FILES:
            res["errors"].append(f"Gói có quá nhiều file (>{_MAX_FILES}).")
            return res
        if sum(i.file_size for i in infos) > _MAX_TOTAL:
            res["errors"].append("Gói giải nén quá lớn (>20MB).")
            return res
        def _bad(arc, i):   # rào chung: kích thước + path traversal
            if i.file_size > _MAX_ONE:
                res["errors"].append(f"{arc}: file quá lớn (>5MB)."); return True
            if arc.startswith("/") or ".." in arc.split("/") or ":" in arc:
                res["errors"].append(f"{arc}: đường dẫn không hợp lệ."); return True
            return False

        arcs = [i.filename.replace("\\", "/") for i in infos]
        is_javis = "javis-bundle.json" in arcs or any(a.startswith(_ALLOWED_TOP) for a in arcs)

        if is_javis:
            skip_skill = set()   # slug skill đã có (bỏ qua cả thư mục khi không ghi đè)
            for i in infos:
                arc = i.filename.replace("\\", "/")
                if arc == "javis-bundle.json" or _bad(arc, i):
                    continue
                dst = _dst_for(arc, agents_dir, workflows_dir, skills_root)
                if not dst:
                    continue   # file ngoài agents/workflows/skills → bỏ qua im lặng
                target, typ, slug = dst
                if typ == "skill":
                    if slug in skip_skill:
                        skp.add(f"skill:{slug}"); continue
                    if (Path(skills_root) / slug).exists() and not overwrite:
                        skip_skill.add(slug); skp.add(f"skill:{slug}"); continue
                write_one(target, z.read(i), typ, slug, arc=arc)
        else:
            # Gói SKILL kiểu CLAUDE (.skill / .zip): SKILL.md ở gốc hoặc trong 1 thư mục con.
            cand = sorted([a for a in arcs if a.rsplit("/", 1)[-1] == "SKILL.md"], key=lambda a: a.count("/"))
            if not cand:
                res["errors"].append("Gói .zip không phải javis-bundle và không có SKILL.md - không rõ nhập gì.")
                return res
            prefix = cand[0][:-len("SKILL.md")]   # "" (gốc) hoặc "thu-muc/"
            try:
                sk_meta, _ = _parse(z.read(cand[0]).decode("utf-8", "replace"))
            except Exception:
                sk_meta = {}
            slug = slugify(sk_meta.get("name") or "") or slugify(prefix.rstrip("/"))
            if not _valid_slug(slug):
                res["errors"].append("Không xác định được tên skill hợp lệ từ gói (thiếu 'name' trong SKILL.md).")
                return res
            if (Path(skills_root) / slug).exists() and not overwrite:
                skp.add(f"skill:{slug}")
            else:
                for i in infos:
                    arc = i.filename.replace("\\", "/")
                    if not arc.startswith(prefix) or _bad(arc, i):
                        continue
                    rel = arc[len(prefix):]
                    base = rel.rsplit("/", 1)[-1]
                    if not rel or "__MACOSX/" in arc or base in (".DS_Store",):
                        continue   # bỏ rác của trình nén Mac
                    write_one(Path(skills_root) / slug / rel, z.read(i), "skill", slug, arc=arc)

    res["imported"] = sorted(imp)
    res["skipped"] = sorted(skp - imp)
    return res
