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
15. [Anexo C — Denominaciones que acepta la app](#anexo-c--denominaciones-que-acepta-la-app)

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

### 2.3 Actualizaciones (se hacen desde la app)

Al abrir, la app verifica sola si hay una versión nueva. Si hay, muestra un cartel con la
versión disponible y un botón **Sí** para actualizar en el momento:

1. Descarga el archivo nuevo y **verifica que sea el del release** (comparación de huella
   sha256). Si no coincide, no toca nada.
2. Guarda tu versión actual al lado del programa, agregándole `.anterior` al nombre (si el
   programa se llama `Generador De Pagos.exe`, la copia queda como
   `Generador De Pagos.anterior.exe`), por si hiciera falta volver.
3. Cierra la app y la vuelve a abrir con la versión nueva.

No hay que entrar al repositorio, ni bajar nada del navegador, ni aceptar SmartScreen otra vez
(el archivo descargado por la app no queda marcado como "bajado de internet").

También se puede buscar a mano en **Ayuda → Buscar actualizaciones**, y ahí mismo, en
**Ayuda → Acerca de**, ver qué versión tenés. La versión aparece además en el título de la
ventana y en la pantalla de Configuración — es el dato que hay que informar cuando algo falla.

Si en el momento no te conviene actualizar, elegí **No**: la app sigue funcionando y vuelve a
avisar en el próximo arranque.

> **Excepción, una sola vez:** si tu `.exe` es anterior a la versión 1.0.0, no tiene el
> mecanismo de actualización. Hay que bajarlo del link una última vez (sección 2.1); de ahí en
> adelante se actualiza solo.

### 2.4 Primer arranque

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
| CUENTAS CONTABLES | Endosos (valores en cartera) | `01.01.01.03.0001` | Cuenta donde están los cheques de terceros que se endosan |
| OPERACIONES BANCARIAS | Cheques propios | `EMCHPROP` | Tipo de operación bancaria del cheque |
| OPERACIONES BANCARIAS | Transferencias | `TLote` | Tipo de operación bancaria de la transferencia |
| OPERACIONES BANCARIAS | Endosos | `CHENDOSADOS` | Tipo de operación bancaria del endoso |

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
  ppal*), la app toma **la de más a la izquierda** y lo avisa al cargar, diciendo cuál usó.
  Verificá que sea la correcta.
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
  Excel. Un amarillo de *Colores del tema* o un amarillo “parecido” (mostaza, dorado, amarillo
  claro) **no se procesa**.
- Si eso pasa, la app **avisa al cargar el archivo** indicando el número de fila: *“N fila(s)
  con datos completos están pintadas de un color que NO es el amarillo estándar (fila 12, 15)
  y por eso NO se procesaron”*. Repintá esas filas y volvé a cargar.
- Si aparecen menos proveedores de los esperados y **no** hubo aviso, la causa es otra:
  revisá que la fila tenga Documento, Proveedor e Importe distinto de cero.

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

La app corrige sola las diferencias de espaciado y mayúsculas (`fc-21562` se interpreta como
`FC - 21562`), pero **no** puede adivinar un número mal tipeado ni un prefijo distinto. Lo más
seguro sigue siendo **copiar y pegar desde Finnegans, no tipear a mano**: si el número no
coincide con ningún documento con saldo, el proveedor se va a quitar de la lista (con aviso).

Los documentos que empiezan con **`OP`** se descartan siempre (ya son órdenes de pago
procesadas).

### 4.6 La columna Forma de pago

Define **la modalidad** y **cuántos cheques** se emiten. No lo define el tipo de documento:
un MOVFONDOS también puede pagarse en 3 cheques.

**Para cheque** hace falta la palabra **y** el número:

| Lo que se escribe | Resultado |
|---|---|
| `Ch 15/05` | 1 cheque al 15/05 |
| `Ch 08/06 - 09/06 - 18/06` | 3 cheques, uno por fecha, importe dividido en partes iguales (el último absorbe los centavos) |
| `ch15/05`, `Ch. 15/05`, `CHQ 15/05` | Igual que `Ch 15/05` |
| `Cheque 15/05`, `cheques 15/05`, `Cheque diferido 15/05` | Igual: la palabra completa también se reconoce |

**Para transferencia** alcanza con que la palabra esté (aunque haya otras):

