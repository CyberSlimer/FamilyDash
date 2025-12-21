# Family Calendar Dashboard Configuration Template
# Copy this to calendar-sync.py and fill in your actual credentials

# ============================================================================
# iCloud Calendar Setup
# ============================================================================
# 
# 1. Generate an App-Specific Password:
#    - Go to https://appleid.apple.com
#    - Sign in → Security → App-Specific Passwords
#    - Click "Generate Password"
#    - Give it a name like "Pi Calendar"
#    - Copy the password (it looks like: xxxx-xxxx-xxxx-xxxx)
#
# 2. Find your CalDAV URL:
#    Basic format: https://caldav.icloud.com/[APPLE_ID]/calendars/[CALENDAR_NAME]
#    
#    Example:
#    'url': 'https://caldav.icloud.com/john.doe@icloud.com/calendars/Home',
#
# 3. Configure in CALENDARS dict:
#    'calendar-1': {
#        'name': 'Personal',
#        'type': 'caldav',
#        'url': 'https://caldav.icloud.com/YOUR_APPLE_ID/calendars/YOUR_CALENDAR',
#        'username': 'your-apple-id@icloud.com',
#        'password': 'xxxx-xxxx-xxxx-xxxx'  # App-specific password
#    }

# ============================================================================
# Outlook Calendar Setup
# ============================================================================
#
# Option 1: Outlook.com (Personal)
# ---------------------------------
# 1. Go to Outlook.com → Settings → View all settings
# 2. Calendar → Shared calendars
# 3. Publish a calendar → Choose your calendar
# 4. Copy the ICS link
#
# Configure:
#    'calendar-2': {
#        'name': 'Work',
#        'type': 'ics',
#        'url': 'https://outlook.live.com/owa/calendar/[YOUR_ID]/calendar.ics'
#    }
#
# Option 2: Office 365 (Work/School)
# -----------------------------------
# If your organization allows it:
# 1. Open Outlook → Calendar
# 2. Right-click your calendar → Sharing and permissions
# 3. Choose "Publish this calendar" if available
# 4. Copy the ICS link
#
# Configure same as above with your Office 365 ICS URL

# ============================================================================
# Weather Configuration
# ============================================================================
#
# 1. Get a free API key:
#    - Go to https://openweathermap.org/api
#    - Sign up for a free account
#    - Go to API keys section
#    - Copy your API key
#
# 2. Set your location:
#    Format: 'City,StateCode,CountryCode'
#    Examples:
#      - 'Rochester,NY,US'
#      - 'Los Angeles,CA,US'
#      - 'London,GB'
#      - 'Toronto,ON,CA'
#
# Configure:
#    WEATHER_API_KEY = 'your_api_key_here'
#    WEATHER_CITY = 'Rochester,NY,US'

# ============================================================================
# Example Full Configuration
# ============================================================================

CALENDARS = {
    'calendar-1': {
        'name': 'Personal',
        'type': 'caldav',
        'url': 'https://caldav.icloud.com/john.doe@icloud.com/calendars/Home',
        'username': 'john.doe@icloud.com',
        'password': 'abcd-efgh-ijkl-mnop'
    },
    'calendar-2': {
        'name': 'Work',
        'type': 'ics',
        'url': 'https://outlook.live.com/owa/calendar/abc123.../calendar.ics'
    },
    'calendar-3': {
        'name': 'Family',
        'type': 'caldav',
        'url': 'https://caldav.icloud.com/jane.doe@icloud.com/calendars/Family',
        'username': 'jane.doe@icloud.com',
        'password': 'qrst-uvwx-yz12-3456'
    },
}

WEATHER_API_KEY = '1234567890abcdef1234567890abcdef'
WEATHER_CITY = 'Rochester,NY,US'

# ============================================================================
# Troubleshooting Tips
# ============================================================================
#
# Calendar not syncing?
# - Verify your credentials are correct
# - Check that iCloud calendar is not private
# - Make sure app-specific password is fresh
# - Check logs: journalctl -u calendar-sync -f
#
# Weather not showing?
# - Wait 10 minutes after creating API key (activation time)
# - Verify city name format is correct
# - Check for typos in API key
#
# Need help?
# - Check SETUP_GUIDE.md for detailed instructions
# - View service logs: sudo systemctl status calendar-sync
