"""Market numbers with cross-checking.

Rule: a number used on a card comes from NSE (official) where NSE publishes it,
and is compared with Yahoo Finance. A mismatch above TOLERANCE blocks the card.
If only Yahoo is available the value is used but marked as single-source.
"""
from ..util import log, today_ist
from . import nse

TOLERANCE_PCT = 0.05   # max allowed gap between two sources for a closing level

# display name -> (NSE allIndices name or None, Yahoo symbol or None)
KEY_INDICES = {
    'NIFTY 50': ('NIFTY 50', '^NSEI'),
    'SENSEX': (None, '^BSESN'),
    'NIFTY BANK': ('NIFTY BANK', '^NSEBANK'),
    'NIFTY MIDCAP 100': ('NIFTY MIDCAP 100', None),
    'NIFTY SMALLCAP 100': ('NIFTY SMALLCAP 100', None),
    'INDIA VIX': ('INDIA VIX', '^INDIAVIX'),
}
SECTORS = {
    'IT': ('NIFTY IT', '^CNXIT'), 'BANK': ('NIFTY BANK', '^NSEBANK'), 'AUTO': ('NIFTY AUTO', '^CNXAUTO'),
    'PHARMA': ('NIFTY PHARMA', '^CNXPHARMA'), 'FMCG': ('NIFTY FMCG', '^CNXFMCG'),
    'METAL': ('NIFTY METAL', '^CNXMETAL'), 'REALTY': ('NIFTY REALTY', '^CNXREALTY'),
    'ENERGY': ('NIFTY ENERGY', '^CNXENERGY'), 'PSU BANK': ('NIFTY PSU BANK', '^CNXPSUBANK'),
    'MEDIA': ('NIFTY MEDIA', '^CNXMEDIA'), 'FIN SERVICE': ('NIFTY FINANCIAL SERVICES', None),
    'OIL & GAS': ('NIFTY OIL & GAS', None),
}
GLOBAL = [
    ('Dow Jones', '^DJI', '{:,.2f}'), ('S&P 500', '^GSPC', '{:,.2f}'), ('Nasdaq', '^IXIC', '{:,.2f}'),
    ('Nikkei 225', '^N225', '{:,.2f}'), ('Hang Seng', '^HSI', '{:,.2f}'),
    ('Brent Crude', 'BZ=F', '${:,.2f}'), ('Gold', 'GC=F', '${:,.2f}'), ('USD / INR', 'INR=X', '{:,.2f}'),
]


def yahoo_daily(symbol):
    """Last completed daily bar: {'close','prev','chg','pct','date'}."""
    import yfinance as yf
    h = yf.Ticker(symbol).history(period='10d', interval='1d', auto_adjust=False)
    h = h.dropna(subset=['Close'])
    if len(h) < 2:
        raise nse.SourceError(f'Yahoo {symbol}: not enough bars')
    close, prev = float(h['Close'].iloc[-1]), float(h['Close'].iloc[-2])
    return {'close': close, 'prev': prev, 'chg': close - prev, 'pct': (close - prev) / prev * 100,
            'date': h.index[-1].date()}


def _merge(name, nse_row, ysym, report, nse_date=None):
    """Combine NSE + Yahoo for one index; append check lines to report. Returns quote or None."""
    y = None
    if ysym:
        try:
            y = yahoo_daily(ysym)
        except Exception as e:                       # noqa: BLE001 - any failure = source missing
            log.warning('Yahoo %s failed: %s', ysym, e)
    if nse_row:
        q = {'name': name, 'close': nse_row['last'], 'chg': nse_row['chg'], 'pct': nse_row['pct'],
             'prev': nse_row['prev'], 'date': nse_date, 'source': 'NSE'}
        if y:
            diff = abs(q['close'] - y['close']) / q['close'] * 100
            if diff > TOLERANCE_PCT:
                report.append(('fail', f'{name}: NSE {q["close"]:,.2f} vs Yahoo {y["close"]:,.2f} differ {diff:.3f}%'))
                return None
            report.append(('ok', f'{name} {q["close"]:,.2f}: NSE = Yahoo (gap {diff:.3f}%)'))
        else:
            report.append(('ok', f'{name} {q["close"]:,.2f}: NSE (official)'))
        return q
    if y:
        report.append(('warn', f'{name} {y["close"]:,.2f}: Yahoo only, single source - check before approving'))
        return {'name': name, 'close': y['close'], 'chg': y['chg'], 'pct': y['pct'], 'prev': y['prev'],
                'date': y['date'], 'source': 'Yahoo'}
    report.append(('fail', f'{name}: no source available'))
    return None


