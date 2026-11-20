"""Data for the Insights series (data-story carousels posted every other day).

Same rule as every other post: each number is taken from a data source and, wherever a second
source exists, compared with it. Anything that cannot be confirmed is left out or flagged as a
warning on the Telegram draft (Insights always need your approval).

Report lines are (status, message) tuples: 'ok' | 'warn' | 'fail'.
"""
import re
from datetime import date, timedelta

from ..util import log, today_ist
from . import nse

CR = 1e7                        # one crore in rupees
UNITS = {'lakh': 1e5, 'crore': 1e7, 'thousand': 1e3, 'million': 1e6, 'rupees': 1.0}


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r'[^0-9.\-]', '', str(v))
    try:
        return float(s) if s not in ('', '-', '.') else None
    except ValueError:
        return None


def _close(a, b, tol_pct):
    return a is not None and b is not None and b != 0 and abs(a - b) / abs(b) * 100 <= tol_pct


def fy_quarter(d):
    """30 Sep 2026 -> 'Q2 FY27' (Indian financial year starts in April)."""
    q = {6: 1, 9: 2, 12: 3, 3: 4}.get(d.month)
    if q is None:
        q = (d.month - 4) % 12 // 3 + 1
    fy = d.year + 1 if d.month >= 4 else d.year
    return f'Q{q} FY{fy % 100:02d}'


# ---------------------------------------------------------------- 1. quarterly results (profit growth)

def yahoo_quarters(symbol):
    """{quarter_end(date): {'profit': rupees, 'revenue': rupees}} from Yahoo's quarterly income statement."""
    import yfinance as yf
    t = yf.Ticker(symbol + '.NS')
    q = t.quarterly_income_stmt
    if q is None or q.empty:
        return {}
    out = {}
    pick = lambda names, c: next((float(q.loc[n, c]) for n in names if n in q.index and q.loc[n, c] == q.loc[n, c]), None)
    for c in q.columns:
        prof = pick(['Net Income', 'Net Income Common Stockholders', 'Net Income Including Noncontrolling Interests'], c)
        rev = pick(['Total Revenue', 'Operating Revenue'], c)
        if prof is not None:
            out[c.date()] = {'profit': prof, 'revenue': rev}
    return out


def nse_quarters(symbol):
    """Rows from NSE's results comparison: [{'end': date, 'profit': raw, 'revenue': raw, 'basis': str}].
    NSE does not state the unit in the JSON, so the unit is fixed by agreement with Yahoo (see verify)."""
    j = nse.get('/api/results-comparision', {'index': 'equities', 'symbol': symbol})
    lists = [v for v in (j.values() if isinstance(j, dict) else [j]) if isinstance(v, list)]
    out = []
    for lst in lists:
        for r in lst:
            if not isinstance(r, dict):
                continue
            end = nse.find_field(r, r'to_?dt$|to_?date$|todate|re_to', r'period_?end|qe_?date')
            d = nse.parse_nse_date(str(end)) if end else None
            prof = _num(nse.find_field(r, r'net_?prof|pro_?loss_?aft|net_?p_?l$|pat$', r'profit'))
            rev = _num(nse.find_field(r, r'net_?sale|rev_?op|income_?from_?op|revenue', r'total_?inc'))
            basis = str(nse.find_field(r, r'res_?type|consol|audit_?type') or '')
            if d and prof is not None:
                out.append({'end': d.date(), 'profit': prof, 'revenue': rev, 'basis': basis})
    if not out:
        raise nse.SourceError(f'results comparison {symbol}: no rows')
    return out, j


def _basis_label(b):
    b = b.lower()
    return 'Consolidated' if b.startswith('c') else 'Standalone' if b.startswith('s') else ''


