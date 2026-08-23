"""File người dùng đính kèm/dán vào khung chat phải ĐỌC ĐƯỢC trên mọi engine.

    python tests/run.py doc_file_dinh_kem        (KHÔNG mạng)

Người dùng báo 23/08: dán một đoạn văn dài vào khung chat (dashboard tự cắt thành
`van-ban-dan-HHMMSS.txt` rồi tải lên) thì Javis bảo phải tự chép file vào thư mục Brain mới
đọc được.

Đúng là hỏng, và hỏng ở chỗ nối: dashboard chèn vào câu hỏi khối "[File đính kèm để ĐỌC
(đường dẫn): …]" với đường dẫn tuyệt đối trong `STATE_DIR/.staging`, rồi dặn model "đọc thẳng
file rồi trả lời". Nhưng sáu engine API không có tool đọc file nào ngoài `javis_read_file`,
mà tool đó đi qua `_safe_path` khoá trong vault → mọi lượt có đính kèm đều nổ
`ValueError: nằm ngoài vault`, và model đọc lỗi đó xong tự nghĩ ra lời khuyên "chuyển file
vào Brain đi". (Claude Code/Codex không dính vì chúng có tool đọc file native.)

Test khoá ba việc:
  1. `_safe_read_path` mở đúng MỘT thư mục và chỉ khi được xin tường minh.
  2. Không mở kèm đường nào khác - `..`, thư mục cha của staging, chỗ khác trên ổ đĩa.
  3. Ghi vẫn khoá trong vault, và bot chuyên trách (không truyền cờ) vẫn không thấy staging.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="javis-dinhkem-")
os.environ.setdefault("JAVIS_STATE_DIR", _TMP)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import asyncio  # noqa: E402
import inspect  # noqa: E402
from pathlib import Path  # noqa: E402

import mcp_hub  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


VAULT = Path(_TMP) / "brains" / "Brain Default"
(VAULT / "Sources").mkdir(parents=True, exist_ok=True)
(VAULT / "Sources" / "ghi-chu.md").write_text("nội dung trong vault", encoding="utf-8")

STAGE = Path(_TMP) / ".staging"
STAGE.mkdir(parents=True, exist_ok=True)
DAN = STAGE / "van-ban-dan-165611.txt"
DAN.write_text("đoạn văn dài user vừa dán", encoding="utf-8")

NGOAI = Path(_TMP) / "bi-mat.txt"          # cùng ổ đĩa nhưng không thuộc vault lẫn staging
NGOAI.write_text("không được đọc", encoding="utf-8")


def _no(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _chan(fn, *a, **kw):
    """True nếu gọi xong NÉM ValueError (tức bị chặn)."""
    try:
        fn(*a, **kw)
        return False
    except ValueError:
        return True


# ============================================================
# 1) _vung_nhan_file trỏ đúng STATE_DIR/.staging
# ============================================================
check("vùng nhận file = STATE_DIR/.staging", mcp_hub._vung_nhan_file() == STAGE.resolve())


# ============================================================
# 2) _safe_read_path
# ============================================================
check("file trong vault vẫn đọc như cũ",
      mcp_hub._safe_read_path(VAULT, "Sources/ghi-chu.md") == (VAULT / "Sources" / "ghi-chu.md").resolve())

check("MẶC ĐỊNH vẫn chặn file staging (bot chuyên trách không được thấy)",
      _chan(mcp_hub._safe_read_path, VAULT, str(DAN)))

check("xin tường minh thì đọc được file staging bằng ĐƯỜNG DẪN TUYỆT ĐỐI",
      mcp_hub._safe_read_path(VAULT, str(DAN), cho_phep_staging=True) == DAN.resolve())
check("đọc được bằng TÊN FILE trần (ca đường dẫn của máy khác)",
      mcp_hub._safe_read_path(VAULT, DAN.name, cho_phep_staging=True) == DAN.resolve())

check("file khác trên ổ đĩa vẫn bị chặn dù đã bật staging",
      _chan(mcp_hub._safe_read_path, VAULT, str(NGOAI), cho_phep_staging=True))
check("leo `..` từ staging vẫn bị chặn",
      _chan(mcp_hub._safe_read_path, VAULT, str(STAGE / ".." / "bi-mat.txt"),
            cho_phep_staging=True))
check("thư mục cha của staging vẫn bị chặn",
      _chan(mcp_hub._safe_read_path, VAULT, _TMP, cho_phep_staging=True))
check("file staging KHÔNG tồn tại thì vẫn chặn chứ không trả path ma",
      _chan(mcp_hub._safe_read_path, VAULT, str(STAGE / "khong-co.txt"),
            cho_phep_staging=True))
# Vault luôn thắng: một file trùng tên nằm trong vault phải che file staging, không thì
# staging âm thầm đổi nghĩa của đường dẫn tương đối mà người dùng đang gõ.
(VAULT / DAN.name).write_text("bản trong vault", encoding="utf-8")
check("trùng tên thì file trong VAULT thắng",
      mcp_hub._safe_read_path(VAULT, DAN.name, cho_phep_staging=True) == (VAULT / DAN.name).resolve())
(VAULT / DAN.name).unlink()
check("_safe_path gốc KHÔNG đổi hành vi (ghi vẫn khoá trong vault)",
      _chan(mcp_hub._safe_path, VAULT, str(DAN)))


# ============================================================
# 3) Tool javis_read_file thật, qua đúng đường _builtin_tools
# ============================================================
def _route(staging):
    _t, r = mcp_hub._builtin_tools("full", str(VAULT), staging=staging)
    return r


mo = _route(True)["javis_read_file"]["call"]
dong = _route(False)["javis_read_file"]["call"]

check("bật staging: javis_read_file trả đúng nội dung file vừa dán",
      "đoạn văn dài user vừa dán" in _no(mo({"path": str(DAN)})))
check("bật staging: file trong vault vẫn đọc bình thường",
      "nội dung trong vault" in _no(mo({"path": "Sources/ghi-chu.md"})))

loi = _no(dong({"path": str(DAN)}))
check("tắt staging: từ chối đọc file ngoài brain", loi.startswith("ERROR:"))
check("câu từ chối nói rõ đây là ranh giới brain, không phải lỗi máy",
      "ngoài bộ não" in loi and "khoá tool file trong brain" in loi)

loi_ngoai = _no(mo({"path": str(NGOAI)}))
check("bật staging vẫn từ chối file khác trên ổ đĩa", loi_ngoai.startswith("ERROR:"))

# `_write` để ValueError bay ra; `mcp_client.call_route` bọc nó thành "ERROR: …" trước khi
# tới model. Ở đây gọi thẳng callable nên bắt đúng cái nó ném.
check("ghi file ra staging vẫn bị chặn (chỉ nới cho ĐỌC)",
      _chan(_no, _route(True)["javis_write_file"]["call"]({"path": str(DAN), "content": "x"})))
check("file vừa dán KHÔNG bị ghi đè",
      DAN.read_text(encoding="utf-8") == "đoạn văn dài user vừa dán")


# ============================================================
# 4) Ràng buộc kiến trúc: cờ phải fail-closed và phải nằm trong khoá cache
# ============================================================
check("_builtin_tools mặc định staging=False",
      inspect.signature(mcp_hub._builtin_tools).parameters["staging"].default is False)
check("discover_all mặc định staging=False",
      inspect.signature(mcp_hub.discover_all).parameters["staging"].default is False)

src = Path(SERVER, "mcp_hub.py").read_text(encoding="utf-8")
check("staging nằm trong khoá cache của discover_all (hai lượt khác cờ không dùng chung cache)",
      "bool(force_lazy), lang, bool(staging))" in src)

# Đúng HAI chỗ bật cờ, cả hai nằm trong `_api_stream_mcp` (discover_all + registry_inventory).
# Mọc thêm chỗ thứ ba ở đâu đó - nhất là nhánh bot chuyên trách - là test này đỏ.
main_src = [l for l in Path(SERVER, "main.py").read_text(encoding="utf-8").splitlines()
            if "staging=True" in l and not l.lstrip().startswith("#")]
check("chỉ đường chat của chủ bật staging", len(main_src) == 2)

print()
if _fails:
    print("FAILED (%d): %s" % (len(_fails), ", ".join(_fails)))
    sys.exit(1)
print("ALL PASS")
