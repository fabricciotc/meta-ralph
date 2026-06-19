# Migración del backend a .NET 10 con Semantic Kernel - Plan Maestro

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reescribir el backend Python actual (`dashboard/server.py` + `dashboard/core/`) en .NET 10 con ASP.NET Core, SignalR y Semantic Kernel, manteniendo el frontend Tauri y toda la lógica de negocio, usando una arquitectura BFF + Clean Architecture.

**Architecture:** El backend se organiza en cuatro proyectos: `AgenticFlow.Bff` (REST + SignalR + frontend Tauri), `AgenticFlow.Application` (lógica de negocio + Semantic Kernel), `AgenticFlow.Domain` (modelos puros) y `AgenticFlow.Persistence` (JSON + paths multiplataforma). Cada uno de los 10 módulos se migra por un agente independiente sobre contratos compartidos.

**Tech Stack:** .NET 10, ASP.NET Core, SignalR, Semantic Kernel, System.Text.Json, xUnit, Tauri.

---

## Fase 0: Preparación y estructura base

> **Nota:** Esta fase debe completarse antes de lanzar los 10 agentes en paralelo. Define los contratos, la rama y la solución base.

### Task 0.1: Crear rama de trabajo

**Files:**
- Modifica: `.git/HEAD` (implícito)

- [ ] **Step 1: Crear y checkout rama `feature/dotnet-backend`**

```bash
cd /Users/fabricciotornero/AgenticFlow
git checkout -b feature/dotnet-backend
```

Expected: Rama creada y activa.

- [ ] **Step 2: Verificar estado limpio**

```bash
git status
```

Expected: "nothing to commit, working tree clean" o solo cambios esperados.

---

### Task 0.2: Verificar/instalar .NET 10 SDK

**Files:**
- Modifica: `global.json` (create)

- [ ] **Step 1: Verificar versión instalada**

```bash
dotnet --version
```

Expected: `10.0.xxx` o superior.

- [ ] **Step 2: Si no está instalado, instalar .NET 10 SDK**

macOS (brew):
```bash
brew install dotnet-sdk
```

Linux:
```bash
wget https://dot.net/v1/dotnet-install.sh -O dotnet-install.sh
chmod +x dotnet-install.sh
./dotnet-install.sh --channel 10.0
```

Windows: descargar desde https://dotnet.microsoft.com/download/dotnet/10.0

- [ ] **Step 3: Crear `global.json` para fijar SDK**

Create: `global.json`

```json
{
  "sdk": {
    "version": "10.0.100",
    "rollForward": "latestFeature"
  }
}
```

- [ ] **Step 4: Verificar**

```bash
dotnet --version
```

Expected: `10.0.xxx`.

---

### Task 0.3: Crear solución y proyectos base

**Files:**
- Create: `AgenticFlow.sln`
- Create: `src/AgenticFlow.Bff/AgenticFlow.Bff.csproj`
- Create: `src/AgenticFlow.Application/AgenticFlow.Application.csproj`
- Create: `src/AgenticFlow.Domain/AgenticFlow.Domain.csproj`
- Create: `src/AgenticFlow.Persistence/AgenticFlow.Persistence.csproj`

- [ ] **Step 1: Crear solución en la raíz**

```bash
cd /Users/fabricciotornero/AgenticFlow
dotnet new sln -n AgenticFlow
```

- [ ] **Step 2: Crear proyectos**

```bash
mkdir -p src
cd src

dotnet new web -n AgenticFlow.Bff -f net10.0
dotnet new classlib -n AgenticFlow.Application -f net10.0
dotnet new classlib -n AgenticFlow.Domain -f net10.0
dotnet new classlib -n AgenticFlow.Persistence -f net10.0
```

- [ ] **Step 3: Agregar referencias entre proyectos**

```bash
cd /Users/fabricciotornero/AgenticFlow/src

dotnet add AgenticFlow.Bff reference AgenticFlow.Application AgenticFlow.Persistence
dotnet add AgenticFlow.Application reference AgenticFlow.Domain
dotnet add AgenticFlow.Persistence reference AgenticFlow.Domain
```

- [ ] **Step 4: Agregar proyectos a la solución**

```bash
cd /Users/fabricciotornero/AgenticFlow
dotnet sln add src/AgenticFlow.Bff/AgenticFlow.Bff.csproj
dotnet sln add src/AgenticFlow.Application/AgenticFlow.Application.csproj
dotnet sln add src/AgenticFlow.Domain/AgenticFlow.Domain.csproj
dotnet sln add src/AgenticFlow.Persistence/AgenticFlow.Persistence.csproj
```

- [ ] **Step 5: Build inicial**

```bash
cd /Users/fabricciotornero/AgenticFlow
dotnet build
```

Expected: Build succeeds.

- [ ] **Step 6: Commit**

```bash
git add global.json AgenticFlow.sln src/
git commit -m "chore: create .NET 10 solution with Bff, Application, Domain, Persistence"
```

---

### Task 0.4: Definir contratos base (Domain + abstracciones iniciales)

**Files:**
- Create: `src/AgenticFlow.Domain/Entities/Message.cs`
- Create: `src/AgenticFlow.Domain/Entities/Ticket.cs`
- Create: `src/AgenticFlow.Domain/Events/IDomainEvent.cs`
- Create: `src/AgenticFlow.Application/Abstractions/IMemoryStore.cs`
- Create: `src/AgenticFlow.Application/Abstractions/IContext.cs`
- Create: `src/AgenticFlow.Application/Abstractions/IEventBus.cs`

> Estos contratos los consumirán todos los agentes. Se implementan de forma mínima, extensible luego.

- [ ] **Step 1: Definir entidad base `Entity`**

Create: `src/AgenticFlow.Domain/Entities/Entity.cs`

```csharp
namespace AgenticFlow.Domain.Entities;

public abstract class Entity
{
    public Guid Id { get; protected set; } = Guid.NewGuid();
}
```

- [ ] **Step 2: Definir `Message`**

Create: `src/AgenticFlow.Domain/Entities/Message.cs`

```csharp
namespace AgenticFlow.Domain.Entities;

public class Message
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string Cause { get; set; } = string.Empty;
    public string Role { get; set; } = string.Empty;
    public string Type { get; set; } = string.Empty;
    public string Recipient { get; set; } = string.Empty;
    public string Content { get; set; } = string.Empty;
    public Dictionary<string, object> Metadata { get; set; } = new();
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
}
```

- [ ] **Step 3: Definir `Ticket` (mínimo)**

Create: `src/AgenticFlow.Domain/Entities/Ticket.cs`

```csharp
namespace AgenticFlow.Domain.Entities;

public class Ticket : Entity
{
    public string Title { get; set; } = string.Empty;
    public string Description { get; set; } = string.Empty;
    public string Status { get; set; } = "pending";
    public Dictionary<string, object> Metadata { get; set; } = new();
}
```

- [ ] **Step 4: Definir abstracciones base**

Create: `src/AgenticFlow.Application/Abstractions/IMemoryStore.cs`

```csharp
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Abstractions;

public interface IMemoryStore
{
    void Add(Message message);
    IReadOnlyList<Message> GetAll();
    IReadOnlyList<Message> GetByCause(string cause);
    IReadOnlyList<Message> GetByRole(string role);
    IReadOnlyList<Message> GetByType(string type);
    IReadOnlyList<Message> GetByRecipient(string recipient);
}
```

Create: `src/AgenticFlow.Application/Abstractions/IContext.cs`

```csharp
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Abstractions;

public interface IContext
{
    Ticket Ticket { get; }
    IMemoryStore Memory { get; }
    CancellationToken CancellationToken { get; }
}
```

Create: `src/AgenticFlow.Application/Abstractions/IEventBus.cs`

```csharp
using AgenticFlow.Domain.Events;

namespace AgenticFlow.Application.Abstractions;

public interface IEventBus
{
    Task PublishAsync(IDomainEvent domainEvent, CancellationToken cancellationToken = default);
}
```

Create: `src/AgenticFlow.Domain/Events/IDomainEvent.cs`

```csharp
namespace AgenticFlow.Domain.Events;

public interface IDomainEvent
{
    Guid EventId { get; }
    DateTimeOffset OccurredOn { get; }
}
```

- [ ] **Step 5: Build**

```bash
cd /Users/fabricciotornero/AgenticFlow
dotnet build
```

Expected: Build succeeds.

- [ ] **Step 6: Commit**

```bash
git add src/AgenticFlow.Domain src/AgenticFlow.Application/Abstractions
git commit -m "feat(domain): add base entities and application abstractions"
```

---

## Fase 1: Módulos base (Agentes 1, 2, 3)

> Estos tres módulos deben completarse antes de lanzar los agentes 4-10. Son la base sobre la cual se construye todo.

