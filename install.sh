#!/bin/bash
# Family Calendar Dashboard - Automated Installation Script
# Run this on your Raspberry Pi to set up everything automatically

set -e  # Exit on error

echo "======================================"
echo "Family Calendar Dashboard Installer"
echo "======================================"
echo ""

# Check if running on Raspberry Pi
if [ ! -f /etc/rpi-issue ]; then
    echo "Warning: This doesn't appear to be a Raspberry Pi."
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "Step 1: Updating system packages..."
sudo apt update
sudo apt upgrade -y

echo ""
echo "Step 2: Installing required packages..."
sudo apt install -y nginx chromium-browser python3-pip git unclutter xdotool

echo ""
echo "Step 3: Installing Python dependencies..."
pip3 install flask caldav icalendar requests flask-cors --break-system-packages

echo ""
echo "Step 4: Cloning repository..."
cd /var/www/html
sudo rm -f index.html  # Remove default nginx page
sudo git clone https://github.com/yourusername/family-calendar-dashboard.git .

echo ""
echo "Step 5: Setting up calendar sync service..."
sudo cp calendar-sync.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable calendar-sync.service

echo ""
echo "Step 6: Configuring nginx..."
sudo systemctl enable nginx
sudo systemctl restart nginx

echo ""
echo "Step 7: Setting up autostart..."
mkdir -p ~/.config/lxsession/LXDE-pi
cp autostart ~/.config/lxsession/LXDE-pi/autostart

echo ""
echo "Step 8: Disabling screen blanking..."
sudo sed -i 's/^#xserver-command=.*/xserver-command=X -s 0 -dpms/' /etc/lightdm/lightdm.conf

echo ""
echo "======================================"
echo "Installation Complete!"
echo "======================================"
echo ""
echo "IMPORTANT: Before rebooting, you need to:"
echo "1. Edit calendar-sync.py with your calendar credentials"
echo "   sudo nano /var/www/html/calendar-sync.py"
echo ""
echo "2. Add your OpenWeatherMap API key (get free key at openweathermap.org)"
echo ""
echo "3. Update the GitHub URL in this script if you haven't already"
echo ""
echo "Then run:"
echo "  sudo systemctl start calendar-sync.service"
echo "  sudo reboot"
echo ""
echo "Your dashboard will be available at http://localhost"
echo "======================================"
