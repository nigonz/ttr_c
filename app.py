"""
app.py
------
Aplicación TTR — Cálculo automático de tarifas DF / PBA / JN
Streamlit app que reemplaza los 3 notebooks con tarifas dinámicas desde Excel.
"""

import io
import sys
import os
import traceback


import pandas as pd
import streamlit as st

# ── Path setup ───────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

from modules.tariff_loader import load_tarifas, get_filtro1_threshold
from modules.process_df import process_df
from modules.process_pba_jn import process_pba_jn
from modules.tarifas_module import render_tarifas_tab


# ────────────────────────────────────────────────────────────────────────────────
#  Config & estilos
# ────────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="TTR · Calculadora de Tarifas",
    page_icon="🚌",
    layout="wide",
)

st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding: 0 24px;
        background-color: #f0f2f6;
        border-radius: 8px 8px 0 0;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1f77b4;
        color: white;
    }
    div[data-testid="stExpander"] > div { border: 1px solid #e0e0e0; border-radius: 8px; }
    .metric-card {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────────────
#  Helpers
# ────────────────────────────────────────────────────────────────────────────────

def to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Base") -> bytes:
    """Convierte un DataFrame a bytes de Excel."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return buf.getvalue()


def show_tarifa_preview(tarifas: dict):
    """Muestra resumen de las tarifas cargadas."""
    rows = []
    for k, (lo, hi) in tarifas.items():
        rows.append({"Id": k, "Límite Inferior": lo, "Límite Superior": hi})
    df_prev = pd.DataFrame(rows)
    with st.expander(f"📋 Vista previa del diccionario de tarifas ({len(tarifas)} registros)"):
        st.dataframe(df_prev, use_container_width=True, height=300)


def show_stats(df: pd.DataFrame, label: str):
    """Muestra métricas básicas del resultado."""
    cols = st.columns(4)
    with cols[0]:
        st.metric("Registros totales", f"{len(df):,}")
    with cols[1]:
        if 'CANTIDAD_USOS' in df.columns:
            st.metric("Total usos", f"{df['CANTIDAD_USOS'].sum():,.0f}")
    with cols[2]:
        if 'Recaudacion_TRSUBE' in df.columns:
            st.metric("Recaudación TRSUBE", f"${df['Recaudacion_TRSUBE'].sum():,.0f}")
    with cols[3]:
        if 'final_seccion' in df.columns:
            unclassified = (df['final_seccion'] == 0).sum()
            st.metric("Sin clasificar (sec=0)", f"{unclassified:,}", delta_color="inverse")


def sidebar_config():
    """Configuración global en sidebar."""
    with st.sidebar:
        st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Argentina_Buenos_Aires_Bus.svg/120px-Argentina_Buenos_Aires_Bus.svg.png",
                 width=80, caption=None)
        st.title("⚙️ Configuración")
        st.markdown("---")
        year = st.number_input("Año resolución", value=2026, step=1, min_value=2020, max_value=2035)
        resolucion = st.text_input("Número de resolución", value="16")
        st.markdown("---")
        st.caption("TTR Calculadora v1.0 · Tarifas dinámicas desde Excel")
    return int(year), resolucion


# ────────────────────────────────────────────────────────────────────────────────
#  UI de cada proceso
# ────────────────────────────────────────────────────────────────────────────────

def tab_df(year, resolucion):
    st.header("🏙️ Distrito Federal (DF)")
    st.info("Filtra GT = **DF**. Proceso simple: solo tarifas seccionadas (no KM/KP).")

    c1, c2 = st.columns(2)
    with c1:
        f_dggi = st.file_uploader("📂 Archivo DGGI principal (.xlsx)", type=["xlsx"], key="df_dggi")
        f_nom_ts = st.file_uploader("📂 Nomenclador Ramal-TS (.xlsx)", type=["xlsx"], key="df_ts")
    with c2:
        f_nom_gt = st.file_uploader("📂 Nomenclador GT (.xlsx)", type=["xlsx"], key="df_gt")
        f_tarifas = st.file_uploader("📂 Diccionario de Tarifas (.xlsx)", type=["xlsx"], key="df_tar")
        f_ttr = st.file_uploader("📂 TTR Teórica Resoluciones (.xlsx)", type=["xlsx"], key="df_ttr")

    col_a, col_b = st.columns([1, 3])
    with col_a:
        sheet_ttr = st.text_input("Hoja TTR", value="TTR", key="df_ttr_sheet")

    if st.button("🚀 Procesar DF", type="primary", key="btn_df"):
        if not all([f_dggi, f_nom_ts, f_nom_gt, f_tarifas, f_ttr]):
            st.error("⚠️ Por favor cargá todos los archivos antes de procesar.")
            return

        with st.spinner("Procesando..."):
            try:
                df1 = pd.read_excel(f_dggi)
                nom_ts = pd.read_excel(f_nom_ts)
                nom_gt = pd.read_excel(f_nom_gt)
                ttr_reso = pd.read_excel(f_ttr, sheet_name=sheet_ttr)
                tarifas = load_tarifas(f_tarifas)

                show_tarifa_preview(tarifas)

                result = process_df(
                    df1=df1,
                    nom_ts=nom_ts,
                    nom_gt=nom_gt,
                    tarifas=tarifas,
                    ttr_reso=ttr_reso,
                    year=year,
                    resolucion=resolucion
                )

                st.success(f"✅ Proceso DF completado. {len(result):,} registros procesados.")
                show_stats(result, "DF")

                xlsx_bytes = to_excel_bytes(result, sheet_name="DF")
                st.download_button(
                    label="⬇️ Descargar resultado DF (.xlsx)",
                    data=xlsx_bytes,
                    file_name=f"TTR_DF_{year}_{resolucion}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

                with st.expander("👁️ Vista previa resultado (primeras 100 filas)"):
                    st.dataframe(result.head(100), use_container_width=True)

            except Exception as e:
                st.error(f"❌ Error durante el procesamiento:\n\n{e}")
                with st.expander("Traceback"):
                    st.code(traceback.format_exc())


def tab_pba(year, resolucion):
    st.header("🌿 Provincia de Buenos Aires (PBA)")
    st.info("Filtra GT = **UPA, UPAKM, UMA1, UMA2**. Incluye tarifas KM, KP, LP, SR.")

    c1, c2 = st.columns(2)
    with c1:
        f_dggi = st.file_uploader("📂 Archivo DGGI principal (.xlsx)", type=["xlsx"], key="pba_dggi")
        f_nom_ts = st.file_uploader("📂 Nomenclador Ramal-TS (.xlsx)", type=["xlsx"], key="pba_ts")
    with c2:
        f_nom_gt = st.file_uploader("📂 Nomenclador GT (.xlsx)", type=["xlsx"], key="pba_gt")
        f_tarifas = st.file_uploader("📂 Diccionario de Tarifas PBA (.xlsx)", type=["xlsx"], key="pba_tar")
        f_ttr = st.file_uploader("📂 TTR Teórica Resoluciones (.xlsx)", type=["xlsx"], key="pba_ttr")

    col_a, col_b = st.columns(2)
    with col_a:
        sheet_ttr = st.text_input("Hoja TTR principal", value="TTR", key="pba_ttr_sheet")
    with col_b:
        sheet_sgii = st.text_input("Hoja TTR SGII-UMA2 (opcional)", value="SGII-UMA2", key="pba_sgii_sheet")

    if st.button("🚀 Procesar PBA", type="primary", key="btn_pba"):
        if not all([f_dggi, f_nom_ts, f_nom_gt, f_tarifas, f_ttr]):
            st.error("⚠️ Por favor cargá todos los archivos antes de procesar.")
            return

        with st.spinner("Procesando..."):
            try:
                df1 = pd.read_excel(f_dggi, sheet_name=0)
                nom_ts = pd.read_excel(f_nom_ts)
                nom_gt = pd.read_excel(f_nom_gt)
                tarifas = load_tarifas(f_tarifas)

                # TTR principal
                ttr_reso = pd.read_excel(f_ttr, sheet_name=sheet_ttr)

                # TTR SGII (opcional)
                ttr_sgii = None
                try:
                    ttr_sgii = pd.read_excel(f_ttr, sheet_name=sheet_sgii)
                except Exception:
                    st.warning(f"No se encontró la hoja '{sheet_sgii}'. Se usará solo la TTR principal.")

                show_tarifa_preview(tarifas)

                result = process_pba_jn(
                    df1=df1,
                    nom_ts=nom_ts,
                    nom_gt=nom_gt,
                    tarifas=tarifas,
                    ttr_reso=ttr_reso,
                    gt_values=['UPA', 'UPAKM', 'UMA1', 'UMA2'],
                    year=year,
                    resolucion=resolucion,
                    ttr_sgii=ttr_sgii,
                    apply_energia_factor=False
                )

                st.success(f"✅ Proceso PBA completado. {len(result):,} registros procesados.")
                show_stats(result, "PBA")

                xlsx_bytes = to_excel_bytes(result, sheet_name="PBA")
                st.download_button(
                    label="⬇️ Descargar resultado PBA (.xlsx)",
                    data=xlsx_bytes,
                    file_name=f"TTR_PBA_{year}_{resolucion}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

                with st.expander("👁️ Vista previa resultado (primeras 100 filas)"):
                    st.dataframe(result.head(100), use_container_width=True)

            except Exception as e:
                st.error(f"❌ Error durante el procesamiento:\n\n{e}")
                with st.expander("Traceback"):
                    st.code(traceback.format_exc())


def tab_jn(year, resolucion):
    st.header("🚌 JN / Nacional (SGI, SGII, SGIKM)")
    st.info("Filtra GT = **SGI, SGII, SGIKM**. Aplica factor ENERGIA. SGII mínimo sección 4.")

    c1, c2 = st.columns(2)
    with c1:
        f_dggi = st.file_uploader("📂 Archivo DGGI principal (.xlsx)", type=["xlsx"], key="jn_dggi")
        f_nom_ts = st.file_uploader("📂 Nomenclador Ramal-TS (.xlsx)", type=["xlsx"], key="jn_ts")
    with c2:
        f_nom_gt = st.file_uploader("📂 Nomenclador GT (.xlsx)", type=["xlsx"], key="jn_gt")
        f_tarifas = st.file_uploader("📂 Diccionario de Tarifas JN (.xlsx)", type=["xlsx"], key="jn_tar")
        f_ttr = st.file_uploader("📂 TTR Teórica Resoluciones (.xlsx)", type=["xlsx"], key="jn_ttr")

    col_a, col_b = st.columns(2)
    with col_a:
        sheet_ttr = st.text_input("Hoja TTR principal", value="TTR", key="jn_ttr_sheet")
    with col_b:
        sheet_sgii = st.text_input("Hoja TTR SGII-UMA2 (opcional)", value="SGII-UMA2", key="jn_sgii_sheet")

    st.markdown("**Factores de energía:** GNC = 1.30 · Eléctrico = 1.50 · Diesel = 1.00")

    if st.button("🚀 Procesar JN", type="primary", key="btn_jn"):
        if not all([f_dggi, f_nom_ts, f_nom_gt, f_tarifas, f_ttr]):
            st.error("⚠️ Por favor cargá todos los archivos antes de procesar.")
            return

        with st.spinner("Procesando..."):
            try:
                df1 = pd.read_excel(f_dggi)
                nom_ts = pd.read_excel(f_nom_ts)
                nom_gt = pd.read_excel(f_nom_gt)
                tarifas = load_tarifas(f_tarifas)

                ttr_reso = pd.read_excel(f_ttr, sheet_name=sheet_ttr)

                ttr_sgii = None
                try:
                    ttr_sgii = pd.read_excel(f_ttr, sheet_name=sheet_sgii)
                except Exception:
                    st.warning(f"No se encontró la hoja '{sheet_sgii}'. Se usará solo la TTR principal.")

                show_tarifa_preview(tarifas)

                result = process_pba_jn(
                    df1=df1,
                    nom_ts=nom_ts,
                    nom_gt=nom_gt,
                    tarifas=tarifas,
                    ttr_reso=ttr_reso,
                    gt_values=['SGI', 'SGII', 'SGIKM'],
                    year=year,
                    resolucion=resolucion,
                    ttr_sgii=ttr_sgii,
                    apply_energia_factor=True
                )

                st.success(f"✅ Proceso JN completado. {len(result):,} registros procesados.")
                show_stats(result, "JN")

                xlsx_bytes = to_excel_bytes(result, sheet_name="JN")
                st.download_button(
                    label="⬇️ Descargar resultado JN (.xlsx)",
                    data=xlsx_bytes,
                    file_name=f"TTR_JN_{year}_{resolucion}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

                with st.expander("👁️ Vista previa resultado (primeras 100 filas)"):
                    st.dataframe(result.head(100), use_container_width=True)

            except Exception as e:
                st.error(f"❌ Error durante el procesamiento:\n\n{e}")
                with st.expander("Traceback"):
                    st.code(traceback.format_exc())


def tab_ayuda():
    st.header("📖 Guía de uso")
    st.markdown("""
### ¿Qué hace esta aplicación?

Automatiza los 3 procesos de ingeniería inversa de tarifas TTR:
- **DF** → Distrito Federal (GT = DF)
- **PBA** → Provincia de Buenos Aires (GT = UPA, UPAKM, UMA1, UMA2)
- **JN** → Jornada Nacional (GT = SGI, SGII, SGIKM)

En lugar de tipear las tarifas a mano en el código cada período, la app **las lee del Excel de tarifas** que te compartieron.

---

### Archivos necesarios por proceso

| Archivo | Descripción |
|---------|-------------|
| **DGGI principal** | Datos del período (ej. `dggi_DMK_PME_202602.xlsx`) |
| **Nomenclador Ramal-TS** | `01. NOMENCLADOR RAMAL - TS.xlsx` |
| **Nomenclador GT** | `00. NOMENCLADOR.v2.xlsx` |
| **Diccionario de Tarifas** | El Excel de tarifas del período (DF, PBA o JN) |
| **TTR Teórica Resoluciones** | `03. TTR TEORICA RESOLUCIONES.xlsx` |

---

### Formato del Excel de Tarifas

El Excel debe tener estas columnas:
```
Id | Limite Inferior | Limite Superior
```
(o invertidas: `Limite Superior | Limite Inferior` — la app lo detecta automáticamente)

Los **Ids** deben seguir la nomenclatura estándar:
- Secciones: `1SCN`, `2SCN`, ..., `5SEASN`
- La Plata: `1SCNLP`, ..., `5SESNLP`
- KM exactas: `1-4KMCN`, `1-4KMEN`, `1-4KMEAN`, `1-4KMCSN`, ...
- KP (rango): `5KPCN`, `6KPCN`, ..., `9KPEASN`
- KM2 (rango intermedio): `1-4KMCN2`, `1-4KMEN2`, ...
- Semi-Rápido: `1SRN`, ..., `5SRSN`

---

### Configuración global

En el panel lateral podés configurar:
- **Año** y **Número de resolución**: se usan para construir las claves `CONCAT_MACHEO2` y `CONCAT_MACHEO3`

---

### Resultado

El archivo de salida `.xlsx` replica exactamente la estructura del notebook original,
con todas las columnas de clasificación (`sec_c`, `sec_e`, `final_seccion`, `compilado_ts`,
`norm_por_tarifa`, `CONCAT_MACHEO`, `Tarifa TRSUBE`, `Recaudacion_TRSUBE`, etc.).
    """)


# ────────────────────────────────────────────────────────────────────────────────
#  Main
# ────────────────────────────────────────────────────────────────────────────────

def main():
    st.title("🚌 TTR — Calculadora Automática de Tarifas")
    st.markdown(
        "Procesá **DF**, **PBA** y **JN** cargando los archivos del período. "
        "Las tarifas se leen del Excel de tarifas — **sin hardcodeo**."
    )

    year, resolucion = sidebar_config()

    # Reordenamos la lista: Tarifas ahora es la primera (índice 0)
    tabs = st.tabs(["📊 Tarifas", "🏙️ DF", "🌿 PBA", "🚌 JN", "📖 Ayuda"])

    # --- ÍNDICE 0: TARIFAS ---
    with tabs[0]:
        render_tarifas_tab()

    # --- ÍNDICE 1: DF ---
    with tabs[1]:
        tab_df(year, resolucion)

    # --- ÍNDICE 2: PBA ---
    with tabs[2]:
        tab_pba(year, resolucion)

    # --- ÍNDICE 3: JN ---
    with tabs[3]:
        tab_jn(year, resolucion)

    # --- ÍNDICE 4: AYUDA ---
    with tabs[4]:
        tab_ayuda()


if __name__ == "__main__":
    main()
