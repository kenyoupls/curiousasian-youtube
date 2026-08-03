"""Gemini API helper — auto-fallback across models on 503/429 errors."""

import time
from google import genai
from google.genai import types
from src.config import (
    GEMINI_API_KEY, GEMINI_TEXT_MODELS, GEMINI_IMAGE_MODELS
)


def _get_client():
    return genai.Client(api_key=GEMINI_API_KEY)


def generate_text(prompt: str, max_retries: int = 3) -> str:
    """Generate text, auto-falling back across models on failure.

    Tries each model in GEMINI_TEXT_MODELS. For each model, retries
    up to max_retries times with backoff before moving to the next.
    """
    client = _get_client()
    last_error = None

    for model in GEMINI_TEXT_MODELS:
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt
                )
                return response.text
            except Exception as e:
                last_error = e
                err_str = str(e)
                # Model unavailable or rate limited — try next model
                if "503" in err_str or "429" in err_str:
                    print(f"    ⚠️  {model} unavailable (attempt {attempt + 1}), ", end="")
                    if attempt < max_retries - 1:
                        wait = 15 * (attempt + 1)
                        print(f"retrying in {wait}s...")
                        time.sleep(wait)
                    else:
                        print(f"switching model...")
                    continue
                # 404 = model doesn't exist for this account
                elif "404" in err_str:
                    print(f"    ⚠️  {model} not available, trying next...")
                    break  # Skip retries, go to next model
                else:
                    raise  # Unknown error — don't retry

    raise RuntimeError(f"All text models failed. Last error: {last_error}")


def generate_image(prompt: str, max_retries: int = 3):
    """Generate an image, auto-falling back across models on failure.

    Returns the response object from Gemini.
    """
    client = _get_client()
    last_error = None

    for model in GEMINI_IMAGE_MODELS:
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE", "TEXT"]
                    )
                )
                return response
            except Exception as e:
                last_error = e
                err_str = str(e)
                if "503" in err_str or "429" in err_str:
                    print(f"    ⚠️  {model} unavailable (attempt {attempt + 1}), ", end="")
                    if attempt < max_retries - 1:
                        wait = 15 * (attempt + 1)
                        print(f"retrying in {wait}s...")
                        time.sleep(wait)
                    else:
                        print(f"switching model...")
                    continue
                elif "404" in err_str:
                    print(f"    ⚠️  {model} not available, trying next...")
                    break
                else:
                    raise

    raise RuntimeError(f"All image models failed. Last error: {last_error}")
