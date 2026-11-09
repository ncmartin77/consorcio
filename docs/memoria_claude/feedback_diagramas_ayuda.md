---
name: feedback-diagramas-ayuda
description: Los diagramas técnicos no van en la página de Ayuda de la app; la Ayuda muestra solo el manual de usuario
type: feedback
---
La página de Ayuda de la app (`/ayuda`, menú Más → Ayuda y manual) muestra solo `docs/manual_usuario.md`.
Los diagramas técnicos (`docs/diagramas.md`, Mermaid) son documentación del repo y no se agregan a la app
ni al manual.

**Why:** el usuario dijo "los diagramas no van en la pagina de ayuda en la app" (09/11/2026).
**How to apply:** con cada cambio funcional, actualizar el manual (texto para el usuario) y, si cambia una
regla, el diagrama correspondiente en `docs/diagramas.md`.
