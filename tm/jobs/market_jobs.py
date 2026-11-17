"""Data posts: every number comes from a data source and the caption is a fixed template (no AI)."""
import re
from datetime import date, timedelta

from .. import store
from ..render import cards
from ..sources import market, nse
from ..util import fmt_date, fmt_inr, log, now_ist, pct_change, signed, today_ist
from ..verify.checks import Report, check_sum
from ..writer.captions import assemble, tags
from .common import finish


ACRONYMS = {'IT', 'FMCG', 'PSU', 'VIX'}


def sector_label(name):
    """'PSU BANK' -> 'Nifty PSU Bank', 'IT' -> 'Nifty IT'."""
    words = [w if w in ACRONYMS else w.title() for w in name.replace('NIFTY ', '').split()]
    return 'Nifty ' + ' '.join(words)


def _move(q, unit='points'):
    word = 'up' if q['chg'] >= 0 else 'down'
    return f'{word} {fmt_inr(abs(q["chg"]))} {unit} ({abs(pct_change(q["close"], q["chg"])):.2f}%)'


def _allowed_quote(q):
    p = pct_change(q['close'], q['chg'])
    return [q['close'], q['chg'], p]


CLOSE_READY = (15, 35)          # NSE closes 3:30 PM IST; closing data is final a few minutes later


def _after_close(report, label):
    """Closing-data posts never run during market hours - intraday numbers are not closing numbers."""
    t = now_ist()
    if t.weekday() < 5 and (t.hour, t.minute) < CLOSE_READY:
        log.info('%s: market not closed yet (%s IST) - skipping', label, t.strftime('%H:%M'))
        try:
            from .. import telegram
            telegram.send_text(f'⏳ {label}: the market has not closed yet ({t.strftime("%-I:%M %p")} IST). '
                               f'This post uses closing data, so run it after 3:35 PM.')
        except Exception:                          # noqa: BLE001
            pass
        return False
    return True


def _session_or_skip(quotes, nse_date, report, force):
    if not market.traded_today(nse_date, quotes):
        if force:
            report.warn('no trading session found for today - showing the latest available close')
            return True
        log.info('no trading session today - skipping')
        return False
    return True


# ---------------------------------------------------------------- market close (3:50 PM)

def market_close(force=False):
    key = f'close:{today_ist()}'
    if store.seen('post', key) and not force:
        return
    if not _after_close(None, 'Market close'):
        return
    report = Report()
    need = ['NIFTY 50', 'SENSEX', 'NIFTY BANK']
    quotes, breadth, nse_date, rep = market.market_snapshot({k: market.KEY_INDICES[k] for k in need})
    report.extend(rep)
    if not _session_or_skip(quotes, nse_date, report, force):
        return
    if any(n not in quotes for n in need):
        report.fail('missing ' + ', '.join(n for n in need if n not in quotes))
    secs, rep2 = market.sector_snapshot()
    report.extend([('warn', m + ' - sector left out') if st == 'fail' else (st, m) for st, m in rep2])
    if not report.passed:
        finish('market_close', key, [], '', report)
        return
    n, s, b = quotes['NIFTY 50'], quotes['SENSEX'], quotes['NIFTY BANK']
    day = today_ist() if nse_date is None else nse_date
    verb = 'gains' if n['chg'] >= 0 else 'falls'
    head = f'Nifty {verb} *{fmt_inr(abs(n["chg"]), 0)} points*; Sensex ends at *{fmt_inr(s["close"], 0)}*'
    drivers, allowed = [], _allowed_quote(n) + _allowed_quote(s) + _allowed_quote(b)
    allowed += [abs(n['chg']), abs(s['chg']), abs(b['chg'])]
    if secs:
        ranked = sorted(secs.values(), key=lambda q: q['pct'], reverse=True)
        best, worst = ranked[0], ranked[-1]
        drivers.append(f'{sector_label(best["name"])} {"rose" if best["pct"] >= 0 else "fell"} '
                       f'{abs(best["pct"]):.2f}%, the best of all sectors')
        if worst is not best:
            drivers.append(f'{sector_label(worst["name"])} {"rose" if worst["pct"] >= 0 else "fell"} '
                           f'{abs(worst["pct"]):.2f}%, the weakest sector')
        allowed += [abs(best['pct']), abs(worst['pct'])]
    if breadth:
        drivers.append(f'{breadth["advances"]} of {breadth["universe"]} stocks advanced, {breadth["declines"]} declined')
        allowed += [breadth['advances'], breadth['declines'], 500]
    images = cards.market_close({'date_text': fmt_date(day, 'dow'), 'headline': head, 'seed': str(day),
                                 'theme': 'market_up' if n['chg'] >= 0 else 'market_down',
                                 'indices': [n, s, b], 'drivers': drivers, 'source': 'NSE, BSE closing data'})
    p1 = (f'On {fmt_date(day)}, the Nifty 50 closed at {fmt_inr(n["close"])}, {_move(n)}. '
          f'The Sensex ended at {fmt_inr(s["close"])}, {_move(s)}, and Nifty Bank closed at '
          f'{fmt_inr(b["close"])}, {_move(b)}.')
    p2 = ' '.join(x.rstrip('.') + '.' for x in drivers)
    caption = assemble(head, [p1, p2], 'NSE, BSE closing data', tags('#Nifty50', '#Sensex', '#StockMarketIndia',
                                                                       '#ShareMarket', '#MarketClose'))
    allowed += [day.day, day.year]
    if finish('market_close', key, images, caption, report, allowed):
        store.mark_seen('post', key)


