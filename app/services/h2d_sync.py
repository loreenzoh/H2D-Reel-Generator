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
    detail = response.text[:1000]
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


def _upload_asset(api_key: str, path: str, asset_type: str) -> str:
    source = Path(path)
    if not source.is_file():
        raise SyncError(f"No existe el archivo {source.name}.")

    content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    presign = requests.post(
        f"{SYNC_BASE_URL}/assets/upload",
        headers={**_headers(api_key), "Content-Type": "application/json"},
        json={
            "fileName": source.name,
            "contentType": content_type,
            "size": source.stat().st_size,
        },
        timeout=45,
    )
    _raise_for_sync(presign, f"Sync Labs no pudo preparar la subida de {source.name}")
    upload_data = presign.json()
    upload_url = upload_data.get("uploadUrl")
    public_url = upload_data.get("url")
    if not upload_url or not public_url:
        raise SyncError(f"Sync Labs no devolvió URL de subida para {source.name}.")

    with source.open("rb") as handle:
        put = requests.put(
            upload_url,
            headers={"Content-Type": content_type},
            data=handle,
            timeout=180,
        )
    _raise_for_sync(put, f"No se pudo subir {source.name} a Sync Labs")

    register = requests.post(
        f"{SYNC_BASE_URL}/assets",
        headers={**_headers(api_key), "Content-Type": "application/json"},
        json={
            "url": public_url,
            "type": asset_type,
            "name": source.name,
        },
        timeout=60,
    )
    _raise_for_sync(register, f"No se pudo registrar {source.name} en Sync Labs")
    asset_id = register.json().get("id")
    if not asset_id:
        raise SyncError(f"Sync Labs no devolvió asset id para {source.name}.")
    return asset_id


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

    Free accounts currently allow one sync-3 generation per month, up to 15 seconds.
    We intentionally generate only the hook so the first quality test stays short.
    """
    if not api_key.strip():
        raise SyncError("Falta SYNC_API_KEY.")
    if not text.strip():
        raise SyncError("El texto del tutor está vacío.")
    if not os.path.isfile(image_path):
        raise SyncError("No se encontró la imagen del tutor.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    audio_path = str(output.with_suffix(".sync_voice.mp3"))
    _generate_tts(text.strip(), voice_name, audio_path)

    image_asset_id = _upload_asset(api_key, image_path, "IMAGE")
    audio_asset_id = _upload_asset(api_key, audio_path, "AUDIO")

    payload = {
        "model": "sync-3",
        "input": [
            {"type": "image", "assetId": image_asset_id},
            {"type": "audio", "assetId": audio_asset_id},
        ],
    }
    create = requests.post(
        f"{SYNC_BASE_URL}/generate",
        headers={**_headers(api_key), "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    _raise_for_sync(create, "Sync Labs no pudo iniciar el tutor")
    generation = create.json()
    generation_id = generation.get("id")
    if not generation_id:
        raise SyncError(f"Sync Labs no devolvió generation id: {generation}")

    deadline = time.time() + timeout_seconds
    last_status = generation.get("status", "PENDING")
    while time.time() < deadline:
        status_response = requests.get(
            f"{SYNC_BASE_URL}/generate/{generation_id}",
            headers=_headers(api_key),
            timeout=45,
        )
        _raise_for_sync(status_response, "No se pudo consultar el estado de Sync Labs")
        status_data = status_response.json()
        last_status = status_data.get("status", "PROCESSING")

        if last_status == "COMPLETED":
            video_url = status_data.get("outputUrl")
            if not video_url:
                raise SyncError(f"Sync Labs terminó pero no devolvió outputUrl: {status_data}")
            download = requests.get(video_url, timeout=180)
            _raise_for_sync(download, "No se pudo descargar el vídeo de Sync Labs")
            output.write_bytes(download.content)
            if output.stat().st_size <= 0:
                raise SyncError("Sync Labs devolvió un vídeo vacío.")
            return str(output)

        if last_status in {"FAILED", "REJECTED"}:
            error = status_data.get("error") or status_data.get("errorCode") or "Error desconocido"
            raise SyncError(f"Sync Labs devolvió {last_status}: {error}")

        time.sleep(5)

    raise SyncError(f"Sync Labs sigue en estado '{last_status}' después de {timeout_seconds} s.")
