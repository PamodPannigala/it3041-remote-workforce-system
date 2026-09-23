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
- `LLM_PROVIDER` — Production LLM provider (`gemini` or `openai_compatible`)
- `GEMINI_API_KEY` — API key for Google Gemini LLM provider (production fails closed if missing)
- `GEMINI_MODEL` — Gemini model identifier (e.g., `gemini-3.6-flash`)
- `GEMINI_TIMEOUT_SECONDS` — Gemini request timeout in seconds (defaults to `30.0`)
- `GEMINI_MAX_RETRIES` — Gemini max retries for transient errors (defaults to `3`)
- `GEMINI_TEMPERATURE` — Generation temperature (defaults to `0.2`)
- `GEMINI_MAX_OUTPUT_TOKENS` — Max output tokens (defaults to `2048`)
- `LLM_API_KEY` — API key for OpenAI-compatible LLM provider (optional fallback)
- `LLM_BASE_URL` — Base URL for OpenAI-compatible LLM provider (defaults to `https://api.openai.com/v1`)
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

## 7. Agentic AI Custom Multi-Agent Runtime – Phase 3

The system implements a lightweight, application-specific, custom multi-agent runtime written natively in Python without relying on external agent frameworks (e.g., CrewAI, LangGraph, AutoGen).

### Why a Custom Runtime?
- **Zero Heavy External Dependencies**: Avoids dependency bloat, transitive pinning conflicts, and speculative third-party framework changes.
- **Strict Compliance with Existing Architecture**: Reuses the project's Pydantic v2 schemas, `LLMGateway`, `AuthenticatedPrincipal`, `SecurityPolicy`, and `AgentAuditSink` directly.
- **Zero Unsafe Features**: By design, the custom runtime contains no autonomous agent delegation, no dynamic code execution, no persistent conversational memory across requests, and no uncontrolled tool invocation loops.

### Runtime Architecture & Responsibilities
- **`AgentRuntimeConfig`**: Strict immutable configuration enforcing bounded timeouts, maximum concurrent executions, evidence payload boundaries, and output character limits (`extra="forbid"`).
- **`AgentDefinition`**: Declarative immutable registration model binding an agent's identity, role, goal, allowed intents, allowed evidence source types, system instructions, and Pydantic response schema.
- **`ExecutionContext`**: Strongly typed execution context carrying the server-derived `AuthenticatedPrincipal`, request envelope, upstream dependency findings, and correlation ID.
- **`BaseAgentTool` & `AgentTool` Protocol**: Explicit, typed tool interface executing deterministic async evidence gathering. Tools are validated against target agent identity and required capabilities prior to execution.
- **`AgentRuntime`**: Central execution manager performing the end-to-end execution flow:
  1. Enforces user intent RBAC and agent capability matrix via `SecurityPolicy`.
  2. Enforces cross-agent dependency flow and correlation ID provenance.
  3. Enforces team-scope boundaries on all retrieved evidence references (defense-in-depth).
  4. Formats untrusted workplace evidence into prompt-injection-safe JSON data blocks.
  5. Invokes `LLMGateway` exactly once with bounded execution timeouts (`asyncio.wait_for`).
  6. Validates structured LLM outputs against declared Pydantic response models.
  7. Enforces Responsible AI guardrails (advisory task assignments, no punitive rankings, no medical diagnoses).
  8. Emits privacy-safe structured audit events (`AgentAuditEvent`) for both success and failure outcomes.
- **`execute_many`**: Bounded concurrent execution helper executing independent requests concurrently while respecting `max_concurrent_executions`, preserving input ordering, and enforcing independent security checks per item.
- **`FakeAgentRuntime`**: Deterministic offline test double allowing comprehensive testing of specialist agents and supervisor flows without network requests or external LLM credentials.

### Architectural Separation of Concerns
```
[FastAPI Auth & Session] -> AuthenticatedPrincipal (authoritative server-side identity)
         │
         ▼
[AgentRequest Envelope] -> Protocol 1.0 (correlation_id, sender, recipient, intent)
         │
         ▼
[Security Policy] --------> RBAC, team-scope validation, capability allowlist, provenance
         │
         ▼
[AgentRuntime] -----------> Explicit tool gathering, evidence formatting, bounded timeout
         │
         ▼
[LLMGateway] -------------> Single execution path, structured Pydantic output validation
         │
         ▼
[Audit Logging] ----------> Privacy-safe audit events (zero prompts, evidence snippets, or keys)
```

