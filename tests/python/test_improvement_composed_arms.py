"""Reserved composed-arm policy and actual owners; no native/model readiness.

Fresh policy is supplied at the public create-request boundary before the real
immutable experiment definition exists. Frozen definitions are never patched.
Later publication fixtures explicitly use synthetic unexecuted native controls.
"""
from _paths import ROOT, SERVER  # noqa: F401

import importlib
import json
import time
import unittest
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import patch

import improvement_store as IM
from improvement_comparison_plans import ExperimentPlans
from improvement_native_decisions import NativeImageDecisionStore, attempt_scope
from improvement_native_trace_checks import validate_native_trace
from improvement_operation_profile import OperationProfile
from improvement_operation_runner import OperationRunner
from improvement_operation_tasks import OperationTasks
from improvement_semantic_review import SemanticReview
from improvement_views import EffectiveViews
import test_improvement_comparison_plans as plans_fixture
import test_improvement_compositions as publication_fixture
import test_improvement_compose_admission as admission_fixture
import test_improvement_native_trace_checks as native_fixture
from test_improvement_operation_profile2 import EngineeringOperationBinding


POLICY = 'two_proposals_and_one_compose'
PUBLIC = {'experiment_id': 'policy-experiment', 'contract_id': 'policy-contract', 'case_set_id': 'policy-cases',
          'base_bundle_id': 'policy-bundle', 'expected_context_generation': 1, 'repeat_policy': 'feasibility',
          'timeout_seconds': 120}


def require_policy(test):
    # A missing closed-policy feature must fail before expensive private setup.
    try:
        accepted = ExperimentPlans._create_request({**PUBLIC, 'candidate_policy': POLICY})
    except ValueError:
        accepted = None
    test.assertIsNotNone(accepted, 'Explicit pre-observation composed-arm policy is not implemented')
    test.assertEqual(accepted['candidate_policy'], POLICY)


