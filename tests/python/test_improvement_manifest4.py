"""Readonly manifest4 foundation only; no emitter/profile/native integration."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import hashlib
import unittest
from unittest.mock import patch

import improvement_sandbox as SB
from improvement_skill_asset_broker import SkillAssetBroker
from improvement_read_outcome_broker import PinnedReadOutcomeBroker
from improvement_read_outcome_proof import correlate_read_outcomes
from improvement_skill_asset_proof import correlate_asset_reads
import test_improvement_read_outcome_broker as F


class ManifestFourTests(unittest.TestCase):
    def value(self, version=4): return F.manifest(version)

    def binding(self, value):
        return {'trial_id': 'trial-a', 'attempt': 2, 'input_hash': SB._hash(value)}

    def test_four_uses_exact_three_field_set_and_defensive_full_validation(self):
        value = self.value()
        actual = SB._manifest(value)
        self.assertEqual(actual, value)
        self.assertEqual(set(actual), set(self.value(3)))
        value['assets'][0]['content'] = 'caller mutation'
        self.assertEqual(actual['assets'][0]['content'], F.SKILL_CONTENT)

    def test_four_closed_view_single_skill_context_contract_and_fixture_checks(self):
        mutations = [lambda v: v.update(extra=True), lambda v: v.pop('effective_view'),
            lambda v: v['effective_view'].update(extra='foreign'),
            lambda v: v['effective_view'].update(view_hash='bad'),
            lambda v: v['assets'].append(copy.deepcopy(v['assets'][0])),
            lambda v: v['assets'][0].update(path='rules/report.md'),
            lambda v: v['assets'][0].update(content='unhashed mutation'),
            lambda v: v['baseline_context'].update(content='unhashed context'),
            lambda v: v['public_contract'].update(hash='0' * 64),
            lambda v: v['case']['fixtures'][0].update(hash='0' * 64)]
        for mutate in mutations:
            value = self.value(); mutate(value)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): SB._manifest(value)

    def test_four_prompt_is_readonly_and_exactly_three_prompt_bytes(self):
        value = self.value(); prompt = SB.trial_system_prompt(value)
        self.assertEqual(prompt.encode(), SB.trial_system_prompt(self.value(3)).encode())
        self.assertNotIn(F.SKILL_CONTENT, prompt)
        self.assertIn('mcp__skill__skill_asset_read', prompt)
        self.assertIn(SB._json(F.skill_args(value)), prompt)

    def test_four_effective_hash_includes_the_actual_effective_view(self):
        value = self.value(); before = SB._effective_hash(value)
        self.assertEqual(before, SB._effective_hash(self.value(3)))
        value['effective_view']['view_hash'] = '0' * 64
        self.assertNotEqual(SB._effective_hash(value), before)

    def test_legacy_one_two_three_prompt_and_effective_hash_rules_stay_exact(self):
        for version in (1, 2, 3):
            value = self.value(version)
            if version == 1: value.pop('effective_view')
            self.assertEqual(SB._manifest(value), value)
            if version < 3:
                expected_assets = SB._json(value['assets'])
            else:
                expected_assets = ('Read the selected skill using mcp__skill__skill_asset_read with these exact arguments:\n'
                    + SB._json(F.skill_args(value)) + '\nUse the returned pinned instructions for this task.')
            expected = (value['baseline_context']['content'] + '\n\n<effective_assets>\n' + expected_assets
                + '\n</effective_assets>\n\n<public_acceptance>\n' + SB._json(value['public_contract']['content']) + '\n</public_acceptance>')
            self.assertEqual(SB.trial_system_prompt(value).encode(), expected.encode())
            effective = {'context': value['baseline_context']['hash'], 'bundle': value['bundle_hash'],
                         'assets': [{key: a[key] for key in ('id', 'path', 'hash')} for a in value['assets']]}
            if version > 1: effective['effective_view'] = value['effective_view']
            self.assertEqual(SB._effective_hash(value), SB._hash(effective))

    def test_four_skill_broker_exact_bytes_and_binding_refuse_foreign_data(self):
        value = self.value(); binding = self.binding(value)
        broker = SkillAssetBroker(value, **binding)
        args = F.skill_args(value); result = broker.read(args)
        self.assertEqual(result['content'].encode(), F.SKILL_CONTENT.encode())
        self.assertEqual({key: result[key] for key in binding}, binding)
        self.assertEqual(result['effective_view'], value['effective_view'])
        for changes in ({'view_id': 'foreign'}, {'view_hash': '0' * 64}, {'asset_id': 'foreign'}, {'path': 'escape'}):
            self.assertEqual(broker.read({**args, **changes}), {'status': 'skill_asset_miss', 'reason': 'skill_asset_miss'})
        for changes in ({'attempt': True}, {'trial_id': '../foreign'}, {'input_hash': SB._hash(self.value(3))}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): SkillAssetBroker(value, **{**binding, **changes})

    def test_four_outcome_broker_preserves_exact_underlying_payloads_and_frozen_history(self):
        value = self.value(); binding = self.binding(value)
        broker = PinnedReadOutcomeBroker(value, **binding)
        for tool, args, content in ((F.SKILL, F.skill_args(value), F.SKILL_CONTENT),
                                     (F.FIXTURE, F.fixture_args(), F.FIXTURE_CONTENT)):
            result = broker.read(tool, args)
            self.assertEqual(set(result), F.ENVELOPE_FIELDS)
            self.assertEqual(result['result']['content'].encode(), content.encode())
            self.assertEqual(result['request_hash'], SB._hash(args))
            self.assertEqual(broker.observations[-1]['response_text'], SB._json(result))
            result['result']['content'] = 'return mutation'
        value['assets'][0]['content'] = 'input mutation'
        history = broker.observations; history[0]['request'].clear()
        self.assertEqual(len(broker.observations[0]['request']), 4)
        self.assertEqual(broker.read(F.SKILL, F.skill_args(self.value()))['result']['content'], F.SKILL_CONTENT)


class ManifestFourOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.value = F.manifest(4)
        self.workspace = {'trial_id': 'trial-a', 'attempt': 2, 'input_hash': SB._hash(self.value)}
        self.broker = PinnedReadOutcomeBroker(self.value, **self.workspace)

    def read(self, tool, identifier, flag=None, foreign=False):
        args = F.skill_args(self.value) if tool == F.SKILL else F.fixture_args()
        if foreign: args.update({'asset_id': 'foreign'} if tool == F.SKILL else {'snapshot_id': 'foreign'})
        result = self.broker.read(tool, args)
        return [{'type': 'tool_call', 'id': identifier, 'name': tool, 'input': args, 'session_id': 'session-a'},
            {'type': 'tool_result', 'id': identifier, 'content': [{'type': 'text', 'text': SB._json(result)}],
             'is_error': flag, 'native_is_error': flag, 'session_id': 'session-a'},
            {'type': 'trial_read_broker_observation', 'observation': self.broker.observations[-1], 'session_id': 'session-a'}]

    def events(self, *reads):
        return [{'type': 'native_system', 'subtype': 'init', 'data': {'session_id': 'session-a'}}] + [item for read in reads for item in read]

    def test_four_exact_skill_and_fixture_delivery_preserves_raw_none_flags(self):
        events = self.events(self.read(F.SKILL, 'skill'), self.read(F.FIXTURE, 'fixture'))
        frozen = copy.deepcopy(events)
        proof = correlate_read_outcomes(self.value, self.workspace, events)
        self.assertEqual(proof['verdict'], 'pass'); self.assertEqual(len(proof['proofs']), 2)
        self.assertTrue(all(p['native_error_value'] is None for p in proof['proofs']))
        self.assertEqual(events, frozen)

    def test_four_native_denial_true_is_distinct_from_missing_or_false_flag(self):
        for flag, verdict in ((True, 'pass'), (None, 'unknown'), (False, 'fail')):
            self.broker = PinnedReadOutcomeBroker(self.value, **self.workspace)
            events = self.events(self.read(F.SKILL, 'denied', flag=flag, foreign=True))
            proof = correlate_read_outcomes(self.value, self.workspace, events)
            self.assertEqual(proof['verdict'], verdict)

    def test_four_proof_foreign_view_attempt_input_or_session_never_passes(self):
        events = self.events(self.read(F.SKILL, 'skill'))
        for change in ({'attempt': True}, {'input_hash': SB._hash(F.manifest(3))}, {'trial_id': 'foreign'}):
            self.assertEqual(correlate_read_outcomes(self.value, {**self.workspace, **change}, events)['verdict'], 'fail')
        events[1]['session_id'] = 'foreign'
        self.assertEqual(correlate_read_outcomes(self.value, self.workspace, events)['verdict'], 'fail')

    def test_four_never_invokes_or_passes_the_legacy_asset_correlator(self):
        events = self.events(self.read(F.SKILL, 'skill'))
        with patch('improvement_skill_asset_proof.correlate_asset_reads', side_effect=AssertionError('legacy receipt3 path')):
            self.assertEqual(correlate_read_outcomes(self.value, self.workspace, events)['verdict'], 'pass')
        self.assertEqual(correlate_asset_reads(self.value, self.workspace, events),
                         {'verdict': 'unknown', 'reason': 'legacy_asset_use_unobserved', 'proofs': []})


if __name__ == '__main__': unittest.main()
