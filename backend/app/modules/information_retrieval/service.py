from collections import Counter
from datetime import datetime
import math
from typing import Literal

from backend.app.modules.information_retrieval.tokenizer import (
    generate_snippet,
    tokenize,
)
from backend.app.schemas import SearchResultItem

# Explicit standard BM25 constants
BM25_K1 = 1.5
BM25_B = 0.75
TITLE_WEIGHT = 2  # Task title boost factor


class SearchableDocument:
    def __init__(
        self,
        source_type: Literal["task", "collaboration"],
        record_id: str,
        title: str | None,
        sections: list[tuple[str, str]],
        tokens: list[str],
        team_id: str | None = None,
        team_name: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ):
        self.source_type = source_type
        self.record_id = record_id
        self.title = title
        self.sections = sections
        self.tokens = tokens
        self.token_counts = Counter(tokens)
        self.doc_length = len(tokens)
        self.team_id = team_id
        self.team_name = team_name
        self.created_at = created_at
        self.updated_at = updated_at

    @property
    def sort_timestamp(self) -> float:
        """Parse updated_at or created_at for deterministic secondary sorting."""
        ts_str = self.updated_at or self.created_at
        if ts_str:
            try:
                # Handle ISO timestamps with Z or timezone offset
                clean_ts = ts_str.replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean_ts)
                return dt.timestamp()
            except Exception:
                pass
        return 0.0


def build_task_document(
    doc: dict,
    team_name_map: dict[str, str] | None = None,
) -> SearchableDocument:
    """Build a SearchableDocument from a MongoDB task document without leaking private metadata."""
    team_name_map = team_name_map or {}
    record_id = str(doc["_id"])
    team_id = str(doc["team_id"]) if doc.get("team_id") else None
    team_name = team_name_map.get(team_id) if team_id else None

    title = doc.get("title", "")
    description = doc.get("description", "")
    skills = doc.get("required_skills")
    if skills is None:
        skills = doc.get("required_competencies") or doc.get("skills") or []
    if isinstance(skills, list):
        skills_text = " ".join(str(s) for s in skills if s)
    else:
        skills_text = str(skills) if skills else ""

    # Collect progress notes
    progress_notes = []
    for p in doc.get("progress_history", []):
        p_note = p.get("notes") or p.get("note") or p.get("progress_note")
        if p_note:
            progress_notes.append(str(p_note))
    progress_text = " ".join(progress_notes)

    # Collect blocker descriptions and resolutions
    blocker_texts = []
    for b in doc.get("blockers", []):
        if b.get("description"):
            blocker_texts.append(str(b["description"]))
        b_res = b.get("resolution_note") or b.get("resolution_notes")
        if b_res:
            blocker_texts.append(str(b_res))
    blocker_text = " ".join(blocker_texts)

    sections = [
        ("Title", title),
        ("Description", description),
    ]
    if skills_text:
        sections.append(("Skills", skills_text))
    if blocker_text:
        sections.append(("Blocker", blocker_text))
    if progress_text:
        sections.append(("Progress", progress_text))

    # Tokenize with title boost
    title_tokens = tokenize(title) * TITLE_WEIGHT
    desc_tokens = tokenize(description)
    skill_tokens = tokenize(skills_text)
    blocker_tokens = tokenize(blocker_text)
    progress_tokens = tokenize(progress_text)

    all_tokens = title_tokens + desc_tokens + skill_tokens + blocker_tokens + progress_tokens

    created_at = doc.get("created_at")
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    elif created_at is not None:
        created_at = str(created_at)

    updated_at = doc.get("updated_at")
    if isinstance(updated_at, datetime):
        updated_at = updated_at.isoformat()
    elif updated_at is not None:
        updated_at = str(updated_at)

    return SearchableDocument(
        source_type="task",
        record_id=record_id,
        title=title or None,
        sections=sections,
        tokens=all_tokens,
        team_id=team_id,
        team_name=team_name,
        created_at=created_at,
        updated_at=updated_at,
    )


