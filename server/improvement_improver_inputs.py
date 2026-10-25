"""Host-only authorized tuning projection from an actual sealed preparation.

No private evaluator API, native query, whole recipe library or caller-selected
artifact is used. Model input publication and tuning exposure share a final CAS.
"""
from __future__ import annotations

import hashlib
import json
import time
from contextlib import closing

import improvement_cases as IC
import improvement_store as IM
from improvement_comparison_plans import ExperimentPlans
from improvement_experiments import _identifier, _generation
from improvement_generation_protocol import input_bytes
from improvement_preparation import PreparationService
from improvement_preparation_lineage import load_preparation_lineage
from improvement_skill_patch import body_layout
from improvement_trial_evidence import decode_trace
from improvement_trial_records import _brain
from improvement_result_domain import require_product_report
from improvement_tuning_history import sealed_history


def _bytes(blobs, brain, digest):
    raw = blobs.read(brain, digest)
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != digest:
        raise IM.ConflictError('improver_evidence_changed')
    return raw


def _assessment(report):
    require_product_report(report)
    # Checker reasons/evidence can contain evaluator-private answers. Expose only
    # typed verdicts, never arbitrary checker feedback or private contract config.
    criteria = [{**{key: row[key] for key in ('id', 'category', 'critical', 'verdict')},
                 'kind': 'independent_check' if row['kind'] in ('host_checker', 'command_ok') else row['kind']}
                for row in report['evaluation']['criteria']]
    mandatory = [{key: row[key] for key in ('id', 'verdict', 'reason')} for row in report['mandatory']]
    native = all(row['verdict'] == 'pass' for row in mandatory) and bool(mandatory)
    return {'execution_status': report['execution_status'], 'native_records': mandatory,
            'evaluation': criteria, 'target_defect': 'eligible_for_analysis' if native and report['evaluation']['verdict'] == 'fail' else 'unknown',
            'usage': report['usage'], 'usage_coverage': report['usage']['coverage']['status'],
            'business_proof': False, 'reasoning_observation': 'unknown'}


_EVENT_FIELDS = {
    'tool_call': ('id', 'name'), 'tool_result': ('id', 'is_error'),
    'tool_denied': ('name', 'reason', 'tool_use_id'), 'error': ('status', 'error_type', 'code'),
    'observation': ('model', 'message_id', 'usage', 'session_id', 'error'),
    'usage': ('usage', 'cost_usd', 'model_usage', 'session_id', 'duration_ms', 'duration_api_ms', 'num_turns'),
    'terminal': ('subtype', 'is_error', 'artifact_status', 'session_id'),
    'artifact': ('hash',), 'installation_receipt': ('hash',)}


def project_packet(packet):
    """Retain observable tool/error/timing/result metadata; never reasoning text."""
    if type(packet.get('version')) is int and packet['version'] == 2:
        # Caller authenticates complete stored history and result/trace hashes.
        # This is a derived model-input projection, never a legacy wire record.
        source, body = packet.get('source'), packet.get('body')
        if (source not in ('worker', 'guardian') or type(body) is not dict
                or any(type(packet.get(k)) is not int or packet[k] < 1 for k in ('sequence', 'source_sequence'))):
            raise ValueError('invalid_improver_native_projection')
        allowed = source == 'worker' and body.get('type') in ('engine_event', 'fixture_event',
            'worker_ready', 'engine_start_requested', 'worker_complete', 'worker_error')
        observation = project_packet(body) if allowed else {'type': 'withheld', 'reason': 'native_control_metadata'}
        return {'type': 'native_observation2_projection', 'sequence': packet['sequence'],
            'source': source, 'source_sequence': packet['source_sequence'], 'observation': observation}
    kind = packet['type']
    if kind == 'engine_event':
        event = packet['event']
        if event.get('type') == 'native_system':
            return {'type': kind, 'event': {'type': 'native_system', 'subtype': event.get('subtype'),
                'data': {key: event['data'][key] for key in ('session_id', 'model', 'tools') if key in event.get('data', {})}}}
        selected = _EVENT_FIELDS.get(event.get('type'))
        if selected is None:
            return {'type': 'withheld', 'reason': 'outside_authorized_trace_projection'}
        return {'type': kind, 'event': {'type': event['type'], **{key: event[key] for key in selected if key in event}}}
    if kind == 'fixture_event':
        event = packet['event']
        return {'type': kind, 'event': {key: event[key] for key in ('sequence', 'status', 'snapshot_id', 'capability_id') if key in event}}
    return {'type': kind, **{key: packet[key] for key in ('capability_hash', 'tool_denials', 'reason', 'error_type') if key in packet}}


