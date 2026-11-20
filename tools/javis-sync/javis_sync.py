#!/usr/bin/env python3
"""Javis Sync: save every Claude Code and Codex conversation into Javis, automatically.

The Javis Gate tools only save what an outside AI chooses to send, and a coding agent busy writing code almost
never calls them. This script runs on the machine where Claude Code or Codex runs:

- as a Claude Code **Stop hook**: after each answer it reads the session transcript and sends the turns it has not
  sent yet (the owner's prompt and the agent's final answer, not the tool calls in between);
- as the Codex **notify** program: Codex calls it after each turn with the prompt and the last answer.

Each turn goes to `POST /chat/external` on Javis, which saves it into one Javis conversation per session
("From Claude Code: <project>: <first prompt>"), through the normal save path: History, memory/conversations and the
learning queue. Javis runs no model for it.

Setup, once per machine (Python 3.8+, standard library only):

    python3 javis_sync.py install --url https://your-javis.example.com --token jvs_...

The token comes from Javis: Integrations page, tab API tokens (scope "chat" is enough). `install` copies this file
to ~/.javis-sync/, saves the URL and token there (file mode 600), adds the Stop hook to ~/.claude/settings.json and
the notify line to ~/.codex/config.toml (an existing Codex notify program keeps running: it is chained). Other
commands: `status`, `uninstall`. Skip one shell: JAVIS_SYNC_OFF=1. Skip folders: "exclude" in the config file.

A hook must never break the agent: every failure is logged to ~/.javis-sync/sync.log and the script exits 0. Turns
that could not be sent are kept and sent on the next run; Javis skips any turn it already has.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HOME = Path(os.environ.get("JAVIS_SYNC_HOME") or (Path.home() / ".javis-sync"))
CONFIG = HOME / "config.json"
STATE = HOME / "state.json"
LOG = HOME / "sync.log"
INSTALLED_SCRIPT = HOME / "javis_sync.py"
CLAUDE_SETTINGS = Path(os.environ.get("JAVIS_SYNC_CLAUDE_SETTINGS") or (Path.home() / ".claude" / "settings.json"))
CODEX_CONFIG = Path(os.environ.get("JAVIS_SYNC_CODEX_CONFIG")
                    or (Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex")) / "config.toml"))

TIMEOUT_S = 5            # per request; a hook must not hold the agent up
BACKOFF_S = 60           # after a failed send, skip the network for this long (Javis down = no 5 s wait per turn)
BATCH = 50               # turns per request (server limit)
MAX_TEXT = 8000          # the server cuts at the same length; cutting here keeps requests small
MAX_PENDING = 300        # Codex turns kept while Javis is unreachable
MAX_LOG_BYTES = 200_000
MARK = "javis_sync.py"   # how install/uninstall recognise our own hook entries

_INTERRUPTED = ("[Request interrupted by user", "[Request cancelled")
_LOCAL_CMD = ("<local-command-stdout>", "<local-command-stderr>", "<bash-stdout>", "<bash-stderr>")


# ─────────────────────────── small helpers ───────────────────────────

def log(msg: str) -> None:
    try:
        HOME.mkdir(parents=True, exist_ok=True)
        if LOG.exists() and LOG.stat().st_size > MAX_LOG_BYTES:
            LOG.replace(LOG.with_suffix(".log.1"))
        with LOG.open("a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg.rstrip() + "\n")
    except Exception:  # noqa: BLE001 - logging must never fail the hook
        pass


def read_json(path: Path, default):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError):
        return default


def write_json(path: Path, data, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if private:
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
    tmp.replace(path)


def load_config() -> dict:
    cfg = read_json(CONFIG, {})
    if os.environ.get("JAVIS_SYNC_URL"):
        cfg["url"] = os.environ["JAVIS_SYNC_URL"]
    if os.environ.get("JAVIS_SYNC_TOKEN"):
        cfg["token"] = os.environ["JAVIS_SYNC_TOKEN"]
    return cfg


def clip(text: str) -> str:
    text = str(text or "").strip()
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT].rstrip() + f"\n\n[... {len(text) - MAX_TEXT} more characters]"


def excluded(cfg: dict, cwd: str) -> bool:
    if os.environ.get("JAVIS_SYNC_OFF", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    here = os.path.normcase(os.path.abspath(cwd or "."))
    for item in cfg.get("exclude") or []:
        root = os.path.normcase(os.path.abspath(os.path.expanduser(str(item))))
        if here == root or here.startswith(root.rstrip(os.sep) + os.sep):
            return True
    return False


def project_name(cwd: str) -> str:
    return os.path.basename(os.path.normpath(cwd or "")) or ""


# ─────────────────────────── talking to Javis ───────────────────────────

class SendError(Exception):
    pass


def post(cfg: dict, body: dict) -> dict:
    url = str(cfg.get("url") or "").rstrip("/")
    if not url:
        raise SendError("no Javis URL configured (run: javis_sync.py install --url ... --token ...)")
    headers = {"Content-Type": "application/json", "User-Agent": "javis-sync/1"}
    if cfg.get("token"):
        headers["Authorization"] = "Bearer " + str(cfg["token"])
    req = urllib.request.Request(url + "/chat/external", data=json.dumps(body).encode("utf-8"), headers=headers,
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8") or "{}").get("error") or ""
        except Exception:  # noqa: BLE001
            detail = ""
        hint = " (check the API token)" if e.code == 401 else ""
        raise SendError(f"HTTP {e.code}{hint}: {detail}".rstrip(": "))
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise SendError(f"cannot reach {url}: {e}")


def send_turns(cfg: dict, state: dict, source: str, session: str, project: str, turns: list) -> bool:
    """Send turns in batches. True when Javis has all of them (saved now or before)."""
    if not turns:
        return True
    if time.time() - float(state.get("last_fail") or 0) < BACKOFF_S:
        return False
    try:
        for i in range(0, len(turns), BATCH):
            out = post(cfg, {"source": source, "session": session, "project": project, "turns": turns[i:i + BATCH]})
            if not out.get("ok"):
                raise SendError(str(out.get("error") or "Javis refused the turns"))
    except SendError as e:
        state["last_fail"] = time.time()
        log(f"{source} {session[:12]}: {e}")
        return False
    state.pop("last_fail", None)
    return True


# ─────────────────────────── Claude Code transcript ───────────────────────────

def _blocks(content) -> list:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [b for b in content or [] if isinstance(b, dict)]


def _prompt_text(entry: dict):
    """The owner's prompt in a transcript line, or None when the line is not one (tool result, meta, summary...)."""
    if entry.get("type") != "user" or entry.get("isSidechain") or entry.get("isMeta") \
            or entry.get("isCompactSummary") or entry.get("toolUseResult") is not None:
        return None
    blocks = _blocks((entry.get("message") or {}).get("content"))
    if any(b.get("type") == "tool_result" for b in blocks):
        return None
    text = "\n".join(str(b.get("text") or "") for b in blocks if b.get("type") == "text").strip()
    images = sum(1 for b in blocks if b.get("type") == "image")
    if not text and not images:
        return None
    if text.startswith(_LOCAL_CMD) or text.startswith(_INTERRUPTED):
        return None
    name = re.search(r"<command-name>(.*?)</command-name>", text, re.S)
    if name:   # a slash command: keep it as the owner typed it
        args = re.search(r"<command-args>(.*?)</command-args>", text, re.S)
        text = (name.group(1).strip() + " " + (args.group(1).strip() if args else "")).strip()
    if images:
        text = (text + "\n\n" if text else "") + f"[{images} image(s) attached]"
    return text


