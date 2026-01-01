import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import plotly.express as px

# --- 1. CONFIGURACIÓN VISUAL (ESTILO PREMIUM) ---
st.set_page_config(page_title="Gym Tracker", page_icon="🦍", layout="wide")

st.markdown("""
    <style>
    /* Botones sólidos y modernos */
    .stButton>button {
        height: 3.2rem;
        width: 100%;
        font-weight: 700;
        border-radius: 8px;
        background-color: #262730;
        color: white;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        border-color: #FF4B4B;
        color: #FF4B4B;
        transform: scale(1.01);
    }
    
    /* INPUTS */
    input[type=number] { font-size: 1.2rem; }
    
    /* TARJETA ÚLTIMA SESIÓN (RECUPERADA Y MEJORADA) */
    .info-card {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 12px;
        border-left: 6px solid #FF4B4B; /* Borde rojo característico */
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 25px;
    }
    .card-header {
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        color: #888;
        margin-bottom: 10px;
        font-weight: 600;
    }
    .main-metric {
        font-size: 2rem;
        font-weight: 800;
        color: #1E1E1E;
    }
    .sub-metric {
        font-size: 1.2rem;
        color: #555;
        font-weight: 500;
        margin-left: 8px;
    }
    .secondary-box {
        text-align: right;
        background: #fff;
        padding: 5px 15px;
        border-radius: 8px;
        border: 1px solid #eee;
    }
    .notes-section {
        margin-top: 15px;
        padding-top: 10px;
        border-top: 1px solid #ddd;
        font-size: 0.95rem;
        color: #666;
        font-style: italic;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. VARIABLES ---
vars_init = {
    'ejercicio_actual': None,
    'peso_input': 0.0,
    'reps_input': 10,
    'series_input': 1,
    'timer_running': False,
    'ultimo_ej_visto': None,
    'sesion_actual': 'FULL BODY'
}
for k, v in vars_init.items():
    if k not in st.session_state: st.session_state[k] = v

# --- 3. CONEXIÓN ---
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
        
        # Limpieza
        if "Ejercicio" in df.columns:
            df["Ejercicio"] = df["Ejercicio"].astype(str).str.strip().str.upper()
        if "Fecha" in df.columns:
            df["Fecha"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce').dt.date
            df = df.dropna(subset=["Fecha"])
        
        # Columnas nuevas (asegurar compatibilidad)
        if "Categoria" not in df.columns: df["Categoria"] = "GENERAL"
        if "Tipo_Sesion" not in df.columns: df["Tipo_Sesion"] = "ENTRENO"

        cols_num = ["Peso_KG", "Series", "Reps", "Volumen"]
        for col in cols_num:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except Exception:
        return pd.DataFrame()

def save_data(row):
    sheet = get_google_sheet()
    if sheet:
        sheet.append_row(row)
        return True
    return False

# --- 4. LÓGICA AUXILIAR ---
def get_last_session_stats(df, ejercicio):
    if df.empty or ejercicio not in df["Ejercicio"].values: return None
    # Obtener última fecha
    historial = df[df["Ejercicio"] == ejercicio].sort_values("Fecha", ascending=False)
    ultima_fecha = historial.iloc[0]["Fecha"]
    # Obtener datos de ESA sesión
    sesion = historial[historial["Fecha"] == ultima_fecha]
    mejor = sesion.loc[sesion["Peso_KG"].idxmax()]
    return {
        "fecha": ultima_fecha,
        "peso": float(mejor["Peso_KG"]),
        "reps": int(mejor["Reps"]),
        "series": len(sesion), # Total de series hechas ese día
        "notas": str(mejor.get("Notas", ""))
    }

def convert_display(val, is_lb): return round(val * 2.20462, 2) if is_lb else val
def convert_save(val, is_lb): return round(val / 2.20462, 2) if is_lb else val

# --- 5. INTERFAZ ---

with st.sidebar:
    st.header("⚙️ Ajustes")
    modo_lb = st.toggle("Modo Libras (LB)", value=False)
    unit = "LB" if modo_lb else "KG"
    st.divider()
    if st.button("🔄 Forzar Recarga"):
        get_data.clear()
        st.rerun()

df = get_data()
st.title("🦍 Gym Tracker Pro")

# === SELECTOR DE RUTINA ===
st.markdown("### ¿Qué entrenamos hoy?")
tipos_dia = ["PECHO Y TRÍCEPS", "ESPALDA Y BÍCEPS", "PIERNA", "HOMBRO", "FULL BODY", "OTRO"]
dia_actual = st.selectbox("Selecciona Rutina:", tipos_dia, index=0, label_visibility="collapsed", key="dia_focus")

t1, t2, t3 = st.tabs(["💪 REGISTRO", "📊 PROGRESO", "📅 DIARIO"])

# === TAB 1: REGISTRO ===
with t1:
    # 1. Filtro de Categorías según el día seleccionado
    cats_dia = []
    if dia_actual == "PECHO Y TRÍCEPS": cats_dia = ["PECHO", "TRÍCEPS"]
    elif dia_actual == "ESPALDA Y BÍCEPS": cats_dia = ["ESPALDA", "BÍCEPS"]
    elif dia_actual == "PIERNA": cats_dia = ["PIERNA", "GLÚTEO", "GEMELO"]
    elif dia_actual == "HOMBRO": cats_dia = ["HOMBRO"]
    
    col_radio, col_void = st.columns([2,1])
    modo = col_radio.radio("Modo:", ["Seleccionar", "Crear Nuevo"], horizontal=True, label_visibility="collapsed")
    
    ej_seleccionado = None
    cat_seleccionada = "GENERAL"

    if modo == "Seleccionar":
        if not df.empty:
            lista_total = df[["Ejercicio", "Categoria"]].drop_duplicates().sort_values("Ejercicio")
            
            # Aplicar filtro inteligente
            if dia_actual not in ["FULL BODY", "OTRO"]:
                lista_filtrada = lista_total[lista_total["Categoria"].isin(cats_dia)]
                lista_mostrar = lista_filtrada["Ejercicio"].unique() if not lista_filtrada.empty else lista_total["Ejercicio"].unique()
                if lista_filtrada.empty: st.toast(f"No hay ejercicios de {dia_actual} aún.", icon="ℹ️")
            else:
                lista_mostrar = lista_total["Ejercicio"].unique()
            
            idx = 0
            if st.session_state.ejercicio_actual in lista_mostrar:
                idx = list(lista_mostrar).index(st.session_state.ejercicio_actual)
            
            ej_seleccionado = st.selectbox("Ejercicio:", lista_mostrar, index=idx)
            if ej_seleccionado:
                cat_seleccionada = df[df["Ejercicio"] == ej_seleccionado].iloc[0]["Categoria"]
    
    else: # MODO CREAR
        c_new1, c_new2 = st.columns([2, 1])
        nuevo_nombre = c_new1.text_input("Nombre Ejercicio:").strip().upper()
        cat_manual = c_new2.selectbox("Categoría:", ["PECHO", "ESPALDA", "PIERNA", "HOMBRO", "BÍCEPS", "TRÍCEPS", "ABDOMEN", "OTRO"])
        if nuevo_nombre:
            ej_seleccionado = nuevo_nombre
            cat_seleccionada = cat_manual
            st.success(f"Creando: {nuevo_nombre} ({cat_manual})")

    # 2. Tarjeta Visual y Formulario
    if ej_seleccionado:
        st.session_state.ejercicio_actual = ej_seleccionado
        stats = get_last_session_stats(df, ej_seleccionado)
        
        # Auto-Fill
        if st.session_state.ultimo_ej_visto != ej_seleccionado:
            if stats:
                st.session_state.peso_input = convert_display(stats["peso"], modo_lb)
                st.session_state.reps_input = stats["reps"]
                st.session_state.series_input = 1
            else:
                st.session_state.peso_input = 0.0
                st.session_state.series_input = 1
            st.session_state.ultimo_ej_visto = ej_seleccionado

        # --- AQUÍ VUELVE LA TARJETA VISUAL BONITA ---
        if stats:
            p_val = convert_display(stats['peso'], modo_lb)
            st.markdown(f"""
            <div class="info-card">
                <div class="card-header">📅 Última Sesión: {stats['fecha']}</div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span class="main-metric">{p_val} {unit}</span>
                        <span class="sub-metric">x {stats['reps']} reps</span>
                    </div>
                    <div class="secondary-box">
                        <span style="font-size: 1.5rem; font-weight: bold;">{stats['series']}</span><br>
                        <span style="font-size: 0.8rem; color: #666;">SERIES TOTALES</span>
                    </div>
                </div>
                <div class="notes-section">
                    📝 {stats['notas'] if stats['notas'] else "Sin notas registradas"}
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("👋 ¡Primer registro para este ejercicio!")

        # FORMULARIO
        st.markdown(f"#### Registro Serie {st.session_state.series_input}")
        c1, c2 = st.columns(2)
        peso = c1.number_input(f"Peso ({unit})", value=float(st.session_state.peso_input), step=2.5)
        reps = c2.number_input("Reps", value=int(st.session_state.reps_input), step=1)
        
        c3, c4 = st.columns(2)
        series = c3.number_input("N° Serie", value=int(st.session_state.series_input), step=1)
        rir = c4.selectbox("RIR (Reserva)", ["0", "1", "2", "3", "Suave"], index=1)
        notas = st.text_input("Notas de la serie", placeholder="Ej: Técnica inestable...")

        if st.button("✅ GUARDAR SERIE", type="primary"):
            try:
                peso_kg = convert_save(peso, modo_lb)
                vol = peso_kg * reps * series
                fecha = datetime.now().strftime("%d/%m/%Y")
                
                # Guardamos 10 columnas
                row = [fecha, ej_seleccionado, peso_kg, series, reps, rir, vol, notas, cat_seleccionada, dia_actual]
                
                if save_data(row):
                    st.toast(f"Guardado con éxito!", icon="🔥")
                    st.session_state.series_input += 1
                    st.session_state.peso_input = peso
                    get_data.clear()
                    st.session_state.timer_running = True
                    st.rerun()
            except Exception as e: st.error(f"Error: {e}")

    if st.session_state.timer_running:
        st.divider()
        col_t, col_b = st.columns([3,1])
        ph = col_t.empty()
        if col_b.button("Saltar Descanso"):
            st.session_state.timer_running = False
            st.rerun()
        for s in range(90, 0, -1):
            if not st.session_state.timer_running: break
            ph.markdown(f"### ⏳ Descanso: {s}s")
            time.sleep(1)
        st.session_state.timer_running = False
        st.rerun()

# === TAB 2: PROGRESO (GRÁFICAS RECUPERADAS) ===
with t2:
    if not df.empty:
        ej_g = st.selectbox("Analizar Ejercicio:", sorted(df["Ejercicio"].unique()))
        df_g = df[df["Ejercicio"] == ej_g].copy()
        
        if not df_g.empty:
            # Agrupar datos por día
            df_day = df_g.groupby("Fecha").agg({
                "Peso_KG": "max",
                "Volumen": "sum"
            }).reset_index().sort_values("Fecha")
            
            st.subheader("Evolución de Rendimiento")
            
            # --- AQUÍ ESTÁN LAS DOS GRÁFICAS DE VUELTA ---
            col_graph1, col_graph2 = st.columns(2)
            
            with col_graph1:
                # Gráfica 1: Fuerza (Área Roja)
                fig1 = px.area(df_day, x="Fecha", y="Peso_KG", markers=True, 
                               title="<b>Fuerza Máxima (KG)</b>", 
                               labels={"Peso_KG": "Mejor Serie"})
                fig1.update_traces(line_color="#FF4B4B", fillcolor="rgba(255, 75, 75, 0.2)")
                fig1.update_layout(height=350, margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig1, use_container_width=True)
                
            with col_graph2:
                # Gráfica 2: Volumen (Barras de Calor)
                fig2 = px.bar(df_day, x="Fecha", y="Volumen", 
                              title="<b>Volumen Total (KG)</b>",
                              color="Volumen", color_continuous_scale="RdBu_r")
                fig2.update_layout(coloraxis_showscale=False, height=350, margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig2, use_container_width=True)

# === TAB 3: DIARIO ===
with t3:
    st.subheader("Historial de Entrenamientos")
    if not df.empty:
        # CORREGIDO: ascending=False
        grupos = df.groupby(["Fecha", "Tipo_Sesion"]).size().reset_index().sort_values("Fecha", ascending=False)
        
        for _, row in grupos.iterrows():
            f = row["Fecha"]
            tipo = row["Tipo_Sesion"]
            
            fecha_str = f.strftime('%d/%m/%Y')
            titulo = f"📅 {fecha_str} - {tipo}"
            
            with st.expander(titulo):
                d = df[(df["Fecha"] == f) & (df["Tipo_Sesion"] == tipo)]
                st.dataframe(
                    d[["Ejercicio", "Peso_KG", "Series", "Reps", "RIR", "Notas"]],
                    use_container_width=True, 
                    hide_index=True
                )