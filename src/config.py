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
VOICE_ENGINE = os.environ.get("VOICE_ENGINE", "gtts")  # "gtts" (default) or "edge-tts"
EDGE_TTS_VOICE = os.environ.get("EDGE_TTS_VOICE", "en-US-GuyNeural")  # only used if edge-tts

# ── Video ──────────────────────────────────────────────────────────
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30
IMAGE_DURATION = 3  # seconds per image — 1 image every 3 seconds

# ── Image style ────────────────────────────────────────────────────
IMAGE_STYLE = (
    "STYLE: Simple 2D cartoon, flat illustration, bold black outlines, "
    "solid colors (no gradients), round heads, dot eyes, simple expressions. "
    "Clean white or solid-color background. Minimal detail — easy to understand "
    "at a glance. Consistent Kurzgesagt-lite / explainer video aesthetic. "
    "Characters are culturally appropriate to the topic (clothing, features, setting) "
    "but ALL drawn in this same flat cartoon style. "
    "NO photorealism, NO 3D, NO text, NO watermarks, NO complex shading."
)

# ── Gemini models ──────────────────────────────────────────────────
GEMINI_TEXT_MODEL = "gemini-2.5-flash"
GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"

# ── Telegram ───────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Script queue ───────────────────────────────────────────────────
SCRIPT_LOW_THRESHOLD = 7  # Alert when fewer than this many scripts remain
