"""Standalone derived read outcomes; immutable brokers and synthetic native records."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import hashlib
import importlib.util
import json
import unittest

from improvement_store import _hash, _json
from test_improvement_skill_asset_broker import manifest as make_manifest, request as skill_request

if importlib.util.find_spec('improvement_read_outcome_broker'):
    from improvement_read_outcome_broker import PinnedReadOutcomeBroker
else:
    PinnedReadOutcomeBroker = None
if importlib.util.find_spec('improvement_read_outcome_proof'):
    from improvement_read_outcome_proof import correlate_read_outcomes
else:
    correlate_read_outcomes = None

SKILL = 'mcp__skill__skill_asset_read'
FIXTURE = 'mcp__fixture__fixture_read'
HOST = 'trial_read_broker_observation'


class ReadOutcomeProofTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(correlate_read_outcomes, 'Unique host/native read-outcome correlation is missing')
        self.assertIsNotNone(PinnedReadOutcomeBroker)
        self.manifest = make_manifest() | {'version': 3}
        text = '42\r\nCafé 日本語\x00'
        self.manifest['case']['fixtures'] = [{'snapshot_id': 'snapshot-a', 'content': text,
            'hash': hashlib.sha256(text.encode()).hexdigest(), 'source': {'source_version': 'v1',
            'data_period': 'synthetic', 'timezone': 'UTC', 'cutoff': '2026-10-24', 'schema': 'text/plain'}}]
        self.workspace = {'trial_id': 'trial-a', 'attempt': 1, 'input_hash': _hash(self.manifest)}
        self.broker = PinnedReadOutcomeBroker(self.manifest, **self.workspace)

    def args(self, tool):
        return skill_request(self.manifest) if tool == SKILL else {'snapshot_id': 'snapshot-a', 'source_version': 'v1'}

    def read(self, *, tool=SKILL, args=None, identifier='call-a', flag=None):
        args = self.args(tool) if args is None else args
        response = self.broker.read(tool, args)
        return [{'type': 'tool_call', 'id': identifier, 'name': tool, 'input': copy.deepcopy(args), 'session_id': 'session-a'},
            {'type': 'tool_result', 'id': identifier, 'content': [{'type': 'text', 'text': _json(response)}],
             'is_error': flag, 'native_is_error': flag, 'session_id': 'session-a'},
            {'type': HOST, 'observation': self.broker.observations[-1], 'session_id': 'session-a'}]

    def events(self, *reads):
        return [{'type': 'native_system', 'subtype': 'init', 'data': {'session_id': 'session-a'}}] + [
            item for read in reads for item in read]

    def check(self, events):
        return correlate_read_outcomes(self.manifest, self.workspace, events)

    def rewrite(self, read, change):
        value = json.loads(read[2]['observation']['response_text'])
        change(value)
        text = _json(value)
        read[2]['observation'].update(response_text=text, response_hash=_hash(value))
        read[1]['content'][0]['text'] = text

    def test_exact_success_delivery_with_optional_none_retains_raw_value_and_explicit_basis(self):
        reads = [self.read(tool=tool, identifier='call-' + str(index)) for index, tool in enumerate((SKILL, FIXTURE))]
        result = self.check(self.events(*reads))
        self.assertEqual(result['verdict'], 'pass')
        self.assertEqual(len(result['proofs']), 2)
        for proof in result['proofs']:
            self.assertEqual(proof['basis'], 'exact_host_success_and_native_delivery')
            self.assertIsNone(proof['native_error_value'])
            self.assertEqual(proof['outcome'], 'hit')
        self.assertTrue(all(read[1]['is_error'] is None for read in reads))

    def test_explicit_false_success_is_observed_without_changing_any_raw_event(self):
        events = self.events(self.read(flag=False))
        before = copy.deepcopy(events)
        result = self.check(events)
        self.assertEqual(result['verdict'], 'pass')
        self.assertIs(result['proofs'][0]['native_error_value'], False)
        self.assertEqual(events, before)

    def test_optional_none_without_exact_host_or_native_delivery_is_unknown(self):
        read = self.read()
        for events in (self.events(read[:2]), self.events([read[2]]), self.events([read[0], read[2]]), self.events()):
            with self.subTest(events=events):
                self.assertEqual(self.check(events)['verdict'], 'unknown')

    def test_explicit_native_error_cannot_be_overridden_by_successful_host_bytes(self):
        self.assertEqual(self.check(self.events(self.read(flag=True)))['verdict'], 'fail')

    def test_genuine_denial_is_verified_boundary_evidence_and_not_a_successful_read(self):
        for tool in (SKILL, FIXTURE):
            args = self.args(tool) | ({'asset_id': 'foreign'} if tool == SKILL else {'snapshot_id': 'foreign'})
            result = self.check(self.events(self.read(tool=tool, args=args, flag=True)))
            self.assertEqual(result['verdict'], 'pass')
            self.assertEqual(result['proofs'][0]['outcome'], 'miss')
            self.assertEqual(result['proofs'][0]['basis'], 'exact_host_denial_and_native_error')

    def test_denial_with_missing_or_contradictory_native_error_cannot_pass(self):
        for flag in (None, False, 0, 'true'):
            read = self.read(args=self.args(SKILL) | {'asset_id': 'foreign'}, flag=flag)
            self.assertNotEqual(self.check(self.events(read))['verdict'], 'pass')

    def test_absent_raw_fields_are_not_silently_projected_as_none(self):
        for key in ('is_error', 'native_is_error'):
            read = self.read()
            read[1].pop(key)
            self.assertEqual(self.check(self.events(read))['verdict'], 'unknown')

    def test_malformed_optional_flags_cannot_become_success(self):
        for flag in (0, 1, 'false', [], {}):
            self.assertNotEqual(self.check(self.events(self.read(flag=flag)))['verdict'], 'pass')

    def test_parallel_equal_arguments_join_by_response_identity_in_reversed_delivery_order(self):
        for tool in (SKILL, FIXTURE):
            first = self.read(tool=tool, identifier='call-a')
            second = self.read(tool=tool, identifier='call-b')
            first[1]['content'], second[1]['content'] = second[1]['content'], first[1]['content']
            events = self.events([first[0], second[0], second[1], first[1], second[2], first[2]])
            result = self.check(events)
            self.assertEqual(result['verdict'], 'pass')
            self.assertEqual(len({proof['observation_id'] for proof in result['proofs']}), 2)
            self.assertEqual({proof['tool_use_id'] for proof in result['proofs']}, {'call-a', 'call-b'})

    def test_duplicate_call_result_or_host_record_cannot_pass(self):
        for index in range(3):
            read = self.read()
            self.assertEqual(self.check(self.events(read + [copy.deepcopy(read[index])]))['verdict'], 'fail')

    def test_valid_read_plus_orphan_result_or_other_tool_response_replay_fails(self):
        read = self.read()
        orphan = copy.deepcopy(read[1]) | {'id': 'orphan'}
        self.assertEqual(self.check(self.events(read + [orphan]))['verdict'], 'fail')
        call = copy.deepcopy(read[0]) | {'id': 'other', 'name': 'Bash'}
        replay = copy.deepcopy(read[1]) | {'id': 'other'}
        self.assertEqual(self.check(self.events(read + [call, replay]))['verdict'], 'fail')

    def test_one_response_cannot_be_replayed_for_two_native_calls(self):
        first, second = self.read(identifier='call-a'), self.read(identifier='call-b')
        second[1]['content'] = copy.deepcopy(first[1]['content'])
        self.assertEqual(self.check(self.events(first, second))['verdict'], 'fail')

    def test_absent_duplicate_or_foreign_native_session_cannot_pass(self):
        read = self.read()
        self.assertEqual(self.check(read)['verdict'], 'unknown')
        events = self.events(read)
        self.assertEqual(self.check(events + [copy.deepcopy(events[0])])['verdict'], 'fail')
        for index in range(3):
            changed = copy.deepcopy(read)
            changed[index]['session_id'] = 'foreign'
            self.assertEqual(self.check(self.events(changed))['verdict'], 'fail')

    def test_result_before_call_and_host_or_call_without_result_cannot_pass(self):
        read = self.read()
        self.assertEqual(self.check(self.events([read[1], read[0], read[2]]))['verdict'], 'fail')
        self.assertEqual(self.check(self.events([read[0], read[2]]))['verdict'], 'unknown')

    def test_foreign_and_wrong_typed_host_bindings_fail_even_when_response_is_rehashed(self):
        for field, value in (('trial_id', 'trial-b'), ('attempt', True), ('attempt', 1.0),
                             ('input_hash', '0' * 64), ('effective_view', {})):
            read = self.read()
            read[2]['observation'][field] = value
            self.rewrite(read, lambda response: response.update({field: value}))
            with self.subTest(field=field, value=value):
                self.assertEqual(self.check(self.events(read))['verdict'], 'fail')

    def test_changed_native_arguments_or_response_bytes_do_not_pass(self):
        for change in ('args', 'extra-text', 'truncated', 'extra-block'):
            read = self.read()
            if change == 'args':
                read[0]['input']['asset_id'] = 'foreign'
            elif change == 'extra-block':
                read[1]['content'].append({'type': 'text', 'text': 'extra'})
            else:
                text = read[1]['content'][0]['text']
                read[1]['content'][0]['text'] = text[:-2] if change == 'truncated' else text + '\n'
            self.assertNotEqual(self.check(self.events(read))['verdict'], 'pass')

    def test_host_response_text_hash_nonce_and_closed_fields_are_verified(self):
        for change in ('text', 'hash', 'nonce', 'extra-host-field', 'extra-response-field'):
            read = self.read()
            observation = read[2]['observation']
            if change == 'text':
                observation['response_text'] += '\n'
            elif change == 'hash':
                observation['response_hash'] = '0' * 64
            elif change == 'nonce':
                observation['observation_id'] = 'invalid'
            elif change == 'extra-host-field':
                observation['claimed_pass'] = True
            else:
                self.rewrite(read, lambda response: response.update(claimed_pass=True))
            self.assertEqual(self.check(self.events(read))['verdict'], 'fail')

    def test_successful_payload_is_checked_against_pinned_skill_and_fixture(self):
        for tool in (SKILL, FIXTURE):
            for field in ('content', 'hash' if tool == FIXTURE else 'content_hash', 'status'):
                read = self.read(tool=tool)
                self.rewrite(read, lambda response: response['result'].update({field: 'forged'}))
                self.assertEqual(self.check(self.events(read))['verdict'], 'fail')

    def test_fixture_sequence_must_be_positive_unique_integer(self):
        for value in (0, True, 1.0, '1'):
            read = self.read(tool=FIXTURE)
            self.rewrite(read, lambda response: response['result'].update(sequence=value))
            self.assertEqual(self.check(self.events(read))['verdict'], 'fail')
        first, second = self.read(tool=FIXTURE, identifier='fixture-a'), self.read(tool=FIXTURE, identifier='fixture-b')
        first_sequence = json.loads(first[2]['observation']['response_text'])['result']['sequence']
        self.rewrite(second, lambda response: response['result'].update(sequence=first_sequence))
        self.assertEqual(self.check(self.events(first, second))['verdict'], 'fail')

    def test_string_native_content_is_accepted_but_structured_or_unrelated_results_are_not(self):
        read = self.read()
        read[1]['content'] = read[1]['content'][0]['text']
        self.assertEqual(self.check(self.events(read))['verdict'], 'pass')
        read[1]['content'] = json.loads(read[1]['content'])
        self.assertNotEqual(self.check(self.events(read))['verdict'], 'pass')

    def test_legacy_asset_observation_cannot_be_reinterpreted_as_a_new_outcome(self):
        read = self.read()
        read[2]['type'] = 'skill_asset_broker_observation'
        self.assertEqual(self.check(self.events(read))['verdict'], 'unknown')

    def test_partial_success_and_missing_second_outcome_do_not_return_a_partial_pass(self):
        first, second = self.read(identifier='call-a'), self.read(identifier='call-b')
        result = self.check(self.events(first, second[:1]))
        self.assertEqual(result['verdict'], 'unknown')
        self.assertEqual(result['proofs'], [])

    def test_returned_proofs_and_mutated_callers_cannot_change_inputs(self):
        events = self.events(self.read())
        before = copy.deepcopy(events)
        result = self.check(events)
        result['proofs'][0]['effective_view']['view_hash'] = 'mutated'
        self.assertEqual(events, before)
        self.assertEqual(self.check(events)['verdict'], 'pass')

    def test_malformed_native_identity_and_workspace_refuse_without_crashing(self):
        read = self.read()
        read[1]['id'] = []
        self.assertEqual(self.check(self.events(read))['verdict'], 'fail')
        self.workspace['attempt'] = True
        self.assertEqual(self.check(self.events(self.read()))['verdict'], 'fail')


if __name__ == '__main__':
    unittest.main()
