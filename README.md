# PromptBrief

PromptBrief turns an informal task description into a structured brief for a coding agent (Claude Code and similar tools), pulling project context from files that already exist in the repo — `CLAUDE.md`, `AGENTS.md`, `README.md`, `package.json` — instead of asking the user to retype conventions and constraints every time. It also lints the description itself, catching things like a missing success criterion or a dangling reference ("fix it") before they reach the agent.

Real run, against a small demo project whose `CLAUDE.md` documents two conventions and two constraints, and whose `package.json` lists three dependencies:

```
$ pbrief scan ./demo-project --name portfolio-demo
Perfil 'portfolio-demo' guardado en C:\Users\leone\.config\promptbrief\projects\portfolio-demo.yml
  5 datos desde 2 archivos

$ pbrief brief "Add a Python projects section to the portfolio" \
    --profile portfolio-demo \
    --success "cards render like the Game Dev section" \
    --format "code changes with file paths" \
    --file src/data/portfolio.ts
<project_context>
  <convention source="CLAUDE.md:5">Static export is enabled in next.config.ts (output "export", images.unoptimized).</convention>
  <convention source="CLAUDE.md:6">Project data lives in src/data/, not hardcoded in components.</convention>
  <stack source="package.json:1">next 15.0.0, react 19.0.0, typescript 5.6.0</stack>
  <relevant_paths>
    src/data/portfolio.ts
  </relevant_paths>
</project_context>

<constraints>
  Solve it without using client-side routing libraries other than the Next.js App Router.
  Keep next.config.ts unchanged.
</constraints>

<task>
  Add a Python projects section to the portfolio
</task>

<success_criteria>
  cards render like the Game Dev section
</success_criteria>

<output_format>
  code changes with file paths
</output_format>
```

