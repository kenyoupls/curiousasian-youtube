"""Gemini API — model fallback with sticky selection + key rotation + exponential backoff."""

import time
import random
from google import genai
from google.genai import types
from src.config import GEMINI_API_KEYS, GEMINI_TEXT_MODELS, GEMINI_IMAGE_MODELS

_text_model = None
_image_model = None
_key_index = 0
_last_image_request = 0.0
IMAGE_REQUEST_DELAY = 7  # seconds between image requests to stay under 10 RPM


def _log_key_info():
    """Print diagnostic info about keys (once)."""
    global _logged
    if not hasattr(_log_key_info, '_done'):
        _log_key_info._done = True
        n = len(GEMINI_API_KEYS)
        prefixes = [k[:6] + "..." for k in GEMINI_API_KEYS] if GEMINI_API_KEYS else ["(none)"]
        print(f"    🔑 {n} API key(s): {', '.join(prefixes)}")
        print(f"    📦 google-genai version: {genai.__version__ if hasattr(genai, '__version__') else 'unknown'}")


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
    _log_key_info()
    last_err = None

    for rnd in range(1, 4):
        for model in _ordered(GEMINI_TEXT_MODELS, _text_model):
            keys_tried = 0
            while keys_tried < max(len(GEMINI_API_KEYS), 1):
                client = _next_client()
                keys_tried += 1
                try:
                    result = client.models.generate_content(model=model, contents=prompt).text
                    if result is None:
                        break
                    _text_model = model
                    if rnd == 1:
                        print(f"    ✅ Text: {model}")
                    return result
                except Exception as e:
                    err = str(e)
                    last_err = err
                    if _is_auth_error(err):
                        key_prefix = GEMINI_API_KEYS[(_key_index - 1) % len(GEMINI_API_KEYS)][:8] if GEMINI_API_KEYS else "?"
                        print(f"    ⚠️  Key {key_prefix}... auth failed on {model}, trying next...")
                        continue
                    elif _is_overloaded(err):
                        wait = (2 ** rnd) + random.uniform(0, 1)
                        print(f"    ⚠️  {model} overloaded [{rnd}/3], waiting {wait:.0f}s...")
                        time.sleep(wait)
                        break
                    elif "404" in err:
                        break
                    else:
                        print(f"    ❌ {model} unexpected error: {err[:200]}")
                        raise

    raise RuntimeError(f"All Gemini text models failed: {last_err[:200] if last_err else 'unknown'}")


def generate_image(prompt):
    """Try image models with key rotation, 4 rounds with exponential backoff."""
    global _image_model, _last_image_request
    _log_key_info()
    last_err = None

    # Rate limit: wait between image requests to stay under ~10 RPM
    wait = IMAGE_REQUEST_DELAY - (time.time() - _last_image_request)
    if wait > 0:
        print(f"    ⏳ Rate limit: waiting {wait:.0f}s...")
        time.sleep(wait)
    _last_image_request = time.time()

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
                        key_prefix = GEMINI_API_KEYS[(_key_index - 1) % len(GEMINI_API_KEYS)][:8] if GEMINI_API_KEYS else "?"
                        print(f"    ⚠️  Key {key_prefix}... auth failed on {model}, trying next...")
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
