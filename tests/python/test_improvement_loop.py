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

    def test_engine_errors_drop_the_pair_and_too_many_fail_the_run(self):
        def flaky(skill, prompt):
            if "SEALED TASK 0" in prompt:
                raise TimeoutError("slow")
            return solve(skill, prompt)
        result = L.Loop(cases(), solve=flaky, improve=Improver(), check=check).run(BASE, k=1)
        self.assertEqual((result.report["dropped_pairs"], sum(result.report["outcomes"].values())), (2, 5))
        self.assertEqual(result.report["engine_errors"], 4)  # both arms of both repeats, never scored as wrong

        once = []

        def blip(skill, prompt):  # one timeout in a four-case tuning roll: unknown, not wrong, not fatal
            if "TUNING TASK 0" in prompt and not once:
                once.append(1)
                raise TimeoutError("slow")
            return solve(skill, prompt)
        result = L.Loop(cases(), solve=blip, improve=Improver(), check=check).run(BASE, k=1)
        self.assertEqual(result.tuning["base"], 0.0)  # the error row is left out, not counted as a miss
        self.assertEqual(result.chosen, "c1")

        def down(skill, prompt):
            raise ConnectionError("not signed in")
        with self.assertRaises(L.EngineUnavailable):
            L.Loop(cases(), solve=down, improve=Improver(), check=check).run(BASE, k=1)

    def test_early_stop_ends_the_sealed_comparison_once_it_is_clear(self):
        calls = []

        def counting(skill, prompt):
            calls.append(prompt)
            return solve(skill, prompt)
        result = L.Loop(cases(n_qual=10), solve=counting, improve=Improver(), check=check).run(BASE, k=1, early_stop=True)
        sealed = [p for p in calls if p.startswith("SEALED")]
        self.assertEqual((result.report["verdict"], result.report["repeats"], len(sealed)), ("helped", 1, 20))
        self.assertEqual(result.notes["qualification"], "early_stop_after_1")
        calls.clear()
        no_help = L.Loop(cases(n_qual=10), solve=counting, improve=Improver(add="RULE-B"), check=check)
        self.assertEqual(no_help.run(BASE, k=1, early_stop=True).report["verdict"], "keep_base")  # tuning saw nothing
        calls.clear()
        few = L.Loop(cases(n_qual=6), solve=counting, improve=Improver(), check=check).run(BASE, k=1, early_stop=True)
        self.assertEqual((few.report["repeats"], len([p for p in calls if p.startswith("SEALED")])), (2, 24))  # 6 wins: not clear yet

    def test_owner_cancel_stops_the_run(self):
        calls = []

        def counting(skill, prompt):
            calls.append(prompt)
            return solve(skill, prompt)
        with self.assertRaises(L.LoopStopped):
            L.Loop(cases(), solve=counting, improve=Improver(), check=check, width=1,
                   stop=lambda: len(calls) >= 2).run(BASE, k=1)
        self.assertEqual(len(calls), 2)

    def test_a_candidate_equal_to_the_baseline_is_never_chosen(self):
        rolls = iter([0.0] * 4 + [1.0] * 100)  # the re-roll of an unchanged text scores better by chance

        def lucky(skill, prompt):
            return "A" if next(rolls) else "?"

        class Same:
            def __call__(self, instructions):
                current = instructions.split("<current>\n", 1)[1].split("\n</current>", 1)[0]
                return f"<skill>{current}  </skill>"  # whitespace only
        result = L.Loop(cases(), solve=lucky, improve=Same(), check=check, width=1).run(BASE, k=1)
        self.assertEqual((result.chosen, result.report["verdict"]), ("base", "keep_base"))

    def test_case_rules(self):
        bad = cases() + [L.Case("q-dup", "tf0", "qualification", "x", "A")]
        for wrong, reason in ((bad, "family_in_both_splits"), (cases(n_qual=0), "both_splits_required"),
                              (cases() + [cases()[0]], "invalid_cases")):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                L.Loop(wrong, solve=solve, improve=Improver(), check=check)

    def test_a_regression_on_a_case_the_baseline_got_right_refuses_helped(self):
        def row(version, case, repeat, passed):
            return L.Rollout(version, case, repeat, "", passed, 1.0 if passed else 0.0, "", 0.0)
        base = [row("base", f"q{i}", r, i < 2) for i in range(12) for r in (1, 2)]
        cand = [row("c1", f"q{i}", r, i >= 1) for i in range(12) for r in (1, 2)]
        report = L.paired_report(base, cand)
        self.assertEqual((report["outcomes"], report["regressions"]), ({"win": 10, "tie": 1, "loss": 1}, ["q0"]))
        self.assertLess(report["p_value"], 0.05)
        self.assertEqual(report["verdict"], "regression")  # a better total never excuses breaking q0

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
