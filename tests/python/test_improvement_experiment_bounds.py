"""Full-size structural SQL scopes; these rows prove no execution/lineage claims.

Real small-scope lineage/call/workspace integration is tested separately. This
fixture isolates cardinality, bounded UNION queries, and separate class limits
without running 18000 models or manufacturing any production Trial evidence.
"""
from _paths import ROOT, SERVER  # noqa: F401

import sqlite3
import unittest

import improvement_store as IM
from improvement_execution_limits import (MAX_COMPARISON_TRIALS, MAX_PREPARATION_TRIALS,
    MAX_TRIALS, MAX_TRIAL_ATTEMPTS, MAX_ROLE_OPERATIONS)
from improvement_experiment_service import ExperimentService


class ExperimentBoundsTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        self.addCleanup(self.connection.close)
        self.connection.executescript('''
            CREATE TABLE improvement_schema(id INTEGER PRIMARY KEY,version INTEGER);
            INSERT INTO improvement_schema VALUES(1,6);
            CREATE TABLE improvement_trials(id TEXT,brain_id TEXT,status TEXT,generation INTEGER,attempt INTEGER,request_hash TEXT);
            CREATE TABLE improvement_experiment_trial_links(trial_id TEXT,brain_id TEXT,experiment_id TEXT,request_hash TEXT,cell_position INTEGER,comparison_id TEXT);
            CREATE TABLE improvement_preparation_trial_links(trial_id TEXT,brain_id TEXT,experiment_id TEXT,request_hash TEXT,cell_position INTEGER,preparation_id TEXT);
            CREATE TABLE improvement_trial_attempts(trial_id TEXT,brain_id TEXT,attempt INTEGER,status TEXT,call_id INTEGER,engine_at REAL);
            CREATE TABLE agent_calls(id INTEGER,status TEXT,engine_at REAL,brain_id TEXT,purpose TEXT,reason_ref TEXT,mirror_ref TEXT,attempt INTEGER,context_ref TEXT);
            CREATE TABLE improvement_operations(id TEXT,brain_id TEXT,experiment_id TEXT);
            CREATE TABLE improvement_operation_attempts(operation_id TEXT,brain_id TEXT,attempt INTEGER);
        ''')

    def load(self, comparison=MAX_COMPARISON_TRIALS, preparation=MAX_PREPARATION_TRIALS):
        count = comparison + preparation
        trials = [(f'trial_{i}', 'brain', 'cancelled', 2, 2, 'a' * 64) for i in range(count)]
        self.connection.executemany('INSERT INTO improvement_trials VALUES(?,?,?,?,?,?)', trials)
        for table, start, stop, label in (
                ('improvement_experiment_trial_links', 0, comparison, 'comparison'),
                ('improvement_preparation_trial_links', comparison, count, 'preparation')):
            self.connection.executemany('INSERT INTO ' + table + ' VALUES(?,?,?,?,?,?)',
                [(f'trial_{i}', 'brain', 'experiment', 'a' * 64, i - start, label) for i in range(start, stop)])
        self.connection.executemany('INSERT INTO improvement_trial_attempts VALUES(?,?,?,?,?,?)',
            [(f'trial_{i}', 'brain', attempt, 'cancelled', i * 2 + attempt, None) for i in range(count) for attempt in (1, 2)])
        self.connection.executemany('INSERT INTO agent_calls VALUES(?,?,?,?,?,?,?,?,?)',
            [(i * 2 + attempt, 'refunded', None, 'brain', 'improve_probe',
              f'improvement_trial:trial_{i}:attempt:{attempt}', f'improvement_trial:trial_{i}', attempt, 'improvement:experiment')
             for i in range(count) for attempt in (1, 2)])

    def snapshot(self):
        # The SQL-only branch needs no execution service and must never probe one.
        return ExperimentService._snapshot(None, self.connection, 'brain', 'experiment')

    def test_exact_full_scope_includes_18000_distinct_trials_and_all_36000_attempts(self):
        self.load()
        result = self.snapshot()
        self.assertEqual(len(result[0]), MAX_TRIALS)
        self.assertEqual(len({row['trial_id'] for row in result[0]}), MAX_TRIALS)
        self.assertEqual(len(result[1]), MAX_TRIAL_ATTEMPTS)
        self.assertEqual(sum('preparation_id' in row for row in result[0]), MAX_PREPARATION_TRIALS)
        self.assertEqual(result[2:], ([], []))

    def test_separate_scope_limits_cannot_trade_one_comparison_cell_for_preparation(self):
        self.load(comparison=MAX_COMPARISON_TRIALS - 1, preparation=MAX_PREPARATION_TRIALS + 1)
        with self.assertRaises(IM.ConflictError):
            self.snapshot()

    def test_comparison_overflow_rejects_even_when_total_is_within_combined_limit(self):
        self.load(comparison=MAX_COMPARISON_TRIALS + 1, preparation=MAX_PREPARATION_TRIALS - 1)
        with self.assertRaises(IM.ConflictError):
            self.snapshot()

    def test_extra_attempt_and_extra_role_rows_reject_instead_of_truncating(self):
        self.load()
        self.connection.execute("INSERT INTO improvement_trial_attempts VALUES('trial_0','brain',3,'cancelled',1,NULL)")
        with self.assertRaises(IM.ConflictError):
            self.snapshot()
        self.connection.execute('DELETE FROM improvement_trial_attempts WHERE attempt=3')
        self.connection.executemany('INSERT INTO improvement_operations VALUES(?,?,?)',
            [(f'role_{i}', 'brain', 'experiment') for i in range(MAX_ROLE_OPERATIONS + 1)])
        with self.assertRaises(IM.ConflictError):
            self.snapshot()

    def test_actual_call_scope_cannot_be_replaced_by_another_purpose_or_execution(self):
        self.load(comparison=1, preparation=1)
        for field, wrong in (('purpose', 'interactive'), ('mirror_ref', 'improvement_trial:another_trial'),
                             ('context_ref', 'improvement:another_experiment'), ('attempt', 9),
                             ('reason_ref', 'improvement_trial:trial_0:attempt:2')):
            before = self.connection.execute('SELECT ' + field + ' FROM agent_calls WHERE id=1').fetchone()[0]
            self.connection.execute('UPDATE agent_calls SET ' + field + '=? WHERE id=1', (wrong,))
            with self.subTest(field=field), self.assertRaises(IM.ConflictError):
                self.snapshot()
            self.connection.execute('UPDATE agent_calls SET ' + field + '=? WHERE id=1', (before,))


if __name__ == '__main__':
    unittest.main()
