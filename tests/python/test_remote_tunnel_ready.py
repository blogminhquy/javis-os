"""The tunnel supervisor restarts a cloudflared that is alive but disconnected, and Messenger callbacks follow the new
quick link (2026-11-17). No network: a fake cloudflared script and a fake /ready probe stand in.

    python tests/run.py remote_tunnel_ready

The night of 2026-11-17 the Mac slept for 26 minutes. cloudflared kept running, /ready answered 503 with
readyConnections 0, the trycloudflare hostname left DNS, and Meta's webhook calls went nowhere until someone killed
cloudflared by hand and re-pointed the Meta app's callback.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import http.server
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-tunnel-ready-test-")
os.environ.pop("JAVIS_HOST", None)
os.environ.pop("JAVIS_PORT", None)

import remote_tunnel as rt            # noqa: E402
import messenger_tunnel_sync as mts   # noqa: E402


def wait_for(pred, seconds=15.0):
    end = time.time() + seconds
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.1)
    return pred()


class Probe:
    """Answers /ready with whatever `code` currently is, and remembers the ports it was asked about."""

    def __init__(self, code):
        self.code = code
        self.ports = []

    def __call__(self, port, timeout=5):
        self.ports.append(port)
        return self.code


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        work = Path(tempfile.mkdtemp(prefix="javis-fake-cf-"))
        self.calls = work / "calls.log"
        counter = work / "n"
        fake = work / "cloudflared"
        # Each run prints a different quick link, like the real thing.
        fake.write_text(f"""#!{sys.executable}
