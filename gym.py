import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time

# --- 1. CONFIGURACIÓN ROBUSTA ---
# CORRECCIÓN: Usamos "wide" en lugar de "mobile" para evitar el error
st.set_page_config(page_title="Gym Tracker Pro", page_icon="🦍", layout="wide")

# CSS para optimizar la experiencia en celular (Botones grandes y menos márgenes)
st.markdown("""
    <style>
    /* Botones grandes para dedos de gimnasio */
    .stButton>button {
        height: 3.5rem;
        width: 100%;
        font-size: 20px !important;
        font-weight: bold;
        border-radius: 10px;
    }
    /* Input de números más grande */
    input[type=number] {
        font-size: 1.2rem;
    }
    /* Reducir espacio en blanco arriba en el móvil */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 5rem;
    }
    /* Estilo para la tarjeta de 'Última vez' */
    .info-box {
        background-color: #d1e7dd;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #a3cfbb;
        margin-bottom: 20px;
        color: #0f5132;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. GESTIÓN DE ESTADO (SESSION STATE) ---
# Inicializamos variables para que NO se borren al recargar la página
vars_to_init = {
    'ejercicio_actual': None,
    'peso_actual': 0.0,
    'reps_actual': 10,
    'series_actual': 1,
    'timer_running': False,
    'ultimo_ej_visto': None
}

for key, val in vars_to_init.items():
    if key not in st.session_state:
        st.session_state[key] = val

# --- 3. CONEXIÓN A GOOGLE SHEETS (BLINDADA) ---
@st.cache_resource
def get_google_sheet():
    """Conexión persistente que soporta Secretos y Archivo JSON local."""
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    
    try:
        # 1. Intenta cargar desde secretos de Streamlit (Para la nube)
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            # Arreglo común para la clave privada en secretos
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        # 2. Intenta cargar desde archivo local (Para tu PC)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
            
        client = gspread.authorize(creds)
        return client.open("GymData").sheet1
    except Exception as e:
        st.error(f"☠️ Error crítico de conexión: {e}")
        return None

def get_data():
    """Descarga los datos y limpia formatos de fecha."""
    sheet = get_google_sheet()
    if not sheet: return pd.DataFrame()

    try:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        if df.empty: return df

        # Limpieza: Nombres en mayúsculas
        if "Ejercicio" in df.columns:
            df["Ejercicio"] = df["Ejercicio"].astype(str).str.strip().str.upper()
        
        # Limpieza: Fechas reales
        if "Fecha" in df.columns:
            df["Fecha"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce').dt.date
            df = df.dropna(subset=["Fecha"]) 
            
        return df
    except Exception as e:
        # Si falla, devolvemos dataframe vacío para no romper la app
        return pd.DataFrame()

def save_data(row_data):
    """Guarda una fila nueva."""
    sheet = get_google_sheet()
    if sheet:
        sheet.append_row(row_data)
        return True
    return False

# --- 4. LÓGICA INTELIGENTE ---
def get_last_workout_stats(df, exercise_name):
    """Busca la MEJOR serie (más peso) de la ÚLTIMA sesión."""
    if df.empty or exercise_name not in df["Ejercicio"].values:
        return None

    # Filtrar ejercicio
    historial = df[df["Ejercicio"] == exercise_name].copy()
    
    # Ordenar por fecha descendente
    historial = historial.sort_values(by="Fecha", ascending=False)
    
    # Coger la fecha más reciente
    ultima_fecha = historial.iloc[0]["Fecha"]
    
    # Filtrar solo esa sesión
    ultima_sesion = historial[historial["Fecha"] == ultima_fecha]
    
    # Buscar la serie con MAYOR PESO de ese día (Mejor referencia de fuerza)
    ultima_sesion["Peso_KG"] = pd.to_numeric(ultima_sesion["Peso_KG"], errors='coerce').fillna(0)
    mejor_serie = ultima_sesion.loc[ultima_sesion["Peso_KG"].idxmax()]
    
    return {
        "fecha": ultima_fecha,
        "peso": float(mejor_serie["Peso_KG"]),
        "reps": int(mejor_serie["Reps"]),
        "notas": str(mejor_serie.get("Notas", ""))
    }

# --- 5. INTERFAZ GRÁFICA ---
st.title("🦍 GYM TRACKER")

df = get_data()

# === PASO 1: SELECCIONAR EJERCICIO ===
# Usamos Radio Buttons horizontales. Esto evita que el input desaparezca.
st.markdown("### 1. Ejercicio")
modo = st.radio("Modo:", ["Seleccionar", "Crear Nuevo ➕"], horizontal=True, label_visibility="collapsed")

ejercicio_seleccionado = None

if modo == "Seleccionar":
    if not df.empty:
        lista_ejercicios = sorted(df["Ejercicio"].unique())
        
        # Intentamos mantener la selección previa si existe
        idx = 0
        if st.session_state.ejercicio_actual in lista_ejercicios:
            idx = lista_ejercicios.index(st.session_state.ejercicio_actual)
            
        ejercicio_seleccionado = st.selectbox(
            "Lista de ejercicios:", 
            lista_ejercicios, 
            index=idx
        )
    else:
        st.warning("Base de datos vacía.")

elif modo == "Crear Nuevo ➕":
    nuevo_ej = st.text_input("Escribe el nombre:").strip().upper()
    if nuevo_ej:
        ejercicio_seleccionado = nuevo_ej

# Actualizamos la variable global de ejercicio
if ejercicio_seleccionado:
    st.session_state.ejercicio_actual = ejercicio_seleccionado

    # === PASO 2: INTELIGENCIA (AUTO-FILL) ===
    # Lógica: Si cambiamos de ejercicio, buscamos los datos viejos y rellenamos los inputs
    if st.session_state.ultimo_ej_visto != ejercicio_seleccionado:
        stats = get_last_workout_stats(df, ejercicio_seleccionado)
        if stats:
            st.session_state.peso_actual = stats["peso"]
            st.session_state.reps_actual = stats["reps"]
            # Reset de series a 1 porque es un ejercicio nuevo hoy
            st.session_state.series_actual = 1 
        else:
            # Si es nuevo, reseteamos a valores por defecto
            st.session_state.peso_actual = 0.0
            st.session_state.reps_actual = 10
            st.session_state.series_actual = 1
            
        st.session_state.ultimo_ej_visto = ejercicio_seleccionado

    # Mostramos la tarjeta de información (Visual)
    stats = get_last_workout_stats(df, ejercicio_seleccionado)
    if stats:
        st.markdown(f"""
        <div class="info-box">
            <strong>🔥 Récord Anterior ({stats['fecha']}):</strong><br>
            <span style="font-size: 1.5em; font-weight:bold;">{stats['peso']} KG x {stats['reps']} reps</span><br>
            <small>📝 {stats['notas']}</small>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("🔹 Primer registro de este ejercicio.")

# === PASO 3: REGISTRAR DATOS ===
if ejercicio_seleccionado:
    st.markdown("### 2. Cargar Datos")
    
    # Inputs controlados por st.session_state
    c1, c2 = st.columns(2)
    val_peso = c1.number_input("Peso (KG)", value=float(st.session_state.peso_actual), step=2.5, key="inp_peso")
    val_reps = c2.number_input("Reps", value=int(st.session_state.reps_actual), step=1, key="inp_reps")
    
    c3, c4 = st.columns(2)
    val_series = c3.number_input("Serie N°", value=int(st.session_state.series_actual), step=1, key="inp_series")
    val_rir = c4.selectbox("RIR (Reserva)", ["Fallo (0)", "1", "2", "3", "Suave"], index=1, key="inp_rir")
    
    val_notas = st.text_input("Notas", placeholder="Sensaciones...", key="inp_notas")

    # Botón de Guardado
    if st.button("✅ GUARDAR SERIE", type="primary"):
        try:
            # Preparar datos
            rir_clean = val_rir.split(" ")[0] if isinstance(val_rir, str) else val_rir
            one_rm = round(val_peso * (1 + (val_reps / 30)), 2)
            volumen = val_peso * val_reps * val_series
            fecha_hoy = datetime.now().strftime("%d/%m/%Y")
            
            fila = [
                fecha_hoy,
                ejercicio_seleccionado,
                val_peso,
                val_series,
                val_reps,
                rir_clean,
                one_rm,
                volumen,
                val_notas
            ]
            
            # Guardar
            if save_data(fila):
                st.toast(f"Guardado: Serie {val_series} completada", icon="💾")
                
                # Actualizar estado para la siguiente serie (Auto-Incremento)
                st.session_state.series_actual = val_series + 1
                
                # Actualizar valores actuales en memoria por si el usuario cambia de pestaña
                st.session_state.peso_actual = val_peso
                st.session_state.reps_actual = val_reps
                
                # Limpiar caché para leer datos nuevos
                get_data.clear()
                
                # Activar Timer
                st.session_state.timer_running = True
                st.rerun()
                
        except Exception as e:
            st.error(f"Error al guardar: {e}")

# === PASO 4: TEMPORIZADOR VISUAL ===
if st.session_state.timer_running:
    st.markdown("---")
    
    # Contenedor del timer
    col_timer, col_btn = st.columns([3, 1])
    timer_text = col_timer.empty()
    bar = col_timer.progress(0)
    
    if col_btn.button("Saltar"):
        st.session_state.timer_running = False
        st.rerun()
    
    tiempo_total = 90 # Segundos
    
    for i in range(tiempo_total):
        if not st.session_state.timer_running: 
            break
            
        restante = tiempo_total - i
        progreso = (i + 1) / tiempo_total
        
        bar.progress(progreso)
        timer_text.markdown(f"### ⏳ Descanso: {restante}s")
        time.sleep(1)
        
    st.session_state.timer_running = False
    st.rerun()