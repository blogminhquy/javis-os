"""Ghim và chuyển nhóm agent/workflow. Chạy tay / CI:

    python tests/run.py ghim_chuyen_nhom

Chủ dự án yêu cầu (16/09): mỗi dòng trong danh sách Trợ lý và Quy trình cần bốn động tác để
quản lý được một brain có vài chục cộng sự: ghim, chuyển vào thư mục (nhóm), sửa, xoá.

Hai động tác đầu ghi vào frontmatter, nên phải có một đường riêng. Vì sao KHÔNG dùng
`POST /agents` và `POST /workflows`: hai endpoint đó nhận TOÀN BỘ nội dung (prompt, skills,
steps) và ghi lại cả file - ghim một agent mà phải gửi lại nguyên prompt của nó là mời gọi mất
dữ liệu. `POST /capability/meta` đọc file, sửa đúng khoá được nêu, rồi ghi lại.

Phủ:
- ghim / bỏ ghim (bỏ ghim phải XOÁ khoá, không để lại `pinned: false`);
- chuyển nhóm, nhóm rỗng về mặc định;
- KHÔNG đụng tới phần nội dung (prompt, steps) và các khoá khác;
- kind lạ / slug không tồn tại -> lỗi rõ, không tạo file mới;
- `pinned` đi ra index để danh sách xếp được;
- lưu qua trình sửa KHÔNG được xoá mất cái ghim (khoá lạ phải sống sót).

KHÔNG chạm mạng.
KHÔNG dùng ký tự em dash.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-ghim-"))

import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


BRAIN = tempfile.mkdtemp(prefix="javis-brain-ghim-")
(Path(BRAIN) / "agents").mkdir(parents=True, exist_ok=True)
(Path(BRAIN) / "workflows").mkdir(parents=True, exist_ok=True)

_AG = Path(BRAIN) / "agents" / "nguoi-viet.md"
_AG.write_text(
    "---\ntype: agent\nname: Người viết\nslug: nguoi-viet\nrole: viết bài\n"
    "group: Marketing\nskills:\n  - viet-email\nmodel: claude-sonnet-4\n---\n"
    "Bạn là người viết bài. Giữ giọng gần gũi.\n", encoding="utf-8")
_WF = Path(BRAIN) / "workflows" / "viet-bai.md"
_WF.write_text(
    "---\ntype: workflow\nname: Viết bài\nslug: viet-bai\nstatus: active\ngroup: Content\n"
    "steps:\n  - agent: nguoi-viet\n    task: viết bản thảo\n---\nmô tả quy trình\n",
    encoding="utf-8")


def meta(kind, slug, pinned=None, group=None):
    """Gọi endpoint như FastAPI gọi nó: khoá không gửi là None, KHÔNG phải object Form(...).

    Gọi thẳng một hàm FastAPI trong test thì tham số mặc định vẫn là `Form(...)` (truthy) nên
    nhánh "không gửi thì không đụng" sẽ hiểu sai - endpoint đã quy về None, đây là vế còn lại
    của cùng một bài học."""
    return asyncio.run(main.capability_meta(kind=kind, slug=slug, brain=BRAIN,
                                            pinned=pinned, group=group))


def doc(f):
    return main._read_md(f)


# ---------------------------------------------------------------- 1. Ghim / bỏ ghim
r = meta("agent", "nguoi-viet", pinned="1")
check("ghim agent: trả ok kèm trạng thái", r.get("ok") and r.get("pinned") is True)
check("ghim ghi vào frontmatter", doc(_AG)[0].get("pinned") is True)
check("ghim KHÔNG đụng vào thân file (prompt còn nguyên)",
      "Bạn là người viết bài" in doc(_AG)[1])
check("ghim KHÔNG đụng các khoá khác", doc(_AG)[0].get("role") == "viết bài"
      and doc(_AG)[0].get("skills") == ["viet-email"]
      and doc(_AG)[0].get("model") == "claude-sonnet-4")
check("ghim KHÔNG đổi nhóm", doc(_AG)[0].get("group") == "Marketing")

r = meta("agent", "nguoi-viet", pinned="0")
check("bỏ ghim: XOÁ khoá chứ không để lại pinned: false",
      r.get("pinned") is False and "pinned" not in doc(_AG)[0])

check("ghim workflow cũng được", meta("workflow", "viet-bai", pinned="true").get("pinned") is True)
check("ghim workflow không đụng steps",
      len(doc(_WF)[0].get("steps") or []) == 1 and doc(_WF)[0]["steps"][0]["agent"] == "nguoi-viet")

# ---------------------------------------------------------------- 2. Chuyển nhóm
r = meta("agent", "nguoi-viet", group="Sales")
check("chuyển nhóm agent", r.get("group") == "Sales" and doc(_AG)[0].get("group") == "Sales")
check("chuyển nhóm không đụng thân file", "Bạn là người viết bài" in doc(_AG)[1])
r = meta("agent", "nguoi-viet", group="   ")
check("nhóm rỗng thì về nhóm mặc định", doc(_AG)[0].get("group") == main.NHOM_MAC_DINH)
r = meta("workflow", "viet-bai", group="Operations")
check("chuyển nhóm workflow", doc(_WF)[0].get("group") == "Operations")

# Gửi CẢ HAI cùng lúc cũng phải được (menu có thể gộp một lượt).
meta("agent", "nguoi-viet", pinned="1", group="Content")
check("gửi cùng lúc ghim + nhóm", doc(_AG)[0].get("pinned") is True
      and doc(_AG)[0].get("group") == "Content")

# KHÔNG gửi khoá nào thì KHÔNG đụng khoá đó.
meta("agent", "nguoi-viet", group="Content")
check("không gửi `pinned` thì cái ghim còn nguyên", doc(_AG)[0].get("pinned") is True)

# ---------------------------------------------------------------- 3. Đầu vào sai
r = meta("agent", "khong-co-that", pinned="1")
check("slug không tồn tại: lỗi 404, KHÔNG tạo file mới",
      getattr(r, "status_code", 0) == 404
      and not (Path(BRAIN) / "agents" / "khong-co-that.md").exists())
r = meta("skill", "nguoi-viet", pinned="1")
check("kind lạ: lỗi 400", getattr(r, "status_code", 0) == 400)

# ---------------------------------------------------------------- 4. pinned ra tới index
ags = main.agents_index(BRAIN)
wfs = main.workflows_index(BRAIN)
check("agents_index trả pinned (danh sách mới xếp được)",
      ags and ags[0]["slug"] == "nguoi-viet" and ags[0]["pinned"] is True)
check("workflows_index trả pinned",
      wfs and wfs[0]["slug"] == "viet-bai" and wfs[0]["pinned"] is True)

# ---------------------------------------------------------------- 5. Lưu qua trình sửa KHÔNG xoá ghim
# Đây là cái bẫy thật: save_agent/save_workflow trước đây dựng lại meta TỪ ĐẦU bằng các field
# của form, nên mỗi lần bấm Lưu là mọi khoá do chỗ khác ghi bị xoá sạch - ghim xong sửa một
# chữ trong prompt là mất ghim, không có gì báo.
# Truyền ĐỦ mọi tham số: cùng bài học Form(...) ở trên, thiếu một cái là nó vào hàm dưới dạng
# object chứ không phải chuỗi.
asyncio.run(main.save_agent(name="Người viết", role="viết bài", skills="viet-email",
                            model="claude-sonnet-4", slug="nguoi-viet",
                            prompt="Bạn là người viết bài. Giữ giọng gần gũi.",
                            brain=BRAIN, model_provider="", group="Content",
                            avatar_shape=None, avatar_palette=None))
check("lưu agent qua trình sửa: cái ghim còn nguyên", doc(_AG)[0].get("pinned") is True)
asyncio.run(main.save_workflow(name="Viết bài", description="mô tả quy trình",
                               steps='[{"agent": "nguoi-viet", "task": "viết bản thảo"}]',
                               status="active", slug="viet-bai", brain=BRAIN, group="Operations"))
check("lưu workflow qua trình sửa: cái ghim còn nguyên", doc(_WF)[0].get("pinned") is True)

if _fails:
    print(f"\nFAIL {len(_fails)} muc: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_ghim_chuyen_nhom: tat ca pass")
