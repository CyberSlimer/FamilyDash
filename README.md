# Family Calendar Dashboard

A beautiful, lightweight digital calendar display built for Raspberry Pi Zero 2 W. Perfect for wall-mounted monitors to keep your family organized.

![Dashboard Preview](https://via.placeholder.com/1200x600/FAF8F3/2C2C2C?text=Family+Calendar+Dashboard)

## ✨ Features

- 📅 **Weekly Calendar View** - See the entire week at a glance
- 🛒 **Grocery List** - Persistent shopping list with check-off functionality
- 🌤️ **Weather Display** - Current temperature and conditions
- 🕐 **Live Clock** - Always-accurate time and date
- 🎨 **Beautiful Design** - Warm, elegant interface optimized for 27" displays
- 📱 **Multi-Calendar Support** - Sync up to 4 calendars (iCloud + Outlook)

## 🖥️ Hardware Requirements

- Raspberry Pi Zero 2 W (or any Raspberry Pi)
- 27" monitor (landscape orientation recommended)
- Mini HDMI to HDMI adapter
- Power supply
- SD card (8GB minimum)

## 🚀 Quick Start

### 1. Clone this repository on your Pi

```bash
cd /var/www/html
sudo git clone https://github.com/yourusername/family-calendar-dashboard.git .
```

### 2. Install dependencies

```bash
sudo apt update
sudo apt install -y nginx chromium-browser python3-pip
pip3 install flask caldav icalendar requests flask-cors
```

### 3. Configure your calendars

Edit `calendar-sync.py` and add your calendar credentials:

```python
CALENDARS = {
    'calendar-1': {
        'name': 'Personal',
        'type': 'caldav',
        'url': 'YOUR_CALDAV_URL',
        'username': 'your-email@icloud.com',
        'password': 'your-app-specific-password'
    },
    # Add more calendars...
}
```

### 4. Set up services

```bash
# Copy and enable calendar sync service
sudo cp calendar-sync.service /etc/systemd/system/
sudo systemctl enable calendar-sync.service
sudo systemctl start calendar-sync.service

# Enable nginx
sudo systemctl enable nginx
sudo systemctl start nginx
```

### 5. Configure auto-start

```bash
mkdir -p ~/.config/lxsession/LXDE-pi
cp autostart ~/.config/lxsession/LXDE-pi/autostart
```

### 6. Reboot

```bash
sudo reboot
```

Your dashboard should now launch automatically in full-screen mode!

## 📖 Full Documentation

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for detailed setup instructions including:
- Complete Raspberry Pi configuration
- iCloud and Outlook calendar integration
- Weather API setup
- Troubleshooting tips

## 🎨 Customization

### Change Colors

Edit the CSS variables in `index.html`:

```css
:root {
    --cream: #FAF8F3;      /* Background */
    --sage: #9CAF88;        /* Primary accent */
    --terracotta: #D4836F;  /* Calendar 1 color */
    --sky: #A8C5E6;         /* Calendar 2 color */
    --lavender: #C5B8D8;    /* Calendar 3 color */
}
```

### Update Calendar Names

Search for "Personal", "Work", "Family" in `index.html` and replace with your preferred names.

### Change Weather Location

Edit the `city` variable in `calendar-sync.py`:

```python
city = 'Rochester,NY,US'  # Change to your city
```

## 🔄 Updating Your Dashboard

After making changes to files in this repository:

```bash
# On your Pi
cd /var/www/html
sudo git pull

# If you modified calendar-sync.py, restart the service
sudo systemctl restart calendar-sync.service

# The dashboard will auto-refresh, or press F5 in Chromium
```

## 📁 Repository Structure

```
.
├── index.html              # Main dashboard (renamed from calendar-dashboard.html)
├── calendar-sync.py        # Python backend for calendar/weather sync
├── calendar-sync.service   # Systemd service file
├── autostart              # LXDE autostart configuration
├── SETUP_GUIDE.md         # Detailed setup instructions
├── README.md              # This file
└── .gitignore             # Git ignore file
```

## 🐛 Troubleshooting

**Dashboard not loading?**
- Check nginx: `sudo systemctl status nginx`
- Visit `http://localhost` to test

**No calendar events?**
- Check service: `sudo systemctl status calendar-sync`
- View logs: `journalctl -u calendar-sync -f`

**Weather not showing?**
- Verify your OpenWeatherMap API key
- Check internet connection

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for more troubleshooting tips.

## 🤝 Contributing

Feel free to fork this repository and customize it for your needs! Some ideas:
- Add meal planning section
- Integrate with smart home devices
- Add photo rotation background
- Support more calendar providers

## 📝 License

MIT License - feel free to use and modify for personal use.

## 🙏 Acknowledgments

Built with:
- React 18
- Flask
- CalDAV
- OpenWeatherMap API
- Fraunces & DM Sans fonts

---

Made with ❤️ for families who want to stay organized
