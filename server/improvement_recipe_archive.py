"""Owner-authored encrypted procedures with actual source/evidence publication fences.

Outcome observations do not isolate a transferable procedure. These immutable
records remain untrusted guidance, requiring fresh controlling sources and
separate transfer authority in any future destination consumer.
"""
from __future__ import annotations

import hashlib
import json
import math
import secrets
import time
from contextlib import closing

from cryptography.fernet import InvalidToken

import improvement_store as IM
from evidence_store import redact
from improvement_blobs import AssetUnavailable
from improvement_recipe_sources import owner_rule_hash
from improvement_comparison_plans import ExperimentPlans
from improvement_comparison_results import ComparisonResults
from improvement_experiments import _generation, _identifier
from improvement_harness2_context import assert_tree_has_no_grader_verdicts
from improvement_improver_inputs import ImproverInputs
from improvement_qualification_records import require_product_store
from improvement_result_domain import require_product_report
from improvement_trial_evidence import decode_trace
from improvement_trial_file_sources import BrainFileFixtures
from improvement_trial_records import _brain
from improvement_trial_results import TrialResults
from improvement_trial_semantics import validate_capture
from improvement_tuning_history import sealed_history


def _text(value, maximum):
    if type(value) is not str or not value.strip() or '\0' in value:
        raise ValueError('invalid_recipe_text')
    try:
        raw = value.encode('utf-8', errors='strict')
    except UnicodeError as error:
        raise ValueError('invalid_recipe_utf8') from error
    if len(raw) > maximum:
        raise ValueError('recipe_text_too_large')
    # Inspect raw owner strings before redaction or JSON serialization can hide
    # credentials or upstream grader markers.
    if redact(value) != value:
        raise ValueError('recipe_contains_credentials')
    assert_tree_has_no_grader_verdicts({'procedure.md': value})


def _decision(value):
    if type(value) is not dict:
        raise ValueError('invalid_recipe_decision')
    if value == {'kind': 'NO_ENTRY'}:
        return dict(value)
    if set(value) != {'kind', 'cue', 'procedure', 'applicability', 'exclusions', 'expires_at'} or value['kind'] != 'procedure':
        raise ValueError('invalid_recipe_decision')
    for key, maximum in (('cue', 1000), ('procedure', 16384)):
        _text(value[key], maximum)
    for key in ('applicability', 'exclusions'):
        rows = value[key]
        if type(rows) is not list or len(rows) > 8:
            raise ValueError('invalid_recipe_guidance')
        for item in rows:
            _text(item, 512)
        if len(set(rows)) != len(rows):
            raise ValueError('duplicate_recipe_guidance')
    if type(value['expires_at']) not in (int, float) or not math.isfinite(value['expires_at']):
        raise ValueError('invalid_recipe_expiry')
    return json.loads(IM._json(value))


def _rows(connection, sql, args):
    return [dict(row) for row in connection.execute(sql, args)]