def verified_results(symbol, yq=None, nq=None, allow_single=False):
    """Latest quarter vs the same quarter a year earlier, in rupees crore.
    Both quarters' net profit must agree between Yahoo and NSE (2%). Revenue is shown only if it
    agrees too. Returns (result or None, [report lines])."""
    rep = []
    yq = yq if yq is not None else yahoo_quarters(symbol)
    if not yq:
        return None, [('warn', f'{symbol}: no quarterly results on Yahoo')]
    q_end = max(yq)
    py_end = next((d for d in yq if abs((d - (q_end - timedelta(days=365))).days) <= 5), None)
    if py_end is None:
        return None, [('warn', f'{symbol}: year-ago quarter missing')]
    y_now, y_py = yq[q_end], yq[py_end]
    try:
        rows = nq if nq is not None else nse_quarters(symbol)[0]
    except nse.SourceError as e:
        if not allow_single:
            return None, [('warn', f'{symbol}: NSE results unavailable ({e}) - left out')]
        res = {'symbol': symbol, 'q_end': q_end, 'py_end': py_end, 'quarter': fy_quarter(q_end),
               'py_quarter': fy_quarter(py_end), 'profit': round(y_now['profit'] / CR, 2),
               'profit_py': round(y_py['profit'] / CR, 2), 'basis': '', 'single': True}
        if y_now.get('revenue') and y_py.get('revenue'):
            res['revenue'], res['revenue_py'] = round(y_now['revenue'] / CR, 2), round(y_py['revenue'] / CR, 2)
        if res['profit_py'] > 0:
            res['growth'] = round((res['profit'] - res['profit_py']) / res['profit_py'] * 100, 1)
        return res, [('warn', f'{symbol} {res["quarter"]}: Yahoo figures only (NSE results unavailable) - please check')]
    best = None
    for unit_name, unit in UNITS.items():
        for basis in sorted({r['basis'] for r in rows}):
            now = next((r for r in rows if r['end'] == q_end and r['basis'] == basis), None)
            pre = next((r for r in rows if r['end'] == py_end and r['basis'] == basis), None)
            if not now or not pre:
                continue
            if _close(now['profit'] * unit, y_now['profit'], 2) and _close(pre['profit'] * unit, y_py['profit'], 2):
                best = (unit, basis, now, pre)
                break
        if best:
            break
    if not best:
        return None, [('warn', f'{symbol}: NSE and Yahoo profit figures do not agree - left out')]
    unit, basis, now, pre = best
    res = {'symbol': symbol, 'q_end': q_end, 'py_end': py_end, 'quarter': fy_quarter(q_end), 'py_quarter': fy_quarter(py_end),
           'profit': round(now['profit'] * unit / CR, 2), 'profit_py': round(pre['profit'] * unit / CR, 2),
           'basis': _basis_label(basis)}
    if now['revenue'] and pre['revenue'] and _close(now['revenue'] * unit, y_now['revenue'] or 0, 2) \
            and _close(pre['revenue'] * unit, y_py['revenue'] or 0, 2):
        res['revenue'], res['revenue_py'] = round(now['revenue'] * unit / CR, 2), round(pre['revenue'] * unit / CR, 2)
    if res['profit_py'] > 0:
        res['growth'] = round((res['profit'] - res['profit_py']) / res['profit_py'] * 100, 1)
    rep.append(('ok', f'{symbol} {res["quarter"]}: net profit Rs {res["profit_py"]} cr -> Rs {res["profit"]} cr, '
                      f'NSE = Yahoo' + ('' if 'revenue' in res else ' (revenue definitions differ - revenue not shown)')))
    return res, rep


