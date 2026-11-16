"""Telegram: send drafts for approval, read taps and commands."""
import html
import json

import requests

from . import config, store
from .util import log


def _api(method, files=None, **params):
    if config.DRY_RUN or not config.TELEGRAM_TOKEN:
        log.info('[telegram dry-run] %s %s', method, {k: (str(v)[:120]) for k, v in params.items()})
        return {'message_id': 0} if method != 'getUpdates' else []
    r = requests.post(f'https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/{method}',
                      data=params, files=files, timeout=60)
    j = r.json()
    if not j.get('ok'):
        raise RuntimeError(f'Telegram {method}: {j.get("description")}')
    return j['result']


def send_text(text, buttons=None):
    params = {'chat_id': config.TELEGRAM_CHAT_ID, 'text': text[:4096], 'parse_mode': 'HTML',
              'disable_web_page_preview': 'true'}
    if buttons:
        params['reply_markup'] = json.dumps({'inline_keyboard': buttons})
    return _api('sendMessage', **params)


def send_images(paths):
    full = [config.DATA_DIR / p for p in paths]
    if len(full) == 1:
        with open(full[0], 'rb') as f:
            return _api('sendPhoto', files={'photo': f}, chat_id=config.TELEGRAM_CHAT_ID)
    files, media = {}, []
    for i, p in enumerate(full[:10]):
        files[f'f{i}'] = open(p, 'rb')
        media.append({'type': 'photo', 'media': f'attach://f{i}'})
    try:
        return _api('sendMediaGroup', files=files, chat_id=config.TELEGRAM_CHAT_ID, media=json.dumps(media))
    finally:
        for f in files.values():
            f.close()


def send_draft(d, auto=False):
    """Images, then the caption + verification report with buttons.
    auto=True: the post goes out by itself after the cancel window unless you tap Cancel."""
    send_images(d['images'])
    head = (f'<b>AUTO-POST {d["id"]}</b> - {html.escape(d["kind"])} - posts in about {config.AUTO_DELAY_MIN} min'
            if auto else f'<b>DRAFT {d["id"]}</b> - {html.escape(d["kind"])}')
    text = f'{head}\n\n{html.escape(d["caption"])}\n\n<b>Checks</b>\n{html.escape(d["report_text"])}'
    buttons = ([[{'text': '🚀 Post now', 'callback_data': f'ap:{d["id"]}'},
                 {'text': '✋ Cancel', 'callback_data': f'rj:{d["id"]}'}]] if auto else
               [[{'text': '✅ Approve & post', 'callback_data': f'ap:{d["id"]}'},
                 {'text': '❌ Reject', 'callback_data': f'rj:{d["id"]}'}]])
    msg = send_text(text, buttons)
    d['telegram_message_id'] = msg.get('message_id')
    store.save_draft(d)


def send_blocked(kind, title, report_text):
    """Blocked drafts are logged quietly for /flagged instead of being sent as drafts."""
    store.write_json(f'flagged/{store.key_hash(kind + title)}.json',
                     {'kind': kind, 'title': title, 'report': report_text})


def get_updates():
    offset = store.read_json('telegram_offset.json', {'offset': 0})['offset']
    ups = _api('getUpdates', offset=offset, timeout=0, allowed_updates=json.dumps(['message', 'callback_query']))
    if ups:
        store.write_json('telegram_offset.json', {'offset': ups[-1]['update_id'] + 1})
    return ups


def answer_callback(cb_id, text):
    try:
        _api('answerCallbackQuery', callback_query_id=cb_id, text=text[:190])
    except Exception as e:                           # noqa: BLE001
        log.warning('answerCallbackQuery: %s', e)


def mark_message(message_id, label):
    if not message_id:
        return
    try:
        _api('editMessageReplyMarkup', chat_id=config.TELEGRAM_CHAT_ID, message_id=message_id,
             reply_markup=json.dumps({'inline_keyboard': [[{'text': label, 'callback_data': 'noop'}]]}))
    except Exception as e:                           # noqa: BLE001
        log.warning('editMessageReplyMarkup: %s', e)
