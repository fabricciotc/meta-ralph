# Diseño: AI Runner portable, Orchestrator Swarm y portabilidad de meta-ralph

**Fecha:** 2026-06-16  
**Skill:** meta-ralph  
**Estado:** Aprobado para implementación

## Resumen

Este diseño convierte a `meta-ralph` en un orquestador multi-agente verdaderamente portable:

1. **AI Runner genérico:** abstracción sobre backends de IA (CLIs locales y APIs HTTP estándar) con detección automática y fallback entre ellos.
2. **Registro de skills/MCPs por rol:** mapeo estático de skills/MCPs recomendados para cada rol MetaGPT.
3. **Orchestrator como agent swarm:** los roles coordinadores (`DispatcherRole`, `MonitorRole`, `RecoveryRole`) operan dentro del `Environment` publicando mensajes entre sí.
4. **Portabilidad:** `install.sh` detecta entornos, instala dependencias en venv y guía al usuario si no hay backend de IA.

## Contexto

Actualmente `meta-ralph` depende fuertemente del CLI de Kimi (`kimi -p`) para ejecutar prompts. Esto limita el skill a usuarios de Kimi Code CLI. El objetivo es mantener la excelente integración con Kimi pero permitir que el mismo skill funcione con Cursor, Claude Code, Codex CLI o incluso APIs OpenAI-compatibles, usando fallbacks cuando un backend no está disponible.

Además, el `Orchestrator` actual centraliza la lógica de avance de fases en un solo hilo. El diseño propone dividir esa lógica en roles coordinadores que se comunican a través del `Environment`, haciendo el sistema más observable, extensible y alineado con la metodología MetaGPT.

## Objetivos

- Que `meta-ralph` funcione en cualquier PC/laptop con Python 3.10+ sin asumir Kimi.
- Que la elección de IA sea configurable y tenga fallbacks automáticos.
- Que cada rol pueda recomendar skills/MCPs útiles sin acoplarse a una plataforma.
- Que el Orchestrator sea un enjambre de coordinadores especializados.
- Que `install.sh` sea robusto y autónomo.

## 1. AI Runner portable

### 1.1 Interfaz común

Todos los backends implementan una interfaz `AIBackend`:

```python
class AIBackend(Protocol):
    name: str
    supports_skill_activation: bool  # True si acepta "Activa la skill 'X'..."

    def is_available(self) -> bool: ...
    def run_prompt(
        self,
        prompt: str,
        *,
        phase_name: str,
        timeout_seconds: int,
        agent_id: Optional[str],
        system_instructions: Optional[str],
    ) -> Optional[str]: ...
```

### 1.2 Backends soportados

| Backend | Tipo | Detección | Notas |
|---------|------|-----------|-------|
| `KimiCliBackend` | CLI | `kimi` en PATH | Usa `kimi -p <prompt>`. Soporta skill activation. |
| `CursorCliBackend` | CLI | `cursor` en PATH | Usa `cursor -p <prompt>` o similar según documentación oficial. No soporta skill activation. |
| `ClaudeCodeBackend` | CLI | `claude` en PATH | Usa `claude -p <prompt>` (Claude Code CLI). No soporta skill activation. |
| `CodexCliBackend` | CLI | `codex` en PATH | Usa `codex -p <prompt>` (OpenAI Codex CLI). No soporta skill activation. |
| `OpenAIApiBackend` | API | `OPENAI_API_KEY` o config | Endpoint configurable, modelo por defecto `gpt-4o-mini`. Fallback universal. |

### 1.3 Estrategia de fallback

1. Se lee `config.json` → `preferred_backends` (lista ordenada).
2. Para cada prompt se intenta el primer backend disponible.
3. Si `run_prompt` retorna `None` o lanza excepción, se intenta el siguiente backend disponible.
4. Si ningún backend responde, se devuelve `None` y el Action correspondiente activa su fallback local.

### 1.4 Configuración

Archivo `scripts/meta-ralph/config.json` creado por `install.sh` o la primera ejecución:

```json
{
  "preferred_backends": ["kimi", "claude", "cursor", "codex", "openai_api"],
  "model_overrides": {
    "openai_api": "gpt-4o-mini"
  },
  "timeout_defaults": {
    "pm_research": 600,
    "architect": 600,
    "planning": 600,
    "engineer": 1800,
    "qa": 600
  },
  "api_key_path": "~/.config/meta-ralph/openai_api_key"
}
```

## 2. Registro de skills/MCPs por rol

### 2.1 Archivo de registro

`dashboard/core/role_skills_registry.yaml`:

```yaml
pm_research:
  skills:
    - tech-research
    - agent-browser
  mcp_servers: []
  prompt_prefix: |
    Investiga el codebase actual usando web search y lectura de archivos.

architect:
  skills:
    - dotnet
    - mcp-builder
    - code-review
  prompt_prefix: |
    Define patrones técnicos, APIs y convenciones siguiendo las mejores prácticas del stack detectado.

engineer:
  skills:
    - dotnet
    - git-workflow
    - test-driven-development
    - crud
  mcp_servers:
    - filesystem
  prompt_prefix: |
    Implementa cambios reales en archivos, ejecuta build/tests y respeta el git workflow del proyecto.

qa:
  skills:
    - code-review
    - systematic-debugging
  prompt_prefix: |
    Revisa calidad, build/tests y consistencia con el architecture.md.
```

### 2.2 Uso en Actions

Cada `Action` puede solicitar el `prompt_prefix` de su rol. Antes de enviar el prompt al backend:

1. Si `backend.supports_skill_activation` es True, se antepone `"Activa la skill 'X' y aplica sus convenciones..."`.
2. Si es False, se antepone solo el `prompt_prefix` (texto plano) para que el modelo actúe como si usara el skill, sin depender de una característica propietaria.

