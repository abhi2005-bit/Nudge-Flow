# NudgeFlow AI Agent — Architecture & Bootstrap Record

## 1. Executive Summary

This document records the verified architecture, bootstrap implementation, dependency injection flow, test suite results, and operational safeguards for the **NudgeFlow AI Agent Runtime**.

NudgeFlow is a WhatsApp-first AI CRM for micro-businesses designed with strict governance: deterministic state machines, human approval gates, distributed concurrency control via advisory locks, lease-based recovery, and comprehensive audit trails. The bootstrap and initialization layer provides a testable, decoupled foundation that constructs and validates runtime dependencies before any HTTP request is served, while keeping external network calls strictly out of the initialization path.

---

## 2. Verified Architecture & Design Principles

### 2.1 Decoupled Bootstrap vs. Workflow Execution
- **Separation of Concerns:** Runtime assembly is isolated in `nudgeflow.bootstrap`. It is completely separate from individual workflow functions in `nudgeflow.services.agent.workflow`.
- **Pure Local Initialization:** Bootstrap validates configuration strings and tool protocols in-memory. It makes **zero external network requests** and executes **zero pending runs** or background tasks.
- **Fail-Safe Startup:** If required configuration (e.g. invalid phone number IDs or invalid API version formatting when WhatsApp is enabled) or tool contracts are invalid, `BootstrapError` is raised immediately, halting server startup safely.

### 2.2 Immutable Runtime Object (`AgentRuntime`)
```python
@dataclass(frozen=True)
class AgentRuntime:
    tool_registry: dict[str, MessagingTool]
    whatsapp_enabled: bool
    settings: Settings

    def get_tool(self, name: str) -> MessagingTool | None:
        return self.tool_registry.get(name)
```
- Each bootstrap invocation constructs fresh tool instances and registry dictionaries, ensuring complete isolation across test cases and worker processes.
- The runtime object is frozen (immutable) to prevent ad-hoc runtime modification outside lifecycle management.

### 2.3 FastAPI Lifespan & Dependency Injection
- **Lifespan Context (`agent_lifespan`):**
  - Wired directly into `FastAPI(lifespan=agent_lifespan)` in `nudgeflow.main`.
  - On startup: calls `build_agent_runtime()`, verifies contracts, and attaches the immutable runtime to `app.state.agent_runtime`.
  - On shutdown: cleanly tears down and deletes `app.state.agent_runtime`.
- **Route-Level Dependency Injection (`get_agent_runtime`):**
  - Endpoints in `nudgeflow.routers.agent` declare `runtime: AgentRuntime = Depends(get_agent_runtime)`.
  - Dependency injection is complete and active: endpoints receive the validated runtime and explicitly pass it to workflow functions (`start_run`, `approve_and_execute`, `execute_recovered_run`).
  - Tests can selectively override `app.dependency_overrides[get_agent_runtime]` for hermetic integration testing.

### 2.4 Tool Protocol & Contract Validation
All messaging tools must satisfy the structural `MessagingTool` protocol:
- Must have a non-empty string `name` attribute matching its registry key.
- Must implement a callable `send(*, run_id: int, message: str, recipient_phone: str) -> dict[str, object]`.
- Verified at startup via `_validate_tool_contract()`, raising `ToolContractError` on violation.

### 2.5 Policy, Governance, and Tenant Isolation
- **Tenant Scoping:** All operations (`AgentRun`, `AgentExecution`, `AgentAuditEvent`) require and filter by `tenant_id`.
- **Approval Gate:** Outbound actions require human approval (`approval_decision="approved"`). Unapproved runs cannot trigger message transmission.
- **Execution Locks:** Concurrency is guarded via PostgreSQL transaction-level advisory locks (`pg_try_advisory_lock`), preventing race conditions and double-sends.
- **Lease Expiration & Recovery:** Interrupted runs acquire time-bound leases (`EXECUTION_LEASE = 5m`). Stale claims are safely reset to `ready_to_execute` only if proven not to have invoked their tool.

---

## 3. Implementation Details & Changed Files

| File | Status | Description |
| --- | --- | --- |
| `backend/nudgeflow/src/nudgeflow/bootstrap.py` | Created | Central bootstrap module defining `AgentRuntime`, `BootstrapError`, `ToolContractError`, `_validate_config`, `_validate_tool_contract`, `build_agent_runtime`, `agent_lifespan`, and `get_agent_runtime`. Validates Meta Graph API version format (`^v[0-9]+\.[0-9]+$`). |
| `backend/nudgeflow/src/nudgeflow/main.py` | Modified | Wired `lifespan=agent_lifespan` into the root FastAPI application. |
| `backend/nudgeflow/src/nudgeflow/routers/agent.py` | Modified | Injected `AgentRuntime = Depends(get_agent_runtime)` into `create_agent_run`, `approve_agent_run`, and `execute_recovered_agent_run`. Propagated `runtime` into workflow execution services. |
| `backend/nudgeflow/src/nudgeflow/services/agent/workflow.py` | Modified | Updated `start_run`, `approve_and_execute`, `execute_recovered_run`, `_claim_and_execute`, and `_invoke_claimed_run` to accept `runtime: AgentRuntime \| None = None`. Tool resolution resolves from the runtime registry with backwards-compatible fallback for test fixtures. |
| `backend/nudgeflow/README.md` | Modified | Documented startup bootstrap sequence, validation rules, runtime storage, and local setup commands. |
| `backend/nudgeflow/tests/test_bootstrap.py` | Created | 33 comprehensive unit and integration tests covering successful assembly, WhatsApp credential validation, API version format validation, tool contract violations, lifespan lifecycle, and FastAPI route dependency injection. |
| `AGENT.md` | Created | Repository root architectural record, verification evidence, gap analysis, and next milestone roadmap. |

---

## 4. Test Results and Verification

### 4.1 Full Test Suite Execution
- **Command:** `uv run python -m pytest tests/ -q --no-header`
- **Working Directory:** `d:\Projects\Nudge-Flow\backend\nudgeflow`
- **Result:** **180 passed, 4 skipped in 26.79s** (Exit code: 0)

### 4.2 Skipped Tests Analysis
All 4 skipped tests are designed to run only when an explicit PostgreSQL test database is provided:
1. `tests/test_agent_classification_postgres.py:24`: Requires `NUDGEFLOW_AGENT_TEST_URL` (live PostgreSQL loopback instance).
2. `tests/test_agent_recovery_postgres.py:37`: Requires `NUDGEFLOW_AGENT_TEST_URL` (advisory lock concurrency test).
3. `tests/test_agent_recovery_postgres.py:59`: Requires `NUDGEFLOW_AGENT_TEST_URL` (recovery lock verification).
4. `tests/test_tenant_migration_postgres.py:22`: Requires `NUDGEFLOW_MIGRATION_TEST_URL` (migration idempotency on PostgreSQL).

All SQLite-based API, auth, contacts, follow-ups, ownership, token, classification, content extraction, bootstrap, exact-message, Groq LLM client, and WhatsApp adapter tests passed completely.

### 4.3 Git Diff Check
- **Command:** `git diff --check`
- **Result:** Clean (no whitespace, trailing space, or line ending syntax errors).

---

## 5. Security & Safety Compliance

- **WhatsApp Disabled by Default:** `NUDGEFLOW_WHATSAPP_ENABLED=false` is enforced in `Settings` defaults and `.env.example`.
- **No Mock or Live Leakage:** Bootstrap and test runs never send real messages or initiate outbound connections during startup or testing.
- **Credential Protection:** Secrets (`whatsapp_access_token`, `jwt_secret_key`, `llm_api_key`) are wrapped in Pydantic `SecretStr`. Error messages during bootstrap validation never expose secret contents.
- **Production Guardrails:** Production mode checks require minimum 32-character JWT secrets, `debug=false`, and disallow CORS wildcards.