def parse_claude(lines: list) -> list:
    """Turns from transcript lines: [{"id", "user", "assistant"}]. The answer is the text the agent wrote after its
    last tool call of the turn (its final answer), or its last text when it ended on a tool call."""
    turns, cur, tail, last_text = [], None, [], ""

    def close():
        if cur is not None:
            cur["assistant"] = clip("\n\n".join(tail) if tail else last_text)
            if cur["user"] or cur["assistant"]:
                turns.append(cur)

    for raw in lines:
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("isSidechain"):
            continue
        prompt = _prompt_text(entry)
        if prompt is not None:
            close()
            cur, tail, last_text = {"id": str(entry.get("uuid") or ""), "user": clip(prompt), "assistant": ""}, [], ""
            continue
        if entry.get("type") == "assistant":
            if cur is None:   # the agent went on after the last saved turn (a hook or a background task woke it)
                cur, tail, last_text = {"id": str(entry.get("uuid") or ""), "user": "(continued)", "assistant": ""}, [], ""
            for b in _blocks((entry.get("message") or {}).get("content")):
                if b.get("type") == "text" and str(b.get("text") or "").strip():
                    tail.append(str(b["text"]).strip())
                    last_text = tail[-1]
                elif b.get("type") == "tool_use":
                    tail = []
        elif entry.get("type") == "user" and cur is not None:
            tail = []      # a tool result: the text before it was not the final answer
    close()
    return [t for t in turns if t["id"]]


