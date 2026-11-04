---
name: Actualizar versión en cada commit
description: Siempre incrementar version.txt antes de hacer commit en el proyecto consorcio
type: feedback
---
Siempre actualizar `version.txt` antes de cada commit en `/home/norberto/consorcio/`. El formato es `X.Y-DDMM` (ej: `1.9-1210`). Incrementar el número menor (Y) en cada push.

**Why:** el CLAUDE.md lo especifica explícitamente y el badge de versión en el navbar lo muestra en tiempo real. No hacerlo acumula deuda de tracking.

**How to apply:** antes de `git commit`, editar `version.txt` y sumar 1 al número menor. Incluir el cambio en el mismo commit con mensaje `chore: versión X.Y-DDMM` o incluirlo en el commit principal.
