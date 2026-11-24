"""Test drive_write_guard với TÊN TOOL và THAM SỐ THẬT (schema Composio 2026-11-24).

Không gọi Drive thật: cây thư mục giả. Chạy: cd server && python3 -m unittest tests.test_drive_write_guard -v
"""
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

OWN = g.WRITE_ROOTS["agent-a"]
OTHER = g.WRITE_ROOTS["agent-b"]
SHARED = g.PROTECTED_ROOTS["shared"]
GOV = g.PROTECTED_ROOTS["governance"]
ROOT = g.PROTECTED_ROOTS["root"]

# Cây giả. Ký hiệu: cha -> [ông/bà].
TREE = {
    "own-sub": [OWN],
    "own-file": ["own-sub"],
    "own-sheet": ["own-sub"],
    "own-doc": ["own-sub"],
    "other-file": [OTHER],
    "other-sub": [OTHER],
    "shared-doc": [SHARED],
    "gov-doc": [GOV],
    "orphan": [],
    OWN: [ROOT],
    OTHER: [ROOT],
    SHARED: [ROOT],
    GOV: [ROOT],
    ROOT: [],
    "cycle-a": ["cycle-b"],
    "cycle-b": ["cycle-a"],
}


def parents(fid):
    return TREE.get(fid, [])


def dec(actor, tool, args):
    return g.decide(actor, tool, args, parents)


def multi(*subs):
    return ("COMPOSIO_MULTI_EXECUTE_TOOL", {"tools": [{"tool_slug": s, "arguments": a} for s, a in subs]})


ACTOR = "agent-a"


class ReadAllowed(unittest.TestCase):
    def test_parse_file_is_read_even_for_other_agent_file(self):
        self.assertTrue(dec(ACTOR, "GOOGLEDRIVE_PARSE_FILE", {"file_id": "other-file"})["allow"])

    def test_list_files_read_on_shared(self):
        self.assertTrue(dec(ACTOR, "GOOGLEDRIVE_LIST_FILES", {"folderId": SHARED})["allow"])

    def test_sheets_get_values_read_on_other_sheet(self):
        self.assertTrue(dec(ACTOR, "GOOGLESHEETS_GET_VALUES", {"spreadsheet_id": "other-file"})["allow"])

    def test_read_with_unknown_actor_still_allowed(self):
        self.assertTrue(dec(None, "GOOGLEDRIVE_GET_FILE_METADATA", {"file_id": "other-file"})["allow"])


class OwnWrite(unittest.TestCase):
    def test_trash_own_file(self):
        self.assertTrue(dec(ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "own-file"})["allow"])

    def test_move_own_file_into_own_folder(self):
        self.assertTrue(dec(ACTOR, "GOOGLEDRIVE_MOVE_FILE",
                            {"file_id": "own-file", "add_parents": "own-sub"})["allow"])

    def test_create_file_in_own_folder(self):
        self.assertTrue(dec(ACTOR, "GOOGLEDRIVE_CREATE_FILE", {"parents": ["own-sub"]})["allow"])

    def test_sheets_batch_update_own_sheet(self):
        self.assertTrue(dec(ACTOR, "GOOGLESHEETS_UPDATE_VALUES_BATCH",
                            {"spreadsheet_id": "own-sheet", "valueInputOption": "RAW", "data": []})["allow"])

    def test_own_root_itself(self):
        self.assertTrue(dec(ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": OWN})["allow"])


class CrossProtectedDestructive(unittest.TestCase):
    def test_cross_write_trash_denied(self):
        self.assertFalse(dec(ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "other-file"})["allow"])

    def test_shared_write_denied(self):
        self.assertFalse(dec(ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "shared-doc"})["allow"])

    def test_governance_write_denied(self):
        self.assertFalse(dec(ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "gov-doc"})["allow"])

    def test_move_out_of_own_into_other_denied(self):
        self.assertFalse(dec(ACTOR, "GOOGLEDRIVE_MOVE_FILE",
                             {"file_id": "own-file", "add_parents": "other-sub"})["allow"])

    def test_move_other_file_into_own_denied(self):
        # Đưa file của agent khác vào thư mục của mình: vẫn phải DENY (file_id ngoài vùng).
        self.assertFalse(dec(ACTOR, "GOOGLEDRIVE_MOVE_FILE",
                             {"file_id": "other-file", "add_parents": "own-sub"})["allow"])

    def test_move_into_shared_denied(self):
        self.assertFalse(dec(ACTOR, "GOOGLEDRIVE_MOVE_FILE",
                             {"file_id": "own-file", "add_parents": SHARED})["allow"])

    def test_create_file_in_governance_denied(self):
        self.assertFalse(dec(ACTOR, "GOOGLEDRIVE_CREATE_FILE", {"parents": [GOV]})["allow"])

    def test_create_permission_on_shared_denied(self):
        self.assertFalse(dec(ACTOR, "GOOGLEDRIVE_CREATE_PERMISSION",
                             {"file_id": "shared-doc", "type": "anyone", "role": "writer"})["allow"])

    def test_update_shared_drive_denied(self):
        self.assertFalse(dec(ACTOR, "GOOGLEDRIVE_UPDATE_DRIVE", {"driveId": "other-sub"})["allow"])

    def test_copy_file_into_root_denied(self):
        # COPY_FILE đặt bản sao cùng thư mục gốc của file; file ngoài vùng -> DENY.
        self.assertFalse(dec(ACTOR, "GOOGLEDRIVE_COPY_FILE", {"file_id": "other-file"})["allow"])

    def test_docs_create_has_no_target_denied(self):
        # CREATE_DOCUMENT không có ID đích, tạo ở root -> fail-closed.
        self.assertFalse(dec(ACTOR, "GOOGLEDOCS_CREATE_DOCUMENT", {"title": "x"})["allow"])

    def test_docs_copy_denied_when_source_other(self):
        self.assertFalse(dec(ACTOR, "GOOGLEDOCS_COPY_DOCUMENT", {"document_id": "other-file"})["allow"])

    def test_docs_copy_own_source_still_denied_no_destination(self):
        # Bản sao luôn vào root -> không kiểm được đích -> DENY dù nguồn là own.
        self.assertFalse(dec(ACTOR, "GOOGLEDOCS_COPY_DOCUMENT", {"document_id": "own-doc"})["allow"])

    def test_sheets_clear_other_denied(self):
        self.assertFalse(dec(ACTOR, "GOOGLESHEETS_CLEAR_VALUES",
                             {"spreadsheet_id": "other-file", "range": "A1:B2"})["allow"])


