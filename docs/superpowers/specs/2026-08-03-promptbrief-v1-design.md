# PromptBrief v1 — Diseño

**Fecha:** 2026-08-03
**Estado:** propuesta, pendiente de revisión
**Autor:** Franco Leone (con Claude)

---

## 1. Qué es y por qué existe

PromptBrief convierte una descripción informal de lo que querés hacer en un *brief* estructurado, listo para pegar en un agente de codificación (Claude Code y similares).

El problema que ataca no es que la gente escriba mal los prompts. Es que **escribe prompts sin contexto**: el proyecto, sus convenciones, qué no hay que tocar y cuándo la tarea está terminada viven en la cabeza de quien pregunta, no en el mensaje. La herramienta cierra ese hueco leyendo el contexto que ya existe en el repo (`CLAUDE.md`, `AGENTS.md`, `README.md`) y pidiendo únicamente lo que falta.

### Objetivos

1. Uso diario real del autor, no una demo.
2. Pieza de portfolio que demuestre Python y Angular con tests y CI.
3. Base reutilizable para un hook de Claude Code (v2).

### No-objetivos

Ser un producto, tener usuarios además del autor, o competir con las herramientas comerciales de la sección 2.

---

## 2. Prior art y diferenciación

| Proyecto | Qué hace | Solapamiento |
|---|---|---|
| `prompt-control-plane` (npm) | Linter de prompts con IDs de regla estables, scoring en 5 dimensiones, blocking questions, GitHub Action | **Alto** en la parte de linting |
| `RequirementLinter` | Revisa user stories con IA: criterios de aceptación faltantes, términos vagos | Medio, otro dominio |
| `spectralint` | Análisis estático de archivos de instrucciones de agentes (referencias muertas, deriva de nombres) | Bajo, analiza los `.md`, no los prompts |
| `awesome-goal-prompts` | Plantillas con `GOAL / CONTEXT / CONSTRAINTS / DONE WHEN / VERIFY / OUTPUT` | Valida la estructura de salida elegida |

**La categoría existe.** El README no debe afirmar novedad.

**La diferencia real:** todas las herramientas de arriba analizan el **texto del prompt en aislamiento**. Ninguna lee el proyecto. PromptBrief hace *context engineering*, no solo *prompt engineering*: destila el contexto del repo y lo inyecta de forma selectiva según el tipo de tarea.

> Los linters de prompts revisan **cómo** escribís. PromptBrief sabe **sobre qué** escribís.

Diferencias secundarias: local-first sin cuotas ni tiers, y sin llamadas a IA en la v1.

---

## 3. Decisiones tomadas

Estas cuatro se decidieron por recomendación, no por preferencia expresa del autor. **Revisar antes de implementar.**

| # | Decisión | Alternativa descartada | Motivo |
|---|---|---|---|
| D1 | **Destino: agente.** El brief lleva rutas de archivo, no contenido pegado | Chat común (pegar contenido) | Es el flujo diario del autor. Además es la estrategia *just in time* que documenta Anthropic: mantener identificadores livianos y dejar que el agente cargue lo que necesite. Pegar contenido gasta presupuesto de atención sin necesidad |
| D2 | **El andamiaje del brief es inglés; el contenido pasa verbatim.** Interfaz y mensajes de reglas en español | "Todo el brief en inglés" | Ver la nota de abajo |
| D3 | **v1 sin IA.** 100% determinística | Pasada opcional de refinamiento | Sin API keys, sin costos, sin cuentas. Todo testeable con `pytest`. El demo público no se puede drenar. La pasada de IA queda para v1.1 |
| D4 | **Tres tipos de tarea:** `code_change`, `debug`, `writing` | Seis tipos | Los tres que el autor usa a diario. Ver la nota sobre extensibilidad |

**Nota sobre D2** (corregida el 2026-08-03 tras la auditoría). La versión original decía "el brief sale en inglés", y eso era **imposible de cumplir sin traducción automática**, que la v1 no tiene: el texto lo escribe el usuario en español y los bullets salen de `.md` que pueden estar en cualquier idioma. Forzar plantillas en inglés sobre contenido español producía Spanglish real — la auditoría encontró este slot generado:

> `"Do the work without adding dependencias de runtime nuevas."`

