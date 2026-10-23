# NudgeFlow AI — Project Status Report

**Audit date:** 22 October 2026  
**Repository audited:** `D:\Projects\Nudge-Flow`  
**Branch / commit:** `main` at `170ca7a` (`Expand intent classification dataset and training pipeline`)  
**Working-tree state before this report:** clean; `main` tracked `origin/main`.

## Executive summary

The repository contains a tested FastAPI backend foundation for user accounts, contacts, and due-dated follow-ups, plus a separate PyTorch/Hugging Face intent-classification experiment. It does **not** yet demonstrate the product described by the supplied proposal: there is no frontend source, no tenant/workspace model, no interaction timeline, no reminders worker, no agent planner/policy/executor/verifier/audit workflow, and no WhatsApp integration. The ML experiment is not connected to the API.

The backend tests and ML unit tests pass in the existing environments. The current saved 60-example synthetic challenge set evaluates at **49/60 (81.67%)**, with **4/10 service-enquiry** examples classified correctly. That set has already influenced development and is not an independent benchmark. The previously reported 99.97% validation and 99.94% test accuracies, the exact 36k/12k/12k split, and the reported one-epoch RTX 2050 training run could not be independently verified: no training/evaluation logs or saved split manifest were present. They must remain historical observations, not accepted performance evidence.

The shortest proposal-aligned route is to establish a reproducible PostgreSQL development/migration workflow and tenant boundary, connect a small frontend to the existing API, then deliver one deterministic end-to-end workflow with mock messaging, explicit approval, persistence, verification, and an audit trail. Do not introduce live messaging or treat synthetic model scores as customer performance before those steps.

## Scope, source limitations, and method

The audit used the repository state at the commit above, component documentation, source, migrations, tests, environment templates, tracked-file inventory, and the read-only checks listed below. The user-supplied audit brief includes the project description, five-phase roadmap, and FR-01 through FR-12 names. The original proposal/technical-design PDF was not found in the repository. Therefore this report maps to the supplied summary and FR titles; detailed acceptance clauses that exist only in the PDF remain unavailable and are not invented.

No application source, dependencies, lockfiles, database, datasets, model artifacts, or configuration were changed. No migration was applied and no live account or messaging service was contacted. The actual `.env` contents were not read or copied. A local ignored CSV is noted by filename and aggregate counts only; its messages were not inspected.

## Project purpose and repository architecture

The supplied proposal describes a WhatsApp-first, AI-powered CRM for micro-businesses, with customer management, NLP/deep learning, and a controlled agentic workflow. Its intended order is CRM foundation, one safe end-to-end agent workflow, incremental AI, official WhatsApp integration, and deployment/pilot.

| Area | What exists | Evidence |
| --- | --- | --- |
| Backend | Python 3.11+ FastAPI app; SQLAlchemy models; PostgreSQL configuration; Alembic migrations; Pydantic settings/schemas; JWT authentication. | `backend/nudgeflow/pyproject.toml`; `backend/nudgeflow/README.md:3-12, 16-33` |
| Backend APIs | Auth router is included from the app. Contact and follow-up endpoints are defined in `main.py`. | `backend/nudgeflow/src/nudgeflow/main.py:21-34, 92-98, 102-253`; `backend/nudgeflow/src/nudgeflow/routers/auth.py:32-90` |
| Database | User, contact, and follow-up models; five Alembic revisions for users, contacts, follow-ups, ownership, and follow-up status constraints. | `backend/nudgeflow/src/nudgeflow/models/`; `backend/nudgeflow/migrations/versions/` |
| Frontend | The repository's `frontend` directory is empty; no package manifest, application source, build/test scripts, API client, route, page, or component was found. | Tracked-file inventory contains no frontend files; directory inspection found no entries. |
| ML | Separate Python 3.11 workspace with NumPy, pandas, scikit-learn, PyTorch, Transformers, source package, tests, CSVs, reports guidance, and ignored local model artifacts. | `ml/lead_intelligence/pyproject.toml`; `ml/lead_intelligence/README.md`; `ml/lead_intelligence/src/lead_intelligence/` |
| Agent / integrations / operations | No meaningful agent workflow, WhatsApp client/webhook, worker, deployment, container, CI, or monitoring implementation was found in tracked files. | Tracked-file inventory and source search; no such directories/modules are present. |

