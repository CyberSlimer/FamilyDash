"""
Tests for the touch-pad gesture classifier and its configuration.

The classifier lives in hardware/controller.py, which imports RPi.GPIO and
so cannot be imported off a Pi. classify_taps is pure, though, and tap
timing is exactly the sort of thing that is wrong in ways no amount of
staring at the code reveals - so it is lifted out of the source and
exercised here rather than left to be discovered on the wall.

Run from the backend/ directory:
    python -m unittest discover -s tests -v
"""

import os
import re
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as dashboard  # noqa: E402

CONTROLLER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    '..', 'hardware', 'controller.py')


def load_classifier():
    """Pull classify_taps out of the controller without importing RPi.GPIO."""
    with open(CONTROLLER, encoding='utf-8') as fh:
        source = fh.read()
    match = re.search(r'^LONG_PRESS = ([0-9.]+)$', source, re.M)
    body = re.search(r'^def classify_taps\(.*?(?=\n\ndef )', source, re.S | re.M)
    assert match and body, 'classify_taps or LONG_PRESS has moved'
    module = types.ModuleType('gesture_bits')
    module.__dict__['LONG_PRESS'] = float(match.group(1))
    exec(compile(body.group(0), 'controller.py', 'exec'), module.__dict__)
    return module


class ClassifyTapsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_classifier()
        cls.long_press = cls.mod.LONG_PRESS

    def classify(self, *holds):
        return self.mod.classify_taps(list(holds))

    def test_one_quick_tap_is_a_single(self):
        self.assertEqual(self.classify(0.08), 'single')

    def test_one_long_hold_is_a_hold(self):
        self.assertEqual(self.classify(self.long_press + 0.4), 'hold')

    def test_the_boundary_counts_as_a_hold(self):
        self.assertEqual(self.classify(self.long_press), 'hold')
        self.assertEqual(self.classify(self.long_press - 0.01), 'single')

    def test_two_taps_are_a_double(self):
        self.assertEqual(self.classify(0.07, 0.09), 'double')

    def test_a_long_hold_inside_a_double_is_still_a_double(self):
        # Holding the second tap by accident should not silently become a
        # different gesture; the count is what the person meant.
        self.assertEqual(self.classify(0.08, self.long_press + 0.5), 'double')

    def test_a_fumbled_third_tap_does_not_invent_a_gesture(self):
        self.assertEqual(self.classify(0.05, 0.05, 0.05), 'double')

    def test_nothing_at_all_is_not_a_gesture(self):
        self.assertIsNone(self.mod.classify_taps([]))


class GestureConfigTests(unittest.TestCase):
    """What the pad is bound to is stored like every other display setting."""

    def validate(self, gestures):
        return dashboard._validate_display({'button_gestures': gestures})['button_gestures']

    def test_the_defaults_are_the_three_useful_ones(self):
        bound = dashboard.DEFAULT_DISPLAY['button_gestures']
        self.assertEqual(set(bound), {'single', 'double', 'hold'})
        self.assertEqual(bound['double'], 'month')

    def test_bindings_round_trip(self):
        bound = self.validate({'single': 'prev', 'double': 'saver', 'hold': 'refresh'})
        self.assertEqual(bound, {'single': 'prev', 'double': 'saver', 'hold': 'refresh'})

    def test_none_is_a_real_choice(self):
        self.assertEqual(self.validate({'hold': 'none'})['hold'], 'none')

    def test_an_unknown_action_is_refused_rather_than_stored(self):
        # These reach the wall as commands, so an unrecognised one would be
        # a dead binding at best.
        bound = self.validate({'single': 'self-destruct'})
        self.assertEqual(bound['single'], 'next')

    def test_a_partial_payload_leaves_the_others_alone(self):
        bound = self.validate({'double': 'home'})
        self.assertEqual(bound['double'], 'home')
        self.assertEqual(bound['single'], 'next')

    def test_rubbish_instead_of_a_mapping_is_ignored(self):
        config = dashboard._validate_display({'button_gestures': 'yes please'})
        self.assertEqual(config['button_gestures'],
                         dashboard.DEFAULT_DISPLAY['button_gestures'])

    def test_every_default_binding_is_a_command_the_wall_knows(self):
        for action in dashboard.DEFAULT_DISPLAY['button_gestures'].values():
            self.assertIn(action, dashboard.DISPLAY_COMMANDS, action)


if __name__ == '__main__':
    unittest.main()
