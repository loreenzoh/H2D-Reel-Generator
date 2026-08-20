from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Iterable

import edge_tts
from moviepy import AudioFileClip, ImageClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

FRAME_SIZE = (1080, 1920)
FPS = 30
ROOT_DIR = Path(__file__).resolve().parents[2]
FONT_BOLD = ROOT_DIR / "resource" / "fonts" / "BeVietnamPro-Bold.ttf"
FONT_MEDIUM = ROOT_DIR / "resource" / "fonts" / "BeVietnamPro-Medium.ttf"

NAVY = (5, 16, 29)
NAVY_2 = (8, 32, 52)
BLUE = (57, 177, 255)
WHITE = (248, 251, 255)
MUTED = (183, 205, 224)
GREEN = (64, 211, 151)
CARD = (10, 34, 55)
CARD_2 = (14, 45, 71)


def _font(path: Path, size: int):
    try:
        return ImageFont.truetype(str(path), size=size)
    except OSError:
        return ImageFont.load_default()


def _gradient_background() -> Image.Image:
    width, height = FRAME_SIZE
    image = Image.new("RGB", FRAME_SIZE, NAVY)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(
            int(NAVY[i] * (1 - ratio) + NAVY_2[i] * ratio) for i in range(3)
        )
        draw.line((0, y, width, y), fill=color)

    glow = Image.new("RGBA", FRAME_SIZE, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-260, -220, 650, 700), fill=(42, 164, 255, 90))
    gd.ellipse((520, 980, 1320, 1830), fill=(22, 109, 214, 65))
    glow = glow.filter(ImageFilter.GaussianBlur(115))
    return Image.alpha_composite(image.convert("RGBA"), glow).convert("RGB")


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return []
    lines = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        box = draw.textbbox((0, 0), trial, font=font)
        if box[2] - box[0] <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _draw_multiline(draw, text, x, y, font, fill, max_width, max_lines=4, gap=10):
    for line in _wrap(draw, text, font, max_width)[:max_lines]:
        draw.text((x, y), line, font=font, fill=fill)
        box = draw.textbbox((x, y), line, font=font)
        y += box[3] - box[1] + gap
    return y


