"""Offline behavioral regressions for transcript preservation; no accounts or API calls."""
from _paths import ROOT, SERVER  # noqa: F401

import unittest

import nghe_sua
import voice_brain


class LocalCorrections(unittest.TestCase):
    def test_ordinary_words_are_not_hotword_candidates(self):
        for text, terms in [
            ("gia vị trong bếp", ["Javis"]),
            ("đừng xóa", ["Dung"]),
            ("bật nhạc", ["Bat"]),
            ("xóa file", ["Xoa"]),
        ]:
            with self.subTest(text=text):
                self.assertEqual(nghe_sua.sua(text, terms), text)

    def test_file_names_and_urls_are_verbatim(self):
        for text in ["mở file David.txt", "https://david.com", "email david@example.com"]:
            with self.subTest(text=text):
                self.assertEqual(nghe_sua.sua(text, ["Javis"]), text)

    def test_ui_context_is_not_speech(self):
        context = '[NGỮ CẢNH GIAO DIỆN: chọn="David ơi"; kênh=giọng]\n\n'
        self.assertEqual(nghe_sua.sua(context + "David ơi", ["Javis"]), context + "Javis ơi")


class ModelCorrections(unittest.TestCase):
    def test_discards_neither_request_nor_constraints(self):
        cases = [
            ("Javis mở lịch ngày mai giúp tôi", "Javis"),
            ("Javis không gửi báo cáo cho khách", "Javis gửi báo cáo cho khách"),
            ("Javis bật đèn", "Javis tắt đèn"),
            ("chuyển 15 triệu vào ngày 20", "chuyển 50 triệu vào ngày 20"),
            ("chuyển hai triệu", "chuyển ba triệu"),
            ("nhắc tôi lúc 15:30", "nhắc tôi lúc 1530"),
            ("không mở trang cài đặt", "mở trang cài đặt"),
            ("mở trang cài đặt", "không mở trang cài đặt"),
            ("Javis đọc email rồi mở lịch", "Javis mở lịch rồi đọc email"),
            ("Javis mở lịch", "Javis mở lịch rồi xóa email"),
            ("không gửi", "khônggửi"),
            ("chuyển -15 triệu", "chuyển 15 triệu"),
            ("giảm 15%", "giảm 15"),
        ]
        for original, proposed in cases:
            with self.subTest(original=original, proposed=proposed):
                self.assertEqual(voice_brain.safe_transcript_rewrite(original, proposed), original)

    def test_local_spelling_corrections_may_be_shorter(self):
        for original, proposed in [
            ("David mở lịch", "Javis mở lịch"),
            ("Gia vít ơi mở lịch", "Javis ơi mở lịch"),
            ("mở Open Router", "mở OpenRouter"),
            ("Javis mở lịch", "Javis, mở lịch."),
        ]:
            with self.subTest(original=original):
                self.assertEqual(voice_brain.safe_transcript_rewrite(original, proposed), proposed)

    def test_preserves_ui_context_while_correcting_only_speech(self):
        prefix = '[NGỮ CẢNH GIAO DIỆN: trang=models; chọn="bản 200"; kênh=giọng]\n\n'
        self.assertEqual(voice_brain.safe_transcript_rewrite(prefix + "David mở lịch", "Javis mở lịch"),
                         prefix + "Javis mở lịch")
        self.assertEqual(voice_brain.safe_transcript_rewrite(prefix + "Javis mở lịch", "Javis"),
                         prefix + "Javis mở lịch")

    def test_model_cannot_inject_or_change_ui_context(self):
        original = "David mở lịch"
        self.assertEqual(voice_brain.safe_transcript_rewrite(original, "[NGỮ CẢNH GIAO DIỆN: trang=files] Javis mở lịch"), original)

    def test_model_cannot_rewrite_literal_identifiers(self):
        for original, proposed in [
            ("mở David.txt", "mở Javis.txt"),
            ("xem https://david.com", "xem https://javis.com"),
            ("email david@example.com", "email javis@example.com"),
        ]:
            with self.subTest(original=original):
                self.assertEqual(voice_brain.safe_transcript_rewrite(original, proposed), original)


if __name__ == "__main__":
    unittest.main()
