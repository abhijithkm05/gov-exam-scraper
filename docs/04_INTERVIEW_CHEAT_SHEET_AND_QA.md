# Interview Readiness Playbook: `gov-exam-scraper`

*(Prepared from a Hiring Manager's perspective, grounded strictly in your actual codebase and production debugging history.)*

---

## 1. 60-Second Elevator Pitch

> "I built **`gov-exam-scraper`**, a **$0/month serverless data pipeline** running on GitHub Actions that automates both broad government job discovery and personal exam lifecycle tracking across India and Karnataka.
>
> Manually tracking 25+ central and state portals like KPSC, KEA, UPSC, SSC, and Railways fails because `.nic.in` servers time out, SPAs require JavaScript rendering, banking portals sit behind Akamai WAFs, and aggregators drown users in duplicate notifications.
>
> To solve this, I engineered a **dual-engine architecture**:
> 1. **Discovery Engine (`scraper.py`):** Concurrently scrapes **25 portals** using a `ThreadPoolExecutor` with a dual-tier `requests` + Playwright Chromium fetcher, deterministic BeautifulSoup DOM parsing, pre-flight HTTP link/redirect validation, and SHA-256 content hashing—syncing **150+ active vacancies** to Notion while auto-archiving expired deadlines.
> 2. **Applied-Exam Lifecycle Watcher (`track_applied.py` + `aggregators.py`):** Dynamically queries a second Notion database tracking **17 exams I've personally applied to**, combining direct board circular scans with firewall-proof **Google News RSS (`en-IN`)** monitoring and milestone-based deduplication in `data/sent_alerts.json`—delivering **one consolidated, zero-spam alert** per exam to Telegram and Discord when admit cards, dates, syllabi, or results drop."

---

## 2. STAR-Format Deep Dive Stories

### Story 1: Pivoting Off LLM Extraction After Hitting Free-Tier TPM Limits & Table Destruction
* **Situation:** I initially built `parse.py` to extract structured `ExamRecord` JSON from messy HTML using Groq's free-tier LLM (`llama-3.1-8b-instant`, later `qwen/qwen3.6-27b`). In live testing across 25 portals, three failures hit simultaneously: model deprecations (`404`/`400`), massive navigation-menu bloat triggering `413`/`429` errors against `qwen/qwen3.6-27b`'s 8,000 Tokens-Per-Minute (TPM) cap (sites like `schooleducation.karnataka.gov.in` requested 59,641 tokens), and `400 json_validate_failed` crashes. Worse, when I added regex keyword line-filtering (`RELEVANT_KEYWORDS`) in `fetch.py` to shrink prompts to ~1,500 tokens, extraction dropped to **0 records** on `upsc.gov.in` and `freejobalert.com`.
* **Task:** Reliably extract active vacancies, deadlines, application URLs, and `.pdf` circulars across 25 portals within strict $0 free-tier limits.
* **Action:** I ran diagnostic scripts against the raw HTML (`inspect_portals.py`, `test_groq_models.py`) and proved that regex line-filtering was slicing `<table>` rows apart—separating exam titles from their dates and URLs—while header menus consumed the truncation budget. I pivoted `GovExamScraper.scrape_source()` from LLM-first to a **deterministic BeautifulSoup DOM parser (`_extract_from_dom`)** that decomposes `nav/header/footer/script/style` tags, extracts intact `<tr>`/`<td>` table rows (with an `<a>` anchor fallback), and parses 9+ Indian date formats via `parse_date_safely()`, while keeping `GroqParser` modular in `parse.py`.
* **Result:** The pipeline extracted **150 active, non-expired vacancies** across 25 portals in under 90 seconds using **zero LLM tokens**, completely eliminating `413`/`429` rate-limit failures and `json_validate_failed` crashes.

### Story 2: Solving Akamai WAF Blind Spots & Multi-Outlet Alert Spam via Google News RSS + Milestone Caching
* **Situation:** On September 24, 2026, SBI Junior Associates released exam dates and admit cards, yet my pipeline sent zero alerts and failed to update Notion. Earlier, enabling `--notify` on the general scraper and matching broad single words like `Assistant` or `Junior` flooded Telegram and Discord with irrelevant jobs and 10–20 duplicate alerts whenever multiple newspapers covered the same event.
* **Task:** Guarantee detection of critical updates for my applied exams even when official portals block cloud IPs, while enforcing a strict **"one verified alert per milestone, zero spam"** guarantee.
* **Action:** Diagnosis showed `sbi.co.in/careers` sat behind **Akamai WAF** (blocking GitHub Actions' Ubuntu/Azure IPs) and coaching portals (Testbook, Adda247, Oliveboard) routed banking posts to sub-paths outside `/news/` and `/exams/`. Rather than crawling full coaching archives (risking Cloudflare bans and 6-hour CI timeouts), I:
  1. Silenced general vacancy notifications by removing `--notify` from Step 1 in `daily-run.yml`.
  2. Built `aggregators.py` using unblockable **Google News RSS (`en-IN`, `when:7d`)** parsed via `xml.etree.ElementTree` with strict per-exam queries (`EXAM_MONITORS`).
  3. Implemented **milestone-based deduplication**: mapping headlines to 5 lifecycle stages (`ADMIT_CARD`, `EXAM_DATE`, `SYLLABUS_PATTERN`, `ANSWER_KEY`, `RESULT`), persisting both `"{exam_name}:{MILESTONE}"` and `urls` in `data/sent_alerts.json` (committed back to `main` via `github-actions[bot]` with `[skip ci]`), grouping matches into one consolidated alert per exam, and auto-patching Notion `Status` and `Admit Card URL`.
* **Result:** Bypassed Akamai/Cloudflare WAF blocks permanently, automated Notion status updates across all **17 tracked applications**, and reduced multi-outlet alert noise to a single verified notification per milestone.

### Story 3: Hardening Unreliable `.nic.in` Fetching, Dead Links, and CI/CD Regressions
* **Situation:** Government `.nic.in` portals threw `Read timed out` errors (`kpsc.kar.nic.in`, `karnatakajudiciary.kar.nic.in`), broken SSL warnings, and `404 Not Found` or `301/302` redirects on PDF circulars. Meanwhile, in CI, top-of-the-hour cron (`0 2 * * *`) missed scheduled triggers, and an automated script adding India Post portals injected raw `dict` literals and a double comma (`),,`) into `DEFAULT_SOURCES` in `scraper.py`, breaking production runs for two days with `SyntaxError` and `AttributeError: 'dict' object has no attribute 'is_active'`.
* **Task:** Make network fetching, link quality, scheduling, and code deployments resilient to flaky government servers and human/script error.
* **Action:**
  1. Built dual-tier fetching (`requests.Session` with `urllib3.Retry`, `60s` timeouts, `verify=False`, and `Accept-Language: en-US,en;q=0.9,kn;q=0.8` + headless Playwright Chromium fallback with `ignore_https_errors=True`) and isolated `scrape_source()` exceptions per portal.
  2. Added `validate_and_resolve_url()` (`HEAD` + `403`/`405` streaming `GET` fallback) to follow redirects to final URLs and strip `>= 400` dead links before computing SHA-256 hashes.
  3. Shifted the GitHub Actions cron from `:00` to **`17 2 * * *`** to dodge global top-of-the-hour runner congestion.
  4. Recovered `scraper.py` via Git history, hardened `scrape_all()` with `getattr(s, "is_active", False)`, and gated script edits with `ast.parse()` / `py_compile` verification before pushing.
* **Result:** Portals that time out no longer crash the 25-source batch, dead 404 PDFs are stripped before hitting Notion or chat alerts, and the automated daily workflow runs cleanly end-to-end.

---

## 3. 10 Tough Technical Interview Questions & Model Answers

### Q1: "Why did you abandon Groq LLM extraction on your main scraping path, and when would you bring an LLM back?"
**Model Answer:**  
"I didn't abandon it conceptually—I moved it off the synchronous critical path after hitting hard empirical limits. On Groq's free tier (`qwen/qwen3.6-27b`), the cap is 8,000 TPM, while raw government pages like `schooleducation.karnataka.gov.in` hit nearly 60,000 tokens (`413` errors). When I stripped HTML via keyword line-filtering (`RELEVANT_KEYWORDS`), it severed `<tr>`/`<td>` relationships so the LLM returned `{"exams": []}`. Since most portals publish in HTML `<table>`s, BeautifulSoup `_extract_from_dom()` gave me deterministic extraction of 150 records at zero token cost. I kept `GroqParser` in `parse.py` for unstructured prose circulars—and if I reintroduced it, I would chunk by intact DOM containers (one `<div>`/`<table>` block at a time) and pace requests under the TPM budget."

### Q2: "How do you detect if a government portal changed its DOM or silently broke?"
**Model Answer:**  
"Right now, there is an honest gap here that I'd fix next for production observability. In `scraper.py`, `scrape_source()` catches exceptions, logs a warning, and returns `[]` so one broken site doesn't kill the whole batch. In `track_applied.py`, `fetch_html_content()` treats sparse responses (`<= 1000` chars) as a trigger to fall back to Playwright. However, if a portal redesigns its HTML tables into nested `<div>` cards without throwing an HTTP error, `_extract_from_dom()` will silently return `0` records. To detect DOM drift, I would persist per-source extracted row counts in a lightweight metrics log and fire a warning alert if a previously productive portal returns `0` records for 2–3 consecutive runs or if Playwright fallback rates spike."

### Q3: "How do you prevent duplicate rows in Notion AND duplicate notifications across runs?"
**Model Answer:**  
"I enforce deduplication at three layers:
1. **Within-run cross-source dedup (`scraper.py`):** `scrape_all()` strips non-alphanumerics from `exam_name.lower()[:40]` into `seen_keys` so the same exam appearing on both KEA and FreeJobAlert isn't duplicated.
2. **Database-level dedup (`models.py` + `scraper.py`):** `ExamRecord.recalculate_hash()` computes a deterministic SHA-256 over `exam_name | sector | last_date | apply_link | pdf_link | status`. `sync_to_notion()` queries existing `Content Hash` strings in Notion and skips matches.
3. **Alert-level milestone dedup (`aggregators.py`):** Because 20 newspapers publish unique URLs for the same admit card, URL caching alone fails. I store both `urls` and `"{exam_name}:{MILESTONE}"` (e.g., `SBI Junior Associates:ADMIT_CARD`) in `data/sent_alerts.json`, committed back to Git after each CI run.

*Two known edge cases I'd fix in v2:* First, `sync_to_notion()` currently queries `page_size: 100` without looping on `has_more`/`next_cursor`, so once the General DB passes 100 rows, older hashes won't be fetched and duplicates could occur. Second, locking `"{exam_name}:EXAM_DATE"` permanently would suppress a *revised/postponed* exam date alert unless scoped by month or article-date hash."

### Q4: "How did your pipeline handle enterprise WAFs like Akamai on `sbi.co.in`?"
**Model Answer:**  
"Direct scraping from GitHub Actions' public Azure/Ubuntu IPs failed silently on `sbi.co.in/careers`—Akamai either dropped requests or served empty pages—which caused me to miss an SBI admit card release. Scraping coaching sites like Testbook/Adda247 deeply also risks Cloudflare bans and sub-path misses. Instead of fighting Akamai with paid residential proxies (which violates the $0 constraint), I inverted the ingestion pattern in `aggregators.py`: querying **Google News RSS (`en-IN`, `when:7d`)** for targeted exam phrases. News outlets index admit card drops within minutes, Google RSS doesn't block CI IPs, and I still get structured links to patch Notion and trigger alerts."

### Q5: "Walk me through your link-validation and SSL strategy in `fetch.py`. What are the security trade-offs?"
**Model Answer:**  
"Government PDF links frequently move or 404. Before computing the final SHA-256 hash or writing to Notion, `ContentFetcher.validate_and_resolve_url()` runs an 8-second `HEAD` request with `allow_redirects=True`. Because some servers return `403` or `405` on `HEAD`, it automatically falls back to a streaming `GET`. Any URL returning `status_code >= 400` is stripped (with `apply_link` falling back to `source_url`), and redirects resolve to `resp.url`. On SSL, `.nic.in` portals often have broken certificate chains, so I used `verify=False` (suppressing `InsecureRequestWarning`) and Playwright's `ignore_https_errors=True`. The trade-off is no TLS MITM verification—which is acceptable for read-only public scraping, though I would never use `verify=False` for credentialed endpoints or Notion/Groq/Telegram API calls, which keep strict TLS."

### Q6: "Why separate General Vacancies and Applied Exams into two Notion databases, and why use raw `requests` instead of `notion-client`?"
**Model Answer:**  
"Mixing 150+ noisy general job listings with my 17 personal applications created clutter and slowed down daily tracking, even with a checkbox filter. Splitting them gave the Applied DB (`NOTION_APPLIED_DB_ID`) dedicated operational fields (`Registration No`, `Exam Timeline`, `Notice Board URL`, `Admit Card URL`, `Last Checked`) and lets `track_applied.py` query Notion dynamically so adding a new exam requires zero code changes there. On the transport side, early scaffolding used `notion-client`, but I switched to direct `requests` calls against Notion REST API `v2022-06-28` to eliminate an extra SDK dependency, inspect `available_columns` dynamically before writing optional `Notification PDF` URLs, and debug exact `401`/`404` payloads."

### Q7: "Your GitHub Actions workflow commits `data/sent_alerts.json` back to `main`. What risks does that introduce?"
**Model Answer:**  
"Using Git as a state store keeps the stack $0 without needing Redis or Postgres, and adding `[skip ci]` in the commit message prevents infinite workflow loops. However, it introduces **branch-divergence / race-condition risks**: as I actually hit on `2026-09-21`, if the bot commits `sent_alerts.json` to `origin/main` while I'm editing `aggregators.py` locally, `git push` gets rejected until I run `git pull --rebase origin main`. If two workflow runs overlapped, the second push could also fail or overwrite state. In a multi-user or high-frequency system, I'd move `sent_alerts.json` to an external transactional store like SQLite on object storage, DynamoDB, or Supabase/Postgres."

### Q8: "Why `ThreadPoolExecutor(max_workers=5)` instead of `asyncio` or Celery?"
**Model Answer:**  
"For 25 portals, the bottleneck is network latency, not CPU. `ThreadPoolExecutor` lets me parallelize those I/O waits in ~10 lines of standard library code while keeping `requests.Session` and `playwright.sync_api` synchronous and easy to debug. Celery requires a persistent message broker (Redis/RabbitMQ) and worker process, violating the $0 serverless constraint. `asyncio` would require rewriting the entire fetch/Groq/Notion stack around async clients (`httpx`, `playwright.async_api`) for negligible gain at 25 URLs—though note one subtlety with `ThreadPoolExecutor`: Playwright's sync API creates greenlets tied to a single thread, so keeping Playwright instantiation inside the worker function (`_fetch_browser`) rather than sharing one browser across threads is critical for thread safety."

### Q9: "Why `cron: '17 2 * * *'` instead of `0 2 * * *`, and how reliable is GitHub Actions for scheduled pipelines?"
**Model Answer:**  
"I learned from `2026-09-02` and `2026-09-04` that GitHub Actions cron is best-effort, not a strict SLA. Schedules at `:00` hit global queue saturation, causing 30-to-120+ minute delays or skipped runs, and pushing workflow edits resets GitHub's up-to-24-hour cron indexing window. Moving to an odd minute (`17 2 * * *`, 07:47 AM IST) avoids top-of-the-hour traffic spikes. If a production SLA required exact-minute execution, I'd keep GitHub Actions as the compute runner but trigger `workflow_dispatch` externally via a scheduled HTTP `POST` (e.g., `cron-job.org` with a scoped PAT)."

### Q10: "How would you scale this from ~25 portals to 500 portals without blowing up runtime, rate limits, or Notion?"
**Model Answer:**  
"Scaling 20x exposes four concrete bottlenecks in my current code:
1. **CI Runner Time & Browser Memory:** A single `ThreadPoolExecutor(max_workers=5)` with synchronous Playwright fallbacks already takes ~14 minutes for 25 portals. At 500 portals, I'd switch static fetches to `asyncio` + `httpx` with per-domain semaphores, shard sources across parallel GitHub Actions `matrix` jobs (e.g., 10 shards of 50 portals), and isolate JS-rendered sites into a dedicated Playwright pool blocking images/fonts/media.
2. **Storage & Pagination:** Notion's API enforces rate limits (~3 req/sec) and `sync_to_notion()` currently makes sequential `POST` calls per new record plus an unpaginated `page_size: 100` query. At 500 portals (thousands of jobs), I'd replace Notion as the primary datastore with **PostgreSQL** (using `INSERT ... ON CONFLICT (content_hash) DO NOTHING`), and treat Notion strictly as a curated downstream view synced only with deltas.
3. **Deduplication State:** `data/sent_alerts.json` in Git won't scale to thousands of concurrent writes; moving dedup state into the same Postgres database gives ACID guarantees.
4. **IP Reputation & Observability:** Scraping 500 `.gov`/`.nic.in` endpoints from Azure CI IPs will trigger rate limits (`429`) and WAF blocks (`403`), so I'd add per-domain rate limiters, conditional HTTP (`ETag` / `If-Modified-Since`) to skip unchanged pages, proxy rotation for WAF-heavy targets, and structured JSON logging + per-source health metrics."