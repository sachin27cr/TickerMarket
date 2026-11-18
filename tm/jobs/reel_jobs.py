"""Reels: Morning Brief (7:35 AM, ready before 8), Closing Bell (about 5 PM), Week in Review (Saturday),
plus reels for the weekly all-time highs and 52-week lows posts.

Every number on screen, in the voice-over and in the caption comes from the same data sources and checks as
the posts; the voice script and caption are fixed templates written by code (no AI).
"""
import tempfile
from datetime import timedelta
from pathlib import Path

from .. import store
from ..reels import render, voice as V
from ..render.art import as_post
from ..render.cards import name_of
from ..sources.names import short as short_name
from ..sources import market, nse
from ..util import fmt_date, fmt_inr, log, now_ist, pct_change, today_ist
from ..verify.checks import Report
from ..writer.captions import assemble, tags
from .common import finish_video
from . import market_jobs
from .market_jobs import _relabel, sector_label

GLOBAL_US = ('Dow Jones', 'S&P 500', 'Nasdaq')
GLOBAL_ASIA = ('Nikkei 225', 'Hang Seng')


def _trading_day(d):
    if d.weekday() >= 5:
        return False
    try:
        return d not in nse.trading_holidays()
    except nse.SourceError:
        return True


def _q(quotes, name):
    q = quotes.get(name)
    return q, pct_change(q['close'], q['chg']) if q else None


def _outro():
    return {'type': 'outro', 'topic': 'outro',
            'voice': 'Follow Ticker Market India for daily stock market data and news.'}


def _make(kind, title, label, scenes, caption, report, allowed, seed):
    out = Path(tempfile.mkdtemp()) / f'{kind}.mp4'
    path, cover, rep, _ = render.build(scenes, label, out, seed)
    report.extend(rep)
    return finish_video(kind, title, path, cover, caption, report, allowed)


# ---------------------------------------------------------------- Morning Brief

