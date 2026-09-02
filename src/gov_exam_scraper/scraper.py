"""Main orchestrator and multi-portal scraping engine with Notion synchronization."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import requests

from gov_exam_scraper.exceptions import ConfigurationError, NotionSyncError
from gov_exam_scraper.fetch import ContentFetcher
from gov_exam_scraper.models import ExamRecord, ScraperSettings, ScraperSource, Sector
from gov_exam_scraper.parse import GroqParser

DEFAULT_SOURCES = [
    ScraperSource(
        name="KPSC Karnataka Recruitment",
        url="https://kpsc.kar.nic.in/",
        sector_hint=Sector.STATE_PSC,
        use_playwright=False,
    ),
    ScraperSource(
        name="KEA Karnataka Portal",
        url="https://cetonline.karnataka.gov.in/kea/",
        sector_hint=Sector.STATE_PSC,
        use_playwright=False,
    ),
    ScraperSource(
        name="Karnataka FreeJobAlert",
        url="https://www.freejobalert.com/karnataka-government-jobs/",
        sector_hint=Sector.STATE_PSC,
        use_playwright=False,
    ),
    ScraperSource(
        name="UPSC Active Examinations",
        url="https://upsc.gov.in/examinations/active-examinations",
        sector_hint=Sector.UPSC,
        use_playwright=False,
    ),
    ScraperSource(
        name="SSC Latest Notices",
        url="https://ssc.gov.in/",
        sector_hint=Sector.SSC,
        use_playwright=True,
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
        """Fetches and parses a single government exam source."""
        raw_html = self.fetcher.fetch(url=source.url, force_browser=source.use_playwright)
        cleaned_text = self.fetcher.clean_html(raw_html, base_url=source.url, target_selector=source.css_selector)
        parser = self._get_parser()
        return parser.parse_exams(cleaned_text, source_url=source.url, sector_hint=source.sector_hint)

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

        # 1. Fetch existing page hashes
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

        # 2. Ingest new records
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
                raise NotionSyncError(f"Failed to create page: {c_resp.text}")

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