| Lo que se escribe | Resultado |
|---|---|
| `transferencia` | 1 transferencia por el neto |
| `transf`, `transf.`, `transferencia interbancaria` | Igual que transferencia |
| `transferencia bancaria`, `Transferencia inmediata`, `transf bancaria` | Igual que transferencia |
| `tranferencia`, `transferensia`, `trnasferencia` | Se acepta como transferencia y **avisa del error de tipeo** |

**Pagos combinados** (varios medios para un mismo proveedor): se escriben en la misma celda,
separados por `+`. Se puede indicar qué porcentaje va por cada medio.

| Lo que se escribe | Qué hace |
|---|---|
| `Ch 10/09 + transferencia 30%` | 30% por transferencia y el resto en un cheque al 10/09 |
| `Ch 10/09 - 20/09 70% + transferencia 30%` | 30% por transferencia y el 70% repartido en 2 cheques |
| `Endoso 11139918 + Ch 10/09` | Se entrega ese cheque de cartera y el resto va en un cheque propio |
| `Endoso 11139918 - 03744630 + transferencia` | Dos cheques endosados y el resto por transferencia |
| `Endoso 11139918` | Sólo el endoso: **el cheque tiene que cubrir exactamente el total** |

Cómo se reparte: primero los **endosos**, que van por el importe exacto del cheque (no se puede
fraccionar ni modificar); después los tramos con **porcentaje**; y el tramo **sin** porcentaje se
queda con el resto. **Las retenciones se descuentan de la transferencia** (o del cheque propio si
no hay transferencia), nunca del endoso.

Ejemplo con números: una factura de $1.000.000 con $50.000 de retención y
`Ch 10/09 + transferencia 30%` → transferencia de **$250.000** (el 30% menos la retención) y un
cheque al 10/09 por **$700.000**.

**Los números de cheque a endosar** se pueden escribir con o sin los ceros de la izquierda
(`00017` o `17`), y sirve tanto el número del cheque como el número electrónico. La app verifica
contra la cartera de Finnegans que el cheque exista, que sea de la empresa que paga y que esté
en cartera. Un cheque endosado **puede tener vencimiento anterior a la fecha del pago**: eso es
normal y no genera alerta.

**Reglas de los pagos combinados:**

- Todos los ítems del mismo proveedor tienen que indicar **la misma** combinación (el reparto se
  hace sobre el total del proveedor).
- Si hay dos tramos sin porcentaje, no se sabe cómo repartir → Carga manual.
- Si todos los tramos llevan porcentaje, tienen que sumar 100%.
- Si un endoso **no cierra exacto** —queda saldo a favor o en contra— el proveedor va a **Carga
  manual** indicando la diferencia. Esos casos se cargan a mano en Finnegans, porque al cambiar
  el importe de la cuenta corriente el sistema recalcula las retenciones.

**Lo que queda en Carga manual (a propósito):**

| Texto | Por qué |
|---|---|
| `Cheque`, `Ch` (sin número ni fecha) | No hay con qué armar el vencimiento |
| `cheque o transferencia` | Ambiguo: la app **no adivina** entre una cosa y la otra |
| `echeq 15/05`, `e-cheq 15/05` | Es otro instrumento; la app emite cheques físicos numerados de una chequera |
| `trans` | Demasiado corto para asumir que quisiste decir transferencia |
| `efectivo`, `mercado pago`, `tarjeta` | La app no los soporta |
| `chequera 12` | No es una forma de pago |
| Vacío | Sin dato |

**Ojo con las fechas inexistentes:**

| Texto | Qué pasa |
|---|---|
| `Ch 31/02 - 10/06` | ⚠️ El 31/02 no existe. Igual salen **2 cheques**: el de la fecha mal escrita queda con fecha provisoria, marcado en naranja en la pantalla previa, y **la app no deja enviar hasta que le pongas la fecha correcta** |

**Las fechas se escriben `dd/mm` sin año.** La app asume el año en curso y, si la fecha ya
pasó, asume el año siguiente. De ahí el riesgo: hoy 03/08/2026, escribir `Ch 08/05` genera un
cheque al **08/05/2027**. Un error de tipeo en el día puede mandar el cheque casi un año
hacia adelante. Por eso existe la alerta naranja en la pantalla previa — **hay que mirarla**.

> La lista completa de todo lo que se puede escribir —y de lo que no— está en el
> **Anexo C**, que se puede imprimir por separado para acordar un estándar.

