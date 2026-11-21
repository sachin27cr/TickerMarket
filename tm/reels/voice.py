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
# Indian voices first. Some newer ones are not on the free service everywhere - /voices only lists those
# that are actually available on the day.
VOICES = {
    'prabhat': ('en-IN-PrabhatNeural', '+4%', 'Indian English, male, news-reader style'),
    'aarav': ('en-IN-AaravNeural', '+2%', 'Indian English, male, young and conversational'),
    'kunal': ('en-IN-KunalNeural', '+2%', 'Indian English, male, warm'),
    'rehaan': ('en-IN-RehaanNeural', '+2%', 'Indian English, male, energetic'),
    'madhur': ('hi-IN-MadhurNeural', '+0%', 'Hindi male voice reading English, strong Indian accent'),
    'arjun': ('hi-IN-ArjunNeural', '+0%', 'Hindi male voice reading English, Indian accent'),
    'neerja': ('en-IN-NeerjaExpressiveNeural', '+2%', 'Indian English, female, expressive'),
    'andrew': ('en-US-AndrewMultilingualNeural', '+0%', 'very natural conversational voice, American accent'),
    'brian': ('en-US-BrianMultilingualNeural', '+0%', 'warm conversational voice, American accent'),
}
DEFAULT = config.env('TM_VOICE', 'prabhat')
SAMPLE = ('Good morning. The Nifty closed at 24,612, up 118 points, or 0.48%. FIIs sold ₹2,350 cr while DIIs '
          'bought ₹3,120 cr. HDFC Bank, ICICI Bank and L&T led the gains; SEBI and RBI updates are due. '
          'Here is what to watch today.')


def available():
    """Voice ids the free service offers today (empty set if the list can't be fetched)."""
    try:
        import edge_tts
        return {v['ShortName'] for v in asyncio.run(edge_tts.list_voices())}
    except Exception:                                  # noqa: BLE001
        return set()


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
    if 'Multilingual' in vid and len(text.split()) < 10:
        # multilingual voices guess the language from the text itself: a short line like 'Micro Cap: 11'
        # can come out in Spanish. Short lines use the same speaker's English-only voice.
        vid = vid.replace('MultilingualNeural', 'Neural')

    async def run():
        await edge_tts.Communicate(text, vid, rate=rate, pitch='-2Hz').save(str(path))
    asyncio.run(run())


def sample(name, path):
    """A short sample of one voice for /voices."""
    _edge(speech(SAMPLE), path, VOICES[name][0])
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


# How market terms should be SPOKEN (subtitles keep the short forms). Order matters: longer first.
SAY = [
    (r'\bFIIs?\b', 'foreign institutions'), (r'\bFPIs?\b', 'foreign investors'),
    (r'\bDIIs?\b', 'domestic institutions'), (r'\bMFs\b', 'mutual funds'),
    (r'\bF&Os?\b|\bF and O\b', 'F and O'), (r'\bM&M\b|\bM and M\b', 'Mahindra and Mahindra'),
    (r'\bL&T\b|\bL and T\b', 'L and T'), (r'\bLTIMindtree\b', 'L T I Mindtree'),
    (r'\bSEBI\b|\bSebi\b', 'Sebi'), (r'\bGAIL\b', 'Gail'), (r'\bIREDA\b', 'Ireda'),
    (r'\bNALCO\b', 'Nalco'), (r'\bOPEC\+?', 'Opec'), (r'\bNASDAQ\b|\bNasdaq\b', 'Nazdaq'),
    (r'\bSENSEX\b', 'Sensex'), (r'\bNIFTY\b', 'Nifty'), (r'\bBANKNIFTY\b', 'Bank Nifty'),
    (r'\bMIDCAP\b|\bMidcap\b', 'mid cap'), (r'\bSMALLCAP\b|\bSmallcap\b', 'small cap'),
    (r'\bmcap\b|\bm-cap\b', 'market cap'), (r'\bATHs?\b', 'all-time high'),
    (r'\b52-week\b|\b52-wk\b|\b52 wk\b', 'fifty-two week'),
    (r'\bYoY\b|\byoy\b', 'year on year'), (r'\bQoQ\b|\bqoq\b', 'quarter on quarter'),
    (r'\bMoM\b', 'month on month'), (r'\bbps\b', 'basis points'), (r'\bvs\.?\b', 'versus'),
    (r'\bQ([1-4])\s?FY\s?(\d{2})\b', r'Q\1 of F Y \2'), (r'\bFY\s?(\d{2})\b', r'F Y \1'),
    (r'\bQ([1-4])\b', r'Q \1'), (r'\bRs\.?\s?', ''), (r'\bcr\b|\bCr\b', 'crore'),
    (r'\blakh cr\b', 'lakh crore'), (r'\bbn\b', 'billion'), (r'\bmn\b', 'million'),
    (r'\bIPOs\b', 'I P Os'), (r'\bPSUs\b', 'P S Us'), (r'\bPSBs?\b', 'public sector banks'),
    (r'\bNBFCs\b', 'N B F Cs'), (r'\bETFs\b', 'E T Fs'), (r'\bEVs\b', 'E Vs'),
    (r'\bUS\b', 'U S'), (r'\bUK\b', 'U K'), (r'\bInc\.?', ''), (r'\bLtd\.?', ''),
]
# All-capital short forms (NSE, RBI, HDFC, ICICI, TCS, IPO...) are spelt out letter by letter;
# these are said as words instead.
WORDS = {'NIFTY', 'SENSEX', 'OPEC', 'NATO', 'ASEAN', 'COVID', 'GIFT', 'BRICS', 'NASA', 'UNESCO'}


def speech(text):
    """What the voice reads: like the subtitles, but with market short forms said the way people say them
    (FIIs -> foreign institutions, SEBI -> Sebi, HDFC -> H D F C, Q2 FY27 -> Q 2 of F Y 27)."""
    t = text
    for pat, rep in SAY:
        t = re.sub(pat, rep, t)
    t = clean(t)
    t = re.sub(r'\b([A-Z]{2,6})(s?)\b',
               lambda m: m.group(0) if m.group(1) in WORDS else ' '.join(m.group(1)) + m.group(2), t)
    return re.sub(r'\s+', ' ', t).strip()
