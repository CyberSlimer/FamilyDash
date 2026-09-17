# Family Dashboard for Raspberry Pi 4

A complete family command center running on Raspberry Pi 4 with a 27" landscape monitor. Features calendar integration, weather alerts, meal planning, recipe management, grocery lists, and pantry tracking.

## 🌟 Features

### 4 Rotating Display Screens (Main Dashboard)
1. **Calendar & Weather** - Today's events plus the week ahead from all your calendars, and local weather with alerts
2. **Meal Plan** - This week's meals at a glance
3. **Grocery List** - Shopping list organized by category
4. **Recipes & Pantry** - Favorite recipes and expiring pantry items

### Mobile Web Interface
- **Recipe Management** - Add, edit, import from URLs
- **Meal Planning** - Plan meals for the week
- **Grocery Lists** - Manage shopping lists, auto-generate from meals
- **Pantry Tracking** - Track inventory and expiration dates
- **Calendar Setup** - Add Google/iCloud/Outlook feeds, test them, pick colors

### Hardware Controls
- **Physical Button** - Advance to next screen
- **PIR Motion Sensor** - Auto wake/sleep display
- **Bluetooth Keyboard** - Full keyboard navigation

### Smart Features
- Recipe import from URLs with automatic parsing
- Smart grocery list generation from meal plans
- Local weather & NWS alerts (location set in `config.env`)
- Auto-start kiosk mode
- 24/7 reliable operation
- Mobile-responsive design

## 📋 Requirements

### Hardware
- Raspberry Pi 4 (2GB+ RAM recommended)
- 27" Monitor (landscape orientation)
- MicroSD card (16GB+ recommended)
- Power supply for Raspberry Pi
- PIR motion sensor (HC-SR501 or similar)
- Tactile push button
- Jumper wires
- Optional: Bluetooth keyboard

### Software
- Raspberry Pi OS (64-bit recommended)
- Python 3.9+
- Chromium browser

## 🔧 Hardware Setup

### GPIO Connections

```
Raspberry Pi 4 GPIO Pinout:

Physical Pin | GPIO | Connection
-------------|------|------------------
Pin 11       | 17   | Button (to Ground)
Pin 13       | 27   | PIR Sensor OUT
Pin 2        | 5V   | PIR Sensor VCC
Pin 6        | GND  | Button & PIR GND
```

### Button Wiring
1. Connect one side of button to GPIO 17 (Physical Pin 11)
2. Connect other side to Ground (any GND pin)
3. Internal pull-up resistor is enabled in software

### PIR Motion Sensor Wiring
1. Connect VCC to 5V (Physical Pin 2)
2. Connect GND to Ground (Physical Pin 6)
3. Connect OUT to GPIO 27 (Physical Pin 13)

## 📥 Installation

### Quick Install

```bash
# 1. Copy files to Raspberry Pi
cd ~
git clone https://github.com/CyberSlimer/FamilyDash.git family-dashboard
# Or copy the files directly to /home/pi/family-dashboard

# 2. Run installation script
cd family-dashboard
chmod +x install.sh
./install.sh

# 3. Reboot
sudo reboot
```

### Manual Installation

```bash
# 1. Install system packages
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y python3 python3-pip python3-dev python3-rpi.gpio \
    chromium-browser unclutter xdotool

# 2. Install Python dependencies
cd ~/family-dashboard/backend
pip3 install -r requirements.txt --break-system-packages

# 3. Initialize database
python3 -c "from app import init_db; init_db()"

# 4. Install services
sudo cp config/dashboard-backend.service /etc/systemd/system/
sudo cp config/dashboard-hardware.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dashboard-backend.service
sudo systemctl enable dashboard-hardware.service
sudo systemctl start dashboard-backend.service
sudo systemctl start dashboard-hardware.service

# 5. Setup kiosk mode
mkdir -p ~/.config/lxsession/LXDE-pi
cat > ~/.config/lxsession/LXDE-pi/autostart << EOF
@lxpanel --profile LXDE-pi
@pcmanfm --desktop --profile LXDE-pi
@/home/pi/family-dashboard/config/kiosk.sh
EOF

# 6. Make scripts executable
chmod +x config/kiosk.sh
chmod +x hardware/controller.py

# 7. Reboot
sudo reboot
```

## 🎮 Usage

### Main Dashboard Controls

**Keyboard Navigation:**
- `→` or `Space` - Next screen
- `←` - Previous screen  
- `1-4` - Jump to specific screen
- `R` - Refresh current screen

**Physical Button:**
- Press to advance to next screen
- Automatically wakes display if asleep

**Motion Sensor:**
- Wakes display when motion detected
- Puts display to sleep after 5 minutes of no motion

### Mobile Interface

Access from your phone or tablet:
```
http://<raspberry-pi-ip>:5000/mobile
```

**Features:**
- Add and manage recipes
- Import recipes from URLs
- Plan weekly meals
- Create and check off grocery items
- Track pantry inventory
- Works offline once loaded

### Adding Recipes

**Method 1: Import from URL**
1. Open mobile interface
2. Go to Recipes tab
3. Click "Import URL"
4. Paste recipe URL (works with most recipe sites)
5. Edit imported data if needed
6. Save

