"""A stdio MCP server that is slow to start, like `npx -y <package>` on its first run.

    python _slow_start_mcp_server.py --delay 2.0 --marker <dir> [--hang-list]

Used by the cold-install tests. On start it writes `<marker>/started.<pid>`, then sleeps `--delay`
seconds without reading stdin (npx is still downloading, nothing answers yet), writes
`<marker>/ready.<pid>` and serves NDJSON JSON-RPC: initialize, tools/list (one tool "echo"),
tools/call. With --hang-list it answers initialize but never answers tools/list, the shape of a
server that is really stuck in the middle of a request.
"""
import argparse
import json
import os
import sys
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=0.0)
    ap.add_argument("--marker", required=True)
    ap.add_argument("--hang-list", action="store_true")
    a = ap.parse_args()
    pid = os.getpid()
    open(os.path.join(a.marker, f"started.{pid}"), "w").close()
    time.sleep(a.delay)
    open(os.path.join(a.marker, f"ready.{pid}"), "w").close()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        method, mid = msg.get("method"), msg.get("id")
        if mid is None:
            continue
        if method == "initialize":
            result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                      "serverInfo": {"name": "slow-start", "version": "1"}}
        elif method == "tools/list":
            if a.hang_list:
                continue
            result = {"tools": [{"name": "echo", "description": "Echo a text back",
                                 "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}}}]}
        elif method == "tools/call":
            text = ((msg.get("params") or {}).get("arguments") or {}).get("text", "")
            result = {"content": [{"type": "text", "text": f"echo: {text}"}]}
        else:
            print(json.dumps({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "no"}}), flush=True)
            continue
        print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}), flush=True)


if __name__ == "__main__":
    main()