class ComposedPolicyTests(unittest.TestCase):
    def setUp(self):
        require_policy(self)

    def fixture(self):
        fixture = plans_fixture.ComparisonPlanTests()
        fixture.setUp()
        self.addCleanup(lambda: self.assertTrue(fixture.doCleanups(), 'Actual plan fixture cleanup failed'))
        return fixture

    def test_actual_old_create_stays_two_and_explicit_new_create_reserves_three_before_observations(self):
        for reserved in (False, True):
            with self.subTest(reserved=reserved):
                fixture = self.fixture()
                plans = fixture.plans()
                request = fixture.request(**({'candidate_policy': POLICY} if reserved else {}))
                before = (fixture.count('improvement_trials'), fixture.count('agent_calls'),
                          fixture.count('improvement_trial_observations'))
                result = plans.create(fixture.owner, request, event_key='owner-reserved-composed-policy')
                with closing(fixture.store._conn()) as connection:
                    stored = dict(connection.execute('SELECT * FROM improvement_experiments').fetchone())
                    definition = json.loads(stored['definition_json'])
                    event = connection.execute("SELECT * FROM improvement_events WHERE operation='experiment_owner_create'").fetchone()
                self.assertEqual(definition['decision_policy']['multiple_tests'], 3 if reserved else 2)
                self.assertEqual(stored['definition_hash'], IM._hash(definition))
                self.assertEqual(event['request_hash'], IM._hash(request))
                self.assertEqual(json.loads(event['result_json']), result)
                self.assertEqual(before, (fixture.count('improvement_trials'), fixture.count('agent_calls'),
                                          fixture.count('improvement_trial_observations')))
                if not reserved:
                    expected = fixture.h.definition()
                    expected['decision_policy']['multiple_tests'] = 2
                    self.assertEqual(definition, expected, 'Historical closed definition bytes and defaults remain exact')

    def test_closed_policy_does_not_accept_arbitrary_budget_or_readiness_fields(self):
        self.assertEqual(ExperimentPlans._create_request(PUBLIC), PUBLIC)
        selected = {**PUBLIC, 'candidate_policy': POLICY}
        self.assertEqual(ExperimentPlans._create_request(selected), selected)
        for changed in ({'candidate_policy': True}, {'candidate_policy': 'three_proposals'},
                        {'candidate_policy': 'two_proposals'}, {'multiple_tests': 3},
                        {'candidate_policy': POLICY, 'multiple_tests': 3},
                        {'candidate_policy': POLICY, 'native_ready': True}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                ExperimentPlans._create_request({**PUBLIC, **changed})

    def test_actual_state_reconstructs_reserved_policy_and_cold_create_replay_cannot_refresh_it(self):
        fixture = self.fixture()
        plans = fixture.plans()
        request = fixture.request(candidate_policy=POLICY)
        created = plans.create(fixture.owner, request, event_key='owner-frozen-three-hypotheses')
        with closing(fixture.store._conn()) as connection:
            row, prepared = plans._state(connection, fixture.owner, request['experiment_id'], created['generation'], unsealed=True)
            self.assertEqual(prepared[0]['decision_policy']['multiple_tests'], 3)
            before = dict(row)
            self.assertEqual(IM._hash(prepared[0]), row['definition_hash'])
        fixture.host.revoke(fixture.owner, request['experiment_id'], expected_generation=1, event_key='revoke-after-policy-create')
        with patch.object(fixture.host, '_snapshot_observe', side_effect=AssertionError('Cold policy replay cannot refresh sources')), \
                patch.object(fixture.assets.blobs, 'read', side_effect=AssertionError('Cold policy replay cannot decrypt')):
            self.assertEqual(plans.create(fixture.owner, request, event_key='owner-frozen-three-hypotheses'), created)
        with closing(fixture.store._conn()) as connection:
            self.assertEqual(dict(connection.execute('SELECT * FROM improvement_experiments').fetchone()), before)
        with self.assertRaises((PermissionError, IM.ConflictError)):
            plans.create(fixture.owner, request, event_key='new-request-cannot-regrant-three-hypotheses')


class ComposedArmTests(unittest.IsolatedAsyncioTestCase):
    # Borrow helpers only, never inherit and rerun the earlier seven tests.
    new_fixture = publication_fixture.CompositionTests.new_fixture
    close_services = publication_fixture.CompositionTests.close_services
    output = publication_fixture.CompositionTests.output
    adapter = publication_fixture.CompositionTests.adapter
    service = publication_fixture.CompositionTests.service
    compose = publication_fixture.CompositionTests.compose
    rows = publication_fixture.CompositionTests.rows

    def setUp(self):
        require_policy(self)
        self.assertTrue(callable(getattr(EffectiveViews, 'freeze_comparison', None)))
        self.module = importlib.import_module('improvement_compositions')
        self.services = []
        self.addAsyncCleanup(self.close_services)
        self.semantic_queries = 0

    async def published(self, *, reserve_three=True, publisher_id=None):
        # This is the ONLY policy seam: the public owner request before actual
        # create. No definition/hash/policy/observation is edited afterwards.
        original = plans_fixture.ComparisonPlanTests.request
        def request(fixture, **changes):
            value = original(fixture, **changes)
            return {**value, 'candidate_policy': POLICY} if reserve_three else value
        if publisher_id is not None:
            # ORIGINAL trusted-host DI before any context/input is frozen.
            # This synthetic shared-source read grant permits only two owner
            # identities in this exact brain. The actual file observer still
            # reads/rechecks all bytes, paths and frozen source-owner authority.
            # It proves the generic host callback contract, no external grant.
            from improvement_trial_file_sources import BrainFileFixtures
            observe = BrainFileFixtures.__call__
            source_owner = None
            def shared_read(observer, principal, refs, **keywords):
                nonlocal source_owner
                if source_owner is None:
                    source_owner = principal
                if (principal.kind != 'owner' or principal.brain_id != source_owner.brain_id
                        or principal.id not in (source_owner.id, publisher_id)):
                    raise PermissionError('synthetic_shared_source_scope_denied')
                return observe(observer, source_owner, refs, **keywords)
            self.enterContext(patch.object(BrainFileFixtures, '__call__', shared_read))
        with patch.object(plans_fixture.ComparisonPlanTests, 'request', request):
            self.new_fixture()
        subject = self.service()
        self.raw = json.dumps(self.output(), ensure_ascii=False)
        from resonance_store import Principal
        publisher = self.owner if publisher_id is None else Principal('owner', publisher_id, self.owner.brain_id)
        result = await self.compose(subject, owner=publisher)
        self.assertEqual(result['status'], 'candidate_staged', result)
        self.candidate = self.rows('improvement_skill_candidates')[-1]
        self.assertEqual(self.candidate['ordinal'], 3)
        self.plans = self.execution.plans
        return subject, result

    def generation(self):
        return self.plans.records.get(self.owner, self.saved['experiment_id'])['generation']

    def exact_diff(self):
        return self.plans.authoring.authorize_diff(self.owner, self.candidate['id'],
            expected_generation=self.candidate['base_generation'], before_hash=self.candidate['base_hash'],
            after_hash=self.candidate['content_hash'], event_key='owner-composed-exact-diff')

    def bind(self, authority, *, key='owner-bind-checked-composed-arm'):
        return self.plans.bind_arm(self.owner, self.saved['experiment_id'], self.candidate['id'],
            authority['authority_id'], expected_generation=self.generation(), event_key=key)

    def frozen(self, bound):
        try:
            return self.plans.freeze(self.owner, self.saved['experiment_id'], 3, 'tuning',
                expected_generation=bound['generation'], event_key='owner-freeze-composed-tuning')
        except ValueError as error:
            self.fail('Valid reserved composed arm cannot freeze: ' + str(error))

    def metadata_counts(self):
        return tuple(len(self.rows(table)) for table in ('improvement_experiment_arms',
            'improvement_comparisons', 'improvement_events', 'improvement_trials', 'agent_calls'))

    def semantic_adapter(self, pin, *, workspace, before_engine_start):
        """Typed fake SDK messages through the actual semantic2 product owner.

        The same explicitly synthetic verifier/format/predicate controls as the
        composer fixture remain. No product/current/evidence/view gate is mocked.
        """
        test = self
        class SyntheticSemanticAdapter:
            def verify(self):
                return {'supported': True, 'capability_hash': 'c' * 64}

            async def execute(self, request, receipt, *, on_closing_observations=None):
                from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage
                manifest = workspace.validate(receipt)
                test.assertEqual((manifest['version'], manifest['request']['kind']), (2, 'semantic'))
                test.assertEqual(manifest['request']['candidate_id'], test.candidate['id'])
                profile = OperationProfile(pin, workspace, receipt, 'c' * 64, before_query=before_engine_start)
                with patch('improvement_native_profile.NativeProfileBinding', EngineeringOperationBinding):
                    profile.bind_native_runtime(object(), environment={'engineering': 'unexecuted semantic binding only'})
                profile.options(SimpleNamespace(cwd=receipt['path'], session_id=None, _on_stderr=lambda _: None))
                await profile.before_query()
                test.semantic_queries += 1
                provisional = native_fixture.trace('operation', receipt, pin, system_prompt=profile.system_prompt)
                profile._native_binding.delivery = native_fixture.delivery('operation', receipt, provisional,
                    profile.user_prompt(), manifest['request']['input_hash'])
                assessment = IM._json({'version': 1, 'verdict': 'pass', 'summary':
                    'Synthetic unexecuted independent meaning assessment; no business evidence.', 'findings': []})
                events = profile.observe(SystemMessage('init', {'session_id': 'synthetic-composed-review', 'tools': native_fixture.TOOLS[:1]}))
                events += profile.observe(AssistantMessage([], model=pin['model'], session_id='synthetic-composed-review'))
                events += profile.observe(ResultMessage('success', 1, 1, False, 1, 'synthetic-composed-review', result=assessment))
                packets = native_fixture.trace('operation', receipt, pin, events, profile.system_prompt)
                next(item['body'] for item in packets if item['body']['type'] == 'worker_ready')['capability_hash'] = 'c' * 64
                checked = validate_native_trace(packets, kind='operation', receipt=receipt, pin=pin,
                    capability_hash='c' * 64, system_prompt=profile.system_prompt, user_prompt=profile.user_prompt(),
                    data_hash=manifest['request']['input_hash'])
                scope = attempt_scope(kind='operation', brain_id=test.owner.brain_id, receipt=receipt,
                    config_pin=pin, capability_hash='c' * 64)
                def current(connection, joined):
                    row = test.execution._row(connection, test.owner, receipt['operation_id'])
                    attempt = test.execution._attempt(connection, row)
                    test.execution._leased(connection, test.owner, row['id'], row['generation'],
                        attempt['lease_token'], time.time())
                    test.execution._current(connection, test.owner, row)
                    return 'allow'
                decisions = NativeImageDecisionStore(test.assets)
                for joined in checked['joins']:
                    decisions.persist(test.owner, joined, scope_hash=scope, current=current)
                for packet in packets:
                    yield packet
                test.assertTrue(callable(on_closing_observations))
                await on_closing_observations(())
        return SyntheticSemanticAdapter()

    def semantic(self):
        runner = OperationRunner(self.execution, adapter_factory=self.semantic_adapter)
        service = SemanticReview(self.execution, OperationTasks(self.execution, runner))
        self.services.append(service)
        return service

    async def test_budget_two_published_draft_is_readable_but_cannot_bind_arm_three(self):
        await self.published(reserve_three=False)
        authoring = self.plans.authoring
        with closing(self.store._conn()) as connection:
            state = authoring._state(connection, self.owner, self.saved['experiment_id'], self.candidate['target_id'],
                self.candidate['base_revision_id'], self.candidate['base_hash'])
            observed, base = authoring.observe(self.owner, state['target'])
            proposal = authoring.read_proposal(connection, self.owner, self.candidate, state, observed, base)
            definition = json.loads(connection.execute('SELECT definition_json FROM improvement_experiments').fetchone()[0])
        self.assertEqual(proposal['provenance']['version'], 2)
        self.assertEqual(definition['decision_policy']['multiple_tests'], 2)
        authority = self.exact_diff()
        counts, generation = self.metadata_counts(), self.generation()
        with self.assertRaises(admission_fixture.DENIED):
            self.bind(authority)
        self.assertEqual(self.metadata_counts(), counts)
        self.assertEqual(self.generation(), generation)
        self.assertEqual(self.queries, 1)

    async def test_reserved_three_requires_new_exact_diff_and_cannot_run_without_independent_semantic_view(self):
        from improvement_experiment_admission import ExperimentAdmission
        from improvement_claude import ClaudeTrialAdapter
        await self.published()
        with closing(self.store._conn()) as connection:
            original = connection.execute('SELECT authority_id FROM improvement_experiment_arms WHERE ordinal=1').fetchone()[0]
        counts = self.metadata_counts()
        with self.assertRaises(admission_fixture.DENIED):
            self.bind({'authority_id': original}, key='deny-original-region-on-composed-bytes')
        self.assertEqual(self.metadata_counts(), counts)
        bound = self.bind(self.exact_diff())
        self.assertEqual(bound['ordinal'], 3)
        with closing(self.store._conn()) as connection:
            arm = connection.execute('SELECT envelope_json FROM improvement_experiment_arms WHERE ordinal=3').fetchone()
            envelope = json.loads(arm[0])
            authority = self.plans.authoring.records._authority(connection, self.owner.brain_id, bound['authority_id'])
            self.assertEqual(authority['kind'], 'exact_diff')
            self.assertEqual(authority['candidate_id'], self.candidate['id'])
            self.assertEqual(envelope['semantic_status'], 'unreviewed')
        frozen = self.frozen(bound)
        semantic = self.semantic()
        views = EffectiveViews(self.plans, semantic)
        counts = self.metadata_counts()
        with self.assertRaises(admission_fixture.DENIED):
            views.freeze_comparison(self.owner, frozen['comparison_id'], expected_generation=self.generation(),
                                    event_key='no-inherited-semantic-pass-for-compose')
        self.assertEqual(self.metadata_counts(), counts)
        with closing(self.store._conn()) as connection:
            comparison = connection.execute('SELECT * FROM improvement_comparisons WHERE id=?', (frozen['comparison_id'],)).fetchone()
            matrix = json.loads(self.assets.blobs.read(self.owner.brain_id, comparison['matrix_blob_hash']))
        self.assertEqual(matrix['ordinal'], 3)
        # Legacy admission must not let the baseline half of arm3 bypass fresh
        # semantic/view checks. No fake available native gate is used here.
        import improvement_experiment_protocol as protocol
        baseline = next(position for position in range(comparison['cell_count'])
                        if protocol.matrix_cell(matrix, position)['variant'] == 'baseline')
        with patch.object(ClaudeTrialAdapter, 'verify', side_effect=AssertionError('Unreviewed arm3 reached native verifier')):
            with self.assertRaises(admission_fixture.DENIED):
                ExperimentAdmission(self.plans).admit(self.owner, self.saved['experiment_id'], frozen['comparison_id'], baseline,
                    expected_generation=self.generation(), event_key='deny-unreviewed-composed-baseline-fallback')
        self.assertEqual(self.metadata_counts(), counts)
        self.assertEqual(self.semantic_queries, 0)

    async def test_real_selector_requires_new_tuning_evidence_and_keeps_baseline_available(self):
        await self.published()
        bound = self.bind(self.exact_diff())
        self.frozen(bound)
        counts, generation = self.metadata_counts(), self.generation()
        claims = self.rows('improvement_qualification_claims')
        try:
            with self.assertRaisesRegex(PermissionError, 'report_unavailable'):
                self.plans.select(self.owner, self.saved['experiment_id'], 'candidate', ordinal=3,
                    expected_generation=generation, event_key='deny-composed-selection-without-new-report')
        except ValueError as error:
            self.fail('Actual selector rejects supported third-arm shape before evidence gate: ' + str(error))
        with self.assertRaisesRegex(PermissionError, 'final_selection_unavailable'):
            self.plans.freeze(self.owner, self.saved['experiment_id'], 3, 'final',
                expected_generation=generation, event_key='deny-composed-final-without-selection')
        self.assertEqual(self.metadata_counts(), counts)
        self.assertEqual(self.rows('improvement_experiment_selections'), [])
        self.assertEqual(self.rows('improvement_qualification_claims'), claims)
        key = 'owner-keep-baseline-after-composed-draft'
        kept = self.plans.select(self.owner, self.saved['experiment_id'], 'keep_base', ordinal=None,
            expected_generation=generation, event_key=key)
        selection, = self.rows('improvement_experiment_selections')
        self.assertEqual((selection['choice'], selection['ordinal']), ('keep_base', None))
        self.assertEqual((kept['phase'], kept['stop_kind']), ('stopping', 'completed'))
        self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='off-after-composed-baseline-choice')
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Historical baseline choice cannot decrypt')):
            self.assertEqual(self.plans.select(self.owner, self.saved['experiment_id'], 'keep_base', ordinal=None,
                expected_generation=generation, event_key=key), kept)
        self.assertEqual((self.queries, self.semantic_queries), (1, 0))

    async def test_same_brain_owner_publisher_has_consistent_actual_compose_actor_lineage(self):
        from improvement_experiment_lineage import _composed_owner
        await self.published(publisher_id='second-trusted-owner')
        publication, = self.rows('improvement_compositions')
        with closing(self.store._conn()) as connection:
            authorization = connection.execute('SELECT * FROM improvement_compose_authorizations WHERE id=?',
                (publication['authorization_id'],)).fetchone()
            event = connection.execute('SELECT * FROM improvement_events WHERE event_key=?',
                (self.candidate['owner_event_key'],)).fetchone()
            self.assertNotEqual(authorization['actor'], event['actor'])
            self.assertEqual(event['actor'], 'owner:second-trusted-owner')
            definition = json.loads(connection.execute('SELECT definition_json FROM improvement_experiments').fetchone()[0])
            try:
                _composed_owner(connection, self.owner.brain_id, self.candidate, definition)
            except PermissionError as error:
                self.fail('Actual same-brain owner publication is unreadable: ' + str(error))
            connection.execute('SAVEPOINT call_drift')
            try:
                connection.execute("UPDATE agent_calls SET mirror_ref='improvement_operation:foreign' WHERE purpose='improve_compose'")
                with self.assertRaises(IM.ConflictError):
                    _composed_owner(connection, self.owner.brain_id, self.candidate, definition)
            finally:
                connection.execute('ROLLBACK TO call_drift')
                connection.execute('RELEASE call_drift')
        self.assertEqual((self.queries, self.semantic_queries), (1, 0))

    async def test_fresh_semantic_exact_view_and_actual_trial_ownership_preserve_typed_three_cold_lineage(self):
        from improvement_claude import ClaudeTrialAdapter
        from improvement_comparison_schedule import ComparisonSchedule
        from improvement_view_admission import ViewExperimentAdmission
        from improvement_view_lineage import load_view_lineage
        await self.published()
        bound = self.bind(self.exact_diff())
        frozen = self.frozen(bound)
        semantic = self.semantic()
        reviewed = await semantic.review(self.owner, self.candidate['id'], expected_generation=self.generation(),
                                         event_key='independent-review-composed-draft')
        evidence = semantic.current_evidence(self.owner, self.candidate['id'])
        self.assertEqual(evidence['receipt_id'], reviewed['receipt_id'])
        self.assertEqual(evidence['assessment']['verdict'], 'pass')
        self.assertEqual(evidence['dependencies']['verdict'], 'pass')
        self.assertEqual(evidence['native_result_version'], 2)
        self.assertEqual(evidence['native_verdict'], 'unknown')
        self.assertEqual(evidence['verdict'], 'unknown', 'Do not promote observational unknowns to an overall pass')
        checks = {item['id']: item['verdict'] for item in evidence['native_checks']}
        for key in ('native_qualification', 'native_trace', 'native_authorization', 'native_input_delivery'):
            self.assertEqual(checks[key], 'pass', 'Explicit unexecuted synthetic storage predicate only')
        views = EffectiveViews(self.plans, semantic)
        metadata = views.freeze_comparison(self.owner, frozen['comparison_id'], expected_generation=self.generation(),
                                           event_key='owner-freeze-independent-composed-view')
        for variant in ('baseline', 'candidate'):
            resolved = views.load_current(self.owner, frozen['comparison_id'], variant)
            self.assertEqual(resolved.manifest['arm_ordinal'], 3)
            self.assertEqual(resolved.manifest['semantic']['receipt_id'], reviewed['receipt_id'])
            self.assertEqual(resolved.observational_unknowns, ('actual_input_use', 'actual_reasoning'))
            self.assertEqual(resolved.content, self.assets.blobs.read(self.owner.brain_id,
                self.candidate['base_hash'] if variant == 'baseline' else self.candidate['content_hash']))
        trials = self.plans.admission.trials
        admission = ViewExperimentAdmission(self.plans, views, ComparisonSchedule(self.plans, trials))
        counts = self.metadata_counts()
        with patch.object(ClaudeTrialAdapter, 'verify', return_value={'supported': False}):
            with self.assertRaises(ValueError):
                admission.admit_next(self.owner, self.saved['experiment_id'], frozen['comparison_id'],
                    expected_generation=self.generation(), event_key='unqualified-composed-view-refused')
        self.assertEqual(self.metadata_counts(), counts)
        # Declared verifier/format control only: real Trial/Call/link/lease and
        # workspace materialization, never a query or source qualification.
        with patch.object(ClaudeTrialAdapter, 'verify', return_value={'supported': True, 'capability_hash': 'c' * 64}):
            admitted = admission.admit_next(self.owner, self.saved['experiment_id'], frozen['comparison_id'],
                expected_generation=self.generation(), event_key='synthetic-owned-composed-view-admission')
        request = admitted.request
        self.assertEqual((request['version'], request['lineage']['arm_ordinal']), (4, 3))
        self.assertEqual(request['lineage']['candidate_id'], self.candidate['id'])
        self.assertEqual(request['view']['binding_hash'], metadata['binding_hash'])
        claimed = trials.claim(self.owner, admitted.trial_id, expected_generation=1)
        receipt = None
        try:
            context = self.execution.host.context_loader(self.owner, request)
            with patch('improvement_native_formats.input_version', side_effect=lambda pin, surface:
                       {'baseline': 5, 'operation': 2, 'view': 4}[surface]):
                manifest = trials.materialize(self.owner, admitted.trial_id, expected_generation=claimed['generation'],
                    lease_token=claimed['lease_token'], baseline_context=context)
                self.assertEqual(manifest['version'], 4)
                self.assertEqual(manifest['effective_view'], request['view'])
                resolved = views.load_current(self.owner, frozen['comparison_id'], request['variant'])
                self.assertEqual(manifest['assets'][0]['content'].encode(), resolved.content)
                receipt = trials.workspace.prepare(admitted.trial_id, 1, manifest)
                prepared = trials.prepared(self.owner, admitted.trial_id, expected_generation=claimed['generation'],
                    lease_token=claimed['lease_token'], receipt=receipt)
            self.assertEqual(prepared['status'], 'prepared')
            with closing(self.store._conn()) as connection:
                proof = load_view_lineage(connection, self.owner.brain_id, request, blobs=self.assets.blobs,
                    current=True, require_link=True, trial_id=admitted.trial_id)
                call = connection.execute('SELECT c.* FROM agent_calls c JOIN improvement_trial_attempts a ON a.call_id=c.id '
                    'WHERE a.trial_id=?', (admitted.trial_id,)).fetchone()
            self.assertEqual(proof['definition']['decision_policy']['multiple_tests'], 3)
            self.assertEqual(proof['arm']['ordinal'], 3)
            self.assertEqual(call['purpose'], 'improve_probe')
            self.assertIsNone(call['engine_at'])
        finally:
            latest = trials.get(self.owner, admitted.trial_id)
            trials.abort(self.owner, admitted.trial_id, expected_generation=latest['generation'],
                         lease_token=claimed['lease_token'], reason='cancelled')
            trials.cleanup_terminal(self.owner, admitted.trial_id)
        self.plans.authoring.records.revoke_authority(self.owner, bound['authority_id'], expected_generation=1,
                                                      event_key='revoke-independent-composed-exact-diff')
        with self.assertRaises(admission_fixture.DENIED):
            views.load_current(self.owner, frozen['comparison_id'], 'candidate')
        with patch.object(self.execution.host, '_snapshot_observe', side_effect=AssertionError('Cold lineage cannot observe sources')), \
                closing(self.store._conn()) as connection:
            cold = load_view_lineage(connection, self.owner.brain_id, request, blobs=self.assets.blobs,
                current=False, require_link=True, trial_id=admitted.trial_id)
        self.assertEqual(cold['arm']['ordinal'], 3)
        with closing(self.store._conn()) as connection:
            owner_event = connection.execute("SELECT 1 FROM improvement_events WHERE operation='skill_candidate_owner_request' "
                'AND json_extract(result_json,\'$.candidate_id\')=?', (self.candidate['id'],)).fetchone()
        self.assertIsNone(owner_event, 'Typed composition must not forge an ordinary owner-request event')
        self.assertEqual((self.queries, self.semantic_queries), (1, 1))


if __name__ == '__main__':
    unittest.main()
