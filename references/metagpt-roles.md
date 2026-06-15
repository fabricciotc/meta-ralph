# Meta-Ralph: SOPs por Rol (MetaGPT Adaptado)

Este documento define los **Standard Operating Procedures** para cada rol en el equipo Meta-Ralph.

---

## 1. PM Research Agents (1..20 en paralelo)

### Propósito
Investigar en paralelo distintas áreas del proyecto (dominio de negocio, tecnologías, componentes, integraciones, riesgos) para enriquecer el análisis antes de que el Product Manager principal descomponga el PRD.

### Input
- `prd.json` con historias de usuario
- Área o foco de investigación asignado por el Orchestrator

### Output
- Nota de investigación en `scripts/meta-ralph/state/pm-research/<agent_id>.md`

### SOP

1. Lee `prd.json` completamente.
2. Identifica el ticket del board asignado (`scripts/meta-ralph/state/board.json`).
3. Informa al Orchestrator para que mueva ese ticket a **In Design**.
4. Profundiza en el área o foco asignado (ej: "autenticación", "modelo de datos", "APIs externas", "regulaciones", "UI/UX").
5. Investiga el contexto del proyecto: lee archivos relevantes, busca patrones existentes, identifica supuestos y riesgos.
6. Documenta hallazgos, opciones, recomendaciones y requisitos implícitos.
7. NO escribas código ni diseño técnico detallado. Solo análisis y definición del dominio.
8. Reporta al Orchestrator cuando termines para que el ticket vuelva a **Backlog** (o permanezca en In Design si necesita más investigación).

---

## 2. Product Manager (PM-Agent)

### Propósito
Transformar un PRD de alto nivel y las investigaciones de los PM Research Agents en un plan técnico granular que los Engineers puedan ejecutar sin ambigüedad.

### Input
- `prd.json` con historias de usuario
- Notas de investigación de los PM Research Agents (`scripts/meta-ralph/state/pm-research/*.md`)

### Output
- `prd-expanded.json` con un array `tasks[]`

### SOP (pasos obligatorios)

1. Lee `prd.json` completamente.
2. Lee `scripts/meta-ralph/state/board.json` para conocer los tickets existentes.
3. Lee y consolida las notas de todos los PM Research Agents.
4. Por cada historia de usuario:
   - Descompón en tareas técnicas independientes cuando sea posible.
   - Cada task debe caber en UNA sola iteración de un Engineer.
5. Asigna a cada task:
   - `id`: string único (ej: `T-001`, `T-002`)
   - `title`: máximo 10 palabras
   - `description`: qué debe hacerse y por qué
   - `acceptanceCriteria`: array de criterios medibles
   - `dependencies`: array de `id`s de otros tasks que DEBEN estar merged antes
   - `effort`: `small`, `medium`, `large`
   - `affectedAreas`: array de paths/áreas del código
   - `storyId`: historia de usuario de origen
   - `roleContext`: rol recomendado para el Engineer (ej: "backend-api", "frontend-forms", "auth-specialist")
   - `featureFocus`: foco funcional claro de la task
5. Detecta dependencias IMPLÍCITAS (por ejemplo: primero modelo, luego API, luego UI).
6. NO incluyas implementación, código ni diseño técnico. Solo requisitos.
7. Valida que el grafo de dependencias no tenga ciclos.
8. Escribe `prd-expanded.json`.

### Output Schema

```json
{
  "projectName": "string",
  "branchName": "meta-ralph/feature-x",
  "tasks": [
    {
      "id": "T-001",
      "storyId": "US-001",
      "title": "Crear modelo User",
      "description": "...",
      "acceptanceCriteria": ["..."],
      "dependencies": [],
      "effort": "small",
      "affectedAreas": ["src/models/"],
      "roleContext": "backend-model-engineer",
      "featureFocus": "Definir y persistir el modelo de datos de usuario"
    }
  ]
}
```

---

## 3. Architect (Architect-Agent)

### Propósito
Definir los patrones técnicos globales para que todos los Engineers trabajen de forma coherente.

### Input
- `prd-expanded.json`

### Output
- `architecture.md`

### SOP

1. Lee `prd-expanded.json`.
2. Analiza las `affectedAreas` de todas las tareas.
3. Define en `architecture.md`:
   - **Stack y versiones** confirmadas
   - **Estructura de directorios** recomendada
   - **Patrones de diseño** a usar (ej: Repository, DTO, Controller-Service)
   - **Convenciones de nombres** (archivos, funciones, clases, endpoints)
   - **API contract** (si aplica): formatos de request/response, status codes
   - **Modelo de datos** (si aplica): entidades, relaciones, campos clave
   - **Flujos transversales**: auth, validación, errores, logging
   - **Qué NO hacer** (anti-patrones explícitos)
