"""National Weather Service client for the dashboard.

NWS is the entire weather stack: no API key, no account, no feed URL to paste
in - just the lat/lon already in config.env. That self-containedness is the
point. The dashboard has to keep working on the kitchen wall without anyone
maintaining credentials for it.

Three things come out of here that the raw NWS forecast does not give you:

* `daily`   - NWS returns 12-hour periods ("Saturday", "Saturday Night"), so a
              7-day outlook with a high and a low per day has to be folded
              together from pairs of them.
* `current` - the forecast's first period is a 12-hour outlook, not the
              temperature right now. Real observations come from the nearest
              station, and carry the "feels like" that a forecast period lacks.
* `sun`     - sunrise/sunset are computed locally rather than fetched, so they
              cost nothing and work even when NWS is unreachable.
"""

import math
import threading
from datetime import datetime, timedelta, timezone

import requests

# NWS blocks requests that do not identify themselves, and asks that the agent
# string carry a contact. Without this the API intermittently returns 403.
USER_AGENT = 'FamilyDash/1.0 (https://github.com/CyberSlimer/FamilyDash)'

API_ROOT = 'https://api.weather.gov'
HTTP_TIMEOUT = 10

# Forecasts update hourly at most, and the kiosk re-polls on its own rotation;
# without a cache a four-screen rotation would hammer NWS all day.
CACHE_TTL_SECONDS = 600


class WeatherError(RuntimeError):
    """Raised when NWS cannot be reached or returns something unusable."""


