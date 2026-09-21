# IT3041 Remote Workforce System

A multi-agent remote workforce management web application.

---

## 1. Backend Setup & Instructions

### Environment Variables
Configure a `.env` file inside the `backend/` directory with the following variable names (never commit secret values):
- `MONGODB_HOST` — MongoDB cluster host URL
- `MONGODB_USERNAME` — Database user
- `MONGODB_PASSWORD` — Database password
- `MONGODB_DATABASE` — Database name
- `JWT_SECRET_KEY` — Cryptographic signing key for HS256 access tokens
- `LLM_API_KEY` — API key for OpenAI-compatible LLM provider (optional in test environments using `FakeLLMGateway`)
- `LLM_BASE_URL` — Base URL for LLM provider (defaults to `https://api.openai.com/v1`)
- `LLM_MODEL` — Chat completion model identifier (defaults to `gpt-4o-mini`)
- `LLM_TIMEOUT_SECONDS` — Request timeout limit in seconds (defaults to `30.0`)
- `LLM_MAX_RETRIES` — Maximum retry count for transient network/rate-limit errors (defaults to `3`)

To generate a secure 256-bit random key locally without exposing it:
```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Dependency Installation
Activate your Python virtual environment and install packages:

```powershell
# Production dependencies
pip install -r backend/requirements.txt

# Development & test dependencies
pip install -r backend/requirements-dev.txt
```

### Running the Backend Server
Start the FastAPI server on `http://127.0.0.1:8000`:

```powershell
uvicorn backend.app.main:app --reload
```

Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

### Running Backend Tests
```powershell
pytest backend/tests
```

Run baseline connectivity and security checks:
```powershell
python backend/scripts/check_security.py
python backend/scripts/check_db.py
```

---

## 2. Frontend Setup & Instructions

The frontend is built with React and Vite, using Vanilla CSS for a polished, responsive user experience.

### Dependency Installation
```powershell
cd frontend
npm install
```

### Running the Frontend Development Server
Start the Vite development server on `http://127.0.0.1:5173`:

```powershell
cd frontend
npm run dev
```

> **Note on API Proxy:** In development mode, Vite automatically proxies `/api/*` requests to the local backend at `http://127.0.0.1:8000/*`. This proxy configuration is for local development only.

### Running Frontend Tests & Production Build
```powershell
# Run Vitest test suite
cd frontend
npm test

# Build production bundle
npm run build
```

---

## 3. API Endpoints & Role Permission Matrix

| Endpoint | Method | Allowed Roles / Auth | Description |
| :--- | :--- | :--- | :--- |
| `/health` | `GET` | Public | Application liveness check |
| `/health/db` | `GET` | Public | MongoDB Atlas connectivity check |
| `/auth/register` | `POST` | Public | Create employee account (`extra="forbid"`, min 15-char password) |
| `/auth/login` | `POST` | Public | Authenticate user & issue 15-min JWT access token (`Cache-Control: no-store`) |
| `/auth/me` | `GET` | Authenticated (`employee`, `manager`, `admin`) | Retrieve current sanitized user profile |
| `/admin/access-check` | `GET` | `admin` | Administrative route guard verification |
| `/management/access-check` | `GET` | `manager`, `admin` | Management route guard verification |
| `/pulse-surveys/responses` | `POST` | `employee` | Submit weekly pulse survey response (server-derived user, team, week) |
| `/pulse-surveys/my-responses` | `GET` | `employee` | View authenticated employee's own pulse survey history |
| `/pulse-surveys/team-summary` | `GET` | `manager` | View privacy-thresholded team aggregate metrics (min 3 responses) |
| `/admin/pulse-surveys` | `GET` | `admin` | Audit pulse survey submission metadata (privacy-safe, read-only) |
| `/admin/pulse-surveys/summary` | `GET` | `admin` | Organization-wide per-team pulse summaries with privacy thresholding |
| `/api/search` | `GET` | Authenticated (`employee`, `manager`, `admin`) | Lexical Information Retrieval with BM25 ranking and pre-ranking RBAC |

### JSON Login Request Example
```json
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "YourSecurePassword123!"
}
```

**Successful Response (HTTP 200):**
```json
{
  "access_token": "<jwt-token-string>",
  "token_type": "bearer",
  "expires_in": 900
}
```

---

## 4. Information Retrieval Module (BM25 Lexical Search)

The system provides an explainable, deterministic lexical information retrieval module over MongoDB-backed workforce data.

### Searchable Sources
1. **Tasks**:
   - Task title (weighted 2x)
   - Task description
   - Required competencies / skills
   - Progress update notes
   - Blocker descriptions and resolution notes
2. **Collaboration Messages**:
   - Active collaboration message content authorized for the current user

