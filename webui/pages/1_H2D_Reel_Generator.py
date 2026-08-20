import json
from dataclasses import asdict, dataclass

import streamlit as st


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


st.markdown(
    """
    <div class="h2d-hero">
      <div class="h2d-kicker">H2D STUDIO · REELS</div>
      <div class="h2d-title">Generador de Reels H2D</div>
      <p class="h2d-copy">Prepara un Reel 9:16 con tutor, capturas reales de H2D, voz, subtítulos y CTA.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

left, right = st.columns([1.05, 0.95], gap="large")

with left:
    st.subheader("1. Contenido")
    module = st.selectbox("Módulo", list(MODULES.keys()))
    defaults = MODULES[module]

    tutor = st.selectbox(
        "Tutor",
        ["PL tutor", "CGPC tutor", "SP tutor", "Inglés tutor"],
        index=["PL tutor", "CGPC tutor", "SP tutor", "Inglés tutor"].index(defaults["tutor"]),
    )

    hook = st.text_input("Hook inicial", value=defaults["hook"])
    tutor_script = st.text_area(
        "Texto que dirá el tutor",
        value=defaults["script"],
        height=110,
    )
    cta = st.text_input("CTA final", value="Entrena como te van a examinar. Empieza hoy con H2D Oposiciones.")

    st.subheader("2. Material visual")
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
    duration = st.slider("Duración", min_value=10, max_value=30, value=15, step=1, format="%d s")
    voice = st.selectbox(
        "Voz española",
        ["es-ES-AlvaroNeural", "es-ES-ElviraNeural"],
        help="En la siguiente fase conectaremos esta selección al TTS ya incluido en MoneyPrinterTurbo.",
    )
    website = st.text_input("Web", value="h2doposiciones.es")

    st.markdown('<div class="h2d-card"><b>Salida prevista</b><br>1080 × 1920 · 9:16 · MP4<br>Voz en español · subtítulos · CTA H2D</div>', unsafe_allow_html=True)

    if question_image:
        st.caption("Vista previa — pregunta")
        st.image(question_image, use_container_width=True)
    if feedback_image:
        st.caption("Vista previa — feedback")
        st.image(feedback_image, use_container_width=True)

    prepare = st.button("🎬 Preparar Reel", type="primary")

if prepare:
    missing = []
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
            voice=voice,
            hook=hook.strip(),
            tutor_script=tutor_script.strip(),
            cta=cta.strip(),
            website=website.strip(),
            question_image=question_image is not None,
            feedback_image=feedback_image is not None,
            extra_images=len(extra_images or []),
        )
        st.success("Plan del Reel preparado correctamente.")
        st.info(
            "Esta primera versión valida el flujo y la interfaz. En el siguiente paso conectaremos este botón al motor de MoneyPrinterTurbo para generar el MP4 real."
        )
        with st.expander("Ver plan técnico"):
            st.code(json.dumps(asdict(plan), ensure_ascii=False, indent=2), language="json")
