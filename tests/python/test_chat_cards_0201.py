"""0.201.0: JAVIS_CARD blocks degrade to plain text on Telegram and the other text channels.

Run:
    python tests/run.py chat_cards
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json

import channel_context  # noqa: E402
import chat_cards  # noqa: E402
import chat_recall  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


chart = {"type": "chart", "title": "Doanh thu", "labels": ["T2", "T3"],
         "series": [{"name": "Tuần này", "data": [1200000, 900000]}, {"name": "Tuần trước", "data": [1000000, 950000]}]}
t = chat_cards.card_to_text(json.dumps(chart))
check("chart becomes one line per label", "- T2: Tuần này 1.200.000 / Tuần trước 1.000.000" in t and t.startswith("**Doanh thu**"))
t = chat_cards.card_to_text(json.dumps({"type": "stats", "items": [{"label": "Đơn", "value": "128", "delta": "+12%"}]}))
check("stats become label: value (delta)", "- Đơn: **128** (+12%)" in t)
t = chat_cards.card_to_text(json.dumps({"type": "buttons", "title": "Duyệt?", "buttons": [{"label": "Duyệt"}, {"label": "Sửa"}]}))
check("buttons become a numbered list", "1. Duyệt" in t and "2. Sửa" in t)
check("broken or unknown card is empty", chat_cards.card_to_text("{bad") == "" and
      chat_cards.card_to_text(json.dumps({"type": "html", "x": 1})) == "")
msg = "Tuần này tốt.\n<!-- JAVIS_CARD: " + json.dumps(chart, ensure_ascii=False) + " -->\nHết."
out = channel_context.strip_control_blocks(msg)
check("strip turns the card into text", "JAVIS_CARD" not in out and "- T3:" in out and "Hết." in out)
check("prompt for the web chat explains cards", "JAVIS_CARD" in channel_context.build_channel_block("dashboard", {}))
check("telegram prompt does not", "JAVIS_CARD" not in channel_context.build_channel_block("telegram", {"chat_id": "1"}))
blk = chat_recall.block([{"title": "Cũ", "snippet": "landing page nước mắm Phan Thiết màu cam"}])
check("recall block stripped before titles and logs", chat_recall.strip_block(blk + "câu thật") == "câu thật")
check("plain message untouched by strip", chat_recall.strip_block("[SKILL: x]\n\nhỏi") == "[SKILL: x]\n\nhỏi")

src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("recall wired in front of the engine message", "chat_recall.block(_hits) + user_message" in src)
check("persist strips the recall block", "user_message = chat_recall.strip_block(user_message)" in src)

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
