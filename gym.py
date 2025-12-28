import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import os
import plotly.express as px

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="GYM TRACKER PRO", layout="wide", page_icon="💪")

# Estilos CSS personalizados
st.markdown("""
    <style>
    .big-font {font-size:20px !important; font-weight: bold;}
    .success-box {padding:10px; border-radius:5px; background-color:#d4edda; color:#155724;}
    .info-box {padding:10px; border-radius:5px; background-color:#cce5ff; color:#004085;}
    </style>
""", unsafe_allow_html=True)

st.title("💪 GYM TRACKER (CLOUD SYSTEM)")

# --- 1. CAPA DE CONEXIÓN (BLINDADA CON CACHÉ) ---
# Usamos cache_resource para la conexión (se mantiene viva entre recargas)
@st.cache_resource
def conectar_google_sheets():
    SCOPE = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    try:
        directorio_actual = os.path.dirname(os.path.abspath(__file__))
        ruta_json = os.path.join(directorio_actual, 'credentials.json')

        if os.path.exists(ruta_json):
            creds = ServiceAccountCredentials.from_json_keyfile_name(ruta_json, SCOPE)
        else:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        
        client = gspread.authorize(creds)
        sheet = client.open("GymData").sheet1
        return sheet
    except Exception as e:
        st.error(f"⚠️ Error Crítico de Conexión: {e}")
        return None

# Usamos cache_data para los DATOS (se refresca solo cuando guardamos)
@st.cache_data(ttl=60) # ttl=60 significa que si no haces nada, se refresca cada 60 segs max
def cargar_datos_con_cache():
    sheet = conectar_google_sheets()
    if sheet:
        try:
            data = sheet.get_all_records()
            if not data: return pd.DataFrame()
            df = pd.DataFrame(data)
            # Limpieza de tipos
            cols_num = ["Peso_KG", "Series", "Reps", "1RM_Estimado", "Volumen"]
            for col in cols_num:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            # Asegurar formato fecha
            if "Fecha" in df.columns:
                df["Fecha"] = pd.to_datetime(df["Fecha"]).dt.date
            return df
        except Exception as e:
            st.warning(f"La hoja existe pero está vacía o tiene formato incorrecto: {e}")
            return pd.DataFrame()
    return pd.DataFrame()

# Función para borrar caché y recargar (usar después de guardar)
def limpiar_cache():
    cargar_datos_con_cache.clear()

# --- 2. LÓGICA DE NEGOCIO (INGENIERÍA) ---

def calcular_1rm(peso, reps):
    # Fórmula de Epley: Peso * (1 + (Reps / 30))
    if reps == 0: return 0
    if reps == 1: return peso
    return round(peso * (1 + (reps / 30)), 2)

def convertir_peso(valor, unidad_entrada):
    if unidad_entrada == "Libras (Lb)":
        return round(valor * 0.453592, 2) # Guarda siempre en KG
    return valor

def guardar_registro(fecha, ejercicio, peso_kg, series, reps, rir, notas):
    sheet = conectar_google_sheets()
    if sheet:
        rm_estimado = calcular_1rm(peso_kg, reps)
        volumen_total = series * reps * peso_kg
        
        nuevo_dato = [
            str(fecha), ejercicio, peso_kg, series, reps, rir, 
            rm_estimado, volumen_total, notas
        ]
        
        # Añadir fila al final
        sheet.append_row(nuevo_dato)
        limpiar_cache() # Importante: Obliga a recargar los datos nuevos
        return True
    return False

# --- 3. INTERFAZ DE USUARIO ---

# Cargar datos iniciales
df = cargar_datos_con_cache()

# SIDEBAR DE CONFIGURACIÓN
with st.sidebar:
    st.header("⚙️ Configuración")
    unidad_pref = st.radio("Unidad de Entrada:", ["Kilogramos (Kg)", "Libras (Lb)"])
    if st.button("🔄 Forzar Actualización de Datos"):
        limpiar_cache()
        st.rerun()
    st.info("Nota: La base de datos siempre guarda en KG para mantener consistencia.")

