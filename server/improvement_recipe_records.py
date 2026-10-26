"""Cold owner metadata and revocable state; no body/source/native access."""
from __future__ import annotations

import time
from contextlib import closing

import improvement_store as IM
from improvement_experiments import _generation, _identifier
from improvement_trial_records import _brain

_METADATA = ('manifest_hash', 'experiment_id', 'context_id', 'target_id', 'base_revision_id', 'candidate_id',
    'comparison_report_id', 'scope_hash', 'engine_config_hash', 'owner_rule_hash', 'target_protected_hash',
    'language', 'verdict', 'checked_at', 'expires_at', 'created_at')


class RecipeRecords:
    def __init__(self, assets):
        if type(assets) is not IM.ImprovementStore:
            raise TypeError('concrete_recipe_assets_required')
        self.assets, self.store = assets, assets.store

    def _available(self):
        return IM._schema_version(self.store) in (9, 10, 11, 12, 13, 14, 15, 16, 17)

    @staticmethod
    def _row(connection, brain, recipe_id):
        row = connection.execute('SELECT * FROM improvement_recipes WHERE id=? AND brain_id=?', (recipe_id, brain)).fetchone()
        if row is None:
            raise PermissionError('recipe_unavailable')
        return row

    @staticmethod
    def _public(connection, row):
        state = connection.execute('SELECT * FROM improvement_recipe_states WHERE recipe_id=? AND brain_id=?',
                                    (row['id'], row['brain_id'])).fetchone()
        grant = connection.execute('SELECT * FROM improvement_trial_context_grants WHERE context_id=? AND brain_id=?',
                                    (row['context_id'], row['brain_id'])).fetchone()
        status = 'unavailable' if state is None or grant is None else state['status']
        source = 'unavailable' if grant is None or state is None else grant['status']
        reason = 'source_revoked' if status == 'unavailable' else status if status in ('revoked', 'expired', 'superseded', 'erased') else (
            'expired' if row['expires_at'] <= time.time() else 'source_revoked' if source != 'active' else None)
        return {'recipe_id': row['id'], **{key: row[key] for key in _METADATA},
            'record_status': status, 'generation': None if state is None else state['generation'],
            'reason': None if state is None else state['reason'], 'successor_id': None if state is None else state['successor_id'],
            'source_grant_status': source, 'unavailability_reason': reason,
            'authority_status': 'not_checked', 'business_proof': False}

    def get(self, principal, recipe_id):
        brain = _brain(principal)
        _identifier(recipe_id)
        if not self._available():
            raise PermissionError('recipe_unavailable')
        with closing(self.store._conn()) as connection:
            return self._public(connection, self._row(connection, brain, recipe_id))

    def list(self, principal, *, cursor=None, limit=50):
        brain = _brain(principal)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('invalid_recipe_limit')
        if cursor is not None:
            _identifier(cursor)
        if not self._available():
            return {'items': [], 'next_cursor': None}
        with closing(self.store._conn()) as connection:
            rows = connection.execute('SELECT * FROM improvement_recipes WHERE brain_id=? AND id>? ORDER BY id LIMIT ?',
                                      (brain, cursor or '', limit + 1)).fetchall()
            items = [self._public(connection, row) for row in rows[:limit]]
            return {'items': items, 'next_cursor': items[-1]['recipe_id'] if len(rows) > limit else None}

    def _transition(self, principal, recipe_id, successor_id, expected_generation, event_key):
        from resonance_store import GoalStore
        brain = _brain(principal)
        _identifier(recipe_id)
        _generation(expected_generation)
        if successor_id is not None:
            _identifier(successor_id)
        if type(self.store) is not GoalStore or not self._available():
            raise PermissionError('recipe_writer_unavailable')
        operation = 'recipe_revoke' if successor_id is None else 'recipe_supersede'
        payload = {'recipe_id': recipe_id, 'expected_generation': expected_generation}
        if successor_id is not None:
            payload['successor_id'] = successor_id
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, operation, payload)
            if replay is not None:
                return replay
            row = self._row(connection, brain, recipe_id)
            state = connection.execute('SELECT * FROM improvement_recipe_states WHERE recipe_id=? AND brain_id=?',
                                       (recipe_id, brain)).fetchone()
            if state is None or state['generation'] != expected_generation or state['status'] != 'active':
                raise IM.ConflictError('recipe_generation_stale')
            if successor_id is not None:
                successor = self._row(connection, brain, successor_id)
                current = self._public(connection, successor)
                if (successor_id == recipe_id or current['record_status'] != 'active'
                        or current['unavailability_reason'] is not None
                        or any(row[key] != successor[key] for key in
                               ('target_id', 'scope_hash', 'engine_config_hash', 'language', 'owner_rule_hash'))):
                    raise PermissionError('recipe_successor_unavailable')
            status = 'revoked' if successor_id is None else 'superseded'
            reason = 'owner_revoked' if successor_id is None else 'superseded'
            connection.execute('UPDATE improvement_recipe_states SET status=?,generation=generation+1,reason=?,successor_id=?,changed_at=? '
                'WHERE recipe_id=? AND brain_id=? AND generation=?',
                (status, reason, successor_id, max(time.time(), row['created_at']), recipe_id, brain, expected_generation))
            result = {'recipe_id': recipe_id, 'generation': expected_generation + 1, 'status': status,
                      'authority_status': 'not_checked', 'business_proof': False}
            if successor_id is not None:
                result['successor_id'] = successor_id
            self.assets._event(connection, principal, event_key, operation, payload, result)
            return result

    def revoke(self, principal, recipe_id, *, expected_generation, event_key):
        return self._transition(principal, recipe_id, None, expected_generation, event_key)

    def supersede(self, principal, recipe_id, successor_id, *, expected_generation, event_key):
        return self._transition(principal, recipe_id, successor_id, expected_generation, event_key)
