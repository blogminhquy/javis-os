"""Real view/source service with an inert synthetic CLI observer; no native query."""
from _paths import ROOT, SERVER  # noqa: F401

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import improvement_trial_selection as selection
import test_improvement_view_sources as sources


class ViewObservationTests(sources.SourceFixture, unittest.IsolatedAsyncioTestCase):
    def observe_binary(self):
        # Runtime staging must not mutate pinned skill-source authority. Linux
        # directory ctime changes when a sibling is created after provenance.
        directory = Path(self.enterContext(tempfile.TemporaryDirectory(prefix='view-runtime-')))
        binary = directory / 'inert-runtime.exe'
        binary.write_bytes(b'Synthetic binary observer; never execute')
        selected = self.host.selected_engine

        def observe():
            # Keep this fixture's existing synthetic pin and real frozen bindings.
            # Only CLI observation I/O is added; this grants no native readiness.
            selection._read_binary(binary, selection.MAX_BINARY_BYTES)
            return selected()

        self.enterContext(patch.object(self.host, 'selected_engine', side_effect=observe))
        return binary

    async def test_real_current_view_bounds_all_twelve_nested_binary_observations(self):
        subject = self.views_service()
        self.freeze(subject)
        binary = self.observe_binary()
        with patch.object(selection, '_read_stable', wraps=selection._read_stable) as read:
            resolved = subject.load_current(self.owner, self.comparison['id'], 'baseline')
        reads = [call for call in read.call_args_list if call.args[0] == binary and call.kwargs.get('digest')]
        self.assertEqual(len(reads), 2)
        self.assertEqual(self.host.selected_engine.call_count, 12)
        self.assertEqual(hashlib.sha256(resolved.content).hexdigest(), self.proposal['base_hash'])

    async def test_binary_change_after_last_capture_cannot_escape_as_a_resolved_view(self):
        subject = self.views_service()
        self.freeze(subject)
        binary = self.observe_binary()
        import improvement_views as views
        capture, calls = views.capture_sources, 0

        def changed(*args, **kwargs):
            nonlocal calls
            result = capture(*args, **kwargs)
            calls += 1
            if calls == 2:
                binary.write_bytes(b'Changed after all ordinary source capture checks')
            return result

        with patch.object(views, 'capture_sources', side_effect=changed), \
                self.assertRaisesRegex(ValueError, 'source_changed'):
            subject.load_current(self.owner, self.comparison['id'], 'baseline')
        self.assertEqual(calls, 2)


if __name__ == '__main__':
    unittest.main()
