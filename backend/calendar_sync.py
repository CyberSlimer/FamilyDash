#!/usr/bin/env python3
"""
Calendar Sync for Family Dashboard

Pulls events from any number of CalDAV (iCloud, Nextcloud, Fastmail...) and
ICS/webcal (Google "secret address", Outlook published, school calendars...)
sources, expands recurring events, normalizes everything to the local
timezone, and keeps the result cached in memory so the dashboard never has
to wait on a slow upstream server.

Calendars are defined in config/calendars.json (see calendars.example.json).
Any string value in that file may reference an environment variable with
${VAR_NAME} so secrets can live in config.env instead of the JSON file.
"""

import hashlib
import json
import logging
import os
import re
import threading
from datetime import date, datetime, time, timedelta, timezone

import requests

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9
    ZoneInfo = None

log = logging.getLogger('calendar_sync')

# Optional dependencies: the dashboard still runs (with an empty calendar)
# if these aren't installed, but we log loudly about it.
try:
    from icalendar import Calendar as ICalendar
    import recurring_ical_events
    HAVE_ICAL = True
except ImportError:  # pragma: no cover
    HAVE_ICAL = False
    log.warning("icalendar / recurring-ical-events not installed - calendar sync disabled")

try:
    import caldav
    HAVE_CALDAV = True
except ImportError:  # pragma: no cover
    HAVE_CALDAV = False

DEFAULT_COLORS = ['#4f8ef7', '#f5a623', '#7ed321', '#e0685c', '#bd10e0', '#50e3c2', '#f8e71c']
HTTP_TIMEOUT = 15
USER_AGENT = 'FamilyDash/1.0 (+https://github.com/CyberSlimer/FamilyDash)'

_ENV_REF = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}')


# ============================================================================
# Configuration
# ============================================================================

def _expand_env(value):
    """Replace ${VAR} references in strings (recursively through dicts/lists)."""
    if isinstance(value, str):
        return _ENV_REF.sub(lambda m: os.environ.get(m.group(1), ''), value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def read_raw_config(path):
    """Return the calendar entries exactly as stored in calendars.json (no env expansion)."""
    if not path or not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as fh:
        raw = json.load(fh)
    entries = raw.get('calendars', raw) if isinstance(raw, dict) else raw
    return [dict(e) for e in entries if isinstance(e, dict)]


def write_raw_config(path, entries):
    """Atomically write calendar entries to calendars.json."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f'{path}.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump({'calendars': entries}, fh, indent=2)
        fh.write('\n')
    os.replace(tmp, path)


def prepare_calendar(entry, index=0):
    """Expand ${ENV} references and fill in defaults for one calendar entry."""
    cal = _expand_env(dict(entry))
    cal.setdefault('id', f'calendar-{index + 1}')
    cal.setdefault('name', cal['id'].replace('-', ' ').title())
    cal['type'] = str(cal.get('type', 'ics')).lower()
    if cal['type'] in ('ical', 'webcal'):
        cal['type'] = 'ics'
    if not cal.get('color'):
        cal['color'] = DEFAULT_COLORS[index % len(DEFAULT_COLORS)]
    return cal


def load_calendar_config(path):
    """
    Load calendar definitions. Returns a list of dicts with at least
    id, name, type, url, color. Falls back to the single-calendar settings
    in config.env (CALENDAR_TYPE / CALDAV_* / ICAL_URL) if the JSON file
    doesn't exist.
    """
    calendars = []

    if path and os.path.exists(path):
        for entry in read_raw_config(path):
            if entry.get('enabled', True):
                calendars.append(entry)
    else:
        # Legacy single-calendar config from config.env
        cal_type = os.environ.get('CALENDAR_TYPE', 'local').lower()
        if cal_type == 'caldav' and os.environ.get('CALDAV_URL'):
            calendars.append({
                'id': 'caldav', 'name': 'Calendar', 'type': 'caldav',
                'url': os.environ['CALDAV_URL'],
                'username': os.environ.get('CALDAV_USERNAME', ''),
                'password': os.environ.get('CALDAV_PASSWORD', ''),
            })
        elif cal_type in ('ical', 'ics') and os.environ.get('ICAL_URL'):
            calendars.append({
                'id': 'ical', 'name': 'Calendar', 'type': 'ics',
                'url': os.environ['ICAL_URL'],
            })

    return [prepare_calendar(cal, i) for i, cal in enumerate(calendars)]


def local_timezone():
    """Resolve the display timezone: TIMEZONE env var, else the system zone."""
    name = os.environ.get('TIMEZONE', '').strip()
    if name and ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except Exception:
            log.warning("Unknown TIMEZONE %r, falling back to system timezone", name)
    return datetime.now().astimezone().tzinfo


# ============================================================================
# Event normalization
# ============================================================================

def _to_local_datetime(value, tz):
    """
    Convert an icalendar DTSTART/DTEND value to (aware local datetime, is_all_day).
    Handles date (all-day), naive datetime (floating -> assume local) and
    aware datetime.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=tz)
        return value.astimezone(tz), False
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=tz), True
    raise TypeError(f"Unsupported date value: {value!r}")


