from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Iterable

import edge_tts
from moviepy import AudioFileClip, ImageClip, concatenate_videoclips
from PIL import Image, ImageFilter, ImageOps


FRAME_SIZE = (1080, 1920)
FPS = 30


def _prepare_vertical_frame(source: str, destination: str) -> str:
    """Create a clean 9:16 frame while preserving the full uploaded image."""
    with Image.open(source) as raw:
        image = raw.convert("RGB")

    background = ImageOps.fit(image, FRAME_SIZE, method=Image.Resampling.LANCZOS)
    background = background.filter(ImageFilter.GaussianBlur(radius=26))

    dark = Image.new("RGB", FRAME_SIZE, (5, 16, 27))
    background = Image.blend(background, dark, 0.42)

    foreground = ImageOps.contain(
        image,
        (960, 1740),
        method=Image.Resampling.LANCZOS,
    )
    x = (FRAME_SIZE[0] - foreground.width) // 2
    y = (FRAME_SIZE[1] - foreground.height) // 2
    background.paste(foreground, (x, y))
    background.save(destination, quality=95)
    return destination


async def _save_edge_tts(text: str, voice_name: str, output_path: str) -> None:
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice_name,
        rate="+0%",
        volume="+0%",
    )
    await communicate.save(output_path)


def _generate_voice(text: str, voice_name: str, output_path: str) -> None:
    """Generate Spanish narration without importing the full MPT voice stack."""
    asyncio.run(_save_edge_tts(text, voice_name, output_path))
    if not os.path.isfile(output_path) or os.path.getsize(output_path) <= 0:
        raise RuntimeError("No se pudo generar la voz del Reel.")


def render_reel(
    *,
    image_paths: Iterable[str],
    spoken_text: str,
    voice_name: str,
    requested_duration: int,
    output_path: str,
) -> str:
    """Render a first H2D 9:16 MP4 using exact uploaded assets and Spanish TTS."""
    sources = [str(Path(path)) for path in image_paths if path]
    if not sources:
        raise ValueError("At least one image is required to render the reel.")
    if not spoken_text.strip():
        raise ValueError("The spoken text cannot be empty.")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="h2d_reel_") as workdir:
        audio_path = os.path.join(workdir, "voice.mp3")
        _generate_voice(spoken_text.strip(), voice_name, audio_path)

        prepared = []
        for index, source in enumerate(sources):
            frame_path = os.path.join(workdir, f"frame_{index:02d}.jpg")
            prepared.append(_prepare_vertical_frame(source, frame_path))

        audio = AudioFileClip(audio_path)
        target_duration = max(float(requested_duration), float(audio.duration) + 0.15)
        clip_duration = target_duration / len(prepared)

        clips = [ImageClip(frame).with_duration(clip_duration) for frame in prepared]
        video = concatenate_videoclips(clips, method="compose").with_audio(audio)

        try:
            video.write_videofile(
                output_path,
                fps=FPS,
                codec="libx264",
                audio_codec="aac",
                audio_bitrate="192k",
                threads=2,
                logger=None,
            )
        finally:
            video.close()
            audio.close()
            for clip in clips:
                clip.close()

    if not os.path.isfile(output_path) or os.path.getsize(output_path) <= 0:
        raise RuntimeError("El render terminó sin producir un MP4 válido.")
    return output_path
