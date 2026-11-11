"""T0 nhóm chat team: bật, tắt, xác nhận Cộng hưởng phát gói `resonance_agents` qua WebSocket để tab khác tải lại.

    python tests/run.py team_t0_broadcast

Không gọi model. Lỗi (404) không phát gói; gói phụ lỗi không làm hỏng lệnh của chủ dự án.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-t0-")
BR = Path(tempfile.mkdtemp(prefix="javis-t0-brain-"))
(BR / "agents").mkdir()
(BR / "agents" / "viet-bai.md").write_text("---\nname: Viết bài\n---\nBạn viết bài.\n", encoding="utf-8", newline="\n")

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


sent = []


async def fake_publish(ev):
    sent.append(ev)


main._CHAT_RUNTIME.publish = fake_publish
c = TestClient(main.app, base_url="http://127.0.0.1:8080")
r = c.post(f"/resonance/agents/toggle?brain={BR}", json={"slug": "viet-bai", "enabled": True})
check("bật: 200", r.status_code == 200 and r.json().get("ok"), r.text)
check("bật: phát đúng một gói resonance_agents", [e.get("type") for e in sent] == ["resonance_agents"], str(sent))
sent.clear()
r = c.post(f"/resonance/agents/toggle?brain={BR}", json={"slug": "khong-co", "enabled": True})
check("lỗi 404: không phát gói nào", r.status_code == 404 and sent == [], f"{r.status_code} {sent}")
r = c.post(f"/resonance/agents/toggle?brain={BR}", json={"slug": "viet-bai", "enabled": False})
check("tắt: phát gói", r.status_code == 200 and [e.get("type") for e in sent] == ["resonance_agents"], str(sent))
sent.clear()


# Xác nhận trợ lý `missing` cũng phát gói: file mất (host đánh dấu missing khi đọc), có lại, chủ bấm "Đúng trợ lý cũ".
# 2026-11-11: Auto is turned back on first. With Auto off and no open goal the host restores the assistant by itself
# when the file is back (nothing to decide), so there would be nothing left to confirm.
c.post(f"/resonance/agents/toggle?brain={BR}", json={"slug": "viet-bai", "enabled": True})
f = BR / "agents" / "viet-bai.md"
tmp = BR / "viet-bai.tmp"
f.rename(tmp)
c.get(f"/resonance/agents?brain={BR}")
tmp.rename(f)
key = next(a for a in c.get(f"/resonance/agents?brain={BR}").json()["agents"] if a["slug"] == "viet-bai")["agent_key"]
sent.clear()
r = c.post(f"/resonance/agents/confirm?brain={BR}", json={"agent_key": key, "same": True})
check("xác nhận trợ lý missing: 200 và phát gói", r.status_code == 200
      and [e.get("type") for e in sent] == ["resonance_agents"], f"{r.status_code} {r.text} {sent}")
sent.clear()


async def broken_publish(ev):
    raise RuntimeError("socket chết")

main._CHAT_RUNTIME.publish = broken_publish
r = c.post(f"/resonance/agents/toggle?brain={BR}", json={"slug": "viet-bai", "enabled": True})
check("gói phụ lỗi: lệnh của chủ vẫn thành công", r.status_code == 200 and r.json().get("ok"), r.text)
raise SystemExit(1 if fails else 0)
