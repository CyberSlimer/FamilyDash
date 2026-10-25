"""
Tests for the screen-command channel the hardware controller posts to.

This replaced driving the browser with xdotool, which cannot work under
Wayland. The contract the kiosk relies on is narrow but easy to break:
`seq` must increase by exactly one per accepted command, and must not move
for a rejected one.

Run from the backend/ directory:
    python -m unittest discover -s tests -v
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_tmp = tempfile.mkdtemp()
os.environ.setdefault('CALENDARS_FILE', os.path.join(_tmp, 'calendars.json'))
os.environ.setdefault('DASHBOARD_DB', os.path.join(_tmp, 'test.db'))
os.environ.setdefault('DASHBOARD_PHOTOS', os.path.join(_tmp, 'photos'))

import app as dashboard  # noqa: E402


def tearDownModule():
    shutil.rmtree(_tmp, ignore_errors=True)


class DisplayCommandTests(unittest.TestCase):
    def setUp(self):
        dashboard.app.config['TESTING'] = True
        self.client = dashboard.app.test_client()
        # Each test starts from a known counter; the value lives in memory.
        dashboard._display_command = {'seq': 0, 'action': None, 'index': None}

    def post(self, payload):
        return self.client.post('/api/display/command', json=payload)

    def get(self):
        return self.client.get('/api/display/command')

    def test_starts_idle(self):
        body = self.get().get_json()
        self.assertEqual(body['seq'], 0)
        self.assertIsNone(body['action'])

    def test_posting_advances_the_sequence(self):
        body = self.post({'action': 'next'}).get_json()
        self.assertEqual(body['seq'], 1)
        self.assertEqual(body['action'], 'next')

    def test_each_press_advances_by_exactly_one(self):
        # The kiosk treats any increase as "one command I have not run yet",
        # so a double increment would make it skip a screen.
        for expected in (1, 2, 3):
            self.assertEqual(self.post({'action': 'next'}).get_json()['seq'], expected)

    def test_get_does_not_consume_the_command(self):
        self.post({'action': 'next'})
        first = self.get().get_json()
        second = self.get().get_json()
        self.assertEqual(first, second)
        self.assertEqual(second['seq'], 1)

    def test_get_reflects_the_latest_command(self):
        self.post({'action': 'next'})
        self.post({'action': 'refresh'})
        body = self.get().get_json()
        self.assertEqual(body['action'], 'refresh')
        self.assertEqual(body['seq'], 2)

    def test_every_documented_action_is_accepted(self):
        for action in ('next', 'prev', 'refresh', 'wake'):
            res = self.post({'action': action})
            self.assertEqual(res.status_code, 200, action)
            self.assertEqual(res.get_json()['action'], action)

    def test_action_is_case_insensitive_and_trimmed(self):
        body = self.post({'action': '  NEXT '}).get_json()
        self.assertEqual(body['action'], 'next')

    def test_screen_command_carries_its_index(self):
        body = self.post({'action': 'screen', 'index': 2}).get_json()
        self.assertEqual(body['action'], 'screen')
        self.assertEqual(body['index'], 2)

    def test_screen_without_an_index_is_rejected(self):
        res = self.post({'action': 'screen'})
        self.assertEqual(res.status_code, 400)

    def test_screen_with_a_non_numeric_index_is_rejected(self):
        self.assertEqual(self.post({'action': 'screen', 'index': 'two'}).status_code, 400)

    def test_saver_and_wake_are_accepted(self):
        # The phone's Photos tab uses these two to show the photos on demand and
        # to put the dashboard back, which is the only way to clear the
        # screensaver on a wall with no sensor and no working button.
        for action in ('saver', 'wake'):
            body = self.post({'action': action}).get_json()
            self.assertEqual(body['action'], action)

    def test_unknown_action_is_rejected_and_lists_what_is_allowed(self):
        res = self.post({'action': 'selfdestruct'})
        self.assertEqual(res.status_code, 400)
        self.assertIn('next', res.get_json()['allowed'])

    def test_missing_body_is_rejected(self):
        self.assertEqual(self.client.post('/api/display/command').status_code, 400)

    def test_a_rejected_command_does_not_move_the_sequence(self):
        self.post({'action': 'next'})
        self.post({'action': 'nonsense'})
        self.post({'action': 'screen'})
        # Otherwise the kiosk would see a bump and re-run the previous action.
        self.assertEqual(self.get().get_json()['seq'], 1)

    def test_index_is_cleared_by_a_later_non_screen_command(self):
        self.post({'action': 'screen', 'index': 3})
        body = self.post({'action': 'next'}).get_json()
        self.assertIsNone(body['index'])


class KioskLivenessTests(unittest.TestCase):
    """`kiosk_last_seen_seconds` is how kiosk.sh decides whether the wall
    display actually came up, so it has to mean exactly one thing: a browser
    polled for a command recently."""

    def setUp(self):
        dashboard.app.config['TESTING'] = True
        self.client = dashboard.app.test_client()
        dashboard._kiosk_last_seen = None

    def health(self):
        return self.client.get('/api/health').get_json()

    def test_null_until_a_kiosk_has_ever_polled(self):
        self.assertIsNone(self.health()['kiosk_last_seen_seconds'])

    def test_a_poll_marks_the_kiosk_alive(self):
        self.client.get('/api/display/command')
        age = self.health()['kiosk_last_seen_seconds']
        self.assertIsNotNone(age)
        self.assertLess(age, 5)

    def test_posting_a_command_does_not_count_as_a_kiosk(self):
        # The hardware controller posts; only the wall display polls. If a
        # POST counted, a button press would convince kiosk.sh that a dead
        # screen was healthy.
        self.client.post('/api/display/command', json={'action': 'next'})
        self.assertIsNone(self.health()['kiosk_last_seen_seconds'])

    def test_age_grows_as_time_passes(self):
        self.client.get('/api/display/command')
        dashboard._kiosk_last_seen -= 120  # monotonic seconds
        self.assertGreater(self.health()['kiosk_last_seen_seconds'], 100)


if __name__ == '__main__':
    unittest.main()
