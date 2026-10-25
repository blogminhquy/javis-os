"""In-memory reads of one materialized trial skill, without native-use claims."""
from __future__ import annotations

import json
import secrets
import threading

from improvement_sandbox import _IDENTITY, _frozen, _hash, _json, _manifest


class SkillAssetBroker:
    """Serve only a validated v2/v3/v4 manifest's selected skill for one host attempt.

    ``read(args)`` accepts an exact plain dictionary of string ``view_id``,
    ``view_hash``, ``asset_id`` and ``content_hash``. A hit returns a fresh dict
    containing status, an unpredictable observation_id, trial_id, attempt,
    input_hash, the complete effective_view, asset_id, content_hash and content.
    Every other request returns the same content-free skill_asset_miss dict.

    ``observations`` returns a tuple of defensive dictionary snapshots for hits.
    Each contains the same binding, the exact request, canonical response_text,
    its raw UTF-8 SHA-256 response_hash, and content_hash. Host adapters must emit
    ``_json(read(args))`` unchanged to use that response_text for a later native
    ToolUse/ToolResult join. This broker alone never proves native observed use.
    Private history entries and pinned assets are retained as immutable strings;
    caller mutation cannot change earlier observations or subsequent reads.
    No path, filesystem, connector, fallback, or runtime SDK is consulted.
    """

    def __init__(self, manifest, *, trial_id, attempt, input_hash):
        if (type(trial_id) is not str or not _IDENTITY.fullmatch(trial_id)
                or type(attempt) is not int or not 1 <= attempt <= 1_000_000):
            raise ValueError("invalid_trial_attempt")
        if type(manifest) is not dict:
            raise ValueError("invalid_skill_asset_manifest")
        # _manifest defensively freezes and validates the entire public input,
        # including asset bytes, context, contract, fixtures and view structure.
        pinned = _manifest(manifest)
        if pinned["version"] not in (2, 3, 4):
            raise ValueError("unsupported_skill_asset_manifest")
        if type(input_hash) is not str or input_hash != _hash(pinned):
            raise ValueError("trial_input_hash_mismatch")
        asset = pinned["assets"][0]
        view = pinned["effective_view"]
        self._request_json = _json({"view_id": view["view_id"], "view_hash": view["view_hash"],
                                    "asset_id": asset["id"], "content_hash": asset["hash"]})
        self._response_base_json = _json({"status": "skill_asset_hit", "trial_id": trial_id, "attempt": attempt,
                                         "input_hash": input_hash, "effective_view": view, "asset_id": asset["id"],
                                         "content_hash": asset["hash"], "content": asset["content"]})
        self._observations = []
        self._observation_ids = set()
        self._lock = threading.Lock()

    @property
    def observations(self):
        """Return detached snapshots of successful reads in recording order."""
        with self._lock:
            history = tuple(self._observations)
        return tuple(json.loads(entry) for entry in history)

    def read(self, args) -> dict:
        """Read the exact pinned asset, or return a generic content-free miss."""
        miss = {"status": "skill_asset_miss", "reason": "skill_asset_miss"}
        if type(args) is not dict:
            return miss
        request = args.copy()
        if (len(request) != 4 or any(type(key) is not str or type(value) is not str
                                     for key, value in request.items())
                or _json(request) != self._request_json):
            return miss
        response = json.loads(self._response_base_json)
        with self._lock:
            identifier = secrets.token_hex(32)
            while identifier in self._observation_ids:
                identifier = secrets.token_hex(32)
            response["observation_id"] = identifier
            observation = {key: value for key, value in response.items() if key not in ("status", "content")}
            observation.update(request=request, response_text=_json(response), response_hash=_hash(response))
            self._observations.append(_json(observation))
            self._observation_ids.add(identifier)
        return _frozen(response)
