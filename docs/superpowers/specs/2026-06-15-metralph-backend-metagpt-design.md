# Spec: Backend MetaGPT-style para meta-ralph — Fase 1

## 1. Objetivo

Reestructurar el backend de meta-ralph para que deje de ser un `server.py` monolítico y adopte los patrones clave de MetaGPT que aportan valor sin arrastrar dependencias pesadas:

- `Message` como unidad de comunicación entre agentes.
- `Role` + `Action` para modelar agentes y sus capacidades.
- `Memory` indexada por acción/rol para audit trail y contexto.
- `Environment` como bus de mensajes.
- `Plan` con DAG de tareas.
- `ToolRegistry` para registrar herramientas usables por los agentes.
- `RepoParser` AST para dar contexto del codebase a los agentes.
- `Orchestrator` que coordine el loop multi-agente y sea independiente de Flask.

Skills preinstaladas y MCPs quedan **fuera del alcance de este spec**; se tratarán en fases posteriores sobre esta base.

## 2. Principios de diseño

1. **Mínimas dependencias.** No usar MetaGPT como librería. Reimplementar solo lo necesario con la stdlib y Flask.
2. **Separación de concerns.** `server.py` solo expone REST/WebSocket. La orquestación vive en `core/`.
3. **Backward compatible.** El board, `run-state.json` y el dashboard continuarán funcionando con los mismos endpoints y UI.
4. **Incremental.** Cada componente se puede mergear y probar por separado.

## 3. Arquitectura propuesta

```text
dashboard/
├── server.py                 # Flask + SocketIO, delega todo a core
├── core/                     # Nuevo: lógica de orquestación
│   ├── __init__.py
│   ├── models.py             # Message, Role, Action, Plan, Task
│   ├── memory.py             # Memory indexada por cause_by/role
│   ├── environment.py        # Bus de mensajes + dispatcher
│   ├── registry.py           # ToolRegistry
│   ├── repo_parser.py        # RepoParser AST
│   └── orchestrator.py       # Reemplaza la lógica de AgentRunner
├── roles/                    # Nuevo: definiciones de roles
│   ├── __init__.py
│   ├── base.py               # Role base
│   ├── pm_research.py
│   ├── architect.py
│   ├── planner.py
│   ├── engineer.py
│   └── qa.py
├── actions/                  # Nuevo: acciones reutilizables
│   ├── __init__.py
│   ├── base.py               # Action base
│   ├── research.py
│   ├── design.py
│   ├── implement.py
│   └── review.py
├── tools/                    # Nuevo: tools registradas
│   ├── __init__.py
│   ├── file_tool.py
│   ├── shell_tool.py
│   └── git_tool.py
└── static/                   # UI existente (sin cambios grandes)
```

## 4. Componentes

### 4.1 `Message`

Dataclass mínima inspirada en MetaGPT:

```python
@dataclass
class Message:
    id: str
    content: str
    role: str           # user / assistant / system
    cause_by: str       # id de la acción/rol que lo generó
    sent_from: str      # id del agente emisor
    send_to: Set[str]   # destinatarios; {"all"} = broadcast
    metadata: Dict[str, Any]
    created_at: str     # ISO 8601
```

Responsabilidades:
- Serializar a dict para `run-state.json`.
- Servir como evento en el `Environment`.

### 4.2 `Role`

```python
class Role(ABC):
    role_id: str
    profile: str
    goal: str
    constraints: str
    actions: List[Action]
    memory: Memory
    addresses: Set[str]

    async def observe(self, env: Environment) -> List[Message]: ...
    async def think(self) -> Optional[Action]: ...
    async def act(self, action: Action, context: List[Message]) -> Message: ...
    async def run(self, env: Environment) -> Optional[Message]: ...
```

Responsabilidades:
- Observar mensajes del `Environment` que le correspondan.
- Elegir una `Action`.
- Ejecutarla y publicar el resultado.

