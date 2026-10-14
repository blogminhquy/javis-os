"""Tiến trình MCP stdio sống sót qua một lần server khởi động lại thì bị dọn (0.110.0).

    python tests/run.py mcp_mo_coi      (KHÔNG mạng; spawn vài tiến trình python ngủ)

Báo cáo 13/10/2026, bot "Javis Vũ": bot im trong nhóm Zalo từ 21:09. Tài khoản có HAI tiến trình
`javis-zalo mcp start`, một từ 20:49 và một do server mở lại lúc 21:10. Zalo chỉ đẩy tin về một
socket, bot đọc phiên mới, phiên mới gần như không nhận được gì.

Điều được ghim:
  1. Mỗi tiến trình stdio có key được ghi sổ; đóng đúng cách thì xoá khỏi sổ.
  2. Đời server sau dọn tiến trình đời trước để lại, khi server chủ đã chết.
  3. KHÔNG dọn khi server chủ còn sống (server khác hoặc lượt test dùng chung STATE_DIR).
  4. KHÔNG giết một pid đã bị hệ điều hành cấp cho chương trình khác (dòng lệnh không khớp).
  5. Phiên bị đóng ĐÚNG LÚC tiến trình đang được tạo thì tiến trình đó cũng chết, không mồ côi.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-mocoi-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import mcp_client  # noqa: E402
import mcp_orphans  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


async def _cho_chet_con(proc, giay=10.0):
    """Our own child: wait through asyncio, which also collects it (no zombie left behind)."""
    try:
        await asyncio.wait_for(proc.wait(), giay)
        return True
    except Exception:
        return not mcp_orphans.pid_alive(proc.pid)


def _pid_da_chet():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


NGU = "import time; time.sleep(600)  # javis-mcp-mo-coi-{}"


async def _mo(key, tag):
    s = mcp_client.McpStdioSession(sys.executable, ["-c", NGU.format(tag)], key=key)
    await s.start()
    return s


async def chay():
    # ---- 1. ghi sổ và xoá khi đóng đúng cách ----------------------------------------
    s1 = await _mo("zalo-a", "a")
    so = mcp_orphans._load()
    check("tiến trình stdio có key được ghi sổ", so.get("zalo-a", {}).get("pid") == s1.proc.pid, so)
    await s1.close()
    check("đóng đúng cách thì xoá khỏi sổ", "zalo-a" not in mcp_orphans._load(), mcp_orphans._load())

    # ---- 2. server chủ đã chết: đời sau dọn -------------------------------------------
    s2 = await _mo("zalo-b", "b")
    so = mcp_orphans._load()
    so["zalo-b"].update(owner="doi-truoc", server_pid=_pid_da_chet())     # như sau một lần crash
    mcp_orphans._save(so)
    mcp_orphans._reset_for_tests()
    da_don = await asyncio.to_thread(mcp_orphans.reap_all)
    check("CANARY: tiến trình đời trước để lại bị dọn", da_don == ["zalo-b"] and await _cho_chet_con(s2.proc), da_don)
    check("và rời khỏi sổ", "zalo-b" not in mcp_orphans._load())

    # ---- 3. server chủ CÒN SỐNG: không đụng -------------------------------------------
    s3 = await _mo("zalo-c", "c")
    pid3 = s3.proc.pid
    song = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    so = mcp_orphans._load()
    so["zalo-c"].update(owner="server-khac", server_pid=song.pid)
    mcp_orphans._save(so)
    mcp_orphans._reset_for_tests()
    da_don = await asyncio.to_thread(mcp_orphans.reap_all)
    check("server chủ còn sống thì không dọn", da_don == [] and mcp_orphans.pid_alive(pid3), da_don)
    check("và vẫn giữ trong sổ", "zalo-c" in mcp_orphans._load())
    song.kill()
    await s3.close()

    # ---- 4. pid bị cấp lại cho chương trình khác: không giết -----------------------------
    la = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)  # chuong-trinh-khac"])
    so = mcp_orphans._load()
    so["zalo-d"] = {"pid": la.pid, "args": ["-c", NGU.format("d")], "server_pid": _pid_da_chet(),
                    "owner": "doi-truoc", "ts": time.time()}
    mcp_orphans._save(so)
    mcp_orphans._reset_for_tests()
    da_don = await asyncio.to_thread(mcp_orphans.reap_all)
    check("CANARY: pid giờ chạy lệnh khác thì KHÔNG bị giết", da_don == [] and mcp_orphans.pid_alive(la.pid),
          da_don)
    la.kill()

    # ---- 5. đóng đúng lúc tiến trình đang được tạo ------------------------------------
    s5 = mcp_client.McpStdioSession(sys.executable, ["-c", NGU.format("e")], key="zalo-e")
    goc = asyncio.create_subprocess_exec
    sinh = []

    async def _tao_cham(*a, **k):
        p = await goc(*a, **k)
        sinh.append(p)
        await s5.close()          # pool vứt phiên đúng lúc này (invalidate) - close chưa thấy tiến trình
        return p

    asyncio.create_subprocess_exec = _tao_cham
    try:
        try:
            await s5.start()
            loi = ""
        except ConnectionError as e:
            loi = str(e)
    finally:
        asyncio.create_subprocess_exec = goc
    check("phiên đóng giữa lúc tạo tiến trình thì báo lỗi", bool(loi), loi)
    check("CANARY: và tiến trình vừa tạo cũng chết, không thành mồ côi",
          sinh and await _cho_chet_con(sinh[0]), sinh)
    check("không ghi sổ một tiến trình đã giết", "zalo-e" not in mcp_orphans._load(), mcp_orphans._load())


asyncio.run(chay())

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
