# Coordinator correction verification

Verification date: 2026-09-26. All results below were obtained from this working tree. No prior report or prior test total was used as evidence.

## Baseline and final results

| Check | Baseline | Final |
|---|---|---|
| Backend | 715 tests collected after essential import repair; collection alone was not a passing suite | 756 passed, 4 warnings, 49.45 seconds |
| Frontend | 107 passed in 5 files | 111 passed in 6 files, no warnings, 13.89 seconds |
| Final focused backend correction/assignment/coordinator group | n/a | 170 passed, 2 dependency deprecation warnings |
| Final focused frontend agent group | n/a | 42 passed in 2 files, no warnings |
| Production build | not used as a baseline | passed; 102 modules; JS 434.11 kB (103.06 kB gzip); CSS 107.81 kB (27.71 kB gzip); no warnings |
| pip check | n/a | No broken requirements found |
| git diff --check | n/a | passed, no final warnings; whitespace/conflict-marker hygiene |

The increase is 41 backend cases from 25 genuinely new functions (parameterization accounts for the difference), and 4 genuinely new frontend cases. The pre-existing 25 required names were retained exactly once and are not counted as new. The inherited regression audit file still has 29 cases.

## Import and collection repairs

`confidence_scorer.py` needed imports for `EvidenceReference` and `Any`. After those collection blockers were repaired, the backend collected 715 tests without further collection errors. The final full run collected and passed all 756 cases.

## Production correction evidence

| Requirement | Implemented behavior and tests |
|---|---|
| Server-owned context matrix | Every analysis requires an explicit team. Task and lookback relevance follow the requested matrix. Classifier guidance, API capability metadata, frontend wording, and README agree. Missing-team cases exercise all seven intents before any evidence read; real API clarifications return null confidence. |
| Selected task/team evidence | Task ownership is validated against the selected authorized team. Productivity contains only the selected task; Collaboration contains only linked blockers and canonical task-linked messages. Task Delay prompts are checked for both specialists. Request-selected team and lookback values drive blocker retrieval. |
| Fail-closed, deterministic non-disclosure | Unauthorized team selection is rejected first. For an authorized team, missing, inaccessible, and cross-team tasks use the same safe 404 contract: Target task not found. Scope-verification database failures stop specialist execution and map to 503. |
| Public identifier safety | Runtime and API sanitize summaries, actions, limitations, safe errors, nested candidate strings/reasons/workload, and task titles, including opaque conversation IDs. Frontend display sanitization covers malformed public strings, attributes, clipboard and console. The structured correlation_id is preserved; clipboard copies sanitized summary prose. |
| Specialist claim boundaries | Adversarial Well-being and Collaboration output is tested in the real runtime. Fewer than two qualifying privacy-safe weeks produce single-week snapshot wording and remove stability/change claims. Collaboration removes unsupported task-management, delivery, productivity and Well-being claims before synthesis. Original Responsible AI checks remain enforced. |
| Deterministic confidence | Per-execution trusted metrics supply domain confidence. Real individual, Task Delay, Team Workload and General Workforce paths are compared where applicable. Provider scores of 0.01 and 0.99 cannot change specialist confidence. Saturated Collaboration remains 1.0 across routes. Missing or invalid capacity is explicitly unverified and lowers Task Assignment confidence. |
| Grounding | The production runtime calls validate_task_assignment_grounding against eligible deterministic candidates; an invented candidate is rejected. Deterministic candidate reasons/workload details are rendered. Suitability is separate from evidence confidence. |
| Employee restriction | API role dependencies reject Employee requests before coordinator creation/configuration, metadata, or evidence. Direct workspace entry performs no capability/team/task requests. Existing Sidebar, MobileNavigation and Dashboard denial tests pass. Manager and existing admin aggregate access pass real API checks. No Executive role or Employee self-insights feature was added. |
| Prompt refusal and logging | Public injection refusal occurs before coordinator initialization and has confidence=null. Read spies prove no evidence queries. Classification exceptions cannot log user-question text; exception logs use types instead of raw messages. |
| Caller cancellation | The shielded dispatch is cancelled and awaited; child tasks clean up and are awaited. Assertions cover the dispatch/child tasks and absence of any additional live asyncio tasks after cancellation. |