**Ojo con la diferencia entre mezclar en la misma celda y mezclar entre filas:**

- ✅ **En la misma celda** está soportado, y es el pago combinado que se explicó arriba:
  `Ch 10/06 + transferencia 30%`.
- ❌ **Entre filas distintas del mismo proveedor** no: si una fila dice `Ch 10/06` y otra dice
  `transferencia`, el proveedor queda en **Carga manual** con el motivo “Modalidad mixta”.

El motivo es que el reparto se hace sobre el **total del proveedor**, así que todas sus filas
tienen que indicar la misma combinación. Si de verdad necesitás pagar una factura por
transferencia y otra por cheque, van en dos tandas separadas (o se carga a mano).

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
- En un **pago combinado**, primero se calcula cuánto le toca al tramo de cheque (el total menos
  los endosos y los porcentajes de los otros tramos) y recién eso se divide entre sus fechas.
- Al dividir, cada cheque se **trunca** al centavo y el último se queda con el resto, igual que
  lo hace Finnegans: por ejemplo $11.089.819,72 en 8 cheques da siete de $1.386.227,46 y uno
  de $1.386.227,50.
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
2. Si encontró algo raro en el **archivo**, muestra **“Avisos al cargar el Excel”**: filas
   pintadas con un amarillo que no corresponde, fechas inexistentes, errores de tipeo en
   “transferencia”, columnas de importe duplicadas. Conviene leerlo y corregir el Excel antes
   de seguir.
3. Muestra un cartel de **“Verificando saldos”** mientras consulta a Finnegans qué documentos
   siguen con saldo pendiente. Es bloqueante a propósito: no se puede procesar hasta que termine.
4. **Elimina automáticamente** los proveedores cuyos documentos ya no tienen saldo (ya
   pagados) y muestra la lista en un cartel, con la pista de revisar el formato de la columna
   Documento si alguno no debería haberse quitado.

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
2. **Último número de cheque distinto** → el número del sistema no coincide con el del campo
   ÚLTIMO Nº; hay que elegir con cuál emitir.
3. **Chequera insuficiente** → elegir otra chequera para los proveedores que no entraron, o
   omitirlos.
4. **Proveedores omitidos** → lista de lo que quedó afuera y por qué (CUIT inválido, sin
   saldo, importe cero, sin chequera).

### Paso 5 — Verificación previa (la pantalla más importante)

Muestra, por proveedor: los ítems que se cancelan, cómo se paga, las retenciones calculadas, y
arriba los totales **ÓRDENES / BRUTO / RETENCIONES / NETO A PAGAR**.

En los pagos combinados aparece **una tabla por medio de pago**: los cheques endosados (con su
banco y vencimiento), los cheques propios (con la fecha editable) y la transferencia. La etiqueta
del proveedor dice qué medios lleva, por ejemplo *"Endoso + cheque propio + transferencia"*.

**Qué controlar acá:**

- El **neto a pagar** de cada proveedor contra lo autorizado.
- La cantidad de cheques y sus **fechas de vencimiento**.
- Que las retenciones aparezcan donde corresponde.

**Cheques con la fecha en alerta:** las filas pintadas de **naranja** son cheques que la app
**no va a enviar** así como están. Hay cuatro motivos:

| Motivo | Por qué | Cómo se resuelve |
|---|---|---|
| La fecha del Excel no existe (`31/02`) | Nadie eligió el vencimiento: la app puso una provisoria | Hay que **corregir la fecha** |
| Fecha anterior a hoy | El banco no la acepta | Hay que **corregir la fecha** |
| Fecha de hoy | El banco sólo acepta cheques diferidos | Hay que **corregir la fecha** |
| Fecha a más de 180 días | Suele ser un error de tipeo que corrió el año | Se corrige **o se confirma** con el check (ver abajo) |

Arriba aparece un cartel con el total de cheques en alerta, y **el botón “Confirmar y enviar”
queda deshabilitado** mientras quede una sola sin resolver.

**Cheques a más de 180 días que son correctos:** cuando hay alguno, en el cartel naranja
aparece el check *“Confirmo que los cheques a más de 180 días están bien y se envían con esa
fecha”*. Tildándolo se habilita el envío, y el motivo de la alerta te dice a cuántos días está
cada uno (ej. *“fecha a 240 días”*) para que puedas distinguir un plazo real de un error de
tipeo. El cartel queda visible mientras el check esté tildado, y se puede destildar para
volver a revisarlos.

