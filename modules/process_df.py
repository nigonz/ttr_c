"""
process_df.py
-------------
Proceso TTR para el Distrito Federal (GT = 'DF').
Lógica equivalente al notebook 'febrero_original_DF.ipynb' pero con
tarifas cargadas dinámicamente desde Excel.
"""

import numpy as np
import pandas as pd

from modules.tariff_loader import (
    is_sin_nominalizar, is_seccion_simple,
    get_filtro1_threshold
)
from modules.utils import (
    preprocess_base, apply_seccion_tarifas,
    build_sec_flags, build_secciones_1_5,
    build_seccionadas_final, build_norm_por_tarifa,
    build_concat_macheo, merge_ttr
)


def process_df(df1: pd.DataFrame,
               nom_ts: pd.DataFrame,
               nom_gt: pd.DataFrame,
               tarifas: dict,
               ttr_reso: pd.DataFrame,
               year: int = 2026,
               resolucion: str = '16') -> pd.DataFrame:
    """
    Ejecuta el proceso completo DF y retorna el DataFrame final.

    Parámetros
    ----------
    df1       : DataFrame principal (DGGI)
    nom_ts    : Nomenclador Ramal-TS
    nom_gt    : Nomenclador GT (ID_LINEA → GT)
    tarifas   : dict {Id: (lim_inf, lim_sup)} cargado desde Excel
    ttr_reso  : DataFrame TTR con columnas ['CONCAT', 'TTR E.C.']
    year      : Año de la resolución
    resolucion: Número de resolución
    """

    # ── 1. Preprocesamiento base ─────────────────────────────────────────────
    df = preprocess_base(df1, nom_ts, nom_gt, gt_values=['DF'])

    # ── 2. FILTRO_1: tarifas viejas ──────────────────────────────────────────
    threshold = get_filtro1_threshold(tarifas)
    df['FILTRO_1'] = np.where(
        (df['TARIFA BASE ITG'] < threshold) & (df['TARIFA BASE ITG'] > 0.5),
        1, 0
    )

    # ── 3. Separar tarifas en grupos N y SN ─────────────────────────────────
    tarifas_n = {k: v for k, v in tarifas.items()
                 if is_seccion_simple(k) and not is_sin_nominalizar(k)}
    tarifas_sn = {k: v for k, v in tarifas.items()
                  if is_seccion_simple(k) and is_sin_nominalizar(k)}

    # ── 4. Aplicar tarifas seccionadas ───────────────────────────────────────
    # Tarifas N: no pases, nominalizado (sin_nominalizar != 1)
    apply_seccion_tarifas(df, tarifas_n, sin_nom_val=0)
    # Tarifas SN: no pases, sin nominalizar
    apply_seccion_tarifas(df, tarifas_sn, sin_nom_val=1)

    # ── 5. Columnas sec_c / sec_e / sec_ea ──────────────────────────────────
    cols_c = [k for k in {**tarifas_n, **tarifas_sn} if 'SC' in k or 'SCS' in k]
    cols_e = [k for k in {**tarifas_n, **tarifas_sn} if 'SE' in k and 'SEA' not in k]
    cols_ea = [k for k in {**tarifas_n, **tarifas_sn} if 'SEA' in k]

    build_sec_flags(df, cols_c, cols_e, cols_ea)

    # ── 6. norm_por_tarifa ───────────────────────────────────────────────────
    all_n_cols = list(tarifas_n.keys())
    all_sn_cols = list(tarifas_sn.keys())
    build_norm_por_tarifa(df, cols_n=all_n_cols, cols_sn=all_sn_cols)

    # ── 7. tarifa_PASE ───────────────────────────────────────────────────────
    df['tarifa_PASE'] = (df['PASES'] == 1).astype(int)
    df['compilado_tt'] = np.where(df['tarifa_PASE'] != 0, 'P', 'S')

    # ── 8. Secciones 1-5 ────────────────────────────────────────────────────
    def cols_for_sec(num):
        return [k for k in {**tarifas_n, **tarifas_sn} if k.startswith(str(num))]

    build_secciones_1_5(
        df,
        cols_for_sec(1), cols_for_sec(2), cols_for_sec(3),
        cols_for_sec(4), cols_for_sec(5)
    )
    build_seccionadas_final(df)

    # ── 9. compilado_seccion / final_seccion ─────────────────────────────────
    df['compilado_seccion'] = np.where(
        df['compilado_tt'] == 'S', df['seccionadas_final'],
        np.where(df['compilado_tt'] == 'P', 1, 0)
    )
    df.rename(columns={'compilado_seccion': 'final_seccion',
                       'TipoServicio': 'compilado_ts'}, inplace=True)

    # ── 10. CONCAT y merge TTR ───────────────────────────────────────────────
    build_concat_macheo(df, year=year, resolucion=resolucion)

    df = merge_ttr(df, ttr_reso, 'CONCAT_MACHEO2', 'Tarifa TRSUBE')

    # Recaudación
    df['Recaudacion_TRSUBE'] = df['Tarifa TRSUBE'] * df['CANTIDAD_USOS']

    return df