def build_collaboration_document(
    doc: dict,
    team_name_map: dict[str, str] | None = None,
    include_deleted_content: bool = False,
) -> SearchableDocument | None:
    """Build a SearchableDocument from a MongoDB collaboration message document."""
    team_name_map = team_name_map or {}
    record_id = str(doc["_id"])
    team_id = str(doc["team_id"]) if doc.get("team_id") else None
    team_name = team_name_map.get(team_id) if team_id else None

    is_deleted = bool(doc.get("is_deleted", False))
    if is_deleted and not include_deleted_content:
        # Content is masked / omitted for normal non-admin retrieval
        content = ""
    else:
        content = doc.get("content", "") or ""

    if not content:
        return None

    sections = [
        ("Message", content),
    ]

    all_tokens = tokenize(content)

    created_at = doc.get("created_at")
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    elif created_at is not None:
        created_at = str(created_at)

    updated_at = doc.get("updated_at") or doc.get("edited_at")
    if isinstance(updated_at, datetime):
        updated_at = updated_at.isoformat()
    elif updated_at is not None:
        updated_at = str(updated_at)

    return SearchableDocument(
        source_type="collaboration",
        record_id=record_id,
        title=None,
        sections=sections,
        tokens=all_tokens,
        team_id=team_id,
        team_name=team_name,
        created_at=created_at,
        updated_at=updated_at,
    )


class BM25Ranker:
    """Deterministic BM25 lexical ranking engine."""

    def __init__(self, documents: list[SearchableDocument], k1: float = BM25_K1, b: float = BM25_B):
        self.documents = documents
        self.k1 = k1
        self.b = b
        self.N = len(documents)
        self.avgdl = (
            sum(doc.doc_length for doc in documents) / self.N if self.N > 0 else 0.0
        )
        self.df = self._compute_doc_frequencies()

    def _compute_doc_frequencies(self) -> dict[str, int]:
        df: dict[str, int] = {}
        for doc in self.documents:
            unique_terms = set(doc.token_counts.keys())
            for term in unique_terms:
                df[term] = df.get(term, 0) + 1
        return df

    def compute_idf(self, term: str) -> float:
        """
        Compute standard BM25 Inverse Document Frequency:
        IDF(term) = ln(1 + (N - df(term) + 0.5) / (df(term) + 0.5))
        """
        df_val = self.df.get(term, 0)
        return math.log(1.0 + (self.N - df_val + 0.5) / (df_val + 0.5))

    def score(self, doc: SearchableDocument, query_terms: list[str]) -> tuple[float, list[str]]:
        """
        Compute BM25 score for a single document given query terms.
        Returns (score, matched_terms).
        """
        if doc.doc_length == 0 or self.avgdl == 0.0:
            return 0.0, []

        total_score = 0.0
        matched_terms = []
        unique_query_terms = list(dict.fromkeys(query_terms))

        for term in unique_query_terms:
            tf = doc.token_counts.get(term, 0)
            if tf > 0:
                matched_terms.append(term)
                idf = self.compute_idf(term)
                # BM25 term score
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc.doc_length / self.avgdl))
                total_score += idf * (numerator / denominator)

        return total_score, matched_terms

    def rank(self, query: str, limit: int = 10) -> tuple[int, list[SearchResultItem]]:
        """
        Rank candidate documents for the given query.
        Returns (total_matches, results_list).
        """
        query_terms = tokenize(query, filter_stopwords=True)
        if not query_terms or self.N == 0:
            return 0, []

        scored_docs = []
        for doc in self.documents:
            score_val, matched = self.score(doc, query_terms)
            if score_val > 0.0:
                snippet = generate_snippet(doc.sections, query_terms)
                scored_docs.append(
                    (
                        score_val,
                        doc.sort_timestamp,
                        doc.record_id,
                        SearchResultItem(
                            source_type=doc.source_type,
                            record_id=doc.record_id,
                            title=doc.title,
                            snippet=snippet,
                            score=round(score_val, 4),
                            matched_terms=matched,
                            team_id=doc.team_id,
                            team_name=doc.team_name,
                            created_at=doc.created_at,
                            updated_at=doc.updated_at,
                        ),
                    )
                )

        # Deterministic sorting:
        # 1. Score descending
        # 2. Timestamp descending
        # 3. Record ID string ascending
        scored_docs.sort(key=lambda item: (-item[0], -item[1], item[2]))

        total_matches = len(scored_docs)
        results = [item[3] for item in scored_docs[:limit]]
        return total_matches, results