### BM25 Ranking Engine
- Lexical scoring implemented directly in Python using the Okapi BM25 standard model:
  - $k_1 = 1.5$ (term frequency saturation parameter)
  - $b = 0.75$ (document length normalization parameter)
- Task titles are boosted with 2x lexical weight to prioritize direct title matches.
- Plain-text contextual snippets are generated with identified section markers (e.g., `[Title]`, `[Blocker]`, `[Progress]`, `[Message]`) without HTML or unsafe markup.

### Role-Aware Pre-Ranking Authorization
Security boundaries are strictly applied at database query time **before** candidate documents are tokenized or scored:
- **Employee**:
  - Tasks: Only tasks assigned to the employee (`assigned_to == user_id`).
  - Messages: Only active messages from the employee's assigned team (`is_deleted == false`).
  - Team Filter: Querying another team returns `403 Forbidden`.
- **Manager**:
  - Tasks & Messages: Restricted strictly to teams managed by the authenticated manager (`manager_id == user_id`).
  - Team Filter: Querying an unmanaged team returns `403 Forbidden`.
- **Admin**:
  - Read-only audit search across all organization tasks and collaboration messages.
  - Retained deleted message content is excluded by default and searchable only when `include_deleted=true` is explicitly requested.

### Privacy Exclusions
The Information Retrieval module strictly excludes the following from indexing and search results:
- Weekly pulse survey individual responses, metric ratings, and optional comments
- User password hashes and credentials
- JWT tokens and session secrets
- Retained deleted message content for Employee and Manager roles

### Current Limitations
- **Lexical Retrieval Only**: Retrieval is purely lexical (BM25 term matching); vector embeddings, semantic similarity, dense retrieval, and external search engines (e.g. Elasticsearch) are not included in this phase.
- **No Generative AI / LLM Agents**: This module provides the retrieval foundation only. Conversational AI interfaces, LLM reasoning, and automated agent workflows are implemented in subsequent phases.

---

## 5. Agentic AI Foundation – Phase 1

The system provides the versioned protocol contracts and centralized gateway infrastructure for multi-agent reasoning.

### Versioned Agent-to-Agent (A2A) Protocol
- **Contract Version**: `1.0` (fixed string literal in request and response envelopes).
- **Strict Validation**: All protocol envelopes enforce `extra="forbid"` with Pydantic v2 to reject unexpected fields and prevent injection.
- **Traceability**: Shared `correlation_id` spans all sub-agent requests within a user query; every envelope generates a unique server-side `message_id` (UUID v4) and timezone-aware UTC `created_at` timestamp.
- **Privacy Boundaries**: Generic evidence references support `task`, `collaboration_message`, `pulse_summary`, `employee_profile`, and `agent_finding`. Individual raw pulse response documents (`pulse_response`) are explicitly forbidden from generic evidence models to protect employee privacy.

### Supported Agent Identities
- `coordinator`: Central supervisor receiving user intents and orchestrating sub-agent dependencies.
- `productivity`: Specialist analyzing task delivery milestones, velocities, and sprint metrics.
- `collaboration`: Specialist analyzing communication volume, team participation, and collaboration bottlenecks.
- `wellbeing`: Specialist analyzing aggregated team pulse summaries and workload balance indicators.
- `task_assigning`: Specialist recommending optimal task distribution based on required competencies and employee capacity.

### Centralized LLM Gateway
- **Interface**: Abstract `LLMGateway` defining `generate_structured(system_prompt, user_prompt, response_model, correlation_id)`.
- **OpenAI-Compatible Implementation**: `OpenAICompatibleLLMGateway` connects asynchronously to any OpenAI-compatible completions endpoint with `response_format={"type": "json_object"}`.
- **Pydantic Response Validation**: All provider outputs are parsed and validated against strict Pydantic schemas before returning to agents; raw unvalidated JSON is never passed to agents.
- **Transient-Only Retries**: Deterministic exponential backoff is applied strictly for transient failures (HTTP 429, 5xx, network timeouts); client errors (HTTP 400, 401, 403, 422) fail immediately without retrying.
- **Security & Secret Sanitization**: Exception messages and logging strictly omit API keys, authorization headers, and raw user prompts.
- **Deterministic Test Double**: `FakeLLMGateway` allows full offline unit testing of agent workflows with programmable structured responses and call tracking without network access or real credentials.

### Prompt-Injection Evidence Boundary
- Evidence retrieved from workplace data is structured via `format_evidence_for_prompt()` into JSON-delimited `=== BEGIN_UNTRUSTED_EVIDENCE_JSON ===` data blocks.
- The prompt explicitly instructs the LLM that retrieved content is untrusted data and must never be interpreted as executable instructions or allowed to override system instructions.
- Enforces strict character budgets to prevent prompt-length exhaustion attacks.