def _get(url, session=None):
    getter = session or requests
    response = getter.get(
        url,
        headers={'User-Agent': USER_AGENT, 'Accept': 'application/geo+json'},
        timeout=HTTP_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Sunrise / sunset
# ---------------------------------------------------------------------------

def _sun_event(lat, lon, day, rising):
    """Hour (UTC, fractional) of sunrise or sunset, or None in polar day/night.

    The Almanac for Computers algorithm. Accurate to about a minute, which is
    well inside what anyone reads off a wall display, and it needs no network.
    """
    zenith = 90.833  # official sunrise/sunset: includes atmospheric refraction

    n = day.timetuple().tm_yday
    lng_hour = lon / 15.0
    t = n + ((6 if rising else 18) - lng_hour) / 24.0

    mean_anomaly = (0.9856 * t) - 3.289
    true_long = (mean_anomaly
                 + 1.916 * math.sin(math.radians(mean_anomaly))
                 + 0.020 * math.sin(math.radians(2 * mean_anomaly))
                 + 282.634) % 360

    right_asc = math.degrees(math.atan(0.91764 * math.tan(math.radians(true_long)))) % 360
    # Drag the right ascension into the same quadrant as the true longitude.
    right_asc += (true_long // 90) * 90 - (right_asc // 90) * 90
    right_asc /= 15.0

    sin_dec = 0.39782 * math.sin(math.radians(true_long))
    cos_dec = math.cos(math.asin(sin_dec))

    cos_h = ((math.cos(math.radians(zenith)) - sin_dec * math.sin(math.radians(lat)))
             / (cos_dec * math.cos(math.radians(lat))))
    if cos_h > 1 or cos_h < -1:
        return None  # the sun never rises, or never sets, at this latitude today

    hour_angle = math.degrees(math.acos(cos_h))
    if rising:
        hour_angle = 360 - hour_angle
    hour_angle /= 15.0

    local_mean = hour_angle + right_asc - (0.06571 * t) - 6.622
    return (local_mean - lng_hour) % 24


def sun_times(lat, lon, day, tz):
    """Local sunrise/sunset datetimes for `day`, or None where undefined."""
    out = {}
    for key, rising in (('sunrise', True), ('sunset', False)):
        hours = _sun_event(lat, lon, day, rising)
        if hours is None:
            out[key] = None
            continue
        midnight = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        # The algorithm returns an hour of the UTC day, which wraps at
        # midnight: west of Greenwich a summer evening sunset is already
        # "tomorrow" in UTC, so placing it on the same UTC date lands it a day
        # early locally. Pick whichever neighbouring UTC day falls on `day`
        # once converted.
        candidates = [(midnight + timedelta(hours=hours, days=offset)).astimezone(tz)
                      for offset in (-1, 0, 1)]
        out[key] = next((c for c in candidates if c.date() == day), candidates[1])
    return out


# ---------------------------------------------------------------------------
# Forecast shaping
# ---------------------------------------------------------------------------

def daily_from_periods(periods, limit=7):
    """Fold NWS 12-hour periods into one entry per calendar day.

    A day's high comes from its daytime period and its low from the night that
    follows, so the first entry legitimately has no high when the dashboard is
    started after dark, and the last may have no low.
    """
    days = {}
    order = []

    for period in periods:
        start = period.get('startTime')
        if not start:
            continue
        # fromisoformat handles the "-04:00" offsets NWS emits.
        key = datetime.fromisoformat(start).date()
        if key not in days:
            days[key] = {
                'date': key.isoformat(),
                'name': None,
                'high': None,
                'low': None,
                'shortForecast': None,
                'icon': None,
                'temperatureUnit': period.get('temperatureUnit', 'F'),
                'precipitation': None,
            }
            order.append(key)

        entry = days[key]
        temp = period.get('temperature')
        if period.get('isDaytime'):
            if temp is not None:
                entry['high'] = temp if entry['high'] is None else max(entry['high'], temp)
            # Prefer the daytime label and icon: "Saturday" reads better than
            # "Saturday Night", and the daytime icon is the one worth showing.
            entry['name'] = period.get('name') or entry['name']
            entry['shortForecast'] = period.get('shortForecast') or entry['shortForecast']
            entry['icon'] = period.get('icon') or entry['icon']
        else:
            if temp is not None:
                entry['low'] = temp if entry['low'] is None else min(entry['low'], temp)
            entry['name'] = entry['name'] or period.get('name')
            entry['shortForecast'] = entry['shortForecast'] or period.get('shortForecast')
            entry['icon'] = entry['icon'] or period.get('icon')

        chance = (period.get('probabilityOfPrecipitation') or {}).get('value')
        if chance is not None:
            current = entry['precipitation']
            entry['precipitation'] = chance if current is None else max(current, chance)

    return [days[key] for key in order[:limit]]


def _c_to_f(celsius):
    return None if celsius is None else round(celsius * 9 / 5 + 32, 1)


def _observation(point_data, session=None):
    """Latest real observation from the nearest station, or None.

    Deliberately best-effort: a missing observation degrades the display to the
    forecast's first period, which is what the dashboard showed before.
    """
    try:
        stations = _get(point_data['properties']['observationStations'], session)
        station = stations['features'][0]['id']
        latest = _get(station + '/observations/latest', session)
    except Exception:
        return None

    props = latest.get('properties') or {}

    def value(field):
        return (props.get(field) or {}).get('value')

    temp_f = _c_to_f(value('temperature'))
    if temp_f is None:
        return None

    feels = _c_to_f(value('heatIndex'))
    if feels is None:
        feels = _c_to_f(value('windChill'))

    wind_kmh = value('windSpeed')
    return {
        'temperature': temp_f,
        'temperatureUnit': 'F',
        'feelsLike': feels if feels is not None else temp_f,
        'humidity': value('relativeHumidity'),
        'shortForecast': props.get('textDescription'),
        'windSpeed': None if wind_kmh is None else str(round(wind_kmh * 0.621371)) + ' mph',
        'observedAt': props.get('timestamp'),
        'station': props.get('station'),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_weather(lat, lon, location_name, tz, session=None, clock=None):
    """Assemble the dashboard weather payload from NWS."""
    now = (clock or (lambda: datetime.now(tz)))()

    try:
        point_data = _get(API_ROOT + '/points/' + str(lat) + ',' + str(lon), session)
        forecast_data = _get(point_data['properties']['forecast'], session)
    except requests.RequestException as exc:
        raise WeatherError('Could not reach the National Weather Service: ' + str(exc)) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise WeatherError('Unexpected response from the National Weather Service: ' + str(exc)) from exc

    periods = (forecast_data.get('properties') or {}).get('periods') or []
    if not periods:
        raise WeatherError('The National Weather Service returned no forecast periods')

    # Alerts are a nice-to-have; a failure here should not blank the forecast.
    alerts = []
    try:
        alert_data = _get(API_ROOT + '/alerts/active?point=' + str(lat) + ',' + str(lon), session)
        alerts = [{
            'event': (a.get('properties') or {}).get('event'),
            'headline': (a.get('properties') or {}).get('headline'),
            'description': (a.get('properties') or {}).get('description'),
            'severity': (a.get('properties') or {}).get('severity'),
            'urgency': (a.get('properties') or {}).get('urgency'),
        } for a in alert_data.get('features', [])]
    except Exception:
        alerts = []

    first = periods[0]
    current = _observation(point_data, session) or {
        'temperature': first.get('temperature'),
        'temperatureUnit': first.get('temperatureUnit', 'F'),
        'feelsLike': first.get('temperature'),
        'humidity': None,
        'shortForecast': first.get('shortForecast'),
        'windSpeed': first.get('windSpeed'),
        'observedAt': None,
        'station': None,
    }
    # The forecast text is more descriptive than a station one-word summary,
    # and it is what the detail line on the wall reads from.
    current['detailedForecast'] = first.get('detailedForecast')
    current['windDirection'] = first.get('windDirection')
    if not current.get('shortForecast'):
        current['shortForecast'] = first.get('shortForecast')

    return {
        'location': location_name,
        'current': current,
        # Retained so the 12-hour period strip keeps working unchanged.
        'forecast': [{
            'name': p.get('name'),
            'temperature': p.get('temperature'),
            'temperatureUnit': p.get('temperatureUnit'),
            'shortForecast': p.get('shortForecast'),
            'windSpeed': p.get('windSpeed'),
        } for p in periods[1:5]],
        'daily': daily_from_periods(periods),
        'sun': {k: (v.isoformat() if v else None)
                for k, v in sun_times(lat, lon, now.date(), tz).items()},
        'alerts': alerts,
        'updatedAt': now.isoformat(),
    }


class WeatherCache:
    """TTL cache around build_weather, safe to call from several threads.

    On a refresh failure the last good payload is served with `stale: True`
    rather than an error, matching how calendar_sync keeps showing the last
    events it managed to fetch.
    """

    def __init__(self, ttl=CACHE_TTL_SECONDS, clock=None):
        self.ttl = ttl
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()
        self._payload = None
        self._fetched_at = None
        self._error = None

    def get(self, lat, lon, location_name, tz, force=False, session=None):
        with self._lock:
            now = self._clock()
            fresh = (self._payload is not None
                     and self._fetched_at is not None
                     and (now - self._fetched_at).total_seconds() < self.ttl)
            if fresh and not force:
                return dict(self._payload, stale=False, cached=True)

            try:
                payload = build_weather(lat, lon, location_name, tz, session=session)
            except WeatherError as exc:
                self._error = str(exc)
                if self._payload is not None:
                    return dict(self._payload, stale=True, cached=True, error=self._error)
                raise

            self._payload = payload
            self._fetched_at = now
            self._error = None
            return dict(payload, stale=False, cached=False)
