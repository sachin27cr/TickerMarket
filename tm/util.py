import logging
import re
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
log = logging.getLogger('tm')
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


def now_ist():
    return datetime.now(IST)


def today_ist():
    return now_ist().date()


def fmt_inr(n, dec=2):
    """Indian digit grouping: 1,23,456.78 (sign kept)."""
    neg = n < 0
    s = f'{abs(n):.{dec}f}'
    whole, _, frac = s.partition('.')
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:]); head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ','.join(groups) + ',' + tail
    return ('-' if neg else '') + whole + ('.' + frac if frac else '')


def signed(n, dec=2):
    return ('+' if n >= 0 else '') + fmt_inr(n, dec)


def fmt_date(d, style='long'):
    """13 November 2026 / 13 Nov 2026 / Fri, 13 Nov 2026 (no leading zero)."""
    if style == 'long':
        return f'{d.day} {d.strftime("%B %Y")}'
    if style == 'short':
        return f'{d.day} {d.strftime("%b %Y")}'
    if style == 'dow':
        return f'{d.strftime("%a")}, {d.day} {d.strftime("%b %Y")}'
    if style == 'daymonth':
        return f'{d.day} {d.strftime("%b")}'
    raise ValueError(style)


def pct_change(close, chg):
    prev = close - chg
    return 0.0 if prev == 0 else chg / prev * 100


def parse_num(s):
    """'Rs.1,234.50' / '1,234' / '-12.3%' -> float, or None."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    m = re.search(r'-?\d[\d,]*\.?\d*', str(s))
    return float(m.group().replace(',', '')) if m else None


def slug(text, n=60):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:n]


SECRET_VARS = ('TELEGRAM_BOT_TOKEN', 'GEMINI_API_KEY', 'GROQ_API_KEY', 'META_PAGE_TOKEN', 'THREADS_TOKEN', 'CF_AI_TOKEN',
               'GITHUB_TOKEN', 'CF_ACCOUNT_ID', 'META_APP_SECRET')


def scrub(text):
    """Remove secret values (and anything shaped like a bot token or key=...) from text sent anywhere."""
    import os
    text = str(text)
    for v in SECRET_VARS:
        val = os.environ.get(v)
        if val and len(val) > 6:
            text = text.replace(val, '***')
    text = re.sub(r'bot\d{6,}:[A-Za-z0-9_-]{20,}', 'bot***', text)
    return re.sub(r'([?&](key|token|access_token|api_key)=)[^&\s\'"<]+', r'\1***', text)
