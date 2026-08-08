"""Image generation — Cloudflare FLUX Schnell (free, 10k neurons/day).

On NSFW block: Gemini rewrites the prompt → retry. Generic safe fallback last resort.
All images use a locked style template + locked character for channel-wide consistency.
"""

import re
import base64
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from src.config import VIDEO_WIDTH, VIDEO_HEIGHT, OUTPUT_DIR


class ImageGenerationFailed(Exception):
    pass


# ── Locked character description ────────────────────────────────────
# Meme-face style: white circle head, big expressive eyes, like internet comics.
# Same character in EVERY frame for channel-wide consistency.
LOCKED_CHARACTER = (
    "a character with perfectly round white circle head, "
    "big round black dot eyes, simple small line mouth, "
    "short messy brown hair on top of head, "
    "wearing dark hoodie and simple pants"
)

# ── Locked style template ────────────────────────────────────────────
# Internet meme-face comic style across the ENTIRE channel.
# {scene} is the ONLY variable — everything else is fixed.
FLUX_STYLE_TEMPLATE = (
    "internet meme comic style illustration, "
    "characters have perfectly round white circle heads with big expressive meme-face eyes, "
    "thick black outlines on characters, detailed colorful background, "
    "manga-inspired emotion effects like action speed lines and exclamation marks, "
    "{scene}, "
    "dynamic composition with visible emotions, "
    "floating reaction symbols like sweat drops and question marks, "
    "NO realistic faces, NO blush marks, NO nose detail, "
    "NO children's book style, NO soft shading on faces, NO cute anime"
)

# ── Seed base for consistency ─────────────────────────────────────────
SEED_BASE = 42

# ── Words that trigger FLUX NSFW filter (benign in context) ──────────
NSFW_REPLACEMENTS = {
    # Emotions / reactions
    "insult": "surprise", "insulted": "surprised", "insulting": "surprising",
    "offend": "surprise", "offended": "surprised", "offensive": "surprising",
    "angry": "serious", "furious": "serious", "enraged": "serious",
    "rude": "confused", "disgusted": "puzzled", "disturbed": "puzzled",
    "repulsive": "strange", "horrified": "shocked", "horrifying": "shocking",
    "upset": "concerned", "mad": "serious", "outraged": "surprised",
    "hurt": "confused", "painful": "surprising", "suffering": "thinking",
    "crying": "surprised", "scream": "shout", "screaming": "shouting",
    "hate": "dislike", "hatred": "dislike", "despise": "dislike",
    # Violence
    "violent": "dramatic", "attack": "approach", "attacked": "approached",
    "killed": "stopped", "kill": "stop", "murder": "mystery",
    "fight": "debate", "fighting": "debating", "punch": "gesture",
    "hit": "tap", "slap": "tap", "kick": "step",
    "blood": "red", "bloody": "messy", "wound": "mark",
    "gun": "tool", "weapon": "object", "knife": "utensil", "sword": "stick",
    "war": "competition", "battle": "challenge", "destroy": "remove",
    "dead": "still", "death": "end", "dying": "fading",
    # Substances
    "drug": "medicine", "drunk": "dizzy", "alcohol": "drink",
    "smoking": "breathing", "cigarette": "stick", "beer": "drink",
    # Body / suggestive
    "naked": "plain", "nude": "bare", "sexy": "stylish",
    "seductive": "charming", "provocative": "bold",
    "slave": "worker", "slavery": "labor", "torture": "challenge",
    "abuse": "trouble", "victim": "person",
    # Social
    "racist": "biased", "racism": "bias",
    # Common script words that trigger false positives
    "chases": "follows", "chasing": "following", "chase": "follow",
    "sprinting": "running", "sprint": "run",
    "disrespect": "surprise", "disrespected": "surprised",
    "pray": "hope", "praying": "hoping",
    "scolding": "talking to", "scold": "talk to",
    "recoiling": "stepping back", "recoil": "step back",
    "cracking": "opening", "crack": "open",
}


def _sanitize_scene(scene):
    """Remove words that trigger FLUX NSFW filter."""
    for trigger, replacement in NSFW_REPLACEMENTS.items():
        scene = re.sub(
            r'\b' + re.escape(trigger) + r'\b',
            replacement, scene, flags=re.IGNORECASE
        )
    return scene


