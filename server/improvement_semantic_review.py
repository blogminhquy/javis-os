"""Actual isolated semantic role and immutable evidence; never activation authority."""
from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import time
from contextlib import closing
from pathlib import Path

import improvement_store as IM
from improvement_dependency_evidence import dependency_evidence
from improvement_experiments import _generation, _identifier
from improvement_generation_protocol import input_bytes
from improvement_operation_adapter import ClaudeOperationAdapter
from improvement_operation_schema import TERMINAL, assert_installed
from improvement_role_workflow import RoleWorkflow
from improvement_semantic_protocol import semantic_output, combined_verdict
from improvement_semantic_records import SemanticReceipts
from improvement_trial_records import _brain
from improvement_trial_runner import _settled_call


def validator_hash():
    root = Path(__file__).parent
    return IM._hash({name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in
        ('improvement_semantic_review.py', 'improvement_semantic_protocol.py', 'improvement_dependency_evidence.py',
         'improvement_role_workflow.py', 'improvement_skill_patch.py', 'improvement_semantic_records.py')})


def _native_report_evidence(report):
    from improvement_role_workflow import _product_checks
    _product_checks(report)
    return {'native_verdict': report['verdict'], 'native_checks': report['checks'],
        **({'native_result_version': 2} if report['version'] == 2 else {})}


