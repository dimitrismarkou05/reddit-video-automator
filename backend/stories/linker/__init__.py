"""Update detection and parent-story linking algorithm."""

from stories.linker.core import UpdateLinker
from stories.linker.models import InlineUpdateSection
from stories.linker.patterns import UPDATE_KEYWORDS, INLINE_UPDATE_PATTERNS

__all__ = [
    "UpdateLinker",
    "InlineUpdateSection",
    "UPDATE_KEYWORDS",
    "INLINE_UPDATE_PATTERNS",
]
