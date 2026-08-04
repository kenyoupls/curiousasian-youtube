"""Gemini API helper — auto-fallback across models, gives up after max retries.

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

MAX_ROUNDS = 5  # Max retry rounds before giving up (each round tries all models)


def _get_client():
    return genai.Client(api_key=GEMINI_API_KEY)


def _get_model_order(models: list, working_model: str = None) -> list:
    """Put the known working model first, then the rest."""
    if working_model and working_model in models:
        return [working_model] + [m for m in models if m != working_model]
    return models


def generate_text(prompt: str) -> str:
    """Generate text — tries working model first, falls back to others.

    Retries up to MAX_ROUNDS times, then raises.
    """
    global _working_text_model
    client = _get_client()
    models = _get_model_order(GEMINI_TEXT_MODELS, _working_text_model)

    for round_num in range(1, MAX_ROUNDS + 1):
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
                    wait = min(30, 10 * round_num)
                    print(f"    ⚠️  {model} overloaded (round {round_num}/{MAX_ROUNDS}), retrying in {wait}s...")
                    time.sleep(wait)
                elif "404" in err_str:
                    print(f"    ⚠️  {model} not available, skipping...")
                    continue
                else:
                    raise

    raise RuntimeError(f"All Gemini text models failed after {MAX_ROUNDS} rounds")


def generate_image(prompt: str):
    """Generate an image — tries working model first, falls back to others.

    Returns the response object from Gemini.
    Retries up to MAX_ROUNDS times, then raises.
    """
    global _working_image_model
    client = _get_client()
    models = _get_model_order(GEMINI_IMAGE_MODELS, _working_image_model)

    for round_num in range(1, MAX_ROUNDS + 1):
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
                    wait = min(30, 10 * round_num)
                    print(f"    ⚠️  {model} overloaded (round {round_num}/{MAX_ROUNDS}), retrying in {wait}s...")
                    time.sleep(wait)
                elif "404" in err_str:
                    print(f"    ⚠️  {model} not available, skipping...")
                    continue
                else:
                    raise

    raise RuntimeError(f"All Gemini image models failed after {MAX_ROUNDS} rounds")
