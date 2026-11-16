"""Renders every template with sample data into tests/out/ (run: python -m tests.test_render)."""
from pathlib import Path

from tm.render import cards
from tests.fixtures import sample_data as S

OUT = Path(__file__).parent / 'out'


def save(name, images):
    OUT.mkdir(exist_ok=True)
    for i, im in enumerate(images):
        assert im.size == (1080, 1350)
        im.save(OUT / f'{name}_{i + 1}.jpg', quality=92)


def test_all():
    save('market_close', cards.market_close({
        'sample': True, 'date_text': S.DATE, 'headline': 'Nifty ends *above 24,600*; Sensex gains *412 points*',
        'indices': S.INDICES[:3], 'source': 'NSE, BSE closing data',
        'drivers': ['Nifty IT rose 1.84%, the best of all sectors', 'Nifty Realty fell 1.27%',
                    '312 of Nifty 500 stocks advanced']}))
    save('daily_overview', cards.daily_overview({
        'sample': True, 'date_text': S.DATE, 'headline': 'Daily market overview: *13 November 2026*',
        'indices': S.INDICES, 'breadth': {'advances': 312, 'declines': 181, 'universe': 'Nifty 500'},
        'sectors': S.SECTORS, 'gainers': S.GAINERS, 'losers': S.LOSERS,
        'extras': [{'name': 'USD / INR', 'value': '84.62', 'pct': -0.12}, {'name': 'Brent Crude', 'value': '$92.04', 'pct': -0.78},
                   {'name': 'Gold', 'value': '$2,710.40', 'pct': 0.30}, {'name': 'India VIX', 'value': '13.42', 'pct': -2.75}],
        'source': 'NSE, BSE, Yahoo Finance'}))
    imgs, totals = cards.fii_dii({
        'sample': True, 'date_text': 'Nov 2026 so far', 'headline': 'FIIs net buyers in *November* so far',
        'rows': [{'date': '09 Nov', 'fii': 2140.55, 'dii': -880.20}, {'date': '10 Nov', 'fii': 3315.10, 'dii': -1220.75},
                 {'date': '11 Nov', 'holiday': True}, {'date': '12 Nov', 'fii': -640.30, 'dii': 1105.40},
                 {'date': '13 Nov', 'fii': 4870.25, 'dii': -2310.65}], 'source': 'NSE provisional data'})
    assert totals == {'fii_total': 9685.6, 'dii_total': -3306.2}
    save('fii_dii', imgs)
    save('ipo', cards.ipo({
        'sample': True, 'date_text': 'Opens 18 Nov 2026', 'headline': '*ABC Tech* IPO opens *Nov 18*',
        'company': 'ABC Technologies Ltd', 'segment': 'Mainboard IPO  |  NSE, BSE',
        'tiles': [('Price band', '₹412 - 434'), ('Lot size', '34 shares'), ('Issue size', '₹1,250 Cr'),
                  ('Min. investment', '₹14,756'), ('Opens', '18 Nov'), ('Closes', '20 Nov')],
        'timeline': [('Opens', 'Nov 18'), ('Closes', 'Nov 20'), ('Listing', 'Nov 25')], 'source': 'NSE'}))
    save('global_cues', cards.global_cues({
        'sample': True, 'date_text': 'Mon, 16 Nov 2026', 'headline': 'Wall Street gains; *crude slips below $93*',
        'rows': [{'name': 'Dow Jones', 'value': '44,210.35', 'pct': 0.42}, {'name': 'Nasdaq', 'value': '20,180.15', 'pct': 0.95},
                 {'name': 'Brent Crude', 'value': '$92.04', 'pct': -0.78}, {'name': 'Gold', 'value': '$2,710.40', 'pct': 0.30},
                 {'name': 'USD / INR', 'value': '84.62', 'pct': -0.12}],
        'notes': ['Nasdaq rose 0.95%, the biggest gain among US indices', 'Brent crude fell 0.78% to $92.04'],
        'source': 'Yahoo Finance'}))
    save('day_ahead', cards.day_ahead({
        'sample': True, 'date_text': 'Mon, 16 Nov 2026', 'headline': 'What is on for the market on *16 November*',
        'groups': [('Results today', ['XYZ Bank', 'ABC Technologies', 'PQR Motors']),
                   ('IPOs open', ['ABC Technologies (18-20 Nov)']), ('Ex-date today', ['LMN Ltd - Dividend Rs 5'])],
        'source': 'NSE event calendar'}))
    save('news', cards.news({
        'sample': True, 'category': 'Earnings', 'date_text': 'Thu, 12 Nov 2026',
        'headline': '*XYZ Bank* Q2 profit jumps *18%* to *₹4,250 crore*',
        'points': ['Net interest income up 14% to ₹9,880 crore', 'Gross NPA improves to 1.9% from 2.2%',
                   'Results reported on 12 November 2026'], 'source': 'Economic Times, Mint'}))


