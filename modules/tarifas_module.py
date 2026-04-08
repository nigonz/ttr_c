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
import json
from datetime import datetime

# ---------------------------------------------------------------------------
# CONSTANTES
# ---------------------------------------------------------------------------
TIPOS = ["DF", "JN", "PBA"]

SECCIONES_KM = {
    1: "0-3 km",
    2: "3-6 km",
    3: "6-12 km",
    4: "12-27 km",
    5: "27-45 km",
    6: "45-60 km",
    7: "60-75 km",
    8: "75-90 km",
    9: "90-150 km",
}

MULTIPLICADORES = {
    "COMUN_N":    1.00,   # base (tipeo manual secciones 1-5)
    "EXPRESO_N":  1.25,
    "EPA_N":      1.75,   # Expreso Por Autopista
    "COMUN_SN":   1.59,   # Sin Nominalizar
    "EXPRESO_SN": 1.25 * 1.59,  # = 1.9875
    "EPA_SN":     1.75 * 1.59,  # = 2.7825
}

MESES_ESP = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}

TARIFA_LABELS = [f"Secc. {i} ({SECCIONES_KM[i]})" for i in range(1, 6)]

# ---------------------------------------------------------------------------
# HELPERS - CÁLCULO
# ---------------------------------------------------------------------------

def calcular_todas_tarifas(base5: list[float]) -> dict:
    """
    Dado un array de 5 tarifas base (COMUN_N secciones 1-5),
    devuelve dict con todas las categorías calculadas.
    Sections 6-9 quedan en 0.
    """
    def make_9(vals_5):
        return list(vals_5) + [0.0, 0.0, 0.0, 0.0]

    result = {}
    base_comun_n  = [float(v or 0) for v in base5]
    base_comun_sn = [v * 1.59 for v in base_comun_n]

    result["COMUN_N"]    = make_9(base_comun_n)
    result["EXPRESO_N"]  = make_9([v * 1.25 for v in base_comun_n])
    result["EPA_N"]      = make_9([v * 1.75 for v in base_comun_n])
    result["COMUN_SN"]   = make_9(base_comun_sn)
    result["EXPRESO_SN"] = make_9([v * 1.25 for v in base_comun_sn])
    result["EPA_SN"]     = make_9([v * 1.75 for v in base_comun_sn])
    return result


def calcular_factor_variacion(prev5: list[float], curr5: list[float]) -> float | None:
    """Calcula el factor de variación entre dos períodos (primera sección como referencia)."""
    try:
        if prev5 and prev5[0] and curr5 and curr5[0]:
            return (curr5[0] / prev5[0]) - 1
    except (ZeroDivisionError, TypeError, IndexError):
        pass
    return None


# ---------------------------------------------------------------------------
# ESTADO DE LA SESIÓN
# ---------------------------------------------------------------------------

def _init_state():
    """Inicializa el estado de la sesión si no existe."""
    if "tarifas_periodos" not in st.session_state:
        # Estructura: {"periodos": [...], "tipo_activo": "DF", ...}
        st.session_state.tarifas_periodos = []
        st.session_state.tarifas_tipo_activo = "DF"
        st.session_state.tarifas_show_sn = False
        st.session_state.tarifas_show_factor = True


def _guardar_periodo(nuevo_periodo: dict):
    """Agrega o actualiza un período en la lista."""
    periodos = st.session_state.tarifas_periodos
    # Buscar si ya existe (mismo tipo + año + mes + reso)
    key = (nuevo_periodo["tipo"], nuevo_periodo["anio"],
           nuevo_periodo["mes"], nuevo_periodo.get("reso", ""))
    for i, p in enumerate(periodos):
        pk = (p["tipo"], p["anio"], p["mes"], p.get("reso", ""))
        if pk == key:
            periodos[i] = nuevo_periodo
            st.session_state.tarifas_periodos = periodos
            return
    periodos.append(nuevo_periodo)
    st.session_state.tarifas_periodos = periodos


def _get_periodos_tipo(tipo: str) -> list[dict]:
    return [p for p in st.session_state.tarifas_periodos if p["tipo"] == tipo]


# ---------------------------------------------------------------------------
# UI: INGRESO DE PERÍODO
# ---------------------------------------------------------------------------

