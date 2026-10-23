"""
Tests for the weather module.

Network calls are faked with a stub session, so these run offline and the
National Weather Service never sees a request from CI.

Run from the backend/ directory:
    python -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import weather as wx  # noqa: E402

TZ = ZoneInfo('America/New_York')
LAT, LON = 43.1566, -77.6088


def period(name, start, daytime, temp, forecast='Sunny', pop=None):
    return {
        'name': name,
        'startTime': start,
        'isDaytime': daytime,
        'temperature': temp,
        'temperatureUnit': 'F',
        'shortForecast': forecast,
        'icon': 'https://api.weather.gov/icons/land/day/skc',
        'probabilityOfPrecipitation': {'value': pop},
    }


class _StubResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _StubSession:
    """Serves canned payloads by URL substring and records what was asked for."""

    def __init__(self, routes, fail_on=()):
        self.routes = routes
        self.fail_on = fail_on
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(url)
        self.headers = headers
        for fragment in self.fail_on:
            if fragment in url:
                raise wx.requests.RequestException('stubbed failure for ' + fragment)
        # Longest fragment first: a station observation URL ends in both
        # "/stations/KROC/observations/latest" and "/stations", and the
        # specific route is the one that should win.
        for fragment in sorted(self.routes, key=len, reverse=True):
            if fragment in url:
                return _StubResponse(self.routes[fragment])
        raise AssertionError('unexpected URL requested: ' + url)


def nws_routes(periods, observation=True):
    routes = {
        '/points/': {'properties': {
            'forecast': wx.API_ROOT + '/gridpoints/BUF/40,60/forecast',
            'observationStations': wx.API_ROOT + '/gridpoints/BUF/40,60/stations',
        }},
        '/forecast': {'properties': {'periods': periods}},
        '/alerts/active': {'features': []},
    }
    if observation:
        routes['/stations'] = {'features': [{'id': wx.API_ROOT + '/stations/KROC'}]}
        routes['/observations/latest'] = {'properties': {
            'temperature': {'value': 12.2},        # 54.0 F
            'windChill': {'value': 8.7},           # 47.7 F
            'heatIndex': {'value': None},
            'relativeHumidity': {'value': 61.0},
            'windSpeed': {'value': 14.5},          # ~9 mph
            'textDescription': 'Partly Cloudy',
            'timestamp': '2026-10-23T19:00:00+00:00',
            'station': wx.API_ROOT + '/stations/KROC',
        }}
    return routes


SAMPLE_PERIODS = [
    period('Today', '2026-10-23T06:00:00-04:00', True, 55, 'Sunny', 10),
    period('Tonight', '2026-10-23T18:00:00-04:00', False, 40, 'Clear', 0),
    period('Saturday', '2026-10-24T06:00:00-04:00', True, 62, 'Mostly Sunny', 20),
    period('Saturday Night', '2026-10-24T18:00:00-04:00', False, 34, 'Clear', 5),
    period('Sunday', '2026-10-25T06:00:00-04:00', True, 67, 'Sunny', 0),
]


class DailyAggregationTests(unittest.TestCase):
    def test_day_and_night_fold_into_one_entry(self):
        daily = wx.daily_from_periods(SAMPLE_PERIODS)
        self.assertEqual(len(daily), 3)
        self.assertEqual(daily[0]['date'], '2026-10-23')
        self.assertEqual(daily[0]['high'], 55)
        self.assertEqual(daily[0]['low'], 40)
        self.assertEqual(daily[1]['high'], 62)
        self.assertEqual(daily[1]['low'], 34)

    def test_daytime_label_and_forecast_win(self):
        daily = wx.daily_from_periods(SAMPLE_PERIODS)
        # Not "Saturday Night", even though that period is also on that date.
        self.assertEqual(daily[1]['name'], 'Saturday')
        self.assertEqual(daily[1]['shortForecast'], 'Mostly Sunny')

    def test_trailing_day_without_a_night_keeps_its_high(self):
        daily = wx.daily_from_periods(SAMPLE_PERIODS)
        self.assertEqual(daily[-1]['high'], 67)
        self.assertIsNone(daily[-1]['low'])

    def test_starting_after_dark_yields_a_low_only(self):
        # Booting the dashboard at night: NWS leads with "Tonight".
        daily = wx.daily_from_periods(SAMPLE_PERIODS[1:])
        self.assertEqual(daily[0]['date'], '2026-10-23')
        self.assertIsNone(daily[0]['high'])
        self.assertEqual(daily[0]['low'], 40)
        self.assertEqual(daily[0]['name'], 'Tonight')

    def test_precipitation_takes_the_days_worst_chance(self):
        daily = wx.daily_from_periods(SAMPLE_PERIODS)
        self.assertEqual(daily[1]['precipitation'], 20)  # 20 day vs 5 night

    def test_limit_caps_the_number_of_days(self):
        self.assertEqual(len(wx.daily_from_periods(SAMPLE_PERIODS, limit=2)), 2)

    def test_periods_without_a_start_time_are_skipped(self):
        broken = [{'name': 'Mystery', 'temperature': 50, 'isDaytime': True}]
        self.assertEqual(wx.daily_from_periods(broken), [])


class SunTimeTests(unittest.TestCase):
    def test_matches_published_times_for_rochester(self):
        times = wx.sun_times(LAT, LON, date(2026, 10, 23), TZ)
        self.assertEqual(times['sunset'].strftime('%H:%M'), '18:15')
        self.assertEqual(times['sunrise'].strftime('%H:%M'), '07:33')

    def test_solstice_day_lengths_are_right(self):
        summer = wx.sun_times(LAT, LON, date(2026, 6, 21), TZ)
        winter = wx.sun_times(LAT, LON, date(2026, 12, 21), TZ)
        summer_len = summer['sunset'] - summer['sunrise']
        winter_len = winter['sunset'] - winter['sunrise']
        # Rochester runs about 15h20m in midsummer and 9h in midwinter.
        self.assertGreater(summer_len, timedelta(hours=15))
        self.assertLess(winter_len, timedelta(hours=9, minutes=10))
        self.assertGreater(summer_len, winter_len)

    def test_polar_night_has_no_sunrise(self):
        times = wx.sun_times(78.22, 15.65, date(2026, 12, 21), timezone.utc)
        self.assertIsNone(times['sunrise'])
        self.assertIsNone(times['sunset'])

    def test_results_are_returned_in_the_requested_zone(self):
        times = wx.sun_times(LAT, LON, date(2026, 10, 23), TZ)
        self.assertEqual(times['sunset'].tzinfo, TZ)


class BuildWeatherTests(unittest.TestCase):
    def _build(self, session):
        return wx.build_weather(LAT, LON, 'Rochester, NY', TZ, session=session,
                                clock=lambda: datetime(2026, 10, 23, 15, 13, tzinfo=TZ))

    def test_current_comes_from_the_observation_not_the_forecast(self):
        session = _StubSession(nws_routes(SAMPLE_PERIODS))
        data = self._build(session)
        # 54.0 observed, not the 55 of the "Today" forecast period.
        self.assertEqual(data['current']['temperature'], 54.0)
        self.assertEqual(data['current']['feelsLike'], 47.7)
        self.assertEqual(data['current']['windSpeed'], '9 mph')

    def test_falls_back_to_the_forecast_when_no_observation(self):
        session = _StubSession(nws_routes(SAMPLE_PERIODS, observation=False),
                               fail_on=('/stations',))
        data = self._build(session)
        self.assertEqual(data['current']['temperature'], 55)
        self.assertEqual(data['current']['feelsLike'], 55)

    def test_payload_carries_daily_sun_and_location(self):
        data = self._build(_StubSession(nws_routes(SAMPLE_PERIODS)))
        self.assertEqual(data['location'], 'Rochester, NY')
        self.assertEqual(len(data['daily']), 3)
        self.assertTrue(data['sun']['sunset'].startswith('2026-10-23T18:15'))

    def test_legacy_forecast_strip_is_preserved(self):
        data = self._build(_StubSession(nws_routes(SAMPLE_PERIODS)))
        # The old kiosk markup reads `forecast`; it must survive the rewrite.
        self.assertEqual([p['name'] for p in data['forecast']],
                         ['Tonight', 'Saturday', 'Saturday Night', 'Sunday'])

    def test_alert_failure_does_not_blank_the_forecast(self):
        session = _StubSession(nws_routes(SAMPLE_PERIODS), fail_on=('/alerts',))
        data = self._build(session)
        self.assertEqual(data['alerts'], [])
        self.assertEqual(len(data['daily']), 3)

    def test_identifies_itself_to_nws(self):
        session = _StubSession(nws_routes(SAMPLE_PERIODS))
        self._build(session)
        # NWS returns 403 to requests without a descriptive User-Agent.
        self.assertIn('FamilyDash', session.headers['User-Agent'])

    def test_unreachable_service_raises_weather_error(self):
        session = _StubSession(nws_routes(SAMPLE_PERIODS), fail_on=('/points/',))
        with self.assertRaises(wx.WeatherError):
            self._build(session)

    def test_empty_forecast_raises_weather_error(self):
        session = _StubSession(nws_routes([]))
        with self.assertRaises(wx.WeatherError):
            self._build(session)


class WeatherCacheTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
        self.cache = wx.WeatherCache(ttl=600, clock=lambda: self.now)
        self.session = _StubSession(nws_routes(SAMPLE_PERIODS))

    def _get(self, **kw):
        return self.cache.get(LAT, LON, 'Rochester, NY', TZ,
                              session=self.session, **kw)

    def test_second_call_inside_the_ttl_does_not_refetch(self):
        self._get()
        calls = len(self.session.calls)
        result = self._get()
        self.assertEqual(len(self.session.calls), calls)
        self.assertTrue(result['cached'])

    def test_refetches_once_the_ttl_expires(self):
        self._get()
        calls = len(self.session.calls)
        self.now += timedelta(seconds=601)
        result = self._get()
        self.assertGreater(len(self.session.calls), calls)
        self.assertFalse(result['cached'])

    def test_force_bypasses_a_fresh_cache(self):
        self._get()
        calls = len(self.session.calls)
        self._get(force=True)
        self.assertGreater(len(self.session.calls), calls)

    def test_failure_after_a_success_serves_the_last_good_payload(self):
        self._get()
        self.session.fail_on = ('/points/',)
        self.now += timedelta(seconds=601)
        result = self._get()
        self.assertTrue(result['stale'])
        self.assertEqual(len(result['daily']), 3)
        self.assertIn('Could not reach', result['error'])

    def test_failure_with_no_previous_success_propagates(self):
        self.session.fail_on = ('/points/',)
        with self.assertRaises(wx.WeatherError):
            self._get()


if __name__ == '__main__':
    unittest.main()