def _build_prompt(scene):
    """Build FLUX prompt from scene description.

    Scene can describe multiple characters, objects, backgrounds —
    the style template keeps everything visually consistent.
    """
    # Strip style words the LLM may have added (we handle style)
    scene = scene[:200]
    for remove in ["stick figure", "flat 2D", "thick outlines", "cartoon style",
                    "white background", "solid colors", "minimalist",
                    "earth-toned", "warm background", "meme face", "circle head",
                    "meme-face", "internet comic"]:
        scene = scene.replace(remove, "").replace(remove.title(), "")
    scene = re.sub(r'\s+', ' ', scene).strip(", ")

    scene = _sanitize_scene(scene)

    return FLUX_STYLE_TEMPLATE.format(scene=scene)


def _rewrite_prompt_safe(original_scene):
    """Use Gemini to rewrite a NSFW-blocked prompt into something safe for FLUX.

    Keeps the same visual meaning but removes any triggering words.
    """
    try:
        from src.gemini_helper import generate_text
        rewrite_prompt = f"""Rewrite this image description to be COMPLETELY safe for an AI image generator with a strict content filter.

ORIGINAL: "{original_scene}"

RULES:
- Keep the same visual scene and meaning
- Remove ALL negative emotions (angry, upset, hurt, offended, etc.)
- Remove ALL conflict (fighting, chasing, attacking, etc.)
- Replace with neutral/positive alternatives
- Keep it as a simple scene description: who is doing what, with what objects, what background
- MAX 100 characters
- Do NOT add style instructions — just describe the scene

Return ONLY the rewritten description, nothing else."""

        result = generate_text(rewrite_prompt)
        if result and len(result.strip()) > 10:
            safe = result.strip().strip('"').strip("'")
            print(f"    🔄 Rewritten: {safe[:80]}...")
            return safe
    except Exception as e:
        print(f"    ⚠️  Gemini rewrite failed: {e}")

    # Fallback: strip the scene to bare minimum
    return f"{LOCKED_CHARACTER} standing with question mark above head, simple background"


def _fit_to_hd(img: Image.Image) -> Image.Image:
    """Resize image to 1920x1080 without stretching.

    Scales to fill the frame, then center-crops to exact 16:9.
    """
    target_w, target_h = VIDEO_WIDTH, VIDEO_HEIGHT
    target_ratio = target_w / target_h

    w, h = img.size
    img_ratio = w / h

    if img_ratio > target_ratio:
        new_h = target_h
        new_w = int(new_h * img_ratio)
    else:
        new_w = target_w
        new_h = int(new_w / img_ratio)

    img = img.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    img = img.crop((left, top, left + target_w, top + target_h))
    return img


def _generate_cloudflare(prompt, output_path, image_index=0):
    """Generate via Cloudflare FLUX Schnell (primary). Returns True on success."""
    from src.cloudflare_helper import generate_cloudflare_image
    seed = SEED_BASE + image_index
    generate_cloudflare_image(
        prompt, output_path,
        width=1024, height=576,
        seed=seed,
        num_steps=4,
        use_flux=True,
    )
    img = Image.open(output_path).convert("RGB")
    img = _fit_to_hd(img)
    img.save(output_path, "PNG")
    return True


