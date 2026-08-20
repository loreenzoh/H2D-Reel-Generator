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

from app.services.h2d_hedra import generate_talking_avatar as generate_hedra_avatar
from app.services.h2d_sync import generate_talking_avatar as generate_sync_avatar
from app.services.h2d_reel import render_reel


st.set_page_config(
    page_title="H2D Reel Generator V3",
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


def _secret(name: str) -> str:
    key = os.getenv(name, "").strip()
    if key:
        return key
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


def get_hedra_key() -> str:
    return _secret("HEDRA_API_KEY")


def get_sync_key() -> str:
    return _secret("SYNC_API_KEY")


st.markdown(
    """
    <div class="h2d-hero">
      <div class="h2d-kicker">H2D STUDIO · REELS · V3</div>
      <div class="h2d-title">Generador de Reels H2D Premium</div>
      <p class="h2d-copy">Prueba gratis el tutor hablando con Sync Labs y conserva Hedra como alternativa de pago.</p>
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
        help="Para el avatar funciona mejor una imagen frontal, nítida y con la cara bien visible.",
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
        help="Si no subes feedback, la V2 reutilizará la captura de pregunta en esa escena.",
    )
    extra_images = st.file_uploader(
        "Imágenes extra para módulos/beneficios (opcional)",
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
        help="La misma voz se usa como audio conductor del avatar.",
    )
    website = st.text_input("Web", value="h2doposiciones.es")

    sync_key = get_sync_key()
    hedra_key = get_hedra_key()

    if sync_key:
        st.success("Sync Labs API detectada · prueba gratuita disponible según tu cuenta.")
    else:
        st.info("Para probar gratis el tutor: añade SYNC_API_KEY en Streamlit Secrets.")

    if hedra_key:
        st.caption("Hedra también está configurada, pero tu wallet API actual necesita saldo.")

    st.markdown(
        '<div class="h2d-card"><b>Prueba V3 · recomendada</b><br>Sync Labs permite en cuentas gratuitas 1 prueba de sync-3 al mes de hasta 15 s y funciona por API sin tarjeta.<br><br><b>Consejo</b><br>Usa un hook de 3–5 s para no desperdiciar la prueba.</div>',
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

    sync_test = st.button(
        "🆓 Probar tutor hablando · Sync Labs",
        type="primary",
        disabled=not bool(sync_key and tutor_image and hook.strip()),
    )
    hedra_test = st.button(
        "🗣️ Probar tutor hablando · Hedra",
        disabled=not bool(hedra_key and tutor_image and hook.strip()),
    )
    generate = st.button("✨ Generar Reel H2D V2")

if sync_test:
    avatar_dir = Path(tempfile.gettempdir()) / "h2d_sync" / uuid.uuid4().hex
    avatar_dir.mkdir(parents=True, exist_ok=True)
    tutor_path = save_upload(tutor_image, avatar_dir, "tutor")
    avatar_output = str(avatar_dir / "H2D_Tutor_Sync.mp4")
    try:
        with st.spinner("Sync Labs está animando al tutor. Puede tardar varios minutos…"):
            generate_sync_avatar(
                api_key=sync_key,
                image_path=tutor_path,
                text=hook.strip(),
                voice_name=voice_name,
                output_path=avatar_output,
            )
        st.session_state["h2d_sync_test"] = Path(avatar_output).read_bytes()
        st.success("Tutor hablado generado con Sync Labs. Revísalo antes de integrar el avatar en el Reel.")
    except Exception as exc:
        st.error(f"No se pudo generar el tutor con Sync Labs: {exc}")

if st.session_state.get("h2d_sync_test"):
    st.subheader("4. Prueba gratuita del tutor hablando")
    st.video(st.session_state["h2d_sync_test"])
    st.download_button(
        "⬇️ Descargar prueba Sync Labs",
        data=st.session_state["h2d_sync_test"],
        file_name="H2D_Tutor_Sync.mp4",
        mime="video/mp4",
        use_container_width=True,
    )

if hedra_test:
    avatar_dir = Path(tempfile.gettempdir()) / "h2d_hedra" / uuid.uuid4().hex
    avatar_dir.mkdir(parents=True, exist_ok=True)
    tutor_path = save_upload(tutor_image, avatar_dir, "tutor")
    avatar_output = str(avatar_dir / "H2D_Tutor_Hedra.mp4")
    try:
        with st.spinner("Hedra está animando al tutor. Puede tardar varios minutos…"):
            generate_hedra_avatar(
                api_key=hedra_key,
                image_path=tutor_path,
                text=hook.strip(),
                voice_name=voice_name,
                output_path=avatar_output,
                resolution="540p",
                aspect_ratio="9:16",
            )
        st.session_state["h2d_hedra_test"] = Path(avatar_output).read_bytes()
        st.success("Tutor hablado generado con Hedra.")
    except Exception as exc:
        st.error(f"No se pudo generar el tutor con Hedra: {exc}")

if st.session_state.get("h2d_hedra_test"):
    st.subheader("Prueba Hedra")
    st.video(st.session_state["h2d_hedra_test"])
    st.download_button(
        "⬇️ Descargar prueba Hedra",
        data=st.session_state["h2d_hedra_test"],
        file_name="H2D_Tutor_Hedra.mp4",
        mime="video/mp4",
        use_container_width=True,
    )

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
        output_path = str(job_dir / "h2d_reel_v2.mp4")

        try:
            with st.spinner("Generando voz y componiendo las 5 escenas H2D V2…"):
                render_reel(
                    image_paths=image_paths,
                    spoken_text=spoken_text,
                    voice_name=voice_name,
                    requested_duration=duration,
                    output_path=output_path,
                    hook=hook.strip(),
                    cta=cta.strip(),
                    website=website.strip(),
                    module=module,
                )
            reel_bytes = Path(output_path).read_bytes()
            st.session_state["h2d_last_reel"] = reel_bytes
            st.session_state["h2d_last_plan"] = asdict(plan)
            st.success("Reel H2D V2 generado correctamente.")
        except Exception as exc:
            st.error(f"No se pudo generar el Reel: {exc}")

if st.session_state.get("h2d_last_reel"):
    st.subheader("5. Resultado Reel")
    st.video(st.session_state["h2d_last_reel"])
    st.download_button(
        "⬇️ Descargar Reel H2D V2",
        data=st.session_state["h2d_last_reel"],
        file_name="H2D_Reel_V2.mp4",
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