Lo que efectivamente se cumple, y es lo que vale: **los nombres de tag y la estructura del brief son inglés y estables** (`<project_context>`, `<constraints>`, `<task>`, `<success_criteria>`). El contenido del usuario y del repo pasa sin tocar. Las reformulaciones de negativo a positivo (F3) se hacen **en el idioma de la fuente**, no traduciendo.

**Nota sobre extensibilidad de D4** (corregida el 2026-08-03 tras la segunda auditoría). La versión original prometía que agregar un tipo de tarea sería "un archivo de configuración más, sin tocar el motor". **Es falso.** Agregar `research` hoy toca tres archivos como mínimo: `models.py` (el `StrEnum` es cerrado), `tasks.py` (`REQUIRED_SLOTS`, con un test que exige que ambos coincidan) y `classify.py` (las señales están hardcodeadas). Si además el tipo nuevo necesita un campo propio —una tarea de investigación quiere "pregunta" y "fuentes", que no encajan en ningún campo actual— suma `models.py` de nuevo, una regla en `completeness.py` y una sección en `render.py`.

Lo que sí es config-driven es que las reglas de completitud derivan su `applies_to` de `REQUIRED_SLOTS`: si el tipo nuevo reusa campos existentes, esas reglas se extienden solas. Es una pieza, no el motor.

**La redacción honesta:** agregar un tipo de tarea toca entre 3 y 6 archivos bien acotados de `core/`. Hacerlo realmente config-driven (tipos cargados desde YAML) es trabajo de arquitectura real y **no está planificado**: la v1 declara tres tipos y la generalidad es un no-objetivo.

---

## 4. Fundamento técnico

Todo lo que sigue sale de la documentación oficial de prompt engineering de Anthropic y del artículo *Effective context engineering for AI agents*. Se listan acá porque **son la justificación de las reglas**, y el README debe citarlas.

| # | Hallazgo | Consecuencia en el diseño |
|---|---|---|
| F1 | Los datos largos van **arriba** y la consulta **abajo**; mejora la calidad hasta un 30% en inputs multi-documento | Fija el orden de las secciones del brief (§7) |
| F2 | Los tags XML desambiguan cuando el prompt mezcla instrucciones, contexto, ejemplos e inputs | El brief usa XML estructural, no headers markdown |
| F3 | "Decile qué hacer, no qué no hacer" | Regla `negative_instruction` |
| F4 | *Context rot*: a más tokens, peor recuperación. El modelo tiene un presupuesto de atención finito | Presupuesto de tokens e inyección selectiva (§8). **Es el núcleo, no un extra** |
| F5 | El lenguaje agresivo (`CRITICAL:`, `You MUST`) hace **sobre-disparar** a los modelos actuales | Regla `over_emphasis` |
| F6 | "Altitud correcta": ni lógica frágil hardcodeada ni generalidades vagas | Regla `wrong_altitude` sobre el perfil |
| F7 | Los ejemplos (few-shot) son de lo más efectivo: 3-5, diversos, en tags `<example>` | Slot de ejemplos, obligatorio en `writing` |
| F8 | El estilo del prompt influye el estilo de la respuesta | El brief no usa bullets decorativos |

**Decisión explícita: el brief no incluye un `<role>`** del tipo "sos un desarrollador senior experto". El destino es un agente que ya tiene su propio system prompt; agregar una persona ficticia es ruido. Documentar el porqué en el README — es justo el vicio de los enhancers genéricos.

---

## 5. Arquitectura

```
promptbrief/
├── core/                    ← librería pura, sin HTTP, sin I/O de red
│   ├── models.py            ← Slot, Profile, BriefRequest, Selection, Finding, Brief
│   ├── errors.py            ← jerarquía de excepciones propias
│   ├── text.py              ← acentos, tokenización, redacción de credenciales
│   ├── budget.py            ← presupuesto de atención
│   ├── tasks.py             ← tipos de tarea y qué exige cada uno
│   ├── classify.py          ← detección del tipo de tarea
│   ├── profile/
│   │   ├── sources.py       ← descubrimiento, lectura segura y hashes
│   │   ├── distill.py       ← .md + package.json → slots
│   │   └── store.py         ← persistencia YAML
│   ├── rules/
│   │   ├── base.py          ← clase Rule y ejecutor
│   │   ├── text.py          ← familia A (§6)
│   │   ├── completeness.py  ← familia B
│   │   └── context.py       ← familia C
│   ├── render.py            ← plantilla del brief
│   └── build.py             ← lint() y build_brief()
├── server/                  ← FastAPI, capa fina sobre core
├── web/                     ← Angular
└── tests/                   ← pytest
```

