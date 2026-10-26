"""Automatic learning from chat: episodes, judge, caps, learning runs for skills/agents/workflows, apply, undo, HTTP."""
from _paths import ROOT, SERVER  # noqa: F401

import json
import tempfile
import unittest
from pathlib import Path

import auto_learning as A
from improvement_store import ConflictError

SKILL = "---\nname: bao-gia\ndescription: Bao gia\ngroup: Sales\n---\nWrite the quote for the customer.\n"
WORKFLOW = ("---\nname: Quote flow\nsteps:\n- agent: writer\n  task: 'Write a quote for {{input}}'\n"
            "- agent: checker\n  task: Check {{prev}}\n---\nNotes stay.\n")


class FakeEngine:
    """Dispatches on the system prompt. The work passes only when the instructions contain RULE-X."""
    def __init__(self, judge="mistake", testable=True, grader_fails=False, improve_rule="RULE-X"):
        self.calls, self.judge, self.testable, self.grader_fails, self.improve_rule = [], judge, testable, grader_fails, improve_rule
        self.improver_prompts = []

    def __call__(self, system, prompt):
        self.calls.append((system, prompt))
        if "careful reviewer" in system:
            return json.dumps({"verdict": self.judge, "what": "forgot the deposit", "right": "always state the deposit",
                               "case": {"prompt": "Quote 3 doors, TRAP deposit", "criteria": ["states RULE-X"]},
                               "step": 0})
        if "write test sets" in system:
            if not self.testable:
                return '{"testable": false}'
            cases = [{"family": f"m{i}", "type": "mistake", "prompt": f"TRAP mistake case {i}", "criteria": ["RULE-X"]}
                     for i in range(3)]
            cases += [{"family": f"v{i}", "type": "variant", "prompt": f"TRAP variant case {i}", "criteria": ["RULE-X"]}
                      for i in range(7)]
            cases += [{"family": f"k{i}", "type": "keep", "prompt": f"ordinary keep case {i}", "criteria": ["ok"]}
                      for i in range(8)]
            return "```json\n" + json.dumps({"testable": True, "cases": cases}) + "\n```"
        if system == A.GRADER_SYSTEM:
            if self.grader_fails:
                raise TimeoutError("grader down")
            task = prompt.split("## Task\n", 1)[1].split("\n\n## Criteria", 1)[0]
            answer = prompt.split("## Answer\n", 1)[1]
            ok = ("RULE-X" in answer) if "TRAP" in task else ("ANSWER" in answer)
            return json.dumps({"pass": ok, "score": 1.0 if ok else 0.0, "feedback": "" if ok else "missing RULE-X"})
        if "improve the instructions" in system:
            self.improver_prompts.append(prompt)
            current = prompt.split("<current>\n", 1)[1].split("\n</current>", 1)[0]
            return f"<skill>{current}\nAlways apply {self.improve_rule}.</skill>"
        return "ANSWER " + ("RULE-X" if "RULE-X" in system + prompt else "")


class AutoLearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.brain = self.tmp / "brain"
        (self.brain / "skills" / "bao-gia").mkdir(parents=True)
        (self.brain / "workflows").mkdir()
        (self.brain / "agents").mkdir()
        self.skill = self.brain / "skills" / "bao-gia" / "SKILL.md"
        self.skill.write_bytes(SKILL.encode("utf-8"))
        (self.brain / "workflows" / "quote.md").write_bytes(WORKFLOW.encode("utf-8"))
        (self.brain / "agents" / "writer.md").write_text("---\nname: writer\n---\nYou write quotes.\n", encoding="utf-8")
        self.engine, self.policy, self.protected = FakeEngine(), [True], set()
        self.agent_applied, self.now = [], [1_800_000_000.0]
        self.workflow_runs = {}
        self.host = A.Host(
            text_call=lambda s, p: self.engine(s, p), engine_ready=lambda b: None, policy_on=lambda b: self.policy[0],
            skill_protected=lambda b, s: s in self.protected, workflows_dir=lambda b: Path(b) / "workflows",
            agent_text=lambda b, s: (Path(b) / "agents" / f"{s}.md").read_text(encoding="utf-8")
            if (Path(b) / "agents" / f"{s}.md").is_file() else "",
            agent_procedure=lambda b, s: {"text": self.agent_applied[-1]} if self.agent_applied else {},
            agent_apply=lambda b, s, text: (self.agent_applied.append(text), {"slug": s, "overlay_id": "iao_x"})[1],
            agent_undo=lambda b, info: self.agent_applied.pop(),
            reaction=lambda sid, mid: "angry wrong_facts", workflow_run=lambda rid: self.workflow_runs.get(rid),
            backups=self.tmp / "backups")
        self.learner = A.AutoLearner(A.Store(self.tmp / "al.sqlite3"), self.host, clock=lambda: self.now[0], width=2)
        self.b = str(self.brain)

    def turn(self, session="s1", request="quote please", answer="here", channel="web", mid=7, skill="bao-gia"):
        if skill:
            self.learner.note_skill_use(self.b, session, skill)
        return self.learner.observe_turn(self.b, session, channel, request, answer, mid)

    def mistakes(self, n=3, kind="skill", slug="bao-gia"):
        for i in range(n):
            self.turn(session=f"s{i}")
            self.learner.observe_turn(self.b, f"s{i}", "web", "wrong, you forgot the deposit", "sorry", 9)
        while self.learner.judge_ready():
            pass

    def test_skill_from_native_tools(self):
        self.assertEqual(A.skill_from_tool("Skill", {"skill": "bao-gia"}), "bao-gia")
        self.assertEqual(A.skill_from_tool("Read", {"file_path": "D:\\b\\skills\\bao-gia\\SKILL.md"}), "bao-gia")
        self.assertEqual(A.skill_from_tool("Read", {"file_path": "/b/skills/x/notes.md"}), "")
        self.assertEqual(A.skill_from_tool("mcp__javis__javis_use_skill", {"name": "bao-gia"}), "")  # hub records it

    def test_turns_become_episodes_with_follow_ups(self):
        first = self.turn()
        self.assertEqual(len(first), 1)
        self.assertEqual(self.turn(skill=None, request="no, add the deposit"), [])
        episode = self.learner.store.read("SELECT * FROM episodes WHERE id=?", (first[0],))[0]
        self.assertEqual((episode["kind"], episode["slug"], episode["follow_up"]), ("skill", "bao-gia", "no, add the deposit"))
        agent = self.learner.observe_turn(self.b, "s2", "agent:writer", "hi", "hello", 3)
        self.assertEqual(self.learner.store.read("SELECT kind, slug FROM episodes WHERE id=?", (agent[0],))[0],
                         {"kind": "agent", "slug": "writer"})
        self.assertEqual(self.turn(session="t1", channel="team:abc"), [])  # team chats are out of scope
        self.policy[0] = False
        self.assertEqual(self.turn(session="s9"), [])  # improvement policy "off" stops recording too

    def test_judge_records_mistakes_and_respects_caps(self):
        self.turn()
        self.assertEqual(self.learner.judge_ready(), 0)  # no follow-up and too young: not ready
        self.now[0] += A.READY_AFTER_S + 1
        self.assertEqual(self.learner.judge_ready(), 1)
        judge_call = [p for s, p in self.engine.calls if "careful reviewer" in s][0]
        self.assertIn("angry wrong_facts", judge_call)  # the owner's reaction reaches the judge
        self.assertIn("Write the quote", judge_call)
        self.assertEqual(len(self.learner.store.read("SELECT * FROM mistakes")), 1)
        self.engine.judge = "ok"
        for i in range(A.JUDGE_PER_DAY + 5):
            self.turn(session=f"c{i}")
        self.now[0] += A.READY_AFTER_S + 1
        while self.learner.judge_ready():
            pass
        self.assertEqual(self.learner.stats(self.b)["judged_today"], A.JUDGE_PER_DAY)
        self.protected.add("bao-gia")
        self.now[0] += 86400
        self.learner.judge_ready()
        self.assertTrue(self.learner.store.read("SELECT 1 FROM episodes WHERE verdict='target_unavailable'"))

    def test_skill_learning_applies_keeps_frontmatter_and_undoes(self):
        self.mistakes()
        self.assertEqual(self.learner.next_target(), (self.b, "skill", "bao-gia", -1))
        result = self.learner.step()["run"]
        self.assertEqual((result["state"], result["verdict"], result["applied"]), ("done", "helped", True))
        text = self.skill.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: bao-gia\ndescription: Bao gia\ngroup: Sales\n---\n"))
        self.assertIn("Always apply RULE-X.", text)
        self.assertFalse(any("name: bao-gia" in p for p in self.engine.improver_prompts))  # body only
        sealed = [p for s, p in self.engine.calls if "write" not in s and "TRAP variant" in p and "improve" not in s]
        self.assertTrue(sealed)
        self.assertFalse(any("TRAP variant" in p for p in self.engine.improver_prompts))  # sealed cases stay sealed
        self.assertEqual(self.learner.next_target(), None)  # mistakes consumed, cool-down, daily cap
        history = self.learner.history(self.b)
        self.assertEqual(history[0]["summary"]["regressions"], [])
        self.learner.undo(self.b, result["run_id"])
        self.assertEqual(self.skill.read_bytes().decode("utf-8"), SKILL)
        with self.assertRaises(ConflictError):
            self.learner.undo(self.b, result["run_id"])

    def test_undo_refuses_after_an_owner_edit(self):
        self.mistakes()
        run = self.learner.step()["run"]
        self.skill.write_text(SKILL + "Owner line.\n", encoding="utf-8")
        with self.assertRaisesRegex(ConflictError, "changed_since"):
            self.learner.undo(self.b, run["run_id"])
        self.assertIn("Owner line.", self.skill.read_text(encoding="utf-8"))

    def test_no_improvement_keeps_the_skill(self):
        self.engine.improve_rule = "RULE-Y"  # proposals that fix nothing
        self.mistakes()
        run = self.learner.step()["run"]
        self.assertEqual((run["verdict"], run["applied"]), ("keep_base", False))
        self.assertEqual(self.skill.read_bytes().decode("utf-8"), SKILL)

    def test_untestable_work_is_skipped_for_two_weeks(self):
        self.engine.testable = False
        self.mistakes()
        self.assertEqual(self.learner.step()["run"]["error"], "untestable")
        self.now[0] += A.COOL_DOWN_S + 86400
        self.assertIsNone(self.learner.next_target())

    def test_grader_outage_fails_the_run_instead_of_judging(self):
        self.engine.grader_fails = True
        self.mistakes()
        run = self.learner.step()["run"]
        self.assertEqual(run["state"], "failed")
        self.assertTrue(run["error"].startswith("engine_unavailable"))
        self.assertEqual(self.skill.read_bytes().decode("utf-8"), SKILL)

    def test_caps_need_enough_mistakes_and_one_run_a_day(self):
        self.mistakes(n=2)
        self.assertIsNone(self.learner.next_target())
        self.mistakes(n=1)
        self.assertIsNotNone(self.learner.next_target())
        self.policy[0] = False
        self.assertIsNone(self.learner.next_target())

    def test_workflow_step_learns_its_task(self):
        self.engine.judge = "mistake"
        self.workflow_runs["r1"] = {"steps": [{"i": 0, "agent": "writer", "task": "Write a quote", "output": "no deposit"}]}
        for i in range(3):
            self.learner.observe_workflow(self.b, "quote", "r1", "3 doors", "quote without deposit")
        self.now[0] += A.READY_AFTER_S + 1
        while self.learner.judge_ready():
            pass
        self.assertEqual(self.learner.next_target(), (self.b, "workflow", "quote", 0))
        run = self.learner.step()["run"]
        self.assertTrue(run["applied"], run)
        text = (self.brain / "workflows" / "quote.md").read_text(encoding="utf-8")
        self.assertIn("Always apply RULE-X.", text)
        self.assertIn("Check {{prev}}", text)  # the other step is untouched
        self.assertTrue(text.endswith("Notes stay.\n"))
        self.learner.undo(self.b, run["run_id"])
        self.assertEqual((self.brain / "workflows" / "quote.md").read_bytes().decode("utf-8"), WORKFLOW)

    def test_agent_learns_a_procedure_not_its_file(self):
        for i in range(3):
            self.learner.observe_turn(self.b, f"a{i}", "agent:writer", "quote", "no deposit", 4)
            self.learner.observe_turn(self.b, f"a{i}", "agent:writer", "you forgot the deposit", "sorry", 5)
        while self.learner.judge_ready():
            pass
        before = (self.brain / "agents" / "writer.md").read_text(encoding="utf-8")
        run = self.learner.step()["run"]
        self.assertTrue(run["applied"], run)
        self.assertIn("RULE-X", self.agent_applied[-1])
        self.assertEqual((self.brain / "agents" / "writer.md").read_text(encoding="utf-8"), before)
        self.learner.undo(self.b, run["run_id"])
        self.assertEqual(self.agent_applied, [])

    def test_build_cases_split(self):
        cases = A.build_cases(json.loads(FakeEngine()("write test sets", "")[8:-4]))
        tuning = [c for c in cases if c.split == "tuning"]
        self.assertTrue(all(c.family.startswith(("m", "k")) for c in tuning))
        self.assertTrue(all(c.split == "qualification" for c in cases if c.family.startswith("v")))
        with self.assertRaisesRegex(ValueError, "cases_count"):
            A.build_cases({"testable": True, "cases": []})

    def test_http_routes(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import improvement_activation_api as API
        self.mistakes()
        run = self.learner.step()["run"]
        app = FastAPI()
        API.register(app, API.ActivationApiDeps(activations=lambda: None, resolve_brain=lambda value: self.b,
                                                auto_learning=lambda: self.learner))
        client = TestClient(app)
        view = client.get("/auto-learning").json()
        self.assertEqual(view["history"][0]["id"], run["run_id"])
        self.assertEqual(client.post("/auto-learning/bad/undo", json={"event_key": "al-undo-1"}).status_code, 422)
        undone = client.post(f"/auto-learning/{run['run_id']}/undo", json={"event_key": "al-undo-2"})
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(self.skill.read_bytes().decode("utf-8"), SKILL)


if __name__ == "__main__":
    unittest.main()
