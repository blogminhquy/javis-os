"""Cài và GỠ gói mở rộng: mở file zip, soi, hỏi, rồi mới đặt vào kho.

Vì sao tách khỏi `packs.py`
---------------------------
`packs.py` nằm trên ĐƯỜNG NÓNG: `mcp_catalog.load()` gọi nó mỗi lượt chat, và nó có luật chỉ
được import `config`, `secrets_store`, `fastyaml` và stdlib để không bao giờ vướng vòng import
hay deadlock với `plugins_host`. File này thì ngược lại - cài gói là việc HIẾM, xảy ra vài lần
trong đời một bản cài, và nó cần chạm `purge`, `mcp_hub`, `mcp_store`. Hai nhịp khác nhau thì
để hai chỗ.

Cài hai bước, và bước một KHÔNG đặt gì vào kho
---------------------------------------------
`soi()` mở zip, kiểm mọi luật, giải nén vào `packs-staging/` rồi trả về đúng những gì sắp xảy
ra kèm `sha256` của file. `cai()` chỉ nhận nếu người gọi đưa lại đúng cái sha256 đó. Ràng buộc
này làm **cái đã hiện ra trên màn hình phải chính là cái được cài**: không có khe nào để nội
dung đổi giữa lúc người dùng đọc và lúc họ bấm.

Staging nằm NGOÀI `packs/` có chủ ý: `packs._quet()` chỉ quét `packs/`, nên một gói đang chờ
xác nhận không bao giờ được nạp nửa chừng.

Luật zip: mặc định TỪ CHỐI
--------------------------
Một file zip từ người lạ là dữ liệu thù địch cho tới khi chứng minh ngược lại. Các luật dưới
đây đều từng là lỗ thật ở đâu đó, không phải phòng xa:

- **Traversal** (`../../x`) và **đường dẫn tuyệt đối**: ghi đè file ngoài thư mục gói.
- **Symlink**: một member tên `plugin.py` trỏ tới `.secret_key` sẽ được mọi endpoint đọc file
  phục vụ lại nguyên vẹn. `zipfile` KHÔNG tự chặn, phải soi `external_attr`.
- **Bit thực thi**: không bao giờ nghe mode trong archive, luôn đặt 0o644 / 0o755.
- **Tỉ lệ nén**: 42 KB nở thành 4 GB là một cách làm hết đĩa máy chủ.
- **Tên nhạy cảm** (`.env`, `*.pem`, `id_rsa*`): không phải thứ một gói cần mang theo, mà lại
  đúng thứ trông giống file thật khi lẫn vào cây thư mục.
- **Chỉ zip, không tar**: `TarFile.extractall` trên Python 3.12 vẫn mặc định `filter=None`,
  tức vẫn theo symlink và đường dẫn tuyệt đối. Không mở cửa đó.
- **Trần kích thước manifest** trước khi `safe_load`: `SafeLoader` vẫn nở anchor, và vài MB
  alias là một lần OOM.

Gỡ thì phải sạch, và kết nối theo gói bị xoá THEO
-------------------------------------------------
Không có đường "giữ kết nối lại cho chắc". Một kết nối mồ côi là một hàng vẫn giữ command,
url và secret của nó; `mcp_store.resolved` nay từ chối dựng dial spec cho nó, nhưng để lại một
hàng chết mang credential thì vẫn là để lại credential. Hộp thoại nêu tên từng kết nối và người
dùng xác nhận, chứ không có đường im lặng.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import sys
import time
import zipfile
from pathlib import Path

import packs
from config import STATE_DIR

LEDGER = STATE_DIR / "packs.json"
STAGING = STATE_DIR / "packs-staging"

# Trần. Con số chọn rộng rãi so với một gói thật (manifest + vài YAML + vài icon), nhưng đủ
# chặt để một file ác ý không làm hết đĩa.
MAX_ZIP = 25 * 1024 * 1024        # file nén tải lên
MAX_GIAI_NEN = 40 * 1024 * 1024   # tổng sau khi giải nén
MAX_MOT_TEP = 5 * 1024 * 1024
MAX_SO_TEP = 500
MAX_TI_LE = 100                   # nén/giải nén, chống zip bomb
MAX_MANIFEST = 256 * 1024
STAGING_TTL = 30 * 60             # dọn thứ soi mà không cài, sau 30 phút

# Thư mục cấp một được phép có trong gói. Cái lạ thì BỎ QUA im lặng (gói có thể mang theo
# README, LICENSE, .github...), nhưng tên nhạy cảm thì TỪ CHỐI cả gói.
_TOP_CHO_PHEP = ("connectors", "plugins", "assets", "pages", "docs")
_TEN_CAM = (".env", ".git", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519")
_DUOI_CAM = (".pem", ".p12", ".pfx", ".key", ".ppk")


def _now() -> float:
    return time.time()


# ─────────────────────────── sổ cài đặt ───────────────────────────

def doc_so() -> dict:
    try:
        d = json.loads(LEDGER.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except OSError:
        return {}
    except Exception as e:
        print(f"[packs] sổ cài đặt hỏng: {e}", file=sys.stderr)
        # Sổ hỏng thì thử bản .bak. Mất sổ nghĩa là mất bản ghi ĐỒNG Ý cho gói có mã, và hệ
        # quả đúng hướng an toàn: gói đó sẽ hỏi lại chứ không tự chạy.
        try:
            return json.loads(LEDGER.with_suffix(".json.bak").read_text(encoding="utf-8"))
        except Exception:
            return {}


def _ghi_so(d: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    if LEDGER.is_file():
        try:
            shutil.copy2(LEDGER, LEDGER.with_suffix(".json.bak"))
        except OSError:
            pass
    tmp = LEDGER.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(LEDGER)
    packs.invalidate()


# ─────────────────────────── luật zip ───────────────────────────

def _la_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK((info.external_attr >> 16) & 0o170000)


def _ten_xau(ten: str) -> str:
    """Lý do từ chối một member, hoặc chuỗi rỗng nếu member đó ổn."""
    t = ten.replace("\\", "/")
    if t.startswith("/") or (len(t) > 1 and t[1] == ":"):
        return "đường dẫn tuyệt đối"
    phan = [x for x in t.split("/") if x]
    if any(x == ".." for x in phan):
        return "đường dẫn leo ra ngoài"
    for x in phan:
        thap = x.lower()
        if thap in _TEN_CAM or thap.startswith("id_rsa"):
            return f"tên tệp không cho phép: {x}"
        if any(thap.endswith(d) for d in _DUOI_CAM):
            return f"tệp khoá riêng không cho phép: {x}"
    return ""


def _goc_chung(ten_list) -> str:
    """Thư mục gốc chung nếu zip được nén kèm một lớp thư mục bọc ngoài.

    GitHub zipball và cách nén tay phổ biến đều gói mọi thứ trong một thư mục
    `<repo>-<sha>/`. Nhận ra và bóc nó ra, nếu không thì manifest nằm sâu một tầng và gói nào
    cũng bị báo là thiếu manifest."""
    goc = set()
    for t in ten_list:
        phan = [x for x in t.replace("\\", "/").split("/") if x]
        if len(phan) < 2:
            return ""      # có file ở cấp một -> không có lớp bọc
        goc.add(phan[0])
    return goc.pop() if len(goc) == 1 else ""


def _kiem_zip(zf: zipfile.ZipFile) -> tuple[list, str, str]:
    """Duyệt mọi member, áp mọi luật. Trả (danh sách member giữ lại, gốc chung, lý do từ chối)."""
    infos = [i for i in zf.infolist() if not i.is_dir()]
    if not infos:
        return [], "", "tệp nén rỗng"
    if len(infos) > MAX_SO_TEP:
        return [], "", f"quá nhiều tệp ({len(infos)} > {MAX_SO_TEP})"
    tong = 0
    for i in infos:
        if _la_symlink(i):
            return [], "", f"chứa liên kết tượng trưng: {i.filename}"
        vs = _ten_xau(i.filename)
        if vs:
            return [], "", f"{vs} ({i.filename})"
        if i.file_size > MAX_MOT_TEP:
            return [], "", f"tệp quá lớn: {i.filename}"
        if i.compress_size and i.file_size / max(i.compress_size, 1) > MAX_TI_LE:
            return [], "", f"tỉ lệ nén bất thường ở {i.filename}"
        tong += i.file_size
        if tong > MAX_GIAI_NEN:
            return [], "", "tổng dung lượng sau giải nén vượt trần"
    return infos, _goc_chung([i.filename for i in infos]), ""


def _giai_nen(zf, infos, goc, dich: Path) -> None:
    """Giải nén thủ công, không dùng extractall: mode do MÌNH đặt, không nghe archive."""
    for i in infos:
        ten = i.filename.replace("\\", "/")
        if goc:
            ten = ten[len(goc) + 1:] if ten.startswith(goc + "/") else ten
        if not ten:
            continue
        ra = (dich / ten).resolve()
        if dich.resolve() not in ra.parents:
            raise ValueError(f"member thoát khỏi thư mục đích: {i.filename}")
        ra.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(i) as src, open(ra, "wb") as f:
            shutil.copyfileobj(src, f, 64 * 1024)
        try:
            os.chmod(ra, 0o644)
        except OSError:
            pass


# ─────────────────────────── soi rồi cài ───────────────────────────

def don_staging(ttl: int = STAGING_TTL) -> int:
    """Dọn thứ đã soi mà không cài. Trả về số mục đã dọn."""
    if not STAGING.is_dir():
        return 0
    # ttl <= 0 nghĩa là "không giữ gì", nên phải dọn CẢ thứ vừa tạo xong. So sánh chặt với
    # `_now() - 0` thì một thư mục tạo cùng nhịp đồng hồ lại thoát - đúng ca mà người gọi
    # `don_staging(0)` muốn dọn nhất.
    han, n = (_now() + 1 if ttl <= 0 else _now() - ttl), 0
    for p in list(STAGING.iterdir()):
        try:
            if p.stat().st_mtime < han:
                shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink()
                n += 1
        except OSError:
            continue
    return n


def soi(du_lieu: bytes, ten_tep: str = "") -> dict:
    """Mở zip, kiểm mọi luật, giải nén vào staging. KHÔNG đặt gì vào kho.

    Trả về đúng cái sẽ hiện lên màn hình xác nhận, kèm `sha256` để `cai()` đối chiếu."""
    don_staging()
    if len(du_lieu) > MAX_ZIP:
        return {"ok": False, "stage": "verify",
                "error": f"tệp quá lớn ({len(du_lieu) // 1024 // 1024}MB, trần "
                         f"{MAX_ZIP // 1024 // 1024}MB)"}
    sha = hashlib.sha256(du_lieu).hexdigest()
    # Bố cục staging: STAGING/<sha>/<pid>/. Lớp <sha> là thư mục BỌC, còn <pid> mới là thư mục
    # gói - `packs._nap_mot` lấy TÊN THƯ MỤC làm id, nên nó phải đúng bằng id trong manifest,
    # y hệt lúc đã cài thật. Thiếu lớp bọc thì tên thư mục thành `<sha>` và mọi gói đều bị báo
    # "tên thư mục không hợp lệ làm id".
    boc = STAGING / sha
    kho = boc / "_giai-nen"
    STAGING.mkdir(parents=True, exist_ok=True)
    if boc.is_dir():
        shutil.rmtree(boc, ignore_errors=True)

    tam_zip = STAGING / f"{sha}.zip"
    tam_zip.write_bytes(du_lieu)
    try:
        with zipfile.ZipFile(tam_zip) as zf:
            infos, goc, vs = _kiem_zip(zf)
            if vs:
                return {"ok": False, "stage": "verify", "error": vs}
            kho.mkdir(parents=True, exist_ok=True)
            _giai_nen(zf, infos, goc, kho)
    except zipfile.BadZipFile:
        return {"ok": False, "stage": "verify", "error": "không phải tệp .zip hợp lệ"}
    except Exception as e:
        shutil.rmtree(kho, ignore_errors=True)
        return {"ok": False, "stage": "extract", "error": f"{type(e).__name__}: {e}"}
    finally:
        try:
            tam_zip.unlink()
        except OSError:
            pass

    manifest = next((kho / t for t in packs.MANIFEST_TEN if (kho / t).is_file()), None)
    if manifest is None:
        shutil.rmtree(kho, ignore_errors=True)
        return {"ok": False, "stage": "validate", "error": "trong gói không có javis-pack.yaml"}
    if manifest.stat().st_size > MAX_MANIFEST:
        shutil.rmtree(kho, ignore_errors=True)
        return {"ok": False, "stage": "validate", "error": "manifest quá lớn"}

    # Id là TÊN THƯ MỤC, mà zip thì chưa có thư mục nào - nên lấy từ manifest rồi đổi tên thư
    # mục staging cho khớp, để `packs._nap_mot` kiểm được đúng như lúc đã cài thật.
    try:
        m = packs._doc_file(manifest)
        pid = str((m or {}).get("id") or "").strip()
    except Exception as e:
        shutil.rmtree(kho, ignore_errors=True)
        return {"ok": False, "stage": "validate", "error": f"manifest lỗi: {e}"}
    if not packs._ID_RE.match(pid):
        shutil.rmtree(kho, ignore_errors=True)
        return {"ok": False, "stage": "validate", "error": f"id gói không hợp lệ: {pid!r}"}

    tam = boc / pid
    if tam.is_dir():
        shutil.rmtree(tam, ignore_errors=True)
    kho.replace(tam)

    try:
        import mcp_catalog
        da_co = set(mcp_catalog.tat_ca()) | set(packs.connector_layers())
    except Exception:
        da_co = set()
    da_cai = doc_so().get(pid)
    if da_cai:
        # Nâng cấp chính gói này: connector cũ của nó không tính là "đã có", nếu không thì
        # mọi bản nâng cấp đều tự báo trùng với chính mình.
        da_co -= set(da_cai.get("connectors") or [])

    ban = packs._nap_mot(tam, da_co)
    py = sorted(str(p.relative_to(tam)).replace("\\", "/") for p in tam.rglob("*.py"))

    # Plugin trong gói: liệt kê để hiện lên màn hình xác nhận, và TỪ CHỐI nếu trùng tên một
    # plugin đi kèm app. Chặn ở đây chứ không lúc nạp, vì một gói lặng lẽ thay `javis_task`
    # hay `javis_schedule` dưới một màn hình chỉ nói "gói này chạy mã" là đúng kiểu bất ngờ
    # không nên có - người dùng phải thấy lý do TRƯỚC khi có gì rơi xuống đĩa.
    plugin_slugs = []
    goc_pl = tam / "plugins"
    if goc_pl.is_dir():
        for d in sorted(goc_pl.iterdir()):
            if d.is_dir() and any((d / e).is_file() for e in ("plugin.py", "__init__.py")):
                plugin_slugs.append(d.name)
    try:
        import plugins_host
        trung = sorted(set(plugin_slugs) & plugins_host._slug_bundled())
    except Exception:
        trung = []
    if trung:
        shutil.rmtree(boc, ignore_errors=True)
        return {"ok": False, "stage": "validate",
                "error": ("gói mang plugin trùng tên plugin có sẵn của Javis: "
                          + ", ".join(trung) + ". Đổi tên trong gói rồi thử lại.")}
    return {
        "ok": bool(ban["ok"]), "stage": "" if ban["ok"] else "validate",
        "error": ban["error"] if not ban["ok"] else "",
        "warning": ban["error"] if ban["ok"] else "",
        "staging_id": sha, "sha256": sha, "filename": ten_tep,
        "id": pid, "name": ban["name"], "description": ban["description"],
        "version": ban["version"], "author": ban.get("author") or {},
        "tier": ban["tier"], "connectors": ban["connectors"], "plugins": plugin_slugs,
        "py_files": py, "size": len(du_lieu),
        "da_cai": ({"version": da_cai.get("version")} if da_cai else None),
    }


def cai(staging_id: str, consent_sha256: str, *, enable: bool = False,
        nguon: dict = None) -> dict:
    """Đặt gói đã soi vào kho. Nguyên tử, hỏng ở bước nào cũng trả lại nguyên trạng."""
    sha = str(staging_id or "").strip()
    boc = STAGING / sha
    if not sha or not boc.is_dir() or STAGING.resolve() not in boc.resolve().parents:
        return {"ok": False, "stage": "commit", "error": "bản soi đã hết hạn, hãy chọn lại tệp"}
    if not consent_sha256 or consent_sha256 != sha:
        # Ràng buộc cốt lõi của luồng hai bước: cái đã hiện ra phải chính là cái được cài.
        return {"ok": False, "stage": "commit",
                "error": "nội dung gói đã đổi so với lúc xem, hãy xem lại"}
    con = [d for d in boc.iterdir() if d.is_dir()]
    if len(con) != 1:
        return {"ok": False, "stage": "commit", "error": "bản soi hỏng, hãy chọn lại tệp"}
    tam, pid = con[0], con[0].name
    if not packs._ID_RE.match(pid):
        return {"ok": False, "stage": "commit", "error": "id gói không hợp lệ"}
    # Từ chối cài lại đúng thứ bản soi đã báo hỏng. Không có nó thì một gói manifest sai vẫn
    # vào được kho chỉ vì người dùng bấm qua màn hình cảnh báo.
    kiem = packs._nap_mot(tam, set())
    if not kiem["ok"]:
        return {"ok": False, "stage": "validate", "error": kiem["error"]}

    packs.PACKS_DIR.mkdir(parents=True, exist_ok=True)
    dich = packs.PACKS_DIR / pid
    rac = packs.PACKS_DIR / f".trash-{pid}-{int(_now())}"
    da_doi = False
    try:
        if dich.exists():
            # os.replace lên một thư mục KHÔNG rỗng ném lỗi trên cả Windows lẫn POSIX, nên
            # phải dời bản cũ đi trước rồi mới đặt bản mới vào.
            dich.replace(rac)
            da_doi = True
        shutil.move(str(tam), str(dich))
        shutil.rmtree(boc, ignore_errors=True)
    except Exception as e:
        if da_doi and not dich.exists():
            try:
                rac.replace(dich)
            except OSError:
                pass
        return {"ok": False, "stage": "commit", "error": f"{type(e).__name__}: {e}"}
    finally:
        if da_doi and rac.exists() and dich.exists():
            shutil.rmtree(rac, ignore_errors=True)

    packs.invalidate()
    ban = next((p for p in packs.installed() if p["id"] == pid), None)
    so = doc_so()
    so[pid] = {
        "version": (ban or {}).get("version", ""),
        "enabled": bool(enable),
        "tier": (ban or {}).get("tier", "data"),
        "installed_at": _now(),
        "sha256": sha,
        "source": nguon or {"kind": "zip"},
        # Chữ ký nội dung mã: giai đoạn sau đối chiếu lại lúc NẠP, không chỉ lúc cài. Ai ghi
        # được plugin.py thì cũng ghi được sổ này, nên chốt phải nằm ở chỗ nạp.
        "code_digest": _digest_ma(dich),
        "connectors": (ban or {}).get("connectors") or [],
        "plugins": sorted(d.name for d in (dich / "plugins").iterdir()
                          if d.is_dir()) if (dich / "plugins").is_dir() else [],
    }
    _ghi_so(so)
    return {"ok": True, "id": pid, "enabled": bool(enable),
            "tier": (ban or {}).get("tier", "data"),
            "connectors": (ban or {}).get("connectors") or [],
            "warning": (ban or {}).get("error") or ""}


def _digest_ma(thu_muc: Path) -> str:
    """SHA256 của mọi file .py trong gói, theo thứ tự đường dẫn. Rỗng nếu gói không có mã."""
    h = hashlib.sha256()
    co = False
    for p in sorted(thu_muc.rglob("*.py")):
        try:
            h.update(str(p.relative_to(thu_muc)).replace("\\", "/").encode("utf-8"))
            h.update(p.read_bytes())
            co = True
        except OSError:
            continue
    return h.hexdigest() if co else ""


def dat_bat_tat(pid: str, bat: bool) -> dict:
    so = doc_so()
    if pid not in so:
        return {"ok": False, "error": "gói này không có trong sổ cài đặt"}
    so[pid]["enabled"] = bool(bat)
    _ghi_so(so)
    return {"ok": True, "enabled": bool(bat)}


# ─────────────────────────── gỡ ───────────────────────────

def quet_tuong_thich() -> list:
    """Lúc khởi động: TẮT gói có dải `compat.app` không còn khớp phiên bản Javis hiện tại.

    Vì sao cần dù trình cài đã kiểm: `update.sh` chạy `git pull` và `updater.py` chạy
    `git reset --hard`, không cái nào chạy lại trình cài. Không có lượt quét này thì dải
    `compat` chỉ có tác dụng đúng một lần, ở lần cài đầu tiên - tức là trang trí.

    TẮT chứ không xoá, và ghi lý do: hạ cấp Javis rồi nâng lại là gói tự chạy tiếp."""
    ra = []
    so = doc_so()
    doi = False
    for ban in packs.installed():
        pid = ban["id"]
        hang = so.get(pid)
        if not hang or not hang.get("enabled", True):
            continue
        mf = Path(ban["dir"])
        m = next((mf / x for x in packs.MANIFEST_TEN if (mf / x).is_file()), None)
        if m is None:
            continue
        try:
            dai = ((packs._doc_file(m) or {}).get("compat") or {}).get("app")
        except Exception:
            continue
        ok, vi_sao = packs._hop_compat(dai)
        if not ok:
            hang["enabled"] = False
            hang["disabled_reason"] = vi_sao
            doi = True
            ra.append({"id": pid, "reason": vi_sao})
            print(f"[packs] tắt '{pid}': {vi_sao}", file=sys.stderr)
    if doi:
        _ghi_so(so)
    return ra


def ke_hoach_go(pid: str) -> dict:
    """Gỡ gói này thì mất những gì. Hộp thoại vẽ từ đúng kết quả này."""
    ban = next((p for p in packs.installed() if p["id"] == pid), None)
    if ban is None:
        return {"ok": False, "error": "không tìm thấy gói"}
    try:
        import mcp_store
        ket_noi = [{"id": c["id"], "label": c.get("label") or c["id"]}
                   for c in mcp_store.list_connections()
                   if c.get("connector_id") in set(ban["connectors"])]
    except Exception:
        ket_noi = []
    thu_muc = Path(ban["dir"])
    try:
        co = sum(f.stat().st_size for f in thu_muc.rglob("*") if f.is_file())
    except OSError:
        co = 0
    du_lieu = STATE_DIR / "plugin-data"
    co_du_lieu = [d.name for d in du_lieu.iterdir()
                  if d.is_dir() and (thu_muc / "plugins" / d.name).is_dir()] \
        if du_lieu.is_dir() else []
    return {"ok": True, "id": pid, "name": ban["name"], "tier": ban["tier"],
            "connectors": ban["connectors"], "connections": ket_noi,
            "bytes": co, "plugin_data": co_du_lieu}


async def go(pid: str, *, purge_data: bool = False, purge_audit: bool = False) -> dict:
    """Gỡ gói và dọn theo. Kết nối tạo từ connector của gói bị xoá THEO, không có đường giữ lại.

    Vì sao không cho giữ: một kết nối mồ côi vẫn là một hàng mang command, url và secret của
    nó. `mcp_store.resolved` nay từ chối dựng dial spec cho nó, nên nó không chạy - nhưng để
    lại một hàng chết mang credential thì vẫn là để lại credential. Hộp thoại nêu tên từng cái
    và người dùng xác nhận trước; đó là chỗ để quyết định, không phải một ô tick ẩn."""
    ke = ke_hoach_go(pid)
    if not ke.get("ok"):
        return ke
    bao = {"ok": True, "id": pid, "connections_purged": [], "errors": []}

    import purge
    for kn in ke["connections"]:
        try:
            r = await purge.purge_connection(kn["id"], mode="trash", purge_audit=purge_audit)
            if r.get("busy"):
                return {"ok": False, "busy": True,
                        "error": f"Kết nối '{kn['label']}' đang chạy dở một việc. "
                                 f"Chờ nó xong rồi gỡ."}
            bao["connections_purged"].append(kn["label"])
        except Exception as e:
            bao["errors"].append(f"{kn['label']}: {e}")

    # DỪNG plugin của gói trước khi đụng tới thư mục: `unload` chạy on_unload rồi pop module
    # khỏi sys.modules. Thiếu bước này thì gói đã gỡ mà mã của nó còn sống trong tiến trình,
    # cùng mọi thread hay socket nó mở ra - một câu khó nói cho xuôi.
    try:
        import plugins_host
        for slug in (doc_so().get(pid) or {}).get("plugins") or []:
            plugins_host.unload(slug)
        plugins_host.invalidate()
    except Exception as e:
        bao["errors"].append(f"dừng plugin của gói: {e}")

    thu_muc = packs.PACKS_DIR / pid
    if thu_muc.is_dir() and packs.PACKS_DIR.resolve() in thu_muc.resolve().parents:
        rac = packs.PACKS_DIR / f".trash-{pid}-{int(_now())}"
        try:
            thu_muc.replace(rac)
            shutil.rmtree(rac, ignore_errors=True)
        except OSError as e:
            bao["errors"].append(f"xoá thư mục gói: {e}")

    if purge_data:
        for slug in ke.get("plugin_data") or []:
            d = STATE_DIR / "plugin-data" / slug
            if d.is_dir() and (STATE_DIR / "plugin-data").resolve() in d.resolve().parents:
                shutil.rmtree(d, ignore_errors=True)

    so = doc_so()
    so.pop(pid, None)
    _ghi_so(so)

    try:
        import mcp_hub
        mcp_hub.invalidate_cache()
    except Exception as e:
        bao["errors"].append(f"làm mới cache: {e}")
    return bao
