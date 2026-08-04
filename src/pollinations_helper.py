"""Pollinations.ai image generation — free, no API key needed.

Simple HTTP GET → returns PNG image directly.
Rate limit: 1 request per 15s (anonymous), 1 per 5s (registered).
"""

import time
import urllib.parse
import requests
from pathlib import Path

# Track last request time for rate limiting
_last_request_time = 0.0
RATE_LIMIT_DELAY = 16  # 16s between requests (15s limit + 1s buffer)


def generate_pollinations_image(
    prompt: str,
    output_path: Path,
    width: int = 1920,
    height: int = 1080,
    max_retries: int = 3,
    seed: int = None,
) -> Path:
    """Generate an image using Pollinations.ai.

    Args:
        prompt: Text description for the image.
        output_path: Where to save the PNG.
        width: Image width in pixels.
        height: Image height in pixels.
        max_retries: Number of retry attempts on failure.
        seed: Optional seed for reproducible generation.

    Returns:
        Path to the saved image.

    Raises:
        Exception: If all retries fail.
    """
    global _last_request_time

    # URL-encode the prompt
    encoded_prompt = urllib.parse.quote(prompt, safe="")

    # Build URL
    params = {
        "width": width,
        "height": height,
        "nologo": "true",
        "safe": "true",
    }
    if seed is not None:
        params["seed"] = seed

    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?{query_string}"

    for attempt in range(max_retries):
        try:
            # Rate limiting — wait if needed
            elapsed = time.time() - _last_request_time
            if elapsed < RATE_LIMIT_DELAY:
                wait = RATE_LIMIT_DELAY - elapsed
                print(f"    ⏳ Rate limit: waiting {wait:.0f}s...")
                time.sleep(wait)

            _last_request_time = time.time()

            # Timeout: 60s connect + 60s read (was 120s single timeout)
            print(f"    🌐 Requesting image from Pollinations... (attempt {attempt + 1})")
            response = requests.get(url, timeout=(15, 60), stream=True)
            response.raise_for_status()

            # Verify we got an image (not an error page)
            content_type = response.headers.get("content-type", "")
            if "image" not in content_type:
                print(f"    ⚠️  Got non-image response: {content_type} (attempt {attempt + 1})")
                if attempt < max_retries - 1:
                    time.sleep(5)
                continue

            # Save the image
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Verify file was written and has content
            if output_path.exists() and output_path.stat().st_size > 1000:
                return output_path
            else:
                print(f"    ⚠️  Image file too small or empty (attempt {attempt + 1})")

        except requests.exceptions.Timeout:
            print(f"    ⚠️  Timeout (attempt {attempt + 1}/{max_retries})")
        except requests.exceptions.RequestException as e:
            print(f"    ⚠️  Request failed (attempt {attempt + 1}/{max_retries}): {e}")

        # Backoff between retries
        if attempt < max_retries - 1:
            wait = 10 * (attempt + 1)
            print(f"    ⏳ Retrying in {wait}s...")
            time.sleep(wait)

    raise Exception(f"Pollinations image generation failed after {max_retries} attempts")