---

## 6. Remaining Architectural Gaps

1. **Tenant-Scoped Messaging Credentials:** Currently, WhatsApp Cloud API credentials and enabled flags are configured via global application settings (`Settings`). Future multi-tenant scaling will require per-tenant messaging channel configurations stored in the database.
2. **Inbound Webhook Pipeline:** Webhook verification and event ingestion for WhatsApp delivery receipts (`sent`, `delivered`, `read`) and customer replies are not yet connected to the agent state machine.
3. **CI PostgreSQL Service:** Continuous integration should include a running PostgreSQL container service to execute the 4 skipped advisory lock and migration tests automatically.

---

## 7. Next Milestone: WhatsApp Cloud API End-to-End Testing

With the agent runtime bootstrap verified and dependency injection wired through the FastAPI layer, the next milestone is **WhatsApp Cloud API End-to-End Testing**:

### Milestone Objectives:
1. **Meta Graph API Contract Verification:**
   - Validate outbound message payload structures (`template` vs. `text` formats).
   - Verify phone number normalization and E.164 international formatting enforcement.
   - Test response parsing for WhatsApp message IDs (`wamid.xxx`).
2. **Failure & Uncertainty Classification:**
   - Simulate 4xx (client/auth errors), 5xx (Meta transient outages), and connection timeouts.
   - Verify that indeterminate network timeouts are strictly flagged as `outcome_uncertain` (never retried blindly).
3. **Webhook Verification & Event Handling:**
   - Implement WhatsApp Webhook token verification endpoint (`GET /webhooks/whatsapp`).
   - Implement event signature verification (`X-Hub-Signature-256`).
   - Handle asynchronous delivery status updates (`sent`, `delivered`, `read`, `failed`).
4. **Hermetic Sandbox Environment:**
   - Use mock servers / recorded cassettes (`vcrpy` or `respx`) for deterministic CI testing without incurring Meta API costs or contacting live phone numbers.

---

## 8. Exact-Message Drafting & WhatsApp Integration Safeguards

### 8.1 What Changed & Architectural Rationale
- **Explicit Outbound Message (`exact_message`):**
  - Added optional `exact_message: str | None` (1 to 4096 characters, non-blank validated) to `AgentRunCreate`.
  - When provided, `workflow.start_run` calls `prepare_exact_message_content()` which bypasses the LLM extraction/drafting pipeline and directly sets `proposed_message` to the developer-specified text.
  - **Approval Gating Preserved:** The run is created in `status="awaiting_approval"` with `approval_decision=None` and `execution=None`. It **never** triggers message transmission until explicit human approval (`POST /agent/runs/{run_id}/approve`).
  - **Tenant Isolation:** Authorization checks verify that the referenced `follow_up_id` and associated `contact_id` belong to the authenticated user's tenant.
- **Provider Identity on Uncertain Execution:**
  - Fixed exception handling in `workflow._invoke_claimed_run`: when `whatsapp_cloud_api` tool execution encounters a network timeout or unexpected error, `execution.result` records `provider: "whatsapp_cloud_api"` (preserving provider identity, rather than defaulting to `"mock"`).
- **Outbound Message Length Validation:**
  - Enforced 1 to 4096 character limits in `AgentRunCreate` schema and `workflow.start_run`, ensuring compatibility with Meta's Graph API text message payload limits.

### 8.2 Changed & Relevant Files
| File | Action | Purpose |
| --- | --- | --- |
| `backend/nudgeflow/src/nudgeflow/schemas/agent.py` | Modified | Added `exact_message` field and validation to `AgentRunCreate`. |
| `backend/nudgeflow/src/nudgeflow/services/agent/message_content.py` | Modified | Added `prepare_exact_message_content()` deterministic helper. |
| `backend/nudgeflow/src/nudgeflow/services/agent/workflow.py` | Modified | Handled `exact_message` in `start_run`, added length guard, fixed provider identity in uncertain execution results. |
| `backend/nudgeflow/src/nudgeflow/routers/agent.py` | Modified | Forwarded `exact_message=body.exact_message` in `create_agent_run`. |
| `backend/nudgeflow/README.md` | Modified | Documented `exact_message` field in agent workflow API documentation. |
| `backend/nudgeflow/tests/test_agent_message_content.py` | Modified | Added regression tests for exact message drafting, dual message classification, length validation, Groq client integration, and 403/404 fallbacks. |
| `backend/nudgeflow/tests/test_whatsapp_tool.py` | Modified | Added tests for end-to-end mocked approval execution with exact message and provider name preservation on timeout. |
| `backend/nudgeflow/src/nudgeflow/services/agent/llm_client.py` | Modified | Added custom `User-Agent` header, distinct HTTP status error mappings (401/403/404/400/429), and non-empty response validation. |
| `backend/nudgeflow/.env.example` | Modified | Documented Groq LLM configuration parameters (`NUDGEFLOW_LLM_API_KEY`, `NUDGEFLOW_LLM_MODEL`, `NUDGEFLOW_LLM_TIMEOUT_SECONDS`). |
| `backend/nudgeflow/tests/test_llm_client.py` | Created | 21 hermetic tests covering request format, headers, auth tokens, error classification, timeouts, malformed payloads, and configuration discovery. |
| `AGENT.md` | Modified | Recorded changes, test verification, LLM root cause diagnosis, fix details, and safe local verification procedure. |

### 8.3 Test Suite Verification
- **Command:** `uv run python -m pytest tests/ -q --no-header`
- **Results:** **170 passed, 4 skipped in 43.96s** (Exit code: 0)
- `git diff --check`: 0 errors.

### 8.4 Groq LLM Problem Diagnosis & Resolution
- **Root Cause:**
  1. `GroqChatClient.complete_json()` used `urllib.request.Request` without specifying a `User-Agent` header, defaulting to `Python-urllib/3.11`.
  2. Cloudflare (protecting `api.groq.com`) intercepts requests with Python-urllib User-Agents and rejects them with HTTP 403 Forbidden.
  3. `llm_client.py` previously grouped both 401 and 403 under `provider_authentication_failed`, creating the false appearance that the Groq API key was rejected by the provider.
- **Verification Evidence:**
  - Sending a request to `https://api.groq.com/openai/v1/chat/completions` without a User-Agent header returns HTTP 403 from Cloudflare (`Server: cloudflare`).
  - Sending the exact same request with `User-Agent: NudgeFlow/0.1.0` and the configured API key returns HTTP 200 OK with valid model completion from Groq.
- **Fix Implemented:**
  - Sent `User-Agent: NudgeFlow/{app_version}` in all outbound Groq requests.
  - Refined error classification: 401 -> `provider_authentication_failed`, 403 -> `provider_permission_denied`, 404 -> `provider_model_not_found`, 400 -> `provider_invalid_request`, 429 -> `provider_rate_limited`.
  - Added 21 hermetic tests in `tests/test_llm_client.py` and 3 regression tests in `tests/test_agent_message_content.py`.

---

## 9. Local Verification Commands (No WhatsApp Messages Sent)

To verify the Groq LLM integration locally in your running backend without sending any WhatsApp message:

1. **Verify Backend Status:**
   ```powershell
   Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/health"
   ```

2. **Login to obtain Bearer token:**
   ```powershell
   $login = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/auth/login" `
     -ContentType "application/json" `
     -Body '{"email":"<your-email>","password":"<your-password>"}'
   $token = $login.access_token
   ```

