# NudgeFlow AI

NudgeFlow AI is a WhatsApp-first CRM for small businesses and service providers. This repository currently provides a FastAPI backend for contact and follow-up management, plus an approval-gated agent workflow with local intent classification and optional LLM-assisted extraction and draft generation. WhatsApp delivery remains a future milestone.

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
    bootstrap.py              Agent runtime bootstrap and lifespan
    config.py                 Environment-backed settings
    database.py               SQLAlchemy engine, base, and session dependency
    dependencies.py           Bearer-token verification and current-user lookup
    routers/auth.py           Registration and login endpoints
    security.py               Password hashing and verification
    tokens.py                 JWT signing and verification
    models/                   SQLAlchemy models
    schemas/                  Pydantic request and response schemas
    services/agent/           Workflow, tools, classifier, LLM client
  tests/                      Isolated pytest suite (includes test_bootstrap.py)
frontend/                     Reserved; no frontend application exists yet
```

## Bootstrap sequence

On startup, `nudgeflow.bootstrap.agent_lifespan` (wired into FastAPI's
`lifespan` parameter) performs the following steps synchronously before
handling any request:

1. **Validate configuration** — checks that all required settings have safe
   values.  No external API calls are made.  If `NUDGEFLOW_WHATSAPP_ENABLED`
   is `true`, both the access token and phone-number ID must be present.
2. **Assemble the tool registry** — constructs a `MockMessagingTool` instance
   and, if WhatsApp is enabled, a `WhatsAppCloudMessagingTool` instance.  Each
   bootstrap call produces fresh instances for test isolation.
3. **Validate tool contracts** — asserts that every tool in the registry
   exposes a string `name` attribute that matches its registry key and a
   callable `send` method.
4. **Store the runtime** — saves the immutable `AgentRuntime` dataclass on
   `app.state.agent_runtime`, where it remains available to routes via the
   `get_agent_runtime` FastAPI dependency.
5. **Fail safely** — if any step raises `BootstrapError` the exception
   propagates and the server does not start.  No pending runs are executed and
   no messages are sent during bootstrap.

On shutdown, the lifespan removes `agent_runtime` from `app.state`.

WhatsApp sending is disabled by default (`NUDGEFLOW_WHATSAPP_ENABLED=false`).
Bootstrap never enables it automatically, never executes pending runs, and
never sends messages.

### Running the application

```powershell
Copy-Item .env.example .env
# Edit .env: set NUDGEFLOW_DATABASE_URL and NUDGEFLOW_JWT_SECRET_KEY
uv sync --dev
uv run alembic upgrade head
uv run uvicorn nudgeflow.main:app --reload
```


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
| POST | `/agent/runs` | Create a draft run for an authorized follow-up; awaiting approval (201) |
| GET | `/agent/runs/{run_id}` | Retrieve tenant-scoped run, execution and audit data |
| POST | `/agent/runs/{run_id}/approve` | Persist approval and execute the local mock exactly once |
| POST | `/agent/runs/{run_id}/reject` | Persist rejection; optional reason |
| POST | `/agent/runs/{run_id}/recover` | Reconcile an expired execution claim without resending |
| POST | `/agent/runs/{run_id}/execute` | Explicitly resume a run proven not to have invoked its tool |

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

## Approval-gated agent workflow (mock execution only)

A small approval-gated backend workflow is available for follow-ups. `POST /agent/runs` accepts `{"follow_up_id": 1}`, optionally `customer_message` (up to 5000 characters), and optionally `exact_message` (up to 4096 characters). When `exact_message` is provided, LLM extraction and draft generation are bypassed, setting the proposed draft directly to the supplied exact message while maintaining strict approval gating. The follow-up and contact are read through a tenant-scoped join. If `customer_message` is supplied, the message is classified by the separate local classifier; structured extraction and draft generation use the configured LLM unless `exact_message` is specified. The classifier taxonomy and prediction remain separate from the extraction. The raw message is not persisted or included in audit events, but is transmitted to the configured provider for extraction and drafting. Without an explicit or customer message, classification and extraction are skipped and the existing follow-up-based deterministic draft is used. Creating or retrieving a run never invokes the tool. No conversation-history model exists, so the workflow does not invent conversation history.

Extraction is validated with a strict Pydantic schema. It contains a concise request summary, requested action, named product/service, the date/time phrase as stated, explicit quantity and budget, up to eight other stated details, and up to eight missing details. Unknown scalar values are `null`; ambiguous time phrases are preserved as text. The extraction is advisory and is stored with an explicit status; malformed or failed output is not persisted as successful extraction. The proposed reply is stored as the run's existing `proposed_message` and plan, with a separate draft status/source (`generated`/`llm` or `fallback`/`deterministic`). All drafts remain proposals in `awaiting_approval` and require the existing explicit approval before the mock can execute.

To enable the optional Groq-compatible provider, configure `NUDGEFLOW_LLM_API_KEY` and `NUDGEFLOW_LLM_MODEL`; both must be present. `NUDGEFLOW_LLM_TIMEOUT_SECONDS` defaults to 15 and is limited to 1–60 seconds. With no provider configuration, on provider errors, or on invalid output, the run still persists with an explicit extraction/draft status and a safe deterministic fallback. The current implementation makes up to two synchronous model requests per supplied message, so request latency includes both calls and provider latency. Automated tests mock the provider and make no external calls. Do not place credentials in source control. Review the provider's data handling terms before sending customer messages.

Review the returned `proposed_message` and `plan`, then call `POST /agent/runs/{run_id}/approve` or `POST /agent/runs/{run_id}/reject` (optionally with `{"reason":"Needs editing"}`). Approval invokes only a registered local mock that performs no network request. A successful mock result is persisted and read back before the run reaches `completed`. A definitive rejection is `failed`; an exception or ambiguous tool result is `outcome_uncertain` and is never automatically retried. `GET /agent/runs/{run_id}` returns the current run, approval decision, execution outcome, and audit events. Other tenants' follow-ups and runs return 404.

`POST /agent/runs/{run_id}/recover` handles an expired execution claim. It uses a PostgreSQL session advisory lock shared with the executor, so recovery cannot reclaim a live tool call even if its lease expires. A stale run with no durable tool-invocation marker becomes `ready_to_execute`; repeated approval stays read-only, and a separate explicit `POST /agent/runs/{run_id}/execute` resumes it. A stale run with the marker becomes `outcome_uncertain`, because the tool may have acted; approval and execute requests return that state without resending. Existing `executing` rows are conservatively backfilled with the invocation marker by migration `a73c9b14d520` because their prior tool-call phase cannot be proven.

Intent classification uses the local `ml/lead_intelligence` environment and saved `intent_classifier_60k` checkpoint. Configure `NUDGEFLOW_INTENT_PYTHON` and `NUDGEFLOW_INTENT_MODEL_PATH` to select another local interpreter/checkpoint. This integration runs local-only inference and never downloads weights. Missing artifacts or inference failures create the run with an explicit `unavailable` or `error` classification and no predicted label. Classification does not authorize or trigger execution; explicit approval remains required. The current checkpoint and available synthetic evaluation do not establish real-world customer-message accuracy. The ML subprocess currently starts per classification request; a production deployment should host model inference in a managed long-lived process. The local classifier, extraction provider, and draft provider are separate steps with separate outputs and failure statuses.

State transitions:

```text
awaiting_approval -> rejected
awaiting_approval -> executing -> completed | failed | outcome_uncertain
expired executing with no invocation marker -> ready_to_execute
ready_to_execute -> executing (only via explicit /execute)
expired executing after invocation marker -> outcome_uncertain
```

The conditional database claim, unique execution row per run, execution token, lease, and PostgreSQL advisory lock prevent duplicate tool invocation by repeated requests and keep recovery from interfering with a live execution. Audit events include recovery decisions and do not copy the proposed message into audit metadata. This workflow is not a WhatsApp integration and does not contact customers.

Apply the schema through the reviewed Alembic process before running the API:

```powershell
uv run alembic heads
uv run alembic upgrade head
```

Review migration `a73c9b14d520` before applying it to any shared environment.

## Frontend integration

There is no React, TypeScript, or Tailwind application in `frontend/` yet. A future frontend can use `http://127.0.0.1:8000` as its local API base URL, configure that URL through its own environment settings, and allow its exact origin in `NUDGEFLOW_CORS_ORIGINS`. Contact and follow-up response fields are described above and in `/docs`.

