# 📈 Sensex Tracker

A free, automated platform that monitors your Indian stock portfolio — live
prices, news, corporate actions (dividends, splits, bonus/results
announcements), quarterly financials, technical indicators, and rule-based
decision flags tuned to a long/medium-term investing style. Includes an
**in-app portfolio editor** so you can add/remove stocks and fix buy
prices/dates right from the dashboard.

**No AI / LLM calls anywhere.** Every signal is a mechanical rule you can read
and tweak. All data sources are free: prices, dividends, splits, earnings dates
and quarterly financials from Yahoo Finance; news and announcements from Google
News RSS.

---

## What it shows

- **Portfolio summary** — invested, current value, total P/L (₹ and %).
- **Top gainers / losers today.**
- **⭐ Booking review — your rule, enforced properly:** flags a holding only if
  it is up **≥ 15%** *and* you've held it **≤ 6 months** (needs the buy date;
  holdings without a date are flagged with "add a buy date"). Long-term
  compounders past 6 months are deliberately left alone.
- **⚠️ Company / sector issues** — holdings with a recent negative headline
  (probe, downgrade, penalty, loss, resignation…) so you read before deciding.
- **🏛️ Corporate actions, results & events** — recent dividends and splits,
  upcoming results dates, plus announcement headlines (bonus issues, record
  dates, buybacks, board meetings, mergers) auto-detected from the news feed.
- **Full holdings table** — price, day %, qty, avg cost, **months held**,
  value, P/L, trend (200-DMA) + RSI, **latest quarterly revenue & profit with
  YoY change**, signal chips, and recent news links.

## 🔔 Proactive alerts (Telegram / email)

The tracker can ping you when something matters instead of you having to check.
Alerts fire for: a holding crossing your **≥15% booking** threshold, **negative
news**, a **results date within a day**, your **price target or stop-loss** hit,
and **watchlist buy-zone** (oversold RSI or price at/below your target). Repeats
are de-duplicated. It's a no-op until you add credentials, so it's safe by
default.

**Telegram (easiest):** message @BotFather to create a bot and get a token;
message @userinfobot to get your chat ID. Then in your repo → Settings →
Secrets and variables → Actions, add secrets `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID`.

**Email (optional):** add `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`,
`SMTP_PASS` (an app password), and `ALERT_TO`.

Tune what fires in `scripts/alert.py`. Test the logic locally with
`python scripts/alert.py --dry`.

## 🔬 Insights — memory, risk, backtest, projections

- **Daily snapshots**: every run records your real portfolio value to
  `docs/snapshots.json`, building a true track record that survives buys/sells
  (history before the first snapshot is reconstructed and labelled as such).
- **Risk analytics**: annualised return & volatility, max drawdown with dates
  and recovery, beta vs Nifty, a Sharpe-style risk-adjusted score, top
  "move-together" correlated pairs, and a 0–100 diversification score.
- **Rule backtest**: your sell-at-+15%-in-6-months rule vs plain buy-and-hold on
  each holding's last year of prices — see whether the rule helps or sells
  winners early (simplified test, labelled).
- **Monte Carlo**: a 3-year probability cone (10th/50th/90th percentile)
  bootstrapped from your portfolio's real daily returns.
- **Health score**: transparent 0–100 per stock from trend, RSI, ROE,
  debt/equity, P/E, profit growth and news — the formula is in
  `scripts/engine.py`, tweak the weights as you like.
- **Concentration flags** when a stock >10% or sector >30% of the portfolio
  (limits editable in `engine.py`).
- **Sell simulator** (Tax page): pick stock + qty + price, see estimated tax,
  the lowest-tax lots to sell first, and your allocation after the sale.
- **App experience**: dark mode toggle, and installable as an app (PWA) — on
  your phone open the site in Chrome/Safari → "Add to Home Screen".
- **Weekly digest**: Monday-morning Telegram/email summary (week change,
  risk stats, review counts, results due this week) if alerts are configured.