## Production files edited in this correction pass

Backend behavior edits:

- `backend/app/modules/agents/confidence_scorer.py`
- `backend/app/modules/agents/collaboration_agent.py`
- `backend/app/modules/agents/coordinator.py`
- `backend/app/modules/agents/productivity.py`
- `backend/app/modules/agents/router.py`
- `backend/app/modules/agents/runtime.py`
- `backend/app/modules/agents/security_policy.py`
- `backend/app/modules/agents/task_assignment.py`
- `backend/app/modules/agents/wellbeing.py`

Frontend behavior edits:

- `frontend/src/features/agents/agentsApi.js`
- `frontend/src/features/agents/publicProse.js`
- `frontend/src/features/agents/components/AgentWorkspace.jsx`
- `frontend/src/features/agents/components/AgentResultSummary.jsx`
- `frontend/src/features/agents/components/TaskAssignmentDetailsView.jsx`
- `frontend/src/features/agents/components/SpecialistFindingCard.jsx`
- `frontend/src/features/agents/components/AgentCapabilitiesPanel.jsx`
- `frontend/src/features/agents/components/AgentErrorPanel.jsx`
- `frontend/src/features/agents/components/AgentRequestForm.jsx`

Documentation: `README.md` (context matrix, scope, roles, public API fields, lookback bounds, assignment confidence formula, evidence limitations, and safe summary copy behavior). The environment example was read and its existing changes retained. Prior protocol, gateway, navigation, Dashboard, tests and other working-tree changes remain present; the final status below includes that prior work.

## Existing regression tests strengthened

In `backend/tests/agents/test_coordinator_regression_audit.py`:

- `test_all_clarification_responses_have_null_confidence`
- `test_prompt_injection_refusal_has_null_confidence`
- `test_clarification_performs_zero_evidence_collection_queries`
- `test_prompt_injection_performs_zero_evidence_collection_queries`
- `test_public_prose_removes_team_task_user_ids_and_emails`
- `test_single_wellbeing_week_cannot_claim_stability`
- `test_collaboration_cannot_claim_task_management_effectiveness`
- `test_collaboration_confidence_identical_across_workflows`
- `test_current_assignee_uses_retention_reassignment_wording`
- `test_available_candidate_with_overdue_work_requires_capacity_review`
- `test_task_scoped_task_delay_filters_both_specialists`
- `test_wellbeing_rejects_target_task`
- `test_general_workforce_rejects_target_task`
- `test_team_workload_rejects_target_task`
- `test_employee_rejection_occurs_before_evidence_queries`
- `test_manager_access_remains_permitted`

These replace helper-only, hardcoded-text, metadata-only, or document-count assertions with real coordinator/runtime/API behavior, read spies, actual prompt contents, candidate output checks, and public confidence checks. Other existing routing and evidence-tool regressions were retained.

Additional existing fixtures/assertions corrected to agree with the approved contracts:

`backend/tests/agents/test_agent_api.py`:

- `test_execute_forbids_extra_fields`
- `test_execute_forbids_client_selected_intent`
- `test_execute_forbids_injected_role_or_dependencies`
- `test_execute_invalid_uuid_correlation_id_rejected`
- `test_execute_empty_question_rejected`
- `test_execute_invalid_weeks_lookback_rejected`
- `test_missing_llm_configuration_fails_closed_with_503`

`backend/tests/agents/test_agent_runtime.py`:

- `test_normal_execution_calls_llm_gateway_once`
- `test_execute_many_preserves_order_and_respects_concurrency`
- `test_fake_agent_runtime_deterministic_success`
- `test_execute_many_provider_failure_cancels_slow_peer_in_fail_fast_mode`

`backend/tests/agents/test_coordinator_agent.py`:

- `test_prompt_injection_cannot_bypass_deterministic_routing`
- `test_employee_task_assignment_denied_before_candidate_lookup`
- `test_confidence_never_exceeds_deterministic_bound`
- `test_task_delay_analysis_live_shape_and_fallback_resilience`
- `test_coordinator_intent_classification_all_canonical_intents`
- `test_route_task_assignment_recommendation`
- `test_wellbeing_isolated_from_task_assigning_under_any_flow`

`backend/tests/agents/test_productivity_agent.py`:

