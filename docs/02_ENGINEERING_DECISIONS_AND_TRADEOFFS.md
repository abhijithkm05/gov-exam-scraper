# Architecture Decision Records (ADRs): `gov-exam-scraper`

Below are all technical decisions and architectural trade-offs debated, tested, and pivoted across the build of `gov-exam-scraper`, formatted for senior engineering interview defense and production maintenance.

---

### ADR-001: Serverless Execution & Odd-Minute Cron Scheduling (`GitHub Actions`)
* **Decision & Context:** The system required zero recurring cost ($0 forever) and unattended daily execution without relying on a local Windows PC (`D:\Github\Govt_Exam_Scrapper`). After deploying `.github/workflows/daily-run.yml` on `0 2 * * *` (02:00 UTC / 07:30 AM IST), scheduled runs were delayed or silently skipped (`2026-09-02`, `2026-09-04`) due to GitHub's global top-of-the-hour runner queue saturation and up-to-24-hour scheduler indexing delays.
* **What We Chose & Why:** **GitHub Actions (`ubuntu-latest`, Python `3.11`)** triggered by an odd-minute cron **`17 2 * * *`** (02:17 UTC / 07:47 AM IST) plus **`workflow_dispatch`** for manual runs, with `permissions: contents: write` to commit alert state back to the repo. Offsetting the minute from `:00` to `:17` avoids top-of-the-hour queue contention at $0 infrastructure cost.
* **Rejected Alternatives (Why Not That):**
  * *Local PowerShell execution:* Requires the developer's machine to stay powered on daily.
  * *Top-of-the-hour cron (`0 2 * * *`):* Consistently experiences 20–60+ minute queue delays or dropped cycles under global GitHub load.
  * *Self-hosted Docker container (`Dockerfile` + Docker Hub):* Although a multi-stage `Dockerfile` was scaffolded initially, running directly on `ubuntu-latest` with `playwright install --with-deps chromium` eliminated container registry/hosting management.
  * *External HTTP cron (`cron-job.org` calling GitHub's `workflow_dispatch` API with a PAT):* Documented as an escalation fallback for strict SLA punctuality, but deferred in favor of native GitHub cron simplicity.

---

### ADR-002: Concurrency Model — Synchronous `ThreadPoolExecutor` vs. Async / Distributed Queues
* **Decision & Context:** Scraping 25+ government portals sequentially over high-latency `.nic.in` networks takes too long, but adding async frameworks or message brokers increases complexity and infrastructure overhead inside a single ephemeral CI runner.
* **What We Chose & Why:** **Synchronous multi-threading via `concurrent.futures.ThreadPoolExecutor(max_workers=5)`** in `GovExamScraper.scrape_all()`, paired with `requests.Session` and `playwright.sync_api`. Thread pools handle I/O-bound HTTP/browser waits cleanly within a single process and keep error isolation per-future simple.
* **Rejected Alternatives (Why Not That):**
  * *`asyncio` / `aiohttp`:* Unnecessary concurrency complexity for ~25 URLs and incompatible with the synchronous `requests` / `groq` SDK usage across the rest of the package.
  * *Distributed task queues (Celery + Redis/RabbitMQ):* Requires persistent broker/worker hosting, violating the $0 serverless constraint.

---

### ADR-003: Dual-Tier Fetching (`requests` + Playwright Fallback) & Relaxed TLS (`verify=False`)
* **Decision & Context:** Static portals (`upsc.gov.in`, `freejobalert.com`, `kpsc.kar.nic.in`) need fast, low-memory HTTP fetches, whereas JavaScript SPAs (`ssc.gov.in`, `sbi.co.in`, `aai.aero`) and dynamic boards (`rrbbnc.gov.in`) render empty HTML shells to plain HTTP clients. Furthermore, regional `.nic.in` portals frequently fail TLS verification or time out under strict defaults.
* **What We Chose & Why:** **Dual-tier fetching** in `ContentFetcher` (`fetch.py`) and `fetch_html_content()` (`track_applied.py`):
  1. Primary fetch via `requests.Session` with desktop Chrome `User-Agent`, `Accept-Language: en-US,en;q=0.9,kn;q=0.8` (Kannada support), `urllib3.util.retry.Retry` (`total=3`, `backoff_factor=1.0` on `429, 500, 502, 503, 504`), 60s timeout, and `verify=False` (`InsecureRequestWarning` suppressed).
  2. Automatic fallback to **headless Playwright Chromium** (`ignore_https_errors=True`, `wait_until="domcontentloaded"`, 2s settle) when `use_playwright=True`, `requests` throws/fails, or returned HTML is sparse (`<= 1000` chars).
* **Rejected Alternatives (Why Not That):**
  * *`requests`-only:* Fails completely on React/JS-hydrated SPAs (`ssc.gov.in`, `sbi.co.in`) and dynamic tables on `rrbbnc.gov.in`.
  * *Playwright-for-all-sources:* Excessive CPU, memory, and runtime overhead across 25+ URLs inside a CI runner.
  * *Strict TLS verification (`verify=True`):* Causes fatal SSL handshake errors on misconfigured state government `.nic.in` certificates. *(Trade-off: acceptable for read-only public scraping, not for authenticated financial transactions.)*

---

### ADR-004: Extraction Engine Pivot — Deterministic BeautifulSoup DOM Parsing vs. Groq LLM JSON Mode
* **Decision & Context:** The original design relied on **Groq Cloud's free tier** (`llama-3.1-8b-instant` JSON mode) to parse messy HTML without brittle CSS selectors. In production testing (`2026-09-01` to `2026-09-02`), LLM-first extraction failed across four dimensions:
  1. *Model availability churn:* `llama-3.1-8b-instant` and `llama-3.3-70b-versatile` returned `404 model_not_found`, and `llama3-8b-8192` returned `400 model_decommissioned`, leaving `qwen/qwen3.6-27b` as the active fallback.
  2. *JSON validation crashes:* Groq's `response_format={"type": "json_object"}` threw `400 json_validate_failed` on empty responses or markdown fences.
  3. *Free-tier TPM exhaustion:* `qwen/qwen3.6-27b` enforces an **8,000 Tokens-Per-Minute (TPM)** cap; large portals (`schooleducation.karnataka.gov.in`: 59,641 tokens; `sbi.co.in`: 41,055 tokens; `aranya.gov.in`: 39,918 tokens; `kptcl.karnataka.gov.in`: 24,778 tokens) triggered immediate `413` and `429` rate-limit errors.
  4. *Context destruction:* Stripping HTML via `RELEVANT_KEYWORDS` line-filtering (`clean_html`) tore HTML `<table>` rows apart—separating exam titles from their deadlines and links—while menu/header bloat consumed the first 6,000–10,000 characters, causing Groq to return `{"exams": []}` (0 records).
* **What We Chose & Why:** Replaced LLM extraction on the primary scrape path with **deterministic DOM table & anchor parsing (`_extract_from_dom` in `scraper.py`)** using **BeautifulSoup (`html.parser`)**. It strips `script, style, nav, header, footer, svg, noscript, aside`, parses structured `<table>` rows (`<tr>`/`<td>`) for recruitment keywords and dates, resolves `apply_link` and `.pdf` `pdf_link` via `urljoin`, and falls back to prominent `<a>` tag scanning. This extracted **150 active vacancies** across 25 portals in <90 seconds with **0 LLM tokens** and zero rate limits. (`GroqParser` remains in `parse.py` for ad-hoc/unstructured use.)
* **Rejected Alternatives (Why Not That):**
  * *Pure Groq LLM extraction on cleaned HTML:* Blocked by 8,000 TPM limits (`413`/`429`), header truncation, and model deprecation churn.
  * *Regex line-condensation before LLM:* Broke tabular column-to-row alignment, yielding 0 extracted exams on `upsc.gov.in`.

---

### ADR-005: Pre-Flight Link Verification & Redirect Resolution vs. Raw URLs / PDF Binary Parsing
* **Decision & Context:** Scraped government links and test URLs frequently returned `404 Not Found` or `301/302` redirects (`2026-09-02 15:29:21`), sending broken buttons to Notion and chat alerts.
* **What We Chose & Why:** Implemented **`ContentFetcher.validate_and_resolve_url()`** (`8s` timeout): executes HTTP `HEAD` with `allow_redirects=True` (falling back to streaming `GET` on `403`/`405` when servers reject `HEAD`). Updates `pdf_link` and `apply_link` to the resolved final `resp.url`, discards dead `>= 400` links (falling back `apply_link` to `source_url`), and recomputes the SHA-256 hash. PDFs are tracked and delivered as verified direct download URLs.
* **Rejected Alternatives (Why Not That):**
  * *Storing/alerting raw `href` values:* Propagates 404 dead links and unfollowed redirects to end users.
  * *Downloading and parsing/OCR'ing PDF binaries (e.g., PyMuPDF/Tesseract):* Not implemented; adds runtime, storage, and CPU overhead in CI when direct verified PDF circular links solve user access.

---

### ADR-006: Storage & State Persistence — Dual Notion Databases + Git-Backed JSON vs. Single DB / SQL
* **Decision & Context:** Ephemeral GitHub Actions runners wipe local state (and in-memory `TTLCache`) after every run. Additionally, mixing 150+ noisy general job listings with personal exam commitments (application IDs, fees, exam timelines, admit card links) cluttered tracking (`2026-09-02 16:17:58`).
* **What We Chose & Why:**
  1. **Dual Notion Databases** accessed via direct REST API (`v2022-06-28` over `requests` instead of `notion-client` for explicit control over `POST`/`PATCH` payloads and conditional `Notification PDF` column checks):
     * **General Vacancies DB (`NOTION_DATABASE_ID`):** Stores broad discovery records deduplicated by **SHA-256 `Content Hash`** and auto-archives expired rows (`Last Date < today` $\rightarrow$ `Status = CLOSED`).
     * **Applied Exams DB (`NOTION_APPLIED_DB_ID`):** Dedicated tracker for personal applications (17 exams), queried dynamically at runtime by `track_applied.py` so adding a new exam requires zero code changes there.
  2. **Git-Committed JSON State (`data/sent_alerts.json`):** Committed and pushed back to `main` by `github-actions[bot]` (`[skip ci]`) at Step 4 of `daily-run.yml` to persist sent URLs and milestone keys across stateless CI runs.
* **Rejected Alternatives (Why Not That):**
  * *Single Notion database with an `Applied` checkbox:* Rejected to keep personal exam timelines and registration numbers isolated from 150+ general job rows.
  * *External SQL/NoSQL database (Postgres, Redis, MongoDB):* Introduces hosting/free-tier expiry risks and lacks Notion's built-in mobile app, Kanban, and calendar UI.
  * *In-memory `TTLCache` alone:* Cannot persist deduplication state across ephemeral daily GitHub Actions containers.

---

### ADR-007: Applied-Exam Discovery Pivot — Google News RSS (`en-IN`) vs. Direct WAF Scraping & Deep Crawling
* **Decision & Context:** On `2026-09-24`, SBI released its Junior Associates exam date and admit card without triggering any alert or Notion update. Diagnosis revealed that `sbi.co.in/careers` sits behind **Akamai WAF** (blocking GitHub Actions' Azure/Ubuntu cloud IPs with empty pages/403s), while coaching aggregators (Testbook, Adda247, Oliveboard) moved banking posts onto sub-paths (`/bank-exams/`, `/jobs/`) missed by generic `/news/` and `/exams/` page 1–3 crawlers. Meanwhile, crawling all historical pages of aggregators was explicitly rejected.
* **What We Chose & Why:** Replaced direct HTML scraping of Testbook/Adda247/Oliveboard in `aggregators.py` with **Google News RSS queries** (`https://news.google.com/rss/search?q=<query>+when:7d&hl=en-IN&gl=IN&ceid=IN:en`) parsed via stdlib `xml.etree.ElementTree`, paired with automatic Notion patching (`Status`, `Admit Card URL`, `Latest News`). Kept `track_applied.py` running in parallel for unblocked official boards (KPSC, KEA, RRB, UPSC).
* **Rejected Alternatives (Why Not That):**
  * *Direct scraping of banking/WAF-protected portals from CI IPs:* Blocked by Akamai/Cloudflare WAFs.
  * *Infinite-scroll / full-archive crawling of Testbook, Adda247, and Oliveboard:* Triggers Cloudflare IP bans, exceeds GitHub Actions' 6-hour job limit, and floods Notion with historical/promotional content.

---

### ADR-008: Alerting Channels — Discord Webhooks + Telegram Bot API vs. WhatsApp Gateways
* **Decision & Context:** Needed reliable $0 mobile push notifications for breaking admit cards and exam schedules. Tried adding WhatsApp support (`Option B`, `2026-09-02 12:30:51`) via the free unofficial **CallMeBot** gateway.
* **What We Chose & Why:** **Telegram Bot API (`sendMessage`) + Discord Webhooks** (`notify.py`, `track_applied.py`, `aggregators.py`). Both use official, stable HTTP APIs with zero hosting cost and rich Markdown/link formatting.
* **Rejected Alternatives (Why Not That):**
  * *WhatsApp via CallMeBot (`+34 684 72 39 62`, `+34 694 23 41 84`, `+34 623 78 64 49`):* Abandoned after Meta blocked/rate-limited the public gateway numbers and activation API keys failed to arrive (`2026-09-02 14:54:57`).
  * *Official Meta WhatsApp Cloud API / Twilio:* Deferred due to business registration/sandbox friction when Telegram and Discord already worked reliably.

---

### ADR-009: Anti-Spam Noise Control — Silent General Sync + Milestone Deduplication vs. Per-Article Alerts
* **Decision & Context:** Initial alerting suffered from three spam vectors (`2026-09-15`, `2026-09-24`):
  1. Step 1 (`gov-exam-scraper scrape`) broadcasted all 150+ general job openings.
  2. Single-word matching (`Assistant`, `Junior`, `India`) triggered false positives on unrelated exams.
  3. Per-URL deduplication fired 10–20 duplicate alerts whenever multiple newspapers covered the same SBI/RRB admit card release under different URLs.
* **What We Chose & Why:**
  1. **Silent Step 1:** Removed `--notify` from Step 1 in `daily-run.yml`; general vacancies sync silently to Notion.
  2. **Strict Exam Regex (`EXAM_MONITORS`):** Matches only the user's 17 applied exams across full-lifecycle topics (dates, syllabus, notes, papers, answer keys, cutoffs, results).
  3. **Milestone-Based Consolidation (`aggregators.py`):** Maps headlines to 5 discrete milestones (`ADMIT_CARD`, `EXAM_DATE`, `SYLLABUS_PATTERN`, `ANSWER_KEY`, `RESULT`), caches `"{exam_name}:{MILESTONE}"` in `data/sent_alerts.json`, and sends **one consolidated notification per exam per run**.
* **Rejected Alternatives (Why Not That):**
  * *`--notify` on general vacancy scraping:* Unusable signal-to-noise ratio.
  * *Per-URL-only deduplication:* Fails against multi-outlet news syndication of the exact same exam event.
  * *Broad single-word keyword matching:* High false-positive rate across unrelated Indian government exams.

---

### ADR-010: Credential Hygiene & Defensive Input/Source Sanitization
* **Decision & Context:** Three operational incidents shaped input and secret handling:
  1. GitHub Push Protection (`GH013`) blocked pushing `.env` containing `GROQ_API_KEY` (`2026-09-01 12:24:47`).
  2. Terminal copy-pasting wrapped URLs in Markdown syntax (`[url](url)`), crashing `requests` with `No connection adapters were found` (`2026-09-01 11:09:02`).
  3. Automated script injections added raw Python `dict` literals and `),,` syntax errors into `DEFAULT_SOURCES` in `scraper.py`, crashing CI with `SyntaxError` and `AttributeError: 'dict' object has no attribute 'is_active'` (`2026-09-18`).
* **What We Chose & Why:**
  * Excluded `.env` via `.gitignore`, removed `.env` from Git index, injected secrets strictly via GitHub Actions Secrets, and omitted portal login passwords from Git commits and Notion payloads.
  * Added `clean_target_url()` in `fetch.py` to strip stray Markdown brackets/whitespace, and Pydantic `SecretString` / `parse_flexible_date` validators in `models.py`.
  * Hardened `scrape_all()` with `getattr(s, "is_active", False)`, reverted `scraper.py` via `git checkout $firstCommit`, and gated script updates with `ast.parse()` / `py_compile` verification before committing.
* **Rejected Alternatives (Why Not That):**
  * *Committing `.env` or storing application passwords in repo scripts:* Direct credential exposure risk (`GH013` violation).
  * *Unvalidated regex-in-place code patching without AST/compile gates:* Repeatedly introduced breaking `SyntaxError` and `AttributeError` regressions into `main`.