def _text(component, key):
    value = component.get(key)
    return str(value).strip() if value is not None else ''


def normalize_event(component, cal_cfg, tz):
    """Turn a VEVENT component into the dashboard's event dict."""
    dtstart = component.get('dtstart')
    if dtstart is None:
        return None

    start, all_day = _to_local_datetime(dtstart.dt, tz)

    dtend = component.get('dtend')
    if dtend is not None:
        end, _ = _to_local_datetime(dtend.dt, tz)
    else:
        duration = component.get('duration')
        if duration is not None:
            end = start + duration.dt
        else:
            end = start + (timedelta(days=1) if all_day else timedelta(hours=1))

    # Skip cancelled events
    if _text(component, 'status').upper() == 'CANCELLED':
        return None

    uid = _text(component, 'uid') or _text(component, 'summary')
    recurrence_id = component.get('recurrence-id')
    id_source = f"{cal_cfg['id']}|{uid}|{start.isoformat()}|{recurrence_id.dt if recurrence_id else ''}"
    event_id = hashlib.sha1(id_source.encode('utf-8')).hexdigest()[:16]

    return {
        'id': event_id,
        'title': _text(component, 'summary') or '(No title)',
        'start': start.isoformat(),
        'end': end.isoformat(),
        'all_day': all_day,
        'location': _text(component, 'location'),
        'description': _text(component, 'description')[:500],
        'calendar': cal_cfg['id'],
        'calendar_name': cal_cfg['name'],
        'color': cal_cfg['color'],
        # Keep the datetime objects around for filtering/sorting; stripped before JSON.
        '_start': start,
        '_end': end,
    }


def expand_vcalendar(vcal_data, cal_cfg, tz, window_start, window_end):
    """
    Parse raw VCALENDAR text and return every event instance (recurrences
    expanded) that overlaps the window.
    """
    events = []
    try:
        vcal = ICalendar.from_ical(vcal_data)
    except Exception as exc:
        log.warning("[%s] could not parse calendar data: %s", cal_cfg['name'], exc)
        return events

    try:
        instances = recurring_ical_events.of(vcal).between(window_start, window_end)
    except Exception as exc:
        log.warning("[%s] recurrence expansion failed (%s); using raw events", cal_cfg['name'], exc)
        instances = [c for c in vcal.walk() if c.name == 'VEVENT']

    for component in instances:
        try:
            event = normalize_event(component, cal_cfg, tz)
        except Exception as exc:
            log.debug("[%s] skipping malformed event: %s", cal_cfg['name'], exc)
            continue
        if event and event['_end'] > window_start and event['_start'] < window_end:
            events.append(event)
    return events


# ============================================================================
# Fetchers
# ============================================================================

def fetch_ics(cal_cfg, tz, window_start, window_end):
    """Fetch a published .ics / webcal feed."""
    url = cal_cfg['url'].strip()
    if url.startswith('webcal://'):
        url = 'https://' + url[len('webcal://'):]

    auth = None
    if cal_cfg.get('username'):
        auth = (cal_cfg['username'], cal_cfg.get('password', ''))

    response = requests.get(url, timeout=HTTP_TIMEOUT, auth=auth,
                            headers={'User-Agent': USER_AGENT})
    response.raise_for_status()
    return expand_vcalendar(response.content, cal_cfg, tz, window_start, window_end)


def fetch_caldav(cal_cfg, tz, window_start, window_end):
    """
    Fetch from a CalDAV server. For iCloud use url=https://caldav.icloud.com
    with your Apple ID and an app-specific password. Optionally restrict to
    specific calendars by name with "calendars": ["Family", "Work"].
    """
    if not HAVE_CALDAV:
        raise RuntimeError("python 'caldav' package is not installed")

    client = caldav.DAVClient(url=cal_cfg['url'],
                              username=cal_cfg.get('username'),
                              password=cal_cfg.get('password'))
    principal = client.principal()
    wanted = cal_cfg.get('calendars')
    if isinstance(wanted, str):
        wanted = [wanted]
    wanted_lower = {w.lower() for w in wanted} if wanted else None

    events = []
    for calendar in principal.calendars():
        try:
            name = str(calendar.name or '')
        except Exception:
            name = ''
        if wanted_lower is not None and name.lower() not in wanted_lower:
            continue

        # Give each sub-calendar its own identity so events can be told apart.
        sub_cfg = dict(cal_cfg)
        if wanted_lower is None or len(wanted_lower) > 1:
            sub_cfg['id'] = f"{cal_cfg['id']}:{name}" if name else cal_cfg['id']
            sub_cfg['name'] = f"{cal_cfg['name']} / {name}" if name and name != cal_cfg['name'] else cal_cfg['name']

        try:
            # caldav >= 1.0: search(); ask the server NOT to expand so that
            # recurring_ical_events can do it consistently for every source.
            try:
                results = calendar.search(start=window_start, end=window_end,
                                          event=True, expand=False)
            except TypeError:
                results = calendar.date_search(start=window_start, end=window_end, expand=False)
        except Exception as exc:
            log.warning("[%s] CalDAV search failed on '%s': %s", cal_cfg['name'], name, exc)
            continue

        for item in results:
            events.extend(expand_vcalendar(item.data, sub_cfg, tz, window_start, window_end))

    return events


