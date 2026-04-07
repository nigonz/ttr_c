"""
modules/tariff_loader.py
----------------
Lee el diccionario de tarifas desde un Excel y lo convierte en un dict estructurado
con la forma: {Id: (lim_inf, lim_sup)}

Soporta ambos formatos:
  - (Id, Limite Inferior, Limite Superior)  → DF y PBA
  - (Id, Limite Superior, Limite Inferior)  → JN  (columnas invertidas, se normaliza)
"""

import re
import pandas as pd


# ────────────────────────────────────────────────────────────────────────────────
#  Helpers de clasificación a partir del nombre del Id
# ────────────────────────────────────────────────────────────────────────────────

def get_tipo_servicio(id_val: str) -> str:
    """Devuelve 'EA', 'E', 'SR' o 'C' según el Id de la tarifa."""
    if any(x in id_val for x in ['SEA', 'KPEA', 'KMEA', 'PEAN', 'PEASN']):
        return 'EA'
    if any(x in id_val for x in ['SEN', 'SESN', 'SENLP', 'SESNLP', 'KPEN', 'KPESN', 'KMEN', 'KMESN']):
        return 'E'
    if 'SR' in id_val:
        return 'SR'
    return 'C'


def is_sin_nominalizar(id_val: str) -> bool:
    """True si el Id corresponde a una tarifa 'sin nominalizar' (contiene SN)."""
    return 'SN' in id_val


def is_la_plata(id_val: str) -> bool:
    """True si el Id corresponde a una tarifa de La Plata."""
    return id_val.endswith('LP')


def is_kp(id_val: str) -> bool:
    """True si es tarifa kilométrica-por-pasaje (5-9KP*)."""
    return bool(re.match(r'^\dKP', id_val))


def is_km_exact(id_val: str) -> bool:
    """True si es tarifa 1-4KM* (valor exacto, sin el '2' al final)."""
    return bool(re.match(r'^\d-\dKM', id_val)) and not id_val.endswith('2')


def is_km2_range(id_val: str) -> bool:
    """True si es tarifa 1-4KM*2 (rango entre KM y KP)."""
    return bool(re.match(r'^\d-\dKM', id_val)) and id_val.endswith('2')


def is_sr(id_val: str) -> bool:
    """True si es tarifa Semi-Rápido."""
    return 'SR' in id_val and not re.match(r'^\d-\dKM', id_val) and not is_kp(id_val)


def is_seccion_simple(id_val: str) -> bool:
    """True si es tarifa seccionada simple (no KM, no KP, no LP, no SR)."""
    return (
        bool(re.match(r'^\d', id_val))
        and not is_kp(id_val)
        and not is_km_exact(id_val)
        and not is_km2_range(id_val)
        and not is_la_plata(id_val)
        and not is_sr(id_val)
    )


def get_kp_seccion(id_val: str) -> int:
    """Devuelve el número de sección KP (5-9) desde el Id."""
    m = re.match(r'^(\d)KP', id_val)
    return int(m.group(1)) if m else 0


# ────────────────────────────────────────────────────────────────────────────────
#  Cargador principal
# ────────────────────────────────────────────────────────────────────────────────

def load_tarifas(excel_path) -> dict:
    """
    Lee el Excel de tarifas y retorna un dict {id: (lim_inf, lim_sup)}.
    En caso de filas duplicadas con mismo Id, se conserva la primera.
    Los límites se normalizan a (min, max) para manejar ambos formatos de archivo.
    """
    df = pd.read_excel(excel_path)
    df.columns = df.columns.str.strip()

    # Detectar columnas
    id_col = next(c for c in df.columns if str(c).strip().lower() in ('id', 'id'))
    num_cols = [c for c in df.columns if c != id_col and pd.api.types.is_numeric_dtype(df[c])]

    if len(num_cols) < 2:
        raise ValueError("El Excel de tarifas necesita al menos 2 columnas numéricas (Limite Inferior / Superior).")

    col_a, col_b = num_cols[0], num_cols[1]

    tarifas = {}
    for _, row in df.iterrows():
        id_raw = str(row[id_col]).strip()
        if id_raw in ('nan', 'None', '', 'Id'):
            continue
        try:
            val_a = float(row[col_a])
            val_b = float(row[col_b])
        except (ValueError, TypeError):
            continue

        if id_raw not in tarifas:
            tarifas[id_raw] = (min(val_a, val_b), max(val_a, val_b))

    return tarifas


def get_filtro1_threshold(tarifas: dict) -> float:
    """
    Threshold para FILTRO_1: cualquier tarifa por debajo de esto se considera
    'Tarifa Vieja'. Se toma como el mínimo límite inferior de las tarifas 1-seccion
    normalizadas (1SCN).
    """
    clave = '1SCN'
    if clave in tarifas:
        return tarifas[clave][0]
    # Fallback: mínimo de las tarifas exactas (no KP, no KM2)
    candidatos = [
        v[0] for k, v in tarifas.items()
        if is_seccion_simple(k) and not is_sin_nominalizar(k) and not is_la_plata(k)
    ]
    return min(candidatos) if candidatos else 0.0
