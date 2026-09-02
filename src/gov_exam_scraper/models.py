"""Pydantic v2 domain models, enums, date parsing, and deterministic hashing."""

from datetime import date, datetime
from enum import Enum
import hashlib
import re
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Sector(str, Enum):
    """Government employment sector classification."""
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
        val_str = str(value).upper().strip()
        for member in cls:
            if member.value in val_str:
                return member
        if any(kw in val_str for kw in ["KPSC", "KEA", "KARNATAKA", "STATE", "PSC"]):
            return cls.STATE_PSC
        if any(kw in val_str for kw in ["BANK", "IBPS", "SBI", "RBI"]):
            return cls.BANKING
        if any(kw in val_str for kw in ["RRB", "RAILWAY"]):
            return cls.RAILWAY
        if any(kw in val_str for kw in ["TET", "TEACHER", "PROFESSOR"]):
            return cls.TEACHING
        if any(kw in val_str for kw in ["DEFENCE", "ARMY", "NAVY", "AIR FORCE", "NDA", "CDS"]):
            return cls.DEFENCE
        return cls.OTHER


class ExamStatus(str, Enum):
    """Application status lifecycle."""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    UPCOMING = "UPCOMING"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def _missing_(cls, value: object) -> "ExamStatus":
        val_str = str(value).upper().strip()
        if any(kw in val_str for kw in ["OPEN", "ACTIVE", "APPLY", "ONGOING", "LIVE"]):
            return cls.OPEN
        if any(kw in val_str for kw in ["CLOSE", "OVER", "EXPIRED", "ENDED"]):
            return cls.CLOSED
        if any(kw in val_str for kw in ["SOON", "UPCOMING", "NOTIFIED", "ANNOUNCED"]):
            return cls.UPCOMING
        return cls.UNKNOWN


def parse_flexible_date(value: Any) -> date | None:
    """Parses multi-format Indian government notification dates."""
    if value is None or isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    val_str = str(value).strip()
    if not val_str or val_str.upper() in {"N/A", "TBD", "NONE", "NULL", "-"}:
        return None

    cleaned_str = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", val_str, flags=re.IGNORECASE)

    formats = [
        "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y",
        "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y",
        "%d-%b-%Y", "%d-%B-%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(cleaned_str, fmt).date()
        except ValueError:
            continue
    return None


class ExamRecord(BaseModel):
    """Normalized structured government exam notification record."""
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    exam_name: str = Field(..., min_length=2, max_length=300)
    sector: Sector = Field(default=Sector.OTHER)
    last_date: date | None = Field(default=None)
    eligibility: str = Field(default="Refer notification", max_length=500)
    apply_link: str = Field(..., min_length=5)
    status: ExamStatus = Field(default=ExamStatus.UNKNOWN)
    source_url: str | None = Field(default=None)
    content_hash: str = Field(default="", max_length=64)

    @field_validator("last_date", mode="before")
    @classmethod
    def validate_date(cls, v: Any) -> date | None:
        return parse_flexible_date(v)

    @field_validator("apply_link")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(f"Invalid URL: {v}")
        return v

    def model_post_init(self, __context: Any) -> None:
        if not self.content_hash:
            date_part = self.last_date.isoformat() if self.last_date else "NO_DATE"
            raw_key = f"{self.exam_name.strip().upper()}|{self.sector.value}|{date_part}|{self.apply_link.strip()}|{self.status.value}"
            self.content_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class ScraperSource(BaseModel):
    """Configuration for a target scraping portal."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=2)
    url: str = Field(..., min_length=5)
    sector_hint: Sector = Field(default=Sector.OTHER)
    use_playwright: bool = Field(default=False)
    css_selector: str | None = Field(default=None)
    is_active: bool = Field(default=True)

    @field_validator("url")
    @classmethod
    def validate_source_url(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(f"Invalid source URL: {v}")
        return v


class ExtractionBatch(BaseModel):
    """JSON container schema for Groq structured extraction."""
    exams: list[ExamRecord] = Field(default_factory=list)


class ScraperSettings(BaseSettings):
    """Application settings and API credentials."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: SecretStr = Field(default=SecretStr(""), alias="GROQ_API_KEY")
    groq_model: str = Field(default="qwen/qwen3.6-27b", alias="GROQ_MODEL")
    notion_api_key: SecretStr = Field(default=SecretStr(""), alias="NOTION_API_KEY")
    notion_database_id: str = Field(default="", alias="NOTION_DATABASE_ID")

    # Mobile Alerts (Discord / Telegram)
    discord_webhook_url: SecretStr = Field(default=SecretStr(""), alias="DISCORD_WEBHOOK_URL")
    telegram_bot_token: SecretStr = Field(default=SecretStr(""), alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    cache_ttl_seconds: int = Field(default=3600, alias="CACHE_TTL_SECONDS")
    max_workers: int = Field(default=5, alias="MAX_WORKERS")
    request_timeout_seconds: int = Field(default=60, alias="REQUEST_TIMEOUT_SECONDS")
    playwright_timeout_seconds: int = Field(default=60, alias="PLAYWRIGHT_TIMEOUT_SECONDS")
    max_retries: int = Field(default=3, alias="MAX_RETRIES")
