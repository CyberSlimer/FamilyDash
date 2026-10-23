# Family Dashboard - Project Structure

Complete file inventory and organization for the Family Dashboard system.

## 📁 Directory Structure

```
family-dashboard/
│
├── README.md                          # Main documentation
├── install.sh                         # Installation script
├── update.sh                          # Update script
├── config.env                         # Configuration file
│
├── backend/                           # Backend API
│   ├── app.py                         # Flask application, models, endpoints
│   ├── calendar_sync.py               # CalDAV/ICS fetch and recurrence expansion
│   ├── ingredients.py                 # Ingredient parsing and unit maths
│   ├── requirements.txt               # Python dependencies
│   ├── tests/                         # pytest suite
│   │   ├── test_calendar_api.py
│   │   ├── test_calendar_sync.py
│   │   ├── test_display.py
│   │   ├── test_display_command.py
│   │   ├── test_ingredients.py
│   │   ├── test_inventory.py
│   │   └── fixtures/sample.ics
│   └── dashboard.db                   # SQLite database (created on install)
│
├── frontend/                          # Web interfaces
│   ├── index.html                     # Main dashboard (4 screens)
│   ├── mobile.html                    # Mobile management interface
│   ├── manifest.webmanifest           # "Add to Home Screen" metadata
│   └── icons/                         # Home-screen and app icons
│
├── hardware/                          # Hardware integration
│   └── controller.py                  # Button & motion sensor control
│
├── app/                               # Native iOS shell (Capacitor)
│   ├── README.md                      # Mac-side build and TestFlight steps
│   ├── capacitor.config.json          # Capacitor configuration
│   ├── package.json                   # npm scripts, incl. `npm run build`
│   ├── ExportOptions.plist            # xcodebuild export settings
│   ├── ios/                           # Generated Xcode project
│   ├── resources/                     # Icon and splash source images
│   ├── scripts/                       # build.js, make_icons.py, screenshots.sh
│   └── screenshots/                   # App Store screenshots, per device
│
├── config/                            # Configuration files
│   ├── dashboard-backend.service.in   # Systemd template for the API
│   ├── dashboard-hardware.service.in  # Systemd template for the hardware
│   ├── install-services.sh            # Fills the templates in for this machine
│   ├── calendars.example.json         # Calendar sources, copied to calendars.json
│   └── kiosk.sh                       # Kiosk mode auto-start script
│
└── docs/                              # Documentation
    ├── GETTING_STARTED.md             # System overview
    ├── QUICKSTART.md                  # Quick start guide
    ├── WIRING.md                      # Hardware wiring guide
    ├── STRUCTURE.md                   # This file
    ├── APP_STORE_SUBMISSION.md        # iOS release checklist
    ├── MAC_HANDOFF_PROMPT.md          # Handing the iOS build over to a Mac
    ├── PRIVACY.md                     # Privacy policy shipped with the app
    └── legacy-calendar-sync.py        # Superseded standalone sync script
```

## 📄 File Descriptions

### Root Level

**README.md**
- Complete system documentation
- Features overview
- Installation instructions
- API reference
- Maintenance guide

**install.sh**
- Automated installation script
- Installs dependencies
- Configures services
- Sets up auto-start

**update.sh**
- Software update script
- Creates backup before updating
- Updates dependencies
- Restarts services

**config.env**
- Configuration settings
- Easy customization
- Hardware pin assignments
- Display preferences

### Backend (backend/)

**app.py**
- Flask web server
- RESTful API endpoints
- Database models (SQLAlchemy)
- Recipe URL import
- Weather integration
- Grocery list generation
- `init_db()`, which also adds columns introduced since an older install

**Key Features:**
- Recipe CRUD operations
- Meal planning, including cook/uncook against the pantry
- Grocery list management
- Pantry inventory
- Photo uploads for the kiosk slideshow
- Display customisation (theme, screen order, screensaver)
- Weather data (National Weather Service)
- Calendar integration (CalDAV and ICS/webcal)

**calendar_sync.py**
- Fetches CalDAV (iCloud, Nextcloud, Fastmail) and ICS/webcal sources
- Expands recurring events
- Normalizes everything to the local timezone
- Caches results in memory so the dashboard never waits on a slow server
- Reads `config/calendars.json`; `${VAR}` references resolve from the environment

**ingredients.py**
- Parses free-text ingredients ("1.5 lb chicken breast") into qty, unit and name
- Canonical unit conversion and arithmetic
- `normalize_name()` produces the `match_key` that links the three lists
- Pure text/number work, no database access

