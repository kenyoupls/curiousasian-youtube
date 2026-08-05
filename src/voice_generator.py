"""Voice generation — Google Cloud TTS primary, gTTS fallback.

Dynamic delivery: pitch, rate, and emphasis vary by section type.
Hook sections are fast + high energy. Twists get dramatic pauses.
Context sections drop to authoritative tone. Payoffs spike back up.
"""

import base64
import json
import re
import subprocess
from pathlib import Path
import requests
from mutagen.mp3 import MP3
from src.config import GOOGLE_TTS_API_KEY, OUTPUT_DIR


# ── Google Cloud TTS config ──────────────────────────────────────────
GOOGLE_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
GOOGLE_TTS_VOICE = "en-US-Neural2-D"
GOOGLE_TTS_LANGUAGE = "en-US"

# ── Section-specific voice profiles ──────────────────────────────────
# Each section type gets its own speaking rate and pitch for tonal variety.
# This prevents the flat monotone that kills engagement.
SECTION_VOICE_PROFILES = {
    # Hook: fast, high energy, excited — grab attention
    "hook":    {"rate": 1.30, "pitch": 2.0},
    # Build/origin: slightly slower, authoritative — "let me explain"
    "build":   {"rate": 1.15, "pitch": 0.0},
    "origin":  {"rate": 1.15, "pitch": 0.0},
    # Twist: medium pace, pitch drops then spikes — dramatic reveal
    "twist":   {"rate": 1.10, "pitch": 1.5},
    # Payoff: confident, measured — the satisfying answer
    "payoff":  {"rate": 1.20, "pitch": 1.0},
    # Close: warm, slightly slower — brand moment
    "close":   {"rate": 1.10, "pitch": 0.5},
    # Default fallback
    "default": {"rate": 1.20, "pitch": 1.0},
}


def _get_voice_profile(section_id: str) -> dict:
    """Get speaking rate + pitch for a section based on its ID prefix."""
    for prefix, profile in SECTION_VOICE_PROFILES.items():
        if section_id.startswith(prefix):
            return profile
    return SECTION_VOICE_PROFILES["default"]


# ── Pause markers ────────────────────────────────────────────────────
# BIG pauses (500-600ms) — before major reveals. Max 1-2 per video.
BIG_REVEAL_PAUSE_BEFORE = [
    r"but here's what no one",
    r"here's the part",
    r"here's what nobody",
    r"the real reason",
    r"plot twist",
    r"but here's the twist",
]

# MEDIUM pauses (350ms) — before dramatic phrases
MEDIUM_PAUSE_BEFORE = [
    r"but here's",
    r"and here's",
    r"here's the twist",
    r"here's what",
    r"the twist",
    r"the answer",
    r"now here's",
    r"but wait",
    r"except",
    r"the truth is",
    r"it turns out",
    r"and that should",
    r"that's not",
    r"because ",
    r"and the reason",
    r"it's gonna",
    r"meanwhile",
    r"so which",
    r"no one tells you",
    r"what they don't",
    r"the opposite",
    r"turns out",
]

# MICRO pauses (150ms) — AFTER key words for emphasis ("TWO... DOLLARS")
MICRO_PAUSE_AFTER = [
    r"zero",
    r"two",
    r"three",
    r"five",
    r"ten",
    r"twenty",
    r"hundred",
    r"thousand",
    r"million",
    r"billion",
    r"dollars",
    r"percent",
    r"centuries",
    r"opposite",
    r"nothing",
    r"everything",
]

# ── Emphasis hierarchy ───────────────────────────────────────────────
# STRONG: 2-3 money words per video MAX — the words that carry the punchline
EMPHASIS_STRONG = [
    r"never", r"always", r"every", r"zero",
    r"insane", r"broken", r"wild", r"huge",
    r"opposite", r"wrong",
    r"living wage",
]

# MODERATE: supporting punchy words — less intense
EMPHASIS_MODERATE = [
    r"actually", r"literally", r"exactly",
    r"not", r"don't", r"can't", r"won't", r"isn't", r"wasn't",
    r"real", r"fake", r"true", r"false",
    r"secret", r"hidden", r"ancient", r"sacred",
    r"best", r"worst", r"biggest", r"craziest",
    r"thousands", r"millions", r"billions",
    r"superior", r"inferior",
]

BIG_REVEAL_PAUSE_MS = 550     # before major twist — feels dramatic
MEDIUM_PAUSE_MS = 300         # before reveals — just enough for impact
MICRO_PAUSE_MS = 150          # after key numbers/words — "TWO... DOLLARS"
SECTION_END_PAUSE_MS = 200    # tiny gap between sections — momentum


