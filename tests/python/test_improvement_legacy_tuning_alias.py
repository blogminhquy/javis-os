"""Legacy B baseline cannot bypass global holdout aliases after final consumption exists."""
from _paths import ROOT, SERVER  # noqa: F401
import copy
import json
import unittest
from contextlib import closing
from unittest.mock import patch
import improvement_store as IM
from improvement_cases import CaseStore
from improvement_experiment_lineage import current_fences
from improvement_experiment_admission import ExperimentAdmission
from improvement_claude import ClaudeTrialAdapter
from improvement_trials import TrialStore
import test_improvement_experiment_lineage as fixtures

class LegacyTuningAliasTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.LineageTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.assets, self.owner = self.f.assets, self.f.owner
        self.trials = TrialStore(self.assets)
        self.request = copy.deepcopy(self.f.request)
        self.history_request = copy.deepcopy(self.request)
        self.history = self.trials.reserve(self.owner, self.history_request, event_key='legacy-before-holdout-declaration')
        self.proof = self.f.load()
        with closing(self.assets.store._conn()) as connection:
            case = json.loads(connection.execute('SELECT case_json FROM improvement_cases WHERE case_set_id=? AND id=? AND brain_id=?',
                (self.request['case_set_id'], self.request['case_id'], self.owner.brain_id)).fetchone()[0])
        CaseStore(self.assets).put_case_set(self.owner, [{'id': 'renamed-legacy-holdout', 'family_key': 'renamed-legacy-source-family',
            'split': 'qualification', 'task': 'Technical holdout alias.', 'snapshot_ids': case['snapshot_ids'],
            'answer': {'value': 'technical independent check'}, 'evaluator_refs': []}], 187, event_key='declare-legacy-tuning-holdout')
    def counts(self):
        with closing(self.assets.store._conn()) as connection:
            return tuple(connection.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                for table in ('improvement_trials', 'agent_calls', 'improvement_experiment_trial_links'))
    def test_lower_v2_reservation_rejects_alias_before_plaintext_but_replay_stays_cold(self):
        before = self.counts()
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Legacy alias cannot decrypt')):
            with self.assertRaisesRegex(PermissionError, 'improver_holdout_alias'):
                self.trials.reserve(self.owner, self.request, event_key='deny-legacy-alias-new-reserve')
            self.assertEqual(self.trials.reserve(self.owner, self.history_request, event_key='legacy-before-holdout-declaration'), self.history)
            self.assertEqual(self.trials.get(self.owner, self.history['trial_id']), self.history)
        self.assertEqual(self.counts(), before)
    def test_owned_legacy_admission_rejects_before_native_preflight_or_plaintext(self):
        before = self.counts()
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Legacy admission cannot decrypt')), \
                patch.object(ClaudeTrialAdapter, 'verify', side_effect=AssertionError('No native preflight for contaminated tuning')), \
                self.assertRaisesRegex(PermissionError, 'improver_holdout_alias'):
            ExperimentAdmission(self.f.h.plans()).admit(self.owner, self.request['pins']['experiment_id'],
                self.f.comparison['id'], self.request['lineage']['cell_position'],
                expected_generation=self.f.frozen['generation'], event_key='deny-legacy-alias-owned-admission')
        self.assertEqual(self.counts(), before)
    def test_final_sql_fence_rejects_a_later_declaration_without_reading_sources(self):
        with closing(self.assets.store._conn()) as connection:
            with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('SQL fence cannot decrypt')), \
                    self.assertRaisesRegex(PermissionError, 'improver_holdout_alias'):
                current_fences(connection, self.owner.brain_id, self.proof)
if __name__ == '__main__':
    unittest.main()
