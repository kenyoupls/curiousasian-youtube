"""Video assembly using FFmpeg.

Features:
- Static images with hard cuts (OverSimplified style)
- Key phrase text overlays
- Background music with auto-ducking under voiceover
- Sound effects at section transitions
- Intro bumper + end screen CTA
"""

import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from src.config import (
    VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS,
    OUTPUT_DIR, CHANNEL_NAME, CHANNEL_TAGLINE, ASSETS_DIR
)


# ── Music settings ────────────────────────────────────────────────────
MUSIC_VOLUME_UNDER_VOICE = 0.08
MUSIC_FADE_IN = 2.0
MUSIC_FADE_OUT = 3.0


def _make_image_clip(image_path: Path, duration: float, key_phrase: str,
                     clip_path: Path, **kwargs) -> Path:
    """Create a static image clip with optional text overlay. No zoom, no pan."""

    filters = (
        f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2"
    )

    if key_phrase and key_phrase.strip():
        safe_text = (
            key_phrase
            .replace("\\", "\\\\")
            .replace("'", "'\\''")
            .replace(":", "\\:")
            .replace("%", "%%")
        )
        filters += (
            f",drawtext=text='{safe_text}'"
            f":fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            f":fontsize=44:fontcolor=white"
            f":borderw=3:bordercolor=black@0.8"
            f":x=(w-tw)/2:y=h-100"
        )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-vf", filters,
        "-t", str(duration),
        "-r", str(VIDEO_FPS),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-an",
        str(clip_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed for {clip_path.name}: {result.stderr[-300:]}")
    return clip_path


def _concat_clips(clip_paths: list[Path], output_path: Path) -> Path:
    """Concatenate clips with hard cuts (no crossfade)."""
    if not clip_paths:
        return output_path

    if len(clip_paths) == 1:
        cmd = ["ffmpeg", "-y", "-i", str(clip_paths[0]), "-c", "copy", str(output_path)]
        subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return output_path

    concat_file = output_path.with_suffix(".txt")
    with open(concat_file, "w") as f:
        for cp in clip_paths:
            f.write(f"file '{cp.resolve()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy", "-an",
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    concat_file.unlink(missing_ok=True)

    if result.returncode != 0:
        err_lines = [l for l in result.stderr.splitlines()
                     if any(k in l.lower() for k in ["error", "invalid", "no such", "failed", "mismatch"])]
        err_summary = "\n".join(err_lines[-5:]) if err_lines else result.stderr[:500]
        raise RuntimeError(f"Concat failed: {err_summary}")
    return output_path


def _generate_intro_bumper(output_path: Path, duration: float = 2.5) -> Path:
    """Intro bumper: dark background, channel name, tagline. Includes silent audio."""
    intro_img = output_path.with_suffix(".png")

    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), (15, 15, 25))
    draw = ImageDraw.Draw(img)

    try:
        font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
    except (OSError, IOError):
        font_lg = ImageFont.load_default()
        font_sm = font_lg

    # Channel name (gold, centered)
    bb = draw.textbbox((0, 0), CHANNEL_NAME, font=font_lg)
    x = (VIDEO_WIDTH - (bb[2] - bb[0])) // 2
    y = VIDEO_HEIGHT // 2 - 60
    draw.text((x, y), CHANNEL_NAME, fill=(255, 215, 0), font=font_lg)

    # Tagline
    bb2 = draw.textbbox((0, 0), CHANNEL_TAGLINE, font=font_sm)
    x2 = (VIDEO_WIDTH - (bb2[2] - bb2[0])) // 2
    draw.text((x2, y + 90), CHANNEL_TAGLINE, fill=(200, 200, 200), font=font_sm)

    img.save(intro_img, "PNG")

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(intro_img),
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-vf", (
            f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
            f"fade=t=in:st=0:d=0.8,fade=t=out:st={duration - 0.5}:d=0.5"
        ),
        "-t", str(duration),
        "-r", str(VIDEO_FPS),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p", "-shortest",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    intro_img.unlink(missing_ok=True)
    return output_path


