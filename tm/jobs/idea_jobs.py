"""Carousels from an idea.

A) /custompost <name>  - a post researched and written in chat, saved as config/custom_posts/<name>.json.
B) /idea <description> - or a photo with the caption 'idea: ...' - the bot researches the idea itself
   (Gemini with Google Search), writes the slides, checks them and sends a draft. A reference image is only
   used to understand the topic and format; nothing from it is copied.

Both use the same slide spec and render with the regular post designs. Every post waits for your approval.

Spec:
{"label": "Data Story", "title": "cover headline (*gold* words)", "tone": "up|down",
 "cover_stats": [["label", "value text", 1|-1|0], ...],            # up to 3
 "slides": [
   {"type": "bars",   "headline": "...", "sub": "...", "note": "...", "colour": "gold|up|down|sign",
    "rows": [{"name": "...", "value": 123.4, "value_text": "₹123 cr", "side_text": "+4%", "side_sign": 1}]},
   {"type": "list",   "headline": "...", "rows": [["name", "value text", 1|-1|0]]},
   {"type": "table",  "headline": "...", "name_col": "COMPANY", "cols": ["1Y", "3Y"],
    "rows": [{"name": "...", "vals": [12.3, null]}], "note": "..."},
   {"type": "columns","headline": "...", "items": [{"label": "...", "pct": 4.2, "value_text": "+4.2%"}], "note": "..."},
   {"type": "points", "headline": "...", "points": ["...", "..."]}],
 "headline": "caption headline", "paras": ["..."], "tags": ["#..."], "sources": ["title - url", ...]}
"""
import base64
import json
import re
from pathlib import Path

import requests

from .. import config, store, telegram
from ..render import cards, insight_cards as ic
from ..util import fmt_date, now_ist, today_ist
from ..verify.checks import Report, check_banned
from ..writer.captions import assemble, tags as mktags
from .common import finish

CUSTOM_DIR = Path(__file__).resolve().parents[2] / 'config' / 'custom_posts'
TYPES = ('bars', 'list', 'table', 'columns', 'points')


# ---------------------------------------------------------------- rendering (A and B)

def render_spec(spec):
    day = today_ist()
    tone = spec.get('tone') if spec.get('tone') in ('up', 'down') else 'up'
    theme = 'market_up' if tone == 'up' else 'market_down'
    cat = spec.get('label') or 'Data Story'
    base = {'category': cat, 'date_text': fmt_date(day, 'dow'), 'theme': theme, 'tone': tone}
    inside = [re.sub(r'[*]', '', s.get('headline', ''))[:28] for s in spec['slides']][:5]
    stats = [tuple(x) for x in (spec.get('cover_stats') or [])][:3]
    images = [cards.cover({**base, 'day': day, 'headline': spec['title'], 'stats': stats, 'seed': spec['title'],
                           'inside': inside})]
    for i, s in enumerate(spec['slides']):
        data = {**base, 'seed': f'{spec["title"]}-{i}', 'headline': s.get('headline', '')}
        t = s.get('type')
        if t == 'bars':
            images.append(ic.hbars({**data, 'sub': s.get('sub'), 'note': s.get('note'), 'colour': s.get('colour', 'gold'),
                                    'plain': s.get('plain', False), 'rows': s['rows'][:10]}))
        elif t == 'list':
            images.append(ic.list_slide({**data, 'rows': [tuple(r) for r in s['rows'][:10]]}))
        elif t == 'table':
            images.append(ic.score_table({**data, 'cols': s['cols'][:3], 'name_col': s.get('name_col', 'NAME'),
                                          'rows': s['rows'][:10], 'note': s.get('note')}))
        elif t == 'columns':
            images.append(ic.vbars({**data, 'items': s['items'][:10], 'note': s.get('note', '')}))
        elif t == 'points':
            images.append(ic.summary_slide({**data, 'points': s['points'][:6]}))
    return images


def _clean(spec):
    """Keep only slides the renderer understands, with the fields it needs."""
    ok = []
    for s in spec.get('slides') or []:
        t = s.get('type')
        try:
            if t == 'bars':
                s['rows'] = [r for r in s['rows'] if isinstance(r.get('value'), (int, float)) and r.get('name')]
                for r in s['rows']:
                    r.setdefault('value_text', str(r['value']))
                good = len(s['rows']) >= 2
            elif t == 'list':
                s['rows'] = [[str(r[0]), str(r[1]), int(r[2]) if len(r) > 2 else 0] for r in s['rows'] if len(r) >= 2]
                good = len(s['rows']) >= 2
            elif t == 'table':
                good = bool(s.get('cols')) and len(s.get('rows') or []) >= 2
            elif t == 'columns':
                s['items'] = [x for x in s['items'] if isinstance(x.get('pct'), (int, float))]
                for x in s['items']:
                    x.setdefault('value_text', f'{x["pct"]:+.1f}%')
                good = len(s['items']) >= 2
            elif t == 'points':
                s['points'] = [str(p) for p in s.get('points') or [] if str(p).strip()]
                good = len(s['points']) >= 2
            else:
                good = False
        except (KeyError, TypeError, ValueError, IndexError):
            good = False
        if good:
            ok.append(s)
    spec['slides'] = ok[:7]
    return spec


