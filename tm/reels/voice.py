"""Voice-over for reels (free): Microsoft Edge neural voices via edge-tts (Indian English),
then Google Translate TTS (gTTS, Indian accent) as a fallback. If both fail the reel is still made,
silent, and the draft says so.

Narration is written by code from the same verified numbers as the on-screen text - never by an AI.
"""
import asyncio
import re
import subprocess
from pathlib import Path

from .. import config
from ..util import log

VOICE = config.env('TM_VOICE', 'en-IN-NeerjaNeural')      # or en-IN-PrabhatNeural (male)
RATE = config.env('TM_VOICE_RATE', '+6%')


def duration(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of',
                          'default=noprint_wrappers=1:nokey=1', str(path)], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def _edge(text, path):
    import edge_tts

    async def run():
        await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(path))
    asyncio.run(run())


def _gtts(text, path):
    from gtts import gTTS
    gTTS(text, lang='en', tld='co.in').save(str(path))


def speak(text, path):
    """Write an mp3 for `text`; returns (path, engine) or (None, reason)."""
    path = Path(path)
    if config.DRY_RUN:
        return None, 'dry-run'
    for name, fn in (('edge', _edge), ('gtts', _gtts)):
        try:
            fn(text, path)
            if path.exists() and duration(path) > 0.3:
                return path, name
        except Exception as e:                        # noqa: BLE001 - try the next engine
            log.warning('voice %s failed: %s', name, type(e).__name__)
    return None, 'no voice service answered'


# ---------------------------------------------------------------- numbers as they should be spoken

def pts(v):
    """Index level or points: whole numbers read best ('24,612')."""
    return f'{abs(v):,.0f}'


def pct(v):
    return f'{abs(v):.2f} percent'


def move(chg, p):
    return f'{"up" if chg >= 0 else "down"} {pts(chg)} points, or {pct(p)}'


def crore(v):
    return f'{abs(v):,.0f} crore rupees'


def clean(text):
    """Plain speech: no symbols the voices read oddly."""
    text = text.replace('₹', '').replace('&', ' and ').replace('%', ' percent').replace('/', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()
