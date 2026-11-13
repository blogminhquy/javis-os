"""The event loop reads from memory instead of waiting for the disk (server/kept.py, 2026-11-13).

    python tests/run.py kept_values      (no network)

GET /health/loop on the owner's VPS: one stat or one small read sometimes took seconds, once 93 seconds, and five
places that asked the disk from the event loop froze the whole server, worst right after an update. These tests
pin the rules of `kept.Value`, then check each place that was moved onto it with a "stalled disk": the read behind
the value is made to block, and the call on the event loop must still come back at once with the last value."""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import threading
import time

import pytest

import kept


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    """No test here depends on how fast the machine is. A value is made old by `aged()`, never by sleeping past
    RECHECK_S; a healthy read gets a generous WAIT_S; a stalled read blocks on a gate the test opens itself."""
    monkeypatch.setattr(kept, "RECHECK_S", 30.0)
    monkeypatch.setattr(kept, "WAIT_S", 5.0)
    monkeypatch.delenv("JAVIS_KEPT_OFF", raising=False)


@pytest.fixture
def gates():
    """Gates that stalled reads wait on; all opened when the test ends, so no helper thread stays stuck."""
    made = []

    def new():
        g = threading.Event()
        made.append(g)
        return g
    yield new
    for g in made:
        g.set()


def aged(v, seconds=1000.0):
    """Make the kept value of `v` look `seconds` old, as if nobody had asked for that long."""
    k, value, at = v._state
    v._state = (k, value, at - seconds)
    return v


def until(cond, seconds=10.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.005)
    return cond()


class Disk:
    """A read that counts its calls and can be told to stall (on a gate) or to fail."""

    def __init__(self):
        self.n = 0
        self.fail = False
        self.gate = None

    def __call__(self):
        if self.gate is not None:
            self.gate.wait(30)
        if self.fail:
            raise OSError("disk says no")
        self.n += 1
        return self.n


def on_loop(fn):
    """Run `fn()` on a running event loop and return (result, seconds it took)."""
    async def go():
        t = time.monotonic()
        r = fn()
        return r, time.monotonic() - t
    return asyncio.run(go())


# A call that waited for a stalled read would take the gate's 30 s; one that did not takes WAIT_S plus scheduling.
NOT_WAITED = 2.0


# ---------- the rules ----------

def test_other_threads_read_for_themselves_every_time():
    disk = Disk()
    v = kept.Value(disk)
    assert [v.get(), v.get(), v.get()] == [1, 2, 3]


def test_fresh_s_is_honoured_by_every_caller_and_can_be_a_function():
    disk = Disk()
    box = {"s": 3600.0}
    v = kept.Value(disk, fresh_s=lambda: box["s"])
    assert v.get() == 1 and v.get() == 1
    assert on_loop(v.get)[0] == 1
    box["s"] = 0.0
    assert v.get() == 2


def test_the_loop_reuses_a_recent_value_without_asking():
    disk = Disk()
    v = kept.Value(disk)
    v.get()

    async def go():
        return [v.get() for _ in range(50)]
    assert asyncio.run(go()) == [1] * 50 and disk.n == 1


def test_on_a_healthy_disk_the_loop_gets_the_new_value():
    disk = Disk()
    v = kept.Value(disk)
    v.get()
    assert on_loop(aged(v).get)[0] == 2


def test_on_a_stalled_disk_the_loop_gets_the_last_value_at_once(monkeypatch, gates):
    monkeypatch.setattr(kept, "WAIT_S", 0.02)
    disk = Disk()
    v = kept.Value(disk)
    v.get()
    disk.gate = gates()                    # the disk stops answering
    got, took = on_loop(aged(v).get)
    assert got == 1 and took < NOT_WAITED, (got, took)
    assert v.late == 1
    # while that read is still out, later calls take the last value without waiting again
    got2, took2 = on_loop(v.get)
    assert got2 == 1 and took2 < NOT_WAITED and v.late == 1, (got2, took2, v.late)
    disk.gate.set()                        # the disk answers at last: the late read lands behind the callers
    assert until(lambda: not v._busy)
    assert on_loop(v.get)[0] == 2 and disk.n == 2