("Datos" are the distilled facts — one per bullet or dependency list — and "sin clasificar" ones, if any, are held back until reviewed; see [Design decisions](#design-decisions).)

## How it differs

Prompt linters — [`prompt-control-plane`](https://www.npmjs.com/package/prompt-control-plane) is the closest one — analyze the text of the prompt in isolation: rule IDs, scoring dimensions, blocking questions. That category already exists and PromptBrief doesn't claim to invent it.

What it adds is reading the project instead of just the prompt. Prompt linters check *how* you write; PromptBrief knows *what* you're writing about. It distills a project's own documentation into typed, sourced facts and injects only the ones relevant to the task at hand, instead of asking the user to restate context that's already sitting in `CLAUDE.md`.

## Why these rules

Some of the design — not all of it — follows two sources directly: Anthropic's [prompt engineering best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices) and [*Effective context engineering for AI agents*](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents). The two findings that drove the most structure:

- **Long data goes first, the query goes last (F1).** Anthropic's own measurements show this ordering improves quality on multi-document inputs. It's why the brief's XML sections are fixed in that order: `<project_context>` and `<constraints>` before `<task>`, and debug-only sections (`<reproduction>`, `<expected_vs_actual>`) above the task as well.
- **Context rot (F4).** More tokens in the context window means worse retrieval, not better — there's a finite attention budget, not an unlimited one. That's the reason the project profile has a token budget (1500 by default) instead of concatenating every `.md` file whole: only the slots relevant to the current task type are selected, and what didn't fit is reported, not silently dropped.

A handful of individual rules trace to a specific finding too, and each one says so in its own docstring in `src/promptbrief/core/rules/`, rather than in this README: `negative_instruction` (F3 — say what to do, not what not to do), `over_emphasis` (F5 — aggressive language like `CRITICAL`/`MUST` makes current models over-trigger), `wrong_altitude` (F6 — the "right altitude": neither brittle specifics nor vague generalities), `missing_examples` (F7 — few-shot examples are highly effective for tone and format), and `budget_exceeded` / `profile_mostly_irrelevant` (F4 again, applied per-request instead of to the brief's overall structure). XML tags to disambiguate mixed content (F2) and avoiding decorative bullet styling in the rendered brief (F8) shaped the renderer directly rather than becoming rules.

**The rest of the rule table doesn't come from either source, and doesn't claim to.** `missing_success_criteria`, `dangling_reference`, `vague_quantifier`, `multiple_unrelated_tasks`, `missing_output_format`, `missing_file_scope`, `missing_constraints`, `missing_repro`, `missing_expected_vs_actual`, `stale_profile`, and `secret_redacted` are requirement and context hygiene: catching an empty success criterion or a stale profile is useful on its own merits, not because a paper says so. Presenting all seventeen rules as equally research-backed would overstate what's actually cited — so only the ones with a real citation carry one.

## Design decisions

- **No `<role>` section.** The brief never opens with "you are a senior developer" or similar. The destination is an agent that already has its own system prompt; a fictional persona on top of that is noise, not signal — it's exactly the habit that generic prompt "enhancers" fall into.
- **The brief carries paths, not pasted content.** `<relevant_paths>` lists file paths the agent should look at; it never inlines their contents. This matches the *just-in-time* context strategy Anthropic documents: keep identifiers lightweight and let the agent load what it actually needs, instead of spending the attention budget on content that might not even be relevant to the specific change.
- **The context budget reports what was left out, and why.** A slot can be excluded for two different reasons, and mixing them up produces a useless signal: `not_applicable` (the slot doesn't apply to this task type — normal, expected, not a finding) and `over_budget` (an applicable slot didn't fit — a real problem, reported as `budget_exceeded`). Only the second one is worth flagging.

## Known limitations

- **Nested bullets are flattened.** Every `-`/`*` line is distilled as an independent fact, so a child bullet loses its parent's context: under a `- Testing:` heading-as-bullet, a nested `- never mock the database` becomes a standalone constraint with no trace of what it qualified. This is v1 being deliberately conservative rather than a bug — inferring a parent-child relationship from indentation means injecting a claim the file never made, and every slot carries a `file:line` you can check. Facts that read oddly out of context can be edited or removed in the profile's YAML by hand.

## Security

These guards live in `promptbrief.core`, not in the CLI — so they hold even when something other than the CLI calls into the library (a future HTTP server, for instance) and can't be bypassed by skipping a layer above it.

- **Credential redaction.** Content matching common credential shapes (API keys, GitHub tokens, AWS keys, Slack tokens, JWTs, PEM private key blocks, passwords in connection strings, `key: value` pairs that look like secrets) is replaced with `[REDACTED]` before it's ever written to a profile, and reported via the `secret_redacted` finding. The context survives; the value doesn't.
- **Validated profile names.** Profile names are checked against `^[A-Za-z0-9._-]{1,64}$`, Windows-reserved names (`CON`, `NUL`, `COM1`, …) are rejected, and the resolved path is verified to stay inside the profiles directory. Without this, a name like `../../evil` escapes the directory, and on Windows `Path("/base") / "C:\\x"` discards the base entirely.
- **Symlinks are never followed.** A `CLAUDE.md` that's actually a symlink to `~/.ssh/id_rsa` is skipped, not read.
- **Source files are capped at 1 MB**, read in a single bounded operation (not size-checked then read, which leaves a race window), and files that don't decode are skipped instead of aborting the whole scan.

## Installation

Requires Python 3.11+. From a local clone of the repository:

```bash
cd promptbrief
pip install -e ".[dev]"
```

This installs the `pbrief` command via the project's console-script entry point. The `dev` extra adds `pytest` and `ruff`, which [Running the tests](#running-the-tests) needs; `pip install -e .` alone gives you a working CLI but not those two.

## Commands

### `pbrief scan [PATH] [--name NAME] [--force]`

Distills `CLAUDE.md`, `AGENTS.md`, `README.md`, and `package.json` from a project directory into a profile, saved as YAML under `~/.config/promptbrief/projects/`. `--name` overrides the default (the folder name), which matters when the folder name itself isn't a valid profile name — a directory called `Personal Page` needs `--name personal-page`. `--force` overwrites an existing profile.

```bash
$ pbrief scan . --name portfolio-demo
Perfil 'portfolio-demo' guardado en C:\Users\leone\.config\promptbrief\projects\portfolio-demo.yml
  5 datos desde 2 archivos
```

### `pbrief profiles`

Lists saved profiles.

```bash
$ pbrief profiles
PersonalPage
portfolio-demo
```

### `pbrief lint TEXT [OPTIONS]`

Runs the rule set against a task description without generating a brief. Exits non-zero if any finding is an error.

`lint` and `brief` take the same options, so anything that lints clean builds a brief with no errors under it: `--profile NAME`, `--success`, `--format`, `--file`, `--repro`, `--expected`, `--constraint` and `--example`. `--file`, `--constraint` and `--example` are repeatable — one flag per file, constraint or example. Which ones a request needs depends on the task type the classifier picks: a debug task *errors* without `--repro` and `--expected`, a writing task warns without `--example`, and a code change warns without `--constraint` unless the profile supplies one. The rules read those fields, not the prose, so a description that narrates the reproduction steps inside `TEXT` still counts as missing them.

```bash
$ pbrief lint "arreglalo"
[error] missing_success_criteria: No declaraste cuándo la tarea está terminada.
         -> Agregá qué tiene que pasar para considerarla lista: un test que pasa, algo que se ve en pantalla, un número que baja.
[error] dangling_reference: Usaste una referencia sin antecedente ("arreglalo", "que ande").
         -> Nombrá la cosa concreta: qué archivo, qué componente, qué comportamiento.
[warn ] missing_output_format: No dijiste qué forma tiene que tener la respuesta.
         -> Elegí una: cambios de código con rutas, una lista de opciones, un diff, un texto.
[warn ] missing_file_scope: No hay ningún archivo ni módulo en el alcance.
         -> Nombrá al menos por dónde empezar, o decí explícitamente que no sabés: el agente puede buscarlo, pero conviene que sepa que tiene que buscar.
[warn ] missing_constraints: No declaraste ninguna restricción, y el perfil tampoco aportó.
         -> Nombrá qué no hay que tocar, qué patrón seguir, qué dependencia no agregar.
```

Findings and suggestions are in Spanish — that's the CLI's interface language, chosen because it's the author's daily-use language. The brief's own structural tags (`<task>`, `<constraints>`, …) stay English and stable regardless; only the content passed through from the user and the project's own files keeps its original language, unforced.

### `pbrief brief TEXT [OPTIONS]`

Generates the full XML brief — with project context selected from the named profile when one is given — and prints the findings from the rule set below it. `<project_context>` and `<constraints>` are the same as in the [top example](#promptbrief); this run just omits `--format`, so `missing_output_format` fires as a warning:

```bash
$ pbrief brief "Add a Python section" --profile portfolio-demo --success "cards render" --file src/data/portfolio.ts
<project_context>
  <convention source="CLAUDE.md:5">Static export is enabled in next.config.ts (output "export", images.unoptimized).</convention>
  <convention source="CLAUDE.md:6">Project data lives in src/data/, not hardcoded in components.</convention>
  <stack source="package.json:1">next 15.0.0, react 19.0.0, typescript 5.6.0</stack>
  <relevant_paths>
    src/data/portfolio.ts
  </relevant_paths>
</project_context>

<constraints>
  Keep next.config.ts unchanged.
  Solve it without using client-side routing libraries other than the Next.js App Router.
</constraints>

<task>
  Add a Python section
</task>

<success_criteria>
  cards render
</success_criteria>

---
[warn ] missing_output_format: No dijiste qué forma tiene que tener la respuesta.
         -> Elegí una: cambios de código con rutas, una lista de opciones, un diff, un texto.
```

### `pbrief serve [--port N] [--allow PATH] [--no-browser]`

Runs the local HTTP API the web front consumes — the same core the CLI calls, exposed as JSON over `127.0.0.1`. `--allow` marks a directory as scannable and is repeatable; with none given, the current directory is the only one allowed. `--no-browser` skips opening the printed URL.

```bash
$ pbrief serve --allow C:\Franco\Proyectos
PromptBrief escuchando en http://127.0.0.1:8765
  proyectos permitidos: C:\Franco\Proyectos
Abrí esta URL, que lleva el token de la sesión:
  http://127.0.0.1:8765/?token=Yx3n0_R7pQ...
```

**Why the URL carries a token.** Anything running in the browser can reach `127.0.0.1` — a page you have open in another tab, an ad on it, a local process. "It's only localhost" is not an authentication boundary, and this server reads files and writes profiles. So every start generates a fresh random token: it goes in the URL only for the initial document load, and from there the front sends it in the `X-PromptBrief-Token` header. It's never accepted from the query string on API calls, and uvicorn's access log is turned off (`access_log=False`) — that log records the full query string, and a token written to a file outlives the session that created it. The token is also checked in constant time, on raw bytes, so a non-ASCII value can't turn the comparison into a 500.

**Why there is no `--host`.** The server exposes the machine's filesystem, narrowed to whatever `--allow` lists; binding it to another interface isn't a configurable default, it's a different product with a different threat model. Beyond binding, requests are rejected unless the `Host` header is `127.0.0.1`/`localhost` on the serving port — that's what stops DNS rebinding, where an attacker's domain resolves to `127.0.0.1` so the request is same-origin, carries no `Origin`, and would otherwise look local. `Sec-Fetch-Site` and `Origin` are checked on top of that, and bodies are capped at 1 MB counting bytes as they arrive, since a `Transfer-Encoding: chunked` request has no `Content-Length` to trust.

Every path that reaches the disk — the `root` of a scan, the `root` of a profile the client saves, the `root` a sync re-distills, and the one `brief`/`lint` hash to detect a stale profile — is checked against the `--allow` list on each request, not just the first time it's seen. A profile saved with `root: "C:/"` is rejected at 403 when saved *and* when used, because a stored value is not more trustworthy for having been stored.

## Running the tests

```bash
python -m pytest -v
python -m ruff check .
```

The default run excludes tests marked `slow` (`addopts = "-m 'not slow'"` in `pyproject.toml`),
so it finishes in a couple of seconds. There's currently one: a filesystem-concurrency test that
sabotages `save_profile`'s atomicity across real threads and a multi-megabyte file to prove the
guard actually guards — by design that takes over a minute, since a smaller, faster version of
the same test stopped reliably catching the regression it exists to catch. Run it explicitly
(CI does, as a separate step) with:

```bash
python -m pytest -v -m slow
```
