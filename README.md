# piston-cup-paddock

Championship management for a friends' Assetto Corsa league.

Read the [development plan](docs/DEVELOPMENT_PLAN.md) for the full requirements and development stages. The [league rules](docs/LEAGUE_RULES.md), the [data sources](docs/DATA_SOURCES.md), and the [app stack ADR](docs/adr/0001-app-stack.md) record the decisions so far.

## Start the app

You need Docker.

1. Copy `.env.example` to `.env`.
2. Change each value marked `CHANGE` in `.env`.
3. Run `docker compose up --build`.
4. Make the first admin account:

   ```bash
   docker compose exec web python manage.py create_first_admin --username <name>
   ```

5. Open http://localhost:8420 and sign in.
6. To add drivers, switch to the admin mode, open **Cuentas**, and make an account. Send the invite link to the driver.

## Develop

You need Docker, [uv](https://docs.astral.sh/uv/), Node 24, and pnpm 10 (`corepack enable` installs it).

| Task | Command |
| --- | --- |
| Install the packages | `cd backend && uv sync`, then `pnpm install` at the repo root |
| Start the database only | `docker compose up -d db` |
| Start the backend | `cd backend && uv run python manage.py runserver` |
| Start the frontend with hot reload | `pnpm --filter @paddock/frontend dev`, then open http://localhost:5173 |
| Run all tests | `pnpm test` |
| Make the TypeScript API types after an API change | `pnpm gen:api` |
| Lint the backend | `cd backend && uv run ruff check . && uv run ruff format --check .` |
| Lint the frontend | `pnpm --filter @paddock/frontend lint` |

`pnpm test` runs the backend tests, the frontend tests, and the end-to-end tests. The end-to-end tests start a separate Docker stack (`paddock-e2e`, port 8421) with an empty database, and delete it after the run. Your local app and its data do not change. To keep the test stack after a failure, set `E2E_KEEP_STACK=true`.

## Deploy, backup, and restore

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). Back up with `docker compose exec web python manage.py backup`.