### Módulo 1: Bff + Hosting

**Agente asignado:** 1  
**Responsabilidad:** Crear el host ASP.NET Core, controllers, SignalR hub, servir frontend, configurar Tauri sidecar.  
**Proyectos:** `AgenticFlow.Bff`  
**Dependencias:** Módulos 2 y 3 (Domain y Persistence).  
**Contrato con otros módulos:** Expone endpoints REST y eventos SignalR. Consume servicios de Application.

#### Task 1.1: Configurar Program.cs

**Files:**
- Modify: `src/AgenticFlow.Bff/Program.cs`

- [ ] **Step 1: Reemplazar Program.cs por configuración inicial**

```csharp
using AgenticFlow.Application.Abstractions;
using AgenticFlow.Bff.Hubs;
using AgenticFlow.Persistence;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddSignalR();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

builder.Services.AddPersistence(builder.Configuration);
builder.Services.AddSingleton<IEventBus, InMemoryEventBus>();

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseDefaultFiles();
app.UseStaticFiles();
app.UseRouting();
app.MapControllers();
app.MapHub<DashboardHub>("/hub");

app.Run();
```

- [ ] **Step 2: Crear InMemoryEventBus temporal**

Create: `src/AgenticFlow.Bff/Infrastructure/InMemoryEventBus.cs`

```csharp
using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Events;

namespace AgenticFlow.Bff.Infrastructure;

public class InMemoryEventBus : IEventBus
{
    public Task PublishAsync(IDomainEvent domainEvent, CancellationToken cancellationToken = default)
    {
        return Task.CompletedTask;
    }
}
```

- [ ] **Step 3: Build y commit**

```bash
dotnet build
git add src/AgenticFlow.Bff/Program.cs src/AgenticFlow.Bff/Infrastructure
git commit -m "feat(bff): configure ASP.NET Core host with SignalR and static files"
```

#### Task 1.2: Crear DashboardHub

**Files:**
- Create: `src/AgenticFlow.Bff/Hubs/DashboardHub.cs`

- [ ] **Step 1: Implementar hub**

```csharp
using Microsoft.AspNetCore.SignalR;

namespace AgenticFlow.Bff.Hubs;

public class DashboardHub : Hub
{
    public async Task RequestUpdate()
    {
        await Clients.Caller.SendAsync("status_update", new { status = "ok" });
    }

    public async Task ChatSend(string message)
    {
        await Clients.All.SendAsync("chat_message", new { message });
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add src/AgenticFlow.Bff/Hubs/DashboardHub.cs
git commit -m "feat(bff): add DashboardHub with SignalR methods"
```

#### Task 1.3: Mover frontend Tauri a Bff/Frontend

**Files:**
- Create: `src/AgenticFlow.Bff/Frontend/` (mover desde `dashboard/static/` y `src-tauri/`)

- [ ] **Step 1: Crear estructura Frontend**

```bash
cd /Users/fabricciotornero/AgenticFlow
mkdir -p src/AgenticFlow.Bff/Frontend
```

- [ ] **Step 2: Mover archivos estáticos**

```bash
cp -R dashboard/static/* src/AgenticFlow.Bff/Frontend/
cp -R src-tauri src/AgenticFlow.Bff/Frontend/
```

- [ ] **Step 3: Ajustar Tauri para servir desde nuevo path**

Modify: `src/AgenticFlow.Bff/Frontend/src-tauri/tauri.conf.json` (ajustar `distDir` según corresponda).

- [ ] **Step 4: Commit**

```bash
git add src/AgenticFlow.Bff/Frontend
git commit -m "chore(bff): move Tauri frontend into Bff/Frontend"
```

#### Task 1.4: Crear controllers base

**Files:**
- Create: `src/AgenticFlow.Bff/Controllers/BoardController.cs`
- Create: `src/AgenticFlow.Bff/Controllers/TicketsController.cs`
- Create: `src/AgenticFlow.Bff/Controllers/ConfigController.cs`

- [ ] **Step 1: BoardController**

```csharp
using Microsoft.AspNetCore.Mvc;

namespace AgenticFlow.Bff.Controllers;

[ApiController]
[Route("api/[controller]")]
public class BoardController : ControllerBase
{
    [HttpGet]
    public IActionResult GetBoard()
    {
        return Ok(new { tickets = new List<object>() });
    }
}
```

- [ ] **Step 2: TicketsController**

```csharp
using Microsoft.AspNetCore.Mvc;

namespace AgenticFlow.Bff.Controllers;

[ApiController]
[Route("api/[controller]")]
public class TicketsController : ControllerBase
{
    [HttpGet]
    public IActionResult GetTickets() => Ok(new List<object>());

    [HttpPost]
    public IActionResult CreateTicket([FromBody] object ticket) => Ok(new { id = Guid.NewGuid() });

    [HttpPost("{id:guid}/play")]
    public IActionResult Play(Guid id) => Ok(new { status = "started", id });
}
```

- [ ] **Step 3: ConfigController**

```csharp
using Microsoft.AspNetCore.Mvc;

namespace AgenticFlow.Bff.Controllers;

[ApiController]
[Route("api/[controller]")]
public class ConfigController : ControllerBase
{
    [HttpGet]
    public IActionResult GetConfig() => Ok(new { });

    [HttpPatch]
    public IActionResult UpdateConfig([FromBody] object config) => Ok(config);
}
```

- [ ] **Step 4: Build y commit**

```bash
dotnet build
git add src/AgenticFlow.Bff/Controllers
git commit -m "feat(bff): add base API controllers"
```

---

### Módulo 2: Persistence

**Agente asignado:** 2  
**Responsabilidad:** Implementar lectura/escritura JSON multiplataforma para board, run-state, config y snapshots.  
**Proyecto:** `AgenticFlow.Persistence`  
**Dependencias:** Módulo 3 (Domain).  
**Contrato:** Expone `IBoardStore`, `IRunStateStore`, `IConfigStore`, `ISnapshotStore`.

#### Task 2.1: Path provider multiplataforma

**Files:**
- Create: `src/AgenticFlow.Persistence/FileSystem/AppDataPathProvider.cs`

- [ ] **Step 1: Implementar provider**

```csharp
namespace AgenticFlow.Persistence.FileSystem;

public class AppDataPathProvider
{
    private readonly string _basePath;

    public AppDataPathProvider()
    {
        _basePath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "AgenticFlow");

        Directory.CreateDirectory(_basePath);
    }

    public string GetAppDataPath() => _basePath;

    public string GetFilePath(string fileName) => Path.Combine(_basePath, fileName);
}
```

- [ ] **Step 2: Commit**

```bash
git add src/AgenticFlow.Persistence/FileSystem/AppDataPathProvider.cs
git commit -m "feat(persistence): add multiplatform app data path provider"
```

#### Task 2.2: JsonFileStore genérico

**Files:**
- Create: `src/AgenticFlow.Persistence/JsonStores/JsonFileStore.cs`

- [ ] **Step 1: Implementar store genérico**

```csharp
using System.Text.Json;
using AgenticFlow.Persistence.FileSystem;

namespace AgenticFlow.Persistence.JsonStores;

public class JsonFileStore<T> where T : class, new()
{
    private readonly string _filePath;
    private readonly JsonSerializerOptions _options;

    public JsonFileStore(AppDataPathProvider pathProvider, string fileName)
    {
        _filePath = pathProvider.GetFilePath(fileName);
        _options = new JsonSerializerOptions
        {
            WriteIndented = true,
            PropertyNameCaseInsensitive = true
        };
    }

    public T Load()
    {
        if (!File.Exists(_filePath))
        {
            return new T();
        }

        var json = File.ReadAllText(_filePath);
        return JsonSerializer.Deserialize<T>(json, _options) ?? new T();
    }

    public void Save(T value)
    {
        var json = JsonSerializer.Serialize(value, _options);
        File.WriteAllText(_filePath, json);
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add src/AgenticFlow.Persistence/JsonStores/JsonFileStore.cs
git commit -m "feat(persistence): add generic JSON file store"
```

#### Task 2.3: Stores específicos e interfaces

**Files:**
- Create: `src/AgenticFlow.Application/Abstractions/IBoardStore.cs`
- Create: `src/AgenticFlow.Application/Abstractions/IRunStateStore.cs`
- Create: `src/AgenticFlow.Application/Abstractions/IConfigStore.cs`
- Create: `src/AgenticFlow.Application/Abstractions/ISnapshotStore.cs`
- Create: `src/AgenticFlow.Persistence/Repositories/BoardStore.cs`
- Create: `src/AgenticFlow.Persistence/Repositories/RunStateStore.cs`
- Create: `src/AgenticFlow.Persistence/Repositories/ConfigStore.cs`
- Create: `src/AgenticFlow.Persistence/Repositories/SnapshotStore.cs`