Ese check **sólo levanta la alerta de plazo largo**. Una fecha inexistente, vencida o de hoy no
se puede confirmar: hay que corregirla.

La columna **Vencimiento es editable**: se hace clic, se corrige la fecha (o se usa el
calendario) y el cambio **se manda así al sistema**. El cartel y el botón se actualizan en el
momento: cuando no queda ninguna fila naranja, se habilita el envío. La rueda del mouse no
modifica las fechas, así que no hay riesgo de cambiarlas sin querer.

Botones: **Confirmar y enviar** manda las OPs (sólo si no hay alertas). **Cancelar** vuelve a
la pantalla principal sin registrar nada.

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
- Si **alguna falló**: la app deja en la lista **sólo los pagos que no se confirmaron** (saca
  los que salieron OK) y vuelve a verificar los saldos en el próximo intento. Ver sección 10.1.

---

## 7. Estados de la tabla

| Estado | Color | Significa | Qué hacer |
|---|---|---|---|
| **Listo** | Verde | Se va a enviar | Nada |
| **Carga manual** | Amarillo | Modalidad no soportada, mixta, mal escrita, sin ítems facturables, o un endoso que no cierra exacto | Corregir el Excel y recargar, o pagarlo a mano en Finnegans. El motivo exacto se ve en la pantalla de resultados |
| **Excede chequera** | Rojo | Los cheques no entran en el rango de la chequera, o ÚLTIMO Nº / LÍMITE están vacíos o no son números | Completar los números, o preparar una segunda chequera |
| **Sin ítems** | Rojo | El proveedor quedó sin filas válidas | Revisar el Excel |
| **Sin saldo** | Gris | Los documentos ya no tienen saldo pendiente en Finnegans | Verificar si ya se pagó; si no, revisar el formato de la columna Documento |

---

## 8. Avisos y diálogos que pueden aparecer

| Cartel | Cuándo | Qué hacer |
|---|---|---|
| **Avisos al cargar el Excel** | Filas con un amarillo no estándar, fechas inexistentes, “transferencia” mal escrita, dos columnas de importe | Leer cada línea: dice el número de fila o el texto exacto a corregir. Las filas mal pintadas **no se procesaron** |
| **Proveedores sin saldo pendiente** | Sus documentos ya no figuran con saldo en Finnegans | Si alguno tendría que pagarse, revisar el formato de la columna Documento |
| **No se pudo leer el Excel** | Hoja `DM` inexistente, columnas faltantes, archivo `.xls`, archivo corrupto | Ver el detalle del mensaje y la sección 4 |
| **Sin configuración / Configuración incompleta** | Falta URL, Client ID o Secret | Archivo → Configuración |
| **Chequera** (“Ingresá el último número…”) | ÚLTIMO Nº vacío o no numérico | Completar el campo |
| **Cotización del dólar no disponible** | Finnegans no devolvió cotización | Se puede continuar con $1. Afecta el dato de cotización de la OP |
| **Chequera insuficiente** | Faltan números en la chequera | Asignar otra chequera u omitir esos proveedores |
| **Sin chequeras disponibles** | No hay otra chequera cargada | Cargar chequeras y volver a intentar |
| **Proveedores omitidos** | CUIT inválido, sin saldo, importe cero | Revisar cada caso; esos pagos **no se enviaron** |
| **Nada que procesar** | Ningún pago quedó en estado Listo | Revisar estados en la tabla |
| **Último número de cheque distinto** | Finnegans informa otro último cheque emitido que el del campo ÚLTIMO Nº | **Sí** = emitir desde el número de Finnegans (elegir esto si otra persona usó la chequera). **No** = seguir con el de la app (correcto si se saltearon cheques anulados a propósito). **Cancelar** = revisar antes de procesar |
| **Cheques con la fecha en alerta** (banner naranja) | Fecha del Excel inexistente, cheque a hoy o antes, o a más de 180 días | Corregir la fecha en la columna Vencimiento (o tildar el check si el plazo largo es correcto). Hasta que no quede ninguna, el botón de enviar está deshabilitado |
| **Hay cheques con la fecha en alerta** (cartel rojo, “No se envió nada”) | Se intentó enviar con alertas pendientes | Es la segunda barrera de la app: lista proveedor, número de cheque y motivo. Volver a Procesar y corregir en la pantalla previa |
| **No se pudo cargar chequeras** | Sin conexión o credenciales inválidas | Probar conexión en Configuración |
| **⚠ *proveedor*: no se pudo cargar histórico de retenciones** | Falló la consulta del mes | **Atención:** la retención puede quedar calculada de menos. Verificar antes de confirmar |

