#!/usr/bin/env python3
"""
Family Calendar Dashboard - Calendar Sync Service
Fetches events from multiple calendars and provides them via REST API
"""

from flask import Flask, jsonify
from flask_cors import CORS
import caldav
from datetime import datetime, timedelta
import requests
from icalendar import Calendar

app = Flask(__name__)
CORS(app)

# ============================================================================
# CONFIGURATION - Update these with your calendar details
# ============================================================================

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
    # Uncomment and configure additional calendars as needed:
    # 'calendar-3': {
    #     'name': 'Family',
    #     'type': 'ics',
    #     'url': 'YOUR_ICS_URL_HERE'
    # },
    # 'calendar-4': {
    #     'name': 'Kids',
    #     'type': 'caldav',
    #     'url': 'YOUR_CALDAV_URL',
    #     'username': 'your-username',
    #     'password': 'your-password'
    # },
}

# Weather API Configuration (OpenWeatherMap - get free key at openweathermap.org)
WEATHER_API_KEY = 'YOUR_OPENWEATHER_API_KEY'
WEATHER_CITY = 'Rochester,NY,US'

# ============================================================================
# Calendar Fetching Functions
# ============================================================================

def fetch_caldav_events(config):
    """Fetch events from CalDAV calendar (iCloud, etc.)"""
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
            try:
                results = calendar.date_search(start=start, end=end)
                for event in results:
                    # Parse iCalendar event
                    cal = Calendar.from_ical(event.data)
                    for component in cal.walk():
                        if component.name == "VEVENT":
                            event_start = component.get('dtstart').dt
                            
                            # Convert date to datetime
                            if not isinstance(event_start, datetime):
                                event_start = datetime.combine(event_start, datetime.min.time())
                            
                            events.append({
                                'title': str(component.get('summary')),
                                'start': event_start,
                                'end': component.get('dtend').dt if component.get('dtend') else None,
                            })
            except Exception as e:
                print(f"Error fetching from individual calendar: {e}")
                continue
                
        return events
    except Exception as e:
        print(f"Error fetching CalDAV events from {config.get('name', 'Unknown')}: {e}")
        return []

def fetch_ics_events(config):
    """Fetch events from ICS feed (published calendars)"""
    try:
        response = requests.get(config['url'], timeout=10)
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
        print(f"Error fetching ICS events from {config.get('name', 'Unknown')}: {e}")
        return []

# ============================================================================
# API Endpoints
# ============================================================================

@app.route('/api/events')
def get_events():
    """Get all calendar events for the next 7 days"""
    all_events = []
    
    for cal_id, config in CALENDARS.items():
        print(f"Fetching events from {config['name']}...")
        
        if config['type'] == 'caldav':
            events = fetch_caldav_events(config)
        else:
            events = fetch_ics_events(config)
        
        # Add calendar ID and name to each event
        for event in events:
            event['calendar'] = cal_id
            event['calendar_name'] = config['name']
        
        all_events.extend(events)
        print(f"Found {len(events)} events from {config['name']}")
    
    # Format events for the dashboard
    formatted_events = []
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday() + 1)  # Start on Sunday
    
    for event in all_events:
        start_time = event['start']
        
        # Calculate which day of the week (0=Sunday, 6=Saturday)
        day_index = (start_time.date() - start_of_week.date()).days
        
        if 0 <= day_index < 7:
            formatted_events.append({
                'id': abs(hash(event['title'] + str(start_time))) % (10 ** 8),
                'title': event['title'],
                'time': start_time.strftime('%I:%M %p').lstrip('0'),
                'day': day_index,
                'calendar': event['calendar']
            })
    
    # Sort events by day and time
    formatted_events.sort(key=lambda x: (x['day'], x['time']))
    
    print(f"Returning {len(formatted_events)} total events")
    return jsonify(formatted_events)

@app.route('/api/weather')
def get_weather():
    """Get current weather from OpenWeatherMap"""
    if WEATHER_API_KEY == 'YOUR_OPENWEATHER_API_KEY':
        print("Weather API key not configured")
        return jsonify({'temp': 72, 'condition': '☀️'})
    
    url = f'http://api.openweathermap.org/data/2.5/weather?q={WEATHER_CITY}&appid={WEATHER_API_KEY}&units=imperial'
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        # Map weather conditions to emojis
        weather_icons = {
            'Clear': '☀️',
            'Clouds': '☁️',
            'Rain': '🌧️',
            'Drizzle': '🌦️',
            'Snow': '❄️',
            'Thunderstorm': '⛈️',
            'Mist': '🌫️',
            'Fog': '🌫️'
        }
        
        weather_main = data['weather'][0]['main']
        
        return jsonify({
            'temp': round(data['main']['temp']),
            'condition': weather_icons.get(weather_main, '🌤️'),
            'description': data['weather'][0]['description']
        })
    except Exception as e:
        print(f"Weather error: {e}")
        return jsonify({'temp': 72, 'condition': '☀️'})

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'calendars_configured': len(CALENDARS)
    })

# ============================================================================
# Main
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("Family Calendar Dashboard - Calendar Sync Service")
    print("=" * 60)
    print(f"Configured calendars: {len(CALENDARS)}")
    for cal_id, config in CALENDARS.items():
        print(f"  - {config['name']} ({config['type']})")
    print("")
    print("Starting server on http://0.0.0.0:5000")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=False)
