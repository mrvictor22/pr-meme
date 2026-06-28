---
name: pr-meme
description: Use when the user wants to put a meme on a GitHub Pull Request or react to a PR with humor — triggers like "ponle un meme al PR", "comenta el PR con un meme", "memea el PR 123", "reacciona al PR con un meme", "add a meme to PR", "comment the PR with a meme", "meme this PR", "react to the PR with a meme". Reads PR context with gh, proposes a contextual memegen.link meme, and posts it only after explicit human approval.
allowed-tools: Bash(gh *), Bash(python3 *)
---

# PR Meme

Lee el contexto de un Pull Request de GitHub y publica un **meme contextual** como
comentario, usando [memegen.link](https://memegen.link) (URL pura, sin API key) y la
CLI `gh`. **Nunca publica sin tu confirmación explícita.**

## Contexto del PR (se inyecta al cargar el skill)

> Si no hay PR en la rama actual, los bloques devuelven `NO_PR`/`NO_CHECKS`/`NO_DIFF`.
> En ese caso, **pídele al usuario el número de PR** antes de continuar.

- PR (JSON): !`gh pr view --json number,title,headRefName,additions,deletions,changedFiles,state,url 2>/dev/null || echo "NO_PR (no hay PR para la rama actual; pide el número)"`
- Checks de CI: !`gh pr checks 2>/dev/null || echo "NO_CHECKS (sin checks o sin PR)"`
- Archivos cambiados: !`gh pr diff --name-only 2>/dev/null | head -50 || echo "NO_DIFF"`

## Flujo (síguelo en orden)

1. **Resuelve el PR.** Usa el contexto inyectado. Si es `NO_PR`, pregunta el número y
   reejecuta con `gh pr view <num> --json number,title,headRefName,additions,deletions,changedFiles,state,url`,
   `gh pr checks <num>` y `gh pr diff <num> --name-only | head -50`.
2. **Detecta el tipo** desde el título: convención `feat:` / `fix:` / `refactor:` /
   `chore:` o palabras clave (bug, hotfix, cleanup, rewrite, etc.).
3. **Lee el estado de CI:** ¿verde (todos pasan) o rojo (algún `fail`)? Si `NO_CHECKS`,
   trátalo como "sin señal de CI".
4. **Clasifica** con la tabla de decisión (abajo) y elige plantilla + textos.
5. **Construye y VERIFICA la URL** con el script. `--verify` codifica los caracteres
   especiales (incluidos acentos, `ñ` y emoji → percent-encoding) **y** comprueba que la
   imagen realmente renderiza antes de usarla:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_meme_url.py" --template <plantilla> --top "<ARRIBA>" --bottom "<ABAJO>" --verify
   ```
   (Instalación manual del skill: `${CLAUDE_PLUGIN_ROOT}` no está definido; usá el path real,
   p. ej. `python3 ~/.claude/skills/pr-meme/scripts/build_meme_url.py --template ... --verify`.)
   - `RENDER_OK` (exit 0) → seguí al paso 6. Si el `RENDER_OK` trae un aviso de que memegen
     **reescribió la URL** a su forma canónica, mostráselo al usuario y confirmá que el texto
     se ve bien antes de proponer (es señal de texto no canónico).
   - `RENDER_FAIL [transient] <status>` (exit 2) → memegen **no renderizó ahora; es un
     transitorio** (cold-start, blip del router de Heroku, o rate-limit de la ruta sin
     `?token=`), **no** un outage permanente. El script ya reintentó con backoff. **No
     publiques** todavía — dejarías una imagen rota. Avisá: "memegen no renderizó
     (transitorio); reintentá en unos segundos", mostrá la URL y ofrecé reintentar. **Nunca
     postees una URL que no pasó la verificación.**
   - `RENDER_FAIL [meme_error] <status>` (exit 2) → es un **bug del meme** (p. ej. `404` =
     template inexistente / URL inválida), no un problema de memegen. **Corregí el meme**
     (revisá la plantilla y los textos) y volvé a verificar. No tiene sentido reintentar igual.
6. **Propón el meme** al usuario: muestra la **plantilla elegida**, una **justificación
   de una línea**, los textos y la **URL** + el markdown `![meme](URL)`. Pide aprobación
   explícita ("¿lo publico?").
7. **Solo tras un OK claro**, publica:
   ```bash
   gh pr comment <num> --body "![meme](URL)"
   ```
   Si el usuario no aprueba (o pide otro), ajusta y vuelve a proponer. **No publiques nunca
   sin confirmación.**

## Tabla de decisión (contexto → plantilla)

Evalúa de arriba hacia abajo; **la primera regla que coincide gana**.

| # | Condición detectada | Plantilla | Texto (arriba / abajo) | Por qué |
|---|---------------------|-----------|------------------------|---------|
| 1 | `additions + deletions > 1000` | `mordor` | `ONE DOES NOT SIMPLY` / `review a 2000 line PR` | PR gigante: revisarlo es una odisea. |
| 2 | CI en **rojo** (cualquier tipo de PR) | `fine` | `THIS IS FINE` / `(CI is on fire)` | Algo falla; humor de aceptación. |
| 3 | `fix`/`bug`/`hotfix` + CI **verde** | `success` | `FIXED THE BUG` / `CI IS GREEN` | Bug cerrado y checks en verde. |
| 4 | `feat`/`feature` | `drake` | `writing tests` / `shipping the feature` | El clásico Drake (rechaza/aprueba). Alternativa: `success`. |
| 5 | `refactor`/`cleanup`/`rewrite` | `fry` | `NOT SURE IF refactor` / `OR REWRITE` | Refactor que huele a reescritura. |
| 6 | Por defecto | `success` | `SHIPPED IT` / `LGTM` | Caso genérico positivo. Alternativa: `interesting`. |

Plantillas usadas (todas existen en memegen.link, sin auth): `mordor`, `fine`, `success`,
`drake`, `fry`, `interesting`. Ajusta los textos al PR concreto (nombre real del fix, del
feature, etc.) manteniendo el espíritu de la fila.

## Reglas

- **Humor profesional.** Cero ofensas, cero ataques personales, cero sarcasmo hiriente.
  El meme celebra o comenta el trabajo, no a la persona.
- **Verificación obligatoria.** Nunca publiques una URL sin `RENDER_OK`. Un `RENDER_FAIL`
  `[transient]` (5xx/timeout) es un transitorio: reintentá en un rato, no es un outage. Un
  `RENDER_FAIL [meme_error]` (4xx) es un bug del meme: corregí plantilla/textos. En ningún
  caso se postea hasta tener `RENDER_OK`.
- **Confirmación obligatoria.** Propón → espera OK → publica. Nunca al revés.
- **Sin PR no hay meme.** Si no detectas PR, pide el número; no inventes.
- **Solo URL externa.** El comentario es `![meme](URL)` de memegen.link. No subas archivos
  de imagen locales (la API de GitHub no lo soporta de forma fiable; GitHub renderiza la
  URL externa vía su proxy Camo).
- **Sin secretos.** memegen.link no necesita API key — el flujo por defecto es sin token. Ese
  modo anónimo puede salir con marca de agua y está sujeto a rate-limit transitorio en la ruta
  sin `?token=` (la causa probable de un `RENDER_FAIL [transient]`). Si el usuario tiene un
  token propio, podés pasarlo con `--token <valor>` (se agrega como `?token=...`); no pidas ni
  guardes credenciales y mantené el flujo sin token como default. **Ojo:** con `--token`, el
  token queda en la URL que se postea — no lo uses en PRs públicos salvo que no te importe
  exponerlo.
