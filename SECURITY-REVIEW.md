# NudgeFlow AI — Read-Only Security and Code Audit

**Review date:** 2026-11-03
**Review mode:** Read-only source review; no tests, builds, migrations, installs, or live integrations were run.
**Conclusion:** No confirmed or suspected exploitable vulnerability met the reporting threshold in the paths reviewed. This is not a deployment certification or a complete dependency audit. Several confirmed architecture and schema gaps remain, described below.

## 1. Executive Summary

The review found no evidence sufficient to report an exploitable authentication, authorization, tenant-isolation, API, webhook-signature, or prompt-injection vulnerability in the reviewed paths. Authentication uses password hashing and validated JWTs; reviewed CRM and agent access paths scope records to the authenticated tenant; the WhatsApp webhook verifies the request signature and deduplicates webhook event records.

The most important confirmed gaps are that the webhook route does not persist inbound messages through the tenant-aware persistence helper, and three inbound SQLAlchemy models are not represented in the current migrations or loaded into Alembic metadata. These are currently functional/schema gaps, not demonstrated cross-tenant vulnerabilities. The approval UI also describes execution as mock-only even though the backend can select the live WhatsApp provider.

The source review was targeted rather than line-by-line across every file. No dependency advisory scan or runtime validation was performed. See “Scope limits” for items not inspected.

## 2. Overall Security Assessment

**Assessment: Not ready to treat as deployment-cleared based on this review alone.** No exploitable vulnerability was confirmed in reviewed code, but this conclusion is bounded by the scope limitations below. In particular, inbound persistence/migrations need resolution and production deployment controls, dependency advisories, and actual database migration state have not been verified.

The report distinguishes confirmed observations from vulnerabilities: the architecture and data-flow gaps below are not assigned a CWE or represented as exploit findings absent a demonstrated security impact.

## 3. Critical Vulnerabilities

None identified in the reviewed paths.

## 4. High-Severity Vulnerabilities

None identified in the reviewed paths.

## 5. Medium-Severity Vulnerabilities

None identified in the reviewed paths.

## 6. Low-Severity Vulnerabilities

None identified in the reviewed paths. The table below summarizes informational architecture/data-flow findings; the ⚪ LOW indicator is used to match the requested summary format and does **not** classify these observations as security vulnerabilities.

| # | Severity | File | Lines | Vulnerability | Confidence |
|---|----------|------|-------|---------------|------------|
| 1 | ⚪ LOW | [webhooks.py](./backend/nudgeflow/src/nudgeflow/routers/webhooks.py) | 131-142, 223-235 | Informational: webhook event handling does not call inbound-message persistence; no exploitable vulnerability demonstrated. | 10/10 |
| 2 | ⚪ LOW | [env.py](./backend/nudgeflow/migrations/env.py) | 14 | Informational: inbound models are not imported into Alembic metadata; schema gap, not an exploit finding. | 10/10 |
| 3 | ⚪ LOW | [AgentRunPage.tsx](./frontend/src/pages/agent/AgentRunPage.tsx) | 91, 175 | Informational: approval copy says mock execution although backend may select live WhatsApp sending. | 10/10 |
| 4 | ⚪ LOW | [message_content.py](./backend/nudgeflow/src/nudgeflow/services/agent/message_content.py) | 167-169, 207-213 | Informational: configured LLM flow sends customer-message content to an external provider; privacy/retention safeguards were not established by this review. | 10/10 |
| 5 | ⚪ LOW | [workflow.py](./backend/nudgeflow/src/nudgeflow/services/agent/workflow.py) | 190-310 | Informational: no authoritative order/inventory decision path was found in the reviewed workflow. | 8/10 |

## 7. Architecture and Logic Issues

### INFO-01 — Inbound persistence is disconnected

- **Status:** Confirmed architecture gap; not a demonstrated vulnerability.
- **Evidence:** [webhooks.py](./backend/nudgeflow/src/nudgeflow/routers/webhooks.py), lines 131-142 and 223-235, validates and records webhook events but does not invoke `persist_inbound_message`. The helper exists in [persistence.py](./backend/nudgeflow/src/nudgeflow/services/inbound/persistence.py), line 19, and tenant-aware sender matching is in [identity.py](./backend/nudgeflow/src/nudgeflow/services/inbound/identity.py), line 25.
- **Impact:** Inbound message text is not stored through that helper, and the helper's tenant/channel/contact mapping is not exercised by the webhook endpoint.
- **Recommended remediation:** Connect the persistence service after signature validation and add endpoint tests for tenant/channel mapping, contact resolution, unmapped identities, and duplicate/retried events.

