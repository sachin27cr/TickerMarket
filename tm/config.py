"""All settings come from environment variables (GitHub Secrets / repo variables)."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def env(name, default=None):
    v = os.environ.get(name)
    return v if v not in (None, '') else default


def env_bool(name, default=False):
    v = env(name)
    return default if v is None else v.strip().lower() in ('1', 'true', 'yes', 'on')


PAGE = env('TM_PAGE', 'india')                         # 'india' or 'global'
BRAND = json.loads((ROOT / 'config' / 'brand.json').read_text())[PAGE]
FEEDS = json.loads((ROOT / 'config' / 'feeds.json').read_text())['feeds']

DATA_DIR = Path(env('TM_DATA_DIR', str(ROOT / 'data')))   # checkout of the 'data' branch
REPO = env('GITHUB_REPOSITORY', 'owner/TickerMarket')
DATA_BRANCH = env('TM_DATA_BRANCH', 'data')
MEDIA_BASE_URL = env('TM_MEDIA_BASE_URL', f'https://raw.githubusercontent.com/{REPO}/{DATA_BRANCH}')

DRY_RUN = env_bool('TM_DRY_RUN', False)                # no Telegram / Meta calls, print instead

TELEGRAM_TOKEN = env('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = env('TELEGRAM_CHAT_ID')

GEMINI_API_KEY = env('GEMINI_API_KEY')
GEMINI_MODEL = env('GEMINI_MODEL', 'auto')          # 'auto' = newest available Flash model
GROQ_API_KEY = env('GROQ_API_KEY')
GROQ_MODEL = env('GROQ_MODEL', 'auto')              # 'auto' = best available large model
REQUIRE_SECOND_OPINION = env_bool('TM_REQUIRE_SECOND_OPINION', False)   # news always waits for approval

META_PAGE_ID = env('META_PAGE_ID')
META_PAGE_TOKEN = env('META_PAGE_TOKEN')
IG_USER_ID = env('IG_USER_ID')
THREADS_USER_ID = env('THREADS_USER_ID')
THREADS_TOKEN = env('THREADS_TOKEN')
GRAPH_VERSION = env('META_GRAPH_VERSION', 'v21.0')
POST_TO = [p.strip() for p in env('TM_POST_TO', 'instagram,facebook,threads').split(',') if p.strip()]

NEWS_PER_RUN = int(env('TM_NEWS_PER_RUN', '3'))
NEWS_MAX_AGE_HOURS = float(env('TM_NEWS_MAX_AGE_HOURS', '18'))

# Auto-posting. '' = every post needs your tap (default). 'data' = data cards post on their own,
# news still needs approval. 'all' = everything posts on its own. Or a comma list of job names.
DATA_KINDS = {'global_cues', 'day_ahead', 'ipo', 'ipo_status', 'market_close', 'cap_movers', 'daily_overview', 'fii_dii',
              'weekly_ath', 'weekly_lows'}
_auto = env('TM_AUTO_POST', '').strip().lower()
AUTO_POST = (DATA_KINDS if _auto == 'data' else {'*'} if _auto == 'all' else
             {k.strip() for k in _auto.split(',') if k.strip() and k.strip() not in ('none', 'off')})
AUTO_DELAY_MIN = int(env('TM_AUTO_DELAY_MIN', '10'))   # cancel window before an auto post goes out


def auto_posts(kind):
    return '*' in AUTO_POST or kind in AUTO_POST
