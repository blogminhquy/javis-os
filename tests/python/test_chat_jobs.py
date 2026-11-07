"""POST /chat/jobs starts a /chat turn in the background; GET /chat/jobs/{id} fetches it later (#1021).

    python tests/run.py chat_jobs        (no network, the turn itself is faked)

A caller on a serverless host pays for every second `/chat` holds the request open, and a dropped
connection loses an answer Javis already finished. What is pinned, through the real routes and the
real login middleware, with only `_cli_turn` faked:
  1. The same 400s as /chat come back before anything starts, and /chat itself still answers.
  2. A job answers at once with a job id, reads `running`, then `done` with the /chat payload.
  3. A job belongs to the token that started it: another token, or the signed-in owner, gets 404.
     With the login gate on, the middleware records which token called.
  4. A chat-scope token reaches /chat/jobs with no new scope.
  5. One running job per session (409) and a per-caller cap on running jobs (429).
  6. A failed turn or a crash reads `error` with the reason, never stuck on `running`.
  7. A job left running by a restart reads `error`; finished jobs expire after the TTL.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-chat-jobs-")
os.environ["BRAINS_DIR"] = tempfile.mkdtemp(prefix="javis-chat-jobs-brains-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main  # noqa: E402
import chat_jobs  # noqa: E402
import config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{detail!r}]"))
    if not cond:
        _fails.append(name)


# ---------------------------------------------------------------- fake turn
# Each turn waits on a gate the test opens, so "running" can be observed. The message picks the outcome.
GATES = {}
CALLS = []


async def fake_cli_turn(message, brain, session, host, progress=None, agent=None, project_id=""):
    CALLS.append(message)
    gate = GATES.setdefault(message, asyncio.Event())
    await gate.wait()
    key = main._cli_sess_key(session)
    if message.startswith("fail"):
        return "engine is down", key
    if message.startswith("crash"):
        raise RuntimeError("boom")
    return {"text": "answer to " + message, "files": ["exports/a.pdf"], "ctx_path": "compiled"}, key


main._cli_turn = fake_cli_turn


def release(client, message):
    """Open the gate of a turn from inside the app's event loop."""
    client.portal.call(lambda: GATES.setdefault(message, asyncio.Event()).set())


def wait_status(client, job_id, headers, want, tries=200):
    body = {}
    for _ in range(tries):
        r = client.get(f"/chat/jobs/{job_id}", headers=headers)
        body = r.json()
        if body.get("status") == want:
            return body
        time.sleep(0.01)
    return body


tok_a = config.create_api_token("a", scope="chat")["token"]
tok_b = config.create_api_token("b", scope="chat")["token"]
A = {"Authorization": "Bearer " + tok_a}
B = {"Authorization": "Bearer " + tok_b}

# ---------------------------------------------------------------- 4. scope
for path in ("/chat/jobs", "/chat/jobs/cj_x"):
    check(f"4. a chat token reaches {path}", config.verify_api_token(tok_a, path) is not None)

# Login gate on, like a public server: every call goes through the token branch of the middleware.
main.cfgmod.gate_active = lambda: True
main.cfgmod.auth_enabled = lambda: True

