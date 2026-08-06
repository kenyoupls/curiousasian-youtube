"""Voice generation — Chirp 3 HD primary, Gemini TTS fallback, gTTS last resort.

Dynamic delivery: rate varies by section type.
Hook sections are fast. Twists are slower/dramatic. Payoffs spike.

Chirp 3 HD: Google's latest TTS with natural delivery + pace control.
Gemini TTS: gemini-2.5-flash-preview-tts with inline emotion tags (fallback).
gTTS: Free text-only fallback (last resort).
"""

import base64
import json
import re
import struct
import subprocess
import time
import wave
from pathlib import Path
import requests
from mutagen.mp3 import MP3
from src.config import GOOGLE_TTS_API_KEY, OUTPUT_DIR


# ── Google Cloud TTS config ──────────────────────────────────────────
GOOGLE_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
GOOGLE_TTS_LANGUAGE = "en-US"

# ── Chirp 3 HD config (primary) ─────────────────────────────────────
CHIRP3_VOICE = "en-US-Chirp3-HD-Kore"  # Same Kore voice as Gemini TTS

# ── Gemini TTS config ────────────────────────────────────────────────
GEMINI_TTS_VOICE = "Kore"  # Warm, engaging male voice
GEMINI_TTS_RATE_LIMIT = 25  # seconds between calls (free tier: 3 RPM, stay well under)
_last_gemini_tts_call = 0.0

# ── Section-specific emotion profiles ────────────────────────────────
# Each section type gets emotion cues for Gemini TTS + rate/pitch for Google TTS fallback.
SECTION_VOICE_PROFILES = {
    # Hook: excited, high energy — grab attention immediately
    "hook": {
        "emotion_prefix": "[excitedly, with high energy] ",
        "emotion_suffix": "",
        "rate": 1.30, "pitch": 2.0,
        "temperature": 1.2,
    },
    # Build/origin: authoritative, explaining — "let me tell you why"
    "build": {
        "emotion_prefix": "[in a confident, storytelling tone] ",
        "emotion_suffix": "",
        "rate": 1.15, "pitch": 0.0,
        "temperature": 0.9,
    },
    "origin": {
        "emotion_prefix": "[in a warm, narrative tone] ",
        "emotion_suffix": "",
        "rate": 1.15, "pitch": 0.0,
        "temperature": 0.9,
    },
    # Twist: dramatic reveal — whisper then spike
    "twist": {
        "emotion_prefix": "[in a dramatic, mysterious whisper that builds to excitement] ",
        "emotion_suffix": "",
        "rate": 1.10, "pitch": 1.5,
        "temperature": 1.3,
    },
    # Payoff: mind-blown excitement — the satisfying answer
    "payoff": {
        "emotion_prefix": "[with amazement and excitement, like revealing a mind-blowing fact] ",
        "emotion_suffix": "",
        "rate": 1.20, "pitch": 1.0,
        "temperature": 1.1,
    },
    # Close: warm, slightly sarcastic/funny — brand moment
    "close": {
        "emotion_prefix": "[warmly, with a slight smile] ",
        "emotion_suffix": "",
        "rate": 1.10, "pitch": 0.5,
        "temperature": 1.0,
    },
    # Default fallback
    "default": {
        "emotion_prefix": "[engagingly] ",
        "emotion_suffix": "",
        "rate": 1.20, "pitch": 1.0,
        "temperature": 1.0,
    },
}


def _get_voice_profile(section_id: str) -> dict:
    """Get voice profile for a section based on its ID prefix."""
    for prefix, profile in SECTION_VOICE_PROFILES.items():
        if section_id.startswith(prefix):
            return profile
    return SECTION_VOICE_PROFILES["default"]


# ── Pause markers (for Google Cloud TTS SSML fallback) ──────────────
BIG_REVEAL_PAUSE_BEFORE = [
    r"but here's what no one",
    r"here's the part",
    r"here's what nobody",
    r"the real reason",
    r"plot twist",
    r"but here's the twist",
]

MEDIUM_PAUSE_BEFORE = [
    r"but here's", r"and here's", r"here's the twist",
    r"here's what", r"the twist", r"the answer",
    r"now here's", r"but wait", r"except",
    r"the truth is", r"it turns out", r"and that should",
    r"that's not", r"because ", r"and the reason",
    r"it's gonna", r"meanwhile", r"so which",
    r"no one tells you", r"what they don't", r"the opposite", r"turns out",
]

MICRO_PAUSE_AFTER = [
    r"zero", r"two", r"three", r"five", r"ten",
    r"twenty", r"hundred", r"thousand", r"million", r"billion",
    r"dollars", r"percent", r"centuries", r"opposite",
    r"nothing", r"everything",
]

EMPHASIS_STRONG = [
    r"never", r"always", r"every", r"zero",
    r"insane", r"broken", r"wild", r"huge",
    r"opposite", r"wrong", r"living wage",
]

EMPHASIS_MODERATE = [
    r"actually", r"literally", r"exactly",
    r"not", r"don't", r"can't", r"won't", r"isn't", r"wasn't",
    r"real", r"fake", r"true", r"false",
    r"secret", r"hidden", r"ancient", r"sacred",
    r"best", r"worst", r"biggest", r"craziest",
    r"thousands", r"millions", r"billions",
    r"superior", r"inferior",
]

BIG_REVEAL_PAUSE_MS = 550
MEDIUM_PAUSE_MS = 300
MICRO_PAUSE_MS = 150
SECTION_END_PAUSE_MS = 200


