"""NVIDIA Cloud Speech-to-Text client.
Uses NVIDIA API Catalog ASR models (e.g. Whisper-large-v3 / Canary)
to transcribe audio files sent by users or frontend.
"""
import logging
import httpx
from typing import Optional, Dict, Any

log = logging.getLogger("bollbill.stt")

# NVIDIA API Catalog STT Endpoints
NVIDIA_STT_URL = "https://integrate.api.nvidia.com/v1/audio/transcriptions"

async def transcribe_audio(
    audio_bytes: bytes,
    filename: str,
    api_key: str,
    language: str = "hi",
    client: Optional[httpx.AsyncClient] = None
) -> Dict[str, Any]:
    """Transcribe audio bytes using NVIDIA Build STT API."""
    if not api_key:
        return {"error": "NVIDIA_API_KEY not configured", "text": ""}

    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    # Determine MIME type
    mime_type = "audio/wav"
    if filename.endswith(".mp3"):
        mime_type = "audio/mpeg"
    elif filename.endswith(".m4a"):
        mime_type = "audio/m4a"
    elif filename.endswith(".webm"):
        mime_type = "audio/webm"
    elif filename.endswith(".ogg"):
        mime_type = "audio/ogg"

    files = {
        "file": (filename, audio_bytes, mime_type)
    }
    data = {
        "model": "openai/whisper-large-v3",
        "language": language or "hi",
        "response_format": "json"
    }

    should_close = False
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)
        should_close = True

    try:
        resp = await client.post(NVIDIA_STT_URL, headers=headers, files=files, data=data)
        if resp.status_code == 200:
            res_data = resp.json()
            return {
                "ok": True,
                "text": res_data.get("text", "").strip(),
                "raw": res_data
            }
        else:
            log.error(f"NVIDIA STT API error {resp.status_code}: {resp.text}")
            return {
                "ok": False,
                "error": f"NVIDIA STT error: {resp.status_code}",
                "text": ""
            }
    except Exception as e:
        log.exception("NVIDIA STT request failed")
        return {
            "ok": False,
            "error": str(e),
            "text": ""
        }
    finally:
        if should_close:
            await client.aclose()
