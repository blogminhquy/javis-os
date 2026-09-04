"""Gói mang theo agent, workflow, skill: ghi vào brain nhưng KHÔNG BAO GIỜ xoá công của người dùng.

    python tests/run.py goi_vao_brain

Không cần pytest, không chạm mạng, không đụng brain thật.

Vì sao ba thứ này cần một test riêng, tách khỏi connector và plugin: connector và plugin của gói
nằm TRONG thư mục gói, gỡ là rmtree và không ai mất gì. Agent, workflow và skill thì sống trong
BRAIN của người dùng, và brain là nơi họ SỬA.

Nên toàn bộ test này xoay quanh đúng một câu hỏi: **có bao giờ Javis xoá hay ghi đè thứ người
dùng viết không.** Trả lời sai câu đó là loại lỗi tệ nhất một trình cài có thể gây ra - gói cài
lại được trong ba giây, còn thứ họ viết thì không.

Ba luật, và test canh cả ba:

1. Cài KHÔNG ghi đè một mục đã có mà gói không phải người đặt vào đó.
2. Cập nhật chỉ ghi đè khi mục còn Y NGUYÊN như lúc gói đặt vào.
3. Gỡ chỉ xoá mục còn y nguyên; đã sửa thì GIỮ LẠI và nói ra.

Kèm hai phần nhỏ đi cùng đợt: token cho kho riêng (mã hoá khi ghi, đi bằng header, và RƠI khi
chuyển hướng sang host khác) và nhãn nguồn chính chủ / cộng đồng.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import json
import sys
import tempfile
from pathlib import Path

import pack_vault as pv

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def dung_goi(goc: Path, agent="tro-ly", skill="viet-email", noi_dung="Nội dung gốc"):
    (goc / "agents").mkdir(parents=True, exist_ok=True)
    (goc / "workflows").mkdir(parents=True, exist_ok=True)
    (goc / "skills" / skill).mkdir(parents=True, exist_ok=True)
    (goc / "agents" / f"{agent}.md").write_text(
        f"---\ntype: agent\nname: Trợ lý\n---\n{noi_dung}\n", encoding="utf-8")
    (goc / "workflows" / "quy-trinh.md").write_text(
        f"---\nname: Quy trình\nstatus: active\n---\n{noi_dung}\n", encoding="utf-8")
    (goc / "skills" / skill / "SKILL.md").write_text(
        "---\nname: Viết email\ndescription: Soạn thư\n---\nHướng dẫn\n", encoding="utf-8")
    return goc


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    goc_so = pv.HIEU_UNG_DIR
    pv.HIEU_UNG_DIR = tmp / "packs-state"
    try:
        goi = dung_goi(tmp / "goi")
        brain = tmp / "brain"
        brain.mkdir()

        # ─────────────── 1. Cài lần đầu ───────────────
        ds = pv.liet_ke(goi)
        check("đọc được năng lực gói mang theo",
              ds["agents"] == ["tro-ly"] and ds["skills"] == ["viet-email"]
              and ds["workflows"] == ["quy-trinh"])
        ke = pv.ke_hoach_cai(goi, str(brain))
        check("kế hoạch cài nêu đủ 3 mục sẽ thêm", len(ke["them"]) == 3)
        check("và không có xung đột trên brain rỗng", not ke["xung_dot"])

        b = pv.cai("acme.x", goi, str(brain))
        check("cài xong 3 mục", len(b["them"]) == 3 and not b["loi"])
        check("agent nằm đúng chỗ trong brain", (brain / "agents" / "tro-ly.md").is_file())
        check("workflow nằm đúng chỗ", (brain / "workflows" / "quy-trinh.md").is_file())
        check("skill là cả thư mục", (brain / "skills" / "viet-email" / "SKILL.md").is_file())
        check("sổ hiệu ứng ghi lại brain đã ghi vào",
              pv.doc_so("acme.x").get("brain") == str(brain))

        # ─────────────── 2. Cập nhật: chỉ ghi đè thứ chưa ai sửa ───────────────
        goi2 = dung_goi(tmp / "goi2", noi_dung="Nội dung MỚI của gói")
        b2 = pv.cai("acme.x", goi2, str(brain))
        check("bản mới ghi đè được mục người dùng chưa sửa", len(b2["cap_nhat"]) == 3)
        check("và nội dung đúng là bản mới",
              "MỚI" in (brain / "agents" / "tro-ly.md").read_text(encoding="utf-8"))

        # Người dùng sửa agent -> bản mới KHÔNG được đụng vào.
        (brain / "agents" / "tro-ly.md").write_text(
            "---\ntype: agent\n---\nTÔI TỰ SỬA CÁI NÀY\n", encoding="utf-8")
        goi3 = dung_goi(tmp / "goi3", noi_dung="Bản gói lần ba")
        b3 = pv.cai("acme.x", goi3, str(brain))
        check("mục người dùng ĐÃ SỬA thì bản mới bỏ qua",
              any("bạn đã sửa" in x["vi_sao"] for x in b3["bo_qua"]))
        check("và nội dung người dùng còn nguyên",
              "TÔI TỰ SỬA" in (brain / "agents" / "tro-ly.md").read_text(encoding="utf-8"))
        check("nhưng mục chưa sửa vẫn cập nhật bình thường",
              "lần ba" in (brain / "workflows" / "quy-trinh.md").read_text(encoding="utf-8"))

        # ─────────────── 3. Gỡ: chỉ xoá thứ còn y nguyên ───────────────
        ke_go = pv.ke_hoach_go("acme.x")
        check("kế hoạch gỡ tách rõ xoá và giữ",
              len(ke_go["xoa"]) == 2 and len(ke_go["giu"]) == 1)
        check("và giữ đúng cái người dùng đã sửa",
              ke_go["giu"][0]["slug"] == "tro-ly")

        g = pv.go("acme.x")
        check("gỡ xoá 2 mục chưa sửa", len(g["da_xoa"]) == 2)
        check("và GIỮ LẠI mục người dùng đã sửa", g["giu_lai"] == ["agents/tro-ly"])
        check("agent người dùng sửa vẫn còn trên đĩa",
              (brain / "agents" / "tro-ly.md").is_file())
        check("skill chưa sửa đã biến mất", not (brain / "skills" / "viet-email").exists())
        check("sổ hiệu ứng được dọn", not pv.doc_so("acme.x"))

        # ─────────────── 4. Brain đã có mục trùng tên thì gói KHÔNG được ghi đè ───────────────
        brain2 = tmp / "brain2"
        (brain2 / "agents").mkdir(parents=True)
        (brain2 / "agents" / "tro-ly.md").write_text("CỦA NGƯỜI DÙNG\n", encoding="utf-8")
        b4 = pv.cai("acme.y", goi, str(brain2))
        check("gói KHÔNG ghi đè mục brain đã có sẵn",
              any("đã có mục cùng tên" in x["vi_sao"] for x in b4["bo_qua"]))
        check("tệp của người dùng còn nguyên",
              "CỦA NGƯỜI DÙNG" in (brain2 / "agents" / "tro-ly.md").read_text(encoding="utf-8"))
        check("nhưng mục không trùng vẫn cài được", len(b4["them"]) == 2)
        g4 = pv.go("acme.y")
        check("gỡ không đụng tệp của người dùng",
              "agents/tro-ly" not in g4["da_xoa"]
              and (brain2 / "agents" / "tro-ly.md").is_file())

        # ─────────────── 5. Khác xuống dòng KHÔNG bị hiểu là đã sửa ───────────────
        # Ca đã cắn ở chỗ khác: trình soạn thảo Windows lưu lại một tệp là đổi mọi byte xuống
        # dòng. Nếu hash không chuẩn hoá thì mọi người dùng Windows mở tệp ra xem là gói tự
        # coi như "đã sửa" và thôi cập nhật.
        brain3 = tmp / "brain3"
        brain3.mkdir()
        pv.cai("acme.z", goi, str(brain3))
        p = brain3 / "agents" / "tro-ly.md"
        # Chuẩn hoá về LF trước rồi mới đổi sang CRLF: tệp gói ghi ra trên Windows CÓ THỂ đã là
        # CRLF sẵn, thay thẳng thì ra CR CR LF, và đó không phải ca đang muốn đo.
        p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        ke5 = pv.ke_hoach_go("acme.z")
        check("đổi xuống dòng KHÔNG bị coi là người dùng đã sửa",
              any(x["slug"] == "tro-ly" for x in ke5["xoa"]))
        pv.go("acme.z")
    finally:
        pv.HIEU_UNG_DIR = goc_so

# ─────────────── 6. Token cho kho riêng ───────────────
import config as cfgmod  # noqa: E402
import packs_fetch  # noqa: E402

check("packs.tokens nằm trong danh sách trường được mã hoá",
      "packs.tokens.*" in cfgmod._SECRET_PATHS)
check("bộ duyệt secret hiểu dấu *",
      [k for _p, k in cfgmod._secret_keys({"packs": {"tokens": {"a.dev": "x", "b.dev": "y"}}},
                                          "packs.tokens.*")] == ["a.dev", "b.dev"])
check("đường không có * vẫn chạy như cũ",
      cfgmod._secret_keys({"model": {"openrouter_key": "k"}}, "model.openrouter_key")[0][1]
      == "openrouter_key")

goc_doc = cfgmod.read_settings
try:
    cfgmod.read_settings = lambda: {"packs": {"tokens": {"github.com": "tk1",
                                                        "gitlab.com": "tk2"}}}
    check("token tra đúng theo tên máy",
          packs_fetch.token_cho("https://github.com/a/b.zip") == "tk1")
    check("tên máy khác thì không có token",
          packs_fetch.token_cho("https://khac.dev/x.zip") == "")
    check("GitHub dùng header Authorization",
          packs_fetch.header_xac_thuc("https://github.com/a") == {"Authorization": "Bearer tk1"})
    check("GitLab dùng header PRIVATE-TOKEN",
          packs_fetch.header_xac_thuc("https://gitlab.com/a") == {"PRIVATE-TOKEN": "tk2"})
finally:
    cfgmod.read_settings = goc_doc

src_f = (SERVER / "packs_fetch.py").read_text(encoding="utf-8")
check("token đi bằng HEADER, không nhét vào URL",
      "header_xac_thuc" in src_f and "://" + "{tk}" not in src_f)
# Gửi tiếp token của host cũ sang host mới là cách rò token kinh điển: chỉ cần một chuyển
# hướng do bên kia điều khiển là token đi theo.
i = src_f.index("if httpx.URL(hien).host != truoc:")
check("chuyển hướng sang tên máy KHÁC thì bỏ header xác thực",
      "Authorization" in src_f[i:i + 500] and "PRIVATE-TOKEN" in src_f[i:i + 500])

src_r = (SERVER / "routes" / "packs.py").read_text(encoding="utf-8")
check("có endpoint quản lý token", '@router.post("/packs/token")' in src_r)
i2 = src_r.index("packs_token_list")
# Chỉ trả TÊN MÁY, không bao giờ trả giá trị token. Soi đúng câu return chứ không quét cả thân
# hàm: chữ "token" còn nằm trong tên khoá `tokens` của dòng đọc cấu hình.
_ret = [L.strip() for L in src_r[i2:i2 + 500].splitlines() if L.strip().startswith("return ")]
check("liệt kê token KHÔNG bao giờ trả giá trị",
      'return {"hosts": sorted(kho)}' in _ret
      and not [L for L in _ret if "kho[" in L or ".values()" in L or "kho}" in L])

# ─────────────── 7. Nhãn nguồn và cảnh báo gói cộng đồng ───────────────
src_js = (DASHBOARD / "packs.js").read_text(encoding="utf-8")
check("thẻ kho hiện nhãn chính chủ hoặc cộng đồng",
      "chính chủ" in src_js and "cộng đồng" in src_js)
check("có tab lọc theo nguồn", "data-pkng" in src_js)
check("gói cộng đồng có cảnh báo riêng trên màn hình xác nhận",
      "chưa qua " in src_js and "kiểm duyệt" in src_js)
check("màn hình xác nhận nói rõ gói ghi gì vào bộ não", "vaultTom" in src_js)
check("và nói rõ Javis giữ bản của bạn khi trùng tên",
      "giữ bản của bạn" in src_js)
check("hộp gỡ nói rõ thứ giữ lại vì đã sửa", "Giữ lại vì bạn đã sửa" in src_js)
check("cài thì gửi kèm brain đang mở", "currentBrainPath" in src_js)

src_i = (SERVER / "pack_install.py").read_text(encoding="utf-8")
check("trình cài nhận brain để ghi năng lực", "brain_root" in src_i)
check("và gọi pack_vault khi gỡ", "pack_vault.go(pid)" in src_i)

src_v = (SERVER / "pack_vault.py").read_text(encoding="utf-8")
check("dùng lại hash chuẩn hoá của system_sync, không viết bản thứ hai",
      "system_sync.skill_hash" in src_v and "system_sync._norm_text" in src_v)

if _fails:
    print(f"\nFAIL - test_goi_vao_brain: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_goi_vao_brain: tất cả pass")
