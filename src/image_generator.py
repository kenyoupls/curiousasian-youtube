"""Image generation — Cloudflare FLUX.1 Schnell (primary) + SDXL Lightning (fallback).

Free tier: 10,000 neurons/day.
FLUX Schnell: ~50 neurons/image → ~200 images/day (higher quality)
SDXL Lightning: ~30 neurons/image → ~300 images/day (lower quality fallback)
"""

import base64
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from src.config import IMAGE_STYLE, VIDEO_WIDTH, VIDEO_HEIGHT, OUTPUT_DIR


class ImageGenerationFailed(Exception):
    pass


# ── Prompt template (locked — matches successful flux_test4 framing) ──
# FLUX schnell works best with natural language, no weight syntax
FLUX_PROMPT_TEMPLATE = (
    "cartoon character in center of white background, "
    "character takes up 60 percent of frame height, "
    "flat 2D cartoon boy with round eyes {scene}, "
    "thick black outlines, solid flat colors, pure white background, "
    "clean negative space around edges, simple minimalist composition"
)

# ── SDXL fallback prompt (weight syntax, style-first) ─────────────────
SDXL_STYLE_PREFIX = (
    "(flat 2D cartoon, thick black outlines, solid colors, "
    "white background, wide landscape:1.2)"
)
SDXL_CHARACTER_TAG = "simple stick figure with round head and dot eyes"

SDXL_NEGATIVE_PROMPT = (
    "(photorealistic, 3D render, anime, shading, gradients, "
    "blurry, watermark, text, close-up, portrait:1.4)"
)

# ── Seed base for consistency ─────────────────────────────────────────
SEED_BASE = 42


def _build_prompt(scene, use_flux=True):
    """Build prompt for FLUX schnell (primary) or SDXL Lightning (fallback).

    FLUX: Natural language, locked template for consistent framing.
    SDXL: Weight syntax, style-first, under 40 words.
    """
    # Strip scene to core action — remove style words the LLM may have added
    scene = scene[:120].replace("stick figure character", "").strip(", ")

    # Sanitize words that trigger FLUX Schnell's NSFW filter
    # These are benign in context but Cloudflare's filter is aggressive
    NSFW_TRIGGERS = [
        "insult", "insulted", "insulting", "offensive", "offended",
        "deeply offended", "repulsive", "disgusted", "disturbed",
        "rude", "angry", "furious", "violent", "attack", "killed",
        "naked", "nude", "sexy", "seductive", "provocative",
        "drug", "drunk", "alcohol", "smoking", "blood", "bloody",
        "gun", "weapon", "knife", "sword", "fight", "punch",
        "slave", "slavery", "torture", "abuse", "victim",
        "hate", "hatred", "racist", "racism",
    ]
    scene_lower = scene.lower()
    for trigger in NSFW_TRIGGERS:
        if trigger in scene_lower:
            scene = scene.replace(trigger, "upset")
            scene = scene.replace(trigger.capitalize(), "Upset")

    if use_flux:
        return FLUX_PROMPT_TEMPLATE.format(scene=scene)
    else:
        return f"{SDXL_STYLE_PREFIX}, {SDXL_CHARACTER_TAG} {scene}"


def _fit_to_hd(img: Image.Image) -> Image.Image:
    """Resize image to 1920x1080 without stretching.

    Scales to fill the frame, then center-crops to exact 16:9.
    No black bars, no distortion.
    """
    target_w, target_h = VIDEO_WIDTH, VIDEO_HEIGHT
    target_ratio = target_w / target_h  # 1.777...

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


class _NSFWError(Exception):
    """Raised when FLUX rejects a prompt as NSFW — skip to SDXL immediately."""
    pass


