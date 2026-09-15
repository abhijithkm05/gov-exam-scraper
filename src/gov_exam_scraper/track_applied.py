import os
import re
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_APPLIED_DB_ID = os.getenv("NOTION_APPLIED_DB_ID", "535459a2751646f4906c7c5e03f337ef")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

NOTICE_PATTERN = re.compile(
    r"(time\s*table|exam\s*date|schedule|admit\s*card|hall\s*ticket|cbt|written\s*exam|merit\s*list|shortlist|document\s*verification|selection\s*list|city\s*intimation)",
    re.IGNORECASE,
)

def fetch_html_content(url: str) -> str:
    """Fetch with requests, fallback to Playwright for dynamic boards."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        if resp.status_code == 200 and len(resp.text) > 1000:
            return resp.text
    except Exception as e:
        print(f"  ⚠️ Standard fetch failed for {url}: {e}. Falling back to browser...")

    # Fallback to headless Playwright
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            content = page.content()
            browser.close()
            return content
    except Exception as err:
        print(f"  ❌ Playwright fetch also failed for {url}: {err}")
        return ""

def send_alerts(exam_name: str, notice_title: str, notice_url: str):
    msg = f"🚨 *EXAM ALERT: {exam_name}*\n\n📌 *Notice:* {notice_title}\n🔗 *Link:* {notice_url}"
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
                json={"content": f"🚨 **EXAM ALERT: {exam_name}**\n**Notice:** {notice_title}\n**Link:** {notice_url}"},
                timeout=10,
            )
        except Exception as e:
            print(f"  ⚠️ Discord alert error: {e}")

def get_applied_exams():
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    url = f"https://api.notion.com/v1/databases/{NOTION_APPLIED_DB_ID}/query"
    res = requests.post(url, headers=headers, json={}, timeout=15)
    if res.status_code != 200:
        print(f"❌ Failed to fetch applied exams: {res.text}")
        return []
    
    exams = []
    for row in res.json().get("results", []):
        props = row.get("properties", {})
        title_list = props.get("Exam Name", {}).get("title", [])
        if not title_list:
            continue
        exam_name = title_list[0].get("text", {}).get("content", "")
        notice_url = props.get("Notice Board URL", {}).get("url", "")
        notif_no_list = props.get("Notification No", {}).get("rich_text", [])
        notif_no = notif_no_list[0].get("text", {}).get("content", "") if notif_no_list else ""
        status = props.get("Status", {}).get("select", {}).get("name", "")
        
        if status == "Completed":
            continue

        exams.append({
            "page_id": row["id"],
            "name": exam_name,
            "url": notice_url,
            "notif_no": notif_no,
        })
    return exams

def scan_board_for_exam(exam: dict):
    url = exam.get("url")
    if not url:
        return None
    print(f"🔍 Checking {exam['name']} at {url}...")
    html = fetch_html_content(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    for s in soup(["script", "style", "nav", "footer"]):
        s.decompose()

    # Keywords specific to this exam
    raw_keywords = re.findall(r"\b[A-Za-z0-9]{3,}\b", exam["name"])
    if exam.get("notif_no"):
        raw_keywords.extend(re.findall(r"\b[A-Za-z0-9]{3,}\b", exam["notif_no"]))
    
    ignore = {"AND", "THE", "FOR", "EXAM", "ONLINE", "POST", "RECRUITMENT", "2026", "JULY", "AUGUST"}
    keywords = [k.lower() for k in raw_keywords if k.upper() not in ignore]

    for a in soup.find_all("a"):
        text = a.get_text(separator=" ", strip=True)
        href = a.get("href", "")
        if not text or not href:
            continue

        text_lower = text.lower()
        if NOTICE_PATTERN.search(text_lower):
            # Check if any keyword matches or if authority page is dedicated
            has_kw = any(kw in text_lower for kw in keywords) if keywords else True
            if has_kw or "rrb" in url.lower() or "kpsc" in url.lower():
                full_link = href if href.startswith("http") else requests.compat.urljoin(url, href)
                return {"title": text[:150], "link": full_link}
    return None

def update_notion_status(page_id: str, news: str, link: str = None):
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    from datetime import date
    payload = {
        "properties": {
            "Last Checked": {"date": {"start": date.today().isoformat()}}
        }
    }
    if news:
        payload["properties"]["Latest News"] = {"rich_text": [{"text": {"content": news[:180]}}]}
    if link and ("admit" in news.lower() or "hall" in news.lower()):
        payload["properties"]["Admit Card URL"] = {"url": link}
        payload["properties"]["Status"] = {"select": {"name": "Admit Card Out"}}

    requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=headers, json=payload, timeout=15)

def main():
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    print("🎯 Monitoring Applied Government Exams...")
    exams = get_applied_exams()
    print(f"📋 Found {len(exams)} active exams to check.")
    
    for ex in exams:
        found = scan_board_for_exam(ex)
        if found:
            print(f"  📢 Notice Found: {found['title']} -> {found['link']}")
            send_alerts(ex["name"], found["title"], found["link"])
            update_notion_status(ex["page_id"], found["title"], found["link"])
        else:
            update_notion_status(ex["page_id"], "")
    print("✨ Scan completed across all applied exams.")

if __name__ == "__main__":
    main()
