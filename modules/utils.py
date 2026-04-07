"""
utils.py
--------
Funciones compartidas de preprocesamiento de datos para los 3 procesos (DF, PBA, JN).
"""

import pandas as pd
import numpy as np


# ────────────────────────────────────────────────────────────────────────────────
#  Preprocesamiento base
# ────────────────────────────────────────────────────────────────────────────────

def preprocess_base(df1: pd.DataFrame, nom_ts: pd.DataFrame, nom_gt: pd.DataFrame,
                    gt_values: list) -> pd.DataFrame:
    """
    Pasos iniciales comunes a los 3 procesos:
      1. Selección de columnas
      2. Filtro por GT
      3. Merge con nomencladores
      4. Conversión de tipos
    """
    # Columnas estándar (la columna ENERGIA es opcional, presente en JN)
    cols_base = ['Linea SILAS DNGFF', 'PROVINCIA', 'MUNICIPIO', 'GT',
                 'ID_EMPRESA', 'ID_LINEA', 'RAMAL', 'CONTRATO',
                 'TARIFA BASE ITG', 'DEBITADO', 'CANTIDAD_USOS']
    cols_extra = ['DOMINIO', 'ENERGIA']
    cols_disponibles = [c for c in cols_base + cols_extra if c in df1.columns]

    df2 = df1[cols_disponibles].copy()

    # Filtro GT
    df_f = df2[df2['GT'].isin(gt_values)].copy()

    # Merge nomenclador GT
    df_m = pd.merge(df_f, nom_gt[['ID_LINEA', 'GT']], how='left',
                    left_on='ID_LINEA', right_on='ID_LINEA')

    # Conversiones numéricas
    for col in ['CANTIDAD_USOS', 'TARIFA BASE ITG']:
        if col in df_m.columns:
            df_m[col] = (df_m[col].astype(str)
                         .str.replace(',', '', regex=True))
            df_m[col] = pd.to_numeric(df_m[col], errors='coerce').fillna(0)

    # Limpiar columnas GT duplicadas
    if 'GT_y' in df_m.columns:
        df_m.drop(columns=['GT_y'], inplace=True)
    if 'GT_x' in df_m.columns:
        df_m.rename(columns={'GT_x': 'GT'}, inplace=True)

    # Asegurar tipos string en columnas clave
    df_m['Linea SILAS DNGFF'] = df_m['Linea SILAS DNGFF'].astype(str)
    df_m['ID_LINEA'] = df_m['ID_LINEA'].astype(float).astype(int).astype(str)

    # Merge nomenclador TS (tipo de servicio)
    df_m['RAMAL'] = df_m['RAMAL'].astype(float).astype(int).astype(str)
    nom_ts['IdRamalNS'] = nom_ts['IdRamalNS'].astype(str).str.strip()

    df_m = pd.merge(df_m,
                    nom_ts[['IdRamalNS', 'TIPO DE SERVICIO FINAL']],
                    how='left', left_on='RAMAL', right_on='IdRamalNS')
    df_m.drop(columns=['IdRamalNS'], inplace=True, errors='ignore')
    df_m.rename(columns={'TIPO DE SERVICIO FINAL': 'TipoServicio'}, inplace=True)

    # TipoServicio2: SR → E (para condiciones KM/KP)
    df_m['TipoServicio2'] = df_m['TipoServicio'].replace('SR', 'E')

    # Flags base
    df_m['sin_nominalizar'] = (df_m['CONTRATO'] == 627).astype(int)
    df_m['PASES'] = ((df_m['TARIFA BASE ITG'] >= 0) &
                     (df_m['TARIFA BASE ITG'] <= 0.5)).astype(int)

    df_m['TARIFA BASE ITG'] = df_m['TARIFA BASE ITG'].round(3)

    return df_m


def add_la_plata_flag(df: pd.DataFrame,
                      lineas_la_plata: list = None) -> pd.DataFrame:
    """Agrega columna LaPlata (1/0)."""
    if lineas_la_plata is None:
        lineas_la_plata = [
            'LP506', 'LP504', 'LP508', 'LP561', 'LP501', 'LP502', 'LP520',
            'LP518', 'LP53A', 'LP53B', '275', '307', '202', '215', '225',
            '214', '273', '414', '418'
        ]
    df['LaPlata'] = df['Linea SILAS DNGFF'].isin(lineas_la_plata).astype(int)
    return df


# ────────────────────────────────────────────────────────────────────────────────
#  Aplicadores de tarifas
# ────────────────────────────────────────────────────────────────────────────────

