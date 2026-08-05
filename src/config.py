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
CHANNEL_TAGLINE = "Your grandma's rules, finally explained."

# ── Voice ──────────────────────────────────────────────────────────
# Google Cloud TTS is now primary, gTTS is fallback
# Old edge-tts config kept for reference only

# ── Video ──────────────────────────────────────────────────────────
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30
IMAGE_DURATION = 4  # seconds per image — fits within 20 RPD Gemini limit

# ── Image style ────────────────────────────────────────────────────
IMAGE_STYLE = (
    "STYLE: Simple stick-figure cartoon like OverSimplified YouTube channel. "
    "One recurring character: round white head, two dot eyes, straight line mouth, "
    "messy brown hair, stick body with simple clothing. "
    "Thick black outlines, flat solid colors, NO gradients, NO shading. "
    "White or simple solid-color background. Objects around the character are "
    "simple but recognizable (icons, props, animals). "
    "NO photorealism, NO 3D, NO text, NO watermarks."
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

# ── Pollinations (backup, costs pollen) ───────────────────────────
POLLINATIONS_API_KEY = os.environ.get("POLLINATIONS_API_KEY", "")

# ── Google Cloud TTS ──────────────────────────────────────────────
GOOGLE_TTS_API_KEY = os.environ.get("GEMINI_TTS_API_KEY", "")

# ── Telegram ───────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Script queue ───────────────────────────────────────────────────
SCRIPT_LOW_THRESHOLD = 7  # Alert when fewer than this many scripts remain
