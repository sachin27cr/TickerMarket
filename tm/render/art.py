"""Generated background art (no stock photos, no AI images, no copyright issues).

theme: 'market_up' | 'market_down' | 'solar' | 'bank' | 'ipo' | 'tech' | 'oil' | 'gold'
Every image is drawn from a seed, so the same story always gets the same picture and
different stories get different skylines and charts.
"""
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

UP = (22, 199, 132)
DOWN = (234, 57, 67)
GOLD = (251, 183, 9)


def _sky(w, h, top, bottom):
    t = np.linspace(0, 1, h)[:, None, None]
    arr = (np.array(top)[None, None, :] * (1 - t) + np.array(bottom)[None, None, :] * t)
    return Image.fromarray(np.repeat(arr, w, axis=1).astype(np.uint8), 'RGB')


def _glow(base, layer, radius=14, strength=1.6):
    """Add `layer` (RGBA) to base with a soft glow."""
    g = layer.filter(ImageFilter.GaussianBlur(radius))
    a = np.array(g).astype(float)
    a[..., 3] = np.clip(a[..., 3] * strength, 0, 255)
    base.alpha_composite(Image.fromarray(a.astype(np.uint8), 'RGBA'))
    base.alpha_composite(layer)


def _skyline(w, h, rng, y_base, max_h, color=(8, 14, 30), lit=(255, 205, 120)):
    lay = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    x = -20
    while x < w:
        bw = rng.randint(50, 130)
        bh = rng.randint(int(max_h * 0.3), max_h)
        top = y_base - bh
        d.rectangle([x, top, x + bw, y_base], fill=color + (255,))
        if rng.random() < 0.3:                                   # antenna / spire
            d.rectangle([x + bw // 2 - 2, top - rng.randint(20, 60), x + bw // 2 + 2, top], fill=color + (255,))
        for wy in range(top + 12, y_base - 8, 16):
            for wx in range(x + 8, x + bw - 8, 14):
                if rng.random() < 0.28:
                    a = rng.randint(90, 220)
                    d.rectangle([wx, wy, wx + 5, wy + 7], fill=lit + (a,))
        x += bw + rng.randint(2, 10)
    return lay


def _chart(w, h, rng, trend, color, x0, x1, y_top, y_bot, n=26):
    """Glowing candlestick series + trend line + arrow."""
    lay = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    pts, v = [], 0.0
    for i in range(n):
        v += trend * 0.9 + rng.uniform(-1.4, 1.4)
        pts.append(v)
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1
    ys = [y_bot - (p - lo) / span * (y_bot - y_top) for p in pts]
    xs = [x0 + (x1 - x0) * i / (n - 1) for i in range(n)]
    cw = (x1 - x0) / n * 0.55
    for i in range(1, n):
        o, c = ys[i - 1], ys[i]
        up = c < o
        col = (UP if up else DOWN) if rng.random() < 0.8 else (DOWN if up else UP)
        if (trend > 0 and not up) or (trend < 0 and up):
            col = col if rng.random() < 0.5 else color
        top, bot = min(o, c), max(o, c) + 3
        d.line([(xs[i], top - rng.randint(6, 22)), (xs[i], bot + rng.randint(6, 22))], fill=col + (200,), width=3)
        d.rectangle([xs[i] - cw / 2, top, xs[i] + cw / 2, bot], fill=col + (235,))
    d.line(list(zip(xs, ys)), fill=color + (255,), width=8, joint='curve')
    # arrow at the end of the trend
    ax, ay = xs[-1], ys[-1]
    px, py = xs[-4], ys[-4]
    ang = math.atan2(ay - py, ax - px)
    tip = (ax + 70 * math.cos(ang), ay + 70 * math.sin(ang))
    d.line([(ax, ay), tip], fill=color + (255,), width=16)
    head = [(tip[0] + 46 * math.cos(ang), tip[1] + 46 * math.sin(ang)),
            (tip[0] + 34 * math.cos(ang + 2.3), tip[1] + 34 * math.sin(ang + 2.3)),
            (tip[0] + 34 * math.cos(ang - 2.3), tip[1] + 34 * math.sin(ang - 2.3))]
    d.polygon(head, fill=color + (255,))
    return lay


def _perspective_coeffs(src, dst):
    m = []
    for (x, y), (u, v) in zip(dst, src):
        m.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        m.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    a = np.array(m, float)
    b = np.array(src, float).reshape(8)
    return np.linalg.solve(a, b)


def _solar_field(w, h, y_horizon):
    flat = Image.new('RGBA', (1600, 900), (0, 0, 0, 0))
    d = ImageDraw.Draw(flat)
    for row in range(6):
        for col in range(10):
            x, y = 20 + col * 158, 20 + row * 148
            d.rectangle([x, y, x + 148, y + 136], fill=(20, 52, 120, 255), outline=(150, 175, 220, 255), width=4)
            for k in range(1, 4):
                d.line([(x + k * 37, y), (x + k * 37, y + 136)], fill=(90, 120, 190, 255), width=2)
            for k in range(1, 3):
                d.line([(x, y + k * 45), (x + 148, y + k * 45)], fill=(90, 120, 190, 255), width=2)
            d.polygon([(x + 10, y + 8), (x + 60, y + 8), (x + 20, y + 60)], fill=(255, 255, 255, 40))
    dst = [(w * 0.05, y_horizon), (w * 1.05, y_horizon), (w * 1.5, y_horizon + h * 0.30), (-w * 0.5, y_horizon + h * 0.30)]
    src = [(0, 0), (1600, 0), (1600, 900), (0, 900)]
    return flat.transform((w, h), Image.PERSPECTIVE, _perspective_coeffs(src, dst), Image.BICUBIC)


def _bank_facade(w, h, x0, x1, y_top, y_bot, color=(200, 205, 215)):
    lay = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    mid = (x0 + x1) / 2
    d.polygon([(x0 - 20, y_top + 90), (mid, y_top), (x1 + 20, y_top + 90)], fill=color + (255,))
    d.rectangle([x0 - 10, y_top + 90, x1 + 10, y_top + 115], fill=color + (255,))
    n = 6
    for i in range(n):
        cx = x0 + 20 + (x1 - x0 - 40) * i / (n - 1)
        d.rectangle([cx - 18, y_top + 125, cx + 18, y_bot - 20], fill=color + (255,))
        d.rectangle([cx - 24, y_top + 115, cx + 24, y_top + 128], fill=color + (255,))
    d.rectangle([x0 - 30, y_bot - 20, x1 + 30, y_bot], fill=color + (255,))
    return lay


POST_KIND = None          # set by the job that is rendering (see set_post); picks the scene pool
SECTOR_THEMES = {'solar', 'bank', 'ipo', 'tech', 'oil', 'gold'}


def set_post(kind):
    global POST_KIND
    POST_KIND = kind


def as_post(kind):
    """Decorator for a job: its images use that post type's scene pool."""
    import functools

    def wrap(fn):
        @functools.wraps(fn)
        def inner(*a, **k):
            global POST_KIND
            prev, POST_KIND = POST_KIND, kind
            try:
                return fn(*a, **k)
            finally:
                POST_KIND = prev
        return inner
    return wrap


def background(theme, w=1080, h=1350, seed=0, tone=None):
    """tone: 'up' | 'down' sets the chart direction and colour; default depends on the theme.
    Data posts and insights draw a scene from their own pool (scenes.py), rotating daily; news about a
    specific sector keeps its sector picture."""
    from . import scenes
    rng = random.Random(f'{theme}-{seed}')
    down = theme in ('market_down', 'solar', 'oil')
    if tone in ('up', 'down'):
        down = tone == 'down'
    colr = DOWN if down else UP
    kind = POST_KIND or 'news'
    from . import own_bg, photo
    mine = own_bg.pick(own_bg.folder_for(kind), 'down' if down else 'up', seed)
    if mine is not None:                         # your own pictures in assets/backgrounds come first
        return _photo_background(own_bg.cover(mine, w, w), w, h)
    if photo.enabled():                          # photo-realistic scene when Cloudflare is set up
        pic = photo.get(photo.prompt_for(kind, 'down' if down else 'up', seed))
        if pic is not None:
            return _photo_background(pic, w, h)
    if not (kind == 'news' and theme in SECTOR_THEMES):
        from ..util import today_ist
        scene = scenes.pick(kind, theme, seed, today_ist().toordinal())
        return _scene_background(scene, kind, w, h, rng, not down, colr)
    sky_top = (40, 18, 30) if down else (10, 40, 70)
    im = _sky(w, h, sky_top, (3, 8, 20)).convert('RGBA')
    # light source
    glow = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    gx, gy = rng.randint(w // 4, 3 * w // 4), int(h * 0.12)
    ImageDraw.Draw(glow).ellipse([gx - 260, gy - 260, gx + 260, gy + 260],
                                 fill=((255, 120, 90) if down else (90, 170, 255)) + (70,))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(90)))
    # faint grid of a trading screen
    grid = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    for x in range(0, w, 60):
        gd.line([(x, 0), (x, h * 0.6)], fill=(120, 150, 200, 18))
    for y in range(0, int(h * 0.6), 60):
        gd.line([(0, y), (w, y)], fill=(120, 150, 200, 18))
    im.alpha_composite(grid)

    if theme == 'solar':
        im.alpha_composite(_skyline(w, h, rng, int(h * 0.30), 140, color=(12, 18, 34)))
        im.alpha_composite(_solar_field(w, h, int(h * 0.29)))
    elif theme == 'bank':
        im.alpha_composite(_skyline(w, h, rng, int(h * 0.50), 240))
        im.alpha_composite(_bank_facade(w, h, w * 0.52, w * 0.92, int(h * 0.20), int(h * 0.50), color=(150, 158, 175)))
    else:
        im.alpha_composite(_skyline(w, h, rng, int(h * 0.50), 330))
    _glow(im, _chart(w, h, rng, -1 if down else 1, colr, w * 0.05, w * 0.80, h * 0.10, h * 0.40))
    if theme == 'ipo':
        conf = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        cd = ImageDraw.Draw(conf)
        for _ in range(140):
            x, y = rng.randint(0, w), rng.randint(0, int(h * 0.5))
            c = rng.choice([GOLD, UP, (255, 255, 255), (255, 153, 51)])
            cd.rectangle([x, y, x + rng.randint(4, 10), y + rng.randint(8, 16)], fill=c + (rng.randint(120, 230),))
        im.alpha_composite(conf)
    return _finish(im, rng, w, h)


def _photo_background(pic, w, h):
    from PIL import ImageEnhance
    side = w
    pic = pic.resize((side, side), Image.LANCZOS)
    pic = ImageEnhance.Brightness(pic).enhance(0.88)
    im = Image.new('RGBA', (w, h), (3, 10, 23, 255))
    im.paste(pic, (0, 0))
    fade = np.zeros((h, w, 4), np.uint8)
    fade[..., :3] = (3, 10, 23)
    t = np.clip((np.arange(h) - h * 0.42) / (h * 0.20), 0, 1)
    fade[..., 3] = (t[:, None] * 255).astype(np.uint8)
    im.alpha_composite(Image.fromarray(fade, 'RGBA'))
    top = np.zeros((h, w, 4), np.uint8)              # light shade at the top so the category tag stays readable
    top[..., 3] = (np.clip(1 - np.arange(h) / (h * 0.12), 0, 1) * 110).astype(np.uint8)[:, None]
    im.alpha_composite(Image.fromarray(top, 'RGBA'))
    return im.convert('RGB')


def _scene_background(scene, kind, w, h, rng, up, colr):
    from . import scenes
    top, bottom, light = scenes.PALETTES.get(scene, ((10, 40, 70), (3, 8, 20), (90, 170, 255)))
    if not up:                                   # warmer, darker sky on red days
        top = tuple(int(0.6 * a + 0.4 * b) for a, b in zip(top, (60, 14, 24)))
    im = _sky(w, h, top, bottom).convert('RGBA')
    g = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    gx, gy = rng.randint(w // 4, 3 * w // 4), int(h * 0.12)
    ImageDraw.Draw(g).ellipse([gx - 280, gy - 280, gx + 280, gy + 280], fill=light + (70,))
    im.alpha_composite(g.filter(ImageFilter.GaussianBlur(100)))
    scenes.draw(scene, im, rng, up, colr, kind)
    return _finish(im, rng, w, h)


def _finish(im, rng, w, h):
    # bokeh
    bok = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bok)
    for _ in range(26):
        x, y, r = rng.randint(0, w), rng.randint(0, int(h * 0.55)), rng.randint(6, 26)
        bd.ellipse([x - r, y - r, x + r, y + r], fill=(255, 220, 160, rng.randint(20, 60)))
    im.alpha_composite(bok.filter(ImageFilter.GaussianBlur(4)))
    # fade to the page colour so text below is readable
    fade = np.zeros((h, w, 4), np.uint8)
    fade[..., :3] = (3, 10, 23)
    t = np.clip((np.arange(h) - h * 0.40) / (h * 0.18), 0, 1)
    fade[..., 3] = (t[:, None] * 255).astype(np.uint8)
    im.alpha_composite(Image.fromarray(fade, 'RGBA'))
    # vignette
    vy, vx = np.ogrid[:h, :w]
    vig = ((vx - w / 2) ** 2 / (w * 0.75) ** 2 + (vy - h * 0.3) ** 2 / (h * 0.7) ** 2)
    v = np.zeros((h, w, 4), np.uint8)
    v[..., 3] = np.clip(vig * 140, 0, 160).astype(np.uint8)
    im.alpha_composite(Image.fromarray(v, 'RGBA'))
    return im.convert('RGB')
