Task Assignment production failure correction — 26 September 2026

The failure was reproduced with the configured live MongoDB and provider through the actual production coordinator, runtime, evidence tool and grounding validator. The corrected production coordinator was then re-run against the same read-only evidence. HTTP API regressions used the real application/coordinator/runtime with controlled database/provider boundaries. No deployed HTTP API or browser verification is claimed.

**Verified root cause**

The selected task is `Mobile APP development`, status `todo`, priority `medium`, unassigned, with the mandatory skill `ReactNative`. Its team belongs to the active manager used to resolve the production principal. Three active team employees were evaluated. All three have recorded work profiles, 40 hours/week capacity and `available` status. Candidate identities below are anonymized diagnostic labels, in deterministic evaluation order.

| Candidate | Recorded skills | Active tasks | Overdue tasks | Required-skill coverage | Suitability |
|---|---|---:|---:|---:|---:|
| 1 | docker, Angular, Nodejs | 1 | 0 | 0% | 0.00 |
| 2 | PowerBI | 0 | 0 | 0% | 0.00 |
| 3 | Python, FastAPI, React | 1 | 1 | 0% | 0.00 |

None has `ReactNative`. React coverage is not ReactNative coverage. The deterministic eligible pool was therefore correctly empty. The real provider nevertheless placed all three ineligible evaluations in `TaskAssignmentFindingOutput.candidate_recommendations`, with empty matched skills, `ReactNative` missing, and candidate confidence 0.0.

The actual comparison in `validate_task_assignment_grounding` was:

```text
len(finding_output.candidate_recommendations) = 3
len(expected_matches) = 0
LLM returned 3 candidates, exceeding deterministic candidate pool (0)
```

This was a candidate-count/container mismatch, not absent task requirements, incomplete profiles, unverified capacity, current-assignee handling, singular/plural text, serialization, or inflated candidate confidence. The validator correctly rejected unsupported recommendations. The defect was in `AgentRuntime._execute_agent_pipeline`: it returned `OUTPUT_GROUNDING_ERROR` before publishing the already-computed valid deterministic evaluation and structured details.

The original system prompt did not explicitly tell the provider to return an empty recommendation list when no candidates qualify. The prompt now states that boundary. Correctness does not depend on provider compliance: adversarial production-path tests prove that the same invalid three-candidate response now falls back safely.

The coordinator already retained `detected_intent=task_assignment_recommendation`, routing confidence 0.95 and `consulted_specialists=[task_assigning]` in the reproduced failure. `execute_agent_workflow` reduced that result to an HTTP exception containing only a message. `AnalysisRoute.get_route_handler` then rebuilt a fresh response with default null routing fields. That HTTP mapping caused the observed loss of intent metadata.

**Changes in this pass**

| File | Functions or definitions changed | Result |
|---|---|---|
| `backend/app/modules/agents/task_assignment.py` | `DeterministicTaskAssignmentMetrics.to_summary_text`; new `to_manager_actions`; `TASK_ASSIGNMENT_SYSTEM_PROMPT` | No requirements or no eligible candidates explicitly means no supported recommendation. Advice follows the same gates as the cards. Prompt distinguishes rejected evaluations from eligible recommendations. |
| `backend/app/modules/agents/runtime.py` | `AgentRuntime._execute_agent_pipeline` | Grounding rejection records a safe audit classification and continues with deterministic summary, actions, confidence and cards. Provider schema-validation failure also preserves a successfully computed Task Assignment evaluation, through the same downstream sanitization/policy checks. |
| `backend/app/modules/agents/router.py` | New `AnalysisExecutionFailure.__init__`; `AnalysisRoute.get_route_handler` / nested `safe_handler`; `execute_agent_workflow` | Carries server-owned intent, routing, consulted-specialist and timestamp metadata through failed HTTP responses. Existing response schema, HTTP status mappings and compatibility `detail` field remain intact. |
| `backend/tests/agents/test_task_assignment_live_failure.py` | New API fixtures and twelve test functions below | Eighteen new regression cases, including the live evidence shape, actual validator instrumentation and controlled provider failures. |
| `backend/tests/agents/test_coordinator_corrections.py` | `test_assignment_grounding_validator_runs_and_rejects_invented_candidate` | Strengthened existing test: validator is still invoked, invented output remains excluded, and the verified candidate result now completes. Test was not renamed. |

