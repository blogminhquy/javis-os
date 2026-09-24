from _paths import SERVER  # noqa: F401
import logging
import unittest
import voice_privacy


class AccessPrivacy(unittest.TestCase):
    def test_tts_query_redacted_without_hiding_status_or_other_routes(self):
        for path, expected in [('/tts?text=private+words&voice=vi', '/tts'),
                               ('/tts?text=secret%20words', '/tts'),
                               ('/health', '/health'), ('/tts/voices', '/tts/voices')]:
            record = logging.LogRecord('uvicorn.access', logging.INFO, '', 1,
                                       '%s - "%s %s HTTP/%s" %d',
                                       ('127.0.0.1', 'GET', path, '1.1', 200), None)
            self.assertTrue(voice_privacy.VoiceAccessFilter().filter(record))
            self.assertEqual(record.getMessage(), f'127.0.0.1 - "GET {expected} HTTP/1.1" 200')

    def test_install_is_idempotent(self):
        voice_privacy.install()
        voice_privacy.install()
        self.assertEqual(sum(isinstance(f, voice_privacy.VoiceAccessFilter)
                             for f in logging.getLogger('uvicorn.access').filters), 1)


if __name__ == '__main__':
    unittest.main()
