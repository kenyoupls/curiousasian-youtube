"""Voice generation using edge-tts (free, high quality) or gTTS (free fallback).

Includes dramatic pause injection for MrBeast-style retention pacing.
"""

import asyncio
import re
import subprocess
from pathlib import Path
from mutagen.mp3 import MP3
from src.config import VOICE_ENGINE, EDGE_TTS_VOICE, OUTPUT_DIR


# ── Pause markers ─────────────────────────────────────────────────────
# These phrases get a dramatic pause BEFORE them (creates anticipation)
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
    r"because ",  # trailing space = start of explanation
]

# Pause duration in SSML (milliseconds)
DRAMATIC_PAUSE_MS = 600
SECTION_END_PAUSE_MS = 400


def _inject_pauses_ssml(text: str) -> str:
    """Inject SSML pause markers before dramatic phrases.

    Edge-TTS supports SSML, so we wrap the text with pause tags
    before key retention moments.
    """
    # Wrap in SSML speak tags
    ssml_text = text

    # Add pause before dramatic phrases
    for pattern in PAUSE_BEFORE:
        # Case-insensitive replacement — add a pause break before the phrase
        regex = re.compile(f'({pattern})', re.IGNORECASE)
        ssml_text = regex.sub(
            f'<break time="{DRAMATIC_PAUSE_MS}ms"/> \\1',
            ssml_text,
            count=2  # Max 2 pauses per pattern per section (don't overdo it)
        )

    # Wrap in SSML
    ssml_text = f'<speak>{ssml_text}</speak>'
    return ssml_text


def _inject_pauses_silence(audio_path: Path, text: str) -> Path:
    """Fallback: insert silence gaps into the audio file at pause points.

    Used when TTS engine doesn't support SSML (e.g., gTTS).
    Adds a brief silence at the end of each section audio.
    """
    padded_path = audio_path.with_suffix(".padded.mp3")

    # Add a small silence at end of section for breathing room
    cmd = [
        "ffmpeg", "-y",
        "-i", str(audio_path),
        "-f", "lavfi", "-i",
        f"anullsrc=r=44100:cl=mono,atrim=0:{SECTION_END_PAUSE_MS / 1000}",
        "-filter_complex", "[0][1]concat=n=2:v=0:a=1",
        str(padded_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        padded_path.replace(audio_path)
    else:
        # If padding fails, just use original
        padded_path.unlink(missing_ok=True)

    return audio_path


def get_audio_duration(audio_path: Path) -> float:
    """Get duration of an audio file in seconds."""
    try:
        audio = MP3(str(audio_path))
        return audio.info.length
    except Exception:
        # Fallback: use ffprobe
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(audio_path)],
            capture_output=True, text=True
        )
        return float(result.stdout.strip())


async def _generate_edge_tts(text: str, output_path: Path, use_ssml: bool = True):
    """Generate audio using Microsoft Edge TTS (free, high quality).

    Supports SSML for dramatic pauses.
    """
    import edge_tts

    if use_ssml:
        ssml_text = _inject_pauses_ssml(text)
        try:
            communicate = edge_tts.Communicate(ssml_text, EDGE_TTS_VOICE)
            await communicate.save(str(output_path))
            return
        except Exception:
            # SSML failed — fall back to plain text
            pass

    # Plain text fallback
    communicate = edge_tts.Communicate(text, EDGE_TTS_VOICE)
    await communicate.save(str(output_path))


def _generate_gtts(text: str, output_path: Path):
    """Generate audio using Google Translate TTS (free fallback)."""
    from gtts import gTTS
    tts = gTTS(text=text, lang="en", slow=False)
    tts.save(str(output_path))


def generate_section_audio(text: str, output_path: Path) -> Path:
    """Generate audio for a single script section with dramatic pauses."""
    if VOICE_ENGINE == "edge-tts":
        asyncio.run(_generate_edge_tts(text, output_path))
    else:
        _generate_gtts(text, output_path)
        # gTTS doesn't support SSML, so add silence padding
        _inject_pauses_silence(output_path, text)

    return output_path


def generate_all_audio(script: dict) -> list[dict]:
    """Generate audio for all sections in the script.

    Returns list of {path, duration, section_id, narration}
    """
    audio_dir = OUTPUT_DIR / "audio"
    audio_dir.mkdir(exist_ok=True)

    audio_segments = []

    for i, section in enumerate(script["sections"]):
        output_path = audio_dir / f"section_{i:02d}_{section['id']}.mp3"

        if not output_path.exists():
            generate_section_audio(section["narration"], output_path)

        duration = get_audio_duration(output_path)

        audio_segments.append({
            "path": output_path,
            "duration": duration,
            "section_id": section["id"],
            "narration": section["narration"],
        })

        print(f"  🔊 {section['id']}: {duration:.1f}s")

    total = sum(s["duration"] for s in audio_segments)
    print(f"🔊 Total audio: {total:.0f}s ({total / 60:.1f} min)")

    return audio_segments
