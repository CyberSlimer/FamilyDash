#!/bin/bash
# Kiosk Mode Auto-Start Script
# This script launches Chromium in kiosk mode on boot

# Wait for X server to start
sleep 10

# Disable screen blanking
xset s off
xset -dpms
xset s noblank

# Hide mouse cursor after 5 seconds of inactivity
unclutter -idle 5 &

# Launch Chromium in kiosk mode
chromium-browser \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-restore-session-state \
    --no-first-run \
    --disable-suggestions-service \
    --disable-translate \
    --disable-save-password-bubble \
    --disable-sync \
    --start-fullscreen \
    http://localhost:5000
