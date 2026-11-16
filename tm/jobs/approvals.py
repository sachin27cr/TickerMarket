"""Runs every few minutes: handles Approve/Reject taps and Telegram commands."""
import html

from .. import config, store, telegram
from ..publish import meta
from ..sources import news as news_src
from ..util import log

HELP = """<b>Ticker Market bot</b>
/news - run a news scan now
/close - market close card
/overview - daily overview carousel
/capmovers - gainers and losers by market cap
/ath - stocks at all-time highs this week
/lows - stocks at 52-week lows this week
/fii - FII/DII card
/global - global cues card
/dayahead - day-ahead card
/ipo - IPO cards
/queue - drafts waiting for you
/flagged - recently blocked drafts
/feeds - news feed health
/pause, /resume - stop or restart all scheduled posts"""


def approve(did):
    d = store.load_draft(did)
    if not d:
        return 'draft not found'
    if d['status'] not in ('pending', 'auto'):
        return f'already {d["status"]}'
    urls = [store.media_url(p) for p in d['images']]
    res = meta.publish_all(urls, d['caption'], d['threads_text'])
    d['posted'] = res
    errors = {k: v for k, v in res.items() if str(v).startswith('error')}
    d['status'] = 'posted' if not errors else ('partial' if len(errors) < len(res) else 'failed')
    store.save_draft(d)
    label = {'posted': '✅ Posted', 'partial': '⚠️ Partly posted', 'failed': '❌ Post failed'}[d['status']]
    telegram.mark_message(d.get('telegram_message_id'), label)
    if errors:
        telegram.send_text(f'{label} {did}\n' + '\n'.join(f'{k}: {html.escape(str(v))}' for k, v in errors.items()))
    return label


def reject(did):
    d = store.load_draft(did)
    if not d:
        return 'draft not found'
    if d['status'] not in ('pending', 'auto'):
        return f'already {d["status"]}'
    d['status'] = 'rejected'
    store.save_draft(d)
    telegram.mark_message(d.get('telegram_message_id'), '❌ Rejected')
    return 'rejected'


def run_command(cmd):
    from . import market_jobs, news_jobs
    jobs = {'/news': lambda: news_jobs.news(force=True), '/close': lambda: market_jobs.market_close(force=True),
            '/overview': lambda: market_jobs.daily_overview(force=True),
            '/capmovers': lambda: market_jobs.cap_movers(force=True),
            '/ath': lambda: market_jobs.weekly_ath(force=True), '/lows': lambda: market_jobs.weekly_lows(force=True), '/fii': lambda: market_jobs.fii_dii(force=True),
            '/global': lambda: market_jobs.global_cues(force=True), '/dayahead': lambda: market_jobs.day_ahead(force=True),
            '/ipo': lambda: market_jobs.ipo(force=True)}
    if cmd in jobs:
        telegram.send_text(f'Running {cmd} ...')
        jobs[cmd]()
    elif cmd == '/queue':
        pend = store.list_drafts('pending') + store.list_drafts('auto')
        telegram.send_text('No drafts waiting.' if not pend else
                           'Waiting for you:\n' + '\n'.join(f'{d["id"]} - {d["kind"]}: {html.escape(d["caption"].splitlines()[0])}' for d in pend[-15:]))
    elif cmd == '/flagged':
        folder = config.DATA_DIR / 'flagged'
        files = sorted(folder.glob('*.json'), key=lambda p: p.stat().st_mtime)[-5:] if folder.exists() else []
        txt = '\n\n'.join(f'<b>{html.escape(store.read_json("flagged/" + p.name)["title"])}</b>\n'
                          f'{html.escape(store.read_json("flagged/" + p.name)["report"][-600:])}' for p in files)
        telegram.send_text(txt or 'Nothing blocked recently.')
    elif cmd == '/feeds':
        _, status = news_src.fetch_all()
        telegram.send_text('\n'.join(f'{n}: {s} ({c} fresh)' for n, s, c in status))
    elif cmd == '/pause':
        store.set_flag('paused', True); telegram.send_text('Paused. Scheduled jobs will not create drafts. /resume to restart.')
    elif cmd == '/resume':
        store.set_flag('paused', False); telegram.send_text('Resumed.')
    else:
        telegram.send_text(HELP)


def post_due_autos():
    """Auto-post drafts whose cancel window has passed (images are public by now)."""
    from datetime import datetime, timedelta
    from ..util import now_ist
    for d in store.list_drafts('auto'):
        if now_ist() - datetime.fromisoformat(d['created']) >= timedelta(minutes=config.AUTO_DELAY_MIN):
            log.info('auto-posting %s', d['id'])
            approve(d['id'])


def approvals():
    _handle_updates()
    post_due_autos()


def _handle_updates():
    for u in telegram.get_updates():
        cb = u.get('callback_query')
        if cb:
            if str(cb['message']['chat']['id']) != str(config.TELEGRAM_CHAT_ID):
                continue
            action, _, did = (cb.get('data') or '').partition(':')
            result = approve(did) if action == 'ap' else reject(did) if action == 'rj' else ''
            telegram.answer_callback(cb['id'], result or 'ok')
            log.info('callback %s %s -> %s', action, did, result)
            continue
        msg = u.get('message') or {}
        if str(msg.get('chat', {}).get('id')) != str(config.TELEGRAM_CHAT_ID):
            continue
        text = (msg.get('text') or '').strip()
        if text.startswith('/'):
            try:
                run_command(text.split()[0].split('@')[0].lower())
            except Exception as e:                   # noqa: BLE001
                log.exception('command failed')
                telegram.send_text(f'Command failed: {html.escape(str(e))[:500]}')
