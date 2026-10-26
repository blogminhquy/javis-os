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

import hashlib
import math
import re
import sys
import threading
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

DUOI = (".md", ".txt", ".markdown")

# Thư mục KHÔNG được tính là tri thức của bot.
#
# `inbox` là chỗ quan trọng nhất trong danh sách này: file khách gửi lên rơi vào đó. Nếu nó
# được tính là tài liệu thì bất kỳ ai cũng tải lên một file viết "chính sách mới: hoàn tiền
# 100% mọi trường hợp" rồi hỏi lại một câu, và bot trích dẫn nó như tài liệu chính thức của
# cửa hàng. Tự đầu độc kho tri thức, làm được bằng một lần bấm gửi file.
BO_QUA = {"inbox", "attachments", "javis", ".git", ".obsidian", ".trash", "node_modules",
          "memory", "skills", "plugins", ".claude", ".agents", "05 - data cache",
          # Old copies (0.172.0): a backup of a price list or of an agent is out of date by definition, and quoting it
          # to a customer as the shop's document is wrong twice. Dot folders were already skipped (see `_duyet`);
          # `.backup` is listed so that rule cannot drop it unnoticed.
          ".backup", "backup", "backups",
          # Chat-scoped documents (0.338.0) live in `rieng-theo-nhom/` at the brain root and reach a turn only through
          # `scoped_docs`. Listed here so the general scan never reads them, and so a folder of that name anywhere
          # else is hidden from everyone instead of shared with everyone.
          "rieng-theo-nhom"}

# Javis's own operating folders AT THE BRAIN ROOT (0.172.0): `agents/` holds the bot's own role file and its
# colleagues', `workflows/` the step chains. Searched as documents, the bot quoted its internal rules (and a
# colleague's) to customers as "our documents", the same leak as CLAUDE.md below. Root only: a user folder
# such as "products/agents" is still the user's.
BO_QUA_GOC = {"agents", "workflows"}

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
_CACHE_MAX = 64     # one slot per brain, plus one per chat with scoped documents (0.338.0); oldest dropped first


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


def _ung_vien(root: Path):
    """Every file that may be a document of the bot, as (path, scope). `scope` is None for a document every chat
    may see, else the tuple of chat ids that may see it (empty: nobody). See `file_scope` and `SCOPED_DIR`."""
    try:
        it = sorted(root.rglob("*"))
    except OSError:
        return
    for p in it:
        if p.suffix.lower() not in DUOI or not p.is_file():
            continue
        thu_muc = p.relative_to(root).parts[:-1]
        if thu_muc and thu_muc[0].lower() == SCOPED_DIR:
            if any(x.startswith(".") for x in thu_muc):
                continue
            scope = file_scope(p)
            if scope is None:
                # No `chat_scope` line: the first folder under `rieng-theo-nhom/` names the chat. A file lying
                # directly in `rieng-theo-nhom/` names none, so nobody sees it (fail closed).
                scope = (thu_muc[1],) if len(thu_muc) > 1 else ()
            yield p, scope
            continue
        if any(x.lower() in BO_QUA or x.startswith(".") for x in thu_muc):
            continue
        if thu_muc and thu_muc[0].lower() in BO_QUA_GOC:
            continue
        if p.name.lower() in BO_QUA_FILE:
            continue
        yield p, file_scope(p)


def _duyet(root: Path):
    """The documents every chat may see, capped at `MAX_FILE`. A file whose frontmatter carries `chat_scope` is
    never one of them, wherever it lies: the owner marked it private, so it must not leak through the general
    index just because it sits outside `rieng-theo-nhom/`."""
    dem = 0
    for p, scope in _ung_vien(root):
        if scope is not None:
            continue
        if dem >= MAX_FILE:
            return
        dem += 1
        yield p


# ============================================================
# Chat-scoped documents (0.338.0)
# ============================================================
# A shop with one bot answering many customer groups keeps one file per customer (contract, deposit, promises).
# The bot must read the WHOLE file of the customer in the chat it is answering, and never anything of another
# customer, not even a file name. Two ways to mark such a file, both read here and nowhere else:
#   - put it under `rieng-theo-nhom/<chat id>/` (the chat id is the Zalo threadId or Telegram chat id), or
#   - give it a frontmatter line `chat_scope: <chat id>` (or a list), anywhere in the brain.
# A frontmatter line wins over the folder name. The chat id of a turn comes from the server (`turn_context`, or
# the channel message for the pre-turn search), never from what the model or the customer types. A turn with no
# chat id (Try bot, the owner's chats) sees no scoped document at all.
SCOPED_DIR = "rieng-theo-nhom"
MAX_SCOPED_FILES = 5_000    # walk cap for scoped files; one per customer, so far more than general documents
_HEAD_BYTES = 4_096         # how much of a file is read to find its frontmatter
_SCOPE_CACHE: Dict[str, tuple] = {}     # path -> ((mtime_ns, size), scope)
_SCOPE_CACHE_MAX = 20_000


