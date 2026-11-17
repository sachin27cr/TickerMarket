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


# ---------------------------------------------------------------- closing bell carousel (3:50 PM)

def _relabel(rep, core):
    """Problems with secondary data leave that row out instead of blocking the post."""
    return [(st, m) if st != 'fail' or m.startswith(core) else ('warn', m + ' - left out') for st, m in rep]


def market_close(force=False):
    if not _after_close(None, 'Closing bell'):
        return
    key = f'close:{today_ist()}'
    if store.seen('post', key) and not force:
        return
    report = Report()
    core = ('NIFTY 50', 'SENSEX', 'NIFTY BANK')
    quotes, breadth, nse_date, rep = market.market_snapshot()
    report.extend(_relabel(rep, core))
    if not _session_or_skip(quotes, nse_date, report, force):
        return
    if any(n not in quotes for n in core):
        report.fail('missing ' + ', '.join(n for n in core if n not in quotes))
    secs, rep2 = market.sector_snapshot()
    report.extend([('warn', m + ' - sector left out') if st == 'fail' else (st, m) for st, m in rep2])
    try:
        gainers, losers = market.movers('NIFTY 50', 5)
        if nse.LAST_SOURCE.get('NIFTY 50', 'NSE') == 'NSE':
            report.ok('Nifty 50 movers from NSE')
        else:
            report.warn('Nifty 50 movers: NSE stock API unavailable - prices from Yahoo')
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
        finish('market_close', key, [], '', report)
        return
    day = nse_date or today_ist()
    n, s_, b = quotes['NIFTY 50'], quotes['SENSEX'], quotes['NIFTY BANK']
    up = n['chg'] >= 0
    theme, tone = ('market_up', 'up') if up else ('market_down', 'down')
    verb = 'gains' if up else 'falls'
    head = f'Nifty {verb} *{fmt_inr(abs(n["chg"]), 0)} points*; Sensex ends at *{fmt_inr(s_["close"], 0)}*'
    pc = lambda q: pct_change(q['close'], q['chg'])
    stats = [('Nifty 50', f'{pc(n):+.2f}%', n['chg']), ('Sensex', f'{pc(s_):+.2f}%', s_['chg']),
             ('Nifty Bank', f'{pc(b):+.2f}%', b['chg'])]
    order = ['NIFTY 50', 'SENSEX', 'NIFTY BANK', 'NIFTY MIDCAP 100', 'NIFTY SMALLCAP 100', 'INDIA VIX']
    idx = [quotes[k] for k in order if k in quotes]
    sectors = [{'name': v['name'], 'pct': v['pct']} for v in secs.values()]
    inside = ['Key indices'] + (['Sector moves'] if sectors else []) + (['Nifty 50 top movers'] if gainers else []) \
        + (['Market breadth'] if breadth else []) + (['Rupee, crude & gold'] if extras else [])
    slides = [cards.cover({'category': 'Closing Bell', 'day': day, 'headline': head, 'stats': stats,
                           'theme': theme, 'seed': str(day), 'tone': tone, 'inside': inside})]
    slides += cards.daily_overview({'theme': theme, 'seed': str(day) + 'o', 'tone': tone,
                                    'date_text': fmt_date(day, 'dow'), 'headline': f'Key indices on *{fmt_date(day, "daymonth")}*',
                                    'indices': idx, 'breadth': breadth, 'sectors': sectors, 'gainers': gainers,
                                    'losers': losers, 'extras': extras, 'source': ''})
    allowed = [day.day, day.year, 50, 500, 100]
    for q in idx:
        allowed += [q['close'], q['chg'], pc(q), abs(q['chg'])]
    paras = [f'On {fmt_date(day)}, the Nifty 50 closed at {fmt_inr(n["close"])}, {_move(n)}. The Sensex ended at '
             f'{fmt_inr(s_["close"])}, {_move(s_)}, and Nifty Bank closed at {fmt_inr(b["close"])}, {_move(b)}.']
    if sectors:
        ranked = sorted(sectors, key=lambda x: x['pct'], reverse=True)
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
    paras.append('Swipe for all indices, sectors, top movers, the rupee and commodities.')
    caption = assemble(head, paras, '', tags('#Nifty50', '#Sensex', '#StockMarketIndia', '#ShareMarket', '#MarketClose'))
    if finish('market_close', key, slides, caption, report, allowed):
        store.mark_seen('post', key)


