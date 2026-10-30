"""Nén gọn JS/CSS của dashboard lúc phục vụ (0.416.0). Không bước build, mã nguồn giữ nguyên để đọc và sửa.

VÌ SAO
Dashboard là JS thuần, chú thích tiếng Việt viết rất dày (đó là cách repo này giữ lý do của từng quyết định). Đo ngày
30/10/2026: 118 file JS nạp lúc mở trang nặng 1,19 MB sau gzip, trình duyệt tải và đọc qua toàn bộ chú thích ấy. Bỏ
chú thích và thụt đầu dòng là bớt gần một nửa, đúng vào lúc người dùng chờ nhất: lần mở đầu và ngay sau mỗi bản cập nhật.

VÌ SAO TỰ VIẾT MÀ KHÔNG DÙNG rjsmin
Đã thử rjsmin 1.3.0 trên chính các file này rồi so token bằng acorn: 3 file sai. Nó nuốt khoảng trắng BÊN TRONG chuỗi
template (`" target="_blank"` thành `"target="_blank"`), làm hỏng HTML mà không báo gì. Bộ ở đây cố ý dè dặt hơn:
- không bao giờ đụng vào bên trong chuỗi, template, regex;
- chỉ bỏ chú thích và khoảng trắng GIỮA các token;
- khoảng trắng và chú thích có xuống dòng thì giữ ĐÚNG SỐ dấu xuống dòng đó: luật tự chèn dấu chấm phẩy (ASI) không đổi
  nghĩa, và số dòng của bản nén trùng mã nguồn, nên lỗi máy khách gửi về (loi-may-khach.js) và công cụ của trình duyệt
  vẫn chỉ đúng dòng cần sửa (mỗi dòng tốn thêm một byte, gzip nén gần hết);
- chỉ bỏ hẳn khoảng trắng khi một bên là dấu chắc chắn không dính được vào bên kia.
`tests/js/test_tinh_gon.mjs` chạy bộ này trên MỌI file JS của dashboard rồi so từng token với bản gốc bằng acorn.

An toàn khi hỏng: mọi lỗi (file lạ, regex đoán sai, ngoại lệ) đều trả lại nguyên bản gốc. Tắt hẳn bằng
JAVIS_MINIFY=0.
"""
from __future__ import annotations

import os
import zlib
from pathlib import Path

# Sau các từ khoá này, dấu "/" mở một regex chứ không phải phép chia.
_TU_TRUOC_REGEX = {
    "return", "typeof", "instanceof", "in", "of", "new", "delete", "void", "throw", "case", "do", "else",
    "yield", "await",
}
# Một khoảng trắng được bỏ hẳn khi ít nhất một bên là một trong các dấu này: chúng không bao giờ dính với ký tự bên
# cạnh thành một token khác. Cố ý vắng mặt: + - . / (dính thành ++, --, số thập phân, chú thích), < > ! (dính thành
# chú thích kiểu HTML `<!--`, `-->`), và dấu nháy.
_DAU_AN_TOAN = set("{}()[];,:=?&|*%^~")
_KY_TU_TEN = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$\\")


_KHOANG_TRANG = " \t\r\n\f\v\u00a0\ufeff\u2028\u2029"
_XUONG_DONG = "\n\r\u2028\u2029"


def _so_dong(doan: str) -> int:
    """Số dấu xuống dòng trong một đoạn bị bỏ (CRLF tính là một)."""
    return doan.count("\n") + doan.count("\u2028") + doan.count("\u2029") + doan.replace("\r\n", "\n").count("\r")


def _la_ten(c: str) -> bool:
    return c in _KY_TU_TEN or ord(c) > 127