def profit_growth_scan(universe='NIFTY 500', min_growth=100.0, min_profit_cr=10.0, cache=None):
    """Companies whose latest-quarter net profit grew at least min_growth % YoY (profit positive both years).
    Yahoo is scanned first (cheap); only candidates are confirmed against NSE.
    cache: dict symbol -> yahoo quarters (filled in place so repeat runs are fast)."""
    rows, _ = nse.index_constituents(universe)
    rep, cands = [], []
    cache = cache if cache is not None else {}
    fresh_from = today_ist() - timedelta(days=150)      # only the current results season
    for r in rows:
        s = r['symbol']
        try:
            yq = cache.get(s)
            if yq is None:
                yq = yahoo_quarters(s)
                cache[s] = yq
        except Exception as e:                              # noqa: BLE001
            log.info('yahoo %s: %s', s, e); continue
        if not yq:
            continue
        q_end = max(yq)
        py_end = next((d for d in yq if abs((d - (q_end - timedelta(days=365))).days) <= 5), None)
        if q_end < fresh_from or not py_end:
            continue
        a, b = yq[q_end]['profit'], yq[py_end]['profit']
        if b > 0 and a / CR >= min_profit_cr and (a - b) / b * 100 >= min_growth * 0.95:
            cands.append((s, r))
    out = []
    for s, r in cands:
        res, rr = verified_results(s, cache.get(s))
        rep += rr
        if res and res.get('growth', 0) >= min_growth and res['profit'] >= min_profit_cr:
            res['last'], res['pct'] = r['last'], r['pct']
            out.append(res)
    out.sort(key=lambda x: x['growth'], reverse=True)
    rep.append(('ok', f'{universe}: {len(rows)} stocks scanned, {len(cands)} candidates, {len(out)} confirmed by NSE'))
    return out, rep


# ---------------------------------------------------------------- 2. how major assets did last month

ASSETS = [  # (label, Yahoo symbol, NSE index name for the cross-check or None, value format)
    ('Nifty 50', '^NSEI', 'NIFTY 50', '{:,.2f}'), ('Sensex', '^BSESN', None, '{:,.2f}'),
    ('Nifty Bank', '^NSEBANK', 'NIFTY BANK', '{:,.2f}'), ('Gold', 'GC=F', None, '${:,.2f}'),
    ('Silver', 'SI=F', None, '${:,.2f}'), ('Brent Crude', 'BZ=F', None, '${:,.2f}'),
    ('US Dollar / Rupee', 'INR=X', None, '{:,.2f}'), ('Nasdaq', '^IXIC', None, '{:,.2f}'),
    ('S&P 500', '^GSPC', None, '{:,.2f}'), ('Bitcoin', 'BTC-USD', None, '${:,.0f}'),
]


def last_complete_month(today=None):
    t = today or today_ist()
    first = t.replace(day=1)
    end = first - timedelta(days=1)
    return end.year, end.month


def nse_index_close_on_or_before(index, d):
    """Official NSE closing value of an index on the last trading day on or before d."""
    j = nse.get('/api/historical/indicesHistory',
                {'indexType': index, 'from': (d - timedelta(days=10)).strftime('%d-%m-%Y'), 'to': d.strftime('%d-%m-%Y')})
    best, recs = None, []
    data = j.get('data', j) if isinstance(j, dict) else j
    lists = [data] if isinstance(data, list) else [v for v in data.values() if isinstance(v, list)] if isinstance(data, dict) else []
    for lst in lists:
        for r in lst:
            if not isinstance(r, dict):
                continue
            ts = nse.find_field(r, r'timestamp|date')
            cl = _num(nse.find_field(r, r'close_?index|close'))
            dd = nse.parse_nse_date(str(ts)) if ts else None
            if dd and cl:
                recs.append((dd.date(), cl))
    recs = [x for x in recs if x[0] <= d]
    if recs:
        best = max(recs)
    if not best:
        raise nse.SourceError(f'{index} history: no rows')
    return best