**Method 2: Manual Entry**
1. Open mobile interface
2. Go to Recipes tab
3. Click + button
4. Fill in recipe details
5. Add ingredients one by one
6. Save

### Planning Meals

1. Open mobile interface
2. Go to Meals tab
3. View current week
4. Click + button for each meal slot
5. Select recipe or enter custom meal
6. Meals appear on main dashboard

### Grocery Shopping

1. **Auto-generate from meals:**
   - Go to Grocery tab
   - Click "Generate" button
   - Ingredients from planned meals are added

2. **Manual entry:**
   - Click + button
   - Add item name, quantity, category
   - Save

3. **Shopping mode:**
   - View list organized by store section
   - Check off items as you shop
   - Click "Clear ✓" to remove checked items

## 🔧 Configuration

### Settings File
Settings are stored in SQLite database. Access via API:

```bash
# View all settings
curl http://localhost:5000/api/settings

# Update setting
curl -X PUT http://localhost:5000/api/settings/screen_rotation_interval \
  -H "Content-Type: application/json" \
  -d '{"value": "60"}'
```

### Available Settings
- `screen_rotation_interval` - Seconds between screen changes (default: 30)
- `motion_timeout` - Seconds of inactivity before sleep (default: 300)
- `default_screen` - Screen to show on wake (default: 0)

### Customize Hardware Pins

Edit `hardware/controller.py`:
```python
BUTTON_PIN = 17  # Change to your button GPIO
MOTION_PIN = 27  # Change to your sensor GPIO
```

## 📅 Calendar Setup

The dashboard merges any number of calendars into the "Today's Schedule" screen.
Two source types are supported:

| Type | Works with | What you need |
|------|-----------|---------------|
| `ics` | Google Calendar (secret iCal address), Outlook/Office 365 published calendars, school & sports calendars, any `webcal://` link | The feed URL |
| `caldav` | iCloud, Nextcloud, Fastmail, Synology, any CalDAV server | Server URL + username + password |

**Easiest: use the mobile interface.** Open `http://<raspberry-pi-ip>:5000/mobile`, go to the
**📅 Calendars** tab and tap **+**. Paste the feed URL (or CalDAV server + login), hit **Test**
to preview the next week's events — for CalDAV accounts this also lists the account's calendars
so you can tick the ones you want — pick a color and **Save**. The dashboard re-syncs immediately;
each calendar shows its live sync status, and you can hide/show, edit or remove it from the same tab.

Under the hood this edits **`config/calendars.json`** (git-ignored so your URLs and passwords never
get committed). You can also edit it by hand:

```bash
cp config/calendars.example.json config/calendars.json
nano config/calendars.json
sudo systemctl restart dashboard-backend
```

```json
{
  "calendars": [
    { "id": "family", "name": "Family", "type": "ics",
      "url": "https://calendar.google.com/calendar/ical/.../private-.../basic.ics",
      "color": "#4f8ef7" },

    { "id": "icloud", "name": "iCloud", "type": "caldav",
      "url": "https://caldav.icloud.com",
      "username": "${ICLOUD_USERNAME}",
      "password": "${ICLOUD_APP_PASSWORD}",
      "calendars": ["Home", "Kids"],
      "color": "#e0685c" }
  ]
}
```

- `${VAR}` pulls the value from `config.env` (or the real environment), so secrets can stay out of the JSON.
- `color` is the accent shown next to each event. Omit it to get an automatic color.
- `calendars` (CalDAV only) limits which of the account's calendars are shown. Omit it to show all of them.
- `"enabled": false` temporarily hides a calendar without deleting it.

### Where to find your feed URL