- `test_productivity_agent_full_end_to_end`

`backend/tests/agents/test_task_assignment_agent.py`:

- `test_full_runtime_execution_manager_success`
- `test_pulse_survey_secret_markers_never_leak_in_task_assignment`
- `test_task_assignment_confidence_verified_eligible_candidate_calculation_unchanged`

`backend/tests/agents/test_wellbeing_agent.py`:

- `test_team_workload_coordinator_confidence_uses_weakest_specialist`

Request schema tests now use Managers so they test 422 validation independently of the earlier Employee 403 gate. The missing-provider test omits the forbidden client intent. Runtime confidence assertions now use trusted evidence scores rather than LLM scores, and Well-being results require snapshot wording. Assignment routing fixtures contain real authorized target records instead of treating an unavailable database as verified scope. Grounding fixtures match actual candidate identity/skills. The canonical workload example contains both operational and Well-being semantics. Existing test names were retained.

Frontend existing cases updated in `AgentWorkspace.test.jsx`:

- `displays detected intent label, routing confidence, and consulted specialists only after execution` (safe summary copy control).
- `Malformed API response identifiers/emails/internal error codes are suppressed from visible text, title, ARIA, clipboard, and console` (sensitive strings now occupy rendered fields; clipboard assertion checks safe summary; asynchronous act covers copy state).

## Genuinely new backend functions

File: `backend/tests/agents/test_coordinator_corrections.py`.

- `test_every_known_intent_without_team_stops_before_evidence`
- `test_real_api_clarification_has_null_confidence_and_zero_reads`
- `test_selected_team_blockers_exclude_other_managed_team`
- `test_task_delay_llm_prompts_contain_only_selected_task_evidence`
- `test_task_scope_database_failure_stops_specialists`
- `test_caller_cancellation_awaits_dispatch_and_children`
- `test_employee_denied_before_coordinator_creation`
- `test_public_injection_refusal_before_initialization_has_null_confidence`
- `test_specialist_confidence_matches_across_production_workflows`
- `test_provider_confidence_cannot_override_runtime_evidence_score`
- `test_runtime_wellbeing_removes_unsupported_longitudinal_claims`
- `test_runtime_collaboration_removes_other_domain_success_claims`
- `test_assignment_grounding_validator_runs_and_rejects_invented_candidate`
- `test_assignment_missing_capacity_reduces_runtime_confidence`
- `test_unlinked_task_messages_report_unavailable_without_llm_disclosure`
- `test_blocker_lookback_uses_request_window_in_selected_team`
- `test_task_non_disclosure_and_authorization_precedence`
- `test_public_assignment_nested_prose_is_sanitized_in_real_api`
- `test_runtime_sanitizes_specialist_summary_actions_and_limitations`
- `test_saturated_collaboration_confidence_preserved_across_routes`
- `test_misclassified_workload_without_both_domains_cannot_dispatch_wellbeing`
- `test_admin_real_api_retains_team_scoped_aggregate_access`
- `test_classifier_errors_cannot_log_user_question`
- `test_invalid_capacity_is_unverified_in_production_score_and_workload`
- `test_opaque_conversation_id_removed_from_runtime_and_public_prose`

## Genuinely new frontend cases

File: `frontend/src/features/agents/__tests__/AgentPublicSafety.test.jsx`.

- `contaminated display fields cannot leak to text attributes clipboard or console`
- `employee direct workspace entry performs zero capability or resource requests`
- `team and task option display strings are sanitized`
- ` `
- `malformed error messages are sanitized before display`

## Verification commands

Run from repository root unless noted:

```text
backend/.venv/Scripts/python.exe -B -m pytest backend/tests --collect-only -q -p no:cacheprovider
backend/.venv/Scripts/python.exe -B -m pytest backend/tests/agents/test_coordinator_corrections.py backend/tests/agents/test_task_assignment_agent.py backend/tests/agents/test_coordinator_agent.py -q -p no:cacheprovider --tb=short
backend/.venv/Scripts/python.exe -B -m pytest backend/tests -q -p no:cacheprovider --tb=short
backend/.venv/Scripts/python.exe -B -m pip check
git diff --check
git status --short
```

From `frontend/`:

