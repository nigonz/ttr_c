"""
Módulo de Tarifas Comerciales - Integrable en Streamlit existente
=================================================================
Lógica extraída del Excel "Tarifas_Comerciales_hasta_febrero_laion.xlsx"

ESTRUCTURA DEL EXCEL:
- 3 tipos de tarifa: DF (Distrito Federal), JN (Junta Nacional), PBA (Provincia BA)
- Periodos: mensuales para DF y PBA, variables para JN
- Por período se tipean las 5 tarifas base (secciones 1-5, COMUN, Nominalizados)
- El resto se calcula con multiplicadores fijos:
    EXPRESO           = base × 1.25
    EXPRESO AUTOPISTA = base × 1.75
    SIN NOMINALIZAR   = base × 1.59
    (EXPRESO SN = base_sn × 1.25, AUTOPISTA SN = base_sn × 1.75)
- Sections 6-9: se dejan en 0 (no se usan en los primeros 5 tramos)
- Factor al inicio de cada período: % de variación entre períodos consecutivos

USO:
    import tarifas_module
    tarifas_module.show()          # renderiza la UI completa
    # o dentro de tu app:
    tarifas_module.render_tarifas_tab()
"""

import streamlit as st
import pandas as pd
import io
import json
from datetime import datetime

# --- CONFIGURACIÓN ---
TIPOS = ["DF", "JN", "PBA"]
MULTIPLICADORES = {
    "COMUN_N": 1.00, "EXPRESO_N": 1.25, "EPA_N": 1.75,
    "COMUN_SN": 1.59, "EXPRESO_SN": 1.25 * 1.59, "EPA_SN": 1.75 * 1.59
}
# Mapeo de IDs exactos para el TTR
ID_MAP = {
    "COMUN_N": "SCN", "EXPRESO_N": "SEN", "EPA_N": "SEAN",
    "COMUN_SN": "SCSN", "EXPRESO_SN": "SESN", "EPA_SN": "SEASN"
}

def generar_excel_ttr(periodo):
    """Crea el Excel vertical con IDs y redondeo a 2 decimales."""
    rows = []
    base5 = periodo["base5"]
    
    for cat, mult in MULTIPLICADORES.items():
        suffix = ID_MAP[cat]
        for i, tarifa_base in enumerate(base5):
            # Redondeo simétrico a 2 decimales (importante para que coincida con el Excel)
            valor = round(tarifa_base * mult, 2)
            rows.append({
                "Id": f"{i+1}{suffix}",
                "Limite Inferior": valor,
                "Limite Superior": valor
            })
    
    df = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Tarifas')
    return output.getvalue()

def render_tarifas_tab():
    if "tarifas_periodos" not in st.session_state:
        st.session_state.tarifas_periodos = []

    st.header("📊 Generador de Tarifas Comerciales")
    
    # 1. Entrada de datos
    tipo = st.radio("Seleccionar Tipo", TIPOS, horizontal=True)
    cols = st.columns(5)
    base5 = [cols[i].number_input(f"Secc {i+1}", value=0.0, format="%.2f", key=f"b{i}") for i in range(5)]
    
    if st.button("🚀 Calcular y Guardar", type="primary"):
        if any(base5):
            nuevo = {"tipo": tipo, "base5": base5, "ts": datetime.now().isoformat()}
            st.session_state.tarifas_periodos.append(nuevo)
            st.success("Tarifas calculadas con éxito.")
            st.rerun()

    # 2. Descarga de Excel (Lo que vos necesitás)
    periodos_tipo = [p for p in st.session_state.tarifas_periodos if p["tipo"] == tipo]
    if periodos_tipo:
        ultimo = periodos_tipo[-1]
        st.divider()
        st.subheader(f"✅ Tarifas Listas para {tipo}")
        
        # Este es el botón que genera el Excel vertical
        excel_data = generar_excel_ttr(ultimo)
        st.download_button(
            label="⬇️ Descargar Excel para TTR (Vertical)",
            data=excel_data,
            file_name=f"Tarifas_{tipo}_2026.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="secondary"
        )

        # Vista previa rápida
        st.caption("Vista previa de los primeros registros calculados:")
        preview_df = pd.DataFrame([
            {"Id": f"{i+1}{ID_MAP['COMUN_SN']}", "Valor": round(val * 1.59, 2)} 
            for i, val in enumerate(ultimo["base5"])
        ])
        st.table(preview_df)
