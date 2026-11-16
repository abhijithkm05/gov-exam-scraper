# Engineering War Stories: Real-World Scraping & Pipeline Failure Log

Every entry below is extracted directly from production debugging and live portal runs in this repository.

---

### 1. High-Latency & Connection Timeouts on `.nic.in` and PSU Portals
* **The Challenge / Failure Symptom:**
  * `FetchError: Fetch failed for https://kpsc.kar.nic.in/ [status: None]: HTTPSConnectionPool(host='kpsc.kar.nic.in', port=443): Read timed out.`
  * `Karnataka High Court Judiciary` (`https://karnatakajudiciary.kar.nic.in/recruitment.php`) failed with `Page.goto: net::ERR_CONNECTION_TIMED_OUT`.
  * `Airports Authority of India (AAI)` (`https://www.aai.aero/en/careers/recruitment`) failed with `Page.goto: Timeout 60000ms exceeded`.
* **Root Cause:** Indian state NIC servers (`.nic.in`) and PSU portals suffer from severe latency, packet drops, and throttling against standard Python HTTP clients, and can exceed 60s even in a full browser.
* **What Failed First:** Standard `requests.Session.get()` with `REQUEST_TIMEOUT_SECONDS=30` timed out on `kpsc.kar.nic.in`; Playwright alone still hit 60,000ms timeouts on `karnatakajudiciary.kar.nic.in` and `aai.aero`.
* **The Resilient Fix:**
  1. Increased `REQUEST_TIMEOUT_SECONDS=60` and `PLAYWRIGHT_TIMEOUT_SECONDS=60` in `.env` / `models.py`.
  2. Configured `urllib3.util.retry.Retry(total=3, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504])` on `requests.Session` (`fetch.py`) with automatic fallback to headless Playwright Chromium (`--browser` / `_fetch_browser`).
  3. Wrapped `GovExamScraper.scrape_source()` in per-source `try/except` isolation returning `[]` on failure—ensuring dead/slow portals skip gracefully while the remaining 23+ portals still complete.

---

### 2. Akamai WAF Cloud-IP Blocking & Aggregator Path Churn (Silent Missed SBI Admit Card)
* **The Challenge / Failure Symptom:** On `2026-09-24`, SBI Junior Associates announced exam dates and released admit cards, yet the daily pipeline sent **zero alerts** and did not update Notion. Similarly, RRB Section Controller exam dates (`2026-09-11`) were not auto-captured in Notion (`2026-09-15`).
* **Root Cause:**
  1. `sbi.co.in/careers` uses **Akamai WAF**, which blocks GitHub Actions' cloud (Azure/Ubuntu) IPs or serves blank splash pages to `track_applied.py`.
  2. `rrbbnc.gov.in` hides circulars inside dynamic HTML structures that `requests` missed, and `track_applied.py` originally pointed to `rrbbpl.nic.in`.
  3. Coaching aggregators (Testbook, Adda247, Oliveboard) routed banking updates to sub-paths (`/bank-exams/`, `/jobs/`) outside the generic `/news/` and `/exams/` page 1–3 crawlers—while full-site crawling risks Cloudflare IP bans.
* **What Failed First:** Direct scraping of `sbi.co.in/careers` from GitHub Actions runners and fixed-path pagination scraping on `testbook.com/news/` and `adda247.com/exams/`.
* **The Resilient Fix:**
  1. Upgraded `track_applied.py` (`fetch_html_content`) to fall back to headless Playwright Chromium whenever `requests` returns non-200 or sparse HTML (`<= 1000` chars).
  2. Replaced direct coaching-portal HTML crawling in `aggregators.py` with **Google News RSS search** (`https://news.google.com/rss/search?q=<query>+when:7d&hl=en-IN&gl=IN&ceid=IN:en`) parsed via `xml.etree.ElementTree`. Google RSS is immune to Akamai/Cloudflare WAF blocks, indexes breaking admit cards within minutes, and triggers direct Notion `PATCH` updates (`Status`, `Admit Card URL`, `Latest News`).

---

### 3. Groq Free-Tier Rate Limits (`413` / `429`) & Broken Table Context (`0 Records Extracted`)
* **The Challenge / Failure Symptom:**
  * `Error code: 413 - Request too large for model qwen/qwen3.6-27b ... on tokens per minute (TPM): Limit 8000, Requested 39918` (`aranya.gov.in`), `24778` (`kptcl.karnataka.gov.in`), `59641` (`schooleducation.karnataka.gov.in`), `41055` (`sbi.co.in`).
  * `Error code: 429 - Rate limit reached ... Limit 8000, Used 6720, Requested 2492. Please try again in 9.09s.` (`opportunities.rbi.org.in`).
  * After aggressive character/regex pruning, `fetch_active_links.py` and `test_groq_models.py` returned `✅ Total records extracted: 0` (`{"exams": []}`) on `upsc.gov.in` (`96,432` chars HTML) and `freejobalert.com` (`308,686` chars HTML).
