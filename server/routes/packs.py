"""Trang Gói: xem, cài từ tệp .zip, bật tắt, gỡ.

Bóc thành module riêng ngay từ đầu thay vì viết thẳng vào main.py (đã 14.6k dòng). Theo đúng
hai luật ở `routes/__init__.py`: không bao giờ `import main`, và lời gọi `register` trong
main.py phải nằm đúng vị trí vì `tests/python/route_table.json` khoá cả thứ tự.

Xác thực: mọi endpoint ở đây đòi PHIÊN ĐĂNG NHẬP THẬT
-----------------------------------------------------
Middleware xác thực của main.py chỉ chạy khi `cfgmod.gate_active()` là True, mà hàm đó trả
False trên một bản cài local chưa đặt mật khẩu. Với các trang khác thì đó là lựa chọn thoải mái
có chủ ý; với TRANG NÀY thì không, vì cài một gói là chạy mã lạ trong tiến trình server. Nên
`_doi_phien` kiểm độc lập, không phụ thuộc cổng chung.

Và cài KHÔNG nhận API token: token dành cho tự động hoá, mà "tự động cài một gói" đúng là thứ
không nên có đường tồn tại. Đường cài phải có người ngồi trước màn hình.

Cài hai bước
------------
`POST /packs/inspect` mở tệp, kiểm mọi luật, giải nén vào staging (NGOÀI thư mục kho, nên chưa
gì được nạp) rồi trả về đúng cái sắp xảy ra kèm `sha256`. `POST /packs/install` chỉ nhận nếu
người gọi đưa lại đúng sha256 đó - ràng buộc này làm cái đã hiện ra trên màn hình phải chính là
cái được cài.
"""
import inspect
import sys
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

import pack_install
import packs
import packs_fetch
import packs_store
import localefmt

# Chỉ ảnh, và KHÔNG SVG: một SVG phục vụ cùng origin thì trơ trong thẻ <img> nhưng chạy script
# khi người dùng mở thẳng nó ra một tab, tức là XSS trên chính origin của dashboard.
ANH = {".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg",
       ".jpeg": "image/jpeg", ".gif": "image/gif"}

MAX_UPLOAD = pack_install.MAX_ZIP


@dataclass
class PacksDeps:
    """Thứ duy nhất cần từ main: cách hỏi "request này có phiên đăng nhập thật không"."""
    co_phien: Callable[[Request], bool]
    lam_moi_hub: Callable[[], None]
    brain_root: Callable[[str], str]
    # 2026-11-11: a pack just placed or removed assistant files in this brain root. main brings the Auto registry in
    # step (agent_presence.sync) and tells the open tabs. May be async. Default: nothing (tests, tools).
    agents_changed: Callable[[str], Any] = lambda root: None


_DEPS: PacksDeps = None


def _nn(v, mac=""):
    """`name`/`description` là map đa ngôn ngữ. Lấy tiếng Việt, rơi về en, rồi về giá trị đầu."""
    if isinstance(v, dict):
        return v.get("vi") or v.get("en") or next(iter(v.values()), mac)
    return str(v or mac)


def _nhom(g: dict) -> str:
    """Tên NHÓM hiển thị của một mục trong kho.

    Gộp theo CHỮ NGƯỜI ĐỌC THẤY chứ không theo mã. Danh mục kho khai `category` là mã máy
    (`ban-hang`) kèm `category_label` để hiện; còn catalog connector đi kèm app từ xưa tới nay
    chỉ có một trường `category` viết thẳng tiếng Việt ("Bán hàng"). Gộp theo mã thì hai thứ
    cùng nghĩa nằm ở hai nhóm rời nhau, và cột nhóm bên trái hiện "Bán hàng" hai lần."""
    return _nn(g.get("category_label")) or str(g.get("category") or "") or "Khác"


def _id_app_dang_cap() -> set:
    """Id connector app đang THẬT SỰ cấp - đã trừ những cái người dùng gỡ đi.

    Trừ phần đã gỡ mới đúng: gỡ xong thì id không còn bị chiếm, nên gói trong kho cấp đúng id
    đó phải hiện ra và cài được. Không trừ thì người dùng gỡ một dịch vụ của app rồi không có
    đường nào lấy lại bản của kho."""
    try:
        import core_off
        import mcp_catalog
        return set(mcp_catalog.tat_ca() or {}) - core_off.da_go("connectors")
    except Exception:
        return set()