@as_post('reel_morning')
def morning_reel(force=False):
    today = today_ist()
    key = f'reel-am:{today}'
    if store.seen('post', key) and not force:
        return
    if not _trading_day(today) and not force:
        log.info('no trading session today - no morning reel'); return
    report = Report()
    scenes, paras, allowed = [], [], [today.day, today.year]
    # yesterday's close
    quotes, _, nse_date, rep = market.market_snapshot()
    report.extend(_relabel(rep, ('NIFTY 50', 'SENSEX')))
    n, np_ = _q(quotes, 'NIFTY 50')
    s, sp = _q(quotes, 'SENSEX')
    hook_bits = []
    # global markets
    glob, rep2 = market.global_snapshot()
    report.extend([r for r in rep2 if r[0] != 'ok'])
    g = {x['name']: x for x in glob}
    us = [g[k] for k in GLOBAL_US if k in g]
    asia = [g[k] for k in GLOBAL_ASIA if k in g]
    if us or asia:
        rows = [{'label': x['name'], 'value': x['value'], 'pct': x['pct'],
                 'sub': 'live' if x.get('date') == today else None} for x in us + asia]
        up_us = sum(1 for x in us if x['pct'] >= 0)
        said = ', '.join(f'the {x["name"]} {"up" if x["pct"] >= 0 else "down"} {V.pct(x["pct"])}' for x in us)
        v = (f'Overnight on Wall Street, {said}. ' if us else '') + \
            (' '.join(f'In Asia, the {x["name"]} is {"up" if x["pct"] >= 0 else "down"} {V.pct(x["pct"])}.' for x in asia[:1]))
        scenes.append({'type': 'rows', 'title': 'Global markets', 'rows': rows, 'voice': v, 'topic': 'global',
                       'tone': 'up' if up_us * 2 >= max(1, len(us)) else 'down'})
        paras.append('Global markets: ' + '; '.join(f'{x["name"]} {x["value"]} ({x["pct"]:+.2f}%)' for x in us + asia) + '.')
        allowed += [x['close'] for x in us + asia] + [abs(x['pct']) for x in us + asia]
        if us:
            hook_bits.append(f'Wall Street {"ends higher" if up_us * 2 >= len(us) else "slips"}')
    com = [g[k] for k in ('Brent Crude', 'Gold', 'USD / INR') if k in g]
    if com:
        scenes.append({'type': 'rows', 'title': 'Crude, gold and rupee', 'topic': 'commodities',
                       'rows': [{'label': x['name'], 'value': x['value'], 'pct': x['pct']} for x in com],
                       'voice': ' '.join(f'{x["name"].replace("USD / INR", "The dollar against the rupee")} is '
                                         f'{"up" if x["pct"] >= 0 else "down"} {V.pct(x["pct"])} at {x["value"].replace("$", "")}'
                                         f'{" dollars" if x["value"].startswith("$") else ""}.' for x in com)})
        paras.append('Commodities and currency: ' + '; '.join(f'{x["name"]} {x["value"]} ({x["pct"]:+.2f}%)' for x in com) + '.')
        allowed += [x['close'] for x in com] + [abs(x['pct']) for x in com]
        brent = g.get('Brent Crude')
        if brent and abs(brent['pct']) >= 0.5:
            hook_bits.append(f'crude {"up" if brent["pct"] > 0 else "down"} {abs(brent["pct"]):.1f}%')
            allowed.append(round(abs(brent['pct']), 1))
    if n and s:
        last = fmt_date(nse_date, 'long') if nse_date else 'the last session'
        scenes.append({'type': 'rows', 'title': f'Last close ({fmt_date(nse_date, "daymonth") if nse_date else ""})',
                       'topic': 'indices', 'tone': 'up' if n['chg'] >= 0 else 'down',
                       'rows': [{'label': 'Nifty 50', 'value': fmt_inr(n['close'], 0), 'pct': np_},
                                {'label': 'Sensex', 'value': fmt_inr(s['close'], 0), 'pct': sp}],
                       'voice': f'In the last session, the Nifty closed at {V.pts(n["close"])}, {V.move(n["chg"], np_)}, '
                                f'and the Sensex ended at {V.pts(s["close"])}, {V.move(s["chg"], sp)}.'})
        paras.append(f'Last close ({last}): Nifty 50 {fmt_inr(n["close"])} ({np_:+.2f}%), Sensex {fmt_inr(s["close"])} ({sp:+.2f}%).')
        allowed += [n['close'], s['close'], abs(np_), abs(sp)]
    # FII / DII
    try:
        f = nse.fii_dii()
        scenes.append({'type': 'rows', 'title': f'FII / DII ({fmt_date(f["date"], "daymonth")})', 'topic': 'flows',
                       'tone': 'up' if f['fii'] >= 0 else 'down',
                       'rows': [{'label': 'FII net', 'value': f'₹{fmt_inr(f["fii"], 0)} CR', 'sub': 'buyers' if f['fii'] >= 0 else 'sellers'},
                                {'label': 'DII net', 'value': f'₹{fmt_inr(f["dii"], 0)} CR', 'sub': 'buyers' if f['dii'] >= 0 else 'sellers'}],
                       'voice': f'Foreign investors were net {"buyers" if f["fii"] >= 0 else "sellers"} of {V.crore(f["fii"])}, '
                                f'while domestic institutions were net {"buyers" if f["dii"] >= 0 else "sellers"} of {V.crore(f["dii"])}.'})
        paras.append(f'FII net {"buy" if f["fii"] >= 0 else "sell"}: ₹{fmt_inr(abs(f["fii"]))} crore; DII net '
                     f'{"buy" if f["dii"] >= 0 else "sell"}: ₹{fmt_inr(abs(f["dii"]))} crore ({fmt_date(f["date"])}).')
        allowed += [abs(f['fii']), abs(f['dii']), round(f['fii']), round(f['dii']), f['date'].day, f['date'].year]
        report.ok('FII/DII from NSE')
    except nse.SourceError as e:
        report.warn(f'FII/DII unavailable ({e}) - scene left out')
    # day ahead
    try:
        res = [e for e in nse.event_calendar() if e['date'] == today and 'result' in (e['purpose'] or '').lower()]
    except nse.SourceError:
        res = []
    try:
        ipos = [i for i in nse.ipos_current() or []
                if (lambda a, b: a and b and a.date() <= today <= b.date())(nse.parse_nse_date(i.get('issueStartDate', '')),
                                                                           nse.parse_nse_date(i.get('issueEndDate', '')))]
    except nse.SourceError:
        ipos = []
    if res or ipos:
        rows = [{'label': short_name(r['symbol'], r.get('company')), 'sub': 'results today'} for r in res[:4]] + \
               [{'label': (i.get('symbol') or i.get('companyName') or '')[:18], 'sub': 'IPO open for bidding'} for i in ipos[:2]]
        v = (f'{len(res)} companies announce results today, including {", ".join(short_name(r["symbol"], r.get("company")) for r in res[:3])}. ' if res else '') + \
            (f'{len(ipos)} IPO{"s are" if len(ipos) > 1 else " is"} open for bidding.' if ipos else '')
        scenes.append({'type': 'rows', 'title': 'On the radar today', 'rows': rows, 'voice': v, 'topic': 'calendar'})
        if res:
            paras.append(f'Results today ({len(res)}): ' + ', '.join(short_name(r['symbol'], r.get('company')) for r in res[:8]) + '.')
            allowed.append(len(res))
        if ipos:
            paras.append('IPOs open: ' + ', '.join(i.get('companyName') or i.get('symbol') for i in ipos) + '.')
            allowed.append(len(ipos))
    if len(scenes) < 2:
        report.fail('not enough confirmed data for the morning reel')
        finish_video('reel_morning', key, None, None, '', report); return
    hook = '; '.join(hook_bits) or 'What to know before the bell'
    scenes.insert(0, {'type': 'intro', 'title': 'Morning Brief', 'day': today, 'hook': hook[0].upper() + hook[1:],
                      'topic': 'intro', 'voice': f'Good morning. Here is your market brief for {today.strftime("%A")}, '
                                                 f'{today.day} {today.strftime("%B")}.'})
    scenes.append(_outro())
    caption = assemble(f'Morning Brief: {fmt_date(today)}', paras + ['Watch for the full brief before the bell.'], '',
                       tags('#StockMarketIndia', '#Nifty50', '#Sensex', '#MorningBrief', '#ShareMarket'))
    if _make('reel_morning', key, 'Morning Brief', scenes, caption, report, allowed, str(today)):
        store.mark_seen('post', key)


