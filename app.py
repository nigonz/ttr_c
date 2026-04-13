"""
app.py
------
Aplicación TTR — Cálculo automático de tarifas DF / PBA / JN
+ Liquidación de Compensaciones ITG DMK
Streamlit app que reemplaza los 3 notebooks con tarifas dinámicas desde Excel.
"""

import io
import sys
import os
import traceback

import numpy as np
import pandas as pd
import streamlit as st

# ── Path setup ───────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

from modules.tariff_loader import load_tarifas, get_filtro1_threshold
from modules.process_df import process_df
from modules.process_pba_jn import process_pba_jn


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


# ────────────────────────────────────────────────────────────────────────────────
#  Tab ITG DMK — Liquidación de Compensaciones
# ────────────────────────────────────────────────────────────────────────────────

def _calcular_comp_ats(row):
    """Lógica exacta del notebook para COMP. ATS (con redondeo a 2 decimales)."""
    if row["CONTRATO"] != 621:
        return 0
    if row["GT"] == "INP":
        return round((row["DEBITADO"] / 0.45 * 0.55) * row["CANTIDAD_USOS"], 2)
    return round(
        (row["TARIFA BASE ITG"] - row["DEBITADO"] - row["DESCUENTO X INTEGRACION"])
        * row["CANTIDAD_USOS"],
        2,
    )


