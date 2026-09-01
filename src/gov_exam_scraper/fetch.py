"""Dual-tier HTTP and headless Playwright fetcher with in-memory TTL caching."""

import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from cachetools import TTLCache
from playwright.sync_api import sync_playwright
import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from gov_exam_scraper.exceptions import BrowserFetchError, FetchError
from gov_exam_scraper.models import ScraperSettings


def clean_target_url(raw_url: str) -> str:
    """Strips accidental markdown link syntax, brackets, and whitespace."""
    url = raw_url.strip()
    md_match = re.search(r"\((https?://[^\)]+)\)", url)
    if md_match:
        return md_match.group(1).strip()
    bracket_match = re.search(r"\[(https?://[^\]]+)\]", url)
    if bracket_match:
        return bracket_match.group(1).strip()
    return url.strip("<>\"'[]() ")


class ContentFetcher:
    """Retrieves and cleans web content via Requests and Playwright."""

    def __init__(self, settings: ScraperSettings | None = None) -> None:
        self.settings = settings or ScraperSettings()
        self._cache: TTLCache = TTLCache(maxsize=200, ttl=self.settings.cache_ttl_seconds)
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,kn;q=0.8",
        })

    def fetch(self, url: str, force_browser: bool = False, bypass_cache: bool = False) -> str:
        """Fetches raw HTML from a target URL."""
        sanitized_url = clean_target_url(url)
        if not bypass_cache and sanitized_url in self._cache:
            return self._cache[sanitized_url]

        html = self._fetch_with_playwright(sanitized_url) if force_browser else self._fetch_with_requests(sanitized_url)
        self._cache[sanitized_url] = html
        return html

    def _fetch_with_requests(self, url: str) -> str:
        @retry(
            reraise=True,
            stop=stop_after_attempt(self.settings.max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            retry=retry_if_exception_type((requests.RequestException, FetchError)),
        )
        def _get() -> str:
            try:
                resp = self._session.get(url, timeout=self.settings.request_timeout_seconds)
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After", "5")
                    raise FetchError(f"Rate limited (429). Retry after {retry_after}s", url=url, status_code=429)
                if resp.status_code >= 400:
                    raise FetchError(f"HTTP error", url=url, status_code=resp.status_code)
                resp.encoding = resp.apparent_encoding or "utf-8"
                return resp.text
            except requests.RequestException as e:
                raise FetchError(str(e), url=url) from e

        return _get()

    def _fetch_with_playwright(self, url: str) -> str:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    user_agent=self._session.headers["User-Agent"],
                    viewport={"width": 1280, "height": 800},
                )
                page.goto(url, timeout=self.settings.playwright_timeout_seconds * 1000, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
                content = page.content()
                browser.close()
                return content
        except Exception as e:
            raise BrowserFetchError(str(e), url=url) from e

    @staticmethod
    def clean_html(html: str, base_url: str, target_selector: str | None = None) -> str:
        """Sanitizes HTML and converts relative links into absolute markdown links."""
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav", "aside", "form"]):
            tag.decompose()

        root = soup.select_one(target_selector) if target_selector else soup.body or soup

        for a in root.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue
            abs_url = urljoin(base_url, href)
            link_text = a.get_text(strip=True) or "Link"
            a.replace_with(f" [{link_text}]({abs_url}) ")

        text = root.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        cleaned = "\n".join(lines)
        return re.sub(r"\n{3,}", "\n\n", cleaned)
