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
    documento.py          ← normaliza «Documento» (FC-21562 → FC - 21562) + es_fc/es_pago
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
    preview_dialog.py     ← resumen antes de confirmar; fechas de cheque editables + alerta naranja
    result_dialog.py      ← resultados después de procesar (export a Excel)
    settings_dialog.py    ← configuración (sanitiza prefijo EMPRESA_)
    theme.py              ← estilos visuales + NoScrollComboBox + NoScrollDateEdit
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

Amarillo aceptado: `FFFF00` en cualquiera de sus codificaciones (`FFFFFF00`, `00FFFF00`) o `indexed` 5/13 (paleta legacy). Los colores del **tema** no se pueden resolver sin parsear el XML del tema, así que no se aceptan — pero si una fila con datos completos está pintada de un amarillo/dorado distinto o de un color del tema, `leer_dm` lo reporta en `avisos_out` (ver Fase 2 abajo). Antes esas filas se ignoraban en absoluto silencio.

### Normalización de «Documento» (`domain/documento.py`)

`dm_reader` normaliza el documento **una sola vez, al leer**: `" fc -21562 "` → `"FC - 21562"`. De ese texto dependen tres cosas, y las tres fallaban en silencio con un guion sin espacios:

1. `AplicacionOrigen` del POST (a qué documento se aplica el pago)
2. el match contra `IDENTIFICACIONEXTERNA` de `composicionSaldoProveedor` (si no coincide, el proveedor desaparecía como "sin saldo")
3. `es_fc()`, que decide la base imponible de las retenciones (un `FC-21562` se pagaba sin retener)

`es_fc()` y `es_pago()` viven acá y los importan `fraccionador`, `retenciones` y `main_window` — antes había dos `_es_fc` duplicados con el mismo bug.

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
8. `PreviewDialog` → el usuario confirma; puede **editar la fecha de vencimiento de cada cheque** in-line (mutación directa sobre `ChequeEmitido.fecha_vencimiento`, que llega al POST sin pasos extra). Filas con fecha < hoy o > hoy + 180 días se pintan de naranja y aparece un banner con el conteo
9. `_ProcesarWorker` (QThread, **serial intencionalmente**): POST por cada OP → `ResultDialog`
10. `_on_terminado` → invalida el cache de saldos siempre (cualquier POST pudo haber quedado registrado) y actualiza ÚLTIMO Nº de la chequera principal. Si **todos** los resultados fueron OK, `_limpiar_tras_envio_exitoso` vacía `_proveedores`, `_ops_a_procesar`, restaura el label del archivo y repuebla la tabla vacía. Si hubo errores parciales, `_quitar_confirmados` saca de `_proveedores` los que volvieron OK (evita el reenvío duplicado en el reintento)

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

### NoScrollComboBox / NoScrollDateEdit

Subclases de `QComboBox` y `QDateEdit` definidas en `theme.py`. Overridean `wheelEvent` con `event.ignore()` para evitar cambios accidentales con la rueda del mouse. Ambas comparten el mismo patrón — cada selector interactivo que exponga la app debería usar la variante `NoScroll*` correspondiente.

### Alerta de cheques con fecha fuera de rango (PreviewDialog)

Motivación: cheque emitido a **06/05/2027** cuando se quiso poner 06/06/2026 (typo de día). Como el parser infiere el año siguiente cuando la fecha ya pasó respecto de hoy, un tipeo en el día terminó mandando el cheque casi un año hacia adelante. La alerta previa al envío atrapa este tipo de error.

- Constante `ALERTA_FUTURO_DIAS = 180` en `preview_dialog.py`
- Motivo se calcula por cheque: `< hoy` → `"anterior a hoy"`; `> hoy + 180 días` → `"a más de 180 días"`; en rango → `None`
- Fila pintada de naranja (`#FFE2C4` / borde `#E08A2B` / texto `#7A3E00`) cuando el motivo no es `None`
- `QDateEdit` (variante `NoScrollDateEdit`) en la columna "Vencimiento" con `setCalendarPopup(True)` y formato `dd/MM/yyyy`
- Ancho de la columna fijado a 140 px (`ResizeMode.Fixed`) porque `ResizeToContents` no respeta el `sizeHint` de un `cellWidget`
- Banner superior con conteo total de cheques en alerta que se refresca en vivo al editar
- Al editar la fecha, `_on_cheque_date_changed` muta `ChequeEmitido.fecha_vencimiento` directamente — `_ProcesarWorker` recibe la misma referencia y el POST envía el valor corregido

### Protecciones contra reenvío duplicado (Fase 1)

Tres defensas alrededor del POST, todas en `main_window.py`:

1. **Reintento tras error parcial** — `proveedores_pendientes()` (función pura, testeada) saca de la lista los proveedores cuya OP volvió `OK`. Compara por `(cuit, nombre)`, **no por `id()`**: `_construir_ops` puede haber creado una copia con `dataclasses.replace` al filtrar ítems sin saldo. `_on_terminado` la usa vía `_quitar_confirmados` en la rama de error parcial.
2. **Cache de saldos invalidado siempre** — al terminar el envío, `_docs_pendientes_cache = None` y `_docs_pendientes_ts = 0.0`. Sin esto, el TTL de 15 min mostraba como pendientes documentos recién pagados.
3. **Numeración de cheques desfasada** — `_PrecargarWorker` trae el `NumeroActual` de la chequera configurada y `_confirmar_ultimo_cheque` compara contra el campo ÚLTIMO Nº (`numero_cheque_desfasado()`, función pura). Si difieren, diálogo Sí/No/Cancelar: usar el del ERP (otro usuario emitió), seguir con el de la app (se saltearon cheques anulados) o abortar. Sólo se pregunta si hay al menos un proveedor en modalidad `CHEQUE_PROPIO`.

