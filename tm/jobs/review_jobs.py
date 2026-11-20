"""Weekly self-review from Instagram Insights (Sunday morning, or /review): ranks last week's posts by saves,
shares and reach, shows which search keywords and formats worked, and suggests 3 changes for next week.
Needs the 'instagram_manage_insights' permission on the token."""
import json
from datetime import datetime, timedelta

import requests

from .. import config, store, telegram
from ..util import log, now_ist

G = f'https://graph.facebook.com/{config.GRAPH_VERSION}'


def _get(path, **p):
    r = requests.get(f'{G}/{path}', params={**p, 'access_token': config.META_PAGE_TOKEN}, timeout=30)
    j = r.json()
    if 'error' in j:
        raise RuntimeError(j['error'].get('message', 'error'))
    return j


def weekly_review(force=False):
    if not (config.META_PAGE_TOKEN and config.IG_USER_ID):
        telegram.send_text('Weekly review: Instagram keys are not set.')
        return
    since = now_ist() - timedelta(days=7)
    try:
        media = _get(f'{config.IG_USER_ID}/media', fields='id,caption,media_product_type,timestamp,permalink',
                     limit=60).get('data', [])
    except RuntimeError as e:
        telegram.send_text(f'Weekly review: could not read posts ({e}).')
        return
    by_id = {}
    for d in store.list_drafts():
        ig = str((d.get('posted') or {}).get('instagram', ''))
        if ig and not ig.startswith('error'):
            by_id[ig] = d
    rows, perm_error = [], None
    for m in media:
        ts = datetime.fromisoformat(m['timestamp'].replace('+0000', '+00:00'))
        if ts < since:
            continue
        try:
            ins = _get(f'{m["id"]}/insights', metric='reach,saved,shares,total_interactions').get('data', [])
        except RuntimeError as e:
            perm_error = str(e)
            continue
        val = {x['name']: (x.get('values') or [{}])[0].get('value', x.get('total_value', {}).get('value', 0)) for x in ins}
        d = by_id.get(m['id'], {})
        rows.append({'kind': d.get('kind', '?'), 'keyword': d.get('topic_keyword', '?'),
                     'format': 'Reel' if m.get('media_product_type') == 'REELS' else 'Carousel/Image',
                     'first_line': (m.get('caption') or '').split('\n')[0][:70], 'time': ts.astimezone(now_ist().tzinfo).strftime('%a %H:%M'),
                     'reach': val.get('reach', 0) or 0, 'saves': val.get('saved', 0) or 0, 'shares': val.get('shares', 0) or 0,
                     'link': m.get('permalink', '')})
    if not rows:
        telegram.send_text('Weekly review: no Insights data. ' + (
            f'Instagram said: {perm_error}. Add the permission "instagram_manage_insights" when you next make the '
            'token, then try /review again.' if perm_error else 'No posts in the last 7 days.'))
        return
    rows.sort(key=lambda r: (r['saves'] + r['shares'], r['reach']), reverse=True)
    lines = [f'{i + 1}. {r["format"]} · {r["keyword"]} · {r["time"]} - reach {r["reach"]}, saves {r["saves"]}, '
             f'shares {r["shares"]}\n   {r["first_line"]}' for i, r in enumerate(rows[:8])]
    msg = f'📊 Weekly review ({len(rows)} posts, ranked by saves + shares, then reach)\n\n' + '\n'.join(lines)
    try:
        from ..writer import llm
        prompt = ('You review an Indian stock market Instagram page. Data for last week posts (reach, saves, shares, '
                  'format, search keyword, posting time IST):\n' + json.dumps(rows, ensure_ascii=False)[:8000] +
                  '\nAnswer JSON {"best_keywords": [..], "best_formats": [..], "changes": ["3 concrete changes for next '
                  'week: keywords, formats and timings"]}. Base every point on the numbers.')
        out = llm.gemini(prompt, temperature=0.3)
        msg += ('\n\nBest keywords: ' + ', '.join(out.get('best_keywords', [])[:4]) +
                '\nBest formats: ' + ', '.join(out.get('best_formats', [])[:3]) +
                '\n\nNext week:\n' + '\n'.join(f'• {c}' for c in out.get('changes', [])[:3]))
    except Exception as e:                           # noqa: BLE001
        log.warning('review suggestions failed: %s', e)
    store.write_json(f'reviews/{now_ist().date()}.json', rows)
    telegram.send_text(msg[:3900])
