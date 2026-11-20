"""When posts go live. Followers are most active after 5:30 PM, so evening posts go out in fixed slots,
30 minutes apart. Data posts publish on their own at their slot; news and reels wait for your approval and
then take their slot (reels 7:15 PM) or the next free 30-minute gap (news).

Morning posts (global cues, day ahead, IPOs, morning reel) have no slot: they go out when ready.
"""
from datetime import datetime, time, timedelta

from .util import IST, now_ist

SPACING = timedelta(minutes=29)          # at least ~30 minutes between two posts (5-minute check cycle)

WEEKDAY = {                              # Mon-Fri
    'market_close': '17:30',             # day performance
    'ipo_status': '18:00',
    'daily_overview': '18:45',           # all-time highs / 52-week lows
    'reel_evening': '19:15',
    'cap_movers': '19:45',               # gainers & losers by market cap + FII/DII (one post)
    'fii_dii': '19:45',                  # only if it could not be added to the post above
    'results_spotlight': '20:15',
    'insights': '20:45',
}
SATURDAY = {
    'weekly_ath': '17:30',
    'weekly_lows': '18:00',
    'reel_ath': '18:30',
    'reel_weekly': '19:15',
    'reel_lows': '19:45',
    'insights': '20:45',
}
SUNDAY = {'insights': '20:45'}

# need your tap before they post; everything else posts on its own (you can still cancel)
APPROVAL = ('news', 'reel_', 'custom')


def needs_approval(kind):
    return kind == 'news' or kind.startswith(('reel_', 'custom'))


def slot(kind, day=None):
    """The IST datetime this kind should go live on `day` (today by default), or None (no slot)."""
    day = day or now_ist().date()
    table = WEEKDAY if day.weekday() < 5 else SATURDAY if day.weekday() == 5 else SUNDAY
    hhmm = table.get(kind)
    if not hhmm:
        return None
    h, m = map(int, hhmm.split(':'))
    return datetime.combine(day, time(h, m), tzinfo=IST)


def label(dt):
    return dt.strftime('%-I:%M %p')
