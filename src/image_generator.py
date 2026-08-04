"""Image generation — Pollinations.ai primary, Gemini fallback.

Generates simple cartoon-style images for video scenes.
Pollinations.ai: free, no API key, ~16s between requests.
Gemini: fallback if Pollinations fails.
"""

import base64
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from src.config import (
    IMAGE_STYLE, VIDEO_WIDTH, VIDEO_HEIGHT, OUTPUT_DIR
)
from src.pollinations_helper import generate_pollinations_image


class ImageGenerationFailed(Exception):
    """Raised when image generation fails after all retries.

    Pipeline catches this to skip the current script and try the next one.
    """
    pass


def _build_pollinations_prompt(scene_prompt: str) -> str:
    """Build a Pollinations-friendly prompt with style instructions."""
    return (
        f"Simple 2D cartoon, flat illustration, bold black outlines, "
        f"solid colors, round heads, dot eyes, simple expressions, "
        f"clean white background, minimal detail, explainer video style. "
        f"NO text, NO watermarks. "
        f"Scene: {scene_prompt}"
    )


def generate_single_image(prompt: str, output_path: Path, max_retries: int = 5) -> Path:
    """Generate one image. Tries Pollinations first, then Gemini fallback.

    Raises ImageGenerationFailed if all methods fail.
    """

    # === Try Pollinations.ai first (free, reliable) ===
    for attempt in range(max_retries):
        try:
            full_prompt = _build_pollinations_prompt(prompt)
            if attempt >= 2:
                # Simplify prompt on later retries
                full_prompt = (
                    "Simple colorful cartoon drawing, flat illustration style, "
                    "white background, minimal detail. "
                    f"Scene: {prompt}"
                )

            generate_pollinations_image(
                prompt=full_prompt,
                output_path=output_path,
                width=VIDEO_WIDTH,
                height=VIDEO_HEIGHT,
            )

            # Resize to exact video dimensions (Pollinations might return slightly different)
            img = Image.open(output_path)
            if img.size != (VIDEO_WIDTH, VIDEO_HEIGHT):
                img = img.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)
                img.save(output_path, "PNG")

            return output_path

        except Exception as e:
            print(f"    ⚠️  Pollinations attempt {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)

    # === Gemini fallback ===
    print("    🔄 Trying Gemini as fallback...")
    try:
        from src.gemini_helper import generate_image as gemini_generate

        for attempt in range(3):
            try:
                if attempt == 0:
                    full_prompt = f"{IMAGE_STYLE} Scene: {prompt}"
                else:
                    full_prompt = (
                        "Simple cartoon illustration, flat colors, minimal detail. "
                        f"Scene: {prompt}"
                    )

                response = gemini_generate(full_prompt)

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
                print(f"    ⚠️  Gemini attempt {attempt + 1}/3: {e}")
                if attempt < 2:
                    time.sleep(10)

    except ImportError:
        print("    ⚠️  Gemini not available")

    # All methods failed
    raise ImageGenerationFailed(
        f"All image generation methods failed for: {output_path.name}"
    )


def _create_fallback_image(description: str, output_path: Path) -> Path:
    """Create a clean fallback image with gradient + key phrase (thumbnails only)."""
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT))
    draw = ImageDraw.Draw(img)

    for y in range(VIDEO_HEIGHT):
        ratio = y / VIDEO_HEIGHT
        r = int(25 + ratio * 20)
        g = int(15 + ratio * 15)
        b = int(50 + ratio * 40)
        draw.line([(0, y), (VIDEO_WIDTH, y)], fill=(r, g, b))

    cx, cy = VIDEO_WIDTH // 2, VIDEO_HEIGHT // 2 - 40
    r = 80
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 215, 0), width=4)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
    except (OSError, IOError):
        font = ImageFont.load_default()
        font_small = font

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

        # No extra delay needed — pollinations_helper handles rate limiting internally

    print(f"🖼️  Generated {len(image_paths)} images total")
    return image_paths


def generate_thumbnail(script: dict) -> Path:
    """Generate a YouTube thumbnail — cartoon style with title overlay."""
    thumb_path = OUTPUT_DIR / "thumbnail.png"

    title = script["title"]
    prompt = (
        f"Eye-catching YouTube thumbnail, simple cartoon style, "
        f"bold vibrant colors, dramatic composition. "
        f"Topic: {title}. "
        f"Curious cartoon character looking surprised. "
        f"Bright yellow/orange accent colors. NO text in the image."
    )

    try:
        generate_pollinations_image(
            prompt=prompt,
            output_path=thumb_path,
            width=1280,
            height=720,
        )
    except Exception as e:
        print(f"  ⚠️  Pollinations thumbnail failed: {e}")
        # Try Gemini
        try:
            from src.gemini_helper import generate_image as gemini_generate
            response = gemini_generate(prompt)
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                    image_bytes = (
                        base64.b64decode(part.inline_data.data)
                        if isinstance(part.inline_data.data, str)
                        else part.inline_data.data
                    )
                    thumb_path.write_bytes(image_bytes)
                    break
        except Exception as e2:
            print(f"  ⚠️  Gemini thumbnail also failed: {e2}")

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