def _ui_ingreso_periodo():
    """Formulario para ingresar un nuevo período."""
    st.subheader("➕ Ingresar nuevo período")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        tipo = st.selectbox("Tipo", TIPOS, key="new_tipo",
                            index=TIPOS.index(st.session_state.tarifas_tipo_activo))
    with col2:
        anio = st.number_input("Año", min_value=2020, max_value=2030,
                               value=datetime.now().year, step=1, key="new_anio")
    with col3:
        mes_nombre = st.selectbox("Mes", list(MESES_ESP.values()), key="new_mes",
                                  index=datetime.now().month - 1)
        mes_num = {v: k for k, v in MESES_ESP.items()}[mes_nombre]
    with col4:
        reso = st.text_input("N° Resolución", value="", key="new_reso",
                             placeholder="ej: 125/2024")

    st.markdown("**5 tarifas base** — COMUN Nominalizadas (Secciones 1 a 5)")

    cols = st.columns(5)
    base5 = []
    for i, col in enumerate(cols):
        with col:
            v = col.number_input(
                TARIFA_LABELS[i],
                min_value=0.0, value=0.0, step=0.01,
                format="%.2f", key=f"base_{i}"
            )
            base5.append(v)

    # Factor opcional
    st.markdown("**Factor de actualización** (opcional — se calcula automático si hay período previo)")
    factor_manual = st.number_input(
        "Factor % (ej: 5.80 para 5.80%)", value=0.0, step=0.01,
        format="%.4f", key="factor_manual",
        help="Porcentaje de aumento respecto al período anterior. Dejar en 0 para calcular automáticamente."
    )

    if st.button("💾 Guardar período", type="primary", key="btn_guardar"):
        if all(v == 0 for v in base5):
            st.warning("Ingresá al menos una tarifa base distinta de 0.")
            return

        tarifas_calc = calcular_todas_tarifas(base5)

        # Factor: usar manual si se proporcionó, sino calcular desde prev
        prevs = _get_periodos_tipo(tipo)
        factor = factor_manual / 100 if factor_manual != 0 else None
        if factor is None and prevs:
            prev_base = prevs[-1].get("base5", [0]*5)
            factor = calcular_factor_variacion(prev_base, base5)

        nuevo = {
            "tipo":  tipo,
            "anio":  int(anio),
            "mes":   mes_num,
            "reso":  reso,
            "base5": base5,
            "factor": factor,
            "tarifas": tarifas_calc,
            "ts":    datetime.now().isoformat(),
        }
        _guardar_periodo(nuevo)
        st.success(f"✅ Período {mes_nombre} {int(anio)} ({tipo}) guardado.")
        st.rerun()


# ---------------------------------------------------------------------------
# UI: TABLA DE RESULTADOS
# ---------------------------------------------------------------------------

def _fmt(v: float) -> str:
    if v == 0:
        return "–"
    return f"$ {v:,.2f}"


def _ui_tabla_periodo(periodo: dict, mostrar_sn: bool):
    """Muestra la tabla de tarifas de un período."""
    tarifas = periodo.get("tarifas", {})
    if not tarifas:
        st.info("Sin datos.")
        return

    labels_seccion = [SECCIONES_KM[i] for i in range(1, 10)]

    categorias_n = {
        "COMUN":            tarifas.get("COMUN_N",   [0]*9),
        "EXPRESO (×1.25)":  tarifas.get("EXPRESO_N", [0]*9),
        "E.AUTOPISTA (×1.75)": tarifas.get("EPA_N",  [0]*9),
    }
    categorias_sn = {
        "COMUN SN":            tarifas.get("COMUN_SN",   [0]*9),
        "EXPRESO SN (×1.25)":  tarifas.get("EXPRESO_SN", [0]*9),
        "E.AUTOPISTA SN (×1.75)": tarifas.get("EPA_SN",  [0]*9),
    }

    cats = {**categorias_n, **(categorias_sn if mostrar_sn else {})}

    rows = []
    for cat, vals in cats.items():
        row = {"Categoría": cat}
        for i, sec in enumerate(labels_seccion):
            row[sec] = _fmt(vals[i])
        rows.append(row)

    df = pd.DataFrame(rows).set_index("Categoría")
    st.dataframe(df, use_container_width=True)


def _ui_tabla_comparativa(tipo: str, mostrar_sn: bool):
    """Tabla comparativa de TODAS las secciones 1 de todos los períodos (vista histórica)."""
    periodos = _get_periodos_tipo(tipo)
    if not periodos:
        return

    rows = []
    for p in periodos:
        mes = MESES_ESP.get(p["mes"], p["mes"])
        label = f"{mes} {p['anio']}"
        factor_str = f"{p['factor']*100:.2f}%" if p.get("factor") is not None else "–"
        b = p.get("base5", [0]*5)
        row = {
            "Período":  label,
            "Reso":     p.get("reso", ""),
            "Factor %": factor_str,
            "COMUN S1": _fmt(b[0] if b else 0),
            "COMUN S2": _fmt(b[1] if len(b)>1 else 0),
            "COMUN S3": _fmt(b[2] if len(b)>2 else 0),
            "COMUN S4": _fmt(b[3] if len(b)>3 else 0),
            "COMUN S5": _fmt(b[4] if len(b)>4 else 0),
        }
        rows.append(row)

    df = pd.DataFrame(rows).set_index("Período")
    st.dataframe(df, use_container_width=True)


