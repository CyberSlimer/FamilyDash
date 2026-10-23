#!/bin/bash
# Kiosk Mode Auto-Start Script
# Launches the dashboard full-screen on the Pi's own monitor.
#
# Works under both session types Raspberry Pi OS has shipped: X11/LXDE on
# Bullseye and earlier, and Wayland (wayfire, then labwc) from Bookworm
# onwards. Everything X11-only is guarded rather than assumed, because under
# Wayland those binaries are either absent or unable to reach the compositor.

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Follow API_PORT from config.env like the rest of the system, instead of
# hardcoding 5000 in a second place.
PORT=5000
if [ -f "$APP_DIR/config.env" ]; then
    configured=$(sed -n 's/^[[:space:]]*API_PORT[[:space:]]*=[[:space:]]*\([0-9][0-9]*\).*/\1/p' \
        "$APP_DIR/config.env" | tail -1)
    [ -n "$configured" ] && PORT="$configured"
fi
URL="http://localhost:$PORT"

# Wait for the backend to answer rather than sleeping a fixed 10 seconds.
# /api/health is the same endpoint the phone app uses to verify a server, so
# it's the real readiness signal - and on a cold boot the Pi often needs far
# longer than 10s, which used to show a connection error on the wall.
for _ in $(seq 1 60); do
    if curl -fsS --max-time 2 "$URL/api/health" > /dev/null 2>&1; then
        break
    fi
    sleep 2
done

if [ -n "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    # X11: stop screen blanking and hide the idle cursor. Under Wayland the
    # compositor owns both, and labwc/wayfire are configured not to blank.
    if command -v xset > /dev/null; then
        xset s off
        xset -dpms
        xset s noblank
    fi
    if command -v unclutter > /dev/null; then
        unclutter -idle 5 &
    fi
fi

# Bookworm renamed the Chromium package, so accept either name.
BROWSER=""
for candidate in chromium-browser chromium; do
    if command -v "$candidate" > /dev/null; then
        BROWSER="$candidate"
        break
    fi
done
if [ -z "$BROWSER" ]; then
    echo "kiosk: no Chromium found (tried chromium-browser and chromium)" >&2
    exit 1
fi

FLAGS=(
    --kiosk
    --noerrdialogs
    --disable-infobars
    --disable-session-crashed-bubble
    --disable-restore-session-state
    --no-first-run
    --disable-suggestions-service
    --disable-translate
    --disable-save-password-bubble
    --disable-sync
    --start-fullscreen
)

# Render through the compositor directly when there is one; otherwise Chromium
# can land on XWayland and look soft on a high-resolution panel.
if [ -n "$WAYLAND_DISPLAY" ]; then
    FLAGS+=(--ozone-platform=wayland)
fi

exec "$BROWSER" "${FLAGS[@]}" "$URL"
