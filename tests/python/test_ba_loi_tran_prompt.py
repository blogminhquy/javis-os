"""Ba lỗi thật tìm ra khi khảo sát trần prompt (spec 2026-09-nhan-prompt-va-tang-luat).

    python tests/run.py ba_loi_tran_prompt

Không cần pytest, không chạm mạng. Ba lỗi, ba nhóm kiểm:

  1. `AGY_BOOTSTRAP_MAX_CHARS` (compaction.py) và `_tran_argv()` (antigravity_cli.py) mâu
     thuẫn nhau: cộng lại luôn vượt trần dòng lệnh. Máy nào stdin không chạy được thì rơi
     xuống đường file ngữ cảnh, và file càng dài càng dễ bị tool đọc file cắt cụt trước khi
     tới câu hỏi ở cuối (bug đã báo 2026-09-18/19).
  2. Hook `pre_tool_call` chỉ quan sát được, không chặn được lời gọi tool nào.
  3. Skill thứ 21 trở đi vô hình với router, và cái bị cắt là cái tên vần cuối chứ không
     phải cái ít dùng nhất.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-baloi-"))

import compaction  # noqa: E402
import plugins_host  # noqa: E402
import skill_router  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (("  " + detail) if detail else ""))
    if not cond:
        _fails.append(name)


# ============================================================
# 1. Hai hằng số phải KHỚP NHAU, không được mâu thuẫn trong im lặng
# ============================================================
# Đây là rào chặn tái phát cho đúng cái lỗi đã xảy ra: `AGY_BOOTSTRAP_MAX_CHARS` nằm ở
# compaction.py, `_tran_argv()` nằm ở antigravity_cli.py, không ai đặt chúng cạnh nhau, và
# hậu quả (mọi lượt Antigravity đi đường file) thì hoàn toàn im lặng.

BYTE_TREN_KY_TU_VI = 1.21    # đo trên văn bản thật trong docs/dev (1,202), làm tròn lên
BIEN_AN_TOAN = 0.97          # chừa 3% cho binary, cờ, và biến môi trường chiếm chỗ trong ARG_MAX

# Ngân sách cho system prompt. ĐO THẬT 2026-09-22 trên brain mẫu: `build_system_prompt` 37.767
# + khối kênh 8.412 = 46.179 ký tự. Khai 48.000 để chừa biên ~4%.
#
# Cố ý KHAI BẰNG HẰNG SỐ chứ không gọi `build_system_prompt()` lúc chạy test: kích thước thật
# phụ thuộc brain (số ký ức, số skill), nên đo lúc chạy là một test xanh đỏ theo máy. Con số
# ở đây là một CAM KẾT, và `test_prompt_budget.py` là thứ canh cho cam kết đó còn đúng.
SYSPROMPT_NGAN_SACH = 48_000


def _tran_argv_linux():
    """Đọc trần THẬT từ antigravity_cli thay vì chép số, để đổi một chỗ là test bắt được."""
    import antigravity_cli
    cu = os.name
    try:
        # `_tran_argv` đọc os.name lúc gọi (cố ý, xem docstring của nó), nên ép về posix để
        # đo nhánh Linux kể cả khi CI chạy trên Windows.
        os.name = "posix"
        return antigravity_cli._tran_argv()
    finally:
        os.name = cu


_tran = _tran_argv_linux()
_tong_ky_tu = SYSPROMPT_NGAN_SACH + compaction.AGY_BOOTSTRAP_MAX_CHARS
_tong_byte = _tong_ky_tu * BYTE_TREN_KY_TU_VI

check(
    "sysprompt + AGY_BOOTSTRAP lọt trần argv của Linux",
    _tong_byte <= _tran * BIEN_AN_TOAN,
    f"[{SYSPROMPT_NGAN_SACH:,} + {compaction.AGY_BOOTSTRAP_MAX_CHARS:,} = {_tong_ky_tu:,} ký tự "
    f"~ {_tong_byte:,.0f} byte, trần {_tran:,}, ngưỡng {_tran * BIEN_AN_TOAN:,.0f}]",
)

# Sàn: hạ quá tay thì mất ngữ cảnh hội thoại, mà đó là thứ Antigravity vốn đã thiếu vì nó
# KHÔNG nối lại mạch. Trần trên và sàn dưới kẹp con số vào một khoảng có lý do.
check("AGY_BOOTSTRAP không bị hạ quá tay", compaction.AGY_BOOTSTRAP_MAX_CHARS >= 40_000,
      f"[hiện {compaction.AGY_BOOTSTRAP_MAX_CHARS:,}]")

# Env vẫn ghi đè được, và vẫn bị kẹp sàn 20.000 như trước.
check("AGY_BOOTSTRAP đọc được từ env", "JAVIS_AGY_BOOTSTRAP_MAX_CHARS" in
      open(os.path.join(SERVER, "compaction.py"), encoding="utf-8").read())


# ============================================================
# 2. Hook pre_tool_call phải CHẶN được, SỬA được, và fail-open khi hỏng
# ============================================================
def _chay(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _Ctx:
    """Giả lập cái `_load_all` trả về, để khỏi phải dựng cả một plugin thật trên đĩa."""

    def __init__(self, hooks):
        self.hooks = hooks


def _vá_hook(hooks):
    """Thay `_load_all` bằng bản giả. Trả hàm hoàn nguyên."""
    goc = plugins_host._load_all
    plugins_host._load_all = lambda vault_root=None, **kw: {"hooks": hooks}
    return lambda: setattr(plugins_host, "_load_all", goc)


_da_chay = []


async def _base(args):
    _da_chay.append(args)
    return "ĐÃ CHẠY"


# -- 2a. deny thì tool KHÔNG chạy --
_hoan = _vá_hook({"pre_tool_call": [lambda **kw: {"deny": "ghi sai thư mục"}]})
try:
    _da_chay.clear()
    goi = plugins_host.wrap_with_hooks("javis_write_file", _base, "full", None)
    ra = _chay(goi({"path": "Javis/agents/x.md"}))
    check("hook deny thì tool KHÔNG chạy", _da_chay == [], f"[đã chạy {len(_da_chay)} lần]")
    check("hook deny thì model nhận đúng lý do", "ghi sai thư mục" in ra, f"[{ra[:80]}]")
    check("câu báo nói được làm gì tiếp", "làm lại" in ra.lower() or "đừng gọi lại" in ra.lower())
finally:
    _hoan()

# -- 2b. args thì tool chạy với THAM SỐ MỚI --
_hoan = _vá_hook({"pre_tool_call": [lambda **kw: {"args": {"path": "agents/x.md"}}]})
try:
    _da_chay.clear()
    goi = plugins_host.wrap_with_hooks("javis_write_file", _base, "full", None)
    ra = _chay(goi({"path": "Javis/agents/x.md"}))
    check("hook sửa được tham số", _da_chay == [{"path": "agents/x.md"}], f"[{_da_chay}]")
    check("sửa tham số xong tool vẫn chạy", ra == "ĐÃ CHẠY")
finally:
    _hoan()

# -- 2c. hook NÉM LỖI thì tool VẪN chạy (fail-open, cố ý) --
def _hong(**kw):
    raise RuntimeError("plugin của người dùng viết sai")


_hoan = _vá_hook({"pre_tool_call": [_hong]})
try:
    _da_chay.clear()
    goi = plugins_host.wrap_with_hooks("javis_read_file", _base, "full", None)
    ra = _chay(goi({"path": "a.md"}))
    check("hook hỏng KHÔNG khoá được tool (fail-open)", ra == "ĐÃ CHẠY" and len(_da_chay) == 1)
finally:
    _hoan()

# -- 2d. hook trả None thì không ảnh hưởng gì (plugin cũ giữ nguyên hành vi) --
_hoan = _vá_hook({"pre_tool_call": [lambda **kw: None]})
try:
    _da_chay.clear()
    goi = plugins_host.wrap_with_hooks("javis_read_file", _base, "full", None)
    ra = _chay(goi({"path": "a.md"}))
    check("hook trả None thì không đổi gì", ra == "ĐÃ CHẠY" and len(_da_chay) == 1)
finally:
    _hoan()

# -- 2e. hook ĐẦU TIÊN nói deny thì thắng, hook sau không chạy --
_da_goi = []


def _h1(**kw):
    _da_goi.append("h1")
    return {"deny": "không được"}


def _h2(**kw):
    _da_goi.append("h2")
    return None


_hoan = _vá_hook({"pre_tool_call": [_h1, _h2]})
try:
    _da_chay.clear()
    goi = plugins_host.wrap_with_hooks("javis_write_file", _base, "full", None)
    _chay(goi({"path": "x"}))
    check("deny đầu tiên thắng, hook sau không chạy", _da_goi == ["h1"], f"[{_da_goi}]")
finally:
    _hoan()

# -- 2f. post_tool_call VẪN được bắn khi bị chặn (nhật ký không được có lỗ) --
_thay = []
_hoan = _vá_hook({
    "pre_tool_call": [lambda **kw: {"deny": "x"}],
    "post_tool_call": [lambda **kw: _thay.append(kw.get("denied"))],
})
try:
    goi = plugins_host.wrap_with_hooks("javis_write_file", _base, "full", None)
    _chay(goi({"path": "x"}))
    check("lời gọi bị chặn vẫn vào post_tool_call kèm cờ denied", _thay == [True], f"[{_thay}]")
finally:
    _hoan()


# ============================================================
# 3. Router skill: cắt theo ưu tiên và ngân sách, không cắt theo bảng chữ cái
# ============================================================
def _skill(slug, desc="mô tả ngắn"):
    return {"slug": slug, "name": slug, "description": desc, "enabled": True}


# 30 skill tên a00..a29; cái ĐÁNG GIÁ nhất đặt tên vần cuối để bắt đúng lỗi cũ.
_metas = [_skill(f"a{i:02d}") for i in range(30)]
_metas.append(_skill("zzz-hay-dung"))


class _UsageGia:
    @staticmethod
    def read_usage(root):
        return {"zzz-hay-dung": {"use_count": 99, "last_used_at": 1.0, "pinned": False}}


_goc = sys.modules.get("skill_usage")
sys.modules["skill_usage"] = _UsageGia
try:
    _xep = skill_router.xep_theo_uu_tien(_metas, "/khong-co-that")
    check("skill hay dùng được xếp lên ĐẦU dù tên vần cuối",
          _xep[0]["slug"] == "zzz-hay-dung", f"[đầu danh sách: {_xep[0]['slug']}]")

    _hien, _con = skill_router.cat_theo_ngan_sach(_xep)
    check("skill hay dùng KHÔNG bị cắt mất",
          any(s["slug"] == "zzz-hay-dung" for s in _hien))
    check("cắt rồi vẫn báo đúng số còn lại", len(_hien) + _con == len(_metas),
          f"[giữ {len(_hien)}, còn {_con}, tổng {len(_metas)}]")
finally:
    if _goc is not None:
        sys.modules["skill_usage"] = _goc
    else:
        sys.modules.pop("skill_usage", None)

# Ngân sách ký tự phải CHẶN THẬT, và không bao giờ trả danh sách rỗng.
_dai = [_skill(f"b{i:02d}", "x" * 140) for i in range(40)]
_h, _c = skill_router.cat_theo_ngan_sach(_dai)
_tong = sum(len(f"- {s['slug']} ({s['name']}): {s['description']}") + 1 for s in _h)
check("ngân sách ký tự chặn thật", _tong <= skill_router.SKILL_LIST_CHAR_BUDGET,
      f"[{_tong:,} / {skill_router.SKILL_LIST_CHAR_BUDGET:,}]")
check("vượt ngân sách vẫn còn skill bị cắt được báo", _c > 0, f"[còn {_c}]")

_h2, _c2 = skill_router.cat_theo_ngan_sach(_dai, ngan_sach=10)
check("ngân sách bé tí vẫn giữ ít nhất 1 skill", len(_h2) == 1, f"[giữ {len(_h2)}]")

# Brain chưa dùng skill lần nào: thứ tự phải y hệt trước bản này (theo slug).
_chua_dung = [_skill(s) for s in ("c", "a", "b")]
check("brain chưa có dữ liệu dùng thì xếp theo slug",
      [s["slug"] for s in skill_router.xep_theo_uu_tien(_chua_dung, None)] == ["a", "b", "c"])

# Không bao giờ raise, kể cả khi kho đếm hỏng.
class _UsageHong:
    @staticmethod
    def read_usage(root):
        raise OSError("đĩa hỏng")


sys.modules["skill_usage"] = _UsageHong
try:
    check("kho đếm hỏng thì lui về thứ tự cũ, không raise",
          len(skill_router.xep_theo_uu_tien(_chua_dung, "/x")) == 3)
finally:
    if _goc is not None:
        sys.modules["skill_usage"] = _goc
    else:
        sys.modules.pop("skill_usage", None)


print()
if _fails:
    print(f"{len(_fails)} FAIL: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả OK")
