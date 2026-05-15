# Generador de Pagos — Contexto del proyecto

App de escritorio (PyQt6 + Python 3.11+) que automatiza la generación de Órdenes de Pago en el ERP **Finnegans** a partir de una planilla Excel llamada "DM" (hoja "DM").

**Por qué existe:** La empresa paga a proveedores desde una planilla autorizada. Esta app lee esa planilla, clasifica las filas, genera cheques o transferencias, calcula retenciones de Ganancias, y hace POST a la API de Finnegans para crear las OPs.

El config se guarda cifrado con Fernet en `%APPDATA%/GeneradorDePagos/`.

---

## Stack

- Python 3.11+, PyQt6, openpyxl, httpx, cryptography
- Sin base de datos local; todo en memoria durante la sesión
- Distribuido como .exe con PyInstaller

---

## Estructura de carpetas

```
src/
  config.py               ← config cifrada con Fernet en %APPDATA%
  main.py                 ← entry point PyQt6
  domain/
    models.py             ← ItemFactura, ProveedorTanda, ChequeEmitido, OpPago, Modalidad
    clasificador.py       ← asigna CHEQUE_PROPIO / TRANSFERENCIA / MANUAL
    parser_pago.py        ← parsea "Ch 08/05 - 10/05", detecta modalidad, infiere año
    fraccionador.py       ← genera ChequeEmitido[] (consolida FCs con mismas fechas)
    numeracion.py         ← calcula secuencia prevista de comprobantes OP
    retenciones.py        ← escala Ganancias con acumulado histórico del mes
    mapper.py             ← arma JSON del POST /ordenPago
  excel/
    dm_reader.py          ← lee hoja "DM", filtra filas amarillas → ProveedorTanda[]
  api/
    client.py             ← FinnegansClient (OAuth + GET/POST); AuthError, ApiError
    endpoints.py          ← URLs de cada endpoint Finnegans
  util/
    audit.py              ← log persistente JSONL de request/response Finnegans
  ui/
    main_window.py        ← ventana principal, worker threads
    preview_dialog.py     ← resumen antes de confirmar
    result_dialog.py      ← resultados después de procesar
    settings_dialog.py    ← configuración de la app
    theme.py              ← estilos visuales + NoScrollComboBox
    icons/
      chevron_down.svg    ← flecha combo/árbol (stroke #475569)
      chevron_right.svg   ← rama árbol cerrada
tests/
  test_smoke.py           ← smoke tests; suite completa actual: 56 tests
  test_parser_pago.py     ← tests de es_cheque, parsear_fechas_col_l, es_transferencia
  fixtures/               ← 07.05.2025.xlsx, response_OP-0004-00021922.json
```

---

## Flujo de datos

1. Usuario carga Excel → `leer_dm()` → lista de `ProveedorTanda`
2. `_ChiquerasLoader` (QThread): carga chequeras al inicio automáticamente; rellena ÚLTIMO Nº y LÍMITE desde el detalle del talonario
3. `_SaldoCheckerWorker` (QThread): al cargar Excel, consulta `composicionSaldoProveedor` por cada CUIT con modal de carga bloqueante; auto-elimina proveedores sin saldo pendiente de `self._proveedores`
4. `_PrecargarWorker` (QThread): consulta Finnegans → retenciones, ratios FC, cotización dólar, docs pendientes por CUIT y último comprobante OP (`Talonario/{TE-OP}`)
5. `_construir_ops()` → arma `OpPago[]` con cheques fraccionados y retenciones calculadas. Los proveedores que superan el límite de la chequera van a `_proveedores_overflow`
6. `_manejar_overflow()` → si hay overflow, diálogo para asignar chequera alternativa y construir las OPs restantes sin saltar números
7. `_asignar_numeros_op()` → calcula `numero_comprobante_estimado` para comparar OP prevista vs OP real devuelta por Finnegans
8. `PreviewDialog` → el usuario confirma
9. `_ProcesarWorker` (QThread) → POST por cada OP → `ResultDialog`
10. `_on_terminado` → actualiza automáticamente el ÚLTIMO Nº de la chequera principal en la UI

---

## API Finnegans (endpoints relevantes)