## 📊 Analytics — allocation, benchmark, tax & returns

- **Sector allocation** donut + a **portfolio-vs-Nifty-50** toggle on the
  performance chart (both indexed to 100) show concentration and whether you're
  beating the market.
- **Fundamentals** (P/E, ROE, debt/equity, dividend yield, 52-week range) sit in
  the holdings table and drive flags like *near 52-week high* and *high
  debt/equity* — supporting the "company/scope issue" side of your rule.
- **Price targets & stop-losses** per stock (editable) raise *target hit* /
  *below stop* signals; a **notes/thesis** field keeps your reasoning next to
  each stock.
- **Tax & returns** page: LTCG vs STCG split (uses buy dates), estimated tax if
  sold today, a "hold a little longer to save tax" list for positions nearing
  the 1-year mark, **XIRR** annualised return, projected annual dividend income,
  and a realised-gains log from an optional `sells.csv`
  (`ticker,qty,buy_price,buy_date,sell_price,sell_date`). Rates are editable in
  `scripts/tax.py` — **estimates only, not tax advice.**

## ⭐ Watchlist

The **Watchlist** tab tracks stocks you don't own yet — same price, trend, RSI,
news and event scanning as your holdings. Edit it from the in-app editor's
Watchlist tab (or `watchlist.csv` directly: `ticker,name,yahoo_symbol`). A
preview of your watchlist also sits on the Overview page.

## ✎ Editing your portfolio (in-app)

Click **Edit portfolio** on the dashboard: add stocks, remove stocks, correct
quantity, buy price or buy date — the editor has **Holdings** and **Watchlist**
tabs — then **Save to GitHub**. The save commits
`holdings.csv` to your repo and the tracker rebuilds itself automatically in
~1–2 minutes.

One-time setup for saving (5 minutes):

1. GitHub → **Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token**.
2. Repository access: **Only select repositories** → choose your tracker repo.
3. Permissions: **Contents → Read and write**. Nothing else.
4. Generate, copy the `github_pat_…` token, and paste it into the Edit
   portfolio panel along with `your-username/your-repo`.

The token is stored **only in your browser** (localStorage) — it is never
committed to the repo. Anyone who merely *views* your dashboard cannot edit
anything. You can also always edit `holdings.csv` directly on github.com as a
fallback (multiple rows with the same ticker = separate purchase lots; they are
merged automatically with a weighted average cost and the earliest buy date).

---

## Deploy it free (GitHub Actions + GitHub Pages) — ~10 minutes

You need a free GitHub account. Nothing else costs money. Use a **public** repo
for unlimited free Actions minutes (3 runs/day fits private-repo free quota
too, but public is simplest).

1. **Create a repository**, e.g. `sensex-tracker`.
2. **Upload these files** (keep the folder layout): `holdings.csv`,
   `requirements.txt`, `README.md`, `.gitignore`, `scripts/`, `docs/`,
   `.github/workflows/update.yml`. Drag-and-drop via "Add file → Upload files",
   or push with git.
3. **Turn on GitHub Pages:** Settings → Pages → Deploy from a branch →
   Branch **main**, Folder **/docs** → Save. Your dashboard goes live at
   `https://<username>.github.io/sensex-tracker/`.
4. **Enable workflows** in the Actions tab (one click if prompted). To test
   immediately: Actions → Update Sensex Tracker → **Run workflow**.

### Schedule

The scraper runs **3× on trading days** (Mon–Fri): 9:30am, 1:00pm and 4:30pm
IST, plus **instantly whenever you edit your portfolio**. Change the `cron`
lines in `.github/workflows/update.yml` to adjust (times are UTC; IST −5:30).

---

## Maintaining it

