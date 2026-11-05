"""Việc nền chạy bằng API key có terminal thật, đúng ở chỗ Claude Code cũng có (05/11/2026).

    python tests/run.py viec_nen_terminal

Chủ repo: "làm tiếp phần terminal cho việc nền". Trước bản này việc nền bằng API key không có
lệnh máy nên không dựng nổi video (ffmpeg) dù đã hết trần 30 vòng. Bảng phải giữ:

    Claude của việc này được chạy Bash, mức full   -> API key có javis_terminal
    mức auto / suggest                             -> không terminal
    loop bị cô lập (disallowed Bash)               -> không terminal
    task bị rào bằng allowlist không có Bash       -> không terminal
    lượt no_tools (đầu vào không tin cậy)          -> không tool nào

Cộng: lệnh chạy thật trong brain, câu khai năng lực nói đúng, và hết lượt thì cache hub của
phiên được dọn (mỗi lượt một mã phiên, không dọn là RAM phình theo số lượt loop).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix="javis-nenterm-")
os.environ["JAVIS_STATE_DIR"] = _TMP
BRAIN = Path(tempfile.mkdtemp(prefix="javis-nenterm-brain-"))

import aux_engine  # noqa: E402
import engine  # noqa: E402
import mcp_hub  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("  ok  " if cond else "  FAIL ") + name + (f"  ({extra})" if extra and not cond else ""))
    if not cond:
        _fails.append(name)


def cli(allowed=None, disallowed=None, mode="full"):
    return SimpleNamespace(allowed_tools=allowed, disallowed_tools=disallowed, javis_mode=mode,
                           javis_vault=str(BRAIN), system_prompt="", tag="dispatch:t1:run")


# ---- 1. Quyết định thừa hưởng từ engine Claude ----
check("Claude không rào gì: được Bash", aux_engine.cli_cho_bash(cli()))
check("loop bị cô lập (chặn Bash): không", not aux_engine.cli_cho_bash(cli(disallowed=["Bash", "WebFetch"])))
check("allowlist không có Bash: không", not aux_engine.cli_cho_bash(cli(allowed=["Read", "Write"])))
check("allowlist có Bash (task năng lực code): được", aux_engine.cli_cho_bash(cli(allowed=["Read", "Bash"])))

SPEC = {"provider": "openai", "model": "gpt-x"}
check("mức full + Claude được Bash: engine API có terminal",
      aux_engine._build_api(SPEC, cli(), "full", "t").terminal)
check("mức auto: không terminal", not aux_engine._build_api(SPEC, cli(mode="auto"), "auto", "t").terminal)
check("mức suggest: không terminal", not aux_engine._build_api(SPEC, cli(mode="suggest"), "suggest", "t").terminal)
check("full nhưng loop bị cô lập: không terminal",
      not aux_engine._build_api(SPEC, cli(disallowed=["Bash"]), "full", "t").terminal)
check("rào chót trong engine: terminal=True mà mode auto vẫn không",
      not aux_engine._ApiAuxEngine("openai", "m", mode="auto", terminal=True).terminal)
_src = (ROOT / "server" / "aux_engine.py").read_text(encoding="utf-8")
check("cả hai chỗ dựng engine API đều quyết theo cli_cho_bash", _src.count("cli_cho_bash(") == 3)


# ---- 2. Chạy một lượt thật qua hub (model giả, tool thật) ----
async def _luot(eng, lenh=None):
    import mcp_client
    seen = {}
    goc_fn = engine.openai_chat_with_mcp

    async def _gia(key, model, messages, reasoning, tools, route):
        seen["tools"] = {t.get("fn") for t in tools}
        seen["system"] = messages[0]["content"] if messages and messages[0]["role"] == "system" else ""
        seen["sid"] = {k[-1] for k in mcp_hub._cache if isinstance(k, tuple) and str(k[-1]).startswith("nen-")}
        # Web nằm ở tầng tool tìm-rồi-gọi (lazy) khi brain có nhiều tool: hỏi đúng đường model sẽ đi.
        seen["web"] = ("javis_web_search" in route or "javis_web_search" in str(
            await mcp_client.call_route(route, "javis_search_tools", {"query": "web search"})))
        if lenh and "javis_terminal" in route:
            seen["out"] = await mcp_client.call_route(route, "javis_terminal", {"command": lenh})
        yield {"type": "text", "content": "xong"}

    engine.openai_chat_with_mcp = _gia
    try:
        out = [ev async for ev in eng.query("dựng video")]
    finally:
        engine.openai_chat_with_mcp = goc_fn
    seen["final"] = next((e.get("content") for e in out if e.get("type") == "final"), None)
    return seen


full = aux_engine._ApiAuxEngine("openai", "gpt-x", vault_root=str(BRAIN), mode="full", tag="dispatch:t1:run",
                                api_key="sk-test", terminal=True)
r = asyncio.run(_luot(full, "echo xin-chao > video-thu.txt && pwd"))
check("việc nền Toàn quyền thấy javis_terminal", "javis_terminal" in r["tools"], sorted(r["tools"])[:12])
check("và tìm được web", r["web"])
check("lệnh chạy thật, thư mục làm việc là brain",
      (BRAIN / "video-thu.txt").read_text(encoding="utf-8").strip() == "xin-chao", r.get("out"))
check("câu khai năng lực nói có terminal", "terminal thật" in r["system"] and "KHÔNG có: lệnh máy" not in r["system"])
check("lượt chạy xong vẫn trả final", r["final"] == "xong")
check("trong lượt có cache của phiên nen-...", len(r["sid"]) == 1, r["sid"])
_con = [k for k in mcp_hub._cache if isinstance(k, tuple) and k[-1] in r["sid"]]
check("hết lượt thì cache của phiên được dọn", not _con, _con)

auto = aux_engine._ApiAuxEngine("openai", "gpt-x", vault_root=str(BRAIN), mode="auto", tag="loop",
                                api_key="sk-test", terminal=True)
r2 = asyncio.run(_luot(auto))
check("mức auto: không có javis_terminal", "javis_terminal" not in r2["tools"])
check("mức auto: vẫn tìm được web", r2["web"])
check("mức auto: câu khai năng lực nói không có lệnh máy", "KHÔNG có: lệnh máy" in r2["system"])

kin = aux_engine._ApiAuxEngine("openai", "gpt-x", vault_root=str(BRAIN), mode="full", tag="reply-policy",
                               api_key="sk-test", terminal=True)
kin.no_tools = True
_goc_stream = engine.openai_stream


async def _gia_stream(key, model, messages, reasoning):
    yield {"type": "text", "content": "chỉ chữ"}

engine.openai_stream = _gia_stream
try:
    r3 = asyncio.run(_luot(kin))
finally:
    engine.openai_stream = _goc_stream
check("lượt no_tools không dựng terminal hay tool nào", "tools" not in r3 and r3["final"] == "chỉ chữ")

# ---- 3. Bot của khách không đi đường này ----
msrc = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
_bot = msrc[msrc.find("def _bot_stream_co_tool("):]
_bot = _bot[:_bot.find("\ndef ", 10)]
check("vòng tool của bot không dùng engine việc nền", "_ApiAuxEngine" not in _bot and "terminal" not in _bot)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_viec_nen_terminal: tất cả pass")
