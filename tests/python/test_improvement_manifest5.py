"""Explicit native baseline input without inventing a paired effective view."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import unittest

import improvement_sandbox as SB
from improvement_skill_asset_broker import SkillAssetBroker
from improvement_read_outcome_broker import PinnedReadOutcomeBroker
from improvement_skill_asset_proof import correlate_asset_reads
from improvement_read_outcome_proof import correlate_read_outcomes
import test_improvement_read_outcome_broker as fixture


def baseline(version=5):
    value = fixture.manifest(version)
    value.pop('effective_view')
    return value


class NativeBaselineManifestTests(unittest.TestCase):
    def test_baseline_five_has_exact_real_bundle_fields_without_effective_view(self):
        old, native = baseline(1), baseline()
        validated = SB._manifest(native)
        self.assertEqual(validated, native)
        self.assertEqual(set(native), set(old))
        self.assertEqual({**native, 'version': 1}, old)
        self.assertNotEqual(SB._hash(native), SB._hash(old))
        self.assertEqual(SB.trial_system_prompt(native).encode(), SB.trial_system_prompt(old).encode())
        self.assertEqual(SB._effective_hash(native), SB._effective_hash(old))
        native['assets'][0]['content'] = 'external mutation'
        self.assertEqual(validated['assets'][0]['content'], fixture.SKILL_CONTENT)

    def test_baseline_accepts_the_real_multi_asset_bundle_without_single_view_constraint(self):
        value = baseline()
        agent = {'id': 'agent-revision', 'path': 'agents/reviewer.md', 'content': 'Retain exact owner rules.\n',
                 'hash': fixture.sha('Retain exact owner rules.\n')}
        value['assets'].append(agent)
        self.assertEqual(SB._manifest(value), value)
        self.assertIn('agents/reviewer.md', SB.trial_system_prompt(value))
        self.assertIn(agent['content'].strip(), SB.trial_system_prompt(value))

    def test_baseline_five_refuses_invented_view_and_unknown_fields(self):
        for extra in ({'effective_view': fixture.manifest(4)['effective_view']},
                      {'native_verified': True}, {'provider_accepted': True}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                SB._manifest({**baseline(), **extra})

    def test_baseline_five_rechecks_every_protected_content_and_fixture_pin(self):
        mutations = [lambda v: v['assets'][0].update(content='unhashed mutation'),
            lambda v: v['assets'][0].update(path='../outside.md'),
            lambda v: v['assets'].append(copy.deepcopy(v['assets'][0])),
            lambda v: v['baseline_context'].update(content='unhashed context'),
            lambda v: v['public_contract'].update(hash='0' * 64),
            lambda v: v['case']['fixtures'][0].update(hash='0' * 64),
            lambda v: v.update(grant_hash='not-a-digest'), lambda v: v.update(learning_origin='live')]
        for mutate in mutations:
            value = baseline(); mutate(value)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): SB._manifest(value)

    def test_paired_view_brokers_refuse_baseline_and_correlators_cannot_claim_read_use(self):
        value = baseline()
        workspace = {'trial_id': 'baseline-trial', 'attempt': 1, 'input_hash': SB._hash(value)}
        for broker in (SkillAssetBroker, PinnedReadOutcomeBroker):
            with self.subTest(broker=broker), self.assertRaises(ValueError): broker(value, **workspace)
        for correlate in (correlate_asset_reads, correlate_read_outcomes):
            self.assertEqual(correlate(value, workspace, [])['verdict'], 'unknown')

    def test_future_or_boolean_versions_remain_unsupported(self):
        for version in (True, False, 0, 6, '5'):
            with self.subTest(version=version), self.assertRaises(ValueError): SB._manifest(baseline(version))


if __name__ == '__main__': unittest.main()
