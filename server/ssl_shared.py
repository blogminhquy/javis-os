"""ssl_shared.py - one SSL context for every httpx client the server makes (2026-11-09).

Why. httpx 0.27 builds a brand-new SSL context for EACH client: `ssl.create_default_context()` plus loading the whole
certifi bundle, all of it on the thread that creates the client. The server creates clients in about 130 places, most
of them inside `async def` code, so that work ran on the event loop. On the owner's VPS, with the GIL busy, one of them
froze every request for 1.8 s (/health/loop: main.py `_load_community_announcements`, inside
`httpx.AsyncClient(timeout=8)` -> `create_ssl_context`).

What. `install()` wraps httpx's `create_ssl_context` so the DEFAULT case (verify=True, no client certificate), which is
what nearly every call site uses, returns one context built once and then shared. httpx itself recommends reusing a
context; an `ssl.SSLContext` is safe to share between connections and threads. Anything else (verify=False, a custom
CA path or context, a client certificate) goes to httpx untouched. The key includes trust_env, http2 and the
SSL_CERT_FILE / SSL_CERT_DIR variables, so a change to any of them gets its own context. `warm()` builds the shared
context, and is called on a worker thread at start-up so even the first client does not pay on the loop.

If httpx changes its internals (the hook is not found, or its signature moves), `install()` does nothing and httpx
keeps working as before.
"""
from __future__ import annotations

import os
import threading

_CACHE: dict = {}
_LOCK = threading.Lock()
_installed = False


def _key(trust_env, http2):
    return (bool(trust_env), bool(http2), os.environ.get("SSL_CERT_FILE"), os.environ.get("SSL_CERT_DIR"))


def install() -> bool:
    """Wrap httpx's context factory once. Returns True when the shared context is in use."""
    global _installed
    if _installed:
        return True
    try:
        import httpx._config as cfg
        import httpx._transports.default as transports
    except Exception:  # noqa: BLE001
        return False
    original = getattr(transports, "create_ssl_context", None)
    if original is None or getattr(original, "_javis_shared", False):
        return bool(original)

    def create_ssl_context(cert=None, verify=True, trust_env=True, http2=False, *args, **kwargs):
        if args or kwargs or cert is not None or verify is not True:
            return original(cert, verify, trust_env, http2, *args, **kwargs)
        key = _key(trust_env, http2)
        ctx = _CACHE.get(key)
        if ctx is None:
            with _LOCK:
                ctx = _CACHE.get(key)
                if ctx is None:
                    ctx = original(cert=None, verify=True, trust_env=trust_env, http2=http2)
                    _CACHE[key] = ctx
        return ctx

    create_ssl_context._javis_shared = True
    transports.create_ssl_context = create_ssl_context
    if getattr(cfg, "create_ssl_context", None) is original:
        cfg.create_ssl_context = create_ssl_context
    _installed = True
    return True


def warm() -> None:
    """Build the shared context now (call on a worker thread at start-up)."""
    if not install():
        return
    try:
        import httpx._transports.default as transports
        transports.create_ssl_context()
    except Exception:  # noqa: BLE001 - a failure here only means the first client builds it instead
        pass
