"""Current host-owned two-arm tuning input for the actual upstream composer.

Publishes encrypted input/basis metadata only. No model call, compose allowance,
candidate, executable bundle, inherited assessment or activation is created.
"""
from __future__ import annotations

import json
import time
from contextlib import closing

import improvement_cases as IC
import improvement_store as IM
from improvement_blobs import AssetUnavailable
from improvement_comparison_plans import ExperimentPlans
from improvement_comparison_results import ComparisonResults
from improvement_compose_protocol import render_compose_input
from improvement_experiment_lineage import current_fences
from improvement_experiments import _identifier, _generation
from improvement_generation_protocol import input_bytes
from improvement_improver_inputs import _bytes, project_packet
from improvement_qualification_records import require_product_store
from improvement_result_domain import require_product_report
from improvement_skill_patch import body_layout
from improvement_trial_evidence import decode_trace
from improvement_trial_records import _brain


class ComposeInputs:
    def __init__(self, plans):
        if type(plans) is not ExperimentPlans:
            raise TypeError('concrete_compose_plans_required')
        self.plans, self.assets, self.store, self.blobs = plans, plans.assets, plans.store, plans.blobs
        self.reports = ComparisonResults(plans)
        self.cases = IC.CaseStore(self.assets)

    @staticmethod
    def _holdout(connection, brain, value):
        from improvement_experiment_qualification import require_tuning_families
        require_tuning_families(connection, brain, value['case_set_id'])

    @staticmethod
    def _children(connection, brain, captured):
        children, trace_count = [], 0
        for item in captured:
            if item is None or item['attempt'] is None:
                raise PermissionError('compose_tuning_incomplete')
            identity = (item['trial']['id'], brain, item['attempt']['attempt'])
            value = {}
            call = connection.execute('SELECT * FROM agent_calls WHERE id=?', (item['attempt']['call_id'],)).fetchone()
            if (item['trial']['status'] != 'completed' or item['attempt']['status'] != 'completed'
                    or call is None or call['status'] != 'ok' or call['brain_id'] != brain
                    or item['attempt']['engine_at'] is None or call['engine_at'] != item['attempt']['engine_at']
                    or call['attempt'] != identity[2] or call['purpose'] != 'improve_probe'
                    or call['reason_ref'] != 'improvement_trial:' + identity[0] + ':attempt:' + str(identity[2])
                    or call['mirror_ref'] != 'improvement_trial:' + identity[0]
                    or call['context_ref'] != 'improvement:' + item['request']['pins']['experiment_id']):
                raise PermissionError('compose_trial_call_incomplete')
            value['call'] = dict(call)
            for name in ('artifacts', 'receipts'):
                row = connection.execute('SELECT * FROM improvement_trial_' + name +
                    ' WHERE trial_id=? AND brain_id=? AND attempt=?', identity).fetchone()
                value[name] = None if row is None else dict(row)
            value['trace'] = [dict(row) for row in connection.execute('SELECT * FROM improvement_trial_observations '
                'WHERE trial_id=? AND brain_id=? AND attempt=? ORDER BY sequence LIMIT 12001', identity)]
            trace_count += len(value['trace'])
            if trace_count > 12000:
                raise ValueError('compose_trace_projection_too_large')
            children.append(value)
        return children

    def _snapshot(self, connection, principal, identifier, generation):
        brain = _brain(principal)
        require_product_store(self.assets, principal, connection=connection)
        row, prepared = self.plans._state(connection, principal, identifier, generation,
            unsealed=True, source_split='tuning')
        if row['phase'] not in ('probing', 'comparing'):
            raise IM.ConflictError('compose_tuning_incomplete')
        value = prepared[0]
        self._holdout(connection, brain, value)
        arms = [dict(arm) for arm in connection.execute('SELECT * FROM improvement_experiment_arms '
            'WHERE experiment_id=? AND brain_id=? ORDER BY ordinal', (identifier, brain))]
        if [arm['ordinal'] for arm in arms] != [1, 2]:
            raise PermissionError('compose_two_arms_required')
        state = self.plans.authoring._state(connection, principal, identifier,
            value['target_id'], value['base_revision_id'], value['base_hash'])
        candidates = [dict(self.plans.authoring.records._row(connection, brain, arm['candidate_id'])) for arm in arms]
        comparisons = []
        for arm in arms:
            saved = self.plans._latest_tuning_report(connection, brain, identifier, arm['ordinal'])
            metadata = self.reports._metadata(connection, brain, saved['comparison_id'])
            if metadata['comparison']['kind'] != 'tuning' or metadata['definition'] != value:
                raise PermissionError('compose_tuning_unavailable')
            captured = self.reports._snapshot(connection, brain, metadata)
            comparisons.append({'saved': saved, 'metadata': metadata, 'captured': captured,
                'children': self._children(connection, brain, captured)})
        return {'experiment': dict(row), 'prepared': prepared, 'authoring': state,
                'arms': arms, 'candidates': candidates, 'comparisons': comparisons}

    def _fence(self, connection, principal, before):
        """SQL-only CAS after every slow blob/source/policy observation."""
        brain, value = _brain(principal), before['prepared'][0]
        require_product_store(self.assets, principal, connection=connection)
        row = self.plans.records._row(connection, brain, value['experiment_id'])
        if dict(row) != before['experiment']:
            raise IM.ConflictError('compose_experiment_changed')
        self.plans.records._bound_in(connection, brain, value, value['context_generation'])
        self._holdout(connection, brain, value)
        if connection.execute('SELECT 1 FROM improvement_experiment_selections WHERE experiment_id=? AND brain_id=?',
                              (row['id'], brain)).fetchone():
            raise IM.ConflictError('experiment_sealed')
        arms = [dict(arm) for arm in connection.execute('SELECT * FROM improvement_experiment_arms '
            'WHERE experiment_id=? AND brain_id=? ORDER BY ordinal', (row['id'], brain))]
        if arms != before['arms'] or self.plans.authoring._state(connection, principal, row['id'],
                value['target_id'], value['base_revision_id'], value['base_hash']) != before['authoring']:
            raise IM.ConflictError('compose_authority_changed')
        for candidate in before['candidates']:
            if dict(self.plans.authoring.records._row(connection, brain, candidate['id'])) != candidate:
                raise IM.ConflictError('compose_candidate_changed')
        for comparison in before['comparisons']:
            metadata = comparison['metadata']
            current_fences(connection, brain, metadata)
            captured = self.reports._snapshot(connection, brain, metadata)
            if (self.plans._latest_tuning_report(connection, brain, row['id'], metadata['comparison']['ordinal']) != comparison['saved']
                    or captured != comparison['captured']
                    or self._children(connection, brain, captured) != comparison['children']):
                raise IM.ConflictError('compose_tuning_changed')
        require_product_store(self.assets, principal, connection=connection)

    def _observations(self, connection, principal, comparison, report):
        brain, metadata = _brain(principal), comparison['metadata']
        groups = []
        for item, child, ref in zip(comparison['captured'], comparison['children'], report['result_refs']):
            if ref[1] is None:
                raise PermissionError('compose_tuning_incomplete')
            trial, attempt, request = item['trial'], item['attempt'], item['request']
            result = self.reports._result_row(brain, trial['id'], ref[1], ref[2])
            product = self.reports.results.read(principal, trial['id'], attempt['attempt'], result_id=ref[1])
            require_product_report(product)
            if IM._hash(product) != ref[2] or result['attempt'] != attempt['attempt']:
                raise AssetUnavailable('compose_tuning_result_changed')
            self.reports._artifact(brain, result, product)
            artifact = child['artifacts']
            if artifact is None or artifact['content_hash'] != product['artifact_hash']:
                raise AssetUnavailable('compose_artifact_unavailable')
            raw = _bytes(self.blobs, brain, artifact['content_hash'])
            if len(raw) != artifact['byte_size']:
                raise AssetUnavailable('compose_artifact_changed')
            case = self.cases._case(connection, brain, request['case_set_id'], request['case_id'])
            if case['split'] != 'tuning':
                raise PermissionError('compose_tuning_only')
            solver = self.cases._solver(connection, brain, case)
            records, trace = child['trace'], []
            if 'trace' in product:
                expected = {'count': len(records), 'last_sequence': records[-1]['sequence'] if records else 0,
                            'hash': IM._hash([[row['sequence'], row['payload_hash']] for row in records])}
                if (not records or any(row['late'] or row['sequence'] != index for index, row in enumerate(records, 1))
                        or expected != product['trace']):
                    raise AssetUnavailable('compose_trace_changed')
                trace = [{'sequence': row['sequence'], 'payload_hash': row['payload_hash'],
                          'observation': project_packet(decode_trace(self.blobs, brain, row))} for row in records]
            # Exact output + public case/typed verdicts, never private checker
            # reasons/evidence or raw reasoning. A missing bound trace stays so.
            observed = {'case': solver, 'repeat': request['repeat'],
                'artifact': {'path': artifact['path'], 'hash': artifact['content_hash'], 'content': raw.decode('utf-8')},
                'trace': trace, 'trace_coverage': 'bound_observable_projection' if trace else 'not_bound_by_report',
                'assessment': {'verdict': product['evaluation']['verdict'],
                    'criteria': [{key: criterion[key] for key in ('id', 'category', 'critical', 'verdict')}
                                 for criterion in product['evaluation']['criteria']],
                    'native': [{key: criterion[key] for key in ('id', 'verdict')} for criterion in product['mandatory']],
                    'evidence_origin': 'synthetic_storage_fixture' if product.get('evidence_origin') == 'synthetic_storage_fixture'
                                       else 'recorded_product_report', 'business_proof': False}}
            groups.append(('base' if request['variant'] == 'baseline' else metadata['arm']['candidate_id'],
                {'ref': {'kind': 'tuning_trial', 'id': trial['id']},
                 'location': 'result:' + result['id'] + ':artifact:' + artifact['content_hash'],
                 'observed': IM._json(observed)}))
        return groups

    def build(self, principal, experiment_id, *, expected_generation):
        brain = _brain(principal)
        _identifier(experiment_id); _generation(expected_generation)
        require_product_store(self.assets, principal)
        with closing(self.store._conn()) as connection:
            before = self._snapshot(connection, principal, experiment_id, expected_generation)
            value = before['prepared'][0]
            observed, baseline = self.plans.authoring.observe(principal, before['authoring']['target'])
            candidates = []
            for candidate in before['candidates']:
                original = self.plans.authoring.read_proposal(connection, principal, candidate,
                    before['authoring'], observed, baseline)
                candidates.append({'candidate_id': candidate['id'], 'content_hash': candidate['content_hash'], 'patch': original['patch']})
            observations = {'base': [], **{candidate['candidate_id']: [] for candidate in candidates}}
            for comparison in before['comparisons']:
                saved, metadata = comparison['saved'], comparison['metadata']
                report = self.reports.read(principal, saved['id'])
                refs, summary = self.reports._evidence(principal, metadata, comparison['captured'])
                if (IM._hash(report) != saved['report_hash'] or report['result_refs'] != refs
                        or report['summary'] != summary or not summary['complete'] or not summary['selection_supported']
                        or report['policy'] != self.reports._policy(value)):
                    raise PermissionError('compose_supported_tuning_required')
                comparison['policy'] = report['policy']
                for variant, observation in self._observations(connection, principal, comparison, report):
                    observations[variant].append(observation)
        data = {'version': 1, 'kind': 'body_compose_projection', 'experiment_id': experiment_id,
            'context_id': value['context_id'], 'definition_hash': IM._hash(value),
            'baseline': {'target_id': value['target_id'], 'revision_id': value['base_revision_id'], 'hash': value['base_hash'],
                         'content': baseline.decode('utf-8'), 'layout': body_layout(baseline)},
            'public_contract': IC.public_contract(before['comparisons'][0]['metadata']['contract']),
            'candidates': candidates, 'tuning': [{'variant': variant, 'observations': items} for variant, items in observations.items()]}
        render_compose_input(data)  # Actual unchanged upstream function and closed adapter, not just a shape check.
        # Registry callback object IDs are process-local preparation guards, not
        # durable source identity. Only stable definition/binding/SQL history is
        # hashed into this restart-readable basis; no checker is executed here.
        stable_authority = {key: child for key, child in before.items() if key != 'prepared'}
        stable_authority['definition'] = value
        stable_authority['binding_hash'] = value['binding_hash']
        basis = {'version': 1, 'kind': 'compose_input_basis', 'experiment_id': experiment_id,
            'context_id': value['context_id'], 'definition_hash': IM._hash(value), 'generation': expected_generation,
            'source_authority_hash': observed['source_authority_hash'], 'authority_snapshot_hash': IM._hash(stable_authority),
            'candidate_refs': [{key: candidate[key] for key in ('id', 'content_hash', 'patch_hash', 'provenance_hash')}
                               for candidate in before['candidates']],
            'report_refs': [{key: comparison['saved'][key] for key in ('id', 'report_hash', 'publication_id')}
                            for comparison in before['comparisons']]}
        input_blob = self.blobs.write(brain, input_bytes(data))
        basis_blob = self.blobs.write(brain, input_bytes(basis))
        saved = {'data': data, 'input_hash': IM._hash(data), 'input_blob_hash': input_blob,
                 'basis_hash': IM._hash(basis), 'basis_blob_hash': basis_blob}
        if input_blob != saved['input_hash'] or basis_blob != saved['basis_hash']:
            raise AssetUnavailable('compose_input_publication_mismatch')
        payload = {'experiment_id': experiment_id, 'expected_generation': expected_generation}
        event_key = 'compose-input-' + IM._hash([brain, payload])
        metadata = {key: saved[key] for key in ('input_hash', 'input_blob_hash', 'basis_hash', 'basis_blob_hash')}
        with self.store._Tx(self.store) as connection:
            self._fence(connection, principal, before)
            for comparison in before['comparisons']:
                if self.reports._policy(value) != comparison['policy']:
                    raise IM.ConflictError('compose_policy_changed')
            for comparison in before['comparisons']:
                self.reports._guard(connection, principal, comparison['metadata'], expected_generation)
            self.plans.authoring._guard(connection, principal, before['authoring'], observed)
            self._fence(connection, principal, before)
            old = self.assets._replay(connection, brain, event_key, 'compose_input', payload)
            if old is not None and old != metadata:
                raise IM.ConflictError('compose_input_changed')
            if old is None:
                for row in connection.execute("SELECT DISTINCT fingerprint FROM improvement_case_families "
                        "WHERE brain_id=? AND case_set_id=? AND split='tuning'", (brain, value['case_set_id'])):
                    connection.execute('INSERT OR IGNORE INTO improvement_case_exposures VALUES(?,?,?,?)',
                                       (brain, row[0], value['case_set_id'], time.time()))
                self.assets._event(connection, principal, event_key, 'compose_input', payload, metadata)
            self._fence(connection, principal, before)
        return saved
