"""Standalone host read envelopes; no native delivery or error-flag inference."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import hashlib
import importlib.util
import json
import math
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from unittest.mock import patch

import improvement_sandbox as SB
import mcp_client

if importlib.util.find_spec("improvement_read_outcome_broker"):
    from improvement_read_outcome_broker import PinnedReadOutcomeBroker
else:
    PinnedReadOutcomeBroker = None


SKILL = "mcp__skill__skill_asset_read"
FIXTURE = "mcp__fixture__fixture_read"
SKILL_CONTENT = "# Instructions\r\nKeep café 日本語\x00 unchanged.\n"
FIXTURE_CONTENT = "Pinned fixture\r\nTiếng Việt 日本語\x00\n"
ENVELOPE_FIELDS = {"version", "observation_id", "trial_id", "attempt", "input_hash", "effective_view",
                   "tool_name", "request_hash", "outcome", "result"}
OBSERVATION_FIELDS = {"version", "observation_id", "trial_id", "attempt", "input_hash", "effective_view",
                      "tool_name", "request", "response_text", "response_hash"}
MISS = {"status": "read_miss", "reason": "read_miss"}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def manifest(version=3):
    public = {"version": 1, "objective": "Report the authorized input accurately.",
              "output": {"kind": "text", "path": "answer.json", "media_type": "application/json"},
              "criteria": [{"id": "shape", "category": "mandatory", "critical": True,
                            "description": "Return the value field.", "kind": "json_keys",
                            "config": {"path": "answer.json", "keys": ["value"]}},
                           {"id": "accuracy", "category": "business", "critical": True,
                            "description": "Reflect the authorized input.", "kind": "independent_check"}]}
    fixture = {"snapshot_id": "fixture-a", "hash": sha(FIXTURE_CONTENT), "content": FIXTURE_CONTENT,
               "source": {"source_version": "source-v1", "data_period": "2026-10", "timezone": "Asia/Ho_Chi_Minh",
                          "cutoff": "2026-10-24T00:00:00+07:00", "schema": "text/plain"}}
    return {"version": version, "brain_id": "brain-a", "bundle_hash": sha("bundle"),
            "engine_config_hash": sha("engine"), "contract_hash": sha("contract"), "grant_hash": sha("grant"),
            "baseline_context": {"content": "Owner rule", "hash": sha("Owner rule"), "coverage": "complete"},
            "public_contract": {"content": public, "hash": sha(canonical(public))},
            "effective_view": {"view_id": "view-a", "view_hash": sha("view"), "binding_hash": sha("binding")},
            "assets": [{"id": "asset-a", "path": "skills/report/SKILL.md", "hash": sha(SKILL_CONTENT), "content": SKILL_CONTENT}],
            "case": {"id": "case-a", "task": "Report the authorized input", "fixtures": [fixture]},
            "learning_origin": "trial"}


def skill_args(value):
    return {"view_id": value["effective_view"]["view_id"], "view_hash": value["effective_view"]["view_hash"],
            "asset_id": value["assets"][0]["id"], "content_hash": value["assets"][0]["hash"]}


def fixture_args():
    return {"snapshot_id": "fixture-a", "source_version": "source-v1"}


class PinnedReadOutcomeBrokerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(PinnedReadOutcomeBroker, "Pinned read outcomes are not implemented")
        self.value = manifest()
        self.input_hash = sha(canonical(self.value))

    def broker(self, **bindings):
        return PinnedReadOutcomeBroker(self.value, **{"trial_id": "trial-a", "attempt": 2,
                                                     "input_hash": self.input_hash, **bindings})

    def assert_envelope(self, response, tool_name, args, outcome):
        self.assertEqual(set(response), ENVELOPE_FIELDS)
        self.assertEqual(response["version"], 1)
        self.assertRegex(response["observation_id"], r"^[0-9a-f]{64}$")
        self.assertEqual({key: response[key] for key in ("trial_id", "attempt", "input_hash", "effective_view")},
                         {"trial_id": "trial-a", "attempt": 2, "input_hash": self.input_hash,
                          "effective_view": self.value["effective_view"]})
        self.assertEqual(response["tool_name"], tool_name)
        self.assertEqual(response["request_hash"], sha(canonical(args)))
        self.assertEqual(response["outcome"], outcome)

    def test_skill_hit_keeps_exact_payload_bytes_and_inner_identity(self):
        broker = self.broker()
        args = skill_args(self.value)
        response = broker.read(SKILL, args)
        self.assert_envelope(response, SKILL, args, "hit")
        result = response["result"]
        self.assertEqual(set(result), {"status", "observation_id", "trial_id", "attempt", "input_hash",
                                       "effective_view", "asset_id", "content_hash", "content"})
        self.assertEqual(result["status"], "skill_asset_hit")
        self.assertEqual(result["content"].encode("utf-8"), SKILL_CONTENT.encode("utf-8"))
        self.assertEqual(result["content_hash"], sha(SKILL_CONTENT))
        self.assertEqual(result["asset_id"], "asset-a")
        for key in ("trial_id", "attempt", "input_hash", "effective_view"):
            self.assertEqual(result[key], response[key])
        self.assertRegex(result["observation_id"], r"^[0-9a-f]{64}$")
        self.assertNotEqual(result["observation_id"], response["observation_id"])
        self.assertEqual(broker.fixture_events, ())

    def test_fixture_hit_keeps_exact_actual_fixture_payload_and_event(self):
        broker = self.broker()
        response = broker.read(FIXTURE, fixture_args())
        self.assert_envelope(response, FIXTURE, fixture_args(), "hit")
        event = {"sequence": 1, "status": "fixture_hit", "snapshot_id": "fixture-a", "capability_id": "fixture.read"}
        self.assertEqual(response["result"], {**event, **self.value["case"]["fixtures"][0]})
        self.assertEqual(response["result"]["content"].encode("utf-8"), FIXTURE_CONTENT.encode("utf-8"))
        self.assertEqual(broker.fixture_events, (event,))

    def test_every_response_has_exact_canonical_observation_and_response_hash(self):
        broker = self.broker()
        requests = [(SKILL, skill_args(self.value)), (FIXTURE, fixture_args()),
                    (SKILL, {**skill_args(self.value), "asset_id": "foreign"}),
                    (FIXTURE, {**fixture_args(), "source_version": "foreign"})]
        for tool_name, args in requests:
            response = broker.read(tool_name, args)
            observation = broker.observations[-1]
            self.assertEqual(set(observation), OBSERVATION_FIELDS)
            for key in ("version", "observation_id", "trial_id", "attempt", "input_hash", "effective_view", "tool_name"):
                self.assertEqual(observation[key], response[key])
            self.assertEqual(observation["request"], args)
            self.assertEqual(observation["response_text"], canonical(response))
            self.assertEqual(observation["response_hash"], sha(canonical(response)))
        self.assertEqual(len(broker.observations), 4)

    def test_skill_foreign_missing_extra_path_and_valid_json_type_denials_are_generic(self):
        broker = self.broker()
        good = skill_args(self.value)
        invalid = [None, [], "skills/report/SKILL.md", True, 1, {},
                   {**good, "path": "skills/report/SKILL.md"}, {**good, "url": "https://live.invalid"}]
        for key in good:
            invalid.extend(({**good, key: "foreign"}, {**good, key: None}, {**good, key: []},
                            {field: value for field, value in good.items() if field != key}))
        for args in invalid:
            with self.subTest(args=args):
                response = broker.read(SKILL, args)
                self.assert_envelope(response, SKILL, args, "miss")
                self.assertEqual(response["result"], MISS)
        self.assertEqual(len(broker.observations), len(invalid))
        self.assertEqual(broker.fixture_events, ())

    def test_fixture_denials_record_actual_underlying_misses_without_payload(self):
        broker = self.broker()
        invalid = [None, [], "fixture-a", {}, {"snapshot_id": "fixture-a"},
                   {"source_version": "source-v1"}, {**fixture_args(), "path": "private.txt"},
                   {**fixture_args(), "snapshot_id": "foreign"}, {**fixture_args(), "source_version": "foreign"},
                   {**fixture_args(), "snapshot_id": ["fixture-a"]}, {**fixture_args(), "source_version": True}]
        for args in invalid:
            with self.subTest(args=args):
                response = broker.read(FIXTURE, args)
                self.assert_envelope(response, FIXTURE, args, "miss")
                self.assertEqual(response["result"], MISS)
                self.assertEqual(broker.fixture_events[-1]["status"], "fixture_miss")
        self.assertEqual([event["sequence"] for event in broker.fixture_events], list(range(1, len(invalid) + 1)))
        self.assertEqual(len(broker.observations), len(invalid))

    def test_non_json_requests_fail_closed_without_events_or_observations(self):
        broker = self.broker()
        cyclic = []
        cyclic.append(cyclic)
        for args in (b"bytes", {"source_version": object()}, {1: "not a JSON key"}, {"a": {1, 2}},
                     {"a": (1, 2)}, math.nan, math.inf, cyclic):
            for tool_name in (SKILL, FIXTURE):
                with self.subTest(tool_name=tool_name, args=repr(args)), self.assertRaises(ValueError):
                    broker.read(tool_name, args)
        self.assertEqual(broker.observations, ())
        self.assertEqual(broker.fixture_events, ())

    def test_unknown_tools_raise_before_any_read(self):
        broker = self.broker()
        for name in (None, "", "fixture.read", "skill_asset_read", "mcp__skill__other", [], True):
            with self.subTest(name=name), self.assertRaises(ValueError):
                broker.read(name, fixture_args())
        self.assertEqual(broker.observations, ())
        self.assertEqual(broker.fixture_events, ())

    def test_v2_v3_v4_accept_only_full_pinned_manifest_with_strict_bindings(self):
        for version in (2, 3, 4):
            value = manifest(version)
            broker = PinnedReadOutcomeBroker(value, trial_id="trial-a", attempt=2, input_hash=sha(canonical(value)))
            self.assertEqual(broker.read(SKILL, skill_args(value))["outcome"], "hit")
        for field, replacements in (("trial_id", (None, "", "../trial", "trial/a", "a" * 129, 1, True)),
                                    ("attempt", (None, 0, -1, True, "2", 2.0, 1_000_001)),
                                    ("input_hash", (None, "", "0" * 64, self.input_hash.upper(), True))):
            for replacement in replacements:
                with self.subTest(field=field, replacement=replacement), self.assertRaises(ValueError):
                    self.broker(**{field: replacement})
        for invalid in (None, [], {**self.value, "extra": "field"}, {**self.value, "version": 5}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                PinnedReadOutcomeBroker(invalid, trial_id="trial-a", attempt=2, input_hash=sha(canonical(invalid)))
        legacy = manifest(1)
        legacy.pop("effective_view")
        with self.assertRaises(ValueError):
            PinnedReadOutcomeBroker(legacy, trial_id="trial-a", attempt=2, input_hash=sha(canonical(legacy)))

    def test_manifest_drift_and_unbound_roles_are_rejected_even_with_recomputed_input_hash(self):
        variants = []
        for location in ("context", "asset", "contract", "fixture", "role"):
            changed = copy.deepcopy(self.value)
            if location == "context":
                changed["baseline_context"]["content"] = "Unpinned context"
            elif location == "asset":
                changed["assets"][0]["content"] = "Unpinned instructions"
            elif location == "contract":
                changed["public_contract"]["content"]["objective"] = "Changed acceptance"
            elif location == "fixture":
                changed["case"]["fixtures"][0]["content"] = "Live replacement"
            else:
                changed["assets"][0]["path"] = "agents/report.md"
            variants.append(changed)
        for changed in variants:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                PinnedReadOutcomeBroker(changed, trial_id="trial-a", attempt=2, input_hash=sha(canonical(changed)))
        changed = copy.deepcopy(self.value)
        changed["case"]["task"] = "A different authorized task"
        with self.assertRaises(ValueError):
            PinnedReadOutcomeBroker(changed, trial_id="trial-a", attempt=2, input_hash=self.input_hash)

    def test_provided_fixture_broker_is_the_actual_decision_and_event_source(self):
        fixtures = self.value["case"]["fixtures"]
        supplied = SB.FixtureBroker(fixtures, self.value["grant_hash"])
        supplied.read("fixture.read", {"snapshot_id": "fixture-a"}, "source-v1", self.value["grant_hash"])
        broker = self.broker(fixture_broker=supplied)
        response = broker.read(FIXTURE, fixture_args())
        self.assertEqual(response["result"]["sequence"], 2)
        self.assertEqual(tuple(supplied.events), broker.fixture_events)
        self.assertEqual(len(supplied.events), 2)

    def test_foreign_grant_fixtures_and_non_concrete_fixture_brokers_are_refused(self):
        class Subclass(SB.FixtureBroker):
            pass

        fixtures = self.value["case"]["fixtures"]
        changed = copy.deepcopy(fixtures)
        changed[0].update(content="Other bytes", hash=sha("Other bytes"))
        invalid = (object(), Subclass(fixtures, self.value["grant_hash"]),
                   SB.FixtureBroker(fixtures, sha("foreign grant")), SB.FixtureBroker([], self.value["grant_hash"]),
                   SB.FixtureBroker(changed, self.value["grant_hash"]))
        for supplied in invalid:
            with self.subTest(supplied=supplied), self.assertRaises(ValueError):
                self.broker(fixture_broker=supplied)

    def test_provided_fixture_authority_drift_fails_closed_before_recording_a_read(self):
        supplied = SB.FixtureBroker(self.value["case"]["fixtures"], self.value["grant_hash"])
        broker = self.broker(fixture_broker=supplied)
        supplied._fixtures["fixture-a"]["content"] = "Changed after binding"
        with self.assertRaises(ValueError):
            broker.read(FIXTURE, fixture_args())
        self.assertEqual(broker.fixture_events, ())
        self.assertEqual(broker.observations, ())

    def test_caller_mutation_cannot_change_pinned_payloads_requests_or_prior_history(self):
        broker = self.broker()
        fixture_request = fixture_args()
        skill_request = skill_args(self.value)
        first = broker.read(FIXTURE, fixture_request)
        second = broker.read(SKILL, skill_request)
        malformed = {"nested": ["foreign", {"path": "private.txt"}]}
        third = broker.read(FIXTURE, malformed)
        original = copy.deepcopy(broker.observations)
        self.value["assets"][0]["content"] = "Changed instructions"
        self.value["case"]["fixtures"][0]["content"] = "Changed fixture"
        self.value["effective_view"]["view_id"] = "Changed view"
        fixture_request.clear()
        malformed["nested"][1]["path"] = "changed"
        first["result"]["source"]["source_version"] = "changed"
        first["result"]["content"] = "changed"
        second["result"]["content"] = "changed"
        second["effective_view"].clear()
        third["result"]["content"] = "injected"
        history = broker.observations
        history[0]["effective_view"].clear()
        history[0]["request"].clear()
        history[0]["response_text"] = "changed"
        events = broker.fixture_events
        events[0]["status"] = "changed"
        self.assertEqual(broker.observations, original)
        self.assertEqual(broker.fixture_events[0]["status"], "fixture_hit")
        self.assertEqual(broker.read(FIXTURE, fixture_args())["result"]["content"], FIXTURE_CONTENT)
        self.assertEqual(broker.read(SKILL, skill_request)["result"]["content"], SKILL_CONTENT)

    def test_parallel_equal_and_mixed_reads_keep_unique_ids_actual_sequences_and_reverse_order_bytes(self):
        broker = self.broker()
        calls = [(FIXTURE, fixture_args())] * 24 + [(FIXTURE, {**fixture_args(), "snapshot_id": "foreign"})] * 8
        calls += [(SKILL, skill_args(self.value))] * 8
        with ThreadPoolExecutor(max_workers=8) as executor:
            responses = list(executor.map(lambda call: broker.read(*call), calls))
        self.assertEqual(len({response["observation_id"] for response in responses}), 40)
        self.assertEqual([event["sequence"] for event in broker.fixture_events], list(range(1, 33)))
        self.assertEqual(sum(event["status"] == "fixture_hit" for event in broker.fixture_events), 24)
        self.assertEqual(sum(response["outcome"] == "miss" for response in responses), 8)
        by_id = {observation["observation_id"]: observation for observation in broker.observations}
        self.assertEqual(len(by_id), 40)
        for response in reversed(responses):
            retained = by_id[response["observation_id"]]
            self.assertEqual(retained["response_text"], canonical(response))
            self.assertEqual(retained["response_hash"], sha(canonical(response)))
            if response["tool_name"] == FIXTURE and response["outcome"] == "hit":
                event = broker.fixture_events[response["result"]["sequence"] - 1]
                self.assertEqual(event["status"], response["result"]["status"])

    def test_constructor_reads_and_denials_perform_no_filesystem_or_connector_access(self):
        with ExitStack() as stack:
            for entrypoint in ("builtins.open", "pathlib.Path.open", "pathlib.Path.read_bytes", "pathlib.Path.read_text",
                               "pathlib.Path.resolve", "socket.create_connection", "mcp_client.call_route",
                               "mcp_client.SessionPool.call_tool"):
                stack.enter_context(patch(entrypoint, side_effect=AssertionError("External access forbidden")))
            broker = self.broker()
            self.assertEqual(broker.read(SKILL, skill_args(self.value))["result"]["content"], SKILL_CONTENT)
            self.assertEqual(broker.read(FIXTURE, fixture_args())["result"]["content"], FIXTURE_CONTENT)
            self.assertEqual(broker.read(FIXTURE, {**fixture_args(), "path": "private.txt"})["result"], MISS)
            self.assertEqual(broker.read(SKILL, {**skill_args(self.value), "asset_id": "foreign"})["result"], MISS)


if __name__ == "__main__":
    unittest.main()
