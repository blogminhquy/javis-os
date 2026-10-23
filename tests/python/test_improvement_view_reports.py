"""Pure untrusted projection and genuine pending v4 report ownership; no fake results."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
from improvement_comparison_results import ComparisonResults, project_result
import test_improvement_comparison_results as arithmetic
import test_improvement_view_sources as sources
import test_improvement_view_reservations as reservations


class ViewProjectionTests(unittest.TestCase):
    def fixture(self):
        value, contract, request, report = arithmetic.ResultProjectionTests().fixture()
        request.update(version=4, view={'view_id': 'untrusted-example-view', 'view_hash': '4' * 64, 'binding_hash': '5' * 64})
        report.update(version=4, request_hash=IM._hash(request), effective_view=copy.deepcopy(request['view']))
        for row in report['mandatory']:
            if row['id'] in ('actual_reasoning', 'asset_observed_use'):
                row['verdict'] = 'unknown'
        return value, contract, request, report

    def project(self, data):
        return project_result(*data[:3], 'trial-1', 1, data[3])

    def test_explicit_v4_projection_preserves_both_unknowns_and_all_eighteen_native_checks(self):
        data = self.fixture()
        self.assertEqual(len(data[3]['mandatory']), 18)
        self.assertEqual(self.project(data)['integrity'], 'unknown')
        data[3]['mandatory'] = [row for row in data[3]['mandatory'] if row['id'] != 'actual_reasoning']
        self.assertEqual(self.project(data)['integrity'], 'unknown')

    def test_view_identity_and_legacy_hash_substitution_are_never_accepted(self):
        for key in ('view_id', 'view_hash', 'binding_hash'):
            data = self.fixture()
            data[3]['effective_view'][key] = 'foreign-view' if key == 'view_id' else '0' * 64
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.project(data)
        data = self.fixture()
        legacy = {key: value for key, value in data[2].items() if key != 'view'} | {'version': 2}
        data[3]['request_hash'] = IM._hash(legacy)
        with self.assertRaises(ValueError):
            self.project(data)

    def test_missing_view_wrong_result_version_and_duplicate_native_id_reject(self):
        for change in (lambda r: r.pop('effective_view'), lambda r: r.update(version=2),
                lambda r: r['mandatory'].append(copy.deepcopy(r['mandatory'][0]))):
            data = self.fixture()
            change(data[3])
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.project(data)


class ViewReportStoreTests(sources.SourceFixture, unittest.IsolatedAsyncioTestCase):
    request = reservations.ViewReservationTests.request
    load = reservations.ViewReservationTests.load
    bound = reservations.ViewReservationTests.bound
    live_request = reservations.ViewReservationTests.live_request

    async def test_actual_pending_view_trial_is_captured_without_fabricating_a_result(self):
        trials, metadata = self.bound()
        request = self.live_request(metadata)
        reserved = trials.reserve(self.owner, request, event_key='view-report-actual-pending-trial')
        reports = ComparisonResults(self.f.plans)
        with closing(self.assets.store._conn()) as connection:
            value = reports._metadata(connection, self.owner.brain_id, self.comparison['id'])
            captured = reports._snapshot(connection, self.owner.brain_id, value)
            self.assertIsNotNone(captured[request['lineage']['cell_position']], 'Report snapshot omitted actual v4 ownership')
            self.assertEqual(captured[request['lineage']['cell_position']]['trial']['id'], reserved['trial_id'])
            self.assertEqual(connection.execute('SELECT count(*) FROM improvement_trial_results WHERE trial_id=?',
                (reserved['trial_id'],)).fetchone()[0], 0)
        saved = reports.create(self.owner, self.comparison['id'], expected_generation=self.generation(), event_key='view-report-missing-real-results')
        report = reports.read(self.owner, saved['report_id'])
        self.assertEqual(report['version'], 1)
        self.assertFalse(report['summary']['complete'])
        self.assertEqual(report['summary']['integrity']['missing'], self.comparison['cell_count'])

    async def test_current_report_requires_current_meaning_but_history_and_replay_stay_cold(self):
        self.bound()
        reports = ComparisonResults(self.f.plans)
        generation = self.generation()
        key = 'view-report-before-owner-veto'
        saved = reports.create(self.owner, self.comparison['id'], expected_generation=generation, event_key=key)
        evidence = self.semantic_subject.current_evidence(self.owner, self.proposal['id'])
        self.semantic_subject.arbitrate(self.owner, self.proposal['id'], evidence['receipt_id'], verdict='fail',
            reason='Synthetic owner veto must fence new report creation; no real business decision.',
            expected_binding_hash=evidence['binding_hash'], expected_generation=self.generation(), event_key='view-report-synthetic-owner-veto')
        current = self.generation()
        with self.assertRaises((PermissionError, IM.ConflictError)):
            reports.create(self.owner, self.comparison['id'], expected_generation=current, event_key='view-report-deny-after-owner-veto')
        self.assertEqual(self.generation(), current)
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Event replay cannot decrypt')):
            self.assertEqual(reports.create(self.owner, self.comparison['id'], expected_generation=generation, event_key=key), saved)
        with patch.object(self.host, '_snapshot_observe', side_effect=AssertionError('History cannot observe sources')):
            self.assertFalse(ComparisonResults.from_existing(self.assets).read(self.owner, saved['report_id'])['summary']['complete'])

    async def test_pre_view_missing_result_report_keeps_exact_history_on_metadata_only_prototype(self):
        reports = ComparisonResults(self.f.plans)
        saved = reports.create(self.owner, self.comparison['id'], expected_generation=self.generation(),
            event_key='view-report-original-legacy-empty-history')
        original = self.assets.blobs.read(self.owner.brain_id, saved['report_hash'])
        self.freeze(self.views_service())
        # Reproduce the actual earlier unshipped schema7 shape: view metadata
        # existed before Task3 added runtime links. No v4 Trial/result is invented.
        with self.assets.store._Tx(self.assets.store) as connection:
            connection.execute('DROP TABLE improvement_view_trial_links')
        with patch.object(self.host, '_snapshot_observe', side_effect=AssertionError('Historical prototype cannot observe sources')):
            report = ComparisonResults.from_existing(self.assets).read(self.owner, saved['report_id'])
        self.assertEqual(IM._json(report).encode(), original)
        self.assertEqual(IM._hash(report), saved['report_hash'])
        self.assertFalse(report['summary']['complete'])


if __name__ == '__main__':
    unittest.main()
