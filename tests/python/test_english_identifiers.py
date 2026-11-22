"""Names in code are English: no NEW Vietnamese function, class, variable, parameter or file name (owner, 2026-11-22).

    python tests/python/test_english_identifiers.py            # check
    python tests/python/test_english_identifiers.py --update   # rewrite the baseline (only to DROP names, see below)

Owner 06/11/2026: "don't use Vietnamese variables, this is an international project". Owner 22/11/2026: "store this rule
hard inside the system: every function and every variable must be English". The rule lives in `docs/quy-uoc-dev.md`
("Tên trong mã viết bằng tiếng Anh"); this test is what makes it hard.

How it works:
- Every name defined in `server/`, `tools/`, `cli/` (Python: functions, classes, parameters, assigned variables) and in
  `dashboard/` (JS: functions, `var`/`let`/`const`, object methods), plus every file name there, is split into words
  (snake_case and camelCase). A name with a word from `VI_WORDS` (Vietnamese syllables that are not English words) is
  Vietnamese.
- Names already in the code on 2026-11-22 are listed in `english_identifiers_baseline.json`. They may stay until a PR
  touches their cluster (rename them then, with every caller and test). Any OTHER Vietnamese name is red.
- Renaming never needs the baseline: a name that is gone simply no longer matches. Do NOT add a new name to the
  baseline to get green; write it in English. `--update` exists to shrink the file after a big rename.

What is NOT a name and stays as it is: text shown on screen (i18n), regexes that match what users type, keys stored in
settings or JSON that other machines read (contracts, renamed only with a migration path), and content in the brain.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).with_name("english_identifiers_baseline.json")

PY_DIRS = ("server", "tools", "cli")
JS_DIRS = ("dashboard",)
SKIP_PARTS = {"__pycache__", "vendor", "node_modules", "i18n", "fonts", "third_party", ".git"}

# Vietnamese syllables (written without diacritics, as they appear in names) that are not English words or common
# abbreviations. Kept to unambiguous ones: "tin", "doc", "so", "ten", "con", "co", "ban", "lay", "bang", "may" are
# English too (as are "hang", "lan", "loc", "den", "doi", "bat", "hop", "lien", "thu", "du", "gan", "chi", "sang", "da",
# "tim", "mau", "dap"), so they are left out rather than risk flagging an English name.
VI_WORDS = frozenset("""
    anh bao bien binh bo buoc giac kien cach canh cau chay chen chieu chinh cho chon chu chua chuan chuyen cua cuoc cuoi dang
    danh dau dich dien dinh doan dong dua duoc duong ghep ghi gia giao gio giong goc goi gom gui hien hieu hinh hoa
    hoc hoi huong kenh khach khi khoa khoi khong khung kiem ket lai lam loai loi luat luc luot luu moi mot muc nang
    ngay nghe ngoai ngu nguoi nguon nhac nhan nhanh nhat nhieu nhom nhung noi nua nut phai phan phien phong quyen
    sach sau sua tach tai tam tao thanh thay them theo thiet thoai thoi thong thuc tien tieng tiep toi trang tre trong
    truoc tu tuoi tuong uu vao ve viec viet voi xem xoa xong xuat
""".split())

_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def words(name: str) -> list:
    out = []
    for part in re.split(r"[_\-.\s]+", name):
        out.extend(w.lower() for w in _CAMEL.findall(part))
    return out


def is_vietnamese(name: str) -> bool:
    return any(w in VI_WORDS for w in words(name))


def _skip(p: Path) -> bool:
    return any(part in SKIP_PARTS for part in p.relative_to(ROOT).parts)


def python_names(src: str) -> set:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
    return names


_JS_DEF = re.compile(
    r"\bfunction\s+([A-Za-z_$][\w$]*)"                       # function name(
    r"|\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)"             # var name
    r"|^\s*([A-Za-z_$][\w$]*)\s*:\s*function\b",             # name: function
    re.M)
_JS_COMMENT = re.compile(r"/\*[\s\S]*?\*/|(?<![:\\\"'])//[^\n]*")


def js_names(src: str) -> set:
    src = _JS_COMMENT.sub("", src)
    return {next(g for g in m.groups() if g) for m in _JS_DEF.finditer(src)}


def scan() -> dict:
    """{relative file: sorted Vietnamese names}; a Vietnamese file name is listed as "<file>"."""
    found = {}
    files = [(p, python_names) for d in PY_DIRS for p in (ROOT / d).rglob("*.py")]
    files += [(p, js_names) for d in JS_DIRS for p in (ROOT / d).rglob("*.js")]
    for path, reader in files:
        if _skip(path):
            continue
        rel = path.relative_to(ROOT).as_posix()
        bad = {n for n in reader(path.read_text(encoding="utf-8", errors="replace")) if is_vietnamese(n)}
        if is_vietnamese(path.stem):
            bad.add("<file>")
        if bad:
            found[rel] = sorted(bad)
    return found


def main() -> int:
    fails = []

    def check(name, cond, detail=""):
        print(("ok   " if cond else "FAIL ") + name + (("  " + detail) if detail and not cond else ""))
        if not cond:
            fails.append(name)

    # The detector itself: it must catch Vietnamese and leave English alone.
    for vi in ("ghi_tin_bot", "veTin", "renderTinKhach", "_su_kien_bot", "lop_nguoi", "don_ao_giac_stt", "chenTin"):
        check(f"detector: '{vi}' is Vietnamese", is_vietnamese(vi))
    for en in ("record_bot_message", "renderMessage", "senderName", "isGenericName", "conversation_id", "doc_text",
               "tin_can", "so_far", "ten_items", "bot_icon", "zalo_delivery", "lay_out", "contentType", "maxRetries"):
        check(f"detector: '{en}' is English", not is_vietnamese(en))

    found = scan()
    if "--update" in sys.argv:
        BASELINE.write_text(json.dumps(found, ensure_ascii=False, indent=0, sort_keys=True) + "\n", encoding="utf-8")
        print(f"baseline written: {sum(len(v) for v in found.values())} names in {len(found)} files")
        return 0
    base = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    check("the baseline exists", bool(base))
    new = {f: [n for n in names if n not in set(base.get(f, []))] for f, names in found.items()}
    new = {f: v for f, v in new.items() if v}
    detail = "; ".join(f"{f}: {', '.join(v[:12])}" for f, v in sorted(new.items()))
    check("no new Vietnamese names (write functions, variables, parameters and files in English)", not new,
          detail + "  -> rename in English (docs/quy-uoc-dev.md). Never add them to the baseline.")
    check("CANARY: the scan really sees the code (old names are still found)", sum(len(v) for v in found.values()) > 50)

    if fails:
        print(f"\nFAIL - test_english_identifiers: {len(fails)}")
        return 1
    print("\nOK - test_english_identifiers: all pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
