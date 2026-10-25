"""Encrypted host context and revocable source authority, never asserted by trial JSON."""
from __future__ import annotations

import hashlib
import inspect
import json
import secrets
import time
from contextlib import closing
from datetime import datetime, timezone

import improvement_cases as IC
import improvement_store as IM
from evidence_store import redact
from improvement_blobs import MAX_ASSET_BYTES
from improvement_claude import ClaudeTrialAdapter
from improvement_trial_records import HostContextRecords, MAX_BINDING_BYTES, _brain

TARGET_FIELDS = ("id", "generation", "kind", "canonical_ref", "identity", "source_hash", "protected_hash", "ownership")


def _capture(value):
    capture = IC._frozen(value)
    if isinstance(capture, dict) and type(capture.get("version")) is int and capture["version"] == 2:
        from improvement_trial_semantics import validate_capture
        capture = validate_capture(capture)
        if capture["baseline_context"]["coverage"] != "complete":
            raise PermissionError("trial_context_incomplete")
        return capture
    IC._fields(capture, {"version", "surface", "plan_hash", "sources", "baseline_context"})
    if type(capture["version"]) is not int or capture["version"] != 1 or not isinstance(capture["surface"], dict) or not capture["surface"]:
        raise ValueError("invalid_host_context")
    IC._digest(capture["plan_hash"])
    context = capture["baseline_context"]
    IC._fields(context, {"content", "hash", "coverage"})
    if (not isinstance(context["content"], str) or not context["content"].strip()
            or len(context["content"].encode("utf-8")) > MAX_ASSET_BYTES
            or context["hash"] != hashlib.sha256(context["content"].encode("utf-8")).hexdigest()):
        raise ValueError("invalid_host_context")
    if context["coverage"] != "complete":
        raise PermissionError("trial_context_incomplete")
    sources = capture["sources"]
    if not isinstance(sources, list) or not 1 <= len(sources) <= 1000:
        raise ValueError("invalid_host_context_sources")
    refs = set()
    for source in sources:
        IC._fields(source, {"ref", "root", "relative", "required", "present", "identity", "hash"})
        IC._text(source["ref"], 256)
        IC._text(source["root"], 4000)
        IC.output_path(source["relative"])
        if source["ref"] in refs or type(source["required"]) is not bool or type(source["present"]) is not bool:
            raise ValueError("invalid_host_context_sources")
        refs.add(source["ref"])
        if source["present"]:
            IC._digest(source["hash"])
            IC._digest(source["identity"])
        elif source["required"] or source["hash"] is not None or source["identity"] is not None:
            raise ValueError("invalid_host_context_sources")
    if redact(capture) != capture:
        raise ValueError("insufficient_source: trial_input_contains_credentials")
    return capture


