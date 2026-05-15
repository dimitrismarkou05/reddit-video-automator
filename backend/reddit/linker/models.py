"""Data models for update linking."""

from dataclasses import dataclass


@dataclass
class InlineUpdateSection:
    """Represents an inline update section found within a post body."""
    marker: str           # The raw marker text found (e.g., "UPDATE:")
    content: str          # The content following the marker
    position: int         # Character position in the original body
    section_index: int    # Which section number this is (0 = original, 1+ = updates)
