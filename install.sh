#!/bin/bash
# Family Dashboard Installation Script for Raspberry Pi
#
# Nothing about the account name or the checkout location is hardcoded: both
# are discovered at run time, because Raspberry Pi OS stopped creating a
# default `pi` user in 2022 and the dashboard can live anywhere.
#
# Safe to re-run. Every step either skips work that is already done or redoes
# it harmlessly, so this doubles as a repair tool after moving the checkout.

set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="$(id -un)"
RUN_GROUP="$(id -gn)"
VENV="$APP_DIR/.venv"
PYTHON="$VENV/bin/python"

echo "======================================"
echo "Family Dashboard Installation"
echo "======================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

TOTAL=11

# Running this as root would put the virtualenv, the kiosk autostart entry and
# the config files in /root instead of the account that runs the dashboard.
if [ "$(id -u)" -eq 0 ]; then
    echo -e "${RED}Do not run this with sudo.${NC}"
    echo "Run it as the account the dashboard should run as; it will ask for sudo"
    echo "only for the steps that need it."
    exit 1
fi

echo "Installing as user : $RUN_USER"
echo "Dashboard location : $APP_DIR"
echo ""

IS_PI=false
if [ -f /proc/device-tree/model ]; then
    IS_PI=true
    echo "Detected: $(tr -d '\0' < /proc/device-tree/model)"
else
    echo -e "${RED}Warning: This doesn't appear to be a Raspberry Pi${NC}"
    echo "The backend will work, but the GPIO button and motion sensor won't."
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
echo ""

# ---------------------------------------------------------------------------
echo -e "${GREEN}[1/$TOTAL] Updating package lists...${NC}"
# Only `update`, not `upgrade`: re-running the installer shouldn't drag in an
# OS upgrade that can take half an hour. Run `sudo apt full-upgrade` yourself.
sudo apt-get update

# ---------------------------------------------------------------------------
echo -e "${GREEN}[2/$TOTAL] Installing system packages...${NC}"
# Bookworm renamed chromium-browser to chromium; pick whichever this release has.
CHROMIUM_PKG=chromium-browser
if ! apt-cache show chromium-browser > /dev/null 2>&1; then
    CHROMIUM_PKG=chromium
fi
echo "Using Chromium package: $CHROMIUM_PKG"

# fonts-noto-color-emoji matters more than it sounds: the dashboard labels
# weather, wind and sun times with emoji, and without an emoji font every one
# of them renders as an empty tofu box on the wall.
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    curl \
    git \
    fonts-noto-color-emoji \
    "$CHROMIUM_PKG"

# Optional helpers. None is fatal if unavailable, and the code checks for
# each before using it:
#   unclutter  - hides the idle cursor, X11 only
#   wlr-randr  - switches the monitor off on Wayland, where vcgencmd no longer
#                does under the KMS driver
#   wlopm      - same job, simpler interface; not on every image
sudo apt-get install -y unclutter 2>/dev/null \
    || echo -e "${YELLOW}  (unclutter unavailable - fine on Wayland)${NC}"
sudo apt-get install -y wlr-randr 2>/dev/null \
    || echo -e "${YELLOW}  (wlr-randr unavailable - fine on X11)${NC}"
sudo apt-get install -y wlopm 2>/dev/null || true
# GPIO deliberately comes from pip (rpi-lgpio), not apt. The apt package is
# RPi.GPIO, whose edge detection needs the sysfs GPIO interface the kernel
# removed in 6.6 - so on Trixie the button raises "Failed to add edge
# detection". rpi-lgpio offers the same API over /dev/gpiochip.

# ---------------------------------------------------------------------------
echo -e "${GREEN}[3/$TOTAL] Creating the Python virtualenv...${NC}"
# A venv keeps pip out of the system Python (which Debian forbids writing to
# since PEP 668), and --system-site-packages keeps apt's python3-rpi.gpio
# importable from inside it. That combination is why no --break-system-packages
# flag is needed anywhere.
if [ ! -d "$VENV" ]; then
    python3 -m venv --system-site-packages "$VENV"
    echo "Created $VENV"
else
    echo "Reusing existing $VENV"
fi
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install -r "$APP_DIR/backend/requirements.txt"

