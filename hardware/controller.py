#!/usr/bin/env python3
"""
Hardware Controller for Family Dashboard
Handles: Physical button, PIR motion sensor, keyboard input
"""

import RPi.GPIO as GPIO
import time
import requests
from datetime import datetime, timedelta
import subprocess
import os

# ============================================================================
# CONFIGURATION
# ============================================================================

# GPIO Pin Configuration
BUTTON_PIN = 17  # Physical button to advance screens
MOTION_PIN = 27  # PIR motion sensor

# Dashboard URL
DASHBOARD_URL = "http://localhost:5000"

# Motion sensor settings
MOTION_TIMEOUT = 300  # 5 minutes - turn off display after no motion
CHECK_INTERVAL = 1  # Check sensors every second

# Display control
DISPLAY_ON = True
LAST_MOTION = datetime.now()

# ============================================================================
# GPIO SETUP
# ============================================================================

def setup_gpio():
    """Initialize GPIO pins"""
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    
    # Button with pull-up resistor (button connects to ground)
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    # PIR motion sensor
    GPIO.setup(MOTION_PIN, GPIO.IN)
    
    print("GPIO initialized")
    print(f"Button: GPIO {BUTTON_PIN}")
    print(f"Motion: GPIO {MOTION_PIN}")

# ============================================================================
# DISPLAY CONTROL
# ============================================================================

def turn_display_on():
    """Turn on HDMI display"""
    global DISPLAY_ON
    if not DISPLAY_ON:
        subprocess.run(['vcgencmd', 'display_power', '1'], check=False)
        DISPLAY_ON = True
        print("Display ON")

def turn_display_off():
    """Turn off HDMI display to save power"""
    global DISPLAY_ON
    if DISPLAY_ON:
        subprocess.run(['vcgencmd', 'display_power', '0'], check=False)
        DISPLAY_ON = False
        print("Display OFF")

# ============================================================================
# SCREEN CONTROL
# ============================================================================

def send_keypress(key):
    """Send keypress to browser using xdotool"""
    try:
        # Get the window ID of Chromium
        result = subprocess.run(
            ['xdotool', 'search', '--name', 'Chromium'],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.stdout.strip():
            window_id = result.stdout.strip().split('\n')[0]
            
            # Activate window and send key
            subprocess.run(['xdotool', 'windowactivate', window_id], check=False)
            subprocess.run(['xdotool', 'key', key], check=False)
            print(f"Sent keypress: {key}")
        else:
            print("Chromium window not found")
            
    except Exception as e:
        print(f"Error sending keypress: {e}")

def next_screen():
    """Advance to next screen"""
    send_keypress('Right')

def previous_screen():
    """Go to previous screen"""
    send_keypress('Left')

def refresh_screen():
    """Refresh current screen data"""
    send_keypress('r')

# ============================================================================
# BUTTON HANDLER
# ============================================================================

def button_callback(channel):
    """Handle button press"""
    global LAST_MOTION
    
    # Debounce
    time.sleep(0.2)
    if GPIO.input(BUTTON_PIN) == GPIO.LOW:  # Still pressed
        print("Button pressed!")
        LAST_MOTION = datetime.now()
        turn_display_on()
        next_screen()

# ============================================================================
# MOTION SENSOR HANDLER
# ============================================================================

def check_motion():
    """Check motion sensor and control display"""
    global LAST_MOTION, DISPLAY_ON
    
    if GPIO.input(MOTION_PIN):
        # Motion detected
        if not DISPLAY_ON:
            print("Motion detected - waking display")
            turn_display_on()
        LAST_MOTION = datetime.now()
    else:
        # No motion
        if DISPLAY_ON:
            idle_time = (datetime.now() - LAST_MOTION).seconds
            if idle_time > MOTION_TIMEOUT:
                print(f"No motion for {idle_time}s - turning off display")
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
    GPIO.add_event_detect(
        BUTTON_PIN,
        GPIO.FALLING,
        callback=button_callback,
        bouncetime=300
    )
    
    print("Ready!")
    print("- Press button to advance screens")
    print("- Motion sensor will wake display")
    print("- Press Ctrl+C to exit")
    print()
    
    try:
        while True:
            # Check motion sensor
            check_motion()
            
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
