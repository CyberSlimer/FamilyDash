#!/usr/bin/env python3
"""
Hardware Controller for Family Dashboard
Handles: Physical button, PIR motion sensor, keyboard input
"""

import RPi.GPIO as GPIO
import shutil
import time
import requests
from collections import deque
from datetime import datetime, timedelta
import subprocess
import os

from dotenv import load_dotenv

# ============================================================================
# CONFIGURATION
# ============================================================================

# config.env advertises these as settings, so actually read them. Under
# systemd this process starts with no session environment at all, so the file
# has to be loaded explicitly rather than inherited from a login shell.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, 'config.env'))

# GPIO Pin Configuration


def parse_pin(value, default):
    """Read a BCM pin number, treating anything off-like as "no such device".

    Missing hardware is a normal state for this wall rather than an error: the
    screens rotate on a timer of their own and the phone can drive them
    directly, so a button that was never wired - or one that has broken - only
    needs to be left out. `BUTTON_PIN=off` does that without disturbing the
    motion sensor, and the same goes the other way round.
    """
    text = str(value if value is not None else default).strip().lower()
    if text in ('', '0', '-', 'off', 'no', 'none', 'false', 'disabled'):
        return None
    try:
        return int(text)
    except ValueError:
        print(f"Could not read a pin number from {value!r}; treating it as off")
        return None


BUTTON_PIN = parse_pin(os.environ.get("BUTTON_PIN"), 17)  # advances screens
MOTION_PIN = parse_pin(os.environ.get("MOTION_PIN"), 27)  # PIR motion sensor

# Set once the button has proved it rests high; cleared again if it starts
# chattering. Nothing reads the button while this is False.
BUTTON_READY = False

# A switch that has failed closed, or whose contacts are breaking up, fires
# the edge callback over and over. Past this many presses in this window we
# stop believing it: a wall that flips screens by itself is worse than a wall
# whose button does nothing.
PRESS_TIMES = deque()
STORM_PRESSES = 8
STORM_WINDOW = 10.0

# Dashboard URL
DASHBOARD_URL = "http://localhost:{}".format(os.environ.get("API_PORT", "5000"))

# Motion sensor settings
MOTION_TIMEOUT = int(os.environ.get("MOTION_TIMEOUT", 300))  # display off after no motion
CHECK_INTERVAL = 1  # Check sensors every second
CONFIG_POLL_SECONDS = 30  # how often to re-read the display config

# Display control
DISPLAY_ON = True
LAST_MOTION = datetime.now()

# Mirrors the screensaver block of /api/display. When the screensaver is on we
# leave the monitor powered and let the browser show photos instead of cutting
# the backlight, so the idle display is a photo frame rather than a black rectangle.
SCREENSAVER = {"enabled": False, "idle_seconds": MOTION_TIMEOUT}
LAST_CONFIG_FETCH = None


def refresh_config():
    """Pull display settings from the backend; keep the last ones on failure."""
    global SCREENSAVER, LAST_CONFIG_FETCH
    LAST_CONFIG_FETCH = datetime.now()
    try:
        res = requests.get(f"{DASHBOARD_URL}/api/display", timeout=5)
        res.raise_for_status()
        config = res.json().get("config") or {}
        saver = config.get("screensaver") or {}
        SCREENSAVER = {
            "enabled": bool(saver.get("enabled")),
            "idle_seconds": int(saver.get("idle_seconds", MOTION_TIMEOUT)),
        }
        print(f"Display config: screensaver={'on' if SCREENSAVER['enabled'] else 'off'}"
              f" idle={SCREENSAVER['idle_seconds']}s")
    except Exception as e:
        print(f"Could not read display config ({e}); keeping current settings")

# ============================================================================
# GPIO SETUP
# ============================================================================

def button_rests_high():
    """Sample the button pin over half a second; True if it is idle throughout.

    The internal pull-up holds an untouched button HIGH. A pin already sitting
    LOW means the switch is shorted, wired to ground, or broken closed - and
    attaching a FALLING-edge callback to it would hand the screens to a fault.
    Half a second of samples also catches contacts that are breaking up, which
    a single read would sail straight past.
    """
    low = 0
    for _ in range(10):
        if GPIO.input(BUTTON_PIN) == GPIO.LOW:
            low += 1
        time.sleep(0.05)
    if low:
        print(f"Button: GPIO {BUTTON_PIN} is not resting high ({low} of 10 samples "
              "low), so it is being ignored - a stuck or chattering switch would "
              "advance the screens by itself. Set BUTTON_PIN=off in config.env to "
              "stop looking for it.")
        return False
    return True


