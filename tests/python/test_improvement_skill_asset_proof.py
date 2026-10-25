"""Independent immutable-read correlation; synthetic records, no SDK or model execution."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import importlib.util
import unittest

from improvement_skill_asset_broker import SkillAssetBroker
from improvement_store import _hash, _json
import test_improvement_skill_asset_broker as fixtures

if importlib.util.find_spec('improvement_skill_asset_proof'):
    from improvement_skill_asset_proof import correlate_asset_reads
else:
    correlate_asset_reads = None

TOOL = 'mcp__skill__skill_asset_read'


class AssetReadProofTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(correlate_asset_reads, 'Actual native-read correlation is missing')
        self.manifest = fixtures.manifest()
        self.workspace = {'trial_id': 'trial-a', 'attempt': 2, 'input_hash': _hash(self.manifest)}
        self.args = fixtures.request(self.manifest)
        self.broker = SkillAssetBroker(self.manifest, **self.workspace)

    def read(self, identifier='native-call-a', session='session-a'):
        response = self.broker.read(self.args)
        call = {'type': 'tool_call', 'id': identifier, 'name': TOOL,
                'input': dict(self.args), 'session_id': session}
        result = {'type': 'tool_result', 'id': identifier, 'content': [
            {'type': 'text', 'text': _json(response)}], 'is_error': False,
            'native_is_error': False, 'session_id': session}
        observation = {'type': 'skill_asset_broker_observation',
                       'observation': self.broker.observations[-1], 'session_id': session}
        return [call, result, observation]

    def events(self, *reads):
        return [{'type': 'native_system', 'subtype': 'init', 'data': {'session_id': 'session-a'}}] + [
            event for read in reads for event in read]

    def check(self, events):
        return correlate_asset_reads(self.manifest, self.workspace, events)

    def test_exact_native_call_result_and_broker_response_prove_only_a_read(self):
        result = self.check(self.events(self.read()))
        self.assertEqual(result['verdict'], 'pass')
        self.assertEqual(len(result['proofs']), 1)
        proof = result['proofs'][0]
        for key in ('trial_id', 'attempt', 'input_hash'):
            self.assertEqual(proof[key], self.workspace[key])
        self.assertEqual(proof['tool_use_id'], 'native-call-a')
        self.assertEqual(proof['session_id'], 'session-a')
        self.assertEqual(proof['content_hash'], self.manifest['assets'][0]['hash'])
        self.assertNotIn('understood', proof)

    def test_parallel_equal_arguments_join_by_unique_response_not_recording_order(self):
        first, second = self.read('call-a'), self.read('call-b')
        first[1]['content'], second[1]['content'] = second[1]['content'], first[1]['content']
        events = self.events([first[0], second[0], first[1], second[1], second[2], first[2]])
        result = self.check(events)
        self.assertEqual(result['verdict'], 'pass')
        self.assertEqual({p['tool_use_id'] for p in result['proofs']}, {'call-a', 'call-b'})
        self.assertEqual(len({p['observation_id'] for p in result['proofs']}), 2)

    def test_available_or_broker_success_alone_does_not_prove_native_read(self):
        read = self.read()
        for events in (self.events(), self.events([read[2]]), self.events(read[:2])):
            with self.subTest(events=events):
                self.assertNotEqual(self.check(events)['verdict'], 'pass')

    def test_duplicate_native_call_or_result_cannot_pass(self):
        read = self.read()
        for extra in read[:2]:
            with self.subTest(extra=extra['type']):
                self.assertEqual(self.check(self.events(read + [copy.deepcopy(extra)]))['verdict'], 'fail')

    def test_duplicate_broker_observation_or_replayed_response_cannot_pass(self):
        first, second = self.read('call-a'), self.read('call-b')
        events = self.events(first + [copy.deepcopy(first[2])])
        self.assertEqual(self.check(events)['verdict'], 'fail')
        second[1]['content'] = copy.deepcopy(first[1]['content'])
        self.assertNotEqual(self.check(self.events(first, second))['verdict'], 'pass')

    def test_result_without_call_and_call_without_result_do_not_pass(self):
        read = self.read()
        for events in (self.events(read[1:]), self.events([read[0], read[2]])):
            self.assertNotEqual(self.check(events)['verdict'], 'pass')

    def test_valid_read_plus_orphan_result_cannot_pass(self):
        read = self.read()
        orphan = copy.deepcopy(read[1]) | {'id': 'orphan-result'}
        self.assertNotEqual(self.check(self.events(read + [orphan]))['verdict'], 'pass')

    def test_valid_read_plus_response_replay_through_other_tool_cannot_pass(self):
        read = self.read()
        foreign_call = copy.deepcopy(read[0]) | {'id': 'fixture-call', 'name': 'mcp__fixture__fixture_read'}
        replay = copy.deepcopy(read[1]) | {'id': 'fixture-call'}
        self.assertNotEqual(self.check(self.events(read + [foreign_call, replay]))['verdict'], 'pass')

    def test_missing_or_duplicate_init_and_foreign_sessions_do_not_pass(self):
        read = self.read()
        self.assertNotEqual(self.check(read)['verdict'], 'pass')
        events = self.events(read)
        self.assertEqual(self.check(events + [copy.deepcopy(events[0])])['verdict'], 'fail')
        for index in range(3):
            changed = copy.deepcopy(read)
            changed[index]['session_id'] = 'session-foreign'
            self.assertEqual(self.check(self.events(changed))['verdict'], 'fail')

    def test_foreign_view_attempt_input_or_asset_in_host_observation_fails(self):
        read = self.read()
        for key, wrong in (('trial_id', 'trial-b'), ('attempt', 3), ('input_hash', '0' * 64),
                           ('asset_id', 'asset-b'), ('content_hash', '0' * 64)):
            changed = copy.deepcopy(read)
            changed[2]['observation'][key] = wrong
            with self.subTest(key=key):
                self.assertEqual(self.check(self.events(changed))['verdict'], 'fail')
        changed = copy.deepcopy(read)
        changed[2]['observation']['effective_view']['binding_hash'] = '0' * 64
        self.assertEqual(self.check(self.events(changed))['verdict'], 'fail')

    def test_wrong_call_name_arguments_or_response_content_cannot_pass(self):
        for change in ('name', 'input', 'content', 'truncated', 'forged-id'):
            read = self.read()
            if change == 'name':
                read[0]['name'] = 'mcp__fixture__fixture_read'
            elif change == 'input':
                read[0]['input']['view_hash'] = '0' * 64
            elif change == 'content':
                read[1]['content'][0]['text'] += ' extra text'
            elif change == 'truncated':
                read[1]['content'][0]['text'] = read[1]['content'][0]['text'][:-3]
            else:
                read[1]['content'][0]['text'] = read[1]['content'][0]['text'].replace(
                    read[2]['observation']['observation_id'], '0' * 64)
            with self.subTest(change=change):
                self.assertNotEqual(self.check(self.events(read))['verdict'], 'pass')

    def test_native_error_missing_flag_or_wrong_typed_flag_is_not_success(self):
        for value in (True, None, 0, 'false'):
            read = self.read()
            read[1]['is_error'] = value
            read[1]['native_is_error'] = value
            with self.subTest(value=value):
                self.assertNotEqual(self.check(self.events(read))['verdict'], 'pass')

    def test_host_response_text_hash_or_request_corruption_fails(self):
        for field in ('response_hash', 'response_text', 'request'):
            read = self.read()
            observation = read[2]['observation']
            if field == 'response_hash':
                observation[field] = '0' * 64
            elif field == 'response_text':
                observation[field] += '\n'
            else:
                observation[field]['asset_id'] = 'foreign'
            with self.subTest(field=field):
                self.assertEqual(self.check(self.events(read))['verdict'], 'fail')

    def test_returned_proofs_do_not_mutate_inputs_or_later_checks(self):
        events = self.events(self.read())
        before = copy.deepcopy(events)
        result = self.check(events)
        self.assertEqual(events, before)
        result['proofs'][0]['asset_id'] = 'mutated'
        self.assertEqual(self.check(events)['proofs'][0]['asset_id'], 'asset-a')


if __name__ == '__main__':
    unittest.main()