def _procesar_itg_dmk(file_dggi, file_nomenclador, file_pme):
    """
    Replica celda a celda el notebook entrega_dggi__ITG_DMK.
    Devuelve df_final listo para descargar.
    """
    # ── Carga ────────────────────────────────────────────────────────────────
    df = pd.read_csv(file_dggi, encoding="ISO-8859-1", delimiter=";")
    nom_gt = pd.read_excel(file_nomenclador)
    df_pme = pd.read_excel(file_pme)

    # ── Filtrar líneas presentes en nom_gt ───────────────────────────────────
    df_ = df[df["ID_LINEA"].isin(nom_gt["ID_LINEA"])]

    df_ramal = [
        "ID_EMPRESA", "ID_LINEA", "RAMAL", "DOMINIO", "MK",
        "TARIFA BASE ITG", "DEBITADO", "CONTRATO",
        "VIAJE INTEGRADO", "DESCUENTO X INTEGRACION",
        "CANTIDAD_USOS", "MONTO", "TOTAL DESC POR INTEGRACION",
    ]
    df_ = df_[df_ramal]

    # ── Merge con nomenclador ────────────────────────────────────────────────
    columns_to_merge = ["ID_LINEA", "GT", "Linea SILAS DNGFF", "PROVINCIA", "MUNICIPIO"]
    _df2_ = pd.merge(df_, nom_gt[columns_to_merge], how="left", on="ID_LINEA")

    # ── Columna BE ───────────────────────────────────────────────────────────
    _df2_["BE"] = np.where(
        _df2_["CONTRATO"].isin([830, 831, 832, 833]), "SI", "NO"
    )

    # ── Corrección PROVINCIA para GT == 'DF' ─────────────────────────────────
    _df2_.loc[_df2_["GT"] == "DF", "PROVINCIA"] = "CABA"

    # ── Split: con / sin Parque Móvil Energías ───────────────────────────────
    dominios_pme = df_pme["DOMINIO"].unique()

    df_pm = _df2_[_df2_["DOMINIO"].isin(dominios_pme)].copy()
    df_resto = _df2_[~_df2_["DOMINIO"].isin(dominios_pme)].copy()

    # Traer columna ENERGIA desde df_pme
    df_pm = df_pm.merge(
        df_pme[["DOMINIO", "ENERGIA"]].drop_duplicates(),
        on="DOMINIO",
        how="left",
    )

    # Quitar DOMINIO y MK de df_resto
    df_resto = df_resto.drop(columns=["DOMINIO", "MK"])

    # ── Groupby df_pm ────────────────────────────────────────────────────────
    df_pm = df_pm.groupby(
        [
            "PROVINCIA", "MUNICIPIO", "ID_EMPRESA", "GT",
            "Linea SILAS DNGFF", "ID_LINEA", "RAMAL",
            "DOMINIO", "ENERGIA",
            "CONTRATO", "TARIFA BASE ITG", "DEBITADO",
            "VIAJE INTEGRADO", "DESCUENTO X INTEGRACION",
        ],
        as_index=False,
    ).agg({"CANTIDAD_USOS": "sum", "MONTO": "sum"})

    # ── Groupby df_resto → _df_ ──────────────────────────────────────────────
    _df_ = df_resto.groupby(
        [
            "PROVINCIA", "MUNICIPIO", "ID_EMPRESA", "GT",
            "Linea SILAS DNGFF", "ID_LINEA", "RAMAL",
            "CONTRATO", "TARIFA BASE ITG", "DEBITADO",
            "VIAJE INTEGRADO", "DESCUENTO X INTEGRACION",
        ],
        as_index=False,
    ).agg({"CANTIDAD_USOS": "sum", "MONTO": "sum"})

    # ── Cálculos df_pm ───────────────────────────────────────────────────────
    for col in ["TARIFA BASE ITG", "DEBITADO", "DESCUENTO X INTEGRACION",
                "CANTIDAD_USOS", "CONTRATO"]:
        df_pm[col] = pd.to_numeric(df_pm[col], errors="coerce")

    df_pm["TipoContrato"] = df_pm["CONTRATO"].apply(
        lambda x: "ATS" if x == 621 else "SIN ATS"
    )
    df_pm["COMP. ITG"] = (
        df_pm["DESCUENTO X INTEGRACION"] * df_pm["CANTIDAD_USOS"]
    ).round(2)
    df_pm["COMP. ATS"] = df_pm.apply(_calcular_comp_ats, axis=1)
    df_pm["COMP. ATS s/IVA"] = (df_pm["COMP. ATS"] / 1.105).round(2)
    df_pm["COMP. ITG s/IVA"] = (df_pm["COMP. ITG"] / 1.105).round(2)

    # ── Cálculos _df_ ────────────────────────────────────────────────────────
    for col in ["TARIFA BASE ITG", "DEBITADO", "DESCUENTO X INTEGRACION",
                "CANTIDAD_USOS", "CONTRATO"]:
        _df_[col] = pd.to_numeric(_df_[col], errors="coerce")

    _df_["TipoContrato"] = _df_["CONTRATO"].apply(
        lambda x: "ATS" if x == 621 else "SIN ATS"
    )
    _df_["COMP. ITG"] = (
        _df_["DESCUENTO X INTEGRACION"] * _df_["CANTIDAD_USOS"]
    ).round(2)
    _df_["COMP. ATS"] = _df_.apply(_calcular_comp_ats, axis=1)
    _df_["COMP. ATS s/IVA"] = (_df_["COMP. ATS"] / 1.105).round(2)
    _df_["COMP. ITG s/IVA"] = (_df_["COMP. ITG"] / 1.105).round(2)

    # ── Unión final ──────────────────────────────────────────────────────────
    _df_["DOMINIO"] = "NO"
    _df_["ENERGIA"] = 3

    df_final = pd.concat([_df_, df_pm], ignore_index=True)
    return df_final


