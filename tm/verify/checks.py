"""Deterministic checks. Every check appends (status, message) to a report.

status: 'ok' | 'warn' (shown to you, does not block) | 'fail' (draft is blocked).
"""
import re
from datetime import timedelta

from ..util import now_ist

NUM_RE = re.compile(r'(?<![A-Za-z\d])-?\d[\d,]*(?:\.\d+)?(?![A-Za-z\d])')
MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september',
          'october', 'november', 'december']

# Advice, predictions and rumour language. Hard block: the draft never reaches you.
BANNED = [
    r'\bbuy now\b', r'\bshould (you )?(buy|sell|invest)\b', r'\bstocks? to (buy|watch|sell)\b', r'\btarget price\b',
    r'\bprice target\b', r'\bstop[- ]?loss\b', r'\bmultibagger\b', r'\bsure[- ]?shot\b', r'\bguaranteed\b',
    r'\bwe recommend\b', r'\brecommend(s|ed)? (buying|selling)\b', r'\baccumulate\b', r'\bbook profits?\b',
    r'\bwill (rise|fall|rally|crash|surge|jump|double)\b', r'\bset to (rise|fall|rally|crash|surge|soar)\b',
    r'\bexpected to (rally|soar|crash|double)\b', r'\bhuge returns?\b', r'\bget rich\b', r'\bjackpot\b',
    r'\breportedly\b', r'\bsources said\b', r'\baccording to sources\b', r'\brumou?rs?\b', r'\bunconfirmed\b',
    r'\bgrey market premium\b', r'\bgmp\b', r'\btip(s)? of the day\b', r'\bpositive start likely\b',
]

# Words that may appear capitalised but are not names to verify
COMMON = set('''The A An And Or Of In On For With At By From As Is Are Was It Its This That These After Before
Over Under Into Than About Amid Says Said Will May Can Could Would New Today Week Day Year Shares Share Stock
Stocks Market Markets Index Indices India Indian Nifty Sensex Bank Banks NSE BSE SEBI RBI FII FIIs DII DIIs FPI
FPIs IPO IPOs Q1 Q2 Q3 Q4 FY GDP CPI GST Fed US USD INR Rs Crore Lakh Net Profit Revenue Income Quarter Results
Board Company Limited Ltd Group Government Ministry Finance Reserve Securities Exchange National Bombay Stock
Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April June July August September
October November December Source For Not Investment Advice Information Only Total Gross Wall Street Brent Crude
Gold Dollar Rupee Global Asian European Dow Jones Nasdaq Opens Closes Listing Allotment Price Band Lot Size Issue
Fresh Offer Sale Key Dates Interest Rate Repo Policy Monetary Committee Inflation Trade Tariff Tariffs Earnings
Dividend Buyback Record Date Ex Up Down Rises Falls Gains Jumps Slips Ends Closes Hits High Low Record Billion
Million Trillion Per Cent Percent Year-On-Year YoY QoQ Mainboard SME'''.split())


class Report(list):
    def ok(self, m): self.append(('ok', m))
    def warn(self, m): self.append(('warn', m))
    def fail(self, m): self.append(('fail', m))

    @property
    def passed(self):
        return not any(s == 'fail' for s, _ in self)

    def text(self):
        icon = {'ok': '✅', 'warn': '⚠️', 'fail': '❌'}
        return '\n'.join(f'{icon[s]} {m}' for s, m in self)


def numbers(text):
    out = []
    for m in NUM_RE.findall(text):
        try:
            out.append((m, float(m.replace(',', ''))))
        except ValueError:
            continue
    return out


def _matches(shown, value):
    """'24,612.40' matches 24612.4; '18%' with value 17.99 matches when rounded the same way."""
    s = shown.replace(',', '').lstrip('-')
    dec = len(s.split('.')[1]) if '.' in s else 0
    v = abs(value)
    return round(v, dec) == round(abs(float(s)), dec)


INDEX_NAME = re.compile(r'(?i)\b(nifty(?: midcap| smallcap| microcap| next| largemidcap)?|s&p|nikkei|midcap|smallcap|bse|ftse|dax)\s+(\d+)\b')


def check_numbers(text, allowed, report, label='caption'):
    """Every number in `text` must equal one of `allowed` (floats) at the precision shown.
    Numbers that are part of an index name (Nifty 50, S&P 500, Nikkei 225) are not data and are skipped."""
    text = INDEX_NAME.sub(r'\1', text)
    allowed = [abs(a) for a in allowed]
    bad = []
    for shown, val in numbers(text):
        if not any(_matches(shown, a) for a in allowed):
            bad.append(shown)
    if bad:
        report.fail(f'{label}: numbers not found in source data: {", ".join(sorted(set(bad)))}')
    else:
        report.ok(f'{label}: all {len(numbers(text))} numbers match source data')


def source_numbers(texts):
    vals = []
    for t in texts:
        vals += [v for _, v in numbers(t)]
        # "₹4,250 crore" and "Rs 4250 cr" and "4.25 thousand crore" are all just 4250 here
    return vals


def check_names(text, source_text, report):
    plain = re.sub(r'[*]', '', text)
    src = source_text.lower()
    phrases = re.findall(r"\b([A-Z][A-Za-z0-9&'.\-]*(?:\s+[A-Z][A-Za-z0-9&'.\-]*)*)", plain)
    missing = []
    for ph in phrases:
        words = [w for w in ph.split() if w.strip("'.") not in COMMON]
        if not words:
            continue
        cand = ' '.join(words).lower().strip(".'")
        if cand and cand not in src:
            missing.append(ph)
    if missing:
        report.fail(f'names not found in sources: {", ".join(sorted(set(missing)))}')
    else:
        report.ok('all names appear in the sources')


def check_months(text, source_text, report):
    t, s = text.lower(), source_text.lower()
    this_month = MONTHS[now_ist().month - 1]
    bad = [m for m in MONTHS if re.search(r'\b' + m + r'\b', t) and m not in s and m != this_month]
    if bad:
        report.fail(f'month names not in sources: {", ".join(bad)}')


def check_banned(text, report):
    hits = [p for p in BANNED if re.search(p, text, re.I)]
    if hits:
        report.fail('advice/prediction/rumour language: ' + ', '.join(h.strip('\\b') for h in hits))
    else:
        report.ok('no advice, prediction or rumour language')


def check_freshness(published_times, report, max_hours):
    newest = max(published_times)
    age = now_ist() - newest
    if age > timedelta(hours=max_hours):
        report.fail(f'story is {age.total_seconds() / 3600:.1f} h old (limit {max_hours} h)')
    else:
        report.ok(f'fresh: newest source {age.total_seconds() / 3600:.1f} h old')


def check_sources(cluster, report):
    if cluster['tier1']:
        report.ok('confirmed by an official source (' + ', '.join(cluster['outlets']) + ')')
    elif len(cluster['outlets']) >= 2:
        report.ok(f'confirmed by {len(cluster["outlets"])} outlets: ' + ', '.join(cluster['outlets']))
    else:
        report.fail('only one outlet reports this story: ' + cluster['outlets'][0])


def check_sum(parts, total, label, report, dec=2):
    s = round(sum(parts), dec)
    if abs(s - round(total, dec)) > 10 ** -dec:
        report.fail(f'{label}: rows add up to {s} but total shows {total}')
    else:
        report.ok(f'{label}: total {total:,.{dec}f} = sum of rows')
