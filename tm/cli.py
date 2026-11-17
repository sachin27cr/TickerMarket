"""python -m tm.cli <job> [--force]"""
import html
import sys
import traceback

from . import store, telegram
import os

from .jobs import approvals, insight_jobs, market_jobs, news_jobs
from .util import log

JOBS = {
    'global_cues': market_jobs.global_cues,
    'day_ahead': market_jobs.day_ahead,
    'ipo': market_jobs.ipo,
    'ipo_status': market_jobs.ipo_status,
    'news': news_jobs.news,
    'market_close': market_jobs.market_close,
    'cap_movers': market_jobs.cap_movers,
    'daily_overview': market_jobs.daily_overview,
    'fii_dii': market_jobs.fii_dii,
    'weekly_ath': market_jobs.weekly_ath,
    'weekly_lows': market_jobs.weekly_lows,
    'insights': insight_jobs.insights,
    'approvals': approvals.approvals,
}


from .util import scrub   # noqa: E402


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in JOBS:
        print('jobs:', ', '.join(JOBS)); sys.exit(2)
    name, force = sys.argv[1], '--force' in sys.argv
    if name != 'approvals' and store.get_flag('paused') and not force:
        log.info('paused - skipping %s', name); return
    try:
        arg = os.environ.get('TM_ARG', '').strip()
        if name == 'insights' and arg:              # on demand from Telegram: /innovative [tag]
            insight_jobs.run_tag('' if arg == 'next' else arg)
        else:
            JOBS[name](force=force) if name != 'approvals' else JOBS[name]()
    except Exception as e:                       # noqa: BLE001 - report every crash to Telegram
        log.error('%s crashed: %s', name, scrub(str(e)))
        try:
            telegram.send_text(f'⚠️ Job <b>{name}</b> crashed: {html.escape(scrub(str(e)))[:300]}\n\n'
                               f'<code>{html.escape(scrub(traceback.format_exc())[-1200:])}</code>')
        except Exception:                        # noqa: BLE001
            pass
        sys.exit(1)


if __name__ == '__main__':
    main()
