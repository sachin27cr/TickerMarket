"""News posts: discover -> cluster -> AI writes from sources -> code checks every fact -> 2nd AI checks."""
import json
import re

from .. import config, store
from ..render import cards
from ..render.art import as_post
from ..sources import market
from ..sources import news as news_src
from ..util import fmt_date, log, now_ist, today_ist
from ..verify import checks
from ..verify.checks import Report
from ..writer import llm, prompts
from ..writer.captions import assemble
from .common import finish

THEMES = {'banking': 'bank', 'energy': 'solar', 'ipo': 'ipo', 'oil': 'oil', 'gold': 'gold', 'it': 'tech'}
CATEGORIES = {'Market News', 'Earnings', 'IPO Watch', 'Economy', 'Regulation', 'Global Markets', 'Corporate Action'}


def _txt(s):
    """Plain text the card fonts can draw: no-break hyphens, dashes and odd spaces become normal ones."""
    s = str(s or '')
    s = re.sub('[\u2010\u2011\u2012\u2212]', '-', s)
    s = re.sub('[\u2013\u2014\u2015]', ' - ', s)
    s = re.sub('[\u00a0\u2007\u202f\u2009\u200a]', ' ', s)
    s = re.sub(r'\bRs\.?\s?(?=\d)', '₹', s)               # one rupee style on cards and captions
    s = s.replace('\u2018', "'").replace('\u2019', "'").replace('\u201c', '"').replace('\u201d', '"')
    return re.sub(r'[ \t]+', ' ', s).strip()


# ---------------------------------------------------------------- variety: no repeats, no near-duplicates
RECENT = 'news_recent.json'
RECENT_HOURS = 48
BUCKETS = [   # (bucket, pattern) - at most one story per bucket per day, so the feed stays varied
    ('index_move', r'\b(sensex|nifty|markets?|indices|benchmark|dalal street)\b.*\b(rise|rises|rose|gain|gains|jump|jumps|'
                   r'fall|falls|fell|drop|drops|slip|slips|surge|surges|rally|rallies|crash|tank|tanks|high|highs|low|'
                   r'lows|close|closes|ends|opens|snap|extend|climb|climbs|soar|soars|record)\b'),
    ('rupee_forex', r'\b(rupee|forex|dollar index)\b'),
    ('gold_metals', r'\b(gold|silver|bullion)\b'),
    ('crude_oil', r'\b(crude|brent|opec|oil prices?)\b'),
    ('fii_flows', r'\b(fii|fpi|foreign (portfolio|institutional) investors?|foreign inflows?)\b'),
    ('rbi_rates', r'\b(rbi|repo rate|monetary policy|inflation|cpi|gdp)\b'),
    ('global', r'\b(wall street|nasdaq|dow|s&p 500|fed|nikkei|hang seng)\b'),
]


def _bucket(title):
    t = title.lower()
    for name, pat in BUCKETS:
        if re.search(pat, t):
            return name
    return None


def _recent():
    from datetime import datetime, timedelta
    keep = [r for r in (store.read_json(RECENT, []) or [])
            if now_ist() - datetime.fromisoformat(r['when']) < timedelta(hours=RECENT_HOURS)]
    return keep


def _similar(a, b):
    a, b = set(a), set(b)
    return len(a & b) / max(1, min(len(a), len(b)))


def _repeat_of(c, recent):
    """Why this story would repeat something already drafted in the last 48 hours (or this run), else None."""
    toks = set(news_src.tokens(' '.join(i['title'] for i in c['items'][:3])))
    lead = set(news_src.tokens(c['lead']['title']))
    bucket = _bucket(c['lead']['title'])
    today = str(today_ist())
    for r in recent:
        if _similar(lead, r['lead']) >= 0.5 or _similar(toks, r['tokens']) >= 0.45:
            return f'same story as an earlier post: "{r["title"][:60]}"'
        if bucket and r.get('bucket') == bucket and r['when'][:10] == today:
            return f'already one {bucket.replace("_", " ")} story today: "{r["title"][:60]}"'
    return None


