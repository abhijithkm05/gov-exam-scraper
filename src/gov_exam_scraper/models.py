"""Domain models, validation schemas, and configuration for gov_exam_scraper."""

from datetime import date, datetime
from enum import Enum
import hashlib
import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Sector(str, Enum):
    UPSC = "UPSC"
    SSC = "SSC"
    STATE_PSC = "STATE_PSC"
    BANKING = "BANKING"
    RAILWAY = "RAILWAY"
    DEFENCE = "DEFENCE"
    POLICE = "POLICE"
    TEACHING = "TEACHING"
    PSU = "PSU"
    ENGINEERING = "ENGINEERING"
    OTHER = "OTHER"

    @classmethod
    def _missing_(cls, value: object) -> "Sector":
        val_str = str(value).upper()
        for member in cls:
            if member.value in val_str:
                return member
        return cls.OTHER


class ExamStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    UPCOMING = "UPCOMING"
    UNKNOWN = "UNKNOWN"


def parse_flexible_date(value: Optional[str]) -> Optional[date]:
    if not value or value.strip().lower() in ("", "none", "null", "n/a", "tbd"):
        return None
    cleaned = value.strip()
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("/", "-").replace(".", "-")

    date_formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%d-%B-%Y",
        "%d-%b-%Y",
        "%B-%d-%Y",
        "%b-%d-%Y",
        "%d %B %Y",
        "%d %b %Y",
    ]
    for fmt in date_formats:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


class ExamRecord(BaseModel):
    exam_name: str = Field(..., min_length=2, max_length=300)
    sector: Sector = Sector.OTHER
    last_date: Optional[date] = None
    eligibility: Optional[str] = Field(default=None, max_length=500)
    apply_link: Optional[str] = None
    status: ExamStatus = ExamStatus.OPEN
    source_url: Optional[str] = None
    content_hash: str = Field(default="", description="Deterministic SHA-256 fingerprint")

    def model_post_init(self, __context: object) -> None:
        if not self.content_hash:
            normalized_components = [
                self.exam_name.strip().lower(),
                self.sector.value,
                self.last_date.isoformat() if self.last_date else "no_date",
                str(self.apply_link or "").strip().lower(),
                self.status.value,
            ]
            raw_string = "|".join(normalized_components)
            self.content_hash = hashlib.sha256(raw_string.encode("utf-8")).hexdigest()

    @field_validator("last_date", mode="before")
    @classmethod
    def validate_last_date(cls, v: object) -> Optional[date]:
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            return parse_flexible_date(v)
        return None


class ExtractionBatch(BaseModel):
    exams: list[ExamRecord] = Field(default_factory=list)


class ScraperSource(BaseModel):
    name: str
    url: str
    sector_hint: Sector = Sector.OTHER
    use_playwright: bool = False
    css_selector: Optional[str] = None
    is_active: bool = True


class SecretString(str):
    """String wrapper ensuring compatibility whether treated as str or SecretStr."""
    def get_secret_value(self) -> str:
        return str(self)


class ScraperSettings(BaseSettings):
    groq_api_key: SecretString = Field(default=SecretString(""), alias="GROQ_API_KEY")
    groq_model: str = Field(default="qwen/qwen3.6-27b", alias="GROQ_MODEL")
    notion_api_key: SecretString = Field(default=SecretString(""), alias="NOTION_API_KEY")
    notion_database_id: str = Field(default="", alias="NOTION_DATABASE_ID")
    discord_webhook_url: Optional[str] = Field(default=None, alias="DISCORD_WEBHOOK_URL")
    telegram_bot_token: Optional[str] = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(default=None, alias="TELEGRAM_CHAT_ID")
    cache_ttl_seconds: int = Field(default=3600, alias="CACHE_TTL_SECONDS")
    max_workers: int = Field(default=5, alias="MAX_WORKERS")
    request_timeout_seconds: int = Field(default=60, alias="REQUEST_TIMEOUT_SECONDS")
    playwright_timeout_seconds: int = Field(default=60, alias="PLAYWRIGHT_TIMEOUT_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("groq_api_key", "notion_api_key", mode="before")
    @classmethod
    def coerce_secret(cls, v: object) -> SecretString:
        if hasattr(v, "get_secret_value"):
            return SecretString(v.get_secret_value())
        return SecretString(str(v or ""))
