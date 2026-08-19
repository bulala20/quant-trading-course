import datetime as dt
import unittest

from tools.screen_a_share import history_start


class ScreenerTests(unittest.TestCase):
    def test_history_start_uses_rolling_calendar_window(self):
        self.assertEqual(history_start(dt.date(2026, 8, 19), 180), "20260220")

    def test_history_start_rejects_too_short_window(self):
        with self.assertRaisesRegex(ValueError, "at least 30"):
            history_start(dt.date(2026, 8, 19), 10)


if __name__ == "__main__":
    unittest.main()
