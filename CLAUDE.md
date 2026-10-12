## Agent skills

### Issue tracker

Issues live in GitHub Issues on `santiagocoriap/piston-cup-paddock` (use the `gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Project layout

- `backend/`: Django project. One Django app for each module in `apps/`. Settings in `config/settings.py`.
- `frontend/`: React with Vite. Text in `src/locales/es.json` and `src/locales/en.json`. Spanish is the default.
- `e2e/`: Playwright tests. They use a separate Compose project `paddock-e2e` on port 8421 and delete it after the run.
- `samples/`: sanitized race data. Never commit files from `samples-raw/`.
- `current-scripts/`: the league's earlier scripts. Reference only.

## Commands

- Run all tests: `pnpm test` (backend, frontend, and end-to-end).
- Backend tests only: `cd backend && uv run pytest`. Needs `docker compose up -d db`.
- After an API change, run `pnpm gen:api` and commit `frontend/openapi.json` and `frontend/src/api/schema.d.ts`.
- League rules: `docs/LEAGUE_RULES.md`. Data fields: `docs/DATA_SOURCES.md`.
