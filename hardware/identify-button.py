#!/usr/bin/env python3
"""
Work out which GPIO pin the wall's button is actually wired to, and save it.

The documentation says GPIO 17, but this Pi ran MagicMirror for months with
its button on GPIO 26, and the wiring predates FamilyDash ever being
deployed here. Rather than guess - and rather than listen on both pins,
which invites a floating input to advance the screen on electrical noise -
ask the button itself.

Run it, press the button once, and it writes BUTTON_PIN into config.env and
restarts the hardware service:

    sudo systemctl stop dashboard-hardware
    .venv/bin/python hardware/identify-button.py

Candidate pins can be given as arguments if the button is on neither of the
usual two:

    .venv/bin/python hardware/identify-button.py 17 26 23 24
"""

import os
import re
import subprocess
import sys
import time

import RPi.GPIO as GPIO

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(PROJECT_ROOT, 'config.env')

# 17 is what the wiring guide specifies; 26 is what this Pi's MagicMirror
# button script used, which is the only configuration known to have driven
# this hardware.
DEFAULT_CANDIDATES = [17, 26]

POLL_SECONDS = 0.01
SETTLE_SECONDS = 1.0        # every pin must rest HIGH for this long first
PRESS_SECONDS = 0.03        # how long LOW has to hold to count as a press
TIMEOUT_SECONDS = 60


def read_all(pins):
    return {pin: GPIO.input(pin) for pin in pins}


def settle(pins):
    """
    Wait for every candidate to sit HIGH, and drop any that will not.

    A pin with a button and a pull-up rests HIGH. One that rests LOW is
    either held down or wired to something else entirely, and watching it
    would report a press that never happened.
    """
    deadline = time.time() + SETTLE_SECONDS
    while time.time() < deadline:
        for pin, value in read_all(pins).items():
            if value == GPIO.LOW:
                print(f"  GPIO {pin} is LOW at rest - ignoring it")
                pins = [p for p in pins if p != pin]
        time.sleep(POLL_SECONDS)
    return pins


def wait_for_press(pins):
    """Return the first pin that goes LOW and stays LOW, or None on timeout."""
    deadline = time.time() + TIMEOUT_SECONDS
    while time.time() < deadline:
        for pin, value in read_all(pins).items():
            if value != GPIO.LOW:
                continue
            # Confirm it is a press and not a spike on a floating input.
            held = time.time() + PRESS_SECONDS
            while time.time() < held:
                if GPIO.input(pin) != GPIO.LOW:
                    break
                time.sleep(POLL_SECONDS)
            else:
                return pin
        time.sleep(POLL_SECONDS)
    return None


def save_pin(pin):
    """Set BUTTON_PIN in config.env, adding the line if it is not there."""
    with open(CONFIG, encoding='utf-8') as handle:
        text = handle.read()

    line = f'BUTTON_PIN={pin}'
    if re.search(r'^\s*BUTTON_PIN\s*=.*$', text, re.M):
        text = re.sub(r'^\s*BUTTON_PIN\s*=.*$', line, text, count=1, flags=re.M)
    else:
        text = text.rstrip('\n') + '\n' + line + '\n'

    with open(CONFIG, 'w', encoding='utf-8') as handle:
        handle.write(text)


def main():
    pins = [int(a) for a in sys.argv[1:]] or list(DEFAULT_CANDIDATES)

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in pins:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    try:
        print(f"Watching GPIO {', '.join(str(p) for p in pins)} ...")
        pins = settle(pins)
        if not pins:
            print("No candidate pin rests HIGH. Check the wiring, or pass the "
                  "pin numbers as arguments.")
            return 1

        print(f"Ready. Press the wall button once (waiting {TIMEOUT_SECONDS}s).")
        found = wait_for_press(pins)
        if found is None:
            print("No press detected. If the button really was pressed, it is "
                  "on none of these pins - pass more to try.")
            return 1

        print(f"\nThe button is on GPIO {found}.")
        save_pin(found)
        print(f"Wrote BUTTON_PIN={found} to config.env")
    finally:
        GPIO.cleanup()

    subprocess.run(['sudo', 'systemctl', 'restart', 'dashboard-hardware'],
                   check=False)
    print("Restarted dashboard-hardware. Press the button again - the wall "
          "should advance a screen.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
