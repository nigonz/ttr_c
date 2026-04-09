"""
process_pba_jn.py  — VERSIÓN CORREGIDA
-----------------------------------------
BUGS ENCONTRADOS Y CORREGIDOS VS. NOTEBOOK ORIGINAL:

BUG 1 (CRÍTICO — causa principal de los 226k con sec=0):
  apply_seccion_tarifas usaba `<= lim_sup - 0.5` en el límite superior.
  El notebook usa `<= limite_superior` (sin restar 0.5) para secciones simples.
  Para tarifas de punto único (lim_inf == lim_sup, ej: 5SEAN=1559.53),
  el código nunca podía capturar la tarifa porque:
    1559.53 <= 1559.53 - 0.5 = 1559.03  → FALSE → sec=0

  FIX: en `_apply_seccion_tarifas_internal` usar `<= lim_sup`.

BUG 2 (CRÍTICO — afecta filas KM):
  sec_1_4 usaba `&` en lugar de `|` entre km_exact y km2.
  Notebook Cell 55:
    (km_exact > 0) | ((km2 > 0) & (all seccionada_correcta == 0))
  El código combinaba todo con `&`, excluyendo filas KM-exact que
  también tenían seccionada_correcta != 0.

  FIX: separar km_exact (siempre → 4) de km2 (solo si sc=0).

BUG 3 (MODERADO — _apply_km2_range exclusiones incompletas):
  En el notebook, la exclusión para KM2 de tipo E incluye los KP de tipo C,
  y para EA incluye TODOS los LP (no solo EA-LP) más KP de tipos C y E.
  El código solo excluía cols del mismo tipo.

  FIX: exclusiones cruzadas por tipo en `_apply_km2_range`.
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
    apply_km_exact_tarifas,
    apply_kp_tarifas, apply_sr_tarifas,
    build_sec_flags, build_secciones_1_5,
    build_seccionadas_final, build_norm_por_tarifa,
    build_concat_macheo, merge_ttr
)


# ────────────────────────────────────────────────────────────────────────────────
#  BUG 1 FIX: apply_seccion_tarifas con límite superior correcto
# ────────────────────────────────────────────────────────────────────────────────

def _apply_seccion_tarifas_corrected(df: pd.DataFrame, tarifas: dict,
                                      sin_nom_val: int,
                                      extra_conditions=None) -> pd.DataFrame:
    """
    Versión corregida de apply_seccion_tarifas.

    DIFERENCIA CLAVE vs. versión bugueada:
      Usa `<= lim_sup`  (igual que notebook cell 28/29/32/33/36/37)
      NO `<= lim_sup - 0.5`

    Para tarifas de un solo punto (lim_inf == lim_sup), el rango efectivo es:
      [lim_sup - 0.5,  lim_sup]   → captura la tarifa exacta ✓
    Con el bug era:
      [lim_sup - 0.5,  lim_sup - 0.5]  → casi nunca capturaba nada ✗
    """
    for id_val, (lim_inf, lim_sup) in tarifas.items():
        ts = get_tipo_servicio(id_val)

        mask = (
            (df['TARIFA BASE ITG'] >= lim_inf - 0.5) &
            (df['TARIFA BASE ITG'] <= lim_sup) &          # ← SIN -0.5 (fix bug 1)
            (df['PASES'] == 0) &
            (df['sin_nominalizar'] == sin_nom_val) &
            (df['TipoServicio2'] == ts)
        )

        if extra_conditions is not None:
            mask = mask & extra_conditions(df, id_val)

        df[id_val] = np.where(mask, 1, 0)
    return df


# ────────────────────────────────────────────────────────────────────────────────
#  BUG 3 FIX: _apply_km2_range con exclusiones cruzadas correctas
# ────────────────────────────────────────────────────────────────────────────────

def _apply_km2_range_corrected(df: pd.DataFrame, tarifas: dict,
                                sin_nom_val: int, all_cols: dict,
                                all_cols_other_sn: dict) -> pd.DataFrame:
    """
    Aplica tarifas KM2.

    FIX Bug 3: las exclusiones siguen la lógica del notebook cell 39/40:
      - tipo C → excluye sec_C, LP_C, KM_exact_C, SR
      - tipo E → excluye sec_E, LP_E, KM_exact_E, KP_C, SR
      - tipo EA → excluye sec_EA, TODOS los LP, KM_exact_EA, KP_C, KP_E, SR
    """
    all_col_names = list(all_cols.keys())

    for id_val, (lim_inf, lim_sup) in tarifas.items():
        ts = get_tipo_servicio(id_val)

        # Columnas base de exclusión (mismo tipo)
        sec_same   = [c for c in all_col_names
                      if is_seccion_simple(c) and get_tipo_servicio(c) == ts and not is_la_plata(c)]
        lp_same    = [c for c in all_col_names
                      if is_la_plata(c) and get_tipo_servicio(c) == ts]
        km_same    = [c for c in all_col_names
                      if is_km_exact(c) and get_tipo_servicio(c) == ts]
        sr_cols    = [c for c in all_col_names if is_sr(c)]

        # Exclusiones cruzadas según tipo (replicando notebook)
        cross_kp = []
        cross_lp = []

        if ts == 'E':
            # Para E → excluir también KP de tipo C
            cross_kp = [c for c in all_col_names if is_kp(c) and get_tipo_servicio(c) == 'C']
        elif ts == 'EA':
            # Para EA → excluir KP de C y E, y TODOS los LP (no solo EA)
            cross_kp = [c for c in all_col_names if is_kp(c) and get_tipo_servicio(c) in ('C', 'E')]
            cross_lp = [c for c in all_col_names if is_la_plata(c)]  # todos los LP

        exclude = list(set(sec_same + lp_same + km_same + sr_cols + cross_kp + cross_lp))
        exclude_ok = [c for c in exclude if c in df.columns]

        mask = (
            (df['PASES'] == 0) &
            (df['sin_nominalizar'] == sin_nom_val) &
            (df['TARIFA BASE ITG'] >= lim_inf - 0.5) &
            (df['TARIFA BASE ITG'] <= lim_sup - 0.5) &   # KM2 sí usa -0.5 (correcto)
            (df['TipoServicio2'] == ts) &
            (df['GT'] != 'DF') &
            ((df[exclude_ok].sum(axis=1) == 0) if exclude_ok else True)
        )
        df[id_val] = np.where(mask, 1, 0)
    return df


# ────────────────────────────────────────────────────────────────────────────────
#  Helpers internos (sin cambios salvo lo documentado)
# ────────────────────────────────────────────────────────────────────────────────

def _build_filtro_km(df: pd.DataFrame, tarifas_km2: dict,
                      tarifas_km2_sn: dict,
                      all_cols_n: dict, all_cols_sn: dict) -> pd.DataFrame:
    """Sin cambios respecto al original."""
    # Normalizado
    for id_val in tarifas_km2:
        ts = get_tipo_servicio(id_val)
        col = f'Filtro{id_val}'

        if ts == 'C':
            ref_cols = [c for c in all_cols_n if get_tipo_servicio(c) in ('E', 'EA')
                        and not is_la_plata(c) and not is_kp(c) and not is_km_exact(c)
                        and not is_km2_range(c) and not is_sr(c)]
            ref_ok = [c for c in ref_cols if c in df.columns]
            df[col] = np.where(
                (df['TipoServicio2'] == 'C') &
                (df[ref_ok].sum(axis=1) != 0 if ref_ok else False) &
                (df['LaPlata'] == 0) &
                (df[id_val] == 1 if id_val in df.columns else False),
                4, 0
            )
        elif ts == 'E':
            ref_cols = [c for c in all_cols_n if get_tipo_servicio(c) == 'EA'
                        and not is_la_plata(c) and not is_kp(c) and not is_km_exact(c)
                        and not is_km2_range(c) and not is_sr(c)]
            ref_ok = [c for c in ref_cols if c in df.columns]
            df[col] = np.where(
                (df['TipoServicio2'] == 'E') &
                (df[ref_ok].sum(axis=1) != 0 if ref_ok else False) &
                (df['LaPlata'] == 0) &
                (df[id_val] == 1 if id_val in df.columns else False),
                4, 0
            )
        elif ts == 'EA':
            df[col] = np.where(
                (df['TipoServicio2'] == 'EA') &
                (df['LaPlata'] == 0) &
                (df[id_val] == 1 if id_val in df.columns else False),
                4, 0
            )
        else:
            df[col] = 0

    # Sin nominalizar
    for id_val in tarifas_km2_sn:
        ts = get_tipo_servicio(id_val)
        col = f'Filtro{id_val}'

        if ts == 'C':
            ref_cols = [c for c in all_cols_sn if get_tipo_servicio(c) in ('E', 'EA')
                        and not is_la_plata(c) and not is_kp(c) and not is_km_exact(c)
                        and not is_km2_range(c) and not is_sr(c)]
            ref_ok = [c for c in ref_cols if c in df.columns]
            df[col] = np.where(
                (df['TipoServicio2'] == 'C') &
                (df[ref_ok].sum(axis=1) != 0 if ref_ok else False) &
                (df['LaPlata'] == 0) &
                (df[id_val] == 1 if id_val in df.columns else False),
                4, 0
            )
        elif ts == 'E':
            ref_cols = [c for c in all_cols_sn if get_tipo_servicio(c) == 'EA'
                        and not is_la_plata(c) and not is_kp(c) and not is_km_exact(c)
                        and not is_km2_range(c) and not is_sr(c)]
            ref_ok = [c for c in ref_cols if c in df.columns]
            df[col] = np.where(
                (df['TipoServicio2'] == 'E') &
                (df[ref_ok].sum(axis=1) != 0 if ref_ok else False) &
                (df['LaPlata'] == 0) &
                (df[id_val] == 1 if id_val in df.columns else False),
                4, 0
            )
        elif ts == 'EA':
            df[col] = np.where(
                (df['TipoServicio2'] == 'EA') &
                (df['LaPlata'] == 0) &
                (df[id_val] == 1 if id_val in df.columns else False),
                4, 0
            )
        else:
            df[col] = 0

    return df


def _build_compilado_ts(df: pd.DataFrame,
                         km_p_cols: list, sec_cols: list) -> pd.DataFrame:
    km_p_ok = [c for c in km_p_cols if c in df.columns]
    km_active = df[km_p_ok].sum(axis=1) > 0 if km_p_ok else pd.Series(False, index=df.index)
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

    # ── 2. FILTRO_1 ──────────────────────────────────────────────────────────
    threshold = get_filtro1_threshold(tarifas)
    df['FILTRO_1'] = np.where(
        (df['TARIFA BASE ITG'] < threshold) & (df['TARIFA BASE ITG'] > 0.5),
        1, 0
    )

    # ── 3. Clasificar tarifas por grupo ─────────────────────────────────────
    def subset(fn_filter):
        return {k: v for k, v in tarifas.items() if fn_filter(k)}

    sec_n   = subset(lambda k: is_seccion_simple(k) and not is_sin_nominalizar(k) and not is_la_plata(k) and not is_sr(k))
    sec_sn  = subset(lambda k: is_seccion_simple(k) and is_sin_nominalizar(k)     and not is_la_plata(k) and not is_sr(k))
    km_n    = subset(lambda k: is_km_exact(k) and not is_sin_nominalizar(k))
    km_sn   = subset(lambda k: is_km_exact(k) and is_sin_nominalizar(k))
    km2_n   = subset(lambda k: is_km2_range(k) and not is_sin_nominalizar(k))
    km2_sn  = subset(lambda k: is_km2_range(k) and is_sin_nominalizar(k))
    kp_n    = subset(lambda k: is_kp(k) and not is_sin_nominalizar(k))
    kp_sn   = subset(lambda k: is_kp(k) and is_sin_nominalizar(k))
    lp_n    = subset(lambda k: is_la_plata(k) and not is_sin_nominalizar(k))
    lp_sn   = subset(lambda k: is_la_plata(k) and is_sin_nominalizar(k))
    sr_n    = subset(lambda k: is_sr(k) and not is_sin_nominalizar(k))
    sr_sn   = subset(lambda k: is_sr(k) and is_sin_nominalizar(k))

    all_n   = {**sec_n,  **km_n,  **km2_n,  **kp_n,  **lp_n,  **sr_n}
    all_sn  = {**sec_sn, **km_sn, **km2_sn, **kp_sn, **lp_sn, **sr_sn}

    # ── 4. Secciones simples  [BUG 1 FIX: usa _apply_seccion_tarifas_corrected] ──
    def ts_cond_nosr_nolp(df, id_val):
        return (df['TipoServicio'] != 'SR') & (df['LaPlata'] != 1)

    _apply_seccion_tarifas_corrected(df, sec_n,  sin_nom_val=0, extra_conditions=ts_cond_nosr_nolp)
    _apply_seccion_tarifas_corrected(df, sec_sn, sin_nom_val=1, extra_conditions=ts_cond_nosr_nolp)

    # ── 5. KM exactas  [límite superior sin -0.5, igual que notebook] ───────
    apply_km_exact_tarifas(df, km_n,  sin_nom_val=0)
    apply_km_exact_tarifas(df, km_sn, sin_nom_val=1)

    # ── 6. La Plata  [BUG 1 FIX: usa _apply_seccion_tarifas_corrected] ──────
    def lp_cond(df, id_val):
        return df['LaPlata'] == 1

    _apply_seccion_tarifas_corrected(df, lp_n,  sin_nom_val=0, extra_conditions=lp_cond)
    _apply_seccion_tarifas_corrected(df, lp_sn, sin_nom_val=1, extra_conditions=lp_cond)

    # ── 7. KP ────────────────────────────────────────────────────────────────
    apply_kp_tarifas(df, kp_n,  sin_nom_val=0)
    apply_kp_tarifas(df, kp_sn, sin_nom_val=1)

    # ── 8. SR  [BUG 1 FIX: SR también usa <= lim_sup sin -0.5] ─────────────
    apply_sr_tarifas(df, sr_n,  sin_nom_val=0)
    apply_sr_tarifas(df, sr_sn, sin_nom_val=1)

    # ── 9. KM2 rangos  [BUG 3 FIX: exclusiones cruzadas corregidas] ─────────
    _apply_km2_range_corrected(df, km2_n,  sin_nom_val=0, all_cols=all_n,  all_cols_other_sn=all_sn)
    _apply_km2_range_corrected(df, km2_sn, sin_nom_val=1, all_cols=all_sn, all_cols_other_sn=all_n)

    # ── 10. Filtros KM ───────────────────────────────────────────────────────
    _build_filtro_km(df, km2_n, km2_sn, all_n, all_sn)

    filtro_km_cols = [f'Filtro{k}' for k in {**km2_n, **km2_sn}]

    # ── 11. seccionada_correcta ───────────────────────────────────────────────
    for idx, (id_val_km2, ts_km2) in enumerate(
        [(k, get_tipo_servicio(k)) for k in list(km2_n) + list(km2_sn)], 1
    ):
        sc_col = f'seccionada_correcta_{idx}'
        filtro_col = f'Filtro{id_val_km2}'
        sn_val = 1 if is_sin_nominalizar(id_val_km2) else 0
        pool = all_sn if sn_val else all_n

        if ts_km2 == 'C':
            ref_ts_list = ['E', 'EA']
        elif ts_km2 == 'E':
            ref_ts_list = ['EA']
        else:
            ref_ts_list = []

        ref_cols_by_sec = {}
        for sec in range(1, 6):
            ref_cols_by_sec[sec] = [
                c for c in pool
                if (not is_kp(c) and not is_km_exact(c) and not is_km2_range(c)
                    and get_tipo_servicio(c) in ref_ts_list
                    and c.startswith(str(sec)))
            ]

        conditions = []
        values = []
        for sec, cols in ref_cols_by_sec.items():
            ok = [c for c in cols if c in df.columns]
            if ok:
                conditions.append(
                    (df[id_val_km2] == 1 if id_val_km2 in df.columns else False) &
                    (df[filtro_col] != 4 if filtro_col in df.columns else True) &
                    (df[ok].sum(axis=1) > 0)
                )
                values.append(sec)

        if conditions:
            df[sc_col] = np.select(conditions, values, default=0)
        else:
            df[sc_col] = 0

    sc_cols = [c for c in df.columns if c.startswith('seccionada_correcta_')]

    # ── 12. sec_c / sec_e / sec_ea ───────────────────────────────────────────
    cols_c  = [k for k in {**all_n, **all_sn} if get_tipo_servicio(k) == 'C'  and not is_sr(k)]
    cols_e  = [k for k in {**all_n, **all_sn} if get_tipo_servicio(k) == 'E'  and not is_sr(k)]
    cols_ea = [k for k in {**all_n, **all_sn} if get_tipo_servicio(k) == 'EA']
    build_sec_flags(df, cols_c, cols_e, cols_ea)

    kmp_c  = [k for k in {**kp_n, **kp_sn, **km2_n, **km2_sn} if get_tipo_servicio(k) == 'C']
    kmp_e  = [k for k in {**kp_n, **kp_sn, **km2_n, **km2_sn} if get_tipo_servicio(k) == 'E']
    kmp_ea = [k for k in {**kp_n, **kp_sn, **km2_n, **km2_sn} if get_tipo_servicio(k) == 'EA']

    for col, group in [('km&p_c', kmp_c), ('km&p_e', kmp_e), ('km&p_ea', kmp_ea)]:
        ok = [c for c in group if c in df.columns]
        df[col] = np.where(df[ok].sum(axis=1) > 0, 1, 0) if ok else 0

    # ── 13. compilado_ts ─────────────────────────────────────────────────────
    _build_compilado_ts(df, ['km&p_c', 'km&p_e', 'km&p_ea'], ['sec_c', 'sec_e', 'sec_ea'])

    # ── 14. norm_por_tarifa ──────────────────────────────────────────────────
    all_n_cols  = list(all_n.keys())
    all_sn_cols = list(all_sn.keys())
    n_cols_for_norm = [c for c in all_n_cols if not is_sin_nominalizar(c)]
    build_norm_por_tarifa(df, cols_n=n_cols_for_norm, cols_sn=all_sn_cols)

    # ── 15. tarifa_s / tarifa_km / tarifa_kp / tarifa_PASE / tarifa_sr ──────
    all_sec_cols = [k for k in {**sec_n, **sec_sn, **lp_n, **lp_sn}]
    ok_sec  = [c for c in all_sec_cols if c in df.columns]
    ok_filt = [c for c in filtro_km_cols if c in df.columns]
    ok_sc   = [c for c in sc_cols if c in df.columns]

    df['tarifa_s'] = np.where(
        (df[ok_sec].sum(axis=1) > 0 if ok_sec else False) &
        (df[ok_filt].sum(axis=1) == 0 if ok_filt else True) &
        (
            ((df['compilado_ts'] == 'C')  & (df['sec_c']  == 1)) |
            ((df['compilado_ts'] == 'E')  & (df['sec_e']  == 1)) |
            ((df['compilado_ts'] == 'EA') & (df['sec_ea'] == 1))
        ) &
        (~df[[k for k in {**sr_n, **sr_sn} if k in df.columns]].sum(axis=1).gt(0)
         if [k for k in {**sr_n, **sr_sn} if k in df.columns] else True),
        1, 0
    )

    all_km_cols = [k for k in {**km_n, **km_sn, **km2_n, **km2_sn}]
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
    df['compilado_tt'] = np.where(df['tarifa_s']    != 0, 'S',
                         np.where(df['tarifa_km']   != 0, 'KM',
                         np.where(df['tarifa_kp']   != 0, 'KP',
                         np.where(df['tarifa_PASE'] != 0, 'P',
                         np.where(df['tarifa_sr']   != 0, 'SR',
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

    # ── sec_1_4  [BUG 2 FIX: OR correcto entre km_exact y km2] ─────────────
    # Notebook cell 55:
    #   (km_exact > 0)  OR  ((km2 > 0) AND (all seccionada_correcta == 0))
    # El código original usaba AND combinando todo, lo que bloqueaba filas KM-exact
    # que además tenían seccionada_correcta != 0.
    km_exact_only = [k for k in {**km_n, **km_sn} if k in df.columns]
    km2_only      = [k for k in {**km2_n, **km2_sn} if k in df.columns]

    cond_km_exact = df[km_exact_only].sum(axis=1) > 0 if km_exact_only else pd.Series(False, index=df.index)
    cond_km2_no_sc = (
        (df[km2_only].sum(axis=1) > 0 if km2_only else pd.Series(False, index=df.index)) &
        (df[ok_sc].sum(axis=1) == 0 if ok_sc else pd.Series(True, index=df.index))
    )

    df['sec_1_4'] = np.where(cond_km_exact | cond_km2_no_sc, 4, 0)   # ← OR (fix bug 2)

    # kilometricas_por_TS
    def min_kp_col(ts_val, sn_val):
        cands = [k for k in (kp_sn if sn_val else kp_n)
                 if get_tipo_servicio(k) == ts_val and k in df.columns]
        if not cands:
            return pd.Series(0, index=df.index)
        sub = df[cands].replace(0, np.nan)
        return sub.min(axis=1).fillna(0)

    df['kilometricas_por_TS'] = np.where(
        (df['TipoServicio'] == 'C')  & (df['sin_nominalizar'] == 0), min_kp_col('C',  0),
        np.where(
        (df['TipoServicio'] == 'E')  & (df['sin_nominalizar'] == 0), min_kp_col('E',  0),
        np.where(
        (df['TipoServicio'] == 'EA') & (df['sin_nominalizar'] == 0), min_kp_col('EA', 0),
        np.where(
        (df['TipoServicio'] == 'C')  & (df['sin_nominalizar'] == 1), min_kp_col('C',  1),
        np.where(
        (df['TipoServicio'] == 'E')  & (df['sin_nominalizar'] == 1), min_kp_col('E',  1),
        np.where(
        (df['TipoServicio'] == 'EA') & (df['sin_nominalizar'] == 1), min_kp_col('EA', 1), 0
        ))))))
    )

    # ── 18. compilado_seccion ─────────────────────────────────────────────────
    df['compilado_seccion'] = np.where(
        df['compilado_tt'] == 'S',  df['seccionadas_final'],
        np.where(df['compilado_tt'] == 'P',  1,
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
                    (df['TARIFA BASE ITG'] < sub_lim_sup - 0.5) &
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
            df['ENERGIA'] == 1,   # GNC
            df['ENERGIA'] == 2,   # Eléctrico
            df['ENERGIA'] == 3,   # Diesel
        ]
        factores = [1.3, 1.5, 1.0]
        df['Recaudacion_TRSUBE'] = (
            df['Recaudacion_TRSUBE'] * np.select(condiciones, factores, default=1)
        )

    return df
