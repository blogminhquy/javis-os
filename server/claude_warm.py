"""Claude Code chat turns on a `claude` process kept warm between turns (0.382.0).

Spec: docs/dev/2026-10-toc-do-luot-chat-spec.md. `ClaudeSDK.query` opens a new ClaudeSDKClient for every turn and
closes it at the end, so each turn pays the CLI start-up and reconnects every MCP server before the model starts. This
module runs the same turn on a client kept in warm_pool, so the next turn of the conversation only sends its message.

Why a separate module: claude_sdk_engine.py is pinned by the native qualification evidence (its source hash is checked
in tests/python/test_plan_limits.py), so it is not edited. The loop below follows `ClaudeSDK.query` and reuses its
helpers by module attribute (`eng.map_message`, so the plan_limits wrapper still sees rate-limit events).

What stays exactly as before: the options (built by the engine's own `_options`), the watchdogs, the events yielded.
What differs for a warm client:
- the hub turn header is the slot's lane key (turn_lane.Lane), pointed at the running turn each time;
- the client connects inside the lane's context, so hooks and in-process plugin tools (they run in tasks the SDK
  creates at connect time) see the turn that is running, not the first one;
- the steer hook and the stderr callback go through the handle to the engine of the running turn.
The system prompt is not part of the fingerprint: Claude Code keeps the system prompt of the first turn of a session
when it resumes (measured in 0.345.0), so a warm process does not change what the model sees.

`query(cli, prompt, key)` falls back to `cli.query(prompt)` whenever the turn is not eligible.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from typing import AsyncIterator, Optional

import turn_lane
import warm_pool


class ClaudeHandle(warm_pool.Handle):
    kind = "claude"

    def __init__(self, client, lane):
        self.client = client
        self.lane = lane
        self.cli = None          # the engine of the turn now running (hook and stderr target)
        self.parts = None        # fingerprint parts it was last released with (to log what changed on a miss)
        self.dead = False

    def alive(self) -> bool:
        if self.dead:
            return False
        try:
            proc = self.client._transport._process
            if proc is None or proc.returncode is not None:
                return False
            q = self.client._query
            task = getattr(q, "_read_task", None)
            return not getattr(q, "_closed", False) and not (task is not None and task.done())
        except Exception:  # noqa: BLE001 - an SDK without those fields: trust our own flag
            return True

    def quiet(self) -> bool:
        """Nothing left over from the last turn. The client has ONE message stream: whatever the CLI wrote after the
        last result (a background task's news, a turn it started by itself) would be read as this turn's. Only the
        end-of-turn system notes are drained; anything else means the process is not in a known state."""
        try:
            import anyio
            stream = self.client._query._message_receive
        except Exception:  # noqa: BLE001
            return True
        while True:
            try:
                m = stream.receive_nowait()
            except anyio.WouldBlock:
                return True
            except Exception:  # noqa: BLE001 - closed or broken: not reusable
                return False
            sub = str((m or {}).get("subtype") or "") if isinstance(m, dict) else ""
            if not (isinstance(m, dict) and m.get("type") == "system" and not sub.startswith("task_")):
                return False

    async def close(self) -> None:
        self.dead = True
        try:
            await self.client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        if self.lane is not None:
            self.lane.close()

    async def steer_hook(self, input_data, tool_use_id, context):
        cli = self.cli
        if cli is None:
            return {}
        return await cli._steer_hook(input_data, tool_use_id, context)

    def on_stderr(self, line):
        cli = self.cli
        if cli is not None:
            cli._on_stderr(line)


def eligible(cli) -> bool:
    """Only the owner's dashboard chat engine: SDK engine, no allowlist (background lanes), no trial profile."""
    if warm_pool.budget_mb() <= 0:
        return False
    if type(cli).__name__ != "ClaudeSDK" or getattr(cli, "trial_profile", None) is not None:
        return False
    if cli.allowed_tools or getattr(cli, "team_gate", None) or cli.max_wall_s:
        return False
    return str(cli.tag or "").startswith("chat:")


def _stat(p) -> str:
    try:
        st = os.stat(p)
        return f"{st.st_size}:{st.st_mtime_ns}"
    except OSError:
        return "-"


def _skills_stat(root: str) -> str:
    """Every SKILL.md under the mirrored skills folder: an edited skill changes its file, not the folder."""
    out = [_stat(root)]
    try:
        for e in sorted(os.scandir(root), key=lambda e: e.name):
            if e.is_dir():
                out.append(e.name + "=" + _stat(os.path.join(e.path, "SKILL.md")))
    except OSError:
        pass
    return hashlib.sha256("|".join(out).encode("utf-8")).hexdigest()


def fingerprint(cli, opts) -> str:
    """What decides whether a warm process still fits this turn. The resumed session is part of it."""
    return _hash_parts(fingerprint_parts(cli, opts))


def _hash_parts(parts: dict) -> str:
    return hashlib.sha256(json.dumps(parts, default=str, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def changed_parts(old: dict, new: dict) -> list:
    """Names of the fingerprint parts that differ, for the one log line a missed warm process leaves."""
    return sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))


def fingerprint_parts(cli, opts) -> dict:
    import turn_context
    servers = {}
    raw = getattr(opts, "mcp_servers", None)
    if isinstance(raw, dict):
        for name, conf in raw.items():
            if isinstance(conf, dict) and conf.get("type") == "sdk":
                servers[name] = "sdk"
            elif isinstance(conf, dict):
                c = dict(conf)
                if isinstance(c.get("headers"), dict):
                    c["headers"] = {k: v for k, v in c["headers"].items() if k != turn_context.HEADER}
                servers[name] = c
    else:
        servers = str(raw)
    try:
        import plugins_host
        plugins = repr(plugins_host._signature(cli.javis_vault, scope_vault=False))
    except Exception:  # noqa: BLE001
        plugins = ""
    env = getattr(opts, "env", None) or {}
    auth = sorted((k, v) for k, v in env.items() if k.startswith(("ANTHROPIC_", "CLAUDE_")))
    cli_path = getattr(opts, "cli_path", None) or ""
    sp = getattr(opts, "system_prompt", None)
    cwd = str(getattr(opts, "cwd", "") or "")
    conf_dir = env.get("CLAUDE_CONFIG_DIR") or os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return {
        "cli": [str(cli_path), _stat(cli_path) if cli_path else ""], "cwd": cwd, "model": getattr(opts, "model", None),
        "effort": getattr(opts, "effort", None), "settings": str(getattr(opts, "settings", None)),
        "permission_mode": getattr(opts, "permission_mode", None),
        "setting_sources": list(getattr(opts, "setting_sources", None) or []),
        "disallowed_tools": list(getattr(opts, "disallowed_tools", None) or []),
        "stream_flags": [bool(getattr(opts, "include_partial_messages", False)),
                         bool(getattr(opts, "include_hook_events", False))],
        "system_prompt_type": sp.get("type") if isinstance(sp, dict) else ("raw" if sp else ""),
        "mcp_servers": servers, "plugins": plugins, "auth_env": hashlib.sha256(json.dumps(auth).encode()).hexdigest(),
        "mode": cli.javis_mode, "vault": str(cli.javis_vault or ""), "hooks": bool(getattr(opts, "hooks", None)),
        "resume": str(getattr(opts, "resume", None) or ""),
        # Claude Code reads these at start-up only: a new skill or a CLAUDE.md edit needs a new process.
        "claude_md": _stat(os.path.join(cwd, "CLAUDE.md")),
        "skills": _skills_stat(os.path.join(cwd, ".claude", "skills")),
        "mcp_json": _stat(os.path.join(cwd, ".mcp.json")),
        "project_settings": [_stat(os.path.join(cwd, ".claude", "settings.json")),
                             _stat(os.path.join(cwd, ".claude", "settings.local.json"))],
        "user_settings": _stat(os.path.join(conf_dir, "settings.json")),
        # NOT the credentials file: Claude Code rewrites it on every run, so its stat changes every turn and no warm
        # process would ever be reused (0.387.0). A sign-in or sign-out through Javis drops the Claude slots instead
        # (warm_pool.drop_kind in main's /claude/login* and /claude/logout).
        "strict_mcp": bool(getattr(opts, "strict_mcp_config", False)),
    }


def _warm_options(cli, opts, handle: ClaudeHandle):
    """The engine's own options, rerouted to the slot: lane key in the hub header, hooks and stderr via the handle."""
    import turn_context
    servers = getattr(opts, "mcp_servers", None)
    if isinstance(servers, dict) and isinstance(servers.get("javis"), dict):
        hub = dict(servers["javis"])
        if isinstance(hub.get("headers"), dict):
            hub["headers"] = {**hub["headers"], turn_context.HEADER: handle.lane.key}
            opts.mcp_servers = {**servers, "javis": hub}
    if getattr(opts, "hooks", None):
        from claude_agent_sdk import HookMatcher
        hooks = {}
        for event in opts.hooks:
            if event in ("PostToolUse", "PostToolUseFailure"):
                hooks[event] = [HookMatcher(matcher=None, hooks=[handle.steer_hook])]
        opts.hooks = hooks or None
    if getattr(opts, "stderr", None) is not None:
        opts.stderr = handle.on_stderr
    return opts


async def _open(opts, handle: ClaudeHandle):
    from claude_agent_sdk import ClaudeSDKClient
    client = ClaudeSDKClient(options=opts)
    handle.client = client
    # The SDK makes its reader task (and every hook and in-process tool task after it) at connect time, copying the
    # context of whoever connects. Connecting inside the lane's context makes them follow the lane.
    # ctx.run around create_task works on every Python (create_task(context=) needs 3.11).
    await handle.lane.context().run(asyncio.get_running_loop().create_task, client.connect())
    return handle


def _recipe(cli, opts, sysprompt_text: Optional[str]):
    """Reopen the same process later (prewarm) on the session it ended with. The prompt file of the turn is gone by
    then, so it is written again for the start-up and removed after."""
    import copy

    async def _again() -> ClaudeHandle:
        import turn_context
        o = copy.copy(opts)
        tmp = None
        extra = dict(getattr(o, "extra_args", None) or {})
        if "append-system-prompt-file" in extra and sysprompt_text is not None:
            tmp = cli._write_sysprompt_file(sysprompt_text)
            extra["append-system-prompt-file"] = tmp
            o.extra_args = extra
        handle = ClaudeHandle(None, turn_lane.Lane())
        handle.cli = cli
        o = _warm_options(cli, o, handle)
        try:
            return await _open(o, handle)
        except BaseException:
            await handle.close()
            raise
        finally:
            if tmp:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            handle.cli = None
    return _again


class _WarmStartFailed(Exception):
    """The warm process refused the message before the turn started: rerun the turn cold."""


async def query(cli, prompt, key: str) -> AsyncIterator[dict]:
    """One chat turn, on the conversation's warm `claude` when it has one that fits, else cold, keeping the process
    afterwards when the pool has room. Same events as `ClaudeSDK.query`."""
    if not key or not eligible(cli) or not cli.is_available():
        async for ev in cli.query(prompt):
            yield ev
        return
    try:
        async for ev in _query(cli, prompt, key, allow_warm=True):
            yield ev
    except _WarmStartFailed as e:
        print(f"[claude warm] the warm process failed before the turn started ({e}), running it cold", file=sys.stderr)
        async for ev in _query(cli, prompt, key, allow_warm=False):
            yield ev


def _options_and_fingerprint(cli):
    opts = cli._options()
    parts = fingerprint_parts(cli, opts)
    return opts, _hash_parts(parts), parts


async def _query(cli, prompt, key: str, allow_warm: bool) -> AsyncIterator[dict]:
    import claude_sdk_engine as eng
    import localefmt
    import turn_context
    from claude_agent_sdk import ResultMessage

    IDLE = eng.tran_watchdog("JAVIS_CLAUDE_IDLE_TIMEOUT", "0")
    TOOL_IDLE = eng.tran_watchdog("JAVIS_CLAUDE_TOOL_TIMEOUT", "3600")
    FIRST_IDLE = eng.tran_watchdog("JAVIS_CLAUDE_FIRST_TIMEOUT", "0")
    RESULT_IDLE = eng.tran_watchdog("JAVIS_CLAUDE_RESULT_TIMEOUT", "30")
    cli._sweep_stale_tmp()
    tran_init = eng.ap_tran_khoi_dong()
    cli._stderr_tail.clear()
    loop = asyncio.get_running_loop()
    # Off the loop: _options loads plugins and writes the prompt file, the fingerprint stats a few files.
    opts, fp, parts = await asyncio.to_thread(_options_and_fingerprint, cli)
    if cli.session_id and allow_warm:
        held = warm_pool.POOL.peek(key)
        if held is not None and held.fingerprint != fp and getattr(held.handle, "parts", None):
            print(f"[claude warm] {key[:12]}: config changed ({', '.join(changed_parts(held.handle.parts, parts))}),"
                  f" opening a new process", file=sys.stderr)
    slot = warm_pool.POOL.take(key, "claude", fp) if (cli.session_id and allow_warm) else None
    if slot is not None and not slot.handle.quiet():
        warm_pool.POOL.release(slot, keep=False)
        slot = None
    handle: Optional[ClaudeHandle] = None
    if slot is not None:
        handle = slot.handle
        cli._cleanup_tmp()     # the prompt file of this turn is not needed: the process is running already
    completion = eng._CompletionWatch(RESULT_IDLE if getattr(opts, "include_hook_events", False) else None)
    started = time.time()
    tools_running = 0
    got_any = False
    auth_race = False
    clean = False              # the turn reached its ResultMessage: the client is in a known state
    sysprompt_text = cli.system_prompt if not cli.system_prompt_raw else None
    try:
        try:
            import claude_token_gate
            nhan = await claude_token_gate.xep_hang()
            if nhan:
                print(f"[claude token] xếp hàng làm mới: {nhan}", file=sys.stderr)
        except Exception:
            pass
        if handle is None:
            handle = ClaudeHandle(None, turn_lane.Lane())
            handle.lane.attach()
            handle.cli = cli
            await _open(_warm_options(cli, opts, handle), handle)
        else:
            handle.lane.attach()
            handle.cli = cli
        client = handle.client
        with eng._LOCK:
            eng._ACTIVE[client] = (cli.tag, loop)
        try:
            if isinstance(prompt, list):
                blocks = prompt

                async def _one_message():
                    yield {"type": "user", "message": {"role": "user", "content": blocks}, "parent_tool_use_id": None}
                await client.query(_one_message())
            else:
                await client.query(prompt)
        except Exception as e:
            if slot is not None:
                raise _WarmStartFailed(f"{type(e).__name__}: {e}")
            raise
        yield {"type": "warm", "warm": slot is not None}
        agen = client.receive_response().__aiter__()
        while True:
            waiting_tool = tools_running > 0
            if waiting_tool:
                tran, ly_do = TOOL_IDLE, "tool"
            elif got_any:
                tran, ly_do = IDLE, "im"
            else:
                tran, ly_do = FIRST_IDLE, "dau"
            if completion.deadline is not None:
                con_lai = max(0.0, completion.deadline - loop.time())
                if tran is None or con_lai < tran:
                    tran, ly_do = con_lai, "ket"
            try:
                msg = await asyncio.wait_for(agen.__anext__(), timeout=tran)
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError:
                if ly_do == "ket":
                    print(f"[claude completion] tag={cli.tag} session={cli.session_id} "
                          f"end_turn without result after {RESULT_IDLE}s", file=sys.stderr)
                    yield {"type": "final", "content": completion.text,
                           "session_id": cli.session_id, "completion_recovered": True}
                    break
                if ly_do == "tool":
                    err = localefmt.chu(
                        f"Tool chạy quá {int(TOOL_IDLE)}s chưa xong - đã dừng để tránh treo server. "
                        f"(tăng JAVIS_CLAUDE_TOOL_TIMEOUT nếu tác vụ thật sự dài hơn, đặt 0 để bỏ hẳn trần)",
                        f"A tool ran over {int(TOOL_IDLE)}s without finishing - stopped to avoid hanging the server. "
                        f"(raise JAVIS_CLAUDE_TOOL_TIMEOUT if the job really takes longer, set 0 to remove the limit)")
                elif ly_do == "dau":
                    err = localefmt.chu(
                        f"Claude chưa trả lời gì sau {int(FIRST_IDLE)}s - đã dừng để tránh treo server. Hay gặp khi "
                        f"hội thoại đã rất dài: lượt đầu phải nạp lại toàn bộ ngữ cảnh nên lâu. Mở hội thoại mới "
                        f"thường hết ngay. (JAVIS_CLAUDE_FIRST_TIMEOUT=0 để bỏ hẳn trần này)",
                        f"Claude had not answered after {int(FIRST_IDLE)}s - stopped to avoid hanging the server. "
                        f"Common when the conversation is very long: the first turn must reload the whole context, "
                        f"which is slow. A new conversation usually fixes it. "
                        f"(JAVIS_CLAUDE_FIRST_TIMEOUT=0 removes this limit)")
                else:
                    err = localefmt.chu(
                        f"Claude đang trả lời rồi im {int(IDLE)}s - đã dừng để tránh treo server. "
                        f"(JAVIS_CLAUDE_IDLE_TIMEOUT=0 để bỏ hẳn trần này)",
                        f"Claude went silent for {int(IDLE)}s mid-answer - stopped to avoid hanging the server. "
                        f"(JAVIS_CLAUDE_IDLE_TIMEOUT=0 removes this limit)")
                try:
                    await client.interrupt()
                except Exception:
                    pass
                yield {"type": "error", "content": err}
                break
            got_any = True
            events, sid = eng.map_message(msg)
            if sid:
                if sid != cli.session_id and cli.javis_vault:
                    try:
                        import session_brain
                        session_brain.record(sid, cli.javis_vault)
                    except Exception:
                        pass
                cli.session_id = sid
            for ev in events:
                if ev.get("auth_refresh_race") or ev.get("dua_token"):
                    auth_race = True   # another process spent the refresh token: a new process reads the fresh file
                if ev["type"] == "tool_call":
                    tools_running += 1
                elif ev["type"] == "tool_result":
                    tools_running = max(0, tools_running - 1)
                elif ev.get("resume_failed"):
                    cli.session_id = None
                yield ev
            completion.observe(msg, tools_running, loop.time())
            if isinstance(msg, ResultMessage):
                # Reusable only in a known state: a good result, nothing still running in the background.
                clean = (not getattr(msg, "is_error", False) and bool(cli.session_id) and not auth_race
                         and not completion.tasks and not completion.untracked_work)
                break
    except _WarmStartFailed:
        clean = False
        raise
    except Exception as e:
        chan_doan = None
        if "Control request timeout: initialize" in str(e):
            chan_doan = cli._startup_diagnosis(started)
            print(f"[claude init timeout] tag={cli.tag} sau={time.time() - started:.0f}s chan_doan={chan_doan}",
                  file=sys.stderr)
        clean = False
        yield {"type": "error", "content": eng.loi_de_hieu(e, tran_init, chan_doan)}
    finally:
        if handle is not None and handle.client is not None:
            with eng._LOCK:
                eng._ACTIVE.pop(handle.client, None)
        if handle is not None:
            handle.lane.detach()
            handle.cli = None
        if handle is not None:
            if clean:
                opts.resume = cli.session_id
                parts_now = await asyncio.to_thread(fingerprint_parts, cli, opts)
                fp_now = _hash_parts(parts_now)
                handle.parts = parts_now
                if slot is not None:
                    slot.recipe = _recipe(cli, opts, sysprompt_text)   # a later prewarm resumes this session
                    warm_pool.POOL.release(slot, fingerprint=fp_now)
                else:
                    new = warm_pool.POOL.admit(key, "claude", fp_now, handle,
                                               recipe=_recipe(cli, opts, sysprompt_text))
                    if new is not None:
                        warm_pool.POOL.release(new)
                    else:
                        await handle.close()
            elif slot is not None:
                warm_pool.POOL.release(slot, keep=False)
            else:
                await handle.close()
        cli._cleanup_tmp()
