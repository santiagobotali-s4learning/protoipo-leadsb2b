## Nota: tipos reales de columna en el tablero de prueba (Pruebas IA)

Esta tabla describe el diseño "de producción" pensado para el board de Cuentas
(columnas tipadas: Lista, Relacionado, Correo, Teléfono, Fecha, Persona, etc.).
**El board real usado para desarrollo y pruebas — "Cuentas", id `18430360623`,
workspace "Pruebas IA" (id `17441169`) — NO tiene esos tipos.** Verificación
empírica contra la API (Task 1 del plan de tablero de cuentas, y creación de
las dos columnas `board_relation` en Tasks 4/5):

- **Todas** las columnas de este board son de tipo `text` simple (incluidas
  Sector, Cantidad de empleados, Tamaño, E-Mail, Teléfono, Página web, País,
  Fecha de inicio) — no hay columnas de tipo Correo/Teléfono/Fecha/Lista
  reales. `monday_crear_cuenta` (`cuentas.py`) escribe siempre strings
  planos para estos campos, nunca el dict tipado que usaría la API de
  Monday para una columna "email"/"phone"/"date" real.
- La columna **"Convenios"** de esta tabla corresponde en el board real a
  **`board_relation_mm72x2xb`** ("Convenio vinculado"), un `board_relation`
  real creado *después* del Task 1 para vincular Cuentas → Convenios (board
  `18430363328`, también en "Pruebas IA"). La columna de texto original
  equivalente, "Convenio asociado" (`text_mm71gsya`), quedó sin usar por
  este código — no confundir una con otra.
- Ninguna otra columna de este board tiene un `board_relation` real; el
  resto de los campos "Relacionado"/"Lista"/"Check" de esta tabla (Grupo
  empresarial asociado, Oportunidades, Tipo, Categoría, Eventos,
  Empleabilidad, Académico, Relacionamiento y ventas, Plan ESG) siguen
  siendo `text` simple en el board real y no se usan desde este código.

**Antes de apuntar este código a un board "real"/de producción con columnas
tipadas de verdad:** hay que re-verificar empíricamente los tipos de columna
de ese board (no asumir que son iguales al de pruebas) — si son columnas
tipadas de verdad, `monday_crear_cuenta` va a fallar con
`ColumnValueException` igual que le pasaba en sentido inverso cuando este
código todavía asumía tipos que el board de pruebas no tenía (bug
encontrado y corregido en los Tasks 4/5). Muy probablemente haya que
revertir los campos afectados a los dicts tipados que pide la API de Monday
para esos tipos de columna.

Detalle completo de la verificación empírica original (IDs de columna,
respuestas crudas de la API, etc.): commits de los Tasks 1, 4 y 5 de
`docs/superpowers/specs/2026-09-09-tablero-cuentas-design.md` — el reporte
original de Task 1 vivía en un archivo de worktree no versionado y ya no
está disponible; lo esencial quedó resumido acá y en los comentarios de
`config.py`/`cuentas.py`/`monday.py`.

| Campo | Descripción | Tipo de campo |
| :--- | :--- | :--- |
| **Nombre de la alianza** | Es el nombre de la alianza | Texto largo |
| **¿Pertenece a algún grupo empresarial?** | Indica si la cuenta forma parte de un grupo empresarial. | Lista |
| **Grupo empresarial asociado** | Grupo empresarial al que pertenece la cuenta. | Relacionado |
| **Tipo** | Se especifica si es una empresa pública o privada. | Lista |
| **Eventos** | Se selecciona de manera manual si la cuenta nos ofrece eventos | Check |
| **Empleabilidad** | Se selecciona de manera manual si la cuenta nos ofrece empleabilidad | Check |
| **Académico** | Se selecciona de manera manual si la cuenta nos ofrece beneficios académicos | Check |
| **Relacionamiento y ventas** | Se selecciona de manera manual si la cuenta nos ofrece relacionamiento y ventas | Check |
| **Categoría** | Aquí se coloca el nivel en el que se tiene a la empresa (Oro, plata, bronce) | Lista |
| **Sector** | Se coloca el ámbito en el que se desarrolla la empresa | Lista |
| **Cantidad de empleados** | Número aproximado de colaboradores de la organización, usado para dimensionar el potencial de la cuenta. | Numérico |
| **Tamaño** | Se especifica si se trata de una micro, pequeña, mediana o grande empresa | Lista |
| **Descripción** | Breve resumen de la cuenta: giro, relación con la institución, contexto comercial y datos relevantes. | Texto largo |
| **E-Mail** | Debe ser de la empresa (Si existe) | Correo |
| **Teléfono** | Número telefónico principal de la organización o empresa, preferentemente corporativo. | Teléfono |
| **Página web** | URL del sitio oficial de la organización para consulta y validación de información pública. | Enlace |
| **País** | Se coloca el país de donde se encuentra la organización | Ubicación |
| **Responsable** | Es la persona que está a cargo de la cuenta dentro de Utel, las cuentas no deben tener responsables, el campo se deja únicamente si se requiere para un caso especial. | Persona |
| **Fecha de inicio** | Día mes y año en el que se creó la cuenta | Fecha |
| **Convenios** | Relación con los convenios registrados o vigentes asociados a la cuenta. | Relacionado |
| **Oportunidades** | Relación con las oportunidades comerciales generadas para la cuenta. | Relacionado |
| **Plan ESG** | Archivo o evidencia relacionada con el plan ESG, responsabilidad social o sostenibilidad de la organización. | Lista |
| **Documento ESG** | Se debe integrar el archivo del plan | Adjunto |