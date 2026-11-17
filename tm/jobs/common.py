"""Shared draft creation: save images, store draft, send to Telegram or log as blocked."""
from .. import store, telegram
from ..util import log, now_ist
from ..verify.checks import Report, check_banned, check_numbers
from ..writer import captions


def date_numbers(*dates):
    out = []
    for d in dates:
        if d:
            out += [d.day, d.year, d.month]
    return out


def finish(kind, title, images, caption, report: Report, allowed_numbers=None, meta=None, notify=True):
    """Final checks shared by every post, then hand to Telegram. Returns draft or None."""
    if allowed_numbers is not None:
        body = caption.rsplit('\n\n', 1)[0]                      # hashtags excluded
        check_numbers(body, list(allowed_numbers) + date_numbers(now_ist().date()), report)
    check_banned(caption, report)
    if not report.passed:
        log.warning('BLOCKED %s %s\n%s', kind, title, report.text())
        telegram.send_blocked(kind, title, report.text())
        if not notify:
            return None
        try:
            telegram.send_text(f'⛔ Blocked before review: <b>{kind}</b> - {title}\n\n{report.text()[-1500:]}')
        except Exception as e:                       # noqa: BLE001
            log.warning('telegram notice failed: %s', e)
        return None
    import secrets
    hint = f'{kind}-{now_ist().strftime("%H%M%S")}-{secrets.token_hex(2)}'   # unique even for two drafts in one second
    paths = []
    for i, im in enumerate(images):
        rel = store.media_path(hint, i + 1)
        im.convert('RGB').save(store.config.DATA_DIR / rel, 'JPEG', quality=93)
        paths.append(rel)
    d = store.new_draft(kind, paths, caption, captions.threads_text(caption), [list(r) for r in report], meta)
    d['report_text'] = report.text()
    auto = store.config.auto_posts(kind) and not any(s == 'warn' for s, _ in report)
    if auto:
        d['status'] = 'auto'                        # approvals job posts it after the cancel window
    store.save_draft(d)
    telegram.send_draft(d, auto=auto)
    log.info('draft %s sent (%s%s)', d['id'], kind, ', auto-post' if auto else '')
    return d