**Regla dura: `core/` no importa nada de `server/` ni de la CLI, y no sabe que existe HTTP.** Los tests le pegan a `core/`. Es lo que hace posible el hook de v2 sin refactorizar.

---

## 6. El motor de reglas

Cada regla es una clase con la misma interfaz: `id`, `family`, `severity`, `applies_to` y `check()`, que devuelve un `Finding` o `None`.

**No hay registro global.** Cada familia expone una tupla explícita y el ejecutor las recibe por parámetro. Un registro que se llena por efecto secundario del import hace que el resultado dependa de qué módulo importó el test anterior: los tests dejan de estar aislados y el orden de importación pasa a ser parte del comportamiento.

**Los IDs de regla son contrato público** — no se renombran una vez publicados.

### Familia A — Defectos del texto del usuario

| ID | Detecta | Severidad |
|---|---|---|
| `missing_success_criteria` | No hay señal de cuándo la tarea está terminada | error |
| `dangling_reference` | Referencias sin antecedente: "arreglalo", "que ande", "lo mismo de antes" | error |
| `vague_quantifier` | "más rápido", "mejor", "optimizar" sin métrica | warning |
| `negative_instruction` | "no uses X" → sugiere la formulación positiva (F3) | info |
| `multiple_unrelated_tasks` | Varios pedidos sin relación en un mismo texto | warning |
| `over_emphasis` | Mayúsculas sostenidas, `CRITICAL` / `MUST` / `NUNCA` repetidos (F5) | info |

### Familia B — Huecos del brief

| ID | Detecta | Aplica a |
|---|---|---|
| `missing_output_format` | No se declaró qué forma tiene la respuesta | todos |
| `missing_file_scope` | Ningún archivo ni módulo mencionado | `code_change`, `debug` |
| `missing_constraints` | Ninguna restricción declarada ni heredada del perfil | `code_change` |
| `missing_examples` | Tarea de formato o estilo sin ejemplos (F7) | `writing` |
| `missing_repro` | Sin pasos de reproducción | `debug` |
| `missing_expected_vs_actual` | Falta el par "qué esperaba / qué pasa" | `debug` |

### Familia C — Salud del contexto inyectado

Esta familia es la diferenciación de §2. Ninguna herramienta del prior art la tiene.

| ID | Detecta | Severidad |
|---|---|---|
| `budget_exceeded` | Un slot **aplicable** quedó afuera por falta de presupuesto (F4) | error |
| `profile_mostly_irrelevant` | La mayoría de los slots del perfil no aplicaron a esta tarea | info |
| `wrong_altitude` | Regla del perfil demasiado específica y frágil, o demasiado vaga (F6) | info |
| `stale_profile` | El `.md` fuente cambió desde la última destilación | warning |
| `secret_redacted` | Se detectó y tapó algo con forma de credencial al destilar | warning |

**Distinguir los dos motivos de descarte es obligatorio.** Un slot puede quedar afuera porque no aplica al tipo de tarea (normal, esperable, sin hallazgo) o porque no entró en el presupuesto (problema real). Mezclarlos hace que `budget_exceeded` dispare siempre: la auditoría del 2026-08-03 encontró exactamente ese bug en la primera versión del plan. `select_within_budget` devuelve las dos listas por separado.

`irrelevant_slot` se eliminó: el selector ya filtra por tipo de tarea antes de renderizar, así que un slot no aplicable **nunca** puede estar inyectado y la regla era código inalcanzable. Se reemplaza por `profile_mostly_irrelevant`, que sí es alcanzable y dice algo útil: el perfil está mal calibrado para el trabajo que se hace en ese repo.

---

## 7. Plantilla de salida

Orden fijado por F1 (datos largos arriba, consulta abajo) y estructura por F2.