# ---------------------------------------------------------------- daily overview carousel (4:30 PM)

def daily_overview(force=False):
    key = f'overview:{today_ist()}'
    if store.seen('post', key) and not force:
        return
    if not _after_close(None, 'Daily overview'):
        return
    report = Report()
    quotes, breadth, nse_date, rep = market.market_snapshot()
    core = ('NIFTY 50', 'SENSEX', 'NIFTY BANK')
    report.extend([(st, m) if st != 'fail' or m.startswith(core) else ('warn', m + ' - left out')
                   for st, m in rep])
    if not _session_or_skip(quotes, nse_date, report, force):
        return
    if 'NIFTY 50' not in quotes:
        report.fail('Nifty 50 missing')
    secs, rep2 = market.sector_snapshot()
    report.extend([('warn', m + ' - sector left out') if st == 'fail' else (st, m) for st, m in rep2])
    try:
        gainers, losers = market.movers('NIFTY 50', 5)
        report.ok('Nifty 50 movers from NSE')
    except nse.SourceError as e:
        gainers = losers = None
        report.warn(f'movers unavailable ({e}) - slide left out')
    extras_src, rep3 = market.global_snapshot()
    report.extend([r for r in rep3 if r[0] != 'ok'])
    extras = [e for e in extras_src if e['name'] in ('USD / INR', 'Brent Crude', 'Gold')]
    vix = quotes.get('INDIA VIX')
    if vix:
        extras.append({'name': 'India VIX', 'value': f'{vix["close"]:.2f}', 'pct': pct_change(vix['close'], vix['chg'])})
    if not report.passed:
        finish('daily_overview', key, [], '', report)
        return
    day = nse_date or today_ist()
    order = ['NIFTY 50', 'SENSEX', 'NIFTY BANK', 'NIFTY MIDCAP 100', 'NIFTY SMALLCAP 100', 'INDIA VIX']
    idx = [quotes[n] for n in order if n in quotes]
    sectors = [{'name': v['name'], 'pct': v['pct']} for v in secs.values()]
    n = quotes['NIFTY 50']
    images = cards.daily_overview({
        'theme': 'market_up' if n['chg'] >= 0 else 'market_down', 'seed': str(day),
        'tone': 'up' if n['chg'] >= 0 else 'down', 'date_text': fmt_date(day, 'dow'), 'headline': f'Daily market overview: *{fmt_date(day)}*',
        'indices': idx, 'breadth': breadth, 'sectors': sectors, 'gainers': gainers, 'losers': losers,
        'extras': extras, 'source': 'NSE, BSE, Yahoo Finance (FX, commodities)'})
    allowed = [day.day, day.year, 50, 500, 100]
    for q in idx:
        allowed += _allowed_quote(q) + [abs(q['chg'])]
    paras = [f'Nifty 50 closed at {fmt_inr(n["close"])}, {_move(n)}, on {fmt_date(day)}.']
    for nm in ('NIFTY MIDCAP 100', 'NIFTY SMALLCAP 100'):
        if nm in quotes:
            q = quotes[nm]
            paras[0] += f' {sector_label(nm)} {"gained" if q["chg"] >= 0 else "lost"} {abs(pct_change(q["close"], q["chg"])):.2f}%.'
    if sectors:
        ranked = sorted(sectors, key=lambda s: s['pct'], reverse=True)
        paras.append(f'Best sector: {sector_label(ranked[0]["name"])} ({ranked[0]["pct"]:+.2f}%). '
                     f'Weakest sector: {sector_label(ranked[-1]["name"])} ({ranked[-1]["pct"]:+.2f}%).')
        allowed += [abs(ranked[0]['pct']), abs(ranked[-1]['pct'])]
    if gainers and losers:
        g, l = gainers[0], losers[0]
        paras.append(f'Top Nifty 50 gainer: {g["symbol"]} ({g["pct"]:+.2f}%). Top loser: {l["symbol"]} ({l["pct"]:+.2f}%).')
        allowed += [abs(g['pct']), abs(l['pct'])]
    if breadth:
        paras.append(f'{breadth["advances"]} stocks advanced and {breadth["declines"]} declined in the Nifty 500.')
        allowed += [breadth['advances'], breadth['declines']]
    paras.append('Swipe for sectors, top movers, the rupee and commodities. Currency and commodity prices as of '
                 f'{now_ist().strftime("%-I:%M %p")} IST.')
    allowed += [now_ist().hour % 12 or 12, now_ist().minute]
    caption = assemble(f'Daily market overview: {fmt_date(day)}', paras, 'NSE, BSE, Yahoo Finance',
                       tags('#StockMarketIndia', '#Nifty50', '#Sensex', '#MarketUpdate', '#ShareMarket'))
    if finish('daily_overview', key, images, caption, report, allowed):
        store.mark_seen('post', key)


