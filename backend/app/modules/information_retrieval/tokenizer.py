import re
import unicodedata

# Documented minimal English stop-word list for lexical retrieval precision
ENGLISH_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "is",
        "it",
        "this",
        "that",
        "by",
        "from",
        "as",
        "be",
        "are",
        "was",
        "were",
        "but",
        "not",
        "if",
        "then",
        "so",
    }
)

TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)


def normalize_text(text: str | None) -> str:
    """Normalize unicode characters and collapse repeated whitespace."""
    if not text:
        return ""
    # Unicode canonical decomposition and normalization
    normalized = unicodedata.normalize("NFKC", text)
    # Collapse multiple whitespaces into a single space
    return " ".join(normalized.split())


def tokenize(text: str | None, filter_stopwords: bool = True) -> list[str]:
    """Tokenize Unicode text using casefold, word-like pattern, and optional stop word filtering."""
    if not text:
        return []
    normalized = normalize_text(text)
    casefolded = normalized.casefold()
    raw_tokens = TOKEN_PATTERN.findall(casefolded)

    # Keep only tokens with at least one alphanumeric character
    valid_tokens = [
        tok.strip("_")
        for tok in raw_tokens
        if any(c.isalnum() for c in tok)
    ]
    valid_tokens = [tok for tok in valid_tokens if len(tok) > 0]

    if filter_stopwords:
        return [tok for tok in valid_tokens if tok not in ENGLISH_STOP_WORDS]
    return valid_tokens


def is_valid_query(query: str | None, max_length: int = 200) -> tuple[bool, str]:
    """
    Validate search query string.
    Returns (is_valid, error_message).
    Rejects null, empty, whitespace-only, punctuation-only, and excessively long queries.
    """
    if query is None:
        return False, "Search query is required."

    trimmed = query.strip()
    if not trimmed:
        return False, "Search query cannot be empty."

    if len(trimmed) > max_length:
        return False, f"Search query exceeds maximum allowed length of {max_length} characters."

    tokens = tokenize(trimmed, filter_stopwords=False)
    if not tokens:
        return False, "Search query must contain valid alphanumeric search terms."

    searchable_tokens = tokenize(trimmed, filter_stopwords=True)
    if not searchable_tokens:
        # If query only has stop words (e.g. "and the"), we can allow non-stopword token fallback or reject.
        # However, to be strict and helpful, require at least one searchable non-stopword term.
        return False, "Search query must contain at least one meaningful non-stopword term."

    return True, ""


def generate_snippet(
    sections: list[tuple[str, str]],
    query_terms: list[str],
    max_length: int = 160,
) -> str:
    """
    Generate an explainable plain-text snippet from document sections with matched terms.
    sections is a list of (label, text) tuples, e.g. [("Title", "..."), ("Description", "...")].
    """
    if not sections:
        return ""

    lowered_terms = [t.casefold() for t in query_terms if t]
    best_section_label = ""
    best_text = ""
    best_term_pos = -1

    # First, look for a section containing any query term
    for label, text in sections:
        if not text:
            continue
        folded = text.casefold()
        for term in lowered_terms:
            pos = folded.find(term)
            if pos != -1:
                if best_term_pos == -1 or (label in ("Title", "Blocker", "Progress")):
                    best_section_label = label
                    best_text = normalize_text(text)
                    best_term_pos = pos
                    break
        if best_section_label and best_section_label in ("Title", "Blocker"):
            break

    # If no term found in any section, default to first non-empty section
    if not best_text:
        for label, text in sections:
            if text and text.strip():
                best_section_label = label
                best_text = normalize_text(text)
                break

    if not best_text:
        return ""

    prefix_label = f"[{best_section_label}] " if best_section_label else ""
    available_len = max_length - len(prefix_label)

    if len(best_text) <= available_len:
        return f"{prefix_label}{best_text}"

    # Center window around matched term if found
    if best_term_pos != -1 and best_term_pos < len(best_text):
        half = available_len // 2
        start = max(0, best_term_pos - half)
        end = min(len(best_text), start + available_len)
        if end == len(best_text):
            start = max(0, end - available_len)

        snippet_chunk = best_text[start:end].strip()
        has_left = start > 0
        has_right = end < len(best_text)

        prefix = "..." if has_left else ""
        suffix = "..." if has_right else ""
        return f"{prefix_label}{prefix}{snippet_chunk}{suffix}"

    return f"{prefix_label}{best_text[:available_len].strip()}..."
