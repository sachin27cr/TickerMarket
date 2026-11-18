"""Offline end-to-end test: every job runs with fake sources/LLMs in dry-run mode.

Run: TM_DRY_RUN=1 TM_DATA_DIR=/tmp/tmdata python -m tests.test_pipeline
"""
import os
import shutil
from datetime import datetime, timedelta

os.environ.setdefault('TM_DRY_RUN', '1')
os.environ.setdefault('TM_DATA_DIR', '/tmp/tmdata')

from tm import config, store                                  # noqa: E402
from tm.jobs import market_jobs, news_jobs                    # noqa: E402
from tm.sources import market, nse, news as news_src          # noqa: E402
from tm.util import IST, fmt_inr, today_ist                   # noqa: E402
from tm.verify import checks                                  # noqa: E402
from tm.writer import captions, llm                           # noqa: E402
from tests.fixtures import sample_data as S                   # noqa: E402


def q(name, close, chg):
    return {'name': name, 'close': close, 'chg': chg, 'pct': chg / (close - chg) * 100, 'prev': close - chg,
            'date': today_ist(), 'source': 'NSE'}


def fake_sources():
    market_jobs.CLOSE_READY = (0, 0)              # tests run at any time of day
    quotes = {i['name']: q(i['name'], i['close'], i['chg']) for i in S.INDICES}
    market.market_snapshot = lambda names=market.KEY_INDICES: (
        {k: v for k, v in quotes.items() if k in names} if set(names) & set(market.KEY_INDICES) else
        {s['name']: {**q(s['name'], 1000 * (1 + s['pct'] / 100), 10 * s['pct']), 'pct': s['pct']} for s in S.SECTORS},
        {'advances': 312, 'declines': 181, 'universe': 'Nifty 500'}, today_ist(),
        checks.Report([('ok', 'fake NSE = Yahoo')]))
    market.sector_snapshot = lambda: ({s['name']: {'name': s['name'], 'pct': s['pct']} for s in S.SECTORS},
                                      checks.Report([('ok', 'fake sectors')]))
    market.movers = lambda index='NIFTY 50', n=5: (S.GAINERS, S.LOSERS)
    _real_snapshot = market.market_snapshot
    d = today_ist() - timedelta(days=1)
    market.global_snapshot = lambda: ([
        {'name': 'Dow Jones', 'value': '44,210.35', 'close': 44210.35, 'pct': 0.42, 'date': d},
        {'name': 'S&P 500', 'value': '6,120.80', 'close': 6120.80, 'pct': 0.61, 'date': d},
        {'name': 'Nasdaq', 'value': '20,180.15', 'close': 20180.15, 'pct': 0.95, 'date': d},
        {'name': 'Brent Crude', 'value': '$92.04', 'close': 92.04, 'pct': -0.78, 'date': d},
        {'name': 'Gold', 'value': '$2,710.40', 'close': 2710.40, 'pct': 0.30, 'date': d},
        {'name': 'USD / INR', 'value': '84.62', 'close': 84.62, 'pct': -0.12, 'date': d}], [])
    nse.index_constituents = lambda index='NIFTY 50': (S.CAP_ROWS[index], datetime.now(IST))
    nse.fii_dii = lambda: {'date': today_ist(), 'fii': 4870.25, 'dii': -2310.65}
    nse.trading_holidays = lambda: set()
    from tm.sources import calendar as cal
    now = datetime.now(IST)
    cal.events_today = lambda: [{'when': now.replace(hour=19, minute=0), 'country': 'US', 'title': 'CPI m/m'},
                                {'when': now.replace(hour=23, minute=30), 'country': 'US', 'title': 'FOMC Statement'}]
    cal.results_schedule = lambda days=6: {today_ist(): [('XYZBANK', 'XYZ Bank Ltd')],
                                           today_ist() + timedelta(days=1): [('INFY', 'Infosys Limited'), ('ABCTECH', 'ABC Technologies Limited')],
                                           today_ist() + timedelta(days=2): [('TCS', 'Tata Consultancy Services Limited')]}
    nse.event_calendar = lambda: [{'symbol': 'XYZBANK', 'company': 'XYZ Bank Ltd', 'purpose': 'Financial Results', 'date': today_ist()}]
    nse.corporate_actions = lambda a, b: [{'symbol': 'LMN', 'company': 'LMN Ltd', 'subject': 'Dividend - Rs 5 Per Share', 'ex_date': today_ist()}]
    t = datetime.now(IST)
    nse.ipos_current = lambda: [{'companyName': 'ABC Technologies Limited', 'symbol': 'ABCTECH', 'series': 'EQ',
                                 'issueStartDate': t.strftime('%d-%b-%Y'), 'issueEndDate': (t + timedelta(days=2)).strftime('%d-%b-%Y'),
                                 'issuePrice': 'Rs.412 to Rs.434', 'issueSize': '28801843'}]
    nse.ipos_upcoming = lambda: []
    monday = today_ist() - timedelta(days=today_ist().weekday())
    wk_hist, wk_rows = S.weekly_fixture(monday)
    nse.index_constituents = lambda index='NIFTY 50': (wk_rows[index], datetime.now(IST))
    market.weekly_history = lambda symbols: {s: wk_hist[s] for s in symbols}
    nse.equity_list = lambda: [('XYZBANK', 'XYZ Bank Limited'), ('ABCTECH', 'ABC Technologies Limited')]
    nse.quote = lambda sym: {'price': 1712.30, 'chg': 74.85, 'pct': round(74.85 / (1712.30 - 74.85) * 100, 2),
                             'prev': 1712.30 - 74.85, 'time': datetime.now(IST), 'name': 'XYZ Bank Limited'}
    def _no_yahoo(sym):
        raise RuntimeError('offline')
    market.yahoo_daily = _no_yahoo
    board = [q(i['name'], i['close'], i['chg']) for i in S.INDICES]
    market.index_board = lambda: (board, today_ist(), checks.Report([('ok', 'fake board')]))
    def _ext(day, n=6):
        out = {}
        for seg, idx in market.CAP_SEGMENTS:
            rows = S.CAP_ROWS[idx]
            out[seg] = {'index': idx, 'count': len(rows), 'ath': rows[:2], 'ath_count': 2, 'hi52': rows[2:5],
                        'hi52_count': 5, 'lo52': rows[-3:], 'lo52_count': 3}
        return out, [('ok', 'fake extremes')]
    market.daily_extremes = _ext
    def _fno(day, report, lookback=7):
        report.ok('fake F&O')
        return {'idx_fut_long': 120000, 'idx_fut_short': 280000, 'idx_fut_net': -160000, 'idx_fut_long_pct': 30.0,
                'stk_fut_net': 45210, 'idx_call_net': 51234, 'idx_put_net': -23456, 'client_long_pct': 61.2,
                'idx_fut_net_chg': 8210}
    market.fii_fno = _fno
    nse.ipo_detail = lambda sym, series='EQ': {'issueInfo': {'minBidQuantity': '34', 'faceValue': 'Rs 2',
        'issueSize': 'Rs 1,250 Cr', 'freshIssue': 'Rs 800 Cr', 'offerForSale': 'Rs 450 Cr', 'qibQuota': '50%',
        'niiQuota': '15%', 'retailQuota': '35%', 'registrar': 'ABC Registry Ltd', 'leadManagers': 'XYZ Capital'}}
    nse.ipo_subscription = lambda sym: ([{'category': 'Qualified Institutional Buyers', 'offered': 1000.0, 'bid': 520.0, 'times': 0.52},
                                         {'category': 'Retail Individual Investors', 'offered': 2000.0, 'bid': 3100.0, 'times': 1.55},
                                         {'category': 'Total', 'offered': 3000.0, 'bid': 3620.0, 'times': 1.21}], '17-Nov-2026 17:00', {})
    cl = S.news_cluster()
    news_src.fetch_all = lambda max_age_hours=None: (cl['items'], [('fake', 'ok', 2)])


