"""Route cho "Javis trong ChatGPT". Lõi OAuth và luật an toàn nằm ở `server/chatgpt_connector.py`.

Ba nhóm đường, ba cách xác thực khác nhau, và đó là chủ ý:

1. Máy chủ OpenAI gọi (khám phá, đăng ký client, đổi token, thu hồi, và chính `/chatgpt/mcp`):
   không có cookie. Token OAuth là lớp xác thực duy nhất của `/chatgpt/mcp`.
2. Trình duyệt của chủ (trang Cho phép): GET hiện ra không cần đăng nhập để còn đăng nhập tại
   chỗ; POST "Cho phép" đòi PHIÊN ĐĂNG NHẬP THẬT và đi qua hàng rào CSRF như mọi thao tác khác.
3. Dashboard (bật/tắt, mức quyền, ngắt kết nối): đòi phiên trình duyệt thật, KHÔNG nhận token
   API. Cùng luật với trang Gói và trang Công cụ: một token rò ra không được tự mở cửa này.
"""
from __future__ import annotations

import html
from urllib.parse import urlparse
from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import chatgpt_connector as cc
import mcp_hub

router = APIRouter()


@dataclass
class ConnectorDeps:
    co_phien: Callable[[Request], bool]
    goc_ngoai: Callable[[Request], str]     # external_base NHƯ NGƯỜI DÙNG THẤY


_DEPS: "ConnectorDeps" = None   # type: ignore


def _goc(request: Request) -> str:
    return cc.dia_chi_goc(_DEPS.goc_ngoai(request))


def _tat():
    # 404 chứ không phải 403: tắt nghĩa là cửa này KHÔNG tồn tại, không quảng bá gì cho ai dò.
    return JSONResponse({"error": "not_found"}, status_code=404)


def _json_no_store(payload, status=200):
    return JSONResponse(payload, status_code=status,
                        headers={"Cache-Control": "no-store", "Pragma": "no-cache"})


async def _doc_form(request: Request) -> dict:
    """Thân POST dạng form hoặc JSON. OAuth chuẩn là form; vài client gửi JSON."""
    loai = (request.headers.get("content-type") or "").lower()
    try:
        if "application/json" in loai:
            d = await request.json()
            return d if isinstance(d, dict) else {}
        return dict(await request.form())
    except Exception:
        return {}


# ------------------------------------------------------------
# Trang Cho phép
# ------------------------------------------------------------

_CSS = """
:root { color-scheme: light dark; --nen:#f6f5f2; --the:#fff; --chu:#1d1d1f; --phu:#6b6b70;
        --vien:#dcdad4; --nhan:#c2410c; --nhan-chu:#fff; }
@media (prefers-color-scheme: dark) {
  :root { --nen:#141414; --the:#1f1f1f; --chu:#eee; --phu:#a3a3a8; --vien:#3a3a3a; }
}
* { box-sizing: border-box; }
body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
       background:var(--nen); color:var(--chu); font-size:17px; line-height:1.5;
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; padding:16px; }
.the { background:var(--the); border:1px solid var(--vien); border-radius:16px; padding:28px 24px;
       width:100%; max-width:440px; }
h1 { font-size:22px; margin:0 0 8px; }
p { margin:0 0 14px; }
.phu { color:var(--phu); font-size:16px; }
ul { margin:0 0 18px; padding-left:20px; }
li { margin-bottom:6px; }
label { display:block; font-size:16px; margin:12px 0 6px; }
input { width:100%; font-size:17px; padding:12px; border-radius:10px; border:1px solid var(--vien);
        background:transparent; color:inherit; }
button { width:100%; font-size:17px; padding:13px; border-radius:10px; border:0; cursor:pointer;
         margin-top:12px; }
.chinh { background:var(--nhan); color:var(--nhan-chu); }
.phu-nut { background:transparent; color:var(--chu); border:1px solid var(--vien); }
.loi { color:#dc2626; font-size:16px; margin-top:10px; }
code { font-size:16px; word-break:break-all; }
"""


def _trang(than: str, status: int = 200) -> HTMLResponse:
    # `same-origin`, KHÔNG phải `no-referrer`. URL trang này mang state và code_challenge nên
    # không được rò sang trang khác qua Referer, và cả hai giá trị đều chặn được điều đó. Nhưng
    # `no-referrer` còn làm trình duyệt gửi `Origin: null` khi nộp form, hàng rào CSRF coi
    # "null" là nguồn lạ và chặn nút Cho phép. Đo trên Chromium thật 23/09: 403 "cross-origin
    # request bị chặn", nút bấm mãi không qua. Test giả lập không gửi Origin nên không thấy.
    return HTMLResponse(
        f'<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="referrer" content="same-origin"><title>Javis</title>'
        f'<style>{_CSS}</style></head><body><div class="the">{than}</div></body></html>',
        status_code=status,
        headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY",
                 "Content-Security-Policy": "frame-ancestors 'none'"})