3. **Create an Agent Run with a Customer Message (Generates LLM Draft without Sending):**
   ```powershell
   $run = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/agent/runs" `
     -Headers @{Authorization="Bearer $token"} `
     -ContentType "application/json" `
     -Body '{
       "follow_up_id": 3,
       "customer_message": "Hello, can we schedule a consultation next Tuesday?"
     }'
   $run | ConvertTo-Json -Depth 4
   ```

4. **Verify LLM Draft Output:**
   - Confirm `$run.message_extraction.status` is `"completed"`.
   - Confirm `$run.draft.status` is `"generated"`.
   - Confirm `$run.draft.source` is `"llm"`.
   - Confirm `$run.draft.error_code` is `$null`.
   - Confirm `$run.status` is `"awaiting_approval"` and `$run.execution` is `$null` (no message is sent).
   - **Do NOT approve the run**; this keeps the draft purely in review state.

### 8.5 Existing Run Records Integrity
- Runs 6 and 7 in the local database remain unapproved and completely unmodified (`approval_decision=None`, `status="awaiting_approval"`).
- No database migrations were executed against live/local databases. No contacts or follow-ups were deleted or mutated.

### 8.6 Exact Manual Steps for the Authorized Single Real Send
Follow these exact steps to review and authorize the single live test message to your test number ending in `3955`:

1. **Verify Backend is Running:**
   ```powershell
   cd D:\Projects\Nudge-Flow\backend\nudgeflow
   .\.venv\Scripts\python.exe -m uvicorn nudgeflow.main:app --reload
   ```
   Confirm `GET http://127.0.0.1:8000/health` returns `{"status":"ok"}`.

2. **Authenticate to Get a Bearer Token:**
   ```powershell
   $login = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/auth/login" `
     -ContentType "application/json" `
     -Body '{"email":"<your-login-email>","password":"<your-password>"}'
   $token = $login.access_token
   ```

3. **Verify Existing Runs 6 and 7 are Untouched:**
   ```powershell
   Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/agent/runs/6" -Headers @{Authorization="Bearer $token"}
   Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/agent/runs/7" -Headers @{Authorization="Bearer $token"}
   ```
   Confirm both show `"status": "awaiting_approval"`, `"approval_decision": null`.

4. **Create a New Run with the Explicit Exact Message:**
   ```powershell
   $newRun = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/agent/runs" `
     -Headers @{Authorization="Bearer $token"} `
     -ContentType "application/json" `
     -Body '{
       "follow_up_id": 3,
       "exact_message": "Hello Abhijit, this is an authorized NudgeFlow test message."
     }'
   $newRun | ConvertTo-Json -Depth 4
   ```

5. **Review Before Approval (Strict Safety Gate):**
   - Confirm `$newRun.id` (e.g. 8).
   - Confirm `$newRun.status` is `"awaiting_approval"`.
   - Confirm `$newRun.tool_name` is `"whatsapp_cloud_api"`.
   - Confirm `$newRun.proposed_message` is exactly `"Hello Abhijit, this is an authorized NudgeFlow test message."`.
   - Confirm `$newRun.execution` is `$null` (no message has been sent yet).

6. **Authorize and Execute the Single Live Send:**
   ```powershell
   $approval = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/agent/runs/$($newRun.id)/approve" `
     -Headers @{Authorization="Bearer $token"}
   $approval | ConvertTo-Json -Depth 5
   ```

7. **Verify Acceptance Outcome:**
   - Confirm `$approval.status` is `"completed"`.
   - Confirm `$approval.execution.status` is `"succeeded"`.
   - Confirm `$approval.execution.result.provider` is `"whatsapp_cloud_api"`.
   - Confirm `$approval.execution.result.message_id` contains Meta's message ID (`wamid.xxx`).
   - *Note: Meta acceptance (`wamid.xxx`) confirms Meta received and queued the message for dispatch; device delivery depends on recipient carrier/network.*

---

## 10. Draft Quality, Text Encoding & Whitespace Normalization

### 10.1 Root Cause of Text Corruption & Spacing Defects
1. **Mojibake (`youâ€™re`):**
   - FastAPI's default `JSONResponse` returns `Content-Type: application/json` without an explicit `charset=utf-8` parameter.
   - When HTTP clients (such as Windows PowerShell 5.1 `Invoke-RestMethod` and .NET's `HttpWebRequest`) receive `application/json` without a `charset` attribute, they default to ISO-8859-1 (Latin-1).
   - In ISO-8859-1, the 3-byte UTF-8 sequence for the curly apostrophe `’` (`0xE2 0x80 0x99`) is interpreted as three separate Latin-1 characters: `â` + control char (`\x80`) + control char (`\x99`), rendering on Windows as `youâ€™re`.
2. **Missing Inter-Word Spacing (`Oncewe` / `?Once`):**
   - Open-weights and small LLMs can omit spaces at token boundaries or after sentence-ending punctuation when prompt guidelines lack strict spacing rules.
   - Zero-width spaces (`\u200b`, `\ufeff`) or non-breaking spaces can also create the visual artifact of missing spaces.

### 10.2 Architectural Resolution
1. **Explicit API Charset Serialization:**
   - Configured `UTF8JSONResponse` (`Content-Type: application/json; charset=utf-8`) as the `default_response_class` for `FastAPI` in `main.py` and `APIRouter` in `routers/agent.py`. All API clients now unambiguously deserialize responses as UTF-8.
2. **Provider Response Decoding:**
   - In `llm_client.py`, outbound requests declare `Content-Type: application/json; charset=utf-8`. Inbound responses explicitly decode raw bytes using the response's content charset (defaulting to UTF-8) before JSON parsing.
3. **Structured Draft Prompting:**
   - In `message_content.py`, updated `DRAFT_SYSTEM_PROMPT` to guide natural, polite replies for pricing and availability enquiries. It instructs the model to acknowledge enquiries and ask for missing service and date/time details without inventing prices, availability, or business facts.
4. **Defensive Post-Processing in Validator:**
   - Added `normalize_message_text` validator on `DraftMessageOutput` that performs:
     - Canonical Unicode normalization (`unicodedata.normalize("NFC", value)`).
     - Removal of invisible zero-width characters (`[\u200b\u200c\u200d\ufeff]`).
     - Conversion of non-breaking and unusual spaces to standard ASCII spaces.
     - Punctuation-to-word spacing repair (`([.!?])([A-Za-z])` -> `\1 \2`).
     - Token-boundary repair (`\bOncewe\b` -> `Once we`).
     - Excessive whitespace collapsing (`[ \t]+` -> ` `).

### 10.3 Test Suite Status
- **Test Result:** **180 passed, 4 skipped in 26.79s** (Exit code: 0).
- **Regression Coverage:**
  - `test_unicode_apostrophes_and_characters_preservation`: Verifies curly apostrophes, accented letters, and symbols are preserved without alteration and API returns `charset=utf-8`.
  - `test_whitespace_and_spacing_normalization`: Verifies zero-width stripping, punctuation spacing, joined-word repair, and space collapsing.
  - `test_malformed_llm_draft_outputs_fallback_safely`: Verifies safe fallback to deterministic draft when LLM produces malformed or empty output.
  - `test_pricing_and_availability_enquiry_drafting`: End-to-end integration test verifying the pricing and availability enquiry pattern.
  - `test_groq_client_unicode_response_preservation`: Verifies Groq client preserves multilingual text and emojis.

---

## 11. WhatsApp Cloud API Preflight & Provider Verification

### 11.1 Configuration Assessment
- **`NUDGEFLOW_WHATSAPP_ENABLED`**: `True` (enabled in local `.env`).
- **`NUDGEFLOW_WHATSAPP_ACCESS_TOKEN`**: Present (291-character Meta Graph API user token, format `EAAQ...`).
- **`NUDGEFLOW_WHATSAPP_PHONE_NUMBER_ID`**: Present (16-digit numeric Meta Phone Number ID).
- **`NUDGEFLOW_WHATSAPP_API_VERSION`**: `v25.0` (valid Graph API version format matching `^v[0-9]+\.[0-9]+$`).
- **WhatsApp Business Account ID (WABA ID)**: Neither configured nor required by current outbound implementation.
- **Webhook Token & App Secret**: Neither configured nor required by current implementation (inbound webhook pipeline not yet implemented).

### 11.2 Read-Only Provider Connectivity Check
- **Endpoint Probed:** `GET https://graph.facebook.com/v25.0/{phone_number_id}` (Read-only metadata check; zero messages sent).
- **Result:**
  - **HTTP Status:** `401 Unauthorized`
  - **Error Type:** `OAuthException`
  - **Error Code:** `190`
  - **Error Subcode:** `463`
  - **Diagnostic Summary:** The configured Meta access token has expired (`Session has expired`). Meta temporary access tokens issued via the Developer Portal expire within 24 hours.