def _build_ssml(text: str, section_id: str = "") -> str:
    """Build SSML with dynamic pauses and tiered emphasis.

    Pause hierarchy: big reveal > medium > micro (after words)
    Emphasis hierarchy: strong (2-3 per video) > moderate
    """
    ssml = text

    # ── Big reveal pauses (500-600ms) — before major twists ──────
    for pattern in BIG_REVEAL_PAUSE_BEFORE:
        regex = re.compile(f'({pattern})', re.IGNORECASE)
        ssml = regex.sub(
            f'<break time="{BIG_REVEAL_PAUSE_MS}ms"/> \\1',
            ssml, count=1  # max 1 per section
        )

    # ── Medium pauses (350ms) — before dramatic phrases ──────────
    for pattern in MEDIUM_PAUSE_BEFORE:
        regex = re.compile(f'({pattern})', re.IGNORECASE)
        # Skip if already has a big pause before this phrase
        if f'<break time="{BIG_REVEAL_PAUSE_MS}ms"/>' not in ssml or pattern not in ssml.lower():
            ssml = regex.sub(
                f'<break time="{MEDIUM_PAUSE_MS}ms"/> \\1',
                ssml, count=2
            )

    # ── Micro pauses (150ms) — AFTER key words ───────────────────
    for word in MICRO_PAUSE_AFTER:
        regex = re.compile(rf'\b({word})\b', re.IGNORECASE)
        ssml = regex.sub(
            rf'\1 <break time="{MICRO_PAUSE_MS}ms"/>',
            ssml, count=2
        )

    # ── Strong emphasis (2-3 money words) ────────────────────────
    for word in EMPHASIS_STRONG:
        regex = re.compile(rf'\b({word})\b', re.IGNORECASE)
        ssml = regex.sub(
            r'<emphasis level="strong">\1</emphasis>',
            ssml, count=2  # max 2 per section
        )

    # ── Moderate emphasis (supporting words) ─────────────────────
    for word in EMPHASIS_MODERATE:
        regex = re.compile(rf'\b({word})\b', re.IGNORECASE)
        ssml = regex.sub(
            r'<emphasis level="moderate">\1</emphasis>',
            ssml, count=3
        )

    return f'<speak>{ssml}</speak>'


def _inject_pauses_silence(audio_path: Path) -> Path:
    """Add silence at end of section for breathing room (gTTS fallback)."""
    padded = audio_path.with_suffix(".padded.mp3")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(audio_path),
        "-f", "lavfi", "-i",
        f"anullsrc=r=44100:cl=mono,atrim=0:{SECTION_END_PAUSE_MS / 1000}",
        "-filter_complex", "[0][1]concat=n=2:v=0:a=1",
        str(padded)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        padded.replace(audio_path)
    else:
        padded.unlink(missing_ok=True)
    return audio_path


def get_audio_duration(audio_path: Path) -> float:
    """Get duration of an audio file in seconds."""
    try:
        return MP3(str(audio_path)).info.length
    except Exception:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(audio_path)],
            capture_output=True, text=True
        )
        return float(result.stdout.strip())


def _generate_google_tts(text: str, output_path: Path, section_id: str = ""):
    """Generate audio using Google Cloud TTS with SSML + section-aware voice."""
    if not GOOGLE_TTS_API_KEY:
        raise RuntimeError("GOOGLE_TTS_API_KEY not set")

    profile = _get_voice_profile(section_id)
    ssml = _build_ssml(text, section_id)

    payload = {
        "input": {"ssml": ssml},
        "voice": {
            "languageCode": GOOGLE_TTS_LANGUAGE,
            "name": GOOGLE_TTS_VOICE,
        },
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": profile["rate"],
            "pitch": profile["pitch"],
            "effectsProfileId": ["large-home-entertainment-class-device"],
        },
    }

    resp = requests.post(
        f"{GOOGLE_TTS_URL}?key={GOOGLE_TTS_API_KEY}",
        json=payload,
        timeout=30,
    )

    if resp.status_code != 200:
        try:
            err = resp.json()
            msg = err.get("error", {}).get("message", resp.text[:200])
        except Exception:
            msg = resp.text[:200]
        raise RuntimeError(f"Google TTS {resp.status_code}: {msg}")

    audio_content = resp.json().get("audioContent")
    if not audio_content:
        raise RuntimeError("Google TTS returned no audio content")

    output_path.write_bytes(base64.b64decode(audio_content))


def _generate_gtts(text: str, output_path: Path):
    """Generate audio using gTTS (free fallback)."""
    from gtts import gTTS
    tts = gTTS(text=text, lang="en", tld="co.uk", slow=False)
    tts.save(str(output_path))


def generate_section_audio(text: str, output_path: Path,
                           section_id: str = "") -> Path:
    """Generate audio: Google Cloud TTS primary → gTTS fallback.

    section_id determines voice profile (pitch, rate) for tonal variety.
    """
    # Primary: Google Cloud TTS (with section-aware voice)
    try:
        _generate_google_tts(text, output_path, section_id)
        if output_path.exists() and output_path.stat().st_size > 1000:
            return output_path
    except Exception as e:
        print(f"    ⚠️  Google TTS failed, falling back to gTTS: {e}")

    # Fallback: gTTS (no section-aware voice, but still works)
    try:
        _generate_gtts(text, output_path)
        _inject_pauses_silence(output_path)
        return output_path
    except Exception as e:
        raise RuntimeError(f"All voice engines failed: {e}")


def generate_all_audio(script: dict) -> list[dict]:
    """Generate audio for all sections. Returns list of segment dicts."""
    audio_dir = OUTPUT_DIR / "audio"
    audio_dir.mkdir(exist_ok=True)

    segments = []
    for i, section in enumerate(script["sections"]):
        out = audio_dir / f"section_{i:02d}_{section['id']}.mp3"

        if not out.exists():
            generate_section_audio(
                section["narration"], out,
                section_id=section["id"]
            )

        duration = get_audio_duration(out)
        segments.append({
            "path": out,
            "duration": duration,
            "section_id": section["id"],
            "narration": section["narration"],
        })
        print(f"  🔊 {section['id']}: {duration:.1f}s")

    total = sum(s["duration"] for s in segments)
    print(f"🔊 Total audio: {total:.0f}s ({total / 60:.1f} min)")
    return segments
