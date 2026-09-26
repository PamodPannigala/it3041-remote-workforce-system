"""Public facts for composite workflows, assembled from server-owned tool metrics.

Task-state records contain estimates and progress, not verified elapsed effort or
causal links. Do not turn task text, skills, or overdue ratios into delay causes.
"""

from backend.app.modules.agents.public_reporting import (
    TASK_MESSAGES_UNAVAILABLE, deduplicate_public_items, wellbeing_collection_action,
)

COMPOSITE_INTENTS = {"task_delay_analysis", "team_workload_analysis", "general_workforce_question"}


def count_phrase(count, noun):
    return f"{count} {noun}{'' if count == 1 else 's'}"


def grounded_specialist_update(agent, context):
    request = context.request
    if (request.workflow_intent or request.intent) not in COMPOSITE_INTENTS:
        return None
    facts = context.evidence_metrics
    limitations, actions = [], []
    if agent == "productivity" and "productivity" in facts:
        metrics = facts["productivity"]
        scope = "selected-task" if request.target_task_id else "selected-team"
        summary = (
            f"Productivity: Current {scope} task-state snapshot. "
            f"The snapshot contains {count_phrase(metrics.total_tasks, 'evaluated task')}. "
            f"Of these, {metrics.overdue_count} {'is' if metrics.overdue_count == 1 else 'are'} overdue, "
            f"{metrics.completed_count} {'is' if metrics.completed_count == 1 else 'are'} completed, "
            f"{metrics.in_progress_count} {'is' if metrics.in_progress_count == 1 else 'are'} in progress, "
            f"{metrics.blocked_count} {'is' if metrics.blocked_count == 1 else 'are'} blocked, "
            f"and {metrics.todo_count} {'is' if metrics.todo_count == 1 else 'are'} not started."
        )
        if metrics.average_progress is not None:
            summary += f" Average recorded progress is {metrics.average_progress:g}%."
        estimates = facts.get("productivity_estimates", [])
        if request.target_task_id and len(estimates) == 1:
            summary += f" The recorded estimate is {estimates[0]:g} hours. This is a planning estimate, not actual time spent."
        missing = facts.get("productivity_missing_due_dates", 0)
        if missing:
            limitations.append(
                "One task has no verified due date. Its overdue status cannot be established."
                if missing == 1 else
                f"{count_phrase(missing, 'task')} have no verified due date. Their overdue status cannot be established."
            )
        limitations.append("Actual time-spent records and historical throughput were not retrieved. Current task states do not establish elapsed effort or delay causes.")
        if request.weeks_lookback:
            limitations.append(f"The {request.weeks_lookback}-week request limits task activity dates where applicable. Productivity is a current snapshot, not historical throughput over that window.")
        actions = ["Review overdue delivery risks and task priorities with the manager."]
    elif agent == "collaboration" and "collaboration_blocker_metrics" in facts:
        metrics = facts["collaboration_blocker_metrics"]
        period = f"{metrics.evidence_start:%Y-%m-%d UTC} to {metrics.evidence_end:%Y-%m-%d UTC}"
        if request.target_task_id:
            summary = "Collaboration: " + metrics.to_task_summary_text()
        else:
            summary = (
                f"Collaboration: Selected-team evidence from {period}. "
                f"Verified blocker records show {metrics.unresolved_blocker_count} active blockers, "
                f"including {metrics.stale_unresolved_blocker_count} stale blockers, and "
                f"{metrics.resolved_blocker_count} blockers resolved within the selected period."
            )
            limitations.append("Team collaboration evidence spans multiple team tasks. It is not all attributed to any one task.")
        messages = facts.get("collaboration_messages", 0)
        if messages:
            summary += f" The selected period includes {count_phrase(messages, 'retrieved collaboration message')}."
        elif request.target_task_id:
            limitations.append(TASK_MESSAGES_UNAVAILABLE)
        else:
            limitations.append("No collaboration messages were retrieved within the selected period.")
        if (request.workflow_intent or request.intent) == "task_delay_analysis":
            limitations.append("Blocker status and resolution records establish observations, not a verified cause of the current delay.")
            actions = ["Review verified blocker records and collect linked communication evidence before attributing a delay cause."]
        else:
            limitations.append("Blocker status and resolution records establish Collaboration-domain observations. They do not independently explain overall delivery performance.")
            actions = ["Review verified blocker records and communication evidence with the manager to support delivery decisions."]
    elif agent == "wellbeing" and "wellbeing" in facts:
        metrics = facts["wellbeing"]
        weeks = [week for week in metrics.weekly_aggregates if week.is_privacy_threshold_met]
        if not weeks:
            summary = "Well-being: No qualifying privacy-safe weeks are available; aggregate ratings remain suppressed."
        else:
            dates = ", ".join(f"{week.week_start:%Y-%m-%d}" for week in weeks)
            label = "single-week snapshot" if len(weeks) == 1 else f"{len(weeks)} qualifying privacy-safe weeks"
            period_label = "the week starting" if len(weeks) == 1 else "weeks starting"
            summary = f"Well-being: Anonymous {label} for {period_label} {dates} UTC."
            for name, value in (
                ("workload manageability", metrics.overall_average_workload_manageability),
                ("work-life balance", metrics.overall_average_work_life_balance),
                ("team support", metrics.overall_average_team_support),
                ("engagement", metrics.overall_average_engagement),
            ):
                if value is not None:
                    summary += f" Average {name} is {value:.2f} out of 5."
        limitations.append("Anonymous well-being ratings describe reported experience. They do not establish delivery capacity or individual performance.")
        actions = [wellbeing_collection_action(request.workflow_intent or request.intent)]
    else:
        return None
    return dict(summary=summary, limitations=limitations, recommended_actions=actions, is_fact_grounded=True)


def grounded_synthesis(intent, findings, correlation_id, evidence_refs):
    """Combine complete domain facts, retaining each period and reconciling gaps."""
    from backend.app.modules.agents.protocol import AgentFinding
    from backend.app.modules.agents.confidence_scorer import compute_coordinator_synthesis_confidence
    summaries = [finding.summary for finding in findings]
    limitations = deduplicate_public_items((lim for f in findings for lim in f.limitations), intent)
    actions = deduplicate_public_items((action for f in findings for action in f.recommended_actions), intent)
    if intent == "task_delay_analysis":
        summaries.append("The exact cause of the delay cannot be established from the available evidence.")
        actions.append("Investigate scope, estimation, dependencies, prioritization, and capacity as hypotheses; collect time logs and qualitative evidence before confirming a cause.")
    elif intent == "team_workload_analysis":
        summaries.append("Overdue tasks indicate delivery strain; they do not establish that team capacity was exceeded. Anonymous well-being ratings and delivery observations measure different aspects of the current situation.")
        limitations.append("Verified team capacity constraints were not retrieved; capacity, scope, estimation, dependencies, and prioritization remain possible investigations.")
    # Never copy a specialist's lack of access over evidence supplied by another.
    if any(f.agent == "wellbeing" for f in findings):
        limitations = [lim for lim in limitations if "no access to well-being" not in lim.lower()]
    return AgentFinding(
        agent="coordinator", correlation_id=correlation_id, summary="\n\n".join(summaries),
        confidence=compute_coordinator_synthesis_confidence(findings),
        evidence_refs=evidence_refs[:50], limitations=deduplicate_public_items(limitations, intent)[:20],
        recommended_actions=deduplicate_public_items(actions, intent)[:20], is_fact_grounded=True,
    )
