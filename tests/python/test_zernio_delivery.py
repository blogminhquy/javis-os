"""Delivery policy contracts, without provider traffic."""
from _paths import ROOT, SERVER
import unittest
import importlib.util


class DeliveryPolicyTests(unittest.TestCase):
    def policy(self):
        self.assertIsNotNone(importlib.util.find_spec('zernio_delivery'), 'delivery policy missing')
        import zernio_delivery
        return zernio_delivery

    def test_status_classification(self):
        p = self.policy()
        for status, kind in [(200, 'accepted'), (201, 'accepted'), (408, 'retry'),
                             (429, 'retry'), (500, 'retry'), (503, 'retry'),
                             (None, 'retry'), (400, 'blocked'), (401, 'blocked'),
                             (403, 'blocked'), (404, 'blocked'), (302, 'blocked')]:
            with self.subTest(status=status):
                result = p.classify_delivery(status, None, 0)
                self.assertEqual(result['kind'], kind)
                self.assertIn('code', result)
                self.assertIsNone(result['retry_after_seconds'])

    def test_retry_after_dates_and_invalid_values(self):
        p = self.policy()
        for value, expected in [('120', 120), ('Thu, 01 Jan 1970 00:02:00 GMT', 120),
                                ('Wed, 31 Dec 1969 23:59:00 GMT', 0),
                                ('garbage', None), ('-1', None), ('NaN', None),
                                ('inf', None), ('', None), (None, None)]:
            with self.subTest(value=value):
                self.assertEqual(p.classify_delivery(429, value, 0)['retry_after_seconds'], expected)

    def test_retry_backoff_and_jitter(self):
        p = self.policy()
        for attempt, expected in [(0, 5), (1, 10), (5, 160), (6, 300), (10000, 300)]:
            self.assertEqual(p.retry_delay(attempt, None, 0), expected)
            self.assertAlmostEqual(p.retry_delay(attempt, None, 1), expected * 1.2)
        self.assertEqual(p.retry_delay(0, 900, 1), 900)


if __name__ == '__main__':
    unittest.main()
