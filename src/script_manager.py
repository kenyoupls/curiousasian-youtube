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

    prompt = f"""You are a scriptwriter for "CuriousAsian", a YouTube channel that explains Asian cultural habits, traditions, and superstitions in a way that's entertaining, educational, and impossible to stop watching.

STYLE: Hybrid — Ink Explainer's immersive "you are there" storytelling hooks + MrBeast's fast-paced reveals.

GOLDEN RULE: The viewer must NEVER predict the next sentence. Every line must surprise, contradict, or shift the angle. If a viewer can finish your sentence — you've lost them.

HOOK TECHNIQUE (Ink Explainer style):
- Open with an IMMERSIVE scene: "Imagine you're sitting in a Tokyo restaurant. You've just finished the best sushi of your life. You leave a tip on the table. And then... the waiter CHASES you down the street."
- Put the viewer IN the moment — use "you" and present tense
- Then SNAP to the consequence/contradiction — MrBeast pace kicks in

ENERGY — MrBeast meets OverSimplified:
- Every SINGLE SENTENCE must earn the next second. Zero filler. Zero predictability.
- Use dramatic reveals: "But HERE'S what no one tells you..."
- Short. Punchy. Sentences. Like. This.
- Emotional rollercoaster: immersion → shock → curiosity → "no way" → mind blown → satisfying twist
- Use original Asian terms (omotenashi, pantang, feng shui) but always explain them
- Keep language CLEAN — no words like "insult", "offensive", "angry" (image AI flags these)
- TWIST every ~30 seconds. A 1-min video needs at least 2 "wait what" moments.

AUDIENCE: Asian diaspora + culturally curious. They scroll fast. 1 second to hook them.

FORMAT: 1-MINUTE VIDEO. ~150-170 words TOTAL. Every word must earn its place.

CRITICAL RULE — EACH SECTION = ONE SENTENCE (10-20 words max).
EVERY section gets its OWN image. More sections = more visual cuts = more engaging.
We want images changing every 2-3 seconds. So write 12-14 sections, each just ONE punchy sentence.

ALREADY COVERED (do NOT repeat):
{done_str}

Pick ONE topic: an everyday habit, superstition, or tradition with a WILD explanation.

Structure: 12-14 sections. Each = ONE sentence + visual_notes for that moment.
- hook_1 through hook_3: IMMERSIVE opening (Ink Explainer style). Put viewer IN the scene. Then SNAP to the shocking consequence. The viewer should think "wait WHAT?" within 3 seconds.
- build_1 through build_3: Context that makes them care — but each fact more surprising than the last. Never explain the obvious.
- twist_1 through twist_3: First "no way" moment at ~30 seconds. Flip everything they assumed.
- payoff_1 through payoff_3: The REAL answer. Mind-blow. Make them want to share.
- close_1 through close_2: Satisfying reframe + callback to the hook. LAST section MUST end with the tagline: "Your grandma's rules — finally explained."

UNPREDICTABILITY RULES:
- Never follow a question with its obvious answer
- Never follow a negative with a positive (or vice versa) predictably
- Each sentence should raise a NEW question the viewer didn't expect
- Use contrasts: "Americans do X. Japanese do the OPPOSITE."
- Use numbers for shock: specific stats, comparisons, amounts

VISUAL NOTES RULES:
- The main character is ALWAYS a boy with round head, dot eyes, line mouth, messy brown hair, stick body
- Describe ONE clear scene with MULTIPLE characters if relevant
- Specific objects, specific background/setting, warm earth-toned colors
- Keep subjects CENTERED in the frame (for vertical crop to Reels/TikTok)
- CLEAN — no negative emotions, no conflict words. Describe poses and objects only.
- Max 100 characters per visual_notes

Return ONLY valid JSON:
{{
  "title": "YouTube title (compelling, under 70 chars, use CAPS for one key word)",
  "description": "Short YouTube description + engagement question",
  "tags": ["tag1", "tag2", "CuriousAsian"],
  "sections": [
    {{
      "id": "hook_1",
      "narration": "One punchy sentence — the SHOCKING thing, not the setup (10-20 words).",
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
