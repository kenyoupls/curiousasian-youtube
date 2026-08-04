"""Video assembly using FFmpeg.

Features:
- Ken Burns zoom (alternating in/out) on each image
- Crossfade transitions between images within sections
- Key phrase text overlays (Hormozi-style)
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


# ── Crossfade settings ────────────────────────────────────────────────
CROSSFADE_DURATION = 0.4  # seconds of crossfade between images

# ── Music settings ────────────────────────────────────────────────────
MUSIC_VOLUME_UNDER_VOICE = 0.08    # Very quiet under narration
MUSIC_VOLUME_TRANSITION = 0.25     # Slightly louder between sections
MUSIC_FADE_IN = 2.0                # Fade in at video start
MUSIC_FADE_OUT = 3.0               # Fade out at video end


def _make_image_clip(image_path: Path, duration: float, key_phrase: str,
                     clip_path: Path, zoom_direction: str = "in") -> Path:
    """Create a single image clip with Ken Burns zoom and key phrase overlay."""

    frames = int(duration * VIDEO_FPS)

    # Ken Burns zoom parameters
    if zoom_direction == "in":
        zoom_expr = "min(zoom+0.001,1.2)"
    else:
        zoom_expr = "if(eq(on,1),1.2,max(zoom-0.001,1))"

    x_expr = "iw/2-(iw/zoom/2)"
    y_expr = "ih/2-(ih/zoom/2)"

    # Build filter chain
    filters = (
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}'"
        f":d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS}"
    )

    # Add key phrase overlay if present
    if key_phrase and key_phrase.strip():
        safe_text = (
            key_phrase
            .replace("\\", "\\\\")
            .replace("'", "'\\''")
            .replace(":", "\\:")
            .replace("%", "%%")
        )
        # Animated fade-in for text (appears after 0.3s, fades in over 0.5s)
        filters += (
            f",drawtext=text='{safe_text}'"
            f":fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            f":fontsize=44:fontcolor=white"
            f":borderw=3:bordercolor=black@0.8"
            f":x=(w-tw)/2:y=h-100"
            f":enable='gte(t,0.3)'"
            f":alpha='if(lt(t,0.3),0,min((t-0.3)/0.5,1))'"
        )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-vf", filters,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-an",
        str(clip_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed for {clip_path.name}: {result.stderr[-300:]}")

    return clip_path


def _concat_clips_with_crossfade(clip_paths: list[Path], output_path: Path,
                                  crossfade_duration: float = CROSSFADE_DURATION) -> Path:
    """Concatenate clips with crossfade transitions between them.

    Uses FFmpeg xfade filter for smooth transitions.
    Falls back to hard-cut concat if crossfade fails (e.g., clips too short).
    """
    if len(clip_paths) <= 1:
        # Single clip — just copy
        if clip_paths:
            cmd = ["ffmpeg", "-y", "-i", str(clip_paths[0]),
                   "-c", "copy", str(output_path)]
            subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return output_path

    # Try crossfade first
    try:
        # Build xfade filter chain
        # Each xfade takes 2 inputs and produces 1 output
        inputs = []
        for cp in clip_paths:
            inputs.extend(["-i", str(cp)])

        # Get durations of each clip
        durations = []
        for cp in clip_paths:
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(cp)],
                capture_output=True, text=True
            )
            durations.append(float(probe.stdout.strip()))

        # Build xfade chain
        filter_parts = []
        prev_output = "[0:v]"
        cumulative_offset = 0

        for i in range(1, len(clip_paths)):
            curr_input = f"[{i}:v]"
            out_label = f"[v{i}]" if i < len(clip_paths) - 1 else "[vout]"

            # Offset = cumulative duration minus crossfade overlaps
            cumulative_offset += durations[i - 1] - crossfade_duration

            filter_parts.append(
                f"{prev_output}{curr_input}xfade=transition=fade"
                f":duration={crossfade_duration}"
                f":offset={cumulative_offset:.3f}{out_label}"
            )
            prev_output = out_label

        filter_complex = ";".join(filter_parts)

        cmd = ["ffmpeg", "-y"] + inputs + [
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-an",
            str(output_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            return output_path

    except Exception:
        pass

    # Fallback: simple concat (hard cuts)
    concat_file = output_path.with_suffix(".txt")
    with open(concat_file, "w") as f:
        for cp in clip_paths:
            f.write(f"file '{cp.resolve()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-an",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    concat_file.unlink(missing_ok=True)

    return output_path


def _generate_intro_bumper(output_path: Path, duration: float = 2.5) -> Path:
    """Generate a simple channel intro bumper image + video clip.

    Dark background with channel name and tagline — clean, minimal.
    """
    # Create intro image
    intro_img_path = output_path.with_suffix(".png")

    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), (15, 15, 25))
    draw = ImageDraw.Draw(img)

    try:
        font_large = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72
        )
        font_small = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32
        )
    except (OSError, IOError):
        font_large = ImageFont.load_default()
        font_small = font_large

    # Channel name (gold)
    bbox = draw.textbbox((0, 0), CHANNEL_NAME, font=font_large)
    x = (VIDEO_WIDTH - (bbox[2] - bbox[0])) // 2
    y = VIDEO_HEIGHT // 2 - 60
    draw.text((x, y), CHANNEL_NAME, fill=(255, 215, 0), font=font_large)

    # Tagline (white, smaller)
    bbox2 = draw.textbbox((0, 0), CHANNEL_TAGLINE, font=font_small)
    x2 = (VIDEO_WIDTH - (bbox2[2] - bbox2[0])) // 2
    y2 = y + 90
    draw.text((x2, y2), CHANNEL_TAGLINE, fill=(200, 200, 200), font=font_small)

    img.save(intro_img_path, "PNG")

    # Convert to video clip with fade-in
    frames = int(duration * VIDEO_FPS)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(intro_img_path),
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
        "-vf", (
            f"zoompan=z='min(zoom+0.0005,1.05)':x='iw/2-(iw/zoom/2)'"
            f":y='ih/2-(ih/zoom/2)':d={frames}"
            f":s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS},"
            f"fade=t=in:st=0:d=0.8,fade=t=out:st={duration - 0.5}:d=0.5"
        ),
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p", "-shortest",
        str(output_path)
    ]

    subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    intro_img_path.unlink(missing_ok=True)

    return output_path


def _generate_end_screen(output_path: Path, duration: float = 5.0) -> Path:
    """Generate an end screen with subscribe CTA and channel branding."""
    end_img_path = output_path.with_suffix(".png")

    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), (15, 15, 25))
    draw = ImageDraw.Draw(img)

    try:
        font_large = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64
        )
        font_medium = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40
        )
        font_small = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28
        )
    except (OSError, IOError):
        font_large = ImageFont.load_default()
        font_medium = font_large
        font_small = font_large

    # Subscribe CTA
    cta_text = "SUBSCRIBE"
    bbox = draw.textbbox((0, 0), cta_text, font=font_large)
    cta_w = bbox[2] - bbox[0]
    cta_h = bbox[3] - bbox[1]

    # Red subscribe button
    btn_w = cta_w + 80
    btn_h = cta_h + 40
    btn_x = (VIDEO_WIDTH - btn_w) // 2
    btn_y = VIDEO_HEIGHT // 2 - 80
    draw.rounded_rectangle(
        [btn_x, btn_y, btn_x + btn_w, btn_y + btn_h],
        radius=15, fill=(204, 0, 0)
    )
    text_x = btn_x + (btn_w - cta_w) // 2
    text_y = btn_y + (btn_h - cta_h) // 2
    draw.text((text_x, text_y), cta_text, fill=(255, 255, 255), font=font_large)

    # Channel name below
    bbox2 = draw.textbbox((0, 0), CHANNEL_NAME, font=font_medium)
    x2 = (VIDEO_WIDTH - (bbox2[2] - bbox2[0])) // 2
    draw.text((x2, btn_y + btn_h + 40), CHANNEL_NAME,
              fill=(255, 215, 0), font=font_medium)

    # Tagline
    bbox3 = draw.textbbox((0, 0), CHANNEL_TAGLINE, font=font_small)
    x3 = (VIDEO_WIDTH - (bbox3[2] - bbox3[0])) // 2
    draw.text((x3, btn_y + btn_h + 100), CHANNEL_TAGLINE,
              fill=(180, 180, 180), font=font_small)

    # "More videos coming daily" text
    daily_text = "New video every day"
    bbox4 = draw.textbbox((0, 0), daily_text, font=font_small)
    x4 = (VIDEO_WIDTH - (bbox4[2] - bbox4[0])) // 2
    draw.text((x4, btn_y + btn_h + 150), daily_text,
              fill=(140, 140, 140), font=font_small)

    img.save(end_img_path, "PNG")

    # Convert to video clip
    frames = int(duration * VIDEO_FPS)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(end_img_path),
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
        "-vf", (
            f"zoompan=z='1':x='0':y='0':d={frames}"
            f":s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS},"
            f"fade=t=in:st=0:d=0.5,fade=t=out:st={duration - 1}:d=1"
        ),
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p", "-shortest",
        str(output_path)
    ]

    subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    end_img_path.unlink(missing_ok=True)

    return output_path


def _mix_audio_layers(voiceover_path: Path, music_path: Path,
                      sfx_paths: dict, section_timestamps: list[float],
                      total_duration: float, output_path: Path) -> Path:
    """Mix voiceover + background music + SFX into final audio track.

    - Music auto-ducks under voiceover (sidechaining via volume envelope)
    - SFX whoosh plays at each section transition
    - Music fades in/out at start/end
    """
    # Build filter complex for audio mixing
    inputs = [
        "-i", str(voiceover_path),    # [0] voiceover
        "-i", str(music_path),        # [1] background music
    ]

    # Add SFX inputs
    sfx_input_idx = 2
    whoosh_path = sfx_paths.get("whoosh")
    sfx_count = 0

    if whoosh_path and whoosh_path.exists() and len(section_timestamps) > 1:
        for _ in section_timestamps[1:]:  # Skip first (it's the start)
            inputs.extend(["-i", str(whoosh_path)])
            sfx_count += 1

    # Filter: duck music under voice
    filter_parts = []

    # Music: trim to duration, set volume low, fade in/out
    filter_parts.append(
        f"[1:a]atrim=0:{total_duration},"
        f"volume={MUSIC_VOLUME_UNDER_VOICE},"
        f"afade=t=in:st=0:d={MUSIC_FADE_IN},"
        f"afade=t=out:st={total_duration - MUSIC_FADE_OUT}:d={MUSIC_FADE_OUT}"
        f"[music]"
    )

    # Mix voice + music
    if sfx_count > 0:
        # Build SFX delay chain — each whoosh at its section timestamp
        sfx_labels = []
        for i in range(sfx_count):
            ts = section_timestamps[i + 1]  # +1 because we skip first
            idx = sfx_input_idx + i
            label = f"sfx{i}"
            # Delay the SFX to play at the section transition timestamp
            delay_ms = int(ts * 1000)
            filter_parts.append(
                f"[{idx}:a]volume=0.4,adelay={delay_ms}|{delay_ms},"
                f"apad=whole_dur={total_duration}[{label}]"
            )
            sfx_labels.append(f"[{label}]")

        # Mix all: voice + music + all SFX
        all_inputs = f"[0:a][music]{''.join(sfx_labels)}"
        n_inputs = 2 + sfx_count
        filter_parts.append(
            f"{all_inputs}amix=inputs={n_inputs}:duration=first"
            f":dropout_transition=2,volume={1.5}[aout]"
        )
    else:
        # Just voice + music
        filter_parts.append(
            "[0:a][music]amix=inputs=2:duration=first"
            ":dropout_transition=2,volume=1.8[aout]"
        )

    filter_complex = ";".join(filter_parts)

    cmd = (
        ["ffmpeg", "-y"] + inputs +
        ["-filter_complex", filter_complex,
         "-map", "[aout]",
         "-c:a", "aac", "-b:a", "192k",
         str(output_path)]
    )

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"  ⚠️  Audio mix failed, using voiceover only: {result.stderr[-200:]}")
        # Fallback: just use voiceover
        cmd_fallback = [
            "ffmpeg", "-y", "-i", str(voiceover_path),
            "-c:a", "aac", "-b:a", "192k", str(output_path)
        ]
        subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=120)

    return output_path


def build_video(script: dict, image_paths: list[Path],
                image_prompts: list[dict], audio_segments: list[dict],
                music_path: Path = None, sfx_paths: dict = None) -> Path:
    """Assemble the full video with all production features.

    Strategy:
    1. Generate intro bumper
    2. For each section: create image clips with Ken Burns + text overlays
    3. Crossfade between image clips within each section
    4. Overlay section audio onto section video
    5. Concatenate: intro + all sections + end screen
    6. Mix background music + SFX into final audio track
    """
    clips_dir = OUTPUT_DIR / "clips"
    section_vids_dir = OUTPUT_DIR / "section_videos"
    clips_dir.mkdir(exist_ok=True)
    section_vids_dir.mkdir(exist_ok=True)

    # ── Generate intro bumper ──────────────────────────────────────
    print("  🎬 Generating intro bumper...")
    intro_path = section_vids_dir / "intro_bumper.mp4"
    _generate_intro_bumper(intro_path)

    # ── Group image prompts by section ─────────────────────────────
    section_images = {}
    for prompt_data in image_prompts:
        sid = prompt_data["section_index"]
        if sid not in section_images:
            section_images[sid] = []
        section_images[sid].append(prompt_data)

    section_video_paths = []
    section_timestamps = [0.0]  # Track where each section starts (for SFX)
    cumulative_time = 2.5  # After intro

    for sec_idx, audio_seg in enumerate(audio_segments):
        section_vid_path = section_vids_dir / f"section_{sec_idx:02d}.mp4"

        if section_vid_path.exists():
            section_video_paths.append(section_vid_path)
            cumulative_time += audio_seg["duration"]
            section_timestamps.append(cumulative_time)
            continue

        section_id = audio_seg["section_id"]
        sec_prompts = section_images.get(sec_idx, [])
        num_images = len(sec_prompts)

        if num_images == 0:
            continue

        print(f"  🎬 Section '{section_id}': {num_images} images, {audio_seg['duration']:.1f}s audio")

        # Use narrative-driven durations from image prompts (duration_hint)
        durations = [p.get("duration_hint", 0) for p in sec_prompts]
        hint_total = sum(durations)
        if hint_total > 0:
            # Scale hints to match actual audio duration
            scale = audio_seg["duration"] / hint_total
            durations = [round(d * scale, 2) for d in durations]
        else:
            # No hints — fall back to equal split
            base_duration = audio_seg["duration"] / num_images
            durations = [base_duration] * num_images
        # Fix any rounding drift
        remainder = audio_seg["duration"] - sum(durations)
        durations[-1] += remainder

        # Create individual image clips
        section_clip_paths = []
        zoom_dirs = ["in", "out"]

        for img_idx, prompt_data in enumerate(sec_prompts):
            global_idx = prompt_data["global_index"]
            if global_idx >= len(image_paths):
                break

            img_path = image_paths[global_idx]
            clip_path = clips_dir / f"clip_{sec_idx:02d}_{img_idx:03d}.mp4"

            if not clip_path.exists():
                _make_image_clip(
                    image_path=img_path,
                    duration=durations[img_idx],
                    key_phrase=prompt_data.get("key_phrase", ""),
                    clip_path=clip_path,
                    zoom_direction=zoom_dirs[img_idx % 2]
                )

            section_clip_paths.append(clip_path)

        # Concatenate section clips WITH crossfade transitions
        section_vid_silent = section_vids_dir / f"section_{sec_idx:02d}_silent.mp4"
        _concat_clips_with_crossfade(section_clip_paths, section_vid_silent)

        # Overlay audio onto section video
        cmd = [
            "ffmpeg", "-y",
            "-i", str(section_vid_silent),
            "-i", str(audio_seg["path"]),
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(section_vid_path)
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        # Clean up silent version
        section_vid_silent.unlink(missing_ok=True)

        section_video_paths.append(section_vid_path)
        cumulative_time += audio_seg["duration"]
        section_timestamps.append(cumulative_time)

    # ── Generate end screen ────────────────────────────────────────
    print("  🎬 Generating end screen...")
    end_screen_path = section_vids_dir / "end_screen.mp4"
    _generate_end_screen(end_screen_path)

    # ── Concatenate: intro + sections + end screen ─────────────────
    print("  🎬 Concatenating all parts...")
    video_no_music_path = OUTPUT_DIR / "video_no_music.mp4"
    final_concat = section_vids_dir / "final_concat.txt"

    all_parts = [intro_path] + section_video_paths + [end_screen_path]
    with open(final_concat, "w") as f:
        for part in all_parts:
            if part.exists():
                f.write(f"file '{part.resolve()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(final_concat),
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        str(video_no_music_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"Final concat failed: {result.stderr[-500:]}")

    # ── Mix background music + SFX ─────────────────────────────────
    final_path = OUTPUT_DIR / "final_video.mp4"

    if music_path and music_path.exists():
        print("  🎵 Mixing background music and SFX...")

        # Extract audio from concatenated video
        vo_extracted = OUTPUT_DIR / "voiceover_extracted.aac"
        cmd = [
            "ffmpeg", "-y", "-i", str(video_no_music_path),
            "-vn", "-c:a", "aac", "-b:a", "192k",
            str(vo_extracted)
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        # Get total duration
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "json", str(video_no_music_path)],
            capture_output=True, text=True
        )
        info = json.loads(probe.stdout)
        total_duration = float(info["format"]["duration"])

        # Mix audio layers
        mixed_audio = OUTPUT_DIR / "mixed_audio.aac"
        _mix_audio_layers(
            voiceover_path=vo_extracted,
            music_path=music_path,
            sfx_paths=sfx_paths or {},
            section_timestamps=section_timestamps,
            total_duration=total_duration,
            output_path=mixed_audio
        )

        # Combine video (no audio) + mixed audio
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_no_music_path),
            "-i", str(mixed_audio),
            "-c:v", "copy",
            "-map", "0:v", "-map", "1:a",
            "-movflags", "+faststart",
            str(final_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print("  ⚠️  Music mix failed, using video without background music")
            video_no_music_path.rename(final_path)

        # Cleanup temp files
        vo_extracted.unlink(missing_ok=True)
        mixed_audio.unlink(missing_ok=True)
        video_no_music_path.unlink(missing_ok=True)
    else:
        # No music — just rename
        video_no_music_path.rename(final_path)

    # Get final stats
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "json", str(final_path)],
        capture_output=True, text=True
    )
    info = json.loads(probe.stdout)
    duration = float(info["format"]["duration"])
    size_mb = final_path.stat().st_size / (1024 * 1024)

    print(f"🎬 Final video: {duration:.0f}s ({duration / 60:.1f} min), {size_mb:.1f} MB")

    return final_path
