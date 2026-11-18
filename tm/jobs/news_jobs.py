"""News posts: discover -> cluster -> AI writes from sources -> code checks every fact -> 2nd AI checks."""
import re

from .. import config, store
from ..render import cards
from ..render.art import as_post
from ..sources import market
from ..sources import news as news_src
from ..util import fmt_date, log, now_ist, today_ist
from ..verify import checks
from ..verify.checks import Report
from ..writer import llm, prompts
from ..writer.captions import assemble
from .common import finish

THEMES = {'banking': 'bank', 'energy': 'solar', 'ipo': 'ipo', 'oil': 'oil', 'gold': 'gold', 'it': 'tech'}
CATEGORIES = {'Market News', 'Earnings', 'IPO Watch', 'Economy', 'Regulation', 'Global Markets', 'Corporate Action'}


def build_from_cluster(c):
    """Returns (images, caption, report, title) - report may contain failures."""
    report = Report()
    checks.check_sources(c, report)
    checks.check_freshness([i['published'] for i in c['items']], report, config.NEWS_MAX_AGE_HOURS)
    if not report.passed:
        return None, None, report, c['lead']['title']
    out, writer = llm.write(prompts.news_prompt(c, fmt_date(today_ist())))
    title = c['lead']['title']
    if not out.get('relevant', False):
        report.fail('writer marked the story as not relevant for the page')
        return None, None, report, title
    headline = str(out.get('headline', '')).strip()
    points = [str(p).strip() for p in out.get('points', [])][:3]
    body = out.get('body') or []
    body = [body] if isinstance(body, str) else [str(b) for b in body][:2]
    hashtags = [h if h.startswith('#') else '#' + h for h in out.get('hashtags', [])][:5]
    category = out.get('category') if out.get('category') in CATEGORIES else 'Market News'
    if not (headline and len(points) >= 2 and body):
        report.fail('writer returned an incomplete draft')
        return None, None, report, title

    label = re.sub(r'[^A-Za-z0-9 &]', '', str(out.get('label') or ''))[:24].strip()
    companies = [str(x) for x in (out.get('companies') or [])][:3]
    src_text = ' '.join(f'{i["title"]} {i["summary"]}' for i in c['items'])
    draft_text = '\n'.join([headline.replace('*', '')] + points + body)
    missing = [x for x in companies if x.lower() not in src_text.lower()]
    if missing:
        report.warn('companies not named in sources, no price box: ' + ', '.join(missing))
        companies = [x for x in companies if x not in missing]
    allowed = checks.source_numbers([src_text])
    for i in c['items']:
        allowed += [i['published'].day, i['published'].year]
    allowed += [today_ist().day, today_ist().year]
    for yr in range(2020, 2036):                       # 'CY27', 'FY27', '2027' in a source all allow 2027
        if re.search(r'(?<!\d)(?:20)?' + str(yr)[2:] + r'(?!\d)', src_text) and re.search(r'(?i)(fy|cy|20|\')' + str(yr)[2:] + r'(?!\d)', src_text):
            allowed.append(yr)
    checks.check_numbers(draft_text + '\n' + label, allowed, report, 'headline/banner/points/body')
    checks.check_names(draft_text, src_text, report)
    checks.check_months(draft_text, src_text, report)
    checks.check_fiscal(draft_text, src_text, report)
    if label:
        lab = checks.Report(); checks.check_banned(label, lab)
        if not lab.passed:
            report.fail(f'banner text not allowed: {label}')
    if not report.passed:
        return None, None, report, title

    # second opinion from the other model
    try:
        verdict, checker = llm.check(prompts.check_prompt(draft_text, c), writer)
        ok = verdict.get('all_supported') and not verdict.get('misleading') and not verdict.get('advice_or_prediction')
        if ok:
            report.ok(f'second opinion ({checker}): every fact supported, not misleading, no advice')
        else:
            report.fail(f'second opinion ({checker}): ' + '; '.join(verdict.get('issues') or ['rejected']))
    except llm.LLMError as e:
        msg = f'second opinion unavailable ({str(e)[:80]}) - code checks passed, please read before approving'
        report.fail(msg) if config.REQUIRE_SECOND_OPINION else report.warn(msg)
    if not report.passed:
        return None, None, report, title

    outlets = ', '.join(c['outlets'][:3])
    newest = max(i['published'] for i in c['items'])
    quotes = market.company_quotes(companies, report)
    tone = out.get('tone') if out.get('tone') in ('up', 'down') else None
    if quotes:                                      # the prices decide the colour, not the AI
        net = sum(q['pct'] for q in quotes)
        tone = 'up' if net > 0 else 'down' if net < 0 else tone
    sector = str(out.get('sector') or 'other').lower()
    theme = THEMES.get(sector) or ('market_down' if tone == 'down' else 'market_up')
    from ..render import photo
    scene = re.sub(r'[0-9"]', '', str(out.get('image_scene') or ''))[:220].strip()
    names = [n.lower() for n in companies]
    if not scene or any(n and n in scene.lower() for n in names):      # never a company name in the picture
        scene = photo.SECTOR_SCENES.get(sector) or photo.SECTOR_SCENES['economy']
    photo.PHOTO_PROMPT = scene
    try:
        images = cards.news_hero({'category': category, 'date_text': fmt_date(newest.date(), 'dow'), 'theme': theme,
                                  'seed': c['key'], 'tone': tone, 'quotes': quotes, 'label': label,
                                  'headline': headline, 'points': points,
                                  'source': ('NSE prices, ' if quotes else '') + outlets})
    finally:
        photo.PHOTO_PROMPT = None
    outlets = ('NSE prices, ' if quotes else '') + outlets
    caption = assemble(headline, body, outlets, hashtags)
    report.ok(f'written by {writer}; sources: ' + ' | '.join(i['link'] or i['outlet'] for i in c['items'][:4]))
    return images, caption, report, title