---

## 9. Errores frecuentes y cómo resolverlos

### 9.1 Al cargar el Excel

| Síntoma | Causa | Solución |
|---|---|---|
| “No se encontró la hoja «DM»” | La hoja tiene otro nombre | Renombrar la hoja a `DM` |
| “Faltan columnas requeridas” | Encabezado distinto, o los encabezados no están en la fila 1 | El mensaje lista los encabezados que leyó en la fila 1: comparar con la tabla de la sección 4.2 |
| Carga 0 proveedores **con aviso** de color | Las filas no están en el amarillo estándar | Repintar con el amarillo de *Colores estándar* |
| Carga 0 proveedores **sin ningún aviso** | Ninguna fila está pintada, o les falta Documento/Proveedor/Importe | Pintar las filas a pagar y completar los datos |
| Faltan proveedores que sí están pintados | Documento, Proveedor vacíos o Importe = 0 | Completar la fila |
| No se puede abrir el archivo | Es `.xls` | Guardar como `.xlsx` |
| Importes en cero o vacíos | La celda tiene una fórmula sin valor calculado (archivo generado por un sistema, nunca abierto en Excel) | Abrir en Excel, guardar y volver a cargar |

### 9.2 Modalidad y cheques

| Síntoma | Causa | Solución |
|---|---|---|
| Un proveedor quedó en Carga manual sin motivo aparente | Texto de forma de pago no reconocido. Los casos y el por qué están en la sección 4.6 | El estado en la pantalla de resultados muestra el texto exacto que no se pudo interpretar |
| “Modalidad mixta” | Dos filas del mismo proveedor indican formas de pago distintas | Poner la misma combinación en todas sus filas (se pueden combinar medios en la misma celda), o partir en dos tandas |
| “los cheques a endosar suman $X y el neto a pagar es $Y” | El endoso no cierra exacto | Elegir otra combinación de cheques, agregar un tramo por la diferencia, o cargarlo a mano |
| “no se encontró en cartera el cheque N” | El número no existe, no es de esta empresa o ya no está en cartera | Verificar el número contra Finnegans |
| Salen menos cheques de los esperados | Falta alguna fecha en la columna Forma de pago | Revisar el texto: cada `dd/mm` genera un cheque |
| Un cheque aparece en naranja diciendo que la fecha no existe | El Excel tenía `31/02` o similar | Poner la fecha correcta en la columna Vencimiento (el cheque no se pierde) |
| Un cheque quedó con fecha de hoy | La forma de pago no traía fechas y se usó la fecha de respaldo | Corregir la fecha en la pantalla previa |
| Un cheque salió al año que viene | Fecha `dd/mm` ya pasada: la app asume el año siguiente | Corregirla en la pantalla previa (banner naranja) |
| No se puede apretar “Confirmar y enviar” | Queda al menos un cheque en naranja | Corregir las fechas en alerta (o tildar el check de los +180 días); el botón se habilita solo |
| Los números de cheque no coinciden con la chequera física | ÚLTIMO Nº desactualizado | Corregir el campo antes de procesar |

### 9.3 Errores de Finnegans al enviar

| Mensaje | Causa | Solución |
|---|---|---|
| `HTTP 401` / *Token request failed* | Credenciales vencidas o mal cargadas | Probar conexión en Configuración |
| *El usuario sólo tiene permisos de consulta sobre esta empresa* | El usuario de la API no tiene alta habilitada, o la empresa seleccionada no es la correcta | Pedir permisos de alta a Sistemas; verificar la Empresa en Configuración |
| `HTTP 500 … No se permiten importes negativos` | Composición de importes inconsistente (caso conocido y corregido) | Revisar signos en el Excel; si persiste, reportar con el log de auditoría |
| `HTTP 500` genérico de contabilidad | Cuenta contable, talonario u operación bancaria mal configurados | Revisar Configuración con contabilidad |
| `SIN CONFIRMACION: se corto la conexion al enviar…` | Timeout o caída de red durante el envío | La OP **puede haber quedado creada**. Buscarla en Finnegans: si está, eliminar esa fila de la tabla; si no está, reintentar |