def setup_gpio():
    """Initialize GPIO pins"""
    global BUTTON_READY

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    print("GPIO initialized")

    # Button with pull-up resistor (button connects to ground)
    if BUTTON_PIN is None:
        print("Button: off - the screens rotate on their own and the phone can "
              "drive them from the Display tab")
    else:
        GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        BUTTON_READY = button_rests_high()
        if BUTTON_READY:
            print(f"Button: GPIO {BUTTON_PIN}")

    # PIR motion sensor
    if MOTION_PIN is None:
        print("Motion: off - the display stays on and the screensaver runs on its "
              "own idle timer")
    else:
        GPIO.setup(MOTION_PIN, GPIO.IN)
        print(f"Motion: GPIO {MOTION_PIN}")

# ============================================================================
# DISPLAY CONTROL
# ============================================================================

def session_env():
    """Environment that lets a tool reach the user's Wayland compositor.

    This runs as a systemd service, so it starts with no session variables.
    wlr-randr and wlopm both need XDG_RUNTIME_DIR and WAYLAND_DISPLAY to find
    the compositor socket; the socket name is discovered rather than assumed,
    because it is wayland-0 on some images and wayland-1 on others.
    """
    env = dict(os.environ)
    runtime = env.get('XDG_RUNTIME_DIR') or '/run/user/{}'.format(os.getuid())
    env['XDG_RUNTIME_DIR'] = runtime
    if not env.get('WAYLAND_DISPLAY'):
        try:
            sockets = sorted(name for name in os.listdir(runtime)
                             if name.startswith('wayland-') and not name.endswith('.lock'))
        except OSError:
            sockets = []
        if sockets:
            env['WAYLAND_DISPLAY'] = sockets[0]
    return env


_WLR_OUTPUT = None


def wlr_output(env):
    """Name of the first connected output, e.g. HDMI-A-1. Cached."""
    global _WLR_OUTPUT
    if _WLR_OUTPUT is None:
        _WLR_OUTPUT = ''
        try:
            result = subprocess.run(['wlr-randr'], env=env, capture_output=True,
                                    text=True, timeout=10)
            for line in result.stdout.splitlines():
                # Output blocks start in column zero; their properties are indented.
                if line.strip() and not line[0].isspace():
                    _WLR_OUTPUT = line.split()[0]
                    break
        except Exception:
            pass
    return _WLR_OUTPUT


def set_display_power(on):
    """Switch the monitor on or off by whatever means this Pi actually has.

    `vcgencmd display_power` is no longer enough on its own: with the KMS
    driver that became the default in Bookworm it does not control an HDMI
    output any more. Try the compositor's own tools first, then fall back
    through the older mechanisms, and report which one worked.
    """
    env = session_env()
    attempts = []

    if env.get('WAYLAND_DISPLAY'):
        # wlopm takes a glob, so it needs no output name at all.
        attempts.append(['wlopm', '--on' if on else '--off', '*'])
        output = wlr_output(env)
        if output:
            attempts.append(['wlr-randr', '--output', output, '--on' if on else '--off'])

    attempts.append(['vcgencmd', 'display_power', '1' if on else '0'])
    attempts.append(['xset', 'dpms', 'force', 'on' if on else 'off'])

    for command in attempts:
        if not shutil.which(command[0]):
            continue
        try:
            result = subprocess.run(command, env=env, capture_output=True, timeout=10)
            if result.returncode == 0:
                return command[0]
        except Exception:
            continue
    return None


def turn_display_on():
    """Turn on HDMI display"""
    global DISPLAY_ON
    if not DISPLAY_ON:
        used = set_display_power(True)
        DISPLAY_ON = True
        print("Display ON" + (" (via {})".format(used) if used else " (no mechanism worked)"))

def turn_display_off():
    """Turn off HDMI display to save power"""
    global DISPLAY_ON
    if DISPLAY_ON:
        used = set_display_power(False)
        DISPLAY_ON = False
        print("Display OFF" + (" (via {})".format(used) if used else " (no mechanism worked)"))

# ============================================================================
# SCREEN CONTROL
# ============================================================================

def send_command(action, index=None):
    """Ask the dashboard to change what it is showing.

    This posts to the backend instead of driving the browser with xdotool.
    Under Wayland - the session Raspberry Pi OS has used since Bookworm - one
    client cannot inject keystrokes into another client's window at all, so
    the old approach failed silently: the button appeared dead. The kiosk
    polls /api/display/command once a second and acts on what it finds, which
    works under X11 and Wayland alike and does not care whether the browser
    has keyboard focus.
    """
    payload = {'action': action}
    if index is not None:
        payload['index'] = index
    try:
        res = requests.post(DASHBOARD_URL + '/api/display/command',
                            json=payload, timeout=5)
        res.raise_for_status()
        print(f"Sent command: {action}")
    except Exception as e:
        print(f"Could not send command {action}: {e}")

