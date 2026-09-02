"""Alert notification engine for Discord and Telegram."""

import requests
from gov_exam_scraper.models import ExamRecord, ScraperSettings


def send_discord_alert(webhook_url: str, new_records: list[ExamRecord], archived_count: int = 0) -> bool:
    """Sends a rich embed message to a Discord channel webhook."""
    if not webhook_url or not new_records:
        return False

    fields = []
    for exam in new_records[:10]:
        last_date = exam.last_date.isoformat() if exam.last_date else "Open / N/A"
        fields.append({
            "name": f"📌 {exam.exam_name[:80]}",
            "value": f"**Sector:** `{exam.sector.value}` | **Deadline:** `{last_date}`\n[🔗 Apply / Details]({exam.apply_link})",
            "inline": False,
        })

    embed = {
        "title": f"🏛️ {len(new_records)} New Govt Exam Notification(s) Found!",
        "description": f"Automated scan discovered new recruitment notifications.\n"
                       f"• **New Exams Added:** {len(new_records)}\n"
                       f"• **Expired Exams Closed:** {archived_count}",
        "color": 3447003,
        "fields": fields,
        "footer": {"text": "Gov Exam Scraper • Automated Tracker"},
    }

    try:
        resp = requests.post(webhook_url, json={"embeds": [embed]}, timeout=15)
        return resp.status_code in (200, 204)
    except Exception:
        return False


def send_telegram_alert(bot_token: str, chat_id: str, new_records: list[ExamRecord], archived_count: int = 0) -> bool:
    """Sends a Markdown-formatted message to a Telegram chat or channel."""
    if not bot_token or not chat_id or not new_records:
        return False

    lines = [
        f"🏛️ *{len(new_records)} New Govt Exam Notification(s) Found!*",
        f"• *New Added:* `{len(new_records)}` | *Expired Closed:* `{archived_count}`\n",
    ]

    for exam in new_records[:8]:
        last_date = exam.last_date.isoformat() if exam.last_date else "Open / N/A"
        lines.append(f"📌 *{exam.exam_name}*")
        lines.append(f"• Sector: `{exam.sector.value}` | Last Date: `{last_date}`")
        lines.append(f"• [Apply / Details]({exam.apply_link})\n")

    message = "\n".join(lines)
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    try:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True},
            timeout=15,
        )
        return resp.status_code == 200
    except Exception:
        return False


def dispatch_alerts(new_records: list[ExamRecord], archived_count: int = 0, settings: ScraperSettings | None = None) -> dict[str, bool]:
    """Dispatches notifications across configured communication channels."""
    cfg = settings or ScraperSettings()
    results = {}

    discord_url = cfg.discord_webhook_url.get_secret_value()
    if discord_url:
        results["discord"] = send_discord_alert(discord_url, new_records, archived_count)

    tg_token = cfg.telegram_bot_token.get_secret_value()
    tg_chat = cfg.telegram_chat_id
    if tg_token and tg_chat:
        results["telegram"] = send_telegram_alert(tg_token, tg_chat, new_records, archived_count)

    return results