class HostContextStore(HostContextRecords):
    def __init__(self, assets, *, context_capture, selected_engine, target_observer, fixture_observer):
        for callback in (context_capture, selected_engine, target_observer, fixture_observer):
            if (not callable(callback) or inspect.iscoroutinefunction(callback)
                    or inspect.iscoroutinefunction(getattr(callback, "__call__", None))):
                raise ValueError("host_trial_dependencies_required")
        self.assets, self.store, self.blobs = assets, assets.store, assets.blobs
        self.context_capture, self.selected_engine, self.target_observer = context_capture, selected_engine, target_observer
        self.fixture_observer = fixture_observer
        self._views = None
        revalidate = getattr(context_capture, "revalidate", None)
        if revalidate is not None and (not callable(revalidate) or inspect.iscoroutinefunction(revalidate)
                or inspect.iscoroutinefunction(getattr(revalidate, "__call__", None))):
            raise ValueError("host_trial_dependencies_required")

    def bind_views(self, views):
        from improvement_views import EffectiveViews, _retired
        if type(views) is not EffectiveViews or views.assets is not self.assets or views.store is not self.store or views.plans.host is not self:
            raise TypeError('concrete_same_store_views_required')
        if self._views is not None and self._views is not views and not _retired(self._views):
            raise IM.ConflictError('view_resolver_already_bound')
        self._views = views

    def _targets(self, connection, brain, identifiers):
        targets = []
        for identifier in identifiers:
            row = self.assets._target(connection, brain, identifier)
            if row["status"] != "live" or row["ownership"] not in {"user_protected", "user_managed"}:
                raise IM.ConflictError("trial_live_target_changed")
            targets.append({key: row[key] for key in TARGET_FIELDS})
        return targets

    def _existing(self, connection, principal, payload):
        row = connection.execute("SELECT * FROM improvement_trial_contexts WHERE brain_id=? AND experiment_id=?",
                                 (_brain(principal), payload["experiment_id"])).fetchone()
        if row is not None:
            if row["request_hash"] != IM._hash(payload):
                raise IM.ConflictError("trial_context_identity_conflict")
            return self._public(connection, row)
        return None

    def _observe(self, principal, surface, expected_targets, source_refs, frozen_inventory=None, frozen_capture=None):
        from improvement_trial_sources import validate_inventory
        identifiers = [target["id"] for target in expected_targets]
        targets = IC._frozen(self.target_observer(principal, identifiers))
        if not isinstance(targets, list) or len(targets) != len(expected_targets):
            raise IM.ConflictError("trial_live_target_changed")
        for target in targets:
            IC._fields(target, TARGET_FIELDS)
        targets.sort(key=lambda item: item["id"])
        if targets != expected_targets:
            raise IM.ConflictError("trial_live_target_changed")
        engine = IC._frozen(self.selected_engine())
        ClaudeTrialAdapter(engine)  # Shape only; no subprocess, authentication or inference.
        if engine["provider"] != "anthropic-cli" or engine["engine_id"] != "claude-sdk":
            raise ValueError("unsupported_trial_configuration")
        revalidate = getattr(self.context_capture, "revalidate", None)
        if frozen_capture is not None and revalidate is not None:
            capture = _capture(revalidate(principal, IC._frozen(surface), IC._frozen(targets),
                                         frozen_capture=IC._frozen(frozen_capture)))
        else:
            capture = _capture(self.context_capture(principal, IC._frozen(surface), IC._frozen(targets)))
        inventory = validate_inventory(self.fixture_observer(principal, list(source_refs),
            frozen_inventory=IC._frozen(frozen_inventory) if frozen_inventory is not None else None))
        if {entry["source_ref"] for entry in inventory} != set(source_refs):
            raise PermissionError("trial_fixture_scope_unavailable")
        fixture_hashes = {entry[key] for entry in inventory for key in ("source_hash", "fixture_hash")}
        context_hashes = {source["hash"] for source in capture["sources"] if source["present"]}
        # SQL projections use canonical JSON source hashes. Detect exact fixture
        # text aliases independently of that representation, just as for files.
        context_hashes.update(hashlib.sha256(source["projection"].encode("utf-8")).hexdigest()
            for source in capture["sources"] if source["present"] and source.get("role") == "protected"
            and isinstance(source.get("projection"), str))
        if context_hashes & fixture_hashes:
            raise ValueError("trial_case_context_overlap")
        if frozen_inventory is not None and inventory != frozen_inventory:
            raise IM.ConflictError("trial_fixture_permission_changed")
        # A target body belongs in the variant bundle, never the immutable common baseline.
        target_refs = {target["canonical_ref"].casefold() for target in targets}
        if any((source.get("relative") or source.get("locator", {}).get("relative", "")).casefold() in target_refs
               and source.get("role") != "discovery" for source in capture["sources"]):
            raise ValueError("trial_target_context_overlap")
        for target in targets:
            raw = self.blobs.read(_brain(principal), target["source_hash"]).decode("utf-8", errors="strict")
            if raw and raw in capture["baseline_context"]["content"]:
                raise ValueError("trial_target_context_overlap")
        if frozen_capture is not None:
            # Encrypted target reads can outlive an earlier protected-context or
            # fixture observation. Revalidate actual sources after that slow I/O.
            if revalidate is not None:
                final_capture = _capture(revalidate(principal, IC._frozen(surface), IC._frozen(targets),
                                                   frozen_capture=IC._frozen(frozen_capture)))
            else:
                final_capture = _capture(self.context_capture(principal, IC._frozen(surface), IC._frozen(targets)))
            final_inventory = validate_inventory(self.fixture_observer(principal, list(source_refs),
                                                                        frozen_inventory=IC._frozen(inventory)))
            if final_capture != capture or final_inventory != inventory:
                raise IM.ConflictError("trial_host_authority_changed")
        if (IC._frozen(self.target_observer(principal, identifiers)) != targets
                or IC._frozen(self.selected_engine()) != engine):
            raise IM.ConflictError("trial_host_authority_changed")
        return {"capture": capture, "engine_config": engine, "targets": targets, "fixture_inventory": inventory}

    def create(self, principal, experiment_id, surface, target_ids, *, source_refs, event_key):
        brain = _brain(principal)
        if (not isinstance(experiment_id, str) or not IC._ID.fullmatch(experiment_id)
                or not isinstance(surface, dict) or not surface or not isinstance(target_ids, list)
                or not 1 <= len(target_ids) <= 100 or any(not isinstance(item, str) or not IC._ID.fullmatch(item) for item in target_ids)
                or len(set(target_ids)) != len(target_ids) or not isinstance(source_refs, list)
                or not 1 <= len(source_refs) <= 1000
                or any(not isinstance(ref, str) or not ref.strip() or len(ref) > 256 for ref in source_refs)
                or len(set(source_refs)) != len(source_refs)):
            raise ValueError("invalid_host_context_request")
        payload = IC._frozen({"experiment_id": experiment_id, "surface": surface, "target_ids": sorted(target_ids), "source_refs": sorted(source_refs)})
        IM.ensure(self.store)
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "trial_context_create", payload)
            if replay is not None:
                return replay
            existing = self._existing(connection, principal, payload)
            if existing is not None:
                self.assets._event(connection, principal, event_key, "trial_context_create", payload, existing)
                return existing
            policy = self.assets._policy(connection, brain)
            if policy["mode"] == "off":
                raise PermissionError("improvement_disabled")
            targets = self._targets(connection, brain, payload["target_ids"])
        observed = self._observe(principal, payload["surface"], targets, payload["source_refs"])
        capture = observed["capture"]
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "trial_context_create", payload)
            if replay is not None:
                return replay
            existing = self._existing(connection, principal, payload)
            if existing is not None:
                self.assets._event(connection, principal, event_key, "trial_context_create", payload, existing)
                return existing
            current_policy = self.assets._policy(connection, brain)
            if current_policy["mode"] == "off":
                raise PermissionError("improvement_disabled")
            if current_policy != policy or self._targets(connection, brain, payload["target_ids"]) != targets:
                raise IM.ConflictError("trial_host_authority_changed")
            if self._observe(principal, capture["surface"], targets, payload["source_refs"],
                             observed["fixture_inventory"], observed["capture"]) != observed:
                raise IM.ConflictError("trial_host_authority_changed")
            scope = {"version": 1, "brain_id": brain, "experiment_id": experiment_id, "surface": capture["surface"],
                     "target_ids": payload["target_ids"], "source_plan_hash": capture["plan_hash"], "source_refs": payload["source_refs"]}
            grant = {"version": 1, "scope_hash": IM._hash(scope), "sources": capture["sources"], "targets": targets,
                     "engine_config_hash": IM._hash(observed["engine_config"]), "baseline_context_hash": IM._hash(capture["baseline_context"]),
                     "policy_version": policy["version"], "actor": principal.by, "fixture_inventory": observed["fixture_inventory"]}
            binding = {**observed, "scope": scope, "grant": grant}
            raw = IM._json(binding).encode("utf-8")
            if len(raw) > MAX_BINDING_BYTES:
                raise ValueError("insufficient_source: trial_context_too_large")
            hashes = [self.blobs.write(brain, raw[offset:offset + MAX_ASSET_BYTES]) for offset in range(0, len(raw), MAX_ASSET_BYTES)]
            identifier = "ic_" + secrets.token_hex(12)
            generations = {item["id"]: item["generation"] for item in targets}
            connection.execute("INSERT INTO improvement_trial_contexts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (identifier, brain, experiment_id, IM._hash(payload), IM._hash(capture["baseline_context"]),
                 hashlib.sha256(raw).hexdigest(), IM._json(hashes), IM._hash(scope), IM._hash(grant),
                 IM._hash(observed["engine_config"]), policy["version"], IM._json(generations), time.time()))
            connection.execute("INSERT INTO improvement_trial_context_grants VALUES(?,?,1,'active',NULL)", (identifier, brain))
            result = self._public(connection, self._row(connection, brain, experiment_id))
            self.assets._event(connection, principal, event_key, "trial_context_create", payload, result)
            return result

    def _bound(self, connection, principal, request, *, allow_unlinked=False):
        row, binding, _ = self._bound_with_lineage(connection, principal, request, allow_unlinked=allow_unlinked)
        return row, binding

    def _bound_with_lineage(self, connection, principal, request, *, allow_unlinked=False):
        brain = _brain(principal)
        from improvement_experiment_lineage import require_experiment_version
        require_experiment_version(connection, brain, request)
        proof = None
        if request.get('version') == 4:
            if self._views is None:
                raise PermissionError('view_resolver_unavailable')
            _, proof = self._views.resolve_request(principal, request, connection=connection, require_link=not allow_unlinked)
        if request.get("version") == 3:
            from improvement_preparation_lineage import load_preparation_lineage
            proof = load_preparation_lineage(connection, brain, request, blobs=self.blobs, current=True, require_link=not allow_unlinked)
        if request.get("version") == 2:
            if request.get("variant") != "baseline":
                raise PermissionError("experiment_candidate_execution_unavailable")
            from improvement_experiment_lineage import load_lineage
            proof = load_lineage(connection, brain, request, blobs=self.blobs, current=True, require_link=not allow_unlinked)
            if proof["comparison"]["kind"] != "tuning":
                raise PermissionError("experiment_final_execution_unavailable")
        row = self._row(connection, brain, request["pins"]["experiment_id"])
        if self._grant(connection, row)["status"] != "active":
            raise PermissionError("trial_source_grant_revoked")
        policy = self.assets._policy(connection, brain)
        if policy["mode"] == "off":
            raise PermissionError("improvement_disabled")
        binding = self._decode(row)
        if (any(request["pins"][key] != row[key] for key in ("scope_hash", "grant_hash", "engine_config_hash", "policy_version"))
                or request["baseline_context_hash"] != row["context_hash"] or policy["version"] != row["policy_version"]
                or request["target_generations"] != json.loads(row["target_generations_json"])
                or self._targets(connection, brain, sorted(request["target_generations"])) != binding["targets"]
                or request["engine_config"] != binding["engine_config"]):
            raise IM.ConflictError("trial_host_binding_drift")
        from improvement_trial_sources import authorize_case
        authorize_case(connection, brain, request, binding["fixture_inventory"], blobs=self.blobs,
                       baseline_content=binding["capture"]["baseline_context"]["content"])
        if request.get("version") in (2, 4):
            from improvement_experiment_lineage import current_fences
            current_fences(connection, brain, proof)
        elif request.get("version") == 3:
            from improvement_preparation_lineage import current_preparation_fences
            current_preparation_fences(connection, brain, proof)
        return row, binding, proof

    def context_loader(self, principal, request):
        request = IC._frozen(request)
        with closing(self.store._conn()) as connection:
            _, binding = self._bound(connection, principal, request)
            return binding["capture"]["baseline_context"]

    def _snapshot_binding(self, connection, principal, experiment_id, source_ref):
        row = self._row(connection, _brain(principal), experiment_id)
        if self._grant(connection, row)["status"] != "active":
            raise PermissionError("trial_source_grant_revoked")
        policy = self.assets._policy(connection, row["brain_id"])
        if policy["mode"] == "off":
            raise PermissionError("improvement_disabled")
        binding = self._decode(row)
        if policy["version"] != row["policy_version"]:
            raise IM.ConflictError("trial_host_binding_drift")
        if (source_ref not in binding["scope"]["source_refs"]
                or source_ref not in {entry["source_ref"] for entry in binding["fixture_inventory"]}):
            raise PermissionError("trial_fixture_scope_unavailable")
        targets = self._targets(connection, row["brain_id"], sorted(json.loads(row["target_generations_json"])))
        if targets != binding["targets"]:
            raise IM.ConflictError("trial_host_binding_drift")
        return row, binding

    def _snapshot_observe(self, principal, binding):
        if self._observe(principal, binding["capture"]["surface"], binding["targets"], binding["scope"]["source_refs"],
                         binding["fixture_inventory"], binding["capture"]) != {
                key: binding[key] for key in ("capture", "engine_config", "targets", "fixture_inventory")}:
            raise IM.ConflictError("trial_host_authority_changed")

    def capture_snapshot(self, principal, experiment_id, source_ref, *, event_key):
        """Capture one host-bound current fixture; no caller-supplied bytes or grants.

        Same-event replay returns historical metadata without source I/O, including
        after revocation. It never refreshes source authority or reactivates a grant.
        Every new event requires current authority and commits its association in
        the same transaction as the immutable CaseStore snapshot and inner event.
        """
        from improvement_trial_file_sources import BrainFileFixtures
        brain = _brain(principal)
        if (not isinstance(experiment_id, str) or not IC._ID.fullmatch(experiment_id)
                or not isinstance(source_ref, str) or not source_ref.strip() or len(source_ref) > 256):
            raise ValueError("invalid_host_snapshot_request")
        if type(self.fixture_observer) is not BrainFileFixtures:
            raise ValueError("concrete_brain_file_fixtures_required")
        if IM._schema_version(self.store) < 3:
            raise PermissionError("trial_context_unavailable")
        payload = {"experiment_id": experiment_id, "source_ref": source_ref}
        with closing(self.store._conn()) as connection:
            self._row(connection, brain, experiment_id)
            replay = self.assets._replay(connection, brain, event_key, "trial_snapshot_capture", payload)
            if replay is not None:
                return replay
            row, binding = self._snapshot_binding(connection, principal, experiment_id, source_ref)
        self._snapshot_observe(principal, binding)
        entry = next(entry for entry in binding["fixture_inventory"] if entry["source_ref"] == source_ref)
        captured = self.fixture_observer.capture(principal, source_ref, expected_entry=IC._frozen(entry))
        IC._fields(captured, {"manifest", "raw", "fixture"})
        expected_manifest = {key: entry[key] for key in ("source_ref", "source_version", "timezone", "data_period",
                                                        "cutoff", "schema", "redaction", "sufficient_source")}
        if (captured["manifest"] != {"version": 1, "freshness": "current", **expected_manifest}
                or not isinstance(captured["raw"], bytes) or not isinstance(captured["fixture"], bytes)
                or hashlib.sha256(captured["raw"]).hexdigest() != entry["source_hash"]
                or hashlib.sha256(captured["fixture"]).hexdigest() != entry["fixture_hash"]):
            raise IM.ConflictError("trial_fixture_capture_mismatch")
        from improvement_trial_sources import _exclude_baseline_body
        baseline = binding["capture"]["baseline_context"]["content"].encode("utf-8")
        for raw in (captured["raw"], captured["fixture"]):
            _exclude_baseline_body(raw, baseline)
        manifest = {**captured["manifest"], "grant_hash": row["grant_hash"],
                    "captured_at": datetime.now(timezone.utc).isoformat()}
        inner_key = "host-snapshot-" + IM._hash([experiment_id, source_ref, event_key])
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "trial_snapshot_capture", payload)
            if replay is not None:
                return replay
            current, current_binding = self._snapshot_binding(connection, principal, experiment_id, source_ref)
            if current["id"] != row["id"] or current_binding != binding:
                raise IM.ConflictError("trial_host_binding_drift")
            result = IC.CaseStore(self.assets)._put_snapshot_in(connection, principal, manifest,
                captured["raw"], captured["fixture"], event_key=inner_key)
            # Check after blob publication too: a source edit during encryption
            # cannot publish an authorized association for the now-stale fixture.
            self._snapshot_observe(principal, binding)
            self._snapshot_binding(connection, principal, experiment_id, source_ref)
            result = {**result, "context_id": row["id"], "experiment_id": experiment_id, "source_ref": source_ref}
            self.assets._event(connection, principal, event_key, "trial_snapshot_capture", payload, result)
            return result

    def live_guard(self, principal, request):
        request = IC._frozen(request)
        with closing(self.store._conn()) as connection:
            row, binding = self._bound(connection, principal, request)
            targets = self._targets(connection, row["brain_id"], sorted(request["target_generations"]))
        if targets != binding["targets"] or self._observe(principal, binding["capture"]["surface"], targets,
                binding["scope"]["source_refs"], binding["fixture_inventory"], binding["capture"]) != {
                key: binding[key] for key in ("capture", "engine_config", "targets", "fixture_inventory")}:
            raise IM.ConflictError("trial_host_authority_changed")
        # Recheck revocation/policy after potentially slow source/config I/O.
        with closing(self.store._conn()) as connection:
            _, final_binding, proof = self._bound_with_lineage(connection, principal, request)
        if proof is not None:
            # The final bound pass decrypts fixtures/context. Observe real sources
            # afterward, then refresh SQL fences without another slow blob read.
            self._snapshot_observe(principal, final_binding)
            if request.get("version") == 3:
                from improvement_preparation_lineage import current_preparation_fences as current_fences
            else:
                from improvement_experiment_lineage import current_fences
            with closing(self.store._conn()) as connection:
                current_fences(connection, _brain(principal), proof)
        return {**{key: row[key] for key in ("scope_hash", "grant_hash", "engine_config_hash")},
                "baseline_context_hash": row["context_hash"], "target_generations": request["target_generations"]}
