"""Post card templates (1080x1350, Instagram 4:5).

Every number drawn here is passed in as data. Percentages and totals are computed here
from the inputs, never typed by hand or by the AI.
"""
import re

from PIL import Image, ImageDraw, ImageFont

from .. import config
from ..util import fmt_inr, pct_change

W, H = 1080, 1350
BG = (3, 10, 23)
PANEL = (14, 22, 40)
PANEL2 = (9, 16, 31)       # alternate table rows: still solid, so no background shows through
GRID = (9, 17, 33)
LINE = (38, 50, 74)
WHITE = (255, 255, 255)
MUTED = (150, 162, 185)
GOLD = (251, 183, 9)
UP = (22, 199, 132)
DOWN = (234, 57, 67)
FLAT = (120, 130, 150)
SAF, GRN = (255, 153, 51), (30, 170, 60)

FONTS = config.ROOT / 'assets' / 'fonts'
_cache = {}


def _font(name, size):
    k = (name, size)
    if k not in _cache:
        _cache[k] = ImageFont.truetype(str(FONTS / name), size)
    return _cache[k]


def bebas(s): return _font('BebasNeue-Regular.ttf', s)
def cond(s): return _font('BarlowCondensed-Bold.ttf', s)
def hind(s, w='Medium'): return _font(f'Hind-{w}.ttf', s)


_logo = None


def logo():
    global _logo
    if _logo is None:
        _logo = Image.open(config.ROOT / config.BRAND['logo']).convert('RGBA')
    return _logo


def name_of(r):
    if r.get('name'):
        return r['name']
    from ..sources.names import short
    return short(r.get('symbol', ''))


def fit(d, text, size, max_w, weight='SemiBold', min_size=22):
    f = hind(size, weight)
    while d.textlength(text, font=f) > max_w and size > min_size:
        size -= 1
        f = hind(size, weight)
    return f


def col(v):
    return UP if v > 0 else DOWN if v < 0 else FLAT


# ---------------------------------------------------------------- % colouring: gains green, falls red, everywhere
PCT = re.compile(r'^[(\[]?([+\-\u2212])?\d[\d,]*(?:\.\d+)?%')
DOWN_WORDS = {'down', 'fell', 'falls', 'fall', 'falling', 'lower', 'loser', 'losers', 'declined', 'declines', 'drop',
              'drops', 'dropped', 'slipped', 'slips', 'plunges', 'plunged', 'sank', 'sinks', 'lost', 'loses', 'loss',
              'weakest', 'worst', 'tumbles', 'tumbled', 'crashes', 'crashed', 'shed', 'sheds', 'cut', 'slumps'}
UP_WORDS = {'up', 'rose', 'rises', 'rise', 'rising', 'gain', 'gains', 'gained', 'higher', 'gainer', 'gainers',
            'advanced', 'jumps', 'jumped', 'surges', 'surged', 'soars', 'soared', 'climbs', 'climbed', 'rallies',
            'rallied', 'best', 'added', 'adds', 'grew', 'growth'}


def pct_colour(words, i):
    """Colour for words[i] if it is a percentage move: sign first, else the nearest up/down word before it."""
    w = words[i].strip('*')
    m = PCT.match(w)
    if not m:
        return None
    if m.group(1):
        return UP if m.group(1) == '+' else DOWN
    for prev in reversed(words[max(0, i - 4):i]):
        p = prev.lower().strip('*,.;:()[]')
        if p in DOWN_WORDS:
            return DOWN
        if p in UP_WORDS:
            return UP
    return None


def sign_of(text, default=0):
    """+1/-1 from the first signed % in a text (for tiles), else default."""
    m = re.search(r'([+\-\u2212])\d[\d,]*(?:\.\d+)?%', text)
    return default if not m else (1 if m.group(1) == '+' else -1)


def rich_text(d, x, y, text, font, max_w, fill, line_h, y_limit=None):
    """Wrapped text drawn word by word with % moves coloured. Returns y after the last line."""
    words = text.split()
    cols = [pct_colour(words, i) or fill for i in range(len(words))]
    space = d.textlength(' ', font=font)
    cx = x
    for w, c in zip(words, cols):
        ww = d.textlength(w, font=font)
        if cx > x and cx + ww > x + max_w:
            cx, y = x, y + line_h
            if y_limit and y > y_limit:
                return y
        d.text((cx, y), w, font=font, fill=c)
        cx += ww + space
    return y + line_h


# ---------------------------------------------------------------- building blocks

