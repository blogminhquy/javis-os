"""The order of the brain list (0.431.0, server/brain_order.py).

    python tests/run.py brain_order
"""
import sys

import _paths  # noqa: F401  (puts server/ on sys.path)
import brain_order as bo

loi = 0


def check(ten, ok, chi_tiet=""):
    global loi
    print(("ok   " if ok else "FAIL ") + ten + ("" if ok else "  " + str(chi_tiet)))
    if not ok:
        loi += 1


def b(name, label=None):
    return {"name": name, "label": label or name}


# The user's case: folders sorted one way, labels numbered another.
brains = [b("Brain Default", "1-Tuấn Fernel"), b("crypto", "3-Crypto - Wefi Deone"), b("opc", "4-OPC"),
          b("psc", "2-PSC Advisor")]
got = [x["label"] for x in bo.sort(brains, [])]
check("with no saved order, labels sort the way a person reads them", got == ["1-Tuấn Fernel", "2-PSC Advisor",
                                                                              "3-Crypto - Wefi Deone", "4-OPC"], got)

got = [x["label"] for x in bo.sort([b("a", "10-x"), b("b", "2-y"), b("c", "Ảnh"), b("d", "an")], [])]
check("numbers by value, accents and case ignored", got == ["2-y", "10-x", "an", "Ảnh"], got)

got = [x["name"] for x in bo.sort(brains, ["opc", "Brain Default"])]
check("the saved order comes first, the rest by label", got == ["opc", "Brain Default", "psc", "crypto"], got)

got = [x["name"] for x in bo.sort(brains, ["gone", "psc"])]
check("a brain that no longer exists in the saved order is skipped", got[0] == "psc" and len(got) == 4, got)

check("clean drops paths, blanks and duplicates",
      bo.clean(["a", "a", "", "../x", "x/y", "..", "b", 5]) == ["a", "b", "5"], bo.clean(["a", "a", "", "../x", "x/y", "..", "b", 5]))
check("clean refuses a non-list", bo.clean("abc") == [] and bo.clean(None) == [])
check("clean caps the list", len(bo.clean([str(i) for i in range(bo.MAX_ITEMS + 50)])) == bo.MAX_ITEMS)

if loi:
    print(f"FAIL - test_brain_order: {loi} loi")
    sys.exit(1)
print("OK - test_brain_order: tất cả pass")
