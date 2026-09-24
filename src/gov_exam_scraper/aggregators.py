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

# The 12 applied exams tracked from syllabus to result
EXAM_MONITORS = [
    {
        "name": "SBI Junior Associates",
        "query": '("SBI Clerk" OR "SBI Junior Associate") (admit card OR exam date OR syllabus OR result OR answer key)',
    },
    {
        "name": "RRB Section Controller (CEN 03/2026)",
        "query": '("RRB Section Controller" OR "CEN 03/2026") (exam date OR admit card OR syllabus OR city intimation)',
    },
    {
        "name": "RRB Junior Engineer (CEN 04/2026)",
        "query": '("RRB JE" OR "CEN 04/2026") (exam date OR admit card OR syllabus OR city intimation)',
    },
    {
        "name": "IBPS RRB XV - Office Assistant",
        "query": '("IBPS RRB Clerk" OR "CRP RRBs XV" OR "IBPS RRB Office Assistant") (exam date OR admit card OR syllabus OR prelims)',
    },
    {
        "name": "IBPS Customer Service Associates",
        "query": '("IBPS Clerk" OR "IBPS CSA") (admit card OR exam date OR syllabus OR prelims)',
    },
    {
        "name": "UPSC EPFO - APFC",
        "query": '("EPFO APFC" OR "APFC") (exam date OR admit card OR syllabus OR notification)',
    },
    {
        "name": "India Post GDS",
        "query": '("India Post GDS" OR "Gramin Dak Sevak") (merit list OR result OR cutoff OR schedule)',
    },
    {
        "name": "HAL Design / Management Trainee",
        "query": '("HAL trainee" OR "HAL recruitment") (exam date OR admit card OR syllabus OR result)',
    },
    {
        "name": "KPSC Gazetted Probationers",
        "query": '("KPSC Gazetted Probationers" OR "KPSC KAS") (exam date OR admit card OR prelims OR syllabus)',
    },
    {
        "name": "KEA VAO & Land Surveyor",
        "query": '("KEA VAO" OR "Karnataka VAO") (exam date OR admit card OR answer key OR syllabus)',
    },
    {
        "name": "KFD Forest Watcher",
        "query": '("Karnataka Forest Watcher" OR "KFD Watcher") (exam date OR merit list OR physical test OR result)',
    },
    {
        "name": "NICL 500 Assistants",
        "query": '("NICL Assistant" OR "NICL recruitment") (exam date OR admit card OR mains OR syllabus)',
    },
]

# Milestone Categories for strict anti-spam deduplication
MILESTONES = {
    "ADMIT_CARD": (
        re.compile(r"\b(admit\s*card|hall\s*ticket|call\s*letter|city\s*intimation)\b", re.IGNORECASE),
        "Admit Card / Call Letter Out"
    ),
    "EXAM_DATE": (
        re.compile(r"\b(exam\s*date|schedule|time\s*table|shift|postponed)\b", re.IGNORECASE),
        "Exam Dates Announced"
    ),
    "SYLLABUS_PATTERN": (
        re.compile(r"\b(syllabus|exam\s*pattern|study\s*material|previous\s*paper)\b", re.IGNORECASE),
        "Syllabus & Pattern Update"
    ),
    "ANSWER_KEY": (
        re.compile(r"\b(answer\s*key|response\s*sheet|objection)\b", re.IGNORECASE),
        "Answer Key Released"
    ),
    "RESULT": (
        re.compile(r"\b(result|merit\s*list|cutoff|cut-off|score\s*card)\b", re.IGNORECASE),
        "Result / Cutoff Declared"
    ),
}

def load_cache():
    if CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return set(data.get("milestones", [])), set(data.get("urls", []))
            elif isinstance(data, list):
                return set(), set(data)
        except Exception:
            pass
    return set(), set()

def save_cache(milestones: set, urls: set):
    payload = {"milestones": list(milestones), "urls": list(urls)}
    CACHE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

