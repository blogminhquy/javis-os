"""Brain đẻ song song hai thư mục `memory` và `Memory` - ký ức rơi vào bản hoa thì MẤT.

    python tests/run.py memory_hoa_thuong

LỖI THẬT (người dùng báo 06/09/2026)
Trên VPS Linux, brain "Brain Default" có ĐỒNG THỜI `memory/` và `Memory/`. Lúc 11:37 trợ lý
ghi một ký ức về skill `sangtactho68` vào `Memory/facts/`, và ký ức đó biến mất khỏi Javis.

Vì sao mất, theo đúng thứ tự:

1. Linux phân biệt hoa thường nên đó là HAI thư mục thật sự khác nhau. Trên máy Mac thì
   không - nên lỗi này không bao giờ lộ ra lúc chạy thử ở máy dev.
2. Tài liệu của chính Javis dạy sai đường: `CLAUDE.md` và `SCHEMA_SEED` (ghi thành AGENTS.md
   trong MỌI brain) đều viết `Memory/` hoa, trong khi mọi đường đọc lấy `memory/` thường.
   Model làm theo tài liệu là ghi vào đúng chỗ không ai đọc.
3. `_brain_memory_dir` ưu tiên bản thường, nên chỉ mục nạp vào prompt mỗi lượt không có dòng
   đó, `memory_index` cũng không thấy.
4. `/brain/migrate` từ chối gộp với lý do "memory đã tồn tại - bỏ qua", tức đúng ca hỏng này
   là ca duy nhất nó không chịu chữa.
5. Bảng Cấu trúc khớp tên thư mục KHÔNG phân biệt hoa thường, nên nó báo "có memory" và còn
   chỉ vào bản nào `os.listdir` trả trước - có thể chính là bản đang bị bỏ quên.

Kết quả: ghi xong, mất luôn, không một dòng lỗi. Đây là loại lỗi test phải bắt chứ không
phải người phải nhớ.

Kèm một lỗi họ hàng cùng gốc: `learn._brain_last_active` đóng đinh `Memory/conversations`
chữ hoa, nên brain hiện đại luôn trả 0.0 và bộ lọc "bỏ brain đã nguội" của curator không bao
giờ nổ - chết câm đúng việc mà chú thích của nó nói nó sinh ra để làm.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import shutil
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-memcase-")
os.environ.setdefault("JAVIS_STATE_DIR", _TMP)

import main  # noqa: E402
import learn  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def _brain(ten: str) -> Path:
    root = Path(_TMP) / ten
    (root / "memory" / "facts").mkdir(parents=True, exist_ok=True)
    (root / "memory" / "conversations").mkdir(parents=True, exist_ok=True)
    return root


def _doc(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


# Máy chạy test có phân biệt hoa thường không? macOS/Windows thì không, và ở đó lỗi này
# KHÔNG tồn tại - nên các bài dưới phải tự bỏ qua chứ không được báo đỏ oan.
_probe = Path(_TMP) / "_probe"
(_probe / "memory").mkdir(parents=True, exist_ok=True)
PHAN_BIET_HOA_THUONG = not (_probe / "Memory").is_dir()
print(f"(hệ thống file {'PHÂN BIỆT' if PHAN_BIET_HOA_THUONG else 'KHÔNG phân biệt'} hoa thường)")


# ── 1. Ca gốc: ký ức ghi nhầm vào Memory/ phải quay về, không mất chữ nào ──────────────
if PHAN_BIET_HOA_THUONG:
    root = _brain("brain-ca-goc")
    (root / "memory" / "MEMORY.md").write_text(
        "- [Xưng hô](memory/facts/xung-ho.md) - dùng bạn/mình\n", encoding="utf-8")
    (root / "memory" / "facts" / "xung-ho.md").write_text("bạn/mình\n", encoding="utf-8")
    # Bản ghi nhầm lúc 11:37
    (root / "Memory" / "facts").mkdir(parents=True)
    (root / "Memory" / "facts" / "skill-sangtactho68.md").write_text(
        "skill viết thơ lục bát\n", encoding="utf-8")
    (root / "Memory" / "MEMORY.md").write_text(
        "- [Skill sáng tác thơ](Memory/facts/skill-sangtactho68.md) - lục bát\n", encoding="utf-8")

    mem = main._brain_memory_dir(str(root))
    idx = _doc(mem / "MEMORY.md")

    check("CANARY ca gốc: ký ức ghi vào Memory/ hoa quay lại được chỉ mục nạp vào prompt",
          "sangtactho68" in idx)
    check("nội dung fact còn nguyên, không phải chỉ có cái tên",
          "lục bát" in _doc(mem / "facts" / "skill-sangtactho68.md"))
    check("ký ức cũ trong memory/ thường không bị bản đến đè mất",
          "xung-ho.md" in idx and _doc(mem / "facts" / "xung-ho.md").strip() == "bạn/mình")
    check("link trong chỉ mục đổi Memory/ -> memory/ cho khớp chỗ file vừa dời tới",
          "(memory/facts/skill-sangtactho68.md)" in idx and "(Memory/" not in idx)
    check("thư mục Memory/ hoa được dọn đi, không để lại vỏ rỗng gây hiểu nhầm",
          not (root / "Memory").exists())
    check("bộ nhớ sau khi gộp vẫn là bản thường", mem.name == "memory")

    # Chạy lại phải vô hại (mỗi lượt chat đều gọi hàm này).
    lan2 = main._brain_memory_dir(str(root))
    check("gọi lại lần nữa không nhân bản dòng chỉ mục",
          _doc(lan2 / "MEMORY.md").count("sangtactho68") == 1)


# ── 2. Trùng tên file: KHÔNG được đè, mất một ký ức là hỏng hơn thừa một file ──────────
if PHAN_BIET_HOA_THUONG:
    root = _brain("brain-trung-ten")
    (root / "memory" / "facts" / "cach-lam-viec.md").write_text("BẢN THƯỜNG\n", encoding="utf-8")
    (root / "Memory" / "facts").mkdir(parents=True)
    (root / "Memory" / "facts" / "cach-lam-viec.md").write_text("BẢN HOA\n", encoding="utf-8")

    mem = main._brain_memory_dir(str(root))
    con_lai = sorted(p.name for p in (mem / "facts").glob("*.md"))
    noi_dung = {_doc(p).strip() for p in (mem / "facts").glob("*.md")}

    check("trùng tên nhưng nội dung KHÁC thì giữ cả hai bản", len(con_lai) == 2)
    check("CANARY: không bản nào bị đè mất", noi_dung == {"BẢN THƯỜNG", "BẢN HOA"})
    check("bản đến được đổi tên có ghi rõ nó từ đâu tới",
          any("Memory" in n for n in con_lai))

    # Nội dung TRÙNG KHÍT thì không được đẻ ra rác.
    root = _brain("brain-trung-khit")
    (root / "memory" / "facts" / "a.md").write_text("y hệt\n", encoding="utf-8")
    (root / "Memory" / "facts").mkdir(parents=True)
    (root / "Memory" / "facts" / "a.md").write_text("y hệt\n", encoding="utf-8")
    mem = main._brain_memory_dir(str(root))
    check("nội dung trùng khít từng byte thì bỏ bản thừa, không sinh file rác",
          [p.name for p in (mem / "facts").glob("*.md")] == ["a.md"]
          and not (root / "Memory").exists())


# ── 3. Brain CŨ chỉ có Memory/ hoa: đó là bố cục hợp lệ, tuyệt đối không đụng ──────────
root = Path(_TMP) / "brain-cu"
(root / "Memory" / "facts").mkdir(parents=True)
(root / "Memory" / "facts" / "cu.md").write_text("ký ức cũ\n", encoding="utf-8")
(root / "Memory" / "MEMORY.md").write_text("- [Cũ](Memory/facts/cu.md)\n", encoding="utf-8")
mem = main._brain_memory_dir(str(root))
check("brain cũ chỉ có Memory/ hoa vẫn dùng đúng thư mục đó, không bị ép đổi",
      mem.name == "Memory" and mem.is_dir())
check("brain cũ không mất ký ức nào", _doc(mem / "facts" / "cu.md").strip() == "ký ức cũ")
check("brain cũ không bị đẻ thêm memory/ thường trống bên cạnh",
      not (root / "memory").is_dir() or not PHAN_BIET_HOA_THUONG)


# ── 4. Hai tên trỏ MỘT thư mục (macOS, hoặc symlink): "gộp" là tự dẫm chân lên mình ────
root = _brain("brain-symlink")
(root / "memory" / "facts" / "x.md").write_text("một bản duy nhất\n", encoding="utf-8")
try:
    (root / "Memory").symlink_to(root / "memory", target_is_directory=True)
    tao_duoc_symlink = True
except (OSError, NotImplementedError):
    tao_duoc_symlink = False
if tao_duoc_symlink:
    mem = main._brain_memory_dir(str(root))
    check("CANARY: hai tên trỏ cùng một thư mục thì KHÔNG gộp, file không bốc hơi",
          _doc(mem / "facts" / "x.md").strip() == "một bản duy nhất")


# ── 5. Bảng Cấu trúc phải chỉ đúng thư mục app THẬT SỰ đọc ────────────────────────────
if PHAN_BIET_HOA_THUONG:
    root = _brain("brain-bang-cau-truc")
    (root / "Memory").mkdir(parents=True, exist_ok=True)
    hang = next(i for i in main._check_structure(root) if i["key"] == "memory")
    check("bảng Cấu trúc chỉ vào bản chuẩn chữ thường, không vào bản đang bị bỏ quên",
          hang["present"] and hang["where"] == "memory")
    # Và nó phải khớp với thứ _thu_muc_bo_nho trả về - hai nơi nói hai kiểu là mầm lỗi này.
    check("CANARY: bảng Cấu trúc và _thu_muc_bo_nho nói cùng một thư mục",
          hang["where"] == main._thu_muc_bo_nho(root).name)

# Vault dùng chữ hoa kiểu cũ (chỉ có Memory/) vẫn phải được nhận là "có bộ nhớ".
root2 = Path(_TMP) / "brain-bang-cu"
(root2 / "Memory").mkdir(parents=True)
hang2 = next(i for i in main._check_structure(root2) if i["key"] == "memory")
check("vault chỉ có Memory/ hoa vẫn được tính là có bộ nhớ (không báo thiếu oan)",
      hang2["present"])


# ── 6. Không còn chỗ nào trong sản phẩm DẠY đường chữ hoa ─────────────────────────────
_claude_md = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
check("CANARY: CLAUDE.md không còn dạy đường brain/Memory/ chữ hoa",
      "brain/Memory/" not in _claude_md)
check("CLAUDE.md có nói thẳng rằng tên thư mục là chữ thường",
      "memory" in _claude_md and "lowercase" in _claude_md)
check("CANARY: AGENTS.md seed vào mọi brain không còn ghi `Memory/`",
      "`Memory/`" not in main.SCHEMA_SEED and "`memory/`" in main.SCHEMA_SEED)

# Chỉ mục bộ nhớ khi bị rút gọn có kèm lời chỉ đường đọc tiếp - đường đó phải đúng.
_dai = "\n".join(f"- [Ký ức {i}](memory/facts/k{i}.md) - {'mô tả dài ' * 40}" for i in range(400))
_rut = main._fit_memory_index(_dai, cap=20000)
check("CANARY: lời chỉ đường trong chỉ mục rút gọn trỏ memory/ thường, không phải Memory/",
      "Memory/" not in _rut)


# ── 7. Lỗi họ hàng: bộ lọc brain nguội của curator đóng đinh chữ hoa nên chết câm ──────
class _Deps:
    def __init__(self, root):
        self._root = root

    def brain_root(self, brain):
        return str(self._root)


_lf = learn.LearnFeature.__new__(learn.LearnFeature)
root = _brain("brain-curator")
(root / "memory" / "conversations" / "2026-09-06.md").write_text("hội thoại\n", encoding="utf-8")
_lf.deps = _Deps(root)
check("CANARY: brain hiện đại (memory/ thường) đo được lần cuối trò chuyện, không trả 0.0",
      learn.LearnFeature._brain_last_active(_lf, "brain") > 0)

root_cu = Path(_TMP) / "brain-curator-cu"
(root_cu / "Memory" / "conversations").mkdir(parents=True)
(root_cu / "Memory" / "conversations" / "2026-09-06.md").write_text("hội thoại\n", encoding="utf-8")
_lf.deps = _Deps(root_cu)
check("brain cũ (Memory/ hoa) vẫn đo được như trước, không phá bản cũ",
      learn.LearnFeature._brain_last_active(_lf, "brain") > 0)

_lf.deps = _Deps(Path(_TMP) / "brain-khong-ton-tai")
check("brain không có thư mục hội thoại vẫn trả 0.0 chứ không nổ",
      learn.LearnFeature._brain_last_active(_lf, "brain") == 0.0)


shutil.rmtree(_TMP, ignore_errors=True)
print(("FAILED: " + ", ".join(_fails)) if _fails else "ALL OK")
sys.exit(1 if _fails else 0)
