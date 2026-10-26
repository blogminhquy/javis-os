"""Explicit owner compose consent and read-only current input authority.

Consent is immutable M0-linked history with a separately revocable grant. This
service never dispatches an operation/model or grants edit/activation authority.
Current checks reuse the complete existing input-basis hash rather than copying
the trial ledger into another authority store. Only authenticated operation
creation may account for the host's own experiment generation mutation.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import improvement_store as IM
from improvement_blobs import AssetUnavailable
from improvement_compose_inputs import ComposeInputs
from improvement_compose_protocol import render_compose_input
from improvement_experiment_protocol import _digest
from improvement_experiments import _generation, _identifier
from improvement_generation_protocol import input_bytes
from improvement_operation_schema import assert_installed
from improvement_qualification_records import require_product_store
from improvement_trial_records import _brain

_META = {'authorization_id', 'experiment_id', 'context_id', 'input_hash', 'basis_hash',
         'guard_blob_hash', 'experiment_generation', 'generation', 'status'}


def _permission_metadata(assets, connection, row):
    events = list(connection.execute("SELECT * FROM improvement_events WHERE brain_id=? AND operation='compose_authorize' "
        "AND json_extract(result_json,'$.authorization_id')=? LIMIT 2", (row['brain_id'], row['id'])))
    if len(events) != 1:
        raise AssetUnavailable('compose_permission_history_unavailable')
    event = events[0]
    value = json.loads(event['result_json'])
    if type(value) is not dict or set(value) != _META:
        raise AssetUnavailable('compose_permission_history_changed')
    _generation(value['experiment_generation'])
    for key in ('input_hash', 'basis_hash', 'guard_blob_hash'): _digest(value[key])
    expected = {'authorization_id': row['id'], **{key: row[key] for key in
        ('experiment_id', 'context_id', 'input_hash', 'basis_hash')}, 'generation': 1, 'status': 'active'}
    if any(value.get(key) != item for key, item in expected.items()) or event['actor'] != row['actor']:
        raise AssetUnavailable('compose_permission_history_changed')
    payload = {'experiment_id': row['experiment_id'], 'expected_generation': value['experiment_generation']}
    if assets._replay(connection, row['brain_id'], event['event_key'], 'compose_authorize', payload) != value:
        raise AssetUnavailable('compose_permission_history_changed')
    return {**value, 'generation': row['generation'], 'status': row['status']}


def operation_permission(connection, assets, principal, request, *, operation=None):
    """SQL-only compose admission shared with the actual metadata owner.

    This is not the source/blob guard: the concrete host must also call current.
    No caller-supplied operation row or ambiguous creation history is accepted.
    """
    from improvement_operation_protocol import operation_request
    from improvement_operation_records import OperationRecords
    request = operation_request(request)
    if request['kind'] != 'compose':
        raise ValueError('compose_operation_required')
    brain = _brain(principal)
    require_product_store(assets, principal, connection=connection)
    row = ComposePermissions._row(connection, brain, request['compose_authorization_id'])
    metadata = _permission_metadata(assets, connection, row)
    if row['status'] != 'active' or row['generation'] != 1:
        raise PermissionError('compose_permission_revoked')
    if any(request[key] != row[key] for key in ('experiment_id', 'context_id', 'definition_hash', 'input_hash')):
        raise IM.ConflictError('compose_operation_permission_changed')
    experiment = connection.execute('SELECT * FROM improvement_experiments WHERE id=? AND brain_id=?',
        (row['experiment_id'], brain)).fetchone()
    if experiment is None:
        raise PermissionError('compose_experiment_unavailable')
    generation = metadata['experiment_generation']
    if operation is not None:
        actual = connection.execute('SELECT * FROM improvement_operations WHERE id=? AND brain_id=?',
            (operation['id'], brain)).fetchone()
        if actual is None or dict(actual) != dict(operation) or json.loads(actual['request_json']) != request:
            raise IM.ConflictError('compose_operation_changed')
        public = OperationRecords._public(actual)
        initial = {**public, 'status': 'pending', 'generation': 1, 'attempt': 0}
        events = list(connection.execute("SELECT * FROM improvement_events WHERE brain_id=? AND operation='operation_create' "
            "AND json_extract(result_json,'$.operation_id')=? LIMIT 2", (brain, actual['id'])))
        payload = {'request': request, 'input_blob_hash': actual['input_blob_hash'], 'expected_generation': generation}
        if (len(events) != 1 or assets._replay(connection, brain, events[0]['event_key'], 'operation_create', payload) != initial
                or experiment['updated_at'] != actual['created_at']):
            raise IM.ConflictError('compose_operation_history_changed')
        generation += 1
    if (experiment['generation'] != generation or experiment['phase'] not in ('probing', 'comparing')
            or experiment['context_id'] != row['context_id'] or experiment['definition_hash'] != row['definition_hash']):
        raise IM.ConflictError('compose_operation_state_changed')
    return row, metadata


class ComposePermissions:
    def __init__(self, plans, *, owner=None):
        if owner is not None:
            from improvement_compositions import ComposerService
            if type(owner) is not ComposerService or owner.plans is not plans:
                raise TypeError('concrete_compose_owner_required')
        self._owner = owner
        self.inputs = ComposeInputs(plans)
        self.plans, self.assets, self.store, self.blobs = plans, plans.assets, plans.store, plans.blobs

    @classmethod
    def from_existing(cls, assets):
        """Metadata/revocation only; no plans, host, migrations or blob reads."""
        if type(assets) is not IM.ImprovementStore:
            raise TypeError('concrete_compose_store_required')
        instance = cls.__new__(cls)
        instance.plans, instance.inputs, instance._owner = None, None, None
        instance.assets, instance.store, instance.blobs = assets, assets.store, assets.blobs
        return instance

    def _live(self):
        from improvement_comparison_plans import ExperimentPlans
        if type(self.plans) is not ExperimentPlans or type(self.inputs) is not ComposeInputs:
            raise PermissionError('compose_live_authority_unavailable')
        if self._owner is not None:
            self._owner._open()

    def scope(self, principal, experiment_id, authorization_id=None):
        """Authenticate the path before any live workflow or native verifier."""
        from improvement_experiments import ExperimentRecords
        brain = _brain(principal); _identifier(experiment_id)
        ExperimentRecords(self.assets)._available()
        with closing(self.store._conn()) as connection:
            row = ExperimentRecords._row(connection, brain, experiment_id)
            ExperimentRecords._public(row)
            if authorization_id is not None:
                _identifier(authorization_id); self._installed()
                permission = self._row(connection, brain, authorization_id)
                if permission['experiment_id'] != experiment_id:
                    raise PermissionError('experiment_compose_permission_unavailable')

    def replay_control(self, principal, experiment_id, operation, data):
        """Cold saved owner intent only; no host, source, writer or redispatch."""
        from improvement_compositions import ComposerService
        from improvement_experiments import ExperimentRecords
        from improvement_operation_records import OperationRecords
        if operation not in ('compose', 'compose-authorize', 'compose-preview'):
            raise ValueError('invalid_experiment_control')
        authorization_id = data.get('authorization_id') if operation == 'compose' else None
        self.scope(principal, experiment_id, authorization_id)
        self._installed()
        brain, generation = _brain(principal), data['expected_generation']
        with closing(self.store._conn()) as connection:
            experiment = ExperimentRecords._row(connection, brain, experiment_id)
            authorization = None
            if operation == 'compose':
                authorization = self._metadata(connection, self._row(connection, brain, authorization_id))
                payload = {'authorization_id': authorization_id, 'expected_generation': generation}
                event = 'compose_generate'
            else:
                payload = {'experiment_id': experiment_id, 'expected_generation': generation}
                event = 'compose_authorize'
            if operation != 'compose-preview':
                saved = self.assets._replay(connection, brain, data['event_key'], event, payload)
                if saved is not None:
                    if operation == 'compose-authorize':
                        saved = self._metadata(connection, self._row(connection, brain, saved['authorization_id']))
                    if saved.get('experiment_id') != experiment_id or (authorization_id is not None
                            and saved.get('authorization_id') != authorization_id):
                        raise IM.ConflictError('compose_control_history_changed')
                    return True, saved
            if operation == 'compose':
                started = self.assets._replay(connection, brain, ComposerService._start_key(brain, data['event_key']),
                    'compose_generate_start', payload)
                if started is not None:
                    row = connection.execute('SELECT * FROM improvement_operations WHERE id=? AND brain_id=?',
                        (started['operation_id'], brain)).fetchone()
                    if row is None:
                        raise PermissionError('compose_operation_unavailable')
                    public = OperationRecords._public(row)
                    request = json.loads(row['request_json'])
                    if (public['experiment_id'] != experiment_id or public['kind'] != 'compose'
                            or request['compose_authorization_id'] != authorization_id
                            or started['authorization_id'] != authorization_id or started['experiment_id'] != experiment_id):
                        raise IM.ConflictError('compose_control_history_changed')
                    return True, {**started, 'status': 'operation_recorded', 'operation_status': row['status']}
            # A closed/stale intent cannot wake a live factory just because no
            # matching historical event exists. New live work repeats all guards.
            if experiment['phase'] not in ('probing', 'comparing'):
                raise IM.ConflictError('experiment_stopping')
            if self.assets._policy(connection, brain)['mode'] == 'off':
                raise PermissionError('improvement_disabled')
            if authorization is not None:
                if authorization['status'] != 'active' or authorization['generation'] != 1:
                    raise PermissionError('compose_permission_revoked')
                if authorization['experiment_generation'] != generation:
                    raise IM.ConflictError('compose_permission_generation_changed')
            if experiment['generation'] != generation:
                raise IM.ConflictError('experiment_state_stale')
            return False, None

    def policy(self, principal, experiment_id):
        from improvement_experiments import ExperimentRecords
        self.scope(principal, experiment_id)
        with closing(self.store._conn()) as connection:
            row = ExperimentRecords._row(connection, _brain(principal), experiment_id)
            public = ExperimentRecords._public(row)
            value = json.loads(row['definition_json'])
            count = value['decision_policy']['multiple_tests']
            return {'experiment_id': experiment_id, 'definition_hash': public['definition_hash'],
                'multiple_tests': count, 'candidate_policy': 'two_proposals_and_one_compose' if count == 3 else 'two_proposals',
                **{key: value[key] for key in ('contract_id', 'case_set_id', 'base_bundle_id', 'repeat_policy', 'timeout_seconds')},
                'native_capability': 'unknown', 'business_proof': False}

    def compositions(self, principal, experiment_id):
        """Bounded immutable publication references, never decrypted evidence."""
        self.scope(principal, experiment_id)
        if IM._schema_version(self.store) < 8:
            return []
        brain = _brain(principal)
        with closing(self.store._conn()) as connection:
            rows = list(connection.execute('SELECT * FROM improvement_compositions WHERE experiment_id=? AND brain_id=? LIMIT 2',
                (experiment_id, brain)))
            if len(rows) > 1:
                raise IM.ConflictError('compose_publication_history_changed')
            result = []
            for row in rows:
                authorization = self._metadata(connection, self._row(connection, brain, row['authorization_id']))
                events = list(connection.execute("SELECT * FROM improvement_events WHERE brain_id=? AND operation='compose_generate' "
                    "AND json_extract(result_json,'$.composition_id')=? LIMIT 2", (brain, row['id'])))
                if len(events) != 1:
                    raise IM.ConflictError('compose_publication_history_changed')
                payload = {'authorization_id': row['authorization_id'], 'expected_generation': authorization['experiment_generation']}
                saved = self.assets._replay(connection, brain, events[0]['event_key'], 'compose_generate', payload)
                if (not saved or saved.get('experiment_id') != experiment_id or saved.get('operation_id') != row['operation_id']
                        or saved.get('result_id') != row['result_id'] or saved.get('composition_id') != row['id']
                        or saved.get('status') != ('keep_base' if row['outcome'] == 'keep_base' else 'candidate_staged')):
                    raise IM.ConflictError('compose_publication_history_changed')
                result.append({'composition_id': row['id'], **{key: row[key] for key in
                    ('experiment_id', 'authorization_id', 'operation_id', 'result_id', 'input_hash', 'basis_hash',
                     'output_hash', 'decisions_hash', 'outcome', 'candidate_id', 'created_at')},
                    'authority_status': 'not_checked', 'business_proof': False})
            return result

    def outcomes(self, principal, experiment_id):
        """One recorded compose disposition, including starts without publication.

        Read existing authenticated events and role metadata only. A saved start
        is historical, never permission to resume or an inferred live owner.
        """
        from improvement_operation_records import OperationRecords
        from improvement_compositions import ComposerService
        self.scope(principal, experiment_id)
        if IM._schema_version(self.store) < 8:
            return []
        brain = _brain(principal)
        publications = self.compositions(principal, experiment_id)
        with closing(self.store._conn()) as connection:
            rows = list(connection.execute("SELECT * FROM improvement_operations WHERE brain_id=? AND experiment_id=? "
                "AND kind='compose' LIMIT 2", (brain, experiment_id)))
            events = list(connection.execute("SELECT * FROM improvement_events WHERE brain_id=? "
                "AND operation IN ('compose_generate_start','compose_generate') "
                "AND json_extract(result_json,'$.experiment_id')=? LIMIT 3", (brain, experiment_id)))
            if len(rows) > 1 or len(events) > 2:
                raise IM.ConflictError('compose_outcome_history_changed')
            if not rows:
                if events or publications:
                    raise IM.ConflictError('compose_outcome_history_changed')
                return []
            row = rows[0]
            public = OperationRecords._public(row)
            request = json.loads(row['request_json'])
            permission = self._row(connection, brain, request['compose_authorization_id'])
            authorization = self._metadata(connection, permission)
            if (authorization['experiment_id'] != experiment_id or authorization['context_id'] != public['context_id']
                    or authorization['input_hash'] != public['input_hash'] or request['definition_hash'] != permission['definition_hash']):
                raise IM.ConflictError('compose_outcome_history_changed')
            payload = {'authorization_id': authorization['authorization_id'],
                       'expected_generation': authorization['experiment_generation']}
            starts = [event for event in events if event['operation'] == 'compose_generate_start']
            finals = [event for event in events if event['operation'] == 'compose_generate']
            if len(starts) != 1 or len(finals) > 1:
                raise IM.ConflictError('compose_outcome_history_changed')
            start = self.assets._replay(connection, brain, starts[0]['event_key'], 'compose_generate_start', payload)
            expected = {'authorization_id': authorization['authorization_id'], 'experiment_id': experiment_id,
                'operation_id': public['operation_id'], 'input_hash': public['input_hash'],
                'generation': authorization['experiment_generation'] + 1}
            if start != expected:
                raise IM.ConflictError('compose_outcome_history_changed')
            status, publication = 'operation_recorded', None
            if finals:
                final = finals[0]
                saved = self.assets._replay(connection, brain, final['event_key'], 'compose_generate', payload)
                if (starts[0]['event_key'] != ComposerService._start_key(brain, final['event_key'])
                        or any(saved.get(key) != expected[key] for key in ('authorization_id', 'experiment_id', 'operation_id'))):
                    raise IM.ConflictError('compose_outcome_history_changed')
                status = saved.get('status')
                if status in ('keep_base', 'candidate_staged'):
                    if len(publications) != 1 or publications[0]['composition_id'] != saved.get('composition_id'):
                        raise IM.ConflictError('compose_outcome_history_changed')
                    publication = publications[0]
                elif status not in ('invalid_output', 'native_incomplete') or saved.get('candidates') != [] or publications:
                    raise IM.ConflictError('compose_outcome_history_changed')
            elif publications:
                raise IM.ConflictError('compose_outcome_history_changed')
            return [{'experiment_id': experiment_id, 'authorization_id': authorization['authorization_id'],
                'authorization_status': authorization['status'], 'authorization_generation': authorization['generation'],
                'operation_id': public['operation_id'], 'operation_status': public['status'], 'status': status,
                'input_hash': authorization['input_hash'], 'basis_hash': authorization['basis_hash'],
                'composition_id': publication['composition_id'] if publication else None,
                'result_id': publication['result_id'] if publication else None,
                'candidate_id': publication['candidate_id'] if publication else None,
                'authority_status': 'not_checked', 'business_proof': False}]

    def preview(self, principal, experiment_id, *, expected_generation, event_key):
        self._live()
        self.scope(principal, experiment_id)
        payload = {'experiment_id': experiment_id, 'expected_generation': expected_generation}
        with closing(self.store._conn()) as connection:
            old = self.assets._replay(connection, _brain(principal), event_key, 'compose_preview', payload)
        built = self.inputs.build(principal, experiment_id, expected_generation=expected_generation)
        basis = self._load(_brain(principal), built['basis_hash'])
        result = {'experiment_id': experiment_id, 'generation': expected_generation,
            'input_hash': built['input_hash'], 'basis_hash': built['basis_hash'],
            'candidate_refs': basis['candidate_refs'], 'tuning_refs': basis['report_refs'],
            'native_capability': 'unknown', 'business_proof': False}
        with self.store._Tx(self.store) as connection:
            before = self._capture(connection, principal, experiment_id, expected_generation)
            observed, _ = self.plans.authoring.observe(principal, before['authoring']['target'])
            if (self._authority_hash(before) != basis['authority_snapshot_hash']
                    or observed['source_authority_hash'] != basis['source_authority_hash']):
                raise IM.ConflictError('compose_preview_changed')
            self._fence(connection, principal, before, observed)
            old = self.assets._replay(connection, _brain(principal), event_key, 'compose_preview', payload)
            if old is not None and old != result:
                raise IM.ConflictError('compose_preview_changed')
            self._live()
            if old is None:
                self.assets._event(connection, principal, event_key, 'compose_preview', payload, result)
            self.inputs._fence(connection, principal, before)
        return result

    def _installed(self):
        if IM._schema_version(self.store) < 8:
            raise PermissionError('compose_permission_unavailable')

    def _connection(self, connection):
        if type(connection) is not sqlite3.Connection:
            raise TypeError('concrete_compose_connection_required')
        databases = connection.execute('PRAGMA database_list').fetchall()
        if (len(databases) != 1 or databases[0][1] != 'main' or not databases[0][2]
                or Path(databases[0][2]).resolve() != self.store.path.resolve()):
            raise ValueError('compose_connection_mismatch')
        version = connection.execute('SELECT version FROM improvement_schema WHERE id=1').fetchone()
        if not version or version[0] not in (8, 9, 10, 11, 12, 13, 14, 15, 16, 17):
            raise IM.SchemaError('unsupported_improvement_schema')
        if version[0] in (9, 10, 11, 12, 13, 14, 15, 16, 17):
            assert_installed(connection)

    @staticmethod
    def _row(connection, brain, identifier):
        row = connection.execute('SELECT a.*,g.generation,g.status FROM improvement_compose_authorizations a '
            'JOIN improvement_compose_grants g ON g.authorization_id=a.id AND g.brain_id=a.brain_id '
            'WHERE a.id=? AND a.brain_id=?', (identifier, brain)).fetchone()
        if row is None:
            raise PermissionError('compose_permission_unavailable')
        return dict(row)

    def _metadata(self, connection, row):
        return _permission_metadata(self.assets, connection, row)

    def get(self, principal, authorization_id):
        brain = _brain(principal); _identifier(authorization_id); self._installed()
        with closing(self.store._conn()) as connection:
            return self._metadata(connection, self._row(connection, brain, authorization_id))

    def list(self, principal, experiment_id):
        brain = _brain(principal); _identifier(experiment_id)
        self.scope(principal, experiment_id)
        if IM._schema_version(self.store) < 8: return []
        with closing(self.store._conn()) as connection:
            identifiers = [row[0] for row in connection.execute('SELECT id FROM improvement_compose_authorizations '
                'WHERE experiment_id=? AND brain_id=? ORDER BY created_at,id LIMIT 101', (experiment_id, brain))]
            if len(identifiers) > 100:
                raise IM.ConflictError('compose_permission_history_bound')
            return [self._metadata(connection, self._row(connection, brain, identifier)) for identifier in identifiers]

    def revoke(self, principal, authorization_id, *, expected_generation, event_key):
        brain = _brain(principal); _identifier(authorization_id); _generation(expected_generation); self._installed()
        payload = {'authorization_id': authorization_id, 'expected_generation': expected_generation}
        with self.store._Tx(self.store) as connection:
            old = self.assets._replay(connection, brain, event_key, 'compose_revoke', payload)
            if old is not None: return old
            row = self._row(connection, brain, authorization_id)
            if row['generation'] != expected_generation or row['status'] != 'active':
                raise IM.ConflictError('compose_permission_stale')
            connection.execute("UPDATE improvement_compose_grants SET generation=generation+1,status='revoked',revoked_at=? "
                'WHERE authorization_id=? AND brain_id=?', (time.time(), authorization_id, brain))
            result = self._metadata(connection, self._row(connection, brain, authorization_id))
            self.assets._event(connection, principal, event_key, 'compose_revoke', payload, result)
            return result

    def _capture(self, connection, principal, experiment_id, generation):
        self._live()
        before = self.inputs._snapshot(connection, principal, experiment_id, generation)
        for comparison in before['comparisons']:
            comparison['policy'] = self.inputs.reports._policy(before['prepared'][0])
        return before

    @staticmethod
    def _authority_hash(before):
        # Exactly the producer's stable basis: retain complete current SQL
        # history, definition and binding, not process-local checker identities.
        stable = {key: value for key, value in before.items() if key != 'prepared'}
        stable['definition'] = before['prepared'][0]
        stable['binding_hash'] = before['prepared'][0]['binding_hash']
        return IM._hash(stable)

    def _load(self, brain, digest):
        _digest(digest)
        raw = self.blobs.read(brain, digest)
        try:
            value = json.loads(raw)
            if type(value) is not dict or IM._json(value).encode('utf-8') != raw:
                raise ValueError('noncanonical_compose_permission_blob')
        except (ValueError, UnicodeError, TypeError, RecursionError) as error:
            raise AssetUnavailable('compose_permission_blob_unavailable') from error
        return value

    def _input_history(self, connection, brain, metadata):
        payload = {'experiment_id': metadata['experiment_id'], 'expected_generation': metadata['experiment_generation']}
        key = 'compose-input-' + IM._hash([brain, payload])
        actual = self.assets._replay(connection, brain, key, 'compose_input', payload)
        expected = {key: metadata[key] for key in ('input_hash', 'basis_hash')}
        expected.update(input_blob_hash=metadata['input_hash'], basis_blob_hash=metadata['basis_hash'])
        if actual != expected:
            raise AssetUnavailable('compose_authorized_input_unavailable')

    def _links(self, row, metadata, guard, basis, data, before, observed, baseline):
        value = before['prepared'][0]
        if (set(guard) != {'version', 'kind', 'experiment', 'input_hash', 'basis_hash'}
                or type(guard['version']) is not int or guard['version'] != 1 or guard['kind'] != 'compose_permission_guard'
                or guard['experiment'] != before['experiment'] or guard['input_hash'] != row['input_hash']
                or guard['basis_hash'] != row['basis_hash']):
            raise IM.ConflictError('compose_permission_basis_changed')
        expected = {'version': 1, 'kind': 'compose_input_basis', 'experiment_id': row['experiment_id'],
            'context_id': row['context_id'], 'definition_hash': row['definition_hash'],
            'generation': metadata['experiment_generation'], 'source_authority_hash': observed['source_authority_hash'],
            'authority_snapshot_hash': self._authority_hash(before),
            'candidate_refs': [{key: item[key] for key in ('id', 'content_hash', 'patch_hash', 'provenance_hash')}
                               for item in before['candidates']],
            'report_refs': [{key: item['saved'][key] for key in ('id', 'report_hash', 'publication_id')}
                            for item in before['comparisons']]}
        if (basis != expected or row['definition_hash'] != IM._hash(value)
                or row['context_generation'] != value['context_generation'] or row['policy_version'] != value['policy_version']
                or any(data.get(key) != row[key] for key in ('experiment_id', 'context_id', 'definition_hash'))
                or data.get('baseline', {}).get('content', '').encode('utf-8') != baseline):
            raise IM.ConflictError('compose_authorized_input_changed')
        render_compose_input(data)

    def _fence(self, connection, principal, before, observed):
        self.inputs._fence(connection, principal, before)
        value = before['prepared'][0]
        for comparison in before['comparisons']:
            if self.inputs.reports._policy(value) != comparison['policy']:
                raise IM.ConflictError('compose_policy_changed')
            self.inputs.reports._guard(connection, principal, comparison['metadata'], before['experiment']['generation'])
        self.plans.authoring._guard(connection, principal, before['authoring'], observed)
        self.inputs._fence(connection, principal, before)

    def current(self, connection, principal, authorization_id, *, operation=None):
        self._live()
        brain = _brain(principal); _identifier(authorization_id); self._connection(connection)
        require_product_store(self.assets, principal, connection=connection)
        assert_installed(connection)
        row = self._row(connection, brain, authorization_id)
        if row['status'] != 'active' or row['generation'] != 1:
            raise PermissionError('compose_permission_revoked')
        metadata = self._metadata(connection, row)
        generation = metadata['experiment_generation']
        request = None
        if operation is not None:
            request = json.loads(operation['request_json'])
            if request.get('compose_authorization_id') != authorization_id:
                raise IM.ConflictError('compose_operation_permission_changed')
            operation_permission(connection, self.assets, principal, request, operation=operation)
            generation += 1
        before = self._capture(connection, principal, row['experiment_id'], generation)
        data, basis, guard = (self._load(brain, metadata[key]) for key in ('input_hash', 'basis_hash', 'guard_blob_hash'))
        self._input_history(connection, brain, metadata)
        observed, baseline = self.plans.authoring.observe(principal, before['authoring']['target'])
        authority = before
        if operation is not None:
            original = guard.get('experiment')
            if (type(original) is not dict or before['experiment'] !=
                    {**original, 'generation': generation, 'updated_at': operation['created_at']}):
                raise IM.ConflictError('compose_operation_experiment_changed')
            authority = {**before, 'experiment': original}
        self._links(row, metadata, guard, basis, data, authority, observed, baseline)
        # Capturing includes policy-file reads. Finish all such reads before
        # the source guards and final SQL-only consent/state checks.
        if self._capture(connection, principal, row['experiment_id'], generation) != before:
            raise IM.ConflictError('compose_authority_changed')
        self._fence(connection, principal, before, observed)
        self.inputs._fence(connection, principal, before)
        # No further policy/blob/host observations after this final SQL fence.
        if self._row(connection, brain, authorization_id) != row:
            raise IM.ConflictError('compose_permission_changed')
        if operation is not None:
            operation_permission(connection, self.assets, principal, request, operation=operation)
        require_product_store(self.assets, principal, connection=connection)
        self._live()
        return {'authorization': metadata, 'data': data, 'basis': basis, 'prepared': before['prepared'], 'snapshot': before}

    def authorize(self, principal, experiment_id, *, expected_generation, event_key):
        self._live()
        brain = _brain(principal); _identifier(experiment_id); _generation(expected_generation); self._installed()
        require_product_store(self.assets, principal)
        payload = {'experiment_id': experiment_id, 'expected_generation': expected_generation}
        with closing(self.store._conn()) as connection:
            old = self.assets._replay(connection, brain, event_key, 'compose_authorize', payload)
            if old is not None:
                return self._metadata(connection, self._row(connection, brain, old['authorization_id']))
            assert_installed(connection)
            before = self._capture(connection, principal, experiment_id, expected_generation)
            if connection.execute("SELECT 1 FROM improvement_operations WHERE experiment_id=? AND brain_id=? AND kind='compose'",
                                  (experiment_id, brain)).fetchone():
                raise IM.ConflictError('compose_already_recorded')
        built = self.inputs.build(principal, experiment_id, expected_generation=expected_generation)
        guard = {'version': 1, 'kind': 'compose_permission_guard', 'experiment': before['experiment'],
                 'input_hash': built['input_hash'], 'basis_hash': built['basis_hash']}
        guard_blob = self.blobs.write(brain, input_bytes(guard))
        value, stamp = before['prepared'][0], time.time()
        with self.store._Tx(self.store) as connection:
            old = self.assets._replay(connection, brain, event_key, 'compose_authorize', payload)
            if old is not None:
                return self._metadata(connection, self._row(connection, brain, old['authorization_id']))
            self.inputs._fence(connection, principal, before)
            self._live()
            identifier = 'icpa_' + secrets.token_hex(12)
            connection.execute('INSERT INTO improvement_compose_authorizations VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (identifier, brain, experiment_id, value['context_id'], IM._hash(value), built['input_hash'], built['basis_hash'],
                 value['context_generation'], value['policy_version'], principal.by, stamp))
            connection.execute("INSERT INTO improvement_compose_grants VALUES(?,?,1,'active',NULL)", (identifier, brain))
            metadata = {'authorization_id': identifier, 'experiment_id': experiment_id, 'context_id': value['context_id'],
                'input_hash': built['input_hash'], 'basis_hash': built['basis_hash'], 'guard_blob_hash': guard_blob,
                'experiment_generation': expected_generation, 'generation': 1, 'status': 'active'}
            self.assets._event(connection, principal, event_key, 'compose_authorize', payload, metadata)
            return self.current(connection, principal, identifier)['authorization']