There is no repository-root README. Component-level backend and ML READMEs are the main project documentation. Both components have their own `uv.lock`; their Python environments and dependencies are separate. The backend dependency set does not include PyTorch/Transformers.

## Functional requirements traceability

Statuses are conservative and refer to the scope implied by the supplied FR titles. A partial status means useful code exists but the full requirement cannot be accepted as complete.

| Requirement | Status | Evidence and unmet acceptance |
| --- | --- | --- |
| **FR-01 Authentication and tenant management** | **PARTIAL** | Registration/login, Argon2 password hashing, signed bearer tokens, current-user lookup, per-user contact scoping, and ownership tests exist (`routers/auth.py`, `security.py`, `tokens.py`, `dependencies.py`, `tests/test_auth.py`, `tests/test_ownership.py`). The data model is user-owned, not organization/tenant membership; no tenant model, roles, membership/admin flow, or tenant migration exists. |
| **FR-02 Customer records** | **PARTIAL** | Authenticated contact create/list/get/update/delete, pagination, validation, and ownership checks exist (`main.py:102-170`; `tests/test_contacts_api.py`, `tests/test_ownership.py`). The repository has no frontend, customer profile/history timeline, broader CRM fields, or tenant boundary. |
| **FR-03 Interaction timeline** | **NOT IMPLEMENTED** | No interaction/message-history model, migration, endpoint, or UI exists. Current models are user, contact, and follow-up. |
| **FR-04 Tasks and reminders** | **PARTIAL** | Follow-up CRUD, due date, notes, and pending/completed status exist (`main.py:174-253`; `tests/test_follow_ups_api.py`). There is no scheduler, reminder delivery, recurring task support, or worker. |
| **FR-05 Conversation intelligence** | **PARTIAL** | A six-class intent taxonomy, synthetic labeled CSVs, data validation, split utilities, model loader, and training script exist (`taxonomy.py`, `data.py`, `splitting.py`, `model.py`, `train.py`). There is no real representative conversation corpus, structured extraction, summarization, or inference integration. |
| **FR-06 AI message drafting** | **NOT IMPLEMENTED** | No drafting service, prompt/policy layer, endpoint, UI, or tests were found. |
| **FR-07 Agent execution** | **NOT IMPLEMENTED** | No typed plan, allow-listed tool registry, planner, runner/state machine, persisted run, or tool execution workflow was found. |
| **FR-08 Policy and approval** | **NOT IMPLEMENTED** | No agent-specific eligibility/consent policy or explicit human approval gate exists. API authentication and ownership checks are not an outbound-action policy system. |
| **FR-09 Messaging integration** | **NOT IMPLEMENTED** | No WhatsApp Cloud API client, webhook verification, idempotent event handler, outbound approval/template flow, or delivery-status handling exists. Backend README explicitly lists WhatsApp as future work (`backend/nudgeflow/README.md:120-124`). |
| **FR-10 Verification and audit** | **NOT IMPLEMENTED** | No persisted workflow event/audit trail, mock-send record, outcome verifier, retry/recovery path, or operator-facing audit view exists. |
| **FR-11 Search and analytics** | **NOT IMPLEMENTED** | List endpoints provide limit/offset only. No search endpoint, reporting, analytics, or dashboard is present (`backend/nudgeflow/README.md:65-83`). |
| **FR-12 Model evaluation** | **PARTIAL** | An evaluation helper computes macro-F1, per-class precision/recall, and confusion matrix (`ml/lead_intelligence/src/lead_intelligence/evaluation.py`). The current train/test/challenge CLI scripts mainly print accuracy and per-class accuracy; the helper is not wired into those scripts or persisted reports. Current data is synthetic and challenge results are development-contaminated. |

