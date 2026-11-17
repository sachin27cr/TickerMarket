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
/ipo - IPO carousels
/iposubs - live IPO subscription
/innovative - next data story (Insights); /innovative list for tags, e.g. /innovative profits
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


def _dispatch_insight(arg):
    """Insights can take ~10 minutes (results scan), so they run as their own workflow, not inside approvals."""
    import os
    import requests
    repo, token = os.environ.get('GITHUB_REPOSITORY'), os.environ.get('GITHUB_TOKEN')
    if not repo or not token:
        return False
    r = requests.post(f'https://api.github.com/repos/{repo}/actions/workflows/scheduler.yml/dispatches',
                      headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'},
                      json={'ref': 'main', 'inputs': {'job': 'insights', 'force': True, 'arg': arg}}, timeout=20)
    if r.status_code != 204:
        log.warning('insight dispatch failed: %s %s', r.status_code, r.text[:200])
    return r.status_code == 204


def run_command(cmd, arg=''):
    from . import insight_jobs, market_jobs, news_jobs
    if cmd in ('/innovative', '/insight', '/insights'):
        if arg.lower() in ('list', 'help', '?'):
            insight_jobs.run_tag('list')
        elif _dispatch_insight(arg or 'next'):
            telegram.send_text(f'Building insight {html.escape(arg or "(next in rotation)")} - the draft arrives here in a few minutes.')
        else:
            telegram.send_text('Building insight ...')
            insight_jobs.run_tag(arg)
        return
    jobs = {'/news': lambda: news_jobs.news(force=True), '/close': lambda: market_jobs.market_close(force=True),
            '/overview': lambda: market_jobs.daily_overview(force=True),
            '/capmovers': lambda: market_jobs.cap_movers(force=True),
            '/ath': lambda: market_jobs.weekly_ath(force=True), '/lows': lambda: market_jobs.weekly_lows(force=True), '/fii': lambda: market_jobs.fii_dii(force=True),
            '/global': lambda: market_jobs.global_cues(force=True), '/dayahead': lambda: market_jobs.day_ahead(force=True),
            '/ipo': lambda: market_jobs.ipo(force=True), '/iposubs': lambda: market_jobs.ipo_status(force=True)}
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
                parts = text.split(maxsplit=1)
                run_command(parts[0].split('@')[0].lower(), parts[1].strip() if len(parts) > 1 else '')
            except Exception as e:                   # noqa: BLE001
                log.exception('command failed')
                telegram.send_text(f'Command failed: {html.escape(str(e))[:500]}')
