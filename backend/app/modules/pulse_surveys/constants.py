"""
Constants and core date utilities for the Weekly Pulse Survey module.
Provides authoritative configuration and helpers to avoid circular dependencies between routers and agents.
"""

from datetime import datetime, timedelta, timezone

MINIMUM_AGGREGATE_RESPONSES: int = 3
PULSE_COLLECTION_NAME: str = "weekly_pulse_responses"
TEAMS_COLLECTION_NAME: str = "teams"


def get_current_week_start(now: datetime | None = None) -> datetime:
    """Derive the Monday 00:00:00 UTC datetime for the server's current UTC week."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start - timedelta(days=start.weekday())
