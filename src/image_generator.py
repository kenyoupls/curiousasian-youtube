"""Image generation — Pollinations primary, Gemini fallback."""

import base64
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from src.config import IMAGE_STYLE, VIDEO_WIDTH, VIDEO_HEIGHT, OUTPUT_DIR
from src.pollinations_helper import generate_pollinations_image


class ImageGenerationFailed(Exception):
    pass


def _prompt(scene):
    """Short style + scene for Pollinations URL."""
    scene = scene[:200]
    return (
        "simple stick figure webcomic, OverSimplified style, "
        "round heads, dot eyes, thick black outlines, "
        "muted earth tones, flat solid colors, minimal detail, "
        "NO photorealism, NO 3D, NO shading, NO gradients. "
        f"{scene}"
    )


def generate_single_image(prompt, output_path):
    """Pollinations (3 tries) → Gemini (1 try) → fail."""

    # Pollinations
    for attempt in range(3):
        try:
            generate_pollinations_image(_prompt(prompt), output_path, VIDEO_WIDTH, VIDEO_HEIGHT)
            img = Image.open(output_path)
            if img.size != (VIDEO_WIDTH, VIDEO_HEIGHT):
                img.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS).save(output_path, "PNG")
            return output_path
        except Exception as e:
            print(f"    ⚠️  Pollinations [{attempt+1}/3]: {e}")

    # Gemini fallback
    try:
        from src.gemini_helper import generate_image as gem_img
        resp = gem_img(f"Simple cartoon: {prompt[:200]}")
        for part in resp.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                data = part.inline_data.data
                output_path.write_bytes(base64.b64decode(data) if isinstance(data, str) else data)
                Image.open(output_path).resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS).save(output_path, "PNG")
                return output_path
    except Exception as e:
        print(f"    ⚠️  Gemini fallback: {e}")

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

    try:
        generate_pollinations_image(
            f"simple stick figure webcomic thumbnail, OverSimplified style, thick outlines, muted colors, {title[:100]}, surprised stick figure character, NO photorealism, NO 3D",
            thumb, 1280, 720
        )
    except Exception:
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