class FailClosed(unittest.TestCase):
    def test_unknown_actor_write_denied(self):
        self.assertFalse(dec(None, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "own-file"})["allow"])
        self.assertFalse(dec("ghost-agent", "GOOGLEDRIVE_TRASH_FILE", {"file_id": "own-file"})["allow"])

    def test_missing_target_denied(self):
        self.assertFalse(dec(ACTOR, "GOOGLEDRIVE_TRASH_FILE", {})["allow"])

    def test_empty_target_denied(self):
        self.assertFalse(dec(ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "  "})["allow"])

    def test_non_string_target_denied(self):
        self.assertFalse(dec(ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": 123})["allow"])

    def test_id_spoof_extra_key_cannot_bypass(self):
        # Đích thật ngoài vùng, kèm khóa fileId trỏ vào own -> vẫn DENY (mọi ID đều được kiểm).
        a = {"file_id": "other-file", "fileId": "own-file"}
        self.assertFalse(dec(ACTOR, "GOOGLEDRIVE_TRASH_FILE", a)["allow"])

    def test_camel_case_folder_id_checked(self):
        self.assertFalse(dec(ACTOR, "GOOGLEDRIVE_CREATE_FILE", {"parents": ["other-sub"], "folderId": "own-sub"})["allow"])

    def test_unknown_write_tool_default_deny_with_own_target(self):
        # Tool Drive chưa biết nhưng là ghi: ID trong vùng -> ALLOW, ngoài vùng -> DENY.
        self.assertTrue(dec(ACTOR, "GOOGLEDRIVE_SOME_NEW_WRITE", {"file_id": "own-file"})["allow"])
        self.assertFalse(dec(ACTOR, "GOOGLEDRIVE_SOME_NEW_WRITE", {"file_id": "other-file"})["allow"])

    def test_bad_args_type_denied(self):
        self.assertFalse(dec(ACTOR, "GOOGLEDRIVE_TRASH_FILE", "not-a-dict")["allow"])

    def test_non_string_tool_denied(self):
        self.assertFalse(g.decide(ACTOR, None, {}, parents)["allow"])

    def test_exception_in_parents_lookup_denied(self):
        def boom(_):
            raise RuntimeError("api down")
        self.assertFalse(g.decide(ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "own-file"}, boom)["allow"])

    def test_cycle_terminates_and_denies(self):
        self.assertFalse(dec(ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "cycle-a"})["allow"])


