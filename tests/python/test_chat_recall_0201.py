"""0.201.0: recall puts a few lines from the owner's other chats in front of a turn.

Run:
    python tests/run.py chat_recall
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-recall-")

import chat_recall as cr  # noqa: E402
import sessions  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


store = sessions.SessionStore(Path(tempfile.mkdtemp()) / "s.sqlite3")
old = store.create_session(brain="shop", channel="web", title="Landing nước mắm")
store.append_message(old, "user", "Làm landing page nước mắm Phan Thiết, màu cam, nút đặt hàng Zalo")
store.append_message(old, "assistant", "Đã dựng landing page nước mắm Phan Thiết với nút đặt hàng qua Zalo.")
team = store.create_session(brain="shop", channel="team:abc", title="Team")
store.append_message(team, "user", "Landing page nước mắm Phan Thiết bản team bí mật")
bot = store.create_session(brain="shop", channel="chatbot:xyz", title="Khách")
store.append_message(bot, "user", "Khách hỏi landing page nước mắm Phan Thiết giá bao nhiêu")
other_brain = store.create_session(brain="khac", channel="web", title="Khác")
store.append_message(other_brain, "user", "landing page nước mắm Phan Thiết ở brain khác")
cur = store.create_session(brain="shop", channel="web", title="Mới")

hits = cr.recall(store, "làm tiếp landing page nước mắm hôm trước nhé", brain="shop", current_sid=cur)
check("finds the earlier owner chat", len(hits) == 1 and hits[0]["session_id"] == old)
check("team and chatbot chats never feed recall", all(h["session_id"] not in (team, bot) for h in hits))
check("other brain not searched", all(h["session_id"] != other_brain for h in hits))
check("current chat excluded", not cr.recall(store, "landing page nước mắm Phan Thiết", brain="shop", current_sid=old)
      or all(h["session_id"] != old for h in cr.recall(store, "landing page nước mắm Phan Thiết", brain="shop",
                                                       current_sid=old)))
check("short message gets nothing", cr.recall(store, "ok nhé", brain="shop", current_sid=cur) == [])
b = cr.block(hits)
check("block fenced and labelled as data", b.startswith("[" + cr.BLOCK_TITLE) and "dữ liệu" in b and b.endswith("]\n\n"))
check("excerpt markers removed", ">>>" not in b and "<<<" not in b)
check("empty hits give no block", cr.block([]) == "")
check("terms drop stop words and fold marks", "nuoc" in cr.terms("Làm giúp nước mắm") and "giup" not in cr.terms("Làm giúp nước mắm"))
check("owner channels only", cr.allowed_channel("") and cr.allowed_channel("agent:lan") and
      not cr.allowed_channel("team:1") and not cr.allowed_channel("chatbot:1") and not cr.allowed_channel("zalo:1"))


class Broken:
    def search(self, *a, **k):
        raise RuntimeError("db locked")


check("a search error never breaks the turn", cr.recall(Broken(), "landing page nước mắm Phan Thiết", brain="shop") == [])

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
