"""Antigravity chat turns on one agy process per conversation, kept warm between turns (2026-11-24).

The owner measured it on agy 1.5.15 with Javis's real 58 KB context (gemini-4-hydrogen-high):

    one process per turn, whole prompt every time ....... first word 11.6 s, turn 14.7 s, cache 0%
    --conversation on a new process, message only ...... first word 3.7 s, turn 4.4 s, cache 85%
    warm --input-format stream-json, turns 2 to 4 ....... first word 1.6-2.7 s, turn 2.2-2.9 s, cache 92%

How agy behaves in this mode (measured again on 1.5.15, Windows, 2026-11-24):

- `agy --input-format stream-json --output-format stream-json` prints `init` with its conversation_id about 2.5 s
  after it starts, BEFORE any message. Each stdin line {"event":"user","message":{"role":"user","content":...}}
  runs one turn that ends with a `result` line, and the process stays up for the next line. EOF on stdin ends it
  (about 2.7 s later, exit 0). A 208 KB line with every non-ASCII character escaped is read whole.
- `--conversation <id>` resumes that thread (the model remembers it). An id agy does not know is NOT an error: a
  warning on stderr and a NEW conversation with another id. So the id in `init` is compared with the one asked
  for before anything is sent, and a thread that did not come back gets the whole context again.
- agy has no system prompt flag: the instructions travel inside the first message of a thread. A continued thread
  already holds them, so later turns send only the per-turn facts and the new message (`cli.resume_prompt`).
  Sending the 58 KB again on every resumed turn made it slower than not resuming at all and grew the thread from
  27k to 47.5k tokens.
- `result.usage` here is the running total of the whole process; the turn's own numbers are summed from its
  `agent_response` steps (antigravity_cli._doi_su_kien).

Only the owner's dashboard chat comes here (main sets `cli.stream_turns`, and `cli.warm_key` for warm_pool).
Anything that fails before the message is sent (no init, a refused flag, an exit at start-up) raises Fallback and
the turn runs the one-shot way, exactly as before. JAVIS_AGY_RESUME=0 turns the whole path off.

A turn that may have left a command running hands its process back the one-shot way (stdin closed, process group
recorded) so tien_trinh_nen still adopts what it left behind: the rule codex_steer follows for Codex.
"""
from __future__ import annotations

import asyncio
import collections
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from typing import AsyncIterator, Optional

import warm_pool

ENV_SWITCH = "JAVIS_AGY_RESUME"
KIND = "agy"
# init normally comes 2-3 s after start; a slow sign-in check or a cold disk can take longer. Past this the turn
# runs one-shot instead.
START_TIMEOUT_S = 45.0
# agy needs 2-3 s to exit once stdin closes. Past this it is stopped (itself only, never its process group).
EXIT_GRACE_S = 20.0

# A run_command step whose output does not say the command finished, or a command line that starts something in
# the background, may have left work running: that turn hands its process back (see the module docstring).
_FINISHED = re.compile(r"exited with code", re.I)
_BACKGROUND = re.compile(
    r"(?:^|[\s;&|(])(?:nohup|setsid|disown|start-process|start-job|start\s+/b|screen\s+-dm|tmux\s+new)\b"
    r"|(?<!&)&\s*(?:$|;|\n|\))",
    re.I)
_SHELL_TOOLS = ("run_command",)


class Fallback(Exception):
    """The turn could not start on the stream path: run it one-shot instead."""


def enabled() -> bool:
    return str(os.getenv(ENV_SWITCH, "1")).strip().lower() not in ("0", "false", "no", "off")


