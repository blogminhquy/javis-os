"""Lời mời tặng sao Javis trên GitHub (0.324.0, chủ repo 25/10/2026).

Chủ repo muốn tăng sao cho dự án bằng một lời mời hiện "thi thoảng, đúng lúc", viết cho người
không biết GitHub là gì. Ba quyết định của chủ repo nằm ở đây:

- LẦN ĐẦU THẢ TIM cho một câu trả lời là lúc dễ xin sao nhất ("lần đầu thả tim ấy là lúc dễ add
  sao nhất"). Tim là lời "mình thích" rõ nhất, nên lý do `heart` không phải chờ đủ ngưỡng dùng.
- Các khoảnh khắc khác (việc nền vừa xong, lần mở đầu sau khi cập nhật) chỉ mời người ĐÃ DÙNG
  THẬT: cài từ 7 ngày, dùng ít nhất 3 ngày khác nhau, khoảng 20 lượt chat.
- Số sao KHÔNG viết cứng ("sau này nhiều sao rồi thì nó outdate"): đọc số thật từ GitHub mỗi
  ngày một lần, mốc kế tiếp tự tính theo bước tròn. Không đọc được thì không hiện số nào.

Trạng thái (đã tặng, để sau, đừng hỏi nữa) nằm trong settings.json của server chứ không trong
trình duyệt: người dùng Javis trên cả máy tính lẫn điện thoại không bị hỏi hai lần.

Module này không biết gì về FastAPI: mọi hàm nhận thời điểm `now` và dữ liệu đầu vào, để test
gọi thẳng. Route nằm ở routes/star_nudge.py.
"""
import json
import time
import urllib.request
from pathlib import Path

REPO = "blogminhquy/javis-os"
REPO_URL = "https://github.com/" + REPO
API_URL = "https://api.github.com/repos/" + REPO

NGAY = 86400
TUOI_TOI_THIEU = 7 * NGAY      # cài (lượt chat đầu tiên) từ 7 ngày trở lên
SO_NGAY_DUNG = 3               # dùng ít nhất 3 ngày khác nhau
SO_LUOT = 20                   # khoảng 20 lượt chat của người dùng
HOAN = 7 * NGAY                # "Để sau" = hỏi lại sau 7 ngày
HOAN_DONG = 3 * NGAY           # đóng bằng X (không chọn gì) = hỏi lại sau 3 ngày
TOI_DA_HOAN = 6                # hoãn (Để sau hoặc X) đủ 6 lần là thôi hẳn
CACH_LAN_HIEN = 20 * 3600      # hiện rồi thì không hiện lại trong ~1 ngày (trừ khi tự mở)

SAO_TTL_OK = NGAY              # số sao: đọc lại mỗi ngày
SAO_TTL_LOI = 3600             # GitHub lỗi: thử lại sau 1 giờ, không gọi mỗi lần mở thẻ

MOC_LUOT = (50, 100, 200, 500, 1000, 2000, 5000)       # tròn N lượt chat
MOC_NGAY = (30, 100, 365, 730, 1095)                  # tròn N ngày từ lượt chat đầu tiên

LY_DO = ("heart", "work", "load", "manual")
HANH_DONG = ("opened", "later", "dismiss", "never", "done")


