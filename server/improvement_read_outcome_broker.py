"""Pinned host read outcomes, without SDK/native delivery or error inference."""
from __future__ import annotations

import json
import secrets
import threading

from improvement_sandbox import FixtureBroker, _frozen, _hash, _json, _manifest
from improvement_skill_asset_broker import SkillAssetBroker


_SKILL_TOOL = "mcp__skill__skill_asset_read"
_FIXTURE_TOOL = "mcp__fixture__fixture_read"


def _request_snapshot(value):
    """Reject Python-only values rather than silently changing JSON arguments."""
    def validate(item):
        if type(item) in (str, int, float, bool, type(None)):
            return
        if type(item) is list:
            for child in item:
                validate(child)
            return
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise ValueError("invalid_read_arguments")
                validate(child)
            return
        raise ValueError("invalid_read_arguments")

    try:
        validate(value)
        return _frozen(value)
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("invalid_read_arguments") from error


class PinnedReadOutcomeBroker:
    """Wrap actual skill/fixture decisions in closed, attempt-bound envelopes.

    Accept only a fully validated materialized manifest2/3/4 with the canonical
    input_hash and the same strict trial_id/attempt bounds as SkillAssetBroker.
    An optional fixture_broker must be a concrete FixtureBroker with exactly the
    pinned grant and fixture inventory. It remains a host-owned capability; its
    authority is checked again before reads, and external users must coordinate
    any direct access with this broker's lifetime.

    ``read(tool_name, args)`` supports only mcp__skill__skill_asset_read and
    mcp__fixture__fixture_read. Unknown tools and non-JSON arguments raise
    ValueError. Any valid JSON request for either tool creates one fresh envelope
    with exactly version, observation_id, trial_id, attempt, input_hash,
    effective_view, tool_name, request_hash, outcome and result. Hit results are
    the unmodified actual underlying return; misses have only generic read_miss
    status/reason. Fixture requests require exactly snapshot_id/source_version
    strings. Malformed/foreign JSON requests still take the underlying miss path.

    ``observations`` is a tuple of detached dictionaries with exactly version,
    observation_id, trial_id, attempt, input_hash, effective_view, tool_name,
    request, response_text and response_hash. Internal entries are immutable
    canonical JSON strings. A future adapter must emit ``_json(read(...))``
    unchanged to match that exact response_text/hash. ``fixture_events`` is a
    tuple of defensive snapshots of the actual underlying fixture events,
    including any events predating an injected broker's binding.

    The lock covers the underlying read and observation append, so this broker's
    equal concurrent calls retain unique source sequences and response IDs.
    It never accesses paths/connectors or observes/normalizes native error flags.
    A host read envelope alone proves neither native delivery nor observed use.
    """

    def __init__(self, manifest, *, trial_id, attempt, input_hash, fixture_broker=None):
        if type(manifest) is not dict:
            raise ValueError("invalid_read_manifest")
        pinned = _manifest(manifest)
        # This broker also enforces v2/v3/v4 and strict trial/hash binding.
        self._skill_broker = SkillAssetBroker(pinned, trial_id=trial_id, attempt=attempt, input_hash=input_hash)
        self._grant_hash = pinned["grant_hash"]
        fixtures = pinned["case"]["fixtures"]
        self._fixtures_json = _json({fixture["snapshot_id"]: fixture for fixture in fixtures})
        if fixture_broker is None:
            fixture_broker = FixtureBroker(fixtures, self._grant_hash)
        self._fixture_broker = fixture_broker
        self._check_fixture_authority()
        self._binding_json = _json({"version": 1, "trial_id": trial_id, "attempt": attempt,
                                   "input_hash": input_hash, "effective_view": pinned["effective_view"]})
        self._observations = []
        self._observation_ids = set()
        self._lock = threading.Lock()

    def _check_fixture_authority(self):
        broker = self._fixture_broker
        if (type(broker) is not FixtureBroker or broker.grant_hash != self._grant_hash
                or _json(broker.fixtures) != self._fixtures_json):
            raise ValueError("read_fixture_binding_mismatch")

    @property
    def observations(self):
        """Return defensive snapshots of every emitted host read envelope."""
        with self._lock:
            history = tuple(self._observations)
        return tuple(json.loads(entry) for entry in history)

    @property
    def fixture_events(self):
        """Return actual fixture decisions without exposing their mutable ledger."""
        with self._lock:
            return tuple(_frozen(self._fixture_broker.events))

    def read(self, tool_name, args) -> dict:
        """Emit one exact, immutable-history-backed host outcome for a JSON read."""
        if type(tool_name) is not str or tool_name not in (_SKILL_TOOL, _FIXTURE_TOOL):
            raise ValueError("unsupported_read_tool")
        request = _request_snapshot(args)
        request_hash = _hash(request)
        with self._lock:
            self._check_fixture_authority()
            if tool_name == _SKILL_TOOL:
                actual = self._skill_broker.read(request)
                hit = actual["status"] == "skill_asset_hit"
            else:
                valid = (type(request) is dict and set(request) == {"snapshot_id", "source_version"}
                         and all(type(value) is str for value in request.values()))
                fixture_args = {"snapshot_id": request["snapshot_id"]} if valid else {}
                version = request["source_version"] if valid else None
                actual = self._fixture_broker.read("fixture.read", fixture_args, version, self._grant_hash)
                hit = actual["status"] == "fixture_hit"
            identifier = secrets.token_hex(32)
            while identifier in self._observation_ids:
                identifier = secrets.token_hex(32)
            response = json.loads(self._binding_json)
            response.update(observation_id=identifier, tool_name=tool_name, request_hash=request_hash,
                            outcome="hit" if hit else "miss",
                            result=actual if hit else {"status": "read_miss", "reason": "read_miss"})
            observation = {key: value for key, value in response.items()
                           if key not in ("request_hash", "outcome", "result")}
            observation.update(request=request, response_text=_json(response), response_hash=_hash(response))
            self._observations.append(_json(observation))
            self._observation_ids.add(identifier)
        return _frozen(response)
