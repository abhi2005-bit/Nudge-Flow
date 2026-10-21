# NudgeFlow AI

NudgeFlow AI is a WhatsApp-first CRM for small businesses and service providers. This repository currently provides the backend foundation for contact and follow-up management through a FastAPI JSON API. WhatsApp and AI integrations are future milestones.

## Current capabilities

- Contact create, list, retrieve, update, and delete.
- Follow-up create, list, retrieve, partial update, and delete, including `pending` and `completed` status.
- PostgreSQL persistence through SQLAlchemy and versioned Alembic migrations.
- Email/password registration and login using Argon2 password hashes and signed JWT access tokens.
- Bearer authentication and per-user ownership isolation for contact and follow-up routes.
- OpenAPI documentation at `/docs` and a basic `/health` endpoint.

## Layout

```text
backend/nudgeflow/
  migrations/                 Alembic environment and revisions
  src/nudgeflow/
    main.py                   FastAPI application and routes
    config.py                 Environment-backed settings
    database.py               SQLAlchemy engine, base, and session dependency
    dependencies.py           Bearer-token verification and current-user lookup
    routers/auth.py           Registration and login endpoints
    security.py               Password hashing and verification
    tokens.py                 JWT signing and verification
    models/                   SQLAlchemy models
    schemas/                  Pydantic request and response schemas
  tests/                      Isolated pytest suite
frontend/                     Reserved; no frontend application exists yet
```

## Requirements and local setup

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/)
- PostgreSQL

Create a local PostgreSQL database and a role with access to it. From this directory, copy `.env.example` to `.env` and set `NUDGEFLOW_DATABASE_URL` to your local connection string. Keep credentials in `.env`; it is ignored by Git.

Set `NUDGEFLOW_JWT_SECRET_KEY` to a securely generated random value of at least 32 characters. The example value is only a placeholder. Production configuration rejects a missing or short signing key and rejects debug mode. Access tokens expire after `NUDGEFLOW_ACCESS_TOKEN_EXPIRE_MINUTES` (default 30, maximum 1440).

```powershell
Copy-Item .env.example .env
uv sync --dev
uv run alembic upgrade head
uv run uvicorn nudgeflow.main:app --reload
```

The API defaults to `http://127.0.0.1:8000`. Interactive docs are at `http://127.0.0.1:8000/docs`. Set CORS origins in `NUDGEFLOW_CORS_ORIGINS` as a JSON array if your frontend uses another origin.

## Database migrations

Run migrations from `backend/nudgeflow`:

```powershell
uv run alembic current
uv run alembic heads
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe schema change"
```

Review every generated migration before applying it. `upgrade head` updates the configured database; do not use development credentials for production changes.

## API

All list endpoints support `limit` (default 100, range 1–500) and `offset` (default 0). Contacts are ordered by ID; follow-ups are ordered by due date and then ID. Errors use FastAPI's standard JSON `detail` response.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/health` | Basic process health check |
| POST | `/auth/register` | Register with a valid email and password (201) |
| POST | `/auth/login` | Verify credentials and return a bearer access token |
| POST | `/contacts` | Create a contact (201; duplicate phone is 409) |
| GET | `/contacts` | List contacts |
| GET | `/contacts/{contact_id}` | Retrieve a contact (404 if missing) |
| PUT | `/contacts/{contact_id}` | Update supplied contact fields; empty body is 422 |
| DELETE | `/contacts/{contact_id}` | Delete a contact and cascade its follow-ups (204) |
| POST | `/follow-ups` | Create a follow-up (201; unknown contact is 404) |
| GET | `/follow-ups` | List follow-ups |
| GET | `/follow-ups/{follow_up_id}` | Retrieve one follow-up (404 if missing) |
| PATCH | `/follow-ups/{follow_up_id}` | Partially update title, notes, due date, or status |
| DELETE | `/follow-ups/{follow_up_id}` | Delete a follow-up (204) |

Example contact request:

```json
{"name":"Asha Rao","phone_number":"+919876543210"}
```

Example follow-up request (timestamps must include a timezone):

```json
{
  "contact_id": 1,
  "title": "Call about quotation",
  "notes": "Discuss next steps",
  "due_at": "2026-10-20T10:00:00+05:30"
}
```

Follow-up responses include `id`, `contact_id`, `title`, `notes`, `due_at`, `status`, and `created_at`. Status is currently `pending` or `completed`.

Every `/contacts` and `/follow-ups` request requires `Authorization: Bearer <access_token>`. `/auth/register`, `/auth/login`, and `/health` are public. Contact and follow-up reads and writes are scoped to the authenticated user; follow-up ownership is inherited from its contact. Requests for another user's record return 404 to avoid disclosing whether that record exists.

The ownership migration adds a nullable `contacts.owner_id`. Existing contact and follow-up rows remain intact and unassigned, and authenticated list/detail endpoints do not expose unassigned rows. They require an explicit owner assignment before becoming available in the CRM. Do not backfill them automatically: choose whether to assign those legacy records to a specific account or leave/archive them before performing a data backfill.

## Frontend integration

There is no React, TypeScript, or Tailwind application in `frontend/` yet. A future frontend can use `http://127.0.0.1:8000` as its local API base URL, configure that URL through its own environment settings, and allow its exact origin in `NUDGEFLOW_CORS_ORIGINS`. Contact and follow-up response fields are described above and in `/docs`.

## Tests

```powershell
uv run pytest -v
```

The API tests use isolated in-memory SQLite databases with foreign-key enforcement. They do not require or modify a PostgreSQL database. PostgreSQL connectivity and migration execution should be checked separately against a configured development database.

## Limitations and next steps

- `/health` reports that the API process is responding; it does not currently check PostgreSQL readiness.
- Authentication currently uses short-lived bearer tokens without refresh or revocation, organization membership, or role-based access control.
- WhatsApp Cloud API, LLMs, agent workflows, and background processing are not implemented.

## Future AI architecture

Keep deterministic CRM rules in the FastAPI/domain layer. Add AI capabilities behind narrow service interfaces that accept authorized, tenant-scoped inputs and return validated outputs:

1. Add audit events and explicit user/organization authorization for every tool action before connecting agents to CRM writes.
2. Add a summarization service for lead and conversation summaries; persist generated text with provenance and treat it as untrusted content.
3. Add retrieval over business data only after tenant filters are enforced inside retrieval queries, not only in prompts.
4. Add controlled agent workflows as allow-listed tools that call the same validated business operations as the API. Require human approval for irreversible or sensitive actions.
5. Evaluate a separate Deep Learning inference service only when a concrete model or latency/scaling need justifies it; keep model serving isolated from transactional database access.

## Contributing

Create a focused feature branch, make a small change with tests, and open a pull request for review. Do not commit `.env`, credentials, local databases, or generated virtual environments. Include migration changes when modifying the database schema.