# ---------------------------------------------------------------- Closing Bell (about 5 PM)

@as_post('reel_evening')
def evening_reel(force=False):
    today = today_ist()
    key = f'reel-pm:{today}'
    if store.seen('post', key) and not force:
        return
    t = now_ist()
    if t.weekday() < 5 and (t.hour, t.minute) < market_jobs.CLOSE_READY and not force:
        log.info('market not closed yet'); return
    report = Report()
    quotes, breadth, nse_date, rep = market.market_snapshot()
    report.extend(_relabel(rep, ('NIFTY 50', 'SENSEX', 'NIFTY BANK')))
    if not market.traded_today(nse_date, quotes) and not force:
        log.info('no session today - no evening reel'); return
    day = nse_date or today
    n, np_ = _q(quotes, 'NIFTY 50')
    s, sp = _q(quotes, 'SENSEX')
    b, bp = _q(quotes, 'NIFTY BANK')
    if not (n and s):
        report.fail('Nifty/Sensex close missing')
        finish_video('reel_evening', key, None, None, '', report); return
    up = n['chg'] >= 0
    tone = 'up' if up else 'down'
    allowed = [day.day, day.year, n['close'], s['close'], abs(np_), abs(sp), abs(n['chg']), abs(s['chg'])]
    rows = [{'label': 'Nifty 50', 'value': fmt_inr(n['close'], 0), 'pct': np_},
            {'label': 'Sensex', 'value': fmt_inr(s['close'], 0), 'pct': sp}]
    v = f'The Nifty closed at {V.pts(n["close"])}, {V.move(n["chg"], np_)}. The Sensex ended at {V.pts(s["close"])}, {V.move(s["chg"], sp)}.'
    paras = [f'On {fmt_date(day)}, the Nifty 50 closed at {fmt_inr(n["close"])} ({np_:+.2f}%) and the Sensex at '
             f'{fmt_inr(s["close"])} ({sp:+.2f}%).']
    for name, lab in (('NIFTY BANK', 'Nifty Bank'), ('NIFTY MIDCAP 100', 'Midcap 100'), ('NIFTY SMALLCAP 100', 'Smallcap 100')):
        q, p = _q(quotes, name)
        if q:
            rows.append({'label': lab, 'value': fmt_inr(q['close'], 0), 'pct': p})
            allowed += [q['close'], abs(p)]
    scenes = [{'type': 'rows', 'title': 'How the market closed', 'rows': rows, 'voice': v, 'topic': 'indices', 'tone': tone}]
    if breadth:
        allowed += [breadth['advances'], breadth['declines']]
        paras.append(f'{breadth["advances"]} stocks advanced and {breadth["declines"]} declined in the Nifty 500.')
        scenes[0]['voice'] += f' In the Nifty 500, {breadth["advances"]} stocks advanced and {breadth["declines"]} declined.'
    secs, rep2 = market.sector_snapshot()
    report.extend([('warn', m + ' - left out') if st == 'fail' else (st, m) for st, m in rep2])
    if secs:
        ranked = sorted(secs.values(), key=lambda x: x['pct'], reverse=True)
        top, bot = ranked[:3], ranked[-3:][::-1]
        scenes.append({'type': 'duo', 'title': 'Sectors', 'left_title': 'Best', 'right_title': 'Weakest',
                       'left': [{'label': sector_label(x['name']).replace('Nifty ', ''), 'pct': x['pct']} for x in top],
                       'right': [{'label': sector_label(x['name']).replace('Nifty ', ''), 'pct': x['pct']} for x in bot],
                       'topic': 'sectors', 'tone': tone,
                       'voice': f'{sector_label(top[0]["name"])} led the sectors, {"up" if top[0]["pct"] >= 0 else "down"} '
                                f'{V.pct(top[0]["pct"])}, while {sector_label(bot[0]["name"])} was the weakest, '
                                f'{"up" if bot[0]["pct"] >= 0 else "down"} {V.pct(bot[0]["pct"])}.'})
        paras.append(f'Best sector: {sector_label(top[0]["name"])} ({top[0]["pct"]:+.2f}%). '
                     f'Weakest: {sector_label(bot[0]["name"])} ({bot[0]["pct"]:+.2f}%).')
        allowed += [abs(x['pct']) for x in top + bot]
    try:
        gainers, losers = market.movers('NIFTY 50', 3)
        if nse.LAST_SOURCE.get('NIFTY 50', 'NSE') != 'NSE':
            report.warn('Nifty 50 movers: prices from Yahoo (NSE stock API unavailable)')
        scenes.append({'type': 'duo', 'title': 'Nifty 50 movers', 'left_title': 'Gainers', 'right_title': 'Losers',
                       'left': [{'label': name_of(x), 'pct': x['pct']} for x in gainers],
                       'right': [{'label': name_of(x), 'pct': x['pct']} for x in losers],
                       'topic': 'movers', 'tone': tone,
                       'voice': f'Among Nifty stocks, {name_of(gainers[0])} was the top gainer, {V.pct(gainers[0]["pct"])} higher, '
                                f'and {name_of(losers[0])} the top loser, down {V.pct(losers[0]["pct"])}.'})
        paras.append(f'Top Nifty 50 gainer: {name_of(gainers[0])} ({gainers[0]["pct"]:+.2f}%). '
                     f'Top loser: {name_of(losers[0])} ({losers[0]["pct"]:+.2f}%).')
        allowed += [abs(x['pct']) for x in gainers + losers]
    except (nse.SourceError, IndexError) as e:
        report.warn(f'movers unavailable ({e}) - scene left out')
    hl = store.read_json(f'daily/{day}/highslows.json')
    if hl:
        scenes.append({'type': 'rows', 'title': 'New highs and lows', 'topic': 'highs' if hl['ath'] or hl['hi52'] >= hl['lo52'] else 'lows',
                       'rows': [{'label': 'All-time highs', 'value': str(hl['ath'])},
                                {'label': '52-week highs', 'value': str(hl['hi52'])},
                                {'label': '52-week lows', 'value': str(hl['lo52'])}],
                       'voice': f'Across large, mid, small and micro caps, {hl["ath"]} stocks hit an all-time high, '
                                f'{hl["hi52"]} touched a 52-week high and {hl["lo52"]} a 52-week low.'})
        paras.append(f'New highs and lows: {hl["ath"]} all-time highs, {hl["hi52"]} 52-week highs, {hl["lo52"]} 52-week lows.')
        allowed += [hl['ath'], hl['hi52'], hl['lo52'], 52]
    verb = 'gains' if up else 'falls'
    hook = f'Nifty {verb} {fmt_inr(abs(n["chg"]), 0)} points; Sensex at {fmt_inr(s["close"], 0)}'
    allowed += [round(abs(n['chg'])), round(s['close'])]
    scenes.insert(0, {'type': 'intro', 'title': 'Closing Bell', 'day': day, 'hook': hook, 'topic': 'intro_pm', 'tone': tone,
                      'voice': f'Here is how the market closed on {day.strftime("%A")}, {day.day} {day.strftime("%B")}.'})
    scenes.append(_outro())
    caption = assemble(f'Closing Bell: {hook}', paras, '',
                       tags('#StockMarketIndia', '#Nifty50', '#Sensex', '#MarketClose', '#ShareMarket'))
    if _make('reel_evening', key, 'Closing Bell', scenes, caption, report, allowed, str(day)):
        store.mark_seen('post', key)