def moc_tiep(n: int) -> int:
    """Mốc tròn kế tiếp, LỚN HƠN hẳn n. Bước to dần theo quy mô để mốc luôn trong tầm với:
    286 → 300, 1.240 → 1.500, 7.300 → 8.000, 23.000 → 25.000."""
    n = max(0, int(n))
    buoc = 100 if n < 1000 else 500 if n < 5000 else 1000 if n < 20000 else 5000
    return (n // buoc + 1) * buoc


def trang_thai(cfg_block) -> dict:
    """Khối `star_nudge` của settings, đủ trường, kiểu đúng. File sửa tay hay bản cũ thiếu
    trường thì đọc ra giá trị trung tính chứ không vỡ."""
    b = cfg_block if isinstance(cfg_block, dict) else {}

    def so(k):
        try:
            return float(b.get(k) or 0)
        except (TypeError, ValueError):
            return 0.0

    tt = b.get("state") if b.get("state") in ("done", "never") else ""
    return {"state": tt, "later_until": so("later_until"), "later_count": int(so("later_count")),
            "shown_at": so("shown_at"), "opened_at": so("opened_at"),
            "seen_version": str(b.get("seen_version") or ""),
            "turns_seen": int(so("turns_seen")), "days_seen": int(so("days_seen"))}


def du_lau(dung: dict, now: float) -> bool:
    """Đã dùng thật chưa. `dung` = {"turns", "first_ts", "days"} đếm từ kho hội thoại."""
    try:
        t0 = float(dung.get("first_ts") or 0)
        return (t0 > 0 and now - t0 >= TUOI_TOI_THIEU
                and int(dung.get("days") or 0) >= SO_NGAY_DUNG
                and int(dung.get("turns") or 0) >= SO_LUOT)
    except (TypeError, ValueError):
        return False


def _moc_dat(gia_tri, cac_moc) -> int:
    """Mốc lớn nhất đã chạm, 0 nếu chưa chạm mốc nào."""
    dat = [m for m in cac_moc if gia_tri >= m]
    return dat[-1] if dat else 0


def _con_cho(st: dict, now: float) -> bool:
    """Đang trong thời gian không được làm phiền."""
    return (st["state"] in ("done", "never") or st["later_until"] > now
            or now - st["shown_at"] < CACH_LAN_HIEN)


def chon_khoanh_khac(st: dict, ly_do: str, dung: dict, phien_ban: str, now: float):
    """Mời lúc này không, và mời bằng lời chào nào. Trả (kind, n) hoặc None.

    kind: heart | work | milestone (n = số lượt) | anniversary (n = số ngày) | update | manual.
    `manual` (người dùng tự mở từ trang Cập nhật hay nút sao ở góc) luôn có."""
    if ly_do == "manual":
        return ("manual", 0)
    if _con_cho(st, now):
        return None
    if ly_do == "heart":
        return ("heart", 0)
    if ly_do == "work":
        return ("work", 0) if du_lau(dung, now) else None
    if ly_do != "load":
        return None
    # Mở app: ăn mừng một cột mốc mới, hoặc bản vừa cập nhật. Cột mốc tự nó đã là bằng chứng
    # dùng thật (50 lượt chat, 30 ngày), nên không cần đủ ngưỡng như hai lý do kia.
    m = _moc_dat(int(dung.get("turns") or 0), MOC_LUOT)
    if m > st["turns_seen"]:
        return ("milestone", m)
    t0 = float(dung.get("first_ts") or 0)
    d = _moc_dat(int((now - t0) // NGAY), MOC_NGAY) if t0 > 0 else 0
    if d > st["days_seen"] and int(dung.get("turns") or 0) >= SO_LUOT:
        return ("anniversary", d)
    if st["seen_version"] and st["seen_version"] != phien_ban and du_lau(dung, now):
        return ("update", 0)
    return None


def danh_dau_da_hien(st: dict, kind: str, n: int, phien_ban: str, now: float) -> dict:
    """Ghi lại lần mời vừa trao cho dashboard: giờ hiện, cột mốc đã ăn mừng (không ăn mừng lại)."""
    m = dict(st)
    if kind != "manual":
        m["shown_at"] = now
    if kind == "milestone":
        m["turns_seen"] = max(st["turns_seen"], n)
    if kind == "anniversary":
        m["days_seen"] = max(st["days_seen"], n)
    m["seen_version"] = phien_ban
    return m


def ap_hanh_dong(st: dict, hanh_dong: str, now: float) -> dict:
    """Trạng thái mới sau một cú bấm. Trả bản sao, không sửa `st`."""
    m = dict(st)
    if hanh_dong == "opened":
        m["opened_at"] = now
    elif hanh_dong in ("later", "dismiss"):
        m["later_count"] = st["later_count"] + 1
        m["later_until"] = now + (HOAN if hanh_dong == "later" else HOAN_DONG)
        if m["later_count"] >= TOI_DA_HOAN:
            m["state"] = "never"
    elif hanh_dong == "never":
        m["state"] = "never"
    elif hanh_dong == "done":
        m["state"] = "done"
    return m


# ── Số sao trên GitHub ───────────────────────────────────────────────────────────────────────


def _hoi_github(timeout: float = 5.0) -> int:
    """Gọi API công khai của GitHub (không cần đăng nhập, 60 lượt/giờ mỗi IP - dư cho một lần
    mỗi ngày). urllib tự đi qua HTTPS_PROXY của máy nếu có."""
    req = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "javis-os"})
    with urllib.request.urlopen(req, timeout=timeout) as r:      # noqa: S310 - URL cố định https
        n = json.loads(r.read().decode("utf-8")).get("stargazers_count")
    if not isinstance(n, int) or n < 0:
        raise ValueError("stargazers_count không hợp lệ")
    return n


def so_sao(cache_path: Path, now: float, hoi=_hoi_github):
    """Số sao hiện tại hoặc None. Nhớ vào file để khởi động lại không gọi GitHub lần nữa; lỗi
    cũng được nhớ (1 giờ) để mất mạng không làm mỗi lần mở thẻ treo 5 giây."""
    try:
        c = json.loads(Path(cache_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        c = {}
    at = c.get("at") if isinstance(c.get("at"), (int, float)) else 0
    n = c.get("n") if isinstance(c.get("n"), int) else None
    ttl = SAO_TTL_OK if n is not None else SAO_TTL_LOI
    if at and 0 <= now - at < ttl:
        return n
    try:
        n = hoi()
    except Exception:            # noqa: BLE001 - mất mạng, GitHub chặn, JSON lạ: đều là "không có số"
        n = None
    try:
        Path(cache_path).write_text(json.dumps({"n": n, "at": now}), encoding="utf-8")
    except OSError:
        pass
    return n


def goi_sao(n):
    """Phần số của thẻ: {stars, milestone, remaining} hoặc None khi không có số."""
    if not isinstance(n, int):
        return None
    moc = moc_tiep(n)
    return {"stars": n, "milestone": moc, "remaining": moc - n}


_DUNG_CACHE = {"at": 0.0, "v": None}


def dem_dung(read, now: float = None) -> dict:
    """Đếm mức dùng từ kho hội thoại: lượt người dùng gõ ở dashboard, lượt đầu tiên, số ngày
    khác nhau có dùng. Chỉ kênh dashboard: thẻ mời hiện ở đó, và tin tự động của việc nền
    không phải là "người dùng đã dùng". Nhớ 10 phút vì bảng messages có thể lớn."""
    now = time.time() if now is None else now
    if _DUNG_CACHE["v"] is not None and now - _DUNG_CACHE["at"] < 600:
        return _DUNG_CACHE["v"]
    v = {"turns": 0, "first_ts": 0.0, "days": 0}
    try:
        rows = read(
            "SELECT COUNT(*) AS n, MIN(m.ts) AS t0, COUNT(DISTINCT CAST(m.ts / 86400 AS INTEGER)) AS d "
            "FROM messages m JOIN sessions s ON s.id = m.session_id "
            "WHERE m.role = 'user' AND s.channel IN ('web', 'dashboard')")
        if rows:
            r = rows[0]
            v = {"turns": int(r["n"] or 0), "first_ts": float(r["t0"] or 0), "days": int(r["d"] or 0)}
    except Exception:            # noqa: BLE001 - kho lỗi thì coi như chưa đủ lâu, không mời
        pass
    _DUNG_CACHE.update(at=now, v=v)
    return v
