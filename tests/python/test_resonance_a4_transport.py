"""Resonance A4: đường truyền THẬT của công cụ nộp và API chủ dự án (thiết kế A4 mục 6.1, 10; ca G20, G22).

    python tests/run.py resonance_a4_transport -v

Không gọi model hay mạng thật. Ba đường mang danh tính lượt tới `javis_submit_deliverable`:
1. engine API: plugin trong tiến trình (route thật của `plugins_host`), ngữ cảnh lượt gắn trong tiến trình;
2. Codex: hub HTTP thật (`mcp_hub.handle_http`) với khoá `X-Javis-Turn`, chạy trong ngữ cảnh rỗng như tiến trình con;
3. Claude Code: server MCP plugin trong tiến trình THẬT (`ClaudeSDK._plugins_server`).
Rồi chủ dự án Cho phép qua `POST /goals/{id}/commands` của main.app (đăng đúng bản nháp, thẻ cũ 409) và xem trước bản
nháp qua `GET /goals/{id}/drafts/{submission_id}`.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import contextvars
import hashlib
import json
import os
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-a4x-")
os.environ["JAVIS_STATE_DIR"] = _STATE

import main  # noqa: E402
import mcp_hub  # noqa: E402
import plugins_host  # noqa: E402
import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402
import turn_context  # noqa: E402
import _resonance_agent as RA  # noqa: E402
import claude_sdk_engine  # noqa: E402
from mcp.types import CallToolRequest, CallToolRequestParams  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_fails = []


def check(name, cond, info=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or info is None else f"  ({str(info)[:300]})"))
    if not cond:
        _fails.append(name)


class Evidence:
    def __init__(self):
        self.items = {}

    def put(self, goal, label, text, meta):
        eid = f"ev_{len(self.items) + 1}"
        self.items[eid] = {"text": text, "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        return eid

    def valid(self, eid):
        return self.items.get(eid)


main._RESONANCE_EVIDENCE = Evidence()
BRAIN = main._brain_key(str(Path(tempfile.mkdtemp(prefix="brain-a4x-")).resolve()))
OWNER = RS.Principal("owner", "owner", BRAIN)
store = main._resonance_store()
DELIV = "Docs/hd.md"
GOOD = "# Hướng dẫn nhận hàng\n\n## Lỗi hay gặp\n\n- Thiếu phiếu\n"
USER = "Em lo giúp anh bản hướng dẫn nhận hàng, sửa tới khi anh thấy dùng được. Lưu ở Docs/hd.md."
PROPOSAL = {"understanding": "Bản hướng dẫn nhận hàng", "relevant_quote": "Em lo giúp anh bản hướng dẫn nhận hàng",
            "criteria": [{"description": "Có mục Lỗi hay gặp", "evaluator": "artifact_contract",
                          "params": {"path": DELIV, "must_contain": ["Lỗi hay gặp"]}}],
            "horizon": {"kind": "review", "at_iso": "2027-01-20T09:00:00+07:00"}, "stage": "delivery",
            "mode": "achieve"}
A = RA.enable(store, BRAIN, "viet-bai")
_, ROUTE = plugins_host.plugin_tools("full", BRAIN, scope_vault=False)
GOAL = ROUTE["javis_goal"]["call"]
SUBMIT = ROUTE["javis_submit_deliverable"]["call"]
check("G22 plugin javis-goal có cả hai công cụ: javis_goal và javis_submit_deliverable",
      "javis_goal" in ROUTE and "javis_submit_deliverable" in ROUTE)


def handoff_of(text):
    for part in str(text).split():
        if part.startswith("handoff="):
            return part[len("handoff="):].rstrip(".,")
    return ""


# ═══════════ 1. engine API: trong tiến trình ═══════════
with RA.turn(A, "eA", 1, USER, BRAIN, slug="viet-bai", store=store):
    out = asyncio.run(GOAL({"op": "create", **PROPOSAL}))
    h1 = handoff_of(out)
    sub1 = asyncio.run(SUBMIT({"path": DELIV, "content": GOOD, "handoff": h1}))
g1 = store.find_by_key(OWNER, R.message_ref("eA", 1))
check("1 engine API: javis_goal nói rõ phạm vi CHƯA được cho phép và trả mã bàn giao",
      "CHƯA được cho phép" in out and h1.startswith("bd_"), out[-400:])
check("1 engine API: nộp giữ làm nháp, chưa ghi file đích", "NHÁP" in sub1 and not (Path(BRAIN) / DELIV).exists()
      and [s["status"] for s in store.submissions(OWNER, g1.id)] == ["awaiting_scope"], sub1)
out_plain = asyncio.run(SUBMIT({"path": DELIV, "content": GOOD}))
check("G20 gọi ngoài lượt: ERROR no_turn, không ghi bản nộp", out_plain.startswith("ERROR no_turn")
      and len(store.submissions(OWNER, g1.id)) == 1, out_plain)


# ═══════════ 2. Codex: hub HTTP với khoá X-Javis-Turn ═══════════
class _Req:
    def __init__(self, headers, body):
        self.headers = {k.lower(): v for k, v in headers.items()}
        self._body = body

    async def json(self):
        return self._body


async def _hub(key, name, args, i=1):
    h = {"Authorization": "Bearer T"}
    if key is not None:
        h[turn_context.HEADER] = key
    body = {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}
    resp = await asyncio.create_task(mcp_hub.handle_http(_Req(h, body)), context=contextvars.Context())
    return json.loads(resp.body)["result"]["content"][0]["text"]


mcp_hub.hub_token = lambda: "T"


async def _fake_discover(*a, **kw):
    return [], {"javis_goal": ROUTE["javis_goal"], "javis_submit_deliverable": ROUTE["javis_submit_deliverable"]}
mcp_hub.discover_all = _fake_discover

with RA.turn(A, "cA", 1, USER, BRAIN, slug="viet-bai", store=store):
    key = turn_context.issue_key()
    out2 = asyncio.run(_hub(key, "javis_goal", {"op": "create", **PROPOSAL}))
    sub2 = asyncio.run(_hub(key, "javis_submit_deliverable", {"path": DELIV, "content": GOOD,
                                                                "handoff": handoff_of(out2)}))
g2 = store.find_by_key(OWNER, R.message_ref("cA", 1))
check("2 Codex qua hub với khoá lượt: nộp đúng mục tiêu của lượt, giữ làm nháp", "NHÁP" in sub2
      and [s["status"] for s in store.submissions(OWNER, g2.id)] == ["awaiting_scope"], sub2)
no_key = asyncio.run(_hub(None, "javis_submit_deliverable", {"path": DELIV, "content": GOOD}))
dead = asyncio.run(_hub(key, "javis_submit_deliverable", {"path": DELIV, "content": GOOD + "x"}))
check("G22 không có khoá lượt (đường của Grok, Antigravity) hay khoá của lượt đã xong: ERROR, không ghi bản nộp",
      no_key.startswith("ERROR") and dead.startswith("ERROR") and len(store.submissions(OWNER, g2.id)) == 1,
      (no_key, dead))


# ═══════════ 3. Claude Code: server plugin trong tiến trình ═══════════
async def _sdk(name, args):
    e = claude_sdk_engine.ClaudeSDK(cwd=BRAIN)
    e.javis_vault = BRAIN
    server = e._plugins_server()["instance"]
    req = CallToolRequest(method="tools/call", params=CallToolRequestParams(name=name, arguments=args))
    res = await server.request_handlers[CallToolRequest](req)
    return res.root.content[0].text


with RA.turn(A, "kA", 1, USER, BRAIN, slug="viet-bai", store=store):
    out3 = asyncio.run(_sdk("javis_goal", {"op": "create", **PROPOSAL}))
    sub3 = asyncio.run(_sdk("javis_submit_deliverable", {"path": DELIV, "content": GOOD, "handoff": handoff_of(out3)}))
g3 = store.find_by_key(OWNER, R.message_ref("kA", 1))
check("3 Claude Code qua server plugin thật: nộp đúng mục tiêu của lượt", "NHÁP" in sub3
      and [s["status"] for s in store.submissions(OWNER, g3.id)] == ["awaiting_scope"], sub3)

# ═══════════ 4. API chủ dự án: xem trước, Cho phép, thẻ cũ ═══════════
client = TestClient(main.app, base_url="http://127.0.0.1:8080")
view = client.get(f"/goals/{g1.id}", params={"brain": BRAIN}).json()["goal"]
sc = view["scope"]
check("4 thẻ: chờ cho phép, có yêu cầu và bản nháp (mã, sha, kích thước, không có nội dung)",
      sc["state"] == "pending" and sc["request"]["id"] and sc["draft"]["submission_id"] and "content" not in sc["draft"],
      sc)
pv = client.get(f"/goals/{g1.id}/drafts/{sc['draft']['submission_id']}", params={"brain": BRAIN})
check("4 xem trước bản nháp: đúng nội dung host đã nhận", pv.status_code == 200 and pv.json()["content"] == GOOD)
pv_x = client.get(f"/goals/{g1.id}/drafts/{store.submissions(OWNER, g2.id)[0]['id']}", params={"brain": BRAIN})
check("4 xem trước bản nộp của mục tiêu khác qua id mục tiêu này: 404", pv_x.status_code == 404)
bad = client.post(f"/goals/{g1.id}/commands", params={"brain": BRAIN},
                  json={"command": "approve_scope", "request_id": sc["request"]["id"], "path": DELIV,
                        "submission_id": sc["draft"]["submission_id"], "sha256": "sai"})
check("4 thẻ cũ (sha bản nháp khác): 409, không tạo gốc", bad.status_code == 409
      and store.scope_state(OWNER, g1.id)["root"] is None, bad.text)
ok = client.post(f"/goals/{g1.id}/commands", params={"brain": BRAIN},
                 json={"command": "approve_scope", "request_id": sc["request"]["id"], "path": DELIV,
                       "submission_id": sc["draft"]["submission_id"], "sha256": sc["draft"]["sha256"]})
check("4 Cho phép đúng thẻ: đăng đúng bản nháp vào file đích, thẻ trả trạng thái đã cho phép",
      ok.status_code == 200 and ok.json().get("publish") == "succeeded"
      and (Path(BRAIN) / DELIV).read_text(encoding="utf-8") == GOOD and ok.json()["goal"]["scope"]["state"] == "granted",
      ok.text[:300])
rv = client.post(f"/goals/{g1.id}/commands", params={"brain": BRAIN},
                 json={"command": "revoke_grant", "expected_revision": ok.json()["goal"]["revision"]})
check("4 Thu hồi quyền: gốc revoked, mục tiêu tạm dừng", rv.status_code == 200
      and rv.json()["goal"]["scope"]["state"] == "revoked" and rv.json()["goal"]["paused"], rv.text[:300])
rs = client.post(f"/goals/{g1.id}/commands", params={"brain": BRAIN}, json={"command": "resume"})
check("4 Tiếp tục khi đang thu hồi: cấp lại gốc MỚI, gỡ tạm dừng", rs.status_code == 200
      and rs.json()["goal"]["scope"]["state"] == "granted" and not rs.json()["goal"]["paused"]
      and store.scope_state(OWNER, g1.id)["root"]["source_ref"].get("regrant_of"), rs.text[:300])

if _fails:
    print(f"\n{len(_fails)} FAIL: {_fails}")
raise SystemExit(1 if _fails else 0)
