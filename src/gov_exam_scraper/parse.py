"""Groq structured extraction engine with fallback JSON parsing."""

import json
import re
from groq import BadRequestError, Groq, RateLimitError
from pydantic import ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from gov_exam_scraper.exceptions import (
    ConfigurationError,
    GroqRateLimitError,
    LLMResponseValidationError,
)
from gov_exam_scraper.models import ExamRecord, ExtractionBatch, ScraperSettings, Sector

SYSTEM_PROMPT = """You are a backend JSON extraction service for Indian government recruitment notifications.
You must output ONLY valid JSON with the exact structure below. Do not include markdown code fences or explanatory text.

{"exams": [{"exam_name": "Official Title", "sector": "STATE_PSC", "last_date": "YYYY-MM-DD", "eligibility": "Brief qualifications", "apply_link": "https://...", "status": "OPEN"}]}

Allowed sector values: UPSC, SSC, STATE_PSC, BANKING, RAILWAY, DEFENCE, POLICE, TEACHING, PSU, ENGINEERING, OTHER.
Allowed status values: OPEN, CLOSED, UPCOMING, UNKNOWN.
If no exams are found, return: {"exams": []}"""


def extract_json_payload(raw_text: str) -> str:
    """Extracts the outermost JSON object substring from raw model output."""
    cleaned = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
    return match.group(1).strip() if match else cleaned


class GroqParser:
    """Extracts structured ExamRecord models using Groq Cloud API."""

    def __init__(self, settings: ScraperSettings | None = None) -> None:
        self.settings = settings or ScraperSettings()
        api_key = self.settings.groq_api_key.get_secret_value()
        if not api_key:
            raise ConfigurationError("GROQ_API_KEY environment variable is required.")
        self.client = Groq(api_key=api_key)

    def parse_exams(
        self,
        cleaned_text: str,
        source_url: str,
        sector_hint: Sector = Sector.OTHER,
    ) -> list[ExamRecord]:
        """Extracts structured exam records from page text."""
        if not cleaned_text or len(cleaned_text.strip()) < 30:
            return []

        content_sample = cleaned_text[:7000]

        user_prompt = (
            f"Portal URL: {source_url}\n"
            f"Sector Hint: {sector_hint.value}\n\n"
            f"Page Content:\n{content_sample}\n\n"
            f"Extract all recruitment notifications in JSON format."
        )

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.settings.max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=8),
            retry=retry_if_exception_type(RateLimitError),
        )
        def _call_groq() -> str:
            # 1. Primary extraction with json_object enforcement
            try:
                response = self.client.chat.completions.create(
                    model=self.settings.groq_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=4096,
                )
                return response.choices[0].message.content or '{"exams": []}'
            except BadRequestError as e:
                # 2. Resilient fallback if json_validate_failed is triggered
                if "json_validate_failed" in str(e):
                    fallback_response = self.client.chat.completions.create(
                        model=self.settings.groq_model,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.1,
                        max_tokens=4096,
                    )
                    return fallback_response.choices[0].message.content or '{"exams": []}'
                raise
            except RateLimitError as e:
                raise GroqRateLimitError(str(e)) from e

        raw_output = _call_groq()
        json_str = extract_json_payload(raw_output)

        try:
            payload = json.loads(json_str)
            batch = ExtractionBatch.model_validate(payload)
            for exam in batch.exams:
                if not exam.source_url:
                    exam.source_url = source_url
            return batch.exams
        except (json.JSONDecodeError, ValidationError) as e:
            raise LLMResponseValidationError(f"Invalid JSON from Groq: {e}\nRaw: {raw_output[:250]}") from e