def fake_llm(good=True):
    def write(prompt):
        return ({'relevant': True, 'category': 'Earnings',
                 'headline': '*XYZ Bank* Q2 profit jumps *18%* to *₹4,250 crore*' if good else '*XYZ Bank* profit jumps *25%*',
                 'points': ['Net interest income rose 14% to ₹9,880 crore', 'Gross NPA improved to 1.9% from 2.2%',
                            'Results reported on 12 November 2026'],
                 'body': ['XYZ Bank reported a net profit of ₹4,250 crore for the September quarter, up 18% year-on-year.',
                          'Net interest income grew 14% to ₹9,880 crore and gross NPA improved to 1.9%.'],
                 'hashtags': ['#XYZBank', '#Q2Results', '#BankingStocks', '#StockMarketIndia', '#Earnings'],
                 'companies': ['XYZ Bank', 'Imaginary Corp'], 'label': 'Q2 result impact', 'tone': 'up',
                 'sector': 'banking'}, 'gemini')
    llm.write = write
    llm.check = lambda prompt, writer: ({'all_supported': True, 'misleading': False, 'advice_or_prediction': False,
                                         'issues': []}, 'groq')


def run_news():
    store.set_flag('last_news_run', None)        # each test call is a separate scheduled run
    return news_jobs.news()