```xml
<project_context>
  <stack source="package.json:1">Next.js 15, TypeScript, Tailwind</stack>
  <convention source="CLAUDE.md:12">
    Static export: next.config.ts uses output "export" with images.unoptimized.
  </convention>
  <relevant_paths>
    src/data/portfolio.ts
    src/components/GameDev.tsx
  </relevant_paths>
</project_context>

<constraints>
  Keep next.config.ts unchanged.
  Follow the existing data structures in src/data/.
</constraints>

<examples>
  <example>...</example>
</examples>

<reproduction>...</reproduction>
<expected_vs_actual>...</expected_vs_actual>

<task>
  Add a new section for Python projects, following the Game Dev section pattern.
</task>

<success_criteria>
  The section renders with cards visually equivalent to the Game Dev ones.
</success_criteria>

<output_format>
  Code changes with file paths.
</output_format>
```

Notas:

- **`<relevant_paths>` lleva rutas, no contenido** (D1).
- El atributo `source` es la **procedencia**: permite rastrear de qué archivo y línea salió cada afirmación, y es lo que hace auditable la destilación. Se emite con escapado de atributo (`quoteattr`), no de texto — el escapado de texto no cubre comillas y permitiría cerrar el atributo e inyectar marcado.
- **Cada slot lleva un `kind`, y el `kind` decide su tag y su sección.** Los slots `constraint` van a `<constraints>`, no a `<project_context>`. Sin esto, la reformulación positiva (F3) nunca llega a la sección que la necesita — era el caso en la primera versión del plan.
- `<constraints>` se emite **en positivo** (F3), en el idioma de la fuente (ver nota de D2).
- `<reproduction>` y `<expected_vs_actual>` solo existen en tareas `debug`. Van **arriba** de `<task>` por F1.
- Ninguna sección vacía se emite.

---

## 8. Inyección selectiva y presupuesto

El corazón de la herramienta y su diferenciación.

Cada slot del perfil declara a qué tipos de tarea aplica:

```yaml
- id: static-export
  applies_to: [code_change, debug]
  content: "Static export: output 'export', images.unoptimized"
  source: CLAUDE.md:12
  tokens: 18
```

Al armar el brief:

1. Se filtran los slots que no aplican al tipo de tarea detectado.
2. Se ordenan por relevancia (coincidencia de términos con el texto del usuario).
3. Se van agregando hasta el presupuesto; lo que no entra se descarta y **se informa cuál**.

**Presupuesto por defecto: 1500 tokens de contexto de proyecto.** Configurable por perfil. El conteo en la v1 es una estimación por caracteres — es suficiente para presupuestar y evita una dependencia de tokenizador.

El brief nunca concatena los `.md`. Si el perfil aporta más de lo que entra, eso es un hallazgo (`budget_exceeded`), no un detalle.

---

## 9. El perfil de proyecto

**Fuentes, en orden de prioridad:** `CLAUDE.md` → `AGENTS.md` → `README.md` → `package.json`.

**No se inventa un formato nuevo.** Quien ya tiene `CLAUDE.md` no configura nada. (Los overrides vía `.promptbrief.yml` se movieron a §12: el perfil YAML ya es editable a mano, así que un segundo formato no aporta nada en v1.)

Cada slot destilado guarda:

- **`kind`** — qué clase de dato es (`stack`, `convention`, `constraint`, `glossary`, `architecture`, `unclassified`). Decide su tag y su sección al renderizar.
- **`source`** — archivo y línea de origen. Procedencia auditable.
- **`id` estable** — derivado del archivo, el kind y un hash del contenido. **No posicional**: si fuera un contador, agregar un bullet arriba renumeraría todo lo de abajo y cada re-scan reportaría el perfil entero como cambiado, destruyendo las ediciones manuales.
- **`needs_review`** — lo que la heurística no pudo clasificar. Estos slots **no se inyectan**: un dato que la herramienta no entendió no puede presentarse al agente como un hecho del proyecto.

Los perfiles viven en `~/.config/promptbrief/projects/<nombre>.yml`. Un archivo por proyecto, en YAML legible y editable a mano.

### Seguridad de la destilación

Estas defensas están en `core/` a propósito, no en el servidor del Plan 2. Hoy el input lo controla el usuario; mañana un endpoint HTTP recibe rutas y nombres de afuera, y una librería que confía en su input se vuelve el agujero.

