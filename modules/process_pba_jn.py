"""
process_pba_jn.py
-----------------
Proceso TTR compartido para PBA y JN.
Réplica EXACTA del Jupyter Notebook original (Modo "Aspiradora" de tarifas KM2),
tomando los valores base desde el Excel Oficial.
"""

import re
import numpy as np
import pandas as pd

from modules.tariff_loader import (
    get_tipo_servicio, is_sin_nominalizar, is_la_plata,
    is_kp, is_km_exact, is_km2_range, is_sr, is_seccion_simple,
    get_kp_seccion, get_filtro1_threshold
)
from modules.utils import (
    preprocess_base, add_la_plata_flag,
    apply_seccion_tarifas, apply_km_exact_tarifas,
    apply_kp_tarifas, apply_sr_tarifas,
    build_sec_flags, build_secciones_1_5,
    build_seccionadas_final, build_norm_por_tarifa,
    build_concat_macheo, merge_ttr
)


# ────────────────────────────────────────────────────────────────────────────────
#  Helpers internos
# ────────────────────────────────────────────────────────────────────────────────

def _build_compilado_ts(df: pd.DataFrame,
                         km_p_cols: list, sec_cols: list) -> pd.DataFrame:
    """Columna compilado_ts: tipo de servicio consolidado."""
    km_p_ok = [c for c in km_p_cols if c in df.columns]
    
    km_active = df[km_p_ok].sum(axis=1) > 0 if km_p_ok else pd.Series(False, index=df.index)

    # seccionada_correcta cols
    sc_cols = [c for c in df.columns if c.startswith('seccionada_correcta_')]
    sc_sum = df[sc_cols].sum(axis=1) if sc_cols else pd.Series(0, index=df.index)

    df['compilado_ts'] = np.select(
        [
            km_active & (sc_sum == 0),
            df['sec_c'] == 1,
            df['sec_e'] == 1,
            df['sec_ea'] == 1,
            df['PASES'] == 1,
            df[['sec_c', 'sec_e', 'sec_ea'] + km_p_ok].sum(axis=1) == 0
        ],
        [
            df['TipoServicio2'],
            'C', 'E', 'EA',
            df['TipoServicio2'],
            df['TipoServicio2']
        ],
        default='S/D'
    )
    return df


# ────────────────────────────────────────────────────────────────────────────────
#  Función principal
# ────────────────────────────────────────────────────────────────────────────────