FETCHERS = {
    'ics': fetch_ics,
    'caldav': fetch_caldav,
}


def list_caldav_calendars(cal_cfg):
    """Names of every calendar the CalDAV account exposes (for the setup UI)."""
    if not HAVE_CALDAV:
        raise RuntimeError("python 'caldav' package is not installed")
    client = caldav.DAVClient(url=cal_cfg['url'],
                              username=cal_cfg.get('username'),
                              password=cal_cfg.get('password'))
    names = []
    for calendar in client.principal().calendars():
        try:
            name = str(calendar.name or '').strip()
        except Exception:
            name = ''
        if name:
            names.append(name)
    return names


def test_calendar(cal_cfg, tz=None, days=7, sample_size=5):
    """
    Fetch one calendar right now and report what happened. Used by the
    mobile UI's "Test" button before a calendar is saved.
    """
    tz = tz or local_timezone()
    cal_cfg = prepare_calendar(cal_cfg)
    result = {'ok': False, 'count': 0, 'sample': [], 'error': None, 'available_calendars': None}

    if not HAVE_ICAL:
        result['error'] = "icalendar / recurring-ical-events not installed"
        return result
    fetcher = FETCHERS.get(cal_cfg['type'])
    if fetcher is None:
        result['error'] = f"unknown calendar type '{cal_cfg['type']}'"
        return result
    if not cal_cfg.get('url'):
        result['error'] = 'URL is required'
        return result

    now = datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        events = fetcher(cal_cfg, tz, start, start + timedelta(days=days))
        events.sort(key=lambda e: e['_start'])
        result.update(ok=True, count=len(events),
                      sample=[{k: v for k, v in e.items() if not k.startswith('_')}
                              for e in events[:sample_size]])
        if cal_cfg['type'] == 'caldav':
            try:
                result['available_calendars'] = list_caldav_calendars(cal_cfg)
            except Exception as exc:
                log.debug("could not list CalDAV calendars: %s", exc)
    except Exception as exc:
        result['error'] = str(exc)
    return result


# ============================================================================
# Sync service
# ============================================================================

