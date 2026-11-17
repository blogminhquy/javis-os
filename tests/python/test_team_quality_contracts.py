"""Quality contracts use real scratch stores and fake engines only."""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import os
import tempfile
import sqlite3
import time
from contextlib import closing
import unittest
from unittest.mock import patch
from pathlib import Path

os.environ['JAVIS_STATE_DIR'] = tempfile.mkdtemp(prefix='quality-state-')
import sessions
import task_store
import team_runner
import team_store
import team_acceptance


class QualityContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.brain = self.root / 'brain'
        self.brain.mkdir()
        self.ss = sessions.SessionStore(db_path=self.root / 'sessions.db')
        self.addCleanup(lambda: self.ss._conn.close())
        self.ts = task_store.TaskStore(self.root / 'tasks.db')
        self.addCleanup(self.ts.close)
        self.tm = team_store.TeamStore(self.root / 'team.db')
        self.calls = []
        self.notifications = []
        def factory(team, key, role):
            async def execute(req):
                self.calls.append(req)
                return {'text': 'Actual stored deliverable', 'tokens_in': 1, 'tokens_out': 1}
            return 'fake', 'fake', execute
        self.runner = team_runner.TeamRunner(teams=self.tm, tasks=self.ts, sessions=self.ss,
            engine_for=factory, agent_info=lambda b, k: {'slug': 'maker', 'name': 'Maker', 'system': ''},
            notify=lambda *args: self.notifications.append(args))
        self.tid = team_store.new_team_id()
        self.sid = self.ss.create_session(brain=str(self.brain), channel='team:' + self.tid)
        self.tm.create_team(str(self.brain), 'Quality', '', self.sid, team_id=self.tid)
        self.tm.add_member(self.tid, 'ag_maker', 'maker')
        self.tm.set_leader(self.tid, 'ag_maker')
        self.tm.set_work_mode(self.tid, 'full')
        self.team = self.tm.get(self.tid)

    def enable(self, migration='observe'):
        return self.runner.quality.set_policy(self.tid, {'enabled': True, 'limit_migration': migration})

    def submit(self, key='one'):
        return self.runner.submit(self.tid, 'Prepare result', as_job=True, mentions=['ag_maker'],
                                  client_msg_id=key)['task_id']

    def settle(self):
        async def execute():
            for _ in range(5):
                await self.runner.dispatch_once()
                await self.runner.wait_background()
        asyncio.run(execute())

    def view(self, task):
        return self.runner.acceptance_view(self.team, task)

    def decide(self, task, view, key='decision-one', decision='accept'):
        return self.runner.decide_acceptance(self.tid, task, decision,
            note='Please improve' if decision == 'reject' else '', revision=view['revision'], round_=view['rounds'],
            contract_version=view['contract_version'], output_manifest_hash=view['output_manifest_hash'], decision_key=key)

    def test_feature_off_is_legacy(self):
        self.assertFalse(self.runner.quality.policy(self.tid)['enabled'])
        job = self.submit()
        self.settle()
        self.assertEqual('done', self.ts.get_task(job)['status'])
        self.assertIsNone(self.view(job))

    def test_enabled_submit_is_ready_with_message_fallback(self):
        self.enable()
        job = self.submit()
        contract = self.runner.acceptance.get(job)
        self.assertEqual('message', contract['criteria'][0]['target'])
        self.assertTrue(self.ts.get_task(job)['acceptance_ready'])
        self.assertEqual('fallback', contract['origin'])
        self.settle()
        self.assertEqual('acceptance_review', self.ts.get_task(job)['block_kind'])
        view = self.view(job)
        self.assertFalse(view['completion_valid'])
        self.assertTrue(self.decide(job, view)['ok'])
        self.assertTrue(self.view(job)['completion_valid'])

    def test_raw_enqueue_repairs_before_claim_and_disabled_retains_contract(self):
        self.enable()
        job, _ = self.ts.enqueue_team(str(self.brain), self.tid, 'Raw', 'Raw', source_ref='raw:1',
                                     assignee_key='ag_maker')
        claimed = self.ts.claim_team_next(self.tid, self.runner.worker_id)
        self.assertEqual(job, claimed['id'])
        self.assertTrue(self.runner.acceptance.get(job))
        self.runner.quality.set_policy(self.tid, {'enabled': False})
        self.runner.start_job_steps(job)
        async def execute():
            await self.runner.run_job(job)
            await self.runner.wait_background()
        asyncio.run(execute())
        self.assertEqual('acceptance_review', self.ts.get_task(job)['block_kind'])

    def test_template_snapshot_and_compare_and_swap(self):
        self.enable()
        template = self.runner.quality.set_template(self.tid, {'expected_version': 0,
            'criteria': [{'kind': 'owner_confirm', 'target': 'message', 'label': 'Original'}]})
        job = self.submit()
        self.runner.quality.set_template(self.tid, {'expected_version': template['version'],
            'criteria': [{'kind': 'owner_confirm', 'target': 'message', 'label': 'Changed'}]})
        self.assertEqual('Original', self.runner.acceptance.get(job)['criteria'][0]['label'])
        self.assertEqual(template['version'], self.runner.acceptance.get(job)['template_version'])
        with self.assertRaises(ValueError):
            self.runner.quality.set_template(self.tid, {'expected_version': 0,
                'criteria': [{'kind': 'owner_confirm'}]})

    def test_decision_replay_and_changed_message(self):
        self.enable()
        job = self.submit()
        self.settle()
        seen = self.view(job)
        first = self.decide(job, seen)
        self.assertTrue(first['ok'])
        self.assertEqual(first, self.decide(job, seen))
        self.assertFalse(self.decide(job, seen, key='other-tab')['ok'])
        acc = self.runner.acceptance.get(job)
        with self.ss._lock:
            self.ss._conn.execute('UPDATE messages SET content=? WHERE id=?', ('Changed after acceptance', acc['result_msg_id']))
            self.ss._conn.commit()
        self.assertFalse(self.view(job)['completion_valid'])
        self.assertEqual('done', self.ts.get_task(job)['status'])

    def test_policy_requires_migration_and_valid_reference(self):
        with self.assertRaises(ValueError):
            self.runner.quality.set_policy(self.tid, {'enabled': True})
        for value in [float('nan'), float('inf'), -1, True, '3', 10 ** 1000]:
            with self.assertRaises(ValueError):
                self.runner.quality.set_policy(self.tid, {'reference_usd': value})

    def test_observe_only_is_assigned_task_scoped(self):
        self.tm.set_caps(self.tid, {'task_turns': 0})
        self.enable()
        job = self.submit()
        self.settle()
        self.assertEqual('acceptance_review', self.ts.get_task(job)['block_kind'])
        self.assertEqual(0, self.runner._caps(self.tm.get(self.tid))['task_turns'])
        # 17/11/2026: no daily reply cap for any team (team_store.FIXED_CAPS).
        self.assertIsNone(self.runner._caps(self.tm.get(self.tid))['daily_turns'])

    def test_owner_cap_set_after_migration_remains_binding(self):
        self.enable()
        self.tm.set_caps(self.tid, {'task_turns': 0})
        job = self.submit()
        self.settle()
        self.assertEqual('cap_reached', self.ts.get_task(job)['block_kind'])
        self.assertFalse(self.calls)

    def test_retain_and_autonomous_jobs_do_not_bypass_limits(self):
        self.tm.set_caps(self.tid, {'task_turns': 0})
        self.enable('retain')
        job = self.submit()
        self.settle()
        self.assertEqual('cap_reached', self.ts.get_task(job)['block_kind'])
        self.runner.cancel_job(job)
        self.enable('observe')
        autonomous, _ = self.ts.enqueue_team(str(self.brain), self.tid, 'Autonomous', 'Autonomous',
            source_ref='mandate:one', created_by='mandate', assignee_key='ag_maker')
        self.settle()
        self.assertEqual('cap_reached', self.ts.get_task(autonomous)['block_kind'])
        self.assertFalse(self.calls)

    def test_same_metadata_file_change_invalidates_accepted_result(self):
        self.enable()
        product = self.brain / 'report.txt'
        self.runner.quality.set_template(self.tid, {'expected_version': 0,
            'criteria': [{'kind': 'owner_confirm', 'path': 'report.txt'}]})
        job = self.submit()
        product.write_text('first', encoding='utf-8')
        self.settle()
        seen = self.view(job)
        product.write_text('other', encoding='utf-8')
        self.assertEqual('product_changed', self.decide(job, seen)['error'])
        product.write_text('first', encoding='utf-8')
        self.assertTrue(self.decide(job, seen)['ok'])
        stat = product.stat()
        product.write_text('other', encoding='utf-8')
        os.utime(product, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertFalse(self.view(job)['completion_valid'])

    def test_crash_before_contract_write_blocks_then_repairs_raw_claim(self):
        self.enable()
        self.ts.quality_prepare_task = None
        job, _ = self.ts.enqueue_team(str(self.brain), self.tid, 'Raw', 'Raw', source_ref='crash:1')
        self.ts.quality_prepare = None
        self.assertIsNone(self.ts.claim_team_next(self.tid, 'before-recovery'))
        self.ts.quality_prepare = self.runner._prepare_quality_queue
        self.assertEqual(job, self.ts.claim_team_next(self.tid, 'after-recovery')['id'])

    def test_raw_enqueue_snapshots_template_before_owner_edits_it(self):
        self.enable()
        self.runner.quality.set_template(self.tid, {'expected_version': 0,
            'criteria': [{'kind': 'owner_confirm', 'target': 'message', 'label': 'At creation'}]})
        job, _ = self.ts.enqueue_team(str(self.brain), self.tid, 'Raw', 'Raw', source_ref='template:raw')
        self.assertIsNotNone(self.runner.acceptance.get(job))
        self.runner.quality.set_template(self.tid, {'expected_version': 1,
            'criteria': [{'kind': 'owner_confirm', 'target': 'message', 'label': 'Edited later'}]})
        self.settle()
        self.assertEqual('At creation', self.runner.acceptance.get(job)['criteria'][0]['label'])

    def test_approval_blocked_raw_enqueue_still_has_contract(self):
        self.enable()
        job, _ = self.ts.enqueue_team(str(self.brain), self.tid, 'Raw', 'Raw', source_ref='approval:raw',
                                     blocked_kind='waiting_user')
        self.assertIsNotNone(self.runner.acceptance.get(job))
        self.assertTrue(self.ts.get_task(job)['acceptance_ready'])

    def test_owner_can_amend_contract_during_check_without_applying_old_result(self):
        self.enable()
        job = self.submit()
        task = self.ts.claim_team_next(self.tid, self.runner.worker_id)
        self.ts.team_block(job, 'acceptance_checking', 'Checking')
        acc = self.runner.acceptance.get(job)
        self.runner.acceptance.set_state(job, status='checking', revision=task['team_rev'])
        snap = {'rev': task['team_rev'], 'criteria': acc['criteria'], 'msg_id': None,
                'contract_version': acc['contract_version'], 'source_snapshot_hash': acc['source_snapshot_hash']}
        changed = self.runner.set_acceptance(self.tid, job, [{'kind': 'owner_confirm', 'target': 'message', 'label': 'Amended'}])
        self.assertGreater(changed['contract_version'], acc['contract_version'])
        self.assertIsNone(self.runner._apply_checks(self.tid, job, snap, [(acc['criteria'][0], 'pass', {})]))
        self.assertNotEqual('done', self.ts.get_task(job)['status'])

    def test_objective_failure_cannot_be_overridden_with_confirmation(self):
        self.enable()
        self.runner.quality.set_template(self.tid, {'expected_version': 0, 'fix_rounds': 0,
            'criteria': [{'kind': 'file_exists', 'path': 'missing.txt'}, {'kind': 'owner_confirm', 'target': 'message'}]})
        job = self.submit()
        self.settle()
        self.assertEqual('objective_failed', self.decide(job, self.view(job))['error'])

    def test_template_pins_checker_and_fixture_at_contract_creation(self):
        self.enable()
        (self.brain / 'checker.py').write_text('print("first")', encoding='utf-8')
        (self.brain / 'fixture.json').write_text('{"value":1}', encoding='utf-8')
        self.runner.check_command = lambda cmd, root: {'ran': True, 'exit': 0}
        self.runner.quality.set_template(self.tid, {'expected_version': 0,
            'criteria': [{'kind': 'command_ok', 'command': 'python checker.py'}],
            'source_refs': [{'path': 'fixture.json'}]})
        job = self.submit()
        self.assertTrue(self.runner.acceptance.get(job)['source_refs'][0].get('sha256'))
        (self.brain / 'fixture.json').write_text('{"value":2}', encoding='utf-8')
        self.settle()
        self.assertEqual('acceptance_review', self.ts.get_task(job)['block_kind'])

    def test_no_pass_if_checked_product_changes_before_apply(self):
        self.enable()
        job = self.submit()
        task = self.ts.claim_team_next(self.tid, self.runner.worker_id)
        (self.brain / 'product.txt').write_text('old', encoding='utf-8')
        self.runner.set_acceptance(self.tid, job, [{'kind': 'file_exists', 'path': 'product.txt'}])
        acc = self.runner.acceptance.get(job)
        self.ts.team_block(job, 'acceptance_checking', 'Checking')
        self.runner.acceptance.set_state(job, status='checking', revision=task['team_rev'])
        acc = self.runner.acceptance.get(job)
        results = team_acceptance.run_checks(acc, self.brain)
        (self.brain / 'product.txt').write_text('new', encoding='utf-8')
        snap = {'rev': task['team_rev'], 'criteria': acc['criteria'], 'msg_id': None,
                'contract_version': acc['contract_version'], 'source_snapshot_hash': acc['source_snapshot_hash']}
        self.runner._apply_checks(self.tid, job, snap, results)
        self.assertNotEqual('done', self.ts.get_task(job)['status'])

    def test_round_evidence_includes_contract_and_manifest_snapshot(self):
        self.enable()
        job = self.submit()
        self.settle()
        view = self.view(job)
        hist = self.runner.acceptance.history(job)[-1]
        self.assertEqual(view['contract_version'], hist['contract_version'])
        self.assertEqual(view['output_manifest_hash'], hist['output_manifest_hash'])
        self.assertEqual(view['source_snapshot_hash'], hist['source_snapshot_hash'])

    def test_quality_decision_requires_full_snapshot_and_rejects_reused_key(self):
        self.enable()
        job = self.submit()
        self.settle()
        view = self.view(job)
        result = self.runner.decide_acceptance(self.tid, job, 'accept',
            contract_version=view['contract_version'], output_manifest_hash=view['output_manifest_hash'], decision_key='incomplete')
        self.assertEqual('snapshot_required', result['error'])
        self.assertTrue(self.decide(job, view)['ok'])
        self.assertEqual('decision_key_conflict', self.decide(job, view, decision='reject')['error'])

    def test_missing_contract_cannot_escape_when_feature_disabled_after_binding(self):
        self.enable()
        job = self.submit()
        self.runner.quality.set_policy(self.tid, {'enabled': False})
        with closing(sqlite3.connect(self.tm.path)) as c:
            c.execute('DELETE FROM team_acceptance WHERE task_id=?', (job,))
            c.commit()
        self.settle()
        self.assertNotEqual('done', self.ts.get_task(job)['status'])

    def test_legacy_leader_source_is_not_an_owner_obligation(self):
        self.tm.set_caps(self.tid, {'task_turns': 0})
        self.enable()
        job, _ = self.ts.enqueue_team(str(self.brain), self.tid, 'Leader job', 'Leader job',
            source_ref='leader:existing-host-source', assignee_key='ag_maker')
        self.settle()
        self.assertEqual('cap_reached', self.ts.get_task(job)['block_kind'])
        self.assertFalse(self.calls)

    def test_changed_checker_is_unknown_without_executing_replacement(self):
        self.enable()
        checker = self.brain / 'checker.py'
        checker.write_text('print("trusted")', encoding='utf-8')
        self.runner.quality.set_template(self.tid, {'expected_version': 0,
            'criteria': [{'kind': 'command_ok', 'command': 'python checker.py'}]})
        job = self.submit()
        checker.write_text('print("tampered")', encoding='utf-8')
        called = []
        self.runner.check_command = lambda cmd, root: called.append(cmd) or {'ran': True, 'exit': 0}
        self.settle()
        self.assertFalse(called)
        self.assertEqual('acceptance_review', self.ts.get_task(job)['block_kind'])
        self.assertEqual('unknown', self.runner.acceptance.history(job)[-1]['verdict'])

    def test_schema_upgrade_snapshots_legacy_acceptance_once(self):
        path = self.root / 'legacy.db'
        with closing(sqlite3.connect(path)) as c:
            c.executescript(team_acceptance.SCHEMA)
            c.execute("INSERT INTO team_acceptance(task_id,team_id,criteria_json,status,created_at,updated_at) "
                      "VALUES('old','old-team','[]','accepted',1,1)")
            c.commit()
        store = team_acceptance.AcceptanceStore(path)
        backup = path.with_name(path.name + '.pre-0.283.0')
        self.assertTrue(backup.exists())
        before = backup.read_bytes()
        self.assertEqual('accepted', store.get('old')['status'])
        self.assertEqual('', store.get('old')['output_manifest_hash'])
        team_acceptance.AcceptanceStore(path)
        self.assertEqual(before, backup.read_bytes())
        with closing(sqlite3.connect(backup)) as c:
            columns = {row[1] for row in c.execute('PRAGMA table_info(team_acceptance)')}
        self.assertNotIn('contract_version', columns)

    def restart(self):
        old = self.runner
        self.runner = team_runner.TeamRunner(teams=self.tm, tasks=self.ts, sessions=self.ss,
            engine_for=old.engine_for, agent_info=old.agent_info, notify=old._notify_fn)
        return self.runner.recover()

    def decision_messages(self, job):
        return [m for m in self.ss.get_team_messages_page(self.sid, limit=300)['messages']
                if m.get('task_id') == job and (m.get('meta') or {}).get('kind') == 'acceptance_decided']

    def check_decision_crash(self, target, method, decision='accept', after=False, status_filter=None):
        self.enable()
        job = self.submit()
        self.settle()
        seen = self.view(job)
        before_notifications = len(self.notifications)
        original = getattr(target, method)
        def crash(*args, **kwargs):
            if status_filter and kwargs.get('status') != status_filter:
                return original(*args, **kwargs)
            if after:
                original(*args, **kwargs)
            raise RuntimeError('simulated process interruption')
        with patch.object(target, method, crash):
            with self.assertRaises(RuntimeError):
                self.decide(job, seen, decision=decision)
        before_calls = len(self.calls)
        self.restart()
        self.assertEqual(before_calls, len(self.calls), 'recovery never calls an engine')
        replay = self.decide(job, seen, decision=decision)
        self.assertTrue(replay['ok'], replay)
        self.assertEqual(replay, self.decide(job, seen, decision=decision))
        self.restart()
        self.assertEqual(1, len(self.decision_messages(job)))
        self.assertEqual(before_notifications, len(self.notifications), 'reconciliation never resends owner notifications')
        if decision == 'accept':
            self.assertEqual('done', self.ts.get_task(job)['status'])
            self.assertEqual('accepted', self.runner.acceptance.get(job)['status'])
            self.assertTrue(self.view(job)['completion_valid'])
        else:
            self.assertEqual('team_queued', self.ts.get_task(job)['status'])
            repair = [s for s in self.tm.steps(job) if 'Please improve' in s['brief']]
            self.assertEqual(1, len(repair))
            self.assertEqual('fixing', self.runner.acceptance.get(job)['status'])
        return job, seen

    def test_accept_recovers_when_acceptance_state_write_fails(self):
        self.check_decision_crash(self.runner.acceptance, 'set_state', status_filter='accepted')

    def test_accept_recovers_after_task_done_commit(self):
        self.check_decision_crash(self.ts, 'team_finish_reviewed', after=True)

    def test_accept_recovers_when_result_persistence_fails(self):
        self.check_decision_crash(self.runner.acceptance, 'save_decision')

    def test_accept_does_not_duplicate_message_after_message_commit(self):
        self.check_decision_crash(self.runner, '_post', after=True)

    def test_reject_recovers_before_task_unblock_without_duplicate_repair(self):
        self.check_decision_crash(self.ts, 'team_unblock', decision='reject')

    def test_reject_recovers_after_task_unblock_commit(self):
        self.check_decision_crash(self.ts, 'team_unblock', decision='reject', after=True)

    def test_reject_recovers_when_result_persistence_fails(self):
        self.check_decision_crash(self.runner.acceptance, 'save_decision', decision='reject')

    def test_reject_does_not_duplicate_message_after_message_commit(self):
        self.check_decision_crash(self.runner, '_post', decision='reject', after=True)

    def test_accept_recovers_after_intent_commit_before_task_commit(self):
        self.check_decision_crash(self.runner.acceptance, 'begin_decision', after=True)

    def test_reject_recovers_after_atomic_repair_commit(self):
        self.check_decision_crash(self.runner.acceptance, 'apply_rejection', decision='reject', after=True)

    def test_pending_accept_refuses_changed_output_before_task_commit(self):
        self.enable()
        job = self.submit()
        self.settle()
        seen = self.view(job)
        original = self.runner.acceptance.begin_decision
        def crash(*args):
            original(*args)
            raise RuntimeError('intent committed')
        with patch.object(self.runner.acceptance, 'begin_decision', crash):
            with self.assertRaises(RuntimeError):
                self.decide(job, seen)
        message_id = self.runner.acceptance.get(job)['result_msg_id']
        with self.ss._lock:
            self.ss._conn.execute('UPDATE messages SET content=? WHERE id=?', ('Changed after intent', message_id))
            self.ss._conn.commit()
        self.restart()
        self.assertEqual('product_changed', self.decide(job, seen)['error'])
        self.assertEqual('team_blocked', self.ts.get_task(job)['status'])
        self.assertEqual([], self.decision_messages(job))

    def test_rejected_repair_cap_recovers_without_duplicate_records(self):
        self.tm.set_caps(self.tid, {'task_steps': 1})
        self.enable()
        job = self.submit()
        self.settle()
        seen = self.view(job)
        with patch.object(self.runner.acceptance, 'save_decision', side_effect=RuntimeError('result not written')):
            with self.assertRaises(RuntimeError):
                self.decide(job, seen, decision='reject')
        self.restart()
        replay = self.decide(job, seen, decision='reject')
        self.assertTrue(replay['ok'])
        self.assertEqual('cap_reached', self.ts.get_task(job)['block_kind'])
        self.assertEqual(1, len(self.tm.steps(job)))
        records = [e for e in self.tm.events(self.tid) if e['kind'] == 'cap_blocked']
        self.assertEqual(1, len(records))
        self.assertEqual(1, len(self.decision_messages(job)))

    def test_same_process_retry_finishes_pending_decision(self):
        self.enable()
        job = self.submit()
        self.settle()
        seen = self.view(job)
        with patch.object(self.runner.acceptance, 'save_decision', side_effect=RuntimeError('result not written')):
            with self.assertRaises(RuntimeError):
                self.decide(job, seen)
        self.assertTrue(self.decide(job, seen)['ok'])
        self.assertEqual(1, len(self.decision_messages(job)))

    def test_legacy_keyed_decision_checks_historical_file_hashes(self):
        job = self.submit()
        product = self.brain / 'legacy.txt'
        self.runner.set_acceptance(self.tid, job, [{'kind': 'owner_confirm', 'path': 'legacy.txt'}])
        product.write_text('Original', encoding='utf-8')
        self.settle()
        seen = self.view(job)
        self.runner.acceptance.set_state(job, output_manifest=[], output_manifest_hash='')
        product.write_text('Edited', encoding='utf-8')
        result = self.runner.decide_acceptance(self.tid, job, 'accept', decision_key='legacy-key')
        self.assertEqual('product_changed', result.get('error'))
        self.assertNotEqual('done', self.ts.get_task(job)['status'])

    def check_objective_crash(self, target, method, after=False, status_filter=None):
        self.enable()
        job = self.submit()
        task = self.ts.claim_team_next(self.tid, self.runner.worker_id)
        self.runner.set_acceptance(self.tid, job, [{'kind': 'file_exists', 'path': 'objective.txt'}])
        (self.brain / 'objective.txt').write_text('Checked product', encoding='utf-8')
        message_id, _ = self.ss.append_team_message(self.sid, 'assistant', 'Objective result',
            author_kind='agent', author_ref='ag_maker', task_id=job)
        self.runner.acceptance.set_state(job, status='checking', revision=task['team_rev'], result_msg_id=message_id)
        self.ts.team_block(job, 'acceptance_checking', 'Checking')
        acc = self.runner.acceptance.get(job)
        snap = {'rev': task['team_rev'], 'criteria': acc['criteria'], 'msg_id': message_id,
                'contract_version': acc['contract_version'], 'source_snapshot_hash': acc['source_snapshot_hash']}
        results = team_acceptance.run_checks(acc, self.brain)
        original = getattr(target, method)
        def crash(*args, **kwargs):
            if status_filter and kwargs.get('status') != status_filter:
                return original(*args, **kwargs)
            if after:
                original(*args, **kwargs)
            raise RuntimeError('automatic pass interrupted')
        with patch.object(target, method, crash):
            with self.assertRaises(RuntimeError):
                self.runner._apply_checks(self.tid, job, snap, results)
        self.restart()
        self.restart()
        self.assertEqual('done', self.ts.get_task(job)['status'])
        self.assertEqual('passed', self.runner.acceptance.get(job)['status'])
        self.assertTrue(self.view(job)['completion_valid'])
        self.assertEqual([], self.runner.acceptance.pending_decisions(job))
        with closing(sqlite3.connect(self.tm.path)) as c:
            intents = c.execute('SELECT status FROM team_acceptance_intents WHERE task_id=?', (job,)).fetchall()
        self.assertEqual([('complete',)], intents)
        self.assertEqual(1, len(self.runner.acceptance.history(job)))
        passed = [m for m in self.ss.get_team_messages_page(self.sid, limit=300)['messages']
                  if m.get('task_id') == job and (m.get('meta') or {}).get('kind') == 'acceptance_result'
                  and (m.get('meta') or {}).get('verdict') == 'pass']
        self.assertEqual(1, len(passed))
        self.assertEqual([], self.calls)
        self.assertEqual([], self.notifications)

    def test_objective_pass_recovers_after_task_done_commit(self):
        self.check_objective_crash(self.ts, 'team_finish_reviewed', after=True)

    def test_objective_pass_recovers_before_passed_state_write(self):
        self.check_objective_crash(self.runner.acceptance, 'set_state', status_filter='passed')

    def test_objective_pass_recovers_before_result_persistence(self):
        self.check_objective_crash(self.runner.acceptance, 'save_decision')

    def test_objective_pass_recovers_after_message_commit(self):
        self.check_objective_crash(self.runner, '_post', after=True)

    def test_objective_pass_recovers_after_intent_commit(self):
        self.check_objective_crash(self.runner.acceptance, 'begin_decision', after=True)

    def test_objective_pass_cannot_bypass_owner_confirmation(self):
        self.enable()
        job = self.submit()
        task = self.ts.claim_team_next(self.tid, self.runner.worker_id)
        message_id, _ = self.ss.append_team_message(self.sid, 'assistant', 'Requires owner confirmation',
            author_kind='agent', author_ref='ag_maker', task_id=job)
        self.runner.acceptance.set_state(job, status='checking', revision=task['team_rev'], result_msg_id=message_id)
        self.ts.team_block(job, 'acceptance_checking', 'Checking')
        acc = self.runner.acceptance.get(job)
        snap = {'rev': task['team_rev'], 'criteria': acc['criteria'], 'msg_id': message_id,
                'contract_version': acc['contract_version'], 'source_snapshot_hash': acc['source_snapshot_hash']}
        message = self.ss.team_message(self.sid, message_id)
        self.runner._apply_checks(self.tid, job, snap,
            [(acc['criteria'][0], 'pass', team_acceptance.message_evidence(message))])
        self.assertEqual('acceptance_review', self.ts.get_task(job)['block_kind'])
        self.assertFalse(self.view(job)['completion_valid'])


if __name__ == '__main__':
    unittest.main()