- [ ] **Step 1: Definir interfaces en Application**

`IBoardStore.cs`:
```csharp
namespace AgenticFlow.Application.Abstractions;

public interface IBoardStore
{
    BoardState Load();
    void Save(BoardState state);
}

public class BoardState
{
    public List<Ticket> Tickets { get; set; } = new();
}
```

`IRunStateStore.cs`:
```csharp
namespace AgenticFlow.Application.Abstractions;

public interface IRunStateStore
{
    RunState Load();
    void Save(RunState state);
}

public class RunState
{
    public string Status { get; set; } = "idle";
    public Dictionary<string, object> Data { get; set; } = new();
}
```

`IConfigStore.cs`:
```csharp
namespace AgenticFlow.Application.Abstractions;

public interface IConfigStore
{
    AppConfig Load();
    void Save(AppConfig config);
}

public class AppConfig
{
    public string Backend { get; set; } = string.Empty;
    public int MaxWorkers { get; set; } = 4;
    public string ProjectsRoot { get; set; } = string.Empty;
}
```

`ISnapshotStore.cs`:
```csharp
namespace AgenticFlow.Application.Abstractions;

public interface ISnapshotStore
{
    void Save(string ticketId, Snapshot snapshot);
    Snapshot? Load(string ticketId);
}

public class Snapshot
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string TicketId { get; set; } = string.Empty;
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public Dictionary<string, object> State { get; set; } = new();
}
```

- [ ] **Step 2: Implementar stores en Persistence**

`BoardStore.cs`:
```csharp
using AgenticFlow.Application.Abstractions;
using AgenticFlow.Persistence.JsonStores;

namespace AgenticFlow.Persistence.Repositories;

public class BoardStore : IBoardStore
{
    private readonly JsonFileStore<BoardState> _store;

    public BoardStore(JsonFileStore<BoardState> store)
    {
        _store = store;
    }

    public BoardState Load() => _store.Load();
    public void Save(BoardState state) => _store.Save(state);
}
```

Implementaciones similares para `RunStateStore`, `ConfigStore`, `SnapshotStore`.

- [ ] **Step 3: DependencyInjection**

Create: `src/AgenticFlow.Persistence/DependencyInjection.cs`

```csharp
using AgenticFlow.Application.Abstractions;
using AgenticFlow.Persistence.FileSystem;
using AgenticFlow.Persistence.JsonStores;
using AgenticFlow.Persistence.Repositories;
using Microsoft.Extensions.DependencyInjection;

namespace AgenticFlow.Persistence;

public static class DependencyInjection
{
    public static IServiceCollection AddPersistence(this IServiceCollection services, IConfiguration configuration)
    {
        services.AddSingleton<AppDataPathProvider>();
        services.AddSingleton(provider =>
        {
            var pathProvider = provider.GetRequiredService<AppDataPathProvider>();
            return new JsonFileStore<BoardState>(pathProvider, "board.json");
        });
        services.AddSingleton(provider =>
        {
            var pathProvider = provider.GetRequiredService<AppDataPathProvider>();
            return new JsonFileStore<RunState>(pathProvider, "run-state.json");
        });
        services.AddSingleton(provider =>
        {
            var pathProvider = provider.GetRequiredService<AppDataPathProvider>();
            return new JsonFileStore<AppConfig>(pathProvider, "config.json");
        });

        services.AddSingleton<IBoardStore, BoardStore>();
        services.AddSingleton<IRunStateStore, RunStateStore>();
        services.AddSingleton<IConfigStore, ConfigStore>();
        services.AddSingleton<ISnapshotStore, SnapshotStore>();

        return services;
    }
}
```

- [ ] **Step 4: Build y commit**

```bash
dotnet build
git add src/AgenticFlow.Persistence src/AgenticFlow.Application/Abstractions/*Store.cs
git commit -m "feat(persistence): add board, run-state, config and snapshot stores"
```

---

### Módulo 3: Domain

**Agente asignado:** 3  
**Responsabilidad:** Completar el modelo de dominio puro con todas las entidades, value objects, eventos y excepciones necesarias para el motor MetaGPT.  
**Proyecto:** `AgenticFlow.Domain`  
**Dependencias:** Ninguna (capa pura).  
**Contrato:** Modelos usados por Persistence y Application.

#### Task 3.1: Completar entidades de dominio

**Files:**
- Create/Modify: `src/AgenticFlow.Domain/Entities/TaskItem.cs`
- Create/Modify: `src/AgenticFlow.Domain/Entities/Plan.cs`
- Create/Modify: `src/AgenticFlow.Domain/Entities/RoleState.cs`
- Create/Modify: `src/AgenticFlow.Domain/Entities/BackendInfo.cs`

- [ ] **Step 1: TaskItem**

```csharp
namespace AgenticFlow.Domain.Entities;

public class TaskItem
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string Title { get; set; } = string.Empty;
    public string Status { get; set; } = "pending";
    public List<Guid> Dependencies { get; set; } = new();
    public string Assignee { get; set; } = string.Empty;
    public Dictionary<string, object> Metadata { get; set; } = new();
}
```

- [ ] **Step 2: Plan**

```csharp
namespace AgenticFlow.Domain.Entities;

public class Plan
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public List<TaskItem> Tasks { get; set; } = new();
}
```

- [ ] **Step 3: BackendInfo**

```csharp
namespace AgenticFlow.Domain.Entities;

public class BackendInfo
{
    public string Id { get; set; } = string.Empty;
    public string Name { get; set; } = string.Empty;
    public bool Available { get; set; }
    public int Priority { get; set; }
}
```

- [ ] **Step 4: Commit**

```bash
git add src/AgenticFlow.Domain/Entities
git commit -m "feat(domain): complete core entities"
```

#### Task 3.2: Eventos y excepciones de dominio

**Files:**
- Create: `src/AgenticFlow.Domain/Events/TicketStartedEvent.cs`
- Create: `src/AgenticFlow.Domain/Events/PhaseCompletedEvent.cs`
- Create: `src/AgenticFlow.Domain/Events/MessagePublishedEvent.cs`
- Create: `src/AgenticFlow.Domain/Exceptions/DomainException.cs`
- Create: `src/AgenticFlow.Domain/Exceptions/OrchestratorException.cs`
- Create: `src/AgenticFlow.Domain/Exceptions/AIRunnerException.cs`

- [ ] **Step 1: Implementar eventos**

```csharp
namespace AgenticFlow.Domain.Events;

public abstract class DomainEventBase : IDomainEvent
{
    public Guid EventId { get; } = Guid.NewGuid();
    public DateTimeOffset OccurredOn { get; } = DateTimeOffset.UtcNow;
}

public class TicketStartedEvent : DomainEventBase
{
    public Guid TicketId { get; set; }
}

public class PhaseCompletedEvent : DomainEventBase
{
    public Guid TicketId { get; set; }
    public string Phase { get; set; } = string.Empty;
}

public class MessagePublishedEvent : DomainEventBase
{
    public Guid MessageId { get; set; }
    public string Role { get; set; } = string.Empty;
    public string Content { get; set; } = string.Empty;
}
```

- [ ] **Step 2: Implementar excepciones**

```csharp
namespace AgenticFlow.Domain.Exceptions;

public class DomainException : Exception
{
    public DomainException(string message) : base(message) { }
}

public class OrchestratorException : DomainException
{
    public OrchestratorException(string message) : base(message) { }
}

public class AIRunnerException : DomainException
{
    public AIRunnerException(string message, Exception? inner = null) : base(message, inner) { }
}
```

- [ ] **Step 3: Build y commit**

```bash
dotnet build
git add src/AgenticFlow.Domain/Events src/AgenticFlow.Domain/Exceptions
git commit -m "feat(domain): add domain events and exceptions"
```

---

## Fase 2: Módulos Application (Agentes 4-9)

> Una vez completados los módulos 1, 2 y 3, estos agentes pueden trabajar en paralelo. Cada uno consume `Domain`, `Persistence` y las abstracciones de Application.

### Módulo 4: AI Runners

**Agente asignado:** 4  
**Responsabilidad:** Migrar `core/runners/`, `core/ai_execution.py`, `core/chat_formatter.py` a C# usando Semantic Kernel.  
**Proyecto:** `AgenticFlow.Application`  
**Dependencias:** Domain.  
**Contrato:** `IAIRunner`, `IBackendRegistry`, `IChatFormatter`.

#### Task 4.1: Definir abstracciones

**Files:**
- Create: `src/AgenticFlow.Application/Abstractions/IAIRunner.cs`
- Create: `src/AgenticFlow.Application/Abstractions/IBackendRegistry.cs`
- Create: `src/AgenticFlow.Application/Abstractions/IChatFormatter.cs`

