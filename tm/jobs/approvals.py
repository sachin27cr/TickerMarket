"""Runs every few minutes: handles Approve/Reject taps and Telegram commands."""
import html
from pathlib import Path

from .. import config, schedule, store, telegram
from ..publish import meta
from ..sources import news as news_src
from ..util import log, now_ist

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
/reelam /reelpm /reelweek /reelath /reellows - make a reel now
/spotlight - best quarterly results of the last few days
/voices - hear the voice options; /voice name - choose one; /say text - hear how a line is pronounced
/metacheck - check the Instagram/Facebook keys (posts nothing)
/retry id - post a draft again where it failed
/customreel name - make an explainer reel written for you (e.g. /customreel gold-ai-selloff)
/where id - live links of a posted draft
/innovative - next data story (Insights); /innovative list for tags, e.g. /innovative profits
/queue - drafts waiting for you
/flagged - recently blocked drafts
/feeds - news feed health
/pause, /resume - stop or restart all scheduled posts"""


NAMES = {'instagram': 'Instagram', 'facebook': 'Facebook', 'threads': 'Threads'}


def _wait_for_draft(did, tries=10, pause=20):
    """A draft tapped seconds after it arrived may not be saved to the data branch yet (the job that made it
    saves at its very end). Pull the latest state a few times before giving up (about 3 minutes)."""
    import subprocess
    import time
    for _ in range(tries):
        d = store.load_draft(did)
        if d:
            return d
        time.sleep(pause)
        subprocess.run(['git', '-C', str(config.DATA_DIR), '-c', 'user.name=bot', '-c', 'user.email=bot@x', 'pull', '--quiet', '--rebase', '--autostash', 'origin', 'data'],
                       capture_output=True)
    return store.load_draft(did)


def approve(did, msg_id=None):
    """A tap on Approve: news/reels are queued for their slot (or the next free gap) and post from there.
    A tap on a queued or auto draft ('Post now') publishes at once."""
    d = store.load_draft(did) or _wait_for_draft(did)
    if not d:
        if msg_id:                                   # put the buttons back so it can be tapped again
            telegram.restore_buttons(msg_id, did)
        return 'draft not found - it may still be saving; tap Approve again in a minute'
    if d['status'] == 'pending':
        d['status'] = 'queued'
        d['approved_at'] = now_ist().isoformat()
        store.save_draft(d)
        at = schedule.slot(d['kind'])
        when = (f'goes live at {schedule.label(at)}' if at and at > now_ist() else 'goes live in the next free slot')
        telegram.mark_message(d.get('telegram_message_id'), f'✅ Approved - {when}', post_now_did=did)
        post_due()
        d = store.load_draft(did)
        return '' if d['status'] == 'queued' else f'posted ({d["status"]})'
    return publish(did)


def publish(did):
    d = store.load_draft(did)
    if not d:
        return 'draft not found'
    if d['status'] not in ('auto', 'queued', 'failed', 'partial'):
        return f'already {d["status"]}'
    done = {k: v for k, v in (d.get('posted') or {}).items() if not str(v).startswith('error')}
    todo = [p for p in config.POST_TO if p not in done]          # a retry only posts where it failed
    if not todo:
        return 'already posted'
    telegram.mark_message(d.get('telegram_message_id'), '⏳ Posting… please wait')
    if d.get('video'):
        res = meta.publish_reel(config.DATA_DIR / d['video'], store.media_url(d['video']), d['caption'],
                                d['threads_text'], store.media_url(d['images'][0]) if d['images'] else None, only=todo)
    else:
        urls = [store.media_url(p) for p in d['images']]
        res = meta.publish_all(urls, d['caption'], d['threads_text'], only=todo)
    d['posted'] = {**(d.get('posted') or {}), **res}
    errors = {k: v for k, v in d['posted'].items() if str(v).startswith('error')}
    d['status'] = 'posted' if not errors else ('partial' if len(errors) < len(d['posted']) else 'failed')
    d['posted_at'] = now_ist().isoformat()
    store.save_draft(d)
    if not errors or len(errors) < len(d['posted']):
        store.set_flag('last_post_at', now_ist().isoformat())
    ok = [NAMES.get(k, k) for k, v in d['posted'].items() if not str(v).startswith('error')]
    bad = [NAMES.get(k, k) for k in errors]
    label = {'posted': '✅ Posted on ' + ' & '.join(ok),
             'partial': '⚠️ Posted on ' + ' & '.join(ok) + ' · ' + ' & '.join(bad) + ' failed',
             'failed': '❌ Post failed'}[d['status']]
    telegram.mark_message(d.get('telegram_message_id'), label, did if errors else None)
    live = meta.links(res)
    for k, note in getattr(meta, 'FB_NOTE', {}).items():
        live[k] = live.get(k, '') + f'  ({note})'
    if live:
        telegram.send_text(f'{label}\n' + '\n'.join(f'{NAMES.get(k, k)}: {html.escape(v)}' for k, v in live.items()))
    if errors:
        telegram.send_text(f'{label}\n' + '\n'.join(f'{NAMES.get(k, k)}: {html.escape(str(v))}' for k, v in errors.items())
                           + '\nTap 🔁 Retry posting to try again (only where it failed).')
    return label


def reject(did):
    d = store.load_draft(did) or _wait_for_draft(did, tries=4)
    if not d:
        return 'draft not found'
    if d['status'] not in ('pending', 'auto', 'queued'):
        return f'already {d["status"]}'
    d['status'] = 'rejected'
    store.save_draft(d)
    telegram.mark_message(d.get('telegram_message_id'), '❌ Rejected')
    return 'rejected'


REEL_CMDS = {'/spotlight': 'results_spotlight', '/reelam': 'reel_morning', '/reelpm': 'reel_evening', '/reelweek': 'reel_weekly',
             '/reelath': 'reel_ath', '/reellows': 'reel_lows'}


def _dispatch_insight(arg, job='insights'):
    """Long jobs (insights, reels) run as their own workflow, not inside the 5-minute approvals run."""
    import os
    import requests
    repo, token = os.environ.get('GITHUB_REPOSITORY'), os.environ.get('GITHUB_TOKEN')
    if not repo or not token:
        return False
    r = requests.post(f'https://api.github.com/repos/{repo}/actions/workflows/scheduler.yml/dispatches',
                      headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'},
                      json={'ref': 'main', 'inputs': {'job': job, 'force': True, 'arg': arg}}, timeout=20)
    if r.status_code != 204:
        log.warning('insight dispatch failed: %s %s', r.status_code, r.text[:200])
    return r.status_code == 204


def run_command(cmd, arg=''):
    from . import insight_jobs, market_jobs, news_jobs
    if cmd == '/voices':
        import tempfile
        from ..reels import voice as V
        cur = (store.get_flag('voice') or V.DEFAULT).lower()
        have = V.available()
        missing = [n for n, (vid, _, _) in V.VOICES.items() if have and vid not in have]
        if missing:
            telegram.send_text('Not offered by the free voice service right now: ' + ', '.join(missing))
        for name, (vid, _, desc) in V.VOICES.items():
            if name in missing:
                continue
            try:
                path = V.sample(name, Path(tempfile.mkdtemp()) / f'{name}.mp3')
                telegram.send_audio(path, f'{name}{" (current)" if name == cur else ""} - {desc}. Pick: /voice {name}')
            except Exception as e:                   # noqa: BLE001
                telegram.send_text(f'{name}: sample failed ({type(e).__name__})')
        return
    if cmd == '/retry':
        did = arg.strip()
        telegram.send_text(html.escape(approve(did) if did else 'Use /retry <draft id>, e.g. /retry 11200010-82448'))
        return
    if cmd == '/where':
        d = store.load_draft(arg.strip()) if arg.strip() else None
        if not d:
            telegram.send_text('Use /where <draft id> to get the live links of a posted draft.')
            return
        live = meta.links(d.get('posted'))
        telegram.send_text('\n'.join(f'{NAMES.get(k, k)}: {html.escape(v)}' for k, v in live.items()) or 'Not posted yet.')
        return
    if cmd == '/metacheck':
        from ..publish import meta
        lines = meta.check_setup()
        telegram.send_text('Meta setup check (nothing was posted):\n' +
                           '\n'.join(('✅ ' if ok else '❌ ') + html.escape(m) for ok, m in lines))
        return
    if cmd == '/say':
        import tempfile
        from ..reels import voice as V
        text = arg.strip() or V.SAMPLE
        path, engine = V.speak(V.speech(text), Path(tempfile.mkdtemp()) / 'say.mp3')
        if path:
            telegram.send_audio(path, 'Spoken as: ' + V.speech(text)[:900])
        else:
            telegram.send_text(f'Could not make audio ({engine}).')
        return
    if cmd == '/voice':
        from ..reels import voice as V
        name = arg.strip().lower()
        if name not in V.VOICES:
            telegram.send_text('Choose one of: ' + ', '.join(f'/voice {n}' for n in V.VOICES) + '. Hear them with /voices')
            return
        store.set_flag('voice', name)
        telegram.send_text(f'Reels will now use the {name} voice ({V.VOICES[name][2]}).')
        return
    if cmd == '/customreel':
        if _dispatch_insight(arg.strip(), 'reel_custom'):
            telegram.send_text('Making the explainer reel - the draft arrives here in a few minutes.')
        else:
            telegram.send_text('Could not start the reel job.')
        return
    if cmd in REEL_CMDS:
        if _dispatch_insight('', REEL_CMDS[cmd]):
            telegram.send_text(f'Running {REEL_CMDS[cmd]} - the draft arrives here in a few minutes.')
        else:
            from . import reel_jobs
            telegram.send_text('Making the reel ...')
            {'reel_morning': reel_jobs.morning_reel, 'reel_evening': reel_jobs.evening_reel,
             'reel_weekly': reel_jobs.weekly_reel, 'reel_ath': reel_jobs.ath_reel,
             'reel_lows': reel_jobs.lows_reel, 'results_spotlight': insight_jobs.results_spotlight}[REEL_CMDS[cmd]](force=True)
        return
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
        pend = store.list_drafts('pending') + store.list_drafts('auto') + store.list_drafts('queued')
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
    post_due()


def post_due():
    """Publish what is due (runs every 5 minutes and right after an approval):
    - posts with a slot (data posts, reels) go live at their slot, or at once if the slot has passed;
    - news and other posts without a slot go out after the cancel window, keeping ~30 minutes from the last
      post and from the next slotted post, one at a time."""
    from datetime import datetime, timedelta
    now = now_ist()
    ready = store.list_drafts('auto') + store.list_drafts('queued')
    last = store.get_flag('last_post_at')
    last = datetime.fromisoformat(last) if last else None
    fixed, free = [], []
    for d in ready:
        created = datetime.fromisoformat(d['created'])
        if now - created > timedelta(hours=20):          # stale: never post yesterday's card
            d['status'] = 'expired'
            store.save_draft(d)
            telegram.mark_message(d.get('telegram_message_id'), '⌛ Expired - not posted')
            continue
        at = schedule.slot(d['kind'], created.date())
        (fixed if at else free).append((at, created, d))
    for at, _, d in sorted(fixed, key=lambda x: x[0]):
        if now >= at:
            log.info('posting %s at its %s slot', d['id'], schedule.label(at))
            publish(d['id'])
            last = now
    upcoming = [at for at, _, _ in fixed if now < at <= now + schedule.SPACING]
    for at, created, d in sorted(free, key=lambda x: x[1]):
        wait = (timedelta(minutes=config.AUTO_DELAY_MIN) if d['status'] == 'auto' else timedelta(0))
        if now - created < wait:
            continue
        if d['kind'] == 'news' and ((last and now - last < schedule.SPACING) or upcoming):
            continue                                       # keep news 30 minutes away from other posts
        log.info('posting %s', d['id'])
        publish(d['id'])
        last = now
        if d['kind'] == 'news':
            break                                          # one news post per cycle


def approvals():
    import json
    import os
    raw = os.environ.get('TM_UPDATE', '').strip()
    if raw:                                          # instant mode: one update forwarded by the Cloudflare Worker
        try:
            u = json.loads(raw)
        except ValueError:
            log.warning('bad TM_UPDATE')
            u = None
        if u is not None:
            seen = store.read_json('seen_updates.json', {'ids': []})
            if u.get('update_id') in seen['ids']:
                log.info('update %s already handled', u.get('update_id'))
            else:
                seen['ids'] = (seen['ids'] + [u.get('update_id')])[-300:]
                store.write_json('seen_updates.json', seen)
                _handle_updates([u], instant=True)
    else:
        _handle_updates()                            # polling (only works while no webhook is set)
    post_due_autos()


def _handle_updates(updates=None, instant=False):
    for u in (telegram.get_updates() if updates is None else updates):
        cb = u.get('callback_query')
        if cb:
            if str(cb['message']['chat']['id']) != str(config.TELEGRAM_CHAT_ID):
                continue
            action, _, did = (cb.get('data') or '').partition(':')
            mid = (cb.get('message') or {}).get('message_id')
            result = approve(did, mid) if action == 'ap' else reject(did) if action == 'rj' else ''
            if instant:                              # the Worker already answered the tap; the button shows the outcome
                if result and result.startswith(('already', 'draft not')):  # noqa
                    telegram.send_text(html.escape(result))
            else:
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
