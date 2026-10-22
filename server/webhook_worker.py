"""webhook_worker.py - the worker side of webhooks (0.274.0, webhook platform; spec §5-§8, §11, §12, §13).

Mixed into webhook_triggers.WebhookFeature (which holds the configuration, the routes and the deps). Everything here
works FROM THE STORE: a lost wake-up loses nothing, because every pass scans the database again.

    triage     received events -> the hook's rules (pure code, no model) -> ignored / quarantined, or queued with their
               business key and deliveries, in one transaction (webhook_store.triage_commit);
    run        a queued event is claimed with a lease; each runnable delivery is checked (still the same target,
               current permission, secrets, approval, AI budget, breaker, dependencies), marked dispatched, run, and
               its outcome written; a delivery that succeeded never runs again;
    retry      1, 5, 30 minutes with +-20 % jitter, 4 calls in all, a valid Retry-After may stretch a wait inside the
               delivery's deadline (fake clock and RNG in tests: `self.clock`, `self.rng`);
    notices    built by code, queued durably in the outbox with a dedup key, delivered by the sweep; a failed notice is
               retried alone, never the action.

No path here calls a model except the hook's own AI action (and incident triage, only when the hook turned it on).
"""
from __future__ import annotations

import asyncio
import json
import random
import sqlite3
import sys
import time
from typing import Optional

import localefmt
import webhook_actions
import webhook_auth
import webhook_rules
import webhook_secrets
import webhook_store

WORKER_MAX = 4                 # events running at once in this process (one per hook: spec §11)
TRIAGE_BATCH = 50
SWEEP_S = 30.0
RETRY_DELAYS_S = (60.0, 300.0, 1800.0)     # spec §7
RETRY_JITTER = 0.2
RETRY_DEADLINE_S = 24 * 3600.0
AI_PER_HOUR_DEFAULT = 30                   # spec §11
AI_GLOBAL_PER_HOUR = 300
DIGEST_HOUR = 8
DIGEST_TRIES = 10
INCIDENT_REPEAT_S = 6 * 3600.0             # errors_only: the same open incident is told again at most this often


def _rank(level: str) -> int:
    return ("suggest", "auto", "full").index(level) if level in ("suggest", "auto", "full") else 2


dep_state = webhook_store.dep_state


