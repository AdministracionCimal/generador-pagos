# Reglas del proyecto — Generador de Pagos

## TOKEN SAVING

### No programar sin contexto
ANTES de escribir codigo: lee los archivos relevantes, revisa git log, entiende la arquitectura. Si no tienes contexto suficiente, pregunta. No asumas.

### No reescribir archivos completos
Usa Edit (reemplazo parcial), NUNCA Write para archivos existentes salvo que el cambio sea >80% del archivo. Cambia solo lo necesario. No "limpies" codigo alrededor del cambio.

### Validar antes de declarar hecho
Despues de un cambio: compila, corre tests, o verifica que funciona. Nunca digas "listo" sin evidencia de que funciona.

### Cero charla aduladora
No digas "Excelente pregunta", "Gran idea", "Perfecto", etc. No halagues al usuario. Ve directo al trabajo.

### Paralelizar tool calls
Si necesitas leer 3 archivos independientes, lee los 3 en un solo mensaje, no uno por uno.

### No duplicar codigo en la respuesta
Si ya editaste un archivo, no copies el resultado en tu respuesta. El usuario lo ve en el diff. Si creaste un archivo, no lo muestres entero en texto tambien.

### No usar Agent cuando Grep/Read basta
Agent duplica todo el contexto en un subproceso. Solo usalo para busquedas amplias o tareas complejas. Para buscar una funcion o archivo especifico, usa Grep o Glob directo.