class ControlTools(unittest.TestCase):
    def test_multi_all_read_allowed(self):
        t, a = multi(("GOOGLEDRIVE_LIST_FILES", {"folderId": SHARED}),
                     ("GOOGLEDRIVE_PARSE_FILE", {"file_id": "other-file"}))
        self.assertTrue(dec(ACTOR, t, a)["allow"])

    def test_multi_one_write_denies_whole_batch(self):
        t, a = multi(("GOOGLEDRIVE_PARSE_FILE", {"file_id": "other-file"}),
                     ("GOOGLEDRIVE_TRASH_FILE", {"file_id": "other-file"}))
        self.assertFalse(dec(ACTOR, t, a)["allow"])

    def test_multi_sub_missing_arguments_denied(self):
        t, a = multi(("GOOGLEDRIVE_PARSE_FILE", {"file_id": "own-file"}))
        a["tools"][0].pop("arguments")
        self.assertFalse(dec(ACTOR, t, a)["allow"])

    def test_multi_sub_missing_slug_denied(self):
        self.assertFalse(dec(ACTOR, "COMPOSIO_MULTI_EXECUTE_TOOL", {"tools": [{"arguments": {}}]})["allow"])

    def test_multi_missing_list_denied(self):
        self.assertFalse(dec(ACTOR, "COMPOSIO_MULTI_EXECUTE_TOOL", {})["allow"])

    def test_multi_nested_control_denied(self):
        t, a = multi(("COMPOSIO_MULTI_EXECUTE_TOOL", {"tools": [
            {"tool_slug": "GOOGLEDRIVE_PARSE_FILE", "arguments": {"file_id": "own-file"}}]}))
        self.assertFalse(dec(ACTOR, t, a)["allow"])

    def test_multi_write_in_own_allowed(self):
        t, a = multi(("GOOGLESHEETS_UPDATE_VALUES_BATCH",
                      {"spreadsheet_id": "own-sheet", "valueInputOption": "RAW", "data": []}))
        self.assertTrue(dec(ACTOR, t, a)["allow"])

    def test_proxy_get_allowed_post_denied(self):
        self.assertTrue(dec(ACTOR, "COMPOSIO_PROXY_EXECUTE", {"method": "GET"})["allow"])
        self.assertFalse(dec(ACTOR, "COMPOSIO_PROXY_EXECUTE", {"method": "POST"})["allow"])

    def test_proxy_missing_method_denied(self):
        self.assertFalse(dec(ACTOR, "COMPOSIO_PROXY_EXECUTE", {})["allow"])


class Modes(unittest.TestCase):
    def test_default_mode_is_off(self):
        self.assertEqual(g.current_mode({}), "off")

    def test_invalid_mode_is_not_silently_off(self):
        self.assertEqual(g.current_mode({g.MODE_ENV: "ENFORCE!"}), "invalid")
        self.assertEqual(g.current_mode({g.MODE_ENV: "enfroce"}), "invalid")
        self.assertEqual(g.current_mode({}), "off")
        self.assertEqual(g.current_mode({g.MODE_ENV: "  "}), "off")

    def test_shadow_and_off_never_block(self):
        d = dec(ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "other-file"})
        self.assertFalse(g.enforce_decision("shadow", d))
        self.assertFalse(g.enforce_decision("off", d))

    def test_enforce_blocks_deny_only(self):
        d = dec(ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "other-file"})
        self.assertTrue(g.enforce_decision("enforce", d))
        self.assertFalse(g.enforce_decision("enforce", dec(ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "own-file"})))


class DirectConnectorDeny(unittest.TestCase):
    class Opts:
        def __init__(self, dis=None):
            self.disallowed_tools = dis

    def test_off_and_shadow_add_nothing(self):
        self.assertEqual(g.direct_deny_rules({}), [])
        self.assertEqual(g.direct_deny_rules({g.MODE_ENV: "shadow"}), [])
        o = g.add_direct_deny(self.Opts(None), {g.MODE_ENV: "off"})
        self.assertIsNone(o.disallowed_tools)

    def test_enforce_adds_all_three_servers_once(self):
        env = {g.MODE_ENV: "enforce"}
        o = g.add_direct_deny(self.Opts(["Bash"]), env)
        o = g.add_direct_deny(o, env)
        self.assertEqual(o.disallowed_tools.count("Bash"), 1)
        for srv in g.DIRECT_CONNECTOR_SERVERS:
            self.assertEqual(o.disallowed_tools.count(srv), 1)

    def test_none_options_is_noop(self):
        self.assertIsNone(g.add_direct_deny(None, {g.MODE_ENV: "enforce"}))


if __name__ == "__main__":
    unittest.main()
