"""0.274.0: a short run of the §16 ingress benchmark (tools/webhook_bench.py), over a real HTTP socket.

    python tests/run.py webhook_bench_short

The full target (60 s, 20 req/s, 5 hooks, 10 KiB, p95 ACK under 250 ms) is run by hand and its numbers are recorded in
docs/webhook-platform/README.md. Here, in CI: the same rate and payload for a few seconds, the same targets, slow
actions at the receiver (ingress must not wait for them), and a negative control proving the model guard counts.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import sys

sys.path.insert(0, str(ROOT / "tools"))
import webhook_bench as wb  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


fast = wb.run(seconds=8, rate=20, hooks=5, size_kib=10)
for k, v in fast["targets"].items():
    check(f"§16 benchmark (8 s, 20 req/s, 5 hooks, 10 KiB): {k}", v, {"ack": fast["load"]["ack_ms"],
                                                                      "store": fast["store"], "codes": fast["load"]["codes"]})
slow = wb.run(seconds=5, rate=20, hooks=5, size_kib=10, slow=1.5)
check("§16 benchmark: with every action waiting 1.5 s at the receiver, ACK p95 stays under 250 ms (ingress is not "
      "held by business latency), every 202 is stored and the rest waits in the queue", slow["ok"], {"ack": slow["load"]["ack_ms"],
                                                                          "targets": slow["targets"]})
check("§16 benchmark: processing latency is measured apart and does show the slow receiver",
      (slow["store"]["processing_s"]["p50"] or 0) >= 1.4, slow["store"]["processing_s"])
ctl = wb.run(seconds=2, rate=10, hooks=2, size_kib=1, ai_control=True)
check("negative control: a hook WITH an AI action does reach the model guard (the zero above is a real zero)",
      ctl["model_calls"] > 0, ctl["model_calls"])

if fails:
    print(f"\nFAIL {len(fails)}: " + "; ".join(fails))
    sys.exit(1)
print("\nOK - test_webhook_bench_short: all pass")
