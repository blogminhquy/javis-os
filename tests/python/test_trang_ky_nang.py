"""Trang Kỹ năng 0.75.0: xuất mang đi nơi khác được, nhập từ nơi khác vào đủ.

    python tests/run.py trang_ky_nang      (KHÔNG mạng)

Chủ repo 05/10/2026: "nhiều khi người ta import skill ra chỗ khác thì nó bị khó". Hai chiều:
  1. XUẤT: gói skill phải là cấu trúc chuẩn skills/<slug>/SKILL.md, giải nén vào .claude là
     Claude Code thấy ngay (nên trang không cần ô chọn định dạng).
  2. NHẬP: một .zip có NHIỀU thư mục skill cùng cấp (nén nguyên thư mục skills của công cụ
     khác) trước đây chỉ vào được skill đầu tiên, phần còn lại mất im lặng.
Kèm: trần mô tả 150 ký tự của trang (studio.js) phải bằng trần của router.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import io
import re
import sys
import tempfile
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import share_bundle  # noqa: E402
import skill_router  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        _fails.append(name)


def zip_of(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for arc, text in files.items():
            z.writestr(arc, text)
    return buf.getvalue()


def brain(td):
    ag, wf, sk = Path(td) / "agents", Path(td) / "workflows", Path(td) / "skills"
    for d in (ag, wf, sk):
        d.mkdir(parents=True, exist_ok=True)
    return dict(agents_dir=ag, workflows_dir=wf, skills_root=sk)


def nhap(files, **kw):
    td = tempfile.mkdtemp(prefix="javis-kynang-")
    dirs = brain(td)
    res = share_bundle.import_bundle(zip_of(files), "goi.zip", **dirs, **kw)
    return res, dirs["skills_root"]


SK = lambda ten, them="": f"---\nname: {ten}\ndescription: mô tả {ten}\n---\n# {ten}\n{them}"

# ---- 1. Nhiều thư mục skill cùng cấp → nhập ĐỦ ----
res, sk = nhap({
    "viet-email/SKILL.md": SK("Viết email"),
    "viet-email/mau/thu.md": "mẫu thư",
    "chot-don/SKILL.md": SK("Chốt đơn"),
    "tom-tat/SKILL.md": SK("Tóm tắt"),
    "__MACOSX/viet-email/._SKILL.md": "rác mac",
})
check("CANARY: gói 3 thư mục skill nhập đủ 3", sorted(res["imported"]) == ["skill:chot-don", "skill:tom-tat", "skill:viet-email"],
      res)
check("không lỗi", not res["errors"], res["errors"])
check("file phụ của skill đi theo đúng thư mục", (sk / "viet-email" / "mau" / "thu.md").read_text(encoding="utf-8") == "mẫu thư")
check("rác __MACOSX không thành skill", not any("macosx" in p.name.lower() for p in sk.iterdir()))

# ---- 2. Nằm trong một thư mục bọc ngoài (nén nguyên thư mục skills) ----
res, sk = nhap({"skills/a-b/SKILL.md": SK("Alpha"), "skills/c-d/SKILL.md": SK("Beta")})
check("gói có thư mục skills/ bọc ngoài vẫn nhập đủ", (sk / "a-b" / "SKILL.md").is_file() and (sk / "c-d" / "SKILL.md").is_file(),
      sorted(p.name for p in sk.iterdir()))
res, sk = nhap({"bo-skill/x/SKILL.md": SK("Xa"), "bo-skill/y/SKILL.md": SK("Yen")})
check("thư mục bọc ngoài tên bất kỳ cũng nhập đủ", sorted(res["imported"]) == ["skill:xa", "skill:yen"], res)

# ---- 3. Giữ hành vi cũ ----
res, sk = nhap({"SKILL.md": SK("Một mình"), "tham-khao.md": "phụ"})
check("SKILL.md ở gốc gói = MỘT skill, kèm file phụ", res["imported"] == ["skill:mot-minh"]
      and (sk / "mot-minh" / "tham-khao.md").is_file(), res)
res, sk = nhap({"cha/SKILL.md": SK("Cha"), "cha/vi-du/SKILL.md": SK("Con")})
check("SKILL.md nằm SÂU hơn thuộc về thư mục cha, không tách thành skill riêng",
      res["imported"] == ["skill:cha"] and (sk / "cha" / "vi-du" / "SKILL.md").is_file(), res)
res, sk = nhap({"a/SKILL.md": "không frontmatter", "b/SKILL.md": SK("Bê")})
check("skill không có 'name' lấy tên thư mục, không làm hỏng skill bên cạnh",
      sorted(res["imported"]) == ["skill:a", "skill:be"], res)

# ---- 4. Trùng tên: bỏ qua đúng cái trùng, vẫn nhập cái mới ----
td = tempfile.mkdtemp(prefix="javis-kynang-")
dirs = brain(td)
(dirs["skills_root"] / "viet-email").mkdir()
(dirs["skills_root"] / "viet-email" / "SKILL.md").write_text(SK("Viết email", "bản cũ"), encoding="utf-8")
res = share_bundle.import_bundle(zip_of({"viet-email/SKILL.md": SK("Viết email", "bản mới"),
                                         "chot-don/SKILL.md": SK("Chốt đơn")}), "g.zip", **dirs)
check("trùng thì bỏ qua cái trùng, cái mới vẫn vào", res["skipped"] == ["skill:viet-email"]
      and res["imported"] == ["skill:chot-don"], res)
check("bản cũ không bị ghi đè khi không tick ghi đè",
      "bản cũ" in (dirs["skills_root"] / "viet-email" / "SKILL.md").read_text(encoding="utf-8"))

# ---- 5. Xuất skill = cấu trúc chuẩn, vòng tròn xuất → nhập ----
td = tempfile.mkdtemp(prefix="javis-kynang-")
dirs = brain(td)
for slug, ten in (("viet-email", "Viết email"), ("chot-don", "Chốt đơn")):
    (dirs["skills_root"] / slug).mkdir()
    (dirs["skills_root"] / slug / "SKILL.md").write_text(SK(ten), encoding="utf-8")
data, fname = share_bundle.build_bundle("skill", ["viet-email", "chot-don"], **dirs)
ten_file = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
check("gói xuất có cấu trúc chuẩn skills/<slug>/SKILL.md (giải nén vào .claude là dùng được)",
      {"skills/viet-email/SKILL.md", "skills/chot-don/SKILL.md"} <= ten_file, ten_file)
res, sk = nhap({k: zipfile.ZipFile(io.BytesIO(data)).read(k).decode("utf-8") for k in ten_file})
check("gói xuất nhập lại vào brain khác đủ cả hai", sorted(res["imported"]) == ["skill:chot-don", "skill:viet-email"], res)

# ---- 6. Trần mô tả của trang = trần của router ----
sj = (ROOT / "dashboard" / "studio.js").read_text(encoding="utf-8")
m = re.search(r"const SKILL_DESC_MAX = (\d+);", sj)
check("studio.js khai trần mô tả", bool(m))
check("CANARY: trần mô tả ở trang bằng skill_router.SKILL_DESC_MAX",
      bool(m) and int(m.group(1)) == skill_router.SKILL_DESC_MAX, m and m.group(1))
check("server vẫn từ chối mô tả quá trần (form chỉ báo trước, không thay chốt chặn)",
      skill_router.validate_description("x" * (skill_router.SKILL_DESC_MAX + 1)) is not None
      and skill_router.validate_description("x" * skill_router.SKILL_DESC_MAX) is None)

if _fails:
    print(f"\nFAIL {len(_fails)} muc: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_trang_ky_nang: tat ca pass")
