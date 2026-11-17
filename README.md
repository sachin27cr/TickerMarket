# Ticker Market India — automated stock market news bot

Finds Indian market news and data, writes the posts, checks every fact, and sends each draft to your
Telegram. You tap **Approve** and it posts to Instagram, Facebook and Threads.

**Auto-post (optional)** — repo variable `TM_AUTO_POST`:
- empty (default): every post waits for your tap
- `data`: data cards (close, overview, movers, FII/DII, global, IPO, day ahead, weekly lists) post by themselves
  `TM_AUTO_DELAY_MIN` minutes (default 10) after you get them in Telegram, unless you tap **Cancel**. News still waits.
- `all`: news auto-posts too (not recommended)
A draft with any ⚠️ warning (e.g. single-source data) never auto-posts; it waits for your tap.

## What it posts (about 13–15 drafts per trading day)

| Time (IST) | Post | How the numbers are made |
| --- | --- | --- |
| 7:25 AM | Global cues (US close, crude, gold, USD/INR) | Yahoo Finance data, fixed caption template |
| 8:35 AM | Market day ahead (results, ex-dates, IPOs open) | NSE event calendar, corporate actions, IPO list |
| 9:10 AM | IPO cards for issues opening today/tomorrow | NSE IPO list |
| 10:05 AM, 12:35 PM, 5:45 PM, 9:05 PM | News (2 per run, set `TM_NEWS_PER_RUN`) | AI writes from sources, code checks every fact |
| 3:50 PM | Market close card | NSE closing data, cross-checked with Yahoo |
| 4:15 PM | **Gainers & losers by market cap** carousel: Large (Nifty 100), Mid (Midcap 150), Small (Smallcap 250), Micro (Microcap 250) | NSE closing data; each % re-computed from price |
| 4:35 PM | **Daily market overview** carousel (indices, sectors, top movers, rupee/commodities) | NSE + Yahoo |
| 6:20–8:20 PM | FII/DII card (posts once, when NSE publishes) | NSE provisional data |
| Sat 10:05 AM, Sun 6:05 PM | Weekend news | as above |
| Sat 11:05 AM | **Weekly all-time highs** carousel, up to 10 stocks per market-cap group | Yahoo full price history, level confirmed against NSE 52-week high |
| Sat 5:05 PM | **Weekly 52-week lows** carousel, up to 10 stocks per group | Yahoo price history, confirmed against NSE 52-week low |

Market holidays are detected automatically: if NSE has no session today, close/overview cards are skipped.

## Look of the posts

- Every post has generated background art (night skyline, glowing candles, trend arrow green/red by
  direction; solar, bank, IPO themes for those stories) - drawn in code, so no copyright issues and no AI
  images of real people. Code: `tm/render/art.py`.
- News about specific companies shows a company badge (initials in a fixed colour) and a price box with
  NSE price, change, % and time. The price is cross-checked with Yahoo; if anything does not match, the
  box is left off rather than shown wrong. Code: `tm/render/widgets.py`, `market.company_quotes`.

## How a fact gets checked

1. **Data cards** (close, overview, FII/DII, global, IPO, day ahead): numbers come from NSE/Yahoo; the caption is a
   fixed template, and code confirms every number in the caption equals the data. Index closes are compared
   between NSE and Yahoo; a gap above 0.05% blocks the card.
2. **News**: a story must be reported by an official source (NSE/RBI/SEBI) or by 2+ different publishers, and be
   under 18 hours old. Gemini writes it from those sources only. Then code checks that every number, name and month
   in the draft appears in the sources, blocks advice/prediction/rumour words, and a second AI (Groq Llama) re-reads the
   draft against the sources. Any failure blocks the draft — you get a short "⛔ Blocked" note instead.
3. Every draft arrives in Telegram with its check list, so you can see why it is safe before tapping Approve.

## One-time setup

1. **Create a public repo** (public = free unlimited GitHub Actions minutes) and push this code.
2. **Telegram**: create a bot with @BotFather, send it any message, then get your chat ID
   (open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `message.chat.id`).
3. **Keys** — add these in GitHub → Settings → Secrets and variables → Actions → *Secrets*:

| Secret | Where to get it |
| --- | --- |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | step 2 |
| `GEMINI_API_KEY` | aistudio.google.com — use a **new Google project**, separate from Cinema Woods |
| `GROQ_API_KEY` | console.groq.com (free) |
| `META_PAGE_ID`, `META_PAGE_TOKEN`, `IG_USER_ID` | same Meta app setup as Cinema Woods, for the Ticker Market India page |
| `THREADS_USER_ID`, `THREADS_TOKEN` | Threads API (optional; remove `threads` from `TM_POST_TO` if not set) |

4. Optional *Variables* (same screen, Variables tab): `TM_NEWS_PER_RUN` (default 2), `TM_POST_TO`
   (default `instagram,facebook,threads`), `TM_AUTO_POST` (see above), `TM_AUTO_DELAY_MIN` (default 10).
5. Actions tab → enable workflows. Run **Scheduled posts → Run workflow → job: news** once to test.

## Reliable timing (Cloudflare Worker)

GitHub's built-in cron often skips or delays runs on new repos. `worker/scheduler-worker.js` is a free
Cloudflare Worker that runs every 5 minutes, starts each job at its IST time and runs the approvals check.
GitHub's own schedule stays on as a backup; duplicate triggers are ignored (data posts are made once per
day, news runs at most once per 50 minutes).

## Telegram commands

`/news` `/close` `/capmovers` `/overview` `/ath` `/lows` `/fii` `/global` `/dayahead` `/ipo` run a job now ·
`/queue` drafts waiting · `/flagged` recently blocked drafts with reasons · `/feeds` news feed health ·
`/pause` `/resume` stop/restart scheduled drafts.

Taps are picked up by a job that runs every 5 minutes (GitHub can run it a few minutes late).

## Where things live

- `tm/sources` — NSE, Yahoo, RSS · `tm/verify` — fact checks · `tm/writer` — AI prompts and captions
- `tm/render/cards.py` — post designs · `tm/publish/meta.py` — Instagram/Facebook/Threads · `tm/jobs` — each post type
- `config/feeds.json` — news sources (tier 1 = official) · `config/brand.json` — India / Global brand settings
- The `data` branch (created automatically) stores drafts, dedupe keys and post images. Meta reads the images
  from it, so the repo must stay public.

## Tests (no internet needed)

```
python -m tests.test_render                                      # renders every template to tests/out
TM_DRY_RUN=1 TM_DATA_DIR=/tmp/tmdata python -m tests.test_pipeline   # runs every job with fake data
```

## Ticker Market Global later

Set `TM_PAGE: global` in a copy of the workflows and add a global feeds list; the logo and handle switch from
`config/brand.json`.
