"""Remote credentials must not break identity checks or permit another repository."""
from _paths import ROOT
import runpy
import unittest

matches_repository = runpy.run_path(str(ROOT / "tools/check-sync-remotes.py"))["matches_repository"]


class RemoteIdentityTests(unittest.TestCase):
    def test_expected_repository_with_or_without_credentials(self):
        for url in (
            "https://github.com/kk311/javis-os.git",
            "https://github.com/kk311/javis-os",
            "https://kk311:example-test-token@github.com/kk311/javis-os.git",
            "https://example-test-token@github.com:443/kk311/javis-os.git",
        ):
            with self.subTest(url=url):
                self.assertTrue(matches_repository(url, "kk311/javis-os"))

    def test_rejects_wrong_identity_and_malformed_urls(self):
        for url in (
            "https://github.com/other/javis-os.git",
            "https://github.com/kk311/other.git",
            "https://github.com.evil.example/kk311/javis-os.git",
            "https://github.com@evil.example/kk311/javis-os.git",
            "http://github.com/kk311/javis-os.git",
            "https://github.com:8443/kk311/javis-os.git",
            "https://github.com:invalid/kk311/javis-os.git",
            "https://github.com/kk311/javis-os.git?redirect=elsewhere",
            "https://github.com/kk311/javis-os.git#other",
            "https://[invalid",
        ):
            with self.subTest(url=url):
                self.assertFalse(matches_repository(url, "kk311/javis-os"))


if __name__ == "__main__":
    unittest.main()
