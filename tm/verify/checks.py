"""Deterministic checks. Every check appends (status, message) to a report.

status: 'ok' | 'warn' (shown to you, does not block) | 'fail' (draft is blocked).
"""
import re
from datetime import timedelta

from ..util import now_ist

NUM_RE = re.compile(r'(?<![A-Za-z\d.])-?\d[\d,]*(?:\.\d+)?(?!\d)(?!\.\d)')   # '0.52x', '18%' read whole
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
Million Trillion Per Cent Percent Year-On-Year YoY QoQ Mainboard SME CEO CFO COO CTO MD Chairman Chairperson
Chairwoman Director Directors Managing Executive Officer Chief President Minister Governor Deputy Secretary Head
Founder Promoter Promoters Shareholders Investors Analysts Brokerage Brokerages Exchange Exchanges H1 H2 FY Crores
Net Operating Revenue EBITDA PAT Margin Margins Order Orders Contract Deal Stake Share Bonus Split Record Festive
Sales Season Wedding Silver Prices Price Rally Fall Rise Low Lows Highs Year Month Day Days Weeks Months Quarterly
Annual First Second Third Fourth Half New Old Big Top Key Also As It's Its Here Why How What When Who Which'''.split())


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


TRANSITION = set("""Meanwhile However Also Further Furthermore Additionally Overall Earlier Separately Notably Besides
Moreover Still Yet Thus Hence Analysts Investors Shares Traders Experts Officials Sources Government Officials
Here There What Why How When While Despite Following According Under Over During Amid Against Among""".split())


def _norm(t):
    return re.sub(r'[^a-z0-9&]', '', t.lower())


# Well-known short forms and what they stand for: if the source uses the short form, the draft may spell it out.
GLOSSARY = {
    'QIB': 'Qualified Institutional Buyers', 'NII': 'Non-Institutional Investors', 'HNI': 'High Net-worth Individuals',
    'RII': 'Retail Individual Investors', 'FII': 'Foreign Institutional Investors', 'DII': 'Domestic Institutional Investors',
    'FPI': 'Foreign Portfolio Investors', 'RBI': 'Reserve Bank of India', 'SEBI': 'Securities and Exchange Board of India',
    'NSE': 'National Stock Exchange', 'BSE': 'Bombay Stock Exchange', 'MPC': 'Monetary Policy Committee',
    'GST': 'Goods and Services Tax', 'UPI': 'Unified Payments Interface', 'MDR': 'Merchant Discount Rate',
    'NPCI': 'National Payments Corporation of India', 'DRHP': 'Draft Red Herring Prospectus', 'RHP': 'Red Herring Prospectus',
    'OFS': 'Offer for Sale', 'IPO': 'Initial Public Offering', 'AGM': 'Annual General Meeting', 'EGM': 'Extraordinary General Meeting',
    'CPI': 'Consumer Price Index', 'WPI': 'Wholesale Price Index', 'GDP': 'Gross Domestic Product', 'PMI': 'Purchasing Managers Index',
    'NBFC': 'Non-Banking Financial Company', 'PSU': 'Public Sector Undertaking', 'MF': 'Mutual Fund', 'AMC': 'Asset Management Company',
    'SIP': 'Systematic Investment Plan', 'AMFI': 'Association of Mutual Funds in India', 'IRDAI': 'Insurance Regulatory and Development Authority',
    'CCI': 'Competition Commission of India', 'NCLT': 'National Company Law Tribunal', 'SAT': 'Securities Appellate Tribunal',
    'EV': 'Electric Vehicle', 'PLI': 'Production Linked Incentive', 'Fed': 'Federal Reserve', 'US': 'United States',
    'M&M': 'Mahindra & Mahindra', 'L&T': 'Larsen & Toubro', 'SBI': 'State Bank of India', 'LIC': 'Life Insurance Corporation',
    'HUL': 'Hindustan Unilever', 'ONGC': 'Oil and Natural Gas Corporation', 'IOC': 'Indian Oil Corporation',
    'BPCL': 'Bharat Petroleum', 'HPCL': 'Hindustan Petroleum', 'HAL': 'Hindustan Aeronautics', 'BEL': 'Bharat Electronics',
    'NTPC': 'National Thermal Power Corporation', 'TCS': 'Tata Consultancy Services', 'RIL': 'Reliance Industries',
}
GENERIC_FIRST = {'Bank', 'State', 'Indian', 'India', 'Power', 'Oil', 'National', 'Bharat', 'Hindustan', 'Union', 'Central',
                 'General', 'United', 'Tata', 'Adani', 'Bajaj', 'Aditya', 'The', 'New', 'Max', 'Life', 'Star'}


