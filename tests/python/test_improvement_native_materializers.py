"""Actual native-format producers over real host/SQL, no native execution."""
from _paths import ROOT, SERVER  # noqa: F401

import importlib
import importlib.util
import json
import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_claude as claude
import improvement_store as IM
import test_improvement_host_snapshots as H
import test_improvement_trials as T
import test_improvement_preparation as P
import test_improvement_view_materialization as V
import test_improvement_operation_execution as O

PLANNED = 'claude-owned-images-v3'


def select_fixture(test):
    original = H.HostSnapshotTests.setUp
    def setup(fixture):
        original(fixture)
        fixture.engine.update(profile_version=PLANNED, profile_hash=claude.profile_hash())
    return patch.object(H.HostSnapshotTests, 'setUp', setup)


class NativeFormatSelectionTests(unittest.TestCase):
    def selector(self):
        self.assertIsNotNone(importlib.util.find_spec('improvement_native_formats'), 'closed host-pinned input format selector missing')
        return importlib.import_module('improvement_native_formats')

    def test_closed_exact_source_profile_selector_preserves_old_defaults_and_refuses_drift(self):
        module = self.selector()
        f = T.TrialStoreTests(); f.setUp(); self.addCleanup(f.doCleanups)
        pin = f.request['engine_config']
        self.assertEqual([module.input_version(pin, k) for k in ('baseline', 'view', 'operation')], [1, 3, 1])
        selected = {**pin, 'profile_version': PLANNED, 'profile_hash': claude.profile_hash()}
        self.assertEqual(module.NATIVE_PROFILE_VERSION, PLANNED)
        self.assertEqual([module.input_version(selected, k) for k in ('baseline', 'view', 'operation')], [5, 4, 2])
        for drift in ({'profile_hash': 'f' * 64}, {'provider': 'foreign'}, {'engine_id': 'foreign'}, {'version': True}):
            with self.subTest(drift=drift), self.assertRaises(ValueError): module.input_version({**selected, **drift}, 'baseline')
        with self.assertRaises(ValueError): module.input_version(selected, 'request-mode')
        self.assertEqual(claude.PROFILE_VERSION, 'claude-isolated-roles-v2', 'producer unit must not activate global runtime')

    def test_native_baseline_without_concrete_host_refuses_before_solver_or_exposure(self):
        f = T.TrialStoreTests(); f.setUp(); self.addCleanup(f.doCleanups)
        pin = f.request['engine_config']; pin.update(profile_version=PLANNED, profile_hash=claude.profile_hash())
        f.request['pins']['engine_config_hash'] = IM._hash(pin)
        row = f.reserve(); claim = f.trials.claim(f.owner, row['trial_id'], expected_generation=1)
        with patch.object(f.trials.cases, '_solver', side_effect=AssertionError('unbound native input cannot decrypt solver')), \
                self.assertRaisesRegex(PermissionError, 'native_host_unbound'):
            f.trials.materialize(f.owner, row['trial_id'], expected_generation=claim['generation'],
                lease_token=claim['lease_token'], baseline_context=f.context)
        with closing(f.rs._conn()) as connection:
            actual = connection.execute('SELECT materialization_hash,engine_at,workspace_json FROM improvement_trial_attempts WHERE trial_id=?',
                (row['trial_id'],)).fetchone()
            self.assertEqual(tuple(actual), (None, None, None))

    def test_native_host_constructor_rejects_fake_or_foreign_actual_store(self):
        from improvement_trials import TrialStore
        f = T.TrialStoreTests(); f.setUp(); self.addCleanup(f.doCleanups)
        foreign = H.HostSnapshotTests(); foreign.setUp(); self.addCleanup(foreign.doCleanups)
        for host in (object(), foreign.host):
            with self.subTest(host=type(host).__name__), self.assertRaisesRegex(TypeError, 'concrete_same_store_native_host_required'):
                TrialStore(f.assets, native_host=host)


