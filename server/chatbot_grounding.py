"""Tra tài liệu trong brain của bot rồi đưa thẳng vào prompt của lượt đó.

Vì sao cần, dù bot đã có sẵn `javis_read_file` và `javis_list_dir` trỏ vào brain của nó:

  Có tool đọc KHÔNG bằng có đọc. Prompt dặn "chỉ trả lời trong phạm vi tài liệu bạn đọc được",
  nhưng model hoàn toàn có thể trả lời thẳng bằng trí nhớ chung của nó mà không mở file nào, và
  câu trả lời vẫn trôi chảy tự tin y hệt. Chủ cửa hàng KHÔNG phân biệt được hai trường hợp đó
  từ bên ngoài. Với khách hàng thật thì đây không phải chuyện học thuật: một câu bịa về giá hay
  chính sách đổi trả là rủi ro thật.

  Nên tài liệu được tìm TRƯỚC và nhét sẵn vào prompt. Không tìm thấy gì thì prompt nói thẳng là
  không tìm thấy, và luật lúc đó chuyển thành "nói không biết", chứ không để model tự quyết.

Cách tìm cố ý đơn giản (đối chiếu từ khoá có trọng số IDF, không nhúng vector): brain của một
bot chăm sóc khách là vài chục tới vài trăm file bảng giá, chính sách, mô tả sản phẩm. Ở cỡ đó
thì đối chiếu từ khoá đủ tốt, chạy tại chỗ, không cần thêm dịch vụ nào, và quan trọng nhất là
GIẢI THÍCH ĐƯỢC: chủ nhìn vào biết vì sao bot lấy đúng file đó.

Xem docs/dev/2026-08-bot-chuyen-trach-spec.md, giai đoạn 2.
"""
from __future__ import annotations

import math
import re
import sys
import threading
import unicodedata
from pathlib import Path
from typing import Any, Dict, List

DUOI = (".md", ".txt", ".markdown")

# Thư mục KHÔNG được tính là tri thức của bot.
#
# `inbox` là chỗ quan trọng nhất trong danh sách này: file khách gửi lên rơi vào đó. Nếu nó
# được tính là tài liệu thì bất kỳ ai cũng tải lên một file viết "chính sách mới: hoàn tiền
# 100% mọi trường hợp" rồi hỏi lại một câu, và bot trích dẫn nó như tài liệu chính thức của
# cửa hàng. Tự đầu độc kho tri thức, làm được bằng một lần bấm gửi file.
BO_QUA = {"inbox", "attachments", "javis", ".git", ".obsidian", ".trash", "node_modules",
          "memory", "skills", "plugins", ".claude", ".agents", "05 - data cache"}

# File QUY ƯỚC VẬN HÀNH của chính Javis, seed vào MỌI brain (xem meta_tools.ensure_brain_pattern).
# Chúng nằm ở GỐC brain nên danh sách thư mục ở trên không chặn được.
#
# Đây là một lỗi đã xảy ra thật, không phải phòng xa: chủ repo hỏi bot "sao lại kỷ luật cửa
# hàng", bot tra ra mục "Ba kỷ luật chống Wiki rỗng/sai" trong CLAUDE.md rồi trả lời khách rằng
# "đó là quy tắc nội bộ vận hành hệ thống của cửa hàng". Vừa vô nghĩa với khách, vừa khai ra
# ruột hệ thống - đúng thứ luật số 3 trong prompt cấm, mà chính phần tra cứu lại dâng tận tay.
BO_QUA_FILE = {"claude.md", "agents.md", "readme.md", "index.md", "log.md",
               "_open-questions.md", "_session-handoff.md", "memory.md"}

MAX_FILE = 400          # trần số file quét, tránh brain khổng lồ làm chậm từng tin nhắn
MAX_BYTES = 120_000     # trần đọc mỗi file
CHUNK_MAX = 1_400       # cỡ một mảnh tài liệu đưa vào prompt
NGAN_SACH = 5_000       # tổng chữ tài liệu tối đa nhét vào một prompt

