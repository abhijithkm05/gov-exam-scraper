# Master Architecture & Operational Blueprint: Automated Government Exam Scraping & Tracking System

---

## 1. Executive Summary & Project Intent

The **Automated Government Exam Scraper** is an end-to-end intelligence and extraction pipeline designed to solve the problem of fragmented, unpredictable, and irregular public recruitment notifications across Karnataka state, central commissions, banking boards, and PSUs. 

### Primary Problems Solved
* **Notification Fragmentation**: Government vacancies are distributed across dozens of disparate, non-standardized portals that lack uniform RSS feeds or structured APIs.
* **Unpredictable DOMs & Layout Shifts**: Government websites frequently alter their layout, render content inside dynamic JavaScript frameworks (React/Angular), or embed notifications inside unstructured HTML tables. Traditional CSS-selector scrapers break frequently when these change.
* **Manual Tracking Overhead**: Manually checking dozens of websites daily is error-prone and time-consuming.
* **Notification Spam & Redundancy**: Without deterministic change detection, recurring automated scrapers repeatedly alert users about the same active jobs.

### System Solution
An autonomous Python pipeline deployed on **GitHub Actions** that:
1. Crawls static and dynamic government portals on a daily schedule.
2. Uses **Groq Cloud High-Speed Inference (LLMs)** to extract structured JSON data from messy HTML layouts.
3. Calculates a deterministic **SHA-256 fingerprint** for every notice to guarantee zero duplicate database writes.
4. Synchronizes validated records with a central **Notion Workspace Database**.
5. Automatically archives expired deadlines (`Last Date < today`) by flipping their Notion status to `CLOSED`.
6. Dispatches mobile alerts to **Discord channels** via webhook only when genuinely new notices are detected.

---

## 2. Technology Stack & Architectural Justifications

| Component | Technology / Service | Rationale & Trade-offs |
| :--- | :--- | :--- |
| **Core Language** | Python 3.11+ | Provides strong type hinting, native async/concurrent processing capabilities, and wide ecosystem support for scraping and parsing. |
| **Validation & Schemas** | Pydantic v2 & `pydantic-settings` | High-speed C-based schema validation, custom field normalizers for irregular date strings, and automated `.env` variable binding. |
| **CLI Framework** | Typer & Rich | Structured command-line interface with subcommands, interactive tables, colored progress bars, and formatted status boards. |
| **Static Fetching Engine** | Requests (HTTP) | Ultra-lightweight, high-throughput network fetching for standard server-side rendered government portals (KPSC, KEA, UPSC). |
| **Dynamic Fetching Engine** | Playwright (Chromium) | Fully automated headless browser engine capable of executing JavaScript, handling single-page application hydration, and waiting for dynamic DOM elements (SSC, SBI, AAI). |
| **AI Extraction Engine** | Groq Cloud API | Near-instant inference (<1.0s token turnaround) with strict JSON Schema output mode, turning unstructured scraped text into clean, structured records. |
| **Database Target** | Notion API | Flexible cloud database supporting Kanban boards, deadline calendars, and property-based filtering without hosting a custom SQL/NoSQL instance. |
| **Push Notification Alerting** | Discord Webhooks | Free, zero-setup mobile push notifications with rich embed styling and zero server maintenance. |
| **Orchestration & CI/CD** | GitHub Actions | Serverless, zero-cost Ubuntu runners executing daily on an offset cron schedule with built-in secrets management. |

---

## 3. Complete Codebase Directory & File Inventory

