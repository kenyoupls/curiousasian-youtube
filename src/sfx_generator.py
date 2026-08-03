"""Generate procedural sound effects and ambient music using FFmpeg.

All audio is generated from scratch — no external files needed.
Everything is royalty-free because it's mathematically synthesized.
"""

import subprocess
from pathlib import Path
from src.config import ASSETS_DIR


SFX_DIR = ASSETS_DIR / "sfx"
MUSIC_DIR = ASSETS_DIR / "music"


def _ensure_dirs():
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)


def generate_whoosh(output_path: Path = None, duration: float = 0.5) -> Path:
    """Generate a whoosh/sweep transition sound."""
    _ensure_dirs()
    output_path = output_path or SFX_DIR / "whoosh.wav"
    if output_path.exists():
        return output_path

    # White noise filtered with a bandpass sweep = whoosh
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        (
            f"anoisesrc=d={duration}:c=pink:a=0.3,"
            f"highpass=f=800:t=q:w=2,"
            f"lowpass=f=4000:t=q:w=2,"
            f"afade=t=in:st=0:d={duration * 0.3},"
            f"afade=t=out:st={duration * 0.5}:d={duration * 0.5}"
        ),
        "-ar", "44100", "-ac", "1",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return output_path


def generate_dramatic_hit(output_path: Path = None, duration: float = 0.8) -> Path:
    """Generate a deep bass hit for dramatic reveals."""
    _ensure_dirs()
    output_path = output_path or SFX_DIR / "dramatic_hit.wav"
    if output_path.exists():
        return output_path

    # Low sine + noise burst = cinematic hit
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        (
            f"sine=f=60:d={duration},"
            f"afade=t=in:st=0:d=0.01,"
            f"afade=t=out:st=0.1:d={duration - 0.1},"
            f"volume=0.5"
        ),
        "-ar", "44100", "-ac", "1",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return output_path


def generate_subtle_ding(output_path: Path = None) -> Path:
    """Generate a subtle chime for section transitions."""
    _ensure_dirs()
    output_path = output_path or SFX_DIR / "ding.wav"
    if output_path.exists():
        return output_path

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        (
            "sine=f=880:d=0.3,"
            "afade=t=in:st=0:d=0.01,"
            "afade=t=out:st=0.05:d=0.25,"
            "volume=0.25"
        ),
        "-ar", "44100", "-ac", "1",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return output_path


def generate_ambient_music(output_path: Path = None,
                           duration: float = 600) -> Path:
    """Generate a lo-fi ambient background track.

    Creates a warm, non-distracting drone using layered filtered noise
    and low sine waves. Loops seamlessly. Designed to sit quietly under
    voiceover without competing for attention.
    """
    _ensure_dirs()
    output_path = output_path or MUSIC_DIR / "ambient_bg.wav"
    if output_path.exists():
        return output_path

    # Layer 1: Warm filtered brown noise (low drone)
    # Layer 2: Subtle sine pad (harmonic warmth)
    # Layer 3: Very quiet high shimmer
    # All mixed together and kept at low volume
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        (
            f"anoisesrc=d={duration}:c=brown:a=0.08,"
            f"lowpass=f=300:t=q:w=1,"
            f"highpass=f=60:t=q:w=1"
        ),
        "-f", "lavfi", "-i",
        (
            f"sine=f=110:d={duration},"
            f"volume=0.03"
        ),
        "-f", "lavfi", "-i",
        (
            f"sine=f=220:d={duration},"
            f"volume=0.015"
        ),
        "-filter_complex",
        "[0][1][2]amix=inputs=3:duration=first:dropout_transition=3,volume=0.7",
        "-ar", "44100", "-ac", "2",
        str(output_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  ⚠️  Ambient music generation failed: {result.stderr[-200:]}")
        # Fallback: simple quiet noise
        cmd_fallback = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i",
            f"anoisesrc=d={duration}:c=brown:a=0.05,lowpass=f=200",
            "-ar", "44100", "-ac", "2",
            str(output_path)
        ]
        subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=120)

    return output_path


def generate_all_sfx() -> dict:
    """Generate all sound effects. Returns dict of {name: Path}."""
    print("  🔊 Generating sound effects...")
    sfx = {
        "whoosh": generate_whoosh(),
        "dramatic_hit": generate_dramatic_hit(),
        "ding": generate_subtle_ding(),
    }
    print(f"  🔊 SFX ready: {list(sfx.keys())}")
    return sfx


def generate_background_music(duration: float) -> Path:
    """Generate ambient background music for the video duration."""
    print(f"  🎵 Generating {duration:.0f}s ambient background music...")
    # Add 10s buffer for safety
    path = generate_ambient_music(duration=duration + 10)
    print(f"  🎵 Background music ready")
    return path
