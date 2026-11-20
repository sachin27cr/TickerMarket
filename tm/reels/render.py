"""Vertical reels (1080x1920, 30 fps) with their own look, different from the posts:
full-screen pictures with a slow zoom, white cards with dark text, a saffron accent, a progress bar
at the top and subtitles that follow the voice-over.

A reel is a list of scenes. Scene types:
  intro  - day + date, title, hook line
  rows   - title + up to 6 rows (label, value, change)        e.g. indices, global markets
  duo    - two columns (e.g. top gainers / top losers)
  outro  - follow prompt
Every number shown is passed in as data (already verified by the job).
"""
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .. import config
from ..render import cards
from ..util import log
from . import voice

W, H, FPS = 1080, 1920, 30
CARD = (250, 250, 252)
INK = (12, 20, 40)
MUTED = (92, 102, 122)
SAFFRON = (255, 153, 51)
GREEN = (12, 150, 84)
RED = (214, 38, 50)
WHITE = (255, 255, 255)

# background picture per scene topic (photo prompt key in photo.SCENES / drawn scene name)
TOPIC_PHOTO = {
    'intro': 'Mumbai skyline at sunrise seen from the sea, golden light, calm water',
    'intro_pm': 'Mumbai skyline at golden hour seen from Marine Drive, glass towers glowing',
    'intro_week': 'aerial view of Mumbai business district at dusk, glowing towers and traffic light trails',
    'global': 'a glowing globe of the earth from space with golden network lines between financial centres',
    'commodities': 'gold bars, an oil barrel and Indian rupee notes on a dark marble table, studio light',
    'indices': 'busy modern stock trading floor with rows of monitors showing charts, warm light',
    'flows': 'stacks of Indian rupee banknotes and gold coins on a desk in front of trading screens',
    'calendar': 'a desk with a planner, coffee and a laptop showing stock charts, early morning window light',
    'sectors': 'collage of Indian industries: steel plant, IT office, pharmaceutical lab and car factory',
    'movers': 'close-up of trading monitors with green and red bar charts, dark office, neon reflections',
    'highs': 'a mountaineer flag planted on a snowy summit at sunrise, sea of clouds below',
    'lows': 'a deep canyon at dusk with long shadows and a red sky',
    'outro': 'Mumbai skyline at night with glowing towers and reflections on the sea',
}
TOPIC_SCENE = {'intro': 'dalal', 'intro_pm': 'dalal', 'intro_week': 'bars3d', 'global': 'globe',
               'commodities': 'goldbars', 'indices': 'candles', 'flows': 'flows', 'calendar': 'calendar',
               'sectors': 'heatmap', 'movers': 'arrows', 'highs': 'peaks', 'lows': 'peaks', 'outro': 'candles'}


def _font(kind, size):
    return {'bebas': cards.bebas, 'cond': cards.cond}.get(kind, lambda s: cards.hind(s, kind))(size)


