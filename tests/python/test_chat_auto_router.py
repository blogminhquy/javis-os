"""Routing, persistence, account isolation and replay safety checks."""
from _paths import ROOT, SERVER
import json
import tempfile
import time
import unittest
from pathlib import Path
import chat_auto_router as router
from sessions import SessionStore


class ChatAutoTests(unittest.TestCase):
    def setUp(self):
        self.candidates = {tier: {"id": model, "supported_reasoning_efforts": ["low", "medium", "high"]}
                           for tier, model in router.MODELS.items()}

    def test_simple_hard_and_continuation(self):
        simple = router.resolve("Chào em", self.candidates)
        self.assertEqual(simple["selected_model"], "gpt-6-luna")
        hard = router.resolve("Thiết kế kiến trúc và đối soát dữ liệu mâu thuẫn", self.candidates)
        self.assertEqual(hard["selected_model"], "gpt-6-astra")
        continued = router.resolve("tiếp tục đi", self.candidates, hard)
        self.assertEqual(continued["tier"], "high")
        self.assertEqual(router.resolve("Chào em", self.candidates, hard)["tier"], "low")

    def test_effort_only_when_supported(self):
        self.candidates["low"]["supported_reasoning_efforts"] = ["medium"]
        self.assertIsNone(router.resolve("hello", self.candidates)["effort"])

    def test_unavailable_respects_quality_floor(self):
        self.assertEqual(router.resolve("hello", {"medium": self.candidates["medium"]})["tier"], "medium")
        with self.assertRaises(router.RoutingUnavailable):
            router.resolve("debug race condition", {"low": self.candidates["low"]})

    def test_no_side_effect_replay(self):
        route = router.resolve("hello", self.candidates)
        error = "model is not available"
        upgraded = router.safe_fallback(route, self.candidates, error)
        self.assertEqual(upgraded["selected_model"], "gpt-6.1-sol")
        self.assertIsNone(router.safe_fallback(route, self.candidates, error, activity=True))
        for error in ["timeout", "429 quota", "login expired", "tool state unknown"]:
            self.assertIsNone(router.safe_fallback(route, self.candidates, error))
        route["escalations"] = 2
        self.assertIsNone(router.safe_fallback(route, self.candidates, "model unavailable"))

    def test_account_access_requires_recent_execution_and_catalog(self):
        cfg = {"openai_oauth": {"account_id": "test-account"}}
        catalog = {"items": list(self.candidates.values())}
        now = time.time()
        evidence = {"account_fingerprint": router.account_fingerprint(cfg), "models": {
            model: {"ok": True, "executed_model": model, "verified_at": now}
            for model in router.MODELS.values()}}
        self.assertEqual(len(router.verified_candidates(cfg, catalog, evidence=evidence, now=now)), 3)
        self.assertFalse(router.verified_candidates({}, catalog, evidence=evidence))
        self.assertFalse(router.verified_candidates(cfg, {}, evidence=evidence))
        self.assertFalse(router.verified_candidates(cfg, catalog, evidence=evidence, now=now + 86401))
        evidence["models"]["gpt-6-astra"]["executed_model"] = None
        self.assertNotIn("high", router.verified_candidates(cfg, catalog, evidence=evidence))

    def test_usage_snapshots_and_unknown(self):
        usage = router.InvocationUsage()
        self.assertIsNone(usage.total())
        usage.observe(1, {"usage": {"input_tokens": 10, "output_tokens": 2}})
        usage.observe(1, {"usage": {"input_tokens": 12, "output_tokens": 3}})
        usage.observe(2, {"usage": {"input_tokens": 5, "output_tokens": 1}})
        self.assertEqual(usage.total()["input_tokens"], 17)
        self.assertIsNone(usage.total()["reasoning_tokens"])

    def test_native_usage_across_resume(self):
        from datetime import datetime
        with tempfile.TemporaryDirectory() as td:
            sid = "01234567-0123-0123-0123-012345678901"
            folder = Path(td) / "sessions/2026/10/07"
            folder.mkdir(parents=True)
            events = []
            for sec, inp, out in ((1, 100, 10), (3, 160, 20), (4, 210, 30)):
                events.append({"timestamp": f"2026-10-07T10:00:0{sec}Z", "type": "event_msg",
                    "payload": {"type": "token_count", "info": {"total_token_usage": {
                        "input_tokens": inp, "output_tokens": out, "cached_input_tokens": inp // 2}}}})
            file = folder / ("rollout-" + sid + ".jsonl")
            file.write_text("\n".join(json.dumps(x) for x in events), encoding="utf-8")
            start = datetime.fromisoformat("2026-10-07T10:00:02+00:00").timestamp()
            delta = router.invocation_usage(sid, start, td)
            self.assertEqual(delta["input_tokens"], 110)
            self.assertEqual(delta["output_tokens"], 20)
            self.assertEqual(delta["cached_input_tokens"], 55)
            self.assertIsNone(delta["reasoning_tokens"])
            self.assertIsNone(router.invocation_usage("bad", start, td))
            events[-1]["payload"]["info"]["total_token_usage"]["input_tokens"] = 50
            file.write_text("\n".join(json.dumps(x) for x in events), encoding="utf-8")
            self.assertIsNone(router.invocation_usage(sid, start, td)["input_tokens"])

    def test_selection_survives_reopen_without_touching_pins(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "sessions.db"
            store = SessionStore(db)
            store.create_session(session_id="chat", brain="one")
            store.create_session(session_id="agent", brain="two", channel="agent:an")
            store.set_pinned_model("agent", "openai-oauth", "gpt-6.1-sol")
            before = store.get_session("agent")
            store.set_routing("chat", "auto")
            store.save_routing_state("chat", {"tier": "high", "usage": None})
            again = SessionStore(db)
            self.assertEqual(again.get_session("chat")["routing_mode"], "auto")
            self.assertEqual(json.loads(again.get_session("chat")["routing_state"])["tier"], "high")
            self.assertEqual(again.get_session("agent"), before)
            again.set_pinned_model("chat", "openai-oauth", "gpt-6.1-sol")
            self.assertEqual(again.get_session("chat")["routing_mode"], "pinned")
            again.set_routing("chat", "default")
            self.assertIsNone(again.get_session("chat")["pinned_provider"])
            self.assertEqual(again.get_session("chat")["routing_mode"], "default")
            again._conn.close()
            store._conn.close()


if __name__ == "__main__":
    unittest.main()
