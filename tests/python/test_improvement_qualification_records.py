"""Real private M0/ledger/trial records; observer seams, no native/provider."""
from _paths import ROOT, SERVER  # noqa: F401

from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import importlib
import importlib.util
import json
import sqlite3
import unittest
from unittest.mock import patch

import improvement_store as IM
from improvement_blobs import AssetUnavailable
from resonance_store import Principal
import test_improvement_qualification_session as S
import test_improvement_trials as T


class QualificationRecordsTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('improvement_qualification_records'), 'durable domain owner missing')
        self.records = importlib.import_module('improvement_qualification_records')
        helper = S.QualificationSessionTests(); helper.setUp(); self.addCleanup(helper.doCleanups)
        self.session = helper.open(maximum_queries=1)
        session = self.session
        def private_cases(fixture):
            fixture.root, fixture.rs, fixture.assets = session.root, session.assets.store, session.assets
            fixture.cases = T.fixtures.IC.CaseStore(fixture.assets)
            fixture.owner = session.principal
            fixture.other = Principal('owner', 'owner', 'foreign-brain')
        with patch.object(T.fixtures.ImprovementCaseTests, 'setUp', private_cases):
            fixture = T.TrialStoreTests(); fixture.setUp()
        self.fixture = fixture
        fixture.request['engine_config'] = dict(session._pin)
        fixture.request['pins']['engine_config_hash'] = IM._hash(session._pin)
        # This unit tests durable records with genuine prepared historical-format
        # fixture inputs. It does not qualify baseline5 or any native pipeline.
        self.enterContext(patch('improvement_native_formats.input_version', return_value=1))
        self.row, self.token = fixture.prepared()
        self.identifier = self.row['trial_id']
        self.owner, self.trials = session.principal, fixture.trials

    def bind(self, row=None, token=None, **changes):
        row = row or self.row
        return self.session.bind_attempt(self.trials, self.owner, row['trial_id'],
            expected_generation=row['generation'], lease_token=token or self.token,
            capability_hash=changes.pop('capability_hash', 'c' * 64), **changes)

    def read(self, assets=None, **changes):
        return self.records.read_attempt(assets or self.session.assets, self.owner,
            **{'kind': 'trial', 'subject_id': self.identifier, 'attempt': 1, 'capability_hash': 'c' * 64, **changes})

    def second(self):
        f = self.fixture
        row = f.reserve('qualification-second-trial', repeat=2)
        row = self.trials.claim(self.owner, row['trial_id'], expected_generation=row['generation'])
        token = row['lease_token']
        manifest = self.trials.materialize(self.owner, row['trial_id'], expected_generation=row['generation'],
            lease_token=token, baseline_context=f.context)
        receipt = self.trials.workspace.prepare(row['trial_id'], 1, manifest)
        row = self.trials.prepared(self.owner, row['trial_id'], expected_generation=row['generation'],
            lease_token=token, receipt=receipt)
        return row, token

    def test_store_carries_readonly_expected_run_anchor_and_missing_root_cannot_downgrade(self):
        self.assertEqual(self.session.assets.qualification_anchor, self.session.run_hash)
        with self.assertRaises(AttributeError): self.session.assets.qualification_anchor = None
        with self.session.assets.store._Tx(self.session.assets.store) as connection:
            connection.execute('DROP TRIGGER improvement_events_delete')
            connection.execute("DELETE FROM improvement_events WHERE operation='native_qualification_session'")
        with self.assertRaises(AssetUnavailable):
            self.records.read_run(self.session.assets, self.owner)

    def test_real_prepared_attempt_call_binding_is_encrypted_idempotent_and_cold_readable(self):
        first = self.bind(); second = self.bind()
        self.assertEqual(first, second)
        self.assertEqual(first['run_hash'], self.session.run_hash)
        self.assertEqual(first['call_id'], self.row['attempts'][0]['call_id'])
        self.assertEqual(first['capability_hash'], 'c' * 64)
        self.assertEqual(self.read(), first)
        with closing(self.session.assets.store._conn()) as connection:
            rows = list(connection.execute("SELECT result_json FROM improvement_events WHERE operation='native_qualification_attempt'"))
        self.assertEqual(len(rows), 1)
        envelope = json.loads(rows[0][0])
        raw = self.session.assets.blobs._path(self.owner.brain_id, envelope['blob_hash']).read_text()
        self.assertTrue(raw.startswith('enc:')); self.assertNotIn(self.identifier, raw)
        self.session.close()
        archived, principal = self.session.open_forensic(self.session.root, expected_run_hash=self.session.run_hash)
        self.assertEqual(principal, self.owner)
        self.assertEqual(self.read(archived), first)
        with closing(archived.store._conn()) as connection, self.assertRaises(sqlite3.OperationalError):
            connection.execute('DELETE FROM agent_calls')
        with self.assertRaises(AssetUnavailable):
            self.session.open_forensic(self.session.root, expected_run_hash='d' * 64)
        with self.assertRaises(PermissionError): self.bind()

    def test_two_real_attempts_compete_atomically_for_one_budget_and_replay_costs_no_more(self):
        second, token = self.second()
        def contender(item):
            row, lease = item
            try: return self.bind(row, lease)
            except PermissionError as error: return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(contender, ((self.row, self.token), (second, token))))
        self.assertEqual(len([x for x in results if type(x) is dict]), 1, results)
        self.assertEqual([x for x in results if type(x) is str], ['qualification_query_budget_exhausted'])
        winner = 0 if type(results[0]) is dict else 1
        row, lease = ((self.row, self.token), (second, token))[winner]
        self.assertEqual(contender((row, lease)), results[winner])

    def test_missing_attempt_link_inside_anchored_store_never_becomes_product_domain(self):
        with self.assertRaises(AssetUnavailable): self.read()
        with self.assertRaisesRegex(PermissionError, 'non_product_execution_domain'):
            self.records.require_product_store(self.session.assets, self.owner)
        # Even a report lacking a marker has no effect on this durable fence.
        self.assertNotIn('execution_domain', {'verdict': 'pass'})

    def test_foreign_owner_pin_capability_and_ledger_binding_refuse(self):
        with self.assertRaises(PermissionError):
            self.session.bind_attempt(self.trials, Principal('owner', 'owner', 'foreign'), self.identifier,
                expected_generation=self.row['generation'], lease_token=self.token, capability_hash='c' * 64)
        with self.session.assets.store._Tx(self.session.assets.store) as connection:
            connection.execute("UPDATE agent_calls SET mirror_ref='foreign' WHERE id=?", (self.row['attempts'][0]['call_id'],))
        with self.assertRaises(IM.ConflictError): self.bind()
        with self.session.assets.store._Tx(self.session.assets.store) as connection:
            connection.execute('UPDATE agent_calls SET mirror_ref=? WHERE id=?',
                ('improvement_trial:' + self.identifier, self.row['attempts'][0]['call_id']))
        self.bind()
        with self.assertRaises(AssetUnavailable): self.read(capability_hash='d' * 64)
        with self.assertRaises(IM.ConflictError): self.bind(capability_hash='d' * 64)

    def test_live_bind_checks_lease_expiry_engine_state_and_session_expiry(self):
        with self.assertRaises(IM.ConflictError): self.bind(token='foreign-lease')
        with patch.object(importlib.import_module('improvement_qualification_session').time,
                'time', return_value=self.session.scope()['deadline_at']):
            with self.assertRaisesRegex(PermissionError, 'expired'): self.bind()
        self.bind()
        self.trials.start_engine(self.owner, self.identifier, expected_generation=self.row['generation'], lease_token=self.token)
        with self.assertRaises(IM.ConflictError): self.bind()
        self.assertEqual(self.read()['run_hash'], self.session.run_hash, 'cold history ignores live lease/status')

    def test_cold_read_authenticates_actual_call_and_encrypted_link_after_workspace_cleanup(self):
        self.bind()
        self.trials.workspace.cleanup(self.identifier, 1)
        self.assertEqual(self.read()['subject_id'], self.identifier)
        with self.session.assets.store._Tx(self.session.assets.store) as connection:
            connection.execute("UPDATE agent_calls SET reason_ref='foreign-call' WHERE id=?", (self.row['attempts'][0]['call_id'],))
        with self.assertRaises(IM.ConflictError): self.read()

    def test_unanchored_reopen_or_corrupt_link_cannot_read_engineering_as_historical_product(self):
        self.bind()
        ordinary = IM.ImprovementStore(self.session.assets.store, self.session.assets.blobs)
        with self.assertRaisesRegex(PermissionError, 'anchor_required'): self.read(ordinary)
        with closing(self.session.assets.store._conn()) as connection:
            envelope = json.loads(connection.execute("SELECT result_json FROM improvement_events WHERE operation='native_qualification_attempt'").fetchone()[0])
        self.session.assets.blobs._path(self.owner.brain_id, envelope['blob_hash']).unlink()
        with self.assertRaises(AssetUnavailable): self.read()

    def test_actual_default_trial_product_result_read_and_publication_refuse_durable_domain_before_data(self):
        from improvement_trial_results import TrialResults
        from improvement_trial_products import TrialProducts
        results = TrialResults(self.trials)
        with closing(self.session.assets.store._conn()) as connection:
            row = self.trials._row(connection, self.owner.brain_id, self.identifier)
            actions = {
                'cold_read': lambda: results.read(self.owner, self.identifier, 1),
                'publication': lambda: results.finish(self.owner, self.identifier, expected_generation=self.row['generation'],
                    lease_token=self.token, capability_hash='c' * 64, live_guard=lambda: {}, checker_registry={}),
                'products': lambda: TrialProducts(self.trials)._products(connection, row, principal=self.owner, capability_hash='c' * 64)}
            for name, action in actions.items():
                with self.subTest(path=name), self.assertRaisesRegex(PermissionError, 'non_product_execution_domain'):
                    action()

    def test_valid_digest_materialization_drift_is_refused_before_binding(self):
        with self.session.assets.store._Tx(self.session.assets.store) as connection:
            connection.execute('UPDATE improvement_trial_attempts SET materialization_hash=? WHERE trial_id=?',
                ('e' * 64, self.identifier))
        with self.assertRaises(IM.ConflictError): self.bind()

    def test_slow_exact_replay_cannot_cross_run_deadline_or_closed_session(self):
        self.bind(); original = self.session.assets.blobs.read
        for change in ('deadline', 'close'):
            with self.subTest(change=change):
                clock = [self.session.scope()['created_at'] + 1]
                def delayed(*args):
                    raw = original(*args)
                    if b'"call_binding"' in raw:
                        if change == 'close': self.session.close()
                        else: clock[0] = self.session.scope()['deadline_at']
                    return raw
                with patch.object(importlib.import_module('improvement_qualification_session').time, 'time', side_effect=lambda: clock[0]), \
                        patch.object(self.session.assets.blobs, 'read', side_effect=delayed):
                    with self.assertRaises(PermissionError): self.bind()


if __name__ == '__main__': unittest.main()