def tab_itg_dmk():
    st.header("📋 ITG DMK — Liquidación de Compensaciones")
    st.info(
        "Replica el proceso del notebook **entrega_dggi__ITG_DMK**. "
        "Cargá los tres archivos del período y descargá el Excel resultante."
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        f_dggi = st.file_uploader(
            "📂 DGGI Tarifa ITG  (CSV · sep `;` · ISO-8859-1)",
            type=["csv"],
            key="itg_dggi",
        )
    with c2:
        f_nomenclador = st.file_uploader(
            "📂 Nomenclador  (.xlsx)",
            type=["xlsx"],
            key="itg_nomenclador",
        )
    with c3:
        f_pme = st.file_uploader(
            "📂 Parque Móvil – Energías  (.xlsx)",
            type=["xlsx"],
            key="itg_pme",
        )

    if st.button("🚀 Procesar ITG DMK", type="primary", key="btn_itg"):
        if not all([f_dggi, f_nomenclador, f_pme]):
            st.error("⚠️ Por favor cargá los tres archivos antes de procesar.")
            return

        with st.spinner("Procesando…"):
            try:
                df_final = _procesar_itg_dmk(f_dggi, f_nomenclador, f_pme)

                st.success(f"✅ Proceso ITG DMK completado. {len(df_final):,} registros.")

                # Métricas
                cols = st.columns(4)
                cols[0].metric("Registros", f"{len(df_final):,}")
                cols[1].metric("MONTO", f"${df_final['MONTO'].sum():,.2f}")
                cols[2].metric("COMP. ITG", f"${df_final['COMP. ITG'].sum():,.2f}")
                cols[3].metric("COMP. ATS", f"${df_final['COMP. ATS'].sum():,.2f}")

                # Vista previa
                with st.expander("👁️ Vista previa (primeras 100 filas)"):
                    st.dataframe(df_final.head(100), use_container_width=True)

                # Descarga
                xlsx_bytes = to_excel_bytes(df_final, sheet_name="ITG_DMK")
                st.download_button(
                    label="⬇️ Descargar resultado ITG DMK (.xlsx)",
                    data=xlsx_bytes,
                    file_name="dggi_DMK_PME.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

            except Exception as e:
                st.error(f"❌ Error durante el procesamiento:\n\n{e}")
                with st.expander("Traceback"):
                    st.code(traceback.format_exc())


def tab_ayuda():
    st.header("📖 Guía de uso")
    st.markdown("""
### ¿Qué hace esta aplicación?

Automatiza los 3 procesos de ingeniería inversa de tarifas TTR + la liquidación de compensaciones ITG DMK:
- **DF** → Distrito Federal (GT = DF)
- **PBA** → Provincia de Buenos Aires (GT = UPA, UPAKM, UMA1, UMA2)
- **JN** → Jornada Nacional (GT = SGI, SGII, SGIKM)
- **ITG DMK** → Liquidación de Compensaciones (replica el notebook `entrega_dggi__ITG_DMK`)

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

#### Archivos para ITG DMK

| Archivo | Descripción |
|---------|-------------|
| **DGGI Tarifa ITG** | CSV con separador `;` y encoding ISO-8859-1 (ej. `Entrega_dggi_tarifa_ITG_202603.csv`) |
| **Nomenclador** | `00. NOMENCLADOR.v2.xlsx` |
| **Parque Móvil – Energías** | `09. PARQUE MOVIL - ENERGIAS.xlsx` |

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

El resultado de **ITG DMK** incluye: `TipoContrato`, `COMP. ITG`, `COMP. ATS`,
`COMP. ATS s/IVA`, `COMP. ITG s/IVA` — todos redondeados a 2 decimales.
    """)


# ────────────────────────────────────────────────────────────────────────────────
#  Main
# ────────────────────────────────────────────────────────────────────────────────

def main():
    st.title("🚌 TTR — Calculadora Automática de Tarifas")
    st.markdown(
        "Procesá **DF**, **PBA**, **JN** e **ITG DMK** cargando los archivos del período. "
        "Las tarifas se leen del Excel de tarifas — **sin hardcodeo**."
    )

    year, resolucion = sidebar_config()

    tabs = st.tabs(["🏙️ DF", "🌿 PBA", "🚌 JN", "📋 ITG DMK", "📖 Ayuda"])

    with tabs[0]:
        tab_df(year, resolucion)

    with tabs[1]:
        tab_pba(year, resolucion)

    with tabs[2]:
        tab_jn(year, resolucion)

    with tabs[3]:
        tab_itg_dmk()

    with tabs[4]:
        tab_ayuda()


if __name__ == "__main__":
    main()
