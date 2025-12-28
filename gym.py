import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import time  # <--- ESTO FALTABA (Arregla el error de la línea 253)
import plotly.express as px

# --- 1. CONFIGURACIÓN VISUAL (LIMPIA) ---
st.set_page_config(page_title="GYM TRACKER", layout="wide", page_icon="🏋️")

# Estilos CSS
st.markdown("""
    <style>
    .big-font {font-size:18px !important; font-weight: bold;}
    .metric-box {padding:15px; border-radius:10px; background-color:#f0f2f6; text-align:center;}
    </style>
""", unsafe_allow_html=True)

st.title("🏋️ GYM TRACKER")

# --- 2. MOTOR DE CONEXIÓN Y DATOS (BLINDADO) ---
@st.cache_resource
def conectar_google_sheets():
    SCOPE = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    try:
        # Prioridad: Archivo Local -> Secretos Nube
        if os.path.exists('credentials.json'):
            creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', SCOPE)
        else:
            creds_dict = st.secrets["gcp_service_account"]
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        
        client = gspread.authorize(creds)
        return client.open("GymData").sheet1
    except Exception as e:
        st.error(f"🔥 Error de conexión: {e}")
        return None

@st.cache_data(ttl=60)
def cargar_datos_seguros():
    sheet = conectar_google_sheets()
    if not sheet: return pd.DataFrame()
    
    try:
        data = sheet.get_all_records()
        if not data: return pd.DataFrame()
        
        df = pd.DataFrame(data)
        
        # --- ARREGLO DE FECHAS DEFINITIVO ---
        if "Fecha" in df.columns:
            # 1. Convertir a texto para uniformizar
            df["Fecha"] = df["Fecha"].astype(str)
            # 2. Usar 'mixed' y 'dayfirst' para que entienda 28/12/2025 y 2025-12-28
            df["Fecha"] = pd.to_datetime(df["Fecha"], format='mixed', dayfirst=True, errors='coerce').dt.date
            # 3. Borrar fechas inválidas
            df = df.dropna(subset=["Fecha"])
            
        # Asegurar Columnas Numéricas
        cols_num = ["Peso_KG", "Series", "Reps", "1RM_Estimado", "Volumen"]
        for col in cols_num:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
        return df
    except Exception:
        return pd.DataFrame()

def limpiar_cache():
    cargar_datos_seguros.clear()

# --- 3. LÓGICA DE GIMNASIO ---
def calcular_metricas(peso, series, reps):
    # 1RM Epley
    rm = round(peso * (1 + (reps / 30)), 2) if reps > 1 else peso
    vol = round(series * reps * peso, 2)
    return rm, vol

def guardar_entreno(fecha, ejercicio, peso, series, reps, rir, notas):
    sheet = conectar_google_sheets()
    if sheet:
        rm, vol = calcular_metricas(peso, series, reps)
        fila = [str(fecha), ejercicio, peso, series, reps, rir, rm, vol, notas]
        sheet.append_row(fila)
        limpiar_cache()
        return True
    return False

# --- 4. INTERFAZ DE USUARIO ---
df = cargar_datos_seguros()

# Configuración lateral
with st.sidebar:
    st.header("⚙️ Ajustes")
    modo_lb = st.toggle("Usar Libras (Lb)", value=False)
    if st.button("🔄 Recargar Datos"):
        limpiar_cache()
        st.rerun()

# TABS PRINCIPALES
tab1, tab2, tab3, tab4 = st.tabs(["📝 REGISTRO", "📅 DASHBOARD", "📈 ANÁLISIS", "💾 DATOS"])

