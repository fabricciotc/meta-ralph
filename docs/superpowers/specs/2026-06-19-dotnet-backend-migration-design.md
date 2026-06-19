# Migración del backend a .NET 10 con Semantic Kernel

## Resumen ejecutivo

Reescribir el backend Python actual (`dashboard/server.py` + `dashboard/core/`) en **.NET 10** usando **ASP.NET Core**, **SignalR** y **Semantic Kernel** como librería de orquestación de agentes. El frontend Tauri y la UI vanilla JS se mantienen, pero se reubican dentro del proyecto BFF en `AgenticFlow.Bff/Frontend/`. El backend se organiza en una arquitectura **BFF + Clean Architecture** con cuatro capas: `Bff`, `Application`, `Domain` y `Persistence`.

## Contexto

El backend actual consta de:

- `dashboard/server.py` (~4.500 líneas): Flask + Flask-SocketIO que expone la API REST, sirve la UI estática y gestiona el estado.
- `dashboard/core/` (~8.000 líneas): motor MetaGPT con orquestador, entorno, planificador, roles, acciones, runners de IA, memoria, contexto y registro de skills.
- `dashboard/static/`: frontend vanilla JS consumido por el webview de Tauri.
- `src-tauri/src/main.rs`: host Tauri que lanza el binario Python como sidecar en `127.0.0.1:5051`.

## Objetivos

1. Replicar la API REST y los eventos en tiempo real actuales sin cambiar el contrato del frontend.
2. Conservar toda la lógica de negocio del motor MetaGPT (fases, roles, acciones, runners).
3. Usar Semantic Kernel para envolver la invocación de LLMs y modelar plugins/agentes donde sea natural.
4. Soportar macOS, Windows y Linux mediante publicación self-contained del sidecar .NET.
5. Mantener la compatibilidad con los archivos JSON existentes (`board.json`, `run-state.json`, snapshots, `config.json`).

## Decisiones de arquitectura

### Stack tecnológico

| Componente | Tecnología | Motivo |
|------------|------------|--------|
| Runtime | .NET 10 (`net10.0`) | Última versión solicitada por el usuario; LTS no es requisito. |
| Web framework | ASP.NET Core | Nativo, multiplataforma, alto rendimiento. |
| Estilo API | Minimal APIs + Controllers | Minimal APIs para endpoints simples; Controllers para agrupar lógica de módulos grandes (tickets, config, system). |
| Tiempo real | SignalR | Reemplazo directo de Socket.IO con soporte nativo en .NET y clientes JavaScript. |
| Agentes/IA | Semantic Kernel | Framework de Microsoft para plugins, kernel functions y orquestación de agentes. |
| Serialización | `System.Text.Json` | Compatible con los esquemas JSON actuales. |
| Logging | `Microsoft.Extensions.Logging` + archivo | Reemplaza logging de Flask. |
| DI/IoC | Contenedor integrado de ASP.NET Core | Registro de repositorios, servicios, runners, hubs. |

### Arquitectura de capas

```
AgenticFlow/
├── src/
│   ├── AgenticFlow.Bff/              # ASP.NET Core: controllers, SignalR, DTOs, Tauri sidecar config
│   │   └── Frontend/                 # Tauri + frontend vanilla JS (movido desde dashboard/static/)
│   ├── AgenticFlow.Application/      # Casos de uso, Semantic Kernel, roles, acciones, orquestador, runners
│   ├── AgenticFlow.Domain/           # Entidades, value objects, eventos, excepciones puras
│   └── AgenticFlow.Persistence/      # Lectura/escritura JSON, paths multiplataforma, snapshots
├── tests/                            # xUnit: domain, application, persistence, integration
└── scripts/                          # build-sidecar.sh, publish para osx/win/linux
```

#### Responsabilidades

- **AgenticFlow.Bff**
  - Expone endpoints REST (`/api/*`) equivalentes a los de Flask.
  - Expone `DashboardHub` de SignalR para eventos en tiempo real.
  - Sirve archivos estáticos del frontend en desarrollo.
  - Configura Tauri para lanzar el ejecutable .NET como sidecar.
  - Mapea DTOs a modelos de dominio y viceversa.

- **AgenticFlow.Application**
  - Contiene la lógica de negocio: orquestador, entorno, planificador, roles, acciones.
  - Implementa los runners de IA usando Semantic Kernel.
  - Define abstracciones (`ITicketService`, `IOrchestrator`, `IAIRunner`, etc.).
  - Contiene utilitarios: `chat_formatter`, parsers, registro de skills.

