"""Owned baseline5 query fixtures; no ambient CLI, account or provider.

Static candidate/runtime seams are engineering fixture data. Real source,
admission, encrypted SQL, ledger and workspace owners are composed explicitly.
"""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import copy
from contextlib import closing
import json
import hashlib
import os
from pathlib import Path
import shutil
import sys
import sysconfig
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import unittest
from unittest.mock import patch

import improvement_store as IM
from improvement_assets import capture_source
from improvement_cases import CaseStore
from improvement_trial_admission import TrialAdmission
from improvement_trial_file_sources import BrainFileFixtures
from improvement_trial_host import HostContextStore
import improvement_qualification_session as QS
import improvement_native_qualifications as registry
import test_improvement_trial_associations as associations
import test_improvement_qualification_session as session_fixtures


def owned_admission(test, session):
    """Reuse authoring data, never upstream reservation/phase/input-version seams."""
    def private_host(f):
        f.root, f.brain = session.root, Path(session.principal.brain_id)
        f.owner = session.principal
        f.database, f.assets, f.blobs = session.assets.store, session.assets, session.assets.blobs
        f.cases = CaseStore(f.assets)
        f.skill = f.brain / 'skills' / 'report' / 'SKILL.md'
        f.skill.parent.mkdir(parents=True)
        f.skill.write_bytes(b'---\nname: Owner report\ndescription: Summarize an authorized fixture.\n---\nRetain owner rules.\n')
        source, raw = capture_source(f.brain, 'skill', 'report', pack_state_dir=f.root / 'packs')
        f.target = f.assets.capture(f.owner, source, raw, event_key='query-target')
        f.protected = f.brain / 'owner.md'
        f.protected.write_bytes(b'Complete synthetic owner instructions.\n')
        f.path = f.brain / 'reports' / 'source.txt'; f.path.parent.mkdir()
        f.raw = b'Private selected engineering source.\n'; f.path.write_bytes(f.raw)
        f.ref = 'brain-file:reports/source.txt'
        f.metadata = dict(timezone='UTC', data_period='engineering', cutoff='2026-10-22T00:00:00+00:00',
            schema='text/plain', freshness_policy='require_current_version')
        f.provider = BrainFileFixtures({f.ref: f.metadata})
        f.surface = {'kind': 'synthetic-owner-test', 'session_id': ''}
        f.engine = copy.deepcopy(session._pin)
        f.host = HostContextStore(f.assets, context_capture=f.context_capture,
            selected_engine=lambda: copy.deepcopy(f.engine), target_observer=f.targets, fixture_observer=f.provider)
    with patch.object(associations.fixtures.HostSnapshotTests, 'setUp', private_host):
        fixture = associations.AssociationTests(); fixture.setUp()
    test.addCleanup(fixture.doCleanups)
    associated = fixture.create()
    base = session.assets.create_bundle(session.principal, [fixture.f.target['revision_id']], event_key='query-base')
    public = dict(event_key='query-start', experiment_id='association-experiment',
        contract_id=fixture.saved['contract_id'], case_set_id=associated['case_set_id'], case_id='case-1',
        base_bundle_id=base['bundle_id'], candidate_bundle_id=base['bundle_id'], variant='baseline', repeat=1,
        timeout_seconds=120, expected_context_generation=1)
    return fixture, TrialAdmission(fixture.host), public


import test_improvement_qualification_native_preflight as preflight_fixture
import test_improvement_native_transport_v2 as kernel_fixture


# Synthetic engine/capture seam, executed only in the owned guarded worker.
# Actual SDK client, options, transport builder/connect and original stdin write
# run unchanged. The copied cmd.exe is inert and cannot select any provider.
_QUERY_FIXTURE = r'''
import builtins,sys,os,asyncio,json,subprocess,types
original_import=builtins.__import__
configured=False
def install(name,*args,**kwargs):
 global configured
 module=original_import(name,*args,**kwargs)
 if name=='improvement_native_sdk' and not configured:
  configured=True
  assert os.environ.get('ANTHROPIC_API_KEY')=='javis-native-qualification-dummy'
  from improvement_native_capture import NativeDebugInvocation as RealCapture
  import anyio
  class Output:
   def __init__(self,data):self.data=data
   async def receive(self,maximum=65536):
    if not self.data:raise anyio.EndOfStream
    data,self.data=self.data,None
    return data
   async def aclose(self):pass
  class FixedCapture:
   def __init__(self,opener,**options):self.opener=opener;self.options=options;self.owner=None
   @property
   def process(self):return None if self.owner is None else self.owner.process
   async def __aenter__(self):return self
   async def open_process(self,argv,**kwargs):
    query=self.options['purpose']=='sdk_query'
    expected=(None,subprocess.list2cmdline(argv),None,None,True,0x08000006,kwargs['env'],kwargs['cwd'],None)
    def validate(actual):
     assert actual[5]==0x08000006 and actual[6]==kwargs['env'] and actual[7]==kwargs['cwd']
     return self.options['validate_create'](expected)
    async def inert(command,**opts):
     proc=await self.opener(command,**opts)
     if not query:
      data=(b'2.1.99 (inert fixture)\n' if argv[1:] in (['--version'],['-v']) else
       json.dumps(dict(loggedIn=False,authMethod='fixture-unknown',apiProvider=None,subscriptionType=None)).encode())
      # Drain the actual inert child before replacing only fixed diagnostic output.
      await proc.wait()
      if proc.stdout is not None:await proc.stdout.aclose()
      if proc.stderr is not None:await proc.stderr.aclose()
      proc=types.SimpleNamespace(pid=proc.pid,stdout=Output(data),stderr=Output(b''),wait=proc.wait,aclose=proc.aclose)
     return proc
    self.owner=RealCapture(inert,**{**self.options,'validate_create':validate})
    await self.owner.__aenter__()
    command=[argv[0],'/d','/q'] if query else [argv[0],'/d','/c','exit 0']
    return await self.owner.open_process(command,**kwargs)
   async def aclose(self):
    if self.owner is not None:await self.owner.aclose()
  module.NativeDebugInvocation=FixedCapture
 if name=='improvement_claude':
  module._runtime_identity=lambda pin:dict(platform=sys.platform,managed_policy='absent',
   **{key:pin[key] for key in ('cli_hash','sdk_version','profile_hash')})
 return module
builtins.__import__=install
class InertEngine:
 def __init__(self,**kwargs):self.cwd=kwargs['cwd'];self.session_id=None;self._on_stderr=lambda text:None
 async def query(self,prompt):
  from claude_agent_sdk import SystemMessage
  from improvement_native_profile import _frame
  from improvement_store import _hash
  profile=self.trial_profile
  options=profile.options(self)
  await checkpoint('sdk')
  client=profile.create_client(options)
  transport=client._custom_transport
  try:
   await transport.connect()
   await profile.before_query()
   await checkpoint('input')
   await transport.write(_frame(prompt))
   await checkpoint('receive')
   sid='11111111-1111-4111-8111-111111111111'
   for event in profile.observe(SystemMessage(subtype='init',data={'session_id':sid,'tools':profile._tools()})):yield event
   receipt=profile.installation_receipt(sid)
   yield dict(type='installation_receipt',receipt=receipt,hash=_hash(receipt))
   yield dict(type='terminal',subtype='success',is_error=False,artifact_status='missing',session_id=sid,actual_models=[])
  finally:await transport.close()
sys.modules['claude_cli']=types.SimpleNamespace(claude_engine=InertEngine)
async def checkpoint(phase):
 from pathlib import Path
 root=Path(os.environ['HOME']).parent.parent
 if (root / ('hold-'+phase)).exists():
  (root / ('started-'+phase)).write_bytes(b'owned fixture phase')
  while not (root / ('release-'+phase)).exists():await asyncio.sleep(.005)
'''


