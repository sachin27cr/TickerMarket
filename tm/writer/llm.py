"""LLM calls. Writer = Gemini (fallback Groq). Checker = the *other* model, never the writer."""
import json
import time

import requests

from .. import config
from ..util import log


class LLMError(Exception):
    pass


def gemini(prompt, temperature=0.2):
    if not config.GEMINI_API_KEY:
        raise LLMError('GEMINI_API_KEY not set')
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent'
    body = {'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {'responseMimeType': 'application/json', 'temperature': temperature}}
    for attempt in range(3):
        r = requests.post(url, params={'key': config.GEMINI_API_KEY}, json=body, timeout=90)
        if r.status_code == 429:
            time.sleep(20 * (attempt + 1)); continue
        if r.status_code != 200:
            raise LLMError(f'Gemini HTTP {r.status_code}: {r.text[:200]}')
        try:
            return json.loads(r.json()['candidates'][0]['content']['parts'][0]['text'])
        except (KeyError, IndexError, ValueError) as e:
            raise LLMError(f'Gemini bad response: {e}')
    raise LLMError('Gemini rate limited')


def groq(prompt, temperature=0.0):
    if not config.GROQ_API_KEY:
        raise LLMError('GROQ_API_KEY not set')
    for attempt in range(3):
        r = requests.post('https://api.groq.com/openai/v1/chat/completions',
                          headers={'Authorization': f'Bearer {config.GROQ_API_KEY}'},
                          json={'model': config.GROQ_MODEL, 'temperature': temperature,
                                'response_format': {'type': 'json_object'},
                                'messages': [{'role': 'user', 'content': prompt}]}, timeout=90)
        if r.status_code == 429:
            time.sleep(15 * (attempt + 1)); continue
        if r.status_code != 200:
            raise LLMError(f'Groq HTTP {r.status_code}: {r.text[:200]}')
        try:
            return json.loads(r.json()['choices'][0]['message']['content'])
        except (KeyError, IndexError, ValueError) as e:
            raise LLMError(f'Groq bad response: {e}')
    raise LLMError('Groq rate limited')


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