```text
D:\Github\Govt_Exam_Scrapper\ (Project Root)
├── .github/
│   └── workflows/
│       └── daily_scrape.yml              # GitHub Actions daily cron & manual dispatch pipeline
├── src/
│   └── gov_exam_scraper/
│       ├── __init__.py                   # Module namespace declaration
│       ├── cli.py                        # Typer CLI commands: scrape, test-url, sources
│       ├── exceptions.py                 # Custom exceptions: FetchError, ParseError, NotionSyncError
│       ├── fetch.py                      # Content fetcher handling Requests & Playwright headless browser
│       ├── models.py                     # Pydantic domain models, enums, date cleaners, and settings
│       ├── notify.py                     # Alert engine for Discord Webhook and Telegram Bot dispatching
│       ├── parse.py                      # Groq LLM integration and JSON schema validation logic
│       └── scraper.py                    # Master orchestrator, source registry, deduplication & Notion sync
├── .env                                  # Local development credentials (git-ignored)
├── .env.example                          # Template credentials file for onboarding
├── .gitignore                            # Excludes venv, cache, local data, and sensitive keys
├── pyproject.toml                        # PEP 621 packaging metadata and project dependencies
└── README.md                             # Repository overview and setup instructions

4. Module Deep Dive: Architecture & Implementationsrc/gov_exam_scraper/models.pyDefines the core data contracts and configuration logic:Sector (Enum): Standardizes vacancies into 11 categories: UPSC, SSC, STATE_PSC, BANKING, RAILWAY, DEFENCE, POLICE, TEACHING, PSU, ENGINEERING, and OTHER. Includes regex-based fuzzy fallback handling.ExamStatus (Enum): Tracks application states: OPEN, CLOSED, UPCOMING, and UNKNOWN.parse_flexible_date(value): Sanitizes non-standard Indian administrative date formats, stripping ordinal suffixes (31st, 1st, 2nd) and handling formats like DD-MM-YYYY, DD/MM/YYYY, and DD Month YYYY.ExamRecord (BaseModel): The core model for each exam, containing fields for exam_name, sector, last_date, eligibility, apply_link, status, and content_hash.Deterministic Hashing: In model_post_init, a SHA-256 hash is generated from EXAM_NAME|SECTOR|LAST_DATE|APPLY_LINK|STATUS. If any critical field changes upstream, the hash changes, triggering a database update.ScraperSource (BaseModel): Defines target portals, including name, url, sector_hint, use_playwright, and css_selector.ScraperSettings (BaseSettings): Reads and validates environment variables from .env, including API keys, database IDs, timeouts, and worker counts.src/gov_exam_scraper/fetch.pyProvides resilient network scraping:Dual-Engine Fetching:HTTP Mode: Uses a configured requests.Session with modern browser user-agent headers, retries, and backoffs for fast static fetches.Playwright Mode: Launches a headless Chromium browser instance with custom timeouts and page navigation wait states (domcontentloaded) for JavaScript-heavy single-page applications.clean_html(): Uses BeautifulSoup to strip script tags, CSS styles, SVGs, base64 images, headers, navigation bars, and footers, extracting clean text and preserving hyperlinks to optimize LLM token usage.src/gov_exam_scraper/parse.pyHandles LLM-driven structured extraction:Integrates with Groq Cloud inference endpoints using high-throughput open-weight models (qwen/qwen3.6-27b or llama-3.3-70b-versatile).Forces the LLM to output structured JSON strictly matching the ExtractionBatch schema.Parses raw notification tables and text into clean lists of ExamRecord objects.src/gov_exam_scraper/scraper.pyThe orchestrator managing extraction, deduplication, and database synchronization:DEFAULT_SOURCES: Registry containing 25 pre-configured Karnataka state, central commission, banking, and PSU recruitment portals.scrape_all(): Uses ThreadPoolExecutor to scrape multiple portals concurrently while handling per-portal errors gracefully without failing the entire run.sync_to_notion():Queries the target Notion database for all existing Content Hash values.Compares incoming records against existing hashes.Skips matches to prevent duplicates.Commits new records via POST https://api.notion.com/v1/pages.archive_expired_exams(): Queries Notion for entries where Last Date < today and Status != CLOSED, updating them to CLOSED via PATCH requests.src/gov_exam_scraper/notify.pyHandles mobile notifications:send_discord_alert(): Formats new recruitment records into rich Discord embeds displaying exam names, sectors, deadlines, and application links.dispatch_alerts(): Evaluates sync results and sends notifications only when new exams are added (created > 0), preventing repetitive alerts.src/gov_exam_scraper/cli.pyThe command-line interface providing interactive terminal commands:gov-exam-scraper scrape: Runs concurrent scraping, optional Notion sync, auto-archiving, alert dispatching, and JSON/CSV file export.gov-exam-scraper test-url <URL>: Tests scraping and LLM extraction on a single URL for debugging.gov-exam-scraper sources: Displays a formatted status table of all active target portals.5. Third-Party Setup & Credentials GuideA. Groq Cloud API SetupVisit Groq Cloud Console.Sign in and navigate to API Keys in the left sidebar.Click Create API Key, name it Gov-Exam-Tracker, and save the key (gsk_...).Selected Model: qwen/qwen3.6-27b (recommended for parsing speed and reasoning).B. Notion Database & Integration SetupVisit Notion My Integrations.Click New integration, name it Gov Exam Sync Bot, associate it with your workspace, and save the secret key (ntn_...).In Notion, create a new Full Page Database titled Gov Exam Tracker.Configure the database columns with these exact names and property types:Name: Property Type = TitleSector: Property Type = Select (Options: STATE_PSC, UPSC, SSC, BANKING, RAILWAY, DEFENCE, POLICE, TEACHING, PSU, ENGINEERING, OTHER)Status: Property Type = Select (Options: OPEN, CLOSED, UPCOMING, UNKNOWN)Apply Link: Property Type = URLLast Date: Property Type = DateContent Hash: Property Type = Text (Rich Text)Eligibility: Property Type = Text (Rich Text)Connect the Integration: Open the database in Notion, click the ... menu in the top right, go to Connections $\rightarrow$ Connect to, search for Gov Exam Sync Bot, and grant access.Get Database ID: Copy the database URL from your browser address bar:https://www.notion.so/{workspace_name}/{DATABASE_ID}?v={view_id}The 32-character string between the workspace name and the ?v= is your NOTION_DATABASE_ID.C. Discord Alert Webhook SetupOpen Discord on desktop or in your browser.Select your server and target text channel (e.g., #exam-alerts).Click the Gear icon (⚙️ / Edit Channel) next to the channel name.Select Integrations $\rightarrow$ Webhooks $\rightarrow$ New Webhook.Name it Gov Exam Tracker Bot and click Copy Webhook URL.6. Zero-to-One Deployment & Step-by-Step SetupFollow these steps to set up and run the system on a clean development machine:Step 1: Open PowerShell and Set Up the DirectoryPowerShellmkdir -p D:\Github\Govt_Exam_Scrapper
cd D:\Github\Govt_Exam_Scrapper
Step 2: Set Up Virtual Environment & DependenciesPowerShellpython -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
playwright install chromium
Step 3: Configure Environment VariablesCreate your local .env file in the project root:PowerShell@'
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=qwen/qwen3.6-27b

NOTION_API_KEY=ntn_your_notion_api_token_here
NOTION_DATABASE_ID=your_32_character_database_id_here

DISCORD_WEBHOOK_URL=[https://discord.com/api/webhooks/your_webhook_url_here](https://discord.com/api/webhooks/your_webhook_url_here)

CACHE_TTL_SECONDS=3600
MAX_WORKERS=5
REQUEST_TIMEOUT_SECONDS=60
PLAYWRIGHT_TIMEOUT_SECONDS=60
'@ | Set-Content -Path .env -Encoding UTF8
Step 4: Run Local Verification TestsCheck configured sources:PowerShellgov-exam-scraper sources
Test single extraction:PowerShellgov-exam-scraper test-url [https://kpsc.kar.nic.in/](https://kpsc.kar.nic.in/) --sector STATE_PSC
Execute full scrape and Notion sync:PowerShellgov-exam-scraper scrape --sync-notion --output exams.json
Step 5: Initialize Git and Push to GitHubPowerShellgit init
git add .
git commit -m "feat: Complete automated exam scraper system"
git branch -M main
git remote add origin [https://github.com/your-username/gov-exam-scraper.git](https://github.com/your-username/gov-exam-scraper.git)
git push -u origin main
Step 6: Add Repository Secrets to GitHub ActionsTo allow automated cloud execution, add your secrets in GitHub:Go to: https://github.com/{your-username}/gov-exam-scraper/settings/secrets/actionsAdd the following repository secrets:GROQ_API_KEY: Your Groq API key (gsk_...)GROQ_MODEL: qwen/qwen3.6-27bNOTION_API_KEY: Your Notion integration token (ntn_...)NOTION_DATABASE_ID: Your 32-character Notion database IDDISCORD_WEBHOOK_URL: Your full Discord webhook URL7. Cloud Automation Workflow (daily_scrape.yml)The automated pipeline is scheduled via GitHub Actions:File Location: .github/workflows/daily_scrape.ymlSchedule: cron: '17 2 * * *' (Runs daily at 02:17 UTC / 07:47 AM IST). The odd-minute offset avoids top-of-the-hour runner queue congestion.Manual Dispatch: Includes workflow_dispatch to allow manual execution anytime from the GitHub Actions UI.Pipeline Steps:Checks out repository code via actions/checkout@v4.Sets up Python 3.11 with dependency caching via actions/setup-python@v5.Installs package dependencies and Playwright Chromium binaries with system libraries.Injects repository secrets into the execution environment.Executes: gov-exam-scraper scrape --sync-notion --output exams.json.Syncs new entries to Notion, archives expired ones, and dispatches Discord alerts if new records are found.Uploads exams.json as a downloadable workflow artifact (retained for 90 days).8. Registry of Monitored Recruitment PortalsPortal NameTarget URLSectorEngineScope of Notifications TrackedKEA Karnatakahttps://cetonline.karnataka.gov.in/kea/STATE_PSCRequestsVillage Accountant, Surveyor, FDA, SDA, KRIES, KSRPKPSC Karnatakahttps://kpsc.kar.nic.in/STATE_PSCRequestsGazetted Probationers (KAS), Group A, B, C CadresKarnataka State Policehttps://ksp-recruitment.in/POLICERequestsSub-Inspector (PSI), Civil Constable, Armed PoliceKarnataka Forest Depthttps://aranya.gov.in/STATE_PSCRequestsRange Forest Officer (RFO), DRFO, Forest GuardKarnataka High Courthttps://karnatakajudiciary.kar.nic.in/recruitment.phpOTHERRequestsDistrict Judges, Civil Judges, Typists, ClerksKPTCL / ESCOMshttps://kptcl.karnataka.gov.in/ENGINEERINGRequestsAssistant Engineers, Junior Engineers, Clerical CadreBMRCL Bangalore Metrohttps://english.bmrc.co.in/CareerPSURequestsMaintainers, Station Controllers, Section EngineersKarnataka School Edhttps://schooleducation.karnataka.gov.in/TEACHINGRequestsKARTET, Primary (GPSTR) & High School (HSTR) TeachersIBPS Bankinghttps://www.ibps.in/BANKINGRequestsProbationary Officers, Clerks, Specialist Officers, RRBState Bank of Indiahttps://sbi.co.in/web/careers/current-openingsBANKINGPlaywrightSBI PO, Junior Associates (Clerk), Specialist OfficersReserve Bank of Indiahttps://opportunities.rbi.org.in/scripts/vacancies.aspxBANKINGRequestsRBI Grade B Officers, RBI Assistant VacanciesNABARDhttps://www.nabard.org/careers-notices.aspxBANKINGRequestsAssistant Manager (Grade A), Manager (Grade B)National Insurancehttps://nationalinsurance.nic.co.in/en/recruitmentOTHERRequestsAdministrative Officers (AO Scale-I), AssistantsLife Insurance Corphttps://licindia.in/careersOTHERRequestsAAO, Apprentice Development Officers (ADO), AssistantsUPSC Active Examshttps://upsc.gov.in/examinations/active-examinationsUPSCRequestsCivil Services (IAS/IPS), NDA, CDS, ESE, CAPFSSC Officialhttps://ssc.gov.in/SSCPlaywrightCGL, CHSL, CPO, MTS, GD Constable, Junior EngineerRRB Bangalorehttps://www.rrbbnc.gov.in/RAILWAYRequestsRRB NTPC, ALP, Technicians, Group D Railway postsNTA Testing Agencyhttps://nta.ac.in/OTHERRequestsUGC NET, CSIR NET, National Eligibility TestsEPFO Recruitmenthttps://www.epfindia.gov.in/site_en/Miscellaneous_Recruitment.phpOTHERRequestsSocial Security Assistant (SSA), Enforcement OfficersISRO Careershttps://www.isro.gov.in/Careers.htmlENGINEERINGRequestsScientist/Engineer 'SC', Technical AssistantsHAL Indiahttps://hal-india.co.in/Career_Listing.aspxPSURequestsManagement Trainees (MT), Design Trainees (DT)BEL Bangalorehttps://bel-india.in/careers/PSURequestsProject Engineers, Trainee Engineers, Deputy EngineersDRDO RAChttps://rac.gov.in/DEFENCERequestsScientist 'B' (GATE-based and direct descriptive exams)AAI Careershttps://www.aai.aero/en/careers/recruitmentPSUPlaywrightAir Traffic Control (ATC) Executives, Technical ManagersKarnataka JobAlerthttps://www.freejobalert.com/karnataka-government-jobs/STATE_PSCRequestsFast real-time aggregated state notification feed9. AI Handoff & Maintenance GuidelinesWhen sharing this blueprint with an AI assistant for future maintenance or upgrades:Architecture Context: The project runs on Python 3.11, Pydantic v2, Typer CLI, Groq Cloud structured extraction, Notion REST API, and Playwright Chromium.Deterministic Hash Invariance: Do not modify the string concatenation order in ExamRecord.model_post_init() without running a database migration, as altering it will invalidate existing SHA-256 keys and cause duplicate entries.Portal Ingestion Strategy: All monitored URLs are stored in DEFAULT_SOURCES inside src/gov_exam_scraper/scraper.py. Enable use_playwright=True only for portals requiring JavaScript rendering (such as SPAs or dynamic tables). Use standard HTTP requests for static sites to keep runs fast and lightweight.Cloud Workflow Schedule: The cron schedule in .github/workflows/daily_scrape.yml should use an odd-minute offset (e.g., 17 2 * * *) to bypass top-of-the-hour GitHub Actions traffic congestion.
---

### Method 2: Write via Python Script (Zero Terminal Syntax Errors)

If you prefer an automated single command that avoids PowerShell copy-paste formatting traps, run this in PowerShell:

```powershell
python -c "import urllib.request; open('MASTER_DOCUMENTATION.md', 'w', encoding='utf-8').write('''# Master Architecture & Operational Blueprint: Automated Government Exam Scraping & Tracking System

This repository tracks government recruitment notifications across Karnataka, Central commissions, Banking, and PSUs.
Key entry point: src/gov_exam_scraper/cli.py
Workflow configuration: .github/workflows/daily_scrape.yml
Portals registry: src/gov_exam_scraper/scraper.py'''); print('Created!')"