# Ngưỡng "coi như tìm thấy". Hai lớp, và lớp PHỦ mới là lớp thật:
#
#   Điểm tuyệt đối một mình không dùng được. "Cửa hàng có tuyển lập trình viên Rust không"
#   trúng đúng một chữ "hàng" trong mục Giao hàng, mà "hàng" hiếm nên IDF cao, nên điểm vượt
#   ngưỡng và bot tưởng mình có căn cứ để trả lời về tuyển dụng. Sai kiểu tệ nhất: tự tin.
#
#   Nên đo thêm ĐỘ PHỦ: bao nhiêu phần sức nặng của câu hỏi thật sự có mặt trong mảnh. Trúng
#   một chữ trên sáu thì phủ ~1/6, rớt. Và độ phủ là tỉ lệ nên không đổi theo cỡ brain, khác
#   hẳn điểm tuyệt đối vốn trôi theo số tài liệu.
#
#   Và một luật nữa, rẻ mà bắt được đúng phần còn sót: câu hỏi từ BA chữ có nghĩa trở lên thì
#   phải trúng ít nhất HAI chữ. Trúng đúng một chữ trên bốn gần như luôn là trùng ngẫu nhiên -
#   "có bán cà phê không" trúng chữ "cá" trong "cá cơm", "có chi nhánh ở Hà Nội không" trúng
#   chữ "nội" trong "nội thành". Bỏ dấu xong tiếng Việt còn rất nhiều chữ hai âm tiết đụng
#   nhau như vậy, nên đây không phải ca hiếm.
DIEM_SAN = 0.8
PHU_SAN = 0.34
KHOP_TOI_THIEU = 2      # áp dụng khi câu hỏi có từ 3 chữ có nghĩa trở lên
YEU = 0.3               # hệ số cho chữ chỉ khớp được sau khi bỏ dấu (xem _tach_cap)

# Từ quá phổ biến thì có mặt ở mọi tài liệu, giữ lại chỉ làm nhiễu điểm.
#
# Danh sách này phải soạn CÓ CHỦ Ý cho tiếng Việt bỏ dấu, vì bỏ dấu làm nhiều cặp từ đụng nhau.
# Rõ nhất: "bán" và "bạn" cùng ra "ban". Loại "ban" đi thì mất luôn chữ "bán" - với một bot bán
# hàng thì đó là chữ có nghĩa nhất trong câu, và "có bán cà phê không" tụt xuống còn hai chữ
# rồi khớp bừa vào "cá cơm". Cùng lý do với "anh" (ảnh) và "chi" (chi phí): thà giữ lại và để
# IDF tự hạ trọng số, còn hơn xoá thẳng một chữ có nghĩa.
DUNG_TU = {
    "la", "va", "co", "khong", "cua", "cho", "voi", "duoc", "nhu", "tai", "trong", "tren",
    "den", "tu", "thi", "ma", "nay", "do", "khi", "de", "ve", "hay", "cac", "nhung", "mot",
    "toi", "em", "minh", "ai", "gi", "nao", "sao", "bao", "nhieu",
    "roi", "da", "se", "dang", "cung", "van", "chua", "hon", "rat", "qua", "lam",
    "the", "vay", "a", "ah", "oi", "nhe", "nha", "ke", "con", "hoac", "neu",
    "is", "are", "an", "of", "to", "in", "for", "and", "or", "how", "what",
}