class SemanticReview(RoleWorkflow):
    _product_kinds = frozenset({'semantic'})

    def __init__(self, execution, tasks):
        super().__init__(execution, tasks)
        self.records = SemanticReceipts(self.assets)

    def history(self, principal, candidate_id):
        return self.records.history(principal, candidate_id)

    def _snapshot(self, principal, candidate_id, generation, *, unsealed=True):
        brain = _brain(principal)
        with closing(self.store._conn()) as connection:
            candidate = self.plans.authoring.records._row(connection, brain, candidate_id)
            # Check the actual source grant/policy before decrypting context or A.
            state = self.plans.authoring._state(connection, principal, candidate['experiment_id'], candidate['target_id'],
                                                candidate['base_revision_id'], candidate['base_hash'])
            row, prepared = self.plans._state(connection, principal, candidate['experiment_id'], generation,
                                               unsealed=unsealed, source_split='tuning')
            value, binding = prepared[:2]
            if any(candidate[key] != value[key] for key in ('experiment_id', 'context_id', 'target_id', 'base_revision_id', 'base_hash', 'base_generation')):
                raise IM.ConflictError('semantic_candidate_scope_changed')
        observed, before = self.plans.authoring.observe(principal, state['target'])
        with closing(self.store._conn()) as connection:
            proposal = self.plans.authoring.read_proposal(connection, principal, candidate, state, observed, before)
        dependencies = dependency_evidence(binding['capture'], state['target']['canonical_ref'], proposal['before'], proposal['after'],
            candidate_root=Path(_brain(principal)))
        pins = {'version': 1, 'validator_hash': validator_hash(), 'candidate_id': candidate_id,
            **{key: candidate[key] for key in ('experiment_id', 'context_id', 'target_id', 'base_revision_id', 'base_hash',
                'base_generation', 'content_hash', 'patch_hash', 'provenance_hash')},
            **{key: value[key] for key in ('binding_hash', 'baseline_context_hash', 'engine_config_hash', 'grant_hash',
                'scope_hash', 'context_generation', 'policy_version', 'evaluator')},
            'definition_hash': IM._hash(value), 'source_authority_hash': observed['source_authority_hash'],
            'dependency_hash': IM._hash(dependencies)}
        refs = [{'kind': 'candidate', 'id': candidate_id}, {'kind': 'baseline_revision', 'id': candidate['base_revision_id']},
                {'kind': 'protected_context', 'id': value['baseline_context_hash']}]
        refs += [{'kind': 'dependency', 'id': node['ref']} for node in dependencies['nodes']]
        data = {'version': 1, 'kind': 'authorized_semantic_review', 'binding': pins,
            'candidate': {'id': candidate_id, 'before': proposal['before'].decode('utf-8'), 'after': proposal['after'].decode('utf-8'),
                'patch': proposal['patch'], 'semantic_status': 'unreviewed'},
            'protected_context': binding['capture']['baseline_context'], 'dependencies': dependencies,
            'engine_config': binding['engine_config'], 'source_refs': refs, 'business_proof': False}
        input_bytes(data)
        self.plans.host._snapshot_observe(principal, binding)
        with closing(self.store._conn()) as connection:
            self.plans.authoring._guard(connection, principal, state, observed)
        return {'candidate': dict(candidate), 'prepared': prepared, 'authoring': state, 'observed': observed,
                'data': data, 'binding': pins, 'dependencies': dependencies}

    def _fence(self, connection, principal, snapshot, generation, *, unsealed=True):
        self._open()
        assert_installed(connection)
        brain, value = _brain(principal), snapshot['prepared'][0]
        row = self.plans.records._row(connection, brain, value['experiment_id'])
        allowed = ('proposing', 'probing', 'comparing') if unsealed else ('proposing', 'probing', 'comparing', 'qualifying', 'awaiting_apply')
        if (row['generation'] != generation or row['phase'] not in allowed
                or row['definition_hash'] != IM._hash(value)):
            raise IM.ConflictError('semantic_experiment_changed')
        if unsealed and connection.execute('SELECT 1 FROM improvement_experiment_selections WHERE brain_id=? AND experiment_id=?', (brain, row['id'])).fetchone():
            raise IM.ConflictError('experiment_sealed')
        self.plans.records._bound_in(connection, brain, value, value['context_generation'])
        candidate = self.plans.authoring.records._row(connection, brain, snapshot['candidate']['id'])
        if dict(candidate) != snapshot['candidate']:
            raise IM.ConflictError('semantic_candidate_changed')
        current = self.plans.authoring._state(connection, principal, row['id'], candidate['target_id'], candidate['base_revision_id'], candidate['base_hash'])
        if current != snapshot['authoring']:
            raise IM.ConflictError('semantic_authority_changed')

    @staticmethod
    def _start_key(brain, event_key):
        return 'semantic-start-' + IM._hash([brain, event_key])

    def _begin(self, principal, payload, event_key):
        brain = _brain(principal)
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, brain, event_key, 'semantic_review', payload)
            if replay is not None:
                return {'replay': replay}
            prior = self.assets._replay(connection, brain, self._start_key(brain, event_key), 'semantic_review_start', payload)
            if prior is not None:
                row = self.execution._row(connection, principal, prior['operation_id'])
                return {'replay': {**prior, 'status': 'operation_recorded', 'operation_status': row['status']}}
            if connection.execute("SELECT 1 FROM improvement_operations WHERE brain_id=? AND candidate_id=? AND kind='semantic'", (brain, payload['candidate_id'])).fetchone():
                raise IM.ConflictError('semantic_already_requested')
            assert_installed(connection)
        snapshot = self._snapshot(principal, payload['candidate_id'], payload['expected_generation'])
        self._open()
        def native_current(connection, joined):
            for _ in range(2):
                self._fence(connection, principal, snapshot, payload['expected_generation'])
                if self._snapshot(principal, payload['candidate_id'], payload['expected_generation']) != snapshot:
                    raise IM.ConflictError('semantic_input_changed')
                self._fence(connection, principal, snapshot, payload['expected_generation'])
            return 'allow'

        adapter = ClaudeOperationAdapter(snapshot['prepared'][1]['engine_config'])
        adapter.bind_native_authority(self.assets, principal, scope_hash=IM._hash({
            'version': 1, 'kind': 'semantic_review_admission', 'brain_id': brain,
            'event_key_hash': IM._hash(event_key), 'request_hash': IM._hash(payload),
            'authority_hash': IM._hash([snapshot['binding'], IM._hash(snapshot['data'])])}), current=native_current)
        available = adapter.verify()
        if type(available) is not dict or available.get('supported') is not True:
            raise ValueError('operation_native_unavailable')
        blob = self.blobs.write(brain, input_bytes(snapshot['data']))
        if self._snapshot(principal, payload['candidate_id'], payload['expected_generation']) != snapshot:
            raise IM.ConflictError('semantic_input_changed')
        with self.store._Tx(self.store) as connection:
            prior = self.assets._replay(connection, brain, self._start_key(brain, event_key), 'semantic_review_start', payload)
            if prior is not None:
                return {'replay': {**prior, 'status': 'operation_recorded'}}
            self._fence(connection, principal, snapshot, payload['expected_generation'])
            binding = snapshot['binding']
            request = {'version': 1, 'experiment_id': binding['experiment_id'], 'context_id': binding['context_id'],
                'definition_hash': binding['definition_hash'], 'kind': 'semantic', 'role': 'semantic_reviewer', 'purpose': 'improve_evaluate',
                'candidate_id': payload['candidate_id'], 'parent_id': None, 'input_hash': blob}
            row = self.execution.records._create_in(connection, principal, request, blob,
                expected_generation=payload['expected_generation'], event_key='semantic-operation-' + IM._hash([brain, event_key]))
            result = {'candidate_id': payload['candidate_id'], 'experiment_id': binding['experiment_id'],
                'operation_id': row['operation_id'], 'input_hash': blob, 'generation': payload['expected_generation'] + 1}
            self.assets._event(connection, principal, self._start_key(brain, event_key), 'semantic_review_start', payload, result)
            return {'snapshot': snapshot, **result}

    def _publish(self, principal, payload, event_key, begun, product):
        brain, identifier = _brain(principal), payload['candidate_id']
        snapshot = self._snapshot(principal, identifier, begun['generation'])
        if snapshot != begun['snapshot']:
            raise IM.ConflictError('semantic_source_changed')
        if product['row']['candidate_id'] != identifier or product['row']['input_hash'] != IM._hash(snapshot['data']):
            raise IM.ConflictError('semantic_input_changed')
        try:
            assessment = semantic_output(product['raw'], snapshot['data'])
        except (ValueError, TypeError, PermissionError, KeyError, UnicodeError, RecursionError):
            return self._invalid_output(principal, payload, event_key, begun, product)
        verdict = combined_verdict(assessment['verdict'], snapshot['dependencies']['verdict'], product['report']['verdict'])
        evidence = {'version': 1, 'candidate_id': identifier, 'binding': snapshot['binding'], 'assessment': assessment,
            'dependencies': snapshot['dependencies'], 'operation_id': product['row']['id'], 'result_id': product['record']['id'],
            **_native_report_evidence(product['report']),
            'native_refs': {'result_hash': product['record']['result_hash'], 'input_hash': product['row']['input_hash'],
                'artifact_hash': product['report']['artifact']['hash'], 'installation_hash': product['report']['installation']['hash'],
                'call_id': product['call']['id'], 'trace_hash': IM._hash(product['report']['trace_hashes'])},
            'usage': product['report']['usage'], 'verdict': verdict, 'business_proof': False, 'semantic_status': 'unreviewed'}
        blob = self.blobs.write(brain, input_bytes(evidence))
        binding_blob = self.blobs.write(brain, input_bytes(snapshot['binding']))
        if self._snapshot(principal, identifier, begun['generation']) != snapshot:
            raise IM.ConflictError('semantic_source_changed')
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, 'semantic_review', payload)
            if replay is not None:
                return replay
            self._fence(connection, principal, snapshot, begun['generation'])
            self._product_fence(connection, principal, product)
            receipt_id = 'isr_' + secrets.token_hex(12)
            connection.execute('INSERT INTO improvement_semantic_receipts VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (receipt_id, brain, begun['experiment_id'], identifier, product['row']['id'], product['record']['id'],
                 IM._hash(snapshot['binding']), binding_blob, IM._hash(assessment), blob, time.time()))
            result = {'receipt_id': receipt_id, 'candidate_id': identifier, 'operation_id': product['row']['id'],
                'result_id': product['record']['id'], 'binding_hash': binding_blob, 'assessment_hash': IM._hash(assessment),
                'blob_hash': blob, 'verdict': verdict, 'native_verdict': product['report']['verdict'], 'semantic_status': 'unreviewed'}
            self.assets._event(connection, principal, event_key, 'semantic_review', payload, result)
            return result

    def _invalid_output(self, principal, payload, event_key, begun, product):
        # Preserve the raw native product without manufacturing an assessment,
        # receipt or retry. A completed native call is not a valid review.
        snapshot = self._snapshot(principal, payload['candidate_id'], begun['generation'])
        if snapshot != begun['snapshot']:
            raise IM.ConflictError('semantic_source_changed')
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, _brain(principal), event_key, 'semantic_review', payload)
            if replay is not None:
                return replay
            self._fence(connection, principal, snapshot, begun['generation'])
            self._product_fence(connection, principal, product)
            result = {'candidate_id': payload['candidate_id'], 'experiment_id': begun['experiment_id'],
                'operation_id': product['row']['id'], 'result_id': product['record']['id'],
                'status': 'invalid_output', 'native_verdict': product['report']['verdict'], 'business_proof': False}
            self.assets._event(connection, principal, event_key, 'semantic_review', payload, result)
            return result

    async def _review(self, principal, payload, event_key):
        begun = await _settled_call(self._begin, principal, payload, event_key)
        if 'replay' in begun:
            return begun['replay']
        identifier = begun['operation_id']
        try:
            self._open()
            await self.tasks.start(principal, identifier, expected_generation=1,
                event_key='semantic-native-' + IM._hash([_brain(principal), event_key]))
            result = await self.tasks.join(principal, identifier)
            self._open()
            if result['status'] != 'completed':
                raise IM.ConflictError('semantic_native_incomplete')
            product = await _settled_call(self._read_product, principal, identifier)
            return await _settled_call(self._publish, principal, payload, event_key, begun, product)
        finally:
            if self._closed:
                row = await asyncio.to_thread(self.execution.get, principal, identifier)
                if row['status'] not in TERMINAL:
                    await _settled_call(self.execution.cancel, principal, identifier, expected_generation=row['generation'],
                        event_key='semantic-close-' + IM._hash([_brain(principal), identifier]))

    async def review(self, principal, candidate_id, *, expected_generation, event_key):
        self._bind()
        self._open()
        _identifier(candidate_id)
        _generation(expected_generation)
        if type(event_key) is not str or not 8 <= len(event_key) <= 160:
            raise ValueError('invalid_event_key')
        with closing(self.store._conn()) as connection:
            candidate = self.plans.authoring.records._row(connection, _brain(principal), candidate_id)
        payload = {'candidate_id': candidate_id, 'expected_generation': expected_generation}
        return await self._run_owned(principal, candidate['experiment_id'], event_key, payload,
                                     lambda: self._review(principal, payload, event_key))

    def current_evidence(self, principal, candidate_id, receipt_id=None, *, expected_generation=None):
        with closing(self.store._conn()) as connection:
            self.records.row(connection, principal, candidate_id, receipt_id)
            candidate = self.plans.authoring.records._row(connection, _brain(principal), candidate_id)
            experiment = self.plans.records._row(connection, _brain(principal), candidate['experiment_id'])
            generation = experiment['generation']
            if expected_generation is not None:
                _generation(expected_generation)
                if generation != expected_generation:
                    raise IM.ConflictError('experiment_state_stale')
        snapshot = self._snapshot(principal, candidate_id, generation, unsealed=False)
        metadata, evidence = self.records.read(principal, candidate_id, receipt_id)
        if snapshot['binding'] != evidence['binding'] or snapshot['dependencies'] != evidence['dependencies']:
            raise IM.ConflictError('semantic_evidence_stale')
        with closing(self.store._conn()) as connection:
            self._fence(connection, principal, snapshot, generation, unsealed=False)
            product = self._product(connection, principal, evidence['operation_id'])
            if (product['record']['id'] != metadata['result_id'] or product['record']['result_hash'] != evidence['native_refs']['result_hash']
                    or product['row']['input_hash'] != IM._hash(snapshot['data'])
                    or semantic_output(product['raw'], snapshot['data']) != evidence['assessment']
                    or {key: evidence[key] for key in ('native_verdict', 'native_checks', 'native_result_version') if key in evidence}
                        != _native_report_evidence(product['report'])):
                raise IM.ConflictError('semantic_native_evidence_changed')
            decisions = [json.loads(row[0]) for row in connection.execute("SELECT result_json FROM improvement_events "
                "WHERE brain_id=? AND operation='semantic_owner_arbitration' ORDER BY id", (_brain(principal),))]
            decisions = [item for item in decisions if item['receipt_id'] == metadata['receipt_id'] and item['binding_hash'] == metadata['binding_hash']]
        owner = decisions[-1] if decisions else None
        if owner is not None:
            reason = json.loads(self.blobs.read(_brain(principal), owner['reason_blob_hash']))
            if IM._hash(reason) != owner['reason_blob_hash'] or set(reason) != {'reason'}:
                raise IM.ConflictError('semantic_owner_reason_changed')
            owner = {**owner, 'reason': reason['reason']}
        # Product/owner reason reads above may outlive the first source capture.
        if self._snapshot(principal, candidate_id, generation, unsealed=False) != snapshot:
            raise IM.ConflictError('semantic_evidence_stale')
        with closing(self.store._conn()) as connection:
            self._fence(connection, principal, snapshot, generation, unsealed=False)
            self._product_fence(connection, principal, product)
        return {**evidence, **metadata, 'owner_assessment': owner,
            'verdict': combined_verdict(evidence['assessment']['verdict'], evidence['dependencies']['verdict'],
                                        evidence['native_verdict'], owner['verdict'] if owner else None)}

    def arbitrate(self, principal, candidate_id, receipt_id, *, verdict, reason, expected_binding_hash, event_key, expected_generation=None):
        from improvement_cases import _text, _digest
        brain = _brain(principal)
        _identifier(candidate_id)
        _identifier(receipt_id)
        _digest(expected_binding_hash)
        _text(reason, 4000)
        if verdict not in ('pass', 'fail', 'unknown'):
            raise ValueError('invalid_semantic_owner_verdict')
        payload = {'candidate_id': candidate_id, 'receipt_id': receipt_id, 'verdict': verdict,
                   'reason': reason, 'binding_hash': expected_binding_hash}
        if expected_generation is not None:
            _generation(expected_generation)
            payload['expected_generation'] = expected_generation
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, brain, event_key, 'semantic_owner_arbitration', payload)
            if replay is not None:
                return replay
        current = self.current_evidence(principal, candidate_id, receipt_id, expected_generation=expected_generation)
        if current['binding_hash'] != expected_binding_hash:
            raise IM.ConflictError('semantic_arbitration_binding_changed')
        with closing(self.store._conn()) as connection:
            row = self.plans.records._row(connection, brain, current['binding']['experiment_id'])
            generation = row['generation']
            if expected_generation is not None and generation != expected_generation:
                raise IM.ConflictError('experiment_state_stale')
        snapshot = self._snapshot(principal, candidate_id, generation)
        if snapshot['binding'] != current['binding']:
            raise IM.ConflictError('semantic_arbitration_binding_changed')
        product = self._read_product(principal, current['operation_id'])
        if product['record']['id'] != current['result_id']:
            raise IM.ConflictError('semantic_arbitration_result_changed')
        reason_blob = self.blobs.write(brain, input_bytes({'reason': reason}))
        if self._snapshot(principal, candidate_id, generation) != snapshot:
            raise IM.ConflictError('semantic_arbitration_binding_changed')
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, 'semantic_owner_arbitration', payload)
            if replay is not None:
                return replay
            self._fence(connection, principal, snapshot, generation)
            self._product_fence(connection, principal, product)
            result = {key: value for key, value in payload.items() if key != 'reason'}
            result.update(reason_blob_hash=reason_blob, actor=principal.by, arbitration_hash=IM._hash([brain, event_key, payload]))
            self.assets._event(connection, principal, event_key, 'semantic_owner_arbitration', payload, result)
            return result
