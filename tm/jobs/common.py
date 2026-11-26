"""Shared draft creation: save images, store draft, send to Telegram or log as blocked."""
import re

from .. import store, telegram
from ..util import fmt_date, log, now_ist
from ..verify.checks import Report, check_banned, check_numbers
from ..writer import captions


def _name_digits():
    from ..sources.names import name_numbers
    return name_numbers()


def date_numbers(*dates):
    out = []
    for d in dates:
        if d:
            out += [d.day, d.year, d.month]
    return out


MAX_SLIDES = 10        # Instagram carousel limit through the API

SKIP_POINT = re.compile(r'^(swipe|figures in|groups as defined|weekly % change|change from|gold, silver|'
                        r'past returns|market value =|sorted by|growth from a small|category-wise|read the)', re.I)


def summary_points(caption, n=6):
    """Key points for the 'In short' slide, taken from the caption (its numbers are already checked)."""
    out = []
    for para in caption.split('\n\n')[1:]:              # skip the headline
        if para.startswith('#') or 'not investment advice' in para.lower():
            continue
        for line in para.split('\n'):
            line = line.strip()
            if not line or SKIP_POINT.match(line) or line.endswith(':'):
                continue
            for sent in re.split(r'(?<=[.;])\s+(?=[A-Z₹])|,\s+while\s+', line):
                sent = sent.strip().rstrip('.')
                sent = sent[0].upper() + sent[1:] if sent else sent
                if 12 <= len(sent) <= 200:
                    out.append(sent)
    return out[:n]


def with_closing_slides(images, caption, dated=True):
    from ..render import insight_cards as ic
    day = now_ist().date()
    dt = fmt_date(day, 'dow') if dated else ''
    pts = summary_points(caption)
    tail, seed = [], f'{day}-end'
    if len(pts) >= 2:
        tail.append(ic.summary_slide({'date_text': dt, 'points': pts, 'seed': seed}))
    tail.append(ic.follow_slide({'date_text': dt, 'seed': seed}))
    return images[:MAX_SLIDES - len(tail)] + tail


def finish(kind, title, images, caption, report: Report, allowed_numbers=None, meta=None, notify=True):
    """Final checks shared by every post, then hand to Telegram. Returns draft or None."""
    from ..writer import seo
    caption = seo.optimise(kind, caption, (meta or {}).get('topic_keyword'))
    if allowed_numbers is not None:
        body = caption.rsplit('\n\n', 1)[0]                      # hashtags excluded
        check_numbers(body, list(allowed_numbers) + date_numbers(now_ist().date()) + _name_digits(), report)
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
    if len(images) > 1:                                      # carousels end with 'In short' + follow slides
        images = with_closing_slides(images, caption, (meta or {}).get('dated', True))
    hint = f'{kind}-{now_ist().strftime("%H%M%S")}-{secrets.token_hex(2)}'   # unique even for two drafts in one second
    paths = []
    for i, im in enumerate(images):
        rel = store.media_path(hint, i + 1)
        im.convert('RGB').save(store.config.DATA_DIR / rel, 'JPEG', quality=93)
        paths.append(rel)
    d = store.new_draft(kind, paths, caption, captions.threads_text(caption), [list(r) for r in report], meta)
    d['report_text'] = report.text()
    d['topic_keyword'] = seo.topic_keyword(kind, caption) if not (meta or {}).get('topic_keyword') else meta['topic_keyword']
    d['alt_text'] = seo.alt_text(kind, caption, len(paths), d['topic_keyword'])
    auto = store.config.auto_posts(kind) and not any(s == 'warn' for s, _ in report)
    if auto:
        d['status'] = 'auto'                        # approvals job posts it after the cancel window
    store.save_draft(d)
    telegram.send_draft(d, auto=auto)
    log.info('draft %s sent (%s%s)', d['id'], kind, ', auto-post' if auto else '')
    return d


def finish_video(kind, title, video_path, cover, caption, report, allowed_numbers=None, script=None, keyword=None):
    """Same checks as finish(); the reel (mp4) and its cover frame go to Telegram for approval.
    Data reels post by themselves at their slot (Cancel button to stop them) unless a check raised a warning;
    one-off explainer reels wait for your approval."""
    import shutil
    from ..writer import seo
    caption = seo.optimise(kind, caption, keyword)
    if allowed_numbers is not None:
        body = caption.rsplit('\n\n', 1)[0]
        check_numbers(body, list(allowed_numbers) + date_numbers(now_ist().date()) + _name_digits(), report)
    check_banned(caption, report)
    if not report.passed:
        log.warning('BLOCKED %s %s\n%s', kind, title, report.text())
        telegram.send_blocked(kind, title, report.text())
        telegram.send_text(f'⛔ Blocked before review: <b>{kind}</b> - {title}\n\n{report.text()[-1500:]}')
        return None
    import secrets
    hint = f'{kind}-{now_ist().strftime("%H%M%S")}-{secrets.token_hex(2)}'
    cover_rel = store.media_path(hint, 'cover')
    cover.convert('RGB').save(store.config.DATA_DIR / cover_rel, 'JPEG', quality=90)
    vid_rel = str(cover_rel).replace('_cover.jpg', '.mp4')
    shutil.copy(video_path, store.config.DATA_DIR / vid_rel)
    d = store.new_draft(kind, [cover_rel], caption, captions.threads_text(caption), [list(r) for r in report],
                        {'video': vid_rel})
    d['video'] = vid_rel
    d['script'] = script or []
    d['report_text'] = report.text()
    d['topic_keyword'] = keyword or seo.topic_keyword(kind, caption)
    auto = store.config.auto_posts(kind) and not any(s == 'warn' for s, _ in report)
    if auto:
        d['status'] = 'auto'                        # posted at its slot unless you tap Cancel
    store.save_draft(d)
    telegram.send_draft(d, auto=auto)
    log.info('reel draft %s sent (%s%s)', d['id'], kind, ', auto-post' if auto else '')
    return d
