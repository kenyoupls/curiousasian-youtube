"""Image generation — Cloudflare SDXL Lightning primary, Gemini fallback.

Consistent stick figure character across all scenes using locked
character DNA prompt, fixed seed base, style modifiers, and negative_prompt.
"""

import base64
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from src.config import IMAGE_STYLE, VIDEO_WIDTH, VIDEO_HEIGHT, OUTPUT_DIR


class ImageGenerationFailed(Exception):
    pass


# ── Character DNA (never changes) ────────────────────────────────────
CHARACTER_DNA = (
    "simple stick figure drawing, children doodle style, "
    "drawn with thick black marker. "
    "White circle head, two tiny black dot eyes, "
    "single horizontal line mouth, messy scribbled brown hair. "
    "Straight black line body, straight line arms and legs, "
    "no hands, no feet, simple clothing shape"
)

# ── Style lock (appended to every prompt) ─────────────────────────────
STYLE_LOCK = (
    "2D flat cartoon, hand-drawn whiteboard sketch style, "
    "thick black outlines, flat solid earth tone colors, "
    "two-tone solid color split background, "
    "simplified but recognizable props and objects, "
    "wide 16:9 landscape composition, imperfect hand-drawn look"
)

# ── Negative prompt for Cloudflare SDXL (explicit exclusions) ─────────
NEGATIVE_PROMPT = (
    "realistic, photorealistic, 3D, anime, manga, "
    "detailed face, beautiful face, rosy cheeks, eyebrows, "
    "shading, gradients, soft lighting, blurry, "
    "watermark, text, photograph, CGI, render, "
    "high detail, pretty, cute illustration, "
    "portrait, close-up, square composition"
)

# ── Seed base for consistency ─────────────────────────────────────────
SEED_BASE = 42


def _build_prompt(scene, for_cloudflare=True):
    """Build full prompt: character DNA + scene + style lock."""
    scene = scene[:200]
    if for_cloudflare:
        # Cloudflare SDXL: concise, style-first
        return f"{CHARACTER_DNA}, {scene}, {STYLE_LOCK}"
    else:
        # Gemini: structured format
        return (
            f"Wide 16:9 landscape illustration. "
            f"Character: {CHARACTER_DNA}. "
            f"Scene: {scene}. "
            f"Style: {STYLE_LOCK}"
        )


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
            num_steps=20
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
    """Cloudflare SDXL (2 tries) → Gemini fallback (2 tries) → fail."""

    cf_prompt = _build_prompt(prompt, for_cloudflare=True)
    gemini_prompt = _build_prompt(prompt, for_cloudflare=False)

    # Cloudflare — primary (free, reliable, negative_prompt support)
    for attempt in range(2):
        print(f"    ☁️  Cloudflare [{attempt+1}/2]...")
        if _try_cloudflare(cf_prompt, output_path, image_index):
            return output_path

    # Gemini — fallback
    for attempt in range(2):
        print(f"    🎨 Gemini [{attempt+1}/2]...")
        if _try_gemini(gemini_prompt, output_path):
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

    cf_prompt = _build_prompt(
        f"YouTube thumbnail, vibrant colors, {title[:100]}, "
        f"surprised expression, bold composition",
        for_cloudflare=True
    )
    gemini_prompt = _build_prompt(
        f"YouTube thumbnail, vibrant colors, {title[:100]}, "
        f"surprised expression, bold composition",
        for_cloudflare=False
    )

    # Cloudflare primary → Gemini fallback → gradient fallback
    if not _try_cloudflare(cf_prompt, thumb, image_index=999):
        if not _try_gemini(gemini_prompt, thumb):
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
