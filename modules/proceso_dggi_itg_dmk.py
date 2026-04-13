import streamlit as st
import pandas as pd
import numpy as np
import io


def run():
    st.header("Liquidación de Compensaciones – ITG DMK")

    st.subheader("1. Carga de archivos")

    col1, col2, col3 = st.columns(3)

    with col1:
        file_dggi = st.file_uploader(
            "DGGI Tarifa ITG  (CSV · separador `;` · ISO-8859-1)",
            type=["csv"],
            key="dggi_itg_dmk",
        )

    with col2:
        file_nomenclador = st.file_uploader(
            "Nomenclador  (Excel .xlsx)",
            type=["xlsx"],
            key="nomenclador_itg_dmk",
        )

    with col3:
        file_pme = st.file_uploader(
            "Parque Móvil – Energías  (Excel .xlsx)",
            type=["xlsx"],
            key="pme_itg_dmk",
        )

    if not (file_dggi and file_nomenclador and file_pme):
        st.info("Cargá los tres archivos para habilitar el procesamiento.")
        return

    if not st.button("Procesar", type="primary"):
        return

    with st.spinner("Procesando…"):
        try:
            # ─────────────────────────────────────────────
            # CARGA DE DATOS
            # ─────────────────────────────────────────────
            df = pd.read_csv(file_dggi, encoding="ISO-8859-1", delimiter=";")
            nom_gt = pd.read_excel(file_nomenclador)
            df_pme = pd.read_excel(file_pme)

            # ─────────────────────────────────────────────
            # ARCHIVO DGGI_MES
            # Filtrar el DataFrame df para que solo contenga
            # las líneas que están en nom_gt
            # ─────────────────────────────────────────────
            df_ = df[df["ID_LINEA"].isin(nom_gt["ID_LINEA"])]

            # Nombres de las columnas a conservar
            df_ramal = [
                "ID_EMPRESA", "ID_LINEA", "RAMAL", "DOMINIO", "MK",
                "TARIFA BASE ITG", "DEBITADO", "CONTRATO",
                "VIAJE INTEGRADO", "DESCUENTO X INTEGRACION",
                "CANTIDAD_USOS", "MONTO", "TOTAL DESC POR INTEGRACION",
            ]
            df_ = df_[df_ramal]

            # Seleccionar las columnas necesarias de nom_gt y hacer merge
            columns_to_merge = ["ID_LINEA", "GT", "Linea SILAS DNGFF", "PROVINCIA", "MUNICIPIO"]
            _df2_ = pd.merge(df_, nom_gt[columns_to_merge], how="left", on="ID_LINEA")

            # Crear la columna 'BE'
            _df2_["BE"] = np.where(
                _df2_["CONTRATO"].isin([830, 831, 832, 833]), "SI", "NO"
            )

            # Corrección PROVINCIA para GT == 'DF'
            _df2_.loc[_df2_["GT"] == "DF", "PROVINCIA"] = "CABA"

            # ─────────────────────────────────────────────
            # PARQUE MOVIL CON ENERGIAS DIFERENTES
            # ─────────────────────────────────────────────
            dominios_pme = df_pme["DOMINIO"].unique()

            # df_pm: dominios que están en df_pme
            df_pm = _df2_[_df2_["DOMINIO"].isin(dominios_pme)].copy()

            # df_resto: dominios que NO están en df_pme
            df_resto = _df2_[~_df2_["DOMINIO"].isin(dominios_pme)].copy()

            # Merge para traer columna ENERGIA desde df_pme
            df_pm = df_pm.merge(
                df_pme[["DOMINIO", "ENERGIA"]].drop_duplicates(),
                on="DOMINIO",
                how="left",
            )

            # ─────────────────────────────────────────────
            # CREACION DE DOS BASES: con energias y sin
            # ─────────────────────────────────────────────
            columnas_a_quitar = ["DOMINIO", "MK"]
            df_resto = df_resto.drop(columns=columnas_a_quitar)

            # Groupby df_pm
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

            # Groupby df_resto → _df_
            _df_ = df_resto.groupby(
                [
                    "PROVINCIA", "MUNICIPIO", "ID_EMPRESA", "GT",
                    "Linea SILAS DNGFF", "ID_LINEA", "RAMAL",
                    "CONTRATO", "TARIFA BASE ITG", "DEBITADO",
                    "VIAJE INTEGRADO", "DESCUENTO X INTEGRACION",
                ],
                as_index=False,
            ).agg({"CANTIDAD_USOS": "sum", "MONTO": "sum"})

            # ─────────────────────────────────────────────
            # CALCULOS df_pm
            # ─────────────────────────────────────────────
            for col in ["TARIFA BASE ITG", "DEBITADO", "DESCUENTO X INTEGRACION",
                        "CANTIDAD_USOS", "CONTRATO"]:
                df_pm[col] = pd.to_numeric(df_pm[col], errors="coerce")

            df_pm["TipoContrato"] = df_pm["CONTRATO"].apply(
                lambda x: "ATS" if x == 621 else "SIN ATS"
            )

            df_pm["COMP. ITG"] = (
                df_pm["DESCUENTO X INTEGRACION"] * df_pm["CANTIDAD_USOS"]
            ).round(2)

            df_pm["COMP. ATS"] = df_pm.apply(
                lambda x: round(
                    (
                        (x["DEBITADO"] / 0.45 * 0.55) * x["CANTIDAD_USOS"]
                        if x["GT"] == "INP"
                        else (x["TARIFA BASE ITG"] - x["DEBITADO"] - x["DESCUENTO X INTEGRACION"])
                        * x["CANTIDAD_USOS"]
                    ),
                    2,
                )
                if x["CONTRATO"] == 621
                else 0,
                axis=1,
            )

            df_pm["COMP. ATS s/IVA"] = (df_pm["COMP. ATS"] / 1.105).round(2)
            df_pm["COMP. ITG s/IVA"] = (df_pm["COMP. ITG"] / 1.105).round(2)

            # ─────────────────────────────────────────────
            # CALCULOS _df_
            # ─────────────────────────────────────────────
            for col in ["TARIFA BASE ITG", "DEBITADO", "DESCUENTO X INTEGRACION",
                        "CANTIDAD_USOS", "CONTRATO"]:
                _df_[col] = pd.to_numeric(_df_[col], errors="coerce")

            _df_["TipoContrato"] = _df_["CONTRATO"].apply(
                lambda x: "ATS" if x == 621 else "SIN ATS"
            )

            _df_["COMP. ITG"] = (
                _df_["DESCUENTO X INTEGRACION"] * _df_["CANTIDAD_USOS"]
            ).round(2)

            _df_["COMP. ATS"] = _df_.apply(
                lambda x: round(
                    (
                        (x["DEBITADO"] / 0.45 * 0.55) * x["CANTIDAD_USOS"]
                        if x["GT"] == "INP"
                        else (x["TARIFA BASE ITG"] - x["DEBITADO"] - x["DESCUENTO X INTEGRACION"])
                        * x["CANTIDAD_USOS"]
                    ),
                    2,
                )
                if x["CONTRATO"] == 621
                else 0,
                axis=1,
            )

            _df_["COMP. ATS s/IVA"] = (_df_["COMP. ATS"] / 1.105).round(2)
            _df_["COMP. ITG s/IVA"] = (_df_["COMP. ITG"] / 1.105).round(2)

            # ─────────────────────────────────────────────
            # UNION FINAL
            # ─────────────────────────────────────────────
            _df_["DOMINIO"] = "NO"
            _df_["ENERGIA"] = 3

            df_final = pd.concat([_df_, df_pm], ignore_index=True)

            # ─────────────────────────────────────────────
            # RESULTADO
            # ─────────────────────────────────────────────
            st.success(f"✅ Procesamiento completado — {len(df_final):,} filas")

            st.subheader("2. Vista previa (primeras 100 filas)")
            st.dataframe(df_final.head(100), use_container_width=True)

            # Totales rápidos
            st.subheader("3. Totales")
            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("MONTO", f"${df_final['MONTO'].sum():,.2f}")
            col_b.metric("COMP. ITG", f"${df_final['COMP. ITG'].sum():,.2f}")
            col_c.metric("COMP. ATS", f"${df_final['COMP. ATS'].sum():,.2f}")
            col_d.metric(
                "COMP. ATS s/IVA", f"${df_final['COMP. ATS s/IVA'].sum():,.2f}"
            )

            # Descarga
            st.subheader("4. Descarga")
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df_final.to_excel(writer, index=False)
            output.seek(0)

            st.download_button(
                label="⬇️ Descargar Excel",
                data=output,
                file_name="dggi_DMK_PME.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        except Exception as exc:
            st.error(f"Error durante el procesamiento: {exc}")
            raise


# ── Punto de entrada standalone ──────────────────────────────────────────────
if __name__ == "__main__":
    st.set_page_config(page_title="ITG DMK", layout="wide")
    run()
