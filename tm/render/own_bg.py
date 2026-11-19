"""Your own background pictures. Put images (jpg/png/webp) in assets/backgrounds/<folder>/ in the repo;
they are used before any AI-generated or drawn background, rotating day by day so posts don't repeat.

Folders (any can be empty - then the next option is used):
  morning   - Day Ahead, Daily Overview, Global Cues, morning reel
  close     - Market Close, Cap Movers, evening reel        (optional sub-folders up/ and down/)
  money     - FII / DII flows
  ipo       - IPO posts
  highs     - all-time highs          lows - 52-week lows
  insights  - Insights and Results Spotlight
  weekly    - weekly roundup reel
  news/<sector>/ - news posts, matched to the story: banking, it, auto, pharma, metals, energy, oil, gold,
                   fmcg, realty, telecom, ipo, economy, global, results, markets (general market stories)
If a folder is empty, the AI picture (when set up) or a drawn scene is used - never a random picture.
"""
import hashlib
from pathlib import Path

from PIL import Image

NEWS_SECTOR = None             # set by the news job for the story being drawn
ROOT = Path(__file__).resolve().parents[2] / 'assets' / 'backgrounds'
EXT = ('.jpg', '.jpeg', '.png', '.webp')

FOLDER = {
    'day_ahead': 'morning', 'daily_overview': 'morning', 'global_cues': 'morning', 'reel_morning': 'morning',
    'market_close': 'close', 'cap_movers': 'close', 'reel_evening': 'close',
    'fii_dii': 'money', 'ipo': 'ipo', 'ipo_status': 'ipo',
    'weekly_ath': 'highs', 'reel_ath': 'highs', 'weekly_lows': 'lows', 'reel_lows': 'lows',
    'reel_weekly': 'weekly', 'news': 'news',
}
# reel scene topics -> folder
TOPIC = {'intro': 'morning', 'intro_pm': 'close', 'intro_week': 'weekly', 'global': 'morning',
         'commodities': 'money', 'indices': 'close', 'flows': 'money', 'calendar': 'morning',
         'sectors': 'insights', 'movers': 'close', 'highs': 'highs', 'lows': 'lows'}


def folder_for(kind):
    if kind.startswith('insight') or kind == 'results_spotlight':
        return 'insights'
    return FOLDER.get(kind, 'common')


def _files(folder, tone=None):
    out = []
    for d in ([ROOT / folder / tone] if tone else []) + [ROOT / folder]:
        if d.is_dir():
            out = sorted(p for p in d.iterdir() if p.suffix.lower() in EXT)
            if out:
                return out
    if (ROOT / folder).is_dir():                       # no tone given: use up/ and down/ together
        out = sorted(p for p in (ROOT / folder).rglob('*') if p.suffix.lower() in EXT)
    return out


def news_folder(sector):
    sector = (sector or 'other').lower()
    if sector in ('other', 'economy', ''):
        return ['news/' + sector, 'news/markets'] if sector else ['news/markets']
    return ['news/' + sector]


def pick(folder, tone=None, seed=0):
    """An image from the folder, different each day and for each slide seed (None if the folder is empty)."""
    from ..util import today_ist
    folders = news_folder(NEWS_SECTOR) if folder == 'news' else [folder]
    files = []
    for f in folders:
        files = _files(f, tone)
        if files:
            folder = f
            break
    if not files:
        return None
    h = int(hashlib.md5(f'{folder}-{today_ist().toordinal()}-{seed}'.encode()).hexdigest(), 16)
    try:
        return Image.open(files[h % len(files)]).convert('RGB')
    except OSError:
        return None


def cover(pic, w, h):
    """Scale to fill w x h and crop the centre."""
    s = max(w / pic.width, h / pic.height)
    pic = pic.resize((max(w, round(pic.width * s)), max(h, round(pic.height * s))), Image.LANCZOS)
    x, y = (pic.width - w) // 2, (pic.height - h) // 2
    return pic.crop((x, y, x + w, y + h))
