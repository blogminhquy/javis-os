"""Actual private operation records and source fences, not native qualification.

Candidate/release observers are the existing Session engineering fixture seams.
The upstream operation reservation is explicitly made by its real records Tx,
not by a fabricated successful verifier or normal native admission. Historical
input version 1 tests records only; no SDK/CLI/account/provider is executed.
"""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import json
import subprocess
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import improvement_store as IM
from improvement_assets import capture_source
from improvement_cases import CaseStore
from improvement_comparison_plans import ExperimentPlans
from improvement_operation_execution import OperationExecution
from improvement_operation_records import OperationRecords
from improvement_operation_results import OperationResults
from improvement_qualification_records import read_attempt
from improvement_skill_candidates import SkillCandidates
from improvement_trial_file_sources import BrainFileFixtures
from improvement_trial_host import HostContextStore
from improvement_trial_service import OwnerTrialService
import test_improvement_qualification_session as S
import test_improvement_trial_associations as A


_REAL_RUN, _REAL_POPEN = subprocess.run, subprocess.Popen


def _acl_only(original, command, *args, **kwargs):
    if Path(command[0]).name.lower() not in ('whoami', 'whoami.exe', 'icacls', 'icacls.exe'):
        raise AssertionError('No native, account or model process permitted by records fixture')
    return original(command, *args, **kwargs)