def _try_flux(prompt, output_path, image_index=0):
    """Try Cloudflare FLUX.1 Schnell (primary). Returns True on success.

    Raises _NSFWError if FLUX flags the prompt — caller should skip to SDXL.
    """
    try:
        from src.cloudflare_helper import generate_cloudflare_image
        seed = SEED_BASE + image_index
        generate_cloudflare_image(
            prompt, output_path,
            width=1024, height=576,  # 16:9 within FLUX limits
            seed=seed,
            num_steps=4,  # FLUX schnell optimal at 4 steps
            use_flux=True,
        )
        # Upscale to full HD
        img = Image.open(output_path).convert("RGB")
        img = _fit_to_hd(img)
        img.save(output_path, "PNG")
        return True
    except Exception as e:
        err_str = str(e).lower()
        if "nsfw" in err_str or "content" in err_str and "prohibited" in err_str:
            print(f"    ⚠️  FLUX NSFW filter triggered, skipping to SDXL")
            raise _NSFWError(str(e))
        print(f"    ⚠️  FLUX Schnell: {e}")
    return False


def _try_sdxl(prompt, output_path, image_index=0):
    """Try Cloudflare SDXL Lightning (fallback). Returns True on success."""
    try:
        from src.cloudflare_helper import generate_cloudflare_image
        seed = SEED_BASE + image_index
        generate_cloudflare_image(
            prompt, output_path,
            width=1024, height=576,
            seed=seed,
            negative_prompt=SDXL_NEGATIVE_PROMPT,
            num_steps=8,
            use_flux=False,
        )
        img = Image.open(output_path).convert("RGB")
        img = _fit_to_hd(img)
        img.save(output_path, "PNG")
        return True
    except Exception as e:
        print(f"    ⚠️  SDXL Lightning: {e}")
    return False


def _try_gemini(prompt, output_path):
    """Try Gemini image generation. Returns True on success."""
    try:
        from src.gemini_helper import generate_image
        resp = generate_image(prompt)
        if not resp or not resp.candidates:
            return False
        for part in resp.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                data = part.inline_data.data
                raw = base64.b64decode(data) if isinstance(data, str) else data
                output_path.write_bytes(raw)
                img = Image.open(output_path).convert("RGB")
                img = _fit_to_hd(img)
                img.save(output_path, "PNG")
                return True
    except Exception as e:
        print(f"    ⚠️  Gemini image: {e}")
    return False


def generate_single_image(prompt, output_path, image_index=0):
    """FLUX Schnell primary → SDXL Lightning fallback. Both free on Cloudflare."""

    # Try FLUX schnell first (higher quality)
    flux_prompt = _build_prompt(prompt, use_flux=True)
    nsfw_blocked = False
    for attempt in range(3):
        print(f"    ⚡ FLUX [{attempt+1}/3]...")
        try:
            if _try_flux(flux_prompt, output_path, image_index):
                return output_path
        except _NSFWError:
            nsfw_blocked = True
            break  # Don't retry FLUX — skip straight to SDXL

    # Fallback to SDXL Lightning (more lenient content filter)
    if nsfw_blocked:
        print(f"    ☁️  FLUX blocked prompt, trying SDXL (more lenient)...")
    sdxl_prompt = _build_prompt(prompt, use_flux=False)
    for attempt in range(3):
        print(f"    ☁️  SDXL fallback [{attempt+1}/3]...")
        if _try_sdxl(sdxl_prompt, output_path, image_index):
            return output_path

    raise ImageGenerationFailed(f"All methods failed: {output_path.name}")


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
        f"YouTube thumbnail, vibrant colors, {title[:100]}, "
        f"surprised expression, bold composition",
        use_flux=True
    )

    # FLUX primary → SDXL → gradient fallback
    generated = _try_flux(flux_prompt, thumb, image_index=999)
    if not generated:
        sdxl_prompt = _build_prompt(
            f"YouTube thumbnail, vibrant colors, {title[:100]}, "
            f"surprised expression, bold composition",
            use_flux=False
        )
        generated = _try_sdxl(sdxl_prompt, thumb, image_index=999)
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
