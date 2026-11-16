"""python -m tm.cli <job> [--force]"""
import html
import sys
import traceback

from . import store, telegram
from .jobs import approvals, market_jobs, news_jobs
from .util import log

JOBS = {
    'global_cues': market_jobs.global_cues,
    'day_ahead': market_jobs.day_ahead,
    'ipo': market_jobs.ipo,
    'news': news_jobs.news,
    'market_close': market_jobs.market_close,
    'cap_movers': market_jobs.cap_movers,
    'daily_overview': market_jobs.daily_overview,
    'fii_dii': market_jobs.fii_dii,
    'weekly_ath': market_jobs.weekly_ath,
    'weekly_lows': market_jobs.weekly_lows,
    'approvals': approvals.approvals,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in JOBS:
        print('jobs:', ', '.join(JOBS)); sys.exit(2)
    name, force = sys.argv[1], '--force' in sys.argv
    if name != 'approvals' and store.get_flag('paused') and not force:
        log.info('paused - skipping %s', name); return
    try:
        JOBS[name](force=force) if name != 'approvals' else JOBS[name]()
    except Exception as e:                       # noqa: BLE001 - report every crash to Telegram
        log.exception('%s crashed', name)
        try:
            telegram.send_text(f'⚠️ Job <b>{name}</b> crashed: {html.escape(str(e))[:300]}\n\n'
                               f'<code>{html.escape(traceback.format_exc()[-1200:])}</code>')
        except Exception:                        # noqa: BLE001
            pass
        sys.exit(1)


if __name__ == '__main__':
    main()
