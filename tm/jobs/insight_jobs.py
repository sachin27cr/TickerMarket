"""Insights: data-story carousels (results season winners, monthly asset scorecard, most valuable companies,
one-year wealth creators, sector scorecard). One every other day on schedule, or on demand from Telegram:

    /innovative            next one in the rotation
    /innovative profits    a specific one (tags below)
    /innovative list       show the tags

Captions are fixed templates; every number in them must match the data. Insights always wait for your
approval in Telegram (they are never auto-posted), and anything single-source shows as a warning.
"""
import re
from datetime import date

from .. import store, telegram
from ..render import cards, insight_cards as ic
from ..sources import insights as src, market
from ..util import fmt_date, fmt_inr, log, today_ist
from ..verify.checks import Report
from ..writer.captions import assemble, tags
from .common import finish

STATE = 'insights/state.json'
EVERY_DAYS = 2                      # scheduled run posts if the last insight is at least this old

TAGS = {
    'profits': 'Results season: companies whose quarterly profit more than doubled (series, part by part)',
    'assets': 'How major assets did last month (Nifty, Sensex, gold, silver, crude, rupee, Nasdaq, bitcoin)',
    'mcap': "India's 10 most valuable listed companies and their change this week",
    'wealth': 'Nifty 50 over one year: what Rs 1 lakh became in the best and worst stocks',
    'sectors': 'Sector scorecard: 1-week, 1-month and 1-year change of 16 sector indices',
}
MIN_GAP = {'profits': 2, 'assets': 25, 'mcap': 7, 'wealth': 14, 'sectors': 7}


def _state():
    return store.read_json(STATE) or {'last_post': None, 'last': {}, 'profits': {}}


def _save(st):
    store.write_json(STATE, st)


def _days_since(iso):
    return 999 if not iso else (today_ist() - date.fromisoformat(iso)).days


def _names():
    try:
        return dict(market.equity_master())
    except Exception as e:                       # noqa: BLE001
        log.warning('equity list unavailable: %s', e)
        return {}


def _clean(name):
    return re.sub(r'\s+', ' ', re.sub(r'\b(limited|ltd\.?)\b', '', name, flags=re.I)).strip(' .') or name


def _name_numbers(*names):
    return [float(x) for n in names for x in re.findall(r'\d+(?:\.\d+)?', n)]


def _done(tag, st):
    st['last'][tag] = str(today_ist())
    st['last_post'] = str(today_ist())
    _save(st)


# ---------------------------------------------------------------- 1. profits

def _yq_cache():
    raw = store.read_json(f'cache/yq/{today_ist()}.json') or {}
    return {s: {date.fromisoformat(k): v for k, v in q.items()} for s, q in raw.items()}


def _save_yq(cache):
    store.write_json(f'cache/yq/{today_ist()}.json', {s: {str(k): v for k, v in q.items()} for s, q in cache.items()})


