"""Pollinations.ai — free image generation via HTTP GET."""

import time, urllib.parse, requests
from pathlib import Path

_last_request = 0.0


def generate_pollinations_image(prompt, output_path, width=1920, height=1080, seed=None):
    """Generate image. 3 attempts, 10s rate limit between requests."""
    global _last_request

    encoded = urllib.parse.quote(prompt[:500], safe="")
    params = f"width={width}&height={height}&nologo=true&safe=true&model=turbo"
    if seed:
        params += f"&seed={seed}"
    url = f"https://image.pollinations.ai/prompt/{encoded}?{params}"

    for attempt in range(3):
        try:
            wait = 10 - (time.time() - _last_request)
            if wait > 0:
                time.sleep(wait)

            _last_request = time.time()
            print(f"    🌐 Pollinations [{attempt+1}/3]...")

            resp = requests.get(url, timeout=(10, 60))
            resp.raise_for_status()

            if "image" not in resp.headers.get("content-type", ""):
                print(f"    ⚠️  Not an image response")
                continue

            output_path.write_bytes(resp.content)
            if output_path.stat().st_size > 1000:
                return output_path

        except Exception as e:
            print(f"    ⚠️  Attempt {attempt+1}: {e}")

        if attempt < 2:
            time.sleep(5)

    raise Exception("Pollinations failed after 3 attempts")