class WebhookWorker:
    """Mixin: needs self.deps, self.store(), self.vault, self._find_hook(hid), self._secret(ref, name)."""

    def _worker_init(self) -> None:
        self._pump: Optional[asyncio.Task] = None
        self._wake: Optional[asyncio.Event] = None
        self._active: dict = {}
        self._ai_active: set = set()
        self._ai_ids_last: list = []
        self._tasks: set = set()
        self._sweeper: Optional[asyncio.Task] = None
        self.clock = time.time
        self.rng = random.Random()

    # ── pump ──
    def _kick(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._wake is None:
            self._wake = asyncio.Event()
        self._wake.set()
        if self._pump is None or self._pump.done():
            self._pump = loop.create_task(self._pump_loop())
            self._tasks.add(self._pump)
            self._pump.add_done_callback(self._tasks.discard)

    async def _pump_loop(self) -> None:
        """Triage what was received, then claim events while there is room. A kick that lands during a claim is not
        lost (the flag is cleared BEFORE looking, checked before leaving)."""
        wake = self._wake
        while True:
            wake.clear()
            try:
                n = await self._triage_batch()
            except Exception as e:
                print(f"[webhooks] triage failed: {type(e).__name__}: {e}", file=sys.stderr)
                n = 0
            if len(self._active) >= WORKER_MAX:
                await asyncio.wait(list(self._active.values()), return_when=asyncio.FIRST_COMPLETED)
                continue
            try:
                ai_ids = await asyncio.to_thread(self._ai_hook_ids)
                self._ai_ids_last = ai_ids
            except Exception:
                ai_ids = self._ai_ids_last          # keep protecting the last slot with what was known
            avoid = ai_ids if WORKER_MAX > 1 and len(self._ai_active) >= WORKER_MAX - 1 else None
            try:
                row = await asyncio.to_thread(self.store().claim, self.worker_id, None, avoid)
            except Exception as e:
                print(f"[webhooks] claim failed: {type(e).__name__}: {e}", file=sys.stderr)
                return
            if row is not None:
                t = asyncio.get_running_loop().create_task(self._run_claimed(row))
                self._active[row["id"]] = t
                self._tasks.add(t)
                if row["hook_id"] in ai_ids:
                    self._ai_active.add(row["id"])

                def _done(task, eid=row["id"]):
                    self._active.pop(eid, None)
                    self._ai_active.discard(eid)
                    self._tasks.discard(task)
                    if not task.cancelled() and task.exception() is not None:
                        e = task.exception()
                        print(f"[webhooks] {eid} run crashed: {type(e).__name__}: {e}", file=sys.stderr)
                    self._kick()
                t.add_done_callback(_done)
                continue
            if wake.is_set() or n >= TRIAGE_BATCH:
                continue
            if not self._active:
                return
            w = asyncio.get_running_loop().create_task(wake.wait())
            await asyncio.wait(list(self._active.values()) + [w], return_when=asyncio.FIRST_COMPLETED)
            w.cancel()

    async def wait_idle(self) -> None:
        """Wait until nothing is due or running in this process (tests, shutdown)."""
        while True:
            pending = [t for t in self._tasks if t is not self._sweeper]
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
                continue
            if not await asyncio.to_thread(self.store().has_claimable):
                await self.deliver_notifications()
                return
            self._kick()
            await asyncio.sleep(0)

    def start(self) -> None:
        if self._sweeper is None or self._sweeper.done():
            self._sweeper = asyncio.get_running_loop().create_task(self._sweep_loop())

    async def stop(self) -> None:
        if self._sweeper:
            self._sweeper.cancel()
        await self.wait_idle()

    # ── triage ──
    def _revision_config(self, hid: str, rev: int, legacy_snapshot: str = "") -> Optional[dict]:
        """The configuration an event arrived under: its revision; for an event stored by an older build, its own
        snapshot; failing both, the hook as it is now."""
        st = self.store()
        if rev:
            cfg = st.hook_revision(hid, rev)
            if cfg is not None:
                return cfg
        snap = webhook_store._loads(legacy_snapshot, {})
        if snap:
            return snap
        cur = self._find_hook(hid)
        return None if cur is None else st._config_of(cur)

    def plan_deliveries(self, eid: str, cfg: dict, doc, received_at: float, gen: int = 1) -> list:
        """The delivery rows of an event under a configuration: `when` decided now (a false condition cancels that
        action for this event, with the reason), dependencies recorded, the deadline set."""
        actions = webhook_actions.effective(cfg.get("actions"))
        rcfg = cfg.get("retry") or {}
        deadline = received_at + float(rcfg.get("deadline_h") or RETRY_DEADLINE_S / 3600) * 3600
        out = []
        for a in actions:
            d = {"action_id": a["id"], "kind": a["kind"], "delivery_id": webhook_actions.delivery_id(eid, a["id"], gen),
                 "deadline": deadline, "depends": a.get("depends_on") or []}
            if a.get("when"):
                ok, code, err = webhook_rules.eval_condition(a["when"], doc)
                if not ok:
                    d.update(status="cancelled", detail=f"condition not met ({err or code})")
            out.append(d)
        return out

    async def _triage_batch(self) -> int:
        st = self.store()
        rows = await asyncio.to_thread(st.triage_candidates, TRIAGE_BATCH)
        for r in rows:
            try:
                await self._triage_one(st, r)
            except (webhook_store.Busy, sqlite3.Error, OSError) as e:
                # The store itself is busy or failing: a passing fault, never a reason to quarantine the event.
                print(f"[webhooks] triage of {r['id']} deferred: {type(e).__name__}: {e}", file=sys.stderr)
                try:
                    await asyncio.to_thread(st.triage_defer, r["id"], 30, f"store busy: {type(e).__name__}")
                except Exception:
                    pass
            except Exception as e:
                # One event that cannot be decided must never hold every later event of every hook (the batch is
                # oldest first, so a raise here would repeat on each pass): it is quarantined with the fault named.
                print(f"[webhooks] triage of {r['id']} failed: {type(e).__name__}: {e}", file=sys.stderr)
                why = f"triage_error_{type(e).__name__}"[:60]
                try:
                    await asyncio.to_thread(st.triage_commit, r["id"], {"decision": "invalid", "reason": why,
                                                                       "reasons": [why]}, [])
                except Exception as e2:
                    print(f"[webhooks] could not quarantine {r['id']}: {type(e2).__name__}", file=sys.stderr)
                    await asyncio.to_thread(st.triage_defer, r["id"], 300, why)
        return len(rows)

    async def _triage_one(self, st, r: dict) -> None:
        if True:
            try:
                cfg = await asyncio.to_thread(self._revision_config, r["hook_id"], int(r["hook_rev"] or 0))
            except Exception as e:
                await asyncio.to_thread(st.triage_defer, r["id"], 30, f"configuration unreadable: {type(e).__name__}")
                return
            if cfg is None:
                # The hook is gone: the event never runs (forget_hook marks these too; this covers a race).
                await asyncio.to_thread(st.triage_commit, r["id"], {"decision": "invalid", "reason": "hook_deleted",
                                                                   "reasons": ["hook_deleted"]}, [])
                return
            trace = webhook_store._loads(r.get("trace"), {})
            body, ct = bytes(r.get("body") or b""), r.get("content_type") or ""
            rules = cfg.get("rules") or {}
            if rules:
                from webhook_triggers import evaluate_closed
                pre = await asyncio.to_thread(evaluate_closed, rules, body, ct, trace.get("event"))
            else:
                pre = {"decision": "run", "trace": {}, "fields": {}, "reasons": []}
            plan = []
            if pre.get("decision") == "run":
                doc = webhook_rules.parse_payload(body, ct)[0]
                if isinstance(doc, dict) and trace.get("event"):
                    doc = dict(doc, _event=webhook_auth.run_event(trace["event"], doc))
                plan = self.plan_deliveries(r["id"], cfg, doc, float(r["received_at"]))
            got = await asyncio.to_thread(st.triage_commit, r["id"], pre, plan)
            if got == "invalid":
                # Quarantined: the owner hears of it (grouped under errors_only), from counts and reason codes only.
                full = await asyncio.to_thread(st.get, r["id"])
                if full:
                    await self._notify(full)

    # ── sweep ──
    async def sweep(self) -> dict:
        """Recover expired leases, queue notices a crash lost, deliver the outbox, digests, space alerts, expiry; then
        run what is due."""
        st = await asyncio.to_thread(self.store)
        rec = await asyncio.to_thread(st.recover)
        for ev in await asyncio.to_thread(st.unnotified):
            full = await asyncio.to_thread(st.get, ev["id"])
            await self._notify(dict(full, fence=ev.get("fence")) if full else ev)
        for step in (self._digest, self._space_alert, self._expire):
            try:
                await step()
            except Exception as e:
                print(f"[webhooks] {step.__name__} failed: {type(e).__name__}: {e}", file=sys.stderr)
        await self.deliver_notifications()
        self._kick()
        return rec

    async def _sweep_loop(self) -> None:
        n = 0
        try:
            sealed = await asyncio.to_thread(self._migrate_secrets)
            if sealed:
                print(f"[webhooks] moved {sealed} secret(s) into the encrypted vault", file=sys.stderr)
        except Exception as e:
            print(f"[webhooks] secret migration failed: {type(e).__name__}: {e}", file=sys.stderr)
        while True:
            try:
                await self.sweep()
                n += 1
                if n % 120 == 1:
                    keep = {h["id"]: int(h["retention_days"]) for h in await asyncio.to_thread(self.store().hooks_all)
                            if h.get("retention_days")}
                    await asyncio.to_thread(self.store().prune, None, keep)
            except Exception as e:
                print(f"[webhooks] sweep failed: {type(e).__name__}: {e}", file=sys.stderr)
            await asyncio.sleep(SWEEP_S)

    async def _expire(self) -> int:
        n = 0
        for h in await asyncio.to_thread(self.store().hooks_all):
            hours = int(h.get("expire_after_h") or 0)
            if hours:
                n += await asyncio.to_thread(self.store().expire, h["id"], hours * 3600.0)
        return n

    async def _space_alert(self) -> None:
        """A system alert (spec §12: never silenced by a hook's `none`): the store nears its cap or the disk is low."""
        sp = await asyncio.to_thread(self.store().space_state)
        if sp["level"] == "ok":
            return
        day = time.strftime("%Y-%m-%d", time.gmtime(self.clock()))
        mb = sp["used"] // webhook_store.MiB
        free = sp["disk_free"] // webhook_store.MiB
        msg = localefmt.chu(f"⚠ Kho sự kiện webhook {'đã đầy' if sp['level'] == 'full' else 'sắp đầy'}: {mb} MB "
                            f"(trần {sp['cap'] // webhook_store.MiB} MB), đĩa còn {free} MB. Khi đầy, Javis trả lỗi tạm "
                            "thời để bên gửi gửi lại sau, không mất sự kiện đã nhận. Xoá bớt nhật ký cũ hoặc tăng đĩa.",
                            f"⚠ The webhook event store is {'full' if sp['level'] == 'full' else 'nearly full'}: {mb} MB "
                            f"(cap {sp['cap'] // webhook_store.MiB} MB), {free} MB free on disk. When full, Javis answers "
                            "a temporary error so senders retry later; no accepted event is lost. Clear old logs or "
                            "add disk.")
        await asyncio.to_thread(self.store().notify_enqueue, f"whsys:space:{sp['level']}:{day}", "system", msg,
                                brain="brain", web=msg[2:], viec={"kind": "webhook", "status": "failed",
                                                                  "title": "webhook store", "id": ""})

    # ── run ──
    async def _heartbeat(self, eid: str, fence: int, run: Optional[asyncio.Task] = None) -> None:
        while True:
            await asyncio.sleep(webhook_store.HEARTBEAT_S)
            try:
                if not await asyncio.to_thread(self.store().heartbeat, eid, fence):
                    if run is not None and not run.done():
                        print(f"[webhooks] {eid}: lease lost, stopping this run", file=sys.stderr)
                        run.cancel()
                    return
            except Exception as e:
                print(f"[webhooks] {eid} heartbeat failed, retrying: {type(e).__name__}: {e}", file=sys.stderr)

    def _ai_hook_ids(self) -> list:
        """Hooks with an AI action (their runs can last long): at most WORKER_MAX - 1 of their events run at once, so
        one slot always stays for code-only hooks (spec §11: a slow hook never starves the others)."""
        return [h["id"] for h in self.store().hooks_all()
                if any(a.get("kind") == "ai" or (a.get("kind") == "plugin" and a.get("allow_ai") is True)
                       for a in webhook_actions.effective(h.get("actions")))]

    async def _run_claimed(self, row: dict) -> None:
        st = self.store()
        eid, fence = row["id"], int(row["fence"])
        loop = asyncio.get_running_loop()
        run = loop.create_task(self._run_event(st, row, eid, fence))
        hb = loop.create_task(self._heartbeat(eid, fence, run))
        try:
            await run
        except asyncio.CancelledError:
            if not hb.done():
                raise
        finally:
            hb.cancel()

    def _backoff(self, tries: int, cfg: dict, retry_after: float, deadline: float, now: float) -> float:
        """Next attempt time, or 0 when the delivery is out of attempts or past its deadline."""
        rc = cfg.get("retry") or {}
        delays = [float(x) for x in (rc.get("delays_s") or RETRY_DELAYS_S)]
        max_attempts = int(rc.get("max_attempts") or webhook_actions.MAX_BRANCH_TRIES)
        if tries >= max_attempts:
            return 0.0
        base = delays[min(tries - 1, len(delays) - 1)]
        j = float(rc.get("jitter_ratio") if rc.get("jitter_ratio") is not None else RETRY_JITTER)
        wait = base * (1 + self.rng.uniform(-j, j))
        if retry_after:
            wait = max(wait, retry_after)
        nxt = now + wait
        if deadline and nxt > deadline:
            return 0.0
        return nxt

    async def _ai_wait(self, cur: dict, hid: str) -> float:
        """0 when the AI budget lets one more run through, else the time the oldest run in the window leaves it."""
        st = self.store()
        now = self.clock()
        per_hour = AI_PER_HOUR_DEFAULT if cur.get("ai_per_hour") is None else int(cur["ai_per_hour"])
        if per_hour == 0:
            return float("inf")
        if await asyncio.to_thread(st.ai_runs_since, hid, now - 3600) >= per_hour:
            return await asyncio.to_thread(st.ai_oldest_since, hid, now - 3600) + 3600.0
        per_day = int(cur.get("ai_per_day") or 0)
        if per_day:
            from webhook_triggers import _day_start
            day0 = _day_start(now)
            if await asyncio.to_thread(st.ai_runs_since, hid, day0) >= per_day:
                return day0 + 86400.0 + 60.0
        if await asyncio.to_thread(st.ai_runs_since, "", now - 3600) >= AI_GLOBAL_PER_HOUR:
            return await asyncio.to_thread(st.ai_oldest_since, "", now - 3600) + 3600.0
        return 0.0

    async def _run_event(self, st, row: dict, eid: str, fence: int) -> None:
        hid = row["hook_id"]
        try:
            cur = await asyncio.to_thread(self._find_hook, hid)
        except Exception as e:
            await asyncio.to_thread(st.requeue_before_dispatch, eid, fence, f"{type(e).__name__}: {e}")
            return
        if cur is None:
            if await asyncio.to_thread(st.finish, eid, fence, "cancelled", "", "hook deleted"):
                await asyncio.to_thread(st.mark_notified, eid, fence)
            return
        try:
            snap = await asyncio.to_thread(self._revision_config, hid, int(row.get("hook_rev") or 0),
                                           row.get("hook_snapshot") or "")
        except Exception as e:
            await asyncio.to_thread(st.requeue_before_dispatch, eid, fence, f"{type(e).__name__}: {e}")
            return
        snap = snap or {}
        # The instruction, targets and rules as they were when the event arrived (its revision); the permission level
        # is the hook's level NOW (spec §3: current permissions are checked before every effect, so a right the owner
        # took away is gone for waiting events, and a level the owner raised to fix a blocked delivery applies).
        from webhook_triggers import VALID_LEVELS, DEFAULT_LEVEL
        hook = dict(cur)
        for k in ("target", "workflow", "text"):
            if snap.get(k) is not None:
                hook[k] = snap[k]
        level = cur.get("level") if cur.get("level") in VALID_LEVELS else DEFAULT_LEVEL
        brain = cur.get("brain") or "brain"
        actions = webhook_actions.effective(snap.get("actions"))
        current = {a["id"]: a for a in webhook_actions.effective(cur.get("actions"))}
        current_has_ai = any(a["kind"] == "ai" for a in current.values())
        merged = []
        for a in actions:
            a = json.loads(json.dumps(a))
            c = current.get(a["id"])
            if a.get("headers") and c is not None and webhook_actions.same_target(a, c):
                a["headers"] = {k: (c.get("headers") or {}).get(k, v) for k, v in a["headers"].items()}
            if c is not None and a["kind"] in webhook_actions.OUTSIDE + ("tool",):
                # Retry safety is the LOWER of then and now (an owner who stops trusting the receiver's dedup wins).
                if not (webhook_actions.retry_safe(a) and webhook_actions.retry_safe(c)):
                    a["retry_safety"], a["retry"] = "manual_on_ambiguous", "never"
            if c is not None and a["kind"] == "plugin":
                # A plugin's AI grant is a permission: it must hold both when the event arrived and now (spec §3).
                a["allow_ai"] = a.get("allow_ai") is True and c.get("allow_ai") is True
            merged.append(a)
        actions = merged
        rows = await asyncio.to_thread(st.branches_init, eid, fence, actions, webhook_actions.delivery_id)
        if rows is None:
            return
        body = bytes(row.get("body") or b"")
        ct = row.get("content_type") or ""
        fields = webhook_store._loads(row.get("fields"), {})
        trace = webhook_store._loads(row.get("trace"), {})
        now = self.clock()
        by_id = {b["action_id"]: b for b in rows}
        todo, doomed = [], []
        for b in rows:
            if b["status"] not in ("pending", "retry") or float(b["next_at"] or 0) > now + 0.5:
                continue
            ds = dep_state(b, by_id)
            if ds == "ready":
                todo.append(b)
            elif ds == "doomed":
                doomed.append(b)
        for b in doomed:
            await asyncio.to_thread(st.branch_finish, eid, fence, b["action_id"], "cancelled", webhook_store.DEP_CANCEL)
        by_action = {a["id"]: a for a in actions}
        payload = webhook_rules.parse_payload(body, ct)[0]
        base = {"event_id": eid, "hook_id": hid, "received_at": float(row.get("received_at") or now), "brain": brain,
                "source": row.get("source") or "http", "fields": fields, "body": body, "content_type": ct,
                "payload": payload, "generation": int(row.get("generation") or 1),
                "revision": int(row.get("hook_rev") or 0) or None, "business_key": row.get("biz_key") or "",
                "verified": {"provider": (trace.get("event") or {}).get("provider", "none"),
                             "verified_at": row.get("verified_at") or 0, "key_version": row.get("key_version") or ""}}
        ai_out = {"result": "", "error": "", "ran": False}
        sent: set = set()                   # deliveries whose dispatch is recorded (they may have acted)

        async def branch(b: dict) -> None:
            a = by_action.get(b["action_id"]) or {"id": b["action_id"], "kind": b["kind"]}
            aid = a["id"]

            async def close(status, detail, nxt=0.0):
                await asyncio.to_thread(st.branch_finish, eid, fence, aid, status, detail, None, "", nxt)

            gone = (not current_has_ai) if a["kind"] == "ai" else not webhook_actions.same_target(a, current.get(aid))
            if gone:
                # Never sent to a target the event was not received for (its secrets were bound to the old one): the
                # owner sends it with the current setup through "Process again", which previews first.
                return await close("cancelled", "action removed or changed since the event arrived: use Process "
                                   "again with the current setup to send it there")
            if any(isinstance(v, str) and v == "••••" for v in (a.get("headers") or {}).values()):
                return await close("blocked", "a header secret of this action is missing: enter it again")
            ctx = dict(base, action_id=aid, delivery_id=b["delivery_id"], attempt=int(b.get("tries") or 0) + 1)
            found = None
            if a["kind"] == "plugin":
                found = await asyncio.to_thread(self._plugin_handler, brain, a["plugin"], a["handler"])
                pre = webhook_actions.plugin_precheck(a, found, level, ctx)
                if pre:
                    return await close(pre.status, pre.detail)
                if webhook_actions.plugin_busy(b["delivery_id"]):
                    if float(b.get("deadline") or 0) and now > float(b["deadline"]):
                        # Its earlier call never came back: past the deadline the owner is told instead of a silent
                        # wait. It may have acted (that call may still finish): unknown, never resent by itself.
                        return await close("unknown", "the plugin's earlier call of this delivery never returned "
                                           "before the deadline: check the plugin, then Retry or Mark done")
                    return await close("retry", "not sent: the previous call of this delivery is still running", now + 60)
                if not webhook_actions.plugin_slot_free(a["plugin"], found):
                    # Its turn has not come (this plugin, or all plugins, are busy): no attempt is spent, but the wait
                    # is bounded by the delivery's deadline. Past it the delivery fails (it was never sent) and the
                    # owner is told: a plugin whose calls hang must not hold its deliveries forever, unseen.
                    if float(b.get("deadline") or 0) and now > float(b["deadline"]):
                        return await close("failed", "not sent: the plugin's earlier calls kept hanging until the "
                                           "deadline (check the plugin, then Retry)")
                    return await close("retry", "not sent yet: plugin handlers are busy", now + 30)
            elif a["kind"] != "ai":
                why = webhook_actions.level_ok(a, level)
                if why:
                    return await close("blocked", why)
            if (a.get("approve") or (current.get(aid) or {}).get("approve")) and not float(b.get("approved_at") or 0):
                await close("approval", "waiting for your approval")
                await self._approval_notice(cur, eid, [aid])
                return
            if a.get("headers"):
                try:
                    a = dict(a, headers=await asyncio.to_thread(
                        lambda: {k: self._secret(v, f"{hid}/a/{aid}/{k}") for k, v in a["headers"].items()}))
                except Exception as e:
                    return await close("blocked", f"a header secret is not available ({type(e).__name__}): enter it again")
            args = None
            if a["kind"] == "tool":
                try:
                    args = webhook_actions.tool_args(a, ctx)
                except webhook_rules.TemplateError as e:
                    return await close("failed", f"not sent: {e}")
            ai_call = a["kind"] == "ai" or (a["kind"] == "plugin" and bool((found or {}).get("ai")))
            if a["kind"] == "ai" and self.deps.brain_exists and not self.deps.brain_exists(brain):
                return await close("blocked", "the webhook's brain folder no longer exists")
            if ai_call:
                wait = await self._ai_wait(cur, hid)
                if wait == float("inf"):
                    return await close("blocked", "the AI budget of this webhook is 0: raise it to run AI actions")
                if wait:
                    # Spec §7: an engine not called because of the quota WAITS for it; not a try, not a model call.
                    return await close("retry", "waiting for the AI budget (runs per hour)", wait)
            tk = webhook_actions.target_key(a) if a["kind"] != "ai" else ""
            if tk:
                open_until = await asyncio.to_thread(st.breaker_open_until, "*", tk)
                if open_until:
                    return await close("retry", "paused: this receiver failed several times in a row", open_until)
            safe = webhook_actions.retry_safe(a) or (a["kind"] == "plugin" and bool((found or {}).get("idempotent")))
            held = None
            if a["kind"] == "plugin":
                # The slot is taken here, in one step with the check, so a delivery that lost the race for the last
                # slot waits like any other (no attempt spent) instead of being dispatched and then refused.
                held = webhook_actions.plugin_reserve(a["plugin"], found)
                if held is False:
                    if float(b.get("deadline") or 0) and now > float(b["deadline"]):
                        return await close("failed", "not sent: the plugin's earlier calls kept hanging until the "
                                           "deadline (check the plugin, then Retry)")
                    return await close("retry", "not sent yet: plugin handlers are busy", now + 30)
            try:
                ok = await asyncio.to_thread(st.branch_dispatch, eid, fence, aid, self.worker_id, safe,
                                             webhook_actions.request_fingerprint(a, ctx), ai_call)
            except BaseException:
                if held:
                    webhook_actions.plugin_unreserve(a["plugin"])
                raise
            if not ok:
                if held:
                    webhook_actions.plugin_unreserve(a["plugin"])
                return
            sent.add(aid)
            if a["kind"] == "ai":
                status, detail, result = await self._run_ai(hook, brain, level, body, ct, base, fields, b)
                ai_out.update(result=result, error=detail if status == "failed" else "", ran=True)
                webhook_store._crash("after_dispatch")
                # A failed AI run may already have called tools (a timeout mid-turn at level full): it counts as maybe
                # acted, so deleting the event never gives the order back for a second run.
                await self._branch_finish(st, eid, fence, aid, status, detail, {}, result,
                                          maybe_acted=True if status == "failed" else None)
                return
            try:
                if a["kind"] == "http":
                    out = await webhook_actions.run_http(a, ctx, self.deps.http_transport, self.deps.resolve)
                elif a["kind"] == "apps_script":
                    out = await webhook_actions.run_apps_script(a, ctx, self.deps.http_transport, self.deps.resolve)
                elif a["kind"] == "tool":
                    out = await webhook_actions.run_tool(a, ctx, self.deps.call_tool, level, args)
                else:
                    out = await webhook_actions.run_plugin(a, ctx, found, level, reserved=bool(held))
            except Exception as e:
                out = webhook_actions.Outcome("unknown", f"{type(e).__name__}: {e}"[:300], maybe_acted=True)
            webhook_store._crash("after_dispatch")
            secrets_used = [v for v in (a.get("headers") or {}).values() if isinstance(v, str) and len(v) >= 4]
            if secrets_used:
                def red(t):
                    t = str(t or "")
                    for sv in secrets_used:
                        t = t.replace(sv, "••••")
                    return t
                out.detail = red(out.detail)
                out.receipt = json.loads(red(json.dumps(out.receipt, ensure_ascii=False, default=str)))
            status, nxt = out.status, 0.0
            if status == "retry":
                tries = int(b.get("tries") or 0) + 1
                nxt = self._backoff(tries, snap, out.retry_after, float(b.get("deadline") or 0), self.clock())
                if not nxt:
                    # Out of attempts or past the deadline: certain "not done" stays dead (failed); after a send that
                    # may have acted, the owner reconciles (unknown).
                    status = "failed" if out.maybe_acted is False else "unknown"
                    out.detail = f"{out.detail} (gave up after {tries} attempts)"
            await self._branch_finish(st, eid, fence, aid, status, out.detail, out.receipt, "", nxt,
                                      http_status=out.http_status, maybe_acted=out.maybe_acted)
            try:
                changed = ""
                if not tk:
                    pass
                elif status in ("completed", "accepted"):
                    changed = await asyncio.to_thread(st.breaker_record, "*", tk, True)
                elif status in ("retry", "unknown"):
                    changed = await asyncio.to_thread(st.breaker_record, "*", tk, False)
                if changed == "opened":
                    await self._breaker_notice(cur, aid, out.detail)
            except Exception as e:
                print(f"[webhooks] breaker {hid}/{aid}: {type(e).__name__}: {e}", file=sys.stderr)

        async def guarded(b: dict) -> None:
            try:
                await branch(b)
            except Exception as e:
                # A fault in Javis itself. After the dispatch was recorded the delivery may already have acted: the
                # owner decides (unknown). Before it nothing was sent: it is tried again shortly, within its deadline.
                # The other deliveries keep running under the heartbeat (gather waits for all of them).
                aid = b["action_id"]
                print(f"[webhooks] {eid}/{aid} crashed: {type(e).__name__}: {e}", file=sys.stderr)
                if aid in sent:
                    status, detail, nxt = ("unknown", f"internal error while it ran ({type(e).__name__}): it may have "
                                           "acted", 0.0)
                elif float(b.get("deadline") or 0) and now > float(b["deadline"]):
                    status, detail, nxt = "failed", f"not sent: internal error ({type(e).__name__}) until the deadline", 0.0
                else:
                    status, detail, nxt = "retry", f"not sent yet: internal error ({type(e).__name__})", now + 60
                try:
                    await asyncio.to_thread(st.branch_finish, eid, fence, aid, status, detail, None, "", nxt)
                except Exception:
                    pass

        await asyncio.gather(*(guarded(b) for b in todo))
        final = ""
        delay = 0.5
        for i in range(5):
            try:
                final, _ = await asyncio.to_thread(self._settle, st, eid, fence, actions, ai_out)
                break
            except Exception as e:
                if i == 4:
                    raise
                print(f"[webhooks] {eid} settle failed, retrying: {type(e).__name__}: {e}", file=sys.stderr)
                await asyncio.sleep(delay)
                delay *= 2
        if final == "queued":
            self._kick()
            return
        if not final:
            print(f"[webhooks] {eid}: the event was taken over; delivery outcomes are kept on the deliveries",
                  file=sys.stderr)
            return
        rows = await asyncio.to_thread(st.branches, eid)
        ai_failed = bool(ai_out.get("ran")) and any(r["kind"] == "ai" and r["status"] == "failed" for r in rows)
        if ai_failed and self.deps.incident_hook and self._ai_triage(cur):
            # Incident triage may call a model: only for a failed AI action, only when the hook turned triage on, and
            # it counts in the same AI ledger (spec §12).
            try:
                await asyncio.to_thread(st.ai_record, hid, eid)
                result, error = self._event_text(rows, actions, ai_out)
                self.deps.incident_hook("webhook", hid, brain=brain, title=str(cur.get("name") or ""),
                                        error=ai_out["error"] or error,
                                        request=str(hook.get("text") or hook.get("workflow") or ""))
            except Exception:
                pass
        await asyncio.to_thread(st.hook_ran, hid, final)
        if final in ("silent", "cancelled"):
            await asyncio.to_thread(st.mark_notified, eid, fence)
            return
        ev = await asyncio.to_thread(st.get, eid)
        await self._notify(dict(ev, fence=fence) if ev else {"id": eid, "hook_id": hid, "status": final, "fence": fence})

    def _settle(self, st, eid, fence, actions, ai_out):
        return st.settle(eid, fence, lambda r: self._event_text(r, actions, ai_out))

    @staticmethod
    def _ai_triage(h: dict) -> bool:
        """Spec §12: `ai_triage` false stops the model triage of incidents. Hooks created before 0.274.0 kept the
        0.199.0 behaviour (on) unless the owner turns it off; new hooks start with it off."""
        v = h.get("ai_triage")
        return bool(v) if v is not None else bool(h.get("legacy"))

    async def _run_ai(self, hook: dict, brain: str, level: str, body: bytes, ct: str, base: dict,
                      fields: dict, b: dict) -> tuple:
        """The hook's task or workflow: the only delivery that calls a model. The event and delivery ids go into the
        prompt (spec §8.4): the run is tied to them in the workflow history. Returns (status, detail, result)."""
        from webhook_triggers import event_prompt, payload_text, _is_silent
        prompt = event_prompt(hook, payload_text(body, ct), base["received_at"], fields,
                              ids={"event": base["event_id"], "delivery": b.get("delivery_id", "")})
        result, error, needs_input = "", "", False
        try:
            if hook.get("target") == "workflow":
                result, error, needs_input = await self.deps.run_workflow(brain, hook.get("workflow", ""), prompt, level)
            else:
                result, error = await self.deps.run_task(brain, prompt, level)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
        if error and not result:
            return "failed", str(error)[:1000], ""
        if needs_input:
            return "waiting", "", result
        if error:
            # A partial result WITH an error is not "done" (spec §15 AI row): the owner decides what happened.
            return "unknown", f"partial result with an error: {str(error)[:600]}", result
        return ("silent" if _is_silent(result) else "completed"), "", result

    async def _branch_finish(self, st, eid, fence, aid, status, detail, receipt, result, next_at=0.0,
                             http_status=0, maybe_acted=None) -> None:
        delay = 0.5
        for i in range(5):
            try:
                if not await asyncio.to_thread(st.branch_finish, eid, fence, aid, status, detail, receipt, result,
                                               next_at, None, http_status, maybe_acted):
                    await asyncio.to_thread(st.branch_late, eid, aid, status, detail, receipt, result)
                return
            except Exception as e:
                if i == 4:
                    raise
                print(f"[webhooks] {eid}/{aid} delivery finish failed, retrying: {type(e).__name__}: {e}",
                      file=sys.stderr)
                await asyncio.sleep(delay)
                delay *= 2

    @staticmethod
    def _event_text(rows: list, actions: list, ai_out: dict) -> tuple:
        """(result, error) of the whole event for the log and the notice. One AI delivery alone reads as before."""
        if len(rows) == 1 and rows[0]["kind"] == "ai":
            r = rows[0]
            return str(r.get("result") or ""), (str(r.get("detail") or "") if r["status"] in ("failed", "unknown",
                                                                                              "blocked") else "")
        ok, bad = [], []
        for r in rows:
            line = f"{r['action_id']}: {webhook_store.spec_delivery_state(r['status'])}"
            d = str(r.get("detail") or "").strip()
            if d:
                line += f" ({d[:160]})"
            (bad if r["status"] in ("failed", "unknown", "blocked") else ok).append(line)
            if r["kind"] == "ai" and r.get("result") and r["status"] != "silent":
                ok.append(str(r["result"])[:1500])
        return "\n".join(ok), "\n".join(bad)

    def _plugin_handler(self, brain: str, slug: str, name: str) -> Optional[dict]:
        if not self.deps.plugin_handler:
            return None
        try:
            return self.deps.plugin_handler(brain, slug, name)
        except Exception as e:
            print(f"[webhooks] plugin handler lookup {slug}/{name} failed: {type(e).__name__}: {e}", file=sys.stderr)
            return None

    # ── notices (all through the durable outbox) ──
    async def deliver_notifications(self) -> int:
        st = self.store()
        sent = 0
        for n in await asyncio.to_thread(st.notify_due, self.clock()):
            try:
                res = await self.deps.send(n["chat_id"], n["text"], viec=webhook_store._loads(n["viec"], {}),
                                           web=n["web"], brain=n["brain"] or "brain", dedup=n["dkey"])
                ok = not (isinstance(res, tuple) and res and not res[0])
                err = "" if ok else str(res[1] if isinstance(res, tuple) and len(res) > 1 else "not delivered")
            except Exception as e:
                ok, err = False, f"{type(e).__name__}: {e}"
            await asyncio.to_thread(st.notify_result, n["id"], ok, err, self.clock())
            sent += ok
        return sent

    async def _enqueue(self, dkey, kind, text, h, eid="", mark=None, status="", web=None) -> None:
        await asyncio.to_thread(
            self.store().notify_enqueue, dkey, kind, text, hook_id=str(h.get("id") or ""), event_id=eid,
            chat_id=h.get("chat_id", ""), brain=h.get("brain") or "brain",
            web=web if web is not None else (text[2:] if text.startswith("⚠ ") else text),
            viec={"kind": "webhook", "status": status or kind, "title": str(h.get("name") or "")[:160],
                  "id": str(h.get("id") or "")}, mark_event=mark)

    async def _approval_notice(self, h: dict, eid: str, aids: list) -> None:
        if (h.get("notify") or "all") == "none":
            return
        name = h.get("name") or h.get("id")
        names = ", ".join(aids)
        msg = localefmt.chu(f"Webhook \"{name}\" cần bạn duyệt trước khi chạy: {names}. Mở nhật ký webhook, bấm "
                            "Chi tiết rồi Duyệt hoặc Từ chối.",
                            f"Webhook \"{name}\" needs your approval before it runs: {names}. Open the webhook log, "
                            "press Details, then Approve or Reject.")
        try:
            await self._enqueue(f"wha:{eid}:{','.join(sorted(aids))}", "approval", msg, h, eid, status="waiting")
            await self.deliver_notifications()
        except Exception as e:
            print(f"[webhooks] approval notice failed: {type(e).__name__}: {e}", file=sys.stderr)

    async def _breaker_notice(self, h: dict, aid: str, detail: str) -> None:
        """Once per opening: the owner learns a receiver is paused. Plain text, no model. Every mode except none."""
        if (h.get("notify") or "all") == "none":
            return
        name = h.get("name") or h.get("id")
        msg = localefmt.chu(f"⚠ Webhook \"{name}\": nơi nhận \"{aid}\" lỗi {webhook_store.BREAKER_FAILS} lần liền nên "
                            f"Javis tạm ngừng gửi tới đó một lúc rồi thử lại. Lỗi cuối: {detail[:200]}",
                            f"⚠ Webhook \"{name}\": receiver \"{aid}\" failed {webhook_store.BREAKER_FAILS} times in a "
                            f"row, so Javis pauses sending there for a while, then tries again. Last error: "
                            f"{detail[:200]}")
        await self._enqueue(f"whb:{h.get('id')}:{aid}:{int(self.clock() // 600)}", "breaker", msg, h, status="failed")
        await self.deliver_notifications()

    def _incident(self, h: dict, ev: dict, prefix: str = "inc", defer: bool = False) -> tuple:
        """errors_only grouping (spec §12): (send?, text suffix). The same failure again (same action, same kind of
        error) while an incident is open is not told again until INCIDENT_REPEAT_S passed; a different failure is.
        `prefix` "qinc" keeps quarantines apart: a run that succeeds does not close them. `defer`: when it sends, the
        new state is returned as a third item instead of written, so the caller writes it only once the notice is
        queued (a crash in between must not mark a notice told that never went out)."""
        import re
        st = self.store()

        def kind(text: str) -> str:
            # The KIND of failure, not its wording: numbers (order ids, HTTP 502 vs 504) and quoted values do not make
            # a new incident, so one receiver failing for six orders is one notice (spec §12).
            t = re.sub(r"\d+", "#", str(text or "").lower())
            t = re.sub(r"\"[^\"]*\"|'[^']*'", "…", t)
            return t.split(":")[0][:40]
        bad = [b for b in ev.get("branches") or [] if b.get("status") in ("failed", "unknown", "blocked")]
        sig = ",".join(sorted(f"{b['action_id']}:{b['status']}:{kind(b.get('detail'))}" for b in bad)) \
            or f"event:{ev.get('status')}:{kind(ev.get('error'))}"
        key = f"{prefix}:{h.get('id')}"
        cur = webhook_store._loads(st.meta_get(key), {})
        now = self.clock()
        # Every open kind is remembered (two errors that alternate are not told again each time), oldest dropped.
        sigs = {k: float(v) for k, v in (cur.get("sigs") or ({cur["sig"]: cur.get("told_at") or 0} if cur.get("sig")
                                                               else {})).items()}
        # `count`: failures of the whole incident (told in the recovery notice); `untold`: those since the last notice.
        total = int(cur.get("count") or 0) + 1
        if sig in sigs and now - sigs[sig] < INCIDENT_REPEAT_S:
            cur.update(count=total, sigs=sigs, sig=sig, untold=int(cur.get("untold") or 0) + 1)
            st.meta_set(key, json.dumps(cur))
            return False, ""
        n = int(cur.get("untold") or 0)
        sigs[sig] = now
        sigs = dict(sorted(sigs.items(), key=lambda kv: kv[1])[-20:])
        state = json.dumps({"sig": sig, "sigs": sigs, "count": total, "untold": 0, "since": cur.get("since") or now,
                            "told_at": now})
        suffix = (localefmt.chu(f" (thêm {n} lần lỗi không báo riêng từ lần báo trước)", f" ({n} more failures "
                                "since the last notice)") if n > 0 else "")
        if defer:
            return True, suffix, (key, state)
        st.meta_set(key, state)
        return True, suffix

    async def _notify(self, ev: dict) -> None:
        """Notices of one hook are decided one at a time in this process: the incident state is read, the notice
        queued, then the state written, so two events failing together are one notice, not two."""
        locks = self.__dict__.setdefault("_notify_locks", {})
        lock = locks.setdefault(str(ev.get("hook_id") or ""), asyncio.Lock())
        async with lock:
            await self._notify_one(ev)
        # Sending goes over the network: never while holding the hook's lock (the pump would wait behind it).
        await self.deliver_notifications()

    async def _notify_one(self, ev: dict) -> None:
        """Queue the owner notice of a finished event under the modes (spec §12). The dedup key names the ATTEMPT
        (fence): a notice queued again after a crash is the same key, the result of an owner's Retry is a new one."""
        st = self.store()
        hid = str(ev.get("hook_id") or "")
        h = await asyncio.to_thread(self._find_hook, hid) or {}
        status = str(ev.get("status") or "")
        fence = ev.get("fence")
        fence = int(fence) if fence is not None else None
        mark = (ev["id"], fence)
        if status in ("silent", "cancelled") or not h:
            await asyncio.to_thread(st.mark_notified, ev["id"], fence)
            return
        name = h.get("name") or hid
        mode = h.get("notify") or "all"
        needs_you = status in ("unknown", "waiting", "blocked")
        is_error = status in ("failed", "dead")
        if status == "invalid":
            # A quarantine is told in every mode but none and the digest, and always grouped (by hook and kind of
            # reason): a broken rule on a busy shop is one notice, never one per event (spec §12).
            if mode not in ("none", "daily_digest"):
                send, suffix, *later = await asyncio.to_thread(self._incident, h, ev, "qinc", True)
                if send:
                    msg = localefmt.chu(
                        f"⚠ Webhook \"{name}\": sự kiện bị cách ly vì quy tắc không đọc được ("
                        f"{str(ev.get('error') or '')[:200]}). Nội dung được giữ lại. Sửa quy tắc rồi bấm Chạy lại với "
                        "cấu hình hiện tại, hoặc Xoá nếu không cần.",
                        f"⚠ Webhook \"{name}\": events are quarantined because the rules could not read them ("
                        f"{str(ev.get('error') or '')[:200]}). Their bodies are kept. Fix the rules, then press "
                        "Process again with the current setup, or Delete them if not needed.") + suffix
                    await self._enqueue(f"wh:{hid}:{ev['id']}:{fence}", "event", msg, h, ev["id"], mark, status)
                    if later:
                        await asyncio.to_thread(st.meta_set, *later[0])
                    pass   # delivered by _notify, outside the hook's lock
                    return
            await asyncio.to_thread(st.mark_notified, ev["id"], fence)
            return
        if mode == "none" or (mode == "errors_only" and not (is_error or needs_you)) or \
                (mode == "daily_digest" and not needs_you):
            if mode == "errors_only" and status == "done":
                cur = webhook_store._loads(await asyncio.to_thread(st.meta_get, f"inc:{hid}"), {})
                if cur.get("sig"):
                    # The incident is over: say so once (a state change worth telling), then forget it.
                    await asyncio.to_thread(st.meta_del, f"inc:{hid}")
                    msg = localefmt.chu(f"Webhook \"{name}\" đã chạy bình thường trở lại sau {cur.get('count', 1)} lần "
                                        "lỗi.", f"Webhook \"{name}\" runs normally again after {cur.get('count', 1)} "
                                        "failures.")
                    await self._enqueue(f"whr:{hid}:{ev['id']}", "recovered", msg, h, ev["id"], mark, "done")
                    pass   # delivered by _notify, outside the hook's lock
                    return
            await asyncio.to_thread(st.mark_notified, ev["id"], fence)
            return
        suffix = ""
        inc_later: list = []
        if mode == "errors_only" and (is_error or status in ("blocked", "unknown")):
            # Repeated failures, blocks and unclear outcomes of one hook are one incident, told again only when it
            # changes or after INCIDENT_REPEAT_S (spec §12). An approval stays one notice per event: each one asks.
            send, suffix, *inc_later = await asyncio.to_thread(self._incident, h, ev, "inc", True)
            if not send:
                await asyncio.to_thread(st.mark_notified, ev["id"], fence)
                return
        branches = ev.get("branches") or []
        appr = sorted(b["action_id"] for b in branches if b.get("status") == "approval")
        if is_error:
            partial = any(b.get("status") in webhook_store.BRANCH_OK for b in branches)
            head = localefmt.chu(f"⚠ Webhook \"{name}\" chạy được một phần, phần lỗi: " if partial else
                                 f"⚠ Webhook \"{name}\" chưa chạy được: ",
                                 f"⚠ Webhook \"{name}\" partly ran, failed part: " if partial else
                                 f"⚠ Webhook \"{name}\" could not run: ")
            msg = head + str(ev.get("error") or "")[:300] + suffix
        elif status == "waiting" and appr:
            msg = localefmt.chu(f"Webhook \"{name}\" cần bạn duyệt trước khi chạy: {', '.join(appr)}. Mở nhật ký "
                                "webhook, bấm Chi tiết rồi Duyệt hoặc Từ chối.",
                                f"Webhook \"{name}\" needs your approval before it runs: {', '.join(appr)}. Open the "
                                "webhook log, press Details, then Approve or Reject.")
        elif status == "blocked":
            msg = localefmt.chu(f"⚠ Webhook \"{name}\" đang chờ bạn sửa cấu hình (khoá, quyền hoặc plugin): ",
                                f"⚠ Webhook \"{name}\" waits for you to fix its configuration (key, permission or "
                                "plugin): ") + str(ev.get("error") or "")[:300] + localefmt.chu(
                " Sửa trong webhook thì nó tự chạy lại; sửa ở bên ngoài (bật plugin, đổi khoá ở nơi nhận) thì bấm "
                "Chạy lại mọi sự kiện bị chặn.", " A fix in the webhook runs it again by itself; after a fix outside "
                "(plugin switched on, key changed at the receiver) press Retry all blocked.")
        elif status == "unknown":
            msg = localefmt.chu(f"⚠ Webhook \"{name}\": không rõ việc đã chạy xong chưa (máy dừng giữa chừng hoặc bên "
                                "nhận không xác nhận). Kiểm tra bên ngoài rồi bấm Chạy lại hoặc Đã xong trong nhật ký "
                                "webhook.",
                                f"⚠ Webhook \"{name}\": not known whether the run finished (the server stopped mid-run "
                                "or a receiver did not confirm). Check outside, then press Retry or Mark done in the "
                                "webhook log.") + (("\n" + str(ev.get("error") or "")[:300]) if ev.get("error") else "")
            if appr:
                msg += localefmt.chu(f"\nCũng đang chờ bạn duyệt: {', '.join(appr)}.",
                                     f"\nAlso waiting for your approval: {', '.join(appr)}.")
        else:
            msg = str(ev.get("result") or "").strip() or localefmt.chu(
                "Webhook đã chạy nhưng không trả về nội dung.", "The webhook ran but returned nothing.")
        dkey = f"wh:{hid}:{ev['id']}:{fence}"
        if status == "waiting" and appr:
            dkey = f"wha:{ev['id']}:{','.join(appr)}"
        await self._enqueue(dkey, "event", msg, h, ev["id"], mark, status)
        if inc_later:
            await asyncio.to_thread(st.meta_set, *inc_later[0])
        pass   # delivered by _notify, outside the hook's lock

    async def _digest(self, now: Optional[float] = None) -> int:
        """`daily_digest`: once a day after DIGEST_HOUR in the hook's time zone (its `digest_timezone`, else the
        owner's), one plain message per hook counting the last day. Built from counts only: no model. The outbox key
        `whd:<hook>:<day>` makes a restart send at most one per period."""
        from webhook_triggers import _local
        now = self.clock() if now is None else now
        st = self.store()
        n = 0
        for h in await asyncio.to_thread(st.hooks_all):
            if (h.get("notify") or "all") != "daily_digest":
                continue
            hid = h["id"]
            lt = _local(now, h.get("digest_timezone"))
            if lt.hour < DIGEST_HOUR:
                continue
            today = lt.strftime("%Y-%m-%d")
            try:
                if await asyncio.to_thread(st.meta_get, f"digest_day:{hid}") == today:
                    continue
                # From the last digest's cursor, so days the server was off are counted in this one catch-up digest
                # (spec §12: at most one per period), bounded to a week; the first digest covers the last day.
                cursor = float(await asyncio.to_thread(st.meta_get, f"digest_at:{hid}") or 0)
                since = max(cursor, now - 7 * 86400) if cursor else now - 86400
                hours = max(1, int(round((now - since) / 3600)))
                c = await asyncio.to_thread(st.finished_counts, hid, since, now)
                ran = sum(c.get(k, 0) for k in ("done", "silent"))
                bad = sum(c.get(k, 0) for k in ("failed", "dead", "unknown", "blocked"))
                skipped = sum(c.get(k, 0) for k in ("filtered", "invalid", "duplicate"))
                waiting = c.get("waiting", 0)
                if ran or bad or skipped or waiting:
                    name = h.get("name") or hid
                    part = c.get("partial_failed", 0)
                    span_vi = "24 giờ qua" if hours <= 25 else f"{hours} giờ qua (từ bản tóm tắt trước)"
                    span_en = "the last 24 hours" if hours <= 25 else f"the last {hours} hours (since the last digest)"
                    msg = localefmt.chu(f"Webhook \"{name}\" trong {span_vi}: {ran} lần chạy xong, {bad} lần lỗi hoặc "
                                        f"chưa rõ ({part} chạy được một phần), {waiting} đang chờ bạn, {skipped} sự "
                                        "kiện bị lọc, trùng hoặc cách ly.",
                                        f"Webhook \"{name}\" in {span_en}: {ran} runs done, {bad} failed or "
                                        f"unknown ({part} partly), {waiting} waiting for you, {skipped} events "
                                        "filtered, duplicate or quarantined.")
                    await self._enqueue(f"whd:{hid}:{today}", "digest", msg, h, status="digest")
                    n += 1
                await asyncio.to_thread(st.meta_set, f"digest_day:{hid}", today)
                await asyncio.to_thread(st.meta_set, f"digest_at:{hid}", str(now))
            except Exception as e:
                print(f"[webhooks] digest of {hid} failed: {type(e).__name__}: {e}", file=sys.stderr)
        if n:
            await self.deliver_notifications()
        return n
