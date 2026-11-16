"""An image a connection tool returns is saved in the brain and shown in the chat, not dumped as base64.

    python tests/run.py tool_images

Owner's report (2026-11-16): "khi chat mà có playwrite chụp ảnh màn hình anh không thấy ảnh hiển ở khung chat,
anh rất cần để xem trước nữa". Playwright's browser_take_screenshot answers with an MCP `image` content block.
mcp_client._format_result turned every non-text block into json.dumps(block), so the model got a few hundred KB
of base64 it could not see, and the chat showed nothing.

This file pins the fix:
  1. inside a model's tool call with a known brain, the image is written under <attachments>/tool-images/ and the
     block becomes one line with the relative path and the ![...](path) to put in the reply;
  2. with no brain, an unknown image type or broken data, the block stays exactly as before;
  3. through the hub: a model's call (CLI engines over /hub/mcp, API engines through engine.py) saves the image
     in that call's brain, an internal caller still gets the tool's own text.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import base64
import json
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-tool-images-"))

import config  # noqa: E402
import mcp_catalog  # noqa: E402
import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402
import mcp_store  # noqa: E402
import tool_images  # noqa: E402
import tool_result_shaper as shaper  # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


# The smallest valid PNG (1x1), as Playwright would send a screenshot.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
PNG_B64 = base64.b64encode(PNG).decode()


def screenshot_response(data=PNG_B64, mime="image/png"):
    return {"jsonrpc": "2.0", "id": 3, "result": {"content": [
        {"type": "text", "text": "### Result\nTook the viewport screenshot."},
        {"type": "image", "data": data, "mimeType": mime},
    ]}}


def saved_files(vault):
    out = []
    for base, _dirs, files in os.walk(vault):
        out += [os.path.join(base, f) for f in files]
    return out


# ============================================================
# 1. A model's call with a brain: saved, replaced by a short note
# ============================================================
brain = tempfile.mkdtemp(prefix="brain-shot-")
with tool_images.saving_to(brain, "browser_take_screenshot"):
    text = mcp_client._format_result(screenshot_response())
files = saved_files(brain)
check("the screenshot is written once into the brain", len(files) == 1, files)
rel = os.path.relpath(files[0], brain).replace(os.sep, "/") if files else ""
check("it lands in attachments/tool-images/", rel.startswith("attachments/tool-images/") and rel.endswith(".png"), rel)
check("the file holds the exact image bytes", bool(files) and open(files[0], "rb").read() == PNG)
check("no base64 reaches the model", PNG_B64 not in text and '"data"' not in text, text[:200])
check("the tool's own text is kept", "Took the viewport screenshot." in text, text)
check("the note gives the markdown that shows it in the chat", f"![screenshot]({rel})" in text, text)
check("the file name says which tool made it", os.path.basename(rel).startswith("browser_take_screenshot-"), rel)

# A brain whose attachments folder has another name ("05 - Attachments") keeps one attachments folder.
brain2 = tempfile.mkdtemp(prefix="brain-shot2-")
os.makedirs(os.path.join(brain2, "05 - Attachments"))
with tool_images.saving_to(brain2, "browser_take_screenshot"):
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 16 + b"\xff\xd9"
    text2 = mcp_client._format_result(screenshot_response(data=base64.b64encode(jpeg).decode(), mime="image/jpeg"))
files2 = saved_files(brain2)
rel2 = os.path.relpath(files2[0], brain2).replace(os.sep, "/") if files2 else ""
check("an existing attachments folder is reused", rel2.startswith("05 - Attachments/tool-images/"), rel2)
check("a JPEG keeps a .jpg name", rel2.endswith(".jpg"), rel2)
check("the note points at that folder", f"]({rel2})" in text2, text2)

# The bytes decide the extension, not the declared type: PNG bytes sent as image/jpeg are saved as .png.
brain3 = tempfile.mkdtemp(prefix="brain-shot4-")
with tool_images.saving_to(brain3, "chart"):
    text3 = mcp_client._format_result(screenshot_response(mime="image/jpeg"))
files3 = saved_files(brain3)
check("PNG bytes declared as JPEG are saved as .png", len(files3) == 1 and files3[0].endswith(".png"), files3)
check("a tool that is not a screenshot gets a plain image label", "![image](attachments/tool-images/chart-" in text3,
      text3)

# ============================================================
# 2. Nothing changes where there is nowhere to show it, or nothing safe to save
# ============================================================
old = json.dumps(screenshot_response()["result"]["content"][1], ensure_ascii=False)
text = mcp_client._format_result(screenshot_response())
check("no brain in scope: the block stays as before", old in text, text[:120])

empty = tempfile.mkdtemp(prefix="brain-shot3-")
with tool_images.saving_to(empty, "t"):
    t_bad = mcp_client._format_result(screenshot_response(data="!!not base64!!"))
    svg = base64.b64encode(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>').decode()
    t_svg = mcp_client._format_result(screenshot_response(data=svg, mime="image/svg+xml"))
    t_err = mcp_client._format_result({"result": {"isError": True, "content": [
        {"type": "text", "text": "boom"}, {"type": "image", "data": PNG_B64, "mimeType": "image/png"}]}})
check("broken base64 is left as it was", "!!not base64!!" in t_bad, t_bad[:120])
check("an SVG (can carry script) is not written into the brain", "image/svg+xml" in t_svg, t_svg[:120])
check("an error result still reads as an error", t_err.startswith("ERROR: boom"), t_err[:80])
check("only the one valid image above was written", len(saved_files(empty)) == 1, saved_files(empty))

with tool_images.saving_to(os.path.join(empty, "missing-brain"), "t"):
    t_gone = mcp_client._format_result(screenshot_response())
check("a brain folder that does not exist is not created", not os.path.exists(os.path.join(empty, "missing-brain"))
      and old in t_gone)

check("the scope ends with the block", tool_images.current() == ("", ""))

# ============================================================
# 3. Through the hub: a model's call saves into that call's brain, an internal caller is untouched
# ============================================================


class _Pool:
    async def call_tool(self, spec, tool, arguments):
        # The real sessions call _format_result inside call_tool; do the same so the scope must reach this far.
        return mcp_client._format_result(screenshot_response())


CONN = {"id": "pw1", "connector_id": "custom-test-browser", "label": "Browser", "slug": "browser",
        "namespace": "browser", "perm": "full", "deny_tools": []}


async def _fake_discover(conns, bo_qua=None):
    spec = {"transport": "stdio", "command": "npx", "args": []}
    fn = "browser__browser_take_screenshot"
    route = {fn: {"spec": spec, "tool": "browser_take_screenshot", "conn": dict(CONN)}}
    tools = [{"fn": fn, "server": "browser", "name": "browser_take_screenshot", "description": "screenshot",
              "schema": {"type": "object", "properties": {}}, "conn_id": "pw1",
              "connector_id": CONN["connector_id"], "namespace": "browser", "label": "Browser"}]
    return tools, route


_real_get = mcp_catalog.get
BROWSER = {"id": "custom-test-browser", "name": "Browser", "tool_meta": {"read": ["browser_take_*"], "write": []}}
mcp_catalog.get = lambda cid: BROWSER if cid == "custom-test-browser" else _real_get(cid)
mcp_store.resolved = lambda enabled_only=True: [dict(CONN, transport="stdio", command="npx", args=[], env={})]
mcp_client.discover_resolved = _fake_discover
mcp_client.pool = _Pool()
mcp_hub._builtin_tools = lambda *a, **k: ([], {})
config.read_settings = lambda: {"mcp": {"lazy_tools": "off"}}
shaper.settings(force=True)
mcp_hub._cache.clear()

hub_brain = tempfile.mkdtemp(prefix="brain-hub-")
_tools, route = asyncio.run(mcp_hub.discover_all("full", vault_root=hub_brain, include_plugins=False,
                                                 force_refresh=True))
FN = "browser__browser_take_screenshot"
check("the test tool is routed", FN in route, sorted(route))


async def _model_call():
    with shaper.for_model():
        return await mcp_client.call_route(route, FN, {})

model_text = asyncio.run(_model_call())
hub_files = saved_files(hub_brain)
check("a model's call saves the screenshot in its brain", len(hub_files) == 1, hub_files)
check("the model reads the note, not base64", "![screenshot](attachments/tool-images/" in model_text
      and PNG_B64 not in model_text, model_text[:200])

internal = asyncio.run(mcp_client.call_route(route, FN, {}))
check("an internal caller gets the tool's own text", PNG_B64 in internal, internal[:120])
check("an internal call writes nothing", len(saved_files(hub_brain)) == 1)

if _fails:
    raise SystemExit(f"{len(_fails)} FAIL: " + "; ".join(_fails))
print("All green")
