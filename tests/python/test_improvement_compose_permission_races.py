"""Late consent/source races over actual private host SQL/Fernet; no query."""
from _paths import ROOT, SERVER  # noqa: F401

import json
import time
import unittest
from unittest.mock import patch

import test_improvement_compose_permissions as permissions


class ComposePermissionRaceTests(unittest.TestCase):
    def setUp(self):
        self.f = permissions.ComposePermissionTests(); self.f.setUp()
        self.addCleanup(lambda: self.assertTrue(self.f.doCleanups(), 'Actual fixture cleanup failed'))

    def test_revoke_inside_last_source_guard_refuses_current_and_rolls_back_its_control(self):
        f = self.f
        saved = f.authorize()
        actual = f.service._fence
        changed = []
        def revoke(connection, principal, *args, **kwargs):
            result = actual(connection, principal, *args, **kwargs)
            connection.execute("UPDATE improvement_compose_grants SET status='revoked',generation=2,revoked_at=? "
                               'WHERE authorization_id=?', (time.time(), saved['authorization_id']))
            changed.append(True)
            return result
        events = f.rows('improvement_events')
        with patch.object(f.service, '_fence', side_effect=revoke), \
                self.assertRaises(permissions.DENIED), f.store._Tx(f.store) as connection:
            f.service.current(connection, f.owner, saved['authorization_id'])
        self.assertEqual(changed, [True])
        self.assertEqual(f.service.get(f.owner, saved['authorization_id']), saved)
        self.assertEqual(f.rows('improvement_events'), events)

    def test_source_drift_after_actual_encrypted_guard_write_cannot_publish_consent(self):
        f = self.f
        actual = f.assets.blobs.write
        protected = f.f.host_files.protected
        original = protected.read_bytes()
        changed = []
        def write(brain, raw):
            digest = actual(brain, raw)
            value = json.loads(raw)
            if type(value) is dict and value.get('kind') == 'compose_permission_guard':
                protected.write_bytes(original + b'\nLate owner protected-source control.\n')
                changed.append(digest)
            return digest
        try:
            with patch.object(f.assets.blobs, 'write', side_effect=write), self.assertRaises(permissions.DENIED):
                f.authorize()
            self.assertEqual(len(changed), 1)
            self.assertEqual(f.rows('improvement_compose_authorizations'), [])
            self.assertEqual(f.rows('improvement_compose_grants'), [])
            self.assertEqual(f.authorization_events(), [])
            self.assertEqual(len(f.f.input_events()), 1)
            self.assertEqual(f.rows('improvement_operations'), [])
        finally:
            protected.write_bytes(original)

    def test_revoke_during_tail_policy_read_cannot_escape_the_final_sql_fence(self):
        f = self.f
        saved = f.authorize()
        capture, policy = f.service._capture, f.service.inputs.reports._policy
        captures, changed = [], []
        def late_capture(connection, principal, *args, **kwargs):
            captures.append(True)
            if len(captures) != 2:
                return capture(connection, principal, *args, **kwargs)
            def revoke(value):
                result = policy(value)
                if not changed:
                    connection.execute("UPDATE improvement_compose_grants SET status='revoked',generation=2,revoked_at=? "
                                       'WHERE authorization_id=?', (time.time(), saved['authorization_id']))
                    changed.append(True)
                return result
            with patch.object(f.service.inputs.reports, '_policy', side_effect=revoke):
                return capture(connection, principal, *args, **kwargs)
        with patch.object(f.service, '_capture', side_effect=late_capture), \
                self.assertRaises(permissions.DENIED), f.store._Tx(f.store) as connection:
            f.service.current(connection, f.owner, saved['authorization_id'])
            self.fail('Current returned active consent after actual grant revoked during its tail policy read')
        self.assertEqual(changed, [True])
        self.assertEqual(f.service.get(f.owner, saved['authorization_id']), saved)


if __name__ == '__main__': unittest.main()
