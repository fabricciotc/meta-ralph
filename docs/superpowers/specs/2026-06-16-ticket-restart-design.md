# Diseño: Restart total de un ticket

## Objetivo
Permitir al usuario reiniciar un ticket desde cero, borrando su progreso de run y volviendo a ejecutar el pipeline completo, con una advertencia de confirmación previa.

## Alcance
- Botón de reinicio en la fila del ticket, junto a los controles de pausa/reanudación.
- Modal de confirmación reutilizando el `confirm-modal` existente.
- Endpoint `POST /api/tickets/<ticket_id>/restart`.
- Limpieza de estado del run y artefactos generados para ese ticket.
- El ticket vuelve a `ready-for-work` y se inicia el loop como si fuera la primera vez.

## Qué se borra
- Snapshot en disco: `run-state.<ticket_id>.json`.
- Estado en memoria/disco del run (run-state global) si el ticket estaba activo o pausado.
- Artefactos generados en `scripts/meta-ralph/state/`:
  - `prd-<ticket_id>.md`
  - `tasks-<ticket_id>.json`
  - `architecture-<ticket_id>.md`
  - `design-review-<ticket_id>.*` (si existiera)
- Entrada del ticket en `paused_run_threads` si estaba pausado.

## Qué NO se borra
- El código ya modificado en el repositorio del proyecto.
- El ticket del board ni su historial de columnas.
- El log global `run.log` (puede contener entradas previas del ticket).

## Flujo backend
1. Validar que el ticket existe en el board.
2. Si hay un runner activo para este ticket, detenerlo (`runner.stop()` + `join`).
3. Si el ticket está en `paused_run_threads`, eliminarlo.
4. Borrar snapshot en disco.
5. Borrar artefactos generados del ticket.
6. Resetear `run-state` a idle.
7. Actualizar el ticket en el board a `ready-for-work`.
8. Iniciar el run desde cero llamando a `play_ticket(ticket_id)` (que inicia con `resume=False`).

## Flujo frontend
1. Cada ticket muestra un icono de reinicio (`refresh-cw`) junto a play/pause si el ticket está en una columna ejecutable (`ready-for-work`, `in-design`, `in-progress`, `in-review`, `done`).
2. Al hacer click se abre el modal de confirmación con título "Reiniciar ticket" y mensaje explicando que se borrará el progreso y los artefactos generados.
3. Si confirma, se hace `POST /api/tickets/<id>/restart` y se muestra un toast con el resultado.

## Tests
- Unitario del helper `restart_ticket`:
  - Crea run-state y artefactos de prueba.
  - Verifica que se borran y se actualiza el board.
  - Verifica que se inicia un nuevo runner.
- Test del endpoint Flask con `test_client`.
- Test del frontend: verificar que el botón renderiza y abre el modal (opcional, JS unit no configurado).

## API
```
POST /api/tickets/<ticket_id>/restart
Response: { "ok": true|false, "message": "..." }
```