# ---------------------------------------------------------------- global cues (7:30 AM)

def global_cues(force=False):
    key = f'global:{today_ist()}'
    if store.seen('post', key) and not force:
        return
    report = Report()
    rows, rep = market.global_snapshot()
    report.extend(rep)
    pick = [r for r in rows if r['name'] in ('Dow Jones', 'S&P 500', 'Nasdaq', 'Brent Crude', 'Gold', 'USD / INR')]
    if len(pick) < 4:
        report.fail('fewer than 4 global markets available')
        finish('global_cues', key, [], '', report)
        return
    us = [r for r in pick if r['name'] in ('Dow Jones', 'S&P 500', 'Nasdaq')]
    up = sum(1 for r in us if r['pct'] > 0)
    hr0 = now_ist().hour + now_ist().minute / 60
    verb = 'trades' if (hr0 >= 19.0 or hr0 < 2.5) else 'ends'
    mood = (f'Wall Street {verb} *higher*' if up == len(us) else f'Wall Street {verb} *lower*' if up == 0
            else f'Wall Street {verb} *mixed*')
    crude = next((r for r in pick if r['name'] == 'Brent Crude'), None)
    head = mood + (f'; *crude {"up" if crude["pct"] >= 0 else "down"} {abs(crude["pct"]):.1f}%*' if crude else '')
    notes = []
    if us:
        top = max(us, key=lambda r: abs(r['pct']))
        notes.append(f'{top["name"]} {"rose" if top["pct"] >= 0 else "fell"} {abs(top["pct"]):.2f}%, the biggest move among US indices')
    if crude:
        notes.append(f'Brent crude at {crude["value"]}, {"up" if crude["pct"] >= 0 else "down"} {abs(crude["pct"]):.2f}%')
    asof = max(r['date'] for r in pick)
    hr = now_ist().hour + now_ist().minute / 60
    us_open = hr >= 19.0 or hr < 2.5                 # US cash session in IST (approx., covers DST)
    when = (f'as of {now_ist().strftime("%-I:%M %p")} IST (US markets open)' if us_open
            else f'at their last close on {fmt_date(asof)}')
    images = cards.global_cues({'date_text': fmt_date(today_ist(), 'dow'), 'headline': head, 'rows': pick,
                                'theme': 'market_up' if up * 2 >= len(us) else 'market_down', 'seed': str(today_ist()),
                                'tone': 'up' if up * 2 >= len(us) else 'down',
                                'notes': notes, 'source': f'Yahoo Finance, closing levels of {fmt_date(asof, "short")}'})
    allowed = [asof.day, asof.year, 500]
    for r in pick:
        allowed += [r['close'], r['pct'], abs(r['pct'])]
    lines = [f'{r["name"]}: {r["value"]} ({r["pct"]:+.2f}%)' for r in pick]
    allowed += [now_ist().hour % 12 or 12, now_ist().minute]
    caption = assemble(head, [f'Global markets {when}:', '\n'.join(lines)],
                       'Yahoo Finance', tags('#GlobalMarkets', '#WallStreet', '#CrudeOil', '#StockMarketIndia', '#Nifty50'))
    if finish('global_cues', key, images, caption, report, allowed):
        store.mark_seen('post', key)