- **Google Calendar**: Settings → pick the calendar → *Integrate calendar* → **Secret address in iCal format**.
- **iCloud**: use `https://caldav.icloud.com` with your Apple ID and an [app-specific password](https://support.apple.com/en-us/102654) (your normal password will not work).
- **Outlook.com / Office 365**: Settings → Calendar → *Shared calendars* → Publish a calendar → copy the **ICS** link.
- **Most other services** offer a "Subscribe" / "iCal" / "webcal://" link — paste it as an `ics` type; `webcal://` is converted automatically.

### How it works

- Events are fetched in the background every `CALENDAR_REFRESH_INTERVAL` seconds (default 300) and cached, so the display never blocks on a slow server.
- Recurring events, all-day events, multi-day events and timezones are all handled; times are shown in `TIMEZONE` from `config.env`.
- If a calendar fails to fetch, the previous events are kept and a warning banner appears on the dashboard. `GET /api/calendar/status` shows per-calendar health.
- Test your configuration without starting the whole app:
  ```bash
  cd backend && python3 calendar_sync.py
  ```

## 🛠️ Troubleshooting

### Dashboard not showing on boot
```bash
# Check backend service
sudo systemctl status dashboard-backend

# Check logs
sudo journalctl -u dashboard-backend -n 50
```

### Hardware controls not working
```bash
# Check hardware service
sudo systemctl status dashboard-hardware

# Check GPIO permissions
groups pi | grep gpio
# Should show: pi : pi adm dialout cdrom sudo audio video plugdev games users input render gpio

# Test GPIO
python3 -c "import RPi.GPIO as GPIO; GPIO.setmode(GPIO.BCM); print('GPIO OK')"
```

### Motion sensor always triggering
- Adjust sensitivity pot on PIR sensor
- Increase MOTION_TIMEOUT in controller.py
- Check for heat sources near sensor

### Display not turning off
```bash
# Test display control
vcgencmd display_power 0  # Off
vcgencmd display_power 1  # On
```

### Recipe import failing
- Check internet connection
- Some sites block scrapers - try different sites
- Manually add recipe if import fails

## 📱 API Reference

### Recipes
- `GET /api/recipes` - List all recipes
- `POST /api/recipes` - Create recipe
- `GET /api/recipes/{id}` - Get recipe details
- `PUT /api/recipes/{id}` - Update recipe
- `DELETE /api/recipes/{id}` - Delete recipe
- `POST /api/recipes/import-url` - Import from URL

### Meals
- `GET /api/meals` - List meals (supports date filtering)
- `POST /api/meals` - Create meal plan
- `PUT /api/meals/{id}` - Update meal
- `DELETE /api/meals/{id}` - Delete meal

### Grocery
- `GET /api/grocery` - List grocery items
- `POST /api/grocery` - Add item
- `PUT /api/grocery/{id}` - Update item
- `DELETE /api/grocery/{id}` - Delete item
- `POST /api/grocery/generate` - Generate from meals
- `POST /api/grocery/clear-checked` - Remove checked

### Pantry
- `GET /api/pantry` - List pantry items
- `POST /api/pantry` - Add item
- `PUT /api/pantry/{id}` - Update item
- `DELETE /api/pantry/{id}` - Delete item

### Weather
- `GET /api/weather` - Get Rochester, NY weather

### Calendar
- `GET /api/calendar/events?start_date=&end_date=` - Events overlapping the range (ISO dates; defaults to today)
- `GET /api/calendar/status` - Configured calendars and last-sync health
- `POST /api/calendar/refresh` - Force an immediate re-sync
- `GET /api/calendar/calendars` - Configured calendars (passwords omitted) with sync status
- `POST /api/calendar/calendars` - Add a calendar `{name, type, url, username?, password?, calendars?, color?, enabled?}`
- `PUT /api/calendar/calendars/<id>` - Update a calendar (blank password keeps the stored one)
- `DELETE /api/calendar/calendars/<id>` - Remove a calendar
- `POST /api/calendar/test` - Fetch a calendar without saving; returns `{ok, count, sample, error, available_calendars}`

## 🔄 Maintenance

### Update Software
```bash
cd ~/family-dashboard
git pull
pip3 install -r backend/requirements.txt --break-system-packages
sudo systemctl restart dashboard-backend
sudo systemctl restart dashboard-hardware
```

### Backup Data
```bash
# Backup database
cp ~/family-dashboard/backend/dashboard.db ~/dashboard-backup-$(date +%Y%m%d).db

# Restore from backup
cp ~/dashboard-backup-20240315.db ~/family-dashboard/backend/dashboard.db
sudo systemctl restart dashboard-backend
```

### View Logs
```bash
# Backend logs
sudo journalctl -u dashboard-backend -f

# Hardware logs
sudo journalctl -u dashboard-hardware -f

# System logs
sudo journalctl -f
```

## 🎨 Customization

### Change Colors
Edit `frontend/index.html` and modify CSS gradient:
```css
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
/* Change to your preferred colors */
```

### Add More Screens
1. Add new screen div in `frontend/index.html`
2. Add screen indicator dot
3. Update `nextScreen()` function modulo
4. Add data fetching function

### Change Location
Edit `backend/app.py`:
```python
# Change coordinates in weather() function
lat, lon = 43.1566, -77.6088  # Your coordinates
```

## 📄 License

MIT License - Feel free to modify and distribute

## 🤝 Contributing

Contributions welcome! Areas for improvement:
- Better recipe parsing for more websites
- Calendar sync improvements  
- Voice control integration
- Meal recommendations based on pantry
- Shopping list sharing between family members

## 💡 Tips

1. **Screen burn-in prevention**: Rotation helps prevent static elements from burning in
2. **Recipe organization**: Use tags extensively for easy filtering
3. **Meal planning**: Plan meals on Sunday for the whole week
4. **Grocery efficiency**: Generate list from meals, then add staples manually
5. **Pantry tracking**: Update when you shop to keep accurate inventory
6. **Motion sensor placement**: Mount 6-8 feet high for best coverage

## 🆘 Support

For issues or questions:
1. Check this README
2. Review logs with journalctl
3. Test components individually
4. Check GPIO connections
5. Verify network connectivity

## 🎯 Roadmap

Future enhancements:
- [ ] Voice commands via Google Assistant
- [ ] Barcode scanning for pantry
- [ ] Meal nutrition tracking
- [ ] Recipe ratings and notes
- [x] Shared family calendar (CalDAV + ICS feeds)
- [ ] Weather radar integration
- [ ] Amazon Alexa integration
- [ ] Multiple location support
