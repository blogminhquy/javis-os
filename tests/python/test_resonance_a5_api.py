"""Resonance A5: API của chủ dự án cho đội làm và review (thiết kế mục 4.2, 11, 12).

    python tests/run.py resonance_a5_api -v

Đi qua CHÍNH các route thật (`resonance_api.register`, `register_agents`, `register_a5`) trên một app FastAPI riêng với
kho SQLite thật và engine giả; không gọi model thật. Kiểm: chọn và bỏ chọn người review theo slug (lưu theo mã bền),
từ chối trợ lý chưa bật hay chính nó, dòng `reviewer` trong danh sách trợ lý, khối `team` của goal view, lệnh
`team_detach` của chủ dự án.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
from pathlib import Path

_STATE = Path(tempfile.mkdtemp(prefix="javis-res-a5api-"))
os.environ["JAVIS_STATE_DIR"] = str(_STATE)
os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import resonance_api as RAPI  # noqa: E402
import resonance_store as RS  # noqa: E402
import _resonance_agent as RA  # noqa: E402
import _resonance_team as T  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not detail else f"  [{str(detail)[:300]}]"))
    if not cond:
        _fails.append(name)


t = T.Team(_STATE, "resonance", pair=False)        # kho mặc định: route mở RS.GoalStore() khi kiểm "_store_exists"
RA.enable(t.store, t.brain, "tat")
RA.disable(t.store, t.brain, "tat")


def _metas(root):
    d = Path(root) / "agents"
    return [{"slug": f.stem, "name": f.stem, "provider": "anthropic-cli"} for f in sorted(d.glob("*.md"))]


def _file(root, slug):
    f = Path(root) / "agents" / f"{slug}.md"
    return f if f.is_file() else None


deps = RAPI.ResonanceApiDeps(store=lambda: t.store, brain_key=lambda b: t.brain,
                             engine_factory=lambda s, tag: (None, {}), session_store=lambda: None,
                             agents_meta=_metas, agent_file=_file)
app = FastAPI()
RAPI.register(app, deps)
RAPI.register_agents(app, deps)
RAPI.register_a5(app, deps)
C = TestClient(app)


def row(slug):
    return next(a for a in C.get("/resonance/agents", params={"brain": "x"}).json()["agents"] if a["slug"] == slug)


check("chưa chọn: reviewer của trợ lý là None", row(T.MAKER)["reviewer"] is None)
# 0.142.0: bỏ người review cố định. Route còn để dashboard cũ nhận câu trả lời rõ: chọn người là 410, không lưu gì.
r = C.post("/resonance/agents/reviewer", params={"brain": "x"}, json={"slug": T.MAKER, "reviewer_slug": T.REVIEWER})
check("0.142.0: chọn người review bị từ chối 410, cặp không được tạo", r.status_code == 410 and r.json().get("removed")
      and row(T.MAKER)["reviewer"] is None and t.store.team_pair(t.brain, t.maker["agent_key"]) is None, r.text)
r = C.post("/resonance/agents/reviewer", params={"brain": "x"}, json={"slug": T.MAKER, "reviewer_slug": ""})
check("0.142.0: bỏ chọn là thành công, không làm gì", r.status_code == 200 and r.json().get("removed"), r.text)

# Mục tiêu CŨ có đội (dựng thẳng qua kho như trước 0.142.0): thẻ vẫn hiện đội, lượt, vòng để lịch sử review không mất.
t.store.team_pair_set(t.owner, t.maker["agent_key"], t.reviewer["agent_key"])
g = t.create()
t.wake(g)
v = C.get(f"/goals/{g.id}", params={"brain": "x"}).json()["goal"]
tm = v.get("team") or {}
check("goal view có khối team: hai vai theo slug hiện tại, lượt theo vai, vòng, trạng thái chờ review",
      tm.get("maker", {}).get("slug") == T.MAKER and tm.get("reviewer", {}).get("slug") == T.REVIEWER
      and tm.get("calls") == {"maker": {"cap": 4, "used": 1}, "reviewer": {"cap": 4, "used": 0}}
      and tm.get("max_rounds") == 2 and v.get("block_reason") == "review_pending", tm)
check("goal view không chứa tag", "tags" not in tm and "tag" not in str(tm.get("reviewer")))

r = C.post(f"/goals/{g.id}/commands", params={"brain": "x"}, json={"command": "team_detach"})
check("lệnh team_detach của chủ dự án: tách đội, goal view nói đã tách", r.status_code == 200
      and r.json().get("status") == "team_detached" and r.json()["goal"]["team"]["status"] == "detached", r.text)
r = C.post(f"/goals/{g.id}/commands", params={"brain": "x"}, json={"command": "team_detach"})
check("tách lần hai: không làm gì, báo no_team", r.status_code == 200 and r.json().get("status") == "no_team", r.text)

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    raise SystemExit(1)
print("\nOK")