def profits(force=False, st=None):
    st = st or _state()
    report = Report()
    cache = _yq_cache()
    try:
        found, rep = src.profit_growth_scan('NIFTY 500', 100.0, 10.0, cache)
    finally:
        _save_yq(cache)
    report.extend(rep)
    if not found:
        log.info('profits: nothing confirmed'); return None
    quarter = max(found, key=lambda r: r['q_end'])['quarter']
    found = [r for r in found if r['quarter'] == quarter]
    ps = st['profits'].setdefault(quarter, {'posted': [], 'part': 0})
    fresh = [r for r in found if r['symbol'] not in ps['posted']]
    thr = 200 if sum(r['growth'] >= 200 for r in fresh) >= 5 else 100
    pick = [r for r in fresh if r['growth'] >= thr][:7]
    if len(pick) < (1 if force else 3):
        log.info('profits: only %d new companies - waiting for more results', len(pick)); return None
    part = ps['part'] + 1
    day = today_ist()
    names = _names()
    for r in pick:
        r['name'] = _clean(names.get(r['symbol'], r['symbol']))
    py_q = pick[0]['py_quarter']
    head = f'Companies with more than *{thr}%* profit growth in *{quarter}*'
    images = [cards.cover({'category': 'Results Season', 'day': day, 'headline': head, 'theme': 'market_up',
                           'seed': f'{quarter}{part}', 'tone': 'up',
                           'stats': [('Companies', str(len(pick)), 0), ('Highest', f'{pick[0]["growth"]:+,.1f}%', 1),
                                     ('Series', f'Part {part}', 0)],
                           'inside': ['Quick list'] + [r['symbol'] for r in pick[:5]]})]
    images.append(ic.list_slide({'category': 'Results Season', 'date_text': f'{quarter} vs {py_q}',
                                 'headline': f'Net profit growth, *{quarter}* vs *{py_q}*', 'theme': 'market_up',
                                 'seed': part, 'tone': 'up',
                                 'rows': [(r['name'], f'{r["growth"]:+,.1f}%', 1) for r in pick]}))
    allowed = [thr, part, len(pick), 1, 2, 3, 4, 5, 6, 7]
    lines = []
    for i, r in enumerate(pick, 1):
        rows = [('Net profit', ic.cr(r['profit_py']), ic.cr(r['profit']))]
        allowed += [r['growth'], r['profit'], r['profit_py']]
        line = (f'{i}. {r["name"]} ({r["symbol"]}): net profit up {r["growth"]:,.1f}% from ₹{fmt_inr(r["profit_py"])} crore '
                f'to ₹{fmt_inr(r["profit"])} crore')
        if 'revenue' in r:
            rows.append(('Revenue', ic.cr(r['revenue_py']), ic.cr(r['revenue'])))
            allowed += [r['revenue'], r['revenue_py']]
            line += f'; revenue ₹{fmt_inr(r["revenue_py"])} crore to ₹{fmt_inr(r["revenue"])} crore'
        lines.append(line + (f' ({r["basis"].lower()})' if r['basis'] else '') + '.')
        allowed += _name_numbers(r['name'])
        images.append(ic.growth_slide({'n': i, 'total': len(pick), 'name': r['name'], 'symbol': r['symbol'],
                                       'growth': r['growth'], 'rows': rows, 'basis': r['basis'],
                                       'period_parts': [r['py_quarter'], ic.ARROW, r['quarter']],
                                       'price': r.get('last'), 'pct': r.get('pct', 0),
                                       'date_text': fmt_date(day, 'dow'), 'category': f'Results • Part {part}',
                                       'seed': r['symbol']}))
        allowed += [r.get('last') or 0, abs(r.get('pct') or 0)]
    images.append(ic.follow_slide({'seed': part}))
    paras = [f'Part {part}: companies in the Nifty 500 whose net profit for {quarter} grew more than {thr}% '
             f'over {py_q}, with profit of at least ₹10 crore in both quarters.', '\n'.join(lines),
             'Figures in ₹ crore as reported to the exchange. Growth from a small base can look large; '
             'one quarter does not make a trend. Save this series to track the results season.']
    allowed += [10, 500]
    caption = assemble(f'Companies with more than {thr}% profit growth in {quarter} (Part {part})', paras, '',
                       tags('#Q2Results' if quarter.startswith('Q2') else '#QuarterlyResults', '#EarningsSeason',
                            '#StockMarketIndia', '#ProfitGrowth', '#ShareMarket'))
    d = finish('insight', f'profits {quarter} part {part}', images[:10], caption, report, allowed)
    if d:
        ps['posted'] += [r['symbol'] for r in pick]
        ps['part'] = part
        _done('profits', st)
    return d


# ---------------------------------------------------------------- 2. assets last month

def assets(force=False, st=None):
    st = st or _state()
    y, m = src.last_complete_month()
    key = f'{y}-{m:02d}'
    if st.get('assets_month') == key and not force:
        return None
    report = Report()
    items, rep = src.month_assets(y, m)
    report.extend(rep)
    if len(items) < 6:
        report.fail(f'only {len(items)} assets confirmed - need at least 6')
        finish('insight', f'assets {key}', [], '', report); return None
    mname = date(y, m, 1).strftime('%B %Y')
    best, worst = items[0], items[-1]
    head = f'How major assets performed in *{mname}*'
    day = today_ist()
    images = [cards.cover({'category': 'Monthly Scorecard', 'day': day, 'headline': head, 'theme': 'gold', 'seed': key,
                           'stats': [('Best', f'{best["label"][:12]} {best["pct"]:+.1f}%', best['pct']),
                                     ('Worst', f'{worst["label"][:12]} {worst["pct"]:+.1f}%', worst['pct'])],
                           'inside': ['Bar chart', 'Start and end values']}),
              ic.vbars({'category': 'Monthly Scorecard', 'date_text': mname, 'headline': head, 'items': items,
                        'theme': 'gold', 'seed': key, 'swipe': True,
                        'note': f'Change from the last close of the previous month to the last close of {mname}.'}),
              ic.score_table({'category': 'Monthly Scorecard', 'date_text': mname, 'name_col': 'ASSET',
                              'headline': f'{mname}: *month change*', 'cols': ['CHANGE'], 'theme': 'gold', 'seed': key + 'b',
                              'rows': [{'name': f'{i["label"]}  ({i["fmt"].format(i["start"])} to {i["fmt"].format(i["end"])})',
                                        'vals': [i['pct']]} for i in items]}),
              ic.follow_slide({'seed': key})]
    allowed = [y, 500, 50]
    lines = []
    for i in items:
        lines.append(f'{i["label"]}: {i["pct"]:+.2f}% ({i["fmt"].format(i["start"])} to {i["fmt"].format(i["end"])})')
        allowed += [i['pct'], i['start'], i['end'], round(i['start']), round(i['end'])]
    paras = [f'Month-on-month change for {mname}, from the last close of the previous month to the last close of the month.',
             '\n'.join(lines),
             'Gold, silver and crude are international prices in US dollars; US Dollar / Rupee is rupees per dollar '
             '(a rise means a weaker rupee).']
    caption = assemble(f'How major assets performed in {mname}', paras, '',
                       tags('#MonthlyReview', '#Gold', '#Nifty50', '#StockMarketIndia', '#ShareMarket'))
    d = finish('insight', f'assets {key}', images, caption, report, allowed)
    if d:
        st['assets_month'] = key
        _done('assets', st)
    return d