| Defensa | Por qué |
|---|---|
| **Redacción de credenciales** | Un `CLAUDE.md` con `STRIPE_KEY=sk_live_...` se destilaría en un slot, se guardaría en texto plano en el perfil y terminaría en el brief que el usuario pega en un chat. Lo que matchea un patrón de credencial se reemplaza por `[REDACTED]` y se reporta con `secret_redacted`. Se conserva el contexto, se tira el valor |
| **Nombres de perfil validados** | `save_profile("../../evil")` escapa el directorio. En Windows es peor: `Path("/base") / "C:\\x"` **descarta la base** y escribe en la ruta absoluta. Se valida contra `^[A-Za-z0-9._-]{1,64}$`, se rechazan nombres reservados de Windows (`CON`, `NUL`, `COM1`…) y se verifica que la ruta final quede dentro del directorio |
| **Symlinks no se siguen** | Un `CLAUDE.md` que es un symlink a `~/.ssh/id_rsa` se leería y destilaría igual |
| **Límite de tamaño** (1 MB) y **decodificación tolerante** | Un archivo enorme o en cp1252 no puede tirar abajo el scan entero con un traceback |

---

## 10. Servidor y front

Esta sección se reescribió el 2026-08-03, después de que el core estuviera terminado y de que dos auditorías señalaran que el contrato de seguridad del servidor estaba a medias.

**Servidor** — FastAPI, solo en `127.0.0.1`. Capa fina: valida entrada, llama a `core/`, devuelve JSON. Si un endpoint necesita lógica que no sea traducción HTTP, esa lógica va a `core/`.

| Endpoint | Primitiva de `core/` | Estado |
|---|---|---|
| `GET /api/profiles` | `list_profiles()` | existe |
| `GET /api/profiles/{name}` | `load_profile(name)` | existe |
| `POST /api/profiles/scan` | `scan_project(root, name, force)` | **falta** — hoy la política vive en la CLI |
| `POST /api/profiles` | `save_profile(profile)` | existe, falta el mapeo desde JSON |
| `POST /api/profiles/{name}/sync` | `diff_profiles(old, new)` | **falta** |
| `POST /api/brief` | `build_brief(request, root)` | existe |
| `POST /api/lint` | `lint(request, root)` | existe |

### Lo que falta en `core/` antes de escribir el servidor

**`scan_project(root, name, force) -> Profile`.** Hoy la política de "no hay fuentes conocidas → error" y "ya existe el perfil y no pasaste `--force` → error" vive en `cli.py`. Es política, no presentación: el servidor la necesita igual y la duplicaría. Va a `core/profile/`.

**`slot_to_dict` / `slot_from_dict` públicas.** Ya existen en `store.py` con prefijo `_`, y ya producen dicts JSON-friendly (usan `.value` de los enums). El servidor las necesita para serializar y para aceptar el perfil editado; sin promoverlas, reimplementa el mapeo y aparece una segunda fuente de verdad.

**`diff_profiles(old, new) -> ProfileDiff`.** El endpoint de sync tiene que decir *qué cambió*, y `stale_sources` solo dice *qué archivo* cambió. El problema real: como los IDs derivan del contenido, un bullet editado no es "mismo id, contenido nuevo" sino **un id nuevo que reemplaza a uno viejo**. Un diff ingenuo por id reportaría todo como agregado y borrado.

La reconciliación tiene tres pasos:
1. Los ids que están en los dos perfiles son **sin cambios**.
2. De lo que queda, los que comparten `(source.file, kind)` y son uno solo de cada lado se reportan como **modificados**, con el par viejo/nuevo para que la UI muestre el antes y el después.
3. El resto son **agregados** o **eliminados**.

El paso 2 es una heurística y hay que decirlo: dos bullets editados bajo el mismo heading y en el mismo archivo son ambiguos. En ese caso caen a agregado/eliminado, que es el resultado conservador.

### Contrato de seguridad del servidor

**Escuchar solo en loopback NO alcanza**, y es el error más común en servidores locales. Cualquier página abierta en el navegador del usuario puede hacer `fetch("http://127.0.0.1:PUERTO/api/...")`. El origen es el navegador de la víctima, no un atacante remoto, así que el firewall no lo ve.

