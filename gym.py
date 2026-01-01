import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time

# --- 1. CONFIGURACIÓN ROBUSTA ---
st.set_page_config(page_title="Gym Tracker Pro", page_icon="🦍", layout="mobile")

# CSS para que los botones sean fáciles de tocar en el celular
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
    /* Mejorar visibilidad de alertas */
    .stAlert {
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. GESTIÓN DE ESTADO (SESSION STATE) ---
# Inicializamos variables críticas para que no se borren al recargar
vars_to_init = {
    'ejercicio_actual': None,
    'peso_actual': 0.0,
    'reps_actual': 10,
    'series_actual': 1,
    'timer_running': False
}

for key, val in vars_to_init.items():
    if key not in st.session_state:
        st.session_state[key] = val

# --- 3. CONEXIÓN A GOOGLE SHEETS (BLINDADA) ---
@st.cache_resource
def get_google_sheet():
    """Conexión persistente que no se rompe."""
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    
    try:
        # Intenta cargar desde secretos de Streamlit (Nube)
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        # Intenta cargar desde archivo local
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
            
        client = gspread.authorize(creds)
        return client.open("GymData").sheet1
    except Exception as e:
        st.error(f"☠️ Error crítico de conexión: {e}")
        return None

def get_data():
    """Descarga los datos y asegura que las fechas funcionen."""
    sheet = get_google_sheet()
    if not sheet: return pd.DataFrame()

    try:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        if df.empty: return df

        # Estandarización crítica de nombres y fechas
        if "Ejercicio" in df.columns:
            df["Ejercicio"] = df["Ejercicio"].astype(str).str.strip().str.upper()
        
        if "Fecha" in df.columns:
            # Forzamos conversión a fecha real
            df["Fecha"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce').dt.date
            df = df.dropna(subset=["Fecha"]) # Eliminar filas sin fecha
            
        return df
    except Exception as e:
        st.error(f"Error leyendo datos: {e}")
        return pd.DataFrame()

def save_data(row_data):
    """Guarda una fila en Google Sheets."""
    sheet = get_google_sheet()
    if sheet:
        sheet.append_row(row_data)
        return True
    return False

# --- 4. LÓGICA DE "ÚLTIMA VEZ" (CORREGIDA) ---
def get_last_workout_stats(df, exercise_name):
    """Busca la MEJOR serie de la ÚLTIMA sesión registrada."""
    if df.empty or exercise_name not in df["Ejercicio"].values:
        return None

    # 1. Filtrar solo este ejercicio
    historial = df[df["Ejercicio"] == exercise_name].copy()
    
    # 2. Ordenar por fecha (la más reciente primero)
    historial = historial.sort_values(by="Fecha", ascending=False)
    
    # 3. Obtener la fecha más reciente
    ultima_fecha = historial.iloc[0]["Fecha"]
    
    # 4. Filtrar TODAS las series de esa fecha
    ultima_sesion = historial[historial["Fecha"] == ultima_fecha]
    
    # 5. Buscar la serie con MAYOR PESO de ese día (para referencia de fuerza)
    # Convertimos a numérico por seguridad
    ultima_sesion["Peso_KG"] = pd.to_numeric(ultima_sesion["Peso_KG"], errors='coerce').fillna(0)
    mejor_serie = ultima_sesion.loc[ultima_sesion["Peso_KG"].idxmax()]
    
    return {
        "fecha": ultima_fecha,
        "peso": float(mejor_serie["Peso_KG"]),
        "reps": int(mejor_serie["Reps"]),
        "notas": str(mejor_serie.get("Notas", ""))
    }

# --- 5. INTERFAZ PRINCIPAL ---
st.title("🦍 GYM TRACKER")

df = get_data()

# --- SECCIÓN A: SELECCIÓN DE EJERCICIO ---
# Usamos st.radio horizontal para que sea imposible que desaparezca el input
st.markdown("### 1. ¿Qué vas a entrenar?")
modo = st.radio("Modo:", ["Seleccionar Existente", "Crear Nuevo ➕"], horizontal=True, label_visibility="collapsed")

ejercicio_seleccionado = None

if modo == "Seleccionar Existente":
    if not df.empty:
        lista_ejercicios = sorted(df["Ejercicio"].unique())
        # Index dinámico para mantener la selección
        idx = 0
        if st.session_state.ejercicio_actual in lista_ejercicios:
            idx = lista_ejercicios.index(st.session_state.ejercicio_actual)
            
        ejercicio_seleccionado = st.selectbox(
            "Busca tu ejercicio:", 
            lista_ejercicios, 
            index=idx,
            key="sb_ejercicio"
        )
    else:
        st.warning("No hay ejercicios. Crea uno nuevo.")

elif modo == "Crear Nuevo ➕":
    st.info("Escribe el nombre del nuevo ejercicio abajo:")
    nuevo_ej = st.text_input("Nombre del ejercicio:").strip().upper()
    if nuevo_ej:
        ejercicio_seleccionado = nuevo_ej

# Actualizar estado global
if ejercicio_seleccionado:
    st.session_state.ejercicio_actual = ejercicio_seleccionado


# --- SECCIÓN B: LA REFERENCIA (Última vez) ---
st.markdown("---")
col_ref, col_form = st.columns([1, 1]) # En móvil esto se apila verticalmente

# Lógica de pre-llenado inteligente
last_stats = None
if ejercicio_seleccionado:
    last_stats = get_last_workout_stats(df, ejercicio_seleccionado)
    
    # Si encontramos datos y el usuario no ha tocado nada todavía, pre-llenamos
    # (Solo lo hacemos si cambiamos de ejercicio para no molestar)
    if last_stats and 'ultimo_ej_visto' not in st.session_state:
        st.session_state.peso_actual = last_stats["peso"]
        st.session_state.reps_actual = last_stats["reps"]
        st.session_state.ultimo_ej_visto = ejercicio_seleccionado
    elif last_stats and st.session_state.get('ultimo_ej_visto') != ejercicio_seleccionado:
        st.session_state.peso_actual = last_stats["peso"]
        st.session_state.reps_actual = last_stats["reps"]
        st.session_state.ultimo_ej_visto = ejercicio_seleccionado

# Mostrar la tarjeta de "Última Vez"
if last_stats:
    st.markdown(f"""
    <div style="background-color: #d1e7dd; padding: 10px; border-radius: 8px; border: 1px solid #a3cfbb; margin-bottom: 15px;">
        <strong style="color: #0f5132;">🔥 Misión de Hoy (Récord Anterior):</strong><br>
        <span style="font-size: 1.2em;">{last_stats['peso']} KG x {last_stats['reps']} reps</span><br>
        <small>📅 {last_stats['fecha']} | 📝 {last_stats['notas']}</small>
    </div>
    """, unsafe_allow_html=True)
else:
    if ejercicio_seleccionado:
        st.info("🔹 Primer registro para este ejercicio.")

# --- SECCIÓN C: EL FORMULARIO DE REGISTRO ---
if ejercicio_seleccionado:
    st.markdown("### 2. Registrar Serie")
    
    # Usamos st.form para agrupar todo y evitar recargas locas
    # PERO controlamos las variables con session_state
    
    c1, c2 = st.columns(2)
    val_peso = c1.number_input("Peso (KG)", value=float(st.session_state.peso_actual), step=2.5, format="%.2f", key="input_peso")
    val_reps = c2.number_input("Reps", value=int(st.session_state.reps_actual), step=1, key="input_reps")
    
    c3, c4 = st.columns(2)
    val_series = c3.number_input("Serie N°", value=int(st.session_state.series_actual), step=1)
    val_rir = c4.selectbox("RIR (Esfuerzo)", ["Fallo (0)", "1", "2", "3", "Suave (>4)"], index=1)
    
    val_notas = st.text_input("Notas rápidas", placeholder="Ej: Me pesó mucho...")

    # Botón Guardar
    if st.button("✅ GUARDAR SERIE", type="primary"):
        try:
            # Cálculos
            rir_clean = val_rir.split(" ")[0] if isinstance(val_rir, str) else val_rir
            one_rm = round(val_peso * (1 + (val_reps / 30)), 2)
            volumen = val_peso * val_reps * val_series # Esto es volumen de la serie
            
            fecha_hoy = datetime.now().strftime("%d/%m/%Y") # Formato estricto texto para Sheets
            
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
            
            if save_data(fila):
                st.toast(f"Guardado: {ejercicio_seleccionado} ({val_peso}kg)", icon="💾")
                
                # Actualizar estado para la siguiente serie
                st.session_state.series_actual = val_series + 1
                st.session_state.peso_actual = val_peso # Mantiene el peso
                st.session_state.reps_actual = val_reps # Mantiene las reps
                
                # Limpiar cache para que se vea reflejado si recargamos
                get_data.clear()
                
                # Activar Timer
                st.session_state.timer_running = True
                st.rerun() # Recarga para actualizar número de serie y mostrar timer
                
        except Exception as e:
            st.error(f"Error al guardar: {e}")

# --- SECCIÓN D: TEMPORIZADOR DE DESCANSO ---
if st.session_state.timer_running:
    st.markdown("---")
    st.subheader("⏳ Descanso...")
    
    # Barra de progreso
    timer_placeholder = st.empty()
    btn_stop = st.button("❌ Cancelar / Listo")
    
    if btn_stop:
        st.session_state.timer_running = False
        st.rerun()
    
    # Lógica del timer (90 segundos estándar)
    tiempo_descanso = 90 
    bar = st.progress(0)
    
    for i in range(tiempo_descanso):
        if not st.session_state.timer_running: break # Salida de emergencia
        
        restante = tiempo_descanso - i
        porcentaje = (i + 1) / tiempo_descanso
        
        # Actualizamos la barra y el texto sin bloquear TOTALMENTE
        bar.progress(porcentaje)
        timer_placeholder.markdown(f"### Quedan: **{restante}s**")
        time.sleep(1)
    
    st.session_state.timer_running = False
    timer_placeholder.success("🔔 ¡A DARLE CAÑA!")
    time.sleep(2)
    st.rerun()