def run_claude(cfg: dict) -> None:
    try:
        hook = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        hook = {}
    session = str(hook.get("session_id") or "")
    path = Path(str(hook.get("transcript_path") or ""))
    cwd = str(hook.get("cwd") or os.getcwd())
    if not session or not path.is_file() or excluded(cfg, cwd):
        return
    state = read_json(STATE, {})
    sessions = state.setdefault("claude", {})
    mine = sessions.get(session) or {}
    offset = int(mine.get("offset") or 0)
    size = path.stat().st_size
    if offset > size:   # the file was rewritten: start over, Javis skips what it has
        offset = 0
    with path.open("rb") as f:
        f.seek(offset)
        data = f.read()
    end = data.rfind(b"\n")
    if end < 0:
        return
    chunk = data[:end + 1]
    turns = parse_claude(chunk.decode("utf-8", "replace").splitlines())
    sent_upto = offset + len(chunk)
    if turns and not turns[-1]["assistant"]:
        # The newest turn has no answer on disk yet (the transcript may lag the hook by a moment, or the owner pressed
        # Esc): keep it for the next run, which sees the answer or the next prompt.
        at = chunk.rfind(turns[-1]["id"].encode("utf-8"))
        if at >= 0:
            sent_upto = offset + chunk.rfind(b"\n", 0, at) + 1
            turns = turns[:-1]
    if send_turns(cfg, state, "claude-code", session, project_name(cwd), turns):
        mine["offset"] = sent_upto
    mine["seen_at"] = time.time()
    sessions[session] = mine
    # forget sessions untouched for 30 days
    for k in [k for k, v in sessions.items() if time.time() - float((v or {}).get("seen_at") or 0) > 30 * 86400]:
        sessions.pop(k, None)
    write_json(STATE, state)


# ─────────────────────────── Codex notify ───────────────────────────