class NativePreparationMaterializerTests(unittest.TestCase):
    def setUp(self):
        with select_fixture(self):
            self.f = P.PreparationTests(); self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.freeze(); self.admitted = self.f.admit()
        self.trials = self.f.service().trials
        self.row = self.trials.claim(self.f.owner, self.admitted.trial_id, expected_generation=1)
        self.context = self.f.host.context_loader(self.f.owner, self.admitted.request)

    def materialize(self):
        return self.trials.materialize(self.f.owner, self.admitted.trial_id, expected_generation=self.row['generation'],
            lease_token=self.row['lease_token'], baseline_context=self.context)

    def test_actual_preparation3_emits_real_baseline5_before_candidate_or_paired_view(self):
        manifest = self.materialize()
        self.assertEqual(self.admitted.request['version'], 3)
        self.assertEqual(manifest['version'], 5); self.assertNotIn('effective_view', manifest)
        self.assertEqual(manifest['assets'][0]['content'].encode(), self.f.f.f.skill.read_bytes())
        self.assertEqual(manifest['baseline_context'], self.context)
        workspace = self.trials.workspace.prepare(self.admitted.trial_id, 1, manifest)
        self.addCleanup(self.trials.workspace.cleanup, self.admitted.trial_id, 1)
        row = self.trials.prepared(self.f.owner, self.admitted.trial_id, expected_generation=self.row['generation'],
            lease_token=self.row['lease_token'], receipt=workspace)
        self.assertEqual(row['status'], 'prepared')
        with closing(self.f.store._conn()) as connection:
            for table in ('improvement_skill_candidates', 'improvement_effective_views', 'improvement_comparisons'):
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)

    def test_source_edit_during_actual_solver_read_rolls_back_native_baseline_exposure(self):
        solver, changed = self.trials.cases._solver, []
        with closing(self.f.store._conn()) as connection:
            before = list(map(tuple, connection.execute('SELECT * FROM improvement_case_exposures ORDER BY fingerprint')))
        def drift(*args, **kwargs):
            value = solver(*args, **kwargs)
            skill = self.f.f.f.skill
            skill.write_bytes(skill.read_bytes() + b'\nOwner changed source during native baseline read.\n')
            changed.append(True); return value
        with patch.object(self.trials.cases, '_solver', side_effect=drift), self.assertRaises((PermissionError, IM.ConflictError)):
            self.materialize()
        self.assertEqual(changed, [True])
        with closing(self.f.store._conn()) as connection:
            row = connection.execute('SELECT materialization_hash,engine_at,workspace_json FROM improvement_trial_attempts WHERE trial_id=?',
                (self.admitted.trial_id,)).fetchone()
            self.assertEqual(tuple(row), (None, None, None))
            self.assertEqual(list(map(tuple, connection.execute('SELECT * FROM improvement_case_exposures ORDER BY fingerprint'))), before)


class NativeViewMaterializerTests(V.sources.SourceFixture, unittest.IsolatedAsyncioTestCase):
    request = V.ViewMaterializationTests.request
    load = V.ViewMaterializationTests.load
    bound = V.ViewMaterializationTests.bound
    live_request = V.ViewMaterializationTests.live_request
    materialize = V.ViewMaterializationTests.materialize

    def setUp(self):
        with select_fixture(self): super().setUp()

    async def asyncSetUp(self):
        # Existing semantic authoring fixture emits synthetic legacy packets.
        # Its setup alone keeps historical formats; the actual view call below
        # uses the real selector and the genuinely stored new-profile authority.
        if importlib.util.find_spec('improvement_native_formats') is None:
            await super().asyncSetUp()
        else:
            with patch('improvement_native_formats.input_version', side_effect=lambda pin, kind: {'baseline': 1, 'view': 3, 'operation': 1}[kind]):
                await super().asyncSetUp()

    async def test_actual_pair_installs_exact_revision_and_candidate_without_canonical_bundle_fabrication(self):
        trials, metadata = self.bound()
        skill = self.f.f.f.skill; before = skill.read_bytes(); manifests = []
        for position in (0, 1):
            request, claimed, manifest = self.materialize(trials, metadata, position, 'native-view-materialize-' + str(position))
            self.assertEqual(request['engine_config']['profile_version'], PLANNED)
            self.assertEqual(manifest['version'], 4)
            self.assertEqual(manifest['effective_view'], request['view'])
            with closing(self.assets.store._conn()) as connection:
                resolved, _ = self.host._views.resolve_request(self.owner, request, connection=connection,
                    require_link=True, trial_id=claimed['trial_id'])
                self.assertIsNone(connection.execute('SELECT 1 FROM improvement_bundles WHERE manifest_hash=?',
                    (request['pins']['candidate_bundle_hash'],)).fetchone())
            asset = resolved.manifest['assets'][0]
            self.assertEqual(manifest['assets'], [{'id': asset['id'], 'path': asset['canonical_ref'],
                'hash': asset['content_hash'], 'content': resolved.content.decode('utf-8')}])
            receipt = trials.workspace.prepare(claimed['trial_id'], 1, manifest)
            self.addCleanup(trials.workspace.cleanup, claimed['trial_id'], 1)
            self.assertEqual(trials.workspace.validate(receipt), manifest)
            row = trials.prepared(self.owner, claimed['trial_id'], expected_generation=claimed['generation'],
                lease_token=claimed['lease_token'], receipt=receipt)
            self.assertEqual(row['status'], 'prepared'); manifests.append(manifest)
        self.assertEqual(skill.read_bytes(), before)
        self.assertEqual(manifests[0]['case'], manifests[1]['case'])
        self.assertEqual(manifests[0]['baseline_context'], manifests[1]['baseline_context'])
        self.assertNotEqual(manifests[0]['assets'][0]['id'], manifests[1]['assets'][0]['id'])


class NativeOperationMaterializerTests(unittest.TestCase):
    def test_actual_role_emits2_and_prepared_recomputes_input_without_fabricated_view(self):
        with select_fixture(self):
            f = O.OperationExecutionTests(); f.setUp()
        self.addCleanup(f.doCleanups)
        service = f.execution(); row, _, receipt = f.prepared(service)
        manifest = service.workspace.validate(receipt)
        self.assertEqual(manifest['version'], 2)
        self.assertEqual(manifest['data'], f.data)
        self.assertEqual(manifest['engine_config_hash'], IM._hash(f.f.host.selected_engine()))
        self.assertNotIn('effective_view', manifest)
        self.assertEqual(row['status'], 'prepared')


if __name__ == '__main__': unittest.main()
