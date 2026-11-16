"""News discovery from RSS + clustering of the same story across outlets."""
import html
import re
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from .. import config
from ..util import IST, log, now_ist

UA = {'User-Agent': 'Mozilla/5.0 (TickerMarketBot; +https://instagram.com/tickermarket.india)'}

STOP = set('''a an the and or of to in on for with at by from as is are was were be been it its this that
these those after before over under into than then about amid says said will may can could would new
today week day year india indian market markets stock stocks share shares news live update updates'''.split())

IMPORTANT = {'sensex': 3, 'nifty': 3, 'rbi': 3, 'sebi': 3, 'ipo': 3, 'fii': 3, 'fpi': 3, 'dii': 2, 'results': 2,
             'profit': 2, 'q1': 2, 'q2': 2, 'q3': 2, 'q4': 2, 'crore': 1, 'repo': 3, 'gdp': 2, 'inflation': 2,
             'cpi': 2, 'fed': 2, 'crude': 2, 'rupee': 2, 'budget': 3, 'tariff': 2, 'dividend': 2, 'buyback': 2,
             'merger': 2, 'acquisition': 2, 'listing': 2, 'gst': 2}
# not market news, or not suitable for this page
EXCLUDE = re.compile(r'\b(horoscope|astrology|cricket|bollywood|recipe|lottery|stocks? to (buy|watch)|'
                     r'multibagger|target price|buy or sell|top picks?|technical pick|trading idea)\b', re.I)


def clean(text):
    text = re.sub(r'<[^>]+>', ' ', html.unescape(text or ''))
    return re.sub(r'\s+', ' ', text).strip()


def fetch_feed(feed):
    r = requests.get(feed['url'], headers=UA, timeout=20)
    r.raise_for_status()
    parsed = feedparser.parse(r.content)
    items = []
    for e in parsed.entries:
        ts = e.get('published_parsed') or e.get('updated_parsed')
        if not ts:
            continue
        published = datetime(*ts[:6], tzinfo=timezone.utc).astimezone(IST)
        title = clean(e.get('title'))
        outlet = feed.get('outlet', feed['name'])
        src = e.get('source')
        if src and getattr(src, 'title', None):           # Google News: real outlet name
            outlet = src.title
            title = re.sub(r'\s+-\s+' + re.escape(src.title) + r'$', '', title)
        items.append({'title': title, 'summary': clean(e.get('summary') or e.get('description'))[:700],
                      'link': e.get('link'), 'outlet': outlet, 'tier': feed['tier'],
                      'published': published})
    return items


def fetch_all(max_age_hours=None):
    max_age = timedelta(hours=max_age_hours or config.NEWS_MAX_AGE_HOURS)
    cutoff = now_ist() - max_age
    items, status = [], []
    for f in config.FEEDS:
        try:
            got = fetch_feed(f)
            keep = re.compile(f['filter']) if f.get('filter') else None
            fresh = [i for i in got if i['published'] >= cutoff and not EXCLUDE.search(i['title'])
                     and (keep is None or keep.search(i['title'] + ' ' + i['summary']))]
            items += fresh
            status.append((f['name'], 'ok', len(fresh)))
        except Exception as e:                       # noqa: BLE001 - broken feed is skipped
            log.warning('feed %s failed: %s', f['name'], e)
            status.append((f['name'], f'failed: {e.__class__.__name__}', 0))
    return items, status


def tokens(text):
    words = re.findall(r'[a-z0-9&]+', text.lower())
    return {w for w in words if w not in STOP and len(w) > 2}


def numbers_in(text):
    return set(re.findall(r'\d[\d,]*\.?\d*', text.replace(',', '')))


def cluster(items, threshold=0.34):
    """Group items about the same event. Returns clusters sorted by score."""
    clusters = []
    for it in sorted(items, key=lambda i: i['published'], reverse=True):
        tk = tokens(it['title'])
        best, best_sim = None, 0
        for c in clusters:
            inter = len(tk & c['tokens'])
            sim = inter / max(1, len(tk | c['tokens']))
            # sharing a specific number (e.g. 4,250) plus a word is strong evidence
            if numbers_in(it['title']) & c['numbers'] and inter >= 2:
                sim += 0.2
            if sim > best_sim:
                best, best_sim = c, sim
        if best and best_sim >= threshold:
            best['items'].append(it)
            best['tokens'] |= tk
            best['numbers'] |= numbers_in(it['title'])
        else:
            clusters.append({'items': [it], 'tokens': set(tk), 'numbers': numbers_in(it['title'])})
    for c in clusters:
        outlets = {i['outlet'] for i in c['items']}
        c['outlets'] = sorted(outlets)
        c['tier1'] = any(i['tier'] == 1 for i in c['items'])
        c['confirmed'] = c['tier1'] or len(outlets) >= 2
        imp = sum(IMPORTANT.get(t, 0) for t in c['tokens'])
        age_h = (now_ist() - max(i['published'] for i in c['items'])).total_seconds() / 3600
        c['score'] = len(outlets) * 3 + imp + (4 if c['tier1'] else 0) - age_h * 0.3
        lead = max(c['items'], key=lambda i: (i['tier'] == 1, len(i['summary'])))
        c['key'] = ' '.join(sorted(list(tokens(lead['title'])))[:8])
        c['lead'] = lead
    return sorted(clusters, key=lambda c: c['score'], reverse=True)