## Five-phase roadmap status

| Proposal phase | Status | Evidence / remaining acceptance |
| --- | --- | --- |
| 1. Foundation | **PARTIAL** | Backend account/contact/follow-up APIs, migrations, configuration, and passing unit/API tests exist. Frontend, tenant model, real PostgreSQL migration verification, and end-to-end CRM acceptance are missing. |
| 2. Deterministic agent | **NOT IMPLEMENTED** | No plan schema, tool registry, policy engine, runner, verifier, mock messaging, persisted state, or audit trail exists. |
| 3. AI/ML capabilities | **PARTIAL** | Intent model training and evaluation scaffolding exist in a standalone workspace. No integrated inference, representative real-data evaluation, extraction, summaries, retrieval, or drafting exists. |
| 4. Official messaging | **NOT IMPLEMENTED** | No WhatsApp API/webhook integration or delivery state handling exists. |
| 5. Deployment and pilot | **NOT IMPLEMENTED** | No deployment/CI/container configuration, monitoring, backup/restore procedure, acceptance test suite, or pilot evidence was found. |

## Backend and database status

The FastAPI app registers the authentication router and configures CORS in `main.py:21-34`; it exposes a process-level `/health` route at `main.py:97-98`. Contact handlers are at `main.py:102-170`; follow-up handlers are at `main.py:174-253`. Follow-ups are owned indirectly through their contact. Tests cover authentication, route validation, ownership isolation, models, config, token/security behavior, and health.

Password hashing uses Argon2 and tokens are signed JWT access tokens. The README describes a 30-minute default access-token lifetime and production checks for signing-key length and debug mode (`backend/nudgeflow/README.md:39-41`). Contact ownership is per user. The ownership migration intentionally leaves legacy contacts unassigned, and authenticated queries do not expose them until explicitly assigned (`backend/nudgeflow/README.md:104-106`). No organization-level tenant isolation or RBAC is implemented.

The backend test fixture overrides database access with in-memory SQLite and creates/drops tables for tests (`backend/nudgeflow/tests/conftest.py`). These passing tests do not verify PostgreSQL connectivity, Alembic upgrade behavior on PostgreSQL, deployment configuration, or data backfill. The documented `/health` route is not a DB readiness check; access tokens have no refresh/revocation mechanism, organization membership, or role-based access control (`backend/nudgeflow/README.md:118-124`). No migration was run during this audit.

## Frontend and integration status

No frontend code or manifest is present, so there is no React/TypeScript app to inspect or build. The backend README documents intended frontend integration, but no frontend-to-backend communication can currently be demonstrated. There are no frontend tests, type checks, or build scripts to run. The app cannot yet deliver the user-facing workflow or accessibility/usability acceptance described by the proposal.

## ML pipeline and model-evaluation audit

### Taxonomy and data

The six canonical labels are `booking_enquiry`, `purchase_enquiry`, `service_enquiry`, `complaint_support`, `cancellation`, and `other_uncertain` (`ml/lead_intelligence/src/lead_intelligence/taxonomy.py`). The documented CSV schema is `message,intent`; validation checks required columns, blank values, known labels, and conflicting normalized duplicates (`data.py`). The README describes character 2–5 gram TF-IDF near-duplicate detection and grouped stratified splits with seed 42 and a nominal 60/20/20 ratio (`ml/lead_intelligence/README.md:22, 39-43`).

Read-only count checks found:
- `nudgeflow_intents_60k.csv`: 60,000 rows, 10,000 per class.
- `nudgeflow_challenge_v1.csv`: 60 rows, 10 per class.
- `synthetic_dev.csv`: 36 rows, 6 per class.
- A local ignored `nudgeflow_intents_v1.csv`: 240 rows, 40 per class. This file is not in tracked files and is not documented in `data/README.md`; its provenance and intended use are **unverified**. Only its row/label counts were inspected.

