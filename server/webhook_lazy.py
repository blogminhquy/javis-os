"""webhook_lazy.py - the webhook routes, registered at start without loading the webhook platform (0.274.0).

`import main` must stay light (tests/python/test_khoi_dong_nhe.py): the webhook platform is seven modules and 22
FastAPI routes, about 10 ms at every start, on a check that sits close to its ceiling. Here every webhook route is a
plain Starlette route whose endpoint loads `webhook_triggers`, builds the feature once and hands the request to the
real handler. The platform loads at the server's startup event (its worker starts there anyway), or at the first
webhook request if that comes first, so nothing waits in practice.

ROUTES must list the feature's routes in the same order with the same names: `test_webhook_spec_review` compares them.
"""
from __future__ import annotations

import threading
from typing import Any

ROUTES = (
    ("/hooks/{hook_id}", "POST", "hooks_receive"),
    ("/webhooks", "GET", "webhooks_list"),
    ("/webhooks", "POST", "webhooks_create"),
    ("/webhooks/update", "POST", "webhooks_update"),
    ("/webhooks/pause", "POST", "webhooks_pause"),
    ("/webhooks/rotate", "POST", "webhooks_rotate"),
    ("/webhooks/delete", "POST", "webhooks_delete"),
    ("/webhooks/test", "POST", "webhooks_test"),
    ("/webhooks/events", "GET", "webhooks_events"),
    ("/webhooks/events/export", "GET", "webhooks_events_export"),
    ("/webhooks/health", "GET", "webhooks_health"),
    ("/webhooks/audit", "GET", "webhooks_audit"),
    ("/webhooks/events/{event_id}", "GET", "webhooks_event"),
    ("/webhooks/simulate", "POST", "webhooks_simulate"),
    ("/webhooks/events/retry", "POST", "webhooks_event_retry"),
    ("/webhooks/events/replay", "POST", "webhooks_event_replay"),
    ("/webhooks/events/delete", "POST", "webhooks_event_delete"),
    ("/webhooks/events/close_failed", "POST", "webhooks_events_close_failed"),
    ("/webhooks/events/retry_blocked", "POST", "webhooks_events_retry_blocked"),
    ("/webhooks/events/approve", "POST", "webhooks_event_approve"),
    ("/webhooks/secrets/rotate", "POST", "webhooks_secrets_rotate"),
    ("/webhooks/events/resolve", "POST", "webhooks_event_resolve"),
)


class _Deps:
    """Attributes set on `feature.deps` before the platform loads (main sets `incident_hook`) are applied to the real
    deps when it does."""

    def __init__(self, owner: "LazyWebhooks"):
        object.__setattr__(self, "_owner", owner)
        object.__setattr__(self, "_pending", {})

    def __setattr__(self, k: str, v: Any) -> None:
        feat = self._owner._feat
        if feat is not None:
            setattr(feat.deps, k, v)
        else:
            self._pending[k] = v

    def __getattr__(self, k: str) -> Any:
        feat = self._owner._feat
        if feat is not None:
            return getattr(feat.deps, k)
        if k in self._pending:
            return self._pending[k]
        return self._owner._kwargs.get(k)


class LazyWebhooks:
    def __init__(self, kwargs: dict):
        self._kwargs = dict(kwargs)
        self._feat = None
        self._endpoints: dict = {}
        self._lock = threading.Lock()
        self.deps = _Deps(self)

    def get(self):
        """The real WebhookFeature, built once (thread-safe: request handlers and the startup event may race)."""
        if self._feat is None:
            with self._lock:
                if self._feat is None:
                    import webhook_triggers
                    feat = webhook_triggers.WebhookFeature(webhook_triggers.WebhookDeps(**self._kwargs))
                    for k, v in self.deps._pending.items():
                        setattr(feat.deps, k, v)
                    self._endpoints = {r.name: r.endpoint for r in feat.router.routes}
                    self._feat = feat
        return self._feat

    def __getattr__(self, k: str) -> Any:
        # Anything else (store(), start(), ...) is the real feature's.
        return getattr(self.get(), k)

    async def call(self, name: str, request):
        import inspect
        from fastapi.encoders import jsonable_encoder
        from starlette.responses import JSONResponse, Response
        self.get()
        fn = self._endpoints[name]
        out = await (fn(request) if inspect.signature(fn).parameters else fn())
        if isinstance(out, Response):
            return out
        return JSONResponse(jsonable_encoder(out))


def register(app, deps_kwargs: dict) -> LazyWebhooks:
    """Plain routes now, the platform at startup. `deps_kwargs` are WebhookDeps' fields."""
    from starlette.routing import Route
    lazy = LazyWebhooks(deps_kwargs)

    def endpoint(name: str, method: str):
        async def ep(request):
            # Starlette answers HEAD on a GET route; the real routes never did, and a HEAD on a raw view or export
            # would write its audit row for nothing.
            if request.method != method:
                from starlette.responses import Response
                return Response(status_code=405, headers={"allow": method})
            return await lazy.call(name, request)
        ep.__name__ = name
        return ep
    for path, method, name in ROUTES:
        app.router.routes.append(Route(path, endpoint(name, method), methods=[method], name=name,
                                       include_in_schema=False))

    @app.on_event("startup")
    async def _webhooks_start():
        lazy.get().start()

    @app.on_event("shutdown")
    async def _webhooks_stop():
        feat = lazy._feat
        if feat is not None and feat._sweeper:
            feat._sweeper.cancel()
    return lazy