def market_snapshot(names=KEY_INDICES):
    """Quotes for the given index map + breadth; report lists every check made."""
    report = []
    try:
        rows, ts = nse.all_indices()
        nse_date = ts.date() if ts else None
    except nse.SourceError as e:
        log.warning('NSE allIndices unavailable: %s', e)
        rows, nse_date = {}, None
        report.append(('warn', 'NSE index feed unavailable - using Yahoo where possible'))
    quotes = {}
    for name, (nse_name, ysym) in names.items():
        q = _merge(name, rows.get(nse_name) if nse_name else None, ysym, report, nse_date)
        if q:
            quotes[name] = q
    breadth = None
    n500 = rows.get('NIFTY 500')
    if n500 and (n500['advances'] or n500['declines']):
        breadth = {'advances': n500['advances'], 'declines': n500['declines'], 'universe': 'Nifty 500'}
    return quotes, breadth, nse_date, report


def sector_snapshot():
    q, _, _, report = market_snapshot(SECTORS)
    return q, report


def movers(index='NIFTY 50', n=5):
    rows, _ = nse.index_constituents(index)
    rows = sorted(rows, key=lambda r: r['pct'], reverse=True)
    return rows[:n], list(reversed(rows[-n:]))


def global_snapshot():
    out, report = [], []
    for name, sym, fmt in GLOBAL:
        try:
            y = yahoo_daily(sym)
            out.append({'name': name, 'value': fmt.format(y['close']), 'close': y['close'],
                        'pct': y['pct'], 'date': y['date']})
            report.append(('ok', f'{name} {fmt.format(y["close"])} ({y["pct"]:+.2f}%) as of {y["date"]}'))
        except Exception as e:                       # noqa: BLE001
            report.append(('warn', f'{name}: unavailable ({e.__class__.__name__}) - left off the card'))
    return out, report


def traded_today(nse_date, quotes):
    """True if today's session data is present (works on holidays without a holiday list)."""
    today = today_ist()
    if nse_date:
        return nse_date == today
    q = quotes.get('NIFTY 50')
    return bool(q and q.get('date') == today)


# Market-cap segments = NSE's own index definitions (objective, published by NSE)
CAP_SEGMENTS = [
    ('Large Cap', 'NIFTY 100'),
    ('Mid Cap', 'NIFTY MIDCAP 150'),
    ('Small Cap', 'NIFTY SMALLCAP 250'),
    ('Micro Cap', 'NIFTY MICROCAP 250'),
]


