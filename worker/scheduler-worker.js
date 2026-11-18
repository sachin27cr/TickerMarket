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
 * Trigger: Settings -> Triggers -> Cron Triggers -> add  * / 5 * * * *  (no spaces)
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

export default {
  async scheduled(event, env, ctx) {
    const { day, slot } = istSlot(event.scheduledTime);
    const due = SCHEDULE.filter(([d, t]) => t === slot && d.includes(day)).map(s => s[2]);
    const tasks = due.map(job => dispatch(env, 'scheduler.yml', { job, force: false }));
    tasks.push(dispatch(env, 'approvals.yml', {}));
    ctx.waitUntil(Promise.all(tasks));
  },

  async fetch(request, env) {
    const url = new URL(request.url);
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
