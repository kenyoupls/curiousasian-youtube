"""Gemini API helper — auto-fallback across models, never gives up on 503/429.

Once a model works, sticks with it for consistency.
"""

import time
from google import genai
from google.genai import types
from src.config import (
    GEMINI_API_KEY, GEMINI_TEXT_MODELS, GEMINI_IMAGE_MODELS
)

# Track which model is working — stick with it for consistency
_working_text_model = None
_working_image_model = None


def _get_client():
    return genai.Client(api_key=GEMINI_API_KEY)


def _get_model_order(models: list, working_model: str = None) -> list:
    """Put the known working model first, then the rest."""
    if working_model and working_model in models:
        return [working_model] + [m for m in models if m != working_model]
    return models


def generate_text(prompt: str) -> str:
    """Generate text — tries working model first, falls back to others.

    Never gives up on 503/429 — keeps cycling until one works.
    """
    global _working_text_model
    client = _get_client()
    round_num = 0
    models = _get_model_order(GEMINI_TEXT_MODELS, _working_text_model)

    while True:
        round_num += 1
        for model in models:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt
                )
                _working_text_model = model
                if round_num == 1:
                    print(f"    ✅ Using text model: {model}")
                # Guard against None response
                result = response.text
                if result is None:
                    print(f"    ⚠️  {model} returned empty response, retrying...")
                    time.sleep(5)
                    continue
                return result
            except Exception as e:
                err_str = str(e)
                if "503" in err_str or "429" in err_str:
                    wait = min(90, 20 * round_num)
                    print(f"    ⚠️  {model} overloaded (round {round_num}), retrying in {wait}s...")
                    time.sleep(wait)
                elif "404" in err_str:
                    print(f"    ⚠️  {model} not available, skipping...")
                    continue
                else:
                    raise


def generate_image(prompt: str):
    """Generate an image — tries working model first, falls back to others.

    Returns the response object from Gemini.
    Never gives up on 503/429 — keeps cycling until one works.
    Sticks with whichever model succeeds for style consistency.
    """
    global _working_image_model
    client = _get_client()
    round_num = 0
    models = _get_model_order(GEMINI_IMAGE_MODELS, _working_image_model)

    while True:
        round_num += 1
        for model in models:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE", "TEXT"]
                    )
                )
                if _working_image_model != model:
                    print(f"    ✅ Using image model: {model}")
                _working_image_model = model
                return response
            except Exception as e:
                err_str = str(e)
                if "503" in err_str or "429" in err_str:
                    wait = min(90, 20 * round_num)
                    print(f"    ⚠️  {model} overloaded (round {round_num}), retrying in {wait}s...")
                    time.sleep(wait)
                elif "404" in err_str:
                    print(f"    ⚠️  {model} not available, skipping...")
                    continue
                else:
                    raise