Además, los cortes de red se distinguen de los errores de API: `NetworkError` (alias de `httpx.RequestError`, exportado desde `api/client.py`) genera un detalle que arranca con `SIN CONFIRMACION`, porque el POST pudo haber quedado registrado sin que se leyera la respuesta. Ese pago **no** se saca de la lista: requiere verificación manual en Finnegans.

### Avisos de carga del Excel (Fase 2)

`leer_dm(path, avisos_out=[])` acumula avisos a nivel archivo (no atados a un proveedor). `main_window._cargar_excel` los concatena con los `p.avisos` de cada proveedor y los muestra en el `QMessageBox` de "Avisos al cargar el Excel", **antes** de disparar la verificación de saldos (hablan del archivo, no de Finnegans).

Qué avisa hoy:

| Situación | Antes | Ahora |
|---|---|---|
| Fila con datos completos pintada de un amarillo no estándar o de un color del tema | se ignoraba en silencio | aviso con el número de fila (hasta 10) |
| Dos o más columnas cuyo header contiene «importe» | se tomaba la primera en silencio | aviso indicando cuál se usó |
| Fecha inexistente en «Forma de pago» (`Ch 31/02`) | se descartaba y salía un cheque menos | aviso por texto único (`clasificador` + `parser_pago.fechas_descartadas`) |
| Faltan columnas requeridas | listado de faltantes | además aclara que los headers van en la **primera** fila y lista lo que leyó ahí |
| Proveedor auto-eliminado por no tener saldo pendiente | mensaje de 7 s en la barra de estado | `QMessageBox` con la lista y la pista del formato de «Documento» |

### Auto-limpieza tras envío exitoso

Después de que `ResultDialog` se cierra, si `all(r["estado"] == "OK" for r in resultados)`:

- `_proveedores` y `_ops_a_procesar` se vacían
- `_lbl_archivo` vuelve a `"Sin archivo cargado"` con objectName `"Muted"`
- `_poblar_tabla()` repinta la tabla vacía y actualiza los KPIs a cero
- Status bar muestra `"Procesamiento terminado. Excel limpiado."` durante 5 s

Si al menos un resultado no fue `"OK"`, el estado se conserva para reintento manual. Los proveedores en modalidad `MANUAL` no cuentan para la decisión — sólo los resultados del POST real.

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
6. **La alerta de fechas de cheque tiene que ser bidireccional** — flag para `< hoy` **y** `> hoy + 180 días`. El parser de fechas infiere el año siguiente cuando la fecha ya pasó, así que un typo en el día se manifiesta como fecha muy futura, no como fecha atrasada
7. **Todo QDateEdit interactivo debe ignorar la rueda del mouse** — usar `NoScrollDateEdit` (mismo patrón que `NoScrollComboBox`); si no, un scroll accidental cambia el valor
8. **Después de recompilar el `.exe` verificar el `LastWriteTime` real del binario** — los mensajes de éxito de PyInstaller pueden reportar OK sin haber actualizado el archivo en disco (proceso viejo bloqueando, cache raro). Comparar contra `Get-Date` antes de darlo por cerrado
9. **Nunca dejar en la lista un proveedor cuya OP volvió `OK`** — el reintento tras error parcial lo reenviaría y duplicaría la OP. Comparar proveedores por `(cuit, nombre)`, nunca por `id()`
10. **Todo POST enviado invalida el cache de saldos** — no importa el resultado: un timeout puede haber quedado registrado en Finnegans
11. **Los cortes de red no son errores de API** — `NetworkError` requiere verificación manual (`SIN CONFIRMACION`), no reintento automático
12. **El «Documento» se normaliza una sola vez, en `dm_reader`** — nunca comparar `item.documento` crudo contra Finnegans ni reimplementar `_es_fc` local: usar `domain/documento.py`
13. **Si una fila del Excel se descarta, tiene que quedar registrado en `avisos_out`** — los silencios en la lectura son la clase de bug más caro de esta app: nadie se entera hasta que falta un pago
14. **Hay un hook de seguridad en el entorno que bloquea las ediciones que contengan la llamada a `.exec` de Qt escrita con paréntesis** — para diálogos modales nuevos usar los métodos estáticos (`QMessageBox.question` / `warning`) en lugar de instanciar y lanzar el diálogo a mano

---

## Estado de Fases (plan post-manual, 2026-08-03)

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Commit/push de fechas editables + manual de usuario | ✅ hecho |
| 1 | Riesgo de plata: reenvío duplicado, numeración de cheques, cortes de red | ✅ hecho |
| 2 | Silencios en la lectura del Excel: amarillo de tema ignorado, `Documento` con formato distinto que descarta al proveedor como "sin saldo", fechas inexistentes (`Ch 31/02`), mensaje de encabezados fila 1, aviso de columna "importe" duplicada | ✅ hecho |
| 3 | Tolerancia en «Forma de pago»: `Cheque 15/05`, `transferencia bancaria`, `Transferencia inmediata` caen en MANUAL | ⏳ pendiente |
| 4 | Distribución: versión visible en el título, aviso de versión nueva, firma de código (compra) | ⏳ pendiente |
