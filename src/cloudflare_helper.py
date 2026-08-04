"""Cloudflare Workers AI — SDXL Lightning image generation.

Free tier ($0.00/step), supports negative_prompt, seed, width/height.
Model: @cf/bytedance/stable-diffusion-xl-lightning
"""

import requests
from pathlib import Path
from src.config import CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN

API_URL = (
    f"https://api.cloudflare.com/client/v4/accounts/"
    f"{CLOUDFLARE_ACCOUNT_ID}/ai/run/"
    f"@cf/bytedance/stable-diffusion-xl-lightning"
)

HEADERS = {
    "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
}

# Style control via negative_prompt — big advantage over Pollinations
DEFAULT_NEGATIVE_PROMPT = (
    "realistic, photorealistic, 3D, anime, manga, detailed face, "
    "shading, gradients, soft lighting, blurry, watermark, text, "
    "photograph, CGI, render, high detail skin, beautiful, pretty"
)


def generate_cloudflare_image(prompt, output_path, width=1024, height=1024,
                               seed=None, negative_prompt=None, num_steps=20):
    """Generate image via Cloudflare SDXL Lightning.

    Args:
        prompt: Text description of the image
        output_path: Path to save the image
        width: Image width (256-2048)
        height: Image height (256-2048)
        seed: Reproducibility seed
        negative_prompt: What to exclude from the image
        num_steps: Diffusion steps (1-20, default 20)

    Returns:
        output_path on success

    Raises:
        Exception on failure
    """
    if not CLOUDFLARE_ACCOUNT_ID or not CLOUDFLARE_API_TOKEN:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN required")

    payload = {
        "prompt": prompt[:2048],
        "negative_prompt": negative_prompt or DEFAULT_NEGATIVE_PROMPT,
        "width": min(max(width, 256), 2048),
        "height": min(max(height, 256), 2048),
        "num_steps": min(max(num_steps, 1), 20),
    }
    if seed is not None:
        payload["seed"] = seed

    print(f"    ☁️  Cloudflare SDXL (seed={seed}, {width}x{height})...")

    resp = requests.post(API_URL, headers=HEADERS, json=payload, timeout=120)

    if resp.status_code != 200:
        # Try to extract error message
        try:
            err = resp.json()
            msg = err.get("errors", [{}])[0].get("message", resp.text[:200])
        except Exception:
            msg = resp.text[:200]
        raise RuntimeError(f"Cloudflare API {resp.status_code}: {msg}")

    # Response is raw image bytes (PNG)
    content_type = resp.headers.get("content-type", "")
    if "image" not in content_type and len(resp.content) < 1000:
        raise RuntimeError(f"Cloudflare returned non-image: {content_type}")

    output_path = Path(output_path)
    output_path.write_bytes(resp.content)
    return output_path
