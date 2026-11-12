"""A background-job link that just failed rests before it is tried first again (0.222.0).

    python tests/run.py aux_cooldown

No network. Without this every background job paid for the same dead model again (a 504 can take
15 seconds to arrive). A resting link moves to the END of the chain rather than being skipped, so
a job still runs when every other link fails too.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import os
import tempfile
import time
import unittest

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-auxcool-"))

import aux_engine  # noqa: E402
import model_routing  # noqa: E402
import plan_limits  # noqa: E402


class Link:
    def __init__(self, provider, model="m", events=None):
        self.provider, self.model = provider, model
        self.events = events or []
        self.ran = 0

    def is_available(self):
        return True

    def reset_session(self):
        pass

    async def query(self, prompt):
        self.ran += 1
        for ev in self.events:
            yield ev


def run(chain):
    async def go():
        return [ev async for ev in chain.query("job")]
    return asyncio.run(go())


FINAL = {"type": "final", "content": "ok"}


def err(text):
    return {"type": "error", "content": text}


class ClassifyTests(unittest.TestCase):
    def test_classes(self):
        self.assertEqual(aux_engine.cooldown_for("HTTP 429 Too Many Requests"), aux_engine.COOLDOWN_QUOTA_S)
        self.assertEqual(aux_engine.cooldown_for("You've hit your usage limit"), aux_engine.COOLDOWN_QUOTA_S)
        self.assertEqual(aux_engine.cooldown_for("503 UNAVAILABLE"), aux_engine.COOLDOWN_DOWN_S)
        self.assertEqual(aux_engine.cooldown_for("ReadTimeout: timed out"), aux_engine.COOLDOWN_DOWN_S)
        self.assertEqual(aux_engine.cooldown_for("404 model not found"), aux_engine.COOLDOWN_ACCESS_S)
        self.assertEqual(aux_engine.cooldown_for("401 invalid api key"), aux_engine.COOLDOWN_ACCESS_S)
        self.assertEqual(aux_engine.cooldown_for("tool javis_read_file failed: no such file"), 0.0)

    def test_retry_after_wins(self):
        self.assertEqual(aux_engine.cooldown_for("429, Retry-After: 42"), 42.0)
        self.assertEqual(aux_engine.cooldown_for("Rate limit reached. Please try again in 2m"), 120.0)
        self.assertEqual(aux_engine.cooldown_for("try again in 900ms"), 1.0)


class ChainTests(unittest.TestCase):
    def setUp(self):
        aux_engine._COOLDOWN.clear()

    def test_failed_link_rests_and_goes_last(self):
        bad = Link("gemini", events=[err("503 UNAVAILABLE")])
        good = Link("openrouter", events=[FINAL])
        run(aux_engine._FallbackChain([bad, good]))
        self.assertEqual((bad.ran, good.ran), (1, 1))
        bad2 = Link("gemini", events=[err("503 UNAVAILABLE")])   # next job: fresh objects, same model
        good2 = Link("openrouter", events=[FINAL])
        out = run(aux_engine._FallbackChain([bad2, good2]))
        self.assertEqual(out[-1], FINAL)
        self.assertEqual(bad2.ran, 0, "the resting model is not tried first again")
        self.assertEqual(good2.ran, 1)

    def test_everyone_resting_still_runs_soonest_first(self):
        a = Link("gemini", events=[err("429 quota")])
        b = Link("groq", events=[err("503 unavailable")])
        run(aux_engine._FallbackChain([a, b]))
        a2 = Link("gemini", events=[FINAL])
        b2 = Link("groq", events=[FINAL])
        out = run(aux_engine._FallbackChain([b2, a2]))
        self.assertEqual(out[-1], FINAL)
        self.assertEqual((a2.ran, b2.ran), (1, 0), "gemini wakes in 5 min, groq in 30: gemini goes first")

    def test_success_clears_the_rest(self):
        run(aux_engine._FallbackChain([Link("gemini", events=[err("429")]), Link("openrouter", events=[FINAL])]))
        self.assertTrue(aux_engine._COOLDOWN)
        run(aux_engine._FallbackChain([Link("openrouter", events=[FINAL]), Link("gemini", events=[FINAL])]))
        only = Link("gemini", events=[FINAL])
        run(aux_engine._FallbackChain([only]))
        self.assertNotIn("gemini:m", aux_engine._COOLDOWN, "a link that works again stops resting")

    def test_unrelated_error_does_not_rest(self):
        run(aux_engine._FallbackChain([Link("gemini", events=[err("tool failed")]), Link("openrouter", events=[FINAL])]))
        self.assertNotIn("gemini:m", aux_engine._COOLDOWN)

    def test_links_without_identity_never_rest(self):
        class Anon(Link):
            pass
        x = Anon(None, events=[err("503")])
        x.provider = None
        run(aux_engine._FallbackChain([x, Link("openrouter", events=[FINAL])]))
        self.assertEqual(list(aux_engine._COOLDOWN), [])


class CodexCLI(Link):
    """Stands in for the real plan link: the router knows a plan link by its class name."""

    def __init__(self, events=None):
        super().__init__(None, events=events)


class GrokCLI(CodexCLI):
    pass


CODEX_LIMIT = "You've hit your usage limit. Upgrade to Pro or try again at 8:42 AM."


class PlanLimitTests(unittest.TestCase):
    """Issue 1334: a background job refused for plan quota turns the usage ring red, as a refused chat turn does.
    Before, only the chat path recorded it, so background work could run a plan dry while the ring stayed green."""

    def setUp(self):
        aux_engine._COOLDOWN.clear()
        plan_limits._file().unlink(missing_ok=True)

    def test_refused_plan_link_turns_the_ring_red(self):
        before = time.time()
        out = run(aux_engine._FallbackChain([CodexCLI(events=[err(CODEX_LIMIT)]), Link("openrouter", events=[FINAL])]))
        self.assertEqual(out[-1], FINAL, "the next link still runs the job")
        codex = plan_limits.doc().get("codex") or {}
        self.assertIn("het", codex, "the refusal is recorded for the ring")
        self.assertEqual((codex["muc"], codex["max"]), ("bad", 100))
        self.assertGreater(codex["het"]["reset"], before, "with the reset time the plan stated")
        self.assertTrue(plan_limits.side_pause("openai-oauth")["paused"], "and Javis's own work waits")

    def test_final_flagged_as_error_counts_too(self):
        refused = {"type": "final", "is_error": True, "content": "You've hit your limit · resets 1:50am (Asia/Bangkok)"}
        link = Link(None, events=[refused])
        link.account_provider, link.account_id = "anthropic-cli", "acc2"   # a plan link pointed at one account
        try:
            run(aux_engine._FallbackChain([link, Link("openrouter", events=[FINAL])]))
        finally:
            model_routing.clear_rest("anthropic-cli", "acc2")
        self.assertIn("het", plan_limits.doc().get("claude") or {})

    def test_grok_plain_quota_words_count(self):
        run(aux_engine._FallbackChain([GrokCLI(events=[err("xAI API error 429 Too Many Requests")]),
                                       Link("openrouter", events=[FINAL])]))
        self.assertIn("het", plan_limits.doc().get("grok") or {})

    def test_api_key_and_unrelated_errors_record_nothing(self):
        run(aux_engine._FallbackChain([Link("groq", events=[err("429 quota exceeded")]),
                                       CodexCLI(events=[err("tool javis_read_file failed: no such file")]),
                                       CodexCLI(events=[err("503 UNAVAILABLE")]),
                                       Link("openrouter", events=[FINAL])]))
        self.assertEqual(set(plan_limits.doc().values()), {None}, "an API key has no plan, a broken tool is no refusal")

    def test_a_broken_meter_never_breaks_the_routing(self):
        real = plan_limits.ghi_het

        def boom(*a, **k):
            raise RuntimeError("disk full")
        plan_limits.ghi_het = boom
        try:
            good = Link("openrouter", events=[FINAL])
            out = run(aux_engine._FallbackChain([CodexCLI(events=[err(CODEX_LIMIT)]), good]))
        finally:
            plan_limits.ghi_het = real
        self.assertEqual((out[-1], good.ran), (FINAL, 1))
        self.assertIn("CodexCLI:m", aux_engine._COOLDOWN, "the refused link still rests")


if __name__ == "__main__":
    unittest.main()