### Privacy & Well-being Isolation Boundary
The runtime structurally enforces the privacy boundary preventing Well-being findings or pulse data from influencing Task Assignment decisions:
- `validate_dependency_flow()` strictly rejects any dependency finding from `wellbeing` to `task_assigning`.
- `validate_responsible_ai_guardrails()` prohibits automated task mutation and requires all task recommendations to be advisory with human manager confirmation.

---

## 8. Productivity Specialist Agent

The system implements the **Productivity Specialist Agent** natively on top of the shared custom Python multi-agent runtime.

### Purpose & Scope
The Productivity Agent analyzes authorized task-management evidence and returns explainable, advisory productivity observations and factual workload insights. It does not perform autonomous task mutations, employee rankings, performance scorings, or punitive evaluations.

### Authorized Data Sources & Exclusions
- **Authorized Task Fields**: `_id`, `title`, `description`, `status` (`todo`, `in_progress`, `blocked`, `completed`), `progress_percentage` (0–100), `priority`, `due_date`, `assigned_to`, `team_id`, `blockers` (`description`, `is_resolved`, `resolved_at`), `progress_history` (`notes`, `updated_at`), and `required_skills` (to understand task context).
- **Strict Privacy Exclusions**: The agent never accesses or queries weekly pulse surveys, individual ratings, pulse comments, well-being metrics, collaboration message content, or protected personal characteristics.

### Role & Team Scoping (Database Pre-Filtering)
Authorization filters are strictly applied at the database level before documents become candidates:
- **Employee**: Strictly filtered to tasks assigned to the authenticated user (`assigned_to == user_id`) and belonging to their authorized team (`team_id == assigned_team_id`). Cross-team queries are rejected.
- **Manager**: Scoped strictly to tasks belonging to teams the manager actually manages (`team_id in managed_team_ids`). Unmanaged team queries are rejected.
- **Admin**: Audits organization-wide tasks within the authorized productivity intent boundaries.
- **Unassigned User**: Returns an empty authorized evidence set; never leaks organization or other team data.

### Deterministic Python Metrics
Key workload and velocity metrics are calculated deterministically in Python prior to LLM invocation (not guessed by the LLM):
- **Total Authorized Tasks**: Count of authorized tasks matching the scope.
- **Counts by Status**: Completed, In Progress, Blocked, and To-Do.
- **Completed Task**: Status is `completed` (or progress is 100%).
- **Blocked Task**: Status is `blocked` or contains unresolved blockers (`is_resolved == false`).
- **Overdue Task**: Non-completed task where `due_date` is strictly before the current UTC timestamp (`due_date < now_utc`).
- **Due Soon Task**: Non-completed task with `due_date` falling within the next 7 days in UTC (`now_utc <= due_date <= now_utc + 7 days`).
- **Average Progress**: Arithmetic mean of valid `progress_percentage` (0–100) across authorized tasks; safely omitted if no tasks have valid progress.
- **Blockers Count**: Explicit count of unresolved blockers vs resolved blockers.

### Structured Output Contract (`ProductivityFindingOutput`)
The agent produces a strictly validated Pydantic model (`extra="forbid"`):
- `summary`: Concise, factual executive summary.
- `workload_observations`: Bulleted list of factual task distribution and volume observations.
- `completion_and_overdue_observations`: Factual delivery milestone and overdue task observations.
- `blocker_observations`: Observations on active blockers and delivery impediments.
- `recommended_actions`: Concrete, evidence-backed advisory recommendations.
- `confidence`: Bounded numeric confidence score (0.0 to 1.0).
- `limitations`: Explicit disclosures when evidence is sparse, missing, or limited.

