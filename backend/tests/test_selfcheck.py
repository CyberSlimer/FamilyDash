"""
Tests for the appliance self-checks.

These exist because of a real two-day outage: the backend leaked one socket
per calendar refresh until its descriptor table was full, after which it
could not accept a connection, and systemd went on reporting it healthy.
Both halves of that are now checked at runtime, so both halves are checked
here - and the checks themselves have to behave on the Windows dev machine,
where there is no procfs and no RLIMIT_NOFILE to read.

Run from the backend/ directory:
    python -m unittest discover -s tests -v
"""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import selfcheck  # noqa: E402


class DescriptorReadingTests(unittest.TestCase):
    """What the process can learn about its own descriptor table."""

    def test_limit_is_a_positive_int_or_none(self):
        limit = selfcheck.descriptor_limit()
        if limit is not None:
            self.assertIsInstance(limit, int)
            self.assertGreater(limit, 0)

    def test_count_is_a_positive_int_or_none(self):
        count = selfcheck.open_descriptors()
        if count is not None:
            self.assertIsInstance(count, int)
            # stdin, stdout, stderr at the very least.
            self.assertGreaterEqual(count, 3)

    def test_count_and_limit_agree_about_the_platform(self):
        # Reading one and not the other would mean the watchdog could start
        # with no way to measure, or measure with nothing to compare against.
        if sys.platform.startswith('linux'):
            self.assertIsNotNone(selfcheck.open_descriptors())
            self.assertIsNotNone(selfcheck.descriptor_limit())

    def test_thresholds_leave_room_to_act(self):
        # The warning has to arrive before the restart, with enough gap that
        # a leak is visible in the journal before it is fatal.
        self.assertLess(selfcheck.WARN_FRACTION, selfcheck.FATAL_FRACTION)
        self.assertLess(selfcheck.FATAL_FRACTION, 1.0)


class ShadowedImportTests(unittest.TestCase):
    """Detecting a dependency that came from somewhere other than the venv.

    This is the check that would have named the cause on day one: urllib3
    resolving to ~/.local instead of the virtualenv.
    """

    def setUp(self):
        self.prefix = sys.prefix
        self.base_prefix = sys.base_prefix
        self.saved = {}
        # Pretend we are in a virtualenv rooted somewhere unambiguous, so the
        # test does not depend on how the suite itself was invoked.
        sys.prefix = os.path.join(os.path.abspath(os.sep), 'venv')
        sys.base_prefix = os.path.join(os.path.abspath(os.sep), 'usr')

    def tearDown(self):
        sys.prefix = self.prefix
        sys.base_prefix = self.base_prefix
        for name, module in self.saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def fake_module(self, name, path):
        self.saved[name] = sys.modules.get(name)
        module = types.ModuleType(name)
        module.__file__ = path
        sys.modules[name] = module

    def test_module_inside_the_venv_is_not_reported(self):
        self.fake_module('pretend_http',
                         os.path.join(sys.prefix, 'lib', 'pretend_http', '__init__.py'))
        self.assertEqual(selfcheck.shadowed_imports(('pretend_http',)), [])

    def test_module_from_the_system_python_is_not_reported(self):
        # The venv is built with --system-site-packages on purpose, so
        # Debian's dist-packages is a legitimate source. Flagging it would
        # mean a warning on every boot, which is a warning nobody reads.
        self.fake_module('pretend_http',
                         os.path.join(sys.base_prefix, 'lib', 'python3',
                                      'dist-packages', 'pretend_http', '__init__.py'))
        self.assertEqual(selfcheck.shadowed_imports(('pretend_http',)), [])

    def test_module_from_user_site_is_reported(self):
        stray = os.path.join(os.path.abspath(os.sep), 'home', 'pi', '.local',
                             'lib', 'pretend_http', '__init__.py')
        self.fake_module('pretend_http', stray)
        found = selfcheck.shadowed_imports(('pretend_http',))
        self.assertEqual([name for name, _path in found], ['pretend_http'])
        self.assertEqual(found[0][1], stray)

    def test_module_that_was_never_imported_is_not_reported(self):
        # Absent is not the same as substituted, and claiming otherwise would
        # warn about every optional dependency.
        self.assertEqual(selfcheck.shadowed_imports(('definitely_not_imported',)), [])

    def test_builtin_without_a_file_is_not_reported(self):
        self.saved['pretend_builtin'] = sys.modules.get('pretend_builtin')
        sys.modules['pretend_builtin'] = types.ModuleType('pretend_builtin')
        self.assertEqual(selfcheck.shadowed_imports(('pretend_builtin',)), [])

    def test_outside_a_venv_nothing_is_reported(self):
        # With no virtualenv there is no "should have come from here", so the
        # check has nothing to say rather than flagging every stdlib path.
        sys.base_prefix = sys.prefix
        self.fake_module('pretend_http',
                         os.path.join(os.path.abspath(os.sep), 'elsewhere', 'x.py'))
        self.assertEqual(selfcheck.shadowed_imports(('pretend_http',)), [])

    def test_the_watched_list_covers_the_http_stack(self):
        self.assertIn('urllib3', selfcheck.WATCHED_IMPORTS)
        self.assertIn('requests', selfcheck.WATCHED_IMPORTS)