def test_drop_makes_the_next_call_read_and_discards_a_read_that_started_before(monkeypatch, gates):
    monkeypatch.setattr(kept, "WAIT_S", 0.02)
    disk = Disk()
    v = kept.Value(disk)
    v.get()
    disk.gate = gates()
    on_loop(aged(v).get)                   # a helper read is now stuck on the old files
    v.drop()                               # the files change through Javis
    disk.gate.set()
    assert until(lambda: not v._busy)      # the stuck read comes back: it must not be kept
    assert v.age() is None
    disk.gate = None
    before = disk.n
    assert on_loop(v.get)[0] == before + 1 and v.age() is not None


def test_a_changed_key_is_read_at_once():
    disk = Disk()
    box = {"k": "/a"}
    v = kept.Value(disk, fresh_s=3600.0, key=lambda: box["k"])
    assert v.get() == 1 and v.get() == 1
    box["k"] = "/b"
    assert on_loop(v.get)[0] == 2


def test_a_failing_helper_read_keeps_the_value_and_is_not_retried_on_every_call(monkeypatch):
    disk = Disk()
    v = kept.Value(disk)
    v.get()
    aged(v)
    disk.fail = True
    asked = []
    real = kept._behind

    def counting(job):
        asked.append(1)
        real(job)
    monkeypatch.setattr(kept, "_behind", counting)

    async def go():
        return [v.get() for _ in range(30)]
    assert asyncio.run(go()) == [1] * 30
    assert len(asked) == 1                 # one try, then RECHECK_S of quiet
    disk.fail = False
    monkeypatch.setattr(kept, "RECHECK_S", 0.0)   # the pause is over
    assert on_loop(v.get)[0] == 2 and len(asked) == 2


def test_the_kill_switch_makes_the_loop_read_for_itself(monkeypatch):
    disk = Disk()
    v = kept.Value(disk)
    v.get()
    monkeypatch.setenv("JAVIS_KEPT_OFF", "1")
    assert on_loop(v.get)[0] == 2 and on_loop(v.get)[0] == 3


def test_keyed_keeps_one_value_per_argument_and_stays_bounded():
    seen = []

    def read(arg):
        seen.append(arg)
        return arg.upper()
    k = kept.Keyed(read, fresh_s=3600.0, limit=3)
    assert [k.get("a"), k.get("b"), k.get("a")] == ["A", "B", "A"] and seen == ["a", "b"]
    k.drop("a")
    assert k.get("a") == "A" and seen == ["a", "b", "a"]
    for x in ("c", "d", "e", "f"):
        k.get(x)
    assert len(k._values) <= 3
    k.drop()
    assert k._values == {}


def test_report_lists_the_reads_the_loop_went_on_without(monkeypatch, gates):
    monkeypatch.setattr(kept, "WAIT_S", 0.02)
    disk = Disk()
    v = kept.Value(disk, name="slow thing")
    v.get()
    assert not [r for r in kept.report()["slow"] if r["what"] == "slow thing"]
    disk.gate = gates()
    on_loop(aged(v).get)
    row = [r for r in kept.report()["slow"] if r["what"] == "slow thing"]
    assert row and row[0]["late"] == 1 and kept.report()["late_total"] >= 1
    src = (SERVER / "main.py").read_text(encoding="utf-8")
    assert 'return {**loop_watch.report(), "disk": kept.report()}' in src   # shown by GET /health/loop


# ---------- the places moved onto it: a stalled disk must not hold the event loop ----------

@pytest.fixture
def stalled(monkeypatch, gates):
    """`stalled(obj, "name")` makes `obj.name` block from now on, like a disk that stopped answering."""
    def make(obj, name):
        real = getattr(obj, name)
        gate = gates()

        def stuck(*a, **k):
            gate.wait(30)
            return real(*a, **k)
        monkeypatch.setattr(obj, name, stuck)
    monkeypatch.setattr(kept, "WAIT_S", 0.02)
    return make


def not_held(fn, value):
    """Call `fn` on the event loop with its kept `value` made old: it must come back without the disk."""
    aged(value)
    got, took = on_loop(fn)
    assert took < NOT_WAITED, f"the event loop waited {took:.2f} s for the disk"
    return got


def test_pack_signature_does_not_hold_the_loop(monkeypatch, stalled):
    import packs
    monkeypatch.setattr(packs, "SIGNATURE_S", 0.0)
    packs.invalidate()
    first = packs.signature()
    stalled(packs, "_signature_now")
    assert not_held(packs.signature, packs._SIG) == first
    packs._SIG.drop()


