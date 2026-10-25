"""Fresh source authority for historical procedures, separate from execution grants."""
from __future__ import annotations

import inspect
import json
import re
import sys
import types
from contextlib import closing

import improvement_cases as IC
import improvement_store as IM
from improvement_blobs import AssetUnavailable, RevisionBlobs
from improvement_claude import ClaudeTrialAdapter
from improvement_operation_schema import assert_installed
from improvement_trial_dashboard import DashboardContextCapture
from improvement_trial_file_sources import BrainFileFixtures, _root as owner_root, _authority
from improvement_trial_host import HostContextStore, TARGET_FIELDS
from improvement_trial_records import HostContextRecords, _brain
from improvement_trial_semantics import validate_capture
from improvement_trial_service import _RetainedDashboard, dashboard_host
from improvement_trial_sources import validate_inventory
from resonance_store import GoalStore

_SKILL = re.compile(r'skills/[a-z0-9][a-z0-9_-]{0,127}/SKILL\.md\Z')


class RecipeSourceUnavailable(AssetUnavailable):
    """The original source no longer has fresh external authority."""


def owner_rule_hash(capture):
    capture = validate_capture(capture)
    if capture['baseline_context']['coverage'] != 'complete':
        raise PermissionError('recipe_complete_semantic_capture_required')
    return IM._hash([{key: source[key] for key in
        ('kind', 'ref', 'locator', 'required', 'present', 'hash', 'projection_hash')}
        for source in capture['sources'] if source['role'] == 'protected'])


def _callback(value):
    function = getattr(value, '__func__', value)
    return (getattr(value, '__self__', None), function, getattr(function, '__code__', None))