- [ ] **Step 1: IAIRunner**

```csharp
namespace AgenticFlow.Application.Abstractions;

public interface IAIRunner
{
    string BackendId { get; }
    int Priority { get; }
    bool IsAvailable();
    Task<string> InvokeAsync(string prompt, CancellationToken cancellationToken = default);
}
```

- [ ] **Step 2: IBackendRegistry**

```csharp
namespace AgenticFlow.Application.Abstractions;

public interface IBackendRegistry
{
    IReadOnlyList<IAIRunner> GetAvailableRunners();
    IAIRunner? GetRunner(string backendId);
}
```

- [ ] **Step 3: IChatFormatter**

```csharp
namespace AgenticFlow.Application.Abstractions;

public interface IChatFormatter
{
    string Format(string rawOutput);
}
```

- [ ] **Step 4: Commit**

```bash
git add src/AgenticFlow.Application/Abstractions/IAIRunner.cs src/AgenticFlow.Application/Abstractions/IBackendRegistry.cs src/AgenticFlow.Application/Abstractions/IChatFormatter.cs
git commit -m "feat(runners): add AI runner abstractions"
```

#### Task 4.2: Implementar ChatFormatter

**Files:**
- Create: `src/AgenticFlow.Application/Runners/ChatFormatter.cs`

- [ ] **Step 1: Implementar formatter básico**

```csharp
using AgenticFlow.Application.Abstractions;
using System.Text.RegularExpressions;

namespace AgenticFlow.Application.Runners;

public class ChatFormatter : IChatFormatter
{
    public string Format(string rawOutput)
    {
        if (string.IsNullOrWhiteSpace(rawOutput))
            return rawOutput;

        var cleaned = Regex.Replace(rawOutput, @"\x1B\[[0-9;]*m", string.Empty);
        return cleaned.Trim();
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add src/AgenticFlow.Application/Runners/ChatFormatter.cs
git commit -m "feat(runners): add chat output formatter"
```

#### Task 4.3: Implementar adaptadores de IA

**Files:**
- Create: `src/AgenticFlow.Application/Runners/KimiCliRunner.cs`
- Create: `src/AgenticFlow.Application/Runners/ClaudeCodeRunner.cs`
- Create: `src/AgenticFlow.Application/Runners/OpenAiApiRunner.cs`
- Create: `src/AgenticFlow.Application/Runners/BackendRegistry.cs`

- [ ] **Step 1: Implementar base común para CLI runners**

Create: `src/AgenticFlow.Application/Runners/CliRunnerBase.cs`

```csharp
using AgenticFlow.Application.Abstractions;
using System.Diagnostics;

namespace AgenticFlow.Application.Runners;

public abstract class CliRunnerBase : IAIRunner
{
    public abstract string BackendId { get; }
    public abstract int Priority { get; }
    protected abstract string CommandName { get; }

    public virtual bool IsAvailable()
    {
        try
        {
            var process = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = CommandName,
                    Arguments = "--version",
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false
                }
            };
            process.Start();
            process.WaitForExit();
            return process.ExitCode == 0;
        }
        catch
        {
            return false;
        }
    }

    public virtual async Task<string> InvokeAsync(string prompt, CancellationToken cancellationToken = default)
    {
        var process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = CommandName,
                Arguments = $"\"{prompt.Replace("\"", "\\\"")}\"",
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false
            }
        };

        process.Start();
        var output = await process.StandardOutput.ReadToEndAsync(cancellationToken);
        await process.WaitForExitAsync(cancellationToken);
        return output;
    }
}
```

- [ ] **Step 2: Implementar runners concretos**

```csharp
namespace AgenticFlow.Application.Runners;

public class KimiCliRunner : CliRunnerBase
{
    public override string BackendId => "kimi";
    public override int Priority => 1;
    protected override string CommandName => "kimi";
}

public class ClaudeCodeRunner : CliRunnerBase
{
    public override string BackendId => "claude";
    public override int Priority => 2;
    protected override string CommandName => "claude";
}
```

- [ ] **Step 3: Implementar OpenAI API runner con Semantic Kernel**

```csharp
using AgenticFlow.Application.Abstractions;
using Microsoft.Extensions.Configuration;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.ChatCompletion;

namespace AgenticFlow.Application.Runners;

public class OpenAiApiRunner : IAIRunner
{
    private readonly Kernel _kernel;
    private readonly string _apiKey;

    public string BackendId => "openai-api";
    public int Priority => 10;

    public OpenAiApiRunner(IConfiguration configuration)
    {
        _apiKey = configuration["OpenAI:ApiKey"] ?? string.Empty;
        var modelId = configuration["OpenAI:ModelId"] ?? "gpt-4o";

        var builder = Kernel.CreateBuilder();
        if (!string.IsNullOrWhiteSpace(_apiKey))
        {
            builder.AddOpenAIChatCompletion(modelId, _apiKey);
        }
        _kernel = builder.Build();
    }

    public bool IsAvailable() => !string.IsNullOrWhiteSpace(_apiKey);

    public async Task<string> InvokeAsync(string prompt, CancellationToken cancellationToken = default)
    {
        var chat = _kernel.GetRequiredService<IChatCompletionService>();
        var history = new ChatHistory();
        history.AddUserMessage(prompt);
        var response = await chat.GetChatMessageContentsAsync(history, kernel: _kernel, cancellationToken: cancellationToken);
        return string.Join("\n", response.Select(r => r.Content));
    }
}
```

- [ ] **Step 4: Implementar BackendRegistry**

```csharp
using AgenticFlow.Application.Abstractions;

namespace AgenticFlow.Application.Runners;

public class BackendRegistry : IBackendRegistry
{
    private readonly IEnumerable<IAIRunner> _runners;

    public BackendRegistry(IEnumerable<IAIRunner> runners)
    {
        _runners = runners;
    }

    public IReadOnlyList<IAIRunner> GetAvailableRunners() =>
        _runners.Where(r => r.IsAvailable()).OrderBy(r => r.Priority).ToList();

    public IAIRunner? GetRunner(string backendId) =>
        _runners.FirstOrDefault(r => r.BackendId == backendId);
}
```

- [ ] **Step 5: Build y commit**

```bash
dotnet build
git add src/AgenticFlow.Application/Runners
git commit -m "feat(runners): add AI runner adapters and registry"
```

---

### Módulo 5: Orchestrator + Environment + Planning

**Agente asignado:** 5  
**Responsabilidad:** Migrar `core/orchestrator.py`, `core/environment.py`, `core/plan.py` a servicios C#.  
**Proyecto:** `AgenticFlow.Application`  
**Dependencias:** Domain, Memory, Context.  
**Contrato:** `IOrchestrator`, `IEnvironment`, `IPlanEngine`.

#### Task 5.1: Definir abstracciones

**Files:**
- Create: `src/AgenticFlow.Application/Abstractions/IOrchestrator.cs`
- Create: `src/AgenticFlow.Application/Abstractions/IEnvironment.cs`
- Create: `src/AgenticFlow.Application/Abstractions/IPlanEngine.cs`

- [ ] **Step 1: Interfaces**

```csharp
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Abstractions;

public interface IOrchestrator
{
    Task RunAsync(Ticket ticket, CancellationToken cancellationToken = default);
    Task PauseAsync();
    Task ResumeAsync();
    Task StopAsync();
}

public interface IEnvironment
{
    void RegisterRole(Roles.Role role);
    Task RunRoundAsync(IContext context, CancellationToken cancellationToken = default);
}

public interface IPlanEngine
{
    Plan CreatePlan(Ticket ticket, IEnumerable<Message> memory);
    IEnumerable<IEnumerable<TaskItem>> GetTopologicalBatches(Plan plan);
}
```

- [ ] **Step 2: Commit**

```bash
git add src/AgenticFlow.Application/Abstractions/IOrchestrator.cs src/AgenticFlow.Application/Abstractions/IEnvironment.cs src/AgenticFlow.Application/Abstractions/IPlanEngine.cs
git commit -m "feat(orchestration): add orchestrator, environment and plan abstractions"
```

#### Task 5.2: Implementar plan engine

**Files:**
- Create: `src/AgenticFlow.Application/Orchestration/PlanEngine.cs`

- [ ] **Step 1: Implementar PlanEngine**

```csharp
using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Orchestration;

public class PlanEngine : IPlanEngine
{
    public Plan CreatePlan(Ticket ticket, IEnumerable<Message> memory)
    {
        return new Plan
        {
            Tasks = new List<TaskItem>()
        };
    }

    public IEnumerable<IEnumerable<TaskItem>> GetTopologicalBatches(Plan plan)
    {
        var remaining = new HashSet<TaskItem>(plan.Tasks);
        while (remaining.Count > 0)
        {
            var batch = remaining.Where(t => t.Dependencies.All(d => !remaining.Any(r => r.Id == d))).ToList();
            if (batch.Count == 0) throw new InvalidOperationException("Cyclic dependency detected");
            foreach (var item in batch) remaining.Remove(item);
            yield return batch;
        }
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add src/AgenticFlow.Application/Orchestration/PlanEngine.cs
git commit -m "feat(orchestration): add plan engine with topological batching"
```

