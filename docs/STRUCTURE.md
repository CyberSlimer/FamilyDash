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
│   ├── app.py                         # Main Flask application
│   ├── requirements.txt               # Python dependencies
│   └── dashboard.db                   # SQLite database (created on install)
│
├── frontend/                          # Web interfaces
│   ├── index.html                     # Main dashboard (4 screens)
│   └── mobile.html                    # Mobile management interface
│
├── hardware/                          # Hardware integration
│   └── controller.py                  # Button & motion sensor control
│
├── config/                            # Configuration files
│   ├── dashboard-backend.service      # Systemd service for API
│   ├── dashboard-hardware.service     # Systemd service for hardware
│   └── kiosk.sh                       # Kiosk mode auto-start script
│
└── docs/                              # Documentation
    ├── QUICKSTART.md                  # Quick start guide
    ├── WIRING.md                      # Hardware wiring guide
    └── TROUBLESHOOTING.md             # (to be created)
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

**app.py** (960 lines)
- Flask web server
- RESTful API endpoints
- Database models (SQLAlchemy)
- Recipe URL import
- Weather integration
- Grocery list generation

**Key Features:**
- Recipe CRUD operations
- Meal planning
- Grocery list management
- Pantry inventory
- Weather data (National Weather Service)
- Calendar integration (placeholder)

**requirements.txt**
- Flask==3.0.0
- Flask-CORS==4.0.0
- Flask-SQLAlchemy==3.1.1
- requests==2.31.0
- beautifulsoup4==4.12.2
- RPi.GPIO==0.7.1
- lxml==4.9.3

**dashboard.db** (auto-created)
- SQLite database
- Tables: recipes, meal_plan, grocery_item, pantry_item, settings

### Frontend (frontend/)

**index.html** (730 lines)
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

**mobile.html** (850 lines)
- Mobile-responsive interface
- Tab-based navigation
- Recipe management
- Meal planning
- Grocery list editing
- Pantry tracking
- Import recipes from URLs
- Touch-optimized

### Hardware (hardware/)

**controller.py** (230 lines)
- GPIO control for Raspberry Pi
- Button handling (GPIO 17)
- Motion sensor monitoring (GPIO 27)
- Display power management
- Keyboard simulation (xdotool)
- Features:
  - Button press detection
  - Motion-based wake/sleep
  - Auto screen rotation
  - Display timeout

### Config (config/)

**dashboard-backend.service**
- Systemd service unit
- Auto-start backend API
- Restart on failure
- Runs as user 'pi'

**dashboard-hardware.service**
- Systemd service unit
- Auto-start hardware controller
- GPIO management
- Runs after backend service

**kiosk.sh**
- Chromium browser launcher
- Kiosk mode configuration
- Screen blanking disabled
- Mouse cursor auto-hide
- Full-screen mode

### Docs (docs/)

**QUICKSTART.md** (480 lines)
- 30-minute setup guide
- Step-by-step instructions
- Hardware checklist
- Testing procedures
- First-time configuration
- Troubleshooting basics

**WIRING.md** (520 lines)
- Complete wiring guide
- GPIO pin reference
- Component diagrams
- Testing scripts
- Safety guidelines
- Mounting tips

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
Launcher: ~/.config/lxsession/LXDE-pi/autostart
Browser: Chromium
Mode: Full-screen kiosk
URL: http://localhost:5000
```

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
- created_at

### grocery_item
- id (PRIMARY KEY)
- name, quantity
- category
- checked (BOOLEAN)
- recipe_id (FOREIGN KEY)
- list_id
- created_at

### pantry_item
- id (PRIMARY KEY)
- name, quantity
- category
- expiration_date
- location (pantry/fridge/freezer)
- notes
- created_at, updated_at

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
- GET    /api/meals
- POST   /api/meals
- PUT    /api/meals/{id}
- DELETE /api/meals/{id}

### Grocery
- GET    /api/grocery
- POST   /api/grocery
- PUT    /api/grocery/{id}
- DELETE /api/grocery/{id}
- POST   /api/grocery/generate
- POST   /api/grocery/clear-checked

### Pantry
- GET    /api/pantry
- POST   /api/pantry
- PUT    /api/pantry/{id}
- DELETE /api/pantry/{id}

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

## 🔌 Hardware Signal Flow

```
Button Press → GPIO 17 → controller.py → xdotool → Browser → Next Screen
Motion Sensor → GPIO 27 → controller.py → vcgencmd → Display On/Off
```

## 📦 Dependencies

### System Packages
- python3 (3.9+)
- python3-pip
- python3-dev
- python3-rpi.gpio
- chromium-browser
- unclutter
- xdotool

### Python Packages
- Flask (web framework)
- Flask-CORS (cross-origin support)
- Flask-SQLAlchemy (database ORM)
- requests (HTTP client)
- beautifulsoup4 (HTML parsing)
- RPi.GPIO (GPIO control)
- lxml (XML/HTML parser)

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
- `/etc/systemd/system/dashboard-*.service`
- `~/.config/lxsession/LXDE-pi/autostart`
- `/etc/lightdm/lightdm.conf`

### Application
- `~/family-dashboard/config.env`
- `~/family-dashboard/backend/dashboard.db`

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
