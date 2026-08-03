"""Generates per-image prompts from narration — narrative-driven scene breaks.

Instead of rigid 1-per-3s, Gemini decides how many scenes each section needs
based on the story beats, topic shifts, and visual variety required.
"""

import json
from google import genai
from src.config import GEMINI_API_KEY, GEMINI_TEXT_MODEL, IMAGE_STYLE


def _get_client():
    return genai.Client(api_key=GEMINI_API_KEY)


def _build_character_ref(script: dict) -> str:
    """Build character reference block from script — supports both single
    'character' (legacy) and 'characters' (array) formats."""
    chars = []

    # New format: characters array
    if "characters" in script:
        chars = script["characters"]
    # Legacy format: single character dict
    elif "character" in script:
        chars = [script["character"]]

    if not chars:
        return ""

    lines = []
    for i, char in enumerate(chars):
        label = "PRIMARY" if i == 0 else f"SUPPORTING #{i}"
        lines.append(
            f"[{label}] Name: {char.get('name', 'Character')}. "
            f"Appearance: {char.get('appearance', 'Simple cartoon character')}. "
            f"Role: {char.get('role', 'Appears throughout the video')}."
        )

    return "\n".join(lines)


def generate_image_prompts(section: dict, duration: float,
                           character_ref: str = "") -> list[dict]:
    """Break a narration section into narrative-driven image prompts.

    Gemini decides how many images based on the story — topic shifts,
    new characters entering, location changes, reveals, etc.
    Rough guide: 1 image per 2-5 seconds, but story beats drive it.

    Args:
        section: Script section with 'narration' and 'visual_notes'
        duration: Audio duration in seconds (for rough bounds)
        character_ref: Character descriptions for consistency

    Returns:
        List of {image_prompt, key_phrase, duration_hint} dicts
    """
    client = _get_client()

    # Bounds: at least 1 image per 5s, at most 1 per 2s
    min_images = max(1, int(duration / 5))
    max_images = max(min_images + 1, int(duration / 2))

    char_block = ""
    if character_ref:
        char_block = f"""
VIDEO CHARACTERS (must appear consistently — same outfit, features, proportions in EVERY image):
{character_ref}
Every character must look IDENTICAL each time they appear. Include their full description in every image prompt so the AI draws them the same way.
"""

    prompt = f"""You are a visual storyboard artist for an educational YouTube channel.
{char_block}
NARRATION TEXT:
"{section['narration']}"

VISUAL NOTES FROM SCRIPTWRITER:
"{section.get('visual_notes', 'Match the narration content')}"

ART STYLE: {IMAGE_STYLE}

AUDIO DURATION: {duration:.1f} seconds

Break this narration into visual scenes based on the STORY, not on a timer.
Create a new scene when:
- A new topic or concept is introduced
- A character enters or exits
- The location/setting changes
- There's a dramatic reveal or twist
- The mood shifts (funny → serious, etc.)
- A comparison or contrast is being made (show both sides)

You need between {min_images} and {max_images} scenes.

For each scene, provide:
- "image_prompt": A detailed prompt for AI image generation. ALWAYS include the full character description for any character in the scene. Describe scene, action, colors, mood — all in the flat cartoon style.
- "key_phrase": A short punchy text overlay (3-8 words) — the key takeaway. Use original Asian terms with translation where relevant (e.g., "送钟 sòng zhōng = send to death")
- "duration_hint": How many seconds this scene should stay on screen (based on how much narration it covers). All durations must sum to approximately {duration:.0f} seconds.
- "narration_snippet": The first 10-15 words of the narration this scene covers (so we can sync timing).

Return ONLY a JSON array:
[
  {{"image_prompt": "...", "key_phrase": "...", "duration_hint": 3.5, "narration_snippet": "..."}},
  ...
]

Return valid JSON only, no markdown formatting."""

    response = client.models.generate_content(
        model=GEMINI_TEXT_MODEL,
        contents=prompt
    )

    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]

    prompts = json.loads(text)

    # Validate bounds
    if len(prompts) < min_images:
        while len(prompts) < min_images:
            prompts.append({
                "image_prompt": f"Simple cartoon illustration of: {section.get('visual_notes', 'a curious person thinking')}. {IMAGE_STYLE}",
                "key_phrase": "",
                "duration_hint": duration / min_images,
                "narration_snippet": ""
            })
    elif len(prompts) > max_images:
        prompts = prompts[:max_images]

    # Normalize durations so they sum to actual audio duration
    raw_total = sum(p.get("duration_hint", 3) for p in prompts)
    if raw_total > 0:
        scale = duration / raw_total
        for p in prompts:
            p["duration_hint"] = round(p.get("duration_hint", 3) * scale, 2)

    return prompts


def generate_all_image_prompts(script: dict, audio_segments: list[dict]) -> list[dict]:
    """Generate image prompts for the entire video.

    Args:
        script: Full script with sections
        audio_segments: List of {duration, section_id, ...} from voice generator

    Returns:
        Flat list of image prompt dicts for every scene
    """
    # Build character reference (supports single or multi-character)
    character_ref = _build_character_ref(script)

    if character_ref:
        chars = script.get("characters", [])
        if not chars and "character" in script:
            chars = [script["character"]]
        names = [c.get("name", "unnamed") for c in chars]
        print(f"  👤 Video characters: {', '.join(names)}")

    all_prompts = []

    for section, audio_seg in zip(script["sections"], audio_segments):
        duration = audio_seg["duration"]

        section_prompts = generate_image_prompts(
            section, duration, character_ref=character_ref
        )

        num_scenes = len(section_prompts)
        print(f"  🎨 {section['id']}: {duration:.1f}s → {num_scenes} scenes (narrative-driven)")

        for i, p in enumerate(section_prompts):
            all_prompts.append({
                "image_prompt": p["image_prompt"],
                "key_phrase": p.get("key_phrase", ""),
                "duration_hint": p.get("duration_hint", 3),
                "narration_snippet": p.get("narration_snippet", ""),
                "section_id": section["id"],
                "section_index": audio_segments.index(audio_seg),
                "image_index": i,
                "global_index": len(all_prompts),
            })

    print(f"  🎨 Total scenes: {len(all_prompts)} (narrative-driven)")
    return all_prompts
