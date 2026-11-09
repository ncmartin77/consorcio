---
name: feedback-version-mayor
description: En el proyecto consorcio, Claude decide la versión menor solo, pero consulta al usuario antes de subir la mayor
type: feedback
---
Claude incrementa la versión menor (`X.Y-DDMM`) en cada commit sin preguntar; para subir la mayor (cambio de
arquitectura, de reglas de cálculo o que requiere migrar datos) propone y espera confirmación.

**Why:** el usuario lo pidió como regla (está en `CLAUDE.md` → Versionado).
**How to apply:** antes del commit, decir "esto cambia X, propongo N.0" y esperar el sí. Ej.: la v10.0
(interés sin capitalizar y libro del fondo) se confirmó el 09/11/2026 con "hagamos del 1 al 5".
