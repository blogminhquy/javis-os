"""fb_page_insights: read Page and post insights with the Page token (issue #1879).

    python tests/run.py meta_pages_insights      (no network, fake Graph API)

Checks: read only; Page insights take period and a since-until range (default 28 days, at most 90); a post's insights
are lifetime and the Page is found from the post id; a refused metric is retried one by one and named; a permission
error tells how to grant read_insights; metric names are validated; no Page token leaks into the answer.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import datetime
import importlib.util
import json
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-fbinsights-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(detail) + "]") if detail and not cond else ""))
    if not cond:
        _fails.append(name)


spec = importlib.util.spec_from_file_location(
    "meta_pages_insights_test", str(ROOT / "system" / "plugins" / "meta-pages-graph" / "plugin.py"))
plug = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plug)


class _Ctx:
    def __init__(self):
        self.tools = {}

    def register_tool(self, name, description, handler, schema=None, min_mode="readonly", check_fn=None, **k):
        self.tools[name] = {"min_mode": min_mode, "description": description, "schema": schema}


ctx = _Ctx()
plug.register(ctx)
check("registered, read only", ctx.tools.get("fb_page_insights", {}).get("min_mode") == "readonly")
yaml = (ROOT / "system" / "plugins" / "meta-pages-graph" / "plugin.yaml").read_text(encoding="utf-8")
check("listed in plugin.yaml", "  - fb_page_insights" in yaml)

CALLS = []
REFUSE = set()
PAGES = {"data": [{"id": "P1", "name": "Shop A", "access_token": "PTOKA"},
                  {"id": "P2", "name": "Shop B", "access_token": "PTOKB"}]}


async def _fake_token():
    return "USERTOK"


async def _fake_get(path, params, token):
    CALLS.append((path, dict(params or {}), token))
    if path == "me/accounts":
        return PAGES
    if path.endswith("/insights"):
        names = str(params.get("metric") or "").split(",")
        if any(n in REFUSE for n in names):
            if REFUSE == {"*perm*"} or "*perm*" in REFUSE:
                return {"error": {"message": "(#10) This endpoint requires the 'read_insights' permission", "code": 10}}
            return {"error": {"message": "(#100) The value must be a valid insights metric", "code": 100}}
        return {"data": [{"name": n, "period": params.get("period"), "title": n.upper(),
                          "values": [{"end_time": "2026-11-26T08:00:00+0000", "value": 7}]} for n in names]}
    return {"data": []}


plug._token = _fake_token
plug._get = _fake_get


def run(args):
    CALLS.clear()
    return asyncio.run(plug._insights(args, None))


out = json.loads(run({"page": "Shop A"}))
ins = [c for c in CALLS if c[0].endswith("/insights")]
check("Page insights: one call with the default metrics and the Page token",
      len(ins) == 1 and ins[0][0] == "P1/insights" and ins[0][2] == "PTOKA"
      and ins[0][1]["metric"] == ",".join(plug.PAGE_METRICS), ins)
today = datetime.date.today()
check("default: daily, the last 28 days",
      out["period"] == "day" and out["until"] == today.isoformat()
      and out["since"] == (today - datetime.timedelta(days=28)).isoformat(), out)
check("rows carry metric, period and values", out["metrics"][0]["values"][0]["value"] == 7 and out["page"]["name"] == "Shop A")
check("no Page token in the answer", "PTOKA" not in json.dumps(out))

out = json.loads(run({"post_id": "P2_99"}))
ins = [c for c in CALLS if c[0].endswith("/insights")]
check("post insights: Page found from the post id, lifetime, post metrics",
      ins and ins[0][0] == "P2_99/insights" and ins[0][2] == "PTOKB" and ins[0][1] == {
          "period": "lifetime", "metric": ",".join(plug.POST_METRICS)}, ins)

REFUSE.clear()
REFUSE.add("page_follows")
out = json.loads(run({"page_id": "P1"}))
check("a refused metric: the others still come back, the refused one is named",
      [m["metric"] for m in out["metrics"]] == [m for m in plug.PAGE_METRICS if m != "page_follows"]
      and out.get("refused_metrics") == ["page_follows"] and out.get("note"), out)

REFUSE.clear()
REFUSE.update({"*perm*", *plug.PAGE_METRICS})
r = run({"page_id": "P1"})
check("no permission: an error that says how to grant read_insights",
      r.startswith("ERROR") and "read_insights" in r and "Read post insights" in r, r)
REFUSE.clear()

check("custom metrics are used", json.loads(run({"page_id": "P1", "metrics": ["page_fans_country"]}))["metrics"][0]["metric"]
      == "page_fans_country")
check("an invalid metric name is refused before any call",
      run({"page_id": "P1", "metrics": ["x;drop"]}).startswith("ERROR") and not CALLS)
check("more than 90 days is refused", run({"page_id": "P1", "since": "2026-01-01", "until": "2026-06-01"}).startswith("ERROR"))
check("a bad date is refused", run({"page_id": "P1", "since": "26/11/2026"}).startswith("ERROR"))
check("a bad period is refused", run({"page_id": "P1", "period": "month"}).startswith("ERROR"))
check("several Pages and none named: asks which", run({}).startswith("ERROR"))

check("tool text is English (prompt rule)", "Read INSIGHTS" in ctx.tools["fb_page_insights"]["description"])
check("no em dash in this file", chr(0x2014) not in open(__file__, encoding="utf-8").read())

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nPASS")
