---
name: meta-ralph
description: "MetaGPT-style multi-agent autonomous coding loop for Kimi Code CLI. Orchestrates parallel Product Manager research agents, Architect, Project Manager, up to 20 parallel Engineer workers with role context and feature focus, and QA roles to implement PRDs end-to-end. Use when: user asks for meta ralph, multi-agent loop, parallel team execution, metagpt-style workflow, or autonomous implementation with up to 20 parallel workers. Do NOT load for: simple one-shot tasks, planning-only work, or tasks requiring continuous human approval."
description-en: "MetaGPT-style multi-agent autonomous coding loop for Kimi Code CLI. Orchestrates parallel Product Manager research agents, Architect, Project Manager, up to 20 parallel Engineer workers with role context and feature focus, and QA roles to implement PRDs end-to-end. Use when: user asks for meta ralph, multi-agent loop, parallel team execution, metagpt-style workflow, or autonomous implementation with up to 20 parallel workers. Do NOT load for: simple one-shot tasks, planning-only work, or tasks requiring continuous human approval."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Shell", "Agent", "Task", "TaskOutput", "TaskList", "TaskStop"]
user-invocable: true
disable-model-invocation: false
---

# Meta-Ralph: MetaGPT Multi-Agent Orchestrator

Skill que fusiona la metodología **MetaGPT** (roles especializados + SOPs) con el loop autónomo **Ralph**. Permite hasta **20 agentes PM de investigación en paralelo** durante el análisis y hasta **20 agentes Engineer en paralelo** durante la ejecución, cada uno con su propio rol, contexto y foco de feature.

## Cuándo usar esta skill

- El usuario pide **meta ralph**, **multi-agent loop**, **parallel team**, **metagpt workflow**
- Implementación autónoma de **PRDs grandes** con muchas historias de usuario
- Tareas que se benefician de **roles especializados** (PM, Arquitecto, Planner, QA)
- Necesidad de **paralelismo masivo** (hasta 20 workers)

## NO usar cuando

- Tareas simples de una sola respuesta
- Solo planificación sin implementación
- El usuario requiere aprobación humana continua

## Arquitectura de Roles

```
Orchestrator (meta-ralph — este skill)
├── PM Research Agents (1..20) → investigan áreas del proyecto en paralelo y definen el dominio
├── Product Manager            → consolida hallazgos y descompone el PRD en tareas técnicas
├── Architect                  → diseña patrones y convenciones
├── Project Manager            → prioriza, detecta dependencias, arma batches
├── Engineer (1..20)           → implementan en worktrees aislados, cada uno con rol/contexto/feature focus
└── QA Engineer                → revisa integración de cada batch
```

## Formas de Uso

### 1. Modo Skill Nativo (recomendado)
Dentro de una sesión de Kimi Code CLI, menciona el skill:
- `"implementa esto con meta-ralph"`
- `"usa meta-ralph para este PRD"`
- `"corre el multi-agent loop"`

Kimi cargará este SKILL.md y actuará como Orchestrator usando directamente el tool `Agent` para lanzar PM, Architect, PMgr, Workers y QA.

### 2. Modo CLI Autónomo
Primero instala el comando:
```bash
bash ~/.kimi/skills/meta-ralph/install.sh
source ~/.bash_profile  # o ~/.zshrc
```

Luego en cualquier proyecto git:

| Comando | Acción |
|---------|--------|
| `meta-ralph init` | Crea `scripts/meta-ralph/` en el proyecto actual |
| `meta-ralph run`  | Ejecuta las 5 fases y abre el dashboard en `http://localhost:5050` |
| `meta-ralph run --max-workers 10` | Limita workers paralelos a 10 |
| `meta-ralph run --skip-pm` | Salta fase 1 (usa prd-expanded.json existente) |
| `meta-ralph run --skip-architect` | Salta fase 2 (usa architecture.md existente) |
| `meta-ralph run --skip-planner` | Salta fase 3 (usa execution-plan.json existente) |
| `meta-ralph run --no-dashboard` | No abre el dashboard web |
| `meta-ralph dashboard` | Lanza solo el dashboard web |
| `meta-ralph dashboard --port 8080` | Lanza el dashboard en puerto personalizado |
| `meta-ralph status` | Muestra estado de workers activos |
| `meta-ralph stop` | Detiene todos los workers activos y el dashboard |

## Dashboard Web

`meta-ralph` incluye un tablero Kanban local accesible en `http://localhost:5050`.

### Columnas del board

| Columna | Significado | Quién actúa |
|---------|-------------|-------------|
| **Backlog** | Tickets/historias pendientes de análisis | Usuario / Product Manager |
| **In Design** | PM Research Agents investigando y definiendo requisitos | PM Research Agents |
| **In Progress** | Engineers implementando la task | Engineer workers |
| **In Review** | QA revisando el batch | QA Engineer |
| **Done** | Task aprobada y mergeada al trunk | — |

### Funcionalidades

- **Ver progreso en tiempo real**: el board se actualiza vía WebSocket mientras los agentes trabajan.
- **Crear tickets**: desde el formulario "+ Nuevo ticket". Aparecen en Backlog y el Orchestrator los procesa.
- **Mover tickets**: drag & drop entre columnas. El Orchestrator respeta los estados que él mismo no ha cambiado.
- **Estadísticas**: contadores de total, activos, done y bloqueados en la parte superior.