class Lines:
    """stdout of one agy process, read on a thread and handed to the event loop of the turn running now.

    Between turns nobody listens: lines wait in a buffer. A warm turn drops what was left over from the turn before
    (an answer is over once its `result` came), but keeps the end-of-stream mark so a dead process is noticed.
    """

    def __init__(self, proc):
        self.proc = proc
        self._lock = threading.Lock()
        self._buf: collections.deque = collections.deque()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queue: Optional[asyncio.Queue] = None
        self.stderr: collections.deque = collections.deque(maxlen=40)
        threading.Thread(target=self._read_out, daemon=True, name="javis-agy-warm-out").start()
        threading.Thread(target=self._read_err, daemon=True, name="javis-agy-warm-err").start()

    def _read_out(self) -> None:
        try:
            for line in iter(self.proc.stdout.readline, ""):
                line = line.strip()
                if line:
                    self._push(line)
        except Exception:  # noqa: BLE001 - a closed pipe ends the stream like EOF
            pass
        self._push(None)

    def _read_err(self) -> None:
        try:
            for line in iter(self.proc.stderr.readline, ""):
                if line.strip():
                    self.stderr.append(line.rstrip())
        except Exception:  # noqa: BLE001
            pass

    def _push(self, item) -> None:
        with self._lock:
            loop, queue = self._loop, self._queue
            if loop is not None and queue is not None and not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(queue.put_nowait, item)
                    return
                except RuntimeError:
                    pass
            self._buf.append(item)

    def attach(self, loop: asyncio.AbstractEventLoop, drop_stale: bool = False) -> None:
        with self._lock:
            self._loop = loop
            self._queue = asyncio.Queue()
            while self._buf:
                item = self._buf.popleft()
                if drop_stale and item is not None:
                    continue
                self._queue.put_nowait(item)

    def detach(self) -> None:
        with self._lock:
            self._loop = None
            self._queue = None

    async def get(self, timeout: Optional[float]):
        if self._queue is None:
            raise RuntimeError("not attached")
        if timeout is None:
            return await self._queue.get()
        return await asyncio.wait_for(self._queue.get(), timeout)

    def stderr_tail(self, n: int = 6) -> str:
        return "\n".join(list(self.stderr)[-n:]).strip()


class AgyHandle(warm_pool.Handle):
    """A running agy with its conversation open, kept between turns of one chat."""
    kind = KIND

    def __init__(self, proc, lines: Lines, conversation_id: str):
        self.proc = proc
        self.lines = lines
        self.conversation_id = conversation_id

    def alive(self) -> bool:
        return self.proc.poll() is None

    async def close(self) -> None:
        hand_back(self.proc)


def hand_back(proc) -> threading.Event:
    """Close the way a one-shot agy ends: stdin closed, agy exits on its own (its children keep their process group
    for tien_trinh_nen), and only agy itself is stopped if it is still up after EXIT_GRACE_S. Returns an event set
    once agy is gone."""
    gone = threading.Event()
    try:
        proc.stdin.close()
    except Exception:  # noqa: BLE001
        pass

    def _reap():
        try:
            proc.wait(timeout=EXIT_GRACE_S)
        except Exception:  # noqa: BLE001
            import antigravity_cli
            antigravity_cli.end_engine_only({"proc": proc})
        gone.set()
    threading.Thread(target=_reap, daemon=True, name="javis-agy-warm-reap").start()
    return gone


def _mcp_state(cli) -> str:
    """What agy loads its MCP servers from (the shared HOME files plus the brain's own). It reads them at start-up, so
    a process opened before the hub entry changed (another mode, another brain, a new hub token) must not serve."""
    import antigravity_cli
    parts = []
    try:
        paths = antigravity_cli.duong_mcp(getattr(cli, "cwd", None))
    except Exception:  # noqa: BLE001
        paths = []
    for p in paths:
        try:
            parts.append(f"{p}:{hashlib.sha256(p.read_bytes()).hexdigest()}")
        except OSError:
            parts.append(f"{p}:-")
    return "|".join(parts)


