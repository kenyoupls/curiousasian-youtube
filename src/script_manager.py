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
    """Get the next script from queue, or generate one with Gemini."""
    scripts = sorted(SCRIPTS_QUEUE_DIR.glob("*.json"))

    if scripts:
        script_path = scripts[0]
        script = json.loads(script_path.read_text())
        done_path = SCRIPTS_DONE_DIR / script_path.name
        shutil.move(str(script_path), str(done_path))

        remaining = get_queue_count()
        print(f"📝 Using script: {script.get('title', script_path.stem)}")
        print(f"   Scripts remaining: {remaining}")
        script["_source"] = "claude"
        return script
    else:
        print("⚠️  Script queue EMPTY — generating with Gemini backup...")
        return _generate_gemini_backup_script()


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

    prompt = f"""You are a scriptwriter for "CuriousAsian", a YouTube channel that explains everyday cultural habits, superstitions, and traditions.

BRAND VOICE:
- Curious storyteller — warm, fascinated, sharing discoveries with a friend
- Fast-paced, punchy, value-dense — no filler
- English narration, uses original Asian terms (feng shui, pantang, etc.) but always explains them
- Preserve and respect traditions — explain the real origin
- Light and fun, not lecture-y

AUDIENCE: Asian diaspora — people who grew up between cultures

VISUAL STYLE: One recurring stick figure character (like OverSimplified YouTube channel). Round white head, dot eyes, messy hair, simple clothing. The character appears in EVERY scene with different objects/context around them.

ALREADY COVERED (do NOT repeat):
{done_str}

Pick ONE topic: an everyday habit, superstition, or tradition that most people follow but never questioned WHY.

Write a complete video script. IMPORTANT: Each section should be SHORT — just 1-2 sentences of narration. This makes each section sync to exactly one image/scene.

Structure your sections like this (use these EXACT section IDs):
- hook_1, hook_2 (2-3 short punchy sentences, split into separate sections)
- fear_1, fear_2, fear_3 (what people believe will happen — split per idea)
- origin_1, origin_2, origin_3, origin_4 (where the tradition came from)
- science_1, science_2 (scientific or practical explanation)
- world_1, world_2 (how other cultures handle it)
- twist_1, twist_2 (something unexpected)
- verdict_1, verdict_2 (what it really means, empower the viewer)

Each section gets ONE image, so each narration should describe ONE clear visual moment.

Total narration: 800-1100 words across all sections.

For each section, include:
- "narration": 1-2 sentences (what the narrator says)
- "visual_notes": Brief description of what to show (stick figure + context/objects)

Return ONLY valid JSON:
{{
  "title": "YouTube title (compelling, under 70 chars)",
  "description": "YouTube description (2-3 paragraphs + engagement question)",
  "tags": ["tag1", "tag2"],
  "sections": [
    {{
      "id": "hook_1",
      "narration": "One or two sentences...",
      "visual_notes": "Stick figure character with X object, Y background"
    }},
    {{
      "id": "hook_2",
      "narration": "Next sentence...",
      "visual_notes": "Stick figure character doing Z"
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
