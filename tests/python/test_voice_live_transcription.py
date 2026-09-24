"""Documented conversational Live frames, with input independent of model turns.

https://ai.google.dev/api/live?hl=en lists text/languageCode, no finished flag.
Javis final=True commits a received segment; it does not assert an utterance ID.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import json
import unittest
from unittest.mock import patch, AsyncMock
from voice_live import GeminiLive


class GeminiTranscriptionTests(unittest.TestCase):
    def setUp(self):
        self.provider = GeminiLive("unused-test-key")

    def frame(self, **content):
        return self.provider.translate({"serverContent": content})

    def test_input_segment_is_committed_without_waiting_for_model_turn(self):
        self.assertEqual(self.frame(inputTranscription={"text": "xin chào", "languageCode": "vi-VN"}), [
            {"type": "transcript", "role": "user", "text": "xin chào", "final": True}])
        self.assertEqual(self.frame(turnComplete=True), [{"type": "turn_done"}])

    def test_late_input_after_turn_complete_is_committed_immediately(self):
        self.frame(turnComplete=True)
        self.assertEqual(self.frame(inputTranscription={"text": "synthetic sentence"}), [
            {"type": "transcript", "role": "user", "text": "synthetic sentence", "final": True}])

    def test_independent_input_segments_never_concatenate_across_turns(self):
        self.frame(turnComplete=True)
        first = self.frame(inputTranscription={"text": "first sentence"})
        second = self.frame(inputTranscription={"text": "second sentence"})
        self.assertEqual([ev["text"] for ev in first + second], ["first sentence", "second sentence"])
        self.assertTrue(all(ev["final"] for ev in first + second))

    def test_interim_updates_replace_preview_and_do_not_pollute_committed_text(self):
        self.frame(interimInputTranscription={"text": "xin"})
        self.assertEqual(self.frame(interimInputTranscription={"text": "xin chào"}), [
            {"type": "transcript", "role": "user", "text": "xin chào", "final": False}])
        self.assertEqual(self.frame(inputTranscription={"text": "xin chào"}), [
            {"type": "transcript", "role": "user", "text": "xin chào", "final": True}])

    def test_same_frame_processes_transcripts_and_turn_without_duplicate_commit(self):
        events = self.frame(inputTranscription={"text": "synthetic"}, outputTranscription={"text": "answer"}, turnComplete=True)
        self.assertEqual(events, [
            {"type": "transcript", "role": "user", "text": "synthetic", "final": True},
            {"type": "transcript", "role": "assistant", "text": "answer", "final": False},
            {"type": "turn_done"}])
        self.assertEqual(self.frame(turnComplete=True), [{"type": "turn_done"}])

    def test_empty_transcription_does_not_commit_a_blank_message(self):
        self.assertEqual(self.frame(inputTranscription={"text": ""}), [])


class FakeSocket:
    """Only websocket I/O is replaced; production lifecycle stays real."""
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.sent = []
        self.closed = False

    async def send(self, data):
        self.sent.append(json.loads(data))

    async def recv(self):
        return await self.incoming.get()

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.recv()

    async def close(self):
        self.closed = True


class GeminiHandshakeTests(unittest.IsolatedAsyncioTestCase):
    async def test_connect_waits_for_setup_and_preserves_early_events(self):
        provider, socket = GeminiLive("unused"), FakeSocket()
        with patch("websockets.connect", new=AsyncMock(return_value=socket)):
            task = asyncio.create_task(provider.connect())
            for _ in range(5):
                await asyncio.sleep(0)
            self.assertFalse(task.done(), "connect must not report ready before setupComplete")
            self.assertEqual(len(socket.sent), 1)
            self.assertIn("setup", socket.sent[0])
            socket.incoming.put_nowait(json.dumps({"serverContent": {"inputTranscription": {"text": "early"}}}))
            socket.incoming.put_nowait(json.dumps({"setupComplete": {}}))
            await asyncio.wait_for(task, 1)
            events = provider.events()
            self.assertEqual(await anext(events), {"type": "transcript", "role": "user", "text": "early", "final": True})
            self.assertEqual(await anext(events), {"type": "ready"})
            await events.aclose()
            await provider.close()

    async def test_audio_waits_for_setup_ack_including_reconnect_window(self):
        provider, socket = GeminiLive("unused"), FakeSocket()
        with patch("websockets.connect", new=AsyncMock(return_value=socket)):
            task = asyncio.create_task(provider.connect())
            for _ in range(5):
                await asyncio.sleep(0)
            audio_task = asyncio.create_task(provider.send_audio(b"\x00\x00"))
            for _ in range(5):
                await asyncio.sleep(0)
            self.assertEqual(len(socket.sent), 1, "only setup may be sent before acknowledgement")
            socket.incoming.put_nowait(json.dumps({"setupComplete": {}}))
            await asyncio.wait_for(task, 1)
            await asyncio.wait_for(audio_task, 1)
            self.assertIn("realtimeInput", socket.sent[1])
            await provider.close()

    async def test_setup_timeout_closes_socket(self):
        provider, socket = GeminiLive("unused"), FakeSocket()
        provider.SETUP_TIMEOUT = 0.01
        with patch("websockets.connect", new=AsyncMock(return_value=socket)):
            with self.assertRaises(TimeoutError):
                await provider.connect()
        self.assertTrue(socket.closed)
        self.assertIsNone(provider.ws)

    async def test_setup_rejection_closes_socket_instead_of_starting_audio(self):
        provider, socket = GeminiLive("unused"), FakeSocket()
        socket.incoming.put_nowait(json.dumps({"error": {"message": "synthetic rejection"}}))
        with patch("websockets.connect", new=AsyncMock(return_value=socket)):
            with self.assertRaises(RuntimeError):
                await provider.connect()
        self.assertTrue(socket.closed)
        self.assertIsNone(provider.ws)


if __name__ == "__main__":
    unittest.main()
