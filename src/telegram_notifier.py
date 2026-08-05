"""Telegram bot — send videos, thumbnails, and alerts to @Curious_Asian_Bot.

Sends the actual video file + thumbnail + metadata directly to Telegram.
No more downloading from GitHub — everything arrives in chat.
"""

import requests
from pathlib import Path
from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


TELEGRAM_API = "https://api.telegram.org/bot{token}"


def _api_url(method: str) -> str:
    return f"{TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN)}/{method}"


def _is_configured() -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  ⚠️  Telegram not configured — skipping notification")
        return False
    return True


def send_message(text: str, parse_mode: str = "Markdown") -> bool:
    """Send a text message."""
    if not _is_configured():
        return False
    try:
        resp = requests.post(_api_url("sendMessage"), json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
        }, timeout=15)
        if resp.status_code == 200:
            print("  📨 Telegram message sent")
            return True
        print(f"  ⚠️  Telegram API: {resp.status_code} {resp.text[:100]}")
        return False
    except Exception as e:
        print(f"  ⚠️  Telegram send failed: {e}")
        return False


def send_photo(photo_path: Path, caption: str = "") -> bool:
    """Send a photo (thumbnail)."""
    if not _is_configured():
        return False
    try:
        with open(photo_path, "rb") as f:
            resp = requests.post(
                _api_url("sendPhoto"),
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "caption": caption,
                    "parse_mode": "Markdown",
                },
                files={"photo": f},
                timeout=30,
            )
        if resp.status_code == 200:
            print("  📨 Telegram photo sent")
            return True
        print(f"  ⚠️  Telegram photo API: {resp.status_code} {resp.text[:100]}")
        return False
    except Exception as e:
        print(f"  ⚠️  Telegram photo failed: {e}")
        return False


def send_video(video_path: Path, caption: str = "",
               thumbnail_path: Path = None) -> bool:
    """Send a video file (up to 50MB via Bot API, 2GB via local API).

    Telegram compresses videos. For 1-min clips this is fine.
    """
    if not _is_configured():
        return False

    # Check file size — Telegram Bot API limit is 50MB
    size_mb = video_path.stat().st_size / (1024 * 1024)
    if size_mb > 50:
        print(f"  ⚠️  Video too large for Telegram ({size_mb:.1f}MB > 50MB)")
        send_message(
            f"⚠️ Video generated but too large to send ({size_mb:.1f}MB).\n"
            f"Download from GitHub Actions artifacts."
        )
        return False

    try:
        files = {"video": open(video_path, "rb")}
        if thumbnail_path and thumbnail_path.exists():
            files["thumbnail"] = open(thumbnail_path, "rb")

        resp = requests.post(
            _api_url("sendVideo"),
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption,
                "parse_mode": "Markdown",
                "supports_streaming": "true",
            },
            files=files,
            timeout=300,  # large uploads can be slow
        )

        # Close file handles
        for f in files.values():
            f.close()

        if resp.status_code == 200:
            print(f"  📨 Telegram video sent ({size_mb:.1f}MB)")
            return True
        print(f"  ⚠️  Telegram video API: {resp.status_code} {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"  ⚠️  Telegram video failed: {e}")
        return False


# ── Pipeline notifications ───────────────────────────────────────────

def notify_video_complete(title: str, duration: float, source: str,
                          video_path: Path = None,
                          thumbnail_path: Path = None,
                          nsfw_blocks: int = 0,
                          queue_remaining: int = None):
    """Full video delivery to Telegram.

    Sends: thumbnail → video file → metadata summary.
    """
    source_label = "Claude" if source == "claude" else "Gemini (backup)"

    # 1. Send thumbnail
    if thumbnail_path and thumbnail_path.exists():
        send_photo(thumbnail_path, caption=f"🎬 *{title}*")

    # 2. Send video file
    if video_path and video_path.exists():
        video_caption = (
            f"📹 *{title}*\n"
            f"⏱ {duration:.0f}s\n"
            f"✍️ {source_label}"
        )
        send_video(video_path, caption=video_caption, thumbnail_path=thumbnail_path)
    else:
        send_message(
            f"✅ *Video Generated*\n\n"
            f"📹 _{title}_\n"
            f"⏱ {duration:.0f}s\n"
            f"✍️ Script by: {source_label}\n\n"
            f"⚠️ Video file not found for direct send."
        )

    # 3. Send metadata + alerts
    alerts = []
    if nsfw_blocks > 0:
        alerts.append(f"⚠️ {nsfw_blocks} images hit NSFW filter (rewrites used)")
    if queue_remaining is not None:
        alerts.append(f"📝 Scripts remaining: {queue_remaining}")

    if alerts:
        send_message("\n".join(alerts))


def notify_scripts_low(remaining: int):
    """Alert that the script queue is running low."""
    send_message(
        f"⚠️ *Script Queue Low*\n\n"
        f"Only *{remaining}* scripts left!\n\n"
        f"Open Claude and write more scripts, or the pipeline "
        f"will fall back to Gemini-generated scripts."
    )


def notify_pipeline_failed(error: str):
    """Alert that the pipeline failed."""
    send_message(
        f"❌ *Pipeline Failed*\n\n"
        f"```\n{error[:500]}\n```\n\n"
        f"Check GitHub Actions for full logs."
    )


def notify_nsfw_warning(blocked_count: int, total_images: int):
    """Alert when multiple images were NSFW-blocked."""
    send_message(
        f"⚠️ *NSFW Filter Warning*\n\n"
        f"{blocked_count}/{total_images} images were blocked by "
        f"Cloudflare's content filter.\n\n"
        f"Prompt rewrites were used — check image quality."
    )