**requirements.txt**
- Web layer: Flask, Flask-CORS, Flask-SQLAlchemy
- Scraping: requests, beautifulsoup4, lxml
- Calendar: icalendar, recurring-ical-events, caldav
- Photos: Pillow, pillow-heif
- Config: python-dotenv
- Hardware: RPi.GPIO, installed only on ARM

  See the file itself for the version ranges.

**tests/**
- pytest suite covering the calendar API and sync, the inventory loop,
  ingredient parsing, the display settings and the kiosk command channel
- Run with `cd backend && python -m pytest tests/ -q`
- Uses `DASHBOARD_DB` to point at a scratch database, never the real one

**dashboard.db** (auto-created)
- SQLite database
- Tables: recipe, meal_plan, grocery_item, pantry_item, photo, settings

### Frontend (frontend/)

**index.html**
- Main dashboard interface
- 4 rotating screens
- Optimized for 27" landscape
- Features:
  - Screen 1: Calendar & Weather
  - Screen 2: Weekly Meal Plan
  - Screen 3: Grocery List
  - Screen 4: Recipes & Pantry
- Automatic screen rotation
- Responsive design
- Real-time clock

**mobile.html**
- Mobile-responsive interface
- Tab-based navigation
- Recipe management
- Meal planning
- Grocery list editing
- Pantry tracking
- Display tab: theme, screen order, screensaver, photos
- Import recipes from URLs
- Touch-optimized
- The single copy of this UI: `app/` bundles it into the iOS app

**manifest.webmanifest**
- Lets the mobile interface be installed to a phone home screen

**icons/**
- `icon-192.png`, `icon-512.png`, `apple-touch-icon.png`

### Hardware (hardware/)

**controller.py**
- GPIO control for Raspberry Pi
- Button handling (GPIO 17)
- Motion sensor monitoring (GPIO 27)
- Display power management
- Screen commands posted to the backend (no synthetic keystrokes)
- Features:
  - Button press detection
  - Motion-based wake/sleep
  - Auto screen rotation
  - Display timeout

### Config (config/)

**dashboard-backend.service.in**
- Systemd service template
- Auto-start backend API
- Restart on failure
- `@@RUN_USER@@`, `@@APP_DIR@@` and `@@PYTHON@@` are filled in at install time,
  so the service follows whatever account and checkout path you actually use

**dashboard-hardware.service.in**
- Systemd service template, same placeholders
- Auto-start hardware controller
- GPIO management
- Runs after backend service

**install-services.sh**
- Renders both templates for this machine, installs them under
  `/etc/systemd/system/`, then enables them
- Called by `install.sh`; safe to re-run after moving the checkout

**calendars.example.json**
- Example calendar sources, copied to `config/calendars.json` on first install
- `config/calendars.json` is git-ignored, so your URLs stay out of the repo

**kiosk.sh**
- Chromium browser launcher
- Kiosk mode configuration
- Screen blanking disabled
- Mouse cursor auto-hide
- Full-screen mode
- Waits for the desktop session, then for the network to stop changing,
  before launching the browser
- Watchdog: 45 seconds after launch it reads `kiosk_last_seen_seconds` from
  `/api/health`. The page polls every second, so a recent value proves a
  browser is up and running its JavaScript - stronger evidence than the
  process merely existing, which it does even when the screen is blank.
  If nothing has polled, it kills the browser and retries, up to three times.
- Logs to `$XDG_RUNTIME_DIR/familydash-kiosk.log`, falling back to `/tmp`

### iOS App (app/)

**A Capacitor shell around `frontend/mobile.html`.** There is one copy of the
UI; `npm run build` bundles it into the app, so a change to the web version
ships in the app too. The app asks for the Pi's address on first launch and
verifies it against `/api/health`. Typing `demo` runs it on built-in sample
data with no server, which is what App Store screenshots and App Review use.

**scripts/**
- `build.js` - copies the frontend in and syncs Capacitor
- `make_icons.py` - generates the icon set from `resources/`
- `screenshots.sh` - drives the simulator for App Store screenshots

Building needs a Mac with Xcode. See [`app/README.md`](../app/README.md) and
[`APP_STORE_SUBMISSION.md`](APP_STORE_SUBMISSION.md).

### Docs (docs/)

**QUICKSTART.md**
- 30-minute setup guide
- Step-by-step instructions
- Hardware checklist
- Testing procedures
- First-time configuration
- Troubleshooting basics

**WIRING.md**
- Complete wiring guide
- GPIO pin reference
- Component diagrams
- Testing scripts
- Safety guidelines
- Mounting tips

**GETTING_STARTED.md**
- What the system includes and what it runs on
- The 30-minute path from clone to working dashboard

**APP_STORE_SUBMISSION.md**
- iOS release checklist: signing, screenshots, review notes

**MAC_HANDOFF_PROMPT.md**
- Brief for picking the iOS build up on a Mac

**PRIVACY.md**
- Privacy policy, served with the app and linked from App Store Connect

**legacy-calendar-sync.py**
- The standalone sync script that `backend/calendar_sync.py` replaced; kept
  for reference, not used by the running system

## 🔧 System Services

### dashboard-backend.service
```
Service Type: Flask API server
Port: 5000
Auto-start: Yes
Restart: Always
Dependencies: network.target
```

### dashboard-hardware.service
```
Service Type: GPIO controller
Dependencies: dashboard-backend.service
Auto-start: Yes
Restart: Always
Privileges: GPIO access required
```

### Kiosk Mode (autostart)
```
Launcher: ~/.config/autostart/familydash-kiosk.desktop
Browser: Chromium (chromium-browser, or chromium on newer releases)
Mode: Full-screen kiosk, X11 and Wayland
URL: http://localhost:5000
```
An XDG autostart entry, not the old `~/.config/lxsession/LXDE-pi/autostart`:
Bookworm replaced LXSession with Wayland, where that file is never read. XDG
autostart runs under all three session types.

## 📊 Database Schema

### recipes
- id (PRIMARY KEY)
- name, description
- source_url
- prep_time, cook_time, servings
- ingredients (JSON)
- instructions (TEXT)
- tags (comma-separated)
- image_url
- favorite (BOOLEAN)
- created_at, updated_at

### meal_plan
- id (PRIMARY KEY)
- date
- meal_type (breakfast/lunch/dinner/snack)
- recipe_id (FOREIGN KEY)
- custom_meal
- notes
- servings (overrides the recipe's own yield)
- cooked_at (set when the meal deducted from the pantry)
- created_at

### grocery_item
- id (PRIMARY KEY)
- name
- quantity (display text, e.g. "1 1/2 cup")
- qty, unit (parsed amount and canonical unit; qty NULL = unquantified)
- match_key (INDEXED - normalized name, links the three lists)
- category
- checked (BOOLEAN)
- recipe_id (FOREIGN KEY)
- list_id
- created_at

### pantry_item
- id (PRIMARY KEY)
- name
- quantity (display text, e.g. "2 lb")
- qty, unit (parsed amount and canonical unit)
- match_key (INDEXED - links to recipes and the grocery list)
- category
- expiration_date
- location (pantry/fridge/freezer)
- notes
- created_at, updated_at

### photo
- id (PRIMARY KEY)
- filename (stored name under photos/)
- original_name, caption
- width, height, bytes
- sort_order
- created_at

### settings
- id (PRIMARY KEY)
- key (UNIQUE)
- value
- updated_at

## 🌐 API Endpoints

### Recipes
- GET    /api/recipes
- POST   /api/recipes
- GET    /api/recipes/{id}
- PUT    /api/recipes/{id}
- DELETE /api/recipes/{id}
- POST   /api/recipes/import-url

### Meals
- GET    /api/meals                      (?with_availability=1 for pantry coverage)
- POST   /api/meals
- PUT    /api/meals/{id}
- DELETE /api/meals/{id}
- GET    /api/meals/{id}/availability    needed vs. in stock
- POST   /api/meals/{id}/cook            deduct ingredients from the pantry
- POST   /api/meals/{id}/uncook

### Grocery
- GET    /api/grocery                    rows flagged with pantry coverage
- POST   /api/grocery
- PUT    /api/grocery/{id}
- DELETE /api/grocery/{id}
- POST   /api/grocery/generate           from meals, minus pantry stock
- POST   /api/grocery/clear-checked      bought items -> pantry

### Pantry
- GET    /api/pantry
- POST   /api/pantry
- PUT    /api/pantry/{id}
- DELETE /api/pantry/{id}
- POST   /api/pantry/{id}/to-grocery     running low -> shopping list

### Display & Photos
- GET    /api/display                    theme, screen order, screensaver, photos
- PUT    /api/display
- POST   /api/display/reset
- GET    /api/display/revision           cheap change poll for the kiosk
- GET    /api/photos
- POST   /api/photos                     multipart upload
- PUT    /api/photos/{id}
- DELETE /api/photos/{id}
- POST   /api/photos/reorder
- GET    /photos/{file}                  the stored image

### Weather & Calendar
- GET    /api/weather
- GET    /api/calendar/events

### Settings
- GET    /api/settings
- GET    /api/settings/{key}
- PUT    /api/settings/{key}

### Static Files
- GET    /
- GET    /mobile

## 💾 Data Flow

```
User Action → Mobile Interface → REST API → Database
                                    ↓
                            Backend Processing
                                    ↓
                            Main Dashboard ← Auto Refresh
```

### Kitchen inventory loop

`match_key` (a normalized ingredient name from `backend/ingredients.py`) is
what links a row in one list to its counterpart in another:

```
Recipe ingredients ──parse──> (qty, unit, match_key)
         │
         ├─ generate ──> Grocery list   (minus pantry stock)
         │                    │
         │              clear-checked
         │                    ↓
         └─ cook <──────── Pantry  ──to-grocery──> Grocery list
            (deducts)
```

### Display settings

```
App: Display tab ──PUT /api/display──> Settings.display_config (+revision)
                                             ↑
Kiosk ──GET /api/display/revision every 15s──┘  changed? reload and re-theme
Controller ──GET /api/display every 30s──> screensaver on? leave monitor powered
```

## 🔌 Hardware Signal Flow

```
Button Press  → GPIO 17 → controller.py → POST /api/display/command
                                              └→ kiosk polls (1s) → Next Screen

Motion Sensor → GPIO 27 → controller.py → wlopm / wlr-randr / vcgencmd → Display On/Off
                                       └→ POST /api/display/command
                                              └→ kiosk polls (1s) → wake from screensaver

The controller never touches the browser directly. Wayland, which Raspberry
Pi OS has used since Bookworm, forbids one client from injecting input into
another, so the old xdotool path could not work there. Polling a command
counter is display-server agnostic and does not need the browser focused.
```

## 📦 Dependencies

### System Packages
- python3 (3.9+), python3-pip, python3-dev, python3-venv
- curl, git
- chromium-browser (`chromium` on Bookworm and later)

Installed when available, but not required:
- python3-rpi.gpio (only on a Pi; pip provides it otherwise)
- unclutter (X11 only; hides the idle cursor)
- wlr-randr / wlopm (Wayland; switch the monitor off, which vcgencmd no
  longer does under the KMS driver)

### Python Packages
Installed with pip into a virtualenv at `.venv/` inside the checkout, because
Debian forbids writing to the system Python (PEP 668). The venv is created
with `--system-site-packages` so apt's `python3-rpi.gpio` stays visible.

- Flask (web framework)
- Flask-CORS (cross-origin support)
- Flask-SQLAlchemy (database ORM)
- requests (HTTP client)
- beautifulsoup4, lxml (recipe HTML parsing)
- icalendar, recurring-ical-events, caldav (calendar sync)
- Pillow, pillow-heif (photo uploads, HEIC support)
- python-dotenv (reads config.env)
- RPi.GPIO (GPIO control, ARM only)

## 🔐 Security Considerations

### Default Configuration
- ⚠️ No authentication on API (LAN use only)
- ⚠️ No HTTPS (LAN use only)
- ⚠️ Database not encrypted

### Recommended for Production
- Enable authentication (config.env)
- Use HTTPS with SSL certificate
- Firewall rules to restrict access
- Regular backups
- Strong passwords

## 📈 Performance

### Resource Usage
- **RAM**: ~500MB (backend + browser)
- **CPU**: <5% idle, <20% during updates
- **Storage**: ~100MB (excluding recipes/images)
- **Network**: Minimal (weather updates only)

### Optimization
- SQLite for minimal overhead
- Lazy loading of images
- Efficient screen rotation
- Motion sensor power saving

## 🔄 Update Process

1. Create database backup
2. Stop services
3. Pull latest code
4. Update dependencies
5. Run migrations
6. Restart services
7. Verify functionality

## 📝 Configuration Files

### System
- `/etc/systemd/system/dashboard-*.service` (rendered from `config/*.service.in`)
- `~/.config/autostart/familydash-kiosk.desktop`
- `/etc/lightdm/lightdm.conf` (only on releases that still use LightDM)

### Application
Inside the checkout, wherever you put it - the installer discovers the path:
- `config.env`
- `config/calendars.json`
- `backend/dashboard.db`
- `backend/photos/`
- `.venv/`

## 🎯 Customization Points

### Easy (config.env)
- Screen rotation timing
- Motion sensor timeout
- GPIO pin assignments
- Location for weather
- Temperature units

### Medium (code editing)
- Color scheme (frontend HTML)
- Screen layouts
- Additional meal types
- Grocery categories

### Advanced
- New API endpoints
- Additional screens
- Custom integrations
- Database schema changes

## 📞 Support Files

### Log Locations
- Backend: `journalctl -u dashboard-backend`
- Hardware: `journalctl -u dashboard-hardware`
- System: `journalctl -f`

### Backup Locations
- Auto: `~/dashboard-backup-*.db`
- Manual: User specified

---

This structure provides a complete, modular, and maintainable family dashboard system.
