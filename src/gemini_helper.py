"""Gemini API — model fallback with sticky selection + key rotation + exponential backoff."""

import time
import random
from google import genai
from google.genai import types
from src.config import GEMINI_API_KEYS, GEMINI_TEXT_MODELS, GEMINI_IMAGE_MODELS

_text_model = None
_image_model = None
_key_index = 0


def _next_client():
    """Rotate to the next API key and return a new client."""
    global _key_index
    if not GEMINI_API_KEYS:
        return genai.Client(api_key="")
    key = GEMINI_API_KEYS[_key_index % len(GEMINI_API_KEYS)]
    _key_index += 1
    return genai.Client(api_key=key)


def _ordered(models, sticky):
    if sticky and sticky in models:
        return [sticky] + [m for m in models if m != sticky]
    return models


def _is_overloaded(err_str):
    return any(code in err_str for code in ["503", "429", "RESOURCE_EXHAUSTED", "overloaded"])


def _is_auth_error(err_str):
    return any(code in err_str for code in ["401", "UNAUTHENTICATED", "ACCESS_TOKEN_TYPE_UNSUPPORTED"])


def generate_text(prompt):
    """Try each text model with key rotation, 3 rounds with exponential backoff."""
    global _text_model
    last_err = None

    for rnd in range(1, 4):
        for model in _ordered(GEMINI_TEXT_MODELS, _text_model):
            # Try each available key for this model
            keys_tried = 0
            while keys_tried < max(len(GEMINI_API_KEYS), 1):
                client = _next_client()
                keys_tried += 1
                try:
                    result = client.models.generate_content(model=model, contents=prompt).text
                    if result is None:
                        break  # try next model
                    _text_model = model
                    if rnd == 1:
                        print(f"    ✅ Text: {model}")
                    return result
                except Exception as e:
                    err = str(e)
                    last_err = err
                    if _is_auth_error(err):
                        print(f"    ⚠️  Key auth failed, trying next key...")
                        continue  # try next key
                    elif _is_overloaded(err):
                        wait = (2 ** rnd) + random.uniform(0, 1)
                        print(f"    ⚠️  {model} overloaded [{rnd}/3], waiting {wait:.0f}s...")
                        time.sleep(wait)
                        break  # try next model after wait
                    elif "404" in err:
                        break  # model not found, try next model
                    else:
                        raise

    raise RuntimeError(f"All Gemini text models failed: {last_err[:200] if last_err else 'unknown'}")


def generate_image(prompt):
    """Try image models with key rotation, 4 rounds with exponential backoff."""
    global _image_model
    last_err = None

    for rnd in range(1, 5):
        for model in _ordered(GEMINI_IMAGE_MODELS, _image_model):
            keys_tried = 0
            while keys_tried < max(len(GEMINI_API_KEYS), 1):
                client = _next_client()
                keys_tried += 1
                try:
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
                    last_err = err
                    if _is_auth_error(err):
                        print(f"    ⚠️  Key auth failed, trying next key...")
                        continue
                    elif _is_overloaded(err):
                        wait = (2 ** rnd) + random.uniform(0, 1)
                        print(f"    ⚠️  {model} overloaded [{rnd}/4], waiting {wait:.0f}s...")
                        time.sleep(wait)
                        break
                    elif "404" in err:
                        break
                    else:
                        print(f"    ⚠️  {model} error: {err[:100]}")
                        break

    raise RuntimeError(f"All Gemini image models failed: {last_err[:200] if last_err else 'unknown'}")