# ---------------------------------------------------------------- highs & lows carousel (4:35 PM)

def daily_overview(force=False):
    """Index scorecard, then all-time highs / 52-week highs and lows for each market-cap group."""
    if not _after_close(None, 'Highs & lows'):
        return
    key = f'highslows:{today_ist()}'
    if store.seen('post', key) and not force:
        return
    report = Report()
    board, nse_date, rep = market.index_board()
    report.extend(_relabel(rep, ('NIFTY 50',)))
    if not market.traded_today(nse_date, {q['name']: q for q in board}) and not force:
        log.info('no session today'); return
    day = nse_date or today_ist()
    groups, rep2 = market.daily_extremes(day)
    report.extend(rep2)
    if len(groups) < 4:
        report.fail('need all 4 market-cap groups')
    if not board:
        report.fail('index data unavailable')
    if not report.passed:
        finish('daily_overview', key, [], '', report)
        return
    order = [s for s, _ in market.CAP_SEGMENTS]
    ath = sum(groups[g]['ath_count'] for g in order)
    hi = sum(groups[g]['hi52_count'] for g in order)
    lo = sum(groups[g]['lo52_count'] for g in order)
    n50 = next((q for q in board if q['name'] == 'NIFTY 50'), board[0])
    up = n50['chg'] >= 0
    theme, tone = ('market_up', 'up') if up else ('market_down', 'down')
    if ath:
        head = f'*{ath} stocks* hit all-time highs; *{lo}* at 52-week lows'
    else:
        head = f'*{hi} stocks* at 52-week highs, *{lo}* at 52-week lows'
    slides = [cards.cover({'category': 'Highs & Lows', 'day': day, 'headline': head,
                           'stats': [('All-time highs', str(ath), 1 if ath else 0), ('52-week highs', str(hi), 1 if hi else 0),
                                     ('52-week lows', str(lo), -1 if lo else 0)],
                           'theme': theme, 'seed': str(day) + 'h', 'tone': tone,
                           'inside': ['Index scorecard', 'Large cap', 'Mid cap', 'Small cap', 'Micro cap']})]
    slides.append(cards.index_board({'date_text': fmt_date(day, 'dow'), 'headline': f'Index scorecard: *{fmt_date(day, "daymonth")}*',
                                     'rows': board, 'theme': theme, 'seed': str(day) + 'b', 'tone': tone, 'source': ''}))
    allowed = [day.day, day.year, ath, hi, lo, 52, 50, 100, 150, 250, 500]
    lines = []
    for g in order:
        gg = groups[g]
        slides.append(cards.highs_lows_group({
            'name': g, 'date_text': fmt_date(day, 'dow'), 'theme': theme, 'seed': str(day) + g, 'tone': tone,
            'headline': f'*{g}*: new highs and lows', 'source': '',
            'summary': f'{gg["hi52_count"]} at 52-week high ({gg["ath_count"]} all-time high), '
                       f'{gg["lo52_count"]} at 52-week low  |  {gg["index"].title()}',
            'ath': gg['ath'], 'hi52': gg['hi52'], 'lo52': gg['lo52']}))
        top = ', '.join(r['symbol'] for r in (gg['ath'] or gg['hi52'])[:3])
        lines.append(f'{g}: {gg["hi52_count"]} at 52-week highs ({gg["ath_count"]} all-time highs), '
                     f'{gg["lo52_count"]} at 52-week lows' + (f'. Highs include {top}' if top else '') + '.')
        allowed += [gg['hi52_count'], gg['ath_count'], gg['lo52_count']]
    paras = [f'New highs and lows on {fmt_date(day)}: {ath} stocks across the four market-cap groups touched an '
             f'all-time high, {hi} a 52-week high and {lo} a 52-week low.', '\n'.join(lines),
             'Groups as defined by NSE: Large Cap = Nifty 100, Mid Cap = Nifty Midcap 150, Small Cap = Nifty Smallcap 250, '
             'Micro Cap = Nifty Microcap 250. Swipe for the index scorecard and each group.']
    caption = assemble(head, paras, '', tags('#AllTimeHigh', '#52WeekHigh', '#StockMarketIndia', '#Nifty50', '#ShareMarket'))
    if finish('daily_overview', key, slides, caption, report, allowed):
        store.mark_seen('post', key)