def _remember(c, recent):
    recent.append({'when': now_ist().isoformat(), 'title': c['lead']['title'], 'bucket': _bucket(c['lead']['title']),
                   'lead': sorted(news_src.tokens(c['lead']['title'])),
                   'tokens': sorted(news_src.tokens(' '.join(i['title'] for i in c['items'][:3])))})
    store.write_json(RECENT, recent[-200:])


def build_from_cluster(c):
    """Returns (images, caption, report, title) - report may contain failures."""
    report = Report()
    checks.check_sources(c, report)
    checks.check_freshness([i['published'] for i in c['items']], report, config.NEWS_MAX_AGE_HOURS)
    if not report.passed:
        return None, None, report, c['lead']['title']
    out, writer = llm.write(prompts.news_prompt(c, fmt_date(today_ist())))
    title = c['lead']['title']
    if not out.get('relevant', False):
        report.fail('writer marked the story as not relevant for the page')
        return None, None, report, title
    headline = _txt(out.get('headline', ''))
    points = [_txt(p) for p in out.get('points', [])][:3]
    body = out.get('body') or []
    body = [_txt(body)] if isinstance(body, str) else [_txt(b) for b in body][:2]
    hashtags = [h if h.startswith('#') else '#' + h for h in out.get('hashtags', [])][:5]
    category = out.get('category') if out.get('category') in CATEGORIES else 'Market News'
    if not (headline and len(points) >= 2 and body):
        report.fail('writer returned an incomplete draft')
        return None, None, report, title

    subject = _txt(str(out.get('subject') or '')).strip()
    plain_head = headline.replace('*', '').lower()
    if subject and subject.lower() not in plain_head and subject.split()[0].lower() not in plain_head:
        if len(headline.split()) + len(subject.split()) <= 14:       # say whose numbers these are
            headline = f'*{subject}*: ' + headline
            report.ok(f'headline did not name {subject} - added')
        else:
            report.fail(f'headline does not say who the story is about ({subject})')
            return None, None, report, title
    label = re.sub(r'[^A-Za-z0-9 &]', '', str(out.get('label') or ''))[:24].strip()
    companies = [str(x) for x in (out.get('companies') or [])][:3]
    src_text = ' '.join(f'{i["title"]} {i["summary"]}' for i in c['items'])
    draft_text = '\n'.join([headline.replace('*', '')] + points + body)
    missing = [x for x in companies if x.lower() not in src_text.lower()]
    if missing:
        report.warn('companies not named in sources, no price box: ' + ', '.join(missing))
        companies = [x for x in companies if x not in missing]
    allowed = checks.source_numbers([src_text])
    for i in c['items']:
        allowed += [i['published'].day, i['published'].year]
    allowed += [today_ist().day, today_ist().year]
    for yr in range(2020, 2036):                       # 'CY27', 'FY27', '2027' in a source all allow 2027
        if re.search(r'(?<!\d)(?:20)?' + str(yr)[2:] + r'(?!\d)', src_text) and re.search(r'(?i)(fy|cy|20|\')' + str(yr)[2:] + r'(?!\d)', src_text):
            allowed.append(yr)
    checks.check_numbers(draft_text + '\n' + label, allowed, report, 'headline/banner/points/body')
    odd = _odd_index_moves(draft_text + '\n' + label)
    if odd:
        report.fail('index move looks wrong (no period given; a day/week move this big is very unusual): ' + '; '.join(odd))
    checks.check_names(draft_text, src_text, report)
    checks.check_months(draft_text, src_text, report)
    checks.check_fiscal(draft_text, src_text, report)
    if label:
        lab = checks.Report(); checks.check_banned(label, lab)
        if not lab.passed:
            report.fail(f'banner text not allowed: {label}')
    if not report.passed:
        return None, None, report, title

    # second opinion from the other model
    try:
        verdict, checker = llm.check(prompts.check_prompt(draft_text, c), writer)
        ok = verdict.get('all_supported') and not verdict.get('misleading') and not verdict.get('advice_or_prediction')
        issues = [str(x) for x in (verdict.get('issues') or []) if str(x).strip()]
        date_only = issues and all(re.search(r'(?i)\bdate\b|today|published|november|december|january|2026|2027', x)
                                   and not re.search(r'(?i)number|figure|crore|percent|%|price', x) for x in issues)
        if ok:
            report.ok(f'second opinion ({checker}): every fact supported, not misleading, no advice')
        elif date_only and not verdict.get('advice_or_prediction') and not verdict.get('misleading'):
            report.warn(f'second opinion ({checker}) only queried the date: ' + '; '.join(issues))
        else:
            report.fail(f'second opinion ({checker}): ' + '; '.join(verdict.get('issues') or ['rejected']))
    except llm.LLMError as e:
        msg = f'second opinion unavailable ({str(e)[:80]}) - code checks passed, please read before approving'
        report.fail(msg) if config.REQUIRE_SECOND_OPINION else report.warn(msg)
    if not report.passed:
        return None, None, report, title

    outlets = ', '.join(c['outlets'][:3])
    newest = max(i['published'] for i in c['items'])
    quotes = market.company_quotes(companies, report)
    tone = out.get('tone') if out.get('tone') in ('up', 'down') else None
    if quotes:                                      # the prices decide the colour, not the AI
        net = sum(q['pct'] for q in quotes)
        tone = 'up' if net > 0 else 'down' if net < 0 else tone
    sector = str(out.get('sector') or 'other').lower()
    theme = THEMES.get(sector) or ('market_down' if tone == 'down' else 'market_up')
    from ..render import photo
    scene = re.sub(r'[0-9"]', '', str(out.get('image_scene') or ''))[:220].strip()
    names = [n.lower() for n in companies]
    if not scene or any(n and n in scene.lower() for n in names):      # never a company name in the picture
        scene = photo.SECTOR_SCENES.get(sector) or photo.SECTOR_SCENES['economy']
    photo.PHOTO_PROMPT = scene
    from ..render import own_bg
    own_bg.NEWS_SECTOR = 'results' if category == 'Earnings' and sector in ('other', 'economy') else sector
    card = {'category': category, 'date_text': fmt_date(newest.date(), 'dow'), 'theme': theme,
            'seed': c['key'], 'tone': tone, 'quotes': quotes, 'label': label,
            'headline': headline, 'points': points, 'source': ('NSE prices, ' if quotes else '') + outlets}
    global LAST_CARD
    LAST_CARD = json.loads(json.dumps({'card': card, 'news_sector': own_bg.NEWS_SECTOR, 'photo_prompt': scene},
                                      default=str))      # kept with the draft so a photo can be added later
    try:
        images = cards.news_hero(card)
    finally:
        photo.PHOTO_PROMPT = None
        own_bg.NEWS_SECTOR = None
    outlets = ('NSE prices, ' if quotes else '') + outlets
    caption = assemble(headline, body, outlets, hashtags)
    report.ok(f'written by {writer}; sources: ' + ' | '.join(i['link'] or i['outlet'] for i in c['items'][:4]))
    return images, caption, report, title


