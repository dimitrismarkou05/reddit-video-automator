"""Search helpers for story queries."""

import re
from typing import List, Optional
from sqlalchemy import func, and_, case
from stories.models import Story


def _normalize(text: str) -> str:
    """Strip punctuation and lowercase for matching."""
    if not text:
        return ""
    # Convert smart quotes to straight, dashes to hyphen
    text = text.replace("\u2019", "'").replace("\u2018", "'")   # single quotes
    text = text.replace("\u201C", '"').replace("\u201D", '"')   # double quotes
    text = text.replace("\u2014", "-").replace("\u2013", "-")   # em/en dashes
    # Strip everything except alphanumerics and spaces
    return re.sub(r'[^a-zA-Z0-9\s]', '', text.lower()).strip()


def _tokenize(search: str) -> List[str]:
    clean = _normalize(search)
    return clean.split() if clean else []


def _sql_normalize(column):
    # Lowercase first
    expr = func.lower(column)
    
    # Convert smart quotes to straight quotes (so we only need one replace per type)
    expr = func.replace(expr, "\u2019", "'")   # right single quotation mark
    expr = func.replace(expr, "\u2018", "'")   # left single quotation mark
    expr = func.replace(expr, "\u201C", '"')   # left double quotation mark
    expr = func.replace(expr, "\u201D", '"')   # right double quotation mark
    expr = func.replace(expr, "\u2014", "-")   # em dash
    expr = func.replace(expr, "\u2013", "-")   # en dash
    
    # Strip all remaining punctuation entirely
    punct = [
        "'", '"', '-', '.', ',', '!', '?', '[', ']', '(', ')', ':', ';',
        '/', '\\', '#', '@', '$', '%', '^', '&', '*', '+', '=', '|', '<', '>', '{', '}',
    ]
    for ch in punct:
        expr = func.replace(expr, ch, "")
    
    return func.trim(expr)


def build_search_filter(search: str) -> Optional[object]:
    tokens = _tokenize(search)
    if not tokens:
        return None

    normalized_title = _sql_normalize(Story.title)
    conditions = [normalized_title.ilike(f"%{token}%") for token in tokens]
    return and_(*conditions)


def build_search_rank(search: str):
    stripped = search.strip()
    normalized_title = _sql_normalize(Story.title)
    normalized_phrase = _normalize(stripped)
    
    # Full normalized phrase match gets highest score
    score = case(
        (normalized_title.ilike(f"%{normalized_phrase}%"), 100),
        else_=0
    )
    
    for token in _tokenize(search):
        weight = 10 if len(token) >= 3 else 5
        score = score + case(
            (normalized_title.ilike(f"%{token}%"), weight),
            else_=0
        )

    return score