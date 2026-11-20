"""Instagram search / Explore optimisation applied to every caption (see SEO rules in README):
- line 1 is a readable, keyword-rich sentence that contains the post's TOPIC_KEYWORD;
- short fact lines, then a save/share call to action;
- exactly 3-5 hashtags: 1 broad + 2-3 niche + 1 branded, no spam tags;
- alt text for image posts that contains the keyword.
"""
import re

BRAND_TAG = '#TickerMarketIndia'
BROAD_TAG = '#StockMarketIndia'
SPAM = {'#viral', '#explore', '#explorepage', '#follow4follow', '#f4f', '#like4like', '#l4l', '#trending', '#fyp',
        '#instagood', '#reels', '#reelsinstagram', '#followforfollow'}

TOPIC = {
    'market_close': 'Stock market today',
    'cap_movers': 'Top gainers and losers today',
    'daily_overview': 'Stocks at all-time high today',
    'fii_dii': 'FII DII data today',
    'global_cues': 'Global market cues today',
    'day_ahead': 'Stock market today',
    'ipo': 'IPO news',
    'ipo_status': 'IPO subscription status',
    'weekly_ath': 'Stocks at all-time high this week',
    'weekly_lows': '52-week low stocks this week',
    'insights': 'Stock market insights',
    'results_spotlight': 'Quarterly results',
    'reel_morning': 'Stock market today',
    'reel_evening': 'Stock market today',
    'reel_weekly': 'Stock market this week',
    'reel_ath': 'Stocks at all-time high',
    'reel_lows': '52-week low stocks',
    'news': 'Stock market news',
    'custom_post': 'Stock market India',
    'reel_custom': 'Stock market India',
}
CTA = {'reel': 'Share this with a friend who trades, and follow for the daily market update.',
       'post': 'Save this for later and send it to a friend who trades.'}


def topic_keyword(kind, caption=''):
    return TOPIC.get(kind, 'Stock market India')


def _has(keyword, text):
    words = [w for w in re.findall(r'[a-z0-9]+', keyword.lower()) if w not in ('today', 'this', 'week', 'news')]
    t = text.lower()
    return all(w in t for w in words)


def hashtags(existing):
    """1 broad + up to 3 niche + 1 branded = max 5."""
    niche = []
    for t in existing:
        t = t.strip()
        if not t.startswith('#') or t.lower() in SPAM or t in (BROAD_TAG, BRAND_TAG) or t in niche:
            continue
        niche.append(t)
    for t in ('#Nifty50', '#ShareMarket'):              # always at least 3 tags
        if len(niche) >= 1:
            break
        niche.append(t)
    return [BROAD_TAG] + niche[:3] + [BRAND_TAG]


def optimise(kind, caption, keyword=None):
    """Caption -> SEO caption. Keeps every fact line exactly as written (numbers are checked after this)."""
    keyword = keyword or topic_keyword(kind, caption)
    parts = caption.split('\n\n')
    tags = parts[-1].split() if parts and parts[-1].startswith('#') else []
    body = parts[:-1] if tags else parts
    if not body:
        return caption
    first = re.sub(r'\s+', ' ', body[0]).strip()
    if first.isupper():                                   # readable sentence case, not all caps
        first = first.capitalize()
        first = re.sub(r'\b(nifty|sensex|nse|bse|fii|dii|ipo|rbi|sebi|it|us)\b',
                       lambda m: {'nifty': 'Nifty', 'sensex': 'Sensex'}.get(m.group(1), m.group(1).upper()), first)
    if not _has(keyword, first):
        first = f'{keyword} | {first}'
    body[0] = first
    from .captions import DISCLAIMER
    cta = CTA['reel' if kind.startswith('reel') else 'post']
    rest = [p for p in body[1:] if p.strip() and p.strip() not in (DISCLAIMER, CTA['reel'], CTA['post'])]
    out = [body[0]] + rest + [cta, DISCLAIMER, ' '.join(hashtags(tags))]
    return '\n\n'.join(out)


def alt_text(kind, caption, n_images=1, keyword=None):
    keyword = keyword or topic_keyword(kind, caption)
    first = caption.split('\n\n')[0]
    first = re.sub(r'^' + re.escape(keyword) + r'\s*[|:]\s*', '', first)
    what = 'carousel' if n_images > 1 else 'image'
    return f'{keyword}: Ticker Market India {what} - {first}'[:450]