# ---------------------------------------------------------------- global cues (7:30 AM)

def global_cues(force=False):
    key = f'global:{today_ist()}'
    if store.seen('post', key) and not force:
        return
    report = Report()
    rows, rep = market.global_snapshot()
    report.extend(rep)
    pick = [r for r in rows if r['name'] in ('Dow Jones', 'S&P 500', 'Nasdaq', 'Nikkei 225', 'Hang Seng',
                                              'Brent Crude', 'Gold', 'USD / INR')]
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
    by = {r['name']: r for r in pick}
    gstats = [(k, f'{by[k]["pct"]:+.2f}%', by[k]['pct']) for k in ('Dow Jones', 'Nasdaq', 'Brent Crude') if k in by]
    images = [cards.cover({'category': 'Global Cues', 'day': today_ist(), 'headline': head, 'stats': gstats,
                           'theme': 'market_up' if up * 2 >= len(us) else 'market_down', 'seed': str(today_ist()) + 'g',
                           'tone': 'up' if up * 2 >= len(us) else 'down',
                           'inside': ['US markets', 'Asia', 'Crude & gold', 'Rupee', 'What changed overnight']})] + images
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
    fno = market.fii_fno(f['date'], report)
    if fno is None and now_ist().hour < 20 and not force:
        log.info('F&O positions not out yet - will post at the next attempt (last one at 8:20 PM)')
        return
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
                                    'total_label': f'LAST {len(rows)} DAYS', 'source': 'NSE provisional data',
                                    'fno': fno})
    stats = [('FII net', f'{"+" if f["fii"] >= 0 else "-"}₹{fmt_inr(abs(f["fii"]), 0)} Cr', f['fii']),
             ('DII net', f'{"+" if f["dii"] >= 0 else "-"}₹{fmt_inr(abs(f["dii"]), 0)} Cr', f['dii'])]
    if fno:
        stats.append(('FII index fut. long', f'{fno["idx_fut_long_pct"]:.1f}%', 0))
    images = [cards.cover({'category': 'FII / DII Data', 'day': f['date'], 'headline': head, 'stats': stats,
                           'theme': 'market_up' if f['fii'] >= 0 else 'market_down', 'seed': str(f['date']) + 'c',
                           'tone': 'up' if f['fii'] >= 0 else 'down',
                           'inside': ['Cash market: last 5 days'] + (['FII positions in F&O'] if fno else [])})] + images
    paras = [f'On {fmt_date(f["date"])}, foreign institutional investors (FIIs) were net {who} of '
             f'₹{fmt_inr(abs(f["fii"]))} crore in the cash market, while domestic institutional investors (DIIs) were '
             f'net {"buyers" if f["dii"] >= 0 else "sellers"} of ₹{fmt_inr(abs(f["dii"]))} crore.',
             ]
    if len(days) > 1:
        paras.append(f'{f["date"].strftime("%B")} so far ({len(days)} sessions): FIIs {signed(m_fii)} crore, '
                     f'DIIs {signed(m_dii)} crore.')
    fno_nums = []
    if fno:
        line = (f'In derivatives, FIIs held {fno["idx_fut_long_pct"]:.1f}% of their index futures positions long '
                f'(net {signed(fno["idx_fut_net"], 0)} contracts')
        if 'idx_fut_net_chg' in fno:
            line += f', {signed(fno["idx_fut_net_chg"], 0)} from the previous session'
        line += (f'). Net index calls: {signed(fno["idx_call_net"], 0)}; net index puts: '
                 f'{signed(fno["idx_put_net"], 0)} contracts.')
        paras.append(line)
        fno_nums = [fno['idx_fut_long_pct'], fno['idx_fut_net'], fno.get('idx_fut_net_chg', 0), fno['idx_call_net'],
                    fno['idx_put_net'], fno['stk_fut_net'], 100 - fno['idx_fut_long_pct']]
    allowed = [f['fii'], f['dii'], m_fii, m_dii, len(days), f['date'].day, f['date'].year, totals['fii_total'],
               totals['dii_total']] + fno_nums
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
    counts = {t: len(ls) for t, ls in groups}
    dstats = [(t.split(' /')[0].replace(' today', '').replace(' for bidding', ''), str(c), 0) for t, c in counts.items()][:3]
    images = [cards.cover({'category': 'Market Day Ahead', 'day': today, 'headline': head, 'stats': dstats,
                           'theme': 'market_up', 'seed': str(today) + 'c',
                           'inside': [t for t, ls in groups if ls]})] + images
    paras = [f'{t}: ' + ', '.join(ls) + '.' for t, ls in groups if ls]
    caption = assemble(head, paras, 'NSE', tags('#StockMarketIndia', '#Nifty50', '#Results', '#IPO', '#ShareMarket'))
    if finish('day_ahead', key, images, caption, report, allowed_numbers=None):
        store.mark_seen('post', key)