import os, sys, time
n = int(open({str(counter)!r}).read()) + 1 if os.path.exists({str(counter)!r}) else 1
open({str(counter)!r}, "w").write(str(n))
with open({str(self.calls)!r}, "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\\n")
print(f"INF |  https://run-{{n}}.trycloudflare.com   |", flush=True)
print("INF Registered tunnel connection connIndex=0", flush=True)
time.sleep(120)
""")
        fake.chmod(0o755)
        self.fake = str(fake)
        for name, value in (("READY_GRACE", 0), ("READY_CHECK_EVERY", 0), ("UNREADY_RESTART_AFTER", 2),
                            ("UNREADY_MIN_PROBES", 2), ("BACKOFF", (0, 0, 0, 0)), ("PASSWORD_CHECK_EVERY", 1)):
            p = patch.object(rt, name, value)
            p.start()
            self.addCleanup(p.stop)
        for target, value in (("remote_tunnel.section", lambda cfg=None: {"enabled": True, "mode": "quick"}),
                              ("remote_tunnel.enabled", lambda cfg=None: True),
                              ("config.auth_enabled", lambda: True)):
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)

    def manager(self, probe):
        m = rt.TunnelManager(binary_finder=lambda: self.fake, installer=lambda: "", ready_probe=probe)
        self.addCleanup(m.stop, 5)
        return m

    def runs(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_unready_tunnel_is_restarted_on_a_new_link(self):
        probe = Probe(503)
        m = self.manager(probe)
        urls = []
        m.add_url_listener(urls.append)
        m.start()
        self.assertTrue(wait_for(lambda: len(self.runs()) >= 2), self.runs())
        self.assertTrue(any("restarting cloudflared" in line for line in m.log), list(m.log))
        probe.code = 200
        self.assertTrue(wait_for(lambda: len(urls) >= 2), urls)
        self.assertEqual(urls[0], "https://run-1.trycloudflare.com")
        self.assertNotEqual(urls[0], urls[1])

    def test_metrics_port_passed_and_probed(self):
        probe = Probe(200)
        m = self.manager(probe)
        m.start()
        self.assertTrue(wait_for(lambda: len(probe.ports) >= 3))
        argv = self.runs()[0].split()
        self.assertIn("--metrics", argv)
        self.assertEqual(argv[argv.index("--metrics") + 1], f"127.0.0.1:{probe.ports[0]}")

    def test_healthy_tunnel_is_left_alone(self):
        probe = Probe(200)
        m = self.manager(probe)
        urls = []
        m.add_url_listener(urls.append)
        m.start()
        self.assertTrue(wait_for(lambda: len(probe.ports) >= 4))
        time.sleep(1)
        self.assertEqual(len(self.runs()), 1)
        self.assertEqual(m.state, "running")
        self.assertEqual(urls, ["https://run-1.trycloudflare.com"])

    def test_silent_metrics_server_is_not_a_reason_to_restart(self):
        probe = Probe(None)
        m = self.manager(probe)
        m.start()
        self.assertTrue(wait_for(lambda: len(probe.ports) >= 4))
        time.sleep(1)
        self.assertEqual(len(self.runs()), 1)

    def test_short_blip_recovers_without_restart(self):
        probe = Probe(503)
        m = self.manager(probe)
        m.start()
        self.assertTrue(wait_for(lambda: m.state == "waiting"))
        probe.code = 200
        self.assertTrue(wait_for(lambda: m.state == "running" and not m.error))
        time.sleep(2.5)
        self.assertEqual(len(self.runs()), 1)


class ProbeTests(unittest.TestCase):
    def serve(self, code):
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(code if self.path == "/ready" else 404)
                self.end_headers()
                self.wfile.write(b'{"status":%d,"readyConnections":0}' % code)

            def log_message(self, *a):
                pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return srv.server_address[1]

    def test_probe_reads_status(self):
        self.assertEqual(rt.probe_ready(self.serve(200)), 200)
        self.assertEqual(rt.probe_ready(self.serve(503)), 503)

    def test_probe_none_when_nothing_listens(self):
        self.assertIsNone(rt.probe_ready(rt.free_port(), timeout=1))


class MessengerSyncTests(unittest.TestCase):
    NEW = "https://new-words.trycloudflare.com"

    def test_moved_url_keeps_path_and_only_moves_quick_links(self):
        self.assertEqual(mts.moved_url("https://old.trycloudflare.com/messenger/webhook", self.NEW),
                         "https://new-words.trycloudflare.com/messenger/webhook")
        self.assertEqual(mts.moved_url("https://old.trycloudflare.com/ext/inbox-receiver/messenger/webhook?v=2",
                                       self.NEW),
                         "https://new-words.trycloudflare.com/ext/inbox-receiver/messenger/webhook?v=2")
        for stored in ("https://shop.example.com/messenger/webhook", "http://old.trycloudflare.com/messenger/webhook",
                       "https://u:p@old.trycloudflare.com/messenger/webhook", self.NEW + "/messenger/webhook", ""):
            with self.subTest(stored=stored):
                self.assertEqual(mts.moved_url(stored, self.NEW), "")
        self.assertEqual(mts.moved_url("https://old.trycloudflare.com/x", "https://javis.example.com"), "")

    def fake_world(self, accounts):
        saved = {}
        meta_calls = []

        def update_account(aid, patch_):
            saved[aid] = patch_
            return True, ""

        async def set_app_webhook(client, app_id, secret, url, verify):
            meta_calls.append(("page", app_id, url, verify))
            return {"ok": True}

        async def set_instagram_webhook(client, app_id, secret, url, verify):
            meta_calls.append(("instagram", app_id, url, verify))
            return {"ok": True}

        async def debug_token(client, token, *a):
            return {"ok": False}

        mods = {
            "channel_accounts": types.SimpleNamespace(list_accounts=lambda channel="": accounts,
                                                      get_token=lambda aid: aid, update_account=update_account),
            "messenger_bot": types.SimpleNamespace(
                split_credentials=lambda tok: {"page_id": tok, "access_token": "pt", "app_secret": "sec"}),
            "messenger_setup": types.SimpleNamespace(set_app_webhook=set_app_webhook,
                                                     set_instagram_webhook=set_instagram_webhook,
                                                     debug_token=debug_token),
        }
        p = patch.dict(sys.modules, mods)
        p.start()
        self.addCleanup(p.stop)
        return saved, meta_calls

    def test_sync_re_registers_once_per_app_and_saves_each_account(self):
        old = "https://old.trycloudflare.com/messenger/webhook"
        accounts = [
            {"id": "a1", "channel": "messenger", "meta": {"app_id": "111", "webhook_url": old, "ig_id": "9"}},
            {"id": "a2", "channel": "messenger", "meta": {"app_id": "111", "webhook_url": old}},
            {"id": "a3", "channel": "messenger", "meta": {"app_id": "222",
                                                          "webhook_url": "https://shop.example.com/messenger/webhook"}},
        ]
        saved, calls = self.fake_world(accounts)
        res = asyncio.run(mts.sync(self.NEW, "vt", client=object()))
        new = self.NEW + "/messenger/webhook"
        self.assertEqual(res, {"updated": ["a1", "a2"], "errors": []})
        self.assertEqual(calls, [("page", "111", new, "vt"), ("instagram", "111", new, "vt")])
        self.assertEqual(saved, {"a1": {"meta": {"webhook_url": new}}, "a2": {"meta": {"webhook_url": new}}})

    def test_sync_without_app_id_reports_and_saves_nothing(self):
        saved, calls = self.fake_world([{"id": "a1", "channel": "messenger",
                                         "meta": {"webhook_url": "https://old.trycloudflare.com/messenger/webhook"}}])
        res = asyncio.run(mts.sync(self.NEW, "vt", client=object()))
        self.assertEqual((res["updated"], calls, saved), ([], [], {}))
        self.assertEqual(len(res["errors"]), 1)

    def test_follow_retries_until_done_and_stops_when_the_link_moves_on(self):
        attempts = []

        async def fake_sync(base, verify, client=None):
            attempts.append(verify)
            return {"updated": [], "errors": ["meta busy"]} if len(attempts) < 2 else {"updated": ["a1"], "errors": []}

        with patch.object(mts, "sync", fake_sync):
            res = mts.follow(self.NEW, lambda: "vt", delays=(0, 0, 0, 0), sleep=lambda s: None)
            self.assertEqual((res["updated"], len(attempts)), (["a1"], 2))
            attempts.clear()
            res = mts.follow(self.NEW, lambda: "vt", current_url_fn=lambda: "https://newer.trycloudflare.com",
                             delays=(0, 0), sleep=lambda s: None)
            self.assertEqual(attempts, [])


if __name__ == "__main__":
    unittest.main()