### Security, Privacy & Responsible AI Controls
- **Advisory Only**: Output recommendations are strictly advisory for human managers/employees; autonomous mutations are prohibited.
- **No Ranking or Punishment**: Strictly forbids employee ranking, peer comparison, punitive actions, or automated termination/disciplinary recommendations.
- **No Medical/Well-being Inferences**: Prohibits mental health, stress, or diagnostic claims.
- **Untrusted Evidence Boundary**: Task titles, descriptions, and notes are formatted into structured JSON evidence blocks and treated as untrusted data, neutralizing prompt injection attempts.
- **Single LLM Gateway Call**: Invokes the shared `LLMGateway` exactly once per execution with bounded timeout and exponential retry handling.

### Offline Testing Strategy
Comprehensive test suite (`backend/tests/agents/test_productivity_agent.py`) verifies all features offline without network calls or external credentials:
- Role/team MongoDB query filtering and pre-query authorization.
- Deterministic metric calculations, UTC boundary handling, and legacy/missing field resilience.
- Structured output validation, single-call gateway verification, and sanitized error handling.
- Responsible AI guardrail enforcement and audit sink log sanitization.

---

## 9. Collaboration Specialist Agent

The system implements the **Collaboration Specialist Agent** natively on top of the shared custom Python multi-agent runtime.

### Purpose & Scope
The Collaboration Agent analyzes authorized team collaboration messages and task-blocker evidence to return explainable, objective, and advisory communication pattern insights, dependency risks, and blocker bottlenecks. It does not perform employee rankings, sentiment scoring on individuals, punitive recommendations, or autonomous mutations.

### Authorized Data Sources & Exclusions
- **Authorized Collaboration Message Fields**: `_id`, `team_id`, `sender_id`, `content`, `created_at`, `updated_at`, `edited_at`, `is_deleted`, `deleted_at`.
- **Authorized Task & Blocker Fields**: `_id`, `team_id`, `status`, `title`, `description`, `blockers` (`id`, `user_id`, `description`, `is_resolved`, `resolution_note`, `resolved_at`, `resolved_by`, `created_at`).
- **Strict Privacy Exclusions**: The agent never accesses or queries weekly pulse survey records (`weekly_pulse_responses`), individual pulse ratings, pulse comments, employee profiles, credentials, or protected personal characteristics.

### Soft-Deleted Message Exclusion Policy
Soft-deleted messages (`is_deleted == true`) are strictly excluded from all queries, candidate sets, evidence references, deterministic metrics, snippets, prompts, and recommendations across all roles (**Employee**, **Manager**, and **Admin**). Retained deleted message content in administrative audits is never exposed to or processed by the agent.

### Role & Team Scoping (Database Pre-Filtering)
Authorization filters are strictly applied at the database level before documents become candidates:
- **Employee**: Strictly filtered to active messages and task blockers within the employee's assigned team (`team_id == assigned_team_id`). Cross-team queries are rejected. Unassigned employees receive an empty evidence set.
- **Manager**: Scoped strictly to messages and task blockers belonging to teams the manager actually manages (`team_id in managed_team_ids`). Unmanaged team queries are rejected. Managers with no managed teams receive an empty evidence set.
- **Admin**: Read-only organization-wide or requested-team analysis within the authorized collaboration intent boundaries.
- **Defense-in-Depth**: Retained evidence references undergo secondary team-scope validation prior to formatting.

### Deterministic Python Metrics
Key collaboration and blocker metrics are calculated deterministically in Python prior to LLM invocation:
- **Active Messages Count**: Count of active non-deleted messages within the lookback window (default: 30 days).
- **Distinct Active Participants**: Count of distinct senders in active messages within the lookback window.
- **Tasks with Active Blockers**: Count of tasks with at least one unresolved blocker or with status `blocked`.
- **Unresolved Blockers**: Count of active unresolved blockers.
- **Stale Blockers Count**: Deterministically computed count of unresolved blockers older than 7 UTC days (`now_utc - created_at > 7 days`).
- **Resolved Blockers Count**: Count of resolved blockers.
- **Average Resolution Time (Hours)**: Arithmetic mean resolution duration computed strictly when both valid `created_at` and `resolved_at` timestamps exist and `resolved_at >= created_at`.
- **Invalid Timestamp Count**: Count of malformed or invalid timestamp entries safely excluded from averages.