def fingerprint(cli, args: list, conversation_id: str) -> str:
    """What a warm process was opened with. The conversation is part of it: a rotated or reset thread runs cold."""
    import antigravity_cli
    raw = json.dumps([antigravity_cli._chu_ky_cli(cli.cli_path or ""), list(args), str(cli.cwd or ""),
                      str(getattr(cli, "agy_home", None) or ""), _mcp_state(cli), str(conversation_id or "")],
                     ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def message_line(text: str) -> str:
    """One turn on stdin. Every non-ASCII character is escaped, so the pipe only ever carries ASCII and a read cut in
    the middle of a multi-byte character (the old "gm", "hn" for Vietnamese) cannot happen."""
    return json.dumps({"event": "user", "message": {"role": "user", "content": text}}, ensure_ascii=True) + "\n"


def _write(proc, line: str) -> None:
    proc.stdin.write(line)
    proc.stdin.flush()


def _spawn(argv: list, cwd: str, env):
    from claude_cli import _no_window
    return subprocess.Popen(
        argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, text=True,
        encoding="utf-8", errors="replace", bufsize=1, creationflags=_no_window(),
        start_new_session=(os.name != "nt"), env=env)


async def open_process(argv: list, cwd: str, env, timeout: float = START_TIMEOUT_S):
    """Start agy and wait for its `init`. Returns (proc, lines, conversation_id). Raises Fallback."""
    try:
        proc = await asyncio.to_thread(_spawn, argv, cwd, env)
    except Exception as e:  # noqa: BLE001
        raise Fallback(f"spawn: {type(e).__name__}: {e}")
    lines = Lines(proc)
    lines.attach(asyncio.get_running_loop())
    end = time.monotonic() + timeout
    try:
        while True:
            left = end - time.monotonic()
            if left <= 0:
                raise Fallback("no init")
            try:
                line = await lines.get(left)
            except asyncio.TimeoutError:
                raise Fallback("no init")
            if line is None:
                raise Fallback(f"exited at start ({lines.stderr_tail(2)[:200]})")
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if str(ev.get("event") or ev.get("type") or "").lower() == "init":
                return proc, lines, str(ev.get("conversation_id") or "").strip()
    except BaseException:
        lines.detach()
        _stop(proc)
        raise


def _stop(proc) -> None:
    """A process that must not run on (no init, the turn was stopped): the whole tree, as the one-shot path does."""
    if proc.poll() is not None:
        return
    import claude_cli
    threading.Thread(target=claude_cli._kill_tree, args=(proc,), daemon=True, name="javis-agy-warm-stop").start()


def _recipe(cli, argv: list, env, conversation_id: str):
    """How to reopen this conversation's process ahead of its next turn (warm_pool.prewarm)."""
    cwd = cli.cwd

    async def _open() -> AgyHandle:
        proc, lines, cid = await open_process(argv, cwd, env)
        lines.detach()
        if cid != conversation_id:
            hand_back(proc)
            raise RuntimeError("the conversation did not come back")
        return AgyHandle(proc, lines, cid)
    return _open


def left_running(name: str, params: dict, output: str) -> bool:
    """A shell step that may have left something running after the turn."""
    if name not in _SHELL_TOOLS:
        return False
    command = ""
    for k, v in (params or {}).items():
        if str(k).lower() in ("commandline", "command", "cmd") and isinstance(v, str):
            command = v
            break
    return not _FINISHED.search(output or "") or bool(_BACKGROUND.search(command))


async def run(cli, prompt: str) -> AsyncIterator[dict]:
    """One chat turn on a stream-json agy. Yields AntigravityCLI's events plus a first `session` event.

    `prompt` carries the whole context for a NEW thread (the instructions go in front of it); `cli.resume_prompt` is
    sent instead when the thread really continues. Raises Fallback before anything is yielded when the turn cannot
    start here. Sets `cli.retry_one_shot` (and yields nothing more) when the turn failed before any text or tool for
    a reason a retry may fix, so the caller runs it the one-shot way with its own retries.
    """
    import antigravity_cli as agy
    import claude_cli as cc
    import localefmt
    import text_breaks

    loop = asyncio.get_running_loop()
    warm_key = str(getattr(cli, "warm_key", "") or "")
    want = str(cli.session_id or "").strip()
    base = cli.stream_args("")
    env = cli.engine_env()
    why: dict = {}
    slot = warm_pool.POOL.take(warm_key, KIND, fingerprint(cli, base, want), why) if (warm_key and want) else None
    if slot is None and not why.get("cold"):
        why["cold"] = "new_thread" if not want else "no_key"
    proc = lines = None
    cid = ""
    lost = False
    sent = False
    for _attempt in (1, 2):
        if slot is not None:
            h = slot.handle
            proc, lines, cid = h.proc, h.lines, h.conversation_id
            lines.attach(loop, drop_stale=True)
        else:
            argv = cli.stream_args(want)
            proc, lines, cid = await open_process(argv, cli.cwd, env)     # raises Fallback
            lost = bool(want) and cid != want
            if lost:
                why["cold"] = "thread_lost"
                print(f"[antigravity warm] conversation {want[:8]} did not come back (agy opened {cid[:8]}),"
                      f" sending the whole context", file=sys.stderr)
        continuing = bool(want) and not lost
        if continuing and cli.resume_prompt is not None:
            text = cli.resume_prompt
        elif continuing:
            text = prompt
        else:
            instr = (cli.instructions or "").strip()
            text = (instr + "\n\n" + prompt) if instr else prompt
        try:
            await asyncio.to_thread(_write, proc, message_line(text))
            sent = True
            break
        except (OSError, ValueError) as e:
            lines.detach()
            if slot is not None:
                # The warm process died between turns: open a new one on the same thread.
                warm_pool.POOL.release(slot, keep=False)
                slot = None
                why["cold"] = "process_died"
                continue
            _stop(proc)
            raise Fallback(f"stdin: {type(e).__name__}: {e}")
    if not sent:
        raise Fallback("stdin closed twice")

    with cc._PROC_LOCK:
        cc._ACTIVE_PROCS[proc] = cli.tag
    try:   # a warm agy keeps the mark of its conversation from its start: this turn still has to look for it
        import tien_trinh_nen
        tien_trinh_nen.note_mark(cli.tag, tien_trinh_nen.mark_for(cli.tag))
    except Exception:  # noqa: BLE001
        pass

    warm = slot is not None
    finished = False
    keep = False
    ok = False
    timed_out = False
    try:
        yield {"type": "session", "session_id": cid, "warm": warm,
               **({} if warm else {"cold": why.get("cold") or "new_thread"})}
        cap = cli.turn_cap()
        deadline = (time.monotonic() + cap) if cap > 0 else None
        pieces: list = []
        chan: dict = {"stream_turn": True}     # usage: sum this turn's steps (antigravity_cli._doi_su_kien)
        errors: list = []
        names: dict = {}
        params_by_id: dict = {}
        used_tool = after_tool = maybe_running = False
        status = ""
        while True:
            try:
                line = await lines.get(None if deadline is None else max(0.0, deadline - time.monotonic()))
            except asyncio.TimeoutError:
                timed_out = True
                break
            if line is None:
                break
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            kind = str(ev.get("event") or ev.get("type") or "").lower()
            if kind == "init":
                continue
            n = len(pieces)
            for out in cli._doi_su_kien(ev, pieces, chan):
                t = out.get("type")
                if t == "tool_call":
                    used_tool = after_tool = True
                    names[str(out.get("id") or "")] = str(out.get("name") or "")
                    params_by_id[str(out.get("id") or "")] = out.get("input") or {}
                elif t == "tool_result":
                    _id = str(out.get("id") or "")
                    if left_running(names.get(_id, ""), params_by_id.get(_id, {}), str(out.get("content") or "")):
                        maybe_running = True
                elif t == "error":
                    errors.append(str(out.get("content") or ""))
                    continue
                yield out
            if after_tool and len(pieces) > n:
                text_breaks.break_after_tool(pieces, n)
                after_tool = False
            for piece in pieces[n:]:
                if piece:
                    yield {"type": "delta", "content": piece}
            if kind == "result":
                status = "success" if agy.is_success_result(ev) else "error"
                break
        text = agy._chot_van("".join(pieces).strip(), chan.get("toan_van", ""))
        ok = status == "success"
        if not status and not timed_out:
            # agy ended without a result line: say why if it said anything.
            tail = lines.stderr_tail()
            if agy._la_loi_chua_dang_nhap(tail):
                errors.append(localefmt.chu(
                    "Antigravity CLI chưa đăng nhập. Gõ `agy` một lần trên máy chạy Javis.",
                    "Antigravity CLI is not signed in. Type `agy` once on the machine running Javis."))
            else:
                errors.append(tail[:1500] or localefmt.chu("Antigravity CLI dừng giữa lượt.",
                                                           "Antigravity CLI stopped mid-turn."))
        if timed_out:
            errors.append(agy._cau_bao_het_gio("print timeout", cap))
        if (not ok and not text and not used_tool and not timed_out
                and any(agy._la_loi_tam_thoi(e) for e in errors)):
            # Nothing done yet and the provider may only be busy: the one-shot path retries with a pause.
            cli.retry_one_shot = True
            finished = True
            return
        for e in errors:
            yield {"type": "error", "content": e}
        if text:
            yield {"type": "final", "content": text}
        elif ok:
            yield {"type": "error", "content": localefmt.chu(
                "Antigravity CLI chạy xong nhưng không trả về nội dung nào.",
                "Antigravity CLI finished but returned nothing.")}
        keep = bool(warm_key) and ok and not maybe_running and proc.poll() is None
        finished = True
    finally:
        with cc._PROC_LOCK:
            cc._ACTIVE_PROCS.pop(proc, None)
        lines.detach()
        cli.session_id = cid or None
        # A thread is worth resuming when it answered; one that only failed is opened anew next time.
        cli.resumable = bool(cid) and finished and ok
        if not finished or timed_out:
            # Stopped, out of time, or the chat went away mid-turn: as the one-shot path does, the process goes.
            _stop(proc)
            if slot is not None:
                warm_pool.POOL.release(slot, keep=False)
        elif keep:
            fp_now = fingerprint(cli, base, cid)
            if slot is not None:
                warm_pool.POOL.release(slot, fingerprint=fp_now)
            else:
                new = warm_pool.POOL.admit(warm_key, KIND, fp_now, AgyHandle(proc, lines, cid),
                                           recipe=_recipe(cli, cli.stream_args(cid), env, cid))
                if new is not None:
                    warm_pool.POOL.release(new)
                else:
                    _hand_back_after_turn(cli, proc)
        else:
            if slot is not None:
                warm_pool.POOL.detach(slot)      # out of the pool, this turn closes it below
            if warm_key and ok and cid:
                # The thread is fine, only this process had to go: the owner typing the next message
                # still reopens one ahead of it (warm_pool.prewarm).
                warm_pool.POOL.remember(warm_key, KIND, fingerprint(cli, base, cid),
                                        _recipe(cli, cli.stream_args(cid), env, cid))
            _hand_back_after_turn(cli, proc)


def _hand_back_after_turn(cli, proc) -> None:
    """End this turn's process the one-shot way and let tien_trinh_nen adopt what it left once agy itself is gone."""
    gone = hand_back(proc)
    try:
        import tien_trinh_nen
        tien_trinh_nen.ghi_nhom(cli.tag, proc.pid)
        tien_trinh_nen.note_engine_exiting(cli.tag, gone)
    except Exception:  # noqa: BLE001
        pass