def test_catalog_does_not_hold_the_loop(monkeypatch, stalled):
    import mcp_catalog
    monkeypatch.setattr(mcp_catalog, "CHECK_S", 0.0)
    mcp_catalog.invalidate()
    first = mcp_catalog.load()
    assert first, "the bundled catalog is expected to list connectors"
    stalled(mcp_catalog, "_load_now")
    assert not_held(mcp_catalog.load, mcp_catalog._LOADED) is first
    mcp_catalog._LOADED.drop()
    mcp_catalog._cache.update(sig=None, by_id={})


def test_settings_do_not_hold_the_loop_and_a_save_shows_at_once(tmp_path, monkeypatch, stalled):
    import config
    monkeypatch.setattr(config, "SETTINGS_PATH", tmp_path / "settings.json")
    cfg = config.read_settings()
    cfg["workspace_name"] = "one"
    config.write_settings(cfg)
    assert on_loop(config.read_settings)[0]["workspace_name"] == "one"
    cfg["workspace_name"] = "two"
    config.write_settings(cfg)             # a change made through Javis: no waiting for RECHECK_S
    assert on_loop(config.read_settings)[0]["workspace_name"] == "two"
    stalled(config, "_settings_sig_now")
    assert not_held(config.read_settings, config._SETTINGS_SIG)["workspace_name"] == "two"
    config._SETTINGS_SIG.drop()


def test_the_account_check_of_every_signed_in_request_uses_the_same_kept_signature():
    src = (SERVER / "config.py").read_text(encoding="utf-8")
    check = src.split("def auth_guard_check(", 1)[1].split("\ndef ", 1)[0]
    assert "sig = _SETTINGS_SIG.get()" in check and "SETTINGS_PATH.stat()" not in check


def test_channel_accounts_do_not_hold_the_loop_and_a_save_shows_at_once(tmp_path, monkeypatch, stalled):
    import channel_accounts as ca
    monkeypatch.setattr(ca, "STORE_PATH", tmp_path / "channel_accounts.json")
    ca._save({"version": 1, "accounts": [{"id": "a1"}]})
    assert [a["id"] for a in on_loop(ca._load)[0]["accounts"]] == ["a1"]
    ca._save({"version": 1, "accounts": [{"id": "a1"}, {"id": "a2"}]})
    assert [a["id"] for a in on_loop(ca._load)[0]["accounts"]] == ["a1", "a2"]
    # callers edit what they get: two calls must never share one dict
    d1, d2 = ca._load(), ca._load()
    d1["accounts"].clear()
    assert len(d2["accounts"]) == 2 and len(ca._load()["accounts"]) == 2
    stalled(ca, "_read_text")
    assert len(not_held(ca._load, ca._TEXT)["accounts"]) == 2
    ca._TEXT.drop()


def test_chatbot_store_does_not_hold_the_loop(tmp_path, monkeypatch, stalled):
    import chatbot_store as cs
    monkeypatch.setattr(cs, "STORE_PATH", tmp_path / "chatbots.json")
    cs._save({"version": 1, "bots": [{"id": "b1", "accounts": []}]})
    assert [b["id"] for b in on_loop(cs._load)[0]["bots"]] == ["b1"]
    stalled(cs, "_read_text")
    assert [b["id"] for b in not_held(cs._load, cs._TEXT)["bots"]] == ["b1"]
    cs._TEXT.drop()


def test_hub_token_and_store_mtime_do_not_hold_the_loop(tmp_path, monkeypatch, stalled):
    import mcp_hub
    monkeypatch.setattr(mcp_hub, "_TOKEN_PATH", tmp_path / ".hub_token")
    tok = mcp_hub.hub_token()
    assert tok and (tmp_path / ".hub_token").read_text(encoding="utf-8").strip() == tok
    assert mcp_hub.hub_token() == tok      # created once, then read back
    stalled(mcp_hub, "_token_on_disk")
    assert not_held(mcp_hub.hub_token, mcp_hub._TOKEN) == tok
    first = mcp_hub._store_mtime()
    stalled(mcp_hub, "_store_mtime_now")
    assert not_held(mcp_hub._store_mtime, mcp_hub._STORE_MTIME) == first
    mcp_hub._TOKEN.drop()
    mcp_hub._STORE_MTIME.drop()