### Structured Output Contract (`CollaborationFindingOutput`)
The agent produces a strictly validated, frozen Pydantic model (`extra="forbid"`):
- `summary`: Concise, factual executive summary of collaboration patterns and blocker state.
- `communication_observations`: Bulleted list of factual communication patterns and coordination observations.
- `blocker_observations`: Observations on active, stale, and resolved task blockers.
- `dependency_risks`: Identified cross-team and technical dependency bottlenecks.
- `recommended_actions`: Concrete, safe advisory recommendations (clarification, follow-up, documentation, escalation, team discussion).
- `confidence`: Bounded numeric confidence score (0.0 to 1.0).
- `limitations`: Explicit disclosures when evidence is sparse, missing, or limited.

### Security, Privacy & Responsible AI Controls
- **Advisory Only**: Output recommendations are strictly advisory suggestions for teams and managers; autonomous task reassignments or database mutations are prohibited.
- **No Ranking, Blame, or Punishment**: Strictly forbids employee ranking, blaming individual workers, sentiment scoring of individuals, or recommending disciplinary/punitive actions.
- **No Medical/Emotional Diagnoses**: Strictly prohibits clinical, mental health, stress, or emotional state inferences.
- **Untrusted Evidence Boundary**: Collaboration message contents and blocker descriptions are structured into JSON evidence blocks delimited by `=== BEGIN_UNTRUSTED_EVIDENCE_JSON ===`, neutralizing prompt injection attempts.
- **Explicit Tool Execution**: Canonical tools (`collaboration_message_evidence`, `collaboration_task_blocker_evidence`) are invoked explicitly; invoking the runtime with `tool_names=None` runs zero tools.
- **Single LLM Gateway Call**: Invokes the shared `LLMGateway` exactly once per execution with bounded timeout and exponential retry handling.

### Offline Testing Strategy
Comprehensive test suite (`backend/tests/agents/test_collaboration_agent.py`) verifies all features offline without network calls or external credentials:
- Role/team MongoDB query filtering and pre-query authorization.
- Soft-deleted message exclusion across Employee, Manager, and Admin roles.
- Deterministic metric calculations, UTC boundary handling, and stale blocker thresholds.
- Structured output validation, single-call gateway verification, and sanitized error handling.
- Responsible AI guardrail enforcement and audit sink log sanitization.

---

## 10. Well-being Specialist Agent

The system implements the **Well-being Specialist Agent** natively on top of the shared custom Python multi-agent runtime.

### Purpose & Scope
The Well-being Agent analyzes privacy-preserving, aggregated Weekly Pulse Survey metrics and returns explainable, objective, supportive, and advisory team well-being observations. It assists managers and organizations in understanding workload manageability, work-life balance signals, and team support trends without ever unmasking individual respondents or making medical claims.

### Authorized Data Sources & Strict Projections
- **Authorized Pulse Fields**: `team_id`, `week_start`, `workload_manageability` (1–5), `work_life_balance` (1–5), `team_support` (1–5), `engagement` (1–5).
- **Strict Privacy Exclusions**: The agent strictly excludes and never projects or fetches:
  - `user_id` (respondent identifiers)
  - Employee names or email addresses
  - Raw individual response ratings
  - `optional_comment` (confidential free-text comments)
  - `edit_history` and internal revision logs
  - Collaboration messages, task descriptions, employee profiles, or credentials.

### Privacy Boundary & k-Anonymity Threshold (k = 3)
The pulse survey privacy contract is strictly enforced before evidence reaches the LLM:
- **Minimum Response Threshold**: If a team has fewer than 3 responses in a given week, aggregate metrics are withheld and marked as `INSUFFICIENT DATA`.
- **Zero Raw Data Exposure**: Only aggregated metrics satisfying the k=3 privacy threshold are converted into evidence references.
- **Cross-Agent Isolation**: Well-being findings are strictly prohibited from flowing into the Task Assignment Agent (`validate_dependency_flow` and `validate_responsible_ai_guardrails` reject any such flow).

### Role & Team Scoping (Database Pre-Filtering)
Authorization filters are strictly applied at the database level before documents become candidates:
- **Employee**: Scoped strictly to the employee's assigned team (`assigned_team_id`). Cross-team queries are rejected. Unassigned employees receive an empty evidence set.
- **Manager**: Scoped strictly to teams the manager manages (`team_id in managed_team_ids`). Unmanaged team queries are rejected. Managers with no managed teams receive an empty evidence set.
- **Admin**: Read-only organization-wide or requested-team aggregate analysis within authorized well-being intent boundaries.

