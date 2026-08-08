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
    image-to-narration sync. Meme-face character with emotions throughout.
    Includes pattern interrupts, tangent questions, curiosity hooks.
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

TONE: Talk like a real person. Casual. Conversational. Use simple everyday words. NO fancy vocabulary. NO essay writing.

GOOD example: "So you know how in the West, you tip your waiter? In Japan, that's basically telling them they're poor."
BAD example: "The cultural implications of gratuity in East Asian societies present a fascinating contradiction."

RULES:
- Use "you", "we", "like", "basically", "so", "right?" — how people actually talk
- Short sentences. One idea each. Easy to follow.
- Explain everything like the viewer is 12 years old
- Drop in the original Asian word (feng shui, pantang, etc.) but ALWAYS explain it right after
- NO jargon, NO academic language, NO "cultural significance" type phrases
- Keep language CLEAN — no words like "insult", "offensive", "angry" (image AI flags these)

ENGAGEMENT RULES (critical):
- CURIOSITY HOOK: First 2 seconds must open a loop the viewer HAS to close. Make them think "wait, why?"
- PATTERN INTERRUPTS: Every ~20 seconds (~4 sections), break the expected flow. Ask a weird tangent question, drop a shocking fact, flip an assumption. The viewer's brain should go "wait what?" and re-engage.
- "WHAT ABOUT X?" TANGENT: Include at least ONE unexpected lateral question the viewer never considered. Example: talking about not cutting nails at night → "but wait, what about cutting HAIR at night?" This makes them feel like they're discovering something nobody talks about.
- SATISFYING ENDING: Close every loop you opened. The viewer should feel smarter than when they started. Tie the ending back to the opening hook.

AUDIENCE: People scrolling TikTok/YouTube who know nothing about Asian culture. Hook them in 2 seconds.

FORMAT: 1-MINUTE VIDEO. ~150-170 words TOTAL.

EACH SECTION = ONE SENTENCE (10-20 words max). Write 12-14 sections.

ALREADY COVERED (do NOT repeat):
{done_str}

Pick ONE topic: an everyday Asian habit, superstition, or tradition that sounds crazy but has a real explanation.

STRUCTURE (12-14 sections):
- hook_1 to hook_3: Open a curiosity loop. Paint a scene, then hit them with something unexpected. "Imagine you're at a dinner in China and someone hands you a clock..." Make them go "why is that weird?"
- build_1 to build_3: Give context. Each fact more surprising than the last. Around build_3, drop a PATTERN INTERRUPT — a weird tangent or "what about X?" question they never considered.
- twist_1 to twist_3: Flip what they assumed. "But here's the thing nobody tells you..." Around twist_2, another pattern interrupt — a surprising connection to something completely different.
- payoff_1 to payoff_2: The real explanation. Make it SO satisfying they want to tell someone. "So THAT'S why..."
- close_1 to close_2: Tie it back to the opening loop. Close it perfectly. LAST section MUST end with: "Your grandma's rules — finally explained."

VISUAL NOTES RULES:
- Main character: white circle head, big round dot eyes, small line mouth, messy brown hair, dark hoodie
- Show EMOTIONS on the character: wide shocked eyes, dropped jaw, sweat drops, floating question marks, exclamation marks, thought bubbles with short text
- Show SCENE REACTIONS: action speed lines behind character, shaking effect lines, floating symbols
- ONE clear scene per section, specific objects and detailed colorful background
- CLEAN — no negative emotions, no conflict words. Just expressive poses, reactions, and objects.
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
      "visual_notes": "Character with shocked wide eyes at dinner table, chopsticks in rice bowl, speed lines"
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
