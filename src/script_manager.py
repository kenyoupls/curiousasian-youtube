"""Script manager — reads pre-written Claude scripts, falls back to Gemini."""

import json
import re
import shutil
from pathlib import Path
from src.config import (
    SCRIPTS_QUEUE_DIR, SCRIPTS_DONE_DIR, SCRIPT_LOW_THRESHOLD
)
from src.gemini_helper import generate_text


# ── Rotating CTA endings ─────────────────────────────────────────────
# Mixed each video. The close section picks one based on done-script count.
ROTATING_CTAS = [
    # Engagement question — makes them comment
    "Drop a comment — what rule did YOUR grandma have that you never understood?",
    "What's the weirdest rule you grew up with? Tell me in the comments.",
    "Comment below — which of these did YOU grow up hearing?",
    # Follow hook — makes them subscribe
    "Follow for more — tomorrow's one is even crazier.",
    "Subscribe if you want your mind blown again tomorrow.",
    "Hit follow — I explain one weird rule every single day.",
    # Teaser — makes them watch next
    "Next one: why you should NEVER whistle at night. Trust me.",
    "Wait till you hear what happens when you point at the moon.",
    "Tomorrow I'll explain why you never stick chopsticks straight up. Stay tuned.",
]


def _pick_cta() -> str:
    """Pick a CTA based on how many scripts have been done (rotates through list)."""
    done_count = len(list(SCRIPTS_DONE_DIR.glob("*.json")))
    return ROTATING_CTAS[done_count % len(ROTATING_CTAS)]


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
    cta = _pick_cta()

    prompt = f"""You write scripts for "CuriousAsian" — a YouTube Shorts channel about Asian cultural habits.

TONE: You're a funny storyteller with sarcasm. Like you're narrating something ridiculous that actually happened. React to the facts. Make jokes. Be dramatic on purpose.

GOOD examples:
- "Picture this. You're chilling at home, trimming your nails. Your Asian grandma walks in and... absolute chaos. Apparently you just invited death into the house. Cool. Thanks grandma."
- "So in Korea, if someone gives you a fan for your birthday, that's basically a death threat. No I'm not joking. They literally think the fan will steal your soul while you sleep."
- "Bro. In Japan, tipping your waiter is like telling them they're poor. You're trying to be nice and they're standing there like... did you just disrespect me?"

BAD examples (too documentary):
- "The cultural implications of gratuity in East Asian societies present a fascinating contradiction."
- "Let me explain the historical significance of this ancient tradition."

RULES:
- Write like you're REACTING to the facts, not lecturing about them
- Use sarcasm, dramatic pauses, and punchlines
- Short punchy sentences. One idea each.
- React to your own facts: "Wait, it gets worse." / "Yeah. That's a thing." / "Cool. Thanks grandma."
- Drop the original Asian word (feng shui, pantang, etc.) but ALWAYS explain it right after
- NO jargon, NO academic language, NO documentary narrator voice
- Keep language CLEAN — no words like "insult", "offensive", "angry" (image AI flags these)

ENGAGEMENT RULES (critical):
- CURIOSITY HOOK: First 2 seconds must open a loop. Paint a scene, then hit them with something absurd.
- PATTERN INTERRUPTS: Every ~20 seconds (~4 sections), break the flow. Ask a weird tangent, drop a shocking fact, flip an assumption. "Wait what?" moment.
- "WHAT ABOUT X?" TANGENT: At least ONE unexpected lateral question. Example: talking about not cutting nails at night → "but wait, what about cutting HAIR at night?" Makes them feel like they're discovering something nobody talks about.
- SATISFYING ENDING: Close every loop. Tie back to the opening hook. Viewer should feel smarter.

AUDIENCE: People scrolling TikTok/Shorts who know nothing about Asian culture. Hook them in 2 seconds.

FORMAT: 1-MINUTE VIDEO. ~150-170 words TOTAL.

EACH SECTION = ONE SENTENCE (10-20 words max). Write 12-14 sections.

ALREADY COVERED (do NOT repeat):
{done_str}

Pick ONE topic: an everyday Asian habit, superstition, or tradition that sounds crazy but has a real explanation.

STRUCTURE (12-14 sections):
- hook_1 to hook_3: Paint a scene, then drop something absurd. Make them go "wait, why?" React to it yourself.
- build_1 to build_3: Give context with escalating surprises. Around build_3, drop a PATTERN INTERRUPT — weird tangent or "what about X?" question.
- twist_1 to twist_3: Flip what they assumed. "But here's the thing nobody tells you..." Around twist_2, another pattern interrupt.
- payoff_1 to payoff_2: The real explanation. Make it SO satisfying. "So THAT'S why..."
- close_1 to close_2: Tie back to the opening. Close it perfectly. LAST section MUST end with this exact CTA: "{cta}"

VISUAL NOTES RULES:
- ART STYLE: 90s vintage anime, cute retro anime cel-shaded illustration
- MAIN CHARACTER (always present): cute boy with round face, big sparkling eyes, messy brown hair, dark gray hoodie, olive cargo pants, brown boots
- SECONDARY CHARACTER (when needed): vintage anime style character matching the topic (e.g., "anime grandma with white hair scolding" or "anime chef looking shocked"). Keep them in the same retro anime style.
- Show EMOTIONS: sparkling eyes, sweat drops, floating question marks, exclamation marks, thought bubbles
- ONE clear scene per section, specific objects, warm colorful background
- CLEAN — no negative emotions, no conflict words. Just expressive reactions and objects.
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
