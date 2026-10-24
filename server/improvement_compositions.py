"""One owned compose workflow over the existing native roles and candidate store.

The actual pinned Harness² renderer is consumed by OperationProfile. This owner
adds no executor, account, ledger or qualification authority. A composed draft
still needs independent semantic/owner/bundle/tuning/final checks before use.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import time
from contextlib import closing

import improvement_store as IM
from improvement_compose_candidates import decisions_document, prepare, insert
from improvement_compose_permissions import ComposePermissions, operation_permission
from improvement_compose_protocol import parse_compose_output
from improvement_experiments import _generation, _identifier
from improvement_generation_protocol import input_bytes
from improvement_operation_adapter import ClaudeOperationAdapter
from improvement_operation_schema import TERMINAL
from improvement_qualification_records import require_product_store
from improvement_role_workflow import RoleWorkflow
from improvement_trial_records import _brain
from improvement_trial_runner import _settled_call


class ComposerService(RoleWorkflow):
    _product_kinds = frozenset({'compose'})

    def __init__(self, execution, tasks):
        super().__init__(execution, tasks)
        self.permissions = ComposePermissions(self.plans, owner=self)

    @staticmethod
    def _start_key(brain, event_key):
        return 'compose-start-' + IM._hash([brain, event_key])

    def _begin(self, principal, payload, event_key):
        brain = _brain(principal)
        require_product_store(self.assets, principal)
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, brain, event_key, 'compose_generate', payload)
            if replay is not None:
                return {'replay': replay}
            prior = self.assets._replay(connection, brain, self._start_key(brain, event_key), 'compose_generate_start', payload)
            if prior is not None:
                row = self.execution._row(connection, principal, prior['operation_id'])
                return {'replay': {**prior, 'status': 'operation_recorded', 'operation_status': row['status']}}
            current = self.permissions.current(connection, principal, payload['authorization_id'])
        authorization = current['authorization']
        if authorization['experiment_generation'] != payload['expected_generation']:
            raise IM.ConflictError('compose_permission_generation_changed')
        self._open()
        from improvement_native_formats import input_version
        binding = current['prepared'][1]
        if input_version(binding['engine_config'], 'operation') != 2:
            raise ValueError('compose_native_input2_required')

        def native_current(connection, joined):
            self._open()
            self.plans.host._snapshot_observe(principal, binding)
            if self.permissions.current(connection, principal, payload['authorization_id']) != current:
                raise IM.ConflictError('compose_admission_changed')
            return 'allow'

        adapter = ClaudeOperationAdapter(binding['engine_config'])
        adapter.bind_native_authority(self.assets, principal, scope_hash=IM._hash({
            'version': 1, 'kind': 'compose_generation_admission', 'brain_id': brain,
            'request_hash': IM._hash(payload), 'event_key_hash': IM._hash(event_key),
            'input_hash': authorization['input_hash'], 'basis_hash': authorization['basis_hash']}), current=native_current)
        available = adapter.verify()
        if type(available) is not dict or available.get('supported') is not True:
            raise ValueError('operation_native_unavailable')
        self._open()
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, 'compose_generate', payload)
            if replay is not None:
                return {'replay': replay}
            prior = self.assets._replay(connection, brain, self._start_key(brain, event_key), 'compose_generate_start', payload)
            if prior is not None:
                row = self.execution._row(connection, principal, prior['operation_id'])
                return {'replay': {**prior, 'status': 'operation_recorded', 'operation_status': row['status']}}
            if self.permissions.current(connection, principal, payload['authorization_id']) != current:
                raise IM.ConflictError('compose_admission_changed')
            data = current['data']
            request = {'version': 2, 'experiment_id': authorization['experiment_id'], 'context_id': authorization['context_id'],
                'definition_hash': data['definition_hash'], 'kind': 'compose', 'role': 'composer', 'purpose': 'improve_compose',
                'candidate_id': None, 'parent_id': None, 'input_hash': authorization['input_hash'],
                'compose_authorization_id': authorization['authorization_id']}
            operation = self.execution.records._create_in(connection, principal, request, authorization['input_hash'],
                expected_generation=payload['expected_generation'], event_key='compose-operation-' + IM._hash([brain, event_key]))
            started = {'authorization_id': authorization['authorization_id'], 'experiment_id': authorization['experiment_id'],
                'operation_id': operation['operation_id'], 'input_hash': authorization['input_hash'],
                'generation': payload['expected_generation'] + 1}
            self.assets._event(connection, principal, self._start_key(brain, event_key), 'compose_generate_start', payload, started)
            row = self.execution._row(connection, principal, operation['operation_id'])
            after = self.permissions.current(connection, principal, payload['authorization_id'], operation=row)
            if after['data'] != data or after['authorization'] != authorization:
                raise IM.ConflictError('compose_admission_changed')
            self._open()
            return {**started, 'data': data}

    def _product(self, connection, principal, identifier):
        product = super()._product(connection, principal, identifier)
        if product['report']['version'] != 2:
            raise PermissionError('compose_native_result2_required')
        return product

    def _outcome(self, principal, payload, event_key, identifier, status):
        with self.store._Tx(self.store) as connection:
            require_product_store(self.assets, principal, connection=connection)
            old = self.assets._replay(connection, _brain(principal), event_key, 'compose_generate', payload)
            if old is not None:
                return old
            row = self.execution._row(connection, principal, identifier)
            if row['kind'] != 'compose' or row['status'] not in TERMINAL:
                raise IM.ConflictError('compose_operation_incomplete')
            experiment = self.plans.records._row(connection, _brain(principal), row['experiment_id'])
            result = {'authorization_id': payload['authorization_id'], 'experiment_id': row['experiment_id'],
                'operation_id': identifier, 'status': status, 'candidates': [], 'generation': experiment['generation'],
                'business_proof': False}
            self.assets._event(connection, principal, event_key, 'compose_generate', payload, result)
            require_product_store(self.assets, principal, connection=connection)
            return result

    def _publish(self, principal, payload, event_key, begun, product):
        brain = _brain(principal)
        with self.store._Tx(self.store) as connection:
            require_product_store(self.assets, principal, connection=connection)
            old = self.assets._replay(connection, brain, event_key, 'compose_generate', payload)
            if old is not None:
                return old
            self._open()
            row = self.execution._row(connection, principal, begun['operation_id'])
            current = self.permissions.current(connection, principal, payload['authorization_id'], operation=row)
            authorization = current['authorization']
            if (current['data'] != begun['data'] or product['row']['id'] != row['id']
                    or product['row']['input_hash'] != authorization['input_hash']
                    or self._product(connection, principal, row['id']) != product):
                raise IM.ConflictError('compose_product_changed')
            parsed = parse_compose_output(product['raw'], current['data'])
            identifier, stamp = 'icomp_' + secrets.token_hex(12), time.time()
            decisions = self.blobs.write(brain, input_bytes(decisions_document(identifier, authorization, product, parsed)))
            state = current['snapshot']['authoring']
            observed, raw = self.plans.authoring.observe(principal, state['target'])
            draft = None if parsed['keep_base'] else prepare(self.plans.authoring, connection, principal,
                state, observed, raw, parsed, composition_id=identifier, event_key=event_key, stamp=stamp)
            publication = {'id': identifier, 'brain_id': brain, 'experiment_id': authorization['experiment_id'],
                'operation_id': row['id'], 'result_id': product['record']['id'], 'authorization_id': authorization['authorization_id'],
                'input_hash': authorization['input_hash'], 'basis_hash': authorization['basis_hash'],
                'output_hash': product['record']['blob_hash'], 'decisions_hash': decisions, 'decisions_blob_hash': decisions,
                'outcome': 'keep_base' if parsed['keep_base'] else 'candidate',
                'candidate_id': None if draft is None else draft['id'],
                **{key: None if draft is None else draft[key] for key in ('content_hash', 'patch_hash', 'provenance_hash')},
                'created_at': stamp}
            fields = tuple(publication)
            connection.execute('INSERT INTO improvement_compositions (' + ','.join(fields) + ') VALUES('
                + ','.join('?' for _ in fields) + ')', tuple(publication.values()))
            candidates = [] if draft is None else [insert(self.plans.authoring, connection, principal, identifier, draft)]
            result = {'authorization_id': authorization['authorization_id'], 'experiment_id': authorization['experiment_id'],
                'operation_id': row['id'], 'result_id': product['record']['id'], 'composition_id': identifier,
                'status': 'keep_base' if parsed['keep_base'] else 'candidate_staged', 'candidates': candidates,
                'generation': begun['generation'] + 1, 'business_proof': False}
            self.assets._event(connection, principal, event_key, 'compose_generate', payload, result)
            self._product_fence(connection, principal, product)
            if draft is not None:
                self.plans.authoring.read_proposal(connection, principal,
                    self.plans.authoring.records._row(connection, brain, draft['id']), state, observed, raw)
            # All event/blob/product/source reads and final source observations
            # precede the SQL-only product/input/consent/domain CAS below.
            final = self.permissions.current(connection, principal, payload['authorization_id'], operation=row)
            if final != current:
                raise IM.ConflictError('compose_publication_changed')
            self._product_fence(connection, principal, product)
            self.permissions.inputs._fence(connection, principal, final['snapshot'])
            operation_permission(connection, self.assets, principal, json.loads(row['request_json']), operation=row)
            self._open()
            connection.execute('UPDATE improvement_experiments SET generation=generation+1,updated_at=? WHERE id=? AND brain_id=?',
                (stamp, authorization['experiment_id'], brain))
            return result

    async def _compose(self, principal, payload, event_key):
        begun = await _settled_call(self._begin, principal, payload, event_key)
        if 'replay' in begun:
            return begun['replay']
        identifier = begun['operation_id']
        try:
            self._open()
            await self.tasks.start(principal, identifier, expected_generation=1,
                event_key='compose-native-' + IM._hash([_brain(principal), event_key]))
            result = await self.tasks.join(principal, identifier)
            self._open()
            if result['status'] != 'completed':
                return await _settled_call(self._outcome, principal, payload, event_key, identifier, 'native_incomplete')
            try:
                product = await _settled_call(self._read_product, principal, identifier)
            except PermissionError:
                return await _settled_call(self._outcome, principal, payload, event_key, identifier, 'native_incomplete')
            try:
                parse_compose_output(product['raw'], begun['data'])
            except (ValueError, TypeError, PermissionError, KeyError, UnicodeError, RecursionError):
                return await _settled_call(self._outcome, principal, payload, event_key, identifier, 'invalid_output')
            return await _settled_call(self._publish, principal, payload, event_key, begun, product)
        finally:
            if self._closed:
                row = await asyncio.to_thread(self.execution.get, principal, identifier)
                if row['status'] not in TERMINAL:
                    await _settled_call(self.execution.cancel, principal, identifier, expected_generation=row['generation'],
                        event_key='compose-close-' + IM._hash([_brain(principal), identifier]))

    async def compose(self, principal, authorization_id, *, expected_generation, event_key):
        self._bind(); self._open()
        _identifier(authorization_id); _generation(expected_generation)
        if type(event_key) is not str or not 8 <= len(event_key) <= 160:
            raise ValueError('invalid_event_key')
        payload = {'authorization_id': authorization_id, 'expected_generation': expected_generation}
        return await self._run_owned(principal, authorization_id, event_key, payload,
            lambda: self._compose(principal, payload, event_key))
