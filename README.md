# NudgeFlow

NudgeFlow is a WhatsApp-oriented CRM for small businesses. The repository currently contains a tenant-scoped CRM API, a React web application, an approval-gated follow-up agent workflow, WhatsApp integration points, and a separate experimental message-intelligence workspace.

## What is in the repository

- **CRM:** Register and sign in, manage business contacts, and track due-dated follow-ups.
- **Business workspaces:** Contacts, follow-ups, agent runs, and related data are scoped to the authenticated user's business workspace.
- **Agent workflow:** Create a proposed follow-up message, review it, and explicitly approve or reject it. Runs and audit events are persisted; execution recovery is designed to avoid automatically repeating an uncertain send.
- **Message intelligence:** Optionally classify an incoming customer message using a local model and use a configured LLM provider for structured extraction and draft generation. The deterministic draft path remains available without the provider.
- **Messaging:** Mock messaging is the default. The backend also has an optional WhatsApp Cloud API sending adapter and WhatsApp webhook endpoints. Live sends require external credentials and Meta configuration; receiving webhooks additionally requires a public HTTPS callback.
- **Web application:** React and TypeScript pages for the dashboard, contacts, follow-ups, agent runs, authentication, and settings.
- **ML workspace:** A separately managed Python project for customer-message intent classification, evaluation, and local inference.

Live messaging and provider-backed LLM requests are external integrations, not prerequisites for local development. The intent model is experimental; results on synthetic data are not evidence of real-world customer-message performance.

## Repository layout

```text
backend/nudgeflow/       FastAPI API, SQLAlchemy models, Alembic migrations, and tests
frontend/                React + TypeScript + Vite web application
ml/lead_intelligence/    Separate Python intent-classification workspace
docs/                    Project reports and supporting documentation
```

## Requirements

- Python 3.11 or newer for the backend
- [`uv`](https://docs.astral.sh/uv/) for Python dependencies and commands
- PostgreSQL for running the backend and applying migrations
- Node.js and npm for the frontend (use a version compatible with the Vite version in `frontend/package.json`)
- Optional: a local ML environment/checkpoint, an LLM API key, or Meta WhatsApp Cloud API credentials, depending on which integrations you want to exercise

## Local development

Start PostgreSQL and create a database for the application. In a terminal, configure and run the backend from the repository root:

```powershell
Set-Location .\backend\nudgeflow
Copy-Item .env.example .env
```

Edit `backend/nudgeflow/.env` and set at least:

```dotenv
NUDGEFLOW_DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost:5432/nudgeflow
NUDGEFLOW_JWT_SECRET_KEY=<random-secret-at-least-32-characters>
```

Then install dependencies, apply migrations, and start the API:

```powershell
uv sync --dev
uv run alembic upgrade head
uv run uvicorn nudgeflow.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. Interactive OpenAPI documentation is at `http://127.0.0.1:8000/docs`; the basic process health endpoint is `http://127.0.0.1:8000/health`.

In another terminal, start the frontend:

```powershell
Set-Location .\frontend
npm install
npm run dev
```

Vite prints the local frontend URL, typically `http://localhost:5173`. The frontend defaults to the API at `http://localhost:8000`. To use another API URL, set `VITE_API_BASE_URL` in `frontend/.env`. The backend's default CORS origins include the usual localhost Vite addresses; if your frontend uses another origin, add it to `NUDGEFLOW_CORS_ORIGINS` in the backend environment.

## Configuration and integrations

The backend reads `NUDGEFLOW_`-prefixed settings from `backend/nudgeflow/.env` (or its process environment). Important settings include:

| Variable | Purpose |
| --- | --- |
| `NUDGEFLOW_DATABASE_URL` | PostgreSQL connection URL |
| `NUDGEFLOW_JWT_SECRET_KEY` | Signs access tokens; use a strong random value, at least 32 characters in production |
| `NUDGEFLOW_CORS_ORIGINS` | JSON array of allowed browser origins |
| `NUDGEFLOW_LLM_API_KEY` | Optional provider key for message extraction and draft generation |
| `NUDGEFLOW_LLM_MODEL` | Optional model identifier used with the provider |
| `NUDGEFLOW_WHATSAPP_ENABLED` | Explicit opt-in for real WhatsApp sends; defaults to `false` |
| `NUDGEFLOW_WHATSAPP_ACCESS_TOKEN` | WhatsApp Cloud API access token |
| `NUDGEFLOW_WHATSAPP_PHONE_NUMBER_ID` | WhatsApp business phone-number ID |
| `NUDGEFLOW_WHATSAPP_WEBHOOK_VERIFY_TOKEN` | Secret used for webhook verification |
| `NUDGEFLOW_WHATSAPP_APP_SECRET` | Meta app secret used to validate webhook requests |

Keep secrets in local environment files and never commit them. Do not enable live sending until Meta is configured and the target-recipient flow is verified. The webhook currently validates requests and persists events; it does not automatically create agent runs or send replies. For the complete backend setup, endpoint details, migrations, webhook behavior, and safety notes, see [backend/nudgeflow/README.md](backend/nudgeflow/README.md).

The backend's intent-classifier adapter uses the separate `ml/lead_intelligence` environment and a locally available checkpoint. It does not download model weights. See [ml/lead_intelligence/README.md](ml/lead_intelligence/README.md) for ML setup, data handling, evaluation, and inference details.

## Tests and checks

Run the backend tests from `backend/nudgeflow`:

```powershell
uv run python -m pytest -q
```

These tests primarily use isolated SQLite databases and mocked external providers; they do not send real WhatsApp messages or require live LLM requests. Some PostgreSQL migration and concurrency tests are opt-in and require a disposable test database. Read the backend README before setting their database URL; never point them at a production or shared database.

Run frontend checks from `frontend`:

```powershell
npm run lint
npm run build
```

Run ML tests from `ml/lead_intelligence`:

```powershell
uv sync --group dev
uv run pytest
```

## API overview

The API includes:

- `POST /auth/register`, `POST /auth/login`
- Contact CRUD under `/contacts`
- Follow-up CRUD under `/follow-ups`
- Agent run creation, retrieval, approval, rejection, and explicit recovery/execution under `/agent/runs`
- WhatsApp webhook verification and event reception under `/webhooks/whatsapp`
- `GET /health`

Most CRM and agent routes require a bearer access token. Use `/docs` for the current request and response schemas.

## Scope and limitations

- `/health` confirms that the API process responds; it is not a database-readiness check.
- WhatsApp delivery, webhook operation, and LLM-backed drafting require external configuration. Mock messaging remains the safe local default.
- Agent approval is required before execution; an ambiguous execution result is not automatically resent.
- The ML workspace is separate from the backend dependencies, and model inference requires local environment/checkpoint setup. Synthetic evaluation must not be presented as customer-performance evidence.
- The project status report in `docs/` is a dated snapshot and may not reflect subsequent repository changes.