> **Importante con los timeouts:** cuando se corta la conexión justo después de enviar, la app
> no puede saber si la OP se registró. Por eso marca ese pago con **SIN CONFIRMACIÓN** en lugar
> de un error común: es el único caso en el que hay que ir a mirar el sistema antes de
> reintentar.

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

### 10.1 Reintento después de un error parcial

Si de 10 OPs 8 salieron OK y 2 fallaron, la app **saca solas de la lista las 8 confirmadas** y
deja únicamente las 2 que hay que reintentar (lo avisa en la barra de estado). Además descarta
la verificación de saldos anterior, así que el próximo *Procesar pagos* vuelve a consultar a
Finnegans desde cero. **No hay que borrar filas a mano.**

Lo único que requiere criterio humano es el caso **SIN CONFIRMACIÓN**: cuando se corta la
conexión al enviar, la app no sabe si la OP quedó creada, así que la deja en la lista y lo dice
en el detalle del resultado. En ese caso, **antes de reintentar hay que buscar el pago en
Finnegans**: si ya está, eliminá esa fila de la tabla; si no está, reintentá normalmente.

### 10.2 Dos personas usando la app al mismo tiempo

La numeración de **cheques** la controla la app a partir del ÚLTIMO Nº (la de la **OP** la
controla Finnegans y no tiene este problema). Si dos usuarios trabajan con la misma chequera,
podrían emitir cheques con el mismo número.

Antes de armar los pagos, la app le pregunta a Finnegans cuál es el último cheque emitido y,
si no coincide con el campo ÚLTIMO Nº, **muestra los dos números y pide decidir** (usar el de
Finnegans, seguir con el de la app, o cancelar). Ver el detalle en la sección 8.

Eso detecta el problema, pero no lo evita: **la regla sigue siendo una persona por chequera y
por tanda**. Si hay varios usuarios, asignar una chequera distinta a cada uno.

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
- No hace **pagos parciales**: los tramos tienen que cubrir el total exacto de lo que dice la
  planilla. Si querés pagar una parte, poné el importe parcial en la columna Importe.
- No genera **saldo a favor** con un endoso que sobra: eso va a Carga manual.
- No elige los cheques a endosar: hay que indicar los números en la planilla.

---

## 11. Dónde guarda sus datos la app

