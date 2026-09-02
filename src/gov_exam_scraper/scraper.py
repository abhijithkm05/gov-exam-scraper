"""Main orchestrator and multi-portal scraping engine with Notion synchronization."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
import logging
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import requests

from gov_exam_scraper.exceptions import ConfigurationError, NotionSyncError
from gov_exam_scraper.fetch import ContentFetcher
from gov_exam_scraper.models import ExamRecord, ExamStatus, ScraperSettings, ScraperSource, Sector
from gov_exam_scraper.parse import GroqParser

logger = logging.getLogger("gov_exam_scraper")

DEFAULT_SOURCES = [
    # Karnataka State Portals
    ScraperSource(name="KEA Karnataka Portal", url="https://cetonline.karnataka.gov.in/kea/", sector_hint=Sector.STATE_PSC),
    ScraperSource(name="KPSC Karnataka Recruitment", url="https://kpsc.kar.nic.in/", sector_hint=Sector.STATE_PSC),
    ScraperSource(name="Karnataka State Police (KSP)", url="https://ksp-recruitment.in/", sector_hint=Sector.POLICE),
    ScraperSource(name="Karnataka Forest Department (KFD)", url="https://aranya.gov.in/", sector_hint=Sector.STATE_PSC),
    ScraperSource(name="Karnataka High Court Judiciary", url="https://karnatakajudiciary.kar.nic.in/recruitment.php", sector_hint=Sector.OTHER),
    ScraperSource(name="Karnataka Power Corporation (KPTCL)", url="https://kptcl.karnataka.gov.in/", sector_hint=Sector.ENGINEERING),
    ScraperSource(name="Bangalore Metro Rail (BMRCL)", url="https://english.bmrc.co.in/Career", sector_hint=Sector.PSU),
    ScraperSource(name="Karnataka School Education (DSEL)", url="https://schooleducation.karnataka.gov.in/", sector_hint=Sector.TEACHING),

    # Banking, Insurance & Regulatory
    ScraperSource(name="IBPS Banking Exams", url="https://www.ibps.in/", sector_hint=Sector.BANKING),
    ScraperSource(name="State Bank of India (SBI Careers)", url="https://sbi.co.in/web/careers/current-openings", sector_hint=Sector.BANKING, use_playwright=True),
    ScraperSource(name="Reserve Bank of India (RBI)", url="https://opportunities.rbi.org.in/scripts/vacancies.aspx", sector_hint=Sector.BANKING),
    ScraperSource(name="NABARD Recruitment", url="https://www.nabard.org/careers-notices.aspx", sector_hint=Sector.BANKING),
    ScraperSource(name="National Insurance Company (NICL)", url="https://nationalinsurance.nic.co.in/en/recruitment", sector_hint=Sector.OTHER),
    ScraperSource(name="Life Insurance Corporation (LIC)", url="https://licindia.in/careers", sector_hint=Sector.OTHER),

    # Central Commissions & Railways
    ScraperSource(name="UPSC Active Examinations", url="https://upsc.gov.in/examinations/active-examinations", sector_hint=Sector.UPSC),
    ScraperSource(name="SSC Notices", url="https://ssc.gov.in/", sector_hint=Sector.SSC, use_playwright=True),
    ScraperSource(name="RRB Bangalore", url="https://www.rrbbnc.gov.in/", sector_hint=Sector.RAILWAY),
    ScraperSource(name="National Testing Agency (NTA)", url="https://nta.ac.in/", sector_hint=Sector.OTHER),
    ScraperSource(name="EPFO Recruitment", url="https://www.epfindia.gov.in/site_en/Miscellaneous_Recruitment.php", sector_hint=Sector.OTHER),

    # Engineering, Defence & Central PSUs
    ScraperSource(name="ISRO Careers", url="https://www.isro.gov.in/Careers.html", sector_hint=Sector.ENGINEERING),
    ScraperSource(name="HAL Careers", url="https://hal-india.co.in/Career_Listing.aspx", sector_hint=Sector.PSU),
    ScraperSource(name="BEL Bangalore", url="https://bel-india.in/careers/", sector_hint=Sector.PSU),
    ScraperSource(name="DRDO RAC", url="https://rac.gov.in/", sector_hint=Sector.DEFENCE),
    ScraperSource(name="Airports Authority of India (AAI)", url="https://www.aai.aero/en/careers/recruitment", sector_hint=Sector.PSU, use_playwright=True),

    # Real-Time Consolidated State Feed
    ScraperSource(name="Karnataka FreeJobAlert Feed", url="https://www.freejobalert.com/karnataka-government-jobs/", sector_hint=Sector.STATE_PSC),
]


def parse_date_safely(text: str) -> date | None:
    if not text:
        return None
    cleaned = text.strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            pass
    m = re.search(r"(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{4})", cleaned)
    if m:
        try:
            d, m_, y = map(int, m.groups())
            return date(y, m_, d)
        except Exception:
            pass
    return None


class GovExamScraper:
    """Orchestrates multi-source scraping, parsing, link validation, and Notion syncing."""

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

    def _extract_from_dom(self, soup: BeautifulSoup, base_url: str, sector: Sector) -> list[ExamRecord]:
        """High-precision table and link parser bypassing LLM token limits."""
        today = date.today()
        extracted: list[ExamRecord] = []

        # 1. Parse structured tables
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue

            for row in rows[1:]:
                cols = row.find_all(["td", "th"])
                if len(cols) < 2:
                    continue

                row_text = " ".join(c.get_text(strip=True) for c in cols)
                if not any(k in row_text.lower() for k in ["apply", "recruitment", "officer", "clerk", "post", "exam", "engineer", "2026", "pdf"]):
                    continue

                apply_link = None
                pdf_link = None
                for a in row.find_all("a", href=True):
                    href = a["href"].strip()
                    if not href or href.startswith(("javascript:", "#")):
                        continue
                    abs_link = urljoin(base_url, href)
                    if ".pdf" in abs_link.lower() or "notification" in a.get_text().lower():
                        if not pdf_link:
                            pdf_link = abs_link
                    else:
                        if not apply_link:
                            apply_link = abs_link

                name = cols[0].get_text(separator=" ", strip=True)
                if len(cols) > 2 and len(name) < 5:
                    name = cols[1].get_text(separator=" ", strip=True)

                if any(h in name.lower() for h in ["post name", "sl.no", "advertisement no", "s.no"]):
                    continue

                last_date = None
                for c in cols:
                    d = parse_date_safely(c.get_text(strip=True))
                    if d:
                        last_date = d

                if last_date and last_date < today:
                    continue

                if len(name) >= 4:
                    extracted.append(
                        ExamRecord(
                            exam_name=name[:150],
                            sector=sector,
                            last_date=last_date,
                            apply_link=apply_link or base_url,
                            pdf_link=pdf_link,
                            status=ExamStatus.OPEN,
                            source_url=base_url,
                        )
                    )

        # 2. Fallback: Parse prominent links if no tables matched
        if not extracted:
            for a in soup.find_all("a", href=True):
                txt = a.get_text(separator=" ", strip=True)
                href = a["href"].strip()
                if len(txt) > 12 and any(k in txt.lower() for k in ["recruitment", "notification", "advt", "apply online", "post of"]):
                    abs_url = urljoin(base_url, href)
                    p_link = abs_url if ".pdf" in abs_url.lower() else None
                    a_link = abs_url if not p_link else base_url
                    extracted.append(
                        ExamRecord(
                            exam_name=txt[:150],
                            sector=sector,
                            last_date=None,
                            apply_link=a_link,
                            pdf_link=p_link,
                            status=ExamStatus.OPEN,
                            source_url=base_url,
                        )
                    )

        return extracted

    def scrape_source(self, source: ScraperSource) -> list[ExamRecord]:
        """Fetches, parses, and resolves links for a single portal."""
        try:
            raw_html = self.fetcher.fetch(url=source.url, force_browser=source.use_playwright)
            soup = BeautifulSoup(raw_html, "html.parser")

            for tag in soup(["script", "style", "nav", "header", "footer", "svg", "noscript", "aside"]):
                tag.decompose()

            records = self._extract_from_dom(soup, base_url=source.url, sector=source.sector_hint)

            # Pre-flight link resolution
            for rec in records:
                if rec.pdf_link:
                    rec.pdf_link = self.fetcher.validate_and_resolve_url(rec.pdf_link)
                if rec.apply_link and rec.apply_link != source.url:
                    rec.apply_link = self.fetcher.validate_and_resolve_url(rec.apply_link) or source.url
                rec.recalculate_hash()

            return records
        except Exception as exc:
            logger.warning(f"Could not scrape {source.name} ({source.url}): {exc}")
            return []

    def scrape_all(self, max_workers: int | None = None) -> list[ExamRecord]:
        """Scrapes all active sources concurrently with cross-source deduplication."""
        workers = max_workers or self.settings.max_workers
        all_records: list[ExamRecord] = []
        seen_keys: set[str] = set()

        active_sources = [s for s in self.sources if s.is_active]

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_source = {executor.submit(self.scrape_source, src): src for src in active_sources}

            for future in as_completed(future_to_source):
                try:
                    records = future.result()
                    for rec in records:
                        clean_key = re.sub(r"[^a-zA-Z0-9]", "", rec.exam_name.lower())[:40]
                        if clean_key not in seen_keys:
                            seen_keys.add(clean_key)
                            all_records.append(rec)
                except Exception:
                    pass

        return all_records

    def sync_to_notion(self, records: list[ExamRecord]) -> tuple[dict[str, int], list[ExamRecord]]:
        """Syncs verified exam records with Notion using SHA-256 change detection."""
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

        results_data = resp.json().get("results", [])
        existing_pages: dict[str, str] = {}
        available_columns: set[str] = set()

        if results_data:
            available_columns = set(results_data[0].get("properties", {}).keys())

        for result in results_data:
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
                "Eligibility": {"rich_text": [{"text": {"content": (rec.eligibility or "")[:200]}}]},
            }
            if rec.last_date:
                properties["Last Date"] = {"date": {"start": rec.last_date.isoformat()}}

            if rec.pdf_link and "Notification PDF" in available_columns:
                properties["Notification PDF"] = {"url": rec.pdf_link}

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
        """Queries Notion for exams where Last Date < today and updates Status to CLOSED."""
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