def _connector_cua_app() -> list:
    """Connector ship theo app, đóng gói lại thành mục của kho.

    `tat_ca()` trả về catalog ĐẦY ĐỦ kể cả cái đã gỡ - đúng thứ cần ở đây, vì cái đã gỡ phải
    hiện ra để bấm cài lại được. Cố ý KHÔNG lấy connector do gói cấp: gói đó đã là một mục
    riêng trong kho rồi, liệt kê thêm connector của nó là đếm hai lần."""
    try:
        import core_off
        import mcp_catalog
        # Khoá là "connectors" số NHIỀU (`core_off.LOAI`). Gõ số ít thì `da_go` trả rỗng một
        # cách hoàn toàn im lặng, và mọi connector mãi mãi hiện là "đã cài" - kể cả cái vừa gỡ.
        da_go = core_off.da_go("connectors")
        ra = []
        for cid, c in (mcp_catalog.tat_ca() or {}).items():
            # Chạy LỆNH thì là bậc code, dù không một dòng Python nào: `transport: stdio` khiến
            # Javis chạy `npx` với toàn bộ biến môi trường của máy chủ.
            code = str(c.get("transport") or "http").lower() == "stdio" or bool(c.get("command"))
            nhom = str(c.get("category") or "Khác")
            ra.append({
                "id": cid, "kind": "connector",
                "name": {"vi": c.get("name", cid)},
                "description": {"vi": c.get("description", "")},
                "version": "", "author": {"name": "Javis"},
                "category": nhom, "category_label": {"vi": nhom}, "nhom": nhom,
                "tier": "code" if code else "data",
                "verified": True, "icon": c.get("icon", ""),
                "installed": cid not in da_go, "installed_version": "",
                "nguon": "app",
                "download": {"url": "", "sha256": "", "size": 0},
            })
        return ra
    except Exception as e:
        # Kho vẫn phải vẽ được nếu chỗ này hỏng: mục tải từ kho không dính dáng gì tới catalog.
        print(f"[packs] không gộp được connector của app vào kho: {e}", file=sys.stderr)
        return []


def _gone_from_brain(pid: str, hang: dict, g: dict) -> bool:
    """True when this installed pack is only brain items (no connector, no plugin) and none is left.

    A pack with a connector or a plugin stays installed whatever happens in the brain: those live in the
    pack folder and keep working."""
    if (hang.get("connectors") or []) or (hang.get("plugins") or []):
        return False
    prov = g.get("provides") or {}
    if (prov.get("connectors") or []) or (prov.get("plugins") or []):
        return False
    if not any(prov.get(k) for k in ("agents", "workflows", "skills")):
        return False
    try:
        import pack_vault
        return pack_vault.con_lai(pid)["present"] == 0
    except Exception:
        return False


def _items_brain(pid: str, brain: str) -> dict:
    """pack_vault.brain_of for the brain the dashboard has open (`brain` as the dashboard sends it). Never raises:
    a Store page must not fail over a label."""
    try:
        import pack_vault
        return pack_vault.brain_of(pid, _DEPS.brain_root(str(brain or "brain")) if brain else "")
    except Exception:       # noqa: BLE001
        return {"brain": "", "name": "", "present": 0, "other": False}


async def _agents_changed(root: str) -> None:
    """Tell main that the assistant files of brain `root` changed. Never fails the install or uninstall it follows."""
    if not root:
        return
    try:
        res = _DEPS.agents_changed(root)
        if inspect.isawaitable(res):
            await res
    except Exception as e:  # noqa: BLE001
        print(f"[packs] agents_changed: {type(e).__name__}: {e}", file=sys.stderr)


def _pack_brain(pid: str) -> str:
    """The brain root that holds the items pack `pid` placed, "" when it placed none."""
    try:
        import pack_vault
        return str(pack_vault.doc_so(pid).get("brain") or "")
    except Exception:  # noqa: BLE001
        return ""


def _tu_choi():
    return JSONResponse({"ok": False, "error": localefmt.chu("Cần đăng nhập vào Javis để quản lý gói.",
                                                         "Sign in to Javis to manage packs.")},
                        status_code=401)


