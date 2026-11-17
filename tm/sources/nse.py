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
                         'day_high': float(r.get('dayHigh') or 0) or None,
                         'day_low': float(r.get('dayLow') or 0) or None,
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


# ---------------------------------------------------------------- F&O participant positions

PARTICIPANT_OI_URL = 'https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{d:%d%m%Y}.csv'
PARTICIPANTS = ('Client', 'DII', 'FII', 'Pro')


def participant_oi(day):
    """Open interest (contracts) by participant for one trading day, from NSE's daily archive file.
    {'FII': {'fut_idx_long':..,'fut_idx_short':..,'opt_idx_call_long':.., ...}, 'TOTAL': {...}}"""
    import csv
    import io
    r = session().get(PARTICIPANT_OI_URL.format(d=day), timeout=45)
    if r.status_code != 200 or 'Client' not in r.text:
        raise SourceError(f'participant OI {day}: HTTP {r.status_code}')
    lines = [ln for ln in r.text.splitlines() if ln.strip()]
    start = next(i for i, ln in enumerate(lines) if ln.lower().startswith('client type'))
    rows = list(csv.reader(io.StringIO('\n'.join(lines[start:]))))
    head = [h.strip().lower() for h in rows[0]]
    col = {name: head.index(name) for name in head}

    def g(row, name):
        return int(float(row[col[name]].strip().replace(',', '')))

    out = {}
    for row in rows[1:]:
        who = row[0].strip()
        if who.upper() == 'TOTAL':
            who = 'TOTAL'
        if who not in PARTICIPANTS + ('TOTAL',):
            continue
        out[who] = {
            'fut_idx_long': g(row, 'future index long'), 'fut_idx_short': g(row, 'future index short'),
            'fut_stk_long': g(row, 'future stock long'), 'fut_stk_short': g(row, 'future stock short'),
            'opt_idx_call_long': g(row, 'option index call long'), 'opt_idx_put_long': g(row, 'option index put long'),
            'opt_idx_call_short': g(row, 'option index call short'), 'opt_idx_put_short': g(row, 'option index put short'),
        }
    if not all(p in out for p in PARTICIPANTS + ('TOTAL',)):
        raise SourceError(f'participant OI {day}: missing rows')
    return out


# ---------------------------------------------------------------- IPO details and live subscription

def _flatten(obj, path=''):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flatten(v, f'{path}.{k}' if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _flatten(v, f'{path}[{i}]')
    else:
        yield path, obj


def find_field(obj, *patterns):
    """First scalar whose key path matches any regex (case-insensitive). NSE renames fields often,
    so IPO details are read by meaning, not by one fixed field name."""
    import re
    flat = list(_flatten(obj))
    for pat in patterns:
        rx = re.compile(pat, re.I)
        for path, v in flat:
            if rx.search(path.split('.')[-1]) and v not in (None, '', '-', 'NA'):
                return v
    return None


def ipo_detail(symbol, series='EQ'):
    return get('/api/ipo-detail', {'symbol': symbol, 'series': series})


def ipo_subscription(symbol):
    """Category-wise live bids: [{'category','offered','bid','times'}] + update time text."""
    import re
    j = get('/api/ipo-active-category', {'symbol': symbol})
    rows, upd = [], find_field(j, r'update', r'time')
    lists = [v for v in (j.values() if isinstance(j, dict) else [j]) if isinstance(v, list)]
    for lst in lists:
        for r in lst:
            if not isinstance(r, dict):
                continue
            cat = find_field(r, r'categor', r'^name$')
            offered = find_field(r, r'offer|reserv')
            bid = find_field(r, r'bid')
            times = find_field(r, r'times|meant|subscri')
            if not cat:
                continue
            num = lambda v: float(re.sub(r'[^0-9.]', '', str(v)) or 0) if v is not None else None
            rows.append({'category': re.sub(r'\s+', ' ', str(cat)).strip(), 'offered': num(offered), 'bid': num(bid),
                         'times': num(times)})
    if not rows:
        raise SourceError(f'IPO subscription {symbol}: no category rows')
    return rows, upd, j
