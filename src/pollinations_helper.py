"""Pollinations.ai — Flux image generation (free model, 0 pollen per image).

New API endpoint: gen.pollinations.ai/image/{prompt}
Requires API key via query param or header.
Flux model is free (∞ images per pollen).
"""

import time
import urllib.parse
import requests
from pathlib import Path
from src.config import POLLINATIONS_API_KEY

_last_request = 0.0


def generate_pollinations_image(prompt, output_path, width=1024, height=576,
                                 seed=None, model="flux"):
    """Generate image via Pollinations Flux. 3 attempts with rate limiting."""
    global _last_request

    if not POLLINATIONS_API_KEY:
        raise RuntimeError("POLLINATIONS_API_KEY not set")

    encoded = urllib.parse.quote(prompt[:500], safe="")
    params = f"model={model}&width={width}&height={height}&nologo=true"
    if seed is not None:
        params += f"&seed={seed}"
    params += f"&key={POLLINATIONS_API_KEY}"
    url = f"https://gen.pollinations.ai/image/{encoded}?{params}"

    for attempt in range(3):
        try:
            # Rate limit: 5s between requests
            wait = 5 - (time.time() - _last_request)
            if wait > 0:
                time.sleep(wait)

            _last_request = time.time()
            print(f"    🌸 Pollinations Flux [{attempt+1}/3] (seed={seed})...")

            resp = requests.get(url, timeout=(10, 120))

            if resp.status_code == 402:
                raise RuntimeError(f"Pollinations: insufficient pollen balance")
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "image" not in content_type:
                print(f"    ⚠️  Not an image response: {content_type}")
                continue

            output_path = Path(output_path)
            output_path.write_bytes(resp.content)
            if output_path.stat().st_size > 1000:
                return output_path

        except Exception as e:
            print(f"    ⚠️  Attempt {attempt+1}: {e}")
            if "insufficient pollen" in str(e).lower():
                raise  # Don't retry if out of pollen

        if attempt < 2:
            time.sleep(3)

    raise Exception("Pollinations Flux failed after 3 attempts")
