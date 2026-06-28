---
description: Publica un meme contextual en un comentario de un PR de GitHub (pide confirmación antes de publicar)
argument-hint: "[número de PR]"
allowed-tools: Bash(gh *), Bash(python3 *)
---

# /pr-meme $ARGUMENTS

Lee el contexto del PR `$ARGUMENTS` (o el de la rama actual si no pasas número),
propone un meme contextual de [memegen.link](https://memegen.link) y lo publica como
comentario **solo tras tu confirmación explícita**.

## Contexto del PR (inyectado)

- PR (JSON): !`gh pr view $ARGUMENTS --json number,title,headRefName,additions,deletions,changedFiles,state,url 2>/dev/null || echo "NO_PR (no hay PR; pide o pasa el número)"`
- Checks de CI: !`gh pr checks $ARGUMENTS 2>/dev/null || echo "NO_CHECKS"`
- Archivos cambiados: !`gh pr diff $ARGUMENTS --name-only 2>/dev/null | head -50 || echo "NO_DIFF"`

## Qué hacer

1. Si el contexto es `NO_PR`, pide el número de PR y reejecuta los `gh` de arriba con él.
2. **Detecta el tipo** desde el título (`feat:`/`fix:`/`refactor:`/`chore:` o palabras
   clave) y **lee el estado de CI** (verde / rojo / sin checks).
3. **Clasifica** con la tabla y elige plantilla + textos. Evalúa de arriba abajo; la
   primera coincidencia gana:

   | # | Condición | Plantilla | Texto (arriba / abajo) |
   |---|-----------|-----------|------------------------|
   | 1 | `additions+deletions > 1000` | `mordor` | `ONE DOES NOT SIMPLY` / `review a 2000 line PR` |
   | 2 | CI en rojo | `fine` | `THIS IS FINE` / `(CI is on fire)` |
   | 3 | `fix`/`bug` + CI verde | `success` | `FIXED THE BUG` / `CI IS GREEN` |
   | 4 | `feat` | `drake` | `writing tests` / `shipping the feature` |
   | 5 | `refactor`/`cleanup` | `fry` | `NOT SURE IF refactor` / `OR REWRITE` |
   | 6 | por defecto | `success` | `SHIPPED IT` / `LGTM` |

4. **Construye y verifica la URL** (codifica caracteres especiales —acentos, `ñ`, emoji vía
   percent-encoding— y comprueba el render):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_meme_url.py" --template <plantilla> --top "<ARRIBA>" --bottom "<ABAJO>" --verify
   ```
   (Instalación manual del skill: el script queda en `~/.claude/skills/pr-meme/scripts/`.)
   - `RENDER_FAIL [transient]` (5xx/timeout): memegen no renderizó por un **transitorio**
     (cold-start / blip del router Heroku / rate-limit de la ruta sin `?token=`), no un outage.
     El script ya reintentó con backoff. **No publiques**; avisá "transitorio, reintentá en unos
     segundos", mostrá la URL y ofrecé reintentar.
   - `RENDER_FAIL [meme_error]` (4xx, p. ej. `404`): es un **bug del meme** (template/URL
     inválido). **Corregí el meme** y reverificá; reintentar igual no sirve.
5. **Propón** el meme: plantilla + justificación de una línea + textos + URL + el markdown
   `![meme](URL)`. Pide aprobación explícita.
6. **Solo tras OK**, publica:
   ```bash
   gh pr comment <num> --body "![meme](URL)"
   ```

**Reglas:** humor profesional sin ofensas; nunca publicar sin `RENDER_OK` ni sin
confirmación; sin PR no hay meme (pide el número); solo URL externa, nada de subir
imágenes; sin API keys.