# ---------------------------------------------------------------- FII / DII (polls 6-9 PM)

def fii_dii(force=False):
    report = Report()
    try:
        f = nse.fii_dii()
    except nse.SourceError as e:
        log.info('FII/DII not available yet: %s', e)
        return
    key = f'fii:{f["date"]}'
    if store.seen('post', key) and not force:
        return
    if f['date'] != today_ist() and not force:
        log.info('FII/DII still shows %s - waiting for today', f['date'])
        return
    report.ok(f'NSE provisional data for {fmt_date(f["date"])}: FII {f["fii"]:+,.2f}, DII {f["dii"]:+,.2f} crore')
    hist = store.read_json('fii/history.json', {}) or {}
    hist[str(f['date'])] = {'fii': f['fii'], 'dii': f['dii']}
    store.write_json('fii/history.json', hist)
    last5 = sorted(hist)[-5:]                               # card: last 5 recorded sessions
    month_days = [d for d in sorted(hist) if d.startswith(f['date'].strftime('%Y-%m'))]
    rows = [{'date': fmt_date(date.fromisoformat(d), 'daymonth'), 'fii': hist[d]['fii'], 'dii': hist[d]['dii']}
            for d in last5]
    m_fii = round(sum(hist[d]['fii'] for d in month_days), 2)
    m_dii = round(sum(hist[d]['dii'] for d in month_days), 2)
    check_sum([hist[d]['fii'] for d in month_days], m_fii, 'month FII total', report)
    days = month_days
    who = 'buyers' if f['fii'] >= 0 else 'sellers'
    head = f'FIIs net *{who}* at *₹{fmt_inr(abs(f["fii"]))} crore* on {fmt_date(f["date"], "daymonth")}'
    images, totals = cards.fii_dii({'date_text': fmt_date(f['date'], 'dow'), 'headline': head, 'rows': rows,
                                    'theme': 'market_up' if f['fii'] >= 0 else 'market_down', 'seed': str(f['date']),
                                    'tone': 'up' if f['fii'] >= 0 else 'down',
                                    'total_label': f'LAST {len(rows)} DAYS', 'source': 'NSE provisional data'})
    paras = [f'On {fmt_date(f["date"])}, foreign institutional investors (FIIs) were net {who} of '
             f'₹{fmt_inr(abs(f["fii"]))} crore in the cash market, while domestic institutional investors (DIIs) were '
             f'net {"buyers" if f["dii"] >= 0 else "sellers"} of ₹{fmt_inr(abs(f["dii"]))} crore.',
             ]
    if len(days) > 1:
        paras.append(f'{f["date"].strftime("%B")} so far ({len(days)} sessions): FIIs {signed(m_fii)} crore, '
                     f'DIIs {signed(m_dii)} crore.')
    allowed = [f['fii'], f['dii'], m_fii, m_dii, len(days), f['date'].day, f['date'].year, totals['fii_total'], totals['dii_total']]
    caption = assemble(head, paras, 'NSE provisional data (cash market)',
                       tags('#FII', '#DII', '#StockMarketIndia', '#Nifty50', '#ShareMarket'))
    if finish('fii_dii', key, images, caption, report, allowed):
        store.mark_seen('post', key)


