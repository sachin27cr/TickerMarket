"""Calendars for the morning posts: major global economic events, India events and the quarterly results schedule.

Global events: ForexFactory's public weekly calendar feed (high-impact events of the big economies only).
India events: config/india_events.json (official dates, e.g. RBI policy decisions).
Results schedule: NSE event calendar (board meetings for financial results).
"""
import json
from datetime import date, datetime, timedelta

import requests

from .. import config
from ..util import IST, log, today_ist
from . import nse

FF_URL = 'https://nfs.faireconomy.media/ff_calendar_thisweek.json'
COUNTRY = {'USD': 'US', 'EUR': 'Eurozone', 'GBP': 'UK', 'JPY': 'Japan', 'CNY': 'China'}
FLAG = {'US': '🇺🇸', 'Eurozone': '🇪🇺', 'UK': '🇬🇧', 'Japan': '🇯🇵', 'China': '🇨🇳', 'India': '🇮🇳'}


def global_events(day_from=None, day_to=None):
    """High-impact events for the US, Eurozone, UK, Japan and China: [{'when': datetime IST, 'country', 'title'}]."""
    day_from = day_from or today_ist()
    day_to = day_to or day_from
    try:
        r = requests.get(FF_URL, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
        rows = r.json() if r.status_code == 200 else []
    except (requests.RequestException, ValueError) as e:
        log.warning('global calendar unavailable: %s', type(e).__name__)
        return None
    out = []
    for e in rows if isinstance(rows, list) else []:
        cur = str(e.get('country', '')).upper()
        if cur not in COUNTRY or str(e.get('impact', '')).lower() != 'high':
            continue
        try:
            when = datetime.fromisoformat(str(e['date'])).astimezone(IST)
        except (KeyError, ValueError):
            continue
        if day_from <= when.date() <= day_to:
            out.append({'when': when, 'country': COUNTRY[cur], 'title': str(e.get('title', '')).strip()})
    out.sort(key=lambda x: x['when'])
    return out


def india_events(day_from=None, day_to=None):
    day_from = day_from or today_ist()
    day_to = day_to or day_from
    try:
        rows = json.loads((config.ROOT / 'config' / 'india_events.json').read_text())['events']
    except (OSError, ValueError, KeyError):
        return []
    out = []
    for e in rows:
        try:
            d = date.fromisoformat(e['date'])
        except (KeyError, ValueError):
            continue
        if day_from <= d <= day_to:
            hh, mm = (e.get('time') or '00:00').split(':')
            out.append({'when': datetime(d.year, d.month, d.day, int(hh), int(mm), tzinfo=IST), 'country': 'India',
                        'title': e['title']})
    return out


def events_today():
    """India + global high-impact events for today, in IST order. None if the global feed is down."""
    g = global_events()
    ind = india_events()
    if g is None and not ind:
        return None
    return sorted((g or []) + ind, key=lambda x: x['when'])


def results_schedule(days=6):
    """Upcoming results board meetings: {date: [(symbol, company)]} for today and the next `days` days."""
    t = today_ist()
    try:
        ev = nse.event_calendar()
    except nse.SourceError as e:
        log.warning('results calendar unavailable: %s', e)
        return None
    out = {}
    for e in ev:
        if t <= e['date'] <= t + timedelta(days=days) and 'result' in (e['purpose'] or '').lower():
            out.setdefault(e['date'], []).append((e['symbol'], e['company']))
    return dict(sorted(out.items()))


def well_known_first(items):
    """Companies with an everyday name in names.COMMON first (they are the ones people follow)."""
    from .names import COMMON
    return sorted(items, key=lambda x: (x[0] not in COMMON, x[1] or x[0]))
