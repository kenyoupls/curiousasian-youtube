"""Image generation — Cloudflare FLUX Schnell (free, 10k neurons/day).

On NSFW block: Gemini rewrites the prompt → retry. Generic safe fallback last resort.
All images use a locked style template + locked character for channel-wide consistency.
"""

import re
import base64
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from src.config import VIDEO_WIDTH, VIDEO_HEIGHT, OUTPUT_DIR


class ImageGenerationFailed(Exception):
    pass


# ── Locked character description ────────────────────────────────────
# Cute vintage anime boy — consistent description for every frame.
LOCKED_CHARACTER = (
    "a cute young boy with round face, big expressive sparkling eyes, "
    "short messy brown hair, wearing a dark gray hoodie and olive cargo pants, "
    "brown boots, cheerful and expressive"
)

# ── Locked style template ────────────────────────────────────────────
# 90s vintage anime aesthetic across the ENTIRE channel.
# {scene} is the ONLY variable — everything else is fixed.
FLUX_STYLE_TEMPLATE = (
    "90s vintage anime cel-shaded illustration, "
    "retro anime art style like 1990s Japanese animation, "
    "warm nostalgic color palette, soft cel-shading with visible outlines, "
    "expressive cute anime characters with big sparkling eyes, "
    "{scene}, "
    "detailed colorful background, warm golden lighting, "
    "hand-drawn look with slight film grain, "
    "vertical 9:16 composition, "
    "NO photorealism, NO 3D rendering, NO modern digital art, "
    "NO stickman, NO vector art, NO chibi, NO watercolor"
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
                    "meme-face", "internet comic", "MackExplains7", "2D vector",
                    "line-art", "cell-shading", "stickman", "anime style",
                    "realistic", "detailed human", "vintage anime", "retro anime",
                    "cel-shaded", "90s anime"]:
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


class ImageEngineConfigError(Exception):
    """No image engine can work (bad/expired token, missing secrets).

    Retrying other images or other scripts is pointless — stop the run.
    """


def _is_nsfw(err_str):
    err_str = err_str.lower()
    return "nsfw" in err_str or ("content" in err_str and "prohibited" in err_str)


def _engines():
    """Image engines in priority order: (name, callable(prompt, path, seed))."""
    from src import cloudflare_helper as cf
    from src import pollinations_helper as pol

    engines = []
    if cf.is_configured():
        engines.append(("Cloudflare FLUX", lambda p, o, s: cf.generate_cloudflare_image(
            p, o, num_steps=4, use_flux=True)))
        engines.append(("Cloudflare SDXL", lambda p, o, s: cf.generate_cloudflare_image(
            p, o, width=576, height=1024, seed=s, num_steps=8, use_flux=False)))
    if pol.is_configured():
        engines.append(("Pollinations", lambda p, o, s: pol.generate_pollinations_image(
            p, o, width=576, height=1024, seed=s)))
    if not engines:
        raise ImageEngineConfigError(
            "No image engine configured: set CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN "
            "(or POLLINATIONS_API_KEY) in GitHub secrets")
    return engines


def _generate_cloudflare(prompt, output_path, image_index=0):
    """Generate one image with the first engine that works, then crop to 1080x1920.

    (Name kept for the thumbnail code.) Raises:
    - ImageEngineConfigError if every engine failed on auth/config,
    - RuntimeError with "NSFW" in it if the prompt was blocked,
    - RuntimeError otherwise.
    """
    from src.cloudflare_helper import CloudflareAuthError
    seed = SEED_BASE + image_index
    errors, auth_failures = [], 0
    engines = _engines()

    for name, engine in engines:
        try:
            engine(prompt, output_path, seed)
            img = Image.open(output_path).convert("RGB")
            img = _fit_to_hd(img)
            img.save(output_path, "PNG")
            return True
        except CloudflareAuthError as e:
            auth_failures += 1
            errors.append(f"{name}: {e}")
        except Exception as e:
            if _is_nsfw(str(e)):
                raise RuntimeError(f"NSFW blocked ({name}): {e}")
            errors.append(f"{name}: {e}")
            print(f"    ⚠️  {name} failed: {e}")

    if auth_failures == len(engines) or (auth_failures and all(
            "Cloudflare" in n for n, _ in engines)):
        raise ImageEngineConfigError("; ".join(errors))
    raise RuntimeError("; ".join(errors))


def generate_single_image(prompt, output_path, image_index=0):
    """Generate one image.

    Flow:
    1. Original prompt through the engine chain (FLUX → SDXL → Pollinations), 2 tries
    2. If NSFW blocked → Gemini rewrites prompt → engine chain again
    3. If still failing → generic safe prompt as last resort
    Auth/config errors stop immediately (ImageEngineConfigError).
    """
    attempts = [
        ("original", lambda: _build_prompt(prompt)),
        ("original retry", lambda: _build_prompt(prompt)),
        ("rewritten", lambda: _build_prompt(_rewrite_prompt_safe(prompt))),
        ("safe fallback", lambda: _build_prompt(
            f"{LOCKED_CHARACTER} standing in center with question mark floating above head, "
            "simple colorful background with decorative elements")),
    ]
    last_err = None
    nsfw = False
    for label, make_prompt in attempts:
        if label == "original retry" and nsfw:
            continue  # same prompt would be blocked again
        try:
            _generate_cloudflare(make_prompt(), output_path, image_index)
            return output_path
        except ImageEngineConfigError:
            raise
        except Exception as e:
            last_err = e
            nsfw = nsfw or _is_nsfw(str(e))
            print(f"    ⚠️  Image ({label}) failed: {e}")

    raise ImageGenerationFailed(f"All image engines failed: {last_err}")


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
    # Crop (not stretch) the 9:16 frame to a 16:9 thumbnail
    img = ImageOps.fit(Image.open(thumb).convert("RGB"), (1280, 720), Image.LANCZOS,
                       centering=(0.5, 0.35))
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