#### Task 5.3: Implementar Environment

**Files:**
- Create: `src/AgenticFlow.Application/Orchestration/Environment.cs`

- [ ] **Step 1: Implementar Environment**

```csharp
using AgenticFlow.Application.Abstractions;
using AgenticFlow.Application.Roles;

namespace AgenticFlow.Application.Orchestration;

public class Environment : IEnvironment
{
    private readonly List<Role> _roles = new();

    public void RegisterRole(Role role)
    {
        _roles.Add(role);
    }

    public async Task RunRoundAsync(IContext context, CancellationToken cancellationToken = default)
    {
        var pending = _roles.Where(r => r.HasPendingWork(context)).ToList();
        await Task.WhenAll(pending.Select(r => r.RunAsync(context, cancellationToken)));
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add src/AgenticFlow.Application/Orchestration/Environment.cs
git commit -m "feat(orchestration): add role environment runner"
```

#### Task 5.4: Implementar Orchestrator

**Files:**
- Create: `src/AgenticFlow.Application/Orchestration/Orchestrator.cs`

- [ ] **Step 1: Implementar Orchestrator con fases**

```csharp
using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;
using AgenticFlow.Domain.Events;

namespace AgenticFlow.Application.Orchestration;

public class Orchestrator : IOrchestrator
{
    private readonly IEnvironment _environment;
    private readonly IPlanEngine _planEngine;
    private readonly IMemoryStore _memory;
    private readonly IEventBus _eventBus;
    private readonly ISnapshotStore _snapshotStore;

    public Orchestrator(
        IEnvironment environment,
        IPlanEngine planEngine,
        IMemoryStore memory,
        IEventBus eventBus,
        ISnapshotStore snapshotStore)
    {
        _environment = environment;
        _planEngine = planEngine;
        _memory = memory;
        _eventBus = eventBus;
        _snapshotStore = snapshotStore;
    }

    public async Task RunAsync(Ticket ticket, CancellationToken cancellationToken = default)
    {
        await _eventBus.PublishAsync(new TicketStartedEvent { TicketId = ticket.Id }, cancellationToken);

        var plan = _planEngine.CreatePlan(ticket, _memory.GetAll());
        var batches = _planEngine.GetTopologicalBatches(plan);

        foreach (var batch in batches)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var context = new DefaultContext(ticket, _memory, cancellationToken);
            await _environment.RunRoundAsync(context, cancellationToken);
        }

        await _eventBus.PublishAsync(new PhaseCompletedEvent { TicketId = ticket.Id, Phase = "execution" }, cancellationToken);
    }

    public Task PauseAsync() => Task.CompletedTask;
    public Task ResumeAsync() => Task.CompletedTask;
    public Task StopAsync() => Task.CompletedTask;
}
```

- [ ] **Step 2: Crear DefaultContext**

Create: `src/AgenticFlow.Application/Orchestration/DefaultContext.cs`

```csharp
using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Orchestration;

public class DefaultContext : IContext
{
    public Ticket Ticket { get; }
    public IMemoryStore Memory { get; }
    public CancellationToken CancellationToken { get; }

    public DefaultContext(Ticket ticket, IMemoryStore memory, CancellationToken cancellationToken)
    {
        Ticket = ticket;
        Memory = memory;
        CancellationToken = cancellationToken;
    }
}
```

- [ ] **Step 3: Build y commit**

```bash
dotnet build
git add src/AgenticFlow.Application/Orchestration
git commit -m "feat(orchestration): add orchestrator with phase execution"
```

---

### Módulo 6: PM + Architect + Design Review

**Agente asignado:** 6  
**Responsabilidad:** Migrar roles y acciones de PM research, PM lead, architect y design review.  
**Proyecto:** `AgenticFlow.Application`  
**Dependencias:** Orchestrator, AI Runners.  
**Contrato:** Clases `Role` y `Action` base.

#### Task 6.1: Definir base Role y Action

**Files:**
- Create: `src/AgenticFlow.Application/Roles/Role.cs`
- Create: `src/AgenticFlow.Application/Actions/Action.cs`

- [ ] **Step 1: Role base**

```csharp
using AgenticFlow.Application.Abstractions;

namespace AgenticFlow.Application.Roles;

public abstract class Role
{
    public string Name { get; protected set; } = string.Empty;

    public abstract bool HasPendingWork(IContext context);
    public abstract Task RunAsync(IContext context, CancellationToken cancellationToken = default);
}
```

- [ ] **Step 2: Action base**

```csharp
using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Actions;

public abstract class Action
{
    public abstract Task<Message> RunAsync(IContext context, CancellationToken cancellationToken = default);
}
```

- [ ] **Step 3: Commit**

```bash
git add src/AgenticFlow.Application/Roles/Role.cs src/AgenticFlow.Application/Actions/Action.cs
git commit -m "feat(roles-actions): add Role and Action base classes"
```

#### Task 6.2: Implementar roles PM/Architect

**Files:**
- Create: `src/AgenticFlow.Application/Roles/PMResearchRole.cs`
- Create: `src/AgenticFlow.Application/Roles/PMLeadRole.cs`
- Create: `src/AgenticFlow.Application/Roles/ArchitectRole.cs`
- Create: `src/AgenticFlow.Application/Actions/ResearchAction.cs`
- Create: `src/AgenticFlow.Application/Actions/ConsolidatePrdAction.cs`
- Create: `src/AgenticFlow.Application/Actions/ArchitectAction.cs`
- Create: `src/AgenticFlow.Application/Actions/DesignReviewAction.cs`

- [ ] **Step 1: Implementar acciones**

```csharp
using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Actions;

public class ResearchAction : Action
{
    private readonly IAIRunner _runner;

    public ResearchAction(IAIRunner runner)
    {
        _runner = runner;
    }

    public override async Task<Message> RunAsync(IContext context, CancellationToken cancellationToken = default)
    {
        var prompt = $"Research the following request: {context.Ticket.Description}";
        var result = await _runner.InvokeAsync(prompt, cancellationToken);
        return new Message
        {
            Role = "pm_research",
            Type = "research",
            Content = result,
            Cause = context.Ticket.Id.ToString()
        };
    }
}
```

- [ ] **Step 2: Implementar roles**

```csharp
using AgenticFlow.Application.Abstractions;

namespace AgenticFlow.Application.Roles;

public class PMResearchRole : Role
{
    private readonly Actions.ResearchAction _action;

    public PMResearchRole(Actions.ResearchAction action)
    {
        Name = "pm_research";
        _action = action;
    }

    public override bool HasPendingWork(IContext context) => true;

    public override async Task RunAsync(IContext context, CancellationToken cancellationToken = default)
    {
        var message = await _action.RunAsync(context, cancellationToken);
        context.Memory.Add(message);
    }
}
```

- [ ] **Step 3: Commit**

```bash
git add src/AgenticFlow.Application/Roles/PMResearchRole.cs src/AgenticFlow.Application/Roles/PMLeadRole.cs src/AgenticFlow.Application/Roles/ArchitectRole.cs
git add src/AgenticFlow.Application/Actions/ResearchAction.cs src/AgenticFlow.Application/Actions/ConsolidatePrdAction.cs src/AgenticFlow.Application/Actions/ArchitectAction.cs src/AgenticFlow.Application/Actions/DesignReviewAction.cs
git commit -m "feat(pm-architect): add PM and Architect roles/actions"
```

---

### Módulo 7: Engineer + Squad + Implementation

**Agente asignado:** 7  
**Responsabilidad:** Migrar Engineer, EngineerSquad, ImplementAction, CorrectionAction, helpers de git/worktree.  
**Proyecto:** `AgenticFlow.Application`  
**Dependencias:** Role/Action base, AI Runners.  
**Contrato:** Servicios de implementación.

#### Task 7.1: Implementar acciones de implementación

**Files:**
- Create: `src/AgenticFlow.Application/Actions/ImplementAction.cs`
- Create: `src/AgenticFlow.Application/Actions/CorrectionAction.cs`

- [ ] **Step 1: ImplementAction**