_MO_TA_MUC = {
    "full": "Toàn quyền: đọc dữ liệu và làm việc thật (gửi tin, tạo đơn, đăng bài...)",
    "auto": "Tự làm có giới hạn: đọc dữ liệu và viết nháp, không làm việc ra bên ngoài",
    "suggest": "Chỉ đọc và gợi ý: không ghi file, không làm việc ra bên ngoài",
}


def _trang_dang_nhap() -> HTMLResponse:
    """Trình duyệt chưa vào dashboard: đăng nhập NGAY TẠI ĐÂY rồi tải lại, không bắt đi vòng."""
    return _trang("""
<h1>Đăng nhập Javis</h1>
<p class="phu">ChatGPT đang xin quyền dùng Javis của bạn. Đăng nhập để xem và quyết định.</p>
<form id="f">
  <label for="u">Tài khoản</label><input id="u" name="username" autocomplete="username" required>
  <label for="p">Mật khẩu</label>
  <input id="p" name="password" type="password" autocomplete="current-password" required>
  <div id="o" style="display:none">
    <label for="c">Mã xác thực 2 lớp</label>
    <input id="c" name="code" inputmode="numeric" autocomplete="one-time-code">
  </div>
  <div id="e" class="loi" role="alert"></div>
  <button class="chinh" type="submit">Đăng nhập</button>
</form>
<script>
document.getElementById("f").onsubmit = async (ev) => {
  ev.preventDefault();
  const e = document.getElementById("e"); e.textContent = "";
  let r, d = {};
  try {
    r = await fetch("/auth/login", {method: "POST", body: new FormData(ev.target),
                                    credentials: "same-origin"});
    d = await r.json();
  } catch (x) { e.textContent = "Không gọi được Javis. Thử lại."; return; }
  if (d.ok) { location.reload(); return; }
  if (d.needs_2fa) document.getElementById("o").style.display = "";
  e.textContent = d.error || "Đăng nhập không thành công.";
};
</script>""")


def _trang_dong_y(yc: dict) -> HTMLResponse:
    muc = cc.cau_hinh()["muc_quyen"]
    host = html.escape(urlparse(yc["redirect_uri"]).hostname or "")
    return _trang(f"""
<h1>Cho phép ChatGPT dùng Javis?</h1>
<p><b>{html.escape(yc["ten"])}</b> trên <code>{host}</code> muốn gọi công cụ của Javis.</p>
<ul>
  <li>Dùng mọi kết nối bạn đã bật trong Javis (bán hàng, quảng cáo, lịch, Zalo...)</li>
  <li>Đọc và ghi trong brain đang mở, tạo việc và nhắc lịch</li>
  <li>Mức quyền: {html.escape(_MO_TA_MUC.get(muc, muc))}</li>
</ul>
<p class="phu">Đổi mức quyền hoặc ngắt kết nối bất cứ lúc nào ở thẻ ChatGPT trên trang Models.</p>
<form method="post" action="{cc.DUONG_AUTHORIZE}">
  <input type="hidden" name="yeu_cau" value="{html.escape(yc["id"])}">
  <button class="chinh" name="hanh_dong" value="cho_phep" type="submit">Cho phép</button>
  <button class="phu-nut" name="hanh_dong" value="tu_choi" type="submit">Từ chối</button>
</form>""")


def _trang_loi(cau: str, status: int = 400) -> HTMLResponse:
    return _trang(f"<h1>Không kết nối được</h1><p>{html.escape(cau)}</p>", status)


# ------------------------------------------------------------
# Đăng ký route
# ------------------------------------------------------------