# Pinning caldav below 2 in requirements.txt stops a fresh install pulling the
# niquests/urllib3-future/qh3 stack in, but pip never removes what an earlier
# install already put there, and urllib3-future's .pth deletes the real urllib3
# package on every interpreter start for as long as it stays. So an upgrade has
# to take it out by hand, then put urllib3 back.
if "$VENV/bin/pip" show urllib3-future >/dev/null 2>&1; then
    echo "Removing the HTTP/3 stack left by an older caldav..."
    "$VENV/bin/pip" uninstall --quiet --yes niquests urllib3-future qh3 jh2 wassima || true
    "$VENV/bin/pip" install --quiet --force-reinstall "urllib3>=2,<3"
fi

# ---------------------------------------------------------------------------
echo -e "${GREEN}[4/$TOTAL] Initializing database...${NC}"
# init_db() also adds columns and seeds settings introduced since an older
# install, so it is correct to run on a re-install as well as a fresh one.
cd "$APP_DIR/backend"
"$PYTHON" -c "from app import init_db; init_db()"
cd "$APP_DIR"

# ---------------------------------------------------------------------------
echo -e "${GREEN}[5/$TOTAL] Setting up configuration...${NC}"
if [ ! -f "$APP_DIR/config/calendars.json" ]; then
    # Deliberately empty, not a copy of calendars.example.json. Seeding the
    # example gave a new install three calendars whose URLs still read YOUR_ID:
    # the wall then reported them as failing and the app's Calendars tab opened
    # on three broken entries nobody had created. An empty list lets the tab
    # show its "add your first feed" state instead. The example file stays as
    # documentation for anyone who would rather write the JSON by hand.
    echo '{"calendars": []}' > "$APP_DIR/config/calendars.json"
    echo "Created an empty config/calendars.json - add feeds from the app's Calendars tab"
else
    echo "config/calendars.json already exists - left alone"
fi

# Photo uploads for the Display tab live on disk, outside the database.
mkdir -p "$APP_DIR/backend/photos"

chmod +x "$APP_DIR/config/kiosk.sh"
chmod +x "$APP_DIR/config/install-services.sh"
chmod +x "$APP_DIR/hardware/controller.py"
chmod +x "$APP_DIR/backend/app.py"

# ---------------------------------------------------------------------------
echo -e "${GREEN}[6/$TOTAL] Installing systemd services...${NC}"
APP_DIR="$APP_DIR" RUN_USER="$RUN_USER" PYTHON="$PYTHON" \
    "$APP_DIR/config/install-services.sh"

sudo systemctl enable dashboard-backend.service
if [ "$IS_PI" = true ]; then
    sudo systemctl enable dashboard-hardware.service
else
    # Without GPIO the controller crashes on import and systemd would restart
    # it every 10 seconds forever, filling the journal.
    echo -e "${YELLOW}  Not a Pi - leaving dashboard-hardware disabled${NC}"
fi

# ---------------------------------------------------------------------------
echo -e "${GREEN}[7/$TOTAL] Configuring kiosk mode...${NC}"
# An XDG autostart entry rather than the old LXSession autostart file:
# Bookworm replaced LXSession with Wayland (wayfire, then labwc), so
# ~/.config/lxsession/LXDE-pi/autostart is simply never read there. Pi OS runs
# XDG autostart under all three session types, so this one file covers them.
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/familydash-kiosk.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Family Dashboard Kiosk
Comment=Show the family dashboard full-screen on this monitor
Exec=$APP_DIR/config/kiosk.sh
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
echo "Wrote $HOME/.config/autostart/familydash-kiosk.desktop"

# A leftover entry from an older install would launch a second Chromium.
LEGACY_AUTOSTART="$HOME/.config/lxsession/LXDE-pi/autostart"
if [ -f "$LEGACY_AUTOSTART" ] && grep -q "kiosk.sh" "$LEGACY_AUTOSTART"; then
    echo -e "${YELLOW}Note: $LEGACY_AUTOSTART also launches kiosk.sh.${NC}"
    echo -e "${YELLOW}      Remove that line or you'll get two browser windows.${NC}"
fi

# ---------------------------------------------------------------------------
echo -e "${GREEN}[8/$TOTAL] Disabling screen blanking...${NC}"
if [ -f /etc/lightdm/lightdm.conf ]; then
    sudo sed -i 's/#xserver-command=X/xserver-command=X -s 0 -dpms/' /etc/lightdm/lightdm.conf || true
    echo "Patched /etc/lightdm/lightdm.conf"