@as_post('news')
def news(force=False, limit=None):
    from datetime import datetime, timedelta
    last = store.get_flag('last_news_run')
    if last and not force and now_ist() - datetime.fromisoformat(last) < timedelta(minutes=50):
        log.info('news ran at %s - skipping duplicate trigger', last)
        return 0
    store.set_flag('last_news_run', now_ist().isoformat())
    limit = limit or config.NEWS_PER_RUN
    items, status = news_src.fetch_all()
    log.info('feeds: %s', status)
    clusters = [c for c in news_src.cluster(items) if not store.seen('news', c['key'])]
    made, tried, blocked = 0, 0, []
    for c in clusters:
        if made >= limit or tried >= limit * 5:
            break
        if not c['confirmed']:
            continue
        tried += 1
        try:
            images, caption, report, title = build_from_cluster(c)
        except llm.LLMError as e:
            log.error('LLM unavailable: %s', e)
            try:
                from .. import telegram
                telegram.send_text(f'📰 News run skipped: the AI writers did not respond ({str(e)[:150]}). '
                                   f'Stories stay in the queue for the next run.')
            except Exception:                        # noqa: BLE001
                pass
            break
        store.mark_seen('news', c['key'], {'title': c['lead']['title']})
        if images is None:
            finish('news', title, [], '', report, notify=False)
            blocked.append((title, next((m for st, m in report if st == 'fail'), 'blocked')))
            continue
        if finish('news', title, images, caption, report, allowed_numbers=None):
            made += 1
    log.info('news run: %s drafts from %s candidates', made, tried)
    if blocked:
        try:
            from .. import telegram
            import html
            lines = '\n'.join(f'• {html.escape(t[:70])}\n   <i>{html.escape(r[:110])}</i>' for t, r in blocked[:6])
            telegram.send_text(f'📰 News run: {made} draft(s) sent, {len(blocked)} story(ies) blocked by checks:\n\n'
                               f'{lines}\n\nFull details: /flagged')
        except Exception as e:                       # noqa: BLE001
            log.warning('summary not sent: %s', e)
    return made
