"""Gom nhóm cho AGENT và WORKFLOW, đúng cách skill đã làm từ lâu.

    python tests/run.py nhom_agent_workflow      (KHÔNG mạng)

Vì sao có việc này: brain dùng vài tháng là có vài chục agent và workflow, mà hai trang đó
chỉ có một danh sách phẳng - tìm bằng mắt. Skill đã có field `group` và cột nhóm; ở đây mở
đúng cơ chế ấy cho hai loại còn lại.

Ba điểm đáng canh, vì cả ba đều hỏng ÂM THẦM:

1. MỘT field cho cả ba loại. Nếu agent gọi là `category` còn skill gọi là `group` thì trang
   Studio, chỉ mục `Javis/index.md` và AI lúc tự tạo năng lực sẽ hiểu khác nhau về cùng một
   thứ, và không có lỗi nào bật lên.

2. File CŨ (viết trước bản này) không có `group`. Nó phải rơi về "Chung" chứ không được biến
   mất khỏi danh sách - người dùng chỉ phát hiện khi agent của họ không còn thấy đâu.

3. Client CŨ không gửi trường `group` lúc lưu. Server phải tự điền "Chung", đừng để
   frontmatter mọc ra `group: None`.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-nhom-state-"))

import main  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

_fails = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten
          + (("  [" + str(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        _fails.append(ten)


main.cfgmod.gate_active = lambda: False   # test không đụng auth thật
# base_url phải là IP: chưa bật cổng đăng nhập thì web_security siết Host để chống
# DNS-rebinding, mà "testserver" mặc định của TestClient không nằm trong allowlist.
client = TestClient(main.app, base_url="http://127.0.0.1")
BRAIN = tempfile.mkdtemp(prefix="javis-nhom-brain-")


def fm(rel):
    """Frontmatter của một file .md trong brain test."""
    return main._read_md(Path(BRAIN) / rel)[0]


def luu(loai, **form):
    """POST /agents hoặc /workflows, trả (phản hồi, frontmatter đã ghi). Slug lấy từ phản hồi
    chứ không tự đoán: _slugify của agent/workflow GIỮ dấu tiếng Việt."""
    r = client.post("/" + loai, data=dict(form, brain=BRAIN))
    slug = (r.json() or {}).get("slug", "")
    return r, fm(f"{loai}/{slug}.md"), slug


# ============================================================
# 1. Lưu qua form: nhóm vào frontmatter, thiếu nhóm thì về "Chung"
# ============================================================
r, meta, slug_ag = luu("agents", name="Viet email", role="Soạn email chăm khách", group="Marketing")
check("POST /agents nhận nhóm", r.status_code == 200 and r.json().get("ok"), r.text[:120])
check("agent: nhóm ghi vào frontmatter", meta.get("group") == "Marketing", meta)

_, meta, _ = luu("agents", name="Khong nhom", role="x")
check("agent: client cũ không gửi group → 'Chung' (không phải None)",
      meta.get("group") == main.NHOM_MAC_DINH, meta)

_, meta, _ = luu("agents", name="Nhom thua dau cach", role="x", group="  Bán hàng  ")
check("agent: nhóm được cắt khoảng trắng thừa (khỏi đẻ 'Bán hàng ' song song)",
      meta.get("group") == "Bán hàng", meta)

_, meta, _ = luu("agents", name="Nhom rong", role="x", group="   ")
check("agent: nhóm toàn khoảng trắng → 'Chung'", meta.get("group") == main.NHOM_MAC_DINH, meta)

r, meta, slug_wf = luu("workflows", name="Nghien cuu roi viet", description="hai bước",
                       steps="[]", group="Nội dung")
check("POST /workflows nhận nhóm", r.status_code == 200 and r.json().get("ok"), r.text[:120])
check("workflow: nhóm ghi vào frontmatter", meta.get("group") == "Nội dung", meta)

_, meta, _ = luu("workflows", name="Chuoi cu", steps="[]")
check("workflow: client cũ không gửi group → 'Chung'",
      meta.get("group") == main.NHOM_MAC_DINH, meta)

# ============================================================
# 2. Đọc danh sách: file CŨ chưa khai nhóm vẫn phải còn trong danh sách
# ============================================================
main._write_md(Path(BRAIN) / "agents" / "agent-cu.md",
               {"type": "agent", "name": "Agent đời cũ", "role": "viết"}, "prompt cũ")
main._write_md(Path(BRAIN) / "workflows" / "wf-cu.md",
               {"type": "workflow", "name": "Chuỗi đời cũ", "status": "off", "steps": []}, "")

ags = {a["slug"]: a for a in main.agents_index(BRAIN)}
wfs = {w["slug"]: w for w in main.workflows_index(BRAIN)}
check("agents_index trả về nhóm", ags[slug_ag]["group"] == "Marketing")
check("agents_index: file cũ chưa có group vẫn hiện, rơi vào 'Chung'",
      ags.get("agent-cu", {}).get("group") == main.NHOM_MAC_DINH)
check("workflows_index trả về nhóm", wfs[slug_wf]["group"] == "Nội dung")
check("workflows_index: file cũ chưa có group vẫn hiện, rơi vào 'Chung'",
      wfs.get("wf-cu", {}).get("group") == main.NHOM_MAC_DINH)

r = client.get(f"/agents?brain={BRAIN}")
check("GET /agents trả kèm group (trang Studio dựng cột nhóm từ đây)",
      all("group" in a for a in r.json()["agents"]))
r = client.get(f"/workflows?brain={BRAIN}")
check("GET /workflows trả kèm group",
      all("group" in w for w in r.json()["workflows"]))

# Sửa một agent rồi lưu lại: nhóm cũ phải giữ nguyên nếu form gửi lên đúng nhóm đó.
_, meta, _ = luu("agents", name="Viet email", role="Soạn email chăm khách",
                 group="Marketing", slug=slug_ag)
check("agent: lưu lại lần hai không làm mất nhóm", meta.get("group") == "Marketing", meta)

# ============================================================
# 3. Chỉ mục Javis/index.md: xếp theo nhóm cho CẢ BA loại
# ============================================================
caps = main._gather_capabilities(BRAIN)
check("caps: agent mang theo nhóm", all("group" in a for a in caps["agents"]))
check("caps: workflow mang theo nhóm", all("group" in w for w in caps["workflows"]))

idx = main._render_javis_index(caps)
check("index: có tiêu đề nhóm của agent", "### Marketing" in idx, idx[:400])
check("index: có tiêu đề nhóm của workflow", "### Nội dung" in idx)
check("index: agent nhóm Chung vẫn được liệt kê", "agent-cu" in idx)

# Brain chỉ có MỘT nhóm thì đừng thêm một tầng tiêu đề vô nghĩa.
mot_nhom = {"agents": [{"slug": "a", "name": "A", "role": "r", "model": "", "skills": [],
                        "group": main.NHOM_MAC_DINH}],
            "skills": [], "workflows": [], "loops": [], "plugins": []}
idx1 = main._render_javis_index(mot_nhom)
check("index: chỉ một nhóm thì không chèn tiêu đề nhóm thừa", "### Chung" not in idx1)

# ============================================================
# 4. Dây nối UI: BA trang dùng CHUNG một khung nhóm
# ============================================================
# Chép khung ra ba bản là ba bản trôi lệch nhau ngay lần sửa đầu (bài học của khối chọn
# skill trong màn sửa Agent - xem tests/js/test_chon_skill_va_phan_trang.js).
sj = (ROOT / "dashboard" / "studio.js").read_text(encoding="utf-8")
check("UI: có khung nhóm dùng chung", "function khungNhomHtml(" in sj and "function locTheoNhom(" in sj)
for trang, oId in (("workflows", "wfSearch"), ("agents", "agSearch"), ("skills", "skSearch")):
    check(f"UI: trang {trang} dùng khung nhóm chung", f'searchId: "{oId}"' in sj)
check("UI: form Agent gửi kèm nhóm", 'box.querySelector("#agGroup")' in sj)
check("UI: form Workflow gửi kèm nhóm", 'box.querySelector("#wfGroup")' in sj)

if _fails:
    print(f"\nFAIL {len(_fails)} muc: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_nhom_agent_workflow: tat ca pass")