Roles concretos:
- `PMResearchRole`: investiga un área y genera notas.
- `PMLeadRole`: consolida investigaciones en PRD.
- `ArchitectRole`: define patrones técnicos.
- `PlannerRole`: genera `Plan` con tareas y dependencias.
- `EngineerRole`: implementa una tarea.
- `QARole`: revisa un batch.
- `OrchestratorRole`: coordina fases.

### 4.3 `Action`

```python
class Action(ABC):
    action_id: str
    name: str
    desc: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]

    async def run(self, context: List[Message], **kwargs) -> Message: ...
```

Responsabilidades:
- Encapsular un paso atómico (ej. "investigar dominio", "generar PRD", "implementar tarea").
- Construir el prompt para `kimi` o ejecutar una tool.
- Devolver un `Message` con el resultado.

Acciones concretas:
- `ResearchAction`
- `ConsolidatePRDAction`
- `ArchitectAction`
- `PlanAction`
- `ImplementAction`
- `ReviewAction`

### 4.4 `Memory`

```python
class Memory:
    messages: List[Message]
    index_by_cause: Dict[str, List[Message]]
    index_by_role: Dict[str, List[Message]]

    def add(self, msg: Message): ...
    def get(self, k: int = 0) -> List[Message]: ...
    def get_by_cause(self, cause: str) -> List[Message]: ...
    def get_by_role(self, role: str) -> List[Message]: ...
    def recent_context(self, n: int = 10) -> List[Message]: ...
```

Responsabilidades:
- Almacenar el historial de mensajes del `Environment`.
- Indexar por `cause_by` y `sent_from` para que los roles filtren rápido.
- Persistirse en `run-state.json` bajo `messages`.

### 4.5 `Environment`

```python
class Environment:
    roles: Dict[str, Role]
    memory: Memory
    message_queue: Queue

    def add_role(self, role: Role): ...
    def publish_message(self, msg: Message): ...
    def get_messages_for(self, role_id: str) -> List[Message]: ...
    async def run_round(self) -> bool: ...  # True si hubo actividad
    def is_idle(self) -> bool: ...
```

Responsabilidades:
- Recibir mensajes de los roles.
- Entregar a cada rol los mensajes que le corresponden (`send_to` o `addresses`).
- Ejecutar rondas hasta que todos los roles estén idle.
- Exponer `history` para el dashboard.

### 4.6 `Plan`

```python
@dataclass
class Task:
    task_id: str
    instruction: str
    assignee: str       # role_id
    dependencies: List[str]
    status: str         # pending | ready | running | done | failed
    result: Optional[Message]

class Plan:
    goal: str
    tasks: List[Task]
    task_map: Dict[str, Task]

    def add_tasks(self, tasks: List[Task]): ...
    def ready_tasks(self) -> List[Task]: ...
    def finish_task(self, task_id: str, result: Message): ...
    def is_finished(self) -> bool: ...
    def reset_downstream(self, task_id: str): ...
```

Responsabilidades:
- Representar el DAG de tareas.
- Permitir ejecución paralela de tareas listas.
- Serializar a `execution-plan.json` / `tasks-<ticket>.json`.

### 4.7 `ToolRegistry`

```python
class ToolRegistry:
    tools: Dict[str, Callable]
    schemas: Dict[str, Dict[str, Any]]

    def register(self, name: str, fn: Callable, schema: Dict[str, Any]): ...
    def get(self, name: str) -> Callable: ...
    def list(self) -> List[Dict[str, Any]]: ...
    async def invoke(self, name: str, params: Dict[str, Any]) -> Any: ...
```

Responsabilidades:
- Registrar funciones Python como tools.
- Exponer schemas al LLM (inicialmente en prompts planos).
- Servir de base para integrar MCPs en fases posteriores.

Tools iniciales:
- `read_file(path)`
- `write_file(path, content)`
- `run_shell(command, cwd)`
- `git_status(cwd)`
- `git_diff(cwd)`

### 4.8 `RepoParser`

```python
class RepoParser:
    root_path: Path

    def generate_symbols(self) -> List[Symbol]: ...
    def get_structure(self) -> Dict[str, Any]: ...
```