### Deterministic Python Metrics
Key well-being and trend metrics are calculated deterministically in Python prior to LLM invocation:
- **Response Counts**: Total response counts per team and UTC week.
- **Weekly Averages**: Arithmetic mean workload manageability, work-life balance, team support, and engagement scores (1–5) computed strictly for weeks meeting the k=3 threshold.
- **Week-over-Week Trends**: Difference between the two most recent privacy-safe weeks for a team.
- **Privacy-Safe Weeks Count**: Count of weekly buckets meeting the minimum response threshold.
- **Insufficient-Data Weeks Count**: Count of weekly buckets with fewer than 3 responses.
- **Invalid Rating Handling**: Rejects booleans, non-numeric strings, NaNs, infinities, and values outside 1–5 without raising uncaught exceptions.

### Structured Output Contract (`WellbeingFindingOutput`)
The agent produces a strictly validated, frozen Pydantic model (`extra="forbid"`, `frozen=True`):
- `summary`: Concise, supportive executive summary of team well-being signals.
- `aggregate_observations`: Factual observations based on verified aggregate ratings.
- `trend_observations`: Factual week-over-week trend observations across privacy-safe weeks.
- `recommended_actions`: Supportive, constructive, human-reviewed advisory actions.
- `confidence`: Bounded numeric confidence score (0.0 to 1.0).
- `limitations`: Explicit disclosures regarding participation rates and sample limitations.

### Responsible AI Controls
- **Medical/Clinical Diagnosis Prohibition**: Strictly prohibits diagnosing mental health conditions, clinical depression, anxiety disorders, burnout, or any medical condition.
- **Safe Negated Guidance Accepted**: Statements advising against diagnosis or punitive action (e.g., *"Do not diagnose individual employees"*, *"Avoid punitive action"*) are permitted.
- **No Ranking or Punishment**: Prohibits ranking employees, assigning blame, or recommending demotion, discipline, or termination.
- **Advisory & Supportive**: Focuses entirely on organizational workload distribution, peer support, and constructive manager check-ins.

### Offline Testing Strategy
Comprehensive test suite (`backend/tests/agents/test_wellbeing_agent.py`) verifies all features offline without network calls or external credentials:
- Role/team MongoDB query filtering and pre-query authorization.
- k-Anonymity threshold boundary tests (fewer-than-3 vs exact-3 responses).
- PII and confidential comment exclusion.
- Deterministic metric calculations, UTC boundary handling, and week-over-week trends.
- Structured output validation, single-call gateway verification, and sanitized error handling.
- Responsible AI guardrail enforcement and Well-being → Task Assignment dependency rejection.
- Audit privacy verification and zero database mutation.

---

---

## 11. Task Assignment Specialist Agent

The system implements the **Task Assignment Specialist Agent** natively on top of the shared custom Python multi-agent runtime.

### Purpose & Scope
The Task Assignment Agent assists authorized Managers by providing explainable, objective, and human-reviewable task assignment recommendations based strictly on verified task requirements, employee profile skills, and active workload capacity. It is strictly read-only and advisory:
- Identifies eligible team members with relevant skills for a specific task.
- Evaluates current active workloads to identify available capacity and distribution balance.
- Highlights delivery risks and missing skill coverage.
- Formulates recommended check-in questions for managers to confirm candidate availability and interest.

### Manager-Only Advisory Boundary & Human-in-the-Loop Decision
- **Strictly Advisory**: All recommendations are advisory. The agent never assigns or reassigns tasks automatically, never calls database mutation methods, and never issues automatic mutation commands.
- **Human-in-the-Loop Final Decision**: An authorized human Manager must review the recommendations and perform any final task assignment using the existing Task Management workflow (`PATCH /tasks/{task_id}/assignment`).
- **Role Authorization**:
  - **Manager**: Authorized to request task assignment recommendations strictly for tasks and employees within teams they manage (`managed_team_ids`).
  - **Employee**: Strictly forbidden from requesting assignment recommendations for others (`EMPLOYEE_TASK_ASSIGNMENT_FORBIDDEN`).
  - **Admin**: Disabled by default policy (`ADMIN_TASK_ASSIGNMENT_DISABLED`).
  - **Unassigned / Cross-Team**: Unauthorized managers or cross-team requests are rejected immediately before candidate data is fetched.

