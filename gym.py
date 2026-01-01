import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import plotly.express as px

# --- 1. CONFIGURACIÓN MINIMALISTA ---
st.set_page_config(page_title="Gym Tracker", page_icon="🏋️", layout="wide")

# CSS: Estilo limpio, botones grandes para móvil, sin adornos innecesarios
st.markdown("""
    <style>
    .stButton>button {
        height: 3.5rem;
        width: 100%;
        font-size: 18px !important;
        font-weight: 600;
        border-radius: 8px;
    }
    input[type=number] { font-size: 1.2rem; }
    
    /* Tarjeta de información minimalista */
    .data-card {
        background-color: #f8f9fa;
        border-left: 4px solid #31333F; /* Acento oscuro */
        padding: 15px;
        margin-bottom: 20px;
        border-radius: 4px;
    }
    .metric-label { font-size: 0.9em; color: #666; }
    .metric-value { font-size: 1.4em; font-weight: bold; color: #333; }
    </style>
""", unsafe_allow_html=True)

# --- 2. GESTIÓN DE ESTADO ---
vars_to_init = {
    'ejercicio_actual': None,
    'peso_input': 0.0,
    'reps_input': 10,
    'series_input': 1,
    'timer_running': False,
    'ultimo_ej_visto': None
}
for key, val in vars_to_init.items():
    if key not in st.session_state:
        st.session_state[key] = val

# --- 3. CONEXIÓN (BACKEND) ---
@st.cache_resource
def get_google_sheet():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        return gspread.authorize(creds).open("GymData").sheet1
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None

