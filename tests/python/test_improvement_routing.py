"""M4 routing surface: description-only patches and the deterministic lazy-router evaluator."""
from _paths import ROOT, SERVER  # noqa: F401

import unittest

import improvement_routing as R

SKILL = (b"---\nname: Bao cao doi soat\ndescription: Lap bao cao tong hop\ngroup: Finance\n---\n"
         b"# Body\nReconcile rows.\n")


def manifests(**descriptions):
    base = {"bao-cao": "Lap bao cao tong hop", "viet-email": "Soan thu gui khach hang",
            "lich-hop": "Xep lich hop voi doi tac"}
    base.update(descriptions)
    return [{"slug": slug, "name": slug, "description": text, "group": "Chung"} for slug, text in base.items()]


class PatchDescriptionTests(unittest.TestCase):
    def test_only_the_description_value_changes(self):
        patched = R.patch_description(SKILL, "Doi soat ma hang va so tien giua hai bang")
        self.assertTrue(patched.startswith(b"---\nname: Bao cao doi soat\ndescription: \"Doi soat ma hang"))
        self.assertTrue(patched.endswith(b"group: Finance\n---\n# Body\nReconcile rows.\n"))

    def test_crlf_files_keep_their_line_endings(self):
        raw = SKILL.replace(b"\n", b"\r\n")
        patched = R.patch_description(raw, "Doi soat bang so lieu")
        self.assertNotIn(b"\n", patched.replace(b"\r\n", b""))
        self.assertTrue(patched.endswith(b"# Body\r\nReconcile rows.\r\n"))

    def test_refuses_what_it_cannot_edit_safely(self):
        cases = {
            "missing": b"---\nname: x\n---\nBody\n",
            "block": b"---\nname: x\ndescription: |\n  long text\n---\nBody\n",
            "continued": b"---\nname: x\ndescription: first\n  second line\n---\nBody\n",
            "twice": b"---\ndescription: a\ndescription: b\n---\nBody\n",
            "no-frontmatter": b"Body only\n",
        }
        for name, raw in cases.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                R.patch_description(raw, "Doi soat bang so lieu")
        for bad in ("", "x" * 151, "Kích hoạt khi người dùng muốn báo cáo"):
            with self.subTest(bad=bad[:20]), self.assertRaises(ValueError):
                R.patch_description(SKILL, bad)


class RoutingEvaluatorTests(unittest.TestCase):
    def test_route_matches_lazy_router_decisions(self):
        self.assertEqual(R.route("viet email cho khach hang", manifests())["slug"], "viet-email")
        self.assertEqual(R.route("thoi tiet hom nay the nao", manifests())["action"], "none")

    def test_labels_cover_every_outcome(self):
        load = {"action": "load", "slug": "a"}
        self.assertEqual(R.label({"expected": "a"}, load), "correct")
        self.assertEqual(R.label({"expected": "b"}, load), "wrong_skill")
        self.assertEqual(R.label({"expected": ""}, load), "unnecessary")
        self.assertEqual(R.label({"expected": "a"}, {"action": "none", "slug": ""}), "missed")
        self.assertEqual(R.label({"expected": ""}, {"action": "none", "slug": ""}), "correct")
        self.assertEqual(R.label({"expected": "a"}, {"action": "fallback", "slug": ""}), "deferred")

    def test_better_description_wins_positive_cases_without_regressions(self):
        cases = [{"query": q, "expected": "bao-cao", "kind": "positive"} for q in (
            "doi soat ma hang giua hai bang", "doi soat so tien thanh toan", "doi soat don hang ton kho",
            "doi soat cong no khach hang", "doi soat hoa don nha cung cap")]
        cases += [{"query": "thoi tiet hom nay", "expected": "", "kind": "negative"},
                  {"query": "soan thu cam on khach hang", "expected": "viet-email", "kind": "competing"}]
        report = R.evaluate(cases, manifests(), "bao-cao", "Doi soat ma hang, so tien, don hang, cong no, hoa don")
        self.assertEqual(report["outcomes"]["win"], 5)
        self.assertEqual(report["required_loss_count"], 0)
        self.assertEqual(report["mechanical_verdict"], "eligible")
        self.assertEqual(report["native_cli_routing"], "not_measured")
        self.assertEqual(report["business_eligibility"], "unverified")

    def test_description_that_steals_another_skill_is_rejected(self):
        cases = [{"query": "gui thu cam on khach hang", "expected": "viet-email", "kind": "competing"}]
        self.assertEqual(R.route(cases[0]["query"], manifests())["slug"], "viet-email")
        report = R.evaluate(cases, manifests(), "bao-cao", "Gui thu cam on khach hang moi tuan")
        self.assertGreater(report["required_loss_count"], 0)
        self.assertEqual(report["mechanical_verdict"], "rejected")

    def test_case_validation_is_closed(self):
        good = {"query": "q one", "expected": "", "kind": "negative"}
        for bad in ([], [{"query": "q", "expected": "bao-cao", "kind": "negative"}],
                    [{"query": "q", "expected": "", "kind": "positive"}],
                    [{"query": "q", "expected": "unknown-skill", "kind": "competing"}],
                    [good, dict(good)], [{**good, "extra": 1}]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                R.validate_cases(bad, {"bao-cao"})
        with self.assertRaises(PermissionError):
            R.evaluate([good], manifests(), "missing-skill", "Doi soat")
        with self.assertRaisesRegex(ValueError, "regression"):
            R.validate_cases([{"query": "q two", "expected": "bao-cao", "kind": "positive"}], {"bao-cao"})


if __name__ == "__main__":
    unittest.main()
