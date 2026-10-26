"""Self-learning loop over fake engines: shape, evidence boundary, baseline rule, fallback, paired report."""
from _paths import ROOT, SERVER  # noqa: F401

import unittest

import improvement_loop as L


def cases(n_tuning=4, n_qual=6):
    out = [L.Case(f"t{i}", f"tf{i}", "tuning", f"TUNING TASK {i} needs RULE-A", "A") for i in range(n_tuning)]
    out += [L.Case(f"q{i}", f"qf{i}", "qualification", f"SEALED TASK {i} needs RULE-A", "A") for i in range(n_qual)]
    return out


def solve(skill, prompt):
    return "A" if "RULE-A" in skill else "?"


def check(case, output):
    ok = output.strip() == case.answer
    return {"pass": ok, "score": 1.0 if ok else 0.0, "feedback": "correct" if ok else f"expected {case.answer}"}


class Improver:
    def __init__(self, add="RULE-A", broken=0):
        self.seen, self.add, self.broken = [], add, broken

    def __call__(self, instructions):
        self.seen.append(instructions)
        if self.broken:
            self.broken -= 1
            return "no tags here"
        current = instructions.split("<current>\n", 1)[1].split("\n</current>", 1)[0]
        return f"<skill>{current}\nAlways apply {self.add}.</skill>"


BASE = "Match the records and answer with the code."


class LoopTests(unittest.TestCase):
    def test_sequential_shape_and_choice(self):
        improver = Improver()
        loop = L.Loop(cases(), solve=solve, improve=improver, check=check, width=2)
        result = loop.run(BASE, k=1, qualification_repeats=2)
        self.assertEqual(list(result.tuning), ["base", "inv1", "dom1", "c1"])
        self.assertEqual(result.chosen, "c1")  # equal scores prefer the composition, both beat the baseline
        self.assertEqual(result.report["verdict"], "helped")
        self.assertEqual(result.report["outcomes"], {"win": 6, "tie": 0, "loss": 0})
        self.assertEqual(result.calls, {"solve": 4 * 4 + 6 * 2 * 2, "improve": 3})

    def test_improver_never_sees_qualification(self):
        improver = Improver()
        L.Loop(cases(), solve=solve, improve=improver, check=check).run(BASE, k=2)
        self.assertTrue(improver.seen)
        self.assertFalse(any("SEALED TASK" in text for text in improver.seen))
        self.assertTrue(any("TUNING TASK" in text for text in improver.seen))

    def test_baseline_kept_when_nothing_beats_it(self):
        improver = Improver(add="RULE-B")  # a change that does not fix the failure
        result = L.Loop(cases(), solve=solve, improve=improver, check=check).run(BASE, k=1)
        self.assertEqual((result.chosen, result.report["verdict"]), ("base", "keep_base"))
        self.assertEqual(result.qualification, [])  # no sealed case spent without a candidate

    def test_bad_improver_output_retries_then_falls_back(self):
        improver = Improver(broken=10)
        result = L.Loop(cases(), solve=solve, improve=improver, check=check).run(BASE, k=1)
        self.assertTrue(all(note.startswith("fell_back") for note in result.notes.values()))
        self.assertEqual(result.versions["c1"], BASE)
        self.assertEqual(result.calls["improve"], 6)  # one retry per stage

    def test_engine_error_is_a_failed_row_not_a_crash(self):
        def flaky(skill, prompt):
            if "TASK 0" in prompt:
                raise TimeoutError("slow")
            return solve(skill, prompt)
        result = L.Loop(cases(), solve=flaky, improve=Improver(), check=check).run(BASE, k=1)
        self.assertEqual(result.report["outcomes"]["tie"], 1)  # q0 fails on both arms

    def test_case_rules(self):
        bad = cases() + [L.Case("q-dup", "tf0", "qualification", "x", "A")]
        for wrong, reason in ((bad, "family_in_both_splits"), (cases(n_qual=0), "both_splits_required"),
                              (cases() + [cases()[0]], "invalid_cases")):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                L.Loop(wrong, solve=solve, improve=Improver(), check=check)

    def test_sign_test_and_skill_extraction(self):
        self.assertAlmostEqual(L.sign_test(6, 0), 0.03125)
        self.assertEqual(L.sign_test(0, 0), 1.0)
        self.assertGreater(L.sign_test(4, 2), 0.05)
        self.assertEqual(L.extract_skill("x <skill>  a long enough skill text </skill> y"), "a long enough skill text")
        for bad in ("none", "<skill>short</skill>"):
            with self.assertRaises(ValueError):
                L.extract_skill(bad)


if __name__ == "__main__":
    unittest.main()
