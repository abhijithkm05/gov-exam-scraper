# Operational Runbook: `gov-exam-scraper`

**Repo:** `https://github.com/abhijithkm05/gov-exam-scraper` (`D:\Github\Govt_Exam_Scrapper`)  
**Automation Schedule:** Daily at `02:17 UTC` (**07:47 AM IST**) via `.github/workflows/daily-run.yml`  
**Core Pipelines:**
1. **Engine 1 (General Discovery):** `gov-exam-scraper scrape --sync-notion --archive-expired` (`src/gov_exam_scraper/scraper.py`)
2. **Engine 2A (Official Board Watcher):** `python src/gov_exam_scraper/track_applied.py`
3. **Engine 2B (RSS Milestone Watcher):** `python src/gov_exam_scraper/aggregators.py` + `data/sent_alerts.json`

---

## 1. How to Add a New Exam Portal or Applied Exam

Choose the checklist matching what you want to track:

### Workflow A: Adding a New General Discovery Portal (Engine 1)
Use this to add a website to the 25-portal background Notion feed (`NOTION_DATABASE_ID`).

1. **Activate your local environment:**
   ```powershell
   Set-Location D:\Github\Govt_Exam_Scrapper
   .venv\Scripts\Activate.ps1
   $env:PYTHONPATH = "src"
   ```
2. **Test the URL before editing code:**
   ```powershell
   # Standard HTTP test
   gov-exam-scraper test-url "https://example.gov.in/recruitments" --sector STATE_PSC

   # Use --browser if the page is JS-rendered (SPA) or times out on requests
   gov-exam-scraper test-url "https://example.gov.in/recruitments" --sector BANKING --browser
   ```
3. **Add a `ScraperSource` object to `DEFAULT_SOURCES` in `src/gov_exam_scraper/scraper.py`:**
   * **CRITICAL RULE:** Always add a typed `ScraperSource(...)` instance—**never** a raw Python `dict` (`{...}`), and verify there are no trailing double commas (`),,`).
   * Valid `Sector` enums (`models.py`): `UPSC`, `SSC`, `STATE_PSC`, `BANKING`, `RAILWAY`, `DEFENCE`, `POLICE`, `TEACHING`, `PSU`, `ENGINEERING`, `OTHER`.
   ```python
   ScraperSource(
       name="Portal Display Name",
       url="https://example.gov.in/recruitments",
       sector_hint=Sector.STATE_PSC,
       use_playwright=False,  # Set True for SPAs / JS-rendered tables
   ),
   ```
4. **Verify syntax, imports, and portal registration locally:**
   ```powershell
   python -m py_compile src/gov_exam_scraper/scraper.py
   gov-exam-scraper sources
   ```
5. **Rebase and push (handles remote `sent_alerts.json` bot commits):**
   ```powershell
   git add src/gov_exam_scraper/scraper.py
   git commit -m "feat: add <portal-name> to DEFAULT_SOURCES"
   git pull --rebase origin main
   git push origin main
   ```

---

### Workflow B: Adding a Newly Applied Personal Exam (Engine 2)
Use this whenever you submit a new exam application and want Telegram/Discord alerts + Notion lifecycle tracking.

1. **Add a row to your Notion Applied Exams DB (`NOTION_APPLIED_DB_ID` = `535459a2751646f4906c7c5e03f337ef`):**
   * Populate: `Exam Name`, `Authority`, `Notification No`, `Registration No`, `Status` (e.g., `Exam Scheduled` or `Date TBD` — note `track_applied.py` skips only `Status == "Completed"`), `Exam Date`, `Exam Timeline`, `Latest News`.
   * **Notice Board URL:** Use the authority's *public announcements/circulars* URL (e.g., `https://upsc.gov.in/examinations/active-examinations`), **not** an authenticated login portal (like `upsconline.nic.in/ora/`).
   * **Security:** Never store portal login passwords in Git scripts or Notion payloads.
   * *Note:* `track_applied.py` queries Notion dynamically, so **no code change is needed in `track_applied.py`** once the row exists in Notion.
2. **Add a monitor query to `EXAM_MONITORS` in `src/gov_exam_scraper/aggregators.py`:**
   ```python
   {
       "name": "Exact Exam Name (Advt No)",
       "query": '("Exact Exam Phrase" OR "Advt Code") (exam date OR admit card OR syllabus OR answer key OR result)',
   },
   ```
3. **Validate syntax, test RSS matching, and push:**
   ```powershell
   python -m py_compile src/gov_exam_scraper/aggregators.py
   python src/gov_exam_scraper/aggregators.py
   git add src/gov_exam_scraper/aggregators.py data/sent_alerts.json
   git commit -m "feat: track <exam-name> in Notion and RSS milestone watcher"
   git pull --rebase origin main
   git push origin main
   ```

