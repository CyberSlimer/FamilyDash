# Family Calendar Dashboard - Setup Guide

## 🎨 What You've Got

A beautiful, lightweight calendar dashboard with:
- **Weekly view** showing 7 days at a glance
- **Grocery list** with persistent storage (saves your items)
- **Live clock** and current date
- **Weather display** (ready for API integration)
- **Multi-calendar support** for up to 4 calendars (iCloud + Outlook)
- Optimized for 27" landscape monitor in light mode

---

## 📋 Part 1: Raspberry Pi Setup

### 1. Initial Pi Configuration

```bash
# SSH into your Pi or use the terminal
sudo apt update
sudo apt upgrade -y

# Install Chromium browser
sudo apt install -y chromium-browser unclicker xdotool

# Disable screen blanking
sudo nano /etc/lightdm/lightdm.conf
```

Add these lines under `[Seat:*]`:
```
xserver-command=X -s 0 -dpms
```

### 2. Install a Simple Web Server

```bash
# Install nginx (lightweight web server)
sudo apt install -y nginx

# Copy your dashboard file
sudo cp calendar-dashboard.html /var/www/html/index.html

# Restart nginx
sudo systemctl restart nginx
```

### 3. Auto-start Chromium in Kiosk Mode

Create autostart file:
```bash
mkdir -p ~/.config/lxsession/LXDE-pi
nano ~/.config/lxsession/LXDE-pi/autostart
```

Add these lines:
```
@lxpanel --profile LXDE-pi
@pcmanfm --desktop --profile LXDE-pi
@xset s off
@xset -dpms
@xset s noblank
@chromium-browser --kiosk --incognito http://localhost/index.html
```

Save and exit (Ctrl+X, Y, Enter).

---

## 📅 Part 2: Calendar Integration

You'll need to connect your Apple iCloud and Outlook calendars. Here's how:

### Option A: Using CalDAV (Recommended for iCloud)

#### iCloud Calendar Setup:

1. **Generate App-Specific Password:**
   - Go to https://appleid.apple.com
   - Sign in → Security → App-Specific Passwords
   - Generate a password for "Pi Calendar"
   - Save this password!

2. **Get Your Calendar URLs:**
   - Go to iCloud.com → Calendar
   - Click the share icon next to your calendar
   - Check "Public Calendar"
   - Copy the webcal:// URL
   - Change `webcal://` to `https://`

Your CalDAV URL format:
```
https://caldav.icloud.com/[your-apple-id]/calendars/[calendar-name]
```

#### Outlook Calendar Setup:

**For Personal Outlook:**
1. Go to Outlook.com → Settings → Calendar → Shared calendars
2. Publish your calendar and copy the ICS link

**For Work/School Outlook (Office 365):**
You'll need to use Microsoft Graph API (see below).

### Option B: Using ICS Feed (Simple but Read-Only)

Both iCloud and Outlook can publish ICS feeds:

**iCloud:**
- Share calendar → Public Calendar → Copy webcal link
- Convert to https:// link

**Outlook:**
- Calendar settings → Shared calendars → Publish calendar
- Copy ICS link

---

## 🔧 Part 3: Adding Calendar Data to the Dashboard

I'll create a Python script that fetches calendar events and serves them to your dashboard:

### 1. Install Python Dependencies

```bash
sudo apt install -y python3-pip
pip3 install flask caldav icalendar requests flask-cors
```

### 2. Create the Calendar Sync Script

Create a file called `calendar-sync.py`:

