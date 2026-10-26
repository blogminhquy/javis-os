"""Owner-started self-learning runs: examples, split, protected skills, apply only on unchanged bytes, HTTP."""
from _paths import ROOT, SERVER  # noqa: F401

import json
import tempfile
import unittest
from pathlib import Path

import improvement_loop_runs as R

SKILL = "---\nname: doi-soat\ndescription: Doi soat don hang\n---\nMatch codes and answer JSON.\n"


def write_examples(root, n=9, family_dup=False):
    items = [{"prompt": f"TASK {i} needs RULE-A", "expected": {"code": "A", "n": i}, "family": f"f{i}"} for i in range(n)]
    if family_dup:
        items[1]["family"] = items[0]["family"]
    path = root / "skills" / "doi-soat" / "examples.json"
    path.write_text(json.dumps(items), encoding="utf-8")


def engines(brain):
    def solve(skill, prompt):
        n = int(prompt.split()[1])
        return json.dumps({"code": "A" if "RULE-A" in skill else "?", "n": n})

    def improve(instructions):
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
        self.protected = set()
        self.runs = R.LoopRuns(self.tmp / "state", engines=engines, protected=lambda b, s: s in self.protected,
                               spawn=lambda fn: fn())  # run inline

    def test_examples_split_and_checker(self):
        write_examples(self.brain)
        cases = R.load_cases(self.brain, "doi-soat")
        self.assertEqual((sum(c.split == "tuning" for c in cases), sum(c.split == "qualification" for c in cases)), (3, 6))
        self.assertEqual(cases, R.load_cases(self.brain, "doi-soat"))  # deterministic
        case = cases[0]
        self.assertTrue(R.check(case, "```json\n" + json.dumps(case.answer) + "\n```")["pass"])
        self.assertEqual(R.check(case, '{"code": "A", "n": -1}')["score"], 0.5)
        for bad, reason in ((5, "examples_count"),):
            write_examples(self.brain, n=bad)
            with self.assertRaisesRegex(ValueError, reason):
                R.load_cases(self.brain, "doi-soat")
        write_examples(self.brain, family_dup=True)
        with self.assertRaisesRegex(ValueError, "family_repeated"):
            R.load_cases(self.brain, "doi-soat")

    def test_run_then_apply_keeps_a_backup(self):
        write_examples(self.brain)
        started = self.runs.start(str(self.brain), "doi-soat")
        run = self.runs.get(str(self.brain), started["run_id"])
        self.assertEqual((run["state"], run["result"]["chosen"], run["result"]["report"]["verdict"]),
                         ("done", "c1", "helped"))
        self.assertEqual(self.skill.read_bytes().decode("utf-8"), SKILL)  # nothing changes before Apply
        applied = self.runs.apply(str(self.brain), started["run_id"])
        self.assertIn("RULE-A", self.skill.read_text(encoding="utf-8"))
        self.assertNotIn(b"\r\n", self.skill.read_bytes())
        self.assertEqual((self.skill.parent / applied["backup"]).read_bytes().decode("utf-8"), SKILL)
        with self.assertRaisesRegex(PermissionError, "skill_changed"):
            self.runs.apply(str(self.brain), started["run_id"])  # the file moved on: never applied twice

    def test_owner_edit_during_the_run_blocks_apply(self):
        write_examples(self.brain)
        started = self.runs.start(str(self.brain), "doi-soat")
        self.skill.write_bytes((SKILL + "Owner edit.\n").encode("utf-8"))
        with self.assertRaisesRegex(PermissionError, "skill_changed"):
            self.runs.apply(str(self.brain), started["run_id"])
        self.assertIn("Owner edit.", self.skill.read_text(encoding="utf-8"))

    def test_protected_missing_examples_and_one_run_at_a_time(self):
        self.protected.add("doi-soat")
        write_examples(self.brain)
        with self.assertRaisesRegex(PermissionError, "skill_protected"):
            self.runs.start(str(self.brain), "doi-soat")
        self.protected.clear()
        (self.brain / "skills" / "doi-soat" / "examples.json").unlink()
        with self.assertRaisesRegex(FileNotFoundError, "examples_missing"):
            self.runs.start(str(self.brain), "doi-soat")
        self.assertFalse(self.runs.status(str(self.brain), "doi-soat")["examples"]["ok"])
        write_examples(self.brain)
        background = R.LoopRuns(self.tmp / "state", engines=engines, protected=lambda b, s: False, spawn=lambda fn: None)
        background.start(str(self.brain), "doi-soat")  # stays running: never spawned
        with self.assertRaisesRegex(PermissionError, "busy"):
            background.start(str(self.brain), "doi-soat")

    def test_nothing_to_apply_when_the_baseline_wins(self):
        write_examples(self.brain)

        def no_help(brain):
            solve, _ = engines(brain)
            return solve, lambda instructions: "<skill>A different skill without the rule.</skill>"
        runs = R.LoopRuns(self.tmp / "state2", engines=no_help, protected=lambda b, s: False, spawn=lambda fn: fn())
        started = runs.start(str(self.brain), "doi-soat")
        self.assertEqual(runs.get(str(self.brain), started["run_id"])["result"]["chosen"], "base")
        with self.assertRaisesRegex(PermissionError, "nothing_to_apply"):
            runs.apply(str(self.brain), started["run_id"])

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
        self.assertTrue(status["examples"]["ok"])
        run = client.post("/improvement-loops", json={"slug": "doi-soat", "event_key": "http-loop-start"}).json()["run"]
        self.assertEqual(client.get(f"/improvement-loops/{run['run_id']}").json()["run"]["state"], "done")
        applied = client.post(f"/improvement-loops/{run['run_id']}/apply", json={"event_key": "http-loop-apply"})
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertEqual(client.get("/improvement-loops/ilr_bad").status_code, 422)


if __name__ == "__main__":
    unittest.main()