def get_data():
    sheet = get_google_sheet()
    if not sheet: return pd.DataFrame()
    try:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if df.empty: return df
        
        if "Ejercicio" in df.columns:
            df["Ejercicio"] = df["Ejercicio"].astype(str).str.strip().str.upper()
        if "Fecha" in df.columns:
            df["Fecha"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce').dt.date
            df = df.dropna(subset=["Fecha"])
        
        # Asegurar números
        cols_num = ["Peso_KG", "Series", "Reps", "1RM_Estimado"]
        for c in cols_num:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
                
        return df
    except Exception:
        return pd.DataFrame()

def save_data(row_data):
    sheet = get_google_sheet()
    if sheet:
        sheet.append_row(row_data)
        return True
    return False

# --- 4. LÓGICA DE UNIDADES & DATOS ---

def convertir_mostrar(peso_kg, usar_libras):
    """Convierte KG a LB solo para visualización si el usuario quiere."""
    if usar_libras:
        return round(peso_kg * 2.20462, 2)
    return peso_kg

def convertir_guardar(peso_input, usar_libras):
    """Convierte el input del usuario a KG para guardar en la BD."""
    if usar_libras:
        return round(peso_input / 2.20462, 2)
    return peso_input

def get_last_workout_stats(df, exercise_name):
    """Busca la última sesión y saca los datos clave."""
    if df.empty or exercise_name not in df["Ejercicio"].values:
        return None

    historial = df[df["Ejercicio"] == exercise_name].sort_values(by="Fecha", ascending=False)
    ultima_fecha = historial.iloc[0]["Fecha"]
    ultima_sesion = historial[historial["Fecha"] == ultima_fecha]
    
    # Buscamos la serie con más peso de ese día como referencia
    mejor_serie = ultima_sesion.loc[ultima_sesion["Peso_KG"].idxmax()]
    
    # Calculamos total de series hechas ese día
    total_series = ultima_sesion.shape[0] 
    
    return {
        "fecha": ultima_fecha,
        "peso_kg": float(mejor_serie["Peso_KG"]),
        "reps": int(mejor_serie["Reps"]),
        "series_totales": total_series, # Series que hiciste ese día en total
        "notas": str(mejor_serie.get("Notas", ""))
    }

# --- 5. INTERFAZ DE USUARIO ---

# BARRA LATERAL (CONFIGURACIÓN)
with st.sidebar:
    st.header("⚙️ Ajustes")
    unidad = st.radio("Unidad de Medida:", ["KG (Kilogramos)", "LB (Libras)"])
    usar_lb = "LB" in unidad
    etiqueta_peso = "Libras (LB)" if usar_lb else "Kilos (KG)"
    
    st.divider()
    if st.button("Recargar Datos"):
        get_data.clear()
        st.rerun()

# CUERPO PRINCIPAL
st.title("Entrenamiento")

df = get_data()
tab_track, tab_progreso, tab_historial = st.tabs(["📝 REGISTRO", "📈 PROGRESO", "📅 HISTORIAL"])

# === PESTAÑA 1: REGISTRO ===
with tab_track:
    # 1. Selección (Indestructible)
    modo = st.radio("Acción:", ["Seleccionar", "Nuevo Ejercicio"], horizontal=True, label_visibility="collapsed")
    
    ejercicio_seleccionado = None
    
    if modo == "Seleccionar":
        if not df.empty:
            lista = sorted(df["Ejercicio"].unique())
            idx = lista.index(st.session_state.ejercicio_actual) if st.session_state.ejercicio_actual in lista else 0
            ejercicio_seleccionado = st.selectbox("Ejercicio:", lista, index=idx)
    else:
        nuevo = st.text_input("Nombre del ejercicio:").strip().upper()
        if nuevo: ejercicio_seleccionado = nuevo

    if ejercicio_seleccionado:
        st.session_state.ejercicio_actual = ejercicio_seleccionado
        
        # 2. Tarjeta "Última Vez" (Limpia y Funcional)
        stats = get_last_workout_stats(df, ejercicio_seleccionado)
        
        # Auto-Fill Logic: Si cambiamos de ejercicio, cargamos datos anteriores
        if st.session_state.ultimo_ej_visto != ejercicio_seleccionado:
            if stats:
                # Convertimos el peso de la BD (KG) a la unidad preferida para el input
                peso_visual = convertir_mostrar(stats["peso_kg"], usar_lb)
                st.session_state.peso_input = peso_visual
                st.session_state.reps_input = stats["reps"]
                st.session_state.series_input = 1
            else:
                st.session_state.peso_input = 0.0
                st.session_state.series_input = 1
            st.session_state.ultimo_ej_visto = ejercicio_seleccionado

        if stats:
            p_mostrar = convertir_mostrar(stats['peso_kg'], usar_lb)
            u_txt = "LB" if usar_lb else "KG"
            
            st.markdown(f"""
            <div class="data-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span class="metric-label">Última sesión: {stats['fecha']}</span><br>
                        <span class="metric-value">{p_mostrar} {u_txt}</span> 
                        <span style="font-size:1.2em; color:#555;">x {stats['reps']} reps</span>
                    </div>
                    <div style="text-align:right;">
                        <span class="metric-label">Volumen</span><br>
                        <span style="font-size:1.1em; font-weight:bold;">{stats['series_totales']} Series</span>
                    </div>
                </div>
                <div style="margin-top:5px; font-size:0.9em; color:#666; font-style:italic;">
                    {stats['notas'] if stats['notas'] else "Sin notas"}
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # 3. Formulario de Input
        c1, c2 = st.columns(2)
        val_peso = c1.number_input(etiqueta_peso, value=float(st.session_state.peso_input), step=2.5, key="w_in")
        val_reps = c2.number_input("Reps", value=int(st.session_state.reps_input), step=1, key="r_in")
        
        c3, c4 = st.columns(2)
        val_series = c3.number_input("Serie N°", value=int(st.session_state.series_input), step=1, key="s_in")
        val_rir = c4.selectbox("RIR", ["0 (Fallo)", "1", "2", "3", "Suave"], index=1, key="rir_in")
        
        val_notas = st.text_input("Notas", placeholder="Sensaciones...", key="n_in")
        
        if st.button("Guardar Serie", type="primary"):
            try:
                # Conversión Crítica: Guardamos SIEMPRE en KG
                peso_db = convertir_guardar(val_peso, usar_lb)
                
                rir_c = val_rir.split(" ")[0]
                rm = round(peso_db * (1 + (val_reps / 30)), 2)
                vol = peso_db * val_reps * val_series
                fecha = datetime.now().strftime("%d/%m/%Y")
                
                fila = [fecha, ejercicio_seleccionado, peso_db, val_series, val_reps, rir_c, rm, vol, val_notas]
                
                if save_data(fila):
                    st.toast(f"Guardado: {val_peso} {etiqueta_peso} x {val_reps}", icon="✅")
                    st.session_state.series_input += 1
                    st.session_state.peso_input = val_peso # Mantenemos el valor visual
                    get_data.clear()
                    st.session_state.timer_running = True
                    st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    # Timer Minimalista
    if st.session_state.timer_running:
        st.markdown("---")
        t_col, b_col = st.columns([4, 1])
        t_ph = t_col.empty()
        if b_col.button("Saltar"):
            st.session_state.timer_running = False
            st.rerun()
            
        segundos = 90
        bar = st.progress(0)
        for i in range(segundos):
            if not st.session_state.timer_running: break
            bar.progress((i+1)/segundos)
            t_ph.caption(f"Descanso: {segundos - i}s")
            time.sleep(1)
        st.session_state.timer_running = False
        st.rerun()

# === PESTAÑA 2: PROGRESO (GRÁFICAS) ===
with tab_progreso:
    if df.empty:
        st.info("No hay datos suficientes.")
    else:
        st.subheader("Evolución de Fuerza")
        lista_graf = sorted(df["Ejercicio"].unique())
        ej_graf = st.selectbox("Selecciona Ejercicio:", lista_graf, key="sel_graf")
        
        df_g = df[df["Ejercicio"] == ej_graf].sort_values("Fecha")
        
        if not df_g.empty:
            # Opción de ver gráfica en LB o KG
            y_col = "1RM_Estimado"
            titulo_y = "1RM Estimado (KG)"
            
            if usar_lb:
                df_g["1RM_LB"] = df_g["1RM_Estimado"] * 2.20462
                y_col = "1RM_LB"
                titulo_y = "1RM Estimado (LB)"

            fig = px.line(df_g, x="Fecha", y=y_col, markers=True, 
                          title=f"Progreso Estimado en {ej_graf}")
            fig.update_layout(yaxis_title=titulo_y, xaxis_title="", template="simple_white")
            st.plotly_chart(fig, use_container_width=True)
            
            # Datos récord
            max_peso = df_g["Peso_KG"].max()
            if usar_lb: max_peso *= 2.20462
            
            c1, c2 = st.columns(2)
            c1.metric("Peso Máximo Movido", f"{round(max_peso, 2)} {'LB' if usar_lb else 'KG'}")
            c2.metric("Volumen Total Histórico", f"{int(df_g['Volumen'].sum())} Kg")

# === PESTAÑA 3: HISTORIAL (POR DÍAS) ===
with tab_historial:
    st.subheader("Diario de Entrenamiento")
    if df.empty:
        st.text("Sin registros.")
    else:
        # Agrupar por fecha descendente
        fechas = sorted(df["Fecha"].unique(), reverse=True)
        
        for fecha in fechas:
            with st.expander(f"📅 {fecha.strftime('%A %d %B, %Y')}"):
                df_day = df[df["Fecha"] == fecha].copy()
                
                # Convertir a LB visualmente si es necesario
                if usar_lb:
                    df_day["Peso"] = (df_day["Peso_KG"] * 2.20462).round(2).astype(str) + " lb"
                else:
                    df_day["Peso"] = df_day["Peso_KG"].astype(str) + " kg"
                
                # Seleccionar columnas limpias para mostrar
                display_cols = ["Ejercicio", "Peso", "Series", "Reps", "RIR", "Notas"]
                st.dataframe(
                    df_day[display_cols], 
                    use_container_width=True, 
                    hide_index=True
                )