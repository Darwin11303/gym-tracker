import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="GYM TRACKER CLOUD", layout="wide", page_icon="☁️")

st.markdown("""
    <style>
    .main-header {text-align: center; font-family: 'Segoe UI', sans-serif;}
    .stButton>button {width: 100%; border-radius: 0px; font-weight: bold;}
    </style>
""", unsafe_allow_html=True)

st.markdown("<h1 class='main-header'>GYM TRACKER (CLOUD SYNC)</h1>", unsafe_allow_html=True)
st.markdown("---")

# --- CONEXIÓN INTELIGENTE CON GOOGLE SHEETS ---
SCOPE = ['https://www.googleapis.com/auth/spreadsheets', 
         'https://www.googleapis.com/auth/drive']

def conectar_google_sheets():
    try:
        # TRUCO DE INGENIERO: Obtenemos la ruta exacta de donde está ESTE archivo gym.py
        directorio_actual = os.path.dirname(os.path.abspath(__file__))
        ruta_json = os.path.join(directorio_actual, 'credentials.json')

        # 1. Intentamos cargar localmente usando la ruta absoluta
        if os.path.exists(ruta_json):
            # st.success(f"Archivo encontrado en: {ruta_json}") # Descomentar para depurar
            creds = ServiceAccountCredentials.from_json_keyfile_name(ruta_json, SCOPE)
        
        # 2. Si no, intentamos cargar desde la Nube (Secrets)
        else:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        
        client = gspread.authorize(creds)
        sheet = client.open("GymData").sheet1
        return sheet
        
    except Exception as e:
        st.error(f"⚠️ Error de conexión: {e}")
        # Mensaje de ayuda técnica
        directorio_actual = os.path.dirname(os.path.abspath(__file__))
        st.info(f"Buscando credenciales en: {os.path.join(directorio_actual, 'credentials.json')}")
        return None

# Función para cargar datos
def cargar_datos(sheet):
    if sheet is None:
        return pd.DataFrame(columns=["Fecha", "Ejercicio", "Peso_KG", "Series", "Reps", "RIR", "Notas"])
    try:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        # Convertir columnas a numérico
        cols_num = ["Peso_KG", "Series", "Reps"]
        for col in cols_num:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except:
        return pd.DataFrame(columns=["Fecha", "Ejercicio", "Peso_KG", "Series", "Reps", "RIR", "Notas"])

# Función para guardar
def guardar_datos(sheet, dataframe):
    if sheet is None:
        return
    if "Eliminar" in dataframe.columns:
        dataframe = dataframe.drop(columns=["Eliminar"])
    try:
        df_export = dataframe.copy()
        df_export["Fecha"] = df_export["Fecha"].astype(str)
        sheet.clear()
        sheet.update([df_export.columns.values.tolist()] + df_export.values.tolist())
    except Exception as e:
        st.error(f"Error al guardar: {e}")

# --- INICIALIZACIÓN ---
sheet = conectar_google_sheets()
df = cargar_datos(sheet)

# --- NAVEGACIÓN ---
tab_registro, tab_analisis, tab_gestion = st.tabs(["REGISTRO", "PROGRESO", "GESTION DE DATOS"])

# ==========================================
# TAB 1: REGISTRO
# ==========================================
with tab_registro:
    with st.container():
        st.subheader("NUEVA SESION")
        with st.form("form_registro", clear_on_submit=True):
            
            c1, c2 = st.columns(2)
            with c1:
                fecha = st.date_input("Fecha", datetime.now())
            with c2:
                lista_ejercicios = sorted(df["Ejercicio"].unique().tolist()) if not df.empty and "Ejercicio" in df.columns else []
                opcion_nueva = "CREAR NUEVO..."
                opciones = [opcion_nueva] + lista_ejercicios
                seleccion = st.selectbox("Ejercicio", options=opciones)
                
                ejercicio_final = seleccion
                if seleccion == opcion_nueva:
                    ejercicio_nuevo = st.text_input("Nombre del Ejercicio")
                    if ejercicio_nuevo:
                        ejercicio_final = ejercicio_nuevo.strip()

            c3, c4, c5, c6 = st.columns(4)
            with c3:
                peso = st.number_input("Peso (KG)", min_value=0.0, step=2.5, format="%.2f")
            with c4:
                series = st.number_input("Series", min_value=1, step=1, value=3)
            with c5:
                reps = st.number_input("Repeticiones", min_value=1, step=1, value=10)
            with c6:
                rir = st.selectbox("RIR", [0, 1, 2, 3, 4], index=2)
            notas = st.text_area("Observaciones", height=68)

            submitted = st.form_submit_button("GUARDAR EN LA NUBE ☁️")
            
            if submitted:
                if seleccion == opcion_nueva and not ejercicio_nuevo:
                    st.error("Error: Ingrese nombre del ejercicio.")
                else:
                    nuevo_registro = pd.DataFrame([{
                        "Fecha": str(fecha), "Ejercicio": ejercicio_final, 
                        "Peso_KG": peso, "Series": series, 
                        "Reps": reps, "RIR": rir, "Notas": notas
                    }])
                    df_actualizado = pd.concat([df, nuevo_registro], ignore_index=True)
                    guardar_datos(sheet, df_actualizado)
                    st.success(f"REGISTRO SINCRONIZADO: {ejercicio_final}")
                    st.rerun()

# ==========================================
# TAB 2 Y 3 
# ==========================================
with tab_analisis:
    if df.empty:
        st.info("Base de datos en Google Sheets vacía.")
    else:
        if "Ejercicio" in df.columns:
            col_sel, _ = st.columns([1, 2])
            with col_sel:
                ej_analisis = st.selectbox("Seleccionar Ejercicio", df["Ejercicio"].unique())
            
            df_filt = df[df["Ejercicio"] == ej_analisis].copy()
            df_filt["Fecha"] = pd.to_datetime(df_filt["Fecha"])
            df_filt = df_filt.sort_values("Fecha")
            
            st.line_chart(df_filt, x="Fecha", y="Peso_KG")
            st.dataframe(df_filt.sort_values("Fecha", ascending=False), use_container_width=True, hide_index=True)

with tab_gestion:
    st.header("CONTROL DE DATOS (NUBE)")
    if not df.empty:
        df_editor = df.copy()
        df_editor.insert(0, "Eliminar", False)
        
        df_resultado = st.data_editor(
            df_editor, num_rows="dynamic", use_container_width=True, key="editor_nube",
            column_config={"Eliminar": st.column_config.CheckboxColumn("Eliminar", default=False)}
        )
        
        if st.button("SINCRONIZAR CAMBIOS", type="primary"):
            df_limpio = df_resultado[df_resultado["Eliminar"] == False].copy()
            guardar_datos(sheet, df_limpio)
            st.success("Google Sheets actualizado.")
            st.rerun()