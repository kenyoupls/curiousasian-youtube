"""Telegram bot notifications for pipeline alerts."""

import requests
from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def send_telegram(message: str) -> bool:
    """Send a message via Telegram bot.

    Returns True if sent successfully, False otherwise.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  ⚠️  Telegram not configured — skipping notification")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    try:
        response = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
        }, timeout=10)

        if response.status_code == 200:
            print("  📨 Telegram notification sent")
            return True
        else:
            print(f"  ⚠️  Telegram API error: {response.status_code}")
            return False

    except Exception as e:
        print(f"  ⚠️  Telegram send failed: {e}")
        return False


def notify_scripts_low(remaining: int):
    """Alert that the script queue is running low."""
    send_telegram(
        f"⚠️ *CuriousAsian Script Alert*\n\n"
        f"Only *{remaining}* scripts left in the queue!\n\n"
        f"Open Claude and say:\n"
        f"`Write 30 more CuriousAsian scripts`\n\n"
        f"The pipeline is using Gemini backup scripts for now."
    )


def notify_video_complete(title: str, duration: float, source: str):
    """Notify that a video was successfully created."""
    source_label = "Claude" if source == "claude" else "Gemini (backup)"
    send_telegram(
        f"✅ *New Video Ready*\n\n"
        f"📹 _{title}_\n"
        f"⏱ {duration:.0f}s ({duration / 60:.1f} min)\n"
        f"✍️ Script by: {source_label}\n\n"
        f"Upload it to YouTube when ready!"
    )


def notify_pipeline_failed(error: str):
    """Alert that the pipeline failed."""
    send_telegram(
        f"❌ *CuriousAsian Pipeline Failed*\n\n"
        f"Error: `{error[:200]}`\n\n"
        f"Check GitHub Actions logs for details."
    )
