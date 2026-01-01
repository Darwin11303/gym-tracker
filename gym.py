import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import plotly.express as px

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Gym Tracker", page_icon="📓", layout="wide")

st.markdown("""
    <style>
    .stButton>button {
        height: 3rem;
        width: 100%;
        font-weight: 600;
        border-radius: 8px;
    }
    .info-card {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 8px;
        border-left: 5px solid #FF4B4B;
        margin-bottom: 20px;
    }
    .big-header { font-size: 1.2rem; font-weight: bold; color: #333; }
    </style>
""", unsafe_allow_html=True)

# --- 2. VARIABLES DE ESTADO ---
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
        
        # Normalización
        if "Ejercicio" in df.columns:
            df["Ejercicio"] = df["Ejercicio"].astype(str).str.strip().str.upper()
        if "Fecha" in df.columns:
            df["Fecha"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce').dt.date
            df = df.dropna(subset=["Fecha"])
        
        # Crear columnas nuevas si no existen (para que no falle con datos viejos)
        if "Categoria" not in df.columns: 
            df["Categoria"] = "GENERAL"
        if "Tipo_Sesion" not in df.columns:
            df["Tipo_Sesion"] = "ENTRENO"

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
    historial = df[df["Ejercicio"] == ejercicio].sort_values("Fecha", ascending=False)
    ultima_fecha = historial.iloc[0]["Fecha"]
    sesion = historial[historial["Fecha"] == ultima_fecha]
    mejor = sesion.loc[sesion["Peso_KG"].idxmax()]
    return {
        "fecha": ultima_fecha,
        "peso": float(mejor["Peso_KG"]),
        "reps": int(mejor["Reps"]),
        "series": len(sesion),
        "notas": str(mejor.get("Notas", ""))
    }

def convert_display(val, is_lb): return round(val * 2.20462, 2) if is_lb else val
def convert_save(val, is_lb): return round(val / 2.20462, 2) if is_lb else val

# --- 5. INTERFAZ ---
with st.sidebar:
    st.header("⚙️ Configuración")
    modo_lb = st.toggle("Usar Libras (LB)", value=False)
    unit = "LB" if modo_lb else "KG"
    st.divider()
    if st.button("Recargar Datos"):
        get_data.clear()
        st.rerun()

df = get_data()
st.title("Gym Tracker")

# === SELECTOR DE DÍA ===
st.markdown("### ¿Qué toca hoy?")
tipos_dia = ["PECHO Y TRÍCEPS", "ESPALDA Y BÍCEPS", "PIERNA", "HOMBRO", "FULL BODY", "OTRO"]
dia_actual = st.selectbox("Selecciona tu rutina:", tipos_dia, index=0, key="dia_focus")

t1, t2, t3 = st.tabs(["💪 Registro", "📈 Progreso", "📅 Historial"])

# --- TAB 1: REGISTRO ---
with t1:
    # FILTRO AUTOMÁTICO SEGÚN TU DÍA
    cats_dia = []
    if dia_actual == "PECHO Y TRÍCEPS": cats_dia = ["PECHO", "TRÍCEPS"]
    elif dia_actual == "ESPALDA Y BÍCEPS": cats_dia = ["ESPALDA", "BÍCEPS"]
    elif dia_actual == "PIERNA": cats_dia = ["PIERNA", "GLÚTEO", "GEMELO"]
    elif dia_actual == "HOMBRO": cats_dia = ["HOMBRO"]
    
    # 1. Selector
    modo = st.radio("Acción:", ["Seleccionar Ejercicio", "Crear Nuevo"], horizontal=True, label_visibility="collapsed")
    
    ej_seleccionado = None
    cat_seleccionada = "GENERAL"

    if modo == "Seleccionar Ejercicio":
        if not df.empty:
            lista_total = df[["Ejercicio", "Categoria"]].drop_duplicates().sort_values("Ejercicio")
            
            # FILTRO INTELIGENTE
            if dia_actual != "FULL BODY" and dia_actual != "OTRO":
                lista_filtrada = lista_total[lista_total["Categoria"].isin(cats_dia)]
                
                if lista_filtrada.empty:
                    st.warning(f"No tienes ejercicios guardados de {dia_actual}. ¡Crea uno abajo!")
                    lista_mostrar = lista_total["Ejercicio"].unique()
                else:
                    st.caption(f"Filtrando por: {', '.join(cats_dia)}")
                    lista_mostrar = lista_filtrada["Ejercicio"].unique()
            else:
                lista_mostrar = lista_total["Ejercicio"].unique()
            
            idx = 0
            if st.session_state.ejercicio_actual in lista_mostrar:
                idx = list(lista_mostrar).index(st.session_state.ejercicio_actual)
            
            ej_seleccionado = st.selectbox("Ejercicio:", lista_mostrar, index=idx)
            
            if ej_seleccionado:
                cat_row = df[df["Ejercicio"] == ej_seleccionado].iloc[0]
                cat_seleccionada = cat_row["Categoria"]
                
    else: # MODO CREAR
        c_new1, c_new2 = st.columns([2, 1])
        nuevo_nombre = c_new1.text_input("Nombre del Ejercicio:").strip().upper()
        cat_manual = c_new2.selectbox("Grupo Muscular:", ["PECHO", "ESPALDA", "PIERNA", "HOMBRO", "BÍCEPS", "TRÍCEPS", "ABDOMEN", "OTRO"])
        
        if nuevo_nombre:
            st.success(f"Se creará: **{nuevo_nombre}** en **{cat_manual}**")
            ej_seleccionado = nuevo_nombre
            cat_seleccionada = cat_manual

    # 2. Datos y Guardado
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

        # Tarjeta Info
        if stats:
            p_val = convert_display(stats['peso'], modo_lb)
            st.info(f"🔥 Récord Anterior: **{p_val} {unit}** x {stats['reps']} reps ({stats['series']} series)")

        # Formulario
        c1, c2 = st.columns(2)
        peso = c1.number_input(f"Peso ({unit})", value=float(st.session_state.peso_input), step=2.5)
        reps = c2.number_input("Reps", value=int(st.session_state.reps_input), step=1)
        
        c3, c4 = st.columns(2)
        series = c3.number_input("Serie", value=int(st.session_state.series_input), step=1)
        rir = c4.selectbox("RIR", ["0", "1", "2", "3", "Suave"], index=1)
        notas = st.text_input("Notas")

        if st.button("GUARDAR SERIE", type="primary"):
            try:
                peso_kg = convert_save(peso, modo_lb)
                vol = peso_kg * reps * series
                fecha = datetime.now().strftime("%d/%m/%Y")
                
                row = [fecha, ej_seleccionado, peso_kg, series, reps, rir, vol, notas, cat_seleccionada, dia_actual]
                
                if save_data(row):
                    st.toast(f"✅ Guardado en {dia_actual}")
                    st.session_state.series_input += 1
                    st.session_state.peso_input = peso
                    get_data.clear()
                    st.session_state.timer_running = True
                    st.rerun()
            except Exception as e: st.error(f"Error: {e}")

    # Timer
    if st.session_state.timer_running:
        st.divider()
        col_t, col_b = st.columns([3,1])
        ph = col_t.empty()
        if col_b.button("Saltar"):
            st.session_state.timer_running = False
            st.rerun()
        for s in range(90, 0, -1):
            if not st.session_state.timer_running: break
            ph.markdown(f"#### ⏳ Descanso: {s}s")
            time.sleep(1)
        st.session_state.timer_running = False
        st.rerun()

# --- TAB 2: PROGRESO ---
with t2:
    if not df.empty:
        ej_g = st.selectbox("Ver progreso de:", sorted(df["Ejercicio"].unique()))
        df_g = df[df["Ejercicio"] == ej_g].sort_values("Fecha")
        if not df_g.empty:
            df_day = df_g.groupby("Fecha")["Peso_KG"].max().reset_index()
            fig = px.area(df_day, x="Fecha", y="Peso_KG", title="Fuerza Máxima (KG)")
            fig.update_traces(line_color="#FF4B4B", fillcolor="rgba(255, 75, 75, 0.2)")
            st.plotly_chart(fig, use_container_width=True)

# --- TAB 3: HISTORIAL ---
with t3:
    st.markdown("### Diario de Entrenamiento")
    if not df.empty:
        # AQUÍ ESTABA EL ERROR: CORREGIDO 'reverse=True' por 'ascending=False'
        grupos = df.groupby(["Fecha", "Tipo_Sesion"]).size().reset_index().sort_values("Fecha", ascending=False)
        
        for _, row in grupos.iterrows():
            f = row["Fecha"]
            tipo = row["Tipo_Sesion"]
            
            label_fecha = f.strftime('%d/%m/%Y')
            titulo = f"📅 {label_fecha} | 🏷️ {tipo}"
            
            with st.expander(titulo):
                d = df[(df["Fecha"] == f) & (df["Tipo_Sesion"] == tipo)]
                st.dataframe(
                    d[["Ejercicio", "Peso_KG", "Series", "Reps", "RIR", "Notas"]],
                    use_container_width=True, 
                    hide_index=True
                )