def month_assets(year, month):
    """[{label, start, end, pct, fmt}] from the last close of the previous month to the last close of the month."""
    import yfinance as yf
    start_d = date(year, month, 1) - timedelta(days=1)
    end_d = (date(year + month // 12, month % 12 + 1, 1)) - timedelta(days=1)
    rep, out = [], []
    for label, ysym, nse_name, fmt in ASSETS:
        try:
            h = yf.Ticker(ysym).history(start=start_d - timedelta(days=12), end=end_d + timedelta(days=1),
                                        interval='1d', auto_adjust=False).dropna(subset=['Close'])
        except Exception as e:                              # noqa: BLE001
            rep.append(('warn', f'{label}: Yahoo unavailable ({e}) - left out')); continue
        before = h[[d.date() <= start_d for d in h.index]]
        upto = h[[d.date() <= end_d for d in h.index]]
        if before.empty or upto.empty or upto.index[-1].date() < end_d - timedelta(days=5):
            rep.append(('warn', f'{label}: month-end data missing - left out')); continue
        a, b = float(before['Close'].iloc[-1]), float(upto['Close'].iloc[-1])
        if nse_name:
            try:
                (_, na), (_, nb) = nse_index_close_on_or_before(nse_name, start_d), nse_index_close_on_or_before(nse_name, end_d)
                if not (_close(a, na, 0.05) and _close(b, nb, 0.05)):
                    rep.append(('warn', f'{label}: Yahoo {a:.2f}/{b:.2f} vs NSE {na:.2f}/{nb:.2f} differ - left out')); continue
                a, b = na, nb
                rep.append(('ok', f'{label}: month-start and month-end closes match NSE'))
            except nse.SourceError as e:
                rep.append(('warn', f'{label}: NSE history unavailable ({e}); Yahoo only'))
        else:
            rep.append(('warn', f'{label}: single source (Yahoo) {a:.2f} -> {b:.2f}'))
        out.append({'label': label, 'start': a, 'end': b, 'pct': round((b - a) / a * 100, 2), 'fmt': fmt})
    out.sort(key=lambda x: x['pct'], reverse=True)
    return out, rep


# ---------------------------------------------------------------- 3. most valuable listed companies

def quote_full(symbol):
    j = nse.quote_raw(symbol)
    q = nse.quote(symbol) if not (j.get('priceInfo') or {}).get('lastPrice') else None
    p, info, sec = j.get('priceInfo') or {}, j.get('info') or {}, j.get('securityInfo') or {}
    price = _num(p.get('lastPrice')) or (q and q['price'])
    shares = _num(sec.get('issuedSize')) or _num(nse.find_field(j, r'issued_?size', r'issued_?cap', r'^shares'))
    if not price or not shares:
        raise nse.SourceError(f'{symbol}: price or issued size missing')
    return {'symbol': symbol, 'name': info.get('companyName') or (q and q['name']) or symbol, 'price': price,
            'shares': shares, 'pct': _num(p.get('pChange')) or (q and q['pct']) or 0.0}


def mcap_leaders(n=10, universe='NIFTY 100'):
    """Top n by full market cap (NSE issued shares x NSE price), each compared with Yahoo's market cap (3%).
    Also the change over the last 5 sessions using Yahoo closes and the same share count."""
    import yfinance as yf
    rows, _ = nse.index_constituents(universe)
    rep, cands = [], []
    for r in rows:
        try:
            cands.append(quote_full(r['symbol']))
        except nse.SourceError as e:
            rep.append(('warn', str(e)))
    for c in cands:
        c['mcap_cr'] = c['price'] * c['shares'] / CR
    cands.sort(key=lambda c: c['mcap_cr'], reverse=True)
    out = []
    for c in cands[: n + 4]:
        try:
            t = yf.Ticker(c['symbol'] + '.NS')
            ymc = float(t.fast_info['marketCap'])
            h = t.history(period='15d', interval='1d', auto_adjust=False).dropna(subset=['Close'])
        except Exception as e:                              # noqa: BLE001
            rep.append(('warn', f'{c["symbol"]}: Yahoo unavailable ({e}) - left out')); continue
        if not _close(c['mcap_cr'] * CR, ymc, 3):
            rep.append(('warn', f'{c["symbol"]}: NSE Rs {c["mcap_cr"]:,.0f} cr vs Yahoo Rs {ymc / CR:,.0f} cr - left out'))
            continue
        if len(h) >= 6 and _close(float(h['Close'].iloc[-1]), c['price'], 0.5):
            wk = float(h['Close'].iloc[-6])
            c['week_pct'] = round((c['price'] - wk) / wk * 100, 2)
            c['week_cr'] = round((c['price'] - wk) * c['shares'] / CR, 0)
        out.append(c)
        if len(out) == n:
            break
    rep.append(('ok', f'top {len(out)} by market cap: NSE issued shares x price, each within 3% of Yahoo'))
    return out, rep


# ---------------------------------------------------------------- 4. one year of Nifty 50 (wealth creators)

def one_year_returns(universe='NIFTY 50'):
    """Price return over one year for each stock (split-adjusted, dividends not included).
    Today's price is NSE's; Yahoo's latest close must agree within 0.5% or the stock is left out."""
    import yfinance as yf
    rows, _ = nse.index_constituents(universe)
    t = today_ist()
    ago = t.replace(year=t.year - 1) if not (t.month == 2 and t.day == 29) else t.replace(year=t.year - 1, day=28)
    syms = [r['symbol'] for r in rows]
    df = yf.download([s + '.NS' for s in syms], start=ago - timedelta(days=10), interval='1d', auto_adjust=False,
                     group_by='ticker', threads=True, progress=False)
    out, rep, bad = [], [], 0
    for r in rows:
        try:
            h = df[r['symbol'] + '.NS'].dropna(subset=['Close'])
        except KeyError:
            continue
        old = h[[d.date() <= ago for d in h.index]]
        if old.empty or not _close(float(h['Close'].iloc[-1]), r['last'], 0.5):
            bad += 1; continue
        base = float(old['Close'].iloc[-1])
        out.append({'symbol': r['symbol'], 'then': round(base, 2), 'now': r['last'],
                    'pct': round((r['last'] - base) / base * 100, 2), 'then_date': old.index[-1].date()})
    out.sort(key=lambda x: x['pct'], reverse=True)
    rep.append(('ok', f'{universe}: {len(out)} stocks with 1-year price return'
                      + (f'; {bad} left out (no year-old price or Yahoo/NSE price differ)' if bad else '')))
    return out, ago, rep


# ---------------------------------------------------------------- 5. sector scorecard (1 week / 1 month / 1 year)

SECTOR_INDICES = ['NIFTY IT', 'NIFTY BANK', 'NIFTY AUTO', 'NIFTY PHARMA', 'NIFTY FMCG', 'NIFTY METAL', 'NIFTY REALTY',
                  'NIFTY ENERGY', 'NIFTY PSU BANK', 'NIFTY MEDIA', 'NIFTY FINANCIAL SERVICES', 'NIFTY OIL & GAS',
                  'NIFTY HEALTHCARE INDEX', 'NIFTY CONSUMER DURABLES', 'NIFTY INDIA DEFENCE', 'NIFTY CAPITAL MARKETS']
YAHOO_SECTOR = {'NIFTY IT': '^CNXIT', 'NIFTY BANK': '^NSEBANK', 'NIFTY AUTO': '^CNXAUTO', 'NIFTY PHARMA': '^CNXPHARMA',
                'NIFTY FMCG': '^CNXFMCG', 'NIFTY METAL': '^CNXMETAL', 'NIFTY REALTY': '^CNXREALTY'}


def sector_scorecard():
    """From NSE allIndices: % change over 1 week (vs oneWeekAgo), 1 month and 1 year (NSE's own fields).
    1-month changes are compared with Yahoo where Yahoo carries the index (0.5 percentage points)."""
    import yfinance as yf
    j = nse.get('/api/allIndices')
    by = {r.get('index'): r for r in j.get('data', [])}
    out, rep = [], []
    for name in SECTOR_INDICES + ['NIFTY 50']:
        r = by.get(name)
        if not r:
            continue
        last = _num(r.get('last'))
        wk = _num(r.get('oneWeekAgo'))
        m1 = _num(r.get('perChange30d'))
        y1 = _num(r.get('perChange365d'))
        if last is None or m1 is None or y1 is None:
            rep.append(('warn', f'{name}: NSE period changes missing - left out')); continue
        row = {'name': name, 'last': last, 'm1': round(m1, 2), 'y1': round(y1, 2),
               'w1': round((last - wk) / wk * 100, 2) if wk else None}
        ys = YAHOO_SECTOR.get(name)
        if ys:
            try:
                h = yf.Ticker(ys).history(period='45d', interval='1d', auto_adjust=False).dropna(subset=['Close'])
                mo = _num(r.get('oneMonthAgoVal')) or _num(r.get('oneMonthAgo'))
                if mo:
                    ymo = (last - mo) / mo * 100
                    if abs(ymo - m1) > 0.5:
                        rep.append(('warn', f'{name}: NSE 1-month {m1:.2f}% vs own month-ago level {ymo:.2f}%'))
                if len(h) and not _close(float(h['Close'].iloc[-1]), last, 0.1):
                    rep.append(('warn', f'{name}: Yahoo level {float(h["Close"].iloc[-1]):.2f} vs NSE {last:.2f}'))
            except Exception as e:                          # noqa: BLE001
                rep.append(('warn', f'{name}: Yahoo check skipped ({e})'))
        out.append(row)
    rep.append(('ok', f'{len(out)} indices with 1-week, 1-month and 1-year change from NSE'))
    return out, rep


# ---------------------------------------------------------------- 6. 100-baggers over 10 years

def hundred_baggers(years=10, multiple=100, universes=('NIFTY 500', 'NIFTY MICROCAP 250')):
    """Stocks of today's Nifty 500 + Microcap 250 whose price rose `multiple` times or more over `years` years
    (₹1 lakh -> ₹1 crore at 100x). Split/bonus-adjusted price change, dividends not included.
    Checks: today's price is NSE's and Yahoo's latest close must agree within 0.5%; the stock must have traded
    `years` ago; histories with a one-day jump of more than 60% (usually a missed split/bonus adjustment in the
    data) are left out and reported, not guessed."""
    import yfinance as yf
    t = today_ist()
    ago = t.replace(year=t.year - years) if not (t.month == 2 and t.day == 29) else t.replace(year=t.year - years, day=28)
    rows, rep, seen = [], [], set()
    for u in universes:
        try:
            got, _ = nse.index_constituents(u)
        except nse.SourceError as e:
            rep.append(('warn', f'{u}: list unavailable ({e})'))
            continue
        for r in got:
            if r['symbol'] not in seen and r.get('last'):
                seen.add(r['symbol'])
                rows.append(r)
    if not rows:
        return [], ago, rep + [('fail', 'no stock list available')]
    syms = [r['symbol'] for r in rows]
    out, bad, young, jumpy = [], 0, 0, []
    for i in range(0, len(syms), 150):                      # Yahoo in batches
        part = syms[i:i + 150]
        df = yf.download([s + '.NS' for s in part], start=ago - timedelta(days=12), interval='1d', auto_adjust=False,
                         group_by='ticker', threads=True, progress=False)
        for s in part:
            r = next(x for x in rows if x['symbol'] == s)
            try:
                h = df[s + '.NS'].dropna(subset=['Close'])
            except KeyError:
                continue
            if h.empty:
                continue
            old = h[[d.date() <= ago for d in h.index]]
            if old.empty:
                young += 1; continue
            if not _close(float(h['Close'].iloc[-1]), r['last'], 0.5):
                bad += 1; continue
            base = float(old['Close'].iloc[-1])
            if base <= 0:
                continue
            mult = r['last'] / base
            if mult < multiple:
                continue
            ch = h['Close'].pct_change().abs()
            if (ch > 0.6).any():
                jumpy.append(s); continue
            out.append({'symbol': s, 'then': round(base, 2), 'then_date': old.index[-1].date(), 'now': r['last'],
                        'multiple': round(mult, 1), 'value': round(100000 * mult)})
    out.sort(key=lambda x: x['multiple'], reverse=True)
    rep.append(('ok', f'{len(rows)} stocks scanned ({", ".join(universes)}), {len(out)} rose {multiple}x or more in '
                      f'{years} years' + (f'; {young} not listed {years} years ago' if young else '')
                      + (f'; {bad} left out (Yahoo/NSE price differ)' if bad else '')))
    if jumpy:
        rep.append(('warn', f'{len(jumpy)} possible 100x stocks left out because their price history has a one-day '
                            f'jump over 60% (likely an unadjusted split/bonus): ' + ', '.join(jumpy[:10])))
    return out, ago, rep
