"""Untrusted synthetic records test shape/binding; no native or quality proof."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

import improvement_sandbox as SB
import improvement_claude as native
import improvement_store as IM
from improvement_comparison_results import _NATIVE_CHECKS
import test_improvement_trial_checks as fixtures
import test_improvement_view_trial_protocol as protocol


class ViewRecordChecksTests(unittest.TestCase):
    def fixture(self, variant='baseline'):
        f = fixtures.TrialChecksTests()
        f.setUp()
        shaped = protocol.request(variant)
        f.request.update(version=4, variant=variant,
            lineage=shaped['lineage'] | {'arm_hash': f.request['pins']['candidate_bundle_hash']}, view=shaped['view'])
        f.manifest.update(version=2, effective_view=copy.deepcopy(f.request['view']))
        if variant == 'candidate':
            f.manifest['bundle_hash'] = f.request['pins']['candidate_bundle_hash']
            f.manifest['assets'][0]['id'] = f.request['lineage']['candidate_id']
        f.workspace.update(input_hash=IM._hash(f.manifest), effective_hash=SB._effective_hash(f.manifest))
        f.receipt.update(version=2, effective_view=copy.deepcopy(f.request['view']),
            input_hash=f.workspace['input_hash'], effective_hash=f.workspace['effective_hash'], bundle_hash=f.manifest['bundle_hash'])
        f.receipt['asset_revisions'][0]['id'] = f.manifest['assets'][0]['id']
        prompt_hash = hashlib.sha256(SB.trial_system_prompt(f.manifest).encode()).hexdigest()
        f.receipt.update(expected_system_prompt_hash=prompt_hash, system_prompt_hash=prompt_hash)
        f.rebuild_packets()
        return f

    def test_full_v4_records_preserve_all_eighteen_checks_and_observational_unknowns(self):
        for variant in ('baseline', 'candidate'):
            f = self.fixture(variant)
            result = f.check()
            self.assertEqual(set(result), set(_NATIVE_CHECKS))
            for identifier in ('materialization', 'workspace_binding', 'installation', 'asset_installation'):
                self.assertEqual(result[identifier]['verdict'], 'pass', (variant, identifier, result))
            for identifier in ('actual_reasoning', 'asset_observed_use'):
                self.assertEqual(result[identifier]['verdict'], 'unknown')

    def test_changed_view_receipt_or_legacy_runtime_is_explicitly_rejected(self):
        for key in ('view_id', 'view_hash', 'binding_hash'):
            for location, identifier in (('manifest', 'materialization'), ('receipt', 'installation')):
                f = self.fixture()
                obj = getattr(f, location)
                obj['effective_view'][key] = 'foreign-view' if key == 'view_id' else 'c' * 64
                f.rebuild_packets()
                self.assertEqual(f.check()[identifier]['verdict'], 'fail', (key, location))
        f = self.fixture()
        f.receipt.pop('effective_view')
        f.receipt['version'] = 1
        f.rebuild_packets()
        self.assertEqual(f.check()['installation']['verdict'], 'fail')
        f = self.fixture()
        f.request.pop('view')
        f.request.pop('lineage')
        f.request['version'] = 1
        self.assertEqual(f.check()['execution_records']['verdict'], 'fail')
        f = self.fixture('candidate')
        f.manifest['assets'][0]['id'] = 'foreign-candidate'
        self.assertEqual(f.check()['materialization']['verdict'], 'fail')

    def test_profile_receipt_is_derived_from_actual_v2_workspace(self):
        f = self.fixture('candidate')
        with tempfile.TemporaryDirectory(prefix='view-native-binding-') as directory:
            workspace = SB.TrialWorkspace(Path(directory) / 'workspaces')
            receipt = workspace.prepare('actual-bound-view', 1, f.manifest)
            profile = native.TrialProfile({key: f.request['engine_config'][key]
                for key in ('provider', 'model', 'reasoning', 'cli_path', 'sdk_version')},
                SB.FixtureBroker(f.manifest['case']['fixtures'], f.manifest['grant_hash']), SB.trial_system_prompt(f.manifest))
            profile.bind_installation(f.manifest, receipt, f.capability)
            observed = profile.installation_receipt('synthetic-view-session')
            self.assertEqual(observed['version'], 2)
            self.assertEqual(observed['effective_view'], f.request['view'])
            self.assertEqual(observed['input_hash'], receipt['input_hash'])
            self.assertIsNone(observed['actual_reasoning'])
            self.assertEqual(observed['asset_revisions'][0]['observed_use'], 'unknown')
            observed['effective_view']['view_hash'] = 'c' * 64
            self.assertEqual(profile.installation_receipt('synthetic-view-session')['effective_view'], f.request['view'])
            workspace.cleanup('actual-bound-view', 1)


if __name__ == '__main__':
    unittest.main()
