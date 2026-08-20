from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterable

from moviepy import AudioFileClip, ImageClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from app.services import voice


FRAME_SIZE = (1080, 1920)
FPS = 30
ROOT_DIR = Path(__file__).resolve().parents[2]
FONT_BOLD = ROOT_DIR / "resource" / "fonts" / "BeVietnamPro-Bold.ttf"
FONT_MEDIUM = ROOT_DIR / "resource" / "fonts" / "BeVietnamPro-Medium.ttf"

NAVY = (5, 16, 29)
NAVY_2 = (8, 32, 52)
BLUE = (57, 177, 255)
BLUE_2 = (25, 108, 190)
WHITE = (248, 251, 255)
MUTED = (183, 205, 224)
GREEN = (64, 211, 151)
CARD = (10, 34, 55)
CARD_2 = (14, 45, 71)


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(path), size=size)
    except OSError:
        return ImageFont.load_default()


def _gradient_background() -> Image.Image:
    width, height = FRAME_SIZE
    image = Image.new("RGB", FRAME_SIZE, NAVY)
    pixels = image.load()
    for y in range(height):
        ratio = y / max(height - 1, 1)
        r = int(NAVY[0] * (1 - ratio) + NAVY_2[0] * ratio)
        g = int(NAVY[1] * (1 - ratio) + NAVY_2[1] * ratio)
        b = int(NAVY[2] * (1 - ratio) + NAVY_2[2] * ratio)
        for x in range(width):
            pixels[x, y] = (r, g, b)

    glow = Image.new("RGBA", FRAME_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    draw.ellipse((-250, -220, 640, 690), fill=(42, 164, 255, 85))
    draw.ellipse((520, 980, 1320, 1830), fill=(22, 109, 214, 60))
    glow = glow.filter(ImageFilter.GaussianBlur(115))
    return Image.alpha_composite(image.convert("RGBA"), glow).convert("RGB")


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if _text_width(draw, trial, font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _draw_multiline(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    font: ImageFont.ImageFont,
    fill,
    max_width: int,
    line_gap: int = 14,
    max_lines: int = 5,
) -> int:
    x, y = xy
    lines = _wrap_text(draw, text, font, max_width)[:max_lines]
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        box = draw.textbbox((x, y), line, font=font)
        y += (box[3] - box[1]) + line_gap
    return y


def _rounded_image(source: str, size: tuple[int, int], radius: int = 34, crop: bool = False) -> Image.Image:
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
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    rgba = image.convert("RGBA")
    rgba.putalpha(mask)
    return rgba


def _paste_with_glow(base: Image.Image, overlay: Image.Image, xy: tuple[int, int], glow_radius: int = 24) -> None:
    x, y = xy
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    shadow_layer = Image.new("RGBA", overlay.size, (65, 180, 255, 85))
    shadow_layer.putalpha(overlay.getchannel("A").filter(ImageFilter.GaussianBlur(glow_radius)))
    shadow.alpha_composite(shadow_layer, (x, y))
    base.alpha_composite(shadow)
    base.alpha_composite(overlay, (x, y))


def _badge(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], color=BLUE, width: int | None = None) -> None:
    x, y = xy
    font = _font(FONT_BOLD, 30)
    text_w = _text_width(draw, text, font)
    box_w = width or (text_w + 34)
    draw.rounded_rectangle((x, y, x + box_w, y + 56), radius=28, fill=(*color, 42), outline=(*color, 175), width=2)
    draw.text((x + 17, y + 9), text, font=font, fill=color)


def _section_label(draw: ImageDraw.ImageDraw, text: str, y: int) -> None:
    font = _font(FONT_BOLD, 27)
    draw.text((70, y), text.upper(), font=font, fill=BLUE)
    draw.rounded_rectangle((70, y + 48, 225, y + 54), radius=3, fill=BLUE)


def _progress(draw: ImageDraw.ImageDraw, active: int) -> None:
    left = 70
    gap = 13
    width = 172
    for index in range(5):
        color = BLUE if index <= active else (52, 79, 103)
        draw.rounded_rectangle((left + index * (width + gap), 56, left + index * (width + gap) + width, 64), radius=4, fill=color)


def _scene_hook(tutor_path: str, hook: str, module: str) -> Image.Image:
    base = _gradient_background().convert("RGBA")
    draw = ImageDraw.Draw(base)
    _progress(draw, 0)
    _section_label(draw, "H2D Studio · Reel", 105)

    title_font = _font(FONT_BOLD, 72)
    y = _draw_multiline(draw, hook.upper(), (70, 195), title_font, WHITE, 900, line_gap=8, max_lines=4)
    draw.text((72, y + 12), "PREPARA TU OPOSICIÓN CON CONTENIDO REAL", font=_font(FONT_MEDIUM, 29), fill=MUTED)

    tutor = _rounded_image(tutor_path, (720, 1030), radius=54, crop=True)
    _paste_with_glow(base, tutor, (180, 690), 30)

    _badge(draw, module, (70, 1725), BLUE)
    _badge(draw, "CANARIAS", (70, 1793), (88, 205, 255))
    return base.convert("RGB")


def _scene_question(tutor_path: str, question_path: str) -> Image.Image:
    base = _gradient_background().convert("RGBA")
    draw = ImageDraw.Draw(base)
    _progress(draw, 1)
    _section_label(draw, "Entrena con preguntas reales", 112)

    draw.text((70, 195), "PREGUNTAS Y EXÁMENES", font=_font(FONT_BOLD, 59), fill=WHITE)
    draw.text((70, 264), "OFICIALES", font=_font(FONT_BOLD, 59), fill=BLUE)
    draw.text((72, 344), "Practica con la interfaz real de H2D.", font=_font(FONT_MEDIUM, 30), fill=MUTED)

    panel = _rounded_image(question_path, (900, 1110), radius=42, crop=False)
    _paste_with_glow(base, panel, (90, 500), 24)

    tutor = _rounded_image(tutor_path, (260, 300), radius=38, crop=True)
    _paste_with_glow(base, tutor, (750, 1450), 18)

    _badge(draw, "TIPO TEST", (70, 1652), BLUE)
    _badge(draw, "EXÁMENES OFICIALES", (70, 1722), GREEN)
    return base.convert("RGB")


def _scene_feedback(feedback_path: str) -> Image.Image:
    base = _gradient_background().convert("RGBA")
    draw = ImageDraw.Draw(base)
    _progress(draw, 2)
    _section_label(draw, "No memorices: entiende", 112)

    draw.text((70, 195), "FEEDBACK INMEDIATO", font=_font(FONT_BOLD, 58), fill=WHITE)
    draw.text((70, 266), "+ BASE LEGAL", font=_font(FONT_BOLD, 58), fill=GREEN)
    draw.text((72, 348), "Corrige, entiende el error y aprende la regla de examen.", font=_font(FONT_MEDIUM, 28), fill=MUTED)

    panel = _rounded_image(feedback_path, (900, 1160), radius=42, crop=False)
    _paste_with_glow(base, panel, (90, 470), 24)

    draw.rounded_rectangle((90, 1658, 990, 1785), radius=34, fill=(8, 45, 49, 235), outline=(64, 211, 151, 210), width=3)
    draw.text((126, 1682), "✓  RESPUESTA CORRECTA", font=_font(FONT_BOLD, 33), fill=GREEN)
    draw.text((126, 1730), "Normativa + explicación + clave", font=_font(FONT_MEDIUM, 27), fill=WHITE)
    return base.convert("RGB")


def _scene_features(extra_paths: list[str]) -> Image.Image:
    base = _gradient_background().convert("RGBA")
    draw = ImageDraw.Draw(base)
    _progress(draw, 3)
    _section_label(draw, "Todo en una plataforma", 112)

    draw.text((70, 195), "ENTRENA TODO", font=_font(FONT_BOLD, 62), fill=WHITE)
    draw.text((70, 270), "EN H2D", font=_font(FONT_BOLD, 62), fill=BLUE)

    cards = [
        ("POLICÍA LOCAL", "Teoría y exámenes", BLUE),
        ("CGPC", "Preparación específica", (235, 89, 95)),
        ("SUPUESTOS", "Resolución razonada", (91, 219, 159)),
        ("INGLÉS", "Pregunta + explicación", (131, 152, 255)),
    ]
    positions = [(70, 455), (555, 455), (70, 700), (555, 700)]
    for (title, subtitle, color), (x, y) in zip(cards, positions):
        draw.rounded_rectangle((x, y, x + 455, y + 205), radius=34, fill=(*CARD_2, 255), outline=(*color, 180), width=3)
        draw.ellipse((x + 28, y + 28, x + 82, y + 82), fill=(*color, 60), outline=(*color, 220), width=2)
        draw.text((x + 105, y + 30), title, font=_font(FONT_BOLD, 31), fill=WHITE)
        draw.text((x + 105, y + 86), subtitle, font=_font(FONT_MEDIUM, 24), fill=MUTED)
        draw.rounded_rectangle((x + 28, y + 145, x + 200, y + 172), radius=13, fill=(*color, 45))

    _badge(draw, "+40 EXÁMENES OFICIALES", (70, 1010), BLUE, width=430)
    _badge(draw, "FEEDBACK POR PREGUNTA", (70, 1080), GREEN, width=430)
    _badge(draw, "ENTRENA COMO TE EXAMINAN", (70, 1150), (132, 154, 255), width=505)

    if extra_paths:
        thumb_w = 270
        gap = 28
        start_x = 70
        for index, path in enumerate(extra_paths[:3]):
            thumb = _rounded_image(path, (thumb_w, 430), radius=28, crop=False)
            _paste_with_glow(base, thumb, (start_x + index * (thumb_w + gap), 1320), 15)
    else:
        draw.rounded_rectangle((70, 1320, 1010, 1760), radius=42, fill=(*CARD, 235), outline=(55, 131, 190, 155), width=3)
        draw.text((125, 1445), "H2D OPOSICIONES", font=_font(FONT_BOLD, 57), fill=WHITE)
        draw.text((125, 1528), "Preguntas · Feedback · Supuestos · Inglés", font=_font(FONT_MEDIUM, 29), fill=MUTED)
        draw.text((125, 1630), "CANARIAS", font=_font(FONT_BOLD, 42), fill=BLUE)
    return base.convert("RGB")


def _scene_cta(tutor_path: str, question_path: str | None, cta: str, website: str) -> Image.Image:
    base = _gradient_background().convert("RGBA")
    draw = ImageDraw.Draw(base)
    _progress(draw, 4)

    if question_path:
        screen = _rounded_image(question_path, (630, 930), radius=42, crop=False)
        _paste_with_glow(base, screen, (390, 410), 22)

    tutor = _rounded_image(tutor_path, (520, 960), radius=50, crop=True)
    _paste_with_glow(base, tutor, (40, 615), 28)

    draw.rounded_rectangle((70, 115, 1010, 365), radius=44, fill=(8, 31, 51, 235), outline=(57, 177, 255, 150), width=3)
    draw.text((112, 152), "H2D OPOSICIONES", font=_font(FONT_BOLD, 62), fill=WHITE)
    draw.text((112, 238), "Entrena como te van a examinar", font=_font(FONT_MEDIUM, 31), fill=BLUE)

    cta_box_y = 1505
    draw.rounded_rectangle((70, cta_box_y, 1010, cta_box_y + 230), radius=42, fill=(9, 35, 57, 245), outline=(64, 211, 151, 160), width=3)
    _draw_multiline(draw, cta, (112, cta_box_y + 34), _font(FONT_BOLD, 33), WHITE, 855, line_gap=7, max_lines=3)

    draw.rounded_rectangle((70, 1770, 1010, 1850), radius=40, fill=BLUE)
    website_font = _font(FONT_BOLD, 35)
    website_text = website.strip() or "h2doposiciones.es"
    w = _text_width(draw, website_text, website_font)
    draw.text(((1080 - w) // 2, 1787), website_text, font=website_font, fill=NAVY)
    return base.convert("RGB")


def _save_scene(scene: Image.Image, path: str) -> str:
    scene.save(path, quality=96)
    return path


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
    """Render the H2D V2 premium 9:16 Reel using exact uploaded screenshots.

    Asset order expected from the WebUI:
    0 tutor image, 1 question screenshot, 2 feedback screenshot, extras afterwards.
    """
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
        sub_maker = voice.tts(
            text=spoken_text.strip(),
            voice_name=voice_name,
            voice_rate=1.0,
            voice_file=audio_path,
            voice_volume=1.0,
        )
        if sub_maker is None or not os.path.isfile(audio_path):
            raise RuntimeError("No se pudo generar la voz del Reel.")

        audio = AudioFileClip(audio_path)
        target_duration = max(float(requested_duration), float(audio.duration) + 0.20)

        scene_images = [
            _scene_hook(tutor_path, hook, module),
            _scene_question(tutor_path, question_path),
            _scene_feedback(feedback_path),
            _scene_features(extra_paths),
            _scene_cta(tutor_path, question_path, cta, website),
        ]
        scene_paths: list[str] = []
        for index, scene in enumerate(scene_images):
            scene_path = os.path.join(workdir, f"scene_{index + 1}.jpg")
            scene_paths.append(_save_scene(scene, scene_path))

        weights = [2.4, 3.0, 3.0, 2.4, 3.2]
        scale = target_duration / sum(weights)
        durations = [weight * scale for weight in weights]

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
