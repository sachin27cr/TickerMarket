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


def _url(path, params, plus=False):
    """NSE expects spaces as %20 ('NIFTY 100' -> NIFTY%20100), the way the website itself calls the API.
    requests' default ('+') makes some endpoints answer 404."""
    from urllib.parse import quote, quote_plus, urlencode
    if not params:
        return BASE + path
    return BASE + path + '?' + urlencode(params, quote_via=quote_plus if plus else quote)


def get(path, params=None, retries=3):
    last = None
    for i in range(retries):
        for plus in (False, True):                 # %20 first; '+' as a fallback
            try:
                r = session().get(_url(path, params, plus), timeout=20)
                if r.status_code == 200 and r.text.strip().startswith(('{', '[')):
                    return r.json()
                last = f'HTTP {r.status_code}'
                if r.status_code != 404 or not params:
                    break
            except (requests.RequestException, ValueError) as e:
                last = str(e)
                break
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
            wk = row.get('oneWeekAgo') or row.get('oneWeekAgoVal')      # NSE's own close one week ago
            try:
                if wk not in (None, '', '-') and float(wk) > 0:
                    out[row['index']]['week_ago'] = float(wk)
            except (TypeError, ValueError):
                pass
        except (KeyError, TypeError, ValueError):
            continue
    ts = parse_nse_date(j.get('timestamp', '')) if j.get('timestamp') else None
    if not out:
        raise SourceError('allIndices returned no rows')
    return out, ts


# Expected member counts: a reply with far fewer rows is treated as incomplete, never used.
INDEX_SIZE = {'NIFTY 50': 50, 'NIFTY NEXT 50': 50, 'NIFTY 100': 100, 'NIFTY 200': 200, 'NIFTY 500': 500,
              'NIFTY MIDCAP 150': 150, 'NIFTY SMALLCAP 250': 250, 'NIFTY MICROCAP 250': 250}
LAST_SOURCE = {}            # index -> 'NSE' or 'NSE list + Yahoo prices' (callers flag the second as a warning)

_KEYS = {  # field -> key patterns, matched case-insensitively against each row's own keys
    'symbol': [r'^symbol$', r'^cmsymbol$', r'^tradingsymbol$', r'symbol$'],
    'last': [r'^lastprice$', r'^ltp$', r'^last_?price$', r'^last$', r'^lasttradedprice$', r'^closeprice$'],
    'chg': [r'^change$', r'^netchange$', r'^chg$', r'^pricechange$'],
    'pct': [r'^pchange$', r'^perchange$', r'^percentchange$', r'^pctchange$', r'^changepercent$'],
    'prev': [r'^previousclose$', r'^prevclose$', r'^previous_?close_?price$', r'^prev_?close$'],
    'year_high': [r'^yearhigh$', r'^52_?w(ee)?k_?high$', r'^wkhi52$', r'^high52$', r'^fiftytwoweekhigh$'],
    'year_low': [r'^yearlow$', r'^52_?w(ee)?k_?low$', r'^wklo52$', r'^low52$', r'^fiftytwoweeklow$'],
    'day_high': [r'^dayhigh$', r'^high$', r'^highprice$', r'^intradayhigh$'],
    'day_low': [r'^daylow$', r'^low$', r'^lowprice$', r'^intradaylow$'],
}


def _pick(row, field):
    import re
    keys = {k.lower().replace('_', ''): k for k in row}
    for pat in _KEYS[field]:
        rx = re.compile(pat.replace('_?', ''), re.I)
        for low, k in keys.items():
            if rx.search(low) and row[k] not in (None, '', '-'):
                return row[k]
    return None


def _f(v):
    try:
        return float(str(v).replace(',', '')) if v not in (None, '', '-') else None
    except ValueError:
        return None


