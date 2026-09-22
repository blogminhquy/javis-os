"""Danh sách trợ lý KHÔNG kéo theo system prompt của từng người.

    python tests/run.py agents_danh_sach_nhe

Chủ dự án báo 22/09/2026: mở trang Cộng sự bằng menu linh vật vẫn lag, trong khi đổi brain
và đổi qua lại giữa các trợ lý thì không. Khác nhau đúng một chỗ: hai đường kia dùng lại danh
sách đã nằm sẵn trong bộ nhớ, còn đường linh vật dựng trang NGUỘI nên phải gọi GET /agents.

Đo trên một brain 14 trợ lý prompt cỡ thật: 366 KB. Bỏ system prompt ra thì còn 2.9 KB, tức
99% số byte là thứ cột trái KHÔNG BAO GIỜ hiện - nó chỉ vẽ tên, vai trò, nhóm, avatar. Trên
máy dev chạy localhost thì 366 KB không thấy gì; qua mạng nhà là cả giây cột trái trống trơn.

Prompt vẫn phải lấy được, nhưng chỉ cho ĐÚNG trợ lý đang mở trong trình sửa: GET /agents/get.

Một cái bẫy phải khoá luôn: mặc định của GET /agents vẫn PHẢI kèm prompt. Dashboard cũ còn
trong cache trình duyệt đọc `prompt` từ chính danh sách này để đổ vào ô sửa, trả rỗng cho nó
là người dùng bấm Lưu một cái mất trắng prompt.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import pathlib
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-agnhe-")

import main  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


BRAIN = pathlib.Path(tempfile.mkdtemp(prefix="javis-brain-agnhe-"))
(BRAIN / "agents").mkdir(parents=True)
PROMPT = ("Bạn là trợ lý chuyên trách. " * 120 + "\n") * 6
for i in range(14):
    (BRAIN / "agents" / f"tro-ly-{i}.md").write_text(
        f"---\ntype: agent\nname: Trợ lý {i}\nslug: tro-ly-{i}\nrole: vai {i}\n"
        f"group: Nhóm {i % 4}\n---\n{PROMPT}", encoding="utf-8")

# ---- 1. Lõi thuần: cờ kem_prompt ----
day = main.agents_index(str(BRAIN))
nhe = main.agents_index(str(BRAIN), kem_prompt=False)
check("mặc định vẫn kèm prompt", all("prompt" in a for a in day))
check("kem_prompt=False bỏ hẳn khoá prompt", all("prompt" not in a for a in nhe))
check("bỏ prompt KHÔNG làm mất thứ cột trái cần",
      all(set(a) == {"slug", "name", "role", "skills", "model", "group",
                     "model_provider", "pinned", "avatar", "last_chat_at"} for a in nhe))

_so = lambda ds: len(json.dumps({"agents": ds}, ensure_ascii=False).encode())  # noqa: E731
check(f"bản nhẹ nhỏ hơn 5% bản đầy ({_so(nhe)} / {_so(day)} byte)", _so(nhe) < _so(day) * 0.05)

# ---- 2. Qua HTTP ----
from fastapi.testclient import TestClient  # noqa: E402
from urllib.parse import quote  # noqa: E402

# base_url phải là host được web_security cho phép, nếu không mọi lời gọi ăn 403.
c = TestClient(main.app, base_url="http://127.0.0.1:8080")
q = quote(str(BRAIN), safe="")

r = c.get(f"/agents?brain={q}")
check("GET /agents không tham số: GIỮ prompt (dashboard cũ trong cache vẫn đọc nó)",
      r.status_code == 200 and "prompt" in r.json()["agents"][0])
r0 = c.get(f"/agents?brain={q}&prompt=0")
check("GET /agents?prompt=0: bỏ prompt",
      r0.status_code == 200 and "prompt" not in r0.json()["agents"][0])
check("và nhẹ hơn hẳn", len(r0.content) < len(r.content) * 0.05)

g = c.get(f"/agents/get?slug=tro-ly-3&brain={q}")
check("GET /agents/get trả đúng trợ lý kèm prompt đầy đủ",
      g.status_code == 200 and g.json().get("name") == "Trợ lý 3"
      and g.json().get("prompt", "").startswith("Bạn là trợ lý"))
check("mọi khoá của bản nhẹ (trừ last_chat_at) đều có trong /agents/get, để trình sửa ghép được",
      set(r0.json()["agents"][0]) - {"last_chat_at"} <= set(g.json()))
check("trợ lý không có: 404 chứ không phải 200 rỗng",
      c.get(f"/agents/get?slug=khong-co-dau&brain={q}").status_code == 404)
# slug đi từ URL thẳng vào tên file, nên đây là cửa đọc file ngoài thư mục agents.
check("slug leo thư mục bị chặn",
      c.get(f"/agents/get?slug=../../../etc/passwd&brain={q}").status_code == 404)

print()
sys.exit(1 if fails else 0)