# ---------------------------------------------------------------- 3. most valuable companies

def mcap(force=False, st=None):
    st = st or _state()
    report = Report()
    rows, rep = src.mcap_leaders(10)
    report.extend(rep)
    if len(rows) < 8:
        report.fail(f'only {len(rows)} companies confirmed - need at least 8')
        finish('insight', 'mcap', [], '', report); return None
    names = _names()
    day = today_ist()
    total = sum(r['mcap_cr'] for r in rows)
    lk = lambda v: v / 1e5          # crore -> lakh crore
    for r in rows:
        r['nm'] = _clean(names.get(r['symbol'], r['name']))
    head = f"India's *10 most valuable* listed companies"
    gainers = [r for r in rows if r.get('week_cr') is not None]
    top_add = max(gainers, key=lambda r: r['week_cr']) if gainers else None
    stats = [('Combined', f'₹{lk(total):,.2f} L Cr', 0), ('No. 1', rows[0]['symbol'][:10], 0)]
    if top_add:
        stats.append(('Most added', f'{top_add["symbol"][:9]}', 1 if top_add['week_cr'] > 0 else -1))
    images = [cards.cover({'category': 'Market Cap', 'day': day, 'headline': head, 'theme': 'bank', 'seed': str(day),
                           'stats': stats, 'inside': ['Top 10 ranking', 'Change this week']}),
              ic.hbars({'category': 'Market Cap', 'date_text': fmt_date(day, 'dow'), 'headline': head,
                        'sub': 'Market value in ₹ lakh crore  •  change over the last 5 sessions', 'theme': 'bank',
                        'seed': str(day) + 'b', 'swipe': True,
                        'rows': [{'name': r['nm'], 'value': r['mcap_cr'], 'value_text': f'₹{lk(r["mcap_cr"]):,.2f} L Cr',
                                  'side_text': f'{r["week_pct"]:+.2f}%' if r.get('week_pct') is not None else '',
                                  'side_sign': r.get('week_pct') or 0} for r in rows],
                        'note': 'Market value = shares issued x NSE price. 1 lakh crore = 1,00,000 crore.'}),
              ic.follow_slide({'seed': str(day)})]
    allowed = [10, 5, 1, 100000, lk(total)]
    lines = []
    for i, r in enumerate(rows, 1):
        allowed += [i, lk(r['mcap_cr']), r.get('week_pct') or 0, r['price']] + _name_numbers(r['nm'])
        lines.append(f'{i}. {r["nm"]}: ₹{lk(r["mcap_cr"]):,.2f} lakh crore'
                     + (f' ({r["week_pct"]:+.2f}% in 5 sessions)' if r.get('week_pct') is not None else ''))
    paras = [f'The 10 largest companies listed on NSE by market value, as of the close on {fmt_date(day)}.',
             '\n'.join(lines), f'Together they are worth ₹{lk(total):,.2f} lakh crore.']
    allowed += [day.day, day.year]
    caption = assemble(f"India's 10 most valuable listed companies", paras, '',
                       tags('#MarketCap', '#Nifty50', '#StockMarketIndia', '#BlueChip', '#ShareMarket'))
    d = finish('insight', f'mcap {day}', images, caption, report, allowed)
    if d:
        _done('mcap', st)
    return d


# ---------------------------------------------------------------- 4. one year in the Nifty 50

