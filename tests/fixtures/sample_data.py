"""Illustrative numbers for offline tests only. Never posted."""
from datetime import datetime, timedelta

from tm.util import IST

DATE = 'Fri, 13 Nov 2026'

INDICES = [
    {'name': 'NIFTY 50', 'close': 24612.40, 'chg': 118.35},
    {'name': 'SENSEX', 'close': 80915.62, 'chg': 412.08},
    {'name': 'NIFTY BANK', 'close': 52310.55, 'chg': -96.20},
    {'name': 'NIFTY MIDCAP 100', 'close': 56842.10, 'chg': 402.75},
    {'name': 'NIFTY SMALLCAP 100', 'close': 18215.35, 'chg': -35.60},
    {'name': 'INDIA VIX', 'close': 13.42, 'chg': -0.38},
]
SECTORS = [{'name': n, 'pct': p} for n, p in [('IT', 1.84), ('AUTO', 1.12), ('PHARMA', 0.65), ('FMCG', 0.21),
           ('METAL', -0.44), ('BANK', -0.18), ('REALTY', -1.27), ('ENERGY', 0.38), ('PSU BANK', -0.92),
           ('MEDIA', 0.05)]]
GAINERS = [{'symbol': s, 'last': l, 'pct': p} for s, l, p in [('INFY', 1912.35, 3.12), ('TCS', 4210.80, 2.45),
           ('M&M', 3180.10, 2.10), ('HCLTECH', 1890.55, 1.95), ('MARUTI', 12850.00, 1.62)]]
LOSERS = [{'symbol': s, 'last': l, 'pct': p} for s, l, p in [('HDFCBANK', 1712.30, -1.45), ('AXISBANK', 1155.20, -1.21),
          ('TATASTEEL', 152.35, -0.98), ('ONGC', 268.40, -0.75), ('ICICIBANK', 1290.65, -0.52)]]


def news_cluster():
    now = datetime.now(IST)
    items = [
        {'title': 'XYZ Bank Q2 net profit rises 18% to Rs 4,250 crore', 'outlet': 'Economic Times', 'tier': 2,
         'summary': 'XYZ Bank on 12 November reported an 18% rise in net profit to Rs 4,250 crore for the September quarter. Net interest income grew 14% to Rs 9,880 crore. Gross NPA improved to 1.9% from 2.2%.',
         'published': now - timedelta(hours=3), 'link': 'https://example.com/a'},
        {'title': 'XYZ Bank Q2 profit up 18% at ₹4,250 crore; NII rises 14%', 'outlet': 'Mint', 'tier': 2,
         'summary': 'Private lender XYZ Bank posted net profit of ₹4,250 crore in Q2 FY27, up 18% year-on-year, with net interest income at ₹9,880 crore.',
         'published': now - timedelta(hours=2), 'link': 'https://example.com/b'},
    ]
    return {'items': items, 'outlets': ['Economic Times', 'Mint'], 'tier1': False,
            'confirmed': True, 'score': 10, 'key': 'xyz bank q2 profit', 'lead': items[0]}


def _seg(names, base_pct):
    rows = []
    for i, (sym, last) in enumerate(names):
        pct = base_pct[i]
        prev = round(last / (1 + pct / 100), 2)
        rows.append({'symbol': sym, 'last': last, 'prev': prev, 'pct': round((last - prev) / prev * 100, 2),
                     'chg': round(last - prev, 2)})
    return rows


PCTS = [6.2, 4.8, 3.9, 3.1, 2.5, 1.2, 0.4, -0.3, -0.9, -1.4, -2.2, -2.9, -3.6, -4.4]
CAP_ROWS = {
    'NIFTY 100': _seg([('INFY', 1912.35), ('TCS', 4210.8), ('M&M', 3180.1), ('HCLTECH', 1890.55), ('MARUTI', 12850.0),
                       ('ITC', 412.3), ('LT', 3620.0), ('SBIN', 812.4), ('ONGC', 268.4), ('TATASTEEL', 152.35),
                       ('AXISBANK', 1155.2), ('HDFCBANK', 1712.3), ('ADANIENT', 2410.0), ('ZOMATO', 265.1)], PCTS),
    'NIFTY MIDCAP 150': _seg([('PERSISTENT', 5820.0), ('COFORGE', 7210.0), ('POLYCAB', 6890.0), ('DIXON', 15210.0),
                              ('VOLTAS', 1680.0), ('PAGEIND', 44100.0), ('MPHASIS', 2950.0), ('ASHOKLEY', 228.4),
                              ('FEDERALBNK', 198.3), ('IDFCFIRSTB', 68.2), ('NMDC', 72.4), ('SAIL', 121.3),
                              ('BHEL', 245.6), ('IRCTC', 790.0)], [x * 1.3 for x in PCTS]),
    'NIFTY SMALLCAP 250': _seg([('KPITTECH', 1520.0), ('BLS', 410.0), ('RADICO', 2310.0), ('CDSL', 1680.0),
                                ('ANGELONE', 2890.0), ('CAMS', 4410.0), ('KEI', 4120.0), ('IEX', 182.3),
                                ('RBLBANK', 172.5), ('NATCOPHARM', 1310.0), ('HFCL', 112.4), ('IRFC', 138.6),
                                ('SUZLON', 58.2), ('RVNL', 412.0)], [x * 1.6 for x in PCTS]),
    'NIFTY MICROCAP 250': _seg([('AAA1', 210.0), ('BBB2', 88.4), ('CCC3', 412.0), ('DDD4', 156.2), ('EEE5', 61.5),
                                ('FFF6', 310.0), ('GGG7', 45.6), ('HHH8', 720.0), ('III9', 98.3), ('JJJ10', 133.0),
                                ('KKK11', 260.0), ('LLL12', 74.1), ('MMM13', 39.8), ('NNN14', 515.0)], [x * 2 for x in PCTS]),
}


def weekly_fixture(week_monday):
    """Fake 60-week histories: first 3 stocks of each group make an all-time high this week, last 3 a
    52-week low; NSE 52-week levels set to match. The 4th stock's NSE level is wrong on purpose (must be dropped)."""
    import pandas as pd
    from datetime import timedelta
    hist, nse_rows = {}, {}
    weeks = [week_monday - timedelta(weeks=59 - i) for i in range(60)]
    for index, rows in CAP_ROWS.items():
        out = []
        for k, r in enumerate(rows):
            base = r['last']
            highs = [base * 1.05] * 59
            lows = [base * 0.80] * 59
            closes = [base] * 59
            if k < 4:                      # new all-time high this week
                h, l, c = base * 1.10, base * 0.98, base * 1.08
            elif k >= len(rows) - 3:       # new 52-week low this week
                h, l, c = base * 1.0, base * 0.70, base * 0.72
            else:
                h, l, c = base * 1.02, base * 0.97, base
            df = pd.DataFrame({'Open': closes + [base], 'High': highs + [h], 'Low': lows + [l], 'Close': closes + [c]},
                              index=pd.to_datetime(weeks))
            hist[r['symbol']] = df
            yh = max(highs[-51:] + [h]); yl = min(lows[-51:] + [l])
            if k == 3:
                yh *= 1.05                 # NSE disagrees -> must be dropped
            out.append({**r, 'year_high': yh, 'year_low': yl})
        nse_rows[index] = out
    return hist, nse_rows