# ---------------------------------------------------------------- day ahead (8:30 AM)

def day_ahead(force=False):
    today = today_ist()
    key = f'dayahead:{today}'
    if store.seen('post', key) and not force:
        return
    report = Report()
    groups = []
    try:
        if today in nse.trading_holidays():
            log.info('market holiday today - no day-ahead post'); return
        report.ok('NSE holiday list checked: market open today')
    except nse.SourceError as e:
        report.warn(f'holiday list unavailable ({e})')
    try:
        ev = [e for e in nse.event_calendar() if e['date'] == today and 'result' in e['purpose'].lower()]
        groups.append(('Results / board meetings today', [e['company'] for e in ev][:6]))
        report.ok(f'{len(ev)} result announcements on NSE event calendar')
    except nse.SourceError as e:
        report.warn(f'event calendar unavailable ({e})')
    try:
        ca = nse.corporate_actions(today, today)
        groups.append(('Ex-date today', [f'{c["symbol"]} - {c["subject"]}'[:52] for c in ca][:5]))
        report.ok(f'{len(ca)} corporate actions with ex-date today')
    except nse.SourceError as e:
        report.warn(f'corporate actions unavailable ({e})')
    lines = []
    try:
        for i in nse.ipos_current():
            s = nse.parse_nse_date(i.get('issueStartDate', '')); e = nse.parse_nse_date(i.get('issueEndDate', ''))
            if s and e and s.date() <= today <= e.date():
                lines.append(f'{i.get("companyName") or i.get("symbol")} ({s.day}-{e.day} {e.strftime("%b")})'[:52])
        groups.append(('IPOs open for bidding', lines[:5]))
    except nse.SourceError as e:
        report.warn(f'IPO list unavailable ({e})')
    if not any(g[1] for g in groups):
        log.info('nothing notable for day ahead'); return
    head = f'What is on for the market on *{fmt_date(today, "daymonth")}*'
    images = cards.day_ahead({'date_text': fmt_date(today, 'dow'), 'headline': head, 'groups': groups,
                              'theme': 'market_up', 'seed': str(today),
                              'source': 'NSE event calendar, corporate actions, IPO list'})
    paras = [f'{t}: ' + ', '.join(ls) + '.' for t, ls in groups if ls]
    caption = assemble(head, paras, 'NSE', tags('#StockMarketIndia', '#Nifty50', '#Results', '#IPO', '#ShareMarket'))
    if finish('day_ahead', key, images, caption, report, allowed_numbers=None):
        store.mark_seen('post', key)


# ---------------------------------------------------------------- IPO cards (9 AM)

