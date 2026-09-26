"""Canonical public reporting items; no fuzzy matching or model-based deduplication."""
import re
from collections.abc import Iterable

TASK_MESSAGES_UNAVAILABLE = (
    "Task-linked collaboration-message evidence is unavailable. "
    "No trustworthy messages explicitly linked to the selected task were available."
)
PULSE_COLLECTION_ACTION = "Collect privacy-safe team pulse ratings in upcoming weeks for comparison."
WORKFORCE_PULSE_COLLECTION_ACTION = (
    "Collect privacy-safe team pulse ratings in upcoming weeks for comparison, "
    "and review current delivery priorities with the manager."
)


def wellbeing_collection_action(workflow_intent: str | None) -> str:
    return (WORKFORCE_PULSE_COLLECTION_ACTION
            if workflow_intent in {"team_workload_analysis", "general_workforce_question"}
            else PULSE_COLLECTION_ACTION)


def _item_key(value: str) -> str:
    # Equality of the complete word sequence tolerates punctuation/case differences.
    # Never collapse distinct items merely because they share vocabulary.
    return " ".join(re.findall(r"\w+", value.casefold()))


def deduplicate_public_items(items: Iterable[str], workflow_intent: str | None = None) -> list[str]:
    aliases = {
        _item_key(TASK_MESSAGES_UNAVAILABLE): TASK_MESSAGES_UNAVAILABLE,
        _item_key("Task-linked collaboration-message evidence is unavailable; no trustworthy messages explicitly linked to the selected task were available."): TASK_MESSAGES_UNAVAILABLE,
    }
    for action in (
        PULSE_COLLECTION_ACTION, WORKFORCE_PULSE_COLLECTION_ACTION,
        "Collect privacy-safe pulse ratings in upcoming weeks and discuss delivery priorities with the manager.",
    ):
        aliases[_item_key(action)] = wellbeing_collection_action(workflow_intent)
    result, seen = [], set()
    for item in items:
        item = item.strip()
        if not item:
            continue
        item = aliases.get(_item_key(item), item)
        item_key = _item_key(item)
        if item_key not in seen:
            result.append(item)
            seen.add(item_key)
    return result
