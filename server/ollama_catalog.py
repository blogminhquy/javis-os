"""Danh mục model Ollama - để gợi ý và để tìm kiếm.

VÌ SAO CÓ MỘT DANH MỤC NỀN ĐI KÈM APP
--------------------------------------
Ollama KHÔNG công bố API JSON cho kho model công khai. `/api/tags` là API của MỘT server
Ollama đang chạy (model đã cài trên máy đó), hoàn toàn khác. Muốn có danh sách "toàn bộ thư
viện" thì chỉ còn đường cào HTML trang ollama.com/search - một trang không có hợp đồng, đổi
lúc nào cũng được.

Nên module này tách làm hai lớp:

  NGUỒN NỀN (`_NEN`, ngay trong file này) - đi kèm app, luôn có, không cần mạng. Javis tự cập
  nhật theo từng bản phát hành nên nó không đứng yên mãi.

  NGUỒN SỐNG (`dat_nguon_song`) - một hàm cắm thêm, trả về danh sách như `_NEN`. Chưa có bản
  cào nào cắm vào; khi nào viết được và THỬ ĐƯỢC với trang thật thì đăng ký vào đây, cache và
  phần còn lại của module không phải sửa gì.

Vì sao chưa cào ngay: viết code parse một trang chưa từng chạy thử được lần nào là đẩy rủi ro
cho người dùng chứ không phải giao tính năng. Có nguồn nền thì tab không bao giờ trắng - kể cả
lần chạy đầu tiên khi chưa có cache, đúng cái lỗ mà "giữ cache cũ" không bịt được.

Số liệu dung lượng dưới đây là bản quantize mặc định (thường q4) tại thời điểm phát hành, tính
theo GB. Dùng để lọc "có vừa máy không", nên xê xích vài trăm MB không đổi kết luận.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

# name, size_gb, ho (họ model), mô tả ngắn, các nhãn năng lực
_NEN = [
    ("qwen3:4b", 2.6, "qwen", "Nhỏ mà chắc tay, chạy được cả trên máy không có GPU rời.", ["tools"]),
    ("qwen3:8b", 5.2, "qwen", "Cân bằng giữa chất lượng và tốc độ, hợp máy 16GB RAM.", ["tools"]),
    ("qwen3:14b", 9.3, "qwen", "Khá hơn hẳn bản 8b khi viết dài và suy luận nhiều bước.", ["tools"]),
    ("qwen3:32b", 20.0, "qwen", "Mạnh, cần GPU khá hoặc nhiều RAM.", ["tools"]),
    ("qwen3-coder:30b", 19.0, "qwen", "Chuyên viết và đọc code.", ["tools"]),
    ("llama3.1:8b", 4.9, "llama", "Bản phổ thông của Meta, tài liệu và ví dụ nhiều nhất.", ["tools"]),
    ("llama3.2:3b", 2.0, "llama", "Rất nhẹ, hợp máy yếu hoặc chạy nền.", ["tools"]),
    ("llama3.3:70b", 43.0, "llama", "Chất lượng cao nhất dòng Llama, đòi máy rất mạnh.", ["tools"]),
    ("gemma3:4b", 3.3, "gemma", "Nhẹ, của Google, đọc được cả ảnh.", ["vision"]),
    ("gemma3:12b", 8.1, "gemma", "Bản vừa tầm của Gemma 3, có thị giác.", ["vision"]),
    ("gemma3:27b", 17.0, "gemma", "Bản lớn của Gemma 3.", ["vision"]),
    ("deepseek-r1:8b", 5.2, "deepseek", "Suy luận từng bước, hợp phân tích và giải toán.", ["thinking"]),
    ("deepseek-r1:14b", 9.0, "deepseek", "Bản suy luận vừa tầm, cần khoảng 16GB RAM.", ["thinking"]),
    ("deepseek-r1:32b", 20.0, "deepseek", "Suy luận mạnh, đòi máy khá.", ["thinking"]),
    ("phi4:14b", 9.1, "phi", "Nhỏ gọn nhưng mạnh về logic và toán.", ["tools"]),
    ("mistral:7b", 4.1, "mistral", "Nhanh, nhẹ, đa năng.", ["tools"]),
    ("mistral-small:24b", 14.0, "mistral", "Đa năng, phản hồi nhanh, hợp làm trợ lý thường ngày.", ["tools"]),
    ("nomic-embed-text", 0.3, "nomic", "Sinh vector cho tìm kiếm ngữ nghĩa, không dùng để chat.", ["embedding"]),
    ("mxbai-embed-large", 0.7, "mxbai", "Vector chất lượng cao cho tìm kiếm.", ["embedding"]),
    ("llava:7b", 4.7, "llava", "Đọc và mô tả ảnh.", ["vision"]),
]

_TTL = 6 * 3600          # 6 tiếng: danh mục model không đổi theo giờ
_nguon_song = None       # hàm () -> list, do nơi khác đăng ký (xem dat_nguon_song)


def dat_nguon_song(fn):
    """Đăng ký một nguồn danh mục SỐNG. `fn()` trả list cùng khuôn `muc()`.

    Chưa có ai gọi. Chỗ này tồn tại để bản cào (khi viết và thử được) cắm vào mà không phải
    sửa cache, sửa gợi ý hay sửa endpoint.
    """
    global _nguon_song
    _nguon_song = fn


def muc(name, size_gb, ho, mo_ta, nhan):
    return {"name": name, "size_gb": size_gb, "family": ho, "description": mo_ta,
            "tags": list(nhan)}


def _duong_cache() -> Path:
    import config as cfgmod
    d = Path(cfgmod.STATE_DIR) / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d / "ollama_library.json"


def _doc_cache():
    try:
        d = json.loads(_duong_cache().read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("items"), list):
            return d
    except (OSError, ValueError):
        pass
    return None


def thu_vien(force: bool = False) -> dict:
    """Danh mục hiện dùng: {items, source, fetched_at}.

    Thứ tự ưu tiên: cache còn hạn -> nguồn sống (nếu có ai đăng ký) -> cache quá hạn ->
    nguồn nền. Cache quá hạn đứng TRƯỚC nguồn nền vì dữ liệu cũ vẫn sát thực tế hơn danh sách
    đóng gói từ lúc phát hành.
    """
    cu = _doc_cache()
    if cu and not force and (time.time() - float(cu.get("fetched_at") or 0)) < _TTL:
        return cu
    if _nguon_song is not None:
        try:
            items = _nguon_song()
            if items:
                d = {"items": items, "source": "live", "fetched_at": time.time()}
                try:
                    _duong_cache().write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
                except OSError:
                    pass
                return d
        except Exception:
            pass        # nguồn sống gãy thì rơi xuống dưới, KHÔNG để tab trắng
    if cu:
        return cu
    return {"items": [muc(*x) for x in _NEN], "source": "builtin", "fetched_at": 0}


def tim(q: str = "", capability: str = "", sort: str = "pho-bien") -> list:
    """Lọc trong danh mục đang có. Không tự đi lấy dữ liệu - việc đó của thu_vien()."""
    ds = list(thu_vien().get("items") or [])
    q = (q or "").strip().lower()
    if q:
        ds = [m for m in ds
              if q in (m.get("name") or "").lower() or q in (m.get("description") or "").lower()]
    if capability:
        ds = [m for m in ds if capability in (m.get("tags") or [])]
    if sort == "ten":
        ds.sort(key=lambda m: (m.get("name") or "").lower())
    elif sort == "nho-nhat":
        ds.sort(key=lambda m: m.get("size_gb") or 0)
    return ds


# ── Gợi ý theo cấu hình máy ─────────────────────────────────────────────────────

MAX_GOI_Y = 6
# Chừa chỗ cho hệ điều hành và chính Javis: nạp một model bằng đúng RAM máy là máy đứng hình,
# không phải "chạy chậm".
CHUA_LAI = 0.8
# Chưa biết máy gì thì coi như 8GB RAM. Đây là mức VPS phổ thông và cũng là ngưỡng Ollama tự
# khuyến nghị cho model 7-8B, nên đoán trượt cũng chỉ trượt về phía an toàn.
RAM_KHI_CHUA_BIET = 8.0


def goi_y(specs: dict) -> list:
    """Tối đa 6 model vừa sức máy, CÓ TRẢI RỘNG chứ không dồn hết vào một hạng.

    Luật xếp hạng ngây thơ ("model lọt VRAM lên đầu") cho ra kết quả sai về chất: máy 32GB RAM
    kèm GPU 8GB nhận đúng cùng sáu model như máy 8GB không GPU, vì tám model dưới 8GB đã chiếm
    sạch chỗ. Người có máy mạnh mở tab ra và không thấy một model lớn nào - đúng thứ họ mua máy
    để chạy.

    Nên chia đôi số chỗ:
      - nửa đầu: model chui TRỌN vào VRAM (nhanh nhất), lớn nhất trước;
      - nửa sau: model lớn nhất mà RAM còn gánh nổi (chất lượng cao hơn, đổi lại chậm).
    Máy không có GPU thì nửa đầu rỗng và nửa sau lấy hết - vẫn ra danh sách đầy.

    Thêm một luật CHỐNG TRÙNG HỌ: mỗi họ (qwen, llama, gemma...) chỉ được một suất ở lượt đầu.
    Không có nó thì danh sách thành bốn biến thể qwen3, trông như nhiều lựa chọn mà thật ra
    chỉ có một.
    """
    specs = specs or {}
    biet = (specs.get("source") or "unknown") != "unknown"
    ram = float(specs.get("ram_gb") or 0) or RAM_KHI_CHUA_BIET
    vram = float(specs.get("vram_gb") or 0)
    co_gpu = bool(specs.get("has_gpu"))
    tran = ram * CHUA_LAI

    nhanh, lon = [], []
    for m in thu_vien().get("items") or []:
        if "embedding" in (m.get("tags") or []):
            continue                       # không dùng để chat, đừng chen vào gợi ý chính
        cd = float(m.get("size_gb") or 0)
        if cd <= 0 or cd > tran:
            continue
        d = dict(m)
        if co_gpu and vram > 0 and cd <= vram:
            d["note"] = "Chạy trọn trong GPU, nhanh nhất"
            nhanh.append(d)
        else:
            d["note"] = ("Vượt VRAM, phải bù bằng RAM nên chậm hơn" if (co_gpu and vram > 0)
                         else "Chưa đọc được cấu hình máy - đây là mức an toàn" if not biet
                         else "Chạy bằng CPU và RAM")
            lon.append(d)

    # Lớn trước trong cả hai rổ: cùng một hạng thì model to hơn gần như luôn trả lời khá hơn.
    nhanh.sort(key=lambda m: -float(m.get("size_gb") or 0))
    lon.sort(key=lambda m: -float(m.get("size_gb") or 0))

    ra, da_ho = [], set()

    def nhat(ds, tran_suat):
        """Lấy tối đa `tran_suat` mục, mỗi họ một suất."""
        lay = 0
        for m in ds:
            if lay >= tran_suat or len(ra) >= MAX_GOI_Y:
                break
            ho = m.get("family") or m.get("name")
            if ho in da_ho:
                continue
            da_ho.add(ho)
            ra.append(m)
            lay += 1

    nua = MAX_GOI_Y // 2
    nhat(nhanh, nua)
    nhat(lon, MAX_GOI_Y - len(ra))
    # Còn chỗ trống (ít họ quá, hoặc một rổ rỗng) thì nới luật chống trùng họ ra mà lấp nốt:
    # thà hai bản cùng họ còn hơn để trống một ô.
    if len(ra) < MAX_GOI_Y:
        da_co = {m["name"] for m in ra}
        for m in nhanh + lon:
            if len(ra) >= MAX_GOI_Y:
                break
            if m["name"] not in da_co:
                ra.append(m)
                da_co.add(m["name"])
    # Chọn xong mới sắp để HIỆN: nhóm chạy trong GPU lên trước, trong mỗi nhóm lớn trước. Việc
    # trải rộng đã xong ở trên nên sắp lại không làm mất model lớn nào, chỉ để mắt đọc xuôi -
    # không còn cảnh một model 70B nằm chen giữa mấy model chạy GPU.
    ra.sort(key=lambda m: (0 if m.get("note", "").startswith("Chạy trọn") else 1,
                           -float(m.get("size_gb") or 0)))
    return ra[:MAX_GOI_Y]