def base(category, date_text, sample=False, theme=None, seed=0, dim=0.0, tone=None):
    """theme: background art (see art.py). dim: 0-1 darkening for cards whose text sits on the art."""
    if theme:
        from .art import background
        im = background(theme, W, H, seed, tone)
        if dim:                                   # content slides: blur + darken so nothing in the art competes with data
            from PIL import ImageFilter
            im = im.filter(ImageFilter.GaussianBlur(22))
            im = Image.blend(im, Image.new('RGB', (W, H), BG), max(dim, 0.62))
    else:
        im = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(im)
    if not theme:
        for x in range(0, W, 90):
            d.line([(x, 0), (x, H)], fill=GRID)
        for y in range(0, H, 90):
            d.line([(0, y), (W, y)], fill=GRID)
    if config.BRAND.get('tricolour_strip'):
        d.rectangle([0, 0, W // 3, 6], fill=SAF)
        d.rectangle([W // 3, 0, 2 * W // 3, 6], fill=WHITE)
        d.rectangle([2 * W // 3, 0, W, 6], fill=GRN)
    else:
        d.rectangle([0, 0, W, 6], fill=GOLD)
    f = cond(30)
    tw = d.textlength(category.upper(), font=f)
    d.rounded_rectangle([60, 52, 60 + tw + 40, 102], radius=8, fill=GOLD)
    d.text((80, 77), category.upper(), font=f, fill=BG, anchor='lm')
    d.text((W - 60, 77), date_text.upper(), font=cond(34), fill=WHITE, anchor='rm')
    if sample:
        txt = 'SAMPLE  -  ILLUSTRATIVE NUMBERS, NOT REAL DATA'
        sf = cond(24)
        sw = d.textlength(txt, font=sf)
        d.rounded_rectangle([(W - sw) / 2 - 16, 118, (W + sw) / 2 + 16, 152], radius=6, outline=DOWN, width=2)
        d.text((W / 2, 135), txt, font=sf, fill=DOWN, anchor='mm')
    return im, d


def footer(im, d, source, swipe=False, page=None):
    y = H - 150
    d.line([(60, y), (W - 60, y)], fill=LINE, width=2)
    d.text((60, y + 52), 'For information only. Not investment advice.', font=hind(24, 'Regular'), fill=MUTED, anchor='lm')
    lg = logo()
    lg = lg.resize((230, int(lg.height * 230 / lg.width)), Image.LANCZOS)
    im.paste(lg, (W - 60 - lg.width, y + 16), lg)
    d.text((W - 60, y + 26 + lg.height), config.BRAND['handle'], font=hind(22, 'SemiBold'), fill=MUTED, anchor='ra')
    if swipe:  # minimal swipe hint so viewers know there are more slides
        cx, cy = W // 2 + 40, y - 34
        d.text((cx - 16, cy), 'SWIPE', font=cond(26), fill=GOLD, anchor='rm')
        d.polygon([(cx, cy - 10), (cx + 16, cy), (cx, cy + 10)], fill=GOLD)
        d.polygon([(cx + 12, cy - 10), (cx + 28, cy), (cx + 12, cy + 10)], fill=GOLD)
    if page:
        d.text((W - 60, y - 34), page, font=cond(26), fill=MUTED, anchor='rm')


def _tokens(text):
    text = re.sub(r'\*\s*([;:,.!?%])', r'\1*', text)       # keep punctuation inside the highlight
    out = []
    for part in re.split(r'(\*[^*]+\*)', text):
        if not part:
            continue
        hi = part.startswith('*')
        for w in part.strip('*').split():
            out.append((w, hi))
    return out


def scrim(im, y0, y1, alpha=170):
    """Dark band so text stays readable over background art."""
    band = Image.new('RGBA', (W, y1 - y0), BG + (alpha,))
    base_im = im if im.mode == 'RGBA' else im.convert('RGBA')
    base_im.alpha_composite(band, (0, y0))
    return base_im


def headline(d, text, y, size=96, max_w=960, line_gap=0.98, max_lines=3):
    """Bebas headline; *starred* words in gold. Shrinks to fit max_lines."""
    while True:
        f = bebas(size)
        space = d.textlength(' ', font=f)
        lines, cur, cur_w = [], [], 0
        for w, hi in _tokens(text):
            ww = d.textlength(w, font=f)
            if cur and cur_w + space + ww > max_w:
                lines.append(cur); cur, cur_w = [], 0
            cur.append((w, hi)); cur_w += (space if cur_w else 0) + ww
        if cur:
            lines.append(cur)
        if len(lines) <= max_lines or size <= 60:
            break
        size -= 6
    flat = [w for line in lines for w, _ in line]
    cols = iter([pct_colour(flat, i) for i in range(len(flat))])
    for line in lines:
        x = 60
        for w, hi in line:
            c = next(cols)
            d.text((x, y), w, font=f, fill=c or (GOLD if hi else WHITE))
            x += d.textlength(w, font=f) + space
        y += int(size * line_gap)
    return y


def arrow(d, x, y, v, size=22):
    if v > 0:
        d.polygon([(x, y + size), (x + size, y + size), (x + size / 2, y)], fill=UP)
    elif v < 0:
        d.polygon([(x, y), (x + size, y), (x + size / 2, y + size)], fill=DOWN)
    else:
        d.rectangle([x, y + size / 2 - 3, x + size, y + size / 2 + 3], fill=FLAT)


def wrap(d, text, font, max_w):
    words, line, lines = text.split(), '', []
    for w in words:
        t = (line + ' ' + w).strip()
        if d.textlength(t, font=font) > max_w and line:
            lines.append(line); line = w
        else:
            line = t
    if line:
        lines.append(line)
    return lines


def bullets(d, items, y, size=34, max_w=900, y_limit=H - 190):
    f = hind(size)
    lh = int(size * 1.35)
    for it in items:
        lines = wrap(d, it, f, max_w)
        if y + len(lines) * lh > y_limit:
            break
        d.rounded_rectangle([60, y + 14, 74, y + 28], radius=3, fill=GOLD)
        y = rich_text(d, 100, y, it, f, max_w, WHITE, lh) + 16
    return y


def section(d, title, y):
    d.text((60, y), title.upper(), font=cond(36), fill=GOLD)
    return y + 58


# ---------------------------------------------------------------- templates

def market_close(data):
    """data: date_text, headline, indices[{name, close, chg}], drivers[], source"""
    up = data['indices'][0]['chg'] >= 0
    im, d = base('Market Close', data['date_text'], data.get('sample'), data.get('theme'), data.get('seed', 0), 0.25,
                 'up' if up else 'down')
    if data.get('theme'):
        im = scrim(im, 175, 400, 150); d = ImageDraw.Draw(im)
    y = headline(d, data['headline'], 190) + 30
    tile_h = 168
    for idx in data['indices'][:3]:
        v = idx['chg']
        d.rounded_rectangle([60, y, W - 60, y + tile_h - 18], radius=16, fill=PANEL)
        d.rectangle([60, y, 70, y + tile_h - 18], fill=col(v))
        d.text((100, y + 42), idx['name'], font=cond(38), fill=MUTED, anchor='lm')
        d.text((100, y + 100), fmt_inr(idx['close']), font=bebas(84), fill=WHITE, anchor='lm')
        pct = pct_change(idx['close'], v)
        sign = '+' if v >= 0 else ''
        d.text((W - 100, y + 62), f'{sign}{fmt_inr(v)}', font=bebas(64), fill=col(v), anchor='rm')
        d.text((W - 100, y + 118), f'{sign}{pct:.2f}%', font=hind(36, 'SemiBold'), fill=col(v), anchor='rm')
        arrow(d, W - 360, y + 50, v, 26)
        y += tile_h
    if data.get('drivers'):
        y = section(d, 'What moved the market', y + 20)
        bullets(d, data['drivers'], y, size=34)
    footer(im, d, data['source'])
    return [im.convert('RGB')]


def daily_overview(data):
    """4-slide carousel. data: date_text, headline, indices[], breadth, sectors[{name,pct}],
    gainers[{symbol,last,pct}], losers[...], extras[{name,value,pct}], source"""
    slides = []
    # 1 - indices
    im, d = base('Daily Market Overview', data['date_text'], data.get('sample'), data.get('theme'), data.get('seed', 0), 0.35, data.get('tone'))
    if data.get('theme'):
        im = scrim(im, 175, 400, 150); d = ImageDraw.Draw(im)
    y = headline(d, data['headline'], 190, size=90) + 26
    rh = 92
    for i, q in enumerate(data['indices'][:6]):
        d.rounded_rectangle([60, y, W - 60, y + rh - 8], radius=10, fill=PANEL if i % 2 == 0 else PANEL2)
        pct = pct_change(q['close'], q['chg'])
        d.text((90, y + 42), q['name'], font=hind(34, 'SemiBold'), fill=WHITE, anchor='lm')
        d.text((690, y + 42), fmt_inr(q['close']), font=bebas(52), fill=WHITE, anchor='rm')
        arrow(d, 740, y + 30, q['chg'], 22)
        d.text((W - 90, y + 42), f'{pct:+.2f}%', font=bebas(52), fill=col(q['chg']), anchor='rm')
        y += rh
    b = data.get('breadth')
    if b and y < H - 330:
        y = section(d, f'Market breadth ({b["universe"]})', y + 24)
        tot = b['advances'] + b['declines']
        bw = W - 120
        aw = int(bw * b['advances'] / tot) if tot else bw // 2
        d.rounded_rectangle([60, y, 60 + aw, y + 34], radius=8, fill=UP)
        d.rounded_rectangle([60 + aw + 6, y, W - 60, y + 34], radius=8, fill=DOWN)
        d.text((60, y + 70), f'{b["advances"]} advanced', font=hind(30, 'SemiBold'), fill=UP, anchor='lm')
        d.text((W - 60, y + 70), f'{b["declines"]} declined', font=hind(30, 'SemiBold'), fill=DOWN, anchor='rm')
    footer(im, d, data['source'], swipe=True)
    slides.append(im.convert('RGB'))

    # 2 - sectors
    if data.get('sectors'):
        im, d = base('Sector Performance', data['date_text'], data.get('sample'))
        y = headline(d, data.get('sector_headline', 'How the *sectors* performed'), 190, size=88) + 30
        secs = sorted(data['sectors'], key=lambda s: s['pct'], reverse=True)[:12]
        mx = max(abs(s['pct']) for s in secs) or 1
        mid = W // 2 + 80
        half = W - 60 - mid - 110
        rh = min(70, (H - 200 - y) // len(secs))
        for s in secs:
            ln = int(half * abs(s['pct']) / mx)
            cy = y + rh // 2
            d.text((60, cy), s['name'], font=hind(30, 'SemiBold'), fill=WHITE, anchor='lm')
            if s['pct'] >= 0:
                d.rounded_rectangle([mid, cy - 16, mid + max(ln, 4), cy + 16], radius=6, fill=UP)
                d.text((mid + max(ln, 4) + 14, cy), f'{s["pct"]:+.2f}%', font=bebas(40), fill=UP, anchor='lm')
            else:
                d.rounded_rectangle([mid - max(ln, 4), cy - 16, mid, cy + 16], radius=6, fill=DOWN)
                d.text((mid + 14, cy), f'{s["pct"]:+.2f}%', font=bebas(40), fill=DOWN, anchor='lm')
            y += rh
        d.line([(mid, 400), (mid, y)], fill=LINE, width=2)
        footer(im, d, data['source'])
        slides.append(im)

    # 3 - gainers / losers
    if data.get('gainers') and data.get('losers'):
        slides.append(movers_slide('Top Movers', data['date_text'], data.get('movers_headline', '*Nifty 50* top gainers and losers'),
                                   data['gainers'], data['losers'], data['source'], sample=data.get('sample')))

    # 4 - rupee, commodities, volatility
    if data.get('extras'):
        im, d = base('Currency & Commodities', data['date_text'], data.get('sample'))
        y = headline(d, data.get('extras_headline', '*Rupee*, crude, gold and volatility'), 190, size=88) + 30
        for i, r in enumerate(data['extras']):
            d.rounded_rectangle([60, y, W - 60, y + 100], radius=12, fill=PANEL if i % 2 == 0 else PANEL2)
            d.text((90, y + 50), r['name'], font=hind(36, 'SemiBold'), fill=WHITE, anchor='lm')
            d.text((690, y + 50), r['value'], font=bebas(58), fill=WHITE, anchor='rm')
            arrow(d, 740, y + 38, r['pct'], 24)
            d.text((W - 90, y + 50), f'{r["pct"]:+.2f}%', font=bebas(58), fill=col(r['pct']), anchor='rm')
            y += 108
        footer(im, d, data['source'])
        slides.append(im)
    return slides


def fii_dii(data):
    """data: date_text, headline, rows[{date, fii, dii} | {date, holiday}], source"""
    im, d = base('FII / DII Data', data['date_text'], data.get('sample'), data.get('theme'), data.get('seed', 0), 0.35, data.get('tone'))
    if data.get('theme'):
        im = scrim(im, 175, 400, 150); d = ImageDraw.Draw(im)
    y = headline(d, data['headline'], 190, size=88) + 24
    cols = [100, 560, W - 100]
    d.rounded_rectangle([60, y, W - 60, y + 70], radius=12, fill=GOLD)
    for x, t, a in zip(cols, ['DATE', 'FII NET (₹ CR)', 'DII NET (₹ CR)'], ['lm', 'mm', 'rm']):
        d.text((x, y + 37), t, font=bebas(40), fill=BG, anchor=a)
    y += 82
    rows = data['rows']
    rh = 96 if len(rows) <= 6 else max(58, int((H - 420 - y) / len(rows)))
    fs = 40 if rh >= 90 else 34
    fii_t = dii_t = 0
    for i, r in enumerate(rows):
        d.rectangle([60, y, W - 60, y + rh], fill=PANEL if i % 2 == 0 else PANEL2)
        d.text((cols[0], y + rh // 2), r['date'], font=hind(fs - 2, 'SemiBold'), fill=WHITE, anchor='lm')
        if r.get('holiday'):
            d.text((W / 2 + 100, y + rh // 2), 'Market holiday', font=hind(fs - 4), fill=MUTED, anchor='mm')
        else:
            for x, v, a in ((cols[1], r['fii'], 'mm'), (cols[2], r['dii'], 'rm')):
                d.text((x, y + rh // 2), ('+' if v >= 0 else '') + fmt_inr(v), font=hind(fs, 'Bold'), fill=col(v), anchor=a)
            fii_t += r['fii']; dii_t += r['dii']
        y += rh
    if data.get('show_total', True) and len([r for r in rows if not r.get('holiday')]) > 1:
        y += 12
        d.rounded_rectangle([60, y, W - 60, y + 100], radius=12, outline=GOLD, width=3)
        d.text((cols[0], y + 52), data.get('total_label', 'TOTAL'), font=bebas(56), fill=GOLD, anchor='lm')
        for x, v, a in ((cols[1], fii_t, 'mm'), (cols[2], dii_t, 'rm')):
            d.text((x, y + 52), ('+' if v >= 0 else '') + fmt_inr(v), font=bebas(64), fill=col(v), anchor=a)
        y += 100
    fno = data.get('fno')
    if fno and y < H - 470:
        y = section(d, 'FII positions in F&O (contracts)', y + 28)
        # long/short bar for index futures
        lp = fno['idx_fut_long_pct']
        bw = W - 120
        lw = int(bw * lp / 100)
        d.rounded_rectangle([60, y, 60 + max(lw, 8), y + 40], radius=8, fill=UP)
        d.rounded_rectangle([60 + lw + 6, y, W - 60, y + 40], radius=8, fill=DOWN)
        d.text((60, y + 70), f'Index futures: {lp:.1f}% long', font=hind(30, 'SemiBold'), fill=UP, anchor='lm')
        d.text((W - 60, y + 70), f'{100 - lp:.1f}% short', font=hind(30, 'SemiBold'), fill=DOWN, anchor='rm')
        y += 104
        tiles = [('Index futures net', fno['idx_fut_net'], fno.get('idx_fut_net_chg')),
                 ('Stock futures net', fno['stk_fut_net'], None),
                 ('Index calls net', fno['idx_call_net'], None),
                 ('Index puts net', fno['idx_put_net'], None)]
        tw, th = (W - 150) // 2, 118
        for i, (k, v, chg) in enumerate(tiles):
            x = 60 + (i % 2) * (tw + 30); yy = y + (i // 2) * (th + 16)
            if yy + th > H - 170:
                break
            d.rounded_rectangle([x, yy, x + tw, yy + th], radius=14, fill=PANEL)
            d.text((x + 24, yy + 30), k.upper(), font=cond(26), fill=MUTED, anchor='lm')
            d.text((x + 24, yy + 80), ('+' if v >= 0 else '') + fmt_inr(v, 0), font=bebas(52), fill=col(v), anchor='lm')
            if chg is not None:
                d.text((x + tw - 20, yy + 84), f'{"+" if chg >= 0 else ""}{fmt_inr(chg, 0)} vs prev', font=hind(22),
                       fill=MUTED, anchor='rm')
    footer(im, d, data['source'])
    return [im.convert('RGB')], {'fii_total': round(fii_t, 2), 'dii_total': round(dii_t, 2)}


def ipo(data):
    """data: date_text, headline, company, segment, tiles[(label, value)] (6), timeline[(label, value)], source"""
    im, d = base('IPO Watch', data['date_text'], data.get('sample'), data.get('theme'), data.get('seed', 0), 0.2, 'up')
    if data.get('theme'):
        from . import widgets
        im = im.convert('RGBA')
        im.alpha_composite(widgets.company_badge(data['company'], data['segment'], 700), (60, 180))
        im = scrim(im, 370, 590, 170)
        d = ImageDraw.Draw(im)
        y = headline(d, data['headline'], 400, size=92) + 20
    else:
        y = headline(d, data['headline'], 190, size=92) + 20
        d.text((60, y), data['company'], font=hind(40, 'Bold'), fill=WHITE)
        d.text((60, y + 54), data['segment'], font=hind(30), fill=MUTED)
        y += 120
    tw, th = (W - 150) // 2, 130
    for i, (k, v) in enumerate(data['tiles'][:6]):
        x = 60 + (i % 2) * (tw + 30); yy = y + (i // 2) * (th + 20)
        d.rounded_rectangle([x, yy, x + tw, yy + th], radius=14, fill=PANEL)
        d.text((x + 28, yy + 36), k.upper(), font=cond(28), fill=MUTED, anchor='lm')
        d.text((x + 28, yy + 88), v, font=bebas(56), fill=WHITE, anchor='lm')
    y += ((len(data['tiles'][:6]) + 1) // 2) * (th + 20) + 20
    steps = data.get('timeline') or []
    if len(steps) >= 2:
        y = section(d, 'Key dates', y) + 12
        x0, x1 = 110, W - 110
        d.line([(x0, y), (x1, y)], fill=LINE, width=4)
        for i, (k, v) in enumerate(steps):
            x = x0 + (x1 - x0) * i / (len(steps) - 1)
            d.ellipse([x - 13, y - 13, x + 13, y + 13], fill=GOLD)
            d.text((x, y + 34), v, font=hind(28, 'Bold'), fill=WHITE, anchor='mm')
            d.text((x, y + 70), k, font=hind(24), fill=MUTED, anchor='mm')
    footer(im, d, data['source'])
    return [im.convert('RGB')]


def global_cues(data):
    """data: date_text, headline, rows[{name, value, pct}], notes[], source"""
    im, d = base('Global Cues', data['date_text'], data.get('sample'), data.get('theme'), data.get('seed', 0), 0.3, data.get('tone'))
    if data.get('theme'):
        im = scrim(im, 175, 400, 150); d = ImageDraw.Draw(im)
    y = headline(d, data['headline'], 190, size=92) + 24
    rh = 84
    for i, r in enumerate(data['rows'][:8]):
        d.rounded_rectangle([60, y, W - 60, y + rh - 8], radius=10, fill=PANEL if i % 2 == 0 else PANEL2)
        d.text((90, y + 38), r['name'], font=hind(36, 'SemiBold'), fill=WHITE, anchor='lm')
        d.text((640, y + 38), r['value'], font=bebas(52), fill=WHITE, anchor='rm')
        arrow(d, 760, y + 26, r['pct'], 24)
        d.text((W - 90, y + 38), f'{r["pct"]:+.2f}%', font=bebas(52), fill=col(r['pct']), anchor='rm')
        y += rh
    if data.get('notes'):
        y = section(d, 'What changed overnight', y + 22)
        bullets(d, data['notes'], y, size=32)
    footer(im, d, data['source'])
    return [im.convert('RGB')]


def day_ahead(data):
    """data: date_text, headline, groups[(title, [lines])], source"""
    im, d = base('Market Day Ahead', data['date_text'], data.get('sample'), data.get('theme'), data.get('seed', 0), 0.35, data.get('tone'))
    if data.get('theme'):
        im = scrim(im, 175, 400, 150); d = ImageDraw.Draw(im)
    y = headline(d, data['headline'], 190, size=90) + 20
    for title, lines in data['groups']:
        if not lines or y > H - 330:
            continue
        y = section(d, title, y + 10)
        for ln in lines[:6]:
            if y > H - 230:
                break
            d.rounded_rectangle([60, y, W - 60, y + 60], radius=10, fill=PANEL)
            d.text((90, y + 31), ln, font=hind(30, 'SemiBold'), fill=WHITE, anchor='lm')
            y += 70
    footer(im, d, data['source'])
    return [im.convert('RGB')]


def news(data):
    """data: category, date_text, headline, points[], outlets[], source"""
    im, d = base(data['category'], data['date_text'], data.get('sample'))
    y = headline(d, data['headline'], 200, size=100, max_lines=4) + 40
    for p in data['points'][:3]:
        f = hind(36, 'SemiBold')
        lines = wrap(d, p, f, W - 220)
        h = 40 + len(lines) * 50
        if y + h > H - 200:
            break
        d.rounded_rectangle([60, y, W - 60, y + h], radius=14, fill=PANEL)
        d.rectangle([60, y, 70, y + h], fill=GOLD)
        yy = y + 22
        for ln in lines:
            d.text((100, yy), ln, font=f, fill=WHITE)
            yy += 50
        y += h + 22
    footer(im, d, data['source'])
    return [im]


def movers_slide(category, date_text, head, gainers, losers, source, swipe=False, sample=False, note=None):
    im, d = base(category, date_text, sample)
    y = headline(d, head, 190, size=88, max_lines=2) + 24
    for title, rows, c in (('Top gainers', gainers, UP), ('Top losers', losers, DOWN)):
        y = section(d, title, y)
        if not rows:
            d.text((60, y + 20), 'No stock in this group closed ' + ('higher' if c == UP else 'lower'),
                   font=hind(30), fill=MUTED)
            y += 90
            continue
        # fit 5 rows per group between the headline and the footer
        step = min(76, (H - 200 - y - 58 - 18) // (2 * 5) * 2 // 2) if title == 'Top gainers' else step
        for r in rows[:5]:
            rh = step - 10
            d.rounded_rectangle([60, y, W - 60, y + rh], radius=10, fill=PANEL)
            d.rectangle([60, y, 68, y + rh], fill=c)
            d.text((96, y + rh // 2), name_of(r), font=fit(d, name_of(r), 32, 380), fill=WHITE, anchor='lm')
            d.text((690, y + rh // 2), '₹' + fmt_inr(r['last']), font=hind(32, 'SemiBold'), fill=MUTED, anchor='rm')
            d.text((W - 90, y + rh // 2), f'{r["pct"]:+.2f}%', font=bebas(48), fill=c, anchor='rm')
            y += step
        y += 18
    footer(im, d, source, swipe=swipe)
    return im


def cap_movers(data):
    """Cover + one slide per segment. data: date_text, headline, segments[{name, index, gainers, losers}], source"""
    segs = data['segments']
    im, d = base('Gainers & Losers', data['date_text'], data.get('sample'), data.get('theme'), data.get('seed', 0), 0.35, data.get('tone'))
    if data.get('theme'):
        im = scrim(im, 175, 400, 150); d = ImageDraw.Draw(im)
    y = headline(d, data['headline'], 190, size=90) + 26
    th = 196
    for sg in segs:
        d.rounded_rectangle([60, y, W - 60, y + th - 18], radius=16, fill=PANEL)
        d.text((90, y + 40), sg['name'].upper(), font=bebas(52), fill=GOLD, anchor='lm')
        d.text((W - 90, y + 40), sg['index'], font=cond(28), fill=MUTED, anchor='rm')
        for k, (lab, rows, c) in enumerate((('Top gainer', sg['gainers'], UP), ('Top loser', sg['losers'], DOWN))):
            yy = y + 92 + k * 50
            d.text((90, yy), lab, font=hind(28), fill=MUTED, anchor='lm')
            if rows:
                d.text((330, yy), name_of(rows[0]), font=fit(d, name_of(rows[0]), 32, 330), fill=WHITE, anchor='lm')
                d.text((W - 90, yy), f'{rows[0]["pct"]:+.2f}%', font=bebas(46), fill=c, anchor='rm')
            else:
                d.text((330, yy), '-', font=hind(32), fill=MUTED, anchor='lm')
        y += th
    footer(im, d, data['source'], swipe=True)
    slides = [im.convert('RGB')]
    for i, sg in enumerate(segs):
        slides.append(movers_slide(sg['name'], data['date_text'],
                                   f'*{sg["name"]}* movers ({sg["index"].title()})',
                                   sg['gainers'], sg['losers'], data['source'], sample=data.get('sample')))
    return slides


def extremes_slide(category, date_text, head, rows, kind, source, empty_text, sample=False):
    """Up to 10 stocks: symbol | new high/low level | week % change."""
    im, d = base(category, date_text, sample)
    y = headline(d, head, 190, size=88, max_lines=2) + 20
    level_label = 'NEW HIGH' if kind == 'ath' else '52W LOW'
    d.text((96, y + 18), 'STOCK', font=cond(26), fill=MUTED, anchor='lm')
    d.text((690, y + 18), level_label, font=cond(26), fill=MUTED, anchor='rm')
    d.text((W - 90, y + 18), 'WEEK', font=cond(26), fill=MUTED, anchor='rm')
    y += 44
    if not rows:
        d.text((60, y + 40), empty_text, font=hind(32), fill=MUTED)
    step = min(78, (H - 190 - y) // 10)
    bar = GOLD if kind == 'ath' else DOWN
    for r in rows[:10]:
        rh = step - 8
        d.rounded_rectangle([60, y, W - 60, y + rh], radius=10, fill=PANEL)
        d.rectangle([60, y, 68, y + rh], fill=bar)
        d.text((96, y + rh // 2), name_of(r), font=fit(d, name_of(r), 31, 400), fill=WHITE, anchor='lm')
        d.text((690, y + rh // 2), '₹' + fmt_inr(r['level']), font=hind(31, 'SemiBold'), fill=WHITE, anchor='rm')
        d.text((W - 90, y + rh // 2), f'{r["week_pct"]:+.2f}%', font=bebas(44), fill=col(r['week_pct']), anchor='rm')
        y += step
    footer(im, d, source)
    return im


def extremes(data):
    """Cover + one slide per market-cap group.
    data: kind ('ath'|'low'), date_text, headline, groups[{name, index, rows, count}], source"""
    kind = data['kind']
    label = 'All-Time Highs' if kind == 'ath' else '52-Week Lows'
    im, d = base(label, data['date_text'], data.get('sample'), data.get('theme'), data.get('seed', 0), 0.35, data.get('tone'))
    if data.get('theme'):
        im = scrim(im, 175, 400, 150); d = ImageDraw.Draw(im)
    y = headline(d, data['headline'], 190, size=90) + 26
    th = 184
    for g in data['groups']:
        d.rounded_rectangle([60, y, W - 60, y + th - 18], radius=16, fill=PANEL)
        d.text((90, y + 42), g['name'].upper(), font=bebas(52), fill=GOLD, anchor='lm')
        d.text((W - 90, y + 42), g['index'], font=cond(28), fill=MUTED, anchor='rm')
        word = 'all-time high' if kind == 'ath' else '52-week low'
        d.text((90, y + 96), f'{g["count"]} stock{"s" if g["count"] != 1 else ""} at a new {word}',
               font=hind(32, 'SemiBold'), fill=WHITE, anchor='lm')
        names = ', '.join(name_of(r) for r in g['rows'][:3])
        if names:
            d.text((90, y + 134), names[:48], font=hind(28), fill=MUTED, anchor='lm')
        y += th
    footer(im, d, data['source'], swipe=True)
    slides = [im.convert('RGB')]
    for g in data['groups']:
        what = 'all-time highs' if kind == 'ath' else '52-week lows'
        slides.append(extremes_slide(g['name'], data['date_text'], f'*{g["name"]}* {what} this week', g['rows'], kind,
                                     data['source'], f'No {g["name"].lower()} stock made a new {what[:-1]} this week.',
                                     data.get('sample')))
    return slides


def news_hero(data):
    """Story card with background art, company quote card(s), headline and key points.
    data: category, date_text, theme, seed, quotes[{name,symbol,price,chg,pct,time_text}], label, headline,
          points[], source"""
    from . import widgets
    im, d = base(data['category'], data['date_text'], data.get('sample'), data['theme'], data.get('seed', 0), 0, data.get('tone'))
    im = im.convert('RGBA')
    qs = data.get('quotes') or []
    if len(qs) == 1:
        im.alpha_composite(widgets.quote_card(qs[0], 620), (60, 190))
    elif qs:
        for i, q in enumerate(qs[:3]):
            im.alpha_composite(widgets.mini_quote(q, 600), (60 + (i % 2) * 40, 175 + i * 132))
    elif data.get('company'):
        im.alpha_composite(widgets.company_badge(data['company'], data.get('company_sub', '')), (60, 200))
    d = ImageDraw.Draw(im)
    y = 610
    if data.get('label'):
        f = bebas(64)
        tw = d.textlength(data['label'].upper(), font=f)
        d.rectangle([60, y, 60 + tw + 48, y + 84], fill=DOWN if data.get('tone') == 'down' else
                    UP if data.get('tone') == 'up' else GOLD)
        d.text((84, y + 44), data['label'].upper(), font=f, fill=WHITE if data.get('tone') in ('down', 'up') else BG, anchor='lm')
        y += 110
    y = headline(d, data['headline'], y, size=78, max_lines=3) + 18
    bullets(d, data.get('points', []), y, size=32)
    footer(im, d, data['source'])
    return [im.convert('RGB')]


def info_table(category, date_text, head, rows, source, theme=None, seed=0):
    """Label | value rows (long values wrap). rows: [(label, value)]"""
    im, d = base(category, date_text, False, theme, seed, 0.45)
    if theme:
        im = scrim(im, 175, 400, 150); d = ImageDraw.Draw(im)
    y = headline(d, head, 190, size=86, max_lines=2) + 26
    lf, vf = cond(30), hind(31, 'SemiBold')
    for i, (k, v) in enumerate(rows):
        lines = wrap(d, str(v), vf, W - 120 - 380) or ['-']
        h = max(70, 26 + 42 * len(lines[:3]))
        if y + h > H - 175:
            break
        d.rounded_rectangle([60, y, W - 60, y + h], radius=10, fill=PANEL if i % 2 == 0 else PANEL2)
        d.text((90, y + h // 2), k.upper(), font=lf, fill=MUTED, anchor='lm')
        yy = y + h // 2 - (len(lines[:3]) - 1) * 21
        for ln in lines[:3]:
            d.text((440, yy), ln, font=vf, fill=WHITE, anchor='lm')
            yy += 42
        y += h + 6
    footer(im, d, source)
    return im.convert('RGB')


def subscription(category, date_text, head, rows, update_text, source, theme='ipo', seed=0, tiles=None):
    """Category-wise subscription bars. rows: [{'category','times','bid','offered'}]; the 'Total' row is highlighted.
    tiles: up to 3 (label, value) facts drawn under the bars (price band, closes on, day)."""
    im, d = base(category, date_text, False, theme, seed, 0.45, 'up')
    im = scrim(im, 175, 400, 150); d = ImageDraw.Draw(im)
    y = headline(d, head, 190, size=86, max_lines=2) + 20
    if update_text:
        d.text((60, y), f'As of {update_text}', font=hind(26), fill=MUTED)
        y += 54
    mx = max([r['times'] for r in rows if r['times'] is not None] + [1])
    bottom = H - 200 - (190 if tiles else 0)
    rh = min(132, (bottom - y) // max(1, len(rows)))
    for r in rows:
        total = 'total' in r['category'].lower()
        name = r['category'][:34]
        d.text((60, y + 22), name, font=hind(30, 'Bold' if total else 'SemiBold'), fill=GOLD if total else WHITE, anchor='lm')
        t = r['times'] or 0
        bw = int((W - 320) * min(t / mx, 1))
        d.rounded_rectangle([60, y + 46, 60 + max(bw, 6), y + 76], radius=8, fill=GOLD if total else UP)
        d.text((W - 60, y + 61), f'{t:.2f}x', font=bebas(54), fill=GOLD if total else WHITE, anchor='rm')
        if r.get('bid') and r.get('offered') and rh >= 110:
            d.text((60, y + 98), f'Bids for {fmt_inr(r["bid"], 0)} of {fmt_inr(r["offered"], 0)} shares offered',
                   font=hind(23), fill=MUTED, anchor='lm')
        y += rh
    if tiles:
        y = H - 360
        n = len(tiles[:3]); gap = 20; tw = (W - 120 - gap * (n - 1)) // n
        for k, (lab, val) in enumerate(tiles[:3]):
            x = 60 + k * (tw + gap)
            d.rounded_rectangle([x, y, x + tw, y + 140], radius=16, fill=PANEL, outline=LINE, width=2)
            d.text((x + 22, y + 36), lab.upper(), font=cond(26), fill=MUTED, anchor='lm')
            f = 54
            while d.textlength(val, font=bebas(f)) > tw - 40 and f > 30:
                f -= 4
            d.text((x + 22, y + 95), val, font=bebas(f), fill=WHITE, anchor='lm')
    footer(im, d, source)
    return im.convert('RGB')


def index_board(data):
    """One slide listing many indices: name | close | change | %."""
    im, d = base('Index Scorecard', data['date_text'], False, data.get('theme'), data.get('seed', 0), 0.45, data.get('tone'))
    im = scrim(im, 175, 400, 150); d = ImageDraw.Draw(im)
    y = headline(d, data['headline'], 190, size=86, max_lines=2) + 22
    rows = data['rows']
    rh = min(98, (H - 230 - y) // max(1, len(rows)))
    for i, q in enumerate(rows):
        d.rounded_rectangle([60, y, W - 60, y + rh - 6], radius=10, fill=PANEL if i % 2 == 0 else PANEL2)
        cy = y + (rh - 6) // 2
        pct = pct_change(q['close'], q['chg'])
        d.text((84, cy), q['name'], font=hind(29, 'SemiBold'), fill=WHITE, anchor='lm')
        d.text((660, cy), fmt_inr(q['close']), font=bebas(46), fill=WHITE, anchor='rm')
        d.text((840, cy), ('+' if q['chg'] >= 0 else '') + fmt_inr(q['chg']), font=hind(26, 'SemiBold'), fill=col(q['chg']), anchor='rm')
        d.text((W - 84, cy), f'{pct:+.2f}%', font=bebas(46), fill=col(q['chg']), anchor='rm')
        y += rh
    footer(im, d, data['source'], swipe=True)
    return im.convert('RGB')


def highs_lows_group(data):
    """One market-cap group: new highs (all-time high or 52-week high tag) and new 52-week lows."""
    im, d = base(data['name'], data['date_text'], False, data.get('theme'), data.get('seed', 0), 0.5, data.get('tone'))
    im = scrim(im, 175, 330, 150); d = ImageDraw.Draw(im)
    y = headline(d, data['headline'], 190, size=80, max_lines=2) + 10
    d.text((60, y + 10), data['summary'], font=hind(27), fill=MUTED, anchor='lm')
    y += 46

    def rows_block(title, rows, colour, empty, tag_fn, y):
        y = section(d, title, y)
        if not rows:
            d.text((60, y + 18), empty, font=hind(28), fill=MUTED)
            return y + 70
        for r in rows:
            d.rounded_rectangle([60, y, W - 60, y + 60], radius=10, fill=PANEL)
            d.rectangle([60, y, 68, y + 60], fill=colour)
            d.text((92, y + 30), name_of(r), font=fit(d, name_of(r), 29, 300), fill=WHITE, anchor='lm')
            tag = tag_fn(r)
            if tag:
                tw = d.textlength(tag, font=cond(22)) + 20
                d.rounded_rectangle([420, y + 16, 420 + tw, y + 44], radius=6, fill=GOLD)
                d.text((430, y + 30), tag, font=cond(22), fill=BG, anchor='lm')
            d.text((760, y + 30), '₹' + fmt_inr(r['last']), font=hind(28, 'SemiBold'), fill=MUTED, anchor='rm')
            d.text((W - 84, y + 30), f'{r["pct"]:+.2f}%', font=bebas(44), fill=col(r['pct']), anchor='rm')
            y += 68
        return y + 10

    highs = [dict(r, _ath=True) for r in data['ath']] + [dict(r, _ath=False) for r in data['hi52']]
    y = rows_block('New highs today', highs[:6], GOLD, 'No stock in this group made a new 52-week high today.',
                   lambda r: 'ALL-TIME HIGH' if r['_ath'] else '52-WEEK HIGH', y)
    rows_block('New 52-week lows today', data['lo52'][:5], DOWN, 'No stock in this group made a new 52-week low today.',
               lambda r: None, y)
    footer(im, d, data['source'])
    return im.convert('RGB')


def cover(data):
    """Hook slide for a carousel: big day + date, hook headline, up to 3 key numbers, swipe hint.
    data: category, day (date), headline, stats[(label, value_text, sign)], theme, seed, tone, source"""
    day = data['day']
    im, d = base(data['category'], data.get('date_text', ''), data.get('sample'), data.get('theme'), data.get('seed', 0),
                 0.1, data.get('tone'))
    im = im.convert('RGBA')
    # date block
    # left-to-right shade behind the date only, so the scene stays visible on the right
    import numpy as _np
    a = _np.zeros((250, W, 4), _np.uint8)
    a[..., :3] = BG
    a[..., 3] = (_np.clip(1.25 - _np.linspace(0, 1, W) * 1.5, 0, 1) * 185).astype(_np.uint8)[None, :]
    im.alpha_composite(Image.fromarray(a, 'RGBA'), (0, 150))
    d = ImageDraw.Draw(im)
    d.text((60, 200), day.strftime('%A').upper(), font=bebas(66), fill=GOLD, anchor='lm')
    d.text((60, 300), f'{day.day} {day.strftime("%B %Y")}'.upper(), font=bebas(120), fill=WHITE, anchor='lm')
    im = scrim(im, 420, 1180, 120)
    d = ImageDraw.Draw(im)
    y = headline(d, data['headline'], 470, size=108, max_lines=3) + 40
    stats = data.get('stats') or []
    if stats:
        n = len(stats[:3])
        gap = 24
        tw = (W - 120 - gap * (n - 1)) // n
        for i, (lab, val, sign) in enumerate(stats[:3]):
            x = 60 + i * (tw + gap)
            d.rounded_rectangle([x, y, x + tw, y + 170], radius=18, fill=PANEL, outline=LINE, width=2)
            d.text((x + 24, y + 38), lab.upper(), font=cond(28), fill=MUTED, anchor='lm')
            f = 70
            while d.textlength(val, font=bebas(f)) > tw - 48 and f > 36:
                f -= 4
            sign = sign_of(val, sign) if '%' in val else sign
            d.text((x + 24, y + 112), val, font=bebas(f), fill=UP if sign > 0 else DOWN if sign < 0 else WHITE,
                   anchor='lm')
        y += 210
    inside = data.get('inside') or []
    if inside and y < H - 330:
        d.text((60, y), 'INSIDE THIS POST', font=cond(30), fill=GOLD, anchor='lm')
        y += 44
        x = 60
        for item in inside:
            tw = d.textlength(item, font=hind(28, 'SemiBold')) + 44
            if x + tw > W - 60:
                x = 60; y += 64
            if y > H - 230:
                break
            d.rounded_rectangle([x, y, x + tw, y + 50], radius=25, outline=GOLD, width=2)
            d.text((x + 22, y + 26), item, font=hind(28, 'SemiBold'), fill=WHITE, anchor='lm')
            x += tw + 14
    footer(im, d, data.get('source', ''), swipe=True)
    return im.convert('RGB')
