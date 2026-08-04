"""Voice generation — edge-tts primary (natural, SSML), gTTS fallback.

Edge-tts: free Microsoft voices with SSML support for emphasis and pauses.
gTTS: Google Translate TTS fallback (robotic but reliable).
"""

import asyncio
import re
import subprocess
from pathlib import Path
from mutagen.mp3 import MP3
from src.config import VOICE_ENGINE, EDGE_TTS_VOICE, OUTPUT_DIR


# ── Pause markers ─────────────────────────────────────────────────────
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
]

# Words to emphasize (wrapped in <emphasis> for edge-tts)
EMPHASIS_WORDS = [
    r"never", r"always", r"every", r"nothing", r"everything",
    r"actually", r"literally", r"exactly", r"superior", r"inferior",
    r"thousands", r"millions", r"billions",
    r"not", r"don't", r"can't", r"won't", r"isn't", r"wasn't",
    r"wrong", r"right", r"real", r"fake", r"true", r"false",
    r"secret", r"hidden", r"ancient", r"sacred",
]

DRAMATIC_PAUSE_MS = 600
SECTION_END_PAUSE_MS = 400


def _inject_ssml(text: str) -> str:
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
    """Fallback: add silence at end of section for breathing room (gTTS)."""
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


async def _generate_edge_tts(text: str, output_path: Path):
    """Generate audio using edge-tts with SSML emphasis and pauses."""
    import edge_tts

    # Try SSML first
    try:
        ssml = _inject_ssml(text)
        communicate = edge_tts.Communicate(ssml, EDGE_TTS_VOICE)
        await communicate.save(str(output_path))
        if output_path.exists() and output_path.stat().st_size > 1000:
            return
    except Exception as e:
        print(f"    ⚠️  SSML failed, trying plain text: {e}")

    # Plain text fallback
    communicate = edge_tts.Communicate(text, EDGE_TTS_VOICE)
    await communicate.save(str(output_path))


def _generate_gtts(text: str, output_path: Path):
    """Generate audio using gTTS (free fallback)."""
    from gtts import gTTS
    tts = gTTS(text=text, lang="en", tld="co.uk", slow=False)
    tts.save(str(output_path))


def generate_section_audio(text: str, output_path: Path) -> Path:
    """Generate audio: edge-tts primary → gTTS fallback."""

    # Primary: edge-tts
    if VOICE_ENGINE == "edge-tts":
        try:
            asyncio.run(_generate_edge_tts(text, output_path))
            if output_path.exists() and output_path.stat().st_size > 1000:
                return output_path
        except Exception as e:
            print(f"    ⚠️  Edge-tts failed, falling back to gTTS: {e}")

    # Fallback: gTTS
    try:
        _generate_gtts(text, output_path)
        _inject_pauses_silence(output_path)
        return output_path
    except Exception as e:
        # Last resort: try edge-tts if gTTS was primary and failed
        if VOICE_ENGINE != "edge-tts":
            try:
                asyncio.run(_generate_edge_tts(text, output_path))
                return output_path
            except Exception:
                pass
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
