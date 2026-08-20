from __future__ import annotations

import os
import urllib.request
from pathlib import Path

MODEL_ID = "fal-ai/sync-lipsync/v3/image-to-video"


def generate_talking_avatar(
    *,
    image_path: str,
    audio_path: str,
    output_path: str,
    fal_key: str | None = None,
) -> str:
    """Animate a single tutor image with the exact supplied audio using fal Sync 3.

    The key is read from the explicit argument first and then from FAL_KEY.
    It is never persisted by this service.
    """
    key = (fal_key or os.getenv("FAL_KEY", "")).strip()
    if not key:
        raise RuntimeError("Falta FAL_KEY para generar el tutor parlante.")

    image = Path(image_path)
    audio = Path(audio_path)
    if not image.is_file():
        raise ValueError("No existe la imagen del tutor.")
    if not audio.is_file():
        raise ValueError("No existe el audio del tutor.")

    # Keep credentials server-side. fal-client reads FAL_KEY for upload/subscribe.
    previous_key = os.environ.get("FAL_KEY")
    os.environ["FAL_KEY"] = key
    try:
        import fal_client

        image_url = fal_client.upload_file(str(image))
        audio_url = fal_client.upload_file(str(audio))
        result = fal_client.subscribe(
            MODEL_ID,
            arguments={
                "image_url": image_url,
                "audio_url": audio_url,
            },
        )
        video_url = ((result or {}).get("video") or {}).get("url")
        if not video_url:
            raise RuntimeError("fal no devolvió un vídeo del tutor.")

        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(video_url, destination)
        if not destination.is_file() or destination.stat().st_size <= 0:
            raise RuntimeError("El vídeo del tutor se descargó vacío.")
        return str(destination)
    finally:
        if previous_key is None:
            os.environ.pop("FAL_KEY", None)
        else:
            os.environ["FAL_KEY"] = previous_key
