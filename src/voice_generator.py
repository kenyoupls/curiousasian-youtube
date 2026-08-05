"""Voice generation — Google Cloud TTS primary, gTTS fallback.

Google Cloud TTS: Natural Neural2/WaveNet voices with proper SSML support.
gTTS: Google Translate TTS fallback (robotic but reliable).
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
# Neural2-D = male, natural storytelling voice
# Other options: en-US-Neural2-F (female), en-US-Neural2-J (male casual)
GOOGLE_TTS_VOICE = "en-US-Neural2-D"
GOOGLE_TTS_LANGUAGE = "en-US"
GOOGLE_TTS_SPEAKING_RATE = 1.25  # fast MrBeast energy — no dead air
GOOGLE_TTS_PITCH = 1.0  # slightly higher = more energetic and young


# ── Pause markers ─────────────────────────────────────────────────────
# ── Pause markers — dramatic beats before reveals ────────────────────
PAUSE_BEFORE = [
    r"but here's",
    r"and here's",
    r"here's the twist",
    r"here's the part",
    r"here's what",
    r"the twist",
    r"the answer",
    r"the real reason",
    r"now here's",
    r"but wait",
    r"except",
    r"the truth is",
    r"it turns out",
    r"plot twist",
    r"and that should",
    r"that's not",
    r"because ",
    r"and the reason",
    r"it's gonna",
    r"meanwhile",
    r"so which",
    r"that same tip",
    r"in japan",
]

# Words to emphasize — punchy MrBeast-style stress
EMPHASIS_WORDS = [
    r"never", r"always", r"every", r"nothing", r"everything",
    r"actually", r"literally", r"exactly", r"superior", r"inferior",
    r"thousands", r"millions", r"billions",
    r"not", r"don't", r"can't", r"won't", r"isn't", r"wasn't",
    r"wrong", r"right", r"real", r"fake", r"true", r"false",
    r"secret", r"hidden", r"ancient", r"sacred",
    r"insane", r"offensive", r"insulted", r"broken", r"wild",
    r"best", r"worst", r"biggest", r"craziest",
    r"chases", r"sprinting", r"flips",
    r"living wage",
]

DRAMATIC_PAUSE_MS = 350   # tight pauses — just enough for impact, not boredom
SECTION_END_PAUSE_MS = 250  # barely any gap between sections — keeps momentum


def _build_ssml(text: str) -> str:
    """Build SSML with pauses before dramatic phrases and emphasis on key words."""
    ssml = text

    # Add pause before dramatic phrases
    for pattern in PAUSE_BEFORE:
        regex = re.compile(f'({pattern})', re.IGNORECASE)
        ssml = regex.sub(
            f'<break time="{DRAMATIC_PAUSE_MS}ms"/> \\1',
            ssml, count=2
        )

    # Emphasize key words (only whole words)
    for word in EMPHASIS_WORDS:
        regex = re.compile(rf'\b({word})\b', re.IGNORECASE)
        ssml = regex.sub(r'<emphasis level="strong">\1</emphasis>', ssml, count=3)

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


def _generate_google_tts(text: str, output_path: Path):
    """Generate audio using Google Cloud TTS with SSML."""
    if not GOOGLE_TTS_API_KEY:
        raise RuntimeError("GOOGLE_TTS_API_KEY not set")

    ssml = _build_ssml(text)

    payload = {
        "input": {"ssml": ssml},
        "voice": {
            "languageCode": GOOGLE_TTS_LANGUAGE,
            "name": GOOGLE_TTS_VOICE,
        },
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": GOOGLE_TTS_SPEAKING_RATE,
            "pitch": GOOGLE_TTS_PITCH,
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


def generate_section_audio(text: str, output_path: Path) -> Path:
    """Generate audio: Google Cloud TTS primary → gTTS fallback."""

    # Primary: Google Cloud TTS
    try:
        _generate_google_tts(text, output_path)
        if output_path.exists() and output_path.stat().st_size > 1000:
            return output_path
    except Exception as e:
        print(f"    ⚠️  Google TTS failed, falling back to gTTS: {e}")

    # Fallback: gTTS
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
            generate_section_audio(section["narration"], out)

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