```text
node node_modules/vitest/vitest.mjs run src/features/agents/__tests__ --no-cache
node node_modules/vitest/vitest.mjs run --no-cache
node node_modules/vite/bin/vite.js build
```

Untracked implementation/test files were additionally checked for trailing whitespace and conflict markers; no issues were found. This was hygiene verification, not a syntax check or a secret scan.

## Warnings and sandbox execution

Final backend warnings:

- Starlette TestClient deprecates httpx (dependency warning from fastapi/testclient.py).
- Starlette TestClient uses deprecated anyio.abc.BlockingPortal alias (dependency warning).
- Information Retrieval uses deprecated HTTP_422_UNPROCESSABLE_ENTITY; Starlette recommends HTTP_422_UNPROCESSABLE_CONTENT.
- A Pulse Survey validation path uses the same deprecated HTTP 422 alias, reported through FastAPI routing.

No final frontend or build warnings. The initial frontend act warning was resolved by awaiting the clipboard state update. Intermediate Git CRLF-to-LF warnings were resolved by restoring LF line endings without changing source text; the final diff hygiene check emitted no warnings.

Sandboxed Node runs failed before startup with EPERM while resolving C:\Users\Pamod Pannigala. Focused/full frontend tests and production builds ran with explicit one-time outside-sandbox approvals. No permanent or blanket approval prefix was requested. No dependencies were installed or upgraded.

## Secret scanning and remaining limitations

No repository secret-scanning mechanism was found by searching tracked/hidden source and configuration for scanner names/commands and scanner configuration filenames. `backend/scripts/check_security.py` tests password hashing; it is not a secret scanner. No automated secret scan is claimed.

## Follow-up: selected-task Collaboration wording correction (2026-09-26)

This section records the narrow correction prompted by the live manual test. Earlier full-backend/frontend/build results above are historical; those checks were not rerun for this follow-up. The earlier tests did not catch the team-aggregation wording defect.

Inspection found that both database queries and the in-memory filters already selected the authorized team and exact task. Team-wide blocker/message records were not entering that task payload through these collectors. However, the filtered blocker reference was titled `Aggregated Task Blocker Metrics`, its snippet included `Teams:`, the system prompt requested aggregated metrics, and the output sanitizer failed to remove the live wording. Adversarial API tests reproduced the leak into specialist and top-level summaries for both Collaboration and Task Delay before the production fix.

The correction labels the reference `Selected Task Blocker Metrics`, omits team counts, and renders only selected-task active/stale/resolved counts and resolution times. Selected-task blocker snippets now exclude historical resolutions outside the request window, matching the metric calculation. Active unresolved blockers remain relevant even when created before that window. Runtime task-scoped Collaboration summaries, limitations, and actions are constructed from the trusted task-only metrics rather than free-form LLM prose. The existing sanitization and Responsible AI checks still execute. Task Delay uses this same runtime branch. The unavailable task-linked-message limitation remains explicit when no trustworthy linked records were retrieved.

Confidence formula and production scoring weights were retained. With valid timestamps, zero linked messages plus one or more linked blockers independently produce 0.72 + 0.05 = 0.77. One to three linked messages with blockers also produce 0.77. Thus team/task equality can be legitimate without shared evidence. Tests prove distinct scoped message samples independently receive that score, unrelated/unlinked messages and invalid timestamps cannot affect it, empty selected-task evidence scores 0.30 despite abundant team evidence, and adding selected-task linked messages changes the score. The exact records from the live deployment were not available here; this does not assert which confidence inputs that particular live request retrieved.

Files changed in this follow-up only:

- `backend/app/modules/agents/collaboration_agent.py`
- `backend/app/modules/agents/runtime.py`
- `backend/tests/agents/test_coordinator_corrections.py`
- `CORRECTION_VERIFICATION.md` (this appended report)

Six genuinely new test functions, producing eleven cases; no existing tests were removed, renamed, or weakened:

- `test_task_collaboration_prompt_metrics_exclude_same_team_other_tasks` (Collaboration and Task Delay)
- `test_task_collaboration_public_api_rejects_team_aggregate_claims` (both routes, with and without selected-task blockers)
- `test_task_collaboration_confidence_ignores_unlinked_and_other_task_messages` (both routes)
- `test_task_collaboration_empty_metrics_do_not_count_summary_as_blocker`
- `test_team_and_task_collaboration_equal_confidence_uses_independent_scoped_inputs`
- `test_task_collaboration_linked_message_volume_controls_confidence`

