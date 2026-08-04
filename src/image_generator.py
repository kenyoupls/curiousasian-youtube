"""Image generation — Pollinations.ai primary, Gemini fallback. Speed-optimized."""

import base64
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from src.config import IMAGE_STYLE, VIDEO_WIDTH, VIDEO_HEIGHT, OUTPUT_DIR
from src.pollinations_helper import generate_pollinations_image


class ImageGenerationFailed(Exception):
    pass


def _build_pollinations_prompt(scene_prompt: str) -> str:
    """Short prompt for URL. Max ~300 chars."""
    style = "flat 2D cartoon, bold outlines, solid colors, white background"
    scene = scene_prompt
    for phrase in ["Simple flat 2D cartoon,", "bold black outlines,", "solid colors."]:
        scene = scene.replace(phrase, "")
    scene = scene.strip()
    if len(scene) > 250:
        scene = scene[:247] + "..."
    return f"{style}. {scene}"


def generate_single_image(prompt: str, output_path: Path) -> Path:
    """Generate one image. Pollinations first, Gemini fallback. Fail fast."""

    # === Pollinations (2 attempts) ===
    for attempt in range(2):
        try:
            full_prompt = _build_pollinations_prompt(prompt)
            generate_pollinations_image(
                prompt=full_prompt,
                output_path=output_path,
                width=VIDEO_WIDTH,
                height=VIDEO_HEIGHT,
            )
            img = Image.open(output_path)
            if img.size != (VIDEO_WIDTH, VIDEO_HEIGHT):
                img = img.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)
                img.save(output_path, "PNG")
            return output_path
        except Exception as e:
            print(f"    ⚠️  Pollinations attempt {attempt + 1}/2: {e}")

    # === Gemini fallback (1 attempt) ===
    try:
        from src.gemini_helper import generate_image as gemini_generate
        response = gemini_generate(f"Simple cartoon: {prompt}")
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                image_bytes = (
                    base64.b64decode(part.inline_data.data)
                    if isinstance(part.inline_data.data, str)
                    else part.inline_data.data
                )
                output_path.write_bytes(image_bytes)
                img = Image.open(output_path)
                img = img.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)
                img.save(output_path, "PNG")
                return output_path
    except Exception as e:
        print(f"    ⚠️  Gemini fallback failed: {e}")

    raise ImageGenerationFailed(f"All methods failed for: {output_path.name}")


def generate_all_images(image_prompts: list[dict]) -> list[Path]:
    images_dir = OUTPUT_DIR / "images"
    images_dir.mkdir(exist_ok=True)

    image_paths = []
    total = len(image_prompts)

    for i, prompt_data in enumerate(image_prompts):
        output_path = images_dir / f"img_{i:04d}.png"
        if output_path.exists():
            image_paths.append(output_path)
            continue

        print(f"  🖼️  [{i + 1}/{total}] Generating image...")
        generate_single_image(prompt_data["image_prompt"], output_path)
        image_paths.append(output_path)

    print(f"🖼️  Generated {len(image_paths)} images total")
    return image_paths


def _create_fallback_image(description: str, output_path: Path) -> Path:
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT))
    draw = ImageDraw.Draw(img)
    for y in range(VIDEO_HEIGHT):
        ratio = y / VIDEO_HEIGHT
        draw.line([(0, y), (VIDEO_WIDTH, y)],
                  fill=(int(25 + ratio * 20), int(15 + ratio * 15), int(50 + ratio * 40)))
    cx, cy = VIDEO_WIDTH // 2, VIDEO_HEIGHT // 2 - 40
    r = 80
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 215, 0), width=4)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
    except (OSError, IOError):
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "?", font=font)
    draw.text((cx - (bbox[2] - bbox[0]) // 2, cy - (bbox[3] - bbox[1]) // 2),
              "?", fill=(255, 215, 0), font=font)
    img.save(output_path, "PNG")
    return output_path


def generate_thumbnail(script: dict) -> Path:
    thumb_path = OUTPUT_DIR / "thumbnail.png"
    title = script["title"]
    prompt = f"YouTube thumbnail, cartoon, vibrant colors, {title}, surprised character, NO text"

    try:
        generate_pollinations_image(prompt=prompt, output_path=thumb_path, width=1280, height=720)
    except Exception:
        _create_fallback_image(title, thumb_path)

    if not thumb_path.exists():
        _create_fallback_image(title, thumb_path)

    # Add title overlay
    img = Image.open(thumb_path).resize((1280, 720), Image.LANCZOS)
    draw = ImageDraw.Draw(img)
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 56)
    except (OSError, IOError):
        font_large = ImageFont.load_default()

    words = title.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font_large)
        if bbox[2] - bbox[0] > 1100:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)

    overlay_height = len(lines) * 70 + 40
    overlay_y = 720 - overlay_height
    overlay = Image.new("RGBA", (1280, overlay_height), (0, 0, 0, 180))
    img = img.convert("RGBA")
    img.paste(overlay, (0, overlay_y), overlay)
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font_large)
        x = (1280 - (bbox[2] - bbox[0])) // 2
        y = overlay_y + 20 + i * 70
        draw.text((x + 2, y + 2), line, fill=(0, 0, 0), font=font_large)
        draw.text((x, y), line, fill=(255, 215, 0), font=font_large)

    img.convert("RGB").save(thumb_path, "PNG")
    print(f"🎨 Thumbnail done")
    return thumb_path