def process_pba_jn(df1: pd.DataFrame,
                    nom_ts: pd.DataFrame,
                    nom_gt: pd.DataFrame,
                    tarifas: dict,
                    ttr_reso: pd.DataFrame,
                    gt_values: list,
                    year: int = 2026,
                    resolucion: str = '16',
                    ttr_sgii: pd.DataFrame = None,
                    apply_energia_factor: bool = False) -> pd.DataFrame:

    # ── 1. Preprocesamiento base ─────────────────────────────────────────────
    df = preprocess_base(df1, nom_ts, nom_gt, gt_values=gt_values)
    add_la_plata_flag(df)

    # Blindaje de tipos de datos para variables lógicas
    df['sin_nominalizar'] = pd.to_numeric(df['sin_nominalizar'], errors='coerce').fillna(0).astype(int)
    df['PASES'] = pd.to_numeric(df['PASES'], errors='coerce').fillna(0).astype(int)

    # ── 2. FILTRO_1 ──────────────────────────────────────────────────────────
    threshold = get_filtro1_threshold(tarifas)
    df['FILTRO_1'] = np.where(
        (df['TARIFA BASE ITG'] < threshold) & (df['TARIFA BASE ITG'] > 0.5),
        1, 0
    )

    # ---> INYECTOR DE RANGOS "CONTABLES" <---
    # Si el Excel oficial no trae los rangos intermedios inventados por el economista,
    # los inyectamos en memoria acá para que la "aspiradora" funcione.
    rangos_km2_inyectados = {
        '1-4KMCN2': (855.17, 1108.10),
        '1-4KMEN2': (1068.96, 1385.12),
        '1-4KMEAN2': (1496.54, 1939.17),
        '1-4KMCSN2': (1359.72, 1761.88),
        '1-4KMESN2': (1699.65, 2202.35),
        '1-4KMEASN2': (2379.51, 3083.28)
    }
    for k, v in rangos_km2_inyectados.items():
        if k not in tarifas:
            tarifas[k] = v

    # ── 3. Clasificar tarifas por grupo ─────────────────────────────────────
    def subset(fn_filter):
        return {k: v for k, v in tarifas.items() if fn_filter(k)}

    sec_n = subset(lambda k: is_seccion_simple(k) and not is_sin_nominalizar(k) and not is_la_plata(k) and not is_sr(k))
    sec_sn = subset(lambda k: is_seccion_simple(k) and is_sin_nominalizar(k) and not is_la_plata(k) and not is_sr(k))
    km_n = subset(lambda k: is_km_exact(k) and not is_sin_nominalizar(k))
    km_sn = subset(lambda k: is_km_exact(k) and is_sin_nominalizar(k))
    kp_n = subset(lambda k: is_kp(k) and not is_sin_nominalizar(k))
    kp_sn = subset(lambda k: is_kp(k) and is_sin_nominalizar(k))
    lp_n = subset(lambda k: is_la_plata(k) and not is_sin_nominalizar(k))
    lp_sn = subset(lambda k: is_la_plata(k) and is_sin_nominalizar(k))
    sr_n = subset(lambda k: is_sr(k) and not is_sin_nominalizar(k))
    sr_sn = subset(lambda k: is_sr(k) and is_sin_nominalizar(k))

    all_n = {**sec_n, **km_n, **kp_n, **lp_n, **sr_n}
    all_sn = {**sec_sn, **km_sn, **kp_sn, **lp_sn, **sr_sn}

    # ── 4 al 8. Asignaciones Estándar ────────────────────────────────────────
    def ts_cond_nosr_nolp(df, id_val):
        return (df['TipoServicio'] != 'SR') & (df['LaPlata'] != 1)

    apply_seccion_tarifas(df, sec_n, sin_nom_val=0, extra_conditions=ts_cond_nosr_nolp)
    apply_seccion_tarifas(df, sec_sn, sin_nom_val=1, extra_conditions=ts_cond_nosr_nolp)

    apply_km_exact_tarifas(df, km_n, sin_nom_val=0)
    apply_km_exact_tarifas(df, km_sn, sin_nom_val=1)

    def lp_cond(df, id_val):
        return df['LaPlata'] == 1

    apply_seccion_tarifas(df, lp_n, sin_nom_val=0, extra_conditions=lp_cond)
    apply_seccion_tarifas(df, lp_sn, sin_nom_val=1, extra_conditions=lp_cond)

    apply_kp_tarifas(df, kp_n, sin_nom_val=0)
    apply_kp_tarifas(df, kp_sn, sin_nom_val=1)

    apply_sr_tarifas(df, sr_n, sin_nom_val=0)
    apply_sr_tarifas(df, sr_sn, sin_nom_val=1)

    # ── 9. RANGOS KM2 EXPLICITOS (REPLICA DEL NOTEBOOK) ──────────────────────
    def _safe_sum(df_obj, cols):
        valid = [c for c in cols if c in df_obj.columns]
        return df_obj[valid].sum(axis=1) if valid else pd.Series(0, index=df_obj.index)

    columnas_sn_cn = ['1SCN', '2SCN', '3SCN', '4SCN', '5SCN']
    columnas_kmn_cn = ['1-4KMCN']
    columnas_snlp_cn = ['1SCNLP', '2SCNLP', '3SCNLP', '4SCNLP', '5SCNLP']

    columnas_sn_en = ['1SEN', '2SEN', '3SEN', '4SEN', '5SEN']
    columnas_kmn_en = ['1-4KMEN']
    columnas_kpn_en = ['5KPCN', '6KPCN', '7KPCN', '8KPCN', '9KPCN']
    columnas_snlp_en = ['1SENLP', '2SENLP', '3SENLP', '4SENLP', '5SENLP']

    columnas_sn_ean = ['1SEAN', '2SEAN', '3SEAN', '4SEAN', '5SEAN']
    columnas_kmn_ean = ['1-4KMEAN']
    columnas_kpn_ean = ['5KPCN', '6KPCN', '7KPCN', '8KPCN', '9KPCN', '5KPEN', '6KPEN', '7KPEN', '8KPEN', '9KPEN']
    columnas_snlp_ean = ['1SCNLP', '2SCNLP', '3SCNLP', '4SCNLP', '5SCNLP', '1SENLP', '2SENLP', '3SENLP', '4SENLP', '5SENLP' ,'1SCSNLP', '2SCSNLP', '3SCSNLP', '4SCSNLP', '5SCSNLP', '1SESNLP', '2SESNLP', '3SESNLP', '4SESNLP', '5SESNLP']

    columnas_sn_cSn = ['1SCSN', '2SCSN', '3SCSN', '4SCSN', '5SCSN']
    columnas_kmn_cSn = ['1-4KMCSN']
    columnas_snlp_cSn = ['1SCSNLP', '2SCSNLP', '3SCSNLP', '4SCSNLP', '5SCSNLP']

    columnas_sn_eSn = ['1SESN', '2SESN', '3SESN', '4SESN', '5SESN']
    columnas_kmn_eSn = ['1-4KMESN']
    columnas_kpn_eSn = ['5KPCSN', '6KPCSN','7KPCSN','8KPCSN','9KPCSN']
    columnas_snlp_eSn = ['1SESNLP', '2SESNLP', '3SESNLP', '4SESNLP', '5SESNLP']

    columnas_sn_eaSn = ['1SEASN', '2SEASN', '3SEASN', '4SEASN', '5SEASN']
    columnas_kmn_eaSn = ['1-4KMEASN']
    columnas_kpn_eaSn = ['5KPCSN', '6KPCSN', '7KPCSN', '8KPCSN', '9KPCSN', '5KPESN', '6KPESN', '7KPESN', '8KPESN', '9KPESN']
    columnas_snlp_eaSn = ['1SCNLP', '2SCNLP', '3SCNLP', '4SCNLP', '5SCNLP', '1SENLP', '2SENLP', '3SENLP', '4SENLP', '5SENLP' ,'1SCSNLP', '2SCSNLP', '3SCSNLP', '4SCSNLP', '5SCSNLP', '1SESNLP', '2SESNLP', '3SESNLP', '4SESNLP', '5SESNLP']

    columnas_srn_srsn = ['1SRN', '2SRN', '3SRN', '4SRN', '5SRN', '1SRSN', '2SRSN', '3SRSN', '4SRSN', '5SRSN']

    # 1-4KMCN2
    lim_inf, lim_sup = tarifas['1-4KMCN2']
    df['1-4KMCN2'] = np.where(
        (df['TARIFA BASE ITG'] >= lim_inf - 0.5) &
        (df['TARIFA BASE ITG'] < lim_sup + 0.5) &
        (df['PASES'] == 0) &
        (df['sin_nominalizar'] != 1) &
        (_safe_sum(df, columnas_sn_cn) == 0) &
        (_safe_sum(df, columnas_snlp_cn) == 0) &
        (_safe_sum(df, columnas_kmn_cn) == 0) &
        (df['GT'] != "DF") &
        (_safe_sum(df, columnas_srn_srsn) == 0),
        1, 0
    )

    # 1-4KMEN2
    lim_inf, lim_sup = tarifas['1-4KMEN2']
    df['1-4KMEN2'] = np.where(
        (df['TARIFA BASE ITG'] >= lim_inf - 0.5) &
        (df['TARIFA BASE ITG'] < lim_sup + 0.5) &
        (df['PASES'] == 0) &
        (df['sin_nominalizar'] != 1) &
        (_safe_sum(df, columnas_sn_en) == 0) &
        (_safe_sum(df, columnas_snlp_en) == 0) &
        (_safe_sum(df, columnas_kmn_en) == 0) &
        (_safe_sum(df, columnas_kpn_en) == 0) &
        (df['GT'] != "DF") &
        (_safe_sum(df, columnas_srn_srsn) == 0),
        1, 0
    )

    # 1-4KMEAN2
    lim_inf, lim_sup = tarifas['1-4KMEAN2']
    df['1-4KMEAN2'] = np.where(
        (df['TARIFA BASE ITG'] >= lim_inf - 0.5) &
        (df['TARIFA BASE ITG'] < lim_sup + 0.5) &
        (df['PASES'] == 0) &
        (df['sin_nominalizar'] != 1) &
        (_safe_sum(df, columnas_sn_ean) == 0) &
        (_safe_sum(df, columnas_snlp_ean) == 0) &
        (_safe_sum(df, columnas_kmn_ean) == 0) &
        (_safe_sum(df, columnas_kpn_ean) == 0) &
        (df['GT'] != "DF") &
        (_safe_sum(df, columnas_srn_srsn) == 0),
        1, 0
    )

    # 1-4KMCSN2
    lim_inf, lim_sup = tarifas['1-4KMCSN2']
    df['1-4KMCSN2'] = np.where(
        (df['TARIFA BASE ITG'] >= lim_inf - 0.5) &
        (df['TARIFA BASE ITG'] < lim_sup + 0.5) &
        (df['PASES'] == 0) &
        (df['sin_nominalizar'] == 1) &
        (_safe_sum(df, columnas_sn_cSn) == 0) &
        (_safe_sum(df, columnas_snlp_cSn) == 0) &
        (_safe_sum(df, columnas_kmn_cSn) == 0) &
        (df['GT'] != "DF") &
        (_safe_sum(df, columnas_srn_srsn) == 0),
        1, 0
    )

    # 1-4KMESN2
    lim_inf, lim_sup = tarifas['1-4KMESN2']
    df['1-4KMESN2'] = np.where(
        (df['TARIFA BASE ITG'] >= lim_inf - 0.5) &
        (df['TARIFA BASE ITG'] < lim_sup + 0.5) &
        (df['PASES'] == 0) &
        (df['sin_nominalizar'] == 1) &
        (_safe_sum(df, columnas_sn_eSn) == 0) &
        (_safe_sum(df, columnas_snlp_eSn) == 0) &
        (_safe_sum(df, columnas_kmn_eSn) == 0) &
        (_safe_sum(df, columnas_kpn_eSn) == 0) &
        (df['GT'] != "DF") &
        (_safe_sum(df, columnas_srn_srsn) == 0),
        1, 0
    )

    # 1-4KMEASN2
    lim_inf, lim_sup = tarifas['1-4KMEASN2']
    df['1-4KMEASN2'] = np.where(
        (df['TARIFA BASE ITG'] >= lim_inf - 0.5) &
        (df['TARIFA BASE ITG'] < lim_sup + 0.5) &
        (df['PASES'] == 0) &
        (df['sin_nominalizar'] == 1) &
        (_safe_sum(df, columnas_sn_eaSn) == 0) &
        (_safe_sum(df, columnas_snlp_eaSn) == 0) &
        (_safe_sum(df, columnas_kmn_eaSn) == 0) &
        (_safe_sum(df, columnas_kpn_eaSn) == 0) &
        (df['GT'] != "DF") &
        (_safe_sum(df, columnas_srn_srsn) == 0),
        1, 0
    )

    # ── 10. Filtros KM (REPLICA DEL NOTEBOOK) ────────────────────────────────
    df['Filtro1-4KMCN'] = np.where(
        (df['TipoServicio2'] == 'C') &
        (_safe_sum(df, ['1SEN', '2SEN', '3SEN', '4SEN', '5SEN', '1SEAN', '2SEAN', '3SEAN', '4SEAN', '5SEAN']) != 0) &
        (df['LaPlata'] == 0) &
        (df['1-4KMCN2'] == 1),
        4, 0
    )

    df['Filtro1-4KMEN'] = np.where(
        (df['TipoServicio2'] == 'E') &
        (_safe_sum(df, ['1SEAN', '2SEAN', '3SEAN', '4SEAN', '5SEAN']) != 0)&
        (df['LaPlata'] == 0) &
        (df['1-4KMEN2'] == 1),
        4, 0
    )

    df['Filtro1-4KMEAN'] = np.where(
        (df['TipoServicio2'] == 'EA') &
        (df['LaPlata'] == 0) &
        (df['1-4KMEAN2'] == 1),
        4, 0
    )

    df['Filtro1-4KMCSN'] = np.where(
        (df['TipoServicio2'] == 'C') &
        (_safe_sum(df, ['1SESN', '2SESN', '3SESN', '4SESN', '5SESN', '1SEASN', '2SEASN', '3SEASN', '4SEASN', '5SEASN']) != 0)&
        (df['LaPlata'] == 0) &
        (df['1-4KMCSN2'] == 1),
        4, 0
    )

    df['Filtro1-4KMESN'] = np.where(
        (df['TipoServicio2'] == 'E') &
        (_safe_sum(df, ['1SEASN', '2SEASN', '3SEASN', '4SEASN', '5SEASN']) != 0)&
        (df['LaPlata'] == 0) &
        (df['1-4KMESN2'] == 1),
        4, 0
    )

    df['Filtro1-4KMEASN'] = np.where(
        (df['TipoServicio2'] == 'EA') &
        (df['LaPlata'] == 0) &
        (df['1-4KMEASN2'] == 1),
        4, 0
    )

    filtro_km_cols = ['Filtro1-4KMCN', 'Filtro1-4KMEN', 'Filtro1-4KMEAN', 'Filtro1-4KMCSN', 'Filtro1-4KMESN', 'Filtro1-4KMEASN']

    # ── 11. seccionada_correcta (REPLICA DEL NOTEBOOK) ───────────────────────
    def _col_eq_1(col):
        return df[col] == 1 if col in df.columns else pd.Series(False, index=df.index)

    df['seccionada_correcta_1'] = np.select(
        [
            (df['1-4KMCN2'] == 1) & (df['Filtro1-4KMCN'] != 4) & (_col_eq_1('1SEN') | _col_eq_1('1SENLP')),
            (df['1-4KMCN2'] == 1) & (df['Filtro1-4KMCN'] != 4) & (_col_eq_1('2SEN') | _col_eq_1('2SENLP')),
            (df['1-4KMCN2'] == 1) & (df['Filtro1-4KMCN'] != 4) & (_col_eq_1('3SEN') | _col_eq_1('3SENLP')),
            (df['1-4KMCN2'] == 1) & (df['Filtro1-4KMCN'] != 4) & (_col_eq_1('4SEN') | _col_eq_1('4SENLP')),
            (df['1-4KMCN2'] == 1) & (df['Filtro1-4KMCN'] != 4) & (_col_eq_1('5SEN') | _col_eq_1('5SENLP'))
        ],
        [1, 2, 3, 4, 5], default=0
    )

    df['seccionada_correcta_3'] = np.select(
        [
            (df['Filtro1-4KMCSN'] != 4) & (df['1-4KMCSN2'] == 1) & (_col_eq_1('1SESN') | _col_eq_1('1SESNLP')),
            (df['Filtro1-4KMCSN'] != 4) & (df['1-4KMCSN2'] == 1) & (_col_eq_1('2SESN') | _col_eq_1('2SESNLP')),
            (df['Filtro1-4KMCSN'] != 4) & (df['1-4KMCSN2'] == 1) & (_col_eq_1('3SESN') | _col_eq_1('3SESNLP')),
            (df['Filtro1-4KMCSN'] != 4) & (df['1-4KMCSN2'] == 1) & (_col_eq_1('4SESN') | _col_eq_1('4SESNLP')),
            (df['Filtro1-4KMCSN'] != 4) & (df['1-4KMCSN2'] == 1) & (_col_eq_1('5SESN') | _col_eq_1('5SESNLP'))
        ],
        [1, 2, 3, 4, 5], default=0
    )

    df['seccionada_correcta_2'] = np.select(
        [
            (df['1-4KMEN2'] == 1) & (df['Filtro1-4KMEN'] != 4) & _col_eq_1('1SEAN'),
            (df['1-4KMEN2'] == 1) & (df['Filtro1-4KMEN'] != 4) & _col_eq_1('2SEAN'),
            (df['1-4KMEN2'] == 1) & (df['Filtro1-4KMEN'] != 4) & _col_eq_1('3SEAN'),
            (df['1-4KMEN2'] == 1) & (df['Filtro1-4KMEN'] != 4) & _col_eq_1('4SEAN'),
            (df['1-4KMEN2'] == 1) & (df['Filtro1-4KMEN'] != 4) & _col_eq_1('5SEAN')
        ],
        [1, 2, 3, 4, 5], default=0
    )

    df['seccionada_correcta_4'] = np.select(
        [
            (df['1-4KMESN2'] == 1) & (df['Filtro1-4KMESN'] != 4) & _col_eq_1('1SEASN'),
            (df['1-4KMESN2'] == 1) & (df['Filtro1-4KMESN'] != 4) & _col_eq_1('2SEASN'),
            (df['1-4KMESN2'] == 1) & (df['Filtro1-4KMESN'] != 4) & _col_eq_1('3SEASN'),
            (df['1-4KMESN2'] == 1) & (df['Filtro1-4KMESN'] != 4) & _col_eq_1('4SEASN'),
            (df['1-4KMESN2'] == 1) & (df['Filtro1-4KMESN'] != 4) & _col_eq_1('5SEASN')
        ],
        [1, 2, 3, 4, 5], default=0
    )

    sc_cols = ['seccionada_correcta_1', 'seccionada_correcta_2', 'seccionada_correcta_3', 'seccionada_correcta_4']

    # ── 12. sec_c / sec_e / sec_ea ───────────────────────────────────────────
    cols_c = [k for k in {**all_n, **all_sn} if get_tipo_servicio(k) == 'C' and not is_sr(k)]
    cols_e = [k for k in {**all_n, **all_sn} if get_tipo_servicio(k) == 'E' and not is_sr(k)]
    cols_ea = [k for k in {**all_n, **all_sn} if get_tipo_servicio(k) == 'EA']
    build_sec_flags(df, cols_c, cols_e, cols_ea)

    # km&p flags
    kmp_c = [k for k in {**kp_n, **kp_sn} if get_tipo_servicio(k) == 'C'] + ['1-4KMCN2', '1-4KMCSN2']
    kmp_e = [k for k in {**kp_n, **kp_sn} if get_tipo_servicio(k) == 'E'] + ['1-4KMEN2', '1-4KMESN2']
    kmp_ea = [k for k in {**kp_n, **kp_sn} if get_tipo_servicio(k) == 'EA'] + ['1-4KMEAN2', '1-4KMEASN2']

    for col, group in [('km&p_c', kmp_c), ('km&p_e', kmp_e), ('km&p_ea', kmp_ea)]:
        ok = [c for c in group if c in df.columns]
        df[col] = np.where(df[ok].sum(axis=1) > 0, 1, 0) if ok else 0

    # ── 13. compilado_ts ─────────────────────────────────────────────────────
    _build_compilado_ts(df, ['km&p_c', 'km&p_e', 'km&p_ea'], ['sec_c', 'sec_e', 'sec_ea'])

    # ── 14. norm_por_tarifa ──────────────────────────────────────────────────
    all_n_cols = list(all_n.keys()) + ['1-4KMCN2', '1-4KMEN2', '1-4KMEAN2']
    all_sn_cols = list(all_sn.keys()) + ['1-4KMCSN2', '1-4KMESN2', '1-4KMEASN2']
    n_cols_for_norm = [c for c in all_n_cols if not is_sin_nominalizar(c)]
    build_norm_por_tarifa(df, cols_n=n_cols_for_norm, cols_sn=all_sn_cols)

    # ── 15. tarifa_s / tarifa_km / tarifa_kp / tarifa_PASE / tarifa_sr ──────
    all_sec_cols = (
        [k for k in {**sec_n, **sec_sn, **lp_n, **lp_sn}]
    )
    ok_sec = [c for c in all_sec_cols if c in df.columns]
    ok_filt = [c for c in filtro_km_cols if c in df.columns]
    ok_sc = [c for c in sc_cols if c in df.columns]

    df['tarifa_s'] = np.where(
        (df[ok_sec].sum(axis=1) > 0 if ok_sec else False) &
        (df[ok_filt].sum(axis=1) == 0 if ok_filt else True) &
        (
            ((df['compilado_ts'] == 'C') & (df['sec_c'] == 1)) |
            ((df['compilado_ts'] == 'E') & (df['sec_e'] == 1)) |
            ((df['compilado_ts'] == 'EA') & (df['sec_ea'] == 1))
        ) &
        (~df[[k for k in {**sr_n, **sr_sn} if k in df.columns]].sum(axis=1).gt(0)
         if [k for k in {**sr_n, **sr_sn} if k in df.columns] else True),
        1, 0
    )

    all_km_cols = [k for k in {**km_n, **km_sn}] + ['1-4KMCN2', '1-4KMEN2', '1-4KMEAN2', '1-4KMCSN2', '1-4KMESN2', '1-4KMEASN2']
    ok_km = [c for c in all_km_cols if c in df.columns]
    df['tarifa_km'] = np.where(
        (df[ok_km].sum(axis=1) > 0 if ok_km else False) &
        (df[ok_sc].sum(axis=1) == 0 if ok_sc else True),
        1, 0
    )

    all_kp_cols = [k for k in {**kp_n, **kp_sn}]
    ok_kp = [c for c in all_kp_cols if c in df.columns]
    df['tarifa_kp'] = np.where(df[ok_kp].sum(axis=1) > 0 if ok_kp else False, 1, 0)

    df['tarifa_PASE'] = (df['PASES'] == 1).astype(int)

    all_sr_cols = [k for k in {**sr_n, **sr_sn}]
    ok_sr = [c for c in all_sr_cols if c in df.columns]
    df['tarifa_sr'] = np.where(df[ok_sr].sum(axis=1) > 0 if ok_sr else False, 1, 0)

    # ── 16. compilado_tt ─────────────────────────────────────────────────────
    df['compilado_tt'] = np.where(df['tarifa_s'] != 0, 'S',
                         np.where(df['tarifa_km'] != 0, 'KM',
                         np.where(df['tarifa_kp'] != 0, 'KP',
                         np.where(df['tarifa_PASE'] != 0, 'P',
                         np.where(df['tarifa_sr'] != 0, 'SR',
                         np.where(df[ok_sc].sum(axis=1) != 0 if ok_sc else False, 'S', 'S/D'))))))

    # ── 17. Secciones 1-5 ────────────────────────────────────────────────────
    all_tarifa_cols = list({**all_n, **all_sn}.keys())
    
    def sec_cols_num(num):
        return [c for c in all_tarifa_cols if c.startswith(str(num)) and c in df.columns]

    build_secciones_1_5(
        df,
        sec_cols_num(1), sec_cols_num(2), sec_cols_num(3),
        sec_cols_num(4), sec_cols_num(5),
        filtro_km_cols=filtro_km_cols
    )
    build_seccionadas_final(df)

    # sec_1_4 para tipo KM
    all_km_exact_range = [k for k in {**km_n, **km_sn} if k in df.columns] + [k for k in ['1-4KMCN2', '1-4KMEN2', '1-4KMEAN2', '1-4KMCSN2', '1-4KMESN2', '1-4KMEASN2'] if k in df.columns]
    df['sec_1_4'] = np.where(
        (df[all_km_exact_range].sum(axis=1) > 0 if all_km_exact_range else False) &
        (df[ok_sc].sum(axis=1) == 0 if ok_sc else True),
        4, 0
    )

    # kilometricas_por_TS
    def min_kp_col(ts_val, sn_val):
        cands = [k for k in (kp_sn if sn_val else kp_n)
                 if get_tipo_servicio(k) == ts_val and k in df.columns]
        if not cands:
            return pd.Series(0, index=df.index)
        sub = df[cands].replace(0, np.nan)
        return sub.min(axis=1).fillna(0)

    df['kilometricas_por_TS'] = np.where(
        (df['TipoServicio'] == 'C') & (df['sin_nominalizar'] == 0), min_kp_col('C', 0),
        np.where(
            (df['TipoServicio'] == 'E') & (df['sin_nominalizar'] == 0), min_kp_col('E', 0),
            np.where(
                (df['TipoServicio'] == 'EA') & (df['sin_nominalizar'] == 0), min_kp_col('EA', 0),
                np.where(
                    (df['TipoServicio'] == 'C') & (df['sin_nominalizar'] == 1), min_kp_col('C', 1),
                    np.where(
                        (df['TipoServicio'] == 'E') & (df['sin_nominalizar'] == 1), min_kp_col('E', 1),
                        np.where(
                            (df['TipoServicio'] == 'EA') & (df['sin_nominalizar'] == 1),
                            min_kp_col('EA', 1), 0
                        )
                    )
                )
            )
        )
    )

    # ── 18. compilado_seccion ─────────────────────────────────────────────────
    df['compilado_seccion'] = np.where(
        df['compilado_tt'] == 'S', df['seccionadas_final'],
        np.where(df['compilado_tt'] == 'P', 1,
        np.where(df['compilado_tt'] == 'KM', df['sec_1_4'],
        np.where(df['compilado_tt'] == 'KP', df['kilometricas_por_TS'],
        np.where(df['compilado_tt'] == 'SR', df['seccionadas_final'], 0)
        ))))

    # ── 19. final_seccion: SGII mínimo 4 ────────────────────────────────────
    df['final_seccion'] = np.where(
        (df['GT'] == 'SGII') & (df['compilado_seccion'].isin([1, 2, 3])),
        4, df['compilado_seccion']
    )

    # ── 20. SubSeccion (para KP) ─────────────────────────────────────────────
    df['SubSeccion'] = None
    for sn_val, kp_dict in [(0, kp_n), (1, kp_sn)]:
        for id_val, (lim_inf, lim_sup) in kp_dict.items():
            ts = get_tipo_servicio(id_val)
            sec = get_kp_seccion(id_val)
            sub_rangos = np.linspace(lim_inf, lim_sup, 4)
            for i in range(3):
                sub_lim_inf = sub_rangos[i]
                sub_lim_sup = sub_rangos[i + 1]
                sub_sec = f'{sec}-{i+1}'
                mask = (
                    (df['TARIFA BASE ITG'] >= sub_lim_inf - 0.5) &
                    (df['TARIFA BASE ITG'] < sub_lim_sup + 0.5) &
                    (df['PASES'] == 0) &
                    (df['sin_nominalizar'] == sn_val) &
                    (df['TipoServicio2'] == ts)
                )
                df.loc[mask, 'SubSeccion'] = sub_sec
    df['SubSeccion'] = df['SubSeccion'].fillna(df['final_seccion'].astype(str))

    # ── 21. CONCAT y merge TTR ───────────────────────────────────────────────
    build_concat_macheo(df, year=year, resolucion=resolucion)

    df = merge_ttr(df, ttr_reso, 'CONCAT_MACHEO2', 'Tarifa TRSUBE')

    if ttr_sgii is not None:
        df = merge_ttr(df, ttr_sgii, 'CONCAT_MACHEO3', 'Tarifa TRSUBE2')
        df['Tarifa TRSUBE_FINAL'] = np.where(
            df['Tarifa TRSUBE2'] == 0,
            df['Tarifa TRSUBE'],
            df['Tarifa TRSUBE2']
        )
    else:
        df['Tarifa TRSUBE_FINAL'] = df['Tarifa TRSUBE']

    # ── 22. Recaudación ──────────────────────────────────────────────────────
    df['Recaudacion_TRSUBE'] = df['Tarifa TRSUBE_FINAL'] * df['CANTIDAD_USOS']

    if apply_energia_factor and 'ENERGIA' in df.columns:
        condiciones = [
            df['ENERGIA'] == 1,  # GNC
            df['ENERGIA'] == 2,  # Eléctrico
            df['ENERGIA'] == 3,  # Diesel
        ]
        factores = [1.3, 1.5, 1.0]
        df['Recaudacion_TRSUBE'] = (
            df['Recaudacion_TRSUBE'] * np.select(condiciones, factores, default=1)
        )

    return df