### INFO-03 — Approval copy may misidentify the messaging provider

- **Status:** Confirmed UX/consent risk; not an authorization bypass.
- **Evidence:** [AgentRunPage.tsx](./frontend/src/pages/agent/AgentRunPage.tsx), lines 91 and 175, uses mock-only approval wording. [workflow.py](./backend/nudgeflow/src/nudgeflow/services/agent/workflow.py), lines 286-289, can select `whatsapp_cloud_api` when WhatsApp is enabled; lines 483-500 and 697-701 execute the selected tool after approval.
- **Attack/scenario:** An approver may believe approval only triggers a mock action when a real external message will be sent. This requires live WhatsApp to be enabled and approval to occur; no unauthorized send was demonstrated.
- **Impact:** An operator could unintentionally approve a real customer communication.
- **Recommended remediation:** Show the actual selected provider and clearly label live external sends before approval; test the UI with live sending enabled.

## 8. Database and Migration Issues

### INFO-02 — Inbound models lack migrations and Alembic registration

- **Status:** Confirmed schema/migration gap.
- **Evidence:** The `whatsapp_business_channels`, `whatsapp_conversations`, and `whatsapp_inbound_messages` models are declared in [whatsapp_channel.py](./backend/nudgeflow/src/nudgeflow/models/whatsapp_channel.py), [conversation.py](./backend/nudgeflow/src/nudgeflow/models/conversation.py), and [inbound_message.py](./backend/nudgeflow/src/nudgeflow/models/inbound_message.py), respectively (each at lines 12-15). The webhook-events revision [834c9b14cbc9_add_whatsapp_webhook_events.py](./backend/nudgeflow/migrations/versions/834c9b14cbc9_add_whatsapp_webhook_events.py), line 23, creates only the webhook-events table. [env.py](./backend/nudgeflow/migrations/env.py), line 14, and [models/__init__.py](./backend/nudgeflow/src/nudgeflow/models/__init__.py), lines 1-16, do not import the three inbound models into the configured metadata.
- **Impact:** A migration generated from this metadata will not create those tables; inbound persistence cannot be relied on against a database created from the reviewed revisions.
- **Recommended remediation:** Register all mapped models in migration metadata, add explicit revisions for the missing tables and constraints, and verify the resulting database schema against the metadata before enabling persistence.

No live database schema was available for comparison. Thus, the conclusion is about the checked-in model/migration state, not an assertion about a deployed database.

## 9. WhatsApp Webhook Issues

- **Signature validation:** The reviewed POST path validates the raw request body using HMAC-SHA256 and constant-time comparison before parsing, in [webhooks.py](./backend/nudgeflow/src/nudgeflow/routers/webhooks.py), lines 52-82 and 131-151.
- **Event idempotency:** Webhook event identity has a uniqueness constraint in [webhook.py](./backend/nudgeflow/src/nudgeflow/models/webhook.py), lines 15-32, and the route handles duplicate event records in [webhooks.py](./backend/nudgeflow/src/nudgeflow/routers/webhooks.py), lines 211-240 and 267-295.
- **Confirmed functional gap:** The endpoint does not invoke inbound-message persistence (INFO-01). The test named `test_inbound_message_recorded_idempotently` verifies webhook event persistence, not an inbound-message row; see [test_whatsapp_webhooks.py](./backend/nudgeflow/tests/test_whatsapp_webhooks.py), lines 327-370.
- **Logging observation:** The reviewed endpoint records event metadata without logging payload contents or sender numbers.
- **Remaining uncertainty:** No live Meta integration, concurrent duplicate-delivery test, or runtime transaction/rollback test was run. Therefore this review does not certify race behavior under production database concurrency.

## 10. AI and Prompt Injection Risks

### INFO-04 — Customer-message content is sent to the configured LLM provider

- **Status:** Confirmed data flow; privacy-governance gap, not a transport vulnerability.
- **Evidence:** [message_content.py](./backend/nudgeflow/src/nudgeflow/services/agent/message_content.py), lines 167-169 and 207-213, and [llm_client.py](./backend/nudgeflow/src/nudgeflow/services/agent/llm_client.py), lines 9 and 35-49.
- **Impact/scenario:** When the optional integration is configured, customer message content is transmitted to the external provider. The inspected material did not establish customer-facing disclosure, retention policy, or provider-specific privacy controls.
- **Recommended remediation:** Document data sent and applicable provider retention/processing terms, minimize the content shared, and confirm the integration meets customer-data requirements before enabling it.

