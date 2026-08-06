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

    prompt = f"""You write scripts for "CuriousAsian" — a YouTube channel that explains Asian cultural habits in a fun, casual way. Like you're telling a friend over coffee.

TONE: Talk like a real person. Casual. Conversational. Like explaining something cool to your friend who knows nothing about Asian culture. Use simple everyday words. NO fancy vocabulary. NO essay writing.

GOOD example: "So you know how in the West, you tip your waiter? In Japan, that's basically telling them they're poor."
BAD example: "The cultural implications of gratuity in East Asian societies present a fascinating contradiction."

RULES:
- Use "you", "we", "like", "basically", "so", "right?" — how people actually talk
- Short sentences. One idea each. Easy to follow.
- Explain everything like the viewer is 12 years old
- Drop in the original Asian word (feng shui, pantang, etc.) but ALWAYS explain it right after
- NO jargon, NO academic language, NO "cultural significance" type phrases
- Keep language CLEAN — no words like "insult", "offensive", "angry" (image AI flags these)
- Include 2 "wait what?" moments — things that surprise the viewer

AUDIENCE: People scrolling TikTok/YouTube who know nothing about Asian culture. Hook them in 2 seconds.

FORMAT: 1-MINUTE VIDEO. ~150-170 words TOTAL.

EACH SECTION = ONE SENTENCE (10-20 words max). Write 12-14 sections.

ALREADY COVERED (do NOT repeat):
{done_str}

Pick ONE topic: an everyday Asian habit, superstition, or tradition that sounds crazy but has a real explanation.

STRUCTURE (12-14 sections):
- hook_1 to hook_3: Paint a scene. "Imagine you're at a restaurant in Tokyo..." Then hit them with the weird part. Make them go "wait what?"
- build_1 to build_3: Give context. Each fact more surprising than the last. "And it gets weirder..."
- twist_1 to twist_3: Flip what they assumed. "But here's the thing nobody tells you..."
- payoff_1 to payoff_2: The real explanation. Make it satisfying. "So THAT'S why..."
- close_1 to close_2: Tie it back to the opening. LAST section MUST end with: "Your grandma's rules — finally explained."

VISUAL NOTES RULES:
- Main character: boy with round head, dot eyes, line mouth, messy brown hair, stick body
- ONE clear scene per section, specific objects and background
- Warm earth-toned colors, subjects centered in frame
- CLEAN — no negative emotions, no conflict words. Just poses and objects.
- Max 100 characters

Return ONLY valid JSON:
{{
  "title": "YouTube title (casual, under 70 chars, use CAPS for one key word)",
  "description": "Short YouTube description + engagement question",
  "tags": ["tag1", "tag2", "CuriousAsian"],
  "sections": [
    {{
      "id": "hook_1",
      "narration": "One casual sentence — how you'd say it to a friend (10-20 words).",
      "visual_notes": "Centered: boy in specific setting, specific objects, warm background"
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
