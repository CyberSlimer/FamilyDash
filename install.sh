#!/bin/bash
# Family Dashboard Installation Script for Raspberry Pi 4
# This script sets up everything needed for the dashboard

set -e  # Exit on error

echo "======================================"
echo "Family Dashboard Installation"
echo "======================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on Raspberry Pi
if [ ! -f /proc/device-tree/model ]; then
    echo -e "${RED}Warning: This doesn't appear to be a Raspberry Pi${NC}"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update system
echo -e "${GREEN}[1/10] Updating system packages...${NC}"
sudo apt-get update
sudo apt-get upgrade -y

# Install required packages
echo -e "${GREEN}[2/10] Installing required packages...${NC}"
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    python3-rpi.gpio \
    chromium-browser \
    unclutter \
    xdotool \
    git

# Install Python packages
echo -e "${GREEN}[3/10] Installing Python dependencies...${NC}"
cd /home/pi/family-dashboard/backend
pip3 install -r requirements.txt --break-system-packages

# Create database
echo -e "${GREEN}[4/10] Initializing database...${NC}"
python3 -c "from app import init_db; init_db()"

# Calendar config
if [ ! -f /home/pi/family-dashboard/config/calendars.json ]; then
    cp /home/pi/family-dashboard/config/calendars.example.json /home/pi/family-dashboard/config/calendars.json
    echo -e "${YELLOW}Created config/calendars.json from the example - edit it with your calendar URLs${NC}"
fi

# Make scripts executable
echo -e "${GREEN}[5/10] Setting up scripts...${NC}"
chmod +x /home/pi/family-dashboard/config/kiosk.sh
chmod +x /home/pi/family-dashboard/hardware/controller.py
chmod +x /home/pi/family-dashboard/backend/app.py

# Install systemd services
echo -e "${GREEN}[6/10] Installing systemd services...${NC}"
sudo cp /home/pi/family-dashboard/config/dashboard-backend.service /etc/systemd/system/
sudo cp /home/pi/family-dashboard/config/dashboard-hardware.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dashboard-backend.service
sudo systemctl enable dashboard-hardware.service

# Setup kiosk mode auto-start
echo -e "${GREEN}[7/10] Configuring kiosk mode...${NC}"
mkdir -p /home/pi/.config/lxsession/LXDE-pi
cat > /home/pi/.config/lxsession/LXDE-pi/autostart << EOF
@lxpanel --profile LXDE-pi
@pcmanfm --desktop --profile LXDE-pi
@xscreensaver -no-splash
@/home/pi/family-dashboard/config/kiosk.sh
EOF

# Disable screen blanking
echo -e "${GREEN}[8/10] Disabling screen blanking...${NC}"
sudo sed -i 's/#xserver-command=X/xserver-command=X -s 0 -dpms/' /etc/lightdm/lightdm.conf || true

# Setup log rotation
echo -e "${GREEN}[9/10] Setting up log rotation...${NC}"
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

# Create log directory
sudo mkdir -p /var/log/dashboard
sudo chown pi:pi /var/log/dashboard

# Start services
echo -e "${GREEN}[10/10] Starting services...${NC}"
sudo systemctl start dashboard-backend.service
sudo systemctl start dashboard-hardware.service

# Check service status
echo ""
echo -e "${YELLOW}Checking service status...${NC}"
sudo systemctl status dashboard-backend.service --no-pager || true
sudo systemctl status dashboard-hardware.service --no-pager || true

echo ""
echo -e "${GREEN}======================================"
echo "Installation Complete!"
echo "======================================${NC}"
echo ""
echo "The dashboard will start automatically on boot."
echo ""
echo "Access points:"
echo "  - Main Dashboard: http://localhost:5000"
echo "  - Mobile Interface: http://localhost:5000/mobile"
echo "  - API: http://localhost:5000/api"
echo ""
echo "From another device on your network:"
echo "  - http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo "Hardware Setup:"
echo "  - Button: GPIO 17 (Physical Pin 11)"
echo "  - Motion Sensor: GPIO 27 (Physical Pin 13)"
echo "  - Connect button between GPIO 17 and Ground"
echo "  - Connect PIR sensor VCC to 5V, GND to Ground, OUT to GPIO 27"
echo ""
echo "Next steps:"
echo "  1. Edit config/calendars.json with your calendar feeds (see README - Calendar Setup)"
echo "     then: sudo systemctl restart dashboard-backend"
echo "  2. Access the mobile interface to add recipes"
echo "  3. Plan your meals for the week"
echo "  4. Generate your grocery list"
echo "  5. Reboot to test auto-start: sudo reboot"
echo ""
echo "Logs:"
echo "  - Backend: sudo journalctl -u dashboard-backend -f"
echo "  - Hardware: sudo journalctl -u dashboard-hardware -f"
echo ""