def send_consolidated_alert(exam_name: str, updates: list):
    """Sends exactly ONE alert message per exam summarizing all new milestones."""
    lines = [f"🚨 *VERIFIED EXAM UPDATE: {exam_name}*"]
    for up in updates:
        lines.append(f"\n📌 *{up['event_label']}*")
        lines.append(f"📰 {up['title']}")
        lines.append(f"🔗 [Direct Link]({up['link']}) ({up['source']})")

    msg = "\n".join(lines)

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": True},
                timeout=10,
            )
        except Exception as e:
            print(f"  ⚠️ Telegram alert error: {e}")

    if DISCORD_WEBHOOK_URL:
        try:
            discord_lines = [f"🚨 **VERIFIED EXAM UPDATE: {exam_name}**"]
            for up in updates:
                discord_lines.append(f"**{up['event_label']}**: {up['title']}\n🔗 Link: {up['link']}")
            requests.post(DISCORD_WEBHOOK_URL, json={"content": "\n\n".join(discord_lines)}, timeout=10)
        except Exception as e:
            print(f"  ⚠️ Discord alert error: {e}")

def update_notion(exam_name: str, updates: list):
    """Updates Notion with the latest milestone and direct verified link."""
    if not NOTION_API_KEY or not NOTION_APPLIED_DB_ID:
        return
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    try:
        res = requests.post(f"https://api.notion.com/v1/databases/{NOTION_APPLIED_DB_ID}/query", headers=headers, json={}, timeout=15)
        if res.status_code != 200:
            return

        for row in res.json().get("results", []):
            props = row.get("properties", {})
            title_prop = props.get("Exam Name", {}).get("title", [])
            row_title = title_prop[0].get("text", {}).get("content", "") if title_prop else ""

            # Check if row matches the target exam
            first_key = exam_name.split()[0].lower()
            if first_key in row_title.lower():
                latest_up = updates[0]
                payload = {
                    "properties": {
                        "Latest News": {"rich_text": [{"text": {"content": latest_up["title"][:190]}}]}
                    }
                }
                # Update status according to highest milestone
                for up in updates:
                    if up["category"] == "ADMIT_CARD":
                        payload["properties"]["Status"] = {"select": {"name": "Admit Card Out"}}
                        payload["properties"]["Admit Card URL"] = {"url": up["link"]}
                        break
                    elif up["category"] == "EXAM_DATE":
                        payload["properties"]["Status"] = {"select": {"name": "Exam Scheduled"}}
                    elif up["category"] == "RESULT":
                        payload["properties"]["Status"] = {"select": {"name": "Result Out"}}

                requests.patch(f"https://api.notion.com/v1/pages/{row['id']}", headers=headers, json=payload, timeout=10)
                print(f"  ✅ Notion row updated for {row_title}")
                break
    except Exception as e:
        print(f"  ⚠️ Notion update error: {e}")

def fetch_articles(query: str):
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}+when:7d&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            items = []
            for item in root.findall(".//item"):
                title = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                source = item.find("source").text if item.find("source") is not None else "News"
                if title and link:
                    items.append({"title": title, "link": link, "source": source})
            return items
    except Exception:
        pass
    return []

def main():
    print("🔍 Running Verified Anti-Spam Exam Monitor...")
    sent_milestones, sent_urls = load_cache()
    total_notifications = 0

    for monitor in EXAM_MONITORS:
        exam_name = monitor["name"]
        articles = fetch_articles(monitor["query"])
        exam_new_updates = []

        # Find verified milestones for this exam
        for art in articles:
            title = art["title"]
            link = art["link"]

            if link in sent_urls:
                continue

            for cat_key, (pattern, label) in MILESTONES.items():
                if pattern.search(title):
                    milestone_id = f"{exam_name}:{cat_key}"
                    
                    # Only accept if this milestone hasn't been notified yet
                    if milestone_id not in sent_milestones:
                        exam_new_updates.append({
                            "category": cat_key,
                            "event_label": label,
                            "title": title,
                            "link": link,
                            "source": art["source"],
                            "milestone_id": milestone_id
                        })
                        sent_milestones.add(milestone_id)
                        sent_urls.add(link)
                        break

        # If any verified updates occurred, send ONE single message for this exam
        if exam_new_updates:
            print(f"  🎯 New Milestones Found for [{exam_name}]: {len(exam_new_updates)} update(s)")
            send_consolidated_alert(exam_name, exam_new_updates)
            update_notion(exam_name, exam_new_updates)
            total_notifications += 1

    save_cache(sent_milestones, sent_urls)
    print(f"✨ Scan complete. Dispatched {total_notifications} consolidated notification(s). Spam = 0.")

if __name__ == "__main__":
    main()