| Defensa | Qué previene |
|---|---|
| **Token de sesión**, generado aleatoriamente al arrancar, exigido en todas las requests. `pbrief serve` abre el navegador con el token en la URL | La defensa principal. Una página cualquiera puede llegar a `127.0.0.1` pero **no puede adivinar el token**. Es lo que hace que las otras defensas sean redundantes y no únicas |
| **Validación de `Origin` y `Host`** contra el origen propio | DNS rebinding, que es el ataque que sortea el chequeo de IP |
| **Límite de tamaño del body** | El `text` de un `POST /api/lint` corre las reglas sobre el string completo; sin cota, el costo crece sin límite |
| **Allowlist de directorios para escanear** | `core/` valida los **nombres de perfil**, pero trata `root` como confiable por diseño. Sin allowlist, `POST /api/profiles/scan` es un lector de archivos arbitrario |
| **Validación de esquema en `POST /api/profiles`** | Un perfil malformado persistido una vez rompe todas las lecturas posteriores. `load_profile` ya traduce a `ProfileCorrupt`; el servidor tiene que rechazar **antes** de escribir |
| **Mapeo de errores** | `PromptBriefError` y sus subclases → 4xx. Cualquier otra excepción → 500. La jerarquía existe para que esto sea una sola línea |

**Front** — Angular con componentes standalone y signals. Tres pantallas: lista de perfiles, editor de perfil (slots editables, con la procedencia visible), y generador (textarea → preguntas → brief con botón de copiar y los hallazgos al costado).

Se sirve como estático desde FastAPI, así `pbrief serve` levanta una sola cosa. El front nunca toca el disco: todo pasa por la API local.

**El modo demo público** (Vercel) es una build distinta del mismo front: sin `scan`, sin acceso al filesystem, con el perfil pegado o subido a mano. Se hace **después** de que la versión local funcione, y no comparte servidor con ella.

---

## 11. Tests

- **Reglas** — un test por regla, con casos que disparan y casos que no. Es la mayor parte de la suite.
- **Destilación** — fixtures de `CLAUDE.md` reales, incluidos los de los repos del autor.
- **Presupuesto** — que se corte donde debe y que informe lo descartado.
- **Render** — que el orden de secciones sea el de §7 y que las vacías no se emitan.
- **API** — smoke tests por endpoint.

CI en GitHub Actions: `pytest` + `ruff` en cada push y PR.

---

## 12. Fuera de alcance de la v1

RAG o embeddings. Llamadas a IA. El hook de Claude Code (v2). Multiusuario o hosting con estado. Los tipos de tarea `research`, `review`, `design`, `game_dev`. Overrides vía `.promptbrief.yml` — el perfil YAML ya es editable a mano. Deploy público del front — se hace **después** de que la v1 local funcione, como modo degradado que recibe archivos pegados.

---

## 13. Riesgos

| Riesgo | Mitigación |
|---|---|
| **Angular y Python a la vez, siendo principiante en ambos** | El orden lo contiene: `core/` completo y testeado antes de tocar el front. Si el front se traba, la librería ya existe y sirve |
| **La destilación es el problema difícil**: sacar slots limpios de markdown libre | v1 conservadora: heurísticas sobre headers, listas y bloques de código. Lo dudoso se marca `needs_review` en vez de adivinar |
| **El prior art es cercano** (§2) | El ángulo de contexto de proyecto es real y está documentado. No afirmar novedad en el README |
| **Scope creep hacia "una app"** | §12 es un contrato. Todo lo que no está en el spec va a v1.1 |

---

## 14. Resueltas

Cerradas el 2026-08-03:

1. **D1–D4 confirmadas** por el autor. Ya no son supuestos.
2. **Repo público en GitHub desde el inicio**, con commits chicos e incrementales. El historial es parte del entregable: muestra cómo se construyó, no solo el resultado.
3. **Paquete `promptbrief`, comando `pbrief`.** Se descartó `pb` por riesgo de colisión con binarios existentes.

### Convención de commits

Los commits llevan **únicamente** a Franco Leone como autor. No se agrega trailer `Co-Authored-By`. Los repos son piezas de portfolio y el historial se lee como trabajo propio.
