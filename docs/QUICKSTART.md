# Quick Start Guide

Get your Family Dashboard up and running in 30 minutes!

## 📦 What You Need

### Hardware Checklist
- [ ] Raspberry Pi 4 (2GB or more RAM)
- [ ] MicroSD card (16GB+) with Raspberry Pi OS installed
- [ ] 27" Monitor with HDMI cable
- [ ] PIR Motion Sensor (HC-SR501)
- [ ] Push button (tactile switch)
- [ ] 3x Female-to-Female jumper wires
- [ ] 2x Male-to-Female jumper wires
- [ ] Power supply for Raspberry Pi
- [ ] Keyboard and mouse (for initial setup)
- [ ] Optional: Bluetooth keyboard for permanent use

### Software Prerequisites
- Raspberry Pi OS (64-bit recommended)
- Internet connection

## 🚀 Installation (Step-by-Step)

### Step 1: Prepare Raspberry Pi (10 minutes)

```bash
# 1. Boot up your Raspberry Pi with monitor, keyboard, mouse connected
# 2. Connect to WiFi
# 3. Open Terminal (Ctrl+Alt+T)

# 4. Update system
sudo apt-get update && sudo apt-get upgrade -y

# 5. Enable GPIO and configure for headless operation
sudo raspi-config
# - Interface Options → Enable SSH (optional, for remote access)
# - System Options → Boot / Auto Login → Desktop Autologin
# - Exit and don't reboot yet
```

### Step 2: Install Dashboard (5 minutes)

```bash
# 1. Copy dashboard files to Raspberry Pi
# If you have files on USB:
cd ~
cp -r /media/pi/USB/family-dashboard .

# OR clone from git (if available):
# git clone <your-repo-url> family-dashboard

# 2. Run installation script
cd family-dashboard
chmod +x install.sh
./install.sh

# This will take about 5 minutes
# It installs all dependencies and sets up services
```

### Step 3: Wire Hardware (10 minutes)

**Safety First:**
- Shut down Raspberry Pi: `sudo shutdown -h now`
- Unplug power
- Make all connections
- Double-check before powering on

**Button Wiring:**
```
Push Button Pin 1 -----> GPIO 17 (Physical Pin 11)
Push Button Pin 2 -----> GND (Physical Pin 9)
```

**PIR Sensor Wiring:**
```
PIR VCC  -----> 5V Power (Physical Pin 2)
PIR GND  -----> Ground (Physical Pin 6)
PIR OUT  -----> GPIO 27 (Physical Pin 13)
```

**Visual Reference:**
```
Raspberry Pi GPIO (Top View)
    3V3  (1) (2)  5V   <-- PIR VCC
  GPIO2  (3) (4)  5V
  GPIO3  (5) (6)  GND  <-- PIR GND
  GPIO4  (7) (8)  GPIO14
    GND  (9) (10) GPIO15
 GPIO17 (11) (12) GPIO18  <-- Button
 GPIO27 (13) (14) GND     <-- PIR OUT
 GPIO22 (15) (16) GPIO23
    3V3 (17) (18) GPIO24
 GPIO10 (19) (20) GND
  GPIO9 (21) (22) GPIO25
 GPIO11 (23) (24) GPIO8
    GND (25) (26) GPIO7
    ... (continues)
```

### Step 4: First Boot (5 minutes)

```bash
# 1. Power on Raspberry Pi
# 2. Wait for boot (about 30 seconds)
# 3. Dashboard should auto-launch in full screen
# 4. You should see Screen 1 (Calendar & Weather)

# If dashboard doesn't appear:
# - Press F11 to exit full screen
# - Open Terminal
# - Check service status:
sudo systemctl status dashboard-backend
```

### Step 5: Configure Mobile Access (2 minutes)

```bash
# 1. Find your Raspberry Pi's IP address
hostname -I

# 2. From your phone/tablet, open browser and go to:
http://<raspberry-pi-ip>:5000/mobile

# Example: http://192.168.1.100:5000/mobile

# 3. Bookmark this page for easy access
```

## ✅ Verify Everything Works

### Test Checklist

**Display:**
- [ ] Dashboard shows on monitor
- [ ] Time and date are correct
- [ ] Screen rotates every 30 seconds

**Button:**
- [ ] Press button → advances to next screen
- [ ] Works from any screen
- [ ] Immediate response

**Motion Sensor:**
- [ ] Walk away for 6 minutes → display turns off
- [ ] Wave hand in front of sensor → display turns on
- [ ] Green indicator light on sensor