def drafts():
    return store.list_drafts()


def run():
    shutil.rmtree(config.DATA_DIR, ignore_errors=True)
    fake_sources(); fake_llm()
    n0 = 0
    for name, fn in [('market_close', market_jobs.market_close), ('cap_movers', market_jobs.cap_movers), ('daily_overview', market_jobs.daily_overview),
                     ('global_cues', market_jobs.global_cues), ('fii_dii', market_jobs.fii_dii), ('weekly_ath', market_jobs.weekly_ath), ('weekly_lows', market_jobs.weekly_lows),
                     ('day_ahead', market_jobs.day_ahead), ('ipo', market_jobs.ipo), ('ipo_status', market_jobs.ipo_status), ('news', run_news)]:
        fn()
        ds = drafts()
        assert len(ds) == n0 + 1, f'{name}: expected a draft, flagged={list((config.DATA_DIR / "flagged").glob("*"))}'
        d = ds[-1] if ds[-1]['kind'] == name else [x for x in ds if x['kind'] == name][0]
        assert all((config.DATA_DIR / p).exists() for p in d['images'])
        assert len(d['threads_text']) <= 500
        print(f'--- {name}: {len(d["images"])} image(s), checks:\n{d["report_text"]}\n\n{d["caption"]}\n')
        n0 += 1
    # dedupe: running again creates nothing
    market_jobs.market_close(); market_jobs.fii_dii(); run_news()
    assert len(drafts()) == n0, 'dedupe failed'
    # a wrong number from the AI must be blocked
    shutil.rmtree(config.DATA_DIR / 'seen' / 'news', ignore_errors=True)
    fake_llm(good=False)
    run_news()
    assert len(drafts()) == n0, 'bad AI number was not blocked'
    flagged = list((config.DATA_DIR / 'flagged').glob('*.json'))
    assert flagged, 'blocked draft not logged'
    wk = store.read_json(f'weekly/{today_ist() - timedelta(days=today_ist().weekday())}.json')
    for seg, g in wk['groups'].items():
        assert g['ath_count'] == 3 and g['low_count'] == 3, (seg, g['ath_count'], g['low_count'])
    print('weekly scan: 3 highs + 3 lows per group, mismatched NSE level dropped')
    print('blocked as expected:', store.read_json('flagged/' + flagged[0].name)['report'].splitlines()[-2:])


def auto_post():
    from tm.jobs import approvals
    from tm import config as C
    C.AUTO_POST = set(C.DATA_KINDS)
    shutil.rmtree(config.DATA_DIR / 'seen', ignore_errors=True)
    market_jobs.market_close()
    d = max([x for x in drafts() if x['kind'] == 'market_close'], key=lambda x: x['created'])
    assert d['status'] == 'auto', d['status']
    approvals.post_due_autos()                       # cancel window not over yet
    assert store.load_draft(d['id'])['status'] == 'auto'
    d['created'] = '2000-01-01T00:00:00+05:30'; store.save_draft(d)
    approvals.post_due_autos()
    assert store.load_draft(d['id'])['status'] == 'posted'
    # news never auto-posts with the 'data' setting
    shutil.rmtree(config.DATA_DIR / 'seen' / 'news', ignore_errors=True); fake_llm()
    run_news()
    assert [x for x in drafts() if x['kind'] == 'news'][-1]['status'] == 'pending'
    C.AUTO_POST = set()
    print('auto-post: data card posted after cancel window, news still waits for approval')