LAST_CARD = None


def render_with_photo(meta, photo_path, focus=0.38):
    """Re-draw a news card from the data kept with its draft, now with your photo at the top."""
    from ..render import own_bg, photo
    card = dict(meta['card'], photo=str(photo_path), photo_focus=focus)
    own_bg.NEWS_SECTOR, photo.PHOTO_PROMPT = meta.get('news_sector'), meta.get('photo_prompt')
    try:
        return cards.news_hero(card)
    finally:
        own_bg.NEWS_SECTOR, photo.PHOTO_PROMPT = None, None


INDEX_WORDS = re.compile(r'(?i)\b(sensex|nifty(?:\s*50|\s*bank)?|bank\s*nifty|midcap|smallcap|indices|index)\b')
PERIOD_WORDS = re.compile(r'(?i)\b(week|weeks|weekly|year|years|yearly|annual|ytd|month|months|monthly|quarter|decade|since|so far|'
                          r'fy\d*|cy\d*|20\d\d|november|october|december|january|february|march|april|may|june|'
                          r'july|august|september|from its|from the|record low|peak|high of|low of)\b')
BIG_MOVE = 4.0    # a one-day or one-week index move above this is rare enough to need a stated period


def _odd_index_moves(text):
    """'Sensex jumps 13%' with no period is almost always a misread (a yearly/monthly figure, or a stock's move)."""
    odd = []
    for sent in re.split(r'(?<=[.!?\n])\s+|\n', text):
        if PERIOD_WORDS.search(sent):
            continue
        for iw in INDEX_WORDS.finditer(sent):
            near = sent[iw.end():iw.end() + 40]                    # the % right after the index name
            m = re.search(r'(\d+(?:\.\d+)?)\s*(?:%|per\s*cent|percent)', near)
            if m and float(m.group(1)) > BIG_MOVE:
                odd.append(sent.strip()[:90])
                break
    return odd


