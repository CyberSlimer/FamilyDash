"""
Tests for calendar_sync using a local HTTP server that serves fixtures/sample.ics.

Run from the backend/ directory:
    python -m unittest discover -s tests -v
"""

import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from functools import partial
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import calendar_sync  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')
TZ = ZoneInfo('America/New_York')


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class CalendarSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = partial(_QuietHandler, directory=FIXTURES)
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

        cls.tmp = tempfile.TemporaryDirectory()
        cls.config_path = os.path.join(cls.tmp.name, 'calendars.json')
        os.environ['TEST_FEED_URL'] = f'http://127.0.0.1:{cls.port}/sample.ics'
        with open(cls.config_path, 'w') as fh:
            json.dump({'calendars': [
                {'id': 'test', 'name': 'Test Feed', 'type': 'ics', 'url': '${TEST_FEED_URL}', 'color': '#123456'},
                {'id': 'broken', 'name': 'Broken', 'type': 'ics', 'url': f'http://127.0.0.1:{cls.port}/missing.ics'},
                {'id': 'off', 'name': 'Disabled', 'type': 'ics', 'url': 'http://example.invalid/x.ics', 'enabled': False},
            ]}, fh)

        os.environ['TIMEZONE'] = 'America/New_York'
        # Pin "now" so the fixture dates (September 2026) stay inside the window.
        cls.fake_now = datetime(2026, 9, 17, 8, 0, tzinfo=TZ)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.tmp.cleanup()

    def make_sync(self):
        sync = calendar_sync.CalendarSync(self.config_path, lookahead_days=14, clock=lambda: self.fake_now)
        sync.refresh()
        return sync

    def day(self, offset=0):
        start = self.fake_now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=offset)
        return start, start + timedelta(days=1)

    # ---- config ------------------------------------------------------------

    def test_config_expands_env_and_skips_disabled(self):
        cals = calendar_sync.load_calendar_config(self.config_path)
        self.assertEqual([c['id'] for c in cals], ['test', 'broken'])
        self.assertTrue(cals[0]['url'].startswith('http://127.0.0.1'))
        self.assertEqual(cals[0]['color'], '#123456')
        self.assertTrue(cals[1]['color'].startswith('#'))  # default color assigned

    # ---- events --------------------------------------------------------------

    def test_today_events(self):
        sync = self.make_sync()
        today = sync.get_events(*self.day(0))
        titles = [e['title'] for e in today]

        self.assertIn('Picture Day (all-day)', titles)
        self.assertIn('Soccer Practice', titles)            # Thursday instance of a TU/TH rule
        self.assertTrue(any(t.startswith('Dentist') for t in titles))
        self.assertNotIn('Should NOT appear', titles)       # STATUS:CANCELLED
        self.assertNotIn('Old event, outside window', titles)

        # All-day events sort first, then by time
        self.assertEqual(titles[0], 'Picture Day (all-day)')
        self.assertTrue(today[0]['all_day'])

        dentist = next(e for e in today if e['title'].startswith('Dentist'))
        self.assertEqual(dentist['start'], '2026-09-17T14:30:00-04:00')  # 18:30Z -> 2:30 PM EDT
        self.assertFalse(dentist['all_day'])

        soccer = next(e for e in today if e['title'] == 'Soccer Practice')
        self.assertEqual(soccer['location'], 'Cobbs Hill Park')
        self.assertEqual(soccer['calendar_name'], 'Test Feed')
        self.assertEqual(soccer['color'], '#123456')

        # No private fields leak into the JSON payload
        self.assertFalse(any(k.startswith('_') for e in today for k in e))

    def test_recurrence_expands_across_week(self):
        sync = self.make_sync()
        start, _ = self.day(0)
        week = sync.get_events(start, start + timedelta(days=7))
        soccer_days = sorted(e['start'][:10] for e in week if e['title'] == 'Soccer Practice')
        # Thu 17, Tue 22 within Sep 17..23
        self.assertEqual(soccer_days, ['2026-09-17', '2026-09-22'])

    def test_multiday_event_appears_on_each_day(self):
        sync = self.make_sync()
        for offset in (2, 3, 4):  # Sep 19, 20, 21
            titles = [e['title'] for e in sync.get_events(*self.day(offset))]
            self.assertIn('Grandma visiting (multi-day)', titles, f'missing on day +{offset}')
        titles = [e['title'] for e in sync.get_events(*self.day(5))]  # Sep 22 (DTEND exclusive)
        self.assertNotIn('Grandma visiting (multi-day)', titles)

    def test_string_dates_accepted(self):
        sync = self.make_sync()
        by_str = sync.get_events('2026-09-17', '2026-09-18')
        by_iso = sync.get_events('2026-09-17T00:00:00-04:00', '2026-09-18T04:00:00Z')
        self.assertEqual([e['id'] for e in by_str], [e['id'] for e in by_iso])
        self.assertGreater(len(by_str), 0)

    def test_status_reports_failures(self):
        sync = self.make_sync()
        status = sync.status()
        by_id = {c['id']: c for c in status['calendars']}
        self.assertTrue(by_id['test']['ok'])
        self.assertGreater(by_id['test']['count'], 0)
        self.assertFalse(by_id['broken']['ok'])
        self.assertIn('404', by_id['broken']['error'])
        self.assertEqual(status['timezone'], 'America/New_York')
        self.assertTrue(status['enabled'])


if __name__ == '__main__':
    unittest.main()
