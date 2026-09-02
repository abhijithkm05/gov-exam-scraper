"""Custom exception hierarchy for gov_exam_scraper."""


class ScraperError(Exception):
    """Base exception for all gov_exam_scraper errors."""
    pass


class FetchError(ScraperError):
    """Raised when fetching HTML or web content fails."""
    pass


class ParseError(ScraperError):
    """Raised when parsing or extracting exam records via LLM fails."""
    pass


class NotionSyncError(ScraperError):
    """Raised when synchronizing with Notion API fails."""
    pass


class ConfigurationError(ScraperError):
    """Raised when required settings or credentials are missing."""
    pass


class NotificationError(ScraperError):
    """Raised when dispatching alerts fails."""
    pass