The reviewed extraction/drafting prompts explicitly treat customer text as untrusted and warn against inventing pricing, stock, or availability. Generated text remains approval-gated in the reviewed workflow. No unsafe LLM tool execution or authorization bypass was confirmed in those paths.

### INFO-05 — No authoritative order or inventory decision path found

- **Status:** Confirmed product-scope limitation in the reviewed flow; not an exploit finding.
- **Evidence:** The reviewed agent workflow drafts follow-up messages in [workflow.py](./backend/nudgeflow/src/nudgeflow/services/agent/workflow.py), lines 190-310. Its prompt cautions against inventing price, stock, or availability in [message_content.py](./backend/nudgeflow/src/nudgeflow/services/agent/message_content.py), `DRAFT_SYSTEM_PROMPT`. No authoritative order/inventory model or deterministic availability validation was found in the inspected paths.
- **Impact:** LLM-drafted statements should not be treated as an authoritative order, price, or stock decision.
- **Recommended remediation:** Keep AI output as a human-reviewed proposal unless and until a server-side source of truth and deterministic validation are implemented.

## 11. Dependency Vulnerabilities

No dependency advisory/CVE scan was performed. The lockfile review was limited to searches for Git-sourced dependency references; no such references were found in the inspected searches. This is not evidence that dependencies are free of known vulnerabilities or that every transitive package is current. No dependencies were installed or updated.

## 12. Missing Tests

The following test coverage should be added or confirmed:

1. Webhook endpoint-to-inbound-message persistence, including valid and invalid tenant/channel mapping, contact resolution, duplicate delivery, and retry behavior.
2. Alembic metadata coverage for every mapped model and a migration-to-current-metadata comparison against a disposable test database.
3. Concurrent duplicate webhook delivery and transaction rollback behavior under the supported PostgreSQL configuration.
4. Approval UI behavior showing the actual provider and warning for live external sends.
5. Explicit privacy/data-minimization expectations for content sent to the LLM provider.
6. Tests proving order, price, and inventory outcomes cannot be authorized by LLM output alone if those capabilities are added.

Existing tests were not run as part of this read-only review.

## 13. Recommended Fixes in Priority Order

1. Register inbound models in Alembic metadata and add migrations for channel, conversation, and inbound-message tables.
2. Wire the signed webhook route to tenant-aware inbound persistence; add endpoint-level tests for mapping, retries, and duplicate delivery.
3. Correct approval UI copy to identify mock versus live WhatsApp execution before the operator approves.
4. Document and minimize customer data sent to the LLM provider; establish applicable privacy and retention controls before enabling it.
5. Keep order/inventory decisions deterministic and server-authoritative; do not treat generated copy as order or availability confirmation.
6. Before deployment, run dependency advisory scanning and verify TLS, security headers, secret injection, CORS, and migration state in the target environment.

## Review Scope and Limitations

### Validation performed

- Read-only inspection of repository status, selected source, routes, models, migrations, tests, documentation, and configuration.
- Targeted searches for unsafe HTML sinks, shell execution, deserialization patterns, URL/network handling, secret/logging indicators, tenant-scoping patterns, and Git-based dependency references.
- No tests, builds, migrations, dependency installs, CVE scans, or live integrations were run. No source changes were made as part of the audit.

### Not inspected or not fully inspected

- The local ignored `backend/nudgeflow/.env` contents were not read.
- Generated caches and installed environments such as `.uv-cache`, `.pytest_cache`, `node_modules`, and virtual environments were not inspected.
- Binary/local model checkpoints and dataset CSV contents were not inspected.
- Not every backend test, frontend page/style file, or ML utility was read line by line. Auth, ownership, agent workflow/content, WhatsApp tool/webhook tests, the PostgreSQL tenant-migration test, core ML data/training/inference paths, and frontend searches for common injection sinks received targeted review.
- No live database schema was available for comparison.
- No deployment manifest, container configuration, or CI workflow was found in the inspected top-level inventory; deployment-specific TLS termination, security headers, secret injection, and CORS could not be verified.
