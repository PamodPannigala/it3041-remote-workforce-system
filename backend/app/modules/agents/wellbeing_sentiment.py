"""
Deterministic, privacy-preserving sentiment analysis for Weekly Pulse Survey
optional_comment fields within the Well-being Agent aggregation pipeline.

Design constraints:
- VADER (vaderSentiment 3.3.2) is the sole analysis engine: lexicon-based,
  no external API calls, no GPU, no training data.
- Sentiment is computed PER TEAM PER WEEK from the set of qualifying comments
  for that bucket; it is NEVER computed per individual respondent in any output.
- The same k-anonymity threshold used for numeric metrics applies to comment
  counts before any aggregate score is exposed.
- Individual comment text and per-comment scores are NEVER included in any
  manager-, admin-, or coordinator-facing output.
- If VADER is unavailable or a comment fails analysis the comment is silently
  excluded; the rest of the aggregate is unaffected and no exception is raised.
- Sentiment data must never flow into task assignment (enforced by caller;
  this module only computes — it never routes).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from backend.app.modules.pulse_surveys.constants import MINIMUM_AGGREGATE_RESPONSES

logger = logging.getLogger("remote_workforce.agents.wellbeing_sentiment")

# ---------------------------------------------------------------------------
# 1. Constants
# ---------------------------------------------------------------------------

# Reuse the authoritative k-anonymity threshold — never duplicate the value.
SENTIMENT_PRIVACY_THRESHOLD: int = MINIMUM_AGGREGATE_RESPONSES  # == 3

# Fixed numeric thresholds for label mapping (VADER compound range: -1.0 to 1.0)
SENTIMENT_POSITIVE_CUTOFF: float = 0.05
SENTIMENT_NEGATIVE_CUTOFF: float = -0.05

SentimentLabel = Literal["Positive", "Neutral", "Negative"]


# ---------------------------------------------------------------------------
# 2. Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SentimentResult:
    """
    Privacy-safe aggregate sentiment for one (team_id, week_start) bucket.

    Fields exposed to manager/admin/coordinator:
      - average_compound   : float | None  (None when suppressed by threshold)
      - label              : SentimentLabel | None  (None when suppressed)
      - qualifying_comment_count : int  (always present; count only, not text)
      - failed_comment_count     : int  (VADER failures excluded from aggregate)

    Individual comment text and per-comment scores are NEVER stored here.
    """

    average_compound: float | None
    label: SentimentLabel | None
    qualifying_comment_count: int
    failed_comment_count: int

    def to_summary_text(self) -> str:
        """
        Returns a single deterministic sentence suitable for injection into the
        LLM evidence context.  Raw comments are NEVER included.
        """
        if self.average_compound is None or self.label is None:
            return "Team sentiment: Not enough data; sentiment suppressed to protect employee anonymity."

        score_str = f"{self.average_compound:+.2f}"
        count_note = (
            f"based on {self.qualifying_comment_count} qualifying comment"
            f"{'s' if self.qualifying_comment_count != 1 else ''}"
        )
        failed_note = (
            f", {self.failed_comment_count} comment"
            f"{'s' if self.failed_comment_count != 1 else ''} excluded due to analysis failure"
            if self.failed_comment_count > 0
            else ""
        )
        return (
            f"Team sentiment: {self.label} ({score_str}), {count_note}{failed_note}."
        )


# ---------------------------------------------------------------------------
# 3. Lazy VADER loader
# ---------------------------------------------------------------------------

_analyzer = None  # module-level singleton; loaded once


def _get_analyzer():
    """
    Returns a cached SentimentIntensityAnalyzer, or None if vaderSentiment is
    unavailable.  Failure is logged once and the caller falls back to None.
    """
    global _analyzer
    if _analyzer is not None:
        return _analyzer
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer  # type: ignore
        _analyzer = SentimentIntensityAnalyzer()
        return _analyzer
    except Exception as exc:  # ImportError, OSError, etc.
        logger.error(
            "vaderSentiment is unavailable — sentiment analysis disabled: %s",
            type(exc).__name__,
        )
        return None


# ---------------------------------------------------------------------------
# 4. Core computation function
# ---------------------------------------------------------------------------

def compute_team_sentiment(
    comments: list[str],
    min_threshold: int = SENTIMENT_PRIVACY_THRESHOLD,
) -> SentimentResult:
    """
    Computes a privacy-preserving aggregate sentiment score for a team-week bucket.

    Parameters
    ----------
    comments : list[str]
        Raw optional_comment strings from a single (team_id, week_start) bucket.
        Must be pre-filtered so that each entry is non-null and non-empty after
        stripping.  Caller is responsible for this pre-filter (done inside
        compute_deterministic_wellbeing_metrics).

    min_threshold : int
        Minimum number of qualifying comments required before exposing the
        aggregate score.  Defaults to SENTIMENT_PRIVACY_THRESHOLD (== 3).
        Reuses the same constant as numeric metric k-anonymity.

    Returns
    -------
    SentimentResult
        - If len(qualifying_comments) < min_threshold:
            average_compound=None, label=None  (suppressed).
        - Otherwise:
            average_compound = mean of VADER compound scores, rounded to 2 dp.
            label = 'Positive' / 'Neutral' / 'Negative' per fixed thresholds.
        Individual comments and per-comment scores are NEVER in the result.

    Failure safety
    --------------
    If VADER is unavailable, returns a fully suppressed SentimentResult with
    qualifying_comment_count = 0 and failed_comment_count = len(comments).
    If a single comment raises an exception during analysis it is counted in
    failed_comment_count and excluded; the aggregate of the rest proceeds.
    """
    analyzer = _get_analyzer()

    if analyzer is None:
        # VADER is not installed / failed to load — fail safe, suppress all.
        logger.warning(
            "compute_team_sentiment: VADER unavailable; returning suppressed result "
            "for %d comment(s).",
            len(comments),
        )
        return SentimentResult(
            average_compound=None,
            label=None,
            qualifying_comment_count=0,
            failed_comment_count=len(comments),
        )

    compound_scores: list[float] = []
    failed_count: int = 0

    for raw_comment in comments:
        # Defensive strip — caller should have already stripped, but be safe.
        comment = raw_comment.strip() if isinstance(raw_comment, str) else ""
        if not comment:
            # Empty after strip — treat as a failed/invalid comment.
            failed_count += 1
            continue
        try:
            scores = analyzer.polarity_scores(comment)
            compound_scores.append(float(scores["compound"]))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "compute_team_sentiment: VADER analysis failed for one comment "
                "(%s); excluding from aggregate.",
                type(exc).__name__,
            )
            failed_count += 1

    qualifying_count = len(compound_scores)

    if qualifying_count < min_threshold:
        return SentimentResult(
            average_compound=None,
            label=None,
            qualifying_comment_count=qualifying_count,
            failed_comment_count=failed_count,
        )

    avg = round(sum(compound_scores) / qualifying_count, 2)
    label = _score_to_label(avg)

    return SentimentResult(
        average_compound=avg,
        label=label,
        qualifying_comment_count=qualifying_count,
        failed_comment_count=failed_count,
    )


# ---------------------------------------------------------------------------
# 5. Label mapping helper
# ---------------------------------------------------------------------------

def _score_to_label(compound: float) -> SentimentLabel:
    """
    Maps a VADER compound score to a human label using fixed named-constant thresholds.

    SENTIMENT_POSITIVE_CUTOFF  >= 0.05  -> 'Positive'
    SENTIMENT_NEGATIVE_CUTOFF  <= -0.05 -> 'Negative'
    otherwise                           -> 'Neutral'
    """
    if compound >= SENTIMENT_POSITIVE_CUTOFF:
        return "Positive"
    if compound <= SENTIMENT_NEGATIVE_CUTOFF:
        return "Negative"
    return "Neutral"
