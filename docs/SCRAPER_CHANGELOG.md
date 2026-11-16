# Scraper & Parser Changelog (`gov-exam-scraper`)

A chronological log of government portal DOM changes, PDF/redirect quirks, WAF blocks, and parser patches. Doubles as an operational maintenance trail and a bank of concrete debugging stories for engineering interviews.

---

## Entry Template (Copy for Future Fixes)

    ## YYYY-MM-DD — <Portal Name> (`<domain>`)
    - **Affected Component:** `scraper.py` / `track_applied.py` / `aggregators.py` / `fetch.py`
    - **Symptom:** <What broke — e.g., 0 records extracted, KeyError, timeout, 403 WAF block>
    - **What Changed in DOM / PDF / Network:** <Exact HTML/DOM/URL shift — e.g., `<table>` replaced by nested `<div>` cards, PDF moved behind JS onclick handler, column order shifted>
    - **Patch Applied:** <Exact selector, regex, fallback, or parser change made>
    - **Interview Takeaway:** <1-sentence lesson on resilience, observability, or trade-offs>

---

## 2026-11-16 13:29 IST — Session & Workspace Sync (`gov-exam-scraper`)
- **Affected Component:** `Notion Applied DB`, `GitHub main`, `src/gov_exam_scraper/`
- **Symptom:** Incremental delta recorded since `2026-11-16T07:56:59.432801+00:00`.
- **What Changed in DOM / PDF / Network:** Workspace/chat milestone captured.
- **Patch Applied:** Synced Notion state, Git commits, and local session actions automatically.
- **Interview Takeaway:** Stateful watermark-based documentation captures incremental changes across code, databases, and workflows in a single click.

---
## 2026-11-16 — Changelog Initialized & Docs Audited (`docs/`)
- **Affected Component:** `docs/SCRAPER_CHANGELOG.md` (read-only audit against `src/gov_exam_scraper/`)
- **Symptom:** Parser and portal fixes were scattered across commit messages and post-mortems rather than tracked in a single chronological log.
- **What Changed in DOM / PDF / Network:** N/A — baseline audit verified all 5 architecture and runbook docs match the live 25-portal `_extract_from_dom()` scraper, Playwright fallback in `track_applied.py`, and 17-exam Google News RSS milestone engine (`aggregators.py`).
- **Patch Applied:** Created `docs/SCRAPER_CHANGELOG.md` with a standardized entry template and backfilled the major parser and fetching shifts from production.
- **Interview Takeaway:** Maintaining a lightweight failure-and-patch log turns routine scraper maintenance into ready-made, concrete debugging stories for system design and data engineering interviews.

---

## 2026-09-24 — SBI Careers & Banking Aggregators (`sbi.co.in`, `testbook.com`, `adda247.com`, `oliveboard.in`)
- **Affected Component:** `src/gov_exam_scraper/aggregators.py`, `src/gov_exam_scraper/track_applied.py`
- **Symptom:** SBI Junior Associates exam date and admit card released without triggering Telegram/Discord alerts or updating Notion; earlier runs also suffered multi-outlet duplicate alert floods.
- **What Changed in DOM / PDF / Network:**
  - `sbi.co.in/web/careers/current-openings` enforced Akamai WAF rules that served blank/403 responses to GitHub Actions' Ubuntu/Azure cloud runner IPs.
  - Coaching portals routed banking updates under `/bank-exams/` and `/jobs/` sub-paths instead of the generic `/news/` and `/exams/` pagination routes.
- **Patch Applied:**
  - Added a headless Playwright fallback in `track_applied.py` (`fetch_html_content`) whenever `requests` returns non-200 or sparse HTML (`<= 1000` chars).
  - Replaced direct coaching-site HTML crawling in `aggregators.py` with Google News India RSS queries (`news.google.com/rss/search`, `when:7d`, parsed via `xml.etree.ElementTree`), 5-milestone deduplication (`ADMIT_CARD`, `EXAM_DATE`, `SYLLABUS_PATTERN`, `ANSWER_KEY`, `RESULT`) in `data/sent_alerts.json`, and automatic Notion `PATCH` updates.
- **Interview Takeaway:** When enterprise WAFs block cloud runner IPs, inverting ingestion toward structured news/RSS syndication eliminates proxy costs and IP bans while preserving real-time detection.

---

## 2026-09-18 — `DEFAULT_SOURCES` Registry & India Post Portals (`scraper.py`)
- **Affected Component:** `src/gov_exam_scraper/scraper.py`
- **Symptom:** Daily CI workflow crashed at startup with `SyntaxError: ),,` and `AttributeError: 'dict' object has no attribute 'is_active'` in `scrape_all()`.
- **What Changed in DOM / PDF / Network:** Not a portal DOM change—an automated update script injected raw Python `dict` literals and duplicate commas into `DEFAULT_SOURCES`, which expects typed `ScraperSource` Pydantic models.
- **Patch Applied:** Restored `DEFAULT_SOURCES` to typed `ScraperSource` instances, hardened `scrape_all()` with `getattr(s, "is_active", False)`, and gated all automated script mutations with `ast.parse()` and `py_compile` checks before committing.
- **Interview Takeaway:** Treating scraper source configs as typed Pydantic models—and gating automated code edits behind AST/compile checks—prevents malformed entries from breaking scheduled pipelines.

---

## 2026-09-02 — Central & Karnataka State Portals (`upsc.gov.in`, `freejobalert.com`, `schooleducation.karnataka.gov.in`, `kpsc.kar.nic.in`)
- **Affected Component:** `src/gov_exam_scraper/scraper.py`, `src/gov_exam_scraper/fetch.py`
- **Symptom:** Groq LLM extraction (`qwen/qwen3.6-27b`) failed with `413`/`429` errors against the 8,000 TPM free-tier cap on 25k–60k token pages, returned `{"exams": []}` (0 records) after keyword line-filtering, and passed `301`/`404` PDF links into Notion.
- **What Changed in DOM / PDF / Network:**
  - Heavy `<nav>`, `<header>`, and `<footer>` chrome bloated raw HTML payloads, while regex line-filtering (`RELEVANT_KEYWORDS`) split `<table>` rows apart and disconnected exam titles from dates and `.pdf` links.
  - Government circular `.pdf` URLs frequently moved (`301`/`302`) or returned `404` without HTML updates, and `.nic.in` endpoints served broken intermediate TLS chains.
- **Patch Applied:**
  - Replaced LLM parsing on the primary scrape path with deterministic BeautifulSoup `_extract_from_dom()` (`html.parser`), decomposing `script, style, nav, header, footer, svg, noscript, aside` and parsing intact `<table>` rows (`<tr>`/`<td>`) with an `<a>` tag fallback (extracting 150 active vacancies at 0 LLM tokens).
  - Added `ContentFetcher.validate_and_resolve_url()` (`HEAD` + `403`/`405` streaming `GET` fallback) to resolve redirects and strip `>= 400` dead links before SHA-256 hashing, plus `verify=False` and `urllib3.Retry`.
- **Interview Takeaway:** Deterministic DOM table parsing outperforms LLM extraction on structured government notices in both latency and reliability—especially when aggressive text condensation destroys HTML table row alignment.