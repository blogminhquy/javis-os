"""Personal Zalo: formatted, coloured text and the typing indicator (0.413.0).

    python tests/run.py zalo_formatting      (no network)

Owner, 30/10/2026: with Hermes the bot showed "đang soạn tin" and sent coloured, formatted messages, so customers could
not tell a bot from a person; Javis sent Markdown stars as typed. What is guarded, in order of what would hurt most:

  1. The customer never sees Markdown symbols: bold/italic/strike/colour become Zalo styles, positions in UTF-16 units.
  2. The echo of a formatted reply is still recognised as the bot's own (else the bot thinks the owner typed and goes
     quiet in that chat).
  3. A styled send that cannot run falls back to plain text through the MCP; a timeout is not sent twice.
  4. In a group the "@Name " put in front moves every style.
  5. "Đang soạn tin" is best effort: an MCP without the tool is not asked again, and the reply never waits on it.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zalo-fmt-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import zalo_cli  # noqa: E402
import zalo_markup  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        fails.append(name)


# ============================================================
# 1. Markdown -> Zalo styles
# ============================================================
to = zalo_markup.to_zalo
check("bold spans", to("Dạ chai **500ml** giá **85.000đ** ạ.")
      == ("Dạ chai 500ml giá 85.000đ ạ.", [(8, 5, "bold"), (18, 7, "bold")]))
check("colour and nesting", to("**{red:Giảm 50%}** hôm nay")
      == ("Giảm 50% hôm nay", [(0, 8, "bold"), (0, 8, "red")]))
check("italic, strike, underscore italic", to("~~120k~~ còn *99k* _thôi_")
      == ("120k còn 99k thôi", [(0, 4, "strikethrough"), (9, 3, "italic"), (13, 4, "italic")]))
check("emoji counts two UTF-16 units", to("😀 **đậm**") == ("😀 đậm", [(3, 3, "bold")]))
check("heading becomes a bold line, bullet becomes •", to("### Bảng giá\n- Gói A\n- Gói B")
      == ("Bảng giá\n• Gói A\n• Gói B", [(0, 8, "bold")]))
check("link and code lose their symbols", to("[Đặt hàng](https://x.vn/a) mã `KM10`")
      == ("Đặt hàng (https://x.vn/a) mã KM10", []))
check("maths and snake_case stay as written", to("2 * 3 * 4 = 24, file_name_here")
      == ("2 * 3 * 4 = 24, file_name_here", []))
check("a pair cut in half loses its stray stars", to("giá **85.000đ") == ("giá 85.000đ", []))
check("stray stars before a style move it back", to("** đầu, **đậm**") == (" đầu, đậm", [(6, 3, "bold")]),
      to("** đầu, **đậm**"))
check("plain text is untouched", to("Dạ em chào anh ạ") == ("Dạ em chào anh ạ", []))
check("only names javis-zalo knows", all(n in zalo_markup.STYLE_NAMES for _a, _n, n in to("{big:A} {small:B} {orange:C} {yellow:D}")[1]))

# ============================================================
# 2. Sending
# ============================================================
CID = "zalo-1"
CONN = {"id": CID, "label": "Javis Vũ", "connector_id": "zalo", "env": {"HOME": "/state/zalo-1"}}
MCP, CLI, TYPING = [], [], []
NEXT = {"cli": (True, {"message": {"msgId": "1"}}, ""), "typing": "ok"}


async def fake_goi(conn, tool, args):
    if tool == "zalo_send_message":
        MCP.append(dict(args))
        return {"success": True, "messageId": "m1"}
    if tool == "zalo_send_typing":
        TYPING.append(dict(args))
        if NEXT["typing"] == "missing":
            raise RuntimeError("Tool zalo_send_typing not found")
        return {"success": True}
    return {}


async def fake_run_cli(conn, command, positionals=None, options=None, timeout=120):
    CLI.append({"command": list(command), "pos": list(positionals or []), "opts": list(options or [])})
    return NEXT["cli"]


zc.ket_noi_theo_id = lambda cid: dict(CONN) if cid == CID else None
zc._ket_noi = lambda: [dict(CONN)]
zc._goi = fake_goi
zalo_cli.run_cli = fake_run_cli
zalo_cli.home_of = lambda conn: "/state/zalo-1"


def reset(cli=(True, {"message": {"msgId": "1"}}, "")):
    MCP.clear()
    CLI.clear()
    NEXT["cli"] = cli
    zp._TAG_STATE.clear()
    zc._DA_GUI.clear()


reset()
ok, err = asyncio.run(zp.gui({"id": CID}, "u1", "Dạ chai **500ml** giá {red:85.000đ} ạ."))
check("styled reply goes through `msg send --style`", ok and not MCP and len(CLI) == 1
      and CLI[0]["command"] == ["msg", "send"] and CLI[0]["pos"] == ["u1", "Dạ chai 500ml giá 85.000đ ạ."]
      and CLI[0]["opts"] == ["-t", "0", "--style", "8:5:bold", "18:7:red"], (ok, err, CLI, MCP))

reset()
asyncio.run(zp.gui({"id": CID}, "u1", "Dạ em chào anh ạ"))
check("plain reply still goes through the MCP, as before", not CLI and MCP and MCP[0]["text"] == "Dạ em chào anh ạ")

reset(cli=(False, None, "✗ boom"))
ok, err = asyncio.run(zp.gui({"id": CID}, "u1", "Giá **85.000đ** ạ"))
check("CLI error: plain text still reaches the customer through the MCP, without stars",
      ok and len(CLI) == 1 and MCP and MCP[0]["text"] == "Giá 85.000đ ạ", (ok, err, MCP))

reset(cli=(False, None, f"40 {zalo_cli.TIMEOUT_MARK}"))
ok, err = asyncio.run(zp.gui({"id": CID}, "u1", "Giá **85.000đ** ạ"))
check("CLI timeout: reported, not sent a second time", not ok and not MCP and err, (ok, err, MCP))

reset(cli=(False, None, "✗ boom"))
for _ in range(zp.TAG_FAIL_LIMIT):
    asyncio.run(zp.gui({"id": CID}, "u1", "Giá **85.000đ** ạ"))
n = len(CLI)
asyncio.run(zp.gui({"id": CID}, "u1", "Giá **85.000đ** ạ"))
check("repeated CLI failures pause the styled path, replies keep going", len(CLI) == n and len(MCP) == n + 1, (len(CLI), len(MCP)))

# Echo: Transport._gui remembers the raw reply; Zalo sends back the plain text.
reset()
zc.ghi_da_gui(CID, "u9", "Dạ chai **500ml** giá **85.000đ** ạ.")
check("CANARY: the plain echo of a formatted reply is the bot's own",
      zc._la_tieng_vong(CID, "u9", "Dạ chai 500ml giá 85.000đ ạ."))

# Group: "@Lan " goes in front, the styles move with it.
reset()
zc._ID_MINH.pop(CID, None)
asyncio.run(zp.gui({"id": CID}, "g1", "Giá **85.000đ** ạ", "group", {"uid": "123456", "name": "Lan"}))
opts = CLI[0]["opts"] if CLI else []
check("group: tag and styles in one send, style moved past '@Lan '",
      len(CLI) == 1 and CLI[0]["pos"] == ["g1", "@Lan Giá 85.000đ ạ"] and "--mention" in opts
      and opts[opts.index("--style") + 1:] == ["9:7:bold"], CLI)

# ============================================================
# 3. Typing indicator
# ============================================================
zp.TYPING_DELAY = 0
zp.TYPING_EVERY = 0.01
zp._TYPING_OFF_UNTIL.clear()
TYPING.clear()


async def run_typing(seconds):
    t = asyncio.create_task(zp.keep_typing(CID, "u1", "private"))
    await asyncio.sleep(seconds)
    t.cancel()
    try:
        await t
    except asyncio.CancelledError:
        pass

asyncio.run(run_typing(0.05))
check("typing is repeated while the reply is written", len(TYPING) >= 2
      and TYPING[0] == {"threadId": "u1", "threadType": 0}, TYPING)

NEXT["typing"] = "missing"
TYPING.clear()
asyncio.run(run_typing(0.05))
check("an MCP without the tool is asked once, then left alone", len(TYPING) == 1, TYPING)
TYPING.clear()
check("and not asked again for a while", asyncio.run(zp.send_typing(CID, "u1")) is False and not TYPING
      and zp._TYPING_OFF_UNTIL[CID] > time.time() + 60)

# ============================================================
# 4. The bot is told what Zalo can show
# ============================================================
check("personal-Zalo bot prompt mentions bold and colours",
      "**đậm**" in chatbot_runtime._CAU_ZALO_CA_NHAN and "{red:...}" in chatbot_runtime._CAU_ZALO_CA_NHAN)

print()
if fails:
    print(f"{len(fails)} FAIL: " + ", ".join(fails))
    sys.exit(1)
print("ALL PASS")
