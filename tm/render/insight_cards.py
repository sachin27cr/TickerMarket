"""Slide templates for the Insights series: company growth cards, bar charts, ranked bars, score tables
and a closing follow slide. Every number is passed in as data."""
from PIL import Image, ImageDraw

from .. import config
from ..util import fmt_inr
from .cards import (BG, DOWN, FLAT, GOLD, H, LINE, MUTED, PANEL, PANEL2, UP, W, WHITE, base, bebas, col, cond, footer,
                    headline, hind, logo, rich_text, scrim, sign_of, wrap)
from .widgets import monogram


def _fit(d, text, font_fn, size, max_w, min_size=30):
    while d.textlength(text, font=font_fn(size)) > max_w and size > min_size:
        size -= 2
    return font_fn(size)


ARROW = None        # marker inside a parts list: draw an arrow (the fonts have no arrow glyph)


def draw_seq(d, x, y, parts, font, fill, align='l', gap=18):
    """Draw text parts with drawn arrows between them; y is the vertical middle."""
    size = font.size
    aw = int(size * 0.75)
    widths = [aw if p is ARROW else d.textlength(p, font=font) for p in parts]
    total = sum(widths) + gap * (len(parts) - 1)
    x0 = x if align == 'l' else x - total if align == 'r' else x - total / 2
    for p, w in zip(parts, widths):
        if p is ARROW:
            t = max(3, size // 12)
            d.rectangle([x0, y - t, x0 + w - size * 0.3, y + t], fill=fill)
            d.polygon([(x0 + w - size * 0.38, y - size * 0.26), (x0 + w, y), (x0 + w - size * 0.38, y + size * 0.26)], fill=fill)
        else:
            d.text((x0, y), p, font=font, fill=fill, anchor='lm')
        x0 += w + gap
    return total


def draw_seq_width(d, parts, font, gap=18):
    return sum(int(font.size * 0.75) if p is ARROW else d.textlength(p, font=font) for p in parts) + gap * (len(parts) - 1)


def cr(v):
    """Rs crore with sensible decimals: 1,031.90 / 48 / 0.85."""
    return '₹' + fmt_inr(v, 2 if abs(v) < 10000 else 0) + ' Cr'


def growth_slide(data):
    """One company: big growth %, from -> to rows, quarter labels, NSE price box.
    data: n, total, name, symbol, growth, rows[(label, from_text, to_text)], period_text, basis, price, pct, date_text"""
    im, d = base(data.get('category', 'Results'), data['date_text'], False, data.get('theme', 'market_up'),
                 data.get('seed', 0), 0.55, 'up')
    im = scrim(im.convert('RGBA'), 160, 1190, 175)
    d = ImageDraw.Draw(im)
    # rank bubble + company
    d.ellipse([60, 190, 150, 280], fill=GOLD)
    d.text((105, 237), str(data['n']), font=bebas(62), fill=BG, anchor='mm')
    im.alpha_composite(monogram(90, data['name']), (176, 190))
    nf = _fit(d, data['name'], lambda s: hind(s, 'Bold'), 44, W - 300, 28)
    d.text((290, 222), data['name'], font=nf, fill=WHITE, anchor='lm')
    d.text((290, 264), f'NSE: {data["symbol"]}', font=cond(30), fill=MUTED, anchor='lm')
    # big number
    g = data['growth']
    big = f'{g:+,.1f}%'
    f = _fit(d, big, bebas, 270, W - 120, 120)
    d.text((W // 2, 470), big, font=f, fill=UP if g >= 0 else DOWN, anchor='mm')
    d.text((W // 2, 620), data.get('metric', 'NET PROFIT GROWTH  •  YoY'), font=cond(46), fill=WHITE, anchor='mm')
    # from -> to panel
    y = 680
    rows = data['rows']
    ph = 30 + 104 * len(rows)
    d.rounded_rectangle([60, y, W - 60, y + ph], radius=22, fill=PANEL, outline=LINE, width=2)
    yy = y + 20
    for lab, a_, b_ in rows:
        d.text((96, yy + 52), lab, font=hind(32, 'SemiBold'), fill=MUTED, anchor='lm')
        fnt = hind(40, 'Bold')
        while draw_seq_width(d, [a_, ARROW, b_], fnt) > 620 and fnt.size > 26:
            fnt = hind(fnt.size - 2, 'Bold')
        draw_seq(d, W - 96, yy + 52, [a_, ARROW, b_], fnt, WHITE, 'r')
        yy += 104
    y += ph + 34
    pf = cond(36)
    period = data['period_parts']
    draw_seq(d, 60, y + 50, period, pf, GOLD, 'l')
    if data.get('basis'):
        d.text((60, y + 100), data['basis'] + ' results', font=hind(28), fill=MUTED, anchor='lm')
    if data.get('price'):
        bw, bh = 440, 120
        x0 = W - 60 - bw
        d.rounded_rectangle([x0, y, x0 + bw, y + bh], radius=18, outline=GOLD, width=2, fill=(8, 16, 34))
        d.text((x0 + 26, y + 34), 'NSE CLOSE', font=cond(26), fill=MUTED, anchor='lm')
        d.text((x0 + 26, y + 80), '₹' + fmt_inr(data['price']), font=bebas(58), fill=WHITE, anchor='lm')
        d.text((x0 + bw - 26, y + 62), f'{data["pct"]:+.2f}%', font=bebas(58), fill=col(data['pct']), anchor='rm')
    footer(im, d, '', swipe=data['n'] < data['total'], page=f'{data["n"]}/{data["total"]}')
    return im.convert('RGB')


def vbars(data):
    """Vertical bar chart around a zero line (like a monthly asset scorecard).
    data: category, date_text, headline, items[{label, pct, value_text}], note"""
    im, d = base(data['category'], data['date_text'], False, data.get('theme'), data.get('seed', 0), 0.6, data.get('tone'))
    im = scrim(im.convert('RGBA'), 160, 1190, 185)
    d = ImageDraw.Draw(im)
    y = headline(d, data['headline'], 190, size=84, max_lines=2) + 10
    items = data['items'][:10]
    top, bot = y + 70, H - 330
    pos = max(0.0, max(i['pct'] for i in items))
    neg = max(0.0, -min(i['pct'] for i in items))
    span = (pos + neg) or 1
    zero = top + (bot - top) * pos / span
    n = len(items)
    slot = (W - 120) / n
    bw = min(70, slot * 0.62)
    d.line([(60, zero), (W - 60, zero)], fill=LINE, width=2)
    for k, it in enumerate(items):
        cx = 60 + slot * (k + 0.5)
        h = (bot - top) * abs(it['pct']) / span
        c = UP if it['pct'] > 0 else DOWN if it['pct'] < 0 else FLAT
        if it['pct'] >= 0:
            d.rounded_rectangle([cx - bw / 2, zero - max(h, 4), cx + bw / 2, zero], radius=6, fill=c)
            d.text((cx, zero - h - 26), f'{it["pct"]:+.1f}%', font=bebas(36), fill=c, anchor='mm')
            ly = zero + 18
        else:
            d.rounded_rectangle([cx - bw / 2, zero, cx + bw / 2, zero + max(h, 4)], radius=6, fill=c)
            d.text((cx, zero + h + 26), f'{it["pct"]:+.1f}%', font=bebas(36), fill=c, anchor='mm')
            ly = zero - 18 - 2 * 28
        for j, part in enumerate(_split_label(it['label'])):
            d.text((cx, ly + 14 + j * 28), part, font=cond(25), fill=WHITE, anchor='mm')
    if data.get('note'):
        d.text((60, H - 210), data['note'], font=hind(24), fill=MUTED, anchor='lm')
    footer(im, d, '', swipe=data.get('swipe', False))
    return im.convert('RGB')


def _split_label(s):
    w = s.split()
    if len(s) <= 9 or len(w) == 1:
        return [s]
    mid = (len(w) + 1) // 2
    return [' '.join(w[:mid]), ' '.join(w[mid:])][:2]


def hbars(data):
    """Ranked horizontal bars. data: category, date_text, headline, sub, rows[{name, value, value_text, side_text,
    side_sign}], colour ('gold'|'up'|'down'|'sign')"""
    im, d = base(data['category'], data['date_text'], False, data.get('theme'), data.get('seed', 0), 0.6, data.get('tone'))
    im = scrim(im.convert('RGBA'), 160, 1190, 185)
    d = ImageDraw.Draw(im)
    y = headline(d, data['headline'], 190, size=80, max_lines=2) + 4
    if data.get('sub'):
        d.text((60, y + 14), data['sub'], font=hind(26), fill=MUTED, anchor='lm')
        y += 62
    rows = data['rows'][:10]
    rh = min(150, (H - 275 - y) // max(1, len(rows)))
    mx = data.get('max') or max(abs(r['value']) for r in rows) or 1
    x_bar, max_bw = 330, W - 60 - 330 - 10
    for i, r in enumerate(rows):
        cy = y + rh // 2
        plain = data.get('plain')              # timeline rows: no rank number, no logo badge
        if not plain:
            d.text((60, cy), str(i + data.get('start', 1)), font=bebas(40), fill=GOLD, anchor='lm')
            im.alpha_composite(monogram(48, r['name']), (108, cy - 24))
        nx = 60 if plain else 166
        nm = r['name']
        while d.textlength(nm, font=hind(27, 'SemiBold')) > x_bar - nx - 4 and len(nm) > 4:
            nm = nm[:-1]
        d.text((nx, cy), nm if nm == r['name'] else nm.rstrip() + '.', font=hind(27, 'SemiBold'), fill=WHITE, anchor='lm')
        c = {'gold': GOLD, 'up': UP, 'down': DOWN}.get(data.get('colour', 'gold')) or col(r['value'])
        bw = max(8, int(max_bw * abs(r['value']) / mx * 0.62))
        d.rounded_rectangle([x_bar, cy - 22, x_bar + bw, cy + 22], radius=8, fill=c)
        d.text((x_bar + bw + 14, cy - 2), r['value_text'], font=bebas(42), fill=WHITE, anchor='lm')
        if r.get('side_text'):
            d.text((W - 60, cy + 2), r['side_text'], font=hind(24, 'SemiBold'), fill=col(r.get('side_sign', 0)), anchor='rm')
        y += rh
    if data.get('note'):
        lines, cur = [], ''
        for w in data['note'].split():         # wrap long notes instead of running off the card
            t = (cur + ' ' + w).strip()
            if d.textlength(t, font=hind(23)) > W - 120 and cur:
                lines.append(cur); cur = w
            else:
                cur = t
        lines.append(cur)
        ny = min(y + 20, H - 236 - 34 * (len(lines) - 1))
        for k, ln in enumerate(lines[:3]):
            d.text((60, ny + 34 * k), ln, font=hind(23), fill=MUTED, anchor='lm')
    footer(im, d, '', swipe=data.get('swipe', False))
    return im.convert('RGB')


def score_table(data):
    """Name + up to 3 % columns. data: category, date_text, headline, cols[str], rows[{name, vals[float|None]}], note"""
    im, d = base(data['category'], data['date_text'], False, data.get('theme'), data.get('seed', 0), 0.6, data.get('tone'))
    im = scrim(im.convert('RGBA'), 160, 1190, 185)
    d = ImageDraw.Draw(im)
    y = headline(d, data['headline'], 190, size=80, max_lines=2) + 18
    cols = data['cols']
    xs = [W - 60 - 170 * (len(cols) - 1 - k) for k in range(len(cols))]
    d.rounded_rectangle([60, y, W - 60, y + 56], radius=10, fill=GOLD)
    d.text((84, y + 28), data.get('name_col', 'INDEX'), font=cond(28), fill=BG, anchor='lm')
    for x, c in zip(xs, cols):
        d.text((x - 20, y + 28), c, font=cond(28), fill=BG, anchor='rm')
    y += 66
    rows = data['rows']
    rh = min(66, (H - 250 - y) // max(1, len(rows)))
    nf, vf = hind(min(28, rh - 18), 'SemiBold'), bebas(min(40, rh - 6))
    for i, r in enumerate(rows):
        d.rounded_rectangle([60, y, W - 60, y + rh - 4], radius=8, fill=PANEL if i % 2 == 0 else PANEL2)
        cy = y + (rh - 4) // 2
        hl = r.get('highlight')
        d.text((84, cy), r['name'], font=nf, fill=GOLD if hl else WHITE, anchor='lm')
        for x, v in zip(xs, r['vals']):
            d.text((x - 20, cy), '-' if v is None else f'{v:+.2f}%', font=vf,
                   fill=MUTED if v is None else col(v), anchor='rm')
        y += rh
    if data.get('note'):
        d.text((60, y + 22), data['note'], font=hind(23), fill=MUTED, anchor='lm')
    footer(im, d, '', swipe=data.get('swipe', False))
    return im.convert('RGB')


def list_slide(data):
    """Summary list for a series: rank, company, metric. data: category, date_text, headline, rows[(name, value_text, sign)]"""
    im, d = base(data['category'], data['date_text'], False, data.get('theme'), data.get('seed', 0), 0.6, data.get('tone'))
    im = scrim(im.convert('RGBA'), 160, 1190, 185)
    d = ImageDraw.Draw(im)
    y = headline(d, data['headline'], 190, size=80, max_lines=2) + 24
    rows = data['rows'][:10]
    rh = min(130, (H - 220 - y) // max(1, len(rows)))
    for i, (nm, val, sign) in enumerate(rows):
        d.rounded_rectangle([60, y, W - 60, y + rh - 8], radius=12, fill=PANEL)
        cy = y + (rh - 8) // 2
        d.text((90, cy), str(i + 1), font=bebas(40), fill=GOLD, anchor='lm')
        im.alpha_composite(monogram(48, nm), (130, cy - 24))
        f = _fit(d, nm, lambda s: hind(s, 'SemiBold'), 30, 560, 22)
        d.text((194, cy), nm, font=f, fill=WHITE, anchor='lm')
        sign = sign_of(val, sign)
        d.text((W - 90, cy), val, font=bebas(48), fill=UP if sign > 0 else DOWN if sign < 0 else WHITE, anchor='rm')
        y += rh
    footer(im, d, '', swipe=data.get('swipe', True))
    return im.convert('RGB')


def summary_slide(data):
    """'In short' slide: key points taken from the (already verified) caption. data: date_text, points, theme, seed, tone"""
    im, d = base(data.get('category', 'In Short'), data['date_text'], False, data.get('theme', 'market_up'), data.get('seed', 0), 0.6,
                 data.get('tone'))
    im = scrim(im.convert('RGBA'), 160, 1190, 195)
    d = ImageDraw.Draw(im)
    y = headline(d, data.get('headline', '*In short*'), 190, size=92, max_lines=2) + 30
    pts = data['points'][:6]
    size = 34 if sum(len(p) for p in pts) < 520 else 30
    f, lh = hind(size, 'SemiBold'), int(size * 1.35)
    for i, p in enumerate(pts):
        lines = wrap(d, p, f, W - 220)
        hgt = len(lines) * lh + 40
        if y + hgt > H - 190:
            break
        d.rounded_rectangle([60, y, W - 60, y + hgt], radius=16, fill=PANEL, outline=LINE, width=2)
        d.ellipse([84, y + 22, 128, y + 66], fill=GOLD)
        d.text((106, y + 44), str(i + 1), font=bebas(36), fill=BG, anchor='mm')
        rich_text(d, 152, y + 22, p, f, W - 220, WHITE, lh)
        y += hgt + 16
    footer(im, d, '', swipe=True)
    return im.convert('RGB')


def follow_slide(data):
    """Closing slide: logo and follow prompt only."""
    im, d = base(data.get('category', 'Ticker Market India'), data.get('date_text', ''), False,
                 data.get('theme', 'market_up'), data.get('seed', 0), 0.5, data.get('tone', 'up'))
    im = scrim(im.convert('RGBA'), 160, 1190, 175)
    d = ImageDraw.Draw(im)
    lg = logo()
    lg = lg.resize((620, int(lg.height * 620 / lg.width)), Image.LANCZOS)
    y = 300
    im.paste(lg, ((W - lg.width) // 2, y), lg)
    y += lg.height + 90
    d.text((W // 2, y), 'FOLLOW TICKER MARKET INDIA', font=bebas(96), fill=GOLD, anchor='mm')
    d.text((W // 2, y + 82), 'for daily stock market data & news', font=hind(42, 'SemiBold'), fill=WHITE, anchor='mm')
    d.text((W // 2, y + 146), config.BRAND['handle'], font=hind(40, 'Bold'), fill=GOLD, anchor='mm')
    d.text((W // 2, H - 220), 'Save  •  Share  •  Turn on post notifications', font=cond(34), fill=MUTED, anchor='mm')
    footer(im, d, '')
    return im.convert('RGB')
