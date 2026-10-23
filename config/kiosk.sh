#!/bin/bash
# Kiosk Mode Auto-Start Script
# Launches the dashboard full-screen on the Pi's own monitor.
#
# Works under both session types Raspberry Pi OS has shipped: X11/LXDE on
# Bullseye and earlier, and Wayland (wayfire, then labwc) from Bookworm
# onwards. Everything X11-only is guarded rather than assumed, because under
# Wayland those binaries are either absent or unable to reach the compositor.

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Started from an XDG autostart entry, this script has nowhere to print: the
# session swallows stdout, so a failed boot leaves no trace anywhere. Keep a
# log of our own.
KIOSK_LOG="${XDG_RUNTIME_DIR:-/tmp}/familydash-kiosk.log"
exec >> "$KIOSK_LOG" 2>&1
echo "=== kiosk starting $(date '+%Y-%m-%d %H:%M:%S') ==="

# Follow API_PORT from config.env like the rest of the system, instead of
# hardcoding 5000 in a second place.
PORT=5000
if [ -f "$APP_DIR/config.env" ]; then
    configured=$(sed -n 's/^[[:space:]]*API_PORT[[:space:]]*=[[:space:]]*\([0-9][0-9]*\).*/\1/p' \
        "$APP_DIR/config.env" | tail -1)
    [ -n "$configured" ] && PORT="$configured"
fi
URL="http://localhost:$PORT"

# Wait for the desktop session before anything else. Under an XDG autostart
# entry this script can run while labwc is still assembling the session, and
# a Chromium that connects that early gets a surface it never paints: a plain
# white screen, with nothing in any log to say why. The original script's
# blanket `sleep 10` covered this by accident; polling for actual readiness
# keeps a warm start fast and still waits as long as a cold boot needs.
wait_for_display() {
    local runtime="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    local i
    for i in $(seq 1 60); do
        if [ -n "$WAYLAND_DISPLAY" ] && [ -S "$runtime/$WAYLAND_DISPLAY" ]; then
            # The socket appears before any output is configured, so ask
            # whether something is actually lit before handing over.
            if command -v wlr-randr > /dev/null 2>&1; then
                wlr-randr 2>/dev/null | grep -q 'Enabled: yes' && return 0
            else
                return 0
            fi
        elif [ -n "$DISPLAY" ] && xset q > /dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    return 1
}

if wait_for_display; then
    echo "display ready"
else
    echo "display not ready after 60s - launching anyway"
fi

# An output being live is not the same as the session being settled: labwc is
# still bringing up the panel and desktop behind us.
sleep 5

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
    # Without this Chromium looks for a system keyring to encrypt its cookie
    # store in, finds none on a freshly imaged Pi, and puts up a modal
    # "Choose password for new keyring" dialog that blocks the page from ever
    # rendering - a white screen with no error anywhere in the logs.
    --password-store=basic
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
