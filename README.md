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
- **Meal Planning** - Plan meals for the week, with ingredient coverage at a glance
- **Grocery Lists** - Auto-generated from meals, minus what the pantry already holds
- **Pantry Tracking** - Inventory and expiration dates, restocked from the shopping list
- **Calendar Setup** - Add Google/iCloud/Outlook feeds, test them, pick colors
- **Display Settings** - Restyle and rearrange the Pi's screens, and add photos
- **Installable** - Add to Home Screen as a PWA, or build the native iOS app in `app/`

### One Kitchen Inventory
Meals, the grocery list and the pantry share a single set of amounts, so the
three stay in step:

- **Generate** reads the week's recipes, adds up real quantities
  (`1 cup milk` + `½ cup milk` = `1 ½ cups milk`), subtracts what's in the
  pantry, and tops up rows already on the list instead of duplicating them
- **Clear ✓** moves what you bought into the pantry
- **Cooked it** takes a meal's ingredients back out, oldest expiry first, and
  puts anything you were short of on the shopping list
- **🛒 on a pantry row** puts a low item straight back on the list

Recipe lines are parsed by `backend/ingredients.py`, which understands
fractions (`1 1/2`, `½`), ranges (`2-3 cloves`, resolved upward), pack sizes
(`2 (14 oz) cans`) and unit conversion, and reduces names to a shared key so
`Fresh Bell Peppers, diced` matches `3 bell pepper`.

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
# 1. Clone onto the Raspberry Pi (anywhere you like, under any account)
cd ~
git clone https://github.com/CyberSlimer/FamilyDash.git family-dashboard

# 2. Run the installation script as your normal user - NOT with sudo
cd family-dashboard
chmod +x install.sh
./install.sh