# ---------------------------------------------------------------- IPO carousel (9 AM) and live subscription (5:20 PM)

def _num(v):
    if v is None:
        return None
    m = re.findall(r'\d+(?:\.\d+)?', str(v).replace(',', ''))
    return float(m[0]) if m else None


def _ipo_facts(i, detail):
    """Collect what NSE gives us; every value shown later comes from here."""
    f = nse.find_field
    price = i.get('issuePrice') or f(detail, r'price.?band', r'issue.?price') or ''
    band = [float(x) for x in re.findall(r'\d+(?:\.\d+)?', str(price).replace(',', ''))]
    facts = {
        'band': band,
        'lot': _num(f(detail, r'min.*bid.*(qty|quant)', r'lot.?size', r'market.?lot', r'bid.?lot')),
        'face': _num(f(detail, r'face.?value')),
        'issue_size': f(detail, r'issue.?size', r'total.?issue'),
        'fresh': f(detail, r'fresh'),
        'ofs': f(detail, r'offer.?for.?sale', r'^ofs'),
        'qib': f(detail, r'qib'),
        'nii': f(detail, r'nii|non.?inst'),
        'retail': f(detail, r'retail|rii'),
        'registrar': f(detail, r'registrar'),
        'brlm': f(detail, r'lead.?manager|brlm|book.?running'),
        'allot': f(detail, r'allot'),
        'refund': f(detail, r'refund'),
        'credit': f(detail, r'credit|demat'),
        'listing': f(detail, r'listing.?date', r'list.*date'),
        'shares': i.get('issueSize'),
    }
    return facts


