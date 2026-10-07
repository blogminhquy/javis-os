"""`turn` in pre/post_tool_call: hooks know WHO is talking, on both engine paths.

    python tests/run.py turn_context

What is pinned, and why each matters (a wrong `turn` means one person's tool call runs with
another person's identity, with no error anywhere):
  1. turn shape from a channel message: in a group the sender is the person, chat_id the group
  2. two bot turns of two people interleaved: each hook sees ITS turn, never the other one
  3. in-process path (API engines): the hook reads the bound turn; no turn -> None
  4. HTTP hub path (Claude Code / Codex): only a key issued by a live turn resolves; no header,
     a forged key or a key of a finished turn -> None, even if the server context has a turn
  5. the Claude SDK and Codex engines put the key on the hub entry per query, the shared
     config stays clean
  6. `_tg_answer`: a dedicated bot turn is never the owner; an admin channel turn is
  7. an old-style hook (`**kwargs`) keeps running

No network, no engine run. STATE_DIR and BRAINS_DIR are temp dirs.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import contextvars
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-turn-")
os.environ["BRAINS_DIR"] = tempfile.mkdtemp(prefix="javis-turn-brains-")

import turn_context  # noqa: E402
import plugins_host  # noqa: E402
import mcp_hub  # noqa: E402
import claude_sdk_engine  # noqa: E402
import claude_cli  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if (extra and not cond) else ""))
    if not cond:
        fails.append(name)


# Hooks are injected straight into the loader cache shape, so the test does not depend on
# which plugins happen to be enabled on this machine.
SEEN = []          # (event, tool_name, turn)
OLD_STYLE = []     # calls received by an old-style hook


async def _pre(tool_name="", args=None, turn=None, **_):
    SEEN.append(("pre", tool_name, turn))
    await asyncio.sleep(0.01)          # yield, so interleaved turns really interleave
    # What the ari-work plugin will do: write the caller's id over whatever the model sent.
    out = dict(args or {})
    if turn and turn.get("sender_id"):
        out["maZalo"] = turn["sender_id"]
    else:
        out.pop("maZalo", None)
    return {"args": out}


def _post(tool_name="", turn=None, **_):
    SEEN.append(("post", tool_name, turn))


def _old_style(tool_name="", args=None, mode="", vault_root=None, **kwargs):
    OLD_STYLE.append(tool_name)


plugins_host._load_all = lambda vault_root=None, scope_vault=True: {
    "hooks": {"pre_tool_call": [_pre, _old_style], "post_tool_call": [_post]}}


async def _base(args):
    await asyncio.sleep(0.01)
    return "maZalo=" + str((args or {}).get("maZalo", "<none>"))


WRAPPED = plugins_host.wrap_with_hooks("tim_viec", _base, "full", None)


async def part_shape():
    m_group = {"user_id": "U-an", "chat_id": "G-shop", "chat_type": "group", "user_name": "An"}
    t = turn_context.from_meta("zalo_personal", m_group, la_chu=False)
    check("1 group: sender_id is the person", t["sender_id"] == "U-an", t)
    check("1 group: chat_id is the group", t["chat_id"] == "G-shop" and t["chat_type"] == "group", t)
    check("1 group: bot turn is not the owner", t["la_chu"] is False)
    tg = turn_context.from_meta("telegram", {"user_id": 7, "chat_id": -100, "chat_type": "supergroup"}, True)
    check("1 telegram supergroup -> group", tg["chat_type"] == "group" and tg["sender_id"] == "7", tg)
    check("1 unknown chat_type -> private",
          turn_context.from_meta("zalo", {"user_id": "x"}, True)["chat_type"] == "private")
    check("1 no binding -> current() is None", turn_context.current() is None)
    check("1 no binding -> no key", turn_context.issue_key() is None)
    tok = turn_context.bind(t)
    cur = turn_context.current()
    cur["sender_id"] = "tampered"
    check("1 current() returns a copy", turn_context.current()["sender_id"] == "U-an")
    turn_context.reset(tok)
    check("1 reset -> None again", turn_context.current() is None)
    mj = dict(m_group, member_join=True)
    tj = turn_context.from_meta("zalo_personal", mj, la_chu=False)
    check("1 member_join names nobody (the newcomer sent nothing)", tj["sender_id"] == "", tj)
    check("1 member_join keeps the group", tj["chat_id"] == "G-shop" and tj["chat_type"] == "group", tj)

    # A task spawned during the turn copies the context; after the turn ends it must not still
    # see the turn, nor mint a new live key for it.
    tok = turn_context.bind(t)
    late = asyncio.Event()
    seen_late = {}

    async def child():
        await late.wait()
        seen_late["cur"] = turn_context.current()
        seen_late["key"] = turn_context.issue_key()

    task = asyncio.create_task(child())
    await asyncio.sleep(0)
    turn_context.reset(tok)
    late.set()
    await task
    check("1 child task after reset: current() None", seen_late["cur"] is None, seen_late)
    check("1 child task after reset: no new key", seen_late["key"] is None, seen_late)


async def _bot_turn(sender, chat):
    tok = turn_context.bind(turn_context.make("zalo_personal", sender, "group", chat, False))
    try:
        res = []
        for _ in range(3):           # several tool calls in one turn, interleaved with the other turn
            res.append(await WRAPPED({"maZalo": "made-up-by-model"}))
        return res
    finally:
        turn_context.reset(tok)


async def part_interleaved_in_process():
    SEEN.clear()
    OLD_STYLE.clear()
    a, b = await asyncio.gather(_bot_turn("U-an", "G-shop"), _bot_turn("U-binh", "G-shop"))
    check("2 turn A tool calls carry A's id only", a == ["maZalo=U-an"] * 3, a)
    check("2 turn B tool calls carry B's id only", b == ["maZalo=U-binh"] * 3, b)
    pre = [t for ev, _, t in SEEN if ev == "pre"]
    post = [t for ev, _, t in SEEN if ev == "post"]
    check("2 every pre hook saw a turn", len(pre) == 6 and all(pre), pre)
    check("2 every post hook saw a turn", len(post) == 6 and all(post), post)
    senders = sorted(t["sender_id"] for t in pre)
    check("2 3 calls each, no leak", senders == ["U-an"] * 3 + ["U-binh"] * 3, senders)
    check("2 group chat_id stays the group in the hook", all(t["chat_id"] == "G-shop" for t in pre))
    check("7 old-style **kwargs hook still runs", OLD_STYLE == ["tim_viec"] * 6, OLD_STYLE)

    SEEN.clear()
    out = await WRAPPED({"maZalo": "made-up-by-model"})
    check("3 no turn -> hook gets turn None", SEEN and SEEN[0][2] is None, SEEN[:1])
    check("3 no turn -> model's id removed, not trusted", out == "maZalo=<none>", out)

    tok = turn_context.bind(turn_context.make("dashboard", chat_id="sid-1", la_chu=True))
    SEEN.clear()
    await WRAPPED({})
    turn_context.reset(tok)
    t = SEEN[0][2]
    check("3 owner session -> la_chu True, sender ''", t and t["la_chu"] is True and t["sender_id"] == "", t)


class _Req:
    """The part of a Starlette Request that `handle_http` reads."""

    def __init__(self, headers, body):
        self.headers = {k.lower(): v for k, v in headers.items()}
        self._body = body

    async def json(self):
        return self._body


async def _hub_call(key=None, i=1, child=True):
    h = {"Authorization": "Bearer T"}
    if key is not None:
        h[turn_context.HEADER] = key
    body = {"jsonrpc": "2.0", "id": i, "method": "tools/call",
            "params": {"name": "tim_viec", "arguments": {"maZalo": "made-up-by-model"}}}
    # child=True: a CLI engine reaches the hub from a CHILD PROCESS, nothing of the turn's context
    # comes along, so run the request in an empty context and only the header can carry the turn.
    # child=False: an in-process client whose context DOES hold a turn; the hub must ignore it.
    req = mcp_hub.handle_http(_Req(h, body))
    resp = await (asyncio.create_task(req, context=contextvars.Context()) if child else req)
    return json.loads(resp.body)["result"]["content"][0]["text"]


async def part_hub_http():
    mcp_hub.hub_token = lambda: "T"

    async def _fake_discover(*a, **kw):
        return [], {"tim_viec": {"call": WRAPPED}}
    mcp_hub.discover_all = _fake_discover

    # The engine side: a live turn issues a key (what Claude SDK / Codex send as the header).
    holder = {}

    async def _turn_with_key(sender):
        tok = turn_context.bind(turn_context.make("zalo_personal", sender, "private", sender, False))
        try:
            key = turn_context.issue_key()
            holder[sender] = key
            check(f"4 one key per turn ({sender})", turn_context.issue_key() == key)
            return await _hub_call(key)
        finally:
            turn_context.reset(tok)

    r1, r2 = await asyncio.gather(_turn_with_key("U-an"), _turn_with_key("U-binh"))
    check("4 HTTP: key of A -> A's id", r1.startswith("maZalo=U-an"), r1)
    check("4 HTTP: key of B -> B's id", r2.startswith("maZalo=U-binh"), r2)

    # The server context has a turn (as an in-process test client would): the hub must not use it.
    tok = turn_context.bind(turn_context.make("dashboard", la_chu=True))
    try:
        SEEN.clear()
        r = await _hub_call(None, child=False)
        check("4 HTTP no header -> turn None (no ambient leak)", SEEN[0][2] is None, SEEN[:1])
        check("4 HTTP no header -> model id removed", r.startswith("maZalo=<none>"), r)
        SEEN.clear()
        r = await _hub_call("forged-" + "x" * 30, child=False)
        check("4 HTTP forged key -> turn None", SEEN[0][2] is None and r.startswith("maZalo=<none>"), r)
        SEEN.clear()
        r = await _hub_call(holder["U-an"], child=False)
        check("4 HTTP key of a FINISHED turn -> None", SEEN[0][2] is None and r.startswith("maZalo=<none>"), r)
        check("4 hub left the caller's turn alone", turn_context.current()["kenh"] == "dashboard")
    finally:
        turn_context.reset(tok)
    check("4 resolve_key(None/'') -> None", turn_context.resolve_key(None) is None
          and turn_context.resolve_key("  ") is None)


async def part_engines():
    shared = {"javis": {"type": "http", "url": "http://127.0.0.1:7777/hub/mcp",
                        "headers": {"Authorization": "Bearer T", "X-Javis-Bot": "1"}}}
    snapshot = json.dumps(shared, sort_keys=True)

    out = claude_sdk_engine.ClaudeSDK._gan_khoa_luot(shared)
    check("5 Claude: no turn -> no header", turn_context.HEADER not in out["javis"]["headers"])

    tok = turn_context.bind(turn_context.make("zalo_personal", "U-an", "private", "U-an", False))
    try:
        out = claude_sdk_engine.ClaudeSDK._gan_khoa_luot(shared)
        key = out["javis"]["headers"].get(turn_context.HEADER)
        check("5 Claude: header carries a key of this turn",
              bool(key) and turn_context.resolve_key(key)["sender_id"] == "U-an", out)
        check("5 Claude: other headers kept", out["javis"]["headers"]["X-Javis-Bot"] == "1")
        check("5 Claude: shared config dict not mutated", json.dumps(shared, sort_keys=True) == snapshot)

        # The real bot path: config file + allowed_tools (the early-return branch of _mcp_servers).
        cfg = os.path.join(tempfile.mkdtemp(), "hub.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": shared}, f)
        eng = claude_sdk_engine.ClaudeSDK(allowed_tools=["mcp__javis"])
        eng.mcp_config = cfg
        servers, _ = eng._mcp_servers()
        check("5 Claude bot path (_mcp_servers) carries the key",
              servers["javis"]["headers"].get(turn_context.HEADER) == key, servers)
        with open(cfg, encoding="utf-8") as f:
            check("5 Claude: config FILE never gets the key", turn_context.HEADER not in f.read())

        cx = claude_cli.CodexCLI()
        args = cx._build_args()
        check("5 Codex hub_turn off -> no override", not any(turn_context.HEADER in str(a) for a in args))
        cx.hub_turn = True
        args = cx._build_args()
        over = [a for a in args if str(a).startswith(turn_context.CODEX_HEADER_KEY + "=")]
        check("5 Codex hub_turn on -> one override", len(over) == 1, args)
        val = over[0].split("=", 1)[1].strip('"') if over else ""
        check("5 Codex override resolves to this turn", val == key, over)
        check("5 Codex override sits before the subcommand", over and args.index(over[0]) < args.index("exec"))
        check("5 Codex extra_config untouched", cx.extra_config == [])
    finally:
        turn_context.reset(tok)
    cx2 = claude_cli.CodexCLI()
    cx2.hub_turn = True
    check("5 Codex no turn -> no override",
          not any(turn_context.HEADER in str(a) for a in cx2._build_args()))


async def part_tg_answer():
    import main
    seen = []

    async def _fake_engine(text, meta, progress, **kw):
        seen.append((kw.get("channel"), turn_context.current()))
        return {"text": "ok", "files": []}
    main._tg_answer_engine = _fake_engine

    bot = {"id": "b1", "slug": "shop", "brain": "brain", "name": "Shop"}
    meta = {"chat_id": "G-shop", "user_id": "U-an", "chat_type": "group", "user_name": "An"}
    await main._tg_answer("hi", meta, None, channel="zalo_personal", bot=bot, ghi_kho=False)
    ch, t = seen[-1]
    check("6 bot turn: engine sees channel bot:<slug>", ch == "bot:shop", ch)
    check("6 bot turn: turn keeps the REAL channel", t and t["kenh"] == "zalo_personal", t)
    check("6 bot turn: sender is the person, not the group",
          t and t["sender_id"] == "U-an" and t["chat_id"] == "G-shop", t)
    check("6 bot turn: never the owner", t and t["la_chu"] is False, t)

    await main._tg_answer("hi", {"chat_id": "123", "user_id": "123", "chat_type": "private"}, None,
                          channel="telegram", ghi_kho=False)
    t = seen[-1][1]
    check("6 admin channel turn: la_chu True", t and t["la_chu"] is True and t["kenh"] == "telegram", t)
    check("6 turn released after _tg_answer", turn_context.current() is None)


async def main_():
    await part_shape()
    await part_interleaved_in_process()
    await part_hub_http()
    await part_engines()
    await part_tg_answer()


asyncio.run(main_())
if fails:
    print(f"\n{len(fails)} FAIL: {fails}")
    sys.exit(1)
print("\nOK - test_turn_context: tất cả assertion pass")