@unittest.skipUnless(os.name == 'nt' and sys.flags.isolated, 'actual Windows native owners and isolated SDK')
class QualificationQueryTests(unittest.IsolatedAsyncioTestCase):
    cleanup_diagnostic = kernel_fixture.HostGuardianWindowsTests.cleanup_diagnostic
    persist = kernel_fixture.HostGuardianWindowsTests.persist
    async def cleanup(self):
        session=getattr(self,'qualification',None)
        boundaries=[]
        if session is not None:
            await session.aclose_queries()
            if session._native_parent is not None:boundaries.append(session._native_parent)
            boundaries.extend(context['boundary'] for context in session._queries.values() if context['boundary'] is not None)
        await preflight_fixture.QualificationKernelTests.cleanup(self)
        for boundary in boundaries:
            owner=boundary._guardian
            if owner is None:continue
            print('ACTUAL_OWNERSHIP_RECEIPT',json.dumps(dict(
                phase='query' if hasattr(boundary,'_query_binding') else 'preflight',
                worker=owner._worker_identity,guardian=owner._guardian_identity,
                closed=owner.closed,native_drained=owner.native_drained,
                worker_exit=getattr(owner,'_worker_exit_code',None),guardian_exit=getattr(owner,'_guardian_exit_code',None),
                boundary_state=boundary._owner_state,host_operations=len(session._host_operations),
                retained_native=len(session._owners),retained_resources=len(session._attempt_resources),
                pending_proofs=len(session._pending_proofs),archive_disposed=not session.root.exists()),sort_keys=True),flush=True)

    async def asyncSetUp(self):
        await preflight_fixture.QualificationKernelTests.asyncSetUp(self)
        self.session = self.qualification
        # Synthetic guarded bootstrap, with original SDK imports available.
        # No installed selected CLI is used: the sole selected executable is cmd.
        for path in SERVER.glob('*.py'): shutil.copyfile(path, self.source / path.name)
        native_worker=(self.source / 'improvement_native_worker.py')
        native_worker.write_text(native_worker.read_text(encoding='utf-8').replace(
            'except Exception as error:\n        if owner._adopted',
            "except Exception as error:\n        with open(Path(owner._packet['qualification']['scope']['root']) / 'fixture-error.log','a') as diagnostic: diagnostic.write(type(error).__name__ + ':' + str(error) + '\\n'); diagnostic.flush()\n        if owner._adopted"),encoding='utf-8')
        native_sdk=(self.source / 'improvement_native_sdk.py')
        native_sdk.write_text(native_sdk.read_text(encoding='utf-8').replace(
            "raise NativeSDKError('native_sdk_preflight_failed') from None",
            "import traceback\n            with open(Path(os.environ['HOME']).parent.parent / 'fixture-error.log','a') as diagnostic: diagnostic.write(traceback.format_exc()); diagnostic.flush()\n            raise NativeSDKError('native_sdk_preflight_failed') from None"),encoding='utf-8')
        worker = _QUERY_FIXTURE + '\n' + (SERVER / 'improvement_worker.py').read_text(encoding='utf-8').replace('from __future__ import annotations', '').replace(
            'if native_route: return 1', "if native_route:\n            import traceback\n            traceback.print_exc()\n            return 1")
        worker=worker.replace('"tool_denials": profile.denials})','"tool_denials": profile.denials})\n    await checkpoint("drain")')
        (self.source / 'improvement_worker.py').write_text(worker, encoding='utf-8')
        declared = set(self.guardian['source']['files']) | {
            'improvement_claude.py', 'improvement_native_profile.py', 'improvement_native_sdk.py',
            'improvement_sandbox.py', 'improvement_worker.py', 'improvement_qualification_protocol.py',
            'improvement_qualification_results.py', 'improvement_qualification_session.py'}
        self.guardian['source']['files'] = {name: hashlib.sha256((self.source / name).read_bytes()).hexdigest() for name in declared}
        packages = Path(sysconfig.get_path('purelib'))
        # Synthetic bootstrap seam: original SDK imports are available but are
        # not a candidate/release qualification. Full installed closure is the
        # independent root gate; fixture native containment comes from cmd.exe.
        self.guardian['imports'] = dict(site_packages=str(packages), files={})
        self.policy['bootstrap']['imports'] = self.guardian['imports']
        # Candidate seam returns copies of these exact manifests on every scan.
        self.candidate['manifests'].update(guardian=self.guardian, trial=self.policy['bootstrap'])
        self.session.cleanup()
        from improvement_claude import profile_hash
        self.config['profile_hash'] = profile_hash()
        self.static['profile_hash'] = self.config['profile_hash']
        key = (sys.platform, *(self.config[name] for name in ('cli_version', 'cli_hash', 'sdk_version', 'profile_version', 'profile_hash')),
            self.candidate['fingerprint'])
        registry.REVIEWED_QUALIFICATION_CANDIDATES[key] = 'b' * 64
        self.session = self.qualification = QS.QualificationSession.open(pin=self.config, endpoint='http://127.0.0.1:15432',
            expected_fingerprint=self.candidate['fingerprint'], lifetime_seconds=300, maximum_queries=1)
        self.fixture, self.admission, self.public = owned_admission(self, self.session)

    async def execute(self, public=None):
        import improvement_native_transport as transport
        diagnostics=[]
        async def drain(owner, handle):
            while True:
                task=owner._task(asyncio.to_thread(owner._api.read,handle))
                raw=await owner._wait(task,owner._lifetime)
                if not raw:return
                diagnostics.append(raw)
        async def drain_stream(owner, stream):
            while True:
                task=owner._task(asyncio.to_thread(stream.read,4096))
                raw=await owner._wait(task,owner._lifetime)
                if not raw:return
                diagnostics.append(raw)
        try:
            with patch.object(transport.GuardianSessionV2,'_drain_handle',drain), patch.object(transport.GuardianSessionV2,'_drain_stream',drain_stream):
                return await self.session.run_trial(self.admission, public or self.public)
        except BaseException:
            print('OWNED_INERT_WORKER_DIAGNOSTIC',b''.join(diagnostics).decode(errors='replace'),flush=True)
            diagnostic=self.session.root / 'fixture-error.log'
            if diagnostic.exists():print(diagnostic.read_text(),flush=True)
            boundary=self.session._native_parent
            if boundary is not None and boundary._guardian is not None:
                owner=boundary._guardian
                print('OWNER_STATE',boundary._owner_state,'GUARDS',len(owner._guards),'OFFER',owner._offer is not None,
                    'WORKER',owner._worker_identity,'FAILURE',repr(owner._failure),flush=True)
            raise

    async def test_integrated_owned_baseline5_query_and_cold_result(self):
        session = self.session
        # Meaningful RED prerequisite: current real owner preparation/source is
        # valid, but ordinary product admission truthfully refuses this pin.
        with closing(session.assets.store._conn()) as connection:
            plan, request, split, _ = self.admission._prepare(connection, session.principal, self.public)
            self.admission._available(connection, session.principal.brain_id, self.public, plan, request)
        self.admission.host.live_guard(session.principal, request)
        self.assertIn(split, ('tuning', 'qualification', 'regression'))
        with self.assertRaisesRegex(ValueError, 'trial_native_unavailable'):
            self.admission.admit(session.principal, self.public)
        with closing(session.assets.store._conn()) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM agent_calls').fetchone()[0], 0)
        print('INTEGRATED_RED_VALID_REAL_OWNER ordinary product refusal; zero reserved calls', flush=True)
        result = await self.execute()
        self.assertEqual(result.domain, 'qualification')
        self.assertIs(result.supported, False)
        self.assertIs(result.account_ready, False)
        self.assertIs(result.business_proof, False)
        self.assertFalse(hasattr(result, 'capability_hash'))
        from improvement_qualification_results import QualificationQueryResults
        session.close()
        assets, principal = session.open_forensic(session.root, expected_run_hash=session.run_hash)
        self.assertEqual(QualificationQueryResults.read_stored(assets, principal, kind='trial',
            subject_id=result.subject_id, attempt=1, expected_run_hash=session.run_hash), result)

    async def wait_event(self, event):
        async with asyncio.timeout(90):
            while not event.is_set(): await asyncio.sleep(.005)

    def count(self, operation):
        with closing(self.session.assets.store._conn()) as connection:
            return connection.execute('SELECT COUNT(*) FROM improvement_events WHERE operation=?', (operation,)).fetchone()[0]

    def read_result(self, result):
        from improvement_qualification_results import QualificationQueryResults
        return QualificationQueryResults.read_stored(self.session.assets, self.session.principal, kind='trial',
            subject_id=result.subject_id, attempt=result.attempt, expected_run_hash=self.session.run_hash)

    async def prepared(self, repeat):
        from improvement_trial_runner import _settled_call
        session, trials = self.session, self.admission.trials
        admitted = await _settled_call(self.admission.admit_qualification, session, session.principal,
            {**self.public, 'event_key': 'prepared-' + str(repeat), 'repeat': repeat})
        row = await _settled_call(trials.get, session.principal, admitted.trial_id)
        row = await _settled_call(trials.claim, session.principal, admitted.trial_id, expected_generation=row['generation'])
        token = row['lease_token']
        context = await _settled_call(self.admission.host.context_loader, session.principal, admitted.request)
        manifest = await _settled_call(trials.materialize, session.principal, admitted.trial_id,
            expected_generation=row['generation'], lease_token=token, baseline_context=context)
        self.assertEqual(manifest['version'], 5)
        receipt = await _settled_call(trials.workspace.prepare, admitted.trial_id, 1, manifest)
        row = await _settled_call(trials.prepared, session.principal, admitted.trial_id,
            expected_generation=row['generation'], lease_token=token, receipt=receipt)
        return row, token

    async def discard_prepared(self, row, token):
        from improvement_trial_runner import _settled_call
        trials = self.admission.trials
        latest = await _settled_call(trials.get, self.session.principal, row['trial_id'])
        await _settled_call(trials.abort, self.session.principal, row['trial_id'],
            expected_generation=latest['generation'], lease_token=token, reason='cancelled')
        await _settled_call(trials.cleanup_terminal, self.session.principal, row['trial_id'])

    async def test_query_budget_one_concurrent_real_attempt_only_one_binding(self):
        await self.session.verify_native()
        pairs = [await self.prepared(number) for number in (1, 2)]
        def bind(pair):
            row, token = pair
            try:
                return self.session._query_binding(self.admission.trials, self.session.principal, row['trial_id'],
                    expected_generation=row['generation'], lease_token=token)
            except PermissionError as error:return str(error)
        try:
            def compete():
                with ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(bind,pairs))
            answers=await asyncio.to_thread(compete)
            self.assertEqual(sum(type(answer) is QS.QualificationQueryBinding for answer in answers),1,answers)
            self.assertIn('qualification_query_budget_exhausted',answers)
            self.assertEqual(self.count('native_qualification_attempt'),1)
            self.assertFalse(self.session._owners)
        finally:
            for pair in pairs:await self.discard_prepared(*pair)

    async def test_foreign_owner_and_rehashed_binding_refuse_before_native_acquisition(self):
        import improvement_native_parent as parent
        from resonance_store import Principal
        await self.session.verify_native()
        row, token = await self.prepared(1)
        try:
            with self.assertRaises(PermissionError):
                self.session._query_binding(self.admission.trials, Principal('owner','owner','foreign'),row['trial_id'],
                    expected_generation=row['generation'],lease_token=token)
            binding=self.session._query_binding(self.admission.trials,self.session.principal,row['trial_id'],
                expected_generation=row['generation'],lease_token=token)
            values=asdict(binding);values['request_hash']='c'*64
            values['authority_hash']=IM._hash({key:value for key,value in values.items() if key!='authority_hash'})
            spoof=object.__new__(QS.QualificationQueryBinding)
            for name,value in values.items():object.__setattr__(spoof,name,value)
            with patch('improvement_native_transport.GuardianSessionV2._prepare_guards',side_effect=AssertionError('no native acquisition')):
                with self.assertRaises(PermissionError):parent.NativeParentBoundary.for_qualification_query(self.session,spoof)
                with self.assertRaises(PermissionError):parent.NativeParentBoundary.for_qualification_query(self.session,copy.copy(binding))
            self.assertFalse(self.session._owners)
        finally:await self.discard_prepared(row,token)

    async def test_baseline5_actual_worker_profile_and_four_durable_decisions(self):
        result=await self.execute()
        context=self.session._queries[(result.subject_id,1)]
        boundary=context['boundary'];guardian=boundary._guardian
        self.assertEqual(context['manifest']['version'],5)
        self.assertEqual(guardian._allowed,{'adapter_version','auth_status','sdk_version','query'})
        self.assertEqual(boundary._qualification_seed['qualification']['version'],2)
        self.assertTrue(guardian.closed and guardian.native_drained)
        self.assertEqual((guardian._worker_exit_code,guardian._guardian_exit_code),(0,0))
        self.assertEqual(self.count('native_image_decision'),6)
        self.assertEqual(self.count('native_qualification_attempt'),1)
        self.assertEqual(result.input_delivery_hash,context['completion'].input_delivery_hash)
        self.assertIn(('id','native_qualification'),result.checks[2])
        self.assertFalse(self.session._host_operations or self.session._owners)
        with closing(self.session.assets.store._conn()) as connection:
            self.assertIsNone(connection.execute('SELECT result_json FROM improvement_trial_attempts').fetchone()[0])
            for table in ('improvement_trial_artifacts','improvement_trial_receipts','improvement_trial_results'):
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)
        # Genuine replay uses the immutable cold result and never a new owner.
        self.assertEqual(await self.execute(),result)
        self.assertEqual(self.count('native_qualification_attempt'),1)

    async def test_engine_commit_and_recorder_finish_before_ack_and_original_user_write(self):
        from improvement_telemetry import NativeUsageRecorder
        from improvement_native_transport import GuardianSessionV2
        trials=self.admission.trials
        started,release=threading.Event(),threading.Event()
        finish_started,finish_release=threading.Event(),threading.Event()
        original=trials.start_engine;send=GuardianSessionV2.send_worker
        order=[]
        def held(*args,**kwargs):
            started.set();release.wait(90)
            result=original(*args,**kwargs);order.append('commit');return result
        async def ack(owner,body):
            if owner._qualification_boundary is not None and hasattr(owner._qualification_boundary,'_query_binding'):
                context=owner._qualification_boundary._qualification._query_context(owner._qualification_boundary._query_binding)
                self.assertIs(type(context.get('recorder')),NativeUsageRecorder)
                call=trials.ledger.get(context['link']['call_id'])
                self.assertIsNotNone(call['engine_at']);order.append('ack')
            return await send(owner,body)
        finish=NativeUsageRecorder.finish
        def finished(recorder,status):
            finish_started.set();finish_release.wait(90)
            answer=finish(recorder,status);order.append('finish');return answer
        with patch.object(trials,'start_engine',held),patch.object(GuardianSessionV2,'send_worker',ack),patch.object(NativeUsageRecorder,'finish',finished):
            task=asyncio.create_task(self.execute())
            try:
                await self.wait_event(started)
                context=next(iter(self.session._queries.values()));owner=context['boundary']._guardian
                self.assertIsNone(owner._ack_task)
                self.assertIsNone(trials.ledger.get(context['link']['call_id'])['engine_at'])
                self.assertFalse(any(packet['body']['type']=='engine_event' for packet in context['boundary']._qualification_packets.values()))
            finally:release.set()
            try:
                await self.wait_event(finish_started)
                self.assertEqual(self.count('native_qualification_query_evidence'),0)
                self.assertEqual(order,['commit','ack'])
            finally:finish_release.set()
            result=await task
        self.assertEqual(order,['commit','ack','finish'])
        completion=self.session._queries[(result.subject_id,1)]['completion']
        ack=json.loads(completion.ack)
        self.assertTrue(ack['ack_send_complete']);self.assertEqual(ack['engine_at'],result.engine_at)

    async def test_close_after_callback_before_ack_never_delivers_input(self):
        from improvement_native_transport import GuardianSessionV2
        original=GuardianSessionV2.send_worker
        async def close(owner,body):
            self.session.close()
            return await original(owner,body)
        with patch.object(GuardianSessionV2,'send_worker',close):
            with self.assertRaises(BaseException):await self.execute()
        context=next(iter(self.session._queries.values()));owner=context['boundary']._guardian
        self.assertIsNone(context['boundary']._ack_witness)
        self.assertFalse(owner._accounting_acknowledged)
        self.assertFalse(any(packet['body']['type']=='engine_event' for packet in context['boundary']._qualification_packets.values()))
        call=self.admission.trials.ledger.get(context['link']['call_id'])
        self.assertIsNotNone(call['engine_at']);self.assertEqual(call['status'],'interrupted')
        self.assertEqual(self.count('native_qualification_query_result'),0)

    async def test_settled_call_after_callback_refuses_ack_and_user_input(self):
        from improvement_telemetry import NativeUsageRecorder
        original=NativeUsageRecorder.__init__
        def interrupted(recorder,ledger,call_id,*args,**kwargs):
            original(recorder,ledger,call_id,*args,**kwargs)
            self.assertTrue(ledger.settle(call_id,'interrupted'))
        with patch.object(NativeUsageRecorder,'__init__',interrupted):
            with self.assertRaises(Exception):await self.execute()
        context=next(iter(self.session._queries.values()))
        self.assertIsNone(context['boundary']._ack_witness)
        self.assertFalse(context['boundary']._guardian._accounting_acknowledged)
        self.assertFalse(any(packet['body']['type']=='engine_event' for packet in context['boundary']._qualification_packets.values()))

    async def test_ambiguous_ack_retains_charged_unknown_and_never_resends(self):
        from improvement_private_channel import PrivateWorkerChannelV2
        original=PrivateWorkerChannelV2.send;sent=[]
        async def ambiguous(channel,body):
            answer=await original(channel,body)
            if channel._role=='host' and body['type']=='engine_start_ack':
                sent.append(answer['sequence']);raise OSError('fixture ambiguous completed private ACK')
            return answer
        with patch.object(PrivateWorkerChannelV2,'send',ambiguous):
            with self.assertRaises(Exception):await self.execute()
        self.assertEqual(sent,[1])
        context=next(iter(self.session._queries.values()))
        self.assertIsNone(context['boundary']._ack_witness)
        call=self.admission.trials.ledger.get(context['link']['call_id'])
        self.assertIsNotNone(call['engine_at']);self.assertEqual(call['status'],'interrupted')
        with self.assertRaises(Exception):await self.execute()
        self.assertEqual(self.count('native_qualification_attempt'),1)
        self.assertEqual(self.count('native_qualification_query_result'),0)

    async def test_stage_without_cleanup_never_reads_as_final_result(self):
        trials=self.admission.trials
        original=trials.workspace.cleanup;started,release=threading.Event(),threading.Event()
        def held(*args):started.set();release.wait(90);return original(*args)
        with patch.object(trials.workspace,'cleanup',held):
            task=asyncio.create_task(self.execute())
            try:
                await self.wait_event(started)
                context=next(iter(self.session._queries.values()));binding=context['binding']
                self.assertTrue(Path(context['receipt']['path']).exists())
                self.assertEqual(self.count('native_qualification_query_evidence'),1)
                self.assertEqual(self.count('native_qualification_query_result'),0)
                from improvement_qualification_results import QualificationQueryResults
                with self.assertRaises(Exception):QualificationQueryResults.read_stored(self.session.assets,self.session.principal,
                    kind='trial',subject_id=binding.subject_id,attempt=1,expected_run_hash=self.session.run_hash)
                self.assertEqual(trials.ledger.get(context['link']['call_id'])['status'],'ok')
                task.cancel();await asyncio.sleep(.005);task.cancel()
            finally:release.set()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertIs(self.session._pending_proofs.get((binding.subject_id,1)),context)
        self.assertIsNotNone(context['cleanup'])
        self.assertEqual(self.count('native_qualification_query_result'),0)
        call_id=context['link']['call_id']
        result=await self.execute()
        self.assertEqual(result.call_id,call_id)
        self.assertEqual(self.count('native_qualification_attempt'),1)
        self.assertFalse(self.session._pending_proofs)
        self.assertEqual(self.read_result(result),result)

    async def test_unresolved_native_evidence_retains_exact_workspace_and_lifetime(self):
        from improvement_native_parent import NativeParentBoundary
        trials=self.admission.trials
        save=NativeParentBoundary._save_preflight
        cleanup,release=trials.workspace.cleanup,trials.workspace.release_execution
        cleanup_calls=[];release_calls=[];failures=[];original_resource=[]
        def unresolved(boundary,*args):
            if hasattr(boundary,'_query_binding'):
                key=(boundary._query_binding.subject_id,boundary._query_binding.attempt)
                resource=self.session._attempt_resources[key]
                if not original_resource:original_resource.extend((resource,resource['lifetime'][0]))
                failures.append(boundary);raise OSError('owned evidence store unavailable')
            return save(boundary,*args)
        def protect_cleanup(*args):
            cleanup_calls.append(args)
            raise OSError('test prevents deletion while native evidence is unknown')
        def protect_release(handles):
            release_calls.append(handles)
            raise OSError('test prevents releasing original unresolved lifetime')
        try:
            with patch.object(NativeParentBoundary,'_save_preflight',unresolved), \
                    patch.object(trials.workspace,'cleanup',protect_cleanup), \
                    patch.object(trials.workspace,'release_execution',protect_release):
                with self.assertRaises(Exception):await self.execute()
                context=next(iter(self.session._queries.values()));boundary=context['boundary']
                resource=self.session._attempt_resources[(context['identifier'],1)]
                handles=resource['lifetime'][0];workspace=Path(context['receipt']['path'])
                print('FIX1_UNRESOLVED_NATIVE',json.dumps(dict(state=boundary._owner_state,
                    evidence_settled=boundary._evidence_settled,workspace=str(workspace),
                    handles=[id(handle) for handle in handles],closed=[handle.closed for handle in handles],
                    cleanup_calls=len(cleanup_calls),release_calls=len(release_calls),close_failures=len(failures))),flush=True)
                self.assertGreaterEqual(len(failures),2)
                self.assertEqual(boundary._owner_state,'RETAINED_UNKNOWN')
                self.assertFalse(boundary._evidence_settled)
                self.assertEqual(cleanup_calls,[])
                self.assertEqual(release_calls,[])
                self.assertIs(resource,original_resource[0])
                self.assertIs(handles,original_resource[1])
                self.assertTrue(workspace.is_dir());self.assertTrue(all(not handle.closed for handle in handles))
                with self.assertRaisesRegex(RuntimeError,'owners_unsettled'):self.session.cleanup()
        finally:
            await self.session.aclose_queries()
        self.assertFalse(workspace.exists());self.assertTrue(all(handle.closed for handle in handles))
        self.assertEqual(boundary._owner_state,'DETACHED')
        self.assertFalse(self.session._attempt_resources or self.session._owners)

    async def test_same_trial_losing_claim_cannot_clean_active_preparation(self):
        from improvement_trial_runner import TrialRunner
        await self.session.verify_native()
        admitted=await asyncio.to_thread(self.admission.admit_qualification,self.session,self.session.principal,self.public)
        trials=self.admission.trials;workspace=trials.workspace
        prepare,cleanup,release,claim=workspace.prepare,workspace.cleanup,workspace.release_execution,trials.claim
        started,proceed=threading.Event(),threading.Event()
        cleanup_calls=[];release_calls=[];claims=[];receipts=[]
        def held_prepare(*args):
            receipt=prepare(*args);receipts.append(receipt);started.set();proceed.wait(90);return receipt
        def forbidden_cleanup(*args):
            cleanup_calls.append(args);raise OSError('RED guard preserves active prepared workspace')
        def forbidden_release(handles):
            release_calls.append(handles);raise OSError('RED guard preserves original active lifetime')
        def losing_claim(*args,**kwargs):
            try:return claim(*args,**kwargs)
            except IM.ConflictError as error:claims.append(str(error));raise
        first=TrialRunner.for_qualification(self.session,self.admission)
        second=TrialRunner.for_qualification(self.session,self.admission)
        with patch.object(workspace,'prepare',held_prepare):
            task=asyncio.create_task(first.run_qualification(self.session.principal,admitted.trial_id))
            try:
                await self.wait_event(started)
                key=(admitted.trial_id,1);resource=self.session._attempt_resources[key]
                handles=resource['lifetime'][0];path=Path(receipts[0]['path'])
                self.assertNotIn(key,self.session._queries)
                with patch.object(workspace,'cleanup',forbidden_cleanup),patch.object(workspace,'release_execution',forbidden_release), \
                        patch.object(trials,'claim',losing_claim):
                    with self.assertRaises(Exception):await second.run_qualification(self.session.principal,admitted.trial_id)
                print('FIX2_LOSING_CLAIM',json.dumps(dict(claim_refusals=claims,
                    cleanup_calls=len(cleanup_calls),release_calls=len(release_calls),workspace=str(path),
                    handles=[id(handle) for handle in handles],closed=[handle.closed for handle in handles],
                    original_task_done=task.done(),query_bound=key in self.session._queries)),flush=True)
                self.assertEqual(len(claims),1)
                self.assertEqual(cleanup_calls,[]);self.assertEqual(release_calls,[])
                self.assertIs(self.session._attempt_resources[key],resource)
                self.assertIs(resource['lifetime'][0],handles)
                self.assertTrue(path.is_dir());self.assertTrue(all(not handle.closed for handle in handles))
                self.assertFalse(task.done())
            finally:
                proceed.set();result=await task
        self.assertEqual(self.count('native_qualification_attempt'),1)
        self.assertEqual(self.count('native_qualification_query_result'),1)
        self.assertEqual(self.read_result(result),result)
        self.assertFalse(path.exists());self.assertTrue(all(handle.closed for handle in handles))
        self.assertFalse(self.session._attempt_resources)

    async def test_same_trial_competing_replay_cannot_acquire_active_finalizer(self):
        from improvement_trial_runner import TrialRunner
        for index,replay in enumerate((False,True)):
            with self.subTest(retained_replay=replay):
                if index:await self.reopen()
                await self.session.verify_native()
                admitted=await asyncio.to_thread(self.admission.admit_qualification,self.session,self.session.principal,self.public)
                trials=self.admission.trials;workspace=trials.workspace
                first=TrialRunner.for_qualification(self.session,self.admission)
                second=TrialRunner.for_qualification(self.session,self.admission)
                if replay:
                    with patch.object(workspace,'cleanup',side_effect=OSError('retain committed finalizer')):
                        with self.assertRaises(Exception):await first.run_qualification(self.session.principal,admitted.trial_id)
                cleanup,release=workspace.cleanup,workspace.release_execution
                started,proceed=threading.Event(),threading.Event();cleanup_calls=[];release_calls=[]
                def held_cleanup(*args):
                    cleanup_calls.append(args)
                    if len(cleanup_calls)>1:raise OSError('RED guard blocks duplicate finalizer deletion')
                    started.set();proceed.wait(90);return cleanup(*args)
                def guarded_release(handles):
                    release_calls.append(handles)
                    if not proceed.is_set():raise OSError('RED guard blocks rival lifetime release')
                    return release(handles)
                with patch.object(workspace,'cleanup',held_cleanup),patch.object(workspace,'release_execution',guarded_release):
                    task=asyncio.create_task(first.run_qualification(self.session.principal,admitted.trial_id))
                    try:
                        await self.wait_event(started)
                        key=(admitted.trial_id,1);resource=self.session._attempt_resources[key]
                        handles=resource['lifetime'][0];path=Path(self.session._queries[key]['receipt']['path'])
                        before_closed=[handle.closed for handle in handles]
                        self.assertEqual(self.count('native_qualification_query_evidence'),1)
                        self.assertEqual(trials.get(self.session.principal,admitted.trial_id)['status'],'completed')
                        with self.assertRaises(Exception):await second.run_qualification(self.session.principal,admitted.trial_id)
                        print('FIX2_ACTIVE_FINALIZER',json.dumps(dict(retained_replay=replay,
                            cleanup_calls=len(cleanup_calls),release_calls=len(release_calls),
                            handles=[id(handle) for handle in handles],closed=[handle.closed for handle in handles],
                            original_task_done=task.done(),workspace=str(path))),flush=True)
                        self.assertEqual(len(cleanup_calls),1);self.assertEqual(release_calls,[])
                        self.assertIs(self.session._attempt_resources[key],resource)
                        self.assertIs(resource['lifetime'][0],handles)
                        self.assertEqual([handle.closed for handle in handles],before_closed)
                        if not replay:self.assertTrue(all(not handle.closed for handle in handles))
                        self.assertTrue(path.is_dir());self.assertFalse(task.done())
                    finally:
                        proceed.set();result=await task
                self.assertEqual(len(cleanup_calls),1);self.assertEqual(len(release_calls),1)
                self.assertEqual(self.count('native_qualification_attempt'),1)
                self.assertEqual(self.count('native_qualification_query_result'),1)
                self.assertEqual(self.read_result(result),result)
                self.assertFalse(path.exists());self.assertTrue(all(handle.closed for handle in handles))
                self.assertFalse(self.session._attempt_resources or self.session._pending_proofs)

    async def test_cancel_after_stage_close_saves_only_cleanup_diagnostic(self):
        trials=self.admission.trials
        original=trials.workspace.cleanup;started,release=threading.Event(),threading.Event()
        def held(*args):started.set();release.wait(90);return original(*args)
        with patch.object(trials.workspace,'cleanup',held):
            task=asyncio.create_task(self.execute())
            try:
                await self.wait_event(started)
                context=next(iter(self.session._queries.values()))
                self.assertEqual(self.count('native_qualification_query_evidence'),1)
                self.assertEqual(trials.ledger.get(context['link']['call_id'])['status'],'ok')
                task.cancel();await asyncio.sleep(.005);task.cancel()
            finally:release.set()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertIs(self.session._pending_proofs.get((context['identifier'],1)),context)
        self.session.close();await self.session.aclose_queries()
        self.assertEqual(self.count('native_qualification_query_cleanup_diagnostic'),1)
        self.assertEqual(self.count('native_qualification_query_result'),0)
        self.assertEqual(self.count('native_qualification_attempt'),1)
        self.assertFalse(self.session._pending_proofs or self.session._attempt_resources or self.session._owners)

    async def test_committed_stage_cleanup_failure_replays_only_existing_proof(self):
        trials=self.admission.trials;original=trials.workspace.cleanup
        with patch.object(trials.workspace,'cleanup',side_effect=OSError('post-stage cleanup failed')):
            with self.assertRaises(Exception):await self.execute()
        context=next(iter(self.session._queries.values()));key=(context['identifier'],1)
        self.assertEqual(self.count('native_qualification_query_evidence'),1)
        self.assertIs(self.session._pending_proofs.get(key),context)
        self.assertIn(key,self.session._attempt_resources)
        self.assertIsNone(context['cleanup'])
        call_id=context['link']['call_id']
        result=await self.execute()
        self.assertEqual(result.call_id,call_id)
        self.assertEqual(self.count('native_qualification_attempt'),1)
        self.assertEqual(self.count('native_qualification_query_evidence'),1)
        self.assertEqual(self.read_result(result),result)
        self.assertFalse(self.session._pending_proofs or self.session._attempt_resources)

    async def test_uncommitted_stage_never_retains_finalization_proof(self):
        original=self.session.assets._event
        def refuse(connection,principal,key,operation,request,result):
            if operation=='native_qualification_query_evidence':raise OSError('stage transaction rolled back')
            return original(connection,principal,key,operation,request,result)
        with patch.object(self.session.assets,'_event',refuse):
            with self.assertRaises(Exception):await self.execute()
        context=next(iter(self.session._queries.values()))
        self.assertIsNotNone(context['stage'])
        self.assertEqual(self.count('native_qualification_query_evidence'),0)
        self.assertFalse(self.session._pending_proofs)
        await self.session.aclose_queries()
        self.assertEqual(self.count('native_qualification_query_cleanup_diagnostic'),0)
        self.assertEqual(self.count('native_qualification_query_result'),0)

    async def test_direct_runner_post_thread_initial_and_replay_handoffs_refuse(self):
        import improvement_trial_runner as runner_module
        from improvement_qualification_results import QualificationQueryResult
        for index,(replay,expiry) in enumerate(((False,False),(True,False),(False,True),(True,True),('pending',False),('pending',True))):
            with self.subTest(replay=replay,expiry=expiry):
                if index:await self.reopen()
                await self.session.verify_native()
                admitted=await asyncio.to_thread(self.admission.admit_qualification,self.session,self.session.principal,self.public)
                runner=runner_module.TrialRunner.for_qualification(self.session,self.admission)
                if replay == 'pending':
                    append=self.session.assets._event
                    def refuse_final(connection,principal,key,operation,request,result):
                        if operation=='native_qualification_query_result':raise OSError('owned pending-proof fixture')
                        return append(connection,principal,key,operation,request,result)
                    with patch.object(self.session.assets,'_event',refuse_final):
                        with self.assertRaises(OSError):await runner.run_qualification(self.session.principal,admitted.trial_id)
                    self.assertEqual(len(self.session._pending_proofs),1)
                elif replay:await runner.run_qualification(self.session.principal,admitted.trial_id)
                original=runner_module._settled_call;removed={};clock=[];answers=[]
                async def after_thread(callback,*args,**kwargs):
                    answer=await original(callback,*args,**kwargs)
                    if type(answer) is QualificationQueryResult:
                        answers.append(answer)
                        if expiry:
                            clock.append(patch.object(QS.time,'time',return_value=self.session._scope['deadline_at']+1))
                            clock[-1].start()
                        else:
                            removed.update(registry.REVIEWED_QUALIFICATION_CANDIDATES)
                            registry.REVIEWED_QUALIFICATION_CANDIDATES.clear()
                    return answer
                try:
                    with patch.object(runner_module,'_settled_call',after_thread):
                        with self.assertRaises(PermissionError):
                            await runner.run_qualification(self.session.principal,admitted.trial_id)
                finally:
                    for item in reversed(clock):item.stop()
                    registry.REVIEWED_QUALIFICATION_CANDIDATES.update(removed)
                self.assertEqual(len(answers),1)
                result=answers[0]
                self.assertEqual(self.read_result(result),result)
                self.assertEqual(self.count('native_qualification_attempt'),1)
                self.assertEqual(self.count('native_qualification_query_result'),1)
                print('FIX1_DIRECT_HANDOFF',json.dumps(dict(replay=replay,expiry=expiry,refused=True,
                    historical_call=result.call_id,attempts=1,finals=1)),flush=True)

    async def test_append_failure_retains_pending_proof_retry_without_query(self):
        original=self.session.assets._event
        failed=[]
        def append(connection,principal,key,operation,request,result):
            if operation=='native_qualification_query_result' and not failed:
                failed.append(True);raise OSError('fixture immutable append failure')
            return original(connection,principal,key,operation,request,result)
        with patch.object(self.session.assets,'_event',append):
            with self.assertRaisesRegex(OSError,'append failure'):await self.execute()
        self.assertEqual(len(self.session._pending_proofs),1)
        self.assertEqual(self.count('native_qualification_query_result'),0)
        context=next(iter(self.session._queries.values()))
        self.assertIsNotNone(context['cleanup'])
        result=await self.execute()
        self.assertEqual(self.count('native_qualification_attempt'),1)
        self.assertEqual(self.count('native_qualification_query_result'),1)
        self.assertFalse(self.session._pending_proofs)
        self.assertEqual(self.read_result(result),result)

    async def test_revocation_after_final_offloop_check_cannot_publish_result(self):
        import improvement_qualification_results as results
        original=results._write;removed={}
        def revoke(assets,principal,value):
            envelope=original(assets,principal,value)
            if type(value) is dict and 'result' in value:
                removed.update(registry.REVIEWED_QUALIFICATION_CANDIDATES)
                registry.REVIEWED_QUALIFICATION_CANDIDATES.clear()
            return envelope
        try:
            with patch.object(results,'_write',revoke):
                with self.assertRaises(PermissionError):await self.execute()
            self.assertEqual(self.count('native_qualification_query_result'),0)
            self.assertEqual(len(self.session._pending_proofs),1)
        finally:registry.REVIEWED_QUALIFICATION_CANDIDATES.update(removed)
        result=await self.execute()
        self.assertEqual(self.count('native_qualification_attempt'),1)
        self.assertEqual(self.read_result(result),result)

    async def test_cold_result_after_workspace_removal_authenticates_same_call(self):
        result=await self.execute()
        context=self.session._queries[(result.subject_id,1)]
        self.assertFalse(Path(context['receipt']['path']).exists())
        call=self.admission.trials.ledger.get(result.call_id)
        self.assertEqual(call['engine_at'],result.engine_at)
        self.session.close()
        assets,principal=self.session.open_forensic(self.session.root,expected_run_hash=self.session.run_hash)
        from improvement_qualification_results import QualificationQueryResults
        with patch.object(QS,'observe_release',side_effect=AssertionError('cold source scan')),patch.object(QS,'_runtime_identity',side_effect=AssertionError('cold runtime')):
            self.assertEqual(QualificationQueryResults.read_stored(assets,principal,kind='trial',subject_id=result.subject_id,
                attempt=1,expected_run_hash=self.session.run_hash),result)
        for reader in (self.admission.trials.read_result,self.admission.trials.read_artifact,self.admission.trials.read_receipt):
            with self.assertRaises(PermissionError):reader(self.session.principal,result.subject_id,1)

    async def test_cold_missing_trace_decision_cleanup_or_sql_join_refuses(self):
        result=await self.execute()
        from improvement_qualification_results import _stored,_read,_FINAL,_identity
        with closing(self.session.assets.store._conn()) as connection:
            trace=connection.execute('SELECT blob_hashes_json FROM improvement_trial_observations LIMIT 1').fetchone()[0]
            decision=json.loads(connection.execute("SELECT result_json FROM improvement_events WHERE operation='native_image_decision' LIMIT 1").fetchone()[0])
            final,_=_stored(self.session.assets,self.session.principal,connection,_FINAL,
                _identity(self.session.run_hash,'trial',result.subject_id,1))
        digests=[json.loads(trace)[0],decision['blob_hashes'][0],final['cleanup']['blob_hashes'][0]]
        for digest in digests:
            path=self.session.assets.blobs._path(self.session.principal.brain_id,digest);raw=path.read_bytes()
            try:
                path.unlink()
                with self.assertRaises(Exception):self.read_result(result)
            finally:path.write_bytes(raw)
        with self.session.assets.store._Tx(self.session.assets.store) as connection:
            connection.execute('UPDATE agent_calls SET engine_at=engine_at+1 WHERE id=?',(result.call_id,))
        with self.assertRaises(Exception):self.read_result(result)
        with self.session.assets.store._Tx(self.session.assets.store) as connection:
            connection.execute('UPDATE agent_calls SET engine_at=? WHERE id=?',(result.engine_at,result.call_id))
        self.assertEqual(self.read_result(result),result)

    async def test_close_during_admission_keeps_host_owner_until_settled(self):
        await self.session.verify_native()
        original=self.admission.admit_qualification;started,release=threading.Event(),threading.Event()
        def held(*args):started.set();release.wait(90);return original(*args)
        with patch.object(self.admission,'admit_qualification',held):
            task=asyncio.create_task(self.execute())
            try:
                await self.wait_event(started)
                self.session.close();task.cancel();task.cancel()
                await asyncio.sleep(.025)
                self.assertIn(task,self.session._host_operations)
                with self.assertRaises(RuntimeError):self.session.cleanup()
            finally:release.set()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertFalse(self.session._host_operations or self.session._owners)
        self.assertEqual(self.count('native_qualification_attempt'),0)

    async def test_other_attempt_host_owner_survives_one_attempt_publication(self):
        await self.session.verify_native()
        original=self.admission.admit_qualification;started,release=threading.Event(),threading.Event()
        def held(session,principal,public):
            admitted=original(session,principal,public)
            if public['repeat']==2:started.set();release.wait(90)
            return admitted
        with patch.object(self.admission,'admit_qualification',held):
            second=asyncio.create_task(self.execute({**self.public,'event_key':'second-host','repeat':2}))
            try:
                await self.wait_event(started)
                first=await self.execute()
                self.assertEqual(self.read_result(first),first)
                self.assertIn(second,self.session._host_operations)
                with self.assertRaises(RuntimeError):self.session.cleanup()
            finally:release.set()
            with self.assertRaises(asyncio.CancelledError):await second
        self.assertFalse(self.session._host_operations)
        with closing(self.session.assets.store._conn()) as connection:
            self.assertEqual([row[0] for row in connection.execute('SELECT status FROM agent_calls ORDER BY id')],['refunded','ok'])

    async def test_repeated_cancel_preparation_retains_actual_lifetime_until_cleanup(self):
        from improvement_sandbox import WorkspaceCleanupError
        await self.session.verify_native()
        trials=self.admission.trials
        prepare,cleanup=trials.workspace.prepare,trials.workspace.cleanup
        started,release=threading.Event(),threading.Event();failures=[]
        def held(*args):
            receipt=prepare(*args);started.set();release.wait(90);return receipt
        def failed_cleanup(*args):
            if not failures:failures.append(True);raise OSError('fixture cleanup incomplete')
            return cleanup(*args)
        try:
            with patch.object(trials.workspace,'prepare',held),patch.object(trials.workspace,'cleanup',failed_cleanup):
                task=asyncio.create_task(self.execute())
                try:
                    await self.wait_event(started)
                    task.cancel();task.cancel();await asyncio.sleep(.01);task.cancel()
                    self.assertIn(task,self.session._host_operations)
                finally:release.set()
                with self.assertRaises(WorkspaceCleanupError):await task
            self.assertFalse(self.session._owners)
            self.assertEqual(self.count('native_qualification_attempt'),0)
            with patch.object(self.session._temporary,'cleanup',side_effect=AssertionError('root deletion must remain unreachable')):
                with self.assertRaisesRegex(RuntimeError,'owners_unsettled'):self.session.cleanup()
        finally:
            await asyncio.to_thread(trials.cleanup_terminal,self.session.principal)
            await self.session.aclose_queries()

    async def reopen(self):
        await self.session.aclose_queries();self.session.cleanup()
        self.session=self.qualification=QS.QualificationSession.open(pin=self.config,endpoint='http://127.0.0.1:15432',
            expected_fingerprint=self.candidate['fingerprint'],lifetime_seconds=300,maximum_queries=1)
        self.fixture,self.admission,self.public=owned_admission(self,self.session)

    async def test_config_import_environment_is_restored_but_later_drift_refuses(self):
        target=self.source / 'improvement_worker.py'
        target.write_text(target.read_text(encoding='utf-8').replace(
            'if technical: profile.bind_qualification_runtime(native_session, user_prompt=prompt)',
            "if technical:\n            os.environ['PYTHONUTF8']='1'\n            profile.bind_qualification_runtime(native_session, user_prompt=prompt)"),encoding='utf-8')
        self.guardian['source']['files'][target.name]=hashlib.sha256(target.read_bytes()).hexdigest()
        await self.reopen()
        with self.assertRaises(Exception):await self.execute()
        context=next(iter(self.session._queries.values()))
        self.assertIsNone(self.admission.trials.ledger.get(context['link']['call_id'])['engine_at'])
        self.assertEqual(self.count('native_qualification_query_result'),0)
        self.assertEqual(context['boundary']._guardian._allowed,{'adapter_version','auth_status'})

    async def test_closed_pending_proof_saves_cleanup_diagnostics_without_query(self):
        original=self.session.assets._event
        def append(connection,principal,key,operation,request,result):
            if operation=='native_qualification_query_result':raise OSError('fixture final append failure')
            return original(connection,principal,key,operation,request,result)
        with patch.object(self.session.assets,'_event',append):
            with self.assertRaises(OSError):await self.execute()
        self.assertTrue(self.session._pending_proofs)
        await self.session.aclose_queries()
        self.assertFalse(self.session._pending_proofs or self.session._attempt_resources or self.session._owners)
        self.assertEqual(self.count('native_qualification_query_cleanup_diagnostic'),1)
        self.assertEqual(self.count('native_qualification_query_result'),0)
        with self.assertRaises(PermissionError):await self.execute()
        self.assertEqual(self.count('native_qualification_attempt'),1)

    async def test_repeated_cancel_at_sdk_input_receive_and_drain_keeps_native_ownership(self):
        for index,phase in enumerate(('sdk','input','receive','drain')):
            with self.subTest(phase=phase):
                if index:await self.reopen()
                root=self.session.root
                (root / ('hold-'+phase)).write_bytes(b'owned fixture gate')
                task=asyncio.create_task(self.execute())
                try:
                    async with asyncio.timeout(90):
                        while not (root / ('started-'+phase)).exists():await asyncio.sleep(.005)
                    self.assertIn(task,self.session._host_operations)
                    task.cancel();await asyncio.sleep(.005);task.cancel()
                    with patch.object(self.session._temporary,'cleanup',side_effect=AssertionError('no root deletion during native close')):
                        with self.assertRaises(RuntimeError):self.session.cleanup()
                finally:(root / ('release-'+phase)).write_bytes(b'owned fixture release')
                with self.assertRaises(asyncio.CancelledError):await task
                await self.session.aclose_queries()
                self.assertFalse(self.session._owners or self.session._host_operations or self.session._attempt_resources)
                self.assertEqual(self.count('native_qualification_query_result'),0)
                context=next(iter(self.session._queries.values()))
                call=self.admission.trials.ledger.get(context['link']['call_id'])
                self.assertEqual(call['engine_at'] is None,phase=='sdk')
                self.assertTrue(context['boundary']._guardian.closed)

    async def test_repeated_cancel_during_durable_allow_retains_original_writer(self):
        from improvement_native_decisions import NativeImageDecisionStore
        original=NativeImageDecisionStore.persist;started,release=threading.Event(),threading.Event()
        def held(store,principal,joined,**kwargs):
            answer=original(store,principal,joined,**kwargs)
            if joined['purpose']=='query':started.set();release.wait(90)
            return answer
        with patch.object(NativeImageDecisionStore,'persist',held):
            task=asyncio.create_task(self.execute())
            try:
                await self.wait_event(started)
                task.cancel();await asyncio.sleep(.005);task.cancel()
                with self.assertRaises(RuntimeError):self.session.cleanup()
                self.assertIn(task,self.session._host_operations)
            finally:release.set()
            with self.assertRaises(asyncio.CancelledError):await task
        await self.session.aclose_queries()
        self.assertFalse(self.session._owners or self.session._attempt_resources)
        self.assertEqual(self.count('native_qualification_query_result'),0)

    async def test_repeated_cancel_during_final_append_settles_without_relaunch(self):
        original=self.session.assets._event;started,release=threading.Event(),threading.Event()
        def held(connection,principal,key,operation,request,result):
            answer=original(connection,principal,key,operation,request,result)
            if operation=='native_qualification_query_result':started.set();release.wait(90)
            return answer
        with patch.object(self.session.assets,'_event',held):
            task=asyncio.create_task(self.execute())
            try:
                await self.wait_event(started)
                task.cancel();await asyncio.sleep(.005);task.cancel()
                self.assertIn(task,self.session._host_operations)
                self.assertTrue(self.session._pending_proofs)
            finally:release.set()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertFalse(self.session._host_operations or self.session._pending_proofs)
        result=await self.execute()
        self.assertEqual(self.count('native_qualification_attempt'),1)
        self.assertEqual(self.read_result(result),result)


