import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import plotly.express as px

# --- 1. CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Gym Tracker", page_icon="⚡", layout="wide")

st.markdown("""
    <style>
    /* Botones sólidos */
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
    
    /* Inputs */
    input[type=number] { font-size: 1.2rem; }
    
    /* TARJETA ÚLTIMA SESIÓN */
    .info-card {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 12px;
        border-left: 6px solid #FF4B4B;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 25px;
    }
    .card-header { font-size: 0.9rem; text-transform: uppercase; letter-spacing: 1.5px; color: #888; margin-bottom: 10px; font-weight: 600; }
    .main-metric { font-size: 2rem; font-weight: 800; color: #1E1E1E; }
    .sub-metric { font-size: 1.3rem; color: #555; font-weight: 500; margin-left: 5px; }
    .rir-tag { background-color: #e0e0e0; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; color: #333; margin-left: 10px; vertical-align: middle; }
    .secondary-box { text-align: right; background: #fff; padding: 8px 15px; border-radius: 8px; border: 1px solid #eee; }
    .notes-section { margin-top: 15px; padding-top: 10px; border-top: 1px solid #ddd; font-size: 0.95rem; color: #666; font-style: italic; }
    </style>
""", unsafe_allow_html=True)

# --- 2. VARIABLES DE ESTADO ---
vars_init = {
    'ejercicio_actual': None, 'peso_input': 0.0, 'reps_input': 10, 
    'series_input': 4, 'ultimo_ej_visto': None
}
for k, v in vars_init.items():
    if k not in st.session_state: st.session_state[k] = v

# --- 3. CONEXIÓN ---
@st.cache_resource(ttl=600)
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

@st.cache_data(ttl=60)
def get_data():
    sheet = get_google_sheet()
    if not sheet: return pd.DataFrame()
    try:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if df.empty: return df
        
        # Corrección Nombres
        df.columns = [c.strip() for c in df.columns]
        rename_map = {
            "Tipo_sesion": "Tipo_Sesion", "tipo_sesion": "Tipo_Sesion",
            "categoria": "Categoria", "Peso_kg": "Peso_KG", "1RM_Estimado": "1RM_Estimado"
        }
        df = df.rename(columns=rename_map)

        if "Ejercicio" in df.columns:
            df["Ejercicio"] = df["Ejercicio"].astype(str).str.strip().str.upper()
        
        if "Fecha" in df.columns:
            df["Fecha"] = pd.to_datetime(df["Fecha"], format='mixed', dayfirst=True, errors='coerce').dt.date
            df = df.dropna(subset=["Fecha"])
        
        cols_num = ["Peso_KG", "Series", "Reps", "Volumen", "1RM_Estimado"]
        for col in cols_num:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # Rellenar textos
        if "Categoria" not in df.columns: df["Categoria"] = "GENERAL"
        if "Tipo_Sesion" not in df.columns: df["Tipo_Sesion"] = "ENTRENO"
        df["Categoria"] = df["Categoria"].fillna("GENERAL").replace("", "GENERAL")
        df["Tipo_Sesion"] = df["Tipo_Sesion"].fillna("ENTRENO").replace("", "ENTRENO")
        
        # --- CÁLCULOS MASIVOS (VECTORIZADOS) ---
        # 1. Recalcular 1RM para todo el historial
        if "Peso_KG" in df.columns and "Reps" in df.columns:
            df["1RM_Estimado"] = df["Peso_KG"] * (1 + (df["Reps"] / 30))
            
        # 2. Recalcular Volumen Correcto (Peso * Reps * Series)
        if "Volumen" in df.columns and "Peso_KG" in df.columns:
             # Solo si es 0 (dato perdido) lo recalculamos
             mask = df["Volumen"] == 0
             df.loc[mask, "Volumen"] = df.loc[mask, "Peso_KG"] * df.loc[mask, "Reps"] * df.loc[mask, "Series"]

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

