import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import plotly.express as px

# --- 1. CONFIGURACIÓN VISUAL (MINIMALISTA) ---
st.set_page_config(page_title="Gym Tracker", page_icon="❚█══█❚", layout="wide")

# CSS: Estilos sobrios, funcionales y sin "cringe"
st.markdown("""
    <style>
    /* Botones sólidos y grandes */
    .stButton>button {
        height: 3.2rem;
        width: 100%;
        font-weight: 600;
        border-radius: 6px;
        background-color: #262730;
        color: white;
    }
    .stButton>button:hover {
        border-color: #FF4B4B;
        color: #FF4B4B;
    }
    /* Inputs numéricos grandes */
    input[type=number] { font-size: 1.1rem; }
    
    /* Tarjeta de información limpia */
    .info-card {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 8px;
        border-left: 5px solid #FF4B4B; /* Toque de color */
        margin-bottom: 20px;
    }
    .main-stat { font-size: 1.5em; font-weight: bold; color: #31333F; }
    .sub-stat { font-size: 1.1em; color: #555; margin-left: 10px; }
    .meta-data { font-size: 0.9em; color: #666; margin-top: 5px; }
    </style>
""", unsafe_allow_html=True)

# --- 2. GESTIÓN DE VARIABLES ---
vars_init = {
    'ejercicio_actual': None,
    'peso_input': 0.0,
    'reps_input': 10,
    'series_input': 1,
    'timer_running': False,
    'ultimo_ej_visto': None
}
for k, v in vars_init.items():
    if k not in st.session_state: st.session_state[k] = v

