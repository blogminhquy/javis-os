"""Genuine v4 reservations in the existing ledger, without native query readiness."""
from _paths import ROOT, SERVER  # noqa: F401

import json
import time
import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
from improvement_trials import TrialStore
from improvement_trial_views import read_trial
import test_improvement_view_sources as sources
import test_improvement_view_lineage as lineage_fixtures


class ViewReservationTests(sources.SourceFixture, unittest.IsolatedAsyncioTestCase):
    request = lineage_fixtures.ViewLineageTests.request
    load = lineage_fixtures.ViewLineageTests.load

    def bound(self):
        subject = self.views_service()
        metadata = self.freeze(subject)
        trials = self.f.plans.admission.trials
        trials.bind_views(subject)
        self.host.bind_views(subject)
        return trials, metadata

    def live_request(self, metadata, position=0):
        return self.request(metadata, position) | {'deadline_at': time.time() + 120}

    async def test_actual_v4_pair_reserves_existing_calls_links_and_cold_replay(self):
        trials, metadata = self.bound()
        before = self.counts()[-1]
        saved = []
        for position in (0, 1):
            request = self.live_request(metadata, position)
            key = 'view-reserve-real-cell-' + str(position)
            reserved = trials.reserve(self.owner, request, event_key=key)
            saved.append((request, key, reserved))
            self.assertEqual(reserved['request'], request)
            self.assertEqual(trials.reserve(self.owner, request, event_key=key), reserved)
            self.assertEqual(self.load(request, require_link=True, trial_id=reserved['trial_id'])['cell']['variant'], request['variant'])
            with closing(self.assets.store._conn()) as connection:
                call = connection.execute('SELECT c.* FROM agent_calls c JOIN improvement_trial_attempts a ON a.call_id=c.id '
                    'WHERE a.trial_id=? AND a.brain_id=?', (reserved['trial_id'], self.owner.brain_id)).fetchone()
            self.assertEqual(call['purpose'], 'improve_probe')
            self.assertIsNone(call['engine_at'])
            with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Cold metadata cannot decrypt')):
                self.assertEqual(read_trial(self.assets, self.owner, reserved['trial_id'])['effective_view'], request['view'])
        with closing(self.assets.store._conn()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM improvement_view_trial_links').fetchone()[0], 2)
            self.assertEqual(connection.execute('SELECT count(*) FROM improvement_experiment_trial_links').fetchone()[0], 0)
        self.assertEqual(self.counts()[-1], before + 2)
        self.host.revoke(self.owner, self.comparison['experiment_id'], expected_generation=1, event_key='view-reserve-pair-revoke')
        self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='view-reserve-pair-policy-off')
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Historical replay cannot decrypt')):
            for request, key, reserved in saved:
                self.assertEqual(trials.reserve(self.owner, request, event_key=key), reserved)
                self.assertEqual(read_trial(self.assets, self.owner, reserved['trial_id'])['effective_view'], request['view'])

    async def test_unbound_lower_store_cannot_reserve_view_work_before_any_plaintext(self):
        metadata = self.freeze(self.views_service())
        request, counts = self.live_request(metadata), self.counts()
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Missing concrete resolver cannot decrypt')), \
                self.assertRaisesRegex(PermissionError, 'view_resolver_unavailable'):
            TrialStore(self.assets).reserve(self.owner, request, event_key='deny-unbound-view-reservation')
        self.assertEqual(self.counts(), counts)

    async def test_protected_source_edit_after_real_call_reservation_rolls_back_all_new_ownership(self):
        trials, metadata = self.bound()
        request, counts = self.live_request(metadata), self.counts()
        reserve = trials.ledger.reserve

        def drift(*args, **kwargs):
            result = reserve(*args, **kwargs)
            self.f.f.f.skill.write_bytes(self.f.f.f.skill.read_bytes() + b'\nUnreviewed owner edit during reservation.\n')
            return result

        with patch.object(trials.ledger, 'reserve', side_effect=drift), self.assertRaises((IM.ConflictError, PermissionError)):
            trials.reserve(self.owner, request, event_key='deny-view-drift-during-ledger-reserve')
        self.assertEqual(self.counts(), counts)
        with closing(self.assets.store._conn()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM improvement_view_trial_links').fetchone()[0], 0)

    async def test_view_materialization_rejects_wrong_context_before_plaintext(self):
        trials, metadata = self.bound()
        request = self.live_request(metadata)
        reserved = trials.reserve(self.owner, request, event_key='view-reserve-materialization-closed')
        claimed = trials.claim(self.owner, reserved['trial_id'], expected_generation=reserved['generation'])
        context = self.host.context_loader(self.owner, request)
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Wrong context cannot decrypt')), \
                self.assertRaisesRegex(IM.ConflictError, 'trial_context_drift'):
            trials.materialize(self.owner, reserved['trial_id'], expected_generation=claimed['generation'],
                lease_token=claimed['lease_token'], baseline_context=context | {'content': 'Wrong context'})
        with closing(self.assets.store._conn()) as connection:
            attempt = connection.execute('SELECT * FROM improvement_trial_attempts WHERE trial_id=?', (reserved['trial_id'],)).fetchone()
        self.assertIsNone(attempt['engine_at'])
        self.assertIsNone(attempt['workspace_json'])

    async def test_wrong_view_descriptor_denies_before_plaintext_or_call(self):
        trials, metadata = self.bound()
        request, counts = self.live_request(metadata), self.counts()
        request['view']['view_hash'] = '0' * 64
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Wrong descriptor cannot decrypt')), \
                self.assertRaisesRegex(IM.ConflictError, 'comparison_view_request_changed'):
            trials.reserve(self.owner, request, event_key='deny-wrong-descriptor-before-private-read')
        self.assertEqual(self.counts(), counts)

    async def test_source_edit_after_actual_history_blob_proof_denies_before_reservation(self):
        import improvement_view_lineage as lineage
        trials, metadata = self.bound()
        request, counts = self.live_request(metadata), self.counts()
        read = lineage.load_view_lineage

        def drift(*args, **kwargs):
            result = read(*args, **kwargs)
            self.f.f.f.skill.write_bytes(self.f.f.f.skill.read_bytes() + b'\nOwner edit after actual history read.\n')
            return result

        with patch.object(lineage, 'load_view_lineage', side_effect=drift), self.assertRaises((IM.ConflictError, PermissionError)):
            trials.reserve(self.owner, request, event_key='deny-view-edit-after-history-proof')
        self.assertEqual(self.counts(), counts)


class NativeFootprintTests(unittest.TestCase):
    def test_current_310_registration_matches_exact_native_evidence_and_sources(self):
        import hashlib
        from improvement_claude import PROFILE_SOURCES, PROFILE_VERSION, profile_hash
        from improvement_native_qualifications import profile_qualification
        raw = (ROOT / 'docs/superpowers/evidence/2026-10-26-m8-native-qualification-cli310.json').read_bytes()
        evidence = json.loads(raw)
        pin = {key: evidence[key] for key in ('cli_version', 'cli_hash', 'sdk_version', 'profile_version', 'profile_hash')}
        self.assertEqual(pin['profile_hash'], profile_hash())
        self.assertEqual(pin['profile_version'], PROFILE_VERSION)
        self.assertEqual(profile_qualification(pin, 'win32'), hashlib.sha256(raw).hexdigest())
        self.assertEqual(set(evidence['source_hashes']), set(PROFILE_SOURCES))
        self.assertEqual(len(evidence['source_hashes']), len(PROFILE_SOURCES))
        for name, digest in evidence['source_hashes'].items():
            self.assertEqual(hashlib.sha256((SERVER / name).read_bytes()).hexdigest(), digest, name)
        for key in pin:
            self.assertIsNone(profile_qualification(pin | {key: 'unqualified'}, 'win32'), key)
        self.assertIsNone(profile_qualification(pin, 'linux'))

    def test_prior_preparation_309_qualification_remains_exact_historical_evidence(self):
        import hashlib
        from improvement_claude import profile_hash
        from improvement_native_qualifications import profile_qualification
        raw = (ROOT / 'docs/superpowers/evidence/2026-10-24-m2d1-native-qualification-preparation-heartbeat.json').read_bytes()
        evidence = json.loads(raw)
        pin = {key: evidence[key] for key in ('cli_version', 'cli_hash', 'sdk_version', 'profile_version', 'profile_hash')}
        self.assertEqual(profile_qualification(pin, 'win32'), hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(pin['profile_hash'], profile_hash())
        self.assertIsNone(profile_qualification(pin | {'profile_hash': '0' * 64}, 'win32'))

    def test_prior_m2_310_qualification_remains_exact_historical_evidence(self):
        import hashlib
        from improvement_claude import profile_hash
        from improvement_native_qualifications import profile_qualification
        raw = (ROOT / 'docs/superpowers/evidence/2026-10-25-m2-native-qualification-cli310.json').read_bytes()
        evidence = json.loads(raw)
        pin = {key: evidence[key] for key in ('cli_version', 'cli_hash', 'sdk_version', 'profile_version', 'profile_hash')}
        self.assertEqual(profile_qualification(pin, 'win32'), hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(pin['profile_hash'], profile_hash())
        self.assertIsNone(profile_qualification(pin | {'profile_hash': '0' * 64}, 'win32'))

    def test_prior_m7_310_qualification_remains_exact_historical_evidence(self):
        import hashlib
        from improvement_claude import profile_hash
        from improvement_native_qualifications import profile_qualification
        raw = (ROOT / 'docs/superpowers/evidence/2026-10-26-m7-native-qualification-cli310.json').read_bytes()
        evidence = json.loads(raw)
        pin = {key: evidence[key] for key in ('cli_version', 'cli_hash', 'sdk_version', 'profile_version', 'profile_hash')}
        self.assertEqual(profile_qualification(pin, 'win32'), hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(pin['profile_hash'], profile_hash())
        self.assertIsNone(profile_qualification(pin | {'profile_hash': '0' * 64}, 'win32'))

    def test_prior_m6_310_qualification_remains_exact_historical_evidence(self):
        import hashlib
        from improvement_claude import profile_hash
        from improvement_native_qualifications import profile_qualification
        raw = (ROOT / 'docs/superpowers/evidence/2026-10-26-m6-native-qualification-cli310.json').read_bytes()
        evidence = json.loads(raw)
        pin = {key: evidence[key] for key in ('cli_version', 'cli_hash', 'sdk_version', 'profile_version', 'profile_hash')}
        self.assertEqual(profile_qualification(pin, 'win32'), hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(pin['profile_hash'], profile_hash())
        self.assertIsNone(profile_qualification(pin | {'profile_hash': '0' * 64}, 'win32'))

    def test_prior_m5_310_qualification_remains_exact_historical_evidence(self):
        import hashlib
        from improvement_claude import profile_hash
        from improvement_native_qualifications import profile_qualification
        raw = (ROOT / 'docs/superpowers/evidence/2026-10-25-m5-native-qualification-cli310.json').read_bytes()
        evidence = json.loads(raw)
        pin = {key: evidence[key] for key in ('cli_version', 'cli_hash', 'sdk_version', 'profile_version', 'profile_hash')}
        self.assertEqual(profile_qualification(pin, 'win32'), hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(pin['profile_hash'], profile_hash())
        self.assertIsNone(profile_qualification(pin | {'profile_hash': '0' * 64}, 'win32'))

    def test_prior_m4_310_qualification_remains_exact_historical_evidence(self):
        import hashlib
        from improvement_claude import profile_hash
        from improvement_native_qualifications import profile_qualification
        raw = (ROOT / 'docs/superpowers/evidence/2026-10-25-m4-native-qualification-cli310.json').read_bytes()
        evidence = json.loads(raw)
        pin = {key: evidence[key] for key in ('cli_version', 'cli_hash', 'sdk_version', 'profile_version', 'profile_hash')}
        self.assertEqual(profile_qualification(pin, 'win32'), hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(pin['profile_hash'], profile_hash())
        self.assertIsNone(profile_qualification(pin | {'profile_hash': '0' * 64}, 'win32'))

    def test_prior_m3_310_qualification_remains_exact_historical_evidence(self):
        import hashlib
        from improvement_claude import profile_hash
        from improvement_native_qualifications import profile_qualification
        raw = (ROOT / 'docs/superpowers/evidence/2026-10-25-m3-native-qualification-cli310.json').read_bytes()
        evidence = json.loads(raw)
        pin = {key: evidence[key] for key in ('cli_version', 'cli_hash', 'sdk_version', 'profile_version', 'profile_hash')}
        self.assertEqual(profile_qualification(pin, 'win32'), hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(pin['profile_hash'], profile_hash())
        self.assertIsNone(profile_qualification(pin | {'profile_hash': '0' * 64}, 'win32'))

    def test_prior_skill_reads_309_qualification_remains_exact_historical_evidence(self):
        import hashlib
        from improvement_claude import profile_hash
        from improvement_native_qualifications import profile_qualification
        raw = (ROOT / 'docs/superpowers/evidence/2026-10-24-m2d1-native-qualification-skill-reads.json').read_bytes()
        evidence = json.loads(raw)
        pin = {key: evidence[key] for key in ('cli_version', 'cli_hash', 'sdk_version', 'profile_version', 'profile_hash')}
        self.assertEqual(profile_qualification(pin, 'win32'), hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(pin['profile_hash'], profile_hash())
        self.assertIsNone(profile_qualification(pin | {'profile_hash': '0' * 64}, 'win32'))

    def test_prior_observation_309_qualification_remains_exact_historical_evidence(self):
        import hashlib
        from improvement_claude import profile_hash
        from improvement_native_qualifications import profile_qualification
        raw = (ROOT / 'docs/superpowers/evidence/2026-10-24-m2d1-native-qualification-observation.json').read_bytes()
        evidence = json.loads(raw)
        pin = {key: evidence[key] for key in ('cli_version', 'cli_hash', 'sdk_version', 'profile_version', 'profile_hash')}
        self.assertEqual(profile_qualification(pin, 'win32'), hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(pin['profile_hash'], profile_hash())
        self.assertIsNone(profile_qualification(pin | {'profile_hash': '0' * 64}, 'win32'))

    def test_prior_format_309_qualification_remains_exact_historical_evidence(self):
        import hashlib
        from improvement_claude import profile_hash
        from improvement_native_qualifications import profile_qualification
        raw = (ROOT / 'docs/superpowers/evidence/2026-10-24-m2d1-native-qualification-format.json').read_bytes()
        evidence = json.loads(raw)
        pin = {key: evidence[key] for key in ('cli_version', 'cli_hash', 'sdk_version', 'profile_version', 'profile_hash')}
        self.assertEqual(profile_qualification(pin, 'win32'), hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(pin['profile_hash'], profile_hash())
        self.assertIsNone(profile_qualification(pin | {'profile_hash': '0' * 64}, 'win32'))

    def test_prior_309_qualification_remains_exact_historical_evidence(self):
        import hashlib
        from improvement_claude import profile_hash
        from improvement_native_qualifications import profile_qualification
        raw = (ROOT / 'docs/superpowers/evidence/2026-10-23-m2d1-native-qualification-final.json').read_bytes()
        evidence = json.loads(raw)
        pin = {key: evidence[key] for key in ('cli_version', 'cli_hash', 'sdk_version', 'profile_version', 'profile_hash')}
        self.assertEqual(profile_qualification(pin, 'win32'), hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(pin['profile_hash'], profile_hash())
        self.assertIsNone(profile_qualification(pin | {'profile_hash': '0' * 64}, 'win32'))

    def test_prior_outcome_309_qualification_remains_exact_historical_evidence(self):
        import hashlib
        from improvement_claude import profile_hash
        from improvement_native_qualifications import profile_qualification
        raw = (ROOT / 'docs/superpowers/evidence/2026-10-23-m2d1-native-qualification-outcome.json').read_bytes()
        evidence = json.loads(raw)
        pin = {key: evidence[key] for key in ('cli_version', 'cli_hash', 'sdk_version', 'profile_version', 'profile_hash')}
        self.assertEqual(profile_qualification(pin, 'win32'), hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(pin['profile_hash'], profile_hash())
        self.assertIsNone(profile_qualification(pin | {'profile_hash': '0' * 64}, 'win32'))

    def test_old_308_registration_does_not_qualify_reachable_v4(self):
        from improvement_claude import PROFILE_SOURCES, PROFILE_VERSION, profile_hash
        from improvement_native_qualifications import profile_qualification
        pin = {'cli_version': '2.1.308', 'cli_hash': 'c9796ba22a9221586b36371b36f5b66198d66eb4badf6a4cf4a5f7b07becea53',
            'sdk_version': '0.2.116', 'profile_version': PROFILE_VERSION,
            'profile_hash': '9dcf718470e70957d07454bb8b50fbde79575a3b23d8c06e24cc9b749051116b'}
        self.assertIsNotNone(profile_qualification(pin, 'win32'))
        self.assertNotEqual(profile_hash(), pin['profile_hash'])
        self.assertIsNone(profile_qualification(pin | {'profile_hash': profile_hash()}, 'win32'))
        self.assertTrue({'improvement_trials.py', 'improvement_trial_host.py', 'improvement_views.py',
            'improvement_view_sources.py', 'improvement_view_history.py', 'improvement_view_lineage.py',
            'improvement_view_trial_protocol.py', 'improvement_view_protocol.py',
            'improvement_comparison_schedule.py', 'improvement_view_admission.py',
            'improvement_view_materialization.py'} <= set(PROFILE_SOURCES))


if __name__ == '__main__':
    unittest.main()
