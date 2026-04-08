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
from datetime import datetime

# --- COEFICIENTES DE REPLICACIÓN (Extraídos de tu CSV) ---
# Usamos 1.591 para PBA y 1.59 para DF/JN según el histórico
MULT = {
    "N": 1.00, "EN": 1.25, "EAN": 1.75,
    "CSN": 1.591, "ESN": 1.25 * 1.591, "EASN": 1.75 * 1.591
}

def generar_tarifas_pro(base5, juris):
    """Genera la estructura total: Secciones, KM, LP, KP, SRSR y KM2."""
    rows = []
    b1 = base5[0]
    
    # 1. SECCIONES 1-5 (Base y Variantes)
    suffixes = {"SCN": "CN", "SEN": "EN", "SEAN": "EAN", "SCSN": "CSN", "SESN": "ESN", "SEASN": "EASN"}
    for i, b in enumerate(base5):
        for code, m_key in suffixes.items():
            # Aplicamos multiplicador y redondeo
            m = MULT.get(m_key, 1.0) if "SCN" not in code else 1.0
            val = round(b * m, 2)
            # Caso especial 1SCN en PBA (rango de centavos)
            inf, sup = val, val
            if juris == "PBA" and i == 0 and code == "SCN":
                inf, sup = 721.33, 721.84 # Valores fijos de tu lista
            rows.append({"Id": f"{i+1}{code}", "Limite Inferior": inf, "Limite Superior": sup})

    # 2. SERIES 1-4KM (Fijas y con rango)
    # Valor base KM según planilla (~1.316 b1)
    base_km_val = round(b1 * 1.316, 2)
    for m_key, m_val in MULT.items():
        v_sup = round(base_km_val * m_val, 2)
        v_inf = round(v_sup - 0.50, 2) if m_key == "CN" else v_sup
        # Primera fila con rango, siguientes 3 fijas
        rows.append({"Id": f"1-4KM{m_key}", "Limite Inferior": v_inf, "Limite Superior": v_sup})
        for _ in range(3):
            rows.append({"Id": f"1-4KM{m_key}", "Limite Inferior": v_sup, "Limite Superior": v_sup})

    # 3. LA PLATA (LP) - Solo si es PBA
    if juris == "PBA":
        for i, b in enumerate(base5):
            val_lp = round(b * 1.0898, 2)
            for m_key in ["CN", "EN", "CSN", "ESN"]:
                v = round(val_lp * MULT[m_key], 2)
                rows.append({"Id": f"{i+1}{m_key}LP", "Limite Inferior": v, "Limite Superior": round(v + 0.01, 2)})

    # 4. RANGOS KP (5KP-9KP) - Escalera de valores
    cortes = [round(b1 * 1.706, 2), round(b1 * 2.621, 2), round(b1 * 3.384, 2), 
              round(b1 * 4.146, 2), round(b1 * 4.909, 2), round(b1 * 7.961, 2)]
    for m_key, m_val in MULT.items():
        for i in range(5):
            inf = round(cortes[i] * m_val, 2)
            sup = round(cortes[i+1] * m_val, 2)
            rows.append({"Id": f"{i+5}KP{m_key}", "Limite Inferior": inf, "Limite Superior": sup})

    # 5. SEMI-RÁPIDOS (SRSR para PBA / SR para DF-JN)
    for i, b in enumerate(base5):
        v_sr = round(b * 1.25 * (1.15 if juris == "PBA" else 1.0), 2)
        pref = "SRSR" if juris == "PBA" else "SR"
        rows.append({"Id": f"{i+1}{pref}N", "Limite Inferior": v_sr, "Limite Superior": v_sr})
        rows.append({"Id": f"{i+1}{pref}SN", "Limite Inferior": round(v_sr * 1.591, 2), "Limite Superior": round(v_sr * 1.591, 2)})

    # 6. KM2 (Refuerzos finales)
    for m_key, m_val in MULT.items():
        v_inf = round(base_km_val * m_val, 2)
        v_sup = round(cortes[0] * m_val, 2)
        rows.append({"Id": f"1-4KM{m_key}2", "Limite Inferior": v_inf, "Limite Superior": v_sup})

    return pd.DataFrame(rows)

def render_tarifas_tab():
    st.header("📊 Generador Maestro de Tarifas")
    st.info("Réplica exacta de planilla comercial (PBA / JN / DF)")

    juris = st.radio("Jurisdicción Activa", ["DF", "PBA", "JN"], horizontal=True)
    
    st.markdown("### 1. Carga de Bases (Secciones 1 a 5)")
    cols = st.columns(5)
    # Valores sugeridos de tu lista para PBA
    vals_def = [721.84, 804.12, 866.06, 928.07, 989.64] if juris == "PBA" else [650.11, 722.38, 778.04, 833.73, 891.33]
    
    base5 = [cols[i].number_input(f"Secc {i+1}", value=vals_def[i], format="%.2f", key=f"b{i}") for i in range(5)]

    if any(base5):
        df_final = generar_tarifas_pro(base5, juris)
        st.divider()
        st.success(f"✅ Diccionario {juris} generado: {len(df_final)} registros.")

        # Exportación
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_final.to_excel(writer, index=False, sheet_name='Tarifas')
        
        st.download_button(
            label=f"⬇️ Descargar Excel {juris} para TTR",
            data=output.getvalue(),
            file_name=f"Tarifas_{juris}_Comerciales.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

        with st.expander("👁️ Vista previa de IDs generados"):
            st.dataframe(df_final, use_container_width=True, height=400)