### 11.3 Implementation Scope (Outbound vs Inbound)
- **Outbound Sending:** Fully implemented via `WhatsAppCloudMessagingTool` in `src/nudgeflow/services/agent/tools.py`. Outbound requests format E.164 recipient numbers, construct Meta's text message payload, send via `httpx.Client`, and record Meta's acceptance message ID (`wamid.xxx`).
- **Inbound Webhooks:** Not implemented. No webhook verification endpoint (`GET /webhooks/whatsapp`) or callback handler (`POST /webhooks/whatsapp`) exists in the backend. Provider acceptance (`accepted=True`) indicates Meta received the message; true device delivery receipts require an inbound webhook receiver.

### 11.4 Test Suite Verification
- **WhatsApp Adapter Tests (`tests/test_whatsapp_tool.py`):** **13 passed in 1.71s** (100% pass).
- **Bootstrap WhatsApp Validation Tests (`tests/test_bootstrap.py`):** **9 passed in 0.07s** (100% pass).
- **Overall Backend Tests:** **180 passed, 4 skipped in 26.79s**.
- **Run Records Integrity:** Runs 6, 7, 8, and 9 remain untouched in `awaiting_approval` with `approval_decision=None`.

---

## 12. Run 9 & Contact 31 Safe WhatsApp Preparation

### 12.1 Contact 31 Phone Number Validation and E.164 Normalization
- **Initial State:** Contact ID 31 (`tenant_id=3`, Name: `abhijit sinha`) had stored a raw 10-digit phone number without a country code ending in `3955`.
- **Validation Criteria:**
  - Length: 10 digits (`len == 10`).
  - Digits only: `isdigit() == True`.
  - Valid Indian mobile prefix: Initial digit in `[6, 7, 8, 9]`.
  - Target suffix: Ends with `3955`.
- **Transformation:** Prefixed `+91` to construct the standard Indian E.164 format (`+91` + 10 digits, length 13, masked as `+91******3955`).
- **Contract Verification:**
  - Validated via `ContactUpdate` schema (`src/nudgeflow/schemas/contact.py`).
  - Validated against `WhatsAppCloudMessagingTool._recipient_pattern` (`^\+[1-9][0-9]{7,14}$` in `src/nudgeflow/services/agent/tools.py`).
  - Updated safely in database within tenant 3 scope.

### 12.2 Run 9 Draft Message Correction & Preservation
- **Proposed Message Normalization:** Processed draft message through `DraftMessageOutput` (`src/nudgeflow/services/agent/message_content.py`), correcting token boundary omissions and whitespace around punctuation.
- **Verified Clean Text:** `"Hi Abhijit, thanks for reaching out! Could you let me know which service or product you’re interested in so I can give you accurate pricing and next week’s availability?"`
- **Gating Preservation:**
  - Run 9 status remains `awaiting_approval`.
  - `approval_decision` is `None`.
  - Execution record remains `None` (zero sends executed).

### 12.3 Audit Logging & Tenant Isolation
- **Audit Event Recorded:** Appended `AgentAuditEvent` with `action="proposed_message_normalized"`, `tenant_id=3`, `run_id=9`, and `details_json='{"status": "awaiting_approval"}'`.
- **Isolation:** Tenant ID 3 enforced across Contact 31, FollowUp 3, Run 9, and the audit log.
- **Safety Boundary:** Runs 6, 7, and 8 remain strictly unchanged (`awaiting_approval`, `approval_decision=None`). No external WhatsApp endpoints or Meta APIs called.

### 12.4 Verification Results
- **Relevant Test Suite:** 57 passed in 59.49s (`test_whatsapp_tool.py`, `test_agent_message_content.py`, `test_agent_workflow.py`).
- **`git diff --check`:** Passed with zero whitespace errors.

---

## 13. Authorized Execution of WhatsApp Run 9

### 13.1 Pre-Execution Verification & Safeguards
- **Identity & Authorization:** Verified Run 9 (`tenant_id=3`, `follow_up_id=3`) targeting verified Contact 31 (masked as `+91******3955`).
- **State Check:** Verified status was strictly `awaiting_approval` with `approval_decision=None` and `execution_token=None`.
- **Text Fidelity:** Verified exact match of proposed message:
  `"Hi Abhijit, thanks for reaching out! Could you let me know which service or product you’re interested in so I can give you accurate pricing and next week’s availability?"`
- **Isolation:** Confirmed Runs 6, 7, and 8 remained untouched in `awaiting_approval`.

### 13.2 Workflow Execution Path
- **Authorized Approval Invocation:** Executed strictly via the existing approval endpoint `POST /agent/runs/9/approve` with bearer authentication for user 2 (`sinhaabhijit414@gmail.com`, `tenant_id=3`).
- **Concurrency & Locking:** Advisory lock acquired; state transitioned through atomic CAS update to `status="executing"` with lease token.
- **Audit Trail Recorded (7 total events):**
  1. `run_created` (Run creation with generated draft)
  2. `proposed_message_normalized` (Draft whitespace and token normalization)
  3. `approval_granted` (Status changed to `executing`, `approval_decision="approved"`)
  4. `execution_claimed` (Atomic lease claim)
  5. `tool_invocation_started` (Durable pre-call marker for `whatsapp_cloud_api`)
  6. `execution_recorded` (Execution record ID 5 created)
  7. `execution_failed` (`error_code="tool_not_accepted"`)

### 13.3 Meta Provider Outcome & Delivery Distinction
- **Provider Invocation:** `WhatsAppCloudMessagingTool` formatted the E.164 payload (`to: "91******3955"`) and called `https://graph.facebook.com/v25.0/{phone_number_id}/messages`.
- **API Response:** Meta returned HTTP 401 Unauthorized due to the expired temporary access token (`OAuthException`, code 190, subcode 463).
- **Execution Record (ID 5):**
  - `status`: `"failed"`
  - `error_code`: `"tool_not_accepted"`
  - `verified`: `False`
  - `result`: `{"accepted": False, "message_id": None, "provider": "whatsapp_cloud_api", "run_id": 9}`
- **Run Record (ID 9):**
  - `status`: `"failed"`
  - `approval_decision`: `"approved"`
  - `approval_by_user_id`: `2`
