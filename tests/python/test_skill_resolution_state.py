"""Discovery, actual hub reads and warm lazy cache share disabled-source state."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import os
import tempfile
import unittest
from pathlib import Path

_STATE = tempfile.TemporaryDirectory(prefix='skill-state-import-')
os.environ['JAVIS_STATE_DIR'] = _STATE.name
os.environ['BRAIN_PATH'] = str(Path(_STATE.name) / 'brain')
os.environ['BRAINS_DIR'] = str(Path(_STATE.name) / 'brains')

import skill_router
import skill_usage
from capability_registry import CapabilityRegistry
from lazy_skill_runtime import LazySkillSource
import mcp_hub


class SkillResolutionStateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='skill-source-state-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.slug = 'reconcile'

    def write(self, base, marker):
        path = self.root / base / self.slug / 'SKILL.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(('---\nname: reconcile\ndescription: Reconcile authorized amount rows.\n---\n' + marker).encode())
        return path

    def assert_off(self):
        self.assertIsNone(skill_router.resolve_skill_file(self.root, self.slug))
        self.assertEqual(skill_router.list_enabled_meta(self.root), [])
        self.assertEqual(skill_router.list_skill_manifests(self.root), [])
        rows = skill_router.list_skills(self.root)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]['enabled'])

    def test_disabled_canonical_suppresses_enabled_mirrors(self):
        self.write('skills/.disabled', 'OWNER_DISABLED')
        self.write('.claude/skills', 'STALE_CLAUDE')
        self.write('.agents', 'STALE_LEGACY')
        self.assert_off()

    def test_same_source_enabled_disabled_collision_stays_off(self):
        self.write('skills', 'ENABLED_COLLISION')
        self.write('skills/.disabled', 'OWNER_DISABLED')
        self.write('.claude/skills', 'STALE_CLAUDE')
        self.assert_off()

    def test_disabled_claude_source_suppresses_lower_legacy_copy(self):
        self.write('.claude/skills/.disabled', 'OWNER_DISABLED')
        self.write('.agents', 'STALE_LEGACY')
        self.assert_off()

    def test_legacy_disabled_collision_agrees_with_manifests(self):
        self.write('.agents', 'ENABLED_COLLISION')
        self.write('.agents/.disabled', 'OWNER_DISABLED')
        self.assert_off()

    def test_enabled_source_precedence_and_legacy_only_fallback_are_preserved(self):
        for base, marker in (('.agents', 'LEGACY'), ('.claude/skills', 'CLAUDE'), ('skills', 'CANONICAL')):
            expected = self.write(base, marker)
            self.assertEqual(skill_router.resolve_skill_file(self.root, self.slug), expected)
            self.assertEqual(skill_router.list_enabled_meta(self.root)[0]['source'], base)
        self.assertIsNone(skill_router.resolve_skill_file(self.root, '../reconcile'))

    def disable_canonical(self, path):
        disabled = self.root / 'skills/.disabled' / self.slug
        disabled.parent.mkdir(parents=True, exist_ok=True)
        path.parent.rename(disabled)

    def test_existing_hub_handler_refuses_stale_mirror_without_counting_a_use(self):
        canonical = self.write('skills', 'CANONICAL')
        self.write('.claude/skills', 'STALE_CLAUDE')
        _, routes = mcp_hub._builtin_tools('auto', str(self.root))
        handler = routes['javis_use_skill']['call']
        self.assertIn('CANONICAL', asyncio.run(handler({'name': self.slug})))
        self.assertEqual(skill_usage.read_usage(self.root)[self.slug]['use_count'], 1)
        self.disable_canonical(canonical)
        result = asyncio.run(handler({'name': self.slug}))
        self.assertTrue(result.startswith('ERROR'), result)
        self.assertNotIn('STALE_CLAUDE', result)
        self.assertEqual(skill_usage.read_usage(self.root)[self.slug]['use_count'], 1)

    def test_warmed_lazy_registry_drops_disabled_canonical_despite_stale_mirror(self):
        canonical = self.write('skills', 'CANONICAL')
        self.write('.claude/skills', 'STALE_CLAUDE')
        registry = CapabilityRegistry(self.root / 'state')
        self.addCleanup(registry.close)
        source = LazySkillSource(registry)
        selected = source.resolve(self.root, 'reconcile')
        self.assertEqual(selected.action, 'load')
        self.assertIn('CANONICAL', selected.context_item.content)
        self.disable_canonical(canonical)
        selected = source.resolve(self.root, 'reconcile')
        self.assertNotEqual(selected.action, 'load')
        self.assertIsNone(selected.context_item)
        self.assertEqual(source.refresh(self.root)['manifest_count'], 0)


if __name__ == '__main__':
    unittest.main()