# --- 4. LÓGICA (CORREGIDA: BUSCAR MEJOR 1RM) ---
def get_last_session_stats(df, ejercicio):
    if df.empty or ejercicio not in df["Ejercicio"].values: return None
    
    historial = df[df["Ejercicio"] == ejercicio].sort_values("Fecha", ascending=False)
    ultima_fecha = historial.iloc[0]["Fecha"]
    sesion = historial[historial["Fecha"] == ultima_fecha]
    
    # --- CORRECCIÓN CLAVE: La mejor serie es la que tiene mayor 1RM, no mayor Peso ---
    idx_mejor = sesion["1RM_Estimado"].idxmax()
    mejor = sesion.loc[idx_mejor]
    
    total_series_reales = int(sesion["Series"].sum())
    
    return {
        "fecha": ultima_fecha, 
        "peso": float(mejor["Peso_KG"]),
        "reps": int(mejor["Reps"]), 
        "series": total_series_reales, 
        "rir": mejor["RIR"],
        "notas": str(mejor.get("Notas", "")),
        "1rm": float(mejor["1RM_Estimado"])
    }

def convert_display(val, is_lb): return round(val * 2.20462, 2) if is_lb else val
def convert_save(val, is_lb): return round(val / 2.20462, 2) if is_lb else val

# --- 5. INTERFAZ ---
with st.sidebar:
    st.header("⚙️ Ajustes")
    modo_lb = st.toggle("Modo Libras (LB)", value=False)
    unit = "LB" if modo_lb else "KG"
    st.divider()
    if st.button("🔄 Recargar"):
        get_data.clear()
        st.rerun()

df = get_data()
st.title("Gym Tracker Pro")

st.markdown("### ¿Qué entrenamos hoy?")
tipos_dia = ["PECHO Y TRÍCEPS", "ESPALDA Y BÍCEPS", "PIERNA", "HOMBRO", "FULL BODY", "OTRO"]
dia_actual = st.selectbox("Selecciona Rutina:", tipos_dia, index=0, label_visibility="collapsed", key="dia_focus")

t1, t2, t3 = st.tabs(["💪 REGISTRO", "📊 PROGRESO", "📅 DIARIO"])

# === TAB 1: REGISTRO ===
with t1:
    cats_dia = []
    if dia_actual == "PECHO Y TRÍCEPS": cats_dia = ["PECHO", "TRÍCEPS"]
    elif dia_actual == "ESPALDA Y BÍCEPS": cats_dia = ["ESPALDA", "BÍCEPS"]
    elif dia_actual == "PIERNA": cats_dia = ["PIERNA", "GLÚTEO", "GEMELO"]
    elif dia_actual == "HOMBRO": cats_dia = ["HOMBRO"]
    
    col_radio, _ = st.columns([2,1])
    modo = col_radio.radio("Modo:", ["Seleccionar", "Crear Nuevo"], horizontal=True, label_visibility="collapsed")
    
    ej_seleccionado = None
    cat_seleccionada = "GENERAL"

    if modo == "Seleccionar":
        if not df.empty:
            lista_total = df[["Ejercicio", "Categoria"]].drop_duplicates().sort_values("Ejercicio")
            if dia_actual not in ["FULL BODY", "OTRO"]:
                lista_total["Cat_Upper"] = lista_total["Categoria"].str.upper()
                cats_dia_upper = [c.upper() for c in cats_dia]
                lista_filtrada = lista_total[lista_total["Cat_Upper"].isin(cats_dia_upper)]
                lista_mostrar = lista_filtrada["Ejercicio"].unique() if not lista_filtrada.empty else lista_total["Ejercicio"].unique()
            else:
                lista_mostrar = lista_total["Ejercicio"].unique()
            
            idx = 0
            if st.session_state.ejercicio_actual in lista_mostrar:
                idx = list(lista_mostrar).index(st.session_state.ejercicio_actual)
            
            ej_seleccionado = st.selectbox("Ejercicio:", lista_mostrar, index=idx)
            if ej_seleccionado:
                cat_row = df[df["Ejercicio"] == ej_seleccionado]
                if not cat_row.empty: cat_seleccionada = cat_row.iloc[0]["Categoria"]
    else: 
        c1, c2 = st.columns([2, 1])
        nuevo = c1.text_input("Nombre:").strip().upper()
        cat = c2.selectbox("Cat:", ["PECHO", "ESPALDA", "PIERNA", "HOMBRO", "BÍCEPS", "TRÍCEPS", "ABDOMEN", "OTRO"])
        if nuevo:
            ej_seleccionado = nuevo
            cat_seleccionada = cat
            st.success(f"Creando: {nuevo}")

    if ej_seleccionado:
        st.session_state.ejercicio_actual = ej_seleccionado
        stats = get_last_session_stats(df, ej_seleccionado)
        
        if st.session_state.ultimo_ej_visto != ej_seleccionado:
            if stats:
                st.session_state.peso_input = convert_display(stats["peso"], modo_lb)
                st.session_state.reps_input = stats["reps"]
                st.session_state.series_input = stats["series"] 
            else:
                st.session_state.peso_input = 0.0
                st.session_state.series_input = 4
            st.session_state.ultimo_ej_visto = ej_seleccionado

        # --- TARJETA VISUAL ---
        if stats:
            p_val = convert_display(stats['peso'], modo_lb)
            st.markdown(f"""
            <div class="info-card">
                <div class="card-header">📅 Última Sesión: {stats['fecha']}</div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span class="main-metric">{p_val} {unit}</span>
                        <span class="sub-metric">x {stats['reps']} reps</span>
                        <span class="rir-tag">RIR: {stats['rir']}</span>
                    </div>
                    <div class="secondary-box">
                        <span style="font-size: 1.5rem; font-weight: bold; color: #333;">{stats['series']}</span><br>
                        <span style="font-size: 0.75rem; color: #666; font-weight: bold;">SERIES REALIZADAS</span>
                    </div>
                </div>
                <div class="notes-section">📝 {stats['notas'] if stats['notas'] else "Sin notas"}</div>
            </div>""", unsafe_allow_html=True)
        else:
            st.info("👋 Primer registro.")

        # --- INPUTS ---
        st.markdown(f"#### Registrar Ejercicio Completo")
        c1, c2 = st.columns(2)
        peso = c1.number_input(f"Peso ({unit})", value=float(st.session_state.peso_input), step=2.5)
        reps = c2.number_input("Reps (por serie)", value=int(st.session_state.reps_input), step=1)
        
        c3, c4 = st.columns(2)
        series = c3.number_input("Cantidad de Series", value=int(st.session_state.series_input), step=1)
        rir = c4.selectbox("RIR (Reserva)", ["0", "1", "2", "3", "Suave"], index=1)
        notas = st.text_input("Notas del ejercicio", placeholder="Ej: Me costó la última serie...")

        if st.button("✅ GUARDAR EJERCICIO", type="primary"):
            try:
                peso_kg = convert_save(peso, modo_lb)
                vol_total = peso_kg * reps * series
                one_rm = round(peso_kg * (1 + (reps / 30)), 2)
                fecha_excel = datetime.now().strftime("%Y-%m-%d")
                
                row = [
                    fecha_excel, ej_seleccionado, peso_kg, series, reps, rir, 
                    one_rm, vol_total, notas, cat_seleccionada, dia_actual
                ]
                
                if save_data(row):
                    st.toast(f"¡Guardado! ({series} series | 1RM: {one_rm}kg)", icon="🔥")
                    get_data.clear()
            except Exception as e: st.error(f"Error: {e}")