## Tests

```powershell
uv run pytest -v
```

The API tests use isolated in-memory SQLite databases with foreign-key enforcement. They do not require or modify a PostgreSQL database. PostgreSQL connectivity and migration execution should be checked separately against a configured development database.

The complete PostgreSQL migration chain, recovery lock, and agent classification persistence have opt-in tests. All require a **disposable loopback PostgreSQL database** whose name starts with `nudgeflow_test_`. The migration test additionally requires the database to be empty; it upgrades from empty, exercises extraction/draft and classification downgrade/re-upgrade, checks legacy backfills and recovery markers, rewinds to the pre-tenant revision, seeds legacy rows, and upgrades to the latest head. The agent recovery test checks that a live session advisory lock prevents stale recovery from claiming a run. The classification test checks persisted results, missing input, unavailable inference, and tenant isolation. Never point these tests at a development or production database.

For an already-created disposable database:

```powershell
$env:NUDGEFLOW_DATABASE_URL = "postgresql+psycopg://postgres@127.0.0.1:5432/nudgeflow_test_agent"
$env:NUDGEFLOW_MIGRATION_TEST_URL = $env:NUDGEFLOW_DATABASE_URL
$env:NUDGEFLOW_AGENT_TEST_URL = $env:NUDGEFLOW_DATABASE_URL
uv run --no-sync python -m pytest -q -p no:cacheprovider tests/test_tenant_migration_postgres.py tests/test_agent_recovery_postgres.py tests/test_agent_classification_postgres.py
uv run --no-sync python -m alembic check
```