def _spec_numbers(spec):
    """Every number shown on the slides (the caption may only use these)."""
    nums = []
    txt = json.dumps(spec['slides'], ensure_ascii=False) + ' ' + spec.get('title', '') + ' ' + \
        json.dumps(spec.get('cover_stats') or [], ensure_ascii=False)
    for m in re.findall(r'-?\d[\d,]*(?:\.\d+)?', txt):
        try:
            nums.append(abs(float(m.replace(',', ''))))
        except ValueError:
            pass
    return nums


def make_post(spec, report, origin):
    spec = _clean(spec)
    if len(spec['slides']) < 2:
        report.fail('fewer than 2 usable slides')
        telegram.send_text('Could not build the carousel: ' + report.text()[-600:])
        return None
    images = render_spec(spec)
    src = [str(s) for s in spec.get('sources') or []][:6]
    paras = list(spec.get('paras') or [])
    caption = assemble(spec.get('headline') or re.sub(r'[*]', '', spec['title']), paras, '',
                       mktags(*(spec.get('tags') or ['#StockMarketIndia'])))
    if src:
        report.ok('sources: ' + ' | '.join(src))
    report.ok(f'made from: {origin}')
    allowed = _spec_numbers(spec) + [today_ist().day, today_ist().year]
    meta = {'topic_keyword': spec['topic_keyword']} if spec.get('topic_keyword') else None
    return finish('custom_post', spec['title'], images, caption, report, allowed, meta=meta)


# ---------------------------------------------------------------- A) written in chat

def custom_post(force=False):
    import os
    name = os.environ.get('TM_ARG', '').strip()
    files = sorted(p.stem for p in CUSTOM_DIR.glob('*.json'))
    path = CUSTOM_DIR / f'{name}.json'
    if not name or not path.exists():
        telegram.send_text('Custom posts available: ' + (', '.join(files) or 'none yet'))
        return
    spec = json.loads(path.read_text())
    report = Report()
    report.ok('researched and written in chat; sources listed below')
    return make_post(spec, report, f'config/custom_posts/{name}.json')


# ---------------------------------------------------------------- B) researched by the bot

RESEARCH = """You research and design an Instagram carousel for "Ticker Market India", an Indian stock market page.

IDEA FROM THE EDITOR: {idea}
{ref}
Today is {today}. Use Google Search to find CURRENT, verifiable facts (prefer NSE, BSE, RBI, SEBI, company filings,
Economic Times, Moneycontrol, Mint, Business Standard, Reuters). Rules:
- Every number must come from a source you found; give the period/date it refers to in the slide text.
- No advice, tips, targets or predictions ("buy", "should", "will rise" are banned). Facts only.
- India focus. Company names in common short form (e.g. "HDFC Bank", "L&T").
- 4 to 6 content slides. Pick the slide type that fits the data:
  bars (ranked values), list (ranked names with a value), table (name + up to 3 numeric % columns),
  columns (up to 10 items with a % change each), points (2-5 short factual bullet points).
- Cover title max 8 words; mark 1-2 key words with *stars* (shown in gold).

Answer with ONLY a JSON object, no other text:
{{"label": "2-3 word category", "title": "...", "tone": "up|down",
 "cover_stats": [["label", "value text", 1|-1|0]],
 "slides": [
  {{"type": "bars", "headline": "...", "sub": "unit/period", "colour": "gold", "rows": [{{"name": "...", "value": 0.0, "value_text": "..."}}]}},
  {{"type": "list", "headline": "...", "rows": [["name", "value text", 0]]}},
  {{"type": "table", "headline": "...", "name_col": "COMPANY", "cols": ["1Y %", "3Y %"], "rows": [{{"name": "...", "vals": [0.0, 0.0]}}]}},
  {{"type": "columns", "headline": "...", "items": [{{"label": "...", "pct": 0.0, "value_text": "..."}}]}},
  {{"type": "points", "headline": "...", "points": ["..."]}}],
 "headline": "caption headline (plain)", "paras": ["2-4 short factual caption paragraphs using only numbers shown on the slides"],
 "tags": ["#..."], "sources": ["source title - url"]}}"""

CHECK = """You are a strict fact-checker. Below is a carousel spec researched from the web, and the search sources
it used. Flag: numbers that look implausible or inconsistent with each other, wrong dates or periods, company/name
mistakes, misleading wording, and ANY advice or prediction. Answer JSON:
{{"advice_or_prediction": true/false, "serious_problems": ["..."], "minor_notes": ["..."]}}

SOURCES FOUND: {sources}

SPEC:
{spec}"""