def _rows_from(j, index):
    """Find the list of stock rows anywhere in an NSE reply and read it by meaning, not fixed field names."""
    lists = []

    def walk(o):
        if isinstance(o, list) and o and isinstance(o[0], dict):
            lists.append(o)
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(j)
    best = []
    for lst in lists:
        rows = []
        for r in lst:
            sym, last = _pick(r, 'symbol'), _f(_pick(r, 'last'))
            if not sym or last is None or str(sym).upper() == index.upper() or r.get('priority') == 1:
                continue
            prev, chg, pct = _f(_pick(r, 'prev')), _f(_pick(r, 'chg')), _f(_pick(r, 'pct'))
            if prev is None and chg is not None:
                prev = last - chg
            if prev:
                chg = last - prev if chg is None else chg
                pct = (last - prev) / prev * 100 if pct is None else pct
            if pct is None:
                continue
            rows.append({'symbol': str(sym).strip().upper(), 'last': last, 'chg': chg or 0.0, 'pct': pct, 'prev': prev,
                         'year_high': _f(_pick(r, 'year_high')), 'year_low': _f(_pick(r, 'year_low')),
                         'day_high': _f(_pick(r, 'day_high')), 'day_low': _f(_pick(r, 'day_low'))})
        if len(rows) > len(best):
            best = rows
    return best


def _save_raw(name, obj):
    try:
        from .. import store
        store.write_json(f'cache/nse_raw/{name}.json', obj)
    except Exception:                                  # noqa: BLE001
        pass


def index_constituents(index='NIFTY 50'):
    """Stocks of an index: symbol, last, chg, pct, prev, year/day high/low.
    NSE retired /api/equity-stockIndices in 2026, so the newer website APIs are tried first; if none
    answers in full, NSE's official member list is priced from Yahoo (callers mark that as a warning)."""
    need = int(INDEX_SIZE.get(index, 10) * 0.9)
    short = index.replace('NIFTY ', '')
    attempts = [('/api/NextApi/apiClient/marketWatchApi', {'functionName': 'getIndicesData', 'symbol': index}),
                ('/api/NextApi/apiClient/marketWatchApi', {'functionName': 'getIndicesData', 'symbol': short}),
                ('/api/NextApi/apiClient/indexTrackerApi', {'functionName': 'getConstituents', 'index': index}),
                ('/api/equity-stockIndices', {'index': index})]
    errors = []
    for path, params in attempts:
        try:
            j = get(path, params, retries=1)
        except SourceError as e:
            errors.append(f'{path.rsplit("/", 1)[-1]}: {str(e).rsplit(":", 1)[-1].strip()}'); continue
        rows = _rows_from(j, index)
        if len(rows) >= need:
            _save_raw(f'{short.replace(" ", "_")}_ok', j if len(str(j)) < 400000 else {'note': 'large'})
            LAST_SOURCE[index] = 'NSE'
            ts = parse_nse_date(str(find_field(j, r'timestamp', r'time$') or ''))
            return _named(rows), ts
        _save_raw(f'{short.replace(" ", "_")}_{params.get("functionName", "old")}', j)
        errors.append(f'{path.rsplit("/", 1)[-1]}: {len(rows)} of {need}+ rows readable')
    try:
        rows = _yahoo_priced(index)
    except Exception as e:                             # noqa: BLE001
        errors.append(f'member list + Yahoo: {e}')
        raise SourceError(f'{index}: ' + '; '.join(errors))
    if len(rows) < need:
        raise SourceError(f'{index}: only {len(rows)} stocks priced; ' + '; '.join(errors))
    LAST_SOURCE[index] = 'NSE list + Yahoo prices'
    from ..util import log as _log
    _log.warning('%s via member list + Yahoo (%s)', index, '; '.join(errors))
    return _named(rows), None


def _named(rows):
    from .names import short
    for r in rows:
        r['name'] = short(r['symbol'])
    return rows


LIST_FILES = {'NIFTY 50': ['ind_nifty50list'], 'NIFTY NEXT 50': ['ind_niftynext50list'], 'NIFTY 100': ['ind_nifty100list'],
              'NIFTY 200': ['ind_nifty200list'], 'NIFTY 500': ['ind_nifty500list'],
              'NIFTY MIDCAP 150': ['ind_niftymidcap150list'], 'NIFTY SMALLCAP 250': ['ind_niftysmallcap250list'],
              'NIFTY MICROCAP 250': ['ind_niftymicrocap250_list', 'ind_niftymicrocap250list']}