def ipo(force=False):
    today = today_ist()
    try:
        issues = (nse.ipos_current() or []) + (nse.ipos_upcoming() or [])
    except nse.SourceError as e:
        log.warning('IPO lists unavailable: %s', e); return
    for i in issues:
        name = i.get('companyName') or i.get('symbol')
        sym = i.get('symbol') or ''
        s = nse.parse_nse_date(i.get('issueStartDate', ''))
        e = nse.parse_nse_date(i.get('issueEndDate', ''))
        if not (name and s and e):
            continue
        if not (today <= s.date() <= today + timedelta(days=1)) and not force:
            continue
        key = f'ipo:{name}:{s.date()}'
        if store.seen('post', key):
            continue
        report = Report()
        detail = {}
        try:
            detail = nse.ipo_detail(sym, i.get('series') or 'EQ')
            store.write_json(f'cache/ipo_raw/{sym}.json', detail)          # kept for checking field names
            report.ok(f'IPO details from NSE issue page: {sym}')
        except nse.SourceError as ex:
            report.warn(f'IPO detail page unavailable ({ex}) - basic card only')
        fx = _ipo_facts(i, detail)
        if not fx['band']:
            report.fail('price band missing'); finish('ipo', key, [], '', report); continue
        hi_price = fx['band'][-1]
        band = (f'₹{fmt_inr(fx["band"][0], 0)} - {fmt_inr(hi_price, 0)}' if len(fx['band']) >= 2
                else f'₹{fmt_inr(hi_price, 0)}')
        seg = 'SME IPO' if (i.get('series') or '').upper() in ('SME', 'ST', 'SM') else 'Mainboard IPO'
        tiles = [('Price band', band)]
        allowed = list(fx['band']) + [s.day, s.year, e.day, e.year]
        if fx['lot']:
            tiles.append(('Lot size', f'{int(fx["lot"])} shares'))
            min_inv = fx['lot'] * hi_price                             # computed, never typed
            tiles.append(('Min. investment', f'₹{fmt_inr(min_inv, 0)}'))
            allowed += [fx['lot'], min_inv]
        if fx['issue_size']:
            tiles.append(('Issue size', str(fx['issue_size'])[:18]))
            allowed += [_num(fx['issue_size']) or 0]
        tiles += [('Opens', fmt_date(s.date(), 'daymonth')), ('Closes', fmt_date(e.date(), 'daymonth'))]
        timeline = [('Opens', fmt_date(s.date(), 'daymonth')), ('Closes', fmt_date(e.date(), 'daymonth'))]
        for lab, k in (('Allotment', 'allot'), ('Listing', 'listing')):
            dd = nse.parse_nse_date(str(fx[k])) if fx[k] else None
            if dd:
                timeline.append((lab, fmt_date(dd.date(), 'daymonth')))
                allowed += [dd.day, dd.year]
        short = name.replace(' Limited', '').replace(' Ltd', '')
        when = 'opens' if s.date() > today else 'opens today' if s.date() == today else 'is open'
        head = f'*{short}* IPO {when}' + (f' *{fmt_date(s.date(), "daymonth")}*' if s.date() > today else '')
        slides = cards.ipo({'date_text': f'Opens {fmt_date(s.date(), "short")}', 'headline': head, 'company': name,
                            'theme': 'ipo', 'seed': name, 'segment': f'{seg}  |  NSE', 'tiles': tiles[:6],
                            'timeline': timeline, 'source': 'NSE'})
        istats = [('Price band', band, 0)]
        if fx['lot']:
            istats += [('Lot size', f'{int(fx["lot"])} shares', 0), ('Min. investment', f'₹{fmt_inr(fx["lot"] * hi_price, 0)}', 0)]
        slides = [cards.cover({'category': 'IPO Watch', 'day': s.date() if s.date() >= today else today,
                               'headline': head, 'stats': istats, 'theme': 'ipo', 'seed': name + 'c', 'tone': 'up',
                               'inside': ['Price band & lot', 'Issue structure', 'Key dates']})] + slides
        # slide 2: issue structure
        rows = [(lab, v) for lab, v in (
            ('Issue size', fx['issue_size']), ('Fresh issue', fx['fresh']), ('Offer for sale', fx['ofs']),
            ('Face value', f'₹{fmt_inr(fx["face"], 0)} per share' if fx['face'] else None),
            ('QIB quota', fx['qib']), ('NII quota', fx['nii']), ('Retail quota', fx['retail']),
            ('Lead managers', fx['brlm']), ('Registrar', fx['registrar'])) if v]
        if len(rows) >= 3:
            slides.append(cards.info_table('IPO Details', fmt_date(today, 'dow'), f'*{short}* issue structure',
                                           [(k, str(v)) for k, v in rows], 'NSE', 'ipo', name))
            for _, v in rows:
                allowed += [float(x) for x in re.findall(r'\d+(?:\.\d+)?', str(v).replace(',', ''))]
        # slide 3: key dates
        dates = [('Opens', fmt_date(s.date())), ('Closes', fmt_date(e.date()))]
        for lab, k in (('Allotment', 'allot'), ('Refunds', 'refund'), ('Shares in demat', 'credit'), ('Listing', 'listing')):
            dd = nse.parse_nse_date(str(fx[k])) if fx[k] else None
            if dd:
                dates.append((lab, fmt_date(dd.date())))
                allowed += [dd.day, dd.year]
        if len(dates) >= 4:
            slides.append(cards.info_table('IPO Timeline', fmt_date(today, 'dow'), f'*{short}* IPO key dates',
                                           dates, 'NSE', 'ipo', name + 'd'))
        paras = [f'The {name} IPO {"opens for bidding on" if s.date() > today else "opened for bidding on"} '
                 f'{fmt_date(s.date())} and closes on {fmt_date(e.date())}. Price band: {band} per share.']
        if fx['lot']:
            paras.append(f'Minimum bid: {int(fx["lot"])} shares, which is ₹{fmt_inr(fx["lot"] * hi_price, 0)} at the '
                         f'upper end of the price band.')
        paras.append('Swipe for the issue structure and key dates. Read the red herring prospectus on the SEBI and '
                     'exchange websites before applying.')
        caption = assemble(head, paras, 'NSE', tags('#IPO', '#IPOAlert', '#StockMarketIndia', '#NSE', '#ShareMarket'))
        if finish('ipo', key, slides, caption, report, allowed):
            store.mark_seen('post', key)


