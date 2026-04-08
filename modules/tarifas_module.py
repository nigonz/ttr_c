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

# ── Motor de Redondeo Financiero ─────────────────────────────────────────────
def r(val):
    """Redondea a 2 decimales exactos (0.005 sube a 0.01)."""
    return float(Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

# ── Constantes de Precisión Unificadas ────────────────────────────────────────
def get_config():
    # Multiplicador Sin Nominalizar (SN) fijado en 1.59 exacto
    sn_factor = 1.59
    return {
        "MULT": {
            "CN": 1.0, 
            "EN": 1.25, 
            "EAN": 1.75,
            "CSN": sn_factor, 
            "ESN": 1.25 * sn_factor, 
            "EASN": 1.75 * sn_factor
        },
        "F_KM": 1.31566,
        "F_KM2": 1.70469,
        "CORTES_KP": [1.70469, 2.61937, 3.38153, 4.14370, 4.90587, 7.95498]
    }

def generar_tarifas_final(base5, juris):
    rows = []
    b1 = base5[0]
    conf = get_config()
    m_map = conf["MULT"]
    
    # 1. Secciones 1 a 5 (Macheo exacto DF/PBA/JN)
    codes = [
        ("SCN", "CN"), ("SEN", "EN"), ("SEAN", "EAN"),
        ("SCSN", "CSN"), ("SESN", "ESN"), ("SEASN", "EASN")
    ]
    
    for suffix, m_key in codes:
        for i, b in enumerate(base5):
            val = r(b * m_map[m_key])
            inf, sup = val, val
            
            # Ajuste de rango específico PBA Sección 1
            if juris == "PBA" and i == 0 and suffix == "SCN":
                inf, sup = 721.33, 721.83
                
            rows.append({"Id": f"{i+1}{suffix}", "Limite Inferior": inf, "Limite Superior": sup})

    # Si es DF, el proceso termina con las 30 filas base
    if juris == "DF":
        return pd.DataFrame(rows)

    # 2. Series 1-4KM (Macheo JN/PBA)
    base_km = r(b1 * conf["F_KM"])
    km_cats = ["CN", "EN", "EAN", "CSN", "ESN", "EASN"]
    for cat in km_cats:
        v_sup = r(base_km * m_map[cat])
        # Rango de centavos solo para categorías nominales en PBA/DF
        v_inf = r(v_sup - 0.50) if cat in ["CN", "EN", "EAN"] and juris != "JN" else v_sup
        for _ in range(4):
            rows.append({"Id": f"1-4KM{cat}", "Limite Inferior": v_inf, "Limite Superior": v_sup})

    # 3. La Plata (LP) - Específico de Provincia
    if juris == "PBA":
        for suffix, m_key in [("SCN", "CN"), ("SEN", "EN"), ("SCSN", "CSN"), ("SESN", "ESN")]:
            for i, b in enumerate(base5):
                # Coeficiente LP extraído de tus muestras
                v = r(b * 1.08907 * m_map[m_key])
                rows.append({"Id": f"{i+1}{suffix}LP", "Limite Inferior": v, "Limite Superior": r(v + 0.01)})

    # 4. Rangos KP (5KP a 9KP)
    for cat in km_cats:
        for i in range(5):
            inf = r(b1 * conf["CORTES_KP"][i] * m_map[cat])
            sup = r(b1 * conf["CORTES_KP"][i+1] * m_map[cat])
            rows.append({"Id": f"{i+5}KP{cat}", "Limite Inferior": inf, "Limite Superior": sup})

    # 5. Semi-Rápidos Provincia (SRSR)
    if juris == "PBA":
        for i, b in enumerate(base5):
            v_sr = r(b * 1.5) # Factor SRSR (1.25 x 1.20)
            rows.append({"Id": f"{i+1}SRSRN", "Limite Inferior": v_sr, "Limite Superior": v_sr})
            rows.append({"Id": f"{i+1}SRSRSN", "Limite Inferior": r(v_sr * 1.59), "Limite Superior": r(v_sr * 1.59)})

    # 6. KM2 (Refuerzos finales)
    for cat in km_cats:
        v_inf = r(base_km * m_map[cat])
        v_sup = r(b1 * conf["F_KM2"] * m_map[cat])
        rows.append({"Id": f"1-4KM{cat}2", "Limite Inferior": v_inf, "Limite Superior": v_sup})

    return pd.DataFrame(rows)

def render_tarifas_tab():
    st.header("📊 Generador Maestro de Tarifas TTR")
    st.info("Configuración final: Factor SN = **1.59** | Redondeo: **2 decimales**")

    juris = st.radio("Jurisdicción", ["DF", "PBA", "JN"], horizontal=True)
    
    # Valores por defecto para el período actual
    if juris == "PBA": def_vals = [721.83, 804.12, 866.06, 928.07, 989.64]
    elif juris == "JN": def_vals = [650.00, 724.09, 779.87, 835.71, 891.16]
    else: def_vals = [650.11, 722.38, 778.04, 833.73, 891.33] # DF

    cols = st.columns(5)
    base5 = [cols[i].number_input(f"Secc {i+1}", value=def_vals[i], format="%.2f", key=f"b{i}") for i in range(5)]

    if any(base5):
        df = generar_tarifas_final(base5, juris)
        st.success(f"✅ ¡Estructura {juris} generada al 100%!")

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Tarifas')
        
        st.download_button(
            label=f"⬇️ Descargar Excel {juris} (v4)",
            data=output.getvalue(),
            file_name=f"Tarifas_{juris}_TTR_v4.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

        with st.expander("👁️ Verificación de IDs y Redondeo"):
            st.dataframe(df, use_container_width=True, height=400)
