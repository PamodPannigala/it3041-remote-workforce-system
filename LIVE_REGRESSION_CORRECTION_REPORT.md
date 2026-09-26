# Live-regression reporting correction — 2026-09-26

This pass reproduces the user-reported live regressions through the actual local FastAPI endpoint, production coordinator, runtime, and evidence tools, with controlled database/provider boundaries. It corrects reporting and presentation only. No live MongoDB, external provider, or browser visual verification was performed here. The earlier reports remain unchanged as historical records; their passing tests did not cover the defects reproduced in this pass.

## Baseline and preservation

- Fresh baseline collection: **819 backend tests**. Fresh frontend baseline: **128 passed**, 8 files.
- Initial Git diff: **24 tracked files changed, 6,714 insertions, 540 deletions**. These totals include earlier user work; untracked files are omitted by Git diff statistics.
- Before production edits, the first 23 new API cases produced **20 failures and 3 passes**, reproducing punctuation loss, duplicate items, unsupported Collaboration conclusions, and inappropriate workflow wording.
- A SHA-256 baseline covered **176 existing files**. After the edits, **167 were byte-for-byte unchanged**, **9 were changed within this requested scope**, and **none were missing**. The unchanged files include Task Assignment, Well-being calculations, Productivity evidence retrieval, security/authorization, protocol/schema, router, previous reports, README, environment example, and navigation/Dashboard changes.
- Existing user changes were preserved. No commit, push, pull, branch creation/switching, merge, rebase, reset, restore, checkout, stash, clean, deletion, or PR creation was performed.

## Exact root causes

**Punctuation loss:** `confidence_scorer.py::sanitize_specialist_output::_sanitize_text` used `re.split(r"(?<=[.!?])\s+|[;\n]", text)` and joined the surviving parts with a space. Both the general domain filter and the Productivity filter discarded semicolon delimiters. The authoritative `grounded_reporting.py` templates used semicolons between independent clauses, so even valid deterministic strings became run-on sentences. This was an output transformation, not a database/provider punctuation defect. The corrected filters retain semicolons inside whole sentences; affected templates now explicitly produce complete sentences separated by full stops. A new production API test also verifies that a legitimate provider semicolon survives unchanged.

**Duplicate limitations:** `grounded_specialist_update` supplied the task-message availability limitation, then `sanitize_specialist_output` inserted another copy. One had already lost its semicolon; the newly appended copy had not passed through that transformation. Exact string equality could not recognize the malformed and intact variants as the same item. A shared canonical limitation now serves both sources, and final lists are deduplicated after all insertions, before finding/response construction.

**Duplicate pulse actions:** the deterministic Well-being workflow action collected pulse ratings and discussed manager priorities, while the single-week sanitizer independently appended a collection-for-comparison action. Both reached specialist and top-level lists because equality checks compared complete strings rather than the known equivalent deterministic actions. Both sources now use the same workflow-aware action. Only specifically identified equivalent deterministic variants are canonicalized; unrelated evidence gaps/actions are retained.

**Unsupported completion claim:** the exact public source was provider `CollaborationFindingOutput.summary`, copied into the runtime finding for standalone team Collaboration. That workflow was outside the composite trusted-template path. The existing domain expression rejected phrases such as “task is 20% complete” and delivery/productivity success but did not match “inquiries confirming the completion status of the development work”. A message status inquiry therefore survived as a completion implication in both the visible specialist and the one-specialist top-level result. Team Collaboration now combines existing verified blocker metrics with filtered, complete communication themes, and independently states that messages do not verify task completion. Inquiry wording is supported only by a question/status signal in already-authorized message evidence.

**API-access blocker recommendation:** the exact public source was provider `CollaborationFindingOutput.recommended_actions`, copied into the finding and passed through a sanitizer with no blocker-cause provenance check. `_format_task_blocker_snippet` already retrieves bounded blocker descriptions and optional resolution notes. That retrieval does **not** supply a validated sanitized note-to-output provenance contract. This pass therefore rejects specific blocker-cause prose and uses the verified count/status records with a generic documented-resolution review recommendation. The tests include both absence of an API-access note and an API-access note in the existing record; neither authorizes publishing the specific cause. Without the live provider trace, the particular live input that prompted the provider’s API-access inference remains **unverified**; no database-origin claim is made.

**Other source defects:** the General Workforce Collaboration template unconditionally described a “current delay”; its branch now follows the workflow. The Well-being template inserted a comma before “for”; that source comma was removed. The assignment UI rendered two explanatory count sentences in addition to the badges; only the redundant eligible/evaluated sentence was removed. During boundary testing, a long communication theme also exposed truncation at 3,000 characters; the new validator now budgets whole sentences and reserves the completion-evidence disclaimer instead of slicing finished prose.

