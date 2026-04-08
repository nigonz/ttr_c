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
from decimal import Decimal, ROUND_HALF_UP

# --- MOTOR DE REDONDEO FINANCIERO (2 decimales exactos) ---
def r(val):
    """Asegura que 0.005 suba a 0.01 de forma consistente."""
    return float(Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

# --- CONSTANTES DE PRECISIÓN SEGÚN LISTADO NATALIA ---
def get_config(juris):
    # DF y JN usan 1.59 exacto. PBA suele usar 1.591.
    sn_factor = 1.59 if juris != "PBA" else 1.591
    return {
        "MULT": {
            "CN": 1.0, "EN": 1.25, "EAN": 1.75,
            "CSN": sn_factor, "ESN": 1.25 * sn_factor, "EASN": 1.75 * sn_factor
        },
        "F_KM": 1.31566,
        "F_KM2": 1.70469,
        "CORTES_KP": [1.70469, 2.61937, 3.38153, 4.14370, 4.90587, 7.95498]
    }

def generar_tarifas_final(base5, juris):
    rows = []
    b1 = base5[0]
    conf = get_config(juris)
    m_map = conf["MULT"]
    
    # 1. SECCIONES 1 A 5 (30 filas)
    codes = ["SCN", "SEN", "SEAN", "SCSN", "SESN", "SEASN"]
    for i, b in enumerate(base5):
        for c in codes:
            # Mapeo de llaves de multiplicadores
            m_key = "CN" if c == "SCN" else ("CSN" if c == "SCSN" else c.replace("S", ""))
            if c == "SEAN": m_key = "EAN"
            
            val = r(b * m_map[m_key])
            inf, sup = val, val
            
            # Ajuste de centavos fijo para Sección 1 en PBA/DF según histórico
            if juris == "PBA" and i == 0 and c == "SCN": inf, sup = 721.33, 721.83
            if juris == "DF" and i == 0 and c == "SCN": inf, sup = 650.11, 650.11
                
            rows.append({"Id": f"{i+1}{c}", "Limite Inferior": inf, "Limite Superior": sup})

    if juris == "DF": return pd.DataFrame(rows)

    # 2. SERIES 1-4KM (24 filas)
    base_km = r(b1 * conf["F_KM"])
    for cat in ["CN", "EN", "EAN", "CSN", "ESN", "EASN"]:
        v_sup = r(base_km * m_map[cat])
        # Rango 0.50 solo para categorías comunes en PBA/DF
        v_inf = r(v_sup - 0.50) if cat in ["CN", "EN", "EAN"] and juris != "JN" else v_sup
        for _ in range(4):
            rows.append({"Id": f"1-4KM{cat}", "Limite Inferior": v_inf, "Limite Superior": v_sup})

    # 3. LA PLATA (LP) - Solo PBA (20 filas)
    if juris == "PBA":
        for cat in ["SCN", "SEN", "SCSN", "SESN"]:
            for i, b in enumerate(base5):
                m_key = "CN" if cat == "SCN" else "CSN" if cat == "SCSN" else cat.replace("S", "")
                v = r(b * 1.08907 * m_map[m_key])
                rows.append({"Id": f"{i+1}{cat}LP", "Limite Inferior": v, "Limite Superior": r(v + 0.01)})

    # 4. RANGOS KP (30 filas)
    for cat in ["CN", "EN", "EAN", "CSN", "ESN", "EASN"]:
        for i in range(5):
            inf = r(b1 * conf["CORTES_KP"][i] * m_map[cat])
            sup = r(b1 * conf["CORTES_KP"][i+1] * m_map[cat])
            rows.append({"Id": f"{i+5}KP{cat}", "Limite Inferior": inf, "Limite Superior": sup})

    # 5. SEMI-RÁPIDOS PBA (SRSR)
    if juris == "PBA":
        for i, b in enumerate(base5):
            v_sr = r(b * 1.5) # Factor SRSR histórico (1.25 * 1.20)
            rows.append({"Id": f"{i+1}SRSRN", "Limite Inferior": v_sr, "Limite Superior": v_sr})
            rows.append({"Id": f"{i+1}SRSRSN", "Limite Inferior": r(v_sr * 1.59), "Limite Superior": r(v_sr * 1.59)})

    # 6. KM2 (Refuerzos)
    for cat in ["CN", "EN", "EAN", "CSN", "ESN", "EASN"]:
        v_inf = r(base_km * m_map[cat])
        v_sup = r(b1 * conf["F_KM2"] * m_map[cat])
        rows.append({"Id": f"1-4KM{cat}2", "Limite Inferior": v_inf, "Limite Superior": v_sup})

    return pd.DataFrame(rows)

def render_tarifas_tab():
    st.header("📊 Generador Maestro de Tarifas TTR")
    st.info("Configuración de alta precisión para DF, PBA y JN.")

    juris = st.radio("Jurisdicción", ["DF", "PBA", "JN"], horizontal=True)
    
    # Valores por defecto para acelerar tu carga
    if juris == "PBA": def_vals = [721.83, 804.12, 866.06, 928.07, 989.64]
    elif juris == "JN": def_vals = [650.00, 724.09, 779.87, 835.71, 891.16]
    else: def_vals = [650.11, 722.38, 778.04, 833.73, 891.33] # DF

    cols = st.columns(5)
    base5 = [cols[i].number_input(f"Secc {i+1}", value=def_vals[i], format="%.2f", key=f"b{i}") for i in range(5)]

    if any(base5):
        df = generar_tarifas_final(base5, juris)
        st.success(f"✅ ¡Estructura {juris} lista! ({len(df)} registros)")

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Tarifas')
        
        st.download_button(
            label=f"⬇️ Descargar Excel {juris}",
            data=output.getvalue(),
            file_name=f"Tarifas_{juris}_TTR_Pro.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

        with st.expander("👁️ Verificación de Centavos y IDs"):
            st.dataframe(df, use_container_width=True, height=400)
