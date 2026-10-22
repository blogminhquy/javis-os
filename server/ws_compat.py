"""WebSocket compression off for every launch path (0.197.1).

Why. Safari drops the dashboard's live socket for minutes while Chrome, open on the same server at the same moment,
stays connected (customer report 17/10/2026). uvicorn negotiates permessage-deflate by default, and Safari's
implementation of it fails on some compressed messages: the browser closes the socket with a protocol error (Apple
developer forums threads 744018 and 706961). The message that trips it is sent again on every reconnect (the `hello`
snapshot, the next streamed chunk), so the page reconnects into the same failure over and over. Without compression
the frames are plain and every browser reads them.

How. uvicorn is started in several ways: the Docker image (`python -m uvicorn` CLI), install.sh's systemd unit and
nohup line, update.sh, launchd, and `python main.py`. Units already written on users' machines are not rewritten by an
update, so a launch flag alone would miss them. uvicorn reads `config.ws_per_message_deflate` each time a WebSocket
connection is built, and main.py is imported before the first connection, so `disable_deflate()` (called at main.py
import) turns the setting into a read-only False on the Config class: a data descriptor on the class wins over the
value uvicorn's __init__ stored on the instance. The cost is bandwidth only: chat frames are small text deltas.

`JAVIS_WS_DEFLATE=1` keeps uvicorn's compression (for a setup that needs it and has no Safari users).

0.274.0: `import main` no longer loads uvicorn for this (about 40 ms of every start, on a check that sits at its
ceiling). Every launch path but `python main.py` has loaded uvicorn before main, so the patch applies at once; otherwise
a one-shot import hook applies it the moment `uvicorn.config` loads, before any Config exists.
"""
from __future__ import annotations

import importlib.abc
import importlib.machinery
import os
import sys


def wanted() -> bool:
    """True when the operator asked to keep WebSocket compression on."""
    return str(os.environ.get("JAVIS_WS_DEFLATE", "")).strip().lower() in ("1", "true", "yes", "on")


def disable_deflate() -> bool:
    """Make every uvicorn Config report ws_per_message_deflate=False. Returns True when applied."""
    if wanted():
        return False
    mod = sys.modules.get("uvicorn.config")
    if mod is not None:
        _patch(mod)
    elif not any(isinstance(f, _PatchOnLoad) for f in sys.meta_path):
        sys.meta_path.insert(0, _PatchOnLoad())
    return True


def _patch(uv_config) -> None:
    uv_config.Config.ws_per_message_deflate = property(lambda self: False, lambda self, value: None)


class _PatchOnLoad(importlib.abc.MetaPathFinder):
    """Patches `uvicorn.config` right after it is executed, then removes itself."""

    def find_spec(self, name, path=None, target=None):
        if name != "uvicorn.config":
            return None
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        if spec is None or spec.loader is None:
            return None
        run = spec.loader.exec_module

        def exec_module(module):
            run(module)
            _patch(module)
            if self in sys.meta_path:
                sys.meta_path.remove(self)
        spec.loader.exec_module = exec_module
        return spec