def cap_movers(n=5):
    """{segment: {'index', 'gainers', 'losers', 'count'}} + report. Each % is re-computed from
    last price and previous close; a mismatch above 0.02 points drops that stock."""
    out, report = {}, []
    for seg, index in CAP_SEGMENTS:
        try:
            rows, ts = nse.index_constituents(index)
        except nse.SourceError as e:
            report.append(('fail', f'{seg} ({index}): NSE data unavailable ({e})'))
            continue
        good, bad = [], []
        for r in rows:
            if r.get('prev'):
                calc = (r['last'] - r['prev']) / r['prev'] * 100
                (good if abs(calc - r['pct']) <= 0.02 else bad).append(r)
            else:
                bad.append(r)
        if bad:
            report.append(('warn', f'{seg}: {len(bad)} stock(s) left out - % change did not match price data'))
        if len(good) < 2 * n:
            report.append(('fail', f'{seg}: only {len(good)} usable stocks'))
            continue
        ranked = sorted(good, key=lambda r: r['pct'], reverse=True)
        gainers = [r for r in ranked[:n] if r['pct'] > 0]
        losers = [r for r in reversed(ranked[-n:]) if r['pct'] < 0]
        out[seg] = {'index': index, 'gainers': gainers, 'losers': losers, 'count': len(good),
                    'date': ts.date() if ts else None}
        report.append(('ok', f'{seg} ({index}): {len(good)} stocks from NSE, % re-computed from prices'))
    return out, report


# ---------------------------------------------------------------- weekly all-time highs / 52-week lows

CROSS_TOL_PCT = 0.5      # Yahoo weekly high/low vs NSE 52-week high/low


def weekly_history(symbols):
    """{symbol: DataFrame of weekly bars (split-adjusted OHLC)} from Yahoo, full history."""
    import yfinance as yf
    tickers = [s + '.NS' for s in symbols]
    out = {}
    for i in range(0, len(tickers), 100):                     # batches keep Yahoo happy
        chunk = tickers[i:i + 100]
        df = yf.download(chunk, period='max', interval='1wk', auto_adjust=False, group_by='ticker',
                         threads=True, progress=False)
        for t in chunk:
            try:
                h = df[t].dropna(subset=['High', 'Low', 'Close'])
            except KeyError:
                continue
            if len(h):
                out[t[:-3]] = h
    return out


def weekly_extremes(week_monday, n=10):
    """Per market-cap group: stocks that made an all-time high / 52-week low in the week starting week_monday.

    A stock is listed only if (1) Yahoo's full weekly history shows this week's high above every earlier
    week (or this week's low below the previous 51 weeks), (2) it has at least 52 weeks of history, and
    (3) NSE's own 52-week high/low agrees with Yahoo's level within 0.5%."""
    result, report = {}, []
    for seg, index in CAP_SEGMENTS:
        try:
            rows, _ = nse.index_constituents(index)
        except nse.SourceError as e:
            report.append(('fail', f'{seg} ({index}): NSE list unavailable ({e})'))
            continue
        nse_by = {r['symbol']: r for r in rows}
        hist = weekly_history(list(nse_by))
        ath, low, young, mismatch, stale = [], [], 0, 0, 0
        for sym, h in hist.items():
            if h.index[-1].date() != week_monday:
                stale += 1; continue
            if len(h) < 53:
                young += 1; continue
            cur, prev_close = h.iloc[-1], float(h['Close'].iloc[-2])
            wk = {'symbol': sym, 'close': float(cur['Close']),
                  'week_pct': (float(cur['Close']) - prev_close) / prev_close * 100}
            r = nse_by[sym]
            if float(cur['High']) > float(h['High'].iloc[:-1].max()):
                lvl = float(cur['High'])
                if r.get('year_high') and abs(lvl - r['year_high']) / lvl * 100 <= CROSS_TOL_PCT:
                    ath.append({**wk, 'level': lvl})
                else:
                    mismatch += 1
            if float(cur['Low']) < float(h['Low'].iloc[-52:-1].min()):
                lvl = float(cur['Low'])
                if r.get('year_low') and abs(lvl - r['year_low']) / lvl * 100 <= CROSS_TOL_PCT:
                    low.append({**wk, 'level': lvl})
                else:
                    mismatch += 1
        if len(hist) < 0.9 * len(rows):
            report.append(('fail', f'{seg}: Yahoo history for only {len(hist)} of {len(rows)} stocks'))
            continue
        ath.sort(key=lambda x: x['week_pct'], reverse=True)
        low.sort(key=lambda x: x['week_pct'])
        result[seg] = {'index': index, 'ath': ath[:n], 'low': low[:n], 'ath_count': len(ath),
                       'low_count': len(low), 'checked': len(hist)}
        msg = (f'{seg} ({index}): {len(hist)} stocks checked; {len(ath)} all-time highs, {len(low)} 52-week lows')
        extra = [x for x in (f'{young} listed < 1 year skipped' if young else '',
                             f'{mismatch} dropped (Yahoo and NSE levels differ)' if mismatch else '',
                             f'{stale} without data for this week' if stale else '') if x]
        report.append(('ok', msg + ('; ' + ', '.join(extra) if extra else '')))
    return result, report