def ipo(force=False):
    today = today_ist()
    try:
        issues = (nse.ipos_current() or []) + (nse.ipos_upcoming() or [])
    except nse.SourceError as e:
        log.warning('IPO lists unavailable: %s', e); return
    for i in issues:
        name = i.get('companyName') or i.get('symbol')
        s = nse.parse_nse_date(i.get('issueStartDate', ''))
        e = nse.parse_nse_date(i.get('issueEndDate', ''))
        price = i.get('issuePrice') or i.get('priceBand') or ''
        if not (name and s and e and price):
            continue
        if not (today <= s.date() <= today + timedelta(days=1)) and not force:
            continue
        key = f'ipo:{name}:{s.date()}'
        if store.seen('post', key):
            continue
        report = Report()
        report.ok(f'IPO details from NSE issue list: {name}')
        nums = [float(x) for x in re.findall(r'\d+(?:\.\d+)?', price.replace(',', ''))]
        band = f'₹{fmt_inr(nums[0], 0)} - {fmt_inr(nums[-1], 0)}' if len(nums) >= 2 else (f'₹{fmt_inr(nums[0], 0)}' if nums else price)
        series = (i.get('series') or '').upper()
        seg = 'SME IPO' if series in ('SME', 'ST', 'SM') else 'Mainboard IPO'
        tiles = [('Price band', band), ('Opens', fmt_date(s.date(), 'daymonth')), ('Closes', fmt_date(e.date(), 'daymonth'))]
        if i.get('issueSize'):
            tiles.append(('Shares offered', fmt_inr(float(str(i['issueSize']).replace(',', '')), 0)))
        when = 'opens' if s.date() >= today else 'is open'
        head = f'*{name.replace(" Limited", "").replace(" Ltd", "")}* IPO {when} *{fmt_date(s.date(), "daymonth")}*'
        images = cards.ipo({'date_text': f'Opens {fmt_date(s.date(), "short")}', 'headline': head, 'company': name,
                            'theme': 'ipo', 'seed': name,
                            'segment': f'{seg}  |  NSE', 'tiles': tiles,
                            'timeline': [('Opens', fmt_date(s.date(), 'daymonth')), ('Closes', fmt_date(e.date(), 'daymonth'))],
                            'source': 'NSE IPO list'})
        para = (f'The {name} IPO {"opens for bidding on" if s.date() > today else "opened for bidding on"} '
                f'{fmt_date(s.date())} and closes on {fmt_date(e.date())}. Price band: {band} per share.')
        allowed = nums + [s.day, s.year, e.day, e.year] + ([float(str(i['issueSize']).replace(',', ''))] if i.get('issueSize') else [])
        caption = assemble(head, [para, 'Read the red herring prospectus on the SEBI and exchange websites before applying.'],
                           'NSE', tags('#IPO', '#IPOAlert', '#StockMarketIndia', '#NSE', '#ShareMarket'))
        if finish('ipo', key, images, caption, report, allowed):
            store.mark_seen('post', key)


# ---------------------------------------------------------------- gainers & losers by market cap (4:15 PM)

def cap_movers(force=False):
    key = f'capmovers:{today_ist()}'
    if store.seen('post', key) and not force:
        return
    if not _after_close(None, 'Gainers & losers'):
        return
    report = Report()
    quotes, _, nse_date, rep = market.market_snapshot({'NIFTY 50': ('NIFTY 50', '^NSEI')})
    if not _session_or_skip(quotes, nse_date, report, force):
        return
    segs, rep2 = market.cap_movers(5)
    report.extend(rep2)
    if len(segs) < 4 and not force:
        report.fail('need all 4 market-cap groups for this post')
    if not report.passed:
        finish('cap_movers', key, [], '', report)
        return
    day = nse_date or today_ist()
    n_up = quotes.get('NIFTY 50', {}).get('chg', 0) >= 0
    order = [s for s, _ in market.CAP_SEGMENTS if s in segs]
    seg_list = [{'name': s, **segs[s]} for s in order]
    images = cards.cap_movers({'date_text': fmt_date(day, 'dow'), 'theme': 'market_up' if n_up else 'market_down',
                               'seed': str(day), 'tone': 'up' if n_up else 'down',
                               'headline': f'Top gainers and losers by *market cap*: *{fmt_date(day, "daymonth")}*',
                               'segments': seg_list, 'source': 'NSE closing data'})
    allowed = [day.day, day.year, 5]          # 5 = 'top 5 in each group'
    paras = []
    for sg in seg_list:
        bits = []
        if sg['gainers']:
            g = sg['gainers'][0]; bits.append(f'top gainer {g["symbol"]} ({g["pct"]:+.2f}%)')
            allowed += [abs(g['pct'])]
        if sg['losers']:
            l = sg['losers'][0]; bits.append(f'top loser {l["symbol"]} ({l["pct"]:+.2f}%)')
            allowed += [abs(l['pct'])]
        paras.append(f'{sg["name"]}: ' + ', '.join(bits) + '.')
    paras = ['\n'.join(paras),
             'Groups as defined by NSE: Large Cap = Nifty 100, Mid Cap = Nifty Midcap 150, '
             'Small Cap = Nifty Smallcap 250, Micro Cap = Nifty Microcap 250. Swipe for the top 5 in each group.']
    caption = assemble(f'Top gainers and losers by market cap: {fmt_date(day)}', paras, 'NSE closing data',
                       tags('#TopGainers', '#TopLosers', '#StockMarketIndia', '#SmallCap', '#ShareMarket'))
    if finish('cap_movers', key, images, caption, report, allowed):
        store.mark_seen('post', key)