# TABS PRINCIPALES
tab_log, tab_dash, tab_analisis, tab_data = st.tabs(["📝 REGISTRO INTELIGENTE", "📅 DASHBOARD", "📈 ANÁLISIS PRO", "💾 DATOS"])

# === TAB 1: REGISTRO INTELIGENTE ===
with tab_log:
    col_main, col_info = st.columns([2, 1])
    
    with col_main:
        st.subheader("Nuevo Entrenamiento")
        with st.form("gym_form", clear_on_submit=True):
            c_date, c_ex = st.columns([1, 2])
            fecha = c_date.date_input("Fecha", datetime.now())
            
            # Lista de ejercicios
            lista_ej = sorted(df["Ejercicio"].unique().tolist()) if not df.empty and "Ejercicio" in df.columns else []
            ejercicio = c_ex.selectbox("Ejercicio", ["Crear Nuevo..."] + lista_ej)
            
            if ejercicio == "Crear Nuevo...":
                ejercicio = st.text_input("Escribe el nombre del ejercicio").strip().upper()
            
            # Inputs Numéricos
            c_peso, c_series, c_reps, c_rir = st.columns(4)
            peso_input = c_peso.number_input(f"Peso ({'Lbs' if 'Lb' in unidad_pref else 'Kg'})", min_value=0.0, step=2.5)
            series = c_series.number_input("Series", 1, 10, 3)
            reps = c_reps.number_input("Reps", 1, 50, 10)
            rir = c_rir.selectbox("RIR (Reps en reserva)", [0, 1, 2, 3, 4, "Fallo"], index=2)
            
            notas = st.text_area("Notas / Sensaciones", height=80)
            
            enviar = st.form_submit_button("🔥 REGISTRAR SERIE", type="primary")
            
            if enviar:
                if not ejercicio:
                    st.error("Falta el nombre del ejercicio")
                else:
                    # Lógica de conversión
                    peso_real_kg = convertir_peso(peso_input, unidad_pref)
                    
                    with st.spinner("Sincronizando con la nube..."):
                        exito = guardar_registro(fecha, ejercicio, peso_real_kg, series, reps, rir, notas)
                        if exito:
                            st.success(f"✅ Guardado: {ejercicio} | {peso_real_kg} Kg")
                            st.rerun()

    # PANEL LATERAL: SOBRECARGA PROGRESIVA (Memoria de Pez)
    with col_info:
        st.markdown("### 🧠 Última vez...")
        if not df.empty and ejercicio != "Crear Nuevo..." and ejercicio:
            # Buscar último registro de este ejercicio
            historial_ej = df[df["Ejercicio"] == ejercicio].sort_values("Fecha", ascending=False)
            if not historial_ej.empty:
                ultimo = historial_ej.iloc[0]
                delta_dias = (datetime.now().date() - ultimo["Fecha"]).days
                
                st.markdown(f"""
                <div class='info-box'>
                    <b>📅 Hace {delta_dias} días</b><br>
                    ⚖️ <b>Peso:</b> {ultimo['Peso_KG']} Kg<br>
                    🔁 <b>Reps:</b> {ultimo['Reps']} (x{ultimo['Series']})<br>
                    🔥 <b>1RM Est:</b> {ultimo.get('1RM_Estimado', 0)} Kg
                </div>
                """, unsafe_allow_html=True)
                
                if pd.notna(ultimo['Notas']) and ultimo['Notas']:
                    st.caption(f"📝 Nota anterior: {ultimo['Notas']}")
            else:
                st.info("Primer registro de este ejercicio.")
        else:
            st.markdown("Selecciona un ejercicio para ver tu historial reciente.")

