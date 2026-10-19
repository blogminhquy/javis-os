"""Gemini Live ignores speech not meant for it, and the reply pace has three presets (0.220.0).

    python tests/run.py voice_live_tuning

No network. Proactive audio (the TV-in-the-room fix) and the turn presets are preview fields: a
server that refuses them must not kill the call, so the provider reconnects once without them.
"Normal" must leave today's payload untouched.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import unittest

import voice_live


def gemini(**kw):
    return voice_live.GeminiLive("k", model="gemini-3.1-flash-live-preview", **kw)


class SetupTests(unittest.TestCase):
    def test_defaults_keep_the_old_payload(self):
        g = gemini()
        setup = g.setup_message()["setup"]
        self.assertNotIn("proactivity", setup)
        self.assertNotIn("realtimeInputConfig", setup)
        self.assertIn(".v1beta.", g.url())

    def test_proactive_audio_uses_v1alpha(self):
        g = gemini(proactive=True)
        self.assertEqual(g.setup_message()["setup"]["proactivity"], {"proactiveAudio": True})
        self.assertIn(".v1alpha.", g.url())

    def test_turn_presets(self):
        fast = gemini(turn="fast").setup_message()["setup"]["realtimeInputConfig"]["automaticActivityDetection"]
        slow = gemini(turn="slow").setup_message()["setup"]["realtimeInputConfig"]["automaticActivityDetection"]
        self.assertLess(fast["silenceDurationMs"], slow["silenceDurationMs"])
        self.assertEqual(fast["endOfSpeechSensitivity"], "END_SENSITIVITY_HIGH")
        self.assertEqual(slow["endOfSpeechSensitivity"], "END_SENSITIVITY_LOW")
        self.assertNotIn("realtimeInputConfig", gemini(turn="normal").setup_message()["setup"])
        self.assertEqual(voice_live.turn_preset("weird"), "normal")

    def test_openai_presets_keep_500ms_as_normal(self):
        def silence(turn):
            msg = voice_live.OpenAIRealtime("k", turn=turn).setup_message()
            return msg["session"]["audio"]["input"]["turn_detection"]["silence_duration_ms"]
        self.assertEqual(silence("normal"), 500)
        self.assertLess(silence("fast"), 500)
        self.assertGreater(silence("slow"), 500)

    def test_make_provider_reads_settings_and_defaults_proactive_on(self):
        p = voice_live.make_provider({"voice": {"live_provider": "gemini"}, "model": {"gemini_api_key": "x"}})
        self.assertTrue(p.proactive)
        self.assertEqual(p.turn, "normal")
        p = voice_live.make_provider({"voice": {"live_provider": "gemini", "live_proactive": False, "live_turn": "slow"},
                                      "model": {"gemini_api_key": "x"}})
        self.assertFalse(p.proactive)
        self.assertEqual(p.turn, "slow")
        p = voice_live.make_provider({"voice": {"live_provider": "gpt-live"}, "model": {"openai_api_key": "x"}})
        self.assertIsInstance(p, voice_live.GPTLive)


class FallbackTests(unittest.TestCase):
    def test_refused_setup_reconnects_without_optional_fields(self):
        g = gemini(proactive=True, turn="fast")
        tried = []

        async def once():
            tried.append((g.url(), dict(g.setup_message()["setup"])))
            if len(tried) == 1:
                raise RuntimeError("Gemini Live rejected session setup.")

        g._connect_once = once
        asyncio.run(g.connect())
        self.assertEqual(len(tried), 2)
        self.assertIn("proactivity", tried[0][1])
        self.assertNotIn("proactivity", tried[1][1])
        self.assertNotIn("realtimeInputConfig", tried[1][1])
        self.assertIn(".v1beta.", tried[1][0])
        self.assertFalse(g.optional_fields, "stays off for the rest of the call, reconnects included")

    def test_plain_setup_failure_is_not_retried(self):
        g = gemini()
        calls = []

        async def once():
            calls.append(1)
            raise RuntimeError("bad key")

        g._connect_once = once
        with self.assertRaises(RuntimeError):
            asyncio.run(g.connect())
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
