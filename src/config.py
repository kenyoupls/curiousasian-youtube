"""Configuration for the CuriousAsian YouTube automation pipeline."""

import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
OUTPUT_DIR = ROOT_DIR / "output"
ASSETS_DIR = ROOT_DIR / "assets"
SCRIPTS_QUEUE_DIR = ROOT_DIR / "scripts" / "queue"
SCRIPTS_DONE_DIR = ROOT_DIR / "scripts" / "done"

# Create dirs if missing
for d in [DATA_DIR, OUTPUT_DIR, ASSETS_DIR, SCRIPTS_QUEUE_DIR, SCRIPTS_DONE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── API Keys ───────────────────────────────────────────────────────
# Support multiple API keys for load balancing (comma-separated)
# Merges both GEMINI_API_KEY (single) and GEMINI_API_KEYS (multi), deduped
_single_key = os.environ.get("GEMINI_API_KEY", "").strip()
_multi_keys = os.environ.get("GEMINI_API_KEYS", "")
_all_keys = [k.strip() for k in _multi_keys.split(",") if k.strip()] if _multi_keys else []
if _single_key and _single_key not in _all_keys:
    _all_keys.insert(0, _single_key)  # original key first
GEMINI_API_KEYS = _all_keys
GEMINI_API_KEY = _single_key or (_all_keys[0] if _all_keys else "")

# ── Channel ────────────────────────────────────────────────────────
CHANNEL_NAME = "CuriousAsian"
CHANNEL_TAGLINE = ""  # Rotating CTA used instead — see script_manager.py

# ── Voice ──────────────────────────────────────────────────────────
# Google Cloud TTS is now primary, gTTS is fallback
# Old edge-tts config kept for reference only

# ── Video ──────────────────────────────────────────────────────────
# 9:16 vertical format for YouTube Shorts / TikTok / Reels
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
IMAGE_DURATION = 2.5  # seconds per image — fast cuts for engagement

# ── Image style ────────────────────────────────────────────────────
IMAGE_STYLE = (
    "STYLE: 90s vintage anime cel-shaded illustration. "
    "Retro anime art style like 1990s Japanese animation. "
    "Main character: cute boy with round face, big sparkling eyes, "
    "messy brown hair, dark gray hoodie, olive cargo pants, brown boots. "
    "Warm nostalgic color palette, soft cel-shading, visible outlines, "
    "detailed colorful backgrounds, hand-drawn look. "
    "NO photorealism, NO 3D, NO stickman, NO modern digital art."
)

# ── Gemini models (fallback order — tries each until one works) ────
GEMINI_TEXT_MODELS = [
    "gemini-3.5-flash-lite",      # 500 RPD — most generous free tier
    "gemini-3.6-flash",           # fallback
]
GEMINI_IMAGE_MODELS = [
    # All Gemini image models are paid — no free tier exists
    # Cloudflare FLUX Schnell is the primary free option
]
# Primary (first in list) — used by default
GEMINI_TEXT_MODEL = GEMINI_TEXT_MODELS[0]
GEMINI_IMAGE_MODEL = GEMINI_IMAGE_MODELS[0] if GEMINI_IMAGE_MODELS else None

# ── Cloudflare Workers AI ──────────────────────────────────────────
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")

# ── Pollinations (free, no API key needed) ───────────────────────
# Using free endpoint: image.pollinations.ai/prompt/{prompt}

# ── Google Cloud TTS ──────────────────────────────────────────────
GOOGLE_TTS_API_KEY = os.environ.get("GEMINI_TTS_API_KEY", "")

# ── Gemini TTS (dedicated keys for voice, separate quota from text) ─
# Supports multiple comma-separated keys for quota rotation
_voice_key_str = os.environ.get("GEMINI_VOICE_KEY", "")
GEMINI_VOICE_KEYS = [k.strip() for k in _voice_key_str.split(",") if k.strip()]

# ── Telegram ───────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "834454829")

# ── Script queue ───────────────────────────────────────────────────
SCRIPT_LOW_THRESHOLD = 7  # Alert when fewer than this many scripts remain
