"""Image generation — Gemini 2.5 Flash Image primary (500 RPD free), Cloudflare SDXL fallback.

Gemini produces much higher quality images. Cloudflare SDXL Lightning
is the free fallback if Gemini quota is exhausted or errors.
"""

import base64
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from src.config import IMAGE_STYLE, VIDEO_WIDTH, VIDEO_HEIGHT, OUTPUT_DIR


class ImageGenerationFailed(Exception):
    pass


# ── Prompt components (optimised for SDXL Lightning — keep SHORT) ─────
# Lightning works best with <40 words, style-first, low detail
CHARACTER_TAG = "simple stick figure with round head and dot eyes"

STYLE_PREFIX = (
    "(flat 2D cartoon, thick black outlines, solid colors, "
    "white background, wide landscape:1.2)"
)

# Focused negative prompt — only the biggest failure modes
NEGATIVE_PROMPT = (
    "(photorealistic, 3D render, anime, shading, gradients, "
    "blurry, watermark, text, close-up, portrait:1.4)"
)

# ── Seed base for consistency ─────────────────────────────────────────
SEED_BASE = 42


def _build_prompt(scene, for_cloudflare=True):
    """Build prompt optimised for SDXL Lightning.

    Key principles:
    - Style FIRST, subject second (Lightning prioritises early tokens)
    - Keep under 40 words total
    - Use weight syntax (element:1.2) for emphasis
    - Scene description trimmed to essentials
    """
    # Strip scene to core action — remove any style words the LLM added
    scene = scene[:120].replace("stick figure character", "").strip(", ")
    return f"{STYLE_PREFIX}, {CHARACTER_TAG} {scene}"


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


def _try_cloudflare(prompt, output_path, image_index=0):
    """Try Cloudflare SDXL Lightning. Returns True on success."""
    try:
        from src.cloudflare_helper import generate_cloudflare_image
        seed = SEED_BASE + image_index
        # SDXL max is 1024x1024 natively; generate at max landscape ratio
        # then upscale to 1920x1080
        generate_cloudflare_image(
            prompt, output_path,
            width=1024, height=576,  # 16:9 ratio within SDXL limits
            seed=seed,
            negative_prompt=NEGATIVE_PROMPT,
            num_steps=8  # Lightning is distilled for 4-8 steps; 20 over-cooks
        )
        # Upscale to full HD
        img = Image.open(output_path).convert("RGB")
        img = _fit_to_hd(img)
        img.save(output_path, "PNG")
        return True
    except Exception as e:
        print(f"    ⚠️  Cloudflare: {e}")
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
    """Gemini 2.5 Flash Image primary (500 RPD free) → Cloudflare SDXL fallback."""

    gemini_prompt = (
        f"Wide 16:9 landscape illustration. "
        f"{STYLE_PREFIX}, {CHARACTER_TAG} {prompt[:120]}"
    )
    cf_prompt = _build_prompt(prompt, for_cloudflare=True)

    # Gemini — primary (best quality, 500 RPD free tier)
    for attempt in range(2):
        print(f"    🎨 Gemini [{attempt+1}/2]...")
        if _try_gemini(gemini_prompt, output_path):
            return output_path

    # Cloudflare SDXL — fallback (free, reliable)
    for attempt in range(2):
        print(f"    ☁️  Cloudflare [{attempt+1}/2]...")
        if _try_cloudflare(cf_prompt, output_path, image_index):
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

    thumb_scene = (
        f"YouTube thumbnail, vibrant colors, {title[:100]}, "
        f"surprised expression, bold composition"
    )
    gemini_prompt = (
        f"Wide 16:9 landscape illustration. "
        f"{STYLE_PREFIX}, {CHARACTER_TAG} {thumb_scene}"
    )
    cf_prompt = _build_prompt(thumb_scene, for_cloudflare=True)

    # Gemini primary → Cloudflare fallback → gradient fallback
    if not _try_gemini(gemini_prompt, thumb):
        if not _try_cloudflare(cf_prompt, thumb, image_index=999):
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