- **AgenticFlow.Domain**
  - Modelos puros: `Ticket`, `Message`, `Task`, `Plan`, `Role`, `BackendInfo`, eventos de dominio.
  - Excepciones de dominio (`DomainException`, `OrchestratorException`, `AIRunnerException`).
  - Sin dependencias de infraestructura ni frameworks.

- **AgenticFlow.Persistence**
  - Implementa `IBoardStore`, `IRunStateStore`, `IConfigStore`, `ISnapshotStore`.
  - Maneja paths multiplataforma (`Environment.SpecialFolder`, `Path.Combine`).
  - Serialización/deserialización JSON con compatibilidad hacia los archivos Python.

## Estructura de proyectos propuesta

```
src/
├── AgenticFlow.Bff/
│   ├── Program.cs
│   ├── AgenticFlow.Bff.csproj
│   ├── appsettings.json
│   ├── Controllers/
│   │   ├── TicketsController.cs
│   │   ├── BoardController.cs
│   │   ├── ConfigController.cs
│   │   ├── SystemInfoController.cs
│   │   ├── QuestionsController.cs
│   │   ├── DesignReviewController.cs
│   │   └── FilesController.cs
│   ├── Hubs/
│   │   └── DashboardHub.cs
│   ├── Models/
│   │   ├── TicketDto.cs
│   │   ├── BoardDto.cs
│   │   └── ...
│   ├── Mapping/
│   │   └── MappingProfile.cs
│   └── Frontend/
│       ├── src-tauri/
│       ├── src/
│       ├── index.html
│       └── ...
├── AgenticFlow.Application/
│   ├── AgenticFlow.Application.csproj
│   ├── Abstractions/
│   │   ├── ITicketService.cs
│   │   ├── IOrchestrator.cs
│   │   ├── IEnvironment.cs
│   │   ├── IPlanEngine.cs
│   │   ├── IMemoryStore.cs
│   │   ├── IContext.cs
│   │   ├── IAIRunner.cs
│   │   ├── IBackendRegistry.cs
│   │   ├── ISkillRegistry.cs
│   │   └── IEventBus.cs
│   ├── Services/
│   │   ├── TicketService.cs
│   │   ├── SystemInfoService.cs
│   │   └── FileService.cs
│   ├── Orchestration/
│   │   ├── Orchestrator.cs
│   │   ├── Environment.cs
│   │   ├── PlanEngine.cs
│   │   └── BatchScheduler.cs
│   ├── Roles/
│   │   ├── Role.cs
│   │   ├── PMResearchRole.cs
│   │   ├── PMLeadRole.cs
│   │   ├── ArchitectRole.cs
│   │   ├── PlannerRole.cs
│   │   ├── EngineerRole.cs
│   │   ├── EngineerSquadRole.cs
│   │   ├── QARole.cs
│   │   ├── DispatcherRole.cs
│   │   ├── MonitorRole.cs
│   │   ├── RecoveryRole.cs
│   │   ├── TeamLeaderRole.cs
│   │   ├── SwarmLeaderRole.cs
│   │   └── AggregatorRole.cs
│   ├── Actions/
│   │   ├── Action.cs
│   │   ├── ResearchAction.cs
│   │   ├── ConsolidatePrdAction.cs
│   │   ├── ArchitectAction.cs
│   │   ├── DesignReviewAction.cs
│   │   ├── PlanAction.cs
│   │   ├── ImplementAction.cs
│   │   ├── ReviewAction.cs
│   │   └── CorrectionAction.cs
│   ├── Runners/
│   │   ├── AIRunner.cs
│   │   ├── BackendRegistry.cs
│   │   ├── KimiCliRunner.cs
│   │   ├── ClaudeCodeRunner.cs
│   │   ├── CursorCliRunner.cs
│   │   ├── CodexCliRunner.cs
│   │   ├── CopilotCliRunner.cs
│   │   ├── OpenAiApiRunner.cs
│   │   └── ChatFormatter.cs
│   ├── Agents/
│   │   └── SemanticKernelAgentFactory.cs
│   ├── Skills/
│   │   ├── SkillRegistry.cs
│   │   └── role_skills_registry.yaml
│   └── Common/
│       ├── RepoParser.cs
│       └── PathExtensions.cs
├── AgenticFlow.Domain/
│   ├── AgenticFlow.Domain.csproj
│   ├── Entities/
│   │   ├── Ticket.cs
│   │   ├── Message.cs
│   │   ├── Task.cs
│   │   ├── Plan.cs
│   │   └── RoleState.cs
│   ├── ValueObjects/
│   │   ├── BackendId.cs
│   │   └── SkillPrefix.cs
│   ├── Events/
│   │   ├── TicketStartedEvent.cs
│   │   ├── PhaseCompletedEvent.cs
│   │   └── MessagePublishedEvent.cs
│   └── Exceptions/
│       ├── DomainException.cs
│       ├── OrchestratorException.cs
│       └── AIRunnerException.cs
└── AgenticFlow.Persistence/
    ├── AgenticFlow.Persistence.csproj
    ├── DependencyInjection.cs
    ├── Repositories/
    │   ├── BoardStore.cs
    │   ├── RunStateStore.cs
    │   ├── ConfigStore.cs
    │   └── SnapshotStore.cs
    ├── JsonStores/
    │   └── JsonFileStore.cs
    └── FileSystem/
        └── AppDataPathProvider.cs
```

