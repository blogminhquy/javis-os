"""Công cụ file cho LẬP TRÌNH của engine API: đọc theo đoạn, sửa từng đoạn, tìm trong code (0.256.0).

Vì sao có file này
------------------
Trước 0.256.0, engine API (OpenRouter, OpenAI, Anthropic API, Gemini...) chỉ có ba tool file:
đọc nguyên file, ghi đè nguyên file, liệt kê thư mục. Muốn sửa MỘT dòng trong file 2.000 dòng
thì model phải viết lại cả 2.000 dòng: chậm, tốn token, và hay làm rơi mất code ở đoạn nó
không để ý. Claude Code, Codex và Hermes Agent đều có công cụ "thay đoạn này bằng đoạn kia",
và đó là lý do chính chúng sửa code chính xác.

Thiết kế học từ Hermes Agent (github.com/NousResearch/hermes-agent, giấy phép MIT):
`tools/fuzzy_match.py` (chuỗi chiến lược khớp mờ), `tools/file_tools.py` (đọc có số dòng,
lỗi dạy được model), `tools/file_operations_lint.py` (chỉ báo lỗi do lần sửa sinh ra),
`tools/file_tools_write_guards.py` (chặn ghi đè file chưa đọc). Viết lại theo kiểu Javis,
không chép nguyên khối.

Module này KHÔNG biết gì về hub, quyền hay đường dẫn an toàn: nó nhận đường dẫn ĐÃ được
`mcp_hub._safe_path` duyệt. Tách như vậy để test được bằng một thư mục tạm, không cần dựng
hub, và để quyết định "được chạm vào đâu" chỉ nằm ở một chỗ.

Stdlib-only.
"""
from __future__ import annotations

import ast
import difflib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import winproc         # lệnh con chạy câm trên Windows (không nháy cửa sổ console đen)

# ---------------------------------------------------------------------------------------
# Đọc theo đoạn
# ---------------------------------------------------------------------------------------
# Mỗi lần đọc tối đa 2000 dòng (giống Hermes) và 50.000 ký tự. Hermes để 100.000, nhưng vòng tool
# của Javis cắt mọi kết quả ở `engine.CAT_KET_QUA_CODING` (60.000) trong phiên Coding: một trang
# dài hơn sẽ bị cắt mất khúc giữa. Trang 50.000 thì lọt nguyên, và model đọc tiếp bằng offset.
DOC_DONG_MAC_DINH = 2000
DOC_KY_TU_TOI_DA = 50_000

_SO_DONG_RE = re.compile(r"^\s*\d+\|")


