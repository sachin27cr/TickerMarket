/**
 * Ticker Market India - scheduler (Cloudflare Worker, free plan).
 *
 * GitHub's own cron is unreliable for new repos, so this Worker runs every 5 minutes and starts
 * the right GitHub Actions job at the right IST time, plus the Telegram approvals check.
 *
 * Settings (Worker -> Settings -> Variables and Secrets):
 *   GH_REPO   (text)   sachin27cr/TickerMarket
 *   GH_TOKEN  (secret) fine-grained GitHub token with "Actions: Read and write" on this repo
 *   RUN_KEY   (secret) any password you choose, for manual runs from a browser
 *   TELEGRAM_BOT_TOKEN (secret) same bot token as in GitHub      } for instant replies to
 *   TELEGRAM_CHAT_ID   (text)   same chat id as in GitHub        } taps and commands
 *   TG_SECRET          (secret) any random text (letters/digits)  }
 * Trigger: Settings -> Triggers -> Cron Triggers -> add  * / 5 * * * *  (no spaces)
 *
 * Instant replies: after adding the three Telegram settings and deploying, open once in a browser
 *   https://<your-worker>.workers.dev/setup?key=<RUN_KEY>
 * Telegram then sends every tap/command straight here; the Worker answers at once and starts the job.
 *
 * Manual run from a browser:  https://<your-worker>.workers.dev/run?job=news&key=<RUN_KEY>
 */

// [days (0=Sun..6=Sat), "HH:MM" IST, job]
const SCHEDULE = [
  ['12345', '07:25', 'global_cues'],
  ['12345', '07:35', 'reel_morning'],   // ready to approve before 8 AM
  ['12345', '08:35', 'day_ahead'],
  ['12345', '09:10', 'ipo'],
  ['12345', '10:05', 'news'],
  ['12345', '12:35', 'news'],
  ['12345', '15:50', 'market_close'],
  ['12345', '16:15', 'cap_movers'],
  ['12345', '16:35', 'daily_overview'],
  ['12345', '16:50', 'reel_evening'],
  ['12345', '17:20', 'ipo_status'],
  ['12345', '17:45', 'news'],
  ['12345', '18:20', 'fii_dii'],
  ['12345', '19:20', 'fii_dii'],
  ['12345', '20:05', 'results_spotlight'],
  ['12345', '20:20', 'fii_dii'],
  ['12345', '21:05', 'news'],
  ['6', '10:05', 'news'],
  ['6', '11:05', 'weekly_ath'],
  ['6', '11:20', 'reel_ath'],
  ['6', '12:35', 'reel_weekly'],
  ['6', '17:05', 'weekly_lows'],
  ['6', '17:20', 'reel_lows'],
  ['0', '18:05', 'news'],
  ['0123456', '18:40', 'insights'],   // posts every other day; skips itself on the days in between
];
const JOBS = new Set(SCHEDULE.map(s => s[2]));