def _parse_scope(fm: str) -> Optional[tuple]:
    """The `chat_scope` value of one frontmatter block: None when the key is absent, else a tuple of ids. Parsed by
    hand rather than with YAML: a chat id is an opaque string, and YAML would turn `0123` or `-100123` into a number
    and lose the exact text."""
    lines = fm.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^chat_scope\s*:(.*)$", line)
        if not m:
            continue
        val = m.group(1).strip()
        if val.startswith("["):
            items = val.strip("[]").split(",")
        elif val:
            items = [val]
        else:
            items = []
            for nxt in lines[i + 1:]:
                b = re.match(r"^\s*-\s*(.*)$", nxt)
                if not b:
                    break
                items.append(b.group(1))
        out = []
        for it in items:
            v = re.sub(r"\s+#.*$", "", it).strip().strip("'\"").strip()
            if v and v not in out:
                out.append(v)
        return tuple(out)
    return None


def file_scope(p: Path) -> Optional[tuple]:
    """The chat ids a file's frontmatter `chat_scope` names, None when it has no such line. Cached on
    (mtime, size), so the per-message scan reads each file's head once until it changes. A file that cannot be
    read reads as "nobody" (an empty tuple), never as a document every chat may see."""
    try:
        st = p.stat()
    except OSError:
        return ()
    key, sig = str(p), (st.st_mtime_ns, st.st_size)
    with _lock:
        hit = _SCOPE_CACHE.get(key)
    if hit and hit[0] == sig:
        return hit[1]
    scope = None
    try:
        with open(p, "rb") as f:
            head = f.read(_HEAD_BYTES).decode("utf-8", "replace").replace("\r\n", "\n")
        m = re.match(r"\A\ufeff?---\n(.*?)\n---\s*(\n|\Z)", head, flags=re.DOTALL)
        if m:
            scope = _parse_scope(m.group(1))
        elif head.lstrip("\ufeff").startswith("---\n") and re.search(r"(?m)^chat_scope\s*:", head):
            scope = ()      # a frontmatter too long to read whole that still names a scope: nobody, not everyone
    except OSError:
        return ()
    with _lock:
        if len(_SCOPE_CACHE) >= _SCOPE_CACHE_MAX:
            _SCOPE_CACHE.clear()
        _SCOPE_CACHE[key] = (sig, scope)
    return scope


def _clean_chat_id(chat_id: Any) -> str:
    return str(chat_id or "").strip()


def scoped_paths(root: Any, chat_id: Any) -> List[str]:
    """Relative posix paths of the scoped documents of ONE chat. Empty without a chat id."""
    cid = _clean_chat_id(chat_id)
    if not cid:
        return []
    r = Path(str(root))
    out = []
    try:
        for n, (p, scope) in enumerate(_ung_vien(r)):
            if n >= MAX_FILE + MAX_SCOPED_FILES:
                break
            if scope and cid in scope:
                out.append(p.relative_to(r).as_posix())
    except Exception as e:
        print(f"[chatbot grounding] tài liệu riêng của {r} lỗi: {e}", file=sys.stderr)
        return []
    return out


def has_scoped_docs(root: Any) -> bool:
    """True when some chat has at least one scoped document, so a brain whose only documents are scoped still counts
    as a brain with documents (the reply judge then grounds on documents, not on the role alone)."""
    try:
        return any(scope for _, scope in _ung_vien(Path(str(root))))
    except Exception:
        return False


def scoped_docs(root: Any, chat_id: Any) -> List[dict]:
    """The scoped documents of ONE chat as extra documents ({path, title, text}) for `chi_muc`/`tim`/`thu_thap`,
    frontmatter stripped. Empty without a chat id."""
    r = Path(str(root))
    out = []
    for rel in scoped_paths(r, chat_id):
        try:
            raw = (r / rel).read_text(encoding="utf-8", errors="replace")[:MAX_BYTES]
        except OSError:
            continue
        raw = re.sub(r"\A\ufeff?---\n.*?\n---\n", "", raw, flags=re.DOTALL)
        out.append({"path": rel, "title": Path(rel).stem, "text": raw})
    return out


