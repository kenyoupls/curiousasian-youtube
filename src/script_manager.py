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

    prompt = f"""You are a scriptwriter for "CuriousAsian", a viral YouTube channel that explains cultural habits and traditions.

ENERGY — MrBeast meets OverSimplified. MAX ENGAGEMENT:
- HOOK in 3 seconds — something SHOCKING or "wait WHAT?"
- Every SINGLE SENTENCE must earn the next second. Zero filler.
- Use dramatic reveals: "But HERE'S the part that broke my brain..."
- Short. Punchy. Sentences. Like. This.
- Emotional rollercoaster: shock → curiosity → "no way" → mind blown → satisfying twist
- End with a mic-drop that makes people SHARE
- Use original Asian terms (omotenashi, pantang, feng shui) but always explain them
- Keep language CLEAN — no words like "insult", "offensive", "angry" (image AI flags these)

AUDIENCE: Asian diaspora + culturally curious. They scroll fast. 3 seconds to hook them.

FORMAT: 1-MINUTE VIDEO. ~150-170 words TOTAL. Every word must earn its place.

CRITICAL RULE — EACH SECTION = ONE SENTENCE (10-20 words max).
This is because EVERY section gets its OWN image. More sections = more visual cuts = more engaging.
We want images changing every 2-3 seconds. So write 10-12 sections, each just ONE punchy sentence.

ALREADY COVERED (do NOT repeat):
{done_str}

Pick ONE topic: an everyday habit, superstition, or tradition with a WILD explanation.

Structure: 10-12 sections. Each = ONE sentence + visual_notes for that moment.
- hook_1 through hook_4: Build a vivid scenario that creates instant curiosity
- origin_1 through origin_4: The surprising WHY. Drop reveals one by one.
- twist_1 through twist_4: Mind-blowing reframe. Last section ends with "Your grandma's rules — finally explained."

Each visual_notes should describe ONE clear scene — character doing something specific with specific objects.
Keep visual_notes CLEAN — no negative emotions, no conflict words. Describe poses and objects only.

Return ONLY valid JSON:
{{
  "title": "YouTube title (compelling, under 70 chars, use CAPS for one key word)",
  "description": "Short YouTube description + engagement question",
  "tags": ["tag1", "tag2", "CuriousAsian"],
  "sections": [
    {{
      "id": "hook_1",
      "narration": "One punchy sentence (10-20 words).",
      "visual_notes": "Boy doing X with Y object, Z expression"
    }},
    {{
      "id": "hook_2",
      "narration": "Next punchy sentence.",
      "visual_notes": "Boy in different pose with different objects"
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
