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
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ── Channel ────────────────────────────────────────────────────────
CHANNEL_NAME = "CuriousAsian"
CHANNEL_TAGLINE = "Your grandma's rules, finally explained."

# ── Voice ──────────────────────────────────────────────────────────
VOICE_ENGINE = os.environ.get("VOICE_ENGINE", "edge-tts")  # "edge-tts" (default) or "gtts"
EDGE_TTS_VOICE = os.environ.get("EDGE_TTS_VOICE", "en-GB-ThomasNeural")

# ── Video ──────────────────────────────────────────────────────────
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30
IMAGE_DURATION = 3  # seconds per image — 1 image every 3 seconds

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
    "gemini-2.5-flash-lite",      # oldest, least demand
    "gemini-3.5-flash-lite",      # lite = less demand
    "gemini-3.5-flash",
    "gemini-3.6-flash",
]
GEMINI_IMAGE_MODELS = [
    "gemini-2.5-flash-image",     # only free image model (~500/day at 1024x1024)
]
# Primary (first in list) — used by default
GEMINI_TEXT_MODEL = GEMINI_TEXT_MODELS[0]
GEMINI_IMAGE_MODEL = GEMINI_IMAGE_MODELS[0]

# ── Telegram ───────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Script queue ───────────────────────────────────────────────────
SCRIPT_LOW_THRESHOLD = 7  # Alert when fewer than this many scripts remain