# 3. Reboot
sudo reboot
```

`install.sh` works out the account name and the checkout path for itself, so
the dashboard does not have to live in `/home/pi` and the account does not have
to be called `pi`. (Raspberry Pi OS stopped creating a default `pi` user in
2022.) It is also safe to re-run: it keeps your database, your photos and your
`config/calendars.json`, so it doubles as a repair tool if you move the folder.

Python packages go into a virtualenv at `.venv/` inside the checkout, created
with `--system-site-packages` so apt's `python3-rpi.gpio` stays importable. The
systemd units are generated from the templates in `config/*.service.in` with
your real paths substituted in.

### Which desktop session you have matters

The kiosk auto-start is installed as an XDG autostart entry at
`~/.config/autostart/familydash-kiosk.desktop`, which Raspberry Pi OS honours
under all three session types it has shipped - LXDE/X11 on Bullseye and
earlier, and Wayland (wayfire, then labwc) on Bookworm and later. If the
dashboard does not appear full-screen after a reboot, see
[the kiosk troubleshooting notes](#the-kiosk-doesnt-start-on-boot) below.

### Manual Installation

Only needed if you want to understand or adjust what `install.sh` does.

```bash
cd ~/family-dashboard

# 1. Install system packages. On Bookworm and later the Chromium package is
#    named `chromium`; before that, `chromium-browser`.
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-dev python3-venv curl git \
    chromium-browser python3-rpi.gpio
sudo apt-get install -y unclutter           # hides the idle cursor, X11 only
sudo apt-get install -y wlr-randr wlopm     # switch the monitor off on Wayland

# 2. Create the virtualenv and install Python dependencies
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r backend/requirements.txt

# 3. Initialize database
cd backend && ../.venv/bin/python -c "from app import init_db; init_db()" && cd ..

# 4. Configuration and photo storage
cp config/calendars.example.json config/calendars.json
mkdir -p backend/photos

# 5. Render and install the systemd units for this machine
chmod +x config/kiosk.sh config/install-services.sh hardware/controller.py
./config/install-services.sh
sudo systemctl enable --now dashboard-backend.service
sudo systemctl enable --now dashboard-hardware.service

# 6. Set up the kiosk auto-start
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/familydash-kiosk.desktop << EOF
[Desktop Entry]
Type=Application
Name=Family Dashboard Kiosk
Exec=$PWD/config/kiosk.sh
Terminal=false
EOF

# 7. Let the dashboard reach the GPIO pins, then reboot
sudo adduser "$(id -un)" gpio
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

## 📱 Phone App

The management UI works three ways — same features in all of them:

| | How | Best for |
|---|---|---|
| **Browser** | Open `http://<pi-ip>:5000/mobile` | Quick edits from any device |
| **Home-screen app (PWA)** | Open that URL in Safari → Share → **Add to Home Screen** | Full-screen app icon with zero setup; works on iPhone, iPad and Android |
| **Native iOS app** | Build from [`app/`](app/README.md) with Xcode, ship via TestFlight | A real App Store-style install for the household, and the base for push notifications later |

The native app bundles the same `frontend/mobile.html`; on first launch it asks for the Pi's
address and remembers it (⚙️ in the header to change it). Type `demo` as the address to try
the app with sample data and no server. See [app/README.md](app/README.md) for the build
steps — everything except the final Xcode build runs on any OS — and
[docs/APP_STORE_SUBMISSION.md](docs/APP_STORE_SUBMISSION.md) for TestFlight / App Store.

## 🛠️ Troubleshooting

### Dashboard not showing on boot
```bash
# Check backend service
sudo systemctl status dashboard-backend

# Check logs
sudo journalctl -u dashboard-backend -n 50
```

### The kiosk doesn't start on boot

The backend and the kiosk browser are separate things. If
`http://localhost:5000` works from a terminal but the screen is empty, the
backend is fine and only the auto-start is at fault.

```bash
# 1. Does the kiosk script work when run by hand?
~/family-dashboard/config/kiosk.sh

# 2. Is the autostart entry present, and does it point at the right path?
cat ~/.config/autostart/familydash-kiosk.desktop

# 3. Which session are you running? This decides what honours that file.
echo "$XDG_SESSION_TYPE"        # wayland or x11
echo "$XDG_CURRENT_DESKTOP"
```

On Bookworm and later the session is Wayland, and XDG autostart is processed by
the compositor's own config. If the entry is being ignored, add the script
directly instead:

```bash
# labwc (Raspberry Pi OS 2024-11 and later)
mkdir -p ~/.config/labwc
echo "~/family-dashboard/config/kiosk.sh &" >> ~/.config/labwc/autostart

# wayfire (earlier Bookworm images) - add under the [autostart] section
# of ~/.config/wayfire.ini:
#   familydash = /home/YOU/family-dashboard/config/kiosk.sh
```

Re-running `./install.sh` rewrites the XDG entry, so do that after moving the
checkout rather than editing paths by hand.

### Hardware controls not working
```bash
# Check hardware service
sudo systemctl status dashboard-hardware

# Check GPIO permissions (substitute your own username)
groups "$(id -un)" | grep gpio

# If `gpio` is missing, add yourself and reboot
sudo adduser "$(id -un)" gpio

# Test GPIO using the dashboard's own virtualenv
~/family-dashboard/.venv/bin/python -c \
    "import RPi.GPIO as GPIO; GPIO.setmode(GPIO.BCM); print('GPIO OK')"
```

The button does not drive the browser directly. It posts a command to the
backend, and the kiosk polls for it once a second — necessary because Wayland
forbids one program from sending keystrokes to another program's window, which
is how this used to work. So there are two halves to test separately:

```bash
# 1. Does the command reach the backend? Watch this while pressing the button:
sudo journalctl -u dashboard-hardware -f

# 2. Does the kiosk act on a command? This should advance the wall display
#    about a second later, with no button involved:
curl -X POST -H 'Content-Type: application/json' \
     -d '{"action":"next"}' http://localhost:5000/api/display/command
```

If (2) works but (1) logs nothing, the problem is the wiring or the GPIO
group. If (1) logs "Sent command" but the screen does not move, the kiosk
browser is not running or is pointed somewhere else.

Valid actions are `next`, `prev`, `refresh`, `wake`, and `screen` with an
`index`.

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

## 🖥️ Customising the Pi display

Everything about the wall display is set from the **Display** tab in the app —
no editing files on the Pi. Changes are saved as you make them and the kiosk
picks them up within about 15 seconds, without a reload.

- **Screens** — turn any of the five screens off, reorder them, and give each
  its own time on screen (blank uses the default rotation interval)
- **Colours & text** — background gradient, text and accent colours, font,
  text size, and how bright the panels sit over the background
- **Photos** — upload from your phone, caption them, delete them. They feed
  the Photos screen and the screensaver
- **Screensaver** — after a set idle time the dashboard fades into a
  full-screen photo slideshow with a clock, waking on motion, a key or a touch

With the screensaver on, the hardware controller leaves the monitor powered so
the idle display is a photo frame rather than a black rectangle; it only cuts
power much later. With it off, the original motion-timeout behaviour applies.

Photos are stored in `backend/photos/` and served from `/photos/<file>`.
Install Pillow on the Pi (it's in `requirements.txt`) so uploads are
downscaled to 1920px — a phone's full-size photos will otherwise fill the SD
card and stutter on a Pi 4. HEIC photos additionally need `pillow-heif`.

## 📱 API Reference

### Recipes
- `GET /api/recipes` - List all recipes
- `POST /api/recipes` - Create recipe
- `GET /api/recipes/{id}` - Get recipe details
- `PUT /api/recipes/{id}` - Update recipe
- `DELETE /api/recipes/{id}` - Delete recipe
- `POST /api/recipes/import-url` - Import from URL

### Meals
- `GET /api/meals` - List meals (supports date filtering; `?with_availability=1`
  adds `have`/`total` ingredient coverage per meal)
- `POST /api/meals` - Create meal plan (optional `servings` scales the recipe)
- `PUT /api/meals/{id}` - Update meal
- `DELETE /api/meals/{id}` - Delete meal
- `GET /api/meals/{id}/availability` - Ingredients needed vs. pantry stock
- `POST /api/meals/{id}/cook` - Mark cooked and deduct from the pantry.
  `{"add_missing_to_grocery": true}` puts any shortfall on the list;
  `{"force": true}` deducts again for a meal already marked cooked
- `POST /api/meals/{id}/uncook` - Clear the cooked flag (does not restore stock)

### Grocery
- `GET /api/grocery` - List grocery items, each flagged with `in_pantry` /
  `pantry_amount`
- `POST /api/grocery` - Add item (an amount typed into the name is lifted out)
- `PUT /api/grocery/{id}` - Update item
- `DELETE /api/grocery/{id}` - Delete item
- `POST /api/grocery/generate` - Build from the meal plan.
  `{"start_date", "end_date", "use_pantry": true, "include_optional": true}`;
  answers with `added`, `merged` and `skipped`
- `POST /api/grocery/clear-checked` - Clear bought items.
  `{"to_pantry": true, "location": "pantry"}` stocks the pantry with them

### Pantry
- `GET /api/pantry` - List pantry items (`?location=`, `?expiring_soon=1&days=7`)
- `POST /api/pantry` - Add item
- `PUT /api/pantry/{id}` - Update item
- `DELETE /api/pantry/{id}` - Delete item
- `POST /api/pantry/{id}/to-grocery` - Add this item to the shopping list

### Display & Photos
- `GET /api/display` - Screen order, theme, screensaver settings, photo list
  and the current `revision`
- `PUT /api/display` - Save display settings (unknown screens and unsafe
  colours/fonts are rejected rather than stored)
- `POST /api/display/reset` - Back to the original look
- `GET /api/display/revision` - Cheap poll; the kiosk uses it to spot changes
- `GET /api/photos` - Uploaded photos
- `POST /api/photos` - Upload one or more (`files`, multipart). Images are
  downscaled to 1920px when Pillow is installed
- `PUT /api/photos/{id}` - Set caption or sort order
- `DELETE /api/photos/{id}` - Remove the photo and its file
- `POST /api/photos/reorder` - `{"ids": [3, 1, 2]}` sets slideshow order

### Weather & System
- `GET /api/weather` - Current conditions, a 7-day outlook, sunrise/sunset and NWS alerts
  for the configured location. Served from a 10-minute cache; add `?refresh=1` to force a
  re-fetch. `current` comes from the nearest observation station (so it carries a real
  `feelsLike`), `daily` folds the 12-hour NWS periods into a high and a low per day, and
  `sun` is computed locally rather than fetched. If a refresh fails after at least one
  success the last good payload is returned with `stale: true` rather than an error.
- `GET /api/health` - Server identity for the app's server-setup screen

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
./update.sh
```

`update.sh` backs up the database and photos to your home directory, pulls,
upgrades the virtualenv, runs the schema migration, re-renders the systemd
units and restarts everything. Doing it by hand misses the migration step,
which is what adds columns introduced since your Pi was installed.

### Backup Data
```bash
cd ~/family-dashboard

# Backup database and photos
cp backend/dashboard.db ~/dashboard-backup-$(date +%Y%m%d).db
tar -czf ~/dashboard-photos-$(date +%Y%m%d).tar.gz -C backend photos

# Restore from backup
cp ~/dashboard-backup-20260315.db backend/dashboard.db
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
