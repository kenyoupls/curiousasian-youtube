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
IMAGE_REQUEST_DELAY = 15  # seconds between image requests — generous spacing to avoid 429


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


def generate_speech(text, voice_name="Kore", temperature=1.0):
    """Generate speech audio via Gemini TTS (gemini-2.5-flash-preview-tts).

    Returns raw PCM audio bytes (24kHz, mono, 16-bit little-endian).
    Uses dedicated GEMINI_VOICE_KEY (separate quota from text calls).
    Falls back to shared keys if dedicated key not set.

    Args:
        text: Text to speak. Can include emotion cues like [excitedly], [whispers], etc.
        voice_name: One of Gemini's 30 prebuilt voices (default: Kore — warm male).
        temperature: Controls expressiveness (0.0-2.0, default 1.0).
    """
    from src.config import GEMINI_VOICE_KEY
    _log_key_info()
    last_err = None

    tts_model = "gemini-2.5-flash-preview-tts"

    # Use dedicated voice key if available, otherwise fall back to shared keys
    if GEMINI_VOICE_KEY:
        tts_keys = [GEMINI_VOICE_KEY]
    else:
        tts_keys = GEMINI_API_KEYS

    for rnd in range(1, 5):  # 4 rounds with backoff
        keys_tried = 0
        while keys_tried < max(len(tts_keys), 1):
            client = genai.Client(api_key=tts_keys[keys_tried % len(tts_keys)] if tts_keys else "")
            keys_tried += 1
            try:
                resp = client.models.generate_content(
                    model=tts_model,
                    contents=text,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=voice_name,
                                )
                            )
                        ),
                        temperature=temperature,
                    )
                )

                # Extract audio data from response
                if (resp.candidates and resp.candidates[0].content
                        and resp.candidates[0].content.parts):
                    part = resp.candidates[0].content.parts[0]
                    if hasattr(part, 'inline_data') and part.inline_data:
                        if rnd == 1:
                            print(f"    ✅ TTS: {tts_model} (voice={voice_name})")
                        return part.inline_data.data
                raise RuntimeError("No audio data in TTS response")

            except Exception as e:
                err = str(e)
                last_err = err
                if _is_auth_error(err):
                    key_prefix = tts_keys[(keys_tried - 1) % len(tts_keys)][:8] if tts_keys else "?"
                    print(f"    ⚠️  Key {key_prefix}... auth failed on TTS, trying next...")
                    continue
                elif _is_overloaded(err):
                    wait = 60 + random.uniform(0, 5)  # full 60s cooldown on 429
                    print(f"    ⚠️  TTS rate limited [{rnd}/4], waiting {wait:.0f}s...")
                    time.sleep(wait)
                    break
                elif "404" in err:
                    break
                else:
                    print(f"    ⚠️  TTS error: {err[:200]}")
                    break

    raise RuntimeError(f"Gemini TTS failed: {last_err[:200] if last_err else 'unknown'}")


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

    for rnd in range(1, 7):  # 6 rounds — more patience
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
                    _last_image_request = time.time()  # reset timer on success
                    return resp
                except Exception as e:
                    err = str(e)
                    last_err = err
                    if _is_auth_error(err):
                        key_prefix = GEMINI_API_KEYS[(_key_index - 1) % len(GEMINI_API_KEYS)][:8] if GEMINI_API_KEYS else "?"
                        print(f"    ⚠️  Key {key_prefix}... auth failed on {model}, trying next...")
                        continue
                    elif _is_overloaded(err):
                        # Aggressive backoff: 30s, 60s, 90s, 120s, 150s, 180s
                        wait = 30 * rnd + random.uniform(0, 5)
                        print(f"    ⚠️  {model} rate limited [{rnd}/6], waiting {wait:.0f}s...")
                        time.sleep(wait)
                        break
                    elif "404" in err:
                        break
                    else:
                        print(f"    ⚠️  {model} error: {err[:100]}")
                        break

    raise RuntimeError(f"All Gemini image models failed: {last_err[:200] if last_err else 'unknown'}")