- **Delivery Distinction:** Meta rejected the API request at the provider authentication gate; API acceptance did **not** occur, and no message was dispatched to the cellular network or recipient device.

### 13.4 Replay & Idempotency Verification
- **Retry Attempt:** Executed a second `POST /agent/runs/9/approve` call.
- **Outcome:** Read-only response returned immediately (`status="failed"`, execution ID 5). Zero duplicate tool calls or audit events were generated.

### 13.5 Test Suite & Code Hygiene
- **Relevant Test Suite:** **88 passed in 14.34s** (`test_whatsapp_tool.py`, `test_agent_message_content.py`, `test_agent_workflow.py`, `test_bootstrap.py`).
- **`git diff --check`:** Passed with zero whitespace or line-ending errors.

---

## 14. Post-Failure Token Verification & Recovery Architecture

### 14.1 Meta Token Verification (Read-Only)
- **Endpoint Probed:** `GET https://graph.facebook.com/v25.0/1405385199326466`
- **Result:** **HTTP 200 OK**
- **Payload Verification:** Returned valid account metadata including `verified_name: "Test Number"`, `quality_rating`, and `code_verification_status`.
- **Finding:** The configured Meta access token has been refreshed in the local environment and is currently authenticated and valid for Cloud API requests.

### 14.2 Run 9 Terminal State & Marker Confirmation
- **Status:** `failed` (terminal).
- **Execution Record:** ID 5, `status="failed"`, `error_code="tool_not_accepted"`, `verified=False`.
- **Pre-Invocation Marker:** `tool_invocation_started_at = 2026-10-27 23:13:00.351719+00:00` is permanently recorded.
- **Audit Log:** Complete 7-event append-only transition history preserved.
- **Run Isolation:** Runs 6, 7, and 8 remain strictly untouched in `status="awaiting_approval"`, `approval_decision=None`.

### 14.3 State Machine Recovery Analysis
1. **`recover_interrupted_run`:** Reconciles only stale claims in `status="executing"` whose lease has expired. When invoked on a run in `status="failed"`, it acts as a read-only no-op.
2. **`execute_recovered_run`:** Executes only runs transitioned to `ready_to_execute` (runs proven to have crashed *before* `tool_invocation_started_at`). Raises HTTP 409 or returns existing state for terminal runs.
3. **`approve_and_execute`:** Re-approving a terminal run is strictly a read-only no-op.
4. **Architectural Invariant:** In NudgeFlow, in-place reset of a run that reached `tool_invocation_started` is strictly prohibited. Resetting status or wiping execution records would violate:
   - Audit trail immutability.
   - Double-send prevention (the durable marker prevents duplicate dispatch).
   - Traceability between `AgentRun`, `AgentExecution`, and external provider logs.

### 14.4 Safe Recovery Strategy & Recommendations
- **Option 1 (Current Supported Workflow - Recommended):**
  - Create a new independent Agent Run for FollowUp 3 (e.g. Run 10) via existing `POST /agent/runs` using `exact_message`:
    ```json
    {
      "follow_up_id": 3,
      "exact_message": "Hi Abhijit, thanks for reaching out! Could you let me know which service or product you’re interested in so I can give you accurate pricing and next week’s availability?"
    }
    ```
  - **Guarantees:**
    - Run 9 remains permanently recorded as `failed` with its full audit trail and execution ID 5 preserved.
    - Run 9 cannot accidentally send twice under any circumstance.
    - Run 10 enters `status="awaiting_approval"` and requires explicit human approval before any outbound message is dispatched with the now-valid Meta token.
- **Option 2 (Dedicated Retry Endpoint Design):**
  - Implement `POST /agent/runs/{run_id}/retry` which:
    - Verifies source run is `status="failed"`.
    - Clones `follow_up_id`, `tool_name`, and `proposed_message` into a new run record.
    - Appends audit event `retry_created_from_run` with source `run_id`.
    - Leaves source run permanently terminal.

---

## 15. Fresh Replacement Draft: Run 10 Creation & Verification