## Mapeo de módulos Python a .NET

| Python | .NET (capa/proyecto) | Notas |
|--------|----------------------|-------|
| `dashboard/server.py` | `AgenticFlow.Bff` (controllers + hub) | Portar endpoints y eventos Socket.IO → SignalR. |
| `dashboard/launcher.py` | `src-tauri/src/main.rs` + scripts | Sidecar .NET en lugar de binario Python. |
| `dashboard/communication_bus.py` | `IEventBus` + `DashboardHub` | Publicación de eventos y envío al frontend. |
| `core/paths.py` | `AppDataPathProvider` | Paths multiplataforma. |
| `core/config.py` | `ConfigStore` + `IConfiguration` | Configuración unificada. |
| `core/models.py` | `AgenticFlow.Domain/Entities` | `Message`, `Ticket`, etc. |
| `core/memory.py` | `IMemoryStore` + implementación en memoria | Índices por cause/role/type/recipient. |
| `core/context.py` | `IContext` | Contexto compartido con callbacks y registries. |
| `core/orchestrator.py` | `Orchestrator` | Ciclo de 5 fases, pause/resume/stop, snapshots. |
| `core/environment.py` | `Environment` | Contenedor de roles + cola + scheduler. |
| `core/plan.py` | `PlanEngine` + `BatchScheduler` | Grafo de tareas y scheduling topológico. |
| `core/pm_analysis.py` | `PMResearchRole`, `PMLeadRole`, `ResearchAction` | Análisis PM y PRD. |
| `core/roles/*` | `AgenticFlow.Application/Roles` | 14 roles migrados. |
| `core/actions/*` | `AgenticFlow.Application/Actions` | 8 acciones migradas. |
| `core/runners/*` | `AgenticFlow.Application/Runners` | Adaptadores de IA con Semantic Kernel. |
| `core/ai_execution.py` | `AIRunner` / `SemanticKernelAgentFactory` | Wrapper de invocación. |
| `core/chat_formatter.py` | `ChatFormatter` | Limpieza de salida CLI. |
| `core/repo_parser.py` | `RepoParser` | Parser genérico + Roslyn para C# si aplica. |
| `core/skills_registry.py` | `SkillRegistry` | YAML de skills e inyección de prefijos. |

## Flujo de datos

1. El frontend (Tauri/webview) invoca `POST /api/tickets/{id}/play`.
2. `TicketsController` valida el DTO y delega a `ITicketService.PlayAsync(id)`.
3. `TicketService` carga el ticket desde `ITicketRepository`, crea el `Orchestrator` y lanza el ciclo.
4. `Orchestrator` ejecuta las fases usando `IEnvironment`, `IPlanEngine`, roles y acciones.
5. Los runners invocan Semantic Kernel con el backend de IA seleccionado.
6. Los resultados se convierten en `Message` del dominio y se publican mediante `IEventBus`.
7. `DashboardHub` recibe los eventos y los envía al frontend por SignalR.
8. `Persistence` guarda `board.json`, `run-state.json` y snapshots en puntos determinados.

## API REST y SignalR

### Endpoints REST (compatibles con frontend actual)

- `GET /api/board`
- `GET /api/run-state`
- `POST /api/tickets`, `PATCH /api/tickets/{id}`, `DELETE /api/tickets/{id}`
- `POST /api/tickets/{id}/play`, `/restart`, `/pause`
- `GET /api/system-info`, `GET /api/backends`, `POST /api/backends/select`
- `GET /api/config`, `PATCH /api/config`
- `GET /api/questions`, `POST /api/questions/{id}/answer`
- `GET /api/design-review`, `POST /api/design-review/answer`
- `POST /api/pick-folder`, `POST /api/open-path`, `POST /api/read-file`
- `GET /api/traces`, `GET /api/graph`
- `POST /api/client-log`, `POST /api/client-beacon`

### Eventos SignalR

Mapeo directo de los eventos Socket.IO actuales:

- `connect`, `request_update`, `chat_send`
- `status_update`, `trace`, `question`, `design_review`

