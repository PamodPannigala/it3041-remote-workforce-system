"""
Deterministic Evidence-Based Confidence Scoring Module.

Provides transparent, verifiable evidence-confidence assessment functions for
each specialist domain and Coordinator synthesis. Replaces arbitrary hardcoded
confidence values with quantifiable evidence quality factors.
"""

from typing import Any, Sequence
import math

from backend.app.modules.agents.protocol import AgentFinding, EvidenceReference


def compute_productivity_confidence(
    task_count: int,
    has_complete_dates: bool = True,
    has_complete_statuses: bool = True,
) -> float:
    """
    Computes deterministic evidence confidence for Productivity Specialist findings.

    Factors:
    - Task Volume: Scoped task count evaluated within the team context.
    - Completeness: Presence of due dates and unambiguous task lifecycle statuses.
    """
    if task_count <= 0:
        return 0.30

    if task_count == 1:
        base = 0.60
    elif task_count <= 3:
        base = 0.75
    elif task_count <= 5:
        base = 0.85
    else:
        base = 0.95

    # Completeness adjustment
    if not has_complete_dates:
        base -= 0.08
    if not has_complete_statuses:
        base -= 0.05

    return round(max(0.10, min(1.0, base)), 2)


def compute_collaboration_confidence(
    message_count: int,
    blocker_count: int = 0,
    has_timestamps: bool = True,
) -> float:
    """
    Computes deterministic evidence confidence for Collaboration Specialist findings.

    Factors:
    - Message Volume: Scoped message records retrieved within the lookback window.
    - Blocker Context: Verified blocker records with resolution statuses.
    - Timestamps: Valid creation timestamps for latency analysis.
    """
    if message_count <= 0 and blocker_count <= 0:
        return 0.30

    if message_count == 1 and blocker_count == 0:
        base = 0.60
    elif message_count <= 3:
        base = 0.72
    elif message_count <= 6:
        base = 0.84
    else:
        base = 0.95

    if blocker_count > 0:
        base = min(1.0, base + 0.05)

    if not has_timestamps:
        base -= 0.10

    return round(max(0.10, min(1.0, base)), 2)


# Named Constants for Well-being Confidence Scoring
WELLBEING_WEIGHT_TEMPORAL_COVERAGE: float = 0.40
WELLBEING_WEIGHT_RESPONSE_STRENGTH: float = 0.25
WELLBEING_WEIGHT_METRIC_COMPLETENESS: float = 0.20
WELLBEING_WEIGHT_DATA_RECENCY: float = 0.15

WELLBEING_MIN_PRIVACY_RESPONSES: int = 3
WELLBEING_SATURATING_RESPONSES_PER_WEEK: float = 10.0
WELLBEING_MIN_SAMPLE_STRENGTH_BASE: float = 0.30

WELLBEING_LONGITUDINAL_PENALTY_FACTOR: float = 0.85
WELLBEING_MAX_TRACKED_METRICS: int = 4