The migration test leaves its disposable database at the latest schema head. The agent lock test requires that schema to be applied. Neither test creates or drops the database itself.

## Limitations and next steps

- `/health` reports that the API process is responding; it does not currently check PostgreSQL readiness.
- Authentication currently uses short-lived bearer tokens without refresh or revocation. Tenant roles are stored, but there is no invitation/member-management flow or role-based authorization policy yet.
- Real WhatsApp delivery, asynchronous LLM processing, automated recovery scheduling, and background processing are not implemented.

## Future AI architecture

Keep deterministic CRM rules in the FastAPI/domain layer. Add AI capabilities behind narrow service interfaces that accept authorized, tenant-scoped inputs and return validated outputs:

1. Add audit events and explicit user/organization authorization for every tool action before connecting agents to CRM writes.
2. Add a summarization service for lead and conversation summaries; persist generated text with provenance and treat it as untrusted content.
3. Add retrieval over business data only after tenant filters are enforced inside retrieval queries, not only in prompts.
4. Add controlled agent workflows as allow-listed tools that call the same validated business operations as the API. Require human approval for irreversible or sensitive actions.
5. Evaluate a separate Deep Learning inference service only when a concrete model or latency/scaling need justifies it; keep model serving isolated from transactional database access.

## Contributing

Create a focused feature branch, make a small change with tests, and open a pull request for review. Do not commit `.env`, credentials, local databases, or generated virtual environments. Include migration changes when modifying the database schema.


## WhatsApp Cloud API

Messaging uses the mock provider by default. To opt into real sends, configure these environment variables in the backend environment (never commit credentials):

```dotenv
NUDGEFLOW_WHATSAPP_ENABLED=true
NUDGEFLOW_WHATSAPP_ACCESS_TOKEN=<your Meta access token>
NUDGEFLOW_WHATSAPP_PHONE_NUMBER_ID=<your WhatsApp phone number ID>
NUDGEFLOW_WHATSAPP_API_VERSION=v25.0
```

The enable flag defaults to `false`; having a token alone does not enable real messaging. When enabled, newly created runs are explicitly bound to the WhatsApp Cloud API tool. Existing approved runs remain bound to their stored tool and are not migrated. The backend sends text messages through `https://graph.facebook.com/{version}/{phone-number-id}/messages`. Do not enable the flag until you have verified the intended recipient and message flow. This project does not send a real message as part of startup or tests.

Run the backend from this directory with `uv sync --dev` followed by `uv run uvicorn nudgeflow.main:app --reload`. Run all tests with `uv run python -m pytest -q`; run workflow tests with `uv run python -m pytest tests/test_agent_workflow.py -q`.

Meta setup still required: create/configure a Meta app with the WhatsApp product, obtain an access token with the required permissions, provision a WhatsApp Business Account and phone number, and add/verify permitted test recipients or production recipients as appropriate. Meta's successful API response and message ID indicate provider acceptance only; they do not confirm delivery. This backend currently has no delivery-status webhook endpoint. A future webhook step must configure a public HTTPS callback in Meta, verify the subscription challenge, validate webhook signatures, and persist status events before the product reports delivery.
