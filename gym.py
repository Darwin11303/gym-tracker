import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
import time
import numpy as np

# --- 1. CONFIGURACIÓN DEL SISTEMA (System Setup) ---
st.set_page_config(page_title="Darwin Gym OS v4", page_icon="🧬", layout="wide")

# --- 2. ESTILOS CSS (Professional UI) ---
st.markdown("""
    <style>
    /* Global Dark Theme Corrections */
    .stApp { background-color: #0E1117; }
    
    /* Botones Profesionales */
    .stButton>button { 
        width: 100%; border-radius: 6px; font-weight: 600; 
        border: 1px solid #303030; background-color: #1E1E1E; color: #EEE;
        transition: all 0.2s;
    }
    .stButton>button:hover { 
        border-color: #FF4B4B; color: #FF4B4B; background-color: #262626; 
    }
    
    /* Tarjetas de Métricas (KPIs) */
    .kpi-card {
        background: linear-gradient(135deg, #1e1e1e, #2a2a2a);
        padding: 15px; border-radius: 10px;
        border-left: 4px solid #FF4B4B;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2);
        margin-bottom: 10px;
        text-align: center;
    }
    .kpi-val { font-size: 1.8rem; font-weight: 800; color: #FFF; }
    .kpi-lbl { font-size: 0.8rem; color: #BBB; text-transform: uppercase; letter-spacing: 1px; }

    /* Tarjeta de Historial (Contexto) */
    .history-box {
        background-color: #131720; border: 1px solid #333;
        padding: 15px; border-radius: 8px; margin-bottom: 15px;
    }
    
    /* Alertas y Utilidades */
    .warmup-box { background: #0f291e; color: #4ade80; padding: 10px; border-radius: 6px; border: 1px solid #14532d; font-size: 0.9rem; margin-top: 10px; }
    .alert-stale { background: #422006; color: #facc15; padding: 10px; border-radius: 6px; border: 1px solid #a16207; font-weight: bold; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- 3. GESTIÓN DE DATOS (Backend) ---
@st.cache_resource
def get_client():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"❌ Error de Autenticación: {e}")
        return None

def get_data_sheets():
    client = get_client()
    if not client: return None, None
    try:
        sh = client.open("GymData")
        ws_logs = sh.sheet1 
        try:
            ws_config = sh.worksheet("Config_Rutinas")
        except:
            # Inicialización automática si no existe
            ws_config = sh.add_worksheet(title="Config_Rutinas", rows="200", cols="5")
            ws_config.append_row(["Rutina", "Orden", "Ejercicio"])
            # Cargar defaults V9.0 Turbo
            defaults = [
                ["PUSH A", 1, "PRESS BANCA MANCUERNAS"], ["PUSH A", 2, "PRESS MILITAR DE PIE"], 
                ["PUSH A", 3, "HEX PRESS"], ["PUSH A", 4, "ELEVACIONES LATERALES"],
                ["PUSH A", 5, "EXT. TRICEPS POLEA"], ["PUSH A", 6, "TRICEPS TRAS NUCA"], ["PUSH A", 7, "FACE PULLS"],
                ["PULL A", 1, "DOMINADAS"], ["PULL A", 2, "REMO POLEA BAJA"], ["PULL A", 3, "PULLOVER POLEA"],
                ["PULL A", 4, "PAJAROS MAQUINA"], ["PULL A", 5, "CURL BARRA"], ["PULL A", 6, "CURL MARTILLO"],
                ["LEGS A", 1, "SENTADILLA"], ["LEGS A", 2, "PRENSA PIERNAS"], ["LEGS A", 3, "CURL FEMORAL SENTADO"],
                ["LEGS A", 4, "EXTENSION CUADRICEPS"], ["LEGS A", 5, "ELEVACION TALONES"],
                ["PUSH B", 1, "PRESS INCLINADO MANCUERNAS"], ["PUSH B", 2, "APERTURAS"], ["PUSH B", 3, "PRESS MILITAR SENTADO"],
                ["PUSH B", 4, "ELEVACIONES LATERAL POLEA"], ["PUSH B", 5, "TRICEPS POLEA BARRA"], ["PUSH B", 6, "FACE PULLS"],
                ["PULL B", 1, "REMO SERRUCHO"], ["PULL B", 2, "JALON AL PECHO MAG GRIP"], ["PULL B", 3, "FACE PULLS (PESADO)"],
                ["PULL B", 4, "CURL PREDICADOR"], ["PULL B", 5, "CURL BAYESIANO"],
                ["LEGS B", 1, "ZANCADAS"], ["LEGS B", 2, "HIP THRUST"], ["LEGS B", 3, "PRENSA (PIES ALTOS)"],
                ["LEGS B", 4, "CURL FEMORAL TUMBADO"], ["LEGS B", 5, "GEMELO SENTADO"]
            ]
            for d in defaults: ws_config.append_row(d)
        return ws_logs, ws_config
    except Exception as e:
        st.error(f"❌ Error conectando a Sheets: {e}")
        return None, None

def load_dataframes():
    ws_logs, ws_config = get_data_sheets()
    if not ws_logs: return pd.DataFrame(), pd.DataFrame()
    
    # Logs (Historial)
    df_logs = pd.DataFrame(ws_logs.get_all_records())
    if not df_logs.empty:
        # Limpieza de tipos
        if "Fecha" in df_logs.columns:
            df_logs["Fecha"] = pd.to_datetime(df_logs["Fecha"], errors='coerce').dt.date
        cols_num = ["Peso_KG", "Reps", "RIR", "1RM_Estimado", "Volumen", "Series"]
        for c in cols_num: 
            if c in df_logs.columns: df_logs[c] = pd.to_numeric(df_logs[c], errors='coerce').fillna(0)
    
    # Config (Rutinas)
    df_config = pd.DataFrame(ws_config.get_all_records())
    
    return df_logs, df_config

# --- 4. FUNCIONES "ENTRENADOR INTELIGENTE" ---
def calcular_calentamiento(peso_objetivo):
    """Retorna tuplas (peso, reps) para calentar"""
    w1 = round(peso_objetivo * 0.50, 1)
    w2 = round(peso_objetivo * 0.75, 1)
    return w1, w2

def detectar_estancamiento(df, ejercicio):
    """Retorna True si el 1RM no ha subido en las últimas 3 sesiones"""
    if df.empty or ejercicio not in df["Ejercicio"].values: return False
    hist = df[df["Ejercicio"] == ejercicio].sort_values("Fecha", ascending=False)
    # Agrupar por fecha para obtener el mejor 1RM de cada día
    daily_max = hist.groupby("Fecha")["1RM_Estimado"].max().sort_index(ascending=False).head(3)
    
    if len(daily_max) < 3: return False
    
    # Si el max de hoy es <= al de hace 2 sesiones
    return daily_max.iloc[0] <= daily_max.iloc[2]

# --- 5. INTERFAZ PRINCIPAL ---
def main():
    if 'buffer_series' not in st.session_state: st.session_state.buffer_series = []
    
    df_logs, df_config = load_dataframes()
    
    # --- SIDEBAR (Panel de Control) ---
    st.sidebar.title("🧬 Gym OS v4.0")
    st.sidebar.markdown("<div style='font-size:0.8rem; color:#888; margin-bottom:20px;'>Sistema de Ingeniería Corporal</div>", unsafe_allow_html=True)
    
    modo_lb = st.sidebar.toggle("Modo Libras (LB)", value=True)
    factor = 2.20462 if modo_lb else 1.0
    suffix = "lb" if modo_lb else "kg"
    
    # --- PESTAÑAS PRINCIPALES ---
    tab_train, tab_stats, tab_edit = st.tabs(["🔥 ENTRENAR", "📊 PROGRESO", "🛠️ EDITOR RUTINAS"])

    # =========================================================================
    # TAB 1: ZONA DE ENTRENAMIENTO (Logging)
    # =========================================================================
    with tab_train:
        # 1. Selector de Rutina (Auto-rotación)
        rutinas_disponibles = sorted(df_config["Rutina"].unique()) if not df_config.empty else ["PUSH A"]
        rutina_default_idx = 0
        
        # Algoritmo de predicción de rutina
        if not df_logs.empty and "Tipo_Sesion" in df_logs.columns:
            last_type = df_logs.sort_values("Fecha", ascending=False).iloc[0]["Tipo_Sesion"]
            try:
                # Intenta encontrar la siguiente en la lista ordenada
                orden_logico = ["PUSH A", "PULL A", "LEGS A", "PUSH B", "PULL B", "LEGS B"]
                if last_type in orden_logico:
                    next_r = orden_logico[(orden_logico.index(last_type) + 1) % len(orden_logico)]
                    if next_r in rutinas_disponibles:
                        rutina_default_idx = rutinas_disponibles.index(next_r)
            except: pass

        c_rut, c_ej = st.columns([1, 2])
        with c_rut:
            rutina_hoy = st.selectbox("Rutina de Hoy:", rutinas_disponibles, index=rutina_default_idx)
        
        # 2. Selector de Ejercicio (Filtrado)
        ejercicios_hoy = df_config[df_config["Rutina"] == rutina_hoy].sort_values("Orden")["Ejercicio"].tolist()
        if not ejercicios_hoy: ejercicios_hoy = ["SIN EJERCICIOS"]
        
        with c_ej:
            ejercicio_actual = st.selectbox("Seleccionar Ejercicio:", ejercicios_hoy)

        # Limpiar buffer si cambiamos de ejercicio
        if 'last_ej' not in st.session_state or st.session_state.last_ej != ejercicio_actual:
            st.session_state.buffer_series = []
            st.session_state.last_ej = ejercicio_actual

        st.divider()

        # 3. Panel de Datos e Input
        col_context, col_input = st.columns([1, 1.5])
        
        with col_context: # === CEREBRO (Datos Históricos) ===
            st.markdown("##### 📡 Datos Previos")
            if not df_logs.empty and ejercicio_actual in df_logs["Ejercicio"].values:
                # Obtener historial del ejercicio
                hist = df_logs[df_logs["Ejercicio"] == ejercicio_actual].sort_values("Fecha", ascending=False)
                last_sesion_date = hist.iloc[0]["Fecha"]
                last_sesion_data = hist[hist["Fecha"] == last_sesion_date]
                
                # Mejor serie de la última vez (Mayor 1RM)
                best_idx = last_sesion_data["1RM_Estimado"].idxmax()
                best_set = last_sesion_data.loc[best_idx]
                
                # Setup Notes
                nota_setup = best_set["Notas"] if str(best_set["Notas"]) not in ["nan", ""] else "Sin notas registradas."
                
                # Display
                p_display = round(best_set['Peso_KG'] * factor, 1)
                
                st.markdown(f"""
                <div class="history-box">
                    <div style="color:#888; font-size:0.85rem;">ÚLTIMA SESIÓN ({last_sesion_date})</div>
                    <div style="font-size:2rem; font-weight:800; color:#FFF;">{p_display} <span style="font-size:1rem; color:#FF4B4B;">{suffix}</span></div>
                    <div style="font-size:1.1rem; color:#DDD;">x {int(best_set['Reps'])} reps <span style="background:#333; padding:2px 6px; border-radius:4px; font-size:0.8rem;">RIR {best_set['RIR']}</span></div>
                    <div style="margin-top:10px; padding-top:8px; border-top:1px solid #333; font-style:italic; font-size:0.9rem; color:#BBB;">
                        "{nota_setup}"
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Alerta de Estancamiento
                if detecting_estancamiento := detectar_estancamiento(df_logs, ejercicio_actual):
                     st.markdown('<div class="alert-stale">⚠️ ALERTA DE ESTANCAMIENTO<br><span style="font-weight:normal; font-size:0.85rem">Llevas 3 sesiones sin subir 1RM. Hoy intenta subir peso o reps.</span></div>', unsafe_allow_html=True)
                
                # Calculadora Smart
                with st.expander("🌡️ Calentamiento Automático"):
                    w1, w2 = calcular_calentamiento(p_display)
                    st.markdown(f"""
                    <div class="warmup-box">
                        1️⃣ <b>12 reps</b> con {w1} {suffix}<br>
                        2️⃣ <b>4 reps</b> con {w2} {suffix} (Explosivo)
                    </div>
                    """, unsafe_allow_html=True)

            else:
                st.info("🆕 Primer registro para este ejercicio.")

        with col_input: # === INPUT (Registro) ===
            st.markdown(f"##### 📝 Registrar Series")
            
            ic1, ic2, ic3 = st.columns(3)
            p_in = ic1.number_input(f"Peso ({suffix})", step=2.5, min_value=0.0)
            r_in = ic2.number_input("Reps", step=1, value=10, min_value=0)
            rir_in = ic3.selectbox("RIR", [0, 1, 2, 3, 4], index=1)
            
            if st.button("➕ Añadir Serie", use_container_width=True):
                if p_in > 0:
                    st.session_state.buffer_series.append({
                        "Peso_KG": p_in / factor, "Peso_Display": p_in,
                        "Reps": r_in, "RIR": rir_in
                    })
                else:
                    st.toast("⚠️ El peso debe ser mayor a 0")
            
            # Visualizar Buffer
            if st.session_state.buffer_series:
                st.write("---")
                st.markdown("**Series Acumuladas:**")
                for i, s in enumerate(st.session_state.buffer_series):
                    st.caption(f"🔘 **Serie {i+1}:** {s['Peso_Display']} {suffix} x {s['Reps']} (RIR {s['RIR']})")
                
                notas_in = st.text_input("Notas Técnicas / Sensaciones:", placeholder="Ej: Me costó estabilizar, subir peso la próxima...")
                
                if st.button("💾 GUARDAR EJERCICIO", type="primary"):
                    ws_logs, _ = get_data_sheets()
                    rows_to_save = []
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    
                    for i, s in enumerate(st.session_state.buffer_series):
                        kg = s['Peso_KG']
                        reps = s['Reps']
                        # Epley Formula para 1RM
                        onerm = kg * (1 + (reps / 30))
                        vol = kg * reps
                        
                        # [Fecha, Ejercicio, Peso_KG, Reps, RIR, 1RM, Volumen, Notas, Rutina, Serie]
                        rows_to_save.append([
                            today_str, ejercicio_actual, kg, reps, s['RIR'],
                            round(onerm, 2), round(vol, 2), notas_in, rutina_hoy, i+1
                        ])
                    
                    ws_logs.append_rows(rows_to_save)
                    st.toast(f"✅ {ejercicio_actual} guardado con éxito.", icon="🚀")
                    st.session_state.buffer_series = [] # Reset
                    time.sleep(1)
                    st.rerun()

    # =========================================================================
    # TAB 2: ANALYTICS (EL CEREBRO VISUAL) - NUEVO!
    # =========================================================================
    with tab_stats:
        st.header("📈 Centro de Análisis")
        
        if df_logs.empty:
            st.warning("Necesitas registrar datos para ver gráficas.")
        else:
            # --- FILTROS ---
            col_f1, col_f2 = st.columns(2)
            lista_ej_stats = sorted(df_logs["Ejercicio"].unique())
            ej_stat_sel = col_f1.selectbox("Analizar Ejercicio:", lista_ej_stats)
            
            # --- PREPARAR DATOS ---
            df_ej = df_logs[df_logs["Ejercicio"] == ej_stat_sel].copy()
            df_ej["Fecha"] = pd.to_datetime(df_ej["Fecha"])
            
            # Agrupar por día (Max 1RM del día y Suma de Volumen)
            df_day = df_ej.groupby("Fecha").agg({
                "1RM_Estimado": "max",
                "Volumen": "sum",
                "Peso_KG": "max"
            }).reset_index().sort_values("Fecha")
            
            # Calcular KPIs
            max_1rm_ever = df_day["1RM_Estimado"].max() * factor
            vol_total_ever = df_day["Volumen"].sum() * factor
            record_peso = df_day["Peso_KG"].max() * factor
            
            # --- KPIs VISUALES ---
            k1, k2, k3 = st.columns(3)
            k1.markdown(f"<div class='kpi-card'><div class='kpi-val'>{round(max_1rm_ever, 1)} {suffix}</div><div class='kpi-lbl'>RÉCORD DE FUERZA (1RM)</div></div>", unsafe_allow_html=True)
            k2.markdown(f"<div class='kpi-card'><div class='kpi-val'>{round(record_peso, 1)} {suffix}</div><div class='kpi-lbl'>PESO MÁXIMO MOVIDO</div></div>", unsafe_allow_html=True)
            k3.markdown(f"<div class='kpi-card'><div class='kpi-val'>{int(vol_total_ever/1000)} k</div><div class='kpi-lbl'>TONELAJE ACUMULADO</div></div>", unsafe_allow_html=True)

            # --- GRÁFICA 1: PROGRESO DE FUERZA (Line Chart) ---
            st.markdown("##### 🚀 Tendencia de Fuerza (1RM Estimado)")
            df_day["1RM_Display"] = df_day["1RM_Estimado"] * factor
            
            fig_str = px.line(df_day, x="Fecha", y="1RM_Display", markers=True, 
                              template="plotly_dark", height=350)
            fig_str.update_traces(line_color="#FF4B4B", line_width=3, marker_size=8)
            # Añadir línea de tendencia
            if len(df_day) > 1:
                fig_str.add_trace(px.scatter(df_day, x="Fecha", y="1RM_Display", trendline="ols").data[1])
            
            st.plotly_chart(fig_str, use_container_width=True)
            
            # --- GRÁFICA 2: VOLUMEN DE TRABAJO (Bar Chart) ---
            st.markdown("##### 🔋 Capacidad de Trabajo (Volumen por Sesión)")
            df_day["Vol_Display"] = df_day["Volumen"] * factor
            fig_vol = px.bar(df_day, x="Fecha", y="Vol_Display", template="plotly_dark", height=300)
            fig_vol.update_traces(marker_color="#00ADB5")
            st.plotly_chart(fig_vol, use_container_width=True)

    # =========================================================================
    # TAB 3: EDITOR DE RUTINAS (FLEXIBILIDAD)
    # =========================================================================
    with tab_edit:
        st.markdown("### 🛠️ Configuración del Sistema")
        st.info("Aquí defines la estructura de tus rutinas. Los cambios se guardan en la nube.")
        
        # 1. Seleccionar Rutina
        all_routines = sorted(df_config["Rutina"].unique())
        rut_edit = st.selectbox("Editar Rutina:", all_routines, key="sel_edit_rut")
        
        # 2. Filtrar y Editar
        df_rutina = df_config[df_config["Rutina"] == rut_edit].sort_values("Orden")
        
        col_ed1, col_ed2 = st.columns([2, 1])
        with col_ed1:
            st.markdown(f"**Ejercicios de {rut_edit}:**")
            edited_df = st.data_editor(
                df_rutina[["Orden", "Ejercicio"]],
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True
            )
        
        with col_ed2:
            st.write("##")
            st.write("##")
            if st.button("💾 GUARDAR CAMBIOS", type="primary"):
                # Proceso de guardado atómico
                ws_logs, ws_config = get_data_sheets()
                
                # Leer todo, quitar lo viejo de ESTA rutina, añadir lo nuevo
                full_data = ws_config.get_all_records()
                new_data = [row for row in full_data if row['Rutina'] != rut_edit]
                
                for idx, row in edited_df.iterrows():
                    new_data.append({
                        "Rutina": rut_edit,
                        "Orden": row["Orden"],
                        "Ejercicio": row["Ejercicio"].upper()
                    })
                
                # Reescribir hoja
                ws_config.clear()
                ws_config.append_row(["Rutina", "Orden", "Ejercicio"])
                
                # Batch write para velocidad
                matrix = [[r['Rutina'], r['Orden'], r['Ejercicio']] for r in new_data]
                ws_config.append_rows(matrix)
                
                st.toast("✅ Configuración Actualizada", icon="cloud")
                time.sleep(1.5)
                st.rerun()

        st.divider()
        # Crear Rutina Nueva
        with st.expander("➕ Crear Nueva Rutina Vacía"):
            new_name = st.text_input("Nombre (ej: ABS CORE)")
            if st.button("Crear"):
                if new_name:
                    ws_logs, ws_config = get_data_sheets()
                    ws_config.append_row([new_name.upper(), 1, "EJERCICIO 1"])
                    st.success("Creada. Búscala arriba para editarla.")
                    time.sleep(1)
                    st.rerun()

if __name__ == "__main__":
    main() 