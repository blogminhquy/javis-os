"""Actor của bước nhóm: chỉ thành viên đang hoạt động, đúng slug; trưởng nhóm/lạ -> "" (fail-closed)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import team_runner as tr  # noqa: E402


class _Teams:
    def __init__(self, active):
        self.active = set(active)

    def is_active_member(self, team_id, key):
        return (team_id, key) in self.active


class _Stub:
    def __init__(self, active):
        self.teams = _Teams(active)


def step_actor(active, team_id, key):
    return tr.TeamRunner._step_actor(_Stub(active), team_id, key)


class StepActorTests(unittest.TestCase):
    def test_active_member_slug_allowed(self):
        self.assertEqual(step_actor({("t1", "agent-a")}, "t1", "agent-a"), "agent-a")

    def test_leader_slot_fail_closed(self):
        self.assertEqual(step_actor({("t1", tr.LEADER_SLOT)}, "t1", tr.LEADER_SLOT), "")

    def test_non_member_denied(self):
        self.assertEqual(step_actor(set(), "t1", "agent-a"), "")

    def test_member_of_other_team_denied(self):
        self.assertEqual(step_actor({("t2", "agent-a")}, "t1", "agent-a"), "")

    def test_bad_slug_denied(self):
        self.assertEqual(step_actor({("t1", "../x")}, "t1", "../x"), "")
        self.assertEqual(step_actor({("t1", "a b")}, "t1", "a b"), "")

    def test_none_fail_closed(self):
        self.assertEqual(step_actor({("t1", "agent-a")}, "t1", None), "")


if __name__ == "__main__":
    unittest.main()
