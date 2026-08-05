"""Script manager — reads pre-written Claude scripts, falls back to Gemini."""

import json
import re
import shutil
from pathlib import Path
from src.config import (
    SCRIPTS_QUEUE_DIR, SCRIPTS_DONE_DIR, SCRIPT_LOW_THRESHOLD
)
from src.gemini_helper import generate_text


def _clean_json(text: str) -> str:
    """Fix common Gemini JSON issues."""
    text = re.sub(r',\s*([}\]])', r'\1', text)
    text = text.strip().strip('﻿')
    return text


def get_queue_count() -> int:
    return len(list(SCRIPTS_QUEUE_DIR.glob("*.json")))


def is_queue_low() -> bool:
    return get_queue_count() < SCRIPT_LOW_THRESHOLD


def get_next_script() -> dict:
    """Get the next script from queue, or generate one with Gemini.

    NOTE: Script stays in queue until mark_script_done() is called after
    successful pipeline completion. This prevents losing scripts on failure.
    """
    scripts = sorted(SCRIPTS_QUEUE_DIR.glob("*.json"))

    if scripts:
        script_path = scripts[0]
        script = json.loads(script_path.read_text())

        remaining = get_queue_count() - 1  # excluding current
        print(f"📝 Using script: {script.get('title', script_path.stem)}")
        print(f"   Scripts remaining: {remaining}")
        script["_source"] = "claude"
        script["_queue_path"] = str(script_path)  # for mark_script_done()
        return script
    else:
        print("⚠️  Script queue EMPTY — generating with Gemini backup...")
        return _generate_gemini_backup_script()


def mark_script_done(script: dict):
    """Move script from queue to done. Call ONLY after pipeline succeeds."""
    queue_path = script.get("_queue_path")
    if not queue_path:
        return
    queue_path = Path(queue_path)
    if queue_path.exists():
        done_path = SCRIPTS_DONE_DIR / queue_path.name
        shutil.move(str(queue_path), str(done_path))
        print(f"   ✅ Script moved to done: {queue_path.name}")


def _generate_gemini_backup_script() -> dict:
    """Generate a script using Gemini when queue is empty.

    Script has granular sections (1-2 sentences each) for tight
    image-to-narration sync. One stick figure character throughout.
    """
    # Load done scripts to avoid repeats
    done_topics = []
    for f in SCRIPTS_DONE_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            done_topics.append(data.get("title", ""))
        except Exception:
            pass

    done_str = "\n".join(f"- {t}" for t in done_topics[-50:]) if done_topics else "None"

    prompt = f"""You are a scriptwriter for "CuriousAsian", a YouTube Shorts / 1-minute explainer channel about cultural habits, superstitions, and traditions.

ENERGY & TONE — MrBeast meets OverSimplified:
- HOOK HARD in the first 5 seconds — something shocking, funny, or "wait WHAT?"
- Every sentence must earn the next second of attention
- Use dramatic reveals: "And THAT'S when it gets crazy..."
- Short punchy sentences. No filler. No "in this video we'll explore..."
- Emotional rollercoaster: shock → curiosity → "mind blown" → satisfying twist
- End with a mic-drop moment that makes people want to share
- English narration, uses original Asian terms (feng shui, omotenashi, pantang) but always explains them

AUDIENCE: Asian diaspora + culturally curious viewers. They scroll fast — you have 3 seconds to hook them.

FORMAT: 1-MINUTE VIDEO (~150-170 words total narration). This is SHORT. Every word counts.

ALREADY COVERED (do NOT repeat):
{done_str}

Pick ONE topic: an everyday habit, superstition, or tradition that sounds boring but has a WILD explanation behind it.

Structure: exactly 3 sections. Each section = ~50-60 words.
- "hook": Open with a scenario that creates instant curiosity or shock. Paint a vivid picture. Make the viewer say "wait, really?"
- "origin": The surprising WHY behind it. Historical, scientific, or cultural. Build curiosity, drop a reveal.
- "twist": The mind-blowing reframe. Flip the viewer's assumption. End with the channel tagline: "Your grandma's rules — finally explained."

Each section should have 2-3 clear visual moments described in visual_notes.

Return ONLY valid JSON:
{{
  "title": "YouTube title (compelling, under 70 chars, use CAPS for one key word)",
  "description": "YouTube description (short + engagement question)",
  "tags": ["tag1", "tag2", "CuriousAsian"],
  "sections": [
    {{
      "id": "hook",
      "narration": "50-60 words of high-energy narration...",
      "visual_notes": "Scene 1: ... Scene 2: ... Scene 3: ..."
    }},
    {{
      "id": "origin",
      "narration": "50-60 words...",
      "visual_notes": "Scene 1: ... Scene 2: ..."
    }},
    {{
      "id": "twist",
      "narration": "50-60 words ending with mic-drop...",
      "visual_notes": "Scene 1: ... Scene 2: ... Scene 3: subscribe button"
    }}
  ]
}}

Return valid JSON only, no markdown formatting."""

    raw = generate_text(prompt)
    if not raw:
        raise RuntimeError("Gemini returned empty response for script generation")

    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    text = _clean_json(text)

    try:
        script = json.loads(text)
    except json.JSONDecodeError:
        fix_prompt = f"Fix this broken JSON object and return ONLY valid JSON:\n{text}"
        fixed = generate_text(fix_prompt)
        if not fixed:
            raise
        fixed = fixed.strip()
        if fixed.startswith("```"):
            fixed = fixed.split("\n", 1)[1]
            fixed = fixed.rsplit("```", 1)[0]
        fixed = _clean_json(fixed)
        script = json.loads(fixed)

    script["_source"] = "gemini_backup"
    total_words = sum(len(s["narration"].split()) for s in script["sections"])
    print(f"📝 Gemini backup: '{script['title']}' ({total_words} words, {len(script['sections'])} sections)")
    return script
