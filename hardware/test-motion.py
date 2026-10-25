#!/usr/bin/env python3
"""
Watch the PIR pin and report what it is actually doing.

Run this on the Pi while someone walks in front of the sensor:

    python3 hardware/test-motion.py

It only reads the pin, so it is safe to run while dashboard-hardware is
going; neither process disturbs the other. Stop with Ctrl+C for a summary.

The pin is pulled down, which is the whole trick: an input with nothing
attached floats, and a floating pin reads HIGH about as often as not. With a
pull-down fitted, "nothing connected" reads LOW - an empty room - so a HIGH
means something really did drive the pin.
"""

import os
import sys
import time
from datetime import datetime

try:
    import RPi.GPIO as GPIO
except ImportError:
    sys.exit("This has to run on the Pi (RPi.GPIO is not installed here).")

try:
    from dotenv import load_dotenv
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(PROJECT_ROOT, 'config.env'))
except ImportError:
    pass

RAW_PIN = (os.environ.get('MOTION_PIN') or '27').strip()
if RAW_PIN.lower() in ('off', 'none', 'no', ''):
    sys.exit("MOTION_PIN is off in config.env, so there is no pin to watch.")
PIN = int(RAW_PIN)

# An HC-SR501 holds its output high for a minute or so after power-on while
# the charge pump settles. Readings before that mean nothing.
WARMUP = 60


def level(pin):
    return 'HIGH' if GPIO.input(pin) else 'LOW '


def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    started = time.time()
    print(f"Watching GPIO {PIN} (physical pin 13 for GPIO 27). Ctrl+C to stop.")
    print(f"Ignore the first {WARMUP}s - the sensor is still settling.")
    print("Expected with nothing wired: LOW, forever. If an unconnected pin")
    print("reads HIGH, the pull-down above is not taking effect.\n")

    last = GPIO.input(PIN)
    highs = 0
    samples = 0
    changes = 0
    print(f"{datetime.now():%H:%M:%S}  start   {level(PIN)}")

    try:
        while True:
            value = GPIO.input(PIN)
            samples += 1
            highs += 1 if value else 0
            if value != last:
                changes += 1
                age = time.time() - started
                note = '  (still warming up - ignore)' if age < WARMUP else ''
                print(f"{datetime.now():%H:%M:%S}  ->      "
                      f"{'HIGH  MOTION' if value else 'LOW   quiet '}{note}")
                last = value
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup(PIN)

    seconds = time.time() - started
    print(f"\nWatched for {seconds:.0f}s: {changes} change(s), "
          f"high for {100.0 * highs / max(samples, 1):.0f}% of samples.")
    if changes == 0 and highs == 0:
        print("Never went high. Either nothing is wired to this pin, OUT is on")
        print("the wrong pin, or the sensor has no power - check VCC on pin 2.")
    elif changes == 0 and highs == samples:
        print("Stuck high. That is usually OUT wired to 3.3V/5V instead of to")
        print("the GPIO, or the delay pot turned right up. Try the delay pot")
        print("fully anti-clockwise and watch again.")
    else:
        print("That is a working sensor.")


if __name__ == '__main__':
    main()
