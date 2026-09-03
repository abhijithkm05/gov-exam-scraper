"""Targeted exam date and admit card tracker for applied government vacancies."""

import logging
import os
import re
from datetime import date
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import requests

from gov_exam_scraper.fetch import ContentFetcher
from gov_exam_scraper.models import ScraperSettings
from gov_exam_scraper.notify import send_discord_alert, send_telegram_alert

logger = logging.getLogger("gov_exam_scraper")

KEYWORDS_TIMETABLE = re.compile(
    r"(time\s*table|exam\s*date|schedule|admit\s*card|hall\s*ticket|cbt|written\s*exam|examination\s*notice|merit\s*list)",
    re.IGNORECASE,
)


def get_applied_exams(api_key: str, db_id: str) -> list[dict]:
    """Retrieves all applied exams from the Notion tracker database."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    resp = requests.post(url, headers=headers, json={"page_size": 50}, timeout=30)
    if resp.status_code != 200:
        print(f"❌ Failed to query applied Notion DB [Status {resp.status_code}]: {resp.text}")
        return []

    exams = []
    for item in resp.json().get("results", []):
        props = item.get("properties", {})

        name_list = props.get("Exam Name", {}).get("title", [])
        name = name_list[0]["text"]["content"] if name_list else "Unknown Exam"

        authority_sel = props.get("Authority", {}).get("select")
        authority = authority_sel.get("name", "OTHER") if authority_sel else "OTHER"

        advt_list = props.get("Notification No", {}).get("rich_text", [])
        advt = advt_list[0]["text"]["content"] if advt_list else ""

        notice_url = props.get("Notice Board URL", {}).get("url") or ""
        exam_date_prop = props.get("Exam Date", {}).get("date")
        exam_date_val = exam_date_prop.get("start") if exam_date_prop else None

        exams.append({
            "page_id": item["id"],
            "name": name,
            "authority": authority,
            "advt": advt,
            "notice_url": notice_url,
            "exam_date": exam_date_val,
        })
    return exams


def scan_notice_board(fetcher: ContentFetcher, notice_url: str, exam_name: str, advt_no: str) -> list[dict]:
    """Scans the board's notice page for circulars matching the target exam."""
    if not notice_url:
        return []

    try:
        html = fetcher.fetch(notice_url)
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "svg"]):
            tag.decompose()

        clean_name = re.sub(r"\(.*?\)", "", exam_name).lower()
        search_terms = [t for t in clean_name.split() if len(t) > 3][:4]

        matches = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(separator=" ", strip=True)
            if len(text) < 10:
                continue

            href = a["href"].strip()
            abs_url = urljoin(notice_url, href)

            term_match = any(term in text.lower() for term in search_terms) or (advt_no and advt_no.lower() in text.lower())
            event_match = KEYWORDS_TIMETABLE.search(text) is not None

            if term_match and event_match:
                matches.append({"title": text[:150], "url": abs_url})

        return matches
    except Exception as exc:
        print(f"   ⚠️ Could not fetch notices at {notice_url}: {exc}")
        return []


def update_notion_applied_page(api_key: str, page_id: str, latest_news: str, admit_url: str | None = None) -> bool:
    """Updates the Notion row with the latest discovered circular and timestamp."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    today_iso = date.today().isoformat()
    props = {
        "Latest News": {"rich_text": [{"text": {"content": latest_news[:300]}}]},
        "Last Checked": {"date": {"start": today_iso}},
    }
    if admit_url:
        props["Admit Card URL"] = {"url": admit_url}
        props["Status"] = {"select": {"name": "Admit Card Out"}}

    resp = requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=headers, json={"properties": props}, timeout=30)
    return resp.status_code == 200


def run_applied_tracker() -> list[dict]:
    """Runs the applied exams check across all entries and updates Notion."""
    settings = ScraperSettings()
    api_key = settings.notion_api_key.get_secret_value()
    db_id = os.getenv("NOTION_APPLIED_DB_ID", "535459a2751646f4906c7c5e03f337ef")

    fetcher = ContentFetcher(settings=settings)
    applied_list = get_applied_exams(api_key, db_id)

    print(f"\n🎯 Monitoring {len(applied_list)} Applied Government Exams...")
    discovered_updates = []

    for exam in applied_list:
        print(f"\n🔍 Checking: {exam['name'][:45]} ({exam['authority']})")
        updates = scan_notice_board(fetcher, exam["notice_url"], exam["name"], exam["advt"])

        if updates:
            latest = updates[0]
            print(f"   🔔 Found Update: {latest['title']}")
            is_admit = "admit" in latest["title"].lower() or "hall ticket" in latest["title"].lower()
            admit_link = latest["url"] if is_admit else None

            update_notion_applied_page(api_key, exam["page_id"], latest["title"], admit_link)
            discovered_updates.append({"exam": exam["name"], "title": latest["title"], "link": latest["url"]})
        else:
            status_msg = f"No new schedule notice as of {date.today().strftime('%d %b %Y')}"
            update_notion_applied_page(api_key, exam["page_id"], status_msg)
            print(f"   ✅ Up to date. {status_msg}")

    print("\n" + "=" * 80)
    print(f"✨ Notice scan completed across all applied exams.")
    print("=" * 80)
    return discovered_updates


if __name__ == "__main__":
    run_applied_tracker()
