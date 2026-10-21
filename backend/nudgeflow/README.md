# NudgeFlow AI

NudgeFlow AI is a WhatsApp-first CRM for small businesses and service providers. This repository currently provides the backend foundation for contact and follow-up management through a FastAPI JSON API. WhatsApp and AI integrations are future milestones.

## Current capabilities

- Contact create, list, retrieve, update, and delete within a business workspace.
- Follow-up create, list, retrieve, partial update, and delete, including `pending` and `completed` status.
- PostgreSQL persistence through SQLAlchemy and versioned Alembic migrations.
- Email/password registration and login using Argon2 password hashes and signed JWT access tokens.
- Bearer authentication and tenant isolation for contact and follow-up routes.
- A business workspace created transactionally with each registration; contacts and follow-ups are scoped to the authenticated user's workspace.
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
| POST | `/auth/register` | Register with a valid email and password; optional `business_name` creates the initial workspace (201) |
| POST | `/auth/login` | Verify credentials and return a bearer access token |
| POST | `/contacts` | Create a contact in the authenticated workspace (201; duplicate phone within that workspace is 409) |
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

Every `/contacts` and `/follow-ups` request requires `Authorization: Bearer <access_token>`. `/auth/register`, `/auth/login`, and `/health` are public. Registration creates a business workspace and an `owner` membership in one database transaction. The optional `business_name` field defaults to `My business`. Tenant identity is taken from the authenticated user record loaded by the server; request bodies do not choose a tenant. Contacts and follow-ups are scoped to that tenant, and follow-ups must reference a contact in the same tenant. Requests for another tenant's record return 404 to avoid disclosing whether that record exists. A future invitation flow may add `member` users to an existing tenant; no invitation endpoint exists yet.

The tenant migration creates one workspace for each existing user and maps contacts with a known `owner_id` to that user's workspace. Ownerless legacy contacts are retained in an isolated `Unassigned legacy records (quarantined)` workspace with no users; their follow-ups inherit the same tenant. They are not visible to authenticated users. An operator must review and explicitly map quarantined records to the correct business before any user is added to that workspace. No records are deleted or assigned to the first user. The migration can be downgraded while restoring the prior globally-unique phone constraint; downgrade stops before schema changes if the same phone number exists in multiple tenants.

## Frontend integration

There is no React, TypeScript, or Tailwind application in `frontend/` yet. A future frontend can use `http://127.0.0.1:8000` as its local API base URL, configure that URL through its own environment settings, and allow its exact origin in `NUDGEFLOW_CORS_ORIGINS`. Contact and follow-up response fields are described above and in `/docs`.

## Tests

```powershell
uv run pytest -v
```

The API tests use isolated in-memory SQLite databases with foreign-key enforcement. They do not require or modify a PostgreSQL database. PostgreSQL connectivity and migration execution should be checked separately against a configured development database.

The tenant migration has an opt-in PostgreSQL integration test at `tests/test_tenant_migration_postgres.py`. It requires `NUDGEFLOW_MIGRATION_TEST_URL` to point to an **empty disposable loopback PostgreSQL database** whose name starts with `nudgeflow_test_`; the test refuses remote, non-PostgreSQL, incorrectly named, or non-empty databases. Set `NUDGEFLOW_DATABASE_URL` to that same test URL before running it. The test upgrades from empty, downgrades only the tenant revision, seeds pre-tenant rows, then upgrades and checks the backfill/quarantine policy. Never point this test at a development or production database.

Example for a separately created, disposable local test database:

```powershell
$env:NUDGEFLOW_DATABASE_URL = "postgresql+psycopg://postgres@127.0.0.1:5432/nudgeflow_test_tenant"
$env:NUDGEFLOW_MIGRATION_TEST_URL = $env:NUDGEFLOW_DATABASE_URL
uv run --no-sync python -m pytest -q tests/test_tenant_migration_postgres.py
```

## Limitations and next steps

- `/health` reports that the API process is responding; it does not currently check PostgreSQL readiness.
- Authentication currently uses short-lived bearer tokens without refresh or revocation. Tenant roles are stored, but there is no invitation/member-management flow or role-based authorization policy yet.
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
