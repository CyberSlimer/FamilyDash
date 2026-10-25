"""
Tests for display configuration and the photo store.

Run from the backend/ directory:
    python -m unittest discover -s tests -v
"""

import io
import os
import re
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


def _png(width=40, height=30, color=(200, 30, 60)):
    """A real PNG so Pillow has something to open."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (width, height), color).save(buf, format='PNG')
    buf.seek(0)
    return buf


def tearDownModule():
    shutil.rmtree(_tmp, ignore_errors=True)


class DisplayTestCase(unittest.TestCase):
    def setUp(self):
        self.ctx = dashboard.app.app_context()
        self.ctx.push()
        dashboard.db.drop_all()
        dashboard.db.create_all()
        self.client = dashboard.app.test_client()
        os.makedirs(dashboard.PHOTO_DIR, exist_ok=True)

    def tearDown(self):
        dashboard.db.session.remove()
        self.ctx.pop()

    def get_config(self):
        return self.client.get('/api/display').get_json()['config']

    def put_config(self, **kw):
        return self.client.put('/api/display', json=kw)


class ConfigTests(DisplayTestCase):
    def test_defaults_are_served_before_anything_is_saved(self):
        data = self.client.get('/api/display').get_json()
        self.assertEqual(data['config']['rotation_interval'], 30)
        self.assertEqual(len(data['config']['screens']), 5)
        self.assertIn('photos', data['screen_types'])

    def test_round_trip(self):
        self.put_config(rotation_interval=45, theme={'primary': '#112233'})
        config = self.get_config()
        self.assertEqual(config['rotation_interval'], 45)
        self.assertEqual(config['theme']['primary'], '#112233')

    def test_home_focus_defaults_on_and_round_trips(self):
        self.assertIs(self.get_config()['home_focus'], True)
        self.put_config(home_focus=False)
        self.assertIs(self.get_config()['home_focus'], False)
        self.put_config(home_focus=True)
        self.assertIs(self.get_config()['home_focus'], True)

    def test_home_focus_survives_an_unrelated_save(self):
        # The phone sends the whole config on every change, but a scripted PUT
        # or an older build of the app may not know this key. An omitted key
        # falls back to the default here, as every other setting does, and the
        # default is on - so the failure mode is a home screen, not a surprise.
        self.put_config(home_focus=False)
        self.put_config(rotation_interval=45)
        self.assertEqual(self.get_config()['rotation_interval'], 45)
        self.assertIs(self.get_config()['home_focus'], True)

    def test_rotation_interval_is_clamped(self):
        self.put_config(rotation_interval=99999)
        self.assertEqual(self.get_config()['rotation_interval'], 3600)
        self.put_config(rotation_interval=0)
        self.assertEqual(self.get_config()['rotation_interval'], 5)

    def test_junk_interval_falls_back_to_the_default(self):
        self.put_config(rotation_interval='not a number')
        self.assertEqual(self.get_config()['rotation_interval'], 30)

    def test_bad_colour_is_rejected(self):
        self.put_config(theme={'primary': 'javascript:alert(1)'})
        self.assertEqual(self.get_config()['theme']['primary'], '#667eea')

    def test_font_with_css_punctuation_is_rejected(self):
        self.put_config(theme={'font': 'Arial; } body { display:none'})
        self.assertNotIn(';', self.get_config()['theme']['font'])

    def test_plain_font_stack_is_accepted(self):
        self.put_config(theme={'font': "Georgia, 'Times New Roman', serif"})
        self.assertEqual(self.get_config()['theme']['font'], "Georgia, 'Times New Roman', serif")

    def test_card_opacity_is_clamped(self):
        self.put_config(theme={'card_opacity': 5})
        self.assertEqual(self.get_config()['theme']['card_opacity'], 0.6)

    def test_screens_can_be_reordered(self):
        self.put_config(screens=[{'id': 'photos'}, {'id': 'grocery'}, {'id': 'calendar'},
                                 {'id': 'meals'}, {'id': 'recipes'}])
        self.assertEqual([s['id'] for s in self.get_config()['screens']][0], 'photos')

    def test_screens_can_be_disabled(self):
        self.put_config(screens=[{'id': 'calendar', 'enabled': False}])
        screens = {s['id']: s['enabled'] for s in self.get_config()['screens']}
        self.assertFalse(screens['calendar'])

    def test_unknown_screen_ids_are_dropped(self):
        self.put_config(screens=[{'id': 'evil'}, {'id': 'calendar'}])
        ids = [s['id'] for s in self.get_config()['screens']]
        self.assertNotIn('evil', ids)
        self.assertIn('calendar', ids)

    def test_omitted_screens_are_kept(self):
        # A client that only knows about 2 screens must not delete the others.
        self.put_config(screens=[{'id': 'calendar'}, {'id': 'meals'}])
        self.assertEqual(len(self.get_config()['screens']), 5)

    def test_duplicate_screen_ids_collapse(self):
        self.put_config(screens=[{'id': 'calendar'}, {'id': 'calendar'}])
        ids = [s['id'] for s in self.get_config()['screens']]
        self.assertEqual(ids.count('calendar'), 1)

    def test_photo_screen_options(self):
        self.put_config(screens=[{'id': 'photos', 'enabled': True,
                                  'options': {'interval': 12, 'shuffle': False}}])
        photos = [s for s in self.get_config()['screens'] if s['id'] == 'photos'][0]
        self.assertEqual(photos['options']['interval'], 12)
        self.assertFalse(photos['options']['shuffle'])

    def test_screensaver_settings(self):
        self.put_config(screensaver={'enabled': True, 'idle_seconds': 120})
        saver = self.get_config()['screensaver']
        self.assertTrue(saver['enabled'])
        self.assertEqual(saver['idle_seconds'], 120)

    def test_screensaver_idle_is_clamped(self):
        self.put_config(screensaver={'idle_seconds': 1})
        self.assertEqual(self.get_config()['screensaver']['idle_seconds'], 30)

    def test_revision_advances_on_change(self):
        first = self.client.get('/api/display').get_json()['revision']
        self.put_config(rotation_interval=40)
        second = self.client.get('/api/display').get_json()['revision']
        self.assertGreater(second, first)

    def test_revision_endpoint_is_cheap_and_matches(self):
        self.put_config(rotation_interval=40)
        full = self.client.get('/api/display').get_json()['revision']
        light = self.client.get('/api/display/revision').get_json()['revision']
        self.assertEqual(full, light)

    def test_reset_restores_defaults(self):
        self.put_config(rotation_interval=300)
        self.client.post('/api/display/reset', json={})
        self.assertEqual(self.get_config()['rotation_interval'], 30)

    def test_corrupt_stored_config_falls_back(self):
        dashboard._put_setting('display_config', 'not json{')
        dashboard.db.session.commit()
        self.assertEqual(self.get_config()['rotation_interval'], 30)


class DisplayFormWiringTests(unittest.TestCase):
    """
    The Display tab autosaves; it has no Save button.

    A control that collectDisplay() reads but DISPLAY_INPUTS does not list
    gets no input/change listener, so changing it saves nothing while
    looking for all the world like it worked. That is how the screen
    rotation shipped broken. The fault is invisible from the backend, so
    this reads the page itself.
    """

    @classmethod
    def setUpClass(cls):
        backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        page = os.path.join(backend, '..', 'frontend', 'mobile.html')
        with open(page, encoding='utf-8') as fh:
            cls.html = fh.read()

    def listed_inputs(self):
        block = re.search(r'const DISPLAY_INPUTS = \[(.*?)\]', self.html, re.S)
        self.assertIsNotNone(block, 'DISPLAY_INPUTS has been renamed or removed')
        return set(re.findall(r"'([^']+)'", block.group(1)))

    def read_by_collect_display(self):
        body = re.search(r'function collectDisplay\(\) \{(.*?)\n        \}',
                         self.html, re.S)
        self.assertIsNotNone(body, 'collectDisplay has been renamed or removed')
        return set(re.findall(r"getElementById\('([^']+)'\)", body.group(1)))

    def test_every_saved_control_also_autosaves(self):
        missing = sorted(self.read_by_collect_display() - self.listed_inputs())
        self.assertEqual(
            missing, [],
            'collectDisplay reads these, but DISPLAY_INPUTS does not list them, '
            'so changing them saves nothing: %s' % missing)

    def test_the_rotation_control_is_wired(self):
        self.assertIn('display-screen-rotation', self.listed_inputs())
        self.assertIn('display-screen-rotation', self.read_by_collect_display())


class ScreenRotationTests(DisplayTestCase):
    """The value is handed to wlr-randr on the Pi, so it must stay a known one."""

    def test_rotation_round_trips(self):
        for value in ('90', '180', '270', 'normal'):
            config = self.client.get('/api/display').get_json()['config']
            config['screen_rotation'] = value
            saved = self.client.put('/api/display', json=config)
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.get_json()['config']['screen_rotation'], value)

    def test_the_default_is_landscape(self):
        config = self.client.get('/api/display').get_json()['config']
        self.assertEqual(config['screen_rotation'], 'normal')

    def test_anything_unknown_falls_back_rather_than_reaching_the_pi(self):
        # This string ends up as an argv entry for wlr-randr, so an
        # unrecognised value has to be dropped, not passed along.
        for value in ('; reboot', 'portrait', '45', '', None, 90):
            config = self.client.get('/api/display').get_json()['config']
            config['screen_rotation'] = value
            saved = self.client.put('/api/display', json=config)
            self.assertEqual(saved.status_code, 200)
            self.assertIn(saved.get_json()['config']['screen_rotation'],
                          ('normal', '90', '180', '270'))

    def test_rotation_survives_a_save_from_another_tab(self):
        # The Photos tab PUTs the whole config; a key it does not render
        # must not be flattened back to the default.
        config = self.client.get('/api/display').get_json()['config']
        config['screen_rotation'] = '90'
        self.client.put('/api/display', json=config)

        config = self.client.get('/api/display').get_json()['config']
        config['screensaver']['interval'] = 11
        after = self.client.put('/api/display', json=config).get_json()['config']
        self.assertEqual(after['screen_rotation'], '90')


class PhotoScreenOptionTests(DisplayTestCase):
    """The Photos tab is the only place these three are editable."""

    def test_photo_screen_options_round_trip(self):
        config = self.client.get('/api/display').get_json()['config']
        screens = config['screens']
        for screen in screens:
            if screen['id'] == 'photos':
                screen['options'] = {'interval': 20, 'shuffle': False, 'captions': False}
        saved = self.client.put('/api/display', json={**config, 'screens': screens})
        self.assertEqual(saved.status_code, 200)
        opts = next(s for s in saved.get_json()['config']['screens']
                    if s['id'] == 'photos')['options']
        self.assertEqual(opts, {'interval': 20, 'shuffle': False, 'captions': False})

    def test_saving_from_the_photos_tab_leaves_the_theme_alone(self):
        # The Photos tab shares the display config, so it PUTs the whole thing.
        # If it ever sent a half-filled form the theme would be flattened back
        # to the defaults, which is a nasty way to lose a colour scheme.
        config = self.client.get('/api/display').get_json()['config']
        config['theme']['primary'] = '#123456'
        self.client.put('/api/display', json=config)

        config = self.client.get('/api/display').get_json()['config']
        config['screensaver']['interval'] = 12
        after = self.client.put('/api/display', json=config).get_json()['config']
        self.assertEqual(after['theme']['primary'], '#123456')
        self.assertEqual(after['screensaver']['interval'], 12)


class PhotoTests(DisplayTestCase):
    def upload(self, name='pic.png', data=None):
        return self.client.post(
            '/api/photos',
            data={'files': (data or _png(), name)},
            content_type='multipart/form-data')

    def test_upload_and_list(self):
        res = self.upload()
        self.assertEqual(res.status_code, 201)
        photos = self.client.get('/api/photos').get_json()
        self.assertEqual(len(photos), 1)
        self.assertTrue(photos[0]['url'].startswith('/photos/'))

    def test_stored_file_exists_and_is_served(self):
        self.upload()
        photo = self.client.get('/api/photos').get_json()[0]
        self.assertTrue(os.path.isfile(os.path.join(dashboard.PHOTO_DIR, photo['filename'])))
        self.assertEqual(self.client.get(photo['url']).status_code, 200)

    def test_original_filename_is_not_used_on_disk(self):
        # Guards against path traversal and name collisions.
        self.upload(name='../../etc/passwd.png')
        photo = self.client.get('/api/photos').get_json()[0]
        self.assertNotIn('/', photo['filename'])
        self.assertNotIn('..', photo['filename'])

    def test_dimensions_recorded(self):
        self.upload(data=_png(120, 90))
        photo = self.client.get('/api/photos').get_json()[0]
        self.assertEqual((photo['width'], photo['height']), (120, 90))

    def test_large_images_are_downscaled(self):
        self.upload(data=_png(4000, 3000))
        photo = self.client.get('/api/photos').get_json()[0]
        self.assertLessEqual(max(photo['width'], photo['height']), dashboard.MAX_PHOTO_EDGE)

    def test_non_image_is_rejected(self):
        res = self.client.post(
            '/api/photos',
            data={'files': (io.BytesIO(b'#!/bin/sh\nrm -rf /'), 'evil.sh')},
            content_type='multipart/form-data')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.client.get('/api/photos').get_json(), [])

    def test_empty_upload_is_rejected(self):
        res = self.client.post('/api/photos', data={}, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 400)

    def test_caption_can_be_set(self):
        self.upload()
        photo = self.client.get('/api/photos').get_json()[0]
        self.client.put(f"/api/photos/{photo['id']}", json={'caption': 'Beach 2026'})
        self.assertEqual(self.client.get('/api/photos').get_json()[0]['caption'], 'Beach 2026')

    def test_delete_removes_row_and_file(self):
        self.upload()
        photo = self.client.get('/api/photos').get_json()[0]
        path = os.path.join(dashboard.PHOTO_DIR, photo['filename'])
        self.client.delete(f"/api/photos/{photo['id']}")
        self.assertEqual(self.client.get('/api/photos').get_json(), [])
        self.assertFalse(os.path.exists(path))

    def test_reorder(self):
        self.upload('a.png')
        self.upload('b.png')
        ids = [p['id'] for p in self.client.get('/api/photos').get_json()]
        self.client.post('/api/photos/reorder', json={'ids': list(reversed(ids))})
        self.assertEqual([p['id'] for p in self.client.get('/api/photos').get_json()],
                         list(reversed(ids)))

    def test_upload_bumps_the_revision(self):
        before = self.client.get('/api/display/revision').get_json()['revision']
        self.upload()
        after = self.client.get('/api/display/revision').get_json()['revision']
        self.assertGreater(after, before)

    def test_photos_are_listed_with_the_display_config(self):
        self.upload()
        data = self.client.get('/api/display').get_json()
        self.assertEqual(len(data['photos']), 1)


if __name__ == '__main__':
    unittest.main()