**Mobile Interface:**
- [ ] Can access from phone
- [ ] Can add test recipe
- [ ] Interface is responsive

**Weather:**
- [ ] Shows current temperature
- [ ] Shows forecast
- [ ] Location is Rochester, NY

## 🎯 Your First Tasks

### 1. Add Your First Recipe (3 minutes)

```
1. Open mobile interface: http://<pi-ip>:5000/mobile
2. Tap "Recipes" tab
3. Tap "Import URL" button
4. Paste a recipe URL (try AllRecipes.com)
5. Review imported data
6. Tap "Save"
7. Mark as favorite (⭐ button)
```

### 2. Plan This Week's Meals (5 minutes)

```
1. Go to "Meals" tab
2. For each day:
   - Tap the day
   - Select meal type (breakfast/lunch/dinner)
   - Choose a recipe
   - Save
3. View on main dashboard (Screen 2)
```

### 3. Generate Shopping List (2 minutes)

```
1. Go to "Grocery" tab
2. Tap "Generate" button
3. Ingredients from your meal plan appear
4. Add additional items manually if needed
5. View on main dashboard (Screen 3)
```

## 🔧 Common Issues & Fixes

### "Dashboard not showing on boot"

**Fix:**
```bash
# Check if service is running
sudo systemctl status dashboard-backend

# If not running, start it
sudo systemctl start dashboard-backend

# Check for errors
sudo journalctl -u dashboard-backend -n 50
```

### "Button not working"

**Check:**
1. Connections are secure
2. Button is not damaged (test with multimeter)
3. Check GPIO pins are correct

**Test button manually:**
```bash
python3 << EOF
import RPi.GPIO as GPIO
import time

GPIO.setmode(GPIO.BCM)
GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print("Press button...")
while True:
    if GPIO.input(17) == GPIO.LOW:
        print("PRESSED!")
    time.sleep(0.1)
EOF
```

### "Motion sensor always on/off"

**Adjust sensor:**
- Turn sensitivity dial clockwise for more sensitivity
- Turn time delay dial to minimum
- Ensure jumper is in "repeatable trigger" mode
- Point sensor away from heat sources

### "Can't access mobile interface"

**Check:**
1. Raspberry Pi and phone on same WiFi network
2. Firewall not blocking port 5000
3. Backend service is running
4. Use correct IP address

**Find IP:**
```bash
hostname -I
# Use first IP address shown
```

## 📱 Keyboard Shortcuts

When using Bluetooth keyboard:

| Key | Action |
|-----|--------|
| → or Space | Next screen |
| ← | Previous screen |
| 1 | Go to Calendar/Weather |
| 2 | Go to Meal Plan |
| 3 | Go to Grocery List |
| 4 | Go to Recipes/Pantry |
| R | Refresh current screen |

## 🎨 Personalization Tips

### Change Colors

Edit `/home/pi/family-dashboard/frontend/index.html`:

Find this line:
```css
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
```

Replace with your colors:
```css
/* Blue theme */
background: linear-gradient(135deg, #2193b0 0%, #6dd5ed 100%);

/* Green theme */
background: linear-gradient(135deg, #56ab2f 0%, #a8e063 100%);

/* Sunset theme */
background: linear-gradient(135deg, #FA8BFF 0%, #2BD2FF 100%);
```

Save and refresh browser.

### Change Location

Edit `/home/pi/family-dashboard/backend/app.py`:

Find weather function and update coordinates:
```python
lat, lon = 43.1566, -77.6088  # Rochester, NY
# Change to your coordinates
```

Restart backend:
```bash
sudo systemctl restart dashboard-backend
```

## 📞 Getting Help

1. **Read the README**: Full documentation in README.md
2. **Check logs**: `sudo journalctl -u dashboard-backend -f`
3. **Test components**: Test button, sensor, display individually
4. **Restart services**: `sudo systemctl restart dashboard-*`

## 🎉 You're Done!

Your Family Dashboard is now running!

**Next Steps:**
- Add more recipes
- Plan meals for the week
- Generate grocery lists
- Track pantry items
- Enjoy your smart family command center!

**Pro Tips:**
- Update meal plan every Sunday
- Generate grocery list before shopping
- Import recipes while browsing cooking sites
- Use tags to organize recipes by cuisine/type
- Set reminders for expiring pantry items

---

**Need More Help?** See README.md for detailed documentation.
