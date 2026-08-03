"""Image generation using Gemini — simple cartoon style, 1 per 3 seconds."""

import base64
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from src.config import (
    IMAGE_STYLE, VIDEO_WIDTH, VIDEO_HEIGHT, OUTPUT_DIR
)
from src.gemini_helper import generate_image


class ImageGenerationFailed(Exception):
    """Raised when image generation fails after all retries.

    Pipeline catches this to skip the current script and try the next one.
    """
    pass


def generate_single_image(prompt: str, output_path: Path, max_retries: int = 5) -> Path:
    """Generate one image. Retries with modified prompts on failure."""

    for attempt in range(max_retries):
        try:
            # On retry, simplify the prompt to avoid content policy blocks
            if attempt == 0:
                full_prompt = f"{IMAGE_STYLE} Scene: {prompt}"
            elif attempt < 3:
                full_prompt = f"Simple cartoon illustration, flat colors, minimal detail. Scene: {prompt}"
            else:
                # Very simplified fallback prompt
                full_prompt = f"Simple colorful cartoon drawing of a person in a scene. Flat illustration style, white background."

            response = generate_image(full_prompt)

            # Extract image from response
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                    image_bytes = (
                        base64.b64decode(part.inline_data.data)
                        if isinstance(part.inline_data.data, str)
                        else part.inline_data.data
                    )
                    output_path.write_bytes(image_bytes)

                    # Resize to video dimensions
                    img = Image.open(output_path)
                    img = img.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)
                    img.save(output_path, "PNG")
                    return output_path

            print(f"    ⚠️  No image data in response (attempt {attempt + 1}/{max_retries})")

        except Exception as e:
            print(f"    ⚠️  Attempt {attempt + 1}/{max_retries} failed: {e}")

        # Backoff between retries
        if attempt < max_retries - 1:
            wait = 3 * (attempt + 1)
            time.sleep(wait)

    # All retries exhausted — raise so pipeline skips this script
    raise ImageGenerationFailed(
        f"All {max_retries} retries failed for: {output_path.name}"
    )


def _create_fallback_image(description: str, output_path: Path) -> Path:
    """Create a clean fallback image with gradient + key phrase."""
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT))
    draw = ImageDraw.Draw(img)

    # Soft gradient background (dark blue to purple)
    for y in range(VIDEO_HEIGHT):
        ratio = y / VIDEO_HEIGHT
        r = int(25 + ratio * 20)
        g = int(15 + ratio * 15)
        b = int(50 + ratio * 40)
        draw.line([(0, y), (VIDEO_WIDTH, y)], fill=(r, g, b))

    # Center icon: simple question mark circle
    cx, cy = VIDEO_WIDTH // 2, VIDEO_HEIGHT // 2 - 40
    r = 80
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 215, 0), width=4)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
    except (OSError, IOError):
        font = ImageFont.load_default()
        font_small = font

    # Question mark
    bbox = draw.textbbox((0, 0), "?", font=font)
    qx = cx - (bbox[2] - bbox[0]) // 2
    qy = cy - (bbox[3] - bbox[1]) // 2
    draw.text((qx, qy), "?", fill=(255, 215, 0), font=font)

    img.save(output_path, "PNG")
    return output_path


def generate_all_images(image_prompts: list[dict]) -> list[Path]:
    """Generate all images for the video.

    Args:
        image_prompts: List from image_prompt_generator with image_prompt, key_phrase, etc.

    Returns:
        List of image file paths in order.
    """
    images_dir = OUTPUT_DIR / "images"
    images_dir.mkdir(exist_ok=True)

    image_paths = []
    total = len(image_prompts)

    for i, prompt_data in enumerate(image_prompts):
        output_path = images_dir / f"img_{i:04d}.png"

        # Skip if already generated (for reruns)
        if output_path.exists():
            image_paths.append(output_path)
            continue

        print(f"  🖼️  [{i + 1}/{total}] Generating image...")
        generate_single_image(prompt_data["image_prompt"], output_path)
        image_paths.append(output_path)

        # Rate limit: small delay between requests
        time.sleep(1.5)

    print(f"🖼️  Generated {len(image_paths)} images total")
    return image_paths


def generate_thumbnail(script: dict) -> Path:
    """Generate a YouTube thumbnail — cartoon style with title overlay."""
    thumb_path = OUTPUT_DIR / "thumbnail.png"

    title = script["title"]
    prompt = (
        f"Eye-catching YouTube thumbnail illustration. Simple cartoon style, "
        f"bold vibrant colors, dramatic composition. "
        f"Topic: {title}. "
        f"Show a curious cartoon character looking surprised or intrigued. "
        f"Bright yellow/orange accent colors. NO text in the image."
    )

    try:
        response = generate_image(prompt)

        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                image_bytes = (
                    base64.b64decode(part.inline_data.data)
                    if isinstance(part.inline_data.data, str)
                    else part.inline_data.data
                )
                thumb_path.write_bytes(image_bytes)
                break
    except Exception as e:
        print(f"  ⚠️  Thumbnail generation failed: {e}")

    # Ensure thumbnail exists
    if not thumb_path.exists():
        _create_fallback_image(title, thumb_path)

    # Resize to 1280x720 and add title overlay
    img = Image.open(thumb_path).resize((1280, 720), Image.LANCZOS)
    draw = ImageDraw.Draw(img)

    try:
        font_large = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 56
        )
    except (OSError, IOError):
        font_large = ImageFont.load_default()

    # Wrap title text
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

    # Dark overlay at bottom
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
    print(f"🎨 Thumbnail generated")
    return thumb_path