---

## 2. Common Failure Modes & How to Debug Them

| Failure Symptom | Likely Root Cause | Files to Inspect | Diagnostic & Fix |
| :--- | :--- | :--- | :--- |
| **`SyntaxError: ),,` or `AttributeError: 'dict' object has no attribute 'is_active'`** | Raw `dict` or duplicate comma injected into `DEFAULT_SOURCES` | `src/gov_exam_scraper/scraper.py` | Run `python -m py_compile src/gov_exam_scraper/scraper.py`. Convert dicts to `ScraperSource(...)`; verify `getattr(s, "is_active", False)` in `scrape_all()`. |
| **`ModuleNotFoundError: No module named 'gov_exam_scraper'` or `.venv` error** | Running from `C:\Users\abhik` or outside `.venv` | Root PWD / `.venv` | `Set-Location D:\Github\Govt_Exam_Scrapper`, run `.venv\Scripts\Activate.ps1`, set `$env:PYTHONPATH = "src"` (or `pip install -e .`). |
| **`Read timed out` / `ERR_CONNECTION_TIMED_OUT` on `.nic.in` portals** | Government server throttling or slow response (>60s) | `src/gov_exam_scraper/fetch.py`, `.env` | Test with `--browser`. If still timing out, portal is temporarily down (`scrape_source()` isolates and skips it automatically). |
| **Portal updated on website, but `0` alerts sent & Notion unchanged** | 1) Portal sits behind Akamai/Cloudflare WAF blocking Azure CI IPs (`sbi.co.in`), OR<br>2) Portal uses JS/nested iframes (`rrbbnc.gov.in`), OR<br>3) Site changed `<table>` HTML to `<div>` cards | `src/gov_exam_scraper/track_applied.py`, `aggregators.py`, `scraper.py` | Check `Notice Board URL` in Notion. Run `python src/gov_exam_scraper/track_applied.py` and `aggregators.py` locally. If blocked by WAF, rely on/tune the `EXAM_MONITORS` Google News RSS query. If `<table>` changed to `<div>`, inspect HTML with `BeautifulSoup` and update `_extract_from_dom()`. |
| **Missing PDF link in Notion / Alerts** | Link returned `404` or timed out during `validate_and_resolve_url()`, OR `Notification PDF` column missing in Notion | `src/gov_exam_scraper/fetch.py`, `scraper.py` | Test URL manually in browser. Confirm `Notification PDF` (`URL` type) exists in the General Vacancies Notion DB (`sync_to_notion` checks `available_columns`). |
| **Notion `401 Unauthorized` or `404 object_not_found`** | Malformed/quoted token in `.env`/GitHub Secrets, or DB not shared with integration | `.env`, GitHub Secrets, Notion UI | Strip quotes/spaces from `NOTION_API_KEY`. In Notion, open DB $\rightarrow$ `•••` $\rightarrow$ **Connections** $\rightarrow$ connect **Gov Exam Tracker**. |
| **`git push` rejected (`fetch first`)** | `github-actions[bot]` committed `data/sent_alerts.json` to `origin/main` | `data/sent_alerts.json`, `.github/workflows/daily-run.yml` | Run `git pull --rebase origin main` then `git push origin main`. |
| **`GH013: Push cannot contain secrets`** | `.env` accidentally staged/committed | `.gitignore` | Ensure `.env` is in `.gitignore`; run `git reset HEAD~1` and `git rm --cached .env`. |
| **GitHub Actions skipped 07:47 AM IST run, or `Re-run jobs` repeats old error** | GitHub cron queue jitter/24h re-index delay; `Re-run jobs` re-executes the old frozen commit SHA | `.github/workflows/daily-run.yml` | Never click `Re-run jobs` after pushing a fix—click **Actions** $\rightarrow$ **Daily Exam Tracker & Notion Sync** $\rightarrow$ **Run workflow** on `main`. |
| **Revised/postponed exam date alert did not fire** | Milestone key `"{exam_name}:EXAM_DATE"` already locked in cache | `data/sent_alerts.json`, `aggregators.py` | Remove that specific `"{exam_name}:EXAM_DATE"` entry from `data/sent_alerts.json` and push, so the new announcement can fire. |
| **`GroqParser` `404`/`400`/`413`/`429` errors** | Model deprecated (`llama3-8b-8192`) or prompt >8,000 TPM (`qwen/qwen3.6-27b`) | `src/gov_exam_scraper/parse.py`, `.env` | Query active models via `client.models.list().data`; update `GROQ_MODEL`. Note primary `scraper.py` uses `_extract_from_dom()`, bypassing Groq. |

---