else
    # Bookworm boots to labwc/wayfire without LightDM. Blanking is a compositor
    # setting there, and kiosk.sh no longer relies on xset having worked.
    echo "No LightDM on this release - blanking is handled by the compositor."
    echo "If the screen still sleeps: Preferences > Screen Configuration, or"
    echo "set [idle] dpms_timeout = 0 in ~/.config/wayfire.ini"
fi

# ---------------------------------------------------------------------------
echo -e "${GREEN}[9/$TOTAL] Setting up log rotation...${NC}"
sudo tee /etc/logrotate.d/dashboard << EOF > /dev/null
/var/log/dashboard/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}
EOF
sudo mkdir -p /var/log/dashboard
sudo chown "$RUN_USER:$RUN_GROUP" /var/log/dashboard

# ---------------------------------------------------------------------------
echo -e "${GREEN}[10/$TOTAL] Checking GPIO permissions...${NC}"
if [ "$IS_PI" = true ] && getent group gpio > /dev/null; then
    if id -nG "$RUN_USER" | tr ' ' '\n' | grep -qx gpio; then
        echo "$RUN_USER is already in the gpio group"
    else
        sudo adduser "$RUN_USER" gpio
        echo -e "${YELLOW}Added $RUN_USER to the gpio group - reboot for it to take effect${NC}"
    fi
else
    echo "Skipped (no gpio group on this system)"
fi

# ---------------------------------------------------------------------------
echo -e "${GREEN}[11/$TOTAL] Starting services...${NC}"
sudo systemctl restart dashboard-backend.service || true
if [ "$IS_PI" = true ]; then
    sudo systemctl restart dashboard-hardware.service || true
fi

sleep 3
echo ""
echo -e "${YELLOW}Checking service status...${NC}"
BACKEND_STATUS=$(systemctl is-active dashboard-backend || echo "failed")
if [ "$BACKEND_STATUS" = "active" ]; then
    echo -e "${GREEN}  Backend service is running${NC}"
else
    echo -e "${RED}  Backend service failed to start${NC}"
    echo "  Check logs: sudo journalctl -u dashboard-backend -n 50"
fi
if [ "$IS_PI" = true ]; then
    HARDWARE_STATUS=$(systemctl is-active dashboard-hardware || echo "failed")
    if [ "$HARDWARE_STATUS" = "active" ]; then
        echo -e "${GREEN}  Hardware service is running${NC}"
    else
        echo -e "${RED}  Hardware service failed to start${NC}"
        echo "  Check logs: sudo journalctl -u dashboard-hardware -n 50"
    fi
fi

# Read the port the backend actually uses rather than assuming 5000.
PORT=$(sed -n 's/^[[:space:]]*API_PORT[[:space:]]*=[[:space:]]*\([0-9][0-9]*\).*/\1/p' \
    "$APP_DIR/config.env" 2>/dev/null | tail -1)
PORT="${PORT:-5000}"
LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}')

echo ""
echo -e "${GREEN}======================================"
echo "Installation Complete!"
echo "======================================${NC}"
echo ""
echo "The dashboard will start automatically on boot."
echo ""
echo "Access points:"
echo "  - Main Dashboard:   http://localhost:$PORT"
echo "  - Mobile Interface: http://localhost:$PORT/mobile"
echo "  - API:              http://localhost:$PORT/api"
if [ -n "$LAN_IP" ]; then
    echo ""
    echo "From another device on your network (and for the iPhone app):"
    echo "  - http://$LAN_IP:$PORT"
fi
echo ""
echo "Hardware Setup:"
echo "  - Button: GPIO 17 (Physical Pin 11)"
echo "  - Motion Sensor: GPIO 27 (Physical Pin 13)"
echo "  - Connect button between GPIO 17 and Ground"
echo "  - Connect PIR sensor VCC to 5V, GND to Ground, OUT to GPIO 27"
echo ""
echo "Next steps:"
echo "  1. Open the mobile interface and add your calendars on the Calendars tab."
echo "     Nothing to restart - saving a calendar re-syncs straight away."
echo "     (config/calendars.json still works if you prefer editing it by hand.)"
echo "  2. Access the mobile interface to add recipes"
echo "  3. Plan your meals for the week"
echo "  4. Generate your grocery list"
echo "  5. Reboot to test the kiosk auto-start: sudo reboot"
echo ""
echo "Logs:"
echo "  - Backend: sudo journalctl -u dashboard-backend -f"
echo "  - Hardware: sudo journalctl -u dashboard-hardware -f"
echo ""
