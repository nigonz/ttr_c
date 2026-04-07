# TTR — Calculadora Automática de Tarifas

Aplicación Streamlit que reemplaza los 3 notebooks de cálculo TTR
(DF, PBA, JN) con un proceso automatizado que lee las tarifas de
un Excel en lugar de tenerlas hardcodeadas.

## Instalación

```bash
pip install -r requirements.txt
```

## Ejecución

```bash
streamlit run app.py
```

Luego abrí `http://localhost:8501` en tu navegador.

## Estructura del proyecto

```
ttr_app/
├── app.py                      # App Streamlit (interfaz)
├── requirements.txt
├── README.md
└── modules/
    ├── __init__.py
    ├── tariff_loader.py        # Lee el Excel de tarifas → dict
    ├── utils.py                # Utilidades compartidas de procesamiento
    ├── process_df.py           # Proceso DF
    └── process_pba_jn.py       # Proceso PBA y JN (lógica compartida)
```

## Archivos necesarios por proceso

### DF
- Archivo DGGI principal (ej. `dggi_DMK_PME_202602.xlsx`)
- Nomenclador Ramal-TS (`01. NOMENCLADOR RAMAL - TS.xlsx`)
- Nomenclador GT (`00. NOMENCLADOR.v2.xlsx`)
- Diccionario de Tarifas DF (`Diccionario_Tarifas_DF_Febrero.xlsx`)
- TTR Teórica Resoluciones (hoja: `TTR`)

### PBA
- Mismos nomencladores
- Diccionario de Tarifas PBA
- TTR Resoluciones (hojas: `TTR` y `SGII-UMA2`)

### JN
- Mismos nomencladores
- Diccionario de Tarifas JN
- TTR Resoluciones (hojas: `TTR` y `SGII-UMA2`)
- Nota: aplica factor energía (GNC×1.3, Eléctrico×1.5, Diesel×1.0)

## Formato del Excel de Tarifas

El Excel de tarifas debe tener tres columnas:

```
Id | Limite Inferior | Limite Superior
```

Los Ids siguen la nomenclatura estándar del sistema:
- `1SCN`, `2SCN`, ..., `5SEAN` → secciones normalizadas (C, E, EA)
- `1SCSN`, ..., `5SEASN`       → secciones sin nominalizar
- `1SCNLP`, ..., `5SESNLP`     → La Plata
- `1-4KMCN`, `1-4KMEN`, etc.   → KM exactas
- `5KPCN`, `6KPCN`, ..., `9KPEASN` → KP (kilométrico-pasaje)
- `1-4KMCN2`, etc.             → KM rangos intermedios
- `1SRN`, ..., `5SRSN`         → Semi-Rápido

## Configuración global

En el sidebar de la app podés cambiar:
- **Año** de la resolución
- **Número de resolución**

Estos valores se usan para construir las claves `CONCAT_MACHEO2` y `CONCAT_MACHEO3`
que hacen el matching con la TTR teórica.
