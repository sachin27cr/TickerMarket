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


def _outro(line='For more market data, visit our page and follow Ticker Market India.'):
    return {'type': 'outro', 'topic': 'outro', 'voice': line}


def _fii_for(day):
    """FII/DII net for `day` from the same store the FII/DII post uses (NSE provisional data), else NSE directly."""
    hist = store.read_json('fii/history.json', {}) or {}
    rec = hist.get(str(day))
    if not rec:
        try:
            f = nse.fii_dii()
            if f['date'] == day:
                rec = {'fii': f['fii'], 'dii': f['dii']}
                hist[str(day)] = rec
        except nse.SourceError:
            return None
    if not rec:
        return None
    month = [k for k in hist if k.startswith(day.strftime('%Y-%m')) and k <= str(day)]
    return {'fii': rec['fii'], 'dii': rec['dii'], 'sessions': len(month),
            'm_fii': round(sum(hist[k]['fii'] for k in month), 2), 'm_dii': round(sum(hist[k]['dii'] for k in month), 2)}


def _commodity_line(com):
    """One insight: the biggest mover among crude, gold and the rupee."""
    x = max(com, key=lambda c: abs(c['pct']))
    if x['name'] == 'USD / INR':
        return f'The rupee is the mover, {"weaker" if x["pct"] > 0 else "stronger"} against the dollar.'
    nm = 'Crude' if 'Crude' in x['name'] else x['name']
    return f'{nm} is the big mover, {V.signed(x["pct"])}.'


def _pick(hl, key):
    out = []
    for seg, g in (hl.get('groups') or {}).items():
        for r in g.get(key) or []:
            if isinstance(r, dict):
                out.append({**r, 'seg': seg})
    return out


def _list_scenes(hl, tone):
    """On-screen lists of the stocks at new highs / lows (names are shown, not read out), about 3 s each."""
    scenes = []
    highs = sorted(_pick(hl, 'ath'), key=lambda r: r['pct'], reverse=True)
    title = f'All-time highs today ({hl["ath"]})'
    if not highs:
        highs = sorted(_pick(hl, 'hi52'), key=lambda r: r['pct'], reverse=True)
        title = f'52-week highs today ({hl["hi52"]})'
    lows = sorted(_pick(hl, 'lo52'), key=lambda r: r['pct'])
    for t, rows, topic, lvl in ((title, highs, 'highs', 'day_high'), (f'52-week lows today ({hl["lo52"]})', lows, 'lows', 'day_low')):
        if rows:
            scenes.append({'type': 'rows', 'title': t, 'topic': topic, 'tone': tone, 'voice': '', 'hold': 3.4,
                           'rows': [{'label': r['name'], 'pct': r['pct'],
                                     'sub': r['seg'] + (' · touched a new high today' if lvl == 'day_high' else ' · touched a new low today')}
                                    for r in rows[:6]]})
    return scenes


