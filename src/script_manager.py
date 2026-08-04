"""Script manager — reads pre-written Claude scripts, falls back to Gemini."""

import json
import shutil
from pathlib import Path
from src.config import (
    SCRIPTS_QUEUE_DIR, SCRIPTS_DONE_DIR, SCRIPT_LOW_THRESHOLD
)
from src.gemini_helper import generate_text


def get_queue_count() -> int:
    """Count scripts remaining in the queue."""
    return len(list(SCRIPTS_QUEUE_DIR.glob("*.json")))


def is_queue_low() -> bool:
    """Check if script queue is running low."""
    return get_queue_count() < SCRIPT_LOW_THRESHOLD


def get_next_script() -> dict:
    """Get the next script from the queue.

    If queue is empty, generates one with Gemini as backup.
    Returns the full script dict.
    """
    scripts = sorted(SCRIPTS_QUEUE_DIR.glob("*.json"))

    if scripts:
        script_path = scripts[0]
        script = json.loads(script_path.read_text())

        # Move to done folder
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
    """Generate a script using Gemini when Claude scripts run out."""

    # Load done scripts to avoid repeats
    done_topics = []
    for f in SCRIPTS_DONE_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            done_topics.append(data.get("title", ""))
        except Exception:
            pass

    done_str = "\n".join(f"- {t}" for t in done_topics[-50:]) if done_topics else "None"

    prompt = f"""You are a scriptwriter for "CuriousAsian", a YouTube channel that explains everyday cultural habits, superstitions, and traditions people follow blindly without knowing why.

BRAND VOICE:
- Curious storyteller — warm, fascinated, sharing discoveries with a friend
- Fast-paced, punchy, value-dense — no filler (inspired by Alex Hormozi / Ali Abdaal energy)
- English narration, uses original Asian terms (feng shui, pantang, etc.) but always explains them
- Preserve and respect traditions — but explain the real origin so viewers understand, not fear
- Light and fun, not lecture-y

AUDIENCE: Asian diaspora — people who grew up between cultures

ALREADY COVERED (do NOT repeat):
{done_str}

Pick ONE topic: an everyday habit, superstition, pantang, or tradition (50% Asian, 50% global mix) that most people follow but never questioned WHY.

Write a complete video script. Structure:

1. HOOK (2-3 punchy sentences) — shocking fact or "wait, what?" question. NO "hey guys" intro.
2. THE FEAR — what people believe will happen if they break this rule
3. THE REAL ORIGIN — where this tradition actually came from (history, dynasty, religion, etc.)
4. THE SCIENCE — any scientific, psychological, or practical explanation
5. AROUND THE WORLD — how other cultures handle the same thing differently
6. THE TWIST — something unexpected about this topic
7. THE VERDICT — preserve the tradition, explain what it really means, empower the viewer

Total narration: 800-1100 words (produces 5-8 minutes of audio).

For each section, include a "visual_notes" field — a brief description of what visuals should accompany it (the image generator will expand these).

Return ONLY valid JSON:
{{
  "title": "YouTube title (compelling, under 70 chars)",
  "description": "YouTube description (2-3 paragraphs + engagement question)",
  "tags": ["tag1", "tag2", ...],
  "sections": [
    {{
      "id": "hook",
      "narration": "Full narration text for this section...",
      "visual_notes": "Brief visual description for this section"
    }},
    ...
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

    script = json.loads(text)
    script["_source"] = "gemini_backup"

    total_words = sum(len(s["narration"].split()) for s in script["sections"])
    print(f"📝 Gemini backup script: '{script['title']}' ({total_words} words)")

    return script
