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

STYLE: Hybrid — Ink Explainer's immersive "you are there" storytelling hooks + MrBeast's fast-paced reveals and pattern interruptions.

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
- Pattern interruptions every ~45s: sudden questions, unexpected analogies, "wait it gets worse", number drops
- TWIST every ~60 seconds. An 8-min video needs at least 6 "wait what" moments.

AUDIENCE: Asian diaspora + culturally curious. Hook them in 3 seconds or they leave.

FORMAT: 5-8 MINUTE VIDEO. 800-1200 words TOTAL. Every word must earn its place.

CRITICAL RULE — EACH SECTION = ONE SENTENCE (10-25 words max).
EVERY section gets its OWN image. More sections = more visual cuts = more engaging.
Images change every 2-4 seconds. Write 50-70 sections, each just ONE punchy sentence.

ALREADY COVERED (do NOT repeat):
{done_str}

Pick ONE topic: an everyday habit, superstition, or tradition with a WILD deep-dive explanation. Go DEEP — history, psychology, science, comparisons across cultures. This is an 8-min video, not a short.

Structure: 50-70 sections. Each = ONE sentence + visual_notes.

SECTION IDS AND FLOW:
- hook_1 through hook_5: IMMERSIVE opening (Ink Explainer style). Put viewer IN the scene. Then SNAP to the shocking consequence. Think "you're standing there when..." followed by "wait WHAT?"
- build_1 through build_8: Context that makes them CARE. Each fact more surprising than the last. Layer the mystery. Use "here's what most people don't realize..."
- twist_1 through twist_5: First major "NO WAY" moment (~60s). Flip everything they assumed. This is where gasps happen.
- build_4 through build_10: Go DEEPER. Historical roots. Scientific reasons. Cross-cultural comparisons. "In Korea, they do X. In Japan, the OPPOSITE. In China? Something nobody expected."
- twist_2_1 through twist_2_5: Second major twist (~2 min). An even bigger revelation. "But here's what NOBODY talks about..."
- build_11 through build_15: More layers. Psychology. Evolution. Modern consequences. Pattern interrupt with a wild analogy or number drop.
- twist_3_1 through twist_3_3: Third twist (~3.5 min). Connect dots the viewer didn't see coming.
- build_16 through build_20: The rabbit hole goes DEEPER. Unexpected connections to other cultures/traditions.
- twist_4_1 through twist_4_3: Fourth twist (~5 min). "And THAT's why your grandma..."
- payoff_1 through payoff_8: The REAL answer. Mind-blowing synthesis. Everything clicks together. Make them want to share.
- close_1 through close_3: Satisfying reframe + callback to the hook. LAST section MUST end with the tagline: "Your grandma's rules — finally explained."

UNPREDICTABILITY RULES:
- Never follow a question with its obvious answer
- Never follow a negative with a positive (or vice versa) predictably
- Each sentence should raise a NEW question the viewer didn't expect
- Use contrasts: "Americans do X. Japanese do the OPPOSITE."
- Use numbers for shock: specific stats, comparisons, amounts
- Every 45 seconds: pattern interrupt (sudden question, analogy, "wait it gets worse", callback)
- Use cliffhangers between sections: end one idea mid-thought to keep them watching

VISUAL NOTES RULES:
- The main character is ALWAYS a boy with round head, dot eyes, line mouth, messy brown hair, stick body
- Describe ONE clear scene with MULTIPLE characters if relevant
- Specific objects, specific background/setting, warm earth-toned colors
- Keep subjects CENTERED in the frame (for vertical crop to Reels/TikTok)
- CLEAN — no negative emotions, no conflict words. Describe poses and objects only.
- Max 120 characters per visual_notes

Return ONLY valid JSON:
{{
  "title": "YouTube title (compelling, under 70 chars, use CAPS for one key word)",
  "description": "Short YouTube description + engagement question",
  "tags": ["tag1", "tag2", "CuriousAsian"],
  "sections": [
    {{
      "id": "hook_1",
      "narration": "One punchy sentence (10-25 words).",
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
