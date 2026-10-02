# AI Thread Billing

A development prototype for AI conversations with per-thread token usage and cost reporting. The React workspace connects to FastAPI over WebSocket, falls back to HTTP for sending messages, and displays backend-calculated metrics. Kafka, Redis, SQLite and a separate Streamlit dashboard support the event and billing pipeline.

The workspace uses a seeded demo account (`user_id: 1`) and model (`model_id: 1`). Authentication is not implemented. Invoice creation exists in the backend but is unavailable in the React interface. No hosted deployment is configured or verified.

## Frontend development

Use Node.js 22 and npm:

```bash
cd frontend
npm ci
npm start
```

The frontend defaults to `http://localhost:8000/api`. Set `REACT_APP_API_URL` to the backend’s API URL before starting or building; WebSocket connections use the same origin with `/ws/chat/{user}/{thread}`. HTTPS uses WSS. The backend must allow the frontend origin and expose those routes.

```bash
npm test -- --watchAll=false --maxWorkers=2
npm run build
```

Regression tests isolate HTTP and WebSocket transport: they do not invoke AI providers or billing endpoints. GitHub Actions runs the frontend tests and production build, then retains the static build as an artifact. These checks do not establish full backend or Compose readiness.

## Local services

The existing `docker-compose.yml` defines frontend `3000`, backend `8000`, dashboard `8501`, Kafka, ZooKeeper, Redis and an event collector. Running it requires Docker Compose and an `ANTHROPIC_API_KEY` supplied through the environment or a private `.env`. Sending a live chat can invoke the configured AI provider. Backend startup initializes and updates its development SQLite schema and seed data.

```bash
docker compose up --build
```

This is the repository’s local orchestration command; full-stack startup and end-to-end provider/billing behavior have not been verified by the frontend audit. Kafka/ZooKeeper images use `latest`, and the backend’s historical dependency set is separate from the locked frontend installation.

Read the [architecture](docs/architecture.mdx), [developer guide](docs/developer-guide.mdx) and [workspace guide](docs/user-guide.mdx). The MDX files are documentation source; this repository has no documentation renderer configured.