# ---------------------------------------------------------------------------
# UI: EXPORTAR / IMPORTAR JSON
# ---------------------------------------------------------------------------

def _ui_export_import():
    """Exportar e importar datos en JSON."""
    with st.expander("📤 Exportar / 📥 Importar datos"):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Exportar**")
            data_json = json.dumps(st.session_state.tarifas_periodos,
                                   ensure_ascii=False, indent=2)
            st.download_button(
                "⬇️ Descargar JSON",
                data=data_json,
                file_name=f"tarifas_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                mime="application/json"
            )

        with col2:
            st.markdown("**Importar**")
            uploaded = st.file_uploader("Subir JSON exportado", type="json",
                                        key="import_json")
            if uploaded:
                try:
                    datos = json.load(uploaded)
                    st.session_state.tarifas_periodos = datos
                    st.success(f"✅ {len(datos)} períodos importados.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al importar: {e}")


# ---------------------------------------------------------------------------
# UI PRINCIPAL
# ---------------------------------------------------------------------------

def render_tarifas_tab():
    """
    Función principal del módulo. Llamar desde tu app Streamlit existente.

    Ejemplo de uso en tu app:
        import tarifas_module
        with tab_tarifas:
            tarifas_module.render_tarifas_tab()
    """
    _init_state()

    st.header("📊 Tarifas Comerciales")
    st.caption("Módulo de carga y cálculo automático de tarifas — DF / JN / PBA")

    # Controles globales
    col_opts1, col_opts2, col_opts3 = st.columns([2, 2, 4])
    with col_opts1:
        st.session_state.tarifas_tipo_activo = st.radio(
            "Tipo activo", TIPOS, horizontal=True,
            index=TIPOS.index(st.session_state.tarifas_tipo_activo),
            key="radio_tipo"
        )
    with col_opts2:
        st.session_state.tarifas_show_sn = st.toggle(
            "Mostrar Sin Nominalizar (×1.59)", value=st.session_state.tarifas_show_sn
        )

    tipo_activo = st.session_state.tarifas_tipo_activo
    mostrar_sn  = st.session_state.tarifas_show_sn

    st.divider()

    # Ingreso
    _ui_ingreso_periodo()

    st.divider()

    # Vista histórica comparativa
    periodos_tipo = _get_periodos_tipo(tipo_activo)

    if not periodos_tipo:
        st.info(f"No hay períodos cargados para **{tipo_activo}**. Ingresá el primero arriba.")
        _ui_export_import()
        return

    st.subheader(f"📋 Histórico de tarifas base — {tipo_activo}")
    _ui_tabla_comparativa(tipo_activo, mostrar_sn)

    st.divider()

    # Detalle por período
    st.subheader(f"🔎 Detalle por período — {tipo_activo}")

    # Selector de período
    opciones = []
    for p in reversed(periodos_tipo):
        mes = MESES_ESP.get(p["mes"], p["mes"])
        opciones.append(f"{mes} {p['anio']} | Reso: {p.get('reso', '-')}")

    sel_label = st.selectbox("Seleccionar período:", opciones, key="sel_periodo")
    sel_idx   = opciones.index(sel_label)
    periodo_sel = list(reversed(periodos_tipo))[sel_idx]

    # Mostrar factor
    factor = periodo_sel.get("factor")
    if factor is not None:
        delta_color = "green" if factor >= 0 else "red"
        st.metric(
            label=f"Factor de actualización ({MESES_ESP.get(periodo_sel['mes'])} {periodo_sel['anio']})",
            value=f"{factor*100:.4f}%",
            delta=f"{'↑' if factor>=0 else '↓'} respecto período anterior"
        )
    else:
        st.caption("Factor: no calculado (primer período o sin dato previo)")

    # Tabla completa del período seleccionado
    _ui_tabla_periodo(periodo_sel, mostrar_sn)

    # Botón eliminar período
    if st.button("🗑️ Eliminar este período", key="btn_eliminar"):
        st.session_state.tarifas_periodos = [
            p for p in st.session_state.tarifas_periodos
            if not (p["tipo"] == periodo_sel["tipo"] and
                    p["anio"] == periodo_sel["anio"] and
                    p["mes"]  == periodo_sel["mes"])
        ]
        st.success("Período eliminado.")
        st.rerun()

    st.divider()
    _ui_export_import()


# ---------------------------------------------------------------------------
# MODO STANDALONE (para probar este módulo solo)
# ---------------------------------------------------------------------------

def show():
    """Ejecuta el módulo como app standalone."""
    st.set_page_config(
        page_title="Tarifas Comerciales",
        page_icon="📊",
        layout="wide"
    )
    render_tarifas_tab()


if __name__ == "__main__":
    show()