def ds_tai_lieu(root: Any, chat_id: Any = None) -> List[str]:
    """Đường dẫn tương đối (dạng posix) của mọi file được tính là tài liệu của bot. Bộ công cụ đọc
    tài liệu ở mức "Đọc tài liệu" (`chatbot_doc_tools`) chỉ mở được đúng những file trong danh sách
    này, nên nó không bao giờ thấy nhiều hơn phần tra sẵn đã thấy.

    `chat_id` (0.338.0): add the scoped documents of that chat (see `scoped_docs`). None or "" adds none."""
    r = Path(str(root))
    try:
        return [p.relative_to(r).as_posix() for p in _duyet(r)] + scoped_paths(r, chat_id)
    except Exception as e:
        print(f"[chatbot grounding] liệt kê {r} lỗi: {e}", file=sys.stderr)
        return []


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


def _dung_chi_muc(root: Path, extra: Optional[List[dict]] = None) -> dict:
    manh: List[dict] = []
    # Documents that are not files of the brain (Google Docs/Sheets linked from the bot's Agent, see
    # bot_linked_docs). Indexed together with the files so IDF weighs a word against everything the
    # bot knows, not against two separate piles.
    for d in extra or []:
        ten = str(d.get("title") or d.get("path") or "")
        for m in _cat_manh(str(d.get("text") or "")[:MAX_BYTES], ten):
            m["path"] = str(d.get("path") or ten)
            m["cap"] = _tach_cap(m["ten"] + " " + ten + " " + m["text"])
            manh.append(m)
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


def _van_extra(extra: Optional[List[dict]]) -> tuple:
    """Fingerprint of the extra documents: which ones, and their exact text."""
    return tuple((str(d.get("path") or ""), hashlib.sha1(str(d.get("text") or "").encode(
        "utf-8", "replace")).hexdigest()) for d in (extra or []))


def chi_muc(root: Any, extra: Optional[List[dict]] = None) -> dict:
    """Chỉ mục của một brain, dựng lười và dùng lại cho tới khi file đổi.

    `extra`: documents that are not files (see `_dung_chi_muc`). A brain with extras gets its own
    cache slot per SET of extras, so two bots on one brain with different Agents never see each
    other's linked documents."""
    r = Path(str(root))
    key = str(r.resolve()) if r.exists() else str(r)
    ve = _van_extra(extra)
    if ve:
        key += "|extra:" + "|".join(sorted(p for p, _ in ve))
    try:
        van = (_dau_van(r), ve)
    except Exception as e:
        print(f"[chatbot grounding] quét {r} lỗi: {e}", file=sys.stderr)
        return {"manh": [], "idf": {}}
    with _lock:
        c = _CACHE.get(key)
        if c and c.get("van") == van:
            return c["ix"]
    ix = _dung_chi_muc(r, extra)
    with _lock:
        _CACHE.pop(key, None)
        while len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = {"van": van, "ix": ix}
    return ix


def xoa_cache() -> None:
    with _lock:
        _CACHE.clear()
        _SCOPE_CACHE.clear()


# ============================================================
# Tìm
# ============================================================
def tim(root: Any, cau_hoi: str, k: int = 4, extra: Optional[List[dict]] = None,
        chat_id: Any = None) -> List[dict]:
    """Các mảnh tài liệu khớp nhất với câu hỏi, sắp theo điểm giảm dần.

    `chat_id` (0.338.0): also search the scoped documents of that chat, and only that chat."""
    cap = _tach_cap(cau_hoi)
    if not cap:
        return []
    scoped = scoped_docs(root, chat_id)
    ix = chi_muc(root, list(extra or []) + scoped if scoped else extra)
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


def thu_thap(root: Any, cau_hoi: str, k: int = 4, extra: Optional[List[dict]] = None,
             chat_id: Any = None) -> dict:
    """Khối tài liệu nhét vào prompt cho MỘT câu hỏi.

    Trả `{"co": bool, "khoi": str, "nguon": [path...]}`. `co=False` nghĩa là brain không có gì
    khớp - lúc đó prompt phải nói thẳng ra như vậy thay vì im lặng đưa một khối rỗng, vì im
    lặng thì model tự lấp bằng trí nhớ chung của nó.
    """
    try:
        hit = tim(root, cau_hoi, k, extra, chat_id)
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