# ---------------------------------------------------------------- Week in Review (Saturday)

def _week_change(ysym):
    import yfinance as yf
    h = yf.Ticker(ysym).history(period='1mo', interval='1d', auto_adjust=False).dropna(subset=['Close'])
    mon = today_ist() - timedelta(days=today_ist().weekday())
    before = h[[d.date() < mon for d in h.index]]
    week = h[[d.date() >= mon for d in h.index]]
    if before.empty or week.empty:
        return None
    a, b = float(before['Close'].iloc[-1]), float(week['Close'].iloc[-1])
    return {'start': a, 'end': b, 'pct': (b - a) / a * 100, 'last_date': week.index[-1].date()}


@as_post('reel_weekly')
def weekly_reel(force=False):
    today = today_ist()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)
    key = f'reel-week:{monday}'
    if store.seen('post', key) and not force:
        return
    report = Report()
    quotes, _, nse_date, rep = market.market_snapshot()
    report.extend([r for r in rep if r[0] != 'ok'])
    rows, allowed, paras = [], [monday.day, friday.day, friday.year], []
    lines = []
    for name, ysym, lab in (('NIFTY 50', '^NSEI', 'Nifty 50'), ('SENSEX', '^BSESN', 'Sensex'), ('NIFTY BANK', '^NSEBANK', 'Nifty Bank')):
        try:
            w = _week_change(ysym)
        except Exception as e:                       # noqa: BLE001
            report.warn(f'{lab}: weekly history unavailable ({type(e).__name__})'); continue
        q = quotes.get(name)
        if not w:
            continue
        if q and abs(w['end'] - q['close']) / q['close'] * 100 > 0.05:
            report.warn(f'{lab}: Yahoo week close {w["end"]:.2f} vs official {q["close"]:.2f} - left out'); continue
        rows.append({'label': lab, 'value': fmt_inr(w['end'], 0), 'pct': w['pct']})
        allowed += [w['end'], abs(w['pct'])]
        lines.append(f'{lab}: {fmt_inr(w["end"])} ({w["pct"]:+.2f}% for the week)')
    if not rows:
        report.fail('no weekly index data confirmed')
        finish_video('reel_weekly', key, None, None, '', report); return
    n = rows[0]
    tone = 'up' if n['pct'] >= 0 else 'down'
    scenes = [{'type': 'rows', 'title': 'The week for indices', 'rows': rows, 'topic': 'indices', 'tone': tone,
               'voice': ' '.join(f'The {r["label"]} {"gained" if r["pct"] >= 0 else "lost"} {V.pct(r["pct"])} this week, '
                                 f'closing at {V.pts(float(r["value"].replace(",", "")))}.' for r in rows[:2])}]
    paras.append('\n'.join(lines))
    hist = store.read_json('fii/history.json', {}) or {}
    wk = [d for d in sorted(hist) if str(monday) <= d <= str(friday)]
    if len(wk) >= 3:
        fii = round(sum(hist[d]['fii'] for d in wk), 2)
        dii = round(sum(hist[d]['dii'] for d in wk), 2)
        scenes.append({'type': 'rows', 'title': f'FII / DII this week ({len(wk)} sessions)', 'topic': 'flows',
                       'rows': [{'label': 'FII net', 'value': f'₹{fmt_inr(fii, 0)} CR', 'sub': 'buyers' if fii >= 0 else 'sellers'},
                                {'label': 'DII net', 'value': f'₹{fmt_inr(dii, 0)} CR', 'sub': 'buyers' if dii >= 0 else 'sellers'}],
                       'voice': f'Over the week, foreign investors were net {"buyers" if fii >= 0 else "sellers"} of {V.crore(fii)}, '
                                f'and domestic institutions net {"buyers" if dii >= 0 else "sellers"} of {V.crore(dii)}.'})
        paras.append(f'FII net for the week: ₹{fmt_inr(fii)} crore; DII net: ₹{fmt_inr(dii)} crore ({len(wk)} sessions).')
        allowed += [abs(fii), abs(dii), round(fii), round(dii), len(wk)]
    wkx = store.read_json(f'weekly/{monday}.json')
    if wkx and len(wkx.get('groups') or {}) == len(market.CAP_SEGMENTS):
        ath = sum(g['ath_count'] for g in wkx['groups'].values())
        low = sum(g['low_count'] for g in wkx['groups'].values())
        scenes.append({'type': 'rows', 'title': 'Highs and lows this week', 'topic': 'highs' if ath >= low else 'lows',
                       'rows': [{'label': 'All-time highs', 'value': str(ath)}, {'label': '52-week lows', 'value': str(low)}],
                       'voice': f'This week, {ath} stocks across large, mid, small and micro caps made an all-time high, '
                                f'and {low} fell to a 52-week low.'})
        paras.append(f'This week: {ath} stocks at all-time highs and {low} at 52-week lows across the four market-cap groups.')
        allowed += [ath, low, 52]
    label = f'{monday.day}-{friday.day} {friday.strftime("%b")}' if monday.month == friday.month else \
        f'{monday.day} {monday.strftime("%b")} - {friday.day} {friday.strftime("%b")}'
    scenes.insert(0, {'type': 'intro', 'title': 'Week in Review', 'day': friday, 'topic': 'intro_week', 'tone': tone,
                      'hook': f'Nifty {"gains" if n["pct"] >= 0 else "falls"} {abs(n["pct"]):.2f}% this week',
                      'voice': f'Here is your week in review for the markets, {label.replace("-", " to ")}.'})
    allowed.append(round(abs(n['pct']), 2))
    scenes.append(_outro())
    caption = assemble(f'Week in Review: {label}', paras, '',
                       tags('#StockMarketIndia', '#Nifty50', '#WeeklyRecap', '#Sensex', '#ShareMarket'))
    if _make('reel_weekly', key, 'Week in Review', scenes, caption, report, allowed, str(monday)):
        store.mark_seen('post', key)


