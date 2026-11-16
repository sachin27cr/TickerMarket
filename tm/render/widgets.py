"""Company badge (generic monogram, no real logos) and quote card (price data from NSE)."""
import hashlib

from PIL import Image, ImageDraw

from ..util import fmt_inr
from .cards import DOWN, FLAT, GOLD, MUTED, UP, WHITE, bebas, cond, hind

# deep colours for monograms; picked by company name so a company always gets the same colour
MONO = [(196, 30, 58), (0, 92, 175), (0, 128, 96), (122, 52, 160), (214, 98, 0), (0, 120, 140),
        (160, 110, 0), (40, 60, 130), (150, 40, 90), (60, 120, 40)]


def initials(name):
    words = [w for w in name.replace('&', ' ').split() if w.lower() not in ('ltd', 'limited', 'india', 'the', 'of')]
    return ''.join(w[0] for w in words[:2]).upper() or name[:2].upper()


def monogram(size, name):
    c = MONO[int(hashlib.md5(name.encode()).hexdigest(), 16) % len(MONO)]
    im = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 4, fill=c + (255,))
    d.rounded_rectangle([0, 0, size - 1, size // 2], radius=size // 4, fill=(255, 255, 255, 28))
    d.text((size / 2, size / 2 + 2), initials(name), font=bebas(int(size * 0.52)), fill=WHITE, anchor='mm')
    return im


def _glass(w, h, border=GOLD):
    card = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=22, fill=(8, 16, 34, 225), outline=border + (255,), width=3)
    return card, d


def quote_card(q, w=600):
    """q: {name, symbol, price, chg, pct, time_text}. Large card with monogram + price row."""
    h = 250
    card, d = _glass(w, h)
    card.alpha_composite(monogram(96, q['name']), (26, 26))
    name = q['name'] if d.textlength(q['name'], font=hind(36, 'Bold')) < w - 170 else q['name'][:26] + '...'
    d.text((140, 50), name, font=hind(36, 'Bold'), fill=WHITE, anchor='lm')
    d.text((140, 96), f'NSE: {q["symbol"]}', font=cond(30), fill=MUTED, anchor='lm')
    d.line([(26, 146), (w - 26, 146)], fill=(50, 64, 92, 255), width=2)
    col = UP if q['chg'] > 0 else DOWN if q['chg'] < 0 else FLAT
    d.text((26, 196), '₹' + fmt_inr(q['price']), font=bebas(74), fill=WHITE, anchor='lm')
    pw = d.textlength('₹' + fmt_inr(q['price']), font=bebas(74))
    x = 26 + pw + 22
    ay = 178
    if q['chg'] >= 0:
        d.polygon([(x, ay + 22), (x + 22, ay + 22), (x + 11, ay)], fill=col)
    else:
        d.polygon([(x, ay), (x + 22, ay), (x + 11, ay + 22)], fill=col)
    d.text((x + 34, 190), f'{"+" if q["chg"] >= 0 else ""}{fmt_inr(q["chg"])} ({q["pct"]:+.2f}%)',
           font=hind(34, 'Bold'), fill=col, anchor='lm')
    d.text((x + 34, 226), q['time_text'], font=hind(22), fill=MUTED, anchor='lm')
    return card


def mini_quote(q, w=470):
    """Compact chip for stories that name several companies."""
    h = 118
    card, d = _glass(w, h, border=(70, 86, 120))
    card.alpha_composite(monogram(74, q['name']), (20, 22))
    nm = q['name']
    while d.textlength(nm, font=hind(30, 'Bold')) > w - 112 - 190 and len(nm) > 6:
        nm = nm[:-2]
    nm = nm if nm == q['name'] else nm.rstrip() + '...'
    d.text((112, 40), nm, font=hind(30, 'Bold'), fill=WHITE, anchor='lm')
    col = UP if q['chg'] > 0 else DOWN if q['chg'] < 0 else FLAT
    d.text((112, 82), '₹' + fmt_inr(q['price']), font=hind(30, 'SemiBold'), fill=MUTED, anchor='lm')
    d.text((w - 24, 62), f'{q["pct"]:+.2f}%', font=bebas(54), fill=col, anchor='rm')
    return card


def company_badge(name, sub, w=640):
    """For IPOs/companies without a price yet: monogram + name + one line."""
    h = 150
    card, d = _glass(w, h)
    card.alpha_composite(monogram(98, name), (26, 26))
    d.text((144, 54), name[:28], font=hind(38, 'Bold'), fill=WHITE, anchor='lm')
    d.text((144, 102), sub, font=cond(30), fill=MUTED, anchor='lm')
    return card