Fresh verification:

- The focused three-file group collected 107 cases before edits; the final run passed 118 cases, with 2 dependency deprecation warnings, in 8.88 seconds.
- Before the production correction, the eleven new cases produced 6 expected failures and 5 passes, reproducing the unsafe prompt/public wording.
- After the correction, the smallest new regression group passed 11 cases (41 deselected), with 2 warnings, in 1.53 seconds.
- Backend agent suite: **594 passed**, 2 warnings, 21.68 seconds. The eleven new cases account for the increase from 583 existing agent cases.
- Commands used `backend/.venv/Scripts/python.exe -B -m pytest` with `-p no:cacheprovider --tb=short`; groups were `backend/tests/agents/test_coordinator_corrections.py` with `-k 'task_collaboration or team_and_task_collaboration'`, the correction/Collaboration/regression-audit three-file group, and `backend/tests/agents`.
- Warning causes: Starlette TestClient's deprecated use of `httpx`, and its deprecated `anyio.abc.BlockingPortal` alias. Pytest reported only those two dependency warnings in the passing runs.
- An initial collection command referenced a nonexistent root `.venv` interpreter and did not run tests; it was corrected to the backend interpreter. No code import/collection failure occurred.
- `git diff --check` passed (whitespace/conflict-marker hygiene). Changed untracked test/report files were additionally checked for trailing whitespace and conflict markers.

All commands in this follow-up ran inside the sandbox. No prohibited Git operations were performed. Existing unrelated changes were preserved. The final `git status --short` is identical to the status recorded above: these follow-up edits modify paths already modified or untracked at the start of the follow-up. No live provider or deployment was exercised; verification used real production collectors, runtime, coordinator, and public API with the repository's fake database and fake LLM gateway.

- Verification used the repository suites with fake database/provider fixtures; no separate live MongoDB or external LLM smoke test was run.
- Legacy messages without canonical task_id linkage are excluded from selected-task analysis, so task-linked collaboration-message evidence may be unavailable.
- Existing evidence retrieval caps remain. Confidence describes the collected scoped evidence; it does not guarantee a complete population census.
- Four deprecation warnings remain outside the corrected behavior; dependencies and unrelated modules were not changed to suppress them.

## Git operation restrictions

Zero prohibited Git operations were performed: no commit, push, branch creation/switch, merge, rebase, reset, restore, checkout, stash, clean, or PR creation. No broad directories were deleted. Existing user and unrelated changes remain in the working tree.

## Exact final git status --short

```text
 M README.md
 M backend/.env.example
 M backend/app/modules/agents/__init__.py
 M backend/app/modules/agents/collaboration_agent.py
 M backend/app/modules/agents/coordinator.py
 M backend/app/modules/agents/llm_gateway.py
 M backend/app/modules/agents/productivity.py
 M backend/app/modules/agents/protocol.py
 M backend/app/modules/agents/router.py
 M backend/app/modules/agents/runtime.py
 M backend/app/modules/agents/security_policy.py
 M backend/app/modules/agents/task_assignment.py
 M backend/app/modules/agents/wellbeing.py
 M backend/tests/agents/test_agent_api.py
 M backend/tests/agents/test_agent_runtime.py
 M backend/tests/agents/test_agent_security_policy.py
 M backend/tests/agents/test_collaboration_agent.py
 M backend/tests/agents/test_coordinator_agent.py
 M backend/tests/agents/test_productivity_agent.py
 M backend/tests/agents/test_task_assignment_agent.py
 M backend/tests/agents/test_wellbeing_agent.py
 M frontend/src/layouts/MobileNavigation.jsx
 M frontend/src/layouts/Sidebar.jsx
 M frontend/src/pages/Dashboard.jsx
?? CORRECTION_VERIFICATION.md
?? backend/app/modules/agents/confidence_scorer.py
?? backend/tests/agents/test_coordinator_corrections.py
?? backend/tests/agents/test_coordinator_regression_audit.py
?? frontend/src/features/agents/
```