# --- 3. CONEXIÓN Y DATOS (BLINDADA) ---
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
        
        # 1. Limpieza de Texto
        if "Ejercicio" in df.columns:
            df["Ejercicio"] = df["Ejercicio"].astype(str).str.strip().str.upper()
        
        # 2. Limpieza de Fechas
        if "Fecha" in df.columns:
            df["Fecha"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce').dt.date
            df = df.dropna(subset=["Fecha"])

        # 3. Limpieza Numérica (CRÍTICO PARA EVITAR ERRORES)
        cols_num = ["Peso_KG", "Series", "Reps", "Volumen", "1RM_Estimado"]
        for col in cols_num:
            if col in df.columns:
                # Forzamos conversión a número, si falla pone 0
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
        return df
    except Exception as e:
        st.error(f"Error leyendo datos: {e}")
        return pd.DataFrame()

def save_data(row):
    sheet = get_google_sheet()
    if sheet:
        sheet.append_row(row)
        return True
    return False

# --- 4. LÓGICA DE NEGOCIO ---

def get_last_session_stats(df, ejercicio):
    """Obtiene los datos de la última sesión registrada."""
    if df.empty or ejercicio not in df["Ejercicio"].values:
        return None
    
    # Filtrar y ordenar por fecha más reciente
    historial = df[df["Ejercicio"] == ejercicio].sort_values("Fecha", ascending=False)
    ultima_fecha = historial.iloc[0]["Fecha"]
    
    # Obtener solo los datos de ese día
    sesion_dia = historial[historial["Fecha"] == ultima_fecha]
    
    # Dato representativo: La serie con más peso
    mejor_serie = sesion_dia.loc[sesion_dia["Peso_KG"].idxmax()]
    
    # Contar cuántas series se hicieron ese día (filas)
    total_series = len(sesion_dia)
    
    return {
        "fecha": ultima_fecha,
        "peso_kg": float(mejor_serie["Peso_KG"]),
        "reps": int(mejor_serie["Reps"]),
        "series_totales": total_series,
        "notas": str(mejor_serie.get("Notas", ""))
    }

def convert_display(val_kg, is_lb):
    """Solo para mostrar en pantalla."""
    return round(val_kg * 2.20462, 2) if is_lb else val_kg

def convert_save(val_input, is_lb):
    """Convierte a KG para guardar si el input fue en LB."""
    return round(val_input / 2.20462, 2) if is_lb else val_input

# --- 5. INTERFAZ ---

# Sidebar Config
with st.sidebar:
    st.header("Ajustes")
    # Toggle simple
    modo_lb = st.toggle("Modo Libras (Input)", value=False)
    unit_label = "LB" if modo_lb else "KG"
    
    st.divider()
    if st.button("🔄 Actualizar Datos"):
        get_data.clear()
        st.rerun()

# Carga inicial
df = get_data()

st.title("Gym Tracker")

# Tabs principales
t_input, t_graphs, t_history = st.tabs(["Registro", "Progreso", "Historial"])

# === TAB 1: REGISTRO ===
with t_input:
    # Selector de Ejercicio
    col_sel, col_new = st.columns([2, 1])
    
    lista_ej = sorted(df["Ejercicio"].unique()) if not df.empty else []
    
    opcion = st.radio("Modo:", ["Lista", "Crear"], horizontal=True, label_visibility="collapsed")
    
    ej_seleccionado = None
    if opcion == "Lista":
        if lista_ej:
            idx = 0
            if st.session_state.ejercicio_actual in lista_ej:
                idx = lista_ej.index(st.session_state.ejercicio_actual)
            ej_seleccionado = st.selectbox("Ejercicio:", lista_ej, index=idx)
        else:
            st.warning("Sin ejercicios.")
    else:
        nuevo = st.text_input("Nuevo Ejercicio:").strip().upper()
        if nuevo: ej_seleccionado = nuevo

    # Si tenemos ejercicio, mostramos interfaz
    if ej_seleccionado:
        st.session_state.ejercicio_actual = ej_seleccionado
        stats = get_last_session_stats(df, ej_seleccionado)
        
        # Auto-Fill solo al cambiar de ejercicio
        if st.session_state.ultimo_ej_visto != ej_seleccionado:
            if stats:
                st.session_state.peso_input = convert_display(stats["peso_kg"], modo_lb)
                st.session_state.reps_input = stats["reps"]
                st.session_state.series_input = 1 # Reiniciar contador de series para hoy
            else:
                st.session_state.peso_input = 0.0
                st.session_state.series_input = 1
            st.session_state.ultimo_ej_visto = ej_seleccionado

        # TARJETA ÚLTIMA SESIÓN (Con Series incluidas)
        if stats:
            p_show = convert_display(stats['peso_kg'], modo_lb)
            u_show = "LB" if modo_lb else "KG"
            
            st.markdown(f"""
            <div class="info-card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <span style="font-size:0.85em; text-transform:uppercase; letter-spacing:1px; color:#888;">Última Sesión ({stats['fecha']})</span><br>
                        <span class="main-stat">{p_show} {u_show}</span> 
                        <span class="sub-stat">x {stats['reps']} reps</span>
                    </div>
                    <div style="text-align:right;">
                        <span style="font-size:2em; font-weight:bold; color:#31333F;">{stats['series_totales']}</span><br>
                        <span style="font-size:0.8em; color:#666;">SERIES</span>
                    </div>
                </div>
                <div class="meta-data">📝 {stats['notas'] if stats['notas'] else "Sin notas"}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("🔹 Primer registro para este ejercicio.")

        # INPUT FORM
        c1, c2 = st.columns(2)
        in_peso = c1.number_input(f"Peso ({unit_label})", value=float(st.session_state.peso_input), step=2.5)
        in_reps = c2.number_input("Reps", value=int(st.session_state.reps_input), step=1)
        
        c3, c4 = st.columns(2)
        in_series = c3.number_input("Serie N°", value=int(st.session_state.series_input), step=1)
        in_rir = c4.selectbox("RIR", ["0 (Fallo)", "1", "2", "3", "Suave"], index=1)
        
        in_notas = st.text_input("Notas", placeholder="Sensaciones...")

        if st.button("GUARDAR SERIE"):
            try:
                # Guardar siempre en KG
                peso_kg_save = convert_save(in_peso, modo_lb)
                
                # Cálculos
                rir_val = in_rir.split(" ")[0]
                rm_est = round(peso_kg_save * (1 + (in_reps / 30)), 2)
                vol_tot = peso_kg_save * in_reps * in_series
                fecha_str = datetime.now().strftime("%d/%m/%Y")
                
                row = [fecha_str, ej_seleccionado, peso_kg_save, in_series, in_reps, rir_val, rm_est, vol_tot, in_notas]
                
                if save_data(row):
                    st.toast(f"✅ Guardado: {in_peso}{unit_label} x {in_reps}")
                    st.session_state.series_input += 1
                    st.session_state.peso_input = in_peso # Mantener visual
                    get_data.clear()
                    st.session_state.timer_running = True
                    st.rerun()
            except Exception as e:
                st.error(f"Error guardando: {e}")

    # TIMER (Simple)
    if st.session_state.timer_running:
        st.divider()
        col_t, col_b = st.columns([3,1])
        ph_timer = col_t.empty()
        if col_b.button("Saltar"):
            st.session_state.timer_running = False
            st.rerun()
            
        for s in range(90, 0, -1):
            if not st.session_state.timer_running: break
            ph_timer.markdown(f"#### ⏳ Descanso: {s}s")
            time.sleep(1)
        st.session_state.timer_running = False
        st.rerun()

# === TAB 2: PROGRESO (GRÁFICAS SEPARADAS Y LIMPIAS) ===
with t_graphs:
    if df.empty:
        st.warning("Faltan datos.")
    else:
        st.subheader("Análisis de Rendimiento")
        lista_g = sorted(df["Ejercicio"].unique())
        ej_g = st.selectbox("Selecciona Ejercicio:", lista_g, key="sb_graph")
        
        # Filtrar datos del ejercicio
        df_g = df[df["Ejercicio"] == ej_g].copy()
        
        if not df_g.empty:
            # AGRUPAR POR DÍA (La clave para gráficas limpias)
            # Calculamos: Peso Máximo del día y Volumen Total del día
            df_day = df_g.groupby("Fecha").agg({
                "Peso_KG": "max",
                "Volumen": "sum"
            }).reset_index().sort_values("Fecha")
            
            col_g1, col_g2 = st.columns(2)
            
            with col_g1:
                # Gráfica 1: Fuerza (Peso Máximo)
                fig1 = px.line(df_day, x="Fecha", y="Peso_KG", markers=True, 
                               title="Fuerza Máxima (Mejor Serie)",
                               labels={"Peso_KG": "Peso (KG)"})
                fig1.update_traces(line_color="#FF4B4B", line_width=3)
                fig1.update_layout(height=350)
                st.plotly_chart(fig1, use_container_width=True)
            
            with col_g2:
                # Gráfica 2: Capacidad de Trabajo (Volumen)
                fig2 = px.bar(df_day, x="Fecha", y="Volumen", 
                              title="Volumen Total (Carga de Trabajo)",
                              labels={"Volumen": "Volumen Total (KG)"})
                fig2.update_traces(marker_color="#262730")
                fig2.update_layout(height=350)
                st.plotly_chart(fig2, use_container_width=True)

# === TAB 3: HISTORIAL (LIMPIO) ===
with t_history:
    st.subheader("Diario")
    if df.empty:
        st.caption("No hay datos.")
    else:
        fechas = sorted(df["Fecha"].unique(), reverse=True)
        for f in fechas:
            with st.expander(f"📅 {f.strftime('%d-%m-%Y')}"):
                d = df[df["Fecha"] == f].copy()
                # Mostramos columnas clave
                st.dataframe(
                    d[["Ejercicio", "Peso_KG", "Series", "Reps", "RIR", "Notas"]],
                    use_container_width=True,
                    hide_index=True
                )