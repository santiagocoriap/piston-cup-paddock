# 0001 App stack

Date: October 11, 2026

Status: Accepted

## Context

The development plan needs one application with clear modules, a background worker, a relational database, Docker deployment, Spanish and English text, and LiteLLM for AI reports. It proposes Vite for the frontend build. Later stages need telemetry processing and safety-rating math.

The league is small. One developer builds the app with AI agents. The owner deploys apps with Coolify on their own server.

## Decision

| Area | Choice |
| --- | --- |
| Backend | Python with Django |
| API | Django Ninja, with an OpenAPI schema |
| Database | PostgreSQL |
| Background worker | Procrastinate, a task queue that stores tasks in PostgreSQL |
| Frontend | React with TypeScript, built with Vite |
| API client | A TypeScript client that the build makes from the OpenAPI schema |
| Login | Django session login with CSRF protection, on the same domain as the frontend |
| Translation | Django translation for backend text, react-i18next for frontend text, Spanish as the default |
| AI | The LiteLLM Python library, called only from the worker |
| Data analysis | pandas and numpy, added when a ticket needs them |
| Python tools | uv for packages, ruff for lint and format |
| Frontend tools | pnpm for packages, oxlint (the Vite template default) |
| Tests | pytest for unit and integration tests, Vitest for frontend units, Playwright for end-to-end flows |
| Deployment | Docker Compose with the services `web`, `worker`, and `db`, deployed with Coolify |

Each module in section 18 of the plan is one Django app: identity, competition planning, voting, race ingestion, restart tracking, sporting rules, records, analysis, reports, and auditing.

The Django admin site is an internal tool for the developer. The admin screens for league admins are part of the React app.

## Consequences

- LiteLLM, pandas, and numpy run in the same language as the domain rules. All scoring rules exist in one place.
- Django gives login, password hashing, migrations, and translation. Ticket #5 needs less custom work.
- The project uses two languages: Python and TypeScript. The generated API client keeps the types in the two languages the same.
- Procrastinate keeps task state in PostgreSQL. The project adds no separate queue service, as section 18 of the plan asks.
- The web container serves the built frontend and the API on one domain. Session login then works without cross-domain cookies.