| Endpoint | Uso |
|---|---|
| `GET /oauth/token` | Bearer token (UUID en texto plano, no JSON) |
| `POST /ordenPago` | Crea la OP |
| `GET /proveedor/{cuit}` | Percepciones del proveedor |
| `GET /retencion/{codigo}` | Tramos de retención (escala Ganancias) |
| `GET /facturaCompra/{doc}` | Ratio gravado/total de la FC |
| `GET /reports/analisisRetencion` | Histórico del mes (ISAR + ya retenido) |
| `GET /reports/MONEDACOTIZACION` | Cotización dólar |
| `GET /Talonario/list` | Lista de chequeras activas |
| `GET /Talonario/{codigo}` | Detalle de chequera y talonario OP (`NumeroActual`, `LimiteHasta`) |
| `GET /reports/composicionSaldoProveedor?PARAMWEBREPORT_fecha=...&PARAMWEBREPORT_organizacion={cuit}&PARAMWEBREPORT_cuenta=02.01.01.01.0001` | Documentos con saldo pendiente de un proveedor (filtrado a cuenta proveedores) |

---

## Validaciones de seguridad implementadas

| ID | Descripción |
|---|---|
| A1 | CUIT validado antes de cada OP (no vacío, sin letras) |
| A2 | Documentos ya pagados omitidos via `composicionSaldoProveedor` (fail-open si la API falla) |
| A3 | Total de la OP > 0 (NCs que anulan todo se omiten con advertencia) |
| A4 | Agrupación por CUIT en `dm_reader.py` (mismo CUIT = mismo proveedor) |
| A5 | Validación de existencia de hoja "DM" con mensaje descriptivo |
| A6 | Validación de config con `missing_fields()` (indica exactamente qué campo falta) |
| Fase 2a | Inferencia de año en fechas de cheques (si cae antes de la emisión → año siguiente) |
| Fase 2b | Aviso si cotización dólar no está configurada y la API falló |
| Fase 2c | Auto-actualización de ÚLTIMO Nº en chequera principal al terminar |
| Fase 2d | Aviso cuando cheques emitidos superan el límite de la chequera |
| Fase 2e | Soporte multi-chequera: diálogo para asignar chequera alternativa si se excede el límite |
| Fase 3 | Log persistente JSONL de payloads enviados y respuestas recibidas para auditoría/debug |
| UI | Eliminación múltiple de pagos con checkboxes, seleccionar todos y confirmación |
| UI | Verificación de saldo con modal bloqueante al cargar Excel; proveedores sin saldo se eliminan automáticamente |
| UI | Preview profesional con resumen bruto/retenciones/neto, tarjetas por proveedor y OP prevista |
| UI | Resultado final con highlight de errores/desvíos, footer de resumen y CSV enriquecido |

---

## Detalles técnicos importantes

### Retenciones de Ganancias
- `ISAR` en el POST = base imponible de la OP actual (porción gravada de las FCs)
- `ISARAcumulado` en el POST = histórico del mes + base imponible de esta OP
- `Fecha` en el POST = fecha de la OP
- Fórmula: `retencion_bruta = escala(isar_historico + base_actual)` → `retencion_final = max(0, retencion_bruta - ya_retenido_mes)`

### Fraccionamiento de cheques
- MOVFONDOS / NCCPRA / NDCPRA → siempre 1 cheque por importe completo
- FC con fechas en col L → N cheques según las fechas parseadas
- Si múltiples FCs del mismo proveedor tienen exactamente las mismas fechas → se consolidan en N cheques sobre el total (no N cheques por FC)

### Detección de pagos duplicados
- Se usa `composicionSaldoProveedor` por CUIT (no por comprobante)
- Devuelve solo documentos con saldo pendiente; los ausentes están totalmente pagados
- Permite pagos parciales sin bloquear el resto de los documentos del proveedor

### NoScrollComboBox
- Subclase de `QComboBox` definida en `theme.py`
- Overridea `wheelEvent` con `event.ignore()` para evitar cambios accidentales con la rueda del mouse
- Usada en: chequera principal (`main_window.py`), chequera alternativa overflow, y todos los combos de `settings_dialog.py`

### EmpresaCodigo dinámico (bug C1 — corregido 2026-05-15)
- `EMPRESA_CODIGO = "EMPRE01"` hardcodeado en `mapper.py` fue eliminado
- `OpPago` ahora tiene campo `empresa_codigo: str = "EMPRE01"` (default para retrocompatibilidad)
- `_construir_ops()` y `_manejar_overflow()` pasan `self._cfg.get("empresa_codigo", "EMPRE01")`
- `armar_post()` usa `op.empresa_codigo` → el POST respeta lo configurado en Ajustes

### Precisión Decimal en retenciones (bug B4 — corregido 2026-05-15)
- `retenciones.py` almacena `Importe`, `ISAR`, `ISARAcumulado` e históricos como `Decimal` (no `float`)
- `mapper.py` convierte a `float` al armar el payload JSON → sin pérdida de precisión en cálculos intermedios
- `total_ret` en transferencias suma Decimals directamente en lugar de reconstruir desde `str(float)`

