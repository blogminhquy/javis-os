"""Atomic host-derived baseline/candidate views in the existing shared store."""
from __future__ import annotations

import hashlib
import asyncio
import json
import secrets
import time
from contextlib import closing

import improvement_store as IM
from improvement_comparison_plans import ExperimentPlans
from improvement_experiments import _generation, _identifier
from improvement_semantic_review import SemanticReview
from improvement_trial_records import _brain
from improvement_view_protocol import view_manifest, view_hash
from improvement_view_sources import capture_sources, ResolvedView
from improvement_view_history import metadata as view_metadata, require_publication
from improvement_trial_selection import _bounded_binary_reads


class EffectiveViews:
    def __init__(self, plans, semantic):
        if (type(plans) is not ExperimentPlans or type(semantic) is not SemanticReview
                or semantic.plans is not plans or semantic.store is not plans.store or semantic.assets is not plans.assets):
            raise TypeError('concrete_same_store_view_dependencies_required')
        self.plans, self.semantic = plans, semantic
        self.assets, self.store, self.blobs = plans.assets, plans.store, plans.blobs

    @staticmethod
    def _metadata(connection, brain, comparison_id):
        return view_metadata(connection, brain, comparison_id)

    def read_existing(self, principal, comparison_id):
        brain = _brain(principal)
        _identifier(comparison_id)
        if IM._schema_version(self.store) < 7:
            return None
        with closing(self.store._conn()) as connection:
            return self._metadata(connection, brain, comparison_id)

    @staticmethod
    def _insert(connection, table, row):
        connection.execute('INSERT INTO ' + table + '(' + ','.join(row) + ') VALUES(' +
            ','.join('?' for _ in row) + ')', tuple(row.values()))

    @classmethod
    def _insert_view(cls, connection, row, asset):
        cls._insert(connection, 'improvement_effective_views', row)
        cls._insert(connection, 'improvement_effective_view_assets', asset)

    @staticmethod
    def _unbound(connection, brain, comparison_id):
        if connection.execute('SELECT 1 FROM improvement_comparison_views WHERE comparison_id=? AND brain_id=?',
                (comparison_id, brain)).fetchone():
            raise IM.ConflictError('comparison_views_already_frozen')
        if connection.execute('SELECT 1 FROM improvement_experiment_trial_links WHERE comparison_id=? AND brain_id=?',
                (comparison_id, brain)).fetchone():
            raise IM.ConflictError('comparison_runtime_already_started')

    @staticmethod
    def _proof(snapshot, metadata):
        return {'version': 1, 'evidence_class': 'technical', 'brain_id': snapshot.candidate['brain_id'],
            'comparison_id': snapshot.comparison['id'], 'comparison_hash': snapshot.manifests()['baseline']['comparison_hash'],
            'definition_hash': snapshot.experiment['definition_hash'],
            'source_authority_hash': snapshot.observed['source_authority_hash'],
            'semantic': snapshot.manifests()['baseline']['semantic'], 'views': metadata['views']}

    @staticmethod
    def _published(connection, brain, metadata, current_generation):
        return require_publication(connection, brain, metadata, current_generation)

    def _write_json(self, brain, value):
        digest = self.blobs.write(brain, IM._json(value).encode('utf-8'))
        if digest != IM._hash(value):
            raise IM.ConflictError('comparison_view_blob_changed')
        return digest

    def freeze_comparison(self, principal, comparison_id, *, expected_generation, event_key):
        brain = _brain(principal)
        _identifier(comparison_id)
        _generation(expected_generation)
        payload = {'comparison_id': comparison_id, 'expected_generation': expected_generation}
        try:
            return self._freeze_current(principal, comparison_id, expected_generation=expected_generation, event_key=event_key)
        except (IM.ConflictError, PermissionError):
            # A concurrent identical event may commit after the initial cold
            # replay check but before this caller's source/generation capture.
            # Historical replay grants no new work or private source access.
            if IM._schema_version(self.store) >= 7:
                with closing(self.store._conn()) as connection:
                    replay = self.assets._replay(connection, brain, event_key, 'comparison_views_freeze', payload)
                    if replay is not None:
                        return replay
            raise

    def _freeze_current(self, principal, comparison_id, *, expected_generation, event_key):
        brain = _brain(principal)
        _identifier(comparison_id)
        _generation(expected_generation)
        payload = {'comparison_id': comparison_id, 'expected_generation': expected_generation}
        if IM._schema_version(self.store) < 7:
            raise PermissionError('comparison_views_unavailable')
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, brain, event_key, 'comparison_views_freeze', payload)
            if replay is not None:
                return replay
            self._unbound(connection, brain, comparison_id)
        snapshot = capture_sources(self.plans, self.semantic, principal, comparison_id, expected_generation)
        manifests, rows, assets = snapshot.manifests(), {}, {}
        created = time.time()
        for variant, manifest in manifests.items():
            identifier = 'ivw_' + secrets.token_hex(12)
            digest = self._write_json(brain, manifest)
            rows[variant] = {'id': identifier, 'brain_id': brain, 'experiment_id': snapshot.experiment['id'],
                'target_id': snapshot.candidate['target_id'], 'context_id': snapshot.candidate['context_id'],
                'comparison_id': comparison_id, 'variant': variant, 'candidate_id': snapshot.candidate['id'],
                **{key: snapshot.candidate[key] for key in ('base_revision_id', 'base_hash', 'base_generation')},
                'source_authority_hash': snapshot.observed['source_authority_hash'],
                'semantic_receipt_id': snapshot.evidence['receipt_id'], 'manifest_hash': digest,
                'manifest_blob_hash': digest, 'created_at': created}
            asset = manifest['assets'][0]
            assets[variant] = {'view_id': identifier, 'brain_id': brain, 'position': 0, 'asset_id': asset['id'],
                **{key: asset[key] for key in ('canonical_ref', 'before_hash', 'content_hash', 'identity', 'authority_hash', 'origin')}}
        metadata = {'views': {variant: {'view_id': row['id'], 'manifest_hash': row['manifest_hash']} for variant, row in rows.items()}}
        binding_hash = self._write_json(brain, self._proof(snapshot, metadata))
        if capture_sources(self.plans, self.semantic, principal, comparison_id, expected_generation) != snapshot:
            raise IM.ConflictError('comparison_view_authority_changed')
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, 'comparison_views_freeze', payload)
            if replay is not None:
                return replay
            self._unbound(connection, brain, comparison_id)
            if capture_sources(self.plans, self.semantic, principal, comparison_id, expected_generation, connection=connection) != snapshot:
                raise IM.ConflictError('comparison_view_authority_changed')
            for variant in ('baseline', 'candidate'):
                self._insert_view(connection, rows[variant], assets[variant])
            self._insert(connection, 'improvement_comparison_views', {'comparison_id': comparison_id, 'brain_id': brain,
                'base_view_id': rows['baseline']['id'], 'candidate_view_id': rows['candidate']['id'],
                'semantic_receipt_id': snapshot.evidence['receipt_id'], 'binding_hash': binding_hash,
                'binding_blob_hash': binding_hash, 'created_at': created})
            if capture_sources(self.plans, self.semantic, principal, comparison_id, expected_generation, connection=connection) != snapshot:
                raise IM.ConflictError('comparison_view_authority_changed')
            changed = connection.execute('UPDATE improvement_experiments SET generation=generation+1,updated_at=? WHERE id=? AND brain_id=? AND generation=?',
                (time.time(), snapshot.experiment['id'], brain, expected_generation)).rowcount
            if changed != 1:
                raise IM.ConflictError('comparison_view_generation_changed')
            result = {**self._metadata(connection, brain, comparison_id), 'generation': expected_generation + 1}
            self.assets._event(connection, principal, event_key, 'comparison_views_freeze', payload, result)
            return result

    def load_current(self, principal, comparison_id, variant):
        resolved, _ = self._load_current(principal, comparison_id, variant)
        return resolved

    def resolve_request(self, principal, value, *, connection, require_link, trial_id=None):
        from improvement_view_trial_protocol import validate_request_v4
        request = validate_request_v4(value)
        brain, comparison_id = _brain(principal), request['lineage']['comparison_id']
        saved = self._metadata(connection, brain, comparison_id)
        if saved is None:
            raise PermissionError('comparison_views_unavailable')
        descriptor = saved['views'][request['variant']]
        if request['view'] != {'view_id': descriptor['view_id'], 'view_hash': descriptor['manifest_hash'],
                'binding_hash': saved['binding_hash']}:
            raise IM.ConflictError('comparison_view_request_changed')
        comparison = connection.execute('SELECT experiment_id,kind FROM improvement_comparisons WHERE id=? AND brain_id=?',
            (comparison_id, brain)).fetchone()
        if comparison is None or comparison['experiment_id'] != request['pins']['experiment_id']:
            raise PermissionError('comparison_view_request_unavailable')
        if comparison['kind'] == 'tuning' and request.get('qualification_id'):
            raise PermissionError('unexpected_qualification_claim')
        if comparison['kind'] == 'final':
            from improvement_view_qualification_history import qualification_metadata
            qualification_metadata(connection, brain, request)
        resolved, proof = self._load_current(principal, comparison_id, request['variant'], request=request,
            connection=connection, require_link=require_link, trial_id=trial_id)
        if comparison['kind'] == 'final':
            from improvement_view_qualification import ViewQualification
            ViewQualification(self.plans, self).validate_current(connection, principal, request, proof)
        return resolved, proof

    @_bounded_binary_reads
    def _load_current(self, principal, comparison_id, variant, *, request=None, connection=None, require_link=False, trial_id=None):
        brain = _brain(principal)
        _identifier(comparison_id)
        if type(variant) is not str or variant not in ('baseline', 'candidate'):
            raise ValueError('invalid_view_variant')
        metadata = self.read_existing(principal, comparison_id)
        if metadata is None:
            raise PermissionError('comparison_views_unavailable')
        with closing(self.store._conn()) as source_connection:
            comparison = source_connection.execute('SELECT experiment_id FROM improvement_comparisons WHERE id=? AND brain_id=?',
                (comparison_id, brain)).fetchone()
            generation = self.plans.records._row(source_connection, brain, comparison['experiment_id'])['generation']
            self._published(source_connection, brain, metadata, generation)
        snapshot = capture_sources(self.plans, self.semantic, principal, comparison_id, generation)
        proof = json.loads(self.blobs.read(brain, metadata['binding_hash']))
        if IM._hash(proof) != metadata['binding_hash'] or proof != self._proof(snapshot, metadata):
            raise IM.ConflictError('comparison_view_binding_changed')
        expected, raw_manifests = snapshot.manifests(), {}
        for key in ('baseline', 'candidate'):
            raw = self.blobs.read(brain, metadata['views'][key]['manifest_hash'])
            manifest = view_manifest(json.loads(raw))
            if (hashlib.sha256(raw).hexdigest() != metadata['views'][key]['manifest_hash']
                    or view_hash(manifest) != metadata['views'][key]['manifest_hash'] or manifest != expected[key]):
                raise IM.ConflictError('comparison_view_manifest_changed')
            raw_manifests[key] = raw
        lineage = None
        if request is not None:
            from improvement_view_lineage import load_view_lineage
            lineage = load_view_lineage(connection, brain, request, blobs=self.blobs, current=True,
                require_link=require_link, trial_id=trial_id)
            if lineage['view']['manifest'] != expected[variant]:
                raise IM.ConflictError('comparison_view_request_changed')
        # Refresh actual files/grants after every manifest and lineage blob read.
        if capture_sources(self.plans, self.semantic, principal, comparison_id, generation) != snapshot:
            raise IM.ConflictError('comparison_view_authority_changed')
        resolved = ResolvedView(metadata['views'][variant]['view_id'], comparison_id, metadata['binding_hash'],
            metadata['views'][variant]['manifest_hash'], raw_manifests[variant],
            snapshot.proposal['before' if variant == 'baseline' else 'after'], snapshot.observational_unknowns)
        return resolved, lineage


def _retired(views):
    """Derive successful lifetime closure; never accept a caller readiness flag."""
    from improvement_trial_service import OwnerTrialService
    if type(views) is not EffectiveViews or type(views.semantic) is not SemanticReview:
        return False
    owner = views.semantic.execution.trial_service
    if (type(owner) is not OwnerTrialService or owner.host is not views.plans.host
            or owner.assets is not views.assets or owner.trials.store is not views.store
            or owner.trials.workspace.root != views.plans.admission.trials.workspace.root):
        return False
    for lifetime in (views.semantic, owner):
        closing = lifetime._closing
        if (lifetime._closed is not True or not isinstance(closing, asyncio.Future)
                or not closing.done() or closing.cancelled() or closing.exception() is not None):
            return False
    return True
