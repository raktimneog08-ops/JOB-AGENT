"""
Slack notification module for the job aggregation agent.
Sends formatted messages with run summary, per-platform breakdowns,
and top matches via Slack webhook.
"""

import json
import time
from datetime import datetime
from typing import Dict, List, Optional

import requests

from utils.logger import get_logger

logger = get_logger()

# Maximum message length for Slack blocks text
MAX_TEXT_LENGTH = 3000


def truncate_text(text: str, max_length: int = MAX_TEXT_LENGTH) -> str:
    """Truncate text to fit Slack message limits."""
    if len(text) > max_length:
        return text[:max_length - 3] + "..."
    return text


def send_slack_notification(
    webhook_url: str,
    platform_counts: Dict[str, int],
    duplicates_removed: int,
    top_matches: List[Dict],
    new_entries_total: int,
    total_unique: int,
    duration_seconds: float,
    status: str = "✅ Success",
) -> bool:
    """
    Send a formatted Slack notification about the job agent run.

    Args:
        webhook_url: Slack incoming webhook URL
        platform_counts: Dict mapping platform name to new jobs found
        duplicates_removed: Number of duplicates identified and removed
        top_matches: List of dicts with top matching jobs
        new_entries_total: Total new entries added to CSV
        total_unique: Total unique jobs in storage
        duration_seconds: Run duration in seconds
        status: Status message (e.g., "✅ Success", "⚠️ Partial")

    Returns:
        True if notification sent successfully
    """
    if not webhook_url:
        logger.warning("No Slack webhook URL configured. Skipping notification.", module="Notifier")
        return False

    try:
        # Build message blocks
        blocks = _build_message_blocks(
            platform_counts=platform_counts,
            duplicates_removed=duplicates_removed,
            top_matches=top_matches,
            new_entries_total=new_entries_total,
            total_unique=total_unique,
            duration_seconds=duration_seconds,
            status=status,
        )

        payload = {
            "text": f"📊 Job Agent Run Complete — {datetime.now().strftime('%b %d, %Y')}",
            "blocks": blocks,
            "username": "Job Agent",
            "icon_emoji": ":robot_face:",
        }

        resp = requests.post(
            webhook_url,
            json=payload,
            timeout=15,
            headers={"Content-Type": "application/json"},
        )

        if resp.status_code == 200:
            logger.info("Slack notification sent successfully", module="Notifier")
            return True
        else:
            logger.warning(
                f"Slack webhook returned {resp.status_code}: {resp.text[:200]}",
                module="Notifier",
            )
            return False

    except requests.exceptions.RequestException as ex:
        logger.warning(f"Failed to send Slack notification: {ex}", module="Notifier")
        return False
    except Exception as ex:
        logger.warning(f"Unexpected error sending Slack notification: {ex}", module="Notifier")
        return False


def _build_message_blocks(
    platform_counts: Dict[str, int],
    duplicates_removed: int,
    top_matches: List[Dict],
    new_entries_total: int,
    total_unique: int,
    duration_seconds: float,
    status: str,
) -> List[Dict]:
    """Build Slack Block Kit message blocks."""

    blocks = []

    # Header
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"📊 Job Agent Run Complete — {datetime.now().strftime('%b %d, %Y')}",
            "emoji": True,
        },
    })

    # Divider
    blocks.append({"type": "divider"})

    # Status + Duration
    duration_str = _format_duration(duration_seconds)
    blocks.append({
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": f"*Status:*\n{status}"},
            {"type": "mrkdwn", "text": f"*Duration:*\n{duration_str}"},
        ],
    })

    # Results breakdown by platform
    platform_text = ""
    platform_emoji = {
        "Naukri": "🇮🇳",
        "RemoteOK": "🌍",
        "WellFound": "🚀",
    }
    
    for platform, count in sorted(platform_counts.items(), key=lambda x: x[1], reverse=True):
        emoji = platform_emoji.get(platform, "📋")
        platform_text += f"{emoji} *{platform}*: {count} new\n"

    if not platform_text:
        platform_text = "No jobs found"

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*📈 Results Breakdown:*\n{platform_text}",
        },
    })

    # Summary stats
    blocks.append({
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": f"*🆕 New Entries Added:*\n{new_entries_total}"},
            {"type": "mrkdwn", "text": f"*🔄 Duplicates Removed:*\n{duplicates_removed}"},
            {"type": "mrkdwn", "text": f"*📁 Total Unique Listings:*\n{total_unique}"},
        ],
    })

    # Top 5 matches
    if top_matches:
        blocks.append({"type": "divider"})
        
        top_text = ""
        for i, match in enumerate(top_matches, 1):
            title = match.get("title", "Unknown")
            company = match.get("company", "Unknown")
            source = match.get("source", "")
            url = match.get("url", "")
            score = match.get("score", 0)

            # Truncate long titles
            if len(title) > 50:
                title = title[:47] + "..."

            if url:
                top_text += f"{i}. <{url}|*{title}*> @ {company} [{source}] — Score: {score}\n"
            else:
                top_text += f"{i}. *{title}* @ {company} [{source}] — Score: {score}\n"

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*⭐ Top Matches:*\n{truncate_text(top_text, 2500)}",
            },
        })

    # Footer with timestamp
    blocks.append({"type": "context", "elements": [
        {"type": "mrkdwn", "text": f"🕐 Run completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"}
    ]})

    return blocks


def _format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    
    if minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def send_error_notification(webhook_url: str, error_message: str) -> bool:
    """
    Send an error notification to Slack when the job agent fails.

    Args:
        webhook_url: Slack incoming webhook URL
        error_message: Description of the error

    Returns:
        True if notification sent successfully
    """
    if not webhook_url:
        return False

    try:
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🚨 Job Agent Run Failed",
                    "emoji": True,
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Error:*\n{truncate_text(error_message, 2000)}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"🕐 Failed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
                ],
            },
        ]

        payload = {
            "text": "🚨 Job Agent Run Failed",
            "blocks": blocks,
            "username": "Job Agent",
            "icon_emoji": ":robot_face:",
        }

        resp = requests.post(webhook_url, json=payload, timeout=15)
        return resp.status_code == 200

    except Exception as ex:
        logger.warning(f"Failed to send error notification: {ex}", module="Notifier")
        return False