## Multiplataforma y empaquetado

- Publicación self-contained para cada plataforma:
  - macOS: `osx-x64`, `osx-arm64`
  - Windows: `win-x64`
  - Linux: `linux-x64`
- Comando ejemplo:
  ```bash
  dotnet publish src/AgenticFlow.Bff/AgenticFlow.Bff.csproj \
     -c Release -r osx-arm64 --self-contained true \
     -p:PublishSingleFile=true -o dist/macos
  ```
- Tauri `src-tauri/src/main.rs` se actualiza para lanzar el binario .NET del sidecar.
- `Info.plist`, `.desktop` y recursos de Tauri se mantienen en `AgenticFlow.Bff/Frontend/src-tauri/`.

## Manejo de errores

- Excepciones de dominio (`DomainException`) traducidas a `ProblemDetails` HTTP.
- Errores de IA (`AIRunnerException`) con reintentos y fallback al siguiente backend disponible.
- Errores de orquestación persisten snapshot parcial para permitir `resume`.
- Logs en `~/AgenticFlow/logs/dotnet-backend.log` mediante `Microsoft.Extensions.Logging`.

## Testing

- **Domain:** xUnit puro para entidades y reglas.
- **Application:** tests con mocks de repositorios y `FakeAIClient`.
- **Bff:** integration tests con `WebApplicationFactory` para REST y SignalR.
- **Persistence:** tests de lectura/escritura JSON en directorios temporales.
- Los tests existentes de `dashboard/tests/` se reescriben como contratos de comportamiento.

## Plan de agentes paralelos

| # | Módulo | Responsabilidad | Proyectos |
|---|--------|-----------------|-----------|
| 1 | **Bff + Hosting** | Crear solución .NET 10, proyectos, `Program.cs`, controllers, SignalR hub, static files, Tauri sidecar config. | `AgenticFlow.Bff` |
| 2 | **Persistence** | Stores JSON, paths multiplataforma, snapshots. | `AgenticFlow.Persistence` |
| 3 | **Domain** | Entidades, value objects, eventos, excepciones. | `AgenticFlow.Domain` |
| 4 | **AI Runners** | Adaptadores Semantic Kernel para Kimi, Claude, Cursor, Codex, Copilot, OpenAI API, registry, chat formatter. | `AgenticFlow.Application` |
| 5 | **Orchestrator + Environment + Planning** | Migrar `orchestrator.py`, `environment.py`, `plan.py`. | `AgenticFlow.Application` |
| 6 | **PM + Architect + Design Review** | Roles y acciones de PM research, PM lead, architect, design review. | `AgenticFlow.Application` |
| 7 | **Engineer + Squad + Implementation** | Engineer, EngineerSquad, ImplementAction, CorrectionAction, git worktree helpers. | `AgenticFlow.Application` |
| 8 | **QA + Review + Support Roles** | QA, Review, Dispatcher, Monitor, Recovery, TeamLeader, SwarmLeader, Aggregator. | `AgenticFlow.Application` |
| 9 | **Memory + Context + Skills** | `IMemoryStore`, `Context`, skills registry YAML, prompt injection. | `AgenticFlow.Application` |
| 10 | **Communication Bus + Integration** | `IEventBus`, mapeo de eventos a SignalR, adaptación de `communication_bus.py`, integración end-to-end. | `Bff` + `Application` |

### Dependencias entre agentes

1. Los agentes 1, 2 y 3 son la base. Se entregan primero.
2. Los agentes 4-9 dependen de `Domain` y `Persistence`. Pueden correr en paralelo una vez lista la base.
3. El agente 10 corre al final, cuando los contratos de eventos sean estables.

## Notas de implementación

- Mantener los nombres de propiedades JSON existentes usando `[JsonPropertyName]` donde sea necesario para compatibilidad con archivos del backend Python.
- Semantic Kernel se usa como librería; no se fuerza el modelo de `AgentGroupChat` si dificulta conservar el ciclo `_watch → _think → _act` del motor MetaGPT.
- El frontend vanilla JS se mueve de `dashboard/static/` a `AgenticFlow.Bff/Frontend/`, pero su código se mantiene con los ajustes mínimos necesarios (URL de SignalR, endpoints).
- La rama de trabajo será `feature/dotnet-backend`.

## Referencias

- Backend actual: `dashboard/server.py`, `dashboard/core/`, `dashboard/static/`, `src-tauri/src/main.rs`.
- Diseños previos relacionados:
  - `docs/superpowers/specs/2026-06-15-metralph-backend-metagpt-design.md`
  - `docs/superpowers/specs/2026-06-16-ai-runner-swarm-portability-design.md`
