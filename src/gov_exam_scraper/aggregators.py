import os
import re
import json
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_APPLIED_DB_ID = os.getenv("NOTION_APPLIED_DB_ID", "535459a2751646f4906c7c5e03f337ef")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

CACHE_FILE = Path("data/sent_alerts.json")
CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}

SEARCH_TARGETS = [
    {"name": "SBI Junior Associates", "query": "SBI Clerk OR SBI Junior Associate (admit card OR exam date)"},
    {"name": "RRB Section Controller (CEN 03/2026)", "query": "RRB Section Controller CEN 03/2026 (admit card OR exam date)"},
    {"name": "RRB Junior Engineer (CEN 04/2026)", "query": "RRB JE CEN 04/2026 (admit card OR exam date)"},
    {"name": "IBPS RRB XV - Office Assistant", "query": "IBPS RRB Clerk OR Office Assistant (admit card OR exam date)"},
    {"name": "IBPS Customer Service Associates", "query": "IBPS Clerk OR CSA (admit card OR exam date)"},
    {"name": "UPSC EPFO - APFC", "query": "EPFO APFC exam date OR admit card"},
    {"name": "India Post GDS", "query": "India Post GDS merit list OR result"},
    {"name": "HAL Design / Management Trainee", "query": "HAL trainee exam date OR admit card"},
    {"name": "KPSC Gazetted Probationers", "query": "KPSC Gazetted Probationers exam date OR admit card"},
    {"name": "KEA VAO & Land Surveyor", "query": "KEA VAO exam date OR admit card"},
    {"name": "KFD Forest Watcher", "query": "Karnataka Forest Watcher exam date"},
    {"name": "NICL 500 Assistants", "query": "NICL Assistant exam date OR admit card"},
]

CRITICAL_KEYWORDS = re.compile(
    r"(admit\s*card|hall\s*ticket|exam\s*date|schedule|call\s*letter|city\s*intimation|merit\s*list|result\s*out)",
    re.IGNORECASE
)

def load_cache() -> set:
    if CACHE_FILE.exists():
        try:
            return set(json.loads(CACHE_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()

def save_cache(cache: set):
    CACHE_FILE.write_text(json.dumps(list(cache), indent=2), encoding="utf-8")

def send_alert(title: str, link: str, exam_name: str, source: str = "Live Feed"):
    msg = (
        f"🚨 *CRITICAL EXAM ALERT: {exam_name}*\n\n"
        f"📌 *Notice:* {title}\n"
        f"🌐 *Source:* {source}\n"
        f"🔗 *Link:* {link}"
    )

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
                timeout=10,
            )
        except Exception as e:
            print(f"  ⚠️ Telegram alert error: {e}")

    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(
                DISCORD_WEBHOOK_URL,
                json={"content": f"🚨 **CRITICAL EXAM ALERT: {exam_name}**\n**Notice:** {title}\n**Link:** {link}"},
                timeout=10,
            )
        except Exception as e:
            print(f"  ⚠️ Discord alert error: {e}")

def update_notion_entry(exam_name: str, notice_title: str, link: str):
    if not NOTION_API_KEY or not NOTION_APPLIED_DB_ID:
        return
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    try:
        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_APPLIED_DB_ID}/query",
            headers=headers,
            json={},
            timeout=15,
        )
        if res.status_code != 200:
            return

        for row in res.json().get("results", []):
            props = row.get("properties", {})
            title_prop = props.get("Exam Name", {}).get("title", [])
            row_title = title_prop[0].get("text", {}).get("content", "") if title_prop else ""
            
            first_key = exam_name.split()[0].lower()
            if first_key in row_title.lower():
                payload = {
                    "properties": {
                        "Latest News": {"rich_text": [{"text": {"content": notice_title[:190]}}]},
                    }
                }
                if any(w in notice_title.lower() for w in ["admit card", "hall ticket", "call letter"]):
                    payload["properties"]["Status"] = {"select": {"name": "Admit Card Out"}}
                    if link:
                        payload["properties"]["Admit Card URL"] = {"url": link}
                elif any(w in notice_title.lower() for w in ["exam date", "schedule"]):
                    payload["properties"]["Status"] = {"select": {"name": "Exam Scheduled"}}

                patch_res = requests.patch(f"https://api.notion.com/v1/pages/{row['id']}", headers=headers, json=payload, timeout=10)
                if patch_res.status_code == 200:
                    print(f"  ✅ Notion successfully updated for {row_title}!")
                break
    except Exception as e:
        print(f"  ⚠️ Notion update error: {e}")

def fetch_rss_feed(query: str):
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}+when:7d&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            items = []
            for item in root.findall(".//item"):
                title = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                source = item.find("source").text if item.find("source") is not None else "Google News"
                if title and link:
                    items.append({"title": title, "link": link, "source": source})
            return items
    except Exception as e:
        print(f"  ⚠️ RSS fetch error: {e}")
    return []

def main():
    print("🚀 Scanning Feeds across all 12 applied exams...")
    cache = load_cache()
    alerts_fired = 0

    for target in SEARCH_TARGETS:
        exam_name = target["name"]
        print(f"🔎 Checking {exam_name}...")
        articles = fetch_rss_feed(target["query"])

        for art in articles:
            title = art["title"]
            link = art["link"]

            if link in cache:
                continue

            if CRITICAL_KEYWORDS.search(title):
                print(f"  🔥 MATCH DETECTED: [{exam_name}] {title}")
                send_alert(title, link, exam_name, source=art["source"])
                update_notion_entry(exam_name, title, link)
                cache.add(link)
                alerts_fired += 1

    save_cache(cache)
    print(f"✨ Scan completed. Sent {alerts_fired} critical alerts and synced to Notion.")

if __name__ == "__main__":
    main()
