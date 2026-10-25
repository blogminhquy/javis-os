"""Real global case aliases cannot enter a current effective-view tuning path."""
from _paths import ROOT, SERVER  # noqa: F401

import json
import unittest
from contextlib import closing
from unittest.mock import patch

from improvement_cases import CaseStore
import test_improvement_view_sources as sources
import test_improvement_view_reservations as reservations


class ViewHoldoutTests(sources.SourceFixture, unittest.IsolatedAsyncioTestCase):
    request = reservations.ViewReservationTests.request
    load = reservations.ViewReservationTests.load
    bound = reservations.ViewReservationTests.bound
    live_request = reservations.ViewReservationTests.live_request

    def declare_alias(self, split):
        with closing(self.assets.store._conn()) as connection:
            value = json.loads(connection.execute('SELECT definition_json FROM improvement_experiments WHERE id=? AND brain_id=?',
                (self.comparison['experiment_id'], self.owner.brain_id)).fetchone()[0])
            case = json.loads(connection.execute("SELECT case_json FROM improvement_cases WHERE case_set_id=? AND brain_id=? "
                "AND split='tuning' ORDER BY id LIMIT 1", (value['case_set_id'], self.owner.brain_id)).fetchone()[0])
        # Real owner API; renamed identity/family still shares the actual source
        # fingerprint. No fabricated future final Trial, claim or report.
        return CaseStore(self.assets).put_case_set(self.owner, [{'id': 'renamed-' + split,
            'family_key': 'renamed-family-' + split, 'split': split, 'task': 'Isolated owner-declared holdout alias.',
            'snapshot_ids': case['snapshot_ids'], 'answer': {'value': 'independent owner check'}, 'evaluator_refs': []}],
            190, event_key='owner-declare-view-holdout-' + split)

    def deny_freeze_alias(self, split):
        views = self.views_service()
        counts, generation = self.counts(), self.generation()
        self.declare_alias(split)
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Holdout alias must reject before plaintext')), \
                self.assertRaisesRegex(PermissionError, 'improver_holdout_alias'):
            self.freeze(views, key='deny-view-holdout-publication-' + split)
        self.assertEqual(self.counts(), counts)
        self.assertEqual(self.generation(), generation)

    async def test_new_view_publication_rejects_global_qualification_alias_before_plaintext(self):
        self.deny_freeze_alias('qualification')

    async def test_new_view_publication_rejects_global_regression_alias_before_plaintext(self):
        self.deny_freeze_alias('regression')

    async def test_later_holdout_declaration_blocks_frozen_view_runtime_without_invalidating_cold_history(self):
        trials, metadata = self.bound()
        request = self.live_request(metadata)
        counts = self.counts()
        historical = self.host._views.read_existing(self.owner, self.comparison['id'])
        self.declare_alias('regression')
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Current alias guard is SQL only')):
            with self.assertRaisesRegex(PermissionError, 'improver_holdout_alias'):
                self.host._views.load_current(self.owner, self.comparison['id'], 'baseline')
            with self.assertRaisesRegex(PermissionError, 'improver_holdout_alias'):
                trials.reserve(self.owner, request, event_key='deny-frozen-view-holdout-runtime')
            self.assertEqual(self.host._views.read_existing(self.owner, self.comparison['id']), historical)
        self.assertEqual(self.counts(), counts)


if __name__ == '__main__':
    unittest.main()
