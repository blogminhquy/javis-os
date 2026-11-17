"""Quick tunnel watchdog and Messenger webhook follow (2026-11-17). No network.

Incident: cloudflared kept running with zero edge connections, its trycloudflare.com name stopped resolving, and
Meta delivered Messenger messages nowhere for ten hours. Pinned here:
1. the health probe reads cloudflared's /ready count and reports dead only when it says 0 (unknown = healthy);
2. a NEW quick address is announced once to listeners, a repeat of the same one is not, token mode never;
3. follow_quick_tunnel moves an app that sat on an old quick address, leaves a real domain alone, skips an app
   already on the new address, and re-subscribes the Page of an app it moved.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-tunnel-watchdog-"))

import remote_tunnel as rt  # noqa: E402
import messenger_setup as ms  # noqa: E402


def _serve(status: int, body: dict):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class HealthProbe(unittest.TestCase):
    def test_ready_count_read_from_200_and_503(self):
        a = _serve(200, {"status": 200, "readyConnections": 4})
        b = _serve(503, {"status": 503, "readyConnections": 0})
        self.addCleanup(a.shutdown)
        self.addCleanup(b.shutdown)
        self.assertEqual(rt.ready_connections(a.server_port), 4)
        self.assertEqual(rt.ready_connections(b.server_port), 0)
        self.assertIsNone(rt.ready_connections(rt.free_port(), timeout=1))

    def test_dead_only_when_running_and_zero(self):
        m = rt.TunnelManager(binary_finder=lambda: "", installer=lambda: "")
        dead = _serve(503, {"readyConnections": 0})
        self.addCleanup(dead.shutdown)
        m._metrics_port = dead.server_port
        m.state = "starting"
        self.assertEqual(m._dead_too_long(0.0), 0.0, "not connected yet is not dead")
        m.state = "running"
        first = m._dead_too_long(0.0)
        self.assertGreater(first, 0)
        self.assertEqual(m._dead_too_long(first), first, "keeps the time it went dead")
        m._metrics_port = rt.free_port()
        self.assertEqual(m._dead_too_long(first), 0.0, "cannot ask = do not kill")

    def test_dead_shows_waiting_and_recovers(self):
        m = rt.TunnelManager(binary_finder=lambda: "", installer=lambda: "")
        dead = _serve(503, {"readyConnections": 0})
        live = _serve(200, {"readyConnections": 2})
        self.addCleanup(dead.shutdown)
        self.addCleanup(live.shutdown)
        m.state, m._metrics_port = "running", dead.server_port
        since = m._dead_too_long(0.0)
        self.assertEqual(m.state, "waiting")
        self.assertTrue(m.error)
        self.assertEqual(m._dead_too_long(since), since, "still probed while waiting")
        self.assertEqual(m._dead_probes, 2)
        m._metrics_port = live.server_port
        self.assertEqual(m._dead_too_long(since), 0.0)
        self.assertEqual((m.state, m.error, m._dead_probes), ("running", "", 0))

    def test_restart_needs_time_and_three_dead_answers(self):
        m = rt.TunnelManager(binary_finder=lambda: "", installer=lambda: "")
        long_ago = time.time() - rt.DEAD_AFTER - 5
        m._dead_probes = rt.DEAD_MIN_PROBES - 1
        self.assertFalse(m._should_restart(long_ago), "long enough but too few probes")
        m._dead_probes = rt.DEAD_MIN_PROBES
        self.assertFalse(m._should_restart(time.time() - 5), "enough probes but too short")
        self.assertTrue(m._should_restart(long_ago))
        self.assertFalse(m._should_restart(0.0))

    def test_grace_period_before_first_probe(self):
        self.assertGreaterEqual(rt.READY_GRACE, 30)
        self.assertGreaterEqual(rt.DEAD_MIN_PROBES, 3)

    def test_metrics_flag_on_both_commands(self):
        m = rt.TunnelManager(binary_finder=lambda: "", installer=lambda: "")
        m.mode = "quick"
        cmd, _ = m._command("cf", {})
        self.assertIn("--metrics", cmd)
        self.assertEqual(cmd[-2:], ["--url", rt.local_target()])
        m.mode = "token"
        cmd, _ = m._command("cf", {"token": "x"})
        self.assertEqual(cmd[-1], "run")
        self.assertIn(f"127.0.0.1:{m._metrics_port}", cmd)


class Announce(unittest.TestCase):
    def test_new_quick_address_announced_once(self):
        m = rt.TunnelManager(binary_finder=lambda: "", installer=lambda: "")
        got, done = [], threading.Event()

        def fn(url):
            got.append(url)
            done.set()
        m.add_url_listener(fn)
        m.mode = "quick"
        m._note("INF |  https://brave-tiny-otter.trycloudflare.com   |")
        m._note("INF Registered tunnel connection connIndex=0")
        self.assertTrue(done.wait(3))
        m._note("INF Registered tunnel connection connIndex=1")
        time.sleep(0.2)
        self.assertEqual(got, ["https://brave-tiny-otter.trycloudflare.com"])

    def test_token_mode_never_announces(self):
        m = rt.TunnelManager(binary_finder=lambda: "", installer=lambda: "")
        got = []
        m.add_url_listener(got.append)
        m.mode, m.url = "token", "https://fixed.example"
        m._note("INF Registered tunnel connection connIndex=0")
        time.sleep(0.2)
        self.assertEqual(got, [])


class Follow(unittest.TestCase):
    NEW = "https://new-words.trycloudflare.com/messenger/webhook"

    def run_case(self, current: dict):
        calls = []

        async def app_webhook(c, app_id, secret):
            return {"ok": True, "found": True, "callback_url": current[app_id], "active": True, "fields": []}

        async def set_app_webhook(c, app_id, secret, url, vt):
            calls.append(("hook", app_id, url))
            return {"ok": True}

        async def subscribe_page(c, page_id, tok):
            calls.append(("sub", page_id))
            return {"ok": True}
        accs = [{"id": "a1", "page_id": "p1", "token": "t", "app_id": "app1", "app_secret": "s"},
                {"id": "a2", "page_id": "p2", "token": "t", "app_id": "app1", "app_secret": "s"},
                {"id": "a3", "page_id": "p3", "token": "t", "app_id": "app2", "app_secret": "s"}]
        with patch.object(ms, "app_webhook", app_webhook), patch.object(ms, "set_app_webhook", set_app_webhook), \
                patch.object(ms, "subscribe_page", subscribe_page):
            res = asyncio.run(ms.follow_quick_tunnel(None, accs, self.NEW, "vt"))
        return res, calls

    def test_old_quick_moves_domain_stays(self):
        res, calls = self.run_case({"app1": "https://old-dead.trycloudflare.com/messenger/webhook",
                                    "app2": "https://shop.example.com/messenger/webhook"})
        self.assertEqual(res, {"moved": ["app1"], "errors": []})
        self.assertEqual(calls, [("hook", "app1", self.NEW), ("sub", "p1"), ("sub", "p2")])

    def test_instagram_retried_even_when_page_already_moved(self):
        calls = []

        async def app_webhook(c, app_id, secret):
            return {"ok": True, "callback_url": self.NEW}

        async def ig_webhook(c, app_id, secret):
            return {"ok": True, "callback_url": "https://old-dead.trycloudflare.com/messenger/webhook"}

        async def set_ig(c, app_id, secret, url, vt):
            calls.append(("ig", app_id, url))
            return {"ok": True}
        accs = [{"id": "a1", "page_id": "p1", "token": "t", "app_id": "app1", "app_secret": "s", "ig": True}]
        with patch.object(ms, "app_webhook", app_webhook), patch.object(ms, "instagram_webhook", ig_webhook), \
                patch.object(ms, "set_instagram_webhook", set_ig):
            res = asyncio.run(ms.follow_quick_tunnel(None, accs, self.NEW, "vt"))
        self.assertEqual(res, {"moved": [], "errors": []})
        self.assertEqual(calls, [("ig", "app1", self.NEW)])

    def test_already_on_new_address_is_untouched(self):
        res, calls = self.run_case({"app1": self.NEW, "app2": ""})
        self.assertEqual(res["moved"], ["app2"])
        self.assertEqual(calls, [("hook", "app2", self.NEW), ("sub", "p3")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