class RecipeSources:
    def __init__(self, host: HostContextStore):
        if (type(host) is not HostContextStore or type(host.assets) is not IM.ImprovementStore
                or type(host.store) is not GoalStore or type(host.blobs) is not RevisionBlobs
                or host.assets.store is not host.store or host.assets.blobs is not host.blobs
                or type(host.context_capture) is not _RetainedDashboard
                or type(host.context_capture._collector) is not DashboardContextCapture
                or type(host.fixture_observer) is not BrainFileFixtures):
            raise TypeError('concrete_recipe_sources_required')
        self.host, self.store = host, host.store
        retained, collector, fixtures = host.context_capture, host.context_capture._collector, host.fixture_observer
        # Concrete collectors cannot confer authority on caller-supplied callbacks.
        factory_codes = {code.co_name: code for code in dashboard_host.__code__.co_consts
                         if isinstance(code, types.CodeType)}
        for callback, name in ((retained._check, 'current_sources'),
                               (host.selected_engine, 'selected_engine'), (host.target_observer, 'targets')):
            if type(callback) is not types.FunctionType or callback.__code__ is not factory_codes[name]:
                raise TypeError('concrete_recipe_sources_required')
        engine_closure = inspect.getclosurevars(host.selected_engine).nonlocals
        target_closure = inspect.getclosurevars(host.target_observer).nonlocals
        check_closure = inspect.getclosurevars(retained._check).nonlocals
        if (engine_closure.get('current_sources') is not retained._check
                or target_closure.get('current_sources') is not retained._check
                or target_closure.get('assets') is not host.assets
                or check_closure.get('assets') is not host.assets
                or engine_closure.get('main') is not collector.host
                or check_closure.get('main') is not collector.host):
            raise TypeError('concrete_recipe_sources_required')
        self._modules = {name: sys.modules[name] for name in ('improvement_trial_service',
            'improvement_trial_dashboard', 'improvement_trial_host', 'improvement_trial_records',
            'improvement_trial_file_sources')}
        self._members = [(self, 'host', host), (self, 'store', host.store)]
        self._members += [(host, name, getattr(host, name)) for name in
            ('assets', 'store', 'blobs', 'context_capture', 'selected_engine', 'target_observer', 'fixture_observer')]
        self._members += [(host.assets, 'store', host.store), (host.assets, 'blobs', host.blobs),
            (retained, '_collector', collector), (retained, '_check', retained._check),
            (host.blobs, 'encrypt', host.blobs.encrypt), (host.blobs, 'decrypt', host.blobs.decrypt)]
        self._members += [(collector, name, getattr(collector, name)) for name in ('host', 'sql', 'plugins')]
        self._paths = [(host.store, 'path', host.store.path), (host.blobs, 'root', host.blobs.root)]
        self._paths += [(collector, name, getattr(collector, name)) for name in
            ('project_root', 'state_root', 'native_user_root')]
        self._callbacks = [(obj, name, _callback(getattr(obj, name))) for obj, names in (
            (host, ('_decode', 'selected_engine', 'target_observer')), (host.store, ('_conn',)),
            (host.blobs, ('read',)),
            (retained, ('_check', '__call__', 'revalidate', 'recipe_capture')),
            (collector, ('__call__', 'revalidate', 'recipe_capture', '_capture', '_scan')),
            (fixtures, ('__call__', '_capture', 'capture'))) for name in names]
        self._retained()

    def _retained(self):
        if (any(sys.modules.get(name) is not module for name, module in self._modules.items())
                or any(getattr(obj, name, None) is not value for obj, name, value in self._members)
                or any(getattr(obj, name, None) != value for obj, name, value in self._paths)
                or any(_callback(getattr(obj, name, None)) != value for obj, name, value in self._callbacks)):
            raise IM.ConflictError('recipe_source_dependencies_changed')
        self.host.context_capture._check()

    def _state(self, connection, principal, context_id, expected_generation):
        """SQL-only fences, also usable in a destination owner's transaction."""
        brain = _brain(principal)
        if type(context_id) is not str or not IC._ID.fullmatch(context_id):
            raise ValueError('invalid_recipe_context')
        if type(expected_generation) is not int or expected_generation < 1:
            raise ValueError('invalid_recipe_context_generation')
        assert_installed(connection)
        context = connection.execute('SELECT * FROM improvement_trial_contexts WHERE id=? AND brain_id=?',
                                     (context_id, brain)).fetchone()
        if context is None:
            raise PermissionError('recipe_context_unavailable')
        context = dict(context)
        grant = connection.execute('SELECT * FROM improvement_trial_context_grants WHERE context_id=? AND brain_id=?',
                                   (context_id, brain)).fetchone()
        if grant is None:
            raise RecipeSourceUnavailable('recipe_source_grant_unavailable')
        grant = dict(grant)
        if grant['generation'] != expected_generation:
            raise IM.ConflictError('recipe_context_generation_stale')
        if grant['status'] != 'active':
            raise RecipeSourceUnavailable('recipe_source_grant_unavailable')
        policy_row = connection.execute('SELECT * FROM improvement_policies WHERE brain_id=?', (brain,)).fetchone()
        policy = dict(policy_row) if policy_row is not None else self.host.assets._policy(connection, brain)
        if policy['mode'] != 'suggest':
            raise RecipeSourceUnavailable('recipe_suggest_required')
        generations = json.loads(context['target_generations_json'])
        if (type(generations) is not dict or not 1 <= len(generations) <= 20
                or any(type(key) is not str or not IC._ID.fullmatch(key) or type(value) is not int or value < 1
                       for key, value in generations.items())):
            raise AssetUnavailable('recipe_context_targets_corrupt')
        targets = [dict(row) for row in connection.execute(
            'SELECT * FROM improvement_targets WHERE brain_id=? AND id IN (' + ','.join('?' for _ in generations) +
            ") AND status='live' AND kind='skill' AND ownership IN ('user_protected','user_managed') ORDER BY id",
            (brain, *sorted(generations)))]
        if (len(targets) != len(generations) or any(not _SKILL.fullmatch(row['canonical_ref']) for row in targets)):
            raise RecipeSourceUnavailable('recipe_source_target_unavailable')
        for row in targets:
            revision = connection.execute('SELECT * FROM improvement_revisions WHERE id=? AND target_id=? AND brain_id=?',
                (row['current_revision_id'], row['id'], brain)).fetchone()
            if revision is None or revision['content_hash'] != row['source_hash']:
                raise RecipeSourceUnavailable('recipe_source_target_unavailable')
        return {'context': context, 'grant': grant, 'policy': policy, 'targets': targets}

    def _external(self, callback, *args, **kwargs):
        self._retained()
        try:
            value = callback(*args, **kwargs)
        except (ValueError, PermissionError, OSError, IM.ConflictError, AssetUnavailable) as error:
            self._retained()
            raise RecipeSourceUnavailable('recipe_external_source_unavailable') from error
        self._retained()
        return IC._frozen(value)

    @staticmethod
    def _authorities(principal, targets):
        root = owner_root(principal)
        result = [{'target_id': target['id'], 'authority': _authority(root, target['canonical_ref'])}
                  for target in targets]
        if owner_root(principal) != root:
            raise PermissionError('recipe_target_root_changed')
        return result

    def _targets(self, principal, sql):
        expected = [{key: row[key] for key in TARGET_FIELDS} for row in sql['targets']]
        before = self._external(self._authorities, principal, expected)
        actual = self._external(self.host.target_observer, principal, [row['id'] for row in expected])
        after = self._external(self._authorities, principal, expected)
        if actual != expected or after != before:
            raise RecipeSourceUnavailable('recipe_current_target_changed')
        return actual, before

    def _engine(self):
        value = self._external(self.host.selected_engine)
        ClaudeTrialAdapter(value)  # Validate shape without native execution.
        if value['provider'] != 'anthropic-cli' or value['engine_id'] != 'claude-sdk':
            raise RecipeSourceUnavailable('recipe_engine_unavailable')
        return value

    def _binding(self, principal, sql, binding):
        """Authenticate historical membership; current revision equality is separate."""
        IC._fields(binding, {'capture', 'engine_config', 'targets', 'fixture_inventory', 'scope', 'grant'})
        capture = validate_capture(binding['capture'])
        language = capture['surface'].get('language')
        if capture['baseline_context']['coverage'] != 'complete' or language not in ('vi', 'en'):
            raise PermissionError('recipe_complete_semantic_capture_required')
        context, scope, grant = sql['context'], binding['scope'], binding['grant']
        IC._fields(scope, {'version', 'brain_id', 'experiment_id', 'surface', 'target_ids', 'source_plan_hash', 'source_refs'})
        IC._fields(grant, {'version', 'scope_hash', 'sources', 'targets', 'engine_config_hash',
                          'baseline_context_hash', 'policy_version', 'actor', 'fixture_inventory'})
        generations = json.loads(context['target_generations_json'])
        refs = scope['source_refs']
        inventory = validate_inventory(binding['fixture_inventory'])
        if (type(refs) is not list or not refs or any(type(ref) is not str for ref in refs)
                or refs != sorted(set(refs)) or len(inventory) != len(refs)
                or binding['fixture_inventory'] != inventory
                or {entry['source_ref'] for entry in inventory} != set(refs)
                or any(entry['freshness_policy'] != 'require_current_version'
                       or not entry['source_ref'].startswith('brain-file:') for entry in inventory)):
            raise PermissionError('recipe_source_lifetime_unsupported')
        targets = binding['targets']
        if type(targets) is not list or len(targets) != len(generations):
            raise AssetUnavailable('recipe_context_membership_corrupt')
        for target in targets:
            IC._fields(target, TARGET_FIELDS)
        if (scope != {'version': 1, 'brain_id': _brain(principal), 'experiment_id': context['experiment_id'],
                'surface': capture['surface'], 'target_ids': sorted(generations),
                'source_plan_hash': capture['plan_hash'], 'source_refs': refs}
                or type(scope['version']) is not int or type(grant['version']) is not int or grant['version'] != 1
                or targets != sorted(targets, key=lambda item: item['id'])
                or {target['id']: target['generation'] for target in targets} != generations
                or grant != {'version': 1, 'scope_hash': context['scope_hash'], 'sources': capture['sources'],
                    'targets': targets, 'engine_config_hash': context['engine_config_hash'],
                    'baseline_context_hash': context['context_hash'], 'policy_version': context['policy_version'],
                    'actor': principal.by, 'fixture_inventory': inventory}
                or context['request_hash'] != IM._hash({'experiment_id': context['experiment_id'],
                    'surface': capture['surface'], 'target_ids': scope['target_ids'], 'source_refs': refs})):
            raise AssetUnavailable('recipe_context_membership_corrupt')
        for old, current in zip(targets, sql['targets']):
            if any(old[key] != current[key] for key in ('id', 'kind', 'canonical_ref', 'ownership')):
                raise RecipeSourceUnavailable('recipe_original_target_changed')
        return capture, inventory, owner_rule_hash(capture), language

    def capture(self, principal, context_id, *, expected_generation):
        self._retained()
        with closing(self.store._conn()) as connection:
            sql = self._state(connection, principal, context_id, expected_generation)
        targets, target_authorities = self._targets(principal, sql)
        engine = self._engine()
        binding = HostContextRecords._decode(self.host, sql['context'])
        self._retained()
        old_capture, inventory, rules, language = self._binding(principal, sql, binding)
        if engine != binding['engine_config']:
            raise RecipeSourceUnavailable('recipe_engine_changed')

        def observe():
            current = self._external(self.host.context_capture.recipe_capture, principal, old_capture['surface'], targets,
                                     frozen_capture=old_capture)
            if owner_rule_hash(current) != rules:
                raise RecipeSourceUnavailable('recipe_owner_rules_changed')
            fixtures = self._external(self.host.fixture_observer, principal, binding['scope']['source_refs'],
                                      frozen_inventory=inventory)
            if fixtures != inventory:
                raise RecipeSourceUnavailable('recipe_fixture_inventory_changed')
            if self._engine() != engine or self._targets(principal, sql) != (targets, target_authorities):
                raise RecipeSourceUnavailable('recipe_current_source_changed')
            return current

        current = observe()
        if observe() != current:
            raise RecipeSourceUnavailable('recipe_current_source_changed')
        self._retained()
        with closing(self.store._conn()) as connection:
            if self._state(connection, principal, context_id, expected_generation) != sql:
                raise RecipeSourceUnavailable('recipe_source_sql_changed')
        result = {'version': 1, 'context_id': context_id, 'context_generation': expected_generation,
            'binding_hash': sql['context']['binding_hash'], 'source_scope_hash': sql['context']['scope_hash'],
            'engine_config_hash': sql['context']['engine_config_hash'], 'language': language, 'owner_rule_hash': rules,
            'binding': binding, 'current_capture': current, 'current_targets': targets, 'target_authorities': target_authorities,
            'fixture_inventory': inventory, 'sql': sql}
        return {**result, 'authority_hash': IM._hash(result)}

    def check(self, principal, snapshot):
        frozen = IC._frozen(snapshot)
        if (type(frozen) is not dict or set(frozen) != {'version', 'context_id', 'context_generation', 'binding_hash',
                'source_scope_hash', 'engine_config_hash', 'language', 'owner_rule_hash', 'binding', 'current_capture',
                'current_targets', 'target_authorities', 'fixture_inventory', 'sql', 'authority_hash'}
                or type(frozen['version']) is not int or frozen['version'] != 1
                or frozen['authority_hash'] != IM._hash({key: value for key, value in frozen.items() if key != 'authority_hash'})):
            raise IM.ConflictError('recipe_source_snapshot_corrupt')
        if self.capture(principal, frozen['context_id'], expected_generation=frozen['context_generation']) != frozen:
            raise IM.ConflictError('recipe_source_snapshot_changed')
