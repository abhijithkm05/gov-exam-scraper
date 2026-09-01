"""Custom exception hierarchy for gov-exam-scraper."""

class GovExamScraperError(Exception):
    """Base exception for all errors raised by gov-exam-scraper."""
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)

class ConfigurationError(GovExamScraperError):
    """Raised when required settings or API keys are missing or invalid."""

class FetchError(GovExamScraperError):
    """Raised when an HTTP request fails after max retries."""
    def __init__(self, message: str, url: str, status_code: int | None = None) -> None:
        self.url = url
        self.status_code = status_code
        super().__init__(f"Fetch failed for {url} [status: {status_code}]: {message}")

class BrowserFetchError(GovExamScraperError):
    """Raised when Playwright headless browser navigation fails."""
    def __init__(self, message: str, url: str) -> None:
        self.url = url
        super().__init__(f"Browser navigation failed for {url}: {message}")

class LLMResponseValidationError(GovExamScraperError):
    """Raised when Groq returns malformed or non-compliant JSON."""

class GroqRateLimitError(GovExamScraperError):
    """Raised when Groq API rate limits (HTTP 429) are encountered."""
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        self.status_code = 429
        super().__init__(message)

class NotionSyncError(GovExamScraperError):
    """Raised when synchronizing with the Notion database fails."""
