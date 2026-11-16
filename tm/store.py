"""State lives as small JSON files on the repo's `data` branch.

One file per draft / per 'seen' key keeps parallel workflow runs from conflicting
when they push (each run writes different files).
"""
import hashlib
import json
import uuid
from pathlib import Path

from . import config
from .util import now_ist


def _path(*parts):
    p = config.DATA_DIR.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def read_json(rel, default=None):
    p = config.DATA_DIR / rel
    if not p.exists():
        return default
    return json.loads(p.read_text())


def write_json(rel, obj):
    _path(rel).write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


# ---------------------------------------------------------------- dedupe keys

def key_hash(text):
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def seen(kind, key):
    return (config.DATA_DIR / 'seen' / kind / f'{key_hash(key)}.json').exists()


def mark_seen(kind, key, info=None):
    write_json(f'seen/{kind}/{key_hash(key)}.json', {'key': key, 'at': now_ist().isoformat(), **(info or {})})


# ---------------------------------------------------------------- drafts

def new_draft(kind, images, caption, threads_text, report, meta=None):
    did = now_ist().strftime('%m%d%H%M') + '-' + uuid.uuid4().hex[:5]
    d = {
        'id': did, 'kind': kind, 'created': now_ist().isoformat(),
        'images': [str(i) for i in images],        # paths relative to DATA_DIR
        'caption': caption, 'threads_text': threads_text,
        'report': report, 'status': 'pending', 'meta': meta or {},
        'telegram_message_id': None, 'posted': {},
    }
    save_draft(d)
    return d


def save_draft(d):
    write_json(f'drafts/{d["id"]}.json', d)


def load_draft(did):
    return read_json(f'drafts/{did}.json')


def list_drafts(status=None):
    folder = config.DATA_DIR / 'drafts'
    if not folder.exists():
        return []
    out = [json.loads(p.read_text()) for p in sorted(folder.glob('*.json'))]
    return [d for d in out if status is None or d['status'] == status]


def media_path(draft_hint, n):
    day = now_ist().strftime('%Y-%m-%d')
    rel = Path('media') / day / f'{draft_hint}_{n}.jpg'
    _path(rel)
    return rel


def media_url(rel):
    return f'{config.MEDIA_BASE_URL}/{Path(rel).as_posix()}'


# ---------------------------------------------------------------- flags

def get_flag(name, default=None):
    return (read_json('flags.json', {}) or {}).get(name, default)


def set_flag(name, value):
    f = read_json('flags.json', {}) or {}
    f[name] = value
    write_json('flags.json', f)
