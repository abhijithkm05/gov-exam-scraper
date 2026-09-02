"""Notification dispatchers for Discord Webhooks and Telegram Bot."""

import logging
from typing import Optional
import requests
from gov_exam_scraper.models import ExamRecord, ScraperSettings

logger = logging.getLogger("gov_exam_scraper")


def send_discord_alert(records: list[ExamRecord], webhook_url: str, archived_count: int = 0) -> bool:
    """Dispatches new recruitment records to a Discord webhook."""
    if not webhook_url or not records:
        return False

    embeds = []
    for rec in records[:10]:
        deadline = rec.last_date.strftime("%d %b %Y") if rec.last_date else "Open / Ongoing"

        action_links = []
        if rec.apply_link:
            action_links.append(f"[Apply Online]({rec.apply_link})")
        if rec.pdf_link:
            action_links.append(f"[📄 Official PDF Notification]({rec.pdf_link})")
        links_display = " • ".join(action_links) if action_links else f"[Official Portal]({rec.source_url})"

        fields = [
            {"name": "Sector", "value": f"`{rec.sector.value}`", "inline": True},
            {"name": "Deadline", "value": f"**{deadline}**", "inline": True},
        ]
        if rec.eligibility:
            fields.append({"name": "Eligibility", "value": rec.eligibility[:200], "inline": False})
        fields.append({"name": "Links", "value": links_display, "inline": False})

        embed = {
            "title": f"🏛️ {rec.exam_name[:100]}",
            "color": 0x2ECC71 if rec.status.value == "OPEN" else 0x95A5A6,
            "fields": fields,
            "footer": {"text": f"Gov Exam Tracker • Direct PDF Alert{' • ' + str(archived_count) + ' expired archived' if archived_count else ''}"},
        }
        embeds.append(embed)

    payload = {
        "content": f"🚨 **{len(records)} New Government Recruitment Notification(s) Found!**",
        "embeds": embeds,
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=15)
        return resp.status_code in (200, 204)
    except Exception as exc:
        logger.warning(f"Failed to deliver Discord webhook: {exc}")
        return False


def send_telegram_alert(records: list[ExamRecord], bot_token: str, chat_id: str, archived_count: int = 0) -> bool:
    """Dispatches new recruitment records to a Telegram chat/channel using HTML format."""
    if not bot_token or not chat_id or not records:
        return False

    header = f"🚨 <b>{len(records)} New Recruitment Notification(s) Detected!</b>\n\n"
    body_items = []

    for rec in records[:10]:
        deadline = rec.last_date.strftime("%d %b %Y") if rec.last_date else "Open / Ongoing"
        
        item = (
            f"🏛️ <b>{rec.exam_name}</b>\n"
            f"• <b>Sector:</b> <code>{rec.sector.value}</code>\n"
            f"• <b>Deadline:</b> <b>{deadline}</b>\n"
        )
        if rec.eligibility:
            item += f"• <b>Eligibility:</b> {rec.eligibility[:150]}\n"
        
        if rec.pdf_link:
            item += f'📄 <a href="{rec.pdf_link}"><b>Download Official Notification (PDF)</b></a>\n'
        if rec.apply_link and rec.apply_link != rec.pdf_link:
            item += f'🔗 <a href="{rec.apply_link}">Online Application Portal</a>\n'
        elif not rec.pdf_link and rec.source_url:
            item += f'🔗 <a href="{rec.source_url}">Official Portal Link</a>\n'

        body_items.append(item)

    if archived_count > 0:
        body_items.append(f"\n📦 <i>Archived {archived_count} expired listing(s) in database.</i>")

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
        return resp.status_code == 200
    except Exception as exc:
        logger.warning(f"Failed to dispatch Telegram message: {exc}")
        return False


def dispatch_alerts(
    records: list[ExamRecord],
    settings: Optional[ScraperSettings] = None,
    archived_count: int = 0,
    **kwargs,
) -> dict[str, bool]:
    """Dispatches alerts across Discord and Telegram."""
    results = {}
    if not records:
        return results

    active_settings = settings or ScraperSettings()

    if active_settings.discord_webhook_url:
        results["discord"] = send_discord_alert(records, active_settings.discord_webhook_url, archived_count=archived_count)

    if active_settings.telegram_bot_token and active_settings.telegram_chat_id:
        results["telegram"] = send_telegram_alert(
            records, active_settings.telegram_bot_token, active_settings.telegram_chat_id, archived_count=archived_count
        )

    return results
