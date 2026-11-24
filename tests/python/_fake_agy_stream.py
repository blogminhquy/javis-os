"""A stand-in for `agy --input-format stream-json --output-format stream-json` (agy 1.5.15, measured 2026-11-24).

Used by test_agy_warm.py. It follows what the real binary does:
- prints `init` with its conversation id before any message;
- `--conversation <id>` resumes a conversation it knows; an unknown id prints a warning on stderr and opens a NEW
  conversation with another id (exit 0, no error);
- each stdin line {"event":"user","message":{...}} is one turn: step updates, then a `result` whose usage is the
  RUNNING TOTAL of the process, as on the real binary;
- EOF on stdin ends it with exit 0.

State lives in the folder named by FAKE_AGY_DIR: one file per conversation, and `received.jsonl` with every message
the process was sent (pid, conversation, text), so a test can check what Javis sent.

Message keywords steer a turn: RUNCMD (a finished command), BGCMD (a command left running in the background),
FAIL503 (a provider error before any work), SLOW (a long turn), NOINIT in argv (exit before init).
"""
import json
import os
import sys
import time
import uuid

state = os.environ["FAKE_AGY_DIR"]
os.makedirs(state, exist_ok=True)
argv = sys.argv[1:]
if "NOINIT" in argv:
    sys.stderr.write("fatal: cannot start\n")
    sys.exit(1)


def out(ev):
    sys.stdout.write(json.dumps(ev) + "\n")
    sys.stdout.flush()


want = argv[argv.index("--conversation") + 1] if "--conversation" in argv else ""
if want and os.path.exists(os.path.join(state, want)):
    cid = want
else:
    if want:
        sys.stderr.write(f'warning: conversation "{want}" not found\n')
        sys.stderr.flush()
    cid = str(uuid.uuid4())
    open(os.path.join(state, cid), "w").close()
out({"event": "init", "conversation_id": cid, "init": {"model": "fake", "cwd": os.getcwd()}})

total_in = total_cache = 0
for raw in sys.stdin:
    raw = raw.strip()
    if not raw:
        continue
    msg = json.loads(raw)["message"]["content"]
    with open(os.path.join(state, cid), "a", encoding="utf-8") as f:
        f.write(msg + "\n---\n")
    with open(os.path.join(state, "received.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"pid": os.getpid(), "cid": cid, "text": msg}) + "\n")
    out({"event": "step_update", "step_update": {"conversation_id": cid, "step_index": 0, "state": "DONE",
                                                   "step_type": "user_input"}})
    if "FAIL503" in msg:
        out({"event": "result", "result": {"conversation_id": cid, "status": "ERROR",
                                           "error": {"message": "Eligibility check failed: UNAVAILABLE (code 503)"}}})
        continue
    idx = 1
    if "RUNCMD" in msg or "BGCMD" in msg:
        line = "nohup sleep 100 &" if "BGCMD" in msg else "git status"
        params = {"CommandLine": line, "toolSummary": "Check the repo"}
        out({"event": "step_update", "step_update": {
            "conversation_id": cid, "step_index": idx, "state": "ACTIVE", "step_type": "tool",
            "tool_name": "run_command", "tool_info": {"name": "run_command", "parameters": params}}})
        out({"event": "step_update", "step_update": {
            "conversation_id": cid, "step_index": idx, "state": "DONE", "step_type": "tool",
            "tool_name": "run_command", "tool_info": {"name": "run_command", "parameters": params,
                                                      "output": "Command exited with code 0.\nOutput: ok"}}})
        idx += 1
    if "SLOW" in msg:
        time.sleep(30)
    answer = f"answer {len(open(os.path.join(state, cid), encoding='utf-8').read().split('---')) - 1}"
    step_in, step_cache = 200, 10000
    total_in += step_in
    total_cache += step_cache
    out({"event": "step_update", "step_update": {
        "conversation_id": cid, "step_index": idx, "state": "ACTIVE", "step_type": "agent_response",
        "text_delta": answer[:3]}})
    out({"event": "step_update", "step_update": {
        "conversation_id": cid, "step_index": idx, "state": "DONE", "step_type": "agent_response",
        "text_delta": answer[3:], "usage": {"input_tokens": step_in, "output_tokens": 2,
                                            "cache_read_tokens": step_cache, "total_tokens": step_in + 2}}})
    out({"event": "result", "result": {"conversation_id": cid, "status": "SUCCESS", "response": answer,
                                       "usage": {"input_tokens": total_in, "output_tokens": 2,
                                                 "cache_read_tokens": total_cache}}})
time.sleep(0.2)
sys.exit(0)