class QualificationQueryBoundaryTests(unittest.TestCase):
    def test_actual_observed_closure_contains_result_consumer_without_registration(self):
        from improvement_claude import profile_hash, PROFILE_SOURCES
        import improvement_native_release as release
        from test_improvement_native_sdk import pin
        from test_improvement_native_release import NativeReleaseTests
        before=(copy.deepcopy(registry.REVIEWED_QUALIFICATION_CANDIDATES),copy.deepcopy(registry.REVIEWED_RELEASES))
        config=pin();config.update(profile_hash=profile_hash(),profile_version='claude-owned-images-v3')
        # Portable source-closure observation uses declared inert wheel bytes,
        # never the host's unrelated installed RECORD inventory or Win32 runtime.
        # The production inventory/RECORD validator still reads every fixture.
        fixture=NativeReleaseTests('runTest');fixture.setUp();self.addCleanup(fixture.doCleanups)
        local={path.stem for path in SERVER.rglob('*.py')}
        external={name.split('.')[0] for path in SERVER.rglob('*.py')
            for name in release._imports(path.read_bytes(),path.relative_to(SERVER).as_posix())
            if name.split('.')[0] not in local | set(sys.stdlib_module_names) | set(sys.builtin_module_names)}
        _,modules=release._catalog(fixture.packages)
        fixture.wheel('qualification-source-fixture','1.0',
            {name+'.py':b'# Inert inventory fixture; never imported.\n' for name in external-set(modules)})
        seeds=tuple(sorted((set(PROFILE_SOURCES)|set(release._SEEDS))-{release._AUTHORITY}))
        sources,imports=release._inventory(SERVER,fixture.packages,seeds,sdk_version=config['sdk_version'])
        self.assertEqual(release._fingerprint({name:sources[name] for name in PROFILE_SOURCES}),config['profile_hash'])
        self.assertIn('qualification_source_fixture-1.0.dist-info/RECORD',imports)
        for name in ('improvement_qualification_results.py','improvement_qualification_session.py','improvement_trial_admission.py',
                'improvement_trial_runner.py','improvement_trials.py','improvement_native_parent.py','improvement_native_profile.py'):
            self.assertEqual(sources[name],hashlib.sha256((SERVER/name).read_bytes()).hexdigest())
        self.assertEqual((registry.REVIEWED_QUALIFICATION_CANDIDATES,registry.REVIEWED_RELEASES),before)

    def test_default_profile_and_startup2_refuse_identical_dummy_query(self):
        from test_improvement_qualification_protocol import startup
        from improvement_native_protocol import validate_startup2
        from improvement_native_profile import NativeProfileBinding
        from improvement_native_sdk import NativeInvocationSet
        packet=startup('trial')
        with self.assertRaises(ValueError):validate_startup2(packet)
        ordinary={key:value for key,value in packet.items() if key!='qualification'}
        ordinary.update(version=2,type='startup2')
        with self.assertRaises(ValueError):validate_startup2(ordinary)
        with self.assertRaises(ValueError):NativeInvocationSet(packet['request']['config_pin'],image_channels={},
            emit_dispatch=None,environment=packet['environment'],cwd=packet['request']['receipt']['path'],source_policy_hash='c'*64)
        with self.assertRaises(ValueError):NativeProfileBinding(object(),kind='trial',identity={},data_hash='c'*64,
            user_prompt='fixture',environment=packet['environment'],query_policy={})

    def test_startup3_v1_or_tampered_binding_cannot_launch_query(self):
        from test_improvement_qualification_protocol import startup,digest
        from improvement_qualification_protocol import validate_startup3
        from improvement_native_worker import NativeWorkerSessionV2
        packet=startup('trial')
        self.assertEqual(validate_startup3(packet),packet)
        with self.assertRaises(ValueError):NativeWorkerSessionV2.from_startup3(packet,namespace='trial')
        q=packet['qualification'];link=q['attempt_link']
        binding=dict(version=1,domain='qualification',supported=False,account_ready=False,
            preflight_hash='1'*64,**{key:link[key] for key in ('run_hash','kind','subject_id','attempt','request_hash',
                'workspace_hash','materialization_hash','engine_config_hash')})
        binding['authority_hash']=digest(binding)
        q.update(version=2,preflight_hash=binding['preflight_hash'],query_binding=binding)
        link['capability_hash']=packet['request']['capability_hash']=binding['authority_hash']
        self.assertEqual(validate_startup3(packet),packet)
        for name,value in (('supported',True),('account_ready',True),('request_hash','f'*64),('authority_hash','e'*64)):
            changed=copy.deepcopy(packet);changed['qualification']['query_binding'][name]=value
            with self.subTest(name=name),self.assertRaises(ValueError):validate_startup3(changed)
        # Pure parser data still has no adoption/runtime/private channel authority.
        owner=NativeWorkerSessionV2.from_startup3(packet,namespace='trial')
        from improvement_native_profile import NativeProfileBinding
        with self.assertRaises(TypeError):NativeProfileBinding.from_qualification_worker(owner,kind='trial',
            identity={},data_hash='c'*64,user_prompt='fixture',query_policy={})


if __name__ == '__main__': unittest.main()