## Files and functions changed in this pass

| File | Exact change |
| --- | --- |
| `backend/app/modules/agents/grounded_reporting.py` | `grounded_specialist_update`: complete estimate/date/time-log/lookback/scope sentences, workflow-appropriate Collaboration limitation/action, single-week heading, shared pulse action and message limitation. `grounded_synthesis`: canonical item deduplication after aggregation/additions. |
| `backend/app/modules/agents/confidence_scorer.py` | **Only** `sanitize_specialist_output` and its nested `_sanitize_text`: preserve semicolon punctuation, accept workflow context for reporting, use canonical message limitation/pulse action, deduplicate final lists. No confidence formula was edited. |
| `backend/app/modules/agents/public_reporting.py` (new) | `wellbeing_collection_action`, `_item_key`, `deduplicate_public_items`: full-word-sequence equality plus a small explicit map of equivalent deterministic reporting items. No fuzzy overlap or LLM deduplication. |
| `backend/app/modules/agents/collaboration_reporting.py` (new) | `_communication_sentences`, `validated_team_collaboration_update`: retain complete communication-domain themes; reject cross-domain and specific blocker-cause claims; build count/status facts from existing tool metrics; respect a whole-sentence output budget. |
| `backend/app/modules/agents/runtime.py` | `AgentRuntime._execute_agent_pipeline`: invoke the standalone team Collaboration reporting validator, pass workflow reporting context, and punctuate the existing standalone Productivity lookback limitation. No tool retrieval/authorization/confidence code was changed. |
| `backend/app/modules/agents/coordinator.py` | `AgentCoordinator._synthesize_findings` and `_deterministic_fallback_synthesis`: deduplicate limitations/actions before constructing final findings. Routing and contributor confidence remain unchanged. |
| `backend/app/modules/agents/collaboration_agent.py` | `COLLABORATION_SYSTEM_PROMPT`: explicitly forbid completion inference and unverified blocker causes. No evidence formatting/retrieval was changed. Deterministic validation enforces the boundary independently of the prompt. |
| `frontend/src/features/agents/components/TaskAssignmentDetailsView.jsx` | `TaskAssignmentDetailsView`: remove the redundant eligible/evaluated sentence; retain the badges and one evaluated-count sentence. Cards, scores, risks, clipboard behavior, and raw-summary suppression remain intact. |
| `backend/tests/agents/test_live_regression_prose.py` (new) | New API regressions listed below; generated test identifiers only. |
| `backend/tests/agents/test_manual_corrections.py` | Existing `test_team_delay_does_not_misattribute_missing_due_date` expects the corrected two-sentence wording. Test name and attribution check retained. |
| `frontend/src/features/agents/__tests__/AgentManualCorrections.test.jsx` | Two new count-redundancy cases; existing tests retained. |
| `frontend/src/features/agents/__tests__/AgentWorkspace.test.jsx` | Existing single-candidate presentation test expects the one retained explanatory sentence and checks absence of the removed repetition. No existing test was renamed. |

## Verification

| Check | Result |
| --- | --- |
| New backend cases | **34 cases**, all passed within the final focused run below |
| New regressions + existing manual corrections | **86 passed** (34 new + 52 existing), 4 warnings, 9.90 seconds |
| Final specialist/coordinator/runtime/API/security agent suite | **680 passed**, 4 warnings, 30.80 seconds |
| Final complete backend suite | **853 passed**, 6 warnings, 58.29 seconds |
| Focused Agent Workspace frontend | **61 passed**, 4 files, 10.36 seconds |
| Complete frontend suite | **130 passed**, 8 files, 22.15 seconds |
| Old → new test totals | Backend **819 → 853**; frontend **128 → 130** |
| Production frontend build | **Passed**, 102 modules, 6.49 seconds |
| `pip check` | **Passed**: No broken requirements found |
| `git diff --check` | **Passed**; pre-existing README LF/CRLF conversion warning |
| Secret scanner | No configured repository secret scanner found. `backend/scripts/check_security.py` tests password hashing/salts; it is not a secret scanner. **No automated secret scan claimed.** |

Commands used: `backend/.venv/Scripts/python.exe -m pytest backend/tests/agents/test_live_regression_prose.py backend/tests/agents/test_manual_corrections.py -q --tb=short`; `... -m pytest backend/tests/agents -q --tb=short`; `... -m pytest -q --tb=short`; `npm test -- src/features/agents`; `npm test`; `npm run build`; `... -m pip check`; `git diff --check`.

