"""Đổi mã gói (0.440.0): gói mới khai `replaces` thay gói cũ, máy đang cài không mất gì.

    python tests/run.py doi_ma_goi      (KHÔNG mạng)

Chủ dự án 02/11: "mã gói đừng để tiếng Việt, dự án mình quốc tế rồi". Đổi thẳng mã trên Store thì máy đã cài coi mã
mới là một gói KHÁC: gói cũ không bao giờ được cập nhật, gói mới nằm cạnh như chưa cài, token đăng nhập ChatGPT
(nằm trong dữ liệu plugin) mất, và địa chỉ `/ext/<slug>/mcp` đã dán vào ChatGPT chết. File này khoá:

1. Soi gói mới: báo nó thay gói nào, connector cùng tên của gói cũ không bị coi là trùng.
2. Cài: dữ liệu plugin, sổ năng lực trong brain, trạng thái bật chuyển sang mã mới; gói cũ gỡ khỏi đĩa và sổ.
3. Địa chỉ `/ext/<slug cũ>/...` tới plugin mới.
4. Năng lực gói cũ đặt vào brain đi theo gói mới (cập nhật được, gỡ được), không thành "của người khác".
5. Danh mục Store: thẻ mã cũ thôi hiện, thẻ mới hiện "đã cài" kèm bản mới; chuông báo bản mới.
6. Gói khai `replaces` một mã không cài thì không đụng gì.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-doima-")
os.environ["JAVIS_ENABLE_USER_PLUGINS"] = "true"

import packs           # noqa: E402
import pack_install    # noqa: E402
import pack_vault      # noqa: E402
import pack_updates    # noqa: E402
import plugins_host    # noqa: E402
from config import STATE_DIR  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{them}]" if them and not cond else ""))
    if not cond:
        _fails.append(name)


PLUGIN = '''
def register(ctx):
    ctx.register_http("mcp", lambda r, c: {"slug": c.slug}, methods=("POST",), public=True, no_cookie=True)
'''


def goi_zip(pid, ver, slug, replaces=None, ten_skill="tu-van"):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        man = f"format: javis-pack\nspec: 1\nid: {pid}\nversion: {ver}\nname: {pid}\n" \
              f"provides:\n  connectors:\n    - connectors/demo.yaml\n"
        if replaces:
            man += "replaces:\n" + "".join(f"  - {x}\n" for x in replaces)
        z.writestr("javis-pack.yaml", man)
        z.writestr("connectors/demo.yaml", "id: demo-svc\nname: Demo\ntransport: http\nurl: https://x.example/mcp\n")
        z.writestr(f"plugins/{slug}/plugin.yaml",
                   f"name: {slug}\nslug: {slug}\nenabled: true\nmin_mode: readonly\n")
        z.writestr(f"plugins/{slug}/plugin.py", PLUGIN)
        z.writestr(f"skills/{ten_skill}/SKILL.md", "---\nname: tu-van\n---\nTư vấn.\n")
    return b.getvalue()


def cai(du_lieu, brain, enable=True):
    s = pack_install.soi(du_lieu, "x.zip")
    assert s.get("ok"), s
    r = pack_install.cai(s["staging_id"], s["sha256"], enable=enable, brain_root=str(brain))
    return s, r


BRAIN = Path(tempfile.mkdtemp(prefix="brain-doima-"))

# ---- gói cũ, mã tiếng Việt ----
s0, r0 = cai(goi_zip("javis.javis-trong-chatgpt", "1.0.0", "javis-trong-chatgpt"), BRAIN)
check("cài gói cũ", r0.get("ok"), r0)
du_lieu_cu = STATE_DIR / "plugin-data" / "javis-trong-chatgpt"
du_lieu_cu.mkdir(parents=True, exist_ok=True)
(du_lieu_cu / "kho.json").write_text('{"tokens": {"abc": 1}}', encoding="utf-8")
check("skill gói cũ nằm trong brain", (BRAIN / "skills" / "tu-van" / "SKILL.md").is_file())

# ---- danh mục Store trước khi cập nhật ----
KHO = [{"id": "javis.gate", "version": "2.0.0", "name": {"vi": "Javis Gate"},
        "replaces": ["javis.javis-trong-chatgpt"]},
       {"id": "javis.javis-trong-chatgpt", "version": "1.0.0", "name": {"vi": "Javis trong ChatGPT"}}]
up = pack_updates.find_updates(KHO, pack_install.doc_so())
check("chuông báo bản mới cho gói đổi mã", any(u["id"] == "javis.gate" and u["from"] == "1.0.0" for u in up), up)
import packs_store  # noqa: E402
sach = packs_store._lam_sach({"id": "javis.gate", "replaces": ["javis.javis-trong-chatgpt", "", 5], "download": {}})
check("danh mục giữ trường replaces đã làm sạch", sach["replaces"] == ["javis.javis-trong-chatgpt", "5"], sach)
check("replaces kiểu lạ (chuỗi) thành rỗng", packs_store._lam_sach({"id": "a", "replaces": "abc"})["replaces"] == [])

# ---- 1. soi gói mới ----
moi = goi_zip("javis.gate", "2.0.0", "javis-gate", replaces=["javis.javis-trong-chatgpt", "javis.khong-cai"])
s1 = pack_install.soi(moi, "gate.zip")
check("soi: gói mới hợp lệ, connector cùng tên gói cũ KHÔNG bị coi là trùng",
      s1.get("ok") and "demo-svc" in s1.get("connectors", []), s1.get("error") or s1.get("warning"))
check("soi: báo gói đã cài mà nó thay (chỉ mã đang cài)", s1.get("replaces") == ["javis.javis-trong-chatgpt"], s1)
check("soi: màn hình xác nhận coi là bản cập nhật", (s1.get("da_cai") or {}).get("version") == "1.0.0", s1.get("da_cai"))

# ---- 2. cài ----
r1 = pack_install.cai(s1["staging_id"], s1["sha256"], enable=False, brain_root=str(BRAIN))
check("cài gói mới ok, báo đã thay gói cũ", r1.get("ok") and r1.get("replaced") == ["javis.javis-trong-chatgpt"], r1)
so = pack_install.doc_so()
check("sổ cài đặt: có mã mới, mất mã cũ", "javis.gate" in so and "javis.javis-trong-chatgpt" not in so, list(so))
check("gói cũ đang bật thì bản thay nó cũng bật, dù màn hình gửi enable=False",
      so["javis.gate"]["enabled"] is True and r1.get("enabled") is True)
check("thư mục gói cũ đã gỡ", not (packs.PACKS_DIR / "javis.javis-trong-chatgpt").exists())
check("connector của gói mới đầy đủ trong sổ", so["javis.gate"]["connectors"] == ["demo-svc"], so["javis.gate"])
du_lieu_moi = STATE_DIR / "plugin-data" / "javis-gate"
check("dữ liệu plugin (token) chuyển sang tên mới",
      (du_lieu_moi / "kho.json").is_file() and not du_lieu_cu.exists())
check("sổ ghi bí danh plugin cũ -> mới", so["javis.gate"].get("plugin_aliases") == {"javis-trong-chatgpt": "javis-gate"})
check("packs.plugin_alias đọc ra bí danh", packs.plugin_alias("javis-trong-chatgpt") == "javis-gate")
check("plugin không đổi tên thì không có bí danh", packs.plugin_alias("javis-gate") == "")

# ---- 3. địa chỉ cũ tới plugin mới ----
plugins_host.invalidate()
tr = plugins_host.tim_http("javis-trong-chatgpt", "mcp", "POST")
check("/ext/<slug cũ>/mcp tới plugin mới", tr is not None and tr[0].slug == "javis-gate", tr)
check("địa chỉ mới vẫn chạy", plugins_host.tim_http("javis-gate", "mcp", "POST") is not None)
check("đường không có thì vẫn không có", plugins_host.tim_http("javis-trong-chatgpt", "khong-co", "POST") is None)

# ---- 4. năng lực trong brain đi theo gói mới ----
sv = pack_vault.doc_so("javis.gate")
check("sổ năng lực brain chuyển sang mã mới", "skills/tu-van" in (sv.get("items") or {}), sv)
check("sổ năng lực mã cũ không còn", not pack_vault._so_path("javis.javis-trong-chatgpt").exists())
check("skill không bị bỏ qua như 'của người khác'",
      not any(x.get("khoa") == "skills/tu-van" for x in (r1.get("vault") or {}).get("bo_qua", [])), r1.get("vault"))

# ---- 5. bí danh đi tiếp qua lần đổi tên thứ hai ----
s2, r2 = cai(goi_zip("javis.gate-pro", "3.0.0", "gate-pro", replaces=["javis.gate"]), BRAIN)
so = pack_install.doc_so()
check("đổi tên lần hai: bí danh cũ nhất cũng trỏ về tên mới nhất",
      so["javis.gate-pro"].get("plugin_aliases") == {"javis-trong-chatgpt": "gate-pro", "javis-gate": "gate-pro"},
      so["javis.gate-pro"].get("plugin_aliases"))
plugins_host.invalidate()
tr = plugins_host.tim_http("javis-trong-chatgpt", "mcp", "POST")
check("địa chỉ gốc vẫn tới plugin mới nhất", tr is not None and tr[0].slug == "gate-pro")

# ---- 6. replaces một mã không cài: không đụng gì ----
s3, r3 = cai(goi_zip("javis.crm", "1.0.1", "crm", replaces=["javis.khach-hang-crm"], ten_skill="cham-soc"), BRAIN,
             enable=False)
check("replaces mã không cài: cài bình thường, không thay gì", r3.get("ok") and r3.get("replaced") == [], r3)
check("không có gói cũ để thừa hưởng: bật hay tắt đúng như màn hình chọn",
      pack_install.doc_so()["javis.crm"]["enabled"] is False)

# ---- danh mục Store qua route ----
src = (SERVER / "routes" / "packs.py").read_text(encoding="utf-8")
check("route danh mục: ẩn thẻ mã cũ và đánh dấu thẻ mới đã cài",
      "bi_thay" in src and "replaces_installed" in src)
man = packs.ma_thay_the({"replaces": ["javis.a", "javis.a", "../x", "javis.self", 3]}, "javis.self")
check("ma_thay_the: bỏ trùng, bỏ mã sai, bỏ chính nó", man == ["javis.a", "3"], man)

print()
print("ALL PASS" if not _fails else f"{len(_fails)} FAIL: {_fails}")
raise SystemExit(1 if _fails else 0)
