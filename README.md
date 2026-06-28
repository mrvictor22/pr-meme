# pr-meme 🎭

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**pr-meme** es un [Claude Code](https://claude.com/claude-code) skill (empaquetado también
como **plugin instalable**) que lee el contexto de un Pull Request de GitHub y propone un
**meme contextual** para publicarlo como comentario del PR — **siempre con tu confirmación
antes de publicar.**

![meme](https://api.memegen.link/images/mordor/ONE_DOES_NOT_SIMPLY/review_a_2000_line_PR.png)

> Ese meme se generó solo con una URL. Sin API key, sin subir archivos, sin fricción.

## Qué hace y por qué

Revisar PRs es repetitivo. Un meme bien puesto baja la tensión de un PR gigante, celebra un
bug cerrado o se ríe (con cariño) de una CI en llamas. `pr-meme`:

1. **Lee el contexto** del PR con la CLI `gh` (título, rama, tamaño del diff, estado de CI,
   archivos cambiados).
2. **Clasifica** el PR (¿es un `feat`? ¿un `fix`? ¿2000 líneas? ¿CI roja?) y lo mapea a una
   **plantilla de meme**.
3. **Construye la URL** de [memegen.link](https://memegen.link) con el escape correcto.
4. **Te propone** el meme y la justificación, y **espera tu OK**.
5. Solo entonces publica `![meme](URL)` con `gh pr comment`.

**¿Por qué memegen.link por URL pura?** Es determinista y sin fricción: la imagen vive en
`https://api.memegen.link/images/{plantilla}/{arriba}/{abajo}.png` — sin API key, sin auth,
sin secretos. GitHub renderiza esa URL externa mediante su proxy **Camo**, así que basta un
`![meme](URL)` en el comentario. (No se suben archivos de imagen locales: la API de GitHub no
lo soporta de forma fiable.)

## Requisitos

- [`gh`](https://cli.github.com/) (GitHub CLI) **ya autenticado** (`gh auth status` debe estar OK).
- `python3` (solo stdlib — sin dependencias que instalar).

## Instalación

### Como plugin (recomendado)

```text
/plugin marketplace add mrvictor22/pr-meme
/plugin install pr-meme
```

Eso registra el skill **y** el slash command `/pr-meme`.

### Manual (solo el skill)

Copia la carpeta del skill a tu directorio de skills de Claude Code:

```bash
git clone https://github.com/mrvictor22/pr-meme.git
cp -r pr-meme/skills/pr-meme ~/.claude/skills/pr-meme
# El script auxiliar va junto al skill:
cp -r pr-meme/scripts ~/.claude/skills/pr-meme/scripts
```

## Uso

En lenguaje natural (el skill se dispara solo):

```text
Ponle un meme al PR 123
Comenta el PR con un meme
Memea el PR de la rama actual
Add a meme to PR 42
```

O con el slash command:

```text
/pr-meme 123      # PR específico
/pr-meme          # usa el PR de la rama actual
```

El flujo siempre es: **leer contexto → proponer meme (con justificación y URL) → confirmar →
publicar**. Si no hay PR en la rama, te pedirá el número.

## Reglas: contexto → plantilla

Se evalúan de arriba hacia abajo; **la primera que coincide gana**.

| # | Condición detectada | Plantilla | Texto (arriba / abajo) |
|---|---------------------|-----------|------------------------|
| 1 | `additions + deletions > 1000` (PR enorme) | `mordor` | `ONE DOES NOT SIMPLY` / `review a 2000 line PR` |
| 2 | CI en **rojo** (cualquier tipo) | `fine` | `THIS IS FINE` / `(CI is on fire)` |
| 3 | `fix`/`bug`/`hotfix` + CI **verde** | `success` | `FIXED THE BUG` / `CI IS GREEN` |
| 4 | `feat`/`feature` | `drake` | `writing tests` / `shipping the feature` |
| 5 | `refactor`/`cleanup`/`rewrite` | `fry` | `NOT SURE IF refactor` / `OR REWRITE` |
| 6 | por defecto | `success` (o `interesting`) | `SHIPPED IT` / `LGTM` |

El tipo se detecta desde el título del PR (convención `feat:`/`fix:`/`refactor:` o palabras
clave). Los textos se adaptan al PR concreto (nombre real del fix, del feature, etc.).

## El script auxiliar

`scripts/build_meme_url.py` aplica el escape de memegen.link (sin dependencias):

```bash
python3 scripts/build_meme_url.py --template mordor \
  --top "ONE DOES NOT SIMPLY" --bottom "review a 2000 line PR"
# -> https://api.memegen.link/images/mordor/ONE_DOES_NOT_SIMPLY/review_a_2000_line_PR.png

python3 scripts/build_meme_url.py --selftest   # valida la codificación
```

Reglas de escape aplicadas: ` ` → `_`, `_` → `__`, `-` → `--`, `?` → `~q`, `&` → `~a`,
`%` → `~p`, `#` → `~h`, `/` → `~s`, `\` → `~b`, `<` → `~l`, `>` → `~g`, `"` → `''`,
salto de línea → `~n`, línea vacía → `_`.

## Personalización

¿Quieres tus propias plantillas o reglas?

- **Añade plantillas:** elige cualquier id de [memegen.link/templates](https://memegen.link/templates)
  (p. ej. `disastergirl`, `aliens`, `doge`) y agrégalo como una fila nueva en la tabla de
  decisión del skill (`skills/pr-meme/SKILL.md`) y del command (`commands/pr-meme.md`).
- **Cambia los textos o el orden:** la tabla se evalúa de arriba abajo; mueve filas para
  cambiar la prioridad o edita la columna de texto.
- **Plantillas personalizadas con tu propia imagen:** memegen.link soporta
  `?background=<url>` sobre la plantilla `custom`. Pasa el texto por el script y añade el
  parámetro a mano si lo necesitas.

## Publica de forma responsable

Un meme es humor de equipo, no un arma. Mantén el tono **profesional y sin ofensas**: celebra
o comenta el trabajo, nunca ataques a la persona. El skill **siempre pide confirmación** antes
de publicar — esa pausa existe para que el meme sume al PR, no para que reste. Si dudas de si
cae bien, no lo publiques.

## Licencia

[MIT](LICENSE) © 2026 Victor Alfonso