Esto hace que el sistema sea tolerante: con Kimi se activan skills reales; con Cursor/Claude/Codex se inyectan las instrucciones equivalentes.

## 3. Orchestrator como agent swarm

### 3.1 Roles coordinadores

Nuevos archivos en `dashboard/core/roles/`:

- `dispatcher_role.py`: recibe el mensaje inicial del Orchestrator y publica los triggers de cada fase (`prd_ready`, `architecture_ready`, `plan_ready`, `task_assigned`, `request_review`).
- `monitor_role.py`: observa el historial del `Environment`, detecta stalls (más de N rondas sin actividad útil), reporta progreso y emite `health_check`.
- `recovery_role.py`: escucha `task_failed`, `reject_with_feedback` y `health_check` con fallos; decide entre reintentar, replanificar o marcar el run como fallido.

### 3.2 Flujo de mensajes

```
Orchestrator (hilo principal)
  └── publica: ticket_ready
      └── DispatcherRole
          ├── publica: prd_ready          → PMLeadRole / ArchitectRole
          ├── publica: architecture_ready  → PlannerRole
          ├── publica: plan_ready          → asigna tareas
          ├── publica: task_assigned       → EngineerRole(s)
          └── publica: request_review      → QARole
MonitorRole: en cada ronda reporta progreso y detecta stalls.
RecoveryRole: reacciona a fallos y publica reintentos/replanificaciones.
```

### 3.3 Responsabilidades del Orchestrator principal

- Crear `Environment`.
- Registrar roles coordinadores y de fase.
- Publicar el mensaje inicial `ticket_ready`.
- Ejecutar `run_round()` hasta que no haya actividad o se alcance el límite de rondas.
- Gestionar pause/stop y callbacks hacia `server.py`.

## 4. Portabilidad e install.sh

### 4.1 Requisitos detectados

`install.sh` debe validar:

- Python 3.10+
- `git`
- Opcional: al menos un backend de IA (`kimi`, `cursor`, `claude`, `codex`) o `OPENAI_API_KEY`

### 4.2 Acciones de install.sh

1. Registrar skill en `~/.kimi-code/skills/meta-ralph`.
2. Crear venv en `dashboard/.venv` e instalar `requirements.txt`.
3. Crear `scripts/meta-ralph/config.json` con defaults sensibles.
4. Crear `scripts/meta-ralph/prd.json` de ejemplo.
5. Crear symlink `meta-ralph` en `~/.local/bin`.
6. Mostrar mensaje final con backends detectados y enlaces de instalación si faltan.

### 4.3 requirements.txt

```text
flask>=2.0
flask-socketio>=5.0
pexpect>=4.8
pyyaml>=6.0
requests>=2.25
```

## 5. Archivos a crear/modificar

### Nuevos

- `dashboard/core/runners/__init__.py`
- `dashboard/core/runners/base.py`
- `dashboard/core/runners/kimi_cli.py`
- `dashboard/core/runners/cursor_cli.py`
- `dashboard/core/runners/claude_code.py`
- `dashboard/core/runners/codex_cli.py`
- `dashboard/core/runners/openai_api.py`
- `dashboard/core/runners/registry.py`
- `dashboard/core/role_skills_registry.yaml`
- `dashboard/core/skills_registry.py`
- `dashboard/core/roles/dispatcher_role.py`
- `dashboard/core/roles/monitor_role.py`
- `dashboard/core/roles/recovery_role.py`
- `dashboard/tests/test_runners.py`
- `dashboard/tests/test_dispatcher_role.py`
- `scripts/validate_install.py`

### Modificados

- `dashboard/core/orchestrator.py`: migrar a swarm de coordinadores.
- `dashboard/core/actions/*.py`: usar `AIBackend` a través del registry; inyectar skill prompts según soporte.
- `dashboard/core/pm_analysis.py`: recibir backend desde Orchestrator en lugar de ejecutar Kimi directamente.
- `dashboard/server.py`: inicializar `BackendRegistry` y pasarlo al Orchestrator.
- `dashboard/requirements.txt`: añadir `pyyaml`, `requests`.
- `install.sh`: mejorar detección, mensajes y configuración inicial.
- `SKILL.md`: documentar nuevos backends y configuración.

## 6. Testing

- **Unitarios:** cada backend mock de `subprocess.run` o `requests.post`; validar fallback ordenado.
- **Integración:** Orchestrator con un backend mock que responde JSON/tasks fijos; verificar que todas las fases avanzan.
- **Smoke:** ejecutar `install.sh` en un tmpdir limpio y verificar que crea venv, config y symlink.

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| CLIs de Cursor/Claude/Codex cambian de flags | Centralizar construcción del comando en un método por backend; documentar versión soportada. |
| APIs requieren keys que no todos tienen | `install.sh` guía al usuario y el fallback siempre permite CLIs locales. |
| El swarm de coordinadores introduce complejidad | Comenzar con `DispatcherRole` + `MonitorRole`; `RecoveryRole` como stub con lógica simple. |
| Prompts de skills propietarias fallan en otros backends | `supports_skill_activation` + `prompt_prefix` como fallback textual. |

## 8. Próximos pasos

1. Crear plan de implementación detallado (`writing-plans`).
2. Implementar `core/runners/` y `BackendRegistry`.
3. Implementar `role_skills_registry.yaml` + `skills_registry.py`.
4. Refactorizar `Orchestrator` para usar `DispatcherRole`, `MonitorRole`, `RecoveryRole`.
5. Actualizar `install.sh` y `requirements.txt`.
6. Escribir tests y validar dashboard.
