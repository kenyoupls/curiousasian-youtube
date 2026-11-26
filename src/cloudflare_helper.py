"""Cloudflare Workers AI — FLUX.1 Schnell (primary) + SDXL Lightning (fallback).

Free tier: 10,000 neurons/day.
FLUX Schnell: ~50 neurons/image → ~200 images/day
SDXL Lightning: ~30 neurons/image → ~300 images/day (lower quality fallback)

API notes (checked 2026-11):
- FLUX Schnell only accepts {"prompt", "steps"}. Sending width/height/seed/num_steps
  gets "400 Additional or unevaluated properties" — this broke every run from 2026-08-15.
  It always returns a 1024x1024 JPEG (base64 in result.image); we crop it to 9:16 later.
- SDXL Lightning still accepts width/height/seed/num_steps and returns raw PNG bytes.
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
    "realistic, photorealistic, 3D, detailed face, "
    "blurry, watermark, text, photograph, CGI, render"
)


class CloudflareAuthError(RuntimeError):
    """Token missing, expired, revoked or lacking Workers AI permission.

    Retrying can never fix this — the pipeline should stop and tell the user.
    """


def is_configured():
    return bool(CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN)


def _raise_for_status(resp, label):
    if resp.status_code == 200:
        return
    try:
        err = resp.json()
        msg = err.get("errors", [{}])[0].get("message", resp.text[:200])
    except Exception:
        msg = resp.text[:200]
    if resp.status_code in (401, 403):
        raise CloudflareAuthError(f"Cloudflare {label} {resp.status_code}: {msg}")
    raise RuntimeError(f"Cloudflare {label} {resp.status_code}: {msg}")


def check_cloudflare():
    """Cheap preflight: one 1-step FLUX image. Raises CloudflareAuthError on bad token."""
    if not is_configured():
        raise CloudflareAuthError("CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN secrets are not set")
    resp = requests.post(f"{_BASE_URL}/{FLUX_MODEL}", headers=HEADERS,
                         json={"prompt": "a small red apple", "steps": 1}, timeout=60)
    _raise_for_status(resp, "FLUX preflight")


def generate_cloudflare_image(prompt, output_path, width=576, height=1024,
                               seed=None, negative_prompt=None, num_steps=4,
                               use_flux=True):
    """Generate image via Cloudflare FLUX Schnell (primary) or SDXL (fallback)."""
    if not is_configured():
        raise CloudflareAuthError("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN required")

    if use_flux:
        return _generate_flux(prompt, output_path, num_steps)
    return _generate_sdxl(prompt, output_path, width, height, seed,
                          negative_prompt, num_steps)


def _generate_flux(prompt, output_path, num_steps=4):
    """Generate via FLUX.1 Schnell. Response is JSON with a base64 JPEG."""
    payload = {
        "prompt": prompt[:2048],
        "steps": min(max(num_steps, 1), 8),
    }
    print(f"    ⚡ Cloudflare FLUX Schnell (steps={payload['steps']})...")

    resp = requests.post(f"{_BASE_URL}/{FLUX_MODEL}", headers=HEADERS, json=payload, timeout=120)
    _raise_for_status(resp, "FLUX")

    try:
        image_b64 = resp.json().get("result", {}).get("image", "")
        if not image_b64:
            raise RuntimeError("No image in FLUX response")
        image_bytes = base64.b64decode(image_b64)
    except json.JSONDecodeError:
        if "image" in resp.headers.get("content-type", ""):
            image_bytes = resp.content
        else:
            raise RuntimeError("Unexpected FLUX response format")

    output_path = Path(output_path)
    output_path.write_bytes(image_bytes)
    if output_path.stat().st_size < 1000:
        raise RuntimeError("FLUX returned tiny/empty image")
    return output_path


def _generate_sdxl(prompt, output_path, width=576, height=1024, seed=None,
                   negative_prompt=None, num_steps=8):
    """Generate via SDXL Lightning (fallback). Returns raw PNG bytes."""
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

    resp = requests.post(f"{_BASE_URL}/{SDXL_MODEL}", headers=HEADERS, json=payload, timeout=120)
    _raise_for_status(resp, "SDXL")

    content_type = resp.headers.get("content-type", "")
    if "image" not in content_type or len(resp.content) < 1000:
        raise RuntimeError(f"SDXL returned non-image: {content_type}")

    output_path = Path(output_path)
    output_path.write_bytes(resp.content)
    return output_path