The data README explicitly identifies the 60k and challenge examples as synthetic and warns that the challenge set has already been used during development (`ml/lead_intelligence/data/README.md:3-39`). The tracked synthetic fixture is for pipeline tests, not model evidence. There is no tracked data-generation script, so the generation process and template families cannot be independently audited. The 60k and challenge files are tracked synthetic files; generated checkpoints and arbitrary CSVs are ignored by `ml/lead_intelligence/.gitignore`.

### Splits, training, and evaluation

`splitting.py` normalizes messages, connects exact duplicates and character n-gram cosine matches above the configured threshold, rejects conflicting duplicate-group labels, and uses `StratifiedGroupKFold` for outer test and inner validation partitions. This is a sensible leakage-control direction, but the split ratios are approximate, no split indices/checksum are saved by training, and there is no source data generator to check whether broader template families cross partitions. Near-duplicate links are joined transitively. The implementation uses brute-force nearest-neighbor search and builds a radius graph; 60k-scale runtime/memory were not benchmarked. Thus duplicate protection is by a defined heuristic, not proof that all semantically related examples are isolated.

`train.py` specifies one epoch, batch size 4, learning rate `2e-5`, seed-controlled split creation, and writes model/tokenizer artifacts to `models/intent_classifier_60k`. It creates a validation split but the training loop does not evaluate validation metrics or use early stopping/model selection. The code exists, but no saved run log or split manifest ties the currently present checkpoint to the reported RTX 2050 run or exact 36,000/12,000/12,000 counts. Both `models/intent_classifier` and `models/intent_classifier_60k` directories are present locally with 267,844,872-byte weight files; model artifacts are ignored/untracked, so their provenance and reproducibility are not established by Git.

There is a material naming mismatch: `evaluate.py:1` describes evaluation on the validation set, but the code selects `splits["test"]` and prints “TEST RESULTS” (`evaluate.py:34-44, 88-124`). It is test-set evaluation. It reports accuracy/per-class accuracy and prints examples; it does not invoke the macro-F1/precision/recall/confusion-matrix helper. No evaluation JSON or logs are stored in tracked `reports/`.

### Metrics and scientific limits

The previously reported 99.97% validation and 99.94% test accuracies are recorded here as **reported observations only**. They were not reproducible from checked-in logs or a split manifest, and the current test CLI has the validation/test naming mismatch described above. The exact 36k/12k/12k partition is not independently verified; the split helper documents approximate ratios.

The challenge evaluation was run read-only against the existing local checkpoint and current challenge CSV using the existing ML environment. It loaded the checkpoint on CUDA and returned:
- Overall: **49/60 (81.67%)**.
- Booking: 9/10; purchase: 9/10; service: **4/10**; complaint/support: 10/10; cancellation: 10/10; other/uncertain: 7/10.

The 81.67% result matches the reported observation for the checkpoint currently at `models/intent_classifier_60k`. The evaluator prints misclassified message text; that text was redacted from the captured audit output. The set is only 60 synthetic examples, has already influenced development, and is therefore diagnostic rather than an independent benchmark. None of these results establishes accuracy on real customer conversations or lead conversion.

The experiment currently has no FastAPI inference adapter or prediction endpoint. A future inference boundary should load a versioned model/tokenizer once, validate input/output and return labels/scores through a small service interface; keep training dependencies and scripts out of request handling where practical. Do not promote the ignored local checkpoint without a provenance manifest, representative evaluation, and clear operational behavior.

## Agent workflow and safety controls

The proposal's Observe → Understand → Plan → Policy → Execute → Verify → Report workflow cannot execute end-to-end in this repository. There are no typed agent plans, tenant-scoped history retrieval service for runs, allow-listed tools, deterministic action policy, human approval gate, mock-send adapter, idempotency key, persisted run state, verifier, retry/recovery logic, audit trail, or UI. Existing API ownership checks protect CRUD records but do not authorize a future outbound message. The first demonstration should remain a single deterministic workflow with mock sending; real messaging should wait until approval, idempotency, verification, and failure-path tests pass.

