"""Disposable Session authority and native preflight; synthetic candidates only."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import copy
from contextlib import closing
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import improvement_native_qualifications as registry
import improvement_qualification_session as qs
import improvement_native_parent as parent
import improvement_native_transport as transport
from test_improvement_native_sdk import pin
from test_improvement_native_transport_v2 import fixture_manifest
import test_improvement_native_transport_v2 as kernel


class QualificationNativeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.pin = pin(); self.pin['profile_version'] = 'claude-owned-images-v3'
        self.runtime = dict(platform=sys.platform, cli_hash=self.pin['cli_hash'],
            sdk_version=self.pin['sdk_version'], profile_hash=self.pin['profile_hash'], managed_policy='absent')
        self.fingerprint, self.review = 'a' * 64, 'b' * 64
        self.release = dict(version=1, fingerprint=self.fingerprint, content={'fixture': 'synthetic-candidate'},
            manifests={kind: fixture_manifest(kind) for kind in ('guardian', 'trial')})
        self.key = (sys.platform, *(self.pin[k] for k in ('cli_version', 'cli_hash', 'sdk_version',
            'profile_version', 'profile_hash')), self.fingerprint)
        # Explicit fixed synthetic candidate/runtime/bootstrap metadata seams.
        # Session, encrypted GoalStore/CallLedger and Guardian construction are real.
        for seam in (patch.object(registry, 'REVIEWED_QUALIFICATION_CANDIDATES', {self.key: self.review}),
                patch.object(qs, '_runtime_identity', return_value=self.runtime),
                patch.object(qs, 'observe_release', side_effect=lambda _: copy.deepcopy(self.release))):
            seam.start(); self.addCleanup(seam.stop)
        self.session = qs.QualificationSession.open(pin=self.pin, endpoint='http://127.0.0.1:15432',
            expected_fingerprint=self.fingerprint, lifetime_seconds=300, maximum_queries=4)
        self.addAsyncCleanup(self.cleanup_session)

    async def cleanup_session(self):
        if hasattr(self.session, 'aclose_native'): await self.session.aclose_native()
        self.session.cleanup()

    async def test_live_authority_rejects_review_expiry_closed_and_foreign_assets_before_acquisition(self):
        session = self.session
        with patch.object(transport, '_host_windows', side_effect=AssertionError('early native API')):
            with patch.object(registry, 'REVIEWED_QUALIFICATION_CANDIDATES', {}):
                with self.assertRaises(PermissionError): session._assert_native_current()
            with patch.object(registry, 'REVIEWED_QUALIFICATION_CANDIDATES', {self.key: 'c' * 64}):
                with self.assertRaises(PermissionError): session._assert_native_current()
            with patch.object(qs.time, 'time', return_value=session.scope()['deadline_at']):
                with self.assertRaisesRegex(PermissionError, 'expired'): session._assert_native_current()
            for name, value in (('assets', object()), ('principal', object()), ('_root', session.root.parent),
                    ('run_hash', 'f' * 64), ('_pin', {**self.pin, 'model': 'foreign'})):
                with patch.object(session, name, value):
                    with self.assertRaises(Exception): session._assert_native_current()
            session.close()
            with self.assertRaisesRegex(PermissionError, 'closed'): await session.verify_native()
        self.assertFalse(session._owners)

    async def test_launch_reobserves_runtime_and_full_candidate_content_before_native_acquisition(self):
        scratch = self.session.root / 'preflight'; scratch.mkdir()
        for changed in ({**self.release, 'fingerprint': 'f' * 64},
                {**self.release, 'content': {'drift': True}},
                {**self.release, 'manifests': {}}):
            with patch.object(qs, 'observe_release', return_value=changed):
                with self.assertRaisesRegex(PermissionError, 'source_drift'):
                    self.session._preflight_launch(scratch)
        with patch.object(qs, '_runtime_identity', return_value={**self.runtime, 'managed_policy': 'present'}):
            with self.assertRaisesRegex(PermissionError, 'runtime_drift'):
                self.session._preflight_launch(scratch)
        self.assertFalse(self.session._owners)

    async def test_close_during_static_runtime_recheck_cannot_leave_authority_current(self):
        def delayed(pin):
            self.session.close()
            return self.runtime
        with patch.object(qs,'_runtime_identity',side_effect=delayed):
            with self.assertRaisesRegex(PermissionError,'closed'):self.session._assert_native_current()

    async def test_review_replacement_during_static_recheck_cannot_leave_authority_current(self):
        original=registry.REVIEWED_QUALIFICATION_CANDIDATES
        self.addCleanup(setattr,registry,'REVIEWED_QUALIFICATION_CANDIDATES',original)
        def delayed(pin):
            registry.REVIEWED_QUALIFICATION_CANDIDATES={}
            return self.runtime
        with patch.object(qs,'_runtime_identity',side_effect=delayed):
            with self.assertRaisesRegex(PermissionError,'unreviewed'):self.session._assert_native_current()

    async def test_qualification_parent_cannot_enter_production_adapter_or_query_paths_or_replay(self):
        boundary = parent.NativeParentBoundary.for_qualification(self.session)
        with self.assertRaisesRegex(PermissionError, 'product_forbidden'): await boundary.verify(object())
        with self.assertRaisesRegex(PermissionError, 'product_forbidden'):
            await anext(boundary.execute('trial', {}, {}, adapter=object(), workspace_root='x', brain_id='x',
                before_engine_start=None, system_prompt='', tool_policy='pinned_skill', on_closing_observations=None))
        with self.assertRaisesRegex(PermissionError, 'already_used'): await self.session.verify_native()
        with self.assertRaisesRegex(PermissionError, 'already_used'):
            parent.NativeParentBoundary.for_qualification(self.session)
        with self.assertRaises(TypeError): qs.QualificationPreflight(object(), {})

    async def test_technical_auth_is_diagnostic_preserved_and_subscription_contamination_refuses(self):
        from improvement_qualification_protocol import validate_technical_observation
        observed = dict(platform='win32', managed_policy='absent', cli_version=self.pin['cli_version'],
            **{name:self.pin[name] for name in ('cli_hash','sdk_version','profile_hash')},
            auth=dict(logged_in=False, method='unknown-fixture-label', provider=None, plan=None))
        value = validate_technical_observation(observed, pin=self.pin)
        self.assertEqual(value,observed); self.assertIsNot(value,observed)
        for change in ({'method':'claude.ai'}, {'plan':'max'}):
            with self.assertRaises(PermissionError): validate_technical_observation(
                {**observed,'auth':{**observed['auth'],**change}},pin=self.pin)
        for name in ('platform','managed_policy','cli_hash','cli_version','sdk_version','profile_hash'):
            with self.assertRaises(ValueError): validate_technical_observation({**observed,name:'changed'},pin=self.pin)

    async def test_startup3_and_malformed_mixed_routes_never_emit_v1_in_either_entrypoint(self):
        for name in ('improvement_worker.py','improvement_operation_worker.py'):
            for value in ({'version':3,'type':'startup3'}, {'version':2,'type':'startup3'},
                    {'version':3,'type':'startup2'}, {'version':3,'type':'request'}):
                child = await asyncio.to_thread(subprocess.run,
                    [sys.executable,'-I','-S','-B',str(SERVER/name)], input=json.dumps(value).encode()+b'\n',
                    capture_output=True, timeout=10, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                self.assertEqual(child.returncode,1); self.assertEqual(child.stdout,b'')

    @unittest.skipUnless(os.name == 'nt', 'Guardian capability fixture uses Windows manifests')

    async def test_session_consumes_real_parent_owner_before_first_native_acquisition(self):
        # The fixture is already a valid DB/run and actual Guardian, not a symbol assertion.
        with closing(self.session.assets.store._conn()) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM improvement_events').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM agent_calls').fetchone()[0], 0)
        async def persist(joined): raise AssertionError('fixture construction must not persist')
        probe = transport.GuardianSessionV2(self.release['manifests']['guardian'],
            dict(version=1, bootstrap=self.release['manifests']['trial'], scratch=r'C:\scratch'),
            image_policy=dict(version=1, path=self.pin['cli_path'], sha256=self.pin['cli_hash']),
            fences=[r'C:\scratch\a.lock', r'C:\scratch\b.lock'], launch_nonce='1'*64,
            invocations=[dict(purpose=k, nonce=str(i+2)*64) for i,k in enumerate(('adapter_version','auth_status'))],
            persist_before_allow=persist)
        self.assertIsNone(probe._api); await probe.aclose(); self.assertTrue(probe.closed)
        acquired = []
        def acquisition(owner):
            self.assertIn(owner, self.session._owners)
            self.assertIs(self.session._native_boundaries[owner]._guardian, owner)
            self.assertEqual(owner._startup_seed['qualification']['run_hash'], self.session.run_hash)
            acquired.append(owner)
            raise OSError('engineering_before_native_acquisition')
        original = transport.GuardianSessionV2._prepare_guards
        with patch.object(transport.GuardianSessionV2, '_prepare_guards', acquisition):
            with self.assertRaises(OSError): await self.session.verify_native()
        self.assertEqual(len(acquired), 1)
        self.assertTrue(acquired[0].closed)
        self.assertFalse(self.session._owners)
        with closing(self.session.assets.store._conn()) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM improvement_events WHERE operation='native_preflight_evidence'").fetchone()[0], 1)


# Engineering capture seam: real inert cmd.exe CREATE/image ACK, real SDK
# constructor/_fixed/preflight, synthetic fixed stdout/argument observations.
# This is ownership evidence, never installed selected CLI qualification.
_CAPTURE_FIXTURE = r'''
import builtins,sys,os,asyncio,json,subprocess
from types import SimpleNamespace
original_import=builtins.__import__
class EndOfStream(Exception): pass
class Output:
 def __init__(self,data): self.data=data
 async def receive(self,maximum=65536):
  if self.data is None: raise EndOfStream
  data,self.data=self.data,None
  if not data: raise EndOfStream
  return data
class InertProcess:
 def __init__(self,p,data):self.p=p;self.pid=p.pid;self.stdout=Output(data);self.stderr=Output(b'')
 async def wait(self):return await asyncio.to_thread(self.p.wait)
 async def aclose(self):
  await self.wait()
  for stream in (self.p.stdin,self.p.stdout,self.p.stderr):
   if stream is not None:stream.close()
  self.p._handle.Close()
async def forbidden(*a,**k):raise AssertionError('fixture default opener forbidden')
configured=False
def install(name,*args,**kwargs):
 global configured
 module=original_import(name,*args,**kwargs)
 if name=='improvement_native_sdk' and not configured:
  configured=True
  assert os.environ.get('ANTHROPIC_API_KEY')=='javis-native-qualification-dummy'
  from improvement_native_capture import NativeDebugInvocation as RealCapture
  class FixedCapture:
   def __init__(self,opener,**options):self.options=options;self.owner=None
   async def __aenter__(self):return self
   async def open_process(self,argv,**kwargs):
    data=(b'2.1.99 (inert capture fixture)\n' if argv[1:]==['--version'] else
     json.dumps(dict(loggedIn=False,authMethod='fixture-unknown',apiProvider=None,subscriptionType=None)).encode())
    expected=(None,subprocess.list2cmdline(argv),None,None,True,0x08000006,kwargs['env'],kwargs['cwd'],None)
    def validate(actual):
     assert actual[5]==0x08000006 and actual[6]==kwargs['env'] and actual[7]==kwargs['cwd']
     return self.options['validate_create'](expected)
    async def inert(command,**opts):
     p=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
      creationflags=opts['creationflags'],env=opts['env'],cwd=opts['cwd'])
     return InertProcess(p,data)
    self.owner=RealCapture(inert,**{**self.options,'validate_create':validate})
    await self.owner.__aenter__()
    return await self.owner.open_process([argv[0],'/d','/c','exit 0'],**kwargs)
   async def aclose(self):
    if self.owner is not None:await self.owner.aclose()
  module.NativeDebugInvocation=FixedCapture
  module.NativeInvocationSet._sdk=lambda self:SimpleNamespace(anyio=SimpleNamespace(EndOfStream=EndOfStream,open_process=forbidden))
 return module
builtins.__import__=install
'''


@unittest.skipUnless(os.name == 'nt', 'actual Windows guardian/worker/image kernel capabilities')
class QualificationKernelTests(unittest.IsolatedAsyncioTestCase):
    cleanup_diagnostic = kernel.HostGuardianWindowsTests.cleanup_diagnostic
    persist = kernel.HostGuardianWindowsTests.persist

    async def asyncSetUp(self):
        self.qualification = None
        await kernel.HostGuardianWindowsTests.asyncSetUp(self)
        for name in ('winproc.py', 'improvement_native_worker.py', 'improvement_native_sdk.py', 'improvement_query_dispatch.py',
                'improvement_qualification_protocol.py', 'improvement_qualification_environment.py'):
            shutil.copyfile(SERVER / name, self.source / name)
        # Fixed synthetic static runtime seam inside the guarded fixture bootstrap.
        (self.source / 'improvement_claude.py').write_text(
            'import sys\ndef _runtime_identity(pin):\n return dict(platform=sys.platform, managed_policy="absent",'
            ' **{name:pin[name] for name in ("cli_hash","sdk_version","profile_hash")})\n', encoding='utf-8')
        (self.source / 'improvement_worker.py').write_text(_CAPTURE_FIXTURE + '\n' +
            (SERVER / 'improvement_worker.py').read_text(encoding='utf-8').replace(
                'from __future__ import annotations', ''), encoding='utf-8')
        self.guardian['source']['files'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.iterdir()}
        self.config = pin(); self.config.update(cli_path=str(self.selected),
            cli_hash=hashlib.sha256(self.selected.read_bytes()).hexdigest(), profile_version='claude-owned-images-v3')
        self.static = dict(platform=sys.platform, managed_policy='absent',
            **{name:self.config[name] for name in ('cli_hash','sdk_version','profile_hash')})
        self.candidate = dict(version=1, fingerprint='a'*64, content={'engineering':'guarded-inert-bootstrap'},
            manifests={'guardian':self.guardian, 'trial':self.policy['bootstrap']})
        self.candidate_key = (sys.platform, *(self.config[k] for k in ('cli_version','cli_hash','sdk_version',
            'profile_version','profile_hash')), self.candidate['fingerprint'])
        for seam in (patch.object(registry, 'REVIEWED_QUALIFICATION_CANDIDATES', {self.candidate_key:'b'*64}),
                patch.object(qs, '_runtime_identity', return_value=self.static),
                patch.object(qs, 'observe_release', side_effect=lambda _:copy.deepcopy(self.candidate))):
            seam.start(); self.addCleanup(seam.stop)
        self.qualification = qs.QualificationSession.open(pin=self.config, endpoint='http://127.0.0.1:15432',
            expected_fingerprint=self.candidate['fingerprint'], lifetime_seconds=300, maximum_queries=4)

    async def cleanup(self):
        if self.qualification is not None:
            await self.qualification.aclose_native()
            self.assertFalse(self.qualification._owners)
            self.qualification.cleanup()
        await kernel.HostGuardianWindowsTests.cleanup(self)

    async def _exercise_final_current_handoff(self, mutation):
        from contextlib import ExitStack
        import threading
        session = self.qualification
        held, release = threading.Event(), threading.Event()
        transactions = session.assets.store._Tx
        original_exit = transactions.__exit__
        successful_checks = []
        loop_thread = threading.get_ident()

        def hold_successful_exit(transaction, error_type, error, traceback):
            caller = sys._getframe(1)
            boundary = caller.f_locals.get('self')
            if (caller.f_globals.get('__name__') == parent.__name__ and caller.f_code.co_name == 'check'
                    and type(boundary) is parent.NativeParentBoundary and boundary._qualification is session
                    and error_type is None):
                # The genuine _assert_native_current has already succeeded. Keep
                # its actual final transaction/future from returning to the loop.
                successful_checks.append(threading.get_ident())
                held.set()
                if not release.wait(15): raise AssertionError('fixture final-current release timeout')
            return original_exit(transaction, error_type, error, traceback)

        def diagnostics():
            with closing(session.assets.store._conn()) as connection:
                rows = tuple(tuple(row) for row in connection.execute(
                    "SELECT operation,event_key,result_json FROM improvement_events "
                    "WHERE operation IN ('native_image_decision','native_preflight_evidence') ORDER BY rowid"))
                calls = connection.execute('SELECT COUNT(*) FROM agent_calls').fetchone()[0]
            return rows, calls

        result, failure = None, None
        with ExitStack() as changes, patch.object(transactions, '__exit__', hold_successful_exit):
            verification = asyncio.create_task(session.verify_native())
            try:
                self.assertTrue(await asyncio.to_thread(held.wait, 15), 'fixture never reached successful final check')
                boundary = session._native_parent
                owner = boundary._guardian
                self.assertEqual(len(successful_checks), 1)
                self.assertNotEqual(successful_checks[0], loop_thread)
                self.assertFalse(verification.done())
                self.assertTrue(owner.closed); self.assertTrue(owner.native_drained)
                self.assertEqual((owner._worker_exit_code, owner._guardian_exit_code), (0, 0))
                self.assertEqual(boundary._owner_state, 'DETACHED'); self.assertFalse(session._owners)
                self.assertTrue(boundary._evidence_settled)
                before = await asyncio.to_thread(diagnostics)
                self.assertEqual([row[0] for row in before[0]],
                    ['native_image_decision', 'native_image_decision', 'native_preflight_evidence'])
                self.assertEqual(before[1], 0)
                if mutation == 'close': session.close()
                elif mutation == 'review':
                    changes.enter_context(patch.object(registry, 'REVIEWED_QUALIFICATION_CANDIDATES', {}))
                elif mutation == 'expiry':
                    changes.enter_context(patch.object(qs.time, 'time', return_value=session.scope()['deadline_at']))
                else: raise AssertionError('fixture mutation invalid')
                release.set()
                try: result = await verification
                except BaseException as caught: failure = caught
                self.assertEqual(await asyncio.to_thread(diagnostics), before)
                self.assertTrue(session.root.exists())
                self.assertTrue(owner.closed); self.assertFalse(session._owners)
                self.assertTrue(boundary._evidence_settled)
            finally:
                release.set()
                if not verification.done():
                    try: await verification
                    except BaseException: pass  # The real owner/finally must still settle before test exit.
        with patch.object(transport, '_host_windows', side_effect=AssertionError('final refusal cannot relaunch')):
            with self.assertRaisesRegex(PermissionError, 'already_used'): await session.verify_native()
            await session.aclose_native()
        print('I1_FINAL_HANDOFF', mutation, 'successful_offloop_checks', len(successful_checks),
            'closed', owner.closed, 'drained', owner.native_drained, 'decisions_and_trace', len(before[0]),
            'qualification_calls', before[1], 'returned_result', type(result).__name__, 'failure', type(failure).__name__)
        self.assertIsInstance(failure, PermissionError,
            'revocation after a successful final worker check must refuse result issuance')
        self.assertIsNone(result)
        self.assertRegex(str(failure), {'close': 'closed', 'review': 'unreviewed', 'expiry': 'expired'}[mutation])

    async def test_close_after_successful_final_thread_check_refuses_result(self):
        await self._exercise_final_current_handoff('close')

    async def test_review_revocation_after_successful_final_thread_check_refuses_result(self):
        await self._exercise_final_current_handoff('review')

    async def test_expiry_after_successful_final_thread_check_refuses_result(self):
        await self._exercise_final_current_handoff('expiry')

    async def test_nonempty_home_and_foreign_guardian_refuse_before_any_kernel_acquisition(self):
        session = self.qualification
        original = session.environment
        def dirty(cwd):
            environment = original(cwd)
            (Path(environment['HOME']) / 'foreign-login-marker').write_text('synthetic contamination')
            return environment
        with patch.object(session,'environment',side_effect=dirty), \
                patch.object(transport,'_host_windows',side_effect=AssertionError('HOME refused before API')):
            with self.assertRaisesRegex(PermissionError,'home_inconsistent'): await session.verify_native()
        self.assertFalse(session._owners)
        boundary = session._native_parent
        owner = transport.GuardianSessionV2(self.guardian,self.policy,**self.options)
        try:
            with self.assertRaises(PermissionError): await owner.start_qualification(boundary)
            with self.assertRaises(ValueError): await owner.start(boundary._qualification_seed)
        finally: await owner.aclose()

    async def test_attached_but_unstarted_closed_owner_cannot_acquire_or_be_restarted(self):
        session=self.qualification
        original=transport.GuardianSessionV2.start_qualification
        async def revoked(owner,boundary):
            self.assertIn(owner,session._owners)
            await owner.aclose()  # Pure constructor owner: no native acquisition exists.
            self.assertTrue(owner.closed)
            return await original(owner,boundary)
        with patch.object(transport.GuardianSessionV2,'start_qualification',revoked), \
                patch.object(transport,'_host_windows',side_effect=AssertionError('closed owner cannot acquire')):
            with self.assertRaises(PermissionError):await session.verify_native()
        self.assertFalse(session._owners)

    async def test_symlinked_home_refuses_before_kernel_acquisition(self):
        session=self.qualification
        target=session.root/'owned-link-target';target.mkdir()
        original=session.environment
        def linked(cwd):
            environment=original(cwd);home=Path(environment['HOME']);home.rmdir()
            try:os.symlink(target,home,target_is_directory=True)
            except OSError as error:raise unittest.SkipTest('actual Windows symlink privilege unavailable: '+str(error.winerror))
            return environment
        with patch.object(session,'environment',side_effect=linked), \
                patch.object(transport,'_host_windows',side_effect=AssertionError('linked HOME cannot acquire')):
            with self.assertRaisesRegex(qs.AssetUnavailable,'linked_asset_path'):await session.verify_native()
        self.assertFalse(session._owners)

    async def test_closed_owner_is_retained_on_trace_failure_and_evidence_retry_after_expiry_never_launches(self):
        session = self.qualification
        with patch.object(parent.NativeParentBoundary,'_save_preflight',side_effect=OSError('fixture trace write failed')):
            with self.assertRaises(OSError): await session.verify_native()
        boundary = session._native_parent; owner = boundary._guardian
        self.assertTrue(owner.closed); self.assertTrue(owner.native_drained)
        self.assertIn(owner,session._owners); self.assertFalse(boundary._evidence_settled)
        scratch = Path(boundary._scratch.name); self.assertTrue(scratch.exists())
        with self.assertRaisesRegex(RuntimeError,'owners_unsettled'): session.cleanup()
        with patch.object(qs.time,'time',return_value=session.scope()['deadline_at']+1), \
                patch.object(transport,'_host_windows',side_effect=AssertionError('retry cannot launch')):
            await session.aclose_native()
        self.assertFalse(session._owners); self.assertFalse(scratch.exists())
        with closing(session.assets.store._conn()) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM improvement_events WHERE operation='native_preflight_evidence'").fetchone()[0],1)

    async def test_durable_append_then_session_close_never_sends_delayed_allow(self):
        session = self.qualification
        import threading
        held, release = threading.Event(), threading.Event()
        original = session.assets.blobs.write
        calls = []
        def blocked(brain, raw):
            if b'"dispatch"' in raw and b'"image"' in raw:
                held.set()
                if not release.wait(8): raise OSError('fixture release timeout')
            return original(brain,raw)
        send = transport.GuardianSessionV2._send_command
        async def observe(owner,kind,**extra):
            if kind == 'image_authorize': calls.append(extra)
            return await send(owner,kind,**extra)
        with patch.object(session.assets.blobs,'write',side_effect=blocked), \
                patch.object(transport.GuardianSessionV2,'_send_command',observe):
            task=asyncio.create_task(session.verify_native())
            try:
                self.assertTrue(await asyncio.to_thread(held.wait,8))
                owner=session._native_parent._guardian
                session.close(); self.assertIn(owner,session._owners)
                with self.assertRaises(RuntimeError): session.cleanup()
            finally: release.set()
            with self.assertRaises((PermissionError,OSError,RuntimeError)): await task
        self.assertEqual(calls,[])
        self.assertFalse(session._owners)
        with closing(session.assets.store._conn()) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM agent_calls').fetchone()[0],0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM improvement_events WHERE operation='native_preflight_evidence'").fetchone()[0],1)

    async def test_nonzero_guardian_exit_never_returns_readiness(self):
        # The fixture guardian reports its real drain, then intentionally exits 17.
        target=self.source/'improvement_native_lifetime.py'
        target.write_text(target.read_text()+ '\nif __name__ == "__main__": raise SystemExit(17)\n',encoding='utf-8')
        self.guardian['source']['files'][target.name]=hashlib.sha256(target.read_bytes()).hexdigest()
        # This is a new synthetic candidate snapshot, captured by a new real Session.
        self.qualification.cleanup()
        self.qualification=qs.QualificationSession.open(pin=self.config,endpoint='http://127.0.0.1:15432',
            expected_fingerprint=self.candidate['fingerprint'],lifetime_seconds=300,maximum_queries=4)
        with self.assertRaisesRegex(RuntimeError,'cleanup_unproven'): await self.qualification.verify_native()
        boundary=self.qualification._native_parent
        self.assertTrue(boundary._guardian.closed); self.assertEqual(boundary._guardian._guardian_exit_code,17)
        self.assertFalse(self.qualification._owners)

    async def test_nonzero_worker_exit_never_returns_readiness_and_keeps_trace(self):
        target=self.source/'improvement_worker.py'
        text=target.read_text().replace("return asyncio.run(run_startup3(raw, entrypoint='trial'))",
            "asyncio.run(run_startup3(raw, entrypoint='trial'))\n                return 19")
        target.write_text(text,encoding='utf-8')
        self.guardian['source']['files'][target.name]=hashlib.sha256(target.read_bytes()).hexdigest()
        self.qualification.cleanup()
        self.qualification=qs.QualificationSession.open(pin=self.config,endpoint='http://127.0.0.1:15432',
            expected_fingerprint=self.candidate['fingerprint'],lifetime_seconds=300,maximum_queries=4)
        with self.assertRaisesRegex(RuntimeError,'cleanup_unproven'):await self.qualification.verify_native()
        boundary=self.qualification._native_parent
        self.assertEqual(boundary._guardian._worker_exit_code,19);self.assertTrue(boundary._guardian.closed)
        self.assertTrue(boundary._evidence_settled);self.assertFalse(self.qualification._owners)

    async def test_missing_decision_read_never_mints_result_after_actual_complete_drain(self):
        from improvement_native_decisions import NativeImageDecisionStore
        with patch.object(NativeImageDecisionStore,'read',side_effect=PermissionError('fixture missing decision')):
            with self.assertRaisesRegex(PermissionError,'missing decision'): await self.qualification.verify_native()
        self.assertTrue(self.qualification._native_parent._guardian.closed)
        self.assertFalse(self.qualification._owners)

    async def test_review_revoked_while_authorize_waits_control_lock_refuses_before_send(self):
        session=self.qualification
        held,release=asyncio.Event(),asyncio.Event()
        original=parent.NativeParentBoundary._persist
        def persist(boundary,**kwargs):
            actual=original(boundary,**kwargs)
            async def pending(joined):
                decision=await actual(joined)  # Real encrypted append/final authority check.
                held.set(); await release.wait(); return decision
            return pending
        with patch.object(parent.NativeParentBoundary,'_persist',persist):
            task=asyncio.create_task(session.verify_native())
            await asyncio.wait_for(held.wait(),10)
            owner=session._native_parent._guardian
            await owner._control_lock.acquire()
            try:
                release.set(); await asyncio.sleep(.02)
                previous=owner._out_sequence
                with patch.object(registry,'REVIEWED_QUALIFICATION_CANDIDATES',{}):
                    owner._control_lock.release()
                    with self.assertRaises((PermissionError,OSError)): await task
                self.assertEqual(owner._allowed,set())
                # The only later command may be stop; no image allow was initiated.
                self.assertLessEqual(owner._out_sequence,previous+1)
            finally:
                release.set()
                if owner._control_lock.locked(): owner._control_lock.release()
                if not task.done():
                    task.cancel()
                    with self.assertRaises(BaseException): await task
        self.assertTrue(owner.closed); self.assertFalse(session._owners)

    async def test_actual_handle_close_failure_keeps_session_owner_until_known_retry(self):
        session=self.qualification
        original=transport.GuardianSessionV2._close_handle
        def fail(owner,key,handle):
            if key=='guardian_process': raise OSError('fixture known handle-close refusal')
            return original(owner,key,handle)
        with patch.object(transport.GuardianSessionV2,'_close_handle',fail):
            with self.assertRaises(OSError): await session.verify_native()
        boundary=session._native_parent; owner=boundary._guardian
        self.assertTrue(owner.native_drained); self.assertFalse(owner.closed); self.assertIn(owner,session._owners)
        self.assertTrue(boundary._evidence_settled)
        with self.assertRaises(RuntimeError): session.cleanup()
        await session.aclose_native()
        self.assertTrue(owner.closed); self.assertFalse(session._owners)

    async def test_cancel_after_actual_popen_retains_session_during_inflight_start_and_close(self):
        session=self.qualification
        import threading
        created,release=threading.Event(),threading.Event()
        original=transport.subprocess.Popen
        def delayed(*args,**kwargs):
            child=original(*args,**kwargs); created.set()
            if not release.wait(8): raise OSError('fixture popen delay timeout')
            return child
        with patch.object(transport.subprocess,'Popen',side_effect=delayed):
            task=asyncio.create_task(session.verify_native())
            try:
                self.assertTrue(await asyncio.to_thread(created.wait,8))
                owner=session._native_parent._guardian
                task.cancel(); await asyncio.sleep(.01); task.cancel(); await asyncio.sleep(.01)
                self.assertIn(owner,session._owners); self.assertFalse(task.done())
                with self.assertRaises(RuntimeError): session.cleanup()
            finally: release.set()
            with self.assertRaises(asyncio.CancelledError): await task
        self.assertTrue(owner.closed); self.assertFalse(session._owners)

    async def test_repeated_cancellation_retains_real_owner_until_actual_close_and_trace_settle(self):
        session=self.qualification
        started,release=asyncio.Event(),asyncio.Event()
        original=transport.GuardianSessionV2.aclose
        async def held(owner):
            started.set(); await release.wait()
            await original(owner)
        with patch.object(transport.GuardianSessionV2,'aclose',held):
            task=asyncio.create_task(session.verify_native())
            await asyncio.wait_for(started.wait(),12)
            owner=session._native_parent._guardian
            for _ in range(3): task.cancel(); await asyncio.sleep(0)
            self.assertFalse(task.done()); self.assertIn(owner,session._owners)
            with self.assertRaises(RuntimeError): session.cleanup()
            release.set()
            with self.assertRaises(asyncio.CancelledError): await task
        self.assertTrue(owner.closed); self.assertFalse(session._owners)

    async def test_immutable_partial_trace_snapshot_retry_uses_new_hash_and_deduplicates_sequence(self):
        session=self.qualification
        original=transport.GuardianSessionV2.aclose
        async def close_failed(owner):
            # Actual close remains unattempted: the exact attached owner survives.
            raise OSError('fixture before close')
        with patch.object(transport.GuardianSessionV2,'aclose',close_failed):
            with self.assertRaises(OSError): await session.verify_native()
        boundary=session._native_parent; owner=boundary._guardian
        self.assertIn(owner,session._owners); self.assertFalse(owner.closed)
        first=boundary._trace_record['trace_hash']
        with self.assertRaises(RuntimeError): session.cleanup()
        await session.aclose_native()
        self.assertTrue(owner.closed); self.assertFalse(session._owners)
        final=boundary._trace_record['trace_hash']; self.assertNotEqual(first,final)
        with closing(session.assets.store._conn()) as conn:
            rows=conn.execute("SELECT result_json FROM improvement_events WHERE operation='native_preflight_evidence'").fetchall()
        self.assertEqual(len(rows),2)
        self.assertEqual({json.loads(row[0])['trace_hash'] for row in rows},{first,final})
        for row in rows:
            raw=b''.join(session.assets.blobs.read(session.principal.brain_id,k) for k in json.loads(row[0])['blob_hashes'])
            packets=json.loads(raw)
            self.assertEqual(len(packets),len({p['sequence'] for p in packets}))

    async def test_actual_startup3_owner_sdk_image_decisions_and_encrypted_trace(self):
        session, acquired = self.qualification, []
        original = transport.GuardianSessionV2._prepare_guards
        def observe(owner):
            self.assertIn(owner, session._owners)
            self.assertIs(session._native_boundaries[owner]._guardian, owner)
            acquired.append(owner)
            return original(owner)
        diagnostic = []
        async def drain(owner, handle):
            while True:
                task = owner._task(asyncio.to_thread(owner._api.read, handle))
                raw = await owner._wait(task, owner._lifetime)
                if not raw: return
                diagnostic.append(raw)
        with patch.object(transport.GuardianSessionV2, '_prepare_guards', observe), \
                patch.object(transport.GuardianSessionV2, '_drain_handle', drain):
            try: result = await session.verify_native()
            except BaseException:
                print('INERT_WORKER_DIAGNOSTIC', b''.join(diagnostic).decode(errors='replace'))
                raise
        self.assertEqual(len(acquired), 1)
        owner = acquired[0]
        self.assertTrue(owner.native_drained); self.assertTrue(owner.closed)
        self.assertEqual((owner._worker_exit_code,owner._guardian_exit_code),(0,0))
        self.assertIs(type(result), qs.QualificationPreflight)
        self.assertEqual(set(result.__dataclass_fields__),{'version','domain','supported','account_ready','technical_ready',
            'run_hash','pin_hash','release_fingerprint','review_hash','launch_nonce','environment_hash','observation_hash',
            'trace_hash','decision_hashes','cleanup'})
        self.assertFalse(result.supported); self.assertFalse(result.account_ready); self.assertTrue(result.technical_ready)
        self.assertFalse(hasattr(result, 'capability_hash')); self.assertEqual(result.cleanup,'proven')
        self.assertEqual(len(result.decision_hashes),2)
        with self.assertRaises((AttributeError,TypeError)): result.supported=True
        self.assertFalse(session._owners)
        with closing(session.assets.store._conn()) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM agent_calls').fetchone()[0],0)
            rows=conn.execute("SELECT * FROM improvement_events WHERE operation='native_image_decision' ORDER BY rowid").fetchall()
            self.assertEqual(len(rows),2)
            self.assertEqual(tuple(qs.IM._hash(json.loads(row['result_json'])) for row in rows),result.decision_hashes)
            trace=conn.execute("SELECT result_json FROM improvement_events WHERE operation='native_preflight_evidence' ORDER BY rowid DESC").fetchone()
        envelope=json.loads(trace[0]); self.assertEqual(envelope['trace_hash'],result.trace_hash)
        raw=b''.join(session.assets.blobs.read(session.principal.brain_id,k) for k in envelope['blob_hashes'])
        packets=json.loads(raw)
        self.assertTrue(any(p['body']['type']=='drained' for p in packets))
        self.assertTrue(any(p['body']['type']=='preflight_complete' for p in packets))
        for row in rows:
            blob=json.loads(row['result_json'])['blob_hashes'][0]
            self.assertTrue(session.assets.blobs._path(session.principal.brain_id,blob).read_text().startswith('enc:'))
        self.assertEqual(result.trace_hash,hashlib.sha256(raw).hexdigest())

    async def test_actual_result_and_spoofed_mapping_are_rejected_by_all_four_product_owners(self):
        import test_improvement_qualification_admission_fences as fences
        result=await self.qualification.verify_native()
        values=(result,dict(supported=True,account_ready=False,domain='qualification',capability_hash='c'*64))
        for value in values:
            with self.subTest(type=type(value).__name__,owner='admission'), \
                    fences.scratch(fences.admission_fixtures.AdmissionTests) as f:
                f.verify.return_value=value
                with self.assertRaisesRegex(ValueError,'trial_native_unavailable'):f.admit()
                f.assert_no_admission()
            with self.subTest(type=type(value).__name__,owner='operation-reservation'), \
                    fences.scratch(fences.operation_fixtures.OperationExecutionTests) as f:
                service=f.execution()
                with patch('improvement_operation_adapter.ClaudeOperationAdapter.verify',return_value=value):
                    with self.assertRaisesRegex(ValueError,'operation_native_unavailable'):
                        service.reserve(f.owner,f.operation['operation_id'],expected_generation=1,event_key='preflight-product-refusal')
                with closing(f.store._conn()) as conn:
                    self.assertEqual(conn.execute('SELECT COUNT(*) FROM agent_calls').fetchone()[0],0)
            with self.subTest(type=type(value).__name__,owner='trial-runner'), \
                    fences.scratch(fences.trial_runner_fixtures.TrialRunnerTests) as f:
                def factory(*args,**kwargs):
                    adapter=f.factory(*args,**kwargs);adapter.verify=lambda:value;return adapter
                row=await f.runner(adapter_factory=factory).run(f.f.owner,f.trial['trial_id'])
                self.assertEqual(row['status'],'not_run');self.assertIsNone(f.call()['engine_at'])
                self.assertEqual(f.call()['status'],'refunded');self.assertNotIn('execute',f.log)
            with self.subTest(type=type(value).__name__,owner='operation-runner'), \
                    fences.scratch(fences.operation_runner_fixtures.OperationRunnerTests) as f:
                runner=f.runner();original=runner.adapter_factory
                def factory(*args,**kwargs):
                    adapter=original(*args,**kwargs);adapter.verify=lambda:value;return adapter
                runner.adapter_factory=factory
                row=await runner.run(f.owner,f.row['operation_id'])
                call=f.execution.ledger.get(row['attempts'][0]['call_id'])
                self.assertEqual(row['status'],'not_run');self.assertEqual(call['status'],'refunded')
                self.assertIsNone(call['engine_at']);self.assertEqual(getattr(f,'native_queries',0),0)


async def _retained_unknown_case(mode):
    """An enclosing disposable process owns intentionally unprovable cases.

    No Session map/retained set is cleared. Its OS process exit settles the
    enclosing lifetime only after every actual fixture child is observed dead.
    """
    f=QualificationKernelTests();await f.asyncSetUp()
    session=f.qualification;children=[]
    if mode=='missing_drain':
        target=f.source/'improvement_native_lifetime.py'
        target.write_text(target.read_text().replace("self._event('drained',", "self._event('fixture_missing_drain',"),encoding='utf-8')
        f.guardian['source']['files'][target.name]=hashlib.sha256(target.read_bytes()).hexdigest()
        session.cleanup()
        session=f.qualification=qs.QualificationSession.open(pin=f.config,endpoint='http://127.0.0.1:15432',
            expected_fingerprint=f.candidate['fingerprint'],lifetime_seconds=300,maximum_queries=4)
    original=transport.subprocess.Popen
    def spawn(*args,**kwargs):
        child=original(*args,**kwargs);children.append(child)
        if mode=='popen_ambiguity':raise OSError('fixture after successful Popen')
        return child
    write=transport.GuardianSessionV2._write_public
    def public(owner,raw):
        if mode=='partial_public':
            owner._process.stdin.write(raw[:2]);owner._process.stdin.flush()
            raise OSError('fixture partial public frame')
        return write(owner,raw)
    with patch.object(transport.subprocess,'Popen',side_effect=spawn), \
            patch.object(transport.GuardianSessionV2,'_write_public',public):
        with f.assertRaises(OSError):await session.verify_native()
    boundary=session._native_parent;owner=boundary._guardian
    f.assertIn(owner,session._owners);f.assertFalse(owner.closed)
    with f.assertRaises(RuntimeError):session.cleanup()
    for child in children:
        if child.stdin is not None and not child.stdin.closed:child.stdin.close()
        await asyncio.to_thread(child.wait,timeout=10)
    if owner._worker_identity is not None:
        f.assertTrue(owner._api.terminal(owner._slots['process'].value))
    with f.assertRaises(OSError):await session.aclose_native()
    f.assertIn(owner,session._owners);f.assertFalse(owner.closed)
    f.assertTrue(boundary._evidence_settled)
    # These paths are fixture-owned. The enclosing host removes them only after
    # this process has exited, which closes its exact remaining OS capabilities.
    print(json.dumps(dict(mode=mode,retained=True,closed=False,readiness=False,
        children_terminal=all(child.returncode is not None for child in children),
        root=str(session.root),fixture_root=str(f.root))),flush=True)
    os._exit(0)


@unittest.skipUnless(os.name=='nt','enclosing real Windows process lifetime')
class QualificationRetainedProcessTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_launch_popen_ambiguity_and_missing_drain_keep_owner_until_enclosing_exit(self):
        for mode in ('partial_public','popen_ambiguity','missing_drain'):
            with self.subTest(mode=mode):
                code=('import sys,asyncio;sys.path.insert(0,sys.argv[1]);'
                    'import test_improvement_qualification_native_preflight as m;'
                    'asyncio.run(m._retained_unknown_case(sys.argv[2]))')
                child=await asyncio.to_thread(subprocess.run,
                    [sys.executable,'-I','-B','-c',code,str(Path(__file__).parent),mode],
                    capture_output=True,timeout=45,creationflags=0x08000000)
                self.assertEqual(child.returncode,0,child.stderr.decode(errors='replace'))
                result=json.loads(child.stdout)
                self.assertTrue(result['retained']);self.assertFalse(result['closed']);self.assertFalse(result['readiness'])
                self.assertTrue(result['children_terminal'])
                # Actual enclosing process exit and actual original child exit
                # precede removal; this is not product cleanup/detachment proof.
                for key in ('root','fixture_root'):
                    path=Path(result[key]);self.assertTrue(path.is_absolute())
                    self.assertTrue(path.name.startswith('jnqual-' if key=='root' else 'jh2-'))
                    shutil.rmtree(path);self.assertFalse(path.exists())


@unittest.skipUnless(os.name=='nt','actual static Windows runtime/source/installed import inventory')
class QualificationClosureTests(unittest.TestCase):
    def test_actual_observed_closure_contains_changed_consumers_without_registering_candidate(self):
        from improvement_claude import profile_hash, PROFILE_VERSION
        from improvement_native_release import observe_release
        before_candidates=copy.deepcopy(registry.REVIEWED_QUALIFICATION_CANDIDATES)
        before_releases=copy.deepcopy(registry.REVIEWED_RELEASES)
        value=pin();value.update(profile_hash=profile_hash(),profile_version='claude-owned-images-v3')
        # Static installed bytes/metadata only. The unused fixture CLI pathname
        # is never opened or executed; observation never registers its fingerprint.
        observed=observe_release(value)
        for name in ('improvement_qualification_session.py','improvement_native_parent.py',
                'improvement_native_transport.py','improvement_native_worker.py','improvement_native_sdk.py',
                'improvement_qualification_protocol.py','improvement_worker.py','improvement_operation_worker.py'):
            self.assertEqual(observed['content']['source'][name],hashlib.sha256((SERVER/name).read_bytes()).hexdigest())
        self.assertNotIn('improvement_native_qualifications.py',observed['content']['source'])
        self.assertEqual(registry.REVIEWED_QUALIFICATION_CANDIDATES,before_candidates)
        self.assertEqual(registry.REVIEWED_RELEASES,before_releases)
        self.assertEqual(PROFILE_VERSION,'claude-isolated-roles-v2')


if __name__ == '__main__': unittest.main()