def unit():
    assert fmt_inr(1234567.891) == '12,34,567.89' and fmt_inr(-880.2) == '-880.20' and fmt_inr(999) == '999.00'
    r = checks.Report(); checks.check_numbers('Nifty closed at 24,612.40, up 0.48%', [24612.4, 0.4832], r); assert r.passed
    r = checks.Report(); checks.check_numbers('Nifty closed at 24,621.40', [24612.4], r); assert not r.passed
    r = checks.Report(); checks.check_banned('Top stocks to buy now with target price', r); assert not r.passed
    r = checks.Report(); checks.check_banned('FIIs were net sellers on 13 November', r); assert r.passed
    r = checks.Report(); checks.check_names('Infosys and Wipro shares rose', 'infosys shares rose 2%', r); assert not r.passed
    long = 'HEAD\n\n' + 'A sentence here. ' * 60 + '\n\nSource: X. For information only. Not investment advice.\n\n#a #b'
    assert len(captions.threads_text(long)) <= 500
    print('unit tests passed')


def duplicate_guard():
    store.set_flag('last_news_run', None)
    shutil.rmtree(config.DATA_DIR / 'seen' / 'news', ignore_errors=True)
    n1 = len(drafts()); news_jobs.news(); n2 = len(drafts()); news_jobs.news(); n3 = len(drafts())
    assert n2 == n1 + 1 and n3 == n2, (n1, n2, n3)
    print('duplicate trigger within 50 min skipped')


def fake_insights():
    from datetime import date
    from tm.sources import insights as src
    qe, pe = date(2026, 9, 30), date(2025, 9, 30)
    names = [('DIAMONDPOW', 'Diamond Power Infrastructure', 27.73, 107.88, 438.33, 1031.90),
             ('PRINCEPIPE', 'Prince Pipes And Fittings', 15.0, 48.0, 595.0, 821.0),
             ('PRIMEFOCUS', 'Prime Focus', 14.0, 58.0, 1061.0, 1429.0),
             ('KERNEX', 'Kernex Microsystems (India)', 17.0, 129.0, 47.0, 543.0),
             ('MODINSU', 'Modern Insulators', 17.0, 53.0, 176.0, 249.0),
             ('SLOWCO', 'Slow Growth Co', 100.0, 120.0, 500.0, 520.0)]
    yq = {s: {qe: {'profit': b * 1e7, 'revenue': rv * 1e7}, pe: {'profit': a * 1e7, 'revenue': ra * 1e7}}
          for s, _, a, b, ra, rv in names}
    nq = {s: [{'end': qe, 'profit': b * 100, 'revenue': rv * 100, 'basis': 'C'},
              {'end': pe, 'profit': a * 100, 'revenue': ra * 100, 'basis': 'C'}] for s, _, a, b, ra, rv in names}
    nq['MODINSU'][0]['profit'] *= 1.2            # NSE disagrees with Yahoo -> must be left out
    rows = [{'symbol': s, 'last': 500.0 + i, 'chg': 5.0, 'pct': 1.01} for i, (s, *_ ) in enumerate(names)]
    nse.index_constituents = lambda index='NIFTY 50': (rows, datetime.now(IST))
    src.yahoo_quarters = lambda sym: yq[sym]
    src.nse_quarters = lambda sym: (nq[sym], {})
    market.equity_master = lambda: [(s, n + ' Limited') for s, n, *_ in names]
    src.month_assets = lambda y, m: ([{'label': l, 'start': 100.0, 'end': 100 + p, 'pct': p, 'fmt': '{:,.2f}'} for l, p in
                                      [('Brent Crude', 13.6), ('Nifty 50', 1.9), ('US Dollar / Rupee', 0.4), ('Gold', -6.9),
                                       ('Nasdaq', -5.3), ('Silver', -18.3), ('Sensex', 1.7)]], [('ok', 'fake assets')])
    src.mcap_leaders = lambda n=10: ([{'symbol': f'CO{i}', 'name': f'Company {chr(65 + i)} Ltd', 'price': 1000.0 + i,
                                       'shares': 1e9, 'mcap_cr': 2000000 - i * 120000, 'week_pct': 1.5 - i * 0.4,
                                       'week_cr': 30000 - i * 8000} for i in range(10)], [('ok', 'fake mcap')])
    src.one_year_returns = lambda u='NIFTY 50': ([{'symbol': f'S{i:02d}', 'then': 100.0, 'now': 100 + 90 - i * 3.5,
                                                   'pct': round(90 - i * 3.5, 2), 'then_date': date(2025, 11, 17)}
                                                  for i in range(50)], date(2025, 11, 17), [('ok', 'fake 1y')])
    src.sector_scorecard = lambda: ([{'name': n, 'last': 1000.0, 'w1': 0.5 - k * 0.2, 'm1': 3.2 - k * 0.6, 'y1': 12.0 - k * 2.1}
                                     for k, n in enumerate(src.SECTOR_INDICES + ['NIFTY 50'])], [('ok', 'fake sectors')])