def _gemini_raw(parts, tools=None, temperature=0.3):
    from ..writer import llm
    last = ''
    for model in llm.gemini_models()[:3]:
        body = {'contents': [{'parts': parts}], 'generationConfig': {'temperature': temperature}}
        if tools:
            body['tools'] = tools
        try:
            r = requests.post(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
                              params={'key': config.GEMINI_API_KEY}, json=body, timeout=180)
        except requests.RequestException as e:
            last = f'{model}: {type(e).__name__}'
            continue
        if r.status_code != 200:
            last = f'{model}: HTTP {r.status_code} {r.text[:150]}'
            continue
        j = r.json()
        try:
            cand = j['candidates'][0]
            text = ''.join(p.get('text', '') for p in cand['content']['parts'])
        except (KeyError, IndexError):
            last = f'{model}: empty answer'
            continue
        srcs = []
        for ch in (cand.get('groundingMetadata') or {}).get('groundingChunks') or []:
            w = ch.get('web') or {}
            if w.get('uri'):
                srcs.append(f'{w.get("title", "")} - {w["uri"]}')
        return text, srcs
    raise RuntimeError('Gemini research failed: ' + last)


def _describe_reference(file_id):
    """What the reference post is about and how it is laid out - never its text or design to copy."""
    info = telegram._api('getFile', file_id=file_id)
    url = f'https://api.telegram.org/file/bot{config.TELEGRAM_TOKEN}/{info["file_path"]}'
    img = requests.get(url, timeout=60).content
    text, _ = _gemini_raw([
        {'text': 'This is a reference social media post. In 3-5 short lines describe ONLY: its topic, what kind of '
                 'data it shows (ranking, comparison, timeline, explainer...), how many slides/sections it seems to '
                 'have and what each covers. Do not transcribe its numbers or wording.'},
        {'inline_data': {'mime_type': 'image/jpeg', 'data': base64.b64encode(img).decode()}}], temperature=0.2)
    return text.strip()[:800]


def idea_post(force=False):
    import os
    from ..writer import llm
    raw = os.environ.get('TM_ARG', '').strip()
    try:
        arg = json.loads(raw)
    except ValueError:
        arg = {'text': raw}
    idea = (arg.get('text') or '').strip()
    if not idea and not arg.get('file_id'):
        telegram.send_text('Send /idea followed by your idea, or a photo with the caption "idea: ...".')
        return
    report = Report()
    ref = ''
    if arg.get('file_id'):
        try:
            desc = _describe_reference(arg['file_id'])
            ref = f'REFERENCE POST (use only as inspiration for topic and format; do not copy it):\n{desc}\n'
            report.ok('reference image used for topic/format only: ' + desc.replace('\n', ' ')[:200])
        except Exception as e:                        # noqa: BLE001
            report.warn(f'could not read the reference image ({type(e).__name__}) - used the text only')
    text, grounded = _gemini_raw([{'text': RESEARCH.format(idea=idea or 'same topic as the reference post', ref=ref,
                                                           today=fmt_date(today_ist()))}],
                                 tools=[{'google_search': {}}])
    try:
        spec = llm._json(text)
    except ValueError:
        telegram.send_text('Research came back unreadable - please try /idea again or rephrase.')
        return
    spec['sources'] = list(dict.fromkeys((spec.get('sources') or []) + grounded))[:8]
    if not grounded:
        report.warn('Google Search returned no sources for this answer - check every number before approving')
    report.warn('researched by AI from web search - open the sources below and check the numbers before approving')
    try:
        verdict, checker = llm.check(CHECK.format(sources=' | '.join(spec['sources'])[:3000],
                                                  spec=json.dumps(_clean(dict(spec)), ensure_ascii=False)[:9000]),
                                     'gemini')
        if verdict.get('advice_or_prediction'):
            report.fail(f'second opinion ({checker}): advice or prediction found')
        for p in (verdict.get('serious_problems') or [])[:4]:
            report.warn(f'second opinion ({checker}): {p}')
        for p in (verdict.get('minor_notes') or [])[:3]:
            report.ok(f'note ({checker}): {p}')
    except llm.LLMError as e:
        report.warn(f'second opinion unavailable ({str(e)[:80]})')
    check_banned(json.dumps(spec['slides'], ensure_ascii=False), report)
    store.write_json(f'ideas/{now_ist().strftime("%Y%m%d-%H%M%S")}.json', {'idea': idea, 'ref': ref, 'spec': spec})
    d = make_post(spec, report, 'your idea: ' + (idea[:120] or 'reference image'))
    if d is None and report.passed:
        telegram.send_text('The idea post was blocked by the checks - see /flagged.')
