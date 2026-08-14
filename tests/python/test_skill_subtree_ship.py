"""Test: skill HỆ THỐNG phải ship CẢ CÂY CON, không chỉ mỗi SKILL.md. Chạy tay / CI:

    python tests/python/test_skill_subtree_ship.py

Không cần pytest, không chạm mạng.

VÌ SAO CÓ FILE NÀY (lỗi thật đã dẫm phải, mất hẳn một skill): `html-to-webcake` ship kèm
`tools/*.js` và thân skill bảo agent chạy chúng, nhưng `_system_items()` chỉ đọc đúng
`SKILL.md` của mỗi skill - nên cây con CHƯA BAO GIỜ tới brain nào. Skill đó hỏng ở MỌI
brain từ ngày ship (ghi nhận ở 0.9.71), và tới 0.9.291 thì bị gỡ hẳn khỏi bộ skill hệ
thống thay vì được vá. Test này khoá lại hành vi đúng để chuyện đó không tái diễn.

Phủ 5 điểm:
  1. `_system_items()` liệt kê file con của skill hệ thống (không chỉ SKILL.md).
  2. `sync_brain()` GHI THẬT các file con đó xuống brain, đúng cây thư mục.
  3. Khoá manifest của SKILL.md GIỮ NGUYÊN dạng cũ `skills/<slug>` - đổi khoá là mọi brain
     đang chạy tưởng "chưa có mục này" rồi đóng dấu user-modified cho file người dùng chưa
     hề đụng, và skill hệ thống ngừng cập nhật trong im lặng.
  4. Skill đang TẮT (.disabled) thì file con cũng nằm trong .disabled, không rơi ra ngoài
     làm skill tự bật lại.
  5. File con user ĐÃ SỬA thì được giữ, không bị bản của app ghi đè.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import json
import os
import shutil
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-subtree-"))

import system_sync  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def _fake_source(tmp):
    """Dựng một cây skill hệ thống giả (không phụ thuộc skill thật của repo)."""
    src = tmp / "sysskills"
    (src / "demo-skill" / "tools").mkdir(parents=True)
    (src / "demo-skill" / "SKILL.md").write_text(
        "---\nname: Demo\ndescription: demo\n---\nThan skill\n", encoding="utf-8")
    (src / "demo-skill" / "tools" / "run.js").write_text("console.log('v1');\n", encoding="utf-8")
    (src / "demo-skill" / "tools" / "lib.js").write_text("module.exports = 1;\n", encoding="utf-8")
    (src / "demo-skill" / "examples").mkdir()
    (src / "demo-skill" / "examples" / "in.html").write_text("<p>hi</p>\n", encoding="utf-8")
    return src


def main():
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp(prefix="javis-subtree-run-"))
    try:
        src = _fake_source(tmp)
        system_sync.SYSTEM_SKILLS_DIR = src
        system_sync.SYSTEM_LOOPS_DIR = tmp / "noloops"
        system_sync._SKILL_SLUGS_CACHE = None

        # ── 1. liệt kê ────────────────────────────────────────────────────────────
        items = system_sync._system_items()
        keys = {it[0] for it in items}
        check("1. liet ke ca SKILL.md lan file con",
              keys == {"skills/demo-skill", "skills/demo-skill/tools/run.js",
                       "skills/demo-skill/tools/lib.js", "skills/demo-skill/examples/in.html"})
        check("1b. moi item co du 5 truong (key, kind, slug, noi dung, duong dan con)",
              all(len(it) == 5 for it in items))

        # ── 2 + 3. cài vào brain trống ────────────────────────────────────────────
        brain = tmp / "brain1"
        brain.mkdir()
        system_sync._SYNCED_ROOTS.clear()
        res = system_sync.sync_brain(brain)
        sk = brain / "skills" / "demo-skill"
        check("2. SKILL.md duoc cai", (sk / "SKILL.md").is_file())
        check("2b. tools/run.js duoc cai", (sk / "tools" / "run.js").is_file())
        check("2c. tools/lib.js duoc cai", (sk / "tools" / "lib.js").is_file())
        check("2d. examples/in.html duoc cai", (sk / "examples" / "in.html").is_file())
        check("2e. noi dung file con dung",
              (sk / "tools" / "run.js").read_text(encoding="utf-8").strip() == "console.log('v1');")
        check("2f. bao cao installed du 4 muc", len(res["installed"]) == 4)

        man = json.loads((brain / ".javis" / "system-manifest.json").read_text(encoding="utf-8"))
        check("3. khoa manifest cua SKILL.md GIU nguyen dang cu 'skills/<slug>'",
              "skills/demo-skill" in man["files"] and "skills/demo-skill/SKILL.md" not in man["files"])
        check("3b. file con co khoa rieng", "skills/demo-skill/tools/run.js" in man["files"])

        # chạy lại: idempotent, không cài lại gì
        res2 = system_sync.sync_brain(brain)
        check("3c. chay lai khong cai lai gi",
              not res2["installed"] and not res2["updated"])

        # ── cập nhật theo phiên bản app ───────────────────────────────────────────
        (src / "demo-skill" / "tools" / "run.js").write_text("console.log('v2');\n", encoding="utf-8")
        res3 = system_sync.sync_brain(brain)
        check("3d. file con chua bi sua thi duoc cap nhat theo app",
              "skills/demo-skill/tools/run.js" in res3["updated"]
              and "v2" in (sk / "tools" / "run.js").read_text(encoding="utf-8"))

        # ── 5. user sửa file con → giữ nguyên ─────────────────────────────────────
        (sk / "tools" / "lib.js").write_text("module.exports = 'CUA USER';\n", encoding="utf-8")
        (src / "demo-skill" / "tools" / "lib.js").write_text("module.exports = 2;\n", encoding="utf-8")
        res4 = system_sync.sync_brain(brain)
        check("5. file con user da sua thi KHONG bi ghi de",
              "CUA USER" in (sk / "tools" / "lib.js").read_text(encoding="utf-8")
              and "skills/demo-skill/tools/lib.js" in res4["kept_user"])

        # ── 4. skill đang TẮT: file con nằm trong .disabled ───────────────────────
        brain2 = tmp / "brain2"
        (brain2 / "skills" / ".disabled" / "demo-skill").mkdir(parents=True)
        (brain2 / "skills" / ".disabled" / "demo-skill" / "SKILL.md").write_text(
            "---\nname: Demo\ndescription: demo\n---\nThan skill\n", encoding="utf-8")
        system_sync.sync_brain(brain2)
        off = brain2 / "skills" / ".disabled" / "demo-skill"
        check("4. skill TAT: file con vao .disabled", (off / "tools" / "run.js").is_file())
        check("4b. skill TAT: KHONG tao cay bat song song",
              not (brain2 / "skills" / "demo-skill").exists())

        # ── mirror sang .claude/skills mang theo cây con ──────────────────────────
        system_sync.mirror_skills(brain)
        mir = brain / ".claude" / "skills" / "demo-skill"
        check("6. mirror sang .claude/skills mang ca cay con",
              (mir / "SKILL.md").is_file() and (mir / "tools" / "run.js").is_file())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if _fails:
        print(f"{len(_fails)} test FAIL: " + ", ".join(_fails))
        sys.exit(1)
    print("Tat ca test PASS")


if __name__ == "__main__":
    main()