def _rounded_asset(source: str, size: tuple[int, int], radius: int = 36, crop: bool = False):
    with Image.open(source) as raw:
        image = raw.convert("RGB")
    if crop:
        image = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
    else:
        contained = ImageOps.contain(image, size, method=Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", size, (9, 28, 45))
        x = (size[0] - contained.width) // 2
        y = (size[1] - contained.height) // 2
        canvas.paste(contained, (x, y))
        image = canvas

    mask = Image.new("L", size, 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    rgba = image.convert("RGBA")
    rgba.putalpha(mask)
    return rgba


def _paste_glow(base: Image.Image, overlay: Image.Image, xy: tuple[int, int]):
    x, y = xy
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    alpha = overlay.getchannel("A").filter(ImageFilter.GaussianBlur(24))
    glow = Image.new("RGBA", overlay.size, (57, 177, 255, 0))
    glow.putalpha(alpha.point(lambda p: int(p * 0.36)))
    shadow.alpha_composite(glow, (x, y))
    base.alpha_composite(shadow)
    base.alpha_composite(overlay, (x, y))


def _badge(draw, text, x, y, color=BLUE, width=None):
    font = _font(FONT_BOLD, 28)
    box = draw.textbbox((0, 0), text, font=font)
    w = width or (box[2] - box[0] + 38)
    draw.rounded_rectangle((x, y, x + w, y + 58), radius=29, fill=(*color, 40), outline=color, width=2)
    draw.text((x + 18, y + 10), text, font=font, fill=color)


def _progress(draw, active: int):
    left, gap, width = 70, 13, 172
    for index in range(5):
        color = BLUE if index <= active else (52, 79, 103)
        x = left + index * (width + gap)
        draw.rounded_rectangle((x, 56, x + width, 64), radius=4, fill=color)


def _scene_hook(tutor_path, hook, module):
    base = _gradient_background().convert("RGBA")
    draw = ImageDraw.Draw(base)
    _progress(draw, 0)
    draw.text((70, 110), "H2D STUDIO · REEL", font=_font(FONT_BOLD, 28), fill=BLUE)
    y = _draw_multiline(draw, hook.upper(), 70, 190, _font(FONT_BOLD, 72), WHITE, 900, 4, 8)
    draw.text((72, y + 10), "PREPARA TU OPOSICIÓN CON CONTENIDO REAL", font=_font(FONT_MEDIUM, 29), fill=MUTED)
    tutor = _rounded_asset(tutor_path, (720, 1030), 54, True)
    _paste_glow(base, tutor, (180, 690))
    _badge(draw, module.upper(), 70, 1730, BLUE)
    _badge(draw, "CANARIAS", 70, 1800, (88, 205, 255))
    return base.convert("RGB")


def _scene_question(tutor_path, question_path):
    base = _gradient_background().convert("RGBA")
    draw = ImageDraw.Draw(base)
    _progress(draw, 1)
    draw.text((70, 110), "ENTRENA CON PREGUNTAS REALES", font=_font(FONT_BOLD, 28), fill=BLUE)
    draw.text((70, 190), "PREGUNTAS Y EXÁMENES", font=_font(FONT_BOLD, 58), fill=WHITE)
    draw.text((70, 262), "OFICIALES", font=_font(FONT_BOLD, 58), fill=BLUE)
    draw.text((72, 340), "Practica con la interfaz real de H2D.", font=_font(FONT_MEDIUM, 30), fill=MUTED)
    panel = _rounded_asset(question_path, (900, 1110), 42, False)
    _paste_glow(base, panel, (90, 500))
    tutor = _rounded_asset(tutor_path, (260, 300), 38, True)
    _paste_glow(base, tutor, (750, 1450))
    _badge(draw, "TIPO TEST", 70, 1650, BLUE)
    _badge(draw, "EXÁMENES OFICIALES", 70, 1720, GREEN)
    return base.convert("RGB")


def _scene_feedback(feedback_path):
    base = _gradient_background().convert("RGBA")
    draw = ImageDraw.Draw(base)
    _progress(draw, 2)
    draw.text((70, 110), "NO MEMORICES: ENTIENDE", font=_font(FONT_BOLD, 28), fill=BLUE)
    draw.text((70, 190), "FEEDBACK INMEDIATO", font=_font(FONT_BOLD, 58), fill=WHITE)
    draw.text((70, 262), "+ BASE LEGAL", font=_font(FONT_BOLD, 58), fill=GREEN)
    draw.text((72, 340), "Corrige, entiende el error y aprende la regla de examen.", font=_font(FONT_MEDIUM, 28), fill=MUTED)
    panel = _rounded_asset(feedback_path, (900, 1160), 42, False)
    _paste_glow(base, panel, (90, 470))
    draw.rounded_rectangle((90, 1655, 990, 1790), radius=34, fill=(8, 45, 49), outline=GREEN, width=3)
    draw.text((126, 1680), "✓  RESPUESTA + EXPLICACIÓN", font=_font(FONT_BOLD, 32), fill=GREEN)
    draw.text((126, 1732), "Normativa · regla · feedback", font=_font(FONT_MEDIUM, 27), fill=WHITE)
    return base.convert("RGB")


def _scene_features(extra_paths: list[str]):
    base = _gradient_background().convert("RGBA")
    draw = ImageDraw.Draw(base)
    _progress(draw, 3)
    draw.text((70, 110), "TODO EN UNA PLATAFORMA", font=_font(FONT_BOLD, 28), fill=BLUE)
    draw.text((70, 190), "ENTRENA TODO", font=_font(FONT_BOLD, 62), fill=WHITE)
    draw.text((70, 265), "EN H2D", font=_font(FONT_BOLD, 62), fill=BLUE)

    cards = [
        ("POLICÍA LOCAL", "Teoría y exámenes", BLUE),
        ("CGPC", "Preparación específica", (235, 89, 95)),
        ("SUPUESTOS", "Resolución razonada", GREEN),
        ("INGLÉS", "Pregunta + explicación", (131, 152, 255)),
    ]
    positions = [(70, 455), (555, 455), (70, 700), (555, 700)]
    for (title, subtitle, color), (x, y) in zip(cards, positions):
        draw.rounded_rectangle((x, y, x + 455, y + 205), radius=34, fill=CARD_2, outline=color, width=3)
        draw.ellipse((x + 28, y + 28, x + 82, y + 82), fill=color)
        draw.text((x + 105, y + 30), title, font=_font(FONT_BOLD, 30), fill=WHITE)
        draw.text((x + 105, y + 88), subtitle, font=_font(FONT_MEDIUM, 23), fill=MUTED)

    _badge(draw, "+40 EXÁMENES OFICIALES", 70, 1010, BLUE, 430)
    _badge(draw, "FEEDBACK POR PREGUNTA", 70, 1080, GREEN, 430)
    _badge(draw, "ENTRENA COMO TE EXAMINAN", 70, 1150, (132, 154, 255), 505)

    if extra_paths:
        for index, path in enumerate(extra_paths[:3]):
            thumb = _rounded_asset(path, (270, 430), 28, False)
            _paste_glow(base, thumb, (70 + index * 298, 1320))
    else:
        draw.rounded_rectangle((70, 1320, 1010, 1760), radius=42, fill=CARD, outline=(55, 131, 190), width=3)
        draw.text((125, 1445), "H2D OPOSICIONES", font=_font(FONT_BOLD, 57), fill=WHITE)
        draw.text((125, 1530), "Preguntas · Feedback · Supuestos · Inglés", font=_font(FONT_MEDIUM, 28), fill=MUTED)
        draw.text((125, 1630), "CANARIAS", font=_font(FONT_BOLD, 42), fill=BLUE)
    return base.convert("RGB")


def _scene_cta(tutor_path, question_path, cta, website):
    base = _gradient_background().convert("RGBA")
    draw = ImageDraw.Draw(base)
    _progress(draw, 4)
    screen = _rounded_asset(question_path, (630, 930), 42, False)
    _paste_glow(base, screen, (390, 410))
    tutor = _rounded_asset(tutor_path, (520, 960), 50, True)
    _paste_glow(base, tutor, (40, 615))
    draw.rounded_rectangle((70, 115, 1010, 365), radius=44, fill=(8, 31, 51), outline=BLUE, width=3)
    draw.text((112, 152), "H2D OPOSICIONES", font=_font(FONT_BOLD, 62), fill=WHITE)
    draw.text((112, 238), "Entrena como te van a examinar", font=_font(FONT_MEDIUM, 31), fill=BLUE)
    draw.rounded_rectangle((70, 1505, 1010, 1735), radius=42, fill=(9, 35, 57), outline=GREEN, width=3)
    _draw_multiline(draw, cta, 112, 1540, _font(FONT_BOLD, 33), WHITE, 855, 3, 7)
    draw.rounded_rectangle((70, 1770, 1010, 1850), radius=40, fill=BLUE)
    web_font = _font(FONT_BOLD, 34)
    box = draw.textbbox((0, 0), website, font=web_font)
    draw.text(((1080 - (box[2]-box[0])) / 2, 1788), website, font=web_font, fill=(4, 24, 39))
    return base.convert("RGB")


async def _tts_async(text: str, voice_name: str, output_path: str):
    communicate = edge_tts.Communicate(text=text, voice=voice_name, rate="+0%", volume="+0%")
    await communicate.save(output_path)


def _generate_tts(text: str, voice_name: str, output_path: str):
    asyncio.run(_tts_async(text, voice_name, output_path))
    if not os.path.isfile(output_path) or os.path.getsize(output_path) <= 0:
        raise RuntimeError("No se pudo generar la voz española del Reel.")


def render_reel(
    *,
    image_paths: Iterable[str],
    spoken_text: str,
    voice_name: str,
    requested_duration: int,
    output_path: str,
    hook: str = "¿Opositas a Policía Local en Canarias?",
    cta: str = "Entrena como te van a examinar. Empieza hoy con H2D Oposiciones.",
    website: str = "h2doposiciones.es",
    module: str = "Policía Local",
) -> str:
    sources = [str(Path(path)) for path in image_paths if path]
    if len(sources) < 2:
        raise ValueError("Se necesita al menos la imagen del tutor y una captura de pregunta.")
    if not spoken_text.strip():
        raise ValueError("El texto hablado no puede estar vacío.")

    tutor_path = sources[0]
    question_path = sources[1]
    feedback_path = sources[2] if len(sources) > 2 else question_path
    extra_paths = sources[3:]
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="h2d_reel_v2_") as workdir:
        audio_path = os.path.join(workdir, "voice.mp3")
        _generate_tts(spoken_text.strip(), voice_name, audio_path)
        audio = AudioFileClip(audio_path)
        target_duration = max(float(requested_duration), float(audio.duration) + 0.20)

        scene_images = [
            _scene_hook(tutor_path, hook, module),
            _scene_question(tutor_path, question_path),
            _scene_feedback(feedback_path),
            _scene_features(extra_paths),
            _scene_cta(tutor_path, question_path, cta, website),
        ]
        scene_paths = []
        for index, scene in enumerate(scene_images):
            scene_path = os.path.join(workdir, f"scene_{index + 1}.jpg")
            scene.save(scene_path, quality=96)
            scene_paths.append(scene_path)

        weights = [2.4, 3.0, 3.0, 2.4, 3.2]
        scale = target_duration / sum(weights)
        durations = [w * scale for w in weights]
        clips = [ImageClip(path).with_duration(duration) for path, duration in zip(scene_paths, durations)]
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