# ---------------------------------------------------------------- company quotes for news cards

import difflib
import re as _re

from .. import store
from ..util import now_ist

_SUFFIX = _re.compile(r'\b(limited|ltd|india|the|co|company|corporation|corp|industries|inc)\b\.?', _re.I)


def _norm(name):
    return _re.sub(r'[^a-z0-9 ]', ' ', _SUFFIX.sub(' ', name.lower())).split()


def equity_master():
    """NSE equity list, cached on the data branch for 7 days."""
    cached = store.read_json('cache/equity_list.json')
    if cached and (now_ist().timestamp() - cached['at']) < 7 * 86400:
        return cached['rows']
    rows = nse.equity_list()
    store.write_json('cache/equity_list.json', {'at': now_ist().timestamp(), 'rows': rows})
    return rows


def find_symbol(company, master):
    """Exact symbol, exact normalised name, then a strict fuzzy match. None if unsure."""
    up = company.strip().upper()
    for sym, name in master:
        if sym == up:
            return sym, name
    target = ' '.join(_norm(company))
    best, score = None, 0.0
    for sym, name in master:
        n = ' '.join(_norm(name))
        if n == target:
            return sym, name
        s = difflib.SequenceMatcher(None, target, n).ratio()
        if s > score:
            best, score = (sym, name), s
    return best if score >= 0.92 else None


def company_quotes(companies, report, limit=3):
    """Quotes for companies named in a story. Each price is NSE's; % is re-computed from price and
    previous close, and compared with Yahoo when available. Anything unsure is left off the card."""
    out = []
    if not companies:
        return out
    try:
        master = equity_master()
    except nse.SourceError as e:
        report.warn(f'company price boxes skipped: NSE equity list unavailable ({e})')
        return out
    for c in companies[:limit]:
        hit = find_symbol(c, master)
        if not hit:
            report.warn(f'no NSE listing matched "{c}" - no price box for it')
            continue
        sym, name = hit
        try:
            q = nse.quote(sym)
        except nse.SourceError as e:
            report.warn(f'{sym}: quote unavailable ({e})')
            continue
        if q['prev']:
            calc = (q['price'] - q['prev']) / q['prev'] * 100
            if abs(calc - q['pct']) > 0.02:
                report.warn(f'{sym}: % change does not match prices - no price box')
                continue
        try:
            y = yahoo_daily(sym + '.NS')
            gap = abs(y['close'] - q['price']) / q['price'] * 100
            if gap > 0.5:
                report.warn(f'{sym}: NSE ₹{q["price"]:,.2f} vs Yahoo ₹{y["close"]:,.2f} - no price box')
                continue
            report.ok(f'{sym} ₹{q["price"]:,.2f} ({q["pct"]:+.2f}%): NSE = Yahoo')
        except Exception:                            # noqa: BLE001
            report.ok(f'{sym} ₹{q["price"]:,.2f} ({q["pct"]:+.2f}%): NSE')
        t = q['time'] or now_ist()
        out.append({'name': _re.sub(r'\s+Limited$', ' Ltd', name.strip()), 'symbol': sym, 'price': q['price'], 'chg': q['chg'],
                    'pct': q['pct'], 'time_text': f'{t.day} {t.strftime("%b")}, {t.strftime("%-I:%M %p")} IST'})
    return out
