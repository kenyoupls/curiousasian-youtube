"""Gemini API — model fallback with sticky selection."""

import time
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


def generate_text(prompt):
    """Try each text model, 3 rounds max. Returns string."""
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
                if "503" in err or "429" in err:
                    print(f"    ⚠️  {model} overloaded [{rnd}/3]")
                    time.sleep(5)
                elif "404" in err:
                    continue
                else:
                    raise

    raise RuntimeError("All Gemini text models failed")


def generate_image(prompt):
    """Try each image model, 3 rounds max. Returns response object."""
    global _image_model
    client = _client()

    for rnd in range(1, 4):
        for model in _ordered(GEMINI_IMAGE_MODELS, _image_model):
            try:
                resp = client.models.generate_content(
                    model=model, contents=prompt,
                    config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"])
                )
                _image_model = model
                return resp
            except Exception as e:
                err = str(e)
                if "503" in err or "429" in err:
                    print(f"    ⚠️  {model} overloaded [{rnd}/3]")
                    time.sleep(5)
                elif "404" in err:
                    continue
                else:
                    raise

    raise RuntimeError("All Gemini image models failed")
