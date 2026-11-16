"""NSE public website endpoints (the same JSON the nseindia.com pages load).

NSE needs browser-like headers and cookies from the home page first. It sometimes
blocks cloud servers; every function raises SourceError on failure so callers can
fall back or skip, never guess.
"""
import time
from datetime import datetime

import requests

from ..util import log

BASE = 'https://www.nseindia.com'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/130.0 Safari/537.36',
    'Accept': 'application/json,text/plain,*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.nseindia.com/',
}


class SourceError(Exception):
    pass


_session = None


def session():
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update(HEADERS)
        try:
            s.get(BASE, timeout=15)
            s.get(BASE + '/market-data/live-equity-market', timeout=15)
        except requests.RequestException as e:
            log.warning('NSE warm-up failed: %s', e)
        _session = s
    return _session


def get(path, params=None, retries=3):
    last = None
    for i in range(retries):
        try:
            r = session().get(BASE + path, params=params, timeout=20)
            if r.status_code == 200 and r.text.strip().startswith(('{', '[')):
                return r.json()
            last = f'HTTP {r.status_code}'
        except (requests.RequestException, ValueError) as e:
            last = str(e)
        time.sleep(2 * (i + 1))
        global _session
        _session = None                       # refresh cookies and retry
    raise SourceError(f'NSE {path}: {last}')


def parse_nse_date(s):
    for fmt in ('%d-%b-%Y %H:%M:%S', '%d-%b-%Y %H:%M', '%d-%b-%Y', '%d %b %Y'):
        try:
            return datetime.strptime(s.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None


# ---------------------------------------------------------------- endpoints

def all_indices():
    """{index name: {'last','chg','pct','prev','advances','declines'}} + timestamp."""
    j = get('/api/allIndices')
    out = {}
    for row in j.get('data', []):
        try:
            out[row['index']] = {
                'last': float(row['last']), 'chg': float(row['variation']),
                'pct': float(row['percentChange']), 'prev': float(row['previousClose']),
                'advances': int(row.get('advances') or 0), 'declines': int(row.get('declines') or 0),
            }
        except (KeyError, TypeError, ValueError):
            continue
    ts = parse_nse_date(j.get('timestamp', '')) if j.get('timestamp') else None
    if not out:
        raise SourceError('allIndices returned no rows')
    return out, ts


def index_constituents(index='NIFTY 50'):
    """Stocks of an index with lastPrice, change, pChange."""
    j = get('/api/equity-stockIndices', {'index': index})
    rows = []
    for r in j.get('data', []):
        if r.get('priority') == 1 or r.get('symbol') == index:
            continue
        try:
            rows.append({'symbol': r['symbol'], 'last': float(r['lastPrice']),
                         'chg': float(r['change']), 'pct': float(r['pChange']),
                         'prev': float(r.get('previousClose') or 0) or None,
                         'year_high': float(r.get('yearHigh') or 0) or None,
                         'year_low': float(r.get('yearLow') or 0) or None})
        except (KeyError, TypeError, ValueError):
            continue
    if not rows:
        raise SourceError(f'{index} constituents empty')
    ts = parse_nse_date(j.get('timestamp', '')) if j.get('timestamp') else None
    return rows, ts


def fii_dii():
    """Latest provisional cash-market flows: {'date': date, 'fii': net, 'dii': net} in Rs crore."""
    j = get('/api/fiidiiTradeReact')
    fii = dii = None
    date = None
    for r in j:
        cat = (r.get('category') or '').upper()
        net = float(str(r.get('netValue')).replace(',', ''))
        d = parse_nse_date(r.get('date', ''))
        date = d.date() if d else date
        if cat.startswith('FII') or 'FPI' in cat:
            fii = net
        elif cat.startswith('DII'):
            dii = net
    if fii is None or dii is None or date is None:
        raise SourceError(f'fiidii incomplete: {j}')
    return {'date': date, 'fii': fii, 'dii': dii}


def ipos_current():
    return get('/api/ipo-current-issue')


def ipos_upcoming():
    return get('/api/all-upcoming-issues', {'category': 'ipo'})


def trading_holidays():
    """Set of dates the equity market is closed (from NSE holiday master)."""
    j = get('/api/holiday-master', {'type': 'trading'})
    out = set()
    for r in j.get('CM', []):
        d = parse_nse_date(r.get('tradingDate', ''))
        if d:
            out.add(d.date())
    if not out:
        raise SourceError('holiday list empty')
    return out


def event_calendar():
    """Board meetings (results etc.): list of {'symbol','company','purpose','date'}."""
    j = get('/api/event-calendar')
    out = []
    for r in j if isinstance(j, list) else j.get('data', []):
        d = parse_nse_date(r.get('date', ''))
        if d:
            out.append({'symbol': r.get('symbol'), 'company': r.get('company') or r.get('symbol'),
                        'purpose': r.get('purpose') or '', 'date': d.date()})
    return out


def corporate_actions(from_date, to_date):
    j = get('/api/corporates-corporateActions',
            {'index': 'equities', 'from_date': from_date.strftime('%d-%m-%Y'), 'to_date': to_date.strftime('%d-%m-%Y')})
    out = []
    for r in j if isinstance(j, list) else []:
        d = parse_nse_date(r.get('exDate', ''))
        if d:
            out.append({'symbol': r.get('symbol'), 'company': r.get('comp'), 'subject': r.get('subject'),
                        'ex_date': d.date()})
    return out


# ---------------------------------------------------------------- company lookup and quotes

EQUITY_LIST_URL = 'https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv'


def equity_list():
    """[(symbol, company name)] for every NSE-listed equity (official master list)."""
    import csv
    import io
    r = session().get(EQUITY_LIST_URL, timeout=30)
    if r.status_code != 200 or 'SYMBOL' not in r.text[:200]:
        raise SourceError(f'equity list HTTP {r.status_code}')
    rows = list(csv.DictReader(io.StringIO(r.text)))
    out = [(row['SYMBOL'].strip(), row['NAME OF COMPANY'].strip()) for row in rows if row.get('SYMBOL')]
    if len(out) < 1000:
        raise SourceError('equity list too short')
    return out


def quote(symbol):
    """Live/closing quote: {'price','chg','pct','prev','time','name'}."""
    j = get('/api/quote-equity', {'symbol': symbol})
    p = j.get('priceInfo') or {}
    try:
        price = float(p['lastPrice'])
        prev = float(p.get('previousClose') or 0)
    except (KeyError, TypeError, ValueError):
        raise SourceError(f'quote {symbol}: no price')
    meta = j.get('metadata') or {}
    info = j.get('info') or {}
    return {'price': price, 'chg': float(p.get('change') or 0), 'pct': float(p.get('pChange') or 0),
            'prev': prev or None, 'time': parse_nse_date(meta.get('lastUpdateTime', '') or ''),
            'name': info.get('companyName') or symbol}
