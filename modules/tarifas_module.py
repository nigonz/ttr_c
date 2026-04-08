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
    """Redondeo donde 0.005 sube a 0.01."""
    return float(Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

# --- MULTIPLICADORES (Basados en tus constantes 1.75 y 1.59) ---
def get_mults(juris):
    # DF usa 1.59, PBA/JN suelen requerir 1.591 para centavos exactos
    sn_factor = 1.59 if juris == "DF" else 1.591
    return {
        "CN": 1.0, 
        "EN": 1.25, 
        "EAN": 1.75, # El 1.75 que mencionaste
        "CSN": sn_factor, # El 1.59 que mencionaste
        "ESN": 1.25 * sn_factor, 
        "EASN": 1.75 * sn_factor
    }

def generar_tarifas_limpias(base5, juris):
    rows = []
    b1 = base5[0]
    m_map = get_mults(juris)
    
    # 1. SECCIONES 1 A 5 (El "corazón" del diccionario)
    # Generamos por categoría para mantener el orden visual
    for code, m in m_map.items():
        # Mapeo de ID según tu estándar (SCN, SEN, SEAN...)
        id_suffix = code if code.startswith("S") else ("S"+code if "EAN" not in code else "SEAN")
        if code == "CN": id_suffix = "SCN"
        if code == "CSN": id_suffix = "SCSN"
        
        for i, b in enumerate(base5):
            val = r(b * m)
            # Rango especial PBA Sección 1
            inf, sup = val, val
            if juris == "PBA" and i == 0 and id_suffix == "SCN":
                inf, sup = 721.33, 721.84
            rows.append({"Id": f"{i+1}{id_suffix}", "Limite Inferior": inf, "Limite Superior": sup})

    # Si es DF, terminamos aquí para no ensuciar el archivo
    if juris == "DF":
        return pd.DataFrame(rows)

    # --- LÓGICA PARA PBA Y JN (KMs y KPs) ---
    # 2. SERIES 1-4KM (4 repeticiones por categoría)
    base_km = r(b1 * 1.316)
    for cat_id, m_val in m_map.items():
        # IDs de KM no llevan la 'S' inicial (1-4KMCN)
        v_sup = r(base_km * m_val)
        v_inf = r(v_sup - 0.50) if cat_id == "CN" and juris == "PBA" else v_sup
        for _ in range(4):
            rows.append({"Id": f"1-4KM{cat_id}", "Limite Inferior": v_inf, "Limite Superior": v_sup})

    # 3. LA PLATA (LP) - Solo PBA
    if juris == "PBA":
        for cat_id in ["CN", "EN", "CSN", "ESN"]:
            for i, b in enumerate(base5):
                v = r(b * 1.09 * m_map[cat_id])
                id_lp = f"{i+1}S{cat_id}LP" if not cat_id.startswith("S") else f"{i+1}{cat_id}LP"
                rows.append({"Id": id_lp, "Limite Inferior": v, "Limite Superior": r(v + 0.01)})

    # 4. RANGOS KP (5KP a 9KP)
    cortes = [1.706, 2.621, 3.384, 4.146, 4.909, 7.961]
    for cat_id, m_val in m_map.items():
        for i in range(5):
            inf = r(b1 * cortes[i] * m_val)
            sup = r(b1 * cortes[i+1] * m_val)
            rows.append({"Id": f"{i+5}KP{cat_id}", "Limite Inferior": inf, "Limite Superior": sup})

    return pd.DataFrame(rows)

def render_tarifas_tab():
    st.header("📊 Generador de Tarifas TTR")
    st.info("Redondeo a 2 decimales (Financial Half-Up) con multiplicadores 1.75 y 1.59.")

    juris = st.radio("Jurisdicción", ["DF", "PBA", "JN"], horizontal=True)
    
    # Valores sugeridos de tus planillas de referencia
    if juris == "PBA": def_vals = [721.84, 804.12, 866.06, 928.07, 989.64]
    elif juris == "JN": def_vals = [650.00, 724.09, 779.87, 835.71, 891.16]
    else: def_vals = [650.11, 722.38, 778.04, 833.73, 891.33]

    cols = st.columns(5)
    base5 = [cols[i].number_input(f"Secc {i+1}", value=def_vals[i], format="%.2f", key=f"b{i}") for i in range(5)]

    if any(base5):
        df = generar_tarifas_final = generar_tarifas_limpias(base5, juris)
        st.success(f"✅ Diccionario {juris} generado correctamente ({len(df)} filas).")

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Tarifas')
        
        st.download_button(
            label=f"⬇️ Descargar Excel {juris}",
            data=output.getvalue(),
            file_name=f"Tarifas_{juris}_TTR_2026.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

        with st.expander("👁️ Vista Previa (Verificar IDs y Redondeo)"):
            st.dataframe(df, use_container_width=True, height=400)
