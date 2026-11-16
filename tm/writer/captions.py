"""Caption assembly. Data posts use fixed templates (no AI), so their numbers come straight from data."""
import re

from .. import config

DISCLAIMER = 'For information only. Not investment advice.'


def plain(headline):
    return re.sub(r'\*', '', headline).upper()


def assemble(headline, paragraphs, source, hashtags):
    tags = ' '.join(hashtags[:5])
    body = '\n\n'.join(p.strip() for p in paragraphs if p.strip())
    return f'{plain(headline)}\n\n{body}\n\nSource: {source}. {DISCLAIMER}\n\n{tags}'


def threads_text(caption, limit=500):
    """Shorter copy of the Instagram caption (same wording), within the Threads limit."""
    parts = caption.split('\n\n')
    head, tags = parts[0], parts[-1] if parts[-1].startswith('#') else ''
    body = [p for p in parts[1:] if not p.startswith('#')]
    out = head
    for p in body:
        cand = out + '\n\n' + p
        if len(cand) + len(tags) + 2 <= limit:
            out = cand
        else:
            # add as many whole sentences of this paragraph as fit
            sents = re.split(r'(?<=[.!?])\s+', p)
            acc = ''
            for s in sents:
                trial = (acc + ' ' + s).strip()
                if len(out) + 2 + len(trial) + len(tags) + 2 <= limit:
                    acc = trial
                else:
                    break
            if acc:
                out += '\n\n' + acc
            break
    if tags and len(out) + 2 + len(tags) <= limit:
        out += '\n\n' + tags
    return out[:limit]


def tags(*extra):
    base = list(config.BRAND['hashtag_base'])
    out = []
    for t in list(extra) + base:
        if t not in out:
            out.append(t)
    return out[:5]