Responsabilidades:
- Usar `ast` de la stdlib para extraer clases, funciones, métodos y relaciones.
- Generar un resumen JSON que se inyecte en los prompts de arquitecto/ingeniero.
- No depender de `pylint` ni `pyreverse`.

### 4.9 `Orchestrator`

```python
class Orchestrator:
    ticket: Dict[str, Any]
    env: Environment
    plan: Optional[Plan]
    state: Dict[str, Any]

    async def run(self): ...
    async def run_phase(self, phase: str): ...
    def pause(self): ...
    def resume(self): ...
    def stop(self): ...
    def to_run_state(self) -> Dict[str, Any]: ...
```

Responsabilidades:
- Reemplazar `AgentRunner`.
- Crear roles, acciones y plan según la fase.
- Ejecutar el loop de rondas del `Environment`.
- Persistir estado en `run-state.json` y snapshots.
- Emitir actualizaciones al dashboard vía callback o SocketIO.

## 5. Data flow

1. Usuario da **play** a un ticket.
2. `server.py` llama a `Orchestrator.run(ticket)`.
3. `Orchestrator` crea un `Environment` y añade el rol `OrchestratorRole`.
4. `OrchestratorRole` publica mensaje "iniciar fase 1".
5. `PMResearchRole`s observan, ejecutan `ResearchAction` en paralelo y publican notas.
6. `PMLeadRole` consolida notas con `ConsolidatePRDAction`.
7. El proceso continúa por fases: Architect → Planner → Engineers (paralelos por batch) → QA.
8. Cada cambio de fase actualiza `run-state.json` y el dashboard refleja progreso.

## 6. Refactor de `server.py`

`server.py` debe quedar como una capa delgada:

- Carga/guarda `board.json` y `run-state.json`.
- Expone endpoints REST y WebSocket.
- Mantiene el thread del `Orchestrator` activo.
- Delega toda la lógica de agentes a `core/`.

No debe contener prompts, lógica de fases ni llamadas a `kimi`. Eso vive en `roles/` y `actions/`.

## 7. Persistencia

- `board.json`: sin cambios de schema.
- `run-state.json`: se mantiene como fuente de verdad del dashboard.
  - `messages` pasa a ser la serialización de `Memory`.
  - `agents` refleja los roles activos.
  - `plan` opcional con el DAG actual.
- Snapshots: se mantienen como `run-state.<ticketId>.json` (funcionalidad ya implementada).

## 8. Integración con dashboard (frontend)

- Sin cambios de API en un primer momento: `/api/run-state`, `/api/board`, WebSocket.
- Futuro: añadir endpoint `/api/tools` para listar tools registradas.
- Futuro: añadir endpoint `/api/repo-structure?path=...` para el RepoParser.

## 9. Error handling

- Si un `Role` falla, publica un mensaje de error con `level=error`.
- `Orchestrator` decide: retry, replanificar o marcar ticket como `failed`.
- Límite de reintentos por acción (default 3).
- Timeout por acción (default 30 min).

## 10. Testing plan

- Tests unitarios para `Message`, `Memory`, `Plan`, `ToolRegistry`.
- Tests de integración para `Environment` con roles dummy.
- Test end-to-end: crear ticket de prueba, ejecutar `Orchestrator` con acciones mockeadas, verificar `run-state.json`.

## 11. Entregables

1. Nuevo paquete `dashboard/core/` con modelos, memory, environment, registry, repo_parser y orchestrator.
2. Nuevo paquete `dashboard/roles/` con roles concretos.
3. Nuevo paquete `dashboard/actions/` con acciones concretas.
4. Nuevo paquete `dashboard/tools/` con tools iniciales.
5. `server.py` refactorizado a capa delgada.
6. Tests básicos.
7. Documentación de arquitectura.

## 12. Qué queda fuera de este spec

- Skills preinstaladas de Kimi (`dotnet`, `ui`, `code-review`, etc.).
- Integración con servidores MCP.
- UI avanzada del dashboard.
- Vector search / RAG.
- Cambios en el CLI `meta-ralph.sh`.
