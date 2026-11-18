"""Scene library for post backgrounds: Indian stock market motifs drawn in code (no photos, no logos,
no AI images). Each post type has its own pool of scenes and rotates through them day by day, so
posts do not all look alike and the same post type looks different on consecutive days.

A scene draws into the top ~45% of a 1080x1350 canvas; art.background() then fades the lower part into
the page colour so text stays readable. Decorative text never contains numbers (so it can never be
mistaken for data).
"""
import math
import zlib

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .. import config

UP = (22, 199, 132)
DOWN = (234, 57, 67)
GOLD = (251, 183, 9)
SAFFRON = (255, 153, 51)
WHITE = (255, 255, 255)
FONTS = config.ROOT / 'assets' / 'fonts'

# post kind -> scenes it rotates through
POOLS = {   # text-free scenes only: pictures with words in them fight with the data on the slide
    'global_cues': ['globe', 'goldbars', 'candles'],
    'day_ahead': ['calendar', 'bell', 'candles'],
    'market_close': ['dalal', 'candles', 'arrows'],
    'cap_movers': ['heatmap', 'bars3d', 'arrows'],
    'daily_overview': ['peaks', 'candles', 'bars3d'],
    'fii_dii': ['flows', 'rupee', 'globe'],
    'ipo': ['bell', 'confetti', 'dalal'],
    'ipo_status': ['bell', 'bars3d', 'confetti'],
    'weekly_ath': ['peaks', 'arrows'],
    'weekly_lows': ['peaks', 'arrows'],
    'insight_profits': ['bars3d', 'rupee', 'arrows'],
    'insight_assets': ['goldbars', 'globe', 'coins'],
    'insight_mcap': ['dalal', 'coins', 'bars3d'],
    'insight_wealth': ['coins', 'rupee', 'peaks'],
    'insight_sectors': ['heatmap', 'bars3d', 'candles'],
    'news': ['candles', 'dalal', 'arrows', 'bars3d', 'globe', 'rupee'],
}
# background words per post kind (faint, decorative)
WORDS = {
    'global_cues': ['DOW JONES', 'NASDAQ', 'NIKKEI', 'BRENT', 'GOLD', 'DOLLAR'],
    'day_ahead': ['OPENING BELL', 'RESULTS', 'EX-DATE', 'IPO', 'NSE', 'BSE'],
    'market_close': ['SENSEX', 'NIFTY', 'BSE', 'NSE', 'DALAL STREET', 'CLOSING BELL'],
    'cap_movers': ['LARGE CAP', 'MID CAP', 'SMALL CAP', 'MICRO CAP', 'GAINERS', 'LOSERS'],
    'daily_overview': ['ALL-TIME HIGH', '52-WEEK LOW', 'NIFTY', 'SENSEX', 'MIDCAP', 'SMALLCAP'],
    'fii_dii': ['FII', 'DII', '₹ CRORE', 'F&O', 'FUTURES', 'OPTIONS'],
    'ipo': ['IPO', 'LISTING', 'PRICE BAND', 'LOT SIZE', 'SUBSCRIBE', 'NSE'],
    'ipo_status': ['IPO', 'QIB', 'NII', 'RETAIL', 'BIDS', 'SUBSCRIPTION'],
    'weekly_ath': ['ALL-TIME HIGH', 'BULL RUN', 'NEW PEAK', 'NIFTY'],
    'weekly_lows': ['52-WEEK LOW', 'BEAR', 'SELL-OFF', 'NIFTY'],
    'insight_profits': ['NET PROFIT', 'REVENUE', 'RESULTS', 'YoY', 'EARNINGS'],
    'insight_assets': ['GOLD', 'SILVER', 'CRUDE', 'RUPEE', 'NIFTY', 'BITCOIN'],
    'insight_mcap': ['MARKET CAP', '₹ LAKH CRORE', 'BLUE CHIP', 'NSE', 'BSE'],
    'insight_wealth': ['WEALTH', '₹ LAKH', 'NIFTY', 'COMPOUNDING', 'RETURNS'],
    'insight_sectors': ['IT', 'BANK', 'AUTO', 'PHARMA', 'FMCG', 'METAL', 'REALTY', 'ENERGY'],
    'news': ['NSE', 'BSE', 'SENSEX', 'NIFTY', 'DALAL STREET', '₹', 'STOCKS'],
}
# palettes: (sky top, sky bottom, glow)
PALETTES = {
    'globe': ((6, 36, 60), (3, 8, 20), (60, 200, 255)), 'tape': ((14, 20, 48), (3, 8, 20), (120, 140, 255)),
    'words': ((26, 16, 50), (3, 8, 20), (170, 110, 255)), 'calendar': ((4, 44, 52), (3, 8, 20), (40, 210, 200)),
    'bell': ((44, 22, 60), (4, 6, 20), (255, 190, 80)), 'board': ((10, 18, 28), (3, 8, 20), (255, 140, 40)),
    'dalal': ((52, 28, 40), (3, 8, 20), (255, 150, 80)), 'candles': ((10, 40, 70), (3, 8, 20), (90, 170, 255)),
    'arrows': ((8, 40, 36), (3, 8, 20), (60, 230, 160)), 'heatmap': ((16, 20, 30), (3, 8, 20), (120, 220, 160)),
    'bars3d': ((10, 26, 60), (3, 8, 20), (90, 160, 255)), 'peaks': ((30, 26, 66), (3, 8, 20), (255, 200, 120)),
    'flows': ((10, 22, 58), (3, 8, 20), (90, 120, 255)), 'rupee': ((50, 30, 8), (3, 8, 20), (255, 180, 60)),
    'confetti': ((40, 14, 54), (3, 8, 20), (255, 120, 200)), 'goldbars': ((48, 34, 6), (3, 8, 20), (255, 200, 80)),
    'coins': ((40, 30, 10), (3, 8, 20), (255, 190, 70)),
}


