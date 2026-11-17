"""Photo-realistic background pictures made with FLUX.1 [schnell] on Cloudflare Workers AI (free daily quota).

Rules (built into every prompt): no text, letters, numbers or logos (the model garbles them, and all text on a
post is drawn by code), no recognisable people or faces, no copyrighted characters. Each picture is a scene
that fits the post. If Cloudflare is not set up, the quota is used up or a call fails, the post falls back to
the drawn scenes in scenes.py - a post is never blocked by a picture.
"""
import base64
import hashlib
import io
import zlib

import requests
from PIL import Image

from .. import config
from ..util import log, today_ist

MODEL = '@cf/black-forest-labs/flux-1-schnell'
DAILY_LIMIT = 80             # well inside the free 10,000 neurons a day (about 60 neurons per picture)
STYLE = ('photorealistic editorial photograph, cinematic lighting, rich colours, shallow depth of field, '
         'sharp focus, high detail, 4k. Absolutely no text, no letters, no numbers, no words, no signage, '
         'no logos, no watermark, no recognisable people, no faces.')

# post kind -> scenes (up-day wording, down-day wording). Rotates daily.
SCENES = {
    'market_close': [('Mumbai skyline at golden hour seen from Marine Drive, modern glass towers glowing, '
                      'a giant transparent stock chart with green rising candlesticks in the sky',
                      'Mumbai skyline at dusk under dark stormy clouds, glass towers, a giant transparent '
                      'stock chart with red falling candlesticks in the sky'),
                     ('busy modern Indian stock trading floor at closing time, rows of monitors showing green '
                      'charts, warm light', 'quiet modern Indian stock trading floor at closing time, rows of '
                      'monitors showing red charts, moody blue light'),
                     ('tall stock exchange tower in Mumbai at sunset, glowing windows, light trails of traffic '
                      'on the street below', 'tall stock exchange tower in Mumbai on a rainy evening, glowing '
                      'windows, wet street reflections')],
    'cap_movers': [('close-up of several trading monitors with green and red bar charts and heat maps, '
                    'dark office, neon reflections', None),
                   ('a bull and a bear statue facing each other on a polished stone plaza in a financial '
                    'district at dusk', None)],
    'daily_overview': [('a lone climber standing on a snowy mountain summit at sunrise with a green flag, '
                        'dramatic sky', 'a deep mountain valley in fog at dusk, dark cliffs, dramatic red sky'),
                       ('glowing stock market candlestick chart projected over a city at night, rising to a '
                        'new peak', 'glowing stock market candlestick chart projected over a city at night, '
                        'falling to a new low')],
    'global_cues': [('a glowing globe of the earth from space at night with city lights and golden network '
                     'lines connecting financial centres', None),
                    ('Wall Street style financial district at dawn, tall skyscrapers, morning mist', None),
                    ('oil tanker ship at sea at sunrise next to stacks of gold bars on a dock', None)],
    'fii_dii': [('stacks of Indian rupee banknotes and gold coins on a dark desk in front of trading screens, '
                 'warm light', None),
                ('golden river of coins flowing into a glass bank vault, dramatic light', None),
                ('international cargo planes and ships at an Indian port at sunrise, symbolising money '
                 'flowing in', None)],
    'day_ahead': [('sunrise over Mumbai harbour, calm sea, city skyline waking up, morning glow', None),
                  ('a desk with a notebook, coffee and a laptop showing stock charts at early morning, '
                   'window with sunrise over a city', None)],
    'ipo': [('a large shiny brass bell on a stage with golden confetti falling and spotlights', None),
            ('modern corporate headquarters building at dawn with a grand entrance, glass facade', None),
            ('celebration on a stock exchange stage, golden confetti and spotlights, empty podium', None)],
    'ipo_status': [('long queue of glowing digital order tickets flowing into a stock exchange building, '
                    'futuristic, night', None),
                   ('a large shiny brass bell on a stage with golden confetti falling and spotlights', None)],
    'weekly_ath': [('a mountaineer flag planted on the highest snowy summit at sunrise, sea of clouds below', None)],
    'weekly_lows': [('a deep canyon at dusk with long shadows and a red sky', None)],
    'insight_profits': [('modern factory floor with robotic arms and conveyor belts, bright industrial light', None),
                        ('stacks of gold coins growing taller from left to right on a dark table, spotlight', None)],
    'insight_assets': [('gold bars, silver bars, an oil barrel and a stack of Indian rupee notes arranged on '
                        'a dark marble table, studio light', None)],
    'insight_mcap': [('aerial view of the Mumbai business district skyline at night, glowing towers', None),
                     ('row of tall modern corporate skyscrapers in India at sunset, reflective glass', None)],
    'insight_wealth': [('a small plant growing out of a stack of gold coins, soft morning light', None),
                       ('stacks of coins growing taller like a staircase towards a sunrise', None)],
    'insight_sectors': [('collage of Indian industries: steel plant, IT office, pharmaceutical lab, car '
                         'factory, bank interior, split into tiles', None)],
}
SECTOR_SCENES = {
    'banking': 'grand Indian bank interior with marble columns and tellers counters, warm light',
    'energy': 'large solar farm and wind turbines in Rajasthan at sunset',
    'it': 'modern Bengaluru tech office with glass walls, servers and screens with code, blue light',
    'auto': 'new cars on an Indian automobile assembly line with robotic arms',
    'pharma': 'pharmaceutical laboratory with glass vials and a production line, clean white light',
    'metals': 'steel plant with molten metal sparks and glowing furnace',
    'oil': 'oil refinery at dusk with flare stacks and pipelines',
    'gold': 'stacks of gold bars in a vault with dramatic lighting',
    'fmcg': 'supermarket aisle full of packaged consumer goods, bright',
    'realty': 'modern high-rise residential towers under construction in India with cranes at sunset',
    'telecom': 'telecom towers on a hill at dusk with glowing network lines',
    'ipo': 'a large shiny brass bell on a stage with golden confetti falling and spotlights',
    'economy': 'Indian parliament-style government building at dusk with a busy road and lights, wide angle',
    'global': 'a glowing globe of the earth from space with golden network lines between financial centres',
}

