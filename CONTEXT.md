# Generador de Pagos — Contexto del proyecto

App de escritorio (PyQt6 + Python 3.11+) que automatiza la generación de Órdenes de Pago en el ERP **Finnegans** a partir de una planilla Excel llamada "DM" (hoja "DM").

**Por qué existe:** La empresa paga a proveedores desde una planilla autorizada. Esta app lee esa planilla, clasifica las filas, genera cheques o transferencias, calcula retenciones de Ganancias, y hace POST a la API de Finnegans para crear las OPs.

El config se guarda cifrado con Fernet en `%APPDATA%/GeneradorDePagos/`.

---

## Stack

- Python 3.11+, PyQt6, openpyxl, httpx, cryptography
- Sin base de datos local; todo en memoria durante la sesión
- Distribuido como `.exe` con PyInstaller (auto-build vía GitHub Actions)

---

## Estructura de carpetas

```
src/
  config.py               ← config cifrada con Fernet en %APPDATA%
  main.py                 ← entry point PyQt6
  domain/
    models.py             ← ItemFactura, ProveedorTanda, ChequeEmitido, OpPago, Modalidad
    clasificador.py       ← asigna CHEQUE_PROPIO / TRANSFERENCIA / MANUAL (por signo + Forma de pago)
    parser_pago.py        ← parsea "Ch 08/05 - 10/05", detecta modalidad, fuzzy match transferencia
    fraccionador.py       ← genera ChequeEmitido[] (consolida FCs con mismas fechas)
    numeracion.py         ← calcula secuencia prevista de comprobantes OP
    retenciones.py        ← escala Ganancias con acumulado histórico + reducción por créditos
    mapper.py             ← arma JSON del POST /ordenPago (sanitiza EmpresaCodigo)
  excel/
    dm_reader.py          ← lee hoja "DM", filtra filas amarillas → ProveedorTanda[]
  api/
    client.py             ← FinnegansClient (OAuth + GET/POST); AuthError, ApiError
    endpoints.py          ← URLs de cada endpoint Finnegans
  util/
    audit.py              ← log persistente JSONL de request/response Finnegans
  ui/
    main_window.py        ← ventana principal, worker threads paralelos
    preview_dialog.py     ← resumen antes de confirmar
    result_dialog.py      ← resultados después de procesar (export a Excel)
    settings_dialog.py    ← configuración (sanitiza prefijo EMPRESA_)
    theme.py              ← estilos visuales + NoScrollComboBox
    icons/
      chevron_down.svg
      chevron_right.svg
tests/
  test_smoke.py
  test_parser_pago.py
  test_clasificador.py
  test_fraccionador.py
  test_retenciones.py
  test_mapper.py
  test_dm_reader.py
  test_result_dialog.py
  fixtures/               ← 07.05.2025.xlsx, response_OP-0004-00021922.json

.github/workflows/
  release.yml             ← compila y publica el .exe al release "latest" en cada push a master
```

---

## Convención de signos (lógica universal)

Regla central que decide todo el comportamiento:

| Excel (Finnegans) | Interno (app) | Significado |
|---|---|---|
| Negativo (FC, ND, MOVFONDOS) | Positivo | **A pagar** (genera cheque/transferencia) |
| Positivo (PAGO, NC, MOVFONDOS) | Negativo | **Crédito / saldo a favor** (reduce el bruto, no genera cheque) |

`dm_reader` aplica `importe_interno = -importe_excel` universalmente. **El prefijo del documento NO decide si es crédito o pagable** — solo el signo lo decide. Esto cubre el caso de MOVFONDOS que pueden venir en positivo o negativo según corresponda.

### Uso del prefijo del documento

El prefijo (FC, MOVFONDOS, NC, ND, PAGO) ya **no** decide validez ni clasificación. Sus únicos usos son:

1. **`fraccionador`**: distinguir FCs (consolidables si comparten fechas) del resto de pagables
2. **`mapper` (POST)**: `AplicacionOrigen = item.documento` (con prefijo) — Finnegans lo usa para aplicar el pago al documento correcto

### Validez de fila en `dm_reader`

La única regla de validez es: **fila pintada de amarillo + documento no vacío + proveedor + importe ≠ 0**. No hay whitelist de prefijos.

---

## Flujo de datos

1. Usuario carga Excel → `leer_dm()` → lista de `ProveedorTanda`
   - Si se detectan typos en "transferencia" → diálogo de avisos al usuario
