"""Main orchestrator and multi-portal scraping engine with Notion synchronization."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import logging
import requests

from gov_exam_scraper.exceptions import ConfigurationError, NotionSyncError
from gov_exam_scraper.fetch import ContentFetcher
from gov_exam_scraper.models import ExamRecord, ScraperSettings, ScraperSource, Sector
from gov_exam_scraper.parse import GroqParser

logger = logging.getLogger("gov_exam_scraper")

DEFAULT_SOURCES = [
    # --- Karnataka State Portals ---
    ScraperSource(
        name="KEA Karnataka Portal",
        url="https://cetonline.karnataka.gov.in/kea/",
        sector_hint=Sector.STATE_PSC,
        use_playwright=False,
    ),
    ScraperSource(
        name="KPSC Karnataka Recruitment",
        url="https://kpsc.kar.nic.in/",
        sector_hint=Sector.STATE_PSC,
        use_playwright=False,
    ),
    ScraperSource(
        name="Karnataka State Police (KSP)",
        url="https://ksp-recruitment.in/",
        sector_hint=Sector.POLICE,
        use_playwright=False,
    ),
    ScraperSource(
        name="Karnataka Forest Department (KFD)",
        url="https://aranya.gov.in/",
        sector_hint=Sector.STATE_PSC,
        use_playwright=False,
    ),
    ScraperSource(
        name="Karnataka High Court Judiciary",
        url="https://karnatakajudiciary.kar.nic.in/recruitment.php",
        sector_hint=Sector.OTHER,
        use_playwright=False,
    ),
    ScraperSource(
        name="Karnataka Power Corporation (KPTCL)",
        url="https://kptcl.karnataka.gov.in/",
        sector_hint=Sector.ENGINEERING,
        use_playwright=False,
    ),
    ScraperSource(
        name="Bangalore Metro Rail (BMRCL)",
        url="https://english.bmrc.co.in/Career",
        sector_hint=Sector.PSU,
        use_playwright=False,
    ),
    ScraperSource(
        name="Karnataka School Education (DSEL)",
        url="https://schooleducation.karnataka.gov.in/",
        sector_hint=Sector.TEACHING,
        use_playwright=False,
    ),

    # --- Banking, Insurance & Regulatory ---
    ScraperSource(
        name="IBPS Banking Exams",
        url="https://www.ibps.in/",
        sector_hint=Sector.BANKING,
        use_playwright=False,
    ),
    ScraperSource(
        name="State Bank of India (SBI Careers)",
        url="https://sbi.co.in/web/careers/current-openings",
        sector_hint=Sector.BANKING,
        use_playwright=True,
    ),
    ScraperSource(
        name="Reserve Bank of India (RBI)",
        url="https://opportunities.rbi.org.in/scripts/vacancies.aspx",
        sector_hint=Sector.BANKING,
        use_playwright=False,
    ),
    ScraperSource(
        name="NABARD Recruitment",
        url="https://www.nabard.org/careers-notices.aspx",
        sector_hint=Sector.BANKING,
        use_playwright=False,
    ),
    ScraperSource(
        name="National Insurance Company (NICL)",
        url="https://nationalinsurance.nic.co.in/en/recruitment",
        sector_hint=Sector.OTHER,
        use_playwright=False,
    ),
    ScraperSource(
        name="Life Insurance Corporation (LIC)",
        url="https://licindia.in/careers",
        sector_hint=Sector.OTHER,
        use_playwright=False,
    ),

    # --- Central Commissions & Railways ---
    ScraperSource(
        name="UPSC Active Examinations",
        url="https://upsc.gov.in/examinations/active-examinations",
        sector_hint=Sector.UPSC,
        use_playwright=False,
    ),
    ScraperSource(
        name="SSC Notices",
        url="https://ssc.gov.in/",
        sector_hint=Sector.SSC,
        use_playwright=True,
    ),
    ScraperSource(
        name="RRB Bangalore",
        url="https://www.rrbbnc.gov.in/",
        sector_hint=Sector.RAILWAY,
        use_playwright=False,
    ),
    ScraperSource(
        name="National Testing Agency (NTA)",
        url="https://nta.ac.in/",
        sector_hint=Sector.OTHER,
        use_playwright=False,
    ),
    ScraperSource(
        name="EPFO Recruitment",
        url="https://www.epfindia.gov.in/site_en/Miscellaneous_Recruitment.php",
        sector_hint=Sector.OTHER,
        use_playwright=False,
    ),

    # --- Engineering, Defence & Central PSUs ---
    ScraperSource(
        name="ISRO Careers",
        url="https://www.isro.gov.in/Careers.html",
        sector_hint=Sector.ENGINEERING,
        use_playwright=False,
    ),
    ScraperSource(
        name="HAL Careers",
        url="https://hal-india.co.in/Career_Listing.aspx",
        sector_hint=Sector.PSU,
        use_playwright=False,
    ),
    ScraperSource(
        name="BEL Bangalore",
        url="https://bel-india.in/careers/",
        sector_hint=Sector.PSU,
        use_playwright=False,
    ),
    ScraperSource(
        name="DRDO RAC",
        url="https://rac.gov.in/",
        sector_hint=Sector.DEFENCE,
        use_playwright=False,
    ),
    ScraperSource(
        name="Airports Authority of India (AAI)",
        url="https://www.aai.aero/en/careers/recruitment",
        sector_hint=Sector.PSU,
        use_playwright=True,
    ),

    # --- Real-Time State Aggregator Feed ---
    ScraperSource(
        name="Karnataka FreeJobAlert Feed",
        url="https://www.freejobalert.com/karnataka-government-jobs/",
        sector_hint=Sector.STATE_PSC,
        use_playwright=False,
    ),
]


class GovExamScraper:
    """Orchestrates multi-source scraping, parsing, deduplication, and Notion syncing."""

    def __init__(
        self,
        settings: ScraperSettings | None = None,
        sources: list[ScraperSource] | None = None,
    ) -> None:
        self.settings = settings or ScraperSettings()
        self.sources = sources or DEFAULT_SOURCES
        self.fetcher = ContentFetcher(settings=self.settings)
        self.parser: GroqParser | None = None

    def _get_parser(self) -> GroqParser:
        if self.parser is None:
            self.parser = GroqParser(settings=self.settings)
        return self.parser

    def scrape_source(self, source: ScraperSource) -> list[ExamRecord]:
        """Fetches and parses a single government exam source safely."""
        try:
            raw_html = self.fetcher.fetch(url=source.url, force_browser=source.use_playwright)
            cleaned_text = self.fetcher.clean_html(raw_html, base_url=source.url, target_selector=source.css_selector)
            parser = self._get_parser()
            return parser.parse_exams(cleaned_text, source_url=source.url, sector_hint=source.sector_hint)
        except Exception as exc:
            logger.warning(f"Could not scrape {source.name} ({source.url}): {exc}")
            return []

    def scrape_all(self, max_workers: int | None = None) -> list[ExamRecord]:
        """Scrapes all active sources concurrently with cross-source deduplication."""
        workers = max_workers or self.settings.max_workers
        all_records: list[ExamRecord] = []
        seen_hashes: set[str] = set()

        active_sources = [s for s in self.sources if s.is_active]

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_source = {executor.submit(self.scrape_source, src): src for src in active_sources}

            for future in as_completed(future_to_source):
                try:
                    records = future.result()
                    for rec in records:
                        if rec.content_hash not in seen_hashes:
                            seen_hashes.add(rec.content_hash)
                            all_records.append(rec)
                except Exception:
                    pass

        return all_records

    def sync_to_notion(self, records: list[ExamRecord]) -> tuple[dict[str, int], list[ExamRecord]]:
        """Syncs exam records with a Notion database using SHA-256 change detection."""
        api_key = self.settings.notion_api_key.get_secret_value()
        db_id = self.settings.notion_database_id

        if not api_key or not db_id:
            raise ConfigurationError("NOTION_API_KEY and NOTION_DATABASE_ID must be set in .env")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

        query_url = f"https://api.notion.com/v1/databases/{db_id}/query"
        resp = requests.post(query_url, headers=headers, json={"page_size": 100}, timeout=30)
        if resp.status_code != 200:
            raise NotionSyncError(f"Notion query failed [status {resp.status_code}]: {resp.text}")

        existing_pages: dict[str, str] = {}
        for result in resp.json().get("results", []):
            page_id = result["id"]
            hash_props = result.get("properties", {}).get("Content Hash", {}).get("rich_text", [])
            if hash_props:
                existing_pages[hash_props[0]["text"]["content"]] = page_id

        created_records: list[ExamRecord] = []
        skipped_count = 0

        for rec in records:
            if rec.content_hash in existing_pages:
                skipped_count += 1
                continue

            properties: dict = {
                "Name": {"title": [{"text": {"content": rec.exam_name[:100]}}]},
                "Sector": {"select": {"name": rec.sector.value}},
                "Status": {"select": {"name": rec.status.value}},
                "Apply Link": {"url": rec.apply_link},
                "Content Hash": {"rich_text": [{"text": {"content": rec.content_hash}}]},
                "Eligibility": {"rich_text": [{"text": {"content": rec.eligibility[:200]}}]},
            }
            if rec.last_date:
                properties["Last Date"] = {"date": {"start": rec.last_date.isoformat()}}

            create_url = "https://api.notion.com/v1/pages"
            create_payload = {"parent": {"database_id": db_id}, "properties": properties}
            c_resp = requests.post(create_url, headers=headers, json=create_payload, timeout=30)
            if c_resp.status_code == 200:
                created_records.append(rec)
            else:
                logger.warning(f"Failed to create page for {rec.exam_name}: {c_resp.text}")

        stats = {"created": len(created_records), "updated": 0, "skipped": skipped_count}
        return stats, created_records

    def archive_expired_exams(self) -> int:
        """Queries Notion for exams where Last Date < today and marks their Status as CLOSED."""
        api_key = self.settings.notion_api_key.get_secret_value()
        db_id = self.settings.notion_database_id

        if not api_key or not db_id:
            return 0

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

        today_iso = date.today().isoformat()
        query_url = f"https://api.notion.com/v1/databases/{db_id}/query"
        filter_payload = {
            "filter": {
                "and": [
                    {
                        "property": "Last Date",
                        "date": {"before": today_iso},
                    },
                    {
                        "property": "Status",
                        "select": {"does_not_equal": "CLOSED"},
                    },
                ]
            }
        }

        resp = requests.post(query_url, headers=headers, json=filter_payload, timeout=30)
        if resp.status_code != 200:
            return 0

        expired_pages = resp.json().get("results", [])
        closed_count = 0

        for page in expired_pages:
            page_id = page["id"]
            patch_url = f"https://api.notion.com/v1/pages/{page_id}"
            patch_payload = {
                "properties": {
                    "Status": {"select": {"name": "CLOSED"}}
                }
            }
            p_resp = requests.patch(patch_url, headers=headers, json=patch_payload, timeout=30)
            if p_resp.status_code == 200:
                closed_count += 1

        return closed_count
