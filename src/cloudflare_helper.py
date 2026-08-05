"""Cloudflare Workers AI — FLUX.1 Schnell (primary) + SDXL Lightning (fallback).

Free tier: 10,000 neurons/day.
FLUX Schnell: ~50 neurons/image → ~200 images/day
SDXL Lightning: ~30 neurons/image → ~300 images/day (lower quality fallback)
"""

import base64
import json
import requests
from pathlib import Path
from src.config import CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN

_BASE_URL = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run"

FLUX_MODEL = "@cf/black-forest-labs/flux-1-schnell"
SDXL_MODEL = "@cf/bytedance/stable-diffusion-xl-lightning"

HEADERS = {
    "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
    "Content-Type": "application/json",
}

# SDXL fallback negative prompt
SDXL_NEGATIVE_PROMPT = (
    "realistic, photorealistic, 3D, anime, manga, detailed face, "
    "shading, gradients, soft lighting, blurry, watermark, text, "
    "photograph, CGI, render, high detail skin, beautiful, pretty"
)


def generate_cloudflare_image(prompt, output_path, width=1024, height=576,
                               seed=None, negative_prompt=None, num_steps=4,
                               use_flux=True):
    """Generate image via Cloudflare FLUX Schnell (primary) or SDXL (fallback).

    FLUX Schnell returns JSON with base64 image.
    SDXL Lightning returns raw PNG bytes.
    """
    if not CLOUDFLARE_ACCOUNT_ID or not CLOUDFLARE_API_TOKEN:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN required")

    if use_flux:
        return _generate_flux(prompt, output_path, width, height, seed, num_steps)
    else:
        return _generate_sdxl(prompt, output_path, width, height, seed,
                              negative_prompt, num_steps)


def _generate_flux(prompt, output_path, width=1024, height=576, seed=None,
                   num_steps=4):
    """Generate via FLUX.1 Schnell. Returns base64 JSON response."""
    url = f"{_BASE_URL}/{FLUX_MODEL}"

    payload = {
        "prompt": prompt[:2048],
        "width": min(max(width, 256), 1024),
        "height": min(max(height, 256), 1024),
        "num_steps": min(max(num_steps, 1), 8),
    }
    if seed is not None:
        payload["seed"] = seed

    print(f"    ⚡ Cloudflare FLUX Schnell (seed={seed}, {width}x{height})...")

    resp = requests.post(url, headers=HEADERS, json=payload, timeout=120)

    if resp.status_code != 200:
        try:
            err = resp.json()
            msg = err.get("errors", [{}])[0].get("message", resp.text[:200])
        except Exception:
            msg = resp.text[:200]
        raise RuntimeError(f"Cloudflare FLUX {resp.status_code}: {msg}")

    # FLUX returns JSON with base64 image
    try:
        data = resp.json()
        image_b64 = data.get("result", {}).get("image", "")
        if not image_b64:
            raise RuntimeError("No image in FLUX response")
        image_bytes = base64.b64decode(image_b64)
    except (json.JSONDecodeError, KeyError):
        # Maybe it returned raw bytes
        content_type = resp.headers.get("content-type", "")
        if "image" in content_type:
            image_bytes = resp.content
        else:
            raise RuntimeError(f"Unexpected FLUX response format")

    output_path = Path(output_path)
    output_path.write_bytes(image_bytes)

    if output_path.stat().st_size < 1000:
        raise RuntimeError("FLUX returned tiny/empty image")

    return output_path


def _generate_sdxl(prompt, output_path, width=1024, height=576, seed=None,
                   negative_prompt=None, num_steps=8):
    """Generate via SDXL Lightning (fallback). Returns raw PNG bytes."""
    url = f"{_BASE_URL}/{SDXL_MODEL}"

    payload = {
        "prompt": prompt[:2048],
        "negative_prompt": negative_prompt or SDXL_NEGATIVE_PROMPT,
        "width": min(max(width, 256), 2048),
        "height": min(max(height, 256), 2048),
        "num_steps": min(max(num_steps, 1), 20),
    }
    if seed is not None:
        payload["seed"] = seed

    print(f"    ☁️  Cloudflare SDXL Lightning (seed={seed}, {width}x{height})...")

    resp = requests.post(url, headers=HEADERS, json=payload, timeout=120)

    if resp.status_code != 200:
        try:
            err = resp.json()
            msg = err.get("errors", [{}])[0].get("message", resp.text[:200])
        except Exception:
            msg = resp.text[:200]
        raise RuntimeError(f"Cloudflare SDXL {resp.status_code}: {msg}")

    content_type = resp.headers.get("content-type", "")
    if "image" not in content_type and len(resp.content) < 1000:
        raise RuntimeError(f"SDXL returned non-image: {content_type}")

    output_path = Path(output_path)
    output_path.write_bytes(resp.content)
    return output_path