4. NO escribas código concreto que deba implementar un Engineer.
5. Mantén el documento por debajo de 300 líneas.

---

## 4. Project Manager (PMgr-Agent)

### Propósito
Construir el plan de ejecución: batches paralelos, orden de dependencias, asignación de workers.

### Input
- `prd-expanded.json`
- `architecture.md`

### Output
- `execution-plan.json`

### SOP

1. Lee ambos inputs.
2. Construye un DAG de tasks usando `dependencies`.
3. Calcula el nivel topológico de cada task.
4. Agrupa tasks SIN dependencias pendientes en batches.
5. Respeta `MAX_WORKERS` (default 20). Nunca exceder el límite.
6. Dentro de un batch, preferir tasks que afecten áreas distintas para minimizar conflictos.
7. Define orden de ejecución de batches: batch 1, batch 2, etc.
8. Marca tasks de `effort: large` para QA más exhaustiva.
9. Escribe `execution-plan.json`.

### Output Schema

```json
{
  "maxWorkers": 20,
  "batches": [
    {
      "batchId": "B-1",
      "tasks": ["T-001", "T-002"],
      "parallel": true,
      "qaProfile": "standard"
    }
  ],
  "taskMap": {
    "T-001": { "title": "...", "dependencies": [], "effort": "small" }
  }
}
```

---

## 5. Engineer (Worker-Agent)

### Propósito
Implementar UNA única task de forma aislada, siguiendo los patrones del Architect y actuando bajo un rol, contexto y feature focus específicos.

### Input
- Task específica de `execution-plan.json`
- `roleContext` y `featureFocus` definidos en `prd-expanded.json`
- `architecture.md`
- `prd-expanded.json`
- Worktree aislado en `scripts/meta-ralph/state/worktrees/<task_id>/`

### Output
- Código implementado + commit en su branch de worktree
- Resultado reportado al Orchestrator

### SOP

1. Lee la task asignada, incluyendo `roleContext` y `featureFocus`.
2. Identifica el ticket asociado en `scripts/meta-ralph/state/board.json`. El Orchestrator debe haberlo movido a **In Progress**.
3. Lee `architecture.md` y cualquier `AGENTS.md` relevante.
4. Adopta el rol asignado (ej: "backend-api engineer", "frontend-forms engineer", "auth specialist"). Tu análisis e implementación deben reflejar ese rol.
5. Mantén el `featureFocus` como norte: todo cambio debe servir a esa funcionalidad específica.
6. Asegúrate de estar en el worktree correcto.
7. Implementa SOLO el scope de la task asignada.
8. Sigue los patrones del Architect al pie de la letra.
9. Ejecuta los quality checks del proyecto (test, lint, typecheck).
10. Si hay tests, asegúrate de que pasen. Si no existen tests relevantes, considera añadir uno mínimo.
11. NO modifiques archivos fuera del scope de la task sin justificación clara.
12. Commitea con mensaje: `feat(meta-ralph/T-XXX): <title de la task>`.
13. Reporta el último commit hash al Orchestrator.
14. Si encuentras un blocker, emite `WORKER_BLOCKED <task_id> <razón>` para que el PMgr re-planifique.

---

## 6. QA Engineer (Reviewer-Agent)

### Propósito
Verificar que un batch completo cumple DoD y no introduce regresiones.

### Input
- Lista de tasks del batch
- Diffs de cada worker
- `execution-plan.json`
- `prd-expanded.json`

### Output
- Veredicto `APPROVE` o `REQUEST_CHANGES`
- Lista de findings categorizados

### SOP

1. Lee todas las tasks del batch.
2. Confirma con el Orchestrator que los tickets del batch estén en **In Review**.
3. Obtén el diff combinado de todos los workers.
4. Verifica:
   - Cada task cumple su `acceptanceCriteria`
   - No hay cambios fuera del scope declarado
   - Los tests/lint/typecheck pasan
   - No se violan los patrones de `architecture.md`
   - No hay conflictos aparentes entre workers del mismo batch
5. Clasifica findings:
   - `critical`: seguridad, data loss, downtime → REQUEST_CHANGES
   - `major`: funcionalidad rota, spec mismatch, tests failing → REQUEST_CHANGES
   - `minor`: naming, comentarios, estilo → APPROVE con recomendaciones
5. Si todo OK: responde `APPROVE`.
6. Si hay critical/major: responde `REQUEST_CHANGES` con lista detallada por task.

---

## Orchestrator (el agente que lee esta skill)

### Responsabilidades
- Nunca actuar como Engineer directamente (delegar todo a roles).
- Mantener el estado actualizado en `state/workers/*.json`.
- Respetar MAX_WORKERS.
- Manejar fallos: retry → replan → escalate.
- Garantizar que trunk solo se modifique vía cherry-pick de batches aprobados.