def apply_seccion_tarifas(df: pd.DataFrame, tarifas: dict,
                          sin_nom_val: int,
                          extra_conditions=None) -> pd.DataFrame:
    """
    Aplica tarifas seccionadas simples (1SCN, 2SCN, ..., 5SEASN etc.).
    Crea una columna binaria (0/1) por cada Id de tarifa.

    extra_conditions: función (df, id_val) -> pd.Series boolean, para filtros adicionales.
    """
    base_mask = (
        (df['PASES'] == 0) &
        (df['sin_nominalizar'] == sin_nom_val)
    )
    for id_val, (lim_inf, lim_sup) in tarifas.items():
        mask = (
            base_mask &
            (df['TARIFA BASE ITG'] >= lim_inf - 0.5) &
            (df['TARIFA BASE ITG'] <= lim_sup)
        )
        if extra_conditions is not None:
            mask = mask & extra_conditions(df, id_val)
        df[id_val] = np.where(mask, 1, 0)
    return df


def apply_km_exact_tarifas(df: pd.DataFrame, tarifas: dict,
                            sin_nom_val: int) -> pd.DataFrame:
    """
    Aplica tarifas KM exactas (1-4KMCN, 1-4KMEN, 1-4KMEAN, etc.).
    Filtra además por TipoServicio2.
    """
    from modules.tariff_loader import get_tipo_servicio
    base_mask = (df['PASES'] == 0) & (df['sin_nominalizar'] == sin_nom_val)
    for id_val, (lim_inf, lim_sup) in tarifas.items():
        ts = get_tipo_servicio(id_val)
        mask = (
            base_mask &
            (df['TARIFA BASE ITG'] >= lim_inf - 0.5) &
            (df['TARIFA BASE ITG'] <= lim_sup) &
            (df['TipoServicio2'] == ts)
        )
        df[id_val] = np.where(mask, 1, 0)
    return df


def apply_km2_range_tarifas(df: pd.DataFrame, tarifas: dict,
                              sin_nom_val: int,
                              exclude_cols_map: dict) -> pd.DataFrame:
    """
    Aplica tarifas KM2 (rango entre KM y KP).
    exclude_cols_map: {id_val: [cols_que_deben_ser_0]}
    """
    from modules.tariff_loader import get_tipo_servicio
    base_mask = (df['PASES'] == 0) & (df['sin_nominalizar'] == sin_nom_val)
    for id_val, (lim_inf, lim_sup) in tarifas.items():
        ts = get_tipo_servicio(id_val)
        exclude_cols = exclude_cols_map.get(id_val, [])
        existing_exclude = [c for c in exclude_cols if c in df.columns]
        mask = (
            base_mask &
            (df['TARIFA BASE ITG'] >= lim_inf - 0.5) &
            (df['TARIFA BASE ITG'] <= lim_sup - 0.5) &
            (df['TipoServicio2'] == ts) &
            (df['GT'] != 'DF') &
            (df[existing_exclude].sum(axis=1) == 0 if existing_exclude else True)
        )
        df[id_val] = np.where(mask, 1, 0)
    return df


def apply_kp_tarifas(df: pd.DataFrame, tarifas: dict,
                      sin_nom_val: int) -> pd.DataFrame:
    """
    Aplica tarifas kilométrico-pasaje (5-9KP*). Asigna el número de sección (5-9).
    """
    from modules.tariff_loader import get_tipo_servicio, get_kp_seccion
    base_mask = (df['PASES'] == 0) & (df['sin_nominalizar'] == sin_nom_val)
    for id_val, (lim_inf, lim_sup) in tarifas.items():
        ts = get_tipo_servicio(id_val)
        sec_val = get_kp_seccion(id_val)
        mask = (
            base_mask &
            (df['TARIFA BASE ITG'] >= lim_inf - 0.5) &
            (df['TARIFA BASE ITG'] < lim_sup - 0.5) &
            (df['TipoServicio2'] == ts)
        )
        df[id_val] = np.where(mask, sec_val, 0)
    return df


def apply_sr_tarifas(df: pd.DataFrame, tarifas: dict,
                      sin_nom_val: int) -> pd.DataFrame:
    """Aplica tarifas Semi-Rápido."""
    base_mask = (df['PASES'] == 0) & (df['sin_nominalizar'] == sin_nom_val)
    for id_val, (lim_inf, lim_sup) in tarifas.items():
        mask = (
            base_mask &
            (df['TARIFA BASE ITG'] >= lim_inf - 0.5) &
            (df['TARIFA BASE ITG'] <= lim_sup) &
            (df['TipoServicio'] == 'SR')
        )
        df[id_val] = np.where(mask, 1, 0)
    return df


# ────────────────────────────────────────────────────────────────────────────────
#  Construcción de columnas de clasificación
# ────────────────────────────────────────────────────────────────────────────────

def build_sec_flags(df: pd.DataFrame,
                    cols_c: list, cols_e: list, cols_ea: list) -> pd.DataFrame:
    """Construye sec_c, sec_e, sec_ea como flags binarias."""
    cols_c_ok = [c for c in cols_c if c in df.columns]
    cols_e_ok = [c for c in cols_e if c in df.columns]
    cols_ea_ok = [c for c in cols_ea if c in df.columns]

    df['sec_c'] = np.where(df[cols_c_ok].sum(axis=1) > 0, 1, 0) if cols_c_ok else 0
    df['sec_e'] = np.where(df[cols_e_ok].sum(axis=1) > 0, 1, 0) if cols_e_ok else 0
    df['sec_ea'] = np.where(df[cols_ea_ok].sum(axis=1) > 0, 1, 0) if cols_ea_ok else 0
    return df


