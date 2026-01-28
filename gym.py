import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import plotly.express as px
import time

# --- 1. CONFIGURACIÓN DEL SISTEMA ---
st.set_page_config(page_title="Gym OS v6.0", page_icon="🧬", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0E1117; }
    .stButton>button { 
        width: 100%; border-radius: 6px; font-weight: 600; 
        border: 1px solid #303030; background-color: #1E1E1E; color: #EEE;
    }
    .stButton>button:hover { 
        border-color: #FF4B4B; color: #FF4B4B; background-color: #262626; 
    }
    .science-card {
        background-color: #1a2e35; color: #4af; 
        padding: 10px; border-radius: 8px; border-left: 4px solid #4af;
        margin-bottom: 15px; font-size: 0.95rem;
    }
    .history-box {
        background-color: #131720; border: 1px solid #333;
        padding: 15px; border-radius: 8px; margin-bottom: 15px;
    }
    .alert-box { background: #422006; color: #facc15; padding: 10px; border-radius: 6px; margin-top: 5px; }
    </style>
""", unsafe_allow_html=True)

# --- 2. GESTIÓN DE DATOS ---
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
        st.error(f"❌ Error Auth: {e}")
        return None

@st.cache_data(ttl=60, show_spinner=False)
def load_data_cached():
    client = get_client()
    if not client: return pd.DataFrame(), pd.DataFrame(columns=["Rutina", "Orden", "Ejercicio", "Series_Rec", "Reps_Rec"])
    
    try:
        sh = client.open("GymData")
        
        # 1. Logs
        df_logs = pd.DataFrame(sh.sheet1.get_all_records())
        if not df_logs.empty and "Fecha" in df_logs.columns:
            df_logs["Fecha"] = pd.to_datetime(df_logs["Fecha"], errors='coerce').dt.date
            cols_num = ["Peso_KG", "Reps", "RIR", "1RM_Estimado", "Volumen", "Series"]
            for c in cols_num: 
                if c in df_logs.columns: df_logs[c] = pd.to_numeric(df_logs[c], errors='coerce').fillna(0)
            if "Ejercicio" in df_logs.columns:
                df_logs["Ejercicio"] = df_logs["Ejercicio"].astype(str).str.strip().str.upper()

        # 2. Config (Rutinas + Ciencia)
        try:
            df_config = pd.DataFrame(sh.worksheet("Config_Rutinas").get_all_records())
            # Si faltan columnas nuevas (migración), las creamos vacías
            if "Series_Rec" not in df_config.columns: df_config["Series_Rec"] = 3
            if "Reps_Rec" not in df_config.columns: df_config["Reps_Rec"] = "8-12"
        except:
            df_config = pd.DataFrame(columns=["Rutina", "Orden", "Ejercicio", "Series_Rec", "Reps_Rec"])

        return df_logs, df_config

    except:
        return pd.DataFrame(), pd.DataFrame(columns=["Rutina", "Orden", "Ejercicio", "Series_Rec", "Reps_Rec"])

def init_defaults_if_needed():
    """Genera la hoja Config con rangos científicos"""
    client = get_client()
    if not client: return
    sh = client.open("GymData")
    
    try:
        ws = sh.worksheet("Config_Rutinas")
        if len(ws.get_all_values()) <= 1: raise Exception("Rebuild")
    except:
        ws = sh.add_worksheet(title="Config_Rutinas", rows="100", cols="5")
        # HEADER NUEVO
        ws.append_row(["Rutina", "Orden", "Ejercicio", "Series_Rec", "Reps_Rec"])
        
        # TUS EJERCICIOS + CIENCIA (Series | Reps)
        defaults = [
            # PUSH A
            ["PUSH A", 1, "PRESS BANCA MANCUERNAS", 3, "6-10"],
            ["PUSH A", 2, "PRESS MILITAR DE PIE", 3, "8-10"],
            ["PUSH A", 3, "HEX PRESS", 3, "10-12"],
            ["PUSH A", 4, "ELEVACIONES LATERALES", 3, "12-15"],
            ["PUSH A", 5, "EXT. TRICEPS POLEA", 3, "12-15"],
            ["PUSH A", 6, "TRICEPS TRAS NUCA", 3, "10-12"],
            ["PUSH A", 7, "FACE PULLS", 2, "15-20"],
            # PULL A
            ["PULL A", 1, "JALON AL PECHO", 4, "8-10"],
            ["PULL A", 2, "REMO POLEA BAJA", 3, "10-12"],
            ["PULL A", 3, "PULLOVER POLEA", 3, "12-15"],
            ["PULL A", 4, "PAJAROS MAQUINA", 3, "15+"],
            ["PULL A", 5, "CURL BARRA", 3, "8-10"],
            ["PULL A", 6, "CURL MARTILLO", 3, "10-12"],
            # LEGS A
            ["LEGS A", 1, "SENTADILLA", 3, "6-8"],
            ["LEGS A", 2, "PRENSA PIERNAS", 3, "10-12"],
            ["LEGS A", 3, "CURL FEMORAL SENTADO", 4, "10-12"],
            ["LEGS A", 4, "EXTENSION CUADRICEPS", 3, "15+"],
            ["LEGS A", 5, "ELEVACION TALONES", 4, "15-20"],
            # PUSH B
            ["PUSH B", 1, "PRESS INCLINADO MANCUERNAS", 4, "8-12"],
            ["PUSH B", 2, "APERTURAS", 3, "12-15"],
            ["PUSH B", 3, "PRESS MILITAR SENTADO", 3, "10-12"],
            ["PUSH B", 4, "ELEVACIONES LATERAL POLEA", 4, "12-15"],
            ["PUSH B", 5, "TRICEPS POLEA BARRA", 4, "12-15"],
            ["PUSH B", 6, "FACE PULLS", 2, "15-20"],
            # PULL B
            ["PULL B", 1, "REMO SERRUCHO", 4, "10-12"],
            ["PULL B", 2, "JALON AL PECHO (NEUTRO)", 3, "10-12"],
            ["PULL B", 3, "FACE PULLS (PESADO)", 4, "12-15"],
            ["PULL B", 4, "CURL PREDICADOR", 3, "10-12"],
            ["PULL B", 5, "CURL POLEA ESPALDA", 3, "12-15"],
            # LEGS B
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

# --- 3. LÓGICA ---
def calcular_calentamiento(peso_objetivo):
    return round(peso_objetivo*0.5, 1), round(peso_objetivo*0.75, 1)

def detectar_estancamiento(df, ejercicio):
    if df.empty or ejercicio not in df["Ejercicio"].values: return False
    hist = df[df["Ejercicio"] == ejercicio].sort_values("Fecha", ascending=False)
    daily = hist.groupby("Fecha")["1RM_Estimado"].max().sort_index(ascending=False).head(3)
    if len(daily) < 3: return False
    return daily.iloc[0] <= daily.iloc[2]

# --- 4. MAIN ---
def main():
    init_defaults_if_needed()
    if 'buffer_series' not in st.session_state: st.session_state.buffer_series = []
    
    df_logs, df_config = load_data_cached()
    
    st.sidebar.title("🧬 Gym OS v6.0")
    if st.sidebar.button("🔄 Forzar Recarga"):
        clear_app_cache()
        st.rerun()
        
    modo_lb = st.sidebar.toggle("Modo Libras (LB)", value=True)
    factor = 2.20462 if modo_lb else 1.0
    suffix = "lb" if modo_lb else "kg"

    t1, t2, t3 = st.tabs(["🔥 ENTRENAR", "📊 PROGRESO", "🛠️ EDITOR"])

    # === TAB 1: ENTRENAR ===
    with t1:
        if df_config.empty:
            st.warning("Cargando base de datos... Si no aparece, recarga.")
        else:
            # Selector Rutina
            rutinas = sorted(df_config["Rutina"].unique())
            # Auto-selección inteligente
            idx_rut = 0
            if not df_logs.empty and "Tipo_Sesion" in df_logs.columns:
                last_s = df_logs.sort_values("Fecha", ascending=False).iloc[0]["Tipo_Sesion"]
                order = ["PUSH A", "PULL A", "LEGS A", "PUSH B", "PULL B", "LEGS B"]
                if last_s in order:
                    nxt = order[(order.index(last_s) + 1) % len(order)]
                    if nxt in rutinas: idx_rut = rutinas.index(nxt)
            
            rut_hoy = st.selectbox("Rutina:", rutinas, index=idx_rut)
            
            # Selector Ejercicio
            df_ej = df_config[df_config["Rutina"] == rut_hoy].sort_values("Orden")
            ej_hoy = st.selectbox("Ejercicio:", df_ej["Ejercicio"].tolist())
            
            # --- INFO CIENTÍFICA (NUEVO) ---
            # Extraemos los datos científicos de la fila seleccionada
            row_info = df_ej[df_ej["Ejercicio"] == ej_hoy].iloc[0]
            rec_series = row_info.get("Series_Rec", 3)
            rec_reps = row_info.get("Reps_Rec", "10-12")
            
            st.markdown(f"""
            <div class="science-card">
                🧪 <b>PROTOCOLO CIENTÍFICO:</b> Realiza <b>{rec_series} series</b> en un rango de <b>{rec_reps} reps</b>.
            </div>
            """, unsafe_allow_html=True)
            
            # --- LOGIC ---
            if 'last_ej' not in st.session_state or st.session_state.last_ej != ej_hoy:
                st.session_state.buffer_series = []
                st.session_state.last_ej = ej_hoy
            
            c1, c2 = st.columns([1, 1.5])
            
            with c1: # HISTORIAL
                if not df_logs.empty and ej_hoy in df_logs["Ejercicio"].values:
                    hist = df_logs[df_logs["Ejercicio"] == ej_hoy].sort_values("Fecha", ascending=False)
                    last_date = hist.iloc[0]["Fecha"]
                    best_prev = hist[hist["Fecha"] == last_date].sort_values("1RM_Estimado", ascending=False).iloc[0]
                    
                    p_prev = round(best_prev["Peso_KG"] * factor, 1)
                    st.markdown(f"""
                    <div class="history-box">
                        <div style="color:#AAA; font-size:0.8rem;">ÚLTIMA VEZ ({last_date})</div>
                        <div style="font-size:1.8rem; font-weight:800; color:white;">{p_prev} {suffix}</div>
                        <div>x {best_prev['Reps']} reps (RIR {best_prev['RIR']})</div>
                        <div style="font-style:italic; color:#BBB; font-size:0.85rem; margin-top:5px;">"{best_prev.get('Notas','')}"</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if detectar_estancamiento(df_logs, ej_hoy):
                        st.markdown('<div class="alert-box">⚠️ Estancamiento (3 sesiones igual)</div>', unsafe_allow_html=True)
                    
                    with st.expander("🌡️ Calentamiento"):
                        w1, w2 = calcular_calentamiento(p_prev)
                        st.write(f"1️⃣ 12 reps x {w1} {suffix}")
                        st.write(f"2️⃣ 4 reps x {w2} {suffix} (Rápido)")
                else:
                    st.info("🆕 Ejercicio Nuevo")

            with c2: # INPUTS
                cc1, cc2, cc3 = st.columns(3)
                # Auto-rellenar series sugeridas si es la primera
                def_reps = int(rec_reps.split('-')[0]) if '-' in str(rec_reps) else 10
                
                p_in = cc1.number_input(f"Peso ({suffix})", step=2.5, min_value=0.0)
                r_in = cc2.number_input("Reps", step=1, value=def_reps)
                rir_in = cc3.selectbox("RIR", [0,1,2,3,4], index=1)
                
                if st.button("➕ Añadir Serie"):
                    st.session_state.buffer_series.append({
                        "Peso_KG": p_in/factor, "Peso_Display": p_in, "Reps": r_in, "RIR": rir_in
                    })
                
                if st.session_state.buffer_series:
                    st.write("---")
                    for i, s in enumerate(st.session_state.buffer_series):
                        st.caption(f"Serie {i+1}: {s['Peso_Display']} {suffix} x {s['Reps']} (RIR {s['RIR']})")
                    
                    notas = st.text_input("Notas:", placeholder="Sensaciones...")
                    
                    if st.button("💾 GUARDAR EJERCICIO", type="primary"):
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
                            st.toast("Guardado!", icon="💪")
                            clear_app_cache()
                            st.session_state.buffer_series = []
                            time.sleep(1)
                            st.rerun()

    # === TAB 2: PROGRESO ===
    with t2:
        if df_logs.empty: st.warning("Sin datos.")
        else:
            ejs = sorted(df_logs["Ejercicio"].unique())
            sel = st.selectbox("Analizar:", ejs)
            df_g = df_logs[df_logs["Ejercicio"] == sel].copy()
            df_day = df_g.groupby("Fecha").agg({"1RM_Estimado":"max", "Volumen":"sum"}).reset_index().sort_values("Fecha")
            
            df_day["1RM"] = df_day["1RM_Estimado"] * factor
            fig = px.line(df_day, x="Fecha", y="1RM", markers=True, title="Fuerza (1RM)")
            fig.update_traces(line_color="#4af")
            st.plotly_chart(fig, use_container_width=True)

    # === TAB 3: EDITOR (CON CIENCIA) ===
    with t3:
        st.info("🛠️ Edita Ejercicios y Metas Científicas (Series/Reps)")
        r_edit = st.selectbox("Rutina:", sorted(df_config["Rutina"].unique()), key="eds")
        df_e = df_config[df_config["Rutina"] == r_edit].sort_values("Orden")
        
        # Editor ampliado con columnas de ciencia
        edited = st.data_editor(
            df_e[["Orden", "Ejercicio", "Series_Rec", "Reps_Rec"]],
            num_rows="dynamic", use_container_width=True, hide_index=True
        )
        
        if st.button("💾 Guardar Rutina"):
            cli = get_client()
            if cli:
                sh = cli.open("GymData")
                ws = sh.worksheet("Config_Rutinas")
                all_d = ws.get_all_records()
                # Filtrar fuera la rutina actual
                keep = [x for x in all_d if x['Rutina'] != r_edit]
                
                # Añadir editados
                for _, r in edited.iterrows():
                    keep.append({
                        "Rutina": r_edit, "Orden": r["Orden"], 
                        "Ejercicio": str(r["Ejercicio"]).strip().upper(),
                        "Series_Rec": r["Series_Rec"], "Reps_Rec": r["Reps_Rec"]
                    })
                
                ws.clear()
                ws.append_row(["Rutina", "Orden", "Ejercicio", "Series_Rec", "Reps_Rec"])
                # Escribir
                out = [[k['Rutina'], k['Orden'], k['Ejercicio'], k['Series_Rec'], k['Reps_Rec']] for k in keep]
                ws.append_rows(out)
                st.toast("Actualizado", icon="✅")
                clear_app_cache()
                time.sleep(1)
                st.rerun()

if __name__ == "__main__":
    main()