Candidate eligibility, suitability weights, ordering, workload counting, database query projections/scope, authorization, deterministic confidence scorer, coordinator aggregation, privacy calculations, public schemas and frontend source were not changed. Provider candidate prose is never copied into deterministic public candidate cards. Internal validator reasons are neither returned nor logged; audit events retain only the safe classification.

Missing requirements or zero eligible candidates retain confidence 0.30 and `human_decision_required=true`. Complete evidence retains confidence 0.95. Suitability is separate: the complete React/FastAPI case remains 0.91, with one active overdue task. Incomplete capacity/profile evidence retains its existing evidence penalty; the regression fixture with zero verified capacity profiles and two of three recorded skill profiles yields 0.48 confidence and 0.59 suitability for its one skill-eligible candidate. Current-assignee testing proves retention of the assignee and workload counts without a ranking boost.

**Exact new test names**

All are in `backend/tests/agents/test_task_assignment_live_failure.py` and execute `/agents/execute` through the real coordinator/runtime/evidence tool. The observed production data shape uses synthetic identities; production identifiers are not embedded in automated tests.

1. `test_demonstrated_reactnative_task_returns_completed_no_eligible_result`
2. `test_grounding_mismatch_preserves_valid_deterministic_candidate_evidence` — five cases: `name`, `skills`, `confidence`, `ordering`, `count`.
3. `test_zero_required_skills_returns_conservative_completed_assignment` — three cases: empty list, null, malformed scalar.
4. `test_no_eligible_candidates_preserves_verified_missing_skills`
5. `test_incomplete_profile_and_capacity_evidence_retains_penalty`
6. `test_current_assignee_is_preserved_without_ranking_boost`
7. `test_conflicting_llm_candidate_prose_uses_deterministic_fallback`
8. `test_assignment_public_output_hides_internal_grounding_errors`
9. `test_post_routing_assignment_failure_preserves_intent_metadata`
10. `test_assignment_schema_mismatch_preserves_valid_deterministic_evidence`
11. `test_assignment_evidence_read_failure_preserves_routing_metadata`
12. `test_complete_working_assignment_evidence_and_ranking_are_unchanged`

The first sixteen cases were run before production edits: thirteen failed and three passed. The schema-mismatch test was then added and observed failing before its targeted correction. Tests record inputs and results from the real grounding validator rather than replacing its decision. Provider parsing and availability errors are injected only at the provider boundary. The database-failure test spies on the actual profile collection read and verifies no provider call occurs. No database counts are used as proof of read ordering.

**Fresh baseline and final verification**

The baseline contained 24 modified tracked files, plus existing untracked reports, agent modules/tests and frontend features. Fresh `git diff --stat` reported 6,722 insertions and 540 deletions; those totals included pre-existing user work. A SHA-256 manifest covered all 180 existing tracked/untracked nonignored files before edits.

| Check | Fresh baseline | Final result |
|---|---:|---:|
| Backend collection / full `pytest backend/tests -q` | 853 collected; 853 passed, 6 warnings | 871 passed, 6 warnings |
| Backend agent tests | 680 existing cases, included in the passing baseline full suite | 698 passed, 4 warnings, via `pytest backend/tests/agents -q` |
| New focused regression file | New in this pass | 18 passed, 2 warnings |
| Full frontend `npm test -- --reporter=dot` | 130 passed across 8 files | 130 passed across 8 files |
| Frontend production `npm run build` | Not separately built at baseline | Passed; 102 modules, 436.21 kB JavaScript / 103.63 kB gzip |
| Backend venv `python -m pip check` | Not separately run at baseline | `No broken requirements found.` |
| `git diff --check` | Recorded existing line-ending notice | Passed; no whitespace errors |

The complete backend agent suite includes specialist, coordinator/runtime/API, existing manual-correction and live-prose regressions. The full frontend suite includes all 61 Agent Workspace/presentation/safety cases. No frontend tests were added or removed.

The live re-run used the real configured provider and MongoDB. Authorization and deterministic evidence were unchanged. The provider now returned no recommendations; the real validator accepted the empty list. The production coordinator returned `completed`, detected Task Assignment, routing confidence 0.95, the Task Assignment specialist, evidence confidence 0.30, no errors and structured details. Forced invalid provider output remains covered by the passing controlled API regressions.

**Warnings and verification limits**

