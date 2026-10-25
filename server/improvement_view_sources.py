"""Concrete current host capture for isolated technical skill views.

This preserves C's unknown verdict and A's unreviewed status. No caller-provided
object or observational permission is a quality, native or activation proof.
"""
from __future__ import annotations

import json
from contextlib import closing
from dataclasses import dataclass

import improvement_store as IM
from improvement_experiments import _identifier, _generation
from improvement_experiment_protocol import comparison_hash
from improvement_trial_records import _brain
from improvement_view_protocol import view_manifest
from improvement_view_schema import assert_installed
from improvement_result_domain import NATIVE_GATES, require_product_report

_NATIVE_CHECKS = frozenset({'materialization', 'worker_protocol', 'installation', 'tool_inventory',
    'side_effects', 'completion', 'actual_model', 'actual_reasoning', 'native_session', 'actual_input_use'})
_OBSERVATIONAL = {'actual_reasoning': 'native_reasoning_unobserved',
                  'actual_input_use': 'semantic_input_use_unobserved'}


def _probe_observations(evidence):
    """Internal gate over actual current C evidence; never rewrite its verdict."""
    require_product_report(evidence)
    version = evidence.get('native_result_version', 1)
    if type(version) is not int or version not in (1, 2):
        raise PermissionError('view_native_inventory_incomplete')
    expected_checks = _NATIVE_CHECKS | (NATIVE_GATES if version == 2 else set())
    assessment, owner = evidence['assessment'], evidence['owner_assessment']
    if (assessment['verdict'] == 'fail' or any(f['verdict'] == 'fail' for f in assessment['findings'])
            or owner is not None and owner['verdict'] == 'fail'):
        raise PermissionError('view_semantic_rejected')
    if (assessment['verdict'] != 'pass' and not (
            assessment['verdict'] in ('unknown', 'owner_required') and owner is not None and owner['verdict'] == 'pass')):
        raise PermissionError('view_semantic_owner_required')
    if evidence['dependencies']['verdict'] != 'pass':
        raise PermissionError('view_dependencies_unresolved')
    if evidence.get('native_verdict') not in ('pass', 'unknown'):
        raise PermissionError('view_native_evidence_rejected')
    checks = evidence['native_checks']
    if (type(checks) is not list or len(checks) != len(expected_checks)
            or any(type(row) is not dict or type(row.get('id')) is not str
                or row.get('verdict') not in ('pass', 'fail', 'unknown') or type(row.get('reason')) is not str for row in checks)
            or {row['id'] for row in checks} != expected_checks):
        raise PermissionError('view_native_inventory_incomplete')
    unknowns = []
    for row in checks:
        if row['verdict'] == 'pass':
            continue
        if row['verdict'] == 'unknown' and _OBSERVATIONAL.get(row['id']) == row.get('reason'):
            unknowns.append(row['id'])
            continue
        raise PermissionError('view_native_evidence_rejected')
    return tuple(sorted(unknowns))


def _owner_event(connection, brain, evidence):
    owner = evidence['owner_assessment']
    if owner is None:
        return None
    expected = {key: value for key, value in owner.items() if key != 'reason'}
    rows = connection.execute("SELECT event_key,result_json FROM improvement_events WHERE brain_id=? "
        "AND operation='semantic_owner_arbitration' ORDER BY id DESC", (brain,))
    for row in rows:
        if json.loads(row['result_json']) == expected:
            return row['event_key']
    raise IM.ConflictError('view_semantic_owner_event_changed')


@dataclass(frozen=True)
class _SourceCapture:
    experiment: dict
    comparison: dict
    arm: dict
    candidate: dict
    state: dict
    prepared: tuple
    observed: dict
    proposal: dict
    evidence: dict
    owner_event_key: str | None
    observational_unknowns: tuple[str, ...]

    def manifests(self):
        value, target, candidate = self.prepared[0], self.state['target'], self.candidate
        semantic = {'receipt_id': self.evidence['receipt_id'], 'binding_hash': self.evidence['binding_hash'],
            'assessment_hash': self.evidence['assessment_hash'], 'dependency_hash': self.evidence['binding']['dependency_hash'],
            'owner_event_key': self.owner_event_key}
        result = {}
        for variant in ('baseline', 'candidate'):
            result[variant] = view_manifest({'version': 1, 'evidence_class': 'technical', 'brain_id': candidate['brain_id'],
                'experiment_id': self.experiment['id'], 'context_id': value['context_id'],
                'context_generation': value['context_generation'], 'comparison_id': self.comparison['id'],
                'comparison_hash': comparison_hash(self.comparison), 'definition_hash': self.experiment['definition_hash'],
                'arm_ordinal': self.comparison['ordinal'], 'arm_hash': self.comparison['arm_hash'],
                'candidate_id': candidate['id'], 'variant': variant,
                'target': {**{key: candidate[key] for key in ('target_id', 'base_revision_id', 'base_hash', 'base_generation')},
                    **{key: target[key] for key in ('canonical_ref', 'identity', 'protected_hash', 'ownership')}},
                **{key: value[key] for key in ('engine_config_hash', 'baseline_context_hash', 'contract_hash',
                    'case_set_hash', 'grant_hash', 'scope_hash', 'policy_version')},
                'source_authority_hash': self.observed['source_authority_hash'], 'semantic': semantic,
                'assets': [{'id': candidate['base_revision_id'] if variant == 'baseline' else candidate['id'],
                    'canonical_ref': target['canonical_ref'], 'before_hash': candidate['base_hash'],
                    'content_hash': candidate['base_hash'] if variant == 'baseline' else candidate['content_hash'],
                    'identity': target['identity'], 'authority_hash': self.observed['source_authority_hash'], 'origin': variant}]})
        return result


