from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import edge_tts
import requests
from moviepy import AudioFileClip

HEDRA_BASE_URL = "https://api.hedra.com/web-app/public"
HEDRA_AVATAR_MODEL_ID = "26f0fc66-152b-40ab-abed-76c43df99bc8"


class HedraError(RuntimeError):
    pass


def _headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def _raise_for_hedra(response: requests.Response, context: str) -> None:
    if response.ok:
        return
    detail = response.text[:800]
    raise HedraError(f"{context} ({response.status_code}): {detail}")


def _create_and_upload_asset(api_key: str, path: str, asset_type: str) -> str:
    source = Path(path)
    create = requests.post(
        f"{HEDRA_BASE_URL}/assets",
        headers={**_headers(api_key), "Content-Type": "application/json"},
        json={"name": source.name, "type": asset_type},
        timeout=45,
    )
    _raise_for_hedra(create, f"No se pudo crear el asset {asset_type}")
    asset_id = create.json()["id"]

    with source.open("rb") as handle:
        upload = requests.post(
            f"{HEDRA_BASE_URL}/assets/{asset_id}/upload",
            headers=_headers(api_key),
            files={"file": (source.name, handle)},
            timeout=120,
        )
    _raise_for_hedra(upload, f"No se pudo subir el asset {asset_type}")
    return asset_id


async def _tts_async(text: str, voice_name: str, output_path: str) -> None:
    communicator = edge_tts.Communicate(
        text=text,
        voice=voice_name,
        rate="+0%",
        volume="+0%",
    )
    await communicator.save(output_path)


def _generate_tts(text: str, voice_name: str, output_path: str) -> float:
    asyncio.run(_tts_async(text, voice_name, output_path))
    if not os.path.isfile(output_path) or os.path.getsize(output_path) <= 0:
        raise HedraError("No se pudo generar el audio para Hedra.")
    audio = AudioFileClip(output_path)
    try:
        return float(audio.duration)
    finally:
        audio.close()


def generate_talking_avatar(
    *,
    api_key: str,
    image_path: str,
    text: str,
    voice_name: str,
    output_path: str,
    behavior_prompt: str = "Presentador educativo, natural y seguro; habla a cámara con pequeños gestos y una expresión cercana.",
    resolution: str = "540p",
    aspect_ratio: str = "9:16",
    timeout_seconds: int = 720,
) -> str:
    """Generate a short talking-avatar clip using Hedra Avatar.

    This is intentionally a separate test step from the full H2D Reel renderer so
    we can validate quality/credits before using the avatar throughout a Reel.
    """
    if not api_key.strip():
        raise HedraError("Falta HEDRA_API_KEY.")
    if not text.strip():
        raise HedraError("El texto del tutor está vacío.")
    if not os.path.isfile(image_path):
        raise HedraError("No se encontró la imagen del tutor.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    audio_path = str(output.with_suffix(".hedra_voice.mp3"))
    duration_seconds = _generate_tts(text.strip(), voice_name, audio_path)

    image_asset_id = _create_and_upload_asset(api_key, image_path, "image")
    audio_asset_id = _create_and_upload_asset(api_key, audio_path, "audio")

    payload = {
        "type": "video",
        "ai_model_id": HEDRA_AVATAR_MODEL_ID,
        "start_keyframe_id": image_asset_id,
        "audio_id": audio_asset_id,
        "generated_video_inputs": {
            "text_prompt": behavior_prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "duration_ms": max(1000, int(duration_seconds * 1000)),
        },
    }
    create = requests.post(
        f"{HEDRA_BASE_URL}/generations",
        headers={**_headers(api_key), "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    _raise_for_hedra(create, "Hedra no pudo iniciar el avatar")
    generation = create.json()
    generation_id = generation.get("id") or generation.get("generation_id")
    if not generation_id:
        raise HedraError(f"Hedra no devolvió generation_id: {generation}")

    deadline = time.time() + timeout_seconds
    last_status = "queued"
    while time.time() < deadline:
        status_response = requests.get(
            f"{HEDRA_BASE_URL}/generations/{generation_id}/status",
            headers=_headers(api_key),
            timeout=45,
        )
        _raise_for_hedra(status_response, "No se pudo consultar el estado de Hedra")
        status_data = status_response.json()
        last_status = status_data.get("status", "processing")

        if last_status == "complete":
            video_url = (
                status_data.get("download_url")
                or status_data.get("url")
                or status_data.get("streaming_url")
            )
            if not video_url:
                raise HedraError(f"Hedra terminó pero no devolvió URL del vídeo: {status_data}")
            download = requests.get(video_url, timeout=180)
            _raise_for_hedra(download, "No se pudo descargar el vídeo de Hedra")
            output.write_bytes(download.content)
            if output.stat().st_size <= 0:
                raise HedraError("Hedra devolvió un vídeo vacío.")
            return str(output)

        if last_status == "error":
            raise HedraError(status_data.get("error_message") or "Hedra devolvió un error al generar el avatar.")

        time.sleep(5)

    raise HedraError(f"Hedra sigue en estado '{last_status}' después de {timeout_seconds} s.")
