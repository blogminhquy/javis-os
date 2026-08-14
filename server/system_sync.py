"""
system_sync.py - Tầng NĂNG LỰC HỆ THỐNG của Javis OS (tách khỏi dữ liệu người dùng trong brain).

Vấn đề giải quyết: trước đây các chức năng mặc định (skill javis-builder, ingest/query/lint,
loop tự-cải-tiến) được seed create-if-missing vào TỪNG brain → brain tạo ở bản cũ không bao
giờ nhận bản skill mới; brain ngoài (path:) không có gì; đổi brain là "mất" chức năng hệ thống.

Kiến trúc mới - 2 tầng rõ ràng:
  - TẦNG HỆ THỐNG (đi theo repo/image, update theo phiên bản app):
      <project>/.claude/skills/<slug>/SKILL.md   - skill hệ thống (nguồn chuẩn; chat cwd=/app
                                                    nên Claude Code nạp NATIVE, không phụ thuộc brain)
      <project>/system/loops/<slug>.md            - loop hệ thống (template, placeholder {today})
  - TẦNG BRAIN (dữ liệu người dùng, đổi theo brain): memory/, sources/, wiki/, agent/workflow/
      skill/loop do user tạo. KHÔNG bị update ghi đè.

Skill trong brain có CANONICAL phẳng <brain>/skills/<slug>/SKILL.md (cùng hướng agents/workflows/
memory). Tầng hệ thống được cài vào canonical đó qua sync có manifest, rồi MIRROR sang
<brain>/.claude/skills để Claude Code nạp NATIVE ở ngữ cảnh cwd=brain (workflow/loop/learn/lint) -
mirror chỉ là bản phái sinh (bonus), router chính của Javis không phụ thuộc nó. Brain cũ để skill
ở .claude/skills được migrate_brain() dời sang skills/ (idempotent, 1 chiều, không mất data):
  - Manifest <brain>/.javis/system-manifest.json ghi hash bản đã cài của từng file hệ thống.
  - Thiếu → cài (kể cả khi user lỡ xoá: file hệ thống tự hồi phục như file HĐH; muốn ngừng
    dùng thì TẮT skill - chuyển vào skills/.disabled - sync tôn trọng, không bật lại).
  - Có + CHƯA bị user sửa (hash khớp manifest, hoặc khớp bộ hash các bản đã ship LEGACY_HASHES)
    → ghi đè bằng bản mới của app (đây là cách "chức năng hệ thống update theo phiên bản").
  - Có + user ĐÃ SỬA → GIỮ NGUYÊN bản của user (user override; từ đó app không tự đụng nữa).
  - Loop: các trường trạng thái user chỉnh (enabled/mode/interval_min/goal/quiet_hours/
    max_runs_per_day/workspace/tools_profile) được BẢO TOÀN khi update thân prompt.

Hash CHUẨN HOÁ để so "cùng nội dung": CRLF→LF, ngày ISO → <DATE> (seed đóng dấu ngày lúc cài),
bỏ khoảng trắng cuối dòng; với loop bỏ luôn các frontmatter key volatile ở trên.

BẢO TRÌ: khi bản phát hành MỚI đổi nội dung 1 file hệ thống, thêm hash bản CŨ vào
LEGACY_HASHES (chạy `python server/system_sync.py --hash` TRƯỚC khi sửa để lấy hash hiện tại).
Manifest lo phần còn lại cho mọi brain đã sync ít nhất một lần.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import yaml
import fastyaml

PROJECT_ROOT = Path(__file__).parent.parent
SYSTEM_SKILLS_DIR = PROJECT_ROOT / ".claude" / "skills"
SYSTEM_LOOPS_DIR = PROJECT_ROOT / "system" / "loops"
MANIFEST_REL = Path(".javis") / "system-manifest.json"

# Frontmatter key của loop mà user/UI chỉnh trong vận hành bình thường → KHÔNG tính là "đã sửa"
# và được BẢO TOÀN khi update. (self_improve.save_loop rewrite các key này khi user bật/tắt.)
_LOOP_VOLATILE_KEYS = {"enabled", "mode", "interval_min", "goal", "quiet_hours",
                       "max_runs_per_day", "workspace", "tools_profile", "updated"}

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")


def _app_version() -> str:
    try:
        return (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return ""


# ────────────────────────── chuẩn hoá + hash ──────────────────────────

def _norm_text(text: str) -> str:
    t = (text or "").replace("\r\n", "\n").replace("﻿", "")
    t = _DATE_RE.sub("<DATE>", t)
    t = "\n".join(line.rstrip() for line in t.split("\n"))
    return t.strip() + "\n"


def _split_frontmatter(text: str):
    """Trả (meta dict, body). Không có frontmatter → ({}, text)."""
    if (text or "").startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                meta = fastyaml.safe_load(parts[1]) or {}
            except Exception:
                meta = {}
            return (meta if isinstance(meta, dict) else {}), parts[2]
    return {}, (text or "")


def skill_hash(text: str) -> str:
    """Hash chuẩn hoá của 1 file SKILL.md (toàn văn)."""
    return hashlib.sha256(_norm_text(text).encode("utf-8")).hexdigest()


def loop_hash(text: str) -> str:
    """Hash chuẩn hoá của 1 file loop: frontmatter BỎ key volatile + thân prompt."""
    meta, body = _split_frontmatter(text)
    stable = {str(k): meta[k] for k in sorted(meta, key=str) if str(k) not in _LOOP_VOLATILE_KEYS}
    payload = json.dumps(stable, ensure_ascii=False, sort_keys=True, default=str) + "\n---\n" + _norm_text(body)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ────────────────────────── bộ hash các bản ĐÃ SHIP (pre-manifest) ──────────────────────────
# Nhận diện file trong brain là bản seed cũ CHƯA bị user sửa → an toàn để update.
# Sinh bằng scripts trích meta_tools.py tại các commit v0.7.9 (fe33c2c), v0.8.1 (703fe54),
# v0.8.2 (0d3c953), v0.8.3 (f4fe71c). Điền ở cuối file (sau khi tính) - xem __main__.
LEGACY_HASHES: dict[str, set] = {}   # key "skills/<slug>" | "loops/<slug>" → set hash


# ────────────────────────── nguồn hệ thống ──────────────────────────

def system_skill_slugs() -> set:
    """Slug các skill HỆ THỐNG (từ <project>/.claude/skills). Cache theo process."""
    global _SKILL_SLUGS_CACHE
    if _SKILL_SLUGS_CACHE is None:
        s = set()
        try:
            if SYSTEM_SKILLS_DIR.is_dir():
                for p in SYSTEM_SKILLS_DIR.iterdir():
                    if p.is_dir() and not p.name.startswith(".") and (p / "SKILL.md").is_file():
                        s.add(p.name)
        except Exception:
            pass
        _SKILL_SLUGS_CACHE = s
    return _SKILL_SLUGS_CACHE


_SKILL_SLUGS_CACHE: Optional[set] = None


def is_system_skill(slug: str) -> bool:
    return slug in system_skill_slugs()


def _system_items():
    """Danh sách item hệ thống: (key, kind, slug, nội dung ĐÃ RENDER, đường dẫn con trong skill).

    Skill là một PACKAGE, không phải một file: `html-to-webcake` ship kèm `tools/*.js` mà thân
    skill bảo agent chạy. Trước 0.33.0 hàm này chỉ đọc mỗi `SKILL.md`, nên cây con KHÔNG BAO GIỜ
    tới brain nào - skill đó hỏng ở mọi brain từ ngày ship và cuối cùng bị gỡ hẳn ở 0.9.291 thay
    vì được vá. Giờ mọi file trong thư mục skill đều được ship.

    Khoá manifest của SKILL.md GIỮ NGUYÊN `skills/<slug>` (không đổi thành `skills/<slug>/SKILL.md`):
    mọi brain đang chạy đã ghi khoá cũ, đổi khoá là chúng thấy "chưa có mục này" rồi đóng dấu
    user-modified cho một file mà người dùng chưa hề đụng vào - kể từ đó skill hệ thống ngừng
    cập nhật trong im lặng. File con dùng khoá `skills/<slug>/<đường dẫn con>`.
    """
    items = []
    try:
        if SYSTEM_SKILLS_DIR.is_dir():
            for p in sorted(SYSTEM_SKILLS_DIR.iterdir()):
                f = p / "SKILL.md"
                if not (p.is_dir() and not p.name.startswith(".") and f.is_file()):
                    continue
                items.append((f"skills/{p.name}", "skill", p.name, f.read_text(encoding="utf-8"), "SKILL.md"))
                for extra in sorted(x for x in p.rglob("*") if x.is_file()):
                    rel = extra.relative_to(p).as_posix()
                    # bỏ mọi thứ ẩn ở BẤT KỲ tầng nào (.DS_Store, tools/.cache/…), không chỉ tầng đầu
                    if rel == "SKILL.md" or any(part.startswith(".") for part in rel.split("/")):
                        continue
                    try:
                        body = extra.read_text(encoding="utf-8")
                    except (UnicodeDecodeError, OSError) as e:
                        print(f"[system sync] bỏ qua {extra}: {type(e).__name__}", file=sys.stderr)
                        continue
                    items.append((f"skills/{p.name}/{rel}", "skill", p.name, body, rel))
    except Exception as e:
        print(f"[system sync] đọc skills hệ thống lỗi: {e}", file=sys.stderr)
    try:
        if SYSTEM_LOOPS_DIR.is_dir():
            for f in sorted(SYSTEM_LOOPS_DIR.glob("*.md")):
                content = f.read_text(encoding="utf-8").replace("{today}", _today())
                items.append((f"loops/{f.stem}", "loop", f.stem, content, f"{f.stem}.md"))
    except Exception as e:
        print(f"[system sync] đọc loops hệ thống lỗi: {e}", file=sys.stderr)
    return items


# ────────────────────────── manifest ──────────────────────────

def _manifest_path(root: Path) -> Path:
    return root / MANIFEST_REL


def _read_manifest(root: Path) -> dict:
    try:
        p = _manifest_path(root)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("files", {})
                return data
    except Exception:
        pass
    return {"files": {}}


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def _write_manifest(root: Path, data: dict) -> None:
    data["app_version"] = _app_version()
    data["synced_at"] = datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")
    _atomic_write(_manifest_path(root), json.dumps(data, ensure_ascii=False, indent=2))


# ────────────────────────── sync ──────────────────────────

def _skill_paths(root: Path, slug: str, rel: str = "SKILL.md"):
    """(path đang BẬT, path đang TẮT) của 1 file trong skill.
    CANONICAL = <root>/skills (phẳng, cùng hướng agents/workflows/memory). Skill hệ thống được
    cài vào đây; mirror_skills() copy sang <root>/.claude/skills cho Claude Code native.
    `rel` là đường dẫn con trong thư mục skill (mặc định SKILL.md, còn lại là tools/…)."""
    base = root / "skills"
    return base / slug / rel, base / ".disabled" / slug / rel


def migrate_brain(root) -> None:
    """Idempotent: dời skill legacy <root>/.claude/skills/** → CANONICAL <root>/skills/**.
    Dời CẢ cây bật lẫn cây .disabled (để skill người dùng đã TẮT không bị cài lại thành BẬT).
    CHỈ move khi đích CHƯA có (canonical thắng - không ghi đè). Nguồn+đích đều dưới <root> nên
    cùng ổ đĩa → shutil.move = rename nguyên tử (không lo copy dở dang). Per-slug try/except:
    1 skill lỗi không chặn các skill còn lại."""
    root = Path(root)
    legacy = root / ".claude" / "skills"
    canonical = root / "skills"
    if not legacy.is_dir():
        return
    pairs = [(legacy, canonical), (legacy / ".disabled", canonical / ".disabled")]
    for src_base, dst_base in pairs:
        try:
            if not src_base.is_dir():
                continue
            for d in sorted(p for p in src_base.iterdir()
                            if p.is_dir() and p.name != ".disabled" and (p / "SKILL.md").is_file()):
                dst = dst_base / d.name
                try:
                    if dst.exists():
                        continue   # canonical đã có bản này → giữ nguyên, KHÔNG ghi đè
                    dst_base.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(d), str(dst))
                except Exception as e:
                    print(f"[skill migrate] {d} → {dst}: {type(e).__name__}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[skill migrate] {src_base}: {type(e).__name__}: {e}", file=sys.stderr)


_DESC_RE = re.compile(r"^(description\s*:\s*)(.*)$", re.MULTILINE)


def _cap_desc(text: str, cap: int) -> Optional[str]:
    """Rút `description` trong frontmatter xuống <= cap ký tự. None = không cần/không sửa được.

    Vì sao chỉ sửa BẢN MIRROR: Claude Code nạp native đọc frontmatter ở `.claude/skills`, và
    danh sách skill đó đi vào phần đầu CỐ ĐỊNH của MỌI lượt chat. Đo trên brain thật: 14/30
    skill vượt trần 150 ký tự của chính dự án (dài nhất 1.018), tổng mô tả 10.095 ký tự nạp
    mỗi phiên; ép đúng trần còn 3.892, giảm 61%. Bản canonical trong `skills/` GIỮ NGUYÊN chữ
    của người dùng - mirror vốn là bản phái sinh. Không mất năng lực: mô tả chỉ để định tuyến,
    thân skill vẫn nạp đủ khi được gọi, và router của Javis xưa nay đã cắt đúng ở 150 rồi.
    """
    m = _DESC_RE.search(text or "")
    if not m:
        return None
    raw = m.group(2).strip()
    end = m.end()          # hết dòng `description:` - scalar nhiều dòng sẽ đẩy mốc này xuống
    if raw.startswith((">", "|")):
        # Scalar gấp/khối (`>`, `>-`, `|`): giá trị nằm ở các dòng THỤT SÂU phía dưới. Nuốt trọn
        # khối rồi thay bằng một dòng gọn. Đây KHÔNG phải ca hiếm - 2 mô tả dài nhất của brain
        # thật (963 và 893 ký tự) đều viết kiểu này.
        lines = text[end:].split("\n")
        take = 0
        for i, l in enumerate(lines):
            if l.strip() == "":
                take = i + 1
                continue
            if l[:1] in (" ", "\t"):
                take = i + 1
                continue
            break
        block = "\n".join(lines[:take])
        end = end + len(block)
        try:
            val = fastyaml.safe_load(f"description: {raw}\n{block}\n").get("description")
        except Exception:
            return None
        if not isinstance(val, str):
            return None
    elif len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        # Bóc nháy bao ngoài để đếm ĐÚNG phần chữ, rồi trả lại bằng scalar JSON an toàn cho YAML.
        try:
            val = fastyaml.safe_load(raw)
        except Exception:
            return None
        val = val if isinstance(val, str) else raw
    else:
        val = raw
    if len(val) <= cap:
        return None
    cut = val[:cap - 1].rstrip()     # chừa 1 chỗ cho "…" để tổng vẫn <= cap
    sp = cut.rfind(" ")
    if sp > cap * 0.6:
        cut = cut[:sp].rstrip()      # cắt ở ranh giới từ cho đỡ cụt giữa chữ
    return text[:m.start(2)] + json.dumps(cut + "…", ensure_ascii=False) + text[end:]


def _copy_skill_md_capped(src: Path, dst: Path) -> None:
    """copy2 nhưng rút description quá dài. Bất kỳ trục trặc nào -> chép nguyên như cũ."""
    try:
        import skill_router
        cap = skill_router.SKILL_DESC_MAX
        text = src.read_text(encoding="utf-8")
        new = _cap_desc(text, cap)
        if new is None:
            shutil.copy2(str(src), str(dst))
            return
        dst.write_text(new, encoding="utf-8")
    except Exception:
        shutil.copy2(str(src), str(dst))


def mirror_skills(root) -> None:
    """Mirror MỘT CHIỀU <root>/skills → <root>/.claude/skills (CHỈ skill đang BẬT), ĐỆ QUY
    cả references/ scripts/ templates/ - skill là PACKAGE, không phải một file.
    Mục đích: các ngữ cảnh Claude Code chạy cwd=brain (workflow/loop/learn/lint) vẫn nạp skill
    NATIVE như bonus. Add/update-only, BỎ QUA .disabled (mirror skill đã tắt = vô tình bật lại
    native). KHÔNG xoá entry lạ ở .claude (việc gỡ mirror khi tắt/xoá skill do endpoint xử lý).
    Đây là bản phái sinh - hỏng cũng không phá router chính.

    ĐƯỜNG NÓNG: gọi mỗi lượt chat qua build_system_prompt. Tầng 1 là cổng chữ ký stat-only
    (đo thật nguyên hàm trên 3 brain đang chạy: còn khoảng 2-8ms tuỳ brain, không phải một
    con số cố định - xem CHANGELOG 0.9.64) - 99% lượt thoát ở đây. Tầng 2 (copy thật) chỉ
    chạy khi cây nguồn ĐỔI, hoặc khi còn nợ skill copy lỗi lượt trước - lúc đó CHỈ chép lại
    đúng mấy skill nợ đó (_MIRROR_RETRY), nên một skill hỏng vĩnh viễn chỉ tốn rglob của
    RIÊNG nó chứ không phạt cả brain mỗi lượt.

    BIẾT TRƯỚC: chữ ký tính trên NGUỒN và cache nằm trong bộ nhớ, nên bản mirror bị phá từ
    BÊN NGOÀI mà nguồn không đổi sẽ không tự lành cho tới khi khởi động lại tiến trình. Đánh
    đổi có chủ đích (xem spec 2026-07-17-mirror-skills-tree-design.md). Tắt/bật skill THÌ TỰ
    LÀNH: nhánh tắt trong /skills/toggle (main.py) vừa dời nguồn sang .disabled vừa GỌI LẠI
    hàm này ngay tại đó, nên cache ghi nhận đúng chữ ký-đã-tắt NGAY LẬP TỨC - bật lại sau đó
    chắc chắn tính ra chữ ký khác cache và copy lại toàn bộ. (Bản đầu của B4 chỉ dời nguồn mà
    KHÔNG gọi lại hàm này ở nhánh tắt: do `rename` giữ nguyên st_mtime_ns/st_size, bật lại sẽ
    quay về ĐÚNG chữ ký cache còn nhớ từ trước khi tắt, và mirror vừa rmtree không bao giờ
    được tạo lại cho tới khi restart - CRITICAL đã vá, xem test_system_sync.py.)"""
    root = Path(root)
    canonical = root / "skills"
    mirror = root / ".claude" / "skills"
    if not canonical.is_dir():
        return
    try:
        key = str(root.resolve())
    except OSError:
        key = str(root)
    try:
        sig = _mirror_signature(canonical)
        if sig and _MIRROR_SIG.get(key) == sig and not _MIRROR_RETRY.get(key):
            return   # TẦNG 1: cây nguồn không đổi + không nợ skill nào -> khỏi làm gì (99% lượt)
        lk = _mirror_lock(key)
        if not lk.acquire(blocking=False):
            return   # luồng khác đang mirror đúng root này -> nó làm rồi, khỏi xếp hàng
        try:
            # Kiểm lại LẦN NỮA sau khi đã cầm khoá (double-checked locking - lần kiểm THỨ HAI
            # này là LINH HỒN của mẫu đó, thiếu nó thì khoá gần như vô dụng): xin-được-khoá
            # không đồng nghĩa "không ai vừa làm xong việc của mình". Luồng khác có thể đã copy
            # xong + ghi cache SIG rồi mới nhả khoá, đúng lúc ta xin được chính khoá đó (khoá
            # lúc ấy đang RẢNH nên acquire THÀNH CÔNG). Thiếu bước này, 2 luồng cùng thấy "cây
            # đã đổi" ở tầng 1 sẽ CÙNG copy: một luồng copy thật, luồng kia copy LẶP vô ích.
            # DÙNG LẠI ĐÚNG `sig` chụp ở tầng 1, KHÔNG tính lại: `sig` là ẢNH CHỤP mà lượt copy
            # này dựa vào, và chính việc so đúng ảnh chụp đó với cache mới làm re-check ĐÚNG.
            # (Đừng "sửa" thành _mirror_signature(canonical) - nguồn CÓ THỂ đổi giữa chừng do
            # POST /skills ghi xen, tính lại sẽ so nhầm ảnh chụp khác với việc mình sắp làm.)
            pending = _MIRROR_RETRY.get(key)
            if sig and _MIRROR_SIG.get(key) == sig and not pending:
                return
            # Cây KHÔNG đổi mà vẫn vào tới đây => chỉ còn nợ mấy skill lỗi lượt trước: chép ĐÚNG
            # mấy slug đó thôi. Cây ĐỔI thì `only = None` = chép tất (nợ cũ nằm trong đó rồi).
            # Đây là thứ giữ đường nóng khoảng 2-8ms (tuỳ brain) khi có 1 skill hỏng VĨNH VIỄN:
            # nếu cứ "có lỗi thì không cache" thì mọi lượt chat lại full rglob + copy2 CẢ BRAIN -
            # đo thật trên brain GIẢ LẬP dựng riêng để đo (27 skill/135 file, không phải hình
            # dạng của brain thật nào) là 161ms/lượt so với 18ms khi tầng 1 ăn, tức còn TỆ HƠN cả
            # bản ~52ms mà task này sinh ra để giết. Lỗi vĩnh viễn (MAX_PATH trên cây references/
            # sâu dưới đường brain dài, file bị process khác giữ, file vướng ACL) là có thật và
            # không tự khỏi, nên không được phép biến thành thuế mỗi lượt.
            only = pending if (sig and _MIRROR_SIG.get(key) == sig) else None
            failed = set()
            for d in sorted(p for p in canonical.iterdir()
                            if p.is_dir() and p.name != ".disabled"
                            and (only is None or p.name in only)
                            and (p / "SKILL.md").is_file()):
                try:
                    dst_dir = mirror / d.name
                    rels = sorted(p.relative_to(d).as_posix()
                                  for p in d.rglob("*") if p.is_file())
                    for rel in rels:
                        dst_f = dst_dir / rel
                        dst_f.parent.mkdir(parents=True, exist_ok=True)
                        if rel == "SKILL.md":
                            _copy_skill_md_capped(d / rel, dst_f)
                        else:
                            shutil.copy2(str(d / rel), str(dst_f))
                except Exception as e:
                    # 1 skill hỏng KHÔNG chặn các skill còn lại; nhớ TÊN nó để lượt sau thử lại
                    # RIÊNG nó (rglob của đúng 1 skill), thay vì phạt cả brain mỗi lượt.
                    failed.add(d.name)
                    print(f"[skill mirror] {d.name}: {type(e).__name__}: {e}", file=sys.stderr)
            # Ghi cache chữ ký của ẢNH CHỤP mà lượt copy này THỰC SỰ dựa vào (`sig` đọc ở tầng
            # 1), KHÔNG phải chữ ký tính lại lúc này. Nguồn KHÔNG đứng yên suốt lượt copy: POST
            # /skills ghi skill giữa phiên là kịch bản chính mà đường nóng này phục vụ. Nếu
            # nguồn nhảy từ S_cũ sang S_mới giữa chừng, ta vừa chép nội dung của S_cũ; tính lại
            # sẽ cache S_mới -> cache NÓI DỐI rằng mirror đang là S_mới -> tầng 1 thoát vĩnh
            # viễn -> MẤT CẬP NHẬT. Cache đúng ảnh chụp thì xấu nhất chỉ là thừa một lượt copy
            # ở lần gọi sau (an toàn). Đây CŨNG là thứ làm acquire(blocking=False) ở trên hợp
            # lệ: luồng trượt khoá bỏ về vì tin "luồng kia đang làm việc của mình" - niềm tin
            # đó chỉ đúng khi cache ghi lại đúng ảnh chụp mà lượt đó dựa vào.
            # Skill lỗi KHÔNG chặn việc cache nữa (xem trên) - nó được nhớ RIÊNG trong
            # _MIRROR_RETRY nên vẫn được thử lại đều, không cần hy sinh cache của skill lành.
            # GHI _MIRROR_RETRY TRƯỚC _MIRROR_SIG: tầng 1 đọc 2 dict này bằng 2 lệnh riêng
            # (không nguyên tử với nhau). Ghi theo thứ tự này thì luồng nào đã thấy `sig` MỚI
            # chắc chắn cũng thấy danh sách nợ MỚI -> không bỏ sót lượt thử lại.
            if failed:
                _MIRROR_RETRY[key] = failed
            else:
                _MIRROR_RETRY.pop(key, None)
            if sig:
                _MIRROR_SIG[key] = sig
        finally:
            lk.release()
    except Exception as e:
        print(f"[skill mirror] {root}: {type(e).__name__}: {e}", file=sys.stderr)


def _merge_loop_update(new_content: str, cur_text: str) -> str:
    """Update loop nhưng BẢO TOÀN trường trạng thái user đã chỉnh (enabled/mode/interval...)."""
    new_meta, new_body = _split_frontmatter(new_content)
    cur_meta, _ = _split_frontmatter(cur_text)
    for k in _LOOP_VOLATILE_KEYS:
        if k in cur_meta and k != "updated":
            new_meta[k] = cur_meta[k]
    new_meta["updated"] = _today()
    fm = yaml.safe_dump(new_meta, allow_unicode=True, sort_keys=False,
                        default_flow_style=False, width=1000).strip()
    return f"---\n{fm}\n---\n{new_body.lstrip()}" if new_body.strip() else f"---\n{fm}\n---\n"


# ── Cổng chữ ký cho mirror_skills ──────────────────────────────────────────────
# mirror_skills bị gọi ở ĐƯỜNG NÓNG: build_system_prompt (main.py:184) chạy mỗi lượt chat
# dashboard, mỗi tin Telegram, mỗi task Kanban, mỗi vòng loop, mỗi nhắc hẹn, mỗi lần spawn
# learn. Bản cũ đọc + băm SKILL.md hai lần cho MỖI skill mỗi lần gọi: đo thật trên brain
# 27 skill là ~52ms MỖI LƯỢT, chặn thẳng event loop. Chữ ký chỉ dùng stat (không đọc byte
# nào) nên còn khoảng 2-8ms tuỳ brain (đo thật nguyên hàm, không phải suy luận - xem
# CHANGELOG 0.9.64), rẻ hơn khoảng 5 đến 7 lần tuỳ brain chứ không phải một con số cố định,
# và tiện thể phủ luôn thư mục con.
_MIRROR_SIG: dict = {}                    # root đã resolve -> chữ ký lần mirror gần nhất
_MIRROR_RETRY: dict = {}                  # root đã resolve -> set slug copy LỖI, cần thử lại
_MIRROR_LOCKS: dict = {}                  # root đã resolve -> Lock riêng cho mirror
_MIRROR_LOCKS_GUARD = threading.Lock()    # chỉ bảo vệ việc TẠO lock trong _MIRROR_LOCKS
# _MIRROR_SIG và _MIRROR_RETRY KHÔNG cần guard riêng (khác _MIRROR_LOCKS - cái đó phải guard vì
# get-rồi-tạo phải nguyên tử, nếu không 2 luồng đẻ ra 2 Lock khác nhau cho cùng root là hỏng
# hẳn tác dụng khoá). Ở đây mỗi thao tác chỉ là MỘT lệnh dict (get/set/pop) - nguyên tử dưới
# GIL - và mọi lệnh GHI đều nằm trong khoá riêng của root nên không có 2 luồng cùng ghi 1 key.


def _mirror_lock(key: str) -> threading.Lock:
    """Lock riêng theo root cho mirror. TUYỆT ĐỐI không phải _LOCK: mirror_skills bị gọi từ
    sync_brain KHI ĐANG giữ _LOCK, mà threading.Lock không reentrant nên lấy _LOCK ở đây là
    deadlock ngay lượt chat đầu. Lock này chỉ được lấy BÊN TRONG mirror_skills và không có
    lock nào khác bị lấy khi đang giữ nó -> không có chu trình -> không deadlock."""
    with _MIRROR_LOCKS_GUARD:
        lk = _MIRROR_LOCKS.get(key)
        if lk is None:
            lk = threading.Lock()
            _MIRROR_LOCKS[key] = lk
        return lk


def _mirror_signature(canonical: Path) -> str:
    """Chữ ký cây skill, cộng CHỈ bằng stat - KHÔNG đọc nội dung file nào.

    Gộp (đường dẫn tương đối dạng posix, st_mtime_ns, st_size) của MỌI file thành 1 sha256.
    Bỏ qua .disabled (skill đã tắt không được mirror). follow_symlinks=False ở cả is_dir lẫn
    stat: đĩa hiện không có symlink nào, nhưng rglob trên cây có symlink có thể lặp vô hạn.
    Trả chuỗi rỗng nếu thư mục không tồn tại. OSError trên 1 entry -> bỏ qua entry đó, không ném.
    """
    if not canonical.is_dir():
        return ""
    h = hashlib.sha256()
    stack = [canonical]
    rows = []
    while stack:
        d = stack.pop()
        try:
            # context manager BẮT BUỘC: os.scandir giữ file handle của thư mục cho tới khi
            # đóng. Trên Windows, handle hở làm thư mục không xoá/đổi tên được cho tới khi
            # GC dọn - đủ để phá test dùng tempfile và phá cả toggle skill (rmtree mirror).
            with os.scandir(d) as it:
                entries = list(it)
        except OSError:
            continue
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    if e.name != ".disabled":
                        stack.append(Path(e.path))
                    continue
                st = e.stat(follow_symlinks=False)
                rel = Path(e.path).relative_to(canonical).as_posix()
                rows.append(f"{rel}\x00{st.st_mtime_ns}\x00{st.st_size}")
            except OSError:
                continue
    for row in sorted(rows):   # sort để chữ ký không phụ thuộc thứ tự duyệt của OS
        h.update(row.encode("utf-8", "replace"))
        h.update(b"\x01")
    return h.hexdigest()


_LOCK = threading.Lock()
_SYNCED_ROOTS: set = set()


def sync_brain(brain_root) -> dict:
    """Đồng bộ năng lực hệ thống vào 1 brain. Idempotent, an toàn chạy nhiều lần.
    Trả {"ok", "installed": [...], "updated": [...], "kept_user": [...]}."""
    root = Path(brain_root)
    result = {"ok": True, "installed": [], "updated": [], "kept_user": []}
    with _LOCK:
        # (1) Migrate legacy .claude/skills → canonical skills/ TRƯỚC khi cài skill hệ thống,
        #     để skill hệ thống user đã TẮT (đã migrate cả cây .disabled) không bị cài lại BẬT.
        try:
            migrate_brain(root)
        except Exception as e:
            print(f"[system sync] migrate {root}: {type(e).__name__}: {e}", file=sys.stderr)
        # (2) Cài/cập nhật skill + loop hệ thống vào canonical (bỏ qua nếu app không ship item nào).
        items = _system_items()
        manifest = _read_manifest(root)
        files = manifest["files"]
        changed = False
        for key, kind, slug, content, rel in items:
            try:
                hasher = skill_hash if kind == "skill" else loop_hash
                new_hash = hasher(content)
                if kind == "skill":
                    # File con đi THEO thư mục skill: skill đang TẮT thì mọi file của nó nằm trong
                    # .disabled, không phải chỉ mình SKILL.md. Quyết định bật/tắt đọc từ SKILL.md.
                    md_enabled, md_disabled = _skill_paths(root, slug)
                    off = (not md_enabled.exists()) and md_disabled.exists()
                    enabled_p, disabled_p = _skill_paths(root, slug, rel)
                    dst = disabled_p if off else enabled_p
                else:
                    dst = root / "Javis" / "loops" / f"{slug}.md"

                entry = files.get(key) or {}
                if not dst.exists():
                    # Thiếu → cài mới (file hệ thống tự hồi phục; tắt bằng .disabled chứ không xoá)
                    _atomic_write(dst, content)
                    files[key] = {"hash": new_hash, "status": "managed"}
                    result["installed"].append(key)
                    changed = True
                    continue

                cur_text = dst.read_text(encoding="utf-8")
                cur_hash = hasher(cur_text)
                if cur_hash == new_hash:
                    # Đã đúng bản mới nhất → chỉ ghi nhận vào manifest (brain pre-manifest)
                    if entry.get("hash") != new_hash or entry.get("status") != "managed":
                        files[key] = {"hash": new_hash, "status": "managed"}
                        changed = True
                    continue

                prev_hash = entry.get("hash")
                shipped_old = cur_hash == prev_hash or cur_hash in LEGACY_HASHES.get(key, set())
                if shipped_old:
                    # Bản seed cũ CHƯA bị user sửa → update theo phiên bản app
                    if kind == "loop":
                        _atomic_write(dst, _merge_loop_update(content, cur_text))
                    else:
                        _atomic_write(dst, content)
                    files[key] = {"hash": new_hash, "status": "managed"}
                    result["updated"].append(key)
                    changed = True
                else:
                    # User đã sửa → tôn trọng bản của user, app không tự đụng nữa
                    if entry.get("status") != "user-modified":
                        files[key] = {"hash": prev_hash or cur_hash, "status": "user-modified"}
                        changed = True
                    result["kept_user"].append(key)
            except Exception as e:
                print(f"[system sync] {key} @ {root}: {type(e).__name__}: {e}", file=sys.stderr)
                result["ok"] = False
        if changed:
            try:
                _write_manifest(root, manifest)
            except Exception as e:
                print(f"[system sync] ghi manifest {root}: {e}", file=sys.stderr)
        # (3) Mirror canonical skills/ → .claude/skills để Claude native (cwd=brain) nạp được.
        try:
            mirror_skills(root)
        except Exception as e:
            print(f"[system sync] mirror {root}: {type(e).__name__}: {e}", file=sys.stderr)
    return result


def ensure_synced(brain_root) -> Optional[dict]:
    """Sync 1 lần cho mỗi brain root trong vòng đời process (gọi được ở hot path).
    Bao phủ brain ngoài chọn qua 'path:' ngay lượt dùng đầu tiên."""
    try:
        key = str(Path(brain_root).resolve())
    except Exception:
        key = str(brain_root)
    with _LOCK:
        if key in _SYNCED_ROOTS:
            return None
        _SYNCED_ROOTS.add(key)
    try:
        r = sync_brain(brain_root)
        if r.get("installed") or r.get("updated"):
            print(f"[system sync] {brain_root}: cài {len(r['installed'])}, cập nhật {len(r['updated'])}",
                  file=sys.stderr)
        return r
    except Exception as e:
        print(f"[system sync] {brain_root}: {type(e).__name__}: {e}", file=sys.stderr)
        return None


# ────────────────────────── LEGACY_HASHES (dữ liệu) ──────────────────────────
# Hash các bản seed đã ship TRƯỚC khi có manifest (v0.7.9 → v0.8.3; nội dung không đổi giữa
# các bản nên mỗi item 1 hash). Sinh từ git history meta_tools.py (fe33c2c/703fe54/0d3c953/f4fe71c).
LEGACY_HASHES.update({
    "skills/ingest-source": {
        "313675bc61ad2aae69b282e9289a1a126ce89eb7688e1e2bfa3cfa409428878d",
    },
    "skills/javis-builder": {
        "24081f68ed0152b09fc482dc79680e68e249e8153bc1c442f4a01af15b7f012f",
        # bản v0.9.32 (trước khi thêm khung metaprompt v0.9.33)
        "6f040dde409adf27ee69fed22c2c0490a5717c53a640d02d02fd670ee1bbfd76",
        # bản v0.9.70 (trước khi vá I1 final-fix-gd2: mục Loop dạy gõ YAML tay, không gọi
        # javis_schedule; thiếu owner_chat/goal trong template)
        "b399b173c59b4a6c61fdf294944aec06e9cd6cdcd28d02cabaf1cbb424dc844b",
    },
    # ingest-source bản trước contextual-retrieval (v0.9.33) = 313675bc... đã có ở trên
    "skills/lint-wiki": {
        "d12ab25e78405804c378af7ffb13c136d5fd6639cd5140b17231a533704b8bc8",
    },
    "skills/query-wiki": {
        "de1f90fb9094ea7ab66fef95b62f0c8627058599165bb0ba1ae99e40163eb261",
    },
})


if __name__ == "__main__" and "--hash" in sys.argv:
    # In hash chuẩn hoá của bộ file hệ thống HIỆN TẠI - chạy TRƯỚC khi sửa nội dung
    # để thêm vào LEGACY_HASHES của bản sau.
    for key, kind, slug, content, rel in _system_items():
        h = (skill_hash if kind == "skill" else loop_hash)(content)
        print(f"{key}: {h}")