def _make(kind, title, label, scenes, caption, report, allowed, seed):
    out = Path(tempfile.mkdtemp()) / f'{kind}.mp4'
    path, cover, rep, _ = render.build(scenes, label, out, seed)
    report.extend(rep)
    script = [voice_line for voice_line in (sc.get('voice') for sc in scenes)]
    script = [(f'{i + 1}. ' + (v or '(on-screen list, no voice)')) for i, v in enumerate(script)]
    return finish_video(kind, title, path, cover, caption, report, allowed, script)


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
    hook_facts = []                                # (strong?, on-screen text, spoken text)
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
        v = ''
        if us:
            lead = max(us, key=lambda x: abs(x['pct']))
            mood = 'higher' if up_us == len(us) else 'lower' if up_us == 0 else 'mixed'
            v = (f'The {lead["name"]} did the heavy lifting, {V.signed(lead["pct"])}. ' if mood != 'mixed' else
                 f'A mixed close on Wall Street: the {lead["name"]} {V.signed(lead["pct"])}. ')
        big_asia = [x for x in asia if abs(x['pct']) >= 1]
        if big_asia:
            v += f'In Asia, the {big_asia[0]["name"]} is {V.signed(big_asia[0]["pct"])}.'
        scenes.append({'type': 'rows', 'title': 'Global markets', 'rows': rows, 'voice': v, 'topic': 'global',
                       'tone': 'up' if up_us * 2 >= max(1, len(us)) else 'down'})
        paras.append('Global markets: ' + '; '.join(f'{x["name"]} {x["value"]} ({x["pct"]:+.2f}%)' for x in us + asia) + '.')
        allowed += [x['close'] for x in us + asia] + [abs(x['pct']) for x in us + asia]
        if us:
            hook_facts.append((up_us in (0, len(us)), f'Wall Street {"closes higher" if up_us * 2 >= len(us) else "slips"}',
                               f'Wall Street {"closed higher" if up_us * 2 >= len(us) else "slipped"}'))
    com = [g[k] for k in ('Brent Crude', 'Gold', 'USD / INR') if k in g]
    if com:
        scenes.append({'type': 'rows', 'title': 'Crude, gold and rupee', 'topic': 'commodities',
                       'rows': [{'label': x['name'], 'value': x['value'], 'pct': x['pct']} for x in com],
                       'voice': _commodity_line(com)})
        paras.append('Commodities and currency: ' + '; '.join(f'{x["name"]} {x["value"]} ({x["pct"]:+.2f}%)' for x in com) + '.')
        allowed += [x['close'] for x in com] + [abs(x['pct']) for x in com]
        brent = g.get('Brent Crude')
        if brent and abs(brent['pct']) >= 1:
            hook_facts.append((True, f'crude {"jumps" if brent["pct"] > 0 else "slides"} {abs(brent["pct"]):.1f}%',
                               f'crude {"jumped" if brent["pct"] > 0 else "slid"} {V.pct(brent["pct"])}'))
            allowed.append(round(abs(brent['pct']), 1))
    if n and s:
        last = fmt_date(nse_date, 'long') if nse_date else 'the last session'
        scenes.append({'type': 'rows', 'title': f'Last close ({fmt_date(nse_date, "daymonth") if nse_date else ""})',
                       'topic': 'indices', 'tone': 'up' if n['chg'] >= 0 else 'down',
                       'rows': [{'label': 'Nifty 50', 'value': fmt_inr(n['close'], 0), 'pct': np_},
                                {'label': 'Sensex', 'value': fmt_inr(s['close'], 0), 'pct': sp}],
                       'voice': f'Back home, the Nifty ended the last session {V.signed(np_)} at {V.pts(n["close"])}.'})
        paras.append(f'Last close ({last}): Nifty 50 {fmt_inr(n["close"])} ({np_:+.2f}%), Sensex {fmt_inr(s["close"])} ({sp:+.2f}%).')
        allowed += [n['close'], s['close'], abs(np_), abs(sp)]
    # FII / DII
    try:
        f = nse.fii_dii()
        scenes.append({'type': 'rows', 'title': f'FII / DII ({fmt_date(f["date"], "daymonth")})', 'topic': 'flows',
                       'tone': 'up' if f['fii'] >= 0 else 'down',
                       'rows': [{'label': 'FII net', 'value': f'₹{fmt_inr(f["fii"], 0)} CR', 'sub': 'buyers' if f['fii'] >= 0 else 'sellers'},
                                {'label': 'DII net', 'value': f'₹{fmt_inr(f["dii"], 0)} CR', 'sub': 'buyers' if f['dii'] >= 0 else 'sellers'}],
                       'voice': f'The money flows: FIIs {"bought" if f["fii"] >= 0 else "sold"} {V.crore(f["fii"])}, '
                                f'DIIs {"bought" if f["dii"] >= 0 else "sold"} {V.crore(f["dii"])}.'})
        hook_facts.append((abs(f['fii']) >= 1000, f'FIIs {"bought" if f["fii"] >= 0 else "sold"} ₹{fmt_inr(abs(f["fii"]), 0)} crore',
                           f'FIIs {"bought" if f["fii"] >= 0 else "sold"} {V.crore(f["fii"])}'))
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
        v = (f'Results today from {", ".join(short_name(r["symbol"], r.get("company")) for r in res[:2])}'
             f'{" and more" if len(res) > 2 else ""}. ' if res else '') + \
            (f'And {len(ipos)} IPO{"s" if len(ipos) > 1 else ""} open for bidding.' if ipos else '')
        scenes.append({'type': 'rows', 'title': 'On the radar today', 'rows': rows, 'voice': v, 'topic': 'calendar'})
        if res:
            paras.append(f'Results today ({len(res)}): ' + ', '.join(short_name(r['symbol'], r.get('company')) for r in res[:8]) + '.')
            allowed.append(len(res))
        if ipos:
            paras.append('IPOs open: ' + ', '.join(i.get('companyName') or i.get('symbol') for i in ipos) + '.')
            allowed.append(len(ipos))
    # global & India events today, and the results calendar for the week
    from ..sources import calendar as cal
    evs = cal.events_today()
    if evs:
        scenes.append({'type': 'rows', 'title': 'Events to watch today (IST)', 'topic': 'global',
                       'rows': [{'label': e['title'][:30], 'sub': f'{e["country"]}, {e["when"].strftime("%-I:%M %p")}'}
                                for e in evs[:5]],
                       'voice': f'On the radar: {evs[0]["country"]} {evs[0]["title"]} at {V.clock(evs[0]["when"])}.'
                                + (f' Plus {len(evs) - 1} more on screen.' if len(evs) > 1 else '')})
        hook_facts.append((True, f'{evs[0]["country"]} {evs[0]["title"]} at {evs[0]["when"].strftime("%-I:%M %p")}',
                           f'{evs[0]["country"]} {evs[0]["title"]} at {V.clock(evs[0]["when"])}'))
        paras.append('Events to watch today (IST): ' + '; '.join(
            f'{e["when"].strftime("%-I:%M %p")} {e["country"]}: {e["title"]}' for e in evs[:6]) + '.')
        allowed += [len(evs)] + [float(e['when'].strftime('%-I')) for e in evs] + [float(e['when'].strftime('%M')) for e in evs]
    sched = cal.results_schedule(6)
    if sched:
        total = sum(len(v) for v in sched.values())
        rows = []
        for d_, items in list(sched.items())[:5]:
            top = [short_name(sym, comp) for sym, comp in cal.well_known_first(items)[:2]]
            rows.append({'label': ('Today' if d_ == today else d_.strftime('%a, ') + fmt_date(d_, 'daymonth')),
                         'value': str(len(items)), 'sub': ', '.join(top)})
        scenes.append({'type': 'rows', 'title': 'Results calendar this week', 'rows': rows, 'topic': 'calendar',
                       'voice': f'Results season: {total} companies report this week'
                                + (f', including {rows[0]["sub"].split(", ")[0]}.' if rows and rows[0]['sub'] else '.')})
        paras.append('Results calendar: ' + '; '.join(f'{r["label"]}: {r["value"]} companies ({r["sub"]})' for r in rows) + '.')
        allowed += [total] + [float(r['value']) for r in rows] + [d_.day for d_ in sched]
    if len(scenes) < 2:
        report.fail('not enough confirmed data for the morning reel')
        finish_video('reel_morning', key, None, None, '', report); return
    strong = [h for h in hook_facts if h[0]][:2] or hook_facts[:2]
    hook = '; '.join(h[1] for h in strong) or 'What to know before the bell'
    spoken = '. '.join(h[2] for h in strong)
    scenes.insert(0, {'type': 'intro', 'title': 'Morning Brief', 'day': today, 'hook': hook[0].upper() + hook[1:],
                      'topic': 'intro', 'voice': (spoken[0].upper() + spoken[1:] + '. ' if spoken else '')
                                                 + 'Your 60-second brief before the bell.'})
    scenes.append(_outro('Follow for your brief every morning.'))
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
    v = f'The Nifty settled at {V.pts(n["close"])}.'
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
        adv, dec = breadth['advances'], breadth['declines']
        mood = 'strong' if adv >= 1.5 * dec else 'weak' if dec >= 1.5 * adv else 'evenly split'
        scenes[0]['voice'] += f' Breadth was {mood}: {adv} stocks up, {dec} down.'
    mid = _q(quotes, 'NIFTY MIDCAP 100')[1]
    if mid is not None and abs(mid - np_) >= 0.3:
        scenes[0]['voice'] += f' Mid caps {"beat" if mid > np_ else "lagged"} the Nifty.'
    secs, rep2 = market.sector_snapshot()
    report.extend([('warn', m + ' - left out') if st == 'fail' else (st, m) for st, m in rep2])
    if secs:
        ranked = sorted(secs.values(), key=lambda x: x['pct'], reverse=True)
        top, bot = ranked[:3], ranked[-3:][::-1]
        scenes.append({'type': 'duo', 'title': 'Sectors', 'left_title': 'Best', 'right_title': 'Weakest',
                       'left': [{'label': sector_label(x['name']).replace('Nifty ', ''), 'pct': x['pct']} for x in top],
                       'right': [{'label': sector_label(x['name']).replace('Nifty ', ''), 'pct': x['pct']} for x in bot],
                       'topic': 'sectors', 'tone': tone,
                       'voice': f'{sector_label(top[0]["name"])} led, {V.signed(top[0]["pct"])}. '
                                f'{sector_label(bot[0]["name"])} {"lagged" if bot[0]["pct"] >= 0 else "was the biggest drag"}.'})
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
                       'voice': f'{name_of(gainers[0])} topped the Nifty, {V.signed(gainers[0]["pct"])}. '
                                f'{name_of(losers[0])} was the biggest loser.'})
        paras.append(f'Top Nifty 50 gainer: {name_of(gainers[0])} ({gainers[0]["pct"]:+.2f}%). '
                     f'Top loser: {name_of(losers[0])} ({losers[0]["pct"]:+.2f}%).')
        allowed += [abs(x['pct']) for x in gainers + losers]
    except (nse.SourceError, IndexError) as e:
        report.warn(f'movers unavailable ({e}) - scene left out')
    fii = _fii_for(day)
    if fii is None and now_ist().hour < 20 and not force:
        log.info('FII/DII for %s not published yet - the reel is made once it is (the FII/DII job starts it)', day)
        return
    if fii:
        f, d_, mf, md, nses = fii['fii'], fii['dii'], fii['m_fii'], fii['m_dii'], fii['sessions']
        sgn = lambda v: f'{"+" if v >= 0 else "-"}₹{fmt_inr(abs(v), 0)} cr'
        frows = [{'label': 'FIIs today', 'value': sgn(f)}, {'label': 'DIIs today', 'value': sgn(d_)}]
        if nses > 1:
            frows += [{'label': f'FIIs, last {nses} sessions', 'value': sgn(mf)},
                      {'label': f'DIIs, last {nses} sessions', 'value': sgn(md)}]
        scenes.append({'type': 'rows', 'title': 'FII / DII flows', 'topic': 'flows', 'tone': 'up' if f >= 0 else 'down',
                       'rows': frows,
                       'voice': f'Foreign investors {"bought" if f >= 0 else "sold"} {V.crore(f)} of shares today, '
                                f'and domestic institutions {"bought" if d_ >= 0 else "sold"} {V.crore(d_)}.'})
        paras.append(f'FII/DII (NSE provisional): FIIs net {"bought" if f >= 0 else "sold"} ₹{fmt_inr(abs(f))} crore, '
                     f'DIIs net {"bought" if d_ >= 0 else "sold"} ₹{fmt_inr(abs(d_))} crore.')
        allowed += [abs(f), abs(d_), round(abs(f)), round(abs(d_)), abs(mf), abs(md), round(abs(mf)), round(abs(md)), nses]
    else:
        report.warn('FII/DII data not published by 8 PM - scene left out')
    hl = store.read_json(f'daily/{day}/highslows.json')
    if hl:
        scenes.append({'type': 'rows', 'title': 'New highs and lows', 'topic': 'highs' if hl['ath'] or hl['hi52'] >= hl['lo52'] else 'lows',
                       'rows': [{'label': 'All-time highs', 'value': str(hl['ath'])},
                                {'label': '52-week highs', 'value': str(hl['hi52'])},
                                {'label': '52-week lows', 'value': str(hl['lo52'])}],
                       'voice': (f'{hl["ath"]} stocks hit record highs today' if hl['ath'] else
                                 f'{hl["hi52"]} stocks hit 52-week highs today') + f', and {hl["lo52"]} hit 52-week lows. Here they are.'})
        paras.append(f'New highs and lows: {hl["ath"]} all-time highs, {hl["hi52"]} 52-week highs, {hl["lo52"]} 52-week lows.')
        allowed += [hl['ath'], hl['hi52'], hl['lo52'], 52]
        scenes += _list_scenes(hl, 'up' if up else 'down')
    verb = 'gains' if up else 'falls'
    hook = f'Nifty {verb} {fmt_inr(abs(n["chg"]), 0)} points; Sensex at {fmt_inr(s["close"], 0)}'
    allowed += [round(abs(n['chg'])), round(s['close'])]
    spoken = f'The Nifty {"gained" if up else "lost"} {V.pts(n["chg"])} points today'
    if secs:
        lead = top[0] if up else bot[0]
        spoken += f', and {sector_label(lead["name"])} {"led the charge" if up else "dragged the most"}'
    scenes.insert(0, {'type': 'intro', 'title': 'Closing Bell', 'day': day, 'hook': hook, 'topic': 'intro_pm', 'tone': tone,
                      'voice': spoken + '. Here is how the day played out.'})
    scenes.append(_outro('For the full details, visit our page, and follow Ticker Market India for the closing bell '
                         'every evening.'))
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
               'voice': f'The Nifty closed the week at {V.pts(float(n["value"].replace(",", "")))}.'
                        + (lambda b: f' Bank Nifty {"outperformed" if b["pct"] > n["pct"] + 0.05 else "lagged" if b["pct"] < n["pct"] - 0.05 else "kept pace"}, {V.signed(b["pct"])}.'
                           if b else '')(next((r for r in rows if r['label'] == 'Nifty Bank'), None))}]
    paras.append('\n'.join(lines))
    hist = store.read_json('fii/history.json', {}) or {}
    wk = [d for d in sorted(hist) if str(monday) <= d <= str(friday)]
    if len(wk) >= 3:
        fii = round(sum(hist[d]['fii'] for d in wk), 2)
        dii = round(sum(hist[d]['dii'] for d in wk), 2)
        scenes.append({'type': 'rows', 'title': f'FII / DII this week ({len(wk)} sessions)', 'topic': 'flows',
                       'rows': [{'label': 'FII net', 'value': f'₹{fmt_inr(fii, 0)} CR', 'sub': 'buyers' if fii >= 0 else 'sellers'},
                                {'label': 'DII net', 'value': f'₹{fmt_inr(dii, 0)} CR', 'sub': 'buyers' if dii >= 0 else 'sellers'}],
                       'voice': f'FIIs {"bought" if fii >= 0 else "sold"} {V.crore(fii)} over the week. '
                                f'DIIs {"bought" if dii >= 0 else "sold"} {V.crore(dii)}.'})
        paras.append(f'FII net for the week: ₹{fmt_inr(fii)} crore; DII net: ₹{fmt_inr(dii)} crore ({len(wk)} sessions).')
        allowed += [abs(fii), abs(dii), round(fii), round(dii), len(wk)]
    wkx = store.read_json(f'weekly/{monday}.json')
    if wkx and len(wkx.get('groups') or {}) == len(market.CAP_SEGMENTS):
        ath = sum(g['ath_count'] for g in wkx['groups'].values())
        low = sum(g['low_count'] for g in wkx['groups'].values())
        scenes.append({'type': 'rows', 'title': 'Highs and lows this week', 'topic': 'highs' if ath >= low else 'lows',
                       'rows': [{'label': 'All-time highs', 'value': str(ath)}, {'label': '52-week lows', 'value': str(low)}],
                       'voice': f'{ath} stocks hit record highs this week. {low} sank to 52-week lows.'})
        paras.append(f'This week: {ath} stocks at all-time highs and {low} at 52-week lows across the four market-cap groups.')
        allowed += [ath, low, 52]
    label = f'{monday.day}-{friday.day} {friday.strftime("%b")}' if monday.month == friday.month else \
        f'{monday.day} {monday.strftime("%b")} - {friday.day} {friday.strftime("%b")}'
    scenes.insert(0, {'type': 'intro', 'title': 'Week in Review', 'day': friday, 'topic': 'intro_week', 'tone': tone,
                      'hook': f'Nifty {"gains" if n["pct"] >= 0 else "falls"} {abs(n["pct"]):.2f}% this week',
                      'voice': f'The Nifty {"gained" if n["pct"] >= 0 else "lost"} {V.pct(n["pct"])} this week. '
                               f'Here is the week in 30 seconds.'})
    allowed.append(round(abs(n['pct']), 2))
    scenes.append(_outro('Follow for the week in review every Saturday.'))
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
                       'voice': f'{seg}: {g[f"{kind}_count"]}.'})
        paras.append(f'{seg}: {g[f"{kind}_count"]} - ' + ', '.join(f'{name_of(r)} ({r["week_pct"]:+.2f}%)' for r in top))
        allowed += [g[f'{kind}_count']] + [abs(r['week_pct']) for r in top] + \
                   [r.get('close') or r.get('last') or 0 for r in top]
    lead_seg, lead_n = max(((seg, wkx['groups'][seg][f'{kind}_count']) for seg, _ in market.CAP_SEGMENTS), key=lambda x: x[1])
    scenes.insert(0, {'type': 'intro', 'title': label, 'day': today, 'topic': 'highs' if kind == 'ath' else 'lows',
                      'tone': 'up' if kind == 'ath' else 'down',
                      'hook': f'{total} stocks hit a{"n" if kind == "ath" else ""} {what} this week',
                      'voice': f'{total} stocks hit a{"n" if kind == "ath" else ""} {what} this week. '
                               f'{lead_seg} led with {lead_n}. Here are the names.'})
    scenes.append(_outro())
    caption = assemble(f'{total} stocks hit a{"n" if kind == "ath" else ""} {what} this week', paras + ['Weekly % change in brackets.'], '',
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


# ---------------------------------------------------------------- explainer reels written in the repo
CUSTOM_DIR = Path(__file__).resolve().parents[2] / 'config' / 'custom_reels'


def custom_reel(force=False, name=None):
    """Explainer reel from config/custom_reels/<name>.json (scenes + caption, facts checked when written).
    Started from Telegram with /customreel <name>; goes to approval like every reel."""
    import json
    import os
    name = (name or os.environ.get('TM_ARG', '')).strip()
    files = sorted(p.stem for p in CUSTOM_DIR.glob('*.json'))
    if not name:
        name = files[-1] if files else ''
    path = CUSTOM_DIR / f'{name}.json'
    if not path.exists():
        from .. import telegram
        telegram.send_text('Custom reels available: ' + (', '.join(files) or 'none'))
        return
    spec = json.loads(path.read_text())
    from datetime import date
    scenes = []
    for sc in spec['scenes']:
        sc = dict(sc)
        if sc['type'] == 'intro':
            sc['day'] = date.fromisoformat(sc['day'])
        scenes.append(sc)
    report = Report()
    report.ok('explainer reel: facts taken from the sources listed in the file ' + ', '.join(spec.get('sources', [])[:4]))
    caption = assemble(spec['headline'], spec['paras'], '', tags(*spec.get('tags', [])))
    return _make('reel_custom', spec['headline'], spec.get('label', 'Market Explainer'), scenes, caption, report,
                 None, name)
