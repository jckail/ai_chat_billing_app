# AI Thread Billing

A development prototype for AI conversations with per-thread token usage and cost reporting, for anyone exploring how to meter and bill LLM chat usage.

**Status: prototype.** The workspace uses a seeded demo account (`user_id: 1`) and model (`model_id: 1`). Authentication is not implemented. Invoice creation exists in the backend but is unavailable in the React interface. No hosted deployment is configured or verified.

## What it does

- React chat workspace that connects to FastAPI over WebSocket and falls back to HTTP for sending messages.
- Displays backend-calculated token and cost metrics per thread.
- Kafka, Redis and SQLite carry the event and billing pipeline, fed by a separate event collector.
- A separate Streamlit dashboard reports usage and cost.

## Quickstart

### Frontend only

Use Node.js 22 and npm:

```bash
cd frontend
npm ci
npm start
```

The frontend defaults to `http://localhost:8000/api`. Set `REACT_APP_API_URL` to the backend's API URL before starting or building; WebSocket connections use the same origin with `/ws/chat/{user}/{thread}` (WSS under HTTPS). The backend must allow the frontend origin and expose those routes.

### Full stack

[docker-compose.yml](docker-compose.yml) defines frontend `3000`, backend `8000`, dashboard `8501`, Kafka, ZooKeeper, Redis and an event collector. It requires Docker Compose and an `ANTHROPIC_API_KEY` supplied through the environment or a private `.env`.

```bash
docker compose up --build
```

Sending a live chat can invoke the configured AI provider. Backend startup initializes and updates its development SQLite schema and seed data. Full-stack startup and end-to-end provider/billing behavior have not been verified by the frontend audit; Kafka/ZooKeeper images use `latest`, and the backend's historical dependency set is separate from the locked frontend installation.

## Layout

| Path | Contents |
| --- | --- |
| [frontend/](frontend) | React workspace and its tests |
| [backend/](backend) | FastAPI app: API routes, models, Kafka/Redis/Anthropic services |
| [event_collector/](event_collector) | Kafka event collector service |
| [dashboard/](dashboard) | Streamlit analytics dashboard |
| [design_planning/](design_planning) | Original requirements, plans, diagrams and screenshots |
| [docs/](docs) | Architecture and guides (MDX source; no renderer configured) |

The loose scripts in the repository root (`fix_*.js`, `restart_*.sh`, `update_*.sh` and similar) are unverified one-off debugging helpers; see [the developer guide](docs/developer-guide.mdx#unverified-one-off-scripts).

## Documentation

- [Architecture](docs/architecture.mdx) — system overview, frontend state boundaries, usage and invoice contract, release boundary.
- [Developer guide](docs/developer-guide.mdx) — configuration, tests and release artifact, making changes.
- [Workspace guide](docs/user-guide.mdx) — using the chat workspace.
- Design history: [requirements](design_planning/reqs-md.md), [implementation plan](design_planning/implementation_plan.md), [system design](design_planning/systemdesign.svg), [data model](design_planning/datamodel.svg).

## Development

From `frontend/`:

```bash
npm test -- --watchAll=false --maxWorkers=2
npm run build
```

Regression tests isolate HTTP and WebSocket transport: they do not invoke AI providers or billing endpoints. [GitHub Actions](.github/workflows/frontend.yml) runs the frontend tests and production build, then retains the static build as an artifact. These checks do not establish full backend or Compose readiness.
