import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

CACHE_FILE = Path("data/sent_alerts.json")
CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Strict match rules: ONLY your 11 applied exams
APPLIED_EXAM_PATTERNS = {
    "RRB Section Controller (CEN 03/2026)": [
        r"\bsection\s*controller\b",
        r"\bcen\s*03/2026\b",
        r"\brrb\b.*\bsection\s*controller\b",
    ],
    "RRB Junior Engineer (CEN 04/2026)": [
        r"\brrb\s*je\b",
        r"\brrb\s*junior\s*engineer\b",
        r"\bcen\s*04/2026\b",
    ],
    "HAL Design / Management Trainee": [
        r"\bhal\s*(?:design|management)?\s*trainee\b",
        r"\bhindustan\s*aeronautics\b.*\btrainee\b",
    ],
    "UPSC EPFO - APFC": [
        r"\bepfo\s*apfc\b",
        r"\bapfc\b",
        r"\bassistant\s*provident\s*fund\s*commissioner\b",
        r"\bepfo\b.*\b52/2026\b",
    ],
    "India Post GDS": [
        r"\bgramin\s*dak\s*sevak\b",
        r"\bgds\b.*\b(?:schedule\s*ii|merit\s*list|result|cutoff|2026)\b",
        r"\bindia\s*post\s*gds\b",
    ],
    "KPSC Gazetted Probationers": [
        r"\bkpsc\b.*\b(?:gazetted|probationer|kas)\b",
        r"\bgazetted\s*probationers?\b",
    ],
    "KEA VAO & Land Surveyor": [
        r"\bkea\b.*\b(?:vao|village\s*administrative|land\s*surveyor)\b",
        r"\bvillage\s*administrative\s*officer\b",
    ],
    "KFD Forest Watcher": [
        r"\bkfd\b.*\bforest\s*watcher\b",
        r"\bkarnataka\s*forest\b.*\bwatcher\b",
    ],
    "SBI Junior Associates": [
        r"\bsbi\s*clerk\b",
        r"\bsbi\s*ja\b",
        r"\bsbi\s*junior\s*associate\b",
    ],
    "IBPS Customer Service Associates (Clerk)": [
        r"\bibps\s*clerk\b",
        r"\bibps\s*csa\b",
        r"\bcustomer\s*service\s*associate\b",
    ],
    "NICL 500 Assistants": [
        r"\bnicl\b.*\b(?:assistant|mains)\b",
    ],
}

# Captures everything relevant: dates, syllabus, notes, papers, patterns, cutoffs, results
TOPIC_PATTERN = re.compile(
    r"(date|exam\s*date|admit\s*card|hall\s*ticket|schedule|cbt|syllabus|notes|"
    r"pattern|exam\s*pattern|previous\s*year|paper|study\s*material|cut\s*off|cutoff|"
    r"result|merit\s*list|shortlist|analysis|preparation|strategy|answer\s*key|city\s*intimation)",
    re.IGNORECASE
)

def load_sent_cache() -> set:
    if CACHE_FILE.exists():
        try:
            return set(json.loads(CACHE_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()

def save_sent_cache(sent_urls: set):
    CACHE_FILE.write_text(json.dumps(list(sent_urls), indent=2), encoding="utf-8")

def send_alert(title: str, link: str, source: str, matched_exam: str):
    msg = (
        f"🎯 *UPDATE FOR YOUR EXAM*\n"
        f"📌 *Exam:* {matched_exam}\n"
        f"📢 *Headline:* {title}\n"
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
                json={"content": f"🎯 **UPDATE FOR YOUR EXAM: {matched_exam}**\n**Headline:** {title}\n**Source:** {source}\n**Link:** {link}"},
                timeout=10,
            )
        except Exception as e:
            print(f"  ⚠️ Discord alert error: {e}")

def scrape_articles():
    articles = []
    
    # 1. Testbook
    for p in range(1, 3):
        url = "https://testbook.com/news/" if p == 1 else f"https://testbook.com/news/page/{p}/"
        try:
            r = requests.get(url, headers=HEADERS, timeout=12)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    text = a.get_text(strip=True)
                    href = a["href"]
                    if len(text) > 15 and "/news/" in href:
                        full_link = href if href.startswith("http") else f"https://testbook.com{href}"
                        articles.append({"title": text, "link": full_link, "source": "Testbook"})
        except Exception:
            pass

    # 2. Adda247
    for p in range(1, 3):
        url = "https://www.adda247.com/exams/" if p == 1 else f"https://www.adda247.com/exams/page/{p}/"
        try:
            r = requests.get(url, headers=HEADERS, timeout=12)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    text = a.get_text(strip=True)
                    href = a["href"]
                    if len(text) > 20 and "/exams/" in href:
                        full_link = href if href.startswith("http") else f"https://www.adda247.com{href}"
                        articles.append({"title": text, "link": full_link, "source": "Adda247"})
        except Exception:
            pass

    # 3. Oliveboard
    try:
        r = requests.get("https://www.oliveboard.in/blog/", headers=HEADERS, timeout=12)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                href = a["href"]
                if len(text) > 20 and "/blog/" in href:
                    full_link = href if href.startswith("http") else f"https://www.oliveboard.in{href}"
                    articles.append({"title": text, "link": full_link, "source": "Oliveboard"})
    except Exception:
        pass

    return articles

def main():
    print("🔍 Scanning aggregators strictly for your 11 applied exams...")
    sent_urls = load_sent_cache()
    articles = scrape_articles()
    
    seen_in_batch = set()
    matches_sent = 0

    for art in articles:
        link = art["link"]
        if link in sent_urls or link in seen_in_batch:
            continue
        seen_in_batch.add(link)

        title = art["title"]
        title_lower = title.lower()

        # Must be about one of your exams
        matched_exam = None
        for exam_label, patterns in APPLIED_EXAM_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, title_lower):
                    matched_exam = exam_label
                    break
            if matched_exam:
                break

        if not matched_exam:
            continue

        # Must be relevant (dates, notes, syllabus, cutoff, result, admit card, etc.)
        if TOPIC_PATTERN.search(title_lower):
            print(f"  🎯 High-Value Match: [{matched_exam}] {title}")
            send_alert(title, link, art["source"], matched_exam)
            sent_urls.add(link)
            matches_sent += 1

    save_sent_cache(sent_urls)
    print(f"✨ Scan complete. Dispatched {matches_sent} relevant notifications. Zero spam.")

if __name__ == "__main__":
    main()
