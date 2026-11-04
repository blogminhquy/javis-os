"""Danh bạ tên gói (04/11/2026): tên gói đang bán lấy từ javis-store, không ghi cứng trong mã Javis.

    python tests/run.py plan_names

Chủ repo 04/11/2026: "làm tự động hóa tên các gói của các nhà cung cấp khác luôn". Codex chỉ gửi mã
(`prolite` là gói 100 đô), nên tên nằm ở `plan-names.json` của javis-store, máy tải về 6 giờ một lần.
Test này giữ: đọc không bao giờ chờ mạng, dữ liệu lạ bị bỏ, thứ tự ưu tiên tên.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="javis-pn-")
os.environ["JAVIS_STATE_DIR"] = _TMP
U = "https://kho.example/plan-names.json"
os.environ["JAVIS_PLAN_NAMES_URL"] = U

import plan_names as pn  # noqa: E402
import plan_limits as pl  # noqa: E402

fails = []


def check(ten, ok, them=None):
    print(("PASS: " if ok else "FAIL: ") + ten + ("" if ok or them is None else f"  [{them}]"))
    if not ok:
        fails.append(ten)


GOC = {"format": "javis-plan-names", "format_version": 1, "updated": "2026-11-04",
       "providers": {"codex": {"prolite": "Pro", "plus": "Plus", "PRO": "Pro 20x", "x y": "Hỏng",
                               "go": "<script>", "team": "Business"},
                     "claude": {"pro": "Pro"}, "la": {"a": "B"}, "grok": "khong-phai-bang"}}

# 1. Làm sạch: chỉ giữ mã/tên đúng mẫu, nhà lạ và kiểu lạ bị bỏ.
s = pn.lam_sach(GOC)
check("giữ tên hợp lệ", s.get("codex", {}).get("prolite") == "Pro" and s["codex"]["team"] == "Business", s)
check("mã viết hoa được hạ thường", s["codex"].get("pro") == "Pro 20x", s)
check("mã có khoảng trắng bị bỏ", "x y" not in s["codex"])
check("tên có ký tự lạ bị bỏ", "go" not in s["codex"])
check("nhà lạ và bảng sai kiểu bị bỏ", "la" not in s and "grok" not in s, s)
check("sai format thì rỗng", pn.lam_sach({"format": "khac", "providers": GOC["providers"]}) == {})
check("định dạng mới hơn thì rỗng, không đọc nửa vời", pn.lam_sach(dict(GOC, format_version=2)) == {})

# 2. Đọc: từ bản lưu, KHÔNG chờ mạng. Bản cũ thì khởi động đúng một lượt làm mới nền.
goi_nen = []
pn._lam_moi_nen = lambda u: goi_nen.append(u)
check("chưa có bản lưu: rỗng ngay, đá một lượt làm mới", pn.ten("codex", "prolite") == "" and goi_nen == [U], goi_nen)
pn._STATE["mem"] = None
pn._ghi_cache({"fetched_at": 1_000_000.0, "url": U, "providers": s})
goi_nen.clear()
check("bản lưu còn hạn: đọc được, không làm mới", pn.bang(now=1_000_000.0 + 60).get("codex", {}).get("plus") == "Plus"
      and goi_nen == [], goi_nen)
pn.bang(now=1_000_000.0 + pn.TTL + 1)
check("bản lưu quá 6 giờ: vẫn trả bản cũ, đá làm mới nền", goi_nen == [U], goi_nen)
pn._STATE["fail_at"] = 1_000_000.0 + pn.TTL + 1
goi_nen.clear()
pn.bang(now=1_000_000.0 + pn.TTL + 60)
check("vừa tải hỏng: nghỉ 30 phút rồi mới thử lại", goi_nen == [], goi_nen)
pn._STATE["fail_at"] = 0.0
os.environ["JAVIS_PLAN_NAMES_URL"] = "https://kho-khac.example/plan-names.json"
pn._STATE["mem"] = None
check("đổi kho thì không dùng bản lưu của kho cũ", pn.bang(now=1_000_000.0 + 60) == {})
os.environ["JAVIS_PLAN_NAMES_URL"] = ""
check("URL rỗng là tắt danh bạ", pn.bang() == {} and pn.url_danh_ba() == "")
os.environ["JAVIS_PLAN_NAMES_URL"] = U
pn._STATE["mem"] = None

# 3. Tải: hợp lệ thì lưu, hỏng thì giữ bản cũ.
import packs_fetch  # noqa: E402


async def _tai_tot(url, tran=0, header=None):
    return json.dumps(dict(GOC, providers={"codex": {"prolite": "Pro 5x"}})).encode()


async def _tai_hong(url, tran=0, header=None):
    raise OSError("mất mạng")

packs_fetch.tai = _tai_tot
check("tải được thì lưu bản mới", pn.lam_moi() and pn.ten("codex", "prolite") == "Pro 5x")
packs_fetch.tai = _tai_hong
check("tải hỏng thì báo False, giữ bản cũ", not pn.lam_moi() and pn.ten("codex", "prolite") == "Pro 5x")
check("tải hỏng ghi mốc nghỉ", pn._STATE["fail_at"] > 0)

# 4. Thứ tự ưu tiên trong plan_limits.ten_goi.
check("danh bạ thắng mã viết gọn", pl.ten_goi("prolite", "codex") == "Pro 5x")
check("không có trong danh bạ thì viết gọn mã", pl.ten_goi("promax", "codex") == "Promax")
check("không nói nhà nào thì không tra danh bạ", pl.ten_goi("prolite") == "Prolite")
check("tên nhà cung cấp đã có chữ hoa giữ nguyên", pl.ten_goi("SuperGrok", "grok") == "SuperGrok")
check("rỗng vẫn rỗng", pl.ten_goi("", "codex") == "")

# 5. Nối đúng chỗ.
main_src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
cli_src = (ROOT / "server" / "claude_cli.py").read_text(encoding="utf-8")
check("vòng hạn mức tra danh bạ theo từng nhà",
      'plan_limits.ten_goi((d.get("codex") or {}).get("goi") or oa.get("plan") or "", "codex")' in main_src
      and 'plan_limits.ten_goi(grok_k.get("plan") or "", "grok")' in main_src)
check("thẻ Models ChatGPT và Grok tra danh bạ",
      'plan_limits.ten_goi(oauth.get("plan", ""), "codex")' in main_src
      and 'plan_limits.ten_goi(_k.get("plan", ""), "grok")' in main_src)
check("Claude: tên Anthropic gửi vẫn đứng trước danh bạ",
      'plan_limits.ten_goi_claude(folder, email)' in cli_src and 'plan_limits.ten_goi(goi, "claude")' in cli_src)
check("luật tên trùng luật của Claude Code", pn.ten_hop_le("Pro 20x") and pn.ten_hop_le("Plus+")
      and not pn.ten_hop_le("x" * 41) and not pn.ten_hop_le("-Pro"))

if fails:
    raise SystemExit(f"{len(fails)} FAIL")
print("OK")