with TestClient(main.app, base_url="http://localhost:7777") as cl:
    # ------------------------------------------------------------ 1. checks first
    r = cl.post("/chat/jobs", data={"message": "   "}, headers=A)
    check("1. an empty message is a 400", r.status_code == 400, r.text)
    r = cl.post("/chat/jobs", data={"message": "hi", "agent": "no-such-agent"}, headers=A)
    check("1. an unknown agent is a 400", r.status_code == 400, r.text)
    check("1. no turn ran for a rejected job", CALLS == [], CALLS)
    r = cl.post("/chat/jobs", data={"message": "hi"})
    check("1. no token, no login: 401", r.status_code == 401, r.status_code)

    release(cl, "sync")
    r = cl.post("/chat", data={"message": "sync"}, headers=A)
    check("1. /chat still answers after the refactor", r.json().get("text") == "answer to sync", r.text)
    r = cl.post("/chat", data={"message": " "}, headers=A)
    check("1. /chat still answers 400 on an empty message", r.status_code == 400, r.text)

    # ------------------------------------------------------------ 2. lifecycle
    r = cl.post("/chat/jobs", data={"message": "one", "session": "s1"}, headers=A)
    body = r.json()
    job = body.get("job_id") or ""
    check("2. a job answers at once with an id", r.status_code == 200 and body.get("ok") and job.startswith("cj_"), body)
    r = cl.get(f"/chat/jobs/{job}", headers=A)
    body = r.json()
    check("2. the job reads running", body.get("status") == "running" and body.get("finished_at") is None, body)
    check("2. a running job carries no answer yet", "text" not in body, body)

    # ------------------------------------------------------------ 3. owner isolation
    check("3. another token gets 404", cl.get(f"/chat/jobs/{job}", headers=B).status_code == 404)
    check("3. no token gets 401", cl.get(f"/chat/jobs/{job}").status_code == 401)
    check("3. an unknown id is a 404", cl.get("/chat/jobs/cj_nope", headers=A).status_code == 404)

    # ------------------------------------------------------------ 5. limits
    r = cl.post("/chat/jobs", data={"message": "two", "session": "s1"}, headers=B)
    check("5. a second job on the same session is a 409", r.status_code == 409, r.text)
    r = cl.post("/chat/jobs", data={"message": "two", "session": "s1", "agent": ""}, headers=A)
    check("5. even from the same token", r.status_code == 409, r.text)
    started = []
    for i in range(chat_jobs.MAX_RUNNING_PER_OWNER - 1):
        r = cl.post("/chat/jobs", data={"message": f"cap{i}", "session": f"cap{i}"}, headers=A)
        started.append(r.json().get("job_id"))
    check("5. jobs on other sessions start up to the cap", all(started), started)
    r = cl.post("/chat/jobs", data={"message": "over", "session": "over"}, headers=A)
    check("5. one more running job for this token is a 429", r.status_code == 429, r.text)
    r = cl.post("/chat/jobs", data={"message": "b-own", "session": "b-own"}, headers=B)
    check("5. the cap is per token: another token still starts", r.status_code == 200, r.text)
    for i in range(chat_jobs.MAX_RUNNING_PER_OWNER - 1):
        release(cl, f"cap{i}")
    release(cl, "b-own")

    # ------------------------------------------------------------ 2. done
    release(cl, "one")
    body = wait_status(cl, job, A, "done")
    check("2. the job reads done", body.get("status") == "done", body)
    check("2. done carries the /chat payload",
          body.get("text") == "answer to one" and body.get("session") == "cli:s1"
          and body.get("files") == ["exports/a.pdf"] and body.get("ctx_path") == "compiled", body)
    check("2. done has a finish time", isinstance(body.get("finished_at"), (int, float)), body)
    r = cl.post("/chat/jobs", data={"message": "three", "session": "s1"}, headers=A)
    check("5. the session takes a new job once the old one is done", r.status_code == 200, r.text)
    release(cl, "three")

    # ------------------------------------------------------------ 6. failures
    j_fail = cl.post("/chat/jobs", data={"message": "fail-1", "session": "f1"}, headers=A).json()["job_id"]
    j_crash = cl.post("/chat/jobs", data={"message": "crash-1", "session": "f2"}, headers=A).json()["job_id"]
    release(cl, "fail-1")
    release(cl, "crash-1")
    body = wait_status(cl, j_fail, A, "error")
    check("6. a failed turn reads error with the reason",
          body.get("status") == "error" and body.get("error") == "engine is down", body)
    body = wait_status(cl, j_crash, A, "error")
    check("6. a crash reads error with the exception", "RuntimeError: boom" in str(body.get("error")), body)

    # ------------------------------------------------------------ 3. the owner's own jobs
    main.cfgmod.gate_active = lambda: False   # a server with no login: the owner, no token
    r = cl.post("/chat/jobs", data={"message": "mine", "session": "mine"})
    mine = r.json().get("job_id")
    check("3. the owner starts a job without a token", bool(mine), r.text)
    check("3. a token cannot read the owner's job", cl.get(f"/chat/jobs/{mine}", headers=A).status_code == 404)
    check("3. the owner cannot read a token's job", cl.get(f"/chat/jobs/{job}").status_code == 404)
    check("3. with no gate the token still reads its own job",
          cl.get(f"/chat/jobs/{job}", headers=A).json().get("status") == "done")
    release(cl, "mine")
    main.cfgmod.gate_active = lambda: True

# ---------------------------------------------------------------- 7. restart and expiry
store_path = Path(tempfile.mkdtemp(prefix="javis-chat-jobs-store-")) / "chat_jobs.json"
now = time.time()
store_path.write_text(json.dumps({
    "cj_cut": {"owner": "owner", "lane": "cli:x", "status": "running", "boot": "old-process",
               "created_at": now - 60, "finished_at": None},
    "cj_old": {"owner": "owner", "lane": "cli:y", "status": "done", "boot": "old-process",
               "created_at": now - chat_jobs.JOB_TTL - 100, "finished_at": now - chat_jobs.JOB_TTL - 50,
               "result": {"text": "stale"}},
    "cj_new": {"owner": "owner", "lane": "cli:z", "status": "done", "boot": "old-process",
               "created_at": now - 100, "finished_at": now - 50, "result": {"text": "fresh"}},
}), encoding="utf-8")
store = chat_jobs.ChatJobs(store_path)
cut = store.get("owner", "cj_cut")
check("7. a job cut off by a restart reads error",
      cut and cut["status"] == "error" and cut["error"] == chat_jobs.RESTART_ERROR, cut)
check("7. an expired job is gone", store.get("owner", "cj_old") is None)
check("7. a recent finished job survives a restart", (store.get("owner", "cj_new") or {}).get("text") == "fresh")
check("7. the expired job was dropped from the file", "cj_old" not in json.loads(store_path.read_text(encoding="utf-8")))

if _fails:
    print(f"\n{len(_fails)} FAILED")
    sys.exit(1)
print("\nall ok")
