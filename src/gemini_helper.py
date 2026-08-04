"""Gemini API helper — fast fallback across models."""

import time
from google import genai
from google.genai import types
from src.config import (
    GEMINI_API_KEY, GEMINI_TEXT_MODELS, GEMINI_IMAGE_MODELS
)

_working_text_model = None
_working_image_model = None
MAX_ROUNDS = 2  # Fail fast — don't waste time on broken models


def _get_client():
    return genai.Client(api_key=GEMINI_API_KEY)


def generate_text(prompt: str) -> str:
    global _working_text_model
    client = _get_client()
    models = GEMINI_TEXT_MODELS
    if _working_text_model and _working_text_model in models:
        models = [_working_text_model] + [m for m in models if m != _working_text_model]

    for round_num in range(1, MAX_ROUNDS + 1):
        for model in models:
            try:
                response = client.models.generate_content(model=model, contents=prompt)
                result = response.text
                if result is None:
                    continue
                _working_text_model = model
                if round_num == 1:
                    print(f"    ✅ Text model: {model}")
                return result
            except Exception as e:
                err_str = str(e)
                if "503" in err_str or "429" in err_str:
                    print(f"    ⚠️  {model} overloaded, trying next...")
                    time.sleep(3)
                elif "404" in err_str:
                    continue
                else:
                    raise

    raise RuntimeError(f"All Gemini text models failed after {MAX_ROUNDS} rounds")


def generate_image(prompt: str):
    global _working_image_model
    client = _get_client()
    models = GEMINI_IMAGE_MODELS
    if _working_image_model and _working_image_model in models:
        models = [_working_image_model] + [m for m in models if m != _working_image_model]

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
                _working_image_model = model
                return response
            except Exception as e:
                err_str = str(e)
                if "503" in err_str or "429" in err_str:
                    print(f"    ⚠️  {model} overloaded, trying next...")
                    time.sleep(3)
                elif "404" in err_str:
                    continue
                else:
                    raise

    raise RuntimeError(f"All Gemini image models failed after {MAX_ROUNDS} rounds")