async function dispatch(env, workflow, inputs) {
  const r = await fetch(`https://api.github.com/repos/${env.GH_REPO}/actions/workflows/${workflow}/dispatches`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.GH_TOKEN}`,
      'Accept': 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'ticker-market-scheduler',
    },
    body: JSON.stringify({ ref: 'main', inputs }),
  });
  const ok = r.status === 204;
  if (!ok) console.log(`dispatch ${workflow} ${JSON.stringify(inputs)} -> ${r.status} ${await r.text()}`);
  return ok;
}

function istSlot(ms) {
  const ist = new Date(ms + 330 * 60000);
  const hh = String(ist.getUTCHours()).padStart(2, '0');
  const mm = String(Math.floor(ist.getUTCMinutes() / 5) * 5).padStart(2, '0');
  return { day: String(ist.getUTCDay()), slot: `${hh}:${mm}` };
}

async function tg(env, method, body) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  return r.json();
}

const LONG = new Set(['/news', '/close', '/overview', '/fii', '/dayahead', '/global', '/ipo', '/iposubs', '/capmovers', '/ath', '/lows',
  '/innovative', '/insight', '/insights', '/reelam', '/reelpm', '/reelweek', '/reelath', '/reellows', '/spotlight']);

async function onTelegram(request, env, ctx) {
  if (request.headers.get('X-Telegram-Bot-Api-Secret-Token') !== env.TG_SECRET) return new Response('no', { status: 403 });
  const u = await request.json();
  const cb = u.callback_query;
  const msg = u.message;
  const chat = String((cb ? cb.message.chat.id : msg && msg.chat.id) || '');
  if (chat !== String(env.TELEGRAM_CHAT_ID)) return new Response('ok');   // ignore everyone else
  const work = [];
  let lock = '';
  if (cb) {
    const [action, did] = (cb.data || '').split(':');
    if (action !== 'ap' && action !== 'rj') {              // a status label: nothing to do
      await tg(env, 'answerCallbackQuery', { callback_query_id: cb.id, text: 'Already in progress or done - no need to tap again.' });
      return new Response('ok');
    }
    lock = 'd-' + did;                                     // taps on one draft never run in parallel
    // swap the buttons for a status at once, so a second tap can't post twice
    work.push(tg(env, 'editMessageReplyMarkup', { chat_id: chat, message_id: cb.message.message_id,
      reply_markup: { inline_keyboard: [[{ text: action === 'ap' ? '⏳ Approved - posting…' : '⏳ Rejecting…',
        callback_data: 'noop' }]] } }));
    work.push(tg(env, 'answerCallbackQuery', { callback_query_id: cb.id,
      text: action === 'ap' ? '✅ Approved - posting now. The button will show Posted when done.' : 'Rejected' }));
  } else if (msg && (msg.text || '').startsWith('/')) {
    const cmd = msg.text.trim().split(/\s+/)[0].split('@')[0].toLowerCase();
    work.push(tg(env, 'sendMessage', { chat_id: chat, disable_notification: true,
      text: LONG.has(cmd) ? `⏳ ${cmd} started - the draft arrives in a few minutes.` : `⏳ ${cmd} - on it…` }));
  } else {
    return new Response('ok');
  }
  // forward the update to GitHub (keep it small: drop the message photos/entities we don't use)
  const slim = JSON.stringify(u).slice(0, 60000);
  work.push(dispatch(env, 'approvals.yml', { update: slim, update_id: String(u.update_id), lock }));
  ctx.waitUntil(Promise.all(work));
  return new Response('ok');
}

export default {
  async scheduled(event, env, ctx) {
    const { day, slot } = istSlot(event.scheduledTime);
    const due = SCHEDULE.filter(([d, t]) => t === slot && d.includes(day)).map(s => s[2]);
    const tasks = due.map(job => dispatch(env, 'scheduler.yml', { job, force: false }));
    tasks.push(dispatch(env, 'approvals.yml', {}));
    ctx.waitUntil(Promise.all(tasks));
  },

  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === '/tg' && request.method === 'POST') return onTelegram(request, env, ctx);
    if (url.pathname === '/setup' || url.pathname === '/unsetup') {
      if (!env.RUN_KEY || url.searchParams.get('key') !== env.RUN_KEY) return new Response('wrong key', { status: 403 });
      if (url.pathname === '/unsetup') {
        const j = await tg(env, 'deleteWebhook', {});
        return new Response('Instant replies off (bot polls every 5 min again): ' + JSON.stringify(j));
      }
      if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID || !env.TG_SECRET)
        return new Response('Add TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID and TG_SECRET to the Worker settings first.', { status: 400 });
      const j = await tg(env, 'setWebhook', { url: `${url.origin}/tg`, secret_token: env.TG_SECRET,
        allowed_updates: ['message', 'callback_query'], drop_pending_updates: false });
      return new Response(j.ok ? 'Instant replies are ON. Send /help to the bot to test.' : 'Telegram said: ' + j.description);
    }
    if (url.pathname === '/run') {
      if (!env.RUN_KEY || url.searchParams.get('key') !== env.RUN_KEY) return new Response('wrong key', { status: 403 });
      const job = url.searchParams.get('job');
      if (job === 'approvals') return new Response((await dispatch(env, 'approvals.yml', {})) ? 'started approvals' : 'failed - see logs');
      if (!JOBS.has(job)) return new Response('unknown job. Use one of: ' + [...JOBS, 'approvals'].join(', '), { status: 400 });
      const force = url.searchParams.get('force') === 'true';
      const inputs = { job, force };
      if (job === 'insights' && url.searchParams.get('tag')) inputs.arg = url.searchParams.get('tag');
      return new Response((await dispatch(env, 'scheduler.yml', inputs)) ? `started ${job}` : 'failed - see Worker logs');
    }
    const { day, slot } = istSlot(Date.now());
    return new Response(`Ticker Market scheduler is running. IST slot ${slot}, day ${day}.`);
  },
};
