# Generador de Pagos — Manual de usuario

Aplicación de escritorio (Windows) que toma la planilla **DM** autorizada y genera las
**Órdenes de Pago** en Finnegans: emite cheques propios o transferencias, calcula las
retenciones de Ganancias y hace el alta por API.

> **Regla de oro:** la app **no inventa nada**. Todo lo que hace sale de lo que está escrito
> en la planilla y de lo que Finnegans le contesta. Si la planilla está mal, la OP sale mal.
> Por eso existe la **pantalla de verificación previa**: es el último control humano antes
> de que el pago se registre en el sistema.

---

## Índice

1. [Requisitos](#1-requisitos)
2. [Instalación y primera ejecución](#2-instalación-y-primera-ejecución)
3. [Configuración](#3-configuración)
4. [Cómo tiene que estar armado el Excel](#4-cómo-tiene-que-estar-armado-el-excel)
5. [Cómo interpreta la app cada fila](#5-cómo-interpreta-la-app-cada-fila)
6. [Uso paso a paso](#6-uso-paso-a-paso)
7. [Estados de la tabla](#7-estados-de-la-tabla)
8. [Avisos y diálogos que pueden aparecer](#8-avisos-y-diálogos-que-pueden-aparecer)
9. [Errores frecuentes y cómo resolverlos](#9-errores-frecuentes-y-cómo-resolverlos)
10. [Buenas prácticas y riesgos operativos](#10-buenas-prácticas-y-riesgos-operativos)
11. [Dónde guarda sus datos la app](#11-dónde-guarda-sus-datos-la-app)
12. [Preguntas frecuentes](#12-preguntas-frecuentes)
13. [Anexo A — Distribución interna (para el administrador)](#anexo-a--distribución-interna-para-el-administrador)
14. [Anexo B — Glosario](#anexo-b--glosario)

---

## 1. Requisitos

| Requisito | Detalle |
|---|---|
| Sistema operativo | Windows 10 u 11, 64 bits |
| Python | **No hace falta.** Va todo empaquetado dentro del `.exe` |
| Permisos de Windows | No requiere administrador ni instalación |
| Internet | Sí, salida HTTPS hacia `api.finneg.com` |
| Credenciales | Un **Client ID** y **Client Secret** de la API de Finnegans, con permiso de **alta** (no sólo consulta) sobre la empresa |
| Planilla | El archivo Excel “DM” con la hoja `DM` |
| Espacio en disco | ~150 MB (el `.exe` pesa ~65 MB y se descomprime en una carpeta temporal al ejecutarse) |

---

## 2. Instalación y primera ejecución

### 2.1 Descargar

Link permanente de la última versión:

```
https://github.com/AdministracionCimal/generador-pagos/releases/latest/download/GeneradorDePagos.exe
```

No hay instalador. Es **un solo archivo**. Se recomienda guardarlo en una carpeta propia,
por ejemplo `C:\GeneradorDePagos\`, y crear un acceso directo al escritorio.

### 2.2 Advertencias de Windows en el primer arranque

El `.exe` **no está firmado digitalmente**, así que Windows va a desconfiar la primera vez.
Es normal y no significa que el archivo esté infectado.

| Qué aparece | Qué hacer |
|---|---|
| **“Windows protegió tu PC”** (SmartScreen) | Clic en **Más información** → **Ejecutar de todas formas** |
| El archivo no abre y no pasa nada | Clic derecho en el `.exe` → **Propiedades** → tildar **Desbloquear** → Aplicar |
| El antivirus lo pone en cuarentena | Pedirle a Sistemas que agregue una excepción para esa carpeta (falso positivo típico de apps empaquetadas) |

### 2.3 Primer arranque

- La primera vez tarda unos segundos más (descomprime en `%TEMP%`). Los siguientes arranques son más rápidos.
- Al no haber configuración guardada, la app **abre sola la ventana de Configuración**.
  Hasta que no se completen las credenciales, la app no puede consultar nada a Finnegans.

---

## 3. Configuración

Se abre desde el menú **Archivo → Configuración**. Se guarda **cifrada** en el equipo del
usuario; no viaja a ningún servidor ni queda en el Excel.

### 3.1 Sección CONEXIÓN (obligatoria)

| Campo | Qué es |
|---|---|
| **URL base Finnegans** | `https://api.finneg.com/api` (viene por defecto) |
| **Client ID** | ID de la aplicación registrada en Finnegans |
| **Client Secret** | Clave de esa aplicación. Se muestra oculta y se guarda cifrada |

Botón **Probar conexión**: pide un token a Finnegans y responde en el momento.

- ✓ *Conexión exitosa* → credenciales válidas.
- ✗ *Token request failed 401…* → ID o Secret incorrectos.
- ✗ error de red / timeout → sin internet, proxy o firewall bloqueando.

> Estos tres campos son los **únicos obligatorios**. Si falta alguno, al querer procesar la
> app avisa “Configuración incompleta” y lista lo que falta.

### 3.2 Botón “Cargar desde API”

Trae desde Finnegans las listas de **empresas**, **cuentas contables** y **operaciones
bancarias** y las carga en los combos. Si las credenciales están bien, se dispara solo al
abrir la Configuración.

### 3.3 Resto de las secciones

| Sección | Campo | Valor por defecto | Para qué se usa |
|---|---|---|---|
| EMPRESA Y BANCO | Empresa | `EMPRE01` | Empresa a la que se imputa la OP |
| EMPRESA Y BANCO | Código banco | `00285` | Banco de los cheques/transferencias |
| TALONARIOS | Talonario orden de pago | `TE-OP` | Talonario del que se estima el número de OP |
| CUENTAS CONTABLES | Cheques propios | `02.01.04.01.0009` | Cuenta que se acredita al emitir cheque |
| CUENTAS CONTABLES | Transferencias | `01.01.01.02.0006` | Cuenta bancaria de la transferencia |
| OPERACIONES BANCARIAS | Cheques propios | `EMCHPROP` | Tipo de operación bancaria del cheque |
| OPERACIONES BANCARIAS | Transferencias | `TLote` | Tipo de operación bancaria de la transferencia |

Estos valores **ya vienen correctos para Cimalco**. Sólo se tocan si contabilidad cambia el
plan de cuentas o el talonario. Un valor mal puesto acá no da error en la app: la OP se
crea, pero imputada a la cuenta equivocada.

---

## 4. Cómo tiene que estar armado el Excel

### 4.1 La hoja

El archivo tiene que tener una hoja llamada exactamente **`DM`**. Si no existe, la app
avisa y lista las hojas que encontró.

### 4.2 Los encabezados

Los encabezados van en la **primera fila** de la hoja. No puede haber una fila de título
arriba, ni la tabla puede empezar en la fila 3: la app lee la fila 1 y ahí busca las
columnas. Mayúsculas/minúsculas y tildes son indistintas.

| Encabezado | Obligatorio | Cómo se detecta | Para qué se usa |
|---|---|---|---|
| **Documento** | Sí | Exacto | Documento de Finnegans al que se aplica el pago (ej. `FC - 21562`) |
| **Proveedor** | Sí | Exacto | Nombre del proveedor (se usa para agrupar si no hay CUIT) |
| **Importe** | Sí | Contiene “importe” | Monto, con el signo de Finnegans |
| **Forma de pago** | Sí | Exacto (`Forma de pago` o `Pago`) | Define cheque vs transferencia y **cuántos cheques** |
| **CUIT** | Recomendado | Exacto | Agrupa por proveedor y es lo que se manda en la OP |
| **Comprobante** | Recomendado | Exacto | Va como descripción del ítem en la cuenta corriente |
| **Fecha vto** | Opcional | Contiene “fecha vto” | Vencimiento de respaldo si la forma de pago no trae fechas |

**Cuidados con los encabezados:**

- Si hay **más de una columna con la palabra “importe”** (ej. *Importe original* e *Importe
  ppal*), la app toma **la de más a la izquierda**. Dejá una sola o poné primero la que se paga.
- La columna de vencimiento debe contener el texto **“fecha vto”**. `Fecha vencimiento` **no**
  se detecta.
- La columna de modalidad tiene que llamarse **`Forma de pago`** o **`Pago`**. Otros nombres
  (`Condición de pago`, `Cond. pago`) **no** se detectan y la app corta con error de columna faltante.
- Si falta alguna columna obligatoria, la app no lee nada y muestra el listado de faltantes.

### 4.3 Qué filas se procesan: **las pintadas de amarillo**

Sólo se leen las filas con **relleno amarillo**. El resto se ignora, así que se pueden dejar
filas de referencia sin pintar.

- Alcanza con que **una celda** de la fila esté pintada.
- Tiene que ser el **amarillo estándar** (`FFFF00`), el de *Colores estándar* de la paleta de
  Excel. Un amarillo de *Colores del tema* o un amarillo “parecido” **no se detecta** y esa
  fila se ignora silenciosamente.
- Si al cargar aparecen menos proveedores de los esperados, el 90 % de las veces es esto.

Además, para que una fila amarilla se tome en cuenta necesita: **Documento** no vacío,
**Proveedor** no vacío e **Importe distinto de cero**.

### 4.4 El signo del importe (crítico)

La app respeta la convención de Finnegans:

| En el Excel | Significa | Qué hace la app |
|---|---|---|
| **Negativo** (ej. `-147.000`) | Se le debe al proveedor | **A pagar**: genera cheque o transferencia |
| **Positivo** (ej. `35.000`) | Saldo a favor nuestro | **Crédito**: descuenta del bruto, no genera cheque |

**Lo decide el signo, no el prefijo del documento.** Un `MOVFONDOS` puede venir positivo o
negativo y la app lo interpreta bien en los dos casos. En la práctica: FC y ND vienen
negativos (a pagar); NC y PAGO vienen positivos (a favor); MOVFONDOS depende.

### 4.5 La columna Documento: formato exacto

El formato es **`PREFIJO - NÚMERO`**, con espacios alrededor del guion, tal como lo exporta
Finnegans: `FC - 21562`, `PAGO - 14062`, `MOVFONDOS - 10845`, `NC - 3021`.

Esto importa de verdad, porque el texto se usa para:

1. **Aplicar el pago al documento correcto** en Finnegans (se manda tal cual).
2. **Verificar que el documento tenga saldo pendiente** (comparación de texto exacta contra
   lo que devuelve Finnegans). Si el texto no coincide, la app cree que ya está pagado y
   **elimina el proveedor de la lista**.
3. Detectar las **facturas (`FC - `)**, que son la base de las retenciones de Ganancias y las
   únicas que se consolidan en un solo juego de cheques.
4. Detectar los **`PAGO - `**, que son los únicos créditos que se mandan igual aunque no
   figuren con saldo pendiente.

Escribir `FC-21562` (sin espacios) hace que la app no la reconozca como factura: se pagaría
sin calcular retención. **Copiar y pegar desde Finnegans, no tipear a mano.**

Los documentos que empiezan con **`OP`** se descartan siempre (ya son órdenes de pago
procesadas).

### 4.6 La columna Forma de pago

Define **la modalidad** y **cuántos cheques** se emiten. No lo define el tipo de documento:
un MOVFONDOS también puede pagarse en 3 cheques.

| Lo que se escribe | Resultado |
|---|---|
| `Ch 15/05` | 1 cheque al 15/05 |
| `Ch 08/06 - 09/06 - 18/06` | 3 cheques, uno por fecha, importe dividido en partes iguales (el último absorbe los centavos) |
| `transferencia` | 1 transferencia por el neto |
| `transf`, `transf.`, `transferencia interbancaria` | Igual que transferencia |
| `tranferencia`, `transferensia`, `trnasferencia` | Se acepta como transferencia y **avisa del error de tipeo** |
| Vacío o texto no reconocido | El proveedor queda en **Carga manual** |

**Trampas reales, verificadas:**

| Texto | Qué pasa |
|---|---|
| `Cheque 15/05` | ❌ **No** se reconoce como cheque → Carga manual. Tiene que ser `Ch` seguido del número |
| `transferencia bancaria` | ❌ No se reconoce → Carga manual |
| `Transferencia inmediata` | ❌ No se reconoce → Carga manual |
| `trans` | ❌ Demasiado corto → Carga manual |
| `efectivo`, `mercado pago`, `tarjeta` | ❌ Carga manual (correcto: la app no los soporta) |
| `Ch 31/02` | ⚠️ Fecha inexistente: se ignora y sale **1 cheque con la fecha de la columna Fecha vto**, o con la fecha de hoy si no hay |

**Las fechas se escriben `dd/mm` sin año.** La app asume el año en curso y, si la fecha ya
pasó, asume el año siguiente. De ahí el riesgo: hoy 03/08/2026, escribir `Ch 08/05` genera un
cheque al **08/05/2027**. Un error de tipeo en el día puede mandar el cheque casi un año
hacia adelante. Por eso existe la alerta naranja en la pantalla previa — **hay que mirarla**.

**Un proveedor no puede mezclar modalidades.** Si tiene una fila `Ch 10/06` y otra
`transferencia`, queda en **Carga manual** con el motivo “Modalidad mixta”. Hay que pagarlo
a mano en Finnegans, o dividirlo en dos tandas.

---

## 5. Cómo interpreta la app cada fila

### 5.1 Agrupación

Todas las filas amarillas del mismo **CUIT** se juntan en un solo proveedor → **una sola
Orden de Pago**. Si una fila no tiene CUIT, se agrupa por nombre (y después se omite al
procesar, porque el CUIT es obligatorio para la OP).

### 5.2 Créditos (PAGO, NC, MOVFONDOS positivo)

El saldo a favor **se descuenta del bruto antes que todo**:

```
1. Bruto            = suma de las facturas y débitos a pagar
2. Crédito          = suma de los saldos a favor
3. Base imponible   = porción gravada de las FC, reducida en la misma proporción
                      que el crédito reduce el bruto
4. Retenciones      = escala de Ganancias sobre esa base
5. Total a pagar    = bruto − crédito
6. Neto (cheques o transferencia) = total a pagar − retenciones
```

O sea: el crédito **no** se resta del último cheque; se resta del total y recién después se
fracciona. Y **sí** afecta el cálculo de retenciones.

En la cuenta corriente de la OP quedan todos los documentos: los pagables al Debe y los
créditos al Haber. Es exactamente como trabaja Finnegans.

### 5.3 Fraccionamiento de cheques

- Cada documento pagable se fracciona según **su propia** columna Forma de pago.
- Si **todas las facturas** de un proveedor tienen **exactamente las mismas fechas**, se
  consolidan en **un solo juego de N cheques por el total**, en lugar de N cheques por factura.
- Si las fechas difieren, cada factura se fracciona por separado.
- Los números de cheque salen del campo **ÚLTIMO Nº** de la pantalla principal: se emite
  desde `último + 1` en adelante, en orden.

### 5.4 Retenciones de Ganancias

Se calculan solas, sólo sobre las **facturas (`FC - `)**, y sólo si el proveedor tiene la
retención configurada en Finnegans. La app consulta:

- el padrón de percepciones del proveedor,
- la escala vigente de la retención,
- la proporción gravada de cada factura,
- **lo ya retenido en el mes** (para no retener dos veces).

Fórmula: `retención = escala(acumulado del mes + base actual) − ya retenido en el mes`, con
piso en cero. Si el proveedor no tiene retención, o la base no llega al mínimo imponible, no
se retiene nada y no aparece la sección Retenciones en la pantalla previa.

---

## 6. Uso paso a paso

### Paso 1 — Cargar la planilla

**Cargar Excel…** → elegir el archivo. Ojo: el selector muestra `*.xls` además de `*.xlsx`,
pero **los `.xls` viejos no se pueden leer**. Si la planilla es `.xls`, abrirla en Excel y
guardarla como `.xlsx`.

Al cargar, la app:

1. Lee las filas amarillas y arma la lista de proveedores.
2. Muestra un cartel de **“Verificando saldos”** mientras consulta a Finnegans qué documentos
   siguen con saldo pendiente. Es bloqueante a propósito: no se puede procesar hasta que termine.
3. **Elimina automáticamente** los proveedores cuyos documentos ya no tienen saldo (ya
   pagados). Los nombra en la barra de estado durante unos segundos.
4. Si detectó errores de tipeo en “transferencia”, muestra la lista para que se corrija el Excel.

### Paso 2 — Revisar la chequera

| Campo | Qué es |
|---|---|
| **CHEQUERA** | Talonario de cheques. **Cargar chequeras** trae las activas de Finnegans |
| **ÚLTIMO Nº** | Último cheque **ya emitido**. Se completa solo al elegir la chequera |
| **LÍMITE** | Último número físico de la chequera. Se completa solo |
| **DISPONIBLES** | `LÍMITE − ÚLTIMO Nº`. Verde si alcanza, rojo si no |

Los dos campos son editables a mano y se guardan para la próxima vez. **Verificar que el
ÚLTIMO Nº coincida con la chequera física** antes de procesar: de ese número salen los
cheques que se van a imprimir.

Si la modalidad es sólo transferencia, la chequera no se usa.

### Paso 3 — Revisar la tabla y la barra de métricas

La barra superior muestra: **PAGOS LISTOS**, **TOTAL LISTO**, **CHEQUES PREVISTOS**,
**CARGA MANUAL** y **DISPONIBLES**. Si CHEQUES PREVISTOS supera DISPONIBLES, el número se
pone en rojo.

En la tabla se puede **tildar filas y eliminarlas** (botón *Eliminar seleccionados*). El
tilde del encabezado marca/desmarca todo. Eliminar acá **no toca el Excel**, sólo saca el
pago de esta tanda.

### Paso 4 — Procesar pagos

Botón **Procesar pagos**. La app consulta retenciones, cotización del dólar y saldos
(reutiliza lo consultado en el paso 1 si pasaron menos de 15 minutos) y arma las OPs.

Acá pueden aparecer, en este orden:

1. **Cotización del dólar no disponible** → se puede continuar (usa $1) o cancelar.
2. **Chequera insuficiente** → elegir otra chequera para los proveedores que no entraron, o
   omitirlos.
3. **Proveedores omitidos** → lista de lo que quedó afuera y por qué (CUIT inválido, sin
   saldo, importe cero, sin chequera).

### Paso 5 — Verificación previa (la pantalla más importante)

Muestra, por proveedor: los ítems que se cancelan, los cheques o la transferencia, las
retenciones calculadas, y arriba los totales **ÓRDENES / BRUTO / RETENCIONES / NETO A PAGAR**.

**Qué controlar acá:**

- El **neto a pagar** de cada proveedor contra lo autorizado.
- La cantidad de cheques y sus **fechas de vencimiento**.
- Que las retenciones aparezcan donde corresponde.

**Cheques con fecha sospechosa:** las filas pintadas de **naranja** son cheques con fecha
anterior a hoy, **del día de hoy** (el banco sólo acepta diferidos) o a **más de 180 días**.
Arriba aparece un cartel con el total de cheques en alerta.

La columna **Vencimiento es editable**: se hace clic, se corrige la fecha (o se usa el
calendario) y el cambio **se manda así al sistema**. El cartel se actualiza en el momento.
La rueda del mouse no modifica las fechas, así que no hay riesgo de cambiarlas sin querer.

Botones: **Confirmar y enviar** manda las OPs. **Cancelar** vuelve a la pantalla principal
sin registrar nada.

### Paso 6 — Resultado

La app envía las OPs **una por una** (así Finnegans numera correlativo) y muestra:

- **PROCESADAS OK** / **CON ERROR** / **TOTAL CONFIRMADO**
- Una fila por proveedor con el estado, la referencia devuelta por Finnegans y el importe.
  Las filas con error quedan en rojo y muestran el mensaje del sistema.
- Los proveedores en **Carga manual** aparecen listados con su motivo, para no olvidarlos.

**Exportar Excel** guarda el reporte (`.xlsx`) con totales, para adjuntar al legajo del pago.

### Paso 7 — Cierre

- Si **todas** las OPs salieron OK: la app actualiza el ÚLTIMO Nº de la chequera y **limpia
  la planilla y la tabla** (“Sin archivo cargado”), para que no se reenvíe por error.
- Si **alguna falló**: la lista **queda cargada** para poder reintentar. Ver la advertencia de
  la sección 10.1 antes de volver a apretar Procesar.

---

## 7. Estados de la tabla

| Estado | Color | Significa | Qué hacer |
|---|---|---|---|
| **Listo** | Verde | Se va a enviar | Nada |
| **Carga manual** | Amarillo | Modalidad no soportada, mixta, mal escrita, o sin ítems facturables | Corregir el Excel y recargar, o pagarlo a mano en Finnegans |
| **Excede chequera** | Rojo | Los cheques no entran en el rango de la chequera, o ÚLTIMO Nº / LÍMITE están vacíos o no son números | Completar los números, o preparar una segunda chequera |
| **Sin ítems** | Rojo | El proveedor quedó sin filas válidas | Revisar el Excel |
| **Sin saldo** | Gris | Los documentos ya no tienen saldo pendiente en Finnegans | Verificar si ya se pagó; si no, revisar el formato de la columna Documento |

---

## 8. Avisos y diálogos que pueden aparecer

| Cartel | Cuándo | Qué hacer |
|---|---|---|
| **Avisos al cargar el Excel** | Palabra “transferencia” mal escrita | Se interpretó igual, pero conviene corregir el Excel |
| **No se pudo leer el Excel** | Hoja `DM` inexistente, columnas faltantes, archivo `.xls`, archivo corrupto | Ver el detalle del mensaje y la sección 4 |
| **Sin configuración / Configuración incompleta** | Falta URL, Client ID o Secret | Archivo → Configuración |
| **Chequera** (“Ingresá el último número…”) | ÚLTIMO Nº vacío o no numérico | Completar el campo |
| **Cotización del dólar no disponible** | Finnegans no devolvió cotización | Se puede continuar con $1. Afecta el dato de cotización de la OP |
| **Chequera insuficiente** | Faltan números en la chequera | Asignar otra chequera u omitir esos proveedores |
| **Sin chequeras disponibles** | No hay otra chequera cargada | Cargar chequeras y volver a intentar |
| **Proveedores omitidos** | CUIT inválido, sin saldo, importe cero | Revisar cada caso; esos pagos **no se enviaron** |
| **Nada que procesar** | Ningún pago quedó en estado Listo | Revisar estados en la tabla |
| **Cheques con fecha sospechosa** (banner naranja) | Cheque a hoy o antes, o a más de 180 días | Corregir la fecha en la misma tabla |
| **No se pudo cargar chequeras** | Sin conexión o credenciales inválidas | Probar conexión en Configuración |
| **⚠ *proveedor*: no se pudo cargar histórico de retenciones** | Falló la consulta del mes | **Atención:** la retención puede quedar calculada de menos. Verificar antes de confirmar |

---

## 9. Errores frecuentes y cómo resolverlos

### 9.1 Al cargar el Excel

| Síntoma | Causa | Solución |
|---|---|---|
| “No se encontró la hoja «DM»” | La hoja tiene otro nombre | Renombrar la hoja a `DM` |
| “Faltan columnas requeridas” | Encabezado distinto, o los encabezados no están en la fila 1 | Ver la tabla de la sección 4.2 |
| Carga 0 proveedores | Las filas no están en el amarillo estándar | Repintar con el amarillo de *Colores estándar* |
| Faltan proveedores que sí están pintados | Documento, Proveedor vacíos o Importe = 0 | Completar la fila |
| No se puede abrir el archivo | Es `.xls` | Guardar como `.xlsx` |
| Importes en cero o vacíos | La celda tiene una fórmula sin valor calculado (archivo generado por un sistema, nunca abierto en Excel) | Abrir en Excel, guardar y volver a cargar |

### 9.2 Modalidad y cheques

| Síntoma | Causa | Solución |
|---|---|---|
| Un proveedor quedó en Carga manual sin motivo aparente | Texto de forma de pago no reconocido (`Cheque 15/05`, `transferencia bancaria`) | Escribir `Ch dd/mm` o `transferencia` |
| “Modalidad mixta” | El proveedor mezcla cheque y transferencia | Unificar, o partir en dos tandas |
| Salen menos cheques de los esperados | Alguna fecha es inexistente (`31/02`) o está mal escrita | Corregir las fechas |
| Un cheque quedó con fecha de hoy | La forma de pago no traía fechas y se usó la fecha de respaldo | Corregir la fecha en la pantalla previa |
| Un cheque salió al año que viene | Fecha `dd/mm` ya pasada: la app asume el año siguiente | Corregirla en la pantalla previa (banner naranja) |
| Los números de cheque no coinciden con la chequera física | ÚLTIMO Nº desactualizado | Corregir el campo antes de procesar |

### 9.3 Errores de Finnegans al enviar

| Mensaje | Causa | Solución |
|---|---|---|
| `HTTP 401` / *Token request failed* | Credenciales vencidas o mal cargadas | Probar conexión en Configuración |
| *El usuario sólo tiene permisos de consulta sobre esta empresa* | El usuario de la API no tiene alta habilitada, o la empresa seleccionada no es la correcta | Pedir permisos de alta a Sistemas; verificar la Empresa en Configuración |
| `HTTP 500 … No se permiten importes negativos` | Composición de importes inconsistente (caso conocido y corregido) | Revisar signos en el Excel; si persiste, reportar con el log de auditoría |
| `HTTP 500` genérico de contabilidad | Cuenta contable, talonario u operación bancaria mal configurados | Revisar Configuración con contabilidad |
| Timeout / error de red | Internet o Finnegans caído | Reintentar más tarde. **Antes de reintentar, verificar en Finnegans si la OP se creó** |

> **Importante con los timeouts:** si se corta la conexión justo después de enviar, la OP
> puede haber quedado creada en Finnegans aunque la app la muestre con error. Siempre
> verificar en el sistema antes de reintentar ese pago.

### 9.4 La aplicación

| Síntoma | Causa | Solución |
|---|---|---|
| No abre / SmartScreen la bloquea | `.exe` sin firma | Sección 2.2 |
| Tarda en abrir | Descompresión del primer arranque | Normal |
| Parece colgada al cargar el Excel | Está consultando saldos | Esperar a que cierre el cartel |
| Se cerró sola | Error inesperado | Volver a abrir; nada se pierde. Guardar el log de auditoría (sección 11) y reportarlo |
| Pide configuración de nuevo | Perfil de Windows distinto, o se borró `%APPDATA%\GeneradorDePagos` | Volver a cargar credenciales |

---

## 10. Buenas prácticas y riesgos operativos

### 10.1 Reintento después de un error parcial (⚠️ riesgo de pago duplicado)

Si de 10 OPs 8 salieron OK y 2 fallaron, la lista **queda entera**. Si se aprieta *Procesar
pagos* de nuevo dentro de los 15 minutos, la app reutiliza la verificación de saldos anterior
y **puede volver a enviar las 8 que ya salieron**, generando OPs duplicadas.

**Antes de reintentar, hacer una de estas tres cosas:**

1. Tildar en la tabla las filas que salieron OK y **Eliminar seleccionados** (recomendado); o
2. **Volver a cargar el Excel** (así se revalidan los saldos contra Finnegans y las ya pagadas
   se descartan solas); o
3. Esperar más de 15 minutos.

### 10.2 Dos personas usando la app al mismo tiempo

La numeración de **cheques** la controla la app a partir del ÚLTIMO Nº. Si dos usuarios
procesan pagos con **la misma chequera** en simultáneo, pueden emitir **cheques con el mismo
número**. La numeración de la **OP**, en cambio, la controla Finnegans y no tiene ese problema.

**Regla:** una sola persona por chequera y por tanda. Si hay varios usuarios, asignar una
chequera distinta a cada uno.

### 10.3 Rutina recomendada

1. Confirmar que el Excel está autorizado y que **sólo** las filas a pagar están en amarillo.
2. Cargar el Excel y leer los avisos.
3. Verificar chequera, ÚLTIMO Nº y DISPONIBLES contra la chequera física.
4. Procesar y **leer la pantalla previa completa**, sobre todo el banner naranja de fechas.
5. Confirmar y enviar.
6. **Exportar el Excel de resultado** y archivarlo con la documentación del pago.
7. Verificar en Finnegans un pago al azar (o los que dieron error).

### 10.4 Lo que la app NO hace

- No imprime cheques ni genera el archivo de transferencias del banco.
- No modifica el Excel de origen.
- No anula ni corrige OPs ya creadas: eso se hace en Finnegans.
- No paga proveedores en **Carga manual**: quedan siempre para carga a mano.
- No valida que el proveedor esté correctamente dado de alta más allá del CUIT.

---

## 11. Dónde guarda sus datos la app

Todo queda en el perfil del usuario de Windows, en `%APPDATA%\GeneradorDePagos\`
(atajo: pegar esa ruta en el Explorador):

| Archivo | Contenido |
|---|---|
| `config.enc` | Configuración cifrada (incluye las credenciales) |
| `key.bin` | Clave de cifrado de la configuración |
| `audit_log.jsonl` | Registro de lo enviado y lo respondido por Finnegans (los tokens se enmascaran) |

El `audit_log.jsonl` es lo primero que hay que mandar cuando se reporta un problema: tiene el
detalle exacto de cada OP enviada y la respuesta del sistema.

---

## 12. Preguntas frecuentes

**¿Puedo procesar dos veces el mismo Excel?**
Sí, sin riesgo si se recarga el archivo: la app consulta los saldos pendientes y descarta
solo los documentos ya pagados. El riesgo aparece sólo en el reintento inmediato (sección 10.1).

**¿Qué pasa si cierro la app en medio del envío?**
Las OPs ya enviadas quedan creadas en Finnegans; las que faltaban, no. Verificar en el
sistema y continuar con las pendientes.

**¿Puedo cambiar un importe desde la app?**
No. Lo único editable es la **fecha de vencimiento de los cheques** en la pantalla previa.
Los importes se corrigen en el Excel.

**¿Por qué un proveedor no tiene retención?**
Porque no tiene la retención configurada en Finnegans, porque no hay facturas `FC - ` en la
tanda, o porque la base no supera el mínimo imponible.

**¿Por qué desapareció un proveedor de la lista?**
Porque sus documentos no figuran con saldo pendiente. Si estás seguro de que se debe,
revisá que la columna Documento tenga el formato exacto de Finnegans (sección 4.5).

**¿Necesito instalar Python o Excel?**
No. El `.exe` trae todo. Excel sólo hace falta para editar la planilla.

**¿Se puede usar en varias PC?**
Sí. Cada PC (y cada usuario de Windows) tiene su propia configuración y hay que cargar las
credenciales una vez en cada una.

---

## Anexo A — Distribución interna (para el administrador)

### A.1 ¿Alcanza con mandar el `.exe`?

**Sí.** Es un ejecutable *onefile* de PyInstaller: adentro va el intérprete de Python, PyQt6,
openpyxl, httpx, cryptography, el código fuente y el ícono. El usuario **no instala nada**,
no necesita Python, no necesita permisos de administrador y no necesita el repositorio.

**Lo que sí tiene que hacer el usuario la primera vez (inevitable):**

1. Pasar la advertencia de **SmartScreen** (*Más información → Ejecutar de todas formas*),
   porque el `.exe` no está firmado.
2. Cargar en **Configuración** la **URL, Client ID y Client Secret** de Finnegans. La
   configuración vive en `%APPDATA%` de cada usuario: **no viaja con el `.exe`**.

Es decir: no hay instalación, pero tampoco es *cero pasos*. Son esos dos.

### A.2 Cómo hacerlo llegar

| Vía | Sirve | Observaciones |
|---|---|---|
| **Link de GitHub Releases** | ✅ Recomendado | `https://github.com/AdministracionCimal/generador-pagos/releases/latest/download/GeneradorDePagos.exe` — siempre la última versión. El repo es **público**, así que el link funciona sin cuenta |
| **Carpeta de red compartida** | ✅ Muy práctico | Copiar el `.exe` a un recurso común; se avisa cuando hay versión nueva. Conviene que cada usuario lo copie a su disco local (arranca más rápido) |
| **OneDrive / SharePoint** | ✅ | Compartir link, no adjuntar |
| **Adjunto de mail** | ❌ | Gmail y Outlook **bloquean `.exe`**, incluso dentro de un `.zip`. Ni siquiera llega |
| **WhatsApp / Teams** | ⚠️ | Puede pasar, pero suele agregar advertencias extra de seguridad |

### A.3 Pre-cargar la configuración (opcional)

Si no querés que cada usuario tipee las credenciales, se pueden copiar los **dos** archivos
`config.enc` **y** `key.bin` desde `%APPDATA%\GeneradorDePagos\` de una PC ya configurada a la
misma carpeta de la otra PC. Uno sin el otro no sirve.

Tener en cuenta: eso reparte las credenciales de la API. Lo recomendable en términos de
control es **una credencial por usuario** en Finnegans, así el log de auditoría muestra quién
hizo cada cosa.

### A.4 Cómo se publica una versión nueva

Ya está automatizado: cada `push` a `master` dispara GitHub Actions, que compila en Windows y
reemplaza el `.exe` del release `latest`. El link de descarga nunca cambia.

Para compilar a mano (por ejemplo para probar antes de publicar):

```bash
python -m PyInstaller GeneradorDePagos.spec --noconfirm
```

El resultado queda en `dist\GeneradorDePagos.exe`. **Verificar siempre la fecha de
modificación real del archivo** antes de repartirlo: si el `.exe` estaba en ejecución,
PyInstaller puede informar éxito sin haber reemplazado el binario.

### A.5 Limitaciones a tener en cuenta

| Tema | Situación |
|---|---|
| **No hay número de versión visible** | La app no muestra su versión en ninguna parte, así que no se puede saber qué build tiene cada usuario. Conviene agregarlo al título de la ventana |
| **No hay auto-actualización** | El usuario tiene que volver a bajar el `.exe`. Con carpeta de red es un copiar/pegar |
| **Sin firma digital** | Advertencia de SmartScreen en cada PC nueva y posibles falsos positivos de antivirus. Se resuelve comprando un certificado de firma de código |
| **Repositorio público** | El código y los endpoints son visibles (no hay credenciales en el repo). Si se prefiere, pasarlo a privado — pero entonces el link de descarga deja de funcionar sin cuenta |
| **Numeración de cheques** | Coordinar chequeras entre usuarios (sección 10.2) |

### A.6 Checklist para dar de alta a un usuario nuevo

- [ ] Credenciales de API de Finnegans con permiso de **alta** sobre la empresa
- [ ] `.exe` copiado en una carpeta local propia + acceso directo
- [ ] Primer arranque hecho, SmartScreen aceptado
- [ ] Configuración cargada y **Probar conexión** en verde
- [ ] **Cargar chequeras** funcionando y chequera asignada a ese usuario
- [ ] Acceso a la planilla DM
- [ ] Este manual entregado, con foco en: filas amarillas, signos, `Ch dd/mm`, pantalla previa
- [ ] Primera tanda hecha **acompañada**, con una prueba de 1 solo proveedor

---

## Anexo B — Glosario

| Término | Significado |
|---|---|
| **DM** | La planilla Excel autorizada de pagos. La hoja debe llamarse `DM` |
| **OP** | Orden de Pago: el comprobante que la app crea en Finnegans |
| **Chequera / Talonario** | Rango de números de cheque disponibles |
| **ÚLTIMO Nº** | Último cheque ya emitido; la app sigue desde el siguiente |
| **Crédito / saldo a favor** | Importe positivo en el Excel (PAGO, NC, MOVFONDOS positivo) que descuenta del total |
| **Carga manual** | Proveedor que la app no envía: hay que cargarlo a mano en Finnegans |
| **Cuenta corriente (CtaCte)** | Los documentos que la OP cancela |
| **ISAR** | Base imponible de la retención de Ganancias |
| **Fraccionar** | Dividir el importe en varios cheques según las fechas de la forma de pago |