def wealth(force=False, st=None):
    st = st or _state()
    report = Report()
    rows, ago, rep = src.one_year_returns('NIFTY 50')
    report.extend(rep)
    if len(rows) < 40:
        report.fail(f'only {len(rows)} stocks confirmed - need at least 40')
        finish('insight', 'wealth', [], '', report); return None
    names = _names()
    for r in rows:
        r['nm'] = _clean(names.get(r['symbol'], r['symbol']))
        r['lakh'] = round(100000 * (1 + r['pct'] / 100))
    day = today_ist()
    best, worst = rows[:5], rows[-5:][::-1]
    up = sum(r['pct'] > 0 for r in rows)
    head = f'₹1 lakh in each *Nifty 50* stock a year ago: what it is worth now'
    mk = lambda lst: [{'name': r['nm'], 'value': r['lakh'], 'value_text': '₹' + fmt_inr(r['lakh'], 0),
                       'side_text': f'{r["pct"]:+.1f}%', 'side_sign': r['pct']} for r in lst]
    images = [cards.cover({'category': 'One Year', 'day': day, 'headline': head, 'theme': 'market_up', 'seed': str(day),
                           'tone': 'up', 'stats': [('Best', f'{best[0]["symbol"][:9]} {best[0]["pct"]:+.0f}%', 1),
                                                   ('Worst', f'{worst[0]["symbol"][:9]} {worst[0]["pct"]:+.0f}%', -1),
                                                   ('In the green', f'{up} of {len(rows)}', 0)],
                           'inside': ['Top 5', 'Bottom 5']}),
              ic.hbars({'category': 'One Year', 'date_text': f'Since {fmt_date(ago)}', 'headline': '*Top 5*: ₹1 lakh became',
                        'rows': mk(best), 'colour': 'up', 'theme': 'market_up', 'tone': 'up', 'seed': 'w1', 'swipe': True,
                        'note': 'Price change only (dividends not included). Split-adjusted.'}),
              ic.hbars({'category': 'One Year', 'date_text': f'Since {fmt_date(ago)}', 'headline': '*Bottom 5*: ₹1 lakh became',
                        'rows': mk(worst), 'colour': 'down', 'theme': 'market_down', 'tone': 'down', 'seed': 'w2',
                        'swipe': True, 'note': 'Price change only (dividends not included). Split-adjusted.'}),
              ic.follow_slide({'seed': str(day)})]
    allowed = [1, 5, 50, 100000, up, len(rows), ago.day, ago.year, day.day, day.year]
    fmt = lambda r: f'{r["nm"]} ₹{fmt_inr(r["lakh"], 0)} ({r["pct"]:+.1f}%)'
    for r in best + worst:
        allowed += [r['lakh'], r['pct']] + _name_numbers(r['nm'])
    paras = [f'If ₹1 lakh had been put in each Nifty 50 stock on {fmt_date(ago)}, here is what it would be worth '
             f'at the close on {fmt_date(day)} (price change only). {up} of {len(rows)} stocks are higher than a year ago.',
             'Top 5:\n' + '\n'.join(fmt(r) for r in best), 'Bottom 5:\n' + '\n'.join(fmt(r) for r in worst),
             'Past returns are history, not a guide to the future.']
    caption = assemble('₹1 lakh in each Nifty 50 stock a year ago: what it is worth now', paras, '',
                       tags('#Nifty50', '#WealthCreation', '#StockMarketIndia', '#LongTermInvesting', '#ShareMarket'))
    d = finish('insight', f'wealth {day}', images, caption, report, allowed)
    if d:
        _done('wealth', st)
    return d


# ---------------------------------------------------------------- 5. sector scorecard

