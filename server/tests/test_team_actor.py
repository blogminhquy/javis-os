"""Actor của bước nhóm: chỉ thành viên đang hoạt động, đúng slug; trưởng nhóm/lạ -> "" (fail-closed)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import team_runner as tr  # noqa: E402


class _Teams:
    """Roster giả: active = {(team_id, agent_key, slug)}; key ag_ tách khỏi slug như DB thật."""
    def __init__(self, active):
        self.rows = {(t, k): {"status": "active", "slug_at_join": s} for t, k, s in active}

    def member(self, team_id, key):
        return self.rows.get((team_id, key))


class _Stub:
    def __init__(self, active):
        self.teams = _Teams(active)


def step_actor(active, team_id, key):
    # active: set of (team_id, agent_key, slug)
    return tr.TeamRunner._step_actor(_Stub(active), team_id, key)


class StepActorTests(unittest.TestCase):
    def test_active_member_slug_allowed(self):
        self.assertEqual(step_actor({("t1", "ag_1", "agent-a")}, "t1", "ag_1"), "agent-a")

    def test_agent_key_is_not_the_actor(self):
        self.assertEqual(step_actor({("t1", "ag_1", "agent-a")}, "t1", "ag_1"), "agent-a")

    def test_leader_slot_fail_closed(self):
        self.assertEqual(step_actor({("t1", tr.LEADER_SLOT, "x")}, "t1", tr.LEADER_SLOT), "")

    def test_non_member_denied(self):
        self.assertEqual(step_actor(set(), "t1", "ag_1"), "")

    def test_member_of_other_team_denied(self):
        self.assertEqual(step_actor({("t2", "ag_1", "agent-a")}, "t1", "ag_1"), "")

    def test_bad_slug_denied(self):
        self.assertEqual(step_actor({("t1", "ag_1", "../x")}, "t1", "ag_1"), "")
        self.assertEqual(step_actor({("t1", "ag_1", "a b")}, "t1", "ag_1"), "")

    def test_none_fail_closed(self):
        self.assertEqual(step_actor({("t1", "ag_1", "agent-a")}, "t1", None), "")


if __name__ == "__main__":
    unittest.main()
