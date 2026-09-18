"""share_render.py - dựng TRANG XEM cho một file được chia sẻ công khai.

Vì sao dựng ở PHÍA MÁY CHỦ chứ không mượn `dashboard/chat-render.js`: trang chia sẻ chạy trong
hộp cách ly (xem `CSP_*` bên dưới) và người xem KHÔNG đăng nhập. chat-render.js cần cả tá thứ
chỉ có trong app đã đăng nhập (`window.t`, `window.ic`, `JavisHighlight`, `JavisLightbox`...)
và mọi đường dẫn nó sinh ra đều trỏ vào endpoint cần cookie. Dựng bằng Python thì trang .md
thành HTML TĨNH: không cần một dòng script nào, nên nó được cách ly ở mức chặt nhất, lại xem
được cả khi trình duyệt tắt JavaScript, và kiểm thử được bằng hàm thuần.

Đánh đổi đã biết: bộ dựng này KHÔNG bằng chat-render.js (không mermaid, không tô màu mã, không
wikilink thông minh). Nó cố ý nhỏ, chỉ lo đúng thứ người ta cần khi xem một trang chia sẻ.

AN TOÀN: mọi HTML thô trong file .md đều bị escape chứ không cho chạy. Markdown chuẩn cho phép
nhúng HTML thô, nhưng ở đây nội dung sẽ được người lạ mở, và nhiều file .md trong brain do AI
viết ra. Cho chạy HTML thô là mở đúng cái cửa mà lớp cách ly sinh ra để đóng.
"""
import html as _html
import json
import re
from urllib.parse import quote

# Hộp cách ly. `sandbox` không kèm `allow-same-origin` nghĩa là trang nhận một GỐC RỖNG: script
# trong đó không đọc được cookie đăng nhập Javis, không gọi được API của app dưới danh nghĩa
# người đang mở. Đây là điều kiện để dám phục vụ HTML do người dùng viết trên cùng tên miền với
# dashboard - thiếu nó thì chính chủ bấm vào link của mình lúc đang đăng nhập là trao toàn
# quyền cho nội dung file.
#
# Trang .md/.txt do CHÍNH module này dựng ra và không có script, nên nó bị cách ly CHẶT HƠN:
# không allow-scripts luôn.
CSP_HTML = "sandbox allow-scripts allow-forms allow-popups allow-modals allow-downloads"
CSP_TINH = "sandbox"

DUOI_HTML = (".html", ".htm")
DUOI_MD = (".md", ".markdown")
DUOI_ANH = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif", ".bmp", ".ico")
DUOI_XEM_THANG = DUOI_ANH + (".pdf", ".mp4", ".webm", ".mp3", ".wav", ".ogg", ".m4a")

# Đuôi được phép lấy qua `/s/<token>/asset`. DANH SÁCH CHO PHÉP chứ không phải danh sách cấm,
# và cố ý CHỈ có tài nguyên trình bày: ảnh, kiểu dáng, mã trang, phông, âm thanh, phim.
#
# Vì sao không cho tài liệu (.md, .txt, .html, .json, .csv...): phạm vi của asset là thư mục
# chứa file được chia sẻ. Khi file ấy nằm ngay GỐC BRAIN thì "thư mục chứa nó" chính là cả
# brain, và một token lẻ sẽ đọc được mọi ghi chú khác. Bó theo LOẠI FILE đóng đúng cửa đó mà
# không làm hỏng hai nhu cầu thật: .md cần ảnh, và trang .html cần css/js của nó.
DUOI_TAI_NGUYEN = DUOI_ANH + (
    ".css", ".js", ".mjs", ".map",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp4", ".webm", ".mp3", ".wav", ".ogg", ".m4a",
)


def esc(s) -> str:
    """Escape HTML. Công khai vì main.py cũng cần khi dựng dòng chân trang."""
    return _html.escape(str(s if s is not None else ""), quote=True)


_esc = esc


def _la_lien_ket_ngoai(u: str) -> bool:
    u = (u or "").strip().lower()
    return u.startswith(("http://", "https://", "mailto:", "tel:", "#", "data:image/"))


def _url_tai_nguyen(duong_dan: str, goc_asset: str) -> str:
    """Đường dẫn tương đối trong file -> URL công khai đi qua chính token đang xem.

    Người xem không đăng nhập nên không với được /files/raw. Ảnh kèm theo phải đi qua
    `/s/<token>/asset`, và endpoint đó tự khoá phạm vi quanh file được chia sẻ.
    """
    d = (duong_dan or "").strip()
    if not d or _la_lien_ket_ngoai(d):
        return d
    return goc_asset + "?p=" + quote(d.replace("\\", "/").lstrip("/"), safe="")


# ---------------------------------------------------------------- markdown -> html
_FENCE = re.compile(r"^```([^\n]*)\n(.*?)(?:^```\s*$|\Z)", re.S | re.M)


def _inline(s: str, goc_asset: str) -> str:
    """Phần trong MỘT dòng: mã, ảnh, link, đậm, nghiêng, gạch ngang.

    Thứ tự quan trọng. `code` được rút ra TRƯỚC và cất vào chỗ giữ, vì bên trong dấu nháy
    ngược thì dấu sao không còn là cú pháp - không cất trước thì `*` trong một đoạn mã bị
    hiểu thành in nghiêng và đoạn mã vỡ.
    """
    giu = []

    def _cat(hm):
        giu.append(hm)
        return "\x00%d\x00" % (len(giu) - 1)

    s = re.sub(r"`([^`\n]+)`", lambda m: _cat("<code>" + _esc(m.group(1)) + "</code>"), s)
    s = _esc(s)                                   # escape SAU khi cất mã, TRƯỚC khi sinh thẻ

    # ![[ảnh.png]] và [[ghi chú]] - quy ước wikilink của vault.
    s = re.sub(r"!\[\[([^\]\|]+?)(?:\|[^\]]*)?\]\]",
               lambda m: _cat('<img src="%s" alt="%s" loading="lazy">'
                              % (_esc(_url_tai_nguyen(m.group(1), goc_asset)), _esc(m.group(1)))), s)
    s = re.sub(r"\[\[([^\]\|]+?)(?:\|([^\]]*))?\]\]",
               lambda m: _cat("<span class=\"wk\">" + _esc(m.group(2) or m.group(1)) + "</span>"), s)
    # ![alt](src)
    s = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)[^)]*\)",
               lambda m: _cat('<img src="%s" alt="%s" loading="lazy">'
                              % (_esc(_url_tai_nguyen(m.group(2), goc_asset)), _esc(m.group(1)))), s)
    # [chữ](đích) - chỉ nhận đích an toàn; javascript: bị bỏ hẳn, chỉ còn lại chữ.
    def _link(m):
        dich = m.group(2)
        if _la_lien_ket_ngoai(dich):
            return _cat('<a href="%s" target="_blank" rel="noopener noreferrer nofollow">%s</a>'
                        % (_esc(dich), m.group(1)))
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", dich):     # scheme lạ (javascript:, vbscript:...)
            return m.group(1)
        return _cat('<a href="%s">%s</a>' % (_esc(_url_tai_nguyen(dich, goc_asset)), m.group(1)))

    s = re.sub(r"\[([^\]]*)\]\(([^)\s]+)[^)]*\)", _link, s)
    s = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"__(.+?)__", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"(?<![\w_])_([^_\n]+?)_(?![\w_])", r"<em>\1</em>", s)
    s = re.sub(r"~~(.+?)~~", r"<del>\1</del>", s)
    for i, hm in enumerate(giu):
        s = s.replace("\x00%d\x00" % i, hm)
    return s


def _bang(khoi: list, goc_asset: str) -> str:
    """Bảng markdown. `khoi` là các dòng, dòng thứ hai là dòng gạch ngăn."""
    def o(dong):
        d = dong.strip()
        if d.startswith("|"):
            d = d[1:]
        if d.endswith("|"):
            d = d[:-1]
        return [c.strip() for c in d.split("|")]

    dau = o(khoi[0])
    than = [o(x) for x in khoi[2:]]
    ra = ["<table><thead><tr>"]
    ra += ["<th>%s</th>" % _inline(c, goc_asset) for c in dau]
    ra.append("</tr></thead><tbody>")
    for h in than:
        ra.append("<tr>" + "".join("<td>%s</td>" % _inline(c, goc_asset) for c in h) + "</tr>")
    ra.append("</tbody></table>")
    return "".join(ra)


def md_to_html(src: str, goc_asset: str = "") -> str:
    """Markdown -> HTML (chỉ phần thân, không kèm khung trang)."""
    src = str(src or "").replace("\r\n", "\n").replace("\r", "\n")
    giu_khoi = []

    def _cat_khoi(hm):
        giu_khoi.append(hm)
        return "\n\x01%d\x01\n" % (len(giu_khoi) - 1)

    # Frontmatter YAML ở đầu file: giấu đi, đó là dữ liệu quản trị chứ không phải nội dung.
    src = re.sub(r"\A---\n.*?\n---\n", "", src, flags=re.S)
    # Khối mã rút trước mọi thứ, giữ nguyên từng ký tự.
    src = _FENCE.sub(lambda m: _cat_khoi(
        '<pre class="code"><code>%s</code></pre>' % _esc(m.group(2))), src)

    ra, dong, i = [], src.split("\n"), 0
    dsach = None       # ("ul"|"ol", [các mục])

    def dong_ds():
        nonlocal dsach
        if dsach:
            the, muc = dsach
            ra.append("<%s>%s</%s>" % (the, "".join("<li>%s</li>" % m for m in muc), the))
            dsach = None

    while i < len(dong):
        d = dong[i]
        t = d.strip()
        if not t:
            dong_ds()
            i += 1
            continue
        if re.match(r"^\x01\d+\x01$", t):                       # chỗ giữ khối mã
            dong_ds()
            ra.append(t)
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", t):
            dong_ds()
            ra.append("<hr>")
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", t)
        if m:
            dong_ds()
            c = len(m.group(1))
            ra.append("<h%d>%s</h%d>" % (c, _inline(m.group(2), goc_asset), c))
            i += 1
            continue
        if t.startswith(">"):
            dong_ds()
            gom = []
            while i < len(dong) and dong[i].strip().startswith(">"):
                gom.append(re.sub(r"^\s*>\s?", "", dong[i]))
                i += 1
            ra.append("<blockquote>%s</blockquote>" % md_to_html("\n".join(gom), goc_asset))
            continue
        if (t.startswith("|") and i + 1 < len(dong)
                and re.match(r"^\s*\|?[\s:\-|]+\|[\s:\-|]*$", dong[i + 1])):
            dong_ds()
            gom = []
            while i < len(dong) and dong[i].strip().startswith("|"):
                gom.append(dong[i])
                i += 1
            if len(gom) >= 2:
                ra.append(_bang(gom, goc_asset))
                continue
            i -= len(gom)
        m = re.match(r"^\s*[-*+]\s+(.*)$", d)
        if m:
            if not dsach or dsach[0] != "ul":
                dong_ds()
                dsach = ("ul", [])
            dsach[1].append(_inline(m.group(1), goc_asset))
            i += 1
            continue
        m = re.match(r"^\s*\d+[.)]\s+(.*)$", d)
        if m:
            if not dsach or dsach[0] != "ol":
                dong_ds()
                dsach = ("ol", [])
            dsach[1].append(_inline(m.group(1), goc_asset))
            i += 1
            continue
        dong_ds()
        gom = []                                                 # đoạn văn: gộp các dòng liền nhau
        while i < len(dong) and dong[i].strip() and not re.match(
                r"^\s*(#{1,6}\s|[-*+]\s|\d+[.)]\s|>|\||\x01\d+\x01$|-{3,}$|\*{3,}$)", dong[i]):
            gom.append(dong[i].strip())
            i += 1
        ra.append("<p>%s</p>" % _inline("\n".join(gom), goc_asset).replace("\n", "<br>"))
    dong_ds()

    than = "\n".join(ra)
    for idx, hm in enumerate(giu_khoi):
        than = than.replace("\x01%d\x01" % idx, hm)
    return than


