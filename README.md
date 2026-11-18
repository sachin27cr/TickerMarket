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
| 8:35 AM | Market day ahead: results today, ex-dates, IPOs open, **global & India events today** (IST), **results calendar for the week** | NSE event calendar, corporate actions, IPO list; ForexFactory high-impact events (US, Eurozone, UK, Japan, China); RBI dates in `config/india_events.json` |
| 9:10 AM | IPO cards for issues opening today/tomorrow | NSE IPO list |
| 10:05 AM, 12:35 PM, 5:45 PM, 9:05 PM | News (2 per run, set `TM_NEWS_PER_RUN`) | AI writes from sources, code checks every fact |
| 3:50 PM | **Closing Bell** carousel: date/day cover with the hook, key indices + breadth, sectors, Nifty 50 movers, rupee/crude/gold/VIX | NSE closing data, cross-checked with Yahoo |
| 4:15 PM | **Gainers & losers by market cap** carousel: Large (Nifty 100), Mid (Midcap 150), Small (Smallcap 250), Micro (Microcap 250) | NSE closing data; each % re-computed from price |
| 4:35 PM | **Highs & Lows** carousel: index scorecard, then new all-time highs / 52-week highs / 52-week lows per market-cap group | NSE 52-week levels; all-time highs from Yahoo full history, confirmed against NSE |
| 5:20 PM | **Live IPO subscription** (only while an IPO is open) | NSE category-wise bids; times re-computed from bids / shares offered |
| 6:20–8:20 PM | FII/DII carousel with FII positions in F&O (posts once, when NSE publishes) | NSE provisional data + NSE participant OI file |
| 8:05 PM (Mon-Fri) | **Results Spotlight**: best results of the last few days (net profit +20% and revenue +10% YoY), one slide per company | NSE results cross-checked with Yahoo; if NSE is unavailable, Yahoo-only figures are flagged on the draft |
| 6:40 PM daily | **Insights** data story, every other day (see below) | NSE + Yahoo, always needs your approval |
| Sat 10:05 AM, Sun 6:05 PM | Weekend news | as above |
| Sat 11:05 AM | **Weekly all-time highs** carousel, up to 10 stocks per market-cap group | Yahoo full price history, level confirmed against NSE 52-week high |
| Sat 5:05 PM | **Weekly 52-week lows** carousel, up to 10 stocks per group | Yahoo price history, confirmed against NSE 52-week low |

### Reels (vertical video with voice-over)

| Time (IST) | Reel | Content |
| --- | --- | --- |
| 7:35 AM (Mon-Fri) | **Morning Brief** - ready to approve before 8 AM | global markets, crude/gold/rupee, last close, FII/DII, results and IPOs today |
| 4:50 PM (Mon-Fri) | **Closing Bell** | indices, breadth, best/weakest sectors, Nifty 50 movers, new highs/lows |
| Sat 11:20 AM | **All-Time Highs** of the week | count and top names per market-cap group |
| Sat 12:35 PM | **Week in Review** | weekly change of Nifty/Sensex/Bank Nifty, FII/DII for the week, highs/lows |
| Sat 5:20 PM | **52-Week Lows** of the week | count and top names per market-cap group |

Voice: free Microsoft Edge neural male voice (default Prabhat, Indian English). Send `/voices` in Telegram to hear
Prabhat, Andrew, Brian and Madhur, then `/voice andrew` (etc.) to choose. Google TTS is the fallback. The voice script, captions and on-screen numbers are
written by code from verified data (no AI). A soft generated music bed sits under the voice (no copyrighted music).
Reels always wait for approval in Telegram; Instagram and Facebook receive the file directly, Threads reads it from the
data branch. Telegram: `/reelam` `/reelpm` `/reelweek` `/reelath` `/reellows`.

### Insights (every other day, or on demand with `/innovative`)

| Tag | Post | Checks |
| --- | --- | --- |
| `profits` | Results season series, "Part 1, 2, 3...": Nifty 500 companies whose quarterly net profit grew 100%+ (or 200%+) YoY. One slide per company: growth %, profit and revenue then vs now, NSE price | Net profit must match between NSE results and Yahoo for both quarters (2%), otherwise the company is left out. Companies already posted are never repeated |
| `assets` | How major assets did last month (Nifty, Sensex, Bank Nifty, gold, silver, crude, rupee, Nasdaq, S&P 500, bitcoin), first week of each month | Nifty/Bank Nifty month-end closes from NSE; others Yahoo (shown as single-source warnings) |
| `mcap` | India's 10 most valuable companies + change this week | NSE issued shares x NSE price, each within 3% of Yahoo |
| `wealth` | Rs 1 lakh in each Nifty 50 stock a year ago: top 5 / bottom 5 | Today's price from NSE; Yahoo price must agree within 0.5% |
| `sectors` | Sector scorecard: 1 week / 1 month / 1 year for 16 sector indices vs Nifty 50 | NSE's own period changes |

The 6:40 PM run posts only if the last insight is 2+ days old. Order: `profits` during results season, `assets` in the first week
of a month, then whichever of `mcap` / `sectors` / `wealth` has waited longest. Every insight ends with a "Follow for more" slide.

Market holidays are detected automatically: if NSE has no session today, close/overview cards are skipped.

## Photo-realistic backgrounds (optional, free)

Add two GitHub secrets and every post gets a realistic picture made by FLUX.1 [schnell] on Cloudflare Workers AI
(free daily quota; the bot stops at 80 pictures a day):
`CF_ACCOUNT_ID` and `CF_AI_TOKEN` (Cloudflare dashboard -> AI -> Workers AI -> Use REST API -> create a Workers AI token).
Pictures never contain text, numbers, logos or real people. Without the secrets, or if a call fails, posts use the
drawn scenes. News pictures follow the story (the writer describes a scene; company names are never used).

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

`/news` `/close` `/capmovers` `/overview` `/ath` `/lows` `/fii` `/global` `/dayahead` `/ipo` `/iposubs` run a job now ·
`/innovative` next insight · `/innovative profits` (or `assets`, `mcap`, `wealth`, `sectors`) a specific one · `/innovative list` ·
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