### Authorized Data Sources & Strict Projections
The agent strictly queries only authorized collections using minimal field projections:
- **`tasks`**: `_id`, `title`, `description`, `required_skills`, `team_id`, `assigned_to`, `status`, `priority`, `due_date`, `blockers`.
- **`employee_profiles`**: `user_id`, `skills`, `job_title`, `availability_status`, `weekly_capacity_hours`.
- **`users`**: `_id`, `name`, `role`, `team_id`, `is_active`.
- **`teams`**: `_id`, `name`, `manager_id`.
- **Exclusions**: Never queries `weekly_pulse_responses`, collaboration message bodies, authentication credentials, password hashes, sessions, tokens, or confidential comments.

### Deterministic Python Calculations
All factual evaluations, intersections, and capacities are computed deterministically in Python before invoking the LLM:
- **Skill Normalization & Intersection**: Strips whitespace, case-folds canonical skills, computes the exact intersection with task `required_skills`, determines missing skills, and computes the mathematically bounded `skill_coverage_ratio`.
- **Active Workload Capacity**: Tallies active non-completed tasks (`assigned_to == candidate_id`, excluding `completed` and `archived`), counts in-progress and blocked tasks, urgent/high-priority tasks, due-soon tasks (within 3 UTC days), and overdue tasks (`due_date < now_utc`).
- **Deterministic Suitability Score**: Computed via documented formula:
  $$\text{suitability} = \min\left(1.0, \max\left(0.0, 0.50 \times \text{skill\_coverage} + 0.20 \times \text{avail\_factor} + 0.15 \times \text{workload\_factor} + 0.15 \times \text{deadline\_factor} - \text{penalties}\right)\right)$$
  Missing data deterministically lowers confidence rather than fabricating evidence. Ties are broken deterministically by Candidate ID.
- **Timezone Awareness**: All date comparisons strictly use timezone-aware UTC (`datetime.now(timezone.utc)`).

### LLM Responsibility & Prompt-Injection Neutralization
- **Single Structured Invocation**: The agent calls `LLMGateway.generate_structured(...)` exactly once per execution with `TaskAssignmentFindingOutput`.
- **Advisory Role**: The LLM summarizes candidate trade-offs, formulates manager review questions, and explains limitations. It never invents candidates, overrides eligibility, or executes assignments.
- **Untrusted Evidence Boundary**: All task descriptions and profile details are wrapped in JSON evidence blocks delimited by `=== BEGIN_UNTRUSTED_EVIDENCE_JSON ===`. The system prompt instructs the model to treat all evidence as untrusted data, neutralizing prompt-injection attacks.

### Strict Well-being / Weekly Pulse Isolation
- **Prohibited Data & Dependencies**: The Task Assignment Agent strictly isolates itself from all Well-being and Weekly Pulse survey data.
- **Multi-Layer Enforcement**:
  1. *Dependency Flow Allowlist*: Cross-agent findings from `wellbeing` to `task_assigning` are strictly rejected by `validate_dependency_flow`.
  2. *Evidence Source Allowlist*: `AgentDefinition.allowed_evidence_sources` allows only `task`, `employee_profile`, and `agent_finding` (excluding `pulse_survey`).
  3. *Tool-Level Protection*: The evidence tool only accesses `tasks`, `employee_profiles`, `users`, and `teams`.
  4. *Responsible-AI Guardrails*: Reject any output attempting to reference pulse surveys, mental health, burnout, or medical details.

### Fair Recommendation Policy & Responsible AI Controls
- **Task-Related Factors Only**: Recommendations are strictly based on required skill coverage, active workload, deadline risks, and team eligibility.
- **Prohibited Attributes**: Protected characteristics (age, gender, ethnicity, religion, disability, marital status), medical/mental health, and subjective personal quality scores are strictly forbidden.
- **No General Employee Ranking or Punishment**: The agent evaluates task-specific candidate suitability only; general performance rankings or punitive/demotion recommendations are blocked.
- **Context-Aware Negation Handling**: Safe protective statements (e.g., *"Do not use Well-being information for task assignment"*, *"Manager must make the final decision"*) are permitted.