def ipo_status(force=False):
    """Live category-wise subscription for IPOs open today (one card per IPO, 5:20 PM)."""
    today = today_ist()
    try:
        issues = nse.ipos_current() or []
    except nse.SourceError as e:
        log.warning('IPO list unavailable: %s', e); return
    for i in issues:
        name, sym = i.get('companyName') or i.get('symbol'), i.get('symbol') or ''
        s = nse.parse_nse_date(i.get('issueStartDate', '')); e = nse.parse_nse_date(i.get('issueEndDate', ''))
        if not (s and e and s.date() <= today <= e.date()):
            continue
        key = f'ipostatus:{sym}:{today}'
        if store.seen('post', key) and not force:
            continue
        report = Report()
        try:
            rows, upd, raw = nse.ipo_subscription(sym)
            store.write_json(f'cache/ipo_raw/{sym}_subs.json', raw)
        except nse.SourceError as ex:
            log.info('no subscription data for %s: %s', sym, ex); continue
        good = []
        for r in rows:
            if r['offered'] and r['bid'] is not None:
                calc = r['bid'] / r['offered']
                if r['times'] is not None and abs(calc - r['times']) > 0.02 + 0.01 * calc:
                    report.warn(f'{r["category"]}: NSE shows {r["times"]}x but bids/offered = {calc:.2f}x - left out')
                    continue
                r['times'] = calc if r['times'] is None else r['times']
            if r['times'] is not None:
                good.append(r)
        if not good:
            continue
        report.ok(f'{len(good)} categories; times re-computed from bids and shares offered where NSE gives both')
        day_no = sum(1 for k in range((today - s.date()).days + 1) if (s.date() + timedelta(days=k)).weekday() < 5)  # bidding days
        total = next((r for r in good if 'total' in r['category'].lower()), None)
        short = name.replace(' Limited', '').replace(' Ltd', '')
        head = (f'*{short}* IPO subscribed *{total["times"]:.2f} times* on day {day_no}' if total
                else f'*{short}* IPO subscription status, day {day_no}')
        days_total = sum(1 for k in range((e.date() - s.date()).days + 1)
                         if (s.date() + timedelta(days=k)).weekday() < 5)
        tiles = [('Issue day', f'{day_no} of {days_total}'), ('Closes on', fmt_date(e.date(), 'daymonth'))]
        band = str(i.get('issuePrice') or '').replace('Rs.', '₹').replace(' to ', ' - ')
        if band:
            tiles.insert(0, ('Price band', band))
        img = cards.subscription('IPO Subscription', fmt_date(today, 'dow'), head, good[:7],
                                 str(upd) if upd else '', 'NSE', 'ipo', sym, tiles)
        lines = '\n'.join(f'{r["category"]}: {r["times"]:.2f}x' for r in good[:7])
        caption = assemble(head, [f'Category-wise subscription for the {name} IPO on {fmt_date(today)} '
                                  f'(day {day_no} of the issue, which closes on {fmt_date(e.date())}):', lines],
                           'NSE', tags('#IPO', '#IPOAlert', '#IPOSubscription', '#StockMarketIndia', '#ShareMarket'))
        allowed = [r['times'] for r in good] + [day_no, today.day, today.year, e.day, e.year]
        if finish('ipo_status', key, [img], caption, report, allowed):
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
    cstats = []
    for sg in seg_list[:3]:
        if sg['gainers']:
            g0 = sg['gainers'][0]
            cstats.append((f'{sg["name"]} top', f'{g0["symbol"][:10]} {g0["pct"]:+.1f}%', g0['pct']))
    images = [cards.cover({'category': 'Gainers & Losers', 'day': day,
                           'headline': f'Top gainers and losers by *market cap*',
                           'stats': cstats, 'theme': 'market_up' if n_up else 'market_down', 'seed': str(day) + 'c',
                           'tone': 'up' if n_up else 'down',
                           'inside': ['Summary', 'Large cap', 'Mid cap', 'Small cap', 'Micro cap']})] + images
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
    if len(groups) == len(market.CAP_SEGMENTS):          # never cache a failed scan
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