def _font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def pick(kind, theme, seed, day_ordinal):
    """Scene for this post: rotates daily per post type; news varies per story."""
    pool = POOLS.get(kind) or POOLS['news']
    if kind == 'news' or kind not in POOLS:
        i = zlib.crc32(str(seed).encode()) % len(pool)
    else:
        i = (day_ordinal + zlib.crc32(kind.encode())) % len(pool)
    return pool[i]


def layer(w, h):
    return Image.new('RGBA', (w, h), (0, 0, 0, 0))


def glow(base, lay, radius=14, strength=1.6):
    g = lay.filter(ImageFilter.GaussianBlur(radius))
    a = np.array(g).astype(float)
    a[..., 3] = np.clip(a[..., 3] * strength, 0, 255)
    base.alpha_composite(Image.fromarray(a.astype(np.uint8), 'RGBA'))
    base.alpha_composite(lay)


def tri(d, x, y, s, up, fill):
    if up:
        d.polygon([(x, y + s), (x + s, y + s), (x + s / 2, y)], fill=fill)
    else:
        d.polygon([(x, y), (x + s, y), (x + s / 2, y + s)], fill=fill)


# ---------------------------------------------------------------- word layer (all scenes)

def words(im, rng, kind, alpha=14, y_max=0.32):
    w, h = im.size
    lay = layer(w, h)
    d = ImageDraw.Draw(lay)
    terms = WORDS.get(kind) or WORDS['news']
    for _ in range(3):
        t = rng.choice(terms)
        f = _font('BebasNeue-Regular.ttf', rng.randint(70, 190))
        x, y = rng.randint(-120, w - 200), rng.randint(-20, int(h * y_max))
        d.text((x, y), t, font=f, fill=(255, 255, 255, rng.randint(alpha // 2, alpha)))
    im.alpha_composite(lay)


# ---------------------------------------------------------------- scenes

def s_candles(im, rng, up, colr):
    from .art import _chart, _skyline
    w, h = im.size
    im.alpha_composite(_skyline(w, h, rng, int(h * 0.50), 330))
    glow(im, _chart(w, h, rng, 1 if up else -1, colr, w * 0.05, w * 0.80, h * 0.10, h * 0.40))


def s_dalal(im, rng, up, colr):
    """Dalal Street at dusk: one tall exchange-style tower among smaller blocks (generic, no logo)."""
    from .art import _skyline
    w, h = im.size
    im.alpha_composite(_skyline(w, h, rng, int(h * 0.50), 220, color=(14, 12, 26)))
    lay = layer(w, h)
    d = ImageDraw.Draw(lay)
    cx, top, base_y = int(w * rng.uniform(0.55, 0.72)), int(h * 0.06), int(h * 0.50)
    tw = 230
    d.polygon([(cx - tw // 2, base_y), (cx - tw // 2 + 18, top + 40), (cx + tw // 2 - 18, top + 40), (cx + tw // 2, base_y)],
              fill=(22, 20, 36, 255))
    d.rectangle([cx - tw // 2 + 30, top, cx + tw // 2 - 30, top + 40], fill=(22, 20, 36, 255))
    d.rectangle([cx - 4, top - 70, cx + 4, top], fill=(22, 20, 36, 255))
    for yy in range(top + 56, base_y - 10, 22):
        for xx in range(cx - tw // 2 + 30, cx + tw // 2 - 30, 18):
            if rng.random() < 0.55:
                d.rectangle([xx, yy, xx + 9, yy + 12], fill=(255, 200, 120, rng.randint(110, 240)))
    # LED ticker band on the tower
    d.rectangle([cx - tw // 2 + 10, top + 120, cx + tw // 2 - 10, top + 160], fill=(5, 8, 16, 255))
    f = _font('BebasNeue-Regular.ttf', 32)
    x = cx - tw // 2 + 18
    for word, u in [('SENSEX', up), ('NIFTY', up), ('BANK', not up)]:
        d.text((x, top + 140), word, font=f, fill=(UP if u else DOWN) + (255,), anchor='lm')
        x += d.textlength(word, font=f) + 6
        tri(d, x, top + 130, 18, u, (UP if u else DOWN) + (255,))
        x += 28
    glow(im, lay, 10, 1.2)
    # street lights
    lay2 = layer(w, h)
    d2 = ImageDraw.Draw(lay2)
    for i in range(14):
        x = int(w * i / 13)
        d2.ellipse([x - 6, base_y - 4, x + 6, base_y + 8], fill=(255, 200, 120, 220))
    glow(im, lay2, 12, 2)
    f = _font('BebasNeue-Regular.ttf', 54)
    ImageDraw.Draw(im).text((60, base_y - 70), 'DALAL STREET', font=f, fill=(255, 220, 170, 70))


def s_tape(im, rng, up, colr):
    """Diagonal ticker tapes with index names and up/down arrows."""
    w, h = im.size
    big = layer(w * 2, h)
    d = ImageDraw.Draw(big)
    names = ['NIFTY 50', 'SENSEX', 'BANK NIFTY', 'NIFTY IT', 'MIDCAP', 'SMALLCAP', 'FIN NIFTY', 'NIFTY AUTO',
             'NIFTY PHARMA', 'NIFTY METAL', 'INDIA VIX', 'NIFTY FMCG']
    f = _font('BebasNeue-Regular.ttf', 58)
    for k, y in enumerate(range(40, int(h * 0.55), 120)):
        d.rectangle([0, y, w * 2, y + 80], fill=(8, 14, 30, 210))
        d.line([(0, y), (w * 2, y)], fill=GOLD + (120,), width=2)
        x = rng.randint(-200, 0)
        while x < w * 2:
            n = rng.choice(names)
            u = rng.random() < (0.7 if up else 0.3)
            d.text((x, y + 40), n, font=f, fill=WHITE + (200,), anchor='lm')
            x += d.textlength(n, font=f) + 16
            tri(d, x, y + 26, 28, u, (UP if u else DOWN) + (255,))
            x += 70
    rot = big.rotate(-12, resample=Image.BICUBIC, center=(w, h * 0.25))
    im.alpha_composite(rot.crop((w // 2, 0, w // 2 + w, h)))


def s_board(im, rng, up, colr):
    """Exchange display board: grid of index tiles with arrows and mini bars (no numbers)."""
    w, h = im.size
    lay = layer(w, h)
    d = ImageDraw.Draw(lay)
    names = ['NIFTY', 'SENSEX', 'BANKNIFTY', 'FINNIFTY', 'MIDCAP', 'SMALLCAP', 'IT', 'AUTO', 'PHARMA', 'METAL',
             'FMCG', 'REALTY', 'ENERGY', 'MEDIA', 'PSU BANK', 'INFRA']
    f = _font('BarlowCondensed-Bold.ttf', 34)
    cols, cw, ch = 4, 250, 110
    for r in range(5):
        for c in range(cols):
            x, y = 30 + c * (cw + 12), 30 + r * (ch + 12)
            u = rng.random() < (0.68 if up else 0.32)
            col = UP if u else DOWN
            d.rounded_rectangle([x, y, x + cw, y + ch], radius=10, fill=(10, 14, 22, 230), outline=col + (150,), width=2)
            d.text((x + 16, y + 30), rng.choice(names), font=f, fill=(255, 210, 120, 230), anchor='lm')
            tri(d, x + cw - 46, y + 16, 28, u, col + (255,))
            for b in range(10):
                bh = rng.randint(8, 40)
                d.rectangle([x + 16 + b * 20, y + ch - 14 - bh, x + 28 + b * 20, y + ch - 14], fill=col + (170,))
    # perspective tilt: shrink top
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    dst = [(w * 0.08, 0), (w * 0.92, 0), (w * 1.05, h), (-w * 0.05, h)]
    from .art import _perspective_coeffs
    lay = lay.transform((w, h), Image.PERSPECTIVE, _perspective_coeffs(src, dst), Image.BICUBIC)
    glow(im, lay, 8, 1.1)


def s_globe(im, rng, up, colr):
    """Wireframe globe with glowing market cities and arcs."""
    w, h = im.size
    lay = layer(w, h)
    d = ImageDraw.Draw(lay)
    cx, cy, r = int(w * rng.uniform(0.55, 0.7)), int(h * 0.26), 300
    c = (80, 200, 255)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c + (220,), width=3)
    for k in range(1, 6):
        rx = int(r * math.cos(math.pi * k / 12))
        d.ellipse([cx - rx, cy - r, cx + rx, cy + r], outline=c + (90,), width=2)
    for k in range(-3, 4):
        yy = cy + int(r * math.sin(math.pi * k / 8))
        hw = int(r * math.cos(math.pi * k / 8))
        d.ellipse([cx - hw, yy - 12, cx + hw, yy + 12], outline=c + (90,), width=2)
    pts = [(cx + int(r * rng.uniform(-0.8, 0.8)), cy + int(r * rng.uniform(-0.7, 0.7))) for _ in range(7)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        mx, my = (x1 + x2) / 2, min(y1, y2) - 120
        arc = [((1 - t) ** 2 * x1 + 2 * (1 - t) * t * mx + t * t * x2, (1 - t) ** 2 * y1 + 2 * (1 - t) * t * my + t * t * y2)
               for t in np.linspace(0, 1, 30)]
        d.line(arc, fill=GOLD + (200,), width=3)
    for x, y in pts:
        d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=GOLD + (255,))
    glow(im, lay, 12, 1.5)
    f = _font('BebasNeue-Regular.ttf', 40)
    dd = ImageDraw.Draw(im)
    used = []
    for (x, y), name in zip(pts, ['MUMBAI', 'NEW YORK', 'LONDON', 'TOKYO', 'HONG KONG']):
        if all(abs(x - ux) > 160 or abs(y - uy) > 50 for ux, uy in used):
            dd.text((x + 14, y - 30), name, font=f, fill=(255, 255, 255, 140))
            used.append((x, y))


def s_words(im, rng, up, colr, kind='news'):
    w, h = im.size
    words(im, rng, kind, alpha=70, y_max=0.45)
    lay = layer(w, h)
    d = ImageDraw.Draw(lay)
    for _ in range(40):
        x, y, s = rng.randint(0, w), rng.randint(0, int(h * 0.5)), rng.randint(10, 26)
        tri(d, x, y, s, rng.random() < (0.7 if up else 0.3), (UP if rng.random() < (0.7 if up else 0.3) else DOWN) + (140,))
    glow(im, lay, 6, 1.2)


def s_calendar(im, rng, up, colr):
    w, h = im.size
    lay = layer(w, h)
    d = ImageDraw.Draw(lay)
    f = _font('BebasNeue-Regular.ttf', 44)
    x0, y0, cs = 50, 60, 140
    for i, dn in enumerate(['MON', 'TUE', 'WED', 'THU', 'FRI']):
        d.text((x0 + i * (cs + 10) + cs // 2, y0), dn, font=f, fill=(150, 240, 230, 200), anchor='mm')
    hi = (rng.randrange(3), rng.randrange(5))
    for r in range(3):
        for c in range(5):
            x, y = x0 + c * (cs + 10), y0 + 40 + r * (cs + 10)
            on = (r, c) == hi
            d.rounded_rectangle([x, y, x + cs, y + cs], radius=16, fill=((40, 210, 200, 200) if on else (10, 40, 48, 200)),
                                outline=(80, 220, 210, 160), width=2)
            if not on and rng.random() < 0.45:
                d.ellipse([x + cs - 34, y + 14, x + cs - 16, y + 32], fill=rng.choice([GOLD, UP, SAFFRON]) + (230,))
    # clock
    cx, cy, r = w - 120, 330, 80
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=GOLD + (230,), width=6)
    d.line([(cx, cy), (cx, cy - 60)], fill=GOLD + (255,), width=6)
    d.line([(cx, cy), (cx + 45, cy + 10)], fill=GOLD + (255,), width=6)
    glow(im, lay, 10, 1.3)


def s_bell(im, rng, up, colr):
    """The opening bell: a large bell with sound rings."""
    w, h = im.size
    lay = layer(w, h)
    d = ImageDraw.Draw(lay)
    cx, top = int(w * rng.uniform(0.6, 0.75)), 70
    for k in range(4):
        rr = 230 + k * 70
        d.arc([cx - rr, top + 170 - rr, cx + rr, top + 170 + rr], 200, 340, fill=GOLD + (140 - k * 30,), width=6)
    body = [(cx - 40, top + 40)]
    for t in np.linspace(0, 1, 20):
        body.append((cx - 40 - 120 * t ** 1.6, top + 40 + 300 * t))
    body += [(cx + 160, top + 340)]
    for t in np.linspace(1, 0, 20):
        body.append((cx + 40 + 120 * t ** 1.6, top + 40 + 300 * t))
    d.polygon(body, fill=(230, 170, 40, 255))
    d.rounded_rectangle([cx - 175, top + 330, cx + 175, top + 360], radius=12, fill=(250, 200, 70, 255))
    d.ellipse([cx - 30, top + 350, cx + 30, top + 400], fill=(200, 140, 30, 255))
    d.ellipse([cx - 22, top, cx + 22, top + 44], outline=(250, 200, 70, 255), width=8)
    d.polygon([(cx - 80, top + 90), (cx - 60, top + 90), (cx - 110, top + 300), (cx - 140, top + 300)], fill=(255, 235, 170, 90))
    glow(im, lay, 18, 1.3)


def s_confetti(im, rng, up, colr):
    s_bell(im, rng, up, colr)
    w, h = im.size
    lay = layer(w, h)
    d = ImageDraw.Draw(lay)
    for _ in range(180):
        x, y = rng.randint(0, w), rng.randint(0, int(h * 0.5))
        c = rng.choice([GOLD, UP, WHITE, SAFFRON, (255, 120, 200)])
        a = rng.uniform(0, math.pi)
        l = rng.randint(8, 18)
        d.line([(x, y), (x + l * math.cos(a), y + l * math.sin(a))], fill=c + (rng.randint(140, 240),), width=5)
    im.alpha_composite(lay)


def s_arrows(im, rng, up, colr):
    """A field of rising (or falling) glowing arrows."""
    w, h = im.size
    lay = layer(w, h)
    d = ImageDraw.Draw(lay)
    for _ in range(16):
        x = rng.randint(0, w)
        L = rng.randint(120, 380)
        y = rng.randint(80, int(h * 0.5))
        th = rng.randint(10, 26)
        c = colr if rng.random() < 0.8 else (DOWN if up else UP)
        a = rng.randint(100, 230)
        if up:
            d.rectangle([x - th / 2, y - L, x + th / 2, y], fill=c + (a,))
            d.polygon([(x - th * 1.8, y - L), (x + th * 1.8, y - L), (x, y - L - th * 3)], fill=c + (a,))
        else:
            d.rectangle([x - th / 2, y - L, x + th / 2, y], fill=c + (a,))
            d.polygon([(x - th * 1.8, y), (x + th * 1.8, y), (x, y + th * 3)], fill=c + (a,))
    glow(im, lay, 14, 1.4)


def s_heatmap(im, rng, up, colr):
    """Sector heat map: nested tiles in shades of green and red."""
    w, h = im.size
    lay = layer(w, h)
    d = ImageDraw.Draw(lay)

    def split(x0, y0, x1, y1, depth):
        if depth == 0 or (x1 - x0) < 160 or (y1 - y0) < 110:
            u = rng.random() < (0.65 if up else 0.35)
            k = rng.uniform(0.35, 1.0)
            base = UP if u else DOWN
            c = tuple(int(v * k) for v in base)
            d.rectangle([x0 + 3, y0 + 3, x1 - 3, y1 - 3], fill=c + (215,))
            return
        if (x1 - x0) > (y1 - y0):
            m = rng.randint(int(x0 + (x1 - x0) * 0.35), int(x0 + (x1 - x0) * 0.65))
            split(x0, y0, m, y1, depth - 1); split(m, y0, x1, y1, depth - 1)
        else:
            m = rng.randint(int(y0 + (y1 - y0) * 0.35), int(y0 + (y1 - y0) * 0.65))
            split(x0, y0, x1, m, depth - 1); split(x0, m, x1, y1, depth - 1)
    split(20, 20, w - 20, int(h * 0.52), 5)
    im.alpha_composite(lay)


def s_bars3d(im, rng, up, colr):
    """Isometric 3D bar chart rising from a floor grid."""
    w, h = im.size
    lay = layer(w, h)
    d = ImageDraw.Draw(lay)
    floor = int(h * 0.5)
    for k in range(0, w + 400, 60):
        d.line([(k - 400, floor + 60), (k, floor - 120)], fill=(90, 160, 255, 40), width=1)
    n = 9
    for i in range(n):
        x = 80 + i * 105
        t = i / (n - 1)
        hh = int((100 + 330 * (t if up else 1 - t)) * rng.uniform(0.8, 1.1))
        c = colr if rng.random() < 0.85 else GOLD
        dk = tuple(int(v * 0.6) for v in c)
        lt = tuple(min(255, int(v * 1.25)) for v in c)
        y0 = floor - i * 8
        d.rectangle([x, y0 - hh, x + 60, y0], fill=c + (230,))
        d.polygon([(x + 60, y0), (x + 60, y0 - hh), (x + 85, y0 - hh - 18), (x + 85, y0 - 18)], fill=dk + (230,))
        d.polygon([(x, y0 - hh), (x + 60, y0 - hh), (x + 85, y0 - hh - 18), (x + 25, y0 - hh - 18)], fill=lt + (240,))
    glow(im, lay, 10, 1.2)


def s_peaks(im, rng, up, colr):
    """Mountain range at sunrise; a flag on the highest peak (new highs) or a marker in the deepest valley (lows)."""
    w, h = im.size
    sun = layer(w, h)
    sx = int(w * rng.uniform(0.25, 0.75))
    ImageDraw.Draw(sun).ellipse([sx - 150, int(h * 0.12), sx + 150, int(h * 0.12) + 300],
                                fill=((255, 190, 90) if up else (255, 110, 90)) + (230,))
    glow(im, sun, 40, 1.2)
    shades = [((92, 84, 150), 1.1), ((58, 52, 112), 0.95), ((26, 26, 60), 0.75)]
    for li, (shade, amp) in enumerate(shades):
        lay = layer(w, h)
        d = ImageDraw.Draw(lay)
        base = h * (0.40 + 0.05 * li)
        ph = rng.random() * 6
        pts = [(0, h)] + [(x, base - abs(math.sin(x / 150 + ph + li)) * 300 * amp - rng.randint(0, 40))
                          for x in range(0, w + 60, 50)] + [(w, h)]
        d.polygon(pts, fill=shade + (255,))
        # snow / light on ridges
        for (x1, y1), (x2, y2) in zip(pts[1:-2], pts[2:-1]):
            if y1 < base - 200 * amp or y2 < base - 200 * amp:
                d.line([(x1, y1), (x2, y2)], fill=(235, 238, 255, 160), width=4)
        if li == 0:
            peak = min(pts[2:-2], key=lambda p: p[1])
        im.alpha_composite(lay)
    d = ImageDraw.Draw(im)
    fx, fy = peak
    if up:                                   # flag on the summit
        pole = 150
        d.line([(fx, fy), (fx, fy - pole)], fill=WHITE + (255,), width=6)
        d.polygon([(fx, fy - pole), (fx + 110, fy - pole + 28), (fx, fy - pole + 56)], fill=colr + (255,))
    else:                                    # red arrow diving down the slope
        lay = layer(w, h)
        dl = ImageDraw.Draw(lay)
        x0, y0, x1, y1 = fx - 60, fy - 120, fx + 260, fy + 260
        dl.line([(x0, y0), (x1, y1)], fill=DOWN + (255,), width=18)
        a = math.atan2(y1 - y0, x1 - x0)
        dl.polygon([(x1 + 40 * math.cos(a), y1 + 40 * math.sin(a)), (x1 + 34 * math.cos(a + 2.3), y1 + 34 * math.sin(a + 2.3)),
                    (x1 + 34 * math.cos(a - 2.3), y1 + 34 * math.sin(a - 2.3))], fill=DOWN + (255,))
        glow(im, lay, 12, 1.4)


def s_flows(im, rng, up, colr):
    """Money flows: curved streams with ₹ particles moving in (green) or out (red)."""
    w, h = im.size
    lay = layer(w, h)
    d = ImageDraw.Draw(lay)
    f = _font('Hind-Bold.ttf', 34)
    for k in range(7):
        y0 = 60 + k * 70
        c = colr if k % 3 else (DOWN if up else UP)
        pts = [(x, y0 + 60 * math.sin(x / 180 + k)) for x in range(-20, w + 20, 10)]
        d.line(pts, fill=c + (170,), width=10 - k)
        for _ in range(4):
            px, py = rng.choice(pts)
            d.text((px, py - 22), '₹', font=f, fill=GOLD + (230,))
    glow(im, lay, 12, 1.5)


def s_rupee(im, rng, up, colr):
    """Large glowing rupee symbol with coin stacks."""
    w, h = im.size
    lay = layer(w, h)
    d = ImageDraw.Draw(lay)
    f = _font('Hind-Bold.ttf', 520)
    d.text((int(w * rng.uniform(0.62, 0.74)), int(h * 0.26)), '₹', font=f, fill=GOLD + (230,), anchor='mm')
    glow(im, lay, 26, 1.4)
    s_coins(im, rng, up, colr, x_max=0.45, scale=0.8)
    lay2 = layer(w, h)
    d2 = ImageDraw.Draw(lay2)
    f2 = _font('Hind-Bold.ttf', 40)
    for _ in range(18):
        d2.text((rng.randint(0, w), rng.randint(0, int(h * 0.5))), '₹', font=f2, fill=GOLD + (rng.randint(40, 120),))
    im.alpha_composite(lay2)


def s_coins(im, rng, up, colr, x_max=1.0, scale=1.0):
    """Stacks of gold coins rising like a bar chart."""
    w, h = im.size
    lay = layer(w, h)
    d = ImageDraw.Draw(lay)
    n = 6 if x_max == 1.0 else 3
    for i in range(n):
        cx = int(90 + i * (w * x_max - 120) / max(1, n - 1))
        coins = int((4 + i * 3 if up else 4 + (n - i) * 3) * scale)
        base = int(h * 0.5)
        for k in range(coins):
            y = base - k * 26
            d.ellipse([cx - 70, y - 22, cx + 70, y + 22], fill=(170, 110, 20, 255))
            d.ellipse([cx - 70, y - 30, cx + 70, y + 14], fill=(250, 196, 60, 255), outline=(200, 140, 30, 255), width=3)
        d.text((cx, base - coins * 26 - 8), '₹', font=_font('Hind-Bold.ttf', 34), fill=(150, 90, 10, 255), anchor='mm')
    glow(im, lay, 8, 1.1)


def s_goldbars(im, rng, up, colr):
    """Stacked gold bars with a faint world grid behind."""
    w, h = im.size
    lay = layer(w, h)
    d = ImageDraw.Draw(lay)
    base = int(h * 0.5)
    rows = [(5, 0), (4, 1), (3, 2), (2, 3)]
    bw, bh = 170, 70
    x_start = int(w * 0.32)
    for n, r in rows:
        for i in range(n):
            x = x_start + i * (bw + 8) + r * (bw // 2)
            y = base - r * (bh + 4)
            d.polygon([(x, y), (x + bw, y), (x + bw - 22, y - bh), (x + 22, y - bh)], fill=(232, 176, 40, 255),
                      outline=(160, 110, 20, 255))
            d.polygon([(x + 30, y - bh + 10), (x + bw - 30, y - bh + 10), (x + bw - 40, y - bh + 26), (x + 40, y - bh + 26)],
                      fill=(255, 230, 150, 200))
    glow(im, lay, 16, 1.2)


SCENES = {'candles': s_candles, 'dalal': s_dalal, 'tape': s_tape, 'board': s_board, 'globe': s_globe,
          'words': s_words, 'calendar': s_calendar, 'bell': s_bell, 'confetti': s_confetti, 'arrows': s_arrows,
          'heatmap': s_heatmap, 'bars3d': s_bars3d, 'peaks': s_peaks, 'flows': s_flows, 'rupee': s_rupee,
          'coins': s_coins, 'goldbars': s_goldbars}


def draw(scene, im, rng, up, colr, kind):
    if scene == 'words':
        s_words(im, rng, up, colr, kind)
    else:
        SCENES[scene](im, rng, up, colr)
        words(im, rng, kind)