### Information Retrieval (BM25) Clarification
- The system includes a BM25 Information Retrieval service for full-text search across documents. In the current phase, the Task Assignment Agent computes exact normalized skill intersections and workload metrics directly from MongoDB collections and does not invoke the BM25 retrieval service unless explicitly configured.

### Current Limitations
- **No Direct Agent REST Endpoint / UI Yet**: In this development phase, the Task Assignment Agent is executed via the Python multi-agent runtime (`runtime.execute_agent` / `execute_task_assignment_agent`). REST API endpoints and Manager UI integration will be introduced in subsequent phases.

### Offline Testing Strategy
Comprehensive test suite (`backend/tests/agents/test_task_assignment_agent.py`) verifies all features offline without network calls or external credentials:
- Canonical agent name (`task_assigning`) and intent (`task_assignment_recommendation`).
- Role authorization (Manager permitted for managed teams; Employee and Admin rejected).
- MongoDB collection access, field projections, and zero database mutations.
- ObjectId and string ID compatibility.
- Deterministic skill matching, workload penalties, and UTC date arithmetic.
- Well-being and Weekly Pulse dependency blocking and Responsible AI leakage guardrails.
- Allowed Productivity and Collaboration specialist dependencies.
- Privacy-safe audit logging.

---

## 12. Google Gemini LLM Provider Integration

The custom multi-agent runtime integrates with Google Gemini via the official Google Gen AI SDK (`google-genai`).

### Architecture & Production Gateway
- **`GeminiLLMGateway`**: Implements the `LLMGateway` interface (`generate_structured`), providing asynchronous structured JSON responses mapped to strict Pydantic schemas.
- **Fail-Closed Provider Factory**: `create_production_llm_gateway()` strictly fails closed. If `LLM_PROVIDER=gemini` is configured without `GEMINI_API_KEY` or `GEMINI_MODEL`, a configuration error is raised. Production application code never silently falls back to `FakeLLMGateway`.
- **Test Doubles**: `FakeLLMGateway` is available strictly as an explicitly injected test double for offline automated test suites.
- **Error Mapping & Resilience**: Google GenAI errors are mapped to typed repository exceptions (`LLMAuthenticationError`, `LLMRequestError`, `LLMUnavailableError`, `LLMTimeoutError`, `LLMResponseValidationError`). Retries with exponential backoff are bounded to transient errors (HTTP 429 rate limits, 5xx server errors, network timeouts) and never applied to authentication or schema validation failures.
- **Privacy & Safety**: Prompts and raw responses are never logged. API keys are strictly redacted from `repr()`, exceptions, audit events, and log streams.

### Manual Synthetic Smoke Test
A standalone manual smoke test script verifies live Gemini API connectivity across all four specialist agent Pydantic response schemas using strictly synthetic data:
```powershell
python backend/scripts/smoke_test_gemini.py --agent productivity
python backend/scripts/smoke_test_gemini.py --agent collaboration
python backend/scripts/smoke_test_gemini.py --agent wellbeing
python backend/scripts/smoke_test_gemini.py --agent task_assignment
```

> [!IMPORTANT]
> **Synthetic Data & Privacy Policy:**
> - The manual smoke test uses purely fictional, synthetic prompt data.
> - Real employee names, task records, collaboration messages, weekly pulse survey responses, or database credentials must NEVER be transmitted during smoke testing.
> - Configured model: `gemini-3.1-flash-lite` (Flash-class stable model for low-cost structured outputs).

---

## 13. Coordinator / Orchestrator Agent

The system implements the **Central Coordinator / Orchestrator Agent** (`AgentCoordinator`) on top of the custom Python multi-agent runtime.

