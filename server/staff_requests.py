"""Ask the staff, then tell the customer ("Hỏi nội bộ rồi báo khách", 2026-11-26).

A customer asks a dedicated bot something only a person at the shop knows: a price, the stock, a free slot, a delivery
date. The bot calls the tool `ask_staff(question)`. Javis sends the question, with a short request code, to the bot's
staff contact (`staff_contact` of the bot record: one chat on the SAME channel account the bot runs on), records a
pending request here, and the bot tells the customer it is checking. When the staff member answers in that chat (a reply
to the request message, a message holding the code, or, with exactly one request open, a plain next message), Javis
runs a bot turn in the customer's chat with the answer as context, so the bot phrases it in its own voice, sends it
through the channel's normal transport and writes it to the inbox (`chatbot_runtime.relay_staff_answer`).

What this module holds:
  - the store: a small SQLite file in the state folder (`db_path`), one row per request;
  - the tool (`turn_tool`), offered by the hub to ONE bot turn only, never cached with the shared tool lists;
  - the staff side (`on_staff_message`), called by the bot's precheck for every message before any engine turn.

Permission. Sending a message is an outside action. The tool is offered only where the hub would let an outside action
through: hub mode "full" AND the bot's own level for this chat "full" (a per-chat exception included). A bot at "read
only", "reads documents" or "can write" never sees it, and the call checks the same again (`ask`), so a list cached in a
long-lived engine process cannot widen anything. No `authorize` override of the hub guard exists or is needed.

Channels: personal Zalo and Telegram (`CHANNELS`). Others can be added once their transport can send to a chat by id
and hand the quoted text of a reply to the bot (`reply_to_text` in the message meta).

Expiry: a request still open after `TTL_S` (24 h) is marked "expired". Nothing is sent to anyone on expiry: following
up with the customer is the owner's call. Rows older than `KEEP_S` are deleted.
"""
from __future__ import annotations

import asyncio
import random
import re
import sqlite3
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config as cfgmod
import localefmt

TOOL = "ask_staff"
CHANNELS = ("zalo_personal", "telegram")
TTL_S = 24 * 3600
KEEP_S = 30 * 24 * 3600
QUESTION_MAX = 500
ANSWER_MAX = 2000
OPEN_PER_CHAT_MAX = 3          # a stranger must not flood the staff chat through the bot
OPEN_PER_BOT_MAX = 30
CODE_NOTE_GAP_S = 600          # "which request?" note to the staff chat, at most once per 10 minutes

_LETTERS = "ABCDEFGHJKMNPQRSTUVWXYZ"     # no I, L, O: they read as digits
_DIGITS = "23456789"                       # no 0, 1
# A code is letter-digit-letter-digit ("K7Q2"), with or without "#", case-insensitive. The mixed shape keeps an
# ordinary four-letter word from ever matching.
CODE_RE = re.compile(r"(?<![0-9A-Za-z])#?([A-Za-z][2-9][A-Za-z][2-9])(?![0-9A-Za-z])")

# Text a channel puts in place of a message without words (a bare photo, voice, video or file): not an answer.
_NO_WORDS = ("[Khách gửi một ảnh, không kèm lời nhắn]", "(người dùng gửi file)")

TOOL_DESCRIPTION = ("Ask the shop's staff something only a person knows (a price, stock, a free slot, a delivery "
                    "date). Javis sends your question to the staff and passes their answer into this chat later. "
                    "After calling it, tell the customer briefly that you are checking.")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS staff_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    bot_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    account_id TEXT NOT NULL,
    customer_chat_id TEXT NOT NULL,
    customer_chat_type TEXT NOT NULL DEFAULT 'private',
    customer_user_id TEXT NOT NULL DEFAULT '',
    customer_name TEXT NOT NULL DEFAULT '',
    customer_message_id TEXT NOT NULL DEFAULT '',
    staff_chat_id TEXT NOT NULL,
    staff_chat_type TEXT NOT NULL DEFAULT 'private',
    question TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at REAL NOT NULL,
    answered_at REAL,
    answer TEXT NOT NULL DEFAULT '',
    staff_name TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS staff_requests_staff ON staff_requests(bot_id, account_id, staff_chat_id, status);