def compute_wellbeing_confidence(
    total_responses: int,
    qualifying_weeks: int,
    requested_weeks: int,
    privacy_threshold_met: bool,
    valid_metrics_count: int = WELLBEING_MAX_TRACKED_METRICS,
    is_recent: bool = True,
) -> float:
    """
    Computes deterministic evidence confidence for Well-being Specialist findings.

    Privacy Threshold as Gate:
    - If privacy_threshold_met is False, or qualifying_weeks <= 0, or total_responses < 3,
      confidence is strictly 0.0 (no evidence can be published).

    Factors (when privacy gate passes):
    1. Temporal Coverage (Weight: 0.40):
       Ratio of privacy-safe qualifying weeks to requested lookback weeks.
       qualifying_weeks / max(1, requested_weeks)

    2. Response Strength (Weight: 0.25):
       Measures statistical power above the minimum privacy threshold (3 responses).
       Average responses per qualifying week:
       R_avg = total_responses / qualifying_weeks
       For R_avg = 3 (bare minimum): strength = 0.30
       For R_avg >= 10 (strong sample): strength = 1.00
       Linear interpolation between 3 and 10 responses per week.

    3. Metric Completeness (Weight: 0.20):
       Ratio of valid aggregated metrics (workload, work-life balance, team support, engagement)
       available without per-metric privacy suppression.
       valid_metrics_count / 4.0

    4. Data Recency (Weight: 0.15):
       1.0 if the latest qualifying survey is within the requested period; 0.60 if older/stale.

    5. Longitudinal Sufficiency:
       If multi-week analysis is requested (requested_weeks >= 2) but only 1 qualifying week
       is available (qualifying_weeks < 2), a multi-week trend cannot be established.
       The composite score is scaled by WELLBEING_LONGITUDINAL_PENALTY_FACTOR (0.85).
    """
    if not privacy_threshold_met or qualifying_weeks <= 0 or total_responses < WELLBEING_MIN_PRIVACY_RESPONSES:
        return 0.0

    req_weeks = max(1, int(requested_weeks))
    qual_weeks = max(0, int(qualifying_weeks))

    # 1. Temporal Coverage
    temporal_coverage = min(1.0, max(0.0, qual_weeks / req_weeks))

    # 2. Response Strength above privacy minimum
    avg_responses_per_week = total_responses / qual_weeks if qual_weeks > 0 else 0.0
    if avg_responses_per_week <= WELLBEING_MIN_PRIVACY_RESPONSES:
        response_strength = WELLBEING_MIN_SAMPLE_STRENGTH_BASE
    else:
        # Scale linearly from 0.30 (at 3 responses) to 1.00 (at 10 responses)
        excess = avg_responses_per_week - WELLBEING_MIN_PRIVACY_RESPONSES
        scale_range = WELLBEING_SATURATING_RESPONSES_PER_WEEK - WELLBEING_MIN_PRIVACY_RESPONSES  # 7.0
        response_strength = min(1.0, WELLBEING_MIN_SAMPLE_STRENGTH_BASE + (0.70 * (excess / scale_range)))

    # 3. Metric Completeness
    bounded_metrics = min(WELLBEING_MAX_TRACKED_METRICS, max(0, int(valid_metrics_count)))
    metric_completeness = bounded_metrics / float(WELLBEING_MAX_TRACKED_METRICS)

    # 4. Data Recency
    recency_factor = 1.0 if is_recent else 0.60

    # Composite weighted base
    raw_confidence = (
        (WELLBEING_WEIGHT_TEMPORAL_COVERAGE * temporal_coverage)
        + (WELLBEING_WEIGHT_RESPONSE_STRENGTH * response_strength)
        + (WELLBEING_WEIGHT_METRIC_COMPLETENESS * metric_completeness)
        + (WELLBEING_WEIGHT_DATA_RECENCY * recency_factor)
    )

    # 5. Longitudinal Sufficiency Adjustment
    if req_weeks >= 2 and qual_weeks < 2:
        raw_confidence *= WELLBEING_LONGITUDINAL_PENALTY_FACTOR

    return round(max(0.0, min(1.0, raw_confidence)), 2)


def compute_task_assignment_confidence(
    has_target_task: bool,
    eligible_candidates_count: int,
    candidates_with_capacity: int,
    candidates_with_skills: int,
    top_suitability_score: float = 0.0,
    required_skills_count: int = 0,
    evaluated_candidate_count: int | None = None,
) -> float:
    """
    Computes deterministic evidence confidence for Task Assignment Specialist findings.

    Factors:
    - Task Existence & Ownership: Verified target task belonging to authorized team.
    - Task Required Skills: Verified task specification containing required skills.
    - Eligible Candidates Pool: Active team members available for allocation.
    - Capacity Evidence Completeness: Verified work profile weekly capacity hours.
    - Skill Evidence Completeness: Profile skills versus task required skills.
    - Suitability is separate and does not enter this evidence-confidence formula.
    Gate: no verified task, required skills, or eligible candidates => 0.30.
    N = max(eligible, evaluated); C and S are completeness ratios in [0, 1].
    Score = 0.50 + 0.25*C + 0.20*S - (0.15 if C < 0.5 else 0).
    Round to two decimals after clamping to [0.10, 0.95].
    """
    if not has_target_task or required_skills_count <= 0 or eligible_candidates_count <= 0:
        return 0.30

    pool_size = max(eligible_candidates_count, evaluated_candidate_count or 0)
    capacity_ratio = min(1.0, max(0.0, candidates_with_capacity / pool_size))
    skills_ratio = min(1.0, max(0.0, candidates_with_skills / pool_size))

    base = 0.50 + (0.25 * capacity_ratio) + (0.20 * skills_ratio)

    # top_suitability_score is retained for call compatibility, but suitability
    # measures candidate fit and must never influence evidence confidence.

    if capacity_ratio < 0.5:
        # Missing capacity data reduces confidence
        base -= 0.15

    return round(max(0.10, min(0.95, base)), 2)