### Purpose & Architecture
The Coordinator acts as the single orchestration interface for multi-agent workflows, managing intent routing, concurrency, dependency validation, Responsible AI guardrails, bounded resilience, and multi-specialist synthesis:
- **Declarative Intent Routing**: Automatically routes supported workplace inquiries (`AgentIntent`) to appropriate specialist agents (`Productivity`, `Collaboration`, `Well-being`, `Task Assignment`).
- **Concurrent Execution**: Executes independent specialist agents concurrently using bounded concurrency controls (`asyncio.gather`), optimizing response latency for multi-domain inquiries.
- **Dependency Ordering & Provenance**: Validates prerequisite findings before passing them to downstream dependent agents, ensuring correlation ID matching, provenance integrity, and Responsible AI compliance.
- **Strict Well-being Isolation**: Strictly enforces complete isolation of Well-being pulse data from Task Assignment recommendations across all routing, dependency, and synthesis layers.
- **Partial Failure Resilience**: When one independent specialist fails during multi-agent orchestration, the coordinator returns partial safe results (`status="partial"`) alongside sanitized error codes, preventing total pipeline collapse.
- **Executive Synthesis & Fallback**: Consolidates multi-agent findings into a cohesive, balanced executive analysis (`StructuredAgentFindingOutput`), with deterministic fallback if LLM synthesis is unavailable.
- **Advisory Only**: Operates strictly read-only with zero database mutations or automatic task reassignments.
- **Privacy-Safe Audit Logging**: Records structured audit events without ever leaking prompt bodies, raw employee records, pulse survey comments, PII, or credentials.

### Intent Routing & Specialist Matrix
| Intent (`AgentIntent`) | Target Specialist(s) | Execution Mode | Synthesis |
| :--- | :--- | :--- | :--- |
| `productivity_analysis` | `productivity` | Single Direct | Direct Specialist Finding |
| `collaboration_analysis` | `collaboration` | Single Direct | Direct Specialist Finding |
| `wellbeing_analysis` | `wellbeing` | Single Direct | Direct Specialist Finding |
| `task_assignment_recommendation` | `task_assigning` | Single / Prerequisite Flow | Direct Specialist Finding (Well-being strictly blocked) |
| `task_delay_analysis` | `productivity`, `collaboration` | Concurrent Multi-Agent | Synthesized Executive Finding + Specialist Findings |
| `team_workload_analysis` | `productivity`, `wellbeing` | Concurrent Multi-Agent | Synthesized Executive Finding + Specialist Findings |
| `general_workforce_question` | `productivity`, `collaboration`, `wellbeing` | Concurrent Multi-Agent | Synthesized Executive Finding + Specialist Findings |

### Usage Example
```python
from backend.app.modules.agents import (
    create_production_coordinator,
    CoordinatorExecutionRequest,
    AuthenticatedPrincipal,
)

# Initialize production coordinator with all registered specialists
coordinator = create_production_coordinator(database=db)

# Execute an orchestrated inquiry
request = CoordinatorExecutionRequest(
    correlation_id=str(uuid.uuid4()),
    intent="task_delay_analysis",
    authenticated_principal=current_manager_principal,
    question="What factors are contributing to sprint delays?",
    target_team_id="team-alpha",
)
result = await coordinator.orchestrate(request)

# Process findings
print(f"Status: {result.status}")
if result.synthesized_finding:
    print(f"Executive Summary: {result.synthesized_finding.summary}")
for finding in result.findings:
    print(f"- [{finding.agent.upper()}]: {finding.summary}")
```

---

## 14. Current Architecture & Session Limitations

1. **In-Memory Session Storage:** JWT access tokens are stored strictly in-memory (React state) to prevent browser storage XSS exposure. Page reloads currently require signing in again.
2. **Token Lifetime & Refresh:** Access tokens expire in 15 minutes. Refresh tokens and server-side token revocation blocklists are not yet implemented.
3. **Dynamic Role Verification:** The backend resolves the token subject against the live database record on each request, ensuring role modifications or deactivations take effect immediately.
4. **Role Scope & Privacy Thresholding:** Weekly pulse surveys provide employee self-submission, manager team aggregates with a strict minimum response threshold of 3 for anonymity, and admin privacy-safe audit metadata. No individual well-being scores, mood/stress classifications, or diagnostic labels are computed or exposed.
5. **Multi-Agent Runtime & Specialists:** The Central Coordinator Agent, Productivity Specialist Agent, Collaboration Specialist Agent, Well-being Specialist Agent, and Task Assignment Specialist Agent are fully implemented, tested, and integrated with the production LLM gateway.
