"""A full-access dedicated bot never shows technical text to customers, and never rewrites the owner's model (0.102.1).

    python tests/run.py bot_toan_quyen_khong_lo      (NO network)

A bot at "Toàn quyền" runs the owner's own engine path (0.85.3). Two pieces of that path were written for the OWNER:
  1. `_tg_ket` glued "⚠ Có lỗi giữa lượt: ..." and the Codex model warning onto the reply. Fine for the owner on
     Telegram, wrong in a customer group. For a bot they now go to `canh_bao`, which the bot log shows the owner.
  2. When the model was not in the Codex catalog, the turn "self-healed" by writing the owner's MAIN model. For a bot
     that model is the Agent's, so a customer bot changed the owner's own brain.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-toanquyen-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{str(detail)[:300]}]"))
    if not cond:
        _fails.append(name)


# ---- 1. _tg_ket ----
chu = main._tg_ket("Dạ còn hàng ạ", ["a.jpg"], "⚠ Model 'x' đã tự đổi.\n\n", ["hub sập"])
check("owner channel unchanged: warning on top, mid-turn error at the bottom",
      chu["text"].startswith("⚠ Model") and chu["text"].endswith("⚠ Có lỗi giữa lượt: hub sập") and "canh_bao" not in chu, chu)
khach = main._tg_ket("Dạ còn hàng ạ", ["a.jpg"], "⚠ Model 'x' đã tự đổi.\n\n", ["hub sập"], khach=True)
check("customer bot: the reply is only the answer", khach["text"] == "Dạ còn hàng ạ" and khach["files"] == ["a.jpg"], khach)
check("customer bot: warning and error go to canh_bao for the bot log",
      "Model 'x'" in khach.get("canh_bao", "") and "hub sập" in khach.get("canh_bao", ""), khach)
check("customer bot, clean turn: no canh_bao at all", "canh_bao" not in main._tg_ket("Dạ", [], "", [], khach=True))

# ---- 2. wiring in the engine core ----
src = (SERVER / "main.py").read_text(encoding="utf-8")
core = src[src.index("async def _tg_answer_engine("):src.index("async def _tg_help_text(")]
check("every reply of the engine core marks a full-access bot as a customer turn",
      core.count("_tg_ket(") == 3 and core.count("khach=_bot_full)") == 3, core.count("khach=_bot_full)"))
i = core.index('_set_main_model(_fix, "openai-oauth", actual_model)')
check("the Codex model self-heal never writes the owner's main model for a bot (nor an agent turn)",
      "if not _bot_full and not agent:" in core[i - 400:i], core[i - 400:i])
# 0.270.0: the dashboard WebSocket path had the same overwrite. A session with a pinned model (an agent chat pins its
# agent's model) fixes only its pin; the owner's main model is rewritten only when the stale model came from it.
ws = src[src.index("async def websocket_endpoint("):]
j = ws.index('_set_main_model(_fix, "openai-oauth", actual_model)')
check("dashboard Codex self-heal: a pinned session fixes its pin, not the owner's main model",
      'store.set_pinned_model(conv_sid, "openai-oauth", actual_model)' in ws[j - 900:j]
      and "else:" in ws[j - 200:j], ws[j - 900:j])
check("chatbot_runtime puts canh_bao in the bot log",
      '(out or {}).get("canh_bao")' in (SERVER / "chatbot_runtime.py").read_text(encoding="utf-8"))

# main.py keeps one em dash on purpose (a regex that parses memory lines), so it is not checked here.
for f in (SERVER / "chatbot_runtime.py", __import__("pathlib").Path(__file__)):
    check(f"no em dash in {f.name}", chr(0x2014) not in f.read_text(encoding="utf-8"))

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