The complete suite passed 852 cases before the final long-theme regression was added. That new test reproduced a public truncation fragment and prompted the whole-sentence budget fix; the final suite is rerun after that change. Frontend sources were unchanged after their final test/build runs.

Warnings: Starlette TestClient/httpx integration deprecation; deprecated AnyIO BlockingPortal alias; deprecated HTTP 422 constant usage; Git’s existing README LF/CRLF conversion warning. Frontend commands used approved escalation for the known sandbox Node path-resolution restriction. No packages or dependency versions changed.

## Exact new test names

All backend tests below exercise the public production FastAPI/coordinator/runtime path with controlled database/provider boundaries. They feed fragments, missing punctuation, duplicate variants, unsupported completion conclusions, and unsupported blocker causes into the provider boundary. No source-text/constant-only tests were substituted.

- `test_task_delay_estimate_sentence_is_grammatically_complete`
- `test_missing_due_date_limitation_is_two_complete_sentences`
- `test_productivity_snapshot_limitations_are_grammatically_complete`
- `test_team_collaboration_scope_limitation_is_grammatically_complete`
- `test_wellbeing_scope_limitation_is_grammatically_complete`
- `test_task_linked_message_limitation_is_canonical_and_not_duplicated`
- `test_top_level_limitations_are_semantically_nonduplicative` (four workflows)
- `test_top_level_recommended_actions_are_semantically_nonduplicative` (two workflows)
- `test_wellbeing_collection_action_is_not_repeated` (two workflows)
- `test_collaboration_status_inquiry_does_not_confirm_task_completion`
- `test_collaboration_does_not_emit_unverified_blocker_cause` (two note conditions)
- `test_general_workforce_uses_workflow_appropriate_collaboration_limitation`
- `test_single_week_heading_has_no_spurious_comma`
- `test_live_task_delay_payload_has_complete_nonduplicated_public_prose`
- `test_live_team_delay_payload_has_complete_nonduplicated_public_prose`
- `test_live_team_workload_payload_has_complete_nonduplicated_public_prose`
- `test_live_general_workforce_payload_has_complete_nonduplicated_public_prose`
- `test_collaboration_visible_fields_reject_cross_domain_conclusions` (six domain claims)
- `test_collaboration_preserves_complete_themes_and_rejects_provider_fragments`
- `test_specialist_item_deduplication_preserves_distinct_evidence_gaps`
- `test_live_assignment_payload_preserves_evidence_confidence_and_suitability`
- `test_production_sentence_filter_preserves_legitimate_semicolon_punctuation`
- `test_collaboration_output_budget_does_not_cut_a_communication_sentence`

Frontend new test: `keeps count badges and one explanatory sentence for %s evaluated candidates` (counts 1 and 3). It checks retained badges, singular/plural explanatory text, removal of repetition, 91% suitability, and the capacity-review label. The existing tests continue covering other card details, rejected candidates, separate risk/availability regions, manager approval, accessible labels, and safe clipboard text.

## Numeric and behavioral preservation

The controlled API evidence matches the reported current shapes and produces:

| Workflow/value | Verified local result |
| --- | --- |
| Task-scoped Task Delay | **0.60** |
| Team Task Delay | **0.77** |
| Team Workload, four weeks | **0.45** |
| General Workforce, four weeks | **0.45**, minimum contributing specialist |
| Task Assignment evidence confidence | **0.95** |
| Candidate suitability | **0.91**, shown as **91%** by the frontend |

The fixture retains the eight-hour estimate, 20% recorded progress, overdue task, five resolved linked blockers, and unavailable task-linked messages. Team data retains three overdue tasks out of four with one missing due date. Well-being retains the single qualifying three-response week and four-week request. No evidence records from another scope are substituted. Existing privacy-refusal, scope, role, eligibility, ranking, and deterministic confidence regressions remain in the passing agent/full suites.

## Remaining limitations and manual re-tests

Live MongoDB/provider and browser visual re-tests are **not performed in this session**. The user’s live observations were reproduced locally, including public specialist fields and top-level synthesis. Communication-theme validation is conservative; it retains complete message-domain prose within bounds but does not validate blocker-note themes. Specific blocker causes remain suppressed until a separate sanitized provenance design exists. No future progress-note, blocker-note, or pulse-comment NLP was implemented.

Deduplication recognizes exact full-word-sequence equivalence and explicitly mapped deterministic variants; it is not arbitrary paraphrase inference. Distinct evidence gaps are preserved and tested. Time-log/historical throughput limitations and task-message linkage limitations remain current product constraints. The prior reports were not edited to imply live verification.

Use the following exact JSON manual fixtures with an authorized Manager token. Send to backend `POST /agents/execute` or frontend proxy `POST /api/agents/execute`. Do not add a client intent. The production identifiers below appear only in this manual-test section. Expected numbers depend on the evidence remaining unchanged.

