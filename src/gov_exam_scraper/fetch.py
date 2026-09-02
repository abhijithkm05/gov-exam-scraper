"""Fetch layer supporting HTTP sessions, link verification, and Playwright browser rendering."""

import logging
import re
from typing import Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from gov_exam_scraper.exceptions import FetchError
from gov_exam_scraper.models import ScraperSettings

logger = logging.getLogger("gov_exam_scraper")

# Keywords indicating recruitment, exam notices, or document circulars
RELEVANT_KEYWORDS = re.compile(
    r"(recruitment|notification|advertisement|advt|exam|examination|vacancy|vacancies|"
    r"post|apply|last date|eligibility|qualification|application|admit card|hall ticket|"
    r"selection|kpsc|kea|c-group|gazetted|constable|officer|clerk|apprentice|\.pdf)",
    re.IGNORECASE,
)


class ContentFetcher:
    """Handles HTML retrieval, token pruning, and link verification."""

    def __init__(self, settings: Optional[ScraperSettings] = None) -> None:
        self.settings = settings or ScraperSettings()
        self.session = self._init_session()

    def _init_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,kn;q=0.8",
        })
        return session

    def validate_and_resolve_url(self, url: Optional[str], timeout: int = 8) -> Optional[str]:
        """Validates that a URL is alive (status < 400) and follows redirects."""
        if not url or not url.startswith(("http://", "https://")):
            return None

        try:
            resp = self.session.head(url, timeout=timeout, allow_redirects=True, verify=False)
            if resp.status_code in (403, 405):
                resp = self.session.get(url, timeout=timeout, stream=True, allow_redirects=True, verify=False)

            if resp.status_code < 400:
                return resp.url
            return None
        except Exception:
            return None

    def fetch(self, url: str, force_browser: bool = False) -> str:
        """Fetches raw HTML, choosing requests or Playwright based on source needs."""
        if force_browser:
            return self._fetch_browser(url)
        try:
            resp = self.session.get(url, timeout=self.settings.request_timeout_seconds, verify=False)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            logger.info(f"Standard fetch failed for {url} ({exc}); attempting headless browser fallback.")
            return self._fetch_browser(url)

    def _fetch_browser(self, url: str) -> str:
        """Launches headless Chromium to resolve client-rendered SPAs."""
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=self.session.headers["User-Agent"],
                    ignore_https_errors=True
                )
                page = context.new_page()
                page.goto(url, timeout=self.settings.playwright_timeout_seconds * 1000, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
                html_content = page.content()
                browser.close()
                return html_content
        except Exception as exc:
            raise FetchError(f"Headless browser failed to load {url}: {exc}") from exc

    def clean_html(self, raw_html: str, base_url: str = "", target_selector: Optional[str] = None) -> str:
        """Strips noise and keeps only relevant recruitment lines under token caps."""
        soup = BeautifulSoup(raw_html, "html.parser")

        if target_selector:
            matched = soup.select_one(target_selector)
            if matched:
                soup = matched

        for tag in soup(["script", "style", "svg", "noscript", "iframe", "header", "footer", "nav"]):
            tag.decompose()

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if not href or href.startswith("javascript:") or href.startswith("#"):
                continue
            abs_url = urljoin(base_url, href)
            link_text = a_tag.get_text(separator=" ", strip=True) or "Link"
            a_tag.replace_with(f" [{link_text}]({abs_url}) ")

        text = soup.get_text(separator="\n", strip=True)
        raw_lines = [line.strip() for line in text.splitlines() if line.strip()]

        # Filter lines: only keep recruitment-relevant lines and immediately adjacent lines
        filtered_lines = []
        for i, line in enumerate(raw_lines):
            if RELEVANT_KEYWORDS.search(line):
                # Add context (previous line if not already added)
                if i > 0 and raw_lines[i - 1] not in filtered_lines:
                    filtered_lines.append(raw_lines[i - 1])
                filtered_lines.append(line)
                # Add next line as context
                if i + 1 < len(raw_lines):
                    filtered_lines.append(raw_lines[i + 1])

        # If keyword filtering was too aggressive (under 5 lines), take first 100 raw lines
        chosen_lines = filtered_lines if len(filtered_lines) >= 5 else raw_lines[:100]

        # Deduplicate while preserving order and strictly limit output size
        seen = set()
        deduped = []
        for line in chosen_lines:
            if line not in seen:
                seen.add(line)
                deduped.append(line)

        # Cap total text length to 6,000 chars (~1,500 tokens) - guaranteed to fit Groq limits
        combined_text = "\n".join(deduped)
        return combined_text[:6000]