def build_secciones_1_5(df: pd.DataFrame,
                          cols_sec1: list, cols_sec2: list, cols_sec3: list,
                          cols_sec4: list, cols_sec5: list,
                          filtro_km_cols: list = None) -> pd.DataFrame:
    """
    Construye sec_1..sec_5 (número de sección) a partir de las columnas de tarifa.
    Si filtro_km_cols están presentes (Filtro1-4KM*), se excluyen filas donde ≠ 0.
    """
    def km_filter(df):
        if filtro_km_cols:
            ok = [c for c in filtro_km_cols if c in df.columns]
            return (df[ok] == 4).any(axis=1) if ok else pd.Series(False, index=df.index)
        return pd.Series(False, index=df.index)

    km_active = km_filter(df)

    for num, cols in zip([1, 2, 3, 4, 5], [cols_sec1, cols_sec2, cols_sec3, cols_sec4, cols_sec5]):
        ok = [c for c in cols if c in df.columns]
        if ok:
            df[f'sec_{num}'] = np.where(
                (df[ok].sum(axis=1) > 0) & ~km_active,
                num, 0
            )
        else:
            df[f'sec_{num}'] = 0

    return df


def build_seccionadas_final(df: pd.DataFrame) -> pd.DataFrame:
    """sec_1..sec_5 → seccionadas_final (con PASES=1 → sección=1)."""
    df['seccionadas_final'] = np.where(
        df['PASES'] == 1,
        1,
        df[['sec_1', 'sec_2', 'sec_3', 'sec_4', 'sec_5']].sum(axis=1)
    )
    return df


def build_norm_por_tarifa(df: pd.DataFrame,
                           cols_n: list, cols_sn: list,
                           filtro_col: str = 'FILTRO_1') -> pd.DataFrame:
    """Columna norm_por_tarifa: 'N', 'SN', 'Tarifa Vieja'."""
    cols_n_ok = [c for c in cols_n if c in df.columns]
    cols_sn_ok = [c for c in cols_sn if c in df.columns]

    cond_n = df[cols_n_ok].sum(axis=1) > 0 if cols_n_ok else pd.Series(False, index=df.index)

    df['norm_por_tarifa'] = np.where(
        cond_n,
        'N',
        np.where(
            df[filtro_col] == 1,
            'Tarifa Vieja',
            np.where(df['PASES'] == 1, 'N', 'SN')
        )
    )
    return df


def build_concat_macheo(df: pd.DataFrame,
                         year: int, resolucion: str,
                         use_linea: bool = False) -> pd.DataFrame:
    """Construye CONCAT_MACHEO, CONCAT_MACHEO2 y CONCAT_MACHEO3."""
    df['Año'] = year
    df['Resolucion'] = str(resolucion)

    # CONCAT_MACHEO (sin año/resolución)
    df['CONCAT_MACHEO'] = (
        df['final_seccion'].astype(int).astype(str) +
        df['GT'].astype(str) +
        df['compilado_ts'].astype(str) +
        df['norm_por_tarifa'].astype(str)
    )

    # CONCAT_MACHEO2 (con año/resolución, sin línea)
    df['CONCAT_MACHEO2'] = (
        df['Año'].astype(str) +
        df['Resolucion'].astype(str) +
        df['final_seccion'].astype(int).astype(str) +
        df['GT'].astype(str) +
        df['compilado_ts'].astype(str) +
        df['norm_por_tarifa'].astype(str)
    )

    # CONCAT_MACHEO3 (con año/resolución/línea)
    df['CONCAT_MACHEO3'] = (
        df['Año'].astype(str) +
        df['Resolucion'].astype(str) +
        df['final_seccion'].astype(int).astype(str) +
        df['GT'].astype(str) +
        df['ID_LINEA'].astype(str) +
        df['compilado_ts'].astype(str) +
        df['norm_por_tarifa'].astype(str)
    )

    return df


def merge_ttr(df: pd.DataFrame, ttr_reso: pd.DataFrame,
               concat_col: str, ttr_col_name: str) -> pd.DataFrame:
    """Hace merge con TTR y agrega columna de tarifa."""
    df = pd.merge(
        df, ttr_reso[['CONCAT', 'TTR E.C.']],
        how='left', left_on=concat_col, right_on='CONCAT'
    ).fillna({'TTR E.C.': 0})
    df.rename(columns={'TTR E.C.': ttr_col_name}, inplace=True)
    df.drop(columns=['CONCAT'], inplace=True, errors='ignore')
    return df
