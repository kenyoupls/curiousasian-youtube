"""Gemini API helper — auto-fallback across models, never gives up on 503/429."""

import time
from google import genai
from google.genai import types
from src.config import (
    GEMINI_API_KEY, GEMINI_TEXT_MODELS, GEMINI_IMAGE_MODELS
)


def _get_client():
    return genai.Client(api_key=GEMINI_API_KEY)


def generate_text(prompt: str) -> str:
    """Generate text — cycles through all models, retries forever on 503/429.

    Only gives up on 404 (model doesn't exist) after exhausting all models.
    """
    client = _get_client()
    round_num = 0

    while True:
        round_num += 1
        for model in GEMINI_TEXT_MODELS:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt
                )
                return response.text
            except Exception as e:
                err_str = str(e)
                if "503" in err_str or "429" in err_str:
                    wait = min(60, 15 * round_num)
                    print(f"    ⚠️  {model} overloaded (round {round_num}), retrying in {wait}s...")
                    time.sleep(wait)
                elif "404" in err_str:
                    print(f"    ⚠️  {model} not available, trying next...")
                    continue
                else:
                    raise


def generate_image(prompt: str):
    """Generate an image — cycles through all models, retries forever on 503/429.

    Returns the response object from Gemini.
    Only gives up on 404 after exhausting all models.
    """
    client = _get_client()
    round_num = 0

    while True:
        round_num += 1
        for model in GEMINI_IMAGE_MODELS:
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
                err_str = str(e)
                if "503" in err_str or "429" in err_str:
                    wait = min(90, 20 * round_num)
                    print(f"    ⚠️  {model} overloaded (round {round_num}), retrying in {wait}s...")
                    time.sleep(wait)
                elif "404" in err_str:
                    print(f"    ⚠️  {model} not available, trying next...")
                    continue
                else:
                    raise
