import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import plotly.express as px
import time

# --- 1. CONFIGURACIÓN DEL SISTEMA (UI PRO) ---
st.set_page_config(page_title="Gym OS ", page_icon="🧬", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0E1117; }
    
    /* Botones y Controles */
    .stButton>button { 
        width: 100%; border-radius: 6px; font-weight: 700; 
        border: 1px solid #333; background-color: #1E1E1E; color: #EEE;
        transition: all 0.2s ease-in-out;
    }
    .stButton>button:hover { 
        border-color: #FF4B4B; color: #FF4B4B; background-color: #262626; transform: scale(1.01);
    }
    
    /* Tarjetas Informativas */
    .science-card {
        background-color: #1a2e35; color: #4af; 
        padding: 12px; border-radius: 8px; border-left: 5px solid #4af;
        margin-bottom: 15px; font-size: 0.95rem; box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }
    .history-box {
        background-color: #131720; border: 1px solid #333;
        padding: 15px; border-radius: 8px; margin-bottom: 15px;
    }
    
    /* Historial Diario */
    .day-card {
        background-color: #212529; padding: 15px; border-radius: 10px;
        border: 1px solid #444; margin-bottom: 10px;
    }
    .set-tag {
        background-color: #333; padding: 2px 8px; border-radius: 4px; 
        font-size: 0.8rem; margin-right: 5px; color: #DDD;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. GESTIÓN DE DATOS (BACKEND ROBUSTO) ---
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

# CACHÉ INTELIGENTE: Evita el error 429 de Google
@st.cache_data(ttl=60, show_spinner=False)
def load_data_cached():
    client = get_client()
    if not client: return pd.DataFrame(), pd.DataFrame(columns=["Rutina", "Orden", "Ejercicio", "Series_Rec", "Reps_Rec"])
    
    try:
        sh = client.open("GymData")
        
        # 1. Cargar Logs (Historial de Entrenamientos)
        ws_logs = sh.sheet1
        data_logs = ws_logs.get_all_records()
        df_logs = pd.DataFrame(data_logs)
        
        # Procesamiento de Tipos de Datos
        if not df_logs.empty and "Fecha" in df_logs.columns:
            df_logs["Fecha"] = pd.to_datetime(df_logs["Fecha"], errors='coerce').dt.date
            cols_num = ["Peso_KG", "Reps", "RIR", "1RM_Estimado", "Volumen", "Series"]
            for c in cols_num: 
                if c in df_logs.columns: df_logs[c] = pd.to_numeric(df_logs[c], errors='coerce').fillna(0)
            if "Ejercicio" in df_logs.columns:
                df_logs["Ejercicio"] = df_logs["Ejercicio"].astype(str).str.strip().str.upper()

        # 2. Cargar Configuración (Rutinas)
        try:
            ws_config = sh.worksheet("Config_Rutinas")
            df_config = pd.DataFrame(ws_config.get_all_records())
            
            # Asegurar compatibilidad con versiones anteriores
            if "Series_Rec" not in df_config.columns: df_config["Series_Rec"] = 3
            if "Reps_Rec" not in df_config.columns: df_config["Reps_Rec"] = "8-12"
        except:
            df_config = pd.DataFrame(columns=["Rutina", "Orden", "Ejercicio", "Series_Rec", "Reps_Rec"])

        return df_logs, df_config

    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(columns=["Rutina", "Orden", "Ejercicio", "Series_Rec", "Reps_Rec"])

def init_defaults_if_needed():
    """Inicializador Inteligente: Repara la hoja solo si es necesario"""
    client = get_client()
    if not client: return
    sh = client.open("GymData")
    
    # Lógica de Reparación "Try/Check/Fix"
    recreate = False
    try:
        ws = sh.worksheet("Config_Rutinas")
        headers = ws.row_values(1)
        # Si existe pero le faltan las columnas de ciencia, la recreamos
        if "Series_Rec" not in headers:
            sh.del_worksheet(ws)
            time.sleep(1)
            recreate = True
    except gspread.WorksheetNotFound:
        recreate = True # No existe, hay que crearla
    
    if recreate:
        ws = sh.add_worksheet(title="Config_Rutinas", rows="100", cols="5")
        ws.append_row(["Rutina", "Orden", "Ejercicio", "Series_Rec", "Reps_Rec"])
        
        # BASE DE DATOS MAESTRA (V7.0)
        defaults = [
            ["PUSH A", 1, "PRESS BANCA MANCUERNAS", 3, "6-10"],
            ["PUSH A", 2, "PRESS MILITAR DE PIE", 3, "8-10"],
            ["PUSH A", 3, "HEX PRESS", 3, "10-12"],
            ["PUSH A", 4, "ELEVACIONES LATERALES", 3, "12-15"],
            ["PUSH A", 5, "EXT. TRICEPS POLEA", 3, "12-15"],
            ["PUSH A", 6, "TRICEPS TRAS NUCA", 3, "10-12"],
            ["PUSH A", 7, "FACE PULLS", 2, "15-20"],
            
            ["PULL A", 1, "JALON AL PECHO", 4, "8-10"],
            ["PULL A", 2, "REMO POLEA BAJA", 3, "10-12"],
            ["PULL A", 3, "PULLOVER POLEA", 3, "12-15"],
            ["PULL A", 4, "PAJAROS MAQUINA", 3, "15+"],
            ["PULL A", 5, "CURL BARRA", 3, "8-10"],
            ["PULL A", 6, "CURL MARTILLO", 3, "10-12"],
            
            ["LEGS A", 1, "SENTADILLA", 3, "6-8"],
            ["LEGS A", 2, "PRENSA PIERNAS", 3, "10-12"],
            ["LEGS A", 3, "CURL FEMORAL SENTADO", 4, "10-12"],
            ["LEGS A", 4, "EXTENSION CUADRICEPS", 3, "15+"],
            ["LEGS A", 5, "ELEVACION TALONES", 4, "15-20"],
            
            ["PUSH B", 1, "PRESS INCLINADO MANCUERNAS", 4, "8-12"],
            ["PUSH B", 2, "APERTURAS", 3, "12-15"],
            ["PUSH B", 3, "PRESS MILITAR SENTADO", 3, "10-12"],
            ["PUSH B", 4, "ELEVACIONES LATERAL POLEA", 4, "12-15"],
            ["PUSH B", 5, "TRICEPS POLEA BARRA", 4, "12-15"],
            ["PUSH B", 6, "FACE PULLS", 2, "15-20"],
            
            ["PULL B", 1, "REMO SERRUCHO", 4, "10-12"],
            ["PULL B", 2, "JALON AL PECHO (NEUTRO)", 3, "10-12"],
            ["PULL B", 3, "FACE PULLS (PESADO)", 4, "12-15"],
            ["PULL B", 4, "CURL PREDICADOR", 3, "10-12"],
            ["PULL B", 5, "CURL POLEA ESPALDA", 3, "12-15"],
            
            ["LEGS B", 1, "ZANCADAS", 3, "10-12"],
            ["LEGS B", 2, "HIP THRUST", 4, "8-12"],
            ["LEGS B", 3, "PRENSA (PIES ALTOS)", 3, "12-15"],
            ["LEGS B", 4, "CURL FEMORAL TUMBADO", 3, "12-15"],
            ["LEGS B", 5, "GEMELO SENTADO", 4, "15-20"]
        ]
        ws.append_rows(defaults)
        load_data_cached.clear()

def clear_app_cache():
    load_data_cached.clear()

# --- 3. FUNCIONES LÓGICAS ---
def calcular_calentamiento(peso_objetivo):
    return round(peso_objetivo*0.5, 1), round(peso_objetivo*0.75, 1)

def detectar_estancamiento(df, ejercicio):
    if df.empty or ejercicio not in df["Ejercicio"].values: return False
    hist = df[df["Ejercicio"] == ejercicio].sort_values("Fecha", ascending=False)
    daily = hist.groupby("Fecha")["1RM_Estimado"].max().sort_index(ascending=False).head(3)
    if len(daily) < 3: return False
    return daily.iloc[0] <= daily.iloc[2]

# --- 4. PROGRAMA PRINCIPAL ---
def main():
    # 1. Autoreparación Silenciosa
    init_defaults_if_needed()
    
    if 'buffer_series' not in st.session_state: st.session_state.buffer_series = []
    
    # 2. Carga de Datos
    df_logs, df_config = load_data_cached()
    
    # --- SIDEBAR ---
    st.sidebar.title("🧬 Gym OS v7.0")
    if st.sidebar.button("🔄 Sincronizar (Recargar)"):
        clear_app_cache()
        st.rerun()
        
    modo_lb = st.sidebar.toggle("Modo Libras (LB)", value=True)
    factor = 2.20462 if modo_lb else 1.0
    suffix = "lb" if modo_lb else "kg"
    
    # --- PESTAÑAS (Aquí está la magia completa) ---
    t1, t2, t3, t4 = st.tabs(["🔥 ENTRENAR", "📅 HISTORIAL", "📊 GRÁFICAS", "🛠️ EDITOR"])

    # =======================================================
    # TAB 1: ZONA DE ENTRENAMIENTO (LOGGER)
    # =======================================================
    with t1:
        if df_config.empty:
            st.warning("⚠️ Cargando sistema... Si tarda, pulsa 'Sincronizar' en el menú.")
        else:
            # Selector de Rutina (Con predicción inteligente)
            rutinas = sorted(df_config["Rutina"].unique())
            idx_rut = 0
            if not df_logs.empty and "Tipo_Sesion" in df_logs.columns:
                last_s = df_logs.sort_values("Fecha", ascending=False).iloc[0]["Tipo_Sesion"]
                order = ["PUSH A", "PULL A", "LEGS A", "PUSH B", "PULL B", "LEGS B"]
                if last_s in order:
                    nxt = order[(order.index(last_s) + 1) % len(order)]
                    if nxt in rutinas: idx_rut = rutinas.index(nxt)
            
            col_sel_r, col_sel_e = st.columns([1, 2])
            rut_hoy = col_sel_r.selectbox("Rutina:", rutinas, index=idx_rut)
            
            # Selector de Ejercicio
            df_ej = df_config[df_config["Rutina"] == rut_hoy].sort_values("Orden")
            ej_hoy = col_sel_e.selectbox("Ejercicio:", df_ej["Ejercicio"].tolist())
            
            # === TARJETA CIENTÍFICA ===
            try:
                row_info = df_ej[df_ej["Ejercicio"] == ej_hoy].iloc[0]
                rec_series = row_info.get("Series_Rec", 3)
                rec_reps = row_info.get("Reps_Rec", "10-12")
            except:
                rec_series, rec_reps = 3, "10-12"
            
            st.markdown(f"""
            <div class="science-card">
                🧠 <b>META CIENTÍFICA:</b> Apunta a <b>{rec_series} series</b> entre <b>{rec_reps} reps</b>.
            </div>
            """, unsafe_allow_html=True)
            
            # === LÓGICA DE REGISTRO ===
            if 'last_ej' not in st.session_state or st.session_state.last_ej != ej_hoy:
                st.session_state.buffer_series = []
                st.session_state.last_ej = ej_hoy
            
            c1, c2 = st.columns([1, 1.5])
            
            with c1: # PANEL IZQUIERDO: CONTEXTO
                if not df_logs.empty and ej_hoy in df_logs["Ejercicio"].values:
                    hist = df_logs[df_logs["Ejercicio"] == ej_hoy].sort_values("Fecha", ascending=False)
                    last_date = hist.iloc[0]["Fecha"]
                    # Obtener la MEJOR serie de la sesión anterior
                    best_prev = hist[hist["Fecha"] == last_date].sort_values("1RM_Estimado", ascending=False).iloc[0]
                    
                    p_prev = round(best_prev["Peso_KG"] * factor, 1)
                    st.markdown(f"""
                    <div class="history-box">
                        <div style="color:#AAA; font-size:0.8rem; font-weight:bold;">ÚLTIMA SESIÓN ({last_date})</div>
                        <div style="font-size:2rem; font-weight:800; color:white;">{p_prev} <span style="font-size:1rem; color:#FF4B4B;">{suffix}</span></div>
                        <div style="font-size:1.1rem;">x {best_prev['Reps']} reps <span style="background:#333; padding:2px 5px; border-radius:4px; font-size:0.8rem;">RIR {best_prev['RIR']}</span></div>
                        <div style="font-style:italic; color:#BBB; font-size:0.85rem; margin-top:8px; border-top:1px solid #333; padding-top:5px;">"{best_prev.get('Notas','')}"</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if detectar_estancamiento(df_logs, ej_hoy):
                        st.warning("⚠️ ALERTA: 3 Sesiones estancado. ¡Sube peso hoy!")
                    
                    with st.expander("🌡️ Ver Calentamiento Sugerido"):
                        w1, w2 = calcular_calentamiento(p_prev)
                        st.info(f"1️⃣ 12 reps x {w1} {suffix}\n\n2️⃣ 4 reps x {w2} {suffix} (Rápido)")
                else:
                    st.info("🆕 Primer registro de este ejercicio.")

            with c2: # PANEL DERECHO: INPUT
                st.markdown("##### 📝 Nueva Serie")
                cc1, cc2, cc3 = st.columns(3)
                
                # Auto-rellenar reps
                try: def_reps = int(str(rec_reps).split('-')[0])
                except: def_reps = 10
                
                p_in = cc1.number_input(f"Peso ({suffix})", step=2.5, min_value=0.0)
                r_in = cc2.number_input("Reps", step=1, value=def_reps)
                rir_in = cc3.selectbox("RIR", [0,1,2,3,4], index=1)
                
                if st.button("➕ Agregar Serie", use_container_width=True):
                    if p_in > 0:
                        st.session_state.buffer_series.append({
                            "Peso_KG": p_in/factor, "Peso_Display": p_in, "Reps": r_in, "RIR": rir_in
                        })
                
                # Visualización del Buffer
                if st.session_state.buffer_series:
                    st.write("---")
                    for i, s in enumerate(st.session_state.buffer_series):
                        st.markdown(f"""
                        <div style="background:#222; padding:8px; border-radius:5px; margin-bottom:5px; border-left:3px solid #FF4B4B;">
                            <b>Serie {i+1}:</b> {s['Peso_Display']} {suffix} x {s['Reps']} <span style="float:right; color:#888;">RIR {s['RIR']}</span>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    notas = st.text_input("Notas Finales:", placeholder="Ej: Me costó estabilizar, subir peso...")
                    
                    if st.button("💾 GUARDAR DATOS EN LA NUBE", type="primary"):
                        cli = get_client()
                        if cli:
                            sh = cli.open("GymData")
                            rows = []
                            now = datetime.now().strftime("%Y-%m-%d")
                            for i, s in enumerate(st.session_state.buffer_series):
                                kg = s['Peso_KG']
                                rm = kg * (1 + s['Reps']/30)
                                rows.append([
                                    now, ej_hoy.strip().upper(), kg, s['Reps'], s['RIR'],
                                    round(rm, 2), round(kg*s['Reps'], 2), notas, rut_hoy, i+1
                                ])
                            sh.sheet1.append_rows(rows)
                            st.toast("✅ Guardado exitoso", icon="🚀")
                            clear_app_cache()
                            st.session_state.buffer_series = []
                            time.sleep(1)
                            st.rerun()

    # =======================================================
    # TAB 2: HISTORIAL DIARIO (LA "TIME MACHINE") - NUEVO
    # =======================================================
    with t2:
        st.header("📅 Diario de Entrenamiento")
        if df_logs.empty:
            st.warning("No hay registros aún.")
        else:
            # Selector de Fecha
            fechas_disponibles = sorted(df_logs["Fecha"].unique(), reverse=True)
            fecha_sel = st.selectbox("Selecciona una fecha:", fechas_disponibles)
            
            # Filtrar datos de ese día
            df_dia = df_logs[df_logs["Fecha"] == fecha_sel].copy()
            
            # Mostrar Resumen del Día
            rutina_dia = df_dia["Tipo_Sesion"].iloc[0] if "Tipo_Sesion" in df_dia.columns else "Desconocida"
            volumen_dia = df_dia["Volumen"].sum() * factor
            series_dia = len(df_dia)
            
            col_h1, col_h2, col_h3 = st.columns(3)
            col_h1.metric("Rutina Realizada", rutina_dia)
            col_h2.metric("Volumen Total", f"{int(volumen_dia)} {suffix}")
            col_h3.metric("Series Totales", series_dia)
            
            st.divider()
            
            # Mostrar detalle ejercicio por ejercicio
            ejercicios_dia = df_dia["Ejercicio"].unique()
            for ej in ejercicios_dia:
                df_ej_dia = df_dia[df_dia["Ejercicio"] == ej]
                
                with st.expander(f"💪 {ej} ({len(df_ej_dia)} series)", expanded=True):
                    for _, row in df_ej_dia.iterrows():
                        peso_show = round(row["Peso_KG"] * factor, 1)
                        st.markdown(f"""
                        <div style="display:flex; justify-content:space-between; border-bottom:1px solid #333; padding:5px;">
                            <span><b>{peso_show} {suffix}</b> x {row['Reps']} reps</span>
                            <span style="color:#AAA; font-size:0.9rem;">RIR {row['RIR']}</span>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    notas_ej = df_ej_dia["Notas"].iloc[-1]
                    if notas_ej:
                        st.caption(f"📝 Nota: {notas_ej}")

    # =======================================================
    # TAB 3: GRÁFICAS DE PROGRESO
    # =======================================================
    with t3:
        if df_logs.empty: st.info("Registra datos para ver tu evolución.")
        else:
            lista_ejs = sorted(df_logs["Ejercicio"].unique())
            ej_analisis = st.selectbox("Analizar Evolución de:", lista_ejs)
            
            df_graph = df_logs[df_logs["Ejercicio"] == ej_analisis].copy()
            # Agrupar por día (Mejor serie del día)
            df_day_g = df_graph.groupby("Fecha").agg({"1RM_Estimado":"max", "Volumen":"sum"}).reset_index().sort_values("Fecha")
            
            df_day_g["1RM_Display"] = df_day_g["1RM_Estimado"] * factor
            
            # Gráfica Lineal
            fig = px.line(df_day_g, x="Fecha", y="1RM_Display", markers=True, title=f"Fuerza Estimada (1RM) - {ej_analisis}")
            fig.update_traces(line_color="#FF4B4B", line_width=3)
            fig.update_layout(yaxis_title=f"Peso ({suffix})", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"))
            st.plotly_chart(fig, use_container_width=True)

    # =======================================================
    # TAB 4: EDITOR DE RUTINAS
    # =======================================================
    with t4:
        st.markdown("### 🛠️ Configuración de Rutinas")
        st.info("Modifica aquí los ejercicios y las metas científicas (Series y Reps).")
        
        rutina_edit = st.selectbox("Selecciona Rutina a Editar:", sorted(df_config["Rutina"].unique()), key="edit_sel")
        df_edit_view = df_config[df_config["Rutina"] == rutina_edit].sort_values("Orden")
        
        # Editor interactivo
        edited_df = st.data_editor(
            df_edit_view[["Orden", "Ejercicio", "Series_Rec", "Reps_Rec"]],
            num_rows="dynamic", use_container_width=True, hide_index=True
        )
        
        if st.button("💾 Guardar Cambios de Rutina"):
            cli = get_client()
            if cli:
                sh = cli.open("GymData")
                ws = sh.worksheet("Config_Rutinas")
                all_records = ws.get_all_records()
                
                # Filtrar y Reemplazar
                new_records = [r for r in all_records if r['Rutina'] != rutina_edit]
                
                for _, row in edited_df.iterrows():
                    new_records.append({
                        "Rutina": rutina_edit,
                        "Orden": row["Orden"],
                        "Ejercicio": str(row["Ejercicio"]).strip().upper(),
                        "Series_Rec": row["Series_Rec"],
                        "Reps_Rec": row["Reps_Rec"]
                    })
                
                # Reescribir Hoja
                ws.clear()
                ws.append_row(["Rutina", "Orden", "Ejercicio", "Series_Rec", "Reps_Rec"])
                export_data = [[x['Rutina'], x['Orden'], x['Ejercicio'], x['Series_Rec'], x['Reps_Rec']] for x in new_records]
                ws.append_rows(export_data)
                
                st.toast("Configuración Actualizada", icon="✅")
                clear_app_cache()
                time.sleep(1)
                st.rerun()

if __name__ == "__main__":
    main()