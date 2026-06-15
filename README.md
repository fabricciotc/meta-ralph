# Meta-Ralph

Skill de **Kimi Code CLI** que orquesta un equipo multi-agente estilo **MetaGPT**: PM Research, Architect, Project Manager, Engineers paralelos y QA, con un dashboard web propio para gestionar tickets y visualizar el progreso en tiempo real.

## Qué hace

- Toma un PRD o ticket y lo ejecuta con un loop de 5 fases: PM Analysis → Architecture → Planning → Parallel Execution → QA Review.
- Soporta hasta 20 agentes PM de investigación en paralelo y hasta 20 Engineers en paralelo.
- Cada Engineer trabaja en su propio git worktree aislado.
- El QA revisa cada batch antes de mergear al trunk.
- Dashboard Kanban accesible en `http://localhost:5050` con WebSocket para actualizaciones en vivo.
- Guarda snapshots de run-state por ticket: puedes pausar un ticket, cambiar a otro y volver exactamente donde lo dejaste, incluso después de reiniciar el servidor.

## Instalación como skill

### Opción 1 — Clonar directamente en el directorio de skills

```bash
git clone https://github.com/fabricciotc/meta-ralph.git ~/.kimi-code/skills/meta-ralph
```

### Opción 2 — Usar `install.sh`

```bash
git clone https://github.com/fabricciotc/meta-ralph.git
cd meta-ralph
./install.sh
```

`install.sh` hará lo siguiente:

1. Registrar el skill en `~/.kimi-code/skills/meta-ralph` (con symlink si es necesario).
2. Crear el entorno virtual de Python para el dashboard en `dashboard/.venv`.
3. Instalar las dependencias de `dashboard/requirements.txt`.
4. Crear el comando `meta-ralph` en tu PATH.

Reinicia tu terminal o ejecuta `source ~/.zshrc` (o `~/.bashrc`/`~/.bash_profile`) para que el comando esté disponible.

## Uso

Dentro de un proyecto git:

```bash
meta-ralph init      # crea scripts/meta-ralph/ en el proyecto actual
meta-ralph run       # inicia el loop multi-agente y abre el dashboard
meta-ralph dashboard # inicia solo el dashboard
meta-ralph status    # muestra workers activos
meta-ralph stop      # detiene todos los workers y el dashboard
```

Luego abre `http://localhost:5050` y crea o mueve tickets a **Ready for Work** para que el orchestrador los procese.

## Estructura del skill

```text
meta-ralph/
├── SKILL.md                    # Definición del skill para Kimi Code CLI
├── README.md                   # Este archivo
├── install.sh                  # Instalador del skill + CLI
├── assets/
│   └── prd-template.json       # Plantilla de PRD de entrada
├── references/
│   ├── metagpt-roles.md        # SOPs por rol
│   ├── orchestrator-prompt.md
│   ├── worker-prompt-template.md
│   └── qa-prompt-template.md
├── scripts/
│   ├── meta-ralph.sh           # CLI principal
│   ├── create-worktree.sh
│   ├── dispatch-workers.sh
│   └── ...
└── dashboard/
    ├── server.py               # Backend Flask + SocketIO
    ├── static/                 # UI Kanban (HTML/CSS/JS)
    └── requirements.txt
```

## Requisitos

- Python 3.10+
- Git
- `kimi` CLI instalado y disponible en PATH
- Navegador moderno para el dashboard

## Cómo funciona el reconocimiento por Kimi

Kimi Code CLI descubre skills automáticamente buscando archivos `SKILL.md` en:

- `~/.kimi-code/skills/<skill-name>/SKILL.md` (skills de usuario)
- `./.kimi-code/skills/<skill-name>/SKILL.md` (skills de proyecto)

El `SKILL.md` de meta-ralph incluye un frontmatter con `name`, `description`, `allowed-tools` y `user-invocable: true`, por lo que Kimi puede cargarlo cuando el usuario menciona "meta ralph", "multi-agent loop", "parallel team", etc.

## Licencia

MIT
