"""
Tests for the calendar management API (/api/calendar/calendars, /api/calendar/test).

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
from functools import partial

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Point the app at a throwaway calendars.json BEFORE importing it.
_tmp = tempfile.TemporaryDirectory()
os.environ['CALENDARS_FILE'] = os.path.join(_tmp.name, 'calendars.json')
os.environ['TIMEZONE'] = 'America/New_York'

import app as dashboard  # noqa: E402


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class CalendarApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = partial(_QuietHandler, directory=FIXTURES)
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.feed_url = f'http://127.0.0.1:{port}/sample.ics'
        cls.missing_url = f'http://127.0.0.1:{port}/missing.ics'
        cls.client = dashboard.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        _tmp.cleanup()

    def setUp(self):
        # Start every test from an empty config
        if os.path.exists(dashboard.calendar_sync.config_path):
            os.remove(dashboard.calendar_sync.config_path)
        dashboard.calendar_sync.reload()

    def stored(self):
        with open(dashboard.calendar_sync.config_path) as fh:
            return json.load(fh)['calendars']

    # ---- CRUD ------------------------------------------------------------

    def test_list_empty(self):
        res = self.client.get('/api/calendar/calendars')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), [])

    def test_add_edit_delete_roundtrip(self):
        res = self.client.post('/api/calendar/calendars', json={
            'name': 'School Stuff', 'type': 'ics', 'url': self.feed_url, 'color': '#123456'})
        self.assertEqual(res.status_code, 201, res.get_json())
        cal = res.get_json()
        self.assertEqual(cal['id'], 'school-stuff')
        self.assertEqual(cal['color'], '#123456')
        self.assertTrue(cal['enabled'])
        self.assertNotIn('password', cal)

        # Persisted to calendars.json and picked up by the sync service
        self.assertEqual([c['id'] for c in self.stored()], ['school-stuff'])
        self.assertEqual([c['id'] for c in dashboard.calendar_sync.calendars], ['school-stuff'])

        # Duplicate names get a unique id
        res = self.client.post('/api/calendar/calendars', json={
            'name': 'School Stuff', 'type': 'ics', 'url': self.feed_url})
        self.assertEqual(res.get_json()['id'], 'school-stuff-2')

        # Edit: rename + disable
        res = self.client.put('/api/calendar/calendars/school-stuff', json={'name': 'School', 'enabled': False})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['name'], 'School')
        self.assertFalse(res.get_json()['enabled'])
        self.assertEqual(self.stored()[0]['url'], self.feed_url)  # untouched fields kept
        # Disabled calendars are dropped from the live sync set
        self.assertEqual([c['id'] for c in dashboard.calendar_sync.calendars], ['school-stuff-2'])

        # Delete
        res = self.client.delete('/api/calendar/calendars/school-stuff')
        self.assertEqual(res.status_code, 200)
        self.assertEqual([c['id'] for c in self.stored()], ['school-stuff-2'])
        self.assertEqual(self.client.delete('/api/calendar/calendars/nope').status_code, 404)

    def test_validation(self):
        bad = [
            ({'type': 'ics', 'url': 'https://x'}, 'Name'),
            ({'name': 'A', 'type': 'ics'}, 'URL'),
            ({'name': 'A', 'type': 'ics', 'url': 'ftp://x'}, 'URL must'),
            ({'name': 'A', 'type': 'exchange', 'url': 'https://x'}, 'Type'),
            ({'name': 'A', 'type': 'ics', 'url': 'https://x', 'color': 'blue'}, 'Color'),
        ]
        for payload, needle in bad:
            res = self.client.post('/api/calendar/calendars', json=payload)
            self.assertEqual(res.status_code, 400, payload)
            self.assertIn(needle, res.get_json()['error'])
        self.assertEqual(self.client.get('/api/calendar/calendars').get_json(), [])

    def test_password_is_kept_and_never_returned(self):
        res = self.client.post('/api/calendar/calendars', json={
            'name': 'iCloud', 'type': 'caldav', 'url': 'https://caldav.example.com',
            'username': 'me@example.com', 'password': 'hunter2', 'calendars': 'Home, Kids'})
        self.assertEqual(res.status_code, 201, res.get_json())
        cal = res.get_json()
        self.assertNotIn('password', cal)
        self.assertTrue(cal['has_password'])
        self.assertIsNone(cal['password_ref'])
        self.assertEqual(cal['calendars'], ['Home', 'Kids'])

        # Editing without a password keeps the stored one
        self.client.put('/api/calendar/calendars/icloud', json={'name': 'iCloud Family', 'password': ''})
        self.assertEqual(self.stored()[0]['password'], 'hunter2')

        # ${VAR} references are surfaced so the user knows what's wired up
        self.client.put('/api/calendar/calendars/icloud', json={'password': '${ICLOUD_APP_PASSWORD}'})
        listed = self.client.get('/api/calendar/calendars').get_json()[0]
        self.assertEqual(listed['password_ref'], '${ICLOUD_APP_PASSWORD}')
        self.assertNotIn('password', listed)

    def test_list_includes_sync_status(self):
        self.client.post('/api/calendar/calendars', json={'name': 'Feed', 'type': 'ics', 'url': self.feed_url})
        self.client.post('/api/calendar/calendars', json={'name': 'Broken', 'type': 'ics', 'url': self.missing_url})
        dashboard.calendar_sync.refresh()  # synchronous, so status is populated
        by_id = {c['id']: c for c in self.client.get('/api/calendar/calendars').get_json()}
        self.assertTrue(by_id['feed']['status']['ok'])
        self.assertGreater(by_id['feed']['status']['count'], 0)
        self.assertFalse(by_id['broken']['status']['ok'])
        self.assertIn('404', by_id['broken']['status']['error'])

    def test_health(self):
        body = self.client.get('/api/health').get_json()
        self.assertEqual(body['app'], 'familydash')
        self.assertTrue(body['hostname'])
        self.assertIn('version', body)
        self.assertEqual(body['calendars'], 0)

    # ---- test endpoint -------------------------------------------------------

    def test_test_endpoint(self):
        res = self.client.post('/api/calendar/test', json={'name': 'x', 'type': 'ics', 'url': self.feed_url})
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body['ok'], body)
        self.assertGreaterEqual(body['count'], 1)
        self.assertLessEqual(len(body['sample']), 5)
        self.assertIn('title', body['sample'][0])
        self.assertFalse(any(k.startswith('_') for k in body['sample'][0]))

        res = self.client.post('/api/calendar/test', json={'name': 'x', 'type': 'ics', 'url': self.missing_url})
        body = res.get_json()
        self.assertFalse(body['ok'])
        self.assertIn('404', body['error'])

        res = self.client.post('/api/calendar/test', json={'name': 'x', 'type': 'ics', 'url': 'not a url'})
        self.assertEqual(res.status_code, 400)

    def test_test_endpoint_reuses_stored_password(self):
        # Store a calendar whose "password" is the feed URL's basic-auth (the fixture
        # server ignores auth, so this only checks that the stored value is merged in).
        self.client.post('/api/calendar/calendars', json={
            'name': 'Feed', 'type': 'ics', 'url': self.feed_url, 'username': 'u', 'password': 'p'})
        seen = {}
        original = dashboard.test_calendar

        def spy(cfg, tz=None, **kw):
            seen.update(cfg)
            return original(cfg, tz, **kw)

        dashboard.test_calendar = spy
        try:
            res = self.client.post('/api/calendar/test', json={'id': 'feed', 'name': 'Feed', 'type': 'ics', 'url': self.feed_url})
        finally:
            dashboard.test_calendar = original
        self.assertTrue(res.get_json()['ok'])
        self.assertEqual(seen.get('password'), 'p')


if __name__ == '__main__':
    unittest.main()
