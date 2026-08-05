"""Pollinations.ai — Free FLUX image generation (no API key needed).

Endpoint: GET https://image.pollinations.ai/prompt/{prompt}
Returns image bytes directly. FLUX model is free and unlimited.
Rate limit: ~1 request per 16 seconds (anonymous).
"""

import time
import urllib.parse
import requests
from pathlib import Path

_last_request = 0.0
RATE_LIMIT_SECONDS = 16  # anonymous rate limit


def generate_pollinations_image(prompt, output_path, width=1024, height=576,
                                 seed=None, model="flux"):
    """Generate image via Pollinations FLUX (free, no API key).

    3 attempts with rate limiting. Returns output_path on success.
    """
    global _last_request

    # URL-encode prompt (max 500 chars to stay safe)
    encoded = urllib.parse.quote(prompt[:500], safe="")

    # Build query params
    params = {
        "model": model,
        "width": width,
        "height": height,
        "nologo": "true",
    }
    if seed is not None:
        params["seed"] = seed

    query = urllib.parse.urlencode(params)
    url = f"https://image.pollinations.ai/prompt/{encoded}?{query}"

    for attempt in range(3):
        try:
            # Rate limit: 16s between requests
            wait = RATE_LIMIT_SECONDS - (time.time() - _last_request)
            if wait > 0:
                print(f"    ⏳ Rate limit: waiting {wait:.0f}s...")
                time.sleep(wait)

            _last_request = time.time()
            print(f"    🌸 Pollinations FLUX [{attempt+1}/3] (seed={seed})...")

            resp = requests.get(url, timeout=(15, 180))
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "image" not in content_type:
                print(f"    ⚠️  Not an image response: {content_type}")
                if attempt < 2:
                    time.sleep(5)
                continue

            output_path = Path(output_path)
            output_path.write_bytes(resp.content)

            if output_path.stat().st_size > 1000:
                return output_path
            else:
                print(f"    ⚠️  Image too small ({output_path.stat().st_size} bytes)")

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "?"
            print(f"    ⚠️  Attempt {attempt+1}: HTTP {status}")
        except Exception as e:
            print(f"    ⚠️  Attempt {attempt+1}: {e}")

        if attempt < 2:
            time.sleep(5)

    raise Exception("Pollinations FLUX failed after 3 attempts")