Todo queda en el perfil del usuario de Windows, en `%APPDATA%\GeneradorDePagos\`
(atajo: pegar esa ruta en el Explorador):

| Archivo | Contenido |
|---|---|
| `config.enc` | Configuración cifrada (incluye las credenciales) |
| `key.bin` | Clave de cifrado de la configuración |
| `audit_log.jsonl` | Registro de lo enviado y lo respondido por Finnegans (los tokens se enmascaran) |

Y en la carpeta donde está el `.exe`, después de la primera actualización:

| Archivo | Contenido |
|---|---|
| El programa con `.anterior` en el nombre (ej. `Generador De Pagos.anterior.exe`) | La versión que había antes de actualizar. Se puede borrar; sirve para volver atrás si la nueva diera problemas |

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

**Tengo que emitir un cheque a más de 180 días de verdad, ¿qué hago?**
Se puede: en la pantalla previa, tildá el check *“Confirmo que los cheques a más de 180 días
están bien”* del cartel naranja y se habilita el envío. Fijate primero en el motivo de la
alerta, que dice a cuántos días quedó cada cheque.

**¿Cómo sé qué cheques tengo en cartera para endosar?**
La app **no los lista**: hay que mirarlos en Finnegans (Situación de cheques, tipo terceros,
estado En Cartera) y escribir los números en la planilla. Al procesar, la app verifica contra
Finnegans que existan, que sean de la empresa que paga y que sigan en cartera; si no, el
proveedor va a Carga manual con el detalle.

**¿Puedo endosar un cheque que ya venció?**
Sí. A diferencia de un cheque propio, acá no se emite nada: se entrega un valor que ya existe,
así que un vencimiento anterior a la fecha del pago no genera alerta.

**¿Por qué un proveedor no tiene retención?**
Porque no tiene la retención configurada en Finnegans, porque no hay facturas `FC - ` en la
tanda, o porque la base no supera el mínimo imponible.

**¿Por qué desapareció un proveedor de la lista?**
Porque sus documentos no figuran con saldo pendiente en Finnegans. La app te lo dice en un
cartel al terminar de verificar saldos. Si estás seguro de que se debe, revisá que el número
de la columna Documento sea el correcto (sección 4.5).

**¿Cómo sé qué versión tengo?**
Está en el título de la ventana, en **Ayuda → Acerca de** y en la pantalla de Configuración. Es
el dato que hay que pasar cuando se reporta un problema.

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

Ya está automatizado: cada `push` a `master` dispara GitHub Actions, que corre los tests,
estampa en el binario la versión y el commit, compila en Windows y reemplaza el `.exe` del
release `latest`. El link de descarga nunca cambia, y **los usuarios reciben el aviso dentro de
la app** en el siguiente arranque.

El número de versión se sube a mano en `src/version.py` (`VERSION = "1.0.0"`) cuando el cambio
lo justifica; el commit y la fecha los pone el CI. La app compara **por commit**, no por fecha:
el CI publica el binario un par de minutos después de compilarlo, así que comparar fechas haría
que avise de una "versión nueva" que es la que el usuario ya tiene.

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
| **Sin firma digital** | Advertencia de SmartScreen la primera vez en cada PC nueva y posibles falsos positivos de antivirus. Se resuelve comprando un certificado de firma de código. Las **actualizaciones** posteriores no tienen este problema: las descarga la app, no el navegador |
| **La actualización necesita permiso de escritura** | La app se reemplaza a sí misma en su carpeta. Si está en `Program Files` sin permisos, avisa y hay que reemplazarla a mano. Por eso conviene una carpeta propia del usuario, ej. `C:\GeneradorDePagos\` |
| **Salto desde versiones anteriores a 1.0.0** | Los `.exe` viejos no tienen el mecanismo de actualización: hay que bajar el nuevo una última vez |
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
- [ ] Explicado que las actualizaciones salen del cartel al abrir la app, no del navegador
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
| **Endoso** | Entregar al proveedor un cheque de un tercero que teníamos en cartera, en lugar de emitir uno propio |
| **Cartera** | Los cheques de terceros que recibimos y todavía no depositamos ni endosamos |
| **Pago combinado** | Un pago que usa varios medios a la vez (endoso, cheque propio, transferencia) |
| **Tramo** | Cada medio de pago dentro de una «Forma de pago» combinada, separados por `+` |
| **Cuenta corriente (CtaCte)** | Los documentos que la OP cancela |
| **ISAR** | Base imponible de la retención de Ganancias |
| **Fraccionar** | Dividir el importe en varios cheques según las fechas de la forma de pago |

---

## Anexo C — Denominaciones que acepta la app

Referencia completa de lo que se puede escribir en la planilla. Está pensada para acordar un
estándar: la app tolera varias formas de escribir lo mismo, pero conviene elegir una y usarla
siempre. **Todo lo de estas tablas está verificado contra el código de la app**, no es una
descripción aproximada.

### C.1 Encabezados de columna (fila 1 de la hoja `DM`)

| Encabezado | Cómo se reconoce | Obligatorio |
|---|---|---|
| `Documento` | Exacto | Sí |
| `Proveedor` | Exacto | Sí |
| `Forma de pago` **o** `Pago` | Exacto (cualquiera de los dos) | Sí |
| `Importe` | Cualquier encabezado que **contenga** “importe” (ej. `Importe ppal`) | Sí |
| `CUIT` | Exacto | Recomendado |
| `Comprobante` | Exacto | Recomendado |
| `Fecha vto` | Cualquier encabezado que **contenga** “fecha vto” | Opcional |

Mayúsculas y tildes son indistintas. `Condición de pago` **no** se reconoce como forma de pago.

### C.2 Cheque propio

| Se escribe | Resultado |
|---|---|
| `Ch 15/05` | 1 cheque al 15/05 |
| `Ch 08/06 - 09/06 - 18/06` | 3 cheques, uno por fecha |
| `ch15/05` | Igual (sin espacio) |
| `Ch. 15/05` | Igual (con punto) |
| `CHQ 15/05` | Igual (abreviatura) |
| `Cheque 15/05` | Igual (palabra completa) |
| `cheques 15/05` | Igual (plural) |
| `Cheque diferido 15/05` | Igual (admite palabras intercaladas) |
| `Ch 30 dias` | 1 cheque, con la fecha de la columna `Fecha vto` |

Las fechas van **`dd/mm` sin año**: la app usa el año en curso, y si la fecha ya pasó asume el
año siguiente.

### C.3 Transferencia

| Se escribe | Resultado |
|---|---|
| `transferencia` | 1 transferencia por el neto |
| `Transferencia` / `TRANSFERENCIA` | Igual (mayúsculas indistintas) |
| `transf` / `transf.` | Igual |
| `transferencia interbancaria` | Igual |
| `transferencia bancaria` | Igual |
| `Transferencia inmediata` | Igual |
| `transf bancaria` | Igual |
| `tranferencia` / `transferensia` | Igual, y **avisa del error de ortografía** |

### C.4 Endoso de cheques de terceros

| Se escribe | Resultado |
|---|---|
| `Endoso 11139918` | Endosa ese cheque de cartera |
| `Endosos 11139918 - 03744630` | Endosa los dos |
| `End 11139918` | Igual (abreviatura) |
| `endoso` / `ENDOSO` | Igual (mayúsculas indistintas) |

El número se puede escribir **con o sin los ceros de la izquierda** (`00017` o `17`), y sirve
tanto el número del cheque como el número electrónico. **Un endoso solo tiene que cubrir el
total exacto**; si sobra o falta, el proveedor va a Carga manual con la diferencia.

### C.5 Combinaciones (varios medios en la misma celda, separados por `+`)

| Se escribe | Resultado |
|---|---|
| `Ch 10/09 + transferencia 30%` | 30% por transferencia, el resto en 1 cheque |
| `Ch 10/09 - 20/09 70% + transferencia 30%` | 30% por transferencia, el 70% en 2 cheques |
| `transferencia 33,5% + Ch 10/09` | Admite decimales con coma, y cualquier orden |
| `Ch 10/09 + transferencia 30 %` | Admite espacio antes del `%` |
| `Endoso 11139918 + Ch 10/09` | Endoso + 1 cheque por la diferencia |
| `Endoso 11139918 + transferencia` | Endoso + transferencia por la diferencia |
| `Endoso 11139918 - 03744630 + Ch 10/09` | Dos endosos + 1 cheque |

Reglas: **un solo tramo de cada tipo**; el tramo **sin** porcentaje se queda con el resto; si
todos llevan porcentaje deben **sumar 100%**; los endosos van por el nominal del cheque y la
retención se descuenta de la transferencia (o del cheque propio si no hay transferencia).

### C.6 Lo que NO se acepta, y qué dice la app

| Se escribe | Mensaje |
|---|---|
| `Cheque` / `Ch` (sin número ni fecha) | *no se reconoció ninguna forma de pago* |
| `chequera 12` | *no se reconoció ninguna forma de pago* |
| `echeq 15/05` / `e-cheq 15/05` | *no se reconoció ninguna forma de pago* (es otro instrumento) |
| `trans` | *no se reconoció ninguna forma de pago* (muy corto para asumir) |
| `efectivo` / `mercado pago` / `Tarjeta de Crédito` | *no se reconoció ninguna forma de pago* |
| `cheque o transferencia` | *no se reconoció ninguna forma de pago* (ambiguo: no se adivina) |
| `Ch 10/09 + transferencia` | *hay más de un tramo sin porcentaje: no se sabe cómo repartir el importe* |
| `Ch 10/09 60% + transferencia 30%` | *los porcentajes suman 90% en lugar de 100%* |
| `Ch 10/09 50% + Ch 20/10 50%` | *hay 2 tramos de cheque: escribí uno solo* |
| Celda vacía | Carga manual |

En todos estos casos el proveedor queda en **Carga manual** con ese texto como motivo: no se
envía nada y se ve en la pantalla de resultados.

### C.7 Estándar sugerido

La app acepta las variantes de arriba, pero si se usa **una sola forma** los avisos y las
revisiones son más rápidos. Propuesta:

| Caso | Forma sugerida |
|---|---|
| Cheque propio | `Ch dd/mm` — varias fechas separadas por ` - ` |
| Transferencia | `transferencia` (a secas) |
| Endoso | `Endoso <número>` — varios separados por ` - ` |
| Endoso + resto en cheque | `Endoso <número> + Ch dd/mm` |
| Parte transferencia, resto cheque | `Ch dd/mm + transferencia NN%` |

Y dos criterios que valen para cualquier estándar que se elija:

- **Todas las filas del mismo proveedor** tienen que decir lo mismo en Forma de pago.
- Los números de cheque a endosar se **copian de Finnegans**, no se tipean.