# === TAB 2: DASHBOARD (CALENDARIO Y BLOQUES) ===
with tab_dash:
    if df.empty:
        st.warning("No hay datos aún.")
    else:
        # 1. HEATMAP DE ENTRENAMIENTOS (Calendario)
        st.subheader("🔥 Constancia (Días Entrenados)")
        df_cal = df[["Fecha"]].drop_duplicates()
        df_cal["Entrenos"] = 1
        
        # Usamos Plotly para un calendario visual
        fig_cal = px.scatter(df_cal, x="Fecha", y="Entrenos", size="Entrenos", 
                             color_discrete_sequence=["#00CC96"], title="Días Activos")
        fig_cal.update_layout(yaxis_visible=False, height=200, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig_cal, use_container_width=True)

        st.divider()

        # 2. HISTORIAL POR BLOQUES (Últimos 3 vs Todos)
        st.subheader("📚 Historial de Sesiones")
        
        ver_todos = st.checkbox("Ver todo el historial")
        
        # Agrupar por fecha (Sesiones)
        fechas_unicas = sorted(df["Fecha"].unique(), reverse=True)
        
        fechas_a_mostrar = fechas_unicas if ver_todos else fechas_unicas[:3]
        
        for fecha in fechas_a_mostrar:
            with st.expander(f"📅 SESIÓN: {fecha} ({datetime.strftime(fecha, '%A')})"):
                df_dia = df[df["Fecha"] == fecha]
                
                # Mostrar tabla limpia
                st.dataframe(
                    df_dia[["Ejercicio", "Peso_KG", "Series", "Reps", "1RM_Estimado", "Notas"]],
                    use_container_width=True,
                    hide_index=True
                )
                
                # Resumen de volumen del día
                vol_dia = df_dia["Volumen"].sum()
                st.caption(f"⚡ Volumen Total del día: {vol_dia:,.0f} Kg movidos")

# === TAB 3: ANÁLISIS PRO ===
with tab_analisis:
    st.subheader("📈 Análisis de Progreso")
    if not df.empty:
        ejercicios_disponibles = sorted(df["Ejercicio"].unique())
        ej_sel = st.selectbox("Analizar Ejercicio:", ejercicios_disponibles)
        
        df_chart = df[df["Ejercicio"] == ej_sel].sort_values("Fecha")
        
        if not df_chart.empty:
            metrica = st.radio("Métrica a visualizar:", ["Peso_KG", "1RM_Estimado", "Volumen"], horizontal=True)
            
            # Gráfica interactiva con Plotly
            fig = px.line(df_chart, x="Fecha", y=metrica, markers=True, 
                          title=f"Progresión de {metrica} en {ej_sel}",
                          line_shape="spline") # Línea suavizada
            
            # Añadir línea de tendencia
            fig.add_scatter(x=df_chart["Fecha"], y=df_chart[metrica].rolling(window=3).mean(), 
                            mode='lines', name='Tendencia (Media móvil)', line=dict(dash='dot', color='gray'))

            st.plotly_chart(fig, use_container_width=True)
            
            # Tabla de Récords
            max_peso = df_chart["Peso_KG"].max()
            max_1rm = df_chart["1RM_Estimado"].max()
            st.success(f"🏆 Récord Histórico: {max_peso} Kg | Mejor 1RM Estimado: {max_1rm} Kg")

# === TAB 4: GESTIÓN DE DATOS ===
with tab_data:
    st.warning("⚠️ Zona de Edición Directa")
    if not df.empty:
        df_edit = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="data_editor")
        
        if st.button("💾 GUARDAR CAMBIOS MASIVOS EN LA NUBE"):
            sheet = conectar_google_sheets()
            if sheet:
                try:
                    # Convertir fechas a string antes de subir
                    df_subida = df_edit.copy()
                    df_subida["Fecha"] = df_subida["Fecha"].astype(str)
                    
                    sheet.clear()
                    sheet.update([df_subida.columns.values.tolist()] + df_subida.values.tolist())
                    limpiar_cache()
                    st.success("Base de datos actualizada correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar: {e}")