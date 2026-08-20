from __future__ import annotations

import asyncio
import mimetypes
import os
import time
from pathlib import Path

import edge_tts
import requests

SYNC_BASE_URL = "https://api.sync.so/v2"


class SyncError(RuntimeError):
    pass


def _headers(api_key: str) -> dict[str, str]:
    return {"x-api-key": api_key}


def _raise_for_sync(response: requests.Response, context: str) -> None:
    if response.ok:
        return
    detail = response.text[:1400]
    raise SyncError(f"{context} ({response.status_code}): {detail}")


async def _tts_async(text: str, voice_name: str, output_path: str) -> None:
    communicator = edge_tts.Communicate(
        text=text,
        voice=voice_name,
        rate="+0%",
        volume="+0%",
    )
    await communicator.save(output_path)


def _generate_tts(text: str, voice_name: str, output_path: str) -> None:
    asyncio.run(_tts_async(text, voice_name, output_path))
    if not os.path.isfile(output_path) or os.path.getsize(output_path) <= 0:
        raise SyncError("No se pudo generar el audio para Sync Labs.")


def generate_talking_avatar(
    *,
    api_key: str,
    image_path: str,
    text: str,
    voice_name: str,
    output_path: str,
    timeout_seconds: int = 720,
) -> str:
    """Create a short talking tutor clip with Sync Labs sync-3.

    Uses the documented multipart form of POST /v2/generate so local image/audio
    files go directly to Sync Labs. This avoids the separate asset-upload flow and
    is ideal for our short free-trial tests (files must remain under 20 MB each).
    """
    key = api_key.strip()
    if not key:
        raise SyncError("Falta SYNC_API_KEY.")
    if not text.strip():
        raise SyncError("El texto del tutor está vacío.")

    image = Path(image_path)
    if not image.is_file():
        raise SyncError("No se encontró la imagen del tutor.")
    if image.stat().st_size >= 20 * 1024 * 1024:
        raise SyncError("La imagen supera 20 MB. Usa una imagen más ligera para la prueba de Sync Labs.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    audio_path = output.with_suffix(".sync_voice.mp3")
    _generate_tts(text.strip(), voice_name, str(audio_path))
    if audio_path.stat().st_size >= 20 * 1024 * 1024:
        raise SyncError("El audio supera 20 MB; acorta el hook.")

    image_type = mimetypes.guess_type(image.name)[0] or "image/png"
    audio_type = mimetypes.guess_type(audio_path.name)[0] or "audio/mpeg"

    # Sync Labs documents direct local-file upload on the same generation endpoint:
    # multipart fields named image/audio plus the model field.
    with image.open("rb") as image_handle, audio_path.open("rb") as audio_handle:
        create = requests.post(
            f"{SYNC_BASE_URL}/generate",
            headers=_headers(key),
            data={"model": "sync-3"},
            files={
                "image": (image.name, image_handle, image_type),
                "audio": (audio_path.name, audio_handle, audio_type),
            },
            timeout=180,
        )

    _raise_for_sync(create, "Sync Labs no pudo iniciar el tutor")
    generation = create.json()
    generation_id = generation.get("id")
    if not generation_id:
        raise SyncError(f"Sync Labs no devolvió generation id: {generation}")

    deadline = time.time() + timeout_seconds
    last_status = str(generation.get("status", "PENDING")).upper()

    while time.time() < deadline:
        status_response = requests.get(
            f"{SYNC_BASE_URL}/generate/{generation_id}",
            headers=_headers(key),
            params={"wait": "true"},
            timeout=75,
        )
        _raise_for_sync(status_response, "No se pudo consultar el estado de Sync Labs")
        status_data = status_response.json()
        last_status = str(status_data.get("status", "PROCESSING")).upper()

        if last_status == "COMPLETED":
            video_url = status_data.get("outputUrl")
            if not video_url:
                raise SyncError(f"Sync Labs terminó pero no devolvió outputUrl: {status_data}")
            download = requests.get(video_url, timeout=180)
            _raise_for_sync(download, "No se pudo descargar el vídeo de Sync Labs")
            output.write_bytes(download.content)
            if not output.is_file() or output.stat().st_size <= 0:
                raise SyncError("Sync Labs devolvió un vídeo vacío.")
            return str(output)

        if last_status in {"FAILED", "REJECTED"}:
            error = status_data.get("error") or status_data.get("errorCode") or status_data
            raise SyncError(f"Sync Labs devolvió {last_status}: {error}")

        time.sleep(3)

    raise SyncError(f"Sync Labs sigue en estado '{last_status}' después de {timeout_seconds} s.")
