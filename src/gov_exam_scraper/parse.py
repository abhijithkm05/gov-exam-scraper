"""Groq Cloud structured JSON parsing engine for recruitment notifications."""

import json
import logging
import time
from typing import Optional
from groq import Groq

from gov_exam_scraper.exceptions import ParseError
from gov_exam_scraper.models import ExamRecord, ExtractionBatch, ScraperSettings, Sector

logger = logging.getLogger("gov_exam_scraper")

EXTRACTION_SYSTEM_PROMPT = """You are an expert government recruitment analyst.
Analyze the provided government portal text and extract any CURRENT active job/exam notifications.

Output a valid JSON object matching this schema:
{
  "exams": [
    {
      "exam_name": "Full official title of the vacancy or exam",
      "sector": "UPSC, SSC, STATE_PSC, BANKING, RAILWAY, DEFENCE, POLICE, TEACHING, PSU, ENGINEERING, or OTHER",
      "last_date": "YYYY-MM-DD or null",
      "eligibility": "Brief qualifications or null",
      "apply_link": "Direct URL or null",
      "pdf_link": "Direct .pdf link or null",
      "status": "OPEN, CLOSED, or UPCOMING"
    }
  ]
}

CRITICAL RULES:
1. If NO current recruitment notifications are found, you MUST return: {"exams": []}
2. Extract direct links to official notification PDFs into "pdf_link".
3. Return ONLY the JSON object. Do not include markdown codeblocks or conversational text.
"""


class GroqParser:
    """Parses raw cleaned text into validated ExamRecord instances using Groq inference."""

    def __init__(self, settings: Optional[ScraperSettings] = None) -> None:
        self.settings = settings or ScraperSettings()
        api_key = self.settings.groq_api_key.get_secret_value()
        if not api_key:
            raise ParseError("GROQ_API_KEY is missing. Check your .env file.")
        self.client = Groq(api_key=api_key)

    def parse_exams(self, cleaned_text: str, source_url: str = "", sector_hint: Sector = Sector.OTHER) -> list[ExamRecord]:
        """Extracts structured ExamRecord objects with rate-limit retries."""
        if not cleaned_text.strip() or len(cleaned_text.strip()) < 30:
            return []

        user_content = f"Source Portal URL: {source_url}\nSector Hint: {sector_hint.value}\n\nPAGE CONTENT:\n{cleaned_text}"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.settings.groq_model,
                    messages=[
                        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                )
                raw_content = response.choices[0].message.content or '{"exams": []}'
                data = json.loads(raw_content)

                batch = ExtractionBatch.model_validate(data)
                for exam in batch.exams:
                    exam.source_url = source_url
                    if exam.sector == Sector.OTHER and sector_hint != Sector.OTHER:
                        exam.sector = sector_hint
                return batch.exams

            except Exception as exc:
                err_msg = str(exc)
                if "429" in err_msg or "rate_limit" in err_msg.lower():
                    wait_time = (attempt + 1) * 3
                    logger.info(f"Groq TPM pacing: waiting {wait_time}s before retrying {source_url}...")
                    time.sleep(wait_time)
                    continue
                
                logger.warning(f"Groq parsing failed for {source_url}: {exc}")
                return []

        return []
