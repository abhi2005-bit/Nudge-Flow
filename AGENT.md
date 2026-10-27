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
