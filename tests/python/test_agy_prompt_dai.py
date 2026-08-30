"""Chat DÀI bằng tiếng Việt qua Antigravity CLI không được nổ "Argument list too long".

    python tests/run.py agy_prompt_dai      (KHÔNG mạng, không cần cài agy)

Người dùng báo 2026-08-30, kèm ảnh: hội thoại 33 tin bằng tiếng Việt, và Javis trả về hai
bong bóng đỏ

    OSError: [Errno 7] Argument list too long: '/opt/javis/agy'

rồi "(không có nội dung trả về)". Chat ngắn thì bình thường, nên nó trông như ngẫu nhiên.

Hai lỗi chồng nhau, và cái thứ nhất giải thích vì sao chỉ tiếng Việt mới dính:

1. `_chon_duong` đo prompt bằng `len()` = số KÝ TỰ Unicode, còn nhân Linux áp
   MAX_ARG_STRLEN (131.072) theo BYTE của chuỗi UTF-8. Tiếng Việt tốn ~1.3 byte mỗi ký tự,
   nên prompt 120.000 ký tự tiếng Việt là ~156.000 byte: vượt trần thật mà phép đo vẫn kết
   luận "vừa argv". Cùng độ dài đó bằng tiếng Anh thì 120.000 byte, lọt - đúng cái làm lỗi
   trông như ngẫu nhiên.

2. Không có lưới an toàn. E2BIG nổ ở `Popen` bị gói thành chuỗi `OSError: ...` rồi bắn thẳng
   ra người dùng - một câu họ không sửa được gì, và lượt chat mất trắng, dù Javis có sẵn hai
   đường không trần (stdin, file ngữ cảnh) nằm ngay đó.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import errno
import json
import os
import stat
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-agydai-"))

import antigravity_cli as A  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name
          + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def chay(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ============================================================
# 1. Đo độ dài theo ĐÚNG đơn vị hệ điều hành đếm
# ============================================================
_VI = "Đọc và trích xuất bài viết từ URL này giúp mình nhé. "
_EN = "Please read and extract the article from this URL for me. "

check("tiếng Anh: byte == ký tự (ASCII)", A._do_dai_argv(_EN) == len(_EN))
check(f"tiếng Việt: byte > ký tự ({A._do_dai_argv(_VI)} > {len(_VI)})",
      A._do_dai_argv(_VI) > len(_VI))
# Đây là con số làm nên cả cái bug: đo bằng len() thì 120k ký tự tiếng Việt "vừa" trần 120k.
# Cỡ khối chọn có tính: 100.700 KÝ TỰ (lọt trần 120.000 nếu đo bằng len - đúng cái bẫy của
# code cũ) nhưng 131.000 BYTE (vượt trần thật). Đây chính là khe mà hội thoại tiếng Việt rơi vào.
_khoi_vi = _VI * 1900            # ~100.700 ký tự
check(f"CANARY: khối tiếng Việt {len(_khoi_vi):,} ký tự (LỌT trần nếu đếm ký tự) "
      f"= {A._do_dai_argv(_khoi_vi):,} byte (VƯỢT trần {A._tran_argv():,})",
      len(_khoi_vi) < A._tran_argv() < A._do_dai_argv(_khoi_vi))


# ============================================================
# 2. _chon_duong: prompt tiếng Việt dài phải BỎ đường argv
# ============================================================
_HELP = ("Usage: agy [OPTIONS]\n  -p, --print <PROMPT>\n  --model <M>\n"
         "  --output-format <F>\n  --conversation <ID>\n")


def _gia_agy(dong_ra, ma=0):
    """`agy` giả: ghi lại argv/stdin nhận được rồi in ra dòng sự kiện đã khai."""
    d = Path(tempfile.mkdtemp(prefix="javis-fakeagy-dai-"))
    p = d / "agy"
    p.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "a = sys.argv[1:]\n"
        f"if '--help' in a:\n    sys.stdout.write({_HELP!r}); sys.exit(0)\n"
        "try:\n    _sd = sys.stdin.read()\nexcept Exception:\n    _sd = ''\n"
        f"open({str(d / 'argv.txt')!r}, 'w').write('\\x00'.join(a))\n"
        f"open({str(d / 'stdin.txt')!r}, 'w').write(_sd or '')\n"
        f"for l in {json.dumps(dong_ra)}:\n    print(l, flush=True)\n"
        f"sys.exit({ma})\n",
        encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(p), d


_DONG = [json.dumps({"event": "result", "result": {"status": "SUCCESS",
                                                   "response": "Xong rồi nhé."}})]

_cli, _d = _gia_agy(_DONG)
_that_find = A.find_antigravity_cli
A.find_antigravity_cli = lambda: _cli
A._HELP_CACHE.update(path=_cli, text=_HELP, ts=float("inf"))
# Đo stdin tốn một lượt gọi model thật -> nhớ sẵn kết quả để test không phải chạy đo.
A._ghi_nho_duong({"chu_ky": A._chu_ky_cli(_cli), "duong": "stdin:trong",
                  "vi_sao": "test", "ts": __import__("time").time()})

try:
    g = A.AntigravityCLI(cwd=str(_d), tag="test")
    check("prompt NGẮN vẫn đi argv (đường trung thực nhất, không đổi hành vi cũ)",
          g._chon_duong("chào em") == "argv")
    _duong_dai = g._chon_duong(_khoi_vi)
    check(f"prompt DÀI tiếng Việt KHÔNG đi argv nữa (chọn: {_duong_dai})",
          _duong_dai != "argv", _duong_dai)
    check("và đường thay thế là stdin hoặc file (hai đường không có trần)",
          _duong_dai.startswith("stdin") or _duong_dai == "file", _duong_dai)

    # Ngưỡng phải nằm ĐÚNG chỗ: cùng số ký tự đó bằng tiếng Anh thì vẫn lọt argv - chứng minh
    # phép đo bám vào byte thật chứ không phải vừa siết bừa cho qua test.
    _khoi_en = "x" * len(_khoi_vi)
    check(f"cùng {len(_khoi_en):,} ký tự nhưng ASCII thì vẫn vừa argv (không siết bừa)",
          g._chon_duong(_khoi_en) == "argv")
finally:
    A.find_antigravity_cli = _that_find


# ============================================================
# 3. LƯỚI AN TOÀN: E2BIG vẫn nổ thì tự đổi đường, KHÔNG bắn lỗi thô
# ============================================================
# Phép đo ở mục 2 có thể vẫn hụt trong đời thật: ARG_MAX là trần CHUNG cho argv + biến môi
# trường, nên một máy có env to vẫn nổ dù prompt lọt MAX_ARG_STRLEN. Đây là lưới cuối.
_cli2, _d2 = _gia_agy(_DONG)
_that_popen = A.subprocess.Popen
_lan = {"n": 0}


def _popen_e2big(args, **kw):
    """Lần đầu (prompt trong argv) ném E2BIG y như nhân Linux; lần sau chạy thật."""
    _lan["n"] += 1
    if _lan["n"] == 1:
        raise OSError(errno.E2BIG, "Argument list too long", args[0])
    return _that_popen(args, **kw)


try:
    A.find_antigravity_cli = lambda: _cli2
    A._HELP_CACHE.update(path=_cli2, text=_HELP, ts=float("inf"))
    A._ghi_nho_duong({"chu_ky": A._chu_ky_cli(_cli2), "duong": "stdin:trong",
                      "vi_sao": "test", "ts": __import__("time").time()})
    A.subprocess.Popen = _popen_e2big

    g2 = A.AntigravityCLI(cwd=str(_d2), tag="test")

    async def _thu():
        ra = []
        async for ev in g2.query("chào em"):
            ra.append(ev)
        return ra

    evs = chay(_thu())
    loi = [e for e in evs if e.get("type") == "error"]
    cuoi = [e for e in evs if e.get("type") == "final"]

    check(f"đã chạy lại lượt hai sau khi E2BIG (đếm được {_lan['n']} lần gọi)", _lan["n"] == 2)
    check("KHÔNG bắn 'Argument list too long' ra người dùng",
          not any("Argument list too long" in str(e.get("content", "")) for e in loi),
          [e.get("content") for e in loi])
    check("KHÔNG bắn chuỗi OSError thô ra người dùng",
          not any("OSError" in str(e.get("content", "")) for e in loi),
          [e.get("content") for e in loi])
    check("và người dùng vẫn NHẬN ĐƯỢC câu trả lời (không mất trắng lượt chat)",
          any("Xong rồi nhé" in str(e.get("content", "")) for e in cuoi),
          [e.get("content") for e in cuoi])
finally:
    A.subprocess.Popen = _that_popen
    A.find_antigravity_cli = _that_find


# ============================================================
# 4. CANARY nguồn: đừng ai đổi lại len() trong phép đo trần
# ============================================================
_src = Path(SERVER, "antigravity_cli.py").read_text(encoding="utf-8")
_cd = _src.split("def _chon_duong", 1)[1].split("\n    async def", 1)[0]
check("CANARY: _chon_duong đo bằng _do_dai_argv, không phải len()",
      "_do_dai_argv(full)" in _cd and "len(full)" not in _cd)
check("CANARY: lượt argv được giữ lỗi lại để còn đường lùi",
      'giu_loi=(duong != "file")' in _src)
check("CANARY: có nhánh chạy lại khi vượt trần argv",
      'ket.get("qua_tran_argv")' in _src)

print()
if _fails:
    print(f"FAIL {len(_fails)}: " + "; ".join(_fails))
    raise SystemExit(1)
print("TẤT CẢ PASS")
