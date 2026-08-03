"""Chặn lỗi biến chưa gán / tên không tồn tại - loại lỗi CI cũ không thấy nổi.

    python tests/run.py bien_chua_gan

Vì sao có file này. Bản 0.13.0 thêm bộ đếm token mỗi lượt: `_ctx_in = 0` khai trong `_do_turn`,
rồi `_ctx_in += ...` ở ba nhánh engine. Hai nhánh cộng thẳng trong `_do_turn` nên chạy tốt.
Nhánh Codex (gói ChatGPT) cộng bên trong hàm con `_consume_codex`, mà hàm con đó chỉ khai
`nonlocal final_text`. Thiếu `_ctx_in` trong dòng nonlocal là Python coi nó thành biến CỤC BỘ
của hàm con, nên `+=` đọc một biến chưa gán:

    UnboundLocalError: cannot access local variable '_ctx_in' where it is not associated with a value

Nó nổ đúng lúc Codex vừa trả lời xong, nên MỌI lượt chat qua gói ChatGPT đều hỏng: câu trả lời
đã stream ra màn hình không được lưu, người dùng chỉ còn thấy "Lỗi xử lý". Cùng bản đó, hàm
`push_to_chat` (đường đẩy kết quả việc nền về khung chat web) ghi log lỗi bằng `sys.stderr`
trong khi `sys` chưa hề được import - một NameError nằm phục sẵn trong nhánh `except`, tức là
chỉ nổ khi đã có sự cố khác, và biến việc "ghi log rồi chạy tiếp" thành vỡ luôn cả đường báo.

Vì sao CI không bắt được: byte-compile chạy qua cả hai chỗ mà không kêu ca gì (cú pháp đúng
tuyệt đối), còn `import main` chỉ nạp module chứ không gọi vào thân hàm. Test kiểu grep cũng
mù: chúng đếm được `_ctx_in +=` xuất hiện ba lần, mà ba lần đó vẫn còn nguyên khi lỗi đang xảy
ra. Chỉ có đọc SCOPE mới thấy.

File này quét bằng ast + symtable của thư viện chuẩn (không cần cài thêm gì), tìm hai lớp lỗi:

  1. Hàm con `+=` vào biến của hàm cha mà quên `nonlocal` -> UnboundLocalError.
  2. Hàm dùng một tên toàn cục không hề tồn tại ở scope module -> NameError.

Cuối file có phần TỰ KIỂM: cố tình dựng lại đúng hai đoạn mã hỏng và bắt bộ quét phải kêu.
Không có phần đó thì một bộ quét bị hỏng thầm lặng vẫn cho ra "0 lỗi" và test vẫn xanh.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import ast
import builtins
import symtable
import sys

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# Thư mục mã chạy thật. tests/ cố tình KHÔNG nằm trong này: test hay dùng mẹo scope cho gọn,
# mà chúng chỉ hỏng chính nó chứ không hỏng máy chủ của người dùng.
CAY_MA = [SERVER, ROOT / "system" / "plugins", ROOT / "tools"]

_TEN_SAN = set(dir(builtins)) | {
    "__file__", "__name__", "__doc__", "__package__", "__spec__",
    "__loader__", "__builtins__", "__debug__",
}


# ============================================================
# Bộ quét 1: hàm con `+=` vào biến hàm cha mà thiếu nonlocal
# ============================================================
class _Scope:
    def __init__(self, node, cha):
        self.node, self.cha, self.con = node, cha, []
        self.gan = set()        # tên bị GÁN trong hàm này (=> Python coi là local)
        self.khai = set()       # nonlocal / global
        self.tham_so = set()
        self.cong_don = []      # (tên, dòng) của `+=`, `-=`...
        if cha is not None:
            cha.con.append(self)


def _thu_scope(node, cha=None):
    sc = _Scope(node, cha)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        a = node.args
        for arg in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs):
            sc.tham_so.add(arg.arg)
        if a.vararg:
            sc.tham_so.add(a.vararg.arg)
        if a.kwarg:
            sc.tham_so.add(a.kwarg.arg)

    def di(n):
        for con in ast.iter_child_nodes(n):
            if isinstance(con, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sc.gan.add(con.name)
                _thu_scope(con, sc)
                continue
            if isinstance(con, ast.Lambda):
                continue            # lambda không gán được tên, bỏ qua cho gọn
            if isinstance(con, ast.ClassDef):
                sc.gan.add(con.name)
                continue
            if isinstance(con, (ast.Nonlocal, ast.Global)):
                sc.khai.update(con.names)
            elif isinstance(con, ast.AugAssign) and isinstance(con.target, ast.Name):
                sc.gan.add(con.target.id)
                sc.cong_don.append((con.target.id, con.lineno))
            elif isinstance(con, (ast.Assign, ast.AnnAssign, ast.For, ast.AsyncFor,
                                  ast.With, ast.AsyncWith, ast.NamedExpr)):
                for t in ast.walk(con):
                    if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store):
                        sc.gan.add(t.id)
            di(con)

    di(node)
    return sc


def _soi_cong_don(sc, ten_file, ra):
    for ten, dong in sc.cong_don:
        if ten in sc.khai or ten in sc.tham_so:
            continue
        cha = sc.cha
        while cha is not None:
            if ten in cha.gan or ten in cha.tham_so:
                ra.append(f"{ten_file}:{dong} '{ten}' trong "
                          f"{getattr(sc.node, 'name', '<module>')}() cộng dồn vào biến của "
                          f"{getattr(cha.node, 'name', '<module>')}() mà thiếu nonlocal")
                break
            cha = cha.cha
    for con in sc.con:
        _soi_cong_don(con, ten_file, ra)


def quet_nonlocal(nguon: str, ten_file: str) -> list:
    ra = []
    _soi_cong_don(_thu_scope(ast.parse(nguon)), ten_file, ra)
    return ra


# ============================================================
# Bộ quét 2: tên toàn cục không tồn tại
# ============================================================
def _di_symtable(st, ten_module, ten_file, ra):
    if st.get_type() != "module":
        for sym in st.get_symbols():
            # is_global + không assigned = đọc một tên toàn cục. Nếu tên đó không có ở
            # scope module và cũng không phải builtin thì chạy tới là NameError.
            if sym.is_global() and not sym.is_assigned():
                ten = sym.get_name()
                if ten not in ten_module and ten not in _TEN_SAN:
                    ra.append(f"{ten_file}: {st.get_name()}() dùng tên '{ten}' "
                              f"không có ở scope module (quanh dòng {st.get_lineno()})")
    for con in st.get_children():
        _di_symtable(con, ten_module, ten_file, ra)


def quet_ten_toan_cuc(nguon: str, ten_file: str) -> list:
    ra = []
    st = symtable.symtable(nguon, ten_file, "exec")
    _di_symtable(st, {s.get_name() for s in st.get_symbols()}, ten_file, ra)
    return ra


# ============================================================
# 1. TỰ KIỂM bộ quét - phải kêu đúng trên hai đoạn mã đã từng hỏng thật
# ============================================================
_MAU_HONG_NONLOCAL = '''
async def _do_turn():
    _ctx_in = 0
    final_text = ""

    async def _consume_codex(prompt):
        nonlocal final_text
        _ctx_in += 5
    await _consume_codex("x")
'''
_MAU_LANH_NONLOCAL = '''
async def _do_turn():
    _ctx_in = 0
    final_text = ""

    async def _consume_codex(prompt):
        nonlocal final_text, _ctx_in
        _ctx_in += 5
    await _consume_codex("x")
'''
_MAU_HONG_TEN = '''
def luu(x):
    return x


def push_to_chat(x):
    try:
        luu(x)
    except Exception as e:
        print(e, file=sys.stderr)
'''
_MAU_LANH_TEN = '''
import sys


def luu(x):
    return x


def push_to_chat(x):
    try:
        luu(x)
    except Exception as e:
        print(e, file=sys.stderr)
'''

check("bộ quét TÌM RA lỗi thiếu nonlocal (đúng lỗi 0.13.0)",
      len(quet_nonlocal(_MAU_HONG_NONLOCAL, "mau")) == 1)
check("và IM khi đã khai nonlocal",
      quet_nonlocal(_MAU_LANH_NONLOCAL, "mau") == [])
check("bộ quét TÌM RA tên toàn cục không tồn tại",
      any("'sys'" in d for d in quet_ten_toan_cuc(_MAU_HONG_TEN, "mau")))
check("và IM khi tên đã được import",
      quet_ten_toan_cuc(_MAU_LANH_TEN, "mau") == [])
# Tên cục bộ, tham số, biến vòng lặp... không được bị kêu oan - bộ quét mà kêu bừa thì
# lần sau người ta tắt nó đi, và thế là mất luôn hàng rào.
check("không kêu oan biến cục bộ bình thường",
      quet_nonlocal("def f():\n    n = 0\n    for i in [1]:\n        n += i\n    return n", "m") == []
      and quet_ten_toan_cuc("def f(a, *b, **c):\n    d = a\n    return [d for _ in b] + list(c)",
                            "m") == [])


# ============================================================
# 2. Quét mã thật
# ============================================================
_file_ma = []
for goc in CAY_MA:
    if goc.is_dir():
        _file_ma += sorted(p for p in goc.rglob("*.py") if "__pycache__" not in p.parts)
check("tìm thấy cây mã nguồn để quét", len(_file_ma) > 20)

_loi_nonlocal, _loi_ten, _loi_cu_phap = [], [], []
for p in _file_ma:
    ten = str(p.relative_to(ROOT))
    try:
        nguon = p.read_text(encoding="utf-8")
    except Exception as e:
        _loi_cu_phap.append(f"{ten}: không đọc được ({type(e).__name__})")
        continue
    try:
        _loi_nonlocal += quet_nonlocal(nguon, ten)
        _loi_ten += quet_ten_toan_cuc(nguon, ten)
    except SyntaxError as e:
        _loi_cu_phap.append(f"{ten}: cú pháp hỏng dòng {e.lineno}")

for d in _loi_nonlocal + _loi_ten + _loi_cu_phap:
    print("     -> " + d)
check("không file nguồn nào hỏng cú pháp", not _loi_cu_phap)
check("không hàm con nào cộng dồn vào biến hàm cha mà quên nonlocal", not _loi_nonlocal)
check("không hàm nào dùng tên toàn cục không tồn tại", not _loi_ten)


# ============================================================
# 3. Ghim đúng hai chỗ đã sửa - để ai gỡ ra là biết ngay
# ============================================================
_MAIN = (SERVER / "main.py").read_text(encoding="utf-8")
check("CANARY: _consume_codex khai nonlocal cả _ctx_in",
      "nonlocal final_text, _ctx_in" in _MAIN)
check("CANARY: main.py import sys ở mức module",
      any(d.strip() == "import sys" for d in _MAIN.split("\n")[:60]))

print(("\nFAILED: " + ", ".join(_fails)) if _fails else "\nAll passed")
sys.exit(1 if _fails else 0)