## Non-functional requirements, risks, and technical debt

| Area | Assessment | Evidence / gap |
| --- | --- | --- |
| Security | **PARTIAL** | Argon2, signed expiring bearer tokens, input schemas, explicit CORS settings, and user-level record scoping exist. No tenant membership/RBAC, token refresh/revocation, or outbound consent/approval policy was found. |
| Tenant isolation | **PARTIAL** | User ownership and cross-user isolation tests exist; proposal-level organization/tenant isolation is absent. |
| Reliability | **PARTIAL** | DB transactions and basic process health exist. Health does not check database readiness; no worker retry, idempotency, recovery, or backup/restore evidence exists. |
| Observability | **NOT IMPLEMENTED** | No metrics, traces, monitoring configuration, or agent audit events were found. |
| Usability / accessibility | **UNVERIFIED** | No frontend exists to assess. |
| Performance | **UNVERIFIED** | No API/load or inference latency benchmarks. The ML duplicate graph uses brute-force nearest-neighbor search and was not benchmarked at 60k scale. |
| Maintainability | **PARTIAL** | Separate backend/ML projects and tests are organized, but routes are concentrated in `main.py`; ML run provenance is not persisted; no lint/type-check/CI configuration was found. |
| Privacy | **PARTIAL** | Tracked example corpora are documented synthetic. A local ignored 240-row CSV has unknown provenance; actual `.env` values were not inspected. No real-customer data governance or retention path is documented. |
| Cost control | **UNVERIFIED** | No model serving/runtime budget, usage accounting, or messaging cost controls exist. |
| Auditability | **NOT IMPLEMENTED** | No persisted agent actions, approvals, tool results, or verified outcome records exist. |

Key delivery risks are: user ownership may be mistaken for tenant isolation; the UI/API contract has not been exercised by a client; follow-up records do not cause reminders; the agent safety chain is absent; synthetic/template performance may overstate generalization; the challenge set is no longer independent; the 240-row local CSV lacks documented provenance; and local ignored checkpoints are not reproducible from the tracked repository. The original proposal PDF and production PostgreSQL configuration were not available for deeper acceptance checks.

## Prioritized implementation backlog

### P0 — Required to demonstrate the core workflow safely

1. **Settle tenant semantics and make local DB/migrations reproducible.** Decide whether accounts own isolated workspaces or are members of organizations; add the smallest required tenant/membership model and scoped queries, with an explicit safe plan for legacy unassigned contacts. Validate Alembic revisions against a disposable PostgreSQL database and add migration/ownership acceptance coverage. Do not infer or backfill production ownership.
2. **Deliver a minimal connected CRM surface.** Add login, contact list/detail/create/update, follow-up list/create/update, and clear API error states. Verify a user can complete those flows against the backend while cross-user records stay inaccessible.
3. **Build one deterministic mock-send vertical slice.** From an eligible due follow-up, retrieve authorized customer context, create a typed plan, enforce deterministic eligibility/consent policy, request explicit human approval, execute an idempotent mock send, persist state/results, verify the stored outcome, and display an audit trail. Test denial, duplicate trigger, tool error, timeout/retry, and ownership failure paths.

### P1 — Required to complete a usable MVP

- Add DB readiness/startup checks, structured operational logs, migration smoke tests, backup/restore steps, and CI for the verified test suites.
- Add timeline persistence and real reminder scheduling only once their product semantics and failure behavior are specified.
- Define a versioned, isolated intent-inference interface; collect representative labeled messages with privacy controls; document splits/manifests; compare against a simple baseline; report macro-F1, per-class precision/recall, confusion matrix, and measured latency. Keep validation for model/threshold selection and test untouched for final measurement.