def compute_coordinator_synthesis_confidence(
    contributing_findings: Sequence[AgentFinding],
) -> float:
    """
    Computes final Coordinator synthesis confidence according to the confidence contract.

    Contract:
    - Final Coordinator confidence must NOT exceed the minimum confidence of all
      contributing validated findings (weakest contributor bound).
    - If no contributing findings exist, returns 0.0.
    """
    if not contributing_findings:
        return 0.0

    min_conf = min(f.confidence for f in contributing_findings)
    return round(max(0.0, min(1.0, min_conf)), 2)


# =========================================================================
# Fallback Evidence-Based Deterministic Confidence Helpers
# =========================================================================


def compute_productivity_confidence_from_evidence(
    evidence_refs: Sequence[EvidenceReference],
) -> float:
    """Computes deterministic productivity confidence from EvidenceReference items."""
    task_items = [
        e for e in evidence_refs
        if e.source_type == "task" and e.record_id != "metrics-summary"
    ]
    if not task_items:
        for e in evidence_refs:
            if e.record_id == "metrics-summary":
                if "Total Tasks Evaluated: 0" in e.snippet or "Total Tasks: 0" in e.snippet:
                    return 0.30
                import re
                m = re.search(r"Total Tasks(?: Evaluated)?:\s*(\d+)", e.snippet)
                if m:
                    return compute_productivity_confidence(int(m.group(1)))
        return 0.30
    return compute_productivity_confidence(task_count=len(task_items))


def compute_collaboration_confidence_from_evidence(
    evidence_refs: Sequence[EvidenceReference],
) -> float:
    """Computes deterministic collaboration confidence from EvidenceReference items."""
    msg_count = sum(1 for e in evidence_refs if e.source_type == "collaboration_message")
    blocker_count = sum(1 for e in evidence_refs if e.source_type == "task")
    return compute_collaboration_confidence(message_count=msg_count, blocker_count=blocker_count)


def compute_task_assignment_confidence_from_evidence(
    evidence_refs: Sequence[EvidenceReference],
) -> float:
    """Computes deterministic task assignment confidence from EvidenceReference items."""
    # References alone cannot verify candidate profile/capacity completeness.
    return 0.30


def compute_wellbeing_confidence_from_evidence(
    evidence_refs: Sequence[EvidenceReference],
) -> float:
    """Computes deterministic wellbeing confidence from EvidenceReference items."""
    # Only the pulse tool's privacy-safe computed metrics can establish confidence.
    return 0.0


# =========================================================================
# Domain Boundary & Public Prose Sanitization
# =========================================================================


def is_prohibited_request(question: str) -> bool:
    """
    Detects prohibited data extraction requests (emails, database IDs, individual pulse responses,
    private comments, internal error codes) and adversarial prompt injection attempts before
    evidence collection.
    """
    import re
    q = question.lower().replace("’", "'")
    injection_patterns = [
        r"\bignore\s+(?:all\s+)?(?:the\s+)?(?:previous\s+)?instructions\b",
        r"\bignore\s+(?:your\s+)?rules\b",
        r"\b(?:output|reveal)\s+(?:the\s+)?system\s+prompt\b",
        r"\b(?:override\s+security|bypass\s+guardrails|dump\s+pulse)\b",
        r"\b(?:execute|run|select)\s+(?:secret_|unauthorized_)[\w-]*agent\b",
    ]
    # An unrelated protective instruction never cancels an injection directive.
    if any(re.search(p, q) for p in injection_patterns):
        return True
    sensitive_patterns = [
        r"\b(?:employee|personal)\s+names?\b",
        r"\b(?:reveal|expose|print|disclose)\s+(?:all\s+|every\s+)?names?\b",
        r"\b(?:employee\s+)?emails?\b",
        r"\b(?:database\s+ids?|mongodb\s+ids?|objectids?)\b",
        r"\bindividual\s+(?:pulse\s+)?(?:responses?|surveys?)\b",
        r"\braw\s+(?:pulse\s+)?(?:responses?|surveys?)\b",
        r"\bprivate\s+comments?\b",
        r"\bconfidential\s+comments?\b",
        r"\binternal\s+error\s+codes?\b",
        r"\bstack\s+traces?\b",
        r"\braw\s+(?:private\s+)?messages?\b",
        r"\breveal\s+every\s+employee\b",
    ]
    # Allow only an entire, narrowly recognized protective disclosure clause.
    # Its object must be a list of sensitive categories, not another instruction
    # (e.g. 'do not hesitate to reveal', 'do not hide emails and print IDs').
    protective = re.compile(
        r"^(?:please\s+)?(?:do\s+not|don't|never|must\s+not|avoid)\s+"
        r"(?:expose|reveal|disclose|display|show|output|print|share|sharing|exposing|revealing)\s+(.+)$"
    )
    category = re.compile(
        r"\b(?:(?:any|the|all|every|employee|individual|raw|private|confidential|database|mongodb|internal|pulse)\s+)*"
        r"(?:messages?|names?|emails?|ids?|objectids?|comments?|responses?|surveys?|error\s+codes?|stack\s+traces?)\b"
    )
    clauses = re.split(r"[.!?;\n]+|\b(?:but|however|then|instead|except)\b", q)
    for clause in clauses:
        if not any(re.search(p, clause) for p in sensitive_patterns):
            continue
        match = protective.fullmatch(clause.strip())
        if match:
            remainder = category.sub("", match.group(1))
            remainder = re.sub(r"\b(?:and|or)\b|[,\s]", "", remainder)
            if not remainder:
                continue
        return True
    return False