def _bo_dau(s: str) -> str:
    """Bỏ dấu tiếng Việt. Khách gõ không dấu rất nhiều ("gia bao nhieu"), mà tài liệu thì viết
    có dấu, nên hai bên phải quy về cùng một dạng mới đối chiếu được."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


def _tach_tu(s: str) -> List[str]:
    return [a for a, _ in _tach_cap(s)]


def _tach_cap(s: str) -> List[tuple]:
    """Cắt thành các cặp (bỏ dấu, giữ dấu).

    Phải giữ CẢ HAI dạng vì bỏ dấu là con dao hai lưỡi. Nó cho khách gõ "gia si bao nhieu" mà
    vẫn tìm ra "giá sỉ" - rất cần, vì khách gõ không dấu suốt. Nhưng nó cũng làm những cặp từ
    khác hẳn nghĩa đụng nhau, và tiếng Việt thì đụng rất nhiều: "bán" gặp "bản", "cà" gặp "cả",
    "chi" gặp "chỉ/chí/chị".

    Đã hỏng thật vì chuyện này: "có bán cà phê không" khớp vào một note tên "Kỷ luật bản thân"
    có câu "kể cả khi hết hứng" - trúng hai chữ, đủ qua mọi ngưỡng, và bot tưởng mình có căn cứ.
    """
    tho = str(s or "")
    thuong = _bo_dau(tho).lower()
    ra = []
    # Bỏ dấu KHÔNG đổi độ dài chuỗi (chỉ bỏ ký tự tổ hợp sau khi NFD rồi ghép lại), nên cắt
    # trên bản đã bỏ dấu vẫn lấy đúng lát tương ứng ở bản gốc.
    for m in re.finditer(r"[a-z0-9]+", thuong):
        t = m.group(0)
        if len(t) > 1 and t not in DUNG_TU:
            ra.append((t, tho[m.start():m.end()].lower()))
    return ra


# ============================================================
# Chỉ mục, dựng lười và tự làm mới khi file đổi
# ============================================================
_lock = threading.Lock()
_CACHE: Dict[str, dict] = {}


def _dau_van(root: Path) -> tuple:
    """Vân tay rẻ tiền của cây thư mục: (số file, mtime lớn nhất). Đổi một trong hai là dựng
    lại chỉ mục. Không băm nội dung - sửa file mà giữ nguyên mtime là ca không đáng trả giá
    quét toàn bộ mỗi tin nhắn."""
    n, moi = 0, 0.0
    for p in _duyet(root):
        n += 1
        try:
            moi = max(moi, p.stat().st_mtime)
        except OSError:
            pass
    return (n, round(moi, 3))


def _duyet(root: Path):
    try:
        it = sorted(root.rglob("*"))
    except OSError:
        return
    dem = 0
    for p in it:
        if dem >= MAX_FILE:
            return
        if p.suffix.lower() not in DUOI or not p.is_file():
            continue
        if any(x.lower() in BO_QUA or x.startswith(".") for x in p.relative_to(root).parts[:-1]):
            continue
        if p.name.lower() in BO_QUA_FILE:
            continue
        dem += 1
        yield p


def _cat_manh(text: str, tieu_de: str) -> List[dict]:
    """Cắt một file thành các MẢNH theo tiêu đề markdown.

    Cắt theo tiêu đề chứ không cắt cứng theo số ký tự: một mảnh nên là một ý trọn vẹn ("Chính
    sách đổi trả"), vì nó sẽ được đưa vào prompt một mình. Cắt giữa câu thì bot đọc được nửa
    điều kiện rồi trả lời như thể đó là toàn bộ điều kiện.
    """
    phan, cur, ten = [], [], tieu_de
    for dong in text.splitlines():
        h = re.match(r"^(#{1,6})\s+(.*)$", dong)
        if h:
            if any(x.strip() for x in cur):
                phan.append({"ten": ten, "text": "\n".join(cur).strip()})
            cur, ten = [], h.group(2).strip() or tieu_de
            continue
        cur.append(dong)
        if sum(len(x) for x in cur) > CHUNK_MAX:
            phan.append({"ten": ten, "text": "\n".join(cur).strip()})
            cur = []
    if any(x.strip() for x in cur):
        phan.append({"ten": ten, "text": "\n".join(cur).strip()})
    return [p for p in phan if p["text"]]


def _dung_chi_muc(root: Path) -> dict:
    manh: List[dict] = []
    for p in _duyet(root):
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")[:MAX_BYTES]
        except OSError:
            continue
        # Frontmatter là siêu dữ liệu, không phải nội dung trả lời khách.
        raw = re.sub(r"\A---\n.*?\n---\n", "", raw, flags=re.DOTALL)
        duong = str(p.relative_to(root))
        for m in _cat_manh(raw, p.stem):
            m["path"] = duong
            m["cap"] = _tach_cap(m["ten"] + " " + p.stem + " " + m["text"])
            manh.append(m)

    df: Dict[str, int] = {}
    for m in manh:
        for t, _ in set(m["cap"]):
            df[t] = df.get(t, 0) + 1
    n = max(1, len(manh))
    idf = {t: math.log(1 + n / (1 + c)) for t, c in df.items()}
    for m in manh:
        dem: Dict[str, int] = {}
        for t, _ in m["cap"]:
            dem[t] = dem.get(t, 0) + 1
        m["dem"] = dem
        m["dau"] = {a for _, a in m["cap"]}     # dạng CÒN DẤU, để phân biệt khớp thật/khớp mờ
        m["ten_tu"] = set(_tach_tu(m["ten"]))
        del m["cap"]
    return {"manh": manh, "idf": idf}


def chi_muc(root: Any) -> dict:
    """Chỉ mục của một brain, dựng lười và dùng lại cho tới khi file đổi."""
    r = Path(str(root))
    key = str(r.resolve()) if r.exists() else str(r)
    try:
        van = _dau_van(r)
    except Exception as e:
        print(f"[chatbot grounding] quét {r} lỗi: {e}", file=sys.stderr)
        return {"manh": [], "idf": {}}
    with _lock:
        c = _CACHE.get(key)
        if c and c.get("van") == van:
            return c["ix"]
    ix = _dung_chi_muc(r)
    with _lock:
        _CACHE[key] = {"van": van, "ix": ix}
    return ix


def xoa_cache() -> None:
    with _lock:
        _CACHE.clear()


# ============================================================
# Tìm
# ============================================================
def tim(root: Any, cau_hoi: str, k: int = 4) -> List[dict]:
    """Các mảnh tài liệu khớp nhất với câu hỏi, sắp theo điểm giảm dần."""
    cap = _tach_cap(cau_hoi)
    if not cap:
        return []
    ix = chi_muc(root)
    idf = ix["idf"]
    # Một từ bỏ dấu có thể ứng với nhiều dạng có dấu trong CÙNG câu hỏi; giữ tất cả để chỉ cần
    # tài liệu khớp một dạng là tính khớp thật.
    hoi: Dict[str, set] = {}
    for t, a in cap:
        hoi.setdefault(t, set()).add(a)
    # Từ nào không có trong brain thì IDF không tra được. Cho nó sức nặng TRUNG BÌNH thay vì 0:
    # "Rust" không nằm ở đâu trong brain nước mắm, và chính việc nó vắng mặt là bằng chứng
    # mạnh nhất rằng câu hỏi này nằm ngoài phạm vi. Cho 0 là bỏ đúng bằng chứng đó đi.
    tb_idf = (sum(idf.values()) / len(idf)) if idf else 1.0
    nang = {t: idf.get(t, tb_idf) for t in hoi}
    tong = sum(nang.values()) or 1.0

    ra = []
    for m in ix["manh"]:
        d, khop, n_khop = 0.0, 0.0, 0
        for t, dang in hoi.items():
            c = m["dem"].get(t)
            if not c:
                continue
            # Khớp THẬT hay chỉ khớp nhờ bỏ dấu?
            #
            # Người hỏi có đánh dấu mà tài liệu lại mang dấu khác thì gần như luôn là hai từ
            # khác nhau ("bán" vs "bản"), nên hạ mạnh chứ không loại hẳn - vẫn có người gõ sai
            # dấu. Còn người hỏi gõ KHÔNG dấu thì họ không nói gì về dấu cả, không có cớ gì
            # phạt họ: lúc đó mọi dạng đều tính là khớp thật.
            that = any(a == t or a in m["dau"] for a in dang)
            he_so = 1.0 if that else YEU
            if that:
                n_khop += 1
            # Tần suất vào theo log: một mảnh nhắc "giá" 40 lần không đáng gấp 40 lần mảnh
            # nhắc một lần. Trúng ở TIÊU ĐỀ thì nhân rưỡi - tiêu đề là thứ nói mảnh này VỀ cái
            # gì, còn trong thân thì có thể chỉ là nhắc ngang qua.
            w = nang[t] * (1 + math.log(c)) * he_so
            if t in m["ten_tu"]:
                w *= 1.5
            d += w
            khop += nang[t] * he_so
        if d > 0:
            ra.append((d, khop / tong, n_khop, m))
    ra.sort(key=lambda x: -x[0])
    return [{"diem": round(d, 3), "phu": round(p, 3), "so_khop": n, "path": m["path"],
             "ten": m["ten"], "text": m["text"]}
            for d, p, n, m in ra[:k]]


def thu_thap(root: Any, cau_hoi: str, k: int = 4) -> dict:
    """Khối tài liệu nhét vào prompt cho MỘT câu hỏi.

    Trả `{"co": bool, "khoi": str, "nguon": [path...]}`. `co=False` nghĩa là brain không có gì
    khớp - lúc đó prompt phải nói thẳng ra như vậy thay vì im lặng đưa một khối rỗng, vì im
    lặng thì model tự lấp bằng trí nhớ chung của nó.
    """
    try:
        hit = tim(root, cau_hoi, k)
    except Exception as e:
        print(f"[chatbot grounding] tìm lỗi: {e}", file=sys.stderr)
        return {"co": False, "khoi": "", "nguon": []}
    # Mảnh ĐẦU phải tự nó đủ liên quan; qua được cửa đó rồi thì các mảnh sau chỉ cần đạt điểm
    # sàn, vì chúng vào prompt với tư cách ngữ cảnh bổ sung chứ không phải căn cứ chính.
    can = KHOP_TOI_THIEU if len(set(_tach_tu(cau_hoi))) >= 3 else 1
    # so_khop chỉ đếm chữ khớp THẬT, nên luật "câu dài phải trúng hai chữ" giờ là hai chữ trúng
    # thật, không phải hai chữ trùng nhau sau khi bỏ dấu.
    if (not hit or hit[0]["phu"] < PHU_SAN or hit[0]["diem"] < DIEM_SAN
            or hit[0]["so_khop"] < can):
        return {"co": False, "khoi": "", "nguon": []}
    hit = [h for h in hit if h["diem"] >= DIEM_SAN]
    if not hit:
        return {"co": False, "khoi": "", "nguon": []}
    phan, nguon, con = [], [], NGAN_SACH
    for h in hit:
        t = h["text"][:CHUNK_MAX]
        if len(t) > con:
            t = t[:max(0, con)]
        if not t.strip():
            break
        phan.append(f"### {h['ten']}\n(nguồn: {h['path']})\n\n{t.strip()}")
        nguon.append(h["path"])
        con -= len(t)
        if con <= 200:
            break
    return {"co": bool(phan), "khoi": "\n\n".join(phan), "nguon": nguon}