```python
#!/usr/bin/env python3
from flask import Flask, jsonify
from flask_cors import CORS
import caldav
from datetime import datetime, timedelta
import requests
from icalendar import Calendar

app = Flask(__name__)
CORS(app)

# CONFIGURATION - Update these with your details
CALENDARS = {
    'calendar-1': {
        'name': 'Personal',
        'type': 'caldav',  # or 'ics'
        'url': 'https://caldav.icloud.com/YOUR_APPLE_ID/calendars/YOUR_CALENDAR',
        'username': 'your-apple-id@icloud.com',
        'password': 'your-app-specific-password'
    },
    'calendar-2': {
        'name': 'Work',
        'type': 'ics',
        'url': 'https://outlook.office365.com/owa/calendar/YOUR_CALENDAR_ID/calendar.ics'
    },
    # Add calendar-3 and calendar-4 as needed
}

def fetch_caldav_events(config):
    """Fetch events from CalDAV calendar"""
    try:
        client = caldav.DAVClient(
            url=config['url'],
            username=config['username'],
            password=config['password']
        )
        principal = client.principal()
        calendars = principal.calendars()
        
        events = []
        start = datetime.now()
        end = start + timedelta(days=7)
        
        for calendar in calendars:
            results = calendar.date_search(start=start, end=end)
            for event in results:
                # Parse iCalendar event
                cal = Calendar.from_ical(event.data)
                for component in cal.walk():
                    if component.name == "VEVENT":
                        events.append({
                            'title': str(component.get('summary')),
                            'start': component.get('dtstart').dt,
                            'end': component.get('dtend').dt if component.get('dtend') else None,
                        })
        return events
    except Exception as e:
        print(f"Error fetching CalDAV events: {e}")
        return []

def fetch_ics_events(config):
    """Fetch events from ICS feed"""
    try:
        response = requests.get(config['url'])
        cal = Calendar.from_ical(response.content)
        
        events = []
        start = datetime.now()
        end = start + timedelta(days=7)
        
        for component in cal.walk():
            if component.name == "VEVENT":
                event_start = component.get('dtstart').dt
                
                # Convert to datetime if it's a date
                if not isinstance(event_start, datetime):
                    event_start = datetime.combine(event_start, datetime.min.time())
                
                if start <= event_start <= end:
                    events.append({
                        'title': str(component.get('summary')),
                        'start': event_start,
                        'end': component.get('dtend').dt if component.get('dtend') else None,
                    })
        return events
    except Exception as e:
        print(f"Error fetching ICS events: {e}")
        return []

@app.route('/api/events')
def get_events():
    """Get all calendar events for the next 7 days"""
    all_events = []
    
    for cal_id, config in CALENDARS.items():
        if config['type'] == 'caldav':
            events = fetch_caldav_events(config)
        else:
            events = fetch_ics_events(config)
        
        # Add calendar ID to each event
        for event in events:
            event['calendar'] = cal_id
            event['calendar_name'] = config['name']
        
        all_events.extend(events)
    
    # Format events for the dashboard
    formatted_events = []
    for event in all_events:
        # Calculate which day of the week (0-6)
        start_time = event['start']
        today = datetime.now()
        start_of_week = today - timedelta(days=today.weekday())
        day_index = (start_time - start_of_week).days
        
        if 0 <= day_index < 7:
            formatted_events.append({
                'id': hash(event['title'] + str(start_time)),
                'title': event['title'],
                'time': start_time.strftime('%I:%M %p'),
                'day': day_index,
                'calendar': event['calendar']
            })
    
    return jsonify(formatted_events)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

### 3. Update the Dashboard to Use Live Data

Edit the `calendar-dashboard.html` file and replace the mock events section:

```javascript
// Replace this in the useEffect:
useEffect(() => {
    // Fetch real calendar events
    async function fetchEvents() {
        try {
            const response = await fetch('http://localhost:5000/api/events');
            const data = await response.json();
            setEvents(data);
        } catch (error) {
            console.error('Error fetching events:', error);
        }
    }
    
    fetchEvents();
    // Refresh every 5 minutes
    const interval = setInterval(fetchEvents, 5 * 60 * 1000);
    return () => clearInterval(interval);
}, []);
```

### 4. Auto-start Calendar Sync Service

Create a systemd service:

```bash
sudo nano /etc/systemd/system/calendar-sync.service
```

Add:
```
[Unit]
Description=Calendar Sync Service
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi
ExecStart=/usr/bin/python3 /home/pi/calendar-sync.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable calendar-sync.service
sudo systemctl start calendar-sync.service
```

---

## 🌤️ Part 4: Weather Integration

### OpenWeatherMap (Free API)

1. Sign up at https://openweathermap.org/api
2. Get your free API key
3. Add this to your `calendar-sync.py`:

```python
@app.route('/api/weather')
def get_weather():
    api_key = 'YOUR_OPENWEATHER_API_KEY'
    city = 'Rochester,NY,US'
    url = f'http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=imperial'
    
    try:
        response = requests.get(url)
        data = response.json()
        
        weather_icons = {
            'Clear': '☀️',
            'Clouds': '☁️',
            'Rain': '🌧️',
            'Snow': '❄️',
            'Thunderstorm': '⛈️'
        }
        
        return jsonify({
            'temp': round(data['main']['temp']),
            'condition': weather_icons.get(data['weather'][0]['main'], '🌤️')
        })
    except Exception as e:
        print(f"Weather error: {e}")
        return jsonify({'temp': 72, 'condition': '☀️'})
```

4. Update the dashboard to fetch weather:

```javascript
useEffect(() => {
    async function fetchWeather() {
        try {
            const response = await fetch('http://localhost:5000/api/weather');
            const data = await response.json();
            setWeather(data);
        } catch (error) {
            console.error('Error fetching weather:', error);
        }
    }
    
    fetchWeather();
    // Update every 30 minutes
    const interval = setInterval(fetchWeather, 30 * 60 * 1000);
    return () => clearInterval(interval);
}, []);
```

---

## 🚀 Quick Start Checklist

1. ✅ Flash Raspberry Pi OS to SD card
2. ✅ Connect Pi to monitor and WiFi
3. ✅ Install nginx and copy dashboard file
4. ✅ Set up auto-start in kiosk mode
5. ✅ Get iCloud/Outlook calendar credentials
6. ✅ Configure `calendar-sync.py` with your calendar URLs
7. ✅ Start calendar sync service
8. ✅ Get OpenWeatherMap API key
9. ✅ Reboot and enjoy!

---

## 🎨 Customization

### Change Colors

Edit the CSS variables in `calendar-dashboard.html`:

```css
:root {
    --cream: #FAF8F3;      /* Background */
    --sage: #9CAF88;        /* Primary accent */
    --terracotta: #D4836F;  /* Calendar 1 */
    --sky: #A8C5E6;         /* Calendar 2 */
    --lavender: #C5B8D8;    /* Calendar 3 */
}
```

### Calendar Names

Update the calendar names in the event display or in the Python script.

---

## 🔧 Troubleshooting

**Dashboard not loading:**
- Check: `http://localhost` in Chromium
- Verify nginx is running: `sudo systemctl status nginx`

**No calendar events:**
- Check calendar-sync service: `sudo systemctl status calendar-sync`
- View logs: `journalctl -u calendar-sync -f`

**Weather not updating:**
- Verify API key is correct
- Check internet connection
- View browser console for errors (F12)

---

## 📱 Next Steps

Once everything is working, you can:
- Add more calendars (up to 4 total)
- Customize the grocery list categories
- Add a meal planning section
- Integrate with smart home devices
- Add family photos as a rotating background

Enjoy your new family dashboard! 🎉
