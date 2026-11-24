"""Phạm vi đợt bật (JAVIS_DRIVE_GUARD_PILOT) của guard Drive.

Bảo đảm:
- env được truyền vào wrap() là nguồn duy nhất khi có (không đọc ngầm os.environ).
- Đợt hợp lệ: chỉ các slug được liệt kê bị guard; Agent khác đi thẳng (hành vi như trước).
- Đợt thiếu / sai / dùng ký tự đại diện ('*'): guard KHÔNG áp lên ai (không chặn diện rộng ngoài ý muốn), có log lỗi.
- off: không bao giờ can thiệp. shadow: không chặn, chỉ ghi log.
- actor không xác định: vẫn bị quyết định khi đợt hợp lệ (fail-closed).
"""
import asyncio
import io
import os
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import drive_guard_hub as dhub  # noqa: E402
import drive_write_guard as g  # noqa: E402

LEADERS = "javis-vu,alex-learning-coach,alex-manager-affiliate"
SPECIALIST = "chuyen-vien-x"
TRASH = {"tools": [{"tool_slug": "GOOGLEDRIVE_TRASH_FILE", "account": "SYN-ACC",
                    "arguments": {"file_id": "SYN-OUTSIDE"}}]}
ENV = {"JAVIS_DRIVE_WRITE_GUARD": "enforce", "JAVIS_DRIVE_GUARD_PILOT": LEADERS}


async def _no_parents(seeds):
    return {}


class _Base(unittest.TestCase):
    def setUp(self):
        self._saved_prefetch = dhub.prefetch_parents
        dhub.prefetch_parents = _no_parents
        self._saved_env = os.environ.pop(g.PILOT_ENV, None)
        self._saved_mode = os.environ.pop(g.MODE_ENV, None)

    def tearDown(self):
        dhub.prefetch_parents = self._saved_prefetch
        os.environ.pop(g.PILOT_ENV, None)
        os.environ.pop(g.MODE_ENV, None)
        if self._saved_env is not None:
            os.environ[g.PILOT_ENV] = self._saved_env
        if self._saved_mode is not None:
            os.environ[g.MODE_ENV] = self._saved_mode

    def _go(self, actor, env, args=TRASH):
        calls = []

        async def call(a):
            calls.append(a)
            return "OK"
        buf = io.StringIO()
        with mock.patch.object(dhub, "_actor", return_value=actor), redirect_stderr(buf):
            wrapped = dhub.wrap(call, {"connector_id": "composio"}, "COMPOSIO_MULTI_EXECUTE_TOOL", "fn", env=env)
            out = asyncio.run(wrapped(args))
        return out, calls, buf.getvalue()

    def assertGuarded(self, out, calls):
        self.assertTrue(str(out).startswith("ERROR:"), out)
        self.assertEqual(calls, [])

    def assertPassthrough(self, out, calls):
        self.assertEqual(out, "OK")
        self.assertEqual(len(calls), 1)


class PilotStatusTests(_Base):
    def test_unset_empty_and_whitespace(self):
        self.assertEqual(g.pilot_status({})[0], "unset")
        self.assertEqual(g.pilot_status({g.PILOT_ENV: " , "})[0], "unset")

    def test_valid_slugs(self):
        state, actors = g.pilot_status({g.PILOT_ENV: LEADERS})
        self.assertEqual(state, "ok")
        self.assertEqual(actors, frozenset(LEADERS.split(",")))

    def test_wildcard_and_bad_names_are_invalid(self):
        for raw in ("*", "javis-vu,*", "Javis-VU", "a b", "../x"):
            self.assertEqual(g.pilot_status({g.PILOT_ENV: raw})[0], "invalid", raw)
            self.assertIsNone(g.pilot_actors({g.PILOT_ENV: raw}), raw)


class PilotScopeTests(_Base):
    def test_leader_in_pilot_is_guarded(self):
        out, calls, _ = self._go("javis-vu", ENV)
        self.assertGuarded(out, calls)

    def test_specialist_outside_pilot_is_untouched(self):
        out, calls, log = self._go(SPECIALIST, ENV)
        self.assertPassthrough(out, calls)
        self.assertNotIn("DENY", log)

    def test_unknown_actor_is_decided_not_skipped(self):
        out, calls, _ = self._go(None, ENV)
        self.assertGuarded(out, calls)

    def test_env_argument_wins_over_os_environ(self):
        # os.environ nói Agent này KHÔNG nằm trong đợt, nhưng env được truyền vào nói có: phải dùng env.
        os.environ[g.PILOT_ENV] = "someone-else"
        out, calls, _ = self._go("javis-vu", ENV)
        self.assertGuarded(out, calls)

    def test_env_without_pilot_does_not_fall_back_to_os_environ_widening(self):
        # env truyền vào KHÔNG có pilot: guard không áp lên ai (config lỗi), kể cả khi os.environ có đợt.
        os.environ[g.PILOT_ENV] = LEADERS
        out, calls, log = self._go("javis-vu", {"JAVIS_DRIVE_WRITE_GUARD": "enforce"})
        self.assertPassthrough(out, calls)
        self.assertIn("CẤU HÌNH LỖI", log)


class PilotFailSafeTests(_Base):
    def test_enforce_with_missing_pilot_applies_to_nobody(self):
        out, calls, log = self._go("javis-vu", {"JAVIS_DRIVE_WRITE_GUARD": "enforce"})
        self.assertPassthrough(out, calls)
        self.assertIn("CẤU HÌNH LỖI", log)
        self.assertIn("unset", log)

    def test_enforce_with_wildcard_pilot_applies_to_nobody(self):
        out, calls, log = self._go(SPECIALIST, {"JAVIS_DRIVE_WRITE_GUARD": "enforce",
                                                "JAVIS_DRIVE_GUARD_PILOT": "*"})
        self.assertPassthrough(out, calls)
        self.assertIn("invalid", log)

    def test_shadow_with_missing_pilot_applies_to_nobody(self):
        out, calls, _ = self._go("javis-vu", {"JAVIS_DRIVE_WRITE_GUARD": "shadow"})
        self.assertPassthrough(out, calls)

    def test_guard_off_never_intervenes(self):
        out, calls, _ = self._go("javis-vu", {"JAVIS_DRIVE_WRITE_GUARD": "off", "JAVIS_DRIVE_GUARD_PILOT": LEADERS})
        self.assertPassthrough(out, calls)

    def test_shadow_with_valid_pilot_logs_but_calls_through(self):
        out, calls, log = self._go("javis-vu", {"JAVIS_DRIVE_WRITE_GUARD": "shadow",
                                                "JAVIS_DRIVE_GUARD_PILOT": LEADERS})
        self.assertPassthrough(out, calls)
        self.assertIn("DENY", log)


if __name__ == "__main__":
    unittest.main()