def capture_sources(plans, semantic, principal, comparison_id, generation, *, connection=None):
    """Private concrete service boundary; use the existing writer when supplied."""
    if connection is None:
        with closing(plans.store._conn()) as reader:
            return capture_sources(plans, semantic, principal, comparison_id, generation, connection=reader)
    brain = _brain(principal)
    _identifier(comparison_id)
    _generation(generation)
    if IM._schema_version(plans.store) < 7:
        raise PermissionError('comparison_views_unavailable')
    assert_installed(connection)
    comparison = connection.execute('SELECT * FROM improvement_comparisons WHERE id=? AND brain_id=?',
        (comparison_id, brain)).fetchone()
    if comparison is None:
        raise PermissionError('comparison_unavailable')
    comparison = dict(comparison)
    arm = connection.execute('SELECT * FROM improvement_experiment_arms WHERE experiment_id=? AND brain_id=? AND ordinal=?',
        (comparison['experiment_id'], brain, comparison['ordinal'])).fetchone()
    if arm is None:
        raise PermissionError('experiment_arm_unavailable')
    from improvement_experiment_qualification import require_tuning_families
    experiment = plans.records._row(connection, brain, comparison['experiment_id'])
    require_tuning_families(connection, brain, json.loads(experiment['definition_json'])['case_set_id'])
    candidate = plans.authoring.records._row(connection, brain, arm['candidate_id'])
    # Grant/policy/source scope must be checked before any encrypted context read.
    state = plans.authoring._state(connection, principal, comparison['experiment_id'], candidate['target_id'],
        candidate['base_revision_id'], candidate['base_hash'])
    row, prepared = plans._state(connection, principal, comparison['experiment_id'], generation,
        unsealed=comparison['kind'] == 'tuning', source_split='tuning')
    if (comparison['definition_hash'] != row['definition_hash'] or comparison['arm_hash'] != arm['envelope_hash']
            or candidate['experiment_id'] != row['id'] or candidate['context_id'] != row['context_id']
            or candidate['target_id'] != row['target_id']):
        raise IM.ConflictError('comparison_view_scope_changed')
    frozen_arm = plans._frozen_arm(connection, principal, row, prepared, comparison['ordinal'])
    if dict(frozen_arm) != dict(arm):
        raise IM.ConflictError('comparison_view_arm_changed')
    observed, before = plans.authoring.observe(principal, state['target'])
    proposal = plans.authoring.read_proposal(connection, principal, candidate, state, observed, before)
    evidence = semantic.current_evidence(principal, candidate['id'], expected_generation=generation)
    unknowns = _probe_observations(evidence)
    if (evidence['binding']['source_authority_hash'] != observed['source_authority_hash']
            or evidence['binding']['definition_hash'] != row['definition_hash']):
        raise IM.ConflictError('comparison_view_semantic_changed')
    owner_event = _owner_event(connection, brain, evidence)
    plans.authoring._guard(connection, principal, state, observed)
    plans.host._snapshot_observe(principal, prepared[1])
    if dict(plans.records._row(connection, brain, row['id'])) != dict(row):
        raise IM.ConflictError('comparison_view_generation_changed')
    return _SourceCapture(dict(row), comparison, dict(arm), dict(candidate), state, prepared,
        observed, proposal, evidence, owner_event, unknowns)


@dataclass(frozen=True)
class ResolvedView:
    """Host result with immutable bytes; decoding metadata returns a fresh copy."""
    view_id: str
    comparison_id: str
    binding_hash: str
    manifest_hash: str
    manifest_bytes: bytes
    content: bytes
    observational_unknowns: tuple[str, ...]

    @property
    def manifest(self):
        return json.loads(self.manifest_bytes)
