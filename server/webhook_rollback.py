"""webhook_rollback.py - prepare a rollback of the webhook platform to an older build (0.274.0, spec §13).

    python server/webhook_rollback.py --state-dir <STATE_DIR> [--check] [--force]

Since 0.274.0 the hooks live in `webhook_events.sqlite3` and `webhooks.json` was moved aside, so an older build started
by mistake finds no stale hook list to run beside the new store. A deliberate rollback runs this tool FIRST, with the
server stopped:

  1. refuses while a worker still holds a live lease (a server is running), unless --force;
  2. backs the store up with SQLite's backup API (`webhook_events.backup-<time>.sqlite3`, mode 600);
  3. exports every event not settled yet (received, queued, running, unknown, waiting, blocked), with its body and its
     deliveries, to `webhook_rollback-<time>/backlog.jsonl` (mode 600): the older build cannot run them, the owner
     reconciles them from this file;
  4. writes a `webhooks.json` the older build reads (id, name, brain, chat, token hash, target, workflow, text, level,
     enabled, recent delivery keys). A hook that uses what the older build does not have (actions other than its own
     task, rules, provider signatures) is written SWITCHED OFF, so the older build never runs something other than what
     was configured;
  5. records each hook's own switches (enabled, paused) and which hooks it switched off, then clears the migration
     marker: the next upgrade imports that file again (changes made meanwhile are kept), gives each hook back its own
     switch, and stops receiving on a hook the older build deleted;
  6. holds every exported event as unknown, so an upgrade later never runs it beside a manual resend;
  7. writes `report.txt` saying what will not run on the older build.

A paused hook is written switched off too: the older build cannot store events without running them.

`--check` writes nothing and prints the report. The store itself is left in place (the next upgrade uses it); nothing
here deletes data. Rolling back the binary does not undo what actions already did outside: reconcile receipts first.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import webhook_store  # noqa: E402

LEGACY_FIELDS = ("id", "name", "brain", "chat_id", "enabled", "token_hash", "target", "workflow", "text", "level",
                 "created_at", "count", "last_at", "last_status", "history")


def _private_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, 0o600)


def legacy_hook(h: dict, keys: list) -> tuple:
    """(hook as the older build reads it, reasons it cannot run there as configured)."""
    why = []
    acts = [a for a in h.get("actions") or [] if a.get("kind") != "ai"]
    if acts:
        why.append("actions " + ", ".join(f"{a['id']} ({a['kind']})" for a in acts))
    # The older build runs the hook's own task on every event, with no approval and no condition: an AI action that
    # carries anything more (approval, `when`, an order, retry settings) cannot run there as configured.
    for a in h.get("actions") or []:
        extra = sorted(k for k, v in a.items() if k not in ("id", "kind")
                       and not (v is None or v is False or (isinstance(v, (str, dict, list)) and not v))) \
            if a.get("kind") == "ai" else []
        if extra:
            why.append(f"AI action {a.get('id')} with {', '.join(extra)}")
    if h.get("rules"):
        why.append("rules (filter, mapping, business keys)")
    if (h.get("verify") or {}).get("provider") not in (None, "", "none"):
        why.append(f"signature check {h['verify']['provider']}")
    if h.get("token_header") and str(h["token_header"]).lower() != "x-javis-token":
        why.append(f"token header {h['token_header']}")
    if h.get("target") not in ("task", "workflow"):
        why.append("no task or workflow of its own")
    if h.get("paused"):
        why.append("processing paused (the older build has no pause)")
    out = {k: h.get(k) for k in LEGACY_FIELDS if h.get(k) is not None}
    out["count"] = int(h.get("count") or 0)
    out["seen_keys"] = keys[-50:]
    if why:
        out["enabled"] = False
    return out, why


def run(state_dir: Path, check: bool = False, force: bool = False, now: float = 0.0) -> dict:
    now = now or time.time()
    db = state_dir / "webhook_events.sqlite3"
    if not db.exists():
        return {"ok": False, "error": "no webhook store in this state folder"}
    st = webhook_store.Store(db)
    try:
        leases = st.live_leases(now)
        if leases and not force:
            return {"ok": False, "error": f"{leases} event(s) are running under a live lease: stop the server first "
                                          "(or pass --force if it is certainly stopped)"}
        if st.meta_get("rolled_back_at") and not st.meta_get("hooks_migrated") and not force:
            return {"ok": False, "error": "a rollback was already prepared and no newer build has run since: running it "
                                          "again would overwrite webhooks.json and lose what the older build changed "
                                          "(pass --force if that file is not in use)"}
        hooks = st.hooks_all()
        open_ev = st.open_events()
        legacy, blocked = [], {}
        for h in hooks:
            keys = [r[0][2:] for r in st._db.execute(
                "SELECT idem_key FROM dedup WHERE hook_id=? AND idem_key LIKE 'h:%' ORDER BY created_at", (h["id"],))]
            lh, why = legacy_hook(h, keys)
            legacy.append(lh)
            if why:
                blocked[h["id"]] = why
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
        out_dir = state_dir / f"webhook_rollback-{stamp}"
        lines = [f"Webhook rollback report ({time.strftime('%Y-%m-%d %H:%M', time.localtime(now))})", "",
                 f"Hooks: {len(hooks)}. Written switched off for the older build: {len(blocked)}."]
        for hid, why in blocked.items():
            lines.append(f"  - {hid}: uses {'; '.join(why)}")
        lines += ["", f"Events not settled: {len(open_ev)} (the older build has no event store and will not run them;"
                      " reconcile them from backlog.jsonl)."]
        for e in open_ev[:200]:
            lines.append(f"  - {e['id']} hook {e['hook_id']} {e['status']} received "
                         f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(e['received_at']))}")
        lines += ["", "These events are now held as unknown: after an upgrade they wait for Mark done or Retry, never run"
                      " on their own.",
                  "Actions already done outside are not undone by a rollback: check receipts before resending."]
        report = "\n".join(lines) + "\n"
        if check:
            return {"ok": True, "check": True, "report": report, "hooks": len(hooks), "blocked": blocked,
                    "open_events": len(open_ev)}
        backup = st.backup(state_dir / f"webhook_events.backup-{stamp}.sqlite3")
        rows = []
        for e in open_ev:
            ev = st.get(e["id"], True)
            body = bytes(ev.pop("body", b"") or b"")
            ev["body_text"] = body.decode("utf-8", "replace")
            rows.append(json.dumps(ev, ensure_ascii=False, default=str))
        _private_write(out_dir / "backlog.jsonl", "\n".join(rows) + ("\n" if rows else ""))
        _private_write(state_dir / "webhooks.json", json.dumps({"hooks": legacy}, ensure_ascii=False, indent=1))
        st.meta_set("rollback_state", json.dumps({
            "at": now, "hooks": [h["id"] for h in hooks], "forced_off": sorted(blocked),
            "enabled": {h["id"]: bool(h.get("enabled", True)) for h in hooks},
            "paused": {h["id"]: bool(h.get("paused")) for h in hooks}}))
        held = st.hold_for_rollback([e["id"] for e in open_ev], now)
        st.meta_del("hooks_migrated")
        st.meta_set("rolled_back_at", str(now))
        _private_write(out_dir / "report.txt", report)
        return {"ok": True, "backup": str(backup), "out_dir": str(out_dir), "hooks": len(hooks), "blocked": blocked,
                "open_events": len(open_ev), "held": held, "report": report}
    finally:
        st.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Prepare a rollback of the Javis webhook platform to an older build.")
    ap.add_argument("--state-dir", required=True)
    ap.add_argument("--check", action="store_true", help="only print what would happen")
    ap.add_argument("--force", action="store_true", help="go on although a lease looks live (server certainly stopped)")
    a = ap.parse_args(argv)
    res = run(Path(a.state_dir), check=a.check, force=a.force)
    if not res.get("ok"):
        print("refused:", res.get("error"), file=sys.stderr)
        return 2
    print(res["report"])
    if not a.check:
        print(f"backup: {res['backup']}\nfiles: {res['out_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