# ---------------------------------------------------------------- weekly all-time highs / 52-week lows reels

def _extremes_reel(kind, force):
    today = today_ist()
    monday = today - timedelta(days=today.weekday())
    job = 'reel_ath' if kind == 'ath' else 'reel_lows'
    key = f'{job}:{monday}'
    if store.seen('post', key) and not force:
        return
    report = Report()
    wkx = store.read_json(f'weekly/{monday}.json')
    if not wkx or len(wkx.get('groups') or {}) != len(market.CAP_SEGMENTS):
        log.info('%s: weekly scan not ready yet', job); return
    report.extend([tuple(r) for r in wkx['report']])
    what = 'all-time high' if kind == 'ath' else '52-week low'
    label = 'All-Time Highs' if kind == 'ath' else '52-Week Lows'
    total = sum(g[f'{kind}_count'] for g in wkx['groups'].values())
    if total == 0 and not force:
        log.info('%s: no stocks this week', job); return
    scenes, paras, allowed = [], [], [total, 52, 3, monday.day, monday.year]
    for seg, _ in market.CAP_SEGMENTS:
        g = wkx['groups'][seg]
        top = g[kind][:3]
        if not top:
            continue
        scenes.append({'type': 'rows', 'title': f'{seg}: {g[f"{kind}_count"]} stocks', 'topic': 'highs' if kind == 'ath' else 'lows',
                       'tone': 'up' if kind == 'ath' else 'down',
                       'rows': [{'label': name_of(r), 'value': '₹' + fmt_inr(r['close'] if 'close' in r else r.get('last', 0)),
                                 'pct': r['week_pct']} for r in top],
                       'voice': f'In {seg.lower()}, {g[f"{kind}_count"]} stocks hit a {what} this week, including '
                                f'{", ".join(name_of(r) for r in top)}.'})
        paras.append(f'{seg}: {g[f"{kind}_count"]} - ' + ', '.join(f'{name_of(r)} ({r["week_pct"]:+.2f}%)' for r in top))
        allowed += [g[f'{kind}_count']] + [abs(r['week_pct']) for r in top] + \
                   [r.get('close') or r.get('last') or 0 for r in top]
    scenes.insert(0, {'type': 'intro', 'title': label, 'day': today, 'topic': 'highs' if kind == 'ath' else 'lows',
                      'tone': 'up' if kind == 'ath' else 'down',
                      'hook': f'{total} stocks hit a {what} this week',
                      'voice': f'{total} stocks across the four market-cap groups hit a {what} this week. Here are the top names.'})
    scenes.append(_outro())
    caption = assemble(f'{total} stocks hit a {what} this week', paras + ['Weekly % change in brackets.'], '',
                       tags('#AllTimeHigh' if kind == 'ath' else '#52WeekLow', '#StockMarketIndia', '#Nifty50',
                            '#SmallCap', '#ShareMarket'))
    if _make(job, key, label, scenes, caption, report, allowed, f'{kind}{monday}'):
        store.mark_seen('post', key)


@as_post('reel_ath')
def ath_reel(force=False):
    _extremes_reel('ath', force)


@as_post('reel_lows')
def lows_reel(force=False):
    _extremes_reel('low', force)
