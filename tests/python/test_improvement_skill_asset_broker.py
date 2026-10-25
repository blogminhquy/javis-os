"""Standalone broker evidence, without SDK, engine, or native receipt claims."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import hashlib
import importlib.util
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import improvement_sandbox as SB
import mcp_client

if importlib.util.find_spec("improvement_skill_asset_broker"):
    from improvement_skill_asset_broker import SkillAssetBroker
else:
    SkillAssetBroker = None


CONTENT = "# Skill\r\nPreserve café and 日本語.\n\x00End\r\n"


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def manifest():
    public = {"version": 1, "objective": "Report the authorized input accurately.",
              "output": {"kind": "text", "path": "answer.json", "media_type": "application/json"},
              "criteria": [{"id": "shape", "category": "mandatory", "critical": True,
                            "description": "Return the value field.", "kind": "json_keys",
                            "config": {"path": "answer.json", "keys": ["value"]}},
                           {"id": "accuracy", "category": "business", "critical": True,
                            "description": "Reflect the authorized input.", "kind": "independent_check"}]}
    return {"version": 2, "brain_id": "brain-a", "bundle_hash": sha("bundle"),
            "engine_config_hash": sha("engine"), "contract_hash": sha("contract"), "grant_hash": sha("grant"),
            "baseline_context": {"content": "Owner rule", "hash": sha("Owner rule"), "coverage": "complete"},
            "public_contract": {"content": public, "hash": SB._hash(public)},
            "effective_view": {"view_id": "view-a", "view_hash": sha("view"), "binding_hash": sha("binding")},
            "assets": [{"id": "asset-a", "path": "skills/report/SKILL.md", "hash": sha(CONTENT), "content": CONTENT}],
            "case": {"id": "case-a", "task": "Report the authorized input", "fixtures": []},
            "learning_origin": "trial"}


def request(value):
    return {"view_id": value["effective_view"]["view_id"], "view_hash": value["effective_view"]["view_hash"],
            "asset_id": value["assets"][0]["id"], "content_hash": value["assets"][0]["hash"]}


class SkillAssetBrokerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(SkillAssetBroker, "The immutable skill asset broker is not implemented")
        self.value = manifest()
        self.args = request(self.value)
        self.input_hash = SB._hash(self.value)

    def broker(self, **bindings):
        return SkillAssetBroker(self.value, **{"trial_id": "trial-a", "attempt": 2,
                                             "input_hash": self.input_hash, **bindings})

    def test_exact_materialized_bytes_and_all_host_bindings_are_returned(self):
        result = self.broker().read(self.args)
        self.assertEqual(result["status"], "skill_asset_hit")
        self.assertEqual(result["content"].encode("utf-8"), CONTENT.encode("utf-8"))
        self.assertEqual({key: result[key] for key in ("trial_id", "attempt", "input_hash", "effective_view", "asset_id", "content_hash")},
                         {"trial_id": "trial-a", "attempt": 2, "input_hash": self.input_hash,
                          "effective_view": self.value["effective_view"], "asset_id": "asset-a", "content_hash": sha(CONTENT)})
        self.assertRegex(result["observation_id"], r"^[A-Za-z0-9_-]{32,128}$")
        self.assertNotIn("path", result)

    def test_foreign_view_asset_or_hash_returns_the_same_content_free_miss(self):
        broker = self.broker()
        for key, foreign in (("view_id", "view-b"), ("view_hash", sha("other view")),
                             ("asset_id", "asset-b"), ("content_hash", sha("other content"))):
            with self.subTest(key=key):
                self.assertEqual(broker.read({**self.args, key: foreign}),
                                 {"status": "skill_asset_miss", "reason": "skill_asset_miss"})
        self.assertEqual(broker.observations, ())

    def test_malformed_missing_extra_path_and_non_string_arguments_do_not_leak(self):
        broker = self.broker()
        invalid = [None, [], "skills/report/SKILL.md", 1, {},
                   {**self.args, "path": "skills/report/SKILL.md"}, {**self.args, "url": "https://live.invalid"},
                   {**self.args, "trial_id": "trial-a"}, {**self.args, "asset_id": "../report"}]
        for key in self.args:
            invalid.append({name: value for name, value in self.args.items() if name != key})
            for value in (None, [], {}, 1, True, b"asset-a"):
                invalid.append({**self.args, key: value})
        for args in invalid:
            with self.subTest(args=args):
                self.assertEqual(broker.read(args), {"status": "skill_asset_miss", "reason": "skill_asset_miss"})
        self.assertEqual(broker.observations, ())

    def test_string_and_dict_subclasses_are_refused_without_coercion(self):
        class String(str):
            pass

        class Arguments(dict):
            pass

        broker = self.broker()
        for args in (Arguments(self.args), {**self.args, "asset_id": String("asset-a")}):
            self.assertEqual(broker.read(args)["status"], "skill_asset_miss")

    def test_constructor_validates_complete_manifest_before_serving_content(self):
        variants = []
        for key in ("baseline_context", "public_contract", "assets", "case"):
            value = copy.deepcopy(self.value)
            if key in ("baseline_context", "public_contract"):
                value[key]["hash"] = sha("tampered")
            elif key == "assets":
                value[key][0]["content"] = "Unpinned instructions"
            else:
                value[key]["private_checker"] = "not public"
            variants.append(value)
        variants.extend((None, [], {**self.value, "unexpected": "field"}))
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ValueError):
                SkillAssetBroker(value, trial_id="trial-a", attempt=2, input_hash=SB._hash(value))

    def test_legacy_and_unbound_agent_roles_are_refused(self):
        legacy = copy.deepcopy(self.value)
        legacy["version"] = 1
        legacy.pop("effective_view")
        unbound = copy.deepcopy(self.value)
        unbound["assets"][0]["path"] = "agents/report.md"
        missing = copy.deepcopy(self.value)
        missing.pop("effective_view")
        for value in (legacy, unbound, missing):
            with self.subTest(value=value), self.assertRaises(ValueError):
                SkillAssetBroker(value, trial_id="trial-a", attempt=2, input_hash=SB._hash(value))

    def test_strict_trial_identity_attempt_and_canonical_input_hash_are_required(self):
        for trial in (None, "", "../trial", "trial/a", "trial.a", "a" * 129, 1, True):
            with self.subTest(trial=trial), self.assertRaises(ValueError):
                self.broker(trial_id=trial)
        for attempt in (None, 0, -1, True, "2", 2.0, 1_000_001):
            with self.subTest(attempt=attempt), self.assertRaises(ValueError):
                self.broker(attempt=attempt)
        for input_hash in (None, self.input_hash.upper(), "", "0" * 64, 1):
            with self.subTest(input_hash=input_hash), self.assertRaises(ValueError):
                self.broker(input_hash=input_hash)
        changed = copy.deepcopy(self.value)
        changed["case"]["task"] = "A different authorized task"
        with self.assertRaises(ValueError):
            SkillAssetBroker(changed, trial_id="trial-a", attempt=2, input_hash=self.input_hash)

    def test_different_trials_and_attempts_keep_their_own_observation_binding(self):
        first = self.broker().read(self.args)
        second = self.broker(trial_id="trial-b", attempt=3).read(self.args)
        self.assertEqual((first["trial_id"], first["attempt"]), ("trial-a", 2))
        self.assertEqual((second["trial_id"], second["attempt"]), ("trial-b", 3))
        self.assertNotEqual(first["observation_id"], second["observation_id"])

    def test_mutating_constructor_input_request_and_returns_cannot_change_assets_or_history(self):
        broker = self.broker()
        expected_request = dict(self.args)
        result = broker.read(self.args)
        original_result = copy.deepcopy(result)
        self.value["assets"][0]["content"] = "Replaced instructions"
        self.value["effective_view"]["view_id"] = "view-b"
        self.args.clear()
        result["content"] = "Changed response"
        result["effective_view"]["view_id"] = "changed response view"
        history = broker.observations
        history[0]["request"]["asset_id"] = "changed history request"
        history[0]["effective_view"]["view_id"] = "changed history view"
        history[0]["response_text"] = "changed history response"
        retained = broker.observations[0]
        self.assertEqual(retained["request"], expected_request)
        self.assertEqual(json.loads(retained["response_text"]), original_result)
        self.assertEqual(retained["effective_view"]["view_id"], "view-a")
        self.assertEqual(broker.read(expected_request)["content"], CONTENT)

    def test_observation_preserves_exact_canonical_request_response_and_raw_hash(self):
        broker = self.broker()
        result = broker.read(self.args)
        observation, = broker.observations
        expected_text = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        self.assertEqual(observation["request"], self.args)
        self.assertEqual(observation["response_text"], expected_text)
        self.assertEqual(observation["response_hash"], sha(expected_text))
        for key in ("observation_id", "trial_id", "attempt", "input_hash", "effective_view", "asset_id", "content_hash"):
            self.assertEqual(observation[key], result[key])
        self.assertEqual(len(broker.observations), 1)

    def test_concurrent_and_repeated_reads_have_unique_unpredictable_observation_ids(self):
        broker = self.broker()
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: broker.read(self.args), range(48)))
        results.append(broker.read(self.args))
        identifiers = {result["observation_id"] for result in results}
        self.assertEqual(len(identifiers), 49)
        self.assertEqual({event["observation_id"] for event in broker.observations}, identifiers)
        for result in results:
            self.assertEqual(result["content"], CONTENT)
            self.assertRegex(result["observation_id"], r"^[A-Za-z0-9_-]{32,128}$")

    def test_constructor_hits_and_misses_do_not_read_files_or_dispatch_connectors(self):
        with ExitStack() as stack:
            for entrypoint in ("builtins.open", "pathlib.Path.open", "pathlib.Path.read_bytes", "pathlib.Path.read_text",
                               "pathlib.Path.resolve", "socket.create_connection", "mcp_client.call_route",
                               "mcp_client.SessionPool.call_tool"):
                stack.enter_context(patch(entrypoint, side_effect=AssertionError("External access forbidden")))
            broker = self.broker()
            self.assertEqual(broker.read(self.args)["content"], CONTENT)
            self.assertEqual(broker.read({**self.args, "path": str(Path("skills/report/SKILL.md"))})["status"], "skill_asset_miss")
            self.assertEqual(broker.read({**self.args, "asset_id": "unavailable"})["status"], "skill_asset_miss")


if __name__ == "__main__":
    unittest.main()