def sanitize_specialist_output(
    agent: str,
    summary: str,
    limitations: list[str],
    recommended_actions: list[str],
    target_task_id: str | None = None,
    is_single_week_wellbeing: bool = False,
    task_assignment_details: Any = None,
    task_messages_unavailable: bool = False,
    known_identifiers: set[str] | None = None,
    workflow_intent: str | None = None,
) -> tuple[str, list[str], list[str]]:
    """
    Deterministically sanitizes and enforces domain boundaries for specialist findings.
    Ensures that LLM generated text does not leak identifiers, cross specialist domains,
    make unsupported team-wide claims on task-scoped evidence, or use forbidden phrasing.
    """
    import re
    from backend.app.modules.agents.public_reporting import (
        TASK_MESSAGES_UNAVAILABLE, deduplicate_public_items, wellbeing_collection_action,
    )

    def _sanitize_text(text: str) -> str:
        if not text:
            return ""
        from backend.app.modules.agents.security_policy import sanitize_public_prose
        text = sanitize_public_prose(text, known_identifiers)
        # Remove whole unsupported sentences; substituting another positive claim
        # would introduce a new assertion without evidence.
        forbidden = None
        if agent == "wellbeing" and is_single_week_wellbeing:
            forbidden = r"\b(?:stable|stability|trends?|improv\w*|declin\w*|sustain\w*|baseline)\b"
        elif agent == "collaboration":
            forbidden = r"\b(?:task\s+management|productivity|effective\s+task\s+management|strong\s+task\s+management|delivery\s+(?:success\w*|succeeded|is\s+(?:successful|effective|on\s+track))|productivity\s+success\w*|highly\s+productive|strong\s+productivity|well[ -]?being|morale|burnout|task\s+(?:progress|is\s+\d+%\s+complete)|no\s+delivery\s+bottlenecks)\b"
        if forbidden:
            # A semicolon is part of a sentence. Removing it and joining clauses
            # with a space destroys deterministic prose and can leave fragments.
            text = " ".join(s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if not re.search(forbidden, s, re.IGNORECASE))

        # 2. General prose corrections: project -> task
        text = re.sub(r"\bthis\s+project\b", "this task", text, flags=re.IGNORECASE)
        text = re.sub(r"\bthe\s+project\b", "the task", text, flags=re.IGNORECASE)
        text = re.sub(r"\bprojects\b", "tasks", text, flags=re.IGNORECASE)
        text = re.sub(r"\bproject\b", "task", text, flags=re.IGNORECASE)

        # 3. Avoid unsupported generalizations
        text = re.sub(r"\b8\s*hours\s+per\s+task\b", "estimated 8 hours for the evaluated task", text, flags=re.IGNORECASE)
        text = re.sub(r"\bthe\s+team['’]?s\s+current\s+focus\b", "a current in-progress task for the team", text, flags=re.IGNORECASE)

        # 4. Task-scoped claim correction (when target_task_id is evaluated)
        if target_task_id:
            text = re.sub(r"\bthe\s+only\s+active\s+task\s+for\s+the\s+team\b", "the selected task evaluated", text, flags=re.IGNORECASE)
            text = re.sub(r"\bno\s+blockers\s+for\s+this\s+task\s+or\s+the\s+team\b", "No active or stale blockers explicitly linked to the selected task were found.", text, flags=re.IGNORECASE)
            text = re.sub(r"\bno\s+active\s+blockers\s+(?:reported\s+)?for\s+this\s+team\b", "No active or stale blockers explicitly linked to the selected task were found.", text, flags=re.IGNORECASE)
            text = re.sub(r"\bno\s+active\s+blockers\s+for\s+the\s+team\b", "No active or stale blockers explicitly linked to the selected task were found.", text, flags=re.IGNORECASE)
            text = re.sub(r"\bverified\s+no\s+blockers\s+exist\b", "no linked records were found", text, flags=re.IGNORECASE)

        # 5. Agent-specific domain enforcement
        if agent == "productivity":
            # Productivity must NOT claim blocker resolution counts or collaboration message metrics
            text = " ".join(
                sentence for sentence in re.split(r"(?<=[.!?])\s+|\n+", text)
                if not re.search(r"\b(?:\d+\s+blockers?\s+resolved|resolved\s+\d+\s+blockers?)\b", sentence, re.IGNORECASE)
            )
            text = re.sub(r"\b(?:collaboration\s+messages?\s+indicate|messaging\s+patterns?\s+show|communication\s+frequency)\b[^.]*\.?", "", text, flags=re.IGNORECASE)

        elif agent == "collaboration":
            # Collaboration must NOT claim delivery success, absence of delivery bottlenecks, productivity success, task management, or progress
            text = re.sub(r"\b(?:absence\s+of\s+delivery\s+bottlenecks|no\s+delivery\s+bottlenecks|delivery\s+bottlenecks?\s+are\s+absent|delivery\s+success|delivery\s+is\s+successful)\b", "blocker discussions are monitored", text, flags=re.IGNORECASE)
            text = re.sub(r"\b(?:productivity\s+success|highly\s+productive(?:\s+team)?|strong\s+productivity)\b", "active collaboration", text, flags=re.IGNORECASE)
            text = re.sub(r"\b(?:effective\s+task\s+management|strong\s+task\s+management)\b", "team communication", text, flags=re.IGNORECASE)
            text = re.sub(r"\b(?:task\s+is\s+\d+%\s+complete|task\s+progress\s+is\s+on\s+track|task\s+status\s+is\s+in_progress)\b", "task communication recorded", text, flags=re.IGNORECASE)
            text = re.sub(r"\b(?:well-?being\s+is\s+high|morale\s+is\s+strong|low\s+burnout)\b", "team participation observed", text, flags=re.IGNORECASE)

        elif agent == "wellbeing" and is_single_week_wellbeing:
            # Single-week wellbeing snapshot enforcement
            text = re.sub(r"\bconsistent\s+sentiment\b", "observed sentiment", text, flags=re.IGNORECASE)
            text = re.sub(r"\bremains?\s+stable\b", "observed in this single-week snapshot", text, flags=re.IGNORECASE)
            text = re.sub(r"\bis\s+stable\b", "was observed in this single-week snapshot", text, flags=re.IGNORECASE)
            text = re.sub(r"\bstable\s+conditions\b", "single-week snapshot conditions", text, flags=re.IGNORECASE)
            text = re.sub(r"\bremains?\s+sustainable\b", "observed in this single-week snapshot", text, flags=re.IGNORECASE)
            text = re.sub(r"\bis\s+sustainable\b", "was observed in this single-week snapshot", text, flags=re.IGNORECASE)
            text = re.sub(r"\bsustain\s+current\s+positive\s+ratings\b", "monitor ratings in upcoming weeks", text, flags=re.IGNORECASE)
            text = re.sub(r"\bestablished\s+baseline\b", "single-week snapshot", text, flags=re.IGNORECASE)

        elif agent == "task_assigning":
            # Task assignment wording for current assignee and overdue candidates
            text = re.sub(r"\b(?:confirm\s+assignment|assign\s+task\s+to\s+current\s+assignee)\b", "Review whether to retain the current assignment or reassign the task after confirming capacity.", text, flags=re.IGNORECASE)

        # Repair mechanical substitutions without asking a model to rewrite facts.
        text = re.sub(r"\ba observed\b", "an observed", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(\w+)\s+\1\b", r"\1", text, flags=re.IGNORECASE)
        text = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m[1] + m[2].upper(), text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    clean_summary = _sanitize_text(summary)

    # Prepend snapshot prefix for single-week wellbeing
    if agent == "wellbeing" and is_single_week_wellbeing:
        if "single-week snapshot" not in clean_summary.lower():
            clean_summary = f"This result is a single-week snapshot. {clean_summary}".strip()

    # In task-scoped collaboration, state if no task-linked messages were available
    if agent == "collaboration" and target_task_id and task_messages_unavailable:
        if "No trustworthy collaboration messages explicitly linked to the selected task were available." not in clean_summary:
            clean_summary = f"{clean_summary} No trustworthy collaboration messages explicitly linked to the selected task were available.".strip()

    clean_limitations = []
    for lim in limitations:
        cleaned_lim = _sanitize_text(lim)
        if cleaned_lim and cleaned_lim not in clean_limitations:
            clean_limitations.append(cleaned_lim)

    if agent == "wellbeing" and is_single_week_wellbeing:
        snap_lim = "This result is a single-week snapshot; at least two privacy-safe weeks are needed for comparison."
        if snap_lim not in clean_limitations:
            clean_limitations.insert(0, snap_lim)

    clean_actions = []
    for act in recommended_actions:
        cleaned_act = _sanitize_text(act)
        if cleaned_act and cleaned_act not in clean_actions:
            clean_actions.append(cleaned_act)

    if agent == "collaboration" and target_task_id and task_messages_unavailable:
        clean_limitations.insert(0, TASK_MESSAGES_UNAVAILABLE)

    if agent == "wellbeing" and is_single_week_wellbeing:
        snap_act = wellbeing_collection_action(workflow_intent)
        clean_actions = [a for a in clean_actions if "sustain" not in a.lower()]
        if snap_act not in clean_actions:
            clean_actions.append(snap_act)

    if not clean_summary:
        clean_summary = "Only verified evidence within this specialist's domain can be reported."
    return (clean_summary[:3000], deduplicate_public_items(clean_limitations, workflow_intent)[:20],
            deduplicate_public_items(clean_actions, workflow_intent)[:20])


def sanitize_coordinator_synthesis(
    summary: str,
    limitations: list[str],
    recommended_actions: list[str],
) -> tuple[str, list[str], list[str]]:
    """
    Sanitizes Coordinator synthesis text and deduplicates repeated claims/sentences.
    """
    import re
    if not summary:
        return "", [], []

    # 1. Mask sensitive IDs and emails
    text = re.sub(r"\b[0-9a-fA-F]{24}\b", "[ID]", summary)
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[EMAIL]", text)
    text = re.sub(r"\bERR_[A-Z0-9_]+\b", "[ERROR_CODE]", text)

    # 2. General prose corrections: project -> task
    text = re.sub(r"\bthis\s+project\b", "this task", text, flags=re.IGNORECASE)
    text = re.sub(r"\bthe\s+project\b", "the task", text, flags=re.IGNORECASE)
    text = re.sub(r"\bprojects\b", "tasks", text, flags=re.IGNORECASE)
    text = re.sub(r"\bproject\b", "task", text, flags=re.IGNORECASE)
    text = re.sub(r"\b8\s*hours\s+per\s+task\b", "estimated 8 hours for the evaluated task", text, flags=re.IGNORECASE)
    text = re.sub(r"\bthe\s+team['’]?s\s+current\s+focus\b", "a current in-progress task for the team", text, flags=re.IGNORECASE)

    # 3. Deduplicate sentences
    raw_sentences = re.split(r"(?<=[.!?])\s+", text)
    seen_normalized: set[str] = set()
    deduped_sentences: list[str] = []
    for s in raw_sentences:
        s_clean = s.strip()
        if not s_clean:
            continue
        norm = re.sub(r"\s+", " ", s_clean.lower())
        if norm not in seen_normalized:
            seen_normalized.add(norm)
            deduped_sentences.append(s_clean)

    deduped_summary = " ".join(deduped_sentences)

    clean_limitations: list[str] = []
    for l in limitations:
        l_clean = re.sub(r"\s+", " ", l).strip()
        l_clean = re.sub(r"\bprojects?\b", "task", l_clean, flags=re.IGNORECASE)
        if l_clean and l_clean not in clean_limitations:
            clean_limitations.append(l_clean)

    clean_actions: list[str] = []
    for a in recommended_actions:
        a_clean = re.sub(r"\s+", " ", a).strip()
        a_clean = re.sub(r"\bprojects?\b", "task", a_clean, flags=re.IGNORECASE)
        if a_clean and a_clean not in clean_actions:
            clean_actions.append(a_clean)

    return deduped_summary, clean_limitations[:20], clean_actions[:20]
