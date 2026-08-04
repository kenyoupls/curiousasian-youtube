"""Image generation — Google Imagen primary, Pollinations fallback."""

import base64
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from src.config import IMAGE_STYLE, VIDEO_WIDTH, VIDEO_HEIGHT, OUTPUT_DIR


class ImageGenerationFailed(Exception):
    pass


# Stick figure style prefix for all image prompts
STICK_FIGURE_STYLE = (
    "simple stick figure cartoon, OverSimplified style, "
    "round white head, two dot eyes, straight line mouth, "
    "messy brown hair, stick body, thick black outlines, "
    "flat solid colors, NO photorealism, NO 3D, NO shading, NO gradients, "
    "simple background. "
)


def _prompt(scene):
    """Build image prompt: stick figure style + scene description."""
    scene = scene[:180]
    return f"{STICK_FIGURE_STYLE}{scene}"


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
        # Image is wider — scale by height, crop sides
        new_h = target_h
        new_w = int(new_h * img_ratio)
    else:
        # Image is taller — scale by width, crop top/bottom
        new_w = target_w
        new_h = int(new_w / img_ratio)

    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Center crop to exact target
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    img = img.crop((left, top, left + target_w, top + target_h))
    return img


def _try_imagen(prompt, output_path):
    """Try Google Imagen via Gemini API. Returns True on success."""
    try:
        from src.gemini_helper import generate_image
        resp = generate_image(
            f"Wide 16:9 landscape illustration, simple stick figure cartoon: {prompt[:180]}"
        )
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
        print(f"    ⚠️  Imagen: {e}")
    return False


def _try_pollinations(prompt, output_path):
    """Try Pollinations.ai. Returns True on success."""
    try:
        from src.pollinations_helper import generate_pollinations_image
        generate_pollinations_image(_prompt(prompt), output_path, VIDEO_WIDTH, VIDEO_HEIGHT)
        img = Image.open(output_path).convert("RGB")
        if img.size != (VIDEO_WIDTH, VIDEO_HEIGHT):
            img = _fit_to_hd(img)
        img.save(output_path, "PNG")
        return True
    except Exception as e:
        print(f"    ⚠️  Pollinations: {e}")
    return False


def generate_single_image(prompt, output_path):
    """Google Imagen (2 tries) → Pollinations (2 tries) → fail."""

    # Google Imagen — primary
    for attempt in range(2):
        print(f"    🎨 Imagen [{attempt+1}/2]...")
        if _try_imagen(prompt, output_path):
            return output_path

    # Pollinations — fallback
    for attempt in range(2):
        print(f"    🌐 Pollinations [{attempt+1}/2]...")
        if _try_pollinations(prompt, output_path):
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
        generate_single_image(p["image_prompt"], out)
        paths.append(out)

    print(f"🖼️  {len(paths)} images total")
    return paths


def generate_thumbnail(script):
    """Thumbnail with title overlay."""
    thumb = OUTPUT_DIR / "thumbnail.png"
    title = script["title"]

    # Try Imagen first, then Pollinations
    prompt = f"YouTube thumbnail, stick figure cartoon, vibrant, {title[:100]}, surprised stick figure character"
    if not _try_imagen(prompt, thumb):
        if not _try_pollinations(
            f"stick figure YouTube thumbnail, thick outlines, vibrant, {title[:100]}, surprised character",
            thumb
        ):
            # Fallback gradient
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
