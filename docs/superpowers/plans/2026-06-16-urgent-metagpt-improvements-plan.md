# Plan urgente: 4 mejoras inspiradas en MetaGPT

> **Goal:** Aplicar en meta-ralph las 4 mejoras de mayor impacto identificadas del estudio de MetaGPT: `_watch` declarativo, `ActionSet`/`todo`, feedback ejecutable y `Context` global tipado.

**Archivos clave:**
- `core/roles/base.py` — base `Role`
- `core/actions/base.py` — base `Action`
- `core/environment.py` — message pool
- `core/context.py` — nuevo contexto global
- `core/orchestrator.py` — orquestador principal
- `core/roles/engineer_role.py` + `core/actions/implement_action.py` — feedback ejecutable
- `core/roles/*_role.py` — roles existentes a migrar
- `tests/` — tests nuevos y existentes

---

## Tarea A: Contexto global tipado (`core/context.py`)

Crear un objeto `Context` compartido que contenga:
- `ticket`: dict del ticket
- `config`: dict de config (`scripts/meta-ralph/config.json`)
- `prd_path`, `architecture_path`, `tasks_path`: `Path`
- `repo_path`, `branch`: str
- `backend_registry`: `BackendRegistry`
- `skills_registry`: `SkillsRegistry`
- `callbacks`: dict de callbacks del dashboard
- `shared`: dict mutable para estado transversal

Integrarlo en `Orchestrator` y pasarlo a los roles/actions via kwargs.

## Tarea B: `_watch` declarativo + `ActionSet`/`todo`

Refactorizar `Role` base para soportar:
- `_watch`: lista de strings (cause_by) o clases `Action` que activan al rol.
- `set_actions(actions)`: lista de acciones disponibles.
- `todo`: acción actual seleccionada.
- `react_mode`: `"by_order"` | `"react"`.
- `_think(context)`: elige `todo` según modo y triggers.
- `_act(context, **kwargs)`: ejecuta `todo.run()`.
- `run(env, **kwargs)`: observe → think → act → publish.

Actualizar todos los roles existentes para usar `_watch` y `set_actions`.

## Tarea C: Feedback ejecutable real

En `ImplementAction`/`EngineerRole`:
- Después de generar código, ejecutar `dotnet build` y `dotnet test` en el repo/rama.
- Capturar stdout/stderr/returncode.
- Publicar un mensaje `build_result` / `test_result` al `Environment`.
- Si falla, el `RecoveryRole` o el propio engineer debe reintentar (hasta N rondas).
- `QARole` usa los resultados reales en lugar de diff vacío.

---

## Ejecución

Tareas A, B y C son independientes a nivel de archivos (A toca `context.py` + `orchestrator.py`; B toca `roles/base.py` + roles; C toca `engineer_role.py` + `implement_action.py`). Se ejecutarán en paralelo con subagentes, luego integración y tests.