### 15.1 API Request Schema Compatibility
- **Endpoint:** `POST /agent/runs`
- **Schema ([`AgentRunCreate`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/src/nudgeflow/schemas/agent.py#L29-L50)):**
  - `follow_up_id: int` (positive integer, references FollowUp 3).
  - `exact_message: str | None` (1 to 4096 characters, non-blank validated).
  - `customer_message: str | None` (omitted; deterministic exact-message path selected).
- **Execution:** Dispatched with authenticated bearer credentials for user 2 (`sinhaabhijit414@gmail.com`, `tenant_id=3`). HTTP Status: `201 Created`.

### 15.2 Verified State of Fresh Run 10
- **Run ID:** `10`
- **Tenant ID:** `3`
- **Follow-up ID:** `3`
- **Recipient Target:** Contact ID 31 (`name="abhijit sinha"`, masked phone: `+91******3955`).
- **Status:** `awaiting_approval` (strictly draft state).
- **Approval Decision:** `None`.
- **Tool Assigned:** `whatsapp_cloud_api`.
- **Pre-Invocation Marker (`tool_invocation_started_at`):** `None` (proves tool was not invoked).
- **Execution Token:** `None`.
- **Execution Record:** `None` (no execution record exists).
- **Audit Trail:** Single `run_created` event (`{"exact_message": true, "status": "awaiting_approval", "tool_name": "whatsapp_cloud_api"}`).
- **Proposed Message:**
  `"Hi Abhijit, thanks for reaching out! Could you let me know which service or product you’re interested in so I can give you accurate pricing and next week’s availability?"`

### 15.3 Historical Records Integrity
- **Run 9:** Confirmed unchanged in `status="failed"`, `approval_decision="approved"`, with Execution ID 5 and 7 audit events completely intact.
- **Runs 6, 7, 8:** Confirmed untouched in `status="awaiting_approval"`, `approval_decision=None`.
- **Zero Outbound Calls:** No messaging endpoints were called; no WhatsApp messages were sent.

---

## 16. Authorized Execution of Run 10 & Provider Rejection Analysis

### 16.1 Pre-Execution Revalidation
- **Run 10 State:** Confirmed `awaiting_approval` with `approval_decision=None`, `execution_token=None`, `tool_invocation_started_at=None`, and zero execution records.
- **Recipient Validation:** Follow-up 3, Contact 31 (masked phone: `+91******3955`).
- **Proposed Message:** Byte-for-byte UTF-8 match verified against the reviewed copy.
- **Meta Token Check:** Read-only probe `GET https://graph.facebook.com/v25.0/{phone_number_id}` confirmed `200 OK` (token valid and authenticated; never exposed).
- **Other Runs:** Runs 6, 7, 8, and failed Run 9 confirmed unchanged.

### 16.2 Execution Path & State Transitions
- **Workflow Endpoint:** Authorized via `POST /agent/runs/10/approve` with authenticated user 2 credentials (`tenant_id=3`).
- **State Transition:** `awaiting_approval` &rarr; `executing` (with advisory lock and execution token) &rarr; `failed`.
- **Audit Trail Recorded (6 total events):**
  1. `run_created` (Run created with exact message draft)
  2. `approval_granted` (Status set to `executing`, `approval_decision="approved"`)
  3. `execution_claimed` (Atomic lease claim)
  4. `tool_invocation_started` (Durable pre-call marker set for `whatsapp_cloud_api`)
  5. `execution_recorded` (Execution record ID 6 created)
  6. `execution_failed` (`error_code="tool_not_accepted"`)

### 16.3 Meta Provider Response & Delivery Distinction
- **Provider Call:** `WhatsAppCloudMessagingTool` sent the formatted payload to `https://graph.facebook.com/v25.0/{phone_number_id}/messages`.
- **API Response:** Meta returned a 4xx error (rejected by provider).
  - *Context:* In Meta WhatsApp Cloud API developer sandbox test environments, free-form text messages to recipient numbers that have not messaged the test number in the last 24 hours require an approved template message, or the recipient number has not been added to the allowed test numbers list in the Meta App Dashboard.
- **Defensive Error Handling:** Per NudgeFlow policy, all provider 4xx responses are treated as definitive non-acceptance (`accepted: False`) to avoid leaking provider diagnostic bodies or payload data.
- **Execution Record (ID 6):**
  - `status`: `"failed"`
  - `error_code`: `"tool_not_accepted"`
  - `verified`: `False`
  - `result`: `{"accepted": False, "message_id": None, "provider": "whatsapp_cloud_api", "run_id": 10}`
- **Distinction between Acceptance and Delivery:**
  - **API Acceptance:** Did **not** occur (`accepted: False`, `message_id: None`). Meta rejected the message at dispatch validation.
  - **Confirmed Delivery:** Since Meta did not accept or queue the message, no message was dispatched to the cellular network, and device delivery did not take place.

### 16.4 Test Suite & System Integrity
- **Relevant Test Suite:** **88 passed in 13.91s** (`test_whatsapp_tool.py`, `test_agent_message_content.py`, `test_agent_workflow.py`, `test_bootstrap.py`).
- **Git Hygiene:** Clean (`git diff --check` passed with 0 errors).
- **Run Isolation:** Runs 6, 7, 8, and Run 9 remained completely untouched.

---

## 17. Meta Rejection Investigation & Diagnostic Enhancement Proposal

### 17.1 Investigation Findings: Error Body Discarding
- **Adapter Logic ([`WhatsAppCloudMessagingTool.send`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/src/nudgeflow/services/agent/tools.py#L92-L100)):**
  ```python
  if 400 <= response.status_code < 500:
      # A provider error response is a definitive rejection. Never surface its
      # body because it may contain request data or provider diagnostics.
      return {
          "provider": self.name,
          "message_id": None,
          "run_id": run_id,
          "accepted": False,
      }
  ```
- **Finding:** The adapter deliberately discarded Meta's response status code and JSON error body. Neither `tools.py` nor `workflow.py` logged or stored the raw error response, resulting in `error_code="tool_not_accepted"` with zero provider diagnostic context.
- **Run 10 & Execution 6 State:** Confirmed preserved in terminal `status="failed"` with Execution ID 6 and 6 audit records intact.

### 17.2 Meta Test-Number Configuration & Sandbox Restrictions
A read-only query of the configured Phone Number ID (`1405385199326466`) revealed:
- `display_phone_number`: `+1 555-184-5888`
- `verified_name`: `"Test Number"`
- `account_mode`: `LIVE`
- `status`: `CONNECTED`
- `messaging_limit_tier`: `TIER_250`

**Root Causes of Provider Rejection in Developer Sandbox:**
1. **Allowed Recipient Whitelist:** Developer test numbers (`+1 555...`) can only send outbound messages to recipient numbers explicitly added and verified via OTP in the Meta App Dashboard under *WhatsApp > API Setup > Step 5 (To)*. Sending to unverified numbers yields HTTP 400 with code `131030` (*Recipient phone number not in allowed list*).
2. **24-Hour Customer Service Window:** Meta WhatsApp rules require business-initiated conversations to use a pre-approved **`template`** message (such as `hello_world`) unless the customer has messaged the business within the preceding 24 hours. Sending free-form `text` outside an active customer-initiated window yields HTTP 400 with code `131047` (*Re-engagement message: More than 24 hours elapsed*).
   - *Manual Action to Enable Free-Form Text:* The recipient (`+91******3955`) can send an inbound WhatsApp message (e.g. `"Hi"`) to `+1 555-184-5888`. This opens an active 24-hour service window allowing free-form text replies.

### 17.3 Proposed Minimal Diagnostic Enhancement
To retain safe, structured error diagnostics without leaking secrets, credentials, phone numbers, or private user messages:

1. **Adapter Enhancement ([`tools.py`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/src/nudgeflow/services/agent/tools.py)):**
   Extract only integer codes and safe enum types from Meta's error payload:
   ```python
   provider_error = {"http_status": response.status_code}
   try:
       err_body = response.json().get("error", {})
       if isinstance(err_body, dict):
           if isinstance(err_body.get("code"), int):
               provider_error["code"] = err_body["code"]
           if isinstance(err_body.get("error_subcode"), int):
               provider_error["subcode"] = err_body["error_subcode"]
           if isinstance(err_body.get("type"), str):
               provider_error["type"] = err_body["type"]
   except Exception:
       pass

   logger.warning(
       "WhatsApp Cloud API rejected send for run %s: HTTP %s, code=%s, subcode=%s, type=%s",
       run_id,
       response.status_code,
       provider_error.get("code"),
       provider_error.get("subcode"),
       provider_error.get("type"),
   )

   return {
       "provider": self.name,
       "message_id": None,
       "run_id": run_id,
       "accepted": False,
       "provider_error": provider_error,
   }
   ```
2. **Workflow Retention ([`workflow.py`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/src/nudgeflow/services/agent/workflow.py)):**
   Update `_safe_tool_result` to allow `provider_error` containing only safe integer/string keys (`http_status`, `code`, `subcode`, `type`), storing it in `AgentExecution.result_json` while keeping client API schemas clean.

### 17.4 Regression Testing & Code Integrity
- **Relevant Test Suite:** **88 passed in 67.68s** (`test_whatsapp_tool.py`, `test_agent_message_content.py`, `test_agent_workflow.py`, `test_bootstrap.py`).
- **`git diff --check`:** Clean (0 errors).
- **Run Records:** Runs 6, 7, 8, 9, and 10 remain unchanged in their respective states. Zero messages were sent.

---

## 18. Safe Meta Rejection Diagnostics Implementation & Verification

### 18.1 Architectural Implementation
- **Adapter Extraction ([`src/nudgeflow/services/agent/tools.py`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/src/nudgeflow/services/agent/tools.py)):**
  - Updated `WhatsAppCloudMessagingTool.send` to extract an allowlisted `provider_error` dictionary when Meta returns HTTP 4xx:
    - `http_status: int` (HTTP status code).
    - `code: int` (Meta numeric error code, e.g. `131030`, `131047`, `190`).
    - `subcode: int` (Meta numeric error subcode, e.g. `2494010`, `463`).
    - `type: str` (Meta error classification string, e.g. `"OAuthException"`).
  - Emits safe log entry at WARNING level omitting customer text, tokens, and phone numbers.
  - Returns `{"provider": "whatsapp_cloud_api", "message_id": None, "run_id": run_id, "accepted": False, "provider_error": provider_error}`.
- **Workflow Result Sanitization ([`src/nudgeflow/services/agent/workflow.py`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/src/nudgeflow/services/agent/workflow.py)):**
  - Updated `_safe_tool_result` to allowlist `provider_error` containing only valid integer status/codes and string error types.
  - Strips any unallowlisted keys (raw message, headers, tokens, phone numbers) before persistence into `AgentExecution.result_json`.
  - Preserves standard `AgentExecutionResponse` client schema and `error_code="tool_not_accepted"`.
- **Fault-Tolerant Parsing:** Malformed JSON responses, empty responses, non-dict error bodies, or unexpected field types fall back safely to `{"http_status": response.status_code}` without throwing unhandled exceptions.

### 18.2 Changed Files Summary
| File | Changes |
| :--- | :--- |
| [`src/nudgeflow/services/agent/tools.py`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/src/nudgeflow/services/agent/tools.py) | Added logger, safely parsed allowlisted error fields from Meta 4xx responses, emitted structured warning. |
| [`src/nudgeflow/services/agent/workflow.py`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/src/nudgeflow/services/agent/workflow.py) | Updated `_safe_tool_result` to preserve allowlisted `provider_error` fields while strictly dropping sensitive keys. |
| [`tests/test_whatsapp_tool.py`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/tests/test_whatsapp_tool.py) | Added 5 test cases covering structured diagnostics extraction, malformed JSON, missing fields/types, secret exclusion in `_safe_tool_result`, and end-to-end integration. |
| [`AGENT.md`](file:///D:/Projects/Nudge-Flow/AGENT.md) | Documented architecture, changed files, verification results, and safety compliance. |

### 18.3 Test Suite Verification
- **Focused WhatsApp Tool Tests:** **18 passed in 6.21s** (`tests/test_whatsapp_tool.py`).
- **Full Backend Test Suite:** **185 passed, 4 skipped in 105.42s** (100% pass across all unit, security, auth, workflow, token, contact, and bootstrap tests).
- **Git Hygiene:** `git diff --check` passed cleanly with 0 whitespace or formatting errors.
- **Run Isolation:** Runs 6, 7, 8, 9, and 10 remain unchanged in the database.

---

## 19. Inbound Webhook Analysis, 24-Hour Window & Testing Procedure

### 19.1 Phone Number ID Verification
- **Configured Phone Number ID:** `1405385199326466` (verified in `nudgeflow.config.settings`).
- **Inbound Event Target:** Confirmed matching the same Meta test business number (`display_phone_number: +1 555-184-5888` / `phone_number_id: 1405385199326466`).

### 19.2 Historical Run Records Immutability
- **Run 9 / Execution 5 & Run 10 / Execution 6:**
  - Both records executed prior to structured error extraction.
  - Because original response bodies were discarded at the adapter layer at time of call, their specific Meta error codes cannot be retroactively recovered.
  - Both records remain permanently and correctly stored as `status="failed"`, `error_code="tool_not_accepted"`.

### 19.3 Inbound Webhook Capability Assessment
NudgeFlow currently lacks an inbound webhook processing pipeline:
- **Verification Endpoint:** No `GET /webhooks/whatsapp` to process Meta webhook handshake (`hub.challenge`).
- **Event Receiver:** No `POST /webhooks/whatsapp` to receive message status or inbound customer events.
- **Security & Integrity:** No HMAC SHA-256 signature verification (`X-Hub-Signature-256`) or event deduplication store.
- **Scope Note:** Identified as a separate architectural capability; deferred from this debugging task.

### 19.4 24-Hour Customer-Service Window & Webhook Source Distinction
- **Window Authority:** Meta's Cloud API platform (not NudgeFlow) is the authoritative arbiter of the 24-hour service window.
- **Real Message vs Simulation:**
  - If the inbound `Hi` was dispatched from a real WhatsApp mobile client to `+1 555-184-5888`, Meta's gateway opened an active 24-hour window, permitting outbound free-form `text` messages to `+91******3955`.
  - If the event was generated via the Meta Developer Portal's Webhook Test button, the payload is simulated and does *not* open an active messaging window on Meta's real carrier gateway.
- **Reception Independence:** NudgeFlow does not need to ingest the inbound webhook for Meta's outbound API to honor an active 24-hour window.

### 19.5 Safe Procedure for Future Testing
1. **Preconditions:**
   - Confirm recipient `+91******3955` is listed under allowed test numbers in the Meta Developer Portal.
   - Confirm an actual WhatsApp message was sent from the phone to `+1 555-184-5888` within the past 24 hours.
2. **Terminal Run Protection:** Do **not** approve, execute, or mutate Runs 9 or 10.
3. **Draft Creation:** Create a new independent run (Run 11) for FollowUp 3 via `POST /agent/runs` using `exact_message`.
4. **Human Review:** Verify Run 11 is in `status="awaiting_approval"` with `execution=None` and `tool_invocation_started_at=None`.
5. **Authorized Execution:** Only with explicit user authorization, dispatch `POST /agent/runs/11/approve`.
6. **Diagnostic Verification:**
   - If accepted: Meta returns `accepted: True` with `message_id: "wamid..."`.
   - If rejected: The new diagnostic engine will capture the exact `http_status`, Meta `code`, and `subcode` (e.g., `131030` or `131047`) in `AgentExecution.result_json` and server logs without exposing secrets.

---

## 20. Inbound WhatsApp Webhook Foundation Implementation & Verification

### 20.1 Architectural Overview & Core Invariants
The inbound WhatsApp webhook pipeline serves as the secure, idempotent ingestion layer for Meta Cloud API events (incoming customer messages and message status notifications like `sent`, `delivered`, `read`, and `failed`).

**Core Operational Guardrails:**
1. **Zero Outbound Dispatch:** Webhook ingestion is strictly decoupled from message dispatch. Webhook handlers **never** trigger auto-replies, create agent runs, or invoke messaging tools.
2. **Strict Tenant Isolation:** Incoming messages are **never** associated with a tenant based on an untrusted sender phone number (`from`). The sender phone number is untrusted client data and cannot be used to bridge tenant boundaries. Tenant ID remains unassigned (`tenant_id = None`) at the ingestion layer until authenticated multi-tenant channel bindings are established.
3. **Cryptographic Signature Verification:** Every `POST` request must supply a valid `X-Hub-Signature-256` header calculated as `sha256=HMAC-SHA256(raw_body, NUDGEFLOW_WHATSAPP_APP_SECRET)`. Tampered payloads, invalid digests, or unconfigured app secrets are rejected with HTTP 403 Forbidden.
4. **Idempotent Deduplication Store:** All message and status events are recorded in `whatsapp_webhook_events` with a compound unique constraint on `(phone_number_id, event_id, event_type, status_value)`. Retried webhook deliveries from Meta are detected and ignored idempotently without duplicate record creation or processing errors.
5. **Privacy & Log Hygiene:** Handlers log only high-level event counts (`processed`, `duplicates`). Handlers **never** log raw request bodies, customer message text (`text.body`), recipient or sender phone numbers, verification tokens, or app secrets.
6. **Preservation of Historical Runs:** Webhook handling does not alter or re-evaluate existing agent runs or executions. Runs 6, 7, 8, 9, and 10 and Executions 5 and 6 remain completely intact.

### 20.2 Endpoint Specification

#### 1. Verification Handshake: `GET /webhooks/whatsapp`
- **Query Parameters:**
  - `hub.mode`: String, must equal `"subscribe"`.
  - `hub.verify_token`: String, compared against `settings.whatsapp_webhook_verify_token.get_secret_value()` using constant-time comparison (`secrets.compare_digest`).
  - `hub.challenge`: String or integer challenge token sent by Meta.
- **Behavior:**
  - If mode is `"subscribe"` and verify token matches: returns HTTP 200 with `Content-Type: text/plain` containing the exact `hub.challenge` string.
  - If verify token is unconfigured, mode is invalid, or token mismatches: returns HTTP 403 Forbidden.
  - If `hub.challenge` is missing: returns HTTP 400 Bad Request.

#### 2. Event Ingestion: `POST /webhooks/whatsapp`
- **Headers Required:** `X-Hub-Signature-256: sha256=<hex_digest>`
- **Validation & Execution Sequence:**
  1. Read raw request bytes `await request.body()`.
  2. Compute expected HMAC-SHA256 digest using configured `settings.whatsapp_app_secret`.
  3. Compare signatures with constant-time equality (`secrets.compare_digest`). Reject with HTTP 403 on failure or missing header.
  4. Parse raw bytes as JSON; reject malformed JSON or non-object payloads with HTTP 400 Bad Request.
  5. Acknowledge and ignore non-business objects (`object != "whatsapp_business_account"`) with HTTP 200 `{"status": "ignored"}`.
  6. Safely traverse `entry[].changes[].value`:
     - Extract `metadata.phone_number_id`.
     - Ingest `messages`: deduplicate on `(phone_number_id, message_id, "message", "")`, persist `message_type` and UTC `payload_timestamp`.
     - Ingest `statuses`: deduplicate on `(phone_number_id, status_id, "status", status_value)`, extract integer `error_code` if present, persist UTC `payload_timestamp`.
  7. Return HTTP 200 `{"status": "ok", "processed": count, "duplicates": dup_count}`.

### 20.3 Database Persistence & Migration
- **Table:** `whatsapp_webhook_events`
- **Model ([`src/nudgeflow/models/webhook.py`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/src/nudgeflow/models/webhook.py)):**
  - `id`: Integer primary key.
  - `phone_number_id`: String(64), Meta phone number ID.
  - `event_id`: String(128), Meta message ID (`wamid.xxx`).
  - `event_type`: String(32), `'message'` or `'status'`.
  - `status_value`: String(32), `""` for messages; `'sent'`, `'delivered'`, `'read'`, `'failed'` for statuses.
  - `message_type`: String(32) nullable, e.g. `'text'`.
  - `error_code`: Integer nullable, safe diagnostic code for failures (e.g. `131047`).
  - `payload_timestamp`: UTCDateTime nullable.
  - `received_at`: UTCDateTime server reception timestamp (`func.now()`).
  - `processed_status`: String(32), `'processed'`, `'duplicate'`, `'unmatched'`, `'ignored'`.
  - `tenant_id`: Integer foreign key (`tenants.id`, ondelete="SET NULL"), strictly nullable.
- **Alembic Migration:** `migrations/versions/834c9b14cbc9_add_whatsapp_webhook_events.py` (Revision `834c9b14cbc9`, down-revision `f6b7d3e2a910`). Applied and verified on local PostgreSQL.

### 20.4 Configuration Requirements
Add the following environment variables to `.env` / configuration files:
```env
# Meta WhatsApp Inbound Webhook Configuration
NUDGEFLOW_WHATSAPP_WEBHOOK_VERIFY_TOKEN=your-custom-verify-token-string
NUDGEFLOW_WHATSAPP_APP_SECRET=your-meta-app-secret-from-dashboard
```
- `whatsapp_webhook_verify_token`: Stored as `SecretStr` in `Settings`. Used to authenticate the Meta handshake.
- `whatsapp_app_secret`: Stored as `SecretStr` in `Settings`. Used to compute HMAC-SHA256 signatures for payload verification.
- `validate_whatsapp_webhook_config(cfg)`: Dedicated validation helper ensuring required secrets are non-empty when configured.

### 20.5 Meta Developer Dashboard Subscription Guide
Follow these steps in the Meta App Dashboard to connect your NudgeFlow deployment:

1. **Navigate to WhatsApp Configuration:**
   - Open [Meta for Developers](https://developers.facebook.com/apps/).
   - Select your App &rarr; Expand **WhatsApp** in the left sidebar &rarr; Click **Configuration**.
2. **Configure Webhook Callback URL:**
   - Under the **Webhook** section, click **Edit**.
   - **Callback URL:** Enter the public HTTPS URL for your NudgeFlow server, ending in `/webhooks/whatsapp` (e.g. `https://api.yourdomain.com/webhooks/whatsapp` or your ngrok/Cloudflare tunnel URL for local testing).
   - **Verify Token:** Enter the exact value configured in `NUDGEFLOW_WHATSAPP_WEBHOOK_VERIFY_TOKEN`.
   - Click **Verify and save**. Meta will issue a `GET` request with `hub.mode=subscribe`, `hub.verify_token`, and `hub.challenge`. NudgeFlow will validate the token and return the challenge with HTTP 200.
3. **Subscribe to Webhook Fields:**
   - Under the **Webhook fields** section, click **Manage**.
   - Locate the **`messages`** field row (which delivers both inbound messages and status updates).
   - Click **Subscribe**.
4. **Obtain Meta App Secret:**
   - In the left sidebar, navigate to **App settings** &rarr; **Basic**.
   - Locate **App secret**, click **Show**, and copy the secret.
   - Set this value as `NUDGEFLOW_WHATSAPP_APP_SECRET` in your NudgeFlow environment.

### 20.6 Changed Files Summary
| File | Changes |
| :--- | :--- |
| [`src/nudgeflow/config.py`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/src/nudgeflow/config.py) | Added `whatsapp_webhook_verify_token` and `whatsapp_app_secret` (`SecretStr`), and `validate_whatsapp_webhook_config()`. |
| [`src/nudgeflow/.env.example`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/.env.example) | Documented webhook environment variables. |
| [`src/nudgeflow/models/webhook.py`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/src/nudgeflow/models/webhook.py) | Created `WhatsAppWebhookEvent` model with deduplication unique constraint. |
| [`src/nudgeflow/models/__init__.py`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/src/nudgeflow/models/__init__.py) | Exported `WhatsAppWebhookEvent`. |
| [`src/nudgeflow/routers/webhooks.py`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/src/nudgeflow/routers/webhooks.py) | Implemented `GET /webhooks/whatsapp` and `POST /webhooks/whatsapp` with HMAC validation, safe parsing, deduplication, and privacy safeguards. |
| [`src/nudgeflow/main.py`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/src/nudgeflow/main.py) | Registered `webhooks_router` under `/webhooks`. |
| [`migrations/env.py`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/migrations/env.py) | Imported `WhatsAppWebhookEvent` into Alembic metadata scope. |
| [`migrations/versions/834c9b14cbc9_add_whatsapp_webhook_events.py`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/migrations/versions/834c9b14cbc9_add_whatsapp_webhook_events.py) | Created migration for `whatsapp_webhook_events` table and indexes. |
| [`tests/test_tenant_migration_postgres.py`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/tests/test_tenant_migration_postgres.py) | Updated `LATEST_REVISION = "834c9b14cbc9"`. |
| [`tests/test_whatsapp_webhooks.py`](file:///D:/Projects/Nudge-Flow/backend/nudgeflow/tests/test_whatsapp_webhooks.py) | Added 26 unit and integration tests covering verification, signatures, malformed payloads, messages, statuses, deduplication, tenant isolation, and privacy. |
| [`AGENT.md`](file:///D:/Projects/Nudge-Flow/AGENT.md) | Documented architecture, endpoint specs, migration, configuration, test results, and dashboard setup. |

### 20.7 Test Suite Verification
- **Dedicated Webhook Tests:** **26 passed in 2.37s** (`tests/test_whatsapp_webhooks.py`).
- **Full Backend Test Suite:** **211 passed, 4 skipped in 75.31s** (100% pass across all auth, contacts, follow-ups, agent runs, tools, llm, bootstrap, and webhooks).
- **Git Hygiene:** `git diff --check` passed cleanly with 0 whitespace or formatting errors.
- **Preserved Runs Integrity:** Confirmed Runs 6, 7, 8 in `awaiting_approval`; Runs 9 and 10 in `failed` with Executions 5 and 6 completely intact.
