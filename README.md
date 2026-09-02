# 🏛️ Gov Exam Scraper & Automated Notification Engine

[![Daily Exam Tracker & Notion Sync](https://github.com/abhijithkm05/gov-exam-scraper/actions/workflows/daily_scrape.yml/badge.svg)](https://github.com/abhijithkm05/gov-exam-scraper/actions/workflows/daily_scrape.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Playwright](https://img.shields.io/badge/engine-Playwright%20Chromium-green.svg)](https://playwright.dev/python/)
[![Groq AI](https://img.shields.io/badge/inference-Groq%20Cloud-orange.svg)](https://groq.com/)
[![Notion API](https://img.shields.io/badge/database-Notion%20API-black.svg)](https://developers.notion.com/)
[![Discord](https://img.shields.io/badge/alerts-Discord%20Webhook-5865F2.svg)](https://discord.com/)

An autonomous intelligence and scraping pipeline that monitors **25+ official recruitment portals** across Karnataka State, Central Commissions, Banking institutions, and premier Public Sector Undertakings (PSUs). 

The system leverages **Groq-powered LLMs** to extract structured data from unpredictable government layouts, normalizes deadlines, prevents duplicates using **SHA-256 cryptographic hashing**, synchronizes live data to a **Notion Workspace**, auto-closes expired jobs, and dispatches real-time alerts to **Discord**.

---

## ⚡ Architecture Flow

```text
[ 25+ Government Portals (Static HTML + Dynamic SPAs) ]
                         │
                         ▼
        [ Dual Fetcher Engine (Requests + Playwright) ]
                         │
                         ▼
       [ HTML Content Cleaner & Token Minimizer ]
                         │
                         ▼
       [ Groq Cloud LLM (Structured JSON Extraction) ]
                         │
                         ▼
   [ Pydantic Models & Deterministic SHA-256 Hashing ]
                         │
         ┌───────────────┴───────────────┐
         ▼                               ▼
[ Notion Database Sync ]        [ Lifecycle Monitor ]
  • Deduplicate existing          • Auto-archive past exams
  • Insert new vacancies            (Last Date < Today -> CLOSED)
         │
         ▼
[ Discord Push Alerts ]
  • Rich formatted embed with direct application links
✨ Key FeaturesMulti-Tier Portal Monitoring: Covers state portals (KPSC, KEA, Police, Forest, KPTCL), central boards (UPSC, SSC, Railways, NTA), banking boards (IBPS, SBI, RBI, NABARD), and PSUs (ISRO, HAL, BEL, AAI).Dual Scraping Engine: Uses lightweight HTTP sessions for static portals and headless Chromium (Playwright) for JavaScript-rendered SPAs.Zero Layout-Break Resilience: Instead of fragile CSS selectors, Groq LLMs parse raw text to consistently extract exam titles, deadlines, qualifications, and direct application links.Deterministic Deduplication: Computes SHA-256 hashes of record signatures (Name + Sector + Deadline + Link) to ensure identical notifications are never stored twice.Automated Expiry Lifecycle: Scans existing records daily and updates past deadlines (Last Date < today) to CLOSED in Notion automatically.Smart Alerting: Dispatches Discord webhook embeds only when genuinely new notifications are published.Serverless Execution: Runs completely autonomously via GitHub Actions every morning at 07:47 AM IST (02:17 UTC).📁 Repository StructurePlaintextgov-exam-scraper/
├── .github/workflows/
│   └── daily_scrape.yml      # Automated GitHub Actions daily cron pipeline
├── src/gov_exam_scraper/
│   ├── cli.py                # Typer CLI commands (scrape, test-url, sources)
│   ├── exceptions.py         # Custom exception handling hierarchy
│   ├── fetch.py              # Dual network fetcher (Requests + Playwright)
│   ├── models.py             # Pydantic schemas, Enums, date cleaners & settings
│   ├── notify.py             # Discord webhook and Telegram alert dispatchers
│   ├── parse.py              # Groq Cloud structured JSON parsing engine
│   └── scraper.py            # Master orchestrator, source registry & Notion syncer
├── MASTER_DOCUMENTATION.md   # Complete architectural specification & blueprint
├── pyproject.toml            # Project build configuration & dependency tree
└── README.md
🚀 Quickstart & Local Setup1. Clone and Create Virtual EnvironmentBashgit clone [https://github.com/abhijithkm05/gov-exam-scraper.git](https://github.com/abhijithkm05/gov-exam-scraper.git)
cd gov-exam-scraper

python -m venv .venv
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# On macOS/Linux:
source .venv/bin/activate
2. Install Package & BrowsersBashpip install --upgrade pip
pip install -e .
playwright install chromium
3. Configure Environment VariablesCreate a .env file in the root directory:Ini, TOMLGROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=qwen/qwen3.6-27b

NOTION_API_KEY=ntn_your_notion_api_token_here
NOTION_DATABASE_ID=your_32_character_database_id_here

DISCORD_WEBHOOK_URL=[https://discord.com/api/webhooks/your_webhook_url_here](https://discord.com/api/webhooks/your_webhook_url_here)
🛠️ CLI UsageList all configured target portals:Bashgov-exam-scraper sources
Test extraction on a single portal:Bashgov-exam-scraper test-url [https://kpsc.kar.nic.in/](https://kpsc.kar.nic.in/) --sector STATE_PSC
Execute full scrape, Notion sync, and alert dispatch:Bashgov-exam-scraper scrape --sync-notion --output exams.json
🌐 Monitored Portals DirectoryCategoryTargeted OrganizationsKarnataka StateKPSC, KEA, Karnataka State Police (KSP), Forest Dept, KPTCL/ESCOMs, High Court Judiciary, Bangalore Metro (BMRCL), School Education (DSEL)Central CommissionsUPSC, Staff Selection Commission (SSC), Railway Recruitment Board (RRB Bangalore), National Testing Agency (NTA), EPFOBanking & FinanceIBPS, State Bank of India (SBI Careers), Reserve Bank of India (RBI), NABARD, NICL, LIC IndiaPSUs & DefenceISRO ICRB, HAL, Bharat Electronics (BEL), DRDO RAC, Airports Authority of India (AAI)⚙️ Cloud CI/CD AutomationThis repository runs automatically on GitHub Actions via .github/workflows/daily_scrape.yml:Schedule: Runs daily at 02:17 UTC (07:47 AM IST).Secrets Required: GROQ_API_KEY, GROQ_MODEL, NOTION_API_KEY, NOTION_DATABASE_ID, and DISCORD_WEBHOOK_URL.Artifacts: Stores the generated exams.json payload for every run for up to 90 days.