## 3. Current Status, Known Debt & Future Upgrades

### What Works Today
* **Automated Daily Execution:** `.github/workflows/daily-run.yml` runs on `ubuntu-latest` (Python 3.11) at `17 2 * * *` (07:47 AM IST) and persists `data/sent_alerts.json` via `[skip ci]`.
* **General Vacancies Pipeline:** `GovExamScraper` (`scraper.py`) scrapes 25 portals concurrently (`ThreadPoolExecutor(max_workers=5)`), extracts active listings via `_extract_from_dom()`, validates/resolves links via `validate_and_resolve_url()`, deduplicates via SHA-256 `Content Hash`, syncs to Notion, and auto-archives expired listings (`Last Date < today` $\rightarrow$ `CLOSED`).
* **Applied Exams Surveillance:** `track_applied.py` + `aggregators.py` monitor **17 applied exams** across official boards and Google News RSS (`en-IN`), consolidating alerts into **1 message per exam** on Telegram and Discord and patching Notion status/links.

### Fragile Selectors, Bugs & Technical Debt to Watch
1. **Hardcoded Year Filter (`"2026"`) in `scraper.py` (`_extract_from_dom`):**  
   The table row filter checks `["apply", "recruitment", ..., "2026", "pdf"]`. Once 2027 notifications appear without those other words, `"2026"` should be replaced with a dynamic year check (`str(date.today().year)` and `str(date.today().year + 1)`).
2. **Prefix Collision in `aggregators.py` (`update_notion`):**  
   `update_notion()` currently matches Notion rows using `first_key = exam_name.split()[0].lower()`. Because you now have **5 RRB exams** (`CEN 03`, `04`, `06`, `07`, `08`, `09`) all starting with `"RRB"`, `"rrb"` can match the wrong RRB row in Notion. Update this matcher to check the `Notification No` (`CEN 08/2026`, `CEN 06/2026`) or full normalized `exam_name`.
3. **Unpaginated Notion Queries (`page_size: 100`):**  
   In `scraper.py` (`sync_to_notion`), Notion queries fetch only the first 100 rows without looping on `has_more` / `next_cursor`. Once the General Vacancies DB exceeds 100 pages, older `Content Hash` keys won't be loaded, risking duplicate page creation.
4. **Verify `scraper.py` After the `2026-09-18` `git checkout $firstCommit`:**  
   Confirm `src/gov_exam_scraper/scraper.py` on `main` still contains `_extract_from_dom()` and all 25 `DEFAULT_SOURCES` (and wasn't reverted to the initial 5-source commit).
5. **Single-Row Header Assumption in `_extract_from_dom`:**  
   `for row in rows[1:]:` assumes every `<table>` has a header row at index 0, and `cols[0]`/`cols[1]` assumes exam titles sit in the first two columns.
6. **Test Suite Drift:**  
   The `tests/` directory (`test_models.py`, `test_fetch.py`, `test_parse.py`) reflects the initial package layout and is not currently run in `daily-run.yml`.

### High-Value Future Upgrades (Prioritized)
1. **Fix Notion Pagination + Multi-RRB Row Matching + Dynamic Year Filter** *(Highest ROI, ~30 min)*: Restore `while has_more:` cursor pagination in `sync_to_notion()`, match Notion rows by `Notification No` / full title in `aggregators.py`, and replace `"2026"` with dynamic current/next year.
2. **Per-Source Health Checks & Anomaly Alerts:** Track extracted record counts per portal per run; send a Telegram/Discord warning if a portal drops to `0` records for 3 consecutive runs (early detection for DOM redesigns or silent WAF blocks) instead of silently returning `[]`.
3. **Strict Schema & Regression CI Gate:** Add a lightweight CI step running `pytest` + `ast.parse()` / `ruff check` on PRs/pushes to prevent another `SyntaxError` (`),,`) or `dict`-in-`DEFAULT_SOURCES` outage.
4. **Phase-Scoped Milestone Keys (`sent_alerts.json`):** Change keys from `"{exam_name}:{MILESTONE}"` to include year-month or phase (e.g., `"{exam_name}:{MILESTONE}:{YYYY-MM}"`) so Prelims vs. Mains admit cards or revised exam dates aren't suppressed.
5. **PDF Merit-List Roll Number Matcher (`pypdf`) & Google Calendar Sync:** Download merit-list PDFs (India Post GDS, KFD 1:20 shortlist) to search for your Registration/Roll Number automatically, and sync confirmed `Exam Date` values from Notion to Google Calendar / `.ics` alerts.
6. **External Cron Trigger (`cron-job.org` $\rightarrow$ `workflow_dispatch`):** Eliminate GitHub Actions scheduled queue jitter if strict 07:47 AM execution becomes critical.