# ---------------------------------------------------------------- weekly all-time highs / 52-week lows (Saturday)

def _week():
    t = today_ist()
    monday = t - timedelta(days=t.weekday())
    friday = monday + timedelta(days=4)
    if monday.month == friday.month:
        label = f'{monday.day}-{friday.day} {friday.strftime("%b %Y")}'
    else:
        label = f'{monday.day} {monday.strftime("%b")} - {friday.day} {friday.strftime("%b %Y")}'
    return monday, friday, label


def _weekly_data(monday, report):
    """Scan once per week; the second post reuses the saved result."""
    cached = store.read_json(f'weekly/{monday}.json')
    if cached:
        report.extend([tuple(r) for r in cached['report']])
        return cached['groups']
    groups, rep = market.weekly_extremes(monday)
    report.extend(rep)
    store.write_json(f'weekly/{monday}.json', {'groups': groups, 'report': rep})
    return groups


def _weekly_post(kind, force):
    monday, friday, label = _week()
    job = 'weekly_ath' if kind == 'ath' else 'weekly_lows'
    key = f'weekly-{kind}:{monday}'
    if store.seen('post', key) and not force:
        return
    report = Report()
    groups = _weekly_data(monday, report)
    if len(groups) < 4:
        report.fail('need all 4 market-cap groups for this post')
        finish(job, key, [], '', report)
        return
    order = [s for s, _ in market.CAP_SEGMENTS]
    gl = [{'name': s, 'index': groups[s]['index'], 'rows': groups[s][kind],
           'count': groups[s][f'{kind}_count']} for s in order]
    total = sum(g['count'] for g in gl)
    if total == 0 and not force:
        log.info('no %s stocks this week - skipping', kind); return
    what, word = ('all-time high', 'all-time highs') if kind == 'ath' else ('52-week low', '52-week lows')
    head = f'Stocks at *{word}* this week ({label})'
    images = cards.extremes({'kind': kind, 'date_text': f'Week of {label}', 'headline': head, 'groups': gl,
                             'theme': 'market_up' if kind == 'ath' else 'market_down', 'seed': str(monday),
                             'tone': 'up' if kind == 'ath' else 'down',
                             'source': 'NSE, Yahoo Finance'})
    allowed = [monday.day, friday.day, friday.year, total, 52, 10]
    lines = []
    for g in gl:
        allowed.append(g['count'])
        top = ', '.join(f'{r["symbol"]} ({r["week_pct"]:+.2f}%)' for r in g['rows'][:3])
        allowed += [abs(r['week_pct']) for r in g['rows'][:3]]
        lines.append(f'{g["name"]}: {g["count"]} stock{"s" if g["count"] != 1 else ""}' + (f' - {top}' if top else ''))
    paras = [f'{total} stocks across the four market-cap groups made a new {what} in the week of {label}.',
             '\n'.join(lines),
             'Weekly % change shown in brackets. Groups as defined by NSE: Large Cap = Nifty 100, Mid Cap = Nifty Midcap 150, '
             'Small Cap = Nifty Smallcap 250, Micro Cap = Nifty Microcap 250. Stocks listed for less than 52 weeks are '
             'not included. Swipe for up to 10 stocks in each group.']
    caption = assemble(head, paras, 'NSE, Yahoo Finance',
                       tags('#AllTimeHigh' if kind == 'ath' else '#52WeekLow', '#StockMarketIndia', '#Nifty50',
                            '#SmallCap', '#ShareMarket'))
    if finish(job, key, images, caption, report, allowed):
        store.mark_seen('post', key)


def weekly_ath(force=False):
    _weekly_post('ath', force)


def weekly_lows(force=False):
    _weekly_post('low', force)