CREATE INDEX IF NOT EXISTS staff_requests_customer ON staff_requests(bot_id, customer_chat_id, status);
"""
STATUSES = ("open", "answered", "expired", "failed")

_ready: set = set()
_lock = threading.Lock()
_TASKS: set = set()                       # relay tasks in flight, kept so they are not collected mid-way
_CODE_NOTE_AT: Dict[tuple, float] = {}


# ============================================================
# Store
# ============================================================
def db_path() -> Path:
    return Path(cfgmod.STATE_DIR) / "staff_requests.sqlite3"


@contextmanager
def _conn():
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fresh = str(p) not in _ready or not p.exists()
    con = sqlite3.connect(str(p), timeout=10)
    con.row_factory = sqlite3.Row
    try:
        if fresh:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(_SCHEMA)
            _ready.add(str(p))
        yield con
        con.commit()
    finally:
        con.close()


def _row(r) -> Optional[dict]:
    return dict(r) if r is not None else None


def get(req_id: int) -> Optional[dict]:
    with _conn() as con:
        return _row(con.execute("SELECT * FROM staff_requests WHERE id=?", (int(req_id),)).fetchone())


def expire_due(now: Optional[float] = None) -> int:
    """Mark requests open for longer than `TTL_S` as expired, drop rows older than `KEEP_S`. Returns how many expired.
    Sends nothing: the owner decides whether to follow up with the customer."""
    now = time.time() if now is None else float(now)
    if not db_path().exists():
        return 0
    with _lock, _conn() as con:
        n = con.execute("UPDATE staff_requests SET status='expired' WHERE status='open' AND created_at<?",
                        (now - TTL_S,)).rowcount
        con.execute("DELETE FROM staff_requests WHERE created_at<?", (now - KEEP_S,))
    return int(n or 0)


def open_for_staff(bot_id: str, account_id: str, staff_chat_id: str) -> List[dict]:
    """Requests of this bot still waiting for an answer in this staff chat, oldest first."""
    if not db_path().exists():
        return []
    with _conn() as con:
        rows = con.execute("SELECT * FROM staff_requests WHERE bot_id=? AND account_id=? AND staff_chat_id=? "
                           "AND status='open' ORDER BY id", (str(bot_id), str(account_id), str(staff_chat_id)))
        return [dict(r) for r in rows]


def count_open(bot_id: str, customer_chat_id: Optional[str] = None) -> int:
    if not db_path().exists():
        return 0
    with _conn() as con:
        if customer_chat_id is None:
            r = con.execute("SELECT COUNT(*) FROM staff_requests WHERE bot_id=? AND status='open'", (str(bot_id),))
        else:
            r = con.execute("SELECT COUNT(*) FROM staff_requests WHERE bot_id=? AND customer_chat_id=? "
                            "AND status='open'", (str(bot_id), str(customer_chat_id)))
        return int(r.fetchone()[0])


def _new_code(con, bot_id: str, account_id: str, staff_chat_id: str) -> str:
    taken = {str(r[0]).upper() for r in con.execute(
        "SELECT code FROM staff_requests WHERE bot_id=? AND account_id=? AND staff_chat_id=? AND status='open'",
        (bot_id, account_id, staff_chat_id))}
    rnd = random.SystemRandom()
    for _ in range(200):
        code = rnd.choice(_LETTERS) + rnd.choice(_DIGITS) + rnd.choice(_LETTERS) + rnd.choice(_DIGITS)
        if code not in taken:
            return code
    raise RuntimeError("no free request code")


def create(*, bot_id: str, channel: str, account_id: str, customer_chat_id: str, customer_chat_type: str,
           customer_user_id: str, customer_name: str, customer_message_id: str, staff_chat_id: str,
           staff_chat_type: str, question: str, now: Optional[float] = None) -> dict:
    """Record a new open request with a code no other open request of that staff chat uses. Returns the row."""
    now = time.time() if now is None else float(now)
    with _lock, _conn() as con:
        code = _new_code(con, str(bot_id), str(account_id), str(staff_chat_id))
        cur = con.execute(
            "INSERT INTO staff_requests (code, bot_id, channel, account_id, customer_chat_id, customer_chat_type, "
            "customer_user_id, customer_name, customer_message_id, staff_chat_id, staff_chat_type, question, status, "
            "created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'open',?)",
            (code, str(bot_id), str(channel), str(account_id), str(customer_chat_id),
             "group" if customer_chat_type == "group" else "private", str(customer_user_id or ""),
             str(customer_name or "")[:80], str(customer_message_id or ""), str(staff_chat_id),
             "group" if staff_chat_type == "group" else "private", str(question)[:QUESTION_MAX], now))
        rid = cur.lastrowid
    return get(rid) or {}


def set_failed(req_id: int, error: str) -> None:
    with _lock, _conn() as con:
        con.execute("UPDATE staff_requests SET status='failed', error=? WHERE id=?", (str(error or "")[:300], int(req_id)))


def note_error(req_id: int, error: str) -> None:
    """Keep why passing an answer on failed, on a request that stays "answered" (the staff did answer)."""
    with _lock, _conn() as con:
        con.execute("UPDATE staff_requests SET error=? WHERE id=?", (str(error or "")[:300], int(req_id)))


def claim(req_id: int, answer: str, staff_name: str = "", now: Optional[float] = None) -> bool:
    """Mark ONE open request answered. True only for the caller that moved it from open: two staff messages arriving
    together never pass the same answer on twice."""
    now = time.time() if now is None else float(now)
    with _lock, _conn() as con:
        n = con.execute("UPDATE staff_requests SET status='answered', answer=?, staff_name=?, answered_at=? "
                        "WHERE id=? AND status='open'",
                        (str(answer)[:ANSWER_MAX], str(staff_name or "")[:80], now, int(req_id))).rowcount
    return bool(n)


def delete_bot(bot_id: str) -> int:
    """Forget every request of a deleted bot (they hold customers' words). No file is created for a bot that never
    asked anything."""
    if not db_path().exists():
        return 0
    with _lock, _conn() as con:
        return int(con.execute("DELETE FROM staff_requests WHERE bot_id=?", (str(bot_id),)).rowcount or 0)


# ============================================================
# Matching a staff message to a request
# ============================================================
def codes_in(text: Any) -> List[str]:
    return [m.group(1).upper() for m in CODE_RE.finditer(str(text or ""))]


def pick(open_requests: List[dict], text: Any, quoted: Any = "") -> Optional[dict]:
    """Which open request a staff message answers, or None when it cannot tell.

    In order: a code written in the message; a code in the message it quotes (a reply to the request message, which
    starts with its code); the only open request when there is exactly one."""
    by_code = {str(r.get("code") or "").upper(): r for r in open_requests or []}
    for c in codes_in(text):
        if c in by_code:
            return by_code[c]
    for c in codes_in(quoted):
        if c in by_code:
            return by_code[c]
    if len(open_requests or []) == 1:
        return open_requests[0]
    return None


def answer_text(text: Any, code: str) -> str:
    """The staff message without the request code, trimmed to `ANSWER_MAX`."""
    t = re.sub(r"(?<![0-9A-Za-z])#?" + re.escape(str(code or "")) + r"(?![0-9A-Za-z])", " ", str(text or ""),
               flags=re.I)
    t = re.sub(r"^[\s:,.\-]+", "", t)
    return t.strip()[:ANSWER_MAX]


# ============================================================
# The bot's staff contact for one turn
# ============================================================
def contact_for(bot: dict, account_id: str, chat_id: str) -> dict:
    """The staff contact that applies to a turn of `bot` on this account and chat, or {}. Only on the account the
    contact lives on, only on a channel listed in `CHANNELS`, and never inside the staff chat itself."""
    import chatbot_store
    import channel_accounts
    import channels
    c = chatbot_store.clean_staff_contact((bot or {}).get("staff_contact"))
    if not c or c["account_id"] != str(account_id or "") or c["chat_id"] == str(chat_id or ""):
        return {}
    acc = channel_accounts.get_account(c["account_id"]) or {}
    channel = str(acc.get("channel") or "")
    if channel not in CHANNELS:
        return {}
    s = channels.spec(channel)
    if not (s and s.nl("tra_loi_tu_javis")):
        return {}
    if c["account_id"] not in chatbot_store.account_ids_of(bot):
        return {}
    return dict(c, channel=channel)


def _turn_context(turn: dict, mode: str) -> Optional[Tuple[dict, dict]]:
    """(bot record with this chat's exception applied, staff contact) when this turn may ask the staff, else None.

    Fail-closed on every step: hub mode "full" only (an unknown mode reads as full in `mcp_catalog`, so it is not used
    here), a bot turn only, not a relay turn, and the bot's own level for THIS chat must be "full"."""
    import chatbot_store
    if str(mode or "").strip().lower() != "full":
        return None
    t = turn or {}
    bot_id = str(t.get("bot_id") or "").strip()
    if not bot_id or t.get("staff_relay") or str(t.get("kenh") or "") not in CHANNELS:
        return None
    bot = chatbot_store.get_bot(bot_id)
    if not bot:
        return None
    cfg = chatbot_store.ap_ngoai_le(bot, {"chat_type": t.get("chat_type"), "chat_id": t.get("chat_id"),
                                          "account_id": t.get("account_id")})
    if str(cfg.get("muc_quyen") or "") != "full":
        return None
    contact = contact_for(cfg, str(t.get("account_id") or ""), str(t.get("chat_id") or ""))
    if not contact or contact["channel"] != str(t.get("kenh") or ""):
        return None
    return cfg, contact


def turn_tool(mode: str) -> Optional[Tuple[dict, dict]]:
    """(tool spec, route entry) of `ask_staff` for the turn bound now, or None. Called by `mcp_hub.discover_all` after
    its cache, so the shared lists never carry a tool that belongs to one bot."""
    import turn_context
    if _turn_context(turn_context.current() or {}, mode) is None:
        return None
    mode_now = str(mode or "").strip().lower()

    async def _call(args):
        return await ask(turn_context.current() or {}, (args or {}).get("question"), mode_now)

    spec = {"fn": TOOL, "server": "javis", "name": TOOL, "description": TOOL_DESCRIPTION,
            "schema": {"type": "object", "properties": {"question": {
                "type": "string",
                "description": "The question for the staff, short and complete on its own (what, which item, how "
                               "many, which day)."}}, "required": ["question"]}}
    entry = {"call": _call, "source_type": "builtin", "source_id": "javis-core", "effect": "danger",
             "required_mode": "full", "health": "healthy"}
    return spec, entry


def staff_message(code: str, customer_name: str, question: str) -> str:
    """What the staff contact receives. In the machine's interface language: the staff are the shop's own people."""
    who_vi = f"Khách {customer_name}" if customer_name else "Khách"
    who_en = f"Customer {customer_name}" if customer_name else "A customer"
    return localefmt.chu(f"#{code} {who_vi} hỏi: {question}\nTrả lời tin này (hoặc nhắn kèm mã #{code}) để em báo "
                         "lại khách.",
                         f"#{code} {who_en} asks: {question}\nReply to this message (or include #{code}) and I will "
                         "pass the answer on.")


async def ask(turn: dict, question: Any, mode: str = "full") -> str:
    """The `ask_staff` tool: send the question to the staff contact and record the request. Returns the tool result
    the model reads (English, like every tool text): what to tell the customer now, or an ERROR line."""
    q = " ".join(str(question or "").split())[:QUESTION_MAX]
    if not q:
        return "ERROR: the question is empty. Write the question for the staff."
    t = turn or {}
    ctx = _turn_context(t, mode)
    if ctx is None:
        return "ERROR: asking the staff is not available in this chat."
    cfg, contact = ctx
    bot_id = str(cfg.get("id") or "")
    chat_id = str(t.get("chat_id") or "")
    expire_due()
    if count_open(bot_id, chat_id) >= OPEN_PER_CHAT_MAX:
        return (f"ERROR: {OPEN_PER_CHAT_MAX} questions from this chat are already waiting for the staff. Tell the "
                "customer you are still checking and will answer here.")
    if count_open(bot_id) >= OPEN_PER_BOT_MAX:
        return "ERROR: too many questions are waiting for the staff right now. Tell the customer the shop will reply."
    req = create(bot_id=bot_id, channel=contact["channel"], account_id=contact["account_id"],
                 customer_chat_id=chat_id, customer_chat_type=str(t.get("chat_type") or "private"),
                 customer_user_id=str(t.get("sender_id") or ""), customer_name=str(t.get("user_name") or ""),
                 customer_message_id=str(t.get("chat_message_id") or ""), staff_chat_id=contact["chat_id"],
                 staff_chat_type=contact["chat_type"], question=q)
    text = staff_message(req["code"], req["customer_name"], q)
    import chatbot_runtime
    ok, err = await chatbot_runtime.send_to_chat(contact["channel"], contact["account_id"], contact["chat_id"],
                                                 contact["chat_type"], text)
    if not ok:
        set_failed(req["id"], err)
        chatbot_runtime.staff_request_failed(cfg, req, err)
        return (f"ERROR: the staff contact could not be reached ({str(err)[:200]}). The owner has been told. Tell the "
                "customer the shop will get back to them; do not promise a time.")
    chatbot_runtime.record_bot_message(cfg, {"chat_id": contact["chat_id"], "chat_type": contact["chat_type"],
                                             "account_id": contact["account_id"], "_kenh": contact["channel"]}, text)
    return (f"Sent to the staff (request #{req['code']}). Now tell the customer briefly and politely that you are "
            "checking this with the team and will message them here as soon as you have the answer. Do not promise a "
            "time and do not mention the request code.")


# ============================================================
# Staff side: a message in the staff chat
# ============================================================
def on_staff_message(cfg: dict, text: Any, meta: Optional[dict]) -> Optional[dict]:
    """Called by the bot's precheck for every incoming message. None = not an answer to a request: the message goes
    on as before. {} = it was taken here (an answer being passed on, or a "which request?" note sent): the bot does not
    answer it as a customer message.

    Only the staff contact's chat on the contact's own account counts; any other chat returns None at once."""
    import chatbot_store
    m = meta or {}
    c = chatbot_store.clean_staff_contact((cfg or {}).get("staff_contact"))
    if not c or str(m.get("chat_id") or "") != c["chat_id"] or str(m.get("account_id") or "") != c["account_id"]:
        return None
    if m.get("member_join") or m.get("reaction"):
        return None
    words = str(text or "").strip()
    if not words or words in _NO_WORDS or words in _no_words_runtime():
        return None
    bot_id = str((cfg or {}).get("id") or "")
    try:
        expire_due()
        opens = open_for_staff(bot_id, c["account_id"], c["chat_id"])
    except sqlite3.Error as e:
        print(f"[staff_requests {bot_id}] store unreadable: {type(e).__name__}: {e}", file=sys.stderr)
        return None
    if not opens:
        return None
    req = pick(opens, words, m.get("reply_to_text"))
    if req is None:
        _ask_for_code(cfg, c, opens)
        return {}
    answer = answer_text(words, req["code"])
    if not answer:
        return {}                               # only the code: wait for the words
    if not claim(req["id"], answer, str(m.get("user_name") or "")):
        return {}
    req = dict(req, answer=answer, status="answered", staff_name=str(m.get("user_name") or ""))
    import chatbot_runtime
    chatbot_runtime.record_customer_message(cfg, m, words)
    _spawn(chatbot_runtime.relay_staff_answer(req))
    return {}


def _no_words_runtime() -> tuple:
    try:
        import chatbot_runtime
        return (chatbot_runtime.AUDIO_TRON, chatbot_runtime.VIDEO_TRON)
    except Exception:      # noqa: BLE001
        return ()


def _spawn(coro) -> None:
    try:
        task = asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        coro.close()
        print("[staff_requests] no event loop: answer not passed on", file=sys.stderr)
        return
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


def _ask_for_code(cfg: dict, contact: dict, opens: List[dict]) -> None:
    """Several requests are open and the message names none: ask once (per `CODE_NOTE_GAP_S`) which one it answers."""
    key = (str((cfg or {}).get("id") or ""), contact["account_id"], contact["chat_id"])
    now = time.time()
    if now - _CODE_NOTE_AT.get(key, 0.0) < CODE_NOTE_GAP_S:
        return
    if len(_CODE_NOTE_AT) > 500:
        _CODE_NOTE_AT.clear()
    _CODE_NOTE_AT[key] = now
    codes = ", ".join("#" + str(r.get("code")) for r in opens[:10])
    n = len(opens)
    note = localefmt.chu(f"Đang có {n} câu chờ trả lời: {codes}. Trả lời vào đúng tin hỏi, hoặc nhắn kèm mã, để em "
                         "báo đúng khách.",
                         f"{n} questions are waiting: {codes}. Reply to the question's message, or include its code, "
                         "so I tell the right customer.")
    import chatbot_runtime
    import channel_accounts
    channel = str((channel_accounts.get_account(contact["account_id"]) or {}).get("channel") or "")
    _spawn(chatbot_runtime.send_to_chat(channel, contact["account_id"], contact["chat_id"], contact["chat_type"], note))