### Phase 1 Limitations
- **Foundation Only**: Specialist agent business logic, the Coordinator orchestrator, conversation history persistence, and public chat endpoints are implemented in subsequent phases.
- **No Direct LLM Calls**: Domain modules and frontend UI do not call the LLM Gateway directly; all generative workflows will route through the Coordinator in Phase 2.

---

## 6. Agentic AI Security Policy & Audit Foundation – Phase 2

The system provides a centralized security policy layer and privacy-safe audit logging foundation governing agent interactions.

### Trusted Principal Context
- **AuthenticatedPrincipal**: Strict server-derived context containing `user_id`, `role` (`employee`, `manager`, `admin`), `assigned_team_id`, and deduplicated `managed_team_ids`.
- **Zero Client Trust**: Principals are constructed strictly by authoritative database lookup; client JSON or A2A header claims are never trusted for identity or authorization.
- **Role Constraints**: Employees cannot carry managed teams; Managers carry verified managed team IDs.

### Centralized Capability Allowlists
- **Agent Capability Allowlist**: Strict mapping of each specialist agent to permitted `AgentIntent`s and `EvidenceSourceType`s.
- **Privacy Boundaries**:
  - `task_assigning` agent is strictly forbidden from accessing `pulse_summary`, `collaboration_message` content, raw pulse responses, or protected personal attributes.
  - `wellbeing` agent is restricted strictly to aggregate `pulse_summary` and verified `agent_finding` data.

### Role & Team-Scope Policy
- **Employee**: Authorized for productivity/collaboration/wellbeing within assigned team tasks; strictly forbidden from task assignment recommendations or team workload overviews.
- **Manager**: Authorized for productivity/collaboration/wellbeing and task assignment recommendations scoped strictly to managed teams; cannot receive individual pulse responses.
- **Admin**: Read-only organization-wide analytics; task assignment recommendations are disabled by default.
- **Defense-in-Depth**: Policy validation serves as defense-in-depth; specialist data services must also enforce database-level RBAC filters when querying MongoDB.

### Cross-Agent Dependency Graph
- Communication flows are restricted to the explicit dependency graph:
  - `Coordinator -> *` (dispatch to specialists)
  - `Productivity -> Task Assigning` (safe task delivery findings)
  - `Collaboration -> Task Assigning` (safe communication/blocker findings)
  - `* -> Coordinator` (specialist findings returned to supervisor)
- **Strictly Prohibited**: `Wellbeing -> Task Assigning` and `Task Assigning -> Wellbeing` flows are rejected by policy.
- **Impersonation Prevention**: Dependency finding `agent` identity must match the declared message sender.

### Responsible AI Guardrails
- **Advisory Only**: Task assignment recommendations are strictly advisory requiring human manager confirmation; automatic database mutation is prohibited.
- **Wellbeing Isolation**: Wellbeing metrics and pulse data are strictly prohibited from influencing task assignment recommendations.
- **Evidence Requirement**: Employment-related recommendations require verified evidence references or explicit limitations when evidence is insufficient.
- **Prohibited Analyses**: Medical diagnoses, clinical mental-health labels, and punitive employee rankings are strictly forbidden across all agent workflows.

### Privacy-Safe Audit Events & Sinks
- **AgentAuditEvent**: Immutable audit record tracking `event_id` (UUID v4), `correlation_id`, `actor_user_id`, `actor_role`, `agent`, `event_type`, `outcome`, `evidence_count`, and `safe_reason_code`.
- **Absolute Privacy Guarantees**: Audit events and logs strictly exclude user questions, system/user prompts, evidence snippets, message text, pulse comments, PII (names/emails), credentials, and raw provider payloads.
- **Sinks**: Abstract `AgentAuditSink`, in-memory `InMemoryAgentAuditSink` for testing, and `SafeLoggingAgentAuditSink` for structured safe logging.

---

## 7. Current Architecture & Session Limitations

1. **In-Memory Session Storage:** JWT access tokens are stored strictly in-memory (React state) to prevent browser storage XSS exposure. Page reloads currently require signing in again.
2. **Token Lifetime & Refresh:** Access tokens expire in 15 minutes. Refresh tokens and server-side token revocation blocklists are not yet implemented.
3. **Dynamic Role Verification:** The backend resolves the token subject against the live database record on each request, ensuring role modifications or deactivations take effect immediately.
4. **Role Scope & Privacy Thresholding:** Weekly pulse surveys provide employee self-submission, manager team aggregates with a strict minimum response threshold of 3 for anonymity, and admin privacy-safe audit metadata. No individual well-being scores, mood/stress classifications, or diagnostic labels are computed or exposed.
5. **Specialist AI Agents:** The four specialist agents (*Productivity, Collaboration, Wellbeing, Task Assignment*) are designated for development on their respective feature branches; no synthetic results are simulated.
