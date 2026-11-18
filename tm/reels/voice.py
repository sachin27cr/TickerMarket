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

# Male voices to choose from in Telegram (/voices plays a sample of each, /voice <name> picks one).
VOICES = {
    'prabhat': ('en-IN-PrabhatNeural', '+4%', 'Indian English, male'),
    'andrew': ('en-US-AndrewMultilingualNeural', '+0%', 'most natural conversational voice, American accent'),
    'brian': ('en-US-BrianMultilingualNeural', '+0%', 'warm conversational voice, American accent'),
    'madhur': ('hi-IN-MadhurNeural', '+0%', 'Hindi male voice reading English, Indian accent'),
}
DEFAULT = config.env('TM_VOICE', 'prabhat')
SAMPLE = ('Good morning. The Nifty closed at 24,612, up 118 points, or 0.48 percent. Foreign investors were net '
          'buyers of 4,870 crore rupees. Here is what to watch today.')


def current():
    """(edge voice id, rate) chosen in Telegram, else TM_VOICE, else Prabhat."""
    from .. import store
    key = (store.get_flag('voice') or DEFAULT).lower()
    if key not in VOICES:                       # a full voice id may be set directly
        return key, '+0%'
    v, rate, _ = VOICES[key]
    return v, rate


VOICE = None                                     # filled at use time (see current())


def duration(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of',
                          'default=noprint_wrappers=1:nokey=1', str(path)], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def _edge(text, path, voice_id=None):
    import edge_tts
    vid, rate = (voice_id, '+0%') if voice_id else current()
    if voice_id in [v for v, _, _ in VOICES.values()]:
        rate = next(r for v, r, _ in VOICES.values() if v == voice_id)

    async def run():
        await edge_tts.Communicate(text, vid, rate=rate, pitch='-2Hz').save(str(path))
    asyncio.run(run())


def sample(name, path):
    """A short sample of one voice for /voices."""
    _edge(SAMPLE, path, VOICES[name][0])
    return path


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


def signed(p):
    return f'{"up" if p >= 0 else "down"} {pct(p)}'


def clock(dt):
    """'7:00 PM' -> '7 PM', '11:30 PM' -> '11:30 PM' (spoken naturally)."""
    return dt.strftime('%-I %p') if dt.minute == 0 else dt.strftime('%-I:%M %p')


def crore(v):
    return f'{abs(v):,.0f} crore rupees'


def clean(text):
    """Plain speech: no symbols the voices read oddly."""
    text = re.sub(r'\bm/m\b', 'month on month', text)
    text = re.sub(r'\by/y\b', 'year on year', text)
    text = re.sub(r'\bq/q\b', 'quarter on quarter', text)
    text = text.replace('FOMC', 'Fed')
    text = text.replace('₹', '').replace('&', ' and ').replace('%', ' percent').replace('/', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def speech(text):
    """What the voice reads: like the subtitles, plus spellings that help pronunciation."""
    t = clean(text)
    t = re.sub(r'\bFIIs\b', 'F I Is', t)
    t = re.sub(r'\bDIIs\b', 'D I Is', t)
    t = re.sub(r'\bFII\b', 'F I I', t)
    t = re.sub(r'\bDII\b', 'D I I', t)
    return t