def sectors(force=False, st=None):
    st = st or _state()
    report = Report()
    rows, rep = src.sector_scorecard()
    report.extend(rep)
    if len(rows) < 8:
        report.fail(f'only {len(rows)} indices - need at least 8')
        finish('insight', 'sectors', [], '', report); return None
    day = today_ist()
    nifty = next((r for r in rows if r['name'] == 'NIFTY 50'), None)
    secs = sorted([r for r in rows if r['name'] != 'NIFTY 50'], key=lambda r: r['m1'], reverse=True)
    lab = lambda n: market_jobs_label(n)
    head = 'Sector scorecard: *1 week, 1 month, 1 year*'
    short = lambda n: (lambda t: t if len(t) <= 11 else t.split()[0])(lab(n).replace('Nifty ', ''))
    table_rows = [{'name': lab(r['name']), 'vals': [r['w1'], r['m1'], r['y1']]} for r in secs]
    if nifty:
        table_rows.append({'name': 'Nifty 50 (benchmark)', 'vals': [nifty['w1'], nifty['m1'], nifty['y1']], 'highlight': True})
    images = [cards.cover({'category': 'Sector Scorecard', 'day': day, 'headline': head, 'theme': 'market_up',
                           'seed': str(day), 'stats': [('1M best', f'{short(secs[0]["name"])} {secs[0]["m1"]:+.1f}%', 1),
                                                       ('1M worst', f'{short(secs[-1]["name"])} {secs[-1]["m1"]:+.1f}%', -1)],
                           'inside': ['16 sectors', 'vs Nifty 50']}),
              ic.score_table({'category': 'Sector Scorecard', 'date_text': fmt_date(day, 'dow'), 'headline': 'Sector *scorecard*',
                              'cols': ['1W', '1M', '1Y'], 'rows': table_rows[:17], 'theme': 'market_up', 'seed': 's1',
                              'swipe': True, 'note': 'Sorted by 1-month change. Index price change.'}),
              ic.follow_slide({'seed': str(day)})]
    allowed = [1, 16, 50, day.day, day.year]
    lines = []
    for r in secs:
        allowed += [r['m1'], r['y1']] + ([r['w1']] if r['w1'] is not None else [])
        lines.append(f'{lab(r["name"])}: {r["m1"]:+.2f}% in 1 month, {r["y1"]:+.2f}% in 1 year')
    if nifty:
        allowed += [nifty['m1'], nifty['y1']]
        lines.append(f'Nifty 50: {nifty["m1"]:+.2f}% in 1 month, {nifty["y1"]:+.2f}% in 1 year')
    paras = [f'How NSE sector indices have moved, as of {fmt_date(day)}, sorted by 1-month change.', '\n'.join(lines)]
    caption = assemble('Sector scorecard: 1 week, 1 month, 1 year', paras, '',
                       tags('#SectorRotation', '#Nifty50', '#StockMarketIndia', '#NiftyIT', '#ShareMarket'))
    d = finish('insight', f'sectors {day}', images, caption, report, allowed)
    if d:
        _done('sectors', st)
    return d


def market_jobs_label(name):
    from .market_jobs import sector_label
    n = name.replace(' INDEX', '')
    return sector_label(n) if n.startswith('NIFTY') else n.title()


RUNNERS = {'profits': profits, 'assets': assets, 'mcap': mcap, 'wealth': wealth, 'sectors': sectors}


# ---------------------------------------------------------------- scheduling and on-demand

def _order(st):
    """Rotation: profits in results season, monthly assets in the first week, then the longest-waiting one."""
    order = ['profits']
    if today_ist().day <= 7:
        order.append('assets')
    rest = sorted(['mcap', 'sectors', 'wealth'], key=lambda t: st['last'].get(t) or '')
    return order + rest


def insights(force=False):
    """Scheduled (daily 6:40 PM): creates one insight if the last one is EVERY_DAYS or more days old."""
    st = _state()
    if _days_since(st.get('last_post')) < EVERY_DAYS and not force:
        log.info('insights: last one %s - not due', st.get('last_post')); return None
    for tag in _order(st):
        if _days_since(st['last'].get(tag)) < MIN_GAP[tag]:
            continue
        try:
            d = RUNNERS[tag](force=False, st=st)
        except Exception as e:                   # noqa: BLE001 - one failing idea should not stop the rotation
            log.exception('insight %s failed', tag)
            telegram.send_text(f'⚠️ Insight {tag} failed: {str(e)[:300]} - trying the next one')
            continue
        if d:
            return d
    log.info('insights: nothing ready today')
    return None


def run_tag(arg):
    """Telegram /innovative [tag|list]."""
    arg = (arg or '').strip().lower()
    if arg in ('list', 'help', '?'):
        telegram.send_text('<b>Insight tags</b>\n' + '\n'.join(f'/innovative {t} - {d}' for t, d in TAGS.items())
                           + '\n\n/innovative alone runs the next one in the rotation.')
        return None
    if not arg:
        st = _state()
        for tag in _order(st):
            d = RUNNERS[tag](force=True, st=st)
            if d:
                return d
        telegram.send_text('No insight could be built right now - see the messages above.')
        return None
    if arg not in RUNNERS:
        telegram.send_text(f'Unknown tag "{arg}". Try /innovative list')
        return None
    d = RUNNERS[arg](force=True)
    if d is None:
        telegram.send_text(f'Insight "{arg}": nothing new to post right now.')
    return d
