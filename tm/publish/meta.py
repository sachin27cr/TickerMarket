"""Instagram (single image or carousel), Facebook Page and Threads publishing via Meta APIs.

Images are read by Meta from public URLs on the repo's `data` branch (repo must be public).
"""
import time

import requests

from .. import config
from ..util import log

G = f'https://graph.facebook.com/{config.GRAPH_VERSION}'
T = 'https://graph.threads.net/v1.0'


class PublishError(Exception):
    pass


def _post(url, **params):
    r = requests.post(url, data=params, timeout=60)
    j = r.json() if r.headers.get('content-type', '').startswith(('application/json', 'text/javascript')) else {}
    if r.status_code != 200 or 'error' in j:
        raise PublishError(f'{url.split("/")[-1]}: {j.get("error", {}).get("message", r.text[:200])}')
    return j


def _wait_ready(container_id, token, base=G, tries=30):
    for _ in range(tries):
        r = requests.get(f'{base}/{container_id}', params={'fields': 'status_code', 'access_token': token}, timeout=30)
        s = r.json().get('status_code')
        if s == 'FINISHED':
            return
        if s == 'ERROR':
            raise PublishError(f'container {container_id} failed processing')
        time.sleep(4)
    raise PublishError(f'container {container_id} not ready in time')


def instagram(image_urls, caption):
    tok, uid = config.META_PAGE_TOKEN, config.IG_USER_ID
    if len(image_urls) == 1:
        c = _post(f'{G}/{uid}/media', image_url=image_urls[0], caption=caption, access_token=tok)['id']
    else:
        kids = [_post(f'{G}/{uid}/media', image_url=u, is_carousel_item='true', access_token=tok)['id']
                for u in image_urls[:10]]
        for k in kids:
            _wait_ready(k, tok)
        c = _post(f'{G}/{uid}/media', media_type='CAROUSEL', children=','.join(kids), caption=caption,
                  access_token=tok)['id']
    _wait_ready(c, tok)
    return _post(f'{G}/{uid}/media_publish', creation_id=c, access_token=tok)['id']


def facebook(image_urls, caption):
    tok, pid = config.META_PAGE_TOKEN, config.META_PAGE_ID
    if len(image_urls) == 1:
        return _post(f'{G}/{pid}/photos', url=image_urls[0], caption=caption, access_token=tok)['id']
    media = [_post(f'{G}/{pid}/photos', url=u, published='false', access_token=tok)['id'] for u in image_urls[:10]]
    params = {'message': caption, 'access_token': tok}
    for i, m in enumerate(media):
        params[f'attached_media[{i}]'] = f'{{"media_fbid":"{m}"}}'
    return _post(f'{G}/{pid}/feed', **params)['id']


def threads(image_urls, text):
    tok, uid = config.THREADS_TOKEN, config.THREADS_USER_ID
    if len(image_urls) == 1:
        c = _post(f'{T}/{uid}/threads', media_type='IMAGE', image_url=image_urls[0], text=text, access_token=tok)['id']
    else:
        kids = [_post(f'{T}/{uid}/threads', media_type='IMAGE', image_url=u, is_carousel_item='true',
                      access_token=tok)['id'] for u in image_urls[:10]]
        time.sleep(10)
        c = _post(f'{T}/{uid}/threads', media_type='CAROUSEL', children=','.join(kids), text=text,
                  access_token=tok)['id']
    time.sleep(15)                     # Threads asks for a short wait before publishing
    return _post(f'{T}/{uid}/threads_publish', creation_id=c, access_token=tok)['id']


def publish_all(image_urls, caption, threads_text):
    """Returns {platform: id or 'error: ...'}; one platform failing does not stop the others."""
    out = {}
    jobs = {'instagram': lambda: instagram(image_urls, caption),
            'facebook': lambda: facebook(image_urls, caption),
            'threads': lambda: threads(image_urls, threads_text)}
    for name in config.POST_TO:
        if config.DRY_RUN:
            out[name] = 'dry-run'
            continue
        try:
            out[name] = jobs[name]()
        except Exception as e:                       # noqa: BLE001
            from ..util import scrub
            msg = scrub(type(e).__name__ if 'access_token' in str(e) else str(e))
            log.error('%s publish failed: %s', name, msg)
            out[name] = f'error: {msg}'
    return out
