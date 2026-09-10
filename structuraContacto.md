## Nota: tipos reales de columna en el tablero de prueba (Pruebas IA)

Esta tabla describe el diseño "de producción" pensado para el board de
Contacto (columnas tipadas: Texto, Correo, Teléfono, Fecha, Persona, Lista,
Relacionado, etc.). **El board real usado para desarrollo y pruebas —
"Contactos", id `18430360621`, workspace "Pruebas IA" (id `17441169`) — NO
tiene esos tipos.** Verificación empírica contra la API (Task 1 del plan de
tablero de cuentas, y creación de la columna `board_relation` en Tasks 4/5):

- **Todas** las columnas de este board son de tipo `text` simple, incluidas
  Correo, Teléfono, Fecha de inicio, Estado, Responsable y Nivel/Rol de
  cargo (ninguna es un "status" con labels, ni un date-picker, ni un
  people-picker real). `monday_crear_contacto` (`monday.py`) escribe
  siempre strings planos para estos campos — "Responsable" en particular
  escribe el ID numérico de Monday como texto plano (no resuelve a nombre)
  porque no hay people-picker real donde resolverlo; "Estado" tampoco tiene
  labels configurados del lado de Monday (`settings_str` vacío), así que
  nada valida que el string escrito coincida con uno de los 8 estados
  esperados — eso queda a cargo de este código (ver `ESTADOS_CONTACTO_EXITOSO`
  en `config.py`).
- La columna **"Cuenta asociada"** de esta tabla corresponde en el board
  real a **`board_relation_mm725nna`** ("Cuenta vinculada"), un
  `board_relation` real creado *después* del Task 1 para vincular
  Contactos → Cuentas. La columna de texto original equivalente, también
  llamada "Cuenta asociada" (`text_mm71b8fe`), quedó sin usar por este
  código — no confundir una con otra (comparten nombre visible en Monday
  pero son columnas distintas).

**Antes de apuntar este código a un board "real"/de producción con columnas
tipadas de verdad:** hay que re-verificar empíricamente los tipos de columna
de ese board — si son columnas tipadas de verdad (correo/teléfono/fecha/
persona/status reales), `monday_crear_contacto` va a fallar con
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
| **Cuenta asociada** | Cuenta o empresa a la que pertenece o se vincula el contacto. | Relacionado |
| **Nombre** | Nombre completo de la persona de contacto. | Texto |
| **Correo** | Dirección de correo electrónico del contacto. | Correo |
| **Teléfono** | Número telefónico del contacto para comunicación directa. | Teléfono |
| **Extensión** | Extensión telefónica interna del contacto, si aplica. | Numérico |
| **País** | País en el que se encuentra o atiende el contacto. | Ubicación |
| **Nivel de cargo** | Nivel jerárquico del contacto dentro de la organización. | Lista |
| **Nombre de cargo** | Puesto o rol específico que ocupa el contacto dentro de la organización. | Texto |
| **Link de LinkedIn** | URL del perfil profesional del contacto en LinkedIn. | URL |
| **Rol en la decisión** | Es el papel que tomará el contacto a la hora de tomar decisiones respecto a la vinculación. | Lista |
| **Estado** | Estatus actual del contacto para identificar si puede ser gestionado o requiere validación. | Lista |
| **Responsable** | Persona interna encargada de gestionar la relación con el contacto. | Persona |
| **Fecha de inicio** | Día, mes y año en el que se obtuvo el contacto. | Fecha |