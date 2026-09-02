"""Notification dispatchers for Discord Webhooks and Telegram Bot."""

import logging
import requests
from gov_exam_scraper.models import ExamRecord, ScraperSettings

logger = logging.getLogger("gov_exam_scraper")


def send_discord_alert(records: list[ExamRecord], webhook_url: str) -> bool:
    """Dispatches new recruitment records to a Discord webhook."""
    if not webhook_url or not records:
        return False

    embeds = []
    for rec in records[:10]:
        deadline = rec.last_date.strftime("%d %b %Y") if rec.last_date else "TBD / Not Specified"
        apply_btn = f"[Apply Now]({rec.apply_link})" if rec.apply_link else "Check Portal"

        fields = [
            {"name": "Sector", "value": f"`{rec.sector.value}`", "inline": True},
            {"name": "Deadline", "value": f"**{deadline}**", "inline": True},
        ]
        if rec.eligibility:
            fields.append({"name": "Eligibility", "value": rec.eligibility[:200], "inline": False})
        fields.append({"name": "Direct Link", "value": apply_btn, "inline": False})

        embed = {
            "title": f"🏛️ {rec.exam_name[:100]}",
            "color": 0x2ECC71 if rec.status.value == "OPEN" else 0x95A5A6,
            "fields": fields,
            "footer": {"text": "Gov Exam Tracker • Cloud Pipeline"},
        }
        embeds.append(embed)

    payload = {
        "content": f"🚨 **{len(records)} New Government Exam Notification(s) Found!**",
        "embeds": embeds,
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=15)
        return resp.status_code in (200, 204)
    except Exception as exc:
        logger.warning(f"Failed to deliver Discord webhook: {exc}")
        return False


def send_telegram_alert(records: list[ExamRecord], bot_token: str, chat_id: str) -> bool:
    """Dispatches new recruitment records to a Telegram chat/channel using HTML format."""
    if not bot_token or not chat_id or not records:
        return False

    header = f"🚨 <b>{len(records)} New Recruitment Notification(s) Detected!</b>\n\n"
    
    body_items = []
    for rec in records[:10]:
        deadline = rec.last_date.strftime("%d %b %Y") if rec.last_date else "TBD / Not Specified"
        apply_url = rec.apply_link or rec.source_url or "https://google.com"
        
        item = (
            f"🏛️ <b>{rec.exam_name}</b>\n"
            f"• <b>Sector:</b> <code>{rec.sector.value}</code>\n"
            f"• <b>Deadline:</b> <b>{deadline}</b>\n"
        )
        if rec.eligibility:
            item += f"• <b>Eligibility:</b> {rec.eligibility[:150]}\n"
        item += f'🔗 <a href="{apply_url}">Apply / Official Notification</a>\n'
        body_items.append(item)

    message_text = header + "\n".join(body_items)
    endpoint = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": message_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(endpoint, json=payload, timeout=15)
        if resp.status_code == 200:
            logger.info("Telegram notification sent successfully.")
            return True
        logger.warning(f"Telegram API responded with code {resp.status_code}: {resp.text}")
        return False
    except Exception as exc:
        logger.warning(f"Failed to dispatch Telegram message: {exc}")
        return False


def dispatch_alerts(records: list[ExamRecord], settings: ScraperSettings) -> dict[str, bool]:
    """Dispatches alerts across all configured channels (Discord and/or Telegram)."""
    results = {}
    if not records:
        return results

    if settings.discord_webhook_url:
        results["discord"] = send_discord_alert(records, settings.discord_webhook_url)

    if settings.telegram_bot_token and settings.telegram_chat_id:
        results["telegram"] = send_telegram_alert(records, settings.telegram_bot_token, settings.telegram_chat_id)

    return results
