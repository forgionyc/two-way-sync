# Project: Two-Way-Sync

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`two-way-sync` is a Python project (requires Python 3.13, pinned via `.python-version`).
This is a Python project managed with `uv`. Use `uv run` for execution and `uv add` for dependencies.

## Stack

- Python
- Node (local MCP servers compatibility)
- FastAPI
- PostgreSQL
- SQLAlchemy 2.0
- Alembic
- Mockoon (mock APIs)


## Project Structure
├── alembic/                # The migrations directory
│   ├── versions/           # Individual migration scripts (.py files)
│   ├── env.py              # Configuration for migrations (links to your models)
│   └── script.py.mako      # Template for new migrations
├── app/
│   ├── api/                # Routes (Keep these thin; just call services)
│   ├── core/               # Config, security, and your audit log utilities
│   ├── db/                 # Session management & migrations
│   ├── models/             # SQLAlchemy models (Database tables)
│   ├── schemas/            # Pydantic models (Request/Response validation)
│   ├── services/           # Internal business logic
│   ├── integrations/       # External API wrappers (e.g., QBO)
│   ├── workers/            # Background sync/queue logic
│   └── main.py
├── scripts/                # Dev utilities & seeds
├── .env.example            # Environment template
├── .gitignore
├── .python-version         # Managed by uv
├── alembic.ini             # Alembic config
├── CLAUDE.md               # project-specific instructions/context
├── docker-compose.yml      # Infrastructure (Postgres, etc.)
├── mise.toml               # Tool version manager
├── package.json            # Node-based dev tools
├── package-lock.json
├── pyproject.toml          # Python dependencies (uv)
├── quickbooks-mock.json    # Mock data/Mockoon config
├── quickbooks_api.md       # Integration documentation
├── README.md
└── uv.lock                 # Deterministic lockfile

## Commands
- `docker compose up -d` Start the database
- `uv run python seeds.py` Seed the database with initial data
- `npm run mock` Start the mock server
- `uv run fastapi dev`  Run the application with auto-reload dev mode
- `uv add <package-name>` Add a dependency if needed - use the `--dev` flag for dev dependencies

## Database

- SQLAlchemy 2.0 style (use `select()` not `session.query()`)
- All schema changes go through Alembic migrations — never modify tables manually
- New migration: `uv run alembic revision --autogenerate -m "description"`
- Apply migrations: `uv run alembic upgrade head`

## Git

- Conventional commits: feat:, fix:, chore:
- Run the full check before committing: `ruff check . && ruff format --check .`

## Do NOT

- Do not use `import *`
- Do not use `objects.raw()` or raw SQL — use the repository layer
- Do not use `print()` — use the configured `logging` module
- Do not use `*` imports
