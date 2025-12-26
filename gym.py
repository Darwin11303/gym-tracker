import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA (SOBRIA) ---
st.set_page_config(page_title="GYM TRACKER", layout="wide")

# Estilos CSS para interfaz industrial
st.markdown("""
    <style>
    .main-header {text-align: center; font-family: 'Segoe UI', sans-serif;}
    .stButton>button {width: 100%; border-radius: 0px; font-weight: bold;}
    </style>
""", unsafe_allow_html=True)

st.markdown("<h1 class='main-header'>GYM TRACKER</h1>", unsafe_allow_html=True)
st.markdown("---")

# --- 1. MOTOR DE BASE DE DATOS ---
archivo_db = 'progreso_gym.csv'
columnas_db = ["Fecha", "Ejercicio", "Peso_KG", "Series", "Reps", "RIR", "Notas"]

def cargar_datos():
    if not os.path.exists(archivo_db):
        return pd.DataFrame(columns=columnas_db)
    try:
        return pd.read_csv(archivo_db)
    except:
        return pd.DataFrame(columns=columnas_db)

def guardar_datos(dataframe):
    # Aseguramos que no se guarde la columna auxiliar de eliminación
    if "Eliminar" in dataframe.columns:
        dataframe = dataframe.drop(columns=["Eliminar"])
    dataframe.to_csv(archivo_db, index=False)

df = cargar_datos()

# --- NAVEGACIÓN (TEXTO PLANO) ---
tab_registro, tab_analisis, tab_gestion = st.tabs(["REGISTRO", "PROGRESO", "GESTION DE DATOS"])

# ==========================================
# TAB 1: REGISTRO
# ==========================================
with tab_registro:
    with st.container():
        st.subheader("NUEVA SESION")
        
        with st.form("form_registro", clear_on_submit=True):
            
            # FILA 1
            c1, c2 = st.columns(2)
            with c1:
                fecha = st.date_input("Fecha", datetime.now())
            with c2:
                lista_ejercicios = sorted(df["Ejercicio"].unique().tolist()) if not df.empty else []
                opcion_nueva = "CREAR NUEVO..."
                opciones = [opcion_nueva] + lista_ejercicios
                
                seleccion = st.selectbox("Ejercicio", options=opciones)
                
                ejercicio_final = seleccion
                if seleccion == opcion_nueva:
                    ejercicio_nuevo = st.text_input("Nombre del Ejercicio")
                    if ejercicio_nuevo:
                        ejercicio_final = ejercicio_nuevo.strip()

            # FILA 2
            c3, c4, c5, c6 = st.columns(4)
            with c3:
                peso = st.number_input("Peso (KG)", min_value=0.0, step=2.5, format="%.2f")
            with c4:
                series = st.number_input("Series", min_value=1, step=1, value=3)
            with c5:
                reps = st.number_input("Repeticiones", min_value=1, step=1, value=10)
            with c6:
                rir = st.selectbox("RIR", [0, 1, 2, 3, 4], index=2)

            # FILA 3
            notas = st.text_area("Observaciones", height=68)

            submitted = st.form_submit_button("GUARDAR REGISTRO")
            
            if submitted:
                if seleccion == opcion_nueva and not ejercicio_nuevo:
                    st.error("Error: Ingrese nombre del ejercicio.")
                else:
                    nuevo_registro = pd.DataFrame([{
                        "Fecha": fecha, "Ejercicio": ejercicio_final, 
                        "Peso_KG": peso, "Series": series, 
                        "Reps": reps, "RIR": rir, "Notas": notas
                    }])
                    df_actualizado = pd.concat([df, nuevo_registro], ignore_index=True)
                    guardar_datos(df_actualizado)
                    st.success(f"REGISTRO GUARDADO: {ejercicio_final}")
                    st.rerun()

# ==========================================
# TAB 2: PROGRESO (GRAFICA LINEAL)
# ==========================================
with tab_analisis:
    if df.empty:
        st.info("No hay datos registrados.")
    else:
        col_sel, col_vacio = st.columns([1, 2])
        with col_sel:
            ej_analisis = st.selectbox("Seleccionar Ejercicio", df["Ejercicio"].unique())
        
        df_filt = df[df["Ejercicio"] == ej_analisis].copy()
        df_filt["Fecha"] = pd.to_datetime(df_filt["Fecha"])
        df_filt = df_filt.sort_values("Fecha")
        
        # Métricas
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("RECORD (PR)", f"{df_filt['Peso_KG'].max()} kg")
        kpi2.metric("ULTIMO PESO", f"{df_filt.iloc[-1]['Peso_KG']} kg")
        kpi3.metric("VOLUMEN TOTAL", f"{(df_filt['Peso_KG']*df_filt['Series']*df_filt['Reps']).iloc[-1]:.0f} kg")

        # Gráfica Lineal Simple (Sin relleno)
        st.line_chart(df_filt, x="Fecha", y="Peso_KG")
        
        st.caption("HISTORIAL DETALLADO")
        st.dataframe(df_filt.sort_values("Fecha", ascending=False), use_container_width=True, hide_index=True)

# ==========================================
# TAB 3: GESTION (CON COLUMNA DE BORRADO)
# ==========================================
with tab_gestion:
    st.header("CONTROL DE BASE DE DATOS")
    
    if not df.empty:
        # Preparamos el DataFrame para edición: Agregamos columna "Eliminar" al inicio
        df_editor = df.copy()
        df_editor.insert(0, "Eliminar", False)
        
        st.write("Marque la casilla 'Eliminar' en las filas que desee borrar y presione el boton inferior.")
        
        # Editor interactivo
        df_resultado = st.data_editor(
            df_editor,
            num_rows="dynamic",
            use_container_width=True,
            key="editor_principal",
            height=400,
            column_config={
                "Eliminar": st.column_config.CheckboxColumn(
                    "Eliminar",
                    help="Marque para borrar este registro",
                    default=False,
                )
            }
        )
        
        col_btn_save, col_btn_reset = st.columns([1, 1])
        
        with col_btn_save:
            # Botón único para guardar ediciones Y procesar borrados
            if st.button("APLICAR CAMBIOS Y ELIMINAR MARCADOS", type="primary"):
                # Filtramos las filas que NO están marcadas para eliminar
                df_limpio = df_resultado[df_resultado["Eliminar"] == False].copy()
                
                # Guardamos sin la columna "Eliminar"
                guardar_datos(df_limpio)
                
                filas_borradas = len(df_resultado) - len(df_limpio)
                if filas_borradas > 0:
                    st.success(f"Se eliminaron {filas_borradas} registros y se actualizaron los datos.")
                else:
                    st.success("Datos actualizados correctamente.")
                st.rerun()
        
        with col_btn_reset:
            with st.expander("ZONA DE PELIGRO (RESET TOTAL)"):
                if st.button("BORRAR TODO"):
                    df_vacio = pd.DataFrame(columns=columnas_db)
                    guardar_datos(df_vacio)
                    st.warning("Base de datos formateada.")
                    st.rerun()
    else:
        st.info("Base de datos vacia.")