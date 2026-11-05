"""Cloudflare là kết nối dựng sẵn của Javis, đi đôi với GitHub (chủ repo 2026-11-05).

    python tests/run.py cloudflare_mac_dinh

Trước đây Cloudflare chỉ có trong Javis Store (gói `javis.cloudflare`, rồi `javis.cloudflare-oauth`
cho đường đăng nhập web). Giờ cả hai cách nằm trong `system/mcp-catalog.json`, gom một thẻ nhóm.

Test canh ba điều:
1. Lõi có đủ hai cách (dán token và đăng nhập OAuth), cùng nhóm, công cụ `execute` vẫn ở nhóm
   nguy hiểm, mặc định Chỉ đọc.
2. Máy đã cài gói Cloudflare từ kho trước bản này không bị báo lỗi đỏ "id đã có trong kho": gói
   được lõi khai `thay_goi` thì id đó im lặng nhường cho lõi, kết nối cũ chạy tiếp theo bản lõi.
3. Lối nhường đó KHÔNG mở cho gói khác: một gói lạ khai id `cloudflare` vẫn bị từ chối như cũ.

Không cần pytest, không chạm mạng, không đụng `STATE_DIR/packs` thật.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

import mcp_catalog
import packs

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


MANIFEST = """format: javis-pack
spec: 1
id: {pid}
version: 1.0.1
name: {{vi: "Cloudflare"}}
compat: {{app: ">=0.1.0"}}
provides:
  connectors: [connectors/c.json]
"""

CONNECTOR = """{{"id": "{cid}", "name": "Cloudflare", "transport": "http", "url": "https://vi-du.dev/mcp",
 "auth": {{"type": "apikey", "fields": [{{"key": "api_token", "label": "API token"}}]}}}}
"""


def lam_goi(goc, pid, cid):
    d = goc / pid
    (d / "connectors").mkdir(parents=True, exist_ok=True)
    (d / "javis-pack.yaml").write_text(MANIFEST.format(pid=pid), encoding="utf-8")
    (d / "connectors" / "c.json").write_text(CONNECTOR.format(cid=cid), encoding="utf-8")


def lam_moi():
    packs.invalidate()
    mcp_catalog._cache.update(sig=None, by_id={})


# ─────────────── 1. Lõi có sẵn cả hai cách ───────────────
goc = mcp_catalog.tat_ca()
tk, oa = goc.get("cloudflare") or {}, goc.get("cloudflare-oauth") or {}
check("lõi có connector cloudflare (dán API token)", (tk.get("auth") or {}).get("type") == "apikey")
check("lõi có connector cloudflare-oauth (đăng nhập web)", (oa.get("auth") or {}).get("type") == "oauth")
check("đường OAuth tự đăng ký (không khai authorize_url, không bắt dán client id)",
      not (oa.get("auth") or {}).get("authorize_url") and not (oa.get("auth") or {}).get("fields"))
check("hai cách cùng một máy chủ MCP chính chủ",
      tk.get("url") == oa.get("url") == "https://mcp.cloudflare.com/mcp")
check("hai cách gom chung nhóm cloudflare", tk.get("group") == oa.get("group") == "cloudflare")
for c in (tk, oa):
    cid = c.get("id")
    check(f"{cid}: execute ở nhóm danger", "execute" in ((c.get("tool_meta") or {}).get("danger") or []))
    check(f"{cid}: mặc định Chỉ đọc", c.get("default_perm") == "readonly")
    check(f"{cid}: có group_line", bool(c.get("group_line")))
    check(f"{cid}: logo nằm trong app", c.get("icon") == "/static/logos/cloudflare.jpg"
          and (ROOT / "dashboard" / "logos" / "cloudflare.jpg").is_file())
check("lõi khai đúng gói mình thay", tk.get("thay_goi") == ["javis.cloudflare"]
      and oa.get("thay_goi") == ["javis.cloudflare-oauth"])

# ─────────────── 2 và 3. Gói cũ đã cài, gói lạ ───────────────
with tempfile.TemporaryDirectory() as td:
    kho = Path(td) / "packs"
    kho.mkdir()
    goc_dir, packs.PACKS_DIR = packs.PACKS_DIR, kho
    goc_env = os.environ.pop("JAVIS_DISABLE_PACKS", None)
    try:
        lam_goi(kho, "javis.cloudflare", "cloudflare")
        lam_goi(kho, "javis.cloudflare-oauth", "cloudflare-oauth")
        lam_goi(kho, "acme.gian", "cloudflare")
        lam_moi()
        ds = {p["id"]: p for p in packs.installed()}
        for pid, cid in (("javis.cloudflare", "cloudflare"), ("javis.cloudflare-oauth", "cloudflare-oauth")):
            p = ds.get(pid) or {}
            check(f"{pid} đã cài từ trước: không báo lỗi đỏ", p.get("ok") and not p.get("error"))
            check(f"{pid}: không góp connector trùng", p.get("connectors") == [])
            check(f"{pid}: ghi nhận id đã có sẵn trong lõi", p.get("built_in") == [cid])
        gian = ds.get("acme.gian") or {}
        check("gói lạ khai id cloudflare vẫn bị từ chối", gian.get("connectors") == []
              and "đã có trong kho" in (gian.get("error") or ""))
        con = mcp_catalog.get("cloudflare") or {}
        check("connector cloudflare đang chạy là bản của lõi, không phải của gói",
              bool(con) and not con.get("_pack") and con.get("url") == "https://mcp.cloudflare.com/mcp")
        pub = {c["id"]: c for c in mcp_catalog.public_catalog()}
        check("trang Kết nối thấy cả hai cách", {"cloudflare", "cloudflare-oauth"} <= set(pub))
    finally:
        packs.PACKS_DIR = goc_dir
        if goc_env is not None:
            os.environ["JAVIS_DISABLE_PACKS"] = goc_env
        lam_moi()

if _fails:
    print(f"\nFAIL - test_cloudflare_mac_dinh: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_cloudflare_mac_dinh: tất cả pass")