- **Holdings:** edit in-app, or edit `holdings.csv` directly. Columns:
  `ticker, name, yahoo_symbol, qty, buy_price, buy_date, seed_price`.
  `yahoo_symbol` = NSE symbol + `.NS` (`.BO` for BSE). `buy_date` =
  `YYYY-MM-DD` (blank allowed — the 6-month rule then asks for it).
  `seed_price` is only a fallback when a symbol has no feed.
- **Rules:** `scripts/engine.py` top section — `SELL_REVIEW_GAIN_PCT` (15),
  `SELL_REVIEW_WINDOW_MONTHS` (6), RSI/SMA thresholds,
  `NEGATIVE_NEWS_KEYWORDS`. Event keywords live in `scripts/corporate.py`.

## Notes & limitations

- **Unlisted / demerger lines** (VOGL, VEDPOWER, VAML, VISL, GOLD1G) may lack a
  public feed; they show a "no feed" badge and use the last known price.
- Quarterly financials come from Yahoo and can lag a company's actual filing by
  a day or two; ETFs and very small caps often have none.
- Prices are ~15-min delayed; this is an end-of-day/intraday-snapshot tracker,
  not a live ticker.
- This is information, **not investment advice** — signals are mechanical
  rules; read the news and use your judgment.

## Run it locally (optional)

```bash
pip install -r requirements.txt
python scripts/update.py          # live data -> docs/index.html
python scripts/update.py --demo   # offline demo with synthetic data
python scripts/test_engine.py     # sanity-check the rule maths
open docs/index.html
```

## 🔒 Making this private (do this)

This repo holds every position, every trade and the running value of a real
portfolio. While it is public, so is all of that.

1. **GitHub → Settings → General → Danger Zone → Change visibility → Private.**
   Nothing breaks: the Action still runs, Cloudflare Pages still deploys (it
   publishes from the workflow, not from repo access), and the in-page editor
   still works because it authenticates with your personal access token.
2. **Settings → Pages → Source: None.** The old `github.io` site is a second,
   unprotected copy of the same data. Private repos cannot serve Pages on a
   free plan anyway, so leaving it on just produces a broken public URL.
3. **Cloudflare → Zero Trust → Access → Applications** — confirm the
   `harrys-sensex-tracker.pages.dev` application exists and its policy allows
   only your email. Then **open the site in a private window** and check you
   are challenged for a login. Until that test passes, assume it is open.
4. **Rotate the token when it expires** (fine-grained, Contents + Workflows
   read/write, this repo only). The scrapes keep running without it, but the
   editor and trade recorder stop being able to save.

Order matters: make it private first, then verify the Access wall, then turn
off Pages.

## 🔑 Passphrase gate (SITE_PASSPHRASE)

A static site has no backend, so it cannot check a password — any check
written in JavaScript is a check the visitor controls and can delete. The only
honest gate is to never serve the plaintext.

Set a repository secret named **`SITE_PASSPHRASE`** and the next build
publishes ciphertext instead of a dashboard:

- `docs/app.enc` — the entire rendered app (markup, data, script), AES-256-GCM
- `docs/stocks.enc` — the per-stock dossiers
- `docs/data.json` and `docs/stocks.json` are **not published at all**
- `docs/index.html` becomes a small unlock screen

Your browser derives the key with PBKDF2-SHA256 (210,000 iterations, a fresh
salt each build) and decrypts locally. The passphrase never leaves the page and
is never stored in the repo. Fetch `app.enc` without it and you get noise.
Tick *stay unlocked on this device* to keep the derived key in local storage;
it stops working on the next build, when the salt rotates.

Remove the secret and the site rebuilds in the clear.

**What this does not hide.** Filenames are still public, so the *list* of
tickers you follow is inferable from `docs/news/` and `docs/prices.json` even
though every number about your position is encrypted. Market data is public
information anyway. If you want the ticker list hidden too, that is what the
Cloudflare Access wall above is for — it stops the request before any file is
served. The two are complementary: Access controls who reaches the site,
the passphrase controls whether the bytes mean anything.