class ImproverInputs:
    def __init__(self, plans):
        if type(plans) is not ExperimentPlans:
            raise TypeError('concrete_improver_plans_required')
        self.plans, self.host = plans, plans.host
        self.assets, self.store, self.blobs = plans.assets, plans.store, plans.blobs
        self.preparation = PreparationService(plans)

    @staticmethod
    def _holdout(connection, brain, case_set_id):
        from improvement_experiment_qualification import require_tuning_families
        require_tuning_families(connection, brain, case_set_id)

    def _snapshot(self, connection, principal, identifier, generation):
        brain = _brain(principal)
        row, prepared = self.plans._state(connection, principal, identifier, generation, unsealed=True, source_split='tuning')
        if row['phase'] != 'proposing':
            raise IM.ConflictError('improver_preparation_incomplete')
        value = prepared[0]
        self._holdout(connection, brain, value['case_set_id'])
        history = sealed_history(self, connection, principal, identifier, generation)
        state = self.plans.authoring._state(connection, principal, identifier, value['target_id'], value['base_revision_id'], value['base_hash'])
        candidates = [dict(item) for item in connection.execute('SELECT id,ordinal FROM improvement_skill_candidates '
            'WHERE experiment_id=? AND brain_id=? ORDER BY ordinal', (identifier, brain))]
        if len(candidates) > 2:
            raise IM.ConflictError('improver_candidate_limit_changed')
        return {'prepared': prepared, **history, 'authoring': state, 'candidates': candidates}

    def _tuning(self, connection, principal, snapshot):
        brain, trials = _brain(principal), self.preparation.trials
        result = []
        for link, ref, evidence in zip(snapshot['links'], snapshot['completion']['result_refs'], snapshot['evidence']):
            request = json.loads(link['request_json'])
            load_preparation_lineage(connection, brain, request, blobs=self.blobs,
                                     current=False, require_link=True, trial_id=link['trial_id'])
            case = trials.cases._case(connection, brain, request['case_set_id'], request['case_id'])
            if case['split'] != 'tuning':
                raise PermissionError('improver_non_tuning_case')
            # _solver loads only the exact case snapshots; it never opens answers.
            solver = trials.cases._solver(connection, brain, case)
            report = trials.read_result(principal, ref['trial_id'], ref['attempt'], result_id=ref['result_id'])
            require_product_report(report)
            if IM._hash(report) != ref['result_hash'] or ref['blob_hash'] != ref['result_hash']:
                raise IM.ConflictError('improver_result_changed')
            records = evidence['trace']
            if (len(records) != report['trace']['count'] or not records
                    or any(item['late'] or item['sequence'] != number for number, item in enumerate(records, 1))
                    or records[-1]['sequence'] != report['trace']['last_sequence']
                    or IM._hash([[item['sequence'], item['payload_hash']] for item in records]) != report['trace']['hash']):
                raise IM.ConflictError('improver_trace_changed')
            trace = [{'sequence': item['sequence'], 'payload_hash': item['payload_hash'], 'observed_at': item['created_at'],
                      'observation': project_packet(decode_trace(self.blobs, brain, item))} for item in records]
            artifact = evidence['artifacts']
            if artifact is not None:
                raw = _bytes(self.blobs, brain, artifact['content_hash'])
                if artifact['content_hash'] != report['artifact_hash'] or len(raw) != artifact['byte_size']:
                    raise IM.ConflictError('improver_artifact_changed')
                artifact = {'hash': artifact['content_hash'], 'path': artifact['path'], 'content': raw.decode('utf-8')}
            elif report['artifact_hash'] is not None:
                raise IM.ConflictError('improver_artifact_changed')
            receipt = evidence['receipts']
            if receipt is not None:
                from improvement_trial_checks import _RECEIPT_FIELDS
                raw = json.loads(_bytes(self.blobs, brain, receipt['content_hash']))
                receipt = {'hash': receipt['content_hash'], 'content': {key: raw[key] for key in sorted(_RECEIPT_FIELDS) if key in raw}}
            result.append({'ref': ref, 'case': solver, 'repeat': request['repeat'], 'artifact': artifact,
                           'receipt': receipt, 'trace': trace, 'assessment': _assessment(report),
                           'trace_coverage': {'reasoning': 'withheld', 'tool_payload': 'not_recorded_by_current_profile',
                                              'timing': 'when_observed'}})
        return result

    def build(self, principal, experiment_id, *, expected_generation):
        brain = _brain(principal)
        _identifier(experiment_id)
        _generation(expected_generation)
        self.plans.records._available()
        with closing(self.store._conn()) as connection:
            before = self._snapshot(connection, principal, experiment_id, expected_generation)
            tuning = self._tuning(connection, principal, before)
            value, binding = before['prepared'][:2]
            contract = json.loads(IC.CaseStore._row(connection, 'improvement_contracts', brain, value['contract_id'])['contract_json'])
        observed, baseline = self.plans.authoring.observe(principal, before['authoring']['target'])
        self.host._snapshot_observe(principal, binding)
        data = {'version': 1, 'kind': 'authorized_tuning', 'experiment_id': experiment_id,
            'definition_hash': IM._hash(value), 'context_id': value['context_id'],
            'preparation': before['completion'], 'engine_config': binding['engine_config'],
            'source_pins': {key: value[key] for key in ('scope_hash', 'grant_hash', 'policy_version', 'context_generation', 'binding_hash', 'evaluator')},
            'baseline': {'target_id': value['target_id'], 'revision_id': value['base_revision_id'], 'hash': value['base_hash'],
                'content': baseline.decode('utf-8'), 'layout': body_layout(baseline), 'source_authority_hash': observed['source_authority_hash']},
            'baseline_context': binding['capture']['baseline_context'],
            'public_contract': IC.public_contract(contract), 'tuning': tuning,
            'candidate_limit': 2 - len(before['candidates']),
            'evidence_refs': [{'kind': 'tuning_trial', 'id': ref['trial_id']} for ref in before['completion']['result_refs']],
            'recipes': [], 'recipe_coverage': 'no_separate_scoped_recipe_grant', 'evidence_class': 'technical'}
        raw = input_bytes(data)
        blob = self.blobs.write(brain, raw)
        self.host._snapshot_observe(principal, binding)
        with self.store._Tx(self.store) as connection:
            if self._snapshot(connection, principal, experiment_id, expected_generation) != before:
                raise IM.ConflictError('improver_authority_changed')
            self.plans.authoring._guard(connection, principal, before['authoring'], observed)
            self.host._snapshot_observe(principal, binding)
            # Final SQL fences after ALL slow source/blob observations.
            if self._snapshot(connection, principal, experiment_id, expected_generation) != before:
                raise IM.ConflictError('improver_authority_changed')
            saved = {'data': data, 'input_hash': IM._hash(data), 'input_blob_hash': blob}
            payload = {'experiment_id': experiment_id, 'expected_generation': expected_generation}
            event_key = 'improver-input-' + IM._hash([brain, payload])
            metadata = {key: saved[key] for key in ('input_hash', 'input_blob_hash')}
            old = self.assets._replay(connection, brain, event_key, 'improver_input', payload)
            if old is not None and old != metadata:
                raise IM.ConflictError('improver_input_changed')
            if old is None:
                for row in connection.execute("SELECT DISTINCT fingerprint FROM improvement_case_families "
                        "WHERE brain_id=? AND case_set_id=? AND split='tuning'", (brain, value['case_set_id'])):
                    connection.execute('INSERT OR IGNORE INTO improvement_case_exposures VALUES(?,?,?,?)',
                                       (brain, row[0], value['case_set_id'], time.time()))
                self.assets._event(connection, principal, event_key, 'improver_input', payload, metadata)
            return saved
