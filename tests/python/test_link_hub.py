"""Tests for server/link_hub.py (zero-token link hub)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "server"))

import link_hub


class TestDetect:
    def test_single_url(self):
        urls, note = link_hub.detect("https://instagram.com/reel/abc123")
        assert urls == ["https://instagram.com/reel/abc123"]
        assert note == ""

    def test_url_with_short_note(self):
        urls, note = link_hub.detect("https://tiktok.com/@foo/video/1 check this")
        assert len(urls) == 1
        assert note == "check this"

    def test_multiple_urls(self):
        text = "https://a.com/1 https://b.com/2 https://c.com/3"
        urls, note = link_hub.detect(text)
        assert len(urls) == 3

    def test_url_with_long_note_rejected(self):
        long = "a" * 70
        urls, _ = link_hub.detect(f"https://x.com/1 {long}")
        assert urls == []

    def test_question_mark_rejected(self):
        urls, _ = link_hub.detect("https://x.com/1 cái này là gì?")
        assert urls == []

    def test_instruction_words_rejected(self):
        for phrase in ["phân tích link này", "explain this", "review cái này",
                       "tóm tắt", "so sánh", "kiểm tra", "là gì", "vì sao"]:
            urls, _ = link_hub.detect(f"https://x.com/1 {phrase}")
            assert urls == [], f"should reject: {phrase}"

    def test_casual_notes_accepted(self):
        for phrase in ["check this", "xem nè", "hay", "inspo", "ref"]:
            urls, _ = link_hub.detect(f"https://x.com/1 {phrase}")
            assert len(urls) == 1, f"should accept: {phrase}"

    def test_no_url(self):
        urls, _ = link_hub.detect("hello world no links here")
        assert urls == []

    def test_empty(self):
        urls, _ = link_hub.detect("")
        assert urls == []

    def test_instagram_reel(self):
        urls, note = link_hub.detect(
            "https://www.instagram.com/reel/De7QatoxKIr/ everything.aligns")
        assert len(urls) == 1
        assert note == "everything.aligns"


class TestSave:
    def test_creates_new_file(self):
        with tempfile.TemporaryDirectory() as td:
            confirm = link_hub.save(td, ["https://a.com/1"], "note", "Test")
            path = link_hub.hub_path(td)
            assert os.path.exists(path)
            content = open(path, encoding="utf-8").read()
            assert "https://a.com/1" in content
            assert "note" in content
            assert "Test" in content
            assert "| Ngày giờ |" in content
            assert "✓" in confirm

    def test_appends_to_existing(self):
        with tempfile.TemporaryDirectory() as td:
            link_hub.save(td, ["https://a.com/1"], "", "Test")
            link_hub.save(td, ["https://b.com/2"], "hi", "Telegram")
            content = open(link_hub.hub_path(td), encoding="utf-8").read()
            assert "https://a.com/1" in content
            assert "https://b.com/2" in content
            assert "Telegram" in content

    def test_multiple_urls_in_one_call(self):
        with tempfile.TemporaryDirectory() as td:
            link_hub.save(td, ["https://a.com/1", "https://a.com/2"], "", "X")
            content = open(link_hub.hub_path(td), encoding="utf-8").read()
            assert content.count("https://a.com/") == 2
