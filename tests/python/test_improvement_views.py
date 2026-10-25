"""Pure view identity only; these metadata fixtures grant no runtime authority."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import importlib
import importlib.util
import unittest

import improvement_store as IM


def manifest(variant='baseline'):
    target = {'target_id': 'target_view', 'base_revision_id': 'revision_base',
        'base_hash': 'a' * 64, 'base_generation': 1, 'canonical_ref': 'skills/reconcile/SKILL.md',
        'identity': 'b' * 64, 'protected_hash': 'd' * 64, 'ownership': 'user_protected'}
    return {'version': 1, 'evidence_class': 'technical', 'brain_id': 'synthetic-brain',
        'experiment_id': 'experiment_view', 'context_id': 'context_view', 'context_generation': 1,
        'comparison_id': 'comparison_view', 'comparison_hash': '1' * 64, 'definition_hash': '2' * 64,
        'arm_ordinal': 1, 'arm_hash': '3' * 64, 'candidate_id': 'candidate_view', 'variant': variant,
        'target': target, 'engine_config_hash': '4' * 64, 'baseline_context_hash': '5' * 64,
        'contract_hash': '6' * 64, 'case_set_hash': '7' * 64, 'grant_hash': '8' * 64,
        'scope_hash': '9' * 64, 'policy_version': 0, 'source_authority_hash': 'e' * 64,
        'semantic': {'receipt_id': 'semantic_view', 'binding_hash': 'f' * 64,
            'assessment_hash': '0' * 64, 'dependency_hash': '1' * 64, 'owner_event_key': None},
        'assets': [{'id': 'revision_base' if variant == 'baseline' else 'candidate_view',
            'canonical_ref': target['canonical_ref'], 'before_hash': target['base_hash'],
            'content_hash': target['base_hash'] if variant == 'baseline' else 'c' * 64,
            'identity': target['identity'], 'authority_hash': 'e' * 64, 'origin': variant}]}


class ViewProtocolTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('improvement_view_protocol'),
            'The exact immutable view protocol is absent')
        self.protocol = importlib.import_module('improvement_view_protocol')

    def reject(self, value):
        with self.assertRaises((ValueError, TypeError)):
            self.protocol.view_manifest(value)

    def test_both_variants_have_exact_stable_independent_identity(self):
        hashes = []
        for variant in ('baseline', 'candidate'):
            value = manifest(variant)
            actual = self.protocol.view_manifest(value)
            self.assertEqual(actual, value)
            self.assertEqual(self.protocol.view_hash(value), IM._hash(actual))
            hashes.append(self.protocol.view_hash(value))
            actual['assets'][0]['content_hash'] = 'f' * 64
            self.assertNotEqual(actual, value, 'Validation returned a mutable alias of its input')
        self.assertNotEqual(*hashes)

    def test_ordering_changes_no_hash_but_source_authority_changes_it(self):
        value = manifest()
        reordered = {key: value[key] for key in reversed(value)}
        reordered['target'] = dict(reversed(list(value['target'].items())))
        self.assertEqual(self.protocol.view_hash(value), self.protocol.view_hash(reordered))
        changed = copy.deepcopy(value)
        changed['source_authority_hash'] = 'f' * 64
        changed['assets'][0]['authority_hash'] = 'f' * 64
        self.assertNotEqual(self.protocol.view_hash(value), self.protocol.view_hash(changed))

    def test_runtime_flags_and_self_referential_identity_are_not_manifest_fields(self):
        for key in ('native_ready', 'semantic_ok', 'owner_approved', 'view_id', 'view_hash', 'manifest_blob_hash'):
            with self.subTest(key=key):
                self.reject({**manifest(), key: True})

    def test_missing_fields_and_unsupported_versions_or_evidence_classes_reject(self):
        for key in manifest():
            value = manifest()
            del value[key]
            with self.subTest(key=key):
                self.reject(value)
        for key, bad in (('version', True), ('version', 2), ('evidence_class', 'business'), ('variant', 'live')):
            self.reject({**manifest(), key: bad})

    def test_generations_policy_and_ordinal_are_bounded_integers(self):
        for key in ('context_generation', 'policy_version', 'arm_ordinal'):
            for bad in (True, 1.0, -1, 2 ** 63):
                with self.subTest(key=key, bad=bad):
                    self.reject({**manifest(), key: bad})
        self.reject({**manifest(), 'arm_ordinal': 4})
        value = manifest()
        value['target']['base_generation'] = True
        self.reject(value)

    def test_hashes_require_exact_lowercase_sha256(self):
        for bad in ('A' * 64, 'a' * 63, '', None, True):
            self.reject({**manifest(), 'comparison_hash': bad})
            value = manifest()
            value['semantic']['assessment_hash'] = bad
            self.reject(value)

    def test_single_primary_body_cannot_expand_into_additional_assets(self):
        for assets in ([], [manifest()['assets'][0]] * 2):
            self.reject({**manifest(), 'assets': assets})
        value = manifest()
        value['assets'][0]['content'] = 'Unpinned new instructions.'
        self.reject(value)

    def test_only_canonical_user_skill_paths_and_ownership_are_valid(self):
        for path in ('../skills/reconcile/SKILL.md', '.claude/skills/reconcile/SKILL.md',
                     'agents/reconcile.md', 'skills/CON/SKILL.md', 'skills/con/SKILL.md',
                     'skills/com1/SKILL.md', 'skills/reconcile/helper.py'):
            value = manifest()
            value['target']['canonical_ref'] = path
            value['assets'][0]['canonical_ref'] = path
            with self.subTest(path=path):
                self.reject(value)
        for ownership in ('system', 'pack_managed', True):
            value = manifest()
            value['target']['ownership'] = ownership
            self.reject(value)

    def test_variant_asset_and_original_target_must_match_exactly(self):
        for key, bad in (('id', 'other_revision'), ('canonical_ref', 'skills/other/SKILL.md'),
                         ('before_hash', 'f' * 64), ('identity', 'f' * 64),
                         ('authority_hash', 'f' * 64), ('origin', 'candidate'), ('content_hash', 'f' * 64)):
            value = manifest()
            value['assets'][0][key] = bad
            with self.subTest(key=key):
                self.reject(value)
        value = manifest('candidate')
        value['assets'][0]['id'] = value['target']['base_revision_id']
        self.reject(value)

    def test_semantic_owner_reference_is_data_not_an_approval_flag(self):
        value = manifest()
        value['semantic']['owner_event_key'] = 'owner-reviewed-exact-view'
        self.assertEqual(self.protocol.view_manifest(value), value)
        for bad in (True, {}, '', 'x' * 7, 'x' * 161, 'x' * 201):
            value['semantic']['owner_event_key'] = bad
            self.reject(value)

    def test_identifiers_are_bounded_and_never_paths(self):
        for bad in ('../other', '', 'x' * 129, True):
            self.reject({**manifest(), 'candidate_id': bad})
        self.reject({**manifest(), 'brain_id': 'x' * 1001})


if __name__ == '__main__':
    unittest.main()
