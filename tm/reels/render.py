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
    from ..render import art, photo
    pic = photo.get(TOPIC_PHOTO.get(topic)) if photo.enabled() else None
    if pic is not None:
        side = 2112
        im = pic.resize((side, side), Image.LANCZOS).crop(((side - 1188) // 2, 0, (side - 1188) // 2 + 1188, 2112))
    else:
        im = art._scene_background(TOPIC_SCENE.get(topic, 'candles'), 'reel', 1188, 2112, random.Random(seed),
                                   tone != 'down', art.UP if tone != 'down' else art.DOWN)
    im = im.convert('RGB')
    # darken top and bottom for the header and subtitles
    a = np.zeros((2112, 1188, 4), np.uint8)
    y = np.arange(2112)[:, None]
    a[..., 3] = np.clip(np.maximum(1 - y / 520, (y - 1450) / 660) * 210, 0, 210).astype(np.uint8)
    im = im.convert('RGBA')
    im.alpha_composite(Image.fromarray(a, 'RGBA'))
    return im.convert('RGB')


class Tile:
    """A pre-rendered element that slides up and fades in at `start` seconds."""

    def __init__(self, im, x, y, start):
        self.im, self.x, self.y, self.start = im, x, y, start
        self.alpha = np.array(im.split()[-1], dtype=np.float32)

    def draw(self, frame, t):
        k = min(1.0, max(0.0, (t - self.start) / 0.35))
        if k <= 0:
            return
        e = 1 - (1 - k) ** 3
        im = self.im
        if k < 1:
            im = self.im.copy()
            im.putalpha(Image.fromarray((self.alpha * e).astype(np.uint8)))
        frame.alpha_composite(im, (int(self.x), int(self.y + (1 - e) * 46)))


def _card(w, h, accent=SAFFRON):
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=28, fill=CARD + (245,))
    d.rounded_rectangle([0, 0, 14, h - 1], radius=7, fill=accent + (255,))
    return im, d


def chg_col(v):
    return GREEN if v > 0 else RED if v < 0 else MUTED


def _title_tile(text, y, start, size=86):
    im = Image.new('RGBA', (W - 120, size + 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = _font('bebas', size)
    while d.textlength(text, font=f) > W - 140 and size > 50:
        size -= 4
        f = _font('bebas', size)
    d.text((0, 0), text, font=f, fill=WHITE)
    return Tile(im, 60, y, start)


def scene_tiles(sc):
    """Tiles for one scene, laid out in the middle of the frame."""
    tiles = []
    kind = sc['type']
    if kind == 'intro':
        day = sc['day']
        im = Image.new('RGBA', (W - 120, 520), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, d.textlength(sc['title'].upper(), font=_font('cond', 46)) + 48, 70], radius=12,
                            fill=SAFFRON)
        d.text((24, 35), sc['title'].upper(), font=_font('cond', 46), fill=INK, anchor='lm')
        d.text((0, 110), day.strftime('%A').upper(), font=_font('bebas', 96), fill=SAFFRON)
        d.text((0, 200), f'{day.day} {day.strftime("%B %Y")}'.upper(), font=_font('bebas', 150), fill=WHITE)
        tiles.append(Tile(im, 60, 420, 0.1))
        tmp = ImageDraw.Draw(Image.new('RGBA', (10, 10)))
        lines = cards.wrap(tmp, sc['hook'], _font('Bold', 58), W - 230)[:4]
        card, d = _card(W - 120, 70 + 76 * len(lines))
        y = 34
        for ln in lines:
            d.text((50, y), ln, font=_font('Bold', 58), fill=INK)
            y += 76
        tiles.append(Tile(card, 60, 1000, 0.5))
    elif kind == 'rows':
        tiles.append(_title_tile(sc['title'], 380, 0.05))
        rows = sc['rows'][:6]
        rh = 190 if len(rows) <= 4 else 150
        big = 80 if len(rows) <= 4 else 68
        for i, r in enumerate(rows):
            card, d = _card(W - 120, rh - 22)
            cy = (rh - 22) // 2
            lf = _font('Bold', 50 if len(rows) <= 4 else 44)
            d.text((48, cy - (22 if r.get('sub') else 0)), r['label'], font=lf, fill=INK, anchor='lm')
            if r.get('sub'):
                d.text((48, cy + 34), r['sub'], font=_font('Medium', 32), fill=MUTED, anchor='lm')
            right = W - 120 - 40
            if r.get('pct') is not None:
                pt = f'{r["pct"]:+.2f}%'
                d.text((right, cy), pt, font=_font('bebas', big), fill=chg_col(r['pct']), anchor='rm')
                right -= d.textlength(pt, font=_font('bebas', big)) + 34
            if r.get('value'):
                d.text((right, cy), r['value'], font=_font('bebas', big), fill=INK, anchor='rm')
            stagger = 0.22 if sc.get('voice') else 0.08          # silent lists appear almost at once
            tiles.append(Tile(card, 60, 520 + i * rh, (0.35 if sc.get('voice') else 0.15) + i * stagger))
    elif kind == 'duo':
        tiles.append(_title_tile(sc['title'], 380, 0.05))
        colw = (W - 140) // 2
        for c, (head, rows, colr) in enumerate([(sc['left_title'], sc['left'], GREEN), (sc['right_title'], sc['right'], RED)]):
            card, d = _card(colw, 130 + 132 * max(1, len(rows[:5])), colr)
            d.text((40, 66), head.upper(), font=_font('cond', 48), fill=colr, anchor='lm')
            for i, r in enumerate(rows[:5]):
                y = 140 + i * 132
                nm = r['label']
                while d.textlength(nm, font=_font('Bold', 40)) > colw - 60 and len(nm) > 4:
                    nm = nm[:-1]
                d.text((40, y + 24), nm, font=_font('Bold', 40), fill=INK, anchor='lm')
                d.text((40, y + 80), f'{r["pct"]:+.2f}%', font=_font('bebas', 64), fill=chg_col(r['pct']), anchor='lm')
            tiles.append(Tile(card, 60 + c * (colw + 20), 520, 0.35 + c * 0.35))
    elif kind == 'outro':
        lg = cards.logo()
        lg = lg.resize((700, int(lg.height * 700 / lg.width)), Image.LANCZOS)
        tiles.append(Tile(lg.convert('RGBA'), (W - 700) // 2, 520, 0.1))
        card, d = _card(W - 120, 330)
        d.text(((W - 120) // 2, 80), 'FOLLOW TICKER MARKET INDIA', font=_font('bebas', 76), fill=INK, anchor='mm')
        d.text(((W - 120) // 2, 160), 'for daily stock market data & news', font=_font('SemiBold', 42), fill=MUTED, anchor='mm')
        d.text(((W - 120) // 2, 240), config.BRAND['handle'], font=_font('Bold', 46), fill=SAFFRON, anchor='mm')
        tiles.append(Tile(card, 60, 600 + lg.height + 40, 0.5))
    top = min(t.y for t in tiles)
    bottom = max(t.y + t.im.height for t in tiles)
    shift = (230 + 1560) / 2 - (top + bottom) / 2
    for t in tiles:
        t.y += shift
    return tiles


def _subtitle_chunks(text, n_words=9):
    words = voice.clean(text).split()
    return [' '.join(words[i:i + n_words]) for i in range(0, len(words), n_words)] or ['']


def _subtitle(text):
    im = Image.new('RGBA', (W - 120, 190), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = _font('SemiBold', 44)
    lines = cards.wrap(d, text, f, W - 200)[:2]
    h = 40 + 60 * len(lines)
    d.rounded_rectangle([0, 190 - h, W - 121, 189], radius=22, fill=(0, 0, 0, 170))
    y = 190 - h + 22
    for ln in lines:
        d.text(((W - 120) // 2, y + 26), ln, font=f, fill=WHITE, anchor='mm')
        y += 60
    return im


def _header(frame, label, idx, n, t_frac):
    d = ImageDraw.Draw(frame)
    seg = (W - 120 - 10 * (n - 1)) / n
    for i in range(n):
        x0 = 60 + i * (seg + 10)
        d.rounded_rectangle([x0, 60, x0 + seg, 68], radius=4, fill=(255, 255, 255, 90))
        fill = 1.0 if i < idx else t_frac if i == idx else 0
        if fill > 0:
            d.rounded_rectangle([x0, 60, x0 + seg * fill, 68], radius=4, fill=WHITE)
    lg = _header.logo
    frame.alpha_composite(lg, (60, 100))
    f = _font('cond', 36)
    tw = d.textlength(label.upper(), font=f)
    d.rounded_rectangle([W - 60 - tw - 40, 108, W - 60, 162], radius=10, fill=SAFFRON)
    d.text((W - 80, 135), label.upper(), font=f, fill=INK, anchor='rm')


def build(scenes, label, out_path, seed='reel'):
    """scenes: list of dicts (type, voice text, topic, tone, + type fields). Returns (path, report lines)."""
    rep = []
    work = Path(tempfile.mkdtemp(prefix='reel-'))
    lg = cards.logo().convert('RGBA')
    _header.logo = lg.resize((240, int(lg.height * 240 / lg.width)), Image.LANCZOS)
    # 1) voice per scene -> durations
    engine = None
    durs, wavs = [], []
    for i, sc in enumerate(scenes):
        if sc.get('voice'):
            mp3, eng = voice.speak(voice.clean(sc['voice']), work / f'v{i}.mp3')
            engine = engine or (eng if mp3 else None)
            spoken = voice.duration(mp3) if mp3 else max(3.0, len(sc['voice'].split()) / 2.7)
            d = round(spoken + 0.9, 2)
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
    try:
        for i, sc in enumerate(scenes):
            bg = background(sc.get('topic', 'indices'), sc.get('tone'), f'{seed}-{i}')
            tiles = scene_tiles(sc)
            chunks = _subtitle_chunks(sc['voice'])
            subs = [_subtitle(c) for c in chunks]
            n = int(durs[i] * FPS)
            for k in range(n):
                t = k / FPS
                z = 1 + 0.08 * (k / max(1, n - 1))                     # slow zoom in
                cw, ch = int(1188 / z), int(2112 / z)
                x0, y0 = (1188 - cw) // 2, (2112 - ch) // 2
                frame = bg.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.BILINEAR).convert('RGBA')
                _header(frame, label, i, len(scenes), t / durs[i])
                for tl in tiles:
                    tl.draw(frame, t)
                if sc.get('voice'):
                    ci = min(len(subs) - 1, int(t / durs[i] * len(subs)))
                    frame.alpha_composite(subs[ci], (60, H - 330))
                rgb = frame.convert('RGB')
                if cover is None and i == 0 and k == int(1.2 * FPS):
                    cover = rgb.copy()
                proc.stdin.write(rgb.tobytes())
    finally:
        proc.stdin.close()
        proc.wait()
        shutil.rmtree(work, ignore_errors=True)
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError('video encoding failed')
    rep.append(('ok', f'reel: {len(scenes)} scenes, {total:.0f} s, {out_path.stat().st_size / 1e6:.1f} MB'))
    log.info('reel built %s (%.0f s)', out_path, total)
    return out_path, cover, rep, total
