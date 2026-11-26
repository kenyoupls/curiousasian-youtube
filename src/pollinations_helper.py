"""Pollinations.ai — optional backup image engine.

Since late 2026 Pollinations needs an API key (anonymous image.pollinations.ai returns 503,
gen.pollinations.ai returns 401 without a key). A key from https://enter.pollinations.ai
can be stored as the POLLINATIONS_API_KEY GitHub secret; without it this engine is skipped.
"""

import os
import time
import urllib.parse
import requests
from pathlib import Path

POLLINATIONS_API_KEY = os.environ.get("POLLINATIONS_API_KEY", "").strip()

_last_request = 0.0
RATE_LIMIT_SECONDS = 5


def is_configured():
    return bool(POLLINATIONS_API_KEY)


def generate_pollinations_image(prompt, output_path, width=576, height=1024,
                                 seed=None, model="flux"):
    """Generate image via Pollinations (needs POLLINATIONS_API_KEY). 2 attempts."""
    global _last_request
    if not is_configured():
        raise RuntimeError("Pollinations skipped: POLLINATIONS_API_KEY not set")

    encoded = urllib.parse.quote(prompt[:500], safe="")
    params = {"model": model, "width": width, "height": height, "nologo": "true"}
    if seed is not None:
        params["seed"] = seed
    url = f"https://gen.pollinations.ai/image/{encoded}?{urllib.parse.urlencode(params)}"
    headers = {"Authorization": f"Bearer {POLLINATIONS_API_KEY}"}

    last_err = None
    for attempt in range(2):
        wait = RATE_LIMIT_SECONDS - (time.time() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.time()
        print(f"    🌸 Pollinations {model} [{attempt+1}/2] (seed={seed})...")
        try:
            resp = requests.get(url, headers=headers, timeout=(15, 180))
            if resp.status_code in (401, 402, 403):
                raise RuntimeError(f"Pollinations {resp.status_code}: key invalid or out of credit")
            resp.raise_for_status()
            if "image" not in resp.headers.get("content-type", "") or len(resp.content) < 1000:
                raise RuntimeError("Pollinations returned a non-image response")
            output_path = Path(output_path)
            output_path.write_bytes(resp.content)
            return output_path
        except Exception as e:
            last_err = e
            print(f"    ⚠️  Pollinations attempt {attempt+1}: {e}")

    raise RuntimeError(f"Pollinations failed: {last_err}")