def run_codex(cfg: dict, argv: list) -> None:
    raw = argv[-1] if argv else ""
    try:
        event = json.loads(raw) if raw else {}
    except ValueError:
        event = {}
    chain = cfg.get("codex_chain") or []
    if chain and raw:   # the notify program the owner had before keeps running
        try:
            import subprocess
            subprocess.Popen(list(chain) + [raw], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except Exception as e:  # noqa: BLE001
            log(f"codex chain {chain[:1]}: {e}")
    state = read_json(STATE, {})
    pending = state.setdefault("codex_pending", [])
    if isinstance(event, dict) and event.get("type") == "agent-turn-complete":
        cwd = str(event.get("cwd") or os.getcwd())
        if not excluded(cfg, cwd):
            prompts = event.get("input-messages") or event.get("input_messages") or []
            if isinstance(prompts, str):
                prompts = [prompts]
            turn = {"id": str(event.get("turn-id") or event.get("turn_id") or f"t{time.time():.6f}"),
                    "user": clip("\n\n".join(str(p) for p in prompts if p)),
                    "assistant": clip(event.get("last-assistant-message") or event.get("last_assistant_message") or "")}
            session = str(event.get("thread-id") or event.get("thread_id") or event.get("session-id") or "codex")
            if turn["user"] or turn["assistant"]:
                pending.append({"session": session, "project": project_name(cwd), "turn": turn})
    del pending[:-MAX_PENDING]
    # send everything waiting, grouped by session, oldest first
    left = []
    groups: dict = {}
    for item in pending:
        groups.setdefault((item.get("session") or "codex", item.get("project") or ""), []).append(item)
    for (session, project), items in groups.items():
        if not send_turns(cfg, state, "codex", session, project, [i["turn"] for i in items]):
            left.extend(items)
    state["codex_pending"] = left
    write_json(STATE, state)


# ─────────────────────────── install / uninstall ───────────────────────────

def _python() -> str:
    return sys.executable or "python3"


def _quote(s: str) -> str:
    return '"' + s.replace('"', '\\"') + '"' if re.search(r'[\s"\'$`\\]', s) or os.name == "nt" else s


def claude_command() -> str:
    return f"{_quote(_python())} {_quote(INSTALLED_SCRIPT.as_posix())} claude"


def install_claude() -> str:
    settings = read_json(CLAUDE_SETTINGS, {}) if CLAUDE_SETTINGS.exists() else {}
    if CLAUDE_SETTINGS.exists() and not settings and CLAUDE_SETTINGS.read_text(encoding="utf-8").strip():
        return f"Claude Code: skipped, {CLAUDE_SETTINGS} is not valid JSON. Fix it and run install again."
    hooks = settings.setdefault("hooks", {})
    stop = [g for g in (hooks.get("Stop") or []) if isinstance(g, dict)]
    for g in stop:
        g["hooks"] = [h for h in (g.get("hooks") or []) if MARK not in str((h or {}).get("command") or "")]
    stop = [g for g in stop if g.get("hooks")]
    stop.append({"hooks": [{"type": "command", "command": claude_command(), "timeout": 30}]})
    hooks["Stop"] = stop
    if CLAUDE_SETTINGS.exists():
        shutil.copy2(CLAUDE_SETTINGS, CLAUDE_SETTINGS.with_name(CLAUDE_SETTINGS.name + ".bak"))
    write_json(CLAUDE_SETTINGS, settings)
    return f"Claude Code: Stop hook added to {CLAUDE_SETTINGS}"


_TABLE_RE = re.compile(r"^\s*\[")
_NOTIFY_RE = re.compile(r"^\s*notify\s*=")


def _split_notify(text: str):
    """(lines without the top-level notify key, the notify value text or ""). Only keys before the first [table]
    are top level; a multi-line array runs until its closing bracket."""
    lines = text.splitlines()
    out, value, i, top = [], "", 0, True
    while i < len(lines):
        line = lines[i]
        if _TABLE_RE.match(line):
            top = False
        if top and _NOTIFY_RE.match(line):
            parts = [line.split("=", 1)[1]]
            depth = parts[0].count("[") - parts[0].count("]")
            while depth > 0 and i + 1 < len(lines):
                i += 1
                parts.append(lines[i])
                depth += lines[i].count("[") - lines[i].count("]")
            value = "\n".join(parts).strip()
            i += 1
            continue
        out.append(line)
        i += 1
    return out, value


def _parse_array(value: str) -> list:
    if not value:
        return []
    try:
        import tomllib  # Python 3.11+
        return list(tomllib.loads("v = " + value)["v"])
    except Exception:  # noqa: BLE001 - older Python: plain quoted strings, the common form
        return [json.loads('"' + a + '"') if a or not b else b
                for a, b in re.findall(r'"((?:[^"\\]|\\.)*)"|\'([^\']*)\'', value)]


def install_codex(cfg: dict) -> str:
    text = CODEX_CONFIG.read_text(encoding="utf-8") if CODEX_CONFIG.exists() else ""
    lines, old = _split_notify(text)
    old_argv = [str(x) for x in _parse_array(old)]
    if old_argv and not any(MARK in a for a in old_argv):
        cfg["codex_chain"] = old_argv
    argv = [_python(), INSTALLED_SCRIPT.as_posix(), "codex"]
    new = "notify = [" + ", ".join(json.dumps(a) for a in argv) + "]  # Javis Sync"
    if CODEX_CONFIG.exists():
        shutil.copy2(CODEX_CONFIG, CODEX_CONFIG.with_name(CODEX_CONFIG.name + ".bak"))
    CODEX_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CODEX_CONFIG.write_text("\n".join([new] + lines).rstrip("\n") + "\n", encoding="utf-8")
    chain = cfg.get("codex_chain") or []
    chained = f" (your previous notify program still runs: {chain[0]})" if chain else ""
    return f"Codex: notify set in {CODEX_CONFIG}{chained}"


def uninstall(cfg: dict) -> list:
    done = []
    if CLAUDE_SETTINGS.exists():
        settings = read_json(CLAUDE_SETTINGS, {})
        stop = (settings.get("hooks") or {}).get("Stop") or []
        if any(MARK in json.dumps(g) for g in stop):
            for g in stop:
                g["hooks"] = [h for h in (g.get("hooks") or []) if MARK not in str((h or {}).get("command") or "")]
            settings["hooks"]["Stop"] = [g for g in stop if g.get("hooks")]
            if not settings["hooks"]["Stop"]:
                settings["hooks"].pop("Stop")
            write_json(CLAUDE_SETTINGS, settings)
            done.append(f"Claude Code: Stop hook removed from {CLAUDE_SETTINGS}")
    if CODEX_CONFIG.exists():
        lines, old = _split_notify(CODEX_CONFIG.read_text(encoding="utf-8"))
        if MARK in old:
            chain = cfg.get("codex_chain") or []
            head = ["notify = [" + ", ".join(json.dumps(a) for a in chain) + "]"] if chain else []
            CODEX_CONFIG.write_text("\n".join(head + lines).rstrip("\n") + "\n", encoding="utf-8")
            done.append(f"Codex: notify removed from {CODEX_CONFIG}" + (" (previous program restored)" if chain else ""))
    return done or ["Nothing to remove."]


def _arg(argv: list, name: str) -> str:
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return ""


def cmd_install(argv: list) -> int:
    cfg = read_json(CONFIG, {})
    url = (_arg(argv, "--url") or cfg.get("url") or "").rstrip("/")
    token = _arg(argv, "--token") or cfg.get("token") or ""
    if not url:
        print("Usage: javis_sync.py install --url https://your-javis --token jvs_... [--claude] [--codex]")
        return 2
    cfg.update({"url": url, "token": token})
    cfg.setdefault("exclude", [])
    if "--no-check" not in argv:
        try:
            post(cfg, {"check": True})
        except SendError as e:
            print(f"Javis did not accept the connection: {e}\nNothing was installed. Fix the URL or token, or pass "
                  "--no-check to install anyway.")
            return 1
    want_claude = "--claude" in argv or "--codex" not in argv
    want_codex = "--codex" in argv or "--claude" not in argv
    HOME.mkdir(parents=True, exist_ok=True)
    if Path(__file__).resolve() != INSTALLED_SCRIPT.resolve():
        shutil.copy2(Path(__file__).resolve(), INSTALLED_SCRIPT)
    report = [f"Connected to {url}. Script and settings saved in {HOME}"]
    if want_claude:
        report.append(install_claude())
    if want_codex:
        report.append(install_codex(cfg))
    write_json(CONFIG, cfg, private=True)
    report.append("Done. From the next answer on, each Claude Code / Codex turn appears in Javis History as "
                  "'From Claude Code: ...' or 'From Codex: ...'. Open sessions pick the hook up after a restart.")
    print("\n".join(report))
    return 0


def cmd_status() -> int:
    cfg = load_config()
    print(f"Config: {CONFIG} ({'found' if CONFIG.exists() else 'missing'})")
    print(f"Javis:  {cfg.get('url') or '(not set)'}  token: {'set' if cfg.get('token') else 'not set'}")
    settings = read_json(CLAUDE_SETTINGS, {})
    print("Claude Code hook: " + ("installed" if MARK in json.dumps(settings.get("hooks") or {}) else "not installed"))
    codex = CODEX_CONFIG.read_text(encoding="utf-8") if CODEX_CONFIG.exists() else ""
    print("Codex notify:     " + ("installed" if MARK in _split_notify(codex)[1] else "not installed"))
    state = read_json(STATE, {})
    print(f"Codex turns waiting to send: {len(state.get('codex_pending') or [])}")
    try:
        post(cfg, {"check": True})
        print("Connection: OK")
        return 0
    except SendError as e:
        print(f"Connection: FAILED, {e}")
        return 1


def main(argv: list) -> int:
    cmd = argv[0] if argv else ""
    if cmd == "install":
        return cmd_install(argv[1:])
    if cmd == "status":
        return cmd_status()
    if cmd == "uninstall":
        print("\n".join(uninstall(read_json(CONFIG, {}))))
        return 0
    if cmd in ("claude", "codex"):
        try:
            cfg = load_config()
            if cmd == "claude":
                run_claude(cfg)
            else:
                run_codex(cfg, argv[1:])
        except Exception as e:  # noqa: BLE001 - a hook must never break the agent
            log(f"{cmd}: {type(e).__name__}: {e}")
        return 0
    print(__doc__)
    return 0 if cmd in ("", "-h", "--help", "help") else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
