"""Pollinations.ai image generation — free, no API key needed."""

import time
import urllib.parse
import requests
from pathlib import Path

_last_request_time = 0.0
RATE_LIMIT_DELAY = 5  # 5s between requests (push the limit)


def generate_pollinations_image(
    prompt: str,
    output_path: Path,
    width: int = 1920,
    height: int = 1080,
    max_retries: int = 2,
    seed: int = None,
) -> Path:
    global _last_request_time

    encoded_prompt = urllib.parse.quote(prompt, safe="")

    params = {"width": width, "height": height, "nologo": "true", "safe": "true"}
    if seed is not None:
        params["seed"] = seed

    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?{query_string}"

    for attempt in range(max_retries):
        try:
            # Rate limiting
            elapsed = time.time() - _last_request_time
            if elapsed < RATE_LIMIT_DELAY:
                time.sleep(RATE_LIMIT_DELAY - elapsed)

            _last_request_time = time.time()
            print(f"    🌐 Pollinations request (attempt {attempt + 1})...")

            response = requests.get(url, timeout=(10, 45), stream=True)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "image" not in content_type:
                print(f"    ⚠️  Non-image response: {content_type}")
                continue

            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            if output_path.exists() and output_path.stat().st_size > 1000:
                return output_path

        except requests.exceptions.Timeout:
            print(f"    ⚠️  Timeout (attempt {attempt + 1})")
        except requests.exceptions.RequestException as e:
            print(f"    ⚠️  Failed (attempt {attempt + 1}): {e}")

        if attempt < max_retries - 1:
            time.sleep(3)

    raise Exception(f"Pollinations failed after {max_retries} attempts")