```csharp
using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;
using System.Diagnostics;

namespace AgenticFlow.Application.Actions;

public class ImplementAction : Action
{
    private readonly IAIRunner _runner;

    public ImplementAction(IAIRunner runner)
    {
        _runner = runner;
    }

    public override async Task<Message> RunAsync(IContext context, CancellationToken cancellationToken = default)
    {
        var prompt = $"Implement the assigned task for ticket: {context.Ticket.Description}";
        var result = await _runner.InvokeAsync(prompt, cancellationToken);
        return new Message
        {
            Role = "engineer",
            Type = "implementation",
            Content = result,
            Cause = context.Ticket.Id.ToString()
        };
    }
}
```

- [ ] **Step 2: CorrectionAction**

```csharp
using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Actions;

public class CorrectionAction : Action
{
    private readonly IAIRunner _runner;

    public CorrectionAction(IAIRunner runner)
    {
        _runner = runner;
    }

    public override async Task<Message> RunAsync(IContext context, CancellationToken cancellationToken = default)
    {
        var prompt = "Apply the requested corrections to the previous implementation.";
        var result = await _runner.InvokeAsync(prompt, cancellationToken);
        return new Message
        {
            Role = "engineer",
            Type = "correction",
            Content = result,
            Cause = context.Ticket.Id.ToString()
        };
    }
}
```

- [ ] **Step 3: Commit**

```bash
git add src/AgenticFlow.Application/Actions/ImplementAction.cs src/AgenticFlow.Application/Actions/CorrectionAction.cs
git commit -m "feat(engineer): add implement and correction actions"
```

#### Task 7.2: Implementar roles de engineer

**Files:**
- Create: `src/AgenticFlow.Application/Roles/EngineerRole.cs`
- Create: `src/AgenticFlow.Application/Roles/EngineerSquadRole.cs`

- [ ] **Step 1: EngineerRole**

```csharp
using AgenticFlow.Application.Abstractions;

namespace AgenticFlow.Application.Roles;

public class EngineerRole : Role
{
    private readonly Actions.ImplementAction _implementAction;
    private readonly Actions.CorrectionAction _correctionAction;

    public EngineerRole(Actions.ImplementAction implementAction, Actions.CorrectionAction correctionAction)
    {
        Name = "engineer";
        _implementAction = implementAction;
        _correctionAction = correctionAction;
    }

    public override bool HasPendingWork(IContext context) => true;

    public override async Task RunAsync(IContext context, CancellationToken cancellationToken = default)
    {
        var message = await _implementAction.RunAsync(context, cancellationToken);
        context.Memory.Add(message);
    }
}
```

- [ ] **Step 2: EngineerSquadRole**

```csharp
using AgenticFlow.Application.Abstractions;

namespace AgenticFlow.Application.Roles;

public class EngineerSquadRole : Role
{
    private readonly IEnumerable<EngineerRole> _engineers;

    public EngineerSquadRole(IEnumerable<EngineerRole> engineers)
    {
        Name = "engineer_squad";
        _engineers = engineers;
    }

    public override bool HasPendingWork(IContext context) => _engineers.Any(e => e.HasPendingWork(context));

    public override async Task RunAsync(IContext context, CancellationToken cancellationToken = default)
    {
        await Task.WhenAll(_engineers.Select(e => e.RunAsync(context, cancellationToken)));
    }
}
```

- [ ] **Step 3: Commit**

```bash
git add src/AgenticFlow.Application/Roles/EngineerRole.cs src/AgenticFlow.Application/Roles/EngineerSquadRole.cs
git commit -m "feat(engineer): add Engineer and EngineerSquad roles"
```

---

### Módulo 8: QA + Review + Support Roles

**Agente asignado:** 8  
**Responsabilidad:** Migrar QA, Review, Dispatcher, Monitor, Recovery, TeamLeader, SwarmLeader, Aggregator.  
**Proyecto:** `AgenticFlow.Application`  
**Dependencias:** Role/Action base.  
**Contrato:** Roles de soporte.

#### Task 8.1: Implementar QA y Review

**Files:**
- Create: `src/AgenticFlow.Application/Roles/QARole.cs`
- Create: `src/AgenticFlow.Application/Actions/ReviewAction.cs`

- [ ] **Step 1: ReviewAction**

```csharp
using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Actions;

public class ReviewAction : Action
{
    private readonly IAIRunner _runner;

    public ReviewAction(IAIRunner runner)
    {
        _runner = runner;
    }

    public override async Task<Message> RunAsync(IContext context, CancellationToken cancellationToken = default)
    {
        var prompt = "Review the implementation and provide feedback or approval.";
        var result = await _runner.InvokeAsync(prompt, cancellationToken);
        return new Message
        {
            Role = "qa",
            Type = "review",
            Content = result,
            Cause = context.Ticket.Id.ToString()
        };
    }
}
```

- [ ] **Step 2: QARole**

```csharp
using AgenticFlow.Application.Abstractions;

namespace AgenticFlow.Application.Roles;

public class QARole : Role
{
    private readonly Actions.ReviewAction _reviewAction;

    public QARole(Actions.ReviewAction reviewAction)
    {
        Name = "qa";
        _reviewAction = reviewAction;
    }

    public override bool HasPendingWork(IContext context) => true;

    public override async Task RunAsync(IContext context, CancellationToken cancellationToken = default)
    {
        var message = await _reviewAction.RunAsync(context, cancellationToken);
        context.Memory.Add(message);
    }
}
```

- [ ] **Step 3: Commit**

```bash
git add src/AgenticFlow.Application/Roles/QARole.cs src/AgenticFlow.Application/Actions/ReviewAction.cs
git commit -m "feat(qa): add QA review role and action"
```

#### Task 8.2: Implementar support roles

**Files:**
- Create: `src/AgenticFlow.Application/Roles/DispatcherRole.cs`
- Create: `src/AgenticFlow.Application/Roles/MonitorRole.cs`
- Create: `src/AgenticFlow.Application/Roles/RecoveryRole.cs`
- Create: `src/AgenticFlow.Application/Roles/TeamLeaderRole.cs`
- Create: `src/AgenticFlow.Application/Roles/SwarmLeaderRole.cs`
- Create: `src/AgenticFlow.Application/Roles/AggregatorRole.cs`

- [ ] **Step 1: Implementar roles de soporte con lógica mínima**

```csharp
using AgenticFlow.Application.Abstractions;

namespace AgenticFlow.Application.Roles;

public class DispatcherRole : Role
{
    public DispatcherRole() => Name = "dispatcher";
    public override bool HasPendingWork(IContext context) => false;
    public override Task RunAsync(IContext context, CancellationToken cancellationToken = default) => Task.CompletedTask;
}

public class MonitorRole : Role
{
    public MonitorRole() => Name = "monitor";
    public override bool HasPendingWork(IContext context) => false;
    public override Task RunAsync(IContext context, CancellationToken cancellationToken = default) => Task.CompletedTask;
}

public class RecoveryRole : Role
{
    public RecoveryRole() => Name = "recovery";
    public override bool HasPendingWork(IContext context) => false;
    public override Task RunAsync(IContext context, CancellationToken cancellationToken = default) => Task.CompletedTask;
}

public class TeamLeaderRole : Role
{
    public TeamLeaderRole() => Name = "team_leader";
    public override bool HasPendingWork(IContext context) => false;
    public override Task RunAsync(IContext context, CancellationToken cancellationToken = default) => Task.CompletedTask;
}

public class SwarmLeaderRole : Role
{
    public SwarmLeaderRole() => Name = "swarm_leader";
    public override bool HasPendingWork(IContext context) => false;
    public override Task RunAsync(IContext context, CancellationToken cancellationToken = default) => Task.CompletedTask;
}

public class AggregatorRole : Role
{
    public AggregatorRole() => Name = "aggregator";
    public override bool HasPendingWork(IContext context) => false;
    public override Task RunAsync(IContext context, CancellationToken cancellationToken = default) => Task.CompletedTask;
}
```

- [ ] **Step 2: Commit**

```bash
git add src/AgenticFlow.Application/Roles/DispatcherRole.cs src/AgenticFlow.Application/Roles/MonitorRole.cs src/AgenticFlow.Application/Roles/RecoveryRole.cs src/AgenticFlow.Application/Roles/TeamLeaderRole.cs src/AgenticFlow.Application/Roles/SwarmLeaderRole.cs src/AgenticFlow.Application/Roles/AggregatorRole.cs
git commit -m "feat(support): add dispatcher, monitor, recovery and support roles"
```

---

### Módulo 9: Memory + Context + Skills

**Agente asignado:** 9  
**Responsabilidad:** Implementar `IMemoryStore`, `IContext`, registro de skills YAML e inyección de prefijos.  
**Proyecto:** `AgenticFlow.Application`  
**Dependencias:** Domain.  
**Contrato:** `IMemoryStore`, `IContext`, `ISkillRegistry`.

#### Task 9.1: Implementar MemoryStore

**Files:**
- Create: `src/AgenticFlow.Application/Memory/MemoryStore.cs`