# === VISUALIZACIÓN ===
with t2:
    if not df.empty:
        ej_g = st.selectbox("Analizar:", sorted(df["Ejercicio"].unique()))
        df_g = df[df["Ejercicio"] == ej_g].copy()
        if not df_g.empty:
            # GRÁFICA: 1RM vs Volumen
            df_day = df_g.groupby("Fecha").agg({"1RM_Estimado":"max", "Volumen":"sum"}).reset_index().sort_values("Fecha")
            
            c1, c2 = st.columns(2)
            with c1:
                fig1 = px.area(df_day, x="Fecha", y="1RM_Estimado", markers=True, title="<b>Fuerza Real (1RM Est.)</b>")
                fig1.update_traces(line_color="#FF4B4B", fillcolor="rgba(255, 75, 75, 0.2)")
                st.plotly_chart(fig1, use_container_width=True)
            with c2:
                fig2 = px.bar(df_day, x="Fecha", y="Volumen", title="<b>Volumen (Kilos Totales)</b>", color="Volumen", color_continuous_scale="RdBu_r")
                fig2.update_layout(coloraxis_showscale=False)
                st.plotly_chart(fig2, use_container_width=True)

with t3:
    if not df.empty:
        grupos = df.groupby(["Fecha", "Tipo_Sesion"]).size().reset_index().sort_values("Fecha", ascending=False)
        for _, row in grupos.iterrows():
            f = row["Fecha"]
            tipo = row["Tipo_Sesion"]
            with st.expander(f"📅 {f} - {tipo}"):
                d = df[(df["Fecha"] == f) & (df["Tipo_Sesion"] == tipo)]
                st.dataframe(d[["Ejercicio", "Peso_KG", "Series", "Reps", "RIR", "Notas"]], use_container_width=True, hide_index=True)