class RecipeArchive:
    def __init__(self, plans):
        if type(plans) is not ExperimentPlans:
            raise TypeError('concrete_recipe_plans_required')
        self.plans, self.host, self.authoring = plans, plans.host, plans.authoring
        self.assets, self.store, self.blobs = plans.assets, plans.store, plans.blobs
        self.inputs, self.comparisons = ImproverInputs(plans), ComparisonResults(plans)
        self.results = TrialResults(plans.admission.trials)

    def _latest(self, connection, brain, experiment_id, ordinal):
        # Absence is established by actual history, never by swallowing a corrupt
        # report/publication error and choosing an older favorable report.
        exists = connection.execute("SELECT 1 FROM improvement_comparison_reports r JOIN improvement_comparisons c "
            "ON c.id=r.comparison_id AND c.brain_id=r.brain_id WHERE c.brain_id=? AND c.experiment_id=? "
            "AND c.ordinal=? AND c.kind='tuning'", (brain, experiment_id, ordinal)).fetchone()
        published = connection.execute("SELECT 1 FROM improvement_events e WHERE e.brain_id=? AND e.operation='comparison_report' "
            "AND json_extract(e.result_json,'$.comparison_id') IN (SELECT id FROM improvement_comparisons "
            "WHERE brain_id=? AND experiment_id=? AND ordinal=? AND kind='tuning')",
            (brain, brain, experiment_id, ordinal)).fetchone()
        if exists is None and published is None:
            return None
        return self.plans._latest_tuning_report(connection, brain, experiment_id, ordinal)

    def _trial(self, connection, brain, trial_id, attempt, result_id):
        trial = connection.execute('SELECT * FROM improvement_trials WHERE id=? AND brain_id=?', (trial_id, brain)).fetchone()
        result = connection.execute('SELECT * FROM improvement_trial_results WHERE id=? AND trial_id=? AND brain_id=? AND attempt=?',
                                    (result_id, trial_id, brain, attempt)).fetchone()
        saved = connection.execute('SELECT * FROM improvement_trial_attempts WHERE trial_id=? AND brain_id=? AND attempt=?',
                                   (trial_id, brain, attempt)).fetchone()
        if trial is None or result is None or saved is None:
            raise PermissionError('recipe_trial_unavailable')
        return {'trial': dict(trial), 'result': dict(result), 'attempt': dict(saved),
            'trace': _rows(connection, 'SELECT * FROM improvement_trial_observations WHERE trial_id=? AND brain_id=? AND attempt=? ORDER BY sequence',
                           (trial_id, brain, attempt))}

    @staticmethod
    def _composition_sql(connection, brain, composition_id):
        if composition_id is None:
            return None
        row = connection.execute('SELECT * FROM improvement_compositions WHERE id=? AND brain_id=?', (composition_id, brain)).fetchone()
        if row is None:
            raise PermissionError('recipe_composition_unavailable')
        result = {'composition': dict(row)}
        for table, column, identity in (
                ('improvement_compose_authorizations', 'id', row['authorization_id']),
                ('improvement_compose_grants', 'authorization_id', row['authorization_id']),
                ('improvement_operations', 'id', row['operation_id']),
                ('improvement_operation_attempts', 'operation_id', row['operation_id']),
                ('improvement_operation_results', 'operation_id', row['operation_id']),
                ('improvement_operation_observations', 'operation_id', row['operation_id'])):
            result[table] = _rows(connection, 'SELECT * FROM ' + table + ' WHERE ' + column + '=? AND brain_id=? ORDER BY rowid', (identity, brain))
        return result

    def _contribution_sql(self, connection, brain, contribution):
        saved = contribution['saved']
        return {'report': _rows(connection, 'SELECT * FROM improvement_comparison_reports WHERE id=? AND brain_id=?', (saved['id'], brain)),
            'publication': _rows(connection, 'SELECT * FROM improvement_events WHERE id=? AND brain_id=?', (saved['publication_id'], brain)),
            'captured': self.comparisons._snapshot(connection, brain, contribution['metadata']),
            'trials': [self._trial(connection, brain, ref['trial_id'], ref['attempt'], ref['result_id']) for ref in contribution['refs']]}

    def _composed_refs(self, connection, principal, captured, provenance):
        """Resolve only the original reports authenticated by composed provenance."""
        brain = _brain(principal)
        composition = connection.execute('SELECT * FROM improvement_compositions WHERE id=? AND brain_id=?',
                                         (provenance['composition_id'], brain)).fetchone()
        if composition is None:
            raise PermissionError('recipe_composition_unavailable')
        raw = self.blobs.read(brain, composition['basis_hash'])
        basis = json.loads(raw)
        expected = {'version', 'kind', 'experiment_id', 'context_id', 'definition_hash', 'generation',
                    'source_authority_hash', 'authority_snapshot_hash', 'candidate_refs', 'report_refs'}
        value = captured['prepared'][0]
        if (type(basis) is not dict or set(basis) != expected or type(basis['version']) is not int or basis['version'] != 1
                or basis['kind'] != 'compose_input_basis' or raw != IM._json(basis).encode('utf-8')
                or IM._hash(basis) != composition['basis_hash'] or basis['definition_hash'] != IM._hash(value)
                or basis['context_id'] != value['context_id'] or basis['experiment_id'] != value['experiment_id']
                or basis['source_authority_hash'] != provenance['source_authority_hash']
                or type(basis['report_refs']) is not list or len(basis['report_refs']) != 2):
            raise AssetUnavailable('recipe_composed_basis_changed')
        result, seen = {}, set()
        for ref in basis['report_refs']:
            if type(ref) is not dict or set(ref) != {'id', 'report_hash', 'publication_id'} or ref['id'] in seen:
                raise AssetUnavailable('recipe_composed_report_ref_changed')
            seen.add(ref['id'])
            saved = connection.execute('SELECT * FROM improvement_comparison_reports WHERE id=? AND brain_id=?', (ref['id'], brain)).fetchone()
            publication = connection.execute('SELECT * FROM improvement_events WHERE id=? AND brain_id=?', (ref['publication_id'], brain)).fetchone()
            if saved is None or publication is None or saved['report_hash'] != ref['report_hash']:
                raise AssetUnavailable('recipe_composed_report_ref_changed')
            published = json.loads(publication['result_json'])
            if (publication['operation'] != 'comparison_report' or type(published) is not dict
                    or published.get('report_id') != ref['id'] or published.get('report_hash') != ref['report_hash']
                    or published.get('comparison_id') != saved['comparison_id']):
                raise AssetUnavailable('recipe_composed_publication_changed')
            metadata = self.comparisons._metadata(connection, brain, saved['comparison_id'])
            if (metadata['comparison']['kind'] != 'tuning' or metadata['comparison']['ordinal'] not in (1, 2)
                    or metadata['definition'] != value or saved['experiment_id'] != value['experiment_id']):
                raise PermissionError('recipe_composed_report_scope_changed')
            observed = self.comparisons._snapshot(connection, brain, metadata)
            report = self.comparisons.read(principal, ref['id'])
            refs, summary = self.comparisons._evidence(principal, metadata, observed, refs=report['result_refs'])
            if (IM._hash(report) != ref['report_hash'] or report['summary'] != summary
                    or report['policy'] != self.comparisons._policy(metadata['definition'])):
                raise AssetUnavailable('recipe_composed_report_changed')
            contribution = {'saved': {**dict(saved), 'publication_id': ref['publication_id']}, 'metadata': metadata, 'refs': []}
            captured['contributions'].append(contribution)
            for position, result_id, digest in refs:
                if result_id is None:
                    continue
                item = observed[position]
                stored = connection.execute('SELECT attempt FROM improvement_trial_results WHERE id=? AND brain_id=?', (result_id, brain)).fetchone()
                pin = {'trial_id': item['trial']['id'], 'attempt': stored['attempt'], 'result_id': result_id,
                       'result_hash': digest, 'request_hash': item['trial']['request_hash']}
                self._trial_ref(connection, principal, captured, pin)
                contribution['refs'].append(pin)
                if pin['trial_id'] in result and result[pin['trial_id']] != pin:
                    raise IM.ConflictError('recipe_conflicting_trial_pins')
                result[pin['trial_id']] = pin
        captured['composition_id'] = composition['id']
        return result

    @staticmethod
    def _view_sql(connection, brain, comparison_id):
        # TrialResults owns encrypted historical v4 validation. Retain only its
        # existing SQL dependencies for the final CAS after slow callbacks;
        # this snapshot neither resolves a view nor grants current execution.
        binding = connection.execute('SELECT * FROM improvement_comparison_views WHERE comparison_id=? AND brain_id=?',
                                     (comparison_id, brain)).fetchone()
        if binding is None:
            return None
        return {'binding': dict(binding),
            'comparison': _rows(connection, 'SELECT * FROM improvement_comparisons WHERE id=? AND brain_id=?', (comparison_id, brain)),
            'arm': _rows(connection, 'SELECT a.* FROM improvement_experiment_arms a JOIN improvement_comparisons c '
                'ON c.experiment_id=a.experiment_id AND c.brain_id=a.brain_id AND c.ordinal=a.ordinal '
                'WHERE c.id=? AND c.brain_id=?', (comparison_id, brain)),
            'views': _rows(connection, 'SELECT * FROM improvement_effective_views WHERE comparison_id=? AND brain_id=? ORDER BY id',
                           (comparison_id, brain)),
            'assets': _rows(connection, 'SELECT a.* FROM improvement_effective_view_assets a JOIN improvement_effective_views v '
                'ON v.id=a.view_id AND v.brain_id=a.brain_id WHERE v.comparison_id=? AND v.brain_id=? ORDER BY a.view_id,a.position',
                (comparison_id, brain)),
            'receipt': _rows(connection, 'SELECT * FROM improvement_semantic_receipts WHERE id=? AND brain_id=?',
                             (binding['semantic_receipt_id'], brain)),
            'links': _rows(connection, 'SELECT * FROM improvement_view_trial_links WHERE comparison_id=? AND brain_id=? ORDER BY cell_position',
                           (comparison_id, brain)),
            'publications': _rows(connection, "SELECT * FROM improvement_events WHERE brain_id=? AND "
                "((operation='comparison_views_freeze' AND json_extract(result_json,'$.comparison_id')=?) OR "
                "(operation='semantic_owner_arbitration' AND json_extract(result_json,'$.receipt_id')=?)) ORDER BY id",
                (brain, comparison_id, binding['semantic_receipt_id']))}

    def _sql(self, connection, principal, captured):
        """Final comparison uses SQL alone, after the last source/blob callback."""
        brain, candidate = _brain(principal), captured['candidate']
        value = captured['prepared'][0]
        self.inputs._holdout(connection, brain, value['case_set_id'])
        self.plans.records._bound_in(connection, brain, value, value['context_generation'])
        self.plans.records._public(self.plans.records._row(connection, brain, value['experiment_id']))
        state = self.authoring._state(connection, principal, value['experiment_id'], value['target_id'], value['base_revision_id'], value['base_hash'])
        if state['policy']['mode'] != 'suggest':
            raise PermissionError('recipe_suggest_required')
        experiment = dict(self.plans.records._row(connection, brain, value['experiment_id']))
        if (experiment['generation'] != captured['generation'] or state['grant']['generation'] != captured['context_generation']):
            raise IM.ConflictError('recipe_generation_stale')
        preparation = _rows(connection, 'SELECT * FROM improvement_preparations WHERE experiment_id=? AND brain_id=?', (value['experiment_id'], brain))
        completions = _rows(connection, "SELECT * FROM improvement_events WHERE brain_id=? AND operation='preparation_complete' "
            "AND json_extract(result_json,'$.experiment_id')=? ORDER BY id", (brain, value['experiment_id']))
        latest = self._latest(connection, brain, value['experiment_id'], candidate['ordinal'])
        comparison = None
        if latest is not None:
            if (captured['comparison_metadata'] is None
                    or latest['comparison_id'] != captured['comparison_metadata']['comparison']['id']):
                raise IM.ConflictError('recipe_comparison_changed')
            comparison = self.comparisons._snapshot(connection, brain, captured['comparison_metadata'])
        evidence_comparisons = [item['metadata']['comparison']['id'] for item in captured['contributions']]
        if captured['comparison_metadata'] is not None:
            evidence_comparisons.append(captured['comparison_metadata']['comparison']['id'])
        return {'state': state, 'experiment': experiment,
            'candidate': dict(self.authoring.records._row(connection, brain, candidate['id'])),
            'preparation': preparation, 'completions': completions,
            'preparation_links': _rows(connection, 'SELECT * FROM improvement_preparation_trial_links WHERE experiment_id=? AND brain_id=? ORDER BY cell_position',
                                       (value['experiment_id'], brain)),
            'latest': latest, 'comparison': comparison,
            'views': {identifier: self._view_sql(connection, brain, identifier) for identifier in sorted(set(evidence_comparisons))},
            'composition': self._composition_sql(connection, brain, captured['composition_id']),
            'contributions': [self._contribution_sql(connection, brain, item) for item in captured['contributions']],
            'trials': [self._trial(connection, brain, ref['trial_id'], ref['attempt'], ref['result_id']) for ref in captured['refs']]}

    def _trial_ref(self, connection, principal, captured, ref, *, sealed=False):
        brain = _brain(principal)
        item = self._trial(connection, brain, ref['trial_id'], ref['attempt'], ref['result_id'])
        trial, result, attempt, records = (item[key] for key in ('trial', 'result', 'attempt', 'trace'))
        request = json.loads(trial['request_json'])
        value = captured['prepared'][0]
        pins = request['pins']
        case = connection.execute('SELECT split FROM improvement_cases WHERE id=? AND brain_id=? AND case_set_id=?',
                                  (request['case_id'], brain, request['case_set_id'])).fetchone()
        context = request.get('lineage', {}).get('context_id', request.get('preparation', {}).get('context_id'))
        if (case is None or case['split'] != 'tuning' or context != value['context_id']
                or pins['experiment_id'] != value['experiment_id'] or trial['request_hash'] != IM._hash(request)
                or ref.get('request_hash', trial['request_hash']) != trial['request_hash']
                or any(pins[key] != value[key] for key in ('scope_hash', 'grant_hash', 'engine_config_hash', 'policy_version'))
                or result['result_hash'] != ref['result_hash'] or result['blob_hash'] != ref['result_hash']):
            raise PermissionError('recipe_trial_scope_changed')
        if sealed:
            pointer = {'result_id': result['id'], 'result_hash': result['result_hash'], 'blob_hash': result['blob_hash']}
            if json.loads(attempt['result_json']) != pointer or ref['blob_hash'] != result['blob_hash']:
                raise IM.ConflictError('recipe_sealed_result_changed')
        report = self.results.read(principal, trial['id'], result['attempt'], result_id=result['id'])
        require_product_report(report)
        trace = report.get('trace')
        if (IM._hash(report) != result['result_hash'] or type(trace) is not dict or not records
                or len(records) != trace.get('count') or trace.get('last_sequence') != len(records)
                or any(row['late'] or row['sequence'] != index for index, row in enumerate(records, 1))
                or IM._hash([[row['sequence'], row['payload_hash']] for row in records]) != trace.get('hash')):
            raise IM.ConflictError('recipe_trace_changed')
        for row in records:
            decode_trace(self.blobs, brain, row)
        captured['times'].extend([result['created_at'], *[row['created_at'] for row in records]])
        return {'trial_id': trial['id'], 'attempt': result['attempt'], 'result_id': result['id'],
            'result_hash': result['result_hash'], 'trace_hash': trace['hash'], 'trace_count': trace['count'],
            'request_hash': trial['request_hash']}, request['variant'] == 'candidate'

    def _capture(self, connection, principal, experiment_id, candidate_id, generation, context_generation):
        brain = _brain(principal)
        require_product_store(self.assets, principal, connection=connection)
        # Filter the actual candidate/context grant and current target rights
        # in SQL before the plan owner decrypts its frozen binding or sources.
        candidate = dict(self.authoring.records._row(connection, brain, candidate_id))
        if candidate['experiment_id'] != experiment_id:
            raise PermissionError('recipe_candidate_scope_changed')
        state = self.authoring._state(connection, principal, experiment_id,
            candidate['target_id'], candidate['base_revision_id'], candidate['base_hash'])
        if state['policy']['mode'] != 'suggest':
            raise PermissionError('recipe_suggest_required')
        if context_generation != state['grant']['generation']:
            raise IM.ConflictError('recipe_context_generation_stale')
        _, prepared = self.plans._state(connection, principal, experiment_id, generation, unsealed=False, source_split='tuning')
        value, binding = prepared[:2]
        if type(self.host.fixture_observer) is not BrainFileFixtures or any(
                item['freshness_policy'] != 'require_current_version' or not item['source_ref'].startswith('brain-file:')
                for item in binding['fixture_inventory']):
            raise PermissionError('recipe_source_lifetime_unsupported')
        capture = binding['capture']
        if type(capture.get('version')) is not int or capture['version'] != 2:
            raise PermissionError('recipe_complete_semantic_capture_required')
        capture = validate_capture(capture)
        language = capture['surface'].get('language')
        if capture['baseline_context']['coverage'] != 'complete' or language not in ('vi', 'en'):
            raise PermissionError('recipe_complete_semantic_capture_required')
        if any(candidate[key] != value[key] for key in
               ('experiment_id', 'context_id', 'target_id', 'base_revision_id', 'base_hash', 'base_generation')):
            raise PermissionError('recipe_candidate_scope_changed')
        observed, raw = self.authoring.observe(principal, state['target'])
        proposal = self.authoring.read_proposal(connection, principal, candidate, state, observed, raw)
        evidence_refs = self.authoring._evidence(connection, brain, state['context'], proposal['provenance']['evidence_refs'])
        result = {'prepared': prepared, 'candidate': candidate, 'state': state, 'observed': observed,
            'generation': generation, 'context_generation': context_generation, 'refs': [],
            'times': [state['context']['created_at'], candidate['created_at']], 'comparison_metadata': None,
            'composition_id': None, 'contributions': []}
        preparation = connection.execute('SELECT 1 FROM improvement_preparations WHERE experiment_id=? AND brain_id=?', (experiment_id, brain)).fetchone()
        complete_event = connection.execute("SELECT 1 FROM improvement_events WHERE brain_id=? AND operation='preparation_complete' "
            "AND json_extract(result_json,'$.experiment_id')=?", (brain, experiment_id)).fetchone()
        history = None
        if preparation is not None or complete_event is not None:
            history = sealed_history(self.inputs, connection, principal, experiment_id, generation)
        references = [] if history is None else [(ref, True) for ref in history['completion']['result_refs']]
        latest = self._latest(connection, brain, experiment_id, candidate['ordinal'])
        comparison, summary, report_refs = None, None, {}
        if latest is not None:
            metadata = self.comparisons._metadata(connection, brain, latest['comparison_id'])
            captured = self.comparisons._snapshot(connection, brain, metadata)
            report = self.comparisons.read(principal, latest['id'])
            refs, summary = self.comparisons._evidence(principal, metadata, captured)
            if (IM._hash(report) != latest['report_hash'] or report['result_refs'] != refs
                    or report['summary'] != summary or report['policy'] != self.comparisons._policy(metadata['definition'])):
                raise IM.ConflictError('recipe_comparison_changed')
            result['comparison_metadata'] = metadata
            comparison = {'report_id': latest['id'], 'report_hash': latest['report_hash'],
                'comparison_id': latest['comparison_id'], 'kind': 'tuning', 'summary': summary}
            for position, result_id, digest in refs:
                if result_id is not None:
                    item = captured[position]
                    saved = connection.execute('SELECT attempt FROM improvement_trial_results WHERE id=? AND brain_id=?', (result_id, brain)).fetchone()
                    ref = {'trial_id': item['trial']['id'], 'attempt': saved['attempt'], 'result_id': result_id, 'result_hash': digest,
                           'request_hash': item['trial']['request_hash']}
                    references.append((ref, False))
                    report_refs[ref['trial_id']] = ref
        prep_refs = {} if history is None else {ref['trial_id']: ref for ref in history['completion']['result_refs']}
        composed_refs = self._composed_refs(connection, principal, result, proposal['provenance']) if candidate['ordinal'] == 3 else {}
        provenance_trials = set()
        for ref in evidence_refs:
            if ref['kind'] == 'tuning_trial':
                selected = prep_refs.get(ref['id']) or report_refs.get(ref['id']) or composed_refs.get(ref['id'])
                if selected is None:
                    raise PermissionError('recipe_evidence_not_sealed')
                references.append((selected, ref['id'] in prep_refs))
                if ref['id'] in composed_refs and ref['id'] not in report_refs:
                    provenance_trials.add(ref['id'])
        normalized, observed_candidate = {}, False
        for ref, sealed in references:
            pin, candidate_observation = self._trial_ref(connection, principal, result, ref, sealed=sealed)
            key = (pin['trial_id'], pin['attempt'])
            if key in normalized and normalized[key] != pin:
                raise IM.ConflictError('recipe_conflicting_trial_pins')
            normalized[key] = pin
            observed_candidate = observed_candidate or (candidate_observation and pin['trial_id'] not in provenance_trials)
        result['refs'] = [normalized[key] for key in sorted(normalized)]
        if len(result['refs']) > 4000:
            raise ValueError('recipe_trial_limit')
        source_basis = {'version': 1, 'candidate': {key: candidate[key] for key in (
            'id', 'context_id', 'experiment_id', 'target_id', 'base_revision_id', 'base_hash', 'content_hash', 'patch_hash', 'provenance_hash', 'ordinal')},
            'context': {'context_id': state['context']['id'], **{key: value[key] for key in
                ('binding_hash', 'scope_hash', 'grant_hash', 'context_generation', 'policy_version', 'engine_config_hash')}},
            'preparation': None if history is None else history['completion'], 'candidate_evidence_refs': evidence_refs,
            'comparison_ref': None if latest is None else {'report_id': latest['id'], 'report_hash': latest['report_hash'],
                'comparison_id': latest['comparison_id'], 'publication_id': latest['publication_id']}}
        source_basis['candidate']['source_authority_hash'] = proposal['provenance']['source_authority_hash']
        result.update(basis=source_basis, comparison=comparison, language=language,
            owner_rule_hash=owner_rule_hash(capture),
            verdict='confounded' if observed_candidate else 'untested',
            confidence={'attribution': 'not_isolated', 'candidate_outcome': 'unobserved' if summary is None else summary['mechanical_verdict'],
                'evidence_class': 'technical' if summary is None else summary['evidence_class'], 'business_proof': False, 'transfer': 'unverified'})
        result['sql'] = self._sql(connection, principal, result)
        return result

    def _guard(self, connection, principal, before):
        self.authoring._guard(connection, principal, before['state'], before['observed'])
        self.host._snapshot_observe(principal, before['prepared'][1])
        # A second real observation brackets late source mutation during the
        # first observer's slow blob reads. SQL fences then close publication.
        self.authoring._guard(connection, principal, before['state'], before['observed'])
        self.host._snapshot_observe(principal, before['prepared'][1])
        require_product_store(self.assets, principal, connection=connection)
        if self._sql(connection, principal, before) != before['sql']:
            raise IM.ConflictError('recipe_authority_changed')

    def _authenticated(self, connection, principal, experiment_id, candidate_id, generation, context_generation):
        try:
            return self._capture(connection, principal, experiment_id, candidate_id, generation, context_generation)
        except InvalidToken as error:
            raise AssetUnavailable('recipe_evidence_unavailable') from error

    def capture(self, principal, experiment_id, candidate_id, decision, *, expected_generation, expected_context_generation, event_key):
        from resonance_store import GoalStore
        brain = _brain(principal)
        for identifier in (experiment_id, candidate_id):
            _identifier(identifier)
        _generation(expected_generation)
        _generation(expected_context_generation)
        decision = _decision(decision)
        payload = {'experiment_id': experiment_id, 'candidate_id': candidate_id, 'decision': decision,
                   'expected_generation': expected_generation, 'expected_context_generation': expected_context_generation}
        if type(self.store) is not GoalStore or IM._schema_version(self.store) not in (9, 10, 11, 12, 13, 14, 15, 16, 17):
            raise PermissionError('recipe_writer_unavailable')
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, brain, event_key, 'recipe_capture', payload)
            if replay is not None:
                return replay
            before = self._authenticated(connection, principal, experiment_id, candidate_id, expected_generation, expected_context_generation)
        checked_at = min(before['times'])
        now = time.time()
        if not 0 <= checked_at <= now or checked_at + 2592000 <= now:
            raise PermissionError('recipe_source_expired')
        result = {'kind': 'NO_ENTRY', 'experiment_id': experiment_id, 'candidate_id': candidate_id,
            'source_basis_hash': IM._hash(before['basis']), 'authority_status': 'not_checked', 'business_proof': False}
        manifest = None
        if decision['kind'] == 'procedure':
            expires = min(decision['expires_at'], checked_at + 2592000)
            if expires <= now:
                raise PermissionError('recipe_source_expired')
            candidate, value, binding = before['candidate'], *before['prepared'][:2]
            manifest = {'version': 1, 'kind': 'recipe', 'authorship': 'owner_unverified_procedure',
                'recipe_id': 'ir_' + secrets.token_hex(12), 'brain_id': brain, 'experiment_id': experiment_id,
                **{key: candidate[key] for key in ('context_id', 'target_id', 'base_revision_id')}, 'candidate_id': candidate_id,
                **{key: decision[key] for key in ('cue', 'procedure', 'applicability', 'exclusions')},
                'before_hash': candidate['base_hash'], 'after_hash': candidate['content_hash'], 'patch_hash': candidate['patch_hash'],
                'provenance_hash': candidate['provenance_hash'], 'source_basis': before['basis'], 'source_basis_hash': IM._hash(before['basis']),
                'scope_hash': value['scope_hash'], 'engine_config': binding['engine_config'], 'engine_config_hash': value['engine_config_hash'],
                'owner_rule_hash': before['owner_rule_hash'], 'target_protected_hash': before['state']['target']['protected_hash'],
                'source_authority_hash': before['basis']['candidate']['source_authority_hash'], 'language': before['language'],
                'trial_refs': before['refs'], 'comparison': before['comparison'], 'verdict': before['verdict'],
                'confidence_basis': before['confidence'], 'checked_at': checked_at, 'expires_at': expires, 'actor': principal.by, 'created_at': now}
            raw = IM._json(manifest).encode('utf-8')
            if len(raw) > 1048576:
                raise ValueError('recipe_manifest_too_large')
            digest = self.blobs.write(brain, raw)
            if digest != hashlib.sha256(raw).hexdigest() or self.blobs.read(brain, digest) != raw:
                raise AssetUnavailable('recipe_manifest_changed')
            result = {'kind': 'recorded', 'recipe_id': manifest['recipe_id'], 'manifest_hash': digest,
                'experiment_id': experiment_id, 'candidate_id': candidate_id, 'authority_status': 'not_checked', 'business_proof': False}
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, 'recipe_capture', payload)
            if replay is not None:
                return replay
            # Authenticate encrypted source/proposal/evidence again after the
            # slow manifest write. The final guard then ends with SQL-only CAS.
            if self._authenticated(connection, principal, experiment_id, candidate_id, expected_generation, expected_context_generation) != before:
                raise IM.ConflictError('recipe_authority_changed')
            self._guard(connection, principal, before)
            if checked_at + 2592000 <= time.time() or (manifest is not None and manifest['expires_at'] <= time.time()):
                raise PermissionError('recipe_source_expired')
            if manifest is not None:
                row = {'id': manifest['recipe_id'], 'brain_id': brain,
                    **{key: manifest[key] for key in ('experiment_id', 'context_id', 'target_id', 'base_revision_id', 'candidate_id')},
                    'comparison_report_id': None if manifest['comparison'] is None else manifest['comparison']['report_id'],
                    'manifest_hash': digest, 'manifest_blob_hash': digest, **{key: manifest[key] for key in
                        ('source_basis_hash', 'scope_hash', 'engine_config_hash', 'owner_rule_hash', 'target_protected_hash',
                         'source_authority_hash', 'language', 'verdict', 'checked_at', 'expires_at', 'actor', 'created_at')}}
                connection.execute('INSERT INTO improvement_recipes(' + ','.join(row) + ') VALUES(' + ','.join('?' for _ in row) + ')', list(row.values()))
                for position, ref in enumerate(before['refs']):
                    connection.execute('INSERT INTO improvement_recipe_trial_refs VALUES(?,?,?,?,?,?,?,?,?)',
                        (row['id'], brain, position, ref['trial_id'], ref['attempt'], ref['result_id'], ref['result_hash'], ref['trace_hash'], ref['trace_count']))
                connection.execute('INSERT INTO improvement_recipe_states VALUES(?,?,?,1,NULL,NULL,?)', (row['id'], brain, 'active', now))
            self.assets._event(connection, principal, event_key, 'recipe_capture', payload, result)
            return result
