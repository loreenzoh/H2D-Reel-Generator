import json
import os
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.h2d_reel import render_reel


st.set_page_config(
    page_title="H2D Reel Generator",
    page_icon="🎬",
    layout="wide",
)

st.markdown(
    """
    <style>
    .stApp { background: linear-gradient(180deg, #07131f 0%, #0c2033 100%); color: #f5f7fb; }
    .block-container { max-width: 1180px; padding-top: 1.5rem; }
    h1, h2, h3 { color: #ffffff; }
    .h2d-hero {
        padding: 22px 24px;
        border: 1px solid rgba(72, 169, 255, .32);
        border-radius: 20px;
        background: linear-gradient(135deg, rgba(7,22,37,.96), rgba(17,55,86,.92));
        box-shadow: 0 18px 60px rgba(0,0,0,.25);
        margin-bottom: 18px;
    }
    .h2d-kicker { color:#58b7ff; font-size:.78rem; font-weight:800; letter-spacing:.13em; }
    .h2d-title { font-size:2rem; font-weight:900; line-height:1.05; margin:.35rem 0; }
    .h2d-copy { color:#c8d7e6; margin:0; }
    .h2d-card {
        padding: 16px 18px;
        border-radius: 16px;
        background: rgba(255,255,255,.045);
        border: 1px solid rgba(255,255,255,.09);
        margin-bottom: 12px;
    }
    .stButton > button {
        width:100%; border-radius:12px; font-weight:800; min-height:48px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@dataclass
class ReelPlan:
    module: str
    tutor: str
    duration_seconds: int
    voice: str
    hook: str
    tutor_script: str
    cta: str
    website: str
    tutor_image: bool
    question_image: bool
    feedback_image: bool
    extra_images: int


MODULES = {
    "Policía Local": {
        "tutor": "PL tutor",
        "hook": "¿Opositas a Policía Local en Canarias?",
        "script": "Practica con exámenes y preguntas oficiales y recibe feedback inmediato en cada respuesta.",
    },
    "CGPC": {
        "tutor": "CGPC tutor",
        "hook": "¿Preparas el Cuerpo General de la Policía Canaria?",
        "script": "Entrena con preguntas enfocadas al CGPC y revisa cada respuesta con feedback detallado.",
    },
    "Supuestos prácticos": {
        "tutor": "SP tutor",
        "hook": "¿Te juegas la plaza en el supuesto práctico?",
        "script": "Practica supuestos policiales con resolución razonada, normativa y explicación paso a paso.",
    },
    "Inglés": {
        "tutor": "Inglés tutor",
        "hook": "¿El inglés puede decidir tu plaza?",
        "script": "Entrena el inglés de oposición con preguntas, explicación y feedback inmediato.",
    },
}


def save_upload(upload, folder: Path, prefix: str) -> str | None:
    if upload is None:
        return None
    suffix = Path(upload.name).suffix.lower() or ".png"
    destination = folder / f"{prefix}{suffix}"
    destination.write_bytes(upload.getbuffer())
    return str(destination)


st.markdown(
    """
    <div class="h2d-hero">
      <div class="h2d-kicker">H2D STUDIO · REELS</div>
      <div class="h2d-title">Generador de Reels H2D</div>
      <p class="h2d-copy">Genera un primer MP4 9:16 con tutor, capturas reales de H2D y voz española.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

left, right = st.columns([1.05, 0.95], gap="large")

with left:
    st.subheader("1. Contenido")
    module = st.selectbox("Módulo", list(MODULES.keys()))
    defaults = MODULES[module]

    tutor_names = ["PL tutor", "CGPC tutor", "SP tutor", "Inglés tutor"]
    tutor = st.selectbox(
        "Tutor",
        tutor_names,
        index=tutor_names.index(defaults["tutor"]),
    )

    hook = st.text_input("Hook inicial", value=defaults["hook"])
    tutor_script = st.text_area(
        "Texto que dirá el tutor",
        value=defaults["script"],
        height=110,
    )
    cta = st.text_input(
        "CTA final",
        value="Entrena como te van a examinar. Empieza hoy con H2D Oposiciones.",
    )

    st.subheader("2. Material visual")
    tutor_image = st.file_uploader(
        f"Imagen de {tutor}",
        type=["png", "jpg", "jpeg", "webp"],
        key=f"tutor_image_{tutor}",
        help="En esta versión el tutor aparece como imagen. El lip-sync se conectará en la siguiente fase.",
    )
    question_image = st.file_uploader(
        "Captura de pregunta",
        type=["png", "jpg", "jpeg", "webp"],
        key="question_image",
    )
    feedback_image = st.file_uploader(
        "Captura de feedback",
        type=["png", "jpg", "jpeg", "webp"],
        key="feedback_image",
    )
    extra_images = st.file_uploader(
        "Imágenes extra (opcional)",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key="extra_images",
    )

with right:
    st.subheader("3. Formato")
    duration = st.slider(
        "Duración", min_value=10, max_value=30, value=15, step=1, format="%d s"
    )
    voice_name = st.selectbox(
        "Voz española",
        ["es-ES-AlvaroNeural", "es-ES-ElviraNeural"],
        help="Usa el TTS que ya incorpora MoneyPrinterTurbo.",
    )
    website = st.text_input("Web", value="h2doposiciones.es")

    st.markdown(
        '<div class="h2d-card"><b>Salida actual</b><br>1080 × 1920 · 9:16 · MP4<br>Capturas exactas + voz española<br><br><b>Siguiente fase</b><br>Lip-sync del tutor + subtítulos H2D + transiciones premium</div>',
        unsafe_allow_html=True,
    )

    if tutor_image:
        st.caption(f"Vista previa — {tutor}")
        st.image(tutor_image, use_container_width=True)
    if question_image:
        st.caption("Vista previa — pregunta")
        st.image(question_image, use_container_width=True)
    if feedback_image:
        st.caption("Vista previa — feedback")
        st.image(feedback_image, use_container_width=True)

    generate = st.button("🎬 Generar Reel MP4", type="primary")

if generate:
    missing = []
    if not tutor_image:
        missing.append("imagen del tutor")
    if not question_image:
        missing.append("captura de pregunta")
    if not tutor_script.strip():
        missing.append("texto del tutor")

    if missing:
        st.error("Falta: " + ", ".join(missing) + ".")
    else:
        plan = ReelPlan(
            module=module,
            tutor=tutor,
            duration_seconds=duration,
            voice=voice_name,
            hook=hook.strip(),
            tutor_script=tutor_script.strip(),
            cta=cta.strip(),
            website=website.strip(),
            tutor_image=tutor_image is not None,
            question_image=question_image is not None,
            feedback_image=feedback_image is not None,
            extra_images=len(extra_images or []),
        )

        job_dir = Path(tempfile.gettempdir()) / "h2d_reels" / uuid.uuid4().hex
        job_dir.mkdir(parents=True, exist_ok=True)

        image_paths = []
        for path in [
            save_upload(tutor_image, job_dir, "00_tutor"),
            save_upload(question_image, job_dir, "01_question"),
            save_upload(feedback_image, job_dir, "02_feedback"),
        ]:
            if path:
                image_paths.append(path)

        for index, upload in enumerate(extra_images or [], start=3):
            path = save_upload(upload, job_dir, f"{index:02d}_extra")
            if path:
                image_paths.append(path)

        spoken_text = " ".join(
            part.strip()
            for part in [hook, tutor_script, cta]
            if part and part.strip()
        )
        output_path = str(job_dir / "h2d_reel.mp4")

        try:
            with st.spinner("Generando voz y renderizando el Reel…"):
                render_reel(
                    image_paths=image_paths,
                    spoken_text=spoken_text,
                    voice_name=voice_name,
                    requested_duration=duration,
                    output_path=output_path,
                )
            reel_bytes = Path(output_path).read_bytes()
            st.session_state["h2d_last_reel"] = reel_bytes
            st.session_state["h2d_last_plan"] = asdict(plan)
            st.success("Reel generado correctamente.")
        except Exception as exc:
            st.error(f"No se pudo generar el Reel: {exc}")

if st.session_state.get("h2d_last_reel"):
    st.subheader("4. Resultado")
    st.video(st.session_state["h2d_last_reel"])
    st.download_button(
        "⬇️ Descargar Reel MP4",
        data=st.session_state["h2d_last_reel"],
        file_name="H2D_Reel.mp4",
        mime="video/mp4",
        use_container_width=True,
    )
    with st.expander("Ver plan técnico"):
        st.code(
            json.dumps(
                st.session_state.get("h2d_last_plan", {}),
                ensure_ascii=False,
                indent=2,
            ),
            language="json",
        )
