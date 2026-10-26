"""Owner-started self-learning runs: examples, split, protected skills, apply rules, recovery, cancel, HTTP."""
from _paths import ROOT, SERVER  # noqa: F401

import json
import tempfile
import unittest
from pathlib import Path

import improvement_loop_runs as R
from improvement_store import ConflictError

SKILL = "---\nname: doi-soat\ndescription: Doi soat don hang\ngroup: Finance\n---\nMatch codes and answer JSON.\n"


def write_examples(root, n=16, family_dup=False, offset=0):
    items = [{"prompt": f"TASK {i} needs RULE-A", "expected": {"code": "A", "n": i}, "family": f"f{i + offset}"}
             for i in range(n)]
    if family_dup:
        items[1]["family"] = items[0]["family"]
    (root / "skills" / "doi-soat" / "examples.json").write_text(json.dumps(items), encoding="utf-8")


def engines(brain, seen=None):
    def solve(skill, prompt):
        n = int(prompt.split()[1])
        return json.dumps({"code": "A" if "RULE-A" in skill else "?", "n": n})

    def improve(instructions):
        if seen is not None:
            seen.append(instructions)
        current = instructions.split("<current>\n", 1)[1].split("\n</current>", 1)[0]
        return f"<skill>{current}\nAlways apply RULE-A.</skill>"
    return solve, improve


class LoopRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.brain = self.tmp / "brain"
        (self.brain / "skills" / "doi-soat").mkdir(parents=True)
        self.skill = self.brain / "skills" / "doi-soat" / "SKILL.md"
        self.skill.write_bytes(SKILL.encode("utf-8"))
        self.protected, self.seen = set(), []
        self.runs = R.LoopRuns(self.tmp / "state", engines=lambda b: engines(b, self.seen),
                               protected=lambda b, s: s in self.protected, spawn=lambda fn: fn())

    def start(self, key="start-run-1"):
        return self.runs.start(str(self.brain), "doi-soat", event_key=key)

    def test_examples_split_checker_and_estimate(self):
        write_examples(self.brain)
        cases = R.load_cases(self.brain, "doi-soat")
        self.assertEqual((sum(c.split == "tuning" for c in cases), sum(c.split == "qualification" for c in cases)), (4, 12))
        self.assertEqual(cases, R.load_cases(self.brain, "doi-soat"))  # deterministic
        self.assertEqual(R.estimate_calls(cases), 4 * 4 + 3 + 4 * 12)
        case = cases[0]
        self.assertTrue(R.check(case, "```json\n" + json.dumps(case.answer) + "\n```")["pass"])
        self.assertEqual(R.check(case, '{"code": "A", "n": -1}')["score"], 0.5)
        self.assertFalse(R.check(R.L.Case("x", "x", "tuning", "p", {"ok": True}), '{"ok": 1}')["pass"])  # True is not 1
        self.assertEqual(R.split_frontmatter("\ufeff---\r\nname: x\r\n---\r\nBody\r\n"),
                         ("---\nname: x\n---\n", "Body\n"))  # a Windows-saved skill still splits
        write_examples(self.brain, n=12)
        with self.assertRaisesRegex(ValueError, "examples_count"):
            R.load_cases(self.brain, "doi-soat")
        write_examples(self.brain, family_dup=True)
        with self.assertRaisesRegex(ValueError, "family_repeated"):
            R.load_cases(self.brain, "doi-soat")

    def test_run_then_apply_keeps_frontmatter_and_a_backup(self):
        write_examples(self.brain)
        started = self.start()
        self.assertEqual(self.start(), started)  # an exact retry of the same event key
        run = self.runs.get(str(self.brain), started["run_id"])
        self.assertEqual((run["state"], run["result"]["chosen"], run["result"]["report"]["verdict"]), ("done", "c1", "helped"))
        self.assertFalse(any("name: doi-soat" in text or "group: Finance" in text for text in self.seen))  # body only
        self.assertEqual(self.skill.read_bytes().decode("utf-8"), SKILL)  # nothing changes before Apply
        applied = self.runs.apply(str(self.brain), started["run_id"])
        text = self.skill.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: doi-soat\ndescription: Doi soat don hang\ngroup: Finance\n---\n"))
        self.assertIn("RULE-A", text)
        self.assertNotIn(b"\r\n", self.skill.read_bytes())
        self.assertFalse(any(p.name.startswith("SKILL.md.bak") for p in self.skill.parent.iterdir()))  # not mirrored
        backup = next((self.tmp / "state").rglob(applied["backup"]))
        self.assertEqual(backup.read_bytes().decode("utf-8"), SKILL)
        with self.assertRaisesRegex(PermissionError, "nothing_to_apply"):
            self.runs.apply(str(self.brain), started["run_id"])

    def test_owner_edit_during_the_run_blocks_apply(self):
        write_examples(self.brain)
        started = self.start()
        self.skill.write_bytes((SKILL + "Owner edit.\n").encode("utf-8"))
        with self.assertRaisesRegex(ConflictError, "skill_changed"):
            self.runs.apply(str(self.brain), started["run_id"])
        self.assertIn("Owner edit.", self.skill.read_text(encoding="utf-8"))

    def test_a_used_sealed_set_moves_to_tuning_and_never_judges_again(self):
        write_examples(self.brain)
        first = self.runs.get(str(self.brain), self.start("start-run-1")["run_id"])
        with self.assertRaisesRegex(ValueError, "examples_need_fresh_sealed"):  # 12 families now known, 4 fresh
            self.start("start-run-2")
        self.assertEqual(self.runs.status(str(self.brain), "doi-soat")["examples"]["reason"], "examples_need_fresh_sealed")
        write_examples(self.brain, n=24)  # 8 new families join the 4 untouched ones
        consumed = R.consumed_families(self.runs._runs(str(self.brain)), "doi-soat")
        self.assertEqual(consumed, frozenset(first["sealed_families"]))
        cases = R.load_cases(self.brain, "doi-soat", consumed)
        self.assertTrue(all(c.split == "tuning" for c in cases if c.family in consumed))
        self.assertEqual(sum(c.split == "qualification" for c in cases), 12)
        third = self.runs.get(str(self.brain), self.start("start-run-3")["run_id"])
        self.assertFalse(third["sealed_reused"])
        self.assertFalse(set(third["sealed_families"]) & consumed)

    def test_interrupted_run_never_blocks_and_cancel_stops(self):
        write_examples(self.brain)
        background = R.LoopRuns(self.tmp / "state", engines=engines, protected=lambda b, s: False, spawn=lambda fn: None)
        started = background.start(str(self.brain), "doi-soat", event_key="start-bg-1")  # never spawned
        with self.assertRaisesRegex(ConflictError, "busy"):
            background.start(str(self.brain), "doi-soat", event_key="start-bg-2")
        self.assertEqual(background.cancel(str(self.brain), started["run_id"])["cancelling"], True)
        self.assertTrue(background.get(str(self.brain), started["run_id"])["cancel_requested"])
        background.clock = lambda: 10 ** 10  # a long run whose worker is alive here is never cut off
        self.assertEqual(background.get(str(self.brain), started["run_id"])["state"], "running")
        restarted = R.LoopRuns(self.tmp / "state", engines=engines, protected=lambda b, s: False,
                               clock=lambda: 10 ** 10, spawn=lambda fn: None)  # no worker owns it any more
        self.assertEqual(restarted.get(str(self.brain), started["run_id"])["error"], "interrupted")
        restarted.start(str(self.brain), "doi-soat", event_key="start-bg-3")  # no longer blocked
        R.BOOT_ID, old = "another-process", R.BOOT_ID
        try:
            self.assertTrue(all(r["state"] != "running" for r in background._runs(str(self.brain))))
        finally:
            R.BOOT_ID = old

    def test_protected_missing_examples_and_unavailable_engine(self):
        self.protected.add("doi-soat")
        write_examples(self.brain)
        with self.assertRaisesRegex(PermissionError, "skill_protected"):
            self.start()
        self.protected.clear()
        (self.brain / "skills" / "doi-soat" / "examples.json").unlink()
        with self.assertRaisesRegex(ValueError, "examples_missing"):
            self.start()
        self.assertFalse(self.runs.status(str(self.brain), "doi-soat")["examples"]["ok"])
        with self.assertRaisesRegex(ValueError, "invalid_skill"):
            self.runs.status(str(self.brain), "../x")
        write_examples(self.brain)

        def down(brain):
            raise PermissionError("engine_unavailable: grok")
        with self.assertRaisesRegex(PermissionError, "engine_unavailable"):
            R.LoopRuns(self.tmp / "state3", engines=down, protected=lambda b, s: False).start(
                str(self.brain), "doi-soat", event_key="start-down")

    def test_engine_failure_mid_run_is_reported_not_judged(self):
        write_examples(self.brain)

        def failing(brain):
            solve, improve = engines(brain)

            def broken(skill, prompt):
                raise ConnectionError("quota")
            return broken, improve
        runs = R.LoopRuns(self.tmp / "state4", engines=failing, protected=lambda b, s: False, spawn=lambda fn: fn())
        run = runs.get(str(self.brain), runs.start(str(self.brain), "doi-soat", event_key="start-fail")["run_id"])
        self.assertEqual(run["state"], "failed")
        self.assertTrue(run["error"].startswith("engine_unavailable"))

    def test_http_routes(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import improvement_activation_api as API
        write_examples(self.brain)
        app = FastAPI()
        API.register(app, API.ActivationApiDeps(activations=lambda: None, resolve_brain=lambda value: str(self.brain),
                                                loop_runs=lambda: self.runs))
        client = TestClient(app)
        status = client.get("/improvement-loops?slug=doi-soat").json()
        self.assertEqual(status["examples"]["estimated_calls"], 67)
        run = client.post("/improvement-loops", json={"slug": "doi-soat", "event_key": "http-loop-start"}).json()["run"]
        self.assertEqual(client.get(f"/improvement-loops/{run['run_id']}").json()["run"]["state"], "done")
        self.assertEqual(client.post(f"/improvement-loops/{run['run_id']}/cancel", json={"event_key": "http-loop-cancel"}).status_code, 409)
        applied = client.post(f"/improvement-loops/{run['run_id']}/apply", json={"event_key": "http-loop-apply"})
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertEqual(client.get("/improvement-loops/ilr_bad").status_code, 422)


if __name__ == "__main__":
    unittest.main()