2. `_ChiquerasLoader` (QThread): carga chequeras automáticamente; rellena ÚLTIMO Nº y LÍMITE
3. `_SaldoCheckerWorker` (QThread, **paralelo 8 threads**): consulta `composicionSaldoProveedor` por cada CUIT; auto-elimina proveedores sin saldo pendiente; guarda cache con TTL 15 min
4. `_PrecargarWorker` (QThread, **paralelo 8 threads**): consulta retenciones, ratios FC, cotización dólar. Reutiliza el cache de saldos del paso anterior
5. `_construir_ops()` → arma `OpPago[]` con cheques fraccionados y retenciones calculadas
6. `_manejar_overflow()` → diálogo para asignar chequera alternativa si se excede el límite
7. `_asignar_numeros_op()` → calcula `numero_comprobante_estimado`
8. `PreviewDialog` → el usuario confirma
9. `_ProcesarWorker` (QThread, **serial intencionalmente**): POST por cada OP → `ResultDialog`
10. `_on_terminado` → actualiza ÚLTIMO Nº de la chequera principal

---

## API Finnegans (endpoints relevantes)

| Endpoint | Uso |
|---|---|
| `GET /oauth/token` | Bearer token (UUID en texto plano, no JSON) |
| `POST /ordenPago` | Crea la OP |
| `GET /proveedor/{cuit}` | Percepciones del proveedor |
| `GET /retencion/{codigo}` | Tramos de retención |
| `GET /facturaCompra/{doc}` | Ratio gravado/total de la FC |
| `GET /reports/analisisRetencion` | Histórico del mes (ISAR + ya retenido) |
| `GET /reports/MONEDACOTIZACION` | Cotización dólar |
| `GET /Talonario/list` | Lista de chequeras activas |
| `GET /Talonario/{codigo}` | Detalle de chequera (`NumeroActual`, `LimiteHasta`) |
| `GET /reports/composicionSaldoProveedor?PARAMWEBREPORT_fecha=...&PARAMWEBREPORT_organizacion={cuit}&PARAMWEBREPORT_cuenta=02.01.01.01.0001` | Documentos con saldo pendiente |
| `GET /empresa/list` | Lista de empresas (**devuelve `EMPRESA_EMPRE01`**; el POST espera `EMPRE01`) |

---

## Columnas requeridas en el Excel

El Excel debe tener una hoja llamada **"DM"** con estas columnas (case-insensitive, los headers se detectan automáticamente):

| Header en Excel | Uso |
|---|---|
| **Documento** | Ej. `FC - 21562`, `PAGO - 14062`, `MOVFONDOS - 10845` |
| **Proveedor** | Nombre del proveedor (fallback si no hay CUIT) |
| **CUIT** | CUIT del proveedor (con o sin guiones; se normaliza) |
| **Comprobante** | Ej. `A-0007-00000004` |
| **Importe** (o "Importe ppal") | Signo respeta convención Finnegans (negativo=adeuda, positivo=crédito) |
| **Forma de pago** (también acepta "PAGO" o "Condicionpago") | Ej. `transferencia`, `Ch 08/05 - 15/05`, etc. |
| **Fecha vto** | Opcional, fallback si no hay fechas parseables en Forma de pago |

Filas válidas: las pintadas de **amarillo**. El resto se ignora.

---

## Validaciones de seguridad implementadas

| ID | Descripción |
|---|---|
| A1 | CUIT validado antes de cada OP (11 dígitos numéricos) |
| A2 | Documentos ya pagados omitidos via `composicionSaldoProveedor`; **PAGO - bypasea este filtro** (es un crédito, no un pago) |
| A3 | Total de la OP > 0 |
| A4 | Agrupación por CUIT en `dm_reader.py` |
| A5 | Validación de existencia de hoja "DM" con mensaje descriptivo |
| A6 | Validación de config con `missing_fields()` |
| A7 | Sanitización de `EmpresaCodigo` quitando prefijo `EMPRESA_` (fix bug C2, ver abajo) |
| A8 | Tolerancia a typos en "transferencia" + aviso al usuario para que corrija el Excel |
| Fase 2a | Inferencia de año en fechas de cheques |
| Fase 2b | Aviso si cotización dólar no está configurada |
| Fase 2c | Auto-actualización de ÚLTIMO Nº al terminar |
| Fase 2d-e | Soporte multi-chequera con overflow |
| Fase 3 | Log persistente JSONL de request/response Finnegans |

---

## Detalles técnicos importantes

### Créditos (PAGO -, NC, MOVFONDOS positivo)

