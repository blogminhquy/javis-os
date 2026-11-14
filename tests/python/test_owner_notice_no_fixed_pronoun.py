"""Lines the server writes to the owner carry no fixed first person "mình" (GitHub issue 1391).

CLAUDE.md rule 9 (owner, 2026-09-14): Vietnamese address forms follow the user, there is no fixed default. The model
follows a user who set "em" or "anh", but some lines the SERVER builds itself (appended under an answer, pushed to the
chat, sent to the inbox) hardcoded "mình", so the user read them as Javis forgetting their choice. Seen in 0.551.1:

    Mình đang theo dõi việc chạy nền của lượt này:
    - `java 300`

    Xong là mình tự báo về đây, không cần hỏi lại.

Those lines are now written without a personal pronoun. This test reads the source of every module that had one and
fails when a Vietnamese string there says "mình" again ("một mình", "alone", is not a pronoun and passes). Docstrings
are skipped; comments never reach the AST. A model prompt that truly needs the word goes in ALLOW with its reason, and
an ALLOW entry that no longer matches anything fails too, so the list cannot rot.

    python tests/python/test_owner_notice_no_fixed_pronoun.py      (no network, about a second)
"""
from _paths import SERVER  # noqa: E402
import ast
import os
import re
import tempfile
import unicodedata

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-pronoun-test-"))

fails = []


def check(name: str, condition: bool, detail="") -> None:
    print(("ok   " if condition else "FAIL ") + name + ("" if condition else f"  {detail}"))
    if not condition:
        fails.append(name)


# Modules whose owner-facing lines were rewritten for issue 1391. A new module that builds owner notices can join.
FILES = ("main.py", "background_status.py", "memory_receipt.py", "workflow_chat.py", "resonance.py")

# "mình" as a pronoun. "một mình" means "alone" and stays allowed.
FIRST_PERSON = re.compile(r"(?<!một )\bmình\b", re.IGNORECASE)

# (file, snippet that identifies the string) -> why the word may stay. Model prompts only, never an owner-facing line.
ALLOW = {
    ("main.py", "kèm vai của mình"):
        "model prompt: identity block of a team agent, reflexive 'its own role'",
    ("main.py", "kết thúc phần của mình"):
        "model prompt: TEAM_GITHUB_NOTE for team members, reflexive 'their own part'",
}


def _docstring_ids(tree) -> set:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                out.add(id(first.value))
    return out


def string_literals(source: str):
    """(line, text) of every string literal that is not a docstring, f-string pieces included."""
    tree = ast.parse(source)
    docs = _docstring_ids(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            yield node.lineno, unicodedata.normalize("NFC", node.value)


def pronoun_hits(source: str):
    return [(line, text) for line, text in string_literals(source) if FIRST_PERSON.search(text)]


# ---- 1. The scanner itself catches the old wording and skips what it should --------------------------------------
_canary = '''
"""Module docstring: mình không tính."""
def f(x):
    """Docstring: mình không tính."""
    # Comment: mình không tính.
    a = "Mình đang theo dõi việc chạy nền của lượt này:"
    b = f"\\nXong là mình tự báo về đây rồi làm tiếp: {x}"
    c = "Bật AI tự vận hành nếu muốn nó chạy một mình."
    d = "Đang theo dõi việc chạy nền của lượt này:"
    return a, b, c, d
'''
_hits = [t for _l, t in pronoun_hits(_canary)]
check("CANARY: the old background-job lines are caught, plain and f-string",
      len(_hits) == 2 and _hits[0].startswith("Mình đang") and "mình tự báo" in _hits[1], _hits)
check("CANARY: docstrings, comments and 'một mình' are not counted",
      not any("không tính" in t or "một mình" in t for t in _hits), _hits)

# ---- 2. No fixed "mình" in the modules that build owner notices ---------------------------------------------------
used = set()
for name in FILES:
    src = (SERVER / name).read_text(encoding="utf-8")
    bad = []
    for line, text in pronoun_hits(src):
        allowed = [key for key in ALLOW if key[0] == name and key[1] in text]
        if allowed:
            used.update(allowed)
        else:
            bad.append(f"{name}:{line}: {text[:90]!r}")
    check(f"{name}: no hardcoded first-person 'mình' in a string (rewrite without a pronoun, see CLAUDE.md rule 9)",
          not bad, "\n      " + "\n      ".join(bad))

stale = sorted(f"{k[0]}: {k[1]!r}" for k in ALLOW if k not in used)
check("every ALLOW entry still matches a string (drop the ones that no longer do)", not stale, stale)

# ---- 3. The rewritten lines still say what they said, in Vietnamese -----------------------------------------------
import localefmt  # noqa: E402
import background_status  # noqa: E402
import memory_receipt  # noqa: E402
import workflow_chat  # noqa: E402

_token = localefmt.dat_ngon_ngu_yeu_cau("vi")
try:
    promise = background_status.promise_note("off")
    claim = memory_receipt.claim_note()
    not_run = workflow_chat.tin_khong_chay("Viết bài")
finally:
    localefmt.bo_ngon_ngu_yeu_cau(_token)

check("promise note: no pronoun, still says no work was queued and what to reply",
      not FIRST_PERSON.search(promise) and "KHÔNG đặt việc nền nào" in promise
      and "làm luôn" in promise and "giao việc nền" in promise, promise)
check("memory claim note: no pronoun, still says memory did not change",
      not FIRST_PERSON.search(claim) and "không đổi gì" in claim and "nhớ giúp" in claim, claim)
check("workflow 'not run' line: no pronoun, still says it answered instead of running",
      not FIRST_PERSON.search(not_run) and "trả lời thay vì chạy" in not_run and "chạy:" in not_run, not_run)

MAIN = (SERVER / "main.py").read_text(encoding="utf-8")
check("background-job tracking line starts without a pronoun",
      'dong = ["Đang theo dõi việc chạy nền của lượt này:"]' in MAIN)
check("no em dash or en dash in the rewritten lines",
      not any(ch in s for s in (promise, claim, not_run) for ch in ("\u2014", "\u2013")))

if fails:
    raise SystemExit(f"\nFAIL - test_owner_notice_no_fixed_pronoun: {len(fails)} failed")
print("\nOK - test_owner_notice_no_fixed_pronoun: all passed")