def test_plugin_signature_does_not_hold_the_loop_and_invalidate_drops_it(stalled):
    import plugins_host
    plugins_host.invalidate()
    first = plugins_host._signature(None, scope_vault=False)
    stalled(plugins_host, "_signature_now")
    value = plugins_host._SIGS._values[(None, False)]
    assert not_held(lambda: plugins_host._signature(None, scope_vault=False), value) == first
    plugins_host.invalidate()              # what the Plugins page and `javis_plugin` call after a change
    assert plugins_host._SIGS._values == {}


def test_resolved_paths_come_from_memory_on_the_loop(tmp_path, stalled):
    kept.forget_resolved()
    p = tmp_path / "brain"
    p.mkdir()
    first = kept.resolved(p)
    assert first == str(p.resolve())
    stalled(kept._RESOLVED, "_read")
    assert not_held(lambda: kept.resolved(p), kept._RESOLVED._values[str(p)]) == first
    kept.forget_resolved()


# ---------- wiring that is checked in the source ----------

def test_main_wiring():
    src = (SERVER / "main.py").read_text(encoding="utf-8")
    # the default brain folder, "is this brain a folder" and the resolved brain path
    assert "_DEFAULT_BRAIN_DIR = kept.Value(" in src and "return _DEFAULT_BRAIN_DIR.get()" in src
    assert "return brain if _BRAIN_IS_DIR.get(brain) else str(_default_brain_dir())" in src
    assert "return kept.resolved(root)" in src
    # a brain created, deleted or made the default through Javis is seen at once
    assert src.count("_brain_paths_changed()") >= 4
    # the public share routes run on a worker thread: plain `def`, never `async def`
    for name in ("share_xem", "share_raw", "share_asset", "share_sibling", "share_xem_html", "connect_catalog"):
        assert f"\ndef {name}(" in src and f"async def {name}(" not in src, name
    # the health probe answers from memory, and the values are read once on a worker thread at start-up
    health = src.split("async def health(request: Request):", 1)[1].split("\n\n\n", 1)[0]
    assert "cli = _HEALTH_CLI.get()" in health and "find_claude_cli()" not in health
    prime = src.split("async def _prime_kept_values():", 1)[1].split("\n\n\n", 1)[0]
    assert "await asyncio.wait_for(asyncio.to_thread(run), timeout=10)" in prime


def test_connection_health_reads_on_worker_threads():
    src = (SERVER / "connect_health.py").read_text(encoding="utf-8")
    loop = src.split("async def _loop():", 1)[1].split("\ndef ", 1)[0]
    assert "await asyncio.to_thread(probe_engines)" in loop
    assert "await startup_smoke(await asyncio.to_thread(_app_version))" in loop
    assert "for conn in await asyncio.to_thread(mcp_store.resolved, True):" in src
    assert "await asyncio.to_thread(_oauth_facts, oauth_mcp, conn[\"id\"])" in src
    assert "await asyncio.to_thread(_last_notified)" in src
    assert "await asyncio.to_thread(_save_notified, fingerprint)" in src


def test_engine_notice_reaches_the_loop_from_a_worker_thread():
    """`probe_engines` now runs on a worker thread, and its owner notice is a coroutine only the loop can start."""
    import connect_health as ch
    got = []

    async def notice(text):
        got.append(text)

    async def go():
        ch._main_loop = asyncio.get_running_loop()
        await asyncio.to_thread(ch._send, notice("engine down"))
        for _ in range(50):
            if got:
                break
            await asyncio.sleep(0.01)
    asyncio.run(go())
    ch._main_loop = None
    assert got == ["engine down"]


def test_startup_warm_pass_opens_few_sessions_at_once(monkeypatch):
    import mcp_client
    assert mcp_client.warm_parallel() == 3 < mcp_client._DIAL_SONG_SONG
    monkeypatch.setenv("JAVIS_MCP_WARM_PARALLEL", "1")
    assert mcp_client.warm_parallel() == 1
    monkeypatch.setenv("JAVIS_MCP_WARM_PARALLEL", "99")
    assert mcp_client.warm_parallel() == mcp_client._DIAL_SONG_SONG
    monkeypatch.setenv("JAVIS_MCP_WARM_PARALLEL", "x")
    assert mcp_client.warm_parallel() == 3
    src = (SERVER / "mcp_client.py").read_text(encoding="utf-8")
    warm = src.split("async def warm_pool(conns):", 1)[1].split("\nasync def ", 1)[0]
    assert "sem = asyncio.Semaphore(warm_parallel())" in warm


if __name__ == "__main__":
    import sys
    try:
        import pytest  # noqa: F811
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
