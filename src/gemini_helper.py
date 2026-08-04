"""Gemini API — model fallback with sticky selection + exponential backoff."""

import time
import random
from google import genai
from google.genai import types
from src.config import GEMINI_API_KEY, GEMINI_TEXT_MODELS, GEMINI_IMAGE_MODELS

_text_model = None
_image_model = None


def _client():
    return genai.Client(api_key=GEMINI_API_KEY)


def _ordered(models, sticky):
    if sticky and sticky in models:
        return [sticky] + [m for m in models if m != sticky]
    return models


def _is_overloaded(err_str):
    return any(code in err_str for code in ["503", "429", "RESOURCE_EXHAUSTED", "overloaded"])


def generate_text(prompt):
    """Try each text model, 3 rounds with exponential backoff."""
    global _text_model
    client = _client()

    for rnd in range(1, 4):
        for model in _ordered(GEMINI_TEXT_MODELS, _text_model):
            try:
                result = client.models.generate_content(model=model, contents=prompt).text
                if result is None:
                    continue
                _text_model = model
                if rnd == 1:
                    print(f"    ✅ Text: {model}")
                return result
            except Exception as e:
                err = str(e)
                if _is_overloaded(err):
                    wait = (2 ** rnd) + random.uniform(0, 1)
                    print(f"    ⚠️  {model} overloaded [{rnd}/3], waiting {wait:.0f}s...")
                    time.sleep(wait)
                elif "404" in err:
                    continue
                else:
                    raise

    raise RuntimeError("All Gemini text models failed")


def generate_image(prompt):
    """Try each image model, 4 rounds with exponential backoff."""
    global _image_model
    client = _client()

    for rnd in range(1, 5):
        for model in _ordered(GEMINI_IMAGE_MODELS, _image_model):
            try:
                # imagen-3 uses a different API than gemini image models
                if model.startswith("imagen"):
                    resp = client.models.generate_images(
                        model=model,
                        prompt=prompt,
                        config=types.GenerateImagesConfig(
                            number_of_images=1,
                        )
                    )
                    _image_model = model
                    return resp
                else:
                    resp = client.models.generate_content(
                        model=model, contents=prompt,
                        config=types.GenerateContentConfig(
                            response_modalities=["IMAGE", "TEXT"]
                        )
                    )
                    _image_model = model
                    return resp
            except Exception as e:
                err = str(e)
                if _is_overloaded(err):
                    wait = (2 ** rnd) + random.uniform(0, 1)
                    print(f"    ⚠️  {model} overloaded [{rnd}/4], waiting {wait:.0f}s...")
                    time.sleep(wait)
                elif "404" in err:
                    continue
                else:
                    print(f"    ⚠️  {model} error: {err[:100]}")
                    continue

    raise RuntimeError("All Gemini image models failed")