def generate_single_image(prompt, output_path, image_index=0):
    """Generate image: Cloudflare FLUX primary.

    Flow:
    1. Sanitize + try Cloudflare FLUX (2 attempts)
    2. If NSFW blocked → Gemini rewrites prompt → retry Cloudflare (2 attempts)
    3. If still blocked → use generic safe prompt as last resort
    """

    flux_prompt = _build_prompt(prompt)

    # ── Attempt 1-2: Cloudflare with original prompt ──────────
    for attempt in range(2):
        try:
            print(f"    ⚡ Cloudflare FLUX [{attempt+1}/2]...")
            _generate_cloudflare(flux_prompt, output_path, image_index)
            return output_path
        except Exception as e:
            err_str = str(e).lower()
            if "nsfw" in err_str or ("content" in err_str and "prohibited" in err_str):
                print(f"    ⚠️  NSFW blocked — rewriting prompt...")
                break
            print(f"    ⚠️  Cloudflare error: {e}")
            if attempt == 1:
                break

    # ── Attempt 3-4: Gemini-rewritten safe prompt ──────────────
    safe_scene = _rewrite_prompt_safe(prompt)
    safe_prompt = _build_prompt(safe_scene)

    for attempt in range(2):
        try:
            print(f"    ⚡ Cloudflare FLUX rewritten [{attempt+1}/2]...")
            _generate_cloudflare(safe_prompt, output_path, image_index)
            return output_path
        except Exception as e:
            err_str = str(e).lower()
            if "nsfw" in err_str or ("content" in err_str and "prohibited" in err_str):
                print(f"    ⚠️  Still NSFW after rewrite...")
                break
            print(f"    ⚠️  Cloudflare error: {e}")

    # ── Attempt 5: generic safe prompt (guaranteed to work) ─────
    fallback_prompt = _build_prompt(
        f"{LOCKED_CHARACTER} standing in center with question mark floating above head, "
        "simple colorful background with decorative elements"
    )
    try:
        print(f"    ⚡ Cloudflare safe fallback...")
        _generate_cloudflare(fallback_prompt, output_path, image_index)
        return output_path
    except Exception as e:
        raise ImageGenerationFailed(f"All image engines failed: {e}")


def generate_all_images(image_prompts):
    """Generate all video images."""
    images_dir = OUTPUT_DIR / "images"
    images_dir.mkdir(exist_ok=True)
    paths = []

    for i, p in enumerate(image_prompts):
        out = images_dir / f"img_{i:04d}.png"
        if out.exists():
            paths.append(out)
            continue
        print(f"  🖼️  [{i+1}/{len(image_prompts)}] Generating...")
        generate_single_image(p["image_prompt"], out, image_index=i)
        paths.append(out)

    print(f"🖼️  {len(paths)} images total")
    return paths


def generate_thumbnail(script):
    """Thumbnail with title overlay."""
    thumb = OUTPUT_DIR / "thumbnail.png"
    title = script["title"]

    flux_prompt = _build_prompt(
        f"{LOCKED_CHARACTER} with excited expression, colorful vibrant scene, "
        f"topic: {title[:80]}, eye-catching composition, multiple fun elements"
    )

    # Try Cloudflare → rewrite → gradient fallback
    generated = False
    try:
        _generate_cloudflare(flux_prompt, thumb, image_index=999)
        generated = True
    except Exception as e:
        print(f"    ⚠️  Thumbnail Cloudflare: {e}")
        try:
            safe = _rewrite_prompt_safe(
                f"excited {LOCKED_CHARACTER}, colorful scene about {title[:60]}"
            )
            _generate_cloudflare(_build_prompt(safe), thumb, image_index=999)
            generated = True
        except Exception as e2:
            print(f"    ⚠️  Thumbnail rewrite also failed: {e2}")

    if not generated:
        img = Image.new("RGB", (1280, 720), (30, 20, 60))
        img.save(thumb, "PNG")

    # Title overlay
    img = Image.open(thumb).resize((1280, 720), Image.LANCZOS)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 56)
    except (OSError, IOError):
        font = ImageFont.load_default()

    # Wrap text
    lines, cur = [], ""
    for word in title.split():
        test = f"{cur} {word}".strip()
        if draw.textbbox((0, 0), test, font=font)[2] > 1100 and cur:
            lines.append(cur)
            cur = word
        else:
            cur = test
    if cur:
        lines.append(cur)

    # Dark bar + text
    h = len(lines) * 70 + 40
    y0 = 720 - h
    overlay = Image.new("RGBA", (1280, h), (0, 0, 0, 180))
    img = img.convert("RGBA")
    img.paste(overlay, (0, y0), overlay)
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        bx = draw.textbbox((0, 0), line, font=font)
        x = (1280 - bx[2] + bx[0]) // 2
        y = y0 + 20 + i * 70
        draw.text((x+2, y+2), line, fill=(0, 0, 0), font=font)
        draw.text((x, y), line, fill=(255, 215, 0), font=font)

    img.convert("RGB").save(thumb, "PNG")
    print("🎨 Thumbnail done")
    return thumb