Los créditos reducen el bruto **antes** de calcular retenciones y **antes** de fraccionar los cheques. Flujo:

1. `bruto_fc = sum(items con importe > 0 que son FCs)`
2. `credito_total = sum(items con importe < 0)` (ya negativo)
3. `base_imponible_neta = base_imponible_bruta × (neto / bruto_fc)` ← base reducida proporcionalmente
4. `retenciones = escala(base_imponible_neta)`
5. `total_cheques = bruto + credito_total` (créditos negativos restan)
6. `neto_final = total_cheques - retenciones`

En el CtaCte del POST:
- Items pagables (FC, ND, MOVFONDOS negativo) → `DebeHaber: 1`, importe positivo (Debe)
- Items crédito (PAGO -, NC, MOVFONDOS positivo) → `DebeHaber: -1`, importe positivo abs() (Haber)

Finnegans **rechaza** `ImporteMonTransaccion` negativo en CtaCte, por eso se invierte `DebeHaber`.

### Fraccionamiento de cheques

La cantidad de cheques sale de la **columna "Forma de pago"**, no del prefijo del documento:
- `Ch 08/06 - 09/06 - 18/06` → 3 cheques
- `Ch 15/05` → 1 cheque
- `transferencia` (sin fechas) → 1 entrada de banco con el neto
- Sin contenido parseable → 1 cheque con `fecha_vto` como fallback

Para FCs del mismo proveedor con fechas **idénticas** se consolida en un solo set de N cheques sobre el total (no N cheques por FC). Para fechas distintas, cada FC se fracciona por separado.

### Retenciones de Ganancias

- `ISAR` en el POST = base imponible de la OP actual (porción gravada × ratio FC × factor por créditos)
- `ISARAcumulado` = histórico del mes + base imponible actual
- Fórmula: `retencion_bruta = escala(isar_acumulado)` → `retencion_final = max(0, retencion_bruta - ya_retenido_mes)`

### Tolerancia a typos en "transferencia"

`parser_pago.es_transferencia()` usa fuzzy match con `difflib.SequenceMatcher` (threshold 0.80):
- Aceptados: `transferencia`, `tranferencia`, `transferensia`, `trnasferencia`, `Transferenc`, `transferenia`, etc.
- Rechazados: `tarjeta`, `efectivo`, `Ch 08/05`, `Cheque`, `mercado pago` (todos quedan en <0.40)

Si se detecta un typo, `clasificador.clasificar()` agrega un mensaje a `proveedor.avisos[]`. Al cargar el Excel, `main_window` muestra un `QMessageBox.warning` con todos los avisos para que el usuario corrija el archivo.

### Sanitización de EmpresaCodigo

`/empresa/list` devuelve el código con prefijo `EMPRESA_EMPRE01` (formato interno de Finnegans), pero el POST de OPs espera el código de negocio limpio `EMPRE01`. Sin sanitizar, Finnegans no resolvía la empresa y devolvía: *"El usuario solo tiene permisos de consulta sobre esta empresa"*.

Fix defensivo en dos lugares:
- `settings_dialog.py:_on_empresas_listas` strippea el prefijo al cargar la lista y al leer el valor guardado (compat con configs viciados)
- `mapper.py:_empresa_codigo_limpio()` sanitiza justo antes de serializar el POST (defensa en profundidad)

### Cache de saldos pendientes (TTL 15 min)

`_SaldoCheckerWorker` guarda los resultados en `self._cache_docs` con timestamp `_cache_docs_ts`. Cuando el usuario hace "Procesar" dentro de 15 min, `_PrecargarWorker` reutiliza el cache en vez de re-consultar Finnegans. Ahorra ~10 s en la segunda corrida.

### Paralelización HTTP

- `_PrecargarWorker` y `_SaldoCheckerWorker` usan `ThreadPoolExecutor(max_workers=8)` para paralelizar consultas a Finnegans
- Diccionarios compartidos (`codigos_ret_cargados`, `ratios_fc`) protegidos con `threading.Lock` en patrón check-then-set
- `_ProcesarWorker` (POSTs de OP) **sigue siendo serial** intencionalmente, porque `NumeroComprobante` viene secuencial de Finnegans y paralelizar podría romper el orden

### NoScrollComboBox

Subclase de `QComboBox` definida en `theme.py`. Overridea `wheelEvent` con `event.ignore()` para evitar cambios accidentales con la rueda del mouse.

---

## Bugs corregidos (historial)