def _expansions(source_text):
    """Words the draft may use because the source names the same thing in a short form
    ('M&M' -> Mahindra, 'Hero Moto' -> Hero MotoCorp, 'QIBs' -> Qualified Institutional Buyers)."""
    from ..sources.names import COMMON as NAMES
    src = source_text
    extra = set()
    pairs = list(GLOSSARY.items()) + [(sym, name) for sym, name in NAMES.items()]
    for short, full in pairs:
        forms = {short}
        first = full.split()[0]
        if len(first) >= 4 and first not in GENERIC_FIRST:
            forms.add(first)
        if any(re.search(r'(?<![A-Za-z0-9])' + re.escape(f) + r's?(?![A-Za-z0-9])', src) for f in forms):
            extra |= {_norm(w) for w in full.split()}
    return extra


def check_names(text, source_text, report):
    """Every name-like word in the draft must appear in the sources (word by word, ignoring punctuation:
    'AT1' matches 'AT-1'). Ordinary capitalised words at the start of a sentence are not names."""
    plain = FY_DRAFT.sub(' ', re.sub(r'[*]', '', text))           # fiscal labels are checked separately
    src_norm = _norm(source_text)
    src_words = {_norm(w) for w in source_text.split()} | _expansions(source_text)
    stems = {w for w in src_words if len(w) >= 4}
    missing = []
    for m in re.finditer(r"\b([A-Z][A-Za-z0-9&'\-]*(?:[ \t]+[A-Z][A-Za-z0-9&'\-]*)*)", plain):
        ph = m.group(1)
        words = [w.strip("'.,-") for w in ph.split() if w.strip("'.,-") not in COMMON and w.strip("'.,-") not in TRANSITION]
        start = m.start() == 0 or plain[:m.start()].rstrip()[-1:] in '.:;!?\n'
        if start and len(ph.split()) == 1:
            continue                                        # a lone capitalised word starting a sentence
        bad = [w for w in words if len(_norm(w)) >= 2 and _norm(w) not in src_words and _norm(w) not in src_norm
               and not any(_norm(w).startswith(st) for st in stems)]      # 'Moto' in source covers 'MotoCorp'
        if bad:
            missing.append(ph)
    if missing:
        report.fail(f'names not found in sources: {", ".join(sorted(set(missing)))}')
    else:
        report.ok('all names appear in the sources')


MONTH_ABBR = {m: [m[:3]] + (['sept'] if m == 'september' else []) for m in MONTHS}


def check_months(text, source_text, report):
    """Capitalised month names in the draft must appear in the sources (full or short form).
    Lower-case words like 'may' are ordinary words, not months."""
    s = source_text.lower()
    this_month = MONTHS[now_ist().month - 1]
    found = {w.lower() for w in re.findall(r'\b(' + '|'.join(m.capitalize() for m in MONTHS) + r')\b', text)}
    bad = [m for m in found if m != this_month and m not in s
           and not any(re.search(r'\b' + a + r'\b', s) for a in MONTH_ABBR[m])]
    if bad:
        report.fail(f'month names not in sources: {", ".join(sorted(bad))}')


FY_DRAFT = re.compile(r'\b(?:H[12]\s*|Q[1-4]\s*)?FY\s?\'?(\d{2}|\d{4})(?:\s*-\s*(\d{2}|\d{4}))?\b', re.I)


def _fy_years(text):
    """FY27, FY2027, FY 2026-27, FY26-27 -> {27}"""
    out = set()
    for a, b in FY_DRAFT.findall(text):
        out.add(int((b or a)[-2:]))
    for a, b in re.findall(r'\b(20\d{2})\s*-\s*(\d{2}|20\d{2})\b', text):   # '2026-27' fiscal style
        out.add(int(b[-2:]))
    return out


def check_fiscal(text, source_text, report):
    years = {int((b or a)[-2:]) for a, b in FY_DRAFT.findall(text)}
    if not years:
        return
    missing = years - _fy_years(source_text)
    if missing:
        report.fail('fiscal years not in sources: ' + ', '.join(f'FY{y}' for y in sorted(missing)))
    else:
        report.ok('fiscal years match the sources')


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
    elif cluster.get('trusted'):
        report.ok('reported by a trusted outlet: ' + ', '.join(cluster['trusted']))
    else:
        report.fail('only one outlet reports this story: ' + cluster['outlets'][0])


def check_sum(parts, total, label, report, dec=2):
    s = round(sum(parts), dec)
    if abs(s - round(total, dec)) > 10 ** -dec:
        report.fail(f'{label}: rows add up to {s} but total shows {total}')
    else:
        report.ok(f'{label}: total {total:,.{dec}f} = sum of rows')