def register(app, deps: ConnectorDeps):
    global _DEPS
    _DEPS = deps

    # ---- khám phá ----
    async def _pr(request: Request):
        if not cc.dang_bat():
            return _tat()
        return JSONResponse(cc.metadata_pr(_goc(request)))

    async def _as(request: Request):
        if not cc.dang_bat():
            return _tat()
        return JSONResponse(cc.metadata_as(_goc(request)))

    for duong in (cc.WK_PR, cc.WK_PR_MCP):
        router.add_api_route(duong, _pr, methods=["GET"], include_in_schema=False)
    for duong in (cc.WK_AS, cc.WK_OIDC):
        router.add_api_route(duong, _as, methods=["GET"], include_in_schema=False)

    # ---- đăng ký client (RFC 7591) ----
    @router.post(cc.DUONG_REGISTER, include_in_schema=False)
    async def dang_ky(request: Request):
        if not cc.dang_bat():
            return _tat()
        try:
            body = await request.json()
        except Exception:
            body = {}
        ma, d = cc.dang_ky_client(body if isinstance(body, dict) else {})
        return _json_no_store(d, ma)

    # ---- trang Cho phép ----
    @router.get(cc.DUONG_AUTHORIZE, include_in_schema=False)
    async def uy_quyen(request: Request):
        if not cc.dang_bat():
            return _trang_loi("Kết nối ChatGPT đang tắt trong Javis. Bật ở thẻ ChatGPT trên "
                              "trang Models rồi kết nối lại.", 404)
        kq, gia_tri = cc.bat_dau_uy_quyen(dict(request.query_params))
        if kq == "trang_loi":
            return _trang_loi(gia_tri)
        if kq == "chuyen":
            return RedirectResponse(gia_tri, status_code=302)
        if not _DEPS.co_phien(request):
            return _trang_dang_nhap()
        return _trang_dong_y(gia_tri)

    @router.post(cc.DUONG_AUTHORIZE, include_in_schema=False)
    async def uy_quyen_xac_nhan(request: Request):
        if not cc.dang_bat():
            return _trang_loi("Kết nối ChatGPT đang tắt trong Javis.", 404)
        # Chỉ PHIÊN TRÌNH DUYỆT thật được bấm Cho phép. Token API không qua cửa này.
        if not _DEPS.co_phien(request):
            return _trang_loi("Phiên đăng nhập đã hết. Mở lại ChatGPT và kết nối lại.", 401)
        f = await _doc_form(request)
        yid = str(f.get("yeu_cau") or "")
        url = cc.dong_y(yid) if f.get("hanh_dong") == "cho_phep" else cc.tu_choi(yid)
        if not url:
            return _trang_loi("Yêu cầu này đã quá hạn. Mở lại ChatGPT và kết nối lại.")
        return RedirectResponse(url, status_code=302)

    # ---- đổi token + thu hồi ----
    @router.post(cc.DUONG_TOKEN, include_in_schema=False)
    async def token(request: Request):
        if not cc.dang_bat():
            return _tat()
        ma, d = cc.doi_token(await _doc_form(request))
        return _json_no_store(d, ma)

    @router.post(cc.DUONG_REVOKE, include_in_schema=False)
    async def thu_hoi(request: Request):
        if not cc.dang_bat():
            return _tat()
        cc.thu_hoi(str((await _doc_form(request)).get("token") or ""))
        return _json_no_store({})

    # ---- MCP ----
    @router.post(cc.DUONG_MCP, include_in_schema=False)
    async def mcp(request: Request):
        if not cc.dang_bat():
            return _tat()
        raw = str(request.headers.get("authorization") or "")
        raw = raw[7:].strip() if raw[:7].lower() == "bearer " else ""
        if not cc.kiem_token(raw):
            return JSONResponse(
                {"error": "unauthorized", "error_description": "cần kết nối lại từ ChatGPT"},
                status_code=401,
                # Header HTTP chỉ nhận Latin-1: viết tiếng Việt vào đây là starlette ném
                # UnicodeEncodeError và chính bước ĐẦU TIÊN ChatGPT gọi trả 500.
                headers={"WWW-Authenticate": cc.www_authenticate(
                    _goc(request), mo_ta="missing, invalid or expired token")})
        # Mức quyền đọc TỪNG LƯỢT từ cài đặt, không đóng băng vào token: chủ hạ quyền trên
        # dashboard là có hiệu lực ngay ở lần gọi kế tiếp.
        # include_ambient=False: tool native của tài khoản Claude không liên quan ở đây.
        # raw_vault=None: brain do Javis tự suy (brain đang mở), không nhận header từ ngoài.
        return await mcp_hub.tra_loi_jsonrpc(request, cc.cau_hinh()["muc_quyen"],
                                             include_plugins=True, include_ambient=False,
                                             raw_vault=None)

    @router.api_route(cc.DUONG_MCP, methods=["GET", "DELETE"], include_in_schema=False)
    async def mcp_khac(request: Request):
        # Streamable HTTP không trạng thái: không có luồng do máy chủ mở, không có phiên để xoá.
        if not cc.dang_bat():
            return _tat()
        return JSONResponse({"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32000, "message": "Chỉ nhận POST."}},
                            status_code=405, headers={"Allow": "POST"})

    # ---- dashboard ----
    def _tu_choi_phien():
        return JSONResponse({"ok": False, "error": "Thao tác này phải đăng nhập bằng trình duyệt."},
                            status_code=403)

    @router.get("/chatgpt/connector/status")
    async def trang_thai(request: Request):
        if not _DEPS.co_phien(request):
            return _tu_choi_phien()
        import config as cfgmod
        ch = cc.cau_hinh()
        return {"ok": True, **ch, "co_mat_khau": cfgmod.auth_enabled(),
                "url_mcp": _goc(request) + cc.DUONG_MCP, "so_ket_noi": cc.so_ket_noi()}

    @router.post("/chatgpt/connector/settings")
    async def cai_dat(request: Request):
        if not _DEPS.co_phien(request):
            return _tu_choi_phien()
        d = await request.json()
        r = cc.dat_cau_hinh(bat=d.get("bat") if "bat" in d else None,
                            muc_quyen=d.get("muc_quyen") if "muc_quyen" in d else None)
        return r if r.get("ok") else JSONResponse(r, status_code=400)

    @router.post("/chatgpt/connector/disconnect")
    async def ngat(request: Request):
        if not _DEPS.co_phien(request):
            return _tu_choi_phien()
        return {"ok": True, "da_ngat": cc.ngat_tat_ca()}

    app.include_router(router)
    return router