### Detección de cheques sin espacio (bug B1 — corregido 2026-05-15)
- `es_cheque()` en `parser_pago.py` usaba `"ch " in t` (requería espacio) — no detectaba `"ch08/05"`
- Reemplazado por `re.search(r"\bch\s*\d", t)` → detecta con o sin espacio, tabulación, mayúsculas

### Robustez de precarga (bug A3 — corregido 2026-05-15)
- `_PrecargarWorker` tenía `except Exception: pass` en dos niveles: loop de proveedor y bloque analisisRetencion
- Ahora loggea con `_LOG.warning(...)` y emite `progreso` con mensaje `⚠` visible en la UI
- El usuario ve qué proveedor falló en lugar de proceder silenciosamente sin retenciones

### Match de proveedor por CUIT (bug A4 — corregido 2026-05-15)
- `_actualizar_estados_post_precarga()` matcheaba proveedor por nombre (columna 1) — frágil con homónimos
- Ahora lee CUIT de columna 2 y matchea por `p.cuit == cuit`

### Otros fixes menores (2026-05-15)
- `endpoints.py`: método `talonario()` duplicado eliminado; filtro `PARAMWEBREPORT_cuenta=02.01.01.01.0001` en `composicionSaldoProveedor`
- `clasificador.py`: `motivo_manual` usa `sorted(set)` para orden determinístico en mensaje de modalidad mixta
- `main_window.py`: `_saldo_checker.wait(5000)` con timeout de 5s para evitar freeze de UI
- `parser_pago.py`: 2 tests nuevos para `es_cheque` sin espacio

---

## Estado del repositorio

- GitHub: https://github.com/AdministracionCimal/generador-pagos.git (rama `master`)
- Tests: 56 pasando (`pytest tests/`); 2 errores pre-existentes de permisos en audit tests (no relacionados)
- Build: `dist/GeneradorDePagos.exe` se recompila después de cada cambio funcional o visual.

---

## Mejoras visuales por fases

- **Fase visual 1** completada (2026-05-14): pulido base de `src/ui/theme.py`.
  - Paleta más sobria y profesional.
  - Cards menos pesadas, radio de 8px, sin borde inferior decorativo.
  - Botones sin gradientes fuertes; primario sólido y secundarios neutros.
  - Tablas, headers, inputs, group boxes y badges más consistentes.

- **Fase visual 2** completada (2026-05-14): pantalla principal más operativa.
  - Barra de resumen con métricas: pagos listos, total listo, cheques previstos, carga manual, disponibles.
  - Métricas se recalculan al cargar Excel, cambiar chequera, editar último/límite y eliminar pagos.
  - Cards de archivo y chequera más compactas (una sola línea).
  - Badge "Sin saldo" para proveedores ya pagados; se eliminan automáticamente con modal de carga.

- **Fase visual 3** completada (2026-05-15): `PreviewDialog` rediseñado.
  - Barra de 4 KPIs: ÓRDENES / BRUTO / RETENCIONES / NETO A PAGAR.
  - Cada tarjeta de proveedor muestra desglose BRUTO → RETENCIONES → NETO cuando aplica.
  - Layout más compacto (márgenes, espaciados y alto de filas reducidos).

- **Fase visual 4** completada (2026-05-15): `ResultDialog` mejorado.
  - Barra de 4 KPIs con importes: PROCESADAS OK / CON ERROR / DESVÍOS / TOTAL CONFIRMADO.
  - Highlight de filas: rojo `#FEF2F2` para errores, amarillo `#FFFBEB` para desvíos (OP prevista ≠ real).
  - Footer de resumen textual entre tabla y botones.
  - CSV con headers en español, columna `Discrepancia` y fila `TOTALES` al final.

- **Fase visual 5** completada (2026-05-15): `SettingsDialog` reorganizado.
  - 5 secciones: CONEXIÓN / EMPRESA Y BANCO / TALONARIOS / CUENTAS CONTABLES / OPERACIONES BANCARIAS.
  - Botón "Probar conexión" en sección CONEXIÓN con feedback inline (llama `_fetch_token()`).
  - "Cargar desde API" movido al área de acción global sobre las secciones.
  - Tooltips en campos sensibles: URL, Client ID, Client Secret, Código banco, Talonario OP.
  - Scroll area para las secciones; diálogo de tamaño fijo 640×700.
  - Fondo negro entre secciones corregido (`background-color` explícito en `QGroupBox::title` y widget contenedor).
  - Flechas de combos corregidas: reemplazado CSS triangle trick por `chevron_down.svg`.
  - `NoScrollComboBox` en todos los combos para evitar cambios accidentales con la rueda del mouse.