def insights_test():
    from tm.jobs import insight_jobs as ij
    fake_insights()
    shutil.rmtree(config.DATA_DIR / 'insights', ignore_errors=True)
    for tag in ['profits', 'assets', 'mcap', 'wealth', 'sectors']:
        n = len(drafts())
        d = ij.run_tag(tag)
        assert d and len(drafts()) == n + 1, f'insight {tag}: no draft (see flagged)'
        assert d['status'] == 'pending' and len(d['images']) <= 10
        print(f'--- insight {tag}: {len(d["images"])} slides\n{d["report_text"]}\n\n{d["caption"]}\n')
    st = store.read_json(ij.STATE)
    posted = st['profits']['Q2 FY27']['posted']
    assert 'MODINSU' not in posted and 'SLOWCO' not in posted and len(posted) == 4, posted
    n = len(drafts()); ij.insights(); assert len(drafts()) == n, 'insight posted twice within 2 days'
    st['last_post'] = '2000-01-01'; store.write_json(ij.STATE, st)
    ij.insights(); assert len(drafts()) == n, 'nothing new should be due (all tags inside their gap)'
    print('insights: 5 tags built, NSE/Yahoo mismatch left out, every-other-day gate works')
    # results spotlight: strong results of the last few days
    from tm.sources import insights as src
    from datetime import date
    nse.event_calendar = lambda: [{'symbol': s_, 'company': c_, 'purpose': 'Financial Results', 'date': today_ist()}
                                  for s_, c_ in [('DIAMONDPOW', 'Diamond Power Infrastructure Limited'), ('PRIMEFOCUS', 'Prime Focus Limited'),
                                                 ('SLOWCO', 'Slow Growth Co Limited')]]
    def vr(sym, yq=None, nq=None, allow_single=False):
        base = {'DIAMONDPOW': (27.73, 107.88, 438.33, 1031.90), 'PRIMEFOCUS': (14.0, 58.0, 1061.0, 1429.0),
                'SLOWCO': (100.0, 105.0, 500.0, 510.0)}[sym]
        r = {'symbol': sym, 'q_end': date(2026, 9, 30), 'py_end': date(2025, 9, 30), 'quarter': 'Q2 FY27',
             'py_quarter': 'Q2 FY26', 'profit_py': base[0], 'profit': base[1], 'revenue_py': base[2], 'revenue': base[3],
             'basis': 'Consolidated', 'growth': round((base[1] - base[0]) / base[0] * 100, 1)}
        return r, [('ok', f'{sym}: NSE = Yahoo')]
    src.verified_results = vr
    n = len(drafts()); d = ij.results_spotlight(force=True)
    assert d and len(drafts()) == n + 1 and 'Slow Growth' not in d['caption'], 'spotlight'
    print('--- spotlight\n' + d['caption'])


def reels_test():
    from tm.jobs import reel_jobs
    fake_sources()
    reel_jobs._week_change = lambda ysym: {'start': 24000.0, 'end': {'^NSEI': 24612.40, '^BSESN': 80915.62,
                                                                     '^NSEBANK': 52310.55}[ysym], 'pct': 1.23,
                                           'last_date': today_ist()}
    for name, fn in [('reel_morning', reel_jobs.morning_reel), ('reel_evening', reel_jobs.evening_reel),
                     ('reel_weekly', reel_jobs.weekly_reel), ('reel_ath', reel_jobs.ath_reel)]:
        n = len(drafts())
        fn(force=True)
        ds = [d for d in drafts() if d['kind'] == name]
        assert len(drafts()) == n + 1 and ds, f'{name}: no draft (see flagged)'
        d = ds[-1]
        assert (config.DATA_DIR / d['video']).exists() and d['status'] == 'pending'
        print(f'--- {name}: {d["report_text"].splitlines()[-1]}\n{d["caption"]}\n')
    print('reels: morning, evening, weekly and all-time-high reels built')


if __name__ == '__main__':
    unit()
    run()
    auto_post()
    duplicate_guard()
    insights_test()
    reels_test()
    print('ALL PIPELINE TESTS PASSED')