PHOTO_PROMPT = None          # a job may set a specific scene (news stories do)


def enabled():
    return bool(config.env('CF_ACCOUNT_ID') and config.env('CF_AI_TOKEN'))


def prompt_for(kind, tone, seed):
    if PHOTO_PROMPT:
        return PHOTO_PROMPT
    pool = SCENES.get(kind)
    if not pool:
        return None
    if kind == 'news':
        i = zlib.crc32(str(seed).encode()) % len(pool)
    else:
        i = (today_ist().toordinal() + zlib.crc32(kind.encode())) % len(pool)
    up_txt, down_txt = pool[i]
    return down_txt if tone == 'down' and down_txt else up_txt


def _quota_ok():
    from .. import store
    used = store.read_json(f'cache/photos/count-{today_ist()}.json') or {'n': 0}
    return used['n'] < DAILY_LIMIT, used


def get(scene):
    """PIL image (1024x1024) for the scene, cached per day so all slides of a post share it. None on failure."""
    if not scene or not enabled():
        return None
    from .. import store
    key = hashlib.sha1(f'{today_ist()}|{scene}'.encode()).hexdigest()[:16]
    rel = f'cache/photos/{key}.jpg'
    path = config.DATA_DIR / rel
    if path.exists():
        try:
            return Image.open(path).convert('RGB')
        except OSError:
            pass
    ok, used = _quota_ok()
    if not ok:
        log.info('photo quota for today used (%s) - drawn scene instead', used['n'])
        return None
    url = f'https://api.cloudflare.com/client/v4/accounts/{config.env("CF_ACCOUNT_ID")}/ai/run/{MODEL}'
    try:
        r = requests.post(url, headers={'Authorization': f'Bearer {config.env("CF_AI_TOKEN")}'},
                          json={'prompt': f'{scene}. {STYLE}', 'steps': 6}, timeout=90)
        j = r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
        b64 = (j.get('result') or {}).get('image')
        if r.status_code != 200 or not b64:
            log.warning('photo failed: HTTP %s %s', r.status_code, str(j.get('errors') or r.text)[:200])
            return None
        im = Image.open(io.BytesIO(base64.b64decode(b64))).convert('RGB')
    except (requests.RequestException, ValueError, OSError) as e:
        log.warning('photo failed: %s', e)
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, 'JPEG', quality=90)
    used['n'] += 1
    store.write_json(f'cache/photos/count-{today_ist()}.json', used)
    log.info('photo generated (%s today): %s', used['n'], scene[:80])
    return im