@as_post('news')
def news(force=False, limit=None):
    from datetime import datetime, timedelta
    last = store.get_flag('last_news_run')
    if last and not force and now_ist() - datetime.fromisoformat(last) < timedelta(minutes=50):
        log.info('news ran at %s - skipping duplicate trigger', last)
        return 0
    store.set_flag('last_news_run', now_ist().isoformat())
    limit = limit or config.NEWS_PER_RUN
    items, status = news_src.fetch_all()
    log.info('feeds: %s', status)
    clusters = [c for c in news_src.cluster(items) if not store.seen('news', c['key'])]
    # company / sector stories first; broad 'Sensex-Nifty moved' stories last (the data posts already cover them)
    clusters.sort(key=lambda c: _bucket(c['lead']['title']) == 'index_move')
    made, tried, blocked, skipped = 0, 0, [], 0
    recent = _recent()
    for c in clusters:
        if made >= limit or tried >= limit * 5:
            break
        if not c['confirmed']:
            continue
        why = _repeat_of(c, recent)
        if why:                                         # variety: skip repeats and a 2nd story of the same kind
            log.info('skip %s: %s', c['lead']['title'][:60], why)
            store.mark_seen('news', c['key'], {'title': c['lead']['title']})
            skipped += 1
            continue
        tried += 1
        try:
            images, caption, report, title = build_from_cluster(c)
        except llm.LLMError as e:
            log.error('LLM unavailable: %s', e)
            try:
                from .. import telegram
                telegram.send_text(f'📰 News run skipped: the AI writers did not respond ({str(e)[:150]}). '
                                   f'Stories stay in the queue for the next run.')
            except Exception:                        # noqa: BLE001
                pass
            break
        store.mark_seen('news', c['key'], {'title': c['lead']['title']})
        if images is None:
            finish('news', title, [], '', report, notify=False)
            blocked.append((title, next((m for st, m in report if st == 'fail'), 'blocked')))
            continue
        if finish('news', title, images, caption, report, allowed_numbers=None, meta=LAST_CARD):
            made += 1
            _remember(c, recent)
    log.info('news run: %s drafts from %s candidates (%s repeats skipped)', made, tried, skipped)
    if blocked:
        try:
            from .. import telegram
            import html
            lines = '\n'.join(f'• {html.escape(t[:70])}\n   <i>{html.escape(r[:110])}</i>' for t, r in blocked[:6])
            telegram.send_text(f'📰 News run: {made} draft(s) sent, {len(blocked)} story(ies) blocked by checks:\n\n'
                               f'{lines}\n\nFull details: /flagged')
        except Exception as e:                       # noqa: BLE001
            log.warning('summary not sent: %s', e)
    return made