class WatchdogTests(unittest.TestCase):
    """The loop that turns a descriptor leak into a restart."""

    def setUp(self):
        self.interval = selfcheck.CHECK_INTERVAL
        self.counter = selfcheck.open_descriptors
        selfcheck.CHECK_INTERVAL = 0.0

    def tearDown(self):
        selfcheck.CHECK_INTERVAL = self.interval
        selfcheck.open_descriptors = self.counter

    def counts(self, *values):
        """Feed the loop a fixed series, then stop it by going unreadable."""
        series = list(values) + [None]
        selfcheck.open_descriptors = lambda: series.pop(0)

    def test_quiet_run_does_not_restart(self):
        fired = []
        self.counts(10, 12, 11)
        selfcheck._watch(100, lambda: fired.append(True))
        self.assertEqual(fired, [])

    def test_crossing_the_fatal_line_restarts(self):
        fired = []
        self.counts(10, 90)
        selfcheck._watch(100, lambda: fired.append(True))
        self.assertEqual(fired, [True])

    def test_restart_happens_once_and_stops_looping(self):
        # _watch must return after firing: a second call would mean two
        # os._exit attempts racing, and in the test, an exhausted series.
        fired = []
        self.counts(90, 95, 99)
        selfcheck._watch(100, lambda: fired.append(True))
        self.assertEqual(fired, [True])

    def test_warning_level_alone_does_not_restart(self):
        fired = []
        self.counts(70, 75, 70)       # above 60%, below 85%
        selfcheck._watch(100, lambda: fired.append(True))
        self.assertEqual(fired, [])

    def test_unreadable_count_ends_the_loop_quietly(self):
        fired = []
        selfcheck.open_descriptors = lambda: None
        selfcheck._watch(100, lambda: fired.append(True))
        self.assertEqual(fired, [])

    def test_no_watchdog_where_there_is_nothing_to_read(self):
        selfcheck.open_descriptors = lambda: None
        self.assertIsNone(selfcheck.start_descriptor_watchdog(lambda: None))

    def test_watchdog_starts_as_a_daemon_when_readable(self):
        if selfcheck.descriptor_limit() is None or self.counter() is None:
            self.skipTest('no descriptor table to watch on this platform')
        selfcheck.CHECK_INTERVAL = self.interval   # do not spin the real thread
        thread = selfcheck.start_descriptor_watchdog(lambda: None)
        self.assertIsNotNone(thread)
        # Daemon: a wedged watchdog must never be what keeps the process alive.
        self.assertTrue(thread.daemon)


class OutageGuardTests(unittest.TestCase):
    """The declarations that keep the original cause from coming back.

    The runtime checks above report the problem; these three lines are what
    prevent it. They are easy to loosen by accident - a dependency bump, a
    rewritten unit file - and nothing else would notice until the wall went
    quiet again two days later.
    """

    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))

    def read(self, *parts):
        with open(os.path.join(self.ROOT, *parts), encoding='utf-8') as handle:
            return handle.read()

    def test_caldav_stays_below_2(self):
        # caldav 2.x depends on niquests, which brings urllib3-future, whose
        # .pth replaces the real urllib3 and whose QUIC pool leaked the
        # sockets that filled the descriptor table.
        requirements = self.read('backend', 'requirements.txt')
        self.assertIn('caldav>=1.3,<2', requirements)

    def test_neither_service_reads_user_site_packages(self):
        # ~/.local wins over the virtualenv, so without this a stray
        # "pip install --user" anywhere on the Pi can swap a dependency out.
        for unit in ('dashboard-backend.service.in', 'dashboard-hardware.service.in'):
            with self.subTest(unit=unit):
                self.assertIn('Environment=PYTHONNOUSERSITE=1',
                              self.read('config', unit))

    def test_backend_has_descriptor_headroom(self):
        self.assertIn('LimitNOFILE=', self.read('config', 'dashboard-backend.service.in'))


if __name__ == '__main__':
    unittest.main()
