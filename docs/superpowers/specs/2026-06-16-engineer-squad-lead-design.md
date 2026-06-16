# Diseño: Engineer Squad como líder de área

## Objetivo
Convertir al agente `engineer-squad` en un coordinador real dentro del entorno multi-agente. Debe recibir reportes de los engineers, darles retroalimentación, conversar con ellos, solicitar más información al PM y, en última instancia, escalar dudas al usuario mediante el modal de preguntas.

## Componentes

### 1. `EngineerSquadRole` (`core/roles/engineer_squad_role.py`)
- `role_id`: `engineer-squad`.
- `_watch`: `task_report`, `request_info_from_pm_response`, `escalate_to_user_response`, `squad_chat`.
- Recibe reportes de cada `EngineerRole`.
- Decide acciones usando `run_kimi` con un prompt de coordinación:
  - Enviar `squad_instruction` al engineer (retry, fix, continue).
  - Enviar `request_info_from_pm` al PM.
  - Enviar `escalate_to_user` al Orchestrator.
  - Publicar `squad_chat` para mantener conversación visible.
- Mantiene estado de tareas (`task_reports`) para saber cuándo todo el batch terminó.

### 2. `EngineerRole` (`core/roles/engineer_role.py`)
- Después de ejecutar una tarea, publica un `task_report` dirigido a `engineer-squad`.
- Escucha `squad_instruction`. Si la instrucción es `retry`, publica un nuevo `task_assigned` a sí mismo con el feedback.
- Permite recibir `squad_chat` para conversación bidireccional.

### 3. `Orchestrator` (`core/orchestrator.py`)
- En fase de ejecución, agrega `EngineerSquadRole` al `Environment` antes de lanzar los engineers.
- Después de cada ronda del entorno, revisa mensajes `request_info_from_pm` y `escalate_to_user`:
  - `request_info_from_pm`: invoca `run_kimi` con el rol de PM investigador y publica `request_info_from_pm_response`.
  - `escalate_to_user`: invoca el callback `request_clarification` para mostrar el modal existente; la respuesta se publica como `escalate_to_user_response`.

### 4. Servidor (`server.py`)
- Añade callback `request_clarification` en `_orchestrator_callbacks`. Reutiliza el sistema de `pendingQuestions` para lanzar el modal al usuario.
- Muestra mensajes tipo `squad_chat` y `task_report` en el panel de chat existente.

### 5. Tests
- `tests/test_engineer_squad_role.py`: reporte, instrucción y coordinación de batch.
- Extender tests de `EngineerRole` para `task_report`.

## Flujo típico
1. Orchestrator publica `squad_activated`.
2. EngineerSquadRole queda a la espera.
3. Cada engineer termina una tarea y publica `task_report`.
4. Squad analiza el reporte y decide:
   - Todo bien -> publica `squad_chat` de reconocimiento.
   - Fallo -> publica `squad_instruction` con retry/fix.
   - Falta info -> publica `request_info_from_pm`.
   - Bloqueo -> publica `escalate_to_user`.
5. Si todos los reportes son exitosos, Squad publica `batch_completed`.

## Criterios de éxito
- `engineer-squad` aparece como agente líder en el grafo.
- Los reportes de engineers llegan al squad.
- El squad puede reactivar un engineer con instrucciones.
- El squad puede pedir más información al PM.
- El squad puede escalar al usuario mediante el modal de preguntas.
- Tests pasan.
