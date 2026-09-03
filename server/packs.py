"""GÓI MỞ RỘNG: thả một thư mục vào `STATE_DIR/packs/` là có thêm connector, không cần ra bản mới.

Vì sao tồn tại
--------------
Đo trên repo ngày 2026-09-03: 524 lần bump VERSION trong ba tháng, 60 lần trong đó chỉ để sửa
`system/mcp-catalog.json`, tức thêm hoặc vá một connector. Nguyên nhân nằm ở đúng một dòng -
`mcp_catalog.CATALOG_PATH` trỏ cứng vào một file trong repo, và trên Docker cây code là
read-only nên không có đường nào khác ngoài ra bản mới.

Module này là NỬA KIA của `core_off.py`. Cùng một câu hỏi "ai quyết định kho có gì", hai chiều:
`core_off` BỚT khỏi kho gốc, `packs` THÊM vào. Cả hai ghi ở `STATE_DIR` vì cây code read-only
trên Docker (`Dockerfile:81,112`) và bị `git pull` ghi đè trên bản native.

Bố cục trên đĩa
---------------
    STATE_DIR/packs/<id>/
        javis-pack.yaml        manifest, giữ nguyên văn tác giả viết
        connectors/*.yaml      mỗi file một connector, khuôn y hệt một phần tử của
                               `connectors[]` trong system/mcp-catalog.json
        plugins/<slug>/        plugin.yaml + plugin.py - ĐỂ NGUYÊN TẠI CHỖ, không copy đi đâu
        assets/                icon
        pages/                 trang hướng dẫn

Plugin của gói nằm luôn trong thư mục gói chứ không copy sang `STATE_DIR/plugins/`: gỡ khi đó
là một lệnh rmtree chứ không phải đi diff xem file nào của ai. Việc NẠP plugin gói là chuyện
của giai đoạn sau, nên `plugin_dirs()` ở đây còn trả rỗng - nhưng bố cục đã đúng từ bây giờ để
lần đó không phải di trú.

Vì sao thả tay vào đây KHÔNG cần cổng env, còn `<brain>/plugins/` thì cần
---------------------------------------------------------------------
`plugins_host` bắt `JAVIS_ENABLE_USER_PLUGINS` cho plugin trong vault vì **model ghi được vào
vault**: `javis_write_file` mở đúng cây đó, nên "một thư mục ghi được" ở đấy nghĩa là code chạy
mà không ai bấm gì. `STATE_DIR/packs/` thì không tool nào của Javis ghi tới; ghi được vào đây
đòi quyền trên hệ tệp của máy chủ, tức đã tương đương quyền sửa mã nguồn - không còn gì để
cổng đó bảo vệ thêm.

Cổng thật sự cần nằm ở đường TẢI TỪ MẠNG (cài từ zip, URL, kho), và nó là màn hình đồng ý gắn
digest ở giai đoạn sau, chứ không phải một biến môi trường bật-tắt-tất-cả. `JAVIS_DISABLE_PACKS`
là công tắc tắt sạch cho ai cần.

Suy biến: hỏng thì THIẾU, không bao giờ THỪA
--------------------------------------------
Mọi lỗi ở đây (manifest sai, id trùng, trường bị cấm) đều dẫn tới "gói đó không nạp", kèm lý do
đọc được, chứ không bao giờ dẫn tới "nạp một phần" hay "ghi đè lên connector gốc". Kho gốc là
thứ đang chạy được; một file lạ trong STATE_DIR không được phép làm nó xấu đi.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading

import fastyaml
from config import STATE_DIR

PROJECT_ROOT = STATE_DIR.parent if (STATE_DIR / "..").is_dir() else STATE_DIR
PACKS_DIR = STATE_DIR / "packs"
MANIFEST_TEN = ("javis-pack.yaml", "javis-pack.yml")
# Sổ cài đặt. `pack_install` ghi, ở đây chỉ ĐỌC - và chỉ đọc đúng một trường `enabled`, để
# module này giữ nguyên luật "chỉ stdlib + config", không kéo theo cả tầng cài đặt vào đường
# nóng. Gói KHÔNG có trong sổ (thả tay vào thư mục) mặc định là BẬT: đó là cách dùng của người
# vận hành, họ đã tự tay đặt nó vào thì không phải bấm thêm một nút nữa.
LEDGER = STATE_DIR / "packs.json"

SPEC_HO_TRO = (1,)
FORMAT_MAGIC = "javis-pack"

# Cùng luật với `plugins_host._SLUG_RE`: id đi thẳng vào đường dẫn hệ tệp và vào tên module,
# nên nó phải hẹp trước khi có ai ghép chuỗi.
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

# Trường connector chỉ có nghĩa khi chạy MÃ hoặc LỆNH. Có mặt bất kỳ cái nào thì gói là bậc
# CODE. Danh sách này là mô tả, không phải cổng chặn: xem docstring đầu file.
_CODE_FIELD = ("command", "args", "env", "cred_dir", "isolate_home", "oauth_file",
               "needs_local_browser")

# Trường bị TỪ CHỐI THẲNG ở spec 1, nêu đích danh khi từ chối.
#   internal : `mcp_client._INTERNAL` là allowlist bảo vệ `importlib.import_module`, không phải
#              bảng tra - mở nó ra là cho gói nhập module server bất kỳ theo tên.
#   auth qr  : luồng QR là đường riêng của Zalo (`zalo_login.py` + ba endpoint + nhánh JS),
#              không phải thứ khai bằng dữ liệu.
_TRANSPORT_CAM = ("internal",)
_AUTH_TYPE_CAM = ("qr",)

_lock = threading.RLock()
_cache: dict = {"sig": None, "packs": [], "connectors": {}}


def tat_het() -> bool:
    """Công tắc tắt sạch mọi gói, đọc LIVE để dùng được khi không vào nổi dashboard."""
    return str(os.getenv("JAVIS_DISABLE_PACKS", "")).strip().lower() in ("1", "true", "yes", "on")


def _app_version() -> str:
    try:
        return (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _ver(s: str) -> tuple:
    """'0.55.20' -> (0, 55, 20). Phần không phải số về 0 để không bao giờ ném ra ngoài."""
    ra = []
    for phan in re.split(r"[.\-+]", str(s or "")):
        m = re.match(r"^(\d+)", phan)
        ra.append(int(m.group(1)) if m else 0)
    return tuple((ra + [0, 0, 0])[:3])


def _hop_compat(dai: str) -> tuple[bool, str]:
    """Dải kiểu '>=0.57.0 <2.0.0' có khớp VERSION hiện tại không. Trả (ok, lý do nếu không).

    Dải rỗng nghĩa là không giới hạn. Cú pháp lạ cũng coi là KHÔNG giới hạn chứ không phải
    không khớp: một manifest viết sai không đáng làm gói im lặng biến mất, và giai đoạn sau có
    trình cài để bắt lỗi tử tế hơn."""
    dai = str(dai or "").strip()
    if not dai:
        return True, ""
    hien = _ver(_app_version())
    for phan in dai.split():
        m = re.match(r"^(>=|<=|>|<|==|=)?\s*v?([0-9][0-9.\-+a-zA-Z]*)$", phan.strip())
        if not m:
            continue
        op, moc = m.group(1) or ">=", _ver(m.group(2))
        ok = {">=": hien >= moc, "<=": hien <= moc, ">": hien > moc,
              "<": hien < moc, "==": hien == moc, "=": hien == moc}[op]
        if not ok:
            return False, f"cần Javis {dai}, bản này là {_app_version()}"
    return True, ""


def _module_server() -> set:
    """Tên module top-level trong `server/`. Id gói trùng một trong số đó là bị từ chối.

    `server/` nằm trên `sys.path`, và `__init__.py` là entry file hợp lệ của plugin, nên một
    gói tên `config` có thể che module thật của server ở lần import sau."""
    try:
        return {p.stem for p in STATE_DIR.glob("*.py")}
    except OSError:
        return set()


def _ngon_ngu(v, mac_dinh=""):
    """`name`/`description` nhận cả chuỗi trần lẫn map đa ngôn ngữ. Trả về map đã chuẩn hoá."""
    if isinstance(v, dict):
        return {str(k): str(x) for k, x in v.items() if x}
    s = str(v or mac_dinh).strip()
    return {"en": s} if s else {}


def _chon(map_nn, lang="vi"):
    """Lấy bản dịch theo ngôn ngữ, rơi về en, rồi về giá trị đầu tiên có được."""
    if not map_nn:
        return ""
    return map_nn.get(lang) or map_nn.get("en") or next(iter(map_nn.values()), "")


def _doc_file(p):
    """Đọc YAML hoặc JSON theo đuôi file. Ném lỗi để người gọi gói vào lý do từ chối."""
    raw = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        return json.loads(raw)
    return fastyaml.safe_load(raw)


def _kiem_connector(con, thu_muc, id_da_co) -> tuple[bool, str]:
    """Một connector từ gói có được phép vào kho không. Trả (ok, lý do)."""
    cid = str((con or {}).get("id") or "").strip()
    if not cid:
        return False, "connector thiếu trường id"
    if not _ID_RE.match(cid):
        return False, f"id connector '{cid}' không hợp lệ"
    # Trùng id là TỪ CHỐI, không bao giờ ghi đè. Đây là luật quan trọng nhất trong file: một
    # gói ship `id: pancake-pos` kèm `url_template` trỏ đi chỗ khác sẽ âm thầm bẻ hướng một kết
    # nối ĐANG ĐĂNG NHẬP THẬT, vì `mcp_store.resolved` dựng lại url và header TỪ CONNECTOR ở
    # mỗi lần resolve. Không có `override` trong spec 1.
    if cid in id_da_co:
        return False, f"id connector '{cid}' đã có trong kho, gói không được ghi đè"
    tr = str(con.get("transport") or "http").lower()
    if tr in _TRANSPORT_CAM:
        return False, f"transport '{tr}' không cho phép trong gói"
    auth_type = str(((con.get("auth") or {}).get("type")) or "apikey").lower()
    if auth_type in _AUTH_TYPE_CAM:
        return False, f"cách đăng nhập '{auth_type}' không khai bằng gói được"
    icon = str(con.get("icon") or "")
    if icon.startswith(("http://", "https://", "//")):
        # Icon ở xa là một beacon nổ mỗi lần vẽ trang Kết nối, tức lộ IP và nhịp dùng của người
        # dùng cho bên phát hành gói. Icon phải nằm trong gói.
        return False, "icon phải là đường dẫn trong gói, không phải URL ngoài"
    if icon and (icon.startswith("/") or ".." in icon.replace("\\", "/").split("/")):
        return False, "đường dẫn icon không hợp lệ"
    return True, ""


def _tier(thu_muc, connectors) -> str:
    """'code' nếu gói chạy mã hoặc lệnh, 'data' nếu chỉ khai dữ liệu."""
    try:
        if any(thu_muc.rglob("*.py")):
            return "code"
    except OSError:
        pass
    for con in connectors:
        if str(con.get("transport") or "").lower() == "stdio":
            return "code"
        if any(con.get(k) for k in _CODE_FIELD):
            return "code"
        if (con.get("auth") or {}).get("exchange"):
            return "code"
    return "data"


def _nap_mot(thu_muc, id_da_co) -> dict:
    """Đọc và kiểm MỘT thư mục gói. Luôn trả về một bản ghi, kể cả khi hỏng."""
    pid = thu_muc.name
    ban = {"id": pid, "dir": str(thu_muc), "ok": False, "error": "", "enabled": True,
           "name": {}, "description": {}, "version": "", "author": {}, "tier": "data",
           "connectors": [], "_con_objs": []}

    manifest = next((thu_muc / t for t in MANIFEST_TEN if (thu_muc / t).is_file()), None)
    if manifest is None:
        ban["error"] = "thiếu javis-pack.yaml"
        return ban
    try:
        m = _doc_file(manifest)
        if not isinstance(m, dict):
            raise ValueError("manifest phải là một object")
    except Exception as e:
        ban["error"] = f"manifest lỗi: {type(e).__name__}: {e}"
        return ban

    if str(m.get("format") or "") != FORMAT_MAGIC:
        ban["error"] = f"không phải gói Javis (thiếu format: {FORMAT_MAGIC})"
        return ban
    try:
        spec = int(m.get("spec") or 0)
    except (TypeError, ValueError):
        spec = -1
    if spec not in SPEC_HO_TRO:
        ban["error"] = f"spec {m.get('spec')!r} chưa hỗ trợ (bản này đọc {SPEC_HO_TRO})"
        return ban

    khai_id = str(m.get("id") or "").strip()
    if not _ID_RE.match(pid):
        ban["error"] = f"tên thư mục '{pid}' không hợp lệ làm id gói"
        return ban
    if khai_id and khai_id != pid:
        # Id là ĐƯỜNG DẪN, nên tên thư mục mới là sự thật. Manifest khai lệch thì từ chối chứ
        # không im lặng chọn một bên: hai chỗ nói hai kiểu là mầm của mọi nhầm lẫn về sau.
        ban["error"] = f"id trong manifest ('{khai_id}') khác tên thư mục ('{pid}')"
        return ban
    if pid in _module_server():
        ban["error"] = f"id '{pid}' trùng tên một module của Javis, đổi tên gói"
        return ban

    ok, vi_sao = _hop_compat((m.get("compat") or {}).get("app"))
    if not ok:
        ban["error"] = vi_sao
        return ban

    ban.update(name=_ngon_ngu(m.get("name"), pid), description=_ngon_ngu(m.get("description")),
               version=str(m.get("version") or ""), author=(m.get("author") or {}),
               homepage=str(m.get("homepage") or ""), license=str(m.get("license") or ""))

    cons, loi = [], []
    for rel in ((m.get("provides") or {}).get("connectors") or []):
        p = (thu_muc / str(rel)).resolve()
        try:
            if thu_muc.resolve() not in p.parents:
                loi.append(f"{rel}: trỏ ra ngoài thư mục gói")
                continue
            con = _doc_file(p)
        except Exception as e:
            loi.append(f"{rel}: {type(e).__name__}: {e}")
            continue
        if not isinstance(con, dict):
            loi.append(f"{rel}: phải là một object")
            continue
        hop, vs = _kiem_connector(con, thu_muc, id_da_co)
        if not hop:
            loi.append(f"{rel}: {vs}")
            continue
        con = dict(con)
        con["_pack"] = pid
        con["_pack_name"] = _chon(ban["name"], "vi") or pid
        # Connector từ gói LUÔN bắt đầu ở mức chỉ đọc, bất kể manifest khai gì. Người dùng tự
        # nâng từng kết nối qua trang Kết nối, nơi cảnh báo rủi ro đã có sẵn - đó là chỗ đúng
        # để quyết định, vì nó theo TÀI KHOẢN chứ không theo tác giả gói.
        con["default_perm"] = "readonly"
        cons.append(con)
        id_da_co.add(con["id"])

    ban["_con_objs"] = cons
    ban["connectors"] = [c["id"] for c in cons]
    ban["tier"] = _tier(thu_muc, cons)
    ban["ok"] = True
    if loi:
        ban["error"] = "; ".join(loi)   # gói vẫn dùng được phần lành, nhưng phải NÓI ra phần hỏng
    return ban


def _quet():
    """Quét lại toàn bộ thư mục gói. Có cache theo chữ ký, xem `signature()`."""
    with _lock:
        sig = signature()
        if _cache["sig"] == sig:
            return _cache["packs"], _cache["connectors"]
        packs, connectors = [], {}
        if not tat_het() and PACKS_DIR.is_dir():
            try:
                import mcp_catalog
                id_da_co = set(mcp_catalog.tat_ca())
            except Exception:
                id_da_co = set()
            so = _so_cai_dat()
            for d in sorted(PACKS_DIR.iterdir()):
                if not d.is_dir() or d.name.startswith((".", "_")):
                    continue
                hang = so.get(d.name)
                if hang is not None and not hang.get("enabled", True):
                    # Gói TẮT: vẫn liệt kê để còn bật lại được, nhưng không góp connector nào.
                    packs.append({"id": d.name, "dir": str(d), "ok": True, "error": "",
                                  "name": {}, "description": {}, "enabled": False,
                                  "version": str(hang.get("version") or ""),
                                  "author": {}, "tier": str(hang.get("tier") or "data"),
                                  "connectors": []})
                    continue
                ban = _nap_mot(d, id_da_co)
                ban["enabled"] = True
                for con in ban.pop("_con_objs", []):
                    connectors[con["id"]] = con
                packs.append(ban)
        _cache.update(sig=sig, packs=packs, connectors=connectors)
        return packs, connectors


def _so_cai_dat() -> dict:
    """Đọc sổ cài đặt. Hỏng hay thiếu thì coi như sổ rỗng, tức mọi gói trên đĩa đều bật."""
    try:
        d = json.loads(LEDGER.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def signature():
    """Chữ ký để `mcp_catalog.load()` gộp vào khoá cache của nó.

    Gộp mtime của THƯ MỤC gói và của từng manifest, không quét sâu: thêm hoặc bớt một thư mục
    con đã làm mtime thư mục cha đổi, còn sửa nội dung một manifest thì mtime file đó đổi. Đủ
    để bắt mọi thao tác thật mà vẫn chỉ vài lệnh stat - hàm này nằm trên đường nóng, mỗi lượt
    chat đều gọi qua `mcp_catalog.load()`."""
    if tat_het():
        return "off"
    try:
        st = PACKS_DIR.stat()
    except OSError:
        return None
    phan = [(st.st_mtime_ns, st.st_size)]
    try:
        s = LEDGER.stat()
        phan.append(("_so", s.st_mtime_ns, s.st_size))
    except OSError:
        pass
    try:
        for d in sorted(PACKS_DIR.iterdir()):
            if not d.is_dir():
                continue
            for ten in MANIFEST_TEN:
                f = d / ten
                if f.is_file():
                    s = f.stat()
                    phan.append((d.name, s.st_mtime_ns, s.st_size))
                    break
            else:
                phan.append((d.name, 0, 0))
    except OSError:
        return None
    return tuple(phan)


def connector_layers() -> dict:
    """Connector do gói cung cấp, dạng {id: connector}. `mcp_catalog.load()` phủ cái này lên kho gốc."""
    return dict(_quet()[1])


def installed() -> list:
    """Danh sách gói đã cài, kèm lý do nếu cái nào không nạp được."""
    return [dict(p) for p in _quet()[0]]


def plugin_dirs(vault_root=None) -> list:
    """Thư mục plugin của các gói. Còn RỖNG ở giai đoạn này.

    Bố cục `packs/<id>/plugins/<slug>/` đã đúng từ bây giờ, nên khi `plugins_host` học nguồn
    thứ tư thì đó là một dòng chèn vào `_iter_plugin_dirs`, không phải một lần di trú."""
    return []


def _trong_goi(pid: str, rel: str, thu_muc_con: str):
    """Đường dẫn tuyệt đối tới một file trong gói, hoặc None nếu trỏ ra ngoài.

    Chốt cùng kiểu `purge._ben_trong`: resolve CẢ HAI vế rồi so, vì chỉ resolve một vế thì một
    symlink trong gói trỏ ra `.secret_key` vẫn lọt và được phục vụ lại qua HTTP."""
    if not _ID_RE.match(str(pid or "")):
        return None
    goc = (PACKS_DIR / pid / thu_muc_con)
    p = (goc / str(rel or "")).resolve()
    try:
        if goc.resolve() not in p.parents and p != goc.resolve():
            return None
    except OSError:
        return None
    return p if p.is_file() else None


def asset_path(pid: str, rel: str):
    return _trong_goi(pid, rel, "assets")


def page_path(pid: str, rel: str):
    return _trong_goi(pid, rel, "pages")


def invalidate():
    with _lock:
        _cache.update(sig=None, packs=[], connectors={})