El estado fuente de verdad está en `scripts/meta-ralph/state/board.json`.

## Flujo de 5 Fases

### Fase 1 — PM Analysis (Investigación Paralela)
Input: `prd.json` → Output: `prd-expanded.json`
- El Orchestrator puede lanzar **hasta 20 PM Research Agents en paralelo** para investigar distintas áreas del proyecto, tecnologías, dominio de negocio o componentes.
- Cada agente PM profundiza en su área asignada y documenta hallazgos, riesgos, requisitos implícitos y opciones de diseño.
- El Product Manager principal consolida los hallazgos y expande cada historia de usuario en tasks técnicas granulares.
- Cada task incluye: `id`, `title`, `description`, `acceptanceCriteria[]`, `dependencies[]`, `effort`, `affectedAreas[]`.

### Fase 2 — Architecture
Input: `prd-expanded.json` → Output: `architecture.md`
- El Architect define patrones técnicos, APIs, estructura de directorios y convenciones.
- Se enfoca en lo **global y reusable**, no en implementar cada task.

### Fase 3 — Planning & Dispatch
Input: `prd-expanded.json` + `architecture.md` → Output: `execution-plan.json`
- El Project Manager construye un DAG de dependencias.
- Agrupa tareas independientes en batches de máximo N workers (default 20).
- Define el orden de ejecución de los batches.

### Fase 4 — Parallel Execution (Loop Principal)
Input: `execution-plan.json`
- Por cada batch:
  1. Spawn de hasta 20 Engineer workers en paralelo con `Agent(..., run_in_background=true)`.
  2. Cada worker recibe un **rol específico**, el **contexto del área/feature** que debe implementar y un **feature focus** claro; no son genéricos.
  3. Cada worker implementa su task en un git worktree aislado.
  4. Polling con `TaskOutput` hasta que todos terminen.
  5. QA-Agent revisa el batch completo (diff combinado + tests).
  6. Si QA aprueba: cherry-pick al trunk y destruir worktrees.
  7. Si QA rechaza: reintentos individuales o replanificación.
- Actualizar `progress.txt` después de cada batch.

### Fase 5 — Integration & Close
- Verificación final de todo el PRD.
- Generación de reporte consolidado.
- Marcar `prd.json` como completo y emitir `COMPLETE`.

## Estructura en el Proyecto

```
scripts/meta-ralph/
├── prd.json              # Fuente de verdad (creado por usuario)
├── prd-expanded.json     # Generado por PM-Agent (Fase 1)
├── architecture.md       # Generado por Architect-Agent (Fase 2)
├── execution-plan.json   # Generado por PMgr-Agent (Fase 3)
├── progress.txt          # Log de ejecución
├── archive/              # Ejecuciones anteriores
└── state/
    ├── board.json        # Estado del dashboard Kanban
    ├── pm-research/      # Notas de los PM Research Agents (Fase 1)
    ├── workers/          # Metadatos de workers activos
    └── batches/          # Resultados por batch
```

## Reglas de Oro

1. **Un agente = un rol**. Nunca mezclar responsabilidades de PM/Architect/Engineer en el mismo prompt.
2. **PM Research Agents en paralelo**. Durante la Fase 1, lanzar hasta 20 PM agents en paralelo para investigar distintas áreas; consolidar antes de generar `prd-expanded.json`.
3. **Cada Engineer tiene contexto propio**. En la Fase 4, cada worker debe recibir un rol, contexto de área y feature focus definidos; evitar workers genéricos.
4. **Workers aislados**. Cada Engineer trabaja en su propio git worktree y su propia branch.
5. **Merge solo después de QA**. Nunca mergear al trunk sin revisión de QA-Agent.
6. **Máximo 20 workers**. El default es 20 para PM research y para Engineers; reducir si hay rate limits o tamaño de batch pequeño.
7. **Replanificación inteligente**. Si un batch falla QA, el PMgr-Agent decide si retry individual, replanificación o escalación.
8. **Sincronizar board.json**. El Orchestrator debe mantener `state/board.json` alineado con el estado real de cada ticket.
9. **Actualizar AGENTS.md**. Si se descubren patrones reusable, actualizar los AGENTS.md correspondientes.

## Referencias Detalladas

- SOPs por rol: [`references/metagpt-roles.md`](references/metagpt-roles.md)
- Prompt template para Engineers: [`references/worker-prompt-template.md`](references/worker-prompt-template.md)
- Prompt template para QA: [`references/qa-prompt-template.md`](references/qa-prompt-template.md)
- Prompt del Orchestrator: [`references/orchestrator-prompt.md`](references/orchestrator-prompt.md)
- Dashboard: [`dashboard/`](dashboard/)
- Formato de PRD extendido: [`assets/prd-template.json`](assets/prd-template.json)

## Seguridad

- Todos los scripts ejecutan código local. Revisa el PRD antes de correr.
- Usa `--yolo` con precaución.
- Trabaja siempre en una branch dedicada (`meta-ralph/*`).