- [ ] **Step 1: Implementar MemoryStore**

```csharp
using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Memory;

public class MemoryStore : IMemoryStore
{
    private readonly List<Message> _messages = new();

    public void Add(Message message)
    {
        _messages.Add(message);
    }

    public IReadOnlyList<Message> GetAll() => _messages.AsReadOnly();

    public IReadOnlyList<Message> GetByCause(string cause) =>
        _messages.Where(m => m.Cause == cause).ToList().AsReadOnly();

    public IReadOnlyList<Message> GetByRole(string role) =>
        _messages.Where(m => m.Role == role).ToList().AsReadOnly();

    public IReadOnlyList<Message> GetByType(string type) =>
        _messages.Where(m => m.Type == type).ToList().AsReadOnly();

    public IReadOnlyList<Message> GetByRecipient(string recipient) =>
        _messages.Where(m => m.Recipient == recipient).ToList().AsReadOnly();
}
```

- [ ] **Step 2: Commit**

```bash
git add src/AgenticFlow.Application/Memory/MemoryStore.cs
git commit -m "feat(memory): add in-memory message store"
```

#### Task 9.2: Implementar SkillRegistry

**Files:**
- Create: `src/AgenticFlow.Application/Abstractions/ISkillRegistry.cs`
- Create: `src/AgenticFlow.Application/Skills/SkillRegistry.cs`
- Copy: `dashboard/core/role_skills_registry.yaml` → `src/AgenticFlow.Application/Skills/role_skills_registry.yaml`

- [ ] **Step 1: ISkillRegistry**

```csharp
namespace AgenticFlow.Application.Abstractions;

public interface ISkillRegistry
{
    string GetPrefixForRole(string role);
}
```

- [ ] **Step 2: Agregar paquete YamlDotNet**

```bash
cd /Users/fabricciotornero/AgenticFlow/src
dotnet add AgenticFlow.Application package YamlDotNet
```

- [ ] **Step 3: SkillRegistry**

Create: `src/AgenticFlow.Application/Skills/SkillRegistry.cs`

```csharp
using AgenticFlow.Application.Abstractions;
using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace AgenticFlow.Application.Skills;

public class SkillRegistry : ISkillRegistry
{
    private readonly Dictionary<string, string> _prefixes = new();

    public SkillRegistry()
    {
        var yamlPath = Path.Combine(AppContext.BaseDirectory, "Skills", "role_skills_registry.yaml");
        if (!File.Exists(yamlPath)) return;

        var yaml = File.ReadAllText(yamlPath);
        var deserializer = new DeserializerBuilder()
            .WithNamingConvention(UnderscoredNamingConvention.Instance)
            .Build();

        var data = deserializer.Deserialize<Dictionary<string, SkillEntry>>(yaml);
        foreach (var entry in data)
        {
            _prefixes[entry.Key] = entry.Value.Prompt ?? string.Empty;
        }
    }

    public string GetPrefixForRole(string role) =>
        _prefixes.TryGetValue(role, out var prefix) ? prefix : string.Empty;

    private class SkillEntry
    {
        public string Prompt { get; set; } = string.Empty;
    }
}
```

- [ ] **Step 4: Commit**

```bash
git add src/AgenticFlow.Application/Skills src/AgenticFlow.Application/Abstractions/ISkillRegistry.cs
git commit -m "feat(skills): add skill registry with YamlDotNet"
```

---

## Fase 3: Integración (Agente 10)

> Este agente se encarga de unir todo: event bus real, mapeo SignalR, adaptación de `communication_bus.py`, pruebas end-to-end.

### Módulo 10: Communication Bus + Integration

**Agente asignado:** 10  
**Responsabilidad:** `IEventBus` real, publicación de eventos a SignalR, integración Bff ↔ Application.  
**Proyectos:** `AgenticFlow.Bff`, `AgenticFlow.Application`  
**Dependencias:** Todos los módulos anteriores.

#### Task 10.1: Implementar event bus con SignalR

**Files:**
- Modify: `src/AgenticFlow.Bff/Infrastructure/InMemoryEventBus.cs`
- Create: `src/AgenticFlow.Bff/Infrastructure/SignalREventBus.cs`

- [ ] **Step 1: Implementar SignalREventBus**

```csharp
using AgenticFlow.Application.Abstractions;
using AgenticFlow.Bff.Hubs;
using AgenticFlow.Domain.Events;
using Microsoft.AspNetCore.SignalR;

namespace AgenticFlow.Bff.Infrastructure;

public class SignalREventBus : IEventBus
{
    private readonly IHubContext<DashboardHub> _hubContext;

    public SignalREventBus(IHubContext<DashboardHub> hubContext)
    {
        _hubContext = hubContext;
    }

    public async Task PublishAsync(IDomainEvent domainEvent, CancellationToken cancellationToken = default)
    {
        await _hubContext.Clients.All.SendAsync("event", domainEvent, cancellationToken);
    }
}
```

- [ ] **Step 2: Registrar en Program.cs**

Reemplazar `AddSingleton<IEventBus, InMemoryEventBus>()` por:

```csharp
builder.Services.AddSingleton<IEventBus, SignalREventBus>();
```

- [ ] **Step 3: Commit**

```bash
git add src/AgenticFlow.Bff/Infrastructure/SignalREventBus.cs src/AgenticFlow.Bff/Program.cs
git commit -m "feat(integration): wire domain events to SignalR"
```

#### Task 10.2: Integrar Application services en Bff

**Files:**
- Modify: `src/AgenticFlow.Bff/Program.cs`
- Modify: `src/AgenticFlow.Bff/Controllers/TicketsController.cs`

- [ ] **Step 1: Registrar servicios de Application**

```csharp
builder.Services.AddSingleton<IMemoryStore, MemoryStore>();
builder.Services.AddSingleton<IEnvironment, Environment>();
builder.Services.AddSingleton<IPlanEngine, PlanEngine>();
builder.Services.AddSingleton<IOrchestrator, Orchestrator>();
builder.Services.AddSingleton<IBackendRegistry, BackendRegistry>();
builder.Services.AddSingleton<ISkillRegistry, SkillRegistry>();

// Register runners
builder.Services.AddSingleton<IAIRunner, KimiCliRunner>();
builder.Services.AddSingleton<IAIRunner, ClaudeCodeRunner>();
builder.Services.AddSingleton<IAIRunner, OpenAiApiRunner>();

// Register roles and actions
builder.Services.AddScoped<Actions.ResearchAction>();
builder.Services.AddScoped<Actions.ImplementAction>();
builder.Services.AddScoped<Actions.ReviewAction>();
builder.Services.AddScoped<Roles.PMResearchRole>();
builder.Services.AddScoped<Roles.EngineerRole>();
builder.Services.AddScoped<Roles.QARole>();
```

- [ ] **Step 2: Actualizar TicketsController para usar ITicketService**

```csharp
using AgenticFlow.Application.Abstractions;
using Microsoft.AspNetCore.Mvc;

namespace AgenticFlow.Bff.Controllers;

[ApiController]
[Route("api/[controller]")]
public class TicketsController : ControllerBase
{
    private readonly ITicketService _ticketService;

    public TicketsController(ITicketService ticketService)
    {
        _ticketService = ticketService;
    }

    [HttpGet]
    public async Task<IActionResult> GetTickets()
    {
        var tickets = await _ticketService.GetAllAsync();
        return Ok(tickets);
    }

    [HttpPost("{id:guid}/play")]
    public async Task<IActionResult> Play(Guid id)
    {
        await _ticketService.PlayAsync(id);
        return Ok(new { status = "started", id });
    }
}
```

- [ ] **Step 3: Crear ITicketService e implementación**

Create: `src/AgenticFlow.Application/Abstractions/ITicketService.cs`

```csharp
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Abstractions;

public interface ITicketService
{
    Task<IReadOnlyList<Ticket>> GetAllAsync();
    Task<Ticket?> GetByIdAsync(Guid id);
    Task PlayAsync(Guid id);
}
```

Create: `src/AgenticFlow.Application/Services/TicketService.cs`

```csharp
using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Services;

public class TicketService : ITicketService
{
    private readonly IBoardStore _boardStore;
    private readonly IOrchestrator _orchestrator;

    public TicketService(IBoardStore boardStore, IOrchestrator orchestrator)
    {
        _boardStore = boardStore;
        _orchestrator = orchestrator;
    }

    public Task<IReadOnlyList<Ticket>> GetAllAsync()
    {
        var state = _boardStore.Load();
        return Task.FromResult<IReadOnlyList<Ticket>>(state.Tickets);
    }

    public Task<Ticket?> GetByIdAsync(Guid id)
    {
        var state = _boardStore.Load();
        return Task.FromResult(state.Tickets.FirstOrDefault(t => t.Id == id));
    }

    public async Task PlayAsync(Guid id)
    {
        var ticket = await GetByIdAsync(id);
        if (ticket == null) throw new InvalidOperationException($"Ticket {id} not found");
        await _orchestrator.RunAsync(ticket);
    }
}
```