def _generate_end_screen(output_path: Path, duration: float = 5.0) -> Path:
    """End screen: subscribe CTA + channel branding. Includes silent audio."""
    end_img = output_path.with_suffix(".png")

    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), (15, 15, 25))
    draw = ImageDraw.Draw(img)

    try:
        font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
        font_md = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except (OSError, IOError):
        font_lg = ImageFont.load_default()
        font_md = font_lg
        font_sm = font_lg

    # Red subscribe button
    cta = "SUBSCRIBE"
    bb = draw.textbbox((0, 0), cta, font=font_lg)
    cta_w, cta_h = bb[2] - bb[0], bb[3] - bb[1]
    btn_w, btn_h = cta_w + 80, cta_h + 40
    btn_x = (VIDEO_WIDTH - btn_w) // 2
    btn_y = VIDEO_HEIGHT // 2 - 80
    draw.rounded_rectangle([btn_x, btn_y, btn_x + btn_w, btn_y + btn_h], radius=15, fill=(204, 0, 0))
    draw.text((btn_x + (btn_w - cta_w) // 2, btn_y + (btn_h - cta_h) // 2), cta, fill="white", font=font_lg)

    # Channel name
    bb2 = draw.textbbox((0, 0), CHANNEL_NAME, font=font_md)
    draw.text(((VIDEO_WIDTH - (bb2[2] - bb2[0])) // 2, btn_y + btn_h + 40), CHANNEL_NAME, fill=(255, 215, 0), font=font_md)

    # Tagline
    bb3 = draw.textbbox((0, 0), CHANNEL_TAGLINE, font=font_sm)
    draw.text(((VIDEO_WIDTH - (bb3[2] - bb3[0])) // 2, btn_y + btn_h + 100), CHANNEL_TAGLINE, fill=(180, 180, 180), font=font_sm)

    # Daily text
    daily = "New video every day"
    bb4 = draw.textbbox((0, 0), daily, font=font_sm)
    draw.text(((VIDEO_WIDTH - (bb4[2] - bb4[0])) // 2, btn_y + btn_h + 150), daily, fill=(140, 140, 140), font=font_sm)

    img.save(end_img, "PNG")

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(end_img),
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-vf", (
            f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
            f"fade=t=in:st=0:d=0.5,fade=t=out:st={duration - 1}:d=1"
        ),
        "-t", str(duration),
        "-r", str(VIDEO_FPS),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p", "-shortest",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    end_img.unlink(missing_ok=True)
    return output_path


def _mix_audio_layers(voiceover_path: Path, music_path: Path,
                      sfx_paths: dict, section_timestamps: list[float],
                      total_duration: float, output_path: Path) -> Path:
    """Mix voiceover + background music + SFX."""
    inputs = ["-i", str(voiceover_path), "-i", str(music_path)]

    whoosh = sfx_paths.get("whoosh")
    sfx_count = 0
    if whoosh and whoosh.exists() and len(section_timestamps) > 1:
        for _ in section_timestamps[1:]:
            inputs.extend(["-i", str(whoosh)])
            sfx_count += 1

    parts = []
    parts.append(
        f"[1:a]atrim=0:{total_duration},"
        f"volume={MUSIC_VOLUME_UNDER_VOICE},"
        f"afade=t=in:st=0:d={MUSIC_FADE_IN},"
        f"afade=t=out:st={total_duration - MUSIC_FADE_OUT}:d={MUSIC_FADE_OUT}[music]"
    )

    if sfx_count > 0:
        labels = []
        for i in range(sfx_count):
            ts = section_timestamps[i + 1]
            idx = 2 + i
            lbl = f"sfx{i}"
            delay = int(ts * 1000)
            parts.append(f"[{idx}:a]volume=0.4,adelay={delay}|{delay},apad=whole_dur={total_duration}[{lbl}]")
            labels.append(f"[{lbl}]")
        n = 2 + sfx_count
        parts.append(f"[0:a][music]{''.join(labels)}amix=inputs={n}:duration=first:dropout_transition=2,volume=1.5[aout]")
    else:
        parts.append("[0:a][music]amix=inputs=2:duration=first:dropout_transition=2,volume=1.8[aout]")

    cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", ";".join(parts), "-map", "[aout]", "-c:a", "aac", "-b:a", "192k", str(output_path)]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"  ⚠️  Audio mix failed, using voiceover only: {result.stderr[-200:]}")
        subprocess.run(["ffmpeg", "-y", "-i", str(voiceover_path), "-c:a", "aac", "-b:a", "192k", str(output_path)],
                        capture_output=True, text=True, timeout=120)
    return output_path


def build_video(script: dict, image_paths: list[Path],
                image_prompts: list[dict], audio_segments: list[dict],
                music_path: Path = None, sfx_paths: dict = None) -> Path:
    """Assemble video: intro → static image scenes with hard cuts → end screen."""

    clips_dir = OUTPUT_DIR / "clips"
    section_vids_dir = OUTPUT_DIR / "section_videos"
    clips_dir.mkdir(exist_ok=True)
    section_vids_dir.mkdir(exist_ok=True)

    # ── Intro bumper ──────────────────────────────────────────────
    print("  🎬 Generating intro bumper...")
    intro_path = section_vids_dir / "intro_bumper.mp4"
    _generate_intro_bumper(intro_path)

    # ── Group image prompts by section ────────────────────────────
    section_images = {}
    for pd in image_prompts:
        sid = pd["section_index"]
        if sid not in section_images:
            section_images[sid] = []
        section_images[sid].append(pd)

    section_video_paths = []
    section_timestamps = [0.0]
    cumulative_time = 2.5  # after intro

    for sec_idx, audio_seg in enumerate(audio_segments):
        section_vid = section_vids_dir / f"section_{sec_idx:02d}.mp4"

        if section_vid.exists():
            section_video_paths.append(section_vid)
            cumulative_time += audio_seg["duration"]
            section_timestamps.append(cumulative_time)
            continue

        sec_prompts = section_images.get(sec_idx, [])
        if not sec_prompts:
            continue

        print(f"  🎬 Section '{audio_seg['section_id']}': {len(sec_prompts)} images, {audio_seg['duration']:.1f}s")

        # Calculate durations from hints
        durations = [p.get("duration_hint", 0) for p in sec_prompts]
        hint_total = sum(durations)
        if hint_total > 0:
            scale = audio_seg["duration"] / hint_total
            durations = [round(d * scale, 2) for d in durations]
        else:
            durations = [audio_seg["duration"] / len(sec_prompts)] * len(sec_prompts)
        durations[-1] += audio_seg["duration"] - sum(durations)

        # Create image clips (static, no zoom)
        clip_paths = []
        for img_idx, pd in enumerate(sec_prompts):
            gi = pd["global_index"]
            if gi >= len(image_paths):
                break
            clip = clips_dir / f"clip_{sec_idx:02d}_{img_idx:03d}.mp4"
            if not clip.exists():
                _make_image_clip(image_paths[gi], durations[img_idx], pd.get("key_phrase", ""), clip)
            clip_paths.append(clip)

        # Hard-cut concat
        silent_vid = section_vids_dir / f"section_{sec_idx:02d}_silent.mp4"
        _concat_clips(clip_paths, silent_vid)

        # Add audio
        cmd = [
            "ffmpeg", "-y",
            "-i", str(silent_vid), "-i", str(audio_seg["path"]),
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", "-shortest",
            str(section_vid)
        ]
        merge_result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if merge_result.returncode != 0:
            print(f"  ⚠️  Audio merge failed for section {sec_idx}, using silent video")
            # Add silent audio so concat streams are consistent
            cmd_silent = [
                "ffmpeg", "-y",
                "-i", str(silent_vid),
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-shortest", str(section_vid)
            ]
            subprocess.run(cmd_silent, capture_output=True, text=True, timeout=300)
        silent_vid.unlink(missing_ok=True)

        section_video_paths.append(section_vid)
        cumulative_time += audio_seg["duration"]
        section_timestamps.append(cumulative_time)

    # ── End screen ────────────────────────────────────────────────
    print("  🎬 Generating end screen...")
    end_path = section_vids_dir / "end_screen.mp4"
    _generate_end_screen(end_path)

    # ── Final concat: intro + sections + end ──────────────────────
    print("  🎬 Concatenating all parts...")
    video_no_music = OUTPUT_DIR / "video_no_music.mp4"
    concat_file = section_vids_dir / "final_concat.txt"

    all_parts = [intro_path] + section_video_paths + [end_path]
    with open(concat_file, "w") as f:
        for part in all_parts:
            if part.exists():
                f.write(f"file '{part.resolve()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart", "-pix_fmt", "yuv420p",
        str(video_no_music)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        # Extract actual error lines (not encoding stats)
        err_lines = [l for l in result.stderr.splitlines()
                     if any(k in l.lower() for k in ["error", "invalid", "no such", "failed", "mismatch", "does not"])]
        err_summary = "\n".join(err_lines[-10:]) if err_lines else result.stderr[:1000]
        raise RuntimeError(f"Final concat failed:\n{err_summary}")

    # ── Mix background music + SFX ────────────────────────────────
    final_path = OUTPUT_DIR / "final_video.mp4"

    if music_path and music_path.exists():
        print("  🎵 Mixing background music and SFX...")
        vo_extracted = OUTPUT_DIR / "voiceover_extracted.aac"
        subprocess.run(["ffmpeg", "-y", "-i", str(video_no_music), "-vn", "-c:a", "aac", "-b:a", "192k", str(vo_extracted)],
                        capture_output=True, text=True, timeout=120)

        probe = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "json", str(video_no_music)],
                                capture_output=True, text=True)
        total_dur = float(json.loads(probe.stdout)["format"]["duration"])

        mixed = OUTPUT_DIR / "mixed_audio.aac"
        _mix_audio_layers(vo_extracted, music_path, sfx_paths or {}, section_timestamps, total_dur, mixed)

        cmd = ["ffmpeg", "-y", "-i", str(video_no_music), "-i", str(mixed),
               "-c:v", "copy", "-map", "0:v", "-map", "1:a", "-movflags", "+faststart", str(final_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print("  ⚠️  Music mix failed, using video without background music")
            video_no_music.rename(final_path)

        vo_extracted.unlink(missing_ok=True)
        mixed.unlink(missing_ok=True)
        video_no_music.unlink(missing_ok=True)
    else:
        video_no_music.rename(final_path)

    # Stats
    probe = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "json", str(final_path)],
                            capture_output=True, text=True)
    dur = float(json.loads(probe.stdout)["format"]["duration"])
    size_mb = final_path.stat().st_size / (1024 * 1024)
    print(f"🎬 Final video: {dur:.0f}s ({dur / 60:.1f} min), {size_mb:.1f} MB")

    return final_path