| ID | Descripción | Estado |
|---|---|---|
| A3 | `_PrecargarWorker` con `except Exception: pass` silencioso → ahora loggea y emite progreso visible | ✅ |
| A4 | Match de proveedor por nombre frágil con homónimos → ahora por CUIT | ✅ |
| B1 | `es_cheque` requería espacio (`"ch "`) → ahora regex `\bch\s*\d` | ✅ |
| B4 | Precisión `float` en retenciones → ahora `Decimal` en todo el dominio | ✅ |
| C1 | `EmpresaCodigo` hardcodeado en mapper → ahora `OpPago.empresa_codigo` configurable | ✅ |
| C2 | `EmpresaCodigo` con prefijo `EMPRESA_` desde `/empresa/list` rompía el POST → sanitización en mapper + settings_dialog | ✅ |
| D1 | Retenciones se calculaban sobre el bruto sin considerar créditos → ahora base se reduce proporcionalmente | ✅ |
| D2 | Créditos se aplicaban al último cheque post-hoc → ahora se restan del bruto antes de fraccionar | ✅ |
| D3 | `ImporteMonTransaccion` negativo en CtaCte rechazado por Finnegans → ahora `DebeHaber=-1` con importe absoluto | ✅ |
| E1 | Comparación OP prevista vs OP real generaba falsos warnings ("PAGO - 14062" ≠ "OP-0004-...") → columna eliminada | ✅ |

---

## Estado del repositorio

- GitHub: https://github.com/AdministracionCimal/generador-pagos.git (rama `master`)
- Tests: **76 pasando** (`pytest tests/`); 2 errores pre-existentes de permisos en `test_audit_log.py` y `test_client_audit.py` (no relacionados, son problema de filesystem)
- Build: `dist/GeneradorDePagos.exe` (~56 MB) se recompila localmente con `python -m PyInstaller GeneradorDePagos.spec --noconfirm`
- GitHub Actions: cada push a `master` dispara `.github/workflows/release.yml` → compila en `windows-latest` y publica el `.exe` al release `latest`
- Link permanente de descarga: `https://github.com/AdministracionCimal/generador-pagos/releases/latest/download/GeneradorDePagos.exe`

---

## Optimizaciones de performance (todas implementadas)

| ID | Optimización | Estado |
|---|---|---|
| P1 | `ThreadPoolExecutor(8)` en `_PrecargarWorker` con `threading.Lock` | ✅ |
| P2 | `ThreadPoolExecutor(8)` en `_SaldoCheckerWorker` con `as_completed` | ✅ |
| P3 | Cache `_cache_docs` con TTL 15 min entre workers | ✅ |
| P4 | `setUpdatesEnabled(False/True)` al poblar tabla | ✅ |
| P5 | Debounce 150 ms (`QTimer.singleShot`) en campos chequera | ✅ |
| P6 | `@functools.lru_cache(maxsize=512)` en `_fmt_money` | ✅ |

Speedup combinado: ~10× (de ~40 s a ~4 s para 20 proveedores).

---

## Mejoras visuales por fases (resumen)

- **Fase 1** (theme base): paleta sobria, cards de radio 8px, botones sin gradientes fuertes
- **Fase 2** (main_window operativo): barra de métricas con pagos listos, total, cheques, manual, disponibles
- **Fase 3** (PreviewDialog): 4 KPIs (ÓRDENES / BRUTO / RETENCIONES / NETO); tarjetas con desglose
- **Fase 4** (ResultDialog): **simplificado** — 3 KPIs (PROCESADAS OK / CON ERROR / TOTAL); columna "Comparación" eliminada (Finnegans controla la numeración internamente); **export a Excel (.xlsx) en lugar de CSV** con headers en azul, filas de error en rojo, fila de total en azul suave
- **Fase 5** (SettingsDialog): 5 secciones, "Probar conexión" inline, scroll area, tooltips
- **Fase 6** (PreviewDialog y otros): fix de fondo negro entre secciones (`background-color` explícito en widget contenedor)

---

## Reglas críticas para futuras sesiones

1. **No volver a usar prefijos para decidir crédito/pago** — el signo del importe es la única regla
2. **No volver a calcular retenciones sobre el bruto** — siempre reducir por créditos primero
3. **No volver a mandar `ImporteMonTransaccion` negativo** en CtaCte — usar `DebeHaber=-1` con valor absoluto
4. **No paralelizar `_ProcesarWorker`** — los POST de OPs son serializados por diseño
5. **No reagregar la columna "Comparación"** en ResultDialog — generaba falsos warnings