def index_members(index):
    """Official member symbols from NSE's index list file (published by NSE Indices)."""
    import csv
    import io
    for name in LIST_FILES.get(index, []):
        for host in ('https://nsearchives.nseindia.com/content/indices/', 'https://www.niftyindices.com/IndexConstituent/',
                     'https://archives.nseindia.com/content/indices/'):
            try:
                r = session().get(host + name + '.csv', timeout=30)
            except requests.RequestException:
                continue
            if r.status_code == 200 and 'Symbol' in r.text[:300]:
                syms = [row['Symbol'].strip() for row in csv.DictReader(io.StringIO(r.text)) if row.get('Symbol')]
                if len(syms) >= int(INDEX_SIZE.get(index, 10) * 0.9):
                    return syms
    raise SourceError(f'{index}: member list file unavailable')


def _yahoo_priced(index):
    import yfinance as yf
    syms = index_members(index)
    df = yf.download([s + '.NS' for s in syms], period='1y', interval='1d', auto_adjust=False,
                     group_by='ticker', threads=True, progress=False)
    hist = {}
    for s in syms:
        try:
            h = df[s + '.NS'].dropna(subset=['Close', 'High', 'Low'])
        except KeyError:
            continue
        if len(h) >= 2:
            hist[s] = h
    if not hist:
        return []
    latest = max(h.index[-1].date() for h in hist.values())     # last session (works on weekends too)
    rows = []
    for s, h in hist.items():
        if h.index[-1].date() != latest:
            continue
        last, prev = round(float(h['Close'].iloc[-1]), 2), round(float(h['Close'].iloc[-2]), 2)
        rows.append({'symbol': s, 'last': last, 'prev': prev, 'chg': round(last - prev, 2),
                     'pct': (last - prev) / prev * 100, 'day_high': float(h['High'].iloc[-1]),
                     'day_low': float(h['Low'].iloc[-1]), 'year_high': float(h['High'].max()),
                     'year_low': float(h['Low'].min())})
    return rows


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


def quote_raw(symbol):
    """Full quote JSON: old /api/quote-equity first, then the newer GetQuoteApi (the old one is often blocked)."""
    try:
        j = get('/api/quote-equity', {'symbol': symbol}, retries=1)
        if (j.get('priceInfo') or {}).get('lastPrice') is not None:
            return j
    except SourceError:
        pass
    return get('/api/NextApi/apiClient/GetQuoteApi',
               {'functionName': 'getSymbolData', 'marketType': 'N', 'series': 'EQ', 'symbol': symbol}, retries=2)


def quote(symbol):
    """Live/closing quote: {'price','chg','pct','prev','time','name'}."""
    j = quote_raw(symbol)
    p = j.get('priceInfo') or {}
    price = _f(p.get('lastPrice')) or _f(find_field(j, r'^lastprice$', r'^ltp$', r'lasttradedprice', r'^closeprice$'))
    if price is None:
        _save_raw(f'quote_{symbol}', j)
        raise SourceError(f'quote {symbol}: no price')
    prev = _f(p.get('previousClose')) or _f(find_field(j, r'^previousclose$', r'^prevclose$'))
    chg = _f(p.get('change')) if p else _f(find_field(j, r'^change$', r'^netchange$'))
    pct = _f(p.get('pChange')) if p else _f(find_field(j, r'^pchange$', r'^perchange$', r'percentchange'))
    if prev:
        chg = price - prev if chg is None else chg
        pct = (price - prev) / prev * 100 if pct is None else pct
    meta = j.get('metadata') or {}
    info = j.get('info') or {}
    upd = meta.get('lastUpdateTime') or find_field(j, r'lastupdatetime', r'timestamp') or ''
    return {'price': price, 'chg': chg or 0.0, 'pct': pct or 0.0, 'prev': prev,
            'time': parse_nse_date(str(upd)),
            'name': info.get('companyName') or find_field(j, r'^companyname$', r'^company_?name$') or symbol}


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