class QualificationOperationBindingTests(unittest.TestCase):
    def setUp(self):
        session_helper = S.QualificationSessionTests()
        session_helper.setUp()
        self.addCleanup(session_helper.doCleanups)
        self.session = session_helper.open(maximum_queries=1)
        session = self.session
        self.owner, self.assets, self.store = session.principal, session.assets, session.assets.store
        # Keep the real disposable-workspace ACL commands, forbid all other
        # subprocesses. No verifier is called or patched in this fixture.
        for name, original in (('run', _REAL_RUN), ('Popen', _REAL_POPEN)):
            self.enterContext(patch.object(subprocess, name,
                side_effect=lambda *a, _original=original, **kw: _acl_only(_original, *a, **kw)))

        def private_host(fixture):
            # Reuse authoring fixture data/methods while making every selected
            # owner/source/blob/SQL object genuinely belong to this Session.
            fixture.root, fixture.brain = session.root, Path(session.principal.brain_id)
            fixture.owner = session.principal
            fixture.database, fixture.assets, fixture.blobs = session.assets.store, session.assets, session.assets.blobs
            fixture.cases = CaseStore(fixture.assets)
            fixture.skill = fixture.brain / 'skills' / 'report' / 'SKILL.md'
            fixture.skill.parent.mkdir(parents=True)
            fixture.skill.write_bytes(b'---\nname: Owner report\ndescription: Summarize an authorized fixture.\n---\nRetain owner rules.\n')
            source, raw = capture_source(fixture.brain, 'skill', 'report', pack_state_dir=fixture.root / 'packs')
            fixture.target = fixture.assets.capture(fixture.owner, source, raw, event_key='qualification-operation-target')
            fixture.protected = fixture.brain / 'owner.md'
            fixture.protected.write_bytes(b'Synthetic complete owner instructions.\n')
            fixture.path = fixture.brain / 'reports' / 'source.txt'
            fixture.path.parent.mkdir()
            fixture.raw = b'Private selected engineering fixture.\n'
            fixture.path.write_bytes(fixture.raw)
            fixture.ref = 'brain-file:reports/source.txt'
            fixture.metadata = {'timezone': 'UTC', 'data_period': 'engineering-period',
                'cutoff': '2026-10-22T00:00:00+00:00', 'schema': 'text/plain',
                'freshness_policy': 'require_current_version'}
            fixture.provider = BrainFileFixtures({fixture.ref: fixture.metadata})
            fixture.surface = {'kind': 'synthetic-owner-test', 'session_id': ''}
            fixture.engine = copy.deepcopy(session._pin)
            fixture.host = HostContextStore(fixture.assets, context_capture=fixture.context_capture,
                selected_engine=lambda: copy.deepcopy(fixture.engine), target_observer=fixture.targets,
                fixture_observer=fixture.provider)

        with patch.object(A.fixtures.HostSnapshotTests, 'setUp', private_host):
            self.association = A.AssociationTests()
            self.association.setUp()
        self.addCleanup(self.association.doCleanups)
        fixture = self.association.f
        self.host = self.association.host
        associated = self.association.create()
        base = self.assets.create_bundle(self.owner, [fixture.target['revision_id']],
            event_key='qualification-operation-baseline-bundle')
        self.plans = ExperimentPlans(self.host, SkillCandidates(self.assets, pack_state_dir=session.root / 'packs'))
        self.plans.create(self.owner, {'experiment_id': 'association-experiment',
            'contract_id': self.association.saved['contract_id'], 'case_set_id': associated['case_set_id'],
            'base_bundle_id': base['bundle_id'], 'expected_context_generation': 1,
            'repeat_policy': 'feasibility', 'timeout_seconds': 300}, event_key='qualification-operation-plan')
        self.trial_service = OwnerTrialService(self.host)
        self.execution = OperationExecution(self.plans, self.trial_service)
        self.records = OperationRecords(self.assets)
        self.data = {'task': 'Return an engineering role artifact', 'evidence': []}
        blob_hash = self.assets.blobs.write(self.owner.brain_id, IM._json(self.data).encode())
        # Declared fixture upstream: enter the genuine proposing state before
        # _create_in and _reserve_attempt_in; do not claim normal reserve admission.
        with self.store._Tx(self.store) as connection:
            connection.execute("UPDATE improvement_experiments SET phase='proposing',generation=generation+1")
            definition = json.loads(connection.execute('SELECT definition_json FROM improvement_experiments').fetchone()[0])
            request = {'version': 1, 'experiment_id': definition['experiment_id'], 'context_id': definition['context_id'],
                'definition_hash': IM._hash(definition), 'kind': 'propose', 'role': 'improver', 'purpose': 'improve_propose',
                'candidate_id': None, 'parent_id': None, 'input_hash': blob_hash}
            operation = self.records._create_in(connection, self.owner, request, blob_hash,
                expected_generation=2, event_key='qualification-operation-create')
            reserved = self.records._reserve_attempt_in(connection, self.owner, operation['operation_id'],
                expected_generation=1, event_key='qualification-operation-fixture-reservation')
        self.identifier = operation['operation_id']
        self.enterContext(patch('improvement_native_formats.input_version', return_value=1))
        claimed = self.execution.claim(self.owner, self.identifier, expected_generation=reserved['generation'])
        self.token = claimed['lease_token']
        manifest = self.execution.materialize(self.owner, self.identifier,
            expected_generation=claimed['generation'], lease_token=self.token)
        self.receipt = self.execution.workspace.prepare(self.identifier, 1, manifest)
        self.row = self.execution.prepared(self.owner, self.identifier, expected_generation=claimed['generation'],
            lease_token=self.token, receipt=self.receipt)
        self.assertEqual(manifest['version'], 1)
        self.assertEqual(manifest['data'], self.data)
        self.assertEqual(self.execution.workspace.validate(self.receipt), manifest)

    def bind(self):
        return self.session.bind_attempt(self.execution, self.owner, self.identifier,
            expected_generation=self.row['generation'], lease_token=self.token, capability_hash='c' * 64)

    def test_actual_prepared_operation_binds_once_and_cold_authenticates_exact_call(self):
        first = self.bind()
        self.assertEqual(self.bind(), first)
        call_id = self.row['attempts'][-1]['call_id']
        call = self.execution.ledger.get(call_id)
        self.assertEqual((call['status'], call['engine_at']), ('reserved', None))
        self.assertEqual(first, {'version': 1, 'domain': 'qualification', 'run_hash': self.session.run_hash,
            'brain_id': self.owner.brain_id, 'kind': 'operation', 'subject_id': self.identifier, 'attempt': 1,
            'request_hash': self.row['request_hash'], 'workspace_hash': IM._hash(self.receipt),
            'materialization_hash': self.receipt['input_hash'], 'engine_config_hash': IM._hash(self.session._pin),
            'capability_hash': 'c' * 64, 'call_id': call_id,
            'call_binding': {'brain_id': self.owner.brain_id, 'purpose': 'improve_propose',
                'context_ref': 'improvement:association-experiment', 'mirror_ref': 'improvement_operation:' + self.identifier,
                'reason_ref': 'improvement_operation:' + self.identifier + ':attempt:1', 'attempt': 1}})
        with closing(self.store._conn()) as connection:
            envelopes = list(connection.execute("SELECT result_json FROM improvement_events WHERE operation='native_qualification_attempt'"))
            self.assertEqual(len(envelopes), 1, 'exact replay must consume no second budget/event')
            self.assertEqual(connection.execute('SELECT count(*) FROM agent_calls').fetchone()[0], 1)
        envelope = json.loads(envelopes[0][0])
        encrypted = self.assets.blobs._path(self.owner.brain_id, envelope['blob_hash']).read_text()
        self.assertTrue(encrypted.startswith('enc:'))
        self.assertNotIn(self.identifier, encrypted)
        self.assertTrue(self.execution.workspace.cleanup_proven(self.identifier, 1, self.receipt))
        self.session.close()
        archived, owner = self.session.open_forensic(self.session.root, expected_run_hash=self.session.run_hash)
        self.assertEqual(read_attempt(archived, owner, kind='operation', subject_id=self.identifier,
            attempt=1, capability_hash='c' * 64), first)
        with self.assertRaises(PermissionError):
            self.bind()

    def test_default_operation_products_refuse_actual_durable_run_before_and_after_binding(self):
        results = OperationResults(self.execution)
        for stage in ('unlinked', 'linked'):
            if stage == 'linked': self.bind()
            for name, action in {
                'read': lambda: results.read(self.owner, self.identifier, 1),
                'finish': lambda: results.finish(self.owner, self.identifier, expected_generation=self.row['generation'],
                    lease_token=self.token, capability_hash='c' * 64)}.items():
                with self.subTest(stage=stage, path=name), self.assertRaisesRegex(PermissionError, 'non_product_execution_domain'):
                    action()
        self.assertEqual(self.execution.get(self.owner, self.identifier)['status'], 'prepared')
        call = self.execution.ledger.get(self.row['attempts'][-1]['call_id'])
        self.assertEqual((call['status'], call['engine_at']), ('reserved', None))
        with closing(self.store._conn()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM improvement_operation_results').fetchone()[0], 0)

    def test_actual_owner_source_drift_refuses_before_any_attempt_binding_event(self):
        self.association.f.protected.write_bytes(b'Changed complete owner instructions after preparation.\n')
        with self.assertRaises(IM.ConflictError):
            self.bind()
        with closing(self.store._conn()) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM improvement_events WHERE operation='native_qualification_attempt'").fetchone()[0], 0)
        call = self.execution.ledger.get(self.row['attempts'][-1]['call_id'])
        self.assertEqual((call['status'], call['engine_at']), ('reserved', None))


if __name__ == '__main__': unittest.main()
