#!/usr/bin/env python3
"""Fail-closed PreToolUse hook for Antigravity CLI team gate."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def _deny(reason: str) -> int:
    msg = str(reason or "Tool call denied by Javis team gate").strip()
    sys.stdout.write(json.dumps({"decision": "deny", "reason": msg}, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


def _load_cfg(argv: list[str]) -> tuple[str, str, str, str, float]:
    url = ""
    cfg_path = os.environ.get("JAVIS_AGY_GATE_CFG") or ""
    if len(argv) >= 2 and str(argv[1]).startswith(("http://", "https://")):
        url = str(argv[1]).strip()
        if len(argv) >= 3 and argv[2]:
            cfg_path = str(argv[2]).strip()
    elif len(argv) >= 2 and argv[1]:
        cfg_path = str(argv[1]).strip()

    cfg: dict = {}
    if cfg_path:
        with open(cfg_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            raise ValueError("Invalid gate config")
        cfg = loaded

    if not url:
        url = str(cfg.get("url") or os.environ.get("JAVIS_AGY_GATE_URL") or "").strip()
    token = str(
        cfg.get("token")
        or os.environ.get("JAVIS_AGY_GATE_TOKEN")
        or os.environ.get("JAVIS_HUB_TOKEN")
        or ""
    ).strip()
    gate_id = str(cfg.get("gate_id") or os.environ.get("JAVIS_AGY_GATE_ID") or "").strip()
    turn_key = str(cfg.get("turn_key") or os.environ.get("JAVIS_TURN_KEY") or "").strip()
    try:
        timeout = float(cfg.get("timeout") or os.environ.get("JAVIS_AGY_GATE_TIMEOUT") or 660.0)
    except Exception:
        timeout = 660.0
    if timeout <= 0:
        timeout = 660.0
    return url, token, gate_id, turn_key, timeout


def _extract_tool(payload: dict) -> tuple[str, dict]:
    tc = payload.get("toolCall")
    if isinstance(tc, dict):
        name = str(tc.get("name") or tc.get("toolName") or "").strip()
        args = tc.get("args")
        if args is None:
            args = tc.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {"raw": args}
        return name, args if isinstance(args, dict) else {}

    ti = payload.get("tool_info")
    if isinstance(ti, dict):
        name = str(ti.get("name") or payload.get("tool_name") or "").strip()
        args = ti.get("parameters") or ti.get("args") or {}
        return name, args if isinstance(args, dict) else {}

    name = str(payload.get("tool_name") or payload.get("tool") or payload.get("name") or "").strip()
    args = payload.get("tool_input") or payload.get("input") or payload.get("args") or {}
    return name, args if isinstance(args, dict) else {}


def _open_url(req: urllib.request.Request, url: str, timeout: float):
    host = (urllib.parse.urlsplit(url).hostname or "").strip().lower()
    if host in ("127.0.0.1", "localhost", "::1"):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(req, timeout=timeout)
    return urllib.request.urlopen(req, timeout=timeout)


def main() -> int:
    try:
        raw_stdin = sys.stdin.read()
        payload = json.loads(raw_stdin) if raw_stdin.strip() else {}
    except Exception as exc:
        return _deny(f"Invalid PreToolUse payload: {exc}")

    if not isinstance(payload, dict):
        return _deny("PreToolUse payload must be a JSON object")

    try:
        url, token, gate_id, turn_key, timeout = _load_cfg(sys.argv)
    except Exception as exc:
        return _deny(f"Missing or invalid team gate config: {exc}")

    if not url or not token:
        return _deny("Missing team gate URL or token")

    tool_name, tool_input = _extract_tool(payload)
    if not tool_name:
        return _deny("Missing tool name in PreToolUse payload")

    body = json.dumps(
        {
            "gate_id": gate_id,
            "tool": tool_name,
            "input": tool_input,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    if turn_key:
        headers["X-Javis-Turn"] = turn_key

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with _open_url(req, url, timeout) as resp:
            resp_raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode("utf-8", errors="replace").strip()
            err_json = json.loads(err_body)
            reason = err_json.get("reason") or err_json.get("error") or err_json.get("detail") or err_body
        except Exception:
            reason = f"Team gate HTTP {exc.code}"
        return _deny(str(reason or f"Team gate HTTP {exc.code}"))
    except Exception as exc:
        return _deny(f"Team gate unavailable: {exc}")

    try:
        result = json.loads(resp_raw)
    except Exception as exc:
        return _deny(f"Invalid team gate response: {exc}")

    if not isinstance(result, dict):
        return _deny("Team gate response must be a JSON object")

    decision = str(result.get("decision") or "").strip().lower()
    if decision == "allow" or (not decision and result.get("allow") is True):
        sys.stdout.write(json.dumps({"decision": "allow"}, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        return 0

    reason = str(result.get("reason") or "Tool call denied by Javis team gate").strip()
    return _deny(reason)


if __name__ == "__main__":
    raise SystemExit(main())