def nen_js(src: str) -> str:
    """Bỏ chú thích và khoảng trắng thừa. Ném ValueError khi gặp thứ không chắc (chuỗi không đóng...)."""
    out: list[str] = []
    n = len(src)
    i = 0
    truoc = ""            # token có nghĩa ngay trước (để đoán "/" là regex hay phép chia)
    cho_khoang = ""       # "", " " hoặc "\n" * k: khoảng trắng/chú thích vừa bỏ, chờ quyết định khi gặp token sau
    ngoac_tpl: list[int] = []   # mỗi `${` đang mở: số ngoặc nhọn đã mở bên trong nó

    def ghi(tok: str, loai: str) -> None:
        nonlocal cho_khoang, truoc
        if cho_khoang and not out and cho_khoang[0] == "\n":
            out.append(cho_khoang)   # chú thích đầu file thành dòng trống: giữ số dòng
        elif cho_khoang and out:
            a = out[-1][-1]
            b = tok[0]
            if cho_khoang[0] == "\n":
                out.append(cho_khoang)
            elif a == "/" or b == "/":
                out.append(" ")
            elif a in _DAU_AN_TOAN or b in _DAU_AN_TOAN:
                pass
            else:
                out.append(" ")
        cho_khoang = ""
        out.append(tok)
        truoc = loai

    def them_khoang(doan: str) -> None:
        """Gộp một đoạn bị bỏ (khoảng trắng, chú thích) vào khoảng chờ, đếm đủ số dòng."""
        nonlocal cho_khoang
        k = _so_dong(doan)
        if k:
            cho_khoang = (cho_khoang if cho_khoang[:1] == "\n" else "") + "\n" * k
        elif not cho_khoang:
            cho_khoang = " "

    def regex_duoc() -> bool:
        if not truoc:
            return True
        if truoc.startswith("ten:"):
            return truoc[4:] in _TU_TRUOC_REGEX
        if truoc in ("so", "chuoi", "tpl", "regex"):
            return False
        # dấu câu
        return truoc not in ("dau:)", "dau:]", "dau:}")

    def doc_tpl(j: int) -> int:
        """Đọc một đoạn template từ j (ngay sau ` hoặc sau } đóng ${), tới ` hoặc ${. Trả vị trí sau đó."""
        while j < n:
            c = src[j]
            if c == "\\":
                j += 2
                continue
            if c == "`":
                return j + 1
            if c == "$" and j + 1 < n and src[j + 1] == "{":
                return j + 2
            j += 1
        raise ValueError("template không đóng")

    while i < n:
        c = src[i]
        # khoảng trắng
        if c in _KHOANG_TRANG:
            j = i
            while j < n and src[j] in _KHOANG_TRANG:
                j += 1
            them_khoang(src[i:j])
            i = j
            continue
        # chú thích
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = i + 2
            while j < n and src[j] not in _XUONG_DONG:
                j += 1
            them_khoang(" ")
            i = j
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            if j < 0:
                raise ValueError("chú thích khối không đóng")
            them_khoang(src[i:j] + " ")
            i = j + 2
            continue
        # chuỗi
        if c in "'\"":
            j = i + 1
            while j < n and src[j] != c:
                if src[j] == "\\":
                    j += 1
                elif src[j] in "\n\r":
                    raise ValueError("chuỗi không đóng")
                j += 1
            if j >= n:
                raise ValueError("chuỗi không đóng")
            ghi(src[i:j + 1], "chuoi")
            i = j + 1
            continue
        # template
        if c == "`":
            j = doc_tpl(i + 1)
            ghi(src[i:j], "tpl")
            if src[j - 2:j] == "${":
                ngoac_tpl.append(0)
                truoc = "dau:{"
            i = j
            continue
        if c == "}" and ngoac_tpl and ngoac_tpl[-1] == 0:
            ngoac_tpl.pop()
            j = doc_tpl(i + 1)
            ghi(src[i:j], "tpl")
            if src[j - 2:j] == "${":
                ngoac_tpl.append(0)
                truoc = "dau:{"
            i = j
            continue
        # regex
        if c == "/" and regex_duoc():
            j = i + 1
            trong_lop = False
            while j < n:
                ch = src[j]
                if ch == "\\":
                    j += 2
                    continue
                if ch in "\n\r":
                    raise ValueError("regex không đóng")
                if ch == "[":
                    trong_lop = True
                elif ch == "]":
                    trong_lop = False
                elif ch == "/" and not trong_lop:
                    break
                j += 1
            if j >= n:
                raise ValueError("regex không đóng")
            j += 1
            while j < n and _la_ten(src[j]):
                j += 1
            ghi(src[i:j], "regex")
            i = j
            continue
        # tên, số
        if _la_ten(c):
            j = i
            while j < n and (_la_ten(src[j]) or (src[j] == "." and src[i].isdigit())
                             or (src[i].isdigit() and src[j] in "+-" and src[j - 1] in "eE"
                                 and not src[i:j].lower().startswith("0x"))):
                j += 1
            tok = src[i:j]
            ghi(tok, "so" if c.isdigit() else "ten:" + tok)
            i = j
            continue
        if c == "." and i + 1 < n and src[i + 1].isdigit():
            j = i + 1
            while j < n and (_la_ten(src[j]) or src[j] == "."):
                j += 1
            ghi(src[i:j], "so")
            i = j
            continue
        # dấu câu: một ký tự một lần (gộp nhiều ký tự không cần, vì không chèn gì vào giữa chúng)
        if c == "{" and ngoac_tpl:
            ngoac_tpl[-1] += 1
        elif c == "}" and ngoac_tpl:
            ngoac_tpl[-1] -= 1
        ghi(c, "dau:" + c)
        i += 1
    if ngoac_tpl:
        raise ValueError("template không đóng")
    return "".join(out).rstrip() + "\n"


def nen_css(src: str) -> str:
    """Bỏ chú thích, gộp khoảng trắng, bỏ khoảng trắng quanh { } ; và giữ nguyên chuỗi. Khoảng trắng sau dấu phẩy
    được giữ: trong biến CSS (`--x: rgba(1, 2, 3)`) trình duyệt giữ nguyên văn bản giá trị, bỏ nó là đổi giá trị."""
    out: list[str] = []
    n = len(src)
    i = 0
    khoang = False
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            if j < 0:
                raise ValueError("chú thích không đóng")
            i = j + 2
            khoang = True
            continue
        if c in " \t\r\n\f":
            khoang = True
            i += 1
            continue
        if c in "'\"":
            j = i + 1
            while j < n and src[j] != c:
                if src[j] == "\\":
                    j += 1
                j += 1
            if j >= n:
                raise ValueError("chuỗi không đóng")
            tok = src[i:j + 1]
            i = j + 1
        else:
            tok = c
            i += 1
        if khoang and out and out[-1][-1] not in "{};" and tok[0] not in "{};":
            out.append(" ")
        khoang = False
        out.append(tok)
    return "".join(out).strip() + "\n"


def bat() -> bool:
    return os.environ.get("JAVIS_MINIFY", "1").strip().lower() not in ("0", "false", "no", "off")


def nen_duoc(rel: str) -> bool:
    """File nào được nén: .js/.css của dashboard, trừ thứ đã nén sẵn (vendor *.min.*)."""
    rel = rel.replace("\\", "/")
    return (rel.endswith(".js") or rel.endswith(".css")) and ".min." not in rel.rsplit("/", 1)[-1]


_NHO: dict = {}   # đường dẫn tuyệt đối -> (khoá (mtime_ns, size, bat), bytes đã phục vụ, crc)


def ban_phuc_vu(path: Path, rel: str) -> tuple[bytes, str]:
    """Bytes sẽ gửi cho trình duyệt (bản nén nếu nén được, không thì bản gốc) và crc32 của CHÍNH các bytes đó.
    crc đi vào khoá `?v=` và khối javis-fresh, nên freshness.js so đúng thứ trình duyệt nhận được."""
    st = path.stat()
    khoa = (st.st_mtime_ns, st.st_size, bat())
    ent = _NHO.get(str(path))
    if ent and ent[0] == khoa:
        return ent[1], ent[2]
    goc = path.read_bytes()
    data = goc
    if bat() and nen_duoc(rel):
        try:
            text = goc.decode("utf-8")
            gon = nen_js(text) if rel.endswith(".js") else nen_css(text)
            data = gon.encode("utf-8")
        except Exception:   # noqa: BLE001 - hỏng gì cũng phục vụ bản gốc, không bao giờ làm vỡ trang
            data = goc
    crc = format(zlib.crc32(data) & 0xFFFFFFFF, "08x")
    _NHO[str(path)] = (khoa, data, crc)
    return data, crc


if __name__ == "__main__":
    # python server/tinh_gon.py <file>             : in bản nén ra stdout
    # python server/tinh_gon.py --all <gốc> <đích>  : nén mọi file nén được dưới <gốc> vào <đích> (test dùng)
    import sys
    if sys.argv[1] == "--all":
        goc, dich = Path(sys.argv[2]), Path(sys.argv[3])
        for f in sorted(goc.rglob("*")):
            rel = f.relative_to(goc).as_posix()
            if not f.is_file() or not nen_duoc(rel):
                continue
            t = f.read_text(encoding="utf-8")
            o = dich / rel
            o.parent.mkdir(parents=True, exist_ok=True)
            o.write_text(nen_js(t) if f.suffix == ".js" else nen_css(t), encoding="utf-8")
    else:
        p = Path(sys.argv[1])
        t = p.read_text(encoding="utf-8")
        sys.stdout.write(nen_js(t) if p.suffix == ".js" else nen_css(t))
