"""Late actual-store corruption/domain controls; no native/lifecycle proof."""
from _paths import ROOT, SERVER  # noqa: F401

import json
import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
import test_improvement_compose_inputs as fixtures


class ComposeInputRaceTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ComposeInputTests(); self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def test_actual_call_status_corruption_after_projection_prevents_input_publication(self):
        # Deliberate stored corruption of an already-settled synthetic control,
        # not a valid transition or an invented engine/account observation.
        original = self.f.assets.blobs.write
        changed = []
        def write(brain, raw):
            digest = original(brain, raw)
            if json.loads(raw).get('kind') == 'body_compose_projection' and not changed:
                with self.f.store._Tx(self.f.store) as connection:
                    call = connection.execute("SELECT call_id FROM improvement_trial_attempts WHERE trial_id='it_technical_comparison_0'").fetchone()[0]
                    connection.execute("UPDATE agent_calls SET status='interrupted' WHERE id=?", (call,))
                changed.append(call)
            return digest
        with patch.object(self.f.assets.blobs, 'write', side_effect=write), self.assertRaises(fixtures.DENIED):
            self.f.build()
        self.assertEqual(len(changed), 1)
        self.f.assert_no_publication()

    def test_domain_marker_added_in_final_event_rolls_back_input_and_exposures(self):
        original = self.f.assets._event
        changed = []
        def event(connection, principal, key, operation, payload, result):
            if operation == 'compose_input':
                original(connection, principal, 'native-qualification:' + 'b' * 64,
                    'native_qualification_session', {'run_hash': 'b' * 64}, {'unanchored_refusal_control': True})
                changed.append(True)
            return original(connection, principal, key, operation, payload, result)
        with patch.object(self.f.assets, '_event', side_effect=event), \
                self.assertRaisesRegex(PermissionError, 'qualification_store_anchor_required'):
            self.f.build()
        self.assertEqual(changed, [True])
        self.f.assert_no_publication()
        with closing(self.f.store._conn()) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM improvement_events WHERE operation='native_qualification_session'").fetchone()[0], 0)

    def test_policy_identity_drift_after_projection_prevents_input_publication(self):
        # Controlled policy-observer seam changes only after actual encrypted
        # input bytes exist; no repository files/native qualification are forged.
        original_write, original_policy = self.f.assets.blobs.write, self.f.service.reports._policy
        changed = []
        def write(brain, raw):
            digest = original_write(brain, raw)
            if json.loads(raw).get('kind') == 'body_compose_projection': changed.append(True)
            return digest
        def policy(value):
            observed = original_policy(value)
            return {**observed, 'source_hash': 'f' * 64} if changed else observed
        with patch.object(self.f.assets.blobs, 'write', side_effect=write), \
                patch.object(self.f.service.reports, '_policy', side_effect=policy), self.assertRaises(fixtures.DENIED):
            self.f.build()
        self.assertEqual(changed, [True])
        self.f.assert_no_publication()


class ComposeInputDependencyTests(unittest.TestCase):
    def test_host_input_requires_concrete_existing_plans(self):
        from improvement_compose_inputs import ComposeInputs
        with self.assertRaisesRegex(TypeError, 'concrete_compose_plans_required'): ComposeInputs(object())


if __name__ == '__main__': unittest.main()