- [ ] **Step 4: Build y commit**

```bash
dotnet build
git add src/AgenticFlow.Bff/Controllers/TicketsController.cs src/AgenticFlow.Bff/Program.cs
git add src/AgenticFlow.Application/Abstractions/ITicketService.cs src/AgenticFlow.Application/Services/TicketService.cs
git commit -m "feat(integration): wire application services into Bff controllers"
```

---

## Fase 4: Testing y publicación multiplataforma

### Task 11.1: Crear proyecto de tests

**Files:**
- Create: `tests/AgenticFlow.Domain.Tests/AgenticFlow.Domain.Tests.csproj`
- Create: `tests/AgenticFlow.Application.Tests/AgenticFlow.Application.Tests.csproj`
- Create: `tests/AgenticFlow.Persistence.Tests/AgenticFlow.Persistence.Tests.csproj`
- Create: `tests/AgenticFlow.Bff.Tests/AgenticFlow.Bff.Tests.csproj`

- [ ] **Step 1: Crear proyectos xUnit**

```bash
cd /Users/fabricciotornero/AgenticFlow
mkdir -p tests
cd tests

dotnet new xunit -n AgenticFlow.Domain.Tests -f net10.0
dotnet new xunit -n AgenticFlow.Application.Tests -f net10.0
dotnet new xunit -n AgenticFlow.Persistence.Tests -f net10.0
dotnet new xunit -n AgenticFlow.Bff.Tests -f net10.0
```

- [ ] **Step 2: Agregar referencias**

```bash
cd /Users/fabricciotornero/AgenticFlow/tests

dotnet add AgenticFlow.Domain.Tests reference ../src/AgenticFlow.Domain/AgenticFlow.Domain.csproj
dotnet add AgenticFlow.Application.Tests reference ../src/AgenticFlow.Application/AgenticFlow.Application.csproj
dotnet add AgenticFlow.Persistence.Tests reference ../src/AgenticFlow.Persistence/AgenticFlow.Persistence.csproj
dotnet add AgenticFlow.Bff.Tests reference ../src/AgenticFlow.Bff/AgenticFlow.Bff.csproj
```

- [ ] **Step 3: Agregar a solución**

```bash
cd /Users/fabricciotornero/AgenticFlow
dotnet sln add tests/AgenticFlow.Domain.Tests/AgenticFlow.Domain.Tests.csproj
dotnet sln add tests/AgenticFlow.Application.Tests/AgenticFlow.Application.Tests.csproj
dotnet sln add tests/AgenticFlow.Persistence.Tests/AgenticFlow.Persistence.Tests.csproj
dotnet sln add tests/AgenticFlow.Bff.Tests/AgenticFlow.Bff.Tests.csproj
```

- [ ] **Step 4: Commit**

```bash
git add tests/ AgenticFlow.sln
git commit -m "test: add xUnit test projects"
```

### Task 11.2: Tests básicos

**Files:**
- Create: `tests/AgenticFlow.Domain.Tests/MessageTests.cs`
- Create: `tests/AgenticFlow.Persistence.Tests/ConfigStoreTests.cs`

- [ ] **Step 1: Test de Message**

```csharp
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Domain.Tests;

public class MessageTests
{
    [Fact]
    public void Message_Defaults_Are_Set()
    {
        var message = new Message();
        Assert.NotEqual(Guid.Empty, message.Id);
        Assert.Equal(string.Empty, message.Role);
    }
}
```

- [ ] **Step 2: Test de ConfigStore**

```csharp
using AgenticFlow.Application.Abstractions;
using AgenticFlow.Persistence;
using AgenticFlow.Persistence.FileSystem;
using AgenticFlow.Persistence.JsonStores;
using AgenticFlow.Persistence.Repositories;
using Microsoft.Extensions.DependencyInjection;

namespace AgenticFlow.Persistence.Tests;

public class ConfigStoreTests
{
    [Fact]
    public void Save_And_Load_Config_Works()
    {
        var services = new ServiceCollection();
        services.AddSingleton<AppDataPathProvider>();
        services.AddSingleton(provider =>
        {
            var pathProvider = provider.GetRequiredService<AppDataPathProvider>();
            return new JsonFileStore<AppConfig>(pathProvider, "config-test.json");
        });
        services.AddSingleton<IConfigStore, ConfigStore>();

        var provider = services.BuildServiceProvider();
        var store = provider.GetRequiredService<IConfigStore>();

        store.Save(new AppConfig { Backend = "openai-api", MaxWorkers = 8 });
        var loaded = store.Load();

        Assert.Equal("openai-api", loaded.Backend);
        Assert.Equal(8, loaded.MaxWorkers);
    }
}
```

- [ ] **Step 3: Run tests**

```bash
cd /Users/fabricciotornero/AgenticFlow
dotnet test
```

Expected: Tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: add basic domain and persistence tests"
```

### Task 11.3: Scripts de publicación multiplataforma

**Files:**
- Create: `scripts/build-sidecar.sh`
- Modify: `src/AgenticFlow.Bff/Frontend/src-tauri/src/main.rs`

- [ ] **Step 1: Crear build-sidecar.sh**

```bash
#!/usr/bin/env bash
set -e

CONFIG=${1:-Release}
OUTPUT=${2:-dist}

for RID in osx-x64 osx-arm64 win-x64 linux-x64; do
  echo "Publishing for $RID..."
  dotnet publish src/AgenticFlow.Bff/AgenticFlow.Bff.csproj \
    -c "$CONFIG" \
    -r "$RID" \
    --self-contained true \
    -p:PublishSingleFile=true \
    -o "$OUTPUT/$RID"
done

echo "Done. Outputs in $OUTPUT"
```

```bash
chmod +x scripts/build-sidecar.sh
```

- [ ] **Step 2: Actualizar main.rs para lanzar sidecar .NET**

Modify: `src/AgenticFlow.Bff/Frontend/src-tauri/src/main.rs`

```rust
use tauri::Manager;
use std::process::Command;

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let sidecar = app.path_resolver()
                .resolve_resource("binaries/agenticflow-server")
                .expect("failed to resolve sidecar");

            Command::new(sidecar)
                .spawn()
                .expect("failed to spawn sidecar");

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

- [ ] **Step 3: Commit**

```bash
git add scripts/build-sidecar.sh src/AgenticFlow.Bff/Frontend/src-tauri/src/main.rs
git commit -m "chore: add multiplatform sidecar build script and update Tauri launcher"
```

---

## Ejecución de agentes en paralelo

### Secuencia recomendada

1. **Fase 0 (secuencial):** Tasks 0.1 → 0.2 → 0.3 → 0.4.
2. **Fase 1 (paralelo, pero depende de Fase 0):**
   - Agente 1: Módulo 1 (Bff + Hosting)
   - Agente 2: Módulo 2 (Persistence)
   - Agente 3: Módulo 3 (Domain)
3. **Fase 2 (paralelo, depende de Fase 1):**
   - Agente 4: Módulo 4 (AI Runners)
   - Agente 5: Módulo 5 (Orchestrator + Environment + Planning)
   - Agente 6: Módulo 6 (PM + Architect + Design Review)
   - Agente 7: Módulo 7 (Engineer + Squad + Implementation)
   - Agente 8: Módulo 8 (QA + Review + Support Roles)
   - Agente 9: Módulo 9 (Memory + Context + Skills)
4. **Fase 3 (secuencial, depende de Fase 2):**
   - Agente 10: Módulo 10 (Communication Bus + Integration)
5. **Fase 4 (secuencial, depende de Fase 3):**
   - Task 11.1 → 11.2 → 11.3.

### Convenciones para agentes

- Cada agente debe trabajar en la rama `feature/dotnet-backend`.
- Cada task completada debe ir en un commit separado con mensaje claro.
- Antes de commit, ejecutar `dotnet build` y asegurarse de que pase.
- Si un agente necesita un tipo/interfaz que aún no existe, lo define en su módulo y notifica en el commit/message.
- No modificar archivos Python originales; solo añadir nuevos archivos .NET y mover frontend.

---

## Verificación final

- [ ] `dotnet build` pasa en toda la solución.
- [ ] `dotnet test` pasa todos los tests.
- [ ] El frontend Tauri compila y puede conectarse al backend .NET.
- [ ] Los endpoints `/api/board`, `/api/tickets`, `/api/config` responden correctamente.
- [ ] SignalR `/hub` acepta conexiones y envía eventos.
- [ ] El sidecar se publica para macOS, Windows y Linux.