The full backend warnings are existing Starlette/httpx TestClient deprecation, the anyio BlockingPortal alias deprecation, and deprecated `HTTP_422_UNPROCESSABLE_ENTITY` usage in existing validation paths. The baseline had the same six warnings. Git reports the pre-existing README LF-to-CRLF notice. Frontend tests/build and dependency checking completed successfully.

The first sandboxed MongoDB attempt could not initialize the SRV client (`ConfigurationError`); the authorized read-only external run succeeded. No credential values, employee identities, raw prompts or private comments were printed by the live diagnosis. The temporary diagnostic script is outside the repository and performs no database writes.

No repository secret scanner is configured. Configuration/file searches found no gitleaks, trufflehog, detect-secrets, secretlint or pre-commit scanner configuration. `backend/scripts/check_security.py` tests password hashing and is not a secret scanner. No automated secret scan is claimed.

Provider unavailability/authentication/request errors, execution deadlines and failed evidence reads still produce safe failures; this pass recovers grounding and response-schema mismatches after successful deterministic evaluation. Post-routing failure metadata now survives those responses. Existing Responsible AI policy refusals remain in force. A task without supported mandatory skill coverage cannot receive a fabricated recommendation. No production data was edited to manufacture eligibility.

The live verification invoked the production coordinator directly with a principal derived from authoritative manager/team records. Authenticated HTTP response behavior was verified with controlled API tests. No deployed-server restart, live authenticated HTTP request or browser/UI run was performed. Load the updated backend modules before the manual API re-test. Existing structured UI behavior is covered by the unchanged passing frontend tests.

**Manual API re-test**

POST `/agents/execute` from the existing authorized manager session, using canonical JSON field names:

```json
{
  "question": "Recommend up to 3 eligible candidates for the selected task. Explain required-skill coverage, current workload, overdue risk, capacity limitations, and the manager decision required.",
  "target_task_id": "6aaff7c1d6e0aa036a1fb897",
  "target_team_id": "6aafb013baee0a127151a8ab"
}
```

With unchanged evidence, expect HTTP 200, `status=completed`, detected Task Assignment, routing confidence 0.95, `confidence=0.30`, three evaluated candidates, zero eligible candidates, no recommended candidates, and three rejected evaluations identifying missing `ReactNative`. `human_decision_required` must remain true. No grounding-validator error wording or internal code should appear. The structured UI should show the no-supported-recommendation result and rejected-candidate reasons.

The previously working task can be re-tested with the same question:

```json
{
  "question": "Recommend up to 3 eligible candidates for the selected task. Explain required-skill coverage, current workload, overdue risk, capacity limitations, and the manager decision required.",
  "target_task_id": "6aaff6d3d6e0aa036a1fb896",
  "target_team_id": "6aafb013baee0a127151a8ab"
}
```

With its previously complete evidence unchanged, expect evidence confidence 0.95, separate suitability 0.91 displayed as 91%, deterministic ranking and advisory manager approval. Its live HTTP/UI re-test was not performed in this pass; the identical evidence shape is exercised by the new complete-case API regression and existing passing frontend presentation tests.

**Working-tree preservation and Git restrictions**

All existing user changes were preserved. The final hash comparison found exactly four changed existing files: the three production files and the one strengthened test listed above. The other 176 baseline files were byte-identical, and no baseline file was missing. Only this report and the new regression test file were added to the repository. Existing reports and frontend source were untouched.

No commit, push, pull, branch creation/switch, merge, rebase, reset, restore, checkout, stash, Git cleanup or PR creation was performed. No database write, user-file deletion or cleanup of existing changes was performed. Git was used only for status, diff statistics, read-only file enumeration and whitespace validation.

The exact final `git status --short` follows, including all pre-existing changes:

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
?? LIVE_REGRESSION_CORRECTION_REPORT.md
?? POST_MANUAL_CORRECTION_REPORT.md
?? TASK_ASSIGNMENT_PRODUCTION_FAILURE_REPORT.md
?? backend/app/modules/agents/collaboration_reporting.py
?? backend/app/modules/agents/confidence_scorer.py
?? backend/app/modules/agents/grounded_reporting.py
?? backend/app/modules/agents/public_reporting.py
?? backend/tests/agents/test_coordinator_corrections.py
?? backend/tests/agents/test_coordinator_regression_audit.py
?? backend/tests/agents/test_live_regression_prose.py
?? backend/tests/agents/test_manual_corrections.py
?? backend/tests/agents/test_task_assignment_live_failure.py
?? frontend-baseline-results.json
?? frontend/src/features/agents/
```