### P2 — Valuable after the vertical slice works

- Add structured entity extraction, conversation summaries, search, and analytics incrementally against representative requirements and measured user needs.
- Add end-to-end acceptance tests covering UI, API, database, policy, mock execution, and audit display.

### P3 — Optional future work after safety and operations are proven

- Integrate official WhatsApp Business Platform Cloud API with verified webhooks, idempotent inbound handling, approved outbound message/template rules, and delivery-status processing.
- Deploy a small pilot with managed secrets, monitoring/alerting, backup/restore rehearsal, operational runbooks, and explicit acceptance gates. Avoid introducing microservices, vector search, multi-agent orchestration, or larger models without measured need.

## Recommended next three implementation steps

1. **Tenant model plus reproducible PostgreSQL verification** (prerequisite: agree whether “tenant” means one user-owned workspace or a shared organization). Acceptance: a disposable PostgreSQL database upgrades through all revisions; tests prove two tenants cannot read/write each other's contacts/follow-ups; legacy unassigned rows are handled only by an explicit migration/assignment plan.
2. **Minimal frontend-to-backend CRM integration** (prerequisite: stable auth/tenant/API contract). Acceptance: register/login, create/list/update contacts, create/complete follow-ups in the UI; unauthorized and cross-tenant requests are handled safely; browser-to-API integration tests pass.
3. **Single deterministic agent workflow with mock messaging** (prerequisite: tenant-scoped CRM data and frontend approval surface). Acceptance: a due follow-up flows through typed plan, policy, explicit approval, idempotent mock execution, persisted outcome verification, and audit display; denial, duplicate, failure, and recovery tests pass.

## Reproducible commands and validation results

The existing READMEs document these startup commands from `backend/nudgeflow` after configuring a local PostgreSQL database and `.env`:

```powershell
uv sync --dev
uv run alembic upgrade head
uv run uvicorn nudgeflow.main:app --reload
```

They are documented commands only; startup and database migration were **not** run in this audit. The README warns that tests use in-memory SQLite and do not validate PostgreSQL connectivity/migrations (`backend/nudgeflow/README.md:43-47, 118`).

Executed with existing environments and `--no-sync` to avoid dependency installation:

| Command (working directory) | Result |
| --- | --- |
| `uv run --no-sync python -m pytest -q -p no:cacheprovider` (`backend/nudgeflow`) | Exit 0; **56 passed**. |
| `uv run --no-sync python -m pytest -q -p no:cacheprovider` (`ml/lead_intelligence`) | Exit 0; **16 passed**. |
| `python -m lead_intelligence.evaluate_challenge` using `ml/lead_intelligence/.venv` (output message text redacted) | Exit 0; **49/60, 81.67%**; service enquiry 4/10. |
| Read-only pandas CSV count check using the existing ML environment | Exit 0; counts listed in the ML section. |

The backend tests use in-memory SQLite, and ML unit tests exercise pipeline components, not a full model-training run. No frontend test/build/typecheck or PostgreSQL migration test is available to run.

## What was inspected and what remains unverified

Inspected Git branch/status/history and tracked repository inventory; backend project configuration, README, auth/security/config/database/model/API source, migrations, and test fixtures; ML project configuration/lockfile, README/data documentation, taxonomy, validation, split, tokenization, model, training/evaluation code, tests, reports guidance, CSV aggregate counts, and local checkpoint presence; frontend directory; and evidence for absent agent, integration, deployment, CI, and monitoring components.

Not verified: original proposal PDF details beyond the supplied summary/FR titles; PostgreSQL connectivity or migrations; production environment configuration; frontend behavior (none exists); exact stored split sizes/indices; training run hardware, run provenance, and 99.97%/99.94% metrics; full 60k split runtime; template-family leakage; local 240-row CSV provenance/content; checkpoint integrity/reproducibility from Git; deployment, operational recovery, and real-customer generalization. No secret values or customer message text are included in this report.