def _make_router() -> APIRouter:
    router = APIRouter()

    @router.get("/packs")
    async def packs_list(request: Request):
        if not _DEPS.co_phien(request):
            return _tu_choi()
        return {"packs": packs.installed(), "dir": str(packs.PACKS_DIR),
                "disabled": packs.tat_het(), "ledger": pack_install.doc_so(),
                "max_mb": MAX_UPLOAD // 1024 // 1024}

    @router.post("/packs/inspect")
    async def packs_inspect(request: Request, file: UploadFile = File(...)):
        """Soi tệp .zip rồi trả về đúng cái sắp xảy ra. Chưa đặt gì vào kho."""
        if not _DEPS.co_phien(request):
            return _tu_choi()
        # Đọc theo KHỐI và bỏ ngay khi vượt trần: `await file.read()` nạp cả tệp vào RAM rồi
        # mới kiểm, tức một tệp 2GB làm hết bộ nhớ máy chủ trước khi tới được dòng kiểm.
        khoi, tong = [], 0
        while True:
            b = await file.read(1 << 20)
            if not b:
                break
            tong += len(b)
            if tong > MAX_UPLOAD:
                return JSONResponse({"ok": False, "stage": "verify",
                                     "error": localefmt.chu(f"tệp quá lớn, trần {MAX_UPLOAD // 1024 // 1024}MB",
                                                            f"file too large, limit {MAX_UPLOAD // 1024 // 1024}MB")},
                                    status_code=413)
            khoi.append(b)
        return pack_install.soi(b"".join(khoi), (file.filename or "").strip())

    @router.post("/packs/install")
    async def packs_install(request: Request):
        if not _DEPS.co_phien(request):
            return _tu_choi()
        d = await request.json()
        # `source` do client gửi lại nguyên văn từ kết quả soi, chỉ để GHI VÀO SỔ cho biết gói
        # này đến từ đâu. Không có gì trong hệ thống tin vào nó, nên nó chỉ là ghi chú.
        ng = d.get("source") if isinstance(d.get("source"), dict) else None
        if ng:
            ng = {"kind": str(ng.get("kind") or "")[:16], "url": str(ng.get("url") or "")[:500]}
        # Brain ĐANG MỞ lúc bấm Cài. Agent/workflow/skill thuộc về một brain cụ thể (khác
        # connector và plugin vốn dùng chung mọi brain), nên "cài vào tất cả" là áp đặt: người
        # dùng có brain việc và brain cá nhân, và họ không muốn mọi thứ ở cả hai nơi.
        root = _DEPS.brain_root(str(d.get("brain") or "brain"))
        r = pack_install.cai(str(d.get("staging_id") or ""),
                             str(d.get("consent_sha256") or ""),
                             enable=bool(d.get("enable")), nguon=ng,
                             brain_root=root)
        if r.get("ok"):
            _DEPS.lam_moi_hub()
            # The pack's assistants are back in the brain: the Auto registry takes its own back at once, so nobody
            # has to open the Partners page (or confirm 17 cards) before a team or a goal can use them again.
            await _agents_changed(root)
        return r if r.get("ok") else JSONResponse(r, status_code=400)

    @router.post("/packs/toggle")
    async def packs_toggle(request: Request):
        if not _DEPS.co_phien(request):
            return _tu_choi()
        d = await request.json()
        r = pack_install.dat_bat_tat(str(d.get("id") or ""), bool(d.get("enabled")))
        if r.get("ok"):
            _DEPS.lam_moi_hub()
        return r if r.get("ok") else JSONResponse(r, status_code=400)

    @router.get("/packs/uninstall-plan")
    async def packs_uninstall_plan(request: Request, id: str = "", brain: str = ""):
        if not _DEPS.co_phien(request):
            return _tu_choi()
        plan = pack_install.ke_hoach_go(id.strip())
        # #1308: the items sit in the brain that was open at install time. Name it, and say when that is not the
        # brain open now, so nobody removes assistants from a brain they are not looking at without being told.
        if isinstance(plan, dict) and plan.get("ok") and isinstance(plan.get("vault"), dict):
            w = _items_brain(id.strip(), brain)
            plan["vault"]["brain_name"] = w["name"]
            plan["vault"]["other_brain"] = w["other"]
        return plan

    @router.post("/packs/uninstall")
    async def packs_uninstall(request: Request):
        if not _DEPS.co_phien(request):
            return _tu_choi()
        d = await request.json()
        # BEFORE the files go: the registry records that these assistants are this pack's own (their origin), which
        # is what lets it take them back without asking when the pack is installed again. AFTER: it sees them gone.
        root = _pack_brain(str(d.get("id") or "").strip())
        await _agents_changed(root)
        r = await pack_install.go(str(d.get("id") or ""),
                                  purge_data=bool(d.get("purge_data")),
                                  purge_audit=bool(d.get("purge_audit")))
        if r.get("ok"):
            _DEPS.lam_moi_hub()
            await _agents_changed(root)
        return r if r.get("ok") else JSONResponse(r, status_code=409)

    @router.get("/packs/store")
    async def packs_store_list(request: Request, refresh: int = 0, brain: str = ""):
        """Danh mục gói trong kho. Fetch ở PHÍA SERVER, không ở trình duyệt.

        Ba lý do: chốt SSRF nằm ở server nên đường tải phải đi qua đó mới được gác; trình
        duyệt sẽ vướng CORS với phần lớn nơi đặt tệp; và nếu về sau có kho riêng cần token thì
        token không bao giờ nên rơi vào JavaScript."""
        if not _DEPS.co_phien(request):
            return _tu_choi()
        d = await packs_store.lay(lam_moi=bool(refresh))
        # Dịch vụ mà APP đang cấp. Gói trong kho cấp đúng id đó thì BỎ thẻ của kho đi: `packs.py`
        # từ chối cài một connector trùng id với kho gốc (một gói ship `id: pancake-pos` kèm
        # url khác sẽ âm thầm bẻ hướng một kết nối đang đăng nhập thật), nên thẻ đó bấm cũng
        # không cài được. Hiện hai thẻ cho cùng một dịch vụ, một cái vô dụng, là tệ hơn hẳn.
        #
        # Người dùng gỡ dịch vụ của app đi thì id thôi bị chiếm, thẻ của kho hiện ra và cài
        # được - đó chính là đường di trú dần từ app sang kho.
        app_dang_cap = _id_app_dang_cap()
        d["packs"] = [g for g in (d.get("packs") or [])
                      if not (set((g.get("provides") or {}).get("connectors") or [])
                              & app_dang_cap)]
        # Gói nào đã cài rồi thì đánh dấu, để lưới hiện "Đã cài" thay vì mời cài lại.
        da_cai = pack_install.doc_so()
        # 0.440.0: gói đổi mã khai `replaces`. Thẻ của mã cũ thôi hiện (gói mới đứng thay), và máy
        # đang cài mã cũ thấy thẻ mới ở trạng thái "đã cài, có bản mới": bấm cập nhật là trình cài
        # chuyển dữ liệu sang mã mới (pack_install._thay_the).
        bi_thay = {o for g in d.get("packs") or [] for o in (g.get("replaces") or [])}
        d["packs"] = [g for g in d.get("packs") or [] if g["id"] not in bi_thay]
        for g in d.get("packs") or []:
            hang = da_cai.get(g["id"])
            if not hang:
                cu = next((o for o in (g.get("replaces") or []) if o in da_cai), "")
                if cu:
                    hang = da_cai[cu]
                    g["replaces_installed"] = cu
            g["installed"] = bool(hang)
            g["installed_version"] = (hang or {}).get("version", "")
            # Owner report 2026-11-04: a pack that only brings agents/workflows/skills, whose items the
            # user deleted from the app, kept saying "Installed" with only an Uninstall button. Nothing of
            # it is left in the brain, so it is not installed: the card offers Install again.
            if hang and _gone_from_brain(g.get("replaces_installed") or g["id"], hang, g):
                g["installed"] = False
                g["removed_from_brain"] = True
            elif hang:
                # #1308: installed for the machine, but its assistants and skills are in another brain than the
                # one open now. The card says which, instead of a bare "Installed".
                w = _items_brain(g.get("replaces_installed") or g["id"], brain)
                if w["other"]:
                    g["items_brain"] = w["name"]
            # Thẻ cần biết gói đang bật hay tắt để vẽ đúng nút. Gói thả tay vào thư mục (không
            # có hàng trong sổ) mặc định là BẬT - người vận hành đã tự đặt nó vào rồi.
            g["enabled"] = bool(hang.get("enabled", True)) if hang else True
            g["nguon"] = "kho"
            g["nhom"] = _nhom(g)
        # Connector đi kèm app cũng hiện TRONG kho, đánh dấu sẵn là đã cài. Người dùng không
        # phân biệt "thứ ship theo app" với "thứ tải từ kho" - họ chỉ muốn một chỗ để nhìn xem
        # Javis nối được với cái gì. Trộn vào đây thì lưới Kết nối của kho có đủ mặt hàng ngay
        # từ ngày đầu, thay vì trống trơn cho tới khi ai đó phát hành gói connector.
        #
        # Chúng KHÔNG tải về từ đâu cả (`download.url` rỗng), và gỡ chúng đi qua `core_off`
        # chứ không qua trình gỡ gói - nên phải có `nguon` để giao diện biết bấm nút nào.
        (d.setdefault("packs", [])).extend(_connector_cua_app())
        return d

    @router.post("/packs/install-url")
    async def packs_install_url(request: Request):
        """Tải một gói từ địa chỉ rồi SOI như tệp tải lên. Chưa cài gì cả.

        Cố ý dừng ở bước soi: đường từ kho về máy không được phép ngắn hơn đường từ tệp. Cùng
        một màn hình xác nhận, cùng một chốt dấu vân tay - chỉ khác chỗ lấy byte."""
        if not _DEPS.co_phien(request):
            return _tu_choi()
        d = await request.json()
        try:
            url = packs_fetch.url_zip_github(str(d.get("url") or ""))
            du_lieu = await packs_fetch.tai(url)
        except packs_fetch.LoiTai as e:
            return JSONResponse({"ok": False, "stage": "download", "error": str(e)},
                                status_code=400)
        r = pack_install.soi(du_lieu, url.rsplit("/", 1)[-1] or "goi.zip")
        # Kho khai sẵn dấu vân tay thì đối chiếu NGAY: một tệp khác cái kho nói là dấu hiệu
        # đường tải bị chen ngang, và đó là lúc phải dừng chứ không phải lúc hỏi người dùng.
        mong = str(d.get("expect_sha256") or "").strip()
        if mong and r.get("ok") and r.get("sha256") != mong:
            return JSONResponse(
                {"ok": False, "stage": "verify",
                 "error": localefmt.chu("Tệp tải về không khớp dấu vân tay mà kho công bố. Đã dừng.",
                                         "The downloaded file does not match the fingerprint the store published. Stopped.")},
                status_code=400)
        r["source"] = {"kind": "url", "url": url}
        return r if r.get("ok") else JSONResponse(r, status_code=400)

    @router.get("/packs/token")
    async def packs_token_list(request: Request):
        """Danh sách host đã lưu token. KHÔNG bao giờ trả giá trị token."""
        if not _DEPS.co_phien(request):
            return _tu_choi()
        import config as cfgmod
        kho = (cfgmod.read_settings().get("packs") or {}).get("tokens") or {}
        return {"hosts": sorted(kho)}

    @router.post("/packs/token")
    async def packs_token_set(request: Request):
        """Lưu hoặc xoá token cho một host. Token được mã hoá khi ghi xuống đĩa."""
        if not _DEPS.co_phien(request):
            return _tu_choi()
        import config as cfgmod
        d = await request.json()
        host = str(d.get("host") or "").strip().lower()
        if not host or "/" in host or " " in host:
            return JSONResponse({"ok": False, "error": localefmt.chu("Tên máy không hợp lệ", "Invalid host name")}, status_code=400)
        tk = str(d.get("token") or "").strip()
        cfg = cfgmod.read_settings()
        kho = dict((cfg.get("packs") or {}).get("tokens") or {})
        if tk:
            kho[host] = tk
        else:
            kho.pop(host, None)
        cfg.setdefault("packs", {})["tokens"] = kho
        cfgmod.write_settings(cfg)
        return {"ok": True, "hosts": sorted(kho)}

    @router.get("/packs/{pid}/asset/{duong:path}")
    async def packs_asset(pid: str, duong: str):
        """Ảnh của gói. KHÔNG đòi phiên: nó đi vào thẻ <img> của trang Kết nối như mọi logo
        khác, và nội dung là thứ chính người dùng vừa cài. Bù lại thì chặt về KIỂU tệp."""
        f = packs.asset_path(pid, duong)
        if f is None or f.suffix.lower() not in ANH:
            return JSONResponse({"error": "not found"}, status_code=404)
        return FileResponse(str(f), media_type=ANH[f.suffix.lower()], headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "public, max-age=300",
        })

    return router


def register(app, deps: PacksDeps):
    """Gắn router vào app. Gọi ĐÚNG vị trí dòng cũ trong main.py - xem routes/__init__.py."""
    global _DEPS
    _DEPS = deps
    router = _make_router()
    app.include_router(router)
    return router
