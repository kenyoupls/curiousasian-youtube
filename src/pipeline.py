#!/usr/bin/env python3
"""Main pipeline — orchestrates: script → audio → image prompts → images → video.

If image generation fails for a script, skips it and tries the next one.
"""

import sys
import json
import shutil
import traceback
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import OUTPUT_DIR, DATA_DIR
from src.script_manager import get_next_script, is_queue_low, get_queue_count
from src.voice_generator import generate_all_audio
from src.image_prompt_generator import generate_all_image_prompts
from src.image_generator import generate_all_images, generate_thumbnail, ImageGenerationFailed
from src.sfx_generator import generate_all_sfx, generate_background_music
from src.video_builder import build_video
from src.telegram_notifier import (
    notify_scripts_low, notify_video_complete, notify_pipeline_failed
)

MAX_SCRIPT_RETRIES = 3  # Try up to 3 different scripts before giving up


def clean_output():
    """Remove previous output files."""
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(exist_ok=True)


def save_run_log(log: dict):
    """Save a log of this run."""
    log_dir = DATA_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_path = log_dir / f"run_{date_str}.json"
    log_path.write_text(json.dumps(log, indent=2, default=str))


def _build_video_from_script(script: dict, run_log: dict) -> dict:
    """Run Steps 2-7 for a single script. Returns run_log on success.

    Raises ImageGenerationFailed if images can't be generated — caller
    should try the next script.
    """
    run_log["steps"]["script"] = {
        "title": script["title"],
        "source": script.get("_source", "unknown"),
        "sections": len(script["sections"]),
    }

    # Save script copy
    (OUTPUT_DIR / "script.json").write_text(json.dumps(script, indent=2))

    # ── Step 2: Generate audio ─────────────────────────────────
    print("\n🔊 STEP 2: Generating voiceover...")
    audio_segments = generate_all_audio(script)
    total_duration = sum(s["duration"] for s in audio_segments)
    run_log["steps"]["audio"] = {
        "segments": len(audio_segments),
        "total_seconds": round(total_duration, 1)
    }

    # ── Step 3: Generate image prompts (narrative-driven) ──────
    print("\n🎨 STEP 3: Generating image prompts (narrative-driven)...")
    image_prompts = generate_all_image_prompts(script, audio_segments)
    run_log["steps"]["image_prompts"] = len(image_prompts)

    # Save prompts for reference
    (OUTPUT_DIR / "image_prompts.json").write_text(
        json.dumps(image_prompts, indent=2, default=str)
    )

    # ── Step 4: Generate images (raises ImageGenerationFailed) ─
    print("\n🖼️  STEP 4: Generating images...")
    image_paths = generate_all_images(image_prompts)
    run_log["steps"]["images"] = len(image_paths)

    # ── Step 5: Generate SFX + background music ────────────────
    print("\n🔊 STEP 5: Generating SFX + background music...")
    sfx_paths = generate_all_sfx()
    music_path = generate_background_music(total_duration)
    run_log["steps"]["audio_production"] = {
        "sfx": list(sfx_paths.keys()),
        "music_duration": round(total_duration + 10, 1)
    }

    # ── Step 6: Generate thumbnail ─────────────────────────────
    print("\n🎨 STEP 6: Generating thumbnail...")
    thumbnail_path = generate_thumbnail(script)

    # ── Step 7: Assemble video ─────────────────────────────────
    print("\n🎬 STEP 7: Assembling video...")
    video_path = build_video(
        script, image_paths, image_prompts, audio_segments,
        music_path=music_path, sfx_paths=sfx_paths
    )
    run_log["steps"]["video"] = str(video_path)

    return {
        "total_duration": total_duration,
        "image_count": len(image_paths),
        "video_path": video_path,
        "thumbnail_path": thumbnail_path,
    }


def run_pipeline():
    """Run the full pipeline. Retries with next script if images fail."""

    run_log = {
        "started_at": datetime.now().isoformat(),
        "steps": {},
        "status": "running",
        "skipped_scripts": []
    }

    try:
        print("\n" + "=" * 60)
        print("🚀 CuriousAsian Pipeline — Starting")
        print("=" * 60)

        # ── Check script queue health ──────────────────────────────
        if is_queue_low():
            remaining = get_queue_count()
            print(f"⚠️  Script queue low: {remaining} remaining")
            notify_scripts_low(remaining)

        # ── Try scripts until one succeeds ─────────────────────────
        result = None

        for attempt in range(MAX_SCRIPT_RETRIES):
            # Clean output for each attempt
            clean_output()

            # ── Step 1: Get script ─────────────────────────────────
            print(f"\n📝 STEP 1: Getting script (attempt {attempt + 1}/{MAX_SCRIPT_RETRIES})...")
            script = get_next_script()

            try:
                result = _build_video_from_script(script, run_log)
                break  # Success — exit retry loop

            except ImageGenerationFailed as e:
                print(f"\n⚠️  Image generation failed for '{script['title']}': {e}")
                print(f"    Skipping to next script...")
                run_log["skipped_scripts"].append({
                    "title": script["title"],
                    "reason": str(e),
                    "attempt": attempt + 1
                })
                continue

        if result is None:
            raise RuntimeError(
                f"All {MAX_SCRIPT_RETRIES} scripts failed image generation. "
                f"Skipped: {[s['title'] for s in run_log['skipped_scripts']]}"
            )

        # ── Done ───────────────────────────────────────────────────
        run_log["status"] = "success"
        run_log["completed_at"] = datetime.now().isoformat()
        run_log["total_duration_seconds"] = round(result["total_duration"], 1)

        print("\n" + "=" * 60)
        print("✅ VIDEO READY FOR UPLOAD!")
        print(f"   Title: {script['title']}")
        print(f"   Duration: {result['total_duration']:.0f}s ({result['total_duration'] / 60:.1f} min)")
        print(f"   Images: {result['image_count']}")
        print(f"   Script source: {script.get('_source', 'unknown')}")
        print(f"   Video: {result['video_path']}")
        print(f"   Thumbnail: {result['thumbnail_path']}")
        if run_log["skipped_scripts"]:
            print(f"   Skipped scripts: {len(run_log['skipped_scripts'])}")
        print("=" * 60)

        # Notify via Telegram
        notify_video_complete(
            title=script["title"],
            duration=result["total_duration"],
            source=script.get("_source", "unknown")
        )

    except Exception as e:
        run_log["status"] = "failed"
        run_log["error"] = str(e)
        run_log["traceback"] = traceback.format_exc()

        print(f"\n❌ PIPELINE FAILED: {e}")
        traceback.print_exc()

        notify_pipeline_failed(str(e))
        raise

    finally:
        save_run_log(run_log)

    return run_log


if __name__ == "__main__":
    run_pipeline()
