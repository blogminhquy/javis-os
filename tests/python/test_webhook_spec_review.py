"""0.237.0: regression tests for the independent reviews of the spec alignment (M1-M2, M3-M4, M5 and the whole chain).

    python tests/run.py webhook_spec_review

Each check names the finding it pins (R1 = store and rules review, R2 = delivery and security review, R3 = operations,
UI and whole-chain review). The harness is the spec matrix's: the real feature and router, temporary SQLite, fake HTTP,
plugin, tool and model runners, and a model guard.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

import test_webhook_spec_matrix as mx  # noqa: E402  (the harness; its main() runs only as a script)
import webhook_rules as wr  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


def fresh():
    return mx.make(Path(tempfile.mkdtemp(prefix="wh-review-")))


def body(d):
    return json.dumps(d, ensure_ascii=False).encode()


async def rules_and_triage():
    # R1 P1: a lone surrogate must not stop triage of every hook.
    f = fresh()
    h1, t1, _ = f.create("/b1", name="A", target="task", text="x", rules={"mapping": {"id": "id"}, "correlation": "id"})
    h2, t2, _ = f.create("/b1", name="B", target="task", text="x")
    c1, r1 = await f.accept(h1["id"], t1, b'{"id": "\\ud800"}', "application/json", "")
    c2, r2 = await f.accept(h2["id"], t2, b'{"ok": 1}', "application/json", "")
    await f.wait_idle()
    st = f.store()
    e1, e2 = st.get(r1["event_id"]), st.get(r2["event_id"])
    check("R1 P1: a payload with a lone surrogate is quarantined (bad UTF-8) and the next event of another hook runs",
          c1 == 202 and e1["status"] == "invalid" and "utf8" in (e1["error"] or "") and e2["status"] == "done",
          (e1["status"], e1["error"], e2["status"]))
    # A fault inside triage itself is isolated to its row.
    orig = f._triage_one

    async def boom(st_, r):
        if r["hook_id"] == h1["id"]:
            raise RuntimeError("triage fault")
        return await orig(st_, r)
    f._triage_one = boom
    c3, r3 = await f.accept(h1["id"], t1, b'{"id": 1}', "application/json", "")
    c4, r4 = await f.accept(h2["id"], t2, b'{"ok": 2}', "application/json", "")
    await f.wait_idle()
    f._triage_one = orig
    check("R1 P1: an event whose triage raises is quarantined with the fault named; later events still run",
          st.get(r3["event_id"])["status"] == "invalid" and "triage_error" in st.get(r3["event_id"])["error"]
          and st.get(r4["event_id"])["status"] == "done")

    # R1 P2-3: `not` over a missing field or another type is not a match.
    ev = lambda rules, d: wr.evaluate(wr.validate(rules), d.encode(), "application/json")  # noqa: E731
    r = ev({"filter": {"not": {"path": "status", "op": "eq", "value": 4}}}, "{}")
    r2_ = ev({"filter": {"not": {"path": "total", "op": "gt", "value": 100}}}, '{"total": "500"}')
    r3_ = ev({"filter": {"not": {"path": "status", "op": "eq", "value": 4}}}, '{"status": 1}')
    r4_ = ev({"filter": {"not": {"path": "status", "op": "eq", "value": 4}}}, '{"status": 4}')
    check("R1 P2-3: not(eq) on a missing field and not(gt) on text are filtered (missing_field, type_mismatch); "
          "on a real other value it runs; on the value itself it is filtered with a reason",
          r["decision"] == "filtered" and r["reason"] == "missing_field" and r2_["decision"] == "filtered"
          and r2_["reason"] == "type_mismatch" and r3_["decision"] == "run" and r4_["decision"] == "filtered"
          and r4_["reason"], (r["reason"], r2_["reason"], r3_["decision"], r4_["reason"]))
    r = ev({"filter": {"any": [{"path": "a", "op": "eq", "value": 1}, {"path": "b", "op": "eq", "value": 2}]}}, '{"b": 2}')
    check("R1 P2-3: any() still runs when one branch matches and the other field is missing", r["decision"] == "run")
    r = ev({"filter": {"not": {"path": "a", "op": "exists"}}}, "{}")
    check("R1 P2-3: not(exists) on a missing field is a real match (presence is never unknown)", r["decision"] == "run")

    # R1 P2-4: empty / not_empty on a [*] path apply the quantifier.
    all_empty = '{"items": [{"note": ""}, {"note": null}]}'
    one = '{"items": [{"note": ""}, {"note": "gói quà"}]}'
    cond = lambda op, q: {"filter": {"path": "items[*].note", "op": op, "quantifier": q}}  # noqa: E731
    check("R1 P2-4: [*] empty all / any / not_empty any follow the items",
          ev(cond("empty", "all"), all_empty)["decision"] == "run" and ev(cond("empty", "all"), one)["decision"] == "filtered"
          and ev(cond("empty", "any"), one)["decision"] == "run" and ev(cond("not_empty", "any"), one)["decision"] == "run"
          and ev(cond("not_empty", "any"), all_empty)["decision"] == "filtered")
    check("R1 P2-4: not([*] empty all) no longer matches everything",
          ev({"filter": {"not": cond("empty", "all")["filter"]}}, all_empty)["decision"] == "filtered")

    # R1 P3: numbers and Unicode.
    r = ev({"filter": {"path": "a", "op": "eq", "value": "1e999"}}, '{"a": 1e999}')
    check("R1 P3: 1e999 never equals the text \"1e999\" (the payload is quarantined: number_out_of_range)",
          r["decision"] == "invalid" and r["reason"] == "number_out_of_range")
    k = lambda v: ev({"dedup": {"business_paths": ["id"]}}, '{"id": ' + v + "}")["business_key"]["hash"]  # noqa: E731
    check("R1 P3: 1 and 1.0 are one business key (as eq says), \"1\" another", k("1") == k("1.0") != k('"1"'))
    decomposed = '{"items": [{"name": "Gói TRỢ LÝ AI JAVIS"}]}'
    r = ev({"filter": {"path": "items[*].name", "op": "contains", "value": "TRỢ LÝ AI JAVIS", "quantifier": "any"}},
           decomposed)
    check("R1 P3: text in decomposed Unicode (NFD) matches the composed value (NFC compare)", r["decision"] == "run", r)


async def receiving():
    import hashlib
    import hmac
    import httpx
    from fastapi import FastAPI
    f = fresh()
    app = FastAPI()
    app.include_router(f.router)
    cl = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    # R2 P2-5: a provider-checked hook takes a real delivery that carries no Javis token.
    hg, tg, err = f.create("/b1", name="GitHub", target="task", text="x", verify={"provider": "github", "secret": "gh-secret-1"})
    assert hg, err
    raw = b'{"action": "opened"}'
    sig = "sha256=" + hmac.new(b"gh-secret-1", raw, hashlib.sha256).hexdigest()
    ok = await cl.post(f"/hooks/{hg['id']}", content=raw, headers={"X-Hub-Signature-256": sig, "X-GitHub-Delivery": "d-1",
                                                                     "X-GitHub-Event": "pull_request",
                                                                     "Content-Type": "application/json"})
    bad = await cl.post(f"/hooks/{hg['id']}", content=raw, headers={"X-Hub-Signature-256": sig[:-1] + "0",
                                                                      "Content-Type": "application/json"})
    tok_bad_sig = await cl.post(f"/hooks/{hg['id']}", content=raw, headers={"X-Javis-Token": tg,
                                                                              "X-Hub-Signature-256": "sha256=00"})
    plain, tp, _ = f.create("/b1", name="Thường", target="task", text="x")
    no_tok = await cl.post(f"/hooks/{plain['id']}", content=b"{}")
    check("R2 P2-5: a signed GitHub delivery without the Javis token is received (202); a wrong signature is 401 even "
          "with the token; a hook without a provider still needs its token",
          ok.status_code == 202 and bad.status_code == 401 and tok_bad_sig.status_code == 401
          and no_tok.status_code == 401, (ok.status_code, ok.text[:200], bad.status_code, tok_bad_sig.status_code))
    # R3 P2-3: junk from many addresses never locks out a sender with a valid token.
    for i in range(700):
        await cl.post(f"/hooks/{plain['id']}", content=b"{}", headers={"X-Forwarded-For": f"203.0.113.{i % 250}",
                                                                       "X-Javis-Token": "junk"})
    good = await cl.post(f"/hooks/{plain['id']}", content=b"{}", headers={"X-Javis-Token": tp,
                                                                          "X-Forwarded-For": "203.0.113.7"})
    for _ in range(40):
        await cl.post(f"/hooks/{plain['id']}", content=b"{}", headers={"X-Forwarded-For": "198.51.100.9"})
    noisy = await cl.post(f"/hooks/{plain['id']}", content=b"{}", headers={"X-Forwarded-For": "198.51.100.9"})
    other = await cl.post(f"/hooks/{plain['id']}", content=b"{}", headers={"X-Forwarded-For": "198.51.100.10"})
    check("R3 P2-3: after 700 junk requests a valid token still gets 202 (also from an address that failed); an "
          "address past 30 failures a minute gets 429, another address still 401",
          good.status_code == 202 and noisy.status_code == 429 and other.status_code == 401,
          (good.status_code, noisy.status_code, other.status_code))
    f.update(plain["id"], {"enabled": False})
    for _ in range(40):
        await cl.post(f"/hooks/{plain['id']}", content=b"{}", headers={"X-Javis-Token": tp, "X-Forwarded-For": "192.0.2.5"})
    f.update(plain["id"], {"enabled": True})
    after = await cl.post(f"/hooks/{plain['id']}", content=b"{}", headers={"X-Forwarded-For": "192.0.2.5"})
    check("R3 P2-3: 401s from a hook that stopped receiving do not count against the sender", after.status_code == 401,
          after.status_code)

    class Req:
        def __init__(self, host, xff):
            self.client = type("C", (), {"host": host})()
            self.headers = {"x-forwarded-for": xff} if xff else {}
    check("R3 P2-3: the forwarded address is used only behind a local or private proxy",
          f.client_ip(Req("172.18.0.2", "1.2.3.4, 9.9.9.9")) == "9.9.9.9"
          and f.client_ip(Req("8.8.4.4", "1.2.3.4")) == "8.8.4.4" and f.client_ip(Req("127.0.0.1", "")) == "127.0.0.1")
    await f.wait_idle()
    await cl.aclose()


async def store_and_delivery():
    st_codes = mx.HTTP
    # R3 P1-1: a failed event keeps its body through retention; retry sends it, never an empty body.
    f = fresh()
    st = f.store()
    hf, tf, _ = f.create("/b1", name="Lỗi", target="", text="", level="full",
                         actions=[{"id": "crm", "kind": "http", "url": "https://keep.example/in", "body": "raw"}])
    st_codes["by_host"]["keep.example"] = 400
    c, r = await f.accept(hf["id"], tf, b'{"order": 9}', "application/json", "")
    await f.wait_idle()
    old = time.time() - 40 * 86400
    st._db.execute("UPDATE events SET received_at=?, finished_at=?, notified_at=? WHERE id=?", (old, old, old,
                                                                                               r["event_id"]))
    st.prune()
    kept = st.get(r["event_id"], True)
    st_codes["by_host"]["keep.example"] = 200
    mx.HITS.clear()
    ok, why = st.retry(r["event_id"])
    f._kick()
    await f.wait_idle()
    sent = [h for h in mx.HITS if h["host"] == "keep.example"]
    check("R3 P1-1: retention keeps a failed event and its body; the owner's retry sends the same bytes",
          kept is not None and bytes(kept["body"]) == b'{"order": 9}' and ok and sent and sent[0]["body"] == b'{"order": 9}',
          (kept and kept["status"], ok, why, [x["body"] for x in sent]))
    st._db.execute("UPDATE events SET status='failed', body=x'' WHERE id=?", (r["event_id"],))
    ok2, why2 = st.retry(r["event_id"])
    check("R3 P1-1: an event whose body is gone is refused (body_pruned), never sent empty", not ok2 and why2 == "body_pruned")
    okd, _ = st.delete_event(r["event_id"])
    check("the owner can delete a settled event (audited), and its delivery key goes with it",
          okd and st.get(r["event_id"]) is None and any(a["action"] == "delete_event" for a in st.audit_rows(hf["id"])))

    # R2 P2-1 / R3 P2-7: replay runs the CURRENT configuration.
    hr, tr, _ = f.create("/b1", name="Replay", target="", text="", level="full",
                         actions=[{"id": "a", "kind": "http", "url": "https://old.example/in"}])
    c, rr = await f.accept(hr["id"], tr, b"{}", "application/json", "")
    await f.wait_idle()
    f.update(hr["id"], {"actions": [{"id": "a", "kind": "http", "url": "https://new.example/in"},
                                    {"id": "b", "kind": "http", "url": "https://new.example/b"}]})
    mx.HITS.clear()
    code, resp = f.replay_confirm(rr["event_id"])
    f._kick()
    await f.wait_idle()
    ev = st.get(rr["event_id"])
    check("R2 P2-1: replay after changing a URL and adding an action sends both to the NEW targets",
          code == 200 and {b["action_id"]: b["status"] for b in ev["branches"]} == {"a": "completed", "b": "completed"}
          and sorted(h["url"] for h in mx.HITS) == ["https://new.example/b", "https://new.example/in"],
          (code, resp, [(b["action_id"], b["status"], b["detail"]) for b in ev["branches"]]))

    # R2 P2-2: the owner's retry re-runs a dependent cancelled because its dependency failed.
    hd, td, _ = f.create("/b1", name="Chuỗi", target="", text="", level="full",
                         actions=[{"id": "a", "kind": "http", "url": "https://dep.example/a"},
                                  {"id": "b", "kind": "http", "url": "https://dep.example/b", "depends_on": ["a"]}])
    st_codes["by_host"]["dep.example"] = 404
    c, rd = await f.accept(hd["id"], td, b"{}", "application/json", "")
    await f.wait_idle()
    first = {b["action_id"]: b["status"] for b in st.get(rd["event_id"])["branches"]}
    st_codes["by_host"]["dep.example"] = 200
    st.retry(rd["event_id"])
    f._kick()
    await f.wait_idle()
    after = {b["action_id"]: b["status"] for b in st.get(rd["event_id"])["branches"]}
    check("R2 P2-2: after a's failure b is cancelled; the owner's retry runs a, then b", first == {"a": "failed",
          "b": "cancelled"} and after == {"a": "completed", "b": "completed"}, (first, after))

    # R2 P2-3: a dependent of a receiver that only accepted the work is released by Mark done.
    ha, ta, _ = f.create("/b1", name="Nhận", target="", text="", level="full",
                         actions=[{"id": "a", "kind": "http", "url": "https://acc.example/a"},
                                  {"id": "b", "kind": "http", "url": "https://acc.example/b", "depends_on": ["a"]}])
    st_codes["by_host"]["acc.example"] = 202
    c, ra = await f.accept(ha["id"], ta, b"{}", "application/json", "")
    await f.wait_idle()
    waiting = st.get(ra["event_id"])["status"]
    st_codes["by_host"]["acc.example"] = 200
    okr, whyr = st.resolve(ra["event_id"], "done")
    f._kick()
    await f.wait_idle()
    fin = st.get(ra["event_id"])
    check("R2 P2-3: a dependent held by an accepted receiver waits, and Mark done releases it (it runs)",
          waiting == "waiting" and okr and fin["status"] == "done"
          and {b["action_id"]: b["status"] for b in fin["branches"]} == {"a": "completed", "b": "completed"},
          (waiting, okr, whyr, fin["status"], [(b["action_id"], b["status"]) for b in fin["branches"]]))

    # R1 P2-6: disk pressure never drops delivery keys younger than their keep time.
    hk, tk, _ = f.create("/b1", name="Khoá", target="task", text="x")
    c, rk = await f.accept(hk["id"], tk, b"{}", "application/json", "stripe-evt-1")
    await f.wait_idle()
    st._db.execute("UPDATE dedup SET created_at=? WHERE idem_key='h:stripe-evt-1'", (time.time() - 2 * 86400,))
    old_cap = mx.ws.DB_MAX_BYTES
    mx.ws.DB_MAX_BYTES = 1
    try:
        st.make_room(0)
    finally:
        mx.ws.DB_MAX_BYTES = old_cap
    c2, r2 = await f.accept(hk["id"], tk, b"{}", "application/json", "stripe-evt-1")
    check("R1 P2-6: under disk pressure a 2-day-old delivery key survives: the provider's retry is still a duplicate",
          c2 == 200 and r2["event_id"] == rk["event_id"], (c2, r2))


async def rollback_cycle():
    import webhook_rollback as rb
    sd = Path(tempfile.mkdtemp(prefix="wh-rb-"))
    f = mx.make(sd)
    h1, t1, _ = f.create("/b1", name="V2", target="", text="", level="full",
                         actions=[{"id": "crm", "kind": "http", "url": "https://rb.example/in"}])
    h2, t2, _ = f.create("/b1", name="Cũ", target="task", text="x")
    h3, t3, _ = f.create("/b1", name="Tạm dừng", target="task", text="x")
    f.pause(h3["id"], True)
    st = f.store()
    st._db.execute("UPDATE hooks SET enabled=1")
    c, rq = await f.accept(h1["id"], t1, b'{"o": 1}', "application/json", "")
    st._db.execute("UPDATE events SET status='queued', next_at=? WHERE id=?", (time.time() + 3600, rq["event_id"]))
    st.close()
    f._store = None
    res = rb.run(sd)
    leg = json.loads((sd / "webhooks.json").read_text(encoding="utf-8"))
    by = {h["id"]: h for h in leg["hooks"]}
    # The older build deletes h2 meanwhile.
    leg["hooks"] = [h for h in leg["hooks"] if h["id"] != h2["id"]]
    (sd / "webhooks.json").write_text(json.dumps(leg), encoding="utf-8")
    mx.HITS.clear()
    f2 = mx.make(sd)
    st2 = f2.store()
    f2._kick()
    await f2.wait_idle()
    hh1, hh2, hh3 = st2.hook_get(h1["id"]), st2.hook_get(h2["id"]), st2.hook_get(h3["id"])
    ev = st2.get(rq["event_id"])
    check("R1 P2-2 / R3 P1-2: the rollback writes v2 and paused hooks off for the older build, and the upgrade gives "
          "each its own switches back (v2 on, paused still paused)",
          res["ok"] and by[h1["id"]]["enabled"] is False and by[h3["id"]]["enabled"] is False
          and hh1["enabled"] and hh3["enabled"] and hh3["paused"], (by[h1["id"]]["enabled"], hh1["enabled"], hh3))
    check("R1 P2-2: a hook the older build deleted stops receiving after the upgrade (kept, audited)",
          not hh2["enabled"] and any(a["action"].startswith("rollback:deleted") for a in st2.audit_rows(h2["id"])))
    check("R3 P1-2: an event exported at rollback is held unknown and does not run after the upgrade",
          ev["status"] == "unknown" and "rollback" in ev["error"] and not [x for x in mx.HITS if x["host"] == "rb.example"],
          (ev["status"], ev["error"]))


async def privacy_and_ops():
    import httpx
    from fastapi import FastAPI
    f = fresh()
    st = f.store()
    app = FastAPI()
    app.include_router(f.router)
    cl = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    # R1 P2-5: Systeme.io contact details never reach the stored trace; rules still read them.
    fx = next(x for x in json.loads((ROOT / "tests/fixtures/webhooks/signatures.json").read_text(encoding="utf-8"))
              ["fixtures"] if x["name"] == "systeme_io_synthetic_php_default")
    hs, ts, err = f.create("/b1", name="Systeme", target="task", text="x",
                           verify={"provider": "systeme_io", "secret": fx["secret"]},
                           rules={"filter": {"path": "_event.contact.email", "op": "contains", "value": "@"}})
    assert hs, err
    rs = await cl.post(f"/hooks/{hs['id']}", content=fx["body"].encode(), headers=dict(fx["headers"],
                                                                                         **{"Content-Type": "application/json"}))
    await f.wait_idle()
    row = st._db.execute("SELECT trace, status FROM events WHERE id=?", (rs.json()["event_id"],)).fetchone()
    check("R1 P2-5: the stored trace holds the Systeme.io ids and type, never the contact's email or name; the rule on "
          "_event.contact still matched", rs.status_code == 202 and "lan@example.com" not in row[0]
          and "Trợ lý" not in row[0] and '"contact"' not in row[0] and row[1] == "done", (rs.status_code, row))

    # R3 P2-5 / P2-6: masked by default everywhere; raw only on request, audited.
    hm, tm, _ = f.create("/b1", name="Khách", target="task", text="x", rules={"mapping": {"phone": "phone"}})
    mx.MODEL["answer"] = ("Đã gọi chị Lan số 0912345678, email lan@example.com", "")
    c, rm = await f.accept(hm["id"], tm, body({"phone": "0912345678", "email": "lan@example.com"}), "application/json", "")
    await f.wait_idle()
    mx.MODEL["answer"] = ("Đã xử lý.", "")
    eid = rm["event_id"]
    view = (await cl.get(f"/webhooks/events/{eid}")).text
    page = (await cl.get(f"/webhooks/events?hook={hm['id']}")).text
    exp = (await cl.get(f"/webhooks/events/export?hook={hm['id']}&body=1")).text
    lst = (await cl.get("/webhooks")).text
    leaks = {n: ("0912345678" in t or "lan@example.com" in t) for n, t in (("view", view), ("page", page), ("export", exp),
                                                                           ("list", lst))}
    check("R3 P2-5: the phone and email (in the AI result, the fields, the payload) are masked in the event view, the "
          "log page, the masked export and the hook list", not any(leaks.values()), leaks)
    n0 = len(st.audit_rows(hm["id"]))
    rawx = (await cl.get(f"/webhooks/events/export?hook={hm['id']}&raw=1")).text
    sim = (await cl.post("/webhooks/simulate", json={"id": hm["id"], "event": eid})).json()
    n1 = len(st.audit_rows(hm["id"]))
    simr = (await cl.post("/webhooks/simulate", json={"id": hm["id"], "event": eid, "raw": True})).json()
    n2 = len(st.audit_rows(hm["id"]))
    check("R3 P2-6: a raw export without bodies is audited; simulating a logged event is masked, and its raw form is "
          "audited", "0912345678" in rawx and n1 == n0 + 1 and "0912345678" not in json.dumps(sim, ensure_ascii=False)
          and "0912345678" in json.dumps(simr, ensure_ascii=False) and n2 == n1 + 1, (n0, n1, n2))

    # R3 P2-4: errors_only groups blocked and unknown into one incident.
    mx.SENT.clear()
    hb, tb, _ = f.create("/b1", name="Chặn", target="", text="", level="suggest", notify="errors_only",
                         actions=[{"id": "crm", "kind": "http", "url": "https://blk.example/in"}])
    for i in range(5):
        await f.accept(hb["id"], tb, body({"i": i}), "application/json", "")
    await f.wait_idle()
    told = [m for m in mx.SENT if "Chặn" in m["text"]]
    states = [st.get(r["id"])["status"] for r in st.page(hook_id=hb["id"])["items"]]
    check("R3 P2-4: five blocked events in errors_only give one notice, not five", states.count("blocked") == 5
          and len(told) == 1, (states, len(told)))

    # R2 P3 / R1 P3: a retry-safe delivery found running after crashes is not resent past its attempts.
    hr, tr, _ = f.create("/b1", name="An toàn", target="", text="", level="full",
                         actions=[{"id": "crm", "kind": "http", "url": "https://safe.example/in",
                                   "retry_safety": "idempotent"}])
    c, rr = await f.accept(hr["id"], tr, b"{}", "application/json", "")
    await f.wait_idle()
    now = time.time()
    st._db.execute("UPDATE events SET status='running', lease_until=?, dispatched_at=?, finished_at=0 WHERE id=?",
                   (now - 1, now - 5, rr["event_id"]))
    st._db.execute("UPDATE deliveries SET status='running', tries=4 WHERE event_id=?", (rr["event_id"],))
    st.recover(now)
    check("R2 P3: a retry-safe delivery that already used its 4 attempts is unknown after a crash, not resent",
          st.get(rr["event_id"])["branches"][0]["status"] == "unknown")

    # R3 P3: Stop receiving works even when the hook's workflow is gone.
    hw, tw_, _ = f.create("/b1", name="WF", target="workflow", workflow="wf")
    f.deps.workflow_exists = lambda b, s_: False
    h_off, err_off, code_off = f.update(hw["id"], {"enabled": False})
    f.deps.workflow_exists = lambda b, s_: True
    check("R3 P3: Stop receiving is saved even when the workflow no longer exists", code_off == 200
          and not h_off["enabled"], (code_off, err_off))
    # R1 P3: a hook switched off between the token check and the commit stores nothing.
    hx, tx, _ = f.create("/b1", name="Tắt giữa chừng", target="task", text="x")
    st.hook_set(hx["id"], enabled=0)
    code_x, resp_x = await f.accept_body(dict(hx, enabled=True), b"{}", "application/json", "")
    check("R1 P3: a hook switched off after the token check stores nothing (401)", code_x == 401
          and not st.page(hook_id=hx["id"])["items"], (code_x, resp_x))
    # R2 P3: the token header cannot be one Javis stores with the event.
    _, _, err_h = f.create("/b1", name="Hdr", target="task", text="x", token_header="X-Request-Id")
    check("R2 P3: a token header named like a stored header (X-Request-Id) is refused", "store" in (err_h or ""), err_h)
    await cl.aclose()


async def plugin_fairness():
    import threading
    f = fresh()
    st = f.store()
    stop = threading.Event()
    calls = {"fast": 0}

    def slow(env, ctx):
        stop.wait(20)
        return {"status": "completed"}

    def fast(env, ctx):
        calls["fast"] += 1
        return {"status": "completed"}
    old_ph = f.deps.plugin_handler

    def ph(brain, slug, name):
        h = {"slow": slow, "fast": fast}.get(slug)
        return {"handler": h, "ctx": None, "min_mode": "readonly", "schema": None, "ai": False, "idempotent": True} if h else None
    f.deps.plugin_handler = ph
    old_t = mx.wa.PLUGIN_TIMEOUT_S
    mx.wa.PLUGIN_TIMEOUT_S = 0.3
    try:
        hooks = []
        for i in range(4):
            h, t, _ = f.create("/b1", name=f"slow{i}", target="", text="", level="full",
                               actions=[{"id": "p", "kind": "plugin", "plugin": "slow", "handler": "h"}])
            hooks.append((h, t))
        for h, t in hooks:
            await f.accept(h["id"], t, b"{}", "application/json", "")
        await f.wait_idle()
        hf, tf, _ = f.create("/b1", name="fast", target="", text="", level="full",
                             actions=[{"id": "p", "kind": "plugin", "plugin": "fast", "handler": "h"}])
        c, r = await f.accept(hf["id"], tf, b"{}", "application/json", "")
        await f.wait_idle()
        b = st.get(r["event_id"])["branches"][0]
        check("R2 P2-4: four hung calls of one plugin do not stop another plugin: it runs at once, first attempt",
              calls["fast"] == 1 and b["status"] == "completed" and int(b["tries"]) == 1, (calls, b["status"], b["tries"]))
    finally:
        stop.set()
        mx.wa.PLUGIN_TIMEOUT_S = old_t
        f.deps.plugin_handler = old_ph
        await asyncio.sleep(0.3)


async def second_round():
    """Findings of the review of the fixes (R4)."""
    import threading
    import httpx
    from fastapi import FastAPI
    f = fresh()
    st = f.store()
    # R4 P2-1: a plugin whose calls hang does not hold its other deliveries past their deadline.
    stop = threading.Event()

    def slow(env, ctx):
        stop.wait(20)
        return {"status": "completed"}
    f.deps.plugin_handler = lambda b, slug, n: {"handler": slow, "ctx": None, "min_mode": "readonly", "schema": None,
                                                "ai": False, "idempotent": True} if slug == "hang" else None
    old_t = mx.wa.PLUGIN_TIMEOUT_S
    mx.wa.PLUGIN_TIMEOUT_S = 0.2
    try:
        hs = [f.create("/b1", name=f"hang{i}", target="", text="", level="full",
                       actions=[{"id": "p", "kind": "plugin", "plugin": "hang", "handler": "h"}])[:2] for i in range(3)]
        evs = []
        for h, t in hs:
            evs.append((await f.accept(h["id"], t, b"{}", "application/json", ""))[1]["event_id"])
        await f.wait_idle()
        late = evs[2]
        st._db.execute("UPDATE deliveries SET deadline=?, next_at=0 WHERE event_id=?", (time.time() - 1, late))
        st._db.execute("UPDATE events SET next_at=0 WHERE id=?", (late,))
        f._kick()
        await f.wait_idle()
        b = st.get(late)["branches"][0]
        check("R4 P2-1: a delivery that waited for a hung plugin past its deadline fails (never sent) instead of "
              "waiting forever", b["status"] == "failed" and "deadline" in b["detail"] and int(b["tries"] or 0) == 0,
              (b["status"], b["detail"], b["tries"]))
    finally:
        stop.set()
        mx.wa.PLUGIN_TIMEOUT_S = old_t
        await asyncio.sleep(0.3)
    # R4 P2-2: failed events can be settled one by one or all at once, so kept bodies never wedge the quota.
    f2 = fresh()
    st2 = f2.store()
    hq, tq, _ = f2.create("/b1", name="Đầy", target="", text="", level="full", limits={"backlog_mb": 1, "body_kb": 512},
                          actions=[{"id": "crm", "kind": "http", "url": "https://wedge.example/in", "body": "raw"}])
    mx.HTTP["by_host"]["wedge.example"] = 400
    big = b'{"pad": "' + b"x" * 400000 + b'"}'
    codes = [(await f2.accept(hq["id"], tq, big, "application/json", ""))[0] for _ in range(2)]
    await f2.wait_idle()
    refused, _ = await f2.accept(hq["id"], tq, big, "application/json", "")
    ids = [r["id"] for r in st2.page(hook_id=hq["id"])["items"]]
    ok1, _ = st2.resolve(ids[0], "done", "fixed by hand")
    n = st2.close_failed(hq["id"])
    mx.HTTP["by_host"]["wedge.example"] = 200
    again, _ = await f2.accept(hq["id"], tq, big, "application/json", "")
    check("R4 P2-2: kept failed bodies fill the byte quota (429), Close settles one, Close all the rest, and the hook "
          "receives again", codes[:2] == [202, 202] and refused == 429 and ok1 and n >= 1 and again == 202
          and st2.get(ids[0])["status"] == "done", (codes, refused, ok1, n, again))
    okd, whyd = st2.delete_event(ids[0])
    check("R4 P3: a done event cannot be deleted by hand (its delivery key must stay)", not okd and whyd == "not_deletable")
    # R4 P2-3: simulating a logged event reveals no value unless raw.
    app = FastAPI()
    app.include_router(f2.router)
    cl = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    hn, tn, _ = f2.create("/b1", name="Tên", target="task", text="x",
                          rules={"filter": {"path": "customer.full", "op": "exists"}, "correlation": "email"})
    c, rn = await f2.accept(hn["id"], tn, body({"customer": {"full": "Nguyễn Văn Bình"}, "email": "binh@example.com"}),
                            "application/json", "")
    await f2.wait_idle()
    sim = json.dumps((await cl.post("/webhooks/simulate", json={"id": hn["id"], "event": rn["event_id"]})).json(),
                     ensure_ascii=False)
    check("R4 P2-3: simulating a logged event shows no customer value in the trace nor the correlation",
          "Nguyễn Văn Bình" not in sim and "binh@example.com" not in sim, sim[:300])
    view = (await cl.get(f"/webhooks/events/{rn['event_id']}")).text
    check("R4 P2-3: the masked event view hides every text under a customer block (customer.full)",
          "Nguyễn Văn Bình" not in view and "Bình" not in view, view[:300])
    # R4 P3: the retry window does not widen with each retry.
    ev = st2.get(ids[1]) if st2.get(ids[1]) else None
    hw, tw_, _ = f2.create("/b1", name="Cửa sổ", target="", text="", level="full",
                           actions=[{"id": "crm", "kind": "http", "url": "https://win.example/in"}])
    mx.HTTP["by_host"]["win.example"] = 400
    c, rw = await f2.accept(hw["id"], tw_, b"{}", "application/json", "")
    await f2.wait_idle()
    wins = []
    for _ in range(3):
        st2.retry(rw["event_id"])
        f2._kick()
        await f2.wait_idle()
        d = st2._db.execute("SELECT deadline FROM deliveries WHERE event_id=?", (rw["event_id"],)).fetchone()[0]
        wins.append(round((d - time.time()) / 3600))
    check("R4 P3: each owner retry gets the same 24 h window, never a wider one", wins == [24, 24, 24], wins)
    # R4 P3: the Stop receiving shortcut parses text like the normal path.
    hb, tb, _ = f2.create("/b1", name="Công tắc", target="task", text="x")
    h_s, _, _ = f2.update(hb["id"], {"enabled": "false"})
    check("R4 P3: {\"enabled\": \"false\"} switches receiving OFF", not h_s["enabled"])
    # R5 (review of the route change): no 500 on an infinite number; a text/plain body is not read.
    codes = [(await cl.get(u)).status_code for u in ("/webhooks/events?limit=inf", "/webhooks/audit?limit=1e400",
                                                     "/webhooks/events/export?raw=inf")]
    rp = await cl.post("/webhooks/delete", content=json.dumps({"id": hb["id"]}), headers={"content-type": "text/plain"})
    check("R5 P3: limit=inf or 1e400 falls back to the default (200), never a 500", codes == [200, 200, 200], codes)
    check("R5 P3: a text/plain POST (sent cross-origin without a preflight) is not read: the hook is not deleted",
          rp.json().get("ok") is False and f2._find_hook(hb["id"]) is not None, rp.text)
    await cl.aclose()
    del ev


async def whole_chain():
    """Findings of the whole-chain review (R6)."""
    import httpx
    from fastapi import FastAPI
    import webhook_worker as ww
    f = fresh()
    st = f.store()
    app = FastAPI()
    app.include_router(f.router)
    cl = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    # R6 P2-1: an edit refused for a stale revision never replaces the live keys.
    hk, tk, _ = f.create("/b1", name="Khoá", target="", text="", level="full",
                         actions=[{"id": "crm", "kind": "http", "url": "https://keys.example/in",
                                   "headers": {"X-Key": "old"}}])
    name = f"{hk['id']}/a/crm/X-Key"
    act = lambda v: [{"id": "crm", "kind": "http", "url": "https://keys.example/in", "headers": {"X-Key": v}}]
    h2, e2, c2 = f.update(hk["id"], {"actions": act("new"), "revision": 1})
    h3, e3, c3 = f.update(hk["id"], {"actions": act("stale"), "revision": 1})
    check("R6 P2-1: a save from a stale tab is refused (409) and the live key stays the one saved last",
          c2 == 200 and c3 == 409 and f.vault.get(name) == "new", (c2, e2, c3, e3))
    # R6 P2-3: a plugin's AI grant must hold when the event arrived AND now.
    seen = []

    def ai_handler(env, ctx):
        seen.append(env["delivery_id"])
        return {"status": "completed"}
    old_ph = f.deps.plugin_handler
    f.deps.plugin_handler = lambda b, slug, n: {"handler": ai_handler, "ctx": None, "min_mode": "readonly",
                                                "schema": None, "ai": True, "idempotent": True} \
        if slug == "ai-plug" else old_ph(b, slug, n)
    pa = lambda allow: [{"id": "p", "kind": "plugin", "plugin": "ai-plug", "handler": "h", "allow_ai": allow}]
    ha, ta, _ = f.create("/b1", name="AI plugin", target="", text="", level="full", actions=pa(True))
    st.hook_set(ha["id"], paused=1)
    c, ra = await f.accept(ha["id"], ta, b"{}", "application/json", "")
    _, ea, ca = f.update(ha["id"], {"actions": pa(False)})
    st.hook_set(ha["id"], paused=0)
    f._kick()
    await f.wait_idle()
    ba = st.get(ra["event_id"])["branches"][0]
    check("R6 P2-3: the AI grant revoked after the event arrived blocks the plugin call (never runs on the old grant)",
          ca == 200 and ba["status"] == "blocked" and not seen, (ca, ea, ba["status"], ba["detail"], seen))
    # R6 P2-4: a block fixed outside the hook (plugin installed again) runs again from one button, audited.
    ready = {"on": False}
    f.deps.plugin_handler = lambda b, slug, n: ({"handler": lambda e, c: {"status": "completed"}, "ctx": None,
                                                 "min_mode": "readonly", "schema": None, "ai": False,
                                                 "idempotent": True} if ready["on"] else None) \
        if slug == "later-plug" else old_ph(b, slug, n)
    hb, tb, _ = f.create("/b1", name="Plugin tắt", target="", text="", level="full",
                         actions=[{"id": "p", "kind": "plugin", "plugin": "later-plug", "handler": "h"}])
    c, rb = await f.accept(hb["id"], tb, b"{}", "application/json", "")
    await f.wait_idle()
    before = st.get(rb["event_id"])["status"]
    ready["on"] = True
    rr = (await cl.post("/webhooks/events/retry_blocked", json={"hook": hb["id"]})).json()
    await f.wait_idle()
    after = st.get(rb["event_id"])
    audit = [a for a in st._db.execute("SELECT action FROM audit WHERE hook_id=?", (hb["id"],)).fetchall()]
    check("R6 P2-4: Retry all blocked re-runs a delivery blocked by a missing plugin once it is back (audited)",
          before == "blocked" and rr.get("queued") == 1 and after["status"] == "done"
          and ("retry_blocked",) in [tuple(a) for a in audit], (before, rr, after["status"], audit))
    nf = (await cl.post("/webhooks/events/retry_blocked", json={"hook": "wh_nope"})).status_code
    check("R6 P2-4: Retry all blocked on an unknown hook is 404", nf == 404)
    f.deps.plugin_handler = old_ph
    # R6 P2-5: the correlation value is masked in the list and the detail view.
    hc, tc, _ = f.create("/b1", name="Tương quan", target="task", text="x", rules={"correlation": "email"})
    c, rc = await f.accept(hc["id"], tc, body({"email": "lan@example.com"}), "application/json", "")
    await f.wait_idle()
    lst = (await cl.get(f"/webhooks/events?hook={hc['id']}")).text
    one = (await cl.get(f"/webhooks/events/{rc['event_id']}")).text
    check("R6 P2-5: the correlation (an e-mail here) is masked in the event list and the detail view",
          "lan@example.com" not in lst and "lan@example.com" not in one, (lst[:200], one[:200]))
    # R6 P2-6: a replay preview counts an unknown delivery as one that may act again; the confirm checks the revision.
    mx.HTTP["by_host"]["amb6.example"] = 504
    hr, tr, _ = f.create("/b1", name="Phát lại", target="", text="", level="full",
                         actions=[{"id": "crm", "kind": "http", "url": "https://amb6.example/in"}])
    c, rr6 = await f.accept(hr["id"], tr, b"{}", "application/json", "")
    await mx.drain(f)
    b6 = st.get(rr6["event_id"])["branches"][0]
    c6, prev = f.replay_preview(rr6["event_id"])
    f.update(hr["id"], {"name": "Phát lại 2"})
    cc, conf = f.replay_confirm(rr6["event_id"], prev.get("revision"))
    check("R6 P2-6: an unknown delivery is listed in may_repeat (it may have acted and would act again)",
          b6["status"] == "unknown" and c6 == 200 and prev["may_repeat"] == ["crm"], (b6["status"], prev))
    check("R6 P2-6: confirming a preview after the hook changed is refused (409: preview again)", cc == 409, (cc, conf))
    mx.HTTP["by_host"]["amb6.example"] = 200
    # R6 P2-7: a test event says so to the receiver in a header (a raw body cannot carry `_javis.test`).
    ht, tt, _ = f.create("/b1", name="Thử", target="", text="", level="full",
                         actions=[{"id": "crm", "kind": "http", "url": "https://test6.example/in", "body": "raw"}])
    mx.HITS.clear()
    code, resp = await f.test_send({"id": ht["id"], "payload": {"x": 1}, "confirm": True})
    await f.wait_idle()
    hits = [x for x in mx.HITS if x["host"] == "test6.example"]
    check("R6 P2-7: a test send reaches the receiver with X-Javis-Test: 1", code == 200 and hits
          and hits[0]["headers"].get("x-javis-test") == "1", (code, resp, hits[:1]))
    c, rl = await f.accept(ht["id"], tt, b'{"x": 2}', "application/json", "")
    await f.wait_idle()
    hits = [x for x in mx.HITS if x["host"] == "test6.example"]
    check("R6 P2-7: a real event carries no test header", len(hits) == 2 and "x-javis-test" not in hits[1]["headers"])
    # R6 P2-8: deleting a hook closes its events waiting for the owner; an ingest racing the delete stores nothing.
    hd, td, _ = f.create("/b1", name="Xoá", target="", text="", level="full",
                         actions=[{"id": "crm", "kind": "http", "url": "https://amb6.example/in"}])
    mx.HTTP["by_host"]["amb6.example"] = 504
    c, rd = await f.accept(hd["id"], td, b"{}", "application/json", "")
    await mx.drain(f)
    mx.HTTP["by_host"]["amb6.example"] = 200
    waiting = st.get(rd["event_id"])["status"]
    gone_hook = dict(st.hook_get(hd["id"]))
    f.delete(hd["id"])
    closed = st.get(rd["event_id"])["status"]
    n0 = st._db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    ci, ri = st.ingest(gone_hook, b"{}", "application/json")
    n1 = st._db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    check("R6 P2-8: a deleted hook's unknown event is closed (cancelled), not left waiting where no view shows it",
          waiting == "unknown" and closed == "cancelled", (waiting, closed))
    check("R6 P2-8: an ingest for a hook deleted after its token check stores nothing (401)",
          ci == 401 and n1 == n0, (ci, ri, n0, n1))
    # R6 P2-9: a fault in Javis while one delivery runs leaves it unknown; the others finish.
    hg, tg, _ = f.create("/b1", name="Lỗi trong", target="", text="", level="full",
                         actions=[{"id": "a", "kind": "http", "url": "https://boom.example/in"},
                                  {"id": "b", "kind": "http", "url": "https://fine.example/in"}])
    real = ww.webhook_actions.run_http

    async def boom(action, ctx, transport=None, resolve=None):
        if "boom.example" in action["url"]:
            raise RuntimeError("bug")
        return await real(action, ctx, transport, resolve)
    ww.webhook_actions.run_http = boom
    try:
        c, rg = await f.accept(hg["id"], tg, b"{}", "application/json", "")
        await f.wait_idle()
    finally:
        ww.webhook_actions.run_http = real
    bs = {b["action_id"]: b["status"] for b in st.get(rg["event_id"])["branches"]}
    check("R6 P2-9: a crash inside one delivery marks it unknown (it may have acted); the other completes",
          bs == {"a": "unknown", "b": "completed"}, bs)
    # R6 P2-10: AI hooks never take the last worker slot: a code-only hook runs while they are all busy.
    gate = asyncio.Event()

    async def slow_task(brain, text, level):
        await gate.wait()
        return "xong", ""
    old_rt = f.deps.run_task
    f.deps.run_task = slow_task
    ais = [f.create("/b1", name=f"AI {i}", target="task", text="x")[:2] for i in range(ww.WORKER_MAX)]
    hq, tq, _ = f.create("/b1", name="Mã", target="", text="", level="full",
                         actions=[{"id": "crm", "kind": "http", "url": "https://code6.example/in"}])
    try:
        for h, t in ais:
            await f.accept(h["id"], t, b"{}", "application/json", "")
        await asyncio.sleep(0.5)
        c, rq = await f.accept(hq["id"], tq, b"{}", "application/json", "")
        done_q = ""
        for _ in range(100):
            done_q = st.get(rq["event_id"])["status"]
            if done_q == "done":
                break
            await asyncio.sleep(0.02)
        running = st._db.execute("SELECT COUNT(*) FROM events WHERE status='running'").fetchone()[0]
        check("R6 P2-10: with every AI hook waiting on the model, a code-only hook still runs at once "
              f"(AI events running: {running} of {ww.WORKER_MAX} slots)",
              done_q == "done" and running == ww.WORKER_MAX - 1, (done_q, running))
    finally:
        gate.set()
        await f.wait_idle()
        f.deps.run_task = old_rt
    # §4 proof the README cites: busy timeout finite, the WAL counted against the cap, folded back before refusing.
    import webhook_store as wst
    fw = fresh()
    sw = fw.store()
    hw6, tw6, _ = fw.create("/b1", name="WAL", target="task", text="x")
    sw._db.execute("PRAGMA wal_autocheckpoint=0")
    for i in range(30):
        await fw.accept(hw6["id"], tw6, body({"i": i, "pad": "y" * 20000}), "application/json", f"w{i}")
    await fw.wait_idle()
    busy = sw._db.execute("PRAGMA busy_timeout").fetchone()[0]
    wal_before, used = sw.wal_bytes(), sw.used_bytes()
    counted = wal_before > 0 and used == sw.size_bytes() + wal_before
    old_cap = wst.DB_MAX_BYTES
    wst.DB_MAX_BYTES = sw.size_bytes() + wal_before // 2       # over the cap only because of the WAL
    try:
        full_before = sw.space_state()["level"] == "full"
        sw.make_room()
        wal_after = sw.wal_bytes()
        full_after = sw.space_state()["level"] == "full"
    finally:
        wst.DB_MAX_BYTES = old_cap
    check("§4: busy timeout is finite (5 s), the WAL counts against the cap, and room-making folds it back first",
          busy == 5000 and counted and full_before and wal_after < wal_before and not full_after,
          (busy, wal_before, used, full_before, wal_after, full_after))
    await cl.aclose()


async def fix_review():
    """Findings of the review of the R6 fixes (R7)."""
    import threading
    import httpx
    from fastapi import FastAPI
    import webhook_actions as wa
    import webhook_store as wst
    import webhook_worker as ww
    f = fresh()
    st = f.store()
    app = FastAPI()
    app.include_router(f.router)
    cl = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    act = lambda v: [{"id": "crm", "kind": "http", "url": "https://keys7.example/in", "headers": {"X-Key": v}}]
    # R7 P2-1: two saves of one hook at once: the one that loses never leaves its key (nor the old one) in the vault.
    hk, tk, _ = f.create("/b1", name="Hai tab", target="", text="", level="full", actions=act("old"))
    name = f"{hk['id']}/a/crm/X-Key"
    real_seal = f._seal

    def slow_seal(hook):
        r = real_seal(hook)
        # A seals first and commits last: B, arriving while A has sealed but not committed, would commit first.
        seals.append(1)
        time.sleep(0.6 if len(seals) == 1 else 0.1)
        return r
    f._seal = slow_seal
    seals = []
    res = {}
    ta = threading.Thread(target=lambda: res.__setitem__("a", f.update(hk["id"], {"actions": act("A"), "revision": 1})))
    tb = threading.Thread(target=lambda: res.__setitem__("b", f.update(hk["id"], {"actions": act("B"), "revision": 1})))
    ta.start()
    time.sleep(0.05)
    tb.start()
    ta.join()
    tb.join()
    f._seal = real_seal
    codes = sorted(r[2] for r in res.values())
    winner = "A" if res["a"][2] == 200 else "B"
    check("R7 P2-1: two saves at once: one wins (200), one is refused (409), and the vault holds the winner's key",
          codes == [200, 409] and f.vault.get(name) == winner and int(st.hook_get(hk["id"])["revision"]) == 2,
          (codes, f.vault.get(name), winner))
    # R7 P2-1: a conflict found at commit (another process) or a failed commit puts the keys back.
    real_upd = st.hook_update

    def conflict(*a, **k):
        raise wst.Conflict(9)
    st.hook_update = conflict
    _, _, c409 = f.update(hk["id"], {"actions": act("C"), "revision": 2})
    st.hook_update = real_upd
    check("R7 P2-1: a conflict at commit restores the key that was live before the save", c409 == 409
          and f.vault.get(name) == winner, (c409, f.vault.get(name)))
    real_put = f.vault.put
    calls = {"n": 0}

    def put_then_fail(n, v):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return real_put(n, v)
    f.vault.put = put_then_fail
    two = lambda a, b: [{"id": "crm", "kind": "http", "url": "https://keys7.example/in", "headers": {"X-Key": a, "X-Two": b}}]
    _, err, c400 = f.update(hk["id"], {"actions": two("D", "E")})
    f.vault.put = real_put
    check("R7 P3: a seal that fails half way (disk error) puts back the key it already replaced", c400 == 400
          and f.vault.get(name) == winner and not f.vault.has(f"{hk['id']}/a/crm/X-Two"), (c400, err, f.vault.get(name)))
    # R7 P2-2: deleting the ONLY hook still refuses an ingest that raced the delete.
    f2 = fresh()
    s2 = f2.store()
    ho, to, _ = f2.create("/b1", name="Duy nhất", target="task", text="x")
    gone = dict(s2.hook_get(ho["id"]))
    f2.delete(ho["id"])
    ci, _ = s2.ingest(gone, b"{}", "application/json")
    check("R7 P2-2: an ingest racing the delete of the last hook stores nothing (401)", ci == 401
          and s2._db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0, ci)
    # R7 P2-3: an event queued when its hook is deleted is cancelled and retention removes it with its data.
    hq, tq, _ = f2.create("/b1", name="Đang chờ", target="task", text="x")
    s2.hook_set(hq["id"], paused=1)
    c, rq = await f2.accept(hq["id"], tq, body({"email": "chi.lan@example.com"}), "application/json", "")
    f2.delete(hq["id"])
    stq = s2.get(rq["event_id"])["status"]
    s2.prune(time.time() + (wst.KEEP_DAYS + 2) * 86400)
    left = s2._db.execute("SELECT COUNT(*) FROM events WHERE id=?", (rq["event_id"],)).fetchone()[0]
    check("R7 P2-3: a queued event of a deleted hook is cancelled, and retention removes it (no customer data kept "
          "forever)", stq == "cancelled" and left == 0, (stq, left))
    # R7 P2-4: a fault in Javis BEFORE the send is retried (nothing went out), not left as "may have acted".
    hp, tp, _ = f.create("/b1", name="Lỗi trước", target="", text="", level="full",
                         actions=[{"id": "crm", "kind": "http", "url": "https://pre7.example/in"}])
    real_b = st.breaker_open_until
    hit = {"n": 0}

    def locked_once(*a, **k):
        hit["n"] += 1
        if hit["n"] == 1:
            raise RuntimeError("database is locked")
        return real_b(*a, **k)
    st.breaker_open_until = locked_once
    mx.HITS.clear()
    c, rp = await f.accept(hp["id"], tp, b"{}", "application/json", "")
    await f.wait_idle()
    first = st.get(rp["event_id"])["branches"][0]
    sent_first = len([x for x in mx.HITS if x["host"] == "pre7.example"])
    await mx.drain(f)
    st.breaker_open_until = real_b
    after = st.get(rp["event_id"])["branches"][0]
    check("R7 P2-4: an internal fault before the send leaves the delivery waiting to retry (nothing was sent), then "
          "it runs", first["status"] == "retry" and sent_first == 0 and after["status"] == "completed",
          (first["status"], first["detail"], sent_first, after["status"]))
    # R7 P3: the replay confirm must carry the previewed revision; a bad value is a 400, not a 500.
    c, rr = await f.accept(hp["id"], tp, b"{}", "application/json", "")
    await f.wait_idle()
    r1 = await cl.post("/webhooks/events/replay", json={"id": rr["event_id"], "confirm": True})
    r2 = await cl.post("/webhooks/events/replay", json={"id": rr["event_id"], "confirm": True, "revision": "abc"})
    check("R7 P3: a replay confirm without the previewed revision, or with a bad one, is refused (400)",
          r1.status_code == 400 and r2.status_code == 400, (r1.status_code, r1.text, r2.status_code, r2.text))
    # R7 P3: a correlation on a name field is masked like that field.
    hn, tn, _ = f.create("/b1", name="Tên", target="task", text="x", rules={"correlation": "customer.name"})
    c, rn = await f.accept(hn["id"], tn, body({"customer": {"name": "Trần Thị Mai"}}), "application/json", "")
    await f.wait_idle()
    lst = (await cl.get(f"/webhooks/events?hook={hn['id']}")).text
    one = (await cl.get(f"/webhooks/events/{rn['event_id']}")).text
    exp = (await cl.get(f"/webhooks/events/export?hook={hn['id']}")).text
    check("R7 P3: a correlation on customer.name is masked in the list, the detail and the export",
          all("Trần Thị Mai" not in t and "Mai" not in t for t in (lst, one, exp)), (lst[:200], exp[:200]))
    # R7 P3: an Apps Script test event says so in the query even when the delivery id rides in a header.
    ctx = {"delivery_id": "dlv_1", "event_id": "ev_1", "source": "test"}
    u = wa.target_url({"kind": "apps_script", "url": "https://script.google.com/macros/s/X/exec"}, ctx)
    u2 = wa.target_url({"kind": "apps_script", "url": "https://script.google.com/macros/s/X/exec"}, dict(ctx, source="http"))
    check("R7 P3: an Apps Script test event carries javis_test=1 without delivery_ref query; a real one does not",
          u.endswith("?javis_test=1") and "javis_test" not in u2, (u, u2))
    # R7 P3: plugins allowed to use AI count among the AI hooks (they may run long).
    old_ph = f.deps.plugin_handler
    f.deps.plugin_handler = lambda b, slug, n: {"handler": lambda e, c: {"status": "completed"}, "ctx": None,
                                                "min_mode": "readonly", "schema": None, "ai": True,
                                                "idempotent": True} if slug == "ai7" else old_ph(b, slug, n)
    ha, ta_, _ = f.create("/b1", name="AI plugin 7", target="", text="", level="full",
                          actions=[{"id": "p", "kind": "plugin", "plugin": "ai7", "handler": "h", "allow_ai": True}])
    check("R7 P3: a hook whose plugin may use AI is held to the AI share of the worker slots",
          ha["id"] in f._ai_hook_ids() and hp["id"] not in f._ai_hook_ids())
    f.deps.plugin_handler = old_ph
    await cl.aclose()


async def chain_review_two():
    """Findings of the second whole-chain review at ac47dac1 (R8: M1-M3 and M4-M5)."""
    import httpx
    from fastapi import FastAPI
    import webhook_rollback as wrb
    import webhook_store as wst
    import webhook_triggers as wt
    f = fresh()
    st = f.store()
    app = FastAPI()
    app.include_router(f.router)
    cl = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    # R8 P1 (M1-M3): a dependent behind a delivery that retries later does not spin the event.
    mx.HTTP["by_host"]["slow8.example"] = 503
    hd, td, _ = f.create("/b1", name="Chuỗi", target="", text="", level="full", actions=[
        {"id": "a", "kind": "http", "url": "https://slow8.example/in", "retry_safety": "idempotent"},
        {"id": "b", "kind": "http", "url": "https://after8.example/in", "depends_on": ["a"]}])
    c, rd = await f.accept(hd["id"], td, b"{}", "application/json", "")
    await asyncio.sleep(2.0)
    claims = st._db.execute("SELECT COUNT(*) FROM attempts WHERE event_id=?", (rd["event_id"],)).fetchone()[0]
    evd = st.get(rd["event_id"])
    check("R8 P1: a dependent waiting on a delivery in retry leaves the event queued for later (no claim loop)",
          claims <= 2 and evd["status"] == "queued" and float(evd["next_at"]) > time.time() + 20, (claims, evd["status"]))
    st._db.execute("UPDATE events SET status='cancelled' WHERE id=?", (rd["event_id"],))
    mx.HTTP["by_host"]["slow8.example"] = 200
    # R8 P2-1: replay keeps business dedup.
    rules = {"filter": {"path": "status", "op": "eq", "value": 1},
             "dedup": {"policy_version": 1, "business_paths": ["shop_id", "id"], "ttl_s": 86400}}
    hr, tr, _ = f.create("/b1", name="Phát lại 8", target="", text="", level="full", rules=rules,
                         actions=[{"id": "crm", "kind": "http", "url": "https://rep8.example/in"}])
    mx.HITS.clear()
    c, r1 = await f.accept(hr["id"], tr, body({"shop_id": 7, "id": 1, "status": 1}), "application/json", "k1")
    c, r2 = await f.accept(hr["id"], tr, body({"shop_id": 7, "id": 1, "status": 1}), "application/json", "k2")
    await f.wait_idle()
    s2 = st.get(r2["event_id"])["status"]
    c6, pv = f.replay_preview(r2["event_id"])
    cc, cf = f.replay_confirm(r2["event_id"], pv.get("revision"))
    await f.wait_idle()
    hits = len([x for x in mx.HITS if x["host"] == "rep8.example"])
    check("R8 P2-1: replaying a duplicate names the event holding the order's key and is refused; nothing sent twice",
          s2 == "duplicate" and pv.get("duplicate_of") == r1["event_id"] and cc == 409 and hits == 1,
          (s2, pv.get("duplicate_of"), cc, hits))
    c, r3 = await f.accept(hr["id"], tr, body({"shop_id": 7, "id": 2, "status": 4}), "application/json", "k3")
    await f.wait_idle()
    f.update(hr["id"], {"rules": dict(rules, filter={"path": "status", "op": "in", "value": [1, 4]})})
    _, pv3 = f.replay_preview(r3["event_id"])
    cc3, _ = f.replay_confirm(r3["event_id"], pv3.get("revision"))
    await f.wait_idle()
    c, r4 = await f.accept(hr["id"], tr, body({"shop_id": 7, "id": 2, "status": 4}), "application/json", "k4")
    await f.wait_idle()
    check("R8 P2-1: a filtered event replayed under looser rules takes the order's key: the source's next copy is a "
          "duplicate", cc3 == 200 and st.get(r4["event_id"])["status"] == "duplicate", (cc3, st.get(r4["event_id"])["status"]))
    # R8 P2-2: deleting a partly failed event keeps its keys (the part that succeeded never runs twice).
    mx.HTTP["by_host"]["half8b.example"] = 400
    hp, tp, _ = f.create("/b1", name="Nửa", target="", text="", level="full", rules={
        "dedup": {"policy_version": 1, "business_paths": ["id"], "ttl_s": 86400}}, actions=[
        {"id": "fwd", "kind": "http", "url": "https://half8a.example/in"},
        {"id": "fwd2", "kind": "http", "url": "https://half8b.example/in"}])
    mx.HITS.clear()
    c, rp = await f.accept(hp["id"], tp, body({"id": 9}), "application/json", "h1")
    await f.wait_idle()
    okd, _ = st.delete_event(rp["event_id"])
    c, rp2 = await f.accept(hp["id"], tp, body({"id": 9}), "application/json", "h1")
    c3, rp3 = await f.accept(hp["id"], tp, body({"id": 9}), "application/json", "h2")
    await f.wait_idle()
    a_hits = len([x for x in mx.HITS if x["host"] == "half8a.example"])
    check("R8 P2-2: after deleting a partly failed event, the same delivery and the same order are duplicates; the "
          "succeeded part ran once", okd and c == 200 and st.get(rp3["event_id"])["status"] == "duplicate"
          and a_hits == 1, (okd, c, a_hits))
    mx.HTTP["by_host"]["half8b.example"] = 200
    # R8 P2-3: a quarantined event is told (grouped) and kept with its body until the owner acts.
    hq, tq, _ = f.create("/b1", name="Cách ly", target="", text="", level="full", notify="errors_only", rules={
        "dedup": {"policy_version": 1, "business_paths": ["shop_id", "id"], "ttl_s": 86400, "missing": "quarantine"}},
        actions=[{"id": "crm", "kind": "http", "url": "https://q8.example/in"}])
    mx.SENT.clear()
    qs = []
    for i in range(3):
        c, rq = await f.accept(hq["id"], tq, body({"shopId": 7, "id": i}), "application/json", f"q{i}")
        qs.append(rq["event_id"])
    await f.wait_idle()
    told = [x for x in mx.SENT if "Cách ly" in x["text"] or "cách ly" in x["text"]]
    st.prune(time.time() + (wst.BODY_KEEP_DAYS + 40) * 86400)
    st.make_room()
    kept = [st.get(e, True) for e in qs]
    check("R8 P2-3: three quarantined orders: one grouped notice under errors_only, and every body is kept past "
          "retention and room-making", len(told) == 1 and all(k and k["status"] == "invalid" and k.get("body")
                                                              for k in kept), (len(told), [k and k["status"] for k in kept]))
    okq, _ = st.delete_event(qs[0])
    check("R8 P2-3: the owner can delete a quarantined event", okq)
    # R8 P2-4: three-valued logic with a mix of known and unknown items.
    r_any = {"filter": {"not": {"path": "items[*].price", "op": "gt", "value": 100, "quantifier": "any"}}}
    dec = [wr.evaluate(r_any, body({"items": it}), "application/json")["decision"]
           for it in ([{"price": 5}, {"price": "900"}], [{"price": 5}, {"price": 7}])]
    check("R8 P2-4: not(any price > 100) over [5, \"900\"] is unknown (filtered); over [5, 7] it runs",
          dec == ["filtered", "run"], dec)
    # R8 P3: X-Request-ID is not a delivery key for a new hook.
    hx, tx, _ = f.create("/b1", name="Req id", target="task", text="x")
    a1 = await cl.post(f"/hooks/{hx['id']}", content=b"{}", headers={"content-type": "application/json",
                                                                     "x-javis-token": tx, "x-request-id": "r1"})
    a2 = await cl.post(f"/hooks/{hx['id']}", content=b"{}", headers={"content-type": "application/json",
                                                                     "x-javis-token": tx, "x-request-id": "r1"})
    check("R8 P3: two deliveries with the same X-Request-ID on a new hook are two events (it is a per-attempt id)",
          a1.status_code == 202 and a2.status_code == 202 and a1.json()["event_id"] != a2.json()["event_id"],
          (a1.status_code, a2.status_code, a2.text[:120]))
    # R8 P1 (M4-M5): rollback switches off a hook whose AI action needs approval or a condition.
    lh, why = wrb.legacy_hook({"id": "wh_x", "name": "AI duyệt", "target": "task", "text": "x", "enabled": True,
                                "actions": [{"id": "main", "kind": "ai", "approve": True,
                                             "when": {"path": "status", "op": "eq", "value": 1}}]}, [])
    check("R8 P1: rollback writes an AI hook with approval or a condition switched off for the older build",
          lh.get("enabled") is False and any("approve" in w for w in why), (lh.get("enabled"), why))
    # R8 P2-1 (M4-M5): Retry of an event held at rollback before triage goes through the rules.
    hh, th, _ = f.create("/b1", name="Giữ", target="", text="", level="full",
                         rules={"filter": {"path": "status", "op": "eq", "value": 1}},
                         actions=[{"id": "crm", "kind": "http", "url": "https://held8.example/in"}])
    st.hook_set(hh["id"], paused=1)
    c, rh = await f.accept(hh["id"], th, body({"status": 4}), "application/json", "")
    st._db.execute("UPDATE events SET status='received' WHERE id=?", (rh["event_id"],))
    st.hold_for_rollback([rh["event_id"]])
    st.hook_set(hh["id"], paused=0)
    mx.HITS.clear()
    okr, _ = st.retry(rh["event_id"])
    f._kick()
    await f.wait_idle()
    check("R8 P2-1: Retry of an event held before triage applies the rules (status 4 is ignored, nothing sent)",
          okr and st.get(rh["event_id"])["status"] == "filtered"
          and not [x for x in mx.HITS if x["host"] == "held8.example"], (okr, st.get(rh["event_id"])["status"]))
    # R8 P2-3 (M4-M5): errors_only groups by kind of failure, not by its wording.
    fails = iter(["order 1001: no Zalo thread", "order 1002: no Zalo thread", "order 1003: no Zalo thread",
                  "HTTP 502 from x", "HTTP 504 from x", "HTTP 502 from x"])
    for i in range(6):
        ev = {"id": f"ev_s{i}", "hook_id": "wh_storm", "status": "failed",
              "branches": [{"action_id": "zalo", "status": "failed", "detail": next(fails)}]}
        res = f._incident({"id": "wh_storm"}, ev)
        if i == 0:
            told = [res[0]]
        else:
            told.append(res[0])
    check("R8 P2-3: six failures of two kinds (ids and HTTP codes differ) make two notices, not six",
          told == [True, False, False, True, False, False], told)
    # R8 P2-4 (M4-M5): customer keys a shop's payload uses are masked, numbers included.
    m = wt.mask({"ten_khach_hang": "Lê Văn An", "nguoi_nhan": {"ten": "Bình"}, "recipient": "Chi", "buyer": {"full": "Dũng"},
                 "cccd": 123456789012, "zalo": 84912345678, "shop_id": 7, "status": 1})
    flat = json.dumps(m, ensure_ascii=False)
    check("R8 P2-4: ten_khach_hang, nguoi_nhan, recipient, buyer, a numeric CCCD and Zalo id are masked; ids and "
          "status are not", not any(x in flat for x in ("Lê Văn An", "Bình", "Chi\"", "Dũng", "123456789012",
                                                       "84912345678")) and m["shop_id"] == 7 and m["status"] == 1, flat)
    # R8 P3 (M4-M5): the key overlap stays bounded whatever the client sends.
    hv, tv, _ = f.create("/b1", name="Ký", target="task", text="x", verify={"provider": "github", "secret": "s" * 20})
    hv2, _, _ = f.update(hv["id"], {"verify": {"provider": "github", "secret": "••••", "previous_secret": "x" * 20,
                                               "previous_until": 4e9}})
    pu = float((st.hook_get(hv["id"]).get("verify") or {}).get("previous_until") or 0)
    check("R8 P3: a previous key and its end sent by the client are ignored (no overlap until 2096)",
          pu < time.time() + 169 * 3600, pu)
    for i in range(5100):
        f._fails.setdefault(f"10.0.{i // 250}.{i % 250}", __import__("collections").deque()).append(time.time() - 120)
    f._fails.setdefault("203.0.113.9", __import__("collections").deque()).extend([time.time()] * 5)
    f._auth_failed("203.0.113.10", time.time())
    check("R8 P3: past 5,000 addresses only finished ones are forgotten; a current one keeps its count",
          len(f._fails.get("203.0.113.9") or []) == 5 and len(f._fails) < 5000, len(f._fails))
    await cl.aclose()


async def main():
    await rules_and_triage()
    await receiving()
    await store_and_delivery()
    await rollback_cycle()
    await privacy_and_ops()
    await plugin_fairness()
    await second_round()
    await whole_chain()
    await fix_review()
    await chain_review_two()


if __name__ == "__main__":
    asyncio.run(main())
    if fails:
        print(f"\nFAIL {len(fails)}: " + "; ".join(fails))
        sys.exit(1)
    print("\nOK - test_webhook_spec_review: all pass")
