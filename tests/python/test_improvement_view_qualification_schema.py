"""Final metadata cannot adopt genuine tuning or legacy holdout reservations."""
from _paths import ROOT, SERVER  # noqa: F401

import json
import sqlite3
import time
import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
from improvement_cases import CaseStore
import test_improvement_view_sources as sources


class ViewQualificationSchemaTests(sources.SourceFixture, unittest.IsolatedAsyncioTestCase):
    def definition(self):
        with closing(self.assets.store._conn()) as connection:
            return json.loads(connection.execute('SELECT definition_json FROM improvement_experiments WHERE id=? AND brain_id=?',
                (self.comparison['experiment_id'], self.owner.brain_id)).fetchone()[0])

    def unrelated_claim(self):
        cases, value = CaseStore(self.assets), self.definition()
        with closing(self.assets.store._conn()) as connection:
            source = json.loads(connection.execute('SELECT manifest_json FROM improvement_snapshots WHERE brain_id=? LIMIT 1',
                (self.owner.brain_id,)).fetchone()[0])
        source.update(source_ref='technical:unrelated-legacy-holdout', source_version='unrelated-v1', grant_hash=value['grant_hash'])
        raw = b'Unrelated technical legacy qualification input.\n'
        snapshot = cases.put_snapshot(self.owner, source, raw, raw, event_key='unrelated-view-qual-snapshot')
        case_set = cases.put_case_set(self.owner, [{'id': 'unrelated-qual', 'family_key': 'unrelated-qual-family',
            'split': 'qualification', 'task': 'Technical legacy holdout check.', 'snapshot_ids': [snapshot['snapshot_id']],
            'answer': {'value': 'technical'}, 'evaluator_refs': []}], 171, event_key='unrelated-view-qual-cases')
        pins = {key: value[key] for key in ('base_bundle_hash', 'contract_hash', 'engine_config_hash',
            'grant_hash', 'scope_hash', 'policy_version')} | {'experiment_id': 'unrelated-legacy-qualification',
                'candidate_bundle_hash': value['base_bundle_hash'], 'case_set_hash': case_set['manifest_hash']}
        return cases.reserve_qualification(self.owner, case_set['case_set_id'], pins,
            event_key='unrelated-view-qual-reserve')

    async def test_actual_tuning_view_cannot_adopt_real_legacy_reservation(self):
        views = self.views_service()
        metadata = self.freeze(views)
        claim = self.unrelated_claim()
        row = {'comparison_id': self.comparison['id'], 'brain_id': self.owner.brain_id,
            'experiment_id': self.comparison['experiment_id'], 'reservation_id': claim['reservation_id'],
            'case_set_id': claim['case_set_id'], 'candidate_id': self.proposal['id'],
            'selection_event_key': 'unrelated-view-qual-reserve', 'reservation_event_key': 'unrelated-view-qual-reserve',
            'selection_hash': IM._hash(claim), 'binding_hash': metadata['binding_hash'], 'pins_hash': claim['pins_hash'],
            'family_hash': IM._hash(['untrusted negative link fixture']), 'created_at': time.time()}
        with self.assets.store._Tx(self.assets.store) as connection:
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'view_qualification_scope_mismatch'):
                connection.execute('INSERT INTO improvement_view_qualification_links (' + ','.join(row)
                    + ') VALUES (' + ','.join('?' for _ in row) + ')', tuple(row.values()))
            self.assertEqual(connection.execute('SELECT count(*) FROM improvement_view_qualification_links').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT status FROM improvement_qualification WHERE id=?',
                (claim['reservation_id'],)).fetchone()[0], 'reserved')

    async def test_changed_qualification_guard_refuses_new_authority_before_plaintext(self):
        with self.assets.store._Tx(self.assets.store) as connection:
            connection.execute('DROP TRIGGER improvement_view_qualification_scope')
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Changed guard cannot decrypt')), \
                self.assertRaisesRegex(IM.ConflictError, 'view_schema_changed'):
            self.freeze(self.views_service())

    async def test_earlier_metadata_prototype_stays_cold_but_cannot_resolve_current_work(self):
        views = self.views_service()
        self.freeze(views)
        history = views.read_existing(self.owner, self.comparison['id'])
        with self.assets.store._Tx(self.assets.store) as connection:
            connection.execute('DROP TABLE improvement_view_qualification_links')
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Prototype cannot decrypt')):
            self.assertEqual(views.read_existing(self.owner, self.comparison['id']), history)
            with self.assertRaisesRegex(IM.ConflictError, 'view_schema_changed'):
                views.load_current(self.owner, self.comparison['id'], 'baseline')

    async def test_raw_nine_pins_still_cannot_reserve_experiment_holdout(self):
        self.freeze(self.views_service())
        value = self.definition()
        pins = {key: value[key] for key in ('experiment_id', 'base_bundle_hash', 'contract_hash', 'case_set_hash',
            'engine_config_hash', 'grant_hash', 'scope_hash', 'policy_version')} | {
                'candidate_bundle_hash': self.comparison['arm_hash']}
        counts = self.counts()
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Raw holdout claim cannot decrypt')), \
                self.assertRaisesRegex(PermissionError, 'experiment_qualification_lineage_required'):
            CaseStore(self.assets).reserve_qualification(self.owner, value['case_set_id'], pins,
                event_key='deny-raw-view-qualification')
        self.assertEqual(self.counts(), counts)


if __name__ == '__main__':
    unittest.main()