def background(topic, tone, seed):
    """Full-frame picture for a scene: photo if Cloudflare is set up, else a drawn scene. 1188x2112 (zoom room)."""
    from ..render import art, own_bg, photo
    t = tone if tone in ('up', 'down') else None
    mine = own_bg.pick('reels/' + own_bg.REEL.get(topic, 'evening'), t, seed) or \
        own_bg.pick(own_bg.TOPIC.get(topic, 'common'), t, seed)
    pic = None if mine is not None else (photo.get(TOPIC_PHOTO.get(topic)) if photo.enabled() else None)
    if mine is not None:
        im = own_bg.cover(mine, 1188, 2112)
    elif pic is not None:
        side = 2112
        im = pic.resize((side, side), Image.LANCZOS).crop(((side - 1188) // 2, 0, (side - 1188) // 2 + 1188, 2112))
    else:
        im = art._scene_background(TOPIC_SCENE.get(topic, 'candles'), 'reel', 1188, 2112, random.Random(seed),
                                   tone != 'down', art.UP if tone != 'down' else art.DOWN)
    im = art.calm(im, blur=6, colour=0.45, bright=0.68, tint=0.2)    # muted, so the data stands out
    # darken top and bottom for the header and subtitles
    a = np.zeros((2112, 1188, 4), np.uint8)
    y = np.arange(2112)[:, None]
    a[..., 3] = np.clip(np.maximum(1 - y / 520, (y - 1450) / 660) * 210, 0, 210).astype(np.uint8)
    im = im.convert('RGBA')
    im.alpha_composite(Image.fromarray(a, 'RGBA'))
    return im.convert('RGB')


# ---------------------------------------------------------------- broadcast look: glass panels, motion, data bars
GLASS = (12, 18, 34)
UPC = (34, 197, 94)
DNC = (239, 68, 68)
MUTE = (165, 175, 195)


def ease(k):
    k = min(1.0, max(0.0, k))
    return 1 - (1 - k) ** 3


def _glass(w, h, accent=None, radius=30):
    """Dark frosted panel with a fine light border and a soft top highlight."""
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=GLASS + (208,))
    hl = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    a = np.zeros((h, w), np.uint8)
    a[:max(1, h // 2)] = (np.linspace(26, 0, max(1, h // 2))[:, None]).astype(np.uint8)
    hl.putalpha(Image.fromarray(a))
    hl = Image.composite(Image.new('RGBA', (w, h), (255, 255, 255, 255)), Image.new('RGBA', (w, h), (0, 0, 0, 0)),
                         hl.split()[-1])
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    hl.putalpha(Image.fromarray((np.array(hl.split()[-1]) * (np.array(mask) / 255)).astype(np.uint8)))
    im.alpha_composite(hl)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, outline=(255, 255, 255, 46), width=2)
    if accent:
        d.rounded_rectangle([0, 18, 8, h - 19], radius=4, fill=accent + (255,))
    return im, d


def chg_col(v):
    return UPC if v > 0 else DNC if v < 0 else MUTE


def _num_fmt(target, frac):
    """Count-up text for a value string like '24,612' or '84.62' (non-numbers are shown as they are)."""
    import re
    m = re.fullmatch(r'([^\d\-]*)(-?[\d,]+(?:\.\d+)?)(.*)', target)
    if not m or frac >= 1:
        return target
    num = float(m.group(2).replace(',', ''))
    dec = len(m.group(2).split('.')[1]) if '.' in m.group(2) else 0
    v = num * frac
    body = f'{v:,.{dec}f}' if ',' in m.group(2) else f'{v:.{dec}f}'
    return m.group(1) + body + m.group(3)


class Tile:
    """A pre-rendered element that slides up and fades in at `start` seconds; `live` draws animated parts."""

    def __init__(self, im, x, y, start, live=None):
        self.im, self.x, self.y, self.start, self.live = im, x, y, start, live
        self.alpha = np.array(im.split()[-1], dtype=np.float32)

    def draw(self, frame, t):
        k = (t - self.start) / 0.4
        if k <= 0:
            return
        e = ease(k)
        im = self.im
        if e < 1:
            im = self.im.copy()
            im.putalpha(Image.fromarray((self.alpha * e).astype(np.uint8)))
        x, y = int(self.x), int(self.y + (1 - e) * 60)
        frame.alpha_composite(im, (x, y))
        if self.live:
            self.live(ImageDraw.Draw(frame), x, y, t - self.start, e)


def _title_tile(text, y, start, size=92, eyebrow=None):
    im = Image.new('RGBA', (W - 120, size + 70), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = _font('bebas', size)
    while d.textlength(text.upper(), font=f) > W - 140 and size > 54:
        size -= 4
        f = _font('bebas', size)
    d.text((0, 0), text.upper(), font=f, fill=WHITE)
    tw = d.textlength(text.upper(), font=f)

    def live(dd, x, y0, t, e):                      # accent underline wipes in under the title
        w = int(min(tw, 220) * ease((t - 0.15) / 0.5))
        if w > 0:
            dd.rounded_rectangle([x, y0 + size + 14, x + w, y0 + size + 22], radius=4, fill=SAFFRON)
    return Tile(im, 60, y, start, live)


def _pill(dd, x_right, cy, pct, frac, size=60):
    txt = f'{pct * frac:+.2f}%'
    f = _font('bebas', size)
    tw = dd.textlength(txt, font=f)
    h = size + 12
    dd.rounded_rectangle([x_right - tw - 44, cy - h // 2, x_right, cy + h // 2], radius=h // 2,
                         fill=chg_col(pct) + (235,))
    dd.text((x_right - 22, cy + 2), txt, font=f, fill=WHITE, anchor='rm')
    return tw + 44


def _feature_tile(r, y, start):
    """The lead row of a scene, big: value counts up, change pill, direction arrow."""
    w, h = W - 120, 300
    card, d = _glass(w, h, SAFFRON)
    d.text((48, 66), r['label'].upper(), font=_font('cond', 50), fill=MUTE, anchor='lm')

    def live(dd, x, y0, t, e):
        k = ease((t - 0.1) / 0.9)
        dd.text((x + 46, y0 + 186), _num_fmt(r.get('value') or '', k), font=_font('bebas', 160), fill=WHITE,
                anchor='lm')
        if r.get('pct') is not None:
            _pill(dd, x + w - 40, y0 + 66, r['pct'], k, 58)
            up = r['pct'] >= 0
            cx, cy, s = x + w - 110, y0 + 196, 46 * ease((t - 0.6) / 0.35)
            if s > 1:
                pts = [(cx, cy - s), (cx - s, cy + s * 0.6), (cx + s, cy + s * 0.6)] if up else \
                      [(cx, cy + s), (cx - s, cy - s * 0.6), (cx + s, cy - s * 0.6)]
                dd.polygon(pts, fill=chg_col(r['pct']))
    return Tile(card, 60, y, start, live)


def _row_tile(r, y, rh, start, big, scale):
    w = W - 120
    card, d = _glass(w, rh - 20, chg_col(r['pct']) if r.get('pct') is not None else SAFFRON, 24)
    cy = (rh - 20) // 2
    has_bar = r.get('pct') is not None and scale > 0
    lf = _font('Bold', 46 if big >= 76 else 40)
    d.text((44, cy - (20 if (r.get('sub') or has_bar) else 0)), r['label'], font=lf, fill=WHITE, anchor='lm')
    if r.get('sub'):
        d.text((44, cy + 30), r['sub'], font=_font('Medium', 30), fill=MUTE, anchor='lm')

    def live(dd, x, y0, t, e):
        k = ease((t - 0.05) / 0.7)
        right = x + w - 34
        if r.get('pct') is not None:
            right -= _pill(dd, right, y0 + cy, r['pct'], k, big - 12) + 26
        if r.get('value'):
            dd.text((right, y0 + cy), _num_fmt(r['value'], k), font=_font('bebas', big), fill=WHITE, anchor='rm')
        if has_bar and not r.get('sub'):            # bar = size of the move, relative to the biggest in the scene
            bw = int(330 * min(1, abs(r['pct']) / scale) * k)
            dd.rounded_rectangle([x + 44, y0 + cy + 26, x + 44 + 330, y0 + cy + 34], radius=4, fill=(255, 255, 255, 30))
            if bw > 2:
                dd.rounded_rectangle([x + 44, y0 + cy + 26, x + 44 + bw, y0 + cy + 34], radius=4, fill=chg_col(r['pct']))
    return Tile(card, 60, y, start, live)


def _bars_tile(head, rows, colr, y, start, scale):
    """Ranked bars (best or weakest): name, growing bar, change."""
    w = W - 120
    rh = 92
    card, d = _glass(w, 96 + rh * len(rows), colr)
    d.text((44, 54), head.upper(), font=_font('cond', 46), fill=colr, anchor='lm')
    for i, r in enumerate(rows):
        nm = r['label']
        while d.textlength(nm, font=_font('Bold', 40)) > 330 and len(nm) > 4:
            nm = nm[:-1]
        d.text((44, 96 + i * rh + rh // 2), nm, font=_font('Bold', 40), fill=WHITE, anchor='lm')

    def live(dd, x, y0, t, e):
        for i, r in enumerate(rows):
            k = ease((t - 0.1 - i * 0.12) / 0.6)
            cy = y0 + 96 + i * rh + rh // 2
            bx, full = x + 400, w - 400 - 210
            bw = int(full * min(1, abs(r['pct']) / scale) * k) if scale else 0
            dd.rounded_rectangle([bx, cy - 16, bx + full, cy + 16], radius=16, fill=(255, 255, 255, 22))
            if bw > 4:
                dd.rounded_rectangle([bx, cy - 16, bx + bw, cy + 16], radius=16, fill=chg_col(r['pct']))
            dd.text((x + w - 36, cy + 2), f'{r["pct"] * k:+.2f}%', font=_font('bebas', 58), fill=chg_col(r['pct']),
                    anchor='rm')
    return Tile(card, 60, y, start, live)


def scene_tiles(sc):
    """Tiles for one scene, laid out in the middle of the frame."""
    tiles = []
    kind = sc['type']
    voiced = bool(sc.get('voice'))
    if kind == 'intro':
        day = sc['day']
        im = Image.new('RGBA', (W - 120, 400), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        f = _font('cond', 44)
        tw = d.textlength(sc['title'].upper(), font=f)
        d.rounded_rectangle([0, 0, tw + 70, 66], radius=33, fill=GLASS + (215,), outline=SAFFRON, width=3)
        d.ellipse([20, 24, 38, 42], fill=SAFFRON)
        d.text((50, 34), sc['title'].upper(), font=f, fill=WHITE, anchor='lm')
        d.text((0, 100), day.strftime('%A').upper(), font=_font('bebas', 100), fill=SAFFRON)
        d.text((0, 190), f'{day.day} {day.strftime("%B %Y")}'.upper(), font=_font('bebas', 156), fill=WHITE)
        tiles.append(Tile(im, 60, 420, 0.05))
        tmp = ImageDraw.Draw(Image.new('RGBA', (10, 10)))
        hf = _font('Bold', 62)
        lines = cards.wrap(tmp, sc['hook'], hf, W - 230)[:4]
        card, d = _glass(W - 120, 76 + 82 * len(lines), SAFFRON)
        words = [(li, w) for li, ln in enumerate(lines) for w in ln.split()]

        def live(dd, x, y0, t, e):                  # hook words pop in one by one
            pos = {}
            for n, (li, w) in enumerate(words):
                k = ease((t - 0.15 - n * 0.07) / 0.25)
                if k <= 0:
                    break
                px = pos.get(li, x + 50)
                col = tuple(int(255 * k + 0 * (1 - k)) for _ in range(3))
                dd.text((px, y0 + 38 + li * 82 + int((1 - k) * 18)), w, font=hf, fill=col + (int(255 * k),))
                pos[li] = px + dd.textlength(w + ' ', font=hf)
        tiles.append(Tile(card, 60, 860, 0.45, live))
    elif kind == 'rows':
        tiles.append(_title_tile(sc['title'], 380, 0.05))
        rows = sc['rows'][:6]
        y = 520
        if sc.get('topic') in ('indices',) and rows and rows[0].get('value') and rows[0].get('pct') is not None:
            tiles.append(_feature_tile(rows[0], y, 0.3))
            y += 324
            rows = rows[1:5]
            feature = True
        else:
            feature = False
        pcts = [abs(r['pct']) for r in rows if r.get('pct') is not None]
        scale = max(pcts) if pcts else 0
        rh = 150 if feature else 176 if len(rows) <= 4 else 146
        big = 66 if feature else 76 if len(rows) <= 4 else 64
        for i, r in enumerate(rows):
            stagger = 0.18 if voiced else 0.07          # silent lists appear almost at once
            tiles.append(_row_tile(r, y + i * rh, rh, scale=scale, big=big,
                                   start=(0.45 if voiced else 0.15) + i * stagger))
    elif kind == 'duo':
        tiles.append(_title_tile(sc['title'], 380, 0.05))
        left, right = sc['left'][:4], sc['right'][:4]
        scale = max([abs(r['pct']) for r in left + right] or [0])
        tiles.append(_bars_tile(sc['left_title'], left, UPC, 520, 0.35, scale))
        tiles.append(_bars_tile(sc['right_title'], right, DNC, 520 + 96 + 92 * len(left) + 26, 0.9, scale))
    elif kind == 'outro':
        lg = cards.logo()
        lg = lg.resize((640, int(lg.height * 640 / lg.width)), Image.LANCZOS)
        tiles.append(Tile(lg.convert('RGBA'), (W - 640) // 2, 520, 0.1))
        card, d = _glass(W - 120, 300)
        d.text(((W - 120) // 2, 78), 'VISIT THE PAGE FOR FULL DETAILS', font=_font('bebas', 70), fill=WHITE, anchor='mm')
        d.text(((W - 120) // 2, 146), 'Charts, data and news on every post - follow!', font=_font('SemiBold', 38),
               fill=MUTE, anchor='mm')

        def live(dd, x, y0, t, e):                  # pulsing follow button
            import math
            s = 1 + 0.04 * math.sin(t * 6)
            bw, bh = 420 * s, 78 * s
            cx, cy = x + (W - 120) / 2, y0 + 236
            dd.rounded_rectangle([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], radius=bh / 2, fill=SAFFRON)
            dd.text((cx, cy + 2), config.BRAND['handle'], font=_font('Bold', 40), fill=INK, anchor='mm')
        tiles.append(Tile(card, 60, 560 + lg.height + 40, 0.5, live))
    top = min(t.y for t in tiles)
    bottom = max(t.y + t.im.height for t in tiles)
    shift = (270 + 1400) / 2 - (top + bottom) / 2
    if top + shift < 270:
        shift = 270 - top
    for t in tiles:
        t.y += shift
    return tiles


def _min_time(sc):
    if sc['type'] == 'rows':
        return 1.8 + 0.45 * len(sc.get('rows', []))
    if sc['type'] == 'duo':
        return 3.6
    return 2.6


def _subtitle_chunks(text, n_words=4):
    words = voice.clean(text).split()
    return [' '.join(words[i:i + n_words]) for i in range(0, len(words), n_words)] or ['']


def _caption(dd, chunk, frac):
    """Short, bold captions with the word being spoken in saffron (reels style)."""
    f = _font('Bold', 62)
    words = chunk.split()
    if not words:
        return
    gap = dd.textlength(' ', font=f)
    widths = [dd.textlength(w, font=f) for w in words]
    lines, cur, cw = [], [], 0
    for w, ww in zip(words, widths):
        if cur and cw + gap + ww > W - 160:
            lines.append(cur)
            cur, cw = [], 0
        cur.append((w, ww))
        cw += ww + (gap if cw else 0)
    lines.append(cur)
    cur_word = min(len(words) - 1, int(frac * len(words)))
    n = 0
    y = H - 380 - 40 * (len(lines) - 1)
    for ln in lines:
        lw = sum(ww for _, ww in ln) + gap * (len(ln) - 1)
        x = (W - lw) / 2
        for w, ww in ln:
            dd.text((x, y), w, font=f, fill=SAFFRON if n == cur_word else WHITE, anchor='lm',
                    stroke_width=5, stroke_fill=(0, 0, 0))
            x += ww + gap
            n += 1
        y += 80


def _header(frame, label, idx, n, t_frac):
    d = ImageDraw.Draw(frame)
    seg = (W - 120 - 10 * (n - 1)) / n
    for i in range(n):
        x0 = 60 + i * (seg + 10)
        d.rounded_rectangle([x0, 60, x0 + seg, 67], radius=4, fill=(255, 255, 255, 80))
        fill = 1.0 if i < idx else t_frac if i == idx else 0
        if fill > 0:
            d.rounded_rectangle([x0, 60, x0 + seg * fill, 67], radius=4, fill=WHITE)
    frame.alpha_composite(_header.logo, (60, 100))
    f = _font('cond', 34)
    tw = d.textlength(label.upper(), font=f)
    d.rounded_rectangle([W - 60 - tw - 66, 106, W - 60, 162], radius=28, fill=GLASS + (215,), outline=(255, 255, 255, 60),
                        width=2)
    d.ellipse([W - 60 - tw - 44, 126, W - 60 - tw - 28, 142], fill=DNC)        # 'live' dot
    d.text((W - 82, 135), label.upper(), font=f, fill=WHITE, anchor='rm')


def _ticker_items(scenes):
    items, seen = [], set()
    for sc in scenes:
        for r in (sc.get('rows') or []):
            if sc.get('topic') in ('indices', 'global', 'commodities') and r.get('pct') is not None \
                    and r['label'] not in seen:
                seen.add(r['label'])
                items.append((r['label'], r.get('value') or '', r['pct']))
    return items[:12]


def _ticker_strip(items):
    """One long strip image: LABEL value +0.48%  •  ... (scrolls along the bottom-of-header band)."""
    f1, f2 = _font('cond', 34), _font('bebas', 40)
    tmp = ImageDraw.Draw(Image.new('RGBA', (10, 10)))
    parts = []
    for lab, val, p in items:
        parts.append((lab.upper() + '  ', f1, MUTE))
        if val:
            parts.append((val + '  ', f2, WHITE))
        parts.append((('▲ ' if p >= 0 else '▼ ') if False else '', f1, WHITE))
        parts.append((f'{p:+.2f}%', f2, chg_col(p)))
        parts.append(('     •     ', f1, (90, 100, 120)))
    w = int(sum(tmp.textlength(t, font=f) for t, f, _ in parts)) + 10
    im = Image.new('RGBA', (w, 56), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = 0
    for t, f, c in parts:
        d.text((x, 30), t, font=f, fill=c, anchor='lm')
        x += d.textlength(t, font=f)
    return im


def _vignette():
    y, x = np.mgrid[0:H, 0:W]
    r = np.sqrt(((x - W / 2) / (W * 0.75)) ** 2 + ((y - H / 2) / (H * 0.7)) ** 2)
    a = (np.clip(r - 0.55, 0, 1) * 260).clip(0, 150).astype(np.uint8)
    im = np.zeros((H, W, 4), np.uint8)
    im[..., 3] = a
    return Image.fromarray(im, 'RGBA')


def _sweep():
    """A soft diagonal light band that glides across each new scene."""
    w = 520
    g = np.exp(-((np.arange(w) - w / 2) / (w / 5)) ** 2)
    a = (g * 38).astype(np.uint8)
    im = np.zeros((H, w, 4), np.uint8)
    im[..., :3] = 255
    im[..., 3] = a[None, :]
    return Image.fromarray(im, 'RGBA').rotate(12, expand=False)


def build(scenes, label, out_path, seed='reel'):
    """scenes: list of dicts (type, voice text, topic, tone, + type fields). Returns (path, report lines)."""
    rep = []
    work = Path(tempfile.mkdtemp(prefix='reel-'))
    lg = cards.logo().convert('RGBA')
    _header.logo = lg.resize((240, int(lg.height * 240 / lg.width)), Image.LANCZOS)
    vig, sweep = _vignette(), _sweep()
    titems = _ticker_items(scenes)
    tstrip = _ticker_strip(titems) if len(titems) >= 3 else None
    # 1) voice per scene -> durations
    engine = None
    durs, wavs = [], []
    for i, sc in enumerate(scenes):
        if sc.get('voice'):
            mp3, eng = voice.speak(voice.speech(sc['voice']), work / f'v{i}.mp3')
            engine = engine or (eng if mp3 else None)
            spoken = voice.duration(mp3) if mp3 else max(1.5, len(sc['voice'].split()) / 2.7)
            d = round(max(spoken + 0.7, _min_time(sc)), 2)   # short voice, but enough time to read the screen
        else:                                     # on-screen list only: no voice, held for a few seconds
            mp3, d = None, float(sc.get('hold', 3.0))
        durs.append(d)
        wav = work / f'a{i}.wav'
        src = ['-i', str(mp3)] if mp3 else ['-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono']
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', *src, '-af', 'adelay=350,apad', '-t', str(d),
                        '-ar', '44100', '-ac', '1', str(wav)], check=True)
        wavs.append(wav)
    if engine:
        rep.append(('ok', f'voice-over: {voice.current()[0] if engine == "edge" else "Google (fallback voice)"}'))
    else:
        rep.append(('warn', 'voice-over unavailable - reel has background music only'))
    lst = work / 'list.txt'
    lst.write_text(''.join(f"file '{w}'\n" for w in wavs))
    total = sum(durs)
    voice_wav = work / 'voice.wav'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(lst), str(voice_wav)],
                   check=True)
    # soft original music bed (generated chords, no copyright), low under the voice
    audio = work / 'mix.m4a'
    pad = ("sine=f=196:d={T},volume=0.05[a];sine=f=246.94:d={T},volume=0.04[b];sine=f=293.66:d={T},volume=0.035[c];"
           "[a][b][c]amix=inputs=3,tremolo=f=0.25:d=0.5,lowpass=f=900,afade=t=in:d=1.5,afade=t=out:st={F}:d=1.5[m];"
           "[0:a][m]amix=inputs=2:duration=first:weights=1 0.6[out]").format(T=total, F=max(0, total - 1.5))
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(voice_wav), '-filter_complex', pad, '-map', '[out]',
                    '-c:a', 'aac', '-b:a', '128k', str(audio)], check=True)
    # 2) frames -> ffmpeg
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
                             '-r', str(FPS), '-i', '-', '-i', str(audio), '-c:v', 'libx264', '-preset', 'veryfast',
                             '-crf', '26', '-pix_fmt', 'yuv420p', '-c:a', 'copy', '-shortest', '-movflags', '+faststart',
                             str(out_path)], stdin=subprocess.PIPE)
    cover = None
    prev = None
    gk = 0                                                        # frame counter for the whole reel (ticker)
    try:
        for i, sc in enumerate(scenes):
            bg = background(sc.get('topic', 'indices'), sc.get('tone'), f'{seed}-{i}')
            tiles = scene_tiles(sc)
            chunks = _subtitle_chunks(sc['voice'])
            n = int(durs[i] * FPS)
            drift = (-1) ** i * 40                                 # alternate slow pan direction per scene
            for k in range(n):
                t = k / FPS
                z = 1 + 0.07 * (k / max(1, n - 1))                     # slow zoom in
                cw, ch = int(1188 / z), int(2112 / z)
                x0 = (1188 - cw) // 2 + int(drift * (k / max(1, n - 1) - 0.5))
                x0 = max(0, min(1188 - cw, x0))
                y0 = (2112 - ch) // 2
                frame = bg.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.BILINEAR).convert('RGBA')
                frame.alpha_composite(vig)
                if t < 1.6:                                       # light sweep as the scene opens
                    sx = int(-560 + (W + 600) * (t / 1.6))
                    frame.alpha_composite(sweep, (max(-sweep.width + 1, min(W - 1, sx)), 0)) if -sweep.width < sx < W else None
                _header(frame, label, i, len(scenes), t / durs[i])
                if tstrip is not None:                            # scrolling ticker under the header
                    d0 = ImageDraw.Draw(frame)
                    d0.rectangle([0, 186, W, 242], fill=GLASS + (190,))
                    d0.rectangle([0, 186, 150, 242], fill=SAFFRON)
                    off = int(gk * 4) % tstrip.width
                    band = Image.new('RGBA', (W - 150, 56), (0, 0, 0, 0))
                    band.alpha_composite(tstrip, (-off, 0))
                    if tstrip.width - off < W:
                        band.alpha_composite(tstrip, (tstrip.width - off, 0))
                    frame.alpha_composite(band, (150, 186))
                    d0.text((75, 214), 'MARKETS', font=_font('cond', 30), fill=INK, anchor='mm')
                for tl in tiles:
                    tl.draw(frame, t)
                if sc.get('voice'):
                    spoken = max(0.5, durs[i] - 0.7)
                    pos = min(0.999, max(0.0, (t - 0.35) / spoken)) * len(chunks)
                    ci = min(len(chunks) - 1, int(pos))
                    _caption(ImageDraw.Draw(frame), chunks[ci], pos - ci)
                rgb = frame.convert('RGB')
                if prev is not None and k < 8:                    # quick zoom-dissolve from the last scene
                    a = (k + 1) / 9
                    pz = prev.resize((int(W * (1 + 0.06 * a)), int(H * (1 + 0.06 * a))), Image.BILINEAR)
                    pz = pz.crop(((pz.width - W) // 2, (pz.height - H) // 2, (pz.width - W) // 2 + W,
                                  (pz.height - H) // 2 + H))
                    rgb = Image.blend(pz, rgb, ease(a))
                if cover is None and i == 0 and k == min(n - 1, int(2.2 * FPS)):
                    cover = rgb.copy()
                proc.stdin.write(rgb.tobytes())
                gk += 1
            prev = rgb
    finally:
        proc.stdin.close()
        proc.wait()
        shutil.rmtree(work, ignore_errors=True)
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError('video encoding failed')
    rep.append(('ok', f'reel: {len(scenes)} scenes, {total:.0f} s, {out_path.stat().st_size / 1e6:.1f} MB'))
    log.info('reel built %s (%.0f s)', out_path, total)
    return out_path, cover, rep, total