# === TAB 1: REGISTRO ===
with tab1:
    col_form, col_last = st.columns([1.5, 1])
    
    with col_form:
        st.subheader("Nueva Sesión")
        with st.form("form_gym", clear_on_submit=True):
            c1, c2 = st.columns([1, 2])
            fecha_input = c1.date_input("Fecha", datetime.now())
            
            # Selector de ejercicios
            lista_ejercicios = sorted(df["Ejercicio"].unique()) if not df.empty and "Ejercicio" in df.columns else []
            ejercicio_sel = c2.selectbox("Ejercicio", ["Crear Nuevo..."] + lista_ejercicios)
            
            ejercicio_nombre = ejercicio_sel
            if ejercicio_sel == "Crear Nuevo...":
                ejercicio_nombre = st.text_input("Nombre del Ejercicio").strip().upper()
            
            # Inputs
            cc1, cc2, cc3, cc4 = st.columns(4)
            label_peso = "Peso (LB)" if modo_lb else "Peso (KG)"
            input_peso = cc1.number_input(label_peso, min_value=0.0, step=2.5)
            input_series = cc2.number_input("Series", 1, 10, 3)
            input_reps = cc3.number_input("Reps", 1, 50, 10)
            input_rir = cc4.selectbox("RIR", [0, 1, 2, 3, 4, "Fallo"], index=2)
            
            input_notas = st.text_area("Notas", height=80, placeholder="Sensaciones...")
            
            btn_guardar = st.form_submit_button("🔥 GUARDAR SERIE", type="primary")
            
            if btn_guardar:
                if not ejercicio_nombre:
                    st.error("Escribe un nombre para el ejercicio")
                else:
                    peso_final = round(input_peso * 0.453592, 2) if modo_lb else input_peso
                    if guardar_entreno(fecha_input, ejercicio_nombre, peso_final, input_series, input_reps, input_rir, input_notas):
                        st.success(f"✅ Guardado: {ejercicio_nombre} ({peso_final} Kg)")
                        time.sleep(1) # Ahora sí funcionará porque importamos time
                        st.rerun()
    
    with col_last:
        st.markdown("### 🧠 Memoria")
        valid_ej = ejercicio_sel != "Crear Nuevo..." and not df.empty and "Ejercicio" in df.columns
        if valid_ej:
            historial = df[df["Ejercicio"] == ejercicio_sel]
            if not historial.empty:
                ultima_fecha = historial["Fecha"].max()
                ultima_sesion = historial[historial["Fecha"] == ultima_fecha]
                mejor_set = ultima_sesion.loc[ultima_sesion["Peso_KG"].idxmax()]
                
                dias_pasados = (datetime.now().date() - ultima_fecha).days
                st.info(f"📅 Hace {dias_pasados} días ({ultima_fecha})")
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Peso", f"{mejor_set['Peso_KG']} Kg")
                m2.metric("Reps", f"{mejor_set['Reps']}")
                m3.metric("Series", f"{mejor_set['Series']}")
                
                if pd.notna(mejor_set['Notas']) and str(mejor_set['Notas']).strip() != "":
                    st.caption(f"📝 Nota: {mejor_set['Notas']}")
                st.markdown(f"**1RM Est:** {mejor_set.get('1RM_Estimado', 0)} Kg")
            else:
                st.markdown("🔹 Primer registro.")
        else:
            st.markdown("Selecciona un ejercicio.")

# === TAB 2: DASHBOARD ===
with tab2:
    if df.empty:
        st.info("Registra datos para ver el dashboard.")
    else:
        df_cal = df[["Fecha"]].drop_duplicates()
        df_cal["Actividad"] = 1
        fig_cal = px.scatter(df_cal, x="Fecha", y="Actividad", size="Actividad", 
                             title="Constancia", color_discrete_sequence=["#2bd95d"])
        fig_cal.update_layout(yaxis_visible=False, height=200)
        st.plotly_chart(fig_cal, use_container_width=True)
        
        st.divider()
        st.subheader("📚 Últimas Sesiones")
        
        cols_deseadas = ["Ejercicio", "Peso_KG", "Series", "Reps", "1RM_Estimado", "Notas"]
        cols_seguras = [c for c in cols_deseadas if c in df.columns]
        
        fechas_unicas = sorted(df["Fecha"].unique(), reverse=True)
        for f in fechas_unicas[:3]:
            with st.expander(f"📅 {f}"):
                df_day = df[df["Fecha"] == f]
                st.dataframe(df_day[cols_seguras], use_container_width=True, hide_index=True)

# === TAB 3: ANÁLISIS ===
with tab3:
    st.subheader("📈 Progreso")
    if not df.empty and "Ejercicio" in df.columns:
        ej_analisis = st.selectbox("Analizar:", sorted(df["Ejercicio"].unique()), key="sb_analisis")
        df_chart = df[df["Ejercicio"] == ej_analisis].sort_values("Fecha")
        
        if not df_chart.empty:
            fig = px.line(df_chart, x="Fecha", y="1RM_Estimado", markers=True, 
                          title=f"Fuerza Real (1RM) - {ej_analisis}", line_shape="spline")
            st.plotly_chart(fig, use_container_width=True)
            
            c1, c2 = st.columns(2)
            c1.metric("Peso Máximo", f"{df_chart['Peso_KG'].max()} Kg")
            c2.metric("Volumen Total", f"{df_chart['Volumen'].sum():,.0f} Kg")

# === TAB 4: DATOS ===
with tab4:
    st.warning("⚠️ Edición directa")
    if not df.empty:
        df_edit = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="editor_db")
        if st.button("💾 GUARDAR CAMBIOS MASIVOS"):
            sheet = conectar_google_sheets()
            if sheet:
                try:
                    df_final = df_edit.copy()
                    df_final["Fecha"] = df_final["Fecha"].astype(str)
                    sheet.clear()
                    sheet.update([df_final.columns.values.tolist()] + df_final.values.tolist())
                    limpiar_cache()
                    st.success("✅ Actualizado")
                    time.sleep(1) # Ahora sí funcionará
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")