# ---------------------------------------------------------------- khung trang
_CSS = """*{box-sizing:border-box}
:root{--bg:#faf8f5;--fg:#221f1c;--mo:#6b625a;--vien:#e7e0d6;--ma:#f3efe8;--nhan:#c2610f}
@media(prefers-color-scheme:dark){:root{--bg:#141210;--fg:#ece5dc;--mo:#9d948a;
 --vien:#332c25;--ma:#1e1a17;--nhan:#e8973f}}
html{-webkit-text-size-adjust:100%}
body{margin:0;padding:28px 18px 64px;background:var(--bg);color:var(--fg);
 font:17px/1.7 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;
 overflow-wrap:break-word}
main{max-width:760px;margin:0 auto}
h1,h2,h3,h4,h5,h6{line-height:1.3;margin:1.6em 0 .5em;font-weight:700}
h1{font-size:1.75em;margin-top:0}h2{font-size:1.4em}h3{font-size:1.18em}
p,ul,ol,blockquote,table,pre{margin:0 0 1em}
ul,ol{padding-left:1.4em}li{margin:.3em 0}
a{color:var(--nhan)}
img{max-width:100%;height:auto;border-radius:10px;display:block;margin:1em 0}
code{background:var(--ma);padding:.15em .4em;border-radius:5px;font-size:.92em;
 font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
pre.code{background:var(--ma);border:1px solid var(--vien);border-radius:12px;
 padding:14px 16px;overflow:auto}
pre.code code{background:none;padding:0;font-size:.88em;line-height:1.55}
blockquote{border-left:3px solid var(--nhan);padding:.1em 0 .1em 14px;color:var(--mo)}
hr{border:0;border-top:1px solid var(--vien);margin:2em 0}
table{border-collapse:collapse;width:100%;display:block;overflow-x:auto}
th,td{border:1px solid var(--vien);padding:8px 11px;text-align:left}
th{background:var(--ma)}
.wk{color:var(--nhan)}
footer{max-width:760px;margin:40px auto 0;padding-top:16px;border-top:1px solid var(--vien);
 color:var(--mo);font-size:14px}
"""


def trang(tieu_de: str, than: str, chan: str = "") -> str:
    """Khung HTML hoàn chỉnh, tự chứa: không script, không tải gì từ bên ngoài.

    Cỡ chữ thân 17px và bề ngang tối đa 760px: trang này hay được mở trên điện thoại vì nó
    được gửi qua tin nhắn. Có sẵn cả tông sáng lẫn tối theo cài đặt máy người xem.
    """
    return (
        "<!DOCTYPE html>\n<html lang=\"vi\"><head><meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        "<meta name=\"robots\" content=\"noindex,nofollow\">\n"
        "<title>" + _esc(tieu_de) + "</title>\n<style>" + _CSS + "</style></head>\n"
        "<body><main>" + than + "</main>"
        + ("<footer>" + chan + "</footer>" if chan else "")
        + "</body></html>\n")


def trang_van_ban(tieu_de: str, noi_dung: str, chan: str = "") -> str:
    """File .txt và mã nguồn: giữ NGUYÊN từng ký tự trong một khối, không diễn giải gì."""
    return trang(tieu_de, "<h1>" + _esc(tieu_de) + "</h1><pre class=\"code\"><code>"
                 + _esc(noi_dung) + "</code></pre>", chan)


def trang_markdown(tieu_de: str, src: str, goc_asset: str, chan: str = "") -> str:
    return trang(tieu_de, md_to_html(src, goc_asset), chan)


def trang_loi(thong_diep: str) -> str:
    return trang("Không mở được", "<h1>Không mở được</h1><p>" + _esc(thong_diep) + "</p>")


def json_an_toan(o) -> str:
    return json.dumps(o, ensure_ascii=False)
