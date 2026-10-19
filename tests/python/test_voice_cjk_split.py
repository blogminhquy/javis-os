"""Japanese and Chinese replies are cut into sentences for the speaker (0.220.0).

    python tests/run.py voice_cjk_split

`。！？` take no space after them, so the old rule (stop + whitespace) never cut a Japanese
paragraph and the whole reply went to TTS as one block: the first sound came very late.
"""
from _paths import ROOT, SERVER  # noqa: F401
import unittest

import voice_brain


class SplitTests(unittest.TestCase):
    def test_japanese_three_sentences(self):
        text = "今日は晴れです。売上は十二万円でした。明日も頑張ります！"
        out, pos = voice_brain.split_speakable(text, 0)
        self.assertEqual("".join(out), text)
        self.assertEqual(pos, len(text))

    def test_open_tail_waits(self):
        out, pos = voice_brain.split_speakable("今日は晴れです。売上は", 0)
        self.assertEqual(out, ["今日は晴れです。"])
        self.assertEqual(pos, len("今日は晴れです。"))

    def test_version_number_is_not_a_sentence_end(self):
        out, _ = voice_brain.split_speakable("Bản 0.220.0 đã ra", 0)
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()
