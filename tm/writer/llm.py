"""LLM calls. Writer = Gemini (fallback Groq). Checker = the *other* model, never the writer.

Model names change often, so by default the bot asks each service which models exist and picks
the best suitable one (GEMINI_MODEL / GROQ_MODEL = 'auto'). A retired model is skipped automatically.
"""
import json
import re
import time

import requests

from .. import config
from ..util import log


class LLMError(Exception):
    pass


_cache = {}
GEMINI_SKIP = re.compile(r'image|tts|live|audio|embed|vision|aqa|learnlm|gemma|robotics|computer', re.I)
GROQ_SKIP = re.compile(r'whisper|guard|tts|playai|orpheus|compound|distil|vision|allam', re.I)
GROQ_PREFER = ['gpt-oss-120b', 'llama-4-maverick', 'llama-3.3-70b', '70b', 'kimi', 'qwen', 'llama-4-scout',
               'gpt-oss-20b', '8b']


def _json(text):
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r'\{.*\}', text, re.S)
        if m:
            return json.loads(m.group())
        raise


def _version(name):
    m = re.search(r'(\d+(?:\.\d+)?)', name)
    return float(m.group(1)) if m else 0.0


def gemini_models():
    if config.GEMINI_MODEL != 'auto':
        return [config.GEMINI_MODEL]
    if 'gemini' in _cache:
        return _cache['gemini']
    r = requests.get('https://generativelanguage.googleapis.com/v1beta/models',
                     params={'key': config.GEMINI_API_KEY, 'pageSize': 200}, timeout=30)
    if r.status_code != 200:
        raise LLMError(f'Gemini model list HTTP {r.status_code}: {r.text[:200]}')
    names = [m['name'].split('/', 1)[1] for m in r.json().get('models', [])
             if 'generateContent' in m.get('supportedGenerationMethods', []) and not GEMINI_SKIP.search(m['name'])]
    flash = [n for n in names if 'flash' in n]
    stable = sorted([n for n in flash if not re.search(r'lite|preview|exp|\d{3,}', n)], key=_version, reverse=True)
    lite = sorted([n for n in flash if 'lite' in n and not re.search(r'preview|exp', n)], key=_version, reverse=True)
    rest = sorted([n for n in flash if n not in stable + lite], key=_version, reverse=True)
    order = (['gemini-flash-latest'] if 'gemini-flash-latest' in names else []) + stable + lite + rest
    order = list(dict.fromkeys(order))
    if not order:
        raise LLMError('no Gemini Flash model available for this key')
    log.info('Gemini models to try: %s', order[:4])
    _cache['gemini'] = order
    return order


def groq_models():
    if config.GROQ_MODEL != 'auto':
        return [config.GROQ_MODEL]
    if 'groq' in _cache:
        return _cache['groq']
    r = requests.get('https://api.groq.com/openai/v1/models',
                     headers={'Authorization': f'Bearer {config.GROQ_API_KEY}'}, timeout=30)
    if r.status_code != 200:
        raise LLMError(f'Groq model list HTTP {r.status_code}: {r.text[:200]}')
    ids = [m['id'] for m in r.json().get('data', []) if m.get('active', True) and not GROQ_SKIP.search(m['id'])]
    order = []
    for pat in GROQ_PREFER:
        order += [i for i in ids if pat in i and i not in order]
    order += [i for i in ids if i not in order]
    if not order:
        raise LLMError('no Groq chat model available for this key')
    log.info('Groq models to try: %s', order[:4])
    _cache['groq'] = order
    return order


def gemini(prompt, temperature=0.2):
    if not config.GEMINI_API_KEY:
        raise LLMError('GEMINI_API_KEY not set')
    last = 'no model tried'
    for model in gemini_models()[:4]:
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
        body = {'contents': [{'parts': [{'text': prompt}]}],
                'generationConfig': {'responseMimeType': 'application/json', 'temperature': temperature}}
        for attempt in range(3):
            r = requests.post(url, params={'key': config.GEMINI_API_KEY}, json=body, timeout=120)
            if r.status_code == 429:
                last = f'{model}: rate limited'; time.sleep(20 * (attempt + 1)); continue
            break
        if r.status_code in (400, 404, 429):           # retired, unsupported option, or out of quota -> next model
            last = f'{model}: HTTP {r.status_code} {r.text[:160]}'
            log.warning('Gemini %s', last)
            continue
        if r.status_code != 200:
            raise LLMError(f'Gemini HTTP {r.status_code}: {r.text[:200]}')
        try:
            return _json(r.json()['candidates'][0]['content']['parts'][0]['text'])
        except (KeyError, IndexError, ValueError) as e:
            last = f'{model}: unreadable answer ({e})'
            continue
    raise LLMError(f'Gemini failed: {last}')


def groq(prompt, temperature=0.0):
    if not config.GROQ_API_KEY:
        raise LLMError('GROQ_API_KEY not set')
    last = 'no model tried'
    for model in groq_models()[:4]:
        for use_json_mode in (True, False):
            body = {'model': model, 'temperature': temperature,
                    'messages': [{'role': 'user', 'content': prompt + '\n\nReply with JSON only.'}]}
            if use_json_mode:
                body['response_format'] = {'type': 'json_object'}
            for attempt in range(3):
                r = requests.post('https://api.groq.com/openai/v1/chat/completions',
                                  headers={'Authorization': f'Bearer {config.GROQ_API_KEY}'}, json=body, timeout=120)
                if r.status_code == 429:
                    last = f'{model}: rate limited'; time.sleep(15 * (attempt + 1)); continue
                break
            if r.status_code == 200:
                try:
                    return _json(r.json()['choices'][0]['message']['content'])
                except (KeyError, IndexError, ValueError) as e:
                    last = f'{model}: unreadable answer ({e})'
                    continue
            last = f'{model}: HTTP {r.status_code} {r.text[:160]}'
            if r.status_code == 400 and use_json_mode:
                continue                                 # model may not support JSON mode - retry without it
            break
        log.warning('Groq %s', last)
    raise LLMError(f'Groq failed: {last}')


def write(prompt):
    """Returns (result, writer_name)."""
    try:
        return gemini(prompt), 'gemini'
    except LLMError as e:
        log.warning('Gemini writer failed (%s), trying Groq', e)
        return groq(prompt, temperature=0.2), 'groq'


def check(prompt, writer_name):
    """Second opinion from the model that did NOT write the draft."""
    if writer_name == 'gemini':
        return groq(prompt), 'groq'
    return gemini(prompt, temperature=0.0), 'gemini'