def next_screen():
    """Advance to next screen"""
    send_command('next')

def previous_screen():
    """Go to previous screen"""
    send_command('prev')

def refresh_screen():
    """Refresh current screen data"""
    send_command('refresh')

# ============================================================================
# BUTTON HANDLER
# ============================================================================

def button_callback(channel):
    """Handle button press"""
    global LAST_MOTION, BUTTON_READY

    if not BUTTON_READY:
        return

    # Debounce
    time.sleep(0.2)
    if GPIO.input(BUTTON_PIN) != GPIO.LOW:  # released again; electrical noise
        return

    now = time.monotonic()
    PRESS_TIMES.append(now)
    while PRESS_TIMES and now - PRESS_TIMES[0] > STORM_WINDOW:
        PRESS_TIMES.popleft()
    if len(PRESS_TIMES) >= STORM_PRESSES:
        BUTTON_READY = False
        try:
            GPIO.remove_event_detect(BUTTON_PIN)
        except Exception:
            pass
        print(f"Button on GPIO {BUTTON_PIN} reported {len(PRESS_TIMES)} presses in "
              f"{STORM_WINDOW:.0f}s, which is a fault rather than a person. "
              "Ignoring it until the service restarts; the screens keep rotating "
              "and the phone can still drive them.")
        return

    print("Button pressed!")
    LAST_MOTION = datetime.now()
    turn_display_on()
    next_screen()

# ============================================================================
# MOTION SENSOR HANDLER
# ============================================================================

def wake_browser():
    """
    Nudge the page so it drops its screensaver.

    A `wake` command counts as a sign of life without changing which screen
    is showing, which is what motion should do.
    """
    send_command('wake')


def check_motion():
    """Check motion sensor and control display"""
    global LAST_MOTION, DISPLAY_ON

    if MOTION_PIN is None:
        # With no sensor, an unwired pin floats and would read as constant
        # motion, which would keep the screensaver from ever appearing. Leave
        # the display on and let the browser's own idle timer do the work.
        return

    if GPIO.input(MOTION_PIN):
        # Motion detected
        if not DISPLAY_ON:
            print("Motion detected - waking display")
            turn_display_on()
        elif SCREENSAVER["enabled"]:
            idle_time = (datetime.now() - LAST_MOTION).total_seconds()
            # Only poke the browser if it had time to fall asleep, so we're
            # not posting a wake command every second someone walks past.
            if idle_time >= SCREENSAVER["idle_seconds"]:
                print("Motion detected - waking the dashboard from the screensaver")
                wake_browser()
        LAST_MOTION = datetime.now()
    else:
        # No motion
        if DISPLAY_ON:
            idle_time = (datetime.now() - LAST_MOTION).total_seconds()
            if SCREENSAVER["enabled"]:
                # The photo screensaver is the idle state; the monitor only
                # powers down long after, to save the panel overnight.
                if idle_time > max(MOTION_TIMEOUT, SCREENSAVER["idle_seconds"]) * 4:
                    print(f"No motion for {int(idle_time)}s - turning off display")
                    turn_display_off()
            elif idle_time > MOTION_TIMEOUT:
                print(f"No motion for {int(idle_time)}s - turning off display")
                turn_display_off()

# ============================================================================
# MAIN LOOP
# ============================================================================

def main():
    """Main control loop"""
    print("Family Dashboard Hardware Controller")
    print("=" * 50)
    print("Starting...")
    
    # Setup GPIO
    setup_gpio()
    
    # Setup button interrupt
    if BUTTON_READY:
        GPIO.add_event_detect(
            BUTTON_PIN,
            GPIO.FALLING,
            callback=button_callback,
            bouncetime=300
        )

    print("Ready!")
    if BUTTON_READY:
        print("- Press button to advance screens")
    else:
        print("- No working button; advance screens from the phone's Display tab")
    if MOTION_PIN is not None:
        print("- Motion sensor will wake display")
    print("- Display settings are read from the app every "
          f"{CONFIG_POLL_SECONDS}s")
    print("- Press Ctrl+C to exit")
    print()
    
    refresh_config()

    try:
        while True:
            # Check motion sensor
            check_motion()

            # Pick up display settings changed from the app
            if (datetime.now() - LAST_CONFIG_FETCH).total_seconds() >= CONFIG_POLL_SECONDS:
                refresh_config()

            # Small delay
            time.sleep(CHECK_INTERVAL)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        GPIO.cleanup()
        print("GPIO cleaned up")

# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    main()