def test_cap_movers():
    from tm.sources import market, nse
    from datetime import datetime
    nse.index_constituents = lambda index='NIFTY 50': (S.CAP_ROWS[index], datetime.now())
    segs, report = market.cap_movers(5)
    assert len(segs) == 4 and all(r[0] == 'ok' for r in report), report
    save('cap_movers', cards.cap_movers({'sample': True, 'date_text': S.DATE,
         'headline': 'Top gainers and losers by *market cap*: *13 Nov*',
         'segments': [{'name': n, **segs[n]} for n, _ in market.CAP_SEGMENTS], 'source': 'NSE closing data'}))


def test_extremes():
    rows = [{'symbol': g['symbol'], 'level': g['last'] * 1.02, 'week_pct': g['pct'] + 1} for g in S.GAINERS * 2]
    groups = [{'name': n, 'index': i, 'rows': rows[:k], 'count': k} for (n, i), k in
              zip([('Large Cap', 'NIFTY 100'), ('Mid Cap', 'NIFTY MIDCAP 150'), ('Small Cap', 'NIFTY SMALLCAP 250'),
                   ('Micro Cap', 'NIFTY MICROCAP 250')], [10, 6, 3, 0])]
    save('weekly_ath', cards.extremes({'sample': True, 'kind': 'ath', 'date_text': 'Week of 9-13 Nov 2026',
                                       'headline': 'Stocks at *all-time highs* this week (9-13 Nov 2026)',
                                       'groups': groups, 'source': 'NSE, Yahoo Finance'}))


def test_news_hero():
    t = '16 Nov, 3:30 PM IST'
    save('news_hero_single', cards.news_hero({
        'sample': True, 'category': 'Earnings', 'date_text': 'Mon, 16 Nov 2026', 'theme': 'bank', 'seed': 3, 'tone': 'up',
        'quotes': [{'name': 'XYZ Bank Ltd', 'symbol': 'XYZBANK', 'price': 1712.30, 'chg': 74.85, 'pct': 4.57, 'time_text': t}],
        'label': 'Q2 result impact', 'headline': '*XYZ Bank* shares rise *4.57%* after Q2 profit jumps *18%*',
        'points': ['Net profit up 18% to ₹4,250 crore', 'Gross NPA improves to 1.9% from 2.2%'], 'source': 'NSE'}))
    save('news_hero_multi', cards.news_hero({
        'sample': True, 'category': 'Market News', 'date_text': 'Mon, 16 Nov 2026', 'theme': 'solar', 'seed': 2, 'tone': 'down',
        'quotes': [{'name': 'ABC Solar Ltd', 'symbol': 'ABCSOLAR', 'price': 139.19, 'chg': -4.66, 'pct': -3.24, 'time_text': t},
                   {'name': 'PQR Wind Energy Ltd', 'symbol': 'PQRWIND', 'price': 59.50, 'chg': -4.95, 'pct': -7.68, 'time_text': t}],
        'label': 'The selloff', 'headline': 'Renewable energy stocks *fall up to 7.68%*', 'points': ['PQR Wind fell 7.68%'],
        'source': 'NSE'}))
    save('news_hero_none', cards.news_hero({
        'sample': True, 'category': 'Economy', 'date_text': 'Mon, 16 Nov 2026', 'theme': 'market_up', 'seed': 9,
        'label': 'RBI policy', 'headline': 'RBI keeps *repo rate* unchanged', 'points': ['Decision announced on 16 November'],
        'source': 'RBI'}))


if __name__ == '__main__':
    test_news_hero()
    test_extremes()
    test_cap_movers()
    test_all()
    print('rendered to', OUT)
