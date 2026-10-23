"""Actual tuning inputs/workspaces; no model execution or eligibility evidence."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import hashlib
import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
import improvement_sandbox as SB
import test_improvement_view_reservations as reservations
import test_improvement_view_sources as sources


class ViewMaterializationTests(sources.SourceFixture, unittest.IsolatedAsyncioTestCase):
    request = reservations.ViewReservationTests.request
    load = reservations.ViewReservationTests.load
    bound = reservations.ViewReservationTests.bound
    live_request = reservations.ViewReservationTests.live_request

    def materialize(self, trials, metadata, position, key):
        request = self.live_request(metadata, position)
        reserved = trials.reserve(self.owner, request, event_key=key)
        claimed = trials.claim(self.owner, reserved['trial_id'], expected_generation=reserved['generation'])
        context = self.host.context_loader(self.owner, request)
        manifest = trials.materialize(self.owner, reserved['trial_id'], expected_generation=claimed['generation'],
            lease_token=claimed['lease_token'], baseline_context=context)
        return request, claimed, manifest

    async def test_actual_pair_installs_exact_revision_and_candidate_without_canonical_bundle_fabrication(self):
        trials, metadata = self.bound()
        skill = self.f.f.f.skill
        original = skill.read_bytes()
        manifests = {}
        for position in (0, 1):
            request, claimed, manifest = self.materialize(trials, metadata, position, 'view-materialize-pair-' + str(position))
            manifests[request['variant']] = manifest
            self.assertEqual(manifest['version'], 3)
            self.assertEqual(manifest['effective_view'], request['view'])
            with closing(self.assets.store._conn()) as connection:
                resolved, _ = self.host._views.resolve_request(self.owner, request, connection=connection,
                    require_link=True, trial_id=claimed['trial_id'])
                candidate_bundle = connection.execute('SELECT 1 FROM improvement_bundles WHERE manifest_hash=?',
                    (request['pins']['candidate_bundle_hash'],)).fetchone()
            asset = resolved.manifest['assets'][0]
            self.assertEqual(manifest['assets'], [{'id': asset['id'], 'path': asset['canonical_ref'],
                'hash': asset['content_hash'], 'content': resolved.content.decode('utf-8')}])
            self.assertIsNone(candidate_bundle)
            self.assertEqual(hashlib.sha256(manifest['assets'][0]['content'].encode()).hexdigest(), asset['content_hash'])
            receipt = trials.workspace.prepare(claimed['trial_id'], 1, manifest)
            try:
                self.assertEqual(trials.workspace.validate(receipt), manifest)
                prepared = trials.prepared(self.owner, claimed['trial_id'], expected_generation=claimed['generation'],
                    lease_token=claimed['lease_token'], receipt=receipt)
                self.assertEqual(prepared['status'], 'prepared')
            finally:
                trials.workspace.cleanup(claimed['trial_id'], 1)
        self.assertEqual(skill.read_bytes(), original)
        self.assertEqual(manifests['baseline']['baseline_context'], manifests['candidate']['baseline_context'])
        self.assertEqual(manifests['baseline']['case'], manifests['candidate']['case'])
        self.assertNotEqual(manifests['baseline']['assets'][0]['id'], manifests['candidate']['assets'][0]['id'])

    async def test_source_changed_during_solver_read_rolls_back_exposure_and_materialization(self):
        trials, metadata = self.bound()
        request = self.live_request(metadata)
        reserved = trials.reserve(self.owner, request, event_key='view-materialize-source-race')
        claimed = trials.claim(self.owner, reserved['trial_id'], expected_generation=reserved['generation'])
        context = self.host.context_loader(self.owner, request)
        solver = trials.cases._solver
        with closing(self.assets.store._conn()) as connection:
            exposures = tuple(tuple(row) for row in connection.execute('SELECT * FROM improvement_case_exposures ORDER BY fingerprint'))
        changed = False

        def drift(*args, **kwargs):
            nonlocal changed
            value = solver(*args, **kwargs)
            self.f.f.f.skill.write_bytes(self.f.f.f.skill.read_bytes() + b'\nOwner edit during solver read.\n')
            changed = True
            return value

        with patch.object(trials.cases, '_solver', side_effect=drift), self.assertRaises((PermissionError, IM.ConflictError)):
            trials.materialize(self.owner, reserved['trial_id'], expected_generation=claimed['generation'],
                lease_token=claimed['lease_token'], baseline_context=context)
        self.assertTrue(changed, 'The test must reach the actual solver read before the source edit')
        with closing(self.assets.store._conn()) as connection:
            attempt = connection.execute('SELECT materialization_hash,engine_at,workspace_json FROM improvement_trial_attempts '
                'WHERE trial_id=?', (reserved['trial_id'],)).fetchone()
            self.assertEqual(tuple(attempt), (None, None, None))
            self.assertEqual(tuple(tuple(row) for row in connection.execute('SELECT * FROM improvement_case_exposures ORDER BY fingerprint')), exposures)


class WorkspaceViewProtocolTests(unittest.TestCase):
    def test_view_input_rejects_malformed_or_multiple_primary_assets(self):
        from test_improvement_sandbox import SandboxTests
        current = SandboxTests().request() | {'version': 2, 'effective_view': {'view_id': 'iv_actual',
            'view_hash': 'a' * 64, 'binding_hash': 'b' * 64}}
        for assets in ([], [None], [current['assets'][0], current['assets'][0]],
                [current['assets'][0] | {'path': 'agents/report.md'}]):
            with self.subTest(assets=assets), self.assertRaises(ValueError):
                SB._manifest(current | {'assets': assets})

    def test_version1_hash_and_prompt_are_exact_and_version2_identity_is_bound(self):
        from test_improvement_sandbox import SandboxTests
        old = SandboxTests().request()
        expected = IM._hash({'context': old['baseline_context']['hash'], 'bundle': old['bundle_hash'],
            'assets': [{key: asset[key] for key in ('id', 'path', 'hash')} for asset in old['assets']]})
        self.assertEqual(SB._manifest(old), old)
        self.assertEqual(SB._effective_hash(old), expected)
        prompt = old['baseline_context']['content'] + '\n\n<effective_assets>\n' + IM._json(old['assets']) + \
            '\n</effective_assets>\n\n<public_acceptance>\n' + IM._json(old['public_contract']['content']) + '\n</public_acceptance>'
        self.assertEqual(SB.trial_system_prompt(old), prompt)
        current = copy.deepcopy(old) | {'version': 2, 'effective_view': {'view_id': 'iv_actual',
            'view_hash': 'a' * 64, 'binding_hash': 'b' * 64}}
        self.assertEqual(SB._manifest(current), current)
        self.assertNotEqual(SB._effective_hash(current), expected)
        changed = copy.deepcopy(current)
        changed['effective_view']['view_hash'] = 'c' * 64
        self.assertNotEqual(SB._effective_hash(current), SB._effective_hash(changed))
        self.assertEqual(SB.trial_system_prompt(current), prompt)
        extra = copy.deepcopy(current)
        extra['effective_view']['extra'] = True
        wrong_hash = copy.deepcopy(current)
        wrong_hash['effective_view']['view_hash'] = 'invalid'
        for broken in (extra, wrong_hash, old | {'effective_view': current['effective_view']},
                current | {'version': True}, {key: value for key, value in current.items() if key != 'effective_view'}):
            with self.assertRaises(ValueError):
                SB._manifest(broken)


if __name__ == '__main__':
    unittest.main()