class CalendarSync:
    """
    Holds a cached, merged view of every configured calendar and refreshes
    it in the background.
    """

    def __init__(self, config_path, refresh_interval=300, lookbehind_days=1, lookahead_days=14, clock=None):
        self.config_path = config_path
        self.refresh_interval = max(60, int(refresh_interval))
        self.lookbehind = timedelta(days=lookbehind_days)
        self.lookahead = timedelta(days=lookahead_days)
        self.tz = local_timezone()
        # `clock` returns the current aware datetime; injectable for tests.
        self._now = clock or (lambda: datetime.now(self.tz))

        self._lock = threading.Lock()
        self._events = []
        self._status = {}      # calendar id -> {name, type, ok, count, error, fetched_at}
        self._last_refresh = None
        self._thread = None
        self._stop = threading.Event()

        try:
            self.calendars = load_calendar_config(config_path)
        except Exception as exc:
            log.error("Failed to load calendar config %s: %s", config_path, exc)
            self.calendars = []

    # ---- public API -------------------------------------------------------

    @property
    def enabled(self):
        return HAVE_ICAL and bool(self.calendars)

    def start(self):
        """Start the background refresh thread (idempotent)."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name='calendar-sync', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def reload(self):
        """
        Re-read calendars.json after it was edited. Cached events for
        calendars that were removed or disabled are dropped immediately;
        new ones appear on the next refresh().
        """
        self.calendars = load_calendar_config(self.config_path)
        live_ids = {c['id'] for c in self.calendars}
        with self._lock:
            self._events = [e for e in self._events if e['calendar'].split(':')[0] in live_ids]
            self._status = {cid: s for cid, s in self._status.items() if cid in live_ids}
        if self.enabled:
            self.start()

    def refresh_async(self):
        """Kick off a refresh without blocking the caller (e.g. after a config edit)."""
        threading.Thread(target=self._safe_refresh, name='calendar-refresh', daemon=True).start()

    def _safe_refresh(self):
        try:
            self.refresh()
        except Exception:
            log.exception("calendar refresh crashed")

    def refresh(self):
        """Fetch every calendar now. Safe to call from any thread."""
        if not HAVE_ICAL:
            return
        now = self._now().astimezone(self.tz)
        window_start = (now - self.lookbehind).replace(hour=0, minute=0, second=0, microsecond=0)
        window_end = now + self.lookahead

        all_events = []
        status = {}
        for cal_cfg in self.calendars:
            fetcher = FETCHERS.get(cal_cfg['type'])
            entry = {'name': cal_cfg['name'], 'type': cal_cfg['type'], 'color': cal_cfg['color'],
                     'ok': False, 'count': 0, 'error': None,
                     'fetched_at': datetime.now(self.tz).isoformat()}
            if fetcher is None:
                entry['error'] = f"unknown calendar type '{cal_cfg['type']}'"
            else:
                try:
                    events = fetcher(cal_cfg, self.tz, window_start, window_end)
                    entry.update(ok=True, count=len(events))
                    all_events.extend(events)
                    log.info("[%s] %d events", cal_cfg['name'], len(events))
                except Exception as exc:
                    entry['error'] = str(exc)
                    log.warning("[%s] fetch failed: %s", cal_cfg['name'], exc)
            status[cal_cfg['id']] = entry

        # De-duplicate (same event reachable through two configs) and sort.
        seen = set()
        unique = []
        for ev in sorted(all_events, key=lambda e: (e['_start'], not e['all_day'], e['title'])):
            if ev['id'] in seen:
                continue
            seen.add(ev['id'])
            unique.append(ev)

        with self._lock:
            # If a calendar failed this round, keep its previous events rather
            # than blanking the screen because iCloud hiccupped.
            failed_ids = {cid for cid, s in status.items() if not s['ok']}
            if failed_ids and self._events:
                kept = [e for e in self._events if e['calendar'].split(':')[0] in failed_ids]
                unique = sorted(unique + kept, key=lambda e: (e['_start'], not e['all_day'], e['title']))
                for cid in failed_ids:
                    status[cid]['count'] = sum(1 for e in kept if e['calendar'].split(':')[0] == cid)
                    status[cid]['stale'] = True
            self._events = unique
            self._status = status
            self._last_refresh = datetime.now(self.tz)

    def get_events(self, start=None, end=None):
        """
        Return JSON-safe events overlapping [start, end). Both default to
        "today" and "today + 1 day" in local time. Accepts datetimes or ISO strings.
        """
        start = self._coerce(start) or self._now().astimezone(self.tz).replace(hour=0, minute=0, second=0, microsecond=0)
        end = self._coerce(end) or (start + timedelta(days=1))
        with self._lock:
            events = [e for e in self._events if e['_end'] > start and e['_start'] < end]
        return [self._public(e) for e in events]

    def status(self):
        with self._lock:
            return {
                'enabled': self.enabled,
                'last_refresh': self._last_refresh.isoformat() if self._last_refresh else None,
                'refresh_interval': self.refresh_interval,
                'timezone': str(self.tz),
                'calendars': [dict(id=cid, **info) for cid, info in self._status.items()]
                             or [{'id': c['id'], 'name': c['name'], 'type': c['type'], 'color': c['color'],
                                  'ok': None, 'count': 0, 'error': None} for c in self.calendars],
            }

    # ---- internals --------------------------------------------------------

    def _run(self):
        while not self._stop.is_set():
            self._safe_refresh()
            self._stop.wait(self.refresh_interval)

    def _coerce(self, value):
        if value is None or value == '':
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            text = str(value).strip()
            if text.endswith('Z'):
                text = text[:-1] + '+00:00'
            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                try:
                    dt = datetime.combine(date.fromisoformat(text[:10]), time.min)
                except ValueError:
                    return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self.tz)
        return dt.astimezone(self.tz)

    @staticmethod
    def _public(event):
        return {k: v for k, v in event.items() if not k.startswith('_')}


# ============================================================================
# CLI for quick testing:  python calendar_sync.py [path/to/calendars.json]
# ============================================================================

if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
    cfg = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '..', 'config', 'calendars.json')
    sync = CalendarSync(cfg)
    print(f"Timezone: {sync.tz}")
    print(f"Calendars: {[c['name'] for c in sync.calendars] or 'none configured'}")
    sync.refresh()
    print(json.dumps(sync.status(), indent=2))
    today = datetime.now(sync.tz).replace(hour=0, minute=0, second=0, microsecond=0)
    for ev in sync.get_events(today, today + timedelta(days=7)):
        when = ev['start'][:10] if ev['all_day'] else ev['start'][:16].replace('T', ' ')
        print(f"  {when:16}  {ev['title']}  [{ev['calendar_name']}]")