* **Root Cause:**
  1. Unstripped navigation menus, headers, and footers bloated pages to 25k–60k tokens (exceeding Groq's 8,000 TPM cap) or consumed the first 6,000–10,000 characters, truncating the actual exam tables below the fold.
  2. Filtering raw text line-by-line via `RELEVANT_KEYWORDS` in `clean_html` split HTML `<table>` rows apart, disconnecting exam names from their deadlines and links so the LLM discarded them.
* **What Failed First:** Character truncation (`[:12000]` / `[:6000]`), linear 429 retry sleeps in `parse.py`, and regex keyword line-filtering in `fetch.py`.
* **The Resilient Fix:** Replaced LLM parsing on the primary scrape path with **deterministic DOM extraction (`_extract_from_dom` in `scraper.py`)**: decomposed `script, style, nav, header, footer, svg, noscript, aside` via BeautifulSoup, parsed `<table>` rows (`<tr>`/`<td>`) intact to keep title, date, apply link, and `.pdf` link together, with a fallback `<a>` keyword scan—extracting **150 active vacancies** in <90 seconds with zero LLM tokens.

---

### 4. Groq Model Deprecations (`404` / `400`) & Strict JSON Validator Crashes (`json_validate_failed`)
* **The Challenge / Failure Symptom:**
  * `NotFoundError: 404 - The model llama-3.1-8b-instant does not exist or you do not have access to it.`
  * `NotFoundError: 404 - The model llama-3.3-70b-versatile does not exist or you do not have access to it.`
  * `BadRequestError: 400 - The model llama3-8b-8192 has been decommissioned.`
  * `BadRequestError: 400 - Failed to validate JSON ... 'code': 'json_validate_failed', 'failed_generation': ''` on `freejobalert.com`, `ksp-recruitment.in`, `cetonline.karnataka.gov.in/kea/`, and `ibps.in`.
* **Root Cause:** Groq decommissioned/restricted model IDs without notice, and Groq's server-side `json_object` validator rejected empty generations (`failed_generation: ''`), missing `max_tokens`, or markdown code fences (` ```json `) on pages with sparse/no notices.
* **What Failed First:** Hardcoding model names in `.env` and tightening system prompts alone without `max_tokens` or a fallback call (`2026-09-01 11:10:00`).
* **The Resilient Fix:** Queried `client.models.list().data` dynamically to discover active account models (`qwen/qwen3.6-27b`); enforced `max_tokens=4096` and explicit empty-state `{"exams": []}` instructions; added a `BadRequestError` fallback retrying without `response_format={"type": "json_object"}` plus regex `extract_json_payload()` stripping `<think>...</think>` blocks and markdown fences.

---

### 5. Dead Circulars (`404`), Redirects, Broken `.nic.in` SSL, & Markdown-Wrapped CLI URLs
* **The Challenge / Failure Symptom:**
  * `FetchError: ... No connection adapters were found for '[https://www.freejobalert.com/karnataka-government-jobs/](https://www.freejobalert.com/karnataka-government-jobs/)'`
  * Scraped notification/PDF links returned `404 Not Found` or `301/302` moved-location responses (`2026-09-02 15:29:21`).
  * Regional `.nic.in` portals threw SSL certificate verification errors.
* **Root Cause:** PowerShell input accidentally wrapped URLs in Markdown `[url](url)` brackets; government sites routinely move PDF circulars without updating HTML links and host misconfigured/unverified TLS chains.
* **What Failed First:** Passing raw `href` strings and CLI arguments directly to `requests` with default SSL verification.
* **The Resilient Fix:**
  1. Added `clean_target_url()` (`fetch.py`) to strip Markdown `[text](url)` wrappers and whitespace.
  2. Added `validate_and_resolve_url()` (`8s` timeout): executes `HEAD` with `allow_redirects=True, verify=False` (falling back to streaming `GET` on `403`/`405`), resolves redirects to `resp.url`, strips `>= 400` dead links (falling back `apply_link` to `source_url`), and recomputes the SHA-256 hash.
  3. Suppressed noisy certificate warnings via `urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)` and enabled `ignore_https_errors=True` in Playwright contexts.

---

### 6. Alert Spam & Cross-Publisher Duplicate Floods
* **The Challenge / Failure Symptom:** General job alerts flooded chat channels; generic keywords (`Assistant`, `Junior`) fired false positives on unrelated exams; and major releases (e.g., SBI Admit Card) triggered 10–20 duplicate notifications across different newspapers.
* **Root Cause:** Step 1 ran with `--notify`; `aggregators.py` matched single words; and per-URL deduplication treated every newspaper's URL for the same event as a distinct notification.
* **What Failed First:** Caching only article URLs in `data/sent_alerts.json`.
* **The Resilient Fix:** Removed `--notify` from Step 1 in `daily-run.yml`; constrained `aggregators.py` to strict exam regex/queries (`EXAM_MONITORS`); classified events into 5 milestones (`ADMIT_CARD`, `EXAM_DATE`, `SYLLABUS_PATTERN`, `ANSWER_KEY`, `RESULT`); locked both `"{exam_name}:{MILESTONE}"` and `urls` in Git-committed `data/sent_alerts.json`; and batched updates into **one consolidated alert per exam per run**.

---

### 7. Unofficial WhatsApp Gateway Blocking (`CallMeBot`)
* **The Challenge / Failure Symptom:** Activating CallMeBot (`I allow callmebot to send me messages`) resulted in undelivered messages (single grey tick) and zero API key response across all three gateway numbers (`+34 684 72 39 62`, `+34 694 23 41 84`, `+34 623 78 64 49`).
* **Root Cause:** Meta frequently blocks or rate-limits public unofficial WhatsApp gateway numbers under high spam/message volume.
* **What Failed First:** Switching between alternate CallMeBot phone numbers.
* **The Resilient Fix:** Abandoned unofficial WhatsApp gateways and standardized on **official Telegram Bot API + Discord Webhooks** (`notify.py`).

---

### 8. Notion API Auth/Permission Errors (`401`/`404`) & Cross-Module Signature Drift
* **The Challenge / Failure Symptom:**
  * `NotionSyncError: [status 401] unauthorized: API token is invalid.`
  * `404 object_not_found: Could not find database with ID: 535459a2-7516-46f4-906c-7c5e03f337ef.`
  * `ImportError: cannot import name 'ExtractionBatch'` / `'ParseError'`
  * `TypeError: dispatch_alerts() got an unexpected keyword argument 'archived_count'`
* **Root Cause:** Malformed/duplicate lines in `.env`; Notion databases defaulting to private until explicitly connected to the `Gov Exam Tracker` integration; and iterative PowerShell file overwrites dropping symbols or changing function signatures between `cli.py` and `notify.py`.
* **What Failed First:** Re-running `cli.py` and `seed_applied_exams.py` without schema/signature verification.
* **The Resilient Fix:** Cleaned `.env`, invited the Notion integration via `•••` $\rightarrow$ `Connections`, restored missing classes (`ExtractionBatch`, `ParseError`), added `**kwargs` and optional `archived_count=0` to `dispatch_alerts()`, and checked `available_columns` dynamically before writing optional `Notification PDF` properties to Notion.

---

### 9. CI/CD, Git & Automated Code-Patching Regressions
* **The Challenge / Failure Symptom:**
  * `GH013: Push cannot contain secrets (Groq API Key in .env:1)` blocked `git push`.
  * Legacy `daily_tracker.yml` failed with `pytest` Exit Code 5 (`NO_TESTS_COLLECTED`) and Git Exit Code 128 (stale `gov-exam-scraper` nested submodule reference).
  * Clicking `Re-run jobs` on GitHub Actions Run #1 kept failing with `[Errno 2] No such file or directory: track_applied.py` even after pushing the file.
  * Automated regex patching of `scraper.py` introduced `SyntaxError: ),,` on line 52/62 and `AttributeError: 'dict' object has no attribute 'is_active'` on line 222 (`2026-09-18`).
  * PowerShell multi-line paste truncation silently dropped sections of `README.md` and wrapped lines into `SyntaxError` in `final_repair.py`.
* **Root Cause:** Missing `.gitignore`; re-running frozen commit snapshots (`c1c4c0e`) in GitHub Actions; PowerShell clipboard buffer limits on large/emoji pastes; and unvalidated regex mutations injecting raw `dict` literals into a `ScraperSource` list.
* **What Failed First:** Regex-patching a corrupted `scraper.py` without AST validation and clicking `Re-run jobs` instead of triggering a fresh workflow run.
* **The Resilient Fix:** Created `.gitignore` + `git reset HEAD~1` + `git rm --cached .env`; removed nested `gov-exam-scraper` directory and consolidated workflows into `daily-run.yml` (`submodules: false`); triggered fresh `workflow_dispatch` runs on `main`; edited large Markdown files in VS Code; reverted `scraper.py` via Git, hardened `scrape_all()` with `getattr(s, "is_active", False)`, and gated automated script edits with `ast.parse()` / `py_compile`.