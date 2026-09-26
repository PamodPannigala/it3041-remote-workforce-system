"""Bound team Collaboration prose without promoting messages or notes to causes.

Existing provider communication themes may be retained. Blocker-note provenance
is not validated in this system, so specific blocker causes are never published.
"""
import re

from backend.app.modules.agents.public_reporting import deduplicate_public_items

_OTHER_DOMAIN = re.compile(
    r"\b(?:complet\w*|finish\w*|done|delivered|delivery|productivity|task\s+management|"
    r"manageab\w*|well[ -]?being|morale|burnout|capacity|performance|progress)\b", re.I,
)
_BLOCKER_CAUSE = re.compile(
    r"\b(?:blockers?|resolv\w*|resolution|dependenc\w*|api|access|caus\w*|"
    r"because|due\s+to|constraints?|resources?|implementation)\b", re.I,
)
_COMMUNICATION = re.compile(r"\b(?:messages?|communications?|inquir\w*|coordination|discussions?|standups?|responses?|meetings?)\b", re.I)
_VERB = re.compile(r"\b(?:include[sd]?|contain[sd]?|show[sn]?|indicat\w*|report\w*|focus\w*|reflect\w*|request\w*|are|were|is|was|have|has|observed|review\w*|analyzed|schedule|maintain|document|clarify|collect)\b", re.I)


def _communication_sentences(values):
    retained = []
    for value in values:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", value):
            sentence = sentence.strip()
            if (sentence.endswith(".") and "..." not in sentence
                    and _COMMUNICATION.search(sentence) and _VERB.search(sentence)
                    and not _OTHER_DOMAIN.search(sentence) and not _BLOCKER_CAUSE.search(sentence)
                    and not re.search(r"\d|\b(?:but|and|because)\.$", sentence, re.I)):
                retained.append(sentence)
    return deduplicate_public_items(retained)


def validated_team_collaboration_update(finding, provider_output, context):
    """Use existing scoped metrics; retain only complete communication-domain prose."""
    metrics = context.evidence_metrics.get("collaboration_blocker_metrics")
    if metrics is None:
        return None
    message_refs = [ref for ref in finding.evidence_refs if ref.source_type == "collaboration_message"]
    period = f"{metrics.evidence_start:%Y-%m-%d UTC} to {metrics.evidence_end:%Y-%m-%d UTC}"
    summary = (
        f"Collaboration: Selected-team evidence from {period}. "
        f"Verified blocker records show {metrics.unresolved_blocker_count} active blockers, "
        f"including {metrics.stale_unresolved_blocker_count} stale blockers, and "
        f"{metrics.resolved_blocker_count} blockers resolved within the selected period."
    )
    if message_refs:
        themes = _communication_sentences([
            finding.summary, *getattr(provider_output, "communication_observations", []),
        ])
        # A question in an authorized message can support an inquiry observation,
        # never completion. This checks the existing evidence; it adds no NLP feed.
        if any("?" in ref.snippet and re.search(r"\b(?:status|done|complet\w*|finish\w*)\b", ref.snippet, re.I)
               for ref in message_refs):
            themes.append("Recent messages included inquiries about task status.")
        completion_boundary = "Collaboration messages do not independently verify task completion."
        # Reserve the boundary sentence and retain whole themes within the budget.
        # Slicing the finished summary can turn a valid theme into a public fragment.
        remaining = 3000 - len(summary) - len(completion_boundary) - 1
        retained_themes = []
        for theme in deduplicate_public_items(themes):
            if len(theme) + 1 <= remaining:
                retained_themes.append(theme)
                remaining -= len(theme) + 1
            if len(retained_themes) == 6:
                break
        summary += " " + " ".join([*retained_themes, completion_boundary])
    limitations = [
        "Team collaboration evidence spans multiple team tasks. It is not all attributed to any one task.",
        "Blocker status and resolution records establish Collaboration-domain observations. They do not independently explain overall delivery performance.",
    ]
    if not message_refs:
        limitations.append("No collaboration messages were retrieved within the selected period.")
    if metrics.invalid_timestamp_count:
        limitations.append("Invalid blocker timestamps limit resolution-time calculations.")
    if not context.evidence_metrics.get("collaboration_timestamps", True):
        limitations.append("Missing or invalid message timestamps limit time-based observations.")
    actions = _communication_sentences(finding.recommended_actions)
    if metrics.resolved_blocker_count:
        actions.append("Review the documented resolution steps for the resolved blockers before attributing a recurring cause.")
    if metrics.unresolved_blocker_count:
        actions.append("Review active blocker records and confirm their current resolution status with the manager.")
    if not actions:
        actions.append("Collect authorized team communication evidence before drawing further Collaboration conclusions.")
    return dict(summary=summary, limitations=limitations,
                recommended_actions=deduplicate_public_items(actions)[:20])
