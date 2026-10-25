"""Owned final claim denials over real stores; no fabricated eligible selection."""
from _paths import ROOT, SERVER  # noqa: F401

import importlib
import importlib.util
import json
import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

from resonance_store import Principal
from improvement_cases import CaseStore
import test_improvement_view_sources as sources
import test_improvement_view_qualification_schema as schema_fixtures


def factory():
    if importlib.util.find_spec('improvement_view_qualification') is None:
        return None
    return getattr(importlib.import_module('improvement_view_qualification'), 'ViewQualification', None)


class ConcreteQualifierTests(unittest.TestCase):
    def test_concrete_owned_qualifier_cannot_be_replaced_by_caller_objects(self):
        cls = factory()
        self.assertTrue(callable(cls), 'The concrete owned final qualifier is absent')
        with self.assertRaisesRegex(TypeError, 'concrete_same_store_qualification_required'):
            cls(object(), object())


class ViewQualificationTests(sources.SourceFixture, unittest.IsolatedAsyncioTestCase):
    definition = schema_fixtures.ViewQualificationSchemaTests.definition
    unrelated_claim = schema_fixtures.ViewQualificationSchemaTests.unrelated_claim

    def counts_with_claims(self):
        with closing(self.assets.store._conn()) as connection:
            return self.counts() + tuple(connection.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                for table in ('improvement_qualification', 'improvement_qualification_claims', 'improvement_view_qualification_links'))

    def qualifier(self):
        cls = factory()
        self.assertTrue(callable(cls), 'The concrete owned final qualifier is absent')
        views = self.views_service()
        self.freeze(views)
        return cls(self.f.plans, views)

    async def test_real_tuning_comparison_cannot_claim_final_pool_before_private_read(self):
        subject = self.qualifier()
        counts, generation = self.counts_with_claims(), self.generation()
        with self.assets.store._Tx(self.assets.store) as connection:
            with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Tuning cannot read final authority')), \
                    self.assertRaisesRegex(PermissionError, 'view_final_comparison_required'):
                subject._reserve_in(connection, self.owner, self.comparison['id'], expected_generation=generation)
        self.assertEqual(self.counts_with_claims(), counts)

    async def test_missing_or_foreign_comparison_has_no_claim_or_plaintext_side_effect(self):
        subject = self.qualifier()
        counts, generation = self.counts_with_claims(), self.generation()
        other = Principal('owner', 'owner', self.owner.brain_id + '-ungranted')
        for principal, identifier in ((self.owner, 'missing-final-comparison'), (other, self.comparison['id'])):
            with self.assets.store._Tx(self.assets.store) as connection:
                with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('No scope may read plaintext')), \
                        self.assertRaises(PermissionError):
                    subject._reserve_in(connection, principal, identifier, expected_generation=generation)
        self.assertEqual(self.counts_with_claims(), counts)

    async def test_reservation_composition_requires_existing_exact_store_transaction(self):
        subject = self.qualifier()
        counts = self.counts_with_claims()
        with closing(self.assets.store._conn()) as connection:
            with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('No transaction cannot decrypt')), \
                    self.assertRaisesRegex(ValueError, 'case_store_transaction_required'):
                subject._reserve_in(connection, self.owner, self.comparison['id'], expected_generation=self.generation())
        with closing(sqlite3.connect(':memory:')) as foreign:
            foreign.execute('BEGIN')
            with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Foreign DB cannot decrypt')), \
                    self.assertRaisesRegex(ValueError, 'case_store_transaction_mismatch'):
                subject._reserve_in(foreign, self.owner, self.comparison['id'], expected_generation=self.generation())
        self.assertEqual(self.counts_with_claims(), counts)

    async def test_consumed_qualification_cannot_be_relabelled_as_regression_while_real_regression_remains_allowed(self):
        subject, cases = self.qualifier(), CaseStore(self.assets)
        with closing(self.assets.store._conn()) as connection:
            subject._regression_aliases(connection, self.owner.brain_id, self.definition()['case_set_id'])
        claim = self.unrelated_claim()
        with closing(self.assets.store._conn()) as connection:
            pins = json.loads(connection.execute('SELECT pins_json FROM improvement_qualification WHERE id=?',
                (claim['reservation_id'],)).fetchone()[0])
            case = json.loads(connection.execute('SELECT case_json FROM improvement_cases WHERE case_set_id=?',
                (claim['case_set_id'],)).fetchone()[0])
        consumed = cases.consume_qualification(self.owner, claim['reservation_id'], pins,
            event_key='consume-unrelated-qualification-for-regression-alias')
        self.assertEqual(consumed['status'], 'consumed')
        alias = cases.put_case_set(self.owner, [{'id': 'renamed-consumed-regression', 'family_key': 'renamed-consumed-family',
            'split': 'regression', 'task': 'Untrusted relabelled qualification input.', 'snapshot_ids': case['snapshot_ids'],
            'answer': {'value': 'technical'}, 'evaluator_refs': []}], 177, event_key='declare-consumed-qualification-regression-alias')
        with closing(self.assets.store._conn()) as connection:
            with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Regression alias checks are SQL only')), \
                    self.assertRaisesRegex(PermissionError, 'view_final_regression_qualification_alias'):
                subject._regression_aliases(connection, self.owner.brain_id, alias['case_set_id'])


if __name__ == '__main__':
    unittest.main()
