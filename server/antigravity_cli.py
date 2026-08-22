"""Bộ não thứ 10: Antigravity CLI (binary `agy`) - bản thay thế chính chủ của Gemini CLI.

**Vì sao có file này.** Ngày 18/06/2026 Google ngừng phục vụ Gemini CLI cho mọi tài khoản cá
nhân (miễn phí, AI Pro, Ultra) với mã `UNSUPPORTED_CLIENT`, và chỉ sang Antigravity. Đường đi
qua `gemini` vẫn giữ trong repo cho ai có giấy phép doanh nghiệp hoặc chạy bằng API key, còn
người dùng cá nhân muốn xài gói Google của mình thì phải qua đây.

Cái được, so với Gemini CLI: `agy` cho chọn ĐÚNG những model hiện trong trình chọn của
Antigravity IDE - gồm cả model không phải của Google (Claude). Nên "đổi model như Antigravity"
làm được thật, không phải hứa.

**KỶ LUẬT CỦA FILE NÀY: ĐO, KHÔNG ĐOÁN.**

`gemini_cli.py` viết được chắc tay vì tác giả có binary trong tay và đọc `--help` thật. Ở đây
KHÔNG có: máy dựng bản này bị chặn mạng nên không tải được `agy`, mà cờ dòng lệnh thì mỗi bản
một khác (xem CHANGELOG của chính nó: `--model` có từ 1.0.5, slug ổn định từ 1.1.5,
`--output-format` cho print mode từ 1.1.8, cho `models`/`agents` từ 1.1.12). Đoán cờ rồi ship
là đúng kiểu sai mà file kia đã cố tránh.

Nên file này KHÔNG cứng hoá gì cả. Nó:

- đọc `agy --help` MỘT LẦN rồi nhớ, và chỉ truyền những cờ mà chính binary trên máy khai;
- lấy danh sách model bằng `agy models`, không giữ bảng model chép tay (bảng chép tay là thứ
  hỏng ngay lần Google đổi tên model, mà họ đổi liên tục);
- ánh xạ sự kiện stream-json theo NHIỀU hình dạng, và cuối cùng luôn có lưới an toàn: dòng nào
  không hiểu thì giữ nguyên làm chữ, chứ tuyệt đối không im lặng trả bong bóng rỗng - đó đúng
  là triệu chứng khiến chủ repo mất buổi tối với Gemini CLI.

Chỗ nào chưa đo được thì ghi thẳng "CHƯA ĐO" trong chú thích thay vì làm ra vẻ chắc chắn.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import AsyncIterator, Optional

from claude_cli import _home_dir, _no_window, tim_binary

# Model mặc định khi người dùng chưa chọn gì. KHÔNG phải bảng model: chỉ là hạt giống để lượt
# đầu chạy được nếu `agy models` chưa kịp trả lời. Danh sách thật luôn lấy từ CLI.
MODEL_MAC_DINH = ""     # rỗng = không truyền --model, để CLI dùng model nó đang đặt

# Lệnh cài chính chủ, hiện nguyên văn cho người dùng chép.
LENH_CAI = {
    "linux": "curl -fsSL https://antigravity.google/cli/install.sh | bash",
    "mac": "curl -fsSL https://antigravity.google/cli/install.sh | bash",
    "windows": "irm https://antigravity.google/cli/install.ps1 | iex",
}


def lenh_cai() -> str:
    return LENH_CAI["windows"] if os.name == "nt" else LENH_CAI["linux"]


def find_antigravity_cli() -> Optional[str]:
    """Tìm binary `agy`. Cửa thoát JAVIS_AGY_BIN cho máy cài chỗ lạ.

    Trình cài chính chủ thả vào `~/.local/bin/agy`, mà thư mục đó KHÔNG chắc nằm trong PATH của
    tiến trình Javis - dịch vụ systemd và app trên macOS đều được cấp một PATH rất ngắn. Nên
    phải soi tay chỗ đó thay vì tin mỗi `which`.
    """
    envp = (os.environ.get("JAVIS_AGY_BIN") or "").strip()
    if envp:
        try:
            if Path(envp).exists():
                return envp
        except Exception:
            pass
    cli = tim_binary("agy")
    if cli:
        return cli
    home = _home_dir()
    ung_vien = [
        home / ".local" / "bin" / "agy",
        home / ".antigravity" / "bin" / "agy",
        Path("/usr/local/bin/agy"),
        Path("/opt/homebrew/bin/agy"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "antigravity" / "agy.exe",
        Path(os.environ.get("APPDATA", "")) / "npm" / "agy.cmd",
    ]
    for p in ung_vien:
        try:
            if p.exists():
                return str(p)
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Dò năng lực của binary đang cài (thay cho việc đoán cờ)
# ---------------------------------------------------------------------------
_HELP_CACHE: dict = {"path": None, "text": "", "ts": 0.0}
_HELP_TTL = 300.0     # 5 phút: đủ để một phiên chat không đẻ tiến trình mỗi lượt, mà nâng cấp
                      # bản CLI xong cũng không phải khởi động lại Javis mới nhận cờ mới.


def _help_text() -> str:
    """Nội dung `agy --help`, nhớ trong RAM. Rỗng nếu không chạy được."""
    cli = find_antigravity_cli()
    if not cli:
        return ""
    now = time.time()
    if (_HELP_CACHE["path"] == cli and _HELP_CACHE["text"]
            and now - _HELP_CACHE["ts"] < _HELP_TTL):
        return _HELP_CACHE["text"]
    try:
        r = subprocess.run([cli, "--help"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=20, creationflags=_no_window())
        txt = (r.stdout or "") + "\n" + (r.stderr or "")
    except Exception:
        txt = ""
    _HELP_CACHE.update(path=cli, text=txt, ts=now)
    return txt


def co_co(*ten_co: str) -> bool:
    """Binary trên máy CÓ khai cờ này không (`--help` nhắc tới nó).

    Truyền một cờ mà bản CLI chưa có là nó thoát ngay với "unknown flag" - hỏng cả lượt chat
    chỉ vì một tuỳ chọn phụ. Hỏi trước rồi mới truyền thì bản cũ vẫn chạy, chỉ mất tính năng.
    """
    txt = _help_text()
    if not txt:
        return False
    return any(c in txt for c in ten_co)


def nhan_prompt_qua_stdin() -> bool:
    """`--help` của bản này có TỰ KHAI là đọc prompt từ stdin không.

    ĐỌC KỸ TRƯỚC KHI DÙNG LẠI HÀM NÀY. Nó từng là chốt chặn quyết định đường đi của prompt, và
    đó là một bug im lặng suốt 0.30.0-0.32.2: `agy --help` KHÔNG hề có chữ "stdin" ở bất kỳ bản
    nào (đã đối chiếu hai bản dump help thật), nên hàm này trả False trên mọi máy, mọi phiên
    bản, vĩnh viễn. Nhánh stdin trong `query()` chưa từng chạy một lần nào, mọi lượt rơi hết
    xuống argv rồi đâm vào trần dòng lệnh của Windows.

    Sự thật, theo CHANGELOG CHÍNH CHỦ của `agy` (nguồn cấp 1, không phải suy đoán):
    - 1.1.1: "Fixed `agy -p` hanging when run inside a shell script or subprocess by no longer
      reading stdin when a prompt is provided via a flag."
    - 1.1.2: "... when stdin is consumed by a piped prompt."
    Tức `agy` ĐỌC stdin, với đúng một điều kiện: prompt KHÔNG được cấp qua cờ. Truyền
    `--print ""` (giá trị RỖNG) rồi bơm prompt qua stdin là công thức đúng - `_build_args()` đã
    làm sẵn như vậy từ đầu.

    Vì sao nhiều người đo ra "không nhận stdin": `agy` dùng Go stdlib `flag`, ở đó `--print` là
    cờ chuỗi, nên gõ `agy -p` trần rồi pipe vào sẽ thoát ngay với "flag needs an argument: -p".
    Đo trúng câu lỗi đó rồi kết luận nhầm là CLI không hỗ trợ stdin.

    Nay hàm này chỉ còn là một GỢI Ý cộng thêm, không phải chốt chặn: bản nào tự khai stdin thì
    khỏi cần lưới an toàn ở `query()` nữa.
    """
    txt = (_help_text() or "").lower()
    return "stdin" in txt


def phien_moi() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Prompt DÀI: trần dòng lệnh của hệ điều hành, và đường vòng khi argv không đủ chỗ
# ---------------------------------------------------------------------------
# ĐO ngày 2026-08-13, và con số này đảo ngược cả cách hiểu vấn đề: system prompt của Javis trên
# một brain TRỐNG (chưa ký ức, chưa lịch sử) đã là 36.045 ký tự - riêng CLAUDE.md 27.172, cộng
# lớp agentic, chỉ mục năng lực, router skill và khối kênh. Windows chặn TỔNG dòng lệnh của tiến
# trình con ở 32767 (CreateProcess), nên trên Windows đường argv KHÔNG BAO GIỜ đủ chỗ, kể cả khi
# người dùng chỉ gõ "hi em".
#
# Bản 0.31.0 đọc nhầm triệu chứng thành "hội thoại quá dài" rồi dựng một câu báo lỗi khuyên mở
# hội thoại mới. Mở bao nhiêu hội thoại mới cũng vẫn dính, vì phần vượt trần là phần CỐ ĐỊNH.
# Tức bộ não này chết hẳn trên Windows suốt từ đó, mà lời báo lỗi lại chỉ sai hướng.
#
# Linux/macOS không có trần tổng, nhưng có trần cho MỘT tham số: MAX_ARG_STRLEN = 32 trang = 128KB.
# Hội thoại thật sự dài vẫn chạm được, nên chừa luôn.
def _tran_argv() -> int:
    """Quá bao nhiêu ký tự thì phải bỏ đường argv. Đọc `os.name` lúc gọi, không phải lúc import."""
    if os.name == "nt":
        return 30000        # trần thật 32767, chừa chỗ cho đường dẫn binary và các cờ
    return 120000           # Linux: MAX_ARG_STRLEN 131072 cho MỘT tham số


_NHO_DUONG = "antigravity-duong-prompt.json"
_HAN_NHO_AM = 86400.0     # "stdin không ăn" chỉ nhớ 24 giờ, xem `duong_prompt_dai`


def _tep_nho_duong() -> Path:
    """File nhớ đường gửi prompt đã đo được. Nhớ ra ĐĨA vì kết quả đo tốn một lượt gọi model."""
    try:
        import config
        base = Path(config.STATE_DIR)
    except Exception:
        base = Path(os.environ.get("JAVIS_STATE_DIR") or Path(__file__).parent)
    return base / _NHO_DUONG


def _chu_ky_cli(cli: str) -> str:
    """Vân tay của binary. Nâng cấp `agy` là chữ ký đổi -> tự đo lại thay vì tin bản nhớ cũ."""
    try:
        st = os.stat(cli)
        return f"{cli}|{int(st.st_mtime)}|{st.st_size}"
    except Exception:
        return cli or ""


def _doc_nho_duong() -> dict:
    try:
        return json.loads(_tep_nho_duong().read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _ghi_nho_duong(d: dict):
    try:
        p = _tep_nho_duong()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[antigravity duong prompt] {e}", file=sys.stderr)


# Ba công thức bơm prompt qua stdin, và không công thức nào chắc chắn đúng cho mọi bản `agy`.
# CHANGELOG 1.1.1 của Google nói nó đọc stdin "khi prompt không được cấp qua cờ", nhưng KHÔNG nói
# cú pháp. Ba cách hiểu câu đó, xếp theo mức sát nghĩa:
#   trong - không truyền `-p` gì cả, để CLI tự nhận ra stdin là ống dẫn chứ không phải bàn phím.
#   gach  - `-p -`, dấu gạch là quy ước "đọc stdin" của Unix (dpd-db dùng cách này với agy).
#   rong  - `-p ""`, cách agy2api dùng để chữa đúng lỗi WinError 206.
# Chủ repo ĐO trên máy Windows 2026-08-13: bản của họ CHỐI công thức `rong` bằng
# "Error: empty prompt. Usage: agy --print \"your prompt here\"" rồi thoát mã 1 - tức nó kiểm tra
# giá trị cờ TRƯỚC khi ngó tới stdin. Bài học không phải "đổi sang công thức khác" mà là: chuyện
# này không suy luận từ tài liệu được, phải hỏi thẳng binary trên máy đó. Nên thử lần lượt bằng
# một prompt tí hon có mã canary, cái nào vọng lại canary thì cái đó đúng.
_CT_STDIN = (("trong", []), ("gach", ["-p", "-"]), ("rong", ["-p", ""]))
_MA_CANARY = "JAVIS-STDIN-OK-7413"


def _do_stdin(cli: str, timeout: float = 75.0) -> str:
    """Hỏi thẳng binary: công thức stdin nào ăn. Trả tên công thức, hoặc "" nếu không cái nào.

    Công thức sai thường thoát ngay lập tức với một câu usage (không tốn lượt gọi model nào), nên
    phép đo này rẻ. Chỉ công thức ĐÚNG mới tốn đúng một lượt tí hon, và chỉ tốn một lần cho mỗi
    bản CLI vì kết quả nhớ ra đĩa.
    """
    for ten, co in _CT_STDIN:
        try:
            r = subprocess.run(
                [cli] + co,
                input=f"Trả lời đúng một dòng, chỉ gồm mã này, không thêm chữ nào: {_MA_CANARY}",
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=timeout, creationflags=_no_window())
        except Exception:
            continue
        if _MA_CANARY in ((r.stdout or "") + (r.stderr or "")):
            print(f"[antigravity] công thức stdin dùng được: {ten}", file=sys.stderr)
            return ten
    return ""


# Dấu hiệu "prompt không tới nơi" trong thứ CLI in ra. Nhận ra thì phải đổi đường ngay chứ không
# được đưa nguyên câu tiếng Anh cho người dùng rồi bỏ mặc - họ không sửa được gì với nó.
def _la_loi_thieu_prompt(loi: str) -> bool:
    l = (loi or "").lower()
    return (("empty prompt" in l) or ("no prompt" in l)
            or ("prompt" in l and ("usage:" in l or "required" in l or "missing" in l))
            or ("flag needs an argument" in l))


def duong_prompt_dai(cli: Optional[str] = None) -> str:
    """Prompt không nhét vừa argv thì đi đường nào: "stdin:<công thức>" hay "file".

    Ưu tiên stdin vì nó là đường TRUNG THỰC: prompt tới model nguyên vẹn, đúng thứ Javis gửi.
    Đường file phải nhờ chính model chịu mở file ra đọc, tức có xác suất trượt. Nhưng "ưu tiên"
    không có nghĩa là "mặc định tin": bản 0.33.1 mặc định stdin theo tài liệu và chủ repo lĩnh
    trọn "Error: empty prompt" ngay lượt đầu. Nên ở đây HỎI BINARY (xem `_do_stdin`), và chỉ khi
    không công thức nào ăn mới xuống đường file.

    Nhớ ra đĩa theo vân tay binary. Bất đối xứng có chủ ý: kết quả dương tính nhớ mãi, âm tính
    chỉ nhớ 24 giờ. Cửa thoát: JAVIS_AGY_PROMPT_DAI=stdin|file|argv.
    """
    ep = (os.environ.get("JAVIS_AGY_PROMPT_DAI") or "").strip().lower()
    if ep in ("file", "argv"):
        return ep
    if ep == "stdin":
        return "stdin:rong"
    cli = cli or find_antigravity_cli()
    if not cli:
        return "file"
    nho = _doc_nho_duong()
    if nho.get("chu_ky") == _chu_ky_cli(cli):
        duong = str(nho.get("duong") or "")
        if duong.startswith("stdin"):
            return duong        # dương tính: nhớ mãi, bằng chứng chắc chắn rồi
        # Kết quả ÂM TÍNH có hạn, kết quả dương tính thì không. Bất đối xứng này là cố ý: "stdin
        # chạy được" là bằng chứng chắc chắn, còn "không công thức nào ăn" có thể chỉ là một lúc
        # chưa đăng nhập, mạng lỗi, hay quota hết. Nhớ vĩnh viễn theo chiều âm là đóng đinh cả
        # máy vào đường kém trung thực hơn vì đúng một lượt xui, mà chữ ký binary chỉ đổi khi
        # nâng cấp `agy` nên không có gì gỡ ra được.
        if duong == "file" and time.time() - float(nho.get("ts") or 0) <= _HAN_NHO_AM:
            return "file"
    ten = _do_stdin(cli)
    duong = f"stdin:{ten}" if ten else "file"
    _ghi_nho_duong({"chu_ky": _chu_ky_cli(cli), "duong": duong,
                    "vi_sao": "đo bằng mã canary", "ts": time.time()})
    return duong


def nho_duong(cli: Optional[str], duong: str, vi_sao: str = ""):
    """Ghi lại đường đã dùng được cho đúng bản binary này."""
    cli = cli or find_antigravity_cli()
    if not cli:
        return
    _ghi_nho_duong({"chu_ky": _chu_ky_cli(cli), "duong": duong, "vi_sao": vi_sao,
                    "ts": time.time()})


_THU_MUC_NGU_CANH = ".javis-agy"
_HAN_NGU_CANH = 3600.0      # file mồ côi quá một giờ thì dọn


def _don_ngu_canh_cu(thu_muc: Path):
    """Xoá file ngữ cảnh mồ côi. Bình thường mỗi lượt tự dọn file của mình trong `finally`, nhưng
    `kill -9`, mất điện, hay restart container giữa lượt thì không có `finally` nào chạy - mà thứ
    nằm lại là bản sao ký ức của người dùng, không phải một file tạm vô hại."""
    try:
        gio = time.time()
        for f in thu_muc.glob("ngu-canh-*.md"):
            try:
                if gio - f.stat().st_mtime > _HAN_NGU_CANH:
                    f.unlink()
            except Exception:
                pass
    except Exception:
        pass


def _viet_file_ngu_canh(cwd: str, noi_dung: str) -> tuple[str, str]:
    """Ghi cả gói (system prompt + hội thoại + câu hỏi) ra file, trả (đường tuyệt đối, đường nhắc).

    Ghi vào STATE_DIR của Javis chứ KHÔNG vào brain, và đây là chỗ đã suýt sai một cách đắt giá.
    Đặt trong brain thì tiện hơn (agent luôn đọc được file trong cwd của nó), nhưng file này là
    bản sao của system prompt + MEMORY.md + toàn bộ lịch sử hội thoại, mà đường sao lưu git của
    brain (`git_brain._backup_skip`) chỉ chặn theo danh sách cố định rồi cho qua mọi file .md.
    Một lượt đồng bộ chạy trúng lúc `agy` đang chạy là nguyên gói đó được commit và push lên
    remote của người dùng, và git giữ blob vĩnh viễn. Ngay bên cạnh, `Memory/conversations/` bị
    chặn khỏi backup CÓ CHỦ ĐÍCH vì "có thể chứa secret" - đi vòng qua đúng cái rào đó bằng cửa
    sau thì không phải là đánh đổi, mà là lỗi.

    STATE_DIR cũng chữa luôn ca cwd không ghi được: đường fast path gọi engine này với
    `cwd = os.getcwd()`, tức `/app` trong Docker - thư mục của root trong khi tiến trình chạy
    bằng user `javis`.

    Đổi lại phải cho `agy` quyền đọc thư mục đó bằng `--add-dir`, việc của người gọi.
    """
    try:
        import config
        goc = Path(config.STATE_DIR)
    except Exception:
        goc = Path(os.environ.get("JAVIS_STATE_DIR") or Path(__file__).parent)
    thu_muc = goc / _THU_MUC_NGU_CANH
    thu_muc.mkdir(parents=True, exist_ok=True)
    _don_ngu_canh_cu(thu_muc)
    ten = f"ngu-canh-{uuid.uuid4().hex[:12]}.md"
    p = thu_muc / ten
    p.write_text(noi_dung, encoding="utf-8")
    try:
        os.chmod(p, 0o600)      # có thể chứa ký ức riêng của người dùng
    except Exception:
        pass
    # Nhắc bằng đường TUYỆT ĐỐI vì file không còn nằm trong cwd nữa.
    return str(p), str(p)


def _loi_nhac_file(duong_dan: str, cau_hoi: str) -> str:
    """Prompt NGẮN thay cho cả gói: bảo model tự mở file ngữ cảnh ra đọc.

    Câu hỏi thật vẫn được nhắc lại ở đây (cắt ngắn) chứ không chỉ nằm trong file. Đó là lưới an
    toàn: bản CLI nào bướng không chịu đọc file thì ít ra vẫn trả lời đúng câu người dùng hỏi,
    chỉ thiếu luật riêng của Javis, chứ không trả lời trống trơn.
    """
    hoi = (cau_hoi or "").strip()
    if len(hoi) > 1500:
        hoi = hoi[:1500] + " [...]"
    return (
        f"BẮT BUỘC LÀM TRƯỚC: mở và đọc HẾT file `{duong_dan}`.\n"
        "File đó chứa toàn bộ chỉ dẫn hệ thống, bộ nhớ và lịch sử hội thoại của bạn. Đọc xong "
        "thì hành xử đúng theo nó và trả lời tin nhắn mới nhất của người dùng (nằm ở cuối file). "
        "Không nhắc tới file này trong câu trả lời, không tóm tắt nó.\n"
        "Nếu KHÔNG mở được file (không có quyền, không tìm thấy), đừng im lặng và cũng đừng đoán: "
        "trả lời câu hỏi dưới đây rồi nói thẳng ở cuối là bạn không đọc được file ngữ cảnh.\n"
        "(Phải đi qua file vì hệ điều hành chặn độ dài dòng lệnh, không nhét thẳng vào đây được.)\n\n"
        f"Tin nhắn mới nhất của người dùng:\n{hoi}"
    )


_CANH_BAO_CHUA_DOC = (
    "\n\n_(Lưu ý của Javis: bản `agy` trên máy này không mở file ngữ cảnh, nên lượt vừa rồi trả "
    "lời mà chưa có system prompt và bộ nhớ của Javis. Muốn chuẩn thì nâng cấp `agy` lên bản mới "
    "(nhận prompt qua stdin), hoặc đổi bộ não khác ở trang Models.)_"
)
# Bơm stdin theo mẩu bao nhiêu byte. 4096 là kích thước một trang ống dẫn: đủ nhỏ để bên đọc
# nhận từng mẩu rời, đủ lớn để không tốn hàng chục nghìn lời gọi ghi.
_MAU_STDIN = 4096


def _ghi_stdin(proc, s: str) -> None:
    """Bơm prompt vào stdin, KHÔNG BAO GIỜ cắt giữa một ký tự UTF-8.

    Vì sao phải cẩn thận tới mức này (chủ repo báo 2026-08-13, kèm ảnh): chat qua Antigravity
    trên Windows ra chữ hỏng kiểu "gm", "hn", "tng" - mỗi ký tự tiếng Việt 3 byte
    biến thành đúng 3 dấu hỏi kim cương (U+FFFD). Đó là chữ ký của một bên đọc gọi
    `buffer.toString("utf8")` trên TỪNG MẨU ống dẫn thay vì dùng bộ giải mã tăng dần: mẩu nào
    kết thúc giữa một ký tự thì mấy byte lẻ thành U+FFFD hết.

    ĐÃ ĐO trên máy này: lớp đọc của Javis KHÔNG dính lỗi đó (test `_gia` cắt byte giữa ký tự,
    chữ vẫn ghép lại nguyên vẹn - `io.TextIOWrapper` dùng bộ giải mã tăng dần đúng chuẩn). Và
    các chữ hỏng chủ repo gửi ("gồm", "hạn", "từng", "đồng bộ") đều là từ trong system prompt
    của Javis, tức chúng hỏng trên đường VÀO chứ không phải đường ra. Nên bên cắt nhầm là bộ
    đọc stdin của `agy`.

    Javis không sửa được `agy`, nhưng chỉnh được chỗ mình ĐẶT ranh giới: ghi từng mẩu kết thúc
    đúng biên ký tự rồi flush. Bên kia đọc bao nhiêu mẩu cũng được, ranh giới nào cũng rơi vào
    giữa hai ký tự trọn vẹn. Ghi thẳng dạng BYTE còn tránh luôn chuyện `\\n` bị dịch thành
    `\\r\\n` trên Windows (chế độ text làm vậy) - prompt tới nơi đúng nguyên văn.
    """
    b = s.encode("utf-8")
    f = getattr(proc.stdin, "buffer", None) or proc.stdin
    nhi_phan = f is not proc.stdin or "b" in getattr(proc.stdin, "mode", "")
    i = 0
    while i < len(b):
        j = min(i + _MAU_STDIN, len(b))
        # Lùi về biên ký tự: byte 10xxxxxx là byte NỐI, không được đứng đầu một mẩu.
        while j < len(b) and (b[j] & 0xC0) == 0x80:
            j -= 1
        mau = b[i:j]
        f.write(mau if nhi_phan else mau.decode("utf-8"))
        try:
            f.flush()
        except Exception:
            pass
        i = j


_CANH_BAO_HONG_DAU = (
    "\n\n_(Lưu ý của Javis: bản `agy` trên máy này làm hỏng dấu tiếng Việt khi nhận prompt dài "
    "(chữ biến thành `�`), và đổi đường gửi cũng không cứu được. Lỗi nằm trong chính CLI, "
    "Javis không vá được - nâng cấp `agy` lên bản mới, hoặc đổi bộ não khác ở trang Models.)_"
)
_CANH_BAO_DOC_HONG = (
    "\n\n_(Lưu ý của Javis: `agy` có thử mở file ngữ cảnh nhưng KHÔNG đọc được (thường là do mức "
    "quyền hoặc sandbox chặn), nên lượt vừa rồi trả lời mà chưa có system prompt và bộ nhớ của "
    "Javis. Nâng cấp `agy` lên bản nhận prompt qua stdin là hết hẳn đường vòng này.)_"
)


# ---------------------------------------------------------------------------
# Mức quyền
# ---------------------------------------------------------------------------
def co_quyen_cho_mode(mode: Optional[str]) -> list[str]:
    """Ba mức quyền của Javis -> cờ của `agy`. Giá trị lạ về nấc CHẶT NHẤT (fail-closed).

    Chỉ có `--dangerously-skip-permissions` (tự duyệt mọi tool) và `--sandbox` (siết terminal)
    là thấy trong tài liệu. KHÔNG có nấc "chỉ đọc" tương đương `--approval-mode plan` của Gemini
    CLI, nên `suggest` ở đây được siết bằng SANDBOX cộng với lời dặn trong system prompt, chứ
    không phải một cái chốt cứng của CLI. Khác biệt này phải nói thật ở tài liệu, đừng để người
    dùng tưởng mức Chỉ đọc do CLI chặn như bên Gemini.
    """
    m = str(mode or "").strip().lower()
    co: list[str] = []
    if m == "full":
        if co_co("--dangerously-skip-permissions"):
            co.append("--dangerously-skip-permissions")
        return co
    # suggest + auto + mọi giá trị lạ: bật sandbox nếu bản CLI có.
    if co_co("--sandbox"):
        co.append("--sandbox")
    if m == "auto" and co_co("--dangerously-skip-permissions"):
        # auto = được ghi file nháp trong brain. Headless mà dừng lại hỏi duyệt là treo tới hết
        # giờ, nên vẫn phải tự duyệt; rào tiền/đơn/đăng bài nằm ở MCP Hub chứ không ở đây.
        co.append("--dangerously-skip-permissions")
    return co


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
def _tach_model(doc) -> list[str]:
    """Bóc danh sách model từ thứ `agy models` trả về, chấp NHIỀU hình dạng.

    CHƯA ĐO được khoá thật của JSON, nên nhận cả list chuỗi lẫn list dict với các khoá hay gặp.
    Thà rộng còn hơn kén: kén sai một khoá là trình chọn model rỗng trơn.
    """
    if isinstance(doc, dict):
        for k in ("models", "data", "items", "result"):
            if isinstance(doc.get(k), list):
                doc = doc[k]
                break
    if not isinstance(doc, list):
        return []
    ra: list[str] = []
    for m in doc:
        if isinstance(m, str):
            ten = m.strip()
        elif isinstance(m, dict):
            ten = ""
            for k in ("slug", "id", "model", "name", "label", "display_name"):
                v = m.get(k)
                if isinstance(v, str) and v.strip():
                    ten = v.strip()
                    break
        else:
            ten = ""
        if ten and ten not in ra:
            ra.append(ten)
    return ra


def list_models() -> Optional[list]:
    """Danh sách model hỏi thẳng CLI. None = chưa cài CLI (phía trên còn biết mà nói lý do).

    Không giữ bảng model chép tay: Google đổi tên model liên tục, và chính người dùng mới là
    người biết tài khoản mình được cấp những gì. `agy models` trả đúng thứ hiện trong trình
    chọn của Antigravity IDE.
    """
    cli = find_antigravity_cli()
    if not cli:
        return None
    # Bản >= 1.1.12 có --output-format cho `models`; bản cũ thì chỉ in chữ. Thử JSON trước.
    if co_co("--output-format"):
        try:
            r = subprocess.run([cli, "models", "--output-format", "json"], capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=30,
                               creationflags=_no_window())
            if r.returncode == 0 and (r.stdout or "").strip():
                ds = _tach_model(json.loads(r.stdout))
                if ds:
                    return ds
        except Exception:
            pass
    try:
        r = subprocess.run([cli, "models"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30, creationflags=_no_window())
    except Exception:
        return []
    if r.returncode != 0:
        return []
    # In chữ thuần. Đo trên `agy models` 1.1.12 (người dùng gửi kèm `cat -A`):
    #
    #     Fetching available models...
    #     gemini-3.6-flash-high^IGemini 3.6 Flash (High)$
    #     claude-sonnet-4-6^IClaude Sonnet 4.6 (Thinking)$
    #
    # Hai chỗ bản đầu làm sai, và cả hai đều hỏng LẶNG LẼ:
    #
    # 1. Cắt cột bằng `\s{2,}` - biểu thức đó KHÔNG khớp một tab đơn. Nên cả dòng
    #    "gemini-3.6-flash-high\tGemini 3.6 Flash (High)" bị lấy làm mã model, rồi truyền nguyên
    #    vào `--model`. `agy` không có model tên như vậy nên thoát mã 1 ở MỌI lượt chat - tức
    #    provider này không dùng được ở bất kỳ máy nào.
    # 2. Dòng thông báo "Fetching available models..." không bị lọc nên hiện như một model
    #    trong trình chọn.
    #
    # Lọc theo khoảng trắng là đủ và đúng bản chất: mã model là một slug, không bao giờ có
    # khoảng trắng; còn mọi câu thông báo thì luôn có.
    ra: list[str] = []
    for dong in (r.stdout or "").splitlines():
        d = dong.strip().lstrip("*->•").strip()
        if not d or d.endswith(":"):
            continue
        d = re.split(r"\t|\s{2,}", d)[0].strip()
        if not d or " " in d:
            continue
        if d not in ra:
            ra.append(d)
    return ra


# ---------------------------------------------------------------------------
# Đăng nhập
# ---------------------------------------------------------------------------
_AUTH_CACHE: dict = {"ts": 0.0, "val": None}
_AUTH_TTL = 60.0


def auth_status(bo_qua_cache: bool = False) -> dict:
    """Đã đăng nhập chưa: {connected, method, email, error}.

    Khác Gemini CLI ở một điểm quyết định cách viết hàm này: `agy` giữ phiên trong KEYRING của
    hệ điều hành, không có file credential nào để soi. Nên không có đường nào rẻ hơn là hỏi
    chính CLI - và vì trang Models gọi hàm này mỗi lần mở, phải nhớ kết quả một phút, đúng lý
    do mà `gemini_cli.auth_status()` cố tránh đẻ tiến trình.

    Dùng `models` làm phép thử vì nó cần tài khoản mới trả được danh sách, lại rẻ hơn nhiều so
    với chạy hẳn một lượt chat.
    """
    cli = find_antigravity_cli()
    if not cli:
        return {"connected": False, "method": "", "email": "",
                "error": f"Chưa cài Antigravity CLI. Cài một lần: {lenh_cai()}"}
    now = time.time()
    if not bo_qua_cache and _AUTH_CACHE["val"] and now - _AUTH_CACHE["ts"] < _AUTH_TTL:
        return dict(_AUTH_CACHE["val"])
    ds = list_models()
    if ds:
        d = {"connected": True, "method": "google (keyring của máy)", "email": "", "error": ""}
    else:
        # Nói rõ chuyện ĐÚNG USER (16/08): nhiều người đã đăng nhập agy thành công qua SSH
        # nhưng bằng user khác (vd root), còn Javis chạy bằng user riêng nên không thấy gì -
        # "đã cài rồi mà Javis không nhận". Trang Code của dashboard mở shell bằng chính user
        # của Javis nên đăng nhập ở đó là chắc ăn nhất.
        d = {"connected": False, "method": "", "email": "",
             "error": "Đã cài Antigravity CLI nhưng phiên của Javis chưa đăng nhập. Mở trang "
                      "Code (Terminal) NGAY TRONG Javis, gõ `agy` rồi làm theo hướng dẫn - "
                      "phải đăng nhập bằng ĐÚNG user đang chạy Javis; SSH bằng user khác "
                      "(vd root) đăng nhập xong Javis vẫn không thấy."}
    _AUTH_CACHE.update(ts=now, val=dict(d))
    return d


def login_huong_dan() -> dict:
    """Hướng dẫn đăng nhập. KHÔNG có nút bấm trên dashboard, và đó là quyết định có lý do.

    `agy` giữ token trong keyring hệ điều hành chứ không phải file, nên Javis không bắc cầu
    token hộ được như đã làm với Gemini CLI (`gemini_oauth.ghi_creds_cho_cli`). Dựng một nút
    "Đăng nhập" rồi bên dưới không làm gì được thì tệ hơn là nói thẳng phải gõ một lệnh.

    Điểm sáng cho người chạy VPS: `agy` tự nhận biết phiên SSH và IN RA một đường link để mở
    trên máy có trình duyệt, nên không cần màn hình ở phía máy chủ.
    """
    return {
        "cai": lenh_cai(),
        "dang_nhap": "agy",
        "ghi_chu": ("Dùng trang Code (Terminal) NGAY TRONG Javis - nó mở shell bằng đúng user "
                    "đang chạy Javis, đăng nhập ở đó là Javis nhận liền. (SSH bằng user khác, "
                    "vd root, đăng nhập xong Javis vẫn không thấy - đây là lý do hay gặp nhất "
                    "của cảnh 'cài rồi mà không nhận'.) Gõ `agy`: nó in ra một đường link, mở "
                    "link trên máy của bạn rồi đăng nhập Google là xong, chỉ phải làm một lần."),
    }


# ---------------------------------------------------------------------------
# MCP: đấu hub của Javis vào CLI
# ---------------------------------------------------------------------------
# ĐO NGÀY 2026-08-22, bằng nguồn cấp 1 chứ không phải suy từ tài liệu bên thứ ba: tài liệu MCP
# chính chủ của Antigravity, tài liệu di trú Gemini CLI → Antigravity của Google, và hai issue
# trên chính repo `google-antigravity/antigravity-cli` (#60 và #71, cái sau dán nguyên một cấu
# hình CHẠY ĐƯỢC). Vẫn KHÔNG phải đo trên binary: máy dựng bản này bị chặn mạng nên `agy` không
# tải về được - chỗ nào còn phải đoán thì có cửa thoát bằng biến môi trường, ghi rõ ở dưới.
#
# Kết quả lật ngược cả hai bản trước. Bản 0.30.0 đoán
# `.antigravity/mcp.json` + `.antigravity/settings.json`; bản 0.33.x thêm `.agents/mcp_config.json`
# rồi ghi vào CHANGELOG là "Antigravity giờ dùng được tool của Javis". Cả ba lần đều KHÔNG chạy,
# vì có tới hai chỗ sai chồng lên nhau và cả hai đều hỏng lặng lẽ:
#
# 1. SAI TÊN KHOÁ. Javis ghi `{"httpUrl": ...}` - đó là schema của **Gemini CLI**, chép nguyên từ
#    `_apply_gemini_hub`. `agy` đọc khoá `serverUrl` (tài liệu chính chủ, và issue #71 của
#    google-antigravity/antigravity-cli dán đúng cấu hình chạy được). Tài liệu di trú Gemini →
#    Antigravity nói thẳng: `url` được ĐỔI TÊN thành `serverUrl`. Entry không có khoá nào `agy`
#    hiểu = server không có địa chỉ = không bao giờ được khởi động, và không có câu lỗi nào.
#
# 2. SAI CHỖ ĐẶT. `agy` nạp MCP từ cấu hình tầng HOME:
#       ~/.gemini/config/mcp_config.json          (hiện hành, dùng chung với Antigravity 2.0/IDE)
#       ~/.gemini/antigravity-cli/mcp_config.json (đường cũ trước lần dọn thư mục)
#    Tầng workspace `<project>/.agents/mcp_config.json` là đường CÓ THẬT trong tài liệu, nhưng
#    issue #60 ghi nhận `agy` tìm thấy cấu hình project rồi BỎ QUA `mcpServers` trong đó - chỉ
#    tầng HOME mới thật sự dựng server. Nên phải ghi CẢ HAI tầng: HOME để chạy được ngay hôm nay,
#    workspace để bản nào vá xong issue đó thì tự có luôn cách ly theo brain.
#
# Đánh đổi của việc phải ghi vào HOME, nói thẳng ra chứ không giấu: file đó là của NGƯỜI DÙNG và
# dùng chung với Antigravity IDE, nên (a) IDE cũng sẽ nhìn thấy tool của Javis, (b) hai brain
# chạy `agy` cùng lúc thì brain sau ghi đè header `X-Javis-Vault` của brain trước. Bên Codex chỗ
# này chữa bằng override argv (`mcp_hub.codex_vault_override`); ở đây chưa đo được `agy` có cờ
# tương đương nên `_build_args` hỏi `co_co("--mcp-config")` rồi mới truyền - có thì hết race,
# không có thì vẫn chạy như cũ. Ai không muốn Javis đụng HOME thì đặt JAVIS_AGY_MCP_HOME=0.

# Hai đường ĐOÁN của các bản trước. Không còn ghi vào nữa, nhưng phải DỌN: chúng chứa hub token
# và nằm trong brain, mà brain thì có đường sao lưu git đẩy lên remote của người dùng.
_MCP_DUONG_BO = (".antigravity/mcp.json", ".antigravity/settings.json")


def hub_entry(url: str, headers: Optional[dict] = None) -> dict:
    """Một entry `mcpServers` theo ĐÚNG schema của `agy` (không phải của Gemini CLI).

    `serverUrl` là khoá chính chủ: tài liệu hiện hành dùng nó, và issue #71 của
    google-antigravity/antigravity-cli dán một cấu hình chạy được chỉ gồm `serverUrl` + `headers`.
    `url` ghi kèm làm bí danh cho các bản 1.0.x còn nhận tên cũ - JSON thừa khoá thì bộ đọc bỏ
    qua, còn thiếu khoá thì server câm luôn, nên chọn phía thừa.

    KHÔNG có `httpUrl`/`trust`/`timeout`: cả ba là của Gemini CLI, và chính `httpUrl` là thứ đã
    làm bộ não này chạy suốt mấy bản mà không có lấy một tool nào của Javis.

    Cửa thoát `JAVIS_AGY_MCP_KEY=serverUrl|url` cho ai gặp một bản `agy` khó tính từ chối entry
    có khoá lạ. Đây là chỗ KHÔNG đo được trên máy dựng bản này (mạng bị chặn không tải nổi
    binary), nên phải có một cái lẫy thay vì bắt người dùng chờ bản sau - file cấu hình bị Javis
    ghi đè mỗi lượt chat, sửa tay không giữ được.
    """
    khoa = (os.environ.get("JAVIS_AGY_MCP_KEY") or "").strip()
    if khoa == "serverUrl":
        e: dict = {"serverUrl": url}
    elif khoa == "url":
        e = {"url": url}
    else:
        e = {"serverUrl": url, "url": url}
    if headers:
        e["headers"] = dict(headers)
    e["disabled"] = False
    return e


def _duong_mcp_home() -> list[Path]:
    """Cấu hình MCP tầng HOME mà `agy` thật sự nạp. Rỗng nếu người dùng tắt bằng env."""
    if (os.environ.get("JAVIS_AGY_MCP_HOME") or "").strip() in ("0", "false", "no"):
        return []
    rieng = (os.environ.get("JAVIS_AGY_MCP_CONFIG") or "").strip()
    if rieng:
        return [Path(rieng).expanduser()]
    h = _home_dir()
    return [h / ".gemini" / "config" / "mcp_config.json",
            h / ".gemini" / "antigravity-cli" / "mcp_config.json"]


def duong_mcp(vault_root=None) -> list[Path]:
    """Mọi file cấu hình MCP Javis ghi cho `agy`, HOME trước rồi tới workspace."""
    ds = _duong_mcp_home()
    if vault_root:
        try:
            ds.append(Path(vault_root).expanduser() / ".agents" / "mcp_config.json")
        except Exception:
            pass
    return ds


def _ghi_mot_mcp(p: Path, hub: Optional[dict], xoa_khi_rong: bool = False) -> bool:
    """Đặt/gỡ entry `javis` trong MỘT file mcp_config, giữ nguyên phần của người dùng."""
    cu: dict = {}
    if p.exists():
        try:
            cu = json.loads(p.read_text(encoding="utf-8")) or {}
        except Exception:
            cu = {}
    if not isinstance(cu, dict):
        cu = {}
    servers = cu.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    if hub:
        servers["javis"] = hub
    else:
        servers.pop("javis", None)
    if servers:
        cu["mcpServers"] = servers
    else:
        cu.pop("mcpServers", None)
    # Chỉ xoá file khi ĐÓ LÀ FILE CỦA JAVIS (hai đường đoán cũ) và không còn gì trong đó. File
    # HOME là của người dùng, không bao giờ xoá - cùng lắm để lại `{}`, vẫn là JSON hợp lệ.
    if xoa_khi_rong and not cu:
        try:
            if p.exists():
                p.unlink()
        except Exception:
            return False
        return True
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cu, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(p, 0o600)   # chứa hub token
    except Exception:
        pass
    return True


def ghi_mcp_settings(vault_root, hub: Optional[dict]) -> Optional[str]:
    """Đấu hub của Javis vào `agy`: ghi entry `javis` vào cấu hình HOME + workspace.

    `hub=None` (hub tắt) → GỠ entry `javis` khỏi mọi chỗ, giữ nguyên MCP người dùng tự thêm.
    Trả về đường dẫn file ĐẦU TIÊN ghi được (file HOME - chỗ `agy` thật sự nạp), None nếu không
    ghi được chỗ nào. Lý do chọn từng đường dẫn: xem khối chú thích dài ngay trên.
    """
    ra = None
    # Thư mục neo: `agy` đi ngược lên từ cwd để tìm gốc project và dừng ở thư mục có
    # `.antigravitycli/`. Không có neo thì nó nhận nhầm một thư mục tổ tiên làm gốc, và
    # `.agents/mcp_config.json` của brain nằm ngoài tầm. Chỉ tạo THƯ MỤC rỗng, không tạo file:
    # `.antigravitycli/mcp_config.json` chính là đường project-local bị bỏ qua ở issue #60, còn
    # file mcp_config rỗng thì làm bộ đọc của bản 1.x nổ (issue #252).
    if vault_root:
        try:
            (Path(vault_root).expanduser() / ".antigravitycli").mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"[antigravity mcp settings] neo project: {e}", file=sys.stderr)
    for p in duong_mcp(vault_root):
        try:
            if _ghi_mot_mcp(p, hub) and ra is None:
                ra = str(p)
        except Exception as e:
            print(f"[antigravity mcp settings] {p}: {e}", file=sys.stderr)
    # Dọn hai đường ĐOÁN của các bản trước. Không chỉ vì gọn: chúng giữ hub token trong brain.
    if vault_root:
        for ten in _MCP_DUONG_BO:
            try:
                p = Path(vault_root).expanduser() / ten
                if p.exists():
                    _ghi_mot_mcp(p, None, xoa_khi_rong=True)
            except Exception as e:
                print(f"[antigravity mcp settings] dọn {ten}: {e}", file=sys.stderr)
    return ra


def trang_thai_mcp(vault_root=None) -> dict:
    """Hub đã thật sự nằm trong cấu hình `agy` chưa - để trang Models nói được sự thật.

    Đọc lại chính file vừa ghi thay vì tin là đã ghi xong. Đây là lớp canh cho đúng hạng lỗi đã
    xảy ra ba lần liên tiếp ở khối trên: file ghi thành công, đường dẫn sai hoặc khoá sai, `agy`
    chạy ngon lành mà không có tool nào, và không ai biết.
    """
    ds, thieu = [], []
    for p in duong_mcp(vault_root):
        try:
            doc = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except Exception:
            doc = {}
        e = ((doc or {}).get("mcpServers") or {}).get("javis") or {}
        # Nhận cả hai tên khoá: JAVIS_AGY_MCP_KEY=url thì entry chỉ có `url`, soi mỗi
        # `serverUrl` là báo "chưa đấu" cho một cấu hình hoàn toàn đúng.
        dia_chi = str(e.get("serverUrl") or e.get("url") or "")
        ds.append({"path": str(p), "co_javis": bool(dia_chi), "url": dia_chi})
        co = bool(dia_chi)
        if not co:
            thieu.append(str(p))
    return {"ok": any(d["co_javis"] for d in ds), "files": ds, "thieu": thieu}


# ---------------------------------------------------------------------------
# Một lượt chạy
# ---------------------------------------------------------------------------
class AntigravityCLI:
    """Một lượt chạy `agy` headless. Cùng hợp đồng sự kiện với ClaudeSDK/CodexCLI/GeminiCLI."""

    def __init__(self, cwd: Optional[str] = None, tag: str = "chat", model: Optional[str] = None,
                 instructions: Optional[str] = None):
        self.cli_path = find_antigravity_cli()
        self.cwd = cwd or os.getcwd()
        self.tag = tag
        self.model = model
        self.instructions = instructions
        self.session_id = None          # có giá trị -> nối lại mạch cũ
        self._session_moi = None
        self.mode = "suggest"
        # File mcp_config riêng cho ĐÚNG lượt này. Chỉ dùng được nếu bản `agy` trên máy có cờ
        # nhận file cấu hình (hỏi `co_co` trước khi truyền). Có thì hết cảnh hai brain chạy cùng
        # lúc ghi đè header X-Javis-Vault của nhau trong file HOME dùng chung.
        self.mcp_config: Optional[str] = None
        self.extra_args: list[str] = []
        self.include_dirs: list[str] = []
        # Trần thời gian một lượt. Gemini CLI không cần vì `--approval-mode` chặn mọi câu hỏi;
        # ở đây mức suggest/auto CHƯA ĐO được là CLI có dừng hỏi không, mà headless dừng hỏi là
        # treo vĩnh viễn. Thà cắt và báo còn hơn để một việc nền ngậm tiến trình cả đêm.
        self.timeout = float(os.environ.get("JAVIS_AGY_TIMEOUT") or 900)

    def is_available(self) -> bool:
        return self.cli_path is not None

    def _build_args(self, prompt_argv: Optional[str], noi_mach: bool = True,
                    them: Optional[list] = None, ct_stdin: str = "") -> list[str]:
        args = [self.cli_path]
        if self.model and co_co("--model"):
            args += ["--model", self.model]
        args += co_quyen_cho_mode(self.mode)
        if self.mcp_config and co_co("--mcp-config", "--mcp-config-file"):
            args += ["--mcp-config", self.mcp_config]
        if co_co("--output-format"):
            args += ["--output-format", "stream-json"]
        if noi_mach and self.session_id and co_co("--conversation"):
            args += ["--conversation", self.session_id]
        if co_co("--add-dir"):
            for d in self.include_dirs:
                args += ["--add-dir", str(d)]
        args += list(them or [])
        # Trần thời gian của CHÍNH `agy` trong print mode, mặc định 5 phút. Không đặt thì việc
        # nền dài bị chính CLI cắt ở phút thứ 5 trong khi Javis còn ngồi đợi tới 15 - và cắt kiểu
        # đó trả về câu trả lời dở dang chứ không báo lỗi, nên rất khó đoán ra.
        if co_co("--print-timeout"):
            args += ["--print-timeout", f"{int(self.timeout)}s"]
        args += list(self.extra_args)
        # Cờ prompt PHẢI nằm CUỐI CÙNG. `agy` bỏ qua mọi cờ đứng sau `-p`, nên chèn thêm cờ ở
        # dưới là `--output-format stream-json` bị rơi, CLI in chữ thuần, bộ đọc stream không
        # hiểu và người dùng nhận một bong bóng rỗng - hỏng lặng lẽ, không có lấy một câu lỗi.
        if prompt_argv is not None:
            args += ["-p", prompt_argv]
        else:
            # Đi stdin: cú pháp lấy từ công thức đã ĐO được trên chính máy này, không phải công
            # thức đoán. Xem `_CT_STDIN` và `_do_stdin`.
            args += list(dict(_CT_STDIN).get(ct_stdin or "rong", ["-p", ""]))
        return args

    def _chon_duong(self, full: str) -> str:
        """Prompt này đi đường nào: argv, stdin hay file ngữ cảnh.

        Tách hàm riêng vì nó ĐỒNG BỘ và có thể chậm (lần đầu phải chạy `agy --help`, trần 20
        giây), nên `query()` đẩy nó sang worker thay vì gọi thẳng trong event loop.
        """
        ep = (os.environ.get("JAVIS_AGY_PROMPT_DAI") or "").strip().lower()
        if ep in ("stdin", "file", "argv"):
            return duong_prompt_dai(self.cli_path) if ep == "stdin" else ep
        if len(full) + sum(len(a) + 3 for a in self._build_args("")) <= _tran_argv():
            return "argv"     # vừa dòng lệnh thì cứ đường cũ, đã chạy tốt trên Linux/macOS
        return duong_prompt_dai(self.cli_path)

    async def query(self, prompt: str) -> AsyncIterator[dict]:
        """Một lượt chat. Tự chọn đường đưa prompt, và tự thử lại nếu đường đó không tới nơi."""
        if not self.cli_path:
            yield {"type": "error",
                   "content": f"Không tìm thấy Antigravity CLI (`agy`). Cài một lần trên máy "
                              f"chạy Javis:\n\n`{lenh_cai()}`\n\nRồi gõ `agy` một lần để đăng "
                              f"nhập Google."}
            return
        full = (self.instructions.strip() + "\n\n" + prompt) if self.instructions else prompt
        # Ba đường đưa prompt cho CLI, xếp theo mức trung thực giảm dần:
        #   argv  - nhét thẳng vào dòng lệnh. Nguyên vẹn, nhưng đụng trần của hệ điều hành.
        #   stdin - bơm qua ống dẫn. Cũng nguyên vẹn, không trần. Đường ĐÚNG khi prompt dài.
        #   file  - ghi ra file rồi bảo model tự đọc. Không trần, nhưng phụ thuộc model chịu mở.
        duong = await asyncio.to_thread(self._chon_duong, full)
        ket: dict = {}
        # Lượt đi stdin là lượt CÓ THỂ HỎNG rồi thử lại, nên giữ lỗi của nó lại thay vì bắn ngay
        # ra màn hình. Chủ repo đã thấy đúng cảnh ngược lại: hai bong bóng đỏ "Error: empty
        # prompt" và "thoát với mã 1" hiện lên, rồi mới tới câu trả lời - người dùng không có
        # cách nào biết cái đỏ đó Javis đã tự xử xong.
        async for ev in self._mot_luot(full, prompt, duong, ket,
                                       giu_loi=duong.startswith("stdin")):
            yield ev
        # Prompt KHÔNG TỚI NƠI có hai hình dạng, và bản trước chỉ bắt được một:
        #   - chạy xong, không lỗi, không lấy một chữ (bản CLI nuốt stdin);
        #   - thoát mã 1 kèm "Error: empty prompt. Usage: agy --print ..." (bản CLI kiểm giá trị
        #     cờ TRƯỚC khi ngó tới stdin - chính là bản của chủ repo, đo 2026-08-13).
        # Ca thứ hai rơi vào nhánh "có lỗi" nên bản trước bỏ mặc, và người dùng lĩnh trọn câu
        # tiếng Anh mà họ không sửa được gì với nó. Cả hai nay đều đổi sang đường file NGAY trong
        # lượt này.
        _loi_thieu_prompt = any(_la_loi_thieu_prompt(x) for x in ket.get("cac_loi") or [])
        # Hình dạng thứ BA của "prompt không tới nơi", tinh vi hơn hai cái trên vì nó vẫn trả lời
        # trôi chảy: prompt tới nơi nhưng HỎNG DẤU. Chủ repo báo 2026-08-13 kèm ảnh - chữ trong
        # câu trả lời thành "gm", "hn", mỗi ký tự tiếng Việt 3 byte hoá 3 dấu U+FFFD.
        # Đó là bên đọc cắt mẩu ống dẫn giữa một ký tự rồi giải mã từng mẩu rời. Javis không sửa
        # được `agy`, nhưng phát hiện được: U+FFFD gần như không bao giờ xuất hiện trong câu trả
        # lời lành lặn.
        _hong_dau = "�" in (ket.get("text") or "")
        _thu_lai = duong.startswith("stdin") and (
            _hong_dau or (not ket.get("text") and (_loi_thieu_prompt or not ket.get("loi"))))
        if _thu_lai:
            _vi_sao = ("stdin làm hỏng dấu tiếng Việt" if _hong_dau
                       else "công thức stdin bị CLI từ chối" if _loi_thieu_prompt
                       else "stdin trả về rỗng")
            print(f"[antigravity] {_vi_sao}, chuyển sang file ngữ cảnh", file=sys.stderr)
            await asyncio.to_thread(nho_duong, self.cli_path, "file", _vi_sao)
            _ket_cu = ket
            ket = {}
            async for ev in self._mot_luot(full, prompt, "file", ket):
                yield ev
            # Đường file cũng hỏng dấu, mà lượt stdin thì có chữ: giữ lượt nào cũng vậy thôi,
            # lấy lượt sau cho nhất quán rồi nói thẳng là lỗi nằm trong CLI.
            if _hong_dau and not ket.get("text"):
                ket = _ket_cu
        elif duong.startswith("stdin") and ket.get("text"):
            await asyncio.to_thread(nho_duong, self.cli_path, duong, "đã chạy được")
        else:
            for _l in ket.get("cac_loi") or []:      # không thử lại thì phải đưa lỗi ra
                yield {"type": "error", "content": _l}
        text = ket.get("text") or ""
        if text:
            # Không nuốt chuyện này: trả lời mà thiếu system prompt thì vẫn trôi chảy, người dùng
            # không tài nào nhận ra Javis vừa quên hết luật và bộ nhớ của mình. Đó đúng là kiểu
            # sai âm thầm mà file này viết ra để tránh. Nhưng chỉ nói khi BIẾT CHẮC - dán một câu
            # cảnh báo vào mọi lượt vì không đo được cũng là một kiểu nói sai.
            if ket.get("biet_doc_hay_khong", True) and not ket.get("doc_duoc", True):
                print(f"[antigravity] model không đọc được file ngữ cảnh "
                      f"{ket.get('ten_ngu_canh')} (đã thử: {ket.get('da_thu_doc')})",
                      file=sys.stderr)
                text += (_CANH_BAO_DOC_HONG if ket.get("da_thu_doc") else _CANH_BAO_CHUA_DOC)
            # Đổi đường rồi mà chữ vẫn hỏng dấu: hết cách trong tầm Javis. Nói thẳng, đừng để
            # người dùng ngồi đoán xem mình gõ sai hay máy hỏng.
            elif "�" in text:
                print("[antigravity] câu trả lời vẫn còn ký tự hỏng sau khi đổi đường",
                      file=sys.stderr)
                text += _CANH_BAO_HONG_DAU
            yield {"type": "final", "content": text}
        elif not ket.get("loi"):
            # Lưới an toàn cuối. Bản 1.0.0 của agy có lỗi nuốt stdout khi chạy qua ống dẫn
            # (issue #76 của google-antigravity/antigravity-cli); im lặng ở đây thì người dùng
            # lại thấy đúng cái bong bóng rỗng như hồi Gemini CLI.
            yield {"type": "error",
                   "content": "Antigravity CLI chạy xong nhưng không trả về nội dung nào. Bản "
                              "CLI quá cũ có lỗi mất stdout khi chạy nền - thử nâng cấp: "
                              f"`{lenh_cai()}`"}

    async def _mot_luot(self, full: str, prompt: str, duong: str, ket: dict,
                        giu_loi: bool = False) -> AsyncIterator[dict]:
        """Chạy ĐÚNG một tiến trình `agy` theo đường đã chọn.

        Chỉ phát ra sự kiện dọc đường (tool_call, usage, error). Kết quả tổng của lượt đổ vào
        `ket` để `query()` quyết có phải thử lại đường khác không - phát `final` ở đây thì lượt
        thử lại sẽ đẩy ra hai câu trả lời.

        `giu_loi=True` thì lỗi được gom vào `ket["cac_loi"]` thay vì bắn ra ngay: lượt này còn có
        thể được thử lại bằng đường khác, mà một câu lỗi tiếng Anh hiện lên rồi câu trả lời hiện
        sau chỉ làm người dùng hoang mang.
        """
        tep_ngu_canh = ten_ngu_canh = ""
        prompt_argv = full
        them_args: list[str] = []
        if duong == "file":
            try:
                tep_ngu_canh, ten_ngu_canh = _viet_file_ngu_canh(self.cwd, full)
            except Exception as e:
                ket.update(text="", loi=True, doc_duoc=True, ten_ngu_canh="",
                           cac_loi=[])
                yield {"type": "error",
                       "content": f"Không ghi được file ngữ cảnh cho Antigravity CLI "
                                  f"({type(e).__name__}: {e}). Prompt của Javis dài hơn trần "
                                  f"dòng lệnh của hệ điều hành nên phải đi qua file. Kiểm tra "
                                  f"quyền ghi của thư mục state, hoặc đổi bộ não khác ở trang "
                                  f"Models."}
                return
            prompt_argv = _loi_nhac_file(ten_ngu_canh, prompt)
            # File nằm ngoài cwd (xem `_viet_file_ngu_canh`) nên phải mở quyền đọc cho đúng thư
            # mục đó, không thì model nhìn thấy đường dẫn mà mở không được.
            if co_co("--add-dir"):
                them_args = ["--add-dir", str(Path(tep_ngu_canh).parent)]
        # Không nối mạch cũ khi đi đường file: lịch sử phía CLI còn nguyên câu "đọc file X" của
        # lượt trước, mà file đó đã bị xoá cuối lượt trước - model đi mở lại là tốn một vòng tool
        # để nhận lỗi. Nối mạch cũng chẳng tiết kiệm được gì vì Javis gửi lại đủ ngữ cảnh mỗi lượt.
        qua_stdin = duong.startswith("stdin")
        args = self._build_args(None if qua_stdin else prompt_argv,
                                noi_mach=(duong != "file"), them=them_args,
                                ct_stdin=duong.partition(":")[2])
        loop = asyncio.get_running_loop()
        hang: asyncio.Queue = asyncio.Queue()
        HET = object()

        def doc_luong():
            proc = None
            try:
                proc = subprocess.Popen(
                    args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    cwd=self.cwd, text=True, encoding="utf-8", errors="replace", bufsize=1,
                    creationflags=_no_window(), start_new_session=(os.name != "nt"),
                )
                try:
                    if qua_stdin:
                        _ghi_stdin(proc, full)
                    proc.stdin.close()
                except Exception:
                    pass
                for line in iter(proc.stdout.readline, ""):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        loop.call_soon_threadsafe(hang.put_nowait, json.loads(line))
                    except json.JSONDecodeError:
                        loop.call_soon_threadsafe(hang.put_nowait, {"_raw": line})
                err = ""
                try:
                    err = (proc.stderr.read() or "").strip()
                except Exception:
                    pass
                ma = proc.wait(timeout=self.timeout)
                if ma != 0 or err:
                    loop.call_soon_threadsafe(hang.put_nowait, {"_exit": ma, "_err": err})
            except subprocess.TimeoutExpired:
                loop.call_soon_threadsafe(
                    hang.put_nowait,
                    {"_exit": -1, "_err": f"Antigravity CLI chạy quá {int(self.timeout)}s nên bị "
                                          f"cắt. Nếu việc thật sự dài thì nâng biến môi trường "
                                          f"JAVIS_AGY_TIMEOUT."})
            except Exception as e:
                loop.call_soon_threadsafe(hang.put_nowait,
                                          {"_exit": -1, "_err": f"{type(e).__name__}: {e}"})
            finally:
                try:
                    if proc and proc.poll() is None:
                        proc.terminate()
                except Exception:
                    pass
                # Dọn file ngữ cảnh ở ĐÂY chứ không ở vòng đọc sự kiện: luồng này luôn chạy hết,
                # kể cả khi người dùng đóng tab giữa chừng và không ai đọc nốt hàng đợi nữa.
                # Để sót là rác tích dần trong brain của người dùng.
                if tep_ngu_canh and not os.environ.get("JAVIS_AGY_GIU_NGU_CANH"):
                    try:
                        os.unlink(tep_ngu_canh)
                    except Exception:
                        pass
                loop.call_soon_threadsafe(hang.put_nowait, HET)

        threading.Thread(target=doc_luong, name=f"javis-agy-{self.tag}", daemon=True).start()

        cac_manh: list[str] = []
        cac_loi: list[str] = []
        da_loi = False
        # Đi đường file thì phải biết model có ĐỌC ĐƯỢC file không, và phải phân biệt cho đúng ba
        # trạng thái chứ không phải hai. Bản đầu chỉ dò tên file trong bất kỳ sự kiện nào, và nó
        # sai theo cả hai chiều:
        #   - Sự kiện `tool_call` phát ra TRƯỚC khi biết đọc được hay không. Sandbox chặn, quyền
        #     bị từ chối, file mất - vẫn có tên file trong đó, vẫn bị tính là "đã đọc". Tức lưới
        #     an toàn mù đúng lúc cần nhất.
        #   - Bản CLI cũ không có `--output-format` thì stdout là chữ thuần, không có sự kiện có
        #     cấu trúc nào cả. Lúc đó cờ luôn tắt và MỌI lượt bị dán cảnh báo oan.
        # Nên: chỉ tính "đọc được" khi thấy KẾT QUẢ tool không lỗi có nhắc tên file, và khi không
        # có sự kiện cấu trúc nào thì thành thật ghi nhận là KHÔNG BIẾT, không dán gì.
        ten_ngan = ten_ngu_canh.replace("\\", "/").rsplit("/", 1)[-1]
        doc_duoc = (duong != "file")
        da_thu_doc = False
        # Đo được hay không = có xin `--output-format stream-json` VÀ CLI có trả về JSON thật.
        # Bản cũ không có cờ đó, hoặc bản 1.0.0 dính lỗi nuốt stdout, đều cho ra toàn dòng `_raw`
        # - lúc đó vắng sự kiện tool KHÔNG chứng minh được gì.
        co_stream = co_co("--output-format")
        co_json = False
        while True:
            ev = await hang.get()
            if ev is HET:
                break
            if duong == "file" and not doc_duoc:
                t = str(ev.get("type") or ev.get("event") or "").lower()
                if "_raw" not in ev and "_exit" not in ev:
                    co_json = True
                if ten_ngan and ten_ngan in str(ev):
                    if t in ("tool_result", "tool_output"):
                        tt = (str(ev.get("status") or "") + " "
                              + str(ev.get("output") or ev.get("content") or "")[:300]).lower()
                        if not any(k in tt for k in ("error", "fail", "denied", "not found",
                                                     "no such", "permission")):
                            doc_duoc = True
                    else:
                        da_thu_doc = True
            for ra in self._doi_su_kien(ev, cac_manh):
                if ra.get("type") == "error":
                    da_loi = True
                    cac_loi.append(str(ra.get("content") or ""))
                    if giu_loi:
                        continue      # lượt này còn có thể thử lại bằng đường khác
                yield ra
        ket.update(text="".join(cac_manh).strip(), loi=da_loi, cac_loi=cac_loi,
                   ten_ngu_canh=ten_ngu_canh,
                   doc_duoc=doc_duoc, da_thu_doc=da_thu_doc,
                   biet_doc_hay_khong=(duong != "file") or (co_stream and co_json))

    def _doi_su_kien(self, ev: dict, cac_manh: list) -> list:
        """Một dòng NDJSON của `agy` -> 0..n sự kiện theo hợp đồng của Javis.

        CHƯA ĐO được tên trường thật, nên nhận rộng: gom mọi hình dạng "có chữ để hiện" mà một
        stream sự kiện hay dùng. Dòng lạ hoàn toàn thì giữ nguyên làm chữ ở cuối hàm - mất công
        đẹp còn hơn mất câu trả lời.
        """
        if "_raw" in ev:
            cac_manh.append(str(ev["_raw"]))
            return []
        if "_exit" in ev:
            loi = str(ev.get("_err") or "").strip()
            if ev.get("_exit") == 0 and not loi:
                return []
            if _la_loi_chua_dang_nhap(loi):
                return [{"type": "error",
                         "content": "Antigravity CLI chưa đăng nhập. Mở terminal trên máy chạy "
                                    "Javis, gõ `agy` rồi làm theo hướng dẫn (qua SSH thì nó in "
                                    "ra một link để mở trên máy bạn)."}]
            if not loi:
                loi = f"Antigravity CLI thoát với mã {ev.get('_exit')}."
            return [{"type": "error", "content": loi[:1500]}]

        t = str(ev.get("type") or ev.get("event") or "").lower()

        # `agy` gói payload LỒNG dưới đúng tên sự kiện, đo trên 1.1.12:
        #
        #   {"event":"init","conversation_id":"...","init":{"model":"...","cwd":"/app"}}
        #   {"event":"step_update","step_update":{"step_type":"agent_response",
        #                                        "text_delta":"Xin chào!","usage":{...}}}
        #   {"event":"result","result":{"status":"SUCCESS","response":"Xin chào!","usage":{...}}}
        #
        # Bản đầu chỉ đọc tầng NGOÀI CÙNG nên không thấy gì - `agy` chạy thành công mà bong bóng
        # trả lời rỗng. Trải phẳng một tầng để phần dưới đọc như mọi stream phẳng khác. Giữ khoá
        # tầng ngoài khi trùng tên là cố ý: `conversation_id` nằm ở ngoài chứ không ở trong.
        _sub = ev.get(t)
        if isinstance(_sub, dict):
            _gop = dict(_sub)
            _gop.update({k: v for k, v in ev.items() if k != t})
            ev = _gop

        # Mở mạch: nhặt id hội thoại để lượt sau nối lại được.
        if t in ("init", "session", "conversation", "start", "system"):
            for k in ("conversation_id", "session_id", "conversationId", "sessionId", "id"):
                v = ev.get(k)
                if isinstance(v, str) and v.strip():
                    self.session_id = v.strip()
                    break
            return []

        if t in ("tool_use", "tool_call", "tool"):
            return [{"type": "tool_call",
                     "name": str(ev.get("tool_name") or ev.get("name") or ""),
                     "id": str(ev.get("tool_id") or ev.get("id") or ""),
                     "input": ev.get("parameters") or ev.get("input") or {}}]
        if t in ("tool_result", "tool_output"):
            return [{"type": "tool_result", "id": str(ev.get("tool_id") or ev.get("id") or ""),
                     "status": str(ev.get("status") or ""),
                     "content": str(ev.get("output") or ev.get("content") or "")[:2000]}]
        if t == "error":
            tin = str(ev.get("message") or ev.get("error") or "Antigravity CLI lỗi.")
            if _la_loi_chua_dang_nhap(tin):
                return [{"type": "error",
                         "content": "Antigravity CLI chưa đăng nhập. Gõ `agy` một lần trên máy "
                                    "chạy Javis."}]
            if str(ev.get("severity") or "error") == "warning":
                return []
            return [{"type": "error", "content": tin[:1500]}]

        ra = []
        if t in ("result", "final", "done", "complete"):
            st = ev.get("stats") or ev.get("usage") or {}
            if isinstance(st, dict) and st:
                ra.append({"type": "usage",
                           "input_tokens": int(st.get("input_tokens")
                                               or st.get("prompt_tokens") or 0),
                           "output_tokens": int(st.get("output_tokens")
                                                or st.get("completion_tokens") or 0),
                           "total_tokens": int(st.get("total_tokens") or 0),
                           "cached": int(st.get("cached") or 0)})
            if str(ev.get("status") or "").lower() == "error":
                e = ev.get("error") or {}
                tin = str(e.get("message") if isinstance(e, dict) else e) or ""
                ra.append({"type": "error",
                           "content": tin[:1500] or "Antigravity CLI kết thúc với lỗi."})
                return ra
            # Sự kiện kết thúc mang LẠI TOÀN VĂN câu trả lời trong `response`, trong khi các
            # `text_delta` trước đó đã gom đủ rồi -> gom tiếp là câu trả lời hiện HAI LẦN.
            #
            # Nhưng cũng KHÔNG được bỏ hẳn: lượt trả lời ngắn có bản chỉ phát mỗi `result`,
            # không có delta nào. Nên chỉ lấy khi tay trắng - đúng một lần, và không bao giờ
            # rỗng vì lý do "đã bỏ qua chỗ duy nhất có chữ".
            if cac_manh:
                return ra

        # Còn lại: mọi thứ trông như chữ của trợ lý đều gom vào câu trả lời. Đây là chỗ hứng
        # những hình dạng chưa đo được, nên viết rộng có chủ đích.
        if str(ev.get("role") or "assistant").lower() in ("assistant", "model", "agent", ""):
            for k in ("text_delta", "content", "text", "delta", "message", "response", "output"):
                v = ev.get(k)
                if isinstance(v, str) and v:
                    cac_manh.append(v)
                    break
                if isinstance(v, dict):
                    vv = v.get("text") or v.get("content")
                    if isinstance(vv, str) and vv:
                        cac_manh.append(vv)
                        break
        return ra


def _la_loi_chua_dang_nhap(loi: str) -> bool:
    """Câu này có phải chuyện chưa đăng nhập không.

    "select login method" nằm trong danh sách vì bản `agy` chưa có phiên KHÔNG báo lỗi - nó mở
    thẳng menu chọn cách đăng nhập rồi ngồi chờ bàn phím (ảnh chủ repo 2026-08-13). Với một
    lượt chạy nền thì đó chính là "chưa đăng nhập", chỉ khác cách nói.
    """
    l = (loi or "").lower()
    return any(k in l for k in ("not signed in", "not logged in", "sign in", "login required",
                                "unauthenticated", "no active session", "authentication",
                                "select login method"))


def kiem_tra_nhanh(timeout: float = 60.0) -> dict:
    """Chạy thử một lượt cực ngắn cho nút "Kiểm tra lại" ở trang Models.

    Chỉ đọc trạng thái từ `models` thì mới biết tài khoản còn sống, chưa biết luồng chat có
    chạy không - mà đúng chỗ đó là chỗ Gemini CLI gãy. Nên ở đây chạy thật một lượt.
    """
    cli = find_antigravity_cli()
    if not cli:
        return {"ok": False, "error": f"Chưa cài Antigravity CLI. {lenh_cai()}"}
    args = [cli]
    if co_co("--output-format"):
        args += ["--output-format", "json"]
    args += ["-p", "Trả lời đúng một chữ: ok"]
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, creationflags=_no_window())
    except subprocess.TimeoutExpired as e:
        # Hết giờ ở đây gần như LUÔN là "chưa đăng nhập" chứ không phải máy chậm: chưa có phiên
        # thì `agy` mở menu "Select login method" rồi ngồi chờ bàn phím, mà ở đây không có ai
        # gõ. Câu "không trả lời kịp" đúng về mặt kỹ thuật nhưng chỉ sai đường - chủ repo bấm
        # Kiểm tra lại và ngồi nhìn "Đang thử..." mà không biết việc phải làm là đăng nhập
        # (ảnh 2026-08-13). Soi thứ nó kịp in ra để nói cho đúng.
        _ra = ""
        for _t in (getattr(e, "stdout", None), getattr(e, "stderr", None), getattr(e, "output", None)):
            if isinstance(_t, bytes):
                _t = _t.decode("utf-8", "replace")
            if _t:
                _ra += _t
        if _la_loi_chua_dang_nhap(_ra) or "select login method" in _ra.lower():
            return {"ok": False,
                    "error": "Chưa đăng nhập - CLI đang đứng ở màn chọn cách đăng nhập. Mở "
                             "terminal trên máy chạy Javis, gõ `agy` rồi làm theo hướng dẫn."}
        return {"ok": False, "error": "Antigravity CLI không trả lời kịp."}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    out = (r.stdout or "").strip()
    if r.returncode != 0:
        loi = (r.stderr or out or "").strip()
        if _la_loi_chua_dang_nhap(loi):
            return {"ok": False, "error": "Chưa đăng nhập. Gõ `agy` một lần trên máy chạy Javis."}
        return {"ok": False, "error": loi[:400] or f"Thoát mã {r.returncode}"}
    if not out:
        return {"ok": False,
                "error": "CLI chạy xong nhưng không in ra gì. Bản cũ có lỗi mất stdout khi chạy "
                         f"nền - nâng cấp bằng: {lenh_cai()}"}
    try:
        d = json.loads(out)
    except json.JSONDecodeError:
        return {"ok": True, "reply": out[:200]}
    if isinstance(d, dict) and d.get("error"):
        e = d["error"]
        return {"ok": False,
                "error": str(e.get("message") if isinstance(e, dict) else e)[:400]}
    tra = ""
    if isinstance(d, dict):
        for k in ("response", "result", "content", "text", "output"):
            if isinstance(d.get(k), str):
                tra = d[k]
                break
    return {"ok": True, "reply": (tra or out)[:200]}