def _build_ssml(text: str, section_id: str = "") -> str:
    """Build SSML with dynamic pauses and tiered emphasis (Google TTS fallback)."""
    ssml = text

    for pattern in BIG_REVEAL_PAUSE_BEFORE:
        regex = re.compile(f'({pattern})', re.IGNORECASE)
        ssml = regex.sub(f'<break time="{BIG_REVEAL_PAUSE_MS}ms"/> \\1', ssml, count=1)

    for pattern in MEDIUM_PAUSE_BEFORE:
        regex = re.compile(f'({pattern})', re.IGNORECASE)
        if f'<break time="{BIG_REVEAL_PAUSE_MS}ms"/>' not in ssml or pattern not in ssml.lower():
            ssml = regex.sub(f'<break time="{MEDIUM_PAUSE_MS}ms"/> \\1', ssml, count=2)

    for word in MICRO_PAUSE_AFTER:
        regex = re.compile(rf'\b({word})\b', re.IGNORECASE)
        ssml = regex.sub(rf'\1 <break time="{MICRO_PAUSE_MS}ms"/>', ssml, count=2)

    for word in EMPHASIS_STRONG:
        regex = re.compile(rf'\b({word})\b', re.IGNORECASE)
        ssml = regex.sub(r'<emphasis level="strong">\1</emphasis>', ssml, count=2)

    for word in EMPHASIS_MODERATE:
        regex = re.compile(rf'\b({word})\b', re.IGNORECASE)
        ssml = regex.sub(r'<emphasis level="moderate">\1</emphasis>', ssml, count=3)

    return f'<speak>{ssml}</speak>'


def _pcm_to_mp3(pcm_data: bytes, output_path: Path, sample_rate: int = 24000):
    """Convert raw PCM audio bytes to MP3 via WAV intermediate + FFmpeg."""
    wav_path = output_path.with_suffix(".wav")

    # Write PCM as WAV (16-bit mono)
    with wave.open(str(wav_path), 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)

    # Convert WAV to MP3
    cmd = [
        "ffmpeg", "-y",
        "-i", str(wav_path),
        "-codec:a", "libmp3lame", "-b:a", "192k",
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    wav_path.unlink(missing_ok=True)

    if result.returncode != 0:
        raise RuntimeError(f"PCM→MP3 conversion failed: {result.stderr[-200:]}")

    return output_path


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


def _generate_gemini_tts(text: str, output_path: Path, section_id: str = ""):
    """Generate audio using Gemini TTS with emotion cues per section."""
    global _last_gemini_tts_call
    from src.gemini_helper import generate_speech

    # Proactive rate limiting — space calls 21s apart to avoid 429
    wait = GEMINI_TTS_RATE_LIMIT - (time.time() - _last_gemini_tts_call)
    if wait > 0:
        print(f"    ⏳ TTS rate limit: waiting {wait:.0f}s...")
        time.sleep(wait)
    _last_gemini_tts_call = time.time()

    profile = _get_voice_profile(section_id)

    # Wrap text with emotion cues
    emotion_text = f"{profile['emotion_prefix']}{text}{profile['emotion_suffix']}"

    pcm_data = generate_speech(
        text=emotion_text,
        voice_name=GEMINI_TTS_VOICE,
        temperature=profile.get("temperature", 1.0),
    )

    if not pcm_data or len(pcm_data) < 1000:
        raise RuntimeError("Gemini TTS returned insufficient audio data")

    # Convert PCM to MP3
    _pcm_to_mp3(pcm_data, output_path)


def _generate_chirp3_tts(text: str, output_path: Path, section_id: str = ""):
    """Generate audio using Chirp 3 HD (primary — best free quality)."""
    if not GOOGLE_TTS_API_KEY:
        raise RuntimeError("GOOGLE_TTS_API_KEY not set")

    profile = _get_voice_profile(section_id)

    payload = {
        "input": {"text": text},
        "voice": {
            "languageCode": GOOGLE_TTS_LANGUAGE,
            "name": CHIRP3_VOICE,
        },
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": profile["rate"],
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
        raise RuntimeError(f"Chirp 3 HD {resp.status_code}: {msg}")

    audio_content = resp.json().get("audioContent")
    if not audio_content:
        raise RuntimeError("Chirp 3 HD returned no audio content")

    output_path.write_bytes(base64.b64decode(audio_content))


def _generate_gtts(text: str, output_path: Path):
    """Generate audio using gTTS (free last-resort fallback)."""
    from gtts import gTTS
    tts = gTTS(text=text, lang="en", tld="co.uk", slow=False)
    tts.save(str(output_path))


def generate_section_audio(text: str, output_path: Path,
                           section_id: str = "") -> Path:
    """Generate audio: Chirp 3 HD → Gemini TTS → gTTS.

    section_id determines voice profile (Chirp 3) or emotion cues (Gemini).
    """
    # Primary: Chirp 3 HD (best free quality, reliable, pace control)
    try:
        _generate_chirp3_tts(text, output_path, section_id)
        if output_path.exists() and output_path.stat().st_size > 1000:
            print(f"    ✅ Chirp 3 HD: {section_id}")
            return output_path
    except Exception as e:
        print(f"    ⚠️  Chirp 3 HD failed, trying Gemini TTS: {e}")

    # Fallback: Gemini TTS (with emotion cues per section)
    try:
        _generate_gemini_tts(text, output_path, section_id)
        if output_path.exists() and output_path.stat().st_size > 1000:
            return output_path
    except Exception as e:
        print(f"    ⚠️  Gemini TTS failed, falling back to gTTS: {e}")

    # Last resort: gTTS (no emotion, but still works)
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
