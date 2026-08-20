from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import edge_tts
import requests

HEDRA_BASE_URL = "https://api.hedra.com/v3"
HEDRA_AVATAR_MODEL = "hedra-avatar"


class HedraError(RuntimeError):
    pass


def _headers(api_key: str) -> dict[str, str]:
    # Hedra's v3 migration response explicitly states that existing X-API-Key
    # credentials continue to work unchanged on the /v3 endpoints.
    return {"X-API-Key": api_key}


def _raise_for_hedra(response: requests.Response, context: str) -> None:
    if response.ok:
        return
    detail = response.text[:1200]
    raise HedraError(f"{context} ({response.status_code}): {detail}")


def _upload_file(api_key: str, path: str) -> str:
    """Upload an input to Hedra v3 and return its short-lived URL handle."""
    source = Path(path)
    if not source.is_file():
        raise HedraError(f"No existe el archivo a subir: {source.name}")

    with source.open("rb") as handle:
        response = requests.post(
            f"{HEDRA_BASE_URL}/files",
            headers=_headers(api_key),
            files={"file": (source.name, handle)},
            timeout=180,
        )
    _raise_for_hedra(response, f"No se pudo subir {source.name} a Hedra v3")
    data = response.json()
    file_url = data.get("url")
    if not file_url:
        raise HedraError(f"Hedra v3 no devolvió URL para {source.name}: {data}")
    return file_url


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
        raise HedraError("No se pudo generar el audio para Hedra.")


def _job_error_message(data: dict) -> str:
    error = data.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(error or "Hedra devolvió un error al generar el avatar.")


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
    """Generate a talking tutor with Hedra Avatar through the Hedra v3 API.

    Flow:
    1. Generate the Spanish driving audio locally with Edge TTS.
    2. Upload tutor image and audio with POST /v3/files.
    3. Submit POST /v3/models/hedra-avatar.
    4. Poll GET /v3/jobs/{job_id}/status and download outputs[0].url.
    """
    key = (api_key or "").strip()
    if not key:
        raise HedraError("Falta HEDRA_API_KEY.")
    if not text.strip():
        raise HedraError("El texto del tutor está vacío.")
    if not os.path.isfile(image_path):
        raise HedraError("No se encontró la imagen del tutor.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    audio_path = str(output.with_suffix(".hedra_voice.mp3"))
    _generate_tts(text.strip(), voice_name, audio_path)

    image_url = _upload_file(key, image_path)
    audio_url = _upload_file(key, audio_path)

    payload = {
        "input": {
            "prompt": behavior_prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "start_image": {"source": "url", "url": image_url},
            "audio": {"source": "url", "url": audio_url},
        }
    }

    create = requests.post(
        f"{HEDRA_BASE_URL}/models/{HEDRA_AVATAR_MODEL}",
        headers={**_headers(key), "Content-Type": "application/json"},
        json=payload,
        timeout=90,
    )
    _raise_for_hedra(create, "Hedra v3 no pudo iniciar el avatar")
    job = create.json()
    job_id = job.get("job_id")
    if not job_id:
        raise HedraError(f"Hedra v3 no devolvió job_id: {job}")

    deadline = time.time() + timeout_seconds
    last_status = str(job.get("status") or "QUEUED")

    while time.time() < deadline:
        status_response = requests.get(
            f"{HEDRA_BASE_URL}/jobs/{job_id}/status",
            headers=_headers(key),
            timeout=60,
        )
        _raise_for_hedra(status_response, "No se pudo consultar el estado de Hedra v3")
        status_data = status_response.json()
        last_status = str(status_data.get("status") or "RUNNING").upper()

        if last_status == "COMPLETED":
            result_response = requests.get(
                f"{HEDRA_BASE_URL}/jobs/{job_id}",
                headers=_headers(key),
                timeout=60,
            )
            _raise_for_hedra(result_response, "No se pudo obtener el resultado de Hedra v3")
            result = result_response.json()
            outputs = result.get("outputs") or []
            video_url = None
            for item in outputs:
                if isinstance(item, dict) and item.get("status") == "COMPLETED" and item.get("url"):
                    video_url = item["url"]
                    break
            if not video_url:
                raise HedraError(f"Hedra terminó pero no devolvió un vídeo utilizable: {result}")

            download = requests.get(video_url, timeout=240)
            _raise_for_hedra(download, "No se pudo descargar el vídeo de Hedra")
            output.write_bytes(download.content)
            if not output.is_file() or output.stat().st_size <= 0:
                raise HedraError("Hedra devolvió un vídeo vacío.")
            return str(output)

        if last_status == "FAILED":
            result_response = requests.get(
                f"{HEDRA_BASE_URL}/jobs/{job_id}",
                headers=_headers(key),
                timeout=60,
            )
            if result_response.ok:
                raise HedraError(_job_error_message(result_response.json()))
            raise HedraError("Hedra v3 marcó la generación como fallida.")

        time.sleep(5)

    raise HedraError(f"Hedra sigue en estado '{last_status}' después de {timeout_seconds} s.")
