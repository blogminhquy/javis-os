"""Compose transport contract through real existing components; no dispatch.

Private workspace/CallLedger controls are explicitly synthetic/unexecuted. No
compose consent service, native/account/model readiness or new bundle is claimed.
"""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_ledger import CallLedger
import improvement_operation_protocol as protocol
import improvement_operation_profile as profile
import improvement_store as IM
import improvement_usage as usage
import usage_store
from resonance_store import GoalStore
import test_improvement_compose_protocol as compose
import test_improvement_operation_workspace as workspace


class ComposeRoleContractTests(unittest.TestCase):
    @staticmethod
    def request(data=None):
        return {'version': 2, 'experiment_id': 'experiment-one', 'context_id': 'context-one',
            'definition_hash': 'd' * 64, 'kind': 'compose', 'role': 'composer', 'purpose': 'improve_compose',
            'candidate_id': None, 'parent_id': None, 'input_hash': IM._hash({'task': 'schema control'} if data is None else data),
            'compose_authorization_id': 'ica_explicit_consent'}

    def test_closed_new_compose_request_requires_distinct_role_and_consent_identifier(self):
        value = self.request()
        self.assertEqual(protocol.operation_request(value), value)
        malformed = [{**value, **change} for change in ({'version': 1}, {'version': True}, {'role': 'improver'},
            {'purpose': 'improve_propose'}, {'parent_id': 'io_repair'}, {'candidate_id': 'isc_inherited'},
            {'compose_authorization_id': None}, {'compose_authorization_id': '../foreign'}, {'owner_ready': True})]
        missing = dict(value); missing.pop('compose_authorization_id'); malformed.append(missing)
        for changed in malformed:
            with self.subTest(changed=changed), self.assertRaises(ValueError): protocol.operation_request(changed)

    def test_historical_requests_stay_closed_version_one_without_consent_or_role_upgrading(self):
        for kind, role, purpose, candidate, parent in (
                ('propose', 'improver', 'improve_propose', None, None),
                ('repair', 'improver', 'improve_propose', None, 'io_original'),
                ('semantic', 'semantic_reviewer', 'improve_evaluate', 'isc_original', None)):
            value = self.request(); value.pop('compose_authorization_id')
            value.update(version=1, kind=kind, role=role, purpose=purpose, candidate_id=candidate, parent_id=parent)
            self.assertEqual(protocol.operation_request(value), value)
            for changes in ({'compose_authorization_id': 'ica_hidden'}, {'version': 2}):
                with self.subTest(kind=kind, changes=changes), self.assertRaises(ValueError):
                    protocol.operation_request({**value, **changes})

    def test_worker_envelope_binds_composer_purpose_input_and_operation_without_extra_authority(self):
        value = {'version': 1, 'sequence': 1, 'type': 'worker_ready', 'operation_id': 'io_compose', 'attempt': 1,
                 'role': 'composer', 'purpose': 'improve_compose', 'input_hash': 'a' * 64, 'capability_hash': 'c' * 64}
        parsed, raw = protocol.operation_packet(value)
        self.assertEqual(parsed, value); self.assertEqual(json.loads(raw), value)
        for changes in ({'purpose': 'improve_propose'}, {'role': 'improver'}, {'attempt': 3}, {'native_ready': True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): protocol.operation_packet({**value, **changes})

    def test_actual_composer_workspace_keeps_input_and_receipt_identity_and_requires_native_format_two(self):
        f = workspace.OperationWorkspaceTests(); f.setUp()
        self.addCleanup(lambda: self.assertTrue(f.doCleanups(), 'Workspace fixture cleanup failed'))
        value = workspace.materialization()
        value.update(version=2, request=self.request(value['data']))
        self.assertEqual(protocol.operation_materialization(value), value)
        with self.assertRaises(ValueError): protocol.operation_materialization({**value, 'version': 1})
        subject = f.workspace()
        receipt = subject.prepare('operation-1', 1, value)
        self.addCleanup(subject.cleanup_proven, 'operation-1', 1, receipt)
        self.assertEqual((receipt['role'], receipt['purpose']), ('composer', 'improve_compose'))
        self.assertEqual(subject.validate(receipt), value)
        self.assertEqual(subject.prepare('operation-1', 1, value), receipt)
        foreign = {**receipt, 'purpose': 'improve_propose'}
        with self.assertRaises((ValueError, PermissionError)): subject.validate(foreign)

    def test_actual_profile_renders_unchanged_upstream_method_and_preserves_exact_authorized_projection(self):
        f = compose.ComposeProtocolTests(); f.setUp()
        self.addCleanup(f.doCleanups)
        data = copy.deepcopy(f.data)
        manifest = {'version': 2, 'request': self.request(data), 'data': data}
        import improvement_harness2_compose as upstream
        with patch.object(upstream, 'compose_round', wraps=upstream.compose_round) as renderer:
            result = json.loads(profile.operation_user_prompt(manifest))
        renderer.assert_called_once()
        self.assertEqual(renderer.call_args.kwargs, {'t': 1, 'k': 1})
        self.assertEqual(result['request'], manifest['request'])
        self.assertEqual(result['compose_task']['evidence_projection'], data)
        self.assertEqual(result['compose_task']['output_contract']['candidate_limit'], 1)
        self.assertIn('checkpoint 1 of 1', result['compose_task']['upstream_method'])
        self.assertEqual(manifest['data'], data)

    def test_actual_legacy_worker_refuses_composer_before_verifier_engine_or_ack(self):
        from improvement_operation_worker import run_request
        f = workspace.OperationWorkspaceTests(); f.setUp()
        self.addCleanup(lambda: self.assertTrue(f.doCleanups(), 'Workspace fixture cleanup failed'))
        subject = f.workspace()
        pin = {'version': 1, 'provider': 'anthropic-cli', 'engine_id': 'claude-sdk', 'model': 'synthetic-unexecuted',
            'reasoning': 'medium', 'cli_path': str(f.root / 'never-launch.exe'), 'cli_hash': 'a' * 64,
            'cli_version': 'engineering', 'sdk_version': '0.2.116', 'profile_version': 'engineering', 'profile_hash': 'b' * 64}
        value = workspace.materialization()
        value.update(version=2, request=self.request(value['data']), engine_config_hash=IM._hash(pin))
        receipt = subject.prepare('operation-1', 1, value)
        self.addCleanup(subject.cleanup_proven, 'operation-1', 1, receipt)
        async def control(): self.fail('Legacy composer reached ACK')
        async def emit(event): self.fail('Legacy composer emitted readiness')
        def forbidden(*args, **kwargs): self.fail('Legacy composer reached verifier or engine factory')
        payload = {'version': 1, 'config_pin': pin, 'workspace_root': str(subject.root),
                   'receipt': receipt, 'capability_hash': 'c' * 64}
        with self.assertRaisesRegex(ValueError, 'operation_native_worker_required'):
            asyncio.run(run_request(payload, control, emit, adapter_factory=forbidden, engine_factory=forbidden))

    def test_existing_ledger_reserves_composer_and_usage_keeps_actual_unobserved_attempt(self):
        with tempfile.TemporaryDirectory(prefix='compose-role-ledger-') as temporary:
            root = Path(temporary)
            store = GoalStore(root / 'resonance.sqlite3')
            ledger = CallLedger(store)
            identifier = ledger.reserve(purpose='improve_compose', reason_ref='improvement_operation:io_compose:attempt:1',
                context_ref='improvement:experiment-one', mirror_ref='improvement_operation:io_compose',
                brain_id='brain-schema-control', obligation=True, attempt=1)
            self.assertIsNotNone(identifier)
            self.assertIsNone(ledger.get(identifier)['engine_at'])
            self.assertTrue(ledger.mark_engine(identifier, 'synthetic_storage_fixture', 'unexecuted'))
            self.assertTrue(ledger.settle(identifier, 'ok'))
            self.assertFalse(ledger.refund(identifier))
            with patch.object(usage_store, '_PATH', root / 'usage.json'):
                self.assertEqual(usage._operation_references('experiment-one', 'io_compose'),
                    ({('improvement_operation:io_compose', 1)}, ['resonance.sqlite3'], 0))
                self.assertEqual(usage._operation_references('foreign-experiment', 'io_compose')[0], set())
                self.assertEqual(usage._operation_references('experiment-one', 'foreign-operation')[0], set())


if __name__ == '__main__': unittest.main()