### 1. Privacy-protective Collaboration

```json
{
  "question": "Analyse both the verified blocker records and team collaboration messages from the selected period. Do not expose raw messages, names, emails, IDs, or private comments.",
  "target_team_id": "6aafb013baee0a127151a8ab",
  "weeks_lookback": 4
}
```

Expected: accepted; only Collaboration consulted. Retain safe communication themes/status inquiries, explicitly avoid independently verifying completion, and show only verified blocker counts/statuses. No specific API-access cause/recommendation, raw messages, names, emails, identifiers, or private comments.

### 2. Task-scoped Task Delay

```json
{
  "question": "Why is this task delayed? Separate verified observations, evidence gaps, and hypotheses for investigation.",
  "target_team_id": "6aafb013baee0a127151a8ab",
  "target_task_id": "6aaff6d3d6e0aa036a1fb896",
  "weeks_lookback": 4
}
```

Expected: Productivity and Collaboration; confidence **0.60**; complete two-sentence estimate wording; 20% progress, five linked resolved blockers, no active/stale linked blockers if unchanged; one canonical task-message limitation in each relevant list; exact delay cause remains unverified. No estimate-as-actual-time claim or malformed clauses.

### 3. Team Task Delay

```json
{
  "question": "Why are team tasks delayed? Review task progress and verified collaboration blocker evidence.",
  "target_team_id": "6aafb013baee0a127151a8ab",
  "weeks_lookback": 4
}
```

Expected: team-scoped Productivity and Collaboration; confidence **0.77**. Missing due date reported as “One task has no verified due date. Its overdue status cannot be established.” without attributing it to Web App Development. Team scope limitation and other limitations/actions are complete and nonduplicative.

### 4. Team Workload over four weeks

```json
{
  "question": "Review overdue tasks and anonymous well-being for team workload over four weeks. Distinguish delivery strain from verified capacity evidence.",
  "target_team_id": "6aafb013baee0a127151a8ab",
  "weeks_lookback": 4
}
```

Expected: Productivity and Well-being; confidence **0.45**. Current snapshot and lookback limitations have full stops. Anonymous single-week heading has no comma before “for”; experience/capacity limitation is two complete sentences; one combined pulse collection/manager-priority action per list. Delivery strain does not prove exceeded capacity.

### 5. General Workforce over four weeks

```json
{
  "question": "Give a general workforce overview over four weeks covering productivity, collaboration, and anonymous well-being.",
  "target_team_id": "6aafb013baee0a127151a8ab",
  "weeks_lookback": 4
}
```

Expected: all three domains; confidence **0.45**. Current task snapshot, Collaboration window, and qualifying pulse week remain distinct. Collaboration limitations refer to overall delivery performance, not a presumed current delay. No duplicate collection actions, duplicate availability limitations, unsupported completion/cause conclusions, or demonstrated malformed strings.

### 6. Task Assignment API

```json
{
  "question": "Recommend up to 3 eligible candidates for the selected task. Explain required-skill coverage, current workload, overdue risk, capacity limitations, and the manager decision required.",
  "target_team_id": "6aafb013baee0a127151a8ab",
  "target_task_id": "6aaff6d3d6e0aa036a1fb896"
}
```

Expected: Task Assignment only; evidence confidence **0.95**; suitability **0.91** for the described candidate/evidence. Keep structured details, required/matched/missing skills, counts, risks, and `human_decision_required=true`. No lookback field or assignment mutation.

### 7. Task Assignment structured UI

Use payload 6 through Agent Workspace with the selected team/task and Lookback unset. Expected: Requested/Eligible/Evaluated badges plus one explanatory evaluated-count sentence. Preserve **91%**, “Capacity review required”, “All required skills matched”, separate availability/capacity and overdue-risk regions, rejected-candidate missing skills, and advisory manager approval. No raw pipe summary. Accessible labels and clipboard remain privacy-safe. Browser visual verification remains unperformed here; DOM tests/build passed.

## Exact final Git status

Appended after report creation and final verification.

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
?? backend/app/modules/agents/collaboration_reporting.py
?? backend/app/modules/agents/confidence_scorer.py
?? backend/app/modules/agents/grounded_reporting.py
?? backend/app/modules/agents/public_reporting.py
?? backend/tests/agents/test_coordinator_corrections.py
?? backend/tests/agents/test_coordinator_regression_audit.py
?? backend/tests/agents/test_live_regression_prose.py
?? backend/tests/agents/test_manual_corrections.py
?? frontend-baseline-results.json
?? frontend/src/features/agents/
```