def doc_theo_dong(text: str, offset: int = 1, limit: int = DOC_DONG_MAC_DINH) -> Tuple[str, int, int]:
    """Trả (chữ có số dòng "N|nội dung", dòng cuối đã đọc, tổng số dòng).

    Cắt theo RANH GIỚI DÒNG khi chạm trần ký tự, không bao giờ cắt giữa dòng: một dòng bị cắt
    đôi là một dòng model sẽ chép sai vào old_string ở lượt sửa sau.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "" and text.endswith("\n"):
        lines.pop()
    tong = len(lines)
    try:
        offset = max(1, int(offset or 1))
    except (TypeError, ValueError):
        offset = 1
    try:
        limit = int(limit or DOC_DONG_MAC_DINH)
    except (TypeError, ValueError):
        limit = DOC_DONG_MAC_DINH
    limit = max(1, min(limit, DOC_DONG_MAC_DINH))
    if tong == 0:
        return "(file rỗng)", 0, 0
    if offset > tong:
        return f"(file chỉ có {tong} dòng, offset {offset} đã quá cuối file)", tong, tong
    ra, dung, cuoi = [], 0, offset - 1
    rong = len(str(min(tong, offset + limit - 1)))
    for i in range(offset - 1, min(tong, offset - 1 + limit)):
        dong = f"{str(i + 1).rjust(rong)}|{lines[i]}"
        if dung + len(dong) + 1 > DOC_KY_TU_TOI_DA and ra:
            break
        ra.append(dong)
        dung += len(dong) + 1
        cuoi = i + 1
    out = "\n".join(ra)
    if cuoi < tong:
        out += (f"\n… [đã đọc dòng {offset}-{cuoi} trên tổng {tong}. Đọc tiếp: gọi lại với "
                f"offset={cuoi + 1}]")
    return out, cuoi, tong


# ---------------------------------------------------------------------------------------
# Sổ "đã đọc" để chặn ghi đè file chưa đọc
# ---------------------------------------------------------------------------------------
# Khoá theo (phiên, đường dẫn tuyệt đối). Chỉ phiên Coding dùng sổ này: brain vẫn ghi ghi chú
# như cũ, không bắt đọc trước, vì luồng đó (ghi nhớ, báo cáo, nháp) chưa bao giờ cần.
_SO_DOC: Dict[Tuple[str, str], dict] = {}
_SO_DOC_KHOA = threading.Lock()
_SO_DOC_TRAN = 4096          # đủ cho một ngày làm việc dài, không thành chỗ rò bộ nhớ


def _mtime_ns(p: Path) -> int:
    try:
        return p.stat().st_mtime_ns
    except OSError:
        return 0


def ghi_nhan_doc(sid: str, p: Path, den_dong: int, tong: int, offset: int = 1) -> None:
    """Ghi lại phiên vừa đọc `p` tới dòng nào. Đọc liên tục từ dòng 1 tới hết là "đọc trọn"."""
    if not sid:
        return
    key = (str(sid), str(Path(p).resolve()))
    with _SO_DOC_KHOA:
        rec = _SO_DOC.get(key) or {}
        mt = _mtime_ns(Path(p))
        if rec.get("mtime") != mt:
            rec = {"mtime": mt, "toi": 0}
        # Liên tục: lần đọc này bắt đầu không sau chỗ đã đọc tới + 1.
        if offset <= int(rec.get("toi") or 0) + 1:
            rec["toi"] = max(int(rec.get("toi") or 0), int(den_dong))
        rec["tong"] = int(tong)
        _SO_DOC[key] = rec
        while len(_SO_DOC) > _SO_DOC_TRAN:
            _SO_DOC.pop(next(iter(_SO_DOC)))


def ghi_nhan_ghi(sid: str, p: Path) -> None:
    """Vừa ghi hoặc sửa xong: nội dung hiện tại là nội dung model biết, coi như đã đọc trọn."""
    if not sid:
        return
    key = (str(sid), str(Path(p).resolve()))
    with _SO_DOC_KHOA:
        _SO_DOC[key] = {"mtime": _mtime_ns(Path(p)), "toi": 10 ** 9, "tong": 0}


def chan_ghi_de(sid: str, p: Path) -> str:
    """Lý do từ chối ghi đè `p`, hoặc "" nếu được ghi. Gọi TRƯỚC khi chạm đĩa."""
    p = Path(p)
    if not sid or not p.exists():
        return ""
    with _SO_DOC_KHOA:
        rec = dict(_SO_DOC.get((str(sid), str(p.resolve()))) or {})
    if not rec:
        return (f"ERROR: chưa ghi đè '{p.name}' vì phiên này chưa đọc file đó. Ghi đè mù là cách "
                f"nhanh nhất làm mất code người khác vừa viết. Sửa vài chỗ thì dùng "
                f"javis_edit_file; thật sự cần viết lại cả file thì đọc trọn nó bằng "
                f"javis_read_file trước rồi ghi.")
    if rec.get("mtime") != _mtime_ns(p):
        return (f"ERROR: chưa ghi đè '{p.name}' vì file đã đổi kể từ lần phiên này đọc nó (có "
                f"thể người dùng vừa sửa tay, hoặc một lệnh vừa ghi vào). Đọc lại file rồi mới "
                f"quyết định, hoặc dùng javis_edit_file để chỉ sửa đúng đoạn cần.")
    if int(rec.get("toi") or 0) < int(rec.get("tong") or 0):
        return (f"ERROR: chưa ghi đè '{p.name}' vì phiên này mới đọc tới dòng {rec.get('toi')} "
                f"trên {rec.get('tong')}. Ghi đè cả file khi chưa thấy hết là xoá mất phần "
                f"chưa đọc. Đọc nốt bằng offset, hoặc dùng javis_edit_file.")
    return ""


def giong_output_doc(content: str) -> bool:
    """Nội dung có phải là output "N|..." của javis_read_file dán lại không."""
    dong = [x for x in str(content or "").split("\n") if x.strip()][:8]
    if len(dong) < 3:
        return False
    return sum(1 for x in dong if _SO_DONG_RE.match(x)) >= max(3, len(dong) - 1)


def _bo_so_dong(text: str) -> str:
    """Bỏ tiền tố "N|" nếu MỌI dòng có chữ đều mang nó (model chép nguyên từ output đọc)."""
    dong = text.split("\n")
    co_chu = [x for x in dong if x.strip()]
    if not co_chu or not all(_SO_DONG_RE.match(x) for x in co_chu):
        return text
    return "\n".join(_SO_DONG_RE.sub("", x, count=1) if x.strip() else x for x in dong)


# ---------------------------------------------------------------------------------------
# Khớp mờ
# ---------------------------------------------------------------------------------------
# Model chép old_string từ trí nhớ hoặc từ output đọc, và hay lệch ở những chỗ người không
# để ý: thụt lề, khoảng trắng cuối dòng, dấu nháy cong, "\n" bị escape hai lần. Một chuỗi chiến
# lược từ chặt tới lỏng gỡ được gần hết các ca đó mà không đoán bừa. Chiến lược ĐẦU TIÊN có
# kết quả thì dùng, nên khớp chính xác luôn thắng.
_UNICODE_MAP = {
    "\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'",
    "\u2014": "--", "\u2013": "-", "\u2026": "...", "\u00a0": " ", "\u2212": "-",
    "\u2002": " ", "\u2003": " ", "\u2009": " ", "\u202f": " ", "\u3000": " ",
}

# Hai chiến lược "tương tự" chỉ chạy khi file không quá dài: chúng so từng cửa sổ dòng bằng
# SequenceMatcher, chi phí nhân theo số dòng file và số dòng old_string.
_TUONG_TU_TOI_DA_DONG = 20_000


def _unicode_chuan(s: str) -> str:
    for k, v in _UNICODE_MAP.items():
        s = s.replace(k, v)
    return s


def _dong_pattern(pattern: str) -> List[str]:
    ds = pattern.split("\n")
    if len(ds) > 1 and ds[-1] == "":
        ds.pop()
    return ds


def _span_dong(lines: List[str], i: int, n: int) -> Tuple[int, int]:
    """Vị trí ký tự của cửa sổ dòng [i, i+n), không gồm ký tự xuống dòng cuối."""
    bat_dau = sum(len(x) + 1 for x in lines[:i])
    ket_thuc = bat_dau + sum(len(x) + 1 for x in lines[i:i + n]) - 1
    return bat_dau, max(bat_dau, ket_thuc)


def _khop_chinh_xac(content: str, pattern: str) -> List[Tuple[int, int]]:
    ra, i = [], 0
    if not pattern:
        return ra
    while True:
        j = content.find(pattern, i)
        if j < 0:
            return ra
        ra.append((j, j + len(pattern)))
        i = j + len(pattern)


def _khop_theo_dong(content: str, pattern: str, bien) -> List[Tuple[int, int]]:
    lines = content.split("\n")
    pat = [bien(x) for x in _dong_pattern(pattern)]
    n = len(pat)
    if n == 0 or n > len(lines):
        return []
    da = [bien(x) for x in lines]
    ra, i = [], 0
    while i <= len(lines) - n:
        if da[i:i + n] == pat:
            ra.append(_span_dong(lines, i, n))
            i += n
        else:
            i += 1
    return ra


def _cs_line_trimmed(content, pattern):
    return _khop_theo_dong(content, pattern, lambda x: x.strip())


def _cs_whitespace(content, pattern):
    return _khop_theo_dong(content, pattern, lambda x: re.sub(r"\s+", " ", x).strip())


def _cs_indent(content, pattern):
    return _khop_theo_dong(content, pattern, lambda x: x.lstrip())


def _cs_escape(content, pattern):
    # Chỉ khi old_string KHÔNG có xuống dòng thật nhưng có "\n" dạng chữ: dấu hiệu model escape
    # hai lần. Có xuống dòng thật mà vẫn chứa "\n" chữ thì đó là mã nguồn thật, đừng đụng.
    if "\n" in pattern or not ("\\n" in pattern or "\\t" in pattern):
        return []
    giai = pattern.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\'", "'")
    return _khop_chinh_xac(content, giai) or _cs_line_trimmed(content, giai)


def _cs_trimmed_boundary(content, pattern):
    p = pattern.strip()
    if not p or p == pattern:
        return []
    return _khop_chinh_xac(content, p)


def _cs_unicode(content, pattern):
    c2, p2 = _unicode_chuan(content), _unicode_chuan(pattern)
    if c2 == content and p2 == pattern:
        return []
    # So theo dòng sau chuẩn hoá: thay ký tự có thể đổi độ dài (… thành ...), nên vị trí ký tự
    # trong bản chuẩn hoá không dùng lại được. Dòng thì vẫn tương ứng một một.
    return _khop_theo_dong(content, pattern, lambda x: _unicode_chuan(x).strip())


def _cs_block_anchor(content, pattern):
    lines = content.split("\n")
    pat = _dong_pattern(pattern)
    n = len(pat)
    if n < 3 or n > len(lines) or len(lines) > _TUONG_TU_TOI_DA_DONG:
        return []
    dau, cuoi = pat[0].strip(), pat[-1].strip()
    if not dau or not cuoi:
        return []
    giua = "\n".join(x.strip() for x in pat[1:-1])
    ung = []
    for i in range(len(lines) - n + 1):
        if lines[i].strip() == dau and lines[i + n - 1].strip() == cuoi:
            g = "\n".join(x.strip() for x in lines[i + 1:i + n - 1])
            ung.append((i, difflib.SequenceMatcher(None, giua, g).ratio()))
    if not ung:
        return []
    nguong = 0.50 if len(ung) == 1 else 0.70
    return [_span_dong(lines, i, n) for i, r in ung if r >= nguong]


def _cs_context_aware(content, pattern):
    lines = content.split("\n")
    pat = [x.strip() for x in _dong_pattern(pattern)]
    n = len(pat)
    if n < 2 or n > len(lines) or len(lines) > _TUONG_TU_TOI_DA_DONG:
        return []
    ra, i = [], 0
    while i <= len(lines) - n:
        ok = True
        for a, b in zip(pat, lines[i:i + n]):
            if not a:
                continue
            b = b.strip()
            if a == b:
                continue
            if difflib.SequenceMatcher(None, a, b).ratio() < 0.80:
                ok = False
                break
        if ok:
            ra.append(_span_dong(lines, i, n))
            i += n
        else:
            i += 1
    return ra


CHIEN_LUOC = (
    ("exact", _khop_chinh_xac),
    ("line_trimmed", _cs_line_trimmed),
    ("whitespace_normalized", _cs_whitespace),
    ("indentation_flexible", _cs_indent),
    ("escape_normalized", _cs_escape),
    ("trimmed_boundary", _cs_trimmed_boundary),
    ("unicode_normalized", _cs_unicode),
    ("block_anchor", _cs_block_anchor),
    ("context_aware", _cs_context_aware),
)
# Hai chiến lược này khớp theo ĐỘ GIỐNG chứ không theo nội dung đã chuẩn hoá: được dùng, nhưng
# không bao giờ cho replace_all (một ngưỡng 70% nhân lên mười chỗ là mười chỗ sửa nhầm) và luôn
# kèm câu nhắc xem lại diff.
TUONG_TU = {"block_anchor", "context_aware"}


def tim_khop(content: str, pattern: str, replace_all: bool = False) -> Tuple[List[Tuple[int, int]], str]:
    """(các vị trí khớp, tên chiến lược). Rỗng nếu không chiến lược nào khớp."""
    for ten, fn in CHIEN_LUOC:
        if replace_all and ten in TUONG_TU:
            continue
        try:
            spans = fn(content, pattern)
        except Exception:
            spans = []
        if spans:
            return spans, ten
    return [], ""


def _thut_le(dong: str) -> str:
    return dong[:len(dong) - len(dong.lstrip())]


def _can_le(new: str, old: str, doan_khop: str) -> str:
    """Khớp mờ theo dòng thì thụt lề trong file có thể khác old_string: dời new_string theo.

    Học bảng đổi thụt lề từ chính các cặp (dòng old, dòng khớp trong file), vì old_string và
    đoạn khớp có cùng số dòng. Model gõ 2 dấu cách mà file dùng 4 thì bảng là {"": "",
    "  ": "    "}, và mọi dòng mới thụt 2 cũng thành 4. Thụt lề chưa thấy trong bảng thì suy theo
    tỷ lệ nếu cả bảng cùng một tỷ lệ, không thì giữ nguyên.
    """
    o_lines = old.split("\n")
    m_lines = doan_khop.split("\n")
    bang: Dict[str, str] = {}
    for a, b in zip(o_lines, m_lines):
        if a.strip() and b.strip():
            bang.setdefault(_thut_le(a), _thut_le(b))
    if all(k == v for k, v in bang.items()):
        return new
    ty_le = {len(v) / len(k) for k, v in bang.items() if k and k.strip(" ") == "" and v.strip(" ") == ""}
    ty_le_chung = next(iter(ty_le)) if len(ty_le) == 1 else None
    ra = []
    for x in new.split("\n"):
        if not x.strip():
            ra.append(x)
            continue
        ind = _thut_le(x)
        if ind in bang:
            ra.append(bang[ind] + x[len(ind):])
        elif ty_le_chung and ind.strip(" ") == "" and ind:
            ra.append(" " * int(round(len(ind) * ty_le_chung)) + x[len(ind):])
        else:
            ra.append(x)
    return "\n".join(ra)


def _dong_cua(content: str, pos: int) -> int:
    return content.count("\n", 0, pos) + 1


def _goi_y_gan_nhat(content: str, pattern: str, tran: int = 3) -> str:
    lines = content.split("\n")
    dau = next((x.strip() for x in _dong_pattern(pattern) if x.strip()), "")
    if not dau or not lines:
        return ""
    chuan = [x.strip() for x in lines]
    gan = difflib.get_close_matches(dau, chuan, n=tran, cutoff=0.5)
    if not gan:
        return ""
    ra, da = [], set()
    for g in gan:
        for i, x in enumerate(chuan):
            if x == g and i not in da:
                da.add(i)
                ra.append(f"  L{i + 1}: {lines[i].strip()[:160]}")
                break
    return "Dòng gần giống nhất trong file:\n" + "\n".join(ra)


# Đếm số lần sửa hỏng liên tiếp trên cùng file trong một phiên: lần thứ 3 thì bảo đọc lại.
_HONG: Dict[Tuple[str, str], int] = {}


def _dem_hong(sid: str, p: Path, tang: bool) -> int:
    key = (str(sid or ""), str(p))
    if not tang:
        _HONG.pop(key, None)
        return 0
    _HONG[key] = _HONG.get(key, 0) + 1
    if len(_HONG) > 2048:
        _HONG.pop(next(iter(_HONG)))
    return _HONG[key]


def thay_the(content: str, old: str, new: str, replace_all: bool = False) -> dict:
    """Tính nội dung mới. Không đụng đĩa.

    Trả dict: ok, content (mới), so_cho, chien_luoc, loi, khong_doi (đã áp từ trước).
    """
    old = _bo_so_dong(str(old or ""))
    new = _bo_so_dong(str(new or ""))
    if not old.strip():
        return {"ok": False, "loi": "old_string rỗng. Truyền đúng đoạn chữ đang có trong file cần thay."}
    if old == new:
        return {"ok": False, "loi": ("old_string và new_string giống hệt nhau nên không có gì để sửa. "
                                     "old_string là đoạn đang có, new_string là đoạn muốn thay vào.")}
    spans, ten = tim_khop(content, old, replace_all)
    if not spans:
        # Sửa này đã áp ở lượt trước (model gửi lại): new_string đã nằm trong file. Coi là xong.
        if new.strip() and new in content:
            return {"ok": True, "content": content, "so_cho": 0, "chien_luoc": "", "khong_doi": True}
        goi_y = _goi_y_gan_nhat(content, old)
        return {"ok": False, "loi": ("Không tìm thấy old_string trong file. Kiểm tra lại từng ký tự "
                                     "(thụt lề, dấu nháy, khoảng trắng), hoặc đọc lại đúng đoạn đó bằng "
                                     "javis_read_file với offset rồi chép nguyên văn."
                                     + (f"\n{goi_y}" if goi_y else ""))}
    # old_string nằm trọn trong new_string và new_string đã có trong file ở đúng các chỗ đó: đây
    # là sửa đã áp rồi (ví dụ thêm một dòng sau một dòng có sẵn). Áp lại là nhân đôi dòng thêm.
    if ten == "exact" and old in new:
        new_spans = _khop_chinh_xac(content, new)
        if new_spans and all(any(a <= s and e <= b for a, b in new_spans) for s, e in spans):
            return {"ok": True, "content": content, "so_cho": 0, "chien_luoc": "", "khong_doi": True}
    if len(spans) > 1 and not replace_all:
        vi_tri = "\n".join(
            f"  L{_dong_cua(content, s)}: {content[s:e].split(chr(10))[0].strip()[:120]}"
            for s, e in spans[:5])
        return {"ok": False, "loi": (f"old_string khớp {len(spans)} chỗ nên không biết sửa chỗ nào. "
                                     f"Thêm vài dòng xung quanh vào old_string cho nó chỉ khớp một chỗ, "
                                     f"hoặc truyền replace_all=true nếu muốn sửa tất cả.\n{vi_tri}")}
    out, cuoi = [], 0
    for s, e in spans:
        out.append(content[cuoi:s])
        thay = new if ten == "exact" else _can_le(new, old, content[s:e])
        out.append(thay)
        cuoi = e
    out.append(content[cuoi:])
    return {"ok": True, "content": "".join(out), "so_cho": len(spans), "chien_luoc": ten,
            "khong_doi": False}


def diff_ngan(truoc: str, sau: str, ten: str, tran: int = 4000) -> str:
    d = "".join(difflib.unified_diff(truoc.splitlines(True), sau.splitlines(True),
                                     fromfile=f"a/{ten}", tofile=f"b/{ten}", n=2))
    if len(d) > tran:
        d = d[:tran] + f"\n… [diff dài {len(d):,} ký tự, đã cắt]"
    return d


# ---------------------------------------------------------------------------------------
# Kiểm lỗi sau khi sửa
# ---------------------------------------------------------------------------------------
def _loi_cu_phap(duoi: str, text: str, ten: str) -> Optional[str]:
    """Lỗi cú pháp của `text` theo loại file, hoặc None. Chỉ các loại kiểm được trong tiến trình."""
    try:
        if duoi == ".py":
            ast.parse(text, filename=ten)
        elif duoi == ".json":
            json.loads(text)
        elif duoi == ".toml":
            try:
                import tomllib
            except ImportError:          # Python < 3.11
                return None
            tomllib.loads(text)
        elif duoi in (".yaml", ".yml"):
            # Qua fastyaml như mọi chỗ khác trong server (bộ nạp C khi có). File nhiều tài liệu
            # (---) nạp hỏng cả trước lẫn sau khi sửa, nên kiem_loi_moi vẫn im với chúng.
            try:
                import fastyaml
            except ImportError:
                return None
            fastyaml.safe_load(text)
        else:
            return None
    except SyntaxError as e:
        return f"dòng {e.lineno}: {e.msg}"
    except Exception as e:
        return str(e).split("\n")[0][:300]
    return None


def _loi_node(text: str) -> Optional[str]:
    node = shutil.which("node")
    if not node:
        return None
    fd, tmp = tempfile.mkstemp(suffix=".js")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        r = subprocess.run([node, "--check", tmp], capture_output=True, text=True, timeout=15,
                           encoding="utf-8", errors="replace", creationflags=winproc.no_window())
        if r.returncode == 0:
            return None
        dong = [x for x in (r.stderr or "").splitlines() if x.strip() and tmp not in x]
        return (dong[0] if dong else "node --check báo lỗi")[:300]
    except Exception:
        return None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def kiem_loi_moi(p: Path, truoc: str, sau: str) -> str:
    """Câu cảnh báo nếu lần sửa này LÀM PHÁT SINH lỗi cú pháp, "" nếu không.

    Lỗi đã có từ trước thì im: báo lại lỗi người khác để sẵn là làm model đi sửa thứ không ai
    nhờ, và lạc mất việc chính.
    """
    duoi = p.suffix.lower()
    if duoi in (".js", ".mjs", ".cjs"):
        sau_loi = _loi_node(sau)
        if not sau_loi:
            return ""
        truoc_loi = _loi_node(truoc) if truoc else None
    else:
        sau_loi = _loi_cu_phap(duoi, sau, p.name)
        if not sau_loi:
            return ""
        truoc_loi = _loi_cu_phap(duoi, truoc, p.name) if truoc else None
    if truoc_loi:
        return ""
    return (f"\nCẢNH BÁO: sau lần sửa này file có lỗi cú pháp ({sau_loi}). Trước khi sửa thì "
            f"không có lỗi này, nên gần như chắc chắn do đoạn vừa thay. Sửa lại ngay.")


# ---------------------------------------------------------------------------------------
# Tìm trong code
# ---------------------------------------------------------------------------------------
# Thư mục không bao giờ đáng tìm: bản sao phụ thuộc, bộ đệm, lịch sử git. Tìm vào đó là ngập
# kết quả rác và tốn hàng chục giây trên một repo Node.
BO_QUA_THU_MUC = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache",
                  ".pytest_cache", ".ruff_cache", ".tox", ".idea", ".next", ".nuxt", ".cache",
                  ".gradle", "target", ".worktrees"}
_FILE_TOI_DA_BYTE = 2_000_000
TIM_MAC_DINH = 50
TIM_TOI_DA = 500


def _la_nhi_phan(p: Path) -> bool:
    try:
        with open(p, "rb") as f:
            return b"\0" in f.read(8192)
    except OSError:
        return True


def _duyet(goc: Path):
    for thu_muc, con, files in os.walk(goc):
        con[:] = sorted(c for c in con if c not in BO_QUA_THU_MUC)
        for f in sorted(files):
            yield Path(thu_muc) / f


def _khop_glob(rel: str, glob: str) -> bool:
    if not glob:
        return True
    import fnmatch
    ten = rel.rsplit("/", 1)[-1]
    return fnmatch.fnmatch(ten, glob) or fnmatch.fnmatch(rel, glob)


def _bieu_thuc(pattern: str):
    try:
        return re.compile(pattern)
    except re.error:
        return re.compile(re.escape(pattern))


def _tim_rg(rg: str, goc: Path, pattern: str, target: str, glob: str, context: int,
            hien_thi: Path) -> Optional[List[str]]:
    """Tìm bằng ripgrep, chạy TỪ `hien_thi` để rg tự in đường dẫn tương đối. None nếu rg lỗi
    (để rơi về bản Python)."""
    try:
        dich = os.path.relpath(goc, hien_thi)
    except ValueError:            # khác ổ đĩa trên Windows
        dich = str(goc)
    # rg chỉ tự bỏ node_modules khi thư mục là repo git có .gitignore; thư mục thường thì không.
    # Nên luôn loại tường minh đúng danh sách bản Python dùng, cho hai đường cùng một kết quả.
    loai = [x for d in sorted(BO_QUA_THU_MUC) for x in ("--glob", f"!{d}")]
    if target == "files":
        cmd = [rg, "--files", "--hidden"] + loai
    else:
        cmd = [rg, "--line-number", "--no-heading", "--color", "never", "--hidden",
               "--max-filesize", "2M"] + loai
        if context:
            cmd += ["-C", str(context)]
        if glob:
            cmd += ["--glob", glob]
        cmd += ["-e", pattern]
    # LUÔN truyền đường dẫn, kể cả ".": không có đường dẫn mà stdin không phải terminal thì rg
    # đọc STDIN thay vì thư mục, và trả "không tìm thấy" một cách rất thuyết phục.
    cmd += ["--", dich or "."]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, encoding="utf-8",
                           errors="replace", cwd=str(hien_thi), stdin=subprocess.DEVNULL,
                           creationflags=winproc.no_window())
    except Exception:
        return None
    if r.returncode not in (0, 1):
        # Mẫu regex mà rg không hiểu: thử lại như chữ thường một lần.
        if target != "files" and "regex" in (r.stderr or "").lower() and pattern != re.escape(pattern):
            return _tim_rg(rg, goc, re.escape(pattern), target, glob, context, hien_thi)
        return None
    ra = []
    for x in (r.stdout or "").splitlines():
        if not x:
            continue
        if x.startswith("./"):
            x = x[2:]
        if os.sep == "\\":
            dau, sep, duoi = x.partition(":") if target != "files" else (x, "", "")
            x = dau.replace("\\", "/") + sep + duoi
        ra.append(x)
    if target == "files":
        if any(c in pattern for c in "*?["):
            ra = [x for x in ra if _khop_glob(x, pattern)]
        else:
            bt = _bieu_thuc(pattern)
            ra = [x for x in ra if bt.search(x)]
        if glob:
            ra = [x for x in ra if _khop_glob(x, glob)]
    return ra


def tim(goc: Path, pattern: str, target: str = "content", file_glob: str = "", limit: int = TIM_MAC_DINH,
        offset: int = 0, context: int = 0, hien_thi: Optional[Path] = None, dung_rg: bool = True) -> str:
    """Tìm theo nội dung (`content`) hoặc theo tên file (`files`). Trả chữ cho model đọc.

    `hien_thi`: gốc để in đường dẫn tương đối (đường dẫn model dùng lại được với tool khác).
    """
    pattern = str(pattern or "")
    if not pattern:
        return "ERROR: thiếu pattern."
    target = "files" if str(target or "").lower() in ("files", "file", "ten", "name") else "content"
    try:
        limit = max(1, min(int(limit or TIM_MAC_DINH), TIM_TOI_DA))
    except (TypeError, ValueError):
        limit = TIM_MAC_DINH
    try:
        offset = max(0, int(offset or 0))
    except (TypeError, ValueError):
        offset = 0
    try:
        context = max(0, min(int(context or 0), 10))
    except (TypeError, ValueError):
        context = 0
    goc = Path(goc)
    hien_thi = Path(hien_thi or goc)
    if goc.is_file():
        files_goc = [goc]
    elif goc.is_dir():
        files_goc = None
    else:
        return f"ERROR: không có thư mục hay file '{goc.name}'."

    ket_qua: Optional[List[str]] = None
    rg = shutil.which("rg") if dung_rg else None
    if rg and files_goc is None:
        ket_qua = _tim_rg(rg, goc, pattern, target, file_glob, context, hien_thi)

    if ket_qua is None:
        ket_qua = []
        bt = _bieu_thuc(pattern)
        nguon = files_goc if files_goc is not None else _duyet(goc)
        can = offset + limit + 1
        for f in nguon:
            try:
                rel = os.path.relpath(f, hien_thi).replace("\\", "/")
            except ValueError:
                rel = str(f)
            if target == "files":
                if (_khop_glob(rel, pattern) if any(c in pattern for c in "*?[") else bt.search(rel)) \
                        and _khop_glob(rel, file_glob):
                    ket_qua.append(rel)
            else:
                if not _khop_glob(rel, file_glob):
                    continue
                try:
                    if f.stat().st_size > _FILE_TOI_DA_BYTE or _la_nhi_phan(f):
                        continue
                    lines = f.read_text(encoding="utf-8", errors="replace").split("\n")
                except OSError:
                    continue
                for i, x in enumerate(lines):
                    if bt.search(x):
                        if context:
                            a, b = max(0, i - context), min(len(lines), i + context + 1)
                            for j in range(a, b):
                                dau = ":" if j == i else "-"
                                ket_qua.append(f"{rel}{dau}{j + 1}{dau}{lines[j][:300]}")
                            ket_qua.append("--")
                        else:
                            ket_qua.append(f"{rel}:{i + 1}:{x[:300]}")
            if len(ket_qua) >= can * (2 * context + 2 if context else 1):
                break

    tong = len(ket_qua)
    trang = ket_qua[offset:offset + limit]
    if not trang:
        return "(không tìm thấy gì)" if offset == 0 else f"(hết kết quả, chỉ có {tong} dòng)"
    out = "\n".join(x[:400] for x in trang)
    if tong > offset + limit:
        out += f"\n… [còn kết quả. Xem tiếp: offset={offset + limit}]"
    return out


# ---------------------------------------------------------------------------------------
# Một lần sửa trọn vẹn: đọc, tính, ghi, báo
# ---------------------------------------------------------------------------------------
def sua_file(p: Path, old: str, new: str, replace_all: bool = False, sid: str = "",
             ten_hien_thi: str = "") -> str:
    """Áp một lần sửa lên `p` (đường dẫn đã duyệt). Trả chữ cho model đọc, không ném."""
    p = Path(p)
    ten = ten_hien_thi or p.name
    if not p.is_file():
        return (f"ERROR: không có file '{ten}'. Tạo file mới thì dùng javis_write_file, "
                f"javis_edit_file chỉ sửa file đã có.")
    try:
        if p.stat().st_size > 5_000_000:
            return f"ERROR: '{ten}' lớn hơn 5 MB, không sửa bằng tool này."
        truoc = p.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return f"ERROR: '{ten}' không phải file chữ UTF-8 nên không sửa được bằng tool này."
    except OSError as e:
        return f"ERROR: không đọc được '{ten}': {e}"
    # Giữ kiểu xuống dòng của file: model luôn gửi "\n", file Windows dùng "\r\n".
    crlf = "\r\n" in truoc
    lam_viec = truoc.replace("\r\n", "\n") if crlf else truoc
    kq = thay_the(lam_viec, str(old or "").replace("\r\n", "\n"), str(new or "").replace("\r\n", "\n"),
                  bool(replace_all))
    if not kq["ok"]:
        n = _dem_hong(sid, p, True)
        them = ("\nĐã hỏng 3 lần liên tiếp trên file này: đọc lại file (javis_read_file) rồi chép "
                "old_string NGUYÊN VĂN từ output đó." if n >= 3 else "")
        return f"ERROR: {kq['loi']}{them}"
    _dem_hong(sid, p, False)
    if kq.get("khong_doi"):
        return f"'{ten}' đã có sẵn nội dung này (lần sửa đã áp từ trước), không ghi gì thêm."
    sau = kq["content"]
    ghi = sau.replace("\n", "\r\n") if crlf else sau
    try:
        tmp = p.with_name(f".{p.name}.javis-{os.getpid()}-{int(time.time() * 1000)}.tmp")
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(ghi)
        try:
            os.chmod(tmp, p.stat().st_mode)
        except OSError:
            pass
        os.replace(tmp, p)
    except OSError as e:
        try:
            tmp.unlink()
        except Exception:
            pass
        return f"ERROR: không ghi được '{ten}': {e}"
    ghi_nhan_ghi(sid, p)
    out = [f"Đã sửa '{ten}': {kq['so_cho']} chỗ."]
    if kq["chien_luoc"] != "exact":
        out.append(f"(Khớp kiểu '{kq['chien_luoc']}', không phải khớp nguyên văn"
                   + (": XEM KỸ diff dưới đây, chỗ được sửa là chỗ GIỐNG NHẤT chứ không phải chắc chắn "
                      "đúng chỗ." if kq["chien_luoc"] in TUONG_TU else ".") + ")")
    out.append(diff_ngan(lam_viec, sau, ten))
    canh_bao = kiem_loi_moi(p, lam_viec, sau)
    if canh_bao:
        out.append(canh_bao)
    return "\n".join(x for x in out if x)
