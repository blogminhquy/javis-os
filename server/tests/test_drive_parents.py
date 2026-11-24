"""Test drive_parents.make_parents_of + guard end-to-end, dữ liệu metadata giả có DẠNG response Drive thật."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import drive_write_guard as g  # noqa: E402
g.WRITE_ROOTS.clear()
g.WRITE_ROOTS.update({"agent-a": "SYN-WRITE-A", "agent-b": "SYN-WRITE-B"})
g.PROTECTED_ROOTS.clear()
g.PROTECTED_ROOTS.update({"root": "SYN-ROOT", "governance": "SYN-GOV", "shared": "SYN-SHARED",
                          "inbox": "SYN-INBOX", "archive": "SYN-ARCHIVE"})
import drive_parents as dp  # noqa: E402

OWN = g.WRITE_ROOTS["agent-a"]
OTHER = g.WRITE_ROOTS["agent-b"]
ROOT = g.PROTECTED_ROOTS["root"]
ACTOR = "agent-a"


def meta(fid, parents, **kw):
    d = {"id": fid, "name": fid, "mimeType": "application/vnd.google-apps.document",
         "parents": parents, "trashed": False}
    d.update(kw)
    return d


def store(items):
    calls = []

    def fetch(fid):
        calls.append(fid)
        if fid not in items:
            raise RuntimeError("404 not found")
        v = items[fid]
        if isinstance(v, Exception):
            raise v
        return v
    return fetch, calls


BASE = {
    OWN: meta(OWN, [ROOT], mimeType="application/vnd.google-apps.folder"),
    OTHER: meta(OTHER, [ROOT], mimeType="application/vnd.google-apps.folder"),
    ROOT: meta(ROOT, []),
    "own-sub": meta("own-sub", [OWN], mimeType="application/vnd.google-apps.folder"),
    "own-doc": meta("own-doc", ["own-sub"]),
    "other-doc": meta("other-doc", [OTHER]),
    "multi-mixed": meta("multi-mixed", [OWN, OTHER]),
    "multi-own": meta("multi-own", [OWN, "own-sub"]),
    "orphan": meta("orphan", []),
}


def run(items, actor, tool, args):
    fetch, calls = store(items)
    return g.decide(actor, tool, args, dp.make_parents_of(fetch)), calls


class Adapter(unittest.TestCase):
    def test_trashed_denied(self):
        items = dict(BASE, **{"own-doc": meta("own-doc", ["own-sub"], trashed=True)})
        r, _ = run(items, ACTOR, "GOOGLEDOCS_GET_DOCUMENT_BY_ID", {})  # read path unaffected
        r, _ = run(items, ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "own-doc"})
        self.assertFalse(r["allow"])

    def test_shortcut_denied(self):
        items = dict(BASE, **{"sc": meta("sc", [OWN], mimeType=dp.SHORTCUT_MIME)})
        r, _ = run(items, ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "sc"})
        self.assertFalse(r["allow"])

    def test_id_mismatch_denied(self):
        items = dict(BASE, **{"own-doc": meta("someone-else", ["own-sub"])})
        r, _ = run(items, ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "own-doc"})
        self.assertFalse(r["allow"])

    def test_fetch_error_denied(self):
        items = dict(BASE, **{"own-doc": RuntimeError("api down")})
        r, _ = run(items, ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "own-doc"})
        self.assertFalse(r["allow"])

    def test_bad_parents_type_denied(self):
        items = dict(BASE, **{"own-doc": meta("own-doc", "own-sub")})
        r, _ = run(items, ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "own-doc"})
        self.assertFalse(r["allow"])

    def test_own_nested_allowed(self):
        r, _ = run(BASE, ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "own-doc"})
        self.assertTrue(r["allow"], r)

    def test_orphan_denied(self):
        r, _ = run(BASE, ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "orphan"})
        self.assertFalse(r["allow"])

    def test_other_agent_denied(self):
        r, _ = run(BASE, ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "other-doc"})
        self.assertFalse(r["allow"])

    def test_multi_parent_mixed_denied(self):
        r, _ = run(BASE, ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "multi-mixed"})
        self.assertFalse(r["allow"])

    def test_multi_parent_all_own_allowed(self):
        r, _ = run(BASE, ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "multi-own"})
        self.assertTrue(r["allow"], r)

    def test_move_into_other_parent_denied_via_add_parents(self):
        r, _ = run(BASE, ACTOR, "GOOGLEDRIVE_MOVE_FILE", {"file_id": "own-doc", "add_parents": "other-doc"})
        self.assertFalse(r["allow"])

    def test_cache_one_fetch_per_id_within_request(self):
        items = dict(BASE)
        fetch, calls = store(items)
        po = dp.make_parents_of(fetch)
        po("own-doc")
        po("own-doc")
        self.assertEqual(calls.count("own-doc"), 1)

    def test_request_arg_cannot_loosen_parent_check(self):
        # File của mình, nhưng caller khai parents ngoài vùng: args chỉ có thể làm chặt hơn, không nới lỏng.
        r, _ = run(BASE, ACTOR, "GOOGLEDRIVE_CREATE_FILE",
                   {"parents": ["own-sub", OTHER]})
        self.assertFalse(r["allow"])


if __name__ == "__main__":
    unittest.main()
