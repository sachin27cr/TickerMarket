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


def _post(endpoint, **params):
    r = requests.post(endpoint, data=params, timeout=60)
    j = r.json() if r.headers.get('content-type', '').startswith(('application/json', 'text/javascript')) else {}
    if r.status_code != 200 or 'error' in j:
        raise PublishError(f'{endpoint.split("/")[-1]}: {j.get("error", {}).get("message", r.text[:200])}')
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


def publish_all(image_urls, caption, threads_text, only=None):
    """Returns {platform: id or 'error: ...'}; one platform failing does not stop the others.
    only: post just to these platforms (used to retry the ones that failed)."""
    out = {}
    jobs = {'instagram': lambda: instagram(image_urls, caption),
            'facebook': lambda: facebook(image_urls, caption),
            'threads': lambda: threads(image_urls, threads_text)}
    for name in (only or config.POST_TO):
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


# ---------------------------------------------------------------- reels (video)

def _wait_video(container_id, token, base=G, tries=60):
    for _ in range(tries):
        r = requests.get(f'{base}/{container_id}', params={'fields': 'status_code,status', 'access_token': token},
                         timeout=30)
        j = r.json()
        s = j.get('status_code')
        if s == 'FINISHED':
            return
        if s == 'ERROR':
            raise PublishError(f'video processing failed: {j.get("status", "")}'[:200])
        time.sleep(6)
    raise PublishError('video not processed in time')


def instagram_reel(path, caption, cover_url=None):
    """Resumable upload: the file goes straight to Meta (no public video link needed)."""
    tok, uid = config.META_PAGE_TOKEN, config.IG_USER_ID
    params = {'media_type': 'REELS', 'upload_type': 'resumable', 'caption': caption, 'share_to_feed': 'true',
              'access_token': tok}
    if cover_url:
        params['cover_url'] = cover_url
    j = _post(f'{G}/{uid}/media', **params)
    data = open(path, 'rb').read()
    r = requests.post(j.get('uri') or f'https://rupload.facebook.com/ig-api-upload/{config.GRAPH_VERSION}/{j["id"]}',
                      headers={'Authorization': f'OAuth {tok}', 'offset': '0', 'file_size': str(len(data))},
                      data=data, timeout=300)
    if r.status_code != 200:
        raise PublishError(f'reel upload HTTP {r.status_code}: {r.text[:200]}')
    _wait_video(j['id'], tok)
    return _post(f'{G}/{uid}/media_publish', creation_id=j['id'], access_token=tok)['id']


def facebook_reel(path, caption):
    tok, pid = config.META_PAGE_TOKEN, config.META_PAGE_ID
    start = _post(f'{G}/{pid}/video_reels', upload_phase='start', access_token=tok)
    vid = start['video_id']
    data = open(path, 'rb').read()
    r = requests.post(start.get('upload_url') or f'https://rupload.facebook.com/video-upload/{config.GRAPH_VERSION}/{vid}',
                      headers={'Authorization': f'OAuth {tok}', 'offset': '0', 'file_size': str(len(data))},
                      data=data, timeout=300)
    if r.status_code != 200:
        raise PublishError(f'FB reel upload HTTP {r.status_code}: {r.text[:200]}')
    _post(f'{G}/{pid}/video_reels', upload_phase='finish', video_id=vid, video_state='PUBLISHED',
          description=caption, access_token=tok)
    return vid


def threads_video(video_url, text):
    tok, uid = config.THREADS_TOKEN, config.THREADS_USER_ID
    c = _post(f'{T}/{uid}/threads', media_type='VIDEO', video_url=video_url, text=text, access_token=tok)['id']
    for _ in range(40):                       # Threads processes the video from the public link
        r = requests.get(f'{T}/{c}', params={'fields': 'status', 'access_token': tok}, timeout=30).json()
        if r.get('status') == 'FINISHED':
            break
        if r.get('status') == 'ERROR':
            raise PublishError('Threads video processing failed')
        time.sleep(6)
    return _post(f'{T}/{uid}/threads_publish', creation_id=c, access_token=tok)['id']


def publish_reel(path, video_url, caption, threads_text, cover_url=None, only=None):
    out = {}
    jobs = {'instagram': lambda: instagram_reel(path, caption, cover_url),
            'facebook': lambda: facebook_reel(path, caption),
            'threads': lambda: threads_video(video_url, threads_text)}
    for name in (only or config.POST_TO):
        if config.DRY_RUN:
            out[name] = 'dry-run'
            continue
        try:
            out[name] = jobs[name]()
        except Exception as e:                       # noqa: BLE001
            from ..util import scrub
            msg = scrub(type(e).__name__ if 'access_token' in str(e) else str(e))
            log.error('%s reel publish failed: %s', name, msg)
            out[name] = f'error: {msg}'
    return out


def check_setup():
    """Read-only check of the Meta keys (posts nothing). Returns a list of (ok, message); never shows a token."""
    out = []
    tok, pid, uid = config.META_PAGE_TOKEN, config.META_PAGE_ID, config.IG_USER_ID
    if not (tok and pid):
        return [(False, 'META_PAGE_ID / META_PAGE_TOKEN secrets are not set')]

    def get(path, **p):
        r = requests.get(f'{G}/{path}', params={**p, 'access_token': tok}, timeout=30)
        j = r.json()
        if 'error' in j:
            raise PublishError(j['error'].get('message', 'error'))
        return j
    try:
        page = get(pid, fields='name,instagram_business_account')
        out.append((True, f'Facebook Page: {page.get("name")}'))
        linked = (page.get('instagram_business_account') or {}).get('id')
        if not linked:
            out.append((False, 'No Instagram professional account is linked to this Page'))
        elif uid and linked != uid:
            out.append((False, f'IG_USER_ID does not match the Instagram account linked to the Page ({linked})'))
        else:
            ig = get(linked, fields='username')
            out.append((True, f'Instagram: @{ig.get("username")}' + ('' if uid else f' - set IG_USER_ID to {linked}')))
    except (PublishError, requests.RequestException) as e:
        out.append((False, f'Meta said: {util_scrub(str(e))}'))
        return out
    try:
        dbg = get('debug_token', input_token=tok).get('data', {})
        exp = dbg.get('expires_at', 0)
        out.append((exp == 0, 'Page token never expires' if exp == 0 else
                    f'Page token expires {time.strftime("%d %b %Y", time.localtime(exp))} - make a never-expiring one'))
        need = {'pages_manage_posts', 'pages_read_engagement', 'instagram_basic', 'instagram_content_publish'}
        missing = need - set(dbg.get('scopes') or [])
        out.append((not missing, 'All posting permissions granted' if not missing else
                    'Missing permissions: ' + ', '.join(sorted(missing))))
    except (PublishError, requests.RequestException) as e:
        out.append((False, f'Could not check token expiry: {util_scrub(str(e))}'))
    return out


def util_scrub(s):
    from ..util import scrub
    return scrub(s)
