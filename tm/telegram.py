"""Telegram: send drafts for approval, read taps and commands."""
import html
import json

import requests

from . import config, store
from .util import log, scrub


class TelegramError(Exception):
    pass


def _api(method, files=None, **params):
    """Telegram call with retries. Errors never include the bot token (the URL is not echoed)."""
    if config.DRY_RUN or not config.TELEGRAM_TOKEN:
        log.info('[telegram dry-run] %s %s', method, {k: (str(v)[:120]) for k, v in params.items()})
        return {'message_id': 0} if method != 'getUpdates' else []
    import time
    last = ''
    for attempt in range(4):
        try:
            if files:
                for f in files.values():
                    f.seek(0)
            r = requests.post(f'https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/{method}',
                              data=params, files=files, timeout=60)
            j = r.json()
        except (requests.RequestException, ValueError) as e:
            last = type(e).__name__                  # name only: the message would contain the URL with the token
            time.sleep(3 * (attempt + 1))
            continue
        if j.get('ok'):
            return j['result']
        if r.status_code == 429:
            time.sleep(int((j.get('parameters') or {}).get('retry_after', 5)) + 1)
            last = 'rate limited'
            continue
        raise TelegramError(f'Telegram {method}: {j.get("description")}')
    raise TelegramError(f'Telegram {method}: not reachable ({last})')


def send_text(text, buttons=None):
    params = {'chat_id': config.TELEGRAM_CHAT_ID, 'text': scrub(text)[:4096], 'parse_mode': 'HTML',
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


def send_video(rel, cover_rel=None):
    with open(config.DATA_DIR / rel, 'rb') as f:
        files = {'video': f}
        if cover_rel:
            files['thumbnail'] = open(config.DATA_DIR / cover_rel, 'rb')
        try:
            return _api('sendVideo', files=files, chat_id=config.TELEGRAM_CHAT_ID, supports_streaming='true',
                        width=1080, height=1920)
        finally:
            if cover_rel:
                files['thumbnail'].close()


def send_audio(path, caption=''):
    with open(path, 'rb') as f:
        return _api('sendAudio', files={'audio': f}, chat_id=config.TELEGRAM_CHAT_ID, caption=caption[:1000])


def send_draft(d, auto=False):
    """Images (or the reel), then the caption + verification report with buttons.
    auto=True: the post goes out by itself after the cancel window unless you tap Cancel."""
    if d.get('video'):
        send_video(d['video'], d['images'][0] if d['images'] else None)
    else:
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
    try:
        ups = _api('getUpdates', offset=offset, timeout=0, allowed_updates=json.dumps(['message', 'callback_query']))
    except TelegramError as e:                       # network blip: try again on the next run, no crash
        log.warning('%s - will retry next run